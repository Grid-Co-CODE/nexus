"""Comando > Usinas (11/11/2026, Levi: "Em comando quero a mesma visão de Início > Usinas do mockup"; o Score de saúde
"Fora por agora"; o clique na usina "No próprio Comando"). O que estes testes seguram: a conta de cada coluna
(`nexus/comando/usinas.py`) com a fonte que falta virando "sem leitura" e nunca 0, a ordem do mais grave agora, e as
duas telas (a lista e o prontuário) pela Visão do responsável falsa. Desde 11/11/2026 (Levi: "Coluna Agora pelo COS" e a
régua dele: religamento em campo crítico, inversor desligado atenção, falha de comunicação sem comunicação) a coluna Agora
segue as ocorrências abertas na fotografia da Ronda COS de cada cliente do Andamento."""
import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.campo import leitura as LE
from nexus.comando import usinas as CU
from nexus.cos import andamento as AND

AGORA = AND.instante("2026-11-11T10:00:00-03:00")
IDS = {"THPN-ALT100": 1, "THPN-BWK100": 2, "THPN-COR100": 3}


def _oc(os_="90001", tarefa="Corretiva", falha="Inversor desligado", problema="inv", abertura="2026-11-11T08:00:00-03:00",
        etapa="Técnico acionado"):
    return {"os": os_, "registro": "r" + os_, "severidade": "Médio", "tipo_tarefa": tarefa, "tipo_falha": falha,
            "problema": problema, "equipamentos": [], "falha": "texto do operador", "abertura": abertura,
            "dias_aberta": 0, "etapa": etapa}


def _foto(cliente, *usinas):
    """A fotografia de um cliente: (código, [ocorrências]) por usina."""
    return AND.Leitura(cliente, {"usinas": [{"nome": c, "codigo": c, "ocorrencias": ocs} for c, ocs in usinas]})


def _cos(*leituras):
    return CU.cos_por_usina(list(leituras), lambda nome, cod: IDS.get(cod))


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
    # Brodowski 1: um inversor desligado antigo e um religamento em campo; Altair: nada aberto; Coração 1: o cliente
    # dela não respondeu (sem leitura, nunca normal)
    cos = _cos(_foto("Thopen", ("THPN-BWK100", [_oc("90001", abertura="2026-11-01T08:00:00-03:00"),
                                               _oc("90002", tarefa="Religamento", falha="Desligamento de usina",
                                                   problema="rede")]),
                     ("THPN-ALT100", [])),
               AND.Leitura("Outro Cliente", None, erro="caiu"))
    r = CU.montar(linhas, CAD, cos, {1: 2}, {2}, com_os=True, agora=AGORA)
    assert [x["usina"] for x in r] == ["Brodowski 1", "Coração 1", "Altair"]       # crítico, sem leitura, normal
    alt = r[2]
    assert (alt["estado"], alt["estado_rot"], alt["detalhe"]) == ("normal", "Sem ocorrência", "")
    assert (alt["mwp"], alt["tipologia"], alt["codigo"]) == (5.012, "Tracker", "THPN-ALT100")
    assert (alt["atingimento"], alt["pr"], alt["pr_meta"], alt["os_abertas"], alt["os_atrasadas"]) == (96.4, 78.0, 80.0, 4, 1)
    assert alt["insights"] == 2 and alt["conformidade"] == [("2 extintores vencidos", "critico")]
    bwk = r[0]
    # o religamento em campo manda (crítico), mesmo mais novo que o inversor; o detalhe diz a OS, a idade, a etapa e mais
    assert (bwk["estado"], bwk["estado_rot"], bwk["estado_tom"]) == ("critico", "Religamento em campo", "critico")
    assert bwk["detalhe"] == "OS 90002 · há 2 h · Técnico acionado · +1 ocorrência"
    assert [o["os"] for o in bwk["os_cos"]] == ["90002", "90001"]
    assert bwk["conformidade"] == [("sem luvas", "critico")]
    assert bwk["os_abertas"] == 0 and bwk["insights"] == 0          # sem OS nem insight na usina: 0, com a fonte lida
    cor = r[1]
    assert cor["estado"] == "sem_leitura" and cor["detalhe"] == ""
    assert cor["tipologia"] == "" and cor["mwp"] is None and cor["conformidade_ok"]
    assert "thpn-alt100" in alt["busca"] and "tracker" in alt["busca"]
    assert CU.resumo(r)["por_estado"] == {"normal": 1, "atencao": 0, "critico": 1, "sem_com": 0, "sem_leitura": 1}


