"""As OS de falha do Fracttal, lidas pelo Nexus (06/10/2026): a fonte da tela Engenharia > Confiabilidade.

O REST filtra pelo tipo da tarefa (`tasks_log_task_type_main`), e é isso que deixa a leitura leve: medido em 06/10, a
conta tem 37.960 linhas de OS, e os quatro tipos de falha somam 13.666 (Corretiva 6.189, Corretiva Emergencial 954,
Religamento 4.789, Religamento Remoto 1.734). Data não filtra no REST, mas ordena. Então, por tipo:
- as VIVAS (status 1, em processo, e 2, em verificação) são relidas inteiras a cada passada (~2.100 linhas, ~23
  páginas), porque mudam;
- as CONCLUÍDAS (status 3) não mudam mais: a primeira leitura vai até o início do método (20/10/2025) e fica no
  arquivo; depois, ordenadas pela data de fim, só se leem as que fecharam desde a última leitura completa (menos 3
  dias de margem), 1 ou 2 páginas. Se o Fracttal recusar no meio (429), o que veio fica e a próxima continua de
  onde parou (o mesmo desenho das rondas aprovadas, `nexus/campo/ronda_checklist.py`);
- as CANCELADAS (status 4) ficam fora (o método do Power BI as tira).

O arquivo é `<pasta de dados>/engenharia/os_falhas.json` (fora do git), só com os campos que as contas usam. Nada vai
para o banco nesta fase. Releitura no máximo a cada 30 min, em segundo plano, com 1 s entre páginas (a cota do
Fracttal é de 200 pedidos/min para a empresa toda).
"""
import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

TIPOS = ("Corretiva", "Corretiva Emergencial", "Religamento", "Religamento Remoto")
INICIO_METODO = "2025-10-20"        # DataInicioSistema do Power BI
VALIDADE_S = 1800
ESPERA_APOS_ERRO_S = 300
MARGEM_DIAS = 3
PAGINAS_MAX = 400
PAUSA_S = 1.0                # 1 pedido por segundo, como o robô do PCM no Actions
CAMPOS = ("wo_folio", "id_work_order", "id_work_orders_tasks", "code", "items_log_description", "groups_1_description",
          "groups_2_description", "parent_description", "tasks_log_task_type_main", "description", "creation_date",
          "initial_date", "final_date", "event_date", "task_status", "id_status_work_order", "priorities_description",
          "requested_by", "created_by", "personnel_description", "id_item")
_EST = {"concluidas": {}, "vivas": {}, "ate": {}, "retomar": {}, "topo": {}, "ts": 0.0, "vivas_em": 0.0,
        "lendo": False, "erro": "", "erro_em": 0.0, "carregado": False}
_TRAVA = threading.Lock()


def _ler_fracttal(path):
    from ..campo import fracttal
    return fracttal.ler(path)


def _linha(w: dict) -> dict:
    d = {k: w.get(k) for k in CAMPOS}
    d["task_note"] = str(w.get("task_note") or "")[:300]
    return d


def _chave(w: dict) -> str:
    return str(w.get("id_work_orders_tasks") or f"{w.get('id_work_order')}|{w.get('description')}")


def _arquivo():
    from flask import current_app, has_app_context
    if not has_app_context():
        return None
    from ..cadastro.ligacoes import pasta_dados
    try:
        return pasta_dados(current_app.config) / "engenharia" / "os_falhas.json"
    except RuntimeError:            # teste sem pasta própria: só em memória
        return None


def _carregar():
    with _TRAVA:
        if _EST["carregado"]:
            return
        arq = _arquivo()
        if arq is None:
            return
        _EST["carregado"] = True
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for k in ("concluidas", "vivas", "ate", "retomar", "topo"):
            _EST[k] = d.get(k) or {}
        _EST["vivas_em"] = float(d.get("vivas_em") or 0)
        _EST["ts"] = time.time() if all(_EST["ate"].get(t) for t in TIPOS) else 0.0


def _gravar():
    arq = _arquivo()
    if arq is None:
        return
    corpo = {k: _EST[k] for k in ("concluidas", "vivas", "ate", "retomar", "topo", "vivas_em")}
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(corpo, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, arq)
    except OSError as e:
        logging.warning("os de falha: não gravei o arquivo (%s)", e)


