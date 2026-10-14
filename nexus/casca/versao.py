"""A versão no ar e as atualizações, no Início (13/10/2026).

Levi, à tarde: "Quero que no início do Nexus diga quando foi o último commit para eu acompanhar se está realmente subindo
automático para o server". À noite, o cartão ficou só com isso ("tire as informações de github, preso em 24hrs e essas
observações abaixo do commit") e ganhou a aba de baixo ("Inclua no início uma sub aba de atualizações mostrando as
últimas atualizações dos commits e o que mudou! Ao clicar em versão no ar já leva para lá!"):

- o cartão "Versão no ar": a hora do commit em execução, o commit curto (o mesmo do /saude) e desde quando ESTE processo
  está no ar (o deploy reinicia o Nexus: é a hora em que a versão entrou). Clicar leva às Atualizações;
- a aba **Atualizações** (`/?aba=atualizacoes`): os últimos commits desta pasta, do mais novo, por dia, com o tipo (novidade,
  correção...), a área e o que mudou (o título e, aberto, o resto da mensagem em tópicos, sem a prova nem a coautoria:
  `blocos`). Sem horários (14/10/2026, Levi: "Esconda os horários!"): o dia agrupa.

Tudo sai do git da própria pasta (no servidor, a /opt/nexus, do usuário do serviço), lido uma vez por processo: cada
deploy reinicia o Nexus, e a lista nova vem junto. Sem git (a vitrine estática, uma pasta copiada), o cartão diz "—" e a
aba diz que não há histórico. A conferência com o GitHub que existiu à tarde saiu junto com o semáforo.
"""
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from functools import lru_cache

_BRT = timezone(timedelta(hours=-3))
# importado pelo create_app: é a hora em que este processo subiu (cada deploy reinicia o Nexus)
NO_AR_DESDE = datetime.now(_BRT)
LIMITE_HISTORICO = 60
_PASTA = os.path.dirname(os.path.abspath(__file__))
# o tipo do commit ("feat(base): ...") como a pessoa entende
TIPOS = {"feat": "Novidade", "fix": "Correção", "perf": "Desempenho", "docs": "Documentação", "chore": "Manutenção",
         "test": "Teste", "refactor": "Ajuste interno", "style": "Visual", "revert": "Desfeito"}
_TITULO = re.compile(r"^(?P<tipo>[a-z]+)(?:\((?P<area>[^)]*)\))?!?:\s*(?P<texto>.+)$")
_TRAILER = ("co-authored-by:", "signed-off-by:")
# o parágrafo da prova (os testes que provam a mudança) é para quem revisa o código, não para quem lê a aba (14/10/2026,
# Levi: "Não precisa desse Prova!")
_PROVA = re.compile(r"^provas?\b", re.I)
_MARCADOR = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def blocos(corpo: str) -> list[dict]:
    """O corpo do commit pronto para ler (14/10/2026, Levi: "Esse 'O que mudou em detalhe' está muito feio e bagunçado,
    poderia pontuar mais bonito"): [{"tipo": "pedido" | "lista" | "paragrafo", "texto" | "itens"}]. O texto do commit é
    quebrado a cada ~120 colunas: as linhas de um parágrafo ou de um item viram uma só. O 1º parágrafo que cita o pedido
    ("Levi, 14/10/2026: ...") é o pedido; "- " abre um item da lista (a linha seguinte sem marcador continua o item); o
    parágrafo da prova e as linhas de coautoria saem."""
    out = []
    for bloco in re.split(r"\n\s*\n", str(corpo or "").strip()):
        linhas = [x for x in bloco.splitlines() if x.strip() and not x.strip().lower().startswith(_TRAILER)]
        if not linhas or _PROVA.match(linhas[0].strip()):
            continue
        if _MARCADOR.match(linhas[0]):
            itens = []
            for x in linhas:
                if _MARCADOR.match(x):
                    itens.append(_MARCADOR.sub("", x, count=1).strip())
                elif itens:
                    itens[-1] += " " + x.strip()
            out.append({"tipo": "lista", "itens": itens})
            continue
        texto = " ".join(x.strip() for x in linhas)
        pedido = not out and re.match(r"^Levi\b", texto)
        out.append({"tipo": "pedido" if pedido else "paragrafo", "texto": texto})
    return out


