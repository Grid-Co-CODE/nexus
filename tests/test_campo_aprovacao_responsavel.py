"""A Aprovação de OS por responsável da UFV (Levi, 18/10/2026: "está por região e gestor de contrato quero apenas por
responsável da UFV, quando abrir aparece uma lista das usinas que tem OSs não concluídas, ao clicar na linha aparece o
mesmo card que aparece ao clicar na OS do histórico de OS do OS Creator Web"; "Está demorando muito para carregar").

As decisões dele no mesmo dia: só as OS esperando aprovação (a fila de verificação do Fracttal); a usina abre as OS dela
e a OS abre o card do OS Creator; aprovar é o Concluir do card (quem o Fracttal deixar, como no OS Creator Web); os
indicadores ficam, contados nas usinas do responsável escolhido. Fracttal e banco falsos (o `fila` da Aprovação), com o
Responsável O&M de cada usina na ficha: a Usina A (SP 01) é do Ciclano Chefe (91), a Usina C (SC 01) do Beltrano
Supervisor (90)."""
import re

import pytest
from test_campo_aprovacao_supervisor import _sessao_nexus, fila  # noqa: F401  (fila é fixture)
from test_campo_visao import _aba

from nexus.campo import aprovacao, regras_app, visao


@pytest.fixture
def fila_resp(fila):  # noqa: F811
    _aba(fila.api, "cadastro_nexus", "usinas", [
        {"usina_id": 1, "nome": "Usina A", "status": "OPERAÇÃO", "equipe_id": 10, "data_mobilizacao": "2025-01-01",
         "uf": "SP", "gestor_contrato_id": 90, "responsavel_om_id": 91, "cliente_id": 1},
        {"usina_id": 3, "nome": "Usina C", "status": "OPERAÇÃO", "equipe_id": 20, "data_mobilizacao": "2025-01-01",
         "uf": "SC", "gestor_contrato_id": 91, "responsavel_om_id": 90, "cliente_id": 1}])
    _aba(fila.api, "cadastro_nexus", "clientes", [{"cliente_id": 1, "nome": "Thopen"}])
    visao.limpar()
    return fila


def _usinas(html):
    """As usinas da lista, na ordem da tela."""
    return re.findall(r'<details class="ap-usina[^"]*">\s*<summary[^>]*>\s*<span class="ap-u-nome"><b>([^<]+)</b>', html)


def test_a_lista_e_das_usinas_com_as_os_esperando(fila_resp, logado):
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert _usinas(html) == ["Usina A", "Usina C"]                 # a que tem OS parada há mais tempo primeiro
    for os_ in (15002, 15088, 15102, 16001):
        assert f'data-wo="{os_}"' in html
    # dentro da usina, a OS mais antiga primeiro
    usina_a = html.split('<span class="ap-u-nome"><b>Usina A</b>')[1].split("</details>")[0]
    assert re.findall(r'data-folio="(\d+)"', usina_a) == ["15002", "15088", "15102"]
    # só o filtro do responsável: nada de região de campo, gestor de contrato, equipe nem os cartões de antes
    assert 'name="responsavel"' in html
    for velho in ('name="regiao_campo"', 'name="gestor"', 'name="equipe"', 'class="cn-equipes"', "Por gestor de contrato",
                  "Por região de campo"):
        assert velho not in html, velho


