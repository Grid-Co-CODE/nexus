"""A visão do Nexus para o Campo · App (05/10/2026): Rondas, PT, Zeladoria, Ranking, Central de atenção e a aprovação da
PT, pelos livros que o App grava no banco e pelo cadastro do Nexus. Banco falso (pg_falso), datas relativas a hoje."""
import base64
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo import decisao_pt, fracttal, pt_fracttal, visao
from nexus.campo.ligacao_cadastro import codigo_da_pessoa

BRT = timezone(timedelta(hours=-3))
CHAVE = "chave-de-teste"
HOJE = datetime.now(BRT).date()


def _dia(n):
    return (HOJE - timedelta(days=n)).isoformat()


def _iso_utc(horas_atras):
    return (datetime.now(timezone.utc) - timedelta(hours=horas_atras)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _aba(api, livro, aba, linhas):
    api.workbooks[livro] = {}
    cab = list(linhas[0]) if linhas else ["vazio"]
    api._id(livro, aba)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]


_MOB = "2025-10-01"
USINAS = [{"usina_id": 1, "nome": "Altair", "codigo": "THPN-ALT100", "status": "OPERAÇÃO", "equipe_id": 10,
           "data_mobilizacao": _MOB, "uf": "SP", "cidade": "Altair", "cliente_id": 1, "cluster": "SP Norte"},
          {"usina_id": 2, "nome": "Brodowski 1", "codigo": "THPN-BWK100", "status": "OPERAÇÃO", "equipe_id": 10,
           "data_mobilizacao": _MOB, "uf": "SP", "cidade": "Brodowski", "cliente_id": 1, "cluster": "SP NORTE"},
          {"usina_id": 3, "nome": "Coração 1", "codigo": "THPN-COR100", "status": "OPERAÇÃO", "equipe_id": 20,
           "data_mobilizacao": _MOB, "uf": "SC", "cidade": "Coração", "cliente_id": 2, "cluster": "SC oeste"},
          {"usina_id": 4, "nome": "Nova", "codigo": "THPN-NOV100", "status": "A MOBILIZAR", "equipe_id": 20,
           "uf": "SC", "cidade": "Nova"},
          # em OPERAÇÃO no cadastro, mas sem data de mobilização: não é usina mobilizada (Levi, 05/10)
          {"usina_id": 5, "nome": "Sem Data", "codigo": "THPN-SDT100", "status": "OPERAÇÃO", "equipe_id": 20,
           "uf": "SC", "cidade": "Sem Data"}]
CLIENTES = [{"cliente_id": 1, "nome": "Thopen"}, {"cliente_id": 2, "nome": "Outro Cliente"}]
EQUIPES = [{"equipe_id": 10, "nome": "SP Norte 01"}, {"equipe_id": 20, "nome": "SC Oeste 01"}]
DE_PARA = [{"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Altair 1 - SP"}]
CHAVE_CADASTRO = gerar_chave()


def _pessoas():
    """Dois técnicos na SP Norte 01 (um Ativo, um sem status), um desligado (não conta), um na SC Oeste 01 e os dois
    supervisores, com o nome só cifrado, como no banco."""
    cofre = Cofre(CHAVE_CADASTRO)

    def p(pid, vinculo, cargo, equipe, status, sup, nome=None):
        return {"pessoa_id": pid, "vinculo": vinculo, "cargo": cargo, "equipe_id": equipe, "status": status,
                "supervisor_id": sup, "excluido": "não",
                "sensivel_cifrado": cofre.cifrar(json.dumps({"nome": nome, "nome_padrao": nome}),
                                                 f"banco/pessoas/{pid}") if nome else None}
    return [p(1, "Colaborador de campo", "Técnico O&M", 10, "Ativo", 90),
            p(2, "Colaborador de campo", "Eletricista O&M", 10, None, 90),
            p(3, "Colaborador de campo", "Técnico O&M", 10, "Desligado", 90),
            p(4, "Colaborador de campo", "Técnico O&M", 20, "Ativo", 91),
            p(90, "Supervisor", None, None, None, None, "Beltrano Supervisor"),
            p(91, "Supervisor", None, None, None, None, "Ciclano Chefe")]


def _ronda(dia, usina="Thopen - Altair 1 - SP", ativo="THPN-ALT100", **kw):
    d = {"Data": dia, "OS": "500", "Usina": usina, "Ativo da usina no Fracttal": ativo, "ID da OS no Fracttal": "5000",
         "Região": "SP Norte 01", "Técnico": "Fulano de Tal Souza", "Tipo": "curta", "Situação da OS": "Criada",
         "Nota da ronda": 90, "Falhas": None, "Trackers apontados": 0, "Trackers respondidos": 0,
         "Início": f"{dia}T10:00:00.000Z", "Fim": f"{dia}T11:00:00.000Z", "OS criada em": None}
    d.update(kw)
    return d


