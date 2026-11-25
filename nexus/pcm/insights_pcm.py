"""PCM → Insights do PCM (25/11/2026): o que pede ação agora, em cinco frases.

A base de ideias é a planilha "PCM - Controle Semanal" do time (o `controle_semanal.py` do repositório do PCM, que roda
num PC), pedida na reunião do PCM de 24/11/2026. O desenho é do Levi: "Menos é mais. Vamos tentar ser diretos e ter
informações bem direcionadas, fáceis de leitura. Não precisa ficar enchendo de KPI. Se a informação se repete, a gente
mantém só uma informação." Por isso:
- cada cartão é uma frase, com o número e o pior caso, e a lista curta só quando ela não mora em outra tela;
- o que já existe no Nexus não se repete: a OS parada usa a conta do Radar de Backlog e a rolagem a do Acompanhamento PCM
  (o mesmo número das duas telas); MPA/MPS atrasadas, o backlog detalhado, a carga por supervisor e as usinas que pedem
  atenção já estão no Acompanhamento, no Quadro e no Relatório Executivo, e ficam fora daqui;
- as regras dos três que não existiam são as da planilha, para os números serem os que o time conhece: aberta é a tarefa
  aberta de OS que não está em Finalizados nem em Verificação; "dias" é o atraso contra a data programada (o `dias` da
  Gestão PCM); usina de teste e OS do backoffice ficam fora (a marca `bo`, a mesma dos relatórios).
Conferido em 25/11/2026 contra a planilha de 24/11: 90 religamentos abertos (o pior, a OS 16956, 77 dias), 12 usinas com
handover aberto (a pior, 100 dias), a tarefa que mais rolou 13 vezes.
"""
from __future__ import annotations

import collections
import re
from datetime import date

from .acompanhamento import dados as A

FECHADA = ("finalizados", "finalizado", "verificação", "verificacao")
RELIGAMENTO_DIAS = 7           # religamento aberto além disto pede ação (a planilha lista todos; o pior tinha 76 dias)
ROLAGEM_MIN = 5                # a tarefa que entrou em 5 semanas ou mais (a planilha mostra o top 15: de 9 a 13 vezes)
LISTA = 10                     # quantas linhas a lista curta do cartão mostra
_MPM = re.compile(r"\bMPM\b|preventiva mensal", re.I)
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")


def _os(v) -> str:
    s = str(v if v is not None else "").strip()
    return s[:-2] if s.endswith(".0") else s


def _tarefas(gestao: dict) -> list[dict]:
    """As tarefas que contam: fora a usina de teste e a OS do backoffice (a marca `bo` do robô do PCM)."""
    ts = (gestao or {}).get("tarefas") or []
    bo = {_os(t.get("os")) for t in ts if t.get("bo")}
    return [t for t in ts if "teste" not in str(t.get("usina") or "").lower() and _os(t.get("os")) not in bo]


def _aberta(t: dict) -> bool:
    return bool(t.get("aberta")) and str(t.get("osStatus") or "").strip().lower() not in FECHADA


def _dias(t: dict) -> int:
    try:
        return int(t.get("dias") or 0)
    except (TypeError, ValueError):
        return 0


def religamentos(tarefas: list[dict]) -> dict:
    """As OS de religamento abertas há mais de RELIGAMENTO_DIAS dias, a mais velha primeiro (a aba Religamentos)."""
    por_os: dict[str, dict] = {}
    for t in tarefas:
        if _aberta(t) and "religamento" in str(t.get("tipo") or "").lower():
            e = por_os.setdefault(_os(t.get("os")), {"os": _os(t.get("os")), "usina": A.curta(t.get("usina") or ""),
                                                      "tipo": str(t.get("tipo") or ""), "dias": 0})
            e["dias"] = max(e["dias"], _dias(t))
    velhas = sorted((e for e in por_os.values() if e["dias"] > RELIGAMENTO_DIAS), key=lambda e: -e["dias"])
    return {"n": len(velhas), "abertas": len(por_os), "linhas": velhas}


