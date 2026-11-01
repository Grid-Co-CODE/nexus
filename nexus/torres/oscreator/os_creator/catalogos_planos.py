"""catalogos_planos.py: os planos da Performance guardados por ATIVO (31/10/2026, etapa 4 do canto central; tarefa 4.1).

Até 31/10/2026 cada usina escolhida na Performance relia os planos inversor por inversor (o `task_events_list` de cada ativo),
e o resumo do plano a cada clique. Agora o dono é este módulo, com as regras do `catalogos.py` (o prazo de 24 h, a cópia em
disco que o reinício lê sem pedir nada, o vencido que volta na hora e é relido por trás, o vazio que não fica guardado), mas
por chave: um item por ativo (`planos`) e um por plano e ativo (`detalhes`), com a renovação comum (`catalogos.renovar_por_tras`).

OS PLANOS FICAM POR ATIVO, e não por grupo de tarefas: o RPC é perguntado por `id_item` (os eventos são do ativo; o plano do
tracker mora só no generalizado, e a estação tem planos que o inversor não tem, `api.get_performance_alvos`), e nada no código
mostra dois ativos do mesmo `id_group_task` respondendo o mesmo. Guardar por grupo ofereceria a um ativo um plano que talvez
ele não tenha.

A hora, a geração e a thread de trás vêm do `catalogos` na hora da chamada (os testes trocam lá, e vale aqui).
"""
from __future__ import annotations

import copy
import logging
import os
import threading

import catalogos as _c

log = logging.getLogger("oscreator.catalogos")

# os planos guardados, por ativo: a carteira tem ~2.850 inversores e estações (~190 usinas). Medido com 8 planos por ativo e os
# nomes num objeto só (`_planos_enxutos`): ~5,7 MB na memória e 1,7 MB em disco com a carteira inteira; os de 7 dias sem uso saem
PLANOS_MAX = 3000
# os detalhes de plano (o resumo da Performance, um por usina e plano escolhidos; sem o `raw`): medido, ~25 KB cada com 30
# subtarefas, 3,6 MB com 150
DETALHES_MAX = 150
GUARDA_S = 7 * 24 * 3600        # o plano que ninguém pediu em 7 dias sai da cópia


def _por_chave_limpo() -> dict:
    # "renovando" e "tentou" são a vez de cada chave na renovação comum (`catalogos.renovar_por_tras`)
    return {"itens": {}, "boot": False, "renovando": set(), "tentou": {}, "leituras": 0, "erro": None, "erro_em": 0.0,
            "disco": {"lido": None, "gravado_em": 0.0, "erro": None}}


_PLANOS: dict = _por_chave_limpo()      # {"<id_item>:<id_group_task>": {"lido_em", "planos": [{id_task, description}]}}
_DETALHES: dict = _por_chave_limpo()    # {"<id_task>:<id_item>": {"lido_em", "detalhe": o get_plan_details sem o raw}}
_TRAVA_PLANOS = threading.Lock()
_TEXTOS: dict = {}


def chave_plano(id_item, id_group_task) -> str:
    return "%s:%s" % (id_item, id_group_task)


def configurado() -> None:
    """A pasta mudou (`catalogos.configurar`): o que ainda não tem nada na memória lê o disco na próxima vez."""
    with _TRAVA_PLANOS:
        for p in (_PLANOS, _DETALHES):
            if not p["itens"]:
                p["boot"] = False


def reiniciar() -> None:
    """O processo recém-subido (`catalogos.reiniciar`, que conta a geração antes de chamar): nada na memória."""
    with _TRAVA_PLANOS:
        for p in (_PLANOS, _DETALHES):
            p.clear()
            p.update(_por_chave_limpo())
        _TEXTOS.clear()


def _planos_enxutos(planos) -> list:
    """Os planos de um ativo como ficam guardados: o id e o nome, com UM objeto para cada nome (os mesmos ~30 nomes de plano se
    repetem em milhares de ativos: medido, 7,4 MB contra 5,7 MB com a carteira inteira)."""
    return [{"id_task": p.get("id_task"), "description": _TEXTOS.setdefault(p.get("description"), p.get("description"))
             if isinstance(p.get("description"), str) else p.get("description")} for p in planos if isinstance(p, dict)]


def _boot_por_chave(store: dict, nome: str, campo: str) -> None:
    if store["boot"]:
        return
    with _TRAVA_PLANOS:
        if store["boot"]:
            return
        store["boot"] = True
        arq = _c.arquivo(nome)
        if arq is None or not os.path.exists(arq):
            return
        try:
            carga = _c.ler_json(arq, nome)
            itens = carga.get("itens")
            if not isinstance(itens, dict):
                raise ValueError("sem os itens")
            bons = {k: v for k, v in itens.items() if isinstance(v, dict) and isinstance(v.get("lido_em"), (int, float))
                    and isinstance(v.get(campo), (list, dict))}
            for k, v in bons.items():
                if campo == "planos":
                    v = {"lido_em": v["lido_em"], "planos": _planos_enxutos(v["planos"])}
                store["itens"].setdefault(k, v)
            store["disco"]["lido"] = "cópia gravada em %s (%d)" % (_c.hora(carga.get("gravado_em")), len(bons))
        except (OSError, ValueError, TypeError, KeyError) as e:
            store["disco"]["erro"] = "ler: %s: %s" % (type(e).__name__, str(e)[:120])
            log.warning("catálogos: ignorei a cópia em disco de %s (%s)", nome, store["disco"]["erro"])


