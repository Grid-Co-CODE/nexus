"""Desempenho da equipe (05/11/2026): as mesas estão dentro do MTTA e do aviso no prazo?

Spec R04: "Desempenho por mesa: MTTA, informado no prazo e religamento remoto". Por cliente e por turno, sem nome de
operador (decisão do dono, 05/11/2026: desempenho com nome é dado pessoal); a mesa aparece como o conjunto de clientes de
uma carteira da Ronda COS. Os fatos são o ciclo das ocorrências do Andamento (`GET /api/nexus/<cliente>/ocorrencias`), o
mesmo da tela Ocorrências.

- **MTTA** (decisão do dono, 05/11/2026): do início da falha até a hora em que o COS VIU (`detectada_em`, o
  `detectado_em` da Ronda COS, perguntado a quem abre o desvio na tela desde 03/11/2026). Mediana em minutos, como o MTTA
  de lá. O desvio que veio do sync ou de antes do campo não tem a hora e fica fora da conta, com a amostra à vista; a
  espera negativa (viu antes do início digitado) também fica fora, como lá.
- **Informado no prazo:** o veredito da etapa "cliente informado" da tela Ocorrências (15 min, `ocorrencias.PRAZOS`),
  sobre as que já se decidiram (cumpriu ou não); a que ainda corre o prazo e a que não se mede ficam fora.
- **Religamento remoto:** das normalizadas, quantas tiveram religamento remoto (a regra da tela Religamentos,
  `religamentos.religamento`).
- **Turno:** pela hora do início da falha, nos turnos da Ronda COS (`turno.TURNOS`: dia das 06h, noite das 18h).
"""
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median

from . import andamento as AND
from . import ocorrencias as OC
from . import religamentos as RE
from . import turno as TU

DIAS_OPCOES = (7, 30)
DIAS_PADRAO = 7


def dias_pedidos(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return DIAS_PADRAO
    return n if n in DIAS_OPCOES else DIAS_PADRAO


def turno_de(t: datetime | None) -> str:
    """O turno da Ronda COS em que a hora cai (em Brasília): o último que começou."""
    if not t:
        return ""
    h = t.astimezone(AND._BRT).hour
    vale = [x for x in TU.TURNOS if x.inicio_h <= h]
    return (vale[-1] if vale else TU.TURNOS[-1]).id


def mtta_min(o: dict) -> float | None:
    """Minutos do início da falha até o COS ver; None sem a hora ou com a espera negativa."""
    inicio, viu = AND.instante(o.get(OC.CONTA_DE)), AND.instante(o.get("detectada_em"))
    if not inicio or not viu or viu < inicio:
        return None
    return (viu - inicio).total_seconds() / 60


@dataclass
class Grupo:
    ocorrencias: int = 0
    mtta: list = field(default_factory=list)
    informado: list = field(default_factory=list)     # os estados da etapa
    normalizadas: int = 0
    remoto: int = 0

    def somar(self, o: dict, linha: OC.Linha) -> None:
        self.ocorrencias += 1
        m = mtta_min(o)
        if m is not None:
            self.mtta.append(m)
        self.informado.append(linha.etapas["informado"].estado)
        if not o.get("aberta") and o.get("normalizada"):
            self.normalizadas += 1
            if RE.religamento(o)[0].get("remoto"):
                self.remoto += 1

    @property
    def resumo(self) -> dict:
        cumpriu = sum(e in OC.CUMPRIU for e in self.informado)
        nao = sum(e in OC.NAO_CUMPRIU for e in self.informado)
        return {
            "ocorrencias": self.ocorrencias,
            "mtta": round(median(self.mtta)) if self.mtta else None,
            "mtta_amostra": len(self.mtta),
            "informado_cumpriu": cumpriu,
            "informado_fora": nao,
            "informado_pct": round(100 * cumpriu / (cumpriu + nao)) if cumpriu + nao else None,
            "informado_correndo": sum(e in OC.PENDENTE for e in self.informado),
            "normalizadas": self.normalizadas,
            "remoto": self.remoto,
            "remoto_pct": round(100 * self.remoto / self.normalizadas) if self.normalizadas else None,
        }


@dataclass
class Painel:
    clientes: list            # [{cliente, total, turnos: {dia: resumo, noite: resumo}}]
    turnos: dict              # {dia: resumo, noite: resumo} de todos os clientes lidos
    total: dict
    mesas: list               # [{clientes, operadores, minha, resumo}]
    erros: list
    completo: bool            # todos os clientes lidos
    com_deteccao: bool        # o Andamento já manda a hora em que o COS viu
    truncado: list


def painel(leituras: list, agora: datetime, mesas: list | None = None, minha: list | None = None) -> Painel:
    """`leituras` = o ciclo das ocorrências de cada cliente (`andamento.ler_ocorrencias`); `mesas` = as de `mesa.mesas`;
    `minha` = os clientes da carteira de quem entrou (para marcar a mesa dele)."""
    por_cliente: dict[str, dict[str, Grupo]] = {}
    total, turnos = Grupo(), {t.id: Grupo() for t in TU.TURNOS}
    erros, truncado, com_deteccao = [], [], False
    for lt in leituras:
        if lt.erro:
            erros.append((lt.cliente, lt.erro, lt.velha))
        d = lt.dados
        if not d:
            continue
        if d.get("truncado"):
            truncado.append(lt.cliente)
        envio = d.get("envio_ao_cliente") or {}
        grupos = por_cliente.setdefault(lt.cliente, {"total": Grupo(), **{t.id: Grupo() for t in TU.TURNOS}})
        for o in d.get("ocorrencias") or []:
            com_deteccao = com_deteccao or "detectada_em" in o
            x = OC.linha(o, envio, agora)
            t = turno_de(AND.instante(o.get(OC.CONTA_DE)))
            for g in (grupos["total"], total, *((grupos[t], turnos[t]) if t else ())):
                g.somar(o, x)
    linhas = [{"cliente": c, "total": g["total"].resumo, "turnos": {t.id: g[t.id].resumo for t in TU.TURNOS}}
              for c, g in por_cliente.items()]
    lista_mesas = []
    for m in mesas or []:
        if not all(c in por_cliente for c in m["clientes"]):
            continue
        g = Grupo()
        for c in m["clientes"]:
            for campo in ("ocorrencias", "normalizadas", "remoto"):
                setattr(g, campo, getattr(g, campo) + getattr(por_cliente[c]["total"], campo))
            g.mtta += por_cliente[c]["total"].mtta
            g.informado += por_cliente[c]["total"].informado
        lista_mesas.append({**m, "minha": bool(minha) and set(m["clientes"]) == set(minha), "resumo": g.resumo})
    return Painel(
        clientes=linhas,
        turnos={k: g.resumo for k, g in turnos.items()},
        total=total.resumo,
        mesas=lista_mesas,
        erros=erros,
        completo=bool(leituras) and all(lt.dados for lt in leituras),
        com_deteccao=com_deteccao,
        truncado=truncado,
    )
