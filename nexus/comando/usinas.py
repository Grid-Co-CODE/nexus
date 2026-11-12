"""Comando > Usinas (11/11/2026, Levi: "Em comando quero a mesma visão de Início > Usinas do mockup"): todas as usinas
mobilizadas numa tabela, com o estado de agora e o que cada tela dona diz dela. Funções puras: a view lê as fontes e
passa o dado já lido, e o teste prova a conta.

De onde vem cada coluna (a fonte da tela dona; nada se inventa):
- usina, cliente e cluster: a linha da Visão do responsável (`campo.responsaveis.visao_responsaveis`, a cópia de 5 min);
  código, MWp (a potência contratual, a única preenchida nas 138) e tipologia ("SOLO TRACKER" = Tracker): o cadastro;
- Agora: o COS (11/11/2026, Levi: "Coluna Agora pelo COS"; até ali, o tempo real): as ocorrências abertas na Ronda COS,
  pela fotografia de cada cliente do Andamento (a do COS > Ronda padronizada, que traz o tipo da tarefa e da falha), na
  régua do Levi (`classificar`); sem ocorrência aberta, "Sem ocorrência";
- Atingimento e PR / meta: a meta do mês da Visão (o Gerencial);
- OS abertas e atrasadas: o bloco Manutenção da Visão (as tarefas das OS do Fracttal no banco);
- Insights: os do Nexus Insights que não foram concluídos, pelo nome da usina;
- Conformidade: os extintores vencidos (o PPCI, a conta da Segurança que a Visão já traz) e a usina sem as luvas
  isolantes na última ronda (o EPC, `hseq.epi.luvas`).

O Score de saúde do mockup ficou FORA (Levi, 11/11/2026: "Fora por agora"): o Nexus não tem essa nota e criar uma é regra
nova. A ordem é o estado de agora (o mais grave primeiro), dentro dele a OS do COS mais antiga e depois o atingimento (o
pior primeiro).
"""
import unicodedata

# os grupos do estado de agora (a faixa, a legenda e o filtro): (rótulo, tom, ordem). A régua é do Levi (11/11/2026):
# "quando tiver religamento com OS aberta em campo tem que estar como crítico", "atenção vai ser inversor desligado",
# "falha de comunicação é sem comunicação e etc". O "etc" seguiu a mesma ideia: a usina, a cabine, o SKID ou o QGBT
# desligados, a proteção que atuou e a falta de energia da concessionária param a usina (crítico, o "Crítico / sem
# produção" do mockup); o que sobra (outra falha aberta) é atenção. "Sem leitura": o Andamento não trouxe a usina (nunca
# "Normal" no escuro)
# "Sem comunicação" é roxo (12/11/2026, Levi: "Quando for falha de comunicação [...] na cor precisa estar roxo"): o
# `semcom` do semáforo da casa; até ali saía cinza, igual ao "Sem leitura". O Mapa de equipe e o vídeo wall pegam o tom daqui
ESTADOS = {"critico": ("Crítico", "critico", 0), "atencao": ("Atenção", "alerta", 1),
           "sem_com": ("Sem comunicação", "semcom", 2), "sem_leitura": ("Sem leitura", "neutro", 3),
           "normal": ("Normal", "ok", 4)}
LEGENDA = (("normal", "Normal"), ("atencao", "Atenção"), ("critico", "Crítico"), ("sem_com", "Sem comunicação"),
           ("sem_leitura", "Sem leitura do COS"))
# o tipo da falha que para a usina (a Ronda COS escreve "Desligamento de usina", "Atuação de proteção"...; o
# `problema` "rede" é o grupo "Rede concessionária" do placar dela)
_PARA_A_USINA = ("usina", "cabine", "skid", "qgbt", "protecao", "concessionaria", "rede")
# o motivo numa linha embaixo do status (12/11/2026, Levi: "os status generalizem entre (Normal, Atenção, Crítico, sem
# comunicação e sem leitura. Aí abaixo em apenas uma linha diga o motivo: "Desligamento", "inversor em falha", "Tracker
# parado", "String sem corrente""): (trecho do tipo da falha, sem acento e sem caixa, o motivo). A 1ª que bate vale
_MOTIVOS = (("comunica", "Falha de comunicação"), ("inversor", "Inversor em falha"), ("tracker", "Tracker parado"),
            ("string", "String sem corrente"), ("cabine", "Cabine desligada"), ("skid", "SKID desligado"),
            ("qgbt", "QGBT desligado"), ("protecao", "Proteção atuou"), ("concessionaria", "Falta de energia da rede"),
            ("usina", "Desligamento"), ("deslig", "Desligamento"))
