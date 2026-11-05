"""Prova da Gestão PCM: o Nexus bate célula a célula com o painel do PCM?

Roda o PRÓPRIO JavaScript do painel (js/preventivas.js + o recorte do js/app.js que ele usa) no node, num contexto
isolado (nexus/pcm/prova_gestao.js), contra o MESMO gestao_pcm.json que o Nexus lê, com o relógio dos dois lados
parado no mesmo instante. Depois compara, caso a caso, o que o painel desenharia com o que o Nexus calcula
(nexus/pcm/gestao.py, as mesmas funções que a tela usa):

- Plano: cada linha (grupo, usina e TOTAL GERAL) e cada célula: texto, faixa de cor, se a fração abre a Fila e a dica
  do mouse com as OS; o Geral, os Pendentes e, com a Gerencial, a criticidade e a observação da usina.
- Fila: as linhas, na ordem, com as colunas visíveis; os quatro KPIs; e o par de números do topo.
- A aba além do Plano & Fila (04/11/2026; o renderGestao do js/app.js, com um `document` de mentira para os campos da
  barra): os números do alto (Visíveis, Finalizadas, Em aberto, Atrasadas e a dica das Finalizadas), a linha
  "Atualizado", as duas árvores Cliente ▸ Usina ▸ Tipo (nó a nó, na ordem, com as contagens e as atrasadas, e as
  tabelas dos tipos linha a linha), o Só atrasadas e as listas de cada filtro. Os filtros de cima em várias
  combinações (sem filtro, cliente, cliente + tipo, estado, etiqueta, OS e Solicitação por "contém", o período em
  cada "considerar", duas escolhas no mesmo filtro...), também no Plano & Fila.

A Gerencial (mpas.json) é cifrada: com `NEXUS_PCM_MPAS_SENHA` no ambiente a prova usa a de verdade (decifrada só em
memória); sem ela, monta uma Gerencial SINTÉTICA a partir das OS de MPA/MPS do próprio gestao_pcm.json, com todos os
casos da regra (várias OS na célula, OS sem par, sem OS, Prevista vencida, data inválida, log de observações fora de
ordem, criticidades). A sintética prova a transcrição da regra; os números reais da Fila com a Gerencial só se provam
com a senha.

    python -m nexus.pcm.prova_gestao                         # baixa o JS e o JSON do repositório do PCM
    python -m nexus.pcm.prova_gestao --painel C:/caminho/gridco-pcm-data --dados gestao_pcm.json

Sai com código 0 quando tudo bate. Nunca imprime nome de pessoa: no agrupamento por Responsável, o nome vira um número.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from datetime import timedelta
from pathlib import Path

from werkzeug.datastructures import MultiDict

from . import fonte, gestao as G

RAIZ_PAINEL = fonte.URL_PADRAO.rsplit("/", 1)[0] + "/"      # o mesmo repositório que a tela lê
AQUI = Path(__file__).resolve().parent


def _ler(origem: str, nome: str) -> bytes:
    """Um arquivo do painel: de uma pasta local (o clone do gridco-pcm-data) ou do repositório público."""
    if origem.startswith(("http://", "https://")):
        req = urllib.request.Request(origem.rstrip("/") + "/" + nome, headers={"User-Agent": "Nexus-GridCo/1 (prova)"})
        with urllib.request.urlopen(req, timeout=60) as r:      # noqa: S310 — endereço fixo do repositório do PCM
            return r.read()
    return (Path(origem) / nome).read_bytes()


# ── a Gerencial sintética (sem a senha) ─────────────────────────────────────────────────────────────────────────
def gerencial_sintetica(tarefas: list[dict], h) -> dict:
    """Uma Gerencial no formato do mpas.json decifrado, feita das OS de MPA/MPS do próprio JSON. Determinística."""
    por_os: dict[str, dict] = {}
    for t in G.escopo(tarefas):
        m = G._RX.search(str(t.get("tarefa") or ""))
        if not m or m.group(1) not in ("MPA", "MPS") or not str(t.get("os") or "").strip():
            continue
        r = por_os.setdefault(str(t["os"]).strip(), {"tipo": m.group(1), "t": t, "fin": 0, "total": 0, "tasks": []})
        r["total"] += 1
        r["fin"] += t.get("estado") == "Finalizada"
        r["tasks"].append({"prog": str(t.get("dataProg") or "")[:10] or None})
    oss = sorted(por_os)
    bd = {}
    for i, o in enumerate(oss):
        r = por_os[o]
        sit = ("Concluída" if r["fin"] == r["total"] else "Em andamento") if i % 3 == 0 else None
        bd[o] = {"fin": r["fin"], "total": r["total"], "tasks": r["tasks"] if i % 7 else [], **({"sit": sit} if sit else {})}
    crits = ["Muito Crítico", "Crítico", "Alta", "Média", "Baixa", "", "crítica"]
    status = ["", "Finalizado", "Em execução", "Não iniciado", "finalizada"]
    manut = []
    for i, o in enumerate(oss):
        r, t = por_os[o], por_os[o]["t"]
        usina = str(t.get("usina") or "")
        curta = usina.split(" - ")[1] if usina.count(" - ") >= 2 else usina
        cliente = str(t.get("cliente") or "")
        d = lambda n: (h + timedelta(days=n)).isoformat()          # noqa: E731
        prevista = [d(-200), d(-45), d(-5), d(0), d(20), "", d(-95), "2026-02-30"][i % 8]
        os_cel = [o, o + " / " + oss[(i + 1) % len(oss)], "", "999999", o + ";" + o, o][i % 6]
        obs = ["", f"• {(h - timedelta(days=90)):%d/%m/%Y} - aguardando peça\n• {(h - timedelta(days=3)):%d/%m/%Y} - peça chegou",
               f"• {(h - timedelta(days=70)):%d/%m/%Y}: equipe agendada", "sem data nenhuma",
               f"• {(h - timedelta(days=10)):%d/%m/%Y} - b\n• {(h - timedelta(days=40)):%d/%m/%Y} - a"][i % 5]
        manut.append({
            "tipo": ["MPA", "MPS", "MPA/MPS", "mps"][i % 4] if r["tipo"] == "MPS" else "MPA",
            # o nome da Gerencial diverge do Fracttal como na vida real: travessão, sem a UF, "200" no lugar de "2"
            "cliente": cliente if i % 9 else "", "usina": (cliente + " – " + curta) if i % 4 else usina,
            "usina_curta": curta if i % 5 else "", "cluster": (str(t.get("cluster") or "").upper() if i % 2 else t.get("cluster")) or "",
            "os": os_cel, "prevista": prevista, "criticidade": crits[i % len(crits)], "status": status[i % len(status)],
            "obs": obs, "equipe": f"Equipe {i % 4}\nreserva", "apoio": "" if i % 3 else "Apoio 1"})
    return {"geradoEm": "sintetica", "manut": manut, "bd": bd}


# ── os casos ────────────────────────────────────────────────────────────────────────────────────────────────────
TIPOS_PLANO = ("todos", "prev", "MPM", "MPT", "MPS", "MPA", "corr", "emerg", "relig", "insp", "pred", "adm", "zel", "hand")


def casos(tarefas: list[dict], meses_: list[str]) -> list[dict]:
    esc = G.escopo(tarefas)

    def mais_comum(campo):
        cont: dict[str, int] = {}
        for t in esc:
            cont[str(t.get(campo) or "")] = cont.get(str(t.get(campo) or ""), 0) + 1
        return max(cont, key=cont.get) if cont else ""
    topos = [{}, {"cliente": mais_comum("cliente")}, {"cluster": mais_comum("cluster")},
             {"resp": mais_comum("responsavel")}, {"usina": mais_comum("usina")}]
    out, n = [], 0

    def novo(gpv, topo=None):
        nonlocal n
        n += 1
        base = {"modo": "plano", "tipo": "todos", "dim": "cli", "col": "sig", "val": "pct", "mes": "todos", "busca": "",
                "ordem": "pend", "desc": True, "pend": "todas", "ordemF": "prev", "descF": False, "drill": None}
        out.append({"id": f"c{n:03d}", "gpv": {**base, **gpv}, "topo": topo or {}})

    vals, mes_ops = ("pct", "pend", "fei", "tot"), ("todos", *meses_)
    i = 0
    for tipo in TIPOS_PLANO:
        for dim in ("cli", "clu", "res", "usi"):
            for col in ("sig", "mes"):
                cols = G.colunas(G.Opcoes(tipo=tipo, col=col), meses_)
                ordens = ("pend", "nome", "geral", *cols)
                novo({"tipo": tipo, "dim": dim, "col": col, "val": vals[i % 4], "mes": mes_ops[(i // 4) % 4],
                      "ordem": ordens[i % len(ordens)], "desc": bool(i % 2)})
                i += 1
    for busca in ("jacunda", "THOPEN", "sp", "ba sul", "nada-com-isso"):
        novo({"busca": busca, "dim": "clu"})
    for topo in topos[1:]:
        novo({"dim": "res"}, topo)
        novo({"tipo": "prev", "col": "mes", "val": "pend"}, topo)
    # Fila: só os tipos que existem nela (o resto o painel e o Nexus trocam por Todos antes de chegar aqui)
    usina_drill = mais_comum("usina")
    # sem a ordem "tipo": no painel o cabeçalho Tipo não ordena (cai na Prevista) e o Nexus ordena pelo tipo de
    # propósito (revisão de 08/10/2026)
    for tipo in ("todos", "prev", "MPA", "MPS"):
        for ordem in ("prev", "prog", "atraso", "nome", "crit"):
            for desc in (False, True):
                novo({"modo": "fila", "tipo": tipo, "ordemF": ordem, "descF": desc})
    for pend in ("atraso", "semos", "critsem", "concl"):
        novo({"modo": "fila", "pend": pend})
    for busca in ("jacunda", "1", "sp"):
        novo({"modo": "fila", "busca": busca, "ordemF": "atraso", "descF": True})
    novo({"modo": "fila", "drill": {"usina": usina_drill, "tipo": "MPA"}})
    novo({"modo": "fila", "drill": {"usina": usina_drill, "tipo": "MPS"}})
    for topo in topos[1:]:
        novo({"modo": "fila", "ordemF": "atraso", "descF": True}, topo)
    # os filtros de cima completos (04/11/2026) também valem no Plano & Fila: o Plano com o Tipo Todos (o Tipo de cima
    # vale), o Plano com Tipo próprio (o de cima sai) e a Fila
    for _rot, topo in combos(esc, meses_):
        novo({}, topo)
        novo({"tipo": "prev", "col": "mes", "val": "pend"}, topo)
        novo({"modo": "fila", "ordemF": "atraso", "descF": True}, topo)
    return out


def combos(esc: list[dict], meses_: list[str]) -> list[tuple[str, dict]]:
    """As combinações dos filtros de cima que a prova passa (nas chaves do GP_SEL do painel), tiradas do próprio JSON:
    os valores mais comuns de cada campo, uma OS de poucas tarefas (a árvore que abre sozinha) e, se houver, uma OS só
    de "não finalizadas no período" (a mensagem de visão principal vazia)."""
    def por_frequencia(campo):
        cont = Counter()
        for t in esc:
            v = t.get(campo)
            for x in (v if isinstance(v, list) else [v]):
                if x:
                    cont[str(x)] += 1
        return [v for v, _n in cont.most_common()] or [""]
    cli, tipo, est, etq, usi, clu, resp = (por_frequencia(c) for c in (
        "cliente", "tipo", "estado", "etiquetas", "usina", "cluster", "responsavel"))
    oss = Counter(str(t.get("os")) for t in esc)
    com_principal = {str(t.get("os")) for t in esc if not G.nao_finalizada(t)}

    def acha_os(candidatas, regra):
        """A primeira OS (das mais cheias) cujo "contém" pega um conjunto de OS que cabe na regra."""
        for o in sorted(candidatas, key=lambda x: (-oss[x], x)):
            if len(o) >= 4 and regra([x for x in oss if o in x]):
                return o
        return None
    pequena = acha_os([o for o in oss if 3 <= oss[o] <= 40], lambda pega: sum(oss[x] for x in pega) <= 40)
    so_nf = acha_os([o for o in oss if o not in com_principal], lambda pega: not any(x in com_principal for x in pega))
    ini, fim = f"{meses_[1]}-01", f"{meses_[1]}-15"
    out = [("sem filtro", {}), ("um cliente", {"cliente": [cli[0]]}),
           ("cliente + tipo", {"cliente": [cli[0]], "tipo": [tipo[1 % len(tipo)]]}),
           ("estado", {"estado": [est[1 % len(est)]]}), ("etiqueta", {"etq": [etq[0]]}),
           ("OS por contém", {"os": "12"}), ("Solicitação por contém", {"ss": "29"}),
           *((f"período, considerar {m}", {"pini": ini, "pfim": fim, "pmodo": m})
             for m in ("qq", "prog", "ini", "fim")),
           ("período só com o fim", {"pfim": f"{meses_[0]}-10"}),
           ("duas escolhas no cliente", {"cliente": cli[:2]}), ("duas escolhas no tipo", {"tipo": tipo[1:3]}),
           ("duas escolhas no estado", {"estado": est[-2:]}), ("duas etiquetas", {"etq": etq[1:3]}),
           ("usina em maiúsculas", {"usina": [usi[0].upper()]}),
           ("cluster em minúsculas", {"cluster": [clu[0].lower()]}),
           ("responsável", {"resp": [resp[0]]}),
           ("cliente + estado + período", {"cliente": [cli[1 % len(cli)]], "estado": [est[1 % len(est)]],
                                           "pini": ini, "pfim": fim}),
           ("tipo de cima com etiqueta", {"tipo": [tipo[0]], "etq": [etq[0]]}),
           ("escolha que não existe", {"cliente": ["Cliente que não existe"]}), ("nada", {"os": "zzzz"}),
           ("só atrasadas", {"atr": True}), ("só atrasadas de um cliente", {"atr": True, "cliente": [cli[0]]}),
           ("só atrasadas sem nada", {"atr": True, "os": "zzzz"})]
    if pequena:
        out.append(("árvore pequena, que abre sozinha", {"os": pequena}))
    if so_nf:
        out.append(("só não finalizadas no período", {"os": so_nf}))
    return out


def casos_arv(tarefas: list[dict], meses_: list[str]) -> list[dict]:
    """Os casos da aba além do Plano & Fila: as tabelas de todos os tipos sem filtro (as 32 mil tarefas, uma vez) e,
    nos outros, de até 150 tipos espalhados pela árvore."""
    return [{"id": f"a{i:03d}", "rot": rot, "topo": topo, "maxTabelas": None if not topo else 150}
            for i, (rot, topo) in enumerate(combos(G.escopo(tarefas), meses_), 1)]


_NA_URL = {"cliente": "cliente", "usina": "usina", "cluster": "cluster", "resp": "responsavel", "tipo": "tipo_tarefa",
           "etq": "etiqueta", "estado": "estado"}


def _args(topo: dict) -> MultiDict:
    """O caso (nas chaves do GP_SEL do painel) como a URL da tela o escreve: o lado do Nexus passa pelo `G.filtros`."""
    pares = [(_NA_URL[k], x) for k in _NA_URL for x in (topo.get(k) if isinstance(topo.get(k), list)
                                                        else [topo.get(k)]) if x]
    pares += [(k, topo[k]) for k in ("os", "ss", "pini", "pfim", "pmodo") if topo.get(k)]
    return MultiDict(pares + ([("atr", "1")] if topo.get("atr") else []))


# ── o lado do Nexus ─────────────────────────────────────────────────────────────────────────────────────────────
def _opcoes(gpv: dict, meses_) -> G.Opcoes:
    """Os mesmos controles do caso, pelo caminho da URL da tela (G.opcoes)."""
    args = {"modo": gpv["modo"], "tipo": gpv["tipo"], "dim": gpv["dim"], "col": gpv["col"], "val": gpv["val"],
            "mes": gpv["mes"], "q": gpv["busca"], "ordem": gpv["ordem"], "desc": "1" if gpv["desc"] else "0",
            "pend": gpv["pend"], "ordemf": gpv["ordemF"], "descf": "1" if gpv["descF"] else "0"}
    if gpv.get("drill"):
        args.update(drill=gpv["drill"]["usina"], dt=gpv["drill"]["tipo"])
    return G.opcoes(args, meses_)


def _cel(c) -> dict:
    return {"cls": c["cls"], "frac": c["drill"], "title": c["os"], "txt": c["txt"]}


def _fim(geral) -> dict:
    return {"cls": G.faixa(geral), "txt": "—" if geral is None else f"{geral}%"}


def linhas_plano(mx: dict, o: G.Opcoes, ger: bool) -> list[dict]:
    out = []
    vazio_obs = {"critCls": "", "crit": "", "title": ""}
    for g in mx["grupos"]:
        if o.dim != "usi":
            n = len(g["filhos"])
            out.append({"k": "g", "nome": g["nome"], "mini": f"{n} usina{'s' if n > 1 else ''}",
                        "cols": [_cel(c) for c in g["tds"]], "geral": _fim(g["geral"]),
                        "pend": str(g["tudo"]["t"] - g["tudo"]["f"]), "obs": vazio_obs if ger else None})
        for f in g["filhos"]:
            co = f.get("co")
            obs = ({"critCls": co["critCls"] if co["crit"] else "", "crit": co["crit"], "title": co["obs"]} if co
                   else vazio_obs) if ger else None
            out.append({"k": "u" if o.dim == "usi" else "f", "nome": f["nome"], "mini": "",
                        "cols": [_cel(c) for c in f["tds"]], "geral": _fim(f["geral"]),
                        "pend": str(f["tudo"]["t"] - f["tudo"]["f"]), "obs": obs})
    if not out:
        out.append({"k": "vazio"})
    t = mx["total"]
    out.append({"k": "t", "nome": "TOTAL GERAL", "mini": f"{mx['usinas']} usinas", "cols": [_cel(c) for c in t["tds"]],
                "geral": _fim(t["geral"]), "pend": str(t["tudo"]["t"] - t["tudo"]["f"]), "obs": vazio_obs if ger else None})
    return out


def linhas_fila(ls: list[dict], ger: bool) -> list[dict]:
    out = []
    for x in ls:
        c = [x["nome"], x["tipo"]]
        if ger:
            c += [x["crit"] or "—", G.data_curta(x["prev"]) if x["prev"] else "—"]
        c.append((G.data_curta(x["prog"]) + (" ●" if x["diverge"] else "")) if x["prog"] else "—")
        if x["atraso"] is not None:
            fx = G.faixa_atraso(x["atraso"])
            c.append(f"{x['atraso']} d" + (f"|{fx}" if fx else ""))
        else:
            c.append("✓" if x["conclu"] else "—")
        c.append("sem OS" if x["semOS"] else (f"{x['os']} ?" if x["osSemPar"] else x["os"]))
        c.append(x["sit"]["k"])
        if ger:
            dt = (G.data_curta(x["obsIso"]) + " ") if x["obsIso"] else ""
            c.append(" ".join((dt + (x["obsTxt"][:110] if x["obsTxt"] else "—")).split()))
        else:
            c.append(f"{x['bdFin']}/{x['bdTot']}" if x["bdTot"] is not None else "—")
        out.append({"conclu": x["conclu"], "c": [" ".join(str(v).split()) for v in c]})
    return out


_RECORTES: dict = {}           # o mesmo filtro aparece em vários casos: o recorte das 32 mil tarefas sai uma vez


def _recorte(tarefas_esc, f: G.Filtros) -> G.Recorte:
    if f not in _RECORTES:
        _RECORTES[f] = G.recortar(tarefas_esc, f)
    return _RECORTES[f]


def nexus(caso: dict, tarefas_esc: list[dict], mp, meses_, h) -> dict:
    """O que o Nexus calcula para o caso, pelas mesmas funções da tela (telas._ctx_gestao, sem a cópia guardada)."""
    gpv = caso["gpv"]
    f = G.filtros(_args(caso["topo"]))
    o = _opcoes(gpv, meses_)
    tarefas = G.tarefas_do_plano(_recorte(tarefas_esc, f), f, G.tipo_local(o, f))
    b = G.base(tarefas, meses_)
    fila = G.fila_universo(tarefas, mp, f, h)
    par = G.par_topo(b, meses_, fila)
    res = {"par": par}
    if o.modo == "plano":
        res["plano"] = linhas_plano(G.plano(b, o, meses_, G.crit_obs(mp) if mp is not None else None), o, mp is not None)
    else:
        ls = G.fila_filtrada(fila, o)
        res["fila"] = linhas_fila(ls, mp is not None)
        k = G.kpis_fila(fila)
        res["kpis"] = [str(k["atraso"]), str(k["semos"]), str(k["critsem"]), f"{k['concl']}/{k['total']}"] if mp is not None else []
        res["n"] = (f"{len(ls)} manutenç{'ão' if len(ls) == 1 else 'ões'}") if mp is not None else None
    return res


def _par_painel(txt: str, ger: bool) -> dict:
    """Os números do par de topo, lidos do texto que o painel desenhou."""
    rot = re.search(r"ROTINA \(MPM/MPT · [a-z]{3}/\d{2}\) (—|\d+%)", txt)
    out = {"rotina": rot.group(1) if rot else "?"}
    if ger:
        a = re.search(r"GRANDES \(MPA/MPS\) (\d+) atrasadas?(?: · mais antiga (\d+) d)?", txt)
        g = re.search(r"GESTÃO (\d+) críticas? sem data futura · (\d+) sem OS", txt)
        out.update(atrasadas=a.group(1) if a else "?", mais_antiga=(a.group(2) or "0") if a else "?",
                   crit_sem_data=g.group(1) if g else "?", sem_os=g.group(2) if g else "?")
    return out


def _par_nexus(par: dict, ger: bool) -> dict:
    out = {"rotina": "—" if par["rotina"] is None else f"{par['rotina']}%"}
    if ger:
        out.update(atrasadas=str(par["atrasadas"]), mais_antiga=str(par["mais_antiga"]),
                   crit_sem_data=str(par["crit_sem_data"]), sem_os=str(par["sem_os"]))
    return out


# ── comparação ──────────────────────────────────────────────────────────────────────────────────────────────────
def comparar(painel: dict, nx: dict, caso: dict, ger: bool) -> tuple[int, list[str]]:
    """(células comparadas, divergências). A divergência diz o caso, a linha e o campo, sem nome de pessoa."""
    dif, n = [], 0
    pseud: dict[str, str] = {}

    def nome(s):
        if caso["gpv"]["dim"] != "res" or caso["gpv"]["modo"] != "plano":
            return s
        return pseud.setdefault(s, f"responsável #{len(pseud) + 1}")

    def ver(rotulo, a, b, oculto=False):
        nonlocal n
        n += 1
        if a != b:
            # a observação da Gerencial pode citar gente: na divergência, só se diz que o texto difere
            dif.append(f"{caso['id']} {rotulo}: " + ("o texto difere (oculto)" if oculto else f"painel={a!r} nexus={b!r}"))
    for k, v in _par_nexus(nx["par"], ger).items():
        ver(f"par.{k}", _par_painel(painel["par"], ger).get(k), v)
    if "plano" in nx:
        pa, nb = painel["plano"], nx["plano"]
        ver("plano.linhas", len(pa), len(nb))
        for i, (a, b) in enumerate(zip(pa, nb)):
            r = f"linha {i} ({a.get('k')}:{nome(a.get('nome', ''))})"
            ver(r + " tipo", a["k"], b["k"])
            if a["k"] == "vazio" or b["k"] == "vazio":
                continue
            ver(r + " nome", nome(a["nome"]), nome(b["nome"]))
            ver(r + " mini", a["mini"], b["mini"])
            ver(r + " ncols", len(a["cols"]), len(b["cols"]))
            for j, (ca, cb) in enumerate(zip(a["cols"], b["cols"])):
                # diferenças de propósito: o Nexus escreve a OS sem "#" (o painel: "OS — #123 (1/2)") e não põe a dica
                # "sem preventiva no período" nas células de grupo e do TOTAL, que têm tarefa (revisão de 08/10/2026)
                tit = ca["title"].replace("#", "")
                ca = dict(ca, title="" if tit == "sem preventiva no período" else tit)
                for campo in ("txt", "cls", "frac", "title"):
                    ver(f"{r} col{j}.{campo}", ca[campo], cb[campo])
            ver(r + " geral", a["geral"], b["geral"])
            ver(r + " pendentes", a["pend"], b["pend"])
            if ger:
                oa = a["obs"] or {}
                for campo in ("crit", "critCls"):
                    ver(f"{r} obs.{campo}", oa.get(campo, ""), (b["obs"] or {}).get(campo, ""))
                ver(f"{r} obs.texto", oa.get("title") or "", (b["obs"] or {}).get("title") or "", oculto=True)
    else:
        pa, nb = painel["fila"], nx["fila"]
        ver("fila.linhas", len(pa), len(nb))
        for i, (a, b) in enumerate(zip(pa, nb)):
            ver(f"fila {i} concluída", a["conclu"], b["conclu"])
            ver(f"fila {i} ncols", len(a["c"]), len(b["c"]))
            for j, (ca, cb) in enumerate(zip(a["c"], b["c"])):
                ver(f"fila {i} col{j}", ca, cb, oculto=ger and j == len(a["c"]) - 1)
        if ger:
            ver("fila.kpis", [k["v"] for k in painel["kpis"]], nx["kpis"])
            ver("fila.n", painel["n"], nx["n"])
    return n, dif


# a cor do painel e a classe do Nexus: o estado (gpEstadoPill) e os dias (gpDiasCell e gpFlatHTML)
_ESTADO = {"gp-e-em": "info", "gp-e-pau": "nulo", "gp-e-fin": "ok", "gp-e-ni": "and"}
_DIAS = {"red": "crit", "amber": "and", "ok": "ok", "": ""}
_LISTA_DO_PAINEL = {"cliente": "cliente", "usina": "usina", "cluster": "cluster", "responsavel": "resp",
                    "tipo_tarefa": "tipo", "etiqueta": "etq", "estado": "estado"}


def _nos(clientes: list[dict]) -> list[dict]:
    """A árvore do Nexus na sequência em que o painel a desenha: cliente, as usinas dele, os tipos de cada usina."""
    out = []
    for c in clientes:
        out.append({"k": "c", "nome": c["nome"], "n": str(c["n"])})
        for u in c["usinas"]:
            out.append({"k": "u", "nome": u["nome"], "n": str(u["n"])})
            out += [{"k": "t", "nome": x["nome"], "n": str(x["n"]), "atr": str(x["atrasadas"])} for x in u["tipos"]]
    return out


def comparar_aba(painel: dict, caso: dict, esc: list[dict], gestao: dict) -> tuple[int, list[str]]:
    """A aba além do Plano & Fila, caso a caso: os números do alto, as listas de cada filtro, as duas árvores nó a nó,
    as tabelas dos tipos linha a linha e o Só atrasadas. Nome de pessoa e texto livre (tarefa, etiqueta, observação)
    não saem na divergência."""
    dif, n = [], 0
    alerta = int(gestao.get("diasAlerta") or 10)

    def ver(rotulo, a, b, oculto=False):
        nonlocal n
        n += 1
        if a != b:
            dif.append(f"{caso['id']} ({caso['rot']}) {rotulo}: "
                       + ("o texto difere (oculto)" if oculto else f"painel={a!r} nexus={b!r}"))
    f = G.filtros(_args(caso["topo"]))
    rec = _recorte(esc, f)
    a = G.aba(rec.todas, alerta, f.atr)
    num, k = a["numeros"], painel["k"]
    for rot, chave, valor in (("Visíveis", "vis", "visiveis"), ("Finalizadas", "fin", "finalizadas"),
                              ("Em aberto", "ab", "em_aberto"), ("Atrasadas", "atr", "atrasadas")):
        ver(rot, k[chave], str(num[valor]))
    # a dica e as mensagens pelas MESMAS peças que a tela usa (gestao.dica_finalizadas e as MSG_*): o que a tela mostra
    # é o que se confere contra o painel
    ver("a dica das Finalizadas", k["finTitle"], G.dica_finalizadas(num))
    for nome, chave in _LISTA_DO_PAINEL.items():
        esperado, baixa = list(painel["opcoes"][chave]), {v.lower() for v in painel["opcoes"][chave]}
        for v in getattr(f, nome):                       # o escolhido fica na lista mesmo sem tarefa (regra do Nexus)
            if v.lower() not in baixa:
                baixa.add(v.lower())
                esperado.append(v)
        ver(f"a lista {nome}", esperado, rec.escolhas[nome], oculto=nome in ("responsavel", "etiqueta"))
    if f.atr:
        pl, rows = painel["plana"], a["so_atrasadas"]
        # diferença de propósito: o painel abre a mensagem com um emoji (🎉); o Nexus não usa emoji na interface
        ver("Só atrasadas vazia", pl["msg"] and re.sub(r"^\W+", "", pl["msg"]), G.MSG_SEM_ATRASADA if not rows else None)
        ver("Só atrasadas: linhas", len(pl["rows"]), len(rows))
        if rows:
            ver("Só atrasadas: contagem", pl["cnt"], str(len(rows)))
            ver("Só atrasadas: o limite do vermelho", pl["lim"], str(alerta))
        for i, (x, y) in enumerate(zip(pl["rows"], rows)):
            for campo in ("dias", "os", "cliente", "usina", "tipo", "estado", "prog"):
                ver(f"Só atrasadas {i} {campo}", x[campo], y[campo])
            ver(f"Só atrasadas {i} cor dos dias", _DIAS.get(x["diasCls"], x["diasCls"]), y["dias_cls"])
            ver(f"Só atrasadas {i} cor do estado", _ESTADO.get(x["estadoCls"], x["estadoCls"]), y["estado_cls"])
            for campo in ("tarefa", "etiquetas", "obs"):
                ver(f"Só atrasadas {i} {campo}", x[campo], y[campo], oculto=True)
        return n, dif
    arv, nx = painel["arvore"], a["arvores"]
    ver("a mensagem", arv["msg"], G.MSG_SEM_TAREFA if not num["todas"] else (G.MSG_SO_NF if not nx["todas"]["n"] else None))
    ver("Não Finalizadas no Período", arv["nfN"], str(nx["nf"]["n"]) if nx["nf"]["n"] else None)
    if nx["todas"]["clientes"]:
        ver("a árvore abre sozinha", arv["aberta"], nx["todas"]["aberta"])
    for qual, lista in (("nf", a["nf"]), ("todas", a["arr"])):
        pa, nb = arv[qual], _nos(nx[qual]["clientes"])
        ver(f"árvore {qual}: nós", len(pa), len(nb))
        # as tabelas: as linhas de cada tipo pelo mesmo caminho da árvore que abre sozinha (`linhas`), e a rota da
        # tabela (`tarefas_do_no`) conferida em parte dos nós
        linhas = {}
        for c in G.arvore(lista, alerta, linhas=True):
            for u in c["usinas"]:
                for x in u["tipos"]:
                    linhas[(c["nome"], u["nome"], x["nome"])] = x["linhas"]
        cli = usi = ""
        for i, (x, y) in enumerate(zip(pa, nb)):
            rot = f"árvore {qual} nó {i} ({x['k']}:{x['nome']})"
            for campo in ("k", "nome", "n", "atr"):
                ver(f"{rot} {campo}", x.get(campo), y.get(campo))
            cli, usi = (x["nome"], "") if x["k"] == "c" else (cli, x["nome"] if x["k"] == "u" else usi)
            if x["k"] != "t" or str(x.get("idx")) not in painel["tabelas"]:
                continue
            tab, minhas = painel["tabelas"][str(x["idx"])], linhas.get((cli, usi, x["nome"])) or []
            if i % 25 == 0:
                ver(f"{rot}: a rota da tabela", G.tarefas_do_no(lista, cli, usi, x["nome"], alerta), minhas or None)
            ver(f"{rot}: linhas", len(tab), len(minhas))
            for j, (p, m) in enumerate(zip(tab, minhas)):
                for campo in ("os", "estado", "prog", "fim", "dias"):
                    ver(f"{rot} linha {j} {campo}", p[campo], m[campo])
                ver(f"{rot} linha {j} cor do estado", _ESTADO.get(p["estadoCls"], p["estadoCls"]), m["estado_cls"])
                ver(f"{rot} linha {j} cor dos dias", _DIAS.get(p["diasCls"], p["diasCls"]), m["dias_cls"])
                ver(f"{rot} linha {j} tarefa", p["tarefa"], m["tarefa"], oculto=True)
                ver(f"{rot} linha {j} etiquetas", p["etiquetas"],
                    m["etiquetas"] + ([f"+{m['etiquetas_mais']}"] if m["etiquetas_mais"] else []), oculto=True)
    return n, dif


def rodar_node(entrada: dict) -> dict:
    node = shutil.which("node")
    if not node:
        raise SystemExit("A prova precisa do node no PATH (o JavaScript do painel roda nele). Instale o Node.js LTS.")
    env = dict(os.environ, TZ="America/Sao_Paulo")      # o painel conta as datas no fuso de Brasília (navegador daqui)
    p = subprocess.run([node, str(AQUI / "prova_gestao.js")], input=json.dumps(entrada).encode("utf-8"),
                       capture_output=True, env=env, timeout=900)
    if p.returncode:
        raise SystemExit("o node falhou: " + p.stderr.decode("utf-8", "replace")[-2000:])
    return json.loads(p.stdout.decode("utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--painel", default=RAIZ_PAINEL, help="pasta local do gridco-pcm-data ou o endereço raw do repositório")
    ap.add_argument("--dados", default=fonte.URL_GESTAO, help="o gestao_pcm.json (arquivo ou endereço)")
    ap.add_argument("--max-dif", type=int, default=25, help="quantas divergências mostrar")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")       # o console do Windows não é UTF-8

    t0 = time.perf_counter()
    js = {"preventivas": _ler(a.painel, "js/preventivas.js").decode("utf-8"), "app": _ler(a.painel, "js/app.js").decode("utf-8")}
    bruto = (urllib.request.urlopen(urllib.request.Request(a.dados, headers={"User-Agent": "Nexus-GridCo/1 (prova)"}),  # noqa: S310
                                    timeout=120).read() if a.dados.startswith(("http://", "https://"))
             else Path(a.dados).read_bytes())
    gestao = json.loads(bruto.decode("utf-8"))
    # o relógio dos dois lados: hoje às 15:00 de Brasília (18:00 UTC), quando o "hoje" do painel (que é o dia UTC)
    # e o do Nexus (Brasília) são o mesmo dia
    fixo = G.agora().replace(hour=15, minute=0, second=0, microsecond=0)
    G.agora = lambda: fixo                                                   # noqa: E731 — só nesta execução
    h, meses_ = fixo.date(), G.meses(fixo.date())

    senha = os.environ.get("NEXUS_PCM_MPAS_SENHA", "")
    if senha:
        mp = G.decifrar(json.loads(_ler(a.painel, "mpas.json")), senha)
        qual_ger = "a Gerencial de verdade (mpas.json decifrado em memória)"
    else:
        mp = gerencial_sintetica(gestao.get("tarefas") or [], h)
        qual_ger = f"uma Gerencial SINTÉTICA ({len(mp['manut'])} manutenções feitas das OS de MPA/MPS do JSON; sem a senha)"
    esc = G.escopo(gestao.get("tarefas") or [])
    total_n, total_dif, total_casos = 0, [], 0
    for ger, rotulo in ((False, "sem a Gerencial (lado do Fracttal)"), (True, "com " + qual_ger)):
        cs = casos(gestao.get("tarefas") or [], meses_)
        # a aba além do Plano & Fila não depende da Gerencial: vai só na primeira rodada
        ca = [] if ger else casos_arv(gestao.get("tarefas") or [], meses_)
        tudo = rodar_node({"js": js, "gestao": gestao, "mp": mp if ger else None,
                           "agora": int(fixo.timestamp() * 1000), "casos": cs, "casosArv": ca})
        saida = tudo["casos"]
        n_rodada, dif_rodada = 0, []
        for c in cs:
            n, dif = comparar(saida[c["id"]], nexus(c, esc, mp if ger else None, meses_, h), c, ger)
            n_rodada += n
            dif_rodada += dif
        print(f"Plano & Fila {rotulo}: {len(cs)} casos, {n_rodada} valores comparados, {len(dif_rodada)} divergências")
        total_n, total_dif, total_casos = total_n + n_rodada, total_dif + dif_rodada, total_casos + len(cs)
        if ca:
            n_aba, dif_aba = 1, []
            if tudo["sub"] != G.atualizado(gestao):
                dif_aba.append(f"a linha Atualizado: painel={tudo['sub']!r} nexus={G.atualizado(gestao)!r}")
            for c in ca:
                n, dif = comparar_aba(tudo["arv"][c["id"]], c, esc, gestao)
                n_aba += n
                dif_aba += dif
            print(f"a aba (números, árvores, Só atrasadas, listas): {len(ca)} casos, {n_aba} valores comparados, "
                  f"{len(dif_aba)} divergências")
            total_n, total_dif, total_casos = total_n + n_aba, total_dif + dif_aba, total_casos + len(ca)
    # a versão do JavaScript provado: se o painel mudar o preventivas.js ou o app.js, o resumo muda e a prova tem de
    # rodar de novo
    versao_js, versao_app = (hashlib.sha256(js[k].encode("utf-8")).hexdigest()[:12] for k in ("preventivas", "app"))
    print(f"gestao_pcm.json de {gestao.get('geradoEm')} ({len(gestao.get('tarefas') or [])} tarefas), preventivas.js "
          f"sha256 {versao_js}, app.js sha256 {versao_app}, relógio em {fixo:%d/%m/%Y %H:%M} "
          f"(meses {', '.join(meses_)}), {time.perf_counter() - t0:.0f} s")
    for d in total_dif[:a.max_dif]:
        print("  " + d)
    print(f"BATE célula a célula: {total_casos} casos, {total_n} valores." if not total_dif
          else f"NÃO BATE: {len(total_dif)} divergências em {total_casos} casos.")
    return 0 if not total_dif else 1


if __name__ == "__main__":
    sys.exit(main())
