"""Lê as OS da FAMA e grava `nexus_os_fama` (11/11/2026, fase 1: sombra). O fato e as regras de governança:
`fato_os_fama.py`; a ligação de cada projeto à usina: Base → Ligações entre bases (`nexus/cadastro/ligacao_fama.py`).

A API, medida no servidor em 11/11/2026: base https://api.fama.energy, a chave NEXUS_FAMA_CHAVE no cabeçalho
X-Contractor-Key. É chave de PRESTADORA: só abre as rotas /v2/contractor/ (as outras dão 401). O
`GET /v2/contractor/service-orders/` devolve UMA lista JSON com todas as OS atribuídas à Grid, de uma vez, sem filtro nem
página: 4.749 em 11/11 (de 08/2023 a hoje), em 42 usinas, em ~27 s. O detalhe da OS e o PATCH do status não entram aqui.

A leitura: só GET nessa rota, com timeout de 90 s, UMA vez por hora (a volta da carga de dados, `carga.ligar`, aos :40) e
sem repetir em laço. Erro de rede, resposta que não é 200 (o 401 da chave recusada), que não é JSON ou que não é lista vira
"não li" (`NaoLi`), e nada se grava: a hora seguinte tenta de novo. A chave nunca vai ao log nem à mensagem: o texto que
sai daqui é montado aqui (o tipo do erro, o código HTTP e a frase de erro da FAMA, cortada), e tudo passa por `sem_chave`.

Liga só onde há as três chaves (`CHAVES`: a da FAMA, o token de escrita do banco e a do cadastro, que cifra o texto do
cliente); hoje só o servidor tem as três. Nos testes, nunca sem uma FAMA de mentira; na cópia de prova, nunca (ela não liga
a carga de dados e apaga a NEXUS_FAMA_CHAVE do ambiente).

Não grava (o relatório diz por quê, só com contagens):
- outra máquina gravou há menos de 50 min (regra 11; conferido antes de ler a FAMA e de novo antes de gravar);
- o livro do banco que não vem inteiro (`LeituraCurta`: a aba fora da listagem, menos linhas que o `row_count`): gravar
  por cima perderia as linhas e as cifras;
- o de-para do cadastro lido vazio (a usina não ligaria em nada);
- a trava contra encolher: a lista da FAMA só cresce, então a leitura com menos de 95% das linhas que o banco tem é
  "leitura incompleta". A OS que a FAMA tirar da Grid (até 5%) sai do fato, que é "a OS atribuída à Grid";
- nada mudou (o sha do fato e da dimensão é o da última gravação): o livro não é regravado a cada hora à toa.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from ..cadastro.cifra import CifraErro, Cofre
from . import fato_os_fama as F
from . import livros
from .conexao import base_de as _base
from .fatos import CAB_QUALIDADE

URL = "https://api.fama.energy/v2/contractor/service-orders/"
TIMEOUT_S = 90
INTERVALO_MIN = 50
MINIMO_DO_BANCO = 0.95
DETALHE_MAX = 120
CHAVES = ("NEXUS_FAMA_CHAVE", "GRIDCO_SQL_TOKEN", "NEXUS_CHAVE_CADASTRO")
LIVRO_CADASTRO = "cadastro_nexus"
_BRT = timezone(timedelta(hours=-3))
# o que a volta de hora em hora leva ao log (só contagens e os motivos)
PARA_O_LOG = ("pulou", "nao_li", "nao_grava", "erro", "lidas", "repetidas", "sem_id", "no_banco", "linhas", "projetos",
              "decididas", "ambiguas", "mudou", "gravado", "fora_do_dominio", "datas", "leitura_s", "duracao_s")
log = logging.getLogger("nexus.dados")


class NaoLi(RuntimeError):
    """A FAMA não devolveu a lista (rede, código HTTP, corpo que não é lista): nada se grava."""


class LeituraCurta(RuntimeError):
    """O livro da FAMA no banco não veio inteiro: nada se grava por cima."""


def sem_chave(texto, config) -> str:
    """O texto com a NEXUS_FAMA_CHAVE trocada por [chave] (a defesa de fundo: nenhuma frase daqui a leva)."""
    t = str(texto)
    chave = str((config or {}).get("NEXUS_FAMA_CHAVE") or "").strip()
    return t.replace(chave, "[chave]") if len(chave) >= 4 else t


def para_o_log(rel: dict) -> dict:
    return {k: v for k, v in (rel or {}).items() if k in PARA_O_LOG}


def _detalhe(r) -> str:
    """A frase de erro da FAMA ("Could not validate credentials"), cortada; vazio se a resposta não traz."""
    try:
        corpo = r.json()
    except Exception:       # noqa: BLE001 — sem corpo legível, só o código
        return ""
    d = corpo.get("detail") if isinstance(corpo, dict) else None
    return " ".join(d.split())[:DETALHE_MAX] if isinstance(d, str) else ""


def ler(chave: str, sessao) -> list:
    """A lista das OS atribuídas à Grid: UM GET, com a chave no cabeçalho e o timeout de 90 s. Sobe `NaoLi` com uma frase
    montada aqui (nunca a mensagem do erro, que pode trazer o pedido)."""
    try:
        r = sessao.get(URL, headers={"X-Contractor-Key": chave, "Accept": "application/json"}, timeout=TIMEOUT_S)
    except Exception as e:      # noqa: BLE001 — Timeout, ConnectionError...: "não li"
        raise NaoLi(f"a FAMA não respondeu ({type(e).__name__})") from None
    st = getattr(r, "status_code", None)
    if st != 200:
        d = _detalhe(r)
        recusa = " (a chave foi recusada)" if st in (401, 403) else ""
        raise NaoLi(f"a FAMA respondeu {st}{recusa}" + (f": {d}" if d else "")) from None
    try:
        corpo = r.json()
    except Exception:           # noqa: BLE001
        raise NaoLi("a resposta da FAMA não é JSON") from None
    if not isinstance(corpo, list):
        raise NaoLi(f"a resposta da FAMA não é uma lista ({type(corpo).__name__})")
    return corpo


def ler_banco(base: str, sessao) -> dict:
    """{aba: linhas} do livro da FAMA no banco, CONFERIDO: o livro que não existe (ou criado e nunca gravado) é {}; o que
    existe traz o fato e a dimensão na listagem, a listagem traz as abas que o livro diz ter, e cada aba vem com as linhas
    que a listagem diz (`row_count`). Senão, `LeituraCurta`."""
    r = sessao.get(f"{base}/api/workbooks", timeout=60)
    r.raise_for_status()
    w = next((x for x in r.json() if x.get("key") == F.LIVRO), None)
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    listadas = {x["sheet_name"]: x for x in r.json() if x.get("workbook_key") == F.LIVRO}
    n = livros._int((w or {}).get("sheet_count"))
    if not listadas and (w is None or n == 0):
        return {}
    if (n is not None and len(listadas) < n) or F.ABA not in listadas or F.ABA_DIM not in listadas:
        raise LeituraCurta(f"{F.LIVRO}: a listagem do banco não trouxe o livro inteiro (o livro diz {n} abas e vieram "
                           f"{len(listadas)}); não gravo por cima")
    out = {}
    for aba in (F.ABA, F.ABA_DIM, "atualizacao"):
        meta = listadas.get(aba)
        if meta is None:
            out[aba] = []
            continue
        linhas = livros._linhas(base, sessao, meta["id"])
        esperado = livros._int(meta.get("row_count"))
        if esperado is None or len(linhas) != esperado:
            raise LeituraCurta(f"{F.LIVRO}.{aba}: li {len(linhas)} linhas e o banco diz {esperado}; não gravo por cima")
        out[aba] = linhas
    return out


def _gravou_ha_pouco(atualizacao: list, agora: datetime) -> str | None:
    for l in atualizacao or ():
        try:
            u = datetime.fromisoformat(str(l.get("gerado_em")))
        except (TypeError, ValueError):
            return None
        u = u if u.tzinfo else u.replace(tzinfo=_BRT)
        if agora - u < timedelta(minutes=INTERVALO_MIN):
            return f"a última gravação é de {u.astimezone(_BRT).isoformat(timespec='minutes')} (outra máquina ou a mesma)"
        return None
    return None


def _maquina() -> str:
    return "servidor" if os.name != "nt" else "pc"


def gerar_fama(config, sessao=None, *, fama=None, agora=None, gravar=True, forcar=False) -> dict:
    """Uma volta: confere o banco, lê a FAMA uma vez, monta o fato e a dimensão e grava o livro inteiro, conferido
    (`livros.publicar`). Devolve o relatório, só com contagens e motivos. `fama` = a sessão da FAMA (a de mentira nos
    testes); `forcar` pula o portão dos 50 min e o "nada mudou" (nunca a trava contra encolher)."""
    faltam = [k for k in CHAVES if not str(config.get(k) or "").strip()]
    if faltam:
        return {"pulou": f"a leitura da FAMA só liga com as três chaves ({', '.join(CHAVES)}); falta {', '.join(faltam)}"}
    if config.get("TESTING") and fama is None:
        return {"pulou": "teste e cópia de prova nunca leem a FAMA de verdade"}
    import requests
    s = sessao or requests.Session()
    base = _base(config)
    agora = agora or datetime.now(_BRT)
    t0 = time.time()
    try:
        cofre = Cofre(config["NEXUS_CHAVE_CADASTRO"])
    except CifraErro:
        return {"nao_grava": "a NEXUS_CHAVE_CADASTRO não abre o Cofre: sem cifrar o título e a descrição, nada se grava"}
    # o banco ANTES da FAMA (a leitura dela leva ~27 s): a FAMA só é lida quando o resto da volta pode terminar
    try:
        banco = ler_banco(base, s)
    except LeituraCurta as e:
        return {"nao_grava": str(e)}
    if not forcar and (p := _gravou_ha_pouco(banco.get("atualizacao"), agora)):
        return {"pulou": p}
    de_para = livros.ler(base, s, LIVRO_CADASTRO, "de_para")
    if not de_para:
        return {"nao_grava": "o de-para do cadastro veio vazio: nenhuma OS ligaria à usina; nada se grava"}
    lig, rel_lig = F.ligacao_decidida(de_para)
    t_fama = time.time()
    try:
        itens = ler(str(config["NEXUS_FAMA_CHAVE"]).strip(), fama if fama is not None else requests.Session())
    except NaoLi as e:
        return {"nao_li": sem_chave(e, config), "leitura_s": round(time.time() - t_fama, 1)}
    lido_em = datetime.now(_BRT).isoformat(timespec="seconds")
    por_os, rel = F.validas(itens)
    no_banco = len(banco.get(F.ABA) or [])
    rel.update(no_banco=no_banco, leitura_s=round(time.time() - t_fama, 1), **rel_lig)
    if not por_os and not no_banco:
        return dict(rel, pulou="a FAMA devolveu a lista vazia e o banco não tem nada: nada a guardar")
    if no_banco and len(por_os) < MINIMO_DO_BANCO * no_banco:
        return dict(rel, nao_grava=f"leitura incompleta: a FAMA trouxe {len(por_os)} OS e o banco tem {no_banco} (menos "
                                   f"de {MINIMO_DO_BANCO:.0%}); a lista da FAMA só cresce, o livro fica como está")
    anteriores = {F.id_fama(d.get("fama_os_id")): d for d in banco.get(F.ABA) or ()}
    linhas, rf = F.linhas(por_os, lig, cofre, anteriores)
    F.conferir_grao(linhas)
    dim = F.dim_projetos(por_os, banco.get(F.ABA_DIM) or [])
    impressao = F.sha(linhas, dim)
    rel.update(rf, linhas=len(linhas), projetos=len(dim), sha_linhas=impressao)
    ant = dict((banco.get("atualizacao") or [{}])[0])
    if not forcar and str(ant.get("sha_linhas") or "") == impressao:
        return dict(rel, mudou=False, pulou="nada mudou na FAMA nem nas ligações desde a última gravação")
    iso = agora.isoformat(timespec="seconds")
    q = F.linha_qualidade(linhas, dim, rel, lido_em, iso, no_banco or None)
    tab = {F.ABA: (F.CAB_OS_FAMA, linhas), F.ABA_DIM: (F.CAB_DIM, dim), "qualidade": (CAB_QUALIDADE, [q]),
           "atualizacao": (F.CAB_ATUALIZACAO, [[iso, _maquina(), round(time.time() - t0, 1), len(linhas), F.COMO_LER,
                                                impressao, lido_em]])}
    if not gravar:
        return dict(rel, mudou=True, ensaio="montado com o dado real; nada gravado")
    # outra máquina gravou enquanto esta lia a FAMA
    if not forcar and (p := _gravou_ha_pouco(livros.ler(base, s, F.LIVRO, "atualizacao"), agora)):
        return dict(rel, pulou=p)
    rel["gravado"] = livros.publicar(F.LIVRO, F.NOME_LIVRO, tab, base=base, token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    rel["duracao_s"] = round(time.time() - t0, 1)
    return dict(rel, mudou=True)
