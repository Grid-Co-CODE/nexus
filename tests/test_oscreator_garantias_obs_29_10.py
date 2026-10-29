"""Editar e excluir as observações na tela do chamado (Garantias, 29/10/2026). Levi: "Em garantias > clico na OS > Em
observações da OS gostaria de poder excluir a observação e editar a observação"; quem pode: "qualquer um que é ADM ou do
setor de chamados".

O banco só acrescenta (a regra de 27/09 do `chamados_obs_store`: linha nova a cada vez, o histórico honesto): editar grava
uma linha `edicao` e excluir uma `exclusao`, que apontam a observação (`extra.de`); a tela mostra a versão em vigor
(`vigentes`), com a marca "editada", e some com a excluída. Só a observação escrita (tipo obs) muda; ticket, status e
finalizado, os automáticos, nunca. Quem pode o Nexus decide (`ponte.obs_chamados`: o administrador ou o setor Chamados) e
põe no pedido; o OS Creator sozinho (o oem) fica aberto, como a Área PCM.

Fracttal e banco FALSOS (nada vai à rede). Nomes e números de mentira: o repositório é público."""
import sys

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
CHAVE = "os_web.obs_chamados"


def _reg(id_, os_, tipo, texto, quando="2026-10-28T10:00:00-03:00", extra=None, quem="Analista Teste"):
    return {"id": id_, "quando": quando, "os": os_, "tipo": tipo, "texto": texto, "quem": quem, "email": "",
            "ativo": "", "extra": dict(extra or {})}


# ── o banco: a versão em vigor ──────────────────────────────────────────────────────────────────────────────────
def test_vigentes_aplica_a_edicao_e_tira_a_excluida():
    pytest.importorskip("PyQt6")
    import chamados_obs_store as obs
    lista = [_reg("a", "9101", "obs", "Primeiro texto"), _reg("b", "9101", "obs", "Vai sumir"),
             _reg("c", "9101", "ticket", "Ticket registrado: SR 1"),
             _reg("d", "9101", "edicao", "Texto corrigido", "2026-10-29T09:00:00-03:00", {"de": "a"}, "Outra Pessoa"),
             _reg("e", "9101", "edicao", "Texto corrigido de novo", "2026-10-29T10:00:00-03:00", {"de": "a"}),
             _reg("f", "9101", "exclusao", "Observação excluída", "2026-10-29T11:00:00-03:00", {"de": "b"})]
    v = obs.vigentes(lista)
    assert [x["id"] for x in v] == ["a", "c"]
    a = v[0]
    assert a["texto"] == "Texto corrigido de novo" and a["quando"] == "2026-10-28T10:00:00-03:00"   # a data é a dela
    assert a["editada_em"] == "2026-10-29T10:00:00-03:00" and a["editada_por"] == "Analista Teste"


def test_a_edicao_de_um_automatico_nao_vale():
    pytest.importorskip("PyQt6")
    import chamados_obs_store as obs
    lista = [_reg("c", "9101", "ticket", "Ticket registrado: SR 1"),
             _reg("d", "9101", "edicao", "Outro", extra={"de": "c"}), _reg("e", "9101", "exclusao", "x", extra={"de": "c"})]
    assert [(x["id"], x["texto"]) for x in obs.vigentes(lista)] == [("c", "Ticket registrado: SR 1")]


# ── a tela ─────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def tela(monkeypatch):
    pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
    import api
    import chamados_obs_store as obs_store
    from os_web import criar_app, rotas
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    linha = {"id": 1, "folio": "9101", "cliente": "Cliente A", "usina": "Usina A1", "ativo": "Inversor 1.1", "code": "",
             "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": "", "status_id": 1, "status": "",
             "descricao": "[Inversor 1.1] - Acompanhamento de chamado Huawei", "data": "2026-10-01T13:00:00",
             "data_fim": "", "atribuido_a": "Analista Teste", "id_atribuido": None}
    banco = [_reg("a", "9101", "obs", "Pedimos a declaração ao cliente."),
             _reg("c", "9101", "ticket", "Ticket registrado: SR 1", "2026-10-27T10:00:00-03:00")]
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})
    monkeypatch.setattr(api, "list_chamados", lambda **k: [dict(linha)])
    monkeypatch.setattr(api, "total_chamados", lambda de=None: 1)
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {i: "" for i in ids})
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {"folio": 9101, "notas": "", "code": "TST-1",
                                                              "subtarefas": [], "status_id": 1})
    monkeypatch.setattr(obs_store, "listar", lambda forcar=False: list(banco))

    def inserir(reg):
        banco.append(dict(reg, extra=__import__("json").loads(reg["extra"])))
    monkeypatch.setattr(obs_store.ABA, "inserir", inserir)
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Analista Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    yield c, banco
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()


