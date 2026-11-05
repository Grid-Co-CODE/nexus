"""Gestão PCM: a aba Gestão PCM do painel do PCM, no Nexus.

Levi (07/10/2026): "quero que traga a visão de acompanhamento de manutenção do aplicativo para o Nexus conforme prints".
É a transcrição das contas do `js/preventivas.js` (o bloco "Manutenções — Plano & Fila") e, desde 04/11/2026, do
`js/app.js` (os filtros de cima completos, os números do alto, as árvores Cliente ▸ Usina ▸ Tipo e o Só atrasadas) do
gridco-pcm-data (pcm.gridco.com.br, aba Gestão PCM), para os números do Nexus baterem com os do painel: a prova
(`python -m nexus.pcm.prova_gestao`) roda o próprio JavaScript do painel contra o mesmo JSON e compara célula a célula
(ver nexus/pcm/CLAUDE.md). Mudou a regra lá? Mude aqui e rode a prova de novo.

Diferenças de propósito: a OS sem "#" (convenção do Nexus); o "hoje" em Brasília (o painel usa o dia UTC para
"atrasada", e entre 21h e meia-noite já conta o dia seguinte); a hora do "Atualizado" em Brasília; a célula de grupo e
do TOTAL sem a dica falsa "sem preventiva no período"; o cabeçalho Tipo da Fila ordena pelo tipo (no painel ele não
ordena nada); as listas de cima em cascata (no painel cada lista mostra tudo); e o Fracttal pela OS da tarefa (no
painel, o módulo de OS inteiro).

- PLANO: % de tarefas finalizadas por grupo ▸ usina × sigla (MPM/MPT/MPS/MPA) ou × mês, nos três últimos meses.
  Preventiva conta no mês da Data Programada; demanda (corretiva, religamento...) no mês da CRIAÇÃO. MPA/MPS em fração
  (50% de 4 anuais não é 50% de 200 mensais), e a fração abre a Fila daquela usina.
- FILA: o envelhecimento das MPA/MPS. Com a planilha da Gerencial (o `mpas.json`, CIFRADO no repositório público):
  Prevista × Programada, criticidade e a última observação datada. Sem a chave: só o lado do Fracttal (por OS).

Regra de ouro do painel: concluída é o ESTADO DA TAREFA ("Finalizada"), nunca o status da OS.
"""
import base64
import json
import math
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_BRT = timezone(timedelta(hours=-3))
SIGLAS = ("MPM", "MPT", "MPS", "MPA")                       # ordem de cadência (MPT entrou em 26/08)
_RX = re.compile(r"\b(MP[MSAT])\b")
# Demais tipos (painel, 18/09): a demanda conta o mês pela CRIAÇÃO; "Teste" e Preventiva sem sigla ficam fora
DEMANDA = {"corretiva": "corr", "corretiva emergencial": "emerg", "religamento": "relig", "religamento remoto": "relig",
           "inspecao": "insp", "preditiva": "pred", "administrativa": "adm", "zeladoria": "zel", "handover": "hand"}
ROT_TIPO = {"prev": "Preventivas", "corr": "Corretiva", "emerg": "Emergencial", "relig": "Religamento",
            "insp": "Inspeção", "pred": "Preditiva", "adm": "Administrativa", "zel": "Zeladoria", "hand": "Handover"}
PRIMARIOS = (("todos", "Todos"), ("prev", "Preventivas"), ("corr", "Corretiva"), ("emerg", "Emergencial"),
             ("relig", "Religamento"))
MAIS = ("insp", "pred", "adm", "zel", "hand")
MESNOME = ("", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
DIMS = (("cli", "Cliente ▸ Usina"), ("clu", "Cluster ▸ Usina"), ("res", "Responsável ▸ Usina"), ("usi", "Só usina"))
VALORES = (("pct", "%"), ("pend", "Pendentes"), ("fei", "Feitas"), ("tot", "Total"))
VAL_ROT = {"pct": "% de tarefas finalizadas", "pend": "tarefas que ainda faltam", "fei": "tarefas já finalizadas",
           "tot": "total de tarefas"}
PENDENCIAS = (("todas", "Todas"), ("atraso", "Atrasadas"), ("semos", "Sem OS"), ("critsem", "Críticas s/ data"))


@dataclass(frozen=True)
class Opcoes:
    """Os controles do bloco, com os padrões do painel (o que vem na URL da tela)."""
    modo: str = "plano"
    tipo: str = "todos"
    dim: str = "cli"
    col: str = "sig"
    val: str = "pct"
    mes: str = "todos"
    busca: str = ""
    ordem: str = "pend"
    desc: bool = True
    pend: str = "todas"
    ordem_f: str = "prev"
    desc_f: bool = False
    drill_usina: str = ""
    drill_tipo: str = ""


def eh_demanda(tipo) -> bool:
    return tipo in ROT_TIPO and tipo != "prev"


def opcoes(args, meses_) -> Opcoes:
    """Lê a URL e devolve só valores conhecidos (o resto cai no padrão), com as regras de troca do painel."""
    tipos = {"todos", "prev", *SIGLAS, *ROT_TIPO}
    o = Opcoes(
        modo=args.get("modo") if args.get("modo") in ("plano", "fila") else "plano",
        tipo=args.get("tipo") if args.get("tipo") in tipos else "todos",
        dim=args.get("dim") if args.get("dim") in dict(DIMS) else "cli",
        col=args.get("col") if args.get("col") in ("sig", "mes") else "sig",
        val=args.get("val") if args.get("val") in dict(VALORES) else "pct",
        mes=args.get("mes") if args.get("mes") in meses_ else "todos",
        busca=str(args.get("q") or "").strip()[:80],
        ordem=str(args.get("ordem") or "pend")[:12], desc=args.get("desc", "1") != "0",
        # "concl" não tem botão na Pendência: chega pelo KPI "concluídas", que no painel também filtra a Fila
        pend=args.get("pend") if args.get("pend") in (*dict(PENDENCIAS), "concl") else "todas",
        ordem_f=str(args.get("ordemf") or "prev")[:12], desc_f=args.get("descf") == "1",
        # o drill da fração MPA/MPS vai em "drill" (o "usina" da URL é o filtro de cima, que vale nos dois modos)
        drill_usina=str(args.get("drill") or "")[:160], drill_tipo=args.get("dt") if args.get("dt") in ("MPA", "MPS") else "")
    # MPM/MPT e a demanda não existem na Fila: cair no Todos evita tela vazia sem explicação (painel)
    if o.modo == "fila" and (o.tipo in ("MPM", "MPT") or eh_demanda(o.tipo)):
        o = replace(o, tipo="todos")
    return o


# ── datas ────────────────────────────────────────────────────────────────────────────────────────────────────
def agora() -> datetime:
    """O relógio da conta (Brasília). Um ponto só para a prova poder pará-lo no mesmo instante do painel."""
    return datetime.now(_BRT)


def hoje() -> date:
    return agora().date()


def meses(h: date) -> list[str]:
    """O mês corrente e os dois anteriores, do mais antigo para o atual."""
    out = []
    for i in (2, 1, 0):
        a, m = h.year, h.month - i
        while m < 1:
            a, m = a - 1, m + 12
        out.append(f"{a}-{m:02d}")
    return out


def rot_mes(m: str) -> str:
    return MESNOME[int(m[5:7])] + "/" + m[2:4]


_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _data_js(s: str) -> date | None:
    """A data como o `new Date('aaaa-mm-ddT12:00:00')` do navegador a lê: dia 1 a 31 em qualquer mês, e o que passa
    do mês rola para o seguinte (30/02 vira 02/03); fora disso, data inválida. A prova de 08/10/2026 achou a
    diferença: o Python recusava 30/02 e o painel contava 220 dias de atraso."""
    m = _ISO.fullmatch(s)
    if not m:
        return None
    a, me, d = (int(x) for x in m.groups())
    if not (1 <= me <= 12 and 1 <= d <= 31):
        return None
    return date(a, me, 1) + timedelta(days=d - 1)


def dias(iso, h: date) -> int | None:
    """Dias de `iso` até hoje (o painel conta do meio-dia do dia, arredondando para baixo)."""
    d = _data_js(str(iso)) if iso else None
    if d is None:
        return None
    a = agora()
    if a.date() != h:                           # nos testes, o "hoje" que vier
        a = datetime.combine(h, a.timetz())
    return math.floor((a - datetime.combine(d, datetime.min.time(), _BRT).replace(hour=12)).total_seconds() / 86400)


def data_curta(iso) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[2:4]}" if iso else ""


