"""A demanda do chamado de Garantias (24/11/2026). A equipe de chamados pediu "um chatzinho com os supervisores" dentro do
chamado (no lugar do Teams); o Levi aprovou no mockup a Nova demanda da Caixa de entrada dentro do chamado: "quando a
pessoa escolhe supervisor de campo, já puxa automaticamente o supervisor de campo daquela usina", a usina e a OS vão do
chamado, e o tema "Acompanhamento de chamado", com 3 dias úteis. A demanda é a de sempre (o mesmo livro e a mesma Caixa);
o Enviar volta ao Raio X do chamado, e o cartão do quadro de Garantias mostra a situação. O banco e o Fracttal são de
mentira; nomes inventados."""
from test_campo_visao import banco  # noqa: F401  (fixture: o banco falso)
from test_comando_demandas import ANA, CAIXA, JU, _cliente, _codigo, _form, _h, cena  # noqa: F401  (fixtures)
from test_oscreator_garantias_28_10 import tela  # noqa: F401  (fixture: o quadro de Garantias do OS Creator)

from nexus.cadastro import setor_ids as SID
from nexus.comando import demandas as D
from nexus.comando import temas_padrao as TP


def test_o_tema_padrao_do_chamado():
    assert ("", "Acompanhamento de chamado", 3) in TP.PADRAO["supervisao campo"]
    assert TP.TEMA_DO_CHAMADO == ("", "Acompanhamento de chamado")


def _tema_do_chamado(app, monkeypatch):
    """A Supervisão de Campo da cena (o setor 2) como o setor dos supervisores, com os temas padrão dele criados."""
    monkeypatch.setattr(SID, "SUPERVISAO_CAMPO", 2)
    with app.test_request_context():
        D.criar_temas_padrao([{"setor_id": 2, "nome": "Supervisão Campo"}], JU)
    D.limpar()
    return TP.codigo(2, *TP.TEMA_DO_CHAMADO)


def test_a_usina_da_os_pelo_retrato(app, cena):
    with app.app_context():
        assert (D.usina_da_os(18421), D.usina_da_os(18500), D.usina_da_os(99999), D.usina_da_os(None)) == (1, 3, None, None)


def test_o_contexto_do_chamado(app, cena, monkeypatch):
    """As demandas que citam a OS, os setores e os temas para as listas, a usina da OS e o tema do chamado já escolhido."""
    from nexus.torres.comando.demandas_tela import contexto_do_chamado
    padrao = _tema_do_chamado(app, monkeypatch)
    with app.test_request_context():
        D.abrir(_form(cena, para_hmac=_h(ANA["email"]), para_setor_id="2", tema_id=padrao, titulo="Foto da etiqueta",
                      novo_id="d00000000011"), [], JU)
        D.abrir(_form(cena, os="", novo_id="d00000000012"), [], ANA)               # outra demanda, sem a OS
    D.limpar()
    with app.test_request_context():
        from flask import session
        session.update(logado=True, usuario=dict(JU))
        cx = contexto_do_chamado(18421)
    assert [d["titulo"] for d in cx["demandas"]] == ["Foto da etiqueta"] and cx["abertas"] == 1 and cx["proximo"]
    assert cx["usina"][0] == 1 and cx["setor_sugerido"] == "2" and cx["tema_padrao"] == padrao
    assert ("2", "Supervisão de Campo") in cx["setores"] and ("1", "Performance") in cx["setores"]
    assert any(t["tema_id"] == padrao and t["setor"] == "2" and t["nome"] == "Acompanhamento de chamado (3 dias úteis)"
               for t in cx["temas"])
    assert cx["acao"].endswith("/t/comando/caixa-de-entrada/demandas/nova?chamado=18421") and cx["tem_login"]
    assert cx["demandas"][0]["caixa"].endswith(f"{CAIXA}?d=d00000000011#demandas")


