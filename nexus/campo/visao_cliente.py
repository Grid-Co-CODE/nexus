"""A Visão do cliente, fase 1 (05/11/2026): a síntese das usinas de UM cliente, para o COS, o PCM e a Performance
responderem o cliente em segundos, sem WhatsApp.

De onde veio: a sugestão "Visão do cliente: Comando com a síntese das usinas dele" (Início → Sugestões, 04/11/2026, com
o mockup); o Levi decidiu a fase 1 ("Sim, fase 1"): a tela para a Grid, com o login de hoje, na Usinas 360°. A fase 2 (o
login do cliente) reaproveita ESTA conta, por isso ela é feita POR CLIENTE aqui no servidor e já sai sem o que é interno:
nada de nome ou telefone de técnico, custo, horas, comentário interno da OS nem causa de falha (a plataforma diz o
sintoma, não a causa). "Contrato" não existe como entidade no cadastro: o recorte é o `cliente_id` da usina.

Nenhuma conta nova; cada número é o da tela dona, com a régua de lá:
- status: o tempo real da plataforma (a Entrada, `/api/entrada/tempo-real`), lido pela ponte SÓ DE LEITURA: o pedido do
  Nexus não monta cache nem fala com a API PV, a SunOp é paga (teto de 2.700 por dia). Usina que o tempo real não traz é
  "Sem leitura", nunca parada; fora da janela solar a plataforma diz "Sem sol" e aqui fica "Sem sol", nunca "Gerando";
- performance do mês: o Gerencial (`fato_meta_usina_mes`, a mesma linha da Visão do responsável): a geração do mês sobre
  a meta (P50) até os dias cobertos; o do cliente é a soma das usinas;
- chamados na distribuidora: o Andamento da Ronda COS (a tela Acionamentos), os de 30 dias com o protocolo, sem os
  dispensados. O Andamento não diz quando a distribuidora resolveu: a tela fala "nos últimos 30 dias", não "abertos";
- OS: as tarefas das OS do Fracttal (`fato_tarefa_os`) pela régua do quadro "OS e manutenção" da Visão (`manutencao.
  tarefas_por_usina`): fora o backoffice, o Teste, a zeladoria e as OS de chamado. O número "abertas" é o que ainda vai
  ser feito (a fazer + em execução); a concluída que espera a conferência da Grid fica à parte (na Athon, 382 de 422 em
  05/11/2026: o número do cliente não pode ser a fila interna de aprovação);
- próxima visita: a programação do PCM (`fato_programacao`, o Quadro da semana), o bloco ainda não feito mais próximo de
  hoje em diante. A hora prevista de chegada (equipe saiu da base) é a fase 3, no App.

O detalhe da usina (a entrega 2, mesmo dia): a linha do dia com o que as fontes guardam COM HORA (a parada aberta pela OS
de parada da disponibilidade, o chamado e o protocolo na distribuidora, os blocos de hoje da programação; a OS aberta hoje
vai no fim, com "hoje", porque o fato das OS só guarda o dia), as paradas abertas, os chamados com o protocolo e as OS
com a situação. As mesmas fontes da síntese, nenhuma leitura nova além da agenda de hoje (da mesma programação lida).
"""
from collections import defaultdict
from datetime import date, datetime, timezone

from ..dados import fatos as D
from . import manutencao as M

# o status do tempo real para quem lê: (rótulo, tom, peso na ordem: menor = pede atenção antes)
STATUS = {"sem_producao": ("Parada", "critico", 0), "desligada": ("Parada", "critico", 0),
          "sem_comm": ("Sem comunicação", "alerta", 1), "critico": ("Gerando com perda", "critico", 2),
          "atencao": ("Gerando com perda", "alerta", 3), "ok": ("Gerando", "ok", 9)}
SEM_LEITURA = ("Sem leitura", "neutro", 1)
SEM_SOL = ("Sem sol", "neutro", 8)
# a régua do Gerencial (a mesma da Visão: `META_NA_META` e `META_ATENCAO`)
PERF_OK, PERF_ATENCAO = 97.0, 90.0
TIPO = {"preventiva": "preventiva", "corretiva": "corretiva", "corretiva_emergencial": "corretiva emergencial",
        "religamento": "religamento", "religamento_remoto": "religamento remoto", "inspecao": "inspeção",
        "preditiva": "preditiva", "administrativa": "administrativa", "handover": "handover"}
