"""Performance › Metas das usinas (protótipo de 25/11/2026): a meta de cada mês pelo PVsyst, editável, ou digitada/colada
à mão, com o registro das edições. A regra mora em `nexus/performance/metas_pvsyst.py`; aqui só o HTTP. Importado no fim
do `__init__` da torre (precisa do `bp`).

Levi, 24/11/2026: "É por eles [os PVsyst] que a gente preenche as metas [...] das usinas que não são da Thopen [...] a
ideia seria a gente anexar esses PVSys e já preencher automático na meta"; e, vendo o protótipo (25/11): "deve ser
possível editar e ter o registro das edições ou inserir todos os dados manualmente [...] que nem no Excel, a pessoa pegar
e colar".

- `GET /t/performance/metas`: a página.
- `POST /t/performance/metas/ler`: o PDF (multipart, `arquivo`) -> o que se leu e a meta pelo PVsyst, para editar. O PDF
  fica guardado pelo sha.
- `POST /t/performance/metas/abrir`: {usina, ano} -> a meta salva da usina (para editar) ou 12 meses em branco (à mão),
  com a meta de hoje (Info Mensal) do ano.
- `POST /t/performance/metas/hoje`: {usina, ano} -> só a meta de hoje do ano (trocar o ano ou a usina sem perder o editado).
- `POST /t/performance/metas/salvar`: {usina, ano, meta: [12], sha?, arquivo?} -> salva e registra a edição (pasta de
  dados; NÃO vai ao banco nem à Sala até a validação).
- `GET /t/performance/metas/pdf/<sha>`: o PDF guardado.
"""
from datetime import datetime

from flask import Response, abort, current_app, jsonify, render_template, request, session

from ...auth.origem import de_outro_site
from ...cadastro.ligacoes import pasta_dados
from ...dados.conexao import banco
from ...performance import metas_pvsyst as M
from . import TORRE, bp

MAX_PDF = 25 * 1024 * 1024


def _raiz():
    return pasta_dados(current_app.config)


def _salvas() -> dict:
    try:
        return M.salvas(_raiz())
    except RuntimeError:         # teste sem pasta de dados: nada salvo
        return {}


def _quem() -> str:
    u = session.get("usuario") or {}
    return (u.get("nome") or u.get("email") or "").strip() or "administrador (senha)"


def _meta_hoje() -> dict:
    """A meta de hoje do banco; sem banco (fora do ar, teste), vazia com o erro: a tela segue sem a comparação."""
    try:
        return M.meta_atual(*banco())
    except Exception as ex:      # noqa: BLE001
        return {"mensal": {}, "geral": {}, "usinas": [], "clientes": {}, "lido_em": None,
                "erro": f"{type(ex).__name__}: {str(ex)[:120]}"}


def _ano(usina: str, ano, meta_hoje: dict) -> tuple[int, list[int]]:
    anos = sorted({int(k[:4]) for k in (meta_hoje["mensal"].get(usina) or {})}) or [datetime.now().year]
    agora = datetime.now().year
    for a in (agora, agora + 1):
        if a not in anos:
            anos.append(a)
    anos = sorted(set(anos))
    try:
        ano = int(ano)
    except (TypeError, ValueError):
        ano = None
    if ano not in anos:
        ano = agora + 1 if (agora + 1) in anos and (meta_hoje["mensal"].get(usina) or {}).get(f"{agora + 1}-01") else agora
    return ano, anos


def _hoje(usina: str, ano, meta_hoje: dict) -> dict:
    ano, anos = _ano(usina, ano, meta_hoje)
    return {"ok": True, "usina": usina, "ano": ano, "anos": anos, "cliente": meta_hoje["clientes"].get(usina, ""),
            "kwp_hoje": (meta_hoje["geral"].get(usina) or {}).get("kwp"),
            "hoje": M.meta_de_hoje(meta_hoje["mensal"].get(usina) or {}, ano), "usinas": meta_hoje["usinas"],
            "erro_meta": meta_hoje.get("erro") or ""}


def _resumo(lido: dict) -> dict:
    return {k: lido.get(k) for k in ("projeto", "versao", "simulado_em", "local", "kwp", "pr_ano", "energia_ano_kwh",
                                     "conferencias")}


@bp.route("/metas")
def metas():
    meta_hoje = _meta_hoje()
    feitas = sorted(_salvas().values(), key=lambda r: M.norm(r["usina"]))
    return render_template("performance/metas.html", torre=TORRE, tela=TORRE.tela("metas"), salvas=feitas,
                           usinas=meta_hoje["usinas"], erro_meta=meta_hoje.get("erro") or "", descrever=M.descrever)