# os filtros da tela (12/11/2026, Levi: "filtros também de responsável da UFV, filtros de meta, o que está abaixo, os que
# não tem conformidade"). A meta na régua da Visão gerencial (`campo.responsaveis.META_NA_META` e `META_ATENCAO`)
META_FAIXAS = {"na_meta": "Na meta (97% ou mais)", "atencao": "Atenção (90% a 97%)", "abaixo": "Abaixo (menos de 90%)",
               "sem_meta": "Sem meta no mês"}
CONFORMIDADES = {"pendencia": "Com pendência", "em_dia": "Em dia", "sem_leitura": "Sem leitura"}
FILTROS = ("cliente", "estado", "responsavel", "meta", "conformidade")


def _norm(s) -> str:
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def classificar(oc: dict) -> tuple[str, str]:
    """(grupo, rótulo) de UMA ocorrência aberta da Ronda COS, na régua do Levi. Olha o tipo da tarefa, o tipo da falha e o
    grupo do problema que a Ronda COS manda; não lê o texto livre."""
    tarefa, falha, prob = _norm(oc.get("tipo_tarefa")), _norm(oc.get("tipo_falha")), _norm(oc.get("problema"))
    com_os = str(oc.get("os") or "").isdigit()          # a ocorrência ainda sem OS vem como "R-<registro>"
    if tarefa.startswith("religamento") and "remoto" not in tarefa and com_os:
        return "critico", "Religamento em campo"
    if "comunica" in falha or prob == "com":
        return "sem_com", "Sem comunicação"
    if "inversor" in falha or prob == "inv":
        return "atencao", "Inversor desligado"
    if any(p in falha for p in _PARA_A_USINA) or prob == "rede":
        return "critico", str(oc.get("tipo_falha") or "Usina desligada")
    return "atencao", str(oc.get("tipo_falha") or oc.get("tipo_tarefa") or "Ocorrência aberta")


def motivo(oc: dict) -> str:
    """O motivo de UMA ocorrência em poucas palavras, pelo tipo da falha que a Ronda COS manda (sem ele, pelo tipo da
    tarefa: o religamento é desligamento). O que não está na lista vai com o próprio nome da falha."""
    falha, prob = _norm(oc.get("tipo_falha")), _norm(oc.get("problema"))
    for trecho, txt in _MOTIVOS:
        if trecho in falha:
            return txt
    if prob == "com":
        return "Falha de comunicação"
    if prob == "inv":
        return "Inversor em falha"
    if prob == "rede" or _norm(oc.get("tipo_tarefa")).startswith("religamento"):
        return "Desligamento"
    return str(oc.get("tipo_falha") or oc.get("tipo_tarefa") or "Ocorrência aberta")


def ligador_do_cos(b):
    """O `usina_de(nome, codigo)` da fotografia da Ronda COS, para o `cos_por_usina`: o nome do Fracttal pelo de-para e,
    depois, o código pela regra da casa (`dados.equipamento.usina_do_codigo`, a mesma das normalizações do COS): o
    código cheio igual ao do cadastro ou a terminação que é de UMA usina, e nunca o código com o prefixo de outro
    cliente. O caso que criou a regra (12/11/2026, a análise das usinas Sem leitura): o `E1EN-PCN100`, a Poconé da E1
    (sem código no cadastro), caía na Poconé 1 da Thopen (`THPN-PCN100`) pela terminação — o ligador geral
    (`Ligador.usina`) não olha o prefixo —, e as ocorrências de uma apareciam na outra. `b` = `visao._Base()`."""
    from ..dados import equipamento as EQ
    idx = EQ.IndiceUsinas(b.usinas)

    def usina_de(nome, codigo):
        uid = b.lig.usina_do_fracttal(nome or "")
        if uid:
            return uid
        return EQ.usina_do_codigo(codigo, idx)[0] if codigo else None
    return usina_de


