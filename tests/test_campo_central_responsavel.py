"""Central de atenção por Responsável O&M (Levi, 12/10/2026: "Precisamos deixar filtrado por responsável ... tem que
mostrar usinas desse responsável que nunca tiveram ronda, rondas pendentes e feitas! Ao clicar aparecerá um kanban com
essas três colunas!"). O responsável é o da ficha da USINA (`usinas.responsavel_om_id`), não o gestor de contrato.
Banco falso do test_campo_visao: a Altair (ronda longa pendente) e a Brodowski 1 (em dia) passam ao responsável 91
(Ciclano Chefe) e a Coração 1 (nunca teve ronda) ao 90 (Beltrano Supervisor): o contrário dos gestores delas."""
import pytest
from test_campo_visao import USINAS, _aba, banco  # noqa: F401  (banco é fixture)

from nexus.campo import visao

RESPONSAVEL = {1: 91, 2: 91, 3: 90}


@pytest.fixture
def com_responsavel(banco):
    _aba(banco, "cadastro_nexus", "usinas", [dict(u, responsavel_om_id=RESPONSAVEL.get(u["usina_id"])) for u in USINAS])
    visao.limpar()
    return banco


def _colunas(html) -> dict:
    """{coluna: o pedaço do kanban dela} (nunca, pendente, feita)."""
    out = {}
    for col in ("nunca", "pendente", "feita"):
        ini = html.index(f'id="kb-{col}"')
        fim = html.find("</section>", ini)
        out[col] = html[ini:fim]
    return out


def test_o_responsavel_e_o_da_ficha_da_usina_e_nao_o_gestor(com_responsavel):
    d = visao.atencao(14).dados
    u = {x["usina"]: x for x in d["usinas"]}
    assert (u["Altair"]["responsavel"], u["Altair"]["gestor"]) == ("Ciclano Chefe", "Beltrano Supervisor")
    assert (u["Coração 1"]["responsavel"], u["Coração 1"]["gestor"]) == ("Beltrano Supervisor", "Ciclano Chefe")
    # a usina leva a última ronda e quem a fez: o kanban mostra também as em dia
    assert u["Brodowski 1"]["ultima"] and u["Brodowski 1"]["usina_id"] == 2
    p = {x["usina"]: x for x in d["pendentes"]}
    assert p["Altair"]["responsavel"] == "Ciclano Chefe" and p["Altair"]["tipo"] == "longa_pendente"


def test_cartoes_por_responsavel_e_o_kanban_das_tres_colunas(com_responsavel):
    d = visao.atencao(14).dados
    r = {s["responsavel"]: s for s in visao.por_responsavel(d["usinas"], d["pendentes"])}
    c, b = r["Ciclano Chefe"], r["Beltrano Supervisor"]
    assert (c["usinas"], c["pendentes"], c["longa_pendente"], c["feitas"], c["pct_feitas"], c["equipes"]) == (
        2, 1, 1, 1, 50, ["SP Norte 01"])
    assert (b["usinas"], b["pendentes"], b["nunca"], b["feitas"], b["pct_feitas"]) == (1, 1, 1, 0, 0)
    dele = [u for u in d["usinas"] if u["responsavel"] == "Ciclano Chefe"]
    kb = visao.kanban(dele, [x for x in d["pendentes"] if x["responsavel"] == "Ciclano Chefe"])
    assert ([u["usina"] for u in kb["nunca"]], [u["usina"] for u in kb["pendente"]],
            [u["usina"] for u in kb["feita"]]) == ([], ["Altair"], ["Brodowski 1"])
    assert "ronda longa" in kb["pendente"][0]["obs"]
    todas = visao.kanban(d["usinas"], d["pendentes"])
    assert [u["usina"] for u in todas["nunca"]] == ["Coração 1"]
    # cada usina numa coluna só, e nenhuma some
    assert sum(len(v) for v in todas.values()) == len(d["usinas"])


def test_tela_por_responsavel_e_o_kanban_ao_clicar(com_responsavel, logado):
    html = logado.get("/t/campo/atencao?modo=responsaveis").get_data(as_text=True)
    assert 'aria-current="page">Por responsável</a>' in html and "<table>" not in html
    assert "<b>Ciclano Chefe</b>" in html and "<b>Beltrano Supervisor</b>" in html
    assert "responsavel=Ciclano+Chefe" in html                                   # o cartão abre o kanban dele
    # o clique (ou o filtro) abre o kanban: três colunas, cada usina na sua, e o cartão leva ao histórico da usina
    html = logado.get("/t/campo/atencao?responsavel=Ciclano+Chefe").get_data(as_text=True)
    assert 'class="cn-kanban"' in html and '<option value="Ciclano Chefe" selected>' in html
    col = _colunas(html)
    assert "Nunca teve ronda" in col["nunca"] and "Nenhuma usina." in col["nunca"]
    assert "Altair" in col["pendente"] and "Brodowski" not in col["pendente"]
    assert "Brodowski 1" in col["feita"] and "Última ronda" in col["feita"]
    assert 'href="/t/campo/rondas/usina/1"' in html and 'href="/t/campo/rondas/usina/2"' in html
    assert "Coração" not in html.split('class="cn-kanban"')[1].split('class="cn-nota"')[0]   # é do outro responsável
    # a tabela continua a um clique, só com as pendentes dele
    tab = logado.get("/t/campo/atencao?responsavel=Ciclano+Chefe&modo=tabela").get_data(as_text=True)
    corpo = tab[tab.index("<tbody>"):tab.index("</tbody>")]
    assert "Altair" in corpo and "Coração" not in corpo and "Brodowski" not in corpo
    # os outros modos tiram o responsável; "Todos" no filtro volta ao padrão
    assert "Por equipe</a>" in tab and "responsavel=Ciclano" not in tab.split("Por equipe</a>")[0].split('class="cn-seg"')[1]
    assert "cn-kanban" not in logado.get("/t/campo/atencao?responsavel=*").get_data(as_text=True)


def test_usina_sem_responsavel_vai_para_o_cartao_proprio(banco, logado):
    """No banco falso de antes (sem `responsavel_om_id`), as três usinas são do "Sem responsável O&M", que tem cartão
    próprio (tracejado) e o kanban dele."""
    html = logado.get("/t/campo/atencao?modo=responsaveis").get_data(as_text=True)
    assert "<b>" + visao.SEM_RESPONSAVEL.replace("&", "&amp;") + "</b>" in html and "cn-sup--sem" in html
    html = logado.get("/t/campo/atencao", query_string={"responsavel": visao.SEM_RESPONSAVEL}).get_data(as_text=True)
    col = _colunas(html)
    assert "Coração 1" in col["nunca"] and "Altair" in col["pendente"] and "Brodowski 1" in col["feita"]
