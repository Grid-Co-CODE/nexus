"""A aba Indicadores do contrato (Comando › Contratos, 26/11/2026): o ano contratual mês a mês, usina por usina.

A sugestão de 26/11/2026: "Uma aba Indicadores no contrato [...] uma matriz: meses do ano contratual nas
colunas, usinas nas linhas", com MPM, MPS e MPA feitas sobre as planejadas, a supressão vegetal e a lavagem de módulos com
a data em que foram feitas (contra o mínimo do contrato), o PR e a disponibilidade expurgada contra a meta do contrato; no
alto, os números do contrato inteiro ponderados pela potência. O Levi, no mesmo dia, junto: "ANIVERSÁRIO DE CONTRATO,
RELATÓRIO DE ANIVERSÁRIO DE CONTRATO". Escolhas dele: o ano conta do início da vigência; entram TODAS as usinas do cliente
no cadastro (como a Visão gerencial); o mês sem dado no banco diz "sem dado" (nunca 0); a régua de cor é a da sugestão
(verde na meta, amarelo até 2 pontos abaixo, vermelho abaixo disso, azul com asterisco quando o mês teve expurgo).

As fontes chegam prontas (a tela as junta, `torres/comando/contratos_tela.py`), cada uma a que a tela dona já usa:
- o PR e a disponibilidade, bruta e com o expurgo do contrato: a conta da Visão gerencial (`gerencial.montar`, usina por
  `usina_id`); o banco tem esses meses só desde 10/2026 (`diagnostico_mes.PRIMEIRO_MES`);
- MPM, MPS e MPA: as tarefas do ano do PCM (`pcm.gestao.classificar`: a sigla no nome e o mês da Data Programada; feita =
  "Finalizada"), ligadas à usina pelo nome (`campo.responsaveis.Nomes`);
- a supressão vegetal (roçagem e poda química) e a lavagem (limpeza de módulos): o Radar da Zeladoria (como o Histórico
  de Serviços os junta, `servicos_do_radar`) e as OS finalizadas do Fracttal (`tipo_da_tarefa`, `juntar_servicos`); o
  mínimo do ano, o `zeladoria_contratual` do Radar por UFV (só o "fixo": o "sob demanda" não tem mínimo). Cada mês diz
  feita ou não, sobre o PR expurgado (Levi, 26/11/2026: "tem que mostrar se foi feita ou não sobre o PR expurgado"): o mês
  sem o serviço, com o PR expurgado abaixo da meta e a ronda em 4 ou 5 (sujidade para a lavagem, vegetação para a
  supressão), fica em atenção. Não há perda por sujidade medida em lugar nenhum (o chat da Performance, 26/11/2026: o
  expurgo do contrato só tira a rede e a limitação), então a célula não inventa número;
- as metas: a garantia de disponibilidade e o PR que o contrato lido escreve (as regras de "Disponibilidade e desempenho"),
  ou o que o gestor gravou nos Dados do contrato, que vence.

Puro: nada de rede nem Flask. A ligação pelo nome é medida (quantas tarefas e serviços casaram com uma usina do cliente)
e a tela mostra: o que não casou não some calado.
"""
from __future__ import annotations

import re
from datetime import date

SIGLAS = ("MPM", "MPS", "MPA")
FAIXA = 2.0                                  # pontos abaixo da meta que ainda são amarelo (a régua da sugestão)
# o PR acima de 100% é leitura errada (a régua da Visão gerencial, `gerencial.PR_MAX`): na 1ª prévia, 26/11/2026, uma
# usina da Thopen com PR de mais de 1.000% fez o PR do contrato dar 730,5%
PR_MAX = 100.0
_MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
_PCT = re.compile(r"(\d{2,3}(?:[.,]\d+)?)\s*%")
# a vegetação e a sujidade das rondas (26/11/2026, Levi: "Vegetação e sujidade. Tem na parte de rondas. Do usinas 360°.
# Isso daí aparece bastante"): ao lado do serviço, o pior nível do mês que a ronda leu (de 1 a 5)
LINHAS = (("MPM", "MPM", "manut"), ("MPS", "MPS", "manut"), ("MPA", "MPA", "manut"),
          ("rocada", "Supressão vegetal", "manut"), ("veg", "Vegetação na ronda", "manut"),
          ("lavagem", "Lavagem de módulos", "manut"), ("suj", "Sujidade na ronda", "manut"),
          ("pr", "PR expurgado", "kpi"), ("disp", "Disponibilidade expurgada", "kpi"))
# a garantia de disponibilidade onde o contrato não traz o número (Levi, 26/11/2026: "Garantia de disponibilidade. Bota
# 99% para tudo [...] As que faltam, bota 99%")
DISP_PADRAO = 99.0
NIVEL_TXT = {1: "muito baixa", 2: "baixa", 3: "média", 4: "alta", 5: "muito alta"}


