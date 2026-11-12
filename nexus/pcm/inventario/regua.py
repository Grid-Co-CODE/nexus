"""A régua de mínimo e máximo do almoxarifado (PCM → Almoxarifado → Mínimo e máximo; 26/10/2026).

Levi, 26/10/2026: a régua é "sugestão ajustável": o Nexus propõe pela régua de 14/10 e o PCM muda peça a peça. Desenho:
`docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`, seção 4.4. Cada peça de cada almoxarifado tem três
números de mínimo e máximo, e só um vai ao Fracttal:

- a **sugestão**, calculada (`sugestao`): mínimo = 20% do saldo, máximo = o dobro; a peça avariada (`-AV` no código) fica sem
  mínimo e com o triplo. Não é gravada como decisão de ninguém: guarda-se ao lado da decisão, como era no momento dela;
- o **recomendado** (a Grid): decisão do PCM, só no livro do Nexus (`fato_regua_minimo`). É o histórico com que o PCM
  defende o mínimo diante do cliente;
- o **acordado** (o cliente): decisão do PCM e o ÚNICO que vai ao Fracttal (`min_stock_level` dispara o alarme), no vínculo da
  peça com o almoxarifado, fora da sessão de ajuste (sem movimento, sem mexer no saldo; provado em 26/10). Enquanto o PCM
  não registra o acordado, o Fracttal não muda.

Cada linha do livro é o RETRATO da decisão (a última de cada almoxarifado e peça vale): decidir só o recomendado leva
junto o acordado de antes, senão a última linha apagaria o que o cliente acordou. Quem decide, a hora e o `data_id` vêm do
livro (`fato_inventario`); a pessoa vai só como código (`quem.colunas`).

Gravar no Fracttal segue a regra da casa: mostrar (a tela já traz o acordado registrado), gravar, RELER e só então anotar o
evento `regua_gravada` e o retrato `gravado_fracttal`. A releitura que não bate é um evento `erro` e nada mais: o livro
nunca diz que o Fracttal tem o que não tem. O evento carrega o MÍNIMO (de, para: é o que dispara o alarme); o máximo
acordado fica no retrato da régua, que é o registro do par.

Todos os acordados de um almoxarifado de uma vez (`gravar_acordados`, 11/11/2026; o PCM: "Mínimo e máximo: não está
atualizando após a auditoria automaticamente no Fracttal"): o fim da gravação de cada contagem (`gravacao`, na mesma sessão do
Fracttal de quem gravou) e o botão da régua mandam a régua acordada de cada peça do almoxarifado cujo acordado difere do que o
Fracttal tem (a peça recém-ligada pela gravação inclusive, que entra com 0 e 0), com a mesma regra: só o acordado, relido antes de
anotar, e a falha de uma peça não para as outras. A releitura fica guardada (`lida`), e a tela mostra "no Fracttal agora" sem
esperar a varredura do App.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from flask import abort, current_app, redirect, render_template, request, session

from ...campo import visao
from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from ...prefixo import na_raiz
from .. import telas
from . import erros, quem
from . import estoque as E
from .travas import Travas
from .erros import Conflito, NaoConfere

# a unidade que aceita casa decimal: METRO e MASSA (o `units_description` do Fracttal); a UNIDADE e o que não se sabe é inteira
UNIDADES_DECIMAIS = ("metro", "massa")
_AVARIADA = re.compile(r"-AV(?:-|\s|$)")
# ler o retrato de antes e escrever o de agora é uma conta só: uma trava POR PEÇA do almoxarifado (duas pessoas na mesma peça
# esperam uma pela outra; o resto não espera ninguém, nem a gravação lenta no Fracttal de outra peça)
_PECA = Travas()
# um lote de acordados de cada vez por almoxarifado (o botão e o fim da gravação de uma contagem)
_LOTE = Travas()
_TOLERANCIA = 1e-9
LOTE_REGUA = 50              # as peças mandadas entre uma releitura (e um registro no livro) e outra
ESPERA_LIMITE_S = 62         # a cota do Fracttal é por minuto: 62 s e ela já virou (o mesmo da gravação)
LIMITE = "limite do Fracttal"
LOGIN = "o login do Fracttal expirou"
SEM_RELEITURA = "a releitura do Fracttal não veio"
_BRT = timezone(timedelta(hours=-3))
LIGADA = F.USINA_LIGADA_POR[0]      # por onde a usina do almoxarifado liga: só a de-para do Fracttal


# ── a conta: a régua de 14/10 ────────────────────────────────────────────────────────────────────────────────────────
def _norm(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


def avariada(codigo, marca=False) -> bool:
    """A peça avariada: a do código com `-AV` no fim (a régua de 14/10; no catálogo do App, "SP-3-AV" e "[AVARIADO]"), ou a
    que o catálogo marca como avariada. O "AV" no meio de outra palavra (SP-AVR-001) não conta."""
    return bool(marca) or bool(_AVARIADA.search(str(codigo or "").strip().upper()))


def decimal(unidade) -> bool:
    """A unidade aceita casas decimais (METRO e MASSA). O que não se sabe (vazio) é inteiro: arredondar para duas casas o que
    não se conhece daria 0,2 de um parafuso."""
    return _norm(unidade) in UNIDADES_DECIMAIS


def sugestao(saldo: float | None, avariada: bool, decimal: bool) -> tuple[float | None, float | None]:
    """(mínimo, máximo) pela régua de 14/10: mínimo = 20% do saldo, máximo = 2x o saldo; avariada: sem mínimo (None) e
    máximo 3x. Unidade inteira: arredonda PARA CIMA (decisão do construtor: com saldo 3, mínimo 1, e não 0); decimal (METRO,
    MASSA): duas casas. Saldo 0 (ou negativo, do Fracttal com estoque negativo): (0, 0). Saldo não informado (None, "nan",
    "inf"): (None, None), porque em branco nunca é zero: o saldo que o Fracttal não disse não tem sugestão."""
    try:
        s = float(saldo)
    except (TypeError, ValueError):
        return None, None
    if not math.isfinite(s):
        return None, None
    if s <= 0:
        return 0, 0
    mult = 3 if avariada else 2
    if decimal:
        return (None if avariada else round(s / 5, 2)), round(s * mult, 2)
    # `round(..., 9)` antes do teto: 15 x 0,2 dá 3,0000000000000004 e subiria para 4
    return (None if avariada else math.ceil(round(s / 5, 9))), math.ceil(round(s * mult, 9))


def fmt(n) -> str:
    """O número como a tela o diz: 20, 2,5; vazio quando não há."""
    if n is None:
        return ""
    if isinstance(n, float) and n.is_integer():
        n = int(n)
    return format(n, "f").rstrip("0").rstrip(".").replace(".", ",") if isinstance(n, float) else str(n)


# ── os números que entram ────────────────────────────────────────────────────────────────────────────────────────────
def nivel(v, o_que: str):
    """Um mínimo ou máximo que veio da tela (texto com a vírgula do Brasil) ou do chamador: em branco é None; o que não é
    número, ou é negativo, é erro de quem chama (nunca vira 0: o 0 é "sem mínimo cadastrado" no Fracttal)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    n = A.numero(v)
    if n is None or not math.isfinite(n) or n < 0:
        raise ValueError(f"{o_que}: informe um número, zero ou maior (recebi {str(v)[:20]!r}).")
    return int(n) if n.is_integer() else n


