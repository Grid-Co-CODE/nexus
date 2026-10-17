"""A tela Técnicos por usina (17/10/2026, PCM → Técnicos por usina; rotas em nexus/pcm/telas.py).

O que estes testes seguram: quem vê (setores PCM e Responsáveis UFV) e quem edita (administrador e setor PCM; a carga
inicial só o administrador), pôr e tirar com a tela voltando filtrada, a carga inicial só com o livro vazio, o reenviar
ao App, a página sem e-mail de ninguém e o histórico da usina. O banco é o falso do `test_pcm_tecnicos_usina`."""
import json

from nexus.pcm import atribuicoes as A
from test_pcm_publicar import _no_setor, _pessoa
from test_pcm_tecnicos_usina import F1, PESSOA, _h, banco  # noqa: F401 (fixture)

ROTA = "/t/pcm/tecnicos-por-usina"


def _decisoes(app):
    return A.ler(app.config, forcar=True)["decisoes"]


def _atuais(app):
    return A.atuais(A.ler(app.config, forcar=True), A.hoje_id())


def test_quem_ve_e_quem_edita(app, banco, monkeypatch):
    c = _pessoa(app)
    por = {"usina_id": "1", "pessoa_id": "10", "acao": "por"}
    _no_setor(monkeypatch, "Responsáveis UFV")
    assert c.get(ROTA).status_code == 200
    assert c.post(ROTA + "/decidir", data=por).status_code == 403
    # quem vê: o portão por setor (desligado nos testes) segue o `Tela.do_setor` da torre
    from nexus.auth import setor_telas as ST
    with app.test_request_context():
        assert "pcm/tecnicos-por-usina" in ST.das_do_setor({"id": 1, "nome": "Responsáveis UFV"})
        assert "pcm/tecnicos-por-usina" in ST.das_do_setor({"id": 2, "nome": "PCM"})
        assert "pcm/tecnicos-por-usina" not in ST.das_do_setor({"id": 3, "nome": "Performance"})
    _no_setor(monkeypatch, "pcm")
    r = c.post(ROTA + "/decidir", data=por)
    assert r.status_code == 303 and len(_decisoes(app)) == 1
    assert c.post(ROTA + "/carga-inicial").status_code == 403
    # pedido de outro site não grava, nem para quem pode
    assert c.post(ROTA + "/decidir", data=dict(por, pessoa_id="11"),
                  headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_por_e_tirar_volta_filtrado(app, banco, logado):
    r = logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "por", "ate": "2030-12-31",
                                             "obs": "apoio", "v_equipe": "SP Norte 01"})
    assert r.status_code == 303 and r.headers["Location"].endswith(ROTA + "?equipe=SP+Norte+01")
    linha = _decisoes(app)[0]
    assert linha["usina_fracttal"] == F1 and linha["pessoa_hmac"] == _h("t10@exemplo.test")
    assert int(linha["ate_data_id"]) == 20301231 and linha["assinatura"]
    assert "Técnico posto na usina." in logado.get(ROTA).get_data(as_text=True)
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "tirar"})
    assert _atuais(app) == {}
    r = logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "tirar"})
    assert "já não está nesta usina" in logado.get(ROTA).get_data(as_text=True)


def test_carga_inicial_so_com_livro_vazio(app, banco, logado):
    assert "Carga inicial pela equipe" in logado.get(ROTA).get_data(as_text=True)
    assert logado.post(ROTA + "/carga-inicial").status_code == 303
    dec = _decisoes(app)
    assert len(dec) == 5 and {d["origem"] for d in dec} == {"carga_inicial"}
    html = logado.get(ROTA).get_data(as_text=True)
    assert "5 ligações" in html and "Carga inicial pela equipe" not in html
    logado.post(ROTA + "/carga-inicial")
    assert len(_decisoes(app)) == 5
    assert "o livro já tem decisões" in logado.get(ROTA).get_data(as_text=True)


def test_reemitir_regrava_com_o_nome_novo(app, banco, logado):
    A.decidir(app.config, usina_id=1, usina_fracttal="Nome Antigo", pessoa_id=10, pessoa_hmac=_h("t10@exemplo.test"),
              na_usina=True, usuario=PESSOA)
    assert "Reenviar ao App" in logado.get(ROTA).get_data(as_text=True)
    assert logado.post(ROTA + "/decidir", data={"usina_id": "1", "acao": "reemitir"}).status_code == 303
    dec = _decisoes(app)
    assert len(dec) == 2 and dec[-1]["usina_fracttal"] == F1 and dec[-1]["origem"] == "reemissao"


def test_pagina_sem_email_de_ninguem(app, banco, logado):
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "por"})
    for ver in ("usina", "tecnico"):
        html = logado.get(f"{ROTA}?ver={ver}").get_data(as_text=True)
        assert "exemplo.test" not in html and "Técnico Dez" in html
    dados = json.loads(html.split('id="tu-dados">', 1)[1].split("</script>", 1)[0])
    assert dados["pessoas"] and all(set(p) == {"id", "nome", "equipe_id"} for p in dados["pessoas"])


