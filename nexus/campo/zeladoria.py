"""A Zeladoria do Campo · App: vegetação e sujidade dos módulos semana a semana, por cliente (Levi, 26/10/2026, com o
modelo "Rondas Sujidade e Vegetação": "Quero algo nesses padrões para a parte de zeladoria da seção campo app do nexus.
deixe no estilo do Nexus porém nesse padrão! a evolução por usina deve ser por cliente!").

Sem fonte nova: o que a tela mostra já está no Nexus, e nada aqui escreve.
- **A leitura** (vegetação e sujidade dos módulos de 1 a 5, o técnico comparando com as fotos de referência do App; o App
  alerta acima de 3) é a da ronda, pela MESMA regra da aba Sujidade e vegetação das Rondas (`visao.sujidade_vegetacao`):
  o texto da OS de ronda no Fracttal (`ronda_checklist`), a carga única das rondas sem OS e a ronda avulsa; ronda sem OS
  e sem checklist não é leitura; a validação por foto do dia vale no lugar das rondas daquele dia na usina.
- **A zeladoria feita e a programada** são as tarefas do tipo Zeladoria do Fracttal no banco (`nexus_os ·
  fato_tarefa_os`: as abertas e as finalizadas dos últimos 90 dias). O fato guarda a tarefa como chave (sha1 do texto,
  `fatos.tarefa_chave`); as três do plano são conhecidas pelo texto (medido em 26/10/2026, 76 tarefas: 36 de limpeza de
  módulos, 33 de supressão vegetal e 7 de poda química, uma linha por OS).

Os parâmetros foram decididos pelo Levi em 26/10/2026, com os números do dado real na mão (a regra dele de 16/10: "me
pergunte antes de botar qualquer filtro ou parâmetro"): o limiar é o do App (acima de 3, o mesmo das Rondas e da Visão do
responsável), a semana com mais de uma leitura vale a última (`REGRA_DA_SEMANA`), o prazo é o do modelo (`PRAZO_DIAS`)
e os filtros são os do modelo, o cliente, a região de campo e o gestor de contrato.
"""
from datetime import date, timedelta

from ..dados.fatos import tarefa_chave
from . import ronda_checklist, visao

