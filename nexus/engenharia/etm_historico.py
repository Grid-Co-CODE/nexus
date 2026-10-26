"""O histórico do app de ETM da Engenharia trazido UMA vez para o Nexus (Levi, 26/10/2026: "Traz 1 vez, para as OSs em
aberto bota esses comentários na nota da OS."). Desenho em docs/superpowers/specs/2026-10-26-engenharia-etm-design.md.

O app guardava tudo num repositório privado do GitHub, uma Issue por OS (título "OS <nº>"): cada comentário com o autor
no começo do corpo ("**Autor:**\\ntexto"; o GitHub dá a autoria ao dono do token) e as marcações como labels (o
diagnóstico, o status pós-OS, as etiquetas, "Em Acompanhamento" e "Finalizado pela Engenharia"). O token e o repositório
vêm do .env (`NEXUS_ETM_GITHUB_TOKEN`, `NEXUS_ETM_GITHUB_REPO`): o nome do repositório traz o de uma pessoa, e o código é
público.

O que entra: os comentários no livro da OS da Engenharia (`os_acompanhamento`, com o autor e a data de lá; origem
"app_etm" e o id do comentário) e as marcações atuais no livro das ETMs (`etm_marcas`, com a data da label; o id é
"<issue>:<label>"). Nas OS em aberto, os comentários vão também para a nota da OS, os de cada OS numa escrita só, do mais
antigo ao mais novo (quem escreve é a ponte do OS Creator, na sessão do Fracttal de quem importa). Trazer de novo não
repete: o que já tem o id no livro fica de fora, e a linha que já está na nota não volta.

A leitura do GitHub e a importação levam minutos (uma chamada por issue, uma OS por vez no Fracttal): rodam por trás,
uma de cada vez, e a tela do administrador acompanha pelo `estado_do_job`.
"""
import re
import threading
import time
from datetime import datetime, timezone

API = "https://api.github.com"
PREFIXO = "OS "
ACOMPANHAMENTO, FINALIZADO = "Em Acompanhamento", "Finalizado pela Engenharia"
ORIGEM = "app_etm"
TETO_PAGINAS = 50
_CORPO = re.compile(r"^\*\*(?P<autor>.+?):\*\*\n(?P<texto>[\s\S]*)$")
_JOB = {"fase": "parado", "msg": "", "erro": "", "previa": None, "plano": None, "resultado": None, "em": 0.0}
_TRAVA = threading.Lock()


class SemAcesso(RuntimeError):
    """O GitHub recusou o token ou não achou o repositório."""


class SessaoVencida(RuntimeError):
    """A sessão do Fracttal de quem importa venceu no meio: a importação para (nada da OS em curso foi gravado)."""


def _quando(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _get(sessao, url: str, token: str, params: dict | None = None):
    r = sessao.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                 "X-GitHub-Api-Version": "2022-11-28"}, params=params or {}, timeout=20)
    if r.status_code in (401, 403, 404):
        raise SemAcesso(f"o GitHub recusou (HTTP {r.status_code}): confira o token e o repositório do app no .env")
    r.raise_for_status()
    return r.json()


def _paginas(sessao, url: str, token: str, extra: dict | None = None) -> list:
    out = []
    for pagina in range(1, TETO_PAGINAS + 1):
        d = _get(sessao, url, token, dict(extra or {}, per_page=100, page=pagina)) or []
        out += d
        if len(d) < 100:
            break
    return out


def _comentario(c: dict) -> dict:
    corpo = str(c.get("body") or "")
    m = _CORPO.match(corpo)
    autor, texto = (m.group("autor").strip(), m.group("texto").strip()) if m else ("Desconhecido", corpo.strip())
    return {"id": str(c.get("id")), "autor": autor, "texto": texto, "data": c.get("created_at")}


def ler_github(token: str, repo: str, sessao=None) -> dict[str, dict]:
    """{nº da OS: {"numero", "labels", "comentarios", "datas" (label → quando foi posta), "atualizada"}}."""
    if sessao is None:
        import requests
        sessao = requests.Session()
    base = f"{API}/repos/{repo}"
    out: dict[str, dict] = {}
    for i in _paginas(sessao, base + "/issues", token, {"state": "all"}):
        titulo = str(i.get("title") or "")
        if i.get("pull_request") is not None or not titulo.startswith(PREFIXO):
            continue
        folio = titulo[len(PREFIXO):].strip()
        if not folio.isdigit():
            continue
        labels = {str(x.get("name")) for x in i.get("labels") or [] if x.get("name")}
        coms = ([_comentario(c) for c in _paginas(sessao, f"{base}/issues/{i['number']}/comments", token)]
                if i.get("comments") else [])
        datas = {}
        if labels:
            for ev in _paginas(sessao, f"{base}/issues/{i['number']}/events", token):
                nome = (ev.get("label") or {}).get("name")
                if ev.get("event") == "labeled" and nome in labels:
                    datas[nome] = ev.get("created_at")      # na ordem do GitHub: fica a última vez que foi posta
        out[folio] = {"numero": i["number"], "labels": labels, "comentarios": coms, "datas": datas,
                      "atualizada": i.get("updated_at")}
    return out


