"""Visão do responsável (Levi, 12/10/2026: "uma visão que ele olha as usinas, as metas, os problemas, onde ele deve focar,
no que ele deve deixar. No caso seria separado por responsável"; protótipo aprovado: dois blocos, Performance e
Acompanhamento, linha que abre o detalhe, extintores no acompanhamento e "só tira a parte de Tempo do COS").
Banco falso do test_campo_visao: a Altair e a Brodowski 1 são do responsável 91 (Ciclano Chefe) e a Coração 1 do 90
(Beltrano Supervisor). Por cima: a meta do mês (Gerencial publicado), o diário da disponibilidade, os chamados no banco
(`nexus_chamados`), os extintores do App e os sinais da Confiabilidade (dublados: nada vai ao Fracttal)."""
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_campo_visao import USINAS, _aba, _dia, _ronda, banco  # noqa: F401  (banco é fixture)

from nexus.campo import responsaveis as R
from nexus.campo import ronda_checklist, visao
from nexus.dados import fato_chamado as F

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


def _chamado(os_, usina_id, situacao, dias_atras, equipamento_id=None, fab="STI", comp="Estrutura Trackers"):
    d = HOJE - timedelta(days=dias_atras)
    return dict(zip(F.CAB_CHAMADO, [os_, d.year * 10000 + d.month * 100 + d.day, None, usina_id, "de-para do Fracttal",
                                    "Thopen - X - SP", equipamento_id, "código do ativo" if equipamento_id else None,
                                    "THPN-ALT100-ETKR1", situacao, fab, comp, None]))


def _ext(codigo, usina, val2, conf_dias, cb=""):
    """Uma linha do livro `extintores_app_campo · Extintores` (o contrato com o App, `hseq/extintores.COLUNAS`)."""
    return {"Código": codigo, "Usina": usina, "Código da usina": cb, "Tipo de ativo": "CABN", "Ativo": "",
            "Local": "Cabine", "Posição": "Interno", "Classe": "ABC pó", "Peso (kg)": 6, "Validade da recarga": val2,
            "Validade do hidrostático": "2099", "Última conferência": (HOJE - timedelta(days=conf_dias)).isoformat(),
            "Origem da conferência": "App", "Conferido por (HMAC)": None, "Carga": "CARREGADO", "Itens NÃO": None,
            "Fotos": 1, "Tem informação adicional": "não", "Status": None, "Motivo": None,
            "Origem do cadastro": "Planilha da TST"}


SINAIS = [{"usina_id": 1, "nivel": "critico", "nome": "Inversor 1", "cod": "THPN-ALT100-INVR1", "fam": "Inversor",
           "porQue": ["4 falhas em 30 dias"], "nFalha": 4, "os": []},
          {"usina_id": 2, "nivel": "monitorar", "nome": "Tracker 9", "cod": "THPN-BWK100-TRK9", "fam": "Tracker",
           "porQue": [], "nFalha": 2, "os": []}]


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
    _aba(banco, "nexus_chamados", "fato_chamado", [
        _chamado(16034, 1, "aberto", 26, equipamento_id=900), _chamado(16040, 2, "verificacao", 3),
        _chamado(15000, 1, "concluido", 20), _chamado(16050, 3, "aberto", 2, fab="Convert", comp="Cabine"),
        _chamado(16060, None, "aberto", 5)])                         # sem usina no cadastro: fica de fora, contado
    _aba(banco, "nexus_equipamentos", "dim_equipamento", [
        {"equipamento_id": 900, "codigo": "THPN-ALT100-ETKR1", "descricao": "Tracker 1 STI", "usina_id": 1}])
    este_mes = f"{HOJE.month:02d}/{HOJE.year}"                        # vale até o fim do mês: vence em até 30 dias
    _aba(banco, "extintores_app_campo", "Extintores", [
        _ext("ALT100-EXT01", "Thopen - Altair 1 - SP", "01/2020", 5),   # vencido
        _ext("ALT100-EXT02", "Thopen - Altair 1 - SP", "12/2099", 5),   # em dia
        _ext("COR100-EXT01", "Coração", este_mes, 5, cb="THPN-COR100"),  # vence em até 30 dias
        _ext("COR100-EXT02", "Coração", "12/2099", 60, cb="THPN-COR100")])  # sem conferência há 60 dias
    # as janelas (12/10/2026): a série do PR diário do Painel NOC e as OS que formaram a disponibilidade
    d1, d2 = (HOJE.replace(day=1), HOJE.replace(day=2))
    _aba(banco, "nexus_performance", "fato_desempenho_usina_dia", [
        {"mes_id": MES_ID, "usina": "Altair", "data_id": int(d1.strftime("%Y%m%d")), "geracao_kwh": 37000, "meta_kwh": 40000,
         "ipoa_kwh_m2": 7.4, "ipoa_meta_kwh_m2": 7.7, "pr_pct": 74.3, "pr_meta_pct": 76.0},
        {"mes_id": MES_ID, "usina": "Altair", "data_id": int(d2.strftime("%Y%m%d")), "geracao_kwh": 5800, "meta_kwh": 40000,
         "ipoa_kwh_m2": 1.4, "ipoa_meta_kwh_m2": 7.7, "pr_pct": 61.3, "pr_meta_pct": 76.0},
        # o dia só do PR diário (13/10/2026): sem geração, fora da conta do Gerencial e da tabela da Meta, com PR no gráfico
        {"mes_id": MES_ID, "usina": "Altair", "data_id": int(HOJE.replace(day=3).strftime("%Y%m%d")), "geracao_kwh": None,
         "meta_kwh": 40000, "ipoa_kwh_m2": 5.0, "ipoa_meta_kwh_m2": 7.7, "pr_pct": 70.0, "pr_meta_pct": 76.0},
        {"mes_id": MES_ID, "usina": "Coração 1", "data_id": int(d1.strftime("%Y%m%d")), "geracao_kwh": 1, "meta_kwh": 1,
         "ipoa_kwh_m2": 1, "ipoa_meta_kwh_m2": 1, "pr_pct": 1, "pr_meta_pct": 1}])
    _aba(banco, "falhas_performance", "disponibilidade_os", [
        {"mes": MES, "os": "13001", "usina": "Altair", "usina_fracttal": "Thopen - Altair 1 - SP", "tipo": "Religamento Remoto",
         "origem": "queda", "codigo_ativo": "THPN-ALT100", "escopo": "Usina inteira", "kwp": 6898,
         "inicio": f"{MES}-01T09:00:00", "fim": f"{MES}-01T15:06:00", "aberta": "não", "duracao_sol_min": 366,
         "perda_kwh": 42077},
        {"mes": MES, "os": "13002", "usina": "Altair", "usina_fracttal": "Thopen - Altair 1 - SP",
         "tipo": "Corretiva Emergencial", "origem": "equipamento", "codigo_ativo": "THPN-ALT100-INVR1", "escopo": "Inversor 1",
         "kwp": 250, "inicio": f"{MES}-02T08:00:00", "fim": None, "aberta": "sim", "duracao_sol_min": 120, "perda_kwh": 500}])
    monkeypatch.setattr(R, "_engenharia", lambda: {"dados": {"sinais": SINAIS}, "sem_cadastro": False})
    # a Limpeza (18/10/2026) lê também as respostas das OS de ronda que o processo guardou na memória (a fila da
    # Aprovação, as aprovadas): outro teste pode ter deixado alguma, e a sujidade de lá viraria alerta aqui
    monkeypatch.setattr(ronda_checklist, "respostas", lambda: {})
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
    assert (a["disp"]["disp"], a["disp"]["h_perdidas"], a["disp"]["dias"]) == (85.0, 3.6, 2)
    assert a["ativos"]["critico"] == 1 and b["ativos"]["monitorar"] == 1 and not c["ativos"]
    # chamados = o fato do banco (as OS de acompanhamento), com o nome do equipamento pela dimensão; concluído não conta
    assert (a["chamados"]["abertos"], a["chamados"]["verificacao"]) == (1, 0)
    # o ativo sem a marca e o status do chamado (28/10/2026, o Painel do responsável): o fato falso não tem status
    assert a["chamados"]["lista"][0] == {"os": 16034, "situacao": "aberto", "dias": 26, "equip": "Tracker 1 STI",
                                         "ativo": "Tracker 1", "status": "",
                                         "fabricante": "STI", "componente": "Estrutura Trackers"}
    assert (b["chamados"]["abertos"], b["chamados"]["verificacao"]) == (0, 1) and c["chamados"]["abertos"] == 1
    # extintores = a conta do HSEQ
    assert (a["extintores"]["total"], a["extintores"]["vencidos"]) == (2, 1)
    assert (c["extintores"]["a_vencer"], c["extintores"]["sem_conferir"]) == (1, 1)
    assert c["ronda"]["tipo"] == "nunca" and a["ronda"]["tipo"] == "longa_pendente"
    assert (a["pt"]["aguardando"], a["pt"]["paradas"], a["pt"]["paradas_antigas"]) == (2, 1, 1)
    info = R.visao_responsaveis().dados["info"]
    assert info["chamados"] == {"publicado": True, "abertos": 3, "sem_usina": 1}
    assert info["metas"]["publicado"] and info["extintores"]["publicado"]


def test_os_dois_blocos_com_a_regua_da_tela_dona(tela):
    u = _por_usina()
    a, b, c = u["Altair"], u["Brodowski 1"], u["Coração 1"]
    assert {(x["area"], x["nivel"]) for x in a["perf"]["alertas"]} == {("meta", "critico"), ("disp", "atencao"),
                                                                       ("ativos", "critico")}
    assert {(x["area"], x["nivel"]) for x in a["acomp"]["alertas"]} == {
        ("ronda", "atencao"), ("pt", "critico"), ("pt", "atencao"), ("chamados", "atencao"), ("extintores", "critico")}
    # a PT parada de dias anteriores é crítica, mas não "agora" (o técnico parado de hoje vai para o topo)
    assert not any(x["nivel"] == "agora" for x in a["acomp"]["alertas"])
    assert (b["perf"]["nivel"], b["acomp"]["nivel"]) == ("ok", "ok")
    assert "na meta (100%)" in b["perf"]["bem"] and "sem chamado aberto" in b["acomp"]["bem"]
    assert (c["perf"]["nivel"], c["acomp"]["nivel"]) == ("ok", "critico")
    # a vencer pesa mais que "sem conferência": o do mesmo extintor não alerta duas vezes
    assert [x["titulo"] for x in c["acomp"]["alertas"] if x["area"] == "extintores"] == ["1 extintor vence em até 30 dias"]
    # o Tempo do COS saiu (protótipo aprovado, 12/10/2026)
    assert all(a != "mtta" for _b, a, _r, _t in R.REGUAS) and not any("COS" in x["titulo"] for x in a["acomp"]["alertas"])
    # a linha compacta e o detalhe
    assert a["perf"]["valores"]["meta"] == {"txt": "85%", "cls": "critico", "sub": ""}
    assert a["acomp"]["valores"]["extintores"] == {"txt": "1 vencido", "cls": "critico", "sub": ""}
    assert a["perf"]["tag"] == ("critico", "1 ativo crítico")
    # esperando o De acordo é só PT (Levi, 12/10/2026: "na verdade esperando de acordo é só PT então mostra só PT")
    assert [i["rot"] for i in a["acomp"]["det"]] == ["Ronda", "PT", "Chamados", "Extintores"]


def test_cada_bloco_mostra_todas_as_usinas_na_ordem_dele(tela):
    """Levi, 13/10/2026: "Tem que aparecer todas as usinas do responsável inclusive as que estão em dia" e "Ordene da
    pior meta para a melhor em performance e em acompanhamento ordene pelas rondas"."""
    us = R.visao_responsaveis().dados["usinas"]
    perf, acomp = R.bloco(us, "perf"), R.bloco(us, "acomp")
    # a meta: Altair 85%, Coração 1 99%, Brodowski 1 100% (as duas linhas do Gerencial somadas)
    assert [u["usina"] for u in perf["linhas"]] == ["Altair", "Coração 1", "Brodowski 1"]
    # a ronda: a Coração 1 nunca teve; a Altair tem a longa pendente; a Brodowski 1 por último
    assert [u["usina"] for u in acomp["linhas"]] == ["Coração 1", "Altair", "Brodowski 1"]
    assert "em_dia" not in perf
    assert perf["tri"] == {"critico": 1, "atencao": 0, "ok": 2} and acomp["tri"] == {"critico": 2, "atencao": 0, "ok": 1}


def test_a_ordem_da_ronda_e_da_meta():
    def u(nome, tipo=None, dias=None, ating=None):
        return {"usina": nome, "ronda": {"tipo": tipo, "dias": dias}, "meta": {"atingimento": ating}}
    us = [u("Hoje", dias=0), u("Quatro dias", dias=4), u("Sem dado", dias=999), u("Longa", "longa_pendente", 2),
          u("Treze dias", "sem_ronda", 13), u("Oito dias", "sem_ronda", 8), u("Nunca", "nunca", 999)]
    assert [x["usina"] for x in sorted(us, key=R.ordem_da_ronda)] == [
        "Nunca", "Treze dias", "Oito dias", "Longa", "Quatro dias", "Hoje", "Sem dado"]
    ms = [u("B", ating=99.0), u("Sem meta"), u("A", ating=45.0), u("C", ating=120.0)]
    assert [x["usina"] for x in sorted(ms, key=R.ordem_da_meta)] == ["A", "B", "C", "Sem meta"]


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
    vazias = {k: {} for k in ("metas", "disp", "ativos", "chamados", "extintores")}
    us = R.montar(B, [], [], pts, vazias, hoje.date())
    assert us[0]["usina_id"] == 1 and us[0]["acomp"]["alertas"][0]["nivel"] == "agora"
    assert us[0]["acomp"]["det"][0]["itens"][0]["agora"]
    assert "sem decisão desde 10/10" in us[1]["acomp"]["alertas"][0]["titulo"]


