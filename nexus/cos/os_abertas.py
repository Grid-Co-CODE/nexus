"""OS em aberto (27/10/2026): o Panorama da Ronda COS no Nexus — as OS abertas no Fracttal que o COS abriu, a mais
antiga primeiro, com o que já foi feito e só falta finalizar separado do que está pendente.

Os fatos vêm do Andamento (`GET /api/nexus/os-abertas`, um retrato de TODOS os clientes): o que entra (só corretiva
emergencial, religamento e religamento remoto; sem a usina de teste; sem o assunto encerrado), a situação e o alerta de
1 h são regra da Ronda COS, e o Nexus não os refaz. Daqui são só os filtros, as contas da faixa e a idade de cada OS na
hora em que a tela abre.

Só lê: reconhecer o alerta é na Ronda COS, e o detalhe da OS (descrição, responsável, notas) abre no card do Fracttal,
com o login de quem clica. O Andamento não manda nome de pessoa nem texto livre.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from . import andamento as AND

# As situações do Panorama (`lerSituacao` lá): o padrão é a pendente, porque é o que a tela promete. Em 24/08/2026,
# 199 das 243 OS do Panorama estavam em 100%: dívida administrativa, não operação parada.
SITUACOES = {
    "pendente": "Pendentes",
    "concluida": "Feitas, falta finalizar",
    "todas": "Todas",
}
SITUACAO_PADRAO = "pendente"

# As faixas de idade do Panorama (`faixaDeIdade` lá, os cortes do painel gerencial: 7, 30 e 90 dias), em dias.
FAIXAS = {
    "0-7": ("Até 7 dias", 0, 7),
    "7-30": ("7 a 30 dias", 7, 30),
    "30-90": ("30 a 90 dias", 30, 90),
    "90+": ("Acima de 90 dias", 90, None),
}

# O status da OS no Fracttal (`id_status_work_order`, o mesmo de nexus/engenharia/os_equipe.py). O segundo valor é o
# que o card da OS espera (o selo e a regra do "Editar" das notas saem dele).
STATUS = {1: ("Em processo", "Em Processo"), 2: ("Em verificação", "Em Verificação")}

# O estado do registro da Ronda COS que aponta para a OS (`EstadoRegistro` lá), no tom da casa (cn-t-*). Sem registro é
# o achado da triagem: ninguém acompanha esta OS pela Ronda COS.
ESTADOS_DO_REGISTRO = {
    "DETECTADO": ("Detectada", "critico"),
    "CONFIRMADO": ("Confirmada", "critico"),
    "TRATATIVA_REMOTA": ("Tratativa remota", "info"),
    "EM_CAMPO": ("Em campo", "alerta"),
    "EM_EXECUCAO": ("Em execução", "alerta"),
    "BLOQUEADO": ("Bloqueada", "alerta"),
    "NORMALIZADO": ("Normalizada", "ok"),
    "ENCERRADO": ("Encerrada", "ok"),
}
SEM_REGISTRO = ("Sem registro", "alerta")

# A varredura do Fracttal lá passa de 30 em 30 min (aos 13 e aos 43). Três passagens perdidas = o retrato está velho, e
# uma OS que fechou no Fracttal pode continuar na lista.
VARREDURA_VELHA_MIN = 90
# A busca é texto curto (nº da OS, usina, ativo).
BUSCA_MAX = 80


@dataclass
class Painel:
    itens: list = field(default_factory=list)
    contagem: dict = field(default_factory=dict)
    resumo: dict = field(default_factory=dict)
    cortes: dict = field(default_factory=dict)
    varredura: datetime | None = None
    varredura_velha: bool = False
    horas_para_alerta: int = 1
    truncado: bool = False


def situacao_pedida(v) -> str:
    return v if v in SITUACOES else SITUACAO_PADRAO


def faixa_de(dias: int) -> str:
    for k, (_, de, ate) in FAIXAS.items():
        if dias >= de and (ate is None or dias < ate):
            return k
    return "90+"


def idade(criada: datetime | None, agora: datetime) -> tuple[int, int]:
    """(horas, dias) inteiros desde a criação, nunca negativos (o relógio do Fracttal pode estar à frente)."""
    if not criada:
        return 0, 0
    s = max(0, int((agora - criada).total_seconds()))
    return s // 3600, s // 86400


def aberta_ha(horas: int) -> str:
    """O contador da tela, em horas até dois dias (o Panorama conta em horas) e em dias depois."""
    return f"{horas} h" if horas < 48 else f"{horas // 24} dias"


def _item(o: dict, agora: datetime) -> dict:
    criada = AND.instante(o.get("criada_em"))
    horas, dias = idade(criada, agora)
    status = STATUS.get(o.get("status"), (f"status {o.get('status')}", ""))
    estado = o.get("registro_estado")
    ativos = [str(a) for a in o.get("ativos") or []]
    return {
        "folio": o.get("folio"),
        "id_wo": o.get("id_work_order"),
        "criada": criada,
        "horas": horas,
        "dias": dias,
        "aberta_ha": aberta_ha(horas),
        "faixa": faixa_de(dias),
        "cliente": str(o.get("cliente") or "").strip() or "(sem cliente)",
        "usina": str(o.get("usina") or o.get("usina_codigo") or "").strip() or "(sem usina)",
        "usina_codigo": o.get("usina_codigo") or "",
        "ativo": o.get("ativo_nome") or (ativos[0] if ativos else ""),
        "mais_ativos": max(0, len(ativos) - 1),
        "ativos": ativos,
        "tipo": str(o.get("tipo") or "").strip(),
        "classificacao": str(o.get("classificacao") or "").strip(),
        "prioridade": o.get("prioridade") or "",
        "pct": int(o.get("concluida_pct") or 0),
        "situacao": o.get("situacao") if o.get("situacao") in ("pendente", "concluida") else "pendente",
        "status": status[0],
        "status_card": status[1],
        "registro": ESTADOS_DO_REGISTRO.get(estado, (estado.title(), "neutro")) if estado else SEM_REGISTRO,
        "sem_registro": not estado,
        "reconhecida": AND.instante(o.get("reconhecida_em")),
        "em_alerta": bool(o.get("em_alerta")),
    }


def _casa_busca(i: dict, q: str) -> bool:
    q = q.lower()
    if q.isdigit() and str(i["folio"]) == q:
        return True
    alvo = " ".join([i["usina"], i["usina_codigo"], i["ativo"], *i["ativos"], i["cliente"]]).lower()
    return q in alvo


def painel(leitura, agora: datetime, situacao: str = SITUACAO_PADRAO, cliente: str = "", tipo: str = "",
           faixa: str = "", sem_registro: bool = False, busca: str = "") -> Painel | None:
    """A tela. As pílulas de cliente, tipo e idade contam sobre a situação escolhida, ANTES dos outros filtros (um contador
    que encolhe conforme se filtra não diz mais quanto existe); as de situação contam sobre todas. O alerta é do painel
    inteiro: OS em alerta é sempre pendente."""
    d = leitura.dados if leitura else None
    if not d:
        return None
    situacao = situacao_pedida(situacao)
    todos = [_item(o, agora) for o in d.get("os") or []]
    na_situacao = [i for i in todos if situacao == "todas" or i["situacao"] == situacao]
    lista = na_situacao
    if cliente:
        lista = [i for i in lista if i["cliente"] == cliente]
    if tipo:
        lista = [i for i in lista if i["tipo"].lower() == tipo.lower()]
    if faixa in FAIXAS:
        lista = [i for i in lista if i["faixa"] == faixa]
    if sem_registro:
        lista = [i for i in lista if i["sem_registro"]]
    busca = " ".join((busca or "").split())[:BUSCA_MAX]
    if busca:
        lista = [i for i in lista if _casa_busca(i, busca)]

    varredura = AND.instante(d.get("varredura_em"))
    return Painel(
        itens=lista,
        contagem={
            "situacao": {k: (len(todos) if k == "todas" else sum(1 for i in todos if i["situacao"] == k))
                         for k in SITUACOES},
            "cliente": dict(sorted(Counter(i["cliente"] for i in na_situacao).items())),
            "tipo": dict(Counter(i["tipo"] or "(sem tipo)" for i in na_situacao).most_common()),
            "faixa": {k: sum(1 for i in na_situacao if i["faixa"] == k) for k in FAIXAS},
        },
        resumo={
            "total": len(na_situacao),
            "acima_30": sum(1 for i in na_situacao if i["dias"] >= 30),
            "acima_90": sum(1 for i in na_situacao if i["dias"] >= 90),
            "sem_registro": sum(1 for i in na_situacao if i["sem_registro"]),
            "em_alerta": sum(1 for i in todos if i["em_alerta"]),
        },
        cortes=d.get("cortes") or {},
        varredura=varredura,
        varredura_velha=bool(varredura) and (agora - varredura).total_seconds() > VARREDURA_VELHA_MIN * 60,
        horas_para_alerta=int(d.get("horas_para_alerta") or 1),
        truncado=bool(d.get("truncado")),
    )
