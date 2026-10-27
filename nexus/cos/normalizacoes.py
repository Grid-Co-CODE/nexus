"""Normalizações (27/10/2026, Levi: "Gostaria de inserir no COS" a API de normalizações da Ronda COS): quando cada usina
voltou, pela hora que o COS registrou, e se a OS dela segue aberta no Fracttal.

Por que existe: o Fracttal só encerra a OS quando o técnico a fecha, muitas vezes horas ou dias depois da volta. Na
semana até 27/10/2026 foram 341 normalizações, e 208 delas ainda tinham a OS aberta no Fracttal (a OS 16702, de
Mandaguaçu, normalizada em 19/10 às 05:53, oito dias depois seguia "em processo").

De onde: `GET <Andamento>/api/normalizacoes` (contrato `versao: 1`, guia em docs do dono da Ronda COS), com a mesma chave
das outras telas do COS. A API é incremental: devolve um `cursor`, e o pedido seguinte com `desde=<cursor>` traz só o que
mudou. Aqui o Nexus guarda em memória as normalizações dos últimos 30 dias, por `registro` (o mesmo `registro` pode vir
de novo, com o estado novo: substitui), e pergunta o que mudou a cada minuto. Nada vai ao banco: a tela só lê.

O que é regra de lá e o Nexus não refaz: o que é normalização, a hora da volta (`normalizado_em`, já corrigida quando
alguém corrigiu), o tempo fora, a OS aberta no Fracttal (a varredura de 30 em 30 min de lá). Daqui são só os filtros, as
contas da faixa e o "há quanto tempo a OS segue aberta depois da volta".
"""
import threading
import time
import urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

from . import andamento as AND

VERSAO = 1
# O período da tela (dias para trás da hora da volta). 7 é o padrão da própria API.
DIAS = (1, 7, 30)
DIAS_PADRAO = 7
# Por mês (27/10/2026, Levi: "a única mudança que quero é ver por mês"): o mês corrente e os anteriores, até MESES no
# total. A memória guarda desde o 1º dia do mais antigo (em 27/10: desde 01/08), ~1.500 normalizações por mês.
MESES = 3
MESES_NOME = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
              "Novembro", "Dezembro")
# A cada minuto pergunta o que mudou (o guia: "se `mais` for false, espere 1 minuto").
TTL_S = 60
# A primeira carga de 30 dias vem em páginas: 300 itens levam ~2 s lá. Teto de páginas por pedido da tela, para ninguém
# esperar a carga inteira de uma vez; o resto vem nos pedidos seguintes, e a tela diz que está carregando.
PAGINA = 500
PAGINAS_POR_PEDIDO = 4
TIMEOUT_S = 15

SEVERIDADES = {"CRITICO": ("Crítico", "critico"), "ALTO": ("Alto", "alerta"), "MEDIO": ("Médio", "info"),
               "BAIXO": ("Baixo", "neutro")}
# O status da OS aberta no Fracttal (o mesmo das OS em aberto). O segundo valor é o que o card da OS espera.
STATUS_OS = {1: ("Em processo", "Em Processo"), 2: ("Em verificação", "Em Verificação")}
# Por onde a normalização foi registrada (`declarada_por`).
DECLARADA_POR = {"pessoa": "Operador", "sistema": "Sistema", "fracttal": "Fracttal",
                 "religamento_remoto": "Religamento remoto", "criacao_da_os": "Criação da OS"}

_estado: dict[str, dict] = {}
_trava = threading.Lock()          # a memória
_trava_carga = threading.Lock()    # um pedido ao Andamento por vez (a primeira carga leva segundos)


@dataclass
class Painel:
    itens: list = field(default_factory=list)
    contagem: dict = field(default_factory=dict)
    resumo: dict = field(default_factory=dict)
    varredura: datetime | None = None
    desfeitas: int = 0
    carregando: bool = False


def _mes_de(d: datetime) -> datetime:
    return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _mes_seguinte(d: datetime) -> datetime:
    return _mes_de(d.replace(day=28) + timedelta(days=4))


def meses(agora: datetime) -> list[tuple[str, str, datetime, datetime]]:
    """(chave "2026-10", rótulo, começo, começo do seguinte), do mês corrente para trás. O ano só no rótulo de mês de
    outro ano."""
    out, ini = [], _mes_de(agora)
    for _ in range(MESES):
        rot = MESES_NOME[ini.month - 1] + ("" if ini.year == agora.year else f" de {ini.year}")
        out.append((ini.strftime("%Y-%m"), rot, ini, _mes_seguinte(ini)))
        ini = _mes_de(ini - timedelta(days=1))
    return out


def inicio_da_guarda(agora: datetime) -> datetime:
    """Desde quando a memória guarda: o 1º dia do mês mais antigo da tela (cobre também os 30 dias)."""
    return min(meses(agora)[-1][2], agora - timedelta(days=max(DIAS) + 1))


