"""A camada de dados do Nexus (método Kimball, 05/10/2026): catálogo, calendário, histórico, fatos com IDs, a carga que
grava e confere, e a tela Base → Governança de dados."""
from datetime import date, datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.dados import calendario, carga, catalogo, fatos, historico, livros
from nexus.dados import telas as telas_dados

BASE = "http://pg.falso"
BRT = timezone(timedelta(hours=-3))


# ── catálogo ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_catalogo_declara_grao_e_todas_as_dimensoes():
    ids = [f.id for f in catalogo.FATOS]
    assert len(ids) == len(set(ids))
    for f in catalogo.FATOS:
        assert f.grao.startswith("1 linha"), f.id
        assert set(f.dims) == set(catalogo.DIM_IDS), f.id
        assert all(e in catalogo.ESTADOS for e, _ in f.dims.values()), f.id
        assert f.estado in ("origem", "conformado", "aposentado", "fora"), f.id
        assert (f.estado == "conformado") == bool(f.conformado_em), f.id
    assert catalogo.resumo()["conformados"] >= 1


# ── calendário ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_pascoa_e_os_feriados_moveis():
    assert [calendario._pascoa(a) for a in (2025, 2026, 2027)] == [date(2025, 4, 20), date(2026, 4, 5), date(2027, 3, 28)]
    n = calendario.nacionais_calculados(2026)
    assert n[date(2026, 2, 17)] == "Carnaval" and n[date(2026, 4, 3)] == "Paixão de Cristo" and len(n) == 12


def test_dia_util_semana_e_fonte_do_feriado():
    pcm = {"gerais": [{"tipo": "NACIONAL", "estado": "TODOS", "data": {"$dt": "2026-11-20T00:00:00"},
                       "feriado": "Dia da Consciência Negra"},
                      {"tipo": "ESTADUAL", "estado": "SP", "data": {"$dt": "2026-07-09T00:00:00"}, "feriado": "Rev."}],
           "municipais": [{"tipo": "MUNICIPAL", "estado": "MA", "municipio": "MATÕES",
                           "data": {"$dt": "2026-01-20T00:00:00"}, "feriado": "Feriado Municipal"}]}
    nac, locais = calendario.feriados(pcm)
    assert list(nac) == [date(2026, 11, 20)] and [l[2] for l in locais] == ["MUNICIPAL", "ESTADUAL"]
    d = {l[1]: dict(zip(calendario.CAB_DIA, l)) for l in calendario.dias(nac)}
    assert d["2026-11-20"]["dia_util"] == "não" and d["2026-11-20"]["feriado_fonte"] == "PCM"
    assert d["2026-07-09"]["dia_util"] == "sim"                     # estadual não tira o dia útil de todo mundo
    assert d["2026-12-25"]["feriado_nacional"] is None              # 2026 é do PCM: só o que ele cadastrou
    assert d["2025-12-25"]["feriado_fonte"] == "calculado" and d["2025-12-25"]["dia_util"] == "não"
    assert d["2026-10-05"]["semana_iso"] == "2026-W41" and d["2026-10-04"]["fim_de_semana"] == "sim"
    assert d["2026-10-05"]["data_id"] == 20261005


# ── histórico (válido de / até) ───────────────────────────────────────────────────────────────────────────────────
def _p(pid, equipe, sup, **kw):
    d = {"pessoa_id": pid, "equipe_id": equipe, "supervisor_id": sup, "cargo": "Técnico", "vinculo": "CLT",
         "status": "Ativo", "alterado_em": "2026-09-30T10:00:00", "excluido": "não"}
    d.update(kw)
    return d


def _dic(entidade, linhas):
    return [dict(zip(historico.cabecalho(entidade), l)) for l in linhas]


def test_historico_abre_fecha_e_nao_confunde_tipo():
    h1 = historico.atualizar("pessoas", [_p(1, 10, 100), _p(2, 20, 200)], [], "2026-10-05")
    assert [(l[0], l[-3], l[-1]) for l in h1] == [(1, "2026-09-30", "sim"), (2, "2026-09-30", "sim")]
    # mesma coisa com outro tipo (12.0, "12"): não é mudança
    h2 = historico.atualizar("pessoas", [_p(1, 10.0, "100"), _p(2, 20, 200)], _dic("pessoas", h1), "2026-10-06")
    assert h2 == h1
    # a pessoa 1 muda de supervisor; a 2 sai do cadastro
    h3 = historico.atualizar("pessoas", [_p(1, 10, 101)], _dic("pessoas", h2), "2026-10-07")
    d = [dict(zip(historico.cabecalho("pessoas"), l)) for l in h3]
    um = [x for x in d if x["pessoa_id"] == 1]
    assert [(x["supervisor_id"], x["valido_de"], x["valido_ate"], x["vigente"]) for x in um] == [
        (100, "2026-09-30", "2026-10-07", "não"), (101, "2026-10-07", None, "sim")]
    assert [(x["valido_ate"], x["vigente"]) for x in d if x["pessoa_id"] == 2] == [("2026-10-07", "não")]


