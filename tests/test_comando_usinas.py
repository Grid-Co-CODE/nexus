"""Comando > Usinas (11/11/2026, Levi: "Em comando quero a mesma visão de Início > Usinas do mockup"; o Score de saúde
"Fora por agora"; o clique na usina "No próprio Comando"). O que estes testes seguram: a conta de cada coluna
(`nexus/comando/usinas.py`) com a fonte que falta virando "sem leitura" e nunca 0, a ordem do mais grave agora, e as
duas telas (a lista e o prontuário) pela Visão do responsável falsa."""
import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.campo import leitura as LE
from nexus.comando import usinas as CU


def _visao(uid, usina, cliente="Thopen", ating=None, pr=None, prm=None, os_=None, vencidos=0):
    return {"usina_id": uid, "usina": usina, "cliente": cliente, "cluster": "SP Norte",
            "meta": {"atingimento": ating, "pr": pr, "pr_meta": prm} if ating is not None else None,
            "manutencao": os_ if os_ is not None else {},
            "extintores": {"total": 3, "vencidos": vencidos}}


CAD = {1: {"nome": "Altair", "codigo": "THPN-ALT100", "potencia_contratual": "5.012", "tipologia": "SOLO TRACKER"},
       2: {"nome": "Brodowski 1", "codigo": "THPN-BWK100", "potencia_contratual": "3.26", "tipologia": "SOLO FIXA"},
       3: {"nome": "Coração 1", "codigo": "", "potencia_contratual": "", "tipologia": "N/I"}}


def test_as_colunas_e_a_ordem():
    linhas = [_visao(1, "Altair", ating=96.4, pr=78.0, prm=80.0, os_={"os_abertas": 4, "atrasadas_os": 1}, vencidos=2),
              _visao(2, "Brodowski 1", ating=101.2, pr=82.0, prm=80.0),
              _visao(3, "Coração 1", cliente="Outro Cliente")]
    tr = {1: {"status": "ok"}, 2: {"status": "sem_producao"}, 3: {"status": "ok", "causa": "Sem sol agora"}}
    r = CU.montar(linhas, CAD, tr, {1: 2}, {2}, com_os=True)
    assert [x["usina"] for x in r] == ["Brodowski 1", "Coração 1", "Altair"]       # sem produção, sem sol, normal
    alt = r[2]
    assert (alt["estado_rot"], alt["mwp"], alt["tipologia"], alt["codigo"]) == ("Normal", 5.012, "Tracker", "THPN-ALT100")
    assert (alt["atingimento"], alt["pr"], alt["pr_meta"], alt["os_abertas"], alt["os_atrasadas"]) == (96.4, 78.0, 80.0, 4, 1)
    assert alt["insights"] == 2 and alt["conformidade"] == [("2 extintores vencidos", "critico")]
    bwk = r[0]
    assert bwk["estado_rot"] == "Sem produção" and bwk["conformidade"] == [("sem luvas", "critico")]
    assert bwk["os_abertas"] == 0 and bwk["insights"] == 0          # sem OS nem insight na usina: 0, com a fonte lida
    cor = r[1]
    assert cor["tipologia"] == "" and cor["mwp"] is None and cor["conformidade_ok"]
    assert "thpn-alt100" in alt["busca"] and "tracker" in alt["busca"]
    assert CU.resumo(r)["por_estado"] == {"ok": 1, "atencao": 0, "critico": 1, "sem_comm": 0, "sem_leitura": 1}


def test_a_fonte_que_falta_e_sem_leitura_nunca_zero():
    linhas = [dict(_visao(1, "Altair"), extintores=None)]
    x = CU.montar(linhas, CAD, None, None, None, com_os=False)[0]
    assert x["estado"] == "sem_leitura" and x["os_abertas"] is None and x["insights"] is None
    assert x["conformidade_sem_fonte"] and not x["conformidade_ok"]


