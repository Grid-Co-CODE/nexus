"""As contas do clima-mapa.js (09/10/2026), rodadas no node: o zoom em volta do ponto, os limites do recorte, o enquadramento do estado,
a espera até a próxima releitura (nunca antes do cache, 60 s depois de falha), a sessão que cai (o portão manda para o Entrar), as
linhas da tabela que cabem no modo TV e a busca sem acento. A parte que mexe na página foi conferida no Chrome sem janela."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "clima-mapa.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")


def rodar(expressao):
    script = ("require(process.argv[1]); const M = globalThis.MapaRisco;"
              f"process.stdout.write(JSON.stringify({expressao}));")
    r = subprocess.run(["node", "-e", script, str(JS)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


BASE = [0, 0, 1000, 1027.3]


def test_o_zoom_da_roda_deixa_parado_o_ponto_debaixo_do_mouse():
    vb = rodar(f"M.zoomEm({BASE}, {BASE}, 600, 400, 2)")
    assert vb[2] == pytest.approx(500) and vb[3] == pytest.approx(513.65)
    # o ponto (600, 400) fica na mesma fração do recorte antes e depois
    assert (600 - vb[0]) / vb[2] == pytest.approx(0.6) and (400 - vb[1]) / vb[3] == pytest.approx(400 / 1027.3)


def test_o_zoom_tem_teto_e_chao_e_o_recorte_nao_sai_do_mapa():
    assert rodar(f"M.zoomEm({BASE}, {BASE}, 500, 500, 0.2)") == BASE              # não afasta além do recorte do servidor
    perto = rodar(f"M.zoomEm({BASE}, {BASE}, 500, 500, 1000)")
    assert perto[2] == pytest.approx(1000 / rodar("M.ZOOM_MAX"))
    fora = rodar(f"M.limitar([-400, -300, 500, 513.65], {BASE})")
    assert fora[0] == 0 and fora[1] == 0                                         # arrastado para fora, volta para dentro
    longe = rodar(f"M.limitar([900, 900, 500, 513.65], {BASE})")
    assert longe[0] + longe[2] == pytest.approx(1000) and longe[1] + longe[3] == pytest.approx(1027.3)


def test_o_clique_no_estado_enquadra_a_caixa_dele_com_folga_e_na_proporcao_do_mapa():
    vb = rodar(f"M.enquadrar([600, 500, 700, 560], {BASE})")
    assert vb[0] < 600 and vb[1] < 500 and vb[0] + vb[2] > 700 and vb[1] + vb[3] > 560
    assert vb[2] / vb[3] == pytest.approx(1000 / 1027.3)


@pytest.mark.parametrize("proxima,falhou,espera", [(605, False, 605), (3, False, 10), (99999, False, 1800), ("x", False, 60),
                                                   (605, True, 60)])
def test_a_espera_ate_reler_segue_o_cache_e_depois_de_falha_e_um_minuto(proxima, falhou, espera):
    assert rodar(f"M.proximaEspera({json.dumps(proxima)}, {json.dumps(falhou)})") == espera


@pytest.mark.parametrize("resposta,motivo", [
    ({"tipo": "opaqueredirect", "status": 0, "temMapa": False}, "sessao"),        # o portão mandou para o Entrar
    ({"tipo": "basic", "status": 401, "temMapa": False}, "sessao"),
    ({"tipo": "basic", "status": 200, "temMapa": False}, "sessao"),               # veio outra página no lugar do mapa
    ({"tipo": "basic", "status": 500, "temMapa": False}, "http"),
    ({"tipo": "basic", "status": 200, "temMapa": True}, None),
])
def test_a_sessao_que_cai_e_percebida_e_nao_vira_dado_velho_como_novo(resposta, motivo):
    assert rodar(f"M.motivoDaFalha({json.dumps(resposta)})") == motivo


def test_no_modo_tv_a_tabela_mostra_as_linhas_que_cabem_e_reserva_o_e_mais():
    assert rodar("M.quantasCabem([30, 30, 30], 100, 20)") == 3                   # cabem todas: nada de "e mais"
    assert rodar("M.quantasCabem([30, 30, 30, 30], 100, 20)") == 2               # não cabem: sobra lugar para o "e mais N"
    assert rodar("M.quantasCabem([], 100, 20)") == 0


def test_a_busca_acha_pelo_nome_sem_acento_e_sem_caixa():
    usinas = json.dumps({"1": {"n": "Usina São João"}, "2": {"n": "Usina Sapé"}, "3": {"n": "São Gonçalo 2"}})
    assert rodar(f"M.acharUsina({usinas}, 'usina sao joao')") == "1"
    assert rodar(f"M.acharUsina({usinas}, 'Sao Gon')") == "3"                    # começo do nome
    assert rodar(f"M.acharUsina({usinas}, 'sape')") == "2"                       # parte do nome
    assert rodar(f"M.acharUsina({usinas}, 'inexistente')") is None and rodar(f"M.acharUsina({usinas}, '  ')") is None
