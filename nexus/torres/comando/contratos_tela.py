"""Comando › Contratos (18/11/2026): a visão do contrato, editável e com histórico.

Era a "Prévia: visão do contrato" (12/11/2026), um mockup numa moldura que passou a mostrar a planilha de controle de
obrigações (16/11/2026) e as fichas lidas dos PDFs dos contratos (18/11/2026), ambas subidas por campos de importação. Levi,
18/11/2026: "Tire essas opções de subir arquivos [...] Eu quero que essas informações sejam editáveis [...] Só gestores de
contrato ou administradores podem editar, e tudo com histórico" e "deixar muita informação em cima [...] rouba metade do
espaço da tela [...] Arrume isso". Virou página do Nexus (sem moldura, sem o cabeçalho dobrado), com o nome Contratos; o
que foi importado é a carga inicial, e daí em diante tudo muda aqui (`nexus/contratos/edicao.py`).

Leitura só para quem está logado e não é cliente; edição só do gestor do contrato ou do administrador (a regra mora em
`edicao.pode_editar`, e a página só mostra o lápis para quem pode). O endereço antigo leva ao novo.
"""
import json
import logging

from flask import abort, jsonify, redirect, render_template, request, send_file, session

from ...auth.origem import de_outro_site as _de_outro_site
from ...contratos import edicao as E
from ...prefixo import na_raiz
from . import TORRE, bp

_log = logging.getLogger(__name__)
CONTRATOS = "/t/comando/contratos"


def _pasta_contratos():
    from flask import current_app

    from ...cadastro.ligacoes import pasta_dados
    return pasta_dados(current_app.config) / "contratos"


def _json_da_pasta(nome: str) -> dict | None:
    """Um dos dois arquivos da carga inicial (a planilha de 16/11 e as fichas de 18/11), ou None."""
    try:
        p = _pasta_contratos() / nome
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:            # noqa: BLE001 — arquivo estragado: a tela segue sem ele, e o log diz
        _log.exception("Contratos: não li %s", nome)
        return None


def _base() -> dict:
    from ...contratos import controle as K
    from ...contratos import fichas as F
    return E.carga(_json_da_pasta(K.ARQUIVO), _json_da_pasta(F.ARQUIVO))


def _so_interno():
    from ...auth import setor_telas as ST
    if session.get("via") == "cliente" or ST.em_modo_cliente():
        abort(403)


def _usuario() -> dict:
    u = session.get("usuario")
    return u if isinstance(u, dict) else {}


def _meu_hmac() -> str | None:
    from flask import current_app

    from ...cadastro.ligacao_campo import codigo_da_pessoa
    email = str(_usuario().get("email") or "").strip().lower()
    return codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) if email else None


def _pessoas() -> list[dict]:
    """[{hmac, nome}] das pessoas com setor (a lista das Demandas): é dela que sai o gestor de cada contrato. Fora do ar,
    vazio: ninguém fica gestor pelo nome, e só o administrador edita até voltar."""
    try:
        from ...comando import demandas as D
        return [{"hmac": p["hmac"], "nome": p["nome"]} for p in D.pessoas_com_setor()]
    except Exception:            # noqa: BLE001
        _log.warning("Contratos: a lista de pessoas não veio; só o administrador edita agora")
        return []


@bp.route("/contratos")
def contratos():
    """A página: o JavaScript pede o dados.json e desenha. Sem a carga inicial no servidor, a página diz isso."""
    _so_interno()
    from ...contratos import controle as K
    try:
        tem = (_pasta_contratos() / K.ARQUIVO).exists()
    except Exception:            # noqa: BLE001 — sem a pasta de dados (o teste sem NEXUS_DADOS): a página diz que não chegou
        tem = False
    return render_template("comando/contratos.html", torre=TORRE, tela=TORRE.tela("contratos"), tem_carga=tem)


@bp.route("/visao-do-contrato", defaults={"resto": ""})
@bp.route("/visao-do-contrato/<path:resto>")
def visao_do_contrato_mudou(resto):
    """O endereço de antes (a Prévia, até 18/11/2026) leva à tela nova, com a busca."""
    q = request.query_string.decode("utf-8")
    return redirect(na_raiz(CONTRATOS) + (f"?{q}" if q else ""), code=308)


@bp.route("/contratos/dados.json")
def contratos_dados():
    """O estado de agora (a carga + as mudanças), com as contas de hoje, quem pode editar cada contrato e, para o
    administrador, as pessoas que podem ser gestoras."""
    from ...campo import visao
    _so_interno()
    base = _base()
    if not base["itens"]["cliente"]:
        resp = jsonify(ok=False)
    else:
        admin = bool(session.get("admin"))
        pessoas = _pessoas()
        try:
            mud = E.abrir(E.ler_banco())
            erro = None
        except Exception as e:   # noqa: BLE001 — banco fora: a carga sem as mudanças seria dado velho; a tela avisa
            _log.exception("Contratos: não li as edições do banco")
            mud, erro = [], f"Não li as edições do banco ({type(e).__name__}): o que aparece pode estar sem as últimas mudanças"
        st = E.aplicar(base, mud)
        out = E.visao(base, st, visao._agora().date(), pessoas, _meu_hmac(), admin)
        out.update(ok=True, erro_edicoes=erro, campos={t: [list(c[:3]) + [list(c[3]) if isinstance(c[3], tuple) else c[3]]
                                                           for c in E.CAMPOS[t]] for t in E.CAMPOS},
                   pessoas=pessoas if admin else [], eu=_usuario().get("nome") or "")
        resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/contratos/historico.json")
