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
    html = logado.get("/t/hseq/extintores?modo=tabela&ver=extintor").get_data(as_text=True)
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
    atr = logado.get("/t/hseq/extintores?f=atrasado&ver=extintor").get_data(as_text=True)          # o filtro abre a tabela
    assert _linhas(atr) == ["ALT100-INFC1-PPCI-EXT01", "COR100-INFC1-PPCI-EXT01"]
    sem = logado.get("/t/hseq/extintores?f=sem_atualizacao&ver=extintor").get_data(as_text=True)    # o mais antigo primeiro
    assert _linhas(sem) == ["BWK100-INFC1-PPCI-EXT01", "COR100-INFC1-PPCI-EXT01", "ALT100-INFC1-PPCI-EXT02"]
    reg = logado.get("/t/hseq/extintores?modo=tabela&ver=extintor&regiao_campo=Sul+01").get_data(as_text=True)
    assert _linhas(reg) == ["COR100-INFC1-PPCI-EXT01"] and '<option value="Sul 01" selected>' in reg
    busca = logado.get("/t/hseq/extintores?modo=tabela&ver=extintor&q=skid1").get_data(as_text=True)
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

# ── por usina e dia (Levi, 09/10: "queria agrupado por usina e dia!") ─────────────────────────────────────────────
DIA_DO_GRUPO = [
    # dois de Altair conferidos no mesmo dia viram UMA linha (e o terceiro, noutro dia, outra)
    _ext("ALT100-INFC1-PPCI-EXT04", "Thopen - Altair 1 - SP", "02/2026", "Sem selo", "2026-10-05", carga="SOBRECARGA"),
    _ext("ALT100-INFC1-PPCI-EXT05", "Thopen - Altair 1 - SP", "Sem data", "Sem selo", "2026-10-05"),
]


def test_por_usina_e_dia_junta_os_extintores_da_mesma_conferencia():
    g = {(x["usina"], x["conferencia"]): x for x in EXT.por_usina_dia(
        [dict(EXT.situacao(e, HOJE), usina=e["Usina"], codigo=e["Código"], ext=e["Código"][-5:])
         for e in LIVRO + DIA_DO_GRUPO])}
    alt = g[("Thopen - Altair 1 - SP", date(2026, 10, 5))]
    assert alt["qtd"] == 3 and [x["ext"] for x in alt["extintores"]] == ["EXT04", "EXT01", "EXT05"]
    # a recarga mais próxima é a mais antiga (vencida há mais tempo): 02/2026, e não 08/2026
    assert (alt["situacao"], alt["recarga"], alt["recarga_fim"], alt["recarga_ext"]) == (
        "atrasado", "02/2026", date(2026, 2, 28), "EXT04")
    assert (alt["atrasado"], alt["sem_validade"], alt["status"]) == (2, 1, "CRITICO")
    assert alt["status_qtd"]["CRITICO"] == 2 and alt["status_qtd"]["OK_SEM_VALIDADE"] == 1
    # a mesma usina noutro dia é outra linha; o grupo sem nenhuma recarga com data diz "Sem data"
    assert g[("Thopen - Altair 1 - SP", date(2026, 8, 1))]["qtd"] == 1
    bwk = g[("Thopen - Brodowski 1 - SP", None)]
    assert (bwk["recarga"], bwk["recarga_fim"], bwk["status"]) == ("Sem data", None, "")
    ordem = [(x["usina"][9:13], x["conferencia"]) for x in EXT.por_usina_dia(
        [dict(EXT.situacao(e, HOJE), usina=e["Usina"], codigo=e["Código"], ext=e["Código"][-5:])
         for e in LIVRO + DIA_DO_GRUPO])]
    assert ordem[0] == ("Alta", date(2026, 10, 5))           # o atrasado com a recarga mais antiga primeiro


