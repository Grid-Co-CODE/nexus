"""O e-mail semanal das pendências da Segurança (24/10/2026, `nexus/hseq/email_semanal.py`): a TST, "Receber report
semanal das pendências por email, pra mim e pro supervisor responsável". O Nexus monta e publica, o App de Campo manda.

O caso: o `com_cadastro` de test_hseq_extintores.py (Altair e Brodowski 1 da Supervisora Campo, Coração 1 do Coordenador
Campo, os dois com e-mail na ficha) com as PT e o não reconhecido da Mesa, e uma pessoa do Fracttal no setor Segurança."""
import re
from datetime import date

import pytest
from test_campo_visao import CHAVE, _aba, banco  # noqa: F401  (banco é fixture)
from test_hseq_extintores import com_cadastro, com_livro  # noqa: F401  (fixtures)
from test_hseq_mesa import _com_casos

from nexus.cadastro import setores as S
from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.hseq import email_semanal as ES

TST = codigo_da_pessoa(CHAVE, "tst@exemplo.test")


@pytest.fixture
def com_tst(com_cadastro):
    _com_casos(com_cadastro)
    _aba(com_cadastro, S.LIVRO, S.ABA_SETOR, [{"setor_id": 5, "nome": "Segurança", "criado_em": "2026-10-12",
                                               "alterado_em": "", "excluido": "não"}])
    com_cadastro._id(S.LIVRO, S.ABA_DECISAO)["linhas"] = [
        {"headers": list(S.CAB_DECISAO),
         "values": ["2026-10-12T10:00:00-03:00", 20261012, 700, "", "", TST, 5, "", "tela"]}]
    S._CACHE.clear()
    yield com_cadastro
    S._CACHE.clear()


def test_quem_recebe_a_tst_e_cada_responsavel_pelo_codigo(com_tst, app):
    with app.app_context():
        d = ES.destinatarios(app.config)
    assert d["tst"] == [{"pessoa_id": None, "hmac": TST}]
    assert d["responsaveis"]["Supervisora Campo"] == {"pessoa_id": 92,
                                                      "hmac": codigo_da_pessoa(CHAVE, "supervisora@exemplo.test")}
    assert d["responsaveis"]["Coordenador Campo"]["pessoa_id"] == 93


def test_o_email_da_semana_sem_nome_de_pessoa_e_assinado(com_tst, app):
    with app.test_request_context():
        d = ES.da_semana(app.config, hoje=date(2026, 10, 12))
    assert d["semana"] == "2026-W42" and not d["erros"]
    papeis = [(x["papel"], x["pessoa_id"]) for x in d["linhas"]]
    assert papeis == [("tst", ""), ("responsavel", 93), ("responsavel", 92)]
    sup = next(x for x in d["linhas"] if x["pessoa_id"] == 92)
    assert sup["assunto"] == "Pendências da Segurança nas suas usinas · semana de 12/10: 3 para agir"
    t = sup["corpo_texto"]
    assert "- 1 PT parada" in t and "- 1 extintor vencido" in t and "- 1 extintor não reconhecido" in t
    assert "- Altair (Thopen): 1 PT parada · 1 extintor vencido · 1 extintor não reconhecido" in t
    assert "Ver no Nexus: https://app.gridco.com.br/t/hseq/mesa?r=92" in t
    assert "https://app.gridco.com.br/t/hseq/mesa/pendencias.xlsx?r=92" in t
    # nada de nome nem e-mail de pessoa no que vai para a API compartilhada
    tudo = " ".join(str(v) for x in d["linhas"] for v in x.values())
    for nome in ("Supervisora", "Coordenador", "Técnico", "Eletricista", "@exemplo"):
        assert nome not in tudo
    assert all(re.fullmatch(r"[0-9a-f]{64}", x["assinatura"]) for x in d["linhas"])
    assert sup["assinatura"] == ES.assinatura(sup, CHAVE) != ES.assinatura(dict(sup, assunto="outro"), CHAVE)
    tst = d["linhas"][0]
    assert tst["destinatario_hmac"] == TST and "de todas as usinas" in tst["assunto"] and "?r=" not in tst["corpo_texto"]


def test_o_link_do_email_abre_a_mesa_filtrada_pelo_numero_da_pessoa(com_tst, logado):
    html = logado.get("/t/hseq/mesa?r=92").get_data(as_text=True)
    assert '<option value="Supervisora Campo" selected>' in html and "<b>Coordenador Campo</b>" not in html


def test_a_previa_mostra_quem_recebe_e_o_email(com_tst, app, cliente):
    app.config["NEXUS_ADMINS"] = "tst@exemplo.test"
    with cliente.session_transaction() as s:
        s.update(logado=True, admin=True, usuario={"email": "tst@exemplo.test", "nome": "TST de teste"})
    mesa = cliente.get("/t/hseq/mesa").get_data(as_text=True)
    assert 'href="/t/hseq/mesa/email">Prévia do e-mail semanal</a>' in mesa
    html = cliente.get("/t/hseq/mesa/email").get_data(as_text=True)
    assert "TST · 1 pessoa" in html and ">Supervisora Campo</a>" in html and "publicação desligada" in html
    assert "de todas as usinas" in html
    sup = cliente.get("/t/hseq/mesa/email?ver=92").get_data(as_text=True)
    assert "nas suas usinas" in sup and "Altair (Thopen)" in sup


def test_a_previa_e_so_de_quem_decide(com_tst, cliente):
    with cliente.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "sup@exemplo.test", "nome": "Sup"})
    assert cliente.get("/t/hseq/mesa/email").status_code == 403
    assert "Prévia do e-mail semanal" not in cliente.get("/t/hseq/mesa").get_data(as_text=True)


def test_publica_uma_vez_por_semana(com_tst, app, monkeypatch):
    gravado = {}
    monkeypatch.setattr(ES.livros, "publicar", lambda livro, nome, tabelas, **kw: gravado.update(tabelas))
    app.config["GRIDCO_SQL_TOKEN"] = "x"
    with app.test_request_context():
        r = ES.publicar(app.config, hoje=date(2026, 10, 12))
    assert r == {"publicadas": 3, "semana": "2026-W42", "sem_codigo": 0, "erro": ""}
    cab, linhas = gravado[ES.ABA]
    assert tuple(cab) == ES.CAB and len(linhas) == 3
    # a semana que já está no livro não volta
    monkeypatch.setattr(ES, "ler", lambda cfg: [dict(zip(cab, linhas[0]))])
    with app.test_request_context():
        assert ES.publicar(app.config, hoje=date(2026, 10, 12))["publicadas"] == 0
    assert ES.devido(ES._agora().replace(year=2026, month=10, day=26, hour=7)) and not ES.devido(
        ES._agora().replace(year=2026, month=10, day=26, hour=6))


def test_o_livro_esta_no_catalogo_antes_da_primeira_gravacao():
    from nexus.dados import catalogo as C
    livro = C.LIVRO_POR_NOME[ES.LIVRO]
    assert set(livro.abas) == {ES.ABA} and livro.so_cresce and not livro.no_banco
    assert {f.id: f for f in C.FATOS}["email_pendencias_seguranca"].livro.endswith(ES.ABA)
