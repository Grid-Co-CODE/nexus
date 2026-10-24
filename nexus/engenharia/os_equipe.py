"""As OS da equipe de engenharia, para o quadro da torre Engenharia (Levi, 06/10/2026: "uma tela que fique no setor de
engenharia que agregue todas as OSs que estão abertas ou já foram fechadas ou que serão abertas para essas pessoas";
"FAÇA UMA TELA DINÂMICA, ESTILO KANBAN E SUPERCARDS, DEIXE ALGO BOM DE GERENCIAR!").

Quem é da equipe: os mesmos nomes da Nova solicitação | Engenharia do OS Creator (`OS_WEB_ENGENHARIA_RESPONSAVEIS`, no
.env do OS Creator, separados por ";"; o repositório é público, então os nomes não ficam no código). `NEXUS_ENGENHARIA_
RESPONSAVEIS` no .env do Nexus vale por cima, se existir.

Leitura (medido em 06/10): o REST filtra OS pelo nome do responsável (`personnel_description`, por trecho: "Fulano" acha
"Fulano de Tal"; e literal: um espaço a mais já não casa), mas IGNORA `id_personnel`. Então: cada nome vira a pessoa do Fracttal pela lista `personnel` (150
pessoas, guardada 24 h; nome igual ou começando pelo nome do .env, só se for UMA), e as OS vêm pelo nome e são
conferidas pelo `id_personnel` dela (um homônimo não entra). Os 6 somavam 55 linhas: ~8 pedidos por leitura, guardada
5 min. Nada vai para o banco.

As linhas do REST são por TAREFA; o quadro é por OS (o número), com as tarefas dentro. Coluna:
- Canceladas = status 4; Concluídas = 3; Em verificação = 2;
- status 1: Em execução se alguma tarefa já começou e não terminou; senão A fazer (a data programada diz se atrasou,
  se vence logo ou se ainda vai abrir: "que serão abertas").
"""
import json
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


def grafias(nome: str, p: dict) -> list[str]:
    """Os trechos que vão ao filtro do REST: o nome do .env e o nome como o Fracttal escreve hoje (`name`/`full_name`,
    com os espaços dele), sem o que um trecho mais curto já cobre. Caso real (18/10/2026): o Fracttal passou a escrever o
    nome de um engenheiro com dois espaços, e o nome do .env (um espaço) só achava as OS antigas, de quando ele era
    escrito com um; as OS abertas para ele na semana não apareciam no quadro. As linhas seguem conferidas pelo
    `id_personnel` (em `montar`)."""
    candidatos = []
    for g in (nome, p.get("name"), p.get("full_name")):
        g = str(g or "").strip()
        if g and g not in candidatos:
            candidatos.append(g)
    out = []
    for g in sorted(candidatos, key=len):
        if not any(o in g for o in out):
            out.append(g)
    return out


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
    return [_cartao(folio, ts, pessoa, hoje) for folio, ts in por.items()]


def _nota_da_os(ts: list[dict]) -> str:
    """A nota da OS como o card do OS Creator a lê (`api.get_os_detalhes`): a de cada tarefa (`task_note`, senão a
    `note`), sem repetir. Caso real (24/10/2026, Levi: "não está puxando a nota da OS da engenharia"): a página mostrava
    só a `note`, e a nota das OS da engenharia mora na tarefa."""
    vistas = []
    for t in ts:
        n = str(t.get("task_note") or t.get("note") or "").strip()
        if n and n not in vistas:
            vistas.append(n)
    return "\n".join(vistas)