def _par(par, o_que: str, *, completo: bool = False):
    """O par (mínimo, máximo) validado, ou None quando não veio. O recomendado pode ficar sem o mínimo (a avariada não tem);
    o acordado leva os dois (os dois vão ao Fracttal). O mínimo acima do máximo é recusado antes de qualquer pedido."""
    if par is None:
        return None
    try:
        mn, mx = par
    except (TypeError, ValueError):
        raise ValueError(f"{o_que}: informe o mínimo e o máximo.") from None
    mn, mx = nivel(mn, f"{o_que}, mínimo"), nivel(mx, f"{o_que}, máximo")
    if mn is None and mx is None:
        raise ValueError(f"{o_que}: o mínimo e o máximo estão em branco.")
    if completo and (mn is None or mx is None):
        raise ValueError(f"{o_que}: informe o mínimo e o máximo (os dois vão ao Fracttal).")
    if mn is not None and mx is not None and mn > mx:
        raise ValueError(f"{o_que}: o mínimo ({fmt(mn)}) não pode passar do máximo ({fmt(mx)}).")
    return mn, mx


def _num(v):
    n = A.numero(v)
    if n is None or not math.isfinite(n):
        return None
    return int(n) if n.is_integer() else n


def _sim(v) -> bool:
    return str(v).strip().lower() in ("1", "1.0", "true", "sim")


def _id(v) -> str:
    return A._id(v)


# ── o que o livro diz ────────────────────────────────────────────────────────────────────────────────────────────────
def _vigentes(linhas: list[dict]) -> dict:
    """{(almoxarifado, peça): o retrato da última decisão}: vale a mais nova pela hora gravada (a ordem do livro desempata).
    Os números vêm do livro como texto ("3,0", "", "None"): `_num` os lê."""
    ultimo: dict = {}
    for i, r in enumerate(linhas):
        k = (_id(r.get("id_almoxarifado")), _id(r.get("id_item")))
        marca = (A._txt(r.get("decidida_em")), i)
        if k not in ultimo or marca >= ultimo[k][0]:
            ultimo[k] = (marca, r)
    return {k: {"quando": A._txt(r.get("decidida_em")), "codigo": A._txt(r.get("codigo")),
                "usina_id": _num(r.get("usina_id")), "usina_ligada_por": A._txt(r.get("usina_ligada_por")),
                "sugestao": (_num(r.get("sugestao_min_qtd")), _num(r.get("sugestao_max_qtd"))),
                "recomendado": (_num(r.get("recomendado_min_qtd")), _num(r.get("recomendado_max_qtd"))),
                "acordado": (_num(r.get("acordado_min_qtd")), _num(r.get("acordado_max_qtd"))),
                "gravado": _sim(r.get("gravado_fracttal"))} for k, (_, r) in ultimo.items()}


def _gravadas(eventos: list[dict]) -> dict:
    """{(almoxarifado, peça): {"saldo", "codigo", "usina_id"}} da última contagem GRAVADA de cada peça: o `peca_gravada` mais
    novo (o `para_qtd` é o saldo). O conflito e o erro não são saldo gravado."""
    ultimo: dict = {}
    for i, e in enumerate(eventos):
        if A._txt(e.get("tipo")) != "peca_gravada" or _num(e.get("para_qtd")) is None:
            continue
        k = (_id(e.get("id_almoxarifado")), _id(e.get("id_item")))
        marca = (A._txt(e.get("quando")), i)
        if k not in ultimo or marca >= ultimo[k][0]:
            ultimo[k] = (marca, {"saldo": _num(e.get("para_qtd")), "codigo": A._txt(e.get("codigo")),
                                 "usina_id": _num(e.get("usina_id"))})
    return {k: v for k, (_, v) in ultimo.items()}


def _saldos_gravados(eventos: list[dict]) -> dict:
    """{(almoxarifado, peça): o saldo da última contagem GRAVADA} (`_gravadas`)."""
    return {k: g["saldo"] for k, g in _gravadas(eventos).items()}


def _catalogo_do_app() -> dict:
    """{id_item: a peça do catálogo do App} (a tela do Almoxarifado), para o nome e a unidade da peça da contagem gravada."""
    from .. import almoxarifado
    d = almoxarifado.montar().dados or {}
    return {_id(c.get("id")): c for c in d.get("catalogo", [])} if d.get("estado") == "ok" else {}


def _pecas_da_contagem(almox: str, eventos: list[dict], ja: set, catalogo: dict | None) -> list[dict]:
    """As peças da contagem GRAVADA deste almoxarifado que a varredura do App ainda não traz (a revisão de 11/11/2026): a gravação
    as ligou no Fracttal, e a varredura só as lê no ciclo seguinte; até lá, sem esta lista, o PCM não registraria o acordado
    logo depois da auditoria (o `decidir` só aceita a peça do almoxarifado). Na forma das linhas da varredura: o saldo e o código
    do `peca_gravada`; o nome, a família e a unidade do catálogo do App (sem ele, vazios: a unidade que ninguém disse é
    inteira); o mínimo, nenhum (a varredura não o leu)."""
    out = []
    for (a, item), g in sorted(_gravadas(eventos).items()):
        if a != almox or item in ja:
            continue
        c = (catalogo or {}).get(item) or {}
        out.append({"id_item": item, "id_almox": almox, "codigo": A._txt(c.get("codigo")) or g["codigo"],
                    "nome": A._txt(c.get("nome")), "familia": A._txt(c.get("familia")), "unidade": A._txt(c.get("unidade")),
                    "avariado": bool(c.get("avariado")), "saldo": g["saldo"], "minimo": None, "usina_id": g["usina_id"]})
    return out


def _da_varredura(id_almox: str) -> list[dict]:
    """As linhas do almoxarifado na varredura diária do App (a tela do Almoxarifado, `almoxarifado.montar`). Sem o saldo
    (livros do App ainda não publicados, ou incoerentes sem ciclo guardado), vazio: número pela metade não vai para a tela."""
    from .. import almoxarifado
    d = almoxarifado.montar().dados or {}
    if d.get("estado") != "ok":
        return []
    return [l for l in d.get("linhas", []) if _id(l.get("id_almox")) == id_almox]


def _arquivo_lida(cfg, almox: str):
    """`<NEXUS_DADOS>/almox_inventario/regua-lida-<almox>.json`: o que o Fracttal tinha de mínimo e máximo na última releitura do
    Nexus. É a foto do Fracttal para a tela (como o controle da gravação, fora do banco: não é dado de negócio, e o rastro de
    negócio é o evento `regua_gravada`). Em teste sem pasta de dados, nenhum."""
    from .gravacao import _pasta
    p = _pasta(cfg)
    return None if p is None or not str(almox).isdigit() else p / f"regua-lida-{almox}.json"


def guardar_lida(cfg, almox: str, lido: dict, quando) -> None:
    """Guarda a releitura do almoxarifado inteiro (`Estoque.ler`): o mínimo e o máximo de cada peça ligada, e a hora. O arquivo
    que não grava só tira o "no Fracttal agora" da tela (a coluna volta a ser a da varredura): nunca para quem gravou."""
    arq = _arquivo_lida(cfg, _id(almox))
    if arq is None:
        return
    from .gravacao import _gravar_json, _iso
    try:
        _gravar_json(arq, {"lido_em": _iso(quando), "pecas": {str(i): [_num(v.get("minimo")), _num(v.get("maximo"))]
                                                              for i, v in (lido or {}).items() if isinstance(v, dict)}})
    except OSError as ex:
        logging.warning("régua: a releitura do almoxarifado %s não ficou guardada (%s)", almox, type(ex).__name__)


