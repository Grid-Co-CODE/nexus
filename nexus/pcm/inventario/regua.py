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


def _saldos_gravados(eventos: list[dict]) -> dict:
    """{(almoxarifado, peça): o saldo da última contagem GRAVADA}: o `para_qtd` do evento `peca_gravada` mais novo. O
    conflito e o erro não são saldo gravado."""
    ultimo: dict = {}
    for i, e in enumerate(eventos):
        if A._txt(e.get("tipo")) != "peca_gravada" or _num(e.get("para_qtd")) is None:
            continue
        k = (_id(e.get("id_almoxarifado")), _id(e.get("id_item")))
        marca = (A._txt(e.get("quando")), i)
        if k not in ultimo or marca >= ultimo[k][0]:
            ultimo[k] = (marca, _num(e.get("para_qtd")))
    return {k: v for k, (_, v) in ultimo.items()}


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
    except (F.Recusada, ValueError):
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


def quadro(cfg, id_almox: str, *, varredura: list[dict] | None = None, lida_depois_de: str | None = None) -> list[dict]:
    """Uma entrada por peça do almoxarifado: o saldo (o da última contagem gravada; sem ela, o da varredura), a sugestão, o
    recomendado e o acordado vigentes (a última decisão do `fato_regua_minimo`) e se o acordado já foi ao Fracttal.
    `varredura`: as linhas do saldo do almoxarifado no formato da tela do Almoxarifado; sem elas, as da varredura do App.
    Livro que não se lê levanta `Recusada` (nunca devolve vazio no lugar do que não leu).

    `agora_min`, `agora_max` e `agora_em` (11/11/2026): o que o Fracttal tinha na última releitura do Nexus (`lida`), quando ela é
    mais nova que a varredura que a tela mostra (`lida_depois_de`, o fim do ciclo do App; sem ele, não se sabe qual é a mais
    nova, e vale a varredura): "no Fracttal agora", sem esperar o ciclo seguinte do App. Sem releitura mais nova, `agora_em`
    vazio, e a coluna é a da varredura (só o mínimo: o App não traz o máximo)."""
    alvo = _id(id_almox)
    linhas = _da_varredura(alvo) if varredura is None else [l for l in varredura if _id(l.get("id_almox")) == alvo]
    livro = F.ler(cfg)
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
def _linha_da_peca(almox: str, item: str, varredura) -> dict:
    """A peça de um almoxarifado, pelo saldo dele: o ID que a página mandou só vale se a peça é daquele almoxarifado."""
    for l in (_da_varredura(almox) if varredura is None else varredura):
        if _id(l.get("id_almox")) == almox and _id(l.get("id_item")) == item:
            return l
    raise ValueError(f"A peça {item} não está no saldo do almoxarifado {almox} (a varredura do App ainda não a leu?): "
                     "nada foi registrado.")


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
    l = _linha_da_peca(almox, item, varredura)
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


def _texto_do_lote(r: dict, prefixo: str = "Acordados deste almoxarifado") -> str:
    """O que a tela (o aviso depois do botão; a etapa Gravação da contagem, com o `prefixo` "Régua acordada") diz do lote."""
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


