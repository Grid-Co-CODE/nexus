"""As requisições de material no Almoxarifado (12/11/2026, item 6 da 2ª rodada): o "Aceitar" pelo Nexus.

Como era (a reunião do PCM de 04/11, transcrita): o técnico põe a peça como recurso na tarefa da OS, a requisição de material
nasce sozinha no almoxarifado da usina (o movimento OUTPUT_ORDER, tipo 13), e o PCM fazia três passos no Fracttal: uma Saída
"Geral" com a OS na referência (sem ela o saldo não baixa), aprovar e mudar o status para Entrega total. O PCM pediu "encurtar
esse caminho, não ter que fazer saída, deixar mais automatizado". Decisões do Levi (12/11/2026): a requisição com peça **Rank A**
o PCM aceita no Nexus com UM clique; as de **Rank B e C** o Nexus aceita **sozinho** e registra na auditoria.

O caminho (provado no TESTE - PA em 12/11/2026, lido de volta; o adaptador em `estoque.py`): aprovar (`aprovar_requisicao`, só no
estado 3; depois da entrega o Fracttal diz `STATE_CHANGED`), a saída LIGADA à requisição (`saida_da_requisicao`, o tipo "Ordem
de Serviço" da tela de Saídas: baixa o saldo e leva a requisição sozinha a 5, Entrega total) e reler (a requisição e o saldo).

Regras, com o caso que as criou:
- **Uma função só aceita** (`aceitar`), para o clique do PCM e para o automático: relê antes (estado 3, nem cancelada, nem
  recusada), aprova se ainda não está aprovada, faz a saída e relê. Cada passo que falha para ali e vira um evento
  `requisicao_falha`; a aprovada sem saída fica "aprovada, saída falhou", e a próxima tentativa pula a aprovação.
- **O estado 4 (entrega parcial) não entra**, nem no clique: a saída do pendente não foi provada ("conclua no Fracttal").
- **Saldo insuficiente**: o Fracttal recusa a saída (o almoxarifado não aceita estoque negativo); a tela mostra o motivo, e o
  automático não tenta de novo sozinho (a requisição com falha registrada vai para "Falhas", e só o clique a tenta).
- **O dono**: a saída precisa do responsável do Fracttal de quem está na ponte (`estoque.responsavel`, pelo e-mail) e a
  aprovação da conta dele (o id e o nome, pelo catálogo de pessoas do OS Creator, como os avisos do Comando). Sem um deles,
  nada vai (409): não se grava sem dono.
- **O automático (B e C)**: o Nexus não tem conta de serviço no Fracttal e grava só com o login de quem está na ponte. Quando
  alguém do PCM com o login do Fracttal abre Almoxarifado → Requisições, a página pede o automático, e o Nexus aceita em
  segundo plano, NA SESSÃO DESSA PESSOA, as pendentes cujas peças são TODAS Rank B ou C conhecidas. Uma thread com o
  controle "gravando" (`requisicoes-auto.json`), que o deploy espera (`gravacao.com_lote_aberto`). Para ir sem ninguém abrir a
  tela, precisa de uma conta de serviço (decisão do Levi).
- **O Rank é o da peça no Fracttal** (a Classificação 2, "2. Rank A"), pelo código, no mapa da lista de peças inteira
  (`classificacao.mapa_guardado`, a cópia de 1 h da Curadoria): a "Curva ABC" do catálogo do App vem VAZIA para os Ranks do
  Fracttal (o `_almox_curva` do App só aceita a letra sozinha; a revisão do item 3, 12/11/2026), e a fila "com Rank A" pelo
  catálogo nasceria vazia. A peça fora do mapa, sem a Classificação 2 ou "1.Avariado" é a curva desconhecida, e vai para o PCM.
- **A gravação do inventário**: com a vez do almoxarifado presa (uma contagem gravando ou parada no meio) ou ele fora do modo 0,
  nada vai (a saída seria recusada depois da aprovação).
- **Nome de gente**: o `accounts_log_name` (quem decidiu no Fracttal) e a descrição do responsável só passam pela memória e
  pela tela do PCM; o livro guarda a pessoa como `pessoa_hmac`/`pessoa_id`, e o comentário e a OS só cifrados.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import current_app, jsonify, render_template, session

from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from .. import telas
from . import classificacao as CL
from . import estoque as E
from . import quem
from .erros import Conflito

JANELA_DIAS, DECIDIDAS_DIAS, SOZINHAS_DIAS = 90, 30, 30
PECAS_TTL_S, RESPONSAVEL_TTL_S = 600, 3600
COMENTARIO_MAX = 300
ESTADO_TXT = {E.NAO_ENTREGUE: "não entregue", E.ENTREGA_PARCIAL: "entrega parcial", E.ENTREGA_TOTAL: "entrega total",
              E.CANCELADA: "cancelada"}
CURVAS_SOZINHAS = ("B", "C")
ARQUIVO_AUTO = "requisicoes-auto.json"          # o deploy o espera vivo (`gravacao.com_lote_aberto`, o mesmo nome)
TELA = "/t/pcm/pecas/requisicoes"
SEM_RESPONSAVEL = ("Não achei você na lista de responsáveis do Fracttal (pelo seu e-mail): a saída precisa de um responsável, e "
                   "o Nexus não grava sem dono. Peça ao administrador do Fracttal para cadastrar o seu e-mail. Nada foi enviado.")
SEM_CONTA = ("Não achei a sua conta do Fracttal (o catálogo de pessoas do OS Creator, pelo seu e-mail): a aprovação vai no nome "
             "de quem decide. Nada foi enviado.")
JA_ANDANDO = "O Nexus já está aceitando as de Rank B e C agora: acompanhe nesta página."
_BRT = timezone(timedelta(hours=-3))
log = logging.getLogger(__name__)


class Falhou(Exception):
    """Um passo do aceite (ou da recusa) que o Fracttal não fez: já registrado no livro (`requisicao_falha`). `mensagem` é a da
    tela (o que ficou feito e o que não), `status` o HTTP da ponte (409 a recusa do Fracttal, 429 a pausa, 401 o login, 502 a
    rede) e `causa` o erro do Fracttal (o automático para no 429 e no login)."""

    def __init__(self, mensagem: str, status: int, causa: Exception):
        super().__init__(mensagem)
        self.mensagem, self.status, self.causa = mensagem, status, causa


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _chave(codigo) -> str:
    return "".join(str(codigo or "").split()).upper()


def _quando_txt(iso) -> str:
    """"12/11 às 09:30" (Brasília) de uma data do Fracttal ou do livro; o que não é data volta vazio."""
    try:
        return E.instante(iso).astimezone(_BRT).strftime("%d/%m às %H:%M")
    except ValueError:
        return ""


def _num(v) -> float | None:
    return A.numero(v)


# ── as peças e a curva ──────────────────────────────────────────────────────────────────────────────────────────────────
def pecas_com_curva(linhas: list[dict], curvas: dict | None) -> list[dict]:
    """As peças da requisição (as linhas do `movements_details_list`) para a tela e a regra: o código, o nome, a quantidade, o
    pendente e a CURVA, a letra do Rank da peça no Fracttal pelo código (`curvas`, do `contexto`: "A", "B" ou "C"; "" é a curva
    desconhecida: a peça fora do mapa, sem a Classificação 2 ou "1.Avariado"). A desconhecida nunca é A nem B nem C."""
    out = []
    for l in linhas:
        codigo = " ".join(str(l.get("code") or "").split())
        curva = (curvas or {}).get(_chave(codigo), "") if codigo else ""
        out.append({"id_item": A._id(l.get("id_item")), "codigo": codigo,
                    "nome": " ".join(str(l.get("items_description") or "").split()),
                    "unidade": " ".join(str(l.get("units_description") or "").split()).lower(), "qtd": _num(l.get("qty")),
                    "pendente": _num(l.get("qty_pending")), "curva": curva if curva in ("A", "B", "C") else ""})
    return out


def de_quem(pecas: list[dict] | None) -> str:
    """"sozinha" quando TODAS as peças são Rank B ou C conhecidas (o Nexus aceita sozinho); senão "pcm" (uma A, uma de curva
    desconhecida, ou as peças que não se leram: o PCM decide)."""
    return "sozinha" if pecas and all(p["curva"] in CURVAS_SOZINHAS for p in pecas) else "pcm"


def recusada(r: dict) -> bool:
    """A não aprovada COM a data da decisão foi recusada (o que o Fracttal grava; 12/11/2026)."""
    return not r["aprovada"] and bool(r["decidida_em"])


def pendente(r: dict) -> bool:
    """Ainda a aceitar: não entregue (estado 3) e não recusada. A aprovada sem a saída também (falta a saída)."""
    return r["estado"] == E.NAO_ENTREGUE and not recusada(r)


# ── o que o Nexus já fez (o livro do inventário) ──────────────────────────────────────────────────────────────────────────
def _do_livro(cfg, eventos: list[dict], agora: datetime) -> tuple[dict, list[dict]]:
    """({requisição: a última falha}, as aceitas sozinhas dos últimos 30 dias), pelos eventos. A falha decifra o porquê (o texto
    do Fracttal ou o nosso); a aceita sozinha junta as peças da mesma requisição, com o saldo antes e depois."""
    falhas, sozinhas = {}, {}
    corte = agora - timedelta(days=SOZINHAS_DIAS)
    for i, e in enumerate(eventos):
        t, rid = A._txt(e.get("tipo")), A._id(e.get("movimento_fracttal"))
        if not rid or not t.startswith("requisicao_"):
            continue
        quando = A._txt(e.get("quando"))
        if t == "requisicao_falha":
            if rid not in falhas or (quando, i) >= falhas[rid]["_marca"]:
                d = F.decifrar(cfg, F.ABA_EVENTO, e)
                falhas[rid] = {"_marca": (quando, i), "quando": quando, "quando_txt": _quando_txt(quando),
                               "motivo": A._txt(d.get("motivo")) or "o motivo não se lê agora", "passo": A._txt(d.get("passo")),
                               "por": A._txt(d.get("por")), "os": A._txt(d.get("os"))}
        elif t in ("requisicao_aceita", "requisicao_aceita_sozinha", "requisicao_recusada"):
            falhas.pop(rid, None)                  # o livro está na ordem da gravação: a falha de antes do aceite já passou
        if t == "requisicao_aceita_sozinha":
            try:
                recente = E.instante(quando) >= corte
            except ValueError:
                recente = False
            if not recente:
                continue
            g = sozinhas.setdefault(rid, {"id": rid, "quando": quando, "almox": A._id(e.get("id_almoxarifado")), "pecas": [],
                                          "os": "", "confirmada": True})
            if not g["os"]:
                d = F.decifrar(cfg, F.ABA_EVENTO, e)
                g["os"], g["confirmada"] = A._txt(d.get("os")), d.get("confirmada", True) is not False
            g["quando"] = max(g["quando"], quando)
            g["pecas"].append({"codigo": A._txt(e.get("codigo")), "antes": _num(e.get("de_qtd")),
                               "depois": _num(e.get("para_qtd")), "qtd": _num(e.get("contado_qtd"))})
    lista = sorted(sozinhas.values(), key=lambda g: g["quando"], reverse=True)
    for g in lista:
        g["quando_txt"] = _quando_txt(g["quando"])
    for f in falhas.values():
        f.pop("_marca", None)
    return falhas, lista


# ── a lista (a tela) ────────────────────────────────────────────────────────────────────────────────────────────────────
_PECAS: dict = {}
_TRAVA_PECAS = threading.Lock()


def pecas_guardadas(estoque, id_requisicao: str, relogio=time.monotonic) -> list[dict]:
    """As peças de uma requisição pela cópia de 10 min por id (a lista as lê de cada pendente a cada abertura; a cota é de
    todos). O aceite NÃO usa esta cópia: a saída manda as linhas de agora."""
    agora = relogio()
    with _TRAVA_PECAS:
        g = _PECAS.get(id_requisicao)
        if g and agora - g[0] < PECAS_TTL_S:
            return [dict(l) for l in g[1]]
    linhas = estoque.pecas_da_requisicao(id_requisicao)
    with _TRAVA_PECAS:
        _PECAS[id_requisicao] = (agora, [dict(l) for l in linhas])
    return linhas


def limpar() -> None:
    with _TRAVA_PECAS:
        _PECAS.clear()
    with _TRAVA_RESP:
        _RESPONSAVEIS.clear()


def contexto(cfg, mapa: dict | None) -> dict:
    """O que a lista e o aceite precisam, lido NO PEDIDO (a thread do automático não tem o app): a letra do Rank de cada peça
    pelo código (`curvas`, do mapa das peças do Fracttal, `classificacao.mapa_guardado`), o nome, a usina e o `usina_id` de cada
    almoxarifado (a de-para que o Almoxarifado já usa) e os almoxarifados de teste."""
    from .. import almoxarifado
    d = almoxarifado.montar().dados or {}
    curvas = {codigo: CL.letra_do_rank(g.get("classificacao_2")) for codigo, g in (mapa or {}).items()}
    almoxes = {A._id(c["id"]): {"nome": A._txt(c.get("nome")), "usina": A._txt(c.get("usina")), "usina_id": None}
               for c in d.get("por_almoxarifado", []) if c.get("id")}
    for l in d.get("linhas", []):
        a = almoxes.get(A._id(l.get("id_almox")))
        if a is not None and a["usina_id"] is None and l.get("usina_id"):
            a["usina_id"] = int(l["usina_id"])
    return {"curvas": curvas, "almoxes": almoxes, "teste": set(A.ids_de_teste(cfg))}


def montar(cfg, estoque, ctx: dict, agora: datetime | None = None) -> dict:
    """A fila para a tela: as requisições dos últimos 90 dias (`estoque.requisicoes`), com as peças das pendentes (a cópia de 10
    min) e a curva de cada uma, em grupos:
    - `para_pcm`: as pendentes com peça Rank A ou de curva desconhecida (o "Aceitar" e o "Recusar");
    - `sozinhas`: as pendentes só de B e C conhecidas, que o automático aceita (`ids_sozinhas`, sem as que já falharam);
    - `falhas`: as pendentes com uma falha registrada (o motivo; a aprovada sem saída diz "aprovada, saída falhou");
    - `parciais`: as de entrega parcial (estado 4: "conclua no Fracttal");
    - `aceitas_sozinhas`: as que o automático aceitou nos últimos 30 dias, com o saldo antes e depois (o livro);
    - `decididas`: as aprovadas e recusadas nos últimos 30 dias (o Fracttal: quem, o comentário, quando).
    Dentro de cada grupo, a mais nova primeiro. O almoxarifado de teste fica de fora. O livro do inventário que não se lê agora
    não derruba a lista (`livro_lido` falso), e então o automático não roda: sem saber das falhas, ele tentaria de novo."""
    agora = agora or _agora()
    reqs = [r for r in estoque.requisicoes(JANELA_DIAS, agora) if r["id_almox"] not in ctx["teste"]]
    try:
        falhas, aceitas_sozinhas = _do_livro(cfg, F.ler(cfg)[F.ABA_EVENTO], agora)
        livro_lido = True
    except F.Recusada:
        falhas, aceitas_sozinhas, livro_lido = {}, [], False
    almoxes = ctx["almoxes"]
    grupos = {"para_pcm": [], "sozinhas": [], "falhas": [], "parciais": [], "decididas": []}
    corte = agora - timedelta(days=DECIDIDAS_DIAS)
    for r in reqs:
        a = almoxes.get(r["id_almox"]) or {}
        x = dict(r, almox=a.get("nome") or r["almox_nome"] or f"Almoxarifado {r['id_almox']}", usina=a.get("usina") or "",
                 estado_txt=ESTADO_TXT.get(r["estado"], f"estado {r['estado']}"), criada_txt=_quando_txt(r["criada_em"]),
                 decidida_txt=_quando_txt(r["decidida_em"]), recusada=recusada(r), pecas=None, erro_pecas="",
                 falha=falhas.get(r["id"]))
        if pendente(r):
            try:
                x["pecas"] = pecas_com_curva(pecas_guardadas(estoque, r["id"]), ctx["curvas"])
            except (E.ErroFracttal, OSError) as ex:
                x["erro_pecas"] = f"não consegui ler as peças agora ({type(ex).__name__})"
            x["de_quem"] = de_quem(x["pecas"])
            x["rank_a"] = any(p["curva"] == "A" for p in x["pecas"] or [])
            grupos["falhas" if x["falha"] else "sozinhas" if x["de_quem"] == "sozinha" else "para_pcm"].append(x)
        elif r["estado"] == E.ENTREGA_PARCIAL and not recusada(r):
            grupos["parciais"].append(x)
        if r["decidida_em"] and not pendente(r):
            try:
                if E.instante(r["decidida_em"]) >= corte:
                    grupos["decididas"].append(x)
            except ValueError:
                pass
    for g in grupos.values():
        g.sort(key=lambda x: (x["criada_em"], int(x["id"] or 0)), reverse=True)
    grupos["decididas"].sort(key=lambda x: x["decidida_em"], reverse=True)
    for g in aceitas_sozinhas:
        a = almoxes.get(g["almox"]) or {}
        g["almox_nome"] = a.get("nome") or f"Almoxarifado {g['almox']}"
    return {**grupos, "aceitas_sozinhas": aceitas_sozinhas[:20], "livro_lido": livro_lido,
            "ids_sozinhas": [x["id"] for x in grupos["sozinhas"]],
            "n_total": len(reqs)}


# ── o dono: a conta e o responsável no Fracttal ─────────────────────────────────────────────────────────────────────────
_RESPONSAVEIS: dict = {}
_TRAVA_RESP = threading.Lock()


def conta_do_fracttal(email: str, nome_da_sessao: str = "") -> dict | None:
    """`{"id", "nome"}` da conta do Fracttal de quem decide: o `id_account` pelo catálogo de pessoas do OS Creator (o mesmo
    caminho dos avisos do Comando, `comando.avisos._do_fracttal`: a ligação de Base → Acessos, depois o e-mail) e o nome que o
    Fracttal grava (o do catálogo, senão o da sessão do OS Creator). None sem os dois: a aprovação não vai sem eles."""
    from ...comando import avisos
    _idp, ida, nome = avisos._do_fracttal(email)
    nome = " ".join(str(nome or nome_da_sessao or "").split())
    return {"id": str(ida), "nome": nome} if ida and nome else None


def responsavel_de(estoque, email: str, relogio=time.monotonic) -> dict | None:
    """O responsável do Fracttal de quem está na ponte (`estoque.responsavel`, pelo e-mail), guardado 1 h na memória do processo
    (a lista de responsáveis são páginas da cota de todos). Só o achado fica guardado; nada em arquivo nem em log."""
    e = str(email or "").strip().lower()
    agora = relogio()
    with _TRAVA_RESP:
        g = _RESPONSAVEIS.get(e)
        if g and agora - g[0] < RESPONSAVEL_TTL_S:
            return dict(g[1])
    achado = estoque.responsavel(e)
    if achado:
        with _TRAVA_RESP:
            _RESPONSAVEIS[e] = (agora, dict(achado))
    return achado


# ── aceitar e recusar ───────────────────────────────────────────────────────────────────────────────────────────────────
def _id_da_requisicao(id_requisicao) -> str:
    rid = A._id(id_requisicao)
    if not rid.isdigit():
        raise ValueError("Requisição que não existe: recarregue a página. Nada foi enviado.")
    return rid


def _conferir_estado(r: dict | None, rid: str, ctx: dict) -> dict:
    """A requisição relida agora tem de estar a aceitar: na lista, fora do almoxarifado de teste, no estado 3 e não recusada.
    `Conflito` (409) com o porquê; nada vai ao Fracttal."""
    if r is None or r["id_almox"] in ctx["teste"]:
        raise Conflito(f"A requisição {rid} não está na lista do Fracttal dos últimos {JANELA_DIAS} dias: recarregue a página. "
                       "Nada foi enviado.")
    os_ = f" da OS {r['os']}" if r["os"] else ""
    if r["estado"] == E.CANCELADA:
        raise Conflito(f"A requisição{os_} foi cancelada no Fracttal: nada foi enviado.")
    if r["estado"] == E.ENTREGA_PARCIAL:
        raise Conflito(f"A requisição{os_} está em entrega parcial: conclua no Fracttal (a saída do pendente ainda não foi "
                       "provada pelo Nexus). Nada foi enviado.")
    if r["estado"] == E.ENTREGA_TOTAL:
        raise Conflito(f"A requisição{os_} já está entregue (entrega total) no Fracttal: nada foi enviado.")
    if r["estado"] != E.NAO_ENTREGUE:
        raise Conflito(f"A requisição{os_} está num estado que o Nexus não aceita ({r['estado']}): nada foi enviado.")
    if recusada(r):
        raise Conflito(f"A requisição{os_} foi recusada no Fracttal: nada foi enviado.")
    return r


def _quem_cols(ctx: dict, quem_: dict, id_almox: str) -> dict:
    """A usina pela de-para (com a linhagem) e a pessoa como código: as colunas comuns dos eventos da requisição."""
    uid = (ctx["almoxes"].get(id_almox) or {}).get("usina_id")
    return {"id_almoxarifado": id_almox or None, "usina_id": uid, "usina_ligada_por": F.USINA_LIGADA_POR[0] if uid else None,
            **(quem_ or {})}


def _falha(cfg, ctx, r, quem_, por: str, passo: str, ex: Exception) -> str:
    """Registra a falha de um passo (o evento `requisicao_falha`, com o porquê cifrado) e devolve o texto para a tela. O livro
    que não grava agora não esconde a falha do Fracttal: só vai ao log (o tipo)."""
    motivo = (ex.mensagem if isinstance(ex, E.ErroFracttal) else
              "o Fracttal pediu uma pausa (o limite de pedidos da empresa)" if isinstance(ex, E.Limite) else
              "o login do Fracttal expirou" if isinstance(ex, E.SemLogin) else
              f"o Fracttal não respondeu ({type(ex).__name__}): pode ter gravado; confira antes de repetir")
    try:
        F.acrescentar(cfg, F.ABA_EVENTO, [{"tipo": "requisicao_falha", "movimento_fracttal": r["id"],
                                           **_quem_cols(ctx, quem_, r["id_almox"]),
                                           "dados": {"motivo": motivo, "passo": passo, "por": por, "os": r["os"]}}])
    except (F.Recusada, ValueError) as ex2:
        log.warning("requisições: a falha da requisição %s não foi ao livro (%s)", r["id"], type(ex2).__name__)
    return motivo


def _status(ex: Exception) -> int:
    return 429 if isinstance(ex, E.Limite) else 401 if isinstance(ex, E.SemLogin) else 409 if isinstance(ex, E.Recusado)         else 502


def aceitar(cfg, estoque, id_requisicao, *, por: str, ctx: dict, quem_: dict, conta: dict | None,
            responsavel: dict | None, comentario: str = "", agora: datetime | None = None) -> dict:
    """Aceita UMA requisição (o clique do PCM, `por` "pcm", e o automático, `por` "sozinha"): relê, aprova se ainda não está
    aprovada (o comentário do PCM ou "Aceita pelo Nexus por <nome>"), faz a saída ligada e relê a requisição e o saldo de cada
    peça. `{"ok", "confirmada", "mensagem", "saida"}`.

    Recusa (`Conflito`, 409, nada vai) a que não está a aceitar (`_conferir_estado`), a sem responsável, a sem conta quando
    precisa aprovar, a sem peças, no automático a que tem peça Rank A ou desconhecida, e o almoxarifado com a vez presa por uma
    gravação de inventário ou fora do modo 0. O passo que falha no Fracttal para ali, vira o evento `requisicao_falha` e sobe
    (a rota o diz com o status de sempre); a aprovada sem saída, a próxima tentativa pula a aprovação. Cada peça aceita vira um
    evento (`requisicao_aceita` ou `requisicao_aceita_sozinha`) com o saldo antes e depois e a curva."""
    from . import gravacao
    rid = _id_da_requisicao(id_requisicao)
    texto = " ".join(str(comentario or "").split())
    if len(texto) > COMENTARIO_MAX:
        raise ValueError(f"O comentário passa de {COMENTARIO_MAX} letras.")
    r = _conferir_estado(estoque.reler_requisicao(rid, JANELA_DIAS, agora), rid, ctx)
    if not responsavel:
        raise Conflito(SEM_RESPONSAVEL)
    if not r["aprovada"] and not conta:
        raise Conflito(SEM_CONTA)
    linhas = estoque.pecas_da_requisicao(rid)
    if not linhas:
        raise Conflito("A requisição veio sem peças do Fracttal: nada foi enviado. Confira na tela do Fracttal.")
    pecas = pecas_com_curva(linhas, ctx["curvas"])
    if por == "sozinha" and de_quem(pecas) != "sozinha":
        raise Conflito("A requisição tem peça Rank A ou de curva desconhecida: é o PCM que aceita. Nada foi enviado.")
    almox = r["id_almox"]
    presa = gravacao.vez_presa(cfg, almox)
    if presa:
        raise Conflito(f"Nada foi enviado: {presa.rstrip('.')}.")
    modo = estoque.modo(almox)
    if modo != 0:
        raise Conflito(f"Nada foi enviado: o almoxarifado está no modo {modo} no Fracttal (ajuste ou inventário aberto); a "
                       "saída não passa. Tente depois de fechado.")
    antes = estoque.ler(almox)
    passo = "aprovar"
    try:
        if not r["aprovada"]:
            padrao = (f"Aceita pelo Nexus por {conta['nome']}" if por == "pcm"
                      else f"Aceita pelo Nexus (Rank B ou C), na sessão de {conta['nome']}")
            estoque.aprovar_requisicao(rid, texto or padrao, conta)
        passo = "saida"
        saida = estoque.saida_da_requisicao(r, linhas, responsavel)
    except (E.ErroFracttal, E.Limite, E.SemLogin, OSError) as ex:
        motivo = _falha(cfg, ctx, r, quem_, por, passo, ex)
        log.warning("requisições: a requisição %s parou no passo %s (%s)", rid, passo, type(ex).__name__)
        os_ = f" da OS {r['os']}" if r["os"] else ""
        texto_ = (f"Não aceitei a requisição{os_}: o Fracttal não aprovou ({motivo}). Nada mudou nela." if passo == "aprovar" else
                  f"A requisição{os_} ficou aprovada, mas a saída não passou ({motivo}). Ela está em Falhas; a próxima "
                  "tentativa pula a aprovação.")
        raise Falhou(texto_, _status(ex), ex) from ex
    # reler: a requisição (5 e aprovada) e o saldo de cada peça. A releitura que falha não desfaz nada: diz que não confirmou
    try:
        depois_r = estoque.reler_requisicao(rid, JANELA_DIAS, agora)
        depois = estoque.ler(almox)
    except (E.ErroFracttal, E.Limite, E.SemLogin, OSError):
        depois_r, depois = None, {}
    confirmada = bool(depois_r) and depois_r["estado"] == E.ENTREGA_TOTAL and depois_r["aprovada"]
    tipo = "requisicao_aceita" if por == "pcm" else "requisicao_aceita_sozinha"
    base = _quem_cols(ctx, quem_, almox)
    eventos = [{"tipo": tipo, "movimento_fracttal": rid, **base, "id_item": p["id_item"] or None,
                "codigo": p["codigo"][:60] or None, "contado_qtd": p["qtd"],
                "de_qtd": (antes.get(p["id_item"]) or {}).get("saldo"), "para_qtd": (depois.get(p["id_item"]) or {}).get("saldo"),
                "dados": {"os": r["os"], "curva": p["curva"], "saida": str(saida), "por": por, "confirmada": confirmada,
                          **({"comentario": texto} if texto else {})}}
               for p in pecas]
    os_ = f" da OS {r['os']}" if r["os"] else ""
    hora = _quando_txt(agora or _agora())
    mensagem = (f"Requisição{os_} aceita às {hora.split(' às ')[-1]}: aprovada, saída feita e entrega total." if confirmada else
                f"A requisição{os_} foi aprovada e a saída feita, mas a releitura não mostra a entrega total: confira na tela do "
                "Fracttal antes de repetir.")
    try:
        F.acrescentar(cfg, F.ABA_EVENTO, eventos)
    except (F.Recusada, ValueError) as ex:
        mensagem += f" Não consegui anotar no livro do Nexus ({ex})."
    return {"ok": True, "confirmada": confirmada, "mensagem": mensagem, "saida": str(saida)}


def recusar(cfg, estoque, id_requisicao, *, ctx: dict, quem_: dict, conta: dict | None, comentario: str,
            agora: datetime | None = None) -> dict:
    """Recusa (`outputs_orders_update` com `approved: false`, o comentário obrigatório e a conta), sem saída: o técnico já usou
    a peça, e a recusa só registra. PROVA PENDENTE no Fracttal de verdade. A aprovada não se recusa (409). O evento
    `requisicao_recusada` leva o comentário cifrado."""
    rid = _id_da_requisicao(id_requisicao)
    texto = " ".join(str(comentario or "").split())
    if not texto:
        raise ValueError("Recusar pede o comentário (vai ao Fracttal e fica cifrado no Nexus).")
    if len(texto) > COMENTARIO_MAX:
        raise ValueError(f"O comentário passa de {COMENTARIO_MAX} letras.")
    r = _conferir_estado(estoque.reler_requisicao(rid, JANELA_DIAS, agora), rid, ctx)
    if r["aprovada"]:
        raise Conflito("A requisição já foi aprovada: não se recusa. Nada foi enviado.")
    if not conta:
        raise Conflito(SEM_CONTA)
    try:
        estoque.recusar_requisicao(rid, texto, conta)
    except (E.ErroFracttal, E.Limite, E.SemLogin, OSError) as ex:
        motivo = _falha(cfg, ctx, r, quem_, "pcm", "recusar", ex)
        raise Falhou(f"Não recusei: o Fracttal não aceitou a recusa ({motivo}). Nada mudou na requisição.", _status(ex),
                     ex) from ex
    try:
        depois = estoque.reler_requisicao(rid, JANELA_DIAS, agora)
    except (E.ErroFracttal, E.Limite, E.SemLogin, OSError):
        depois = None
    confirmada = bool(depois) and recusada(depois)
    os_ = f" da OS {r['os']}" if r["os"] else ""
    mensagem = (f"Requisição{os_} recusada no Fracttal." if confirmada else
                f"O Fracttal aceitou a recusa da requisição{os_}, mas a releitura não a mostra recusada: confira na tela do "
                "Fracttal.")
    try:
        F.acrescentar(cfg, F.ABA_EVENTO, [{"tipo": "requisicao_recusada", "movimento_fracttal": rid,
                                           **_quem_cols(ctx, quem_, r["id_almox"]),
                                           "dados": {"motivo": texto, "os": r["os"], "confirmada": confirmada}}])
    except (F.Recusada, ValueError) as ex:
        mensagem += f" Não consegui anotar no livro do Nexus ({ex})."
    return {"ok": True, "confirmada": confirmada, "mensagem": mensagem}


# ── o automático das de Rank B e C ──────────────────────────────────────────────────────────────────────────────────────
_AUTO = threading.Lock()
_ANDANDO: dict = {}


def _arquivo(cfg):
    from .gravacao import _pasta
    p = _pasta(cfg)
    if p is None:
        raise F.Recusada("Este Nexus está sem pasta de dados (NEXUS_DADOS): o automático não começa. Nada foi enviado.")
    return p / ARQUIVO_AUTO


def _salvar(arq, ctrl: dict, *, estrito: bool = False) -> None:
    from .gravacao import _gravar_json, _iso
    ctrl["atualizado_em"] = _iso(_agora())
    try:
        _gravar_json(arq, ctrl)
    except OSError as ex:
        if estrito:
            raise
        log.warning("requisições: o controle do automático não gravou (%s)", type(ex).__name__)


def andando() -> bool:
    th = _ANDANDO.get("th")
    return th is not None and th.is_alive()


def aguardar(timeout: float = 30) -> None:
    """Espera o automático que está andando terminar (os testes e a cópia de prova)."""
    th = _ANDANDO.get("th")
    if th is not None:
        th.join(timeout)


def iniciar_automatico(cfg, estoque, ids: list[str], *, ctx: dict, quem_: dict, conta: dict | None,
                       responsavel: dict | None) -> dict:
    """Aceita em segundo plano, na sessão de quem pediu, as requisições `ids` (as `ids_sozinhas` da lista: só de B e C
    conhecidas e sem falha registrada). Uma de cada vez no processo (`_AUTO`: 409 com outra andando). O controle
    `requisicoes-auto.json` ("gravando", salvo a cada requisição) é o que o deploy espera (`gravacao.com_lote_aberto`) e a tela
    acompanha (`estado_automatico`). Sem o responsável ou a conta, nada começa (409)."""
    ids = [A._id(i) for i in ids if A._id(i).isdigit()]
    if not ids:
        raise Conflito("Nenhuma requisição de Rank B e C a aceitar agora.")
    if not responsavel:
        raise Conflito(SEM_RESPONSAVEL)
    if not conta:
        raise Conflito(SEM_CONTA)
    if not _AUTO.acquire(blocking=False):
        raise Conflito(JA_ANDANDO)
    try:
        arq = _arquivo(cfg)
        from .gravacao import _iso
        ctrl = {"estado": "gravando", "inicio": _iso(_agora()), "pessoa_hmac": (quem_ or {}).get("pessoa_hmac") or "",
                "total": len(ids), "feitas": 0, "aceitas": 0, "falhas": 0, "puladas": 0, "itens": [], "parou": ""}
        try:
            _salvar(arq, ctrl, estrito=True)
        except OSError as ex:
            raise F.Recusada(f"Não consegui gravar o controle do automático no disco do Nexus ({type(ex).__name__}): nada foi "
                             "enviado ao Fracttal.") from ex
        th = threading.Thread(target=_rodar, args=(cfg, estoque, ids, ctx, quem_, conta, responsavel, arq, ctrl),
                              name="requisicoes-automatico", daemon=True)
        _ANDANDO["th"] = th
        th.start()
    except BaseException:
        _ANDANDO.pop("th", None)
        _AUTO.release()
        raise
    return dict(ctrl)


def _rodar(cfg, estoque, ids, ctx, quem_, conta, responsavel, arq, ctrl) -> None:
    """A thread: uma requisição de cada vez, pela `aceitar` (a mesma regra do clique). A que já não está a aceitar (alguém
    aceitou no meio, ou ganhou peça A) é pulada; a falha do Fracttal fica registrada e a próxima segue; o 429 e o login que
    expira param tudo (o resto fica para a próxima abertura da tela)."""
    from .gravacao import _iso
    try:
        for rid in ids:
            item = {"id": rid, "resultado": "", "texto": ""}
            try:
                r = aceitar(cfg, estoque, rid, por="sozinha", ctx=ctx, quem_=quem_, conta=conta, responsavel=responsavel)
                item.update(resultado="aceita" if r["confirmada"] else "sem_confirmar", texto=r["mensagem"])
                ctrl["aceitas"] += 1
            except Conflito as ex:
                item.update(resultado="pulada", texto=str(ex))
                ctrl["puladas"] += 1
            except (Falhou, E.Limite, E.SemLogin, E.ErroFracttal, OSError, F.Recusada, ValueError) as ex:
                causa = ex.causa if isinstance(ex, Falhou) else ex
                item.update(resultado="falha", texto=ex.mensagem if isinstance(ex, (Falhou, E.ErroFracttal)) else
                            f"{type(ex).__name__}: {ex}"[:200])
                ctrl["falhas"] += 1
                if isinstance(causa, (E.Limite, E.SemLogin)):
                    # o resto fica para a próxima abertura da tela: insistir gastaria a cota da empresa (ou o login morto)
                    ctrl["parou"] = ("o Fracttal pediu uma pausa (o limite de pedidos da empresa)" if isinstance(causa, E.Limite)
                                     else "o login do Fracttal de quem abriu a tela expirou")
                    ctrl["itens"].append(item)
                    ctrl["feitas"] += 1
                    break
            ctrl["itens"].append(item)
            ctrl["feitas"] += 1
            _salvar(arq, ctrl)
        ctrl.update(estado="parada" if ctrl["parou"] else "concluida", fim=_iso(_agora()))
    except Exception as ex:          # noqa: BLE001 — o automático para, e a tela diz por quê
        log.warning("requisições: o automático parou (%s)", type(ex).__name__)
        ctrl.update(estado="parada", parou=f"erro inesperado ({type(ex).__name__})", fim=_iso(_agora()))
    finally:
        _salvar(arq, ctrl)
        _ANDANDO.pop("th", None)
        _AUTO.release()


def estado_automatico(cfg) -> dict | None:
    """O último automático (o controle), ou None. O "gravando" sem a thread viva neste processo é o Nexus que reiniciou no meio:
    "parada". `texto` diz o andamento ou o resultado."""
    try:
        from .gravacao import _ler_json
        ctrl = _ler_json(_arquivo(cfg))
    except (F.Recusada, OSError, ValueError):
        return None
    if not ctrl:
        return None
    est = dict(ctrl)
    if est.get("estado") == "gravando" and not andando():
        est.update(estado="parada", parou=est.get("parou") or "o Nexus reiniciou no meio")
    n = f"{est.get('feitas', 0)} de {est.get('total', 0)}"
    if est["estado"] == "gravando":
        est["texto"] = f"Aceitando sozinho as de Rank B e C: {n}."
    else:
        partes = [f"{est.get('aceitas', 0)} aceitas"] + ([f"{est['falhas']} com falha"] if est.get("falhas") else []) + \
                 ([f"{est['puladas']} puladas"] if est.get("puladas") else [])
        est["texto"] = (f"O automático {'parou' if est['estado'] == 'parada' else 'terminou'} ({n}): {', '.join(partes)}."
                        + (f" Parou: {est['parou']}." if est.get("parou") else ""))
    est["fim_txt"] = _quando_txt(est.get("fim") or est.get("atualizado_em"))
    return est


# ── a página (em /t/pcm: não fala com o Fracttal) ───────────────────────────────────────────────────────────────────────
def registrar(bp) -> None:
    @bp.route("/pecas/requisicoes", endpoint="requisicoes")
    def requisicoes_tela():
        """A aba Requisições do Almoxarifado: a casca da página; a lista vem da ponte do login do Fracttal (o cookie dele só
        chega em /os), por `fetch`. Quem entrou pela senha de administrador não é uma pessoa e não tem o login: a página diz
        isso e nem pede. Os outros setores que veem a tela leem que ela é do PCM."""
        email = quem.do_pedido().get("email")
        return render_template("pcm/requisicoes.html", pode=telas.pode_programar(), com_pessoa=bool(email),
                               aviso=session.pop("pcm_requisicoes_aviso", None), auto=estado_automatico(current_app.config))

    @bp.route("/pecas/requisicoes/automatico.json", endpoint="requisicoes_automatico")
    def requisicoes_automatico():
        """O andamento do automático (a tela olha a cada 3 s). Lê o controle; não fala com o Fracttal."""
        est = estado_automatico(current_app.config)
        resp = jsonify(ok=True, estado=est["estado"] if est else "nenhum", texto=(est or {}).get("texto", ""),
                       andando=andando())
        resp.headers["Cache-Control"] = "no-store"
        return resp