def cos_por_usina(leituras: list | None, usina_de) -> dict | None:
    """A fotografia da Ronda COS de cada cliente do Andamento (`cos.andamento.ler`, a mesma do COS > Ronda padronizada)
    por usina do cadastro: {"ocs": {usina_id: as ocorrências abertas}, "lidas": os usina_id que alguma fotografia
    trouxe}. A usina que não veio em nenhuma (o cliente cujo Andamento não respondeu) fica de fora de "lidas" e a tela
    a mostra "Sem leitura". `usina_de(nome, codigo)` = o usina_id. None = nenhum cliente respondeu."""
    boas = [lt for lt in leituras or [] if getattr(lt, "dados", None)]
    if not boas:
        return None
    ocs: dict[int, list[dict]] = {}
    lidas: set[int] = set()
    for lt in boas:
        for u in lt.dados.get("usinas") or []:
            uid = usina_de(u.get("nome"), u.get("codigo"))
            if not uid:
                continue
            lidas.add(uid)
            for o in u.get("ocorrencias") or []:
                # `usina_cod`: o código curto da usina no Andamento ("APR100"), o do cartão do vídeo wall
                ocs.setdefault(uid, []).append(dict(o, cliente_cos=lt.cliente, usina_cod=str(u.get("cod") or "")))
    return {"ocs": ocs, "lidas": lidas}


def _ha(oc: dict, agora) -> tuple[int, str]:
    """(horas, "há 3 h" / "há 5 dias") desde a abertura da ocorrência."""
    from ..cos import andamento as AND
    from ..cos import os_abertas as OA
    horas, _dias = OA.idade(AND.instante(oc.get("abertura")), agora)
    return horas, OA.aberta_ha(horas)


def agora_pelo_cos(ocs: list[dict] | None, agora=None) -> dict:
    """O estado de agora da usina pelas ocorrências abertas na Ronda COS (`None` = sem leitura). Manda a do grupo mais
    grave e, no empate, a mais antiga; a célula diz a OS, há quanto tempo, a etapa e quantas mais."""
    from ..cos import andamento as AND
    agora = agora or AND.agora()
    if ocs is None:
        rot, tom, ordem = ESTADOS["sem_leitura"]
        return {"estado": "sem_leitura", "estado_rot": rot, "estado_tom": tom, "ordem": ordem, "horas": 0,
                "os_cos": [], "detalhe": ""}
    itens = []
    for o in ocs:
        grupo, rot = classificar(o)
        horas, ha = _ha(o, agora)
        os_ = str(o.get("os") or "")
        itens.append(dict(o, grupo=grupo, rotulo=rot, motivo=motivo(o), tom=ESTADOS[grupo][1], horas=horas, ha=ha,
                          os_rotulo=f"OS {os_}" if os_.isdigit() else "ainda sem OS"))
    if not itens:
        rot, tom, ordem = ESTADOS["normal"]
        return {"estado": "normal", "estado_rot": rot, "estado_tom": tom, "ordem": ordem, "horas": 0,
                "os_cos": [], "detalhe": ""}
    itens.sort(key=lambda i: (ESTADOS[i["grupo"]][2], -i["horas"]))
    pior = itens[0]
    # a célula diz só o grupo e o motivo (12/11/2026, Levi: "Em agora pode tirar as informações das OSs, isso fica para
    # quando a pessoa clicar na UFV"); a OS, a idade e a etapa ficam no prontuário
    return {"estado": pior["grupo"], "estado_rot": ESTADOS[pior["grupo"]][0], "estado_tom": pior["tom"],
            "ordem": ESTADOS[pior["grupo"]][2], "horas": pior["horas"], "os_cos": itens, "detalhe": pior["motivo"]}


def tipologia(v) -> str:
    """"SOLO TRACKER" -> "Tracker", "SOLO FIXA" -> "Fixa"; "N/I" e o vazio, "" (a tela escreve —)."""
    t = _norm(v)
    return "Tracker" if "tracker" in t else ("Fixa" if "fixa" in t else "")


def mwp(v) -> float | None:
    """A potência do cadastro ("6.898", "3.26") em número; o que não é número, None."""
    try:
        x = float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def insights_por_usina(insights: list[dict] | None, est: dict, nome_para_uid: dict) -> dict[int, int] | None:
    """{usina_id: os insights que não foram concluídos}. O insight guarda o nome da usina (o do cadastro, ou o código
    quando o cadastro não deu nome): liga pelo nome sem acento e sem caixa. None = o motor ainda não calculou."""
    if insights is None:
        return None
    out: dict[int, int] = {}
    for i in insights:
        if ((est.get(i.get("id")) or {}).get("evento")) == "concluiu":
            continue
        uid = nome_para_uid.get(_norm(i.get("usina")))
        if uid:
            out[uid] = out.get(uid, 0) + 1
    return out


