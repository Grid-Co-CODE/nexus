"""Visão do responsável (Levi, 12/10/2026: "uma visão que ele olha as usinas, as metas, os problemas, onde ele deve focar,
no que ele deve deixar. No caso seria separado por responsável"). Banco falso do test_campo_visao: a Altair e a
Brodowski 1 são do responsável 91 (Ciclano Chefe) e a Coração 1 do 90 (Beltrano Supervisor). Por cima: a meta do mês
(Gerencial publicado), o diário da disponibilidade, os tickets, os sinais da Confiabilidade e as OS de falha (dublados:
nada vai ao Fracttal)."""
from datetime import datetime, timedelta, timezone

import pytest
from test_campo_visao import USINAS, _aba, banco  # noqa: F401  (banco é fixture)

from nexus.campo import responsaveis as R
from nexus.campo import visao
from nexus.engenharia import os_falhas

BRT = timezone(timedelta(hours=-3))
HOJE = datetime.now(BRT).date()
MES_ID, MES = HOJE.year * 100 + HOJE.month, HOJE.strftime("%Y-%m")
RESPONSAVEL = {1: 91, 2: 91, 3: 90}


def _meta(usina, prod, meta, ating, pr=80.0, pr_meta=79.0, mes_id=MES_ID):
    return {"mes_id": mes_id, "usina": usina, "cliente": "Thopen", "carteira": "Thopen", "prod_kwh": prod,
            "meta_kwh": meta, "atingimento_pct": ating, "pr_pct": pr, "pr_meta_pct": pr_meta, "ipoa_kwh_m2": 100,
            "ipoa_meta_kwh_m2": 100, "dias_cobertos_qtd": 10, "dias_mes_qtd": 31, "meta_dias_qtd": 10, "full_om": 1,
            "fonte": "pg", "meta_fonte": "BD_Thopen"}


def _disp(usina, dia, disp, h, fracttal=""):
    return {"mes": MES, "dia": dia, "cliente": "Thopen", "usina": usina, "usina_fracttal": fracttal, "pot_kwp": 1000,
            "disp": disp, "h_perdidas": h}


def _ticket(usina, inicio, fim=None, **kw):
    d = {"Usina": usina, "Código da usina": None, "Início da ocorrência": inicio, "Fim da ocorrência": fim,
         "Causa raiz": "", "Inversor": "1.1", "Quantidade de strings no afetadas": "2"}
    d.update(kw)
    return d


def _os(folio, tipo, ev_min_antes, *, dias=1, status=3, code="THPN-BWK100-INVR1", op="Fulano COS", site=None):
    cri = datetime.now(timezone.utc) - timedelta(days=dias)
    return {"wo_folio": folio, "tasks_log_task_type_main": tipo, "id_status_work_order": status,
            "creation_date": cri.isoformat(), "event_date": (cri - timedelta(minutes=ev_min_antes)).isoformat(),
            "created_by": op, "code": code, "groups_1_description": site or "Thopen - Brodowski 1 - SP",
            "parent_description": "", "items_log_description": ""}


SINAIS = [{"usina_id": 1, "nivel": "critico", "nome": "Inversor 1", "cod": "THPN-ALT100-INVR1", "fam": "Inversor",
           "porQue": ["4 falhas em 30 dias"], "nFalha": 4, "os": [{"url": "https://exemplo.test/os/1"}]},
          {"usina_id": 2, "nivel": "monitorar", "nome": "Tracker 9", "cod": "THPN-BWK100-TRK9", "fam": "Tracker",
           "porQue": [], "nFalha": 2, "os": []},
          {"usina_id": None, "nivel": "critico", "nome": "Sem usina", "cod": "X", "fam": "Outros", "porQue": [],
           "nFalha": 5, "os": []}]


