"""Central de atenção por Responsável O&M (Levi, 12/10/2026: "Precisamos deixar filtrado por responsável ... tem que
mostrar usinas desse responsável que nunca tiveram ronda, rondas pendentes e feitas! Ao clicar aparecerá um kanban com
essas três colunas!"). O responsável é o da ficha da USINA (`usinas.responsavel_om_id`), não o gestor de contrato.
Banco falso do test_campo_visao: a Altair (ronda longa pendente) e a Brodowski 1 (em dia) passam ao responsável 91
(Ciclano Chefe) e a Coração 1 (nunca teve ronda) ao 90 (Beltrano Supervisor): o contrário dos gestores delas."""
import re

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
    # "Por responsável" volta ao kanban dele (o responsável é filtro, 19/10/2026); "Todos" no filtro volta aos cartões
    assert "responsavel=Ciclano+Chefe" in _seg(tab).split(">Por responsável</a>")[0]
    assert "cn-kanban" not in logado.get("/t/campo/atencao?responsavel=*").get_data(as_text=True)
    assert "cn-kanban" not in logado.get("/t/campo/atencao?responsavel=").get_data(as_text=True)


def test_usina_sem_responsavel_vai_para_o_cartao_proprio(banco, logado):
    """No banco falso de antes (sem `responsavel_om_id`), as três usinas são do "Sem responsável O&M", que tem cartão
    próprio (tracejado) e o kanban dele."""
    html = logado.get("/t/campo/atencao?modo=responsaveis").get_data(as_text=True)
    assert "<b>" + visao.SEM_RESPONSAVEL.replace("&", "&amp;") + "</b>" in html and "cn-sup--sem" in html
    html = logado.get("/t/campo/atencao", query_string={"responsavel": visao.SEM_RESPONSAVEL}).get_data(as_text=True)
    col = _colunas(html)
    assert "Coração 1" in col["nunca"] and "Altair" in col["pendente"] and "Brodowski 1" in col["feita"]


# ── Só por responsável (Levi, 19/10/2026: "tire essa visão por região, e gestor de contrato. Uma visão só por responsável
# serve! tanto em Rondas pendentes quanto permissão de trabalho ... A tabela mantém"; os filtros "responsável UFV,
# cliente, Ufv, equipe e o canto para escrever", nas duas abas; e no kanban, "a equipe da usina, pode ser uma ou mais") ──
def _seg(html) -> str:
    """O seletor de visões (Por responsável | Tabela)."""
    ini = html.index('class="cn-seg"')
    return html[ini:html.index("</div>", ini)]


def test_a_central_so_tem_por_responsavel_e_a_tabela(com_responsavel, logado):
    for vista in ("pendentes", "pt"):
        html = logado.get(f"/t/campo/atencao?vista={vista}").get_data(as_text=True)
        seg = _seg(html)
        assert 'aria-current="page">Por responsável</a>' in seg and ">Tabela</a>" in seg, vista
        assert "Por equipe" not in seg and "Por região de campo" not in seg and "Gestor de contrato" not in html, vista
    # os endereços de antes (por equipe, região de campo, gestor, supervisor) abrem por responsável
    for modo in ("equipes", "regioes", "gestores", "supervisores"):
        html = logado.get(f"/t/campo/atencao?modo={modo}").get_data(as_text=True)
        assert 'aria-current="page">Por responsável</a>' in _seg(html) and "<b>Ciclano Chefe</b>" in html, modo


def test_pt_por_responsavel_e_o_cartao_leva_a_tabela_dele(com_responsavel, logado):
    html = logado.get("/t/campo/atencao?vista=pt").get_data(as_text=True)
    cartoes = html[html.index('class="cn-equipes"'):html.index('class="cn-nota"')]
    # a PT-1 (parada) e a PT-2 são da Altair, do Ciclano Chefe; o Beltrano não tem PT esperando: sem cartão
    assert "<b>Ciclano Chefe</b>" in cartoes and "Beltrano Supervisor" not in cartoes and "Responsável UFV" in cartoes
    assert '2</span><span class="d">PT esperando o De acordo' in cartoes and "1 parada há mais de 2 h" in cartoes
    href = re.search(r'<a class="cn-equipe[^"]*" href="([^"]*)"', cartoes).group(1).replace("&amp;", "&")
    assert "modo=tabela" in href and "responsavel=Ciclano+Chefe" in href and "vista=pt" in href
    tabela = logado.get("/t/campo/atencao" + href).get_data(as_text=True)
    assert tabela.count('class="cn-link cn-os"') == 2


