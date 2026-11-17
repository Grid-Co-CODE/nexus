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


@bp.route("/contestacoes")
def contestacoes():
    """Uma aba por setor que a sessão vê (Performance, COS, Zeladoria), a contestação mais nova em cima: quando chegou, a
    usina, o dia contestado, o que o cliente contestou, quem é e como responder, a mensagem e o que ele via na tela
    naquele dia, se o Teams do setor recebeu o aviso e quem é o responsável (ou o "Pegar para mim"). A linha abre o card
    das atualizações. Nome, contato e mensagem só com a chave privada deste Nexus."""
    d = CT.contestacoes()
    vis = _setores_visiveis()
    setores = [(s, rot) for s, rot in CT.SETORES if s in vis]
    setor = request.args.get("setor") if request.args.get("setor") in vis else (setores[0][0] if setores else None)
    try:
        trat, trat_erro = TR.estado(), None
    except Exception as e:      # noqa: BLE001 — sem o livro do acompanhamento, a lista segue sem os responsáveis
        trat, trat_erro = {}, f"Não consegui ler o acompanhamento ({type(e).__name__})"
    lista = (d["por_setor"].get(setor) or []) if setor else []
    from ...auth import setor_telas as ST
    meu_setor = (ST.acesso().get("setor") or {}).get("nome") if not session.get("admin") else None
    return render_template("comando/contestacoes.html", torre=TORRE, tela=TORRE.tela("contestacoes"), d=d,
                           setores=setores, setor=setor, lista=lista, trat=trat, trat_erro=trat_erro,
                           meu=TR.codigo(session.get("usuario")), admin=bool(session.get("admin")), meu_setor=meu_setor,
                           aviso=session.pop(_AVISO, None), erro=session.pop(_ERRO, None))


@bp.route("/contestacoes/<linha_id>/pegar", methods=["POST"])
def contestacao_pegar(linha_id):
    """'Pegar para mim': a pessoa do login vira a responsável pela demanda e volta à lista do setor."""
    if _de_outro_site():
        abort(403)
    x, _ = _achar(linha_id)
    try:
        TR.pegar(x["id"], x["setor"], session.get("usuario"), bool(session.get("admin")))
        session[_AVISO] = f"A contestação de {x['usina']} agora é sua."
    except TR.Recusada as e:
        session[_ERRO] = str(e)
    except Exception as e:      # noqa: BLE001 — banco fora: a tela diz, nada mudou
        _log.exception("Contestações: pegar a demanda %s não gravou", linha_id)
        session[_ERRO] = f"Não consegui gravar no banco ({type(e).__name__}). Nada mudou; tente de novo em instantes."
    return redirect(na_raiz(f"{CONTESTACOES}?setor={x['setor']}"), code=303)


def _card(x, aviso="", erro="", texto=""):
    try:
        t = TR.estado().get(str(x["id"])) or {"responsavel": None, "atualizacoes": []}
        lido = None
    except Exception as e:      # noqa: BLE001 — banco fora: o card diz, sem um "nenhuma atualização" falso
        t, lido = {"responsavel": None, "atualizacoes": []}, f"Não consegui ler o acompanhamento ({type(e).__name__})"
    meu = TR.codigo(session.get("usuario"))
    resp = t["responsavel"]
    return render_template("comando/_contestacao_card.html", x=x, t=t, resp=resp, lido=lido,
                           sou_resp=bool(resp and meu and resp["hmac"] == meu), admin=bool(session.get("admin")),
                           com_login=bool(meu), aviso=aviso, erro=erro, texto=texto,
                           setor_rot=dict(CT.SETORES).get(x["setor"], x["setor"]))


@bp.route("/contestacoes/<linha_id>/card")
def contestacao_card(linha_id):
    """O card por cima da lista (o pedaço de página que o <dialog> mostra): a contestação, o responsável e as
    atualizações com a data e a hora; o campo de escrever só para o responsável."""
    x, _ = _achar(linha_id)
    return _card(x)


@bp.route("/contestacoes/<linha_id>/atualizacao", methods=["POST"])
def contestacao_atualizar(linha_id):
    """Grava a atualização do responsável e devolve o card de novo (com a nova, ou com o motivo e o texto digitado)."""
    if _de_outro_site():
        abort(403)
    x, _ = _achar(linha_id)
    texto = request.form.get("texto") or ""
    try:
        TR.atualizar(x["id"], x["setor"], session.get("usuario"), texto)
    except TR.Recusada as e:
        return _card(x, erro=str(e), texto=texto)
    except Exception as e:      # noqa: BLE001 — banco fora: o texto digitado não se perde
        _log.exception("Contestações: a atualização da demanda %s não gravou", linha_id)
        return _card(x, erro=f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo em instantes.",
                     texto=texto)
    return _card(x, aviso="Atualização salva")


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
    session[_AVISO_CT] = (f"Planilha importada: {len(d['contratos'])} contratos e {len(d['obrigacoes'])} obrigações. "
                          "A visão do contrato já mostra os dados dela.")
    return redirect(na_raiz(VISAO))
