"""As OS da equipe de engenharia, para o quadro da torre Engenharia (Levi, 06/10/2026: "uma tela que fique no setor de
engenharia que agregue todas as OSs que estão abertas ou já foram fechadas ou que serão abertas para essas pessoas";
"FAÇA UMA TELA DINÂMICA, ESTILO KANBAN E SUPERCARDS, DEIXE ALGO BOM DE GERENCIAR!").

Quem é da equipe: os mesmos nomes da Nova solicitação | Engenharia do OS Creator (`OS_WEB_ENGENHARIA_RESPONSAVEIS`, no
.env do OS Creator, separados por ";"; o repositório é público, então os nomes não ficam no código). `NEXUS_ENGENHARIA_
RESPONSAVEIS` no .env do Nexus vale por cima, se existir.

Leitura (medido em 06/10): o REST filtra OS pelo nome do responsável (`personnel_description`, por trecho: "Fulano" acha
"Fulano de Tal"), mas IGNORA `id_personnel`. Então: cada nome vira a pessoa do Fracttal pela lista `personnel` (150
pessoas, guardada 24 h; nome igual ou começando pelo nome do .env, só se for UMA), e as OS vêm pelo nome e são
conferidas pelo `id_personnel` dela (um homônimo não entra). Os 6 somavam 55 linhas: ~8 pedidos por leitura, guardada
5 min. Nada vai para o banco.

As linhas do REST são por TAREFA; o quadro é por OS (o número), com as tarefas dentro. Coluna:
- Canceladas = status 4; Concluídas = 3; Em verificação = 2;
- status 1: Em execução se alguma tarefa já começou e não terminou; senão A fazer (a data programada diz se atrasou,
  se vence logo ou se ainda vai abrir: "que serão abertas").
"""
import os
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

BRT = timezone(timedelta(hours=-3))
VALIDADE_S = 300
FORCAR_S = 5               # a releitura pedida pelo card (ver `pedir_releitura`) não passa de uma a cada 5 s
PESSOAS_S = 24 * 3600
# O quadro pronto enquanto alguém o usa (Levi, 09/10/2026: "talvez um carregamento periódico que carregue em segundo
# plano e deixe todos prontos"): a cada minuto, se alguém abriu o quadro nas últimas 2 h e a cópia passou dos 5 min,
# ela é relida por trás (`manter_quente`). ~8 pedidos a cada 5 min = ~1,6 por minuto, menos de 1% da cota da empresa
# (200/min); ninguém em 2 h, para, e volta na próxima visita.
USO_S = 2 * 3600
QUENTE_S = 60
OS_URL = "https://one.fracttal.com/tasks/wo/{id}"
# O nome do status como o OS Creator escreve (`api.WO_STATUS` do clone; o teste confere que são iguais). O card da OS do
# OS Creator, aberto pelo quadro, recebe o status pelo endereço, como na linha do Histórico: é dele que sai o selo e a
# regra do "Editar" das notas (Levi, 08/10/2026: "Ao clicar na OS quero que abra o mesmo card ... do histórico").
STATUS_OS = {1: "Em Processo", 2: "Em Verificação", 3: "Concluída", 4: "Cancelada"}
COLUNAS = (("fazer", "A fazer"), ("execucao", "Em execução"), ("verificacao", "Em verificação"),
           ("concluida", "Concluídas"), ("cancelada", "Canceladas"))
_EST = {"ts": 0.0, "pessoas_ts": 0.0, "pessoas": [], "os": [], "lendo": False, "erro": "", "erro_em": 0.0, "faltam": [],
        "usado": 0.0}
_TRAVA = threading.Lock()


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _ler_fracttal(path):
    from ..campo import fracttal
    return fracttal.ler(path)


def nomes(config) -> list[str]:
    bruto = config.get("NEXUS_ENGENHARIA_RESPONSAVEIS")
    if not bruto:
        from dotenv import dotenv_values

        from ..torres.oscreator.ponte import RAIZ_CLONE
        bruto = dotenv_values(os.path.join(RAIZ_CLONE, ".env")).get("OS_WEB_ENGENHARIA_RESPONSAVEIS") or ""
    return [n.strip() for n in str(bruto).split(";") if n.strip()]


