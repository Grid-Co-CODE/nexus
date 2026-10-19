"""O que cada setor vê no Nexus (Base → Acessos, 12/10/2026). Levi: "gostaria de uma seção no BASE > ACESSOS onde eu possa
controlar o que cada pessoa de setor pode ver ao logar no Nexus. A que não tiver setor vai aparecer a mensagem 'Sem setor,
fale com o responsável' [...] Criarei um setor chamado 'Administrador' onde será liberado todas as seções para essas
contas! Exclua a parte de cadeiras já que os setores irão substituir!". E depois, no mesmo dia: "não acho legal deixar
como setores pois eu por exemplo sou da performance mas também sou administrador" (administrador é a lista, não setor).

Provas: a matriz vale pela última decisão; sem setor, só a mensagem (página e dados); o setor vê só as telas marcadas
(menu, Início, a tela, as sub-rotas da torre, o OS Creator); setor nenhum dá administrador, e o administrador que tem
setor vê tudo; a tela grava só o que mudou, recusa o setor excluído e a tela desconhecida, e só administrador grava; banco
ilegível
não vira "sem setor"; sem a NEXUS_PESSOA_HMAC ou com NEXUS_ACESSO_POR_SETOR=0, todos veem tudo; e o livro está no
catálogo, sem nada pessoal. O banco é o falso do test_campo_visao; nada vai ao banco de verdade nem ao Fracttal."""
import re
import threading
import time

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.auth import acessos as A
from nexus.auth import setor_telas as ST
from nexus.cadastro import setores as S
from nexus.dados import catalogo

URL = "/t/base/acessos"
BASE = "http://pg.falso"
ANA = "ana@exemplo.test"          # setor Performance
BIA = "bia@exemplo.test"          # setor chamado "Administrador": um setor como os outros
CAIO = "caio@exemplo.test"        # sem setor
DADOS = {"Sec-Fetch-Dest": "empty"}


@pytest.fixture(autouse=True)
def _sem_copias():
    S._CACHE.clear()
    ST.limpar()
    yield
    S._CACHE.clear()
    ST.limpar()


@pytest.fixture
def setores(app, banco):
    """Performance (1) e Administrador (2) no banco falso, com a Ana e a Bia; o portão ligado, como fora dos testes."""
    cfg = app.config
    S.criar("Performance", cfg, BASE, banco)
    S.criar("Administrador", cfg, BASE, banco)
    S.definir([{"id": 701, "email": ANA, "ficha": None, "por": ""}], 1, cfg, BASE, banco)
    S.definir([{"id": 702, "email": BIA, "ficha": None, "por": ""}], 2, cfg, BASE, banco)
    app.config["NEXUS_ACESSO_POR_SETOR"] = "1"
    return banco


def _como(app, email):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, False
        s["usuario"] = {"email": email, "nome": "Pessoa Teste", "perfil": ""}
    return c


def _codigo(c) -> str:
    return re.search(r'name="codigo" value="([^"]+)"', c.get(URL).get_data(as_text=True)).group(1)


def _salvar(c, setor, telas, codigo=None):
    return c.post(URL, data={"codigo": codigo if codigo is not None else _codigo(c), "acao": "telas_setor",
                             "setor": str(setor), "tela": telas})


def _linhas(banco):
    return banco.linhas(ST.LIVRO, ST.ABA)


# ── as regras, sem servidor ───────────────────────────────────────────────────────────────────────────────────────


def test_a_matriz_vale_pela_ultima_decisao():
    d = [{"decidida_em": "2026-10-12T10:00:00Z", "setor_id": 1, "tela": "cos/mesa", "liberada": True},
         {"decidida_em": "2026-10-12T09:00:00Z", "setor_id": 1, "tela": "cos/mesa", "liberada": False},   # mais antiga
         {"decidida_em": "2026-10-12T10:00:00Z", "setor_id": 1, "tela": "pcm/quadro", "liberada": True},
         {"decidida_em": "2026-10-12T11:00:00Z", "setor_id": 1, "tela": "pcm/quadro", "liberada": False},  # fechada
         {"decidida_em": "2026-10-12T10:00:00Z", "setor_id": 3, "tela": "os/inicio", "liberada": True}]
    assert ST.vigentes(d) == {1: {"cos/mesa"}, 3: {"os/inicio"}}