def _gravar_por_chave(store: dict, nome: str, maximo: int) -> None:
    """A cópia em disco dos planos (ou dos detalhes): os mais recentes até `maximo`, sem os de mais de 7 dias."""
    destino = _c.arquivo(nome)
    agora = _c.relogio()
    with _TRAVA_PLANOS:
        vivos = sorted(((k, v) for k, v in store["itens"].items() if agora - v["lido_em"] <= GUARDA_S),
                       key=lambda kv: kv[1]["lido_em"], reverse=True)[:maximo]
        store["itens"] = dict(vivos)
        carga = {"formato": _c.FORMATO, "nome": nome, "gravado_em": agora, "itens": dict(vivos)}
    if destino is None:
        return
    try:
        _c.escrever_json(destino, carga)
        store["disco"].update(gravado_em=agora, erro=None)
    except Exception as e:                                          # noqa: BLE001
        store["disco"]["erro"] = "gravar: %s: %s" % (type(e).__name__, str(e)[:120])
        log.warning("catálogos: não gravei a cópia de %s (%s)", nome, store["disco"]["erro"])


def _renovar_planos_por_tras(ativos: list) -> None:
    """Os planos vencidos destes ativos, relidos por trás com a sessão de quem os pediu (`catalogos.renovar_por_tras`), um ativo
    depois do outro; quem os pedir enquanto isso recebe os de antes. O que falha espera `ESPERA_TENTATIVA_S`."""
    import api
    por_chave = {chave_plano(a.get("id"), a.get("id_group_task")): a for a in ativos}
    mudou = [False]

    def ler_uma(ch, ger):
        a = por_chave[ch]
        try:
            planos = api.ler_planos_do_ativo(a.get("id"), a.get("id_group_task"))
        except Exception as e:                                       # noqa: BLE001 — fica o de antes
            with _TRAVA_PLANOS:
                _PLANOS["erro"], _PLANOS["erro_em"] = _c.motivo_do_erro(e), _c.relogio()
            return
        with _TRAVA_PLANOS:
            if ger != _c.geracao():
                return
            _PLANOS["leituras"] += 1
            if planos:
                _PLANOS["itens"][ch] = {"lido_em": _c.relogio(), "planos": _planos_enxutos(planos)}
            else:
                _PLANOS["itens"].pop(ch, None)                   # o ativo sem plano agora: sai, e a próxima escolha relê
            mudou[0] = True

    def depois():
        if mudou[0]:
            _gravar_por_chave(_PLANOS, "planos", PLANOS_MAX)
    _c.renovar_por_tras(_PLANOS, list(por_chave), ler_uma, trava=_TRAVA_PLANOS, depois=depois)


def planos_dos_ativos(ativos: list) -> dict:
    """{chave do ativo: [{'id_task','description'}]} dos planos de tarefa de cada ativo (o `task_events_list` por `id_item` e
    `id_group_task`, como o `api.get_plans_for_assets` lê), ou None no ativo cuja leitura falhou (o `api` o trata como "sem
    plano", como sempre). O que está guardado e em dia volta sem pedido nenhum; o vencido volta como está e é relido por trás;
    o que falta é lido agora, até 8 de uma vez, com a sessão de quem pediu (o executor do `api` leva o contexto). A lista vazia
    não fica guardada (pode ser a sessão sem a permissão). Grava a cópia em disco uma vez no fim."""
    import api
    _boot_por_chave(_PLANOS, "planos", "planos")
    agora = _c.relogio()
    out, faltam, vencidos = {}, [], []
    with _TRAVA_PLANOS:
        for a in ativos:
            ch = chave_plano(a.get("id"), a.get("id_group_task"))
            item = _PLANOS["itens"].get(ch)
            if item is None:
                faltam.append(a)
                continue
            out[ch] = item["planos"]
            if agora - item["lido_em"] > _c.PRAZO_S["planos"]:
                vencidos.append(a)
    if faltam:
        ger = _c.geracao()

        def ler(a):
            try:
                return a, api.ler_planos_do_ativo(a.get("id"), a.get("id_group_task"))
            except api.FracttalError as e:
                return a, e
        with api._ExecutorComContexto(max_workers=8) as ex:
            lidos = list(ex.map(ler, faltam))
        novos = 0
        with _TRAVA_PLANOS:
            for a, r in lidos:
                ch = chave_plano(a.get("id"), a.get("id_group_task"))
                if isinstance(r, Exception):
                    out[ch] = None
                    _PLANOS["erro"], _PLANOS["erro_em"] = _c.motivo_do_erro(r), _c.relogio()
                    continue
                out[ch] = r
                _PLANOS["leituras"] += 1
                if r and ger == _c.geracao():
                    _PLANOS["itens"][ch] = {"lido_em": _c.relogio(), "planos": _planos_enxutos(r)}
                    novos += 1
        if novos:
            _gravar_por_chave(_PLANOS, "planos", PLANOS_MAX)
    if vencidos:
        _renovar_planos_por_tras(vencidos)
    return {ch: ([dict(p) for p in v] if v is not None else None) for ch, v in out.items()}