def lida(cfg, almox: str) -> dict | None:
    """A última releitura guardada (`{"lido_em", "pecas": {id_item: (mínimo, máximo)}}`), ou None (nunca relido, sem pasta, ou o
    arquivo que não se lê: na dúvida, a tela mostra a varredura)."""
    arq = _arquivo_lida(cfg, _id(almox))
    if arq is None:
        return None
    from .gravacao import _ler_json
    try:
        d = _ler_json(arq)
        quando = E.instante(d.get("lido_em")) if isinstance(d, dict) else None
    except (F.Recusada, ValueError, OSError):        # o disco que não deixa ler não derruba a régua: vale a varredura
        return None
    if quando is None or not isinstance(d.get("pecas"), dict):
        return None
    pecas = {}
    for i, par in d["pecas"].items():
        if isinstance(par, (list, tuple)) and len(par) == 2:
            pecas[str(i)] = (_num(par[0]), _num(par[1]))
    return {"lido_em": quando, "pecas": pecas}


def _quando_lido(quando) -> str:
    """"às 14:05" (hoje, em Brasília) ou "em 25/10 às 14:05"."""
    d = quando.astimezone(_BRT)
    hoje = visao._agora().astimezone(_BRT).date()
    return f"às {d:%H:%M}" if d.date() == hoje else f"em {d:%d/%m} às {d:%H:%M}"


def _montar(l: dict, almox: str, vig: dict, gravados: dict) -> dict:
    item = _id(l.get("id_item"))
    k = (almox, item)
    if k in gravados:
        saldo, de = gravados[k], "contagem gravada"
    else:
        saldo, de = _num(l.get("saldo")), "varredura"
    av, dec = avariada(l.get("codigo"), l.get("avariado")), decimal(l.get("unidade"))
    smin, smax = sugestao(saldo, av, dec)
    v = vig.get(k) or {}
    return {"id_item": item, "codigo": A._txt(l.get("codigo")), "nome": A._txt(l.get("nome")),
            "familia": A._txt(l.get("familia")), "unidade": A._txt(l.get("unidade")).upper(), "avariada": av,
            "decimal": dec, "saldo": saldo, "saldo_de": de, "no_fracttal_min": _num(l.get("minimo")),
            "sugestao_min": smin, "sugestao_max": smax,
            "recomendado": v.get("recomendado", (None, None)), "acordado": v.get("acordado", (None, None)),
            "gravado": bool(v.get("gravado")), "decidida_em": v.get("quando", ""), "usina_id": l.get("usina_id")}


def quadro(cfg, id_almox: str, *, varredura: list[dict] | None = None, lida_depois_de: str | None = None,
           catalogo: dict | None = None) -> list[dict]:
    """Uma entrada por peça do almoxarifado: o saldo (o da última contagem gravada; sem ela, o da varredura), a sugestão, o
    recomendado e o acordado vigentes (a última decisão do `fato_regua_minimo`) e se o acordado já foi ao Fracttal.
    `varredura`: as linhas do saldo do almoxarifado no formato da tela do Almoxarifado; sem elas, as da varredura do App.
    Livro que não se lê levanta `Recusada` (nunca devolve vazio no lugar do que não leu).

    `agora_min`, `agora_max` e `agora_em` (11/11/2026): o que o Fracttal tinha na última releitura do Nexus (`lida`), quando ela é
    mais nova que a varredura que a tela mostra (`lida_depois_de`, o fim do ciclo do App; sem ele, não se sabe qual é a mais
    nova, e vale a varredura): "no Fracttal agora", sem esperar o ciclo seguinte do App. Sem releitura mais nova, `agora_em`
    vazio, e a coluna é a da varredura (só o mínimo: o App não traz o máximo).

    Desde a revisão de 11/11/2026, também as peças da contagem gravada que a varredura ainda não traz (`_pecas_da_contagem`;
    `catalogo` `{id_item: peça}` dá o nome e a unidade delas, e sem `varredura` vem do catálogo do App)."""
    alvo = _id(id_almox)
    linhas = _da_varredura(alvo) if varredura is None else [l for l in varredura if _id(l.get("id_almox")) == alvo]
    livro = F.ler(cfg)
    linhas = linhas + _pecas_da_contagem(alvo, livro[F.ABA_EVENTO], {_id(l.get("id_item")) for l in linhas},
                                         _catalogo_do_app() if varredura is None else catalogo)
    vig, gravados = _vigentes(livro[F.ABA_REGUA]), _saldos_gravados(livro[F.ABA_EVENTO])
    lido = lida(cfg, alvo) if lida_depois_de else None
    try:
        if lido and lido["lido_em"] <= E.instante(lida_depois_de):
            lido = None                          # a varredura é mais nova: ela já traz o que a releitura viu
    except ValueError:
        lido = None
    out = []
    for l in linhas:
        x = _montar(l, alvo, vig, gravados)
        par = (lido or {}).get("pecas", {}).get(x["id_item"]) if lido else None
        x.update(agora_min=par[0] if par else None, agora_max=par[1] if par else None,
                 agora_em=_quando_lido(lido["lido_em"]) if par else "")
        out.append(x)
    return sorted(out, key=lambda x: (x["codigo"], x["id_item"]))


# ── registrar e gravar ───────────────────────────────────────────────────────────────────────────────────────────────
def _linha_da_peca(cfg, almox: str, item: str, varredura) -> dict:
    """A peça de um almoxarifado, pelo saldo dele (a varredura do App) ou pela contagem gravada dele (`_pecas_da_contagem`: a
    peça que a gravação ligou e a varredura ainda não leu): o ID que a página mandou só vale se a peça é daquele almoxarifado."""
    linhas = _da_varredura(almox) if varredura is None else varredura
    for l in linhas:
        if _id(l.get("id_almox")) == almox and _id(l.get("id_item")) == item:
            return l
    for l in _pecas_da_contagem(almox, F.ler(cfg)[F.ABA_EVENTO], set(), _catalogo_do_app() if varredura is None else None):
        if l["id_item"] == item:
            return l
    raise ValueError(f"A peça {item} não está no saldo do almoxarifado {almox} nem numa contagem gravada dele (a varredura do "
                     "App ainda não a leu?): nada foi registrado.")


def _retrato(almox, item, codigo, usina_id, sug, rec, aco, gravado, quem_) -> dict:
    return {"id_almoxarifado": almox, "id_item": item, "codigo": codigo or None, "usina_id": usina_id or None,
            "usina_ligada_por": LIGADA if usina_id else None,
            "sugestao_min_qtd": sug[0], "sugestao_max_qtd": sug[1],
            "recomendado_min_qtd": rec[0], "recomendado_max_qtd": rec[1],
            "acordado_min_qtd": aco[0], "acordado_max_qtd": aco[1], "gravado_fracttal": 1 if gravado else 0, **quem_}


