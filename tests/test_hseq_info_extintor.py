"""A informação adicional da conferência de extintor (26/10/2026, `nexus/hseq/info_extintor.py`). Levi: "caso na última
ronda tenha informações adicionais quero ao clicar na linha que apareça as informações, caso não tenha que venha uma
notificação". O texto vem do App como a foto (POST assinado), cifrado no disco; o livro só diz sim/não. E a caixa de
editar extintor com as listas de local, posição e classe ("todas as classe possíveis e posições possíveis e locais
possíveis registrados até o momento")."""
import time

import pytest
from test_campo_visao import CHAVE, CHAVE_CADASTRO, banco  # noqa: F401  (banco é fixture)
from test_hseq_extintores import LIVRO, com_livro  # noqa: F401  (fixture)

from nexus.campo import visao
from nexus.hseq import extintores as EXT
from nexus.hseq import info_extintor as INFO

EXT03 = "ALT100-INFC1-PPCI-EXT03"


@pytest.fixture
def dados(app, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path)
    app.config["NEXUS_CHAVE_CADASTRO"] = CHAVE_CADASTRO
    app.config["NEXUS_PESSOA_HMAC"] = CHAVE
    return tmp_path


def _enviar(cliente, app, codigo=EXT03, dia="2026-10-05", texto="Suporte solto; trocar na próxima visita", ts=None,
            assinatura=None):
    ts = ts or int(time.time())
    k = INFO.chave(app.config)
    return cliente.post("/t/hseq/extintores/info", data={
        "codigo": codigo, "dia": dia, "ts": ts, "texto": texto,
        "assinatura": assinatura or INFO.assinatura(k, codigo, dia, ts, texto)})


def test_o_app_envia_o_texto_assinado_e_o_nexus_guarda_cifrado(dados, app, cliente):
    r = _enviar(cliente, app)                                     # sem login: a rota vale pela assinatura
    assert r.status_code == 200 and r.get_json()["ok"]
    arq = dados / "hseq" / "extintores" / "info" / f"{EXT03}.json"
    assert arq.exists() and "Suporte solto" not in arq.read_text(encoding="utf-8")      # nunca em claro no disco
    with app.app_context():
        assert INFO.ler(app.config, EXT03) == {"dia": "2026-10-05", "texto": "Suporte solto; trocar na próxima visita"}
    # assinatura errada, hora fora da janela e texto de dia mais velho não gravam
    assert _enviar(cliente, app, texto="outro", assinatura="0" * 64).status_code == 401
    assert _enviar(cliente, app, ts=int(time.time()) - 3600).status_code == 401
    assert "mais novo" in _enviar(cliente, app, dia="2026-10-01", texto="velho").get_json()["mensagem"]
    with app.app_context():
        assert INFO.ler(app.config, EXT03)["texto"].startswith("Suporte solto")
    # a conferência nova sem informação apaga a velha
    _enviar(cliente, app, dia="2026-10-09", texto="")
    with app.app_context():
        assert INFO.ler(app.config, EXT03) is None


def test_o_clique_na_linha_mostra_o_texto_ou_o_aviso(com_livro, dados, app, cliente, logado):
    from test_campo_visao import _aba
    _aba(com_livro, EXT.LIVRO, EXT.ABA, [dict(x, **{"Tem informação adicional": "sim" if x["Código"] == EXT03 else "não"})
                                         for x in LIVRO])
    visao.limpar()
    us = logado.get("/t/hseq/extintores?usina=Altair&ver=extintor").get_data(as_text=True)
    assert f'data-codigo="{EXT03}" data-info="sim"' in us and "com informação adicional" in us
    assert 'data-codigo="ALT100-INFC1-PPCI-EXT01" data-info="nao"' in us
    assert '<dialog class="hs-dialogo" id="hs-info"' in us and 'id="hs-toast"' in us
    assert "sem informações adicionais na última ronda" in us
    # o texto chega do App e sai no clique (a rota de leitura pede login)
    assert logado.get(f"/t/hseq/extintores/info/{EXT03}").get_json() == {"ok": False}
    _enviar(cliente, app)
    j = logado.get(f"/t/hseq/extintores/info/{EXT03}").get_json()
    assert j["ok"] and j["texto"].startswith("Suporte solto") and j["dia"] == "2026-10-05"


def test_a_leitura_do_texto_pede_login(dados, app, cliente):
    r = cliente.get(f"/t/hseq/extintores/info/{EXT03}")
    assert r.status_code in (302, 401)


def test_as_listas_da_caixa_de_editar_e_o_outro(com_livro, logado, app, tmp_path):
    import json

    from nexus.hseq import decisoes as DEC
    op = logado.get("/t/hseq/extintores/opcoes").get_json()
    assert op["classe"] == ["ABC pó"] and op["posicao"] == ["Interno"] and op["local"] == ["Cabine"]
    us = logado.get("/t/hseq/extintores?usina=Altair&ver=extintor").get_data(as_text=True)
    assert '<select class="gc-campo" name="classe" data-lista="classe">' in us and 'name="classe_outro"' in us
    assert 'list="hs-classes"' not in us
    # "Outro (escrever)": vale o que foi escrito
    app.config["NEXUS_HSEQ_DECISOES_ARQUIVO"] = str(tmp_path / "decisoes.json")
    app.config["NEXUS_ADMINS"] = "tst@exemplo.test"
    DEC.limpar()
    with logado.session_transaction() as s:
        s.update(logado=True, admin=True, usuario={"email": "tst@exemplo.test", "nome": "TST de teste"})
    r = logado.post("/t/hseq/extintores/editar", data={"codigo": EXT03, "local": "__outro", "local_outro": "Casa de força",
                                                       "posicao": "Interno", "classe": "ABC pó", "peso": "6",
                                                       "val2": "12/2027", "val3": "2026"})
    assert r.status_code == 303
    linha = json.loads((tmp_path / "decisoes.json").read_text(encoding="utf-8"))[DEC.ABA_EDIT][0]
    assert linha["campos"] == '{"Local":"Casa de força"}'
    DEC.limpar()