def _pt(numero, horas_atras, situacao="aguardando", decidida_horas_atras=None):
    return {"Criada em": _iso_utc(horas_atras), "Número": numero, "OS": "700", "Tarefa": "Troca de string",
            "Código do ativo": "THPN-ALT100-INVR1", "Usina": "Thopen - Altair 1 - SP", "Região": "SP Norte 01",
            "Ativo": "Inversor 1", "Solicitante (HMAC)": codigo_da_pessoa(CHAVE, "tec1@exemplo.test"),
            "Situação": situacao, "Decidida em": _iso_utc(decidida_horas_atras) if decidida_horas_atras else None,
            "Decidida por (HMAC)": None, "Papel de quem decidiu": "Admin" if decidida_horas_atras else None,
            "Motivo": None, "Efeito": None, "Respostas NÃO": 2, "Faltam": None,
            "Atividades": "Eletricidade: 3 sim, 2 não, 0 NA", "Forçada": None}


def _fech(horas_atras, nota, regiao="SP Norte 01", **kw):
    d = {"Registrado em": _iso_utc(horas_atras), "OS": "800", "ID da OS no Fracttal": "8000", "Tarefa": "Inspeção",
         "Código do ativo": "THPN-ALT100-INVR1", "Usina": "Thopen · Thopen - Altair 1 - SP", "Região": regiao,
         "Tipo da OS": "Preventiva", "Criticidade": "Alta",
         "Técnico (HMAC)": codigo_da_pessoa(CHAVE, "tec1@exemplo.test"), "Nota do painel": nota, "Pontual": "sim",
         "Devolvida": None, "Revisão": None}
    d.update(kw)
    return d


@pytest.fixture
def banco(app, tmp_path):
    api = ApiPGFalsa()
    _aba(api, "cadastro_nexus", "usinas", USINAS)
    _aba(api, "cadastro_nexus", "equipes", EQUIPES)
    _aba(api, "cadastro_nexus", "clientes", CLIENTES)
    _aba(api, "cadastro_nexus", "de_para", DE_PARA)
    _aba(api, "cadastro_nexus", "pessoas", _pessoas())
    _aba(api, "rondas_app_campo", "OS de ronda", [
        _ronda(_dia(1), Falhas="ronda longa pendente; item sem foto de evidência"),
        _ronda(_dia(3), Falhas="ronda longa pendente"),
        _ronda(_dia(2), usina="Thopen - Brodowski 1 - SP", ativo="THPN-BWK100", OS=None,
               **{"Situação da OS": "Não criada — Fracttal: Conecte"})])
    _aba(api, "pt_app_campo", "PT", [_pt("PT-1", 30), _pt("PT-2", 1), _pt("PT-3", 50, "de_acordo", 49)])
    _aba(api, "fechamentos_app_campo", "Fechamentos", [_fech(5, 90), _fech(6, 70), _fech(7, 100, regiao="Grid Co.")])
    _aba(api, "decisoes_app_campo", "Decisões", [{"Quando": _iso_utc(2), "Origem": "Central de atenção", "OS": "1",
                                                   "Ação": "resolvida", "Texto": "ok", "Tipo do ponto": "desvio",
                                                   "Usina": "Altair", "Prazo": None, "Decidido por (HMAC)": None}])
    _aba(api, "zeladoria_app_campo", "Zeladoria", [])
    ident = tmp_path / "identidades.json"
    ident.write_text(json.dumps({"porEmail": {"tec1@exemplo.test": {"nome": "Técnico Um da Silva"}}}), encoding="utf-8")
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_PESSOA_HMAC=CHAVE, NEXUS_CAMPO_IDENTIDADES=str(ident),
                      GRIDCO_SQL_TOKEN="token-de-teste", NEXUS_CHAVE_CADASTRO=CHAVE_CADASTRO)
    app.extensions["nexus_dados_sessao"] = api
    visao.limpar()
    with app.app_context():
        yield api
    visao.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def test_so_usina_mobilizada_entra_e_com_estado_e_cidade(banco):
    d = visao.rondas().dados
    cob = {c["usina"]: c for c in d["cobertura"]}
    assert set(cob) == {"Altair", "Brodowski 1", "Coração 1"}      # a mobilizar e a sem data de mobilização ficam fora
    assert d["sem_mobilizacao"] == ["Sem Data"]
    assert (cob["Altair"]["uf"], cob["Altair"]["cidade"]) == ("SP", "Altair")
    assert cob["Altair"]["dias"] == 1 and cob["Brodowski 1"]["dias"] == 2 and cob["Coração 1"]["dias"] == 999
    assert d["cobertura"][0]["usina"] == "Coração 1"                    # a mais tempo sem ronda primeiro
    assert d["todas"][0]["tecnico"] == "Fulano Souza"                 # nome resumido: o "Nome padrão" do cadastro
    k = visao.painel_rondas(d["todas"], d["cobertura"], 14, d["hoje"])["kpi"]
    assert (k["rondas"], k["cobertas"], k["usinas"], k["sem_os"]) == (3, 2, 3, 1)


