"""Rastreador dos endereços que o Nexus escreve (porta única, 09/10/2026): percorre as páginas a partir do Início, como
um navegador logado, e junta todo endereço interno que sai no HTML (href, src, action, data-*), no JavaScript (caminho
do Nexus entre aspas que não passa pelo nexusRota) e no Location dos redirecionamentos.

Por que existe (Levi, 09/10/2026: "a partir de segunda quero o Nexus como link principal"): no servidor o Nexus mora em
/nexus, e cada endereço escrito a partir da raiz cai na plataforma de Performance. Ninguém lembra de ~300 endereços; o
rastreador lembra. Usado por `test_prefixo.py` nos três modos (debaixo do /nexus com o Caddy cortando o caminho, sem
cortar, e na raiz).
"""
import html as _html
import re
from collections import deque
from urllib.parse import urljoin, urlsplit

# atributo="valor" (o Jinja escreve com aspas duplas; aspas simples só aparecem dentro de JavaScript)
_ATRIBUTO = re.compile(r'\s(href|src|action|formaction|poster|data-[\w-]+)="([^"]*)"', re.I)
_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.I | re.S)
_COMENTARIO_HTML = re.compile(r"<!--.*?-->", re.S)
# um caminho do Nexus entre aspas, no JavaScript: os primeiros segmentos que são dele (spec 2026-10-09, seção 2)
SEGMENTOS = ("t", "os", "static", "entrar", "sair", "tema", "cadeira", "saude")
_LITERAL_JS = re.compile(r"""(?P<q>['"`])/(?:%s)(?=[/'"`?#])""" % "|".join(SEGMENTOS))
# O `next` do login do OS Creator vai SEM o prefixo, de propósito: o clone só devolve para /os/... e a ponte tira o
# prefixo do que chegar com ele. É o único caminho do Nexus que o JavaScript escreve cru.
_NEXT_DO_CLONE = re.compile(r"""(encodeURIComponent\(|var volta = )['"]/os/_nexus/""")
_LITERAL_DO_CLONE = re.compile(rb"""(value=)?([\"'`(])/os(?=[/\"'`?#)])""")


def da_plataforma(caminho: str) -> bool:
    """Endereço da Plataforma de Performance que o Nexus escreve DE PROPÓSITO na raiz (porta única, 09/10/2026): o
    formulário do passe e o Sair (`/painel/nexus/...`) e as telas do mapa ("Abrir em outra aba"). No servidor a
    plataforma mora na raiz, ao lado do Nexus em /nexus: com o prefixo, eles quebrariam. Não é página do Nexus, e o
    rastreador não segue."""
    from nexus.performance import porta
    return caminho in (porta.ENTRAR, porta.SAIR) or porta.destino_permitido(caminho) is not None


def _eh_caminho(valor: str, atributo: str) -> bool:
    if not valor.startswith("/") or valor.startswith("//"):
        return False
    if atributo.lower().startswith("data-"):
        return len(valor) > 1 and (valor[1].isalnum() or valor[1] == "_")
    return True


def caminhos_do_html(texto: str):
    """(onde, endereço) de cada endereço interno do HTML: atributos e literais do JavaScript."""
    sem_comentario = _COMENTARIO_HTML.sub("", texto)
    for m in _ATRIBUTO.finditer(sem_comentario):
        valor = _html.unescape(m.group(2))
        if _eh_caminho(valor, m.group(1)):
            yield m.group(1), valor
    for m in _SCRIPT.finditer(sem_comentario):
        yield from caminhos_do_js(m.group(2), json="application/json" in m.group(1))


def caminhos_do_js(texto: str, json: bool = False):
    """Os caminhos do Nexus entre aspas que não passam pelo nexusRota (no JSON escrito pelo servidor, todos)."""
    for m in _LITERAL_JS.finditer(texto):
        antes = texto[max(0, m.start() - 40):m.start()]
        if not json and (re.search(r"[Rr]ota\($", antes) or _NEXT_DO_CLONE.search(antes + m.group("q") + "/os/_nexus/")):
            continue
        fim = texto.find(m.group("q"), m.end())
        yield "js", texto[m.start("q") + 1:fim if fim > 0 else m.end() + 30]


