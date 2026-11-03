"""Fase 2 dos setores conversando (03/11/2026): a conversa presa ao objeto (insight, OS, usina) com @menção de pessoa e
de área, as menções na Caixa de entrada e no sino, e o livro `nexus_conversas`. Nomes e textos inventados."""
import pytest
from test_campo_visao import banco  # noqa: F401  (fixture: o banco falso)
from test_comando_insights import PESSOA, _aberta, _cliente, _codigo, limpo, motor_dublado  # noqa: F401  (fixtures)

from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.comando import conversa as CV
from nexus.comando import motor as MO
from nexus.dados import catalogo, explica

OUTRA = {"email": "beltrana@exemplo.test", "nome": "Beltrana da Engenharia", "perfil": ""}


def _hmac(app, pessoa):
    return codigo_da_pessoa(app.config["NEXUS_PESSOA_HMAC"], pessoa["email"]).lower()


def _cliente_de(app, pessoa):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario=dict(pessoa))
    return c


def test_mensagem_mencao_e_lida(app, banco, limpo):
    """A menção avisa a pessoa (pelo código) e a área (quem o setor vê a torre); quem escreveu não se avisa; o lido
    tira; o texto e o nome só cifrados; o duplo clique não grava outra."""
    eu, ela = _hmac(app, PESSOA), _hmac(app, OUTRA)
    CV.registrar("insight:R07:1", "mensagem", PESSOA, "Recarga até sexta?\nA auditoria é segunda", [ela], ["hseq"])
    CV.registrar("insight:R07:1", "mensagem", PESSOA, "Recarga até sexta?\nA auditoria é segunda", [ela], ["hseq"])
    linhas = banco.linhas(CV.LIVRO, CV.ABA)
    assert [(l["objeto_tipo"], l["objeto_id"], l["evento"], l["mencoes_pessoas"], l["mencoes_areas"]) for l in linhas] \
        == [("insight", "R07:1", "mensagem", ela, "hseq")]
    assert "Recarga" not in str(linhas) and "Fulana" not in str(linhas)
    conv = CV.atual()
    m = conv["insight:R07:1"]["mensagens"][0]
    assert (m["por"], m["texto"]) == ("Fulana de Teste", "Recarga até sexta?\nA auditoria é segunda")
    assert [x["objeto"] for x in CV.para_mim(conv, ela, set())] == ["insight:R07:1"]          # a pessoa mencionada
    assert CV.para_mim(conv, eu, None) == []                                                   # quem escreveu, não
    seg = CV.para_mim(conv, "ab" * 12, {"hseq"})                                               # alguém da Segurança
    assert seg[0]["por_area"] == ["hseq"] and CV.para_mim(conv, "ab" * 12, {"cos"}) == []
    CV.registrar("insight:R07:1", "leu", OUTRA)
    CV.registrar("insight:R07:1", "leu", OUTRA)                                                # nada novo: não grava
    assert [l["evento"] for l in banco.linhas(CV.LIVRO, CV.ABA)] == ["mensagem", "leu"]
    assert CV.para_mim(CV.atual(), ela, set()) == []
    # responder conta como ler, e a resposta avisa quem foi mencionado nela
    CV.registrar("insight:R07:1", "mensagem", OUTRA, "Fechado, a equipe leva", [eu])
    assert [x["n"] for x in CV.para_mim(CV.atual(), eu, set())] == [1]
    for ruim in (("lixo:1", "mensagem", PESSOA, "oi"), ("os:12a", "mensagem", PESSOA, "oi"),
                 ("os:15000", "mensagem", PESSOA, "   "), ("os:15000", "mensagem", {"email": "", "nome": ""}, "oi")):
        with pytest.raises(CV.Recusada):
            CV.registrar(*ruim)