def test_painel_de_rondas_duracao_veredito_e_indicadores(banco):
    d = visao.rondas().dados
    r = d["todas"][0]
    assert r["dur_min"] == 60 and r["ini_hm"] == "07:00"              # 10:00Z = 07:00 em Brasília
    vered = {(x["usina"], x["data"]): x["veredito"] for x in d["todas"]}
    assert vered[("Altair", _dia(1))] == ("alerta", "Atenção")       # 90% com pendência
    p = visao.painel_rondas(d["todas"], d["cobertura"], 7, d["hoje"])
    k = p["kpi"]
    assert k["cobertura_pct"] == 67 and k["qualidade"] == 90 and k["dur_media"] == 60 and k["curtas"] == 0
    assert k["atrasada"]["usina"] == "Coração 1" and k["nunca"] == 1
    assert p["quem"][0]["tecnico"] == "Fulano Souza" and p["quem"][0]["rondas"] == 3


def test_tela_de_rondas_no_estilo_do_painel(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert "Cobertura, duração e qualidade da ronda" in html and "Rondas finalizadas" in html
    assert "Usina mais atrasada" in html and "Rondas diárias" in html and 'class="cn-avatar">FS<' in html
    assert "1h00" in html and "Atenção" in html and "Exportar CSV" in html
    r = logado.get("/t/campo/rondas?csv=1")
    assert r.mimetype == "text/csv" and "Fulano Souza" in r.get_data(as_text=True)
    assert "Coração 1" in logado.get("/t/campo/rondas?aba=cobertura").get_data(as_text=True)
    quem = logado.get("/t/campo/rondas?aba=quem").get_data(as_text=True)
    assert "Quem ronda, por cluster" in quem and "SP Norte" in quem and "SC Oeste" in quem
    assert "Fulano Souza" in logado.get("/t/campo/rondas?aba=quem&cluster=SP+Norte").get_data(as_text=True)
    assert "Nenhuma ronda" in logado.get("/t/campo/rondas?dur=curta").get_data(as_text=True)


def test_pt_fila_da_mais_antiga_nome_resumido_e_local(banco):
    d = visao.pts().dados
    assert [p["numero"] for p in d["aguardando"]] == ["PT-1", "PT-2"]
    a = d["aguardando"][0]
    assert d["resumo"]["paradas"] == 1 and a["solicitante"] == "Técnico Silva" and a["parada"]
    assert (a["usina"], a["uf"], a["cidade"]) == ("Altair", "SP", "Altair")
    assert a["atividades"] == ["Eletricidade: 3 sim, 2 não, 0 NA"]
    assert d["historico"][0]["espera_min"] == 60


def test_ranking_so_pontua_quem_tem_nota_e_cobertura(banco):
    d = visao.ranking(30).dados
    reg = {a["nome"]: a for a in d["regioes"]}
    assert reg["SP Norte 01"]["nota"] == 80 and reg["SP Norte 01"]["cobertura_pct"] == 100
    assert reg["SP Norte 01"]["pontos"] == round(0.6 * 80 + 0.4 * 100)
    assert reg["SC Oeste 01"]["pontos"] is None                        # sem fechamento: não ganha 100 pela cobertura
    assert [a["nome"] for a in d["fora_do_cadastro"]] == ["Grid Co."]
    assert d["colaboradores"][0]["nome"] == "Técnico Silva" and d["colaboradores"][0]["os"] == 3


def test_central_em_tres_visoes(banco):
    d = visao.atencao(14).dados
    pend = {p["usina"]: p for p in d["pendentes"]}
    assert set(pend) == {"Coração 1", "Altair"}                        # Brodowski: ronda há 2 dias, sem longa pendente
    assert pend["Coração 1"]["tipo"] == "nunca"
    assert pend["Altair"]["tipo"] == "longa_pendente"                  # duas rondas com o aviso, uma linha só
    assert d["pendentes"][0]["usina"] == "Coração 1"
    st = {(f["usina"], f["data"]): f["status"] for f in d["feitas"]}
    assert st[("Brodowski 1", _dia(2))] == "sem_os" and st[("Altair", _dia(1))] == "incompleta"
    assert st[("Altair", _dia(3))] == "ok"                             # só a longa pendente: não é evidência faltando
    inc = next(f for f in d["feitas"] if f["status"] == "incompleta")
    assert inc["obs"] == "item sem foto de evidência" and inc["feito_por"] == "Fulano Souza" and inc["os"] == "500"
    assert [p["numero"] for p in d["pts"]] == ["PT-1", "PT-2"]


def test_zeladoria_vazia_diz_por_que(banco, logado):
    html = logado.get("/t/campo/zeladoria").get_data(as_text=True)
    assert "Nenhum registro de zeladoria pelo App ainda" in html


def test_telas_mostram_o_dado_do_banco(banco, logado):
    assert "Coração 1" in logado.get("/t/campo/rondas").get_data(as_text=True)
    assert "PT-1" in logado.get("/t/campo/pt?modo=tabela").get_data(as_text=True)
    assert "SP Norte 01" in logado.get("/t/campo/ranking").get_data(as_text=True)


def test_central_separa_ronda_de_pt_e_sem_hashtag_na_os(banco, logado):
    html = logado.get("/t/campo/atencao?modo=tabela").get_data(as_text=True)
    # só o que está pendente (Levi, 05/10): as rondas feitas foram para a tela Rondas
    assert "Rondas pendentes" in html and "Rondas feitas" not in html and "Permissões de trabalho" in html
    assert "Nunca teve ronda" in html and "Coração" in html
    assert "<th>Usina</th><th>Equipe</th><th>Estado</th><th>Região</th>" in html and "<th>Cidade</th>" not in html
    assert "<th>O quê</th>" not in html and "<th>Quem</th>" not in html
    html = logado.get("/t/campo/rondas?pend=sem_os").get_data(as_text=True)
    assert "<th>Pendências</th>" in html and "Não criada" in html and "Brodowski 1" in html and "#500" not in html
    html = logado.get("/t/campo/rondas?pend=incompleta").get_data(as_text=True)
    assert "item sem foto de evidência" in html and ">500<" in html
    html = logado.get("/t/campo/atencao?vista=pt&modo=tabela").get_data(as_text=True)
    assert 'class="cn-link" href="/t/campo/pt/PT-1"' in html and "Técnico Silva" in html
    assert "Ronda longa pendente" not in html                          # na visão de PT, só status de PT
    html = logado.get("/t/campo/atencao?vista=pt&modo=tabela&f=parada").get_data(as_text=True)
    assert "/t/campo/pt/PT-1" in html and "/t/campo/pt/PT-2" not in html


def test_regiao_do_brasil_pela_uf_e_cartoes_por_equipe(banco):
    d = visao.atencao(14).dados
    assert {p["usina"]: (p["equipe"], p["regiao_br"]) for p in d["pendentes"]} == {
        "Coração 1": ("SC Oeste 01", "Sul"), "Altair": ("SP Norte 01", "Sudeste")}
    c = {x["equipe"]: x for x in visao.por_equipe(d["usinas"], d["pendentes"], d["feitas"], d["pts"], d["times"])}
    sp, sc = c["SP Norte 01"], c["SC Oeste 01"]
    assert (sp["usinas"], sp["pendentes"], sp["feitas"], sp["pct_feitas"]) == (2, 1, 1, 50)   # Altair: longa pendente
    assert (sc["usinas"], sc["pendentes"], sc["feitas"], sc["pct_feitas"]) == (1, 1, 0, 0)
    assert sp["longa_pendente"] == 1 and sc["nunca"] == 1 and sp["regioes"] == ["Sudeste"] and sp["ufs"] == ["SP"]
    assert sp["rondas"] == 3 and sp["sem_os"] == 1 and sp["incompleta"] == 1 and sp["pts"] == 2 and sp["parada"] == 1
    # técnicos e supervisor pelo cadastro: o desligado não conta; o sem status conta (ver visao._Base._time)
    assert (sp["tecnicos"], sp["ativos"], sp["supervisor"]) == (2, 1, "Beltrano Supervisor")
    assert sp["cargos"] == {"Técnico O&M": 1, "Eletricista O&M": 1}
    assert (sc["tecnicos"], sc["supervisor"]) == (1, "Ciclano Chefe")


def test_sem_a_chave_do_cadastro_o_supervisor_sai_pelo_numero(app, banco):
    app.config["NEXUS_CHAVE_CADASTRO"] = None
    visao.limpar()
    assert {x["supervisor"] for x in visao.atencao(14).dados["usinas"]} == {"Supervisor 90", "Supervisor 91"}


def test_central_abre_nos_cartoes_e_o_cartao_leva_a_tabela_da_equipe(banco, logado):
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert 'class="cn-equipes"' in html and "SP Norte 01" in html and "SC Oeste 01" in html and "<table>" not in html
    assert "50%" in html and "feitas" in html and "Sudeste" in html
    assert "modo=tabela&amp;equipe=SP+Norte+01" in html or "equipe=SP+Norte+01" in html
    html = logado.get("/t/campo/atencao?equipe=SP+Norte+01").get_data(as_text=True)
    assert "<table>" in html and "Altair" in html and "Coração 1" not in html and "Equipe: SP Norte 01" in html
    # filtro pela região do Brasil, no lugar do estado
    html = logado.get("/t/campo/atencao?regiao=Sul&modo=tabela").get_data(as_text=True)
    assert "Coração 1" in html and "Altair" not in html and 'id="cn-regiao"' in html and 'id="cn-uf"' not in html
    html = logado.get("/t/campo/atencao?vista=pt").get_data(as_text=True)
    assert "PT esperando o De acordo" in html and "SC Oeste 01" not in html   # equipe sem PT não ganha cartão


def test_cartao_tem_tecnicos_supervisor_e_total_e_filtro_de_supervisor(banco, logado):
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert 'class="cn-capacete"' in html and "<b>2</b>" in html and "2 técnicos na equipe" in html
    assert "Supervisor: <b class=\"cn-eq-sup\">Beltrano Supervisor</b>" in html
    assert "<b>2 usinas</b>total" in html and "<b>1 usina</b>pendente" in html
    assert 'id="cn-supervisor"' in html and "Ciclano Chefe" in html
    html = logado.get("/t/campo/atencao?supervisor=Ciclano+Chefe").get_data(as_text=True)
    assert "SC Oeste 01" in html and "SP Norte 01" not in html
    html = logado.get("/t/campo/atencao?supervisor=Ciclano+Chefe&modo=tabela").get_data(as_text=True)
    assert "Coração 1" in html and "Altair" not in html


def test_tela_de_pt_por_equipe_tabela_e_historico(banco, logado):
    """Levi, 05/10: divisão por equipe com o que está pendente, filtro de supervisor, linha que abre o detalhe,
    equipamento no lugar do estado, espera no fim e só o número da OS, em verde, no lugar do número da PT."""
    html = logado.get("/t/campo/pt").get_data(as_text=True)
    assert 'class="cn-equipes"' in html and "SP Norte 01" in html and "Beltrano Supervisor" in html
    assert "2</span><span class=\"d\">PT esperando o De acordo" in html and "1 parada há mais de 2 h" in html
    # a mesma tela da Central de atenção > Permissões de trabalho (Levi, 05/10)
    import re as _re
    corpo = lambda h: " ".join(_re.sub(r'href="[^"]*"', "", h[h.index('<div class="cn-equipes">'):h.index('<div class="cn-nota">')]).split())
    assert corpo(html) == corpo(logado.get("/t/campo/atencao?vista=pt").get_data(as_text=True))
    html = logado.get("/t/campo/pt?modo=tabela").get_data(as_text=True)
    assert html.count('class="cn-link cn-os"') == 2 and ">700<" in html                    # PT-1 e PT-2, pela OS
    html = logado.get("/t/campo/pt?modo=tabela").get_data(as_text=True)
    cab = ("<th>OS</th><th>Tarefa</th><th>Usina</th><th>Equipamento</th><th>Equipe</th><th>Região</th>"
           "<th>Técnico</th><th>Respostas NÃO</th><th>Espera</th>")
    assert cab in html and "<th>Estado</th>" not in html and "<th>PT</th>" not in html
    assert 'class="cn-detalhe" hidden' in html and "Atividades críticas da APR" in html and "Eletricidade" in html
    assert "Inversor 1" in html and "THPN-ALT100-INVR1" in html
    html = logado.get("/t/campo/pt?supervisor=Ciclano+Chefe&modo=tabela").get_data(as_text=True)
    assert "Nenhuma PT esperando o De acordo com esses filtros" in html
    html = logado.get("/t/campo/pt?aba=historico").get_data(as_text=True)
    assert "<th>Situação</th>" in html and "De acordo" in html and "/t/campo/pt/PT-3" in html
    assert "/t/campo/pt/PT-3/pdf" in html and "<th>PDF</th>" in html


def test_cartao_leva_a_tabela_da_equipe_com_o_supervisor(banco, logado):
    html = logado.get("/t/campo/pt").get_data(as_text=True)
    assert '<a class="cn-equipe cn-equipe--critico" href="?modo=tabela&amp;equipe=SP+Norte+01">' in html
    html = logado.get("/t/campo/pt?modo=tabela&equipe=SP+Norte+01").get_data(as_text=True)
    assert 'class="cn-faixa-equipe"' in html and "Supervisor: <b>Beltrano Supervisor</b>" in html and "2</b> técnicos" in html


class _FracttalPT:
    """O REST do Fracttal para uma OS de PT: a tarefa e os anexos (com o PDF que o App anexa no De acordo)."""

    def __init__(self, com_pdf=True):
        self.com_pdf = com_pdf

    def __call__(self, path):
        if path.startswith("work_orders_attachments"):
            dados = [{"description": "foto 1", "value": "https://s3.test/foto.jpg"}]
            if self.com_pdf:
                dados.append({"description": "Permissão de Trabalho PT-3", "value": "https://s3.test/PT-3.pdf"})
            return {"data": dados}
        if path.startswith("work_orders?wo_folio="):
            return {"data": [{"id_work_orders_tasks": 777, "tasks_description": "Troca de string"}]}
        raise AssertionError(path)


@pytest.fixture
def fracttal_pt():
    fx = _FracttalPT()
    fracttal.usar_fornecedor(fx)
    pt_fracttal.limpar()
    yield fx
    fracttal.usar_fornecedor(None)
    pt_fracttal.limpar()


def test_pdf_da_pt_vem_do_anexo_do_fracttal(banco, logado, fracttal_pt, monkeypatch):
    baixados = []
    monkeypatch.setattr(pt_fracttal, "_baixar", lambda url, lim: baixados.append(url) or b"%PDF-1.4 teste")
    r = logado.get("/t/campo/pt/PT-3/pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert 'filename="PT-3.pdf"' in r.headers["Content-Disposition"] and baixados == ["https://s3.test/PT-3.pdf"]
    fracttal_pt.com_pdf = False
    r = logado.get("/t/campo/pt/PT-3/pdf")
    assert r.status_code == 302 and "não está nos anexos" in logado.get("/t/campo/pt/PT-3").get_data(as_text=True)


def test_assinatura_do_tecnico_vem_da_apr_pelo_login_de_quem_olha(app, banco, logado, fracttal_pt, monkeypatch):
    from nexus.torres.campo import assinatura
    assert logado.get("/os/_nexus/pt/PT-1/assinatura-tecnico").get_json()["login"] is True
    _entrar_no_fracttal(app, logado, _jwt())
    pedidos = []

    def rpc_falso(jwt, email):
        def rpc(metodo, params):
            pedidos.append((metodo, params))
            if metodo == "tasks.work_order_offline_ptw_download":
                return {"data": {"pre": [{"values": {"filled_by_signature": "company_1/validations/ass.png"}}]}}
            if metodo == "companies.s3_object_get":
                return {"data": {"url": "https://s3.test/ass.png"}}
            raise AssertionError(metodo)
        return rpc
    monkeypatch.setattr(assinatura, "_rpc_de_quem_olha", rpc_falso)
    monkeypatch.setattr(pt_fracttal, "_baixar", lambda url, lim: b"\x89PNG\r\n\x1a\nimagem")
    j = logado.get("/os/_nexus/pt/PT-1/assinatura-tecnico").get_json()
    assert j["ok"] and j["img"].startswith("data:image/png;base64,")
    assert pedidos[0] == ("tasks.work_order_offline_ptw_download", {"id_work_order_task": 777})
    logado.get("/os/_nexus/pt/PT-1/assinatura-tecnico")
    assert len(pedidos) == 2                       # guardada 1 h: a segunda vez não pergunta ao Fracttal
    html = logado.get("/t/campo/pt/PT-1").get_data(as_text=True)
    assert 'id="cn-ass-tec"' in html and "/os/_nexus/pt/PT-1/assinatura-tecnico" in html


# ── aprovação da PT no Nexus ─────────────────────────────────────────────────────────────────────────────────────
def _jwt(exp_s=3600):
    corpo = base64.urlsafe_b64encode(json.dumps({"email": "sup@exemplo.test", "exp": time.time() + exp_s}).encode())
    return "x." + corpo.decode().rstrip("=") + ".y"


def _entrar_no_fracttal(app, cliente, jwt):
    """O cookie do OS Creator, como o login do Fracttal dele grava."""
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"email": "sup@exemplo.test", "nome": "Supervisor Teste"}})
    cliente.set_cookie("os_sessao", valor, path="/os")


