"""As sugestões do Início (24/10/2026, Levi: "em início quero uma sub aba chamada 'Sugestões'. Vai ter uma tela para a
pessoa sugerir, os administradores verão em lista a pessoa que pediu, o que pediu e anexos. A pessoa que vai pedir vai
botar um título, uma descrição, poderá selecionar uma área (a área que ela tem visão como 'COS, PCM, Performance' etc...
Também será possível anexar arquivos como .MD, DOCs, PDFs, imagens. Bote um limite no tamanho desses arquivos para não
pesar tanto no server").

O Nexus é a FONTE: 1 linha por sugestão no livro `nexus_sugestoes · fato_sugestao`, registrado no catálogo antes da 1ª
gravação (nexus/dados/CLAUDE.md, regra 10). Em claro só o dia, a área (o id da torre) e a pessoa por código; o título, a
descrição, o nome de quem pediu e os nomes dos anexos vão cifrados (o Cofre, como as ocorrências): o banco tem leitura
aberta. Os anexos ficam no disco do servidor (a pasta de dados do Nexus, como as fotos do HSEQ), com nome de arquivo
neutro (1.pdf, 2.png); o nome original só no livro, cifrado."""
import io
import json
import os
import re
import shutil
import threading
import time
import unicodedata
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app

from ..dados import livros

