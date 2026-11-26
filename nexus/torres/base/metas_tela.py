"""Base › Metas das usinas (protótipo de 25/11/2026): a meta de cada mês de cada usina do Registro mestre, pelo PVsyst,
digitada ou colada do Excel, com o registro das edições. A regra mora em `nexus/performance/metas_pvsyst.py`; aqui só o
HTTP.

Levi, 24/11/2026: "É por eles [os PVsyst] que a gente preenche as metas [...] das usinas que não são da Thopen [...] a
ideia seria a gente anexar esses PVSys e já preencher automático na meta"; e, vendo o protótipo (25/11): "metas das
usinas tem que estar na parte de base [...] Na performance a gente vai focar na performance em si"; "é mais fácil ter um
botão de editar"; "Sempre que for fazer a porra de um filtro, ele tem que ser digitável"; as usinas "de acordo com o
registro mestre".

- `GET /t/base/metas`: a página (as usinas do Registro mestre que não são da Thopen, e as metas salvas).
- `POST /t/base/metas/abrir`: {usina_id, ano} -> a meta de agora da usina no ano: a salva no Nexus; sem ela, a da Info
  Mensal do BD_Performance (a linha casada pelo nome ou pelos Equipamentos); sem as duas, em branco.
- `POST /t/base/metas/ler`: o PDF (multipart, `arquivo`) -> o que se leu, a meta pelo PVsyst e a usina sugerida (com a
  meta de agora dela, para a tela marcar o que muda). O PDF fica guardado pelo sha.
- `POST /t/base/metas/salvar`: {usina_id, ano, meta: [12], sha?, arquivo?} -> salva e registra a edição (pasta de dados;
  NÃO vai ao banco nem à Sala até a validação).
- `GET /t/base/metas/pdf/<sha>`: o PDF guardado.
"""
from collections import Counter
from datetime import datetime

from flask import Response, abort, current_app, jsonify, render_template, request, session

from ...auth.origem import de_outro_site
from ...cadastro.ligacoes import pasta_dados
from ...dados.conexao import banco
from ...performance import metas_pvsyst as M

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


def _usinas() -> list[dict]:
    """As usinas do Registro mestre que não são da Thopen (a Thopen manda a própria meta, no banco), com o kWp da
    conferência (o real; sem ele, o contratual) e o rótulo da lista digitável: o nome; repetido, o nome e o cliente."""
    from ...cadastro.telas import servico
    from ...cadastro.telas_equipamentos import _usinas as usinas_com_kwp
    out = [{"id": str(u["id"]), "nome": str(u["nome"] or ""), "cliente": u.get("cliente") or "",
            "status": u.get("status") or "", "kwp": u.get("kwp")}
           for u in usinas_com_kwp(servico()) if u.get("nome") and "thopen" not in M.norm(u.get("cliente") or "")]
    conta = Counter(M.norm(u["nome"]) for u in out)
    for u in out:
        u["rotulo"] = u["nome"] if conta[M.norm(u["nome"])] == 1 else f"{u['nome']} ({u['cliente'] or 'sem cliente'})"
    return sorted(out, key=lambda u: M.norm(u["rotulo"]))


def _por_id() -> dict:
    """{id: usina} do Registro mestre; fora (sem a chave do cadastro), vazio: nenhuma usina se abre nem se salva."""
    try:
        return {x["id"]: x for x in _usinas()}
    except RuntimeError:
        return {}


def _meta_hoje() -> dict:
    """A Info Mensal do banco e o nome de cada usina em Base > Equipamentos; sem banco (fora do ar, teste), vazias com o
    erro: a tela segue com a meta salva no Nexus."""
    try:
        base, sessao = banco()
        mh = dict(M.meta_atual(base, sessao))
    except Exception as ex:      # noqa: BLE001
        return {"mensal": {}, "exibicoes": {}, "erro": f"{type(ex).__name__}: {str(ex)[:120]}"}
    exib = {}
    try:
        from ...cadastro import estrutura_usina as E
        for s in E.ler(base, sessao)["supervisorios"]:
            if not s.get("excluido") and s.get("usina_exibicao"):
                exib.setdefault(str(s["usina_id"]), set()).add(s["usina_exibicao"])
    except Exception:            # noqa: BLE001 — sem os Equipamentos, casa só pelo nome
        current_app.logger.warning("Metas: os Equipamentos das usinas não abriram; a Info Mensal casa só pelo nome.")
    mh["exibicoes"] = exib
    return mh


def _abrir(u: dict, ano, mh: dict, salvas: dict) -> dict:
    """A meta de agora da usina no ano, e os anos que se pode escolher."""
    linha = M.linha_da_info_mensal(u["nome"], mh["exibicoes"].get(u["id"]), mh["mensal"])
    meses = mh["mensal"].get(linha) or {}
    agora = datetime.now().year
    com_meta = {int(k[:4]) for k in meses} | {int(k.split("|")[1]) for k in salvas if k.split("|")[0] == u["id"]}
    try:
        ano = int(ano)
    except (TypeError, ValueError):
        ano = None
    if ano is None or not 2000 <= ano <= 2100:
        # sem ano pedido: o de agora, se tiver meta; senão o próximo que tiver (a Info Mensal de hoje já traz 2027)
        ano = agora if agora in com_meta or not com_meta else min([a for a in com_meta if a > agora] or [max(com_meta)])
    anos = sorted(com_meta | {agora, agora + 1, ano})
    salva = salvas.get(M.chave_meta(u["id"], ano))
    hoje = M.meta_de_hoje(meses, ano)
    if salva:
        atual, de_onde = salva["meta"], "nexus"
    elif any(x["p50_mwh"] is not None for x in hoje):
        atual, de_onde = hoje, "info_mensal"
    else:
        atual, de_onde = M.meta_vazia(), ""
    return {"ok": True, "usina_id": u["id"], "usina": u["rotulo"], "nome": u["nome"], "cliente": u["cliente"],
            "status": u["status"], "kwp": u["kwp"], "ano": ano, "anos": anos, "atual": atual, "de_onde": de_onde,
            "linha_info": linha,
            "salva": {k: salva.get(k) for k in ("origem", "salvo_em", "salvo_por", "sha", "arquivo", "projeto", "versao",
                                                 "simulado_em", "kwp")} | {"edicoes": len(salva.get("edicoes") or [])}
            if salva else None,
            "erro_meta": mh.get("erro") or ""}