def test_tela_de_aprovar_mostra_a_pt_inteira(banco, logado):
    html = logado.get("/t/campo/pt/PT-1").get_data(as_text=True)
    assert ">PT-1 <" in html and "Troca de string" in html and "Técnico Silva" in html and "Eletricidade" in html
    assert 'action="/os/_nexus/pt/PT-1/decidir"' in html and "De acordo" in html and "Não autorizo" in html
    assert "O App ainda não lê esta decisão" in html
    # já decidida no App: sem botões
    html = logado.get("/t/campo/pt/PT-3").get_data(as_text=True)
    assert "/decidir" not in html and "De acordo" in html
    assert "não está no livro do App" in logado.get("/t/campo/pt/PT-9").get_data(as_text=True)


def test_quem_assina_vem_do_login_do_fracttal_do_os_creator(app, banco, logado):
    assert logado.get("/os/_nexus/quem").get_json()["email"] == ""
    _entrar_no_fracttal(app, logado, _jwt())
    assert logado.get("/os/_nexus/quem").get_json() == {"email": "sup@exemplo.test", "nome": "Supervisor Teste"}
    _entrar_no_fracttal(app, logado, _jwt(-60))                         # token do Fracttal vencido: não assina
    assert logado.get("/os/_nexus/quem").get_json()["email"] == ""


