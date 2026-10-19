"""A conta do bloco Manutenção da Visão do responsável (18/10/2026), pura: nada de rede, banco nem Flask.

Levi, 18/10/2026, ao trazer para a Visão o que um supervisor tinha no painel próprio: OS abertas e atrasadas, tarefas
paradas e o motivo, o programado × feito e a zeladoria, "pegando tudo do Fracttal ou Nexus". As fontes, todas no banco:
as tarefas das OS (`nexus_os · fato_tarefa_os`, lidas do Fracttal pelo Nexus), os motivos do PCM (`nexus_pcm_motivos`,
os do painel Fora da programação), as OS de chamado (`nexus_chamados`) e a programação (`nexus_programacao`, a cópia do
arquivo do PCM).

As réguas são as das telas donas, como no resto da Visão (nenhum indicador refeito com régua nova):
- atrasada é a do PCM (`DIAS_ALERTA` do robô da Gestão PCM): tarefa aberta com a Data Programada há MAIS de 10 dias,
  contada por tarefa como o PCM conta. Decisão do Levi: "Régua do PCM: +10 dias";
- a semana é a conta do Fechamento da semana do PCM (linhas do plano finalizadas ÷ linhas do plano, meta de 85%), na
  semana passada, FECHADA: na semana corrente a rolagem da noite tira da agenda o que não foi feito (vai às pendentes,
  fora do fato) e o "até hoje" saía inflado. O dia de hoje até agora só informa;
- nada conta duas vezes: a tarefa parada por motivo conta em Paradas e não nas atrasadas; a zeladoria tem a coluna dela;
  a OS de chamado já está em Chamados; Teste o PCM também tira; e o backoffice fica fora (decisão do Levi: o supervisor
  não age sobre elas, e elas já ficam fora da programação).
"""
from collections import Counter
from datetime import date, timedelta

from ..dados import equipamento as E
from ..dados import fatos as D
from ..dados.calendario import data_id

DIAS_ATRASO = 10
META_SEMANA = 85.0
LIMITE_PADRAO, LIMITE_MIN, LIMITE_MAX = 30, 10, 365
_VIVA = ("em_processo", "em_verificacao")
# a tarefa que mostra que a OS começou (Levi, 18/10/2026: separar nas OS abertas "o que não foi iniciado"): em progresso,
# pausada no App ou feita. Sem nenhuma, a OS em processo não foi iniciada (estado vazio não prova começo)
_COMECOU = ("em_progresso", "pausada", "finalizada")


