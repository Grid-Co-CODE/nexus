"""Comando > Usinas (11/11/2026, Levi: "Em comando quero a mesma visão de Início > Usinas do mockup"): todas as usinas
mobilizadas numa tabela, com o estado de agora e o que cada tela dona diz dela. Funções puras: a view lê as fontes e
passa o dado já lido, e o teste prova a conta.

De onde vem cada coluna (a fonte da tela dona; nada se inventa):
- usina, cliente e cluster: a linha da Visão do responsável (`campo.responsaveis.visao_responsaveis`, a cópia de 5 min);
  código, MWp (a potência contratual, a única preenchida nas 138) e tipologia ("SOLO TRACKER" = Tracker): o cadastro;
- Agora: a linha do tempo real (a mesma ponte da Visão do cliente), nos estados do mockup;
- Atingimento e PR / meta: a meta do mês da Visão (o Gerencial);
- OS abertas e atrasadas: o bloco Manutenção da Visão (as tarefas das OS do Fracttal no banco);
- Insights: os do Nexus Insights que não foram concluídos, pelo nome da usina;
- Conformidade: os extintores vencidos (o PPCI, a conta da Segurança que a Visão já traz) e a usina sem as luvas
  isolantes na última ronda (o EPC, `hseq.epi.luvas`).

O Score de saúde do mockup ficou FORA (Levi, 11/11/2026: "Fora por agora"): o Nexus não tem essa nota e criar uma é regra
nova. A ordem é o estado de agora (o mais grave primeiro) e, dentro dele, o atingimento (o pior primeiro).
"""
import unicodedata

# os estados do mockup: (rótulo, tom, ordem). "Sem leitura" é a usina que o tempo real não trouxe; "Sem sol", a que
# está ok mas sem irradiância (fora do horário): nenhum dos dois é um problema da usina
ESTADOS = {"sem_producao": ("Sem produção", "critico", 0), "critico": ("Crítico", "critico", 1),
           "sem_comm": ("Sem comunicação", "neutro", 2), "atencao": ("Atenção", "alerta", 3),
           "sem_leitura": ("Sem leitura", "neutro", 4), "sem_sol": ("Sem sol", "neutro", 5), "ok": ("Normal", "ok", 6)}
# a legenda da faixa, como no mockup (o crítico e o sem produção juntos)
LEGENDA = (("ok", "Normal"), ("atencao", "Atenção"), ("critico", "Crítico / sem produção"),
           ("sem_comm", "Sem comunicação"), ("sem_leitura", "Sem leitura ou sem sol"))


def _norm(s) -> str:
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def estado_agora(tr: dict | None) -> str:
    """A chave do estado pela linha do tempo real (None = o tempo real não trouxe a usina)."""
    if not tr:
        return "sem_leitura"
    st = str(tr.get("status") or "")
    if st == "ok" and str(tr.get("causa") or "").lower().startswith("sem sol"):
        return "sem_sol"
    if st in ("sem_producao", "desligada"):
        return "sem_producao"
    return st if st in ESTADOS else "sem_leitura"


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


def montar(linhas_visao: list[dict], cadastro: dict, tempo_real: dict | None, insights: dict | None,
           sem_luvas: set | None, com_os: bool = True) -> list[dict]:
    """Uma linha por usina da Visão do responsável. `cadastro`: {usina_id: a ficha}; `tempo_real`: {usina_id: a linha}
    (None = a ponte não respondeu: todas "Sem leitura"); `insights`: {usina_id: n} (None = o motor ainda calcula);
    `sem_luvas`: os usina_id sem luvas na última ronda (None = a leitura das rondas falhou); `com_os`: as OS do Fracttal
    chegaram ao banco (sem elas, a coluna diz "sem leitura", nunca 0)."""
    out = []
    for u in linhas_visao or []:
        uid = u.get("usina_id")
        ficha = cadastro.get(uid) or {}
        meta = u.get("meta") or {}
        man = u.get("manutencao") or {}
        ext = u.get("extintores")
        chave = estado_agora((tempo_real or {}).get(uid))
        rot, tom, ordem = ESTADOS[chave]
        conf = []
        if ext and ext.get("vencidos"):
            n = ext["vencidos"]
            conf.append((f"{n} {'extintor vencido' if n == 1 else 'extintores vencidos'}", "critico"))
        if sem_luvas is not None and uid in sem_luvas:
            conf.append(("sem luvas", "critico"))
        sem_fonte = ext is None and sem_luvas is None
        tr = (tempo_real or {}).get(uid) or {}
        out.append({
            "usina_id": uid, "usina": u.get("usina") or "", "codigo": str(ficha.get("codigo") or "").strip(),
            "cliente": u.get("cliente") or "", "cluster": u.get("cluster") or "",
            "mwp": mwp(ficha.get("potencia_contratual")), "tipologia": tipologia(ficha.get("tipologia")),
            "estado": chave, "estado_rot": rot, "estado_tom": tom, "ordem": ordem,
            "lido": str(tr.get("ultima_leitura") or "")[11:16],
            "atingimento": meta.get("atingimento"), "pr": meta.get("pr"), "pr_meta": meta.get("pr_meta"),
            "os_abertas": man.get("os_abertas", 0) if com_os else None,
            "os_atrasadas": man.get("atrasadas_os", 0) if com_os else None,
            "insights": None if insights is None else insights.get(uid, 0),
            "conformidade": conf, "conformidade_ok": not conf and not sem_fonte, "conformidade_sem_fonte": sem_fonte})
        x = out[-1]
        # o que a busca da página olha (`filtro-local.js` compara sem acento e sem caixa)
        x["busca"] = _norm(" ".join([x["usina"], x["codigo"], x["cliente"], x["cluster"], x["tipologia"]]))
    out.sort(key=lambda x: (x["ordem"], x["atingimento"] if x["atingimento"] is not None else 1e9, x["usina"]))
    return out


def resumo(linhas: list[dict]) -> dict:
    """As contas da faixa e da legenda: quantas usinas em cada estado da legenda."""
    grupo = {"sem_producao": "critico", "critico": "critico", "sem_sol": "sem_leitura"}
    n = {k: 0 for k, _ in LEGENDA}
    for x in linhas:
        n[grupo.get(x["estado"], x["estado"])] += 1
    return {"por_estado": n, "total": len(linhas), "clientes": sorted({x["cliente"] for x in linhas if x["cliente"]})}