def mes_pedido(v, agora: datetime) -> str:
    return v if v in {m[0] for m in meses(agora)} else ""


def dias_pedidos(v) -> int:
    try:
        d = int(v)
    except (TypeError, ValueError):
        return DIAS_PADRAO
    return d if d in DIAS else DIAS_PADRAO


def limpar() -> None:
    with _trava:
        _estado.clear()


def validar(d) -> dict:
    if not isinstance(d, dict):
        raise AND.FonteErro("a resposta do Andamento não é um objeto")
    if d.get("versao") != VERSAO:
        raise AND.FonteErro(f"o Andamento fala a versão {d.get('versao')!r} das normalizações, e o Nexus entende a "
                            f"{VERSAO}")
    if not isinstance(d.get("normalizacoes"), list) or not isinstance(d.get("cursor"), str):
        raise AND.FonteErro("a resposta do Andamento não tem as normalizações")
    return d


def _data_da(n: dict) -> datetime | None:
    return AND.instante(n.get("normalizado_em")) or AND.instante(n.get("inicio"))


def ler(config, agora: datetime | None = None) -> AND.Leitura:
    """As normalizações guardadas (`dados = {"itens": [...], "carregando": bool}`), postas em dia se a última pergunta
    tem mais de 1 minuto. Na falha, a memória continua, dita velha."""
    f = AND.fonte(config)
    if not f.ligada:
        return AND.Leitura("", None, erro="a fonte do Andamento não está ligada neste servidor")
    agora = agora or AND.agora()
    with _trava_carga:
        with _trava:
            st = _estado.get(f.url)
            # em dia há menos de 1 minuto, ou falhou há menos de 1 minuto (o Andamento fora não segura cada tela 15 s)
            if st and (st["completo"] or st.get("erro")) and time.monotonic() - st["perguntado"] < TTL_S:
                return _leitura(st)
            st = st or {"itens": {}, "cursor": "", "completo": False, "perguntado": 0.0, "lido_em": None}
        desde = st["cursor"] or inicio_da_guarda(agora).isoformat()
        itens, cursor, completo, erro = dict(st["itens"]), st["cursor"], False, ""
        try:
            for _ in range(PAGINAS_POR_PEDIDO):
                q = urllib.parse.urlencode({"desde": desde, "limite": PAGINA})
                d = validar(AND._pedir(f, "/api/normalizacoes?" + q, timeout=TIMEOUT_S))
                for n in d["normalizacoes"]:
                    if isinstance(n, dict) and n.get("registro"):
                        itens[str(n["registro"])] = n          # o mesmo registro volta com o estado novo: substitui
                cursor = desde = d["cursor"]
                if not d.get("mais"):
                    completo = True
                    break
        except AND.FonteErro as ex:
            erro = ("o Andamento ainda não tem a rota das normalizações, ou ela está desligada lá"
                    if ex.codigo == 404 else str(ex))
        corte = inicio_da_guarda(agora)
        itens = {k: n for k, n in itens.items() if (_data_da(n) or agora) >= corte}
        with _trava:
            if erro and not st["itens"] and not itens:
                return AND.Leitura("", None, erro=erro)
            novo = {"itens": itens, "cursor": cursor, "completo": completo or (bool(erro) and st["completo"]),
                    "perguntado": time.monotonic(), "lido_em": st["lido_em"] if erro else time.time(), "erro": erro}
            _estado[f.url] = novo
            return _leitura(novo)


def _leitura(st: dict) -> AND.Leitura:
    erro = st.get("erro", "")
    return AND.Leitura("", {"itens": list(st["itens"].values()), "carregando": not st["completo"]},
                       lido_em=st["lido_em"], erro=erro, velha=bool(erro))


# ── o que a tela mostra (puro) ───────────────────────────────────────────────────────────────────────────────────────
def duracao(minutos) -> str:
    """O tempo fora: minutos até 1 h, horas e minutos até 2 dias, depois dias e horas."""
    try:
        m = max(0, int(minutos))
    except (TypeError, ValueError):
        return "—"
    if m < 60:
        return f"{m} min"
    if m < 48 * 60:
        h, r = divmod(m, 60)
        return f"{h} h {r:02d}" if r else f"{h} h"
    d, r = divmod(m, 24 * 60)
    return f"{d} d {r // 60} h" if r // 60 else f"{d} d"