PODE = {CHAVE: {"pode": True, "aviso": ""}}
NAO_PODE = {CHAVE: {"pode": False, "aviso": "Editar e excluir observações em Garantias é do setor Chamados."}}


def _pagina(c, extra=None):
    return c.get("/os/chamados/acompanhamento/9101", environ_overrides=extra or PODE).get_data(as_text=True)


def test_a_observacao_escrita_tem_editar_e_excluir_e_a_automatica_nao(tela):
    c, _ = tela
    h = _pagina(c)
    tl = h.split('id="tl"', 1)[1]
    escrita = tl.split('data-obs-id="a"', 1)[1].split('class="tl-e', 1)[0]
    assert "data-obs-editar" in escrita and "data-obs-excluir" in escrita
    assert 'data-obs-id="c"' not in tl                                            # o ticket automático, sem botões


def test_quem_nao_pode_nao_ve_os_botoes(tela):
    c, _ = tela
    assert "data-obs-editar" not in _pagina(c, NAO_PODE)


def test_editar_grava_a_linha_nova_e_a_tela_mostra_a_editada(tela):
    c, banco = tela
    r = c.post("/os/api/acomp/9101/obs/a/editar", json={"texto": "Pedimos a declaração de transporte ao cliente."},
               environ_overrides=PODE)
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert banco[-1]["tipo"] == "edicao" and banco[-1]["extra"] == {"de": "a"} and banco[-1]["os"] == "9101"
    assert banco[0]["texto"] == "Pedimos a declaração ao cliente."                # a linha de antes não muda
    tl = _pagina(c).split('id="tl"', 1)[1]
    assert "Pedimos a declaração de transporte ao cliente." in tl and "editada" in tl
    assert "Pedimos a declaração ao cliente." not in tl


def test_excluir_some_da_tela_e_fica_no_banco(tela):
    c, banco = tela
    r = c.post("/os/api/acomp/9101/obs/a/excluir", json={}, environ_overrides=PODE)
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert banco[-1]["tipo"] == "exclusao" and banco[-1]["extra"] == {"de": "a"}
    assert "Pedimos a declaração ao cliente." not in _pagina(c).split('id="tl"', 1)[1]
    assert any(b["id"] == "a" for b in banco)


def test_quem_nao_pode_recebe_403_com_o_aviso(tela):
    c, banco = tela
    for acao, corpo in (("editar", {"texto": "x"}), ("excluir", {})):
        r = c.post("/os/api/acomp/9101/obs/a/%s" % acao, json=corpo, environ_overrides=NAO_PODE)
        assert r.status_code == 403 and "setor Chamados" in r.get_json()["erro"]
    assert len(banco) == 2


def test_automatica_de_outra_os_ou_ja_excluida_nao_muda(tela):
    c, banco = tela
    assert c.post("/os/api/acomp/9101/obs/c/editar", json={"texto": "x"}, environ_overrides=PODE).status_code == 400
    assert c.post("/os/api/acomp/9999/obs/a/excluir", json={}, environ_overrides=PODE).status_code == 404
    assert c.post("/os/api/acomp/9101/obs/zz/excluir", json={}, environ_overrides=PODE).status_code == 404
    c.post("/os/api/acomp/9101/obs/a/excluir", json={}, environ_overrides=PODE)
    assert c.post("/os/api/acomp/9101/obs/a/editar", json={"texto": "x"}, environ_overrides=PODE).status_code == 404
    assert c.post("/os/api/acomp/9101/obs/a/editar", json={"texto": ""}, environ_overrides=PODE).status_code in (400, 404)


def test_sem_o_nexus_dizer_quem_pode_fica_aberto(tela):
    """O OS Creator sozinho (o oem): sem a chave no pedido, como a Área PCM, quem abre a tela edita."""
    c, banco = tela
    r = c.post("/os/api/acomp/9101/obs/a/editar", json={"texto": "Corrigido."})
    assert r.status_code == 200 and banco[-1]["tipo"] == "edicao"


