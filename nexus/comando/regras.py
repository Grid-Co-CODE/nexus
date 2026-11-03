"""As regras do motor de insights (Fase 1, 03/11/2026; Levi: "construa o que você sugere", a partir da tela de Insights do
mockup R18: "essa parte de insights também é muito boa").

Cada regra cruza o que o Nexus JÁ lê e aponta um problema com evidência, ação e dono (a TORRE: o setor da pessoa vê as
torres liberadas em Base → Acessos, sem cadastro de cadeira). Puras: recebem as listas já lidas (o motor lê, `motor.py`)
e devolvem insights; o teste chama direto, com dado inventado.

Um insight é um dict: `id` (estável: a regra e o objeto, para o "assumir" sobreviver à próxima conta), `regra`, `sev`
(critico, atencao, info), `titulo`, `evid` (as provas, em frases curtas), `acao`, `torre`, `usina`, `link` (a tela onde
se age), `desde` (date ou None).

Fora da Fase 1, e por quê (PRD em .taskmaster/docs/prd.txt): R01 (a anomalia sem OS é calculada pela plataforma e não
chega ao Nexus), R02, R04 e R08 (pedem ajuste), R06 completa, R10 e R12 (sem fonte: a vigência da garantia, o EPC, o
prazo do relatório).
"""
import re
from datetime import date, datetime, timedelta

SEVERIDADES = {"critico": ("Crítico", "critico", "agir hoje"), "atencao": ("Atenção", "alerta", "esta semana"),
               "info": ("Informativo", "info", "registrar")}
ORDEM_SEV = {"critico": 0, "atencao": 1, "info": 2}

# O catálogo: o nome, a torre dona, o KPI que a regra protege, de onde ela lê e as áreas que se NOTIFICA (`avisar`). A
# torre dona é quem vê o insight na Caixa de entrada e no sino. `avisar` = as áreas que o botão "Notificar" já traz
# marcadas (Levi, 03/11/2026: "religamentos em 30 dias e etc é coisa da engenharia, já está com eles... pode aparecer
# tipo 'notificar engenharia'"; "extintores pode ser tanto equipe de segurança quanto supervisor o manager quer algo como
# notificar as áreas e saber como está e receber retornos dessas áreas"). A área notificada responde (Recebido, Em
# andamento, Resolvido, com o retorno) e quem notificou acompanha.
REGRAS = {
    "R03": {"nome": "Religamento repetido na mesma cabine", "torre": "cos", "kpi": "Religamento remoto ≥ 70% · MTBF",
            "fonte": "COS → Religamentos (as ocorrências de 30 dias da Ronda COS)", "avisar": ["engenharia"]},
    "R05": {"nome": "Sem comunicação há mais de 24 h", "torre": "cos", "kpi": "Comunicação ≥ 99%",
            "fonte": "Ronda COS (as ocorrências abertas da Thopen, no banco)", "avisar": ["campo"]},
    "R06": {"nome": "Falha nova em ativo que já tem chamado de garantia", "torre": "chamados", "kpi": "Custo evitado",
            "fonte": "OS do Fracttal (no banco) × Chamados → Garantias", "avisar": ["engenharia"]},
    "R07": {"nome": "Extintor vencido", "torre": "hseq", "kpi": "Entregáveis contratuais (PPCI)",
            "fonte": "Segurança → Extintores", "avisar": ["hseq", "campo"]},
    "R09": {"nome": "Equipe acima da capacidade na semana", "torre": "pcm", "kpi": "Backlog ≤ 10%",
            "fonte": "PCM (a programação da semana)", "avisar": ["pcm"]},
    "R11": {"nome": "Usina sem ronda há mais de 7 dias", "torre": "campo", "kpi": "Cobertura de rondas",
            "fonte": "Campo · App → Rondas", "avisar": ["campo", "pcm"]},
    "R13": {"nome": "Chamado parado com o fabricante", "torre": "chamados", "kpi": "Custo evitado",
            "fonte": "Chamados → Garantias", "avisar": ["chamados"]},
    "N01": {"nome": "Normalizada com a OS aberta no Fracttal", "torre": "cos", "kpi": "MTTR e disponibilidade",
            "fonte": "COS → Normalizações (a Ronda COS)", "avisar": ["campo"]},
}

