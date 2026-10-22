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
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote, urlsplit

from . import andamento as AND


@dataclass(frozen=True)
class Prazo:
    minutos: int
    porque: str


# Os prazos da spec R04 (Nexus, "COS como visão global": o ciclo da ocorrência em cinco etapas). Um lugar só.
PRAZOS = {
    "informado": Prazo(15, "R04: o cliente fica sabendo da ocorrência em até 15 min"),
    "campo": Prazo(30, "R04: o campo é acionado em até 30 min"),
}
# De onde os prazos contam: o INÍCIO da falha, o mesmo relógio do escalonamento a campo e do MTTA da Ronda COS. A outra
# leitura possível é a hora em que a Ronda COS registrou a ocorrência ("registrada_em"), que deixaria de fora a demora em
# registrar — medida em 22/10/2026 na Thopen: mediana de 24 min entre o início e o registro.
CONTA_DE = "inicio"

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


def _informado(o: dict, origem: datetime | None, envio: dict, agora: datetime) -> Etapa:
    prazo = PRAZOS["informado"].minutos
    if o.get("estado") == "DETECTADO":
        return Etapa("nao_medido", "—", detalhe="alarme ainda não confirmado: não vai ao cliente")
    if not origem:
        return Etapa("nao_medido", "—", detalhe="sem a hora de início")
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
            return Etapa("no_prazo", hora(em, agora), "ok", f"{via} · em {duracao(m)}")
        return Etapa("fora", hora(em, agora), "critico", f"{via} · em {duracao(m)} (prazo {prazo} min)")
    sem_os = "ainda sem OS: o Andamento só nomeia ao cliente a ocorrência com OS" if not o.get("os") else ""
    if not o.get("aberta"):
        return Etapa("nao_informado", "não avisado", "critico", sem_os or "fechou sem aviso ao cliente")
    m = _min(origem, agora)
    if m <= prazo:
        return Etapa("pendente", "aguardando", "info", f"faltam {duracao(prazo - m)}")
    return Etapa("atrasada", "não avisado", "critico", sem_os or f"há {duracao(m)} (prazo {prazo} min)")


def _campo(o: dict, origem: datetime | None, agora: datetime) -> Etapa:
    prazo = PRAZOS["campo"].minutos
    c = o.get("campo") or {}
    acionado = AND.instante(c.get("acionado_em"))
    if not origem:
        return Etapa("nao_medido", "—", detalhe="sem a hora de início")
    if acionado:
        m = _min(origem, acionado)
        quem = ORIGENS.get(c.get("acionado_por") or "", "")
        if m <= prazo:
            return Etapa("no_prazo", hora(acionado, agora), "ok", f"{quem} · em {duracao(m)}")
        return Etapa("fora", hora(acionado, agora), "critico", f"{quem} · em {duracao(m)} (prazo {prazo} min)")
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
    reg = AND.instante(o.get("registrada_em"))
    partes = []
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


def linha(o: dict, envio: dict, agora: datetime, url_do_andamento: str = "") -> Linha:
    origem = AND.instante(o.get(CONTA_DE))
    sev = o.get("severidade") or ""
    return Linha(
        o=o,
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
            "informado": _informado(o, origem, envio, agora),
            "campo": _campo(o, origem, agora),
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


def painel(leitura, agora: datetime, situacao: str = "", url_do_andamento: str = "") -> Painel | None:
    """O que a tela mostra: as linhas (filtradas pela situação), as contagens de cada situação (antes do filtro) e o
    placar das duas etapas com prazo (sobre todas, antes do filtro)."""
    d = leitura.dados if leitura else None
    if not d:
        return None
    envio = d.get("envio_ao_cliente") or {}
    todas = [linha(o, envio, agora, url_do_andamento) for o in d.get("ocorrencias") or []]
    return Painel(
        itens=[x for x in todas if _na_situacao(x, situacao)],
        total=len(todas),
        contagem={s: sum(_na_situacao(x, s) for x in todas) for s in SITUACOES},
        resumo={"informado": _resumo(todas, "informado"), "campo": _resumo(todas, "campo")},
        envio=envio,
        desde=AND.instante(d.get("desde")),
        gerado_em=AND.instante(d.get("gerado_em")),
        truncado=bool(d.get("truncado")),
    )


def dias_pedidos(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return AND.DIAS_PADRAO
    return n if n in AND.DIAS_DAS_OCORRENCIAS else AND.DIAS_PADRAO
