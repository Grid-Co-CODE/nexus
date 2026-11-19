"""A janela de criar OS da Sala de controle (19/11/2026, plataforma de Performance aberta dentro do Nexus).

Levi: "quando tiver deslogado do Fractal, aparecer só um pop-up só um cardzinho no meio para logar, porque ele
redireciona para uma aba do OS Creator que eu não consigo voltar para a sala de comando"; "dobre o tamanho também do card
do OS Creator quando abre"; "quando eu selecionasse um item e ele fosse reconhecido no Fractal, ele também já aparecesse
ali no topo do OS Creator"; e nos trackers, "por mais que não tenha um de para específico, ele avisa, não tem de para de
trackers para essa usina. Mas ele já abre a opção ali de criar OS".

O que estes testes seguram, nesta ordem:
- `/t/_janela/entrou`: a página em que o login aberto pela Sala numa janela própria termina (avisa a Sala e fecha), atrás
  do login de sempre, aberta para qualquer setor (não é tela de torre), e o `next` dela atravessa o Entrar;
- o Entrar que cai DENTRO da janela da Sala chama a Sala (`gcSalaEntrar`) em vez de trocar a janela de cima (rodado no
  node, com as molduras de mentira);
- o login do OS Creator que cai dentro da janela da Sala (a sessão do Fracttal do OS Creator que não existe, com o Nexus
  aberto pela Microsoft) fica nela, como um cartão, e não toma a Sala;
- o OS Creator aberto pela Sala, maior (`os-sala`, zoom de 1,5);
- os ativos que a Sala mandou e o Fracttal reconheceu, no TOPO da tela e da tabela; o que não foi achado, dito no topo
  (no plano de tracker, que não há de-para de trackers da usina; rodado no node).
Nenhum teste vai à rede; nomes e usinas são de mentira (repositório público).
"""
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import pytest

from nexus import create_app
from nexus.auth import fracttal
from nexus.torres.oscreator import ponte

from conftest import SENHA_TESTE

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

WEB = Path(ponte.RAIZ_CLONE, "os_web")
ENTROU = "/t/_janela/entrou"
NODE = shutil.which("node")


# ── 1. /t/_janela/entrou ─────────────────────────────────────────────────────────────────────────────────────────────
def test_a_janela_entrou_pede_o_login_de_sempre(cliente):
    r = cliente.get(ENTROU)
    assert r.status_code == 302 and r.headers["Location"].startswith("/entrar?next=")
    assert quote(ENTROU, safe="") in r.headers["Location"] or ENTROU in r.headers["Location"]


def test_a_janela_entrou_avisa_a_sala_e_fecha(logado):
    r = logado.get(ENTROU)
    assert r.status_code == 200 and "no-store" in r.headers.get("Cache-Control", "")
    html = r.get_data(as_text=True)
    # só fala com quem a abriu, e só se for da MESMA origem; nada vai para outro site
    assert "window.opener.location.origin === location.origin" in html
    assert 'window.opener.postMessage({gc: "nexus-entrou"}, location.origin)' in html
    assert "window.close()" in html and "Pronto, você entrou. Pode fechar esta janela." in html
    assert 'data-nexus' not in html                       # não é a casca: não tem menu nem moldura


def test_com_o_portao_de_setor_ligado_a_janela_entrou_passa(app, monkeypatch):
    """Não é tela de torre: sem estar em `setor_telas.LIVRES`, o `pode` a barraria para quem tem setor."""
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "ligado", lambda cfg: True)
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": {"performance/sala-de-controle"},
                                               "setor": {"id": 5, "nome": "Setor Qualquer"}, "erro": ""})
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, via="microsoft", ms_ate=time.time() + 3600,
                 usuario={"email": "fulano@exemplo.test", "nome": "Fulano de Tal", "perfil": ""})
    assert c.get(ENTROU).status_code == 200
    monkeypatch.setattr(ST, "LIVRES", ST.LIVRES - {"casca.janela_entrou"})
    assert c.get(ENTROU).status_code == 403