def test_o_setor_de_cada_codigo_e_a_ultima_decisao_da_pessoa():
    d = [{"decidida_em": "2026-10-12T10:00:00Z", "fracttal_id": 1, "pessoa_hmac": "a", "setor_id": 2},
         {"decidida_em": "2026-10-12T11:00:00Z", "fracttal_id": 1, "pessoa_hmac": "a", "setor_id": None},  # tirada
         {"decidida_em": "2026-10-12T10:00:00Z", "fracttal_id": 2, "pessoa_hmac": "b", "setor_id": 3},
         {"decidida_em": "2026-10-12T09:00:00Z", "fracttal_id": 3, "pessoa_hmac": "b", "setor_id": 4}]     # mais velha
    assert ST.setor_de_cada_codigo(d) == {"a": None, "b": 3}


def test_o_caminho_segue_a_tela_a_torre_e_o_os_creator(app):
    telas = {"cos/mesa", "performance/clima/mapa"}
    with app.test_request_context("/"):
        assert ST.pode("/t/cos/mesa", telas) and not ST.pode("/t/cos/ocorrencias", telas)
        assert ST.pode("/t/cos/mesa/dados.json", telas)                  # a sub-rota da tela segue a tela
        assert ST.pode("/t/cos/qualquer-dado", telas)                    # o resto da torre: quem tem uma tela dela
        assert not ST.pode("/t/pcm/qualquer-dado", telas)
        assert ST.pode("/t/performance/clima/mapa", telas)               # o id com barra: a mais longa que casa
        assert not ST.pode("/t/performance/clima", telas)
        assert not ST.pode("/os/", telas) and ST.pode("/os/", telas | {"os/inicio"})   # o OS Creator é a torre OS
        assert ST.pode("/os/_nexus/card/1", telas)                       # as ações do Campo e do HSEQ, não
        assert ST.pode("/", telas) and ST.pode("/tema", telas)


def test_o_estado_do_portao(app):
    cfg = dict(app.config)
    assert ST.estado(cfg) == "desligado"                                 # nos testes, só quando pedido
    assert ST.estado(dict(cfg, NEXUS_ACESSO_POR_SETOR="1")) == "sem_chave"
    assert ST.estado(dict(cfg, NEXUS_ACESSO_POR_SETOR="1", NEXUS_PESSOA_HMAC="k")) == "ligado"
    assert ST.estado(dict(cfg, NEXUS_ACESSO_POR_SETOR="0", NEXUS_PESSOA_HMAC="k")) == "desligado"
    assert ST.estado(dict(cfg, TESTING=False, NEXUS_PESSOA_HMAC="k")) == "ligado"   # fora dos testes, ligado


# ── quem entra ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_sem_setor_so_a_mensagem(app, setores):
    c = _como(app, CAIO)
    for caminho in ("/", "/t/cos/mesa", "/t/base/acessos"):
        r = c.get(caminho)
        assert r.status_code == 403, caminho
        html = r.get_data(as_text=True)
        assert "Sem setor, fale com o responsável." in html
        assert 'data-torre="' not in html                                # o menu vem vazio
    r = c.get("/t/campo/aprovacao", headers=DADOS)
    assert r.status_code == 403 and r.get_json() == {"ok": False, "erro": "Sem setor, fale com o responsável."}
    # o que abre sem setor: sair, o tema, a saúde e os arquivos da página
    assert c.get("/static/nexus.css").status_code == 200
    assert c.post("/tema", data={"tema": "claro", "voltar": "/"}).status_code == 302
    assert c.get("/saude").status_code == 200
    assert c.get("/sair").status_code == 302