def decidir(cfg, id_almox: str, id_item: str, *, recomendado=None, acordado=None, pessoa: dict | None,
            varredura: list[dict] | None = None) -> None:
    """Registra no livro o recomendado e/ou o acordado de uma peça (cada um `(mínimo, máximo)`; o que não vem fica como
    estava). NÃO fala com o Fracttal: quem manda o acordado para lá é `gravar_acordado`. `ValueError` quando o pedido não
    faz sentido (mínimo acima do máximo, número que não é número, peça que não é do almoxarifado): nada é escrito."""
    rec, aco = _par(recomendado, "O recomendado"), _par(acordado, "O acordado", completo=True)
    if rec is None and aco is None:
        raise ValueError("Nada para registrar: informe o recomendado ou o acordado.")
    almox, item = _id(id_almox), _id(id_item)
    l = _linha_da_peca(cfg, almox, item, varredura)
    if aco is not None:
        _confere_a_unidade(aco, l.get("unidade"))
    with _PECA.de((almox, item)):
        livro = F.ler(cfg, forcar=True)
        antes = _vigentes(livro[F.ABA_REGUA]).get((almox, item)) or {}
        agora = _montar(l, almox, {}, _saldos_gravados(livro[F.ABA_EVENTO]))
        rec_final = rec if rec is not None else antes.get("recomendado", (None, None))
        aco_final = aco if aco is not None else antes.get("acordado", (None, None))
        # o acordado novo ainda não está no Fracttal; o que já foi gravado só continua valendo se o acordado é o mesmo
        gravado = bool(antes.get("gravado")) and aco_final == antes.get("acordado")
        F.acrescentar(cfg, F.ABA_REGUA, [_retrato(
            almox, item, A._txt(l.get("codigo")), l.get("usina_id"), (agora["sugestao_min"], agora["sugestao_max"]),
            rec_final, aco_final, gravado, quem.colunas(cfg, pessoa))])


def _confere_a_unidade(par, unidade) -> None:
    """O acordado com casa decimal só vale em METRO e MASSA: o Fracttal guarda o que se manda, e 2,5 de uma peça contada em
    unidades seria um estoque que não existe. A unidade que não se sabe é inteira (a mesma regra da sugestão). `ValueError`."""
    if any(isinstance(n, float) and not n.is_integer() for n in par) and not decimal(unidade):
        raise ValueError(f"O acordado ({fmt(par[0]) or 'sem mínimo'} a {fmt(par[1])}) tem casa decimal, e a unidade da peça "
                         f"({_txt_unidade(unidade)}) é inteira: só METRO e MASSA aceitam decimais. Nada foi registrado.")


def _txt_unidade(unidade) -> str:
    return A._txt(unidade).lower() or "não informada"


def _igual(lido, esperado) -> bool:
    return lido is not None and abs(lido - esperado) <= _TOLERANCIA


def gravar_acordado(cfg, id_almox: str, id_item: str, estoque: E.Estoque, pessoa: dict | None, *,
                    esperado: tuple | None = None) -> str:
    """Manda ao Fracttal o mínimo e o máximo ACORDADOS (o recomendado nunca vai), relê e só então anota o evento
    `regua_gravada` e o retrato `gravado_fracttal`. Devolve o texto para a tela. O Fracttal que o chamador passa é o da
    sessão de quem aprovou (`estoque_da_sessao`).

    `esperado` é o `(mínimo, máximo)` que a página MOSTRAVA a quem apertou: se o acordado registrado agora é outro (outra pessoa
    do PCM mexeu enquanto a tela estava aberta), nada é enviado: `Conflito` ("a régua mudou desde que você abriu a tela").
    `ValueError` quando o acordado tem decimal e a unidade que o Fracttal diz é inteira (antes do pedido que grava).
    `Conflito` também quando a peça não tem acordado registrado, o par registrado está incompleto (uma linha do livro só com
    um dos números) ou a peça não está ligada ao almoxarifado (nada foi enviado); `NaoConfere` quando o Fracttal respondeu e a
    releitura não bateu (anota um `erro`, nunca o `regua_gravada`); `Limite`, `SemLogin` e `ErroFracttal` sobem como são.
    Idempotente: gravar o mesmo par duas vezes dá o mesmo resultado."""
    almox, item = _id(id_almox), _id(id_item)
    with _PECA.de((almox, item)):
        v = _vigentes(F.ler(cfg, forcar=True)[F.ABA_REGUA]).get((almox, item))
        if not v or v["acordado"] == (None, None):
            raise Conflito("Esta peça ainda não tem o mínimo e o máximo ACORDADOS registrados: nada foi enviado ao Fracttal "
                           "(só o acordado vai; o recomendado fica no Nexus).")
        mn, mx = v["acordado"]
        if mn is None or mx is None:
            raise Conflito(f"O acordado registrado desta peça está incompleto (mínimo {fmt(mn) or 'em branco'}, máximo "
                           f"{fmt(mx) or 'em branco'}): os dois vão ao Fracttal. Registre o mínimo e o máximo de novo; nada foi "
                           "enviado.")
        if esperado is not None and tuple(esperado) != (mn, mx):
            raise Conflito(f"Nada foi enviado: a régua mudou desde que você abriu a tela; recarregue a página e confira antes de "
                           f"gravar (o acordado registrado agora é mínimo {fmt(mn)}, máximo {fmt(mx)}).")
        quem_ = quem.colunas(cfg, pessoa)
        peca = estoque.ler(almox).get(item)            # a leitura também guarda a ligação que o `definir_regua` usa
        if peca is None:
            raise Conflito(f"A peça {v['codigo'] or item} não está ligada ao almoxarifado {almox} no Fracttal: a régua é do "
                           "vínculo dela com o almoxarifado (a gravação da contagem a liga). Nada foi enviado.")
        _confere_a_unidade((mn, mx), peca.get("unidade"))      # a unidade que o Fracttal diz, antes do pedido que grava
        estoque.definir_regua(almox, item, mn, mx)
        relido = estoque.ler(almox)
        guardar_lida(cfg, almox, relido, datetime.now(timezone.utc))      # a tela mostra "no Fracttal agora" de todas as peças
        depois = relido.get(item) or {}
        base = {"id_almoxarifado": almox, "id_item": item, "codigo": v["codigo"] or None,
                "usina_id": v["usina_id"], "usina_ligada_por": v["usina_ligada_por"] or None, **quem_}
        if not (_igual(depois.get("minimo"), mn) and _igual(depois.get("maximo"), mx)):
            try:
                F.acrescentar(cfg, F.ABA_EVENTO, [{**base, "tipo": "erro", "de_qtd": peca.get("minimo"), "para_qtd": mn,
                                                   "dados": {"motivo": "a releitura do Fracttal não bateu com o acordado"}}])
            except F.Recusada:      # o erro já é o que a tela vai dizer; sem o livro, ao menos ele sobe
                pass
            raise NaoConfere(f"O Fracttal respondeu, mas a releitura não bateu com o acordado (mínimo {fmt(mn)}, máximo "
                             f"{fmt(mx)}): a régua NÃO foi anotada como gravada. Confira a peça na tela do Fracttal.")
        # o evento primeiro: se o retrato falhar, a peça segue "não gravada" e o PCM grava de novo (é idempotente); o
        # contrário deixaria o livro dizendo "gravado" sem o rastro
        F.acrescentar(cfg, F.ABA_EVENTO, [{**base, "tipo": "regua_gravada", "de_qtd": peca.get("minimo"), "para_qtd": mn}])
        F.acrescentar(cfg, F.ABA_REGUA, [_retrato(almox, item, v["codigo"], v["usina_id"], v["sugestao"],
                                                  v["recomendado"], v["acordado"], True, quem_)])
    return f"Régua gravada no Fracttal: mínimo {fmt(mn)}, máximo {fmt(mx)}."


