"""As decisões da Segurança sobre os extintores (24/10/2026, `nexus/hseq/decisoes.py`): na usina, o não reconhecido se
aceita (a baixa: sai da tela) ou ganha o pedido de nova ronda (o App mostra a ronda pendente), e a Segurança diz quantos
extintores existem na usina. O livro é um arquivo (`NEXUS_HSEQ_DECISOES_ARQUIVO`): nada vai ao banco.

O caso dos testes é o do `com_nao_reconhecido` de test_hseq_extintores.py: o EXT02 da Altair não foi achado na ronda de
05/10/2026."""
import json
import re
from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest
from test_campo_visao import CHAVE, banco  # noqa: F401  (banco é fixture)
from test_hseq_extintores import _abre, _linhas, _texto, com_nao_reconhecido  # noqa: F401  (fixture)

from nexus.hseq import decisoes as DEC

EXT02 = "ALT100-INFC1-PPCI-EXT02"


@pytest.fixture
def livro(app, tmp_path):
    arq = tmp_path / "decisoes.json"
    app.config["NEXUS_HSEQ_DECISOES_ARQUIVO"] = str(arq)
    DEC.limpar()
    yield arq
    DEC.limpar()


@pytest.fixture
def tst(app, cliente):
    """Quem decide: um login de pessoa, administrador (a lista de agora: a sessão segue a NEXUS_ADMINS a cada pedido)."""
    app.config["NEXUS_ADMINS"] = "tst@exemplo.test"
    with cliente.session_transaction() as s:
        s.update(logado=True, admin=True, usuario={"email": "tst@exemplo.test", "nome": "TST de teste"})
    return cliente


def _decidir(c, acao, codigo=EXT02, marca="2026-10-05"):
    return c.post("/t/hseq/extintores/decidir", data={"codigo": codigo, "marca": marca, "acao": acao,
                                                     "cliente": "Thopen", "usina": "Altair"})


def _aviso(r):
    q = parse_qs(urlsplit(r.headers["Location"]).query)
    return q.get("ok", [""])[0], q.get("erro", [""])[0]


# ── as regras ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_decisao_vale_para_a_marca_daquele_dia():
    x = {"codigo": "C1", "nao_reconhecido": date(2026, 10, 5)}
    est = {"extintor": [{"decidida_em": "2026-10-06T09:00:00-03:00", "codigo": "C1", "acao": "nova_ronda",
                         "marca_dia": "2026-10-05"}]}
    seguem, aceitos = DEC.aplicar([x], est)
    assert aceitos == [] and seguem[0]["nova_ronda_em"] == "2026-10-06"
    # a última vale: depois da nova ronda, a Segurança aceitou
    est["extintor"].append({"decidida_em": "2026-10-07T09:00:00-03:00", "codigo": "C1", "acao": "aceitar",
                            "marca_dia": "2026-10-05"})
    assert DEC.aplicar([x], est) == ([], [x])
    # a equipe marcou de novo noutro dia (a nova ronda também não achou): pede decisão nova
    y = dict(x, nao_reconhecido=date(2026, 10, 9))
    seguem, aceitos = DEC.aplicar([y], est)
    assert aceitos == [] and seguem[0]["nova_ronda_em"] == ""


def test_quem_pode_e_a_assinatura():
    assert DEC.pode_decidir({"nome": "Segurança"}, False) and DEC.pode_decidir({"nome": " SEGURANCA "}, False)
    assert DEC.pode_decidir(None, True) and not DEC.pode_decidir({"nome": "PCM"}, False) and not DEC.pode_decidir(None, False)
    linha = {"codigo": "C1", "acao": "aceitar", "marca_dia": "2026-10-05", "decidida_em": "2026-10-06T09:00:00-03:00"}
    a = DEC.assinatura(linha, DEC.ABA_EXT, CHAVE)
    assert re.fullmatch(r"[0-9a-f]{64}", a) and a == DEC.assinatura(dict(linha), DEC.ABA_EXT, CHAVE)
    assert a != DEC.assinatura(dict(linha, acao="nova_ronda"), DEC.ABA_EXT, CHAVE) and DEC.assinatura(linha, DEC.ABA_EXT, "") == ""


# ── na tela: a Segurança decide na usina ─────────────────────────────────────────────────────────────────────────
def test_a_seguranca_pede_nova_ronda_e_depois_aceita_na_usina(com_nao_reconhecido, livro, tst):
    us = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    nr = us[us.index('<tr class="hs-nr">'):]
    nr = nr[:nr.index("</tr>")]
    assert "Não reconhecido" in nr and 'name="acao" value="aceitar"' in nr and 'value="nova_ronda"' in nr
    assert 'data-confirma="Aceitar dá baixa: o EXT02 sai da Altair. Confirma?"' in nr
    # pedir nova ronda: grava a linha assinada e volta à usina com o aviso
    r = _decidir(tst, "nova_ronda")
    assert r.status_code == 303 and r.headers["Location"].endswith("#tabela")
    assert _aviso(r) == ("Nova ronda pedida para o EXT02 da Altair.", "")
    linhas = json.loads(livro.read_text(encoding="utf-8"))[DEC.ABA_EXT]
    assert len(linhas) == 1 and linhas[0]["acao"] == "nova_ronda" and linhas[0]["marca_dia"] == "2026-10-05"
    assert linhas[0]["usina_id"] == 1 and re.fullmatch(r"[0-9a-f]{64}", linhas[0]["assinatura"])
    assert linhas[0]["decidida_por_hmac"] and "tst@exemplo" not in livro.read_text(encoding="utf-8")
    # a tela: o pedido aparece na usina e na caixa, e o botão de pedir de novo some
    depois = tst.get(r.headers["Location"].split("#")[0]).get_data(as_text=True)
    assert "Nova ronda pedida para o EXT02 da Altair." in depois and "nova ronda pedida em" in depois
    assert 'value="nova_ronda"' not in depois and 'value="aceitar"' in depois
    # aceitar: dá baixa, e o EXT02 sai da caixa, da faixa e da usina
    assert _aviso(_decidir(tst, "aceitar"))[0] == "EXT02 aceito: sai da Altair."
    fim = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert EXT02 not in fim and 'id="nao-reconhecidos"' not in fim and "Não reconhecidos" not in _texto(fim)
    # decidir de novo o que já saiu é recusado
    assert "não está mais esperando a Segurança" in _aviso(_decidir(tst, "aceitar"))[1]