def test_o_setor_ve_so_as_telas_marcadas(app, setores, logado):
    assert _salvar(logado, 1, ["cos/mesa", "os/inicio"]).status_code == 303
    c = _como(app, ANA)
    html = c.get("/").get_data(as_text=True)
    assert "Setor: <b>Performance</b>" in html                          # no topo, no lugar da cadeira
    assert 'data-torre="cos"' in html and 'data-torre="os"' in html and 'data-torre="pcm"' not in html
    assert 'href="/t/cos/mesa"' in html and 'href="/t/cos/ocorrencias"' not in html
    assert "1 de 1 prontas" in html and "de 10 prontas" not in html     # o cartão da torre OS conta só as do setor
    assert c.get("/t/cos/mesa").status_code == 200
    r = c.get("/t/cos/ocorrencias")
    assert r.status_code == 403 and "Esta tela não está liberada para o seu setor" in r.get_data(as_text=True)
    assert c.get("/t/cos/nao-existe").status_code == 404                 # a torre é dela: o portão deixa, a rota não há
    assert c.get("/t/pcm/nao-existe").status_code == 403
    r = c.get("/t/pcm/quadro", headers=DADOS)
    assert r.status_code == 403 and r.get_json()["erro"] == "Esta tela não está liberada para o seu setor."
    # fechar vale no próximo clique
    assert _salvar(logado, 1, ["os/inicio"]).status_code == 303
    assert c.get("/t/cos/mesa").status_code == 403


def test_setor_sem_nenhuma_tela_ve_o_inicio_com_o_aviso(app, setores):
    # a Bia: o setor dela (chamado "Administrador") não é dono de tela nenhuma; a Performance é dona dos relatórios da
    # Central de emissão desde 13/10/2026 (Tela.do_setor) e já nasce com eles
    r = _como(app, BIA).get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "O setor Administrador ainda não tem telas liberadas. Fale com o responsável." in html
    assert 'data-torre="' not in html


def test_setor_nao_da_administrador_e_administrador_com_setor_ve_tudo(app, setores):
    """Levi, 12/10: "não acho legal deixar como setores pois eu por exemplo sou da performance mas também sou
    administrador". Um setor chamado "Administrador" é setor comum; administrador é a lista, com ou sem setor."""
    c = _como(app, BIA)
    assert c.get("/t/cos/ocorrencias").status_code == 403
    assert c.get(URL).status_code == 403
    with c.session_transaction() as s:
        assert s["admin"] is False
    app.config["NEXUS_ADMINS"] = ANA                                     # a Ana: Performance E administradora
    c = _como(app, ANA)
    html = c.get("/").get_data(as_text=True)
    assert html.count('<details class="torre') == 13 and "Setor: <b>Performance</b>" in html
    assert c.get("/t/cos/ocorrencias").status_code == 200 and c.get(URL).status_code == 200
    with c.session_transaction() as s:
        assert s["admin"] is True


def test_banco_ilegivel_nao_vira_sem_setor(app, setores, monkeypatch):
    def fora(*a, **k):
        raise ConnectionError("banco fora")
    monkeypatch.setattr(S, "_ler_banco", fora)
    S._CACHE.clear()                                                     # sem nenhuma leitura boa guardada
    r = _como(app, ANA).get("/t/cos/mesa")
    assert r.status_code == 403
    html = r.get_data(as_text=True)
    assert "Não consegui ler o seu setor agora" in html and "Sem setor, fale" not in html


def test_banco_fora_sem_copia_nao_e_tentado_a_cada_clique(app, setores, monkeypatch):
    """Com o banco fora e nenhuma cópia, a 1ª falha vale pelos próximos ESPERA_S: os cliques respondem na hora."""
    chamadas = []

    def fora(*a, **k):
        chamadas.append(1)
        raise ConnectionError("banco fora")
    monkeypatch.setattr(S, "_ler_banco", fora)
    S._CACHE.clear()
    c = _como(app, ANA)
    for _ in range(3):
        r = c.get("/t/cos/mesa")
        assert r.status_code == 403 and "Não consegui ler o seu setor agora" in r.get_data(as_text=True)
    assert len(chamadas) == 1


