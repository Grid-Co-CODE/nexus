"""As fontes novas do dossiê da usina (19/11/2026): a programação do PCM e o que o contrato pede.

Levi, 19/11/2026: "Fontes novas, nesta ordem: Programação do PCM: confirme se a semana seguinte já está no banco antes da
segunda. Contratos: garantia de disponibilidade, PR próprio e prazos de atendimento, sem valores em reais. Comentários dos
analistas: só depois de montar o de-para entre o código da fonte e a usina". As duas primeiras estão aqui; a terceira
espera o de-para.

- **Programação** (`programacao_da_usina`): o `nexus_programacao · fato_programacao`, a semana corrente e a seguinte.
  Medido em 19/11/2026 no banco: o PCM gera a semana seguinte na sexta à noite (17:54 a 20:18 nas 8 últimas semanas), 2,2
  dias antes da segunda, e a carga de hora em hora a traz; de segunda a sexta à tarde a seguinte ainda não existe, e o
  dossiê diz isso em vez de dizer "nada programado". O fato não tem nome de pessoa nem o texto da tarefa.
- **Contrato** (`contrato_da_usina`): as regras que o Comando › Contratos leu do PDF (`contratos/edicao.visao`): a
  garantia de disponibilidade (`gerencial.garantia_de_disponibilidade`), as outras regras de "Disponibilidade e
  desempenho" (o PR próprio mora ali) e os prazos da categoria "SLA". Nenhum valor em reais sai daqui: a regra de valor
  não entra, e um "R$ 123" dentro de um texto vira "(valor no contrato)".

Puro: quem lê o banco é a tela (`torres/comando/__init__._extras_do_dossie`), que entrega as linhas."""
from __future__ import annotations

import re
from datetime import date, timedelta

DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
STATUS = {"nao_iniciada": "não iniciada", "finalizada": "finalizada", "pausada": "pausada", "em_progresso": "em andamento"}
MAX_TAREFAS = 30             # por semana: a usina em handover tem dezenas de blocos; o resto vira "e mais N"
MAX_SLA, MAX_DESEMPENHO = 14, 10
TEXTO = 200
CATEGORIA_DESEMPENHO, CATEGORIA_SLA = "Disponibilidade e desempenho", "SLA"
_REAIS = re.compile(r"R\$\s*\d[\d.,]*(?:\s*(?:mil|milh[ãõ][oe]s?)\b)?")