LIVRO, NOME_LIVRO, ABA = "nexus_sugestoes", "Nexus · sugestões", "fato_sugestao"
CAB = ("id", "registrado_em", "data_id", "area", "pessoa_id", "pessoa_hmac", "dados_cifrados")
TITULO_MAX, TEXTO_MAX, NOME_MAX = 120, 4000, 80
# o peso no servidor (o pedido do Levi): 5 MB por arquivo, 5 arquivos e 15 MB por sugestão. Um print de tela tem uns
# 300 KB; um PDF de manual, 2 a 4 MB
MB = 1024 * 1024
MAX_MB_ARQUIVO, MAX_ARQUIVOS, MAX_MB_TOTAL = 5, 5, 15
# a extensão -> (como conferir o conteúdo, o tipo servido). O conteúdo confere pelo começo do arquivo, não pelo nome: um
# executável renomeado para .pdf não passa (a mesma regra dos anexos da Solicitação de Engenharia do OS Creator)
TIPOS = {".md": ("texto", "text/markdown; charset=utf-8"), ".txt": ("texto", "text/plain; charset=utf-8"),
         ".pdf": ("pdf", "application/pdf"), ".doc": ("ole", "application/msword"),
         ".docx": ("zip", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
         ".png": ("imagem", "image/png"), ".jpg": ("imagem", "image/jpeg"), ".jpeg": ("imagem", "image/jpeg"),
         ".webp": ("imagem", "image/webp")}
_IMAGEM = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# o id: a letra do que é e 11 hexadecimais (a API do banco infere o tipo da coluna: só algarismos voltaria número)
ID_RE = re.compile(r"s[0-9a-f]{11}")
TTL_S = 60
CHAVES = ("NEXUS_CHAVE_CADASTRO", "NEXUS_PESSOA_HMAC", "GRIDCO_SQL_TOKEN")
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def limpar() -> None:
    _CACHE.clear()


def novo_id() -> str:
    return "s" + uuid.uuid4().hex[:11]


def faltam_chaves() -> list[str]:
    """As chaves do .env sem as quais nada se grava (a tela não mostra formulário que só recusaria)."""
    return [k for k in CHAVES if not current_app.config.get(k)]


def aceitos() -> str:
    return ", ".join(TIPOS)


def tamanho_txt(n: int) -> str:
    if n >= MB:
        return f"{n / MB:.1f} MB".replace(".", ",")
    return f"{max(1, round(n / 1024))} KB"


def _ctx(l: dict) -> str:
    """A cifra amarra o texto à linha: mudar a linha no banco perde o texto, em vez de levá-lo para outra sugestão."""
    return f"banco/sugestoes/{_txt(l.get('id'))}/{_txt(l.get('area')) or '-'}/{_txt(l.get('pessoa_hmac'))}"


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela o texto não vai cifrado")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _banco():
    from ..campo import visao
    return visao._base(), visao._sessao()


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _pasta(sid: str) -> Path:
    from ..cadastro.ligacoes import pasta_dados
    return pasta_dados(current_app.config) / "sugestoes" / sid


# ── os anexos ────────────────────────────────────────────────────────────────────────────────────────────────────────
def nome_seguro(nome) -> str:
    """O nome mostrado e o do download: sem o caminho que alguns navegadores mandam ('C:\\fakepath\\...'), sem barra e
    sem caractere de controle; o resto vira '_'."""
    base = re.split(r"[\\/]", str(nome or ""))[-1]
    base = re.sub(r"[^\w .,()-]+", "_", unicodedata.normalize("NFC", base))
    base = re.sub(r"\s+", " ", base).strip(" ._")
    raiz, ext = os.path.splitext(base)
    return (raiz[:NOME_MAX].rstrip(" ._") + ext.lower()) if raiz else ""


def _parece_texto(dados: bytes) -> bool:
    """Texto não tem byte zero no começo (um executável tem vários); o UTF-16 do Bloco de Notas tem, e começa pela marca."""
    amostra = dados[:4096]
    return amostra.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" not in amostra


def conteudo_bate(ext: str, dados: bytes) -> bool:
    jeito = TIPOS[ext][0]
    if jeito == "pdf":
        return b"%PDF-" in dados[:1024]                    # o leitor tolera lixo antes do cabeçalho, até 1 KB
    if jeito == "imagem":
        return dados.startswith(_IMAGEM) or (dados[:4] == b"RIFF" and dados[8:12] == b"WEBP")
    if jeito == "zip":
        return dados.startswith(b"PK\x03\x04")             # o .docx é zip por dentro
    if jeito == "ole":
        return dados.startswith(_OLE)
    return _parece_texto(dados)


def anexos(arquivos) -> list[dict]:
    """Os arquivos do formulário ([(nome, stream)]) -> [{nome, ext, dados}]. Arquivo recusado recusa a sugestão inteira,
    com o motivo: a pessoa anexou porque o arquivo importa. Cada um é lido só até o limite + 1 byte."""
    escolhidos = [(n, s) for n, s in (arquivos or []) if _txt(n)]
    if len(escolhidos) > MAX_ARQUIVOS:
        raise Recusada(f"São {len(escolhidos)} anexos: o limite é {MAX_ARQUIVOS} por sugestão")
    out, total = [], 0
    for nome_in, stream in escolhidos:
        nome = nome_seguro(nome_in)
        quem = f"“{nome or _txt(nome_in)}”"
        ext = os.path.splitext(nome)[1].lower()
        if ext not in TIPOS:
            raise Recusada(f"{quem}: tipo de arquivo não aceito. Aceitos: {aceitos()}")
        dados = stream.read(MAX_MB_ARQUIVO * MB + 1)
        if not dados:
            raise Recusada(f"{quem} veio vazio")
        if len(dados) > MAX_MB_ARQUIVO * MB:
            raise Recusada(f"{quem} passa de {MAX_MB_ARQUIVO} MB, o limite por arquivo")
        if not conteudo_bate(ext, dados):
            raise Recusada(f"{quem} não é {ext} de verdade: o conteúdo não bate com a extensão")
        total += len(dados)
        if total > MAX_MB_TOTAL * MB:
            raise Recusada(f"Os anexos passam de {MAX_MB_TOTAL} MB juntos, o limite por sugestão")
        out.append({"nome": nome, "ext": ext, "dados": dados})
    return out


def _gravar_anexos(sid: str, lista: list[dict]) -> list[dict]:
    """No disco, com nome neutro (1.pdf); cada um vai a um '.parcial' e só depois toma o nome: arquivo pela metade nunca
    aparece na lista."""
    if not lista:
        return []
    pasta = _pasta(sid)
    pasta.mkdir(parents=True, exist_ok=True)
    feitos = []
    for n, a in enumerate(lista, 1):
        destino = pasta / f"{n}{a['ext']}"
        tmp = destino.with_name(destino.name + ".parcial")
        tmp.write_bytes(a["dados"])
        tmp.replace(destino)
        feitos.append({"n": n, "nome": a["nome"], "arquivo": destino.name, "tamanho": len(a["dados"])})
    return feitos


def arquivo(sid: str, n) -> tuple[Path, dict] | None:
    """O arquivo `n` da sugestão `sid` no disco e o que o livro diz dele (o nome original); None se não houver."""
    if not ID_RE.fullmatch(_txt(sid)):
        return None
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    s = next((x for x in lista() if x["id"] == sid), None)
    a = next((x for x in (s or {}).get("anexos", []) if x.get("n") == n), None)
    if not a or not re.fullmatch(r"[1-9][0-9]?\.[a-z]{2,4}", _txt(a.get("arquivo"))):
        return None
    caminho = _pasta(sid) / a["arquivo"]
    return (caminho, a) if caminho.is_file() else None


def zip_da_sugestao(sid: str) -> tuple[bytes, str] | None:
    """Todos os anexos da sugestão num .zip (Levi, 24/10/2026: "gostaria a opção 'Baixar arquivos' baixa todos os
    arquivos da sugestão"), com o nome original de cada um; dois com o mesmo nome ganham " (2)". Montado na memória: são
    15 MB no máximo. None se a sugestão não existe ou nenhum anexo está no disco."""
    if not ID_RE.fullmatch(_txt(sid)):
        return None
    s = next((x for x in lista() if x["id"] == sid), None)
    if not s:
        return None
    buf, vistos, n = io.BytesIO(), set(), 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for a in s["anexos"]:
            achado = arquivo(sid, a.get("n"))
            if not achado:
                continue
            caminho, a = achado
            nome = nome_seguro(a.get("nome")) or a["arquivo"]
            raiz, ext = os.path.splitext(nome)
            novo, i = nome, 2
            while novo.lower() in vistos:
                novo, i = f"{raiz} ({i}){ext}", i + 1
            vistos.add(novo.lower())
            z.write(caminho, novo)
            n += 1
    if not n:
        return None
    # o título vira o nome do .zip; a barra dele ("Filtro/por usina") não é caminho: vira "_" antes do nome_seguro
    titulo = nome_seguro(re.sub(r"[\\/]", "_", s["titulo"]) + ".zip") if s["titulo"] else ""
    return buf.getvalue(), titulo or f"sugestao-{sid}.zip"


def tipo_servido(nome_arquivo: str) -> str:
    return TIPOS.get(os.path.splitext(nome_arquivo)[1].lower(), ("", "application/octet-stream"))[1]


def eh_imagem(nome_arquivo: str) -> bool:
    return TIPOS.get(os.path.splitext(nome_arquivo)[1].lower(), ("",))[0] == "imagem"


# ── gravar ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def _quem(usuario) -> dict:
    email = str((usuario or {}).get("email") or "").strip().lower()
    if not email:
        raise Recusada("Entre com o seu login (Microsoft ou Fracttal) para mandar uma sugestão: a senha de administrador "
                       "não diz quem é a pessoa")
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    cfg = current_app.config
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not codigo:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    nome = " ".join(str((usuario or {}).get("nome") or "").split()) or email
    from ..campo import visao
    try:
        pid = visao.pessoa_do_login(email, nome)
    except Exception:           # noqa: BLE001 — sem cadastro: fica o código do e-mail (regra 4: não liga = vazio)
        pid = None
    return {"email": email, "nome": nome, "hmac": codigo, "pessoa_id": pid}


def _linha(texto, maximo: int, falta: str, nome: str) -> str:
    t = " ".join(str(texto or "").split())
    if not t:
        raise Recusada(falta)
    if len(t) > maximo:
        raise Recusada(f"{nome} passou de {maximo} caracteres")
    return t


def _texto(texto, maximo: int, falta: str, nome: str) -> str:
    """A descrição guarda as quebras de linha (é um texto, não uma linha)."""
    t = str(texto or "").replace("\r\n", "\n").strip()
    if not t:
        raise Recusada(falta)
    if len(t) > maximo:
        raise Recusada(f"{nome} passou de {maximo} caracteres")
    return t


def _reler() -> list[dict]:
    """O livro relido agora, sem a cópia: gravar sobre uma leitura velha apagaria a sugestão de outra pessoa."""
    return livros.ler(*_banco(), LIVRO, ABA)


def _publicar(linhas: list[dict]) -> None:
    base, sessao = _banco()
    try:
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in linhas])},
                        base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
    finally:
        limpar()