_VIVA = M._VIVA
_COMECOU = M._COMECOU
# o instante do Andamento vem com fuso (`andamento.instante`): o "nunca" da ordem também precisa de fuso
_NUNCA = datetime.min.replace(tzinfo=timezone.utc)


def _dia(v) -> date | None:
    return M._dia(v)


def _tipo(v) -> str:
    """O tipo da tarefa para quem lê, em minúscula: o fato das OS grava a chave ("corretiva_emergencial") e a programação
    grava a palavra do PCM ("Corretiva Emergencial", "Inspeção")."""
    import unicodedata
    t = " ".join(unicodedata.normalize("NFKD", D._txt(v)).encode("ascii", "ignore").decode().lower().split())
    if t.replace(" ", "_") in TIPO or t in TIPO:
        return TIPO.get(t.replace(" ", "_"), TIPO.get(t))
    # o código de plano do PCM ("MPA", "MPS"...) é preventiva: a palavra e o código, como o PCM escreve
    if t[:2] == "mp" and t.replace(" ", "").isalnum() and len(t) <= 5:
        return f"preventiva ({D._txt(v).upper()})"
    return D._txt(v)


def status_da_usina(tr: dict | None, hoje: date | None = None) -> dict:
    """O status de uma usina pela linha do tempo real (`None` = o tempo real não a trouxe). A última leitura de outro dia
    leva a data (na bancada, "última leitura 22:43" era de ontem)."""
    if not tr:
        rot, tom, peso = SEM_LEITURA
        return {"rotulo": rot, "tom": tom, "peso": peso, "lido": "", "chave": "sem_leitura"}
    st = str(tr.get("status") or "")
    causa = str(tr.get("causa") or "")
    if st == "ok" and causa.lower().startswith("sem sol"):
        rot, tom, peso = SEM_SOL
        chave = "sem_sol"
    else:
        rot, tom, peso = STATUS.get(st, (st or "sem leitura", "neutro", 1))
        chave = {"sem_producao": "parada", "desligada": "parada", "sem_comm": "sem_com", "critico": "perda",
                 "atencao": "perda", "ok": "gerando"}.get(st, "sem_leitura")
    lido = str(tr.get("ultima_leitura") or "")
    txt = lido[11:16] if len(lido) >= 16 else ""
    if txt and hoje and lido[:10] != f"{hoje:%Y-%m-%d}":
        txt = f"{lido[8:10]}/{lido[5:7]} {txt}"
    return {"rotulo": rot, "tom": tom, "peso": peso, "lido": txt, "chave": chave}


def juntar_tempo_real(usinas_tr: list[dict], nomes) -> dict[int, dict]:
    """{usina_id: a linha do tempo real} pelo nome que a plataforma escreve (`responsaveis.Nomes`: o de-para, o nome do
    cadastro e o Fracttal). Usina do cadastro com duas linhas lá (Santarém 1 e 2): fica a pior."""
    out: dict[int, dict] = {}
    for r in usinas_tr or ():
        uid, _como = nomes.usina(r.get("usina"))
        if not uid:
            continue
        atual = out.get(uid)
        if atual is None or status_da_usina(r)["peso"] < status_da_usina(atual)["peso"]:
            out[uid] = r
    return out


def chamados_por_usina(b, leituras: list) -> dict[int, list[dict]]:
    """{usina_id: os chamados à distribuidora de 30 dias, o mais novo primeiro}, pelas leituras do Andamento (uma por
    cliente dele), com a usina ligada pelo código como a tela Acionamentos (`acionamentos.painel`). Só o que o cliente
    pode ver: a distribuidora, a UC, a situação, quando abriu e quando foi enviado, o protocolo e a OS (nada de quem
    abriu, do contato nem das proteções que atuaram). Os dispensados ficam de fora."""
    from ..cos import acionamentos as AC
    from ..cos import andamento as AND
    out: dict[int, list[dict]] = defaultdict(list)
    for lt in leituras or ():
        d = lt.dados or {}
        uid_do_codigo = {}
        for u in d.get("usinas") or []:
            uid_do_codigo[u.get("codigo")] = b.lig.usina(u.get("nome"), u.get("codigo"))[0]
        for c in d.get("chamados") or []:
            est = str(c.get("estado") or "")
            if est == "DISPENSADO":
                continue
            uid = uid_do_codigo.get(c.get("usina_codigo"))
            if not uid:
                continue
            rot, tom = AC.ESTADOS_DO_CHAMADO.get(est, (est.lower(), "neutro"))
            out[uid].append({"concessionaria": D._txt(c.get("concessionaria")), "uc": D._txt(c.get("uc")),
                             "situacao": rot, "tom": tom, "criado": AND.instante(c.get("criado_em")),
                             "protocolo": D._txt(c.get("protocolo")),
                             "protocolo_quando": AND.instante(c.get("protocolo_em")), "os": D._txt(c.get("os")),
                             "enviado": AND.instante(c.get("enviado_em"))})
    for lst in out.values():
        lst.sort(key=lambda c: c["criado"] or _NUNCA, reverse=True)
    return dict(out)


