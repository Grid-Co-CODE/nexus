"""A torre Contratos e clientes saiu do menu em 12/11/2026. Esta pasta só guarda os endereços antigos.

Levi, 12/11/2026: "Outro ponto, contratos e clientes. Joga o acesso cliente lá para bases, contestações, você vai jogar
para o comando, prévia visão do contrato, você vai jogar no comando, tá certo? Vai ser basicamente isso. Essa parte de
contrato e clientes aqui vai sumir, vai ser absorvido por outras seções".

Para onde foi cada tela:
- Contestações → Comando (`/t/comando/contestacoes`, `nexus/torres/comando/contestacoes_tela.py`);
- Prévia: visão do contrato → Comando (`/t/comando/visao-do-contrato`, o mesmo módulo);
- Acessos dos clientes → Base (`/t/base/acessos-clientes`, `nexus/torres/base/acessos_clientes_tela.py`);
- Clientes, Onboarding de cliente, Comunicação por cliente e Portal do cliente eram só o aviso "em construção" e saíram.

As regras seguem em `nexus/contratos/` (leia o `CLAUDE.md` de lá). Sem `TORRE`, a pasta não entra no menu, no Início nem
na lista de telas dos setores; só o `bp` fica, para o endereço salvo não virar 404 (regra das torres: "Tela que sai não
vira 404"). O portão por setor deixa estes endereços passarem (`setor_telas.TORRES_EXTINTAS`): quem decide é a tela de
destino. A marca que o setor tinha na tela antiga vale para a nova (`setor_telas.RENOMEADAS`).
"""
from flask import Blueprint, redirect, request

from ...prefixo import na_raiz

# a tela antiga → o endereço novo; o que vem depois da tela (o card, o pegar, a atualização) vai junto
DESTINOS = {"contestacoes": "/t/comando/contestacoes",
            "previa": "/t/comando/visao-do-contrato",
            "acessos": "/t/base/acessos-clientes"}

bp = Blueprint("torre_contratos", __name__, url_prefix="/t/contratos")


@bp.route("/", defaults={"resto": ""}, methods=["GET", "POST"])
@bp.route("/<path:resto>", methods=["GET", "POST"])
def antigo(resto: str):
    """308: o método e o corpo vão junto (o formulário de uma aba que ficou aberta com o endereço antigo ainda grava). A
    tela que não tem sucessora (os quatro avisos de "em construção") leva ao Início."""
    tela, _, sub = resto.partition("/")
    destino = DESTINOS.get(tela)
    if destino is None:
        return redirect(na_raiz("/"), code=302)
    url = destino + (f"/{sub}" if sub else "")
    if request.query_string:
        url += "?" + request.query_string.decode("utf-8", "replace")
    return redirect(na_raiz(url), code=308)