def test_copia_vencida_responde_na_hora_e_rele_em_fundo(app, setores, monkeypatch):
    """O banco lento não prende o clique: com a cópia vencida vale ela, e a releitura vai para o segundo plano."""
    S._CACHE["livro"]["lido_em"] -= 3600
    chamadas, liberar, real = [], threading.Event(), S._ler_banco

    def lento(*a, **k):
        chamadas.append(1)
        liberar.wait(5)
        return real(*a, **k)
    monkeypatch.setattr(S, "_ler_banco", lento)
    t0 = time.time()
    r = _como(app, ANA).get("/")
    assert time.time() - t0 < 2 and r.status_code == 200
    assert "Setor: <b>Performance</b>" in r.get_data(as_text=True)
    liberar.set()
    for _ in range(100):
        if not ST._FUNDO["setores"]["rodando"]:
            break
        time.sleep(0.05)
    assert chamadas == [1] and time.time() - S._CACHE["livro"]["lido_em"] < 60     # relida em fundo, uma vez só


def test_a_leitura_do_clique_tem_prazo_curto():
    pedidos = []

    class Sessao:
        def get(self, *a, **k):
            pedidos.append(k["timeout"])
            return "ok"
    assert ST._Curta(Sessao()).get("/api/sheets", timeout=60) == "ok" and pedidos == [ST.PRAZO_S]


def test_sem_a_chave_ou_desligado_todos_veem_tudo(app, setores):
    app.config["NEXUS_ACESSO_POR_SETOR"] = "0"
    assert _como(app, CAIO).get("/t/cos/ocorrencias").status_code == 200
    app.config["NEXUS_ACESSO_POR_SETOR"] = "1"
    app.config.pop("NEXUS_PESSOA_HMAC")
    assert _como(app, CAIO).get("/t/cos/ocorrencias").status_code == 200


# ── a tela Base → Acessos ─────────────────────────────────────────────────────────────────────────────────────────


def test_a_secao_mostra_os_setores_e_a_arvore_do_menu(app, setores, logado):
    html = logado.get(URL).get_data(as_text=True)
    assert "Telas por setor" in html and 'id="ace-matriz"' in html
    assert re.search(r'class="ace-setor ativo"[^>]*>\s*<span class="nome">Administrador</span>', html)  # o 1º pelo nome
    assert '<span class="det">vê tudo' not in html and "0 de " in html            # nenhum setor "vê tudo"
    assert html.count('<input type="checkbox" name="tela"') == sum(len(t.telas) for t in app.extensions["nexus_torres"])
    assert 'value="performance/clima/mapa"' in html and 'value="cos/mesa"' in html
    adm = logado.get(URL + "?setor=2").get_data(as_text=True)                  # o setor "Administrador": caixas
    assert 'id="ace-matriz"' in adm and '<input type="hidden" name="setor" value="2">' in adm
    assert "Cadeira" not in html


def test_a_tela_grava_so_o_que_mudou(app, setores, logado):
    r = _salvar(logado, 1, ["cos/mesa", "os/inicio"])
    assert r.status_code == 303 and r.headers["Location"].endswith(URL + "?setor=1#ace-setores")
    assert "Performance agora vê 2 telas (2 mudanças)" in logado.get(URL + "?setor=1").get_data(as_text=True)
    linhas = _linhas(setores)
    assert list(linhas[0]) == list(ST.CAB)
    assert sorted((x["setor_id"], x["tela"], x["liberada"]) for x in linhas) == [(1, "cos/mesa", "sim"),
                                                                                (1, "os/inicio", "sim")]
    assert all(x["origem"] == "tela" and x["data_id"] for x in linhas)
    # salvar sem mexer não grava nada
    assert _salvar(logado, 1, ["cos/mesa", "os/inicio"]).status_code == 303
    assert len(_linhas(setores)) == 2
    assert "Nada mudou: Performance já via 2 telas." in logado.get(URL + "?setor=1").get_data(as_text=True)
    # desmarcar grava a tela que fechou, e só ela
    _salvar(logado, 1, ["cos/mesa"])
    linhas = _linhas(setores)
    assert len(linhas) == 3 and (linhas[-1]["tela"], linhas[-1]["liberada"]) == ("os/inicio", "nao")
    html = logado.get(URL + "?setor=1").get_data(as_text=True)
    assert re.search(r'<input type="checkbox" name="tela" value="cos/mesa" checked>', html)
    assert not re.search(r'<input type="checkbox" name="tela" value="os/inicio" checked>', html)
    # regra 8: nada de e-mail nem nome no banco
    assert not [v for x in _linhas(setores) for v in x.values() if "@" in str(v)]