def test_a_regua_do_levi():
    """11/11/2026: "religamento com OS aberta em campo tem que estar como crítico", "atenção vai ser inversor desligado",
    "falha de comunicação é sem comunicação e etc"."""
    assert CU.classificar(_oc(tarefa="Religamento", falha="Desligamento de usina")) == ("critico", "Religamento em campo")
    assert CU.classificar(_oc(falha="Inversor desligado", problema="inv")) == ("atencao", "Inversor desligado")
    assert CU.classificar(_oc(falha="Perda de comunicação com a usina", problema="com")) == ("sem_com", "Sem comunicação")
    # o etc: o que para a usina é crítico; o religamento remoto e o ainda sem OS vão pela falha; o resto é atenção
    assert CU.classificar(_oc(falha="Atuação de proteção", problema="rede"))[0] == "critico"
    assert CU.classificar(_oc(falha="Desligamento de SKID", problema="x"))[0] == "critico"
    assert CU.classificar(_oc(tarefa="Religamento remoto", falha="Desligamento de usina", problema="rede")) == (
        "critico", "Desligamento de usina")
    assert CU.classificar(_oc(os_="R-77", tarefa="Religamento", falha="Inversor desligado"))[0] == "atencao"
    assert CU.classificar(_oc(falha="Tracker travado", problema="trk")) == ("atencao", "Tracker travado")
    # a pior manda: crítico > atenção > sem comunicação; nada aberto é normal; sem leitura nunca é normal
    x = CU.agora_pelo_cos([_oc(falha="Perda de comunicação", problema="com"), _oc(falha="Inversor desligado")], AGORA)
    assert (x["estado"], x["estado_rot"]) == ("atencao", "Inversor desligado")
    assert CU.agora_pelo_cos([], AGORA)["estado"] == "normal" and CU.agora_pelo_cos(None)["estado"] == "sem_leitura"
    assert CU.cos_por_usina([AND.Leitura("X", None, erro="caiu")], IDS.get) is None


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
    """A Visão do responsável, o COS > OS em aberto, os insights e as luvas falsos (o cadastro é o `banco` do Campo)."""
    from nexus.campo import responsaveis as R
    from nexus.comando import motor as MO
    from nexus.hseq import epi as EPI
    vis = {"usinas": [_visao(1, "Altair", ating=96.4, pr=78.0, prm=80.0, os_={"os_abertas": 4}, vencidos=1),
                      _visao(2, "Brodowski 1", ating=101.2),
                      _visao(3, "Coração 1", cliente="Outro Cliente")], "erros": {}, "info": {}}
    monkeypatch.setattr(R, "visao_responsaveis", lambda: LE.Leitura(vis, 0))
    monkeypatch.setattr(AND, "fonte", lambda cfg: AND.Fonte(url="http://andamento.falso", chave="chave-de-teste"))
    monkeypatch.setattr(AND, "clientes", lambda cfg: (["Thopen", "Outro Cliente"], ""))
    fotos = {"Thopen": {"gerado_em": "2026-11-11T09:00:00-03:00", "usinas": [
        {"nome": "Altair", "codigo": "THPN-ALT100", "ocorrencias": [
            _oc("7001", tarefa="Religamento", falha="Desligamento de usina", problema="rede")]},
        {"nome": "Brodowski 1", "codigo": "THPN-BWK100", "ocorrencias": []}]},
        "Outro Cliente": {"gerado_em": "2026-11-11T09:00:00-03:00", "usinas": [
            {"nome": "Coração 1", "codigo": "THPN-COR100", "ocorrencias": [
                _oc("7002", falha="Perda de comunicação", problema="com")]}]}}
    monkeypatch.setattr(AND, "ler", lambda cfg, c: AND.Leitura(c, fotos[c]))
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    monkeypatch.setattr(MO, "sem_esperar", lambda: LE.Leitura({"insights": [
        {"id": "R07:1", "regra": "R07", "sev": "critico", "titulo": "Altair sem geração há 2 dias", "acao": "Acionar o COS",
         "usina": "Altair", "torre": "cos", "evid": [], "link": "", "desde": None}]}, 0))
    monkeypatch.setattr(EPI, "luvas", lambda: LE.Leitura({"usinas": [{"usina_id": 2, "situacao": "sem_luvas"}]}, 0))
    return banco


def test_a_lista_e_o_prontuario(logado, telas, monkeypatch):
    html = logado.get("/t/comando/usinas?cliente=Thopen").get_data(as_text=True)
    assert "3 usinas mobilizadas" in html and "Score" not in html
    assert html.index(">Altair<") < html.index(">Brodowski 1<")                # o crítico antes do normal
    assert ">Religamento em campo<" in html and "OS 7001 · há 2 h" in html and "fotografia das" in html
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
    assert "No COS agora" in p and "OS 7001 · Religamento · Desligamento de usina" in p
    assert "/t/cos/ronda?cliente=Thopen" in p
    assert 'href="/t/comando/usinas"' in p and "/t/campo/responsaveis?modo=usina&amp;usina=1" in p
    assert logado.get("/t/comando/usinas/999").status_code == 404