def test_cartoes_por_responsavel_com_os_dois_blocos(tela):
    us = R.visao_responsaveis().dados["usinas"]
    c = {s["responsavel"]: s for s in R.por_responsavel(us)}
    ciclano, beltrano = c["Ciclano Chefe"], c["Beltrano Supervisor"]
    assert ciclano["perf"] == {"critico": 1, "atencao": 0, "ok": 1} and ciclano["acomp"] == {"critico": 1, "atencao": 0, "ok": 1}
    assert ciclano["meta_pct"] == 92.5 and ciclano["disp"] == 92.5                 # (850 + 1000) ÷ (1000 + 1000)
    assert (ciclano["abaixo_meta"], ciclano["pr_abaixo"], ciclano["chamados"], ciclano["ext_vencidos"]) == (1, 0, 1, 1)
    assert ciclano["ativos_criticos"] == 1 and ciclano["pior"] == ["Altair"]
    assert beltrano["perf"] == {"critico": 0, "atencao": 0, "ok": 1} and beltrano["acomp"]["critico"] == 1
    assert list(c)[0] == "Ciclano Chefe"                                # quem tem mais usina pedindo foco primeiro


def test_fonte_que_falha_nao_derruba_as_outras(tela, monkeypatch):
    def quebra(*a, **k):
        raise ConnectionError("banco dos chamados fora")
    monkeypatch.setattr(R, "chamados", quebra)
    visao.limpar()
    d = R.visao_responsaveis().dados
    assert "banco dos chamados fora" in d["erros"]["chamados"]
    u = {x["usina"]: x for x in d["usinas"]}
    assert u["Altair"]["meta"]["atingimento"] == 85.0 and not u["Altair"]["chamados"]


def test_tela_dos_cartoes_e_a_dos_dois_blocos(tela, logado):
    html = logado.get("/t/campo/responsaveis").get_data(as_text=True)
    assert "Visão do responsável" in html and "Ciclano Chefe" in html and "Beltrano Supervisor" in html
    assert "responsavel=Ciclano+Chefe" in html and "Extintores vencidos" in html   # o cartão abre as usinas dele
    # escolhido o responsável, o Painel (Levi, 28/10/2026: "uma tela inicial claro, se for para se aprofundar aí é outro
    # nível"); a Visão geral (18/10/2026, no lugar de Onde focar) é a aba do outro nível
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    assert 'aria-current="page">Painel' in html and '<h1 class="cn-titulo">Ciclano Chefe</h1>' in html
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe&modo=geral").get_data(as_text=True)
    assert 'aria-current="page">Visão geral' in html
    lista = _bloco_manut(html)
    assert "Altair" in lista and "85%" in lista and "1 ativo crítico" in lista
    assert "Brodowski 1" in lista and "usina em dia</b>" not in lista        # em dia vira linha (13/10/2026)
    assert "1 vencido" in lista and "Tracker 1 STI" in lista and "aberto há 26 d" in lista
    assert "Coração 1" not in html                                         # é do outro responsável
    assert "Tempo do COS" not in html and "Visão gerencial da plataforma" in html


def test_quem_entra_pelo_fracttal_cai_nas_usinas_dele(tela, cliente):
    from conftest import SENHA_TESTE
    cliente.post("/entrar", data={"senha": SENHA_TESTE})
    with cliente.session_transaction() as s:
        s["usuario"] = {"email": "beltrano@exemplo.test", "nome": "Beltrano Supervisor", "perfil": ""}
    html = cliente.get("/t/campo/responsaveis").get_data(as_text=True)
    # desde 28/10/2026 ele entra no Painel dele (a tela inicial); a Visão geral é a aba ao lado
    assert '<option value="Beltrano Supervisor" selected>' in html and 'class="pn"' in html
    # o responsável logado não vê os cartões (Levi, 12/10/2026: "não vai aparecer por responsável, já vai direto para
    # Onde Focar!"): nem pelo endereço; "Todos" mostra as usinas de todos, ainda nos dois blocos
    assert ">Por responsável</a>" not in html
    html = cliente.get("/t/campo/responsaveis?responsavel=*&modo=cartoes").get_data(as_text=True)
    assert 'class="cr-gr"' in html and 'class="cn-equipes"' not in html and "Ciclano Chefe" in html


def test_sem_a_meta_e_sem_os_chamados_no_banco_a_tela_avisa_e_nao_cobra(tela, logado):
    for livro, aba in (("nexus_performance", "fato_meta_usina_mes"), ("nexus_chamados", "fato_chamado")):
        tela.abas.pop((livro, aba))                                        # os livros ainda não existem no banco
        tela.workbooks.pop(livro)
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    assert "A meta do mês ainda não chegou ao banco" in html and "Os chamados ainda não chegaram ao banco" in html
    u = _por_usina()
    assert not u["Altair"]["meta"] and not any(a["area"] == "meta" for a in u["Altair"]["perf"]["alertas"])
    assert not u["Altair"]["chamados"] and u["Altair"]["acomp"]["valores"]["chamados"]["txt"] == "—"


def test_dia_do_id():
    assert R._dia_do_id(20261012) == date(2026, 10, 12) and R._dia_do_id(None) is None and R._dia_do_id(20261399) is None


# ── As janelas por cima da tela (12/10/2026) ─────────────────────────────────────────────────────────────────────────
def test_a_tabela_da_meta_dia_a_dia_com_o_total_do_gerencial(tela):
    nomes = R.Nomes(visao._Base())
    serie = R.serie_diaria(1, MES_ID, nomes)
    assert [d["dia"] for d in serie["dias"]] == [1, 2, 3] and serie["usinas_gerencial"] == ["Altair"]
    assert serie["dias"][2]["geracao_kwh"] is None and serie["dias"][2]["pr"] == 70.0
    t = R.tabela_meta(serie)
    assert [(l["dia"], l["meta"], l["real"], l["pct"], l["cls"]) for l in t["linhas"]] == [
        (1, 40.0, 37.0, 92, "alerta"), (2, 40.0, 5.8, 14, "critico")]
    assert {k: t["total"][k] for k in ("meta", "real", "dif", "pct", "cls")} == {
        "meta": 80.0, "real": 42.8, "dif": -37.2, "pct": 53.5, "cls": "critico"}
    assert t["total"]["poa"] == 8.8                                    # 7,4 + 1,4: a soma do POA dos dias da tabela


def test_a_tabela_da_meta_leva_o_poa_e_a_disponibilidade_do_dia():
    """Levi, 13/10/2026: "na tabelinha da meta por dia você adicione o POA DEF e a disponibilidade!". O POA do dia vem da
    série; a disponibilidade, do dia fechado (vazia antes de fechar); no total, a soma do POA e a disponibilidade do mês."""
    serie = {"dias": [{"dia": 1, "geracao_kwh": 9000, "meta_kwh": 10000, "ipoa": 6.2},
                      {"dia": 2, "geracao_kwh": 3000, "meta_kwh": 10000, "ipoa": None},
                      {"dia": 3, "geracao_kwh": 2000, "meta_kwh": 10000, "ipoa": 1.1}]}
    disp = {"dias": [{"dia": 1, "disp": 100.0}, {"dia": 2, "disp": 40.0}], "ate": "2026-10-02"}
    t = R.tabela_meta(serie, disp, 70.0)
    assert [(l["dia"], l["poa"], l["disp"], l["disp_cls"]) for l in t["linhas"]] == [
        (1, 6.2, 100.0, "ok"), (2, None, 40.0, "critico"), (3, 1.1, None, "neutro")]
    assert t["total"]["poa"] == 7.3 and t["total"]["disp"] == 70.0 and t["total"]["disp_cls"] == "critico"
    assert t["disp_ate"] == "2026-10-02" and t["com_disp"]
    # sem a disponibilidade (usina fora do Gerencial › Disponibilidade): a coluna fica vazia, a conta da meta é a mesma
    t2 = R.tabela_meta(serie)
    assert [l["disp"] for l in t2["linhas"]] == [None, None, None] and not t2["com_disp"] and t2["total"]["pct"] == t["total"]["pct"]


def test_os_graficos_da_geracao_com_poa_e_da_curva_do_pr():
    from nexus.campo import responsaveis_graficos as G
    dias = [{"dia": 1, "geracao_kwh": 40000, "meta_kwh": 40000, "ipoa": 7.4, "ipoa_meta": 7.7, "pr": 94.0, "pr_meta": 76.0},
            {"dia": 2, "geracao_kwh": 37000, "meta_kwh": 40000, "ipoa": 2.6, "ipoa_meta": 7.7, "pr": 74.3, "pr_meta": 76.0},
            {"dia": 3, "geracao_kwh": 5800, "meta_kwh": 40000, "ipoa": None, "ipoa_meta": 7.7, "pr": None, "pr_meta": 76.0},
            {"dia": 4, "geracao_kwh": 9000, "meta_kwh": 40000, "ipoa": 1.8, "ipoa_meta": 7.7, "pr": 61.3, "pr_meta": 76.0}]
    g = G.geracao(dias, 31)
    # a barra pela meta do dia, a régua do Gerencial: 100% ok, 92% atenção, 14% crítico
    assert [b["cls"] for b in g["barras"]] == ["ok", "alerta", "critico", "critico"]
    # o dia sem POA quebra a linha: o dia 4, sozinho depois do buraco, fica só como ponto
    assert len(g["poa"]) == 1 and len(g["poa_pontos"]) == 3 and g["meta_y"] is not None and g["meta"] == "40,0"
    q = G.pr(dias, 31)
    assert len(q["linha"]) == 1 and [p["cls"] for p in q["pontos"]] == ["ok", "alerta", "alerta"]
    # os rótulos não se encavalam: o PR da Cipó Guaçu de outubro (13/10/2026), dia a dia
    cipo = [36.0, 96.0, 82.0, 75.0, 94.8, 93.0, 88.7, 70.0, 72.1, 70.9, 91.0, 89.6]
    q = G.pr([{"dia": i + 1, "pr": v, "pr_meta": 76.9} for i, v in enumerate(cipo)], 31)
    pts = q["pontos"]
    assert all(abs(a["x"] - b["x"]) >= G.ROT_LARG or abs(a["ry"] - b["ry"]) >= G.ROT_ALT for a, b in zip(pts, pts[1:]))
    assert pts[0]["rotulo"] == "36,0" and pts[0]["ry"] < pts[0]["y"]          # sem o "%", e em cima quando cabe
    assert q["grades"][-1]["rotulo"] == "125%" and q["grades"][0]["rotulo"] == "0%"   # 94% + folga: 125%, não 200%


def test_as_janelas_de_meta_pr_e_disponibilidade(tela, logado):
    html = logado.get("/t/campo/responsaveis/usina/1/meta").get_data(as_text=True)
    assert "<html" not in html and "Meta do mês" in html and "Geração da meta" in html and "Total" in html
    assert "42,8 MWh" in html and "53,5%" in html
    assert "POA DEF" in html and "Disponibilidade</th>" in html and "7,40" in html          # o POA do dia 1 da Altair
    html = logado.get("/t/campo/responsaveis/usina/1/pr").get_data(as_text=True)
    assert "<svg" in html and "cr-barra--alerta" in html and "cr-linha-poa" in html and "cr-linha-pr" in html
    html = logado.get("/t/campo/responsaveis/usina/1/disp").get_data(as_text=True)
    assert "Mapa diário" in html and "cr-cel--" in html
    assert "13001" in html and "Religamento Remoto" in html and "42077 kWh" in html and "em aberto" in html
    assert "6 h 6 min" in html                                              # do início ao fim da OS 13001
    assert logado.get("/t/campo/responsaveis/usina/1/outra").status_code == 404
    assert logado.get("/t/campo/responsaveis/usina/999/meta").status_code == 404


def test_a_janela_sem_a_serie_no_banco_diz_o_porque(tela, logado):
    for livro, aba in (("nexus_performance", "fato_desempenho_usina_dia"), ("falhas_performance", "disponibilidade_os")):
        tela.abas.pop((livro, aba))
    visao.limpar()
    assert "ainda não chegou ao banco" in logado.get("/t/campo/responsaveis/usina/1/pr").get_data(as_text=True)
    assert "A lista de OS ainda não chegou" in logado.get("/t/campo/responsaveis/usina/1/disp").get_data(as_text=True)


