"""As decisões da Segurança sobre os extintores (24/10/2026, `nexus/hseq/decisoes.py`): a exclusão de extintor (o não
reconhecido aceito na usina e o botão direito na linha), que leva ao histórico de excluídos, e o pedido de nova ronda,
do zero, por usina. O livro é um arquivo (`NEXUS_HSEQ_DECISOES_ARQUIVO`): nada vai ao banco.

O caso dos testes é o do `com_nao_reconhecido` de test_hseq_extintores.py: o EXT02 da Altair não foi achado na ronda de
05/10/2026; a tela está no dia 09/10/2026."""
import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from test_campo_visao import CHAVE, _aba, banco  # noqa: F401  (banco é fixture)
from test_hseq_extintores import _abre, _linhas, _planilha, _tabela, _texto, com_nao_reconhecido  # noqa: F401

from nexus.campo import visao
from nexus.hseq import extintores as EXT
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


def _aceitar(c, codigo=EXT02, marca="2026-10-05"):
    return c.post("/t/hseq/extintores/excluir", data={"codigo": codigo, "marca": marca, "motivo": "nao_reconhecido",
                                                     "cliente": "Thopen", "usina": "Altair"})


def _aviso(r):
    q = parse_qs(urlsplit(r.headers["Location"]).query)
    return q.get("ok", [""])[0], q.get("erro", [""])[0]


def _linhas_livro(arq, aba):
    return json.loads(arq.read_text(encoding="utf-8"))[aba]


# ── as regras ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_excluido_volta_so_com_uma_conferencia_depois_da_exclusao():
    exc = {"decidida_em": "2026-10-06T09:00:00-03:00", "codigo": "C1"}
    assert DEC.excluido({"conferencia": date(2026, 10, 5)}, exc)          # antes: segue excluído
    assert DEC.excluido({"conferencia": date(2026, 10, 6)}, exc)          # no mesmo dia vale a exclusão
    assert not DEC.excluido({"conferencia": date(2026, 10, 7)}, exc)      # depois: a equipe o achou, ele volta
    assert DEC.excluido({"conferencia": None}, exc) and not DEC.excluido({"conferencia": None}, None)


def test_a_nova_ronda_e_do_zero_e_vale_pela_hora():
    """Combinado com o App de Campo em 24/10/2026 (v296), que aplica a mesma regra: o pedido sai quando TODOS os
    extintores da usina têm conferência recebida depois dele (ou marca de não reconhecido depois dele), pela hora."""
    brt = timezone(timedelta(hours=-3))

    def h(dia, hora):
        return datetime(2026, 10, dia, hora, tzinfo=brt)
    pedido = "2026-10-06T10:00:00-03:00"
    est = {"rondas": [{"decidida_em": pedido, "usina_id": u} for u in (1, 2, 3)]}
    por_usina = {1: [{"codigo": "A"}, {"codigo": "B"}],
                 2: [{"codigo": "C"}, {"codigo": "D", "nao_reconhecido": date(2026, 10, 6)}], 3: []}
    rec = {"A": h(6, 14), "B": h(6, 9), "C": h(6, 14)}
    p = DEC.rondas_pendentes(est, por_usina, rec)
    assert (p[1]["feitos"], p[1]["total"]) == (1, 2)                      # o B foi conferido antes do pedido
    assert (p[2]["feitos"], p[2]["total"]) == (1, 2)                      # marca só com o dia, no dia do pedido: não prova
    assert (p[3]["feitos"], p[3]["total"]) == (0, 0)                      # sem extintor, nada prova a ronda
    rec["B"] = h(6, 14)                                                   # pedido às 10h, ronda às 14h: atendido
    por_usina[2][1]["marca_em"] = h(6, 15)                                # a marca com a hora, depois do pedido
    assert set(DEC.rondas_pendentes(est, por_usina, rec)) == {3}
    por_usina[2][1] = {"codigo": "D", "nao_reconhecido": date(2026, 10, 7)}
    assert 2 not in DEC.rondas_pendentes(est, por_usina, rec)             # só o dia, mas do dia seguinte
    assert set(DEC.rondas_pendentes(est, por_usina, {"A": h(6, 14)})) == {1, 2, 3}



