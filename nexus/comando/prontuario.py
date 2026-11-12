"""O prontuário da usina no Comando (12/11/2026). Levi: "A ideia do prontuário da UFV é juntar todas as informações
daquela usina para que o supervisor/gestor fique ciente do que está acontecendo na UFV como métricas, pendências,
insights e etc. Deixe forma visual agradável e direta!"; e "Tem várias coisas que tem no mockup que não estão na versão
final".

A forma (Levi, 12/11/2026, vendo a 1ª versão com tudo aberto): "quanto mais direto formos, melhor [...] a ideia não é
essa página ser uma caixa de texto infinita [...] Primeiramente, dando um parecer geral, e quando a pessoa quiser se
aprofundar, se aprofunda [...] Sejamos assertivos". Por isso: o parecer numa linha (`parecer`) e um cartão FECHADO por
assunto com o estado dele numa linha (`resumos`); o detalhe só aparece ao abrir o cartão. E "essa visão irá substituir a
central da usina": a aba da usina da Usinas 360° mostra esta mesma página.

O painel do alto (Levi, no mesmo dia, vendo a versão enxuta): "ficou legal essa parte mais enxuta. Mas eu creio que dá
para colocar um pouquinho mais de números [...] Pelo menos os KPIs principais de performance, meta, OS, pendências [...]
e deixar de uma forma mais visual. Então, o visual na frente, o que está mais importante na frente, e ali aprofundando
abaixo [...] mesmo dando drill down, a informação direta ali na lata [...] E aí a pessoa consiga também clicar e já se
encaminhando para aquela informação. Aquela informação aparecer na tela dela". Por isso `painel`: a Performance do mês
em medidores com barra (a meta, o PR e a disponibilidade, cada um contra a marca dele), as OS abertas por estado com as
atrasadas, as pausadas e o plano da semana, as pendências contadas, e uma faixa com o resto (ronda, sujidade e
vegetação, chamados, segurança, COS, insights). Cada número abre o cartão dele na própria página.

Funções puras: recebem o dado já lido (a view lê as fontes, `torres/comando/prontuario_dados.py`) e devolvem o que a
tela mostra; o teste prova a conta. Nada se inventa: cada parte sai da tela dona, e a fonte que não tem o dado fica de
fora da página, com o aviso.

De onde vem cada parte:
- "Pede atenção agora": os alertas que a Visão do responsável já calcula para a usina (Performance, Manutenção e
  Acompanhamento), as ocorrências abertas no COS (a régua de Comando > Usinas), os insights vivos críticos e de atenção e
  as demandas vencidas que citam a usina. O mais grave primeiro;
- o painel do alto: os valores da Visão do responsável (o mesmo número e a mesma cor de lá), com a barra de cada um
  e o mês anterior ao lado; as OS abertas por estado são as do bloco Manutenção da Visão (`manutencao.por_usina`);
- mês a mês: `nexus_performance · fato_meta_usina_mes` e `falhas_performance · disponibilidade_dia` (os meses que o
  banco tem: desde 10/2026);
- o COS: as normalizações da Ronda COS (`nexus_cos_normalizacoes · fato_normalizacao`), as últimas e a conta por mês;
- a zeladoria: a leitura semanal de sujidade e vegetação (`nexus_zeladoria · zeladoria_semana`, 1 a 5) e a recomendação;
- as rondas: o histórico de 90 dias do Usinas 360°;
- os equipamentos com OS aberta: as tarefas das OS abertas do Fracttal no banco (`nexus_os · fato_tarefa_os`) por ativo,
  com o nome do `nexus_equipamentos · dim_equipamento` e o chamado de garantia aberto do mesmo ativo;
- a composição: a ficha da usina no cadastro (os rótulos são os de `cadastro/esquema.py`) e a estrutura do Nexus;
- a linha do tempo: as rondas, as normalizações do COS, as PT, os chamados e as OS abertas, numa lista só, por dia.
"""
from datetime import date, datetime, timedelta, timezone

from . import usinas as CU

BRT = timezone(timedelta(hours=-3))
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro",
         "dezembro")
DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
ORDEM_TOM = {"critico": 0, "alerta": 1, "semcom": 2, "info": 3, "neutro": 4, "ok": 5}
# a seção da página a que cada alerta da Visão leva (a `area` do alerta); o que não está aqui é da Manutenção
_SECAO_DA_AREA = {"meta": "perf", "pr": "perf", "disp": "perf", "ronda": "rondas", "limpeza": "rondas",
                  "zeladoria": "rondas", "chamados": "chamados", "pt": "seg", "extintores": "seg"}
# o tipo da falha da Ronda COS que a régua de Comando > Usinas (`usinas._MOTIVOS`) não nomeia
_TIPOS_COS = {"DESLIGAMENTO_USINA": "Usina desligada", "DESLIGAMENTO_INVERSOR": "Inversor desligado",
              "INVERSOR_FALHA_STRING": "String em falha", "INVERSOR_OFFLINE": "Inversor offline",
              "ANORMALIDADE_VENTILADOR": "Anormalidade no ventilador", "MANUTENCAO_PROGRAMADA": "Manutenção programada"}
_RECOMENDACAO = {"supressao_vegetal": "Supressão vegetal", "limpeza_modulos": "Limpeza de módulos"}
_SITUACAO_PT = {"de_acordo": "De acordo", "negada": "Não autorizada", "aguardando": "Aguardando o De acordo"}
_TIPO_TAREFA = {"corretiva_emergencial": "corretiva emergencial", "religamento_remoto": "religamento remoto",
                "inspecao": "inspeção"}
LINHA_DO_TEMPO_DIAS = 30


# ── números e datas em pt-BR ────────────────────────────────────────────────────────────────────────────────────────
def num(v, casas: int = 1) -> str:
    """12345.6 -> "12.345,6"; None -> "—"."""
    if v is None:
        return "—"
    s = f"{float(v):,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v, casas: int = 1) -> str:
    return "—" if v is None else num(v, casas) + "%"