def contratos_historico():
    """O histórico de um cliente: cada mudança com quem, quando, o que era e o que ficou, o motivo e a prova."""
    _so_interno()
    cliente = request.args.get("cliente", "")
    base = _base()
    mud = E.abrir(E.ler_banco())
    out = E.historico(base, mud, cliente)
    for h in out:
        for a in h["anexos"]:
            a["url"] = na_raiz(f"{CONTRATOS}/anexo/{h['edicao_id']}/{a['n']}")
    resp = jsonify(ok=True, historico=out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/contratos/editar", methods=["POST"])
def contratos_editar():
    """Uma mudança (incluir, alterar ou retirar um item), com o motivo e a prova. Só da própria página; a resposta é
    JSON e a página relê o estado."""
    if _de_outro_site():
        abort(403)
    _so_interno()
    f = request.form
    try:
        valores = json.loads(f.get("valores") or "{}")
        if not isinstance(valores, dict):
            raise ValueError
    except ValueError:
        return jsonify(ok=False, erro="Mudança inválida"), 400
    arquivos = [(a.filename, a.stream) for a in request.files.getlist("provas")]
    try:
        r = E.gravar(_base(), f.get("item_tipo", ""), f.getlist("item_id"), f.get("evento", ""), f.get("cliente", ""),
                     valores, f.get("motivo", ""), f.get("prova_texto", ""), arquivos, _usuario(),
                     bool(session.get("admin")), _pessoas())
    except E.Recusada as e:
        return jsonify(ok=False, erro=str(e)), 400
    except Exception as e:       # noqa: BLE001 — banco fora: nada mudou, a tela diz
        _log.exception("Contratos: a mudança não gravou")
        return jsonify(ok=False, erro=f"Não consegui gravar no banco ({type(e).__name__}). Nada mudou; tente de novo."), 503
    return jsonify(ok=True, **r)


@bp.route("/contratos/carga-fichas", methods=["POST"])
def contratos_carga_fichas():
    """Mais fichas lidas dos PDFs na carga inicial (18/11/2026 à tarde: o Levi mandou os PDFs de mais clientes depois que a
    importação saiu da tela). Caminho interno do administrador, sem botão na tela (Levi: "Tire essas opções de subir
    arquivos"): quem lê os PDFs fora do Nexus manda o .json por aqui. Cliente novo entra; cliente que já tinha ficha é
    trocado só se ninguém editou um contrato lido ou uma regra dele (`edicao.juntar_fichas`). JSON na resposta."""
    import os

    from ...campo import visao
    from ...contratos import controle as K
    from ...contratos import fichas as F
    if _de_outro_site():
        abort(403)
    _so_interno()
    if not session.get("admin"):
        abort(403)
    f = request.files.get("fichas")
    if not f or not f.filename:
        return jsonify(ok=False, erro="Mande o arquivo das fichas (.json)"), 400
    conteudo = f.read(20 * 1024 * 1024 + 1)
    if len(conteudo) > 20 * 1024 * 1024:
        return jsonify(ok=False, erro="O arquivo passa de 20 MB"), 400
    try:
        novas = F.ler(json.loads(conteudo.decode("utf-8-sig")))
    except (ValueError, UnicodeDecodeError) as ex:
        return jsonify(ok=False, erro=str(ex) if isinstance(ex, F.FichasInvalidas) else "não é um .json válido"), 400
    controle = _json_da_pasta(K.ARQUIVO) or {}
    try:
        mud = E.abrir(E.ler_banco())
    except Exception as e:       # noqa: BLE001 — sem saber das edições, não troca nada
        return jsonify(ok=False, erro=f"Não li as edições do banco ({type(e).__name__}): nada foi trocado"), 503
    u = _usuario()
    doc, entraram, recusados = E.juntar_fichas(_json_da_pasta(F.ARQUIVO), novas, [c["cliente"] for c in controle.get("contratos") or []],
                                               mud, visao._agora().strftime("%Y-%m-%dT%H:%M"), u.get("nome") or u.get("email") or "",
                                               os.path.basename(f.filename))
    p = _pasta_contratos() / F.ARQUIVO
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return jsonify(ok=True, entraram=entraram, recusados=recusados,
                   regras=sum(len(c.get("regras") or []) for x in novas if x["cliente"] in entraram for c in x["contratos"]))


@bp.route("/contratos/anexo/<edicao_id>/<int:n>")
def contratos_anexo(edicao_id, n):
    """A prova de uma mudança, para quem é da Grid (o cliente não abre)."""
    _so_interno()
    if not E.ID_EDICAO.fullmatch(edicao_id):
        abort(404)
    achado = E.arquivo(edicao_id, n, E.abrir(E.ler_banco()))
    if not achado:
        abort(404)
    caminho, a = achado
    ext = caminho.suffix.lower()
    imagem = ext in (".png", ".jpg", ".jpeg", ".webp")
    return send_file(caminho, mimetype=E.SERVIDO.get(ext, "application/octet-stream"), as_attachment=not imagem and ext != ".pdf",
                     download_name=a.get("nome") or caminho.name)