def _app(prefixo):
    cfg = {"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE}
    if prefixo:
        cfg["NEXUS_PREFIXO"] = prefixo
    a = create_app(cfg)
    a.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    return a


@pytest.mark.parametrize("prefixo", [None, "/nexus"])
def test_o_login_volta_para_a_janela_entrou(prefixo, monkeypatch):
    """O `next` que a Sala manda passa pelo `destino_seguro` do Entrar, com e sem o prefixo, no login do Fracttal e na
    senha de administrador (o da Microsoft guarda o mesmo `next` na ida e o devolve pelo mesmo `next_seguro`)."""
    monkeypatch.setattr(fracttal, "entrar", lambda app, e, s: {"email": e, "nome": "Pessoa Teste", "perfil": "",
                                                                  "cookie": ("os_sessao", "v", 3600)})
    a, base = _app(prefixo), prefixo or ""
    pagina = a.test_client().get(base + "/entrar?next=" + quote(ENTROU, safe="")).get_data(as_text=True)
    assert re.search(r'name="next" value="[^"]*/t/_janela/entrou"|next=[^"&]*_janela(/|%2F)entrou', pagina)   # o formulário leva
    r = a.test_client().post(base + "/entrar", query_string={"next": ENTROU}, data={"email": "pessoa@exemplo.test", "senha": "x"})
    assert r.status_code == 302 and r.headers["Location"] == base + ENTROU
    r = a.test_client().post(base + "/entrar", query_string={"next": ENTROU}, data={"senha": SENHA_TESTE})
    assert r.status_code == 302 and r.headers["Location"] == base + ENTROU


# ── 2. o Entrar dentro da janela da Sala ─────────────────────────────────────────────────────────────────────────────
def _script_da_moldura(html: str) -> str:
    """O trecho do <head> do Entrar que decide o que fazer dentro de moldura."""
    i = html.index("if (window.top === window.self) return;")
    ini = html.rindex("(function () {", 0, i)
    fim = html.index("})();", i) + len("})();")
    return html[ini:fim]


def test_o_entrar_dentro_da_sala_chama_a_sala_antes_de_trocar_a_janela_de_cima(cliente):
    html = cliente.get("/entrar?motivo=caiu").get_data(as_text=True)
    s = _script_da_moldura(html)
    assert s.index("gcSalaEntrar") < s.index('window.top.location.replace(nexusRota("/entrar") + "?next="')
    assert "A sessão caiu: entre de novo pelo cartão da Sala de controle." in html
    assert 'class="entrar-aviso entrar-na-sala-aviso"' in html


@pytest.mark.skipif(not NODE, reason="sem o node nesta máquina")
def test_o_entrar_dentro_da_sala_roda_no_node(cliente):
    """As molduras de mentira: o topo (a casca do Nexus), a Sala (a página da plataforma) e a janela de criar OS."""
    s = _script_da_moldura(cliente.get("/entrar?motivo=caiu").get_data(as_text=True))
    prog = r"""
const casos = {};
function roda(nome, monta) {
  const r = {trocou: null, sala: null, classe: []};
  const self = {}, topo = {location: {pathname: "/t/performance/sala-de-controle", search: "?u=1",
    replace: u => { r.trocou = u; }}};
  const sala = monta(r, topo, self);
  self.top = topo; self.self = self; self.parent = sala || topo;
  global.window = self; global.location = {origin: "https://app.exemplo.test"};
  global.nexusRota = c => c;
  global.document = {documentElement: {classList: {add: c => r.classe.push(c)}}};
  (new Function(SCRIPT))();
  casos[nome] = r;
}
// a janela da Sala: a Sala é da mesma origem e tem o gcSalaEntrar
roda("na_sala", (r, topo) => ({location: {origin: "https://app.exemplo.test"}, gcSalaEntrar: m => { r.sala = m; }}));
// a moldura de sempre (o pai é o topo): troca a janela de cima, como antes
roda("moldura_de_sempre", () => null);
// o pai é outra moldura sem a Sala: como antes
roda("sem_a_sala", () => ({location: {origin: "https://app.exemplo.test"}}));
// o pai de outra origem (o acesso dispara erro): como antes
roda("outra_origem", () => ({get location() { throw new Error("cross-origin"); }, gcSalaEntrar: () => {}}));
console.log(JSON.stringify(casos));
""".replace("SCRIPT", json.dumps(s))
    p = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr
    c = json.loads(p.stdout)
    assert c["na_sala"] == {"trocou": None, "sala": "caiu", "classe": ["entrar-na-sala"]}
    for nome in ("moldura_de_sempre", "sem_a_sala", "outra_origem"):
        assert c[nome]["sala"] is None and c[nome]["trocou"] == "/entrar?next=%2Ft%2Fperformance%2Fsala-de-controle%3Fu%3D1&motivo=caiu", nome


# ── 2b. o login do OS Creator dentro da janela da Sala ───────────────────────────────────────────────────────────────
def test_o_login_do_os_creator_na_janela_da_sala_fica_nela(logado):
    """Com o Nexus aberto pela Microsoft (ou pela senha de administrador), o OS Creator tem o login do Fracttal dele:
    sem ele, a criação de OS manda ao /os/login, e o login saía da moldura e tomava a SALA inteira (o __osTopo da ponte
    sobe até a página de baixo do Nexus, que é a Sala). Vindo da janela da Sala (`janela=1` no `next`), ele fica nela."""
    criar = "/os/performance/criar?frase=recomposicao+de+string&usina=Usina+Teste&janela=1&origem=sala-de-controle"
    html = logado.get("/os/login?next=" + quote(criar, safe="")).get_data(as_text=True)
    assert 'action="/os/login"' in html
    assert ".location.href = location.href" not in html                                  # não toma a Sala
    assert '"os-embutido", "os-janela", "os-sala"' in html                               # fica nela, maior
    fora = logado.get("/os/login?next=" + quote("/os/historico", safe="")).get_data(as_text=True)
    assert ".location.href = location.href" in fora                                     # fora da janela: como antes


# ── 3. o OS Creator aberto pela Sala, maior ──────────────────────────────────────────────────────────────────────────
def test_o_os_creator_aberto_pela_sala_e_maior():
    base = (WEB / "templates" / "base.html").read_text(encoding="utf-8")
    css = (WEB / "static" / "os.css").read_text(encoding="utf-8")
    assert "/[?&]janela=1(&|$)/.test(location.search) && /[?&]origem=sala-de-controle/.test(location.search)" in base
    assert 'h.classList.add("os-sala")' in base
    assert "html.os-sala{zoom:1.5}" in css


# ── 4. os reconhecidos no topo ───────────────────────────────────────────────────────────────────────────────────────
def test_o_aviso_do_topo_e_a_ordem_estao_na_tela():
    html = (WEB / "templates" / "perf_criar.html").read_text(encoding="utf-8")
    js = (WEB / "static" / "perf.js").read_text(encoding="utf-8")
    css = (WEB / "static" / "os.css").read_text(encoding="utf-8")
    assert html.index('<div class="os-sug-topo" id="sug_topo" hidden></div>') < html.index('<div class="os-cardf">')
    assert html.index('class="os-topo-linha"') < html.index('id="sug_topo"')
    assert "data-sug-origem=" in html
    assert "alvos = comSugeridosNoTopo(alvos, achadosIds);" in js and "avisoDoTopo(" in js
    assert ".os-sug-topo[hidden]{display:none}" in css


def _js_puro(js: str) -> str:
    ini = js.index("// ── os sugeridos no topo (19/11/2026)")
    fim = js.index("// ── fim dos sugeridos no topo")
    return js[ini:fim]


@pytest.mark.skipif(not NODE, reason="sem o node nesta máquina")
def test_os_reconhecidos_vao_ao_topo_e_o_que_falta_e_dito_no_node():
    js = _js_puro((WEB / "static" / "perf.js").read_text(encoding="utf-8"))
    prog = """
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
CODIGO
const lista = [{id: 1, label: 'A'}, {id: 2, label: 'B'}, {id: 3, label: 'C'}, {id: 4, label: 'D'}, {id: 5, label: 'E'}];
const r = {};
r.ordem = comSugeridosNoTopo(lista, [4, 2]).map(a => a.id);
r.sem = comSugeridosNoTopo(lista, []).map(a => a.id);
r.repetido = comSugeridosNoTopo(lista, [3, 3, 1]).map(a => a.id);
r.inv = avisoDoTopo(['Inversor 1.3', 'Inversor 1.4'], [], false, 'sala-de-controle');
r.trk = avisoDoTopo([], ['TRK 41'], true, 'sala-de-controle-ocorrencia');
r.falta = avisoDoTopo(['Inversor 1.3'], ['Inversor 9.9'], false, 'tempo-real');
r.nada = avisoDoTopo([], [], false, 'sala-de-controle');
r.escapa = avisoDoTopo(['<b>x</b>'], [], false, 'sala-de-controle');
console.log(JSON.stringify(r));
""".replace("CODIGO", js)
    p = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout)
    assert r["ordem"] == [4, 2, 1, 3, 5]                  # os achados na ordem em que vieram; o resto, na de sempre
    assert r["sem"] == [1, 2, 3, 4, 5] and r["repetido"] == [3, 1, 2, 4, 5]
    inv = r["inv"]
    assert inv["alerta"] is False and "Pré-selecionado pela Sala de controle: <b>Inversor 1.3, Inversor 1.4</b>" in inv["html"]
    trk = r["trk"]
    assert trk["alerta"] is True and 'Não há de-para de trackers desta usina com o Fracttal (não achei "TRK 41")' in trk["html"]
    assert "A lista abaixo já está só com as estruturas de tracker: procure o tracker e marque." in trk["html"]
    falta = r["falta"]
    assert falta["alerta"] is True and "Pré-selecionado pelo link que abriu esta tela" in falta["html"]
    assert 'Não achei "Inversor 9.9" nesta usina no Fracttal: marque à mão.' in falta["html"]
    assert r["nada"] == {"html": "", "alerta": False}
    assert "<b>x</b>" not in r["escapa"]["html"] and "&lt;b&gt;x&lt;/b&gt;" in r["escapa"]["html"]