def chamados_agrupados(chamados: list | None) -> list[dict]:
    """Os chamados da usina para o painel: os do MESMO protocolo (a distribuidora dá um para as várias UCs) num item só,
    com as UCs; sem protocolo, cada chamado é um item. A contagem da tabela e do topo segue por chamado, como a tela
    Acionamentos (a dona)."""
    out, por = [], {}
    for c in chamados or ():
        chave = (c.get("protocolo"), c.get("concessionaria"), c.get("situacao")) if c.get("protocolo") else None
        if chave and chave in por:
            if c.get("uc"):
                por[chave]["ucs"].append(c["uc"])
            continue
        g = {"protocolo": c.get("protocolo") or "", "concessionaria": c.get("concessionaria") or "",
             "situacao": c.get("situacao"), "tom": c.get("tom"), "criado": c.get("criado"),
             "ucs": [c["uc"]] if c.get("uc") else []}
        out.append(g)
        if chave:
            por[chave] = g
    return out


def os_por_usina(tarefas: list[dict] | None, os_de_chamado: set, hoje: date) -> dict[int, list[dict]]:
    """{usina_id: as OS abertas, uma por OS}, pela régua do quadro "OS e manutenção" da Visão (`manutencao.
    tarefas_por_usina`: fora o backoffice, o Teste, a zeladoria e as OS de chamado; a OS em verificação conta, qualquer
    que seja o estado da tarefa). Para quem lê: o número, o tipo e a situação ("em execução", "programada para dd/mm",
    "concluída, em conferência"). Sem horas nem quem fez."""
    por: dict[tuple, dict] = {}
    comecou = set()
    for t in tarefas or ():
        uid, os_ = D._id(t.get("usina_id")), D._id(t.get("os"))
        if not uid or not os_:
            continue
        tipo = D._txt(t.get("tipo_tarefa"))
        if D._txt(t.get("estado_tarefa")) in _COMECOU:
            comecou.add(os_)
        if tipo in ("zeladoria", "teste") or D._int(t.get("do_backoffice")) == 1 or os_ in os_de_chamado:
            continue
        status_os = D._txt(t.get("status_os"))
        viva = D._txt(t.get("estado_tarefa")) != "finalizada" and status_os in _VIVA
        if status_os != "em_verificacao" and not viva:
            continue
        o = por.setdefault((uid, os_), {"os": os_, "wid": D._id(t.get("fracttal_os_id")), "tipos": set(),
                                        "verificacao": False, "programada": None, "criada": None})
        if tipo:
            o["tipos"].add(tipo)
        o["verificacao"] = o["verificacao"] or status_os == "em_verificacao"
        prog, cri = _dia(t.get("data_id_programada")), _dia(t.get("data_id_criacao"))
        if prog and (o["programada"] is None or prog < o["programada"]):
            o["programada"] = prog
        if cri and (o["criada"] is None or cri < o["criada"]):
            o["criada"] = cri
    out: dict[int, list[dict]] = defaultdict(list)
    for (uid, os_), o in por.items():
        if o["verificacao"]:
            sit, tom, ordem = "concluída, em conferência", "ok", 2
        elif os_ in comecou:
            sit, tom, ordem = "em execução", "info", 0
        elif o["programada"] and o["programada"] >= hoje:
            sit, tom, ordem = f"programada para {o['programada']:%d/%m}", "neutro", 1
        else:
            sit, tom, ordem = "aguardando execução", "alerta", 1
        tipos = sorted(_tipo(x) for x in o["tipos"])
        out[uid].append({"os": os_, "wid": o["wid"], "tipo": " · ".join(tipos) or "OS", "situacao": sit, "tom": tom,
                         "ordem": ordem, "criada": o["criada"], "programada": o["programada"],
                         "execucao": os_ in comecou and not o["verificacao"],
                         "verificacao": o["verificacao"]})
    for lst in out.values():
        lst.sort(key=lambda x: (x["ordem"], x["programada"] or date.max, x["os"]))
    return dict(out)