@pytest.fixture
def tela(banco, monkeypatch):
    _aba(banco, "cadastro_nexus", "usinas", [dict(u, responsavel_om_id=RESPONSAVEL.get(u["usina_id"])) for u in USINAS])
    # a Brodowski 1 tem duas linhas no Gerencial, ligadas pelo de-para das abas (como Santarém 1 e 2)
    _aba(banco, "cadastro_nexus", "de_para", [
        {"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Altair 1 - SP"},
        {"usina_id": 2, "sistema": "BD_Thopen · aba", "chave_externa": "Brodowski I A"},
        {"usina_id": 2, "sistema": "BD_Thopen · aba", "chave_externa": "Brodowski I B"}])
    _aba(banco, "nexus_performance", "fato_meta_usina_mes", [
        _meta("Altair", 850000, 1000000, 85.0), _meta("Brodowski 1 A", 600000, 500000, 120.0, pr=82, pr_meta=80),
        _meta("Brodowski 1 B", 400000, 500000, 80.0, pr=78, pr_meta=80), _meta("Coração 1", 990000, 1000000, 99.0),
        _meta("Altair", 1, 1, 100.0, mes_id=MES_ID - 1)])           # outro mês não entra
    ontem = (HOJE - timedelta(days=1)).isoformat()
    _aba(banco, "falhas_performance", "disponibilidade_dia", [
        _disp("Altair", ontem, 100, 0, "Thopen - Altair 1 - SP"), _disp("Altair", ontem[:8] + "01", 70, 3.6),
        _disp("Brodowski 1", ontem, 100, 0), _disp("Coração 1", ontem, 99.5, 0.1)])
    _aba(banco, "tickets_performance", "Strings indisp", [
        _ticket("Altair", "2026-09-01 06:00:00"), _ticket("Altair", "2026-09-02 06:00:00", "2026-09-03 18:00:00"),
        _ticket("Ibirapuã", "2026-09-01 06:00:00")])               # nome que não está no cadastro: fica de fora
    _aba(banco, "tickets_performance", "Trackers", [
        _ticket("COR100", "2026-10-01 06:00:00", Status="Parado", **{"Nº do tracker / Identificação": "T12"}),
        _ticket("Coração 1", None, Status="Em conformidade")])     # check periódico, não é chamado
    monkeypatch.setattr(R, "_engenharia", lambda: {"dados": {"sinais": SINAIS}, "sem_cadastro": False})
    monkeypatch.setattr(os_falhas, "linhas", lambda: [
        _os("1", "Religamento", 120), _os("2", "Religamento", 120),                       # o lote: conta uma vez
        _os("3", "Religamento Remoto", 90), _os("4", "Religamento", -30),                  # evento depois: fora
        _os("5", "Religamento", 300, status=4), _os("6", "Corretiva", 500),                # cancelada e tipo fora
        _os("7", "Corretiva Emergencial", 400, dias=40), _os("8", "Religamento", 5, code="TESTE100-INVR1")])
    visao.limpar()
    return banco


def _por_usina():
    return {u["usina"]: u for u in R.visao_responsaveis().dados["usinas"]}


def test_cada_fonte_chega_a_usina_do_cadastro(tela):
    u = _por_usina()
    assert set(u) == {"Altair", "Brodowski 1", "Coração 1"}             # só as mobilizadas
    a, b, c = u["Altair"], u["Brodowski 1"], u["Coração 1"]
    assert (a["meta"]["atingimento"], a["meta"]["prod_kwh"]) == (85.0, 850000)
    # duas linhas no Gerencial: a produção e a meta somam, o atingimento é refeito e o PR é pesado pela meta
    assert (b["meta"]["prod_kwh"], b["meta"]["meta_kwh"], b["meta"]["atingimento"]) == (1000000, 1000000, 100.0)
    assert (b["meta"]["pr"], b["meta"]["pr_meta"]) == (80.0, 80.0)
    # a disponibilidade do mês é a média dos dias (12 h de sol por dia na régua do Gerencial)
    assert (a["disp"]["disp"], a["disp"]["h_perdidas"], a["disp"]["dias"]) == (85.0, 3.6, 2)
    assert a["ativos"]["critico"] == 1 and b["ativos"]["monitorar"] == 1 and not c["ativos"]
    # o COS: lote uma vez, evento depois e carimbo fora, cancelada, tipo fora, fora da janela e teste fora
    assert b["mtta"] == {"mediana_min": 105.0, "n": 2, "max_min": 120.0}
    # chamado aberto = sem fim; o nome que é código ("COR100") liga pelo código do cadastro; o check não conta
    assert (a["chamados"]["abertos"], a["chamados"]["strings"]) == (1, 1)
    assert (c["chamados"]["abertos"], c["chamados"]["trackers"]) == (1, 1)
    assert c["ronda"]["tipo"] == "nunca" and a["ronda"]["tipo"] == "longa_pendente"
    assert (a["pt"]["aguardando"], a["pt"]["paradas"], a["pt"]["paradas_antigas"]) == (2, 1, 1)
    info = R.visao_responsaveis().dados["info"]
    assert info["chamados"]["sem_usina"] == 1 and info["metas"]["publicado"]


def test_alertas_com_a_regua_da_tela_dona_e_o_foco(tela):
    u = _por_usina()
    al = {(x["area"], x["nivel"]) for x in u["Altair"]["alertas"]}
    assert {("meta", "critico"), ("disp", "atencao"), ("ativos", "critico"), ("chamados", "atencao"),
            ("ronda", "atencao"), ("pt", "critico"), ("pt", "atencao")} == al
    # a PT parada de dias anteriores é crítica, mas não "agora" (o técnico parado de hoje vai para o topo)
    assert not any(x["nivel"] == "agora" for x in u["Altair"]["alertas"])
    assert u["Altair"]["nivel"] == "critico" and u["Coração 1"]["nivel"] == "critico"
    b = u["Brodowski 1"]
    assert [(x["area"], x["nivel"]) for x in b["alertas"]] == [("mtta", "atencao")] and b["nivel"] == "atencao"
    assert "na meta (100%)" in b["bem"] and "disponibilidade 100,0%" in b["bem"] and "sem chamado aberto" in b["bem"]
    # o foco: quem tem mais peso em cima
    assert [x["usina"] for x in R.visao_responsaveis().dados["usinas"]][0] == "Altair"


