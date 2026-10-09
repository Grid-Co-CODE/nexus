"""Extintores no Nexus (Segurança · HSEQ, Levi, 09/10/2026): "ver a tabela dos extintores com uma visão do que está
atrasado, perto de atrasar e sem atualização a mais de 30 dias. Preciso da visão por supervisor".

As regras (`nexus/hseq/extintores.py`) num dia fixo, 09/10/2026, e a tela com o banco falso do Campo
(test_campo_visao.py): Altair (pelo de-para do Fracttal) e Brodowski 1 (pelo código do ativo) são da SP Norte 01, região
Sudeste 03 (Supervisora Campo), gestor Beltrano Supervisor; Coração 1 (pelo código da usina) é da Sul 01, com a vaga de
supervisor aberta, gestor Ciclano Chefe; Irecê 2 não está no cadastro (sem região e sem gestor)."""
import re
from datetime import date, datetime

import pytest
from test_campo_visao import BRT, CHAVE, _aba, banco  # noqa: F401  (banco é fixture)

from nexus.campo import visao
from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.hseq import extintores as EXT

HOJE = date(2026, 10, 9)


def _ext(codigo, usina, val2, val3, conf, ativo="", cb="", carga="CARREGADO", nao=None, hmac=None, **kw):
    """Uma linha do livro `extintores_app_campo · Extintores`, no contrato com o App (`EXT.COLUNAS`)."""
    d = {"Código": codigo, "Usina": usina, "Código da usina": cb, "Tipo de ativo": "CABN", "Ativo": ativo,
         "Local": "Cabine", "Posição": "Interno", "Classe": "ABC pó", "Peso (kg)": 6, "Validade da recarga": val2,
         "Validade do hidrostático": val3, "Última conferência": conf,
         "Origem da conferência": "App" if conf else None, "Conferido por (HMAC)": hmac,
         "Carga": carga if conf else None, "Itens NÃO": nao, "Fotos": 1 if conf else None,
         "Tem informação adicional": "não", "Status": None, "Motivo": None, "Origem do cadastro": "Planilha da TST"}
    d.update(kw)
    return d


LIVRO = [
    # Altair: vencido há 39 dias; vence em 22 dias e conferido há 69; em dia (o NÃO no difusor só pesa no status da TST)
    _ext("ALT100-INFC1-PPCI-EXT01", "Thopen - Altair 1 - SP", "08/2026", "Sem selo", "2026-10-05",
         hmac=codigo_da_pessoa(CHAVE, "tec1@exemplo.test")),
    _ext("ALT100-INFC1-PPCI-EXT02", "Thopen - Altair 1 - SP", "10/2026", "Sem selo", "2026-08-01"),
    _ext("ALT100-INFC1-PPCI-EXT03", "Thopen - Altair 1 - SP", "12/2027", "2026", "2026-10-01", nao="difusor"),
    # Brodowski 1, pelo código do ativo: sem data na recarga e nunca conferido
    _ext("BWK100-INFC1-PPCI-EXT01", "Thopen - Brodowski 1 - SP", "Sem data", "Sem selo", None, ativo="BWK100-SKID1"),
    # Coração 1, pelo código da usina: o hidrostático venceu (a recarga não) e está sem carga
    _ext("COR100-INFC1-PPCI-EXT01", "Thopen - Coração 1 - SC", "03/2027", "09/2026", "2026-03-01", cb="COR100",
         carga="SEM_CARGA"),
    # fora do cadastro do Nexus
    _ext("IRC200-INFC1-PPCI-EXT01", "Thopen - Irecê 2 - BA", "11/2026", "Sem selo", "2026-10-08", cb="IRC200"),
]


@pytest.fixture
def com_livro(banco, monkeypatch):
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 9, 10, 0, tzinfo=BRT))
    _aba(banco, EXT.LIVRO, EXT.ABA, LIVRO)
    visao.limpar()
    return banco