def visitas_por_usina(programacao: list[dict] | None, hoje: date, agora_hhmm: str = "00:00") -> dict[int, dict]:
    """{usina_id: a próxima visita}: o bloco da programação do PCM ainda não feito, de hoje em diante, o mais cedo
    (dia e hora de início). De hoje, só o que ainda vai começar: o bloco das 09:00 visto às 18:00 já foi feito ou está em
    andamento (a OS diz "em execução"), não é a próxima visita (achado na bancada com a Athon, 05/11/2026). A hora é a
    planejada no Quadro, não a de chegada (fase 3)."""
    out: dict[int, dict] = {}
    hid = int(f"{hoje:%Y%m%d}")
    for l in programacao or ():
        uid, dia = D._id(l.get("usina_id")), D._int(l.get("data_id_programada"))
        if not uid or not dia or dia < hid or D._txt(l.get("status_execucao")) == "finalizada":
            continue
        hora = D._txt(l.get("hora_inicio"))[:5]
        if dia == hid and hora and hora < agora_hhmm:
            continue
        chave = (dia, hora or "99:99")
        atual = out.get(uid)
        if atual is None or chave < atual["_chave"]:
            out[uid] = {"_chave": chave, "dia": _dia(dia), "hora": hora,
                        "tipo": _tipo(l.get("tipo_tarefa"))}
    for v in out.values():
        v.pop("_chave", None)
    return out


def _situacao_bloco(status: list[str], passou: bool = False) -> tuple[str, str]:
    """A situação de um bloco da programação pelas tarefas dele: alguma em progresso = em execução; todas finalizadas =
    feita; alguma pausada = pausada; a hora já passou sem começar = não iniciada (o status do Quadro); senão,
    programada."""
    if "em_progresso" in status:
        return "em execução", "info"
    if status and all(s == "finalizada" for s in status):
        return "feita", "ok"
    if "pausada" in status:
        return "pausada", "alerta"
    if passou:
        return "não iniciada", "alerta"
    return "programada", "neutro"


def agenda_de_hoje(programacao: list[dict] | None, hoje: date, agora_hhmm: str = "00:00") -> dict[int, list[dict]]:
    """{usina_id: os blocos de hoje da programação do PCM, em ordem de hora}: um por hora e tipo (as tarefas do mesmo
    bloco juntas), com a situação. O bloco cuja hora já passou sem começar diz "não iniciada" (na bancada da Athon, às
    18:50, o das 09:00 dizia "programada"). Sem quem vai nem duração: só a hora planejada no Quadro, o tipo e a
    situação."""
    hid = int(f"{hoje:%Y%m%d}")
    blocos: dict[tuple, list] = defaultdict(list)
    for l in programacao or ():
        uid = D._id(l.get("usina_id"))
        if not uid or D._int(l.get("data_id_programada")) != hid:
            continue
        blocos[(uid, D._txt(l.get("hora_inicio"))[:5], _tipo(l.get("tipo_tarefa")))].append(
            D._txt(l.get("status_execucao")))
    out: dict[int, list[dict]] = defaultdict(list)
    for (uid, hora, tipo), status in blocos.items():
        sit, tom = _situacao_bloco(status, passou=bool(hora) and hora < agora_hhmm)
        out[uid].append({"hora": hora, "tipo": tipo, "situacao": sit, "tom": tom, "tarefas": len(status)})
    for lst in out.values():
        lst.sort(key=lambda b: (b["hora"] or "99:99", b["tipo"]))
    return dict(out)