# ── texto ────────────────────────────────────────────────────────────────────────────────────────────────────
def sem_acento(s) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if not unicodedata.combining(c)).lower()


def norm(s) -> str:
    """O nome da usina comparável entre a Gerencial e o Fracttal ("Utragaz - Ibirapuã 2 - BA" × "Ultragaz – Ibirapuã 2")."""
    x = "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if not unicodedata.combining(c))
    x = re.sub(r"[–—]", "-", x).lower()
    x = re.sub(r"\s*-\s*[a-z]{2}\s*$", "", x)          # corta o " - UF" do Fracttal
    x = re.sub(r"(\d)00\b", r"\1", x)                   # Gerencial "Marabá 200" ~ Fracttal "Marabá 2"
    x = re.sub(r"\butragaz\b", "ultragaz", x)           # erro de digitação histórico do Fracttal
    return re.sub(r"[^a-z0-9]+", " ", x).strip()


def bate(a: str, k: str) -> bool:
    """A comparação frouxa do painel entre dois nomes já normalizados."""
    return bool(a and k and (a == k or a.startswith(k) or k.startswith(a)
                             or (len(a) >= 8 and a in k) or (len(k) >= 8 and k in a)))


_DATA = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def _k_data(s) -> str:
    m = _DATA.search(s or "")
    return m.group(3) + m.group(2) + m.group(1) if m else ""


def ultima_obs(txt) -> str:
    """A observação exibida é a ENTRADA DATADA MAIS RECENTE do log ("• dd/mm/aaaa - texto"), regra da Gerencial."""
    t = str(txt or "").strip()
    if not t:
        return ""
    melhor, melhor_k = "", ""
    for p in (x.strip() for x in re.split(r"\n|(?=•)", t)):
        if not p:
            continue
        k = _k_data(p)
        if not melhor or k >= melhor_k:
            melhor, melhor_k = p, k
    return re.sub(r"^•\s*", "", melhor)


def crit_cls(c) -> str:
    """"Crítico"/"Muito Crítico"/"Alta" = crit; "Média" = and; o resto ok ('crit' em qualquer posição vem antes)."""
    s = sem_acento(c)
    if not s:
        return ""
    if "crit" in s or s.startswith("alt"):
        return "crit"
    return "and" if s.startswith("m") else "ok"


def _round(x: float) -> int:
    return math.floor(x + 0.5)                          # o Math.round do JavaScript (meio para cima)


# ── base atômica ─────────────────────────────────────────────────────────────────────────────────────────────
def escopo(tarefas) -> list[dict]:
    """Esconde as tarefas sem usina ou cliente (ativos de teste ou sem classificação), como o painel."""
    return [t for t in tarefas or [] if t.get("usina") and t["usina"] != "(sem usina)" and t.get("cliente")
            and t["cliente"] != "(sem cliente)" and str(t["cliente"]).lower() != "usina teste"]


# ── os filtros de cima da aba (a barra do index.html do painel e o `gpFilteredTarefas` do js/app.js) ─────────────────
# (nome na URL, campo da tarefa, rótulo, o "vazio" da lista), na ordem da barra do painel. O Tipo de cima vai como
# `tipo_tarefa` porque o `tipo` da URL já é o Tipo do Plano & Fila (prev, MPM, corr...): o endereço de hoje não muda
LISTAS = (("cliente", "cliente", "Cliente", "Todos"), ("usina", "usina", "Usina", "Todas"),
          ("cluster", "cluster", "Equipe cluster", "Todos"), ("responsavel", "responsavel", "Responsável O&M", "Todos"),
          ("tipo_tarefa", "tipo", "Tipo", "Todos"), ("etiqueta", "etiquetas", "Etiqueta", "Todas"),
          ("estado", "estado", "Estado", "Todos"))
PMODOS = (("qq", "Qualquer data"), ("prog", "Só programada"), ("ini", "Só início"), ("fim", "Só final"))
PARAMS_FILTRO = (*(n for n, *_ in LISTAS), "os", "ss", "pini", "pfim", "pmodo", "atr")   # o "Limpar" tira todos
MAX_VALORES, MAX_TEXTO = 50, 160
_DIA = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class Filtros:
    """Os filtros de cima, já limpos: cada lista com as escolhas (na grafia de quem escolheu; a conta compara sem
    maiúscula), a OS e a Solicitação por "contém", o período (AAAA-MM-DD) com o "considerar" e o Só atrasadas.
    Imutável; entra na chave da cópia guardada da tela (`telas._G_CACHE`) pelo `chave`, normalizado."""
    cliente: tuple = ()
    usina: tuple = ()
    cluster: tuple = ()
    responsavel: tuple = ()
    tipo_tarefa: tuple = ()
    etiqueta: tuple = ()
    estado: tuple = ()
    os: str = ""
    ss: str = ""
    pini: str = ""
    pfim: str = ""
    pmodo: str = "qq"
    atr: bool = False

    def ativos(self) -> bool:
        """Algum filtro valendo (o "considerar" sozinho, sem as datas, não filtra nada)."""
        return bool(any(getattr(self, n) for n, *_ in LISTAS) or self.os or self.ss or self.pini or self.pfim
                    or self.atr)


def _escolhas_da_url(args, nome) -> tuple:
    if hasattr(args, "getlist"):
        brutos = args.getlist(nome)
    else:
        v = (args or {}).get(nome)
        brutos = list(v) if isinstance(v, (list, tuple)) else ([] if v is None else [v])
    out, vistos = [], set()
    for v in brutos:
        s = str(v)[:MAX_TEXTO]
        if s.strip() and s.lower() not in vistos:       # sem a vazia e sem a que só muda na maiúscula
            vistos.add(s.lower())
            out.append(s)
            if len(out) == MAX_VALORES:
                break
    return tuple(out)


def _um(args, nome) -> str:
    v = (args or {}).get(nome)
    return str(v if v is not None else "").strip()[:MAX_TEXTO]       # o gpVal do painel também tira os espaços


def _dia_da_url(args, nome) -> str:
    v = _um(args, nome)
    try:
        return v if _DIA.fullmatch(v) and date.fromisoformat(v) else ""
    except ValueError:                                               # 2026-02-30: o campo de data do painel não deixa
        return ""


def filtros(args) -> Filtros:
    """Os filtros de cima pela URL. Cada lista pode repetir (`?cliente=A&cliente=B`: várias escolhas, como as caixas
    do painel), e o valor único de antes vale igual. Até 50 escolhas por lista e 160 letras por valor; data que não é
    AAAA-MM-DD (ou não existe) e "considerar" desconhecido caem fora."""
    pmodo = _um(args, "pmodo")
    return Filtros(**{n: _escolhas_da_url(args, n) for n, *_ in LISTAS}, os=_um(args, "os"), ss=_um(args, "ss"),
                   pini=_dia_da_url(args, "pini"), pfim=_dia_da_url(args, "pfim"),
                   pmodo=pmodo if pmodo in dict(PMODOS) else "qq", atr=_um(args, "atr") == "1")


def chave(f: Filtros) -> tuple:
    """O filtro como entra na chave da cópia guardada (`telas._G_CACHE`): sem maiúscula, as escolhas de cada lista em
    ordem e o "considerar" sem datas no padrão (sem datas ele não filtra nada). Duas URLs que filtram igual dividem uma
    entrada só (revisão da parte A, 04/11/2026: a memória do servidor é curta). Toda conta guardada compara sem
    maiúscula e não depende da ordem das escolhas; a única marca da grafia é o escolhido sem tarefa no fim da lista, na
    grafia de quem o escolheu primeiro."""
    return (*(tuple(sorted({v.lower() for v in getattr(f, n)})) for n, *_ in LISTAS), f.os.lower(), f.ss.lower(),
            f.pini, f.pfim, f.pmodo if (f.pini or f.pfim) else "qq", f.atr)


