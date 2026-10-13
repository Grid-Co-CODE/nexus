"""A versão no ar, no Início (13/10/2026, Levi: "Quero que no início do Nexus diga quando foi o último commit para eu
acompanhar se está realmente subindo automático para o server").

O cartão "Versão no ar" diz:
- o commit em execução, a hora e o assunto dele, pelo git da própria pasta (no servidor, a /opt/nexus, do usuário do
  serviço; é o mesmo commit do /saude);
- desde quando ESTE processo está no ar: o deploy reinicia o Nexus, então é a hora em que a versão subiu;
- a conferência com o `main` do GitHub, em semáforo: em dia (verde); atrás, "atualizando" (amarelo) nos 5 primeiros
  minutos em que se vê isso, que é o ciclo do deploy automático (o timer roda a cada 2 min), e "atrasado" (vermelho)
  depois, quando o deploy automático não pegou; à frente (commits só desta máquina: o PC de quem desenvolve); diferente
  (commits dos dois lados); ou fora (o commit daqui não está no GitHub).

A conferência vai à API pública do GitHub (`compare main...<commit>`, uma chamada), no máximo a cada 5 min e sempre por
trás: o Início nunca espera a rede. Sem a API (o servidor pode não sair para api.github.com, e sem login o limite é de
60 pedidos por hora por IP), vai pelo `git ls-remote` no github.com, o mesmo caminho do deploy. Nos testes nada sai: com
`TESTING` a conferência fica desligada (`NEXUS_VERSAO_GITHUB=1` liga, e os testes dublam a ida ao GitHub).
"""
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache

_BRT = timezone(timedelta(hours=-3))
# importado pelo create_app: é a hora em que este processo subiu (cada deploy reinicia o Nexus)
NO_AR_DESDE = datetime.now(_BRT)
REPO_PADRAO = "Grid-Co-CODE/nexus"
CONFERIR_S = 300        # uma conferência com o GitHub vale 5 min
ATUALIZANDO_S = 300     # atrás há mais que isso = o deploy automático (a cada 2 min) não pegou
_PASTA = os.path.dirname(os.path.abspath(__file__))
_SITUACAO_API = {"identical": "em_dia", "behind": "atras", "ahead": "a_frente", "diverged": "diferente"}

_TRAVA = threading.Lock()
_ESTADO = {"conferido_em": 0.0, "resultado": None, "atras_desde": 0.0, "trabalhando": False}


def _git(*args, timeout: float = 5) -> str:
    # GIT_TERMINAL_PROMPT=0: sem rede ou sem acesso, o git falha em vez de esperar uma senha que ninguém vai digitar
    r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=timeout, cwd=_PASTA,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "o git falhou").strip()[:160])
    return r.stdout.strip()


def _data(iso) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(_BRT)