def test_a_nova_demanda_do_chamado_volta_ao_raio_x(app, cena, monkeypatch):
    padrao = _tema_do_chamado(app, monkeypatch)
    c = _cliente(app, JU)
    cod = _codigo(c.get(CAIXA).get_data(as_text=True))
    f = dict(_form(cena, para_hmac=_h(ANA["email"]), para_setor_id="2", tema_id=padrao, novo_id="d00000000021"),
             codigo=cod)
    r = c.post(CAIXA + "/demandas/nova?chamado=18421", data=f, content_type="multipart/form-data")
    assert r.status_code == 303
    loc = r.headers["Location"]
    assert "/t/engenharia/equipe/os/18421?de=garantias&ok=Demanda+enviada" in loc and loc.endswith("#demandas")
    assert len(cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)) == 1
    # a recusa volta ao chamado com o motivo, sem gravar
    r = c.post(CAIXA + "/demandas/nova?chamado=18421", data=dict(f, tema_id="m00000000000", novo_id="d00000000022"),
               content_type="multipart/form-data")
    assert "&erro=" in r.headers["Location"] and len(cena["banco"].linhas(D.LIVRO, D.ABA_DEMANDA)) == 1
    # o selo do cartão, pela cópia
    from nexus.torres.oscreator import ponte
    D.limpar()
    with app.test_request_context():
        assert D.por_os()[18421]["abertas"] == 1
        selo = ponte.demandas_chamados()
    assert selo["18421"]["tom"] == "am" and selo["18421"]["texto"].startswith("Demanda aberta · vence ")


def test_o_cartao_do_garantias_mostra_a_demanda(tela):
    c, _, _ = tela
    extra = {"os_web.demandas_chamados": {"9101": {"texto": "Demanda aberta · vence 26/11", "tom": "am"},
                                          "9103": {"texto": "Demanda respondida", "tom": "ok"}}}
    html = c.get("/os/chamados/acompanhamento", environ_overrides=extra).get_data(as_text=True)
    assert '<span class="k-chip k-dm k-dm-am">Demanda aberta · vence 26/11</span>' in html
    assert '<span class="k-chip k-dm k-dm-ok">Demanda respondida</span>' in html
    assert "k-dm" not in c.get("/os/chamados/acompanhamento").get_data(as_text=True)     # o OS Creator sozinho


def test_a_demanda_abre_no_chamado_e_o_passo_volta_a_ele(app, cena, monkeypatch):
    """O clique na demanda abre na própria linha do chamado (a descrição, o andamento e os botões de quem recebeu); o passo
    dado dali volta ao chamado, com ela aberta, e o mesmo passo vale na Caixa de entrada."""
    from nexus.torres.comando.demandas_tela import contexto_do_chamado
    padrao = _tema_do_chamado(app, monkeypatch)
    with app.test_request_context():
        D.abrir(_form(cena, para_hmac=_h(ANA["email"]), para_setor_id="2", tema_id=padrao, titulo="Foto da etiqueta",
                      novo_id="d00000000031"), [], JU)
    D.limpar()
    with app.test_request_context("/?dm=d00000000031"):
        from flask import session
        session.update(logado=True, usuario=dict(ANA))
        cx = contexto_do_chamado(18421)
    d = cx["demandas"][0]
    assert d["eu_recebo"] and not d["eu_pedi"] and d["aberta_agora"]
    assert d["passo_url"].endswith(f"{CAIXA}/demandas/d00000000031/passo?chamado=18421")
    ana = _cliente(app, ANA)
    cod = _codigo(ana.get(CAIXA).get_data(as_text=True))
    r = ana.post(d["passo_url"], data={"codigo": cod, "acao": "em_analise", "aba": "para", "novo_id": D.novo_id("e")})
    loc = r.headers["Location"]
    assert r.status_code == 303 and "/t/engenharia/equipe/os/18421?de=garantias&ok=Feito" in loc
    assert "dm=d00000000031" in loc and loc.endswith("#dm-d00000000031")
    # quem não recebeu volta ao chamado com o motivo, sem gravar
    ju = _cliente(app, JU)
    cod_ju = _codigo(ju.get(CAIXA).get_data(as_text=True))
    r = ju.post(d["passo_url"], data={"codigo": cod_ju, "acao": "respondeu", "texto": "Ok", "aba": "para",
                                      "novo_id": D.novo_id("e")})
    assert "&erro=" in r.headers["Location"] and "/t/engenharia/equipe/os/18421" in r.headers["Location"]
