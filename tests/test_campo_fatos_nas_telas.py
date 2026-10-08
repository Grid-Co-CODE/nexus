"""As telas do Campo · App leem os FATOS (passo 4 do Kimball, Levi, 08/10/2026), o técnico das rondas pelo código
(passo 2, lado do Nexus) e a validação por foto (Levi, 08/10/2026). Banco falso (pg_falso), datas relativas a hoje.

- Rondas, Central de atenção e PT tiram a contagem e a ligação (usina_id, pessoa_id, data_id) do fato conformado
  (`nexus_fatos`); sem o fato no banco (ou com o do banco mais velho que o livro do App), a tela monta o fato na hora
  com a MESMA função da carga e diz isso, discretamente.
- O livro de rondas do App troca `Técnico` (nome em claro) por `Técnico (HMAC)` (código do e-mail): o Nexus aceita as
  duas colunas, inclusive misturadas no mesmo livro, e sem a chave diz que falta a chave.
- A validação por foto (`origem = "validacao_foto"` no livro da avulsa) não é ronda: fora do fato e das contas de ronda;
  entra só como a leitura de sujidade e vegetação da usina naquele dia, e vale no lugar da ronda do mesmo dia."""
import json
from datetime import datetime, timedelta, timezone

from pg_falso import Resposta
from test_campo_visao import CHAVE, CHAVE_CADASTRO, _aba, _dia, _ronda, banco  # noqa: F401  (fixture)

from nexus.cadastro.cifra import Cofre
from nexus.campo import aprovacao, fonte_pg, livros_app, ronda_checklist, visao
from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.dados import carga, fato_pt, fato_ronda, fatos, livros

BASE = "http://pg.falso"
CODIGO_TEC1 = codigo_da_pessoa(CHAVE, "tec1@exemplo.test")      # "Técnico Um da Silva" no identidades.json do teste


def _sem_fracttal(monkeypatch, respostas=None):
    monkeypatch.setattr(ronda_checklist, "respostas", lambda: respostas or {})
    monkeypatch.setattr(ronda_checklist, "pedir_releitura", lambda app=None: None)
    monkeypatch.setattr(ronda_checklist, "estado", lambda: {"lendo": False, "erro": "", "lidas": True, "fila": True})
    monkeypatch.setattr(aprovacao, "_pedir_releitura", lambda: None)


def _linhas_cruas(api, livro, aba, linhas):
    """Cada linha com o PRÓPRIO cabeçalho: um livro lido no meio do `sync-xlsx` pode misturar o cabeçalho velho e o
    novo (o `_aba` do teste usa o cabeçalho da 1ª linha para todas)."""
    api.workbooks[livro] = {}
    api._id(livro, aba)["linhas"] = [{"headers": list(l), "values": list(l.values())} for l in linhas]
    visao.limpar()


def _com_hora_dos_livros(api, quando: dict):
    """A API falsa passa a dizer quando cada livro foi gravado (`updated_at`), como a de verdade."""
    original = api.get

    def get(url, params=None, headers=None, timeout=None):
        if url.endswith("/api/workbooks"):
            chaves = set(api.workbooks) | {wb for wb, _a in api.abas}
            return Resposta(200, [{"key": k, "updated_at": quando.get(k)} for k in sorted(chaves)])
        return original(url, params=params, headers=headers, timeout=timeout)
    api.get = get