def test_historico_da_usina(app, banco, logado):
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "por", "obs": "apoio nas férias"})
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "tirar"})
    r = logado.get(ROTA + "/historico?usina=1")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and html.index("tirou") < html.index("pôs") and "apoio nas férias" in html
    assert "Técnico Dez" in html and "administrador (senha)" in html
    assert logado.get(ROTA + "/historico?usina=x").status_code == 404


def test_banco_fora_a_tela_abre_e_diz(app, logado):
    """Sem o banco (o rastreador do prefixo, ou a API fora do ar), a tela abre com o aviso e sem botão de gravar."""
    r = logado.get(ROTA)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Não consegui ler o cadastro no banco" in html and "Carga inicial" not in html
    assert logado.get(ROTA + "/historico?usina=1").status_code == 503
    r = logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "por"})
    assert r.status_code == 303 and "Não consegui ler o cadastro no banco" in logado.get(ROTA).get_data(as_text=True)


def test_tirar_leva_o_nome_e_o_codigo_que_o_app_tem(app, banco, logado):
    """O App acha a ligação a tirar pelo nome da usina e pelo código que foram na linha que pôs: o tirar leva os
    mesmos, mesmo que o nome no Fracttal tenha mudado depois."""
    A.decidir(app.config, usina_id=1, usina_fracttal="Nome Antigo", pessoa_id=10, pessoa_hmac="c" * 24,
              na_usina=True, usuario=PESSOA)
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "tirar"})
    ult = _decisoes(app)[-1]
    assert ult["na_usina"] == "nao" and ult["usina_fracttal"] == "Nome Antigo" and ult["pessoa_hmac"] == "c" * 24


def test_abas_no_estilo_da_pt_e_a_comparacao_com_o_app(app, banco, logado):
    """As abas Por usina, Por técnico e, com a foto do App, Comparação com o App; os chips das situações."""
    html = logado.get(ROTA).get_data(as_text=True)
    assert 'class="campo-nativa"' in html and 'class="cn-numeros"' in html and "Sem técnico" in html
    assert "Por técnico" in html and "Comparação com o App" not in html
    from test_pcm_tecnicos_usina import _aba
    _aba(banco, "organizacao_app_campo", "Atribuicoes", [{"Usina": F1, "Pessoa (HMAC)": _h("t11@exemplo.test"),
                                                           "Papel": "executa"}])
    from nexus.campo import visao
    visao.limpar()
    html = logado.get(ROTA + "?ver=app").get_data(as_text=True)
    assert "Comparação com o App" in html and "Pendências para a troca" in html and "Técnico Onze" in html


def test_tabela_com_cliente_sem_regiao_e_sem_o_botao_tecnico_na_linha(app, banco, logado):
    """Levi, 17/10: a coluna Cliente antes da Usina, sem a Região de campo; sem o botão "Técnico" na célula (o "Pôr
    técnico" fica no detalhe da linha); os técnicos um em cima do outro, sem a borda verde."""
    logado.post(ROTA + "/decidir", data={"usina_id": "1", "pessoa_id": "10", "acao": "por"})
    html = logado.get(ROTA).get_data(as_text=True)
    cab = html.split("<thead>", 1)[1].split("</thead>", 1)[0]
    assert cab.index("Cliente") < cab.index("Usina") and "Região" not in cab
    assert 'class="tu-mais"' not in html and "Pôr técnico" in html
    assert 'id="f-cliente"' in html and 'id="f-regiao"' not in html


def test_o_filtro_e_na_pagina(app, banco, logado):
    """Levi, 17/10: "sempre que vou puxar um filtro ele carrega o site de novo, deveria só filtrar os dados direto". As
    linhas vão todas à página (as que não passam, escondidas), com o que cada filtro olha; as listas não mandam o
    formulário; as duas abas estão na página."""
    import re
    html = logado.get(ROTA + "?equipe=SP+Norte+01").get_data(as_text=True)
    assert "data-filtro-local" in html and "filtro-local.js" in html and "this.form.submit()" not in html
    linhas = re.findall(r'<tr class="cn-linha"[^>]*>', html)
    assert len(linhas) == 4                                           # as 4 usinas, a desmobilizada também
    escondidas = [l for l in linhas if l.rstrip(">").endswith(" hidden")]
    assert len(escondidas) == 2                                       # a da SC Oeste 01 e a fora de operação
    assert all('data-f-equipe="' in l and 'data-f-situacao="' in l and 'data-f-busca="' in l for l in linhas)
    assert sum('data-fl-fora="1"' in l for l in linhas) == 1
    assert 'data-aba-secao="usina"' in html and 'data-aba-secao="tecnico"' in html
