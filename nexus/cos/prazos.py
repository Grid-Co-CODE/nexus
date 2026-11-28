"""Relógios de prazo (23/11/2026): o que está com o prazo de 15 min correndo ou vencido agora, e quanto saiu no prazo?

O Andamento da Ronda COS calcula os relógios e escala por WhatsApp quando vencem (decisão do dono: "Andamento calcula,
Nexus mostra"); esta tela só lê `GET /api/nexus/<cliente>/prazos`. São três relógios, cada um com o seu "parar":
- **Alarme sem ocorrência**: o SCADA alarma a usina e nenhuma ocorrência aberta cobre o alarme. Para quando a ocorrência
  é aberta, ou o alarme some.
- **Voltou e não foi normalizada**: o supervisório já mostra o equipamento de volta e ninguém normalizou. Para na
  normalização.
- **Registrada sem card ao cliente**: a ocorrência que manda card foi registrada e o card não saiu (quase sempre por falta
  de OS). Para quando o card é gerado.

Nada aqui escreve nem manda mensagem.
"""
from dataclasses import dataclass, field
from datetime import datetime

from . import andamento as AND

DIAS_OPCOES = AND.DIAS_DOS_PRAZOS
DIAS_PADRAO = 1

# A ordem e o nome de cada relógio, como o Andamento os escreve (`ROTULO_DO_PRAZO`).
TIPOS = {
    "ALARME_SEM_OCORRENCIA": "Alarme sem ocorrência",
    "VOLTOU_SEM_NORMALIZAR": "Voltou e não foi normalizada",
    "REGISTRADA_SEM_CARD": "Registrada sem card ao cliente",
}


def dias_pedidos(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return DIAS_PADRAO
    return n if n in DIAS_OPCOES else DIAS_PADRAO


def _duracao(minutos: int) -> str:
    if minutos < 60:
        return f"{minutos} min"
    h, m = divmod(minutos, 60)
    if h < 24:
        return f"{h}h{m:02d}"
    d, h = divmod(h, 24)
    return f"{d} d {h}h"


@dataclass
class Linha:
    tipo: str
    rotulo: str
    nome: str
    os: str | None
    o_que: str
    inicio: datetime | None
    vence_em: datetime | None
    resolvido_em: datetime | None
    escalado: bool
    minutos: int
    dentro: bool | None
    # o que a coluna "Prazo" escreve, e o tom
    prazo: str = ""
    tom: str = "neutro"


@dataclass
class Painel:
    gerado_em: datetime | None
    ligado: bool
    envio: str
    prazo_min: int
    abertos: list[Linha] = field(default_factory=list)
    recentes: list[Linha] = field(default_factory=list)
    vencidos_agora: int = 0
    resumo: list[tuple[str, dict]] = field(default_factory=list)
    total: dict = field(default_factory=dict)
    pct_no_prazo: int | None = None


def _linha(p: dict, prazo_min: int) -> Linha:
    minutos = int(p.get("minutos") or 0)
    dentro = p.get("dentro_do_prazo")
    aberto = p.get("resolvido_em") is None
    if aberto:
        if dentro is False:
            prazo, tom = f"vencido há {_duracao(max(0, minutos - prazo_min))}", "critico"
        else:
            prazo, tom = f"faltam {_duracao(max(0, prazo_min - minutos))}", "alerta"
    else:
        prazo, tom = (f"no prazo ({_duracao(minutos)})", "ok") if dentro else (f"fora do prazo ({_duracao(minutos)})", "critico")
    return Linha(
        tipo=p.get("tipo", ""), rotulo=TIPOS.get(p.get("tipo", ""), p.get("rotulo") or ""), nome=p.get("nome", ""),
        os=p.get("os"), o_que=p.get("o_que", ""), inicio=AND.instante(p.get("inicio")),
        vence_em=AND.instante(p.get("vence_em")), resolvido_em=AND.instante(p.get("resolvido_em")),
        escalado=p.get("escalado_em") is not None, minutos=minutos, dentro=dentro, prazo=prazo, tom=tom)


def painel(leitura: AND.Leitura) -> Painel | None:
    d = leitura.dados
    if not d:
        return None
    prazo_min = int(d.get("prazo_min") or 15)
    p = Painel(gerado_em=AND.instante(d.get("gerado_em")), ligado=bool(d.get("ligado")), envio=d.get("envio") or "ensaio",
               prazo_min=prazo_min)
    p.abertos = [_linha(x, prazo_min) for x in d.get("abertos", [])]
    # o vencido primeiro, e dentro dele o que venceu antes
    p.abertos.sort(key=lambda x: (x.dentro is not False, x.inicio or datetime.max.replace(tzinfo=AND._BRT)))
    p.recentes = [_linha(x, prazo_min) for x in d.get("recentes", [])]
    p.vencidos_agora = sum(1 for x in p.abertos if x.dentro is False)
    resumo = d.get("resumo") or {}
    p.resumo = [(TIPOS[t], resumo.get(t) or {}) for t in TIPOS]
    p.total = resumo.get("total") or {}
    fechados = (p.total.get("dentro") or 0) + (p.total.get("fora") or 0)
    p.pct_no_prazo = round(100 * (p.total.get("dentro") or 0) / fechados) if fechados else None
    return p