def literais_do_clone_sem_prefixo(corpo: bytes, prefixo: str):
    """Os /os/... do OS Creator embutido que a ponte deixou sem o prefixo (menos o value= do `next` do login)."""
    return [m.group(0).decode("utf-8", "replace") for m in _LITERAL_DO_CLONE.finditer(corpo) if not m.group(1)] \
        if prefixo else []


class Rastreio:
    def __init__(self, cliente, prefixo: str, limite: int = 400):
        self.cliente, self.prefixo, self.limite = cliente, prefixo, limite
        self.visitados: dict[str, int] = {}
        self.ruins: list[tuple[str, str, str]] = []          # (página, onde, endereço)
        self.redirecionamentos: list[tuple[str, str]] = []
        self.da_plataforma: list[tuple[str, str, str]] = []     # (página, onde, endereço da plataforma)

    def interno_certo(self, caminho: str) -> bool:
        if self.prefixo:
            return caminho == self.prefixo or caminho.startswith(self.prefixo + "/") \
                or caminho.startswith(self.prefixo + "?")
        return not (caminho == "/nexus" or caminho.startswith("/nexus/"))

    def _seguir(self, caminho: str) -> bool:
        """Só páginas do Nexus por GET; nada que saia, baixe arquivo ou grave."""
        local = caminho[len(self.prefixo):] if self.prefixo and caminho.startswith(self.prefixo) else caminho
        p = urlsplit(local).path
        if not self.interno_certo(caminho) or p in ("/sair", "/os/logout") or p.startswith("/static/"):
            return False
        if re.search(r"\.(pdf|xlsx|csv|zip|png|jpe?g|gif|svg|ico|css|woff2?)$", p, re.I):
            return False
        # o OS Creator embutido: a página e os .js dele (a ponte reescreve), não as imagens nem as rotas de dado
        if p.startswith("/os/") and (p.startswith("/os/api/") or "/foto" in p or "/anexo" in p):
            return False
        # downloads e ações que existem como GET (relatório, PDF da PT, fotos)
        return not re.search(r"/(relatorio|pdf|foto|fotos)(/|$)", p)

    def percorrer(self, inicio: str):
        fila = deque([inicio])
        while fila and len(self.visitados) < self.limite:
            url = fila.popleft()
            chave = urlsplit(url).path
            if chave in self.visitados:
                continue
            resp = self.cliente.get(url)
            self.visitados[chave] = resp.status_code
            destino = resp.headers.get("Location")
            if destino:
                self.redirecionamentos.append((url, destino))
                alvo = urljoin(url, destino)
                if not alvo.startswith("/") and "://" in alvo:
                    alvo = urlsplit(alvo).path + ("?" + urlsplit(alvo).query if urlsplit(alvo).query else "")
                if not self.interno_certo(destino if destino.startswith("/") else alvo):
                    self.ruins.append((url, "Location", destino))
                elif self._seguir(alvo):
                    fila.append(alvo)
                continue
            tipo = resp.headers.get("Content-Type", "")
            corpo = resp.get_data()
            eh_clone = urlsplit(url).path.startswith((self.prefixo or "") + "/os/")
            if eh_clone:
                for lit in literais_do_clone_sem_prefixo(corpo, self.prefixo):
                    self.ruins.append((url, "clone", lit))
            if "javascript" in tipo:
                if not eh_clone:
                    for onde, c in caminhos_do_js(corpo.decode("utf-8", "replace")):
                        self.ruins.append((url, onde, c))
                continue
            if "text/html" not in tipo:
                continue
            for onde, caminho in caminhos_do_html(corpo.decode("utf-8", "replace")):
                if eh_clone and onde == "js":
                    continue                    # o JavaScript do clone é conferido pelo literal (acima)
                if onde != "js" and da_plataforma(caminho):
                    self.da_plataforma.append((url, onde, caminho))
                    continue                    # o endereço da plataforma, na raiz de propósito (moldura e passe)
                if not self.interno_certo(caminho):
                    self.ruins.append((url, onde, caminho))
                    continue
                completo = urljoin(url, caminho)
                if onde.lower() in ("href", "src", "data-url", "data-primeira", "data-fragmento", "data-pagina") \
                        and self._seguir(completo):
                    fila.append(completo)
                elif onde.lower() == "src" and completo.endswith(".js") and "/os/static/" in completo:
                    fila.append(completo)
        return self
