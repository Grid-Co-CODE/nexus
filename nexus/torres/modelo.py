"""Peças de uma torre: a Torre, suas Telas e a view genérica de placeholder.

Uma torre nova é só uma pasta em nexus/torres/ com um __init__.py assim:

    TORRE = Torre("cos", "COS", ordem=20, icone="broadcast", telas=[Tela(...), ...])
    bp = TORRE.criar_blueprint(__name__)

    @bp.route("/mesa")          # opcional: view própria vence a genérica
    def mesa(): ...

Tela sem view própria abre o placeholder, que diz o que ela vai ser e de onde virá o dado.
"""
from dataclasses import dataclass, field

from flask import Blueprint, abort, render_template


@dataclass(frozen=True)
class Tela:
    id: str
    nome: str
    pergunta: str   # a pergunta que a tela responde, na voz de quem usa
    fonte: str      # de onde o dado vai vir quando a tela for construída
    # a tela que se abre POR DENTRO de outra da mesma torre (13/10/2026, os relatórios da Central de emissão; Levi: "Aí a
    # pessoa escolhe que tipo de relatório ela quer!"): sem item próprio no menu, o item da outra acende quando ela está
    # aberta, e quem tem ela liberada no setor vê a outra também (auth/setor_telas.py). Vazio = item do menu, como sempre
    dentro_de: str = ""
    # o setor DONO da tela, pelo setor_id (`cadastro/setor_ids.py`; até 04/11/2026 era o nome, e renomear o setor em Base →
    # Acessos tirava a tela dele sem erro): quem é dele vê a tela sem marcá-la em Base → Acessos (13/10/2026, Levi, sobre os
    # relatórios da Central: "Potência ativa faz parte da performance!" e "Esses dois são do setor performance"). Vazio = só
    # as marcas, como sempre. Pode ser mais de um (uma tupla de IDs, `setor_telas.donos_do_codigo`; 16/10/2026, o Gerar e o
    # Quadro do PCM, que são também dos supervisores: Levi, "tanto PCM quanto supervisores!")
    do_setor: int | tuple[int, ...] = ()
    # a tela de TODO setor (03/11/2026, a Caixa de entrada; Levi: "libera a caixa para todos os setores"): quem tem setor
    # a vê sem marca, como a do dono; quem é mencionado numa conversa precisa dela para ver o aviso
    de_todos: bool = False
    # a tela que recorta pelas usinas do cliente da sessão (07/11/2026, o acesso dos clientes, `auth/clientes.py`): só
    # estas o setor Clientes pode marcar em Base → Acessos, e o cliente não abre nenhuma outra
    do_cliente: bool = False
    # a tela SÓ do cliente (09/11/2026, a Visão do cliente; Levi: "pode tirar pois já temos no modo cliente do nosso
    # menu"): fica no menu do cliente e do administrador no Modo cliente, e sai do menu de quem é da Grid e da lista de
    # telas dos setores da Grid em Base → Acessos
    so_do_cliente: bool = False


@dataclass
class Torre:
    id: str
    nome: str
    ordem: int
    icone: str                      # nome do ícone Phosphor (ph-<icone>)
    descricao: str = ""             # uma frase: para que a torre existe
    telas: list[Tela] = field(default_factory=list)

    def tela(self, tela_id: str) -> Tela | None:
        return next((t for t in self.telas if t.id == tela_id), None)

    @property
    def pasta(self) -> str:
        """Pasta da torre em nexus/torres/. Nem sempre é o id: a torre "os" mora em oscreator/."""
        return getattr(self, "_pasta", self.id)

    def criar_blueprint(self, import_name: str) -> Blueprint:
        self._pasta = import_name.rsplit(".", 1)[-1]
        bp = Blueprint(f"torre_{self.id}", import_name, url_prefix=f"/t/{self.id}",
                       template_folder="templates")
        torre = self

        @bp.route("/<tela_id>")
        def placeholder(tela_id: str):
            tela = torre.tela(tela_id)
            if tela is None:
                abort(404)
            return render_template("tela.html", torre=torre, tela=tela)

        return bp