# ── quem pode: o administrador ou o setor Chamados (o Nexus decide) ─────────────────────────────────────────────
@pytest.fixture
def setor_de_mentira(app, monkeypatch):
    from nexus.auth import setor_telas
    app.config["NEXUS_PESSOA_HMAC"] = "chave-de-teste"
    monkeypatch.setattr(setor_telas, "_banco", lambda: (None, None))
    caixa = {"valor": None}
    monkeypatch.setattr(setor_telas, "setor_da_pessoa", lambda cfg, email, base, sessao: caixa["valor"])
    return caixa


def test_a_regra_do_nexus_administrador_ou_setor_chamados(app, setor_de_mentira):
    from flask import session
    with app.test_request_context("/os/chamados/acompanhamento/9101"):
        session["logado"], session["admin"] = True, True
        assert ponte.obs_chamados() == {"pode": True, "aviso": ""}
        session["admin"] = False
        session["usuario"] = {"email": "pessoa.teste@exemplo.test", "nome": "Pessoa Teste", "perfil": ""}
        for nome in ("Chamados", "chamados", " CHAMADOS "):
            setor_de_mentira["valor"] = {"id": 4, "nome": nome}
            assert ponte.obs_chamados() == {"pode": True, "aviso": ""}, nome
        setor_de_mentira["valor"] = {"id": 2, "nome": "Performance"}
        a = ponte.obs_chamados()
        assert a["pode"] is False and "setor Chamados e dos administradores" in a["aviso"]
        assert "Você está no setor Performance." in a["aviso"]
        # a regra da Área PCM continua a mesma
        setor_de_mentira["valor"] = {"id": 9, "nome": "PCM"}
        assert ponte.area_pcm() == {"pode": True, "aviso": ""}
        assert ponte.obs_chamados()["pode"] is False


def test_a_ponte_so_le_o_setor_na_tela_do_chamado_e_no_editar_excluir():
    """O quadro (e a pergunta de 5 em 5 s dele) não paga a leitura do setor; só a tela que mostra os botões e as rotas."""
    for resto, marca in (("chamados/acompanhamento/9101", True), ("api/acomp/9101/obs/ab12/editar", True),
                         ("api/acomp/9101/obs/ab12/excluir", True), ("chamados/acompanhamento", False),
                         ("chamados/acompanhamento/estado", False), ("api/acomp/9101/obs", False),
                         ("api/acomp/9101/ticket", False)):
        assert bool(ponte._ROTA_OBS.fullmatch(resto)) is marca, resto


def test_a_tela_pede_os_arquivos_com_a_versao(tela):
    """Em 29/10/2026 o editar e o excluir subiram e a tela seguiu com o acomp.js de antes (o navegador reusava a cópia):
    o endereço leva a hora em que o arquivo mudou, e o arquivo novo é outro endereço."""
    import re
    c, _ = tela
    h = _pagina(c)
    for nome in ("acomp.js", "chamados.css", "os_acoes.js", "os_acoes.css"):
        assert re.search(r'/os/static/%s\?v=\d{9,}"' % re.escape(nome), h), nome
    q = c.get("/os/chamados/acompanhamento").get_data(as_text=True)
    assert re.search(r'/os/static/acomp\.js\?v=\d{9,}"', q) and re.search(r'/os/static/chamados\.css\?v=\d{9,}"', q)


# ── o histórico importado da OS retroativa também edita e exclui (Levi, 29/10/2026: "não foi viu") ──────────────
# As linhas "Histórico importado na nota" não são observações do banco: vêm da nota da OS no Fracttal. Editar e excluir
# ficam no banco do Nexus por cima delas (a linha `edicao`/`exclusao` aponta a chave da linha, `h-...`); a nota no
# Fracttal não muda.
NOTA_RETRO = ("[CHAMADO] Acompanhamento — Huawei · Inversor\nOS de abertura: 11001 · OS de campo: 12002 · Ativo: TST-1\n"
              "Data da ocorrência / abertura do chamado: 21/08/2026\n\nHistórico (importado da Gestão de Chamados V02):\n"
              "21/08 - Chamado aberto\n22/08 - Fabricante solicitou verificações\n14/10 - Solicitado previsão ao supervisor")


