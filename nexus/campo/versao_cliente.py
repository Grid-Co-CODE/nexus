"""As versões do cliente das telas do Nexus (08/11/2026, Levi: "a ideia é liberar os campos e conforme for o cliente
aparecerá as usinas só daquele cliente"; o filtro de mês no topo vale para todas).

Cada tela que o setor Clientes vê ganha aqui a conta da versão dele: o mesmo dado da tela da Grid, SÓ das usinas do
cliente da sessão (`setor_telas.usinas_do_cliente`) e no mês escolhido (`setor_telas.mes_do_cliente`), e SEM o que o
mockup da Visão do cliente tira dele: nome e telefone de técnico, supervisor, gestor, custo, horas, comentário interno e
a causa da falha antes da Engenharia. As funções são puras (recebem o dado já lido), para o teste provar o recorte.
"""
from datetime import date, datetime, timedelta


def _no_mes(iso: str | None, mes: date) -> bool:
    try:
        d = datetime.fromisoformat(str(iso)[:10]).date()
    except (TypeError, ValueError):
        return False
    return d.year == mes.year and d.month == mes.month


def rondas(dados: dict, usinas: set[int], mes: date) -> dict:
    """As rondas do mês nas usinas do cliente e a cobertura de agora. Sem técnico, sem nota, sem duração."""
    feitas = [r for r in dados.get("todas") or [] if r.get("usina_id") in usinas and _no_mes(r.get("data"), mes)]
    linhas = [{"data": r["data"], "usina": r.get("usina") or "", "onde": r.get("cidade") or "",
               "tipo": r.get("tipo") or "Ronda", "os": r.get("os"),
               "pendente": bool(r.get("pendencia")),
               "situacao": "com pendência" if r.get("pendencia") else "concluída"}
              for r in sorted(feitas, key=lambda r: (r.get("data") or "", r.get("fim") or ""), reverse=True)]
    cobertura = [{"usina": c.get("usina") or "", "ultima": c.get("ultima"),
                  "dias": c.get("dias") if c.get("ultima") else None}
                 for c in dados.get("cobertura") or [] if c.get("usina_id") in usinas]
    cobertura.sort(key=lambda c: (-(c["dias"] if c["dias"] is not None else 9999), c["usina"]))
    com_ronda = {r.get("usina_id") for r in feitas}
    return {"linhas": linhas, "cobertura": cobertura, "n": len(linhas),
            "usinas": len(cobertura), "com_ronda": len(com_ronda & {c.get("usina_id") for c in dados.get("cobertura") or []
                                                                    if c.get("usina_id") in usinas}),
            "atrasadas": sum(1 for c in cobertura if c["dias"] is None or c["dias"] >= 7)}


# ── Quadro da semana (PCM) ────────────────────────────────────────────────────────────────────────────────────────────
# a situação da OS pelas tarefas dela na programação (o `quadro.estado` de cada tarefa): concluída só com TODAS
# finalizadas; a pausada pesa mais que a em execução (é a que espera alguma coisa)
_DIAS_PCM = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")


def _situacao_os(estados: list[str], dia: date | None, hoje: date) -> tuple[str, str]:
    if estados and all(e == "Finalizada" for e in estados):
        return "concluída", "ok"
    if "Pausada" in estados:
        return "pausada", "alerta"
    if "Em progresso" in estados or "Finalizada" in estados:
        return "em execução", "info"
    if dia is not None and dia >= hoje:
        return "programada", "neutro"
    return "não iniciada", "alerta"


