"""A aba Indicadores do contrato (Comando › Contratos, 26/11/2026): o ano contratual mês a mês, usina por usina.

A sugestão de 26/11/2026: "Uma aba Indicadores no contrato [...] uma matriz: meses do ano contratual nas
colunas, usinas nas linhas", com MPM, MPS e MPA feitas sobre as planejadas, a supressão vegetal e a lavagem de módulos com
a data em que foram feitas (contra o mínimo do contrato), o PR e a disponibilidade expurgada contra a meta do contrato; no
alto, os números do contrato inteiro ponderados pela potência. O Levi, no mesmo dia, junto: "ANIVERSÁRIO DE CONTRATO,
RELATÓRIO DE ANIVERSÁRIO DE CONTRATO". Escolhas dele: o ano conta do início da vigência; entram TODAS as usinas do cliente
no cadastro (como a Visão gerencial); o mês sem dado no banco diz "sem dado" (nunca 0); a régua de cor é a da sugestão
(verde na meta, amarelo até 2 pontos abaixo, vermelho abaixo disso). Desde 27/11/2026 o PR e a disponibilidade vão em
duas linhas cada, sem e com o expurgo, e o contrato pondera pela potência ("Pense que a gente está fazendo uma visão
gerencial para o CEO, para os heads").

As fontes chegam prontas (a tela as junta, `torres/comando/contratos_tela.py`), cada uma a que a tela dona já usa:
- o PR e a disponibilidade, bruta e com o expurgo do contrato: o livro `nexus_kpi_usina_mes` (`comando/kpi_mes.py`, a
  conta da Visão gerencial já feita, de hora em hora) e, sem ele, a própria conta (`gerencial.montar`, usina por
  `usina_id`); o banco tem esses meses só desde 10/2026 (`diagnostico_mes.PRIMEIRO_MES`);
- MPM, MPS e MPA: as tarefas do ano do PCM (`pcm.gestao.classificar`: a sigla no nome e o mês da Data Programada; feita =
  "Finalizada"), ligadas à usina pelo nome (`campo.responsaveis.Nomes`);
- a supressão vegetal (roçagem e poda química) e a lavagem (limpeza de módulos): o Radar da Zeladoria (como o Histórico
  de Serviços os junta, `servicos_do_radar`) e as OS finalizadas do Fracttal (`tipo_da_tarefa`, `juntar_servicos`); o
  mínimo do ano, o `zeladoria_contratual` do Radar por UFV (só o "fixo": o "sob demanda" não tem mínimo). O mês com o
  serviço mostra a data; sem ele, "atrasada" quando o prazo do contrato venceu desde a última (Levi, 27/11/2026: "tem que
  ser a data que foi feita [...] E não feita, a depender do prazo do contrato"); sem prazo no contrato, a dica diz a
  última;
- as metas: a garantia de disponibilidade e o PR que o contrato lido escreve (as regras de "Disponibilidade e desempenho"),
  ou o que o gestor gravou nos Dados do contrato, que vence.

Puro: nada de rede nem Flask. A ligação pelo nome é medida (quantas tarefas e serviços casaram com uma usina do cliente)
e a tela mostra: o que não casou não some calado.
"""
from __future__ import annotations

import calendar
import re
from datetime import date

SIGLAS = ("MPM", "MPS", "MPA")
FAIXA = 2.0                                  # pontos abaixo da meta que ainda são amarelo (a régua da sugestão)
# o PR acima de 100% é leitura errada (a régua da Visão gerencial, `gerencial.PR_MAX`): na 1ª prévia, 26/11/2026, uma
# usina da Thopen com PR de mais de 1.000% fez o PR do contrato dar 730,5%
PR_MAX = 100.0
_MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
_PCT = re.compile(r"(\d{2,3}(?:[.,]\d+)?)\s*%")
# a vegetação e a sujidade da ronda saíram em 27/11/2026 (Levi: "Sobre sujidade e vegetação na ronda, não importa isso
# daí não"); o PR e a disponibilidade vão com e sem o expurgo ("Eu tô sentindo falta do PR ponderado, PR expurgado")
LINHAS = (("MPM", "MPM", "manut"), ("MPS", "MPS", "manut"), ("MPA", "MPA", "manut"),
          ("rocada", "Supressão vegetal", "manut"), ("lavagem", "Lavagem de módulos", "manut"),
          ("pr", "PR", "kpi"), ("pr_exp", "PR expurgado", "kpi"),
          ("disp", "Disponibilidade", "kpi"), ("disp_exp", "Disponibilidade expurgada", "kpi"))