def marcas_do_issue(it: dict) -> list[dict]:
    """As marcações que as labels de uma issue dizem, com a data em que a label foi posta (sem ela, a da issue)."""
    from . import etm_marcas as M
    diag = {n: i for i, n in M.DIAGNOSTICOS}
    pos = {n: i for i, n in M.STATUS_POS}
    etq = {n: i for i, n in M.ETIQUETAS}
    out = []
    for lab in sorted(it.get("labels") or ()):
        if lab in diag:
            ev, v, lig = "diagnostico", diag[lab], None
        elif lab in pos:
            ev, v, lig = "status_pos", pos[lab], None
        elif lab in etq:
            ev, v, lig = "etiqueta", etq[lab], True
        elif lab in (ACOMPANHAMENTO, FINALIZADO):
            ev, v, lig = ("acompanhamento" if lab == ACOMPANHAMENTO else "finalizado"), None, True
        else:
            continue
        out.append({"evento": ev, "valor_id": v, "ligado": lig, "origem_id": f"{it['numero']}:{lab}",
                    "quando": _quando((it.get("datas") or {}).get(lab)) or _quando(it.get("atualizada"))})
    return out


def plano(gh: dict, ja_comentarios: set, ja_marcas: set) -> list[dict]:
    """O que ainda falta trazer, por OS: os comentários e as marcações que o Nexus não tem."""
    out = []
    for folio in sorted(gh, key=int):
        it = gh[folio]
        coms = sorted((c for c in it["comentarios"] if c["id"] not in ja_comentarios), key=lambda c: c.get("data") or "")
        marcas = [m for m in marcas_do_issue(it) if m["origem_id"] not in ja_marcas]
        if coms or marcas:
            out.append({"folio": folio, "comentarios": coms, "marcas": marcas})
    return out


def previa(pl: list[dict], abertas: dict) -> dict:
    """Os números da prévia; `abertas` = {nº: a OS está aberta?} pelo que a tela ETMs leu (a importação confere)."""
    return {"oss": len(pl), "comentarios": sum(len(x["comentarios"]) for x in pl),
            "marcacoes": sum(len(x["marcas"]) for x in pl),
            "notas": sum(1 for x in pl if x["comentarios"] and abertas.get(x["folio"]))}


def linha(c: dict) -> str:
    from . import os_acompanhamento as O
    return O.linha_da_nota(c["texto"], c["autor"], _quando(c.get("data")) or datetime.now(timezone.utc))


# ── as duas tarefas, por trás ───────────────────────────────────────────────────────────────────────────────────────
def estado_do_job() -> dict:
    return {k: _JOB[k] for k in ("fase", "msg", "erro", "previa", "resultado")}


def limpar() -> None:
    _JOB.update(fase="parado", msg="", erro="", previa=None, plano=None, resultado=None, em=0.0)


def _rodar(app, tarefa):
    if app.config.get("TESTING"):
        tarefa()
    else:
        threading.Thread(target=tarefa, daemon=True, name="nexus-etm-historico").start()


def _ja_importados() -> tuple[set, set]:
    from . import etm_marcas as M
    from . import os_acompanhamento as O
    com = {str(e.get("origem_id")) for e in O._reler()["eventos"] if e.get("origem") == ORIGEM and e.get("origem_id")}
    mar = {str(e.get("origem_id")) for e in M._reler()["eventos"] if e.get("origem") == ORIGEM and e.get("origem_id")}
    return com, mar


