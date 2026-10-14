"""O Relatório executivo do PCM na Central de emissão (14/10/2026, Levi: "Quero trazer esses três relatórios para a
plataforma, com as mesmas métricas e parâmetros e estilos"): a cópia do js/relatorio_exec.js do painel
(nexus/pcm/relatorio_exec), na estrutura de toda a Central ("Use a mesma estrutura do print 1 para todos os
relatórios"): os três tipos no bloco "Relatório Gerencial PCM", o período e o escopo do modal do painel na coluna e a
folha na moldura da direita. E a Gerencial aberta pelo servidor ("traz a Gerencial cifrada para aparecer o MPA/MPS").
O que se prova aqui: a cópia não foi editada, o que muda ao servir, a tela, a moldura e os dados ao lado dela, a
Gerencial só com a senha e a porta do setor. Que os números são os do painel, garante a cópia; a folha se confere na
cópia de prova."""
import base64
import gzip
import json
import os
import re

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from nexus.pcm import relatorio_exec as R

URL = "/t/relatorios/pcm-executivo"


@pytest.fixture
def dados_pcm(app, tmp_path):
    g = {"geradoEm": "2026-10-14T12:00:00",
         "filtros": {"clientes": ["Cliente A", "Cliente B"], "clusters": ["Cluster 1"],
                     "usinas": ["Cliente A - Usina X - SP", "Cliente A - Usina Y - MG", "Cliente B - Usina Z - BA"]},
         "tarefas": [{"os": 1, "cliente": "Cliente A", "usina": "Cliente A - Usina X - SP", "tipo": "Corretiva",
                      "estado": "Aberta", "aberta": True}]}
    bd = {"semana_ativa": "2026-W42", "semanas": [{"week": "2026-W42", "rows": [{"os_id": 1, "dia": "Segunda-feira"}]}]}
    cf = {"geradoEm": "2026-10-14T11:00:00", "clientes": []}
    for nome, conteudo in (("g.json", g), ("bd.json", bd), ("cf.json", cf)):
        (tmp_path / nome).write_text(json.dumps(conteudo), encoding="utf-8")
    app.config.update(NEXUS_PCM_GESTAO_FONTE=str(tmp_path / "g.json"), NEXUS_PCM_FONTE=str(tmp_path / "bd.json"),
                      NEXUS_PCM_CONFIABILIDADE_FONTE=str(tmp_path / "cf.json"))
    return g


def _cifrar(dados: dict, senha: str) -> dict:
    """Um mpas.json no formato do painel (gerar_mpas_json.py): AES-GCM + PBKDF2-SHA256."""
    salt, iv = os.urandom(16), os.urandom(12)
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=1000).derive(senha.encode())
    b = lambda x: base64.b64encode(x).decode()          # noqa: E731
    return {"cifrado": True, "iter": 1000, "salt": b(salt), "iv": b(iv),
            "ct": b(AESGCM(chave).encrypt(iv, json.dumps(dados).encode(), None)), "geradoEm": dados["geradoEm"]}


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
    assert R.servido("painel_pcm.js") == R.ler_copia("painel_pcm.js")


def test_os_trechos_do_painel_ficam_no_painel_pcm_e_a_costura_nao_os_repete():
    trechos = R.ler_copia("painel_pcm.js").decode("utf-8")
    costura = R.ler_copia("apoio.js").decode("utf-8")
    for nome in ("function gpScopedTarefas", "const _cliEq", "const GPV_RX", "let MP_PACK=null, MP=null",
                 "function mpSit", "let GPV_MP", "function gpvMpNorm", "function gpvFilaLinhas", "const gpvHoje"):
        assert nome in trechos, nome
        assert nome not in costura, f"{nome} declarado duas vezes quebra o JS da moldura"
    # o que a costura põe: o login de administrador, a Gestão PCM, a Gerencial e a partida pela Central
    assert "var S = { isAdmin: true" in costura and "var GESTAO_DB = null" in costura
    assert "ler('gerencial.json')" in costura and "GPV_MP.estado = 'ok'" in costura and "rexGerar()" in costura


def test_a_tela_tem_os_tres_tipos_o_periodo_e_o_escopo_do_painel(logado, dados_pcm):
    html = logado.get(URL).get_data(as_text=True)
    assert "Relatório Gerencial PCM" in html and "Relatórios Padrão PCM" in html
    for tipo in ("interno", "cliente", "semana"):
        assert f'href="/t/relatorios/pcm-executivo?tipo={tipo}"' in html
    assert re.search(r'class="rp-tipo on" data-relatorio="pcm-executivo" href="/t/relatorios/pcm-executivo\?tipo=interno"',
                     html)
    for k, rotulo in R.PRESETS:
        assert f'data-p="{k}" aria-pressed="false">{rotulo}</button>' in html
    assert 'id="rx-de" name="de"' in html and 'id="rx-ate" name="ate"' in html
    assert "<option >Cliente A</option>" in html and "<option >Cluster 1</option>" in html
    assert html.count("Cliente A - Usina") == 2 and 'name="usi" multiple size="7"' in html
    assert 'name="semprev" value="1"' in html and "criadas no período" in html
    assert "A folha aparece aqui." in html and 'id="rp-folha"' not in html          # só gera quando pede
    # a Abertura da Semana não tem período (no painel ela usa a semana mais recente da programação)
    html = logado.get(URL + "?tipo=semana").get_data(as_text=True)
    assert 'id="rx-de"' not in html and 'name="semprev"' not in html and "o período não" in html


