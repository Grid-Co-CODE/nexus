"""Central de atenção e Permissões de trabalho por região de campo e por gestor de contrato. Era "por supervisor" (Levi,
08/10/2026: "além de por equipe e tabela, adicione mais um botão (por supervisor). Faça o mesmo na tela permissões de
trabalho"); com a estrutura de O&M de 10/2026 (Levi, 08/10: "pode adaptar, deixa as vagas preparadas") o cartão passou a
ser o da REGIÃO DE CAMPO, com o Supervisor de Campo e o Coordenador (ou a vaga), e uma alternância para "por Gestor de
contrato" (Supervisor PM, pelas usinas dele). Banco falso (o mesmo de test_campo_visao.py): a SP Norte 01 (Altair e
Brodowski 1) é da Sudeste 03 (supervisora de campo 92) e a SC Oeste 01 (Coração 1) da Sul 01, com a vaga aberta; as
usinas da SP são do gestor Beltrano Supervisor e a Coração 1 do Ciclano Chefe; as duas PT esperando são da SP Norte 01."""
import re
import shutil
import subprocess

import pytest
from test_campo_visao import EQUIPES, REGIOES, USINAS, _MOB, _aba, banco  # noqa: F401  (banco é fixture)

from nexus.campo import visao


def _cartoes(html):
    """O pedaço dos cartões, sem os endereços, para comparar duas telas."""
    corpo = html[html.index('<div class="cn-equipes">'):html.index('<div class="cn-nota">')]
    return " ".join(re.sub(r'href="[^"]*"', "", corpo).split())


def test_por_regiao_soma_os_cartoes_das_equipes_e_por_gestor_soma_as_usinas(banco):
    d = visao.atencao(14).dados
    eq = visao.por_equipe(d["usinas"], d["pendentes"], [], d["pts"], d["times"])
    r = {x["regiao"]: x for x in visao.por_regiao(eq, d["regioes"])}
    se, sul = r["Sudeste 03"], r["Sul 01"]
    assert (se["equipes"], se["n_equipes"], se["usinas"], se["pendentes"], se["feitas"], se["pct_feitas"]) == (
        ["E-31 SP Norte 01"], 1, 2, 1, 1, 50)
    assert (se["longa_pendente"], se["pts"], se["parada"], se["tecnicos"]) == (1, 2, 1, 2)
    assert (se["supervisor_campo"], se["coordenador_campo"], se["base"]) == ("Supervisora Campo", "Coordenador Campo",
                                                                             "São José do Rio Preto/SP")
    assert (se["aprovador"]["tipo"], se["aprovador"]["pessoa_id"]) == ("supervisor", 92)
    assert (sul["usinas"], sul["pendentes"], sul["pct_feitas"], sul["nunca"], sul["tecnicos"]) == (1, 1, 0, 1, 1)
    # vaga de supervisor aberta: quem aprova é o coordenador, e o texto diz isso
    assert sul["supervisor_campo"] == "vaga" and sul["aprovador"]["tipo"] == "coordenador"
    assert "Vaga aberta de supervisor de campo na região Sul 01: aprova o coordenador" in sul["aprovador"]["texto"]
    # dois cartões de equipe da mesma região viram um, com a soma e o % refeito sobre a soma
    junto = visao.por_regiao([dict(eq[0], regiao_campo="X"), dict(eq[1], regiao_campo="X")])[0]
    assert (junto["n_equipes"], junto["usinas"], junto["pendentes"], junto["pct_feitas"]) == (2, 3, 2, 33)
    # o gestor é da USINA: as do Beltrano são as duas da SP; as PT dele também
    g = {x["gestor"]: x for x in visao.por_gestor(d["usinas"], d["pendentes"], d["pts"], d["times"])}
    b, c = g["Beltrano Supervisor"], g["Ciclano Chefe"]
    assert (b["usinas"], b["pendentes"], b["pct_feitas"], b["pts"], b["equipes"], b["tecnicos"]) == (
        2, 1, 50, 2, ["SP Norte 01"], 2)
    assert (c["usinas"], c["pendentes"], c["nunca"], c["pts"], c["tecnicos"]) == (1, 1, 1, 0, 1)