def _git(*args, timeout: float = 5) -> str:
    # GIT_TERMINAL_PROMPT=0: sem acesso, o git falha em vez de esperar uma senha que ninguém vai digitar
    r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", timeout=timeout, cwd=_PASTA,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "o git falhou").strip()[:160])
    return r.stdout


def _data(iso) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(_BRT)


@lru_cache(maxsize=1)
def local() -> dict:
    """O commit em execução: {sha, em, assunto}. Sem git (ou fora de um clone), sha vazio e em None."""
    try:
        sha, em, assunto = (_git("log", "-1", "--format=%H%x1f%cI%x1f%s").strip().split("\x1f") + ["", "", ""])[:3]
    except (OSError, subprocess.SubprocessError, RuntimeError):
        return {"sha": "", "em": None, "assunto": ""}
    return {"sha": sha, "em": _data(em), "assunto": assunto}


def _item(sha: str, em: str, titulo: str, corpo: str) -> dict:
    m = _TITULO.match(titulo.strip())
    tipo, area, texto = (m.group("tipo"), (m.group("area") or "").strip(), m.group("texto")) if m else ("", "", titulo)
    # "Equipamentos das usinas liga pela aba - cada chave vai ..." = a manchete e o resto
    manchete, _, resto = texto.partition(" - ")
    linhas = [x for x in corpo.splitlines() if not x.strip().lower().startswith(_TRAILER)]
    return {"sha": sha, "curto": sha[:7], "em": _data(em), "tipo": TIPOS.get(tipo, ""), "tipo_id": tipo if tipo in TIPOS else "",
            "area": area, "manchete": manchete.strip(), "resto": resto.strip(), "corpo": "\n".join(linhas).strip(),
            "detalhe": blocos(corpo)}


@lru_cache(maxsize=1)
def historico() -> tuple:
    """Os últimos commits desta pasta, do mais novo: ({sha, curto, em, tipo, area, manchete, resto, corpo}, ...). Vazio
    sem git. Uma leitura por processo (o deploy reinicia)."""
    try:
        saida = _git("log", "-n", str(LIMITE_HISTORICO), "--format=%H%x1f%cI%x1f%s%x1f%b%x1e", timeout=10)
    except (OSError, subprocess.SubprocessError, RuntimeError):
        return ()
    out = []
    for bloco in saida.split("\x1e"):
        partes = bloco.strip("\r\n").split("\x1f")
        if len(partes) >= 3 and partes[0].strip():
            out.append(_item(partes[0].strip(), partes[1], partes[2], partes[3] if len(partes) > 3 else ""))
    return tuple(out)


def _hora(d: datetime | None, agora: datetime) -> str:
    if d is None:
        return ""
    return d.strftime("%H:%M") if d.date() == agora.date() else d.strftime("%d/%m %H:%M")


def cartao(app) -> dict:  # noqa: ARG001 — o app fica na assinatura: é quem chama, e a casca passa sempre
    """O que o cartão do Início mostra: a hora do commit, o commit curto e desde quando o processo está no ar."""
    from . import _commit
    agora = datetime.now(_BRT)
    curto = _commit()
    lo = local()
    do_mesmo = bool(lo["sha"]) and (curto == "local" or lo["sha"].startswith(curto))
    em = lo["em"] if do_mesmo else None
    return {"curto": curto, "em_txt": em.strftime("%d/%m %H:%M") if em else "—",
            "no_ar_desde_txt": _hora(NO_AR_DESDE, agora)}


def dias(itens) -> list[tuple[str, list]]:
    """Os commits por dia (o mais novo primeiro), com o rótulo do dia: "Hoje", "Ontem" ou "dd/mm"."""
    hoje = datetime.now(_BRT).date()
    grupos: dict = {}
    for x in itens:
        d = x["em"].date() if x["em"] else None
        if d is None:
            rot = "Sem data"
        elif d == hoje:
            rot = "Hoje"
        elif d == hoje - timedelta(days=1):
            rot = "Ontem"
        else:
            rot = d.strftime("%d/%m/%Y")
        grupos.setdefault(rot, []).append(x)
    return list(grupos.items())
