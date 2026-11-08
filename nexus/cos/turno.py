"""Passagem de turno (R12 do Fillipe): "a passagem é registrada no sistema; sem registro, ela não aconteceu".

Nada disso existia: a Ronda COS só sabe os turnos (dia 06–18, noite 18–06) e deduz o plantonista pelas ações nas
ocorrências; ninguém registrava quem passou o turno, o que ficou pendente nem quem assumiu (levantamento de 26/10/2026).

O Nexus é a FONTE deste fato: livro `nexus_cos_turno` · `fato_passagem_turno`, registrado no catálogo antes da 1ª
gravação (regra 10). Grão: 1 linha = 1 EVENTO sobre 1 troca de turno (`troca_em`, a hora cheia da troca):
`passagem` (quem sai escreve o que o próximo turno precisa saber; mais de um operador pode escrever na mesma troca) ou
`assumiu` (quem entra leu e assumiu). Só acrescenta: nada se edita nem se apaga.

A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): quem (nome e e-mail) e o texto vão só CIFRADOS com a
chave do cadastro (o Cofre, como o acompanhamento das contestações); a pessoa liga pelo código do e-mail (`pessoa_hmac`).
As contagens do que estava aberto no Andamento na hora da passagem (`abertas_qtd`, `criticas_qtd`) vão em claro: são
números da operação, sem nome.
"""
import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros

LIVRO, NOME_LIVRO = "nexus_cos_turno", "Nexus · passagem de turno do COS"
ABA = "fato_passagem_turno"
CAB = ("id", "registrado_em", "data_id", "troca_em", "data_id_troca", "turno_que_sai", "evento", "pessoa_hmac",
       "quem_cifrado", "texto_cifrado", "abertas_qtd", "criticas_qtd")
EVENTOS = ("passagem", "assumiu")
TEXTO_MAX = 4000
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()       # o livro é trocado inteiro: duas gravações juntas não se apagam


@dataclass(frozen=True)
class Turno:
    id: str
    nome: str
    inicio_h: int    # a hora de Brasília em que o turno começa; ele termina quando o seguinte começa


# Os turnos do COS são os da Ronda COS (ronda.service.ts, `turnoInicio`: dia 06–18, noite 18–06), os mesmos da ronda e
# do RDO. Mudou lá, muda aqui: dois relógios de turno dariam duas respostas para "quem estava no turno".
TURNOS = (Turno("dia", "Dia", 6), Turno("noite", "Noite", 18))
# A passagem registrada até 60 min depois da troca ainda é DAQUELA troca: quem sai às 18:00 e escreve às 18:10 está
# passando o dia, não a noite. Depois disso, a passagem vai para a troca do fim do turno em curso. É também a janela em
# que quem entra pode assumir a troca seguinte antes da hora (chegou às 17:45 e já leu).
TOLERANCIA_MIN = 60
# O histórico da tela: 7 dias, 14 trocas.
DIAS_DO_HISTORICO = 7

SITUACOES = {
    "assumida": ("Assumida", "ok"),
    "registrada": ("Registrada, aguardando quem assume", "info"),
    "sem_assumir": ("Registrada, ninguém assumiu", "alerta"),
    "aguardando": ("Aguardando a passagem", "neutro"),
    "sem_registro": ("Sem registro: a passagem não aconteceu", "critico"),
}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


# ── o relógio dos turnos (puro) ──────────────────────────────────────────────────────────────────────────────────────

def _brt(t: datetime) -> datetime:
    return t.astimezone(_BRT) if t.tzinfo else t.replace(tzinfo=_BRT)


def _horas_de_troca() -> list[int]:
    return sorted(t.inicio_h for t in TURNOS)


def turno_que_comeca(troca: datetime) -> Turno:
    h = _brt(troca).hour
    return next(t for t in TURNOS if t.inicio_h == h)


def turno_que_sai(troca: datetime) -> Turno:
    """O turno que termina nesta troca (o anterior ao que começa)."""
    i = TURNOS.index(turno_que_comeca(troca))
    return TURNOS[i - 1]


def troca_anterior(t: datetime) -> datetime:
    """A última troca em `t` ou antes (o início do turno em curso)."""
    t = _brt(t)
    for dia in (t.date(), t.date() - timedelta(days=1)):
        for h in reversed(_horas_de_troca()):
            c = datetime(dia.year, dia.month, dia.day, h, tzinfo=_BRT)
            if c <= t:
                return c
    raise AssertionError("sem troca nas últimas 24 h: TURNOS vazio?")