# ── todos os acordados de um almoxarifado (11/11/2026, item 2 da 2ª rodada) ─────────────────────────────────────────────
class _LimiteDeNovo(Exception):
    """O 429 que voltou depois da espera de 62 s: o lote para (o resto não vai), como na gravação."""


JA_ANDANDO = "Já tem um lote de acordados indo ao Fracttal neste almoxarifado: espere ele terminar. Nada foi enviado."
INTERROMPIDO = ("o Nexus reiniciou no meio do lote: grave de novo (a peça que o Fracttal já tem é anotada, sem mandar de "
                "novo)")
RESULTADO_H = 12             # o resultado do último lote fica na tela da régua por este tempo depois do fim
_ANDANDO: dict = {}          # almoxarifado -> a thread do lote do botão (`iniciar_lote`)


def _texto_do_lote(r: dict, prefixo: str = "Acordados deste almoxarifado") -> str:
    """O que a tela (o resultado do lote; a etapa Gravação da contagem, com o `prefixo` "Régua acordada") diz do lote."""
    if not r["total"]:
        return "Nenhuma peça deste almoxarifado tem o acordado registrado: nada foi ao Fracttal."

    def n(k, um, varios):
        return f"{r[k]} {um if r[k] == 1 else varios}"
    partes = []
    if r["gravadas"]:
        partes.append(n("gravadas", "gravado no Fracttal e relido", "gravados no Fracttal e relidos"))
    if r["iguais"]:
        partes.append(n("iguais", "já estava igual", "já estavam iguais"))
    if r["falhas"]:
        partes.append(n("falhas", "falhou", "falharam") + " (veja a Auditoria)")
    if r["sem_ligacao"]:
        partes.append(n("sem_ligacao", "sem ligação com o almoxarifado no Fracttal", "sem ligação com o almoxarifado no Fracttal"))
    if r["incompletas"]:
        partes.append(n("incompletas", "com o acordado incompleto (registre o mínimo e o máximo)",
                        "com o acordado incompleto (registre o mínimo e o máximo)"))
    if r["nao_enviadas"]:
        partes.append(n("nao_enviadas", "não foi mandado", "não foram mandados") + f" ({r['parou']}: grave de novo)")
    texto = f"{prefixo}: " + ", ".join(partes) + "."
    if r.get("sem_livro"):
        texto += (f" O Fracttal recebeu, mas não consegui anotar no livro do inventário ({r['sem_livro']}): grave de novo, é o "
                  "mesmo número.")
    return texto


def _tom_do_lote(r: dict) -> str:
    """A cor do resultado (a revisão de 11/11/2026: o lote com falha saía na caixa verde de sucesso)."""
    return "alerta" if r.get("falhas") or r.get("nao_enviadas") or r.get("sem_livro") or r.get("incompletas") \
        or r.get("sem_ligacao") else "ok"


def lote_andando(id_almox: str) -> bool:
    """O lote dos acordados deste almoxarifado está andando (a vez dele, `_LOTE`, presa)? A gravação de contagem pergunta antes
    de começar e de continuar (`gravacao._sem_lote_da_regua`), sob a mesma trava em que o lote confere a vez dela."""
    return _LOTE.de(_id(id_almox)).locked()


def gravar_acordados(cfg, id_almox: str, estoque: E.Estoque, quem_: dict, *, contagem_id: str | None = None, dormir=None,
                     agora=None, ao_andar=None) -> dict:
    """Manda ao Fracttal a régua ACORDADA de cada peça do almoxarifado cujo acordado difere do que o Fracttal tem (o recomendado e
    a sugestão nunca vão; a peça sem acordado não muda), relê e só então anota: o evento `regua_gravada` (o mínimo de -> para) e o
    retrato `gravado_fracttal`, como `gravar_acordado`, mas de uma leitura, um pedido por peça mandada e uma releitura por lote de
    `LOTE_REGUA` (o livro também é escrito uma vez por lote, e não duas vezes por peça). O estoque é o do login de quem gravou
    (o botão da régua, pelo `iniciar_lote`, ou a sessão do Fracttal da gravação da contagem que acabou, `gravacao`); `quem_` as
    colunas da pessoa (`quem.colunas`, ou o aprovador da gravação); `contagem_id`, a contagem cuja gravação puxou o lote (vai nos
    eventos: a Auditoria da contagem os mostra).

    A peça que o Fracttal já tem igual não gasta pedido; se o retrato ainda não dizia "gravado" (o lote que o reinício cortou, o
    livro que recusou o registro, quem gravou à mão), ela ganha um `regua_gravada` de igual para igual e o retrato (a Auditoria
    não perde quem nem quando). O acordado de cada peça é relido sob a trava dela logo antes de mandar (o que outra pessoa
    registrou com o lote andando vai no lugar do de antes). A falha de uma peça é registrada (um evento `erro`, com o porquê
    cifrado e só texto do Nexus) e não para as outras: o `success: false` (`Recusado`) não gravou; a resposta perdida (rede)
    talvez gravou, e a releitura decide. O 429 espera 62 s FORA da trava da peça e tenta UMA vez; de novo, o lote para e o resto
    não vai (o texto diz quantas). O login que expira também para. A releitura que não veio deixa as mandadas sem anotação de
    gravada (o livro nunca diz que o Fracttal tem o que não tem). O acordado que outra pessoa registrou depois do envio não vira
    "gravado" (o retrato é escrito sob a trava da peça, conferindo o registrado de agora). Um lote de cada vez por almoxarifado
    (`Conflito`).

    `Limite`, `SemLogin` e `ErroFracttal` da PRIMEIRA leitura sobem (nada foi mandado); o resto vira o resumo: `{"total", "a_mandar",
    "feitas", "gravadas", "iguais", "falhas", "sem_ligacao", "incompletas", "nao_enviadas", "parou", "sem_livro", "lido_em",
    "texto"}`. `feitas` conta as peças que andaram (mandadas, recusadas, reavaliadas), nunca a que o lote parou antes de mandar.
    `ao_andar(resumo)` a cada peça (o controle do lote e a etapa Gravação mostram o andamento)."""
    almox = _id(id_almox)
    trava = _LOTE.de(almox)
    if not trava.acquire(blocking=False):
        raise Conflito(JA_ANDANDO)
    try:
        return _gravar_acordados(cfg, almox, estoque, quem_, contagem_id, dormir or time.sleep,
                                 agora or (lambda: datetime.now(timezone.utc)), ao_andar)
    finally:
        trava.release()


def _classificar(v: dict, peca: dict | None) -> str:
    """O que fazer com a peça de acordado registrado `v`, pelo que o Fracttal tem dela (`peca`, da leitura do almoxarifado):
    "incompleta" (uma linha do livro com só um dos números: os dois vão ao Fracttal), "sem_ligacao" (a régua é do vínculo da peça
    com o almoxarifado, e a gravação da contagem é que liga), "igual" (o Fracttal já tem), "unidade" (casa decimal com a unidade
    inteira) ou "mandar"."""
    mn, mx = v["acordado"]
    if mn is None or mx is None:
        return "incompleta"
    if peca is None:
        return "sem_ligacao"
    if _igual(peca.get("minimo"), mn) and _igual(peca.get("maximo"), mx):
        return "igual"
    if any(isinstance(n, float) and not n.is_integer() for n in (mn, mx)) and not decimal(peca.get("unidade")):
        return "unidade"
    return "mandar"


