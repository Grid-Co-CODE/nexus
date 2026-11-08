"""A OS para o cliente ver, só leitura (08/11/2026, Levi: "Gostaria também que todas as OSs fossem clicáveis para
visualização porém não terá a opção de editar nada da OS, dessa forma sendo possível até ver sem acessar o fractall").

Sai do BANCO (`nexus_os · fato_tarefa_os`, o retrato das OS do Fracttal que o Nexus já guarda), nunca do Fracttal: o
cliente não tem login lá, e cada clique dele não gasta a cota da empresa (200 por minuto). O retrato tem as OS em
processo e em verificação (e a zeladoria finalizada de 90 dias): a OS concluída e conferida já saiu dele, e a tela diz
isso, sem inventar o resto (nexus: "sem dado não se inventa").

O que vai: o número, a usina, o tipo, a situação (a mesma régua da Visão do cliente), quando abriu, a programação, a
conclusão e cada ativo com a situação dele. O que NÃO vai: quem fez, horas, custo, comentário interno.
"""
from datetime import date

from ..dados import fatos as D
from . import visao

# os estados da tarefa no retrato (`campo/manutencao._COMECOU`): em_progresso, pausada, finalizada; o resto, a fazer
_SITUACAO_TAREFA = {"finalizada": ("feito", "ok"), "em_progresso": ("em execução", "info"), "pausada": ("pausada", "alerta")}
_TIPO = {"corretiva": "Corretiva", "preventiva": "Preventiva", "preditiva": "Preditiva", "zeladoria": "Zeladoria",
         "inspecao": "Inspeção", "ronda": "Ronda", "melhoria": "Melhoria"}


def _dia(v) -> date | None:
    try:
        n = int(v)
        return date(n // 10000, n // 100 % 100, n % 100)
    except (TypeError, ValueError):
        return None


def os_do_cliente(numero: int, usinas: set[int] | None) -> dict | None:
    """A OS `numero` para o cartão, ou None quando não existe no retrato ou é de usina fora de `usinas` (o cliente nunca
    vê a OS de outro; None em `usinas` = a Grid, que vê todas)."""
    from ..dados import fato_tarefa_os as FT
    tarefas = [t for t in visao._livro(FT.LIVRO, FT.ABA) if D._id(t.get("os")) == numero]
    if not tarefas:
        return None
    uids = {D._id(t.get("usina_id")) for t in tarefas} - {None}
    if usinas is not None and (not uids or not uids <= usinas):
        return None
    try:
        b = visao._Base()
        nome_usina = " · ".join(sorted(str((b.por_id.get(u) or {}).get("nome") or "") for u in uids if u))
    except Exception:            # noqa: BLE001 — sem o cadastro, o cartão segue sem o nome
        nome_usina = ""
    status = {D._txt(t.get("status_os")) for t in tarefas}
    estados = [D._txt(t.get("estado_tarefa")) for t in tarefas]
    if "em_verificacao" in status:
        sit, tom = "concluída, em conferência da Grid", "ok"
    elif all(e == "finalizada" for e in estados):
        sit, tom = "concluída", "ok"
    elif any(e in ("em_progresso", "pausada", "finalizada") for e in estados):
        sit, tom = "em execução", "info"
    else:
        sit, tom = "aguardando execução", "alerta"
    ativos = []
    for t in sorted(tarefas, key=lambda x: (str(x.get("codigo_ativo") or ""), D._int(x.get("data_id_programada")) or 0)):
        rot, tm = _SITUACAO_TAREFA.get(D._txt(t.get("estado_tarefa")), ("a fazer", "alerta"))
        ativos.append({"ativo": D._txt(t.get("codigo_ativo")) or "Usina", "situacao": rot, "tom": tm,
                       "programada": _dia(t.get("data_id_programada")), "fim": _dia(t.get("data_id_fim"))
                       if D._txt(t.get("estado_tarefa")) == "finalizada" else None})
    datas = lambda campo: [d for d in (_dia(t.get(campo)) for t in tarefas) if d]   # noqa: E731
    fins = datas("data_id_fim") if all(e == "finalizada" for e in estados) else []
    tipos = sorted({_TIPO.get(D._txt(t.get("tipo_tarefa")), D._txt(t.get("tipo_tarefa")).capitalize())
                    for t in tarefas if D._txt(t.get("tipo_tarefa"))})
    return {"os": numero, "usina": nome_usina, "tipo": " · ".join(tipos) or "OS", "situacao": sit, "tom": tom,
            "aberta": min(datas("data_id_criacao"), default=None), "programada": min(datas("data_id_programada"),
                                                                                     default=None),
            "concluida": max(fins, default=None), "ativos": ativos}