def troca_seguinte(t: datetime) -> datetime:
    """A primeira troca depois de `t` (o fim do turno em curso)."""
    t = _brt(t)
    for dia in (t.date(), t.date() + timedelta(days=1)):
        for h in _horas_de_troca():
            c = datetime(dia.year, dia.month, dia.day, h, tzinfo=_BRT)
            if c > t:
                return c
    raise AssertionError("sem troca nas próximas 24 h: TURNOS vazio?")


def troca_da_passagem(t: datetime) -> datetime:
    """A troca a que vai uma passagem escrita em `t`: a que acabou de acontecer, dentro da tolerância; senão a do fim do
    turno em curso."""
    anterior = troca_anterior(t)
    return anterior if _brt(t) < anterior + timedelta(minutes=TOLERANCIA_MIN) else troca_seguinte(t)


def trocas_que_se_pode_assumir(t: datetime) -> list[datetime]:
    """Quem entra assume a troca que começou o turno em curso, ou a seguinte se faltar menos que a tolerância."""
    out = [troca_anterior(t)]
    seguinte = troca_seguinte(t)
    if seguinte - _brt(t) <= timedelta(minutes=TOLERANCIA_MIN):
        out.append(seguinte)
    return out


def trocas_do_historico(agora: datetime, dias: int = DIAS_DO_HISTORICO) -> list[datetime]:
    """As trocas dos últimos `dias` até a próxima, da mais nova para a mais velha."""
    out, t = [troca_seguinte(agora)], troca_anterior(agora)
    limite = _brt(agora) - timedelta(days=dias)
    while t > limite:
        out.append(t)
        t = troca_anterior(t - timedelta(seconds=1))
    return out


def rotulo_da_troca(troca: datetime) -> str:
    return f"{turno_que_sai(troca).nome} → {turno_que_comeca(troca).nome}"


# A ocorrência crítica no Andamento é a da classe "crit" ou "alto" (a mesma régua da Ronda padronizada, andamento.ronda).
CLASSES_CRITICAS = ("crit", "alto")


def aberto_no_andamento(leituras) -> dict:
    """O que está aberto agora, por cliente e somado, das leituras do Andamento (`andamento.ler`). Algum cliente sem
    leitura: a soma fica None, e nada vai ao livro (número pela metade não se grava)."""
    por_cliente, completo = [], bool(leituras)
    for lt in leituras:
        if not lt.dados:
            completo = False
            por_cliente.append({"cliente": lt.cliente, "abertas": None, "criticas": None, "erro": lt.erro})
            continue
        ocs = [o for u in lt.dados.get("usinas") or [] for o in u.get("ocorrencias") or []]
        por_cliente.append({"cliente": lt.cliente, "abertas": len(ocs), "erro": lt.erro if lt.velha else "",
                            "criticas": sum(1 for o in ocs if o.get("severidade_classe") in CLASSES_CRITICAS)})
    return {"por_cliente": por_cliente,
            "abertas": sum(c["abertas"] for c in por_cliente) if completo else None,
            "criticas": sum(c["criticas"] for c in por_cliente) if completo else None}


# ── o livro ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela nada vai cifrado")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _cofre_ou_nada():
    try:
        return _cofre()
    except Recusada:
        return None


def _ctx(eid, campo) -> str:
    return f"banco/cos_turno/{eid}/{campo}"


def _banco():
    from ..campo import visao
    return visao._base(), visao._sessao()


def ler_todas() -> list[dict]:
    """O livro inteiro, sem cópia em memória: quem acabou de assumir tem de se ver na tela."""
    return livros.ler(*_banco(), LIVRO, ABA)


def _quando(v):
    try:
        return datetime.fromisoformat(str(v or "").replace("Z", "+00:00")).astimezone(_BRT)
    except ValueError:
        return None


def _int(v):
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _abre(cofre, l: dict) -> dict:
    quem, texto = {}, ""
    if cofre:
        try:
            quem = json.loads(cofre.decifrar(l.get("quem_cifrado") or "", _ctx(l.get("id"), "quem")))
        except Exception:           # noqa: BLE001 — cifra de outra chave ou adulterada: sai sem nome
            quem = {}
        if l.get("texto_cifrado"):
            try:
                texto = cofre.decifrar(l.get("texto_cifrado"), _ctx(l.get("id"), "texto"))
            except Exception:       # noqa: BLE001
                texto = ""
    q = _quando(l.get("registrado_em"))
    return {"id": l.get("id"), "troca": _quando(l.get("troca_em")), "evento": str(l.get("evento") or ""), "quando": q,
            "hora": q.strftime("%d/%m %H:%M") if q else "—", "hmac": str(l.get("pessoa_hmac") or ""),
            "nome": quem.get("nome") or quem.get("email") or "", "texto": texto,
            "abertas": _int(l.get("abertas_qtd")), "criticas": _int(l.get("criticas_qtd"))}