def criar(form: dict, arquivos, usuario, areas: dict) -> dict:
    """Uma sugestão nova. `areas` = {id da torre: nome} que a pessoa vê (a área escolhida tem de estar nela; vazio =
    nenhuma em especial). O `novo_id` do formulário vira o id: o 2º envio do mesmo formulário (o duplo clique, o F5)
    acha a sugestão no livro e não grava outra."""
    quem = _quem(usuario)
    cofre = _cofre()
    titulo = _linha(form.get("titulo"), TITULO_MAX, "Escreva um título", "O título")
    descricao = _texto(form.get("descricao"), TEXTO_MAX, "Escreva a descrição", "A descrição")
    area = _txt(form.get("area"))
    if area and area not in areas:
        raise Recusada("Essa área não está entre as que você vê: escolha outra")
    lista_anexos = anexos(arquivos)
    sid = _txt(form.get("novo_id"))
    sid = sid if ID_RE.fullmatch(sid) else novo_id()
    with _TRAVA:
        lido = _reler()
        ja = next((l for l in lido if _txt(l.get("id")) == sid), None)
        if ja:
            return ja
        agora = datetime.now(timezone.utc)
        linha = {"id": sid, "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z",
                 "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "area": area or None,
                 "pessoa_id": quem["pessoa_id"], "pessoa_hmac": quem["hmac"]}
        feitos = _gravar_anexos(sid, lista_anexos)
        dados = {"titulo": titulo, "descricao": descricao, "quem": {"nome": quem["nome"], "email": quem["email"]},
                 "anexos": feitos}
        linha["dados_cifrados"] = cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(linha))
        try:
            _publicar(lido + [linha])
        except Exception:
            # o banco recusou: os arquivos não ficam órfãos no disco (o 2º envio grava de novo, com o mesmo id)
            if feitos:
                shutil.rmtree(_pasta(sid), ignore_errors=True)
            raise
    return linha