def _item(n: dict, agora: datetime) -> dict:
    volta = AND.instante(n.get("normalizado_em"))
    sev = str(n.get("severidade") or "").upper()
    aberta = n.get("os_aberta_no_fracttal") if isinstance(n.get("os_aberta_no_fracttal"), dict) else None
    status = STATUS_OS.get(aberta.get("status"), (f"status {aberta.get('status')}", "")) if aberta else ("", "")
    equip = [e for e in n.get("equipamentos") or [] if isinstance(e, dict)]
    informe = n.get("informe") if isinstance(n.get("informe"), dict) else {}
    try:
        fora = int(n.get("fora_min")) if n.get("fora_min") is not None else None
    except (TypeError, ValueError):
        fora = None
    return {
        "registro": str(n.get("registro")),
        "os": str(n.get("os") or "").strip(),
        "os_relacionadas": [str(x) for x in n.get("os_relacionadas") or [] if str(x).strip()],
        "cliente": str(n.get("cliente") or "").strip() or "(sem cliente)",
        "usina": str(n.get("usina") or n.get("usina_codigo") or "").strip() or "(sem usina)",
        "usina_codigo": str(n.get("usina_codigo") or ""),
        "equipamentos": [str(e.get("nome") or e.get("codigo") or "") for e in equip],
        "falha": str(n.get("tipo_falha_rotulo") or n.get("tipo_falha") or "").strip() or "—",
        "severidade": sev,
        "sev": SEVERIDADES.get(sev, (sev.title() or "—", "neutro")),
        "normalizada": n.get("normalizada") is not False,
        "inicio": AND.instante(n.get("inicio")),
        "volta": volta,
        "data": volta or AND.instante(n.get("inicio")),
        "fora": fora,
        "fora_txt": duracao(fora) if fora is not None else "—",
        "hora_real": n.get("hora_real") is not False,
        "fim_corrigido": bool(n.get("fim_corrigido")),
        "declarada_por": DECLARADA_POR.get(str(n.get("declarada_por") or ""), str(n.get("declarada_por") or "") or "—"),
        "aberta": bool(aberta),
        "status": status[0],
        "status_card": status[1],
        "pct": int((aberta or {}).get("concluida_pct") or 0),
        "aberta_ha_dias": (agora - volta).days if aberta and volta else None,
        "varrida_em": AND.instante((aberta or {}).get("varrida_em")),
        "resumo": str(informe.get("resumo") or "").strip()[:160],
        "fora_do_escopo": bool(n.get("fora_do_escopo_oem")),
    }


def painel(leitura, agora: datetime, dias: int = DIAS_PADRAO, cliente: str = "", severidade: str = "",
           so_aberta: bool = False, mes: str = "") -> Painel | None:
    """A tela. O período é dos últimos `dias` ou, com `mes` ("2026-10"), daquele mês inteiro, pela hora da volta. As pílulas de cliente e de severidade e o "só com OS aberta" contam sobre o período, ANTES dos outros
    filtros (um contador que encolhe ao filtrar não diz mais quanto existe). A faixa conta o recorte de cliente e
    severidade, sem o "só com OS aberta" (senão a fatia com a OS aberta seria sempre 100%). A normalização desfeita (a
    ocorrência voltou a aberta) fica fora da lista e é contada à parte; a sem hora real fica na lista e fora da mediana."""
    d = leitura.dados if leitura else None
    if not d:
        return None
    dias = dias_pedidos(dias)
    desde, ate = agora - timedelta(days=dias), None
    um_mes = next((m for m in meses(agora) if m[0] == mes), None)
    if um_mes:                                  # o mês escolhido vale no lugar dos dias
        desde, ate = um_mes[2], um_mes[3]
    todos = [_item(n, agora) for n in d.get("itens") or []]
    no_periodo = [i for i in todos if i["data"] and i["data"] >= desde and (ate is None or i["data"] < ate)]
    base = [i for i in no_periodo if i["normalizada"]]
    recorte = [i for i in base if (not cliente or i["cliente"] == cliente)
               and (not severidade or i["severidade"] == severidade)]
    lista = [i for i in recorte if i["aberta"]] if so_aberta else recorte
    lista.sort(key=lambda i: i["data"], reverse=True)
    com_hora = [i["fora"] for i in recorte if i["hora_real"] and i["fora"] is not None]
    abertas = [i for i in recorte if i["aberta"]]
    varridas = [i["varrida_em"] for i in todos if i["varrida_em"]]
    sev_count = Counter(i["severidade"] for i in base)
    return Painel(
        itens=lista,
        contagem={
            "cliente": dict(sorted(Counter(i["cliente"] for i in base).items())),
            "severidade": {k: sev_count.get(k, 0) for k in SEVERIDADES},
            "abertas": sum(1 for i in base if i["aberta"]),
        },
        resumo={
            "total": len(recorte),
            "abertas": len(abertas),
            "abertas_pct": round(100 * len(abertas) / len(recorte)) if recorte else 0,
            "abertas_7d": sum(1 for i in abertas if (i["aberta_ha_dias"] or 0) >= 7),
            "mediana": duracao(median(com_hora)) if com_hora else "—",
            "sem_hora_real": sum(1 for i in recorte if not i["hora_real"]),
        },
        varredura=max(varridas) if varridas else None,
        desfeitas=sum(1 for i in no_periodo if not i["normalizada"]),
        carregando=bool(d.get("carregando")),
    )
