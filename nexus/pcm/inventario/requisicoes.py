"""As requisições de material no Almoxarifado (12/11/2026, item 6 da 2ª rodada): o "Aceitar" pelo Nexus.

Como era (a reunião do PCM de 04/11, transcrita): o técnico põe a peça como recurso na tarefa da OS, a requisição de material
nasce sozinha no almoxarifado da usina (o movimento OUTPUT_ORDER, tipo 13), e o PCM fazia três passos no Fracttal: uma Saída
"Geral" com a OS na referência (sem ela o saldo não baixa), aprovar e mudar o status para Entrega total. O PCM pediu "encurtar
esse caminho, não ter que fazer saída, deixar mais automatizado". Decisões do Levi (12/11/2026): a requisição com peça **Rank A**
o PCM aceita no Nexus com UM clique; as de **Rank B e C** o Nexus aceita **sozinho** e registra na auditoria.

O caminho do Fracttal (provado no TESTE - PA em 12/11/2026, pela tela e pelo RPC, lido de volta; o adaptador em `estoque.py`):
aprovar (`aprovar_requisicao`, só no estado 3; depois da entrega o Fracttal diz `STATE_CHANGED`), a saída LIGADA à requisição
(`saida_da_requisicao`, com as linhas da requisição cruas: baixa o saldo e leva a requisição sozinha a 5, Entrega total) e reler.

Regras, com o caso que as criou:
- **Uma função só aceita** (`aceitar`), para o clique do PCM e para o automático: relê (estado 3, nem cancelada, nem recusada),
  confere, aprova se ainda não está aprovada, faz a saída e relê a requisição e o saldo, cada um à parte.
- **A saída nunca sai em dobro** (a revisão do item 6, os Críticos):
  - a do PCM: antes de qualquer saída, o histórico do almoxarifado desde a requisição é lido atrás de um movimento da mesma
    peça com a OS no `document` ou na `description` (a Saída "Geral" que o PCM fazia; `estoque.saida_com_a_os`). Achou: nada
    vai, e a requisição fica em Falhas ("o PCM já deu a saída da OS N em <data>: aprove e mude o status no Fracttal"). E o
    automático só vale para a requisição criada a partir de `AUTO_DESDE` (o dia da entrada no ar): as de antes, do tempo da
    Saída Geral, ficam para o PCM;
  - a do Nexus: a requisição que já tem a saída do Nexus no livro (o evento do aceite), ou uma saída de resposta incerta (a
    rede, ou o Fracttal sem o id), não recebe outra: fica em Falhas, "confira no Fracttal", sem o botão; a memória do
    processo guarda a saída feita também, para o livro que não gravou;
  - o mesmo aceite duas vezes ao mesmo tempo (duas abas, o automático e o clique): uma trava por requisição em memória (o Nexus
    roda num processo só), e a segunda leva 409.
- **O id da peça é o `id_item_original`** (o do catálogo, o do saldo e da dimensão; provado em 12/11/2026: na linha da
  requisição, o `id_item` é o id da peça naquele almoxarifado, outro número). As linhas vão cruas na saída.
- **O que fica na Falhas e o que tenta de novo:** o "não" do Fracttal (`Recusado`) e a resposta incerta tiram a requisição do
  automático e ficam à vista; a pausa (429) e o login vencido não registram falha (nada foi feito) e a próxima abertura tenta.
  O saldo é conferido ANTES de aprovar (a peça que não tem o bastante não chega a "aprovada, saída falhou").
- **O estado 4 (entrega parcial) não entra**, nem no clique: a saída do pendente não foi provada ("conclua no Fracttal").
- **O dono**: a saída precisa do responsável do Fracttal de quem está na ponte (`estoque.responsavel`, pelo e-mail) e a
  aprovação da conta dele (o id e o nome, pelo catálogo de pessoas do OS Creator, como os avisos do Comando). Sem um deles,
  nada vai (409): não se grava sem dono.
- **O automático (B e C)**: o Nexus não tem conta de serviço no Fracttal e grava só com o login de quem está na ponte. Quando
  alguém do PCM com o login do Fracttal abre Almoxarifado → Requisições, a página pede o automático, e o Nexus aceita em
  segundo plano, NA SESSÃO DESSA PESSOA, as pendentes cujas peças são TODAS Rank B ou C conhecidas. Uma thread com o
  controle "gravando" (`requisicoes-auto.json`, só texto do Nexus), que o deploy espera (`gravacao.com_lote_aberto`). Para ir
  sem ninguém abrir a tela, precisa de uma conta de serviço (decisão do Levi).
- **O Rank é o da peça no Fracttal** (a Classificação 2, "2. Rank A"), pelo código, no mapa da lista de peças inteira
  (`classificacao.mapa_guardado`): a "Curva ABC" do catálogo do App vem VAZIA para os Ranks. A peça fora do mapa, sem a
  Classificação 2, "1.Avariado" ou com duas Classificações 2 diferentes no mesmo código é a curva desconhecida, e vai ao PCM.
- **A gravação do inventário**: com a vez do almoxarifado presa (uma contagem gravando ou parada no meio) ou ele fora do modo 0,
  nada vai (a saída seria recusada depois da aprovação).
- **Nome de gente**: o `accounts_log_name` (quem decidiu no Fracttal) e a descrição do responsável só passam pela memória e
  pela tela do PCM; o livro guarda a pessoa como `pessoa_hmac`/`pessoa_id`, e o comentário, a OS e as peças só cifrados.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
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
GERAL_DIAS = 7          # a busca da Saída Geral do PCM começa 7 dias antes da requisição (a re-revisão do item 6, C1)
PECAS_TTL_S, RESPONSAVEL_TTL_S, SEM_RESPONSAVEL_TTL_S = 600, 3600, 300
COMENTARIO_MAX = 300
# O automático só vale para a requisição criada a partir daqui (a revisão do item 6, C1): as de antes são do tempo em que o PCM
# dava a Saída "Geral" à mão, e uma saída do Nexus por cima baixaria o saldo duas vezes. VALOR DE TESTE: o coordenador troca
# pela data (e hora) da entrada no ar, no push. ISO com o fuso.
AUTO_DESDE = "2026-11-12T00:00:00-03:00"
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
EM_CURSO = "Outra pessoa (ou o automático) está aceitando esta requisição agora: espere e recarregue a página. Nada foi enviado."
SEM_LIVRO = ("Não consegui ler o livro do inventário agora: sem ele não sei se o Nexus já fez a saída desta requisição. Nada foi "
             "enviado; tente de novo em instantes.")
_BRT = timezone(timedelta(hours=-3))
log = logging.getLogger(__name__)


class Falhou(Exception):
    """Um passo do aceite (ou da recusa) que o Fracttal não fez, ou cuja resposta não veio. `mensagem` é a da tela (o que ficou
    feito e o que não), `status` o HTTP da ponte (409 o "não" do Fracttal ou a recusa do Nexus, 429 a pausa, 401 o login, 502 a
    resposta incerta) e `causa` o erro do Fracttal, ou None (o automático para no 429 e no login)."""

    def __init__(self, mensagem: str, status: int, causa: Exception | None):
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


def auto_desde_txt() -> str:
    try:
        return E.instante(AUTO_DESDE).astimezone(_BRT).strftime("%d/%m/%Y")
    except ValueError:
        return AUTO_DESDE


def depois_do_corte(r: dict) -> bool:
    """A requisição criada a partir de `AUTO_DESDE` (a que pode ir sozinha). A data ilegível não é: vai ao PCM."""
    try:
        return E.instante(r["criada_em"]) >= E.instante(AUTO_DESDE)
    except ValueError:
        return False


# ── as peças e a curva ──────────────────────────────────────────────────────────────────────────────────────────────────
def pecas_com_curva(linhas: list[dict], curvas: dict | None) -> list[dict]:
    """As peças da requisição (as linhas do `movements_details_list`) para a tela e a regra: o id da peça NO CATÁLOGO (o
    `id_item_original`, com o `id_item` só de reserva; a revisão, I2: o `id_item` da linha é o da peça naquele almoxarifado), o
    código, o nome, a quantidade, o pendente e a CURVA, a letra do Rank da peça no Fracttal pelo código (`curvas`, do
    `contexto`; "" é a curva desconhecida). A desconhecida nunca é A nem B nem C. As linhas em si não mudam (a saída as manda
    cruas)."""
    out = []
    for l in linhas:
        codigo = " ".join(str(l.get("code") or "").split())
        curva = (curvas or {}).get(_chave(codigo), "") if codigo else ""
        out.append({"id_item": A.id_ou_vazio(l.get("id_item_original")) or A.id_ou_vazio(l.get("id_item")),
                    "id_linha": A.id_ou_vazio(l.get("id_item")), "codigo": codigo,
                    "nome": " ".join(str(l.get("items_description") or "").split()),
                    "unidade": " ".join(str(l.get("units_description") or "").split()).lower(), "qtd": _num(l.get("qty")),
                    "pendente": _num(l.get("qty_pending")), "curva": curva if curva in ("A", "B", "C") else ""})
    return out


def de_quem(pecas: list[dict] | None) -> str:
    """"sozinha" quando TODAS as peças são Rank B ou C conhecidas (o Nexus aceita sozinho); senão "pcm" (uma A, uma de curva
    desconhecida, ou as peças que não se leram: o PCM decide)."""
    return "sozinha" if pecas and all(p["curva"] in CURVAS_SOZINHAS for p in pecas) else "pcm"


def _pecas_do_evento(pecas: list[dict]) -> list[dict]:
    """As peças como vão no `dados` cifrado da falha e da recusa (a revisão, M2): o código, o id do catálogo, a quantidade e
    a curva."""
    return [{"codigo": p["codigo"], "id_item": p["id_item"], "qtd": p["qtd"], "curva": p["curva"]} for p in pecas]


def recusada(r: dict) -> bool:
    """A não aprovada COM a data da decisão foi recusada (o que o Fracttal grava; 12/11/2026)."""
    return not r["aprovada"] and bool(r["decidida_em"])


def pendente(r: dict) -> bool:
    """Ainda a aceitar: não entregue (estado 3) e não recusada. A aprovada sem a saída também (falta a saída)."""
    return r["estado"] == E.NAO_ENTREGUE and not recusada(r)


# ── o que o Nexus já fez (o livro do inventário, e a memória do processo) ─────────────────────────────────────────────────
# a saída feita nesta vida do processo (a revisão, C2): segura a repetição mesmo quando o livro não gravou o aceite
_SAIDAS_FEITAS: dict[str, str] = {}
_TRAVA_SAIDAS = threading.Lock()


def _do_livro(cfg, eventos: list[dict], agora: datetime) -> dict:
    """O que o livro diz das requisições: `falhas` {requisição: a última falha, com o porquê decifrado e `travada` quando ela
    não pode ser tentada de novo pelo Nexus}, `travas` {requisição: por que o Nexus não faz outra saída} (a saída do Nexus já
    feita, pelo evento do aceite; a saída de resposta incerta; a Saída Geral do PCM achada) e `sozinhas` (as aceitas sozinhas
    dos últimos 30 dias, com o saldo antes e depois). O aceite tira a falha de antes; a trava da saída feita fica."""
    falhas, travas, sozinhas = {}, {}, {}
    corte = agora - timedelta(days=SOZINHAS_DIAS)
    for i, e in enumerate(eventos):
        t, rid = A._txt(e.get("tipo")), A._id(e.get("movimento_fracttal"))
        if not rid or not t.startswith("requisicao_"):
            continue
        quando = A._txt(e.get("quando"))
        if t in ("requisicao_falha", "requisicao_travada"):
            if rid not in falhas or (quando, i) >= falhas[rid]["_marca"]:
                d = F.decifrar(cfg, F.ABA_EVENTO, e)
                # a trava pelo TIPO do evento (a re-revisão, N3): o `dados` que não se decifra (a chave do cadastro trocada ou
                # ausente) não solta a trava depois do restart. A falha travada de antes do tipo próprio vale pelo `dados`
                travada = t == "requisicao_travada" or d.get("travada") is True
                falhas[rid] = {"_marca": (quando, i), "quando": quando, "quando_txt": _quando_txt(quando),
                               "motivo": A._txt(d.get("motivo")) or "o motivo não se lê agora", "passo": A._txt(d.get("passo")),
                               "por": A._txt(d.get("por")), "os": A._txt(d.get("os")), "travada": travada}
                if travada:
                    travas[rid] = falhas[rid]["motivo"]
        elif t in ("requisicao_aceita", "requisicao_aceita_sozinha", "requisicao_recusada"):
            falhas.pop(rid, None)                  # o livro está na ordem da gravação: a falha de antes do aceite já passou
        if t in ("requisicao_aceita", "requisicao_aceita_sozinha") and rid not in travas:
            saida = A._txt(F.decifrar(cfg, F.ABA_EVENTO, e).get("saida"))
            travas[rid] = (f"o Nexus já fez a saída{' ' + saida if saida else ''} em {_quando_txt(quando)}, e a requisição não "
                           "foi à Entrega total: confira no Fracttal (o Nexus não faz outra)")
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
    with _TRAVA_SAIDAS:
        for rid, texto in _SAIDAS_FEITAS.items():
            travas.setdefault(rid, texto)
    return {"falhas": falhas, "travas": travas, "sozinhas": lista}


def _trava_da_saida(cfg, rid: str) -> str:
    """Por que o Nexus não faz outra saída desta requisição ("" se pode), pelo livro de agora e pela memória do processo. O livro
    que não se lê não deixa passar (`Conflito`): sem ele não se sabe se a saída já foi feita."""
    with _TRAVA_SAIDAS:
        if rid in _SAIDAS_FEITAS:
            return _SAIDAS_FEITAS[rid]
    try:
        eventos = F.ler(cfg)[F.ABA_EVENTO]
    except F.Recusada as ex:
        raise Conflito(SEM_LIVRO) from ex
    return _do_livro(cfg, [e for e in eventos if A._id(e.get("movimento_fracttal")) == rid], _agora())["travas"].get(rid, "")


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
    with _TRAVA_SAIDAS:
        _SAIDAS_FEITAS.clear()
    with _TRAVA_CURSO:
        _EM_CURSO.clear()


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
    - `para_pcm`: as pendentes com peça Rank A ou de curva desconhecida, e as de B e C criadas antes de `AUTO_DESDE` (`antiga`);
    - `sozinhas`: as pendentes só de B e C conhecidas, criadas a partir de `AUTO_DESDE` e sem falha nem trava (`ids_sozinhas`);
    - `falhas`: as pendentes com uma falha registrada ou com a saída do Nexus já feita (`travada`: sem o botão, "confira no
      Fracttal");
    - `parciais`: as de entrega parcial (estado 4: "conclua no Fracttal");
    - `aceitas_sozinhas`: as que o automático aceitou nos últimos 30 dias, com o saldo antes e depois (o livro);
    - `decididas`: as aprovadas e recusadas nos últimos 30 dias (o Fracttal: quem, o comentário, quando).
    Dentro de cada grupo, a mais nova primeiro. O almoxarifado de teste fica de fora. O livro do inventário que não se lê agora
    não derruba a lista (`livro_lido` falso), e então o automático não roda: sem saber das falhas, ele tentaria de novo."""
    agora = agora or _agora()
    reqs = [r for r in estoque.requisicoes(JANELA_DIAS, agora) if r["id_almox"] not in ctx["teste"]]
    try:
        livro = _do_livro(cfg, F.ler(cfg)[F.ABA_EVENTO], agora)
        livro_lido = True
    except F.Recusada:
        livro, livro_lido = {"falhas": {}, "travas": {}, "sozinhas": []}, False
    almoxes = ctx["almoxes"]
    grupos = {"para_pcm": [], "sozinhas": [], "falhas": [], "parciais": [], "decididas": []}
    corte = agora - timedelta(days=DECIDIDAS_DIAS)
    for r in reqs:
        a = almoxes.get(r["id_almox"]) or {}
        falha = livro["falhas"].get(r["id"])
        trava = livro["travas"].get(r["id"])
        if trava and not (falha and falha["travada"]):
            falha = {"motivo": trava, "quando_txt": "", "passo": "saida", "por": "", "travada": True}
        x = dict(r, almox=a.get("nome") or r["almox_nome"] or f"Almoxarifado {r['id_almox']}", usina=a.get("usina") or "",
                 estado_txt=ESTADO_TXT.get(r["estado"], f"estado {r['estado']}"), criada_txt=_quando_txt(r["criada_em"]),
                 decidida_txt=_quando_txt(r["decidida_em"]), recusada=recusada(r), pecas=None, erro_pecas="", falha=falha,
                 antiga=not depois_do_corte(r))
        if pendente(r):
            try:
                x["pecas"] = pecas_com_curva(pecas_guardadas(estoque, r["id"]), ctx["curvas"])
            except Exception as ex:      # noqa: BLE001 — a rede de uma não derruba a lista (N2)
                x["erro_pecas"] = f"não consegui ler as peças agora ({type(ex).__name__})"
            x["de_quem"] = de_quem(x["pecas"])
            x["rank_a"] = any(p["curva"] == "A" for p in x["pecas"] or [])
            sozinha = x["de_quem"] == "sozinha" and not x["antiga"]
            grupos["falhas" if falha else "sozinhas" if sozinha else "para_pcm"].append(x)
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
    for g in livro["sozinhas"]:
        a = almoxes.get(g["almox"]) or {}
        g["almox_nome"] = a.get("nome") or f"Almoxarifado {g['almox']}"
    return {**grupos, "aceitas_sozinhas": livro["sozinhas"][:20], "livro_lido": livro_lido,
            "ids_sozinhas": [x["id"] for x in grupos["sozinhas"]], "n_total": len(reqs), "auto_desde": auto_desde_txt()}


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
    (a lista de responsáveis são páginas da cota de todos); o "não achei" fica 5 min (sem ele, cada abertura da aba relia a lista
    inteira; a revisão, M5). Nada em arquivo nem em log."""
    e = str(email or "").strip().lower()
    agora = relogio()
    with _TRAVA_RESP:
        g = _RESPONSAVEIS.get(e)
        if g and agora - g[0] < (RESPONSAVEL_TTL_S if g[1] else SEM_RESPONSAVEL_TTL_S):
            return dict(g[1]) if g[1] else None
    achado = estoque.responsavel(e)
    with _TRAVA_RESP:
        _RESPONSAVEIS[e] = (agora, dict(achado) if achado else None)
    return achado


# ── aceitar e recusar ───────────────────────────────────────────────────────────────────────────────────────────────────
_EM_CURSO: set = set()
_TRAVA_CURSO = threading.Lock()


@contextmanager
def _tomar(rid: str):
    """Uma requisição de cada vez no processo (a revisão, I1): o segundo aceite (ou recusa) da mesma requisição, enquanto o
    primeiro anda, leva 409. O Nexus roda num processo só, então a trava em memória fecha a janela."""
    with _TRAVA_CURSO:
        if rid in _EM_CURSO:
            raise Conflito(EM_CURSO)
        _EM_CURSO.add(rid)
    try:
        yield
    finally:
        with _TRAVA_CURSO:
            _EM_CURSO.discard(rid)


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


def _certo(ex: Exception) -> bool:
    """O Fracttal não fez nada, com certeza: o "não" dele (`Recusado`), a pausa (429) e o login recusado. O resto (a rede, a
    resposta sem corpo ou sem o id) pode ter vindo DEPOIS de ele gravar."""
    return isinstance(ex, (E.Recusado, E.Limite, E.SemLogin))


def _motivo(ex: Exception) -> str:
    return (ex.mensagem if isinstance(ex, E.ErroFracttal) else
            "o Fracttal pediu uma pausa (o limite de pedidos da empresa)" if isinstance(ex, E.Limite) else
            "o login do Fracttal expirou" if isinstance(ex, E.SemLogin) else
            f"o Fracttal não respondeu ({type(ex).__name__})")


def _status(ex: Exception | None) -> int:
    if isinstance(ex, E.Limite):
        return 429
    if isinstance(ex, E.SemLogin):
        return 401
    return 409 if ex is None or isinstance(ex, E.Recusado) else 502


def _falha(cfg, ctx, r, quem_, por: str, passo: str, motivo: str, pecas: list[dict], travada: bool = False) -> None:
    """Registra a falha de um passo (o evento `requisicao_falha`, com o porquê, as peças com a curva e o `travada` cifrados). O
    livro que não grava agora não esconde a falha do Fracttal: só vai ao log (o tipo)."""
    try:
        F.acrescentar(cfg, F.ABA_EVENTO, [{"tipo": "requisicao_travada" if travada else "requisicao_falha",
                                           "movimento_fracttal": r["id"],
                                           **_quem_cols(ctx, quem_, r["id_almox"]),
                                           "dados": {"motivo": motivo, "passo": passo, "por": por, "os": r["os"],
                                                     "pecas": _pecas_do_evento(pecas), "travada": travada}}])
    except (F.Recusada, ValueError) as ex2:
        log.warning("requisições: a falha da requisição %s não foi ao livro (%s)", r["id"], type(ex2).__name__)


def aceitar(cfg, estoque, id_requisicao, *, por: str, ctx: dict, quem_: dict, conta: dict | None,
            responsavel: dict | None, comentario: str = "", agora: datetime | None = None) -> dict:
    """Aceita UMA requisição (o clique do PCM, `por` "pcm", e o automático, `por` "sozinha"), uma de cada vez por requisição
    (`_tomar`). `{"ok", "confirmada", "mensagem", "saida"}`.

    Recusa (`Conflito`, 409, nada vai): a que não está a aceitar (`_conferir_estado`); no automático, a criada antes de
    `AUTO_DESDE` e a que tem peça Rank A ou desconhecida; a que já tem a saída do Nexus (`_trava_da_saida`); a sem responsável, a
    sem conta quando precisa aprovar, a sem peças; o almoxarifado com a vez presa ou fora do modo 0. Depois de ler o saldo, as
    que não vão e ficam em Falhas (`Falhou`, 409, com o evento): a Saída Geral do PCM achada no histórico e o saldo que não dá.
    Então aprova (se falta) e faz a saída: o "não" do Fracttal e a resposta incerta registram a falha (a incerta da saída
    trava: o Nexus não a repete); a pausa e o login não registram nada. Cada peça aceita vira um evento (`requisicao_aceita` ou
    `requisicao_aceita_sozinha`) com o saldo antes e depois e a curva."""
    rid = _id_da_requisicao(id_requisicao)
    texto = " ".join(str(comentario or "").split())
    if len(texto) > COMENTARIO_MAX:
        raise ValueError(f"O comentário passa de {COMENTARIO_MAX} letras.")
    with _tomar(rid):
        return _aceitar(cfg, estoque, rid, por, ctx, quem_, conta, responsavel, texto, agora)


def _aceitar(cfg, estoque, rid, por, ctx, quem_, conta, responsavel, texto, agora) -> dict:
    from . import gravacao
    r = _conferir_estado(estoque.reler_requisicao(rid, JANELA_DIAS, agora), rid, ctx)
    os_ = f" da OS {r['os']}" if r["os"] else ""
    if por == "sozinha" and not depois_do_corte(r):
        raise Conflito(f"A requisição{os_} é de antes do automático ({auto_desde_txt()}): é o PCM que aceita, conferindo se a "
                       "Saída Geral já foi dada. Nada foi enviado.")
    trava = _trava_da_saida(cfg, rid)
    if trava:
        raise Conflito(f"Nada foi enviado: {trava}.")
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
    # a Saída Geral do PCM (a revisão, C1): a saída GENERAL da mesma peça com a OS, desde 7 dias antes da requisição (a peça pode
    # sair pela Geral antes de o técnico lançar o recurso no App; ruling do coordenador: a janela larga dá, no pior caso, uma
    # recusa a mais para o PCM conferir, nunca uma saída em dobro)
    try:
        desde = E.instante(r["criada_em"]) - timedelta(days=GERAL_DIAS)
    except ValueError:
        desde = (agora or _agora()) - timedelta(days=JANELA_DIAS)
    ids = {p["id_item"] for p in pecas if p["id_item"]} | {p["id_linha"] for p in pecas if p["id_linha"]}
    geral = estoque.saida_com_a_os(almox, r["os"], sorted(ids), desde.isoformat()) if r["os"] else None
    if geral:
        motivo = (f"o PCM já deu a saída da OS {r['os']} em {_quando_txt(geral.get('quando')) or 'data não lida'}: aprove e mude "
                  "o status no Fracttal")
        _falha(cfg, ctx, r, quem_, por, "saida_geral", motivo, pecas, travada=True)
        raise Falhou(f"Nada foi enviado: {motivo}.", 409, None)
    antes = estoque.ler(almox)
    faltam = [p for p in pecas if p["id_item"] not in antes
              or (antes[p["id_item"]].get("saldo") is not None and p["qtd"] is not None
                  and antes[p["id_item"]]["saldo"] < p["qtd"] - 1e-9)]
    if faltam:
        # o saldo conferido ANTES de aprovar (a revisão, M8): a peça sem o bastante não chega a "aprovada, saída falhou"
        motivo = "; ".join((f"{p['codigo'] or p['id_item']} não está ligada ao almoxarifado" if p["id_item"] not in antes else
                            f"{p['codigo']} tem {antes[p['id_item']]['saldo']:g} e a requisição pede {p['qtd']:g}")
                           for p in faltam)
        motivo = f"saldo insuficiente ({motivo}): dê entrada antes"
        _falha(cfg, ctx, r, quem_, por, "saldo", motivo, pecas)
        raise Falhou(f"Nada foi enviado: {motivo}.", 409, None)
    try:
        if not r["aprovada"]:
            padrao = (f"Aceita pelo Nexus por {conta['nome']}" if por == "pcm"
                      else f"Aceita pelo Nexus (Rank B ou C), na sessão de {conta['nome']}")
            estoque.aprovar_requisicao(rid, texto or padrao, conta)
    except Exception as ex:          # noqa: BLE001 — fora o "não" do Fracttal, a pausa e o login, a aprovação pode ter passado
        log.warning("requisições: a requisição %s parou ao aprovar (%s)", rid, type(ex).__name__)
        if not isinstance(ex, (E.Limite, E.SemLogin)):
            _falha(cfg, ctx, r, quem_, por, "aprovar", _motivo(ex), pecas)
        raise Falhou((f"Não aceitei a requisição{os_}: o Fracttal não aprovou ({_motivo(ex)}). Nada mudou nela." if _certo(ex) else
                      f"A aprovação da requisição{os_} não teve resposta ({_motivo(ex)}): ela pode ter sido aprovada. "
                      "Confira no Fracttal; a próxima tentativa relê e pula a aprovação feita."), _status(ex), ex) from ex
    try:
        saida = estoque.saida_da_requisicao(r, linhas, responsavel)
    except Exception as ex:          # noqa: BLE001 — fora o "não", a pausa e o login, a saída pode ter sido feita: trava (C2, N2)
        log.warning("requisições: a requisição %s parou na saída (%s)", rid, type(ex).__name__)
        incerta = not _certo(ex)
        if not isinstance(ex, (E.Limite, E.SemLogin)):
            _falha(cfg, ctx, r, quem_, por, "saida", _motivo(ex) + (": a saída pode ter sido feita" if incerta else ""), pecas,
                   travada=incerta)
        if incerta:
            with _TRAVA_SAIDAS:
                _SAIDAS_FEITAS[rid] = "a resposta da saída não veio (ela pode ter sido feita): confira no Fracttal"
        raise Falhou((f"A requisição{os_} ficou aprovada, e a resposta da saída não veio ({_motivo(ex)}): ela pode ter sido "
                      "feita. Confira no Fracttal; o Nexus não repete esta saída." if incerta else
                      f"A requisição{os_} ficou aprovada, mas a saída não passou ({_motivo(ex)}). A próxima tentativa pula a "
                      "aprovação."), _status(ex), ex) from ex
    with _TRAVA_SAIDAS:
        _SAIDAS_FEITAS[rid] = (f"o Nexus já fez a saída {saida} em {_quando_txt(agora or _agora())}, e a requisição não foi à "
                               "Entrega total: confira no Fracttal (o Nexus não faz outra)")
    # reler: a requisição (5 e aprovada) e o saldo de cada peça, cada leitura à parte (a revisão, M7). Não desfaz nada
    try:
        depois_r = estoque.reler_requisicao(rid, JANELA_DIAS, agora)
        relida = True
    except Exception:                # noqa: BLE001 — a saída já foi: qualquer erro aqui não impede o livro de gravar o aceite
        depois_r, relida = None, False
    try:
        depois = estoque.ler(almox)
    except Exception:                # noqa: BLE001 — idem (a re-revisão, N2: o erro de rede escapava e o aceite não ia ao livro)
        depois = {}
    confirmada = bool(depois_r) and depois_r["estado"] == E.ENTREGA_TOTAL and depois_r["aprovada"]
    if confirmada:
        with _TRAVA_SAIDAS:
            _SAIDAS_FEITAS.pop(rid, None)          # na Entrega total ela nem é mais pendente; o livro guarda o aceite
    tipo = "requisicao_aceita" if por == "pcm" else "requisicao_aceita_sozinha"
    base = _quem_cols(ctx, quem_, almox)
    eventos = [{"tipo": tipo, "movimento_fracttal": rid, **base, "id_item": p["id_item"] or None,
                "codigo": p["codigo"][:60] or None, "contado_qtd": p["qtd"],
                "de_qtd": (antes.get(p["id_item"]) or {}).get("saldo"), "para_qtd": (depois.get(p["id_item"]) or {}).get("saldo"),
                "dados": {"os": r["os"], "curva": p["curva"], "saida": str(saida), "por": por, "confirmada": confirmada,
                          **({"comentario": texto} if texto else {})}}
               for p in pecas]
    hora = _quando_txt(agora or _agora())
    mensagem = (f"Requisição{os_} aceita às {hora.split(' às ')[-1]}: aprovada, saída feita e entrega total." if confirmada else
                f"A requisição{os_} foi aprovada e a saída feita, mas a releitura não mostra a entrega total: confira na tela do "
                "Fracttal. O Nexus não faz outra saída dela." if relida else
                f"A requisição{os_} foi aprovada e a saída feita, mas não consegui reler a requisição: confira na tela do "
                "Fracttal. O Nexus não faz outra saída dela.")
    try:
        F.acrescentar(cfg, F.ABA_EVENTO, eventos)
    except (F.Recusada, ValueError) as ex:
        mensagem += f" Não consegui anotar no livro do Nexus ({ex})."
    return {"ok": True, "confirmada": confirmada, "mensagem": mensagem, "saida": str(saida)}


def recusar(cfg, estoque, id_requisicao, *, ctx: dict, quem_: dict, conta: dict | None, comentario: str,
            agora: datetime | None = None) -> dict:
    """Recusa (`outputs_orders_update` com `approved: false`, o comentário obrigatório e a conta), sem saída: o técnico já usou
    a peça, e a recusa só registra. PROVA PENDENTE no Fracttal de verdade. A aprovada não se recusa (409). O evento
    `requisicao_recusada` leva o comentário e as peças com a curva cifrados. Uma de cada vez por requisição (`_tomar`)."""
    rid = _id_da_requisicao(id_requisicao)
    texto = " ".join(str(comentario or "").split())
    if not texto:
        raise ValueError("Recusar pede o comentário (vai ao Fracttal e fica cifrado no Nexus).")
    if len(texto) > COMENTARIO_MAX:
        raise ValueError(f"O comentário passa de {COMENTARIO_MAX} letras.")
    with _tomar(rid):
        r = _conferir_estado(estoque.reler_requisicao(rid, JANELA_DIAS, agora), rid, ctx)
        if r["aprovada"]:
            raise Conflito("A requisição já foi aprovada: não se recusa. Nada foi enviado.")
        if not conta:
            raise Conflito(SEM_CONTA)
        pecas = pecas_com_curva(estoque.pecas_da_requisicao(rid), ctx["curvas"])
        try:
            estoque.recusar_requisicao(rid, texto, conta)
        except Exception as ex:      # noqa: BLE001 — fora o "não", a pausa e o login, a recusa pode ter passado
            if not isinstance(ex, (E.Limite, E.SemLogin)):
                _falha(cfg, ctx, r, quem_, "pcm", "recusar", _motivo(ex), pecas)
            raise Falhou((f"Não recusei: o Fracttal não aceitou a recusa ({_motivo(ex)}). Nada mudou na requisição."
                          if _certo(ex) else f"A recusa não teve resposta ({_motivo(ex)}): ela pode ter sido feita. Confira "
                          "no Fracttal."), _status(ex), ex) from ex
        try:
            depois = estoque.reler_requisicao(rid, JANELA_DIAS, agora)
        except Exception:            # noqa: BLE001 — a recusa já foi: o livro grava
            depois = None
        confirmada = bool(depois) and recusada(depois)
        os_ = f" da OS {r['os']}" if r["os"] else ""
        mensagem = (f"Requisição{os_} recusada no Fracttal." if confirmada else
                    f"O Fracttal aceitou a recusa da requisição{os_}, mas a releitura não a mostra recusada: confira na tela "
                    "do Fracttal.")
        try:
            F.acrescentar(cfg, F.ABA_EVENTO, [{"tipo": "requisicao_recusada", "movimento_fracttal": rid,
                                               **_quem_cols(ctx, quem_, r["id_almox"]),
                                               "dados": {"motivo": texto, "os": r["os"], "confirmada": confirmada,
                                                         "pecas": _pecas_do_evento(pecas)}}])
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
    conhecidas, criadas a partir de `AUTO_DESDE`, sem falha nem trava). Uma de cada vez no processo (`_AUTO`: 409 com outra
    andando). O controle `requisicoes-auto.json` ("gravando", salvo a cada requisição) é o que o deploy espera
    (`gravacao.com_lote_aberto`) e a tela acompanha (`estado_automatico`). Sem o responsável ou a conta, nada começa (409)."""
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
    aceitou no meio, ou ganhou peça A) é pulada; a falha fica registrada no livro e a próxima segue; o 429 e o login que
    expira param tudo (o resto fica para a próxima abertura da tela). O controle leva só texto do Nexus (a revisão, M4: o texto
    do Fracttal fica cifrado no livro)."""
    from .gravacao import _iso
    try:
        for rid in ids:
            item = {"id": rid, "resultado": "", "texto": ""}
            try:
                r = aceitar(cfg, estoque, rid, por="sozinha", ctx=ctx, quem_=quem_, conta=conta, responsavel=responsavel)
                item.update(resultado="aceita" if r["confirmada"] else "sem_confirmar",
                            texto="aceita" if r["confirmada"] else "saída feita, sem a entrega total na releitura")
                ctrl["aceitas"] += 1
            except Conflito:
                item.update(resultado="pulada", texto="pulada: já não estava para aceitar sozinha (veja na lista)")
                ctrl["puladas"] += 1
            except (Falhou, E.Limite, E.SemLogin, E.ErroFracttal, OSError, F.Recusada, ValueError) as ex:
                causa = ex.causa if isinstance(ex, Falhou) else ex
                item.update(resultado="falha", texto="não aceita (o porquê em Falhas)")
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
                               aviso=session.pop("pcm_requisicoes_aviso", None), auto=estado_automatico(current_app.config),
                               auto_desde=auto_desde_txt())

    @bp.route("/pecas/requisicoes/automatico.json", endpoint="requisicoes_automatico")
    def requisicoes_automatico():
        """O andamento do automático (a tela olha a cada 3 s). Lê o controle; não fala com o Fracttal."""
        est = estado_automatico(current_app.config)
        resp = jsonify(ok=True, estado=est["estado"] if est else "nenhum", texto=(est or {}).get("texto", ""),
                       andando=andando())
        resp.headers["Cache-Control"] = "no-store"
        return resp
