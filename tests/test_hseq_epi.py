"""EPI e EPC (Segurança · HSEQ, Levi, 09/10/2026): "criasse um campo de EPI / EPC começando apenas por EPI, puxando as
luvas das rondas diárias". Banco falso do Campo (test_campo_visao.py): Altair respondeu Sim há 3 dias e Não ontem;
Brodowski 1 (ronda sem OS) respondeu Sim anteontem; Coração 1 nunca teve ronda."""
import re

import pytest
from test_campo_visao import _aba, _dia, _ronda, banco  # noqa: F401  (banco é fixture)

from nexus.campo import visao
from nexus.hseq import epi as EPI

CK = "Computador: Ligado; As luvas isolantes estão disponíveis?: {}; Banheiro: OK"


@pytest.fixture
def luvas(banco):
    _aba(banco, "rondas_app_campo", "OS de ronda", [
        _ronda(_dia(1), **{"Checklist da ronda": CK.format("Não")}),
        _ronda(_dia(3), **{"Checklist da ronda": CK.format("Sim")}),
        _ronda(_dia(2), usina="Thopen - Brodowski 1 - SP", ativo="THPN-BWK100", OS=None,
               **{"Situação da OS": "Não criada — Fracttal: Conecte", "Checklist da ronda": CK.format("Sim")})])
    visao.limpar()
    return banco


def test_a_resposta_sai_do_checklist_da_ronda():
    assert EPI.resposta(CK.format("Sim")) is True and EPI.resposta(CK.format("Não")) is False
    assert EPI.resposta("As luvas isolantes estão disponíveis?: Não [guardadas na cabine]") is False
    assert EPI.resposta("Computador: Ligado") is None and EPI.resposta(None) is None


def test_situacao_por_usina_pela_ultima_ronda(luvas):
    d = EPI.luvas().dados
    u = {x["usina"]: x for x in d["usinas"]}
    assert set(u) == {"Altair", "Brodowski 1", "Coração 1"}               # as mobilizadas, com ou sem resposta
    alt, bwk, cor = u["Altair"], u["Brodowski 1"], u["Coração 1"]
    assert (alt["situacao"], alt["desde"].isoformat(), alt["dias"], alt["nao"], alt["verificacoes"]) == (
        "sem_luvas", _dia(1), 1, 1, 2)
    assert [v["luvas"] for v in alt["historico"]] == [False, True]          # da mais nova para a mais velha
    assert (bwk["situacao"], bwk["dias"]) == ("com_luvas", 2)                # a ronda sem OS também vale
    assert (cor["situacao"], cor["ultima"]) == ("sem_verificacao", None)
    assert [x["usina"] for x in d["usinas"]] == ["Altair", "Coração 1", "Brodowski 1"]   # o mais grave primeiro
    assert EPI.contar(d["usinas"]) == {"usinas": 3, "sem_luvas": 1, "sem_verificacao": 1, "com_luvas": 1}
    # os cartões por responsável (24/10/2026): sem responsável no cadastro, um cartão só, com as usinas na ordem da
    # gravidade (sem luvas, sem verificação, com luvas)
    resp = EPI.por_responsavel(d["usinas"], d["times"])
    assert [s["responsavel"] for s in resp] == ["Sem responsável O&M"]
    assert [x["usina"] for x in resp[0]["lista"]] == ["Altair", "Coração 1", "Brodowski 1"]
    assert (resp[0]["sem_luvas"], resp[0]["sem_verificacao"], resp[0]["com_luvas"]) == (1, 1, 1)


def test_sim_antigo_vira_sem_verificacao():
    hoje = __import__("datetime").date(2026, 10, 9)
    v = [{"dia": __import__("datetime").date(2026, 10, 2), "inicio": "", "luvas": True, "tecnico": "", "os": None}]
    assert EPI._situacao(v, hoje)["situacao"] == "sem_verificacao"          # 7 dias: a régua da ronda pendente
    v[0]["dia"] = __import__("datetime").date(2026, 10, 3)
    assert EPI._situacao(v, hoje)["situacao"] == "com_luvas"


def test_tela_por_responsavel_e_tabela_com_as_fotos_da_ronda(luvas, logado):
    """Levi, 24/10/2026: "tirar visão de região de campo e gestor de contrato, tem que ser por responsável da usina, aí
    mostra as usinas"."""
    from test_campo_visao import USINAS
    _aba(luvas, "cadastro_nexus", "usinas", [dict(u, responsavel_om_id={1: 92, 2: 92, 3: 93}.get(u["usina_id"]))
                                             for u in USINAS])
    visao.limpar()
    html = logado.get("/t/hseq/epi").get_data(as_text=True)
    assert 'aria-current="page">EPI · luvas isolantes<i>1</i></a>' in html and 'aria-disabled="true"' in html
    assert 'aria-current="page">Por responsável</a>' in html and "Por supervisor" not in html
    texto = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert html.index("<b>Supervisora Campo</b>") < html.index("<b>Coordenador Campo</b>")     # mais sem luvas primeiro
    assert "1 usina sem luvas" in texto and "Sudeste 03" not in html and "Gestor de contrato" not in html
    # o cartão mostra as usinas dele, as sem luvas primeiro
    assert re.findall(r'class="hs-usina hs-usina--(\w+)"[^>]*>([^<]+)<', html) == [
        ("sem_luvas", "Altair"), ("com_luvas", "Brodowski 1"), ("sem_verificacao", "Coração 1")]
    # os filtros: região do Brasil, cliente, responsável UFV e a busca; sem região de campo nem gestor
    assert 'name="responsavel"' in html and 'name="regiao_campo"' not in html and 'name="gestor"' not in html
    so = logado.get("/t/hseq/epi?modo=tabela&responsavel=Coordenador+Campo").get_data(as_text=True)
    assert "Coração 1" in so and "Altair" not in so.split("cn-tab")[1]
    assert 'class="hs-legenda"' in html and "Como cada usina entra" in html
    tab = logado.get("/t/hseq/epi?f=sem_luvas").get_data(as_text=True)
    corpo = tab.split('class="hs-legenda"')[0]                             # o aviso do fim também tem o termo
    assert corpo.count('<span class="cn-st cn-t-critico">Sem luvas</span>') == 1 and "Coração 1" not in tab
    assert "<b>Não</b>" in tab and "1 Não em 2" in tab
    assert 'data-url="/t/campo/rondas/os/500/fotos"' in tab and 'class="cn-fotos-linha" hidden' in tab
    todas = logado.get("/t/hseq/epi?modo=tabela").get_data(as_text=True)
    assert "nunca verificada" in todas and "Ronda sem OS: as fotos ficam só no App" in todas


def test_checklist_sem_a_pergunta_das_luvas_a_tela_avisa(banco, logado):
    _aba(banco, "rondas_app_campo", "OS de ronda", [_ronda(_dia(1), **{"Checklist da ronda": "Computador: Ligado"})])
    visao.limpar()
    assert "Nenhuma ronda respondeu a pergunta das luvas" in logado.get("/t/hseq/epi").get_data(as_text=True)