def test_a_tabela_abre_por_usina_e_dia_e_a_linha_abre_os_extintores(com_livro, logado):
    _aba(com_livro, EXT.LIVRO, EXT.ABA, LIVRO + DIA_DO_GRUPO)
    visao.limpar()
    html = logado.get("/t/hseq/extintores?modo=tabela").get_data(as_text=True)
    assert 'aria-current="page">Por usina e dia</a>' in html and 'href="?modo=tabela&amp;ver=extintor"' in html
    cab = _texto(html[html.index("<thead>"):html.index("</thead>")])
    assert cab == "Situação Usina Quantidade de extintores Recarga mais próxima Última conferência Status da TST PDF"
    linhas = html.count('<tr class="cn-linha"')
    assert linhas == 6 and html.count('<tr class="cn-detalhe" hidden>') == 6       # Altair em 2 dias, mais 4 usinas
    primeira = _texto(html[html.index('<tr class="cn-linha"'):html.index('<tr class="cn-detalhe"')])
    assert primeira.startswith("Atrasado Altair Sudeste 03 · Supervisora Campo 3 2 atrasados · 1 sem validade")
    assert "02/2026 venceu há 7 meses" in primeira and "05/10/2026 há 4 d" in primeira
    assert "Crítico 2 críticos · 1 ok sem validade" in primeira
    # a linha abre os extintores dela, sem repetir a usina nem a conferência
    ini = html.index('<table class="ext-sub cn-fotos-grupo">')
    sub = html[ini:html.index("</table>", ini)]
    assert re.findall(r'title="([A-Z]{3}\d{3}-INFC1-PPCI-EXT\d+)"', sub) == [
        "ALT100-INFC1-PPCI-EXT04", "ALT100-INFC1-PPCI-EXT01", "ALT100-INFC1-PPCI-EXT05"]
    assert "Altair" not in _texto(sub) and "Sobrecarga" not in sub and "sobrecarga" in _texto(sub)
    # o filtro da faixa vale para o agrupamento: só os atrasados entram na conta da linha
    atr = logado.get("/t/hseq/extintores?f=atrasado").get_data(as_text=True)
    assert atr.count('<tr class="cn-linha"') == 2
    assert _texto(atr[atr.index('<tr class="cn-linha"'):atr.index('<tr class="cn-detalhe"')]).startswith(
        "Atrasado Altair Sudeste 03 · Supervisora Campo 2 2 atrasados")


# ── o relatório em PDF (Levi, 09/10, com as observações da TST) ──────────────────────────────────────────────────
def _pdf_texto(corpo):
    pypdf = pytest.importorskip("pypdf")
    import io
    return " ".join(" ".join((p.extract_text() or "").split()) for p in pypdf.PdfReader(io.BytesIO(corpo)).pages)


