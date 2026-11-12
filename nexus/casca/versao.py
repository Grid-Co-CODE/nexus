"""A versão no ar e as atualizações, no Início (13/10/2026).

Levi, à tarde: "Quero que no início do Nexus diga quando foi o último commit para eu acompanhar se está realmente subindo
automático para o server". À noite, o cartão ficou só com isso ("tire as informações de github, preso em 24hrs e essas
observações abaixo do commit") e ganhou a aba de baixo ("Inclua no início uma sub aba de atualizações mostrando as
últimas atualizações dos commits e o que mudou! Ao clicar em versão no ar já leva para lá!"):

- o cartão "Versão no ar": a hora do commit em execução, o commit curto (o mesmo do /saude) e desde quando ESTE processo
  está no ar (o deploy reinicia o Nexus: é a hora em que a versão entrou). Clicar leva às Atualizações;
- a aba **Atualizações** (`/?aba=atualizacoes`): só as NOVIDADES, as CORREÇÕES e o DESEMPENHO (`feat`, `fix` e `perf`;
  19/10/2026, Levi: "deixe só novidade e correção"), de UM mês por vez, o atual no padrão (12/11/2026, Levi: "sempre
  filtrado no mês atual, que dê para filtrar em outros meses também"; até ali, os últimos 60 dias), do mais novo, por
  dia, com a área e o que mudou (o título e, aberto, o resto da mensagem em tópicos, sem a prova nem a coautoria:
  `blocos`). O corte do mês é na hora do pedido (`da_aba`): o processo pode ficar dias no ar. O "no ar" marca o commit
  em execução, que pode nem estar na lista (uma documentação). Sem horários (14/10/2026, Levi: "Esconda os horários!"):
  o dia agrupa. Ao lado, um cartão por pessoa com os commits dela no mês (`pessoas`), que filtra a lista no clique.

Tudo sai do git da própria pasta (no servidor, a /opt/nexus, do usuário do serviço), lido uma vez por processo: cada
deploy reinicia o Nexus, e a lista nova vem junto. Sem git (a vitrine estática, uma pasta copiada), o cartão diz "—" e a
aba diz que não há histórico. A conferência com o GitHub que existiu à tarde saiu junto com o semáforo.
"""
import os
import re
import unicodedata
import subprocess
from datetime import datetime, timedelta, timezone
from functools import lru_cache

_BRT = timezone(timedelta(hours=-3))
# importado pelo create_app: é a hora em que este processo subiu (cada deploy reinicia o Nexus)
NO_AR_DESDE = datetime.now(_BRT)
# o git lê no máximo LIMITE_HISTORICO commits (o repositório tinha 1.209 em 12/11/2026, 43 dias depois do primeiro)
# a aba mostra UM mês por vez desde 12/11/2026 (Levi: "sempre filtrado no mês atual, que dê para filtrar em outros meses
# também"; até ali, os últimos 60 dias): o histórico carrega o que há para trás, até HISTORICO_DIAS
HISTORICO_DIAS = 400
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro",
         "dezembro")
TIPOS_NA_ABA = ("feat", "fix", "perf")     # o desempenho desde 24/10/2026 (o Levi não viu a correção da lentidão)
LIMITE_HISTORICO = 20000
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


def pessoa_de(nome) -> str:
    """A chave de quem fez o commit, pelo 1º nome do autor do git, sem acento nem caixa: "Fulano-1234" e "Fulano de Tal"
    (a mesma pessoa em duas contas do git, com e-mails diferentes) são "fulano". Duas pessoas com o mesmo 1º nome
    cairiam juntas: quando acontecer, a regra muda aqui."""
    t = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode().lower().strip()
    m = re.match(r"[a-z]+", t)
    return m.group(0) if m else ""


def _item(sha: str, em: str, titulo: str, corpo: str, autor: str = "", pais: str = "") -> dict:
    m = _TITULO.match(titulo.strip())
    tipo, area, texto = (m.group("tipo"), (m.group("area") or "").strip(), m.group("texto")) if m else ("", "", titulo)
    # "Equipamentos das usinas liga pela aba - cada chave vai ..." = a manchete e o resto
    manchete, _, resto = texto.partition(" - ")
    linhas = [x for x in corpo.splitlines() if not x.strip().lower().startswith(_TRAILER)]
    return {"sha": sha, "curto": sha[:7], "em": _data(em), "tipo": TIPOS.get(tipo, ""), "tipo_id": tipo if tipo in TIPOS else "",
            "area": area, "manchete": manchete.strip(), "resto": resto.strip(), "corpo": "\n".join(linhas).strip(),
            "detalhe": blocos(corpo), "autor": autor.strip(), "pessoa": pessoa_de(autor),
            "merge": len(pais.split()) > 1}


