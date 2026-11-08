"""Grava os chamados de garantia em aberto para o App de Campo (08/11/2026): o livro `nexus_chamados_abertos` (o fato e as
regras: `nexus/dados/fato_chamado_aberto.py`).

Desenho de 08/11/2026, passo 2 ("a leitura do Nexus para o App", dono: o OS Creator). Quem grava é o servidor, de 10 em 10
minutos, a partir do que o OS Creator JÁ tem na memória, sem pedido novo ao Fracttal (a cota de 200 por minuto é da empresa):
- a lista central de OS (`os_creator/os_central.py`), que o `os_leitor` mantém pela credencial da empresa e que vê TODAS as OS:
  as Inspeções de garantia e as OS de acompanhamento, com status, etiquetas, ativo, data e a nota do bloco do chamado;
- os tickets da cópia do quadro do Acompanhamento de chamados (`os_web/rotas_acomp.py`, a cópia "TODOS"), lidos com a sessão
  de quem abriu o quadro, até `TICKETS_MAX_S`; sem ela, a coluna da administrativa já inspecionada fica vazia (não sei);
- a dimensão de equipamento do banco (`nexus_equipamentos · dim_equipamento`), relida de hora em hora, para os IDs.

GUARDAS:
- Desligado por padrão (`LIGADO_PADRAO`; `NEXUS_CHAMADOS_ABERTOS=1` liga numa máquina, `0` desliga): liga o Levi, depois da
  prova. Ligar no servidor é um commit que troca o `LIGADO_PADRAO` (a T.I. não precisa mexer no .env).
- Só grava com a lista central FRESCA (a última leitura dela há até `FRESCA_S` e uma leitura até o topo, a marca d'água). No
  PC o leitor não roda (só o `servir.py` o liga): a lista não é fresca e nada se grava. Lista velha = foto não regerada, e o
  App, vendo a `atualizacao` velha, trata como "não li" (nunca como "não tem chamado").
- Sem a NEXUS_PESSOA_HMAC não grava (a linha iria sem assinatura e o App a ignoraria); sem o GRIDCO_SQL_TOKEN, também não.
- A leitura do banco que falha (a foto anterior, a dimensão) derruba a volta: nada se grava por cima do que não se leu.
- O livro é só deste laço (o `livros.publicar` troca o livro inteiro: dividir o `nexus_chamados` com a gravação de hora em
  hora do `fato_chamado` faria uma apagar a aba da outra).
Os minutos são os da lista de minutos ocupados (`nexus/casca/minutos_ocupados.py`, `CHAMADOS_ABERTOS`): logo depois de cada
leitura dos 7 dias da lista central.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from ...casca import minutos_ocupados as MO
from ...dados import fato_chamado_aberto as F
from ...dados import fatos as D
from ...dados import livros

LIGADO_PADRAO = False
FRESCA_S = 30 * 60              # a lista central só vale com a última leitura há até isto (a mesma régua do `os_central.FRESCA_S`)
TICKETS_MAX_S = 2 * 3600        # a cópia do quadro só vale até isto (o `rotas_acomp.VELHA_MAX`)
DIM_TTL_S = 3600                # a dimensão de equipamento é relida de hora em hora (a carga a regrava de hora em hora)
PRIMEIRA_S = 180                # a 1ª volta depois de subir (o boot lê o disco da lista central)
_BRT = timezone(timedelta(hours=-3))
_ESTADO = {"thread": None, "parar": threading.Event(), "ultimo": None, "dim": None}
log = logging.getLogger("nexus.oscreator.chamados_abertos")


def ligado(config) -> bool:
    v = str(os.environ.get("NEXUS_CHAMADOS_ABERTOS") or config.get("NEXUS_CHAMADOS_ABERTOS") or "").strip()
    if v in ("0", "1"):
        return v == "1"
    return LIGADO_PADRAO


def _base(config) -> str:
    from ...cadastro.ligacoes import BASE_API
    return (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def _modulo(nome: str):
    """O módulo do clone já carregado (o MESMO das telas); None se o clone ainda não o importou neste processo."""
    return sys.modules.get(nome)


def lista_central():
    """(registros, lido_em em datetime ou None, a_conferir, fresca) da lista central de OS deste processo."""
    oc = _modulo("os_central")
    if oc is None:
        return (), None, frozenset(), False
    lista = oc.atual()
    lido = datetime.fromtimestamp(lista.lido_em, timezone.utc) if lista.lido_em else None
    fresca = bool(lido and lista.marca and time.time() - lista.lido_em <= FRESCA_S)
    return tuple(lista.ordem), lido, frozenset(lista.a_conferir), fresca


def tickets_do_quadro():
    """({id da administrativa: ticket}, quando foi lida) da cópia "TODOS" do quadro, se ela tem até `TICKETS_MAX_S`;
    ({}, None) sem ela. Só a memória (e o disco, que o próprio quadro carrega): nada vai ao Fracttal."""
    ra = _modulo("os_web.rotas_acomp")
    if ra is None:
        return {}, None
    try:
        idade, v = ra._guardado_com_idade(("acomp", "TODOS"))
    except Exception:                       # noqa: BLE001 — sem a cópia: a coluna fica vazia, a volta segue
        log.exception("chamados em aberto: a cópia do quadro não foi lida")
        return {}, None
    if not isinstance(v, dict) or idade is None or idade >= TICKETS_MAX_S:
        return {}, None
    return dict(v.get("tickets") or {}), datetime.now(timezone.utc) - timedelta(seconds=idade)


def dimensao(base, sessao, agora_s: float | None = None) -> dict:
    """{código canônico: (equipamento_id, usina_id)} da dimensão de equipamento, guardada `DIM_TTL_S`."""
    agora_s = time.monotonic() if agora_s is None else agora_s
    g = _ESTADO["dim"]
    if g and agora_s - g[0] < DIM_TTL_S:
        return g[1]
    from ...dados.equipamento import canon
    out = {}
    for r in livros.ler(base, sessao, "nexus_equipamentos", "dim_equipamento"):
        c, eid = canon(r.get("codigo")), D._id(r.get("equipamento_id"))
        if c and eid:
            out[c] = (eid, D._id(r.get("usina_id")))
    _ESTADO["dim"] = (agora_s, out)
    return out


def publicar(config, sessao=None, *, lista=None, tickets=None, equip=None, agora: datetime | None = None) -> dict:
    """Uma volta: monta a foto e grava o livro (conferido depois de gravar, `livros.publicar`). Devolve só contagens.
    `lista` = (registros, lido_em, a_conferir, fresca) e `tickets` = (dict, lido_em) servem aos testes."""
    import requests
    agora = agora or datetime.now(timezone.utc)
    registros, lido, a_conferir, fresca = lista if lista is not None else lista_central()
    if not fresca:
        return {"pulou": "a lista central de OS não está fresca neste processo (o leitor só roda no servidor)"}
    chave = config.get("NEXUS_PESSOA_HMAC")
    if not chave:
        return {"erro": "sem NEXUS_PESSOA_HMAC: as linhas iriam sem assinatura, não grava"}
    token = config.get("GRIDCO_SQL_TOKEN")
    if not token:
        return {"erro": "sem GRIDCO_SQL_TOKEN: não grava"}
    s = sessao or requests.Session()
    base = _base(config)
    tk, tk_em = tickets if tickets is not None else tickets_do_quadro()
    eq = equip if equip is not None else dimensao(base, s)
    a = livros.abas_conferidas(base, s, F.LIVRO, (F.ABA, F.ABA_ATU))
    anteriores = livros._linhas(base, s, a[F.ABA]) if F.ABA in a else []
    conta = {}
    lin = F.linhas(registros, tk, eq, anteriores, agora, chave, conta, a_conferir)
    atu = F.atualizacao(len(lin), agora, lido, tk_em, chave)
    gravado = livros.publicar(F.LIVRO, F.NOME_LIVRO, {F.ABA: (F.CAB, F.corpo(lin, F.CAB)),
                                                      F.ABA_ATU: (F.CAB_ATU, F.corpo([atu], F.CAB_ATU))},
                              base=base, token=token, sessao=s)
    return dict(conta, linhas=len(lin), antes=len(anteriores), tickets=len(tk), gravado=gravado)


def _espera_s(agora: datetime | None = None) -> float:
    """Até o próximo minuto de `MO.CHAMADOS_ABERTOS`, em Brasília."""
    agora = (agora or datetime.now(timezone.utc)).astimezone(_BRT)
    base = agora.replace(second=0, microsecond=0)
    for n in range(1, 61):
        alvo = base + timedelta(minutes=n)
        if alvo.minute in MO.CHAMADOS_ABERTOS:
            return (alvo - agora).total_seconds()
    return 600.0


def ligar(app) -> bool:
    """O laço, ligado só pelo `servir.py` e só com a chave ligada (`ligado`). True se ligou."""
    if _ESTADO["thread"] is not None or not ligado(app.config):
        return False

    def laco():
        espera = PRIMEIRA_S
        while not _ESTADO["parar"].wait(espera):
            with app.app_context():
                try:
                    _ESTADO["ultimo"] = publicar(app.config)
                    log.info("chamados em aberto no banco: %s",
                             {k: v for k, v in _ESTADO["ultimo"].items() if k != "gravado"})
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _ESTADO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("chamados em aberto no banco")
            espera = _espera_s()

    from ...casca import fracttal_conta
    _ESTADO["thread"] = threading.Thread(target=fracttal_conta.de_fundo("fundo:nexus-chamados-abertos", laco),
                                         name="nexus-chamados-abertos", daemon=True)
    _ESTADO["thread"].start()
    return True