def test_a_conversa_no_insight_a_mencao_na_caixa_e_no_sino(app, banco, limpo, motor_dublado, monkeypatch):
    c = _cliente(app)
    html = _aberta(c, "/t/comando/insights")
    assert 'id="conv-insight-R07-1"' in html and "Use @ para chamar" in html and "comando/conversa.js" in html
    r = c.post("/t/comando/conversa/acao", data={"codigo": _codigo(c), "objeto": "insight:R07:1", "acao": "mensagem",
                                                 "texto": "@Segurança · HSEQ dá para trocar antes de sexta?",
                                                 "area": ["hseq", "comando"], "voltar": "/t/comando/insights"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/insights#conv-insight-R07-1")
    assert [l["mencoes_areas"] for l in banco.linhas(CV.LIVRO, CV.ABA)] == ["hseq"]          # o Comando não se menciona
    CV.ler(forcar=True)
    html = _aberta(c, "/t/comando/insights")
    assert "Mensagem enviada: 1 menção avisada." in html and "dá para trocar antes de sexta?" in html
    assert 'class="conv-mencao conv-mencao--area">@Segurança · HSEQ<' in html
    # quem é da Segurança vê a menção na Caixa e no sino, abre a conversa e marca como lida
    monkeypatch.setattr(MO, "torres_da_pessoa", lambda: {"hseq"})
    seg = _cliente_de(app, OUTRA)
    caixa = _aberta(seg, "/t/comando/caixa-de-entrada")
    assert "Menções para você" in caixa and "2 extintores vencidos" in caixa and "para Segurança · HSEQ" in caixa
    sino = caixa.split('class="sino-topo"', 1)[1].split("</details>", 1)[0]
    assert "1 menção sem ler" in sino and "/t/comando/conversa/insight/R07:1" in sino
    pag = seg.get("/t/comando/conversa/insight/R07:1").get_data(as_text=True)
    assert "dá para trocar antes de sexta?" in pag and "Abrir o insight" in pag
    seg.post("/t/comando/conversa/acao", data={"codigo": _codigo(seg, "/t/comando/caixa-de-entrada"),
                                               "objeto": "insight:R07:1", "acao": "leu",
                                               "voltar": "/t/comando/caixa-de-entrada"})
    CV.ler(forcar=True)
    caixa = _aberta(seg, "/t/comando/caixa-de-entrada")
    assert "Ninguém mencionou você nem o seu setor." in caixa
    # outro site não grava
    seg.post("/t/comando/conversa/acao", data={"codigo": _codigo(seg, "/t/comando/caixa-de-entrada"),
                                               "objeto": "insight:R07:1", "acao": "mensagem", "texto": "x"},
             headers={"Sec-Fetch-Site": "cross-site"})
    assert len(banco.linhas(CV.LIVRO, CV.ABA)) == 2


def test_conversa_nova_sobre_uma_os(app, banco, limpo, motor_dublado):
    c = _cliente(app)
    ela = _hmac(app, OUTRA)
    r = c.post("/t/comando/conversa/acao", data={"codigo": _codigo(c, "/t/comando/caixa-de-entrada"), "acao": "nova",
                                                 "tipo": "os", "os": "15000", "texto": "@Beltrana a peça chegou?",
                                                 "pessoa": [ela], "voltar": "/t/comando/caixa-de-entrada"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/conversa/os/15000")
    CV.ler(forcar=True)
    pag = c.get("/t/comando/conversa/os/15000").get_data(as_text=True)
    assert "OS 15000" in pag and "a peça chegou?" in pag and "Você" in pag
    assert c.get("/t/comando/conversa/os/abc").status_code == 404
    # sem o número, nada é gravado
    c.post("/t/comando/conversa/acao", data={"codigo": _codigo(c, "/t/comando/caixa-de-entrada"), "acao": "nova",
                                             "tipo": "os", "os": "", "texto": "oi"})
    assert len(banco.linhas(CV.LIVRO, CV.ABA)) == 1


def test_a_lista_do_arroba_so_quando_pede(app, banco, limpo, motor_dublado, monkeypatch):
    chamadas = []
    monkeypatch.setattr(CV, "pessoas_mencionaveis",
                        lambda: chamadas.append(1) or [{"hmac": "ab" * 12, "nome": "Beltrana", "setor": "Engenharia"}])
    c = _cliente(app)
    c.get("/t/comando/insights")
    assert chamadas == []                                               # abrir a tela não lê o pessoal
    d = c.get("/t/comando/conversa/pessoas").get_json()
    assert d["pessoas"][0]["nome"] == "Beltrana" and {"id": "engenharia", "nome": "Engenharia"} in d["areas"]
    assert all(a["id"] not in ("comando", "os") for a in d["areas"]) and chamadas == [1]


def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao():
    l = catalogo.LIVRO_POR_NOME[CV.LIVRO]
    assert l.abas == (CV.ABA,) and l.so_cresce == (CV.ABA,) and not l.no_banco
    f = catalogo.POR_ID["mensagem_conversa"]
    assert f.livro == f"{CV.LIVRO} · {CV.ABA}" and f.chave[0] == CV.CAB[0] and "pessoa_hmac" in CV.CAB
    assert "mensagem_conversa" in explica.RESUMO and "mensagem_conversa" in explica.PARA_QUE