def test_pt_parada_de_hoje_e_agora_e_vai_para_o_topo():
    hoje = datetime(2026, 10, 12, 15, tzinfo=BRT)
    pts = [{"usina_id": 1, "parada": True, "criada": hoje - timedelta(hours=3), "numero": "PT-9", "idade_min": 180},
           {"usina_id": 2, "parada": True, "criada": hoje - timedelta(days=2), "numero": "PT-8", "idade_min": 2880}]

    class B:
        mobilizadas = {1: {}, 2: {}}

        @staticmethod
        def onde(uid):
            return {k: f"{k}{uid}" for k in ("usina", "uf", "cidade", "equipe", "cliente", "regiao_campo", "gestor",
                                             "responsavel", "cluster")}
    vazias = {k: {} for k in ("metas", "disp", "ativos", "mtta", "chamados")}
    us = R.montar(B, [], [], pts, vazias, hoje.date())
    assert us[0]["usina_id"] == 1 and us[0]["alertas"][0]["nivel"] == "agora"
    assert us[1]["alertas"][0]["nivel"] == "critico" and "sem decisão desde 10/10" in us[1]["alertas"][0]["titulo"]


def test_cartoes_por_responsavel_e_o_resumo(tela):
    us = R.visao_responsaveis().dados["usinas"]
    c = {s["responsavel"]: s for s in R.por_responsavel(us)}
    ciclano, beltrano = c["Ciclano Chefe"], c["Beltrano Supervisor"]
    assert (ciclano["usinas"], ciclano["critico"], ciclano["atencao"], ciclano["ok"]) == (2, 1, 1, 0)
    assert ciclano["meta_pct"] == 92.5                                  # (850 + 1000) ÷ (1000 + 1000)
    assert ciclano["disp"] == 92.5 and ciclano["ativos_criticos"] == 1 and ciclano["pior"] == ["Altair"]
    assert (beltrano["usinas"], beltrano["critico"], beltrano["chamados"]) == (1, 1, 1)
    assert list(c)[0] == "Ciclano Chefe"                                # quem tem mais usina pedindo foco primeiro


def test_fonte_que_falha_nao_derruba_as_outras(tela, monkeypatch):
    def quebra(*a, **k):
        raise ConnectionError("tickets fora")
    monkeypatch.setattr(R, "chamados", quebra)
    visao.limpar()
    d = R.visao_responsaveis().dados
    assert "tickets fora" in d["erros"]["chamados"]
    u = {x["usina"]: x for x in d["usinas"]}
    assert u["Altair"]["meta"]["atingimento"] == 85.0 and not u["Altair"]["chamados"]


def test_tela_dos_cartoes_e_a_do_responsavel(tela, logado):
    html = logado.get("/t/campo/responsaveis").get_data(as_text=True)
    assert "Visão do responsável" in html and "Ciclano Chefe" in html and "Beltrano Supervisor" in html
    assert "responsavel=Ciclano+Chefe" in html                          # o cartão abre as usinas dele
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    focar = html[html.index('id="cr-critico"'):html.index('id="cr-atencao"')]
    acompanhar = html[html.index('id="cr-atencao"'):html.index('id="cr-ok"')]
    assert "Altair" in focar and "Meta do mês em 85%" in focar and "Brodowski 1" not in focar
    assert "Brodowski 1" in acompanhar and "COS leva 1 h 45 min para abrir a OS" in acompanhar
    assert "Coração 1" not in html.split("Todas as usinas")[1]          # é do outro responsável
    assert "Visão gerencial da plataforma" in html                      # a régua aparece na nota


def test_quem_entra_pelo_fracttal_cai_nas_usinas_dele(tela, cliente):
    from conftest import SENHA_TESTE
    cliente.post("/entrar", data={"senha": SENHA_TESTE})
    with cliente.session_transaction() as s:
        s["usuario"] = {"email": "beltrano@exemplo.test", "nome": "Beltrano Supervisor", "perfil": ""}
    html = cliente.get("/t/campo/responsaveis").get_data(as_text=True)
    assert '<option value="Beltrano Supervisor" selected>' in html and 'id="cr-critico"' in html
    # "Todos" vence o padrão
    html = cliente.get("/t/campo/responsaveis?responsavel=*").get_data(as_text=True)
    assert 'id="cr-critico"' not in html and "Ciclano Chefe" in html


def test_sem_a_meta_publicada_a_tela_avisa_e_nao_cobra(tela, logado):
    tela.abas.pop(("nexus_performance", "fato_meta_usina_mes"))      # o livro ainda não existe no banco
    tela.workbooks.pop("nexus_performance")
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    assert "A meta do mês ainda não chegou ao banco" in html
    u = _por_usina()
    assert not u["Altair"]["meta"] and not any(a["area"] == "meta" for a in u["Altair"]["alertas"])
