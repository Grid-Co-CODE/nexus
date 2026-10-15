"""Os dados do Acompanhamento do PCM: as cinco abas do painel do PCM O&M (MPA, MPS, Radar de Backlog, Mapa e One Page),
montadas com as fontes que o Nexus JÁ usa nas telas donas de cada número (14/10/2026).

Levi, 14/10/2026, com o pacote de integração do painel: "Quero que libere na seção de PCM essa visão de acompanhamento.
O design quero alá Nexus, não quero que copie o design, mas as estruturas quero sim que mantenha!". O contrato de saída é
o do painel (`DATA`, `EXTRA` e `COLAB`, seção 6 do INTEGRACAO.md do pacote), para a tela manter as estruturas; o que muda
é DE ONDE vem cada número (regra do Nexus centralizado, 12/10/2026: o número de uma tela é o da tela dona dele):

- o Fracttal vem do `gestao_pcm.json` (a Gestão PCM), e não de 4 consultas SQL feitas à mão: a OS "em processo" é o
  `osStatus` "Em processo", a tarefa feita é o `estado` "Finalizada" (a mesma régua da Gestão PCM);
- a programação semanal vem do `banco_dados.json` (as 4 semanas que o Nexus gera e publica), e "executada" é a regra
  do Fechamento da semana do Nexus (`relatorios.regras.fin`), não o casamento OS + código do painel (o próprio painel
  avisa que o dele diverge do relatório oficial: 31% contra 63% na semana 41);
- a Gerencial (aba MPAS) vem do `mpas.json`, aberto pelo servidor com a `NEXUS_PCM_MPAS_SENHA`, e o atraso de cada
  MPA/MPS é o da Fila da Gestão PCM (`gestao.fila_gerencial`), não o da agenda do Painel MPAs e MPSs (outro projeto,
  fora do Nexus). A coluna "Bloqueios para finalização" ainda não vem no mpas.json: o bloqueio fica o da curadoria;
- as usinas no mapa vêm do cadastro do Nexus (coordenada que NUNCA sai do servidor: o navegador recebe o ponto já
  desenhado e as distâncias prontas), as equipes, das pessoas ativas do cadastro (só nome, cargo e cluster: LGPD), e o
  supervisor de cada cluster, do Supervisor de Campo da equipe;
- a curadoria do PCM (grupo, prazo, o que falta: decisão da reunião de PCM) vem do banco (`curadoria.py`).

Tudo aqui é conta pura sobre o que já foi lido: as leituras moram em `__init__.py` (`montar`), e os testes passam
fontes de mentira.
"""
import collections
import re
import unicodedata
from datetime import date, timedelta

from .. import gestao as G
from ..relatorios.regras import DIAS_PT, fin, semana_seg

# A categoria de cada tipo da programação no One Page (a mesma tabela do 2_fracttal.py do painel)
CAT = {"MPM": "Preventivas (MPM e inspeções)", "MPM-Mod/Tracker": "Preventivas (MPM e inspeções)",
       "MPM-Inversor": "Preventivas (MPM e inspeções)", "Inspeção": "Preventivas (MPM e inspeções)",
       "MPT": "Preventivas (MPM e inspeções)", "Corretiva": "Corretivas", "Religamento": "Religamentos",
       "Administrativa": "Administrativas", "MPA": "MPA", "Handover": "Handover", "Zeladoria": "Zeladoria", "MPS": "MPS"}