def _gravar_acordados(cfg, almox, estoque, quem_, contagem_id, dormir, agora, ao_andar) -> dict:
    r = {"total": 0, "a_mandar": 0, "feitas": 0, "gravadas": 0, "iguais": 0, "falhas": 0, "sem_ligacao": 0, "incompletas": 0,
         "nao_enviadas": 0, "parou": "", "sem_livro": "", "lido_em": ""}
    acordados = {item: v for (a, item), v in _vigentes(F.ler(cfg, forcar=True)[F.ABA_REGUA]).items()
                 if a == almox and v["acordado"] != (None, None)}
    r["total"] = len(acordados)
    if not acordados:                             # nem a leitura vai ao Fracttal: a cota é da empresa
        return dict(r, texto=_texto_do_lote(r))

    def chamar(f, *args):
        try:
            return f(*args)
        except E.Limite:
            dormir(ESPERA_LIMITE_S)
            try:
                return f(*args)
            except E.Limite as ex:
                raise _LimiteDeNovo() from ex

    try:
        antes = chamar(estoque.ler, almox)
    except _LimiteDeNovo:
        raise E.Limite("o Fracttal pediu uma pausa de novo depois de 62 s") from None
    lido, lido_em = antes, agora()

    def base(item, v) -> dict:
        b = {"id_almoxarifado": almox, "id_item": item, "codigo": v["codigo"] or None, "usina_id": v["usina_id"],
             "usina_ligada_por": v["usina_ligada_por"] or None, **quem_}
        return dict(b, contagem_id=contagem_id) if contagem_id else b

    def erro(item, v, peca, motivo) -> dict:
        return dict(base(item, v), tipo="erro", de_qtd=(peca or {}).get("minimo"), para_qtd=v["acordado"][0],
                    dados={"motivo": motivo})

    eventos, ficam_gravados = [], []             # ficam_gravados: (peça, o acordado que o Fracttal tem)

    def vai(item, v, peca, como) -> bool:
        """Conta e anota a peça que não vai ao Fracttal agora; True quando ela vai."""
        if como == "mandar":
            return True
        if como == "incompleta":
            r["incompletas"] += 1
        elif como == "sem_ligacao":
            r["sem_ligacao"] += 1
        elif como == "unidade":
            r["falhas"] += 1
            eventos.append(erro(item, v, peca, "o acordado tem casa decimal e a unidade da peça no Fracttal é inteira"))
        else:
            r["iguais"] += 1
            if not v["gravado"]:
                # o Fracttal já tem e o livro não diz: o evento de igual para igual (a Auditoria não perde quem nem quando)
                eventos.append(dict(base(item, v), tipo="regua_gravada", de_qtd=v["acordado"][0], para_qtd=v["acordado"][0]))
                ficam_gravados.append((item, v["acordado"]))
        return False

    a_mandar = [(item, antes.get(item)) for item, v in sorted(acordados.items())
                if vai(item, v, antes.get(item), _classificar(v, antes.get(item)))]
    r["a_mandar"] = len(a_mandar)
    if ao_andar:
        ao_andar(dict(r))

    def enviar(item, peca):
        """Manda o acordado de AGORA, relido sob a trava da peça (o que outra pessoa registrou com o lote andando vale), e devolve
        (o retrato que foi, a resposta perdida) ou None se ele já não vai (`vai` o contou). O 429 espera FORA da trava: registrar
        o acordado da peça não espera os 62 s."""
        for tentativa in (1, 2):
            with _PECA.de((almox, item)):
                v = _vigentes(F.ler(cfg)[F.ABA_REGUA]).get((almox, item)) or acordados[item]
                if v["acordado"] == (None, None) or not vai(item, v, peca, _classificar(v, peca)):
                    return None
                try:
                    estoque.definir_regua(almox, item, *v["acordado"])
                except E.Limite as ex:
                    if tentativa == 2:
                        raise _LimiteDeNovo() from ex
                except (E.SemLogin, E.Recusado, ValueError):
                    raise
                except Exception as ex:            # noqa: BLE001 — a resposta que não veio: talvez gravou, a releitura decide
                    return v, type(ex).__name__
                else:
                    return v, ""
            dormir(ESPERA_LIMITE_S)
        return None

    for k in range(0, max(len(a_mandar), 1), LOTE_REGUA):
        enviadas = []
        for item, peca in a_mandar[k:k + LOTE_REGUA]:
            if r["parou"]:
                r["nao_enviadas"] += 1
                continue
            try:
                foi = enviar(item, peca)
            except _LimiteDeNovo:
                r["parou"], r["nao_enviadas"] = LIMITE, r["nao_enviadas"] + 1      # o 429 não executa nada
            except E.SemLogin:
                r["parou"], r["nao_enviadas"] = LOGIN, r["nao_enviadas"] + 1
            except (E.Recusado, ValueError) as ex:   # o "não" com todas as letras, ou o pedido que nem saiu: nada foi gravado
                r["falhas"], r["feitas"] = r["falhas"] + 1, r["feitas"] + 1
                eventos.append(erro(item, acordados[item], peca, f"o Fracttal recusou a régua ({type(ex).__name__})"))
            else:
                r["feitas"] += 1
                if foi is not None:
                    enviadas.append((item, foi[0], peca, foi[1]))
            if ao_andar:
                ao_andar(dict(r))
        depois = None
        if enviadas:
            try:
                depois = chamar(estoque.ler, almox)
                lido, lido_em = depois, agora()
            except Exception as ex:                # noqa: BLE001 — sem a releitura nada é anotado como gravado
                r["parou"] = r["parou"] or (LOGIN if isinstance(ex, E.SemLogin) else LIMITE if isinstance(ex, _LimiteDeNovo)
                                            else SEM_RELEITURA)
        for item, v, peca, perdida in enviadas:
            mn, mx = v["acordado"]
            agora_ = (depois or {}).get(item) or {}
            if depois is None:
                r["falhas"] += 1
                eventos.append(erro(item, v, peca, "a régua foi enviada, mas a releitura do Fracttal não veio: confira na tela "
                                                   "do Fracttal"))
            elif _igual(agora_.get("minimo"), mn) and _igual(agora_.get("maximo"), mx):
                r["gravadas"] += 1
                eventos.append(dict(base(item, v), tipo="regua_gravada", de_qtd=peca.get("minimo"), para_qtd=mn))
                ficam_gravados.append((item, v["acordado"]))
            else:
                r["falhas"] += 1
                eventos.append(erro(item, v, peca, "a releitura do Fracttal não bateu com o acordado"
                                    + (f" (a resposta não veio: {perdida})" if perdida else "")))
        if eventos or ficam_gravados:
            r["sem_livro"] = r["sem_livro"] or _registrar_lote(cfg, almox, eventos, ficam_gravados, quem_)
        eventos.clear()
        ficam_gravados.clear()
    guardar_lida(cfg, almox, lido, lido_em)
    r["lido_em"] = E.instante(lido_em).isoformat()
    return dict(r, texto=_texto_do_lote(r))


