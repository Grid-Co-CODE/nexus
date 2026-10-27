"""Religamentos (26/10/2026): onde o religamento remoto resolve e onde se repete na mesma cabine?

Os fatos vêm do Andamento da Ronda COS, pela mesma rota da tela Ocorrências (`GET /api/nexus/<cliente>/ocorrencias`),
com os campos que entraram para esta tela: `ativos` (a tag de cada equipamento, na ordem de `equipamentos`) e
`religamento` (houve religamento remoto e/ou local na ocorrência). O desfecho e a repetição são daqui.

O que a Ronda COS não grava, e esta tela não inventa: o resultado "Persistiu" ou "Parcial" do religamento remoto vai só
para o checklist da OS. "O remoto não segurou" é a ocorrência com religamento remoto que foi a campo depois (a OS com
religamento local, ou o campo acionado por pessoa); a passagem automática a "Técnico acionado" não conta como ida a
campo (a mesma regra da tela Ocorrências).
"""
from dataclasses import dataclass, field
from datetime import datetime

from . import andamento as AND

# A régua da repetição. Repete: dois religamentos ou mais no mesmo equipamento no período. Reincidente: três ou mais, a
# régua de reincidência do RDO da Ronda COS (o mesmo ativo três vezes ou mais em 30 dias, `rdo.secoes.ts`).
REPETE_A_PARTIR = 2
REINCIDENTE_A_PARTIR = 3
# A repetição precisa de janela: 30 dias é a do RDO e o máximo que o Andamento entrega.
DIAS_OPCOES = (7, 30)
DIAS_PADRAO = 30

DESFECHOS = {
    "resolveu": ("Remoto resolveu", "ok"),
    "foi_a_campo": ("Remoto e depois campo", "alerta"),
    "em_aberto": ("Remoto, ainda aberta", "info"),
    "so_local": ("Só local", "neutro"),
}

VER = {"repetem": "Repetem", "todos": "Todos os equipamentos"}

USINA_INTEIRA = "Usina inteira"


@dataclass
class Equipamento:
    usina: str
    usina_codigo: str
    rotulo: str
    tag: str
    ocorrencias: list = field(default_factory=list)   # [(quando, desfecho, os, tipo_falha)]
    desfechos: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.ocorrencias)

    @property
    def ultima(self) -> datetime | None:
        q = [o[0] for o in self.ocorrencias if o[0]]
        return max(q) if q else None

    @property
    def repete(self) -> bool:
        return self.total >= REPETE_A_PARTIR

    @property
    def reincidente(self) -> bool:
        return self.total >= REINCIDENTE_A_PARTIR

    @property
    def os(self) -> list[str]:
        return [o[2] for o in sorted(self.ocorrencias, key=lambda o: o[0] or datetime.min.replace(tzinfo=AND._BRT),
                                     reverse=True) if o[2]]

    @property
    def tipos(self) -> list[str]:
        return sorted({o[3] for o in self.ocorrencias if o[3]})


def dias_pedidos(v) -> int:
    try:
        d = int(v)
    except (TypeError, ValueError):
        return DIAS_PADRAO
    return d if d in DIAS_OPCOES else DIAS_PADRAO


def religamento(o: dict) -> tuple[dict, bool]:
    """({"remoto", "local"}, veio do Andamento). Sem o campo (o Andamento de antes de 26/10/2026), o que dá para ver: a
    normalização pelo religamento remoto e o campo acionado pela OS com religamento local — os dois caminhos da
    plataforma; o remoto aberto direto no Fracttal fica de fora, e a tela diz."""
    r = o.get("religamento")
    if isinstance(r, dict):
        return {"remoto": bool(r.get("remoto")), "local": bool(r.get("local"))}, True
    norm = o.get("normalizada") or {}
    campo = o.get("campo") or {}
    return {"remoto": norm.get("por") == "religamento_remoto", "local": campo.get("acionado_por") == "criacao_da_os"}, False