def test_o_plano_de_tracker_ja_devolve_so_as_estruturas_de_tracker(monkeypatch):
    """A lista da tela no plano de tracker é só de estruturas de tracker (o generalizado, os conjuntos e os individuais):
    é o filtro "Estrutura de tracker" que o Levi pediu, sem filtro novo."""
    import api            # o api.py do clone (o perf_alvos chama tudo pelo `api.`)
    import perf_alvos
    monkeypatch.setattr(api, "_eh_tracker_generalizado", lambda a: bool(a.get("gen")))
    monkeypatch.setattr(api, "get_plans_for_assets", lambda ativos, guardados=False: [
        {"id_task": 7, "description": "Verificacao de tracker parado", "asset": ativos[0]}])
    ativos = [{"id": 1, "tipo": "Estrutura Trackers", "gen": True, "code": "TRK-G", "usina": "Usina Teste"},
              {"id": 2, "tipo": "Estrutura Trackers", "code": "TRK-01", "usina": "Usina Teste"},
              {"id": 3, "tipo": "Inversor", "code": "INV-1", "usina": "Usina Teste"},
              {"id": 4, "tipo": "Estação Meteorológica", "code": "ETM-1", "usina": "Usina Teste"}]
    r = perf_alvos.get_performance_alvos(ativos, "verificacao de tracker parado")
    assert r["is_tracker"] is True and "erro" not in r
    assert [a["asset"]["id"] for a in r["ativos"]] == [1, 2]                    # nem o inversor nem a estação