def _registrar_lote(cfg, almox, eventos, ficam_gravados, quem_) -> str:
    """Escreve os eventos e os retratos `gravado_fracttal` de um lote, o evento primeiro (como `gravar_acordado`: o retrato que
    falhar deixa a peça "não gravada", e gravar de novo é o mesmo número). O retrato só sai se o acordado registrado AGORA é o que
    o Fracttal tem, conferido sob a trava de cada peça (ninguém registra outro acordado dela entre a conferência e a escrita). ""
    se gravou; senão o porquê (o Fracttal já recebeu: o texto manda gravar de novo, e o lote seguinte anota a peça igual e sem
    evento de igual para igual)."""
    itens = sorted({e["id_item"] for e in eventos} | {i for i, _ in ficam_gravados})
    travas = [_PECA.de((almox, i)) for i in itens]
    for tr in travas:
        tr.acquire()
    try:
        linhas = []
        if ficam_gravados:
            vig = _vigentes(F.ler(cfg, forcar=True)[F.ABA_REGUA])
            for item, aco in ficam_gravados:
                v = vig.get((almox, item))
                if v and v["acordado"] == aco:
                    linhas.append(_retrato(almox, item, v["codigo"], v["usina_id"], v["sugestao"], v["recomendado"], aco,
                                           True, quem_))
        if eventos:
            F.acrescentar(cfg, F.ABA_EVENTO, list(eventos))
        if linhas:
            F.acrescentar(cfg, F.ABA_REGUA, linhas)
        return ""
    except (F.Recusada, OSError) as ex:
        logging.warning("régua: o lote do almoxarifado %s não entrou no livro (%s)", almox, type(ex).__name__)
        return str(ex) if isinstance(ex, F.Recusada) else type(ex).__name__
    finally:
        for tr in reversed(travas):
            tr.release()


# ── o lote do botão em segundo plano (a revisão de 11/11/2026) ───────────────────────────────────────────────────────────
def _arquivo_lote(cfg, almox: str):
    """`<NEXUS_DADOS>/almox_inventario/regua-lote-<almox>.json`: o controle do lote do botão (o andamento, o resultado e quem
    mandou, como código; nunca o login), na pasta do controle da gravação. Sem a pasta, o lote não começa."""
    from .gravacao import _pasta
    p = _pasta(cfg)
    if p is None:
        raise F.Recusada("Este Nexus está sem pasta de dados (NEXUS_DADOS): nada foi enviado.")
    return p / f"regua-lote-{almox}.json"


def _salvar_lote(arq, ctrl: dict, relogio) -> None:
    """Salva o controle do lote; o disco que falha só tira o andamento da tela e a espera do deploy (nunca para o lote)."""
    from .gravacao import _gravar_json, _iso
    ctrl["atualizado_em"] = _iso(relogio())
    try:
        _gravar_json(arq, ctrl)
    except OSError as ex:
        logging.warning("régua: o controle do lote do almoxarifado %s não gravou (%s)", ctrl.get("id_almox"), type(ex).__name__)


_RESUMO = ("total", "a_mandar", "feitas", "gravadas", "iguais", "falhas", "sem_ligacao", "incompletas", "nao_enviadas", "parou",
           "sem_livro")


def iniciar_lote(cfg, id_almox: str, estoque: E.Estoque, quem_: dict, *, dormir=None, agora=None) -> dict:
    """O botão "Gravar no Fracttal todos os acordados deste almoxarifado" (a revisão de 11/11/2026): o lote (`gravar_acordados`)
    roda numa thread, com um controle "gravando" salvo a cada peça (`regua-lote-<almox>.json`), que o deploy espera
    (`gravacao.com_lote_aberto`) e a tela acompanha (`estado_do_lote`, o `lote.json`). Antes rodava dentro do pedido: 100 peças
    são uns 2 min (574, uns 10), e o restart do deploy no meio deixava peças mandadas sem o evento.

    A vez: a do lote (`_LOTE`) é tomada primeiro; com ela presa, a da gravação de contagem é conferida (`gravacao.vez_presa`: uma
    gravação andando, ou parada no meio, talvez com o almoxarifado travado em ajuste) e o modo do almoxarifado no Fracttal (fora
    do 0, o ajuste aberto ou o inventário físico, nada vai: a régua mandada com o ajuste aberto nunca foi provada). A gravação de
    contagem, do outro lado, recusa enquanto o lote anda (`lote_andando`), sob a mesma trava. `Conflito` (409), `Recusada` (sem
    a pasta de dados) e os erros do Fracttal no `modo` sobem antes da thread; o estoque é o do login de quem apertou."""
    almox = _id(id_almox)
    if not almox.isdigit():
        raise ValueError("Escolha o almoxarifado: nada foi enviado ao Fracttal.")
    trava = _LOTE.de(almox)
    if not trava.acquire(blocking=False):
        raise Conflito(JA_ANDANDO)
    try:
        from . import gravacao
        presa = gravacao.vez_presa(cfg, almox)
        if presa:
            raise Conflito(f"Nada foi enviado: {presa.rstrip('.')}.")
        arq = _arquivo_lote(cfg, almox)
        modo = estoque.modo(almox)
        if modo != 0:
            onde = {2: "em ajuste de inventário (modo 2)", 3: "em inventário físico (modo 3)"}.get(modo, f"no modo {modo}")
            raise Conflito(f"Nada foi enviado: o almoxarifado está {onde} no Fracttal. Feche o ajuste e grave de novo.")
        relogio = agora or (lambda: datetime.now(timezone.utc))
        from .gravacao import _iso
        ctrl = {"id_almox": almox, "estado": "gravando", "inicio": _iso(relogio()),
                "pessoa_hmac": quem_.get("pessoa_hmac") or "", **dict.fromkeys(_RESUMO[:-2], 0), "parou": "", "sem_livro": ""}
        _salvar_lote(arq, ctrl, relogio)
        th = threading.Thread(target=_rodar_lote, args=(cfg, almox, estoque, quem_, arq, ctrl, dormir, relogio, trava),
                              name=f"regua-acordados-{almox}", daemon=True)
        _ANDANDO[almox] = th
        th.start()
    except BaseException:
        _ANDANDO.pop(almox, None)
        trava.release()
        raise
    return estado_do_lote(cfg, almox)


def _rodar_lote(cfg, almox, estoque, quem_, arq, ctrl, dormir, relogio, trava) -> None:
    """A thread do lote do botão: o andamento vai ao controle a cada peça, e o fim (concluído ou parado) também; a vez do lote é
    solta no fim. O Nexus que morre no meio deixa o controle "gravando" (a tela diz que parou, `estado_do_lote`)."""
    from .gravacao import _iso, _motivo_do_erro

    def andou(r: dict) -> None:
        ctrl.update({k: r[k] for k in _RESUMO})
        _salvar_lote(arq, ctrl, relogio)
    try:
        try:
            r = _gravar_acordados(cfg, almox, estoque, quem_, None, dormir or time.sleep, relogio, andou)
            ctrl.update({k: r[k] for k in _RESUMO}, estado="concluida", texto=r["texto"], tom=_tom_do_lote(r),
                        fim=_iso(relogio()))
        except Exception as ex:                    # noqa: BLE001 — o lote para, e a tela diz por quê
            logging.warning("régua: o lote do almoxarifado %s parou (%s)", almox, type(ex).__name__)
            motivo = (LOGIN if isinstance(ex, E.SemLogin) else LIMITE if isinstance(ex, E.Limite)
                      else str(ex) if isinstance(ex, F.Recusada) else _motivo_do_erro(ex))
            ctrl.update(estado="parada", motivo=motivo, texto=f"O lote dos acordados parou: {motivo}. Grave de novo.",
                        tom="critico", fim=_iso(relogio()))
        _salvar_lote(arq, ctrl, relogio)
    finally:
        _ANDANDO.pop(almox, None)
        trava.release()