def por_troca(linhas: list[dict] | None = None) -> dict:
    """{troca (datetime): {"passagens": [evento], "assumiu": [evento]}}, cada lista na ordem da gravação. `linhas` = o
    livro (os testes passam; a tela lê do banco)."""
    cofre = _cofre_ou_nada()
    eventos = [_abre(cofre, l) for l in (ler_todas() if linhas is None else linhas)]
    ordem = {id(e): i for i, e in enumerate(eventos)}
    eventos.sort(key=lambda e: (e["quando"] or datetime.min.replace(tzinfo=_BRT), ordem[id(e)]))
    out: dict = {}
    for e in eventos:
        if e["troca"] is None or e["evento"] not in EVENTOS:
            continue
        x = out.setdefault(e["troca"], {"passagens": [], "assumiu": []})
        x["passagens" if e["evento"] == "passagem" else "assumiu"].append(e)
    return out


def situacao(troca: datetime, x: dict | None, agora: datetime) -> str:
    """A situação de uma troca: sem passagem até a tolerância vencer é "aguardando"; depois, "sem registro" (R12: ela
    não aconteceu). Com passagem, "assumida" quando alguém assumiu; senão aguarda até a tolerância, e depois fica "ninguém
    assumiu"."""
    x = x or {"passagens": [], "assumiu": []}
    venceu = _brt(agora) >= troca + timedelta(minutes=TOLERANCIA_MIN)
    if not x["passagens"]:
        return "sem_registro" if venceu else "aguardando"
    if x["assumiu"]:
        return "assumida"
    return "sem_assumir" if venceu else "registrada"


def destino(agora: datetime, eventos: dict, eu: str | None) -> datetime:
    """A troca a que vai a passagem de `eu` escrita agora: a de `troca_da_passagem`, salvo se ela já passou e `eu` a
    assumiu. Quem assumiu está no turno novo, e o que escreve é para o turno seguinte (sem isto, quem entrou às 18:00 e
    escrevesse às 18:30 passaria o turno que acabou de receber)."""
    t = troca_da_passagem(agora)
    x = eventos.get(t) or {}
    if t <= _brt(agora) and eu and eu in {a["hmac"] for a in x.get("assumiu") or []}:
        return troca_seguinte(agora)
    return t


