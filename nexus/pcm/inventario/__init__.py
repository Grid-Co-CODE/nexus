"""O inventário do almoxarifado (Levi, 26/10/2026): o técnico conta as peças no App, o PCM revisa e aprova, e o Nexus grava o
saldo contado no estoque do Fracttal. Desenho: `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`; o que o
Fracttal de verdade aceita (os métodos, os corpos, as respostas): `...-passo0.md`.

`estoque` é o adaptador: a ÚNICA porta de leitura e gravação de estoque no Fracttal. Quem grava, ajusta a régua ou cria peça
fala só com ele (ou com o `EstoqueFalso` dos testes). `contas` são as contas do inventário (situação de cada peça, contado
efetivo com a curadoria, a contagem mais nova que substitui as velhas, a janela de aprovação), puras: quem lê o livro, mostra
o lote e grava chama as mesmas. `leitura` lê as contagens que o App publica e o estado de cada uma pelos eventos do livro
do inventário. `revisao` é a aba Inventário (a lista, a contagem aberta e a revisão do PCM), `gravacao` grava o lote aprovado
no Fracttal em segundo plano, por sessão de ajuste, `regua` é a régua de mínimo e máximo e `curadoria` o fora do catálogo.
`ponte_os` é a ponte com o login do Fracttal: o cookie dele só chega nas rotas de `/os`, então tudo o que lê ou grava no
Fracttal (o lote, gravar, continuar, encerrar, a régua acordada, cadastrar a peça) roda em `/os/_nexus/inventario/...`.
"""


def registrar(bp) -> None:
    """As rotas da aba Inventário na torre PCM, todas debaixo de `/pecas/inventario` (sub-rotas da tela Almoxarifado, que é do
    setor PCM: quem não a vê, não vê estas). Importa dentro da função: o pacote é importado pelos testes do adaptador sem a
    torre, e `pcm.telas` puxa o motor inteiro."""
    from flask import abort, current_app, jsonify, render_template, request, session

    from ...dados import fato_inventario as F
    from ..telas import _de_outro_site, pode_programar
    from . import gravacao as G
    from . import ponte_os
    from . import revisao as R

    # a ponte com o login do Fracttal fica na RAIZ do app (`/os/_nexus/inventario`, o cookie dele só vai para /os): entra junto com
    # a torre, como a ponte do OS Creator (`torres/oscreator/__init__.py`)
    ponte_os.registrar(bp)                     # idempotente: a torre também chama

    def _da_gravacao(contagem_id) -> dict:
        """O andamento da gravação desta contagem para a tela (None sem gravação) e se quem abre pode continuar agora (ela
        parou, e é quem aprovou, pelo HMAC do e-mail)."""
        grav = G.estado(current_app.config, contagem_id)
        usuario = session.get("usuario")
        email = usuario.get("email") if isinstance(usuario, dict) else None
        parada = bool(grav) and grav["estado"] == "parada"
        return {"gravacao": grav,
                "pode_continuar": parada and G.e_o_aprovador(current_app.config, contagem_id, {"email": email}),
                # quem aprovou, a qualquer hora; o administrador, parada há mais de 24 h
                "pode_encerrar": parada and G.pode_encerrar(current_app.config, contagem_id, {"email": email},
                                                            admin=bool(session.get("admin")))}

    @bp.route("/pecas/inventario", endpoint="inventario")
    def inventario():
        # a gravação parada com o almoxarifado travado no Fracttal avisa também aqui (quem aprovou talvez nem abra a contagem)
        return render_template("pcm/inventario.html", **R.montar_lista(current_app.config),
                               travadas=G.travadas(current_app.config))

    @bp.route("/pecas/inventario/auditoria", endpoint="inventario_auditoria")
    def inventario_auditoria():
        """A aba Auditoria: os eventos do livro do inventário, com o filtro por tipo e a busca na própria página. Não fala com o
        Fracttal; o motivo (cifrado) não aparece, e o nome de quem fez só para quem pode revisar."""
        from .. import telas         # pelo módulo, na hora do pedido (como a régua e a curadoria): quem pode é decidido agora
        a = request.args
        return render_template("pcm/inventario_auditoria.html", a_revisar=R.a_revisar(current_app.config),
                               **R.montar_auditoria(current_app.config, telas.pode_programar(), str(a.get("tipo") or ""),
                                                    str(a.get("busca") or "")))

    @bp.route("/pecas/inventario/<contagem_id>", endpoint="inventario_contagem")
    def inventario_contagem(contagem_id):
        """A contagem aberta, SEM o Fracttal: o login dele não chega a `/t/pcm` (o cookie vale só em /os). O Sistema, o Δ e os seis
        grupos a página busca na ponte (`ponte_os.lote`)."""
        try:
            ctx = R.montar(current_app.config, contagem_id, pode_programar())
        except F.Recusada as ex:
            return render_template("pcm/inventario_contagem.html", erro=str(ex), c=None, a_revisar=None)
        if ctx is None:
            abort(404)
        # o botão "Gravar N alterações" e a assinatura do lote vêm no pedaço da ponte (`ponte_os.lote`), junto do Sistema que
        # eles conferem; aqui fica o andamento da gravação, que não depende do Fracttal (o controle no disco), e a etapa
        # Auditoria: os eventos do livro só desta contagem (o `?tipo=` e o `?busca=` já chegam filtrados, como na Auditoria geral)
        a = request.args
        auditoria = R.montar_auditoria(current_app.config, pode_programar(), str(a.get("tipo") or ""),
                                       str(a.get("busca") or ""), contagem_id=contagem_id)
        return render_template("pcm/inventario_contagem.html", erro="", a_revisar=None, auditoria=auditoria, **ctx,
                               **_da_gravacao(contagem_id))

    @bp.route("/pecas/inventario/<contagem_id>/estado.json", endpoint="inventario_estado")
    def inventario_estado(contagem_id):
        """O andamento da gravação (a tela olha a cada 3 s). Não fala com o Fracttal: lê o controle da gravação."""
        d = _da_gravacao(contagem_id)
        if d["gravacao"] is None:
            return jsonify(ok=False, erro="Esta contagem não tem gravação."), 404
        return jsonify(ok=True, pode_continuar=d["pode_continuar"], pode_encerrar=d["pode_encerrar"], **d["gravacao"])

    @bp.route("/pecas/inventario/<contagem_id>/revisar", methods=["POST"], endpoint="inventario_revisar")
    def inventario_revisar(contagem_id):
        """Tirar uma peça do lote, corrigir o número ou pedir a recontagem (JSON), só de quem `pode_programar` (o
        administrador e o setor PCM) e de uma página deste mesmo endereço. Grava um evento; nunca fala com o Fracttal."""
        if _de_outro_site() or not pode_programar():
            return jsonify(ok=False, erro=R.SO_PCM), 403
        usuario = session.get("usuario")
        email = usuario.get("email") if isinstance(usuario, dict) else None
        try:
            return jsonify(R.revisar(current_app.config, contagem_id, request.get_json(silent=True),
                                     R.pessoa(current_app.config, email)))
        except R.Recusa as ex:
            return jsonify(ok=False, erro=ex.mensagem, **ex.extra), ex.status