def test_central_por_regiao_de_campo_com_a_alternancia_para_gestor(banco, logado):
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert ">Por equipe</a>" in html and ">Por região de campo</a>" in html and ">Tabela</a>" in html
    assert ">Por supervisor</a>" not in html
    html = logado.get("/t/campo/atencao?modo=regioes").get_data(as_text=True)
    assert 'aria-current="page">Por região de campo</a>' in html and "<table>" not in html
    assert "<b>Sudeste 03</b>" in html and "<b>Sul 01</b>" in html
    assert 'Supervisor de Campo: <b class="cn-eq-sup">Supervisora Campo</b>' in html
    assert 'Coordenador: <b class="cn-eq-sup">Coordenador Campo</b>' in html
    assert re.search(r'Supervisor de Campo: <span class="cn-vaga"[^>]*>vaga</span>', html)       # a Sul 01, vaga
    assert "1 equipe · base São José do Rio Preto/SP" in html and "<b>2 usinas</b>total" in html
    assert 'href="?modo=tabela&amp;regiao_campo=Sudeste+03"' in html
    # a ordem: quem tem mais pendentes primeiro, e no empate o menor % feito (Sul 0%, Sudeste 50%)
    assert html.index("<b>Sul 01</b>") < html.index("<b>Sudeste 03</b>")
    # a alternância: por gestor de contrato (Supervisor PM)
    assert 'aria-current="page">Região de campo (Supervisor de Campo)</a>' in html
    assert 'href="?modo=gestores">Gestor de contrato (Supervisor PM)</a>' in html
    gest = logado.get("/t/campo/atencao?modo=gestores").get_data(as_text=True)
    assert 'aria-current="page">Por região de campo</a>' in gest and "<b>Beltrano Supervisor</b>" in gest
    assert "Gestor de contrato (Supervisor PM)</span>" in gest and "2 usinas · 1 equipe" in gest
    assert 'href="?modo=tabela&amp;gestor=Beltrano+Supervisor"' in gest
    # o endereço antigo (modo=supervisores) cai na visão por região
    assert "<b>Sudeste 03</b>" in logado.get("/t/campo/atencao?modo=supervisores").get_data(as_text=True)
    tabela = logado.get("/t/campo/atencao?modo=tabela&regiao_campo=Sudeste+03").get_data(as_text=True)
    assert "<table>" in tabela and "Altair" in tabela and "Coração 1" not in tabela
    assert '<option value="Sudeste 03" selected>' in tabela


def test_cartao_sem_regiao_e_sem_gestor_e_proprio_e_acha_as_linhas(banco, logado):
    # uma equipe de fora da estrutura de campo, numa usina sem gestor de contrato
    _aba(banco, "cadastro_nexus", "usinas", USINAS + [
        {"usina_id": 6, "nome": "Órfã", "codigo": "THPN-ORF100", "status": "OPERAÇÃO", "equipe_id": 30,
         "data_mobilizacao": _MOB, "uf": "MS", "cidade": "Órfã", "cliente_id": 1, "cluster": "MS Leste"}])
    _aba(banco, "cadastro_nexus", "equipes", EQUIPES + [{"equipe_id": 30, "nome": "MS Leste 01"}])
    visao.limpar()
    html = logado.get("/t/campo/atencao?modo=regioes").get_data(as_text=True)
    assert "<b>Sem região de campo</b>" in html and "cn-sup--sem" in html
    assert "equipes fora da estrutura de campo" in html
    assert html.index("<b>Sem região de campo</b>") > html.index("<b>Sudeste 03</b>")         # por último
    assert 'href="?modo=tabela&amp;regiao_campo=Sem+regi%C3%A3o+de+campo"' in html
    tabela = logado.get("/t/campo/atencao?modo=tabela&regiao_campo=Sem+região+de+campo").get_data(as_text=True)
    assert "Órfã" in tabela and "Altair" not in tabela
    assert '<option value="Sem região de campo" selected>' in tabela
    gest = logado.get("/t/campo/atencao?modo=gestores").get_data(as_text=True)
    assert "<b>Sem gestor de contrato</b>" in gest and gest.index("<b>Sem gestor de contrato</b>") > gest.index(
        "<b>Ciclano Chefe</b>")
    tabela = logado.get("/t/campo/atencao?modo=tabela&gestor=Sem+gestor+de+contrato").get_data(as_text=True)
    assert "Órfã" in tabela and "Coração 1" not in tabela


def test_pt_por_regiao_e_por_gestor_na_tela_de_pt_e_na_central_e_a_mesma(banco, logado):
    html = logado.get("/t/campo/pt?modo=regioes").get_data(as_text=True)
    assert ">Por equipe</a>" in html and 'aria-current="page">Por região de campo</a>' in html and ">Tabela</a>" in html
    assert "<b>Sudeste 03</b>" in html and "<b>Sul 01</b>" not in html                 # a Sul 01 não tem PT
    assert "2</span><span class=\"d\">PT esperando o De acordo" in html and "1 parada há mais de 2 h" in html
    assert "1 equipe com PT esperando" in html
    assert 'href="?modo=tabela&amp;regiao_campo=Sudeste+03"' in html
    # _pt_esperando.html é o mesmo nas duas telas (Levi, 05/10): mudou uma, mudou a outra
    for modo in ("regioes", "gestores"):
        assert _cartoes(logado.get(f"/t/campo/pt?modo={modo}").get_data(as_text=True)) == _cartoes(
            logado.get(f"/t/campo/atencao?vista=pt&modo={modo}").get_data(as_text=True)), modo
    gest = logado.get("/t/campo/pt?modo=gestores").get_data(as_text=True)
    assert "<b>Beltrano Supervisor</b>" in gest and "Ciclano Chefe</b>" not in gest     # o Ciclano não tem PT
    tabela = logado.get("/t/campo/pt?modo=tabela&regiao_campo=Sudeste+03").get_data(as_text=True)
    assert tabela.count('class="cn-link cn-os"') == 2
    tabela = logado.get("/t/campo/pt?modo=tabela&regiao_campo=Sul+01").get_data(as_text=True)
    assert "Nenhuma PT esperando o De acordo com esses filtros" in tabela