def test_sem_login_do_fracttal_vai_ao_login_e_volta_para_a_pt(banco, logado):
    r = logado.post("/os/_nexus/pt/PT-1/decidir", data={"decisao": "de_acordo"})
    assert r.status_code == 302 and r.headers["Location"].startswith("/os/login?next=%2Fos%2F_nexus%2Fpt%2FPT-1%2Fvoltar")
    assert logado.get("/os/_nexus/pt/PT-1/voltar").headers["Location"].endswith("/t/campo/pt/PT-1")
    assert "nexus_pt_decisoes" not in banco.workbooks


def test_decisao_gravada_no_banco_com_codigo_e_sem_nome(app, banco, logado):
    _entrar_no_fracttal(app, logado, _jwt())
    r = logado.post("/os/_nexus/pt/PT-1/decidir", data={"decisao": "negada", "motivo": "ok"})
    assert r.headers["Location"].endswith("/t/campo/pt/PT-1")          # "ok" não serve de motivo para negar
    assert "Escreva o motivo" in logado.get("/t/campo/pt/PT-1").get_data(as_text=True)
    r = logado.post("/os/_nexus/pt/PT-1/decidir",
                    data={"decisao": "negada", "motivo": "Sem bloqueio; ligar para fulano@exemplo.test ou 11 99999-0000"})
    assert r.headers["Location"].endswith("?gravada=1")
    linhas = banco.linhas("nexus_pt_decisoes", "decisoes")
    assert len(linhas) == 1
    d = linhas[0]
    assert d["pt"] == "PT-1" and d["decisao"] == "negada" and str(d["usina_id"]) == "1"
    assert d["decidida_por_hmac"] == codigo_da_pessoa(CHAVE, "sup@exemplo.test")
    assert "exemplo.test" not in json.dumps(d, default=str) and "99999" not in d["motivo"]
    html = logado.get("/t/campo/pt/PT-1").get_data(as_text=True)
    assert "no Nexus" in html and "/decidir" not in html               # decidida aqui: sem botões
    # o primeiro que decide vale
    logado.post("/os/_nexus/pt/PT-1/decidir", data={"decisao": "de_acordo"})
    assert "já tem decisão gravada pelo Nexus" in logado.get("/t/campo/pt/PT-1").get_data(as_text=True)
    assert len(banco.linhas("nexus_pt_decisoes", "decisoes")) == 1
    assert decisao_pt.da_pt("PT-1")["decisao"] == "negada"