def test_os_filtros_da_central_sao_responsavel_ufv_cliente_ufv_equipe_e_a_busca(com_responsavel, logado):
    for vista in ("pendentes", "pt"):
        html = logado.get(f"/t/campo/atencao?vista={vista}&modo=tabela").get_data(as_text=True)
        ini = html.index('class="cn-filtros"')
        form = html[ini:html.index("</form>", ini)]
        rotulos = re.findall(r'<label class="cn-filtro-par" for="[^"]+"><span class="gc-rotulo">([^<]+)</span>', form)
        assert rotulos == ["Responsável UFV", "Cliente", "UFV", "Equipe"], vista
        assert 'type="search" name="q"' in form, vista
        for fora in ('id="cn-regiao"', 'id="cn-regiao-campo"', 'id="cn-gestor"', "Responsável O&amp;M", "Região"):
            assert fora not in form, (vista, fora)
    # em cascata: escolhido o cliente, a lista de UFV e a de equipe trazem só as dele
    html = logado.get("/t/campo/atencao?modo=tabela&cliente=Thopen").get_data(as_text=True)
    ufv = html[html.index('id="cn-usina"'):]
    ufv = ufv[:ufv.index("</select>")]
    assert "Altair" in ufv and "Brodowski 1" in ufv and "Coração 1" not in ufv
    corpo = html[html.index("<tbody>"):html.index("</tbody>")]
    assert "Altair" in corpo and "Coração" not in corpo
    # a UFV e a equipe filtram as duas abas
    corpo = logado.get("/t/campo/atencao?modo=tabela&usina=Cora%C3%A7%C3%A3o+1").get_data(as_text=True)
    assert "Coração 1" in corpo[corpo.index("<tbody>"):] and "Altair" not in corpo[corpo.index("<tbody>"):]
    pt = logado.get("/t/campo/atencao?vista=pt&modo=tabela&equipe=SC+Oeste+01").get_data(as_text=True)
    assert "Nenhuma PT esperando o De acordo com esses filtros" in pt
    # a região de campo e o gestor saíram: o parâmetro de antes não filtra mais nada
    html = logado.get("/t/campo/atencao?modo=tabela&regiao_campo=Sul+01&gestor=Ciclano+Chefe").get_data(as_text=True)
    corpo = html[html.index("<tbody>"):html.index("</tbody>")]
    assert "Altair" in corpo and "Coração 1" in corpo


def test_o_kanban_mostra_a_equipe_da_usina(com_responsavel, logado):
    html = logado.get("/t/campo/atencao?responsavel=Ciclano+Chefe").get_data(as_text=True)
    col = _colunas(html)
    assert "<b>Equipe:</b> SP Norte 01" in col["pendente"] and "<b>Equipe:</b> SP Norte 01" in col["feita"]


def test_a_equipe_da_usina_pode_ser_mais_de_uma(com_responsavel, monkeypatch):
    # a do cadastro e as dos técnicos que a tela Técnicos por usina do PCM põe nela (um técnico da SC Oeste 01 na Altair)
    from nexus.pcm import atribuicoes as A
    monkeypatch.setattr(A, "ler", lambda cfg, forcar=False: {"decisoes": [], "erro": "", "lido_em": 0})
    monkeypatch.setattr(A, "atuais", lambda est, hoje: {(1, 4, "titular"): {"status": "vale"},
                                                       (2, 1, "titular"): {"status": "agendado"}})
    eq = visao.equipes_das_usinas([1, 2, 3])
    assert eq == {1: ["SC Oeste 01", "SP Norte 01"], 2: ["SP Norte 01"], 3: ["SC Oeste 01"]}
    # sem as atribuições, só a do cadastro
    monkeypatch.setattr(A, "ler", lambda cfg, forcar=False: (_ for _ in ()).throw(ConnectionError("banco fora")))
    assert visao.equipes_das_usinas([1]) == {1: ["SP Norte 01"]}