def test_o_filtro_e_o_responsavel_da_usina_e_os_numeros_sao_os_dele(fila_resp, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=Beltrano+Supervisor").get_data(as_text=True)
    assert _usinas(html) == ["Usina C"] and 'data-wo="16001"' in html and 'data-wo="15088"' not in html
    assert re.search(r'Esperando aprovação</span>\s*<span class="v">1<small>OS</small>', html)
    assert '<option value="Beltrano Supervisor" selected>' in html
    todos = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert _usinas(todos) == ["Usina A", "Usina C"]
    assert re.search(r'Esperando aprovação</span>\s*<span class="v">4<small>OS</small>', todos)


def test_o_responsavel_do_login_ja_vem_no_filtro(fila_resp, cliente):
    # quem entrou pelo Fracttal e é Responsável O&M (a pessoa 91 na ficha da Usina A) abre nas usinas dele
    _sessao_nexus(cliente, papel={"pessoa_id": 91, "nome": "Ciclano Chefe", "papel": "gestor", "gestor": "Ciclano Chefe"})
    cliente.get("/t/campo/aprovacao?responsavel=*")               # nos testes a releitura roda na hora
    html = cliente.get("/t/campo/aprovacao").get_data(as_text=True)
    assert '<option value="Ciclano Chefe" selected>' in html and _usinas(html) == ["Usina A"]


def test_a_os_abre_o_card_do_os_creator(fila_resp, logado):
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    linha = re.search(r'<tr class="ap-os"[^>]*data-wo="15088"[^>]*>', html).group(0)
    assert 'data-folio="15088"' in linha and 'tabindex="0"' in linha
    assert "window.NexusOsCard" in html and "NexusOsCard.abrir(" in html and "'Em Verificação'" in html
    # aprovar é o Concluir do card: o botão Aprovar do Nexus saiu da tela
    assert "Aprovar a OS" not in html and "/os/_nexus/aprovacao/" not in html
    # o porquê do grupo fica no selo da OS (a regra do App, no mouse)
    selo = re.search(r'<tr class="ap-os"[^>]*data-wo="15088".*?</tr>', html, re.S).group(0)
    assert "Precisa do seu olho" in selo and "Nota do registro 71%" in selo and "Já foi devolvida" in selo


def test_conferir_tira_da_fila_so_o_que_o_fracttal_confirma(fila_resp, logado):
    """Fechado o card com mudança (o Concluir aprovou), a tela pede ao Nexus para conferir: só sai da fila guardada a OS
    que o Fracttal já não tem em verificação (1 pedido de leitura). Ninguém esconde OS da fila (o porquê de a rota
    /tirar ter saído em 08/10)."""
    logado.get("/t/campo/aprovacao")
    r = logado.post("/t/campo/aprovacao/15102/conferir")
    assert r.status_code == 200 and r.get_json() == {"saiu": False}       # o Fracttal ainda tem a OS em verificação
    assert aprovacao.os_na_fila(15102)
    fila_resp.linhas = [w for w in fila_resp.linhas if w["id_work_order"] != 15102]    # o Concluir do card aprovou
    r = logado.post("/t/campo/aprovacao/15102/conferir")
    assert r.get_json() == {"saiu": True} and aprovacao.os_na_fila(15102) is None
    assert 'data-wo="15102"' not in logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert logado.post("/t/campo/aprovacao/15088/conferir", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert logado.post("/t/campo/aprovacao/77777/conferir").get_json() == {"saiu": True}      # já não está na fila


def test_a_visita_nao_refaz_a_conta_da_fila(fila_resp, logado, monkeypatch):
    """"Está demorando muito para carregar": a conta das regras do App sobre a fila inteira é feita uma vez por fila
    lida; o filtro do responsável é feito sobre ela, na hora."""
    from nexus.campo import leitura
    logado.get("/t/campo/aprovacao")
    contas = []
    original = regras_app._fila_supervisao
    monkeypatch.setattr(regras_app, "_fila_supervisao", lambda *a, **k: contas.append(1) or original(*a, **k))
    monkeypatch.setattr(leitura, "TTL_S", 0)                    # a cópia de 5 min de antes venceria a cada visita
    for q in ("", "?responsavel=Beltrano+Supervisor", "?responsavel=Ciclano+Chefe", "?responsavel=*&balde=olho"):
        assert logado.get("/t/campo/aprovacao" + q).status_code == 200
    assert contas == []


def test_o_csv_e_do_responsavel(fila_resp, logado):
    r = logado.get("/t/campo/aprovacao?responsavel=Ciclano+Chefe&csv=1")
    texto = r.get_data(as_text=True)
    cab = texto.splitlines()[0].lstrip("﻿")
    assert cab.startswith("OS;Dias esperando;Criação da OS;Data fim;Responsável O&M;Usina;Cliente;Técnicos")
    assert "Região de campo" not in cab and "Gestor de contrato" not in cab and "Quem aprova" not in cab
    assert "15088;8;31/08/26;" in texto and ";Ciclano Chefe;Usina A;Thopen;" in texto and "16001" not in texto