def _int(v) -> int | None:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _float(v) -> float | None:
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def do_data_id(v) -> date | None:
    """20261108 -> date(2026, 11, 8)."""
    n = _int(v)
    if not n or n < 19000101:
        return None
    try:
        return date(n // 10000, n // 100 % 100, n % 100)
    except ValueError:
        return None


def instante(v) -> datetime | None:
    """O texto ISO (com Z, com -03:00 ou sem fuso, que vale UTC) em horário de Brasília."""
    s = str(v or "").strip()
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(BRT)


def dia_txt(d) -> str:
    """"ter, 10/11"."""
    return f"{DIAS[d.weekday()]}, {d.strftime('%d/%m')}" if d else ""


def fora_txt(minutos) -> str:
    """86 -> "1 h 26 min"; 3 -> "3 min"; 3000 -> "2 d 2 h"."""
    m = _int(minutos)
    if m is None or m < 0:
        return ""
    if m < 60:
        return f"{m} min"
    if m < 24 * 60:
        return f"{m // 60} h" + (f" {m % 60} min" if m % 60 else "")
    d, h = m // (24 * 60), m % (24 * 60) // 60
    return f"{d} d" + (f" {h} h" if h else "")


# ── o resumo do alto ────────────────────────────────────────────────────────────────────────────────────────────────
def sem_o_nome(titulo: str, usina: str) -> str:
    """"Crateús 1: a OS 16702 voltou" -> "A OS 16702 voltou" (o prontuário já é da usina)."""
    t = str(titulo or "")
    if usina and t.lower().startswith(usina.lower() + ":"):
        t = t[len(usina) + 1:].strip()
        t = t[:1].upper() + t[1:]
    return t


def atencao(u: dict | None, os_cos: list | None, insights: list | None, demandas=(), usina: str = "") -> list[dict]:
    """O que pede atenção agora na usina, o mais grave primeiro: [{tom, titulo, detalhe, secao}]. `u` = a linha da
    Visão do responsável (com `perf`, `manut` e `acomp`); `os_cos` = as ocorrências abertas do COS já classificadas
    (`usinas.agora_pelo_cos`); `insights` = os vivos; `demandas` = as que citam a usina e a pessoa pode ver."""
    itens = []
    for bloco in ("perf", "manut", "acomp"):
        for a in ((u or {}).get(bloco) or {}).get("alertas") or []:
            titulo = str(a.get("titulo") or "")
            itens.append({"tom": "critico" if a.get("nivel") == "critico" else "alerta",
                          "titulo": titulo[:1].upper() + titulo[1:], "detalhe": str(a.get("detalhe") or ""),
                          "secao": _SECAO_DA_AREA.get(a.get("area"), "os")})
    for o in os_cos or []:
        partes = [o.get("os_rotulo") or "", f"aberta {o['ha']}" if o.get("ha") else "", o.get("etapa") or ""]
        itens.append({"tom": o.get("tom") or "alerta", "titulo": f"No COS: {o.get('motivo') or o.get('rotulo') or 'ocorrência aberta'}",
                      "detalhe": " · ".join(p for p in partes if p), "secao": "cos"})
    for i in insights or []:
        if i.get("sev") in ("critico", "atencao"):
            itens.append({"tom": "critico" if i["sev"] == "critico" else "alerta",
                          "titulo": sem_o_nome(i.get("titulo"), usina), "detalhe": str(i.get("acao") or ""),
                          "secao": "insights"})
    for d in demandas or []:
        if (d.get("estado") or {}).get("vencida"):
            itens.append({"tom": "critico", "titulo": f"Demanda vencida: {d.get('titulo') or ''}",
                          "detalhe": f"de {d.get('de_nome') or 'alguém'} para {d.get('para_nome') or 'alguém'}",
                          "secao": "demandas"})
    itens.sort(key=lambda i: ORDEM_TOM.get(i["tom"], 9))
    return itens


def em_dia(u: dict | None) -> list[str]:
    """O que a Visão do responsável diz que está bem na usina (o `bem` de cada bloco)."""
    return [str(b) for bloco in ("perf", "manut", "acomp") for b in ((u or {}).get(bloco) or {}).get("bem") or []]


# ── o parecer, o painel do alto e a linha de cada cartão ──────────────────────────────────────────────────────────────
PARECER = {"critico": "Pede ação agora", "alerta": "Pede acompanhamento", "ok": "Em dia"}
_PESO = {"critico": 3, "alerta": 2, "atencao": 2, "semcom": 2, "info": 1, "ok": 1, "neutro": 0}


def _pior(*cls) -> str:
    """O tom mais grave entre os dados (a régua da Visão chama a atenção de "alerta" ou "atencao")."""
    p = max((c or "neutro" for c in cls), key=lambda c: _PESO.get(c, 0), default="neutro")
    return "alerta" if p == "atencao" else p


def parecer(itens: list[dict]) -> dict:
    """O parecer geral da usina numa linha, pelo que pede atenção (`atencao`): {"nivel", "titulo", "frase"}. Crítico
    havendo um ponto crítico; atenção havendo qualquer outro; em dia sem nenhum. A frase conta e diz o principal (o 1º
    da lista, que já vem do mais grave para o menos): nada é opinião, é a contagem do que as telas donas apontam."""
    crit = sum(1 for i in itens if i["tom"] == "critico")
    resto = len(itens) - crit
    nivel = "critico" if crit else ("alerta" if itens else "ok")
    if not itens:
        frase = "Nada aberto na Visão do responsável, no COS nem nos Insights."
    else:
        partes = ([f"{crit} {'ponto crítico' if crit == 1 else 'pontos críticos'}"] if crit else []) + \
                 ([f"{resto} de atenção"] if resto else [])
        frase = " e ".join(partes) + ". O principal: " + itens[0]["titulo"] + "."
    return {"nivel": nivel, "titulo": PARECER[nivel], "frase": frase}


ESCALA_META = 120.0      # a barra da meta do mês vai de 0 a 120% (quem passa da meta ainda cabe); a marca fica em 100%
# as OS abertas por estado no Fracttal (`manutencao.por_usina`): (o campo, o nome na legenda, a chave da cor da barra)
_ESTADOS_OS = (("nao_iniciadas", "não iniciadas", "ni"), ("em_execucao", "em execução", "ex"),
               ("em_verificacao", "em verificação", "ve"))
_RONDA_TIPO = {"longa_pendente": "ronda longa pendente", "nunca": "nunca rondada", "sem_ronda": "sem ronda no prazo"}


def _barra(v, teto: float = 100.0) -> float | None:
    """A largura da barra em % do trilho: `v` numa escala de 0 a `teto`, presa nas duas pontas. None = sem valor (a
    barra não se desenha: nada de barra vazia fingindo zero)."""
    f = _float(v)
    if f is None:
        return None
    return round(max(0.0, min(f, teto)) / teto * 100, 1)


def _valores(u, bloco) -> dict:
    return ((u or {}).get(bloco) or {}).get("valores") or {}


def _medidores(u: dict | None, anterior: dict | None) -> list[dict]:
    """A meta, o PR e a disponibilidade do mês: o número e a cor da Visão do responsável, a barra contra a marca de cada
    um (a meta em 100%, o PR previsto, os 99% da régua da disponibilidade), o que explica o número embaixo e o mês
    anterior ao lado."""
    from ..campo.responsaveis import DISP_OK
    pv, meta, disp, ant = _valores(u, "perf"), (u or {}).get("meta") or {}, (u or {}).get("disp") or {}, anterior or {}

    def antes(k):
        return f"{ant['curto']}: {ant[k]}" if ant.get(k) not in (None, "", "—") else ""

    def m(chave, rot, v, largura, marca, marca_rot, sub, ant_txt):
        v = v or {}
        return {"chave": chave, "rot": rot, "txt": v.get("txt") or "—", "cls": v.get("cls") or "neutro",
                "largura": largura, "marca": marca if largura is not None else None, "marca_rot": marca_rot,
                "sub": sub, "ant": ant_txt}
    prod, alvo = _float(meta.get("prod_kwh")), _float(meta.get("meta_kwh"))
    pr = dict(pv.get("pr") or {})
    if pr.get("txt") and pr["txt"] != "—":
        pr["txt"] = pr["txt"] + "%"
    pr_meta = _float(meta.get("pr_meta"))
    h = _float(disp.get("h_perdidas"))
    return [
        m("meta", "Meta do mês", pv.get("meta"), _barra(meta.get("atingimento"), ESCALA_META), _barra(100, ESCALA_META), "meta",
          f"{num(prod / 1000)} de {num(alvo / 1000)} MWh" if prod is not None and alvo else "", antes("ating")),
        m("pr", "PR", pr, _barra(meta.get("pr")), _barra(pr_meta), "previsto",
          f"previsto {pct(pr_meta)}" if pr_meta is not None else "", antes("pr")),
        m("disp", "Disponibilidade", pv.get("disp"), _barra(disp.get("disp")), float(DISP_OK), f"{DISP_OK}%",
          f"{num(h)} h paradas" if h is not None else "", antes("disp")),
    ]


def _bloco_os(u: dict | None, x: dict | None) -> dict | None:
    """As OS da usina no painel: as abertas, repartidas pelo estado no Fracttal (a barra), e o que pede ação (as tarefas
    atrasadas, as pausadas, as que vencem até amanhã e o plano da semana passada). None = as OS do Fracttal não chegaram
    ao banco: o painel diz "sem leitura", nunca 0."""
    if (x or {}).get("os_abertas") is None:
        return None
    man, mv = (u or {}).get("manutencao") or {}, _valores(u, "manut")

    def n(k):
        return _int(man.get(k)) or 0
    abertas = n("os_abertas")
    partes = [{"chave": c, "rot": rot, "n": n(k)} for k, rot, c in _ESTADOS_OS if n(k)]
    outras = abertas - sum(p["n"] for p in partes)
    if outras > 0 and partes:
        partes.append({"chave": "ou", "rot": "em outro estado", "n": outras})
    for p in partes:
        p["largura"] = round(p["n"] / abertas * 100, 1) if abertas else 0.0
    atr, atr_os, maior = n("atrasadas"), n("atrasadas_os"), _int(man.get("maior_atraso"))
    sub_atr = [f"em {atr_os} OS" if atr_os else "", f"a mais antiga há {maior} d" if maior else ""]
    paradas_agora = len((u or {}).get("paradas_abertas") or ())
    linhas = []
    if paradas_agora:
        linhas.append({"rot": "Parada agora", "txt": str(paradas_agora), "cls": "critico",
                       "sub": "OS de parada aberta" if paradas_agora == 1 else "OS de parada abertas"})
    linhas += [
        {"rot": "Tarefas atrasadas", "txt": str(atr), "cls": ((mv.get("atrasadas") or {}).get("cls") or "alerta") if atr else "ok",
         "sub": " · ".join(s for s in sub_atr if s) if atr else "nenhuma há mais de 10 dias"},
        {"rot": "Tarefas pausadas", "txt": str(n("paradas")), "cls": "alerta" if n("paradas") else "ok",
         "sub": str(man.get("motivo_comum") or "") if n("paradas") else ""},
        {"rot": "Vencem até amanhã", "txt": str(n("vencem")),
         "cls": ((mv.get("vencem") or {}).get("cls") or "neutro") if n("vencem") else "neutro", "sub": ""}]
    semana = None
    prog = n("passada_prog")
    if prog:
        sem = str(man.get("passada") or "")
        semana = {"rot": "Semana passada", "txt": pct(_float(man.get("passada_pct")), 0),
                  "cls": (mv.get("semana") or {}).get("cls") or "neutro", "largura": _barra(man.get("passada_pct")),
                  "sub": f"{n('passada_feitas')} de {prog} tarefas do plano" + (f" · {sem.split('-')[-1]}" if sem else "")}
    return {"abertas": abertas, "partes": partes, "linhas": linhas, "semana": semana}


def os_grupos(man: dict | None, cls_atrasadas: str = "alerta") -> list[dict]:
    """As OS do cartão, o que pede ação primeiro: as atrasadas (a mais antiga primeiro, com os dias e o tipo), as
    pausadas (o motivo, desde quando e quem) e, pelo estado no Fracttal, as que esperam a verificação, as em execução e
    as não iniciadas. [{"chave", "rot", "n", "nota", "tom", "detalhado", "itens": [{"os", "wid", "txt"}]}]; o grupo
    vazio não entra. As listas são as do bloco Manutenção da Visão (`manutencao.tarefas_por_usina`), inteiras: o "e
    mais" abre na tela (Levi, 28/10/2026: "o supervisor deve saber o que é")."""
    from ..campo.manutencao import DIAS_ATRASO
    man = man or {}

    def tipo(t):
        t = str(t or "")
        return _TIPO_TAREFA.get(t, t.replace("_", " "))

    def dm(d):
        s = str(d or "")[:10]
        return f"{s[8:10]}/{s[5:7]}" if len(s) == 10 and s[4] == "-" else s
    out = []
    atr = [{"os": x.get("os"), "wid": x.get("wid"),
            "txt": " · ".join(p for p in (f"há {x['dias']} d" if x.get("dias") is not None else "", tipo(x.get("tipo"))) if p)}
           for x in man.get("todas_atrasadas") or []]
    if atr:
        n = _int(man.get("atrasadas")) or 0
        out.append({"chave": "atrasadas", "rot": "Atrasadas", "n": len(atr), "tom": cls_atrasadas, "detalhado": True,
                    "nota": f"{n} {'tarefa programada' if n == 1 else 'tarefas programadas'} há mais de {DIAS_ATRASO} dias",
                    "itens": atr})
    par = [{"os": x.get("os"), "wid": x.get("wid"),
            "txt": " · ".join(p for p in (str(x.get("motivo") or ""), f"desde {dm(x['desde'])}" if x.get("desde") else "",
                                          str(x.get("quem") or "")) if p)}
           for x in man.get("todas_paradas") or []]
    if par:
        out.append({"chave": "pausadas", "rot": "Pausadas", "n": len(par), "tom": "alerta", "detalhado": True,
                    "nota": "fora da programação, com o motivo", "itens": par})
    for chave, campo, rot, nota in (("verificacao", "os_verificacao", "Esperando a verificação", "feitas, falta aprovar"),
                                    ("execucao", "os_em_execucao", "Em execução", ""),
                                    ("nao_iniciadas", "os_nao_iniciadas", "Não iniciadas", "")):
        itens = [{"os": x.get("os"), "wid": x.get("wid"), "txt": ""} for x in man.get(campo) or []]
        if itens:
            out.append({"chave": chave, "rot": rot, "n": len(itens), "tom": "neutro", "detalhado": False, "nota": nota,
                        "itens": itens})
    return out


def _nivel_cls(n) -> str:
    """A cor de um nível de sujidade ou vegetação (1 a 5) na régua da Limpeza: 5 crítico, 4 atenção, até 3 em dia."""
    return "neutro" if n is None else ("critico" if n >= 5 else ("alerta" if n == 4 else "ok"))


def _faixa(u: dict | None, x: dict | None, cos: dict | None, insights: list | None, resumo: dict) -> list[dict]:
    """O resto do que decide, numa faixa: a última ronda, a sujidade e a vegetação, os chamados, a segurança, o COS e os
    insights. [{rot, txt, cls, sub, secao}] (a de sujidade e vegetação leva `niveis` no lugar do `txt`)."""
    u, x, av = u or {}, x or {}, _valores(u, "acomp")
    r, l, ch = u.get("ronda") or {}, u.get("limpeza") or {}, u.get("chamados") or {}
    out = []
    dias = _int(r.get("dias"))
    out.append({"rot": "Última ronda", "txt": "—" if dias is None else ("hoje" if dias == 0 else f"há {dias} d"),
                "cls": (av.get("ronda") or {}).get("cls") or "neutro",
                "sub": _RONDA_TIPO.get(r.get("tipo"), "") or ("sem ronda lida em 90 dias" if dias is None else ""),
                "secao": "rondas"})
    suj, veg = _int(l.get("sujidade")), _int(l.get("vegetacao"))
    if suj is not None or veg is not None:
        vala = str(l.get("vala") or "").strip()
        out.append({"rot": "Sujidade e vegetação", "txt": "", "cls": (av.get("limpeza") or {}).get("cls") or "neutro",
                    "niveis": [{"rot": "Sujidade", "n": suj, "cls": _nivel_cls(suj)},
                               {"rot": "Vegetação", "n": veg, "cls": _nivel_cls(veg)}],
                    "sub": f"vala {vala.lower()}" if vala and _int(l.get("vala_peso")) else "",
                    "secao": "rondas"})
    n_ch, n_ver, antigo = _int(ch.get("abertos")) or 0, _int(ch.get("verificacao")) or 0, _int(ch.get("mais_antigo"))
    partes = [f"o mais antigo há {antigo} dias" if n_ch and antigo else "", f"{n_ver} em verificação" if n_ver else ""]
    out.append({"rot": "Chamados abertos", "txt": str(n_ch), "cls": ((av.get("chamados") or {}).get("cls") or "alerta") if n_ch else "ok",
                "sub": " · ".join(p for p in partes if p), "secao": "chamados"})
    seg = (resumo or {}).get("seg") or {}
    n_seg = _int(seg.get("n")) or 0
    out.append({"rot": "Segurança", "txt": f"{n_seg} {'pendência' if n_seg == 1 else 'pendências'}" if n_seg else "em dia",
                "cls": seg.get("tom") or "neutro", "sub": seg.get("txt") or "" if n_seg else "PT, extintores e luvas",
                "secao": "seg"})
    meses = (cos or {}).get("por_mes") or []
    cauda = f"{meses[0]['n']} {'normalizada' if meses[0]['n'] == 1 else 'normalizadas'} em {meses[0]['rot']}" if meses else ""
    ocs = x.get("os_cos") or []
    if x.get("estado") == "sem_leitura":
        out.append({"rot": "COS agora", "txt": "—", "cls": "neutro", "sub": "sem leitura agora" + (f" · {cauda}" if cauda else ""),
                    "secao": "cos"})
    else:
        out.append({"rot": "COS agora", "txt": f"{len(ocs)} {'aberta' if len(ocs) == 1 else 'abertas'}",
                    "cls": (ocs[0].get("tom") or "alerta") if ocs else "ok", "sub": cauda, "secao": "cos"})
    if x.get("insights") is None:
        out.append({"rot": "Insights", "txt": "—", "cls": "neutro", "sub": "ainda sendo calculados", "secao": "insights"})
    else:
        vivos = insights or []
        crit = sum(1 for i in vivos if i.get("sev") == "critico")
        out.append({"rot": "Insights", "txt": str(len(vivos)), "cls": "critico" if crit else ("alerta" if vivos else "ok"),
                    "sub": f"{crit} {'crítico' if crit == 1 else 'críticos'}" if crit else ("abertos" if vivos else "nenhum aberto"),
                    "secao": "insights"})
    return out


def painel(u: dict | None, x: dict | None, itens: list[dict], cos: dict | None = None, insights: list | None = None,
           resumo: dict | None = None, anterior: dict | None = None) -> dict:
    """O painel do alto, o visual na frente: {"perf": {"periodo", "medidores"}, "os": o bloco das OS ou None (sem
    leitura), "pend": {"n", "criticos", "alertas"}, "faixa": [...]}. `u` = a linha da Visão do responsável; `x` = a linha
    da lista do Comando; `itens` = `atencao`; `cos` = `cos_historico`; `insights` = os vivos; `resumo` = `resumos`;
    `anterior` = a linha do mês passado de `mes_a_mes`. Os números e as cores são os das telas donas; a barra só existe
    quando há o valor."""
    meta = (u or {}).get("meta") or {}
    cob, mes = _int(meta.get("dias_cob")), _int(meta.get("dias_mes"))
    crit = sum(1 for i in itens or [] if i.get("tom") == "critico")
    return {"perf": {"periodo": f"{cob} de {mes} dias" if cob is not None and mes else "", "medidores": _medidores(u, anterior)},
            "os": _bloco_os(u, x),
            "pend": {"n": len(itens or []), "criticos": crit, "alertas": len(itens or []) - crit},
            "faixa": _faixa(u, x, cos, insights, resumo or {})}


def resumos(u: dict | None, x: dict | None, insights: list | None, cos: dict | None, luvas: dict | None = None,
            pts_aguardando: int = 0, seguranca=(), demandas=(), conversa_n: int = 0) -> dict[str, dict]:
    """O estado de cada cartão numa linha: {secao: {"tom", "txt"}}. É o que a pessoa lê com o cartão fechado; o
    detalhe fica dentro. Os números e as cores são os das telas donas (a Visão do responsável, o COS, a Segurança)."""
    def v(bloco, k):
        return (((u or {}).get(bloco) or {}).get("valores") or {}).get(k) or {}

    def tem(d):
        return d.get("txt") not in (None, "", "—")
    x, u = x or {}, u or {}
    out = {}
    meta, pr, disp = v("perf", "meta"), v("perf", "pr"), v("perf", "disp")
    previsto = str(pr.get("sub") or "").replace("/", "").strip()
    partes = [f"Meta {meta['txt']}" if tem(meta) else "",
              (f"PR {pr['txt']}%" + (f" (previsto {previsto}%)" if previsto else "")) if tem(pr) else "",
              f"Disponibilidade {disp['txt']}" if tem(disp) else ""]
    out["perf"] = {"tom": _pior(meta.get("cls"), pr.get("cls"), disp.get("cls")),
                   "txt": " · ".join(p for p in partes if p) or "Sem meta, PR ou disponibilidade publicados no mês"}

    ocs = x.get("os_cos") or []
    meses = (cos or {}).get("por_mes") or []
    cauda = f"{meses[0]['n']} {'normalizada' if meses[0]['n'] == 1 else 'normalizadas'} em {meses[0]['rot']}" if meses else ""
    if x.get("estado") == "sem_leitura":
        tom, txt = "neutro", "Sem leitura do COS agora"
    elif ocs:
        tom = ocs[0].get("tom") or "alerta"
        txt = f"{len(ocs)} {'aberta' if len(ocs) == 1 else 'abertas'} agora: {ocs[0].get('motivo') or ocs[0].get('rotulo')} {ocs[0].get('ha') or ''}".strip()
    else:
        tom, txt = "ok", "Nenhuma ocorrência aberta"
    out["cos"] = {"tom": tom, "txt": " · ".join(p for p in (txt, cauda) if p)}

    os_, atr, par = v("manut", "os"), v("manut", "atrasadas"), v("manut", "paradas")
    partes = [f"{os_['txt']} OS abertas" if tem(os_) else "Nenhuma OS aberta",
              (f"{atr['txt']} tarefas atrasadas" + (f" (a mais antiga há {atr['sub']})" if atr.get("sub") else "")) if tem(atr)
              else "nenhuma atrasada",
              f"{par['txt']} pausadas" if tem(par) else ""]
    out["os"] = {"tom": _pior(atr.get("cls"), par.get("cls"), v("manut", "vencem").get("cls"), v("manut", "semana").get("cls")),
                 "txt": " · ".join(p for p in partes if p)}

    r, l = u.get("ronda") or {}, u.get("limpeza") or {}
    dias = _int(r.get("dias"))
    partes = [f"Última ronda há {dias} {'dia' if dias == 1 else 'dias'}" if dias is not None else "Sem ronda lida em 90 dias",
              {"longa_pendente": "ronda longa pendente", "nunca": "nunca rondada", "sem_ronda": "sem ronda no prazo"}.get(r.get("tipo"), ""),
              f"sujidade {l['sujidade']}, vegetação {l['vegetacao']}" if l.get("sujidade") not in (None, "") and
              l.get("vegetacao") not in (None, "") else ""]
    out["rondas"] = {"tom": _pior(v("acomp", "ronda").get("cls"), v("acomp", "limpeza").get("cls")),
                     "txt": " · ".join(p for p in partes if p)}

    ch = u.get("chamados") or {}
    n, antigo = _int(ch.get("abertos")) or 0, _int(ch.get("mais_antigo"))
    out["chamados"] = {"tom": _pior(v("acomp", "chamados").get("cls")) if n else "ok",
                       "txt": (f"{n} {'aberto' if n == 1 else 'abertos'}" + (f", o mais antigo há {antigo} dias" if antigo else ""))
                       if n else "Nenhum chamado de garantia aberto"}

    ext = u.get("extintores") or {}
    problemas = []
    venc = _int(ext.get("vencidos")) or 0
    if venc:
        problemas.append((f"{venc} {'extintor vencido' if venc == 1 else 'extintores vencidos'}", "critico"))
    if (luvas or {}).get("situacao") == "sem_luvas":
        problemas.append(("sem luvas na última ronda", "critico"))
    if pts_aguardando:
        problemas.append((f"{pts_aguardando} PT esperando o De acordo", "alerta"))
    for g in seguranca or ():
        if g.get("chave") not in ("pts", "vencidos", "sem_luvas"):
            problemas.append((str(g.get("rot") or ""), "alerta"))
    out["seg"] = ({"tom": _pior(*(t for _p, t in problemas)), "n": len(problemas),
                   "txt": " · ".join(p[:1].upper() + p[1:] if i == 0 else p for i, (p, _t) in enumerate(problemas))}
                  if problemas else {"tom": "ok", "n": 0, "txt": "PT, extintores e luvas sem pendência"})

    if x.get("insights") is None:
        out["insights"] = {"tom": "neutro", "txt": "Ainda sendo calculados"}
    else:
        vivos = insights or []
        crit = sum(1 for i in vivos if i.get("sev") == "critico")
        out["insights"] = {"tom": "critico" if crit else ("alerta" if vivos else "ok"),
                           "txt": (f"{len(vivos)} {'aberto' if len(vivos) == 1 else 'abertos'}" +
                                   (f", {crit} {'crítico' if crit == 1 else 'críticos'}" if crit else "")) if vivos
                           else "Nenhum insight aberto"}

    nd = len(demandas or ())
    vencidas = sum(1 for d in demandas or () if (d.get("estado") or {}).get("vencida"))
    partes = [(f"{nd} {'demanda' if nd == 1 else 'demandas'}" + (f", {vencidas} {'vencida' if vencidas == 1 else 'vencidas'}" if vencidas else ""))
              if nd else "Nenhuma demanda",
              f"{conversa_n} {'mensagem' if conversa_n == 1 else 'mensagens'} na conversa" if conversa_n else "sem conversa"]
    out["demandas"] = {"tom": "critico" if vencidas else ("info" if nd or conversa_n else "neutro"), "txt": " · ".join(partes)}
    return out


# ── mês a mês ───────────────────────────────────────────────────────────────────────────────────────────────────────
def mes_a_mes(metas: dict, disps: dict, hoje: date) -> list[dict]:
    """As linhas do mês a mês, o mais novo primeiro. `metas`: {AAAAMM: a linha de `responsaveis.metas` da usina ou None};
    `disps`: {"AAAA-MM": a de `responsaveis.disponibilidade` ou None}. Mês sem meta nem disponibilidade não entra."""
    ids = {int(k) for k, v in (metas or {}).items() if v} | {int(str(k).replace("-", "")) for k, v in (disps or {}).items() if v}
    out = []
    for mid in sorted(ids, reverse=True):
        m = (metas or {}).get(mid) or {}
        d = (disps or {}).get(f"{mid // 100}-{mid % 100:02d}") or {}
        prod, meta = _float(m.get("prod_kwh")), _float(m.get("meta_kwh"))
        out.append({
            "mes_id": mid, "rot": f"{MESES[mid % 100 - 1]} de {mid // 100}", "curto": MESES[mid % 100 - 1][:3] + f"/{mid // 100 % 100:02d}",
            "parcial": mid == hoje.year * 100 + hoje.month,
            "ating": pct(_float(m.get("atingimento")), 0) if m else "—",
            "ating_largura": _barra(m.get("atingimento"), ESCALA_META) if m else None,
            "ating_cls": _cls_meta(_float(m.get("atingimento"))) if m else "",
            "geracao": f"{num(prod / 1000)} de {num(meta / 1000)} MWh" if prod is not None and meta else "—",
            "pr": pct(_float(m.get("pr"))) if m and m.get("pr") not in (None, "") else "—",
            "pr_meta": pct(_float(m.get("pr_meta"))) if m and m.get("pr_meta") not in (None, "") else "",
            "disp": pct(_float(d.get("disp"))) if d else "—",
            "h_perdidas": f"{num(_float(d.get('h_perdidas')))} h paradas" if d and d.get("h_perdidas") not in (None, "") else "",
            "dias": f"{_int(m.get('dias_cob'))} de {_int(m.get('dias_mes'))} dias" if m and _int(m.get("dias_cob")) is not None
            and _int(m.get("dias_cob")) != _int(m.get("dias_mes")) else ""})
    return out


def _cls_meta(ating) -> str:
    """A cor do atingimento na régua da Visão gerencial (97% e 90%), a de `usinas.faixa_meta`."""
    return {"na_meta": "ok", "atencao": "alerta", "abaixo": "critico", "sem_meta": ""}[CU.faixa_meta(ating)]


# ── o COS ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def tipo_cos(codigo) -> tuple[str, str]:
    """(o tipo em palavras, o tom) de um `tipo_falha` do fato das normalizações ("FALHA_COMUNICACAO"), pela régua de
    Comando > Usinas: comunicação roxo, o que para a usina crítico, o resto atenção."""
    cod = str(codigo or "").strip()
    if not cod or cod == "None":
        return "Ocorrência", "alerta"
    oc = {"tipo_falha": cod.replace("_", " "), "problema": "", "os": "", "tipo_tarefa": ""}
    grupo, _rot = CU.classificar(oc)
    nome = _TIPOS_COS.get(cod) or CU.motivo(oc)
    if nome == oc["tipo_falha"]:          # a régua não conhece: o código em palavras
        nome = cod.replace("_", " ").capitalize()
    return nome, CU.ESTADOS[grupo][1]


def cos_historico(linhas: list[dict] | None, hoje: date, n: int = 6) -> dict:
    """As normalizações da Ronda COS da usina (as linhas do `fato_normalizacao` dela): {"ultimas": as `n` mais novas,
    "por_mes": [{rot, n, parou}] dos meses que há, o mais novo primeiro, "total"}."""
    itens = []
    for r in linhas or []:
        ini = instante(r.get("inicio"))
        if not ini:
            continue
        volta = instante(r.get("normalizado_em"))
        nome, tom = tipo_cos(r.get("tipo_falha"))
        os_ = str(r.get("os") or "").strip()
        itens.append({"quando": ini, "dia": ini.strftime("%d/%m"), "hora": ini.strftime("%H:%M"), "tipo": nome, "tom": tom,
                      "fora": fora_txt(r.get("fora_min")), "parou": str(r.get("geracao_parou") or "") in ("1", "True"),
                      "os": os_ if os_.isdigit() else "", "volta": volta.strftime("%d/%m %H:%M") if volta else "",
                      "fora_escopo": str(r.get("fora_do_escopo_oem") or "") in ("1", "True")})
    itens.sort(key=lambda i: i["quando"], reverse=True)
    meses: dict[int, dict] = {}
    for i in itens:
        k = i["quando"].year * 100 + i["quando"].month
        m = meses.setdefault(k, {"rot": MESES[k % 100 - 1], "n": 0, "parou": 0})
        m["n"] += 1
        m["parou"] += 1 if i["parou"] else 0
    return {"ultimas": itens[:n], "todas": itens, "total": len(itens),
            "por_mes": [meses[k] for k in sorted(meses, reverse=True)][:6]}


# ── a zeladoria ─────────────────────────────────────────────────────────────────────────────────────────────────────
def zeladoria_semanas(linhas: list[dict] | None) -> dict | None:
    """A leitura semanal de sujidade e vegetação da usina (1 a 5; `zeladoria_semana`), da mais velha para a mais nova,
    com os pontos das duas linhas do gráfico (viewBox 0 0 300 78) e a recomendação mais nova. None = sem leitura."""
    sem = []
    for r in sorted(linhas or [], key=lambda r: str(r.get("semana") or "")):
        veg, suj = _int(r.get("vegetacao_nivel")), _int(r.get("sujidade_nivel"))
        if veg is None and suj is None:
            continue
        ini = do_data_id(r.get("data_id_semana"))
        sem.append({"semana": str(r.get("semana") or "")[-3:], "inicio": ini.strftime("%d/%m") if ini else "",
                    "veg": veg, "suj": suj, "vala": str(r.get("vala") or "").strip(), "linha": r})
    if not sem:
        return None
    esq, dir_, topo, base = 14.0, 292.0, 8.0, 60.0
    passo = (dir_ - esq) / max(1, len(sem) - 1)

    def y(nivel):
        return base - (min(5, max(1, nivel)) - 1) * (base - topo) / 4

    def pontos(chave):
        return [{"x": round(esq + i * passo, 1), "y": round(y(s[chave]), 1), "v": s[chave], "semana": s["semana"]}
                for i, s in enumerate(sem) if s[chave] is not None]
    rec = None
    for s in reversed(sem):
        r = s["linha"]
        tipo = str(r.get("recomendacao") or "").strip()
        if tipo in _RECOMENDACAO:
            chave = "sujidade" if tipo == "limpeza_modulos" else "vegetacao"
            sit, quando = str(r.get(f"situacao_{chave}") or ""), do_data_id(r.get(f"data_id_situacao_{chave}"))
            os_ = _int(r.get(f"os_zeladoria_{chave}"))
            txt = {"a_programar": "a programar", "programada": "programada" + (f" para {quando.strftime('%d/%m')}" if quando else ""),
                   "feita": "feita" + (f" em {quando.strftime('%d/%m')}" if quando else "")}.get(sit, "")
            rec = {"tipo": _RECOMENDACAO[tipo], "semana": s["semana"], "situacao": txt, "os": os_,
                   "tom": "ok" if sit == "feita" else ("alerta" if sit == "a_programar" else "info")}
            break
    for s in sem:
        s.pop("linha")
    ult = sem[-1]
    return {"semanas": sem, "suj": pontos("suj"), "veg": pontos("veg"), "ultima": ult, "recomendacao": rec,
            "grades": [{"y": round(y(n), 1), "rot": n} for n in (1, 3, 5)],
            "rotulos": [{"x": round(esq + i * passo, 1), "rot": s["semana"]} for i, s in enumerate(sem)
                        if i % max(1, len(sem) // 6) == 0 or i == len(sem) - 1]}


# ── as rondas ───────────────────────────────────────────────────────────────────────────────────────────────────────
def rondas_resumo(hist: list[dict] | None, n: int = 5) -> dict:
    """As rondas de 90 dias da usina (`visao.historico_usina`): {"total", "curtas", "longas", "ultimas": as `n` mais
    novas com a data, o tipo, o técnico, a duração, o veredito e a leitura de sujidade e vegetação}."""
    rondas = [r for r in hist or [] if not r.get("validada")]
    rondas.sort(key=lambda r: str(r.get("inicio") or r.get("data") or ""), reverse=True)
    ult = []
    for r in rondas[:n]:
        d = do_data_id(str(r.get("data") or "").replace("-", ""))
        ver = r.get("veredito") or ("neutro", "")
        ult.append({"dia": d.strftime("%d/%m") if d else "", "tipo": str(r.get("tipo") or ""), "tecnico": str(r.get("tecnico") or ""),
                    "dur": f"{_int(r.get('dur_min'))} min" if _int(r.get("dur_min")) is not None else "",
                    "tom": ver[0] if ver[0] in ORDEM_TOM else "neutro", "veredito": ver[1],
                    "suj": r.get("sujidade"), "veg": r.get("vegetacao"), "os": _int(r.get("os")),
                    "pendencia": str(r.get("pendencia") or "")})
    return {"total": len(rondas), "curtas": sum(1 for r in rondas if r.get("tipo") == "curta"),
            "longas": sum(1 for r in rondas if r.get("tipo") == "longa"), "ultimas": ult}


# ── os equipamentos com OS aberta ───────────────────────────────────────────────────────────────────────────────────
def equipamentos_abertos(tarefas: list[dict] | None, nomes: dict, chamados: dict, codigo_usina: str = "",
                         n: int = 6) -> dict:
    """As tarefas abertas das OS abertas da usina, por ativo: {"itens": [{codigo, nome, abertas, pausadas, os, tipos,
    chamado, geral}] (o que tem mais tarefa primeiro, até `n`), "mais", "ativos"}. `tarefas` = as linhas do
    `fato_tarefa_os` da usina; `nomes` = {equipamento_id: a descrição do ativo}; `chamados` = {codigo_ativo: o chamado de
    garantia aberto}. A tarefa no ativo que é a própria usina (a preventiva geral) fica como "Usina (geral)"."""
    por: dict[str, dict] = {}
    for t in tarefas or []:
        if str(t.get("estado_tarefa") or "") == "finalizada":
            continue
        cod = str(t.get("codigo_ativo") or "").strip()
        if not cod:
            continue
        e = por.setdefault(cod, {"codigo": cod, "nome": "", "abertas": 0, "pausadas": 0, "os": set(), "tipos": set()})
        e["abertas"] += 1
        e["pausadas"] += 1 if t.get("estado_tarefa") == "pausada" else 0
        if _int(t.get("os")):
            e["os"].add(_int(t.get("os")))
        tipo = str(t.get("tipo_tarefa") or "")
        if tipo:
            e["tipos"].add(_TIPO_TAREFA.get(tipo, tipo.replace("_", " ")))
        e["nome"] = e["nome"] or str(nomes.get(_int(t.get("equipamento_id"))) or "").strip()
    for cod, ch in (chamados or {}).items():      # o ativo só com chamado aberto também aparece
        por.setdefault(cod, {"codigo": cod, "nome": str(ch.get("equip") or ""), "abertas": 0, "pausadas": 0, "os": set(),
                             "tipos": set()})
    usina = str(codigo_usina or "").strip().lower()
    itens = []
    for e in por.values():
        geral = bool(usina) and e["codigo"].lower() == usina
        itens.append({"codigo": e["codigo"], "nome": "Usina (geral)" if geral else (e["nome"] or e["codigo"]),
                      "abertas": e["abertas"], "pausadas": e["pausadas"], "os": sorted(e["os"]),
                      "tipos": sorted(e["tipos"]), "chamado": (chamados or {}).get(e["codigo"]), "geral": geral})
    itens.sort(key=lambda e: (not e["geral"], -(1 if e["chamado"] else 0), -e["abertas"], e["nome"]))
    return {"itens": itens[:n], "mais": max(0, len(itens) - n), "ativos": len(itens)}


# ── a composição ────────────────────────────────────────────────────────────────────────────────────────────────────
def _cheio(v) -> bool:
    return v not in (None, "") and str(v).strip().upper() not in ("N/I", "N/A", "NONE", "-")


def composicao(ficha: dict | None, estrutura: dict | None = None, cliente: str = "") -> list[tuple[str, list[tuple[str, str]]]]:
    """A ficha da usina em grupos, só com o que está preenchido: [(grupo, [(rótulo, valor)])]. `ficha` = a linha do
    cadastro (`cadastro_nexus · usinas`, as colunas em claro); `estrutura` = o `estrutura_usina.resumo` dela."""
    f = ficha or {}

    def txt(k):
        return str(f.get(k)).strip() if _cheio(f.get(k)) else ""

    def n(k, casas=0):
        v = _float(f.get(k))
        return num(v, casas) if v is not None and _cheio(f.get(k)) else ""

    def conj(qtd, fab, mod, pot, unidade):
        partes = " ".join(p for p in (txt(fab), txt(mod)) if p)
        q = n(qtd)
        cab = f"{q} × {partes}" if q and partes else (q or partes)
        p = txt(pot)
        if p and cab:
            cab += f" ({p}{' ' + unidade if _float(p) is not None else ''})"
        return cab
    mob = do_data_id(str(f.get("data_mobilizacao") or "").replace("-", "")[:8])
    grupos = [
        ("Identificação", [
            ("Código", txt("codigo")), ("ID do BD", txt("id_bd")), ("Cliente", cliente), ("Nome SPE", txt("nome_spe")),
            ("Status", txt("status")), ("Tipologia", CU.tipologia(f.get("tipologia"))),
            ("Local", " / ".join(p for p in (txt("cidade"), txt("uf")) if p)), ("Cluster", txt("cluster")),
            ("Base da equipe", txt("base_equipe")),
            ("Mobilizada em", mob.strftime("%d/%m/%Y") if mob else ""),
            ("Contrato", " · ".join(p for p in ("assinado" if txt("contrato_assinado").lower() == "sim" else "",
                                                 f"{n('prazo_meses')} meses" if n("prazo_meses") else "") if p))]),
        ("Potência e conexão", [
            ("Potência contratual", f"{n('potencia_contratual', 2)} MWp" if n("potencia_contratual", 2) else ""),
            ("Potência real", f"{n('potencia_real', 2)} MWp" if n("potencia_real", 2) else ""),
            ("Capacidade instalada", f"{n('capacidade_instalada', 2)} MW" if n("capacidade_instalada", 2) else ""),
            ("Área instalada", f"{n('area_instalada', 1)} ha" if n("area_instalada", 1) else ""),
            ("Concessionária", txt("concessionaria")), ("Tensão de linha", txt("tensao_linha")),
            ("UCs", n("ucs"))]),
        ("Equipamentos", [
            ("Inversores", conj("n_inversores", "fabricante_inversores", "modelo_inversores", "potencia_inversores", "kW")),
            ("Módulos", conj("n_modulos", "fabricante_modulos", "modelo_modulo", "potencia_modulos", "Wp")),
            ("Trackers", " · ".join(p for p in (" ".join(q for q in (txt("fabricante_tracker"), txt("modelo_tracker")) if q),
                                                f"{n('qtd_tcu_motor')} TCU e motores" if _float(f.get("qtd_tcu_motor")) else "") if p)),
            ("Cabines", n("n_cabine")), ("SKID", n("n_skid")), ("QGBT", n("n_qgbt")),
            ("Transformadores", " · ".join(p for p in (n("n_transformador"), txt("tipo_transformador")) if p)),
            ("TR auxiliar", txt("tr_aux"))]),
        ("Acessos e documentos", [
            ("Comando remoto", txt("acesso_comando_remoto")), ("Visualização (monitoramento)", txt("acesso_visualizacao")),
            ("Databook", txt("databook")), ("Internet", txt("prestador_internet"))]),
    ]
    e = estrutura or {}
    if e.get("inversores") or e.get("cabines"):
        grupos.append(("Estrutura no Nexus", [
            ("Cabines", num(e.get("cabines"), 0)), ("Inversores", num(e.get("inversores"), 0)),
            ("Strings esperadas", num(e.get("strings"), 0) if e.get("strings") else ""),
            ("Potência dos inversores", f"{num((e.get('kwp_inversores') or 0) / 1000, 2)} MWp" if e.get("kwp_inversores") else "")]))
    return [(g, [(r, v) for r, v in linhas if v]) for g, linhas in grupos if any(v for _r, v in linhas)]


# ── a linha do tempo ────────────────────────────────────────────────────────────────────────────────────────────────
FONTES = (("cos", "COS"), ("ronda", "Rondas"), ("pt", "PT"), ("chamado", "Chamados"), ("os", "OS"))


def linha_do_tempo(hoje: date, rondas=(), cos=(), pts=(), chamados=(), tarefas=(), dias: int = LINHA_DO_TEMPO_DIAS) -> list[dict]:
    """Os eventos da usina nos últimos `dias`, de todas as fontes numa lista só, por dia (o mais novo primeiro):
    [{"dia": "ter, 10/11", "eventos": [{hora, fonte, tom, titulo, detalhe, os}]}]. `rondas` = o histórico de rondas;
    `cos` = `cos_historico(...)["todas"]`; `pts` = as PT da usina (`visao.pts()["historico"]`); `chamados` = as linhas do
    `fato_chamado` da usina; `tarefas` = as do `fato_tarefa_os` (a OS aberta entra no dia em que foi criada)."""
    desde = hoje - timedelta(days=dias)
    evs = []

    def ev(quando, fonte, tom, titulo, detalhe="", os_=None, com_hora=True):
        if not quando:
            return
        d = quando.date() if isinstance(quando, datetime) else quando
        if d < desde or d > hoje:
            return
        evs.append({"d": d, "ordem": quando.strftime("%H:%M") if isinstance(quando, datetime) and com_hora else "",
                    "hora": quando.strftime("%H:%M") if isinstance(quando, datetime) and com_hora else "",
                    "fonte": fonte, "tom": tom, "titulo": titulo, "detalhe": detalhe, "os": os_})
    for r in rondas or []:
        if r.get("validada"):
            continue
        ver = r.get("veredito") or ("neutro", "")
        leitura = " · ".join(p for p in (f"sujidade {r['sujidade']}" if r.get("sujidade") not in (None, "") else "",
                                         f"vegetação {r['vegetacao']}" if r.get("vegetacao") not in (None, "") else "",
                                         f"{_int(r.get('dur_min'))} min" if _int(r.get("dur_min")) is not None else "",
                                         str(r.get("pendencia") or "")) if p)
        ev(instante(r.get("inicio")) or do_data_id(str(r.get("data") or "").replace("-", "")), "ronda",
           ver[0] if ver[0] in ORDEM_TOM else "neutro",
           f"Ronda {r.get('tipo') or ''}".strip() + (f" · {r['tecnico']}" if r.get("tecnico") else ""), leitura, _int(r.get("os")))
    for c in cos or []:
        ev(c["quando"], "cos", c["tom"], c["tipo"] + (" (a geração parou)" if c["parou"] else ""),
           " · ".join(p for p in (f"fora {c['fora']}" if c["fora"] else "", f"voltou {c['volta']}" if c["volta"] else "") if p),
           _int(c["os"]))
    for p in pts or []:
        sit = str(p.get("situacao") or "")
        ev(instante(str(p.get("criada") or "").replace(" ", "T", 1)), "pt", "ok" if sit == "de_acordo" else "alerta",
           f"PT {_SITUACAO_PT.get(sit, sit.replace('_', ' '))}".strip() + (f" · {p['solicitante']}" if p.get("solicitante") else ""),
           str(p.get("tarefa") or ""), _int(p.get("os")))
    for c in chamados or []:
        nome = str(c.get("equip") or c.get("codigo_ativo") or "").strip()
        fab = str(c.get("fabricante") or "").strip()
        det = " · ".join(p for p in (nome, fab) if p)
        ev(do_data_id(c.get("data_id_abertura")), "chamado", "alerta", "Chamado de garantia aberto", det, _int(c.get("os")))
        ev(do_data_id(c.get("data_id_fim")), "chamado", "ok", "Chamado de garantia concluído", det, _int(c.get("os")))
    vistas = {}
    for t in tarefas or []:
        n = _int(t.get("os"))
        d = do_data_id(t.get("data_id_criacao"))
        if n and d and (n not in vistas or d < vistas[n][0]):
            vistas[n] = (d, str(t.get("tipo_tarefa") or ""))
    citadas = {e["os"] for e in evs if e["os"]}        # a OS da ronda, da PT e do COS já está na linha do evento dela
    for n, (d, tipo) in vistas.items():
        if n not in citadas:
            ev(d, "os", "neutro", f"OS {n} aberta", _TIPO_TAREFA.get(tipo, tipo.replace("_", " ")) + " · segue aberta", n)
    evs.sort(key=lambda e: (e["d"], e["ordem"]), reverse=True)
    out, atual = [], None
    for e in evs:
        if atual is None or atual["data"] != e["d"]:
            atual = {"data": e["d"], "dia": dia_txt(e["d"]), "eventos": []}
            out.append(atual)
        atual["eventos"].append({k: e[k] for k in ("hora", "fonte", "tom", "titulo", "detalhe", "os")})
    return out
