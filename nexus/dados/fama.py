"""Lê as OS da FAMA e grava `nexus_os_fama` (11/11/2026, fase 1: sombra). O fato e as regras de governança:
`fato_os_fama.py`; a ligação de cada projeto à usina: Base → Ligações entre bases (`nexus/cadastro/ligacao_fama.py`).

A API, medida no servidor em 11/11/2026: base https://api.fama.energy, a chave NEXUS_FAMA_CHAVE no cabeçalho
X-Contractor-Key. É chave de PRESTADORA: só abre as rotas /v2/contractor/ (as outras dão 401). O
`GET /v2/contractor/service-orders/` devolve UMA lista JSON com todas as OS atribuídas à Grid, de uma vez, sem filtro nem
página: 4.749 em 11/11 (de 08/2023 a hoje), em 42 usinas, em ~27 s. O detalhe da OS e o PATCH do status não entram aqui.

A leitura: só GET nessa rota, UMA vez por hora (a volta da carga de dados, `carga.ligar`, aos :40) e sem repetir em laço.
O prazo de 90 s é da resposta INTEIRA (relógio monotônico), e não por leitura do socket, que é o que o `timeout` do
requests mede: a resposta lida em blocos (`stream=True`, `raw.read1`, que devolve o que chegou) confere o prazo e o teto
de tamanho (50 MB) a cada bloco, e um vigia corta a conexão no prazo (`raw.shutdown`) se a leitura ficar parada no socket.
Caso que criou a regra (revisão de 11/11/2026): a resposta que pinga devagar, sem nunca ficar 90 s parada, seguraria a
volta da carga sem limite. O redirecionamento NÃO é seguido (`allow_redirects=False`): o 3xx é "não li", e o
X-Contractor-Key nunca vai a outro endereço nem a `http://`. Erro de rede, resposta que não é 200 (o 401 da chave
recusada), que passa do prazo ou do teto, que não é JSON ou que não é lista vira "não li" (`NaoLi`), e nada se grava: a
hora seguinte tenta de novo. A chave nunca vai ao log nem à mensagem: o texto que sai daqui é montado aqui (o tipo do erro,
o código HTTP e a frase de erro da FAMA, cortada), e tudo passa por `sem_chave`. A sessão que o leitor abre, ele fecha.

Liga só onde há as três chaves (`CHAVES`: a da FAMA, o token de escrita do banco e a do cadastro, que cifra o texto do
cliente) E só no servidor (`_maquina`, o critério do Nexus: o servidor é o Linux), para o PC com a chave no .env nunca dar
o segundo GET da hora. O teste (TESTING) nunca lê sem uma FAMA de mentira. A cópia de prova não chega aqui: o
`ferramentas/subir_copia_de_prova.py` (`preparar_ambiente`) desliga a carga de dados (NEXUS_CARGA_DADOS=0) e apaga a
NEXUS_FAMA_CHAVE do ambiente.

Não grava (o relatório diz por quê, só com contagens):
- outra máquina gravou há menos de 50 min (regra 11; conferido antes de ler a FAMA e de novo antes de gravar);
- o livro do banco que não vem inteiro (`LeituraCurta`: a aba fora da listagem, menos linhas que o `row_count`): gravar
  por cima perderia as linhas e as cifras;
- o de-para do cadastro lido vazio (a usina não ligaria em nada);
- a trava contra encolher: a lista da FAMA só cresce, então a leitura com menos de 95% das linhas que o banco tem é
  "leitura incompleta". A OS que a FAMA tirar da Grid (até 5%) sai do fato, que é "a OS atribuída à Grid";
- nada mudou (o sha do fato e da dimensão é o da última gravação) e o batimento de hoje já foi gravado: o livro não é
  regravado a cada hora à toa, mas uma vez por dia sim, com a `atualizacao` dizendo "li, nada mudou" (o batimento: sem
  ele, "sem novidade" e "a leitura quebrada há dias" eram o mesmo `gerado_em` velho).
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from ..cadastro.cifra import CifraErro, Cofre
from . import fato_os_fama as F
from . import livros
from .conexao import base_de as _base
from .fatos import CAB_QUALIDADE

URL = "https://api.fama.energy/v2/contractor/service-orders/"
PRAZO_S = 90                    # a resposta inteira, e também a espera máxima de uma leitura do socket
CONEXAO_S = 15                  # abrir a conexão
TETO_BYTES = 50 * 2 ** 20       # 4.749 OS em 11/11/2026 são poucos MB: 50 MB é folga, não porta aberta
BLOCO = 64 * 1024
DETALHE_BYTES = 4096            # do corpo de uma resposta de erro, só o começo (a frase da FAMA)
RELOGIO = time.monotonic        # o relógio do prazo (o teste põe um de mentira)
_Timer = threading.Timer        # o vigia do prazo (o teste põe um de mentira)
INTERVALO_MIN = 50
MINIMO_DO_BANCO = 0.95
DETALHE_MAX = 120
CHAVES = ("NEXUS_FAMA_CHAVE", "GRIDCO_SQL_TOKEN", "NEXUS_CHAVE_CADASTRO")
LIVRO_CADASTRO = "cadastro_nexus"
_BRT = timezone(timedelta(hours=-3))
# o que a volta de hora em hora leva ao log (só contagens e os motivos)
PARA_O_LOG = ("pulou", "nao_li", "nao_grava", "erro", "lidas", "repetidas", "sem_id", "no_banco", "linhas", "projetos",
              "decididas", "ambiguas", "mudou", "situacao", "gravado", "fora_do_dominio", "datas", "leitura_s",
              "duracao_s")
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


def _detalhe(corpo: bytes) -> str:
    """A frase de erro da FAMA ("Could not validate credentials"), cortada; vazio se o começo do corpo não a traz."""
    try:
        dado = json.loads(corpo)
    except ValueError:
        return ""
    d = dado.get("detail") if isinstance(dado, dict) else None
    return " ".join(d.split())[:DETALHE_MAX] if isinstance(d, str) else ""


class _Vigia:
    """Corta a resposta no prazo (`raw.shutdown`, o urllib3 2.3+): a leitura parada no socket não volta ao laço que confere
    o prazo, e só o corte a solta. `disparou` diz que o corpo que chegou até ali está pela metade."""

    def __init__(self, r, segundos: float):
        self.r, self.disparou = r, False
        self.t = _Timer(segundos, self._cortar)
        self.t.daemon = True
        self.t.start()

    def _cortar(self):
        self.disparou = True
        try:
            self.r.raw.shutdown()
        except Exception:       # noqa: BLE001 — sem o shutdown (urllib3 velho), o prazo vale a cada bloco
            pass

    def cancelar(self):
        self.t.cancel()


def _corpo(r, inicio: float, relogio, vigia: _Vigia, teto: int, *, cortar: bool = False) -> bytes:
    """O corpo da resposta em blocos (`raw.read1`: o que chegou, sem esperar o bloco encher), com o prazo da resposta
    inteira conferido a cada bloco e o teto de tamanho. `cortar`: o corpo de erro, só o começo (não é "não li")."""
    partes, total = [], 0
    ler1 = getattr(r.raw, "read1", None) or r.raw.read

    def no_prazo():
        if vigia.disparou or relogio() - inicio > PRAZO_S:
            raise NaoLi(f"a FAMA passou de {PRAZO_S} s para mandar a resposta inteira")
    while True:
        no_prazo()
        try:
            bloco = ler1(BLOCO, decode_content=True)
        except Exception as e:      # noqa: BLE001 — a conexão caiu (ou o vigia a cortou) no meio do corpo
            no_prazo()
            raise NaoLi(f"a leitura da FAMA caiu no meio ({type(e).__name__})") from None
        if not bloco:
            break
        total += len(bloco)
        if total > teto:
            if cortar:
                partes.append(bloco[:teto - (total - len(bloco))])
                break
            raise NaoLi(f"a resposta da FAMA passou do teto de {teto:,} bytes".replace(",", "."))
        partes.append(bloco)
    no_prazo()                      # o vigia que cortou a conexão faz o corpo acabar "normal": não é a lista inteira
    return b"".join(partes)


def ler(chave: str, sessao, *, relogio=None) -> list:
    """A lista das OS atribuídas à Grid: UM GET em blocos, com a chave no cabeçalho, sem seguir redirecionamento, com o
    prazo de `PRAZO_S` para a resposta inteira e o teto `TETO_BYTES`. Sobe `NaoLi` com uma frase montada aqui (nunca a
    mensagem do erro, que pode trazer o pedido). A resposta sempre se fecha."""
    relogio = relogio or RELOGIO
    inicio = relogio()
    try:
        r = sessao.get(URL, headers={"X-Contractor-Key": chave, "Accept": "application/json"},
                       timeout=(CONEXAO_S, PRAZO_S), stream=True, allow_redirects=False)
    except Exception as e:      # noqa: BLE001 — Timeout, ConnectionError...: "não li"
        raise NaoLi(f"a FAMA não respondeu ({type(e).__name__})") from None
    vigia = None
    try:
        st = getattr(r, "status_code", None)
        if isinstance(st, int) and 300 <= st < 400:
            raise NaoLi(f"a FAMA respondeu {st} (redirecionamento: não sigo, e a chave não vai a outro endereço)")
        restante = PRAZO_S - (relogio() - inicio)
        if restante <= 0:
            raise NaoLi(f"a FAMA passou de {PRAZO_S} s para mandar a resposta inteira")
        vigia = _Vigia(r, restante)
        if st != 200:
            d = _detalhe(_corpo(r, inicio, relogio, vigia, DETALHE_BYTES, cortar=True))
            recusa = " (a chave foi recusada)" if st in (401, 403) else ""
            raise NaoLi(f"a FAMA respondeu {st}{recusa}" + (f": {d}" if d else ""))
        corpo = _corpo(r, inicio, relogio, vigia, TETO_BYTES)
    finally:
        if vigia is not None:
            vigia.cancelar()
        try:
            r.close()
        except Exception:       # noqa: BLE001 — fechar nunca derruba a leitura
            pass
    try:
        dado = json.loads(corpo)
    except ValueError:
        raise NaoLi("a resposta da FAMA não é JSON") from None
    if not isinstance(dado, list):
        raise NaoLi(f"a resposta da FAMA não é uma lista ({type(dado).__name__})")
    return dado


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
    """O critério do Nexus para "é o servidor" (o mesmo do `carga._maquina`): o servidor é o Linux, o PC é o Windows."""
    return "servidor" if os.name != "nt" else "pc"


def _mesmo_dia(gerado_em, agora: datetime) -> bool:
    """A última gravação foi hoje (o dia de Brasília)? Sem data legível, não: o batimento grava."""
    try:
        u = datetime.fromisoformat(str(gerado_em))
    except (TypeError, ValueError):
        return False
    u = u if u.tzinfo else u.replace(tzinfo=_BRT)
    return u.astimezone(_BRT).date() == agora.astimezone(_BRT).date()


def gerar_fama(config, sessao=None, *, fama=None, agora=None, gravar=True, forcar=False) -> dict:
    """Uma volta: confere o banco, lê a FAMA uma vez, monta o fato e a dimensão e grava o livro inteiro, conferido
    (`livros.publicar`). Devolve o relatório, só com contagens e motivos. `fama` = a sessão da FAMA (a de mentira nos
    testes; sem ela, o leitor abre a dele e a fecha); `forcar` pula o portão dos 50 min e o "nada mudou" (nunca a trava
    contra encolher)."""
    faltam = [k for k in CHAVES if not str(config.get(k) or "").strip()]
    if faltam:
        return {"pulou": f"a leitura da FAMA só liga com as três chaves ({', '.join(CHAVES)}); falta {', '.join(faltam)}"}
    if _maquina() != "servidor":
        return {"pulou": "a leitura da FAMA só roda no servidor (uma máquina só: o PC com a chave no .env não dá o "
                         "segundo GET da hora)"}
    if config.get("TESTING") and fama is None:
        # a cópia de prova não chega aqui: o ferramentas/subir_copia_de_prova.py (preparar_ambiente) desliga a carga de
        # dados (NEXUS_CARGA_DADOS=0) e apaga a NEXUS_FAMA_CHAVE
        return {"pulou": "teste nunca lê a FAMA de verdade (sem a FAMA de mentira)"}
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
    chave = str(config["NEXUS_FAMA_CHAVE"]).strip()
    try:
        if fama is not None:
            itens = ler(chave, fama)
        else:
            with requests.Session() as sessao_fama:         # a sessão que o leitor abre, ele fecha
                itens = ler(chave, sessao_fama)
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
    mudou = forcar or str(ant.get("sha_linhas") or "") != impressao
    # o batimento (revisão de 11/11/2026): sem mudança, grava uma vez por dia mesmo assim, "li, nada mudou"; o gerado_em de
    # mais de um dia passa a querer dizer "a leitura parou", e não "sem novidade na FAMA"
    if not mudou and _mesmo_dia(ant.get("gerado_em"), agora):
        return dict(rel, mudou=False, pulou="nada mudou na FAMA nem nas ligações, e o batimento de hoje já foi gravado")
    iso = agora.isoformat(timespec="seconds")
    q = F.linha_qualidade(linhas, dim, rel, lido_em, iso, no_banco or None)
    situacao = F.SITUACAO_MUDOU if mudou else F.SITUACAO_BATIMENTO
    tab = {F.ABA: (F.CAB_OS_FAMA, linhas), F.ABA_DIM: (F.CAB_DIM, dim), "qualidade": (CAB_QUALIDADE, [q]),
           "atualizacao": (F.CAB_ATUALIZACAO, [[iso, _maquina(), round(time.time() - t0, 1), len(linhas), F.COMO_LER,
                                                impressao, lido_em, situacao]])}
    if not gravar:
        return dict(rel, mudou=mudou, ensaio="montado com o dado real; nada gravado")
    # outra máquina gravou enquanto esta lia a FAMA
    if not forcar and (p := _gravou_ha_pouco(livros.ler(base, s, F.LIVRO, "atualizacao"), agora)):
        return dict(rel, pulou=p)
    rel["gravado"] = livros.publicar(F.LIVRO, F.NOME_LIVRO, tab, base=base, token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    rel["duracao_s"] = round(time.time() - t0, 1)
    return dict(rel, mudou=mudou, situacao=situacao)
