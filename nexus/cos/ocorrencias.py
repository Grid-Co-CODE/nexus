"""Ocorrências (22/10/2026): cada ocorrência cumpriu as cinco etapas no prazo?

A spec R04 do Fillipe ("COS como visão global") define o ciclo da ocorrência em cinco etapas: detectada → cliente
informado (até 15 min) → campo acionado (até 30 min) → normalizada → encerrada. O Andamento da Ronda COS diz QUANDO cada
etapa aconteceu e por qual caminho (`GET /api/nexus/<cliente>/ocorrencias`, lido em `andamento.ler_ocorrencias`); o prazo
e o veredito são daqui, porque a spec mora no Nexus.

O que o Andamento já separou, e esta tela não junta de volta:
- o aviso ao cliente conta só o que foi ao grupo DO CLIENTE (o flash ou a fotografia que nomeou a ocorrência);
- a entrada automática em "Técnico acionado" (o escalonamento da Ronda COS quando a tratativa remota passa do tempo) não é
  ninguém acionando o campo: fica à parte, em âmbar, e não conta como cumprido nem como perdido.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit

from . import andamento as AND
from . import normalizacoes as NO

# "Todos os clientes" (11/11/2026, pedido da Ana Barros: "a visão consolidada"): o valor do `?cliente=` que junta as
# ocorrências de todos os clientes do Andamento numa tabela só. Nenhum cliente do Andamento se chama assim.
TODOS = "todos"
# A ocorrência sem hora de registro vai para o fim da tabela juntada.
_NUNCA = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Prazo:
    minutos: int
    porque: str
    # O prazo em palavras, para as telas (11/11/2026: o do aviso deixou de ser um número só).
    texto: str = ""


# Os prazos da spec R04 (Nexus, "COS como visão global": o ciclo da ocorrência em cinco etapas). Um lugar só.
PRAZOS = {
    "informado": Prazo(15, "R04: o cliente fica sabendo da ocorrência em até 15 min",
                       "15 min (desligamento, que vai no flash) ou 60 min (o resto, que vai na fotografia)"),
    "campo": Prazo(30, "R04: o campo é acionado em até 30 min", "30 min"),
}

# ⚠ OS TIPOS QUE VÃO AO CLIENTE PELO FLASH, e por isso têm os 15 min (11/11/2026, decisão do dono: "segue, com prazo de
# 60 min para os da fotografia"). É a regra do Andamento (`regras/flash.ts`, TIPOS_DO_FLASH_DA_RONDA_COS: a fonte das
# ocorrências é a Ronda COS desde 19/10/2026): o desligamento de usina, cabine, QGBT, SKID e inversor. Os outros tipos
# (falha de comunicação, inversor offline, string, tracker...) só chegam ao cliente na fotografia de hora em hora — os
# 15 min eram impossíveis por desenho (em 30 dias, 86 falhas de comunicação e 11 inversores offline "fora" só por isso),
# e eles são julgados pela fotografia seguinte: 60 min. Sem o código do tipo (Andamento antigo), os 15 min de antes.
TIPOS_COM_FLASH = frozenset({"DESLIGAMENTO_USINA", "DESLIGAMENTO_CABINE", "DESLIGAMENTO_QGBT", "DESLIGAMENTO_SKID",
                             "DESLIGAMENTO_INVERSOR"})
PRAZO_DA_FOTOGRAFIA = 60


def prazo_do_aviso(o: dict) -> int:
    """O prazo do aviso ao cliente desta ocorrência: 15 min se o tipo vai no flash, 60 se só vai na fotografia."""
    codigo = o.get("tipo_falha_codigo")
    if codigo and codigo not in TIPOS_COM_FLASH:
        return PRAZO_DA_FOTOGRAFIA
    return PRAZOS["informado"].minutos


# ⚠ DE ONDE OS PRAZOS CONTAM: DE QUANDO O COS VIU A FALHA (11/11/2026, decisão do dono). Até ali contavam do INÍCIO da
# falha, escolha minha de 22/10 sem decisão do dono, e o placar dizia "27% informado no prazo" com 520 dos 530 "fora"
# avisados — a falha levava 25 min (mediana) até ser registrada, e o cliente era avisado ~2 min depois da abertura da
# OS. A spec R04 diz "detectada → cliente informado em 15 min": o relógio é a detecção.
# - `detectada_em`: a hora em que o COS viu, digitada por quem abre o desvio na tela (desde 03/11/2026);
# - sem ela, `registrada_em`: a hora em que a Ronda COS registrou — na ocorrência que veio do Fracttal pela sincronização,
#   DEPOIS de alguém ter visto, e por isso o número sai melhor do que foi (cada linha diz qual relógio valeu);
# - sem as duas, o início.
# A demora até o COS ver NÃO some: é a etapa "Detectada" (do início) e o número "Até o COS ver" do placar.
# `CONTA_DE` continua sendo o INÍCIO da falha: é o relógio da Detectada, da Normalizada (o tempo fora), do turno e do
# MTTA do Desempenho, que não mudaram.
CONTA_DE = "inicio"
RELOGIO = "momento em que o COS viu a falha (sem essa hora, do registro na Ronda COS)"
BASES = {"detectada": "da hora em que o COS viu", "registro": "do registro na Ronda COS", "inicio": "do início da falha"}


def quando_o_cos_viu(o: dict) -> tuple[datetime | None, str]:
    """O relógio dos prazos (ver acima) e qual valeu: "detectada", "registro" ou "inicio"."""
    for campo, base in (("detectada_em", "detectada"), ("registrada_em", "registro"), ("inicio", "inicio")):
        t = AND.instante(o.get(campo))
        if t:
            return t, base
    return None, ""

# A Ronda COS (a plataforma) atende no mesmo servidor do Andamento, na porta 3000: o link "abrir na Ronda COS" sai do
# endereço do Andamento, como o painel do próprio Andamento faz. O endereço não entra no repositório.
PORTA_DA_PLATAFORMA = 3000

ETAPAS = (
    ("detectada", "Detectada"),
    ("informado", "Cliente informado"),
    ("campo", "Campo acionado"),
    ("normalizada", "Normalizada"),
    ("encerrada", "Encerrada"),
)

# Como cada veredito conta no placar.
CUMPRIU = {"no_prazo"}
NAO_CUMPRIU = {"fora", "atrasada", "nao_informado"}
PENDENTE = {"pendente"}

SITUACOES = {
    "abertas": "Abertas",
    "fora": "Fora do prazo",
    "pendentes": "Correndo o prazo",
    "automatico": "Só o escalonamento automático",
}

ORIGENS = {
    "pessoa": "por pessoa",
    "sistema": "automático",
    "fracttal": "pelo Fracttal",
    "criacao_da_os": "OS com religamento local",
    "religamento_remoto": "religamento remoto",
}

SEVERIDADE_TOM = {"CRITICO": "critico", "ALTO": "alerta", "MEDIO": "info", "BAIXO": "neutro"}


@dataclass
class Etapa:
    estado: str          # no_prazo, fora, pendente, atrasada, nao_informado, nao_precisou, so_automatico, sem_campo, ...
    rotulo: str          # a hora, ou a palavra ("aguardando", "não avisado")
    tom: str = "neutro"  # ok, critico, alerta, info, neutro (cn-pill / cn-t-*)
    detalhe: str = ""


@dataclass
class Linha:
    o: dict
    usina: str
    equipamentos: str
    tipo: str
    severidade: str
    severidade_tom: str
    estado: str
    os: str
    link_plataforma: str
    etapas: dict = field(default_factory=dict)
    # O cliente da ocorrência — a coluna que aparece em "Todos os clientes" e no CSV.
    cliente: str = ""
    # De qual relógio os prazos contaram (`quando_o_cos_viu`): "detectada", "registro" ou "inicio".
    relogio: str = ""


@dataclass
class Painel:
    itens: list
    total: int
    contagem: dict
    resumo: dict
    envio: dict
    desde: datetime | None
    gerado_em: datetime | None
    truncado: bool
    # As opções de cada filtro, com quantas ocorrências cada uma tem no período (11/11/2026, ver `FILTROS`).
    opcoes: dict = field(default_factory=dict)


def duracao(minutos: float) -> str:
    """6 min · 1 h 02 · 2 d 3 h."""
    m = max(0, int(minutos))
    if m < 60:
        return f"{m} min"
    if m < 48 * 60:
        return f"{m // 60} h {m % 60:02d}"
    return f"{m // 1440} d {(m % 1440) // 60} h"


def hora(t: datetime | None, agora: datetime) -> str:
    if not t:
        return "—"
    return t.strftime("%H:%M") if t.date() == agora.date() else t.strftime("%d/%m %H:%M")


def _min(a: datetime, b: datetime) -> int:
    """Os minutos INTEIROS de a até b. O prazo se compara assim, como a tela mostra: o início é digitado em minutos, e
    "em 30 min (prazo 30 min)" lido como fora do prazo por causa de segundos seria a tela se contradizendo."""
    return int((b - a).total_seconds() // 60)


def link_da_plataforma(url_do_andamento: str, registro: str) -> str:
    """O Console da Ronda COS com a ocorrência aberta, no mesmo servidor do Andamento (porta 3000)."""
    try:
        p = urlsplit(url_do_andamento)
    except ValueError:
        return ""
    if not p.scheme or not p.hostname or not registro:
        return ""
    return f"{p.scheme}://{p.hostname}:{PORTA_DA_PLATAFORMA}/console?registro={quote(registro, safe='')}"


def _do_registro(base: str) -> str:
    """O aviso, na linha, de que o relógio foi o registro (e não a hora em que o COS viu)."""
    return " · do registro" if base == "registro" else (" · do início" if base == "inicio" else "")


def _informado(o: dict, origem: datetime | None, envio: dict, agora: datetime, base: str = "") -> Etapa:
    """O cliente informado no prazo: `origem` é a hora em que o COS viu (`quando_o_cos_viu`), e o prazo é o do tipo
    (`prazo_do_aviso`: 15 min no flash, 60 na fotografia)."""
    prazo = prazo_do_aviso(o)
    if o.get("estado") == "DETECTADO":
        return Etapa("nao_medido", "—", detalhe="alarme ainda não confirmado: não vai ao cliente")
    if not origem:
        return Etapa("nao_medido", "—", detalhe="sem a hora em que o COS viu")
    desde = AND.instante(envio.get("desde"))
    if envio.get("grupos") == "nenhum":
        return Etapa("nao_medido", "—", detalhe="o Andamento não manda a este cliente")
    if not desde:
        return Etapa("nao_medido", "—", detalhe="o Andamento ainda não mandou nada a este cliente")
    if origem < desde:
        return Etapa("nao_medido", "—", detalhe="antes de o Andamento mandar ao cliente")
    # O religamento remoto vai ao cliente SÓ pelo aviso da volta (decisão do dono, 21/10/2026: "pode ser só a
    # normalização"): quando a volta foi avisada antes de a ocorrência ser, é ali que o cliente soube dela.
    aviso, da_volta = o.get("cliente_informado"), False
    volta = o.get("volta_informada")
    if volta and not o.get("aberta") and AND.instante(volta.get("em")) and (
            not aviso or AND.instante(volta.get("em")) < (AND.instante(aviso.get("em")) or AND.instante(volta.get("em")))):
        aviso, da_volta = volta, True
    em = AND.instante(aviso.get("em")) if aviso else None
    if em:
        m = _min(origem, em)
        via = ("flash" if aviso.get("por") == "flash" else "fotografia") + (" da volta" if da_volta else "")
        if m <= prazo:
            return Etapa("no_prazo", hora(em, agora), "ok", f"{via} · em {duracao(m)}{_do_registro(base)}")
        return Etapa("fora", hora(em, agora), "critico",
                     f"{via} · em {duracao(m)} (prazo {prazo} min){_do_registro(base)}")
    sem_os = "ainda sem OS: o Andamento só nomeia ao cliente a ocorrência com OS" if not o.get("os") else ""
    if not o.get("aberta"):
        return Etapa("nao_informado", "não avisado", "critico", sem_os or "fechou sem aviso ao cliente")
    m = _min(origem, agora)
    if m <= prazo:
        return Etapa("pendente", "aguardando", "info", f"faltam {duracao(prazo - m)}")
    return Etapa("atrasada", "não avisado", "critico", sem_os or f"há {duracao(m)} (prazo {prazo} min)")


def _campo(o: dict, origem: datetime | None, agora: datetime, base: str = "") -> Etapa:
    """O campo acionado no prazo, contado de quando o COS viu (`quando_o_cos_viu`)."""
    prazo = PRAZOS["campo"].minutos
    c = o.get("campo") or {}
    acionado = AND.instante(c.get("acionado_em"))
    if not origem:
        return Etapa("nao_medido", "—", detalhe="sem a hora em que o COS viu")
    if acionado:
        m = _min(origem, acionado)
        quem = ORIGENS.get(c.get("acionado_por") or "", "")
        if m <= prazo:
            return Etapa("no_prazo", hora(acionado, agora), "ok", f"{quem} · em {duracao(m)}{_do_registro(base)}")
        return Etapa("fora", hora(acionado, agora), "critico",
                     f"{quem} · em {duracao(m)} (prazo {prazo} min){_do_registro(base)}")
    escalonado = AND.instante(c.get("escalonado_em"))
    if escalonado:
        return Etapa("so_automatico", "só automático", "alerta",
                     f"escalonado pela Ronda COS às {hora(escalonado, agora)}, sem acionamento registrado por pessoa")
    if not o.get("aberta"):
        n = o.get("normalizada") or {}
        volta = AND.instante(n.get("fim")) or AND.instante(n.get("declarada_em"))
        if volta and _min(origem, volta) <= prazo:
            return Etapa("nao_precisou", "não precisou", detalhe=f"normalizada em {duracao(_min(origem, volta))}")
        if volta:
            return Etapa("sem_campo", "sem campo", "alerta", f"normalizada em {duracao(_min(origem, volta))}, sem acionamento")
        return Etapa("nao_precisou", "não precisou", detalhe="fechou sem ir a campo")
    m = _min(origem, agora)
    if m <= prazo:
        return Etapa("pendente", "aguardando", "info", f"faltam {duracao(prazo - m)}")
    return Etapa("atrasada", "sem campo", "critico", f"há {duracao(m)} (prazo {prazo} min)")


def _detectada(o: dict, origem: datetime | None, agora: datetime) -> Etapa:
    """A etapa Detectada, contada do INÍCIO da falha: é aqui que a demora até o COS ver aparece (11/11/2026: desde que
    os prazos contam de quando o COS viu, ela não está mais dentro deles)."""
    reg = AND.instante(o.get("registrada_em"))
    viu = AND.instante(o.get("detectada_em"))
    partes = []
    if origem and viu and _min(origem, viu) >= 1:
        partes.append(f"COS viu {duracao(_min(origem, viu))} depois")
    if origem and reg and _min(origem, reg) >= 1:
        partes.append(f"registrada {duracao(_min(origem, reg))} depois")
    os_em = AND.instante(o.get("os_aberta_em"))
    if os_em:
        partes.append(f"OS aberta {hora(os_em, agora)}")
    elif not o.get("os"):
        partes.append("sem OS")
    return Etapa("feita", hora(origem, agora), detalhe=" · ".join(partes))


def _normalizada(o: dict, origem: datetime | None, agora: datetime) -> Etapa:
    n = o.get("normalizada")
    if not n:
        if o.get("aberta") and origem:
            return Etapa("aberta", "aberta", "info", f"há {duracao(_min(origem, agora))}")
        return Etapa("aberta", "aberta", "info")
    fim = AND.instante(n.get("fim"))
    declarada = AND.instante(n.get("declarada_em"))
    partes = []
    if origem and fim:
        partes.append(f"fora {duracao(_min(origem, fim))}")
    if declarada:
        partes.append(f"declarada {hora(declarada, agora)} {ORIGENS.get(n.get('por') or '', '')}".strip())
    volta = o.get("volta_informada")
    if volta and AND.instante(volta.get("em")):
        partes.append(f"cliente avisado {hora(AND.instante(volta['em']), agora)}")
    return Etapa("feita", hora(fim or declarada, agora), "ok", " · ".join(partes))


def _encerrada(o: dict, agora: datetime) -> Etapa:
    enc = AND.instante(o.get("encerrada_em"))
    if enc:
        return Etapa("feita", hora(enc, agora), "ok")
    if o.get("normalizada"):
        return Etapa("aguardando", "aguardando", detalhe="a OS ainda não foi finalizada")
    return Etapa("aberta", "—")


def linha(o: dict, envio: dict, agora: datetime, url_do_andamento: str = "", cliente: str = "") -> Linha:
    # Dois relógios (11/11/2026): o INÍCIO da falha para a Detectada e a Normalizada; QUANDO O COS VIU para os prazos.
    origem = AND.instante(o.get(CONTA_DE))
    viu, base = quando_o_cos_viu(o)
    sev = o.get("severidade") or ""
    return Linha(
        o=o,
        cliente=cliente,
        relogio=base,
        usina=o.get("usina") or o.get("usina_codigo") or "",
        equipamentos=", ".join(o.get("equipamentos") or []),
        tipo=o.get("tipo_falha") or "Ocorrência",
        severidade=o.get("severidade_rotulo") or "",
        severidade_tom=SEVERIDADE_TOM.get(sev, "neutro"),
        estado=o.get("estado_rotulo") or o.get("estado") or "",
        os=str(o["os"]) if o.get("os") else "",
        link_plataforma=link_da_plataforma(url_do_andamento, o.get("registro") or ""),
        etapas={
            "detectada": _detectada(o, origem, agora),
            "informado": _informado(o, viu, envio, agora, base),
            "campo": _campo(o, viu, agora, base),
            "normalizada": _normalizada(o, origem, agora),
            "encerrada": _encerrada(o, agora),
        },
    )


def _resumo(linhas: list, etapa: str) -> dict:
    estados = [x.etapas[etapa].estado for x in linhas]
    cumpriu = sum(e in CUMPRIU for e in estados)
    nao = sum(e in NAO_CUMPRIU for e in estados)
    medidas = cumpriu + nao
    return {
        "cumpriu": cumpriu,
        "nao_cumpriu": nao,
        "pendente": sum(e in PENDENTE for e in estados),
        "automatico": sum(e == "so_automatico" for e in estados),
        "medidas": medidas,
        "pct": round(100 * cumpriu / medidas) if medidas else None,
    }


def _deteccao(linhas: list) -> dict:
    """ATÉ O COS VER A FALHA (11/11/2026): a mediana do início da falha à hora em que o COS viu, só onde ela foi
    digitada (`detectada_em`). É a demora que saiu de dentro dos prazos quando eles passaram a contar da detecção — e que
    não pode sumir da tela. `sem` conta as que não têm a hora (vieram do sync, de carga ou de antes de 03/11/2026)."""
    ms = []
    for x in linhas:
        ini, viu = AND.instante(x.o.get("inicio")), AND.instante(x.o.get("detectada_em"))
        if ini and viu:
            ms.append(max(0.0, (viu - ini).total_seconds() / 60))
    ms.sort()
    return {"mediana": duracao(ms[len(ms) // 2]) if ms else "—", "n": len(ms), "sem": len(linhas) - len(ms)}


def _na_situacao(x: Linha, situacao: str) -> bool:
    etapas = (x.etapas["informado"].estado, x.etapas["campo"].estado)
    if situacao == "abertas":
        return bool(x.o.get("aberta"))
    if situacao == "fora":
        return any(e in NAO_CUMPRIU for e in etapas)
    if situacao == "pendentes":
        return any(e in PENDENTE for e in etapas)
    if situacao == "automatico":
        return etapas[1] == "so_automatico"
    return True


def painel(leitura, agora: datetime, situacao: str = "", url_do_andamento: str = "",
           filtros: dict | None = None) -> Painel | None:
    """O que a tela mostra: as linhas (filtradas pela situação), as contagens de cada situação (antes do filtro de
    situação) e o placar das duas etapas com prazo.

    `leitura` é a de um cliente ou, desde 11/11/2026, a LISTA das leituras de todos ("Todos os clientes"): cada
    ocorrência é julgada com o `envio_ao_cliente` do PRÓPRIO cliente (desde quando ele recebe), e a tabela junta todas,
    da registrada mais recente para a mais antiga. A leitura que falhou fica de fora (o aviso de erro é da tela).

    `filtros` (11/11/2026, os da tela Normalizações — ver `FILTROS`): recortam ANTES de tudo, e o placar, os números e as
    situações contam o recorte, como a faixa das Normalizações conta a lista filtrada. As opções de cada filtro contam o
    período inteiro, antes dos filtros (um contador que encolhe ao filtrar não diz mais quanto existe)."""
    leituras = list(leitura) if isinstance(leitura, (list, tuple)) else [leitura]
    validas = [x for x in leituras if x and x.dados]
    if not validas:
        return None
    todas = []
    for lei in validas:
        d = lei.dados
        envio = d.get("envio_ao_cliente") or {}
        cliente = d.get("cliente") or getattr(lei, "cliente", "") or ""
        todas += [linha(o, envio, agora, url_do_andamento, cliente) for o in d.get("ocorrencias") or []]
    if len(validas) > 1:
        todas.sort(key=lambda x: AND.instante(x.o.get("registrada_em")) or _NUNCA, reverse=True)
    um = validas[0].dados if len(validas) == 1 else None
    desdes = [t for t in (AND.instante(x.dados.get("desde")) for x in validas) if t]
    gerados = [t for t in (AND.instante(x.dados.get("gerado_em")) for x in validas) if t]
    f = filtros_pedidos(filtros or {})
    recorte = [x for x in todas if _no_filtro(x, f)]
    return Painel(
        itens=[x for x in recorte if _na_situacao(x, situacao)],
        total=len(recorte),
        contagem={s: sum(_na_situacao(x, s) for x in recorte) for s in SITUACOES},
        resumo={"informado": _resumo(recorte, "informado"), "campo": _resumo(recorte, "campo"),
                "deteccao": _deteccao(recorte)},
        envio=(um.get("envio_ao_cliente") or {}) if um else {},
        desde=min(desdes) if desdes else None,
        gerado_em=min(gerados) if gerados else None,
        truncado=any(bool(x.dados.get("truncado")) for x in validas),
        opcoes=_opcoes(todas),
    )


# ── Os filtros (11/11/2026) ───────────────────────────────────────────────────────────────────────────────────────────
# Pedido da Ana Barros: "os filtros que existem em Normalizações, tipo de falha, cliente, usina, criado por, tecnico,
# status fracttal, lupa de pesquisa". Os MESMOS nomes de parâmetro da tela Normalizações (`falha`, `usina`,
# `criado_por`, `tecnico`, `status`, `q`), para o endereço de uma valer na outra. O cliente é a aba de cima ("Todos os
# clientes" ou um). "Criado por" e "Técnico" são os dois nomes que a Ronda COS manda (os da API das normalizações).
FILTROS = ("falha", "usina", "criado_por", "tecnico", "status", "q")
STATUS_FILTRO = {**NO.STATUS_FILTRO, "sem_os": "Sem OS"}
BUSCA_MAX = NO.BUSCA_MAX


def filtros_pedidos(args) -> dict:
    """Os filtros válidos de um pedido (`request.args` ou um dict): o status fora das opções e a busca longa demais não
    passam — o mesmo trato da tela Normalizações."""
    f = {k: " ".join(str(args.get(k) or "").split()) for k in FILTROS}
    if f["status"] not in STATUS_FILTRO:
        f["status"] = ""
    f["q"] = f["q"][:BUSCA_MAX]
    return f


# A OS que ainda não chegou ao espelho das abertas (checkup do COS, 12/11/2026). A varredura do Fracttal na Ronda COS roda
# de 30 em 30 min; fora do espelho, a tela dizia "Fechada" — e a OS 19377 da Nova Londrina 1, aberta às 10:13, aparecia
# fechada às 10:19 (5 casos assim naquela leitura). A aberta há menos de OS_NOVA_MIN ainda está "Nova".
OS_NOVA_MIN = 40


def _os_nova(o: dict) -> bool:
    aberta = AND.instante(o.get("os_aberta_em"))
    return bool(aberta and AND.agora() - aberta < timedelta(minutes=OS_NOVA_MIN))


def status_filtro(o: dict) -> str:
    """A chave do status da OS para o filtro: processo, verificacao, fechada (fora do espelho das abertas) ou sem_os. A
    nova, que a varredura ainda não viu, conta como em processo."""
    if not o.get("os"):
        return "sem_os"
    f = o.get("os_fracttal")
    if not f:
        return "processo" if _os_nova(o) else "fechada"
    return {1: "processo", 2: "verificacao"}.get(f.get("status"), "")


def alvo_da_busca(x: Linha) -> str:
    """O texto em que a lupa procura: a OS, o cliente, a usina, a falha, os equipamentos, os dois nomes, o que
    aconteceu (causa, ação, informe, descrição, notas) e o status — como a busca da tela Normalizações."""
    o = x.o
    return " ".join([x.os, x.cliente, x.usina, o.get("usina_codigo") or "", x.tipo, x.equipamentos,
                     o.get("os_aberta_por") or "", o.get("tecnico") or "", (o.get("causa") or {}).get("rotulo") or "",
                     o.get("acao") or "", o.get("informe") or "", status_da_os(o), o.get("descricao") or "",
                     *(o.get("notas") or [])]).lower()


def _no_filtro(x: Linha, f: dict) -> bool:
    o = x.o
    if f["falha"] and x.tipo != f["falha"]:
        return False
    if f["usina"] and x.usina != f["usina"]:
        return False
    if f["criado_por"] and (o.get("os_aberta_por") or "") != f["criado_por"]:
        return False
    if f["tecnico"] and (o.get("tecnico") or "") != f["tecnico"]:
        return False
    if f["status"] and status_filtro(o) != f["status"]:
        return False
    q = f["q"].lower()
    if q and not (q.isdigit() and x.os == q) and q not in alvo_da_busca(x):
        return False
    return True


def _opcoes(todas: list) -> dict:
    """As opções de cada filtro, com a contagem do período inteiro (antes dos filtros)."""
    def conta(valores):
        return dict(sorted(Counter(v for v in valores if v).items()))
    return {
        "falha": dict(Counter(x.tipo for x in todas).most_common()),
        "usina": conta(x.usina for x in todas),
        "criado_por": conta(x.o.get("os_aberta_por") for x in todas),
        "tecnico": conta(x.o.get("tecnico") for x in todas),
        "status": {k: sum(1 for x in todas if status_filtro(x.o) == k) for k in STATUS_FILTRO},
    }


# ── O que aconteceu (11/11/2026) ──────────────────────────────────────────────────────────────────────────────────────
# Pedido da Ana Barros: "ajustarmos a visão da aba de ocorrências pra ficar similar a de normalizações (com
# possibilidade de exportação) … não consigo exportar ou ver de bate pronto qq rolou". O Andamento manda, por
# ocorrência, a descrição (sem o planejamento do PCM), a "Ação:" do molde, as notas de pessoa (sem autor nem hora), a
# causa escolhida pelo COS, o resumo do informe e a OS no espelho do Fracttal — o MESMO corte da API das normalizações.
# Andamento antigo, sem os campos: tudo vazio, e a tela segue como era.

def status_da_os(o: dict) -> str:
    """O status da OS no Fracttal, com as palavras da tela Normalizações: "Em processo", "Em verificação" — ou "Fechada"
    quando a OS não está mais no espelho das abertas. Sem OS, vazio."""
    if not o.get("os"):
        return ""
    f = o.get("os_fracttal")
    if not f:
        return "Nova" if _os_nova(o) else "Fechada"
    return NO.STATUS_OS.get(f.get("status"), (f"status {f.get('status')}", ""))[0]


def o_que_aconteceu(o: dict) -> str:
    """A linha curta do que aconteceu, para ler de bate pronto: a causa, a ação e o resumo do informe, nesta ordem."""
    causa = (o.get("causa") or {}).get("rotulo") or ""
    partes = [causa, o.get("acao") or "", o.get("informe") or ""]
    return " · ".join(p.strip() for p in partes if p and p.strip())


CSV_COLUNAS = ("Cliente", "OS", "Usina", "Código da usina", "Equipamentos", "Falha", "Severidade", "Estado", "Aberta",
               "Início", "Registrada", "Detectada pelo COS", "Cliente informado", "Prazo do aviso", "Campo acionado",
               "Prazo do campo", "Normalizada", "Encerrada", "Causa", "Ação", "Informe", "Aberta por (operador)",
               "Técnico", "Status no Fracttal", "% concluída", "Descrição da ocorrência", "Notas")


def csv_linhas(p: Painel) -> list[list]:
    """As linhas do CSV, na ordem da tabela e com o filtro da tela. A hora sai em Brasília, como na tela."""
    def h(campo, o):
        t = AND.instante(o.get(campo))
        return t.strftime("%d/%m/%Y %H:%M") if t else ""

    linhas = []
    for x in p.itens:
        o = x.o
        f = o.get("os_fracttal") or {}
        norm = o.get("normalizada") or {}
        linhas.append([
            x.cliente, x.os, x.usina, o.get("usina_codigo") or "", x.equipamentos, x.tipo, x.severidade, x.estado,
            "sim" if o.get("aberta") else "não", h("inicio", o), h("registrada_em", o), h("detectada_em", o),
            x.etapas["informado"].rotulo, x.etapas["informado"].estado, x.etapas["campo"].rotulo,
            x.etapas["campo"].estado, h("fim", norm), h("encerrada_em", o), (o.get("causa") or {}).get("rotulo") or "",
            o.get("acao") or "", o.get("informe") or "", o.get("os_aberta_por") or "", o.get("tecnico") or "",
            status_da_os(o), f.get("concluida_pct", "") if f else "", o.get("descricao") or "",
            " | ".join(o.get("notas") or []),
        ])
    return linhas


def dias_pedidos(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return AND.DIAS_PADRAO
    return n if n in AND.DIAS_DAS_OCORRENCIAS else AND.DIAS_PADRAO