def _gravar_fato_ronda(app, api, origem_em, gerado_em, *, mexer=None, extra=None):
    """O `fato_ronda` no banco falso, montado pela MESMA função da carga, com a linha de qualidade que diz de qual
    versão do livro do App ele saiu. `mexer(linhas)` muda o fato gravado (para provar que a tela leu o do banco)."""
    def ler(livro, aba):
        return livros.ler(BASE, api, livro, aba)
    cad = {a: ler("cadastro_nexus", a) for a in ("usinas", "equipes", "de_para", "pessoas")}
    m = carga.mapas_das_linhas(app.config, cad["de_para"], cad["pessoas"])
    linhas = carga.montar_ronda(ler, carga.ligador(cad, m), m)[0]
    if mexer:
        mexer(linhas)
    api.workbooks["nexus_fatos"] = {}
    api._id("nexus_fatos", "fato_ronda")["linhas"] = [{"headers": fato_ronda.CAB_RONDA, "values": l} for l in linhas]
    q = {c: None for c in fatos.CAB_QUALIDADE}
    q.update(fato="ronda", linhas=len(linhas), origem_atualizada_em=origem_em, gerado_em=gerado_em,
             extra=json.dumps(extra or {}))
    api._id("nexus_fatos", "qualidade")["linhas"] = [{"headers": fatos.CAB_QUALIDADE,
                                                       "values": [q[c] for c in fatos.CAB_QUALIDADE]}]
    visao.limpar()


def _iso(horas_atras):
    return (datetime.now(timezone(timedelta(hours=-3))) - timedelta(hours=horas_atras)).isoformat()


# ── Passo 2 (lado do Nexus): o técnico das rondas pelo código ────────────────────────────────────────────────────
def test_rondas_aceitam_tecnico_pelo_nome_e_pelo_codigo_no_mesmo_livro(banco):  # noqa: F811
    velha = _ronda(_dia(1))                                          # "Técnico" = o nome em claro (até o App trocar)
    nova = {k: v for k, v in _ronda(_dia(3)).items() if k != "Técnico"}
    nova["Técnico (HMAC)"] = CODIGO_TEC1                              # o App novo: só o código, na 7ª coluna
    _linhas_cruas(banco, "rondas_app_campo", "OS de ronda", [velha, nova])
    d = visao.rondas().dados
    assert {r["data"]: r["tecnico"] for r in d["todas"]} == {_dia(1): "Fulano Souza", _dia(3): "Técnico Silva"}
    assert d["aviso_tecnico"] == ""
    # a fonte das regras copiadas (Triagem, fila da Aprovação) também
    assert livros_app.ronda(velha)["nome"] == "Fulano de Tal Souza"
    assert livros_app.ronda(nova, livros_app.pessoas_por_codigo(CHAVE))["nome"] == "Técnico Um da Silva"
    assert livros_app.ronda(nova)["nome"] == ""                       # sem a tradução: vazio, nunca o código


def test_fonte_das_regras_copiadas_traduz_o_codigo_da_ronda(app, banco):  # noqa: F811
    nova = {k: v for k, v in _ronda(_dia(1)).items() if k != "Técnico"}
    nova["Técnico (HMAC)"] = CODIGO_TEC1
    _linhas_cruas(banco, "rondas_app_campo", "OS de ronda", [nova, _ronda(_dia(2))])
    forn = fonte_pg.Fornecedor(app.config, sessao=banco)
    nomes = sorted(r["nome"] for r in forn("rondas").list_entities())
    assert nomes == ["Fulano de Tal Souza", "Técnico Um da Silva"]


def test_coluna_nova_sem_a_chave_nao_quebra_e_diz_que_falta_a_chave(app, banco, logado):  # noqa: F811
    nova = {k: v for k, v in _ronda(_dia(1)).items() if k != "Técnico"}
    nova["Técnico (HMAC)"] = CODIGO_TEC1
    _linhas_cruas(banco, "rondas_app_campo", "OS de ronda", [nova])
    app.config["NEXUS_PESSOA_HMAC"] = None
    visao.limpar()
    r = logado.get("/t/campo/rondas")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "não tem a chave NEXUS_PESSOA_HMAC: 1 ronda sem o nome do técnico" in html
    assert CODIGO_TEC1 not in html                                    # o código nunca vai para a tela
    assert visao.rondas().dados["todas"][0]["tecnico"] == ""


