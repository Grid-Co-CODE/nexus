"""Os filtros de usina e de técnico da Aprovação de OS (Levi, 15/11/2026, repassado pelo chat do Comando: "na parte de
filtro de aprovação de OS, tem que ter o filtro de usina [...] Também tem que ter o filtro do técnico, que seria quem
executou a OS [...] a ideia seria já vir filtrado na usina correta"). O "Aprovar 7 OS em verificação" do prontuário da
usina abria a fila inteira; agora manda `?usina=<usina_id>` (o id do cadastro, o mesmo de /t/campo/usinas/<id>).

A fila dos testes (test_campo_aprovacao_responsavel.py): na Usina A (id 1, "SP 01" no Fracttal, responsável Ciclano
Chefe) 15002 (Técnico 7), 15088, 15102 e 17001 (fora do pré-filtro); na Usina C (id 3, "SC 01", responsável Beltrano
Supervisor) 16001. Fora a 15002, todas pelo Técnico 1."""
import re

from test_campo_aprovacao_responsavel import _folios, fila_resp, quadro  # noqa: F401  (fixtures)
from test_campo_aprovacao_supervisor import _sessao_nexus, fila  # noqa: F401  (fixtures)


def _form(html):
    m = re.search(r'<form[^>]*data-apq-filtros.*?</form>', html, re.S)
    return m.group(0) if m else ""


def test_a_usina_pelo_id_do_cadastro(quadro, logado):
    html = logado.get("/t/campo/aprovacao?usina=1").get_data(as_text=True)
    assert sorted(_folios(html)) == ["15002", "15088", "15102", "17001"]
    f = _form(html)
    # a lista vai ao servidor (com name, no painel Filtros), com o nome do cadastro e o id no valor
    assert re.search(r'<select[^>]*name="usina"', f)
    assert '<option value="1" selected>Usina A</option>' in f and '<option value="3">Usina C</option>' in f
    assert "Usina A" in html[html.index('class="apq-lote-total"'):html.index("data-apq-lote ")]
    outra = logado.get("/t/campo/aprovacao?usina=3").get_data(as_text=True)
    assert _folios(outra) == ["16001"]


def test_a_usina_pedida_no_endereco_nao_e_cortada_pelo_responsavel_do_login(quadro, cliente):
    # o Ciclano Chefe (91) é responsável só da Usina A e abre a tela nas usinas dele; vindo do prontuário da Usina C, a
    # tela abre na Usina C (o Visualizar do prontuário mostra as OS DELA), com o responsável em Todos
    _sessao_nexus(cliente, papel={"pessoa_id": 91, "nome": "Ciclano Chefe", "papel": "gestor", "gestor": "Ciclano Chefe"})
    cliente.get("/t/campo/aprovacao?responsavel=*")
    html = cliente.get("/t/campo/aprovacao?usina=3").get_data(as_text=True)
    assert _folios(html) == ["16001"]
    assert '<option value="*" selected>Todos</option>' in _form(html)


def test_o_tecnico_que_executou(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*&tecnico=T%C3%A9cnico+7").get_data(as_text=True)
    assert _folios(html) == ["15002"]
    f = _form(html)
    assert re.search(r'<select[^>]*name="tecnico"', f)
    assert '<option value="Técnico 7" selected>Técnico 7</option>' in f and '<option value="Técnico 1">Técnico 1</option>' in f
    junto = logado.get("/t/campo/aprovacao?usina=1&tecnico=T%C3%A9cnico+1").get_data(as_text=True)
    assert sorted(_folios(junto)) == ["15088", "15102", "17001"]


def test_o_csv_leva_os_filtros(quadro, logado):
    csv = logado.get("/t/campo/aprovacao?usina=3&csv=1").get_data(as_text=True)
    linhas = [x for x in csv.splitlines()[1:] if x.strip()]
    assert len(linhas) == 1 and linhas[0].startswith("16001;")


def test_usina_sem_os_na_fila_abre_vazia_com_o_nome(quadro, logado, fila_resp):  # noqa: F811
    # a usina pedida que não tem OS na fila (a conta do prontuário pode estar à frente da releitura): o quadro vazio,
    # com a usina escolhida na lista, e não a fila inteira
    fila_resp.linhas[:] = [w for w in fila_resp.linhas if w["groups_1_description"] != "SC 01"]
    html = logado.get("/t/campo/aprovacao?usina=3").get_data(as_text=True)
    assert _folios(html) == []
    assert '<option value="3" selected>Usina C</option>' in _form(html)


def test_nome_repetido_na_lista_ganha_o_cliente():
    """15/11/2026, conferido em produção: há duas "Linhares 1" no cadastro (a da Axis e a da Thopen, ids diferentes); a
    lista mostrava dois "Linhares 1" iguais. O nome que se repete leva o cliente; o que não se repete fica só o nome."""
    from types import SimpleNamespace

    from nexus.torres.campo import _opcoes_usina
    oss = [{"usina_id_cad": 27, "usina_cad": "Linhares 1", "cliente_cad": "Axis"},
           {"usina_id_cad": 96, "usina_cad": "Linhares 1", "cliente_cad": "Thopen"},
           {"usina_id_cad": 5, "usina_cad": "Altair", "cliente_cad": "Thopen"}]
    mapa = SimpleNamespace(dados={"por_nome": {}})
    assert _opcoes_usina(oss, mapa, None) == [(5, "Altair"), (27, "Linhares 1 · Axis"), (96, "Linhares 1 · Thopen")]