def linha_do_dia(paradas: list | None, chamados: list | None, os_: list | None, agenda: list | None,
                 hoje: date) -> list[dict]:
    """O que aconteceu hoje na usina, pela hora: a parada que começou hoje (a OS de parada da disponibilidade), o chamado
    aberto na distribuidora (o envio; sem envio, quando foi registrado) e o protocolo, os blocos da programação de hoje.
    A OS aberta hoje vai no fim com "hoje": o fato das OS guarda o dia, não a hora. Fonte que não respondeu não inventa
    nada."""
    iso = f"{hoje:%Y-%m-%d}"
    ev = []
    for p in paradas or ():
        ini = str(p.get("_ini") or "")
        if ini[:10] == iso and len(ini) >= 16:
            ev.append({"hora": ini[11:16], "texto": f"Parada registrada: {p.get('escopo') or 'usina'} · OS {p.get('os')}",
                       "tom": "critico"})
    # a distribuidora dá UM protocolo para as várias UCs da usina (produção, 05/11/2026: a Mandaguaçu repetia a mesma
    # linha 4 vezes): o mesmo acontecimento das várias UCs é uma linha só, com quantas UCs
    do_chamado: dict[tuple, int] = {}
    for c in chamados or ():
        conc = c.get("concessionaria") or "distribuidora"
        q = c.get("enviado") or c.get("criado")
        if q and q.date() == hoje:
            k = (f"{q:%H:%M}", f"Chamado aberto na {conc}", "alerta")
            do_chamado[k] = do_chamado.get(k, 0) + 1
        pq = c.get("protocolo_quando")
        if c.get("protocolo") and pq and pq.date() == hoje:
            k = (f"{pq:%H:%M}", f"Protocolo {c['protocolo']} da {conc}", "ok")
            do_chamado[k] = do_chamado.get(k, 0) + 1
    for (hora, texto, tom), n in do_chamado.items():
        ev.append({"hora": hora, "texto": texto + (f" · {n} UCs" if n > 1 else ""), "tom": tom})
    for b in agenda or ():
        ev.append({"hora": b["hora"] or "—", "texto": f"Visita {b['situacao']}: {b['tipo']}", "tom": b["tom"]})
    ev.sort(key=lambda e: e["hora"])
    for o in os_ or ():
        if o.get("criada") == hoje:
            # a OS aberta hoje que já está em conferência foi feita no mesmo dia: "aberta" sozinho enganava
            ev.append({"hora": "hoje", "texto": f"OS {o['os']} aberta e concluída: {o['tipo']}", "tom": "ok"}
                      if o.get("verificacao") else
                      {"hora": "hoje", "texto": f"OS {o['os']} aberta: {o['tipo']}", "tom": "info"})
    return ev


def _parada(p: dict) -> dict:
    """A parada aberta para quem lê: o escopo, desde quando, o tipo da OS e o número. Sem o código do ativo."""
    tipo = D._txt(p.get("tipo"))
    return {"os": D._txt(p.get("os")), "tipo": _tipo(tipo) if tipo and tipo != "—" else "",
            "escopo": "" if D._txt(p.get("escopo")) == "—" else D._txt(p.get("escopo")),
            "desde": D._txt(p.get("inicio"))}


def _tom_perf(p) -> str:
    return "neutro" if p is None else ("ok" if p >= PERF_OK else ("alerta" if p >= PERF_ATENCAO else "critico"))


def _quando(dia: date | None, hora: str, hoje: date) -> str:
    if not dia:
        return ""
    d = "Hoje" if dia == hoje else ("Amanhã" if (dia - hoje).days == 1 else f"{dia:%d/%m}")
    return f"{d} {hora}".strip()