# ── fatos com IDs ─────────────────────────────────────────────────────────────────────────────────────────────────
USINAS = [{"usina_id": 7, "codigo": "THPN-PRM200", "nome": "Primavera 2"},
          {"usina_id": 8, "codigo": "MAB100", "nome": "Mabel 1"}, {"usina_id": 9, "codigo": "ATHN-MAB100"}]
DE_PARA = [{"usina_id": 3, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Ipixuna 1 e 2 - PA"}]
EQUIPES = [{"equipe_id": 41, "nome": "PR Oeste 01"}]


def _fech(**kw):
    d = {"Registrado em": "2026-10-01T02:30:00.000Z", "OS": "15377", "ID da OS no Fracttal": "153770",
         "Tarefa": "Inspeção", "Código do ativo": "THPN-PRM200-PGINVR1", "Usina": "Thopen · Thopen - Ipixuna 1 e 2 - PA",
         "Região": "PR Oeste 01", "Tipo da OS": "Preventiva", "Criticidade": "Alta", "Técnico (HMAC)": "abc",
         "Nota do painel": 72, "Pontual": "sim", "Devolvida": None, "Fotos": 3, "Observação no App": "texto com nome"}
    d.update(kw)
    return d


def _lig():
    return fatos.Ligador(USINAS, DE_PARA, EQUIPES, {"abc": 55})


def test_liga_usina_pelo_de_para_e_pelo_codigo_so_quando_unico():
    lig = _lig()
    assert lig.usina("Thopen · Thopen - Ipixuna 1 e 2 - PA", "") == (3, "de-para do Fracttal")
    assert lig.usina("Thopen · nome que não casa", "THPN-PRM200-TRFR1") == (7, "código do ativo")
    assert lig.usina("x", "MAB100-INVR2.4") == (None, None)         # MAB100 é de duas usinas: não chuta
    assert lig.equipe("pr  oeste 01") == 41 and lig.pessoa("abc;def") == 55 and lig.pessoa("zzz") is None


def test_fato_fechamento_leva_ids_dia_de_brasilia_e_nada_de_texto_livre():
    f = dict(zip(fatos.CAB_FECHAMENTO, fatos.fato_fechamento([_fech()], _lig())[0]))
    assert (f["data_id"], f["usina_id"], f["equipe_id"], f["pessoa_id"]) == (20260930, 3, 41, 55)
    assert f["nota"] == 72 and f["pontual"] == 1 and f["devolvida"] == 0 and f["usina_ligada_por"] == "de-para do Fracttal"
    assert "texto com nome" not in [str(v) for v in f.values()]


def test_checklist_da_ronda_sem_os_liga_pela_data_e_inicio_e_nao_chuta():
    """Carga única de 06/10: a ronda sem OS ganha as respostas do registro dela no App, casando dia + início; ronda sem
    registro único fica fora; o e-mail só vira pessoa_id; sensor "Não se aplica" e vala fora da lista = vazio."""
    import json
    livro = [{"Data": "2026-09-30", "Usina": "Thopen - Ipixuna 1 e 2 - PA", "Ativo da usina no Fracttal": "",
              "Região": "PR Oeste 01", "Tipo": "longa", "Início": "2026-10-01T01:30:00.000Z", "Fim": "2026-10-01T02:30:00.000Z"},
             {"Data": "2026-09-29", "Usina": "Thopen - Ipixuna 1 e 2 - PA", "Início": "2026-09-29T12:00:00.000Z"}]
    resp = {"sujidade": "4", "vegetacao": "9", "vala": "Não se aplica", "pir_ipoa": "Sujo", "pir_ghi": "Limpo",
            "pir_albedo": "Não se aplica", "observacao": "texto com nome"}
    regs = {("2026-09-30", "2026-10-01T01:30:00.000Z"): {"email": "Tec@Exemplo.test", "respostas": json.dumps(resp)}}
    linhas, origem = fatos.fato_checklist_ronda(livro, regs, _lig(), lambda e: "abc" if e == "tec@exemplo.test" else "")
    assert len(linhas) == 1 and origem == livro[:1]
    f = dict(zip(fatos.CAB_CHECKLIST_RONDA, linhas[0]))
    assert (f["data_id"], f["usina_id"], f["equipe_id"], f["pessoa_id"]) == (20260930, 3, 41, 55)   # dia de Brasília
    assert (f["sujidade"], f["vegetacao"], f["vala"]) == (4, None, None)          # 9 não é nível; N/A não é vala
    assert (f["ipoa_sujo"], f["ghi_sujo"], f["albedo_sujo"]) == (1, 0, None)
    assert not any("exemplo" in str(v).lower() or "texto com nome" in str(v) for v in f.values())
    assert any(x.id == "ronda_checklist" and x.estado == "conformado" for x in catalogo.FATOS)


def test_qualidade_conta_e_mostra_o_que_faltou():
    origem = [_fech(), _fech(Usina="Nobreak 1", **{"Código do ativo": "SPDA", "Região": "MT Sul 02"})]
    linhas = fatos.fato_fechamento(origem, _lig())
    q = dict(zip(fatos.CAB_QUALIDADE, fatos.qualidade("fechamento", "x", linhas, fatos.CAB_FECHAMENTO, origem, None, "t")))
    assert (q["linhas"], q["com_usina"], q["pct_usina"], q["pct_equipe"]) == (2, 1, 50, 50)
    assert "Nobreak 1 (1)" in q["sem_usina_exemplos"] and "MT Sul 02 (1)" in q["sem_equipe_exemplos"]


# ── a carga: grava, confere e não grava em dobro ──────────────────────────────────────────────────────────────────
def _aba(api, livro, aba, linhas):
    if not linhas:
        api._id(livro, aba)["linhas"] = []
        return
    cab = list(linhas[0])
    api._id(livro, aba)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]


@pytest.fixture
def banco(tmp_path):
    api = ApiPGFalsa()
    api.workbooks.update({"cadastro_nexus": {}, "fechamentos_app_campo": {}})
    _aba(api, "cadastro_nexus", "usinas", USINAS)
    _aba(api, "cadastro_nexus", "equipes", EQUIPES)
    _aba(api, "cadastro_nexus", "pessoas", [_p(1, 41, 100)])
    _aba(api, "cadastro_nexus", "de_para", DE_PARA)
    _aba(api, "fechamentos_app_campo", "Fechamentos", [_fech(), _fech(OS="15378", Tarefa="Outra")])
    cfg = {"GRIDCO_DB_API": BASE, "GRIDCO_SQL_TOKEN": "t", "TESTING": True, "NEXUS_PCM_TRABALHO": str(tmp_path)}
    return api, cfg


def test_carga_grava_os_dois_livros_e_confere(banco):
    api, cfg = banco
    agora = datetime(2026, 10, 5, 15, 40, tzinfo=BRT)
    r = carga.rodar(cfg, api, agora=agora)
    assert r["gravado"]["nexus_fatos"]["fato_fechamento"] == 2 and r["pct_usina"] == 100
    assert r["gravado"]["nexus_dimensoes"]["dim_data"] == (calendario.FIM - calendario.INICIO).days + 1
    f = livros.ler(BASE, api, "nexus_fatos", "fato_fechamento")
    assert {x["usina_id"] for x in f} == {3} and {x["data_id"] for x in f} == {20260930}
    h = livros.ler(BASE, api, "nexus_dimensoes", "pessoas_historico")
    assert [(x["pessoa_id"], x["vigente"]) for x in h] == [(1, "sim")]
    # outra máquina 10 min depois: pula, não grava em dobro
    assert "pulou" in carga.rodar(cfg, api, agora=agora + timedelta(minutes=10))


def test_carga_seguinte_registra_a_mudanca_de_supervisor(banco):
    api, cfg = banco
    carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 15, 40, tzinfo=BRT))
    _aba(api, "cadastro_nexus", "pessoas", [_p(1, 41, 101)])
    carga.rodar(cfg, api, agora=datetime(2026, 10, 6, 15, 40, tzinfo=BRT))
    h = livros.ler(BASE, api, "nexus_dimensoes", "pessoas_historico")
    assert [(x["supervisor_id"], x["valido_ate"], x["vigente"]) for x in h] == [
        (100, "2026-10-06", "não"), (101, None, "sim")]