def test_os_insights_vivos_por_usina():
    ins = [{"id": "R07:1", "usina": "Altair"}, {"id": "R11:1", "usina": "ALTAIR"}, {"id": "R03:x", "usina": "Coração 1"},
           {"id": "R05:y", "usina": "Usina fora do cadastro"}]
    est = {"R11:1": {"evento": "concluiu"}, "R03:x": {"evento": "assumiu"}}
    nomes = {CU._norm("Altair"): 1, CU._norm("Coração 1"): 3}
    assert CU.insights_por_usina(ins, est, nomes) == {1: 1, 3: 1}
    assert CU.insights_por_usina(None, est, nomes) is None


@pytest.fixture
def telas(monkeypatch, banco):
    """A Visão do responsável, o tempo real, os insights e as luvas falsos (o cadastro é o `banco` do Campo)."""
    from nexus.campo import responsaveis as R
    from nexus.campo import visao_cliente as VC
    from nexus.comando import motor as MO
    from nexus.hseq import epi as EPI
    vis = {"usinas": [_visao(1, "Altair", ating=96.4, pr=78.0, prm=80.0, os_={"os_abertas": 4}, vencidos=1),
                      _visao(2, "Brodowski 1", ating=101.2),
                      _visao(3, "Coração 1", cliente="Outro Cliente")], "erros": {}, "info": {}}
    monkeypatch.setattr(R, "visao_responsaveis", lambda: LE.Leitura(vis, 0))
    monkeypatch.setattr(VC, "ler_tempo_real", lambda cfg: {
        "usinas": [{"usina": "Altair", "status": "critico"}, {"usina": "Brodowski 1", "status": "ok"}],
        "cache_ts": "14:20:00", "idade_s": 30, "erro": ""})
    monkeypatch.setattr(MO, "sem_esperar", lambda: LE.Leitura({"insights": [
        {"id": "R07:1", "regra": "R07", "sev": "critico", "titulo": "Altair sem geração há 2 dias", "acao": "Acionar o COS",
         "usina": "Altair", "torre": "cos", "evid": [], "link": "", "desde": None}]}, 0))
    monkeypatch.setattr(EPI, "luvas", lambda: LE.Leitura({"usinas": [{"usina_id": 2, "situacao": "sem_luvas"}]}, 0))
    return banco


def test_a_lista_e_o_prontuario(logado, telas, monkeypatch):
    html = logado.get("/t/comando/usinas?cliente=Thopen").get_data(as_text=True)
    assert "3 usinas mobilizadas" in html and "Score" not in html
    assert html.index(">Altair<") < html.index(">Brodowski 1<")                # o crítico antes do normal
    assert 'href="/t/comando/usinas/1"' in html and "THPN-ALT100" in html
    assert '<option value="Thopen" data-rotulo="Thopen" selected>' in html      # o filtro do endereço já vem escolhido
    assert "1 extintor vencido" in html and ">sem luvas<" in html
    # o prontuário, no próprio Comando, com a Central da usina em leitura
    from nexus.campo import responsaveis as R
    from nexus.torres import campo as TC
    monkeypatch.setattr(R, "com_manutencao", lambda usinas, limite: usinas)     # as linhas falsas não têm os blocos
    monkeypatch.setattr(TC, "_central_da_usina", lambda todas, uid=None: {
        "u": {"usina_id": uid, "usina": "Altair", "cidade": "Altair", "uf": "SP", "responsavel": "Sem responsável O&M",
              "perf": {"valores": {k: {"txt": "—", "cls": "neutro"} for k in ("meta", "pr", "disp")}, "det": []},
              "manut": {"valores": {"atrasadas": {"txt": "0", "cls": "ok"}}, "det": []},
              "acomp": {"valores": {k: {"txt": "—", "cls": "neutro"} for k in ("ronda", "chamados", "pt")}, "det": []}},
        "erros": {}, "pessoas": {"supervisor": "", "gestor": "", "tecnicos": []}, "ocorrencias": [], "seguranca": [],
        "ronda_pendente": [], "os_pendentes": [], "os_linhas": [], "ronda_limpeza": [], "graf_ger": None})
    p = logado.get("/t/comando/usinas/1").get_data(as_text=True)
    assert "Prontuário da usina" in p and "Altair sem geração há 2 dias" in p and "Crítico" in p
    assert 'href="/t/comando/usinas"' in p and "/t/campo/responsaveis?modo=usina&amp;usina=1" in p
    assert logado.get("/t/comando/usinas/999").status_code == 404