def handovers(tarefas: list[dict]) -> dict:
    """As usinas com tarefa de handover vencida, a mais velha primeiro (a aba Handovers)."""
    por_usina: dict[str, dict] = {}
    for t in tarefas:
        if _aberta(t) and "handover" in (str(t.get("tipo") or "") + str(t.get("tarefa") or "")).lower():
            e = por_usina.setdefault(str(t.get("usina") or ""), {"usina": A.curta(t.get("usina") or ""), "abertas": 0,
                                                                 "vencidas": 0, "dias": 0, "os": set()})
            e["abertas"] += 1
            e["vencidas"] += 1 if t.get("atrasado") else 0
            e["dias"] = max(e["dias"], _dias(t))
            e["os"].add(_os(t.get("os")))
    linhas = sorted((dict(e, os=sorted(e["os"])) for e in por_usina.values() if e["vencidas"]), key=lambda e: -e["dias"])
    return {"n": len(linhas), "linhas": linhas}


def mpm_do_mes(tarefas: list[dict], hoje: date) -> dict:
    """As usinas com MPM do mês corrente já vencida e aberta, a de menor parte feita primeiro (a aba MPM % usina × mês).
    O mês é o da data programada; feita = OS em Finalizados ou Verificação, ou a tarefa finalizada."""
    por_usina: dict[str, dict] = {}
    mes = f"{hoje.year:04d}-{hoje.month:02d}"
    for t in tarefas:
        txt = f"{t.get('tarefa') or ''} {t.get('tipo') or ''}"
        if not _MPM.search(txt) or "spare" in txt.lower() or str(t.get("dataProg") or "")[:7] != mes:
            continue
        e = por_usina.setdefault(str(t.get("usina") or ""), {"usina": A.curta(t.get("usina") or ""), "total": 0,
                                                             "feitas": 0, "vencidas": 0})
        e["total"] += 1
        if _aberta(t):
            e["vencidas"] += 1 if _dias(t) > 0 else 0
        else:
            e["feitas"] += 1
    linhas = sorted((e for e in por_usina.values() if e["vencidas"]),
                    key=lambda e: (e["feitas"] / e["total"], -e["vencidas"]))
    return {"n": len(linhas), "mes": MESES[hoje.month - 1], "linhas": linhas}


def paradas(gestao: dict, hoje: date) -> dict:
    """As OS paradas: as do Radar de Backlog do Acompanhamento PCM (a mesma conta, para o número ser um só no Nexus)."""
    ab = A.abertas(_tarefas(gestao), hoje)
    radar = A.backlog(_tarefas(gestao), ab, hoje)
    return {"n": len(radar), "dias": A.IDADE_BACKLOG, "pior": radar[0] if radar else None}


def rolagens(gestao: dict, bd: dict, hoje: date) -> dict:
    """As OS vivas que entraram em ROLAGEM_MIN semanas ou mais (a conta das rolagens do Acompanhamento PCM)."""
    ab = A.abertas(_tarefas(gestao), hoje)
    rol = A.rolagens(bd, ab)
    por_os = {o["os"]: o for o in ab}
    linhas = sorted(({"os": k, "vezes": v, "usina": A.curta(por_os[k]["usina"]), "tarefa": por_os[k]["desc"]}
                     for k, v in rol.items() if v >= ROLAGEM_MIN and k in por_os), key=lambda e: -e["vezes"])
    return {"n": len(linhas), "linhas": linhas}


def montar(gestao: dict | None, bd: dict | None, hoje: date) -> dict:
    """Os cinco cartões, na ordem em que se age: o que pode estar com a usina fora (religamento), o compromisso do mês
    (MPM), a usina nova (handover), e o que envelhece (parada e rolagem)."""
    ts = _tarefas(gestao or {})
    return {"religamento": religamentos(ts), "mpm": mpm_do_mes(ts, hoje), "handover": handovers(ts),
            "parada": paradas(gestao or {}, hoje), "rolagem": rolagens(gestao or {}, bd or {}, hoje), "lista": LISTA,
            "religamento_dias": RELIGAMENTO_DIAS, "rolagem_min": ROLAGEM_MIN}


def registrar(bp) -> None:
    """A tela `/t/pcm/insights` (a Tela "insights" da torre PCM, que era só o lugar reservado)."""
    from flask import current_app, render_template

    from . import fonte

    @bp.route("/insights", endpoint="insights")
    def tela():
        cfg = current_app.config
        g, b = fonte.ler_gestao(cfg), fonte.ler(cfg)
        d = montar(g.dados, b.dados, date.today()) if g.dados is not None else None
        return render_template("pcm/insights.html", d=d, erro=g.erro if g.dados is None else "",
                               gerado=(g.dados or {}).get("geradoEm") or "")