def _curto(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"[:120]


@lru_cache(maxsize=1)
def local() -> dict:
    """O commit em execução: {sha, em, assunto}. Sem git (ou fora de um clone), sha vazio e em None."""
    try:
        sha, em, assunto = (_git("log", "-1", "--format=%H%x1f%cI%x1f%s").split("\x1f") + ["", "", ""])[:3]
    except (OSError, subprocess.SubprocessError, RuntimeError):
        return {"sha": "", "em": None, "assunto": ""}
    return {"sha": sha, "em": _data(em), "assunto": assunto}


def _pela_api(sha: str, repo: str) -> dict:
    import requests
    r = requests.get(f"https://api.github.com/repos/{repo}/compare/main...{sha}", params={"per_page": 1}, timeout=6,
                     headers={"Accept": "application/vnd.github+json", "User-Agent": "nexus-gridco"})
    if r.status_code == 404:        # o repositório é público: 404 = este commit não está no GitHub
        return {"situacao": "fora", "a_frente": 0, "atras": 0, "main": {}}
    r.raise_for_status()
    j = r.json()
    base = j.get("base_commit") or {}
    c = base.get("commit") or {}
    return {"situacao": _SITUACAO_API.get(j.get("status"), "diferente"), "a_frente": int(j.get("ahead_by") or 0),
            "atras": int(j.get("behind_by") or 0),
            "main": {"sha": base.get("sha") or "", "em": _data((c.get("committer") or {}).get("date")),
                     "assunto": (c.get("message") or "").split("\n", 1)[0]}}


def _pelo_git(sha: str, repo: str) -> dict:
    saida = _git("ls-remote", f"https://github.com/{repo}.git", "refs/heads/main", timeout=10)
    main = saida.split()[0] if saida else ""
    if not main:
        raise RuntimeError("o GitHub não devolveu o main")
    if main == sha:
        lo = local()
        return {"situacao": "em_dia", "a_frente": 0, "atras": 0, "main": {"sha": main, "em": lo["em"], "assunto": lo["assunto"]}}
    info = {"sha": main, "em": None, "assunto": ""}
    try:
        # o commit do GitHub já está nesta pasta (o fetch do deploy o trouxe): dá para datar e contar
        em, assunto = (_git("log", "-1", "--format=%cI%x1f%s", main).split("\x1f") + [""])[:2]
        info.update(em=_data(em), assunto=assunto)
        atras, a_frente = (int(x) for x in _git("rev-list", "--left-right", "--count", f"{main}...{sha}").split())
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
        # sem o objeto aqui não dá para contar; no servidor, que não faz commit, outro commit no GitHub é "atrás"
        return {"situacao": "atras", "a_frente": 0, "atras": 0, "main": info}
    situacao = ("em_dia" if not (atras or a_frente) else "atras" if not a_frente else "a_frente" if not atras
                else "diferente")
    return {"situacao": situacao, "a_frente": a_frente, "atras": atras, "main": info}


def _github(sha: str, repo: str) -> dict:
    """A situação deste commit diante do `main` do GitHub; levanta exceção se não houve como conferir."""
    try:
        return _pela_api(sha, repo)
    except Exception as e_api:      # noqa: BLE001 — sem a API, pelo git
        try:
            return _pelo_git(sha, repo)
        except Exception as e_git:  # noqa: BLE001
            raise RuntimeError(f"API: {_curto(e_api)}; git: {_curto(e_git)}") from e_git


def _ligada(cfg) -> bool:
    v = cfg.get("NEXUS_VERSAO_GITHUB")
    if v is None:
        return not cfg.get("TESTING")
    return str(v).strip().lower() not in ("", "0", "false", "nao", "não", "desligado")


def _conferir(repo: str) -> None:
    try:
        sha = local()["sha"]
        try:
            r = dict(_github(sha, repo), erro="") if sha else {"situacao": "sem_git", "erro": "", "main": {}}
        except Exception as e:      # noqa: BLE001 — a conferência nunca derruba nada: o cartão diz que não conseguiu
            r = {"situacao": "sem_github", "erro": _curto(e), "main": {}}
        agora = time.time()
        with _TRAVA:
            # o relógio do "atrás" conta da 1ª vez que se viu, e só zera em dia: commit novo no GitHub com o servidor
            # parado não pode voltar a "atualizando" (cada deploy reinicia o processo, e o estado zera junto)
            if r["situacao"] == "atras":
                _ESTADO["atras_desde"] = _ESTADO["atras_desde"] or agora
            elif r["situacao"] != "sem_github":
                _ESTADO["atras_desde"] = 0.0
            _ESTADO.update(resultado=r, conferido_em=agora)
    finally:
        with _TRAVA:
            _ESTADO["trabalhando"] = False


def conferir(app) -> None:
    """Pede a conferência com o GitHub por trás, se a última tem mais de 5 min. Quem chama: o Início e, ao subir, o
    servir.py e o app.py (a 1ª visita já encontra a resposta)."""
    if not _ligada(app.config):
        return
    with _TRAVA:
        if _ESTADO["trabalhando"] or (_ESTADO["resultado"] is not None
                                      and time.time() - _ESTADO["conferido_em"] < CONFERIR_S):
            return
        _ESTADO["trabalhando"] = True
    repo = app.config.get("NEXUS_GITHUB_REPO") or REPO_PADRAO
    threading.Thread(target=_conferir, args=(repo,), daemon=True, name="nexus-versao").start()


def _hora(d: datetime | None, agora: datetime) -> str:
    if d is None:
        return ""
    return d.strftime("%H:%M") if d.date() == agora.date() else d.strftime("%d/%m %H:%M")


def _commits(n: int) -> str:
    return f"{n} commit" if n == 1 else f"{n} commits"


def cartao(app) -> dict:
    """O que o cartão do Início mostra. Pede a conferência por trás quando venceu: a página nunca espera."""
    from . import _commit
    conferir(app)
    agora = datetime.now(_BRT)
    curto = _commit()
    lo = local()
    do_mesmo = bool(lo["sha"]) and (curto == "local" or lo["sha"].startswith(curto))
    em = lo["em"] if do_mesmo else None
    with _TRAVA:
        r, conferido_em, atras_desde = _ESTADO["resultado"], _ESTADO["conferido_em"], _ESTADO["atras_desde"]
    main = (r or {}).get("main") or {}
    no_github = f"o {main['sha'][:7]}" if main.get("sha") else "outro commit"
    quando = f", de {_hora(main['em'], agora)}" if main.get("em") else ""
    situacao, classe, rotulo, detalhe = (r or {}).get("situacao"), "neutro", "", ""
    if not _ligada(app.config):
        situacao, rotulo = "desligada", "Conferência com o GitHub desligada"
    elif r is None:
        situacao, rotulo = "conferindo", "Conferindo o GitHub"
    elif situacao == "em_dia":
        classe, rotulo = "ok", "Em dia com o GitHub"
    elif situacao == "atras":
        n = f" ({_commits(r['atras'])} à frente)" if r.get("atras") else ""
        min_atras = int((time.time() - (atras_desde or time.time())) // 60)
        if min_atras * 60 < ATUALIZANDO_S:
            classe, rotulo = "alerta", "Atualizando"
            detalhe = f"O GitHub tem {no_github}{quando}{n}; o deploy automático leva até 3 min."
        else:
            classe, rotulo = "critico", f"Atrasado há {min_atras} min"
            detalhe = f"O GitHub tem {no_github}{quando}{n} e ele não subiu: o deploy automático não pegou."
    elif situacao == "a_frente":
        rotulo, detalhe = "À frente do GitHub", f"{_commits(r['a_frente'])} só nesta máquina."
    elif situacao == "diferente":
        classe, rotulo = "critico", "Diferente do GitHub"
        detalhe = f"{_commits(r['a_frente'])} só aqui e {_commits(r['atras'])} só no GitHub."
    elif situacao == "fora":
        rotulo, detalhe = "Fora do GitHub", "Este commit não está no GitHub (só nesta máquina)."
    elif situacao == "sem_git":
        rotulo = "Sem o git nesta pasta"
    else:
        rotulo, detalhe = "GitHub sem resposta", f"Não consegui conferir agora ({r.get('erro') or 'sem motivo'})."
    return {"curto": curto, "em_txt": em.strftime("%d/%m %H:%M") if em else "—", "assunto": lo["assunto"] if do_mesmo else "",
            "no_ar_desde_txt": _hora(NO_AR_DESDE, agora), "situacao": situacao, "classe": classe, "rotulo": rotulo,
            "detalhe": detalhe, "conferido_txt": f"conferido às {_hora(datetime.fromtimestamp(conferido_em, _BRT), agora)}"
            if conferido_em else ""}
