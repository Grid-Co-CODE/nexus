"""Comando › Contestações e Comando › Prévia: visão do contrato, vindas da torre Contratos e clientes em 12/11/2026.

Levi, 12/11/2026: "Outro ponto, contratos e clientes. Joga o acesso cliente lá para bases, contestações, você vai jogar
para o comando, prévia visão do contrato, você vai jogar no comando [...] Essa parte de contrato e clientes aqui vai
sumir, vai ser absorvido por outras seções". As regras não mudaram de lugar: `nexus/contratos/contestacoes.py`,
`tratamento.py` e o `nexus/contratos/CLAUDE.md`. Os endereços antigos (`/t/contratos/...`) levam aos novos
(`nexus/torres/contratos/__init__.py`), e a marca que o setor tinha na tela antiga vale para a nova
(`setor_telas.RENOMEADAS`).

Fica num módulo à parte, importado no fim do `__init__` da torre (como as demandas): usa o `bp` e a `TORRE` de lá.
"""
import logging
import unicodedata

from flask import abort, redirect, render_template, request, session

from ...contratos import contestacoes as CT
from ...contratos import tratamento as TR
from ...prefixo import na_raiz
from ...auth.origem import de_outro_site as _de_outro_site
from . import TORRE, bp

_log = logging.getLogger(__name__)
CONTESTACOES = "/t/comando/contestacoes"
_AVISO, _ERRO = "contestacoes_aviso", "contestacoes_erro"


def _sem_acento(txt) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(txt or "")) if unicodedata.category(c) != "Mn").strip().lower()


def _setores_visiveis() -> tuple:
    """Os setores de contestação que a sessão vê (Levi, 15/10/2026: "O setor só vê a contestação do próprio setor, exceto
    administrador"). Administrador: todos. Quem tem setor: só o de mesmo nome (os setores do Nexus se chamam
    Performance, COS e Zeladoria, como os das contestações); outro setor, nenhum. Portão por setor desligado
    (NEXUS_ACESSO_POR_SETOR=0, testes): todos, como antes."""
    if session.get("admin"):
        return tuple(s for s, _ in CT.SETORES)
    from ...auth import setor_telas as ST
    a = ST.acesso()
    if a.get("setor"):
        nome = _sem_acento(a["setor"].get("nome"))
        return tuple(s for s, _ in CT.SETORES if s == nome)
    return tuple(s for s, _ in CT.SETORES) if a.get("tudo") else ()


def _achar(linha_id: str):
    """(a contestação, as visíveis) — a linha só se é de um setor que a sessão vê; senão 404 (nem diz que existe)."""
    d = CT.contestacoes()
    vis = _setores_visiveis()
    for s in vis:
        for x in d["por_setor"].get(s) or []:
            if str(x["id"]) == str(linha_id):
                return x, d
    abort(404)


def _quando_txt(dias) -> str:
    if dias is None:
        return ""
    return "hoje" if dias <= 0 else ("ontem" if dias == 1 else f"há {dias} dias")


def _com_acompanhamento(lista: list[dict], trat: dict, hoje) -> list[dict]:
    """Cada contestação com o acompanhamento dela (`t`: a situação, os eventos, a última atualização), o rótulo e o tom da
    situação e há quantos dias chegou."""
    out = []
    for x in lista:
        t = trat.get(str(x["id"])) or TR.VAZIO
        rot, tom = TR.SITUACOES[t["situacao"]]
        dias = (hoje - x["quando"].date()).days if x["quando"] else None
        out.append(dict(x, t=t, sit_rot=rot, sit_tom=tom, dias=dias, chegou_txt=_quando_txt(dias)))
    return out


def _endereco(setor, ver, c=None) -> str:
    """O endereço da fila (sem o prefixo: o template passa pelo |na_raiz, o redirect pelo na_raiz)."""
    from urllib.parse import urlencode
    q = {"setor": setor}
    if ver == "resolvidas":
        q["ver"] = ver
    if c:
        q["c"] = c
    return CONTESTACOES + "?" + urlencode(q)


