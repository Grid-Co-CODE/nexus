"""Os relatos de segurança do App de Campo na tela Incidentes da Segurança · HSEQ (24/11/2026).

Levi, no chat do App de Campo (23/11/2026): "a pessoa vai lá no início, consegue relatar [...] entrará na parte de
segurança do Nexus". O App ganhou na v376 o botão vermelho com a sirene (e, na v377, o "Relatar segurança" no Perfil): o
técnico relata acidente, incidente, incêndio, condição insegura ou EPI e EPC, com a usina, o que aconteceu, as pessoas
envolvidas (só por função e quantidade, sem nome), até 3 fotos e a ação imediata. Acidente e incêndio avisam a TST por
e-mail na hora, pelo próprio App.

O caminho é o das Sugestões (`nexus/casca/relatos_app.py`): o App é a FONTE do relato; o Nexus NÃO guarda o relato no
banco, porque o texto livre pode citar nomes e a API do banco tem leitura aberta (regra 8 de `nexus/dados/CLAUDE.md`). O
Nexus lê a lista no servidor do App, de servidor para servidor, com a MESMA chave das Sugestões (`NEXUS_APP_RELATOS_CHAVE`
aqui, `NEXUS_RELATOS_CHAVE` no App), e as fotos passam pelo Nexus (o navegador não vê a chave nem o endereço do App).

O contrato (versão 1, do App de Campo, 23/11/2026; o texto inteiro mora com o App; mudou lá, muda aqui no mesmo trabalho):
- `GET <base>/app/nexus/seguranca/relatos` com `X-Nexus-Chave` → `{"versao": 1, "relatos": [...]}`, do mais novo para o
  mais antigo, no máximo 500. Cada relato: `id`, `tipo` (acidente|incidente|incendio|condicao_insegura|epi_epc),
  `tipo_rotulo`, `quando` (o momento do fato, ISO com fuso), `usina` (o nome do local no Fracttal), `o_que_aconteceu`,
  `acao_imediata`, `pessoas` [{`funcao` (tecnico|eletricista|mantenedor|terceiro), `quantidade`}], `fotos` (0 a 3),
  `criado_em`, `autor` {`nome`, `email`, `papel`}, `versao_app`, `aviso_tst` {`situacao` (enviado|pendente|nao_avisa),
  `enviado_em`}.
- `GET <base>/app/nexus/seguranca/relatos/<id>/foto/<n>` → a foto `n` (0, 1 ou 2), `image/jpeg` ou `image/png`; 404 se
  não existe. O nome do arquivo no servidor do App leva o e-mail de quem tirou a foto e nunca sai de lá.
- `<base>` é o endereço das Sugestões (`relatos_app._url`, padrão `https://gridco-campo-mw.azurewebsites.net/api/app/
  nexus/relatos`) com `/seguranca/relatos` no lugar do `/relatos` do fim: uma configuração só para as duas rotas.

O e-mail do autor não sai daqui: a tela mostra o nome e o papel. Nada daqui grava no banco nem no disco: a lista fica
numa cópia de 1 minuto, na memória; as fotos não ficam guardadas."""
from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from ..casca import relatos_app as R

VERSAO_DO_CONTRATO = 1
TTL_S = 60
TIMEOUT_FOTO_S = 10
MAX_FOTOS = 3
FOTO_MAX_BYTES = 8 * 1024 * 1024
TIPOS_DE_IMAGEM = ("image/jpeg", "image/png")
# o código do App -> (o rótulo, o tom da casa). Acidente e incêndio são os que avisam a TST na hora, pelo App
TIPOS = {"acidente": ("Acidente", "critico"), "incendio": ("Incêndio", "critico"),
         "incidente": ("Incidente", "alerta"), "condicao_insegura": ("Condição insegura", "alerta"),
         "epi_epc": ("EPI e EPC", "info")}
FUNCOES = {"tecnico": ("técnico", "técnicos"), "eletricista": ("eletricista", "eletricistas"),
           "mantenedor": ("mantenedor", "mantenedores"), "terceiro": ("terceiro", "terceiros")}
AVISOS = {"enviado": ("Enviado", "ok"), "pendente": ("Pendente", "alerta"), "nao_avisa": ("Não avisa", "neutro")}
_CACHE: dict = {}


def limpar() -> None:
    _CACHE.clear()


def ligado() -> bool:
    return R.ligado()


def url_base() -> str:
    base = R._url()
    if base.endswith("/relatos"):
        base = base[: -len("/relatos")]
    return base + "/seguranca/relatos"


def _pedido(caminho: str = "", aceita: str = "application/json") -> urllib.request.Request:
    cab = {"X-Nexus-Chave": R._conf(R.NOME_CHAVE), "User-Agent": "Nexus-GridCo/1 (seguranca)", "Accept": aceita}
    return urllib.request.Request(url_base() + caminho, headers=cab, method="GET")


def _pessoas(lista) -> tuple[list, int]:
    """[(quantidade, "técnicos")], total. Função fora do contrato entra com o código que veio."""
    out, total = [], 0
    for p in lista if isinstance(lista, list) else []:
        if not isinstance(p, dict):
            continue
        try:
            n = int(p.get("quantidade") or 0)
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        cod = R._txt(p.get("funcao")).lower()
        um, varios = FUNCOES.get(cod) or (cod or "pessoa", (cod + "s") if cod else "pessoas")
        out.append({"funcao": cod, "quantidade": n, "texto": f"{n} {um if n == 1 else varios}"})
        total += n
    return out, total