# Os escolhidos em etiquetas na barra fechada (Levi, 04/11/2026: os filtros "suspenso e expandível"), cada um com o ×
# que tira só ele: (rótulo, o valor como a tela mostra, o que muda na URL para tirá-lo)
def fichas(f: Filtros, escolhas: dict | None = None) -> list[dict]:
    """As etiquetas dos filtros escolhidos, na ordem da barra: cada valor de cada lista (na grafia da lista, a mais
    frequente), a OS, a Solicitação, o período com o "considerar" e o Só atrasadas. `tirar` vai no `url(**tirar)` da
    tela: a lista sem aquele valor (as outras escolhas ficam), o campo vazio, o período inteiro."""
    out = []
    for nome, _campo, rot, _vazio in LISTAS:
        grafia = {v.lower(): v for v in (escolhas or {}).get(nome) or ()}
        vs = getattr(f, nome)
        for v in vs:
            resto = [x for x in vs if x != v]
            out.append({"rot": rot, "valor": grafia.get(v.lower(), v), "tirar": {nome: resto or None}})
    for nome, rot in (("os", "OS"), ("ss", "Solicitação")):
        if getattr(f, nome):
            out.append({"rot": rot, "valor": getattr(f, nome), "tirar": {nome: None}})
    if f.pini or f.pfim:
        faixa = (f"{data_br(f.pini)} a {data_br(f.pfim)}" if f.pini and f.pfim else
                 f"desde {data_br(f.pini)}" if f.pini else f"até {data_br(f.pfim)}")
        modo = "" if f.pmodo == "qq" else f" · {dict(PMODOS)[f.pmodo].lower()}"
        out.append({"rot": "Período", "valor": faixa + modo, "tirar": {"pini": None, "pfim": None, "pmodo": None}})
    if f.atr:
        out.append({"rot": "Só atrasadas", "valor": "", "tirar": {"atr": None}})
    return out


# A ordem do `localeCompare(…, 'pt-BR')` do painel (o ICU do navegador), nas listas e nas árvores: o espaço e a
# pontuação antes dos dígitos, os dígitos antes das letras; decide a letra sem acento e sem maiúscula, depois o acento
# (sem acento antes) e por último a maiúscula (a minúscula antes). A ordem dos sinais e dos acentos é a do ICU,
# conferida no node (ICU 78, 04/11/2026; `test_a_ordem_das_listas_e_das_arvores_e_a_do_localecompare_do_painel`)
_SINAIS = " _-‐‑‒–—,;:!?.'\"()[]{}§@*/\\&#%`^°+<=>|~$"
_ACENTOS = "̧̨́̀̆̂̌̊̈̋̃̇̄"


def ordem_pt(s) -> tuple:
    letras, acentos, caixa = [], [], []
    for c in unicodedata.normalize("NFKD", str(s or "")):
        if unicodedata.combining(c):
            if acentos:
                acentos[-1] += (_ACENTOS.find(c) if c in _ACENTOS else 100 + ord(c),)
            continue
        b = c.lower()
        letras.append((3, b) if c.isalpha() else (2, b) if c.isdigit() else
                      (0, _SINAIS.index(c)) if c in _SINAIS else (1, ord(c)))
        acentos.append(())
        caixa.append(c != b)
    return letras, acentos, caixa