def test_quem_nao_e_da_seguranca_so_ve(com_nao_reconhecido, livro, cliente):
    # um supervisor (sem setor Segurança): vê o não reconhecido na usina, sem os botões, e o POST é recusado
    with cliente.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "sup@exemplo.test", "nome": "Sup"})
    us = cliente.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert '<tr class="hs-nr">' in us and 'value="aceitar"' not in us and "esperando a Segurança" in us
    assert "data-editar" not in us and 'class="hs-editar"' not in us
    assert "Só quem é da Segurança" in _aviso(_decidir(cliente, "aceitar"))[1]
    assert not livro.exists()


def test_a_senha_de_administrador_ve_os_botoes_mas_decidir_pede_o_login(com_nao_reconhecido, livro, logado):
    """O histórico guarda quem fez: a senha de administrador não diz quem é."""
    assert 'value="aceitar"' in logado.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert "Entre com o seu login" in _aviso(_decidir(logado, "nova_ronda"))[1]
    assert not livro.exists()


def test_a_seguranca_diz_quantos_extintores_existem_na_usina(com_nao_reconhecido, livro, tst, app):
    us = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    # o editar vai nos três pontos da usina: o cadastro tem 3 (o não reconhecido conta: ainda espera a Segurança)
    assert re.search(r'data-args="cliente=Thopen&amp;usina=Altair" data-editar="1;3;3"', us)
    assert 'class="hs-editar"' in us and '<dialog class="hs-dialogo" id="hs-qtd"' in us
    r = tst.post("/t/hseq/extintores/quantidade", data={"usina_id": "1", "usina": "Altair", "cliente": "Thopen",
                                                        "quantidade": "2", "motivo": "um foi retirado na reforma"})
    assert _aviso(r) == ("Quantidade da Altair: 2 extintores (o cadastro tem 3).", "")
    linha = json.loads(livro.read_text(encoding="utf-8"))[DEC.ABA_QTD][0]
    assert (linha["quantidade_qtd"], linha["no_cadastro_qtd"]) == (2, 3) and linha["dados_cifrados"]
    assert "reforma" not in livro.read_text(encoding="utf-8")                       # o motivo só cifrado
    assert DEC.motivo(app.config, linha) == "um foi retirado na reforma"
    depois = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert "Segurança: 2 em " in _abre(depois, "</span>Altair</td>") and 'data-editar="1;3;2"' in depois
    # número fora da régua não grava
    ruim = tst.post("/t/hseq/extintores/quantidade", data={"usina_id": "1", "usina": "Altair", "quantidade": "-1"})
    assert "número de 0 a 500" in _aviso(ruim)[1]
    assert len(json.loads(livro.read_text(encoding="utf-8"))[DEC.ABA_QTD]) == 1


def test_os_tres_pontos_no_lugar_da_coluna_relatorio(com_nao_reconhecido, livro, logado):
    """Levi, 24/10/2026: "ao invés da coluna relatório, pode substituir para três pontos ao passar o mouse na linha, aí
    clicando nos três pontos tem duas opções: Exportar PDF, Exportar planilha". O menu é um só (a página não pesa)."""
    html = logado.get("/t/hseq/extintores").get_data(as_text=True)
    assert html.count('class="hs-tres"') == html.count('<tr class="cn-linha') and "Relatório" not in _texto(
        html[html.index("<thead>"):html.index("</thead>")])
    menu = html[html.index('id="hs-menu"'):]
    menu = menu[:menu.index("</div>\n")]
    assert ">Exportar PDF</a>" in menu and ">Exportar planilha</a>" in menu
    assert html.count('id="hs-menu"') == 1 and "Exportar PDF" not in html.replace(menu, "")


def test_o_livro_esta_no_catalogo_antes_da_primeira_gravacao():
    from nexus.dados import catalogo as C
    livro = C.LIVRO_POR_NOME[DEC.LIVRO]
    assert set(livro.abas) == {DEC.ABA_EXT, DEC.ABA_QTD} and livro.so_cresce and not livro.no_banco
    fatos = {f.id: f for f in C.FATOS}
    assert fatos["decisao_extintor"].livro.endswith(DEC.ABA_EXT)
    assert fatos["quantidade_extintores"].livro.endswith(DEC.ABA_QTD)
