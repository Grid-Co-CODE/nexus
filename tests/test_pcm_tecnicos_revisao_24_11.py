"""A revisão de Técnicos por usina pedida pelo Levi em 24/11/2026 (PCM → Técnicos por usina).

O pedido: "toda a parte de histórico, eu quero que seja baseado no histórico do OS Creator Web. Mesmo design, mesma lógica,
mesma funcionalidade"; "Esses KPIs aqui de cima, eles estão se repetindo com os pequenininhos de baixo [...] os KPIs podem
sumir"; "essa informação de cadastro, rondas e decisões do banco, lido às [...] fica dentro da exclamação"; "Na parte de
por técnico, eu gostaria de clicar no técnico e escolher as usinas, que ele vai ver"; "esse X aí, ele só aparecesse quando
passasse o mouse por cima"; "em campo, 30 dias [...] Não precisa ficar aparecendo toda hora"; "Essa comparação com o app
está confusa". Decisões dele no mesmo dia: o histórico é uma aba com todas as decisões, no modelo do Histórico de OS; e o
técnico abre uma janela com as usinas e o Salvar, que grava de uma vez (põe as novas como fixo e tira as desmarcadas).

O banco é o falso do `test_pcm_tecnicos_usina`; nomes e usinas inventados."""
import re

from nexus.pcm import atribuicoes as A
from nexus.pcm import tecnicos_usina as T
from test_pcm_tecnicos_usina import HOJE, _aba, _h, _montar, _por, banco  # noqa: F401 (fixture)
from test_pcm_tecnicos_usina import F1
from nexus.campo import visao

ROTA = "/t/pcm/tecnicos-por-usina"


def _atuais(app, pid):
    return sorted(uid for (uid, p, _papel) in A.atuais(A.ler(app.config, forcar=True), HOJE) if p == pid)


# ── por técnico: escolher as usinas ─────────────────────────────────────────────────────────────────────────────────
def test_escolher_as_usinas_do_tecnico_poe_e_tira_de_uma_vez(app, banco, logado):
    r = logado.post(ROTA + "/usinas-do-tecnico", data={"pessoa_id": "10", "usina": ["1", "2"], "v_ver": "tecnico"})
    assert r.status_code == 303 and r.headers["Location"].endswith(ROTA + "?ver=tecnico")
    assert _atuais(app, 10) == [1, 2]
    n = len(A.ler(app.config, forcar=True)["decisoes"])
    logado.post(ROTA + "/usinas-do-tecnico", data={"pessoa_id": "10", "usina": ["2", "3"]})
    assert _atuais(app, 10) == [2, 3]
    assert len(A.ler(app.config, forcar=True)["decisoes"]) == n + 2      # a 1 saiu, a 3 entrou, a 2 ficou como estava
    html = logado.get(ROTA + "?ver=tecnico").get_data(as_text=True)
    assert "1 usina posta e 1 tirada" in html
    # nada marcado: tira todas
    logado.post(ROTA + "/usinas-do-tecnico", data={"pessoa_id": "10"})
    assert _atuais(app, 10) == []


def test_o_apoio_que_continua_marcado_fica_com_as_datas(app, banco, logado):
    _por(app, 1, 11, ate="2030-12-31")
    logado.post(ROTA + "/usinas-do-tecnico", data={"pessoa_id": "11", "usina": ["1", "2"]})
    est = A.ler(app.config, forcar=True)
    linha = A.atuais(est, HOJE)[(1, 11, "executa")]
    assert int(linha["ate_data_id"]) == 20301231 and _atuais(app, 11) == [1, 2]


def test_usina_que_nao_esta_no_cadastro_e_recusada(app, banco, logado):
    logado.post(ROTA + "/usinas-do-tecnico", data={"pessoa_id": "10", "usina": ["1", "999"]})
    assert _atuais(app, 10) == []
    assert "não está no cadastro" in logado.get(ROTA).get_data(as_text=True)


def test_quem_nao_programa_nao_escolhe(app, banco, monkeypatch):
    from test_pcm_publicar import _no_setor, _pessoa
    from nexus.cadastro import setor_ids as SID
    c = _pessoa(app)
    _no_setor(monkeypatch, SID.RESPONSAVEL_UFV)
    assert c.post(ROTA + "/usinas-do-tecnico", data={"pessoa_id": "10", "usina": ["1"]}).status_code == 403


def test_a_aba_por_tecnico_abre_a_janela_das_usinas(app, banco, logado):
    _por(app, 1, 10)
    html = logado.get(ROTA + "?ver=tecnico").get_data(as_text=True)
    assert 'data-escolher-usinas="10"' in html and 'data-usinas-dele="1"' in html
    assert 'id="tu-usinas"' in html and 'action="/t/pcm/tecnicos-por-usina/usinas-do-tecnico"' in html
    assert '"usinas_json"' not in html and '"usinas":' in html          # a lista das usinas vai no JSON da página