def test_estrutura_nao_publicada_avisa_e_nao_quebra(banco, logado):
    """Até a 1ª publicação do cadastro com a aba `regioes_campo`, o banco não tem a estrutura: a tela diz, tudo fica em
    "Sem região de campo" e o filtro de gestor (que já está no banco, pela usina) continua valendo."""
    _aba(banco, "cadastro_nexus", "regioes_campo", [])
    visao.limpar()
    for url in ("/t/campo/atencao?modo=regioes", "/t/campo/pt", "/t/campo/rondas", "/t/campo/rondas?aba=painel"):
        html = logado.get(url).get_data(as_text=True)
        assert "Estrutura de campo ainda não publicada" in html, url
    html = logado.get("/t/campo/atencao?modo=regioes").get_data(as_text=True)
    assert html.count('class="cn-equipe ') == 1 and "<b>Sem região de campo</b>" in html
    assert "Coração 1" in logado.get("/t/campo/atencao?modo=tabela&gestor=Ciclano+Chefe").get_data(as_text=True)
    # com a estrutura no banco, o aviso some
    _aba(banco, "cadastro_nexus", "regioes_campo", REGIOES)
    visao.limpar()
    assert "Estrutura de campo ainda não publicada" not in logado.get("/t/campo/atencao").get_data(as_text=True)


def test_rondas_filtram_por_regiao_de_campo_e_por_gestor_e_o_csv_leva_os_dois(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert 'id="cn-regiao-campo"' in html and 'id="cn-gestor"' in html and 'name="supervisor"' not in html
    assert '<option value="Sudeste 03">Sudeste 03 · Supervisora Campo</option>' in html
    assert "Coração 1" in logado.get("/t/campo/rondas?aba=sem&cob=nunca&regiao_campo=Sul+01").get_data(as_text=True)
    assert "Nenhuma ronda com esses filtros" in logado.get("/t/campo/rondas?regiao_campo=Sul+01").get_data(as_text=True)
    so_b = logado.get("/t/campo/rondas?gestor=Beltrano+Supervisor").get_data(as_text=True)
    assert "Altair" in so_b and '<option value="Beltrano Supervisor" selected>' in so_b
    assert "Coração 1" not in logado.get("/t/campo/rondas?aba=sem&cob=nunca&gestor=Beltrano+Supervisor").get_data(as_text=True)
    # o CSV leva a região de campo, o supervisor de campo e o gestor no FIM (as colunas de antes no mesmo lugar)
    csv = logado.get("/t/campo/rondas?csv=1").get_data(as_text=True)
    cab = csv.splitlines()[0].lstrip("﻿").split(";")
    assert cab[:2] == ["Data", "Técnico"] and cab[-3:] == ["Região de campo", "Supervisor de campo", "Gestor de contrato"]
    assert ";Sudeste 03;Supervisora Campo;Beltrano Supervisor" in csv


def test_detalhe_da_pt_e_historico_da_usina_dizem_regiao_e_gestor(banco, logado):
    html = logado.get("/t/campo/pt?modo=tabela").get_data(as_text=True)
    assert "<dt>Região de campo</dt><dd>Sudeste 03 · Supervisor de Campo Supervisora Campo</dd>" in html
    assert "<dt>Gestor de contrato</dt><dd>Beltrano Supervisor</dd>" in html and "· supervisor " not in html
    hist = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert ("região de campo Sudeste 03 (Supervisor de Campo: Supervisora Campo) · gestor de contrato Beltrano "
            "Supervisor") in hist


def test_ordens_imagens_e_ranking_sairam_do_menu_e_o_endereco_leva_a_central(logado):
    """Levi, 08/10: "ordens de serviço e imagens da ronda e ranking são redundantes"."""
    from nexus.torres import descobrir_torres
    campo = next(t for t in descobrir_torres() if t.id == "campo")
    assert not {"os", "imagens", "ranking"} & {t.id for t in campo.telas}
    menu = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert "Ordens de serviço" not in menu and "Imagens da ronda" not in menu and ">Ranking<" not in menu
    for tela in ("os", "imagens", "ranking"):
        r = logado.get(f"/t/campo/{tela}")
        assert r.status_code == 302 and r.headers["Location"].endswith("/t/campo/atencao"), tela
    assert not hasattr(visao, "ranking")


def test_historico_de_pt_continua_so_em_tabela(banco, logado):
    html = logado.get("/t/campo/pt?aba=historico&modo=regioes").get_data(as_text=True)
    assert "<th>Situação</th>" in html and "<b>Sudeste 03</b>" not in html


@pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")
@pytest.mark.parametrize("url", ["/t/campo/atencao?vista=pt&modo=tabela", "/t/campo/pt?modo=tabela",
                                 "/t/campo/pt?aba=historico"])
def test_scripts_da_central_e_da_pt_sao_javascript_valido(banco, logado, tmp_path, url):
    html = logado.get(url).get_data(as_text=True)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert scripts
    arq = tmp_path / "pagina.js"
    arq.write_text("\n;\n".join(scripts), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