def quadro(semanas: list[dict], usina_de, usinas: set[int], mes: date, hoje: date, nomes: dict | None = None) -> dict:
    """A programação do mês nas usinas do cliente, por usina e por OS (09/11/2026, a entrega 2 das versões do cliente).

    `semanas`: as semanas publicadas no App (`banco_dados.json` do PCM: {week, rows}); `usina_de(nome)`: o usina_id do
    cadastro pelo nome da linha (o `campo.responsaveis.Nomes`, a mesma ligação da Visão do cliente); `nomes`: o nome do
    cadastro de cada usina_id. Cada tarefa cai no dia dela (a segunda da semana + o dia da coluna), e só as do mês
    contam. Fica de fora o que é da Grid: equipe, responsável, horário, horas, deslocamento, relatório, motivo,
    etiquetas e as pendentes que não entraram na semana. O arquivo guarda só as últimas semanas: `desde` diz de quando é
    a mais antiga, para a tela não fingir que o mês está inteiro."""
    from ..pcm import historico_banco as HB
    from ..pcm import quadro as Q
    nomes = nomes or {}
    cache: dict[str, int | None] = {}
    por_os: dict[str, dict] = {}
    desde = None
    for s in semanas or []:
        try:
            seg = HB.segunda(str(s.get("week") or ""))
        except ValueError:
            continue
        desde = seg if desde is None or seg < desde else desde
        for r in s.get("rows") or []:
            d = Q.dia_de(r.get("dia"))
            if d not in _DIAS_PCM:
                continue
            dia = seg + timedelta(days=_DIAS_PCM.index(d))
            if (dia.year, dia.month) != (mes.year, mes.month):
                continue
            nome = str(r.get("usina") or "")
            if nome not in cache:
                cache[nome] = usina_de(nome)
            uid = cache[nome]
            if uid not in usinas:
                continue
            os_n = str(r.get("os_id") or "").strip()
            if not os_n:
                continue
            o = por_os.setdefault(os_n, {"os": os_n, "uid": uid, "dias": set(), "tipos": [], "tarefas": {}})
            o["dias"].add(dia)
            o["tipos"].append(str(r.get("tipo") or "").strip())
            # a tarefa que rolou de uma semana para a outra aparece nas duas: conta uma vez, com o estado da mais nova
            chave = (str(r.get("tarefa") or ""), str(r.get("codigo") or ""))
            if chave not in o["tarefas"] or o["tarefas"][chave][0] <= dia:
                o["tarefas"][chave] = (dia, Q.estado(r))
    por_usina: dict[int, dict] = {}
    for o in por_os.values():
        tipos = [t for t in o["tipos"] if t]
        tipo = max(set(tipos), key=tipos.count) if tipos else ""
        dias = sorted(o["dias"])
        estados = [e for _d, e in o["tarefas"].values()]
        sit, cor = _situacao_os(estados, dias[-1] if dias else None, hoje)
        u = por_usina.setdefault(o["uid"], {"uid": o["uid"], "usina": nomes.get(o["uid"]) or "", "oss": []})
        u["oss"].append({"os": o["os"], "dia": dias[0] if dias else None, "ate": dias[-1] if len(dias) > 1 else None,
                         "tipo": tipo, "tarefas": len(estados), "situacao": sit, "cor": cor})
    linhas = []
    for u in por_usina.values():
        u["oss"].sort(key=lambda x: (x["dia"] or date.min, x["os"]))
        u["n"] = len(u["oss"])
        u["feitas"] = sum(1 for x in u["oss"] if x["cor"] == "ok")
        u["abertas"] = u["n"] - u["feitas"]
        prox = [x["dia"] for x in u["oss"] if x["cor"] != "ok" and x["dia"] and x["dia"] >= hoje]
        u["proxima"] = min(prox) if prox else None
        linhas.append(u)
    linhas.sort(key=lambda u: (-u["abertas"], u["usina"]))
    n = sum(u["n"] for u in linhas)
    feitas = sum(u["feitas"] for u in linhas)
    return {"linhas": linhas, "n": n, "feitas": feitas, "abertas": n - feitas, "usinas": len(linhas),
            "desde": desde if _falta_dia_util(mes, desde) else None, "sem_programacao": desde is None}


def _falta_dia_util(mes: date, desde: date | None) -> bool:
    """O arquivo começa depois de algum dia útil do mês (o PCM programa de segunda a sexta)? Novembro de 2026 começa num
    domingo: o arquivo que vem da segunda, 02/11, cobre o mês inteiro, e o aviso seria falso."""
    if desde is None or desde <= mes:
        return False
    d = mes
    while d < desde and d.month == mes.month:
        if d.weekday() < 5:
            return True
        d += timedelta(days=1)
    return False


# ── Extintores (HSEQ) ────────────────────────────────────────────────────────────────────────────────────────────────
# a ordem da tabela da Segurança: o atrasado primeiro (`extintores.SITUACOES`)
_ORDEM_EXT = {"atrasado": 0, "perto": 1, "sem_validade": 2, "em_dia": 3}


