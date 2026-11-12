"""O Console e a Conferência de OS da Ronda COS dentro do Nexus (12/11/2026; o dono, no protótipo do COS).

Só a moldura: o site da Ronda COS em HTTPS (o Nexus é HTTPS, e o navegador barra página HTTP dentro dele), pelo endereço
da variável ou, sem ela, o do Andamento por IP no sslip.io. Os endereços são de documentação (192.0.2.x, RFC 5737)."""
import pytest

from nexus.cadastro import setor_ids as SID
from nexus.cos import andamento as AND
from nexus.torres.cos import TORRE


@pytest.fixture
def ligada(app):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://192.0.2.10:3002", NEXUS_COS_ANDAMENTO_CHAVE="chave-de-teste")
    return app


def test_as_duas_telas_do_setor_cos_logo_depois_do_acompanhamento():
    ids = [t.id for t in TORRE.telas]
    assert ids[:4] == ["acompanhamento", "console", "monitoramento", "conferencia-os"]
    assert TORRE.tela("console").do_setor == SID.COS and TORRE.tela("conferencia-os").do_setor == SID.COS


def test_o_endereco_do_site_pela_variavel_ou_pelo_ip_do_andamento(ligada):
    assert AND.web_da_ronda(ligada.config) == "https://console.192-0-2-10.sslip.io"
    ligada.config["NEXUS_COS_WEB_URL"] = "https://console.exemplo/"
    assert AND.web_da_ronda(ligada.config) == "https://console.exemplo"
    ligada.config.update(NEXUS_COS_WEB_URL="", NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002")
    assert AND.web_da_ronda(ligada.config) == ""          # um nome, e não IP: só pela variável


def test_a_moldura_do_console_e_da_conferencia(ligada, logado):
    html = logado.get("/t/cos/console?registro=abc 1&x=2").get_data(as_text=True)
    assert 'src="https://console.192-0-2-10.sslip.io/console?registro=abc+1"' in html
    assert 'class="porta-moldura"' in html and "<h1" not in html.split('id="porta"', 1)[1].split("</div>", 1)[0]
    # o tema vai só para a origem do site
    assert 'var origem = "https://console.192-0-2-10.sslip.io";' in html and '"*"' not in html.split("var origem", 1)[1]
    html = logado.get("/t/cos/conferencia-os").get_data(as_text=True)
    assert 'src="https://console.192-0-2-10.sslip.io/conferencia-os"' in html and "Conferência de OS" in html


def test_sem_o_endereco_a_tela_diz_e_nao_abre_moldura(app, logado):
    html = logado.get("/t/cos/console").get_data(as_text=True)
    assert "ainda não ligado neste servidor" in html and "cos-ronda-moldura" not in html