def test_gerar_poe_na_moldura_a_escolha_inteira(logado, dados_pcm):
    q = ("?tipo=cliente&de=2026-10-06&ate=2026-10-12&cli=Cliente+A&clu=Cluster+1&usi=Cliente+A+-+Usina+X+-+SP"
         "&usi=Cliente+A+-+Usina+Y+-+MG&semprev=1&gerar=1")
    html = logado.get(URL + q).get_data(as_text=True)
    src = re.search(r'<iframe id="rp-folha" title="Cliente"\s+src="([^"]+)"', html).group(1).replace("&amp;", "&")
    assert src.startswith("/t/relatorios/pcm-executivo/painel/?tipo=cliente&de=2026-10-06&ate=2026-10-12")
    assert "cli=Cliente+A&clu=Cluster+1" in src and src.count("usi=") == 2 and src.endswith("&semprev=1&gerar=1")
    assert 'data-espera="aviso" data-margem=".rex-a4"' in html
    assert "Cliente · 06/10/2026 a 12/10/2026 · Cliente A · Cluster 1 · 2 usina(s)" in html
    assert "aba=1&amp;tema=" in html and "Abrir em nova aba" in html
    # a escolha volta marcada na coluna
    assert "<option selected>Cliente A</option>" in html and "<option selected>Cliente A - Usina Y - MG</option>" in html
    # a Abertura da Semana leva só o escopo
    html = logado.get(URL + "?tipo=semana&de=2026-10-06&ate=2026-10-12&semprev=1&gerar=1").get_data(as_text=True)
    src = re.search(r'id="rp-folha" title="Abertura da Semana"\s+src="([^"]+)"', html).group(1).replace("&amp;", "&")
    assert src == "/t/relatorios/pcm-executivo/painel/?tipo=semana&gerar=1"


def test_periodo_invertido_nao_gera(logado, dados_pcm):
    html = logado.get(URL + "?tipo=interno&de=2026-10-12&ate=2026-10-06&gerar=1").get_data(as_text=True)
    assert 'id="rp-folha"' not in html and "Confira o período: o início vem antes do fim." in html


def test_o_documento_da_moldura_nos_tres_modos(logado):
    corpo = logado.get(URL + "/painel/?tema=claro").get_data(as_text=True)
    assert 'id="rx-gerar"' in corpo and 'class="l-logo"' in corpo and '<body class="">' in corpo and "#f5f7fb" in corpo
    # a costura e os trechos antes da cópia
    assert corpo.index("painel_pcm.js?v=") < corpo.index("apoio.js?v=") < corpo.index("relatorio_exec.js?v=")
    assert '<body class="rx-previa">' in logado.get(URL + "/painel/?tipo=interno&gerar=1").get_data(as_text=True)
    assert '<body class="rx-aba">' in logado.get(URL + "/painel/?gerar=1&aba=1").get_data(as_text=True)
    # sem a barra, volta com a escolha inteira (o endereço relativo dos arquivos precisa dela)
    r = logado.get(URL + "/painel?tipo=interno&usi=A&usi=B&gerar=1")
    assert r.status_code == 308 and r.headers["Location"].endswith("/painel/?tipo=interno&usi=A&usi=B&gerar=1")


def test_os_arquivos_e_os_dados_ao_lado_da_moldura(logado, dados_pcm):
    r = logado.get(URL + "/painel/relatorio_exec.js")
    assert r.status_code == 200 and r.mimetype == "application/javascript" and "&#128196;" not in r.get_data(as_text=True)
    assert logado.get(URL + "/painel/painel_pcm.js").mimetype == "application/javascript"
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


def test_a_gerencial_sai_aberta_so_com_a_senha_e_so_o_que_a_fila_le(app, logado, tmp_path):
    r = logado.get(URL + "/painel/gerencial.json")
    assert r.status_code == 503 and r.get_json() == {"erro": "sem_chave"}       # sem a senha: como o painel sem ela
    ger = {"geradoEm": "2026-10-14T12:00:00Z", "manut": [{"tipo": "MPA", "os": "10", "usina": "Cliente A – Usina X"}],
           "bd": {"10": {"fin": 0, "total": 3, "tasks": [{"prog": "2026-10-01"}]}}, "compras": {"clusters": []}}
    (tmp_path / "mpas.json").write_text(json.dumps(_cifrar(ger, "senha-de-teste")), encoding="utf-8")
    app.config.update(NEXUS_PCM_MPAS_FONTE=str(tmp_path / "mpas.json"), NEXUS_PCM_MPAS_SENHA="outra-senha")
    r = logado.get(URL + "/painel/gerencial.json")
    assert r.status_code == 503 and "não abriu" in r.get_json()["erro"]
    app.config["NEXUS_PCM_MPAS_SENHA"] = "senha-de-teste"
    r = logado.get(URL + "/painel/gerencial.json")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    assert r.get_json() == {"geradoEm": ger["geradoEm"], "manut": ger["manut"], "bd": ger["bd"]}   # sem as compras


def test_o_relatorio_executivo_e_do_setor_pcm(app, logado):
    from nexus.torres.relatorios import TORRE
    tela = TORRE.tela("pcm-executivo")
    assert tela.do_setor == "PCM" and tela.dentro_de == "central"
    assert 'href="/t/relatorios/pcm-executivo?tipo=interno"' in logado.get("/t/relatorios/central").get_data(as_text=True)