def _json():
    if de_outro_site():
        abort(403)
    return request.get_json(silent=True) or {}


def _resumo(lido: dict) -> dict:
    return {k: lido.get(k) for k in ("projeto", "versao", "simulado_em", "local", "kwp", "pr_ano", "energia_ano_kwh",
                                     "conferencias")}


def registrar_metas(bp, torre) -> None:
    @bp.route("/metas")
    def metas():
        feitas = sorted(_salvas().values(), key=lambda r: (M.norm(r.get("usina")), r.get("ano") or 0))
        try:
            usinas, erro = _usinas(), ""
        except RuntimeError as ex:   # o Registro mestre fora (sem a chave do cadastro): a página abre e diz
            usinas, erro = [], str(ex)
        return render_template("metas_usinas.html", torre=torre, tela=torre.tela("metas"), salvas=feitas,
                               usinas=usinas, erro_cadastro=erro, descrever=M.descrever)

    @bp.route("/metas/abrir", methods=["POST"])
    def metas_abrir():
        d = _json()
        u = _por_id().get(str(d.get("usina_id") or ""))
        if not u:
            return jsonify(ok=False, erro="Escolha uma usina do Registro mestre."), 400
        return jsonify(_abrir(u, d.get("ano"), _meta_hoje(), _salvas()))

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
        usinas = list(_por_id().values())
        # a usina do nome do projeto e do arquivo, se for clara (o PDF da Iramaia anexado com outra usina aberta vai para
        # a Iramaia); sem ela, a que estava aberta na tela
        nome, _nota = M.sugerir_usina(lido, f.filename, [x["nome"] for x in usinas])
        u = next((x for x in usinas if x["nome"] == nome), None) or \
            {x["id"]: x for x in usinas}.get(str(request.form.get("usina_id") or ""))
        pv = {"sha": sha, "arquivo": f.filename, "lido": _resumo(lido), "meta": M.meta_do_pvsyst(lido)}
        if not u:
            return jsonify(ok=True, usina_id="", pvsyst=pv)
        return jsonify(dict(_abrir(u, request.form.get("ano"), _meta_hoje(), _salvas()), pvsyst=pv))

    @bp.route("/metas/salvar", methods=["POST"])
    def metas_salvar():
        d = _json()
        u = _por_id().get(str(d.get("usina_id") or ""))
        if not u:
            return jsonify(ok=False, erro="Escolha a usina da meta antes de salvar."), 400
        try:
            meta = M.validar_meta(d.get("meta"))
            ano = int(d.get("ano"))
            if not 2000 <= ano <= 2100:
                raise ValueError("ano fora de 2000 a 2100")
        except (ValueError, TypeError) as ex:
            return jsonify(ok=False, erro=f"A meta não foi salva: {ex}."), 400
        salvas = _salvas()
        anterior = salvas.get(M.chave_meta(u["id"], ano)) or {}
        sha, lido = str(d.get("sha") or ""), None
        if sha:
            dados = M.ler_pdf_guardado(_raiz(), sha)
            if dados is None:
                return jsonify(ok=False, erro="O PDF do PVsyst não está mais guardado: anexe de novo."), 400
            if anterior.get("sha") != sha:       # PDF novo nesta meta: o que se leu entra no registro
                lido = M.ler_texto(M.texto_do_pdf(dados))
        antes = None
        if not anterior:                         # a 1ª vez: o registro compara com a meta da Info Mensal que a tela mostrava
            ab = _abrir(u, ano, _meta_hoje(), salvas)
            antes = ab["atual"] if ab["de_onde"] == "info_mensal" else None
        reg = M.guardar(_raiz(), u["id"], u["rotulo"], ano, meta, _quem(), sha=sha,
                        nome_arquivo=str(d.get("arquivo") or "")[:200], lido=lido, antes=antes)
        n = len(reg["edicoes"][-1]["mudancas"])
        return jsonify(ok=True, salvo=reg, aviso=f"Meta {ano} de {u['rotulo']} salva ({reg['origem']}): "
                       f"{n} valor{'es' if n != 1 else ''} mudado{'s' if n != 1 else ''} no registro. Protótipo: a Sala de "
                       "controle e o Gerencial seguem com a Info Mensal até a validação.")

    @bp.route("/metas/pdf/<sha>")
    def metas_pdf(sha):
        dados = M.ler_pdf_guardado(_raiz(), sha)
        if dados is None:
            abort(404)
        return Response(dados, mimetype="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="pvsyst-{sha}.pdf"'})