def montar(usinas: list[dict], tempo_real: dict[int, dict] | None, chamados: dict[int, list] | None,
           os_abertas: dict[int, list] | None, visitas: dict[int, dict] | None, hoje: date,
           agenda: dict[int, list] | None = None) -> dict:
    """A síntese de UM cliente. `usinas` = as linhas da Visão do responsável SÓ desse cliente (usina_id, usina, cidade,
    uf, meta, paradas_abertas); as fontes por usina_id, ou None quando a fonte não respondeu: aí o número fica "sem
    leitura" (None), nunca 0. Cada linha leva o detalhe (as paradas abertas e a linha do dia, com a `agenda` de hoje).
    Devolve {kpis, linhas (quem pede atenção primeiro), normais (sem pendência), total}."""
    linhas = []
    for u in usinas:
        uid = u["usina_id"]
        st = status_da_usina((tempo_real or {}).get(uid), hoje) if tempo_real is not None else \
            dict(zip(("rotulo", "tom", "peso"), SEM_LEITURA), lido="", chave="sem_leitura")
        m = u.get("meta") or {}
        pct = m.get("atingimento")
        ch = (chamados or {}).get(uid, []) if chamados is not None else None
        os_ = (os_abertas or {}).get(uid, []) if os_abertas is not None else None
        vis = (visitas or {}).get(uid) if visitas is not None else None
        # o lugar é a cidade, sem a equipe: o nome da equipe pode ser o de uma pessoa (o PCM, 05/11/2026)
        onde = (f"{u['cidade']}/{u['uf']}" if u.get("uf") else u["cidade"]) if u.get("cidade") else ""
        linha = {"usina_id": uid, "usina": u.get("usina") or "", "onde": onde,
                 "status": st, "perf": None if pct is None else {"pct": pct, "tom": _tom_perf(pct)},
                 "prod_kwh": m.get("prod_kwh"), "meta_kwh": m.get("meta_kwh"),
                 "chamados": ch, "chamados_grupos": chamados_agrupados(ch) if ch is not None else None,
                 "os": os_, "visita": vis, "visita_lida": visitas is not None,
                 "visita_txt": _quando(vis["dia"], vis["hora"], hoje) if vis else ""}
        linha["paradas"] = [_parada(p) for p in u.get("paradas_abertas") or ()]
        linha["dia"] = linha_do_dia(u.get("paradas_abertas"), ch, os_, (agenda or {}).get(uid), hoje)
        a_fazer = [o for o in (os_ or ()) if not o["verificacao"]]
        linha["os_abertas"] = len(a_fazer) if os_ is not None else None
        pendente = (st["chave"] not in ("gerando", "sem_sol") or bool(ch) or bool(a_fazer)
                    or (pct is not None and pct < PERF_ATENCAO))
        linha["pendente"] = pendente
        linha["_ordem"] = (st["peso"], -len(ch or ()), pct if pct is not None else 999.0, -len(a_fazer),
                           linha["usina"].lower())
        linhas.append(linha)
    linhas.sort(key=lambda x: x["_ordem"])
    for x in linhas:
        x.pop("_ordem")
    return {"kpis": kpis(linhas, tempo_real is not None, chamados is not None, os_abertas is not None,
                         visitas is not None, hoje),
            "linhas": [x for x in linhas if x["pendente"]], "normais": [x for x in linhas if not x["pendente"]],
            "total": len(linhas)}


def kpis(linhas: list[dict], com_tr: bool, com_ch: bool, com_os: bool, com_vis: bool, hoje: date) -> dict:
    """Os 5 números do topo. Fonte que não respondeu: o número é None (a tela escreve "sem leitura"), nunca 0."""
    total = len(linhas)
    c = defaultdict(int)
    for x in linhas:
        c[x["status"]["chave"]] += 1
    status = None
    if com_tr:
        sem_sol = c["sem_sol"]
        status = {"valor": c["gerando"] + sem_sol, "de": total, "rotulo": "sem alerta" if sem_sol else "gerando",
                  "selos": [(n, rot, tom) for n, rot, tom in (
                      (c["parada"], "parada" if c["parada"] == 1 else "paradas", "critico"),
                      (c["perda"], "com perda", "alerta"), (c["sem_com"], "sem comunicação", "alerta"),
                      (c["sem_leitura"], "sem leitura", "neutro"), (sem_sol, "sem sol", "neutro")) if n]}
    com_meta = [x for x in linhas if x.get("prod_kwh") is not None and x.get("meta_kwh")]
    meta = sum(x["meta_kwh"] for x in com_meta)
    pct = round(100.0 * sum(x["prod_kwh"] for x in com_meta) / meta, 1) if meta else None
    perf = {"pct": pct, "tom": _tom_perf(pct), "usinas": len(com_meta)}
    chamados = None
    if com_ch:
        todos = [(x["usina"], ch) for x in linhas for ch in (x["chamados"] or [])]
        datas = [ch["criado"].date() for _u, ch in todos if ch["criado"]]
        chamados = {"n": len(todos), "protocolo": sum(1 for _u, ch in todos if ch["protocolo"]),
                    "mais_antigo": (hoje - min(datas)).days if datas else None}
    os_ = None
    if com_os:
        todas = [o for x in linhas for o in (x["os"] or [])]
        os_ = {"n": sum(1 for o in todas if not o["verificacao"]), "execucao": sum(1 for o in todas if o["execucao"]),
               "verificacao": sum(1 for o in todas if o["verificacao"]),
               "programadas": sum(1 for o in todas if not o["execucao"] and not o["verificacao"])}
    visita = None
    if com_vis:
        prox = sorted(((x["visita"]["dia"], x["visita"]["hora"] or "99:99", x) for x in linhas if x["visita"]),
                      key=lambda t: (t[0], t[1]))
        visita = {"quando": "", "usina": "", "tipo": ""}
        if prox:
            dia, _h, x = prox[0]
            visita = {"quando": x["visita_txt"], "usina": x["usina"], "tipo": x["visita"]["tipo"]}
    return {"status": status, "perf": perf, "chamados": chamados, "os": os_, "visita": visita}