def casar(nome: str, pessoas: list[dict]) -> dict | None:
    """A pessoa do Fracttal com esse nome: igual, ou começando por ele. Só se for UMA (homônimo não chuta)."""
    alvo = _norm(nome)
    iguais = [p for p in pessoas if alvo in (_norm(p.get("name")), _norm(p.get("full_name")))]
    achados = iguais or [p for p in pessoas if _norm(p.get("name")).startswith(alvo) or _norm(p.get("full_name")).startswith(alvo)]
    return achados[0] if len(achados) == 1 else None


def _paginas(path):
    out, inicio = [], 0
    while True:
        r = _ler_fracttal(f"{path}&limit=100&start={inicio}")
        d = (r.get("data") if isinstance(r, dict) else r) or []
        out += d
        if len(d) < 100:
            return out
        inicio += 100


def _dt(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def coluna(status, tarefas: list[dict]) -> str:
    st = int(status or 0)
    if st == 4:
        return "cancelada"
    if st == 3:
        return "concluida"
    if st == 2:
        return "verificacao"
    comecou = any((t.get("task_status") not in ("NO_STARTED", "DONE", None, "")) or (t.get("initial_date") and t.get("task_status") != "DONE")
                  for t in tarefas)
    return "execucao" if comecou else "fazer"


def montar(linhas: list[dict], pessoa: dict, agora: datetime) -> list[dict]:
    """As OS (uma por número) de uma pessoa, com as tarefas dentro, a coluna e o prazo."""
    por = {}
    for w in linhas:
        if str(w.get("id_personnel")) != str(pessoa["id"]):
            continue
        por.setdefault(str(w.get("wo_folio") or w.get("id_work_order")), []).append(w)
    hoje = agora.astimezone(BRT).date()
    out = []
    for folio, ts in por.items():
        w0 = ts[0]
        col = coluna(w0.get("id_status_work_order"), ts)
        prog = min((d for d in (_dt(t.get("date_maintenance")) for t in ts) if d), default=None)
        fim = max((d for d in (_dt(t.get("wo_final_date") or t.get("final_date")) for t in ts) if d), default=None)
        criada = _dt(w0.get("creation_date"))
        dias = (prog.astimezone(BRT).date() - hoje).days if prog else None
        prazo = ("atrasada" if dias is not None and dias < 0 and col in ("fazer", "execucao") else
                 "vence" if dias is not None and dias <= 2 and col in ("fazer", "execucao") else
                 "futura" if dias is not None and dias > 2 and col == "fazer" else "")
        etiquetas = []
        for t in ts:
            for e in t.get("labels") or []:
                if isinstance(e, dict) and e.get("enabled", True) and e.get("description") and \
                        e["description"] not in [x["nome"] for x in etiquetas]:
                    etiquetas.append({"nome": e["description"], "cor": "#" + str(e.get("color") or "8892a6").lstrip("#")})
        try:
            status = STATUS_OS.get(int(w0.get("id_status_work_order") or 0), "")
        except (TypeError, ValueError):
            status = ""
        out.append({
            "os": folio, "url": OS_URL.format(id=w0["id_work_order"]) if w0.get("id_work_order") else "",
            # o id da OS abre o card do OS Creator (/os/os/<id>); o REST já traz, sem pedido a mais ao Fracttal
            "wid": w0.get("id_work_order"), "status": status,
            "titulo": str(w0.get("description") or "").strip()[:140], "pessoa": pessoa["nome"], "pid": pessoa["id"],
            "coluna": col, "tipo": str(w0.get("tasks_log_task_type_main") or ""),
            "ativo": str(w0.get("items_log_description") or "").split("{")[0].strip()[:80], "codigo": str(w0.get("code") or ""),
            "usina": str(w0.get("groups_1_description") or ""), "prioridade": str(w0.get("priorities_description") or ""),
            "etiquetas": etiquetas, "prazo": prazo, "dias": dias,
            "programada": prog.astimezone(BRT).strftime("%d/%m/%Y") if prog else "",
            "programada_iso": prog.astimezone(BRT).date().isoformat() if prog else "",
            "criada": criada.astimezone(BRT).strftime("%d/%m/%Y %H:%M") if criada else "",
            "fim": fim.astimezone(BRT).strftime("%d/%m/%Y") if fim else "",
            "fim_iso": fim.astimezone(BRT).date().isoformat() if fim else "",
            "solicitante": str(w0.get("requested_by") or w0.get("created_by") or "").strip(),
            "nota": str(w0.get("note") or "").strip()[:600],
            "tarefas": [{"t": str(t.get("description") or "")[:120], "st": str(t.get("task_status") or ""),
                         "obs": str(t.get("task_note") or "").strip()[:300]} for t in ts]})
    return out


def _reler(app):
    a = _EST
    try:
        with app.app_context():
            lista = nomes(app.config)
            if time.time() - a["pessoas_ts"] > PESSOAS_S or not a["pessoas"]:
                a["pessoas"] = _paginas("personnel?x=1")
                a["pessoas_ts"] = time.time()
            agora = datetime.now(timezone.utc)
            todas, faltam = [], []
            equipe = []
            for n in lista:
                p = casar(n, a["pessoas"])
                if not p:
                    faltam.append(n)
                    continue
                pessoa = {"id": p.get("id_personnel"), "nome": n,
                          "nome_fracttal": " ".join(str(p.get("name") or p.get("full_name") or n).split())}
                equipe.append(pessoa)
                todas += montar(_paginas(f"work_orders?personnel_description={quote(n)}"), pessoa, agora)
                time.sleep(0.3)
            a.update(os=todas, equipe=equipe, faltam=faltam, ts=time.time(), erro="", erro_em=0.0)
    except Exception as e:      # noqa: BLE001 — 429 ou rede: fica a leitura anterior
        a.update(erro=str(e)[:160], erro_em=time.time())
    finally:
        a["lendo"] = False


def pedir_releitura(app=None, esperar=False, forcar=False):
    """Relê se a cópia tem mais de 5 min. Sem nenhuma cópia ainda, `esperar` lê na hora (são ~8 pedidos).

    `forcar`: relê mesmo com a cópia nova (se tiver mais de FORCAR_S). É o que o quadro pede depois que alguém mudou uma
    OS pelo card do OS Creator aberto nele (concluir, trocar o responsável...): sem isso, a OS ficaria até 5 min na
    coluna velha."""
    if time.time() - _EST["ts"] < (FORCAR_S if forcar else VALIDADE_S):
        return
    with _TRAVA:
        if _EST["lendo"] or time.time() - _EST["erro_em"] < 60:
            return
        _EST["lendo"] = True
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()
    if esperar or app.config.get("TESTING"):
        _reler(app)
    else:
        threading.Thread(target=_reler, args=(app,), daemon=True, name="nexus-os-equipe").start()


def marcar_uso():
    """A tela foi aberta agora: o `manter_quente` segue relendo por trás pelas próximas 2 h."""
    _EST["usado"] = time.time()


def _tique(app, agora: float | None = None) -> bool:
    """Uma volta do `manter_quente`: relê por trás se alguém abriu o quadro nas últimas 2 h e a cópia passou dos 5 min.
    Pelo `forcar` do `pedir_releitura` (o piso dele, FORCAR_S, e a espera depois de um erro valem igual). True se
    pediu."""
    agora = time.time() if agora is None else agora
    if not _EST["usado"] or agora - _EST["usado"] > USO_S:
        return False
    if _EST["ts"] and agora - _EST["ts"] < VALIDADE_S:
        return False
    pedir_releitura(app, forcar=True)
    return True


def manter_quente(app):
    """Liga, numa thread, a volta de cada minuto (`_tique`). Quem chama é o `instalar` (app.py e servir.py), nunca o
    create_app: teste não fala com a rede."""
    def laco():
        while True:
            time.sleep(QUENTE_S)
            try:
                _tique(app)
            except Exception:       # noqa: BLE001 — a volta seguinte tenta de novo; a tela relê na visita
                pass
    threading.Thread(target=laco, daemon=True, name="nexus-os-equipe-quente").start()


def dados() -> dict:
    return {"os": list(_EST["os"]), "equipe": list(_EST.get("equipe") or []), "faltam": list(_EST["faltam"]),
            "lido": _EST["ts"], "lendo": _EST["lendo"], "erro": _EST["erro"]}


def limpar():
    _EST.update(ts=0.0, pessoas_ts=0.0, pessoas=[], os=[], equipe=[], lendo=False, erro="", erro_em=0.0, faltam=[],
                usado=0.0)
