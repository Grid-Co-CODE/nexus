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