def _texto(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _linhas(html):
    """Os códigos dos extintores na tabela, na ordem."""
    return re.findall(r'title="([A-Z]{3}\d{3}-INFC1-PPCI-EXT\d+)"', html)


# ── as regras ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_etiqueta_vale_ate_o_ultimo_dia_do_mes_e_so_o_ano_ate_31_12():
    assert EXT.validade_fim("02/2028") == date(2028, 2, 29) and EXT.validade_fim("9/2026") == date(2026, 9, 30)
    assert EXT.validade_fim("2027") == EXT.validade_fim("2027.0") == date(2027, 12, 31)       # a API não garante o tipo
    for v in ("Sem data", "Sem selo", "", None, "13/2026", "00/2026", "12/1999", "31/12/2026"):
        assert EXT.validade_fim(v) is None, v


def test_status_da_tst_e_a_regra_do_app_inclusive_na_virada_do_mes():
    """A grade de casos do App (test_v247_extintores_servidor.py roda o `_ext_status` dele nos mesmos)."""
    limpo = set()
    assert EXT.status_tst("CARREGADO", limpo, "12/2027", "Sem selo", HOJE) == (
        "OK", "Nada fora do lugar e validade em dia")
    assert EXT.status_tst("CARREGADO", limpo, "Sem data", "Sem selo", HOJE) == (
        "OK_SEM_VALIDADE", "Checklist limpo, mas falta a validade")
    assert EXT.status_tst("SOBRECARGA", limpo, "12/2027", "", HOJE) == ("CRITICO", "sobrecarga")
    assert EXT.status_tst("Sem carga", limpo, "12/2027", "", HOJE) == ("CRITICO", "sem carga")
    assert EXT.status_tst("CARREGADO", {"manometro", "pintura"}, "12/2027", "", HOJE) == ("CRITICO", "manômetro: Não")
    assert EXT.status_tst("CARREGADO", {"pintura"}, "12/2027", "", HOJE) == ("ATENCAO", "pintura: Não")
    assert EXT.status_tst("CARREGADO", limpo, "10/2026", "", HOJE) == ("ATENCAO", "recarga vence em 31/10")
    # as DUAS etiquetas: o hidrostático vencido deixa crítico mesmo com a recarga em dia (o caso de Marabá 2)
    assert EXT.status_tst("CARREGADO", limpo, "12/2027", "12/2025", HOJE) == (
        "CRITICO", "teste hidrostático vencido em 12/2025")
    # a virada: vence hoje (0 dia) ainda é atenção; no dia seguinte, crítico
    assert EXT.status_tst("CARREGADO", limpo, "09/2026", "", date(2026, 9, 30))[0] == "ATENCAO"
    assert EXT.status_tst("CARREGADO", limpo, "09/2026", "", date(2026, 10, 1)) == (
        "CRITICO", "recarga vencida em 09/2026")
    assert EXT.status_tst("CARREGADO", limpo, "12/2027", "2026", date(2026, 12, 1)) == (
        "ATENCAO", "teste hidrostático vence em 31/12")


def test_o_tempo_vai_em_dias_ate_59_e_depois_em_meses_e_anos():
    """Na 1ª conferência com o cadastro da TST a tabela dizia "venceu há 557 d" e "vence em 1179 d"."""
    assert [EXT.tempo(n) for n in (0, 22, -39, 59, 60, 161, 365, 557, 715, 730, 1179)] == [
        "0 d", "22 d", "39 d", "59 d", "2 meses", "5 meses", "12 meses", "18 meses", "23 meses", "2 anos", "3 anos"]


def test_os_itens_nao_aceitam_a_chave_e_o_rotulo_com_acento():
    assert EXT.itens_nao("manometro; difusor") == {"manometro", "difusor"}
    assert EXT.itens_nao("Manômetro, Sinalização") == {"manometro", "sinalizacao"}
    assert EXT.itens_nao(None) == set()


def test_situacoes_exclusivas_e_a_sem_atualizacao_a_parte():
    s = {x["Código"][-5:] + x["Código"][:3]: EXT.situacao(x, HOJE) for x in LIVRO}
    alt1, alt2, alt3 = s["EXT01ALT"], s["EXT02ALT"], s["EXT03ALT"]
    assert (alt1["situacao"], alt1["dias_vence"], alt1["vence_qual"], alt1["sem_atualizacao"]) == (
        "atrasado", -39, "recarga", False)
    assert (alt2["situacao"], alt2["dias_vence"], alt2["sem_atualizacao"], alt2["dias_conferencia"]) == (
        "perto", 22, True, 69)
    # em dia: o NÃO no difusor deixa o status da TST em atenção, mas não mexe na validade
    assert (alt3["situacao"], alt3["status"], alt3["motivo"]) == ("em_dia", "ATENCAO", "difusor: Não")
    bwk = s["EXT01BWK"]
    assert (bwk["situacao"], bwk["sem_atualizacao"], bwk["conferencia"], bwk["status"]) == (
        "sem_validade", True, None, "")
    cor = s["EXT01COR"]
    assert (cor["situacao"], cor["vence_qual"], cor["dias_vence"]) == ("atrasado", "hidrostático", -9)
    assert cor["status"] == "CRITICO" and cor["motivo"] == "sem carga · teste hidrostático vencido em 09/2026"
    # o que a tabela mostra ao lado do status: só a carga e os itens (a validade já tem coluna)
    assert (cor["motivo_checklist"], alt3["motivo_checklist"], alt1["motivo_checklist"]) == ("sem carga", "difusor: Não", "")
    # 30 dias é o limite dos dois lados: vence em 30 dias = perto; conferido há 30 dias ainda não está sem atualização
    lim = EXT.situacao(_ext("X", "Y", "11/2026", "", "2026-09-09"), date(2026, 10, 31))
    assert (lim["situacao"], lim["dias_vence"], lim["dias_conferencia"], lim["sem_atualizacao"]) == (
        "perto", 30, 52, True)
    assert EXT.situacao(_ext("X", "Y", "12/2026", "", "2026-09-09"), date(2026, 10, 9))["sem_atualizacao"] is False
    assert EXT.situacao(_ext("X", "Y", "12/2026", "", "2026-09-08"), date(2026, 10, 9))["sem_atualizacao"] is True
    # a recarga sem data com o hidrostático vencido é atrasado, não "sem validade" (sabe-se que venceu)
    assert EXT.situacao(_ext("X", "Y", "Sem data", "01/2026", "2026-10-01"), HOJE)["situacao"] == "atrasado"


# ── a tela ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_sem_o_livro_a_tela_diz_que_os_extintores_ainda_nao_chegaram(banco, logado):
    html = logado.get("/t/hseq/extintores").get_data(as_text=True)
    assert "Os extintores ainda não chegaram ao banco do Nexus" in html and "extintores_app_campo" in html
    assert "cn-numeros" not in html and "<table>" not in html
    assert "Como cada extintor entra." in html                       # a explicação das regras fica


def test_a_faixa_conta_o_que_o_pedido_quer_e_cada_numero_filtra_a_tabela(com_livro, logado):
    html = logado.get("/t/hseq/extintores").get_data(as_text=True)
    t = _texto(html)
    assert "Extintores 6 em 4 usinas" in t
    assert "Atrasados 2 recarga ou teste hidrostático vencido" in t
    assert "Perto de vencer 1 vencem em até 30 dias" in t
    assert "Sem atualização 3 conferido há mais de 30 dias, ou nunca" in t
    assert "Sem validade 1 recarga sem data na etiqueta" in t
    for f in EXT.FILTROS:
        assert f'href="?f={f}&amp;modo=tabela"' in html, f


def test_por_supervisor_cartoes_da_regiao_de_campo_e_do_gestor(com_livro, logado):
    html = logado.get("/t/hseq/extintores").get_data(as_text=True)
    assert 'aria-current="page">Por supervisor</a>' in html and "<table>" not in html
    assert 'Supervisor de Campo: <b class="cn-eq-sup">Supervisora Campo</b>' in html
    assert re.search(r'Supervisor de Campo: <span class="cn-vaga"[^>]*>vaga</span>', html)          # Sul 01
    # Sudeste 03: Altair e Brodowski 1 (4 extintores); antes da Sul 01 (mesmos atrasados, mais perto de vencer)
    assert html.index("<b>Sudeste 03</b>") < html.index("<b>Sul 01</b>") < html.index("<b>Sem região de campo</b>")
    corpo = _texto(html[html.index("<b>Sudeste 03</b>"):html.index("<b>Sul 01</b>")])
    assert "1 equipe · 2 usinas" in corpo and "1 extintor atrasado" in corpo and "1 vence em até 30 dias" in corpo
    assert "1 em dia 1 sem validade 4 total" in corpo and "2 sem atualização há mais de 30 dias" in corpo
    assert "1 usina com extintor atrasado" in corpo
    assert 'href="?modo=tabela&amp;regiao_campo=Sudeste+03"' in html
    gest = logado.get("/t/hseq/extintores?modo=gestores").get_data(as_text=True)
    assert 'aria-current="page">Gestor de contrato (Supervisor PM)</a>' in gest
    assert gest.index("<b>Beltrano Supervisor</b>") < gest.index("<b>Ciclano Chefe</b>") < gest.index(
        "<b>Sem gestor de contrato</b>")
    assert 'href="?modo=tabela&amp;gestor=Beltrano+Supervisor"' in gest


def test_a_tabela_poe_o_mais_grave_primeiro_e_filtra_pela_situacao(com_livro, logado):
    html = logado.get("/t/hseq/extintores?modo=tabela").get_data(as_text=True)
    # atrasado (o vencido há mais tempo primeiro), perto, sem validade, em dia (o que vence antes primeiro)
    assert _linhas(html) == ["ALT100-INFC1-PPCI-EXT01", "COR100-INFC1-PPCI-EXT01", "ALT100-INFC1-PPCI-EXT02",
                             "BWK100-INFC1-PPCI-EXT01", "IRC200-INFC1-PPCI-EXT01", "ALT100-INFC1-PPCI-EXT03"]
    t = _texto(html[html.index("<table>"):html.index("</table>")])
    assert "08/2026 venceu há 39 d" in t and "10/2026 vence em 22 d" in t and "nunca conferido" in t
    # o status não repete a validade (está nas colunas ao lado): só a carga e os itens; o motivo inteiro, no title
    assert "Crítico sem carga" in t and 'title="sem carga · teste hidrostático vencido em 09/2026"' in html
    assert "Atenção difusor: Não" in t
    # a região diz o supervisor quando há alguém; a vaga fica nos cartões
    assert "Altair Sudeste 03 · Supervisora Campo" in t and "Coração 1 Sul 01" in t and "Sul 01 · vaga" not in t
    assert "Thopen - Irecê 2 - BA sem região" in t                             # fora do cadastro: o nome do App
    assert "05/10/2026 há 4 d · App Técnico Silva" in t                          # quem conferiu, pelo nome
    assert codigo_da_pessoa(CHAVE, "tec1@exemplo.test") not in html
    atr = logado.get("/t/hseq/extintores?f=atrasado").get_data(as_text=True)          # o filtro abre a tabela
    assert _linhas(atr) == ["ALT100-INFC1-PPCI-EXT01", "COR100-INFC1-PPCI-EXT01"]
    sem = logado.get("/t/hseq/extintores?f=sem_atualizacao").get_data(as_text=True)    # o mais antigo primeiro
    assert _linhas(sem) == ["BWK100-INFC1-PPCI-EXT01", "COR100-INFC1-PPCI-EXT01", "ALT100-INFC1-PPCI-EXT02"]
    reg = logado.get("/t/hseq/extintores?modo=tabela&regiao_campo=Sul+01").get_data(as_text=True)
    assert _linhas(reg) == ["COR100-INFC1-PPCI-EXT01"] and '<option value="Sul 01" selected>' in reg
    busca = logado.get("/t/hseq/extintores?modo=tabela&q=skid1").get_data(as_text=True)
    assert _linhas(busca) == ["BWK100-INFC1-PPCI-EXT01"]


def test_supervisor_que_entra_pelo_fracttal_ja_ve_a_regiao_dele(com_livro, cliente):
    with cliente.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "x@exemplo.test", "nome": "X", "perfil": "Supervisor"},
                 supervisor_padrao={"pessoa_id": 93, "nome": "Coordenador Campo", "papel": "supervisor_campo",
                                    "regioes": ["Sul 01"]})
    html = cliente.get("/t/hseq/extintores?modo=tabela").get_data(as_text=True)
    assert _linhas(html) == ["COR100-INFC1-PPCI-EXT01"] and '<option value="Sul 01" selected>' in html
    todas = cliente.get("/t/hseq/extintores?modo=tabela&regiao_campo=*").get_data(as_text=True)    # "Todas" vence
    assert len(_linhas(todas)) == 6


def test_coluna_da_conta_faltando_a_tela_nao_mostra_numero_pela_metade(com_livro, logado):
    _aba(com_livro, EXT.LIVRO, EXT.ABA, [{k: v for k, v in x.items() if k != "Validade da recarga"} for x in LIVRO])
    visao.limpar()
    html = logado.get("/t/hseq/extintores").get_data(as_text=True)
    assert "O livro dos extintores chegou sem a coluna Validade da recarga" in html
    assert "cn-numeros" not in html and "<table>" not in html


def test_a_tela_aparece_pronta_no_menu_da_torre(com_livro, logado):
    html = logado.get("/t/hseq/extintores").get_data(as_text=True)
    assert "campo-nativa" in html and 'href="/t/hseq/extintores"' in html
    assert logado.get("/t/hseq/riscos").status_code == 200                       # as outras seguem no placeholder
