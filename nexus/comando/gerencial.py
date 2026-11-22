"""Comando › Visão gerencial (teste), 19/11/2026: o portfólio que afunila e a nota de cumprimento do contrato.

Levi, 18/11/2026, com o prontuário da usina no ar: "já conseguimos falar muito bem com quem está focado no campo, mas e para
a gestão? Como a gestão pode acompanhar as carteiras, como está por cliente" e "Quero uma visão do portfólio inteiro
puxando mensal por contratos da parte de COMANDO > CONTRATOS. Portfólio Grid Co, clientes, usinas, MWp e valor mensal,
depois vai afunilando, clientes e depois usinas". Aprovou o desenho em mockup com dado real (o portfólio com o símbolo em
verde 3D, o parque do cliente em blocos e a tela que explica a nota) e mandou: "sobe como Visão gerencial (teste)".

O que este módulo faz (puro: nada de rede, banco nem Flask; quem junta as fontes é `torres/comando/gerencial_tela.py`):

- `montar`: o que a página lê, por cliente e por usina, com o que o contrato diz (o valor mensal, a vigência, a garantia de
  disponibilidade, o valor de cada usina) e a nota de cada usina em cada mês do filtro.
- `nota_do_contrato`: a NOTA DE CUMPRIMENTO DO CONTRATO de uma usina num mês. O Levi pediu "um score de contratos" em cima
  dos blocos e, perguntado (o Comando › Contratos não tem nota: as regras lidas são texto e as obrigações não têm usina),
  escolheu o cumprimento do contrato por usina com quatro itens: disponibilidade, geração e PR, rotinas e prazos de OS.
  Cada item compara o que o contrato pede com o que o Nexus já mede, vale de 0 a 100, e a nota é a MÉDIA SIMPLES dos itens
  medidos. E "quando eu clicar na UFV tem que explicar esse número": cada item leva o texto do que o contrato pede, do que
  o Nexus mediu e da conta.

A RÉGUA É UMA PROPOSTA (o "(teste)" do nome): os números abaixo (20 por ponto percentual, ronda a cada 7 dias, 25 por
urgente, 10 por atrasada, no mínimo 2 itens) foram mostrados ao Levi no mockup e ainda esperam o OK dele. Mudou a régua,
muda aqui e no `nexus/comando/CLAUDE.md`.

O que fica FORA da nota, e por quê (sem dado não se inventa, e zero não cobre dado):
- item sem garantia no contrato (7 dos 16 contratos não garantem disponibilidade) ou sem dado no Nexus;
- PR acima de 100%: é leitura errada (18/11/2026: uma usina com 558,7% em outubro valeria nota cheia com o teto);
- a ronda da usina nunca rondada pelo App (a E1 é corretiva por demanda: a régua de ronda não é dela);
- no MÊS FECHADO, os prazos de OS (a pendência que o Nexus tem é a de hoje, não a do fim do mês) e o plano da semana do
  PCM (não fica guardado por mês): as rotinas viram as rondas do mês contra uma por semana;
- usina com menos de dois itens medidos fica SEM nota (a E1, sem ronda, geração nem disponibilidade, sairia com 100 só por
  não ter OS atrasada).
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date

from . import diagnostico_mes as DM
from . import expurgos as EXP

# ── a régua (proposta de 19/11/2026) ─────────────────────────────────────────────────────────────────────────────────
POR_PONTO_DISP = 20            # cada ponto percentual de disponibilidade abaixo da garantida
RONDA_DIAS = 7                 # a régua de ronda do Nexus (a regra R11 dos Insights): uma a cada 7 dias
POR_DIA_SEM_RONDA = 10         # cada dia além dos 7 sem ronda
POR_URGENTE, POR_ATRASADA = 25, 10
MIN_ITENS = 2                  # com um item só não há nota
PR_MAX = 100.0                 # acima disso o PR é leitura errada
EM_DIA, ATENCAO = 80, 55       # as faixas da cor, as mesmas da pontuação do dossiê do cliente (`dossie_cliente`)

_ROMANOS = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}
_SOLTAS = ("ufv", "usina", "de", "do", "da")
_PCT = re.compile(r"(\d{2,3}(?:[.,]\d+)?)\s*%")
_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro",
          "dezembro")


def _arred(x: float) -> int:
    """Meio para cima (92,5 vira 93): é a conta que a tela mostra ao lado, e o round() do Python daria 92."""
    return int(x + 0.5)


def _num(v, casas: int = 1) -> str:
    return f"{float(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v) -> str:
    return _num(v, 1) + "%"


def _media(v: list) -> float:
    return sum(v) / len(v)


def _maiuscula(t: str) -> str:
    return t[:1].upper() + t[1:]


# ── os nomes: o do contrato e o do cadastro ──────────────────────────────────────────────────────────────────────────
def _plano(t) -> str:
    """O nome sem acento, sem caixa e com o romano em número ("UFV Sol Nascente II" → "sol nascente 2")."""
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(p for p in (_ROMANOS.get(x, x) for x in re.sub(r"[^a-z0-9]+", " ", t).split()) if p not in _SOLTAS)


def _base(t) -> str:
    """O nome sem o número e sem o que vem entre parênteses: "Tupi Paulista 1" e "Tupi Paulista" dão o mesmo."""
    return " ".join(p for p in _plano(re.sub(r"\(.*?\)", " ", str(t or ""))).split() if not p.isdigit() and p not in ("e", "a"))


def chave_cliente(nome) -> str:
    """O cliente do contrato e o do cadastro escritos do mesmo jeito ("RenoGrid" e "Renogrid"; "E1 Energia" e "E1")."""
    c = _plano(nome)
    return {"e1 energia": "e1"}.get(c, c)


def garantia_de_disponibilidade(ficha: dict | None) -> dict | None:
    """A disponibilidade que o contrato garante, como o Contratos leu: a 1ª regra de "Disponibilidade e desempenho" com
    "disponibilidade" no nome e um percentual no texto: {pct, nome, texto, clausula}. Sem regra assim, None: o contrato
    NÃO garante, e o item fica fora da nota (não se inventa 98%)."""
    for k in (ficha or {}).get("contratos") or []:
        for r in k.get("regras") or []:
            if r.get("categoria") != "Disponibilidade e desempenho" or "disponibilidade" not in str(r.get("nome")).lower():
                continue
            texto = str(r.get("vigente") or r.get("contratual") or "")
            p = _PCT.search(texto) or _PCT.search(str(r.get("nome")))
            if p:
                return {"pct": float(p.group(1).replace(",", ".")), "nome": str(r.get("nome") or ""), "texto": texto[:220],
                        "clausula": str((r.get("ref") or {}).get("clausula") or "")}
    return None


def valores_por_usina(ficha: dict | None, usinas: list[dict]) -> dict:
    """{nome da usina no cadastro: valor mensal dela no contrato}, só onde a ligação não deixa dúvida. O contrato escreve o
    nome da usina do jeito dele, então a ligação tenta, nesta ordem: (1) o mesmo nome (sem acento, romano em número); (2) o
    código da usina dentro do nome do contrato ("UFV CPP100 (...)"); (3) o nome SEM o número, quando ele é único no
    cadastro do cliente E no contrato ("Tupi Paulista" x "Tupi Paulista 1") e a potência bate (15%); "União 1 e 2" soma as
    duas linhas do contrato. O resto fica sem valor ("sem ligação"): não se chuta."""
    valores = []
    for k in (ficha or {}).get("contratos") or []:
        v, us_k = k.get("valor") or {}, k.get("usinas") or []
        por = [x for x in (v.get("por_usina") or []) if isinstance(x, dict) and isinstance(x.get("mensal"), (int, float))]
        for x in por:
            nome = x.get("usina") or (us_k[0].get("nome") if len(us_k) == 1 else "")
            valores.append({"nome": nome, "mensal": float(x["mensal"]), "kwp": x.get("potencia_kwp")})
        if not por and isinstance(v.get("mensal"), (int, float)) and len(us_k) == 1:
            valores.append({"nome": us_k[0].get("nome"), "mensal": float(v["mensal"]), "kwp": us_k[0].get("potencia_kwp")})
    out = {}
    for u in usinas:
        nome, curto = u["usina"], str(u.get("codigo") or "").split("-")[-1].lower()
        achou = next((v for v in valores if _plano(v["nome"]) == _plano(nome)), None) or \
            next((v for v in valores if curto and curto in str(v["nome"]).lower().replace(" ", "")), None)
        if achou:
            out[nome] = achou["mensal"]
            continue
        if not _base(nome) or sum(1 for x in usinas if _base(x["usina"]) == _base(nome)) != 1:
            continue
        cand, mw = [v for v in valores if _base(v["nome"]) == _base(nome)], u.get("mwp")
        if len(cand) == 1 and not (cand[0].get("kwp") and mw and abs(cand[0]["kwp"] / 1000 - mw) > 0.15 * mw):
            out[nome] = cand[0]["mensal"]
        elif len(cand) == 2 and re.search(r"\d (e|a) \d", _plano(nome)):
            out[nome] = round(cand[0]["mensal"] + cand[1]["mensal"], 2)
    return out


# ── a nota ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def nota_do_contrato(garantia: dict | None, m: dict, u: dict, atual: bool, semanas: int, expurgo: dict | None = None) -> dict:
    """{nota (0 a 100, ou None), itens: [{nome, nota (ou None = fora), pede, mediu, conta[, expurgo]}], medidos}.

    `garantia` = `garantia_de_disponibilidade`; `m` = o mês: {meta, pr, pr_prev, disp} e, no fechado, {rondas}; `u` = o
    que é de agora: {ronda_dias, nunca_rondada, plano_pct, plano_txt, os_abertas, os_urgentes, os_atrasadas_n,
    mais_antiga_d}; `atual` = o mês vigente (parcial, até ontem); `semanas` = quantas rondas o mês fechado pede.
    `expurgo` (22/11/2026) = `expurgos.aplicar`: a nota usa o mês COM o expurgo do contrato, e a Disponibilidade e a
    Geração e PR levam o texto do que saiu (a cláusula e o número sem o expurgo)."""
    if expurgo:
        m = expurgo["m"]
    itens, quando = [], (" no mês, até ontem." if atual else " no mês fechado.")
    disp = m.get("disp")
    if garantia:
        g = garantia["pct"]
        pede = (f"Mínima de {_num(g, 1 if g % 1 else 0)}%: \"{garantia['nome']}\""
                + (f" (cláusula {garantia['clausula']})" if garantia.get("clausula") else "") + f". {garantia.get('texto') or ''}").strip()
    else:
        pede = "O contrato lido não garante uma disponibilidade."
    if not garantia or disp is None:
        itens.append({"nome": "Disponibilidade", "nota": None, "pede": pede,
                      "mediu": "Sem disponibilidade publicada no mês." if disp is None else _pct(disp) + quando,
                      "conta": "Fica fora da nota."})
    else:
        falta = max(0.0, garantia["pct"] - disp)
        itens.append({"nome": "Disponibilidade", "nota": max(0, _arred(100 - POR_PONTO_DISP * falta)), "pede": pede,
                      "mediu": _pct(disp) + quando,
                      "conta": (f"{_num(falta, 1)} {'pontos percentuais' if falta >= 2 else 'ponto percentual'} abaixo da garantida; "
                                f"cada ponto tira {POR_PONTO_DISP}.") if falta > 0 else "Na garantida ou acima: 100."})

    p, t = [], []
    meta, pr, prev = m.get("meta"), m.get("pr"), m.get("pr_prev")
    if meta is not None:
        p.append(min(100.0, meta))
        t.append(f"{_pct(meta)} da meta de geração")
    if pr is not None and prev and pr <= PR_MAX:
        p.append(min(100.0, 100.0 * pr / prev))
        t.append(f"PR de {_pct(pr)} para {_pct(prev)} previstos")
    elif pr is not None and pr > PR_MAX:
        t.append(f"PR de {_pct(pr)} é leitura errada e fica fora")
    itens.append({"nome": "Geração e PR", "nota": _arred(_media(p)) if p else None,
                  "pede": "A meta de geração do mês e o PR previsto, os que o Nexus já usa.",
                  "mediu": _maiuscula("; ".join(t)) + "." if t else "Sem meta e sem PR publicados.",
                  "conta": "Fica fora da nota." if not p else ("Média dos dois, cada um com teto de 100." if len(p) == 2
                                                                else "Só um dos dois entrou; teto de 100.")})

    if atual:
        p, t, k = [], [], []
        dias = u.get("ronda_dias")
        if dias is not None:
            nr = max(0, 100 - POR_DIA_SEM_RONDA * max(0, dias - RONDA_DIAS))
            p.append(nr)
            k.append(f"ronda {nr}")
            t.append("ronda hoje" if dias == 0 else f"última ronda há {dias} {'dia' if dias == 1 else 'dias'}")
        elif u.get("nunca_rondada"):
            t.append("nunca rondada pelo App (fora da conta)")
        if u.get("plano_pct") is not None:
            p.append(u["plano_pct"])
            k.append(f"plano {_arred(u['plano_pct'])}")
            t.append(f"plano da semana em {_arred(u['plano_pct'])}%" + (f" ({u['plano_txt']})" if u.get("plano_txt") else ""))
        itens.append({"nome": "Rotinas", "nota": _arred(_media(p)) if p else None,
                      "pede": f"Ronda a cada {RONDA_DIAS} dias, a régua do Nexus, e o plano da semana do PCM cumprido.",
                      "mediu": _maiuscula("; ".join(t)) + "." if t else "Sem ronda e sem plano da semana.",
                      "conta": (f"Média de {' e '.join(k)}. Cada dia além de {RONDA_DIAS} sem ronda tira {POR_DIA_SEM_RONDA}."
                                if p else "Fica fora da nota.")})
    else:
        rondas = m.get("rondas")
        tem = rondas is not None and not (u.get("nunca_rondada") and not rondas)
        itens.append({"nome": "Rotinas", "nota": min(100, _arred(100 * rondas / semanas)) if tem else None,
                      "pede": f"Ronda a cada {RONDA_DIAS} dias, a régua do Nexus: {semanas} no mês. O plano da semana do PCM não "
                              "fica guardado por mês.",
                      "mediu": ("Sem o fechamento do mês." if rondas is None else "Nunca rondada pelo App." if not tem
                                else f"{rondas} {'ronda feita' if rondas == 1 else 'rondas feitas'} no mês."),
                      "conta": f"{rondas} de {semanas} esperadas, com teto de 100." if tem else "Fica fora da nota."})

    if not atual:
        itens.append({"nome": "Prazos de OS", "nota": None, "pede": "Nenhuma OS urgente parada e nenhuma atrasada.",
                      "mediu": "As pendências são as de hoje: o Nexus não guarda como elas estavam no fim do mês.",
                      "conta": "Fica fora da nota do mês fechado."})
    elif u.get("os_abertas") is None:
        itens.append({"nome": "Prazos de OS", "nota": None, "pede": "Nenhuma OS urgente parada e nenhuma atrasada.",
                      "mediu": "Sem as OS da usina no Nexus.", "conta": "Fica fora da nota."})
    else:
        urg, atr, antiga = u.get("os_urgentes") or 0, u.get("os_atrasadas_n") or 0, u.get("mais_antiga_d")
        itens.append({"nome": "Prazos de OS", "nota": max(0, 100 - POR_URGENTE * urg - POR_ATRASADA * atr),
                      "pede": "Nenhuma OS urgente parada (religamento, corretiva emergencial) e nenhuma atrasada (programada há "
                              "mais de 10 dias, a régua do PCM).",
                      "mediu": (f"{urg} {'urgente não iniciada' if urg == 1 else 'urgentes não iniciadas'} e {atr} "
                                f"{'OS atrasada' if atr == 1 else 'OS atrasadas'}"
                                + (f", a mais antiga há {antiga} dias" if antiga else "") + "."),
                      "conta": f"Cada urgente tira {POR_URGENTE} e cada atrasada tira {POR_ATRASADA}."})

    if expurgo:
        for it in itens:
            texto = {"Disponibilidade": expurgo.get("disp"), "Geração e PR": expurgo.get("ger")}.get(it["nome"])
            if texto:
                it["expurgo"] = texto
    medidos = [i["nota"] for i in itens if i["nota"] is not None]
    return {"nota": _arred(_media(medidos)) if len(medidos) >= MIN_ITENS else None, "itens": itens, "medidos": len(medidos)}


# ── a montagem ───────────────────────────────────────────────────────────────────────────────────────────────────────
def meses(hoje: date) -> list[dict]:
    """Os meses do filtro, o vigente primeiro (é o que abre; Levi, 19/11/2026: "é bom estar filtrado por mês sempre
    mostrando o mês atual"), até o 1º mês do banco de performance (`diagnostico_mes.PRIMEIRO_MES`)."""
    out = []
    for mid, _rot, vigente in DM.meses(hoje):
        a, m = int(mid[:4]), int(mid[5:7])
        out.append({"id": mid, "nome": f"{_MESES[m - 1]} de {a}", "curto": _MESES[m - 1], "atual": vigente,
                    "semanas": _arred(calendar.monthrange(a, m)[1] / 7)})
    return out


def montar(usinas: list[dict], contratos: dict | None, hoje: date, gerado: str, avisos: list[str] | None = None,
           expurgos: dict | None = None) -> dict:
    """O que a página lê. `usinas` = uma por usina mobilizada: {uid, usina, cliente, codigo, mwp, pontos (a saúde, do
    dossiê do cliente), o que é de agora (ver `nota_do_contrato`) e `meses` {"AAAA-MM": {meta, pr, pr_prev, disp[,
    rondas]}}}. `contratos` = o `edicao.visao` do Comando › Contratos (as listas `contratos` e `fichas`), ou None quando
    ele não abriu: a tela segue sem os valores e diz. `expurgos` (22/11/2026) = {"rede": {"AAAA-MM": {uid: ...}},
    "limitacao": {...}} (`expurgos.rede_por_usina` e `limitacao_por_usina`): o que cada contrato deixa tirar da conta
    (`expurgos.do_contrato`) sai da nota de cada mês."""
    ms = meses(hoje)
    ex = expurgos or {}
    atual = ms[0]["id"]
    por_chave = {chave_cliente(c.get("cliente")): c for c in (contratos or {}).get("contratos") or []}
    fichas = {chave_cliente(n): f for n, f in ((contratos or {}).get("fichas") or {}).items()}
    grupos: dict[str, list[dict]] = {}
    for u in usinas:
        grupos.setdefault(str(u.get("cliente") or "sem cliente"), []).append(u)
    clientes = []
    for nome, us in grupos.items():
        c, f = por_chave.get(chave_cliente(nome)), fichas.get(chave_cliente(nome))
        garantia = garantia_de_disponibilidade(f)
        cont = EXP.do_contrato(f)
        valores = valores_por_usina(f, us)
        saida = []
        for u in sorted(us, key=lambda x: (-(x.get("mwp") or 0), str(x["usina"]).lower())):
            um = u.get("meses") or {}
            score = {}
            for m in ms:
                mm = um.get(m["id"]) or {}
                exp = EXP.aplicar(cont, mm, {k: ((ex.get(k) or {}).get(m["id"]) or {}).get(u.get("uid")) or {}
                                             for k in ("rede", "limitacao")})
                score[m["id"]] = nota_do_contrato(garantia, mm, u, m["atual"], m["semanas"], expurgo=exp)
            saida.append({"uid": u.get("uid"), "usina": u["usina"], "mwp": u.get("mwp"), "pontos": u.get("pontos"),
                          "valor": valores.get(u["usina"]), "meses": {m["id"]: um.get(m["id"]) or {} for m in ms}, "score": score})
        notas = {m["id"]: [x["score"][m["id"]]["nota"] for x in saida if x["score"][m["id"]]["nota"] is not None] for m in ms}
        com_perf = [u for u in us if (lambda x: x.get("meta") is not None or x.get("pr") is not None)((u.get("meses") or {}).get(atual) or {})]
        pts = [u["pontos"] for u in us if u.get("pontos") is not None]
        info = (c or {}).get("valor_info") or {}
        clientes.append({
            "cliente": nome, "usinas_n": len(us), "mwp": round(sum(u.get("mwp") or 0 for u in us), 1),
            # a saúde média só existe com performance publicada: sem meta nem PR, a pontuação alta não quer dizer saúde
            "media": _arred(_media(pts)) if pts and com_perf else None,
            "tem_contrato": c is not None, "valor": (c or {}).get("valor_mensal"), "minuta": bool(info.get("minuta")),
            "inicio": (c or {}).get("inicio"), "fim": (c or {}).get("fim"), "dias_fim": (c or {}).get("dias_fim"),
            "obrigacoes_atrasadas": (c or {}).get("atrasadas") or 0, "disp_garantida": garantia,
            # o que o contrato expurga (22/11/2026), na ordem da lista da Grid
            "expurga": [EXP.CATEGORIAS[k][0] for k in EXP.CATEGORIAS if k in cont["cats"]],
            "score": {mid: {"nota": _arred(_media(v)) if v else None, "usinas": len(v)} for mid, v in notas.items()},
            "usinas": saida})
    clientes.sort(key=lambda x: (-x["mwp"], x["cliente"].lower()))
    com_valor = [c["valor"] for c in clientes if isinstance(c["valor"], (int, float)) and c["valor"]]
    return {"ok": True, "gerado": gerado, "mes_atual": atual, "meses": ms, "contratos_ok": contratos is not None,
            "avisos": list(avisos or []), "clientes": clientes,
            "regua": {"em_dia": EM_DIA, "atencao": ATENCAO},
            "totais": {"clientes": len(clientes), "usinas": sum(c["usinas_n"] for c in clientes),
                       "mwp": round(sum(c["mwp"] for c in clientes), 1),
                       "valor": round(sum(com_valor), 2) if contratos is not None else None, "com_valor": len(com_valor)}}