def test_a_pt_por_cima_decide_e_volta_para_a_visao(tela, logado):
    volta = "/t/campo/responsaveis?responsavel=Ciclano+Chefe"
    html = logado.get("/t/campo/responsaveis/pt/PT-1", query_string={"ativo": "THPN-ALT100-INVR1", "volta": volta}).get_data(as_text=True)
    assert "<html" not in html and "PT-1" in html and "/os/_nexus/pt/PT-1/decidir" in html
    assert f'name="volta" value="{volta}"'.replace("+", "+") in html.replace("&#43;", "+")
    assert "data-cr-assinatura" in html and "data-cr-quem" in html
    # volta para fora da Visão do responsável não vai no formulário
    html = logado.get("/t/campo/responsaveis/pt/PT-1", query_string={"ativo": "THPN-ALT100-INVR1", "volta": "//fora.test"}).get_data(as_text=True)
    assert 'name="volta"' not in html


def test_a_tela_abre_as_janelas_pelo_valor_e_pela_os_da_pt(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe&modo=geral").get_data(as_text=True)
    assert 'id="cr-modal"' in html and "data-cr-painel=" in html
    assert "/t/campo/responsaveis/usina/1/meta" in html and "/t/campo/responsaveis/usina/1/disp" in html
    assert "/t/campo/responsaveis/pt/PT-1" in html and "dia a dia" in html



# ── Os ativos falhando (Levi, 13/10/2026: "Para esses ativos falhando da engenharia, conseguimos criar uma visão?") ──
def _sinal_com_os():
    hoje = datetime.now(BRT)
    d = lambda n: (hoje - timedelta(days=n)).strftime("%d/%m %H:%M")    # noqa: E731
    return {"usina_id": 1, "nivel": "critico", "nome": "Inversor 2.4 Huawei SUN2000-215KTL-H3", "cod": "THPN-ALT100-INVR2.4",
            "fam": "Inversor", "crit": "A", "circuito": "Cabine 2", "porQue": ["4 falhas em 30 dias", "2 falhas em 7 dias"],
            "nFalha": 4, "n7": 2, "n30": 5, "nServico": 1, "p90": 2, "mtbf": 350.0, "mttr": 30.0, "disp": 0.92,
            "os": [{"os": "15101", "t": "Inversor desligado", "nota": "religado", "url": "https://one.fracttal.com/tasks/wo/1",
                    "d": d(1), "tipo": "Corretiva", "st": "Finalizada", "quem": "", "prio": "", "servico": False},
                   {"os": "15102", "t": "Inversor desligado", "nota": "", "url": "", "d": d(1), "tipo": "Corretiva",
                    "st": "Finalizada", "quem": "", "prio": "", "servico": False},
                   {"os": "15050", "t": "Troca de fusível", "nota": "", "url": "", "d": d(12), "tipo": "Corretiva",
                    "st": "Finalizada", "quem": "", "prio": "", "servico": True}]}


def test_a_janela_dos_ativos_falhando(tela, logado, monkeypatch):
    from nexus.engenharia import os_falhas
    monkeypatch.setattr(R, "_engenharia", lambda: {"dados": {"sinais": [_sinal_com_os(), *SINAIS]}, "sem_cadastro": False})
    monkeypatch.setattr(os_falhas, "estado", lambda: {"completa": True, "lendo": False})
    hoje = datetime.now(BRT).date()
    at = R.ativos_da_usina(1, hoje)
    assert [a["nome"] for a in at["ativos"]] == ["Inversor 2.4 Huawei SUN2000-215KTL-H3", "Inversor 1"]
    a = at["ativos"][0]
    assert len(a["linha"]) == 30 and a["linha"][-1]["dia"] == hoje
    assert a["linha"][-2]["falhas"] == 2 and a["linha"][-13]["servicos"] == 1            # ontem 2 falhas; há 12 dias, serviço
    assert (a["mtbf"], a["mttr"], a["disp"], a["disp_cls"]) == ("350 h", "30,0 h", "92,0%", "ok")
    html = logado.get("/t/campo/responsaveis/usina/1/ativos").get_data(as_text=True)
    assert "<html" not in html and "Ativos falhando" in html and "2 críticos</b>" in html and "0 em atenção" not in html
    assert "As OS dos últimos 30 dias" in html and 'class="cr-tl-f">2<' in html and "cr-tl-s" in html
    assert "Inversor 2.4 Huawei SUN2000-215KTL-H3" in html and "P90 da família" in html and "4 falhas em 30 dias" in html
    assert "https://one.fracttal.com/tasks/wo/1" in html and "Abrir a Confiabilidade" in html
    # sem ativo em crítico ou atenção, a janela diz
    html = logado.get("/t/campo/responsaveis/usina/2/ativos").get_data(as_text=True)
    assert "Nenhum ativo desta usina em crítico ou atenção" in html and "1 em monitorar" in html


def test_o_dia_da_os_sem_o_ano():
    assert R._dia_da_os("28/12 10:00", date(2027, 1, 5)) == date(2026, 12, 28)
    assert R._dia_da_os("03/01 08:00", date(2027, 1, 5)) == date(2027, 1, 3)
    assert R._dia_da_os("", date(2027, 1, 5)) is None


def test_a_etiqueta_e_o_detalhe_abrem_os_ativos(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe&modo=geral").get_data(as_text=True)
    assert html.count("/t/campo/responsaveis/usina/1/ativos") == 2           # a etiqueta e o "ver os ativos"
    assert "ver os ativos" in html and 'class="cr-tag cr-tag--critico cr-abre"' in html


# ── A Observação do responsável (Levi, 13/10/2026) ────────────────────────────────────────────────────────────────
def _responsavel(cliente, email="beltrano@exemplo.test", nome="Beltrano Supervisor"):
    from conftest import SENHA_TESTE
    cliente.post("/entrar", data={"senha": SENHA_TESTE})
    with cliente.session_transaction() as s:
        s["usuario"] = {"email": email, "nome": nome, "perfil": ""}
    return cliente


def test_a_observacao_do_responsavel_vai_cifrada_com_dia_e_hora(tela, cliente, banco):
    import json
    from test_campo_visao import CHAVE_CADASTRO
    from nexus.cadastro.cifra import Cofre
    from nexus.campo import observacao_responsavel as O
    c = _responsavel(cliente)
    html = c.get("/t/campo/responsaveis/usina/3/meta").get_data(as_text=True)
    assert "Observação do responsável" in html and "Nenhuma observação nesta usina ainda" in html
    assert 'data-cr-obs' in html and "como Beltrano Supervisor)" in html                 # a usina é dele: sem "cobrindo"
    r = c.post("/t/campo/responsaveis/usina/3/observacao", data={"texto": "Inversor 3 trocado; a geração volta amanhã."})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Observação salva" in html and "Inversor 3 trocado" in html and "<html" not in html
    linhas = O.ler_todas()
    assert len(linhas) == 1
    x = linhas[0]
    assert (x["usina_id"], x["do_responsavel"], x["tela"]) == (3, "sim", "meta")
    assert x["data_id"] == int(datetime.now(BRT).strftime("%Y%m%d")) and x["escrita_em"].endswith("Z")
    bruto = json.dumps(x, ensure_ascii=False)
    assert "Inversor 3" not in bruto and "Beltrano" not in bruto and "beltrano@" not in bruto     # nada em claro no banco
    cofre = Cofre(CHAVE_CADASTRO)
    assert cofre.decifrar(x["texto_cifrado"], f"banco/observacoes/{x['id']}/texto").startswith("Inversor 3 trocado")
    assert json.loads(cofre.decifrar(x["quem_cifrado"], f"banco/observacoes/{x['id']}/quem"))["nome"] == "Beltrano Supervisor"
    # para os relatórios: decifrada, com a usina do cadastro
    with c.application.app_context():
        rel = O.para_relatorio()
    assert [(o["usina"], o["nome"], o["texto"][:10]) for o in rel] == [("Coração 1", "Beltrano Supervisor", "Inversor 3")]


def test_responsavel_de_outra_usina_comenta_cobrindo_ferias(tela, cliente, banco):
    from nexus.campo import observacao_responsavel as O
    c = _responsavel(cliente)                                  # o Beltrano é da Coração 1; a Altair é do Ciclano
    assert "cobrindo Ciclano Chefe" in c.get("/t/campo/responsaveis/usina/1/meta").get_data(as_text=True)
    html = c.post("/t/campo/responsaveis/usina/1/observacao", data={"texto": "Cobrindo as férias do Ciclano."}).get_data(as_text=True)
    assert "Observação salva" in html and ">cobrindo</span>" in html
    assert O.ler_todas()[0]["do_responsavel"] == "não"


def test_so_responsavel_escreve(tela, logado, banco):
    from nexus.campo import observacao_responsavel as O
    html = logado.get("/t/campo/responsaveis/usina/1/meta").get_data(as_text=True)    # o administrador, sem Fracttal
    assert "Só os Responsáveis O&amp;M escrevem aqui" in html and "data-cr-obs" not in html
    html = logado.post("/t/campo/responsaveis/usina/1/observacao", data={"texto": "teste"}).get_data(as_text=True)
    assert "Só os Responsáveis O&amp;M escrevem a observação" in html and O.ler_todas() == []
    # pedido de outro site não grava
    r = logado.post("/t/campo/responsaveis/usina/1/observacao", data={"texto": "x"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_observacao_vazia_ou_comprida_e_recusada_e_o_texto_fica(tela, cliente, banco):
    from nexus.campo import observacao_responsavel as O
    c = _responsavel(cliente)
    assert "Escreva a observação antes de salvar" in c.post("/t/campo/responsaveis/usina/3/observacao",
                                                           data={"texto": "   "}).get_data(as_text=True)
    longo = "x" * (O.TEXTO_MAX + 1)
    html = c.post("/t/campo/responsaveis/usina/3/observacao", data={"texto": longo}).get_data(as_text=True)
    assert "passou de 2000 caracteres" in html and longo in html and O.ler_todas() == []


# ── A Limpeza e as paradas abertas (18/10/2026: o que um supervisor tinha no painel próprio) ────────────────────────
SUJ, VEG = "Sujidade dos módulos (1 a 5)", "Altura da vegetação (1 a 5)"


def test_limpeza_na_regua_das_rondas(tela):
    """A última sujidade e vegetação da usina (o checklist que o App manda no livro de rondas), na régua das Rondas
    (`visao.criticidade`): nível 5 é crítico, nível 4 é atenção; sem leitura, nada."""
    _aba(tela, "rondas_app_campo", "OS de ronda", [
        _ronda(_dia(1), **{SUJ: 2, VEG: 5}),
        _ronda(_dia(2), usina="Thopen - Brodowski 1 - SP", ativo="THPN-BWK100", OS="501", **{SUJ: 4, VEG: 1})])
    visao.limpar()
    u = _por_usina()
    alt, bwk, cor = u["Altair"], u["Brodowski 1"], u["Coração 1"]
    assert alt["acomp"]["valores"]["limpeza"] == {"txt": "S2 V5", "cls": "critico", "sub": ""}
    assert {"area": "limpeza", "nivel": "critico", "titulo": "Vegetação muito alta"} in alt["acomp"]["alertas"]
    assert alt["acomp"]["nivel"] == "critico"
    det = next(i for i in alt["acomp"]["det"] if i["rot"] == "Limpeza")
    assert "Sujidade 2" in det["resto"] and "Vegetação 5" in det["resto"]
    assert det["ronda"]["txt"] == f"ronda de {_dia(1)[8:10]}/{_dia(1)[5:7]}"       # a data abre o card da ronda
    assert bwk["acomp"]["valores"]["limpeza"]["cls"] == "alerta"
    assert {"area": "limpeza", "nivel": "atencao", "titulo": "Sujidade alta"} in bwk["acomp"]["alertas"]
    assert cor["acomp"]["valores"]["limpeza"] == {"txt": "—", "cls": "neutro", "sub": ""}
    assert "Limpeza" not in [i["rot"] for i in cor["acomp"]["det"]]


def test_paradas_abertas_de_todas_as_usinas(tela):
    """A OS de parada aberta do mês (as OS que formaram a disponibilidade, publicadas pela plataforma) vira a lista da
    usina para a faixa "Parada agora"; a OS já fechada não."""
    u = _por_usina()
    assert u["Altair"]["paradas_abertas"] == [{"os": "13002", "tipo": "Corretiva Emergencial", "escopo": "Inversor 1",
                                               "codigo": "THPN-ALT100-INVR1", "inicio": f"02/{MES[5:7]} 08:00",
                                               "_ini": f"{MES}-02T08:00:00"}]
    assert u["Brodowski 1"]["paradas_abertas"] == [] and u["Coração 1"]["paradas_abertas"] == []


# ── O bloco Manutenção (18/10/2026, Levi: o que o supervisor tinha no painel próprio, "pegando tudo do Fracttal ou
# Nexus"): as tarefas das OS (`nexus_os`), as paradas abertas, o limite das atrasadas de quem olha (cookie) ───────────
def _did(d):
    return d.year * 10000 + d.month * 100 + d.day


def _tarefa(tid, os_, usina, dias_atras, tipo="corretiva", status="em_processo", estado="nao_iniciada"):
    """Uma linha do fato `nexus_os · fato_tarefa_os`, como o laço do Campo grava."""
    from nexus.dados import fatos as D
    return {"fracttal_tarefa_id": tid, "os": os_, "fracttal_os_id": 50000 + os_,
            "tarefa_chave": D.tarefa_chave("troca de fusivel"), "codigo_ativo": "THPN-ALT100-INVR1",
            "equipamento_id": None, "equipamento_ligado_por": None, "usina_id": usina,
            "usina_ligada_por": "de-para do Fracttal", "site_fracttal": "Thopen - X - SP", "data_id_criacao": None,
            "data_id_programada": _did(HOJE - timedelta(days=dias_atras)), "data_id_fim": None, "tipo_tarefa": tipo,
            "status_os": status, "estado_tarefa": estado, "do_backoffice": 0, "duracao_min": None}


@pytest.fixture
def manut(tela):
    _aba(tela, "nexus_os", "fato_tarefa_os", [
        _tarefa(1, 901, 2, 31),             # Brodowski 1: atrasada há 31 dias, acima do limite padrão (30)
        _tarefa(2, 902, 3, 12)])            # Coração 1: atrasada há 12 dias, abaixo do limite
    _aba(tela, "nexus_os", "qualidade", [{"fato": "tarefa_os", "gerado_em": f"{HOJE.isoformat()}T09:10:00-03:00"}])
    visao.limpar()
    return tela


def _bloco_manut(html):
    """A lista da Visão geral (desde 18/10/2026 no lugar dos três blocos de Onde focar)."""
    return html[html.index('class="cr-gr-lista"'):html.index('class="cn-nota"')]


def _nivel_da_linha(trecho, usina, bloco="manut"):
    """O nível do bloco na linha da usina (o `data-<bloco>` da linha da Visão geral)."""
    i = trecho.index(f"<b>{usina}")
    linha = trecho[trecho.rindex('<details class="cr-gr-lin', 0, i):i]
    ini = linha.index(f'data-{bloco}="') + len(f'data-{bloco}="')
    return linha[ini:linha.index('"', ini)]


def _com_manut(limite=30):
    return {u["usina"]: u for u in R.com_manutencao(R.visao_responsaveis().dados["usinas"], limite)}


def test_o_bloco_manutencao_na_tela(manut, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    # Levi, 18/10/2026: "A ordem é essa mesmo: Performance, manutenção e acompanhamento"
    assert html.index('id="cr-gr-perf"') < html.index('id="cr-gr-manut"') < html.index('id="cr-gr-acomp"')
    bloco = _bloco_manut(html)
    for rot in ("OS abertas", "Atrasadas", "Pausadas", "Semana passada"):
        assert rot in bloco, rot
    assert "A semana vem do arquivo do PCM" in html
    assert _nivel_da_linha(bloco, "Brodowski 1") == "critico" and _nivel_da_linha(bloco, "Coração 1") == "atencao"
    u = _com_manut()
    assert u["Brodowski 1"]["manut"]["valores"]["atrasadas"]["cls"] == "critico"
    assert u["Coração 1"]["manut"]["valores"]["atrasadas"]["cls"] == "alerta"


def test_o_limite_muda_o_nivel_e_fica_no_cookie(manut, logado):
    r = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&limite=45")
    assert "nexus_resp_limite=45" in r.headers.get("Set-Cookie", "")
    assert _nivel_da_linha(_bloco_manut(r.get_data(as_text=True)), "Brodowski 1") == "atencao"
    # o pedido seguinte, sem o parâmetro, segue com o limite do cookie
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert 'name="limite"' in html and 'value="45"' in html
    assert _nivel_da_linha(_bloco_manut(html), "Brodowski 1") == "atencao"


def test_limite_do_cookie_com_lixo(manut, logado):
    assert [R.limite_do_pedido(v) for v in ("abc", "", None, "0", "-5", "9999", "45", " 60 ")] == [
        30, 30, 30, 10, 10, 365, 45, 60]
    logado.set_cookie("nexus_resp_limite", "abc")
    r = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral")
    assert r.status_code == 200 and 'value="30"' in r.get_data(as_text=True)


def test_parada_aberta_poe_em_focar_e_na_faixa_respeitando_o_filtro(manut, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    faixa = html[html.index('class="cr-parada"'):]
    faixa = faixa[:faixa.index("</div>")]
    assert "Altair" in faixa and "13002" in faixa and "Inversor 1" in faixa
    altair = _com_manut()["Altair"]["manut"]
    assert altair["nivel"] == "critico" and altair["tag"] == ("critico", "parada")
    # o filtro de outro responsável: a faixa não mostra a Altair
    html = logado.get("/t/campo/responsaveis?responsavel=Beltrano+Supervisor&modo=geral").get_data(as_text=True)
    assert 'class="cr-parada"' not in html


def test_sem_o_fato_a_tela_avisa_e_nao_cobra(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert "As OS do Fracttal ainda não chegaram ao banco" in html
    u = _com_manut()
    assert u["Brodowski 1"]["manut"]["nivel"] == u["Coração 1"]["manut"]["nivel"] == "ok"


def test_a_tela_diz_que_a_leitura_falhou(manut, logado, monkeypatch):
    from nexus.campo import tarefas_os
    monkeypatch.setattr(tarefas_os, "estado", lambda: {"ultimo": {"erro": "LeituraIncompleta: o Fracttal recusou"},
                                                       "quando": f"{HOJE.isoformat()}T10:10-03:00"})
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert "A última leitura do Fracttal falhou" in html and "09:10" in html


def test_a_tela_diz_que_a_leitura_nao_gravou(manut, logado, monkeypatch):
    """Revisão de 18/10/2026: a volta que lê e se recusa a gravar (`recusou`: o backoffice não abriu, o cadastro veio
    vazio...) não aparecia na tela, só a que falhava."""
    from nexus.campo import tarefas_os
    monkeypatch.setattr(tarefas_os, "estado", lambda: {
        "ultimo": {"recusou": "a lista do backoffice do PCM não abriu: o do_backoffice sairia chutado"},
        "quando": f"{HOJE.isoformat()}T10:10-03:00"})
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert "A última leitura do Fracttal não gravou" in html and "backoffice do PCM não abriu" in html


def test_a_foto_velha_das_os_avisa_com_o_dia(manut, logado):
    """Revisão de 18/10/2026: a tela dizia só a hora da leitura ("às 09:10"), e a foto de ontem passava por de hoje."""
    ontem = HOJE - timedelta(days=1)
    _aba(manut, "nexus_os", "qualidade", [{"fato": "tarefa_os", "gerado_em": f"{ontem.isoformat()}T09:10:00-03:00"}])
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert f"As OS da tela são da leitura de {ontem.strftime('%d/%m')} às 09:10" in html


def test_a_foto_recente_das_os_nao_avisa(manut, logado):
    agora = datetime.now(BRT) - timedelta(minutes=30)
    _aba(manut, "nexus_os", "qualidade", [{"fato": "tarefa_os", "gerado_em": agora.isoformat(timespec="seconds")}])
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert "As OS da tela são da leitura" not in html
    assert R.foto_das_os(agora.isoformat(), datetime.now(BRT))["velha"] is False


def test_sem_os_motivos_a_tela_avisa(manut, logado, monkeypatch):
    """Revisão de 18/10/2026: sem os motivos do PCM, as tarefas paradas por motivo passavam calado para as atrasadas."""
    from nexus.pcm import motivos
    monkeypatch.setattr(motivos, "ler", lambda cfg, **k: {"motivos": [], "inicial": [], "marcas": [], "backoffice": [],
                                                           "erro": "ConnectionError: o banco não respondeu",
                                                           "lido_em": None})
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert "Os motivos do Fora da programação não abriram" in html


def test_marca_que_nao_abre_com_a_chave_avisa(manut, logado, monkeypatch):
    from nexus.pcm import motivos
    monkeypatch.setattr(motivos, "vigentes", lambda cfg, est: {"_ilegiveis": 2})
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert "2 marcas do Fora da programação não abriram com a chave" in html


def test_os_do_detalhe_abre_o_card_e_nao_a_pt(manut, logado):
    bloco = _bloco_manut(logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True))
    assert re.search(r'<button type="button" class="cn-link cr-os cr-link-botao" data-wid="50901"', bloco)


def test_tarefa_com_motivo_sai_das_atrasadas_e_vai_para_paradas(manut, tmp_path):
    from flask import current_app
    from nexus.pcm import motivos as M
    cfg = current_app.config
    cfg["NEXUS_PCM_MOTIVOS_ARQUIVO"] = str(tmp_path / "motivos.json")
    M.limpar()
    mid = next(m["id"] for m in M.ativos(M.ler(cfg, forcar=True)) if m["nome"] == "Aguardando material")
    M.marcar(cfg, {"os": "901", "codigo": "THPN-ALT100-INVR1", "tarefa": "Troca de fusível",
                   "usina": "Thopen - Brodowski 1 - SP", "cliente": "Thopen", "tipo": "Corretiva"}, mid, "",
             {"email": "pessoa@exemplo.test", "nome": "Pessoa Fictícia"})
    visao.limpar()
    m = _com_manut()["Brodowski 1"]["manutencao"]
    assert (m["atrasadas"], m["paradas"], m["motivo_comum"]) == (0, 1, "Aguardando material")
    M.limpar()


def test_a_fronteira_do_limite_das_atrasadas():
    """Revisão de 18/10/2026 (I7): no limite (30 dias) é Acompanhar; um dia acima, Focar. "Acima do limite" é maior
    que, não maior ou igual."""
    for maior, nivel, cls in ((30, "atencao", "alerta"), (31, "critico", "critico")):
        u = {"manutencao": {"atrasadas": 2, "maior_atraso": maior, "os_abertas": 1}}
        al, _ = R.alertas_manutencao(u, 30)
        assert [a["nivel"] for a in al] == [nivel], maior
        assert R.linha_manutencao(u, 30)["valores"]["atrasadas"]["cls"] == cls, maior


def test_a_fronteira_da_meta_da_semana():
    """A régua do Fechamento do PCM: 85% é a meta (cumprida); 84,9%, Acompanhar."""
    for pct, cobra, cls in ((84.9, True, "alerta"), (85.0, False, "ok")):
        u = {"manutencao": {"passada_pct": pct, "passada": "2026-W41", "passada_prog": 10, "passada_feitas": 8}}
        al, bem = R.alertas_manutencao(u, 30)
        assert any(a["area"] == "semana" for a in al) is cobra, pct
        assert R.linha_manutencao(u, 30)["valores"]["semana"]["cls"] == cls, pct


def test_a_zeladoria_vencida_e_acompanhar_e_a_proxima_nao_cobra():
    base = {"perf": {"nivel": "ok", "peso": 0}, "acomp": {"nivel": "ok", "peso": 0}, "meta": {}}
    us = [dict(base, usina="A", manutencao={"zeladoria_vencida": date(2026, 10, 1)}),
          dict(base, usina="B", manutencao={"zeladoria_proxima": date(2026, 10, 30)}),
          dict(base, usina="C", manutencao={})]
    u = {x["usina"]: x for x in R.com_manutencao(us, 30)}
    assert [u[n]["manut"]["nivel"] for n in "ABC"] == ["atencao", "ok", "ok"]
    assert u["A"]["nivel"] == "atencao" and u["A"]["manut"]["valores"]["zeladoria"]["txt"] == "venc. 01/10"
    assert u["B"]["manut"]["valores"]["zeladoria"]["txt"] == "próx. 30/10"


def test_a_ordem_do_bloco_manutencao():
    """Decisão do Levi (18/10/2026): o nível; dentro dele, a parada primeiro, depois mais atrasadas, mais paradas e a
    semana mais baixa; no empate, o nome."""
    def u(nome, nivel, pa=0, atr=0, par=0, pct=None):
        return {"usina": nome, "manut": {"nivel": nivel}, "paradas_abertas": [{}] * pa,
                "manutencao": {"atrasadas": atr, "paradas": par, "passada_pct": pct}}
    us = [u("H", "ok"), u("G", "atencao", pct=70.0), u("F", "atencao", pct=60.0), u("E", "atencao", par=2),
          u("D", "atencao", atr=3), u("C", "critico", atr=1), u("B", "critico", atr=5), u("A", "critico", pa=1),
          u("I", "atencao", pct=60.0), u("J", "atencao", atr=3, par=1)]
    assert [x["usina"] for x in sorted(us, key=R.ordem_da_manutencao)] == [
        "A", "B", "C", "J", "D", "E", "F", "I", "G", "H"]


def test_cartoes_com_os_tres_blocos(manut, logado):
    html = logado.get("/t/campo/responsaveis?modo=cartoes&responsavel=*").get_data(as_text=True)
    cartoes = html[html.index('class="cn-equipes"'):html.index('class="cn-nota"')]
    assert cartoes.count("<span>Manutenção</span>") == 2


def test_a_programacao_e_lida_do_fim(tela, monkeypatch):
    """A semana vem do `fato_programacao`, que guarda as semanas desde a W21 (16.540 linhas em 18/10/2026: 4,4 s a aba
    inteira a cada conta). A carga põe as 4 semanas do arquivo do PCM no fim: lê-se do fim para trás e para depois de
    passar da semana passada, como a tela Técnicos por usina."""
    seg = HOJE - timedelta(days=HOJE.weekday())

    def linha(semana, status):
        return {"usina_id": 2, "data_id_semana": _did(semana), "data_id_programada": _did(semana),
                "hora_inicio": "08:00", "status_execucao": status}
    _aba(tela, "nexus_programacao", "fato_programacao",
         [linha(seg - timedelta(days=35), "finalizada")] * 2500
         + [linha(seg - timedelta(days=7), "finalizada")] * 17 + [linha(seg - timedelta(days=7), "nao_iniciada")] * 3)
    sid = tela.abas[("nexus_programacao", "fato_programacao")]["id"]
    offsets, get = [], tela.get

    def contando(url, params=None, **k):
        if url.endswith(f"/api/sheets/{sid}/rows"):
            offsets.append(int((params or {}).get("offset", 0)))
        return get(url, params=params, **k)
    monkeypatch.setattr(tela, "get", contando)
    visao.limpar()
    m = _com_manut()["Brodowski 1"]["manutencao"]
    assert (m["passada_prog"], m["passada_feitas"], m["passada_pct"]) == (20, 17, 85.0)
    assert offsets and 0 not in offsets                 # a 1ª página (as semanas antigas) nunca é lida


# ── O Ranking das equipes (18/10/2026, Levi: "qual equipe cobrar", a posição pela régua do ranking por região do App) ──
def test_a_aba_ranking_das_equipes(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking").get_data(as_text=True)
    assert 'aria-current="page">Ranking das equipes</a>' in html and 'class="cn-equipes cr-rk"' in html
    grade = html[html.index('class="cn-equipes cr-rk"'):]                    # os números de cima citam a melhor equipe
    assert grade.index("SC Oeste 01") < grade.index("SP Norte 01")           # sem nota antes da ranqueada
    assert "1º" in html and "de 1" in html and ">93<" in html and "sem nota do App" in html
    assert "60% qualidade" in html and "equipe=SP+Norte+01" in html and "modo=geral" in html


def test_o_responsavel_logado_ve_o_ranking_das_equipes_dele(tela, cliente):
    html = _responsavel(cliente).get("/t/campo/responsaveis?modo=ranking").get_data(as_text=True)
    assert ">Ranking das equipes</a>" in html and ">Por responsável</a>" not in html
    assert "SC Oeste 01" in html and "SP Norte 01" not in html                # Beltrano é o responsável da Coração 1
    html = cliente.get("/t/campo/responsaveis?modo=cartoes").get_data(as_text=True)
    assert 'class="pn"' in html and 'class="cn-equipes"' not in html         # nunca os cartões dos outros: o Painel dele


def test_o_filtro_de_equipe_na_visao_geral(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&equipe=SP+Norte+01").get_data(as_text=True)
    assert "Altair" in html and "Brodowski 1" in html and "Coração 1" not in html
    assert "Equipe SP Norte 01" in html and 'href="?responsavel=%2A&amp;modo=geral"' in html  # o "×" tira só a equipe
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&equipe=SP+Norte").get_data(as_text=True)
    assert "Altair" not in html                                               # o nome exato, nunca um pedaço


def test_sem_as_notas_do_app_o_ranking_avisa(tela, logado, monkeypatch):
    monkeypatch.setattr(R, "ranking_fonte", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("fato fora")))
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking").get_data(as_text=True)
    assert "Não consegui ler as notas do App" in html and 'class="cn-equipes cr-rk"' not in html
    assert 'class="cr-gr"' in logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)


def test_o_filtro_de_equipe_nao_fica_escondido(tela, logado):
    # achado 2 da revisão do ranking: o "Todos os responsáveis ×" levava aos cartões com o `equipe=` escondido, e os
    # números saíam recortados sem aviso. Na Visão geral o × fica na Visão geral, e a equipe segue à vista, com o × dela
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe&modo=geral&equipe=SP+Norte+01").get_data(as_text=True)
    todos = re.search(r'href="([^"]*)" title="As usinas de todos os responsáveis"', html).group(1)
    assert "modo=geral" in todos and "Equipe SP Norte 01" in html


def test_a_regua_do_ranking_diz_o_desempate_e_a_legenda_do_semaforo(tela, logado):
    # achados 4 e 6 da revisão: com 41 de 52 equipes empatadas, a posição saía do desempate sem a tela dizer; e os três
    # números do semáforo só se distinguiam pela cor (a regra da casa: severidade por cor E palavra)
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking").get_data(as_text=True)
    assert "No empate, vence a maior qualidade, depois a maior cobertura, mais notas e o nome" in html
    assert 'class="cr-rk-leg"' in html and ">focar</b>" in html and ">acompanhar</b>" in html and ">em dia</b>" in html


def test_equipe_com_ronda_sem_nota_nao_e_chamada_de_sem_ronda(tela, logado, monkeypatch):
    # achado 5 da revisão: "nenhuma OS nem ronda pelo App" saía também quando havia ronda do App sem nota
    vazio = {"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": False}
    por = {1: {"atual": dict(vazio), "anterior": dict(vazio)}, 2: {"atual": dict(vazio), "anterior": dict(vazio)},
           3: {"atual": dict(vazio, n_ronda=1, rondada=True), "anterior": dict(vazio)}}
    monkeypatch.setattr(R, "ranking_fonte", lambda *a, **k: (por, {}))
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking").get_data(as_text=True)
    assert "sem nota do App: 1 ronda no mês, nenhuma com nota" in html
    assert "sem nota do App: nenhuma OS nem ronda pelo App no mês" in html      # a SP Norte 01, sem nada


def test_o_filtro_de_cliente_escolhe_as_equipes(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking&cliente=Thopen").get_data(as_text=True)
    grade = html[html.index('class="cn-equipes cr-rk"'):]
    assert "SP Norte 01" in grade and "SC Oeste 01" not in grade              # a Coração 1 é de outro cliente


def _comp(faltas=None) -> str:
    """A "Composição da nota" como o App grava no livro: os seis critérios, cheios menos os de `faltas`."""
    import json
    faltas = faltas or {}
    return json.dumps([{"rot": r, "peso": p, "pts": faltas.get(r, (p, ""))[0], "det": faltas.get(r, (p, "ok"))[1]}
                       for r, p in (("Subtarefas obrigatórias", 25), ("Fotos", 20), ("Fotos com descrição", 10),
                                    ("Assinatura", 10), ("Observações", 15), ("GPS no fechamento", 20))],
                      ensure_ascii=False)


@pytest.fixture
def duas_equipes(tela):
    """A SC Oeste 01 com nota: uma ronda do App na Coração 1 (50, com falhas) e uma tarefa (60: sem fotos e sem GPS).
    0,6 × 55 + 0,4 × 100 = 73, a 2ª de 2, atrás da SP Norte 01 (93)."""
    from test_campo_visao import _fech
    _aba(tela, "rondas_app_campo", "OS de ronda", [
        _ronda(_dia(1), Falhas="ronda longa pendente; item sem foto de evidência"),
        _ronda(_dia(3), Falhas="ronda longa pendente"),
        _ronda(_dia(2), usina="Thopen - Brodowski 1 - SP", ativo="THPN-BWK100", OS=None,
               **{"Situação da OS": "Não criada — Fracttal: Conecte"}),
        _ronda(_dia(1), usina="Outro Cliente - Coração 1 - SC", ativo="THPN-COR100", OS="501", Região="SC Oeste 01",
               Falhas="checklist incompleto; item sem foto de evidência",
               **{"Nota da ronda": 50, "ID da OS no Fracttal": "5001", "Início": f"{_dia(1)}T12:00:00.000Z",
                  "Fim": f"{_dia(1)}T13:00:00.000Z"})])
    # a linha com a composição vem primeiro: o cabeçalho da aba falsa sai da 1ª linha
    _aba(tela, "fechamentos_app_campo", "Fechamentos", [
        _fech(4, 60, regiao="SC Oeste 01", OS="801", Tarefa="Limpeza do inversor", Usina="Outro Cliente · Coração 1",
              **{"ID da OS no Fracttal": "8001", "Código do ativo": "THPN-COR100-INVR1",
                 "Composição da nota": _comp({"Fotos": (0, "0 fotos (3 dá o total)"),
                                              "GPS no fechamento": (0, "sem posição")})}),
        _fech(5, 90), _fech(6, 70), _fech(7, 100, regiao="Grid Co.")])
    visao.limpar()
    return tela


def _grade(html):
    return html[html.index('class="cn-equipes cr-rk"'):]


def test_filtrado_a_posicao_fica_a_do_ranking_inteiro(duas_equipes, logado):
    # Levi, 18/10/2026: "O ranking das equipes tem que permancer mesmo filtrados, o que está acontecendo agora é que se
    # eu filtro [um responsável] vai contar de 1 a 11, tem que contar de acordo com o ranking"
    grade = _grade(logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking").get_data(as_text=True))
    assert grade.index("SC Oeste 01") < grade.index("SP Norte 01")          # da última para a 1ª
    assert '2º<small> de 2</small>' in grade and '1º<small> de 2</small>' in grade
    for filtro in ("responsavel=Beltrano+Supervisor", "responsavel=*&cliente=Outro+Cliente", "responsavel=*&q=cora"):
        html = logado.get(f"/t/campo/responsaveis?{filtro}&modo=ranking").get_data(as_text=True)
        grade = _grade(html)
        assert "SC Oeste 01" in grade and "SP Norte 01" not in grade, filtro
        assert '2º<small> de 2</small>' in grade and "1º" not in grade, filtro
        assert ">73<" in grade, filtro


def test_o_responsavel_logado_ve_a_posicao_do_ranking_inteiro(duas_equipes, cliente):
    grade = _grade(_responsavel(cliente).get("/t/campo/responsaveis?modo=ranking").get_data(as_text=True))
    assert "SC Oeste 01" in grade and "SP Norte 01" not in grade and '2º<small> de 2</small>' in grade


def _com_nome(api, pid, nome):
    """O técnico `pid` com o nome na ficha (cifrado, como no banco); só a aba de pessoas é trocada."""
    import json
    from test_campo_visao import CHAVE_CADASTRO, _pessoas
    from nexus.cadastro.cifra import Cofre
    linhas = _pessoas()
    for x in linhas:
        if x["pessoa_id"] == pid:
            x["sensivel_cifrado"] = Cofre(CHAVE_CADASTRO).cifrar(
                json.dumps({"nome": nome, "nome_padrao": nome, "email": None}), f"banco/pessoas/{pid}")
    cab = list(linhas[0])
    api._id("cadastro_nexus", "pessoas")["linhas"] = [{"headers": cab, "values": [x.get(c) for c in cab]} for x in linhas]
    visao.limpar()


def test_o_cartao_abre_o_que_cobrar_com_a_prova(duas_equipes, logado):
    # Levi, 18/10/2026: "Clicando na equipe deve dar um breve resumo do motivo da pontuação da equipe estar abaixo para
    # que o supervisor possa cobrar a equipe"; depois, "quero ao clicar na equipe um detalhamento melhor [do Em quê
    # cobrar], não cheio de informações mas quero a informação, ao resumido e direto onde o supervisor bata o olho e
    # possa cobrar o técnico com dados!" (no quiz: "Item a item com a prova") e, nas OS mais baixas, "Faltou os pontos"
    _com_nome(duas_equipes, 4, "Operador Lima")
    html = logado.get("/t/campo/responsaveis?responsavel=Beltrano+Supervisor&modo=ranking").get_data(as_text=True)
    painel = re.search(r'data-cr-painel="([^"]*/responsaveis/equipe\?[^"]*)"', _grade(html)).group(1)
    assert "equipe=SC+Oeste+01" in painel and "responsavel=Beltrano+Supervisor" in painel
    jan = logado.get(painel.replace("&amp;", "&")).get_data(as_text=True)
    assert "SC Oeste 01" in jan and "2º de 2" in jan and ">73<" in jan and "Técnicos: Operador Lima" in jan
    # o "Em quê cobrar": as áreas da etiqueta do cartão, com a prova (o extintor, a OS do chamado) e a usina
    cobrar = jan[jan.index('class="cr-rk-j-itens"'):jan.index("Nota do App")]
    assert "Acompanhar" in jan and ">Extintores</b>" in cobrar and ">Chamados</b>" in cobrar
    assert "Extintor EXT01 · Coração 1 · " in cobrar
    # a OS citada é o botão verde que abre o card dela (Levi, 19/10/2026: "ao citar uma OS tem que ficar verde grid e
    # deve ser possível clicar e ver o card da OS que nem quando clicamos em uma OS no OS Creator Web")
    assert re.search(r'<button type="button" class="cn-link cr-os cr-link-botao" data-wid="" data-folio="16050"[^>]*>'
                     r'OS 16050</button> · Coração 1 · ', cobrar)
    # a nota: perde 27, todos na qualidade (55; cobertura 100%): a ronda tira 15 (0,6 × 50 ÷ 2), as fotos e o GPS da
    # tarefa, 6 cada (0,6 × 20 ÷ 2)
    nota = jan[jan.index("Nota do App"):]
    # (29/10/2026, "-1 oq?"): o ponto é da nota da equipe, com onde aconteceu, quanto vale e o que fazer
    assert "perdeu 27 pontos de 100 no mês" in nota and "não é OS anulada" in nota
    assert re.findall(r'<li><b class="cr-rk-j-menos">−(\d+) pontos?</b><div><b>([^<]+)</b>', nota) == [
        ("15", "Rondas"), ("6", "Fotos"), ("6", "GPS no fechamento")]
    assert "vale 20 de 100 em cada tarefa · o que fazer: tirar ao menos 3 fotos na tarefa" in nota
    # as OS com nota mais baixa: a nota, a OS, a usina, quem fez, o dia e os pontos que perdeu
    os_ = nota[nota.index("OS com nota mais baixa"):]
    assert os_.index(">50<") < os_.index(">60<")
    assert "Fotos 0/20 · GPS no fechamento 0/20" in os_ and "checklist incompleto; item sem foto de evidência" in os_
    assert re.search(r'data-wid="8001" data-folio="801"[^>]*>OS 801</button> · Coração 1 · Técnico Silva', os_)
    assert re.search(r'Ronda · <button[^>]*data-folio="501"[^>]*>OS 501</button> · Coração 1 · Fulano Souza', os_)
    visao_geral = re.search(r'href="([^"]*modo=geral[^"]*)"', jan).group(1)
    assert "equipe=SC+Oeste+01" in visao_geral and "responsavel=Beltrano+Supervisor" in visao_geral


def test_o_que_cobrar_traz_a_pt_e_quem_pediu(duas_equipes, logado):
    jan = logado.get("/t/campo/responsaveis/equipe?equipe=SP+Norte+01").get_data(as_text=True)
    focar = jan[jan.index(">Focar "):jan.index("Nota do App")]
    # o Focar em tabela (28/10/2026): a área na coluna, a usina na linha e, na célula, a prova sem o nome dela
    assert '<th scope="col">PT parada</th>' in focar and '<th scope="row">Altair</th>' in focar
    assert "PT-1 · pedida por Técnico Silva há 1 d 6 h" in focar


def test_o_motivo_da_equipe_sem_nota_diz_o_que_falta(tela, logado):
    jan = logado.get("/t/campo/responsaveis/equipe?equipe=SC+Oeste+01").get_data(as_text=True)
    assert "Sem nota do App" in jan and "Coração 1" in jan                    # a usina sem ronda em 30 dias
    assert logado.get("/t/campo/responsaveis/equipe?equipe=Nao+Existe").status_code == 404
    assert logado.get("/t/campo/responsaveis/equipe").status_code == 404


def test_sem_as_notas_do_app_o_motivo_avisa(tela, logado, monkeypatch):
    monkeypatch.setattr(R, "ranking_fonte", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("fato fora")))
    visao.limpar()
    jan = logado.get("/t/campo/responsaveis/equipe?equipe=SP+Norte+01").get_data(as_text=True)
    assert "Não consegui ler as notas do App" in jan and "perde " not in jan
    assert '<th scope="col">PT parada</th>' in jan          # o "Em quê cobrar" não depende das notas do App


# ── A Visão geral (18/10/2026, Levi: "uma visão onde unifica todas as usinas", com os KPIs dos três blocos que
# filtram as usinas em atenção daquele bloco ao clicar) ───────────────────────────────────────────────────────────
def test_os_filtros_da_visao_geral_contam_como_o_resumo(manut):
    """Cada filtro da Visão geral usa a condição que conta o número no resumo (`soma`): nenhuma régua nova."""
    lista = list(_com_manut().values())
    s = R.soma("Todos", lista)

    def n(k):
        return len(R.filtrar_geral(lista, k))
    assert n("perf.abaixo_meta") == s["abaixo_meta"] and n("perf.pr_abaixo") == s["pr_abaixo"]
    assert n("acomp.rondas") == s["rondas"]
    assert n("acomp.pts") == sum(1 for u in lista if u["pt"]["aguardando"])
    assert n("manut.atrasadas") == sum(1 for u in lista if (u.get("manutencao") or {}).get("atrasadas")) == 2
    for b in ("perf", "acomp", "manut"):
        assert n(b) == s[b]["critico"] + s[b]["atencao"]
        assert n(f"{b}.critico") == s[b]["critico"] and n(f"{b}.atencao") == s[b]["atencao"]


def test_filtro_da_visao_geral_com_lixo_e_ignorado():
    assert [R.filtro_geral(v) for v in ("manut.atrasadas", "", None, "manut.", "x" * 500, "perf.critico")] == [
        "manut.atrasadas", None, None, None, None, "perf.critico"]
    assert R.filtrar_geral([{"usina": "A"}], None) == [{"usina": "A"}]


def test_a_visao_geral_mostra_os_tres_blocos_e_a_lista_unica(manut, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert 'aria-current="page">Visão geral' in html
    geral = html[html.index('class="cr-gr"'):]
    for b in ("Performance", "Acompanhamento", "Manutenção"):
        assert b in geral
    assert geral.count('class="cr-gr-lin') == len(_com_manut())          # todas as usinas, uma linha cada
    assert re.search(r'filtro=manut\.atrasadas(&|")', geral)              # o número vira link


def test_o_clique_no_numero_filtra_a_lista(manut, logado):
    total = len(_com_manut())
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&filtro=manut.atrasadas").get_data(as_text=True)
    geral = html[html.index('class="cr-gr"'):]
    assert geral.count('class="cr-gr-lin') == 2                          # as duas usinas com tarefa atrasada
    estado = geral[geral.index('class="cr-gr-estado"'):][:600]
    assert f"2 de {total} usinas" in estado and "Tarefas atrasadas" in estado
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&filtro=nada").get_data(as_text=True)
    assert html.count('class="cr-gr-lin') == total                       # filtro que não existe: sem filtro


def test_filtro_sem_usina_diz_e_deixa_limpar(manut, logado):
    # nenhuma tarefa com motivo no fixture: Tarefas paradas é zero
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&filtro=manut.paradas").get_data(as_text=True)
    assert "Nenhuma usina com esse filtro" in html and 'class="cr-gr-limpar"' in html
    blocos = html.split('class="cr-gr-blocos"')[1].split('class="cr-gr-estado"')[0]
    assert not re.search(r'filtro=manut\.paradas(&|")', blocos)          # número zero não é link


def test_quem_entra_pelo_fracttal_ve_so_as_usinas_dele_na_visao_geral(manut, cliente):
    """Como em Onde focar: o responsável que entrou pelo Fracttal vê as usinas dele."""
    _responsavel(cliente)
    html = cliente.get("/t/campo/responsaveis?modo=geral").get_data(as_text=True)
    dele = [u for u in _com_manut().values() if u.get("responsavel") == "Beltrano Supervisor"]
    assert 'aria-current="page">Visão geral' in html
    assert html.count('class="cr-gr-lin') == len(dele) > 0


def test_o_cabecalho_e_as_colunas_ficam_no_centro():
    """Levi, 18/10/2026: "centralize o cabeçalho e todas as colunas exceto Usina" (os blocos e a Visão geral)."""
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    assert re.search(r'\.cr-g > \[class\*="cr-col-"\]\{[^}]*justify-self:center', css)


def test_o_ranking_diz_o_periodo_e_de_onde_vieram_as_notas(tela, logado):
    # pendência da revisão (achado 8): a aba não dizia as datas dos dois períodos nem que as notas saíram na hora
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking").get_data(as_text=True)
    # o mês vigente e o mesmo trecho do mês anterior (28/10/2026: "Ranking das Equipes - Outubro, sempre o mês vigente")
    fim_passado = HOJE.replace(day=1) - timedelta(days=1)
    atual = f"de 01/{HOJE:%m} a {HOJE:%d/%m}"
    anterior = f"de 01/{fim_passado:%m} a {fim_passado.replace(day=min(HOJE.day, fim_passado.day)):%d/%m}"
    assert f"Período: {atual} (o anterior: {anterior})" in html
    assert "fato_fechamento calculado na hora" in html          # o banco falso não tem o fato: a conta é feita na hora


def test_a_faixa_da_visao_geral_diz_que_a_equipe_e_filtro(tela, logado):
    # pendência da revisão (achado 10): com a equipe escolhida, a faixa não dizia "com os filtros"
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&equipe=SP+Norte+01").get_data(as_text=True)
    assert "mobilizadas, com os filtros" in html


def test_a_dica_da_base_pequena_usa_a_constante(tela, logado, monkeypatch):
    # pendência da revisão (achado 11): o 3 estava escrito na dica; a régua é `visao.BASE_PEQUENA`, a do Painel das Rondas
    monkeypatch.setattr(visao, "BASE_PEQUENA", 4)
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking").get_data(as_text=True)
    assert 'title="Menos de 4 usinas' in html


def _linha_geral(html, usina):
    """O resumo (`summary`) da linha da usina na lista da Visão geral."""
    i = html.index(f"<b>{usina}", html.index('class="cr-gr-lista"'))
    return html[html.rindex('<details class="cr-gr-lin', 0, i):html.index("</summary>", i)]


def test_a_usina_parada_tem_a_etiqueta_na_lista_geral(manut, logado):
    """Revisão de 18/10/2026: na lista da Visão geral a usina parada não mostrava a etiqueta "parada" que Onde focar
    mostra no nome (e as células da Manutenção vinham "—"): o supervisor lia a usina como em dia."""
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    altair = _linha_geral(html, "Altair")
    assert "cr-tag--critico" in altair and ">parada<" in altair


def test_o_bloco_sem_detalhe_nao_diz_em_dia(manut, logado, monkeypatch):
    """Revisão de 18/10/2026: o bloco sem nenhuma linha de detalhe é, quase sempre, falta de dado; "em dia" contradizia a
    regra da tela (falta de dado não é em dia). Aqui, a Manutenção sem detalhe."""
    original = R.linha_manutencao
    monkeypatch.setattr(R, "linha_manutencao", lambda u, limite: {**original(u, limite), "det": []})
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    lista = html[html.index('class="cr-gr-lista"'):]
    assert "em dia</p>" not in lista and "Nada a mostrar neste bloco" in lista
    assert "Gestão PCM</a>" not in lista         # os links do fim saíram (Levi, 18/10/2026: "pode tirar")


def test_a_visao_geral_diz_com_os_filtros_com_a_equipe(manut, logado):
    equipe = next(u["equipe"] for u in _com_manut().values() if u.get("equipe"))
    html = logado.get(f"/t/campo/responsaveis?responsavel=*&modo=geral&equipe={equipe}").get_data(as_text=True)
    faixa = html[html.index('class="cr-gr"'):html.index('class="cr-gr-blocos"')]
    assert "com os filtros" in faixa


def test_a_lista_unica_vira_cartoes_ate_1180_px():
    """Revisão de 18/10/2026: entre 761 e 1260 px as colunas não cabiam (a Usina zerava e Semana sumia, cortada sem
    rolagem). Até 1180 px a lista vira os cartões (etiquetas P, M e A); de 1181 a 1366, as colunas principais."""
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    bloco = re.search(r'@media \(max-width:1180px\)\{\n  \.cr-gr-grupos(.*?)\n\}', css, re.S).group(1)
    assert '.cr-gr-g > [class*="cr-col-"]{display:none}' in bloco and ".cr-gr-pills{display:flex" in bloco


# ── A Visão geral no lugar de Onde focar (Levi, 18/10/2026: "A IDEIA É QUE A VISÃO GERAL SEJA UMA MELHORIA DO ONDE
# FOCAR, ENTÃO PODE TIRAR O ONDE FOCAR"; as colunas na ordem Performance, Manutenção e Acompanhamento; "AO CLICAR NO
# BLOCO EM VISÃO GERAL DESTAQUE AS COLUNAS DAQUELE BLOCO E ORDENE DE ACORDO COM AQUELE BLOCO") ──────────────────────
def test_onde_focar_saiu_e_a_visao_geral_e_o_padrao(manut, logado):
    # desde 28/10/2026 o padrão de um responsável escolhido é o Painel; a Visão geral segue na aba, sem Onde focar
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe").get_data(as_text=True)
    assert 'aria-current="page">Painel' in html and ">Visão geral</a>" in html and ">Onde focar</a>" not in html
    # o endereço antigo (o link guardado, o cartão do ranking de antes) abre a Visão geral
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=foco").get_data(as_text=True)
    assert 'aria-current="page">Visão geral' in html and 'class="cr-gr"' in html


def test_as_colunas_da_visao_geral_na_ordem_do_levi(manut, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    lista = _bloco_manut(html)
    cab = lista[lista.index('class="cr-cols'):]
    cab = re.findall(r"<span[^>]*>([^<]*)</span>", cab[:cab.index("</div>")])
    assert cab == ["Usina", "Meta", "PR / prev.", "Disp.", "OS abertas", "Atrasadas", "Pausadas", "Semana passada",
                   "Ronda", "Limpeza", "PT", "Chamados", "Extintores", ""]
    grupos = lista[lista.index('cr-gr-grupos'):]
    assert re.findall(r'>(Performance|Manutenção|Acompanhamento)<', grupos[:grupos.index("</div>")]) == [
        "Performance", "Manutenção", "Acompanhamento"]


def test_a_lista_geral_na_ordem_do_bloco():
    us = [{"usina": n, "meta": {"atingimento": a}, "ronda": {"tipo": t}, "manut": {"nivel": "ok"},
           "perf": {"nivel": "ok"}, "acomp": {"nivel": "ok"}, "manutencao": {}}
          for n, a, t in (("A", 99, "nunca"), ("B", 70, None), ("C", 85, "sem_ronda"))]
    assert [u["usina"] for u in R.lista_geral(us, None, "perf")] == ["B", "C", "A"]      # a pior meta primeiro
    assert [u["usina"] for u in R.lista_geral(us, None, "acomp")] == ["A", "C", "B"]     # a pior ronda primeiro
    assert [u["usina"] for u in R.lista_geral(us, None, None)] == ["A", "B", "C"]        # sem bloco, a ordem que veio
    assert [R.bloco_geral(v, f) for v, f in (("manut", None), (None, "perf.abaixo_meta"), ("xx", None), (None, None),
                                             ("acomp", "manut.atrasadas"))] == ["manut", "perf", None, None, "acomp"]


def test_o_clique_no_bloco_ordena_e_destaca(manut, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&bloco=perf").get_data(as_text=True)
    lista = _bloco_manut(html)
    nomes = re.findall(r'<details class="cr-gr-lin[^>]*>\s*<summary[^>]*>\s*<span class="cr-u"><i[^>]*></i><span><b>([^<]+)', lista)
    esperado = [u["usina"] for u in R.bloco(list(_com_manut().values()), "perf")["linhas"]]
    assert nomes == esperado
    cab = lista[lista.index('class="cr-cols'):]
    cab = cab[:cab.index("</div>")]
    assert re.findall(r'<span class="cr-col-(\w+) cr-gr-csel">', cab) == ["meta", "pr", "disp"]
    assert 'class="cr-gr-gp cr-gr-gp--perf cr-gr-gp--sel"' in lista and 'id="cr-gr-perf"' in html
    assert "Ordenado por Performance" in html and 'class="cr-gr-limpar"' in html


def test_a_largura_das_colunas_se_adapta():
    """Levi, 18/10/2026: "em visão geral tem um espaço grande para as colunas, deixe mais adaptável": as colunas
    dividem a largura (fr), em vez de px fixos com a Usina levando todo o resto."""
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    trilhas = re.search(r"\.cr-gr-g\{grid-template-columns:([^;}]*)", css).group(1)
    assert trilhas.startswith("minmax(160px,2fr)") and trilhas.count("fr)") == 13 and "px " not in trilhas.replace("160px", "")



# ── A revisão da Visão geral nova (18/10/2026) ───────────────────────────────────────────────────────────────────
def _nomes_da_lista(html):
    return re.findall(r'<details class="cr-gr-lin[^>]*>\s*<summary[^>]*>\s*<span class="cr-u"><i[^>]*></i><span><b>([^<]+)',
                      _bloco_manut(html))


def test_o_filtro_destaca_mas_mantem_a_ordem_do_foco(manut, logado):
    """Só o clique no nome do bloco ordena pela régua dele; o número filtra e destaca, e a lista segue na ordem do foco
    (revisão: "PT esperando" ordenado pela ronda jogava a PT parada hoje para o fim, contra a regra da tela)."""
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&filtro=manut.atrasadas").get_data(as_text=True)
    foco = [n for n, u in _com_manut().items() if (u.get("manutencao") or {}).get("atrasadas")]
    assert _nomes_da_lista(html) == foco
    cab = _bloco_manut(html)[_bloco_manut(html).index('class="cr-cols'):]
    assert re.findall(r'<span class="cr-col-(\w+) cr-gr-csel">', cab[:cab.index("</div>")]) == [
        "os", "atrasadas", "paradas", "semana"]
    us = list(_com_manut().values())
    assert R.lista_geral(us, "acomp.pts", None) == R.filtrar_geral(us, "acomp.pts")


def test_de_1181_a_1366_px_ficam_as_colunas_principais():
    """Revisão: a 1366 px (notebook comum) a tela padrão só mostrava as etiquetas, sem número. Ficam Meta, Disp.,
    Atrasadas, Pausadas, Semana passada, Ronda e PT; o resto vai ao detalhe."""
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    meio = re.search(r"@media \(min-width:1181px\) and \(max-width:1366px\)\{(.*?)\n\}", css, re.S).group(1)
    for col in ("pr", "os", "limpeza", "chamados", "extintores"):
        assert f".cr-gr-lista .cr-col-{col}" in meio, col
    assert ".cr-gr-gp--perf{grid-column:span 2}" in meio and ".cr-gr-gp--acomp{grid-column:span 2}" in meio


def test_o_bloco_escolhido_marca_a_etiqueta_no_cartao(manut, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&bloco=manut").get_data(as_text=True)
    lista = _bloco_manut(html)
    assert lista.count("cr-gr-pill--sel") == lista.count('class="cr-gr-lin') > 0
    assert re.search(r'cr-gr-pill cr-gr-pill--sel" title="Manutenção"', lista)


def test_pausadas_em_toda_a_tela(manut, logado, monkeypatch):
    html = logado.get("/t/campo/responsaveis?modo=cartoes&responsavel=*").get_data(as_text=True)
    assert "Tarefas pausadas" in html and "Tarefas paradas" not in html
    assert "a tarefa parada por motivo" not in html
    from nexus.pcm import motivos
    monkeypatch.setattr(motivos, "ler", lambda cfg, **k: {"motivos": [], "inicial": [], "marcas": [], "backoffice": [],
                                                           "erro": "ConnectionError", "lido_em": None})
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert "a coluna Pausadas fica vazia" in html


def test_todos_os_responsaveis_fica_na_visao_geral(manut, logado):
    """Revisão: quem veio do cartão (sem `modo` no endereço) caía nos cartões ao clicar em "Todos os responsáveis ×". O
    "Todos os responsáveis ×" mora na Visão geral (desde 28/10/2026 o padrão do responsável escolhido é o Painel)."""
    html = logado.get("/t/campo/responsaveis?responsavel=Ciclano+Chefe&modo=geral").get_data(as_text=True)
    todos = re.search(r'href="([^"]*)" title="As usinas de todos os responsáveis"', html).group(1)
    assert "modo=geral" in todos
    html = logado.get("/t/campo/responsaveis?modo=cartoes&responsavel=*&filtro=manut.atrasadas&bloco=perf").get_data(as_text=True)
    cartoes = re.findall(r'class="cn-equipe[^"]*cn-sup[^"]*" href="([^"]*)"', html)
    assert cartoes and all("filtro=" not in h and "bloco=" not in h for h in cartoes)


def test_a_zeladoria_vencida_aparece_no_nome(manut, logado):
    """Revisão: a zeladoria saiu das colunas (vai ao detalhe), e a usina ficava amarela sem motivo à vista."""
    _aba(manut, "nexus_os", "fato_tarefa_os", [_tarefa(1, 901, 2, 31), _tarefa(2, 902, 3, 12),
                                               _tarefa(3, 903, 3, 5, tipo="zeladoria")])
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    lista = _bloco_manut(html)
    i = lista.index("<b>Coração 1")
    assert "zeladoria vencida" in lista[i:lista.index("</b>", i)]


# ── O bloco inteiro, os números que filtram, a faixa verde e as réguas no "!" (Levi, 18/10/2026) ─────────────────────
def _campo_css():
    return (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")


def test_o_bloco_inteiro_ordena_e_os_numeros_por_cima_filtram():
    """Levi: "deve ser possível clicar no bloco da performance, manutenção ou acompanhamento inteiro, e não só no
    título". O link do nome cobre o cartão todo (o ::after dele); o "pedem atenção", os números, o nível e o limite das
    atrasadas ficam por cima e continuam filtrando."""
    css = _campo_css()
    assert re.search(r"\.cr-gr-bloco\{[^}]*position:relative", css)
    assert re.search(r'\.cr-gr-tit::after\{content:"";position:absolute;inset:0', css)
    por_cima = re.search(r"\n([^{}\n]*a\.cr-gr-kpi[^{}]*)\{position:relative;z-index:1\}", css).group(1)
    for sel in (".cr-gr-bloco a.cr-gr-atn", ".cr-gr-bloco a.cr-gr-kpi", ".cr-gr-bloco a.cr-gr-chip", ".cr-gr-limite"):
        assert sel in por_cima, sel


def test_os_abertas_tambem_filtra(manut, logado):
    """Levi: "em clicar no card, por exemplo 'abaixo da meta : 2' vai filtrar as duas usinas citadas, funcionará como
    filtro os KPIs do bloco": o OS abertas era o único número dos blocos sem filtro."""
    us = list(_com_manut().values())
    com_os = [u["usina"] for u in us if (u.get("manutencao") or {}).get("os_abertas")]
    assert com_os and R.FILTROS_GERAL["manut.os"][:2] == ("manut", "Com OS abertas")
    assert [u["usina"] for u in R.filtrar_geral(us, "manut.os")] == com_os
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert re.search(r'<a class="cr-gr-kpi" href="[^"]*filtro=manut\.os[^"]*" title="Ver [^"]*"><span class="r">OS abertas<',
                     html)
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&filtro=manut.os").get_data(as_text=True)
    assert _nomes_da_lista(html) == com_os and "Manutenção · Com OS abertas" in html


def test_o_numero_de_usinas_do_bloco_e_o_que_o_filtro_mostra(manut):
    """O "abaixo da meta: 2" mostra as 2 usinas: o número que conta usinas é o tamanho do filtro dele."""
    us = list(_com_manut().values())
    s = R.soma("Todos", us)
    assert s["abaixo_meta"]
    for chave, campo in (("perf.abaixo_meta", "abaixo_meta"), ("perf.pr_abaixo", "pr_abaixo")):
        assert len(R.filtrar_geral(us, chave)) == s[campo], chave


def test_o_destaque_do_bloco_e_uma_faixa_verde_do_cabecalho_ao_fim(manut, logado):
    """Levi: "esse destaque em azul tá feio (...) pegando cabeçalho e célula pegando a área do bloco toda!"; na mesma
    noite, "o verde está muito forte, deixe 1/3 do que está" e "tem que ser uma cor só destacando a área inteira". Uma
    faixa em cada linha, nas colunas do bloco e no espaço entre elas, do cabeçalho do grupo à última usina, OPACA e por
    cima da linha que separa as usinas: as linhas juntas fazem uma área só, de uma cor."""
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&bloco=manut").get_data(as_text=True)
    assert '<div class="cr-gr-lista" data-bloco="manut">' in html
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert '<div class="cr-gr-lista">' in html
    css = _campo_css()
    faixa = re.search(r"\.cr-gr-lista\[data-bloco\] \.cr-gr-g::before\{([^}]*)\}", css).group(1)
    assert "background:var(--faixa-verde)" in faixa and "position:absolute" in faixa and "z-index:-1" in faixa
    assert "bottom:-9px" in faixa                    # cobre a linha de 1 px entre as usinas (o padding é de 8 px)
    nexus = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "nexus.css").read_text(encoding="utf-8")
    assert re.findall(r"--faixa-verde:(#[0-9a-f]{6});", nexus) == ["#24302b", "#f6fbe9"]      # opaca nos dois temas
    meio = re.search(r"@media \(min-width:1181px\) and \(max-width:1366px\)\{(.*?)\n\}", css, re.S).group(1)
    for b, larga, estreita in (("perf", "2 / span 3", "2 / span 2"), ("manut", "5 / span 4", "4 / span 3"),
                               ("acomp", "9 / span 5", "7 / span 2")):
        assert f'.cr-gr-lista[data-bloco="{b}"] .cr-gr-g::before{{grid-column:{larga}}}' in css, b
        assert f'.cr-gr-lista[data-bloco="{b}"] .cr-gr-g::before{{grid-column:{estreita}}}' in meio, b
    cartoes = re.search(r"@media \(max-width:1180px\)\{\n  \.cr-gr-grupos(.*?)\n\}", css, re.S).group(1)
    assert ".cr-gr-lista[data-bloco] .cr-gr-g::before{display:none}" in cartoes
    assert not re.search(r"\.cr-gr-csel\{[^}]*superficie-3", css)                      # o azul saiu


def test_as_reguas_ficam_no_ponto_de_exclamacao_abaixo_da_tabela(manut, logado):
    """Levi: o texto "De onde vem cada número, e a régua de cada alerta. (...)" "deve ficar em um símbolo de exclamação
    abaixo da tabela!". Fechado ao abrir a tela; o símbolo abre o texto de sempre."""
    for modo, tabela in (("geral", 'class="cr-gr-lista"'), ("cartoes", 'class="cn-equipes"')):
        html = logado.get(f"/t/campo/responsaveis?responsavel=*&modo={modo}").get_data(as_text=True)
        i = html.index('<details class="cr-info">')
        assert html.index(tabela) < i < html.index("<b>De onde vem cada número, e a régua de cada alerta.</b>"), modo
        resumo = html[i:html.index("</summary>", i)]
        assert 'aria-label="De onde vem cada número e a régua de cada alerta"' in resumo and "ph-warning-circle" in resumo


# ── O número anômalo (Levi, 18/10/2026: "apenas sinalize que o número está anômalo e o dado pode estar errado, temos
# que sinalizar pela plataforma e não ficar travando a construção!") ─────────────────────────────────────────────────
def test_a_meta_anomala_da_plataforma_e_sinalizada_e_o_numero_fica(tela, logado):
    # a plataforma diz que o número é anômalo: a coluna `anomalia` no fim do fato_meta_usina_mes, com CÓDIGOS de uma
    # lista fechada (regra 8 da camada de dados: no fato, nada de texto livre); a frase é do Nexus (`dominios`). O Nexus
    # só mostra: o número e a cor continuam os do Gerencial, com a etiqueta e o porquê
    from nexus.dados import dominios as DOM
    linhas = [dict(_meta("Altair", 850000, 1000000, 85.0), anomalia="meta_baixa"),
              dict(_meta("Brodowski 1 A", 600000, 500000, 120.0, pr=82, pr_meta=80), anomalia="meta_alta, novo_x"),
              _meta("Brodowski 1 B", 400000, 500000, 80.0, pr=78, pr_meta=80), _meta("Coração 1", 990000, 1000000, 99.0)]
    _aba(tela, "nexus_performance", "fato_meta_usina_mes", linhas)
    visao.limpar()
    u = _por_usina()
    baixa = DOM.ANOMALIA_META["meta_baixa"]
    assert u["Altair"]["meta"]["anomalia"] == baixa and u["Altair"]["meta"]["atingimento"] == 85.0
    # duas linhas do Gerencial na mesma usina: as frases das duas; o código que o Nexus não conhece não some
    assert u["Brodowski 1"]["meta"]["anomalia"] == f"{DOM.ANOMALIA_META['meta_alta']} · {DOM.ANOMALIA_DESCONHECIDA}"
    assert not u["Coração 1"]["meta"]["anomalia"]
    v = u["Altair"]["perf"]["valores"]["meta"]
    assert (v["txt"], v["sub"]) == ("85%", "anômalo") and baixa in v["dica"] and "O dado pode estar errado" in v["dica"]
    assert any(baixa in (d.get("alerta") or "") for d in u["Altair"]["perf"]["det"])
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=foco").get_data(as_text=True)
    assert html.count("<small>anômalo</small>") == 2 and f"dado anômalo: {baixa}. O dado pode estar errado" in html


def test_o_dominio_da_anomalia_e_a_regua_unica_da_plataforma():
    # o Levi escolheu UMA régua (18/10/2026, na plataforma): a meta do mês fora de 2 a 8 kWh por kWp por dia; recusou as
    # outras (PR do mês acima de 130%, geração acima de 8 kWh/kWp/dia, atingimento acima de 200%)
    from nexus.dados import dominios as DOM
    # e o dia que o filtro da plataforma tirou da conta (geração acima da potência × 12 h: a Ibirapuã II em 10/2026, o
    # filtro que o Levi pediu "especificamente para essa usina")
    assert set(DOM.ANOMALIA_META) == {"meta_baixa", "meta_alta", "geracao_impossivel"}
    assert "geração acima da potência × 12 h" in DOM.ANOMALIA_META["geracao_impossivel"]
    assert "abaixo de 2 kWh por kWp por dia" in DOM.ANOMALIA_META["meta_baixa"]
    assert "acima de 8 kWh por kWp por dia" in DOM.ANOMALIA_META["meta_alta"]
    # a frase que a plataforma tinha montado não é código: vira o sinal genérico, nunca some
    assert DOM.anomalias("meta do mês de 0,9 kWh por kWp por dia (o normal é de 2 a 8)") == [DOM.ANOMALIA_DESCONHECIDA]


# ── O detalhe da usina na Visão geral (Levi, 18/10/2026: "quando expandir a informação dos blocos clicando na usina em
# visão geral eu gostaria de algumas mudanças"; "o restante deixe como estar") ─────────────────────────────────────────
def test_o_detalhe_sem_os_links_do_fim_e_com_os_titulos_no_centro(manut, logado):
    """"os títulos PERFORMANCE, MANUTENÇÃO E ACOMPANHAMENTO QUERO CENTRALIZADOS"; "Esses links no final com palavras em
    verde grid pode tirar, a ideia é resolver a maior parte por essa tela"."""
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    lista = _bloco_manut(html)
    assert 'class="cr-gr-det"' in lista and 'class="cr-links"' not in lista
    assert "Rondas da usina" not in lista and "Gestão PCM</a>" not in lista and "Visão gerencial</a>" not in lista
    assert re.search(r"\.cr-gr-det h3\{[^}]*text-align:center", _campo_css())


def test_as_os_abertas_em_linhas_e_a_nao_iniciada_abre_o_quadro(manut, logado):
    """"Em OSs abertas quero que separe por linha, o que está dependendo de aprovação e o que não foi iniciado, ao clicar
    em o que não foi iniciado abre o link do quadro da semana filtrando o cliente com o nome da usina pesquisada!". O
    nome é o do site no Fracttal (o do arquivo do PCM) quando o de-para tem; senão, o do cadastro."""
    _aba(manut, "nexus_os", "fato_tarefa_os", [
        _tarefa(1, 901, 2, 31), _tarefa(2, 902, 2, 3), _tarefa(3, 902, 2, 3, estado="em_progresso"),
        _tarefa(4, 903, 2, 3, status="em_verificacao", estado="finalizada"),
        _tarefa(5, 904, 1, 3)])
    # o nome provisório que o cadastro dá ao site ainda sem a Classificação 1 do Fracttal não é nome de usina no arquivo
    # do PCM (medido em 18/10/2026: 3 dos 8 links sem tarefa eram ele): fica o nome do cadastro
    _aba(manut, "cadastro_nexus", "de_para", [
        {"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Altair 1 - SP"},
        {"usina_id": 2, "sistema": "Fracttal · Classificação 1", "chave_externa": "(sem Classificação 1) BWK100"},
        {"usina_id": 2, "sistema": "BD_Thopen · aba", "chave_externa": "Brodowski I A"},
        {"usina_id": 2, "sistema": "BD_Thopen · aba", "chave_externa": "Brodowski I B"}])
    visao.limpar()
    us = _com_manut()
    det = next(i for i in us["Brodowski 1"]["manut"]["det"] if i["rot"] == "OS abertas")
    assert det["resto"] == "3 OS abertas"
    assert [(x["forte"], bool(x.get("quadro"))) for x in det["itens"]] == [
        ("1 esperando a aprovação", False), ("1 não iniciada", True), ("1 em execução", False)]
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    links = re.findall(r'<a class="cn-link" href="(/t/pcm/quadro\?[^"]*)"[^>]*>([^<]+)</a>', html)
    assert sorted(t for _h, t in links) == ["1 não iniciada", "1 não iniciada"]           # Brodowski 1 e Altair
    hrefs = [h.replace("&amp;", "&") for h, _t in links]
    assert any("cliente=Thopen" in h and "q=Brodowski+1" in h for h in hrefs)              # sem o site no de-para
    assert any("cliente=Thopen" in h and "q=Thopen+-+Altair+1+-+SP" in h for h in hrefs)   # o site do Fracttal


def test_a_ultima_ronda_fica_so_na_limpeza(tela):
    """"aparece a longa pendente e a data da última ronda (...) Deixe a informação da última ronda apenas em limpeza
    pois está redundante repetindo em ronda e em limpeza". A ronda da limpeza é a última: a data sai da linha Ronda e
    fica na Limpeza, onde abre o card."""
    _aba(tela, "rondas_app_campo", "OS de ronda", [_ronda(_dia(3), OS="501", **{SUJ: 4, VEG: 2})])
    visao.limpar()
    u = _por_usina()["Altair"]
    ronda = next(i for i in u["acomp"]["det"] if i["rot"] == "Ronda")
    limpeza = next(i for i in u["acomp"]["det"] if i["rot"] == "Limpeza")
    dm = f"{_dia(3)[8:10]}/{_dia(3)[5:7]}"
    assert ronda["resto"] == "Em dia" and not ronda.get("ronda")
    assert limpeza["resto"] == "Sujidade 4 · Vegetação 2" and limpeza["ronda"] == {"os": 501, "data": _dia(3),
                                                                                  "txt": f"ronda de {dm}"}


def test_a_ronda_sem_limpeza_mais_nova_fica_na_linha_ronda(tela):
    """Quando a última ronda não tem a limpeza (a leitura é de uma ronda mais antiga), a data dela não é repetida: fica
    na linha Ronda, e abre o card dela."""
    _aba(tela, "rondas_app_campo", "OS de ronda", [_ronda(_dia(5), OS="501", **{SUJ: 3, VEG: 3}),
                                                   _ronda(_dia(1), OS="502")])
    visao.limpar()
    u = _por_usina()["Altair"]
    ronda = next(i for i in u["acomp"]["det"] if i["rot"] == "Ronda")
    limpeza = next(i for i in u["acomp"]["det"] if i["rot"] == "Limpeza")
    assert ronda["resto"] == "Em dia" and ronda["ronda"]["os"] == 502
    assert ronda["ronda"]["txt"] == f"última ronda em {_dia(1)[8:10]}/{_dia(1)[5:7]}"
    assert limpeza["ronda"]["os"] == 501


def test_o_card_da_ronda_por_cima_com_data_quem_fez_e_as_fotos(tela, logado):
    """"ao clicar na última ronda aparece um card sobreposto sobre a tela com um blur de fundo mostrando como foi a última
    ronda, fotos, data, quem fez". O card é a janela da Visão (o fundo desfocado); as fotos são as da OS no Fracttal,
    pedidas só quando o card abre (o mesmo pedaço do botão Fotos do histórico da usina)."""
    _aba(tela, "rondas_app_campo", "OS de ronda", [_ronda(_dia(3), OS="501", **{SUJ: 4, VEG: 2})])
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert re.search(r'data-cr-painel="/t/campo/responsaveis/usina/1/ronda\?os=501[^"]*"[^>]*>ronda de ', html)
    assert "[data-cr-fotos]" in html                                   # a janela busca as fotos ao abrir
    card = logado.get("/t/campo/responsaveis/usina/1/ronda?os=501").get_data(as_text=True)
    assert "<html" not in card and "<dt>Quem fez</dt><dd>Fulano Souza</dd>" in card         # o nome curto da tela
    assert f"{_dia(3)[8:10]}/{_dia(3)[5:7]}/{_dia(3)[:4]}" in card
    assert 'data-cr-fotos="/t/campo/rondas/os/501/fotos"' in card
    assert re.search(r"<dt>Sujidade</dt><dd[^>]*>4", card) and re.search(r"<dt>Vegetação</dt><dd[^>]*>2", card)
    sem = logado.get("/t/campo/responsaveis/usina/1/ronda?os=999").get_data(as_text=True)
    assert "Não achei esta ronda" in sem and "data-cr-fotos" not in sem


def test_o_bloco_sem_sublinhado_ao_passar_o_mouse():
    """Levi, 18/10/2026: "Tire esse underline dos blocos quando eu passo o mouse, está nos títulos e ícones de cada
    bloco": o bloco inteiro é o link do nome, e o mouse em qualquer parte dele sublinhava o nome e o ícone. Fica a
    borda do cartão como sinal de que ele é clicável."""
    css = _campo_css()
    assert not re.search(r"\.cr-gr-tit:hover\{[^}]*underline", css)
    assert re.search(r"\.cr-gr-bloco:not\(\.cr-gr-bloco--sel\):hover\{[^}]*border-color", css)


def test_o_cliente_e_o_das_usinas_do_responsavel(tela, logado):
    """Levi, 18/10/2026: "O filtro de cliente deve filtrar de acordo com o responsável": o Cliente lista só os clientes
    das usinas do responsável escolhido; o cliente que não é dele deixa de valer (a tela não esvazia)."""
    def clientes(html):
        sel = html.split('id="cr-cliente"', 1)[1].split("</select>", 1)[0]
        return re.findall(r'<option value="([^"]*)"', sel)
    url = "/t/campo/responsaveis?modo=geral&responsavel="
    assert clientes(logado.get(url + "Beltrano+Supervisor").get_data(as_text=True)) == ["", "Outro Cliente"]
    assert clientes(logado.get(url + "Ciclano+Chefe").get_data(as_text=True)) == ["", "Thopen"]
    assert clientes(logado.get(url + "*").get_data(as_text=True)) == ["", "Outro Cliente", "Thopen"]
    html = logado.get(url + "Beltrano+Supervisor&cliente=Thopen").get_data(as_text=True)
    assert "<b>Coração 1" in html and '<option value="Thopen" selected>' not in html


def test_focar_e_acompanhar_encolhem(duas_equipes, logado):
    # Levi, 19/10/2026: "deve ser possível encolher Focar e acompanhar, eles aparecem expandidos que nem estão agora"
    jan = logado.get("/t/campo/responsaveis/equipe?equipe=SP+Norte+01").get_data(as_text=True)
    assert re.search(r'<details class="cr-rk-j-bloco cr-rk-j-dobra" open>\s*<summary class="cr-rk-j-nivel '
                     r'cn-t-critico">Focar', jan)
    jan = logado.get("/t/campo/responsaveis/equipe?equipe=SC+Oeste+01").get_data(as_text=True)
    assert re.search(r'<details class="cr-rk-j-bloco cr-rk-j-dobra" open>\s*<summary class="cr-rk-j-nivel '
                     r'cn-t-alerta">Acompanhar', jan)


def test_o_card_da_os_abre_por_cima_da_janela_e_ela_volta(tela, logado, tmp_path):
    # a janela é um <dialog> modal (a camada do topo): o card da OS ficaria por baixo dela. O clique na OS de dentro da
    # janela a fecha, abre o card e, quando o card fecha (`aoFechar`), a janela volta como estava
    import shutil
    import subprocess
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking").get_data(as_text=True)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    js = "\n;\n".join(scripts)
    assert "closest('dialog[open]')" in js and "aoFechar" in js and "showModal" in js
    if shutil.which("node"):
        arq = tmp_path / "pagina.js"
        arq.write_text(js, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
