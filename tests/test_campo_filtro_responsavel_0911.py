"""O Responsável UFV que entrou abre a Central de atenção e as Rondas nas usinas dele (Levi, 09/11/2026, pelo Scrum master:
"Se o usuário do nexus for algum responsável por usina sempre que ele for acessar essas telas serão filtradas no nome
dele"), como a Visão do responsável, a Aprovação e as Ocorrências já faziam. O filtro continua trocável ("*" = todos) e
quem não é responsável de usina abre em todas. Nomes inventados."""
import re

from test_campo_responsaveis import _responsavel, banco, tela  # noqa: F401  (fixtures)

BELTRANO = "Beltrano Supervisor"


def _escolhido(html: str, nome: str) -> bool:
    """O responsável está escolhido no filtro da tela (a opção marcada)."""
    return re.search(rf'<option value="{re.escape(nome)}"\s+selected>', html) is not None


def test_a_central_abre_no_responsavel_que_entrou_e_o_todos_vale(tela, cliente):
    c = _responsavel(cliente)
    html = c.get("/t/campo/atencao").get_data(as_text=True)
    assert _escolhido(html, BELTRANO)
    # "Todos" é uma escolha: vai como "*" e não volta para o padrão; os links da tela levam o "*" adiante
    todos = c.get("/t/campo/atencao?responsavel=*").get_data(as_text=True)
    assert not _escolhido(todos, BELTRANO) and '<option value="*">Todos</option>' in todos
    pt = c.get("/t/campo/atencao?vista=pt&responsavel=*").get_data(as_text=True)
    assert not _escolhido(pt, BELTRANO)
    # a aba PT, sem escolha, também abre nele
    assert _escolhido(c.get("/t/campo/atencao?vista=pt").get_data(as_text=True), BELTRANO)


def test_as_rondas_abrem_no_responsavel_que_entrou(tela, cliente):
    c = _responsavel(cliente)
    assert _escolhido(c.get("/t/campo/rondas").get_data(as_text=True), BELTRANO)
    assert not _escolhido(c.get("/t/campo/rondas?responsavel=*").get_data(as_text=True), BELTRANO)


def test_quem_nao_e_responsavel_abre_em_todas(tela, logado):
    """O administrador (sem ficha de responsável de usina) e o coordenador abrem a Central e as Rondas em todas."""
    for url in ("/t/campo/atencao", "/t/campo/rondas"):
        assert not _escolhido(logado.get(url).get_data(as_text=True), BELTRANO), url
