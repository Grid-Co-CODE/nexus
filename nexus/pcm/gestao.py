"""Gestão PCM: o bloco "Manutenções — Plano & Fila" do painel do PCM, no Nexus.

Levi (07/10/2026): "quero que traga a visão de acompanhamento de manutenção do aplicativo para o Nexus conforme prints".
É a transcrição das contas do `js/preventivas.js` do gridco-pcm-data (pcm.gridco.com.br, aba Gestão PCM), para os
números do Nexus baterem com os do painel: a prova (`python -m nexus.pcm.prova_gestao`) roda o próprio JavaScript do
painel contra o mesmo JSON e compara célula a célula (ver nexus/pcm/CLAUDE.md). Mudou a regra lá? Mude aqui e rode a
prova de novo.

Diferenças de propósito: a OS sem "#" (convenção do Nexus); o "hoje" em Brasília (o painel usa o dia UTC para
"atrasada", e entre 21h e meia-noite já conta o dia seguinte); a célula de grupo e do TOTAL sem a dica falsa "sem
preventiva no período"; e o cabeçalho Tipo da Fila ordena pelo tipo (no painel ele não ordena nada).

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


TOPO = ("cliente", "usina", "cluster", "responsavel")      # os filtros de cima que o Nexus traz da aba do painel


def escolhas_topo(tarefas) -> dict[str, list[str]]:
    """As opções de cada filtro de cima. Grafias que só mudam na maiúscula viram UMA, a mais frequente (painel:
    "PA Norte 01" × "PA NORTE 01"); o filtro compara sem maiúscula, então qualquer uma pega as duas."""
    out = {}
    for campo in TOPO:
        por_baixa: dict[str, dict[str, int]] = {}
        for t in tarefas:
            v = t.get(campo)
            if v:
                g = por_baixa.setdefault(str(v).lower(), {})
                g[str(v)] = g.get(str(v), 0) + 1
        out[campo] = sorted((max(g, key=g.get) for g in por_baixa.values()), key=sem_acento)
    return out


def filtrar_topo(tarefas, cliente="", cluster="", responsavel="", usina="") -> list[dict]:
    """Os filtros de cima da aba (no painel, multisseleção; aqui, um de cada), sem diferenciar maiúscula
    (o Fracttal escreve "PA NORTE 01" e "PA Norte 01")."""
    c, k, r, u = (str(x or "").lower() for x in (cliente, cluster, responsavel, usina))
    return [t for t in tarefas if (not c or str(t.get("cliente") or "").lower() == c)
            and (not u or str(t.get("usina") or "").lower() == u)
            and (not k or str(t.get("cluster") or "").lower() == k)
            and (not r or str(t.get("responsavel") or "").lower() == r)]


def base(tarefas, meses_) -> list[dict]:
    """(cliente, usina, cluster, responsável, sigla, mês) -> feitas, total e as OS, na ordem em que aparecem."""
    reg: dict[tuple, dict] = {}
    for t in tarefas:
        m = _RX.search(str(t.get("tarefa") or ""))
        if m:
            sig, mes = m.group(1), str(t.get("dataProg") or "")[:7]
        else:
            sig = DEMANDA.get(sem_acento(t.get("tipo")))
            if not sig:
                continue
            mes = str(t.get("criacao") or "")[:7]
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
    if sig == "CORR":
        return {"txt": f"{c['f']}/{c['t']}", "cls": faixa(p), "drill": False,
                "os": "corretivas: resolvidas/criadas no período · " + os_}
    if o.col == "sig" and sig in ("MPA", "MPS") and o.val == "pct":
        return {"txt": f"{c['f']}/{c['t']}", "cls": faixa(p), "drill": bool(usina),
                "os": ("abrir a Fila desta usina · " if usina else "") + os_}
    v = {"pct": f"{p}%", "pend": c["t"] - c["f"], "fei": c["f"]}.get(o.val, c["t"])
    # Diferença de propósito (revisão de 08/10/2026): o painel põe "sem preventiva no período" em toda célula sem
    # lista de OS, e isso só acontece nas linhas de grupo e no TOTAL GERAL, justamente as que TÊM tarefa ("68%" com a
    # dica dizendo que não há preventiva). Aqui essas células ficam sem dica; a prova desconta essa frase do painel.
    return {"txt": str(v), "cls": faixa(p), "drill": False, "os": os_}


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


def fila_topo_ok(x: dict, cliente="", cluster="", usina="", **_) -> bool:
    """Os filtros de cima nas linhas da Gerencial: os nomes divergem do Fracttal, então a comparação é frouxa.
    Responsável não existe na Gerencial e não filtra a Fila (painel)."""
    if cliente and not bate(norm(cliente), norm(x.get("cli"))):
        return False
    if usina and not any(bate(norm(usina), norm(v)) for v in (x.get("usinaFull"), x.get("nome"))):
        return False
    return not (cluster and not bate(norm(cluster), norm(x.get("clu"))))


def fila_universo(tarefas, mp, topo: dict, h: date) -> list[dict]:
    """Todas as linhas da Fila antes dos filtros do bloco: as da Gerencial (com os filtros de cima) quando a planilha
    abriu, senão o lado do Fracttal, já recortado pelos filtros de cima em `tarefas`."""
    if mp is not None:
        return [x for x in fila_gerencial(mp, h) if fila_topo_ok(x, **topo)]
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
