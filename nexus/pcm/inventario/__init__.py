"""O inventário do almoxarifado (Levi, 26/10/2026): o técnico conta as peças no App, o PCM revisa e aprova, e o Nexus grava o
saldo contado no estoque do Fracttal. Desenho: `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`; o que o
Fracttal de verdade aceita (os métodos, os corpos, as respostas): `...-passo0.md`.

`estoque` é o adaptador: a ÚNICA porta de leitura e gravação de estoque no Fracttal. Quem grava, ajusta a régua ou cria peça
fala só com ele (ou com o `EstoqueFalso` dos testes). `contas` são as contas do inventário (situação de cada peça, contado
efetivo com a curadoria, a contagem mais nova que substitui as velhas, a janela de aprovação), puras: quem lê o livro, mostra
o lote e grava chama as mesmas. `leitura` lê as contagens que o App publica e o estado de cada uma pelos eventos do livro
do inventário. `revisao` é a aba Inventário (a lista, a contagem aberta e a revisão do PCM) e `ponte_os` é a ponte com o login
do Fracttal: o cookie dele só chega nas rotas de `/os`, então tudo o que lê ou grava no Fracttal roda em
`/os/_nexus/inventario/...`. A gravação em segundo plano, a régua e a curadoria entram nas tarefas seguintes.
"""


def registrar(bp) -> None:
    """As rotas da aba Inventário na torre PCM, todas debaixo de `/pecas/inventario` (sub-rotas da tela Almoxarifado, que é do
    setor PCM: quem não a vê, não vê estas). Importa dentro da função: o pacote é importado pelos testes do adaptador sem a
    torre, e `pcm.telas` puxa o motor inteiro."""
    from flask import abort, current_app, jsonify, render_template, request, session

    from ...dados import fato_inventario as F
    from ..telas import _de_outro_site, pode_programar
    from . import ponte_os
    from . import revisao as R

    # a ponte com o login do Fracttal fica na RAIZ do app (`/os/_nexus/inventario`, o cookie dele só vai para /os): entra junto com
    # a torre, como a ponte do OS Creator (`torres/oscreator/__init__.py`)
    bp.record_once(lambda estado: estado.app.register_blueprint(ponte_os.bp_raiz))

    @bp.route("/pecas/inventario", endpoint="inventario")
    def inventario():
        return render_template("pcm/inventario.html", **R.montar_lista(current_app.config))

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
        return render_template("pcm/inventario_contagem.html", erro="", a_revisar=None, **ctx)

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