@bp.route("/contestacoes")
def contestacoes():
    """A fila das contestações do setor (o redesenho de 16/11/2026, Levi: "quero um rebranding! Tire esse 'Pegar pra
    mim' qualquer um daquele setor pode editar e salvar por tanto que salve quem foi que fez isso! deixe mais
    utilizável"): uma aba por setor que a sessão vê, os números do alto (sem resposta, em andamento, resolvidas, a mais
    antiga sem resposta), a lista das abertas (ou das resolvidas) à esquerda, a sem resposta primeiro, e a contestação
    escolhida à direita, com o que o cliente disse, o que ele via, o acompanhamento e o campo de escrever, para quem é do
    setor. Nome, contato e mensagem só com a chave privada deste Nexus."""
    from datetime import datetime
    d = CT.contestacoes()
    vis = _setores_visiveis()
    setores = [(s, rot) for s, rot in CT.SETORES if s in vis]
    try:
        trat, trat_erro = TR.estado(), None
    except Exception as e:      # noqa: BLE001 — sem o livro do acompanhamento, a lista segue sem a situação
        trat, trat_erro = {}, f"Não consegui ler o acompanhamento ({type(e).__name__})"
    hoje = datetime.now(CT._BRT).date()
    # a escolhida pelo endereço (o aviso do topo leva a ela): a aba é a do setor dela, entre os que a sessão vê
    c = str(request.args.get("c") or "")
    setor = request.args.get("setor") if request.args.get("setor") in vis else None
    if c:
        setor = next((s for s in vis for x in d["por_setor"].get(s) or [] if str(x["id"]) == c), setor)
    setor = setor or (setores[0][0] if setores else None)
    todas = _com_acompanhamento((d["por_setor"].get(setor) or []) if setor else [], trat, hoje)
    abertas = [x for x in todas if x["t"]["situacao"] != "resolvida"]
    # a sem resposta primeiro (é o que pede alguém), cada grupo com a mais nova em cima (a ordem de `todas`)
    abertas.sort(key=lambda x: x["t"]["situacao"] != "sem_resposta")
    resolvidas = [x for x in todas if x["t"]["situacao"] == "resolvida"]
    ver = "resolvidas" if request.args.get("ver") == "resolvidas" else "abertas"
    lista = resolvidas if ver == "resolvidas" else abertas
    sel = next((x for x in todas if str(x["id"]) == c), None)
    auto = sel is None
    sel = sel or (lista[0] if lista else None)
    sem = [x for x in todas if x["t"]["situacao"] == "sem_resposta"]
    numeros = {"sem_resposta": len(sem), "em_andamento": sum(1 for x in todas if x["t"]["situacao"] == "em_andamento"),
               "resolvidas": len(resolvidas), "mais_antiga": max(sem, key=lambda x: x["dias"] or 0) if sem else None}
    abertas_de = {s: sum(1 for x in d["por_setor"].get(s) or []
                         if (trat.get(str(x["id"])) or TR.VAZIO)["situacao"] != "resolvida") for s, _ in setores}
    from ...auth import setor_telas as ST
    meu_setor = (ST.acesso().get("setor") or {}).get("nome") if not session.get("admin") else None
    return render_template("comando/contestacoes.html", torre=TORRE, tela=TORRE.tela("contestacoes"), d=d,
                           setores=setores, setor=setor, setor_rot=dict(CT.SETORES).get(setor, setor), lista=lista,
                           ver=ver, sel=sel, auto=auto, numeros=numeros, abertas_de=abertas_de, trat_erro=trat_erro,
                           n_abertas=len(abertas), meu_setor=meu_setor, endereco=_endereco,
                           card=_contexto_card(sel, trat_erro) if sel else None,
                           aviso=session.pop(_AVISO, None), erro=session.pop(_ERRO, None))


def _eu() -> str:
    u = session.get("usuario") or {}
    return " ".join(str(u.get("nome") or "").split()) or str(u.get("email") or "")


def _contexto_card(x, lido=None) -> dict:
    """O que o card da contestação precisa: ela com o acompanhamento, quem está escrevendo e se pode escrever."""
    return {"x": x, "t": x["t"], "lido": lido, "eu": _eu(), "com_login": bool(TR.codigo(session.get("usuario"))),
            "setor_rot": dict(CT.SETORES).get(x["setor"], x["setor"]), "admin": bool(session.get("admin"))}


