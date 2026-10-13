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

    As molduras da Performance (porta única) só contam com a porta ligada (`moldura.SO_COM_A_PORTA`): sem a chave elas
    abrem o aviso "ainda não ligada", e o verde mentiria (revisão de 10/10/2026). A configuração não muda depois do boot,
    então a conta continua sendo uma só.
    """
    from werkzeug.exceptions import HTTPException

    from .moldura import SO_COM_A_PORTA, estado_da_porta

    porta_ligada = estado_da_porta(app.config)["ligada"]
    rotas = app.url_map.bind("localhost")
    prontas = set()
    for torre in app.extensions["nexus_torres"]:
        for tela in torre.telas:
            url = f"/t/{torre.id}/{tela.id}"
            try:
                endpoint, _ = rotas.match(url, method="GET")
            except HTTPException:
                continue
            if endpoint == f"torre_{torre.id}.placeholder" or (endpoint in SO_COM_A_PORTA and not porta_ligada):
                continue
            prontas.add(url)
    return frozenset(prontas)


def montar_menu(torres: list[Torre], torre_atual: str | None, prontas: frozenset[str] = frozenset(),
                liberadas: set[str] | None = None) -> list[dict]:
    """As torres na ordem do catálogo, só com as telas que o setor da pessoa vê (`liberadas`, chaves `torre/tela`; None =
    tudo, o administrador). Torre sem nenhuma tela liberada some. A cadeira (a torre dela subia para o topo) saiu em
    12/10/2026: os setores a substituíram (Base → Acessos).

    O Início não entra aqui: é um botão da casca, fixo no topo do menu. Antes era uma torre cujo
    primeiro sub-item era o próprio Início, o que não fazia sentido para quem usa (Levi, 29/09).
    """
    menu = []
    for t in sorted(torres, key=lambda t: t.ordem):
        telas = [{"id": s.id, "nome": s.nome, "url": f"/t/{t.id}/{s.id}", "pronta": f"/t/{t.id}/{s.id}" in prontas}
                 for s in t.telas if liberadas is None or f"{t.id}/{s.id}" in liberadas]
        if not telas:
            continue
        menu.append({
            "id": t.id,
            "nome": t.nome,
            "icone": t.icone,
            "aberta": t.id == torre_atual,
            "telas": telas,
            "prontas": sum(s["pronta"] for s in telas),
        })
    return menu