def _paginas(path_base: str, para=None):
    """Lê as páginas de `path_base` (com &start=); `para(pagina)` True encerra. Devolve as linhas."""
    out, inicio, n = [], 0, 0
    for _ in range(PAGINAS_MAX):
        if n:
            time.sleep(PAUSA_S)
        r = _ler_fracttal(f"{path_base}&limit=100&start={inicio}")
        pagina = (r.get("data") if isinstance(r, dict) else r) or []
        n += 1
        out += pagina
        if len(pagina) < 100 or (para and para(pagina)):
            break
        inicio += 100
    return out


def _reler_concluidas(tipo: str):
    """As concluídas de um tipo, pela data de fim, da mais nova para trás."""
    a = _EST
    hoje = datetime.now(timezone.utc).date()
    piso = INICIO_METODO
    if a["ate"].get(tipo):
        piso = max(piso, (date.fromisoformat(a["ate"][tipo]) - timedelta(days=MARGEM_DIAS)).isoformat())
        inicio, topo = 0, ""
    else:
        inicio = int(a["retomar"].get(tipo) or 0)
        topo = a["topo"].get(tipo, "") if inicio else ""
    base = f"work_orders?tasks_log_task_type_main={quote(tipo)}&id_status_work_order=3&sort=final_date:desc"
    for _ in range(PAGINAS_MAX):
        r = _ler_fracttal(f"{base}&limit=100&start={inicio}")
        pagina = (r.get("data") if isinstance(r, dict) else r) or []
        for w in pagina:
            a["concluidas"][_chave(w)] = _linha(w)
        datas = [str(w.get("final_date") or "")[:10] for w in pagina if w.get("final_date")]
        if datas and not topo:
            topo = max(datas)
        if len(pagina) < 100 or (datas and max(datas) < piso):
            break
        inicio += 100
        if not a["ate"].get(tipo):
            a["retomar"][tipo], a["topo"][tipo] = max(0, inicio - 100), topo   # uma página antes: as novas empurram
        time.sleep(PAUSA_S)
    a["ate"][tipo] = topo or a["ate"].get(tipo) or hoje.isoformat()
    a["retomar"].pop(tipo, None)
    a["topo"].pop(tipo, None)


def _reler():
    _carregar()
    a = _EST
    try:
        vivas = {}
        for tipo in TIPOS:
            for st in (1, 2):
                for w in _paginas(f"work_orders?tasks_log_task_type_main={quote(tipo)}&id_status_work_order={st}"):
                    vivas[_chave(w)] = _linha(w)
        a["vivas"], a["vivas_em"] = vivas, time.time()
        for tipo in TIPOS:
            _reler_concluidas(tipo)
        # a que fechou sai das vivas (vem nas concluídas); a cancelada some das duas
        for k in list(a["concluidas"]):
            a["vivas"].pop(k, None)
        a.update(ts=time.time(), erro="", erro_em=0.0)
        logging.info("os de falha: %d vivas, %d concluídas", len(a["vivas"]), len(a["concluidas"]))
    except Exception as e:      # noqa: BLE001 — 429 ou rede: fica o que já veio, e tenta de novo depois
        a.update(erro=str(e)[:160], erro_em=time.time())
        logging.warning("os de falha: leitura parou (%s); %d concluídas guardadas", str(e)[:120], len(a["concluidas"]))
    finally:
        _gravar()
        a["lendo"] = False


def pedir_releitura(app=None):
    if time.time() - _EST["ts"] < VALIDADE_S:
        return
    with _TRAVA:
        if _EST["lendo"] or time.time() - _EST["erro_em"] < ESPERA_APOS_ERRO_S:
            return
        _EST["lendo"] = True
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()

    def rodar():
        with app.app_context():
            _reler()
    if app.config.get("TESTING"):
        rodar()
    else:
        threading.Thread(target=rodar, daemon=True, name="nexus-os-falhas").start()


def linhas() -> list[dict]:
    """Todas as OS de falha que o Nexus tem (concluídas e vivas, sem as canceladas)."""
    _carregar()
    out = dict(_EST["concluidas"])
    out.update(_EST["vivas"])
    return list(out.values())


def estado() -> dict:
    """completa = as concluídas de todos os tipos já foram lidas até o início do método ao menos uma vez."""
    return {"lendo": _EST["lendo"], "erro": _EST["erro"], "completa": all(_EST["ate"].get(t) for t in TIPOS),
            "n": len(_EST["concluidas"]) + len(_EST["vivas"]), "vivas_em": _EST["vivas_em"]}


def limpar():
    _EST.update(concluidas={}, vivas={}, ate={}, retomar={}, topo={}, ts=0.0, vivas_em=0.0, lendo=False, erro="",
                erro_em=0.0, carregado=False)