def montar(linhas_visao: list[dict], cadastro: dict, cos: dict | None, insights: dict | None,
           sem_luvas: set | None, com_os: bool = True, agora=None) -> list[dict]:
    """Uma linha por usina da Visão do responsável. `cadastro`: {usina_id: a ficha}; `cos`: as ocorrências da Ronda COS
    por usina (`cos_por_usina`; None = o Andamento não respondeu: todas "Sem leitura"); `insights`: {usina_id: n} (None = o motor ainda calcula);
    `sem_luvas`: os usina_id sem luvas na última ronda (None = a leitura das rondas falhou); `com_os`: as OS do Fracttal
    chegaram ao banco (sem elas, a coluna diz "sem leitura", nunca 0)."""
    out = []
    for u in linhas_visao or []:
        uid = u.get("usina_id")
        ficha = cadastro.get(uid) or {}
        meta = u.get("meta") or {}
        man = u.get("manutencao") or {}
        ext = u.get("extintores")
        ag = agora_pelo_cos(None if cos is None or uid not in cos["lidas"] else cos["ocs"].get(uid, []), agora)
        conf = []
        if ext and ext.get("vencidos"):
            n = ext["vencidos"]
            conf.append((f"{n} {'extintor vencido' if n == 1 else 'extintores vencidos'}", "critico"))
        if sem_luvas is not None and uid in sem_luvas:
            conf.append(("sem luvas", "critico"))
        sem_fonte = ext is None and sem_luvas is None
        ating = meta.get("atingimento")
        codigo = str(ficha.get("codigo") or "").strip()
        out.append({
            "usina_id": uid, "usina": u.get("usina") or "", "codigo": codigo,
            # só o código da UFV, sem o prefixo do cliente (12/11/2026, Levi): "THPN-FRN100" -> "FRN100"
            "codigo_ufv": codigo.split("-", 1)[-1] if "-" in codigo else codigo,
            "responsavel": u.get("responsavel") or "Sem responsável O&M",
            "faixa_meta": faixa_meta(ating),
            "cliente": u.get("cliente") or "", "cluster": u.get("cluster") or "",
            "mwp": mwp(ficha.get("potencia_contratual")), "tipologia": tipologia(ficha.get("tipologia")),
            **ag,
            "atingimento": meta.get("atingimento"), "pr": meta.get("pr"), "pr_meta": meta.get("pr_meta"),
            "os_abertas": man.get("os_abertas", 0) if com_os else None,
            "os_atrasadas": man.get("atrasadas_os", 0) if com_os else None,
            "insights": None if insights is None else insights.get(uid, 0),
            "conformidade": conf, "conformidade_ok": not conf and not sem_fonte, "conformidade_sem_fonte": sem_fonte,
            "conf_chave": "pendencia" if conf else ("sem_leitura" if sem_fonte else "em_dia")})
        x = out[-1]
        # o que a busca da página olha (`filtro-local.js` compara sem acento e sem caixa)
        x["busca"] = _norm(" ".join([x["usina"], x["codigo"], x["cliente"], x["cluster"], x["tipologia"]]))
    out.sort(key=lambda x: (x["ordem"], -x["horas"], x["atingimento"] if x["atingimento"] is not None else 1e9,
                            x["usina"]))
    return out


def faixa_meta(ating) -> str:
    """A faixa do atingimento do mês na régua da Visão gerencial (97% e 90%); sem meta publicada, "sem_meta"."""
    from ..campo.responsaveis import META_ATENCAO, META_NA_META
    if ating is None:
        return "sem_meta"
    return "na_meta" if ating >= META_NA_META else ("atencao" if ating >= META_ATENCAO else "abaixo")


def filtrar(linhas: list[dict], escolhidos: dict) -> list[dict]:
    """As linhas que passam em TODOS os filtros escolhidos ({filtro: [valores]}; lista vazia = sem filtro). Dentro de
    um filtro, qualquer valor marcado serve (como as listas de marcar do Histórico de OS)."""
    campo = {"cliente": "cliente", "estado": "estado", "responsavel": "responsavel", "meta": "faixa_meta",
             "conformidade": "conf_chave"}
    ativos = {k: set(v) for k, v in (escolhidos or {}).items() if k in campo and v}
    return [x for x in linhas if all(x[campo[k]] in v for k, v in ativos.items())]


def resumo(linhas: list[dict]) -> dict:
    """As contas da faixa e da legenda (quantas usinas em cada estado) e as opções dos filtros, de todas as usinas."""
    n = {k: 0 for k, _ in LEGENDA}
    for x in linhas:
        n[x["estado"]] += 1
    return {"por_estado": n, "total": len(linhas), "clientes": sorted({x["cliente"] for x in linhas if x["cliente"]}),
            "responsaveis": sorted({x["responsavel"] for x in linhas}, key=lambda r: (r.startswith("Sem "), _norm(r)))}