def gravar_acordados(cfg, id_almox: str, estoque: E.Estoque, quem_: dict, *, contagem_id: str | None = None, dormir=None,
                     agora=None, ao_andar=None) -> dict:
    """Manda ao Fracttal a régua ACORDADA de cada peça do almoxarifado cujo acordado difere do que o Fracttal tem (o recomendado e
    a sugestão nunca vão; a peça sem acordado não muda), relê e só então anota: o evento `regua_gravada` (o mínimo de -> para) e o
    retrato `gravado_fracttal`, como `gravar_acordado`, mas de uma leitura, um pedido por peça mandada e uma releitura por lote de
    `LOTE_REGUA` (o livro também é escrito uma vez por lote, e não duas vezes por peça). O estoque é o do login de quem gravou
    (o botão da régua, ou a sessão do Fracttal da gravação da contagem que acabou, `gravacao`); `quem_` as colunas da pessoa
    (`quem.colunas`, ou o aprovador da gravação); `contagem_id`, a contagem cuja gravação puxou o lote (vai nos eventos: a
    Auditoria da contagem os mostra).

    A peça que o Fracttal já tem igual não gasta pedido, e passa a "gravado no Fracttal" se o retrato ainda não dizia (é o que
    ele tem). A falha de uma peça é registrada (um evento `erro`, com o porquê cifrado e só texto do Nexus) e não para as
    outras: o `success: false` (`Recusado`) não gravou; a resposta perdida (rede) talvez gravou, e a releitura decide. O 429
    espera 62 s e tenta UMA vez; de novo, o lote para e o resto não vai (o texto diz quantas). O login que expira também para.
    A releitura que não veio deixa as mandadas sem anotação de gravada (o livro nunca diz que o Fracttal tem o que não tem). O
    acordado que outra pessoa registrou enquanto o lote estava no Fracttal não vira "gravado" (o retrato é escrito sob a trava
    da peça, conferindo o registrado de agora). Um lote de cada vez por almoxarifado (`Conflito`).

    `Limite`, `SemLogin` e `ErroFracttal` da PRIMEIRA leitura sobem (nada foi mandado); o resto vira o resumo: `{"total", "a_mandar",
    "feitas", "gravadas", "iguais", "falhas", "sem_ligacao", "incompletas", "nao_enviadas", "parou", "sem_livro", "lido_em",
    "texto"}`. `ao_andar(resumo)` a cada peça mandada (a etapa Gravação mostra o andamento)."""
    dormir, agora = dormir or time.sleep, agora or (lambda: datetime.now(timezone.utc))
    almox = _id(id_almox)
    trava = _LOTE.de(almox)
    if not trava.acquire(blocking=False):
        raise Conflito("Já tem um lote de acordados indo ao Fracttal neste almoxarifado: espere ele terminar. Nada foi enviado.")
    try:
        return _gravar_acordados(cfg, almox, estoque, quem_, contagem_id, dormir, agora, ao_andar)
    finally:
        trava.release()


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

    eventos, ficam_gravados, a_mandar = [], [], []           # ficam_gravados: (peça, o acordado que o Fracttal tem)
    for item, v in sorted(acordados.items()):
        mn, mx = v["acordado"]
        peca = antes.get(item)
        if mn is None or mx is None:
            r["incompletas"] += 1                  # uma linha do livro com só um dos números: os dois vão ao Fracttal
        elif peca is None:
            r["sem_ligacao"] += 1                  # a régua é do vínculo da peça com o almoxarifado: a gravação liga
        elif _igual(peca.get("minimo"), mn) and _igual(peca.get("maximo"), mx):
            r["iguais"] += 1
            if not v["gravado"]:
                ficam_gravados.append((item, v["acordado"]))
        elif any(isinstance(n, float) and not n.is_integer() for n in (mn, mx)) and not decimal(peca.get("unidade")):
            r["falhas"] += 1
            eventos.append(erro(item, v, peca, "o acordado tem casa decimal e a unidade da peça no Fracttal é inteira"))
        else:
            a_mandar.append((item, v, peca))
    r["a_mandar"] = len(a_mandar)
    for k in range(0, max(len(a_mandar), 1), LOTE_REGUA):
        enviadas = []
        for item, v, peca in a_mandar[k:k + LOTE_REGUA]:
            if r["parou"]:
                r["nao_enviadas"] += 1
                continue
            try:
                with _PECA.de((almox, item)):      # a gravação de uma peça só, ao mesmo tempo, espera
                    chamar(estoque.definir_regua, almox, item, *v["acordado"])
                enviadas.append((item, v, peca, ""))
            except _LimiteDeNovo:
                r["parou"], r["nao_enviadas"] = LIMITE, r["nao_enviadas"] + 1      # o 429 não executa nada
            except E.SemLogin:
                r["parou"], r["nao_enviadas"] = LOGIN, r["nao_enviadas"] + 1
            except (E.Recusado, ValueError) as ex:   # o "não" com todas as letras, ou o pedido que nem saiu: nada foi gravado
                r["falhas"] += 1
                eventos.append(erro(item, v, peca, f"o Fracttal recusou a régua ({type(ex).__name__})"))
            except Exception as ex:                # noqa: BLE001 — a resposta que não veio: talvez gravou, a releitura decide
                enviadas.append((item, v, peca, type(ex).__name__))
            r["feitas"] += 1
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
        eventos, ficam_gravados = [], []
    guardar_lida(cfg, almox, lido, lido_em)
    r["lido_em"] = E.instante(lido_em).isoformat()
    return dict(r, texto=_texto_do_lote(r))


def _registrar_lote(cfg, almox, eventos, ficam_gravados, quem_) -> str:
    """Escreve os eventos e os retratos `gravado_fracttal` de um lote, o evento primeiro (como `gravar_acordado`: o retrato que
    falhar deixa a peça "não gravada", e gravar de novo é o mesmo número). O retrato só sai se o acordado registrado AGORA é o que
    o Fracttal tem, conferido sob a trava de cada peça (ninguém registra outro acordado dela entre a conferência e a escrita). ""
    se gravou; senão o porquê (o Fracttal já recebeu: o texto manda gravar de novo)."""
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
            F.acrescentar(cfg, F.ABA_EVENTO, eventos)
        if linhas:
            F.acrescentar(cfg, F.ABA_REGUA, linhas)
        return ""
    except (F.Recusada, OSError) as ex:
        logging.warning("régua: o lote do almoxarifado %s não entrou no livro (%s)", almox, type(ex).__name__)
        return str(ex) if isinstance(ex, F.Recusada) else type(ex).__name__
    finally:
        for tr in reversed(travas):
            tr.release()


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
    if escolhido:
        try:
            ciclo = d.get("ciclo") or {}
            linhas = quadro(cfg, almox, varredura=[l for l in d["linhas"] if _id(l.get("id_almox")) == almox],
                            lida_depois_de=ciclo.get("fim_iso") or ciclo.get("inicio_iso"))
        except F.Recusada as ex:
            erro_livro = str(ex)
    aviso = session.pop("pcm_regua_aviso", None) if status == 200 else None
    resp = render_template("pcm/inventario_regua.html", almoxes=almoxes, almox=escolhido, linhas=linhas, fmt=fmt,
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
        session["pcm_regua_aviso"] = "Registrado. Só o acordado vai ao Fracttal, quando você mandar gravar."
        return redirect(_volta(almox), code=303)
