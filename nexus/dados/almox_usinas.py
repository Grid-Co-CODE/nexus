"""O almoxarifado de cada usina, marcado pelo PCM no Nexus (12/11/2026): "sem almoxarifado", "compartilha" (usa o da usina X)
ou "próprio".

O PCM: "Algumas usinas não tem almoxarifado ou compartilham os almoxarifados [...] poderia ter uma aba desse tipo no Nexus
pra gente ter essa noção". O Levi, 12/11/2026: "Passa para o cadastro do nexus". Até aqui morava na App Setting
`ALMOX_COMPARTILHADOS` do App de Campo ("<usina> > <usina dona>; ..."), que só o Levi editava. O App (v343) lê este livro e
o põe por cima da App Setting; a usina fora do livro segue o que o Fracttal e a App Setting dizem.

O livro `nexus_almoxarifado_usinas` (registrado em `nexus/dados/catalogo.py` antes da 1ª gravação; as regras da tela em
`nexus/pcm/almox_usinas.py`):
- `dim_almoxarifado_usina`: o CONTRATO com o App, nas colunas e na ordem de `CAB`. 1 linha = 1 usina MARCADA (desmarcar tira
  a linha). `usina` é o nome do local da usina no Fracttal ("Cliente - Usina - UF", o mesmo do de-para que o
  `usina_ligada_por` do inventário usa: o App casa por ele, sem a UF); a dona só em "compartilha"; `pessoa_hmac` é quem
  marcou (o `codigo_da_pessoa`; vazio para quem entrou pela senha de administrador, como no inventário).
- `fato_decisao_almox_usina`: o histórico, como o das decisões de setor (`nexus_setores`): 1 linha = 1 marcação ou
  desmarcação, só acrescenta (`so_cresce`). Diz também por onde o "mesmo cliente" foi conferido (`cliente_por`).
Em claro só IDs, os nomes de local do Fracttal (o de-para do cadastro já os tem), as listas fechadas e o código da pessoa:
nada de nome nem e-mail (a API é aberta). Gravar relê o livro inteiro antes (a troca é integral; a leitura que falha, que
volta com menos linhas do que a listagem diz ou sem uma aba do livro que existe não grava), troca as duas abas juntas e
confere a contagem (`livros.publicar`). Uma gravação por vez neste processo.

`NEXUS_ALMOX_USINAS_ARQUIVO` troca o banco por um arquivo (a cópia de prova e os testes); teste sem ele nunca vai à rede
(lê vazio e não grava).
"""
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import livros
from .conexao import banco_de as _banco
from .dominios import SITUACAO_ALMOX_USINA

LIVRO, NOME_LIVRO = "nexus_almoxarifado_usinas", "Nexus · almoxarifado de cada usina (PCM)"
ABA, ABA_DECISAO = "dim_almoxarifado_usina", "fato_decisao_almox_usina"
ABAS = (ABA, ABA_DECISAO)
# o contrato com o App (v343, fechado em 12/11/2026): estas colunas, nesta ordem. Coluna nova só no FIM
CAB = ("usina_id", "usina", "situacao", "usina_dona_id", "usina_dona", "atualizado_em", "pessoa_hmac")
CAB_DECISAO = ("decidida_em", "data_id", "usina_id", "situacao", "usina_dona_id", "cliente_por", "pessoa_hmac")
CABS = {ABA: CAB, ABA_DECISAO: CAB_DECISAO}
SITUACOES = SITUACAO_ALMOX_USINA
COMPARTILHA = "compartilha"
DESMARCADA = "desmarcada"                    # só na decisão: a linha da dimensão saiu
# por onde o "mesmo cliente" da dona foi conferido: o cliente do cadastro das duas usinas, ou o 1º nó do local no Fracttal
CLIENTE_POR = ("cadastro do Nexus", "local do Fracttal")
NOME_MAX = 120
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_RE_HMAC = re.compile(r"[0-9a-f]{24}")
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


