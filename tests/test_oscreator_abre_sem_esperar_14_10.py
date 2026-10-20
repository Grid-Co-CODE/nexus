"""O OS Creator abre sem esperar o Fracttal (14/10/2026, Levi: "quando clico no OS Creator, fica carregando por um bom
tempo"). A tela inicial esperava o selo "N atribuídas a você" (um pedido ao Fracttal, até 45 s com ele lento) e cada
abertura da Performance pedia de novo os planos e as subtarefas; com algumas pessoas juntas, as threads do Nexus ficavam
todas presas. Provas: a tela inicial sai sem pedir nada ao Fracttal e o navegador pede o selo depois (/api/selo, 2 min
por pessoa); a contagem das subtarefas fica 6 h na memória; erro não fica guardado. Nada vai à rede."""
import sys

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import lancador, perf_web, rotas  # noqa: E402
from test_oscreator_desempenho import _cliente, _memoria_limpa  # noqa: E402,F401  (fixture)


def test_a_tela_inicial_nao_pede_nada_ao_fracttal_e_o_selo_vem_depois(monkeypatch):
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: pytest.fail("a tela inicial não pode esperar o Fracttal"))
    h = _cliente().get("/os/").get_data(as_text=True)
    assert "data-selo" in h and "hidden>" in h.split("data-selo", 1)[1][:160]
    assert "fetch('/os/api/selo'" in h


def test_o_selo_vem_da_api_uma_vez_a_cada_2_min_e_a_tela_seguinte_ja_o_traz(monkeypatch):
    vezes = []
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: vezes.append(1) or 3)
    c = _cliente()
    for _ in range(2):
        assert c.get("/os/api/selo").get_json() == {"selo": lancador.texto_selo(3)}
    assert len(vezes) == 1
    h = c.get("/os/").get_data(as_text=True)
    assert lancador.texto_selo(3) in h and "hidden>" not in h.split("data-selo", 1)[1][:160]
    assert len(vezes) == 1                                                     # a tela não pediu de novo


def test_selo_com_o_fracttal_fora_e_vazio_e_nao_fica_guardado(monkeypatch):
    def fora():
        raise api.FracttalError("Fracttal lento")
    monkeypatch.setattr(api, "contar_minhas_analises", fora)
    monkeypatch.setattr(rotas.sessao, "morta", lambda: False)
    c = _cliente()
    assert c.get("/os/api/selo").get_json() == {"selo": ""}
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 2)
    assert c.get("/os/api/selo").get_json() == {"selo": lancador.texto_selo(2)}


def _selo_no_node(html: str, status: int, corpo: dict) -> dict:
    """Roda no node o script do selo da tela inicial, com a resposta do /os/api/selo; devolve onde a página foi parar e
    como o selo ficou."""
    import json
    import re
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    script = next(s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "/os/api/selo" in s)
    js = """
    const [script, status, corpo] = [process.argv[1], Number(process.argv[2]), JSON.parse(process.argv[3])];
    const tag = {hidden: true, textContent: ''};
    globalThis.document = {querySelector: s => s === '[data-selo]' ? tag : null};
    globalThis.location = {pathname: '/os/', search: '', href: ''};
    globalThis.fetch = () => Promise.resolve({status, ok: status >= 200 && status < 300,
                                              json: () => Promise.resolve(corpo)});
    eval(script);
    setTimeout(() => console.log(JSON.stringify({href: location.href, hidden: tag.hidden, selo: tag.textContent})), 50);
    """
    r = subprocess.run(["node", "-e", js, script, str(status), json.dumps(corpo)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_selo_com_a_sessao_do_fracttal_caida_leva_a_pessoa_ao_login(monkeypatch):
    """Até 14/10 a tela inicial pedia o selo ao Fracttal e, com a sessão dele caída, voltava ao login com o aviso. Com o
    selo depois da tela (/api/selo), o 401 dele era ignorado: a pessoa ficava na tela inicial e só ia ao login no clique
    seguinte (achado pelos testes do oem, 20/10/2026). O fetch do selo faz como as outras telas do clone (acomp.js): 401
    com "login" leva ao /os/login, que mostra o aviso (no Nexus, a ponte já encerrou a sessão e o portão leva ao Entrar)."""
    def caiu():
        api._clear_jwt()                                    # o _rpc_call faz isto ao ver USER_NOT_LOGIN
        raise api.SessionExpired("USER_NOT_LOGIN")
    monkeypatch.setattr(api, "contar_minhas_analises", caiu)
    c = _cliente()
    h = c.get("/os/").get_data(as_text=True)
    r = c.get("/os/api/selo")
    assert r.status_code == 401 and r.get_json()["login"] is True
    assert _selo_no_node(h, r.status_code, r.get_json()) == {"href": "/os/login?next=%2Fos%2F", "hidden": True,
                                                             "selo": ""}
    assert c.get("/os/").status_code == 302                                    # a sessão do clone saiu junto


def test_selo_que_chega_aparece_e_a_pessoa_fica_na_tela(monkeypatch):
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 3)
    c = _cliente()
    h = c.get("/os/").get_data(as_text=True)
    r = c.get("/os/api/selo")
    assert _selo_no_node(h, r.status_code, r.get_json()) == {"href": "", "hidden": False,
                                                             "selo": lancador.texto_selo(3)}


def test_as_contagens_da_performance_ficam_6_h_na_memoria(monkeypatch):
    vezes = []
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: [])
    monkeypatch.setattr(perf_web, "contar_subtarefas", lambda assets: vezes.append(1) or {"Limpeza": ["a", "b"]})
    c = _cliente()
    for _ in range(3):
        assert c.get("/os/api/performance/contagens").get_json() == {"contagens": {"Limpeza": ["a", "b"]}}
    assert len(vezes) == 1 and rotas.CONTAGENS_TTL_S == 6 * 3600