def plano(id_item, id_group_task=None) -> list:
    """Os planos de UM ativo: [{'id_task','description'}] (vazio quando a leitura falhou ou ele não tem plano)."""
    v = planos_dos_ativos([{"id": id_item, "id_group_task": id_group_task}]).get(chave_plano(id_item, id_group_task))
    return v or []


def _renovar_detalhe_por_tras(ch: str, id_task, id_item) -> None:
    def ler_uma(_ch, ger):
        try:
            _ler_detalhe(ch, id_task, id_item, ger)
        except Exception as e:                                       # noqa: BLE001 — fica o de antes
            with _TRAVA_PLANOS:
                _DETALHES["erro"], _DETALHES["erro_em"] = _c.motivo_do_erro(e), _c.relogio()
    _c.renovar_por_tras(_DETALHES, [ch], ler_uma, trava=_TRAVA_PLANOS)


def _ler_detalhe(ch: str, id_task, id_item, ger: int) -> dict:
    import api
    det = {k: v for k, v in (api.get_plan_details(id_task, id_item) or {}).items() if k != "raw"}
    with _TRAVA_PLANOS:
        _DETALHES["leituras"] += 1
        guardar = bool(det.get("subtasks") or det.get("description")) and ger == _c.geracao()
        if guardar:
            _DETALHES["itens"][ch] = {"lido_em": _c.relogio(), "detalhe": det}
    if guardar:
        _gravar_por_chave(_DETALHES, "planos_detalhe", DETALHES_MAX)
    return det


def detalhe_do_plano(id_task, id_item) -> dict:
    """O detalhe de um plano para o resumo da Performance (o `api.get_plan_details`, SEM o `raw`: o resumo não o usa e ele
    repetiria as subtarefas na memória), em cópia. Guardado e em dia: sem pedido; vencido: volta e é relido por trás; sem
    ele: lido agora (o erro sobe, como antes)."""
    _boot_por_chave(_DETALHES, "planos_detalhe", "detalhe")
    ch = "%s:%s" % (id_task, id_item)
    with _TRAVA_PLANOS:
        item = _DETALHES["itens"].get(ch)
    if item is not None:
        if _c.relogio() - item["lido_em"] > _c.PRAZO_S["detalhes"]:
            _renovar_detalhe_por_tras(ch, id_task, id_item)
        return copy.deepcopy(item["detalhe"])
    try:
        return copy.deepcopy(_ler_detalhe(ch, id_task, id_item, _c.geracao()))
    except Exception as e:
        with _TRAVA_PLANOS:
            _DETALHES["erro"], _DETALHES["erro_em"] = _c.motivo_do_erro(e), _c.relogio()
        raise


def aquecer() -> None:
    """As cópias em disco dos planos e dos detalhes (o `catalogos.aquecer`, por trás, ao ligar a ponte)."""
    _boot_por_chave(_PLANOS, "planos", "planos")
    _boot_por_chave(_DETALHES, "planos_detalhe", "detalhe")


def estado() -> tuple:
    """(planos, detalhes) para o `catalogos.estado()`: quantos, o mais velho e o mais novo, os vencidos, os renovando, as
    leituras do Fracttal neste processo, a última falha e a cópia em disco. Faz o boot do disco (o Raio-X depois de um deploy)."""
    agora = _c.relogio()

    def por_chave(store, nome, campo, prazo):
        _boot_por_chave(store, nome, campo)
        with _TRAVA_PLANOS:
            idades = [v["lido_em"] for v in store["itens"].values()]
            return {"n": len(store["itens"]), "mais_velho": min(idades) if idades else None,
                    "mais_novo": max(idades) if idades else None,
                    "vencidos": sum(1 for t in idades if agora - t > prazo), "prazo_s": prazo,
                    "renovando": len(store["renovando"]), "leituras": store["leituras"], "erro": store["erro"],
                    "erro_em": store["erro_em"] or None, "disco": dict(store["disco"])}
    return (por_chave(_PLANOS, "planos", "planos", _c.PRAZO_S["planos"]),
            por_chave(_DETALHES, "planos_detalhe", "detalhe", _c.PRAZO_S["detalhes"]))