def _card(x):
    from datetime import datetime
    try:
        trat, lido = TR.estado(), None
    except Exception as e:      # noqa: BLE001 — banco fora: o card diz, sem um "nenhuma atualização" falso
        trat, lido = {}, f"Não consegui ler o acompanhamento ({type(e).__name__})"
    x = _com_acompanhamento([x], trat, datetime.now(CT._BRT).date())[0]
    return render_template("comando/_contestacao_card.html", **_contexto_card(x, lido))


@bp.route("/contestacoes/<linha_id>/card")
def contestacao_card(linha_id):
    """O card da contestação (o pedaço de página do lado direito): a lista troca o card sem reler a página."""
    x, _ = _achar(linha_id)
    return _card(x)


def _gravar(linha_id, acao, ok):
    """As três ações do card (escrever, resolver, reabrir): POST só da própria página, da contestação que a sessão vê. Com
    o JavaScript da página (o cabeçalho X-Nexus-Parte), a resposta é JSON e o texto digitado fica no campo quando não
    grava; sem ele, volta à lista com o aviso."""
    if _de_outro_site():
        abort(403)
    x, _ = _achar(linha_id)
    parte = bool(request.headers.get("X-Nexus-Parte"))
    ver = "resolvidas" if request.form.get("ver") == "resolvidas" else "abertas"
    try:
        acao(x)
        erro = None
    except TR.Recusada as e:
        erro = str(e)
    except Exception as e:      # noqa: BLE001 — banco fora: nada mudou, a tela diz
        _log.exception("Contestações: a gravação da contestação %s não foi", linha_id)
        erro = f"Não consegui gravar no banco ({type(e).__name__}). Nada mudou; tente de novo em instantes."
    if parte:
        from flask import jsonify
        if erro:
            return jsonify({"ok": False, "erro": erro}), 409
        session[_AVISO] = ok              # a página relê na contestação e diz o que gravou
        return jsonify({"ok": True, "aviso": ok})
    session[_ERRO if erro else _AVISO] = erro or ok
    return redirect(na_raiz(_endereco(x["setor"], ver, x["id"])) + "#ct-detalhe", code=303)


@bp.route("/contestacoes/<linha_id>/atualizacao", methods=["POST"])
def contestacao_atualizar(linha_id):
    """Grava a atualização de quem está na sessão (qualquer um do setor, 16/11/2026), com a data e a hora."""
    return _gravar(linha_id, lambda x: TR.atualizar(x["id"], x["setor"], session.get("usuario"),
                                                    request.form.get("texto") or ""), "Atualização salva")


@bp.route("/contestacoes/<linha_id>/resolver", methods=["POST"])
def contestacao_resolver(linha_id):
    return _gravar(linha_id, lambda x: TR.resolver(x["id"], x["setor"], session.get("usuario")),
                   "Contestação marcada como resolvida")


@bp.route("/contestacoes/<linha_id>/reabrir", methods=["POST"])
def contestacao_reabrir(linha_id):
    return _gravar(linha_id, lambda x: TR.reabrir(x["id"], x["setor"], session.get("usuario")), "Contestação reaberta")


@bp.route("/contestacoes/<linha_id>/pegar", methods=["POST"])
def contestacao_pegar(linha_id):
    """O "Pegar para mim" saiu em 16/11/2026 (Levi: "Tire esse 'Pegar pra mim'"): a aba aberta de antes que ainda o
    aperta volta à contestação, sem gravar nada, para escrever direto."""
    if _de_outro_site():
        abort(403)
    x, _ = _achar(linha_id)
    session[_AVISO] = "Não precisa mais pegar a contestação: qualquer pessoa do setor escreve a atualização."
    return redirect(na_raiz(_endereco(x["setor"], "abertas", x["id"])) + "#ct-detalhe", code=303)