# ── o topo, o X e o "em campo" ──────────────────────────────────────────────────────────────────────────────────────
def test_o_topo_sem_os_numeros_grandes_e_a_fonte_no_ponto_de_exclamacao(app, banco, logado):
    html = logado.get(ROTA).get_data(as_text=True)
    assert "data-tu-numeros" not in html and "cn-frescor" not in html
    caixa = html.split('class="gc-explica-caixa"')[1].split("</section>")[0]
    assert "lido às" in caixa and "Cadastro, rondas e decisões do banco" in caixa
    assert "data-fl-chip" in html                                         # os pequenos ficam
    assert "<th>Em campo (30 dias)</th>" not in html                      # saiu da tabela; fica no detalhe da usina
    assert "<dt>Em campo (30 dias)</dt>" in html


def test_o_x_de_tirar_so_aparece_no_passar_do_mouse():
    css = open("nexus/static/pcm.css", encoding="utf-8").read() + open("nexus/static/campo.css", encoding="utf-8").read()
    assert re.search(r"\.tu-tec form button\{[^}]*opacity:0", css)
    assert re.search(r"\.tu-tec:hover form button,\s*\.tu-tec:focus-within form button\{[^}]*opacity:1", css)


# ── o histórico no modelo do Histórico de OS ────────────────────────────────────────────────────────────────────────
def test_a_aba_historico_tem_todas_as_decisoes_e_os_filtros(app, banco, logado):
    _por(app, 1, 10)
    _por(app, 2, 11, obs="apoio nas férias")
    A.decidir(app.config, usina_id=1, usina_fracttal=F1, pessoa_id=10, pessoa_hmac=_h("t10@exemplo.test"),
              na_usina=False, usuario={"email": "pcm.teste@exemplo.test", "nome": "Pcm Teste"})
    html = logado.get(ROTA + "?ver=historico").get_data(as_text=True)
    assert 'aria-current="page">Histórico' in html
    assert 'data-fo' in html and 'name="acao"' in html and 'name="usina"' in html and 'name="tecnico"' in html
    linhas = html.split('id="tu-hist"')[1].split("</table>")[0]
    assert linhas.count('class="tu-h-linha"') == 3
    assert "Tirou" in linhas and "Pôs" in linhas and "apoio nas férias" in linhas
    # o filtro do servidor: só as que tiraram
    so = logado.get(ROTA + "?ver=historico&acao=tirou").get_data(as_text=True).split('id="tu-hist"')[1]
    assert so.split("</table>")[0].count('class="tu-h-linha"') == 1
    # a usina, pelo ID
    us = logado.get(ROTA + "?ver=historico&usina=2").get_data(as_text=True).split('id="tu-hist"')[1]
    assert us.split("</table>")[0].count('class="tu-h-linha"') == 1


def test_o_historico_geral_e_o_mesmo_da_usina(app, banco):
    _por(app, 1, 10)
    _por(app, 2, 11)
    with app.test_request_context():
        base = visao._Base()
        h = T.historico_geral(app.config, base, T.pessoas_de_campo(base, app.config), {})
    assert [(x["usina_id"], x["pessoa_id"], x["acao"]) for x in h["linhas"]] == [(2, 11, "pôs"), (1, 10, "pôs")]
    assert {o["valor"] for o in h["opcoes"]["usina"]} == {"1", "2"}


# ── a comparação com o App, por grupo ───────────────────────────────────────────────────────────────────────────────
def test_a_comparacao_vem_por_grupo_com_o_que_fazer(app, banco):
    _por(app, 1, 10)
    _por(app, 2, 13, hmac="")                     # a linha que vai sem código: a pessoa sem e-mail no cadastro

    def linha(usina, email, papel="executa"):
        return {"Usina": usina, "Pessoa (HMAC)": _h(email), "Papel": papel, "De": "2026-09-01", "Ate": None,
                "Origem": "bd_operacoes"}
    _aba(banco, "organizacao_app_campo", "Atribuicoes", [
        linha(F1, "t10@exemplo.test"), linha(F1, "t11@exemplo.test"), linha("Usina Fantasma - XX", "t10@exemplo.test")])
    visao.limpar()
    app_ = _montar(app)["app"]
    grupos = {g["id"]: g for g in app_["grupos"]}
    assert set(grupos) >= {"sem_codigo", "usina_do_app", "so_no_app"}
    assert grupos["sem_codigo"]["itens"][0]["usina"] == "Usina Dois" and grupos["sem_codigo"]["o_que_fazer"]
    assert grupos["so_no_app"]["itens"][0]["pessoa"] == "Técnico Onze"
    assert all(g["n"] == len(g["itens"]) for g in app_["grupos"])