def tom_nivel(n) -> str:
    """A régua das Rondas (`campo.visao.criticidade`): 5 crítico, 4 atenção; 1 a 3, ok."""
    return "" if n is None else ("critico" if n >= 5 else ("alerta" if n == 4 else "ok"))


# os serviços de zeladoria feitos, como o Histórico de Serviços e a análise do Radar os juntam (Levi, 26/11/2026: "a
# lavagem de módulos está na parte de zeladoria. Eu creio que seja em histórico de serviços"): o retrato do cronograma,
# que a aba lia antes, trazia 28 lavagens; as tabelas, mais (16 no histórico, 33 nas OS de contrato, 9 na rota)
_TIPO_RADAR = {"ROCAGEM": "rocada", "PODA QUIMICA": "rocada", "LIMPEZA DE MODULOS": "lavagem"}
_PRIORIDADE = {"app": 3, "manual": 2, "planilha_historica": 1}


def _sem_acento(t) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(c) != "Mn").upper().strip()


def servicos_do_radar(abas: dict, hoje_iso: str) -> list[dict]:
    """[{usina_radar, usina, codigo, cliente, tipo ("rocada" | "lavagem"), servico, data, origem, os}]: a mesma conta do
    `analiseTimelinePorUsina` do clone do Radar. Entram o histórico de serviços (`servicos_zeladoria`), a cotação com a
    execução terminada, a rota da equipe (o fim do serviço na etapa, ou o fim da rota concluída) e a OS de contrato com a
    execução terminada; o mesmo serviço na mesma usina e no mesmo dia vale uma vez (o do app vence o manual, que vence o da
    planilha histórica). Sem data, fora. O planejado (diarista) não está nas tabelas copiadas e fica fora."""
    usinas = {str(u.get("id")): u for u in abas.get("usinas") or [] if not u.get("excluido")}
    por_nome = {_sem_acento(u.get("usina")): u for u in usinas.values()}
    itens = []

    def junta(u, servico, data, origem, rotulo, os_=None):
        tipo = _TIPO_RADAR.get(_sem_acento(servico))
        data = str(data or "")[:10]
        if not u or not tipo or len(data) != 10 or data > hoje_iso:
            return
        itens.append({"usina_radar": str(u.get("id")), "usina": u.get("usina") or "", "codigo": u.get("codigo") or "",
                      "cliente": u.get("cliente") or "", "tipo": tipo, "servico": str(servico).strip(), "data": data,
                      "origem": origem, "rotulo": rotulo, "os": str(os_ or "")})
    for s in abas.get("servicos_zeladoria") or []:
        if not s.get("excluido"):
            junta(usinas.get(str(s.get("usina_id"))), s.get("tipo"), s.get("data_termino"), s.get("origem") or "manual", "histórico de serviços")
    for c in abas.get("cotacoes") or []:
        if not c.get("excluido") and c.get("data_execucao_fim"):
            junta(por_nome.get(_sem_acento(c.get("usina"))), c.get("servico"), c.get("data_execucao_fim"), "app", "cotação fechada", c.get("numero_os"))
    for r in abas.get("rota_equipe") or []:
        if r.get("excluido"):
            continue
        u = usinas.get(str(r.get("usina_id")))
        et = r.get("etapas") if isinstance(r.get("etapas"), dict) else {}
        for sv in r.get("servicos") or []:
            ex = et.get(sv) if isinstance(et.get(sv), dict) else {}
            fim = ex.get("dataExecucaoFim")
            data = fim if fim and str(fim)[:10] <= hoje_iso else ((r.get("data_fim") or r.get("data_inicio")) if r.get("concluida") else None)
            junta(u, sv, data, "app", "rota da equipe", ex.get("numeroOs"))
    for o in abas.get("contrato_os") or []:
        if not o.get("excluido") and o.get("data_execucao_fim"):
            junta(usinas.get(str(o.get("usina_id"))), o.get("servico"), o.get("data_execucao_fim"), "app", "OS de contrato", o.get("numero_os"))
    melhor: dict = {}
    for i in itens:
        k = (i["usina_radar"], i["servico"].upper(), i["data"])
        if k not in melhor or _PRIORIDADE.get(i["origem"], 0) > _PRIORIDADE.get(melhor[k]["origem"], 0):
            melhor[k] = i
    return sorted(melhor.values(), key=lambda i: (i["data"], i["usina"]))