def _cartao(folio: str, ts: list[dict], pessoa: dict, hoje) -> dict:
    """Uma OS (as linhas das tarefas dela) no formato do quadro."""
    w0 = ts[0]
    col = coluna(w0.get("id_status_work_order"), ts)
    prog = min((d for d in (_dt(t.get("date_maintenance")) for t in ts) if d), default=None)
    fim = max((d for d in (_dt(t.get("wo_final_date") or t.get("final_date")) for t in ts) if d), default=None)
    criada = _dt(w0.get("creation_date"))
    # o que se mexeu na OS no Fracttal: o começo e o fim das tarefas (a "última atualização" da página da OS e o
    # pulso do quadro, junto com o que a Engenharia gravou no Nexus; 24/10/2026)
    atividade = max((d for t in ts for d in (_dt(t.get("initial_date")), _dt(t.get("final_date")),
                                             _dt(t.get("wo_final_date"))) if d), default=None)
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
    return {
        "os": folio, "url": OS_URL.format(id=w0["id_work_order"]) if w0.get("id_work_order") else "",
        # o id da OS: a ponte do comentário na nota e o OS pai do Solicitar OS; o REST já traz, sem pedido a mais
        "wid": w0.get("id_work_order"), "status": status,
        "titulo": str(w0.get("description") or "").strip()[:140], "pessoa": pessoa["nome"], "pid": pessoa["id"],
        "coluna": col, "tipo": str(w0.get("tasks_log_task_type_main") or ""),
        "ativo": str(w0.get("items_log_description") or "").split("{")[0].strip()[:80], "codigo": str(w0.get("code") or ""),
        "usina": str(w0.get("groups_1_description") or ""), "prioridade": str(w0.get("priorities_description") or ""),
        "etiquetas": etiquetas, "prazo": prazo, "dias": dias,
        "programada": prog.astimezone(BRT).strftime("%d/%m/%Y") if prog else "",
        "programada_iso": prog.astimezone(BRT).date().isoformat() if prog else "",
        "criada": criada.astimezone(BRT).strftime("%d/%m/%Y %H:%M") if criada else "",
        "criada_iso": criada.isoformat() if criada else "", "atividade_iso": atividade.isoformat() if atividade else "",
        "prioridade_fracttal": str(w0.get("priorities_description") or ""),
        "fim": fim.astimezone(BRT).strftime("%d/%m/%Y") if fim else "",
        "fim_iso": fim.astimezone(BRT).date().isoformat() if fim else "",
        "solicitante": str(w0.get("requested_by") or w0.get("created_by") or "").strip(),
        "nota": _nota_da_os(ts)[:600],
        "tarefas": [{"t": str(t.get("description") or "")[:120], "st": str(t.get("task_status") or ""),
                     "obs": str(t.get("task_note") or "").strip()[:300]} for t in ts]}


# ── a página da OS do quadro (24/10/2026): a OS lida agora, as filhas e a resposta do técnico ─────────────────────────
TETO_PAGINAS = 3              # um filtro que o REST passasse a ignorar não pode virar a leitura do Fracttal inteiro


def _paginas_ate(path, teto=TETO_PAGINAS):
    out, inicio = [], 0
    for _ in range(teto):
        r = _ler_fracttal(f"{path}&limit=100&start={inicio}")
        d = (r.get("data") if isinstance(r, dict) else r) or []
        out += d
        if len(d) < 100:
            break
        inicio += 100
    return out


def ler_os(folio) -> dict | None:
    """A OS pelo nº, lida agora no REST (só leitura): o formato do quadro, sem filtro de pessoa (as tarefas de todos) e
    com a nota inteira. None quando o Fracttal não tem esse nº."""
    f = str(int(folio))
    linhas = [w for w in _paginas_ate(f"work_orders?wo_folio={f}") if str(w.get("wo_folio")) == f]
    if not linhas:
        return None
    w0 = linhas[0]
    nome = " ".join(str(w0.get("personnel_description") or "").split())
    o = _cartao(f, linhas, {"id": w0.get("id_personnel"), "nome": nome}, datetime.now(timezone.utc).astimezone(BRT).date())
    o["nota"] = _nota_da_os(linhas)
    return o


def filhas(wid) -> list[dict]:
    """As OS que nasceram com esta como OS pai (o REST filtra por `id_parent_wo`, medido em 24/10/2026), uma por nº."""
    if not wid:
        return []
    linhas = [w for w in _paginas_ate(f"work_orders?id_parent_wo={int(wid)}")
              if str(w.get("id_parent_wo")) == str(int(wid))]
    por: dict = {}
    for w in linhas:
        por.setdefault(str(w.get("wo_folio") or w.get("id_work_order")), []).append(w)
    hoje = datetime.now(timezone.utc).astimezone(BRT).date()
    out = []
    for f, ts in por.items():
        nome = " ".join(str(ts[0].get("personnel_description") or "").split())
        out.append(_cartao(f, ts, {"id": ts[0].get("id_personnel"), "nome": nome}, hoje))
    return sorted(out, key=lambda o: int(o["os"]) if str(o["os"]).isdigit() else 0)


ATIVIDADE = "descreva a atividade realizada"     # a subtarefa de toda OS que nasce de uma solicitação (solic_spec.BASE)


def resposta_da_atividade(folio) -> dict:
    """A resposta de "Descreva a atividade realizada" de uma OS: {"tem": a subtarefa existe, "resposta": o texto}."""
    subs = _paginas_ate(f"work_orders_subtasks/?folio={int(folio)}")
    achadas = [s for s in subs if _norm(s.get("description")) == ATIVIDADE]
    textos = [str(s.get("value") or "").strip() for s in achadas if str(s.get("value") or "").strip()]
    return {"tem": bool(achadas), "resposta": " / ".join(textos)}


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
                linhas, vistas = [], set()
                for g in grafias(n, p):
                    for w in _paginas(f"work_orders?personnel_description={quote(g)}"):
                        chave = json.dumps(w, sort_keys=True, default=str)   # a mesma linha por dois trechos entra uma vez
                        if chave not in vistas:
                            vistas.add(chave)
                            linhas.append(w)
                    time.sleep(0.3)
                todas += montar(linhas, pessoa, agora)
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
