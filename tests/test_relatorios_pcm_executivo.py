"""O Relatório executivo do PCM na Central de emissão (14/10/2026, Levi: "Quero trazer esses três relatórios para a
plataforma, com as mesmas métricas e parâmetros e estilos"): a cópia do js/relatorio_exec.js do painel numa moldura
(nexus/pcm/relatorio_exec). O que se prova aqui: a cópia não foi editada, o que muda ao servir, a moldura e os dados ao
lado dela, e a porta do setor. Que os números são os do painel, garante a cópia; a tela se confere na cópia de prova."""
import gzip
import json

import pytest

from nexus.pcm import relatorio_exec as R

URL = "/t/relatorios/pcm-executivo"


@pytest.fixture
def dados_pcm(app, tmp_path):
    g = {"geradoEm": "2026-10-14T12:00:00", "filtros": {"clientes": ["Cliente A"], "clusters": [], "usinas": []},
         "tarefas": [{"os": 1, "cliente": "Cliente A", "usina": "Cliente A - Usina X - SP", "tipo": "Corretiva",
                      "estado": "Aberta", "aberta": True}]}
    bd = {"semana_ativa": "2026-W42", "semanas": [{"week": "2026-W42", "rows": [{"os_id": 1, "dia": "Segunda-feira"}]}]}
    cf = {"geradoEm": "2026-10-14T11:00:00", "clientes": []}
    for nome, conteudo in (("g.json", g), ("bd.json", bd), ("cf.json", cf)):
        (tmp_path / nome).write_text(json.dumps(conteudo), encoding="utf-8")
    app.config.update(NEXUS_PCM_GESTAO_FONTE=str(tmp_path / "g.json"), NEXUS_PCM_FONTE=str(tmp_path / "bd.json"),
                      NEXUS_PCM_CONFIABILIDADE_FONTE=str(tmp_path / "cf.json"))
    return g


def test_a_copia_do_pcm_nao_foi_editada():
    for nome, esperado in R.COPIAS.items():
        assert R.hash_da_copia(nome) == esperado, f"{nome} mudou: é cópia do PCM (ver o CLAUDE.md da pasta)"


def test_ao_servir_saem_os_emojis_e_so_isso():
    js = R.servido("relatorio_exec.js").decode("utf-8")
    original = R.ler_copia("relatorio_exec.js").decode("utf-8")
    for emoji in ("&#128196;", "&#127970;", "&#129309;", "&#128197;", "&#128424;"):
        assert emoji in original and emoji not in js
    assert "Voltar ao painel" not in js and "&#8592; Voltar" in js
    # fora as trocas, o arquivo é o mesmo
    for de, para in R.TROCAS_JS:
        original = original.replace(de, para)
    assert js == original
    assert R.servido("relatorio_exec.css") == R.ler_copia("relatorio_exec.css")


def test_a_tela_traz_a_moldura_com_o_tema(logado):
    html = logado.get(URL).get_data(as_text=True)
    assert 'class="rp-moldura"' in html and 'src="/t/relatorios/pcm-executivo/painel/?tema=' in html
    painel = logado.get(URL + "/painel/?tema=claro")
    corpo = painel.get_data(as_text=True)
    assert painel.status_code == 200 and 'id="rx-gerar"' in corpo and 'class="l-logo"' in corpo
    assert 'src="apoio.js?v=' in corpo and 'src="relatorio_exec.js?v=' in corpo and "#f5f7fb" in corpo
    assert corpo.index("apoio.js") < corpo.index("relatorio_exec.js?v=")       # a costura antes da cópia
    assert logado.get(URL + "/painel").status_code == 308                       # o endereço relativo precisa da barra


def test_os_arquivos_e_os_dados_ao_lado_da_moldura(logado, dados_pcm):
    r = logado.get(URL + "/painel/relatorio_exec.js")
    assert r.status_code == 200 and r.mimetype == "application/javascript" and "&#128196;" not in r.get_data(as_text=True)
    assert logado.get(URL + "/painel/gpv_cel.css").mimetype == "text/css"
    r = logado.get(URL + "/painel/gestao_pcm.json", headers={"Accept-Encoding": "gzip, deflate"})
    assert r.status_code == 200 and r.headers["Content-Encoding"] == "gzip"
    assert json.loads(gzip.decompress(r.get_data()))["tarefas"][0]["os"] == 1
    r = logado.get(URL + "/painel/banco_dados.json")
    assert "Content-Encoding" not in r.headers and r.get_json()["semana_ativa"] == "2026-W42"
    assert logado.get(URL + "/painel/confiabilidade.json").get_json()["clientes"] == []
    assert logado.get(URL + "/painel/segredo.txt").status_code == 404
    assert logado.get(URL + "/painel/..%2Fapp.py").status_code == 404


def test_sem_dado_a_moldura_explica_pelo_json(logado):
    # nos testes, sem as fontes, o fonte.py não vai à rede
    r = logado.get(URL + "/painel/gestao_pcm.json")
    assert r.status_code == 503 and "erro" in r.get_json()


def test_o_relatorio_executivo_e_do_setor_pcm(app, logado):
    from nexus.torres.relatorios import TORRE
    tela = TORRE.tela("pcm-executivo")
    assert tela.do_setor == "PCM" and tela.dentro_de == "central"
    assert 'href="/t/relatorios/pcm-executivo"' in logado.get("/t/relatorios/central").get_data(as_text=True)