def test_a_linha_do_historico_tem_chave_e_o_ajuste_vale_por_cima():
    pytest.importorskip("PyQt6")
    from os_web import acomp_web as aw
    import datetime as dt
    hoje = dt.datetime(2026, 10, 29, 12, 0)
    linha = {"id": 1, "folio": "9101", "note": NOTA_RETRO, "data": "2026-10-01T13:00:00", "status_id": 1,
             "descricao": "[Inversor 1.1] - Acompanhamento de chamado Huawei", "tipo_tarefa": "Administrativa"}
    c = aw.cartao(linha, "", "", hoje)
    hist = aw.ler_nota(NOTA_RETRO)["historico"]
    chaves = [aw.chave_do_historico(h) for h in hist]
    assert len(set(chaves)) == 3 and all(k.startswith("h-") for k in chaves)
    ajustes = {chaves[1]: {"tipo": "edicao", "texto": "Fabricante pediu as verificações por e-mail",
                           "quando": "2026-10-29T10:00:00-03:00", "quem": "Analista Teste"},
               chaves[2]: {"tipo": "exclusao", "texto": "", "quando": "2026-10-29T10:05:00-03:00", "quem": ""}}
    tl = aw.linha_do_tempo(c, [], hist, ajustes)
    textos = [e["texto"] for e in tl]
    assert "Solicitado previsão ao supervisor" not in textos                      # a excluída sai
    assert "Fabricante pediu as verificações por e-mail" in textos and "Fabricante solicitou verificações" not in textos
    editada = next(e for e in tl if e["texto"] == "Fabricante pediu as verificações por e-mail")
    assert editada["editavel"] and editada["id"] == chaves[1] and "editada 29/10 10:00" in editada["autor"]
    assert next(e for e in tl if e["texto"] == "Chamado aberto")["id"] == chaves[0]


@pytest.fixture
def retro(tela, monkeypatch):
    import api
    c, banco = tela
    monkeypatch.setattr(api, "list_chamados", lambda **k: [{
        "id": 1, "folio": "9101", "cliente": "Cliente A", "usina": "Usina A1", "ativo": "Inversor 1.1", "code": "",
        "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": NOTA_RETRO, "status_id": 1, "status": "",
        "descricao": "[Inversor 1.1] - Acompanhamento de chamado Huawei", "data": "2026-10-01T13:00:00",
        "data_fim": "", "atribuido_a": "Analista Teste", "id_atribuido": None}])
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {"folio": 9101, "notas": NOTA_RETRO, "code": "TST-1",
                                                              "subtarefas": [], "status_id": 1})
    monkeypatch.setattr(api, "_wo_id_por_folio", lambda folio: 1)
    return c, banco


def _chave(texto):
    from os_web import acomp_web as aw
    return next(aw.chave_do_historico(h) for h in aw.ler_nota(NOTA_RETRO)["historico"] if h["texto"] == texto)


def test_o_historico_importado_tem_os_botoes(retro):
    c, _ = retro
    tl = _pagina(c).split('id="tl"', 1)[1]
    k = _chave("Fabricante solicitou verificações")
    bloco = tl.split('data-obs-id="%s"' % k, 1)[1].split('class="tl-e', 1)[0]
    assert "data-obs-editar" in bloco and "data-obs-excluir" in bloco


def test_editar_e_excluir_o_historico_fica_no_nexus_por_cima_da_nota(retro):
    c, banco = retro
    k1, k2 = _chave("Fabricante solicitou verificações"), _chave("Solicitado previsão ao supervisor")
    r = c.post("/os/api/acomp/9101/obs/%s/editar" % k1, json={"texto": "Fabricante pediu as verificações por e-mail."},
               environ_overrides=PODE)
    assert r.status_code == 200 and banco[-1]["tipo"] == "edicao" and banco[-1]["extra"] == {"de": k1}
    assert c.post("/os/api/acomp/9101/obs/%s/excluir" % k2, json={}, environ_overrides=PODE).status_code == 200
    tl = _pagina(c).split('id="tl"', 1)[1]
    assert "Fabricante pediu as verificações por e-mail." in tl and "Fabricante solicitou verificações<" not in tl
    assert "Solicitado previsão ao supervisor" not in tl and "Chamado aberto" in tl
    # a excluída não volta a ser editada; a chave que não está na nota não existe
    assert c.post("/os/api/acomp/9101/obs/%s/editar" % k2, json={"texto": "x"}, environ_overrides=PODE).status_code == 404
    assert c.post("/os/api/acomp/9101/obs/h-000000000000/excluir", json={}, environ_overrides=PODE).status_code == 404
    r = c.post("/os/api/acomp/9101/obs/%s/editar" % k1, json={"texto": "y"}, environ_overrides=NAO_PODE)
    assert r.status_code == 403