# UFs do Norte e do Nordeste: a regra do responsável da Manutenção (a curadoria diz quem cuida de cada lado)
NNE = {"AC", "AP", "AM", "PA", "RO", "RR", "TO", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA"}
# O nome do cliente como o painel mostra (o Fracttal escreve "Utragaz", em minúscula ou em caixa alta)
CLI_FIX = {"utragaz": "Ultragaz", "greenyellow": "GreenYellow", "thopen": "Thopen", "athon": "Athon", "axis": "Axis",
           "renogrid": "Renogrid", "2c": "2C"}
IDADE_BACKLOG = 25          # o Radar de Backlog: OS em processo abertas há MAIS de 25 dias
CORTE_TITULOS = 24          # os títulos das tarefas abertas vêm das tarefas criadas há mais de 24 dias (folga do painel)


def norm(s) -> str:
    """Sem acento, sem caixa e só letras e números: "Marabá 100" acha "Athon - Marabá 100 - PA"."""
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def ws(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _d(s) -> date | None:
    try:
        return date.fromisoformat(str(s or "")[:10])
    except ValueError:
        return None


def dias(s, hoje: date) -> int | None:
    d = _d(s)
    return (hoje - d).days if d else None


def curta(usina: str) -> str:
    """"Thopen - Santana do Ipanema 1 - AL" -> "Santana do Ipanema 1" (sem o cliente e sem a UF)."""
    u = ws(usina)
    u = re.sub(r"^\s*[^-]+-\s*", "", u) if " - " in u else u
    return re.sub(r"\s*-\s*[A-Z]{2}\s*$", "", u).strip()


def cliente_de(usina: str) -> str:
    u = ws(usina)
    cli = u.split(" - ")[0].strip() if " - " in u else (u.split()[0] if u else "Sem usina")
    return CLI_FIX.get(norm(cli), cli)


# ── Fracttal, pela Gestão PCM ───────────────────────────────────────────────────────────────────────────────────────

def _em_processo(tarefas) -> dict:
    """{OS: [tarefas]} das OS em processo (o status 1 do painel). Tarefa sem OS não entra."""
    por = collections.defaultdict(list)
    for t in tarefas or []:
        if t.get("osStatus") == "Em processo" and str(t.get("os") or "").strip():
            por[str(t["os"]).strip()].append(t)
    return por


def totais(tarefas) -> dict:
    """{OS: {"tot", "open"}} das OS em processo: o total de tarefas e as ainda abertas (o fracttal_totais.txt)."""
    return {os_: {"tot": len(ts), "open": sum(1 for t in ts if t.get("estado") != "Finalizada")}
            for os_, ts in _em_processo(tarefas).items()}


def abertas(tarefas, hoje: date) -> list[dict]:
    """As OS em processo com tarefa aberta (o fracttal_abertas.txt), com o mesmo agregado da consulta do painel: o MAIOR
    tipo, usina, cluster e responsável (iguais nas tarefas de uma OS), a data de manutenção e a criação MAIS ANTIGAS das
    tarefas abertas e o MENOR título delas. `dias` conta da data de manutenção (sem ela, da criação)."""
    out = []
    for os_, ts in _em_processo(tarefas).items():
        ab = [t for t in ts if t.get("estado") != "Finalizada"]
        if not ab:
            continue
        cri = min((str(t.get("criacao") or "")[:10] for t in ab if _d(t.get("criacao"))), default="")
        dm = min((str(t.get("dataProg") or "")[:10] for t in ab if _d(t.get("dataProg"))), default="") or cri
        out.append({"os": os_, "tipo": max(str(t.get("tipo") or "") for t in ab),
                    "usina": ws(max(str(t.get("usina") or "") for t in ab)),
                    "cluster": max(str(t.get("cluster") or "") for t in ab),
                    "resp": ws(max(str(t.get("responsavel") or "") for t in ab)),
                    "open": len(ab), "tot": len(ts), "dm": dm, "cri": cri,
                    "desc": min(str(t.get("tarefa") or "") for t in ab)[:70], "dias": dias(dm, hoje)})
    return out


def backlog(tarefas, abertas_os: list[dict], hoje: date) -> list[dict]:
    """O Radar de Backlog: as OS em processo abertas há mais de 25 dias (todos os tipos, fora as usinas de teste), com o
    título das tarefas abertas ("Título (×N)" para as iguais), o progresso e a preventiva separada em MPA ou MPS pelo
    título. As OS em revisão ficam fora: já foram executadas em campo."""
    corte = (hoje - timedelta(days=CORTE_TITULOS)).isoformat()
    tit = collections.defaultdict(list)
    for t in tarefas or []:
        if (t.get("osStatus") == "Em processo" and t.get("estado") != "Finalizada"
                and str(t.get("criacao") or "")[:10] < corte and str(t.get("os") or "").strip()):
            tit[str(t["os"]).strip()].append(ws(t.get("tarefa"))[:120])
    canon = {}
    for o in abertas_os:
        k = o["cluster"].upper().strip()
        canon.setdefault(k, o["cluster"].strip() if not o["cluster"].isupper() else o["cluster"].strip().title())
    out = []
    for o in abertas_os:
        idade = dias(o["cri"], hoje)
        if idade is None or idade <= IDADE_BACKLOG or "teste" in o["usina"].lower():
            continue
        t = tit.get(o["os"], [])
        tipo = o["tipo"]
        if tipo == "Preventiva":                         # separa MPA e MPS pelo título das tarefas
            junto = " ".join(t)
            tipo = ("Preventiva (MPA)" if re.search(r"\bMPA\b", junto) else
                    "Preventiva (MPS)" if re.search(r"\bMPS\b", junto) else "Preventiva")
        out.append({"os": o["os"], "st": 1, "tipo": tipo, "cri": o["cri"], "usina": o["usina"], "u": curta(o["usina"]) or "Sem usina",
                    "cli": cliente_de(o["usina"]), "cluster": canon.get(o["cluster"].upper().strip(), o["cluster"]) or "Sem cluster",
                    "resp": o["resp"], "pct": round(100 * (o["tot"] - o["open"]) / o["tot"]) if o["tot"] else 0,
                    "idade": idade, "tit": [x + (f" (×{n})" if n > 1 else "") for x, n in collections.Counter(t).items()]})
    out.sort(key=lambda r: -r["idade"])
    return out


# ── a programação semanal (banco_dados.json) ─────────────────────────────────────────────────────────────────────────

def _dia(dia: str) -> int | None:
    d = str(dia or "")
    return next((i for i, nome in enumerate(DIAS_PT) if d.startswith(nome.split("-")[0])), None)


def semanas(bd: dict, clsup: dict) -> dict:
    """{"42": {"ini", "fim", "fechado", "label", "tasks"}} das semanas do banco_dados, cada tarefa planejada como no
    painel: [equipe, dia 0–4, OS, usina, supervisor, categoria, executada 0/1, noturna]. Planejada = linha do plano (as
    `foraDoPlano` são execução, outro grão); executada = a régua do Fechamento da semana do Nexus (`fin`)."""
    out = {}
    for w in (bd or {}).get("semanas") or []:
        try:
            ini = semana_seg(w["week"])
        except (KeyError, ValueError):
            continue
        tasks = []
        for x in w.get("rows") or []:
            if x.get("foraDoPlano") or not str(x.get("os_id") or "").strip():
                continue
            eq = str(x.get("cluster") or "")
            sup = ws(x.get("responsavel")) or clsup.get(eq.upper().strip(), "") or "TBD"
            tasks.append([eq, _dia(x.get("dia")), str(x["os_id"]).strip(), ws(x.get("usina")), sup,
                          CAT.get(x.get("tipo"), str(x.get("tipo") or "")), 1 if fin(x) else 0,
                          "NOTURNO" in str(x.get("dia") or "").upper()])
        gerada = str(w.get("geradaEm") or "")
        out[str(int(w.get("num") or w["week"][-2:]))] = {
            "ini": ini.isoformat(), "fim": (ini + timedelta(days=4)).isoformat(), "label": w.get("label") or "",
            "fechado": f"{gerada[8:10]}/{gerada[5:7]} às {gerada[11:13]}h{gerada[14:16]}" if len(gerada) >= 16 else "",
            "tasks": tasks}
    return out


def semana_atual(bd: dict) -> str:
    ativa = str((bd or {}).get("semana_ativa") or "")
    return str(int(ativa[-2:])) if re.fullmatch(r"\d{4}-W\d{2}", ativa) else ""


def rolagens(bd: dict, abertas_os: list[dict]) -> dict:
    """{OS: semanas} das OS vivas que já rolaram: em quantas semanas a OS entrou na programação (o "Nº vezes programada"
    do PCM, que conta a 1ª vez e só cresce; vale o maior). Quem entrou uma vez só não rolou e fica fora."""
    vivas = {o["os"] for o in abertas_os}
    rol = {}
    for w in (bd or {}).get("semanas") or []:
        for x in w.get("rows") or []:
            os_ = str(x.get("os_id") or "").strip()
            v = x.get("vezes")
            if os_ in vivas and isinstance(v, (int, float)) and not isinstance(v, bool):
                rol[os_] = max(rol.get(os_, 0), int(v))
    return {k: v for k, v in rol.items() if v > 1}


# ── a Gerencial (mpas.json) ──────────────────────────────────────────────────────────────────────────────────────────

_SUP = re.compile(r"Supervisor\(a\):\s*([^\n|]*)")


def _tipo_ger(m: dict) -> str:
    return "MPS" if "MPS" in str(m.get("tipo") or "").upper() else "MPA"


def gerencial(mp: dict | None, hoje: date) -> tuple[list[dict], dict]:
    """(as linhas da aba MPAS no formato do painel, `painel` = o atraso de cada linha pela Fila da Gestão PCM). A linha é
    a posição no mpas.json (1, 2, 3...), estável dentro de uma leitura."""
    if not mp:
        return [], {}
    fila = G.fila_gerencial(mp, hoje)
    linhas, painel = [], {}
    for i, (m, f) in enumerate(zip(mp.get("manut") or [], fila), 1):
        usina = ws(m.get("usina"))
        sup = ws(m.get("supervisor"))
        if not sup:
            s = _SUP.search(str(m.get("equipe") or ""))
            sup = ws(s.group(1)) if s else ""
        oss = re.findall(r"\d{3,5}", str(m.get("os") or ""))
        linhas.append({"linha": i, "tipo": _tipo_ger(m), "os": ws(m.get("os")), "ult": oss[-1] if oss else "",
                       "cli": ws(m.get("cliente")), "usina": usina, "cluster": ws(m.get("cluster")),
                       "status": ws(m.get("status")), "strel": ws(m.get("relatorio")), "ciclo": ws(m.get("ciclo")),
                       "prev": str(m.get("prevista") or "")[:10], "ini": str(m.get("inicio") or "")[:10],
                       "fim": str(m.get("termino") or "")[:10], "sup": sup, "bloq": [], "obs": ws(m.get("obs"))})
        painel[i] = {"ref_lim": f.get("prev"), "dias": f.get("atraso") or 0,
                     "atrasada": f["sit"]["k"] == "Atrasada", "ref_mensal": False, "cadeia": oss}
    return linhas, painel


# ── as MPAs e MPSs da curadoria ──────────────────────────────────────────────────────────────────────────────────────

def classifica(txt: str) -> list[str]:
    """As categorias de um bloqueio escrito na Gerencial (o 4_dados.py do painel); um texto pode ter mais de uma."""
    t = norm(txt)
    c = []
    if "oleo" in t:
        c.append("Laudo de óleo")
    if "engenharia" in t and ("correc" in t or "retornad" in t):
        c.append("Correção da engenharia")
    elif "engenharia" in t or "relatorio" in t:
        c.append("Revisão da engenharia")
    if "chuva" in t:
        c.append("Chuva")
    if "noturn" in t or "deslig" in t:
        c.append("Desligamento ou noturna")
    if "preench" in t or "finalizacaodaos" in t or "lancar" in t:
        c.append("Lançar na OS")
    if "cliente" in t or "escopo" in t or "custo" in t:
        c.append("Cliente")
    if any(k in t for k in ("equipamento", "curvaiv", "tracador", "camera", "termograf", "microhm", "megom", "luva", "drone")):
        c.append("Equipamento")
    if not ({"Lançar na OS", "Chuva"} & set(c)) and any(
            k in t for k in ("time", "equipe", "atestado", "mantenedor", "semapoio", "tecniconausina", "faltadetecnico")):
        c.append("Equipe")
    return c or ["Outros"]


def achar(linhas: list[dict], usina: str, tipo: str, hint: str | None = None) -> dict | None:
    """A linha da aba MPAS de uma MPA/MPS da curadoria: mesmo tipo, nome curto contido no da planilha e, quando a usina
    tem várias linhas, a da OS `hint`."""
    cands = [r for r in linhas if r["tipo"] == tipo and norm(usina) in norm(r["usina"])]
    if hint:
        c2 = [r for r in cands if hint in r["os"]]
        if c2:
            cands = c2
    return cands[0] if cands else None


def _pendencias(it: dict, tot_os: dict) -> dict:
    """Pendências, total e progresso pelo Fracttal (a OS ou a cadeia de OS); `manual` trava os números da curadoria."""
    x = {}
    if it.get("manual"):
        return x
    g = it.get("grupo")
    if g in (2, 3) and it.get("tot") is not None:
        if it.get("cadeia"):
            partes = re.findall(r"(\d{3,5}) \((\d+) de (\d+)\)", it["cadeia"])
            novas = [(o, (tot_os.get(o) or {}).get("open", 0), (tot_os.get(o) or {}).get("tot", int(t))) for o, _p, t in partes]
            x["pend"], x["tot"] = sum(p for _, p, _ in novas), sum(t for _, _, t in novas)
            x["cadeia"] = " + ".join(f"{o} ({p} de {t})" for o, p, t in novas)
        else:
            t = tot_os.get(str(it.get("os")))
            x["pend"], x["tot"] = (t["open"], t["tot"]) if t else (0, it["tot"])
    elif g == 0 and "prog" in it:
        t = tot_os.get(str(it.get("os")))
        x["prog"] = round(100 * (t["tot"] - t["open"]) / t["tot"]) if t and t["tot"] else 100
    return x


def atraso_fracttal(tarefas, hoje: date) -> dict:
    """{OS: dias de atraso ou None} pela Fila da Gestão PCM SEM a Gerencial (`gestao.fila_fracttal`): da Data Programada
    mais antiga das tarefas de MPA/MPS da OS até hoje, para a OS não concluída; None = no prazo, concluída ou sem data."""
    return {x["os"]: x["atraso"] for x in G.fila_fracttal(tarefas or [], hoje)}


def mpa_mps(curadoria: list[dict], linhas: list[dict], tot_os: dict, hoje: date, manutencao: dict,
            tipo: str, atraso_os: dict | None = None) -> list[dict]:
    """As linhas de uma aba (MPA ou MPS): a curadoria + a linha da Gerencial + as pendências do Fracttal. `manutencao` =
    {"nne": nome, "outros": nome}: o responsável da Manutenção pela UF do cluster (decisão da curadoria).

    O atraso é o da Data Prevista da Gerencial. Sem a linha da Gerencial (ou sem a planilha: o servidor sem a senha dela),
    ele sai do Fracttal, pela regra da Fila da Gestão PCM sem a planilha (`atraso_os`, de `atraso_fracttal`); numa cadeia de
    OS, vale a mais atrasada. 15/10/2026, Levi, com o print da dispersão com todos os pontos grudados no topo: "A dispersão
    não está funcionando direito" (sem a senha da Gerencial no servidor, nenhuma MPA tinha atraso, e o ponto sem atraso
    ia parar fora da escala)."""
    out = []
    for it in curadoria:
        if it.get("tipo") != tipo:
            continue
        g = it.get("grupo")
        x = {k: v for k, v in it.items() if k not in ("grupo", "os", "usina", "tipo", "hint", "manual", "id")}
        x.update(_pendencias(it, tot_os))
        r = dict(g=g, os=str(it.get("os") or ""), tipo=tipo, **x)
        row = achar(linhas, it.get("usina") or "", tipo, it.get("hint"))
        if row:
            r.update(cli=row["cli"], u=row["usina"].split(" - ", 1)[-1], cluster=row["cluster"], sup=row["sup"],
                     prev=row["prev"], linha=row["linha"], bloq=row["bloq"], hist=[])
            if row["bloq"]:
                r["bl"] = list(dict.fromkeys(c for b in row["bloq"] for c in classifica(b)))
        else:
            # sem linha na Gerencial (ou sem a Gerencial): o nome da curadoria; cliente e cluster, das tarefas da OS
            r.update(cli=it.get("cli") or "", u=it.get("usina") or "", cluster=it.get("cluster") or "", sup="", prev="",
                     linha=None, bloq=[], hist=[])
        r.setdefault("bl", [])
        if r.get("fim"):
            r["parado"] = dias(r["fim"], hoje)
        if r.get("prev") and g in (2, 3, 0):
            r["atraso"] = max(dias(r["prev"], hoje) or 0, 0)
            r["atraso_fonte"] = "Gerencial"
        elif g in (2, 3, 0) and atraso_os:
            oss = re.findall(r"\d{3,5}", r.get("cadeia") or "") or [r["os"]]
            achados = [atraso_os[o] for o in oss if o in atraso_os]
            if achados:
                r["atraso"] = max(v or 0 for v in achados)
                r["atraso_fonte"] = "Fracttal"
        if r.get("tot") and r.get("pend") is not None:
            r["prog"] = round(100 * (r["tot"] - r["pend"]) / r["tot"])
        if r.get("flag"):
            r["prog"] = 100
        uf = (r.get("cluster") or "")[:2].upper()
        lado = manutencao.get("nne" if uf in NNE else "outros") if g in (2, 3, 0) and uf else ""
        r["manut"] = lado or ""
        out.append(r)
    return out


def completar_pela_os(curadoria: list[dict], tarefas) -> list[dict]:
    """Cliente e cluster de cada item da curadoria pelas tarefas da OS (para quando a Gerencial não abriu)."""
    por_os = {}
    for t in tarefas or []:
        os_ = str(t.get("os") or "").strip()
        if os_ and os_ not in por_os:
            por_os[os_] = t
    out = []
    for it in curadoria:
        t = por_os.get(str(it.get("os") or ""))
        out.append(dict(it, cli=it.get("cli") or (cliente_de(t.get("usina")) if t else ""),
                        cluster=it.get("cluster") or (str(t.get("cluster") or "") if t else "")))
    return out


def espelho(linhas: list[dict], painel: dict, mpa: list[dict], mps: list[dict]) -> list[dict]:
    """Todas as linhas da aba MPAS (o espelho do gerencial), com o grupo no painel de quem está na curadoria."""
    sit = {r["linha"]: r["g"] for r in mpa + mps if r.get("linha")}
    out = []
    for s in linhas:
        p = painel.get(s["linha"]) or {}
        out.append({"linha": s["linha"], "tipo": s["tipo"], "os": s["os"], "cli": s["cli"],
                    "u": s["usina"].split(" - ", 1)[-1], "cluster": s["cluster"], "ciclo": s["ciclo"], "prev": s["prev"],
                    "ini": s["ini"], "fim": s["fim"], "status": s["status"], "strel": s["strel"], "sup": s["sup"],
                    "g": sit.get(s["linha"]), "bloq": s["bloq"], "hist": [], "atrasada": bool(p.get("atrasada")),
                    "diasAtraso": p.get("dias") or 0, "refLim": p.get("ref_lim")})
    return out


# ── o mapa ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def supervisores(bd: dict, linhas_ger: list[dict], do_cadastro: dict) -> dict:
    """{CLUSTER: supervisor}: o Supervisor de Campo da equipe no cadastro; sem ele, o responsável mais frequente da equipe
    na programação; sem ele, o supervisor da Gerencial."""
    cnt = collections.Counter()
    for w in (bd or {}).get("semanas") or []:
        for x in w.get("rows") or []:
            if x.get("cluster") and ws(x.get("responsavel")):
                cnt[(str(x["cluster"]).upper().strip(), ws(x["responsavel"]))] += 1
    out = {}
    for s in linhas_ger:                                  # a reserva: o supervisor da Gerencial
        if s["cluster"] and s["sup"]:
            out.setdefault(s["cluster"].upper().strip(), s["sup"])
    prog = {}
    for (c, nome), _n in cnt.most_common():              # o mais frequente de cada equipe na programação
        prog.setdefault(c, nome)
    out.update(prog)
    out.update({str(c).upper().strip(): nome for c, nome in (do_cadastro or {}).items() if nome})
    return out


def usinas(abertas_os: list[dict], bd: dict, atual: str, linhas_ger: list[dict], clsup: dict, geo) -> list[dict]:
    """As usinas do mapa: a carga (OS e tarefas abertas por tipo, corretivas, a mais antiga) e as programadas na semana
    atual, com o cluster (Fracttal, senão programação, senão Gerencial), o supervisor do cluster e o ponto no desenho
    (`geo.ponto`, ou None sem coordenada). Entram também as usinas do cadastro sem carga, como no painel."""
    us = {}
    for o in abertas_os:
        u = us.setdefault(o["usina"], {"usina": o["usina"], "cluster": o["cluster"], "os": 0, "tarefas": 0, "corr": 0,
                                       "tipos": collections.Counter(), "maisantiga": 0})
        u["os"] += 1
        u["tarefas"] += o["open"]
        u["tipos"][o["tipo"]] += o["open"]
        if o["tipo"] in ("Corretiva", "Corretiva Emergencial"):
            u["corr"] += 1
        u["maisantiga"] = max(u["maisantiga"], o["dias"] or 0)
    sem_atual = next((w for w in (bd or {}).get("semanas") or [] if str(int(w.get("num") or 0)) == atual), None)
    rows_atual = [x for x in (sem_atual or {}).get("rows") or [] if not x.get("foraDoPlano")]
    por_usina = collections.Counter(ws(x.get("usina")) for x in rows_atual)
    prog_cl = collections.Counter((norm(x.get("usina")), str(x.get("cluster") or ""))
                                  for w in (bd or {}).get("semanas") or [] for x in w.get("rows") or []
                                  if x.get("usina") and x.get("cluster"))
    cl_por_us = {}
    for (k, c), _n in prog_cl.most_common():
        cl_por_us.setdefault(k, c)
    for s in linhas_ger:
        if s["cluster"]:
            cl_por_us.setdefault(norm(s["usina"]), s["cluster"])
    vistos = {norm(k) for k in us}
    for nome in (geo.nomes() if geo else []):
        if " - " in nome and norm(nome) not in vistos:
            us[nome] = {"usina": nome, "cluster": "", "os": 0, "tarefas": 0, "corr": 0, "tipos": collections.Counter(),
                        "maisantiga": 0}
            vistos.add(norm(nome))
    out = []
    for u in us.values():
        u["pt"] = geo.ponto(u["usina"]) if geo else None
        u["w42"] = por_usina.get(u["usina"], 0)
        if not u["cluster"]:
            u["cluster"] = cl_por_us.get(norm(u["usina"]), "")
        u["tipos"] = dict(u["tipos"])
        u["sup"] = clsup.get((u["cluster"] or "").upper().strip(), "")
        u["cli"] = u["usina"].split(" - ")[0].strip()
        out.append(u)
    return out


# ── tudo ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

def montar(gestao: dict | None, bd: dict | None, mp: dict | None, curadoria: list[dict], manutencao: dict,
           hoje: date, geo=None, colab: list | None = None, sup_cadastro: dict | None = None) -> dict:
    """{"DATA", "EXTRA", "COLAB"}: o contrato do painel (seção 6 do INTEGRACAO.md), com o ponto do mapa (`pt`, já no
    desenho) no lugar da latitude e longitude (`xy`), que no Nexus não saem do servidor."""
    tarefas = (gestao or {}).get("tarefas") or []
    ab = abertas(tarefas, hoje)
    tot_os = totais(tarefas)
    linhas_ger, painel = gerencial(mp, hoje)
    cur = completar_pela_os(curadoria, tarefas)
    atr = atraso_fracttal(tarefas, hoje)
    mpa = mpa_mps(cur, linhas_ger, tot_os, hoje, manutencao, "MPA", atr)
    mps = mpa_mps(cur, linhas_ger, tot_os, hoje, manutencao, "MPS", atr)
    clsup = supervisores(bd, linhas_ger, sup_cadastro or {})
    atual = semana_atual(bd)
    data = {"hoje": hoje.isoformat(), "mpa": mpa, "mps": mps, "esp": espelho(linhas_ger, painel, mpa, mps),
            "backlog": backlog(tarefas, ab, hoje)}
    extra = {"painel": painel, "open": ab, "usinas": usinas(ab, bd, atual, linhas_ger, clsup, geo),
             "weeks": semanas(bd, clsup), "w42": {"num": int(atual) if atual else None}, "rol": rolagens(bd, ab),
             "clsup": clsup, "mapa": geo.desenho() if geo else None}
    return {"DATA": data, "EXTRA": extra, "COLAB": colab or []}