D = visao.D
SEMANAS = 8                              # a evolução das últimas 8 semanas, a do modelo
ALERTA_ACIMA = ronda_checklist.ALERTA_ACIMA   # nível 4 e 5 pedem ação: o `alerta_acima` do App
# a semana com mais de uma leitura na usina (medido em 26/10/2026: 206 usina×semana em 9 semanas; a última abaixo da
# maior em 27 na sujidade e 28 na vegetação). "ultima" = o retrato depois da última ronda, como a aba Sujidade e
# vegetação e a Visão do responsável; "pior" = a maior da semana. Decisão do Levi (26/10/2026): a última.
REGRA_DA_SEMANA = "ultima"
# o prazo de cada nível acima do limiar, contado da leitura: os do modelo, nível 4 em até 7 dias e nível 5 imediato
# (decisão do Levi, 26/10/2026; a outra opção era sem prazo). Nível fora daqui sai sem prazo
PRAZO_DIAS = {5: 0, 4: 7}
# a leitura mais velha que isso fica marcada na tabela: a régua de "ronda pendente" das Rondas (7 dias sem ronda)
DIAS_LEITURA_VELHA = visao.DIAS_SEM_RONDA_ALERTA
# as semanas que o filtro oferece: a corrente e as anteriores cuja janela de 8 semanas ainda tem leitura (o checklist
# das rondas é guardado por 90 dias)
SEMANAS_NO_FILTRO = max(1, ronda_checklist.DIAS_PARA_TRAS // 7 - SEMANAS + 1)

CAMPOS = (("vegetacao", "Vegetação"), ("sujidade", "Sujidade"))
# as tarefas de zeladoria do plano (o texto da tarefa no Fracttal), o que cada uma resolve e o nome na tela
TAREFAS_DE_ZELADORIA = (
    ("Acompanhamento - Limpeza de Módulos (Termografia se aplicável)", "limpeza", "Limpeza de módulos", "sujidade"),
    ("Acompanhamento - Supressão Vegetal", "supressao", "Supressão vegetal", "vegetacao"),
    ("Acompanhamento - Poda Química", "poda", "Poda química", "vegetacao"))
_DA_CHAVE = {tarefa_chave(t): (k, nome, campo) for t, k, nome, campo in TAREFAS_DE_ZELADORIA}
OUTRA = ("outra", "Outra tarefa de zeladoria", None)
NOME_DO_TIPO = {k: nome for _, k, nome, _ in TAREFAS_DE_ZELADORIA} | {OUTRA[0]: OUTRA[1]}
# a ação que a recomendação pede e as tarefas que a atendem
ACAO = {"vegetacao": ("Supressão vegetal", {"supressao", "poda"}), "sujidade": ("Limpeza de módulos", {"limpeza"})}
_ABERTA = {"aberta", "execucao"}
_FEITA = {"feita", "verificacao"}


# ── semanas (as do PCM: segunda a domingo, "W43") ────────────────────────────────────────────────────────────────────
def semana_de(dia) -> str:
    d = dia if isinstance(dia, date) else date.fromisoformat(str(dia)[:10])
    ano, sem, _ = d.isocalendar()
    return f"{ano}-W{sem:02d}"


def segunda(sem: str) -> date:
    ano, s = str(sem).split("-W")
    return date.fromisocalendar(int(ano), int(s), 1)


def semanas_ate(sem: str, n: int = SEMANAS) -> list[str]:
    """As `n` semanas que terminam em `sem`, da mais antiga para ela."""
    seg = segunda(sem)
    return [semana_de(seg - timedelta(weeks=i)) for i in range(n - 1, -1, -1)]


def semanas_do_filtro(hoje: date) -> list[str]:
    """A corrente primeiro, depois as anteriores que o filtro oferece."""
    return [semana_de(hoje - timedelta(weeks=i)) for i in range(SEMANAS_NO_FILTRO)]


def rotulo(sem: str) -> str:
    """"W43 · 19 a 25/10" (ou "W44 · 26/10 a 01/11" quando vira o mês)."""
    seg = segunda(sem)
    dom = seg + timedelta(days=6)
    ini = f"{seg:%d}" if seg.month == dom.month else f"{seg:%d/%m}"
    return f"W{sem[-2:]} · {ini} a {dom:%d/%m}"


def semana_valida(pedida, hoje: date) -> str:
    oferecidas = semanas_do_filtro(hoje)
    return pedida if pedida in oferecidas else oferecidas[0]


# ── leituras ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _leitura(r: dict, resp: dict, **extra) -> dict:
    return {"data": r["data"], "fim": r.get("fim"), "tecnico": r.get("tecnico") or "", "os": r.get("os"),
            "tipo": r.get("tipo") or "", "avulsa": bool(r.get("avulsa")), "validada": False, "revisa": [],
            "sujidade": resp.get("sujidade"), "vegetacao": resp.get("vegetacao"), "vala": resp.get("vala") or "",
            "sombreamento": resp.get("sombreamento") or "", "dejeto": resp.get("dejeto") or "",
            "sensores_sujos": list(resp.get("sensores_sujos") or []), **extra}


def leituras(todas, respostas: dict, validacoes, uids) -> dict[int, list[dict]]:
    """{usina_id: as leituras de vegetação e sujidade, da mais antiga para a mais recente}, pela regra da aba Sujidade
    e vegetação: ronda com OS (o texto da OS no Fracttal) ou com o checklist do fato (a carga única, a avulsa); sem
    nenhum dos dois níveis não é leitura; a validação por foto do dia é a leitura da usina naquele dia e as rondas do
    mesmo dia saem (foram revisadas)."""
    uids = set(uids)
    do_dia = {k: v for k, v in visao._validacao_do_dia(validacoes).items() if k[0] in uids}
    out, revisadas = {}, {}
    for r in todas:
        uid = r.get("usina_id")
        if uid not in uids or not r.get("data") or not (r.get("os") or r.get("checklist")):
            continue
        resp = visao.resposta_da_ronda(r, respostas)
        if not resp or (resp.get("sujidade") is None and resp.get("vegetacao") is None):
            continue
        if (uid, r["data"]) in do_dia:
            revisadas.setdefault((uid, r["data"]), []).append(r)
            continue
        out.setdefault(uid, []).append(_leitura(r, resp))
    for (uid, dia), v in do_dia.items():
        rev = revisadas.get((uid, dia), [])
        out.setdefault(uid, []).append(_leitura(
            {**v, "os": next((x["os"] for x in rev if x.get("os")), None), "fim": None, "tipo": ""}, v, validada=True,
            revisa=[{"tecnico": x.get("tecnico") or "", "os": x.get("os")} for x in rev]))
    for lst in out.values():
        # no mesmo dia, a validação por foto fica por último: é o valor que vale para a usina
        lst.sort(key=lambda x: (x["data"], "~" if x["validada"] else (x["fim"] or "")))
    return out


def valor_da_semana(lst, campo: str, regra: str | None = None):
    """O nível da semana: a última leitura que tem o campo (`REGRA_DA_SEMANA = "ultima"`) ou a maior (`"pior"`)."""
    vals = [x[campo] for x in lst if x.get(campo) is not None]
    if not vals:
        return None
    return max(vals) if (regra or REGRA_DA_SEMANA) == "pior" else vals[-1]


# ── zeladoria do Fracttal ────────────────────────────────────────────────────────────────────────────────────────────
def _dia_id(v) -> str:
    i = D._id(v)
    return f"{i // 10000:04d}-{i // 100 % 100:02d}-{i % 100:02d}" if i else ""


def zeladoria_por_usina(tarefas, hoje: date) -> dict[int, list[dict]]:
    """{usina_id: as OS de zeladoria, a mais recente primeiro}. Situação: "feita" (OS finalizada), "verificacao" (o
    técnico terminou, a OS espera a aprovação), "execucao" (tarefa em progresso ou pausada) e "aberta" (programada, ainda
    não começou; `atrasada` quando a data programada já passou)."""
    out = {}
    for t in tarefas or ():
        if D._txt(t.get("tipo_tarefa")) != "zeladoria":
            continue
        uid, os_ = D._id(t.get("usina_id")), D._id(t.get("os"))
        if not uid or not os_:
            continue
        tipo, nome, campo = _DA_CHAVE.get(D._txt(t.get("tarefa_chave")), OUTRA)
        st, estado = D._txt(t.get("status_os")), D._txt(t.get("estado_tarefa"))
        fim, prog = _dia_id(t.get("data_id_fim")), _dia_id(t.get("data_id_programada"))
        if st == "finalizada" or (estado == "finalizada" and st != "em_verificacao"):
            sit = "feita"
        elif st == "em_verificacao":
            sit = "verificacao"
        elif estado in ("em_progresso", "pausada"):
            sit = "execucao"
        else:
            sit = "aberta"
        out.setdefault(uid, []).append({
            "os": os_, "wid": D._id(t.get("fracttal_os_id")), "tipo": tipo, "nome": nome, "campo": campo,
            "situacao": sit, "fim": fim if sit in _FEITA else "", "programada": prog,
            "atrasada": sit in _ABERTA and bool(prog) and prog < hoje.isoformat()})
    for lst in out.values():
        lst.sort(key=lambda z: (z["fim"] or z["programada"] or ""), reverse=True)
    return out


def ultima_feita(zel: list[dict], tipos) -> dict | None:
    return max((z for z in zel if z["tipo"] in tipos and z["situacao"] in _FEITA and z["fim"]),
               key=lambda z: z["fim"], default=None)


def recomendacoes(leitura: dict | None, zel: list[dict], hoje: date, tem_os: bool = True) -> list[dict]:
    """Uma por campo acima do limiar na última leitura: a ação (supressão vegetal, limpeza de módulos), o prazo e se o
    Fracttal já tem a zeladoria: "feita" (terminada depois da leitura), "aberta" (OS de zeladoria do tipo, programada ou
    em execução) ou "sem_os". A feita ANTES da leitura não conta: a leitura é posterior a ela. Sem as OS do Fracttal no
    banco (`tem_os` falso), "sem_dado": não dá para dizer que falta OS."""
    if not leitura:
        return []
    out = []
    for campo, nome_campo in CAMPOS:
        n = leitura.get(campo)
        if n is None or n <= ALERTA_ACIMA:
            continue
        acao, tipos = ACAO[campo]
        feita = max((z for z in zel if z["tipo"] in tipos and z["situacao"] in _FEITA and z["fim"]
                     and z["fim"] >= leitura["data"]), key=lambda z: z["fim"], default=None)
        aberta = min((z for z in zel if z["tipo"] in tipos and z["situacao"] in _ABERTA),
                     key=lambda z: z["programada"] or "9999", default=None)
        status = "feita" if feita else ("aberta" if aberta else ("sem_os" if tem_os else "sem_dado"))
        dias = PRAZO_DIAS.get(n)
        vence = date.fromisoformat(leitura["data"]) + timedelta(days=dias) if dias is not None else None
        atraso = (hoje - vence).days if vence and status != "feita" and vence < hoje else 0
        out.append({"campo": campo, "nome_campo": nome_campo, "nivel": n, "acao": acao, "status": status,
                    "z": feita or aberta, "prazo_dias": dias, "vence": vence.isoformat() if vence else "",
                    "data": leitura["data"], "tecnico": leitura.get("tecnico") or "", "vencida": atraso > 0,
                    "atraso_dias": atraso})
    return out


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def montar(todas, cobertura, respostas: dict, validacoes, tarefas, hoje: date, semana: str | None = None) -> dict:
    """Por usina mobilizada (a base das Rondas): a evolução das 8 semanas que terminam na semana escolhida (o nível de
    cada semana, `valor_da_semana`), a última leitura até o fim da semana escolhida (hoje, na corrente) e a anterior a
    ela (a seta), a criticidade (`visao.criticidade`, a ordem da aba Sujidade e vegetação), a zeladoria do Fracttal e as
    recomendações. Os filtros e o resumo são da rota (`resumo`, `por_cliente`)."""
    semana = semana_valida(semana, hoje)
    janela = semanas_ate(semana)
    ate = min(segunda(semana) + timedelta(days=6), hoje).isoformat()
    lei = leituras(todas, respostas, validacoes, {c["usina_id"] for c in cobertura})
    zel = zeladoria_por_usina(tarefas, hoje)
    tem_os = bool(tarefas)          # o fato vazio (ainda não publicado) não é "nenhuma OS de zeladoria"
    usinas = []
    for c in cobertura:
        uid = c["usina_id"]
        lst = [x for x in lei.get(uid, []) if x["data"] <= ate]
        por_sem = {}
        for x in lst:
            por_sem.setdefault(semana_de(x["data"]), []).append(x)
        celulas = {s: {"vegetacao": valor_da_semana(por_sem.get(s, []), "vegetacao"),
                       "sujidade": valor_da_semana(por_sem.get(s, []), "sujidade"),
                       "leituras": por_sem.get(s, [])} for s in janela}
        ult = lst[-1] if lst else None
        z = zel.get(uid, [])
        u = {**c, "celulas": celulas, "leitura": ult, "anterior": lst[-2] if len(lst) > 1 else None,
             "na_semana": bool(por_sem.get(semana)),
             "dias": (date.fromisoformat(ate) - date.fromisoformat(ult["data"])).days if ult else None,
             "zel": z, "ultima_limpeza": ultima_feita(z, {"limpeza"}),
             "ultima_supressao": ultima_feita(z, {"supressao", "poda"}),
             "recs": recomendacoes(ult, z, hoje, tem_os)}
        u["pontos"], u["status"] = visao.criticidade(ult) if ult else (0, [])
        u["velha"] = u["dias"] is not None and u["dias"] >= DIAS_LEITURA_VELHA
        usinas.append(u)
    corrente = semana_de(hoje)
    return {"semana": semana, "corrente": corrente, "ate": ate, "janela": janela, "usinas": usinas, "tem_os": tem_os,
            "semanas": [{"id": s, "curto": f"W{s[-2:]}", "inicio": segunda(s).isoformat(), "rotulo": rotulo(s),
                         "corrente": s == corrente, "escolhida": s == semana} for s in janela],
            "opcoes_semana": [(s, rotulo(s) + (" · em andamento" if s == corrente else ""))
                              for s in semanas_do_filtro(hoje)]}


def acima(n) -> bool:
    return n is not None and n > ALERTA_ACIMA


def situacao(u: dict, qual: str) -> bool:
    """O filtro Situação: acima do limiar (em qualquer um, só na vegetação, só na sujidade), recomendação sem OS de
    zeladoria, sem leitura na semana escolhida, sem alerta (a última leitura com os dois até o limiar)."""
    lei = u["leitura"] or {}
    return {"": True,
            "atencao": acima(lei.get("vegetacao")) or acima(lei.get("sujidade")),
            "vegetacao": acima(lei.get("vegetacao")),
            "sujidade": acima(lei.get("sujidade")),
            "sem_os": any(r["status"] == "sem_os" for r in u["recs"]),
            "sem_leitura": not u["na_semana"],
            "sem_alerta": bool(lei) and not acima(lei.get("vegetacao")) and not acima(lei.get("sujidade"))}.get(qual, True)


SITUACOES = (("", "todas as situações"), ("atencao", "acima de 3 (vegetação ou sujidade)"),
             ("vegetacao", "vegetação acima de 3"), ("sujidade", "sujidade acima de 3"),
             ("sem_os", "recomendação sem OS de zeladoria"), ("sem_leitura", "sem leitura na semana"),
             ("sem_alerta", "sem alerta"))


def resumo(usinas) -> dict:
    """Os números de cima, sobre as usinas dos filtros (sem o da situação: é o que os números contam)."""
    lidas = [u["leitura"] for u in usinas if u["leitura"]]

    def media(campo):
        v = [x[campo] for x in lidas if x.get(campo) is not None]
        return round(sum(v) / len(v), 1) if v else None
    recs = [r for u in usinas for r in u["recs"]]
    return {"usinas": len(usinas), "na_semana": sum(1 for u in usinas if u["na_semana"]),
            "com_leitura": len(lidas),
            **{f"{c}_acima": sum(1 for x in lidas if acima(x.get(c))) for c, _ in CAMPOS},
            **{f"{c}_5": sum(1 for x in lidas if x.get(c) == 5) for c, _ in CAMPOS},
            **{f"{c}_media": media(c) for c, _ in CAMPOS},
            "recs": len(recs), "sem_os": sum(1 for r in recs if r["status"] == "sem_os"),
            "sem_dado": sum(1 for r in recs if r["status"] == "sem_dado"),
            "abertas": sum(1 for r in recs if r["status"] == "aberta"),
            "feitas": sum(1 for r in recs if r["status"] == "feita"),
            "vencidas": sum(1 for r in recs if r["vencida"] and r["status"] == "sem_os")}


def _ordem_do_nome(nome) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode().lower()


def por_cliente(usinas, semana: str, janela, campo: str) -> list[dict]:
    """A evolução agrupada por cliente (Levi: "a evolução por usina deve ser por cliente!"): os clientes em ordem
    alfabética e, em cada um, as usinas com o nível mais alto na última leitura (até a semana escolhida) primeiro; sem
    leitura, por último; depois pelo nome. Pela última leitura, e não pela semana escolhida: na segunda-feira a semana
    corrente quase não tem ronda, e a ordem virava a alfabética. A linha do cliente diz, em cada semana, quantas usinas
    ficaram acima do limiar e quantas tiveram leitura."""
    grupos = {}
    for u in usinas:
        grupos.setdefault(u.get("cliente") or "Sem cliente", []).append(u)
    out = []
    for cli in sorted(grupos, key=_ordem_do_nome):
        us = sorted(grupos[cli], key=lambda u: _ordem_do_nome(u["usina"]))
        us.sort(key=lambda u: -((u["leitura"] or {}).get(campo) or 0))
        out.append({"cliente": cli, "usinas": us,
                    "semanas": {s: {"acima": sum(1 for u in us if acima(u["celulas"][s][campo])),
                                    "lidas": sum(1 for u in us if u["celulas"][s][campo] is not None)}
                                for s in janela}})
    return out


def fila(usinas) -> list[dict]:
    """As recomendações que pedem ação (sem OS ou com a OS aberta), o nível mais alto primeiro; no mesmo nível, sem OS
    antes de aberta, e a leitura mais antiga antes (esperando há mais tempo)."""
    itens = [{**r, "u": u} for u in usinas for r in u["recs"] if r["status"] != "feita"]
    itens.sort(key=lambda r: r["data"])
    itens.sort(key=lambda r: (-r["nivel"], r["status"] != "sem_os"))
    return itens


# ── a visão no banco, para o dashboard do cliente (26/10/2026) ───────────────────────────────────────────────────────
# Levi, 26/10/2026, depois de aprovar a tela: "agora faz a mesma tela no dashboard do cliente". O 5080 não lê o checklist
# das rondas (o texto da OS no Fracttal, que só o Nexus lê e guarda); decisão do Levi (pelo chat do Dashboard Thopen): o
# Nexus PUBLICA a visão pronta no banco e o 5080 só mostra (`zeladoria_banco.py` grava). 1 linha = usina × semana com
# leitura, das 12 semanas até a corrente (as 8 da evolução até a mais velha que o filtro de semana oferece). A leitura
# da semana é a mesma da célula da evolução (`valor_da_semana`), e a recomendação é a da tela feita sobre ESSA leitura:
# a situação diz se a zeladoria do tipo foi feita depois dela, está programada ou falta programar. Para o cliente: nada
# de nome nem de texto livre (regra 8: a API do banco tem leitura aberta), e a situação em palavras dele.
SEMANAS_NO_BANCO = SEMANAS + SEMANAS_NO_FILTRO - 1
CAB_BANCO = ("semana", "data_id_semana", "usina_id", "vegetacao_nivel", "sujidade_nivel", "vala", "data_id_leitura",
             "os", "leituras_qtd", "recomendacao",
             "situacao_vegetacao", "data_id_prazo_vegetacao", "data_id_situacao_vegetacao", "os_zeladoria_vegetacao",
             "situacao_sujidade", "data_id_prazo_sujidade", "data_id_situacao_sujidade", "os_zeladoria_sujidade",
             "data_id_ultima_supressao", "data_id_ultima_limpeza")
# a situação da recomendação no banco (o 5080 escreve "a programar", "programada para 28/10", "feita em 23/10")
SITUACAO_NO_BANCO = {"sem_os": "a_programar", "aberta": "programada", "feita": "feita", "sem_dado": "sem_dado"}
RECOMENDACAO_NO_BANCO = {"vegetacao": "supressao_vegetal", "sujidade": "limpeza_modulos"}


def _data_id(iso) -> int | None:
    s = str(iso or "")[:10]
    return int(s.replace("-", "")) if len(s) == 10 else None


def _vala_do_dominio(v):
    """A vala com a palavra do App ("Limpa", "Parcial", "Obstruída", "Não se aplica"), ou vazio: outra palavra (o
    "Suja" do formulário de 07/10 da avulsa) vai vazia e conta (`dominios.vala_fora`), nunca o texto como veio."""
    from ..dados import dominios as DOM
    n = DOM.vala(v)
    if n is not None:
        return DOM.VALA_ROTULO[n]
    return "Não se aplica" if DOM.norm(v) == DOM.VALA_NAO_SE_APLICA else None


def visao_do_banco(todas, cobertura, respostas: dict, validacoes, tarefas, hoje: date) -> tuple[list[list], dict]:
    """As linhas da `zeladoria_semana` (`CAB_BANCO`, ordenadas por usina e semana) e o relatório (só contagens)."""
    from ..dados import dominios as DOM
    janela = semanas_ate(semana_de(hoje), SEMANAS_NO_BANCO)
    lei = leituras(todas, respostas, validacoes, {c["usina_id"] for c in cobertura})
    zel = zeladoria_por_usina(tarefas, hoje)
    tem_os = bool(tarefas)
    linhas, rel = [], {"usinas": 0, "linhas": 0, "vala_fora": 0, "recomendacoes": 0, "sem_dado": 0}
    for uid in sorted(lei):
        por_sem = {}
        for x in lei[uid]:
            s = semana_de(x["data"])
            if s in janela:
                por_sem.setdefault(s, []).append(x)
        if not por_sem:
            continue
        rel["usinas"] += 1
        z = zel.get(uid, [])
        for s in sorted(por_sem):
            lst = por_sem[s]
            ult = lst[-1]
            veg, suj = valor_da_semana(lst, "vegetacao"), valor_da_semana(lst, "sujidade")
            recs = {r["campo"]: r for r in recomendacoes({"data": ult["data"], "vegetacao": veg, "sujidade": suj},
                                                          z, hoje, tem_os)}
            fim_sem = min(segunda(s) + timedelta(days=6), hoje).isoformat()
            ate_a_semana = [x for x in z if x["fim"] and x["fim"] <= fim_sem]
            sup, limp = ultima_feita(ate_a_semana, {"supressao", "poda"}), ultima_feita(ate_a_semana, {"limpeza"})
            rel["vala_fora"] += DOM.vala_fora(ult.get("vala"))
            rel["recomendacoes"] += len(recs)
            rel["sem_dado"] += sum(1 for r in recs.values() if r["status"] == "sem_dado")

            def campo(c):
                r = recs.get(c)
                if not r:
                    return [None, None, None, None]
                zz = r["z"] or {}
                quando = zz.get("fim") if r["status"] == "feita" else (zz.get("programada") if r["status"] == "aberta"
                                                                        else None)
                return [SITUACAO_NO_BANCO[r["status"]], _data_id(r["vence"]), _data_id(quando), zz.get("os")]
            linhas.append([s, _data_id(segunda(s).isoformat()), uid, veg, suj, _vala_do_dominio(ult.get("vala")),
                           _data_id(ult["data"]), next((D._id(x["os"]) for x in reversed(lst) if x.get("os")), None),
                           len(lst), ";".join(RECOMENDACAO_NO_BANCO[c] for c, _ in CAMPOS if c in recs) or None,
                           *campo("vegetacao"), *campo("sujidade"),
                           _data_id(sup["fim"]) if sup else None, _data_id(limp["fim"]) if limp else None])
    rel["linhas"] = len(linhas)
    return linhas, rel