def normalizar(r) -> dict | None:
    """O relato do App no formato da tela; None se faltar o essencial (o id, o tipo ou o que aconteceu) ou se o id não for
    um id (ele vai ao endereço da foto e ao HTML)."""
    if not isinstance(r, dict):
        return None
    rid, texto = R._txt(r.get("id")), R._txt(r.get("o_que_aconteceu"))
    tipo = R._txt(r.get("tipo")).lower()
    if not R.ID_RE.fullmatch(rid) or not tipo or not texto:
        return None
    rotulo, tom = TIPOS.get(tipo) or (R._txt(r.get("tipo_rotulo")) or tipo.replace("_", " ").capitalize(), "neutro")
    autor = r.get("autor") if isinstance(r.get("autor"), dict) else {}
    aviso = r.get("aviso_tst") if isinstance(r.get("aviso_tst"), dict) else {}
    situacao = R._txt(aviso.get("situacao")).lower()
    aviso_rotulo, aviso_tom = AVISOS.get(situacao) or ((situacao.capitalize(), "neutro") if situacao else ("—", "neutro"))
    try:
        fotos = max(0, min(MAX_FOTOS, int(r.get("fotos") or 0)))
    except (TypeError, ValueError):
        fotos = 0
    pessoas, total = _pessoas(r.get("pessoas"))
    quando, criado = R._quando(r.get("quando")), R._quando(r.get("criado_em"))
    enviado = R._quando(aviso.get("enviado_em"))
    return {"id": rid, "tipo": tipo, "tipo_rotulo": rotulo, "tom": tom,
            "quando": quando or criado, "criado": criado,
            "usina_fonte": R._txt(r.get("usina")), "o_que_aconteceu": texto,
            "acao_imediata": R._txt(r.get("acao_imediata")), "pessoas": pessoas, "pessoas_total": total,
            "fotos": fotos, "autor": R._txt(autor.get("nome")), "papel": R._txt(autor.get("papel")),
            "versao_app": R._txt(r.get("versao_app")), "aviso": situacao, "aviso_rotulo": aviso_rotulo,
            "aviso_tom": aviso_tom, "aviso_em": enviado}


def _validar(d) -> list:
    if not isinstance(d, dict):
        raise R.FonteErro("a resposta do App não é um objeto")
    if d.get("versao") != VERSAO_DO_CONTRATO:
        raise R.FonteErro(f"o App fala a versão {d.get('versao')!r} do contrato, e o Nexus entende a {VERSAO_DO_CONTRATO}")
    if not isinstance(d.get("relatos"), list):
        raise R.FonteErro("a resposta do App não tem a lista de relatos")
    return d["relatos"]


def ler(forcar: bool = False) -> dict:
    """{"relatos", "erro", "lido_em", "ligado"}, da cópia de 1 minuto. Sem a chave, nem chama o App. Leitura que falha
    devolve a última lista boa com o erro."""
    if not ligado():
        return {"relatos": [], "erro": "", "lido_em": None, "ligado": False}
    agora = time.time()
    g = _CACHE.get("lista")
    if g and not forcar and g.get("lido_em") and agora - g["lido_em"] < TTL_S:
        return g
    try:
        brutos = _validar(R._chamar(_pedido()))
    except R.FonteErro as ex:
        base = g or {"relatos": [], "lido_em": None, "ligado": True}
        _CACHE["lista"] = dict(base, erro=str(ex), lido_em=agora if g else None)
        return _CACHE["lista"]
    relatos = [n for n in (normalizar(r) for r in brutos) if n]
    relatos.sort(key=lambda x: x["quando"] or datetime.min.replace(tzinfo=R._BRT), reverse=True)
    _CACHE["lista"] = {"relatos": relatos, "erro": "", "lido_em": agora, "ligado": True}
    return _CACHE["lista"]


def foto(rid, n) -> tuple[bytes, str] | None:
    """(os bytes, o tipo) da foto `n` do relato, lida no App na hora; None se o relato, a foto ou o tipo não servem.
    FonteErro quando o App recusa ou não responde."""
    rid = R._txt(rid)
    if not ligado() or not R.ID_RE.fullmatch(rid) or not isinstance(n, int) or not 0 <= n < MAX_FOTOS:
        return None
    req = _pedido(f"/{urllib.parse.quote(rid, safe='')}/foto/{n}", aceita="image/jpeg, image/png")
    try:
        with R._abrir(req, timeout=TIMEOUT_FOTO_S) as resp:
            tipo = str(resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            dados = resp.read(FOTO_MAX_BYTES + 1)
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            return None
        if ex.code == 401:
            raise R.FonteErro("o App recusou a chave do Nexus") from None
        raise R.FonteErro(f"o App respondeu {ex.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        raise R.FonteErro(f"o App não respondeu ({type(ex).__name__})") from None
    if tipo not in TIPOS_DE_IMAGEM or not dados or len(dados) > FOTO_MAX_BYTES:
        return None
    return dados, tipo