def test_sem_token_monta_e_nao_grava(banco):
    api, cfg = banco
    cfg.pop("GRIDCO_SQL_TOKEN")
    r = carga.rodar(cfg, api, forcar=True)
    assert "erro" in r and "nexus_fatos" not in api.workbooks


def test_gravacao_que_perde_linha_vira_erro(banco):
    api, cfg = banco
    api.perder = 1
    with pytest.raises(livros.GravacaoErro):
        carga.rodar(cfg, api, forcar=True)


# ── a tela ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_tela_mostra_a_matriz_e_a_qualidade(app, banco):
    api, cfg = banco
    carga.rodar(cfg, api, forcar=True)
    app.config["GRIDCO_DB_API"] = BASE
    app.extensions["nexus_dados_sessao"] = api
    telas_dados._CACHE.update(t=0.0, v=None)
    c = app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["admin"] = "admin", True
    from conftest import SENHA_TESTE
    c.post("/entrar", data={"senha": SENHA_TESTE})
    html = c.get("/t/base/governanca").get_data(as_text=True)
    telas_dados._CACHE.update(t=0.0, v=None)
    assert "Matriz de barramento" in html and "Fechamento de OS" in html and "com IDs" in html
    assert "100% ligado" in html and "Programação semanal" in html


def test_git_ignora_so_a_pasta_de_dado_real_da_raiz():
    """05/10/2026: o `.gitignore` tinha `dados/`, que barrava QUALQUER pasta com esse nome; a camada de dados
    (`nexus/dados/`) e o template dela não iam para o commit, calados. A regra é só a pasta da raiz (`/dados/`)."""
    import subprocess
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent

    def ignorado(p):
        return subprocess.run(["git", "check-ignore", "-q", p], cwd=raiz).returncode == 0
    assert ignorado("dados/pcm/insumos.json") and ignorado("dados/cadastro_ensaio.json")
    assert not ignorado("nexus/dados/catalogo.py") and not ignorado("nexus/templates/dados/governanca.html")
