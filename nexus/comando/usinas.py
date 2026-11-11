"""Comando > Usinas (11/11/2026, Levi: "Em comando quero a mesma visão de Início > Usinas do mockup"): todas as usinas
mobilizadas numa tabela, com o estado de agora e o que cada tela dona diz dela. Funções puras: a view lê as fontes e
passa o dado já lido, e o teste prova a conta.

De onde vem cada coluna (a fonte da tela dona; nada se inventa):
- usina, cliente e cluster: a linha da Visão do responsável (`campo.responsaveis.visao_responsaveis`, a cópia de 5 min);
  código, MWp (a potência contratual, a única preenchida nas 138) e tipologia ("SOLO TRACKER" = Tracker): o cadastro;
- Agora: o COS > OS em aberto (11/11/2026, Levi: "Coluna Agora pelo COS"; até ali, o tempo real): a pior OS que o COS
  tem pendente na usina, na situação do registro da Ronda COS (detectada, em campo, tratativa remota...), com o tipo e
  há quanto tempo; sem OS pendente, "Sem OS aberta";
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

# os grupos do estado de agora (a faixa, a legenda e o filtro): (rótulo, tom, ordem). O tom de cada OS é o do registro
# da Ronda COS (`cos.os_abertas.ESTADOS_DO_REGISTRO`: detectada e confirmada críticas; em campo, em execução, bloqueada e
# sem registro em alerta; tratativa remota em info; normalizada e encerrada ok) e a OS em alerta (o alerta de 1 h da
# Ronda COS) é crítica. Atenção junta o alerta e o info; Normal é a usina sem OS pendente do COS (ou só com a
# normalizada, que falta fechar). "Sem leitura": o Andamento não respondeu (nunca "Normal" no escuro)
ESTADOS = {"critico": ("Crítico", "critico", 0), "atencao": ("Atenção", "alerta", 1),
           "sem_leitura": ("Sem leitura", "neutro", 2), "normal": ("Normal", "ok", 3)}
LEGENDA = (("normal", "Normal"), ("atencao", "Atenção"), ("critico", "Crítico"), ("sem_leitura", "Sem leitura do COS"))
_TOM_ORDEM = {"critico": 0, "alerta": 1, "info": 2, "ok": 3, "neutro": 4}


def _norm(s) -> str:
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def os_do_cos_por_usina(itens: list[dict] | None, usina_de) -> dict[int, list[dict]] | None:
    """{usina_id: as OS do COS > OS em aberto da usina} (`itens` = `cos.os_abertas._item` de cada OS do Andamento;
    `usina_de(nome, codigo)` = o usina_id do cadastro). None = o Andamento não respondeu."""
    if itens is None:
        return None
    out: dict[int, list[dict]] = {}
    for i in itens:
        uid = usina_de(i.get("usina"), i.get("usina_codigo"))
        if uid:
            out.setdefault(uid, []).append(i)
    return out


def _tom_da_os(i: dict) -> str:
    return "critico" if i.get("em_alerta") else (i.get("registro") or ("", "neutro"))[1]


def agora_pelo_cos(os_da_usina: list[dict] | None) -> dict:
    """O estado de agora da usina pelas OS do COS (`None` = sem leitura do Andamento). A que manda é a pendente de tom
    mais grave e, no empate, a mais antiga; as feitas que só falta finalizar não mudam o estado (o Panorama as separa:
    dívida administrativa, não operação parada) e vão no detalhe."""
    if os_da_usina is None:
        rot, tom, ordem = ESTADOS["sem_leitura"]
        return {"estado": "sem_leitura", "estado_rot": rot, "estado_tom": tom, "ordem": ordem, "horas": 0, "os_cos": [],
                "detalhe": ""}
    pend = [i for i in os_da_usina if i.get("situacao") == "pendente"]
    feitas = len(os_da_usina) - len(pend)
    pend.sort(key=lambda i: (_TOM_ORDEM.get(_tom_da_os(i), 9), -(i.get("horas") or 0)))
    falta = f"{feitas} {'feita' if feitas == 1 else 'feitas'}, falta finalizar" if feitas else ""
    if not pend:
        rot, tom, ordem = ESTADOS["normal"]
        return {"estado": "normal", "estado_rot": "Sem OS aberta", "estado_tom": tom, "ordem": ordem, "horas": 0,
                "os_cos": list(os_da_usina), "detalhe": falta}
    pior = pend[0]
    tom = _tom_da_os(pior)
    grupo = "critico" if tom == "critico" else ("normal" if tom == "ok" else "atencao")
    rot = "Em alerta" if pior.get("em_alerta") else (pior.get("registro") or ("Aberta",))[0]
    partes = [pior.get("tipo") or "OS", f"OS {pior.get('folio')}", f"há {pior.get('aberta_ha')}"]
    if len(pend) > 1:
        partes.append(f"+{len(pend) - 1} {'pendente' if len(pend) == 2 else 'pendentes'}")
    if falta:
        partes.append(falta)
    return {"estado": grupo, "estado_rot": rot, "estado_tom": tom if tom != "neutro" else ESTADOS[grupo][1],
            "ordem": ESTADOS[grupo][2], "horas": pior.get("horas") or 0,
            "os_cos": pend + [i for i in os_da_usina if i not in pend], "detalhe": " · ".join(partes)}


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
           sem_luvas: set | None, com_os: bool = True) -> list[dict]:
    """Uma linha por usina da Visão do responsável. `cadastro`: {usina_id: a ficha}; `cos`: {usina_id: as OS do COS > OS
    em aberto} (`os_do_cos_por_usina`; None = o Andamento não respondeu: todas "Sem leitura"); `insights`: {usina_id: n} (None = o motor ainda calcula);
    `sem_luvas`: os usina_id sem luvas na última ronda (None = a leitura das rondas falhou); `com_os`: as OS do Fracttal
    chegaram ao banco (sem elas, a coluna diz "sem leitura", nunca 0)."""
    out = []
    for u in linhas_visao or []:
        uid = u.get("usina_id")
        ficha = cadastro.get(uid) or {}
        meta = u.get("meta") or {}
        man = u.get("manutencao") or {}
        ext = u.get("extintores")
        ag = agora_pelo_cos(None if cos is None else cos.get(uid, []))
        conf = []
        if ext and ext.get("vencidos"):
            n = ext["vencidos"]
            conf.append((f"{n} {'extintor vencido' if n == 1 else 'extintores vencidos'}", "critico"))
        if sem_luvas is not None and uid in sem_luvas:
            conf.append(("sem luvas", "critico"))
        sem_fonte = ext is None and sem_luvas is None
        out.append({
            "usina_id": uid, "usina": u.get("usina") or "", "codigo": str(ficha.get("codigo") or "").strip(),
            "cliente": u.get("cliente") or "", "cluster": u.get("cluster") or "",
            "mwp": mwp(ficha.get("potencia_contratual")), "tipologia": tipologia(ficha.get("tipologia")),
            **ag,
            "atingimento": meta.get("atingimento"), "pr": meta.get("pr"), "pr_meta": meta.get("pr_meta"),
            "os_abertas": man.get("os_abertas", 0) if com_os else None,
            "os_atrasadas": man.get("atrasadas_os", 0) if com_os else None,
            "insights": None if insights is None else insights.get(uid, 0),
            "conformidade": conf, "conformidade_ok": not conf and not sem_fonte, "conformidade_sem_fonte": sem_fonte})
        x = out[-1]
        # o que a busca da página olha (`filtro-local.js` compara sem acento e sem caixa)
        x["busca"] = _norm(" ".join([x["usina"], x["codigo"], x["cliente"], x["cluster"], x["tipologia"]]))
    out.sort(key=lambda x: (x["ordem"], -x["horas"], x["atingimento"] if x["atingimento"] is not None else 1e9,
                            x["usina"]))
    return out


def resumo(linhas: list[dict]) -> dict:
    """As contas da faixa e da legenda: quantas usinas em cada estado da legenda."""
    n = {k: 0 for k, _ in LEGENDA}
    for x in linhas:
        n[x["estado"]] += 1
    return {"por_estado": n, "total": len(linhas), "clientes": sorted({x["cliente"] for x in linhas if x["cliente"]})}