# a lavagem e a supressão nas OS finalizadas do Fracttal (26/11/2026): o Radar juntava 18 lavagens no ano; o arquivo do
# ano do PCM tinha 56 tarefas de limpeza de módulos finalizadas ("Acompanhamento - Limpeza de Módulos") e 194 de
# supressão. A inspeção "pré-lavagem" não é lavagem.
_RX_LAVAGEM = re.compile(r"limpeza (de |dos )?modulo|lavagem")
_RX_ROCADA = re.compile(r"supressao|rocada|rocagem|poda quimica")
_RX_NAO = re.compile(r"inspecao|pre-lavagem|pre lavagem")
JANELA_MESMO_SERVICO = 10                    # dias: a OS do Fracttal perto de um serviço do Radar é o mesmo serviço


def tipo_da_tarefa(tarefa) -> str | None:
    """"lavagem", "rocada" ou None para o nome da tarefa do Fracttal."""
    t = _sem_acento(tarefa).lower()
    if _RX_NAO.search(t):
        return None
    if _RX_LAVAGEM.search(t):
        return "lavagem"
    if _RX_ROCADA.search(t):
        return "rocada"
    return None


def juntar_servicos(radar: list[dict], fracttal: list[dict]) -> list[dict]:
    """Os serviços do Radar e as OS do Fracttal, numa lista por data, cada um {tipo, data, ...}: a OS do Fracttal a até
    `JANELA_MESMO_SERVICO` dias de um serviço do mesmo tipo já contado (do Radar, que vale, ou de outra OS do Fracttal:
    a lavagem de uma usina grande leva dias e mais de uma OS) é o mesmo serviço; duas tarefas da mesma OS contam uma vez."""
    out = sorted(radar, key=lambda x: x["data"])
    vistos = {(x["tipo"], x.get("os")) for x in out if x.get("os")}
    for f in sorted(fracttal, key=lambda x: x["data"]):
        if (f["tipo"], f.get("os")) in vistos:
            continue
        d = date.fromisoformat(f["data"])
        if any(x["tipo"] == f["tipo"] and abs((date.fromisoformat(x["data"]) - d).days) <= JANELA_MESMO_SERVICO for x in out):
            continue
        out.append(f)
        vistos.add((f["tipo"], f.get("os")))
    return sorted(out, key=lambda x: x["data"])


def ultimos_12_meses(hoje: date) -> dict:
    """A janela padrão da aba (Levi, 26/11/2026, vendo o ano contratual no ar: "puxa pelos últimos 12 meses até atualmente
    [...] sempre vai se atualizando, do que tá projetando um futuro que não tem dado, e aí mais da metade do negócio é sem
    dado"): do mês de 11 meses atrás ao mês de hoje, andando sozinha. `n` 0 = não é um ano contratual."""
    a, m = hoje.year, hoje.month - 11
    if m < 1:
        a, m = a - 1, m + 12
    prox = date(hoje.year + (hoje.month == 12), hoje.month % 12 + 1, 1)
    return {"n": 0, "ini": date(a, m, 1).isoformat(), "fim": date.fromordinal(prox.toordinal() - 1).isoformat(),
            "atual": True, "rolante": True}


def meses_do_ano(ano: dict) -> list[dict]:
    """Os 12 meses do ano contratual, do mês do início ao 11º seguinte: {id "AAAA-MM", rot "set/25"}."""
    a, m = int(ano["ini"][:4]), int(ano["ini"][5:7])
    out = []
    for _ in range(12):
        out.append({"id": f"{a:04d}-{m:02d}", "rot": f"{_MESES[m - 1]}/{str(a)[2:]}"})
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


def _pct_da_regra(ficha: dict | None, palavras: re.Pattern) -> dict | None:
    for k in (ficha or {}).get("contratos") or []:
        for r in k.get("regras") or []:
            if r.get("categoria") != "Disponibilidade e desempenho" or not palavras.search(str(r.get("nome") or "").lower()):
                continue
            m = _PCT.search(str(r.get("vigente") or r.get("contratual") or ""))
            if m:
                v = float(m.group(1).replace(",", "."))
                if 50 <= v <= 100:
                    return {"pct": v, "origem": f"do contrato: {r.get('nome')}"}
    return None


def metas(contrato: dict, ficha: dict | None) -> dict:
    """{"pr": {pct, origem} | None, "disp": {pct, origem}}. O número dos Dados do contrato (o gestor gravou, com prova)
    vence. Sem ele, a meta de PR é a da BD Performance, por usina e mês (`montar`, `metas_pr`; Levi, 26/11/2026: "As
    metas de PR, você vai entrar na BD Performance"; o PR lido do PDF saiu: numa ficha, outra regra virou um PR de 98%), e
    a garantia de disponibilidade é a do contrato lido ou, sem ela, 99% (`DISP_PADRAO`)."""
    out = {}
    v = contrato.get("meta_pr")
    out["pr"] = {"pct": float(v), "origem": "dos Dados do contrato"} if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    v = contrato.get("meta_disp")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        out["disp"] = {"pct": float(v), "origem": "dos Dados do contrato"}
    else:
        out["disp"] = _pct_da_regra(ficha, re.compile(r"disponibilidade")) or {"pct": DISP_PADRAO, "origem": "padrão da Grid (99%)"}
    return out