def test_a_marca_de_nao_reconhecido_com_a_hora_do_app():
    """Desde a v296 do App, o "Não reconhecido em" vem com a hora UTC em que o servidor recebeu a marca (o mesmo relógio
    da "Recebida em"): o dia continua o de Brasília, e a ronda pedida compara pela hora."""
    x = {"Não reconhecido em": "2026-10-08T02:00:00.000Z"}                # 23h do dia 07 em Brasília
    assert EXT.nao_reconhecido(x, date(2026, 10, 5)) == date(2026, 10, 7)
    assert EXT._com_hora(x["Não reconhecido em"]) == datetime(2026, 10, 7, 23, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert EXT._com_hora("2026-10-07") is None
    est = {"rondas": [{"decidida_em": "2026-10-07T22:00:00-03:00", "usina_id": 1}]}
    e = {"codigo": "A", "nao_reconhecido": date(2026, 10, 7), "marca_em": EXT._com_hora(x["Não reconhecido em"])}
    assert DEC.rondas_pendentes(est, {1: [e]}, {}) == {}                  # a marca chegou 1 h depois do pedido


def test_quem_pode_e_a_assinatura():
    assert DEC.pode_decidir({"nome": "Segurança"}, False) and DEC.pode_decidir({"nome": " SEGURANCA "}, False)
    assert DEC.pode_decidir(None, True) and not DEC.pode_decidir({"nome": "PCM"}, False) and not DEC.pode_decidir(None, False)
    linha = {"codigo": "C1", "motivo": "nao_reconhecido", "marca_dia": "2026-10-05",
             "decidida_em": "2026-10-06T09:00:00-03:00"}
    a = DEC.assinatura(linha, DEC.ABA_EXC, CHAVE)
    assert re.fullmatch(r"[0-9a-f]{64}", a) and a == DEC.assinatura(dict(linha), DEC.ABA_EXC, CHAVE)
    assert a != DEC.assinatura(dict(linha, motivo="retirado"), DEC.ABA_EXC, CHAVE) and DEC.assinatura(linha, DEC.ABA_EXC, "") == ""
    r = DEC.assinatura({"usina_id": 1, "usina_app": "Thopen - Altair 1 - SP", "decidida_em": "x"}, DEC.ABA_RONDA, CHAVE)
    assert re.fullmatch(r"[0-9a-f]{64}", r) and r != a


# ── na tela ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_aceitar_o_nao_reconhecido_exclui_e_leva_ao_historico(com_nao_reconhecido, livro, tst):
    """Levi, 24/10/2026: "por extintor é só o botão de aceitar, quando a TST aceita o extintor é excluído e vai para um
    histórico de extintores excluídos com o motivo 'Não reconhecido em campo'"."""
    us = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    nr = us[us.index('<tr class="hs-nr">'):]
    nr = nr[:nr.index("</tr>")]
    assert 'name="motivo" value="nao_reconhecido"' in nr and ">Aceitar</button>" in nr and "Pedir nova ronda" not in nr
    assert "vai para o histórico de excluídos, com o motivo Não reconhecido em campo" in nr
    r = _aceitar(tst)
    assert r.status_code == 303 and r.headers["Location"].endswith("#tabela")
    assert _aviso(r)[0] == "EXT02 excluído da Altair (não reconhecido em campo); está no histórico de excluídos."
    linha = _linhas_livro(livro, DEC.ABA_EXC)[0]
    assert (linha["codigo"], linha["motivo"], linha["marca_dia"], linha["usina_id"]) == (EXT02, "nao_reconhecido",
                                                                                          "2026-10-05", 1)
    assert re.fullmatch(r"[0-9a-f]{64}", linha["assinatura"]) and linha["decidida_por_hmac"] and linha["dados_cifrados"]
    assert "TST de teste" not in livro.read_text(encoding="utf-8")         # quem excluiu, só cifrado
    # sai da caixa, da faixa e da usina; aparece nos Excluídos, com o motivo e quem
    fim = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert EXT02 not in fim and 'id="nao-reconhecidos"' not in fim and 'aria-current="page">Excluídos <b>1</b>' not in fim
    assert ">Excluídos <b>1</b></a>" in fim
    exc = tst.get("/t/hseq/extintores?modo=excluidos").get_data(as_text=True)
    t = _texto(exc[exc.index('class="hs-excluidos"'):])
    assert "Altair EXT02" in t and "Não reconhecido em campo marcado em 05/10" in t and "TST de teste" in t
    # aceitar de novo o que já saiu é recusado
    assert "não está mais na tela" in _aviso(_aceitar(tst))[1]


def test_o_botao_direito_exclui_o_extintor_com_o_motivo(com_nao_reconhecido, livro, tst):
    """Levi, 24/10/2026: "como cada extintor tem um cadastro unitário então o certo seria (...) ir na linha do extintor,
    clicar com o botão direito e poder excluir o extintor"."""
    us = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert '<tr class="hs-ext" data-codigo="ALT100-INFC1-PPCI-EXT03">' in us and '<dialog class="hs-dialogo" id="hs-excluir"' in us
    dlg = us[us.index('id="hs-excluir"'):]
    assert re.findall(r'<option value="(\w+)">', dlg[:dlg.index("</select>")]) == ["retirado", "duplicado", "outro"]
    # "Outro motivo" pede a observação; motivo fora da lista não grava
    sem = tst.post("/t/hseq/extintores/excluir", data={"codigo": "ALT100-INFC1-PPCI-EXT03", "motivo": "outro"})
    assert 'escreva qual' in _aviso(sem)[1]
    ruim = tst.post("/t/hseq/extintores/excluir", data={"codigo": "ALT100-INFC1-PPCI-EXT03", "motivo": "sumiu"})
    assert "Motivo que o Nexus não conhece" in _aviso(ruim)[1] and not livro.exists()
    r = tst.post("/t/hseq/extintores/excluir", data={"codigo": "ALT100-INFC1-PPCI-EXT03", "motivo": "retirado",
                                                     "obs": "retirado na reforma da cabine"})
    assert _aviso(r)[0].startswith("EXT03 excluído da Altair (retirado da usina)")
    q = parse_qs(urlsplit(r.headers["Location"]).query)                    # a volta, pelo servidor: a usina do extintor
    assert (q["cliente"], q["usina"]) == (["Thopen"], ["Altair"])
    assert "reforma" not in livro.read_text(encoding="utf-8")
    depois = tst.get("/t/hseq/extintores").get_data(as_text=True)
    assert "Extintores 4 em" in _texto(depois)                            # saiu das contas (eram 5)
    exc = _texto(tst.get("/t/hseq/extintores?modo=excluidos").get_data(as_text=True))
    assert "Retirado da usina retirado na reforma da cabine TST de teste" in exc
    # e do Excel da usina
    xl = _planilha(tst.get("/t/hseq/extintores/relatorio.xlsx?cliente=Thopen&usina=Altair").data)["Extintores"]
    assert "ALT100-INFC1-PPCI-EXT03" not in [c.value for c in xl["F"]]


def test_o_excluido_volta_quando_a_equipe_o_confere_depois(com_nao_reconhecido, livro, tst):
    livro.write_text(json.dumps({DEC.ABA_EXC: [{"decidida_em": "2026-10-01T09:00:00-03:00", "data_id": 20261001,
                                                "usina_id": 1, "codigo": "ALT100-INFC1-PPCI-EXT01", "motivo": "retirado",
                                                "marca_dia": "", "decidida_por_hmac": "x", "assinatura": "y"}]}),
                     encoding="utf-8")
    DEC.limpar()
    html = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert "ALT100-INFC1-PPCI-EXT01" in _linhas(html)                     # conferido em 05/10, depois da exclusão
    exc = _texto(tst.get("/t/hseq/extintores?modo=excluidos").get_data(as_text=True))
    assert "voltou: conferido em 05/10" in exc


def test_pedir_nova_ronda_e_da_usina_inteira(com_nao_reconhecido, livro, tst, monkeypatch):
    """Levi, 24/10/2026: "pedir uma nova ronda é uma nova ronda do zero então será por usina"; nos três pontos. O pedido
    sai quando os três extintores da Altair (o não reconhecido junto) chegam conferidos depois dele."""
    monkeypatch.setattr(DEC, "_agora", lambda: datetime(2026, 10, 9, 10, 0, tzinfo=timezone(timedelta(hours=-3))))
    us = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert re.search(r'<button class="hs-tres"[^>]*data-args="cliente=Thopen&amp;usina=Altair" data-ronda="1">', us)
    assert ">Pedir nova ronda</button>" in us and '<form id="hs-form-ronda"' in us
    r = tst.post("/t/hseq/extintores/ronda", data={"usina_id": "1", "usina": "Altair", "cliente": "Thopen"})
    assert _aviso(r)[0].startswith("Nova ronda de extintores pedida para a Altair")
    linha = _linhas_livro(livro, DEC.ABA_RONDA)[0]
    assert (linha["usina_id"], linha["usina_app"]) == (1, "Thopen - Altair 1 - SP")    # o nome que o App usa
    assert re.fullmatch(r"[0-9a-f]{64}", linha["assinatura"])
    depois = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert "nova ronda pedida em 09/10 · 0 de 3 refeitos" in _abre(depois, "Altair<span")
    assert 'data-ronda="1" data-ronda-em="09/10"' in depois
    # a equipe refaz: duas chegam às 11h (14h UTC) e uma antes do pedido; depois, a terceira
    conf = [{"Código": f"ALT100-INFC1-PPCI-EXT0{n}", "Mês": "2026-10", "Usina": "Thopen - Altair 1 - SP",
             "Recebida em": r} for n, r in ((1, "2026-10-09T14:00:00.000Z"), (2, "2026-10-09T14:00:01.000Z"),
                                            (3, "2026-10-09T12:59:00.000Z"))]
    _aba(com_nao_reconhecido, EXT.LIVRO_CONF, EXT.ABA_CONF, conf)
    visao.limpar()
    meio = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert "2 de 3 refeitos" in _abre(meio, "Altair<span")
    conf[2]["Recebida em"] = "2026-10-09T14:05:00.000Z"
    _aba(com_nao_reconhecido, EXT.LIVRO_CONF, EXT.ABA_CONF, conf)
    visao.limpar()
    fim = tst.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert "nova ronda pedida" not in fim and 'data-ronda-em' not in fim


def test_quem_nao_e_da_seguranca_so_ve(com_nao_reconhecido, livro, cliente):
    with cliente.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "sup@exemplo.test", "nome": "Sup"})
    us = cliente.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert '<tr class="hs-nr">' in us and ">Aceitar</button>" not in us and "esperando a Segurança" in us
    assert 'class="hs-ext"' not in us and "data-ronda" not in us and 'id="hs-excluir"' not in us
    assert "Só quem é da Segurança" in _aviso(_aceitar(cliente))[1]
    assert "Só quem é da Segurança" in _aviso(cliente.post("/t/hseq/extintores/ronda", data={"usina_id": "1"}))[1]
    assert not livro.exists()