def test_a_tela_recusa_o_que_nao_deve_gravar(app, setores, logado):
    r = _salvar(logado, 99, ["cos/mesa"])
    assert r.status_code == 400 and "Setor desconhecido" in r.get_data(as_text=True)
    r = _salvar(logado, 1, ["cos/mesa", "nao/existe"])
    assert r.status_code == 400 and "Tela desconhecida" in r.get_data(as_text=True)
    assert _salvar(logado, 1, ["cos/mesa"], codigo="outro").status_code == 403
    app.config.pop("GRIDCO_SQL_TOKEN")
    r = _salvar(logado, 1, ["cos/mesa"])
    assert r.status_code == 400 and "GRIDCO_SQL_TOKEN" in r.get_data(as_text=True)
    assert _linhas(setores) == []
    app.config["GRIDCO_SQL_TOKEN"] = "token-de-teste"
    assert _salvar(logado, 2, ["cos/mesa"]).status_code == 303                # o setor "Administrador" grava como os outros
    assert [(x["setor_id"], x["tela"]) for x in _linhas(setores)] == [(2, "cos/mesa")]
    # quem não é administrador nem abre a tela, nem grava
    c = _como(app, ANA)
    assert c.post(URL, data={"acao": "telas_setor", "setor": "1", "tela": ["cos/mesa"]}).status_code == 403


def test_quem_entrou_aparece_com_o_setor(app, setores, logado, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    for e in (ANA, BIA, CAIO):
        A.registrar_login(app.config, e)
    html = logado.get(URL).get_data(as_text=True)
    tabela = html[html.index("Quem entrou nos últimos 30 dias"):]
    linha = {e: re.search(re.escape(e) + r".*?</tr>", tabela, re.S).group(0) for e in (ANA, BIA, CAIO)}
    assert "<td>Performance</td>" in linha[ANA]
    assert "<td>Administrador</td>" in linha[BIA] and '<span class="mudo">não</span>' in linha[BIA]
    assert "pelo setor" not in html
    assert "sem setor" in linha[CAIO] and "cad-chip--alerta" in linha[CAIO]
    assert re.search(r'<div class="r">Entraram sem setor</div><div class="v ace-v-alerta">1</div>', html)


def test_cada_administrador_aparece_com_o_setor(app, setores, logado):
    app.config["NEXUS_ADMINS"] = f"{ANA},fora@exemplo.test"
    html = logado.get(URL).get_data(as_text=True)
    tabela = html[html.index('id="ace-admins"'):html.index('id="ace-registro"')]
    assert "<th>Setor</th>" in tabela
    assert re.search(re.escape(ANA) + r".*?<td>Performance</td>", tabela, re.S)
    assert re.search(r"fora@exemplo\.test.*?<td><span class=\"mudo\">—</span></td>", tabela, re.S)


def test_o_livro_no_catalogo_da_governanca():
    """Regra 10: livro registrado antes de existir, o fato com grão, chave e texto; nada pessoal."""
    livro = catalogo.LIVRO_POR_NOME[ST.LIVRO]
    assert livro.abas == (ST.ABA,) and not livro.no_banco
    f = catalogo.POR_ID["decisao_tela_setor"]
    assert f.livro == f"{ST.LIVRO} · {ST.ABA}" and all(c in ST.CAB for c in f.chave) and f.area == "base"
    assert not [c for c in ST.CAB if c in ("nome", "email") or c.startswith(("nome_", "email_"))]