def test_relatorio_pdf_por_usina_e_dia_com_o_filtro_da_tst(com_livro, logado):
    r = logado.get("/t/hseq/extintores/relatorio.pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:4] == b"%PDF"
    assert "inline" in r.headers["Content-Disposition"] and "extintores-todos-2026-10-09.pdf" in r.headers[
        "Content-Disposition"]
    t = _pdf_texto(r.data)
    assert "Relatório de extintores" in t and "Todos os extintores · com as fotos ao lado de cada extintor" in t
    assert "Altair" in t and "Coração 1" in t and "Thopen - Irecê 2 - BA" in t
    assert "Sem foto no Nexus" in t                                   # o padrão é com fotos: o quadro diz que falta
    assert "Recarga mais próxima" in t and "venceu há 39 d" in t
    # só os críticos: o ALT EXT01 (recarga vencida) e o COR EXT01 (sem carga e hidrostático vencido)
    crit = _pdf_texto(logado.get("/t/hseq/extintores/relatorio.pdf?status=criticos").data)
    assert "Só os críticos" in crit and "ALT100-INFC1-PPCI-EXT01" in crit and "COR100-INFC1-PPCI-EXT01" in crit
    assert "EXT02" not in crit and "IRC200" not in crit and "Brodowski" not in crit
    # sem fotos: uma tabela por usina e dia, sem o quadro da foto; os filtros da tela valem e o PDF diz quais
    sem = _pdf_texto(logado.get("/t/hseq/extintores/relatorio.pdf?fotos=0&fotos=0&regiao_campo=Sul+01").data)
    assert "sem fotos" in sem and "Sem foto no Nexus" not in sem and "Filtros: Região de campo: Sul 01" in sem
    assert "Coração 1" in sem and "Altair" not in sem


def test_relatorio_pdf_poe_a_foto_que_o_app_enviou_ao_lado_do_extintor(com_livro, logado, app, tmp_path):
    from PIL import Image
    pasta = tmp_path / "hseq" / "extintores" / "fotos"
    pasta.mkdir(parents=True)
    Image.new("RGB", (1200, 900), (200, 30, 30)).save(pasta / "ALT100-INFC1-PPCI-EXT01.jpg")
    app.config["NEXUS_DADOS"] = str(tmp_path)
    r = logado.get("/t/hseq/extintores/relatorio.pdf?status=criticos")
    pypdf = pytest.importorskip("pypdf")
    import io
    paginas = pypdf.PdfReader(io.BytesIO(r.data)).pages
    fotos = [im for p in paginas for im in p.images if im.name.endswith(".jpg")]     # o logo do topo é PNG
    assert len(fotos) == 1 and max(fotos[0].image.size) <= 600         # reduzida (a de 1200 px não entra inteira)
    assert "Sem foto no Nexus" in _pdf_texto(r.data)                   # o outro crítico continua sem foto


def test_sem_o_livro_o_relatorio_volta_para_a_tela(banco, logado):
    r = logado.get("/t/hseq/extintores/relatorio.pdf")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/hseq/extintores")


# ── o "Baixar" de cada linha, o filtro de cliente e a foto do extintor (Levi, 09/10, depois da 1ª carga no banco) ──
def test_baixar_de_cada_linha_traz_o_pdf_daquela_usina_e_dia(com_livro, logado):
    _aba(com_livro, EXT.LIVRO, EXT.ABA, LIVRO + DIA_DO_GRUPO)
    visao.limpar()
    html = logado.get("/t/hseq/extintores?modo=tabela").get_data(as_text=True)
    links = re.findall(r'<a class="cn-link" href="([^"]+)"[^>]*>Baixar</a>', html)
    assert len(links) == 6
    alt = next(h for h in links if "dia=2026-10-05" in h).replace("&amp;", "&")
    assert "usina=Altair" in alt and "baixar=1" in alt
    r = logado.get(alt)
    assert r.status_code == 200 and r.headers["Content-Disposition"].startswith("attachment;")
    assert 'filename="extintores-altair-2026-10-05.pdf"' in r.headers["Content-Disposition"]
    t = _pdf_texto(r.data)
    assert "ALT100-INFC1-PPCI-EXT04" in t and "ALT100-INFC1-PPCI-EXT01" in t and "ALT100-INFC1-PPCI-EXT05" in t
    assert "ALT100-INFC1-PPCI-EXT02" not in t and "Coração" not in t                    # outro dia, outra usina
    assert "Usina: Altair" in t and "Dia da conferência: 05/10/2026" in t
    # a usina nunca conferida também baixa (dia=nunca), e o filtro da faixa vai junto no link
    bwk = next(h for h in links if "dia=nunca" in h).replace("&amp;", "&")
    assert "BWK100-INFC1-PPCI-EXT01" in _pdf_texto(logado.get(bwk).data)
    atr = logado.get("/t/hseq/extintores?f=atrasado").get_data(as_text=True)
    assert all("f=atrasado" in h for h in re.findall(r'<a class="cn-link" href="([^"]+)"[^>]*>Baixar</a>', atr))


def test_filtro_por_cliente_vale_na_tela_no_pdf_e_no_epi(com_livro, logado):
    html = logado.get("/t/hseq/extintores?modo=tabela&ver=extintor").get_data(as_text=True)
    assert '<select class="gc-campo" id="cn-cliente" name="cliente"' in html
    assert '<option value="Outro Cliente">Outro Cliente</option>' in html and '<option value="Thopen">Thopen</option>' in html
    outro = logado.get("/t/hseq/extintores?modo=tabela&ver=extintor&cliente=Outro+Cliente").get_data(as_text=True)
    assert _linhas(outro) == ["COR100-INFC1-PPCI-EXT01"] and '<option value="Outro Cliente" selected>' in outro
    pdf = _pdf_texto(logado.get("/t/hseq/extintores/relatorio.pdf?cliente=Thopen").data)
    assert "Filtros: Cliente: Thopen" in pdf and "Coração" not in pdf and "Altair" in pdf
    # o formulário do PDF da tela leva o cliente escolhido
    assert '<input type="hidden" name="cliente" value="Outro Cliente">' in outro
    epi = logado.get("/t/hseq/epi?modo=tabela&cliente=Outro+Cliente").get_data(as_text=True)
    assert '<select class="gc-campo" id="cn-cliente" name="cliente"' in epi and "Coração 1" in epi and "Altair" not in epi


def _foto_jpeg():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (2400, 1800), (40, 160, 90)).save(buf, "JPEG")
    return buf.getvalue()


