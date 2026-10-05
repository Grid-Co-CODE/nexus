"""Descoberta das torres: cada subpasta com TORRE e bp vira uma torre registrada.

Assim o programador do COS cria telas em nexus/torres/cos/ sem tocar em nenhum outro arquivo, e uma
torre nova não depende de alguém lembrar de registrá-la num lugar central.
"""
import importlib
import pkgutil

from .modelo import Tela, Torre

__all__ = ["Tela", "Torre", "descobrir_torres", "registrar_torres", "montar_menu", "telas_com_conteudo"]


def _modulos():
    for info in pkgutil.iter_modules(__path__):
        if info.ispkg:
            yield importlib.import_module(f"{__name__}.{info.name}")


def descobrir_torres() -> list[Torre]:
    torres = [m.TORRE for m in _modulos() if hasattr(m, "TORRE")]
    return sorted(torres, key=lambda t: t.ordem)


def registrar_torres(app) -> None:
    for modulo in _modulos():
        if hasattr(modulo, "bp"):
            app.register_blueprint(modulo.bp)
    app.extensions["nexus_torres"] = descobrir_torres()


def telas_com_conteudo(app) -> frozenset[str]:
    """Endereços das telas que já têm view própria, e não o placeholder genérico da torre.

    É o que pinta de verde o menu, para o Levi ir vendo o progresso (04/10/2026). Sai do mapa de rotas, e não de uma
    lista à mão: quem constrói uma tela não precisa lembrar de marcá-la, e uma marca esquecida não mente.
    """
    from werkzeug.exceptions import HTTPException

    rotas = app.url_map.bind("localhost")
    prontas = set()
    for torre in app.extensions["nexus_torres"]:
        for tela in torre.telas:
            url = f"/t/{torre.id}/{tela.id}"
            try:
                endpoint, _ = rotas.match(url, method="GET")
            except HTTPException:
                continue
            if endpoint != f"torre_{torre.id}.placeholder":
                prontas.add(url)
    return frozenset(prontas)


def montar_menu(torres: list[Torre], cadeira_id: str | None, torre_atual: str | None,
                prontas: frozenset[str] = frozenset()) -> list[dict]:
    """A torre da cadeira primeiro, aberta e marcada; o resto na ordem do catálogo.

    O Início não entra aqui: é um botão da casca, fixo no topo do menu. Antes era uma torre cujo
    primeiro sub-item era o próprio Início, o que não fazia sentido para quem usa (Levi, 29/09).
    """
    from ..cadeiras import CADEIRAS

    cadeira = CADEIRAS.get(cadeira_id) if cadeira_id else None
    da_cadeira = cadeira.torre_inicial if cadeira else None

    menu = []
    for t in sorted(torres, key=lambda t: (t.id != da_cadeira, t.ordem)):
        sua = t.id == da_cadeira
        telas = [{"id": s.id, "nome": s.nome, "url": f"/t/{t.id}/{s.id}", "pronta": f"/t/{t.id}/{s.id}" in prontas}
                 for s in t.telas]
        menu.append({
            "id": t.id,
            "nome": t.nome,
            "icone": t.icone,
            "sua": sua,
            "aberta": sua or t.id == torre_atual,
            "telas": telas,
            "prontas": sum(s["pronta"] for s in telas),
        })
    return menu