# ── Passo 4: as telas leem o fato ────────────────────────────────────────────────────────────────────────────────
def test_sem_o_fato_no_banco_a_tela_monta_na_hora_e_diz(banco, logado):  # noqa: F811
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert "fato_ronda calculado na hora; o banco ainda não tem" in html
    assert "fato_pt calculado na hora; o banco ainda não tem" in logado.get("/t/campo/pt").get_data(as_text=True)
    central = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert "fato_ronda calculado na hora" in central and "fato_pt calculado na hora" in central
    assert visao.rondas().dados["fatos"]["fechamento"].startswith("fato_fechamento calculado na hora")


def test_a_tela_monta_o_fato_com_a_mesma_funcao_da_carga(app, banco):  # noqa: F811
    """Uma regra só: a ligação da tela é a do `carga.montar_ronda` (usina, pessoa, dia)."""
    def ler(livro, aba):
        return livros.ler(BASE, banco, livro, aba)
    cad = {a: ler("cadastro_nexus", a) for a in ("usinas", "equipes", "de_para", "pessoas")}
    m = carga.mapas_das_linhas(app.config, cad["de_para"], cad["pessoas"])
    fato = [dict(zip(fato_ronda.CAB_RONDA, l)) for l in carga.montar_ronda(ler, carga.ligador(cad, m), m)[0]]
    tela = {r["ronda_id"]: r for r in visao._rondas_ligadas(visao._Base())}
    assert set(tela) == {f["ronda_id"] for f in fato}
    for f in fato:
        dia = str(f["data_id"])
        assert (tela[f["ronda_id"]]["usina_id"], tela[f["ronda_id"]]["data"]) == (
            f["usina_id"], f"{dia[:4]}-{dia[4:6]}-{dia[6:]}")


def test_fato_do_banco_da_mesma_versao_do_livro_vale_sem_aviso(app, banco, logado):  # noqa: F811
    _com_hora_dos_livros(banco, {"rondas_app_campo": "2026-10-08T15:50:01-03:00"})

    def mexer(linhas):
        # o fato do banco diz que a ronda sem OS de Brodowski foi na Coração 1: se a tela ler o banco, a Coração 1
        # deixa de ser "nunca teve ronda" (a tela não refaz a ligação)
        i = fato_ronda.CAB_RONDA.index("usina_id")
        for l in linhas:
            if l[fato_ronda.CAB_RONDA.index("origem")] == "app_sem_os":
                l[i] = 3
    _gravar_fato_ronda(app, banco, "2026-10-08T15:50:01-03:00", "2026-10-08T16:40:00-03:00", mexer=mexer)
    d = visao.rondas().dados
    assert d["fatos"]["ronda"] == ""
    cob = {c["usina"]: c["dias"] for c in d["cobertura"]}
    assert cob["Coração 1"] == 2 and cob["Brodowski 1"] == 999
    assert "fato_ronda calculado na hora" not in logado.get("/t/campo/rondas").get_data(as_text=True)


def test_fato_do_banco_mais_velho_que_o_livro_a_tela_monta_na_hora(app, banco, logado):  # noqa: F811
    _com_hora_dos_livros(banco, {"rondas_app_campo": "2026-10-08T16:50:02-03:00"})      # o App regravou às 16:50

    def mexer(linhas):
        linhas[:] = []                                                 # o fato velho (vazio) não pode ir para a tela
    _gravar_fato_ronda(app, banco, "2026-10-08T15:50:01-03:00", "2026-10-08T16:40:00-03:00", mexer=mexer)
    d = visao.rondas().dados
    assert len(d["todas"]) == 3
    assert d["fatos"]["ronda"] == ("fato_ronda calculado na hora; o banco tem a carga das 08/10 16:40, de antes do "
                                   "livro do App das 08/10 16:50")
    assert "de antes do livro do App" in logado.get("/t/campo/rondas").get_data(as_text=True)


