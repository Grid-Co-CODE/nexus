"""Central de atenção e Permissões de trabalho por supervisor (Levi, 08/10/2026: "além de por equipe e tabela, adicione
mais um botão (por supervisor). Faça o mesmo na tela permissões de trabalho"). Banco falso (o mesmo de
test_campo_visao.py): SP Norte 01 (Altair e Brodowski 1) é do Beltrano Supervisor, SC Oeste 01 (Coração 1) do Ciclano
Chefe; as duas PT esperando são da SP Norte 01."""
import re
import shutil
import subprocess

import pytest
from test_campo_visao import EQUIPES, USINAS, _MOB, _aba, banco  # noqa: F401  (banco é fixture)

from nexus.campo import visao


def _cartoes(html):
    """O pedaço dos cartões, sem os endereços, para comparar duas telas."""
    corpo = html[html.index('<div class="cn-equipes">'):html.index('<div class="cn-nota">')]
    return " ".join(re.sub(r'href="[^"]*"', "", corpo).split())


def test_por_supervisor_soma_os_cartoes_das_equipes(banco):
    d = visao.atencao(14).dados
    eq = visao.por_equipe(d["usinas"], d["pendentes"], [], d["pts"], d["times"])
    s = {x["supervisor"]: x for x in visao.por_supervisor(eq)}
    b, c = s["Beltrano Supervisor"], s["Ciclano Chefe"]
    assert (b["equipes"], b["n_equipes"], b["usinas"], b["pendentes"], b["feitas"], b["pct_feitas"]) == (
        ["SP Norte 01"], 1, 2, 1, 1, 50)
    assert (b["longa_pendente"], b["pts"], b["parada"], b["tecnicos"]) == (1, 2, 1, 2)
    assert (c["usinas"], c["pendentes"], c["pct_feitas"], c["nunca"], c["tecnicos"]) == (1, 1, 0, 1, 1)
    # dois cartões de equipe do mesmo supervisor viram um, com a soma e o % refeito sobre a soma
    junto = visao.por_supervisor([dict(eq[0], supervisor="X"), dict(eq[1], supervisor="X")])[0]
    assert (junto["n_equipes"], junto["usinas"], junto["pendentes"], junto["pct_feitas"]) == (2, 3, 2, 33)


def test_central_tem_o_botao_por_supervisor_e_o_cartao_leva_a_tabela_dele(banco, logado):
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert ">Por equipe</a>" in html and ">Por supervisor</a>" in html and ">Tabela</a>" in html
    html = logado.get("/t/campo/atencao?modo=supervisores").get_data(as_text=True)
    assert 'aria-current="page">Por supervisor</a>' in html and "<table>" not in html
    assert "<b>Beltrano Supervisor</b>" in html and "<b>Ciclano Chefe</b>" in html
    assert "1 equipe · 2 técnicos" in html and "<b>2 usinas</b>total" in html and "1 com a longa pendente" in html
    assert 'href="?modo=tabela&amp;supervisor=Beltrano+Supervisor"' in html
    # a ordem: quem tem mais pendentes primeiro, e no empate o menor % feito (Ciclano 0%, Beltrano 50%)
    assert html.index("<b>Ciclano Chefe</b>") < html.index("<b>Beltrano Supervisor</b>")
    tabela = logado.get("/t/campo/atencao?modo=tabela&supervisor=Beltrano+Supervisor").get_data(as_text=True)
    assert "<table>" in tabela and "Altair" in tabela and "Coração 1" not in tabela
    assert '<option value="Beltrano Supervisor" selected>' in tabela


def test_cartao_sem_supervisor_no_cadastro_e_proprio_e_acha_as_linhas(banco, logado):
    # uma equipe sem nenhum técnico no cadastro (medido em 05/10: SP Oeste 03, PI Leste 01, MS Leste 01)
    _aba(banco, "cadastro_nexus", "usinas", USINAS + [
        {"usina_id": 6, "nome": "Órfã", "codigo": "THPN-ORF100", "status": "OPERAÇÃO", "equipe_id": 30,
         "data_mobilizacao": _MOB, "uf": "MS", "cidade": "Órfã", "cliente_id": 1, "cluster": "MS Leste"}])
    _aba(banco, "cadastro_nexus", "equipes", EQUIPES + [{"equipe_id": 30, "nome": "MS Leste 01"}])
    visao.limpar()
    html = logado.get("/t/campo/atencao?modo=supervisores").get_data(as_text=True)
    assert "<b>Sem supervisor no cadastro</b>" in html and "cn-sup--sem" in html
    assert html.index("<b>Sem supervisor no cadastro</b>") > html.index("<b>Beltrano Supervisor</b>")    # por último
    assert 'href="?modo=tabela&amp;supervisor=Sem+supervisor"' in html
    tabela = logado.get("/t/campo/atencao?modo=tabela&supervisor=Sem+supervisor").get_data(as_text=True)
    assert "Órfã" in tabela and "Altair" not in tabela and '<option value="Sem supervisor" selected>' in tabela


def test_pt_por_supervisor_na_tela_de_pt_e_na_central_e_a_mesma(banco, logado):
    html = logado.get("/t/campo/pt?modo=supervisores").get_data(as_text=True)
    assert ">Por equipe</a>" in html and 'aria-current="page">Por supervisor</a>' in html and ">Tabela</a>" in html
    assert "<b>Beltrano Supervisor</b>" in html and "Ciclano Chefe</b>" not in html        # o Ciclano não tem PT
    assert "2</span><span class=\"d\">PT esperando o De acordo" in html and "1 parada há mais de 2 h" in html
    assert "1 equipe com PT esperando · 2 técnicos" in html
    assert 'href="?modo=tabela&amp;supervisor=Beltrano+Supervisor"' in html
    # _pt_esperando.html é o mesmo nas duas telas (Levi, 05/10): mudou uma, mudou a outra
    assert _cartoes(html) == _cartoes(logado.get("/t/campo/atencao?vista=pt&modo=supervisores").get_data(as_text=True))
    tabela = logado.get("/t/campo/pt?modo=tabela&supervisor=Beltrano+Supervisor").get_data(as_text=True)
    assert tabela.count('class="cn-link cn-os"') == 2
    tabela = logado.get("/t/campo/pt?modo=tabela&supervisor=Ciclano+Chefe").get_data(as_text=True)
    assert "Nenhuma PT esperando o De acordo com esses filtros" in tabela


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
    html = logado.get("/t/campo/pt?aba=historico&modo=supervisores").get_data(as_text=True)
    assert "<th>Situação</th>" in html and "<b>Beltrano Supervisor</b>" not in html


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