def _dia(v) -> date | None:
    n = D._id(v)
    try:
        return date(n // 10000, n // 100 % 100, n % 100) if n else None
    except ValueError:
        return None


def marcas_paradas(vigentes: dict, usina_de) -> list[dict]:
    """As marcas do recorte do painel Fora da programação (o motivo que tira da programação, ou a justificativa que
    veio do App), prontas para casar com as tarefas: a OS, o código canônico ("" = todos os ativos da OS) e a
    `tarefa_chave` (a mesma conta do fato). `usina_de(marca)` dá o `usina_id` da marca (o fato, quando casa, vence)."""
    out = []
    for iid, m in (vigentes or {}).items():
        if not isinstance(m, dict) or not (m.get("tira") or m.get("origem_motivo") == "app"):
            continue
        os_, chave = D._id(m.get("os")), D.tarefa_chave(m.get("tarefa"))
        if not os_ or not chave:
            continue
        out.append({"usina_id": usina_de(m), "os": os_, "codigo": E.canon(m.get("codigo")), "chave": chave,
                    "motivo": D._txt(m.get("motivo")) or None, "desde": _dia(D.data_do_registro(m.get("desde"))),
                    "quem": D._txt(m.get("quem_motivo") or m.get("quem")) or None})
    return out


def _vazio() -> dict:
    return {"os_abertas": 0, "em_verificacao": 0, "nao_iniciadas": 0, "em_execucao": 0, "atrasadas": 0,
            "atrasadas_os": 0, "maior_atraso": None,
            "lista_atrasadas": [], "vencem": 0, "paradas": 0, "motivo_comum": None, "lista_paradas": [],
            "zeladoria_proxima": None, "zeladoria_vencida": None, "zeladoria_ultima": None}


def _min(a, b):
    return b if a is None or (b is not None and b < a) else a


def tarefas_por_usina(tarefas, marcas: list[dict], os_de_chamado: set, hoje: date) -> dict[int, dict]:
    """Por `usina_id`, o que o bloco mostra (ver `_vazio`). `tarefas` = as linhas do fato (o banco pode dar tudo como
    texto); None = o fato ainda não está no banco: só as paradas, por marca, como o painel faz sem a Gestão PCM."""
    idx = {(m["os"], m["codigo"], m["chave"]): m for m in marcas}
    out, abertas, verif, atr, tipo_atr, wids, paradas = {}, {}, {}, {}, {}, {}, {}
    comecou = set()

    def r_(uid):
        return out.setdefault(uid, _vazio())
    for t in tarefas or ():
        uid, os_ = D._id(t.get("usina_id")), D._id(t.get("os"))
        if not uid or not os_:
            continue
        r = r_(uid)
        wids[os_] = D._id(t.get("fracttal_os_id"))
        if D._txt(t.get("estado_tarefa")) in _COMECOU:
            comecou.add(os_)
        tipo, prog = D._txt(t.get("tipo_tarefa")), _dia(t.get("data_id_programada"))
        viva = D._txt(t.get("estado_tarefa")) != "finalizada" and D._txt(t.get("status_os")) in _VIVA
        if tipo == "zeladoria":
            if viva and prog:
                k = "zeladoria_proxima" if prog >= hoje else "zeladoria_vencida"
                r[k] = _min(r[k], prog)
            elif not viva:
                fim = _dia(t.get("data_id_fim"))
                if fim and (r["zeladoria_ultima"] is None or fim > r["zeladoria_ultima"]):
                    r["zeladoria_ultima"] = fim
            continue
        fora = D._int(t.get("do_backoffice")) == 1 or tipo == "teste" or os_ in os_de_chamado
        # a OS em verificação tem as tarefas feitas e espera o supervisor (a fila da Aprovação): conta como aberta e
        # esperando a aprovação qualquer que seja o estado da tarefa (revisão de 18/10/2026: só contava a tarefa viva)
        if D._txt(t.get("status_os")) == "em_verificacao" and not fora:
            abertas.setdefault(uid, set()).add(os_)
            verif.setdefault(uid, set()).add(os_)
        if not viva:
            continue
        ch = D._txt(t.get("tarefa_chave"))
        m = idx.get((os_, E.canon(t.get("codigo_ativo")), ch)) or idx.get((os_, "", ch))
        if m:
            paradas.setdefault(uid, []).append(m)
            continue
        if fora:
            continue
        abertas.setdefault(uid, set()).add(os_)
        if prog:
            dias = (hoje - prog).days
            if dias > DIAS_ATRASO:
                r["atrasadas"] += 1
                a = atr.setdefault(uid, {})
                if dias > a.get(os_, -1):
                    a[os_], tipo_atr[os_] = dias, tipo or None
            if 0 <= (prog - hoje).days <= 1:
                r["vencem"] += 1
    if tarefas is None:
        for m in marcas:
            if m["usina_id"]:
                r_(m["usina_id"])
                paradas.setdefault(m["usina_id"], []).append(m)
    for uid, r in out.items():
        r["os_abertas"], r["em_verificacao"] = len(abertas.get(uid, ())), len(verif.get(uid, ()))
        em_processo = abertas.get(uid, set()) - verif.get(uid, set())
        r["nao_iniciadas"] = len(em_processo - comecou)
        r["em_execucao"] = len(em_processo) - r["nao_iniciadas"]
        a = atr.get(uid, {})
        r["atrasadas_os"], r["maior_atraso"] = len(a), (max(a.values()) if a else None)
        r["lista_atrasadas"] = [{"os": o, "wid": wids.get(o), "dias": d, "tipo": tipo_atr.get(o)}
                                for o, d in sorted(a.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
        ps = paradas.get(uid, [])
        r["paradas"] = len(ps)
        cont = Counter(m["motivo"] for m in ps if m["motivo"])
        r["motivo_comum"] = sorted(cont.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if cont else None
        unicas = {(m["os"], m["codigo"], m["chave"]): m for m in ps}
        r["lista_paradas"] = [{"os": m["os"], "wid": wids.get(m["os"]), "motivo": m["motivo"], "desde": m["desde"],
                               "quem": m["quem"]}
                              for m in sorted(unicas.values(), key=lambda m: (m["desde"] or date.max, m["os"]))][:5]
    return out


def semana_por_usina(prog: list[dict], hoje: date, agora_hhmm: str) -> dict[int, dict]:
    """Por `usina_id`: a semana passada pela conta do Fechamento (linhas do plano e as finalizadas; sem linha da usina,
    `passada_pct` None, nunca 0%) e o dia de hoje até agora (as linhas cujo horário de início já passou)."""
    segunda = hoje - timedelta(days=hoje.weekday())
    passada = segunda - timedelta(days=7)
    pid, hid = data_id(passada), data_id(hoje)
    ano, sem, _ = passada.isocalendar()
    out = {}

    def r_(uid):
        return out.setdefault(uid, {"passada": f"{ano}-W{sem:02d}", "passada_prog": 0, "passada_feitas": 0,
                                    "passada_pct": None, "hoje_devidas": 0, "hoje_feitas": 0})
    for l in prog or ():
        uid = D._id(l.get("usina_id"))
        if not uid:
            continue
        feita = D._txt(l.get("status_execucao")) == "finalizada"
        if D._int(l.get("data_id_semana")) == pid:
            r = r_(uid)
            r["passada_prog"] += 1
            r["passada_feitas"] += feita
        elif D._int(l.get("data_id_programada")) == hid:
            hora = D._txt(l.get("hora_inicio"))
            if hora and hora <= agora_hhmm:
                r = r_(uid)
                r["hoje_devidas"] += 1
                r["hoje_feitas"] += feita
    for r in out.values():
        p = r["passada_prog"]
        r["passada_pct"] = round(100.0 * r["passada_feitas"] / p, 1) if p else None
    return out