class LeituraIncompleta(RuntimeError):
    """A leitura de uma aba voltou com menos linhas do que a listagem do banco diz que ela tem."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _txt(v) -> str:
    return "" if v is None else " ".join(str(v).split())


def _int(v) -> int | None:
    try:
        n = float(_txt(v).replace(",", "."))
    except ValueError:
        return None
    return int(n) if n.is_integer() and n > 0 else None


# ── o livro: o banco, ou um arquivo na cópia de prova ─────────────────────────────────────────────────────────
def _arquivo_local(cfg) -> Path | None:
    p = cfg.get("NEXUS_ALMOX_USINAS_ARQUIVO")
    return Path(p) if p else None


def _ler_cru(cfg) -> dict:
    """{aba: [linhas]} das duas abas, lidas agora. Livro que ainda não existe = vazio; erro de leitura sobe, e também a
    listagem que não traz uma aba do livro que existe (`livros.abas_conferidas`) e a aba que volta com menos linhas do que o
    `row_count` da listagem diz (a página curta: sem isto, a gravação seguinte desmarcaria as usinas que não vieram)."""
    loc = _arquivo_local(cfg)
    if loc is not None:
        try:
            d = json.loads(loc.read_text(encoding="utf-8"))
        except FileNotFoundError:
            d = {}
        return {a: [dict(x) for x in d.get(a) or []] for a in ABAS}
    if cfg.get("TESTING"):
        return {a: [] for a in ABAS}
    base, sessao = _banco(cfg)
    ids = livros.abas_conferidas(base, sessao, LIVRO, ABAS)
    if not ids:
        return {a: [] for a in ABAS}
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    contagem = {x["sheet_name"]: livros._int(x.get("row_count")) for x in r.json() if x.get("workbook_key") == LIVRO}
    out = {}
    for a in ABAS:
        lidas = list(livros._linhas(base, sessao, ids[a])) if a in ids else []
        esperadas = contagem.get(a)
        if esperadas is not None and len(lidas) < esperadas:
            raise LeituraIncompleta(f"{a}: li {len(lidas)} linhas e o banco diz {esperadas}")
        out[a] = lidas
    return out


def _conferir_destino(cfg) -> None:
    if _arquivo_local(cfg) is not None:
        return
    if cfg.get("TESTING"):
        raise Recusada("Este Nexus está em teste e sem o arquivo do livro (NEXUS_ALMOX_USINAS_ARQUIVO): nada foi gravado.")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")


def _gravar_cru(cfg, cru: dict) -> None:
    """Troca o livro inteiro (as duas abas juntas) e confere a contagem (`livros.publicar`). Na cópia de prova, o arquivo."""
    corpo = {a: [[None if x.get(c) in ("", None) else x.get(c) for c in CABS[a]] for x in cru[a]] for a in ABAS}
    loc = _arquivo_local(cfg)
    if loc is not None:
        loc.parent.mkdir(parents=True, exist_ok=True)
        tmp = loc.with_suffix(".tmp")
        tmp.write_text(json.dumps({a: [dict(zip(CABS[a], l)) for l in corpo[a]] for a in ABAS}, ensure_ascii=False,
                                  indent=1), encoding="utf-8")
        tmp.replace(loc)
        return
    base, sessao = _banco(cfg)
    try:
        livros.publicar(LIVRO, NOME_LIVRO, {a: (list(CABS[a]), corpo[a]) for a in ABAS}, base=base,
                        token=cfg["GRIDCO_SQL_TOKEN"], sessao=sessao)
    except livros.GravacaoRecusada as ex:
        raise Recusada("O banco devolveu o livro incompleto ou menor do que já tinha: nada foi gravado, para não apagar o "
                       "histórico. Tente de novo em instantes.") from ex


def _vigentes(dim: list[dict]) -> dict:
    """{usina_id: linha} da dimensão (a última de cada usina, se o livro tiver duas)."""
    out = {}
    for l in dim:
        uid = _int(l.get("usina_id"))
        if uid:
            out[uid] = dict(l, usina_id=uid, usina_dona_id=_int(l.get("usina_dona_id")))
    return out


def ler(cfg, forcar: bool = False) -> dict:
    """{"marcadas": {usina_id: linha}, "decisoes": [...], "erro", "lido_em"}, guardado por 1 minuto. A leitura que falha devolve
    a última boa com `velha` e o erro; sem nenhuma, nada marcado com o erro (a tela não deixa gravar sem saber o que há)."""
    chave = str(_arquivo_local(cfg) or "banco")
    g = _CACHE.get(chave)
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        cru = _ler_cru(cfg)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede, leitura curta: a tela diz e não deixa gravar
        erro = f"Não consegui ler o livro das usinas no banco ({type(ex).__name__}): tente de novo em instantes."
        if g:
            return dict(g, erro=erro, velha=True)
        return {"marcadas": {}, "decisoes": [], "erro": erro, "lido_em": None}
    g = {"marcadas": _vigentes(cru[ABA]), "decisoes": cru[ABA_DECISAO], "erro": "", "lido_em": time.time()}
    _CACHE[chave] = g
    return g


def limpar() -> None:
    _CACHE.clear()


# ── a linha que entra ─────────────────────────────────────────────────────────────────────────────────────────
def _nome(v, campo: str) -> str:
    t = _txt(v)
    if not t or len(t) > NOME_MAX or "@" in t:
        raise ValueError(f"{campo} é o nome do local no Fracttal (até {NOME_MAX} caracteres, sem e-mail): {t[:30]!r}")
    return t


def _hmac(v) -> str | None:
    t = _txt(v)
    if t and not _RE_HMAC.fullmatch(t):
        raise ValueError("pessoa_hmac é o código da pessoa (24 hexadecimais), nunca o nome nem o e-mail")
    return t or None


def linha(usina_id, usina, situacao, dona_id=None, dona="", pessoa_hmac="", agora: datetime | None = None) -> dict:
    """A linha da dimensão, conferida pela forma de cada coluna (`ValueError`, erro de quem chama): a dona só em
    "compartilha", e sempre nela."""
    uid = _int(usina_id)
    if not uid:
        raise ValueError(f"usina_id é o ID da usina no cadastro: {usina_id!r}")
    if situacao not in SITUACOES:
        raise ValueError(f"situacao fora da lista ({', '.join(SITUACOES)}): {_txt(situacao)[:30]!r}")
    did = _int(dona_id)
    if situacao == COMPARTILHA:
        if not did:
            raise ValueError("compartilha pede a usina dona (o ID)")
        dona = _nome(dona, "usina_dona")
    elif did or _txt(dona):
        raise ValueError("a usina dona só vai em compartilha")
    return {"usina_id": uid, "usina": _nome(usina, "usina"), "situacao": situacao,
            "usina_dona_id": did if situacao == COMPARTILHA else None, "usina_dona": dona if situacao == COMPARTILHA else None,
            "atualizado_em": _iso(agora or _agora()), "pessoa_hmac": _hmac(pessoa_hmac)}


def decisao(usina_id, situacao, dona_id=None, cliente_por="", pessoa_hmac="", agora: datetime | None = None) -> dict:
    """A linha do histórico: a marcação (uma das `SITUACOES`) ou a desmarcação (`DESMARCADA`)."""
    agora = agora or _agora()
    if situacao not in SITUACOES + (DESMARCADA,):
        raise ValueError(f"situacao da decisão fora da lista: {_txt(situacao)[:30]!r}")
    if cliente_por and cliente_por not in CLIENTE_POR:
        raise ValueError(f"cliente_por fora da lista ({', '.join(CLIENTE_POR)}): {_txt(cliente_por)[:30]!r}")
    return {"decidida_em": _iso(agora), "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "usina_id": _int(usina_id),
            "situacao": situacao, "usina_dona_id": _int(dona_id), "cliente_por": cliente_por or None,
            "pessoa_hmac": _hmac(pessoa_hmac)}


def trocar(cfg, mudar) -> dict:
    """Uma marcação: relê o livro AGORA (sob a trava: a troca é integral), chama `mudar(marcadas)` com as linhas vigentes
    ({usina_id: linha}), que devolve (a nova linha da usina, ou None para desmarcar; a usina; a decisão) ou levanta `Recusada`
    com o porquê (as regras da tela), e grava as duas abas. Devolve as marcadas de agora. `Recusada` também quando o banco não
    deixa reler ou gravar: nada foi gravado."""
    _conferir_destino(cfg)
    with _TRAVA:
        try:
            cru = _ler_cru(cfg)
        except Exception as ex:      # noqa: BLE001
            raise Recusada(f"Não consegui ler o livro das usinas no banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.") from ex
        marcadas = _vigentes(cru[ABA])
        nova, uid, dec = mudar(dict(marcadas))
        if nova is None:
            marcadas.pop(uid, None)
        else:
            marcadas[uid] = nova
        cru = {ABA: sorted(marcadas.values(), key=lambda l: l["usina_id"]), ABA_DECISAO: cru[ABA_DECISAO] + [dec]}
        _gravar_cru(cfg, cru)
        g = {"marcadas": _vigentes(cru[ABA]), "decisoes": cru[ABA_DECISAO], "erro": "", "lido_em": time.time()}
        _CACHE[str(_arquivo_local(cfg) or "banco")] = g
        return g["marcadas"]
