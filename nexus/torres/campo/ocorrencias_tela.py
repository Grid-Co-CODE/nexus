"""A tela Ocorrências da Usinas 360° SAIU em 15/11/2026 (Levi: "mandei capar novas ocorrências mesmo, vai ser substituída
por caixa de entrada em comando"; "tem que matar esse caminho de ocorrências!"). Saíram o menu, a lista, o quadro, a
página da ocorrência, a nova, a etiqueta da Visão geral e a seção do prontuário; os problemas da usina vão como demanda
pela Caixa de entrada do Comando. Todo endereço antigo dela leva para lá, e nada se grava.

Ficam o livro `nexus_ocorrencias` (no banco e no catálogo) e a conta dele (`nexus/campo/ocorrencias.py`): é dado (em
15/11 eram 0 ocorrências em produção)."""
from flask import redirect, url_for

from . import bp


@bp.route("/ocorrencias", methods=["GET", "POST"])
@bp.route("/ocorrencias/<path:resto>", methods=["GET", "POST"])
def ocorrencias(resto: str = ""):
    """Qualquer endereço da tela antiga (a lista, o quadro, a nova, a página e os formulários de uma ocorrência): a Caixa
    de entrada do Comando. 303 para o POST virar GET lá, sem gravar nada."""
    return redirect(url_for("torre_comando.caixa_de_entrada"), code=303)