def extintores(lista: list[dict], usinas: set[int], mes: date) -> dict:
    """Os extintores das usinas do cliente, por usina (10/11/2026, entrega 2). `lista`: os extintores da tela da Segurança
    já sem os excluídos (`decisoes.separar`), com a situação de agora (`extintores.linha`). O mês do topo conta as
    conferências feitas nele e as validades que vencem nele; a situação é a de agora (o livro guarda só a última
    conferência de cada extintor). Fica de fora o que é da Grid: quem conferiu, técnicos, responsável, a informação
    adicional do técnico, os não reconhecidos, as edições e os pedidos de ronda da Segurança, as fotos e os relatórios."""
    from ..hseq import extintores as EXT
    meus = [x for x in lista or [] if x.get("usina_id") in usinas]
    por_usina: dict[int, dict] = {}
    for x in meus:
        rot, tom = EXT.SITUACOES.get(x.get("situacao"), ("", "neutro"))
        st, st_tom = EXT.STATUS_TST.get(x.get("status") or "", ("", "neutro"))
        u = por_usina.setdefault(x["usina_id"], {"uid": x["usina_id"], "usina": x.get("usina") or "", "itens": []})
        u["itens"].append({"ext": x.get("ext") or "", "local": x.get("local") or "", "posicao": x.get("posicao") or "",
                           "classe": x.get("classe") or "", "peso": x.get("peso"), "recarga": x.get("val2") or "",
                           "hidrostatico": x.get("val3") or "", "conferencia": x.get("conferencia"),
                           "situacao": rot, "tom": tom, "chave": x.get("situacao") or "", "status": st,
                           "status_tom": st_tom})
    linhas = []
    for u in por_usina.values():
        u["itens"].sort(key=lambda i: (_ORDEM_EXT.get(i["chave"], 9), i["ext"]))
        u["n"] = len(u["itens"])
        u["atrasados"] = sum(1 for i in u["itens"] if i["chave"] == "atrasado")
        u["perto"] = sum(1 for i in u["itens"] if i["chave"] == "perto")
        u["sem_validade"] = sum(1 for i in u["itens"] if i["chave"] == "sem_validade")
        confs = [i["conferencia"] for i in u["itens"] if i["conferencia"]]
        u["ultima"] = max(confs) if confs else None
        linhas.append(u)
    linhas.sort(key=lambda u: (-u["atrasados"], -u["perto"], u["usina"]))
    vencem = sum(1 for x in meus for f in (x.get("fim2"), x.get("fim3"))
                 if isinstance(f, date) and (f.year, f.month) == (mes.year, mes.month))
    return {"linhas": linhas, "n": len(meus), "usinas": len(linhas),
            "atrasados": sum(u["atrasados"] for u in linhas), "perto": sum(u["perto"] for u in linhas),
            "conferidos_mes": sum(1 for x in meus if _no_mes(x.get("conferencia"), mes)), "vencem_mes": vencem}


# ── EPI e EPC (HSEQ) ─────────────────────────────────────────────────────────────────────────────────────────────────
def epi(linhas_epi: list[dict], usinas: set[int], mes: date) -> dict:
    """As luvas isolantes das usinas do cliente pela ronda diária (10/11/2026, entrega 2). `linhas_epi`: as linhas de
    `hseq.epi.luvas` (uma por usina). A situação e a última verificação são as de agora; o mês do topo conta as
    verificações feitas nele (`por_mes`, todas as respostas da janela do livro, não só as 8 da linha). Sem o técnico, o
    responsável, a equipe nem as fotos da ronda."""
    from ..hseq import epi as EPI
    chave_mes = f"{mes.year}-{mes.month:02d}"
    out = []
    for x in linhas_epi or []:
        if x.get("usina_id") not in usinas:
            continue
        rot, tom = EPI.SITUACOES.get(x.get("situacao"), ("", "neutro"))
        ult = x.get("ultima") or {}
        m = (x.get("por_mes") or {}).get(chave_mes) or {}
        out.append({"usina": x.get("usina") or "", "situacao": rot, "tom": tom, "chave": x.get("situacao") or "",
                    "ultima": ult.get("dia"), "luvas": ult.get("luvas"), "os": ult.get("os"),
                    "desde": x.get("desde"), "mes_n": m.get("n", 0), "mes_nao": m.get("nao", 0)})
    rank = {s: i for i, s in enumerate(EPI.SITUACOES)}
    out.sort(key=lambda u: (rank.get(u["chave"], 9), u["usina"]))
    return {"linhas": out, "usinas": len(out),
            "com_luvas": sum(1 for u in out if u["chave"] == "com_luvas"),
            "sem_luvas": sum(1 for u in out if u["chave"] == "sem_luvas"),
            "sem_verificacao": sum(1 for u in out if u["chave"] == "sem_verificacao"),
            "verificacoes_mes": sum(u["mes_n"] for u in out)}