def test_pt_e_ultima_os_pelo_fato_do_banco(app, banco):  # noqa: F811
    """A PT e a última OS da usina também saem do fato do banco quando ele é da versão do livro do App."""
    def ler(livro, aba):
        return livros.ler(BASE, banco, livro, aba)
    cad = {a: ler("cadastro_nexus", a) for a in ("usinas", "equipes", "de_para", "pessoas")}
    m = carga.mapas_das_linhas(app.config, cad["de_para"], cad["pessoas"])
    lig = carga.ligador(cad, m)
    pt = carga.montar_pt(ler, lig)[0]
    fech = carga.montar_fechamento(ler, lig)[0]
    for l in pt:            # o fato do banco diz outra situação: a tela tem de mostrar a do fato
        l[fato_pt.CAB_PT.index("situacao")] = "negada"
    for l in fech:          # e outra OS
        l[fatos.CAB_FECHAMENTO.index("os")] = "999"
    banco.workbooks["nexus_fatos"] = {}
    banco._id("nexus_fatos", "fato_pt")["linhas"] = [{"headers": fato_pt.CAB_PT, "values": l} for l in pt]
    banco._id("nexus_fatos", "fato_fechamento")["linhas"] = [{"headers": fatos.CAB_FECHAMENTO, "values": l}
                                                             for l in fech]
    quando = {"pt_app_campo": "2026-10-08T15:25:12-03:00", "fechamentos_app_campo": "2026-10-08T15:25:08-03:00"}
    q = []
    for fato, livro in (("pt", "pt_app_campo"), ("fechamento", "fechamentos_app_campo")):
        linha = {c: None for c in fatos.CAB_QUALIDADE}
        linha.update(fato=fato, origem_atualizada_em=quando[livro], gerado_em="2026-10-08T15:40:00-03:00", extra="{}")
        q.append({"headers": fatos.CAB_QUALIDADE, "values": [linha[c] for c in fatos.CAB_QUALIDADE]})
    banco._id("nexus_fatos", "qualidade")["linhas"] = q
    _com_hora_dos_livros(banco, quando)
    visao.limpar()
    d = visao.pts().dados
    assert d["fatos"]["pt"] == "" and not d["aguardando"] and {p["situacao"] for p in d["historico"]} == {"negada"}
    r = visao.rondas().dados
    assert r["fatos"]["fechamento"] == ""
    assert {c["usina"]: (c["ultima_os"] or {}).get("os") for c in r["cobertura"]}["Altair"] == "999"


def test_fato_que_falhou_na_carga_a_tela_monta_na_hora(app, banco):  # noqa: F811
    _com_hora_dos_livros(banco, {"rondas_app_campo": "2026-10-08T15:50:01-03:00"})
    _gravar_fato_ronda(app, banco, "2026-10-08T15:50:01-03:00", "2026-10-08T16:40:00-03:00",
                       mexer=lambda linhas: linhas.clear(), extra={"falhou_nesta_carga": "GraoDuplicado"})
    d = visao.rondas().dados
    assert len(d["todas"]) == 3 and "falhou neste fato" in d["fatos"]["ronda"]


def test_ronda_repetida_no_livro_nao_conta_em_dobro(banco, logado):  # noqa: F811
    _aba(banco, "rondas_app_campo", "OS de ronda", [_ronda(_dia(1)), _ronda(_dia(1))])     # o mesmo Início duas vezes
    visao.limpar()
    leitura = visao.rondas()
    assert leitura.erro.startswith("O livro do App tem a mesma linha duas vezes") and not leitura.dados
    r = logado.get("/t/campo/rondas")
    assert r.status_code == 200 and "não conta em dobro" in r.get_data(as_text=True)