@bp.route("/metas/ler", methods=["POST"])
def metas_ler():
    if de_outro_site():
        return jsonify(ok=False, erro="Pedido de outro site: nada foi lido."), 403
    f = request.files.get("arquivo")
    if not f or not f.filename:
        return jsonify(ok=False, erro="Escolha o PDF do PVsyst."), 400
    dados = f.read(MAX_PDF + 1)
    if len(dados) > MAX_PDF:
        return jsonify(ok=False, erro="O PDF passa de 25 MB."), 400
    if not dados.startswith(b"%PDF"):
        return jsonify(ok=False, erro=f"“{f.filename}” não é um PDF."), 400
    try:
        lido = M.ler_texto(M.texto_do_pdf(dados))
    except M.NaoEhPvsyst as ex:
        return jsonify(ok=False, erro=f"“{f.filename}”: {ex}."), 422
    except Exception as ex:      # noqa: BLE001 — PDF torto, protegido
        return jsonify(ok=False, erro=f"Não consegui ler “{f.filename}” ({type(ex).__name__})."), 422
    sha = M.guardar_pdf(_raiz(), dados)
    meta_hoje = _meta_hoje()
    usina, nota = M.sugerir_usina(lido, f.filename, meta_hoje["usinas"])
    return jsonify(dict(_hoje(usina, None, meta_hoje), sha=sha, arquivo=f.filename, nota=nota, lido=_resumo(lido),
                        meta=M.meta_do_pvsyst(lido), origem="PVsyst"))


def _json():
    if de_outro_site():
        abort(403)
    return request.get_json(silent=True) or {}


@bp.route("/metas/abrir", methods=["POST"])
def metas_abrir():
    d = _json()
    usina = str(d.get("usina") or "").strip()
    meta_hoje = _meta_hoje()
    if not usina:
        return jsonify(ok=False, erro="Escolha a usina."), 400
    salva = _salvas().get(usina)
    r = _hoje(usina, d.get("ano") or (salva or {}).get("ano"), meta_hoje)
    if salva:
        lido = {k: salva.get(k) for k in ("projeto", "versao", "simulado_em", "kwp", "pr_ano", "energia_ano_kwh")} \
            if salva.get("sha") else None
        return jsonify(dict(r, meta=salva["meta"], origem=salva.get("origem"), sha=salva.get("sha") or "",
                            arquivo=salva.get("arquivo") or "", lido=lido, edicoes=len(salva.get("edicoes") or [])))
    return jsonify(dict(r, meta=M.meta_vazia(), origem="manual", sha="", arquivo="", lido=None, edicoes=0))


@bp.route("/metas/hoje", methods=["POST"])
def metas_hoje():
    d = _json()
    return jsonify(_hoje(str(d.get("usina") or "").strip(), d.get("ano"), _meta_hoje()))


@bp.route("/metas/salvar", methods=["POST"])
def metas_salvar():
    d = _json()
    meta_hoje = _meta_hoje()
    usina = str(d.get("usina") or "").strip()
    if not usina or (usina not in meta_hoje["usinas"] and usina not in meta_hoje["mensal"] and usina not in _salvas()):
        return jsonify(ok=False, erro="Escolha a usina da meta antes de salvar."), 400
    try:
        meta = M.validar_meta(d.get("meta"))
        ano = int(d.get("ano"))
    except (ValueError, TypeError) as ex:
        return jsonify(ok=False, erro=f"A meta não foi salva: {ex}."), 400
    sha, lido = str(d.get("sha") or ""), None
    if sha:
        dados = M.ler_pdf_guardado(_raiz(), sha)
        if dados is None:
            return jsonify(ok=False, erro="O PDF do PVsyst não está mais guardado: anexe de novo."), 400
        anterior = _salvas().get(usina) or {}
        if anterior.get("sha") != sha:           # PDF novo nesta usina: o que se leu entra no registro
            lido = M.ler_texto(M.texto_do_pdf(dados))
    reg = M.guardar(_raiz(), usina, ano, meta, _quem(), sha=sha, nome_arquivo=str(d.get("arquivo") or "")[:200], lido=lido)
    ultima = reg["edicoes"][-1]
    n = len(ultima["mudancas"])
    return jsonify(ok=True, salvo=reg, aviso=f"Meta de {usina} salva ({reg['origem']}, {reg['salvo_em']}): "
                   f"{n} valor{'es' if n != 1 else ''} mudado{'s' if n != 1 else ''} registrado{'s' if n != 1 else ''}. "
                   "Protótipo: a Sala de controle e o Gerencial seguem com a Info Mensal até a validação.")


@bp.route("/metas/pdf/<sha>")
def metas_pdf(sha):
    dados = M.ler_pdf_guardado(_raiz(), sha)
    if dados is None:
        abort(404)
    return Response(dados, mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="pvsyst-{sha}.pdf"'})