# ── Almoxarifado (PCM) ───────────────────────────────────────────────────────────────────────────────────────────────
_SIT_PECA = {"abaixo": ("abaixo do mínimo", "critico", 0), "no_limite": ("no limite", "alerta", 1),
             "saldo_unitario": ("saldo unitário", "alerta", 2), "zerada": ("zerada", "neutro", 3),
             "sem_minimo": ("sem mínimo", "neutro", 3), "ok": ("em dia", "ok", 4),
             "nao_informado": ("saldo não informado", "neutro", 5)}


def almoxarifado(d: dict, usinas: set[int], mes: date) -> dict:
    """O almoxarifado de cada usina do cliente (10/11/2026, entrega 2): o saldo de agora (o último ciclo da varredura do
    App) e as peças que saíram nas OS no mês do topo. `d`: a conta da tela do PCM (`pcm.almoxarifado.montar`). O
    almoxarifado mora debaixo da usina no Fracttal (1 almoxarifado = 1 usina): o que não ligou a uma usina fica de fora.
    Sem custo, valor, criticidade, curva, as avariadas, as recusas e o inventário (é a gestão do PCM)."""
    linhas = [x for x in (d or {}).get("linhas") or [] if x.get("usina_id") in usinas and not x.get("avariada")]
    por: dict[str, dict] = {}
    for x in linhas:
        rot, tom, ordem = _SIT_PECA.get(x.get("situacao"), ("", "neutro", 9))
        a = por.setdefault(x["id_almox"], {"id": x["id_almox"], "nome": x.get("almox") or "",
                                           "usina": x.get("usina") or "", "pecas": [], "abaixo": 0, "no_limite": 0,
                                           "saidas": []})
        a["pecas"].append({"codigo": x.get("codigo") or "", "nome": x.get("nome") or "",
                           "unidade": x.get("unidade") or "", "saldo": x.get("saldo"), "minimo": x.get("minimo"),
                           "situacao": rot, "tom": tom, "ordem": ordem})
        a["abaixo"] += x.get("situacao") == "abaixo"
        a["no_limite"] += x.get("situacao") in ("no_limite", "saldo_unitario")
    for c in (d or {}).get("consumo") or []:
        a = por.get(c.get("id_almox"))
        dia = _iso_do_id(c.get("data_id"))
        if a is None or c.get("situacao") != "lançada" or not _no_mes(dia, mes):
            continue
        a["saidas"].append({"dia": dia, "os": c.get("os") or "", "codigo": c.get("codigo") or "",
                            "nome": c.get("nome") or "", "quantidade": c.get("quantidade")})
    out = []
    for a in por.values():
        a["pecas"].sort(key=lambda p: (p["ordem"], p["codigo"]))
        a["saidas"].sort(key=lambda s: (s["dia"], s["os"]), reverse=True)
        out.append(a)
    out.sort(key=lambda a: (-a["abaixo"], -a["no_limite"], a["usina"], a["nome"]))
    return {"almoxarifados": out, "n": len(out), "pecas": len(linhas),
            "abaixo": sum(a["abaixo"] for a in out), "no_limite": sum(a["no_limite"] for a in out),
            "saidas_mes": sum(len(a["saidas"]) for a in out),
            "saldo_de": ((d or {}).get("ciclo") or {}).get("fim") or ""}


def _iso_do_id(v) -> str:
    """20261012 -> "2026-10-12" (vazio se não for uma data)."""
    s = str(v or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else ""