def test_a_senha_de_administrador_ve_os_botoes_mas_decidir_pede_o_login(com_nao_reconhecido, livro, logado):
    """O histórico guarda quem fez: a senha de administrador não diz quem é."""
    assert ">Aceitar</button>" in logado.get("/t/hseq/extintores?cliente=Thopen&usina=Altair").get_data(as_text=True)
    assert "Entre com o seu login" in _aviso(_aceitar(logado))[1]
    assert not livro.exists()


def test_o_filtro_de_status_com_os_nao_reconhecidos(com_nao_reconhecido, livro, logado):
    """Levi, 24/10/2026: "Adicione também um filtro de status (...) Insira não reconhecidos no status também!"."""
    emdia = logado.get("/t/hseq/extintores?f=em_dia&ver=extintor").get_data(as_text=True)
    assert _linhas(emdia[emdia.index('id="tabela"'):]) == ["IRC200-INFC1-PPCI-EXT01", "ALT100-INFC1-PPCI-EXT03"]
    nr = logado.get("/t/hseq/extintores?f=nao_reconhecido").get_data(as_text=True)
    tab = _tabela(nr)
    assert tab.count('<tr class="cn-linha ext-us"') == 1 and "1 não reconhecido" in _texto(tab)
    porext = logado.get("/t/hseq/extintores?f=nao_reconhecido&ver=extintor").get_data(as_text=True)
    assert _linhas(porext[porext.index('id="tabela"'):]) == [EXT02]
    assert '<option value="nao_reconhecido" selected>' in nr


def test_o_livro_esta_no_catalogo_antes_da_primeira_gravacao():
    from nexus.dados import catalogo as C
    livro = C.LIVRO_POR_NOME[DEC.LIVRO]
    assert set(livro.abas) == {DEC.ABA_EXC, DEC.ABA_RONDA} and livro.so_cresce and not livro.no_banco
    fatos = {f.id: f for f in C.FATOS}
    assert fatos["exclusao_extintor"].livro.endswith(DEC.ABA_EXC)
    assert fatos["pedido_ronda_extintor"].livro.endswith(DEC.ABA_RONDA)
    assert set(DEC.MOTIVOS_DO_BOTAO_DIREITO) | {"nao_reconhecido"} == set(DEC.MOTIVOS)
    visao.limpar()