def iniciar_leitura(app, token: str, repo: str, sessao=None) -> dict:
    """Lê o repositório do app e monta a prévia (nada é gravado)."""
    with _TRAVA:
        if _JOB["fase"] in ("lendo", "importando"):
            return estado_do_job()
        _JOB.update(fase="lendo", msg="Lendo o repositório do app de ETM…", erro="", previa=None, plano=None,
                    resultado=None, em=time.time())

    def tarefa():
        try:
            with app.app_context():
                from . import etm as ETM
                gh = ler_github(token, repo, sessao)
                com, mar = _ja_importados()
                pl = plano(gh, com, mar)
                abertas = {o["os"]: o["coluna"] not in ("concluida", "cancelada") for o in ETM.dados()["os"]}
                pv = previa(pl, abertas)
                _JOB.update(fase="lido", plano=pl, previa=pv, msg=(
                    f"{pv['comentarios']} comentário(s) e {pv['marcacoes']} marcação(ões) em {pv['oss']} OS; "
                    f"{pv['notas']} OS em aberto recebem os comentários na nota." if pl else
                    "Nada a trazer: o Nexus já tem todo o histórico do app."))
        except Exception as e:      # noqa: BLE001 — o GitHub ou o banco fora: a tela diz
            _JOB.update(fase="erro", erro=f"{type(e).__name__}: {str(e)[:200]}", msg="")
    _rodar(app, tarefa)
    return estado_do_job()


def iniciar_importacao(app, escrever_nota) -> dict:
    """Grava o plano lido. `escrever_nota(o, linhas)` vai à nota da OS aberta e devolve "sim" ou o motivo de não ter
    ido; se falhar, os comentários daquela OS ficam para a próxima (a nota não pode ficar sem eles, nem eles sem ela)."""
    with _TRAVA:
        if _JOB["fase"] != "lido" or _JOB["plano"] is None:
            return dict(estado_do_job(), erro="Leia o histórico antes de trazer.")
        _JOB.update(fase="importando", msg="Trazendo o histórico…", erro="", em=time.time())
        pl = list(_JOB["plano"])

    def tarefa():
        try:
            with app.app_context():
                _JOB["resultado"] = _importar(pl, escrever_nota)
                r = _JOB["resultado"]
                _JOB.update(fase="feito", plano=None, msg=(
                    f"Trazidos {r['comentarios']} comentário(s) e {r['marcacoes']} marcação(ões); {r['notas']} nota(s) "
                    "de OS em aberto atualizadas." + (f" Ficaram para a próxima (o Fracttal não respondeu): OS "
                                                      f"{', '.join(r['adiadas'])}." if r["adiadas"] else "")
                    + (f" Não achei no Fracttal: OS {', '.join(r['sem_os'])}." if r["sem_os"] else "")))
        except SessaoVencida:
            _JOB.update(fase="erro", erro="A sessão do Fracttal venceu no meio: entre de novo e traga de novo (o que já "
                                          "foi não se repete).", msg="")
        except Exception as e:      # noqa: BLE001 — o banco fora: nada desta vez foi gravado no Nexus
            _JOB.update(fase="erro", erro=f"{type(e).__name__}: {str(e)[:200]}", msg="")
    _rodar(app, tarefa)
    return estado_do_job()


def _importar(pl: list[dict], escrever_nota) -> dict:
    from ..torres.engenharia import _os_para_gravar
    from . import etm_marcas as M
    from . import os_acompanhamento as O
    from . import os_equipe
    comentarios, marcas, adiadas, sem_os, notas = [], [], [], [], 0
    for item in pl:
        try:
            o = os_equipe.ler_os(item["folio"])
        except Exception:           # noqa: BLE001 — a OS volta na próxima vez
            adiadas.append(item["folio"])
            continue
        if not o:
            sem_os.append(item["folio"])
            continue
        osg = _os_para_gravar(o)
        if item["comentarios"]:
            if o["coluna"] in ("concluida", "cancelada"):
                nota = "OS fechada no Fracttal: o comentário do app de ETM ficou só no Nexus"
            else:
                try:
                    nota = escrever_nota(o, [linha(c) for c in item["comentarios"]])
                except SessaoVencida:
                    raise
                except Exception:   # noqa: BLE001 — sem a nota, os comentários da OS esperam a próxima
                    adiadas.append(item["folio"])
                    nota = None
                notas += nota == "sim"
            if nota is not None:
                comentarios += [{"os_": osg, "autor": c["autor"], "texto": c["texto"], "quando": _quando(c.get("data")),
                                 "origem_id": c["id"], "nota": nota} for c in item["comentarios"]]
        marcas += [dict(m, os_=osg) for m in item["marcas"]]
    n_c = O.importar_comentarios(comentarios, ORIGEM) if comentarios else 0
    n_m = M.importar_marcas(marcas, ORIGEM) if marcas else 0
    return {"comentarios": n_c, "marcacoes": n_m, "notas": notas, "adiadas": adiadas, "sem_os": sem_os}
