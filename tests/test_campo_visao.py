"""A visão do Nexus para o Campo · App (05/10/2026): Rondas, PT, Zeladoria, Ranking, Central de atenção e a aprovação da
PT, pelos livros que o App grava no banco e pelo cadastro do Nexus. Banco falso (pg_falso), datas relativas a hoje."""
import base64
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.campo import decisao_pt, visao
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
           "data_mobilizacao": _MOB, "uf": "SP", "cidade": "Altair"},
          {"usina_id": 2, "nome": "Brodowski 1", "codigo": "THPN-BWK100", "status": "OPERAÇÃO", "equipe_id": 10,
           "data_mobilizacao": _MOB, "uf": "SP", "cidade": "Brodowski"},
          {"usina_id": 3, "nome": "Coração 1", "codigo": "THPN-COR100", "status": "OPERAÇÃO", "equipe_id": 20,
           "data_mobilizacao": _MOB, "uf": "SC", "cidade": "Coração"},
          {"usina_id": 4, "nome": "Nova", "codigo": "THPN-NOV100", "status": "A MOBILIZAR", "equipe_id": 20,
           "uf": "SC", "cidade": "Nova"},
          # em OPERAÇÃO no cadastro, mas sem data de mobilização: não é usina mobilizada (Levi, 05/10)
          {"usina_id": 5, "nome": "Sem Data", "codigo": "THPN-SDT100", "status": "OPERAÇÃO", "equipe_id": 20,
           "uf": "SC", "cidade": "Sem Data"}]
EQUIPES = [{"equipe_id": 10, "nome": "SP Norte 01"}, {"equipe_id": 20, "nome": "SC Oeste 01"}]
DE_PARA = [{"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Altair 1 - SP"}]


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
    ident.write_text(json.dumps({"porEmail": {"tec1@exemplo.test": {"nome": "Técnico Um da Silva"}}}), encoding="utf-8")
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_PESSOA_HMAC=CHAVE, NEXUS_CAMPO_IDENTIDADES=str(ident),
                      GRIDCO_SQL_TOKEN="token-de-teste")
    app.extensions["nexus_dados_sessao"] = api
    visao.limpar()
    with app.app_context():
        yield api
    visao.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def test_so_usina_mobilizada_entra_e_com_estado_e_cidade(banco):
    d = visao.rondas(14).dados
    cob = {c["usina"]: c for c in d["cobertura"]}
    assert set(cob) == {"Altair", "Brodowski 1", "Coração 1"}      # a mobilizar e a sem data de mobilização ficam fora
    assert d["sem_mobilizacao"] == ["Sem Data"]
    assert (cob["Altair"]["uf"], cob["Altair"]["cidade"]) == ("SP", "Altair")
    assert cob["Altair"]["dias"] == 1 and cob["Brodowski 1"]["dias"] == 2 and cob["Coração 1"]["dias"] == 999
    assert d["cobertura"][0]["usina"] == "Coração 1"                    # a mais tempo sem ronda primeiro
    assert d["resumo"]["sem_os"] == 1 and d["resumo"]["cobertas"] == 2
    assert d["periodo"][0]["tecnico"] == "Fulano Souza"               # nome resumido: o "Nome padrão" do cadastro


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
    assert "PT-1" in logado.get("/t/campo/pt").get_data(as_text=True)
    assert "SP Norte 01" in logado.get("/t/campo/ranking").get_data(as_text=True)


def test_central_separa_ronda_de_pt_e_sem_hashtag_na_os(banco, logado):
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert "Rondas pendentes" in html and "Rondas feitas" in html and "Permissões de trabalho" in html
    assert "Nunca teve ronda" in html and "Coração" in html and "<th>Estado</th><th>Cidade</th>" in html
    assert "Região" not in html and "<th>O quê</th>" not in html and "<th>Quem</th>" not in html
    html = logado.get("/t/campo/atencao?vista=feitas").get_data(as_text=True)
    assert "<th>Feito por</th>" in html and "Fulano Souza" in html and "#500" not in html and ">500<" in html
    assert "<th>Observação</th>" in html and "Sem OS no Fracttal" in html
    html = logado.get("/t/campo/atencao?vista=pt").get_data(as_text=True)
    assert 'class="cn-link" href="/t/campo/pt/PT-1"' in html and "Técnico Silva" in html
    assert "Ronda longa pendente" not in html                          # na visão de PT, só status de PT
    html = logado.get("/t/campo/atencao?vista=pt&f=parada").get_data(as_text=True)
    assert "/t/campo/pt/PT-1" in html and "/t/campo/pt/PT-2" not in html


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