def tom_kpi(v, meta) -> str:
    """A régua da sugestão: na meta ou acima, ok; até 2 pontos abaixo, alerta; abaixo disso, critico; sem meta ou sem
    valor, sem cor."""
    if v is None or meta is None:
        return ""
    return "ok" if v >= meta else ("alerta" if v >= meta - FAIXA else "critico")


def _br(v, casas=1) -> str:
    return f"{v:.{casas}f}".replace(".", ",")


def _dm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def _media_pesada(pares) -> float | None:
    """A média de (valor, peso); sem peso (a potência que falta), peso 1."""
    pares = [(v, p if p else 1.0) for v, p in pares if v is not None]
    tot = sum(p for _, p in pares)
    return round(sum(v * p for v, p in pares) / tot, 1) if tot else None


def montar(contrato: dict, ficha: dict | None, ano: dict, usinas: list[dict], pcm: dict, zel: dict, zel_min: dict,
           hoje: date, meses_com_dado: set[str], ligacao: dict | None = None, avisos: list[str] | None = None,
           metas_pr: dict | None = None, rondas: dict | None = None, zel_desde: str | None = None) -> dict:
    """O que a aba lê.

    `usinas` = as do cliente na Visão gerencial: [{uid, usina, mwp, meses {"AAAA-MM": {pr, disp, ...}}, com_expurgo
    {"AAAA-MM": {disp, pr}}}]; `pcm` = {uid: {sigla: {"AAAA-MM": [feitas, total]}}}; `zel` = {uid: {"rocada" | "lavagem":
    [datas ISO]}}; `zel_min` = {uid: {"rocada" | "lavagem": n por ano}}; `meses_com_dado` = os meses que o banco de
    performance tem (fora deles, "sem dado"); `metas_pr` = {uid: {"AAAA-MM": PR previsto em %}} (a BD Performance e a BD
    Thopen); `rondas` = {uid: [{data, sujidade, vegetacao}]} (as leituras das rondas do Usinas 360°); `zel_desde` =
    "AAAA-MM", o 1º mês que o arquivo do PCM traz (antes dele, o mês sem serviço é "sem dado", não "não feita")."""
    metas_pr, rondas = metas_pr or {}, rondas or {}
    ms = meses_do_ano(ano)
    mes_hoje = hoje.isoformat()[:7]
    mt = metas(contrato, ficha)
    meta_pr, meta_disp = (mt["pr"] or {}).get("pct"), (mt["disp"] or {}).get("pct")
    ano_fechado = hoje.isoformat() > ano["fim"]

    def cel_prev(par, mid):
        if not par:
            return {"txt": "—", "tom": "", "dica": "sem plano no mês"}
        f, t = par
        if f >= t:
            tom = "ok"
        elif mid < mes_hoje:
            tom = "critico"
        else:
            tom = ""
        return {"txt": f"{f}/{t}", "tom": tom, "dica": f"{f} tarefas feitas de {t} planejadas (o PCM conta tarefa a tarefa); clique para ver as OS"}

    out_us, tot_prev, tot_zel = [], {s: {} for s in SIGLAS}, {"rocada": {}, "lavagem": {}}
    tot_zel_alerta = {"rocada": {}, "lavagem": {}}         # usinas sem o serviço, com o PR abaixo e a ronda alta
    pr_mes_contrato, disp_mes_contrato = {m["id"]: [] for m in ms}, {m["id"]: [] for m in ms}
    bruta_mes_contrato = {m["id"]: [] for m in ms}
    meta_mes_contrato = {m["id"]: [] for m in ms}             # a meta de PR do mês pela potência das usinas com PR
    tot_rd = {"veg": {}, "suj": {}}
    fora_pr = fora_disp = 0
    for u in usinas:
        uid, mwp = u.get("uid"), u.get("mwp")
        linhas, fora_u, fora_kpi_u = {}, 0, 0
        for s in SIGLAS:
            dado = (pcm.get(uid) or {}).get(s) or {}
            cels = {m["id"]: cel_prev(dado.get(m["id"]), m["id"]) for m in ms}
            f = sum(dado[m["id"]][0] for m in ms if m["id"] in dado)
            t = sum(dado[m["id"]][1] for m in ms if m["id"] in dado)
            for m in ms:
                if m["id"] in dado:
                    tp = tot_prev[s].setdefault(m["id"], [0, 0])
                    tp[0] += dado[m["id"]][0]
                    tp[1] += dado[m["id"]][1]
            ruim = any(c["tom"] == "critico" for c in cels.values())
            linhas[s] = {"cels": cels, "acum": {"txt": f"{f}/{t}" if t else "—",
                                                "tom": "ok" if t and f >= t else ("critico" if ruim else ""),
                                                "dica": f"{f} feitas de {t} planejadas no ano contratual" if t else "sem plano no ano"}}
            fora_u += sum(1 for c in cels.values() if c["tom"] == "critico")
        leit = sorted((r for r in rondas.get(uid) or [] if ano["ini"] <= str(r.get("data") or "")[:10] <= ano["fim"]),
                      key=lambda r: r["data"])
        niv = {"veg": {}, "suj": {}}                         # o pior nível do mês, para a célula do serviço
        for chave, campo, nome in (("veg", "vegetacao", "vegetação"), ("suj", "sujidade", "sujidade")):
            cels = {}
            for m in ms:
                ns = [(r[campo], r["data"]) for r in leit if r["data"][:7] == m["id"] and r.get(campo) is not None]
                if not ns:
                    cels[m["id"]] = {"txt": "—", "tom": "", "dica": "nenhuma ronda leu a " + nome + " no mês"}
                    continue
                pior = max(ns)
                niv[chave][m["id"]] = pior[0]
                if pior[0] >= 4:
                    tot_rd[chave][m["id"]] = tot_rd[chave].get(m["id"], 0) + 1
                cels[m["id"]] = {"txt": str(pior[0]), "tom": tom_nivel(pior[0]),
                                 "dica": f"{len(ns)} {'leitura' if len(ns) == 1 else 'leituras'} no mês; a pior: {pior[0]} "
                                         f"({NIVEL_TXT.get(pior[0], '')}) em {_dm(pior[1])}"}
            ult = next((r for r in reversed(leit) if r.get(campo) is not None), None)
            linhas[chave] = {"cels": cels, "acum": ({"txt": str(ult[campo]), "tom": tom_nivel(ult[campo]),
                                                     "dica": f"a última leitura: {ult[campo]} ({NIVEL_TXT.get(ult[campo], '')}) em {_dm(ult['data'])}"}
                                                    if ult else {"txt": "—", "tom": "", "dica": "nenhuma leitura na janela (as rondas ficam 90 dias)"})}
        # o PR e a disponibilidade: o mês sem dado no banco diz "sem dado" (nunca 0)
        um, ue = u.get("meses") or {}, u.get("com_expurgo") or {}
        cels_pr, cels_disp, prs, disps, metas_u = {}, {}, [], [], []
        pr_u = {}                                          # {mês: (PR expurgado, meta)}, para a célula do serviço
        for m in ms:
            mid = m["id"]
            if mid > mes_hoje:
                cels_pr[mid] = cels_disp[mid] = {"txt": "", "tom": "", "dica": "ainda não chegou"}
                continue
            if mid not in meses_com_dado:
                sem = {"txt": "s/d", "tom": "", "dica": "sem dado no banco: o PR e a disponibilidade por mês começam em 10/2026"}
                cels_pr[mid] = cels_disp[mid] = sem
                continue
            # o PR expurgado (o `com_expurgo` da Visão gerencial: a rede e a limitação saem da conta, como na
            # disponibilidade); sem ele, o PR do mês
            pr_bruto = (um.get(mid) or {}).get("pr")
            pr_exp = (ue.get(mid) or {}).get("pr")
            pr = pr_exp if pr_exp is not None else pr_bruto
            errado = pr is not None and not (0 < pr <= PR_MAX)
            if errado:
                pr = None
            teve_pr = pr is not None and pr_bruto is not None and round(pr, 2) != round(pr_bruto, 2)
            bruta = (um.get(mid) or {}).get("disp")
            exp = (ue.get(mid) or {}).get("disp")
            disp = exp if exp is not None else bruta
            parcial = " (mês em curso)" if mid == mes_hoje else ""
            meta_u = meta_pr if meta_pr is not None else (metas_pr.get(uid) or {}).get(mid)
            tpr = tom_kpi(pr, meta_u)
            cels_pr[mid] = {"txt": (_br(pr) + ("*" if teve_pr else "")) if pr is not None else "s/d", "tom": tpr,
                            "dica": (f"PR expurgado {_br(pr)}%" + (f" (sem o expurgo {_br(pr_bruto)}%)" if teve_pr else "")
                                     + (f"; meta {_br(meta_u)}%" if meta_u is not None else "; sem meta de PR")
                                     + parcial) if pr is not None else ("leitura errada: o PR publicado passa de 100%" if errado
                                                                else "a Performance não publicou o PR do mês")}
            pr_u[mid] = (pr, meta_u)
            teve = exp is not None and bruta is not None and round(exp, 2) != round(bruta, 2)
            tdi = "info" if teve else tom_kpi(disp, meta_disp)
            cels_disp[mid] = {"txt": (_br(disp) + ("*" if teve else "")) if disp is not None else "s/d", "tom": tdi,
                              "dica": (f"{_br(disp)}% com o expurgo do contrato; sem o expurgo {_br(bruta)}%" if teve else
                                       (f"{_br(disp)}%" + (f"; garantia {_br(meta_disp)}%" if meta_disp is not None else "")))
                              + parcial if disp is not None else "sem disponibilidade publicada no mês"}
            if pr is not None:
                prs.append(pr)
                pr_mes_contrato[mid].append((pr, mwp))
                if meta_u is not None:
                    meta_mes_contrato[mid].append((meta_u, mwp))
                    metas_u.append(meta_u)
                if meta_u is not None and pr < meta_u:
                    fora_pr += 1
                    fora_u += 1
                    fora_kpi_u += 1
            if disp is not None:
                disps.append(disp)
                disp_mes_contrato[mid].append((disp, mwp))
                if bruta is not None:
                    bruta_mes_contrato[mid].append((bruta, mwp))
                if meta_disp is not None and disp < meta_disp:
                    fora_disp += 1
                    fora_u += 1
                    fora_kpi_u += 1
        # a supressão e a lavagem: feita (a data) ou não, sobre o PR expurgado e a ronda do mês
        for chave, rd, nome_rd, nome in (("rocada", "veg", "vegetação", "supressão"), ("lavagem", "suj", "sujidade", "lavagem")):
            datas = sorted(d for d in (zel.get(uid) or {}).get(chave) or [] if ano["ini"] <= d <= ano["fim"])
            cels = {}
            for m in ms:
                mid = m["id"]
                ds = [d for d in datas if d[:7] == mid]
                p, mu = pr_u.get(mid, (None, None))
                nv = niv[rd].get(mid)
                ctx = ([f"PR expurgado {_br(p)}%" + (f" (meta {_br(mu)}%)" if mu is not None else "")] if p is not None else []) + \
                      ([f"{nome_rd} da ronda {nv} ({NIVEL_TXT.get(nv, '')})"] if nv is not None else [])
                ctx_txt = ("; " + "; ".join(ctx)) if ctx else ""
                if ds:
                    tot_zel[chave][mid] = tot_zel[chave].get(mid, 0) + 1
                    cels[mid] = {"txt": _dm(ds[0]) + (f" +{len(ds) - 1}" if len(ds) > 1 else ""), "tom": "ok",
                                 "dica": "feita em " + ", ".join(_dm(d) for d in ds) + ctx_txt}
                elif mid > mes_hoje:
                    cels[mid] = {"txt": "", "tom": "", "dica": "ainda não chegou"}
                elif zel_desde and mid < zel_desde:
                    cels[mid] = {"txt": "s/d", "tom": "", "dica": "antes deste mês o arquivo do PCM não tem as OS do Fracttal: sem dado"}
                else:
                    alerta = p is not None and mu is not None and p < mu and nv is not None and nv >= 4
                    if alerta:
                        tot_zel_alerta[chave][mid] = tot_zel_alerta[chave].get(mid, 0) + 1
                        fora_u += 1
                    cels[mid] = {"txt": "não", "tom": "alerta" if alerta else "",
                                 "dica": (f"sem {nome} no mês" + (" (mês em curso)" if mid == mes_hoje else "") + ctx_txt
                                          + (f": o PR ficou abaixo da meta com a {nome_rd} alta e sem {nome}" if alerta else ""))}
            minimo = (zel_min.get(uid) or {}).get(chave)
            if minimo:
                tom = "ok" if len(datas) >= minimo else ("critico" if ano_fechado else "alerta")
                acum = {"txt": f"{len(datas)}/{minimo}", "tom": tom, "dica": f"{len(datas)} feitas de {minimo} no mínimo do contrato"}
            else:
                acum = {"txt": str(len(datas)) if datas else "—", "tom": "",
                        "dica": "o contrato da zeladoria não traz o mínimo desta usina" if datas else "nenhuma no ano"}
            linhas[chave] = {"cels": cels, "acum": acum}
        acum_pr = round(sum(prs) / len(prs), 1) if prs else None
        acum_disp = round(sum(disps) / len(disps), 1) if disps else None
        meta_ac = meta_pr if meta_pr is not None else (round(sum(metas_u) / len(metas_u), 1) if metas_u else None)
        linhas["pr"] = {"cels": cels_pr, "acum": {"txt": _br(acum_pr) if acum_pr is not None else "s/d",
                                                  "tom": tom_kpi(acum_pr, meta_ac),
                                                  "dica": f"a média dos {len(prs)} meses com PR" + (f"; meta {_br(meta_ac)}%" if meta_ac is not None else "")}}
        linhas["disp"] = {"cels": cels_disp, "acum": {"txt": _br(acum_disp) if acum_disp is not None else "s/d",
                                                      "tom": tom_kpi(acum_disp, meta_disp), "dica": f"a média dos {len(disps)} meses com dado"}}
        out_us.append({"uid": uid, "usina": u.get("usina"), "mwp": mwp, "fora": fora_u, "fora_kpi": fora_kpi_u,
                       "linhas": [dict(id=i, nome=n, grupo=g, **linhas[i]) for i, n, g in LINHAS]})
    out_us.sort(key=lambda x: (-x["fora"], -(x["mwp"] or 0), str(x["usina"]).lower()))

    # o total do contrato: preventivas somadas, serviços como usinas feitas no mês, PR e disponibilidade pela potência
    total = []
    for s in SIGLAS:
        cels = {m["id"]: cel_prev(tot_prev[s].get(m["id"]), m["id"]) for m in ms}
        f, t = sum(v[0] for v in tot_prev[s].values()), sum(v[1] for v in tot_prev[s].values())
        total.append({"id": s, "nome": s, "grupo": "manut", "cels": cels,
                      "acum": {"txt": f"{f}/{t}" if t else "—", "tom": "ok" if t and f >= t else "", "dica": f"{f} feitas de {t} planejadas"}})
    for chave, nome in (("rocada", "Supressão vegetal"), ("lavagem", "Lavagem de módulos")):
        cels = {}
        for m in ms:
            f, a = tot_zel[chave].get(m["id"], 0), tot_zel_alerta[chave].get(m["id"], 0)
            nada = "—" if m["id"] <= mes_hoje else ""
            dica = (f"{f} {'usina feita' if f == 1 else 'usinas feitas'} no mês" if f else "nenhuma usina feita no mês") + \
                (f"; {a} sem o serviço com o PR expurgado abaixo da meta e a ronda em 4 ou 5 (clique para ver)" if a else "")
            cels[m["id"]] = {"txt": str(f) if f else nada, "tom": "alerta" if a else ("ok" if f else ""), "dica": dica}
        feitas = sum(len([d for d in (zel.get(u.get("uid")) or {}).get(chave) or [] if ano["ini"] <= d <= ano["fim"]]) for u in usinas)
        minimo = sum((zel_min.get(u.get("uid")) or {}).get(chave) or 0 for u in usinas)
        total.append({"id": chave, "nome": nome, "grupo": "manut", "sub": "usinas feitas", "cels": cels,
                      "acum": {"txt": f"{feitas}/{minimo}" if minimo else (str(feitas) if feitas else "—"),
                               "tom": ("ok" if feitas >= minimo else ("critico" if ano_fechado else "alerta")) if minimo else "",
                               "dica": f"{feitas} feitas; mínimo somado das usinas com contrato de zeladoria: {minimo}"}})
    for chave, nome in (("veg", "Vegetação na ronda"), ("suj", "Sujidade na ronda")):
        cels = {m["id"]: ({"txt": str(tot_rd[chave][m["id"]]), "tom": "alerta", "dica": "usinas com nível 4 ou 5 no mês"}
                          if tot_rd[chave].get(m["id"]) else {"txt": "—", "tom": "", "dica": "nenhuma usina com nível 4 ou 5"}) for m in ms}
        agora = sum(1 for u in out_us if next(l for l in u["linhas"] if l["id"] == chave)["acum"]["tom"] in ("alerta", "critico"))
        pos = 4 if chave == "veg" else 6
        total.insert(pos, {"id": chave, "nome": nome, "grupo": "manut", "sub": "usinas em alerta", "cels": cels,
                           "acum": {"txt": str(agora) if agora else "—", "tom": "alerta" if agora else "",
                                    "dica": "usinas com a última leitura em 4 ou 5"}})
    meta_c = {mid: (meta_pr if meta_pr is not None else _media_pesada(v)) for mid, v in meta_mes_contrato.items()}
    pr_c = {mid: _media_pesada(v) for mid, v in pr_mes_contrato.items()}
    disp_c = {mid: _media_pesada(v) for mid, v in disp_mes_contrato.items()}
    metas_ok = [v for v in meta_c.values() if v is not None]
    meta_pr_ac = meta_pr if meta_pr is not None else (round(sum(metas_ok) / len(metas_ok), 1) if metas_ok else None)
    for chave, nome, vals, meta in (("pr", "PR expurgado", pr_c, None), ("disp", "Disponibilidade expurgada", disp_c, meta_disp)):
        cels = {}
        for m in ms:
            v = vals.get(m["id"])
            mm = meta_c.get(m["id"]) if chave == "pr" else meta
            if m["id"] > mes_hoje:
                cels[m["id"]] = {"txt": "", "tom": "", "dica": ""}
            elif m["id"] not in meses_com_dado:
                cels[m["id"]] = {"txt": "s/d", "tom": "", "dica": "sem dado no banco antes de 10/2026"}
            else:
                cels[m["id"]] = {"txt": _br(v) if v is not None else "s/d", "tom": tom_kpi(v, mm),
                                 "dica": "ponderado pela potência das usinas" + (f"; meta {_br(mm)}%" if mm is not None else "")}
        ac = _media_pesada([(v, 1.0) for v in vals.values() if v is not None])
        ma = meta_pr_ac if chave == "pr" else meta
        total.append({"id": chave, "nome": nome, "grupo": "kpi", "sub": "% ponderado", "cels": cels,
                      "acum": {"txt": _br(ac) if ac is not None else "s/d", "tom": tom_kpi(ac, ma), "dica": "a média dos meses com dado"}})
    tp = {s: [sum(v[0] for v in tot_prev[s].values()), sum(v[1] for v in tot_prev[s].values())] for s in SIGLAS}
    pr_ac = next((l["acum"]["txt"] for l in total if l["id"] == "pr"), "s/d")
    disp_ac = next((l["acum"]["txt"] for l in total if l["id"] == "disp"), "s/d")
    # os quatro números do alto (o mockup da sugestão: o PR e a disponibilidade do contrato com o mês a mês em miniatura,
    # as preventivas e os serviços do ano, e o que ficou fora da meta com a usina que mais pesa)
    def barras(chave):
        linha = next(l for l in total if l["id"] == chave)
        def tom(m):
            c = linha["cels"][m["id"]]
            if c["tom"]:
                return c["tom"]
            if m["id"] > mes_hoje:
                return "futuro"
            return "vazio" if c["txt"] in ("", "s/d") else "neutro"      # o mês com número e sem meta: cinza claro
        return [{"rot": m["rot"], "txt": linha["cels"][m["id"]]["txt"], "tom": tom(m)} for m in ms]
    abaixo = {"pr": [m["rot"] for m in ms if (v := pr_c.get(m["id"])) is not None and meta_c.get(m["id"]) is not None and v < meta_c[m["id"]]],
              "disp": [m["rot"] for m in ms if (v := disp_c.get(m["id"])) is not None and meta_disp is not None and v < meta_disp]}
    if mt["pr"] is None and meta_pr_ac is not None:
        mt = {**mt, "pr": {"pct": meta_pr_ac, "origem": "da BD Performance, por usina e mês (a média da janela)"}}
    sem_exp = _media_pesada([(v, 1.0) for v in (_media_pesada(x) for x in bruta_mes_contrato.values()) if v is not None])

    def tom_feitas(f, t):
        return "" if not t else ("ok" if f >= t else ("critico" if ano_fechado else "alerta"))
    zel_ac = {k: next(l["acum"] for l in total if l["id"] == k) for k in ("rocada", "lavagem")}
    pior = max(out_us, key=lambda x: x["fora_kpi"], default=None)
    pior = pior if pior and pior["fora_kpi"] else None
    return {"ok": True, "ano": ano, "meses": ms, "mes_hoje": mes_hoje, "ano_fechado": ano_fechado,
            "metas": mt, "usinas": out_us, "total": total,
            "resumo": {"pr": pr_ac, "pr_tom": next(l["acum"]["tom"] for l in total if l["id"] == "pr"),
                       "disp": disp_ac, "disp_tom": next(l["acum"]["tom"] for l in total if l["id"] == "disp"),
                       "disp_sem_expurgo": _br(sem_exp) if sem_exp is not None else None,
                       "pr_barras": barras("pr"), "disp_barras": barras("disp"),
                       "pr_abaixo": abaixo["pr"], "disp_abaixo": abaixo["disp"],
                       "prev": tp, "prev_tom": {s: tom_feitas(*tp[s]) for s in SIGLAS},
                       "rocada": zel_ac["rocada"]["txt"], "rocada_tom": zel_ac["rocada"]["tom"],
                       "lavagem": zel_ac["lavagem"]["txt"], "lavagem_tom": zel_ac["lavagem"]["tom"],
                       "fora_pr": fora_pr, "fora_disp": fora_disp, "usinas_n": len(out_us),
                       "pior": {"usina": pior["usina"], "fora": pior["fora_kpi"]} if pior else None},
            "ligacao": ligacao or {}, "avisos": list(avisos or [])}