# a garantia de disponibilidade onde o contrato não traz o número (Levi, 26/11/2026: "Garantia de disponibilidade. Bota
# 99% para tudo [...] As que faltam, bota 99%")
DISP_PADRAO = 99.0


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


def _mais_meses(d: date, n: int) -> date:
    a, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    return date(a, m, min(d.day, calendar.monthrange(a, m)[1]))


def _fim_do_mes(mid: str) -> date:
    a, m = int(mid[:4]), int(mid[5:7])
    return date(a, m, calendar.monthrange(a, m)[1])


def _dma(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[2:4]}"


def passo_do_contrato(minimo) -> int | None:
    """Os meses entre um serviço e o próximo pelo mínimo do contrato da zeladoria (2 por ano = a cada 6 meses)."""
    try:
        n = int(minimo)
    except (TypeError, ValueError):
        return None
    return max(1, round(12 / n)) if n > 0 else None


def montar(contrato: dict, ficha: dict | None, ano: dict, usinas: list[dict], pcm: dict, zel: dict, zel_min: dict,
           hoje: date, meses_com_dado: set[str], ligacao: dict | None = None, avisos: list[str] | None = None,
           metas_pr: dict | None = None, zel_desde: str | None = None) -> dict:
    """O que a aba lê.

    `usinas` = as do cliente: [{uid, usina, mwp, meses {"AAAA-MM": {pr, disp, ...}}, com_expurgo {"AAAA-MM": {disp, pr}}}]
    (a conta da Visão gerencial, ou o livro `nexus_kpi_usina_mes` no mesmo formato); `pcm` = {uid: {sigla: {"AAAA-MM":
    [feitas, total]}}}; `zel` = {uid: {"rocada" | "lavagem": [datas ISO]}}; `zel_min` = {uid: {"rocada" | "lavagem": n por
    ano}}; `meses_com_dado` = os meses que o banco de performance tem (fora deles, "sem dado"); `metas_pr` = {uid:
    {"AAAA-MM": PR previsto em %}} (a BD Performance e a BD Thopen); `zel_desde` = "AAAA-MM", o 1º mês que o arquivo do
    PCM traz (antes dele, o mês sem serviço é "sem dado")."""
    metas_pr = metas_pr or {}
    ms = meses_do_ano(ano)
    mes_hoje = hoje.isoformat()[:7]
    mt = metas(contrato, ficha)
    meta_pr, meta_disp = (mt["pr"] or {}).get("pct"), (mt["disp"] or {}).get("pct")
    ano_fechado = hoje.isoformat() > ano["fim"]
    # o relógio do prazo da zeladoria conta da última feita (sem nenhuma, do 1º mês do arquivo do PCM) e nunca de antes do
    # início da vigência (a Apolo, que começou em 11/09/2026, saía atrasada em julho)
    try:
        inicio = date.fromisoformat(str(contrato.get("inicio") or "")[:10])
    except ValueError:
        inicio = None

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

    def valido(v):
        return v if v is not None and 0 < v <= PR_MAX else None

    out_us, tot_prev = [], {s: {} for s in SIGLAS}
    tot_zel = {"rocada": {}, "lavagem": {}}
    tot_atras = {"rocada": {}, "lavagem": {}}            # usinas com o serviço atrasado pelo prazo do contrato
    kpis = ("pr", "pr_exp", "disp", "disp_exp")
    kpi_mes = {k: {m["id"]: [] for m in ms} for k in kpis}
    meta_mes_contrato = {m["id"]: [] for m in ms}             # a meta de PR do mês pela potência das usinas com PR
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
        # a supressão e a lavagem: a data em que foi feita (Levi, 27/11/2026: "tem que ser a data que foi feita [...] E não
        # feita, a depender do prazo do contrato"); sem o serviço no mês, "atrasada" quando o prazo do contrato da
        # zeladoria venceu desde a última (o mínimo do ano: 2 por ano = uma a cada 6 meses); sem prazo no contrato, só a
        # data da última na dica
        for chave, nome in (("rocada", "supressão"), ("lavagem", "lavagem")):
            todas = sorted(d for d in (zel.get(uid) or {}).get(chave) or [] if len(str(d)) >= 10)
            datas = [d for d in todas if ano["ini"] <= d <= ano["fim"]]
            minimo = (zel_min.get(uid) or {}).get(chave)
            passo = passo_do_contrato(minimo)
            regra = f"o contrato da zeladoria pede {minimo} por ano (uma a cada {passo} meses)" if passo else ""
            cels = {}
            for m in ms:
                mid = m["id"]
                ds = [d for d in datas if d[:7] == mid]
                if ds:
                    tot_zel[chave][mid] = tot_zel[chave].get(mid, 0) + 1
                    prox = (f"; a próxima vence em {_dma(_mais_meses(date.fromisoformat(ds[-1]), passo).isoformat())}"
                            if passo else "")
                    cels[mid] = {"txt": _dm(ds[0]) + (f" +{len(ds) - 1}" if len(ds) > 1 else ""), "tom": "ok",
                                 "dica": "feita em " + ", ".join(_dma(d) for d in ds) + prox}
                    continue
                if mid > mes_hoje:
                    cels[mid] = {"txt": "", "tom": "", "dica": "ainda não chegou"}
                    continue
                if zel_desde and mid < zel_desde:
                    cels[mid] = {"txt": "s/d", "tom": "", "dica": "antes deste mês o arquivo do PCM não tem as OS do Fracttal: sem dado"}
                    continue
                if inicio and mid < inicio.isoformat()[:7]:
                    cels[mid] = {"txt": "—", "tom": "", "dica": f"sem {nome} no mês; antes do início da vigência ({_dma(inicio.isoformat())})"}
                    continue
                fim = min(_fim_do_mes(mid), hoje)
                ult = next((d for d in reversed(todas) if d <= fim.isoformat()), None)
                ult_txt = f"a última em {_dma(ult)}" if ult else "nenhuma registrada"
                if passo:
                    base = date.fromisoformat(ult[:10]) if ult else (date.fromisoformat(zel_desde + "-01") if zel_desde else None)
                    base = max(base, inicio) if base and inicio else (base or inicio)
                    venc = _mais_meses(base, passo) if base else None
                    if venc and venc < fim:
                        tot_atras[chave][mid] = tot_atras[chave].get(mid, 0) + 1
                        fora_u += 1
                        cels[mid] = {"txt": "atrasada", "tom": "critico",
                                     "dica": f"sem {nome} no mês; {ult_txt}; {regra}: venceu em {_dma(venc.isoformat())}"}
                    else:
                        cels[mid] = {"txt": "—", "tom": "", "dica": f"sem {nome} no mês; {ult_txt}"
                                     + (f"; a próxima vence em {_dma(venc.isoformat())}" if venc else "")}
                else:
                    cels[mid] = {"txt": "—", "tom": "", "dica": f"sem {nome} no mês; {ult_txt}; o contrato da zeladoria "
                                                                 "desta usina não traz o prazo"}
            ult_ano = f"; a última em {_dma(datas[-1])}" if datas else ""
            if minimo:
                tom = "ok" if len(datas) >= int(minimo) else ("critico" if ano_fechado else "alerta")
                acum = {"txt": f"{len(datas)}/{minimo}", "tom": tom, "dica": f"{len(datas)} feitas de {minimo} no mínimo do contrato{ult_ano}"}
            else:
                acum = {"txt": str(len(datas)) if datas else "—", "tom": "",
                        "dica": (f"{len(datas)} feitas; o contrato da zeladoria não traz o mínimo desta usina{ult_ano}"
                                 if datas else "nenhuma na janela")}
            linhas[chave] = {"cels": cels, "acum": acum}
        # o PR e a disponibilidade, com e sem o expurgo do contrato (Levi, 27/11/2026: "Eu tô sentindo falta do PR
        # ponderado, PR expurgado"; "Disponibilidade expurgada também, mesma lógica"): o mês sem dado no banco diz "sem
        # dado" (nunca 0)
        um, ue = u.get("meses") or {}, u.get("com_expurgo") or {}
        cels_k = {k: {} for k in kpis}
        vals_k = {k: [] for k in kpis}
        metas_u = []
        for m in ms:
            mid = m["id"]
            if mid > mes_hoje:
                for k in kpis:
                    cels_k[k][mid] = {"txt": "", "tom": "", "dica": "ainda não chegou"}
                continue
            if mid not in meses_com_dado:
                for k in kpis:
                    cels_k[k][mid] = {"txt": "s/d", "tom": "", "dica": "sem dado no banco: o PR e a disponibilidade por mês começam em 10/2026"}
                continue
            mm, ex = um.get(mid) or {}, ue.get(mid) or {}
            pr_lido = mm.get("pr")
            pr_b = valido(pr_lido)
            pr_e = valido(ex.get("pr")) if ex.get("pr") is not None else pr_b
            disp_b = mm.get("disp")
            disp_e = ex.get("disp") if ex.get("disp") is not None else disp_b
            parcial = " (mês em curso)" if mid == mes_hoje else ""
            meta_u = meta_pr if meta_pr is not None else (metas_pr.get(uid) or {}).get(mid)
            txt_meta = f"; meta {_br(meta_u)}%" if meta_u is not None else "; sem meta de PR"
            errado = pr_lido is not None and pr_b is None
            for k, v, meta, rot in (("pr", pr_b, meta_u, "PR sem o expurgo"), ("pr_exp", pr_e, meta_u, "PR com o expurgo do contrato"),
                                    ("disp", disp_b, meta_disp, "disponibilidade sem o expurgo"),
                                    ("disp_exp", disp_e, meta_disp, "disponibilidade com o expurgo do contrato")):
                if v is None:
                    falta = ("leitura errada: o PR publicado passa de 100%" if errado and k.startswith("pr") else
                             "a Performance não publicou o PR do mês" if k.startswith("pr") else "sem disponibilidade publicada no mês")
                    cels_k[k][mid] = {"txt": "s/d", "tom": "", "dica": falta}
                    continue
                if k.startswith("pr"):
                    extra = txt_meta
                else:
                    extra = f"; garantia {_br(meta)}%" if meta is not None else ""
                if k == "pr_exp" and pr_b is not None and round(v, 2) != round(pr_b, 2):
                    extra += f"; sem o expurgo {_br(pr_b)}%"
                if k == "disp_exp" and disp_b is not None and round(v, 2) != round(disp_b, 2):
                    extra += f"; sem o expurgo {_br(disp_b)}%"
                cels_k[k][mid] = {"txt": _br(v), "tom": tom_kpi(v, meta), "dica": f"{rot}: {_br(v)}%{extra}{parcial}"}
                vals_k[k].append(v)
                kpi_mes[k][mid].append((v, mwp))
            if pr_b is not None and meta_u is not None:
                meta_mes_contrato[mid].append((meta_u, mwp))
                metas_u.append(meta_u)
            # fora da meta: o número do contrato é o expurgado
            if pr_e is not None and meta_u is not None and pr_e < meta_u:
                fora_pr += 1
                fora_u += 1
                fora_kpi_u += 1
            if disp_e is not None and meta_disp is not None and disp_e < meta_disp:
                fora_disp += 1
                fora_u += 1
                fora_kpi_u += 1
        meta_ac = meta_pr if meta_pr is not None else (round(sum(metas_u) / len(metas_u), 1) if metas_u else None)
        for k in kpis:
            vs = vals_k[k]
            ac = round(sum(vs) / len(vs), 1) if vs else None
            mm_ac = meta_ac if k.startswith("pr") else meta_disp
            linhas[k] = {"cels": cels_k[k], "acum": {"txt": _br(ac) if ac is not None else "s/d", "tom": tom_kpi(ac, mm_ac),
                                                     "dica": f"a média dos {len(vs)} meses com dado"
                                                             + (f"; meta {_br(mm_ac)}%" if mm_ac is not None else "")}}
        out_us.append({"uid": uid, "usina": u.get("usina"), "mwp": mwp, "fora": fora_u, "fora_kpi": fora_kpi_u,
                       "linhas": [dict(id=i, nome=n, grupo=g, **linhas[i]) for i, n, g in LINHAS]})
    out_us.sort(key=lambda x: (-x["fora"], -(x["mwp"] or 0), str(x["usina"]).lower()))

    # o total do contrato: preventivas somadas, serviços como usinas feitas no mês (e as atrasadas), PR e disponibilidade
    # pela potência
    total = []
    for s in SIGLAS:
        cels = {m["id"]: cel_prev(tot_prev[s].get(m["id"]), m["id"]) for m in ms}
        f, t = sum(v[0] for v in tot_prev[s].values()), sum(v[1] for v in tot_prev[s].values())
        total.append({"id": s, "nome": s, "grupo": "manut", "cels": cels,
                      "acum": {"txt": f"{f}/{t}" if t else "—", "tom": "ok" if t and f >= t else "", "dica": f"{f} feitas de {t} planejadas"}})
    for chave, nome in (("rocada", "Supressão vegetal"), ("lavagem", "Lavagem de módulos")):
        cels = {}
        for m in ms:
            f, a = tot_zel[chave].get(m["id"], 0), tot_atras[chave].get(m["id"], 0)
            if m["id"] > mes_hoje:
                cels[m["id"]] = {"txt": "", "tom": "", "dica": ""}
                continue
            feitas = f"{f} {'usina feita' if f == 1 else 'usinas feitas'} no mês" if f else "nenhuma usina feita no mês"
            if a:
                cels[m["id"]] = {"txt": f"{a} atras.", "tom": "critico",
                                 "dica": f"{a} {'usina' if a == 1 else 'usinas'} com o serviço atrasado pelo prazo do contrato; {feitas} (clique para ver)"}
            else:
                cels[m["id"]] = {"txt": str(f) if f else "—", "tom": "ok" if f else "", "dica": feitas}
        feitas = sum(len([d for d in (zel.get(u.get("uid")) or {}).get(chave) or [] if ano["ini"] <= d <= ano["fim"]]) for u in usinas)
        minimo = sum(int((zel_min.get(u.get("uid")) or {}).get(chave) or 0) for u in usinas)
        total.append({"id": chave, "nome": nome, "grupo": "manut", "sub": "usinas feitas", "cels": cels,
                      "acum": {"txt": f"{feitas}/{minimo}" if minimo else (str(feitas) if feitas else "—"),
                               "tom": ("ok" if feitas >= minimo else ("critico" if ano_fechado else "alerta")) if minimo else "",
                               "dica": f"{feitas} feitas; mínimo somado das usinas com contrato de zeladoria: {minimo}"}})
    meta_c = {mid: (meta_pr if meta_pr is not None else _media_pesada(v)) for mid, v in meta_mes_contrato.items()}
    metas_ok = [v for v in meta_c.values() if v is not None]
    meta_pr_ac = meta_pr if meta_pr is not None else (round(sum(metas_ok) / len(metas_ok), 1) if metas_ok else None)
    pond = {k: {mid: _media_pesada(v) for mid, v in kpi_mes[k].items()} for k in kpis}
    for k, nome in (("pr", "PR ponderado"), ("pr_exp", "PR expurgado"), ("disp", "Disponibilidade"),
                    ("disp_exp", "Disponibilidade expurgada")):
        cels = {}
        for m in ms:
            v = pond[k].get(m["id"])
            mm = meta_c.get(m["id"]) if k.startswith("pr") else meta_disp
            if m["id"] > mes_hoje:
                cels[m["id"]] = {"txt": "", "tom": "", "dica": ""}
            elif m["id"] not in meses_com_dado:
                cels[m["id"]] = {"txt": "s/d", "tom": "", "dica": "sem dado no banco antes de 10/2026"}
            else:
                cels[m["id"]] = {"txt": _br(v) if v is not None else "s/d", "tom": tom_kpi(v, mm),
                                 "dica": ("com o expurgo do contrato; " if k.endswith("_exp") else "sem o expurgo; ")
                                         + "ponderado pela potência das usinas" + (f"; meta {_br(mm)}%" if mm is not None else "")}
        ac = _media_pesada([(v, 1.0) for v in pond[k].values() if v is not None])
        ma = meta_pr_ac if k.startswith("pr") else meta_disp
        total.append({"id": k, "nome": nome, "grupo": "kpi", "sub": "% ponderado", "cels": cels,
                      "acum": {"txt": _br(ac) if ac is not None else "s/d", "tom": tom_kpi(ac, ma), "dica": "a média dos meses com dado"}})
    tp = {s: [sum(v[0] for v in tot_prev[s].values()), sum(v[1] for v in tot_prev[s].values())] for s in SIGLAS}
    ac = {k: next(l["acum"] for l in total if l["id"] == k) for k in kpis + ("rocada", "lavagem")}

    # os quatro números do alto (o mockup da sugestão): o PR e a disponibilidade EXPURGADOS do contrato, com o sem expurgo
    # ao lado e o mês a mês em miniatura; as preventivas e os serviços do ano; o que ficou fora da meta
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
    abaixo = {"pr": [m["rot"] for m in ms if (v := pond["pr_exp"].get(m["id"])) is not None and meta_c.get(m["id"]) is not None and v < meta_c[m["id"]]],
              "disp": [m["rot"] for m in ms if (v := pond["disp_exp"].get(m["id"])) is not None and meta_disp is not None and v < meta_disp]}
    if mt["pr"] is None and meta_pr_ac is not None:
        mt = {**mt, "pr": {"pct": meta_pr_ac, "origem": "da BD Performance, por usina e mês (a média da janela)"}}

    def tom_feitas(f, t):
        return "" if not t else ("ok" if f >= t else ("critico" if ano_fechado else "alerta"))
    pior = max(out_us, key=lambda x: x["fora_kpi"], default=None)
    pior = pior if pior and pior["fora_kpi"] else None
    sem = {k: (ac[k]["txt"] if ac[k]["txt"] != "s/d" else None) for k in ("pr", "disp")}
    return {"ok": True, "ano": ano, "meses": ms, "mes_hoje": mes_hoje, "ano_fechado": ano_fechado,
            "metas": mt, "usinas": out_us, "total": total,
            "resumo": {"pr": ac["pr_exp"]["txt"], "pr_tom": ac["pr_exp"]["tom"], "pr_sem_expurgo": sem["pr"],
                       "disp": ac["disp_exp"]["txt"], "disp_tom": ac["disp_exp"]["tom"], "disp_sem_expurgo": sem["disp"],
                       "pr_barras": barras("pr_exp"), "disp_barras": barras("disp_exp"),
                       "pr_abaixo": abaixo["pr"], "disp_abaixo": abaixo["disp"],
                       "prev": tp, "prev_tom": {s: tom_feitas(*tp[s]) for s in SIGLAS},
                       "rocada": ac["rocada"]["txt"], "rocada_tom": ac["rocada"]["tom"],
                       "lavagem": ac["lavagem"]["txt"], "lavagem_tom": ac["lavagem"]["tom"],
                       "fora_pr": fora_pr, "fora_disp": fora_disp, "usinas_n": len(out_us),
                       "pior": {"usina": pior["usina"], "fora": pior["fora_kpi"]} if pior else None},
            "ligacao": ligacao or {}, "avisos": list(avisos or [])}
