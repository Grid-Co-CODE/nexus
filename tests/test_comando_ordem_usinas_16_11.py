"""A ordem do Comando e a Usinas na Usinas 360° (16/11/2026).

Levi: "Ordem comando 1 - Caixa de entrada 2 - Usina 3 - Visão de contrato 4 - Metas do book 5 - Contestações 6 - Nexus
insights" e, logo depois, "Usinas sai de comando e vai para Usinas 360 abaixo de Visão do responsável!".

O que estes testes seguram: a ordem dos itens do menu do Comando; a Usinas como 2º item da Usinas 360°, logo abaixo da
Visão do responsável, com o endereço /t/campo/usinas (a lista, o prontuário e o resto das rotas); o endereço antigo
/t/comando/usinas/... respondendo 308 com o resto do caminho e o filtro; a marca "comando/usinas" de um setor valendo para
"campo/usinas"; e o menu abrindo a Usinas 360° (e não o Comando) quando a Usinas está aberta."""
import re

from nexus.auth import setor_telas as ST
from nexus.torres import descobrir_torres, montar_menu


def test_a_ordem_do_comando_e_a_usinas_na_usinas_360():
    torres = {t.id: t for t in descobrir_torres()}
    menu = {m["id"]: [t["nome"] for t in m["telas"]] for m in montar_menu(list(torres.values()), None)}
    # a Visão gerencial (teste) entrou em 19/11/2026 no FIM: a ordem que o Levi ditou para os outros não muda
    assert menu["comando"] == ["Caixa de entrada", "Contratos", "Metas do book", "Contestações",
                               "Nexus Insights", "Visão gerencial (teste)"]
    assert menu["campo"][:2] == ["Visão do responsável", "Usinas"]
    assert torres["comando"].tela("usinas") is None and torres["campo"].tela("usinas") is not None


def test_o_endereco_novo_e_o_antigo(logado, app):
    rotas = app.url_map.bind("localhost")
    for caminho in ("/t/campo/usinas", "/t/campo/usinas/12", "/t/campo/usinas/12/ia", "/t/campo/usinas/abrir",
                    "/t/campo/usinas/12/dossie.md", "/t/campo/usinas/dossie-da-carteira.md"):
        endpoint, _ = rotas.match(caminho, method="GET")
        assert endpoint.startswith("torre_campo_usinas."), caminho
    r = logado.get("/t/comando/usinas?cliente=Alfa&cliente=Beta")
    assert r.status_code == 308 and r.headers["Location"].endswith("/t/campo/usinas?cliente=Alfa&cliente=Beta")
    r = logado.get("/t/comando/usinas/12/dossie")
    assert r.status_code == 308 and r.headers["Location"].endswith("/t/campo/usinas/12/dossie")
    r = logado.post("/t/comando/usinas/12/ia/perguntar", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 308 and r.headers["Location"].endswith("/t/campo/usinas/12/ia/perguntar")
    r = logado.get("/t/comando/usinas/abrir?nome=Usina%20Alfa")
    assert r.status_code == 308 and r.headers["Location"].endswith("/t/campo/usinas/abrir?nome=Usina%20Alfa")


def test_a_marca_do_setor_vem_junto():
    assert ST.RENOMEADAS["comando/usinas"] == "campo/usinas"
    decisoes = [{"decidida_em": "2026-11-12T10:00:00Z", "data_id": 20261112, "setor_id": 7, "tela": "comando/usinas",
                 "liberada": True, "decidida_por_hmac": "", "origem": ""}]
    assert "campo/usinas" in ST.vigentes(decisoes)[7]


def test_o_menu_abre_a_usinas_360_na_usinas(logado, monkeypatch):
    from nexus.torres import comando as C
    monkeypatch.setattr(C, "_usinas_montadas", lambda: {"linhas": [], "avisos": [], "erro": None, "cos_ts": "",
                                                        "insights_calculando": False, "vivos": {}, "visao": {}})
    h = logado.get("/t/campo/usinas").get_data(as_text=True)
    abertas = re.findall(r'<details class="torre[^"]*" data-torre="([a-z]+)" open>', h)
    assert abertas == ["campo"]
    assert 'href="/t/campo/usinas"' in h