def _js(v) -> str:
    """O String(v) do JavaScript para um valor do JSON (null vira "null", 2.0 vira "2"): é assim que o painel compara a
    OS e a Solicitação e monta as chaves da árvore."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _campo_js(t, campo) -> str:
    return _js(t[campo]) if campo in t else "undefined"


def _esc_js(v) -> str:
    return "" if v is None else _js(v)                  # o gpEsc do painel: nulo vira texto vazio


@dataclass(frozen=True)
class Recorte:
    """O que os filtros de cima deixam: `todas` (o gpFilteredTarefas do painel: os números, as árvores, o Só atrasadas
    e o Plano & Fila sem Tipo próprio), `sem_tipo` (todos os filtros menos o Tipo de cima: o Plano & Fila com Tipo
    próprio) e `escolhas` (as opções de cada lista, em cascata)."""
    todas: list
    sem_tipo: list
    escolhas: dict


_BIT_TIPO = 1 << [n for n, *_ in LISTAS].index("tipo_tarefa")
_BIT_RESTO = 1 << len(LISTAS)            # a OS, a Solicitação e o período: não são lista e valem para todas


def recortar(tarefas, f: Filtros) -> Recorte:
    """Os filtros de cima (gpFilteredTarefas): dentro de uma lista, qualquer das escolhas; entre as listas, todas; sem
    diferenciar maiúscula (o Fracttal escreve "PA NORTE 01" e "PA Norte 01"); a Etiqueta pega a tarefa com qualquer das
    etiquetas escolhidas; OS e Solicitação por "contém"; o período pega a tarefa se a data do "considerar" (por padrão
    qualquer das três: programada, início ou final) cair na faixa.

    Uma passada só: cada tarefa sai marcada com os filtros em que falha, e daí vêm as três coisas. As listas em cascata
    (Levi, 09/10/2026: "Os filtros tem que se auto filtrar também"): cada uma com os OUTROS filtros aplicados (o filtro
    não restringe a si mesmo), a grafia mais frequente entre as que só mudam na maiúscula e a ordem do localeCompare
    pt-BR (gpMsOptions do painel); o valor escolhido fica na lista mesmo sem tarefa (a tela não esconde o filtro que
    está valendo)."""
    sel = [frozenset(v.lower() for v in getattr(f, n)) for n, *_ in LISTAS]
    ativas = [(i, campo, s) for i, ((_n, campo, *_r), s) in enumerate(zip(LISTAS, sel)) if s]
    q_os, q_ss = f.os.lower(), f.ss.lower()
    datas = ({"prog": ("dataProg",), "ini": ("dataInicio",), "fim": ("dataFinal",)}.get(
        f.pmodo, ("dataProg", "dataInicio", "dataFinal")) if (f.pini or f.pfim) else ())

    def dentro(v) -> bool:
        d = _js(v)[:10] if v else ""
        return bool(d) and not (f.pini and d < f.pini) and not (f.pfim and d > f.pfim)
    contas: list[dict] = [{} for _ in LISTAS]

    def conta(i, t):
        v = t.get(LISTAS[i][1])
        for x in (v if isinstance(v, list) else [v]):
            if x:
                s = _js(x)
                g = contas[i].setdefault(s.lower(), {})
                g[s] = g.get(s, 0) + 1
    todas, sem_tipo = [], []
    for t in tarefas:
        m = 0
        for i, campo, s in ativas:
            if campo == "etiquetas":
                if not any((_js(e) if e else "").lower() in s for e in (t.get("etiquetas") or [])):
                    m |= 1 << i
            elif (_js(t.get(campo)) if t.get(campo) else "").lower() not in s:
                m |= 1 << i
        if ((q_os and q_os not in _campo_js(t, "os").lower()) or (q_ss and q_ss not in _campo_js(t, "ss").lower())
                or (datas and not any(dentro(t.get(c)) for c in datas))):
            m |= _BIT_RESTO
        if m == 0:
            todas.append(t)
            for i in range(len(LISTAS)):
                conta(i, t)
        elif m & (m - 1) == 0 and m != _BIT_RESTO:          # falha só numa lista: conta para ela (não se restringe)
            conta(m.bit_length() - 1, t)
        if f.tipo_tarefa and m & ~_BIT_TIPO == 0:
            sem_tipo.append(t)
    escolhas = {}
    for i, (n, *_r) in enumerate(LISTAS):
        valores = sorted((max(g, key=g.get) for g in contas[i].values()), key=ordem_pt)
        ja = set(contas[i])
        for v in getattr(f, n):
            if v.lower() not in ja:
                ja.add(v.lower())
                valores.append(v)
        escolhas[n] = valores
    return Recorte(todas=todas, sem_tipo=sem_tipo if f.tipo_tarefa else todas, escolhas=escolhas)


def tipo_local(o: "Opcoes", f: Filtros) -> bool:
    """O Tipo do Plano & Fila sobrepõe o Tipo de cima (preventivas.js, gpvTarefasTop): compor os dois daria matriz
    vazia sem explicação (Corretiva em cima e Preventivas no Plano). Com o Todos, o de cima vale."""
    return o.tipo != "todos" and bool(f.tipo_tarefa)


def tarefas_do_plano(rec: Recorte, f: Filtros, local: bool) -> list[dict]:
    """As tarefas do Plano & Fila (a matriz, as pendentes da célula e a Fila do Fracttal), como o gpvTarefasTop do
    painel: as do recorte, sem o Tipo de cima quando o Plano tem Tipo próprio; com o Só atrasadas, só as abertas e
    atrasadas."""
    ts = rec.sem_tipo if local else rec.todas
    return [t for t in ts if t.get("aberta") and t.get("atrasado")] if f.atr else ts


def classificar(t) -> tuple[str, str] | None:
    """(sigla, mês) da tarefa, a regra do painel: preventiva pela sigla no nome e o mês da Data Programada; demanda pelo
    tipo e o mês da CRIAÇÃO; "Teste" e preventiva sem sigla, None. Uma regra só para a matriz e a lista de pendentes."""
    m = _RX.search(str(t.get("tarefa") or ""))
    if m:
        return m.group(1), str(t.get("dataProg") or "")[:7]
    sig = DEMANDA.get(sem_acento(t.get("tipo")))
    return (sig, str(t.get("criacao") or "")[:7]) if sig else None


def base(tarefas, meses_) -> list[dict]:
    """(cliente, usina, cluster, responsável, sigla, mês) -> feitas, total e as OS, na ordem em que aparecem."""
    reg: dict[tuple, dict] = {}
    for t in tarefas:
        sm = classificar(t)
        if not sm:
            continue
        sig, mes = sm
        if mes not in meses_:
            continue
        k = (t.get("cliente") or "—", t.get("usina") or "—", t.get("cluster") or "—", t.get("responsavel") or "—", sig, mes)
        c = reg.setdefault(k, {"f": 0, "t": 0, "os": {}})
        fin = 1 if str(t.get("estado") or "") == "Finalizada" else 0
        c["f"] += fin
        c["t"] += 1
        o = str(t.get("os") or "—")
        p = c["os"].get(o, (0, 0))
        c["os"][o] = (p[0] + fin, p[1] + 1)
    return [{"cli": k[0], "usi": k[1], "clu": k[2], "res": k[3], "sig": k[4], "mes": k[5], "f": c["f"], "t": c["t"],
             # a OS só com o número, sem "#" (convenção do Nexus; o painel escreve "#123"): a ordem não muda
             "os": [f"{o} ({c['os'][o][0]}/{c['os'][o][1]})" for o in sorted(c["os"])]} for k, c in reg.items()]


# ── modo Plano ───────────────────────────────────────────────────────────────────────────────────────────────
def colunas(o: Opcoes, meses_) -> list[str]:
    if eh_demanda(o.tipo) or o.col == "mes":
        return list(meses_)
    if o.tipo == "todos":
        return [*SIGLAS, "CORR"]                        # + o contraponto da demanda
    if o.tipo == "prev":
        return list(SIGLAS)
    return [o.tipo]


def rot_col(c: str) -> str:
    return "Corretivas" if c == "CORR" else (c if c in SIGLAS else rot_mes(c))


def faixa(p) -> str:
    return "nulo" if p is None else ("ok" if p >= 100 else ("crit" if p < 40 else "and"))


def tom(p) -> str:
    """A cor da célula da matriz: a do painel NOVO do PCM (`novo.html`, `gpCel`), que o Levi pediu em 09/10/2026 ("uma
    visão parecida com essa, tanto percentual quanto acompanhamento e destacado por cor"): 90% ou mais verde, de 50% a
    89% âmbar, abaixo de 50% vermelho. A `faixa` (40/100, do `preventivas.js`) segue no dado e na prova."""
    return "nulo" if p is None else ("ok" if p >= 90 else ("and" if p >= 50 else "crit"))


def soma(cels) -> dict:
    o = {"f": 0, "t": 0}
    for c in cels:
        if c:
            o["f"] += c["f"]
            o["t"] += c["t"]
    return o


def pct(c) -> int | None:
    return _round(100 * c["f"] / c["t"]) if c and c["t"] else None


def _pivo(b, o: Opcoes) -> dict:
    fs = [*SIGLAS, "corr", "emerg"] if o.tipo == "todos" else (list(SIGLAS) if o.tipo == "prev" else [o.tipo])
    rs = [r for r in b if r["sig"] in fs]
    if o.mes != "todos":
        rs = [r for r in rs if r["mes"] == o.mes]
    if o.busca:
        q = sem_acento(o.busca)
        rs = [r for r in rs if q in sem_acento(f"{r['usi']} {r['cli']} {r['clu']} {r['res']}")]
    por_sig = o.col == "sig" and not eh_demanda(o.tipo)
    grupos: dict[str, dict] = {}
    for r in rs:
        g = "—" if o.dim == "usi" else {"cli": r["cli"], "clu": r["clu"], "res": r["res"]}[o.dim]
        cel = grupos.setdefault(g, {}).setdefault(r["usi"], {})
        k = ("CORR" if r["sig"] in ("corr", "emerg") else r["sig"]) if por_sig else r["mes"]
        c = cel.setdefault(k, {"f": 0, "t": 0, "os": []})
        c["f"] += r["f"]
        c["t"] += r["t"]
        c["os"] = c["os"] + r["os"]
    return grupos


def _ordenar(itens, o: Opcoes):
    if o.ordem == "nome":
        itens.sort(key=lambda x: sem_acento(x["nome"]), reverse=o.desc)
        return

    def chave(x):
        if o.ordem == "pend":
            return x["tudo"]["t"] - x["tudo"]["f"]
        if o.ordem == "geral":
            return x["tudo"]["f"] / x["tudo"]["t"] if x["tudo"]["t"] else 2
        c = x["cel"].get(o.ordem)
        return (c["f"] / c["t"] if c["t"] else 2) if c else 3
    # o sort do JavaScript é estável e o "desc" inverte a comparação, não a lista: empate fica na ordem de chegada
    itens.sort(key=lambda x: -chave(x) if o.desc else chave(x))


def matriz(b, o: Opcoes, meses_) -> dict:
    """A matriz do modo Plano: grupos (com as usinas), as células por coluna, o Geral e o total."""
    cs = colunas(o, meses_)
    csg = [c for c in cs if c != "CORR"]                # o Geral são as preventivas somadas: a CORR fica fora
    grupos = []
    for g, usinas in _pivo(b, o).items():
        filhos = [{"nome": u, "cel": cel, "tudo": soma(cel.get(c) for c in csg)} for u, cel in usinas.items()]
        cel = {c: soma(f["cel"].get(c) for f in filhos) for c in cs}
        for c in cs:
            cel[c]["os"] = []
        grupos.append({"nome": g, "filhos": filhos, "cel": cel, "tudo": soma(cel[c] for c in csg)})
    _ordenar(grupos, o)
    for g in grupos:
        _ordenar(g["filhos"], o)
    tot = {c: soma(g["cel"][c] for g in grupos) for c in cs}
    return {"cols": cs, "grupos": grupos, "total": {"cel": tot, "tudo": soma(tot[c] for c in csg)},
            "usinas": sum(len(g["filhos"]) for g in grupos)}


def celula(c, sig: str, o: Opcoes, usina=None) -> dict:
    """O que a célula mostra: MPA/MPS em fração (com o drill para a Fila na linha da usina); a CORR em resolvidas/
    criadas; o resto pelo Valor escolhido. `os` é a dica do mouse."""
    if not c or not c["t"]:
        return {"txt": "—", "cls": "nulo", "drill": False, "os": ""}
    p = _round(100 * c["f"] / c["t"])
    os_ = ("OS — " + "   ".join(sorted(set(c["os"])))) if c.get("os") else ""
    # o que a tela mostra no %: o percentual e, ao lado, feitas/total (`p`, `f`, `t`), com o fundo pelo `tom`
    tela = {"p": p, "f": c["f"], "t": c["t"], "tom": tom(p)}
    if sig == "CORR":
        return {"txt": f"{c['f']}/{c['t']}", "cls": faixa(p), "drill": False,
                "os": "corretivas: resolvidas/criadas no período · " + os_, **tela}
    if o.col == "sig" and sig in ("MPA", "MPS") and o.val == "pct":
        return {"txt": f"{c['f']}/{c['t']}", "cls": faixa(p), "drill": bool(usina),
                "os": ("abrir a Fila desta usina · " if usina else "") + os_, **tela}
    v = {"pct": f"{p}%", "pend": c["t"] - c["f"], "fei": c["f"]}.get(o.val, c["t"])
    # Diferença de propósito (revisão de 08/10/2026): o painel põe "sem preventiva no período" em toda célula sem
    # lista de OS, e isso só acontece nas linhas de grupo e no TOTAL GERAL, justamente as que TÊM tarefa ("68%" com a
    # dica dizendo que não há preventiva). Aqui essas células ficam sem dica; a prova desconta essa frase do painel.
    return {"txt": str(v), "cls": faixa(p), "drill": False, "os": os_, **tela}


# ── as tarefas pendentes de uma célula (Levi, 12/10/2026: "Na versão antiga ao clicar em cima do % do que tem pendente
# aparecia as tarefas pendentes, resolva isso por gentileza no Nexus! Faça maior e mais bonito") ─────────────────────
# O status da OS no arquivo do PCM ("Em processo", "Verificação", "Finalizados") na grafia que o card da OS do OS Creator
# usa (o selo e a regra do "Editar" saem dele: rotas.STATUS_COR do clone)
STATUS_DO_CARD = {"em processo": "Em Processo", "verificacao": "Em Verificação", "em verificacao": "Em Verificação",
                  "finalizados": "Concluída", "finalizada": "Concluída", "cancelados": "Cancelada",
                  "cancelada": "Cancelada"}
_STATUS_CLS = {"Em Processo": "info", "Em Verificação": "and", "Concluída": "ok", "Cancelada": "nulo"}
ESTADO_CLS = {"nao iniciada": "and", "em progresso": "info", "pausada": "nulo"}
_PREFIXO = re.compile(r"^\s*\[[^\]]*\]\s*-\s*")
_SIGLA_NO_NOME = re.compile(r"^\s*MP[MSAT]\s*-\s*")


def curto(tarefa) -> str:
    """O nome da tarefa sem o "[Grid Co.] - MPM - " da frente ("Estação Solarimétrica"); o inteiro fica no title."""
    s = _SIGLA_NO_NOME.sub("", _PREFIXO.sub("", str(tarefa or "")))
    return s.strip() or str(tarefa or "").strip()


def pendentes(tarefas, o: Opcoes, meses_, usina: str, col: str) -> dict:
    """As tarefas de uma célula do Plano: a usina × a coluna (a sigla, a "CORR" ou o mês; "*" = as colunas do Geral, a
    conta da coluna Pendentes), com os mesmos recortes da matriz (tipo, mês e busca; os filtros de cima já vêm aplicados
    em `tarefas`). Pendente = tarefa que não está Finalizada (a regra de ouro do painel), então o número bate com o da
    célula. `oss`: as pendentes por OS, as atrasadas primeiro, depois pela Data Programada mais antiga. `feitas_oss`
    (18/10/2026, Levi: a célula de 100% "conseguiria abrir uma barra lateral com uma informação mais fácil de ler"): as
    finalizadas por OS, da que terminou por último para a mais antiga (a `dataFinal` mais nova de cada OS)."""
    cs = colunas(o, meses_)
    alvo = {c for c in cs if c != "CORR"} if col == "*" else {col}
    fs = [*SIGLAS, "corr", "emerg"] if o.tipo == "todos" else (list(SIGLAS) if o.tipo == "prev" else [o.tipo])
    por_sig = o.col == "sig" and not eh_demanda(o.tipo)
    q = sem_acento(o.busca) if o.busca else ""
    feitas = total = 0
    oss: dict[str, dict] = {}
    feitas_oss: dict[str, dict] = {}
    for t in tarefas:
        if str(t.get("usina") or "") != usina:
            continue
        sm = classificar(t)
        if not sm or sm[0] not in fs or sm[1] not in meses_ or (o.mes != "todos" and sm[1] != o.mes):
            continue
        if q and q not in sem_acento(f"{t.get('usina') or '—'} {t.get('cliente') or '—'} {t.get('cluster') or '—'} "
                                      f"{t.get('responsavel') or '—'}"):
            continue
        k = ("CORR" if sm[0] in ("corr", "emerg") else sm[0]) if por_sig else sm[1]
        if k not in alvo:
            continue
        total += 1
        n = str(t.get("os") or "—")
        st = STATUS_DO_CARD.get(sem_acento(t.get("osStatus")).strip(), str(t.get("osStatus") or ""))
        if str(t.get("estado") or "") == "Finalizada":
            feitas += 1
            g = feitas_oss.setdefault(n, {"os": n, "wid": t.get("idWO"), "status": st,
                                          "status_cls": _STATUS_CLS.get(st, "nulo"), "url": str(t.get("url") or ""),
                                          "fim": "", "tarefas": []})
            fim = str(t.get("dataFinal") or "")[:10]
            if fim > g["fim"]:
                g["fim"] = fim
            g["tarefas"].append({"tarefa": str(t.get("tarefa") or ""), "curto": curto(t.get("tarefa")),
                                 "sig": sm[0].upper() if sm[0] in SIGLAS else ROT_TIPO.get(sm[0], "")})
            continue
        g = oss.setdefault(n, {"os": n, "wid": t.get("idWO"), "status": st, "status_cls": _STATUS_CLS.get(st, "nulo"),
                               "url": str(t.get("url") or ""), "programada": "", "atrasada": False, "tarefas": []})
        prog = str(t.get("dataProg") or "")[:10]
        if prog and (not g["programada"] or prog < g["programada"]):
            g["programada"] = prog
        g["atrasada"] = g["atrasada"] or bool(t.get("atrasado"))
        estado = str(t.get("estado") or "—")
        g["tarefas"].append({"tarefa": str(t.get("tarefa") or ""), "curto": curto(t.get("tarefa")), "sig": sm[0].upper()
                             if sm[0] in SIGLAS else ROT_TIPO.get(sm[0], ""), "estado": estado,
                             "cls": ESTADO_CLS.get(sem_acento(estado).strip(), "nulo"),
                             "responsavel": str(t.get("responsavel") or "")})
    ordem_estado = {"info": 0, "nulo": 1, "and": 2}
    for g in oss.values():
        # a mesma atividade em vários ativos da OS ("QGBT" quatro vezes: o arquivo não traz o ativo) vira UMA linha com
        # quantas são (`n`); a conta de pendentes segue tarefa a tarefa
        juntas: dict[tuple, dict] = {}
        for x in g["tarefas"]:
            j = juntas.setdefault((x["curto"], x["estado"], x["sig"]), dict(x, n=0))
            j["n"] += 1
        g["tarefas"] = sorted(juntas.values(), key=lambda x: (ordem_estado.get(x["cls"], 3), sem_acento(x["curto"])))
        g["fechada"] = g["status"] == "Concluída"
    lista = sorted(oss.values(), key=lambda g: (not g["atrasada"], g["programada"] or "9999", g["os"]))
    for g in feitas_oss.values():
        juntas = {}
        for x in g["tarefas"]:
            j = juntas.setdefault((x["curto"], x["sig"]), dict(x, n=0))
            j["n"] += 1
        g["tarefas"] = sorted(juntas.values(), key=lambda x: sem_acento(x["curto"]))
    feitas_lista = sorted(feitas_oss.values(), key=lambda g: (g["fim"] or "0000", g["os"]), reverse=True)
    tarefas_p = [x for g in lista for x in g["tarefas"] for _ in range(x["n"])]
    return {"usina": usina, "col": col, "oss": lista, "n_os": len(lista), "n_tarefas": len(tarefas_p),
            "feitas_oss": feitas_lista,
            "feitas": feitas, "total": total, "pct": _round(100 * feitas / total) if total else None,
            "atrasadas": sum(1 for g in lista if g["atrasada"]),
            # (estado, quantas, classe da cor), na ordem do andamento: em progresso, pausada, não iniciada
            "por_estado": sorted(((e, sum(1 for x in tarefas_p if x["estado"] == e),
                                   ESTADO_CLS.get(sem_acento(e).strip(), "nulo")) for e in {x["estado"] for x in tarefas_p}),
                                 key=lambda x: (ordem_estado.get(x[2], 3), x[0]))}


def plano(b, o: Opcoes, meses_, mapa: dict | None = None) -> dict:
    """A matriz pronta para a tela: cada linha com as células (`tds`), o Geral e, com a Gerencial aberta, a
    criticidade e a última observação da usina (`co`). É isto que a prova compara com o painel, célula a célula."""
    mx = matriz(b, o, meses_)
    for g in mx["grupos"]:
        g["tds"] = [celula(g["cel"][c], c, o) for c in mx["cols"]]
        g["geral"] = pct(g["tudo"])
        for f in g["filhos"]:
            f["tds"] = [celula(f["cel"].get(c), c, o, f["nome"]) for c in mx["cols"]]
            f["geral"] = pct(f["tudo"])
            co = achar(mapa, f["nome"]) if mapa is not None else None
            f["co"] = dict(co, critCls=crit_cls(co["crit"])) if co else None
    mx["total"]["tds"] = [celula(mx["total"]["cel"][c], c, o) for c in mx["cols"]]
    mx["total"]["geral"] = pct(mx["total"]["tudo"])
    return mx


# ── Gerencial (mpas.json cifrado) ────────────────────────────────────────────────────────────────────────────
def decifrar(pack: dict, senha: str) -> dict:
    """AES-GCM + PBKDF2-SHA256, o mesmo do painel (gerar_mpas_json.py). Senha errada levanta exceção."""
    b = base64.b64decode
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b(pack["salt"]),
                       iterations=int(pack["iter"])).derive(senha.encode("utf-8"))
    return json.loads(AESGCM(chave).decrypt(b(pack["iv"]), b(pack["ct"]), None).decode("utf-8"))


def crit_obs(mp: dict) -> dict:
    """Usina normalizada -> criticidade (a da MPA vence) e a última observação datada, para a coluna do Plano."""
    mapa: dict[str, dict] = {}

    def grava(k, it):
        if not k:
            return
        prev = mapa.setdefault(k, {"crit": "", "obs": ""})
        if it.get("criticidade") and (not prev["crit"] or "MPA" in str(it.get("tipo") or "").upper()):
            prev["crit"] = it["criticidade"]
        ob = ultima_obs(it.get("obs"))
        if ob and (not prev["obs"] or _k_data(ob) >= _k_data(prev["obs"])):
            prev["obs"] = ob
    for it in (mp or {}).get("manut") or (mp or {}).get("itens") or []:
        grava(norm(it.get("usina")), it)
        curta = norm(((it.get("cliente") + " ") if it.get("cliente") else "") + str(it.get("usina_curta") or ""))
        if curta and curta != norm(it.get("usina")):
            grava(curta, it)
    return mapa


def achar(mapa: dict, nome_usina) -> dict | None:
    k = norm(nome_usina)
    if k in mapa:
        return mapa[k]
    return next((v for kk, v in mapa.items() if bate(kk, k)), None)


_SIT_CLS = {"Concluída": "ok", "Em andamento": "info", "Não iniciada": "and", "Atrasada": "crit"}


def _sit(m: dict, bd: dict, h: date) -> dict:
    """A situação da manutenção da Gerencial (mpSit do painel): a do Fracttal quando a OS tem par, senão o status da
    planilha; não concluída com a Prevista vencida = Atrasada."""
    b = bd.get(str(m.get("os") or "").strip()) if str(m.get("os") or "").strip() else None
    if b and b.get("sit"):
        k = b["sit"]
    else:
        st = str(m.get("status") or "").lower()
        k = "Concluída" if st.startswith("finaliz") else ("Em andamento" if st.startswith("em execu") else "Não iniciada")
    if k != "Concluída" and m.get("prevista") and m["prevista"] < h.isoformat():
        k = "Atrasada"
    return {"k": k, "cls": _SIT_CLS.get(k, "nulo")}


def fila_gerencial(mp: dict, h: date) -> list[dict]:
    hj, bd = h.isoformat(), (mp or {}).get("bd") or {}
    out = []
    for m in (mp or {}).get("manut") or []:
        tipo = "MPS" if "MPS" in str(m.get("tipo") or "").upper() else "MPA"
        # a célula OS da Gerencial pode trazer VÁRIAS OS ("123/456"): a Programada é a mais cedo e as tarefas somam
        partes = [x.strip() for x in re.split(r"[/,;]", str(m.get("os") or "")) if x.strip()]
        bds = [bd[p] for p in partes if bd.get(p)]
        prog = None
        for b in bds:
            for t in b.get("tasks") or []:
                if t.get("prog") and (not prog or t["prog"] < prog):
                    prog = t["prog"]
        fin = sum(b.get("fin") or 0 for b in bds) if bds else None
        tot = sum(b.get("total") or 0 for b in bds) if bds else None
        os_ = " / ".join(partes)
        sit = _sit(m, bd, h)
        conclu = sit["k"] == "Concluída"
        prev = m.get("prevista") or None
        obs = ultima_obs(m.get("obs"))
        od = _DATA.search(obs)
        obs_iso = f"{od.group(3)}-{od.group(2)}-{od.group(1)}" if od else None
        cc = crit_cls(m.get("criticidade"))
        dp, dg = dias(prev, h), dias(prog, h)
        out.append({
            "nome": (m["cliente"] + " – " if m.get("cliente") else "") + str(m.get("usina_curta") or m.get("usina") or "—"),
            "usinaFull": m.get("usina") or "", "cli": m.get("cliente") or "", "clu": m.get("cluster") or "",
            "tipo": tipo, "crit": m.get("criticidade") or "", "critCls": cc, "prev": prev, "prog": prog,
            "atraso": dias(prev, h) if (not conclu and prev and prev < hj) else None,
            "os": os_, "semOS": not os_, "osSemPar": bool(os_) and not bds, "semData": bool(bds) and not prog,
            # "crítica sem data futura": alta/crítica, não concluída e sem programação à frente (mede o funil)
            "critSemData": not conclu and cc == "crit" and (not prog or prog < hj),
            "sit": sit, "conclu": conclu, "obs": obs, "obsIso": obs_iso,
            # o texto da coluna sem a data do começo (a data vai em negrito, à parte, como no painel)
            "obsTxt": _OBS_DATA.sub("", obs, count=1),
            "obsVelha": bool(obs_iso) and (dias(obs_iso, h) or 0) > 60,
            "equipe": str(m.get("equipe") or "").split("\n")[0], "apoio": m.get("apoio") or "",
            "statusPlan": m.get("status") or "", "bdFin": fin, "bdTot": tot,
            # data inválida na planilha: o painel dá NaN e não marca; aqui, sem os dois dias, também não
            "diverge": dp is not None and dg is not None and abs(dp - dg) > 30})
    return out


_OBS_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}\s*[-–—:]*\s*")


def fila_topo_ok(x: dict, f: Filtros) -> bool:
    """Os filtros de cima nas linhas da Gerencial (gpvFilaTopOk do painel): Cliente, Usina e Cluster pela comparação
    frouxa (os nomes divergem do Fracttal), qualquer das escolhas; a OS por "contém"; o período pela Prevista OU pela
    Programada (o "considerar" não vale aqui); o Só atrasadas. Responsável, Tipo, Etiqueta, Estado e Solicitação não
    existem na Gerencial e não filtram a Fila (painel)."""
    def algum(escolhas, valores):
        return any(bate(norm(s), norm(v)) for s in escolhas for v in valores if v)
    if f.cliente and not algum(f.cliente, [x.get("cli")]):
        return False
    if f.usina and not algum(f.usina, [x.get("usinaFull"), x.get("nome")]):
        return False
    if f.cluster and not algum(f.cluster, [x.get("clu")]):
        return False
    if f.os and f.os.lower() not in str(x.get("os") or "").lower():
        return False
    if f.pini or f.pfim:
        def dentro(d):
            return bool(d) and (not f.pini or d >= f.pini) and (not f.pfim or d <= f.pfim)
        if not dentro(x.get("prev")) and not dentro(x.get("prog")):
            return False
    return not (f.atr and x["sit"]["k"] != "Atrasada")


def fila_universo(tarefas, mp, f: Filtros, h: date) -> list[dict]:
    """Todas as linhas da Fila antes dos filtros do bloco: as da Gerencial (com os filtros de cima) quando a planilha
    abriu, senão o lado do Fracttal, já recortado pelos filtros de cima em `tarefas` (`tarefas_do_plano`)."""
    if mp is not None:
        return [x for x in fila_gerencial(mp, h) if fila_topo_ok(x, f)]
    return fila_fracttal(tarefas, h)


def fila_fracttal(tarefas, h: date) -> list[dict]:
    """Sem a Gerencial: só o lado do Fracttal, uma linha por OS de MPA/MPS; atraso pela Programada."""
    hj, por_os = h.isoformat(), {}
    for t in tarefas:
        m = _RX.search(str(t.get("tarefa") or ""))
        if not m or m.group(1) not in ("MPA", "MPS"):
            continue
        os_ = str(t.get("os") or "").strip()
        if not os_:
            continue
        r = por_os.setdefault(os_, {"os": os_, "tipo": m.group(1), "prog": None, "tot": 0, "fin": 0, "andamento": False,
                                    "nome": (t["cliente"] + " – " if t.get("cliente") else "") + str(t.get("usina") or "—")})
        r["tot"] += 1
        est = str(t.get("estado") or "")
        r["fin"] += est == "Finalizada"
        r["andamento"] = r["andamento"] or "progress" in est.lower()
        d = str(t.get("dataProg") or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and (not r["prog"] or d < r["prog"]):
            r["prog"] = d
    out = []
    for r in por_os.values():
        conclu = r["tot"] > 0 and r["fin"] == r["tot"]
        k = "Concluída" if conclu else ("Em andamento" if (r["andamento"] or r["fin"] > 0) else "Não iniciada")
        atrasada = not conclu and r["prog"] and r["prog"] < hj
        if atrasada:
            k = "Atrasada"
        out.append({"nome": r["nome"], "usinaFull": "", "cli": "", "clu": "", "tipo": r["tipo"], "crit": "", "critCls": "",
                    "prev": None, "prog": r["prog"], "atraso": dias(r["prog"], h) if atrasada else None,
                    "os": r["os"], "semOS": False, "osSemPar": False, "semData": not r["prog"], "critSemData": False,
                    "sit": {"k": k, "cls": _SIT_CLS[k]}, "conclu": conclu, "obs": "", "obsIso": None, "obsVelha": False,
                    "equipe": "", "apoio": "", "statusPlan": "", "bdFin": r["fin"], "bdTot": r["tot"], "diverge": False})
    return out


def fila_filtrada(fila, o: Opcoes) -> list[dict]:
    ls = list(fila)
    if o.drill_usina:
        alvo = norm(o.drill_usina)
        ls = [x for x in ls if (bate(norm(x["nome"]), alvo) or bate(norm(x["usinaFull"]), alvo))
              and (not o.drill_tipo or x["tipo"] == o.drill_tipo)]
    if o.tipo in ("MPA", "MPS"):
        ls = [x for x in ls if x["tipo"] == o.tipo]
    filtro = {"atraso": lambda x: x["sit"]["k"] == "Atrasada", "semos": lambda x: (x["semOS"] or x["osSemPar"]) and not x["conclu"],
              "critsem": lambda x: x["critSemData"], "concl": lambda x: x["conclu"]}.get(o.pend)
    if filtro:
        ls = [x for x in ls if filtro(x)]
    if o.busca:
        q = sem_acento(o.busca)
        ls = [x for x in ls if q in sem_acento(f"{x['nome']} {x['os']}")]
    # "tipo": no painel o cabeçalho Tipo é clicável mas a chave não existe e a lista cai na ordem da Prevista (sem a
    # Gerencial, nem se mexe). Aqui ordena pelo Tipo de verdade (revisão de 08/10/2026; a prova não compara esse caso)
    chave = {"prog": lambda x: x["prog"] or "9999", "atraso": lambda x: -(x["atraso"] or -1),
             "nome": lambda x: x["nome"].lower(), "crit": lambda x: {"crit": 0, "and": 1, "ok": 2}.get(x["critCls"], 3),
             "tipo": lambda x: x["tipo"]}.get(o.ordem_f, lambda x: x["prev"] or "9999")
    ls.sort(key=chave, reverse=o.desc_f)
    return ls


def faixa_atraso(d) -> str:
    return "" if d is None or d <= 0 else ("f1" if d <= 30 else ("f2" if d <= 90 else "f3"))


def kpis_fila(fila) -> dict:
    return {"atraso": sum(x["sit"]["k"] == "Atrasada" for x in fila),
            "semos": sum((x["semOS"] or x["osSemPar"]) and not x["conclu"] for x in fila),
            "critsem": sum(x["critSemData"] for x in fila), "concl": sum(x["conclu"] for x in fila), "total": len(fila)}


def par_topo(b, meses_, fila=None) -> dict:
    """O PAR de números do topo (nunca média única): Rotina = MPM+MPT do mês corrente; as grandes atrasadas (e a
    mais antiga) e as críticas sem data futura. Sem a Gerencial, `fila` é o lado do Fracttal: as atrasadas são pela
    Data Programada e criticidade não existe (a tela diz isso; o painel, nesse caso, só mostra o cadeado)."""
    rot = soma(r for r in b if r["sig"] in ("MPM", "MPT") and r["mes"] == meses_[2])
    out = {"mes": meses_[2], "rotina": pct(rot)}
    if fila is not None:
        atr = [x for x in fila if x["sit"]["k"] == "Atrasada"]
        k = kpis_fila(fila)
        out.update(atrasadas=len(atr), mais_antiga=max((x["atraso"] or 0 for x in atr), default=0),
                   crit_sem_data=k["critsem"], sem_os=k["semos"])
    return out


# ── a aba Gestão PCM do painel além do Plano & Fila (Levi, 04/11/2026): os números do alto, as árvores Cliente ▸ Usina
# ▸ Tipo e o Só atrasadas, transcritos do js/app.js (renderGestao, gpTreeHTML, gpTableHTML, gpFlatHTML) ──────────────
ABRE_SOZINHA = 60          # a árvore principal abre sozinha, com as tabelas cheias, até 60 tarefas (renderGestao)
_TIPO_CLASSE = (("emergencial", "emergencial"), ("corretiva", "corretiva"), ("preventiva", "preventiva"),
                ("handover", "handover"), ("religa", "religamento"), ("inspe", "inspecao"), ("predit", "preditiva"),
                ("admin", "administrativa"))


def nao_finalizada(t) -> bool:
    """"Não finalizada no período" (gpNaoFin): a OS já está Finalizados no Fracttal e a tarefa ficou em aberto. Vai numa
    lista à parte e fica fora dos números do alto."""
    return t.get("osStatus") == "Finalizados" and bool(t.get("aberta"))


def tipo_classe(tipo) -> str:
    """A família do tipo na árvore, para a cor (gpTipoClass do painel, pelo pedaço do nome; Zeladoria e o resto,
    "outra")."""
    x = str(tipo or "").lower()
    return next((c for k, c in _TIPO_CLASSE if k in x), "outra")


def estado_cls(estado) -> str:
    """A cor do estado da tarefa (gpEstadoPill do painel) nas classes do Nexus: em progresso info, pausada nulo,
    finalizada ok e o resto (não iniciada) âmbar."""
    x = str(estado or "").lower()
    return "info" if "progress" in x else ("nulo" if "paus" in x else ("ok" if "finaliz" in x else "and"))


def data_br(iso) -> str:
    """A data como a árvore e o Só atrasadas do painel mostram (gpFmtData): dd/mm/aaaa; sem data, "—"."""
    if not iso:
        return "—"
    p = str(iso).split("-")
    return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else str(iso)


def _card(t) -> dict:
    """O que abre a OS: o card dela no Nexus (o id do Fracttal e o status na grafia do card, como nas pendentes) e o
    Fracttal no ícone (a `url` da tarefa: o painel abre só o módulo de OS, porque achava que não havia link por OS)."""
    st = str(t.get("osStatus") or "")
    return {"os": _esc_js(t.get("os")), "wid": t.get("idWO"), "status": STATUS_DO_CARD.get(sem_acento(st).strip(), st),
            "url": str(t.get("url") or "")}


def linha_tarefa(t, dias_alerta: int = 10) -> dict:
    """Uma linha da tabela de um tipo da árvore (gpTableHTML): a OS (sem "#", convenção do Nexus), a tarefa, o estado,
    até três etiquetas e quantas mais, as datas no dd/mm/aaaa do painel e os dias em aberto (gpDiasCell: acima do
    diasAlerta vermelho, de 5 em diante âmbar; finalizada, sem dias ou com dias negativos, "—")."""
    d, etq = t.get("dias"), list(t.get("etiquetas") or [])
    if not t.get("aberta") or d is None or d < 0:
        dias, dias_cls = "—", "ok"
    else:
        dias, dias_cls = _js(d) + "d", ("crit" if d > dias_alerta else ("and" if d >= 5 else "ok"))
    return {**_card(t), "tarefa": str(t.get("tarefa") or "—"), "curto": curto(t.get("tarefa")),
            "estado": str(t.get("estado") or "—"), "estado_cls": estado_cls(t.get("estado")),
            "etiquetas": [_esc_js(e) for e in etq[:3]], "etiquetas_mais": max(0, len(etq) - 3),
            "prog": data_br(t.get("dataProg")), "fim": data_br(t.get("dataFinal")), "dias": dias, "dias_cls": dias_cls}


def linha_atrasada(t, dias_alerta: int = 10) -> dict:
    """Uma linha do Só atrasadas (gpFlatHTML): os dias (sem dias, 0; acima do diasAlerta vermelho, de 5 em diante
    âmbar), a OS, o cliente, a usina, a tarefa, o tipo, o estado, a Data Programada, TODAS as etiquetas e a
    observação da OS."""
    d = t["dias"] if t.get("dias") is not None else 0
    return {**_card(t), "dias": _js(d) + "d", "dias_cls": "crit" if d > dias_alerta else ("and" if d >= 5 else ""),
            "cliente": _esc_js(t.get("cliente")), "usina": _esc_js(t.get("usina")),
            "tarefa": str(t.get("tarefa") or "—"), "curto": curto(t.get("tarefa")), "tipo": str(t.get("tipo") or "—"),
            "estado": str(t.get("estado") or "—"), "estado_cls": estado_cls(t.get("estado")),
            "prog": data_br(t.get("dataProg")), "etiquetas": [_esc_js(e) for e in (t.get("etiquetas") or [])],
            "obs": str(t.get("obs") or "")}


def _pelos_dias(ts) -> list[dict]:
    """As abertas pelos dias em aberto, as mais velhas primeiro; as outras (finalizadas e sem dias) depois, na ordem do
    arquivo (o sort do painel é estável)."""
    return sorted(ts, key=lambda t: -(t["dias"] if t.get("aberta") and t.get("dias") is not None else -1e9))


def arvore(lista, dias_alerta: int = 10, linhas: bool = False) -> list[dict]:
    """A árvore Cliente ▸ Usina ▸ Tipo (gpTreeHTML), cada nível na ordem do localeCompare pt-BR, com quantas tarefas
    cada nó tem e, no tipo, quantas estão atrasadas. Com `linhas` (a árvore que o painel abre sozinha), cada tipo leva
    as linhas da tabela dele; sem, a tabela vem pela rota (`tarefas_do_no`): 31 mil tarefas não vão na página."""
    clientes: dict[str, dict] = {}
    for t in lista:
        c = clientes.setdefault(_campo_js(t, "cliente"), {"n": 0, "usinas": {}})
        u = c["usinas"].setdefault(_campo_js(t, "usina"), {"n": 0, "tipos": {}})
        u["tipos"].setdefault(_campo_js(t, "tipo"), []).append(t)
        c["n"] += 1
        u["n"] += 1
    out = []
    for cn in sorted(clientes, key=ordem_pt):
        usinas = []
        for un in sorted(clientes[cn]["usinas"], key=ordem_pt):
            u, tipos = clientes[cn]["usinas"][un], []
            for tn in sorted(u["tipos"], key=ordem_pt):
                ts = u["tipos"][tn]
                no = {"nome": tn, "n": len(ts), "atrasadas": sum(1 for t in ts if t.get("atrasado")),
                      "classe": tipo_classe(tn)}
                if linhas:
                    no["linhas"] = [linha_tarefa(t, dias_alerta) for t in _pelos_dias(ts)]
                tipos.append(no)
            usinas.append({"nome": un, "n": u["n"], "tipos": tipos})
        out.append({"nome": cn, "n": clientes[cn]["n"], "usinas": usinas})
    return out


def tarefas_do_no(lista, cliente, usina, tipo, dias_alerta: int = 10) -> list[dict] | None:
    """As linhas da tabela de UM tipo da árvore (Cliente ▸ Usina ▸ Tipo), na ordem do painel. None = o nó não existe."""
    ts = [t for t in lista if _campo_js(t, "cliente") == cliente and _campo_js(t, "usina") == usina
          and _campo_js(t, "tipo") == tipo]
    return [linha_tarefa(t, dias_alerta) for t in _pelos_dias(ts)] if ts else None


def aba(todas, dias_alerta: int = 10, so_atrasadas: bool = False) -> dict:
    """A aba Gestão PCM do painel (renderGestao) sobre as tarefas dos filtros de cima: os números do alto (Visíveis =
    Finalizadas + Em aberto, sem as "Não Finalizadas no Período", que vão à parte; Atrasadas = as abertas e atrasadas),
    as duas árvores (a das não finalizadas no período, que abre fechada, e a principal, aberta até 60 tarefas) e, no
    Só atrasadas, a lista plana das mais velhas para as mais novas, só da visão principal (como no painel)."""
    nf = [t for t in todas if nao_finalizada(t)]
    arr = [t for t in todas if not nao_finalizada(t)]
    ab = [t for t in arr if t.get("aberta")]
    atr = [t for t in ab if t.get("atrasado")]
    fin, aberta = len(arr) - len(ab), len(arr) <= ABRE_SOZINHA
    return {"nf": nf, "arr": arr,
            "numeros": {"todas": len(todas), "visiveis": len(arr), "finalizadas": fin, "em_aberto": len(ab),
                        "atrasadas": len(atr), "nf": len(nf),
                        "pct_finalizadas": _round(fin / len(arr) * 100) if arr else 0},
            "arvores": {"nf": {"n": len(nf), "clientes": arvore(nf, dias_alerta)},
                        "todas": {"n": len(arr), "aberta": aberta,
                                  "clientes": arvore(arr, dias_alerta, linhas=aberta)}},
            "so_atrasadas": ([linha_atrasada(t, dias_alerta) for t in sorted(atr, key=lambda t: -(t.get("dias") or 0))]
                             if so_atrasadas else None)}


# As mensagens da aba (renderGestao e gpFlatHTML do painel), as mesmas na tela e na prova: o texto que a tela mostra é
# o que a prova confere contra o painel (revisão da parte A: a prova tinha a sua cópia, e a tela podia mudar sozinha)
MSG_SEM_TAREFA = "Nenhuma tarefa para os filtros selecionados."
MSG_SO_NF = "Sem tarefas na visão principal (só há não finalizadas no período)."
MSG_SEM_ATRASADA = "Nenhuma tarefa atrasada nos filtros atuais."      # o painel abre com um emoji; aqui, sem
PAGINA_ATRASADAS = 100      # o Só atrasadas vem em partes: sem filtro são ~2,2 mil linhas, que não vão de uma vez


def dica_finalizadas(numeros: dict) -> str:
    """A dica das Finalizadas no alto (o title do `gp-kpi-fin` do painel): o % do que está visível e, quando há, as "Não
    Finalizadas no Período" que ficam fora da conta."""
    dica = f"Estado da Tarefa = Finalizada · {numeros['pct_finalizadas']}% do que está visível"
    if numeros.get("nf"):
        dica += f' (as {numeros["nf"]} de "Não Finalizadas no Período" ficam fora desta conta)'
    return dica


def atualizado(d: dict) -> str:
    """A linha debaixo do título da aba (renderGestao): "Atualizado: <geradoEm> · corte <corteData> · fonte: API
    Fracttal", no formato do toLocaleString('pt-BR') do painel. Diferença de propósito: a hora de Brasília (o robô grava
    o geradoEm em UTC sem fuso e o painel o mostra como se fosse hora local: 20:50 lá é 17:50 aqui)."""
    g = d.get("geradoEm")
    try:
        quando = datetime.fromisoformat(str(g)) if g else agora()
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
        txt = f"{quando.astimezone(_BRT):%d/%m/%Y, %H:%M:%S}"
    except ValueError:
        txt = "—"
    return f"Atualizado: {txt} · corte {data_br(d.get('corteData'))} · fonte: API Fracttal"