def _enviar(cliente, app, codigo="ALT100-INFC1-PPCI-EXT01", dia="2026-10-08", ts=None, dados=None, assinatura=None):
    import io
    import time
    from nexus.hseq import fotos as FOT
    dados = _foto_jpeg() if dados is None else dados
    ts = int(time.time()) if ts is None else ts
    sig = assinatura or FOT.assinatura(FOT.chave(app.config), codigo, dia, ts, dados)
    return cliente.post("/t/hseq/extintores/foto", data={"codigo": codigo, "dia": dia, "ts": str(ts),
                                                         "assinatura": sig, "foto": (io.BytesIO(dados), "f.jpg")},
                        content_type="multipart/form-data")


def test_o_app_envia_a_foto_assinada_e_ela_aparece_na_tabela_e_no_pdf(com_livro, app, cliente, logado, tmp_path):
    import time
    app.config["NEXUS_DADOS"] = str(tmp_path)
    # sem login (é o App), mas só com a assinatura certa, na hora certa e com imagem de verdade
    anon = app.test_client()
    assert _enviar(anon, app, assinatura="0" * 64).status_code == 401
    assert _enviar(anon, app, ts=int(time.time()) - 3600).status_code == 401
    assert _enviar(anon, app, dados=b"isto nao e imagem").status_code == 400
    assert _enviar(anon, app, codigo="../../etc").status_code == 400
    r = _enviar(anon, app)
    assert r.status_code == 200 and r.get_json()["ok"] is True
    guardada = tmp_path / "hseq" / "extintores" / "fotos" / "ALT100-INFC1-PPCI-EXT01.jpg"
    from PIL import Image
    assert guardada.is_file() and max(Image.open(guardada).size) == 1600                 # reduzida a 1600 px
    # a foto de um dia mais velho não substitui a guardada
    assert "mais nova" in _enviar(anon, app, dia="2026-09-01").get_json()["mensagem"]
    # ver a foto pede login; a tabela mostra a miniatura e a caixa que amplia
    assert anon.get("/t/hseq/extintores/foto/ALT100-INFC1-PPCI-EXT01.jpg").status_code == 302
    assert logado.get("/t/hseq/extintores/foto/ALT100-INFC1-PPCI-EXT01.jpg").mimetype == "image/jpeg"
    assert logado.get("/t/hseq/extintores/foto/ALT100-INFC1-PPCI-EXT02.jpg").status_code == 404
    html = logado.get("/t/hseq/extintores?modo=tabela").get_data(as_text=True)
    assert html.count('class="cn-foto ext-foto"') == 1 and "foto de 08/10/2026" in html
    assert 'class="cn-caixa-foto"' in html and 'class="ext-sub cn-fotos-grupo"' in html
    pypdf = pytest.importorskip("pypdf")
    import io
    paginas = pypdf.PdfReader(io.BytesIO(logado.get("/t/hseq/extintores/relatorio.pdf?status=criticos").data)).pages
    assert len([im for p in paginas for im in p.images if im.name.endswith(".jpg")]) == 1


def test_sem_a_chave_o_recebimento_de_fotos_fica_desligado(com_livro, app, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path)
    app.config["NEXUS_PESSOA_HMAC"] = ""
    r = app.test_client().post("/t/hseq/extintores/foto", data={"codigo": "ALT100-INFC1-PPCI-EXT01"})
    assert r.status_code == 503 and "desligado" in r.get_json()["mensagem"]