def estado_do_lote(cfg, id_almox: str) -> dict | None:
    """O último lote do botão neste almoxarifado (o controle), ou None. O "gravando" sem a thread viva neste processo é o Nexus
    que reiniciou no meio: "parada", com o que fazer (a peça que o Fracttal já tem é anotada no lote seguinte). `fim_txt`: a hora
    do fim, curta, em Brasília; `recente`: o fim há menos de `RESULTADO_H` (a tela mostra o resultado só então)."""
    almox = _id(id_almox)
    try:
        arq = _arquivo_lote(cfg, almox)
        from .gravacao import _ler_json
        ctrl = _ler_json(arq)
    except (F.Recusada, OSError):
        return None
    if not ctrl:
        return None
    est = dict(ctrl)
    th = _ANDANDO.get(almox)
    if est.get("estado") == "gravando" and not (th is not None and th.is_alive()):
        est.update(estado="parada", motivo=INTERROMPIDO, texto=f"O lote dos acordados parou: {INTERROMPIDO}.", tom="critico")
    try:
        fim = E.instante(est.get("fim") or est.get("atualizado_em"))
    except ValueError:
        fim = None
    est["fim_txt"] = fim.astimezone(_BRT).strftime("%d/%m às %H:%M") if fim else ""
    est["recente"] = bool(fim) and datetime.now(timezone.utc) - fim <= timedelta(hours=RESULTADO_H)
    return est


def aguardar_lote(id_almox: str, timeout: float = 30) -> None:
    """Espera o lote do botão deste almoxarifado terminar neste processo (os testes e as ferramentas)."""
    th = _ANDANDO.get(_id(id_almox))
    if th is not None:
        th.join(timeout)


# ── as telas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _volta(almox: str) -> str:
    return na_raiz("/t/pcm/pecas/inventario/regua" + ("?" + urlencode({"almox": almox}) if almox else ""))


def _do_form(f, prefixo: str):
    """O par (mínimo, máximo) de um formulário, ou None quando os dois campos vieram em branco (não mexeu)."""
    mn, mx = f.get(f"{prefixo}_min", ""), f.get(f"{prefixo}_max", "")
    return None if not str(mn).strip() and not str(mx).strip() else (mn, mx)


def _pagina(almox: str = "", *, erro: str = "", status: int = 200):
    from .. import almoxarifado
    cfg = current_app.config
    g = almoxarifado.montar()
    d = g.dados or {}
    ok_ = d.get("estado") == "ok"
    # a mesma lista do Por almoxarifado, com os que o saldo do ciclo não traz (11/11/2026): eles abrem sem peça nenhuma
    almoxes = [{"id": c["id"], "nome": c["nome"], "usina": c.get("usina"), "pecas": c["pecas"],
                "sem_saldo": bool(c.get("sem_saldo"))} for c in d.get("por_almoxarifado", [])] if ok_ else []
    escolhido = next((a for a in almoxes if a["id"] == almox), None) if almox else None
    linhas, erro_livro = [], ""
    if almox and escolhido is None and ok_:
        erro, status = erro or "Esse almoxarifado não está na varredura do App.", 404 if status == 200 else status
    lote = None
    if escolhido:
        try:
            ciclo = d.get("ciclo") or {}
            linhas = quadro(cfg, almox, varredura=[l for l in d["linhas"] if _id(l.get("id_almox")) == almox],
                            lida_depois_de=ciclo.get("fim_iso") or ciclo.get("inicio_iso"),
                            catalogo={_id(c.get("id")): c for c in d.get("catalogo", [])})
        except F.Recusada as ex:
            erro_livro = str(ex)
        # o lote do botão (a revisão de 11/11/2026): andando, a tela acompanha; parado, diz por quê; terminado há pouco, o
        # resultado na cor dele (o lote com falha não sai na caixa verde)
        lote = estado_do_lote(cfg, almox)
        if lote and lote["estado"] == "concluida" and not lote["recente"]:
            lote = None
    aviso = session.pop("pcm_regua_aviso", None) if status == 200 else None
    resp = render_template("pcm/inventario_regua.html", almoxes=almoxes, almox=escolhido, linhas=linhas, fmt=fmt, lote=lote,
                           pode=telas.pode_programar(), ok=aviso or "", erro=erro, erro_livro=erro_livro,
                           estado=d.get("estado", "sem_livro"), aviso_varredura=d.get("aviso", ""),
                           erro_fonte=g.erro or "")
    return resp, status


def registrar(bp) -> None:
    @bp.route("/pecas/inventario/regua", endpoint="inventario_regua")
    def regua_tela():
        return _pagina(_id(request.args.get("almox")))

    @bp.route("/pecas/inventario/regua/decidir", methods=["POST"], endpoint="inventario_regua_decidir")
    def regua_decidir():
        """Registra o recomendado e/ou o acordado de uma peça. Só administrador e setor PCM (`pode_programar`). A peça vem
        do saldo do almoxarifado, nunca do que a página trouxe. Só grava no livro do Nexus: o que vai ao Fracttal (gravar o
        acordado) roda na ponte `/os/_nexus/inventario/regua/gravar` (`ponte_os.py`), porque o login do Fracttal só chega em /os."""
        if not telas.pode_programar() or telas._de_outro_site():
            abort(403)
        f = request.form
        almox, item = _id(f.get("almox")), _id(f.get("item"))
        try:
            decidir(current_app.config, almox, item, recomendado=_do_form(f, "rec"), acordado=_do_form(f, "aco"),
                    pessoa=quem.do_pedido())
        except (ValueError, OSError) as ex:
            status, texto = erros.resposta(ex)
            return _pagina(almox, erro=texto, status=status)
        session["pcm_regua_aviso"] = ("Registrado. Só o acordado vai ao Fracttal: pelo Gravar no Fracttal, pelo botão de todos, ou "
                                      "sozinho no fim da próxima gravação de contagem deste almoxarifado.")
        return redirect(_volta(almox), code=303)

    @bp.route("/pecas/inventario/regua/lote.json", endpoint="inventario_regua_lote")
    def regua_lote():
        """O andamento do lote dos acordados do almoxarifado (a tela pergunta a cada 3 s enquanto ele anda). Não fala com o
        Fracttal: lê o controle do lote (`estado_do_lote`)."""
        from flask import jsonify
        e = estado_do_lote(current_app.config, _id(request.args.get("almox"))) or {"estado": "nenhum"}
        resp = jsonify({k: e.get(k) for k in ("estado", "a_mandar", "feitas", "gravadas", "iguais", "falhas", "nao_enviadas",
                                               "texto", "tom")})
        resp.headers["Cache-Control"] = "no-store"
        return resp