def test_o_dia_da_ronda_e_o_de_brasilia_do_inicio(banco):  # noqa: F811
    """Regra 7 do nexus/dados: o dia é o de Brasília do início. Medido em 08/10: 1 de 876 rondas com a "Data" do App
    num dia e o início no seguinte (Castelo do Piauí, 06/10 x 07/10 09:09 em Brasília)."""
    ontem, hoje = _dia(1), _dia(0)
    _aba(banco, "rondas_app_campo", "OS de ronda", [_ronda(hoje, **{"Início": f"{hoje}T02:30:00.000Z",
                                                                     "Fim": f"{hoje}T02:50:00.000Z"})])
    visao.limpar()
    assert [r["data"] for r in visao.rondas().dados["todas"]] == [ontem]


def test_a_pessoa_do_fato_junta_as_grafias_pelo_cadastro(app, banco):  # noqa: F811
    """O nome da ronda é o "Nome padrão" da ficha pelo pessoa_id do fato; Quem ronda agrupa pela pessoa, não pela
    grafia (medido em 08/10: 79 grafias para 54 pessoas nos 90 dias)."""
    cofre = Cofre(CHAVE_CADASTRO)
    pessoas = banco.linhas("cadastro_nexus", "pessoas")
    pessoas.append({"pessoa_id": 7, "vinculo": "Colaborador de campo", "cargo": "Técnico O&M", "equipe_id": 10,
                    "status": "Ativo", "supervisor_id": 90, "excluido": "não",
                    "sensivel_cifrado": cofre.cifrar(json.dumps({"nome": "Fulano de Tal Souza",
                                                                 "nome_padrao": "Fulano Tal"}), "banco/pessoas/7")})
    _aba(banco, "cadastro_nexus", "pessoas", pessoas)
    _aba(banco, "rondas_app_campo", "OS de ronda", [_ronda(_dia(1)), _ronda(_dia(2), **{"Técnico": "FULANO DE TAL SOUZA"})])
    visao.limpar()
    d = visao.rondas().dados
    assert {r["tecnico"] for r in d["todas"]} == {"Fulano Tal"} and {r["pessoa_id"] for r in d["todas"]} == {7}
    quem = visao.painel_rondas(d["todas"], d["cobertura"], 7, d["hoje"])["quem"]
    assert [(q["tecnico"], q["rondas"]) for q in quem] == [("Fulano Tal", 2)]


# ── Validação por foto (Levi, 08/10/2026) ────────────────────────────────────────────────────────────────────────
def _avulsa(rid, dia, usina_id, origem="validacao_foto", **kw):
    cofre = Cofre(CHAVE_CADASTRO)
    linha = {"id": rid, "lancada_em": f"{dia}T20:00:00Z", "data_id": int(dia.replace("-", "")), "data": dia,
             "inicio": f"{dia}T08:00:00-03:00", "fim": f"{dia}T09:00:00-03:00", "duracao_min": 60, "usina_id": usina_id,
             "equipe_id": None, "pessoa_id": None, "pessoa_hmac": "",
             "quem_cifrado": cofre.cifrar(json.dumps({"nome": "Validadora de Fotos Teste", "email": "val@exemplo.test"}),
                                          f"banco/rondas_avulsas/{rid}/quem"),
             "tipo": "curta" if origem != "validacao_foto" else "", "sujidade": 5, "vegetacao": 4, "sombreamento": "",
             "vala": "Obstruída", "ipoa_sujo": "", "albedo_sujo": "", "ghi_sujo": "", "comentario_cifrado": "",
             "anula_id": "", "origem": origem}
    linha.update(kw)
    return linha


def test_validacao_por_foto_nao_e_ronda(banco, logado):  # noqa: F811
    antes = visao.rondas().dados
    _aba(banco, "nexus_rondas_avulsas", "fato_ronda_avulsa", [_avulsa("v1", _dia(1), 3)])     # Coração 1: nunca teve
    visao.limpar()
    d = visao.rondas().dados
    assert len(d["todas"]) == len(antes["todas"])                     # não é ronda: fora de Registros e da contagem
    assert {c["usina"]: c["dias"] for c in d["cobertura"]}["Coração 1"] == 999          # nem da cobertura
    k = visao.painel_rondas(d["todas"], d["cobertura"], 7, d["hoje"])["kpi"]
    assert (k["rondas"], k["cobertas"], k["nunca"]) == (3, 2, 1)
    assert [v["usina"] for v in d["validacoes"]] == ["Coração 1"]
    assert 'class="cn-validada"' not in logado.get("/t/campo/rondas").get_data(as_text=True)   # nem em Registros