def por_cliente(usinas: list[dict], b) -> dict[int, list[dict]]:
    """{cliente_id: as linhas da Visão das usinas dele}, pelo `cliente_id` da usina no cadastro (`b.por_id`). "Contrato"
    não existe como entidade: o recorte é este, e a fase 2 vai filtrar pelo mesmo `cliente_id` do login do cliente."""
    out: dict[int, list[dict]] = defaultdict(list)
    for u in usinas or ():
        cid = D._id((b.por_id.get(u.get("usina_id")) or {}).get("cliente_id"))
        if cid:
            out[cid].append(u)
    return dict(out)


def opcoes_de_cliente(grupos: dict[int, list], nome_cliente: dict) -> list[tuple[int, str, int]]:
    """(cliente_id, nome, quantas usinas) para a escolha, em ordem de nome."""
    return sorted(((cid, nome_cliente.get(cid) or f"Cliente {cid}", len(us)) for cid, us in grupos.items()),
                  key=lambda t: t[1].lower())


# ── a leitura do tempo real pela ponte só de leitura (o único pedido à plataforma desta tela) ─────────────────────────
TR_VALIDADE_S = 120
_TR = {"t": 0.0, "dados": None, "erro": ""}


def ler_tempo_real(cfg) -> dict:
    """{"usinas": [as linhas do tempo real], "cache_ts", "idade_s", "erro"} pela ponte só de leitura (`X-Nexus-Leitura`:
    a plataforma serve o que já montou e não fala com a API PV; o `force` nunca vai). Guardado 2 min: a Entrada da
    plataforma é refeita de 30 em 30 min. Sem a ponte configurada, ou sem resposta: `erro` e nenhuma usina (a tela diz
    "sem leitura", nunca parada)."""
    import threading
    import time as _t
    from ..performance import ponte
    trava = _TR.setdefault("_trava", threading.Lock())
    with trava:
        if _TR["dados"] is not None and _t.monotonic() - _TR["t"] < TR_VALIDADE_S:
            return _TR["dados"]
        url, token = cfg.get("NEXUS_PLATAFORMA_URL"), cfg.get("NEXUS_PLATAFORMA_TOKEN")
        out = {"usinas": [], "cache_ts": "", "idade_s": None, "erro": ""}
        if not url or not token:
            out["erro"] = "o tempo real da plataforma não está ligado neste servidor"
        else:
            try:
                r = ponte.enviar(**ponte.montar_pedido(url, token, "GET", "/api/entrada/tempo-real", [], None, None))
                ok = {str(k).lower(): v for k, v in r.headers.items()}.get("x-nexus-leitura-ok") == "1"
                if r.status_code != 200 or not ok:
                    out["erro"] = f"a plataforma respondeu {r.status_code} ao tempo real"
                else:
                    d = r.json()
                    out.update(usinas=[u for g in d.get("grupos") or [] for u in g.get("usinas") or []
                                       if isinstance(u, dict)],
                               cache_ts=str(d.get("cache_ts") or ""), idade_s=d.get("idade_s"))
            except Exception as e:      # noqa: BLE001 — sem o tempo real, a tela segue com "sem leitura"
                out["erro"] = f"o tempo real não respondeu ({type(e).__name__})"
        _TR.update(t=_t.monotonic(), dados=out)
        return out


def limpar() -> None:
    _TR.update(t=0.0, dados=None)