def test_pt_ja_decidida_no_app_nao_recebe_decisao_e_outro_site_nao_decide(app, banco, logado):
    _entrar_no_fracttal(app, logado, _jwt())
    logado.post("/os/_nexus/pt/PT-3/decidir", data={"decisao": "de_acordo"})
    assert "já foi decidida no App" in logado.get("/t/campo/pt/PT-3").get_data(as_text=True)
    r = logado.post("/os/_nexus/pt/PT-2/decidir", data={"decisao": "de_acordo"},
                    headers={"Origin": "https://outro.site.test"})
    assert r.status_code == 403
    assert "nexus_pt_decisoes" not in banco.workbooks


def test_indicadores_da_ronda_filtram_a_tabela(banco, logado):
    """Levi, 05/10: "quero que esses botões sejam clicáveis e filtre a tabela"."""
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert html.count('class="cn-kpi cn-kpi--link"') == 6
    assert 'href="?ind=qualidade"' in html and 'href="?aba=cobertura&amp;cob=sem"' in html and 'href="?dur=curta"' in html
    html = logado.get("/t/campo/rondas?ind=hoje").get_data(as_text=True)
    assert "Só as de hoje" in html and "Nenhuma ronda com esses filtros" in html     # nenhuma ronda hoje no banco falso
    html = logado.get("/t/campo/rondas?ind=qualidade").get_data(as_text=True)
    assert "Qualidade abaixo de 85%" in html and "Nenhuma ronda com esses filtros" in html   # todas com 90%
    html = logado.get("/t/campo/rondas?aba=cobertura&cob=sem").get_data(as_text=True)
    assert "Coração 1" in html and "Brodowski 1" not in html and 'aria-current="true"' in html
    html = logado.get("/t/campo/rondas?aba=cobertura&cob=atrasadas").get_data(as_text=True)
    assert "Coração 1" in html and "<td>Altair</td>" not in html
    html = logado.get("/t/campo/rondas?ind=duracao").get_data(as_text=True)
    assert "Da mais longa para a mais curta" in html