def _txt(v) -> str:
    return "" if v is None else " ".join(str(v).split())


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _data(data_id) -> date | None:
    n = _int(data_id)
    try:
        return date(n // 10000, n // 100 % 100, n % 100) if n else None
    except ValueError:
        return None


def _periodo(segunda: date) -> str:
    return f"{segunda:%d/%m} a {segunda + timedelta(days=6):%d/%m}"


# ── a programação do PCM ─────────────────────────────────────────────────────────────────────────────────────────────
def programacao_da_usina(linhas, usina_id, hoje: date) -> dict:
    """{"corrente": {"periodo", "tarefas", "a_mais"}, "seguinte": {...}, "seguinte_publicada"} da usina. `linhas` = as do
    fato das duas semanas, de TODAS as usinas: "a seguinte já foi publicada" é do fato (alguma usina tem bloco nela), não
    da usina. Uma tarefa = os blocos do mesmo dia, da mesma OS e do mesmo tipo: {"dia", "hora" (a do 1º bloco), "tipo",
    "os", "min" (a soma), "blocos", "status" ({rótulo: quantos}), "reprogramada"}."""
    segunda = hoje - timedelta(days=hoje.weekday())
    semanas = {int(f"{segunda:%Y%m%d}"): "corrente", int(f"{segunda + timedelta(days=7):%Y%m%d}"): "seguinte"}
    grupos = {"corrente": {}, "seguinte": {}}
    publicada = False
    for l in linhas or []:
        qual = semanas.get(_int(l.get("data_id_semana")))
        if qual is None:
            continue
        if qual == "seguinte":
            publicada = True
        if _int(l.get("usina_id")) != _int(usina_id):
            continue
        dia = _data(l.get("data_id_programada"))
        if dia is None:
            continue
        os_n, tipo = _txt(_int(l.get("os")) or l.get("os")), _txt(l.get("tipo_tarefa")) or "sem tipo"
        g = grupos[qual].setdefault((dia, os_n, tipo), {"data": dia, "dia": f"{DIAS[dia.weekday()]} {dia:%d/%m}",
                                                        "hora": "", "tipo": tipo, "os": os_n, "min": 0, "blocos": 0,
                                                        "status": {}, "reprogramada": False})
        hora = _txt(l.get("hora_inicio"))
        if hora and (not g["hora"] or hora < g["hora"]):
            g["hora"] = hora
        g["min"] += _int(l.get("duracao_min")) or 0
        g["blocos"] += 1
        st = STATUS.get(_txt(l.get("status_execucao")), _txt(l.get("status_execucao")) or "sem status")
        g["status"][st] = g["status"].get(st, 0) + 1
        g["reprogramada"] = g["reprogramada"] or _int(l.get("reprogramada")) == 1

    def semana(qual, seg):
        ts = sorted(grupos[qual].values(), key=lambda t: (t["data"], t["hora"], t["os"], t["tipo"]))
        return {"periodo": _periodo(seg), "tarefas": ts[:MAX_TAREFAS], "a_mais": max(0, len(ts) - MAX_TAREFAS)}
    return {"corrente": semana("corrente", segunda), "seguinte": semana("seguinte", segunda + timedelta(days=7)),
            "seguinte_publicada": publicada}


# ── o contrato ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _plano(nome) -> str:
    from . import gerencial as G
    return G._plano(nome)


def _sem_reais(texto: str) -> str:
    return _REAIS.sub("(valor no contrato)", texto)


def _regra(r: dict) -> dict:
    texto = _txt(r.get("vigente") or r.get("contratual"))
    return {"nome": _sem_reais(_txt(r.get("nome"))), "prazo": _sem_reais(_txt(r.get("prazo"))),
            "texto": _sem_reais(texto[:TEXTO] + ("…" if len(texto) > TEXTO else "")),
            "clausula": _txt((r.get("ref") or {}).get("clausula"))}


def _da_usina(contrato: dict, usina: str, codigo: str) -> bool:
    alvo, cod = _plano(usina), _txt(codigo).upper()
    for u in contrato.get("usinas") or []:
        nome = _txt(u.get("nome") if isinstance(u, dict) else u)
        if nome and (_plano(nome) == alvo or (cod and cod in nome.upper())):
            return True
    return False


def contrato_da_usina(fichas: dict | None, cliente: str, usina: str, codigo: str = "") -> dict:
    """O que o contrato do cliente pede, para a usina: {"contratos" (quantos o cliente tem), "ligada" (a usina está na
    lista de UM deles), "garantia" ({pct, nome, texto, clausula} ou None), "desempenho" (as outras regras de
    disponibilidade e desempenho, o PR próprio entre elas), "sla" (os prazos de atendimento), "sla_a_mais"}. Sem ficha do
    cliente (o PDF não foi lido), {"contratos": 0}. Cliente com vários contratos e a usina fora da lista de todos (ou na
    de mais de um): valem as regras de todos, sem repetir, e `ligada` diz que não deu para escolher."""
    from . import gerencial as G
    ficha = next((f for n, f in (fichas or {}).items() if G.chave_cliente(n) == G.chave_cliente(cliente)), None)
    ks = (ficha or {}).get("contratos") or []
    if not ks:
        return {"contratos": 0}
    dela = [k for k in ks if _da_usina(k, usina, codigo)]
    ligada = len(dela) == 1 or len(ks) == 1
    usados = dela if len(dela) == 1 else ks
    garantia = G.garantia_de_disponibilidade({"contratos": usados})
    desempenho, sla, vistos = [], [], set()
    for k in usados:
        for r in k.get("regras") or []:
            cat = r.get("categoria")
            if cat not in (CATEGORIA_DESEMPENHO, CATEGORIA_SLA):
                continue
            x = _regra(r)
            chave = (cat, x["nome"].lower(), x["prazo"].lower(), x["texto"].lower())
            if chave in vistos or (garantia and cat == CATEGORIA_DESEMPENHO and x["nome"] == _sem_reais(garantia["nome"])):
                continue
            vistos.add(chave)
            (desempenho if cat == CATEGORIA_DESEMPENHO else sla).append(x)
    if garantia:
        garantia = dict(garantia, nome=_sem_reais(garantia["nome"]), texto=_sem_reais(garantia["texto"]))
    return {"contratos": len(ks), "ligada": ligada, "garantia": garantia, "desempenho": desempenho[:MAX_DESEMPENHO],
            "desempenho_a_mais": max(0, len(desempenho) - MAX_DESEMPENHO), "sla": sla[:MAX_SLA],
            "sla_a_mais": max(0, len(sla) - MAX_SLA)}