@bp.route("/visao-do-contrato")
def visao_do_contrato():
    """Comando › Prévia: visão do contrato (12/11/2026): o mockup (static/previa/visao-do-contrato.html) numa moldura,
    para Contratos e os setores avaliarem. Desde 16/11/2026, com a planilha de controle de obrigações importada, a página
    mostra os contratos de verdade (`nexus/contratos/controle.py`); sem ela, o exemplo fictício."""
    real = _controle_lido()
    return render_template("comando/visao_do_contrato.html", torre=TORRE, tela=TORRE.tela("visao-do-contrato"),
                           real=real, admin=bool(session.get("admin")),
                           aviso=session.pop(_AVISO_CT, None), erro=session.pop(_ERRO_CT, None))


# ── a planilha de controle de obrigações (16/11/2026) ─────────────────────────────────────────────────────────────────
# Retorno do supervisor de contratos na prévia: "Só não encontrei algum setor que fale sobre renovação contratual e/ou
# ajuste contratual de 12 meses. Essas datas são importantes para a gestão de contratos"; Levi: "ATUALIZE AGORA COM DADOS
# REAIS!". A planilha da área (Backoffice › 2. Contratos) é importada aqui e fica na pasta de dados do servidor: o
# repositório é público e a planilha tem nomes, valores e cláusulas. A leitura é só para quem está logado e não é cliente.
_AVISO_CT, _ERRO_CT = "contrato_aviso", "contrato_erro"
VISAO = "/t/comando/visao-do-contrato"


def _caminho_controle():
    from flask import current_app

    from ...cadastro.ligacoes import pasta_dados
    from ...contratos import controle as K
    return pasta_dados(current_app.config) / "contratos" / K.ARQUIVO


def _controle_lido() -> dict | None:
    """O que foi importado ({arquivo, importado_em, importado_por, contratos, obrigacoes}) ou None."""
    import json
    try:
        p = _caminho_controle()
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:            # noqa: BLE001 — arquivo estragado: a tela volta ao exemplo, e o log diz
        _log.exception("Visão do contrato: não li o controle de obrigações importado")
        return None


def _so_interno():
    from ...auth import setor_telas as ST
    if session.get("via") == "cliente" or ST.em_modo_cliente():
        abort(403)


@bp.route("/visao-do-contrato/dados.json")
def visao_do_contrato_dados():
    """Os contratos e as obrigações importados, com as contas de hoje (`controle.com_datas`), para a página da prévia.
    Sem importação: {"ok": false}, e a página fica no exemplo."""
    from flask import jsonify

    from ...campo import visao
    from ...contratos import controle as K
    _so_interno()
    d = _controle_lido()
    if not d:
        resp = jsonify(ok=False)
    else:
        resp = jsonify(ok=True, **K.com_datas(d, visao._agora().date()))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/visao-do-contrato/importar", methods=["POST"])
def visao_do_contrato_importar():
    """O administrador sobe a planilha de controle de obrigações (.xlsx); o Nexus confere as abas e as colunas, lê e
    guarda o resultado na pasta de dados. A planilha errada não apaga a que estava."""
    import json
    import os

    from ...campo import visao
    from ...contratos import controle as K
    if _de_outro_site():
        abort(403)
    if not session.get("admin"):
        abort(403)
    f = request.files.get("planilha")
    if not f or not f.filename:
        session[_ERRO_CT] = "Escolha a planilha de controle de obrigações (.xlsx)."
        return redirect(na_raiz(VISAO))
    conteudo = f.read()
    if len(conteudo) > 20 * 1024 * 1024:
        session[_ERRO_CT] = "A planilha passa de 20 MB: não é a de controle de obrigações."
        return redirect(na_raiz(VISAO))
    try:
        d = K.ler_planilha(conteudo, os.path.basename(f.filename))
    except K.PlanilhaInvalida as ex:
        session[_ERRO_CT] = f"Não importei: {ex}. A que estava continua."
        return redirect(na_raiz(VISAO))
    u = session.get("usuario")
    d.update(importado_em=visao._agora().strftime("%Y-%m-%dT%H:%M"),
             importado_por=(u.get("nome") or u.get("email") or "") if isinstance(u, dict) else "")
    p = _caminho_controle()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    session[_AVISO_CT] = (f"Planilha importada: {len(d['contratos'])} contratos, {len(d['obrigacoes'])} obrigações e "
                          f"{len(d.get('adicionais') or [])} serviços adicionais. A visão do contrato já mostra os dados dela.")
    return redirect(na_raiz(VISAO))