def test_motivo_de_ronda_sem_os_fala_do_tecnico():
    """Levi, 05/10: "não entendi essa observação, minha conta fracttal já está conectada"."""
    m = visao.motivo_sem_os("Não criada — Fracttal: Conecte sua conta Fracttal (Conectar conta Fracttal)")
    assert m == "OS não criada: o técnico não tinha conectado a conta Fracttal dele no App"
    assert "sessão vencida" in visao.motivo_sem_os("Não criada — Fracttal: Sessão Fracttal expirada — reconecte sua conta")
    assert "(Isake Costa)" in visao.motivo_sem_os("Não criada — responsável não resolvido no Fracttal para 'Isake Costa'")


def test_quem_ronda_por_cluster_com_pendentes_por_pessoa(banco):
    """Levi, 05/10: Quem ronda por cluster; clicando, as mesmas informações por pessoa, com as usinas pendentes de ronda.
    O cluster vem do cadastro com uma grafia só (SP Norte e SP NORTE são o mesmo)."""
    d = visao.rondas().dados
    cl = {c["cluster"]: c for c in visao.painel_rondas(d["todas"], d["cobertura"], 14, d["hoje"])["clusters"]}
    assert set(cl) == {"SP Norte", "SC Oeste"}
    sp, sc = cl["SP Norte"], cl["SC Oeste"]
    # Altair: ronda há 1 dia, mas a longa pendente; Brodowski: há 2 dias, em dia; Coração 1: nunca teve ronda
    assert (sp["usinas"], sp["pendentes"], sp["rondas"], sp["longas"], sp["usinas_rondadas"]) == (2, 1, 3, 0, 2)
    assert (sc["usinas"], sc["pendentes"], sc["rondas"], sc["tecnicos"]) == (1, 1, 0, 0)
    assert sp["equipes"] == ["SP Norte 01"] and sp["tecnicos"] == 1
    p = sp["pessoas"][0]
    assert (p["tecnico"], p["equipe"], p["rondas"], p["pendentes"]) == ("Fulano Souza", "SP Norte 01", 3, 1)
    assert visao.nome_cluster("rn  OESTE") == "RN Oeste" and visao.nome_cluster(None) == visao.SEM_CLUSTER


def test_filtro_por_cliente_conta_a_cobertura_pelas_usinas_do_cadastro(banco, logado):
    """Levi, 05/10: filtro por cliente e a cobertura das rondas das UFVs do cliente, com as mesmas usinas do registro
    mestre (o cadastro): Thopen tem Altair e Brodowski 1 mobilizadas, as duas com ronda."""
    cob = {c["usina"]: c["cliente"] for c in visao.rondas().dados["cobertura"]}
    assert cob == {"Altair": "Thopen", "Brodowski 1": "Thopen", "Coração 1": "Outro Cliente"}
    html = logado.get("/t/campo/rondas?cliente=Thopen").get_data(as_text=True)
    assert "cobertura das rondas: <b class=\"cn-t-ok\">100%</b>" in html
    assert "2 de 2 usinas mobilizadas do cliente" in html
    outro = logado.get("/t/campo/rondas?cliente=Outro+Cliente").get_data(as_text=True)
    assert "0 de 1 usinas mobilizadas do cliente" in outro