# ── ler ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def ler(forcar: bool = False) -> dict:
    """{"linhas", "erro"}, guardado por 1 minuto. Leitura que falha devolve a última boa com o erro."""
    agora = time.time()
    g = _CACHE.get("livro")
    if g and not forcar and agora - g["lido_em"] < TTL_S:
        return g
    try:
        linhas = livros.ler(*_banco(), LIVRO, ABA)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e segue
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(g, erro=erro) if g else {"linhas": [], "lido_em": None, "erro": erro}
    _CACHE["livro"] = {"linhas": linhas, "lido_em": agora, "erro": ""}
    return _CACHE["livro"]


def _quando(v):
    try:
        return datetime.fromisoformat(_txt(v).replace("Z", "+00:00")).astimezone(_BRT)
    except ValueError:
        return None


def lista(areas_nome: dict | None = None) -> list[dict]:
    """As sugestões, da mais nova para a mais antiga, com o texto decifrado (sem a chave, o texto sai vazio e a tela
    diz)."""
    try:
        cofre = _cofre()
    except Recusada:
        cofre = None
    areas_nome = areas_nome or {}
    out = []
    for l in ler()["linhas"]:
        sid = _txt(l.get("id"))
        if not ID_RE.fullmatch(sid):
            continue
        dados = {}
        if cofre and l.get("dados_cifrados"):
            try:
                dados = json.loads(cofre.decifrar(l["dados_cifrados"], _ctx(l)))
            except Exception:    # noqa: BLE001 — linha mexida no banco ou chave trocada: fica sem o texto
                dados = {}
        quando = _quando(l.get("registrado_em"))
        area = _txt(l.get("area"))
        anexos_ = [dict(a, tamanho_txt=tamanho_txt(int(a.get("tamanho") or 0)), imagem=eh_imagem(_txt(a.get("arquivo"))))
                   for a in dados.get("anexos") or [] if isinstance(a, dict)]
        out.append({"id": sid, "quando": quando, "quando_txt": quando.strftime("%d/%m/%Y às %H:%M") if quando else "—",
                    "area": area, "area_nome": areas_nome.get(area, area), "titulo": _txt(dados.get("titulo")),
                    "descricao": _txt(dados.get("descricao")), "nome": _txt((dados.get("quem") or {}).get("nome")),
                    "email": _txt((dados.get("quem") or {}).get("email")), "anexos": anexos_, "legivel": bool(dados)})
    out.sort(key=lambda x: x["quando"] or datetime.min.replace(tzinfo=_BRT), reverse=True)
    return out
