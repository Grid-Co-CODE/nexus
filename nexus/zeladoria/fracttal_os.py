"""A consulta da OS pelo número, para o app da zeladoria (a função `fracttal-os` do Radar, 06/11/2026).

No Supabase era uma função na nuvem que lia o Fracttal; aqui é o leitor do Nexus (`nexus.campo.nota_fracttal`, no ritmo
do porteiro do Fracttal: a cota de 200 pedidos por minuto é da empresa). O app pede até 10 números de uma vez e preenche
a OS de serviço com o técnico, as datas, a situação, a área, a usina e o texto do serviço, como o Radar fazia; os campos
saem das mesmas colunas que a sincronização das rondas do Radar usava (`fracttal-sync`).
"""
import re
from datetime import datetime, timedelta, timezone

FOLIO = re.compile(r"^\d{1,12}$")
LOTE = 10
_BRT = timezone(timedelta(hours=-3))


def _data_brt(v) -> str | None:
    """O dia de Brasília de uma data do Fracttal (o 02:30Z é o dia anterior)."""
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return str(v)[:10]
    if d.tzinfo is None:
        return d.date().isoformat()
    return d.astimezone(_BRT).date().isoformat()


def _txt(v) -> str:
    return str(v or "").strip()


def da_os(folio: str, linhas: list) -> dict:
    """As linhas (tarefas) de uma OS do REST viram o que o app espera; sem linha, `encontrada` falso."""
    if not linhas:
        return {"folio": folio, "encontrada": False}
    o = linhas[0]
    desc = _txt(o.get("description"))
    partes = desc.split(" — ")
    usina = _txt(o.get("groups_1_description")) or (partes[1].strip() if len(partes) > 1 else "")
    areas = []
    for l in linhas:
        a = _txt(l.get("tasks_log_types_2_description"))
        if a and a not in areas:
            areas.append(a)
    try:
        status = int(str(o.get("id_status_work_order")).strip())
    except ValueError:
        status = None
    return {
        "folio": folio, "encontrada": True, "status": status,
        "tecnico": _txt(o.get("personnel_description") or o.get("user_assigned") or o.get("created_by")) or None,
        "aberta_em": o.get("creation_date") or None,
        "data_marcada": _data_brt(o.get("initial_date") or o.get("date_maintenance")),
        "concluida_em": o.get("final_date") or None,
        "area": areas, "usina_texto": usina or None, "servico_texto": desc[:300] or None,
        "nota": _txt(o.get("task_note") or o.get("note"))[:300] or None,
    }


def consultar(folios, ler=None) -> dict:
    """{"os": [...], "limite": bool}. O Fracttal que recusa no meio (a cota da empresa) devolve o que já veio e
    `limite`, e o app diz quantas faltaram, como no Radar."""
    from ..campo import nota_fracttal
    out = []
    for f in folios:
        try:
            linhas = nota_fracttal.tarefas_da_os(f, ler)
        except Exception:  # noqa: BLE001 — a cota de 200/min é da empresa: o resto fica para a próxima
            return {"os": out, "limite": True}
        out.append(da_os(f, [l for l in linhas if str(l.get("wo_folio")) == f]))
    return {"os": out, "limite": False}