def test_historico_de_rondas_da_usina_com_sujidade_e_vegetacao(banco, logado):
    """Levi, 05/10: clicar no nome da usina abre o histórico de rondas com data, sujidade e vegetação."""
    d = visao.rondas().dados
    resp = {"500": {"sujidade": 4, "vegetacao": 2, "vala": "limpa", "sensores_sujos": ["piranômetro"]}}
    h = visao.historico_usina(d["todas"], resp, 1)
    assert [r["data"] for r in h] == [_dia(1), _dia(3)]                 # a mais recente primeiro
    assert (h[0]["sujidade"], h[0]["vegetacao"], h[0]["lida"]) == (4, 2, True)
    assert visao.historico_usina(d["todas"], {}, 3) == []               # Coração 1 nunca teve ronda
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert '/t/campo/rondas/usina/1"' in html                           # o nome da usina é o link do histórico
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert "Histórico de rondas" in pag and "Altair" in pag and "Thopen" in pag and "SP Norte" in pag
    assert pag.count('class="cn-pessoa"') == 2
    vazia = logado.get("/t/campo/rondas/usina/3").get_data(as_text=True)
    assert "Nenhuma ronda pelo App nos últimos 90 dias" in vazia and "Coração 1" in vazia


def test_grafico_do_historico_diz_os_quem_fez_e_quando(banco, logado, monkeypatch):
    """Levi, 06/10: no gráfico de evolução, passar o mouse no ponto mostra a OS, quem fez e o dia com a hora."""
    from nexus.campo import ronda_checklist
    monkeypatch.setattr(ronda_checklist, "respostas", lambda: {"500": {"sujidade": 4, "vegetacao": 2}})
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert pag.count('class="cn-ponto"') == 2 and 'class="cn-dica"' in pag
    d1 = _dia(1)
    assert f'data-quando="{d1[8:10]}/{d1[5:7]}/{d1[:4]} às 07:00 (até 08:00)"' in pag
    assert 'data-os="500"' in pag and 'data-tec="Fulano Souza"' in pag and 'data-suj="4"' in pag


def test_ronda_sem_os_mostra_o_checklist_da_carga_unica(banco, logado):
    """06/10: a ronda sem OS (Brodowski, há 2 dias) tem as respostas no nexus_rondas_checklist; o histórico mostra."""
    _aba(banco, "nexus_rondas_checklist", "fato_checklist_ronda", [
        {"ronda_id": "x", "data_id": 1, "usina_id": 2, "inicio": f"{_dia(2)}T10:00:00.000Z", "sujidade": 3,
         "vegetacao": 5, "vala": "Obstruída", "ipoa_sujo": 1, "ghi_sujo": None, "albedo_sujo": 0}])
    visao.limpar()
    d = visao.rondas().dados
    h = visao.historico_usina(d["todas"], {}, 2)
    assert (h[0]["sujidade"], h[0]["vegetacao"], h[0]["vala"], h[0]["sensores_sujos"], h[0]["lida"]) ==         (3, 5, "Obstruída", ["IPOA"], True)
    assert visao.historico_usina(d["todas"], {}, 1)[0]["lida"] is False     # a com OS segue pelo texto da OS
    s = visao.sujidade_vegetacao(d["todas"], d["cobertura"], {}, 30, d["hoje"])
    assert [x["usina"] for x in s["linhas"]] == ["Brodowski 1"] and s["linhas"][0]["vegetacao"] == 5
    pag = logado.get("/t/campo/rondas/usina/2").get_data(as_text=True)
    assert 'cn-nivel cn-nivel--5">5<' in pag and "não lida" not in pag


def test_eixo_de_datas_do_grafico_nao_encavala(banco, logado, monkeypatch):
    """06/10 (Crateús): com muitas rondas a data do eixo vai em meia fonte e, sem espaço, uma a cada tantos pontos;
    a última sempre aparece."""
    from nexus.campo import ronda_checklist
    base = visao.rondas().dados["todas"][0]
    muitas = [dict(base, data=_dia(i), sujidade=3, vegetacao=2, lida=True, os=str(900 + i), sensores_sujos=[], vala="")
              for i in range(80)]
    monkeypatch.setattr(visao, "historico_usina", lambda todas, resp, uid: muitas)
    monkeypatch.setattr(ronda_checklist, "pedir_releitura", lambda app=None: None)
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    datas = pag.count('class="eixo data"')
    assert 20 <= datas <= 32 and pag.count('class="cn-ponto"') == 80      # 80 pontos, ~30 datas
    assert f'class="eixo data" text-anchor="middle">{_dia(0)[8:10]}/{_dia(0)[5:7]}<' in pag     # a mais recente