def test_avulsa_sem_origem_continua_ronda(banco):  # noqa: F811
    _aba(banco, "nexus_rondas_avulsas", "fato_ronda_avulsa", [_avulsa("a1", _dia(1), 3, origem="")])
    visao.limpar()
    d = visao.rondas().dados
    assert any(r.get("avulsa") and r["usina"] == "Coração 1" for r in d["todas"]) and d["validacoes"] == []
    assert {c["usina"]: c["dias"] for c in d["cobertura"]}["Coração 1"] == 1


def test_validacao_vale_no_lugar_da_ronda_do_mesmo_dia(banco, logado, monkeypatch):  # noqa: F811
    # a ronda do App de ontem na Altair (OS 500) leu sujidade 2 e vegetação 1; a validação do mesmo dia diz 5 e 4
    _sem_fracttal(monkeypatch, {"500": {"sujidade": 2, "vegetacao": 1, "vala": "Limpa", "sensores_sujos": []}})
    _aba(banco, "nexus_rondas_avulsas", "fato_ronda_avulsa", [_avulsa("v1", _dia(1), 1)])
    visao.limpar()
    d = visao.rondas().dados
    s = visao.sujidade_vegetacao(d["todas"], d["cobertura"], ronda_checklist.respostas(), 30, d["hoje"], d["validacoes"])
    alt = next(x for x in s["linhas"] if x["usina"] == "Altair")
    assert (alt["sujidade"], alt["vegetacao"], alt["validada"], alt["data"]) == (5, 4, True, _dia(1))
    assert alt["tecnico"] == "Validadora Teste" and alt["os"] == "500"          # em nome de quem validou
    assert ("Vala obstruída", "critico") in alt["status"]
    html = logado.get("/t/campo/rondas?aba=sujidade").get_data(as_text=True)
    assert 'class="cn-validada"' in html and "Validada por foto" in html and "Não é ronda nova" in html
    # o histórico: a linha validada (com o selo) e a ronda do técnico marcada como revisada; a evolução usa o validado
    h = visao.historico_usina(d["todas"], ronda_checklist.respostas(), 1, d["validacoes"])
    val = [r for r in h if r.get("validada")]
    rev = [r for r in h if r.get("revisada")]
    assert len(val) == 1 and val[0]["sujidade"] == 5 and val[0]["revisa"][0]["os"] == "500"
    assert len(rev) == 1 and rev[0]["data"] == _dia(1) and rev[0]["sujidade"] == 2
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert 'class="cn-revisada"' in pag and 'class="cn-validada"' in pag
    assert ">2</span><span class=\"d\">nos últimos 90 dias" in pag or '<span class="v">2</span><span class="d">nos últimos 90 dias' in pag
    assert 'data-os="validada por foto"' in pag


def test_fato_ronda_deixa_a_validacao_por_foto_de_fora(banco):  # noqa: F811
    lig = fatos.Ligador([], [], [], {})
    av = [_avulsa("v1", _dia(1), 1), _avulsa("a1", _dia(2), 1, origem=""), _avulsa("a2", _dia(3), 1, origem="avulsa")]
    linhas, oq = fato_ronda.fato_ronda([], [], av, lig, {})
    assert len(linhas) == 2                                          # as duas avulsas; a validação não é ronda
    q = fato_ronda.qualidade_ronda(linhas, oq, None, "agora", avulsas=av)
    assert json.loads(q["extra"])["validacao_foto"] == 1
