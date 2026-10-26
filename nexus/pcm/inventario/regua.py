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
"""
from __future__ import annotations

import math
import re
import threading
import unicodedata
from urllib.parse import urlencode

from flask import abort, current_app, redirect, render_template, request, session

from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from ...prefixo import na_raiz
from .. import telas
from . import erros, quem
from . import estoque as E
from .erros import Conflito, NaoConfere

# a unidade que aceita casa decimal: METRO e MASSA (o `units_description` do Fracttal); a UNIDADE e o que não se sabe é inteira
UNIDADES_DECIMAIS = ("metro", "massa")
_AVARIADA = re.compile(r"-AV(?:-|\s|$)")
_TRAVA = threading.Lock()           # ler o retrato de antes e escrever o de agora é uma conta só (duas pessoas, uma peça)
_TOLERANCIA = 1e-9
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
def _nivel(v, o_que: str):
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
    mn, mx = _nivel(mn, f"{o_que}, mínimo"), _nivel(mx, f"{o_que}, máximo")
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


def quadro(cfg, id_almox: str, *, varredura: list[dict] | None = None) -> list[dict]:
    """Uma entrada por peça do almoxarifado: o saldo (o da última contagem gravada; sem ela, o da varredura), a sugestão, o
    recomendado e o acordado vigentes (a última decisão do `fato_regua_minimo`) e se o acordado já foi ao Fracttal.
    `varredura`: as linhas do saldo do almoxarifado no formato da tela do Almoxarifado; sem elas, as da varredura do App.
    Livro que não se lê levanta `Recusada` (nunca devolve vazio no lugar do que não leu)."""
    alvo = _id(id_almox)
    linhas = _da_varredura(alvo) if varredura is None else [l for l in varredura if _id(l.get("id_almox")) == alvo]
    livro = F.ler(cfg)
    vig, gravados = _vigentes(livro[F.ABA_REGUA]), _saldos_gravados(livro[F.ABA_EVENTO])
    return sorted((_montar(l, alvo, vig, gravados) for l in linhas), key=lambda x: (x["codigo"], x["id_item"]))


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
    with _TRAVA:
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


def _igual(lido, esperado) -> bool:
    return lido is not None and abs(lido - esperado) <= _TOLERANCIA


def gravar_acordado(cfg, id_almox: str, id_item: str, estoque: E.Estoque, pessoa: dict | None) -> str:
    """Manda ao Fracttal o mínimo e o máximo ACORDADOS (o recomendado nunca vai), relê e só então anota o evento
    `regua_gravada` e o retrato `gravado_fracttal`. Devolve o texto para a tela. O Fracttal que o chamador passa é o da
    sessão de quem aprovou (`estoque_da_sessao`).

    `Conflito` quando a peça não tem acordado registrado ou não está ligada ao almoxarifado (nada foi enviado); `NaoConfere`
    quando o Fracttal respondeu e a releitura não bateu (anota um `erro`, nunca o `regua_gravada`); `Limite`, `SemLogin` e
    `ErroFracttal` sobem como são. Idempotente: gravar o mesmo par duas vezes dá o mesmo resultado."""
    almox, item = _id(id_almox), _id(id_item)
    with _TRAVA:
        v = _vigentes(F.ler(cfg, forcar=True)[F.ABA_REGUA]).get((almox, item))
        if not v or v["acordado"] in ((None, None), None):
            raise Conflito("Esta peça ainda não tem o mínimo e o máximo ACORDADOS registrados: nada foi enviado ao Fracttal "
                           "(só o acordado vai; o recomendado fica no Nexus).")
        mn, mx = v["acordado"]
        quem_ = quem.colunas(cfg, pessoa)
        peca = estoque.ler(almox).get(item)            # a leitura também guarda a ligação que o `definir_regua` usa
        if peca is None:
            raise Conflito(f"A peça {v['codigo'] or item} não está ligada ao almoxarifado {almox} no Fracttal: a régua é do "
                           "vínculo dela com o almoxarifado (a gravação da contagem a liga). Nada foi enviado.")
        estoque.definir_regua(almox, item, mn, mx)
        depois = estoque.ler(almox).get(item) or {}
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
    almoxes = [{"id": c["id"], "nome": c["nome"], "usina": c.get("usina"), "pecas": c["pecas"]}
               for c in d.get("por_almoxarifado", [])] if ok_ else []
    escolhido = next((a for a in almoxes if a["id"] == almox), None) if almox else None
    linhas, erro_livro = [], ""
    if almox and escolhido is None and ok_:
        erro, status = erro or "Esse almoxarifado não está na varredura do App.", 404 if status == 200 else status
    if escolhido:
        try:
            linhas = quadro(cfg, almox, varredura=[l for l in d["linhas"] if _id(l.get("id_almox")) == almox])
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
        except ValueError as ex:
            status, texto = erros.resposta(ex)
            return _pagina(almox, erro=texto, status=status)
        session["pcm_regua_aviso"] = "Registrado. Só o acordado vai ao Fracttal, quando você mandar gravar."
        return redirect(_volta(almox), code=303)
