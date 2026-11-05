"""Mesa do operador (05/11/2026): o que está aberto na minha mesa e o que falta avisar ao cliente?

Spec R04 (COS como visão global): "cada operador tem uma carteira de clientes, e o líder enxerga todas". A carteira é a da
Ronda COS (a aba "Operador x clientes"), pela rota `GET /api/nexus/carteiras` do Andamento: cada carteira vem com o HMAC
do e-mail com a chave do Nexus, e a tela acha a de quem entrou fazendo a mesma conta com o e-mail do login. Sem carteira
(o supervisor e a gestão não têm, como lá), a tela mostra todas as mesas; qualquer um troca para "Todas as mesas".

O que está aberto vem da fotografia do Andamento (a mesma da Ronda padronizada); o que falta avisar e o campo a acionar,
do ciclo das ocorrências com os prazos e os vereditos da tela Ocorrências (`ocorrencias.py`, a spec R04: cliente
informado em 15 min, campo acionado em 30 min). Nada é regra nova aqui: a Mesa só junta e recorta pela carteira.
"""
from dataclasses import dataclass, field
from datetime import datetime

from . import andamento as AND
from . import ocorrencias as OC
from . import turno as TU

# As ocorrências que ainda podem estar abertas: a janela padrão da tela Ocorrências (a cópia de 60 s é a mesma).
DIAS_DA_MESA = AND.DIAS_PADRAO
# A ordem do que é para fazer: o prazo estourado primeiro, depois o que está correndo.
PARA_FAZER = ("atrasada", "pendente")


@dataclass
class Mesa:
    clientes: list            # os clientes da mesa, na ordem do Andamento
    minha: bool = False       # é a carteira de quem entrou
    fora: list = field(default_factory=list)   # da carteira, os que o Andamento não acompanha
    aviso: str = ""           # por que a tela mostra todas as mesas


def carteira_de(email: str, leitura, chave: str) -> tuple[list | None, list]:
    """(clientes, fora) da carteira de quem entrou; clientes None = não há carteira para este e-mail."""
    d = leitura.dados if leitura else None
    if not d or not email or not chave:
        return None, []
    pessoa = AND.chave_da_pessoa(email, chave)
    for c in d.get("carteiras") or []:
        if c.get("pessoa") == pessoa:
            return [str(x) for x in c.get("clientes") or []], [str(x) for x in c.get("fora") or []]
    return None, []


def escolher(email: str, chave: str, leitura, clientes: list, ver: str = "") -> Mesa:
    """A mesa que a tela mostra: a carteira de quem entrou, ou todas (pedido, sem carteira ou sem leitura)."""
    if ver == "todas":
        return Mesa(list(clientes))
    if not email:
        return Mesa(list(clientes), aviso="Você entrou sem e-mail (a senha de administrador): a tela mostra todas as mesas.")
    if not leitura or not leitura.dados:
        erro = (leitura.erro if leitura else "") or "sem resposta"
        return Mesa(list(clientes), aviso=f"Não consegui ler as carteiras da Ronda COS ({erro}): a tela mostra todas as "
                                           f"mesas.")
    meus, fora = carteira_de(email, leitura, chave)
    if meus is None:
        return Mesa(list(clientes), aviso="Você não tem carteira na Ronda COS (a aba Operador x clientes): a tela mostra "
                                           "todas as mesas.")
    meus = [c for c in clientes if c in meus]
    if not meus:
        return Mesa(list(clientes), fora=fora, aviso="Os clientes da sua carteira não estão no Andamento: a tela mostra "
                                                     "todas as mesas.")
    return Mesa(meus, minha=True, fora=fora)


def mesas(leitura, clientes: list) -> list[dict]:
    """As mesas que existem: cada conjunto de clientes de alguma carteira, com quantos operadores o têm (sem quem)."""
    d = leitura.dados if leitura else None
    vistas: dict[tuple, int] = {}
    for c in (d or {}).get("carteiras") or []:
        chave = tuple(x for x in clientes if x in (c.get("clientes") or []))
        if chave:
            vistas[chave] = vistas.get(chave, 0) + 1
    return [{"clientes": list(k), "operadores": n} for k, n in sorted(vistas.items(), key=lambda kv: [clientes.index(x)
                                                                                                    for x in kv[0]])]


@dataclass
class Item:
    cliente: str
    linha: OC.Linha
    etapa: OC.Etapa
    inicio: datetime | None


@dataclass
class Painel:
    falta_avisar: list
    campo: list
    por_cliente: list
    resumo: dict
    erros: list


def _ordem(i: Item):
    return (PARA_FAZER.index(i.etapa.estado), i.inicio or datetime.max.replace(tzinfo=AND._BRT))


def painel(fotos: list, ciclos: list, agora: datetime, url_do_andamento: str = "") -> Painel:
    """`fotos` = a leitura da fotografia de cada cliente da mesa (`andamento.ler`); `ciclos` = a do ciclo das ocorrências
    (`andamento.ler_ocorrencias`, DIAS_DA_MESA dias). Só as ocorrências ABERTAS entram nas listas."""
    falta, campo, erros = [], [], []
    for lt in ciclos:
        if lt.erro:
            erros.append((lt.cliente, lt.erro, lt.velha))
        d = lt.dados
        if not d:
            continue
        envio = d.get("envio_ao_cliente") or {}
        for o in d.get("ocorrencias") or []:
            if not o.get("aberta"):
                continue
            x = OC.linha(o, envio, agora, url_do_andamento)
            inicio = AND.instante(o.get(OC.CONTA_DE))
            if x.etapas["informado"].estado in PARA_FAZER:
                falta.append(Item(lt.cliente, x, x.etapas["informado"], inicio))
            if x.etapas["campo"].estado in PARA_FAZER:
                campo.append(Item(lt.cliente, x, x.etapas["campo"], inicio))
    for lt in fotos:
        if lt.erro and not any(e[0] == lt.cliente for e in erros):
            erros.append((lt.cliente, lt.erro, lt.velha))
    aberto = TU.aberto_no_andamento(fotos)
    falta.sort(key=_ordem)
    campo.sort(key=_ordem)
    return Painel(
        falta_avisar=falta,
        campo=campo,
        por_cliente=aberto["por_cliente"],
        resumo={
            "abertas": aberto["abertas"],
            "criticas": aberto["criticas"],
            "falta_avisar": len(falta),
            "avisar_atrasadas": sum(1 for i in falta if i.etapa.estado == "atrasada"),
            "campo": len(campo),
            "campo_atrasadas": sum(1 for i in campo if i.etapa.estado == "atrasada"),
        },
        erros=erros,
    )