REINCIDENTE = 3              # religamentos na mesma cabine em 30 dias (a régua de reincidência do RDO, COS → Religamentos)
COMUNICACAO_DIAS = 1         # mais de 24 h aberta
COMUNICACAO_CRITICO_DIAS = 3
GARANTIA_JANELA_DIAS = 90    # o chamado concluído há até 90 dias ainda cobre a falha nova do mesmo ativo
SEM_RONDA_DIAS = 7           # visao.DIAS_SEM_RONDA_ALERTA
SEM_RONDA_CRITICO_DIAS = 15
PARADO_DIAS = 5              # o "parado" do quadro de Garantias (acomp_web.DIAS_PARADA)
PARADO_CRITICO_DIAS = 30
NORMALIZADA_DIAS = 7         # a régua da tela Normalizações (vermelho a partir de 7 dias depois da volta)
NORMALIZADA_CRITICO_DIAS = 15
FABRICANTE = "Aguardando retorno do Fabricante"


def _dia(v) -> date | None:
    """`data_id` (AAAAMMDD, número ou texto) ou date/datetime -> date."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        n = int(float(str(v).strip()))
        return datetime.strptime(str(n), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def _txt(v) -> str:
    return " ".join(str(v or "").split())


def _id(v) -> int | None:
    try:
        n = int(float(str(v).strip()))
        return n or None
    except (TypeError, ValueError):
        return None


def _insight(regra, objeto, sev, titulo, evid, acao, usina="", link="", desde=None) -> dict:
    # o id sem espaço (03/11/2026: "R03:Junco 1:..." era recusado no Assumir e virava âncora inválida na página)
    return {"id": f"{regra}:{re.sub(r'[\s]+', '_', str(objeto).strip())}", "regra": regra, "sev": sev, "titulo": titulo, "evid": [e for e in evid if e],
            "acao": acao, "torre": REGRAS[regra]["torre"], "usina": usina, "link": link, "desde": desde}


# ── R03 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def r03_religamentos(equipamentos: list[dict]) -> list[dict]:
    """Cada equipamento (cabine, inversor) com 3 religamentos ou mais em 30 dias. `equipamentos` = os itens do painel de
    Religamentos de cada cliente: {cliente, usina, rotulo, tag, total, os, ultima}."""
    out = []
    for e in equipamentos:
        if (e.get("total") or 0) < REINCIDENTE:
            continue
        os_ = [str(x) for x in e.get("os") or []][:4]
        out.append(_insight(
            "R03", f"{_txt(e.get('usina'))}:{_txt(e.get('tag')) or _txt(e.get('rotulo'))}", "critico",
            f"{_txt(e.get('usina'))}: {e['total']} religamentos em 30 dias em {_txt(e.get('rotulo')) or 'um equipamento'}",
            [f"OS {', '.join(os_)}" if os_ else "", f"o último em {e['ultima']:%d/%m %H:%M}" if e.get("ultima") else ""],
            "Abrir OS de causa raiz (proteção, qualidade da rede, coordenação com a concessionária) em vez de mais um "
            "religamento: cada um conta como evento no MTBF.",
            _txt(e.get("usina")), f"/t/cos/religamentos?cliente={_txt(e.get('cliente'))}&dias=30&ver=repetem",
            e["ultima"].date() if e.get("ultima") else None))
    return out


# ── R05 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def r05_sem_comunicacao(abertas: list[dict], nome_usina) -> list[dict]:
    """A ocorrência de falha de comunicação aberta há mais de 24 h (o retrato da hora das abertas da Thopen, no banco:
    `nexus_cos_normalizacoes · fato_ocorrencia_aberta`)."""
    out = []
    for o in abertas:
        if "COMUNICA" not in str(o.get("tipo_falha") or "").upper():
            continue
        try:
            dias = int(float(o.get("dias_aberta_qtd") or 0))
        except (TypeError, ValueError):
            continue
        if dias < COMUNICACAO_DIAS:
            continue
        usina = nome_usina(o.get("usina_id")) or _txt(o.get("usina_codigo"))
        os_ = _txt(o.get("os"))
        out.append(_insight(
            "R05", _txt(o.get("registro")) or f"{usina}:{os_}",
            "critico" if dias >= COMUNICACAO_CRITICO_DIAS else "atencao",
            f"{usina}: sem comunicação há {dias} {'dia' if dias == 1 else 'dias'}",
            [f"OS {os_}" if os_ else "ainda sem OS", "a geração parou (resposta do operador)" if str(o.get("geracao_parou"))
             in ("1", "1.0", "True", "true") else ""],
            "Acionar a TI e o campo para a comunicação: sem ela, a usina some do tempo real e a disponibilidade fica sem "
            "medida.", usina, "/t/cos/ronda?cliente=Thopen", _dia(o.get("data_id_inicio"))))
    return out


# ── R06 (parcial) ───────────────────────────────────────────────────────────────────────────────────────────────────
def r06_falha_com_chamado(tarefas_os: list[dict], chamados: list[dict], nome_usina, hoje: date) -> list[dict]:
    """A OS corretiva aberta num ativo que já tem chamado de garantia (aberto, em verificação ou concluído há até 90
    dias), aberta depois do chamado: a falha nova deve ir ao fabricante, junto do chamado, e não virar corretiva comum.
    A R06 completa (o ativo ainda na garantia, sem chamado) espera a vigência da garantia, que o Nexus não tem."""
    por_equip = {}
    for c in chamados:
        eid = _id(c.get("equipamento_id"))
        if not eid:
            continue
        fim = _dia(c.get("data_id_fim"))
        if c.get("situacao") not in ("aberto", "verificacao") and not (fim and (hoje - fim).days <= GARANTIA_JANELA_DIAS):
            continue
        por_equip.setdefault(eid, []).append(c)
    vistas, out = set(), []
    for t in tarefas_os:
        os_, eid = _txt(t.get("os")), _id(t.get("equipamento_id"))
        if not eid or eid not in por_equip or os_ in vistas or "corretiva" not in str(t.get("tipo_tarefa") or "").lower():
            continue
        if str(t.get("status_os") or "") not in ("em_processo", "em_verificacao"):
            continue
        criada = _dia(t.get("data_id_criacao"))
        chs = [c for c in por_equip[eid] if _txt(c.get("os")) != os_
               and (not criada or not _dia(c.get("data_id_abertura")) or _dia(c.get("data_id_abertura")) <= criada)]
        if not chs:
            continue
        vistas.add(os_)
        c = max(chs, key=lambda x: _dia(x.get("data_id_abertura")) or date.min)
        usina = nome_usina(t.get("usina_id")) or _txt(t.get("site_fracttal"))
        ativo = _txt(t.get("codigo_ativo")) or _txt(c.get("codigo_ativo"))
        out.append(_insight(
            "R06", os_, "atencao",
            f"{usina}: OS corretiva {os_} num ativo com chamado de garantia ({ativo})",
            [f"chamado na OS {_txt(c.get('os'))}" + (f" com {_txt(c.get('fabricante'))}" if c.get("fabricante") else ""),
             f"situação do chamado: {_txt(c.get('situacao'))}"],
            "Juntar a falha ao chamado com o fabricante em vez de tratar como corretiva comum: a garantia cobre o reparo.",
            usina, "/t/chamados/garantias", criada))
    return out


# ── R07 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def r07_extintores(por_usina: list[dict]) -> list[dict]:
    """A usina com extintor vencido (a recarga ou o teste hidrostático), pela conta de Segurança → Extintores, já sem os
    excluídos pela Segurança."""
    out = []
    for u in por_usina:
        n = int(u.get("atrasado") or 0)
        if n <= 0:
            continue
        usina = _txt(u.get("usina"))
        out.append(_insight(
            "R07", _txt(u.get("usina_id")) or usina, "critico",
            f"{usina}: {n} {'extintor vencido' if n == 1 else 'extintores vencidos'}",
            [f"de {u.get('qtd')} na usina" if u.get("qtd") else ""],
            "Programar a recarga ou o teste hidrostático e a troca na próxima ronda: extintor vencido é não conformidade "
            "de PPCI.", usina, "/t/hseq/extintores"))
    return out


# ── R09 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def r09_capacidade(resumo: dict, semana: str) -> list[dict]:
    """O cluster (equipe) com mais horas programadas na semana do que a capacidade dele (o `resumo` da semana no banco
    do PCM: {cluster: {hh_util, hh_disp, pend}}). A mesma conta do alerta do PCM (relatorios/alerta.py)."""
    out = []
    for cluster, v in (resumo or {}).items():
        try:
            util, disp = float(v.get("hh_util") or 0), float(v.get("hh_disp") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        if not disp or util <= disp:
            continue
        uso = util / disp
        out.append(_insight(
            "R09", f"{semana}:{cluster}", "critico" if uso > 1.5 else "atencao",
            f"{cluster}: {util:.0f} h programadas para {disp:.0f} h de capacidade na semana {semana}",
            [f"uso de {uso * 100:.0f}%", f"{int(v.get('pend') or 0)} tarefas ficaram fora" if v.get("pend") else ""],
            "Tirar tarefa da semana ou rever a capacidade da equipe: acima da capacidade, a semana vai rolar por "
            "construção.", "", "/t/pcm/quadro"))
    return out


# ── R11 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def r11_sem_ronda(cobertura: list[dict]) -> list[dict]:
    """A usina mobilizada sem ronda há mais de 7 dias (a cobertura de Campo · App → Rondas; 999 = nunca)."""
    out = []
    for c in cobertura:
        dias = int(c.get("dias") or 0)
        if dias < SEM_RONDA_DIAS:
            continue
        usina = _txt(c.get("usina"))
        nunca = dias >= 999
        out.append(_insight(
            "R11", _txt(c.get("usina_id")) or usina, "critico" if nunca or dias >= SEM_RONDA_CRITICO_DIAS else "atencao",
            f"{usina}: {'nenhuma ronda registrada' if nunca else f'sem ronda há {dias} dias'}",
            [f"a última em {c['ultima']:%d/%m}" if hasattr(c.get("ultima"), "strftime") else "",
             f"técnico da última: {_txt(c.get('tecnico'))}" if c.get("tecnico") else ""],
            "Programar a ronda da usina com o PCM e o técnico da região.", usina, "/t/campo/rondas?aba=sem"))
    return out


# ── R13 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def r13_chamado_parado(chamados_por_usina: dict, nome_usina) -> list[dict]:
    """O chamado aberto aguardando o fabricante há 5 dias ou mais (`responsaveis.chamados`: o status do fato, com a
    troca feita na tela de Garantias por cima). Os dias contam da abertura: o fato não guarda quando o status mudou."""
    out = []
    for uid, x in (chamados_por_usina or {}).items():
        for c in x.get("lista") or []:
            if c.get("situacao") != "aberto" or c.get("status") != FABRICANTE:
                continue
            dias = c.get("dias")
            if dias is None or dias < PARADO_DIAS:
                continue
            usina = nome_usina(uid)
            out.append(_insight(
                "R13", _txt(c.get("os")), "critico" if dias >= PARADO_CRITICO_DIAS else "atencao",
                f"{usina}: chamado da OS {c['os']} aguardando o fabricante há {dias} dias",
                [f"{_txt(c.get('fabricante'))}" + (f" · {_txt(c.get('componente'))}" if c.get("componente") else ""),
                 f"equipamento: {_txt(c.get('equip'))}" if c.get("equip") else ""],
                "Cobrar o fabricante com o número do chamado e registrar o retorno na tela de Garantias.", usina,
                "/t/chamados/garantias"))
    return out


# ── N01 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def n01_normalizadas(itens: list[dict]) -> list[dict]:
    """A normalização cuja OS segue aberta no Fracttal 7 dias ou mais depois da volta, ou com a hora a corrigir (a
    conferência da Ronda COS). `itens` = os itens da tela Normalizações (`normalizacoes._item`)."""
    out = []
    for i in itens:
        if not i.get("normalizada") or not i.get("os"):
            continue
        dias = i.get("aberta_ha_dias") if i.get("aberta") else None
        conf = (i.get("conferencia") or {}).get("situacao")
        aberta_demais = dias is not None and dias >= NORMALIZADA_DIAS
        if not aberta_demais and conf != "HORA_A_CORRIGIR":
            continue
        evid = []
        if aberta_demais:
            evid.append(f"{i.get('status') or 'aberta'} no Fracttal {dias} dias depois da volta")
        if conf == "HORA_A_CORRIGIR":
            dif = (i.get("conferencia") or {}).get("dif_fim")
            evid.append("hora a corrigir no Fracttal" + (f" (conclusão {dif:+d} min)" if isinstance(dif, int) else ""))
        out.append(_insight(
            "N01", _txt(i.get("os")), "critico" if (dias or 0) >= NORMALIZADA_CRITICO_DIAS else "atencao",
            f"{_txt(i.get('usina'))}: a OS {i['os']} voltou e segue aberta no Fracttal" if aberta_demais
            else f"{_txt(i.get('usina'))}: a OS {i['os']} com a hora a corrigir no Fracttal",
            evid, "Finalizar a OS no Fracttal com a hora da volta registrada pelo COS: é ela que vale para MTTR e "
            "disponibilidade.", _txt(i.get("usina")), f"/t/cos/normalizacoes?q={_txt(i.get('os'))}",
            i["volta"].date() if i.get("volta") else None))
    return out


def ordenar(insights: list[dict]) -> list[dict]:
    """O mais grave primeiro; na mesma gravidade, o mais antigo (o que espera há mais tempo)."""
    return sorted(insights, key=lambda x: (ORDEM_SEV.get(x["sev"], 9), x.get("desde") or date.max, x["titulo"]))
