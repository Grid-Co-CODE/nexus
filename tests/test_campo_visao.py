"""A visão do Nexus para o Campo · App (05/10/2026): Rondas, PT, Zeladoria, Ranking e Central de atenção pelos livros
que o App grava no banco e pelo cadastro do Nexus. Banco falso (pg_falso), datas relativas a hoje."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.campo import visao
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


USINAS = [{"usina_id": 1, "nome": "Altair", "codigo": "THPN-ALT100", "status": "OPERAÇÃO", "equipe_id": 10},
          {"usina_id": 2, "nome": "Brodowski 1", "codigo": "THPN-BWK100", "status": "OPERAÇÃO", "equipe_id": 10},
          {"usina_id": 3, "nome": "Coração 1", "codigo": "THPN-COR100", "status": "OPERAÇÃO", "equipe_id": 20},
          {"usina_id": 4, "nome": "Nova", "codigo": "THPN-NOV100", "status": "A MOBILIZAR", "equipe_id": 20}]
EQUIPES = [{"equipe_id": 10, "nome": "SP Norte 01"}, {"equipe_id": 20, "nome": "SC Oeste 01"}]
DE_PARA = [{"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Altair 1 - SP"}]


def _ronda(dia, usina="Thopen - Altair 1 - SP", ativo="THPN-ALT100", **kw):
    d = {"Data": dia, "OS": "500", "Usina": usina, "Ativo da usina no Fracttal": ativo, "ID da OS no Fracttal": "5000",
         "Região": "SP Norte 01", "Técnico": "Técnico Um", "Tipo": "curta", "Situação da OS": "Criada",
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
            "Motivo": None, "Efeito": None, "Respostas NÃO": 2, "Faltam": None, "Atividades": "Eletricidade",
            "Forçada": None}


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
    _aba(api, "cadastro_nexus", "de_para", DE_PARA)
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
    ident.write_text(json.dumps({"porEmail": {"tec1@exemplo.test": {"nome": "Técnico Um"}}}), encoding="utf-8")
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_PESSOA_HMAC=CHAVE, NEXUS_CAMPO_IDENTIDADES=str(ident))
    app.extensions["nexus_dados_sessao"] = api
    visao.limpar()
    with app.app_context():
        yield api
    visao.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def test_rondas_cobertura_pelas_usinas_em_operacao(banco):
    d = visao.rondas(14).dados
    cob = {c["usina"]: c for c in d["cobertura"]}
    assert set(cob) == {"Altair", "Brodowski 1", "Coração 1"}           # a usina a mobilizar não conta
    assert cob["Altair"]["dias"] == 1 and cob["Brodowski 1"]["dias"] == 2 and cob["Coração 1"]["dias"] == 999
    assert d["cobertura"][0]["usina"] == "Coração 1"                    # a mais tempo sem ronda primeiro
    assert d["resumo"]["sem_os"] == 1 and d["resumo"]["nao_ligadas"] == 0 and d["resumo"]["cobertas"] == 2


def test_pt_fila_da_mais_antiga_e_espera_ate_a_decisao(banco):
    d = visao.pts().dados
    assert [p["numero"] for p in d["aguardando"]] == ["PT-1", "PT-2"]
    assert d["resumo"]["paradas"] == 1 and d["aguardando"][0]["solicitante"] == "Técnico Um"
    assert d["historico"][0]["espera_min"] == 60


def test_ranking_so_pontua_quem_tem_nota_e_cobertura(banco):
    d = visao.ranking(30).dados
    reg = {a["nome"]: a for a in d["regioes"]}
    assert reg["SP Norte 01"]["nota"] == 80 and reg["SP Norte 01"]["cobertura_pct"] == 100
    assert reg["SP Norte 01"]["pontos"] == round(0.6 * 80 + 0.4 * 100)
    assert reg["SC Oeste 01"]["pontos"] is None                        # sem fechamento: não ganha 100 pela cobertura
    assert [a["nome"] for a in d["fora_do_cadastro"]] == ["Grid Co."]
    assert d["colaboradores"][0]["nome"] == "Técnico Um" and d["colaboradores"][0]["os"] == 3


def test_atencao_junta_as_fontes_sem_repetir_a_ronda_longa(banco):
    d = visao.atencao(14).dados
    tipos = d["por_tipo"]
    assert tipos.get("sem_ronda") == 1                                 # Coração 1, nunca
    assert tipos.get("pt_parada") == 1                                 # PT-1 (30 h); PT-2 tem 1 h
    assert tipos.get("ronda_sem_os") == 1
    assert tipos.get("longa_pendente") == 1                            # duas rondas da Altair, um ponto só
    assert tipos.get("ronda_incompleta") == 1 and "nota_baixa" not in tipos
    inc = next(p for p in d["pontos"] if p["tipo"] == "ronda_incompleta")
    assert inc["oque"] == "item sem foto de evidência"
    assert d["tratados"][0]["acao"] == "resolvida"


def test_zeladoria_vazia_diz_por_que(banco, logado):
    html = logado.get("/t/campo/zeladoria").get_data(as_text=True)
    assert "Nenhum registro de zeladoria pelo App ainda" in html


def test_telas_mostram_o_dado_do_banco(banco, logado):
    assert "Coração 1" in logado.get("/t/campo/rondas").get_data(as_text=True)
    assert "PT-1" in logado.get("/t/campo/pt").get_data(as_text=True)
    assert "SP Norte 01" in logado.get("/t/campo/ranking").get_data(as_text=True)
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert "Usina sem ronda" in html and "Tratados na Central do App" in html
