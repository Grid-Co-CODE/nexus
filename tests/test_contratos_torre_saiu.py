"""A torre Contratos e clientes saiu do menu (12/11/2026). Levi: "Outro ponto, contratos e clientes. Joga o acesso
cliente lá para bases, contestações, você vai jogar para o comando, prévia visão do contrato, você vai jogar no comando
[...] Essa parte de contrato e clientes aqui vai sumir, vai ser absorvido por outras seções".

O que não pode quebrar: o endereço salvo leva à tela nova (com o resto do caminho e o filtro), a marca que o setor tinha
na tela antiga vale na nova, e o portão por setor não barra o endereço antigo antes do redirecionamento."""
import re

from nexus.auth import setor_telas as ST
from nexus.torres import descobrir_torres


def test_a_torre_saiu_do_menu_e_as_telas_foram_para_o_comando_e_a_base(logado):
    torres = {t.id: t for t in descobrir_torres()}
    assert "contratos" not in torres
    comando = [s.id for s in torres["comando"].telas]
    assert comando[-2:] == ["contestacoes", "visao-do-contrato"] and torres["comando"].tela("visao-do-contrato").de_todos
    base = [s.id for s in torres["base"].telas]
    assert base.index("acessos-clientes") == base.index("acessos") + 1
    html = logado.get("/").get_data(as_text=True)
    menu = html.split('<nav class="menu"', 1)[1].split("</nav>", 1)[0]
    assert "Contratos e clientes" not in menu and "/t/contratos/" not in html
    for endereco, nome in (("/t/comando/contestacoes", "Contestações"), ("/t/comando/visao-do-contrato", "Prévia: visão do contrato"),
                           ("/t/base/acessos-clientes", "Acessos dos clientes")):
        assert re.search(r'<a href="%s"[^>]*>\s*%s' % (re.escape(endereco), re.escape(nome)), menu), endereco
    # as quatro telas que eram só o aviso de "em construção" saíram junto
    for fora in ("Onboarding de cliente", "Comunicação por cliente", "Portal do cliente"):
        assert fora not in menu


def test_o_endereco_antigo_leva_a_tela_nova(logado):
    def destino(caminho, metodo="get"):
        r = getattr(logado, metodo)(caminho)
        return r.status_code, r.headers.get("Location", "")

    assert destino("/t/contratos/contestacoes") == (308, "/t/comando/contestacoes")
    # o filtro e o resto do caminho vão junto: o link do aviso do Teams abre no setor certo
    assert destino("/t/contratos/contestacoes?setor=zeladoria") == (308, "/t/comando/contestacoes?setor=zeladoria")
    assert destino("/t/contratos/contestacoes/a1/card") == (308, "/t/comando/contestacoes/a1/card")
    assert destino("/t/contratos/previa") == (308, "/t/comando/visao-do-contrato")
    assert destino("/t/contratos/acessos") == (308, "/t/base/acessos-clientes")
    # 308: o formulário de uma aba que ficou aberta no endereço antigo chega à tela nova com o método e o corpo
    assert destino("/t/contratos/acessos", "post") == (308, "/t/base/acessos-clientes")
    assert destino("/t/contratos/contestacoes/a1/pegar", "post") == (308, "/t/comando/contestacoes/a1/pegar")
    # o que não tem sucessora (os avisos de "em construção") leva ao Início, sem 404
    for sem_sucessora in ("/t/contratos/clientes", "/t/contratos/onboarding", "/t/contratos/portal", "/t/contratos/"):
        assert destino(sem_sucessora) == (302, "/"), sem_sucessora
    assert logado.get("/t/comando/visao-do-contrato").status_code == 200


def test_a_marca_do_setor_na_tela_antiga_vale_na_nova():
    decisoes = [{"setor_id": 7, "tela": "contratos/contestacoes", "liberada": True, "decidida_em": "2026-10-13T12:00:00+00:00"},
                {"setor_id": 7, "tela": "contratos/acessos", "liberada": True, "decidida_em": "2026-10-14T12:00:00+00:00"},
                {"setor_id": 8, "tela": "contratos/previa", "liberada": True, "decidida_em": "2026-11-12T12:00:00+00:00"},
                # a decisão mais nova ganha, com o nome antigo ou com o novo
                {"setor_id": 9, "tela": "contratos/contestacoes", "liberada": True, "decidida_em": "2026-10-13T12:00:00+00:00"},
                {"setor_id": 9, "tela": "comando/contestacoes", "liberada": False, "decidida_em": "2026-11-13T12:00:00+00:00"}]
    assert ST.vigentes(decisoes) == {7: {"comando/contestacoes", "base/acessos-clientes"}, 8: {"comando/visao-do-contrato"}}


def test_o_portao_por_setor_nao_barra_o_endereco_antigo(app):
    """Sem isto, quem não é administrador recebia a recusa no endereço salvo (a torre não está mais no catálogo e o
    portão não achava nenhuma tela dela), em vez de chegar à tela nova, que tem o portão dela."""
    with app.test_request_context("/"):
        assert ST.pode("/t/contratos/contestacoes?setor=cos".split("?")[0], set())
        assert ST.pode("/t/contratos/acessos", {"pcm/quadro"})
        # o destino segue a régua de sempre: só quem tem a tela
        assert not ST.pode("/t/comando/contestacoes", {"pcm/quadro"})
        assert ST.pode("/t/comando/contestacoes", {"comando/contestacoes"})
        assert ST.pode("/t/comando/contestacoes/a1/card", {"comando/contestacoes"})
        assert not ST.pode("/t/base/acessos-clientes", {"base/acessos"})
        assert ST.pode("/t/base/acessos-clientes", {"base/acessos-clientes"})