def desfecho(o: dict, rel: dict) -> str | None:
    """None = a ocorrência não teve religamento. Com remoto: foi a campo depois (OS local ou campo acionado por pessoa),
    ainda aberta, ou resolveu (fechou sem ir a campo). Só com local: "só local"."""
    if rel["remoto"]:
        if rel["local"] or (o.get("campo") or {}).get("acionado_em"):
            return "foi_a_campo"
        return "em_aberto" if o.get("aberta") else "resolveu"
    return "so_local" if rel["local"] else None


def equipamentos(o: dict) -> tuple[list[tuple[str, str]], bool]:
    """([(tag, rótulo)], pela tag). A tag ("THPN-EBG100-SKID3") vem do Andamento desde 26/10/2026; antes, só o nome do
    equipamento, que pode repetir em outra usina (por isso a chave leva a usina). Sem equipamento = a usina inteira."""
    nomes = [str(n) for n in o.get("equipamentos") or []]
    tags = o.get("ativos")
    if isinstance(tags, list):
        return ([(str(t), nomes[i] if i < len(nomes) else str(t)) for i, t in enumerate(tags)] or [("", USINA_INTEIRA)]), True
    return ([(f"nome:{n}", n) for n in nomes] or [("", USINA_INTEIRA)]), False


@dataclass
class Painel:
    itens: list
    total_equipamentos: int
    resumo: dict
    contagem: dict
    pela_tag: bool
    completo: bool
    desde: datetime | None
    gerado_em: datetime | None
    truncado: bool


def painel(leitura, ver: str = "repetem") -> Painel | None:
    """O que a tela mostra: os equipamentos com religamento no período (os que repetem primeiro) e a conta do remoto."""
    d = leitura.dados
    if not d:
        return None
    por_equip: dict[tuple[str, str], Equipamento] = {}
    resumo = {k: 0 for k in DESFECHOS}
    pela_tag = completo = True
    for o in d.get("ocorrencias") or []:
        rel, veio = religamento(o)
        eqs, por_tag = equipamentos(o)
        # o aviso de Andamento antigo vale pela resposta inteira, não só pelas ocorrências com religamento
        completo, pela_tag = completo and veio, pela_tag and por_tag
        des = desfecho(o, rel)
        if des is None:
            continue
        resumo[des] += 1
        quando = AND.instante(o.get("inicio"))
        for tag, rotulo in eqs:
            k = (str(o.get("usina_codigo") or o.get("usina") or ""), tag)
            e = por_equip.setdefault(k, Equipamento(usina=str(o.get("usina") or ""), usina_codigo=k[0], rotulo=rotulo,
                                                    tag="" if tag.startswith("nome:") else tag))
            e.ocorrencias.append((quando, des, str(o.get("os") or ""), str(o.get("tipo_falha") or "")))
            e.desfechos[des] = e.desfechos.get(des, 0) + 1
    todos = sorted(por_equip.values(), key=lambda e: (-e.total, -(e.ultima.timestamp() if e.ultima else 0), e.usina))
    remotos = resumo["resolveu"] + resumo["foi_a_campo"] + resumo["em_aberto"]
    fechados = resumo["resolveu"] + resumo["foi_a_campo"]
    contagem = {"repetem": sum(1 for e in todos if e.repete), "todos": len(todos)}
    return Painel(
        itens=[e for e in todos if ver == "todos" or e.repete], total_equipamentos=len(todos),
        resumo={**resumo, "remotos": remotos, "fechados": fechados,
                "pct_resolveu": round(100 * resumo["resolveu"] / fechados) if fechados else None,
                "reincidentes": sum(1 for e in todos if e.reincidente)},
        contagem=contagem, pela_tag=pela_tag, completo=completo, desde=AND.instante(d.get("desde")),
        gerado_em=AND.instante(d.get("gerado_em")), truncado=bool(d.get("truncado")))