@lru_cache(maxsize=1)
def historico() -> tuple:
    """Os commits desta pasta dos últimos HISTORICO_DIAS dias, do mais novo: ({sha, curto, em, tipo, area, manchete,
    resto, corpo, autor, pessoa, merge}, ...). Vazio sem git. Uma leitura por processo (o deploy reinicia)."""
    try:
        # o autor e os pais vão no FIM do registro: quem lê só os 4 primeiros campos segue valendo
        saida = _git("log", f"--since={HISTORICO_DIAS}.days.ago", "-n", str(LIMITE_HISTORICO),
                     "--format=%H%x1f%cI%x1f%s%x1f%b%x1f%an%x1f%P%x1e", timeout=20)
    except (OSError, subprocess.SubprocessError, RuntimeError):
        return ()
    out = []
    for bloco in saida.split("\x1e"):
        partes = bloco.strip("\r\n").split("\x1f")
        if len(partes) >= 3 and partes[0].strip():
            out.append(_item(partes[0].strip(), partes[1], partes[2], partes[3] if len(partes) > 3 else "",
                             partes[4] if len(partes) > 4 else "", partes[5] if len(partes) > 5 else ""))
    return tuple(out)


def mes_de(d: datetime | None) -> str:
    return f"{d.year}-{d.month:02d}" if d else ""


def nome_do_mes(chave: str) -> str:
    """ "2026-11" -> "novembro de 2026"."""
    try:
        ano, mes = chave.split("-")
        return f"{MESES[int(mes) - 1]} de {ano}"
    except (ValueError, IndexError):
        return chave


def meses(itens, agora: datetime | None = None) -> list[tuple[str, str]]:
    """Os meses do filtro, do mais novo: os que têm commit no histórico e o mês atual (mesmo sem commit)."""
    chaves = {mes_de(x["em"]) for x in itens if x.get("em")} | {mes_de(agora or datetime.now(_BRT))}
    return [(k, nome_do_mes(k)) for k in sorted(chaves - {""}, reverse=True)]


def mes_pedido(valor, itens, agora: datetime | None = None) -> str:
    """O mês da aba: o pedido, se está na lista; senão o ATUAL (12/11/2026, Levi: "sempre filtrado no mês atual")."""
    atual = mes_de(agora or datetime.now(_BRT))
    return valor if valor in {k for k, _ in meses(itens, agora)} else atual


def da_aba(itens, mes: str, pessoas=()) -> list:
    """O que a aba Atualizações mostra: só novidade, correção e desempenho (19/10/2026, Levi: "deixe só novidade e
    correção"), do mês escolhido (12/11/2026: um mês por vez, o atual no padrão) e, com `pessoas` (as chaves de
    `pessoa_de`), só as delas."""
    quem = set(pessoas or ())
    return [x for x in itens if x["tipo_id"] in TIPOS_NA_ABA and x.get("em") is not None and mes_de(x["em"]) == mes
            and (not quem or x.get("pessoa") in quem)]


def pessoas(itens, mes: str) -> list[dict]:
    """Os cartões ao lado da aba (12/11/2026, Levi: "os cards de quantos commits as pessoas que estão mexendo no Nexus
    fizeram"): por pessoa, os commits do mês (todos os tipos, SEM os merges: juntar o trabalho de outro não é commit
    dela) e quantos deles são novidade, correção e desempenho (os que a lista mostra). Do que mais fez para o que menos.
    O nome é o do git: entre os nomes da mesma pessoa, o que parece nome de gente (com espaço, sem número)."""
    por: dict[str, dict] = {}
    for x in itens:
        k = x.get("pessoa") or ""
        if not k or x.get("merge") or not x.get("em") or mes_de(x["em"]) != mes:
            continue
        p = por.setdefault(k, {"chave": k, "nomes": {}, "commits": 0, **{t: 0 for t in TIPOS_NA_ABA}})
        p["commits"] += 1
        p["nomes"][x["autor"]] = p["nomes"].get(x["autor"], 0) + 1
        if x["tipo_id"] in TIPOS_NA_ABA:
            p[x["tipo_id"]] += 1
    out = []
    for p in por.values():
        de_gente = [n for n in p["nomes"] if " " in n and not any(c.isdigit() for c in n)]
        nome = max(de_gente, key=lambda n: p["nomes"][n]) if de_gente else p["chave"].capitalize()
        out.append({k: v for k, v in dict(p, nome=nome).items() if k != "nomes"})
    out.sort(key=lambda p: (-p["commits"], p["nome"]))
    return out


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


def contagem(itens) -> list[tuple[str, str, int]]:
    """Quantos de cada tipo, na ordem da aba e só os que têm item: [("feat", "Novidade", 3), ...]. Vai no cabeçalho do
    dia, que fica recolhido antes de hoje (29/10/2026, Levi: "contando a quantidade de correção, novidade e
    desempenho")."""
    out = []
    for t in TIPOS_NA_ABA:
        n = sum(1 for x in itens if x.get("tipo_id") == t)
        if n:
            out.append((t, TIPOS[t], n))
    return out


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