def atraso_min(troca: datetime, x: dict) -> int | None:
    """Quantos minutos depois da troca a 1ª passagem foi escrita (None quando foi antes ou não houve)."""
    p = (x or {}).get("passagens") or []
    if not p or not p[0]["quando"]:
        return None
    m = int((p[0]["quando"] - troca).total_seconds() // 60)
    return m if m > 0 else None


def painel(agora: datetime, linhas: list[dict] | None = None, eu: str | None = None) -> dict:
    """O que a tela mostra: o turno em curso, para qual troca vai uma passagem escrita agora, a troca que quem está
    entrando assume e o histórico de 7 dias, com a conta das trocas que já fecharam (a tolerância vencida)."""
    eventos = por_troca(linhas)
    hist = []
    for t in trocas_do_historico(agora):
        x = eventos.get(t) or {"passagens": [], "assumiu": []}
        sit = situacao(t, x, agora)
        hist.append({"troca": t, "rotulo": rotulo_da_troca(t), "situacao": sit, "situacao_rotulo": SITUACOES[sit][0],
                     "tom": SITUACOES[sit][1], "passagens": x["passagens"], "assumiu": x["assumiu"],
                     "atraso_min": atraso_min(t, x),
                     "fechou": _brt(agora) >= t + timedelta(minutes=TOLERANCIA_MIN)})
    fechadas = [h for h in hist if h["fechou"]]
    conta = {s: sum(1 for h in fechadas if h["situacao"] == s) for s in SITUACOES}
    registradas = len(fechadas) - conta["sem_registro"]
    em_curso = troca_anterior(agora)
    assumiveis = []
    for t in trocas_que_se_pode_assumir(agora):
        x = eventos.get(t) or {"passagens": [], "assumiu": []}
        passou = {p["hmac"] for p in x["passagens"]}
        assumiu = {a["hmac"] for a in x["assumiu"]}
        assumiveis.append({"troca": t, "rotulo": rotulo_da_troca(t), "passagens": x["passagens"],
                           "assumiu": x["assumiu"], "situacao": situacao(t, x, agora),
                           "eu_passei": bool(eu and eu in passou), "eu_assumi": bool(eu and eu in assumiu)})
    vai = destino(agora, eventos, eu)
    return {
        "agora": _brt(agora),
        "turno": turno_que_comeca(em_curso), "turno_inicio": em_curso, "turno_fim": troca_seguinte(agora),
        "destino": vai, "destino_rotulo": rotulo_da_troca(vai),
        "destino_atrasada": vai <= _brt(agora),
        "destino_passagens": (eventos.get(vai) or {}).get("passagens") or [],
        "assumiveis": assumiveis,
        "historico": hist,
        "fechadas": len(fechadas), "registradas": registradas, "assumidas": conta["assumida"],
        "sem_registro": conta["sem_registro"], "sem_assumir": conta["sem_assumir"],
        "pct_registradas": round(100 * registradas / len(fechadas)) if fechadas else None,
    }


# ── gravar ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def codigo(usuario) -> str | None:
    """O código da pessoa do login (o mesmo do App e dos setores), ou None sem e-mail ou sem a NEXUS_PESSOA_HMAC."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    email = str((usuario or {}).get("email") or "").strip().lower()
    return codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) if email else None


def _linha(troca: datetime, evento: str, usuario: dict, texto: str = "", abertas: int | None = None,
           criticas: int | None = None) -> dict:
    cfg = current_app.config
    email = str((usuario or {}).get("email") or "").strip().lower()
    nome = " ".join(str((usuario or {}).get("nome") or "").split()) or email
    cod = codigo(usuario)
    if not email:
        raise Recusada("Entre com o seu login (Fracttal ou Microsoft) para registrar a passagem: a senha de "
                       "administrador não diz quem é a pessoa")
    if not cod:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    cofre = _cofre()
    eid = uuid.uuid4().hex[:12]
    agora = datetime.now(timezone.utc)
    return {"id": eid, "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "troca_em": troca.isoformat(),
            "data_id_troca": int(troca.strftime("%Y%m%d")), "turno_que_sai": turno_que_sai(troca).id, "evento": evento,
            "pessoa_hmac": cod,
            "quem_cifrado": cofre.cifrar(json.dumps({"nome": nome, "email": email}, ensure_ascii=False), _ctx(eid, "quem")),
            "texto_cifrado": cofre.cifrar(texto, _ctx(eid, "texto")) if texto else None,
            "abertas_qtd": abertas, "criticas_qtd": criticas}


def _publicar(linhas: list[dict]) -> None:
    base, sessao = _banco()
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in linhas])},
                    base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)


def limpar_texto(texto: str) -> str:
    return "\n".join(" ".join(l.split()) for l in str(texto or "").strip().splitlines()).strip()


def passar(usuario: dict, texto: str, agora: datetime, abertas: int | None = None, criticas: int | None = None) -> dict:
    """Quem sai registra o que o próximo turno precisa saber. Vai para a troca de `destino`; mais de um operador pode
    escrever na mesma troca (cada um a sua carteira)."""
    texto = limpar_texto(texto)
    if not texto:
        raise Recusada("Escreva o que o próximo turno precisa saber (se não há nada pendente, diga isso) antes de "
                       "registrar")
    if len(texto) > TEXTO_MAX:
        raise Recusada(f"A passagem passou de {TEXTO_MAX} caracteres")
    nova = _linha(troca_da_passagem(agora), "passagem", usuario, texto, abertas, criticas)
    with _TRAVA:
        linhas = ler_todas()
        troca = destino(agora, por_troca(linhas), nova["pessoa_hmac"])
        nova.update(troca_em=troca.isoformat(), data_id_troca=int(troca.strftime("%Y%m%d")),
                    turno_que_sai=turno_que_sai(troca).id)
        _publicar(linhas + [nova])
    return nova


def assumir(usuario: dict, troca: datetime, agora: datetime) -> dict:
    """Quem entra diz que leu e assumiu. Só a troca que começou o turno em curso (ou a seguinte, dentro da tolerância),
    só com passagem registrada e nunca a própria passagem."""
    troca = _brt(troca)
    if troca not in trocas_que_se_pode_assumir(agora):
        raise Recusada("Esta troca já passou: assume-se só a troca do turno em curso")
    nova = _linha(troca, "assumiu", usuario)
    with _TRAVA:
        linhas = ler_todas()
        x = por_troca(linhas).get(troca) or {"passagens": [], "assumiu": []}
        if not x["passagens"]:
            raise Recusada("A passagem desta troca ainda não foi registrada: sem registro, ela não aconteceu")
        if nova["pessoa_hmac"] in {p["hmac"] for p in x["passagens"]}:
            raise Recusada("Quem passou o turno não assume a própria passagem")
        if nova["pessoa_hmac"] in {a["hmac"] for a in x["assumiu"]}:
            raise Recusada("Você já assumiu este turno")
        _publicar(linhas + [nova])
    return nova
