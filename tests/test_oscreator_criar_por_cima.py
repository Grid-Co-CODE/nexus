"""O Criar OS do prontuário da usina por cima da tela (13/11/2026, Levi: "está jogando para uma aba nova do OS Creator,
que não dá a opção de voltar para o prontuário da usina [...] O melhor é fazer [...] que nem o Nexus Performance faz. Lá
no tempo real [...] Abre o cardzão da OS, dando um blur de fundo, e aí quando a pessoa cria a OS, ela só pode fechar o
card e já era"): a moldura do meio (/os/_nexus/criar, `ponte.criar_os`) com a tela de criação do clone dentro, com
?janela=1, ou o aviso de como entrar pelo Fracttal."""
import json
import shutil
import subprocess

import pytest
from test_oscreator_tema_claro import _login_do_fracttal

from nexus.torres.oscreator import ponte

DE = "/t/comando/usinas/1"


def _abrir(cliente, url, de=DE):
    return cliente.get("/os/_nexus/criar", query_string={"url": url, "de": de})


def test_sem_o_login_do_fracttal_a_moldura_diz_como_entrar_e_volta(logado):
    h = _abrir(logado, "/os/tradicional?ativo=THPN-ALT100").get_data(as_text=True)
    assert "Para criar a OS, entre pelo Fracttal" in h and 'id="nx_cr"' not in h
    # o login do OS Creator, voltando ao prontuário de onde a pessoa saiu (o mesmo /card/voltar do card e do chamado)
    assert 'href="/os/login?next=%2Fos%2F_nexus%2Fcard%2Fvoltar%3Fde%3D%2Ft%2Fcomando%2Fusinas%2F1"' in h
    assert 'target="_top"' in h


def test_com_o_login_a_tela_de_criacao_vem_na_moldura_de_dentro_com_janela(app, logado):
    _login_do_fracttal(app, logado)
    h = _abrir(logado, "/os/tradicional?ativo=THPN-ALT100").get_data(as_text=True)
    assert '<iframe class="nx-cr" id="nx_cr" src="/os/tradicional?ativo=THPN-ALT100&amp;janela=1"' in h
    # aberta sozinha (link copiado), vira a própria tela de criação, sem a janela
    assert 'location.replace("/os/tradicional?ativo=THPN-ALT100")' in h
    # o Esc e a criação seguem para a tela do Nexus
    assert "avisar({nexusCriarOs: 1, tipo: 'fechar'})" in h
    assert "avisar({nexusCriarOs: 1, tipo: 'criada'" in h and "d.gc !== 'os-criada'" in h


def test_as_cinco_formas_do_prontuario_abrem_e_o_resto_nao(app, logado):
    from nexus.torres.comando.prontuario_dados import CRIAR_OS
    _login_do_fracttal(app, logado)
    # as duas listas andam juntas: toda forma do Criar OS do prontuário abre na janela
    assert {u for _r, _s, u, _l in CRIAR_OS} == set(ponte.CRIAR_POR_CIMA)
    for _rot, _sub, url, _leva in CRIAR_OS:
        r = _abrir(logado, url)
        assert r.status_code == 200 and f'src="{url}?janela=1"' in r.get_data(as_text=True), url
    for fora in ("/os/login", "/os/api/tradicional/criar", "/os/", "/t/comando/usinas", "https://exemplo.invalid/os/tradicional",
                 "//exemplo.invalid/os/tradicional", "/os/tradicional/../login", ""):
        assert _abrir(logado, fora).status_code == 404, fora


def test_o_ativo_torto_fica_de_fora_e_a_volta_e_do_proprio_site(app, logado):
    _login_do_fracttal(app, logado)
    h = _abrir(logado, '/os/tradicional?ativo=<script>"x').get_data(as_text=True)
    assert 'src="/os/tradicional?janela=1"' in h and "<script>\"x" not in h
    # o código com acento do Fracttal (Élis) passa
    h = _abrir(logado, "/os/solicitacao?ativo=ÉLIS-MQN100").get_data(as_text=True)
    assert 'src="/os/solicitacao?ativo=%C3%89LIS-MQN100&amp;janela=1"' in h
    h = logado.get("/os/_nexus/criar", query_string={"url": "/os/tradicional", "de": "https://exemplo.invalid/x"})
    assert "exemplo.invalid" not in h.get_data(as_text=True)


def test_o_aviso_da_janela_vale_para_as_cinco_criacoes():
    """A ponte embrulha o fetch da tela com ?janela=1: a criação de dois níveis (a solicitação à Performance e à
    Engenharia) também avisa, a inspeção avisa com o `texto` dela, e a de lote leva quantas falharam."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node não instalado")
    js = ponte._JANELA_OS.decode().removeprefix("<script>").removesuffix("</script>")
    harness = """
    const avisos = []; let resposta = null;
    globalThis.window = {fetch: async (u, o) => ({ok: true, clone() { return this; }, json: async () => resposta})};
    window.parent = {postMessage: (m, o) => avisos.push(m)};
    globalThis.location = {origin: 'https://app.gridco.com.br'};
    globalThis.document = {documentElement: {classList: {add() {}}}};
    """ + js + """
    (async () => {
      resposta = {ok: true, mensagem: 'OS 101 criada'}; await window.fetch('/os/api/tradicional/criar', {method: 'POST'});
      resposta = {ok: 1, falhas: 1, mensagem: '1 de 2'}; await window.fetch('/os/api/solicitacao/performance/criar', {method: 'POST'});
      resposta = {ok: true, texto: 'OS 9 criada com 3 subtarefas.'}; await window.fetch('/os/api/insp/criar', {method: 'POST'});
      resposta = {ok: true}; await window.fetch('/os/api/solicitacao/performance/ativos', {method: 'POST'});   // não é criação
      await new Promise(r => setTimeout(r, 20));
      process.stdout.write(JSON.stringify(avisos));
    })();
    """
    p = subprocess.run([node, "-e", harness], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == [
        {"gc": "os-criada", "mensagem": "OS 101 criada", "detalhes": [], "falhas": 0},
        {"gc": "os-criada", "mensagem": "1 de 2", "detalhes": [], "falhas": 1},
        {"gc": "os-criada", "mensagem": "OS 9 criada com 3 subtarefas.", "detalhes": [], "falhas": 0}]
