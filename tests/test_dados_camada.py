"""A camada de dados do Nexus (método Kimball, 05/10/2026): catálogo, calendário, fatos com IDs, a carga que grava e
confere, e a tela Base → Governança de dados.

08/10/2026 (passos 2 a 6 da auditoria Kimball, ligados na carga): o catálogo com tipo, chave e medidas em todo fato e os
livros registrados antes de existir; o fato único de ronda, a PT conformada, a dimensão de equipamento (gravada só
quando muda), o histórico SCD2 (as regras dele estão em `test_dados_historico.py`) e a programação do PCM, que é
montada e NUNCA gravada daqui (decisão 7 do Levi). Códigos, usinas e PCM inventados."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa, Resposta

from nexus.campo import decisao_pt, ronda_avulsa
from nexus.dados import calendario, carga, catalogo, equipamento, fato_pt, fato_ronda, fatos, geracao, historico, livros
from nexus.dados import programacao
from nexus.dados import telas as telas_dados

BASE = "http://pg.falso"
BRT = timezone(timedelta(hours=-3))


# ── catálogo ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_catalogo_declara_grao_estado_e_todas_as_dimensoes():
    ids = [f.id for f in catalogo.FATOS]
    assert len(ids) == len(set(ids))
    for f in catalogo.FATOS:
        assert f.grao.startswith("1 linha"), f.id
        assert set(f.dims) == set(catalogo.DIM_IDS), f.id
        assert all(e in catalogo.ESTADOS for e, _ in f.dims.values()), f.id
        assert f.estado in catalogo.ESTADOS_FATO, f.id
        if f.estado == "conformado":
            assert f.conformado_em, f.id
        if f.estado in ("origem", "fora", "aposentado", "parte"):
            assert not f.conformado_em, f.id
        # "parte": virou fonte de outro fato, que existe e não é ele mesmo parte de outro (a história fica)
        assert (f.estado == "parte") == bool(f.parte_de), f.id
        assert all(p in catalogo.POR_ID and catalogo.POR_ID[p].estado not in ("parte", "aposentado")
                   for p in f.parte_de), f.id
    r = catalogo.resumo()
    assert r["conformados"] >= 3 and r["montados"] >= 3
    # a auditoria de 08/10: ronda e PT tinham o grão errado; checklist e avulsa viraram fonte do fato único de ronda
    assert "OS de ronda" not in catalogo.POR_ID["ronda"].grao and "ativo" in catalogo.POR_ID["pt"].grao
    assert catalogo.POR_ID["ronda_checklist"].parte_de == catalogo.POR_ID["ronda_avulsa"].parte_de == ("ronda",)
    assert set(catalogo.POR_ID["falha_string"].parte_de) == {"falha_string_episodio", "falha_string_inversor_dia"}
    assert set(catalogo.POR_ID["geracao_thopen"].parte_de) == {"geracao_usina_dia", "geracao_inversor_dia"}


def test_todo_fato_declara_tipo_chave_e_medidas_com_unidade():
    """Auditoria de 08/10: nenhum fato dizia o tipo (transação, foto periódica, foto acumulada, sem medida) nem quais
    colunas são medida e se somam. Agora é obrigatório; medida com a unidade no nome, ou indicador 1/0."""
    for f in catalogo.FATOS:
        assert f.tipo in catalogo.TIPOS_FATO, f.id
    for f in catalogo.ativos():
        assert (f.tipo == "sem_medida") == (f.medidas == ()), f.id
        assert all(isinstance(m, catalogo.Medida) and catalogo.medida_valida(m) for m in f.medidas), f.id
        assert len({m.coluna for m in f.medidas}) == len(f.medidas), f.id
        assert f.fontes, f.id
        # sem chave só o fato que ainda é de origem e diz por quê (decisão do painel, zeladoria)
        if not f.chave:
            assert f.estado == "origem" and "sem chave" in f.observacao, f.id
    assert not catalogo.medida_valida(catalogo.Medida("nota", "pts", "nao"))          # sem a unidade no nome
    assert not catalogo.medida_valida(catalogo.Medida("nota_pts", "pts", "talvez"))
    assert catalogo.medida_valida(catalogo.Medida("pontual", "1/0", "aditiva"))
    # revisão de 08/10: fechamento e ronda MUDAM depois de entrar (a revisão do fechamento, a situação da OS da ronda):
    # declarados transação ("nunca muda"), o passo 0 acrescentaria pela chave e congelaria a 1ª versão da linha
    assert catalogo.POR_ID["fechamento"].tipo == catalogo.POR_ID["ronda"].tipo == "snapshot_acumulado"


CABS = {"fechamento": fatos.CAB_FECHAMENTO, "ronda": fato_ronda.CAB_RONDA, "pt": fato_pt.CAB_PT,
        "programacao": programacao.CAB_PROGRAMACAO, "geracao_usina_dia": geracao.CAB_USINA_DIA,
        "geracao_inversor_dia": geracao.CAB_INVERSOR_DIA}
PROIBIDAS = ("nome", "email", "tecnico", "observacao", "comentario", "motivo", "tarefa", "relatorio", "atividades")


def test_catalogo_bate_com_o_codigo_de_cada_fato_conformado_ou_montado():
    """O catálogo é a fonte da tela e do .md: a chave, as medidas e o ID de cada dimensão 'id' existem no cabeçalho
    que o código grava; quem tem usina_id/equipamento_id diz por onde ligou (regra 5); nada de texto pessoal."""
    assert {f.id for f in catalogo.FATOS if f.estado in ("conformado", "montado")} == set(CABS)
    col_dim = {"data": "data_id", "usina": "usina_id", "equipe": "equipe_id", "pessoa": "pessoa_id",
               "equipamento": "equipamento_id"}
    for fid, cab in CABS.items():
        f = catalogo.POR_ID[fid]
        assert f.chave and f.chave[0] == cab[0] and all(c in cab for c in f.chave), fid
        assert all(m.coluna in cab for m in f.medidas), fid
        for d, (est, _col) in f.dims.items():
            if est == "id":
                assert any(c.startswith(col_dim[d]) or c.endswith(col_dim[d]) for c in cab), (fid, d)
        # no inversor × dia a usina é a da aba: a linhagem dela está no usina × dia da mesma (fonte, aba), sem repetir
        # um texto em ~700 mil linhas
        assert ("usina_id" not in cab) or "usina_ligada_por" in cab or fid == "geracao_inversor_dia", fid
        assert ("equipamento_id" not in cab) or "equipamento_ligado_por" in cab, fid
        # texto pessoal não entra; a contagem (_qtd), a chave (tarefa_chave) e o indicador 1/0 declarado, sim
        indicadores = {m.coluna for m in f.medidas if m.unidade == "1/0"}
        assert not [c for c in cab if c not in indicadores and any(
            c == p or (c.startswith(p + "_") and not c.endswith(("_qtd", "_chave"))) for p in PROIBIDAS)], fid
        if f.conformado_em:
            livro, aba = f.conformado_em.split(" · ")
            assert aba in catalogo.LIVRO_POR_NOME[livro].abas, fid


def test_livros_do_nexus_registrados_antes_de_existir_e_na_regra_10():
    for l in catalogo.LIVROS:
        assert l.nome.startswith("nexus_"), l.nome
        assert l.abas and all(catalogo.aba_segue_a_regra(a) for a in l.abas), l.nome
    for nome in (carga.LIVRO_DIM, carga.LIVRO_FATOS, equipamento.LIVRO, equipamento.LIVRO_FOTO, programacao.LIVRO,
                 geracao.LIVRO, ronda_avulsa.LIVRO, decisao_pt.LIVRO, "nexus_rondas_checklist"):
        assert nome in catalogo.LIVRO_POR_NOME, nome
    assert ronda_avulsa.ABA in catalogo.LIVRO_POR_NOME[ronda_avulsa.LIVRO].abas
    assert equipamento.ABA_FOTO in catalogo.LIVRO_POR_NOME[equipamento.LIVRO_FOTO].abas
    assert geracao.ABA_USINA in catalogo.LIVRO_POR_NOME[geracao.LIVRO].abas
    assert programacao.ABA in catalogo.LIVRO_POR_NOME[programacao.LIVRO].abas
    assert historico.ABA_QUALIDADE in catalogo.LIVRO_POR_NOME[carga.LIVRO_DIM].abas
    assert not catalogo.aba_segue_a_regra("Planilha1")


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


# ── histórico: as regras estão em test_dados_historico.py; aqui, só o cadastro de teste ────────────────────────────
def _p(pid, equipe, sup, **kw):
    d = {"pessoa_id": pid, "equipe_id": equipe, "supervisor_id": sup, "cargo": "Técnico", "vinculo": "CLT",
         "status": "Ativo", "alterado_em": "2026-09-30T10:00:00", "excluido": "não"}
    d.update(kw)
    return d


# ── fatos com IDs ─────────────────────────────────────────────────────────────────────────────────────────────────
USINAS = [{"usina_id": 7, "codigo": "THPN-PRM200", "nome": "Primavera 2"},
          {"usina_id": 8, "codigo": "MAB100", "nome": "Mabel 1"}, {"usina_id": 9, "codigo": "ATHN-MAB100"},
          {"usina_id": 3, "codigo": "XYZ-EXE900", "nome": "Usina do de-para"}]
DE_PARA = [{"usina_id": 3, "sistema": "Fracttal · Classificação 1", "chave_externa": "Cliente Exemplo - Usina Exemplo 1 e 2 - PA"}]
EQUIPES = [{"equipe_id": 41, "nome": "PR Oeste 01"}]


def _fech(**kw):
    d = {"Registrado em": "2026-10-01T02:30:00.000Z", "OS": "15377", "ID da OS no Fracttal": "153770",
         "Tarefa": "Inspeção", "Código do ativo": "THPN-PRM200-PGINVR1", "Usina": "Cliente Exemplo · Cliente Exemplo - Usina Exemplo 1 e 2 - PA",
         "Região": "PR Oeste 01", "Tipo da OS": "Preventiva", "Criticidade": "Alta", "Técnico (HMAC)": "abc",
         "Nota do painel": 72, "Pontual": "sim", "Devolvida": None, "Fotos": 3, "Observação no App": "texto com nome",
         "Vezes reprogramada": 2}
    d.update(kw)
    return d


def _lig():
    return fatos.Ligador(USINAS, DE_PARA, EQUIPES, {"abc": 55})


def test_liga_usina_pelo_de_para_e_pelo_codigo_so_quando_unico():
    lig = _lig()
    assert lig.usina("Cliente Exemplo · Cliente Exemplo - Usina Exemplo 1 e 2 - PA", "") == (3, "de-para do Fracttal")
    assert lig.usina("Cliente Exemplo · nome que não casa", "THPN-PRM200-TRFR1") == (7, "código do ativo")
    assert lig.usina("x", "MAB100-INVR2.4") == (None, None)         # MAB100 é de duas usinas: não chuta
    assert lig.equipe("pr  oeste 01") == 41 and lig.pessoa("abc;def") == 55 and lig.pessoa("zzz") is None


def test_fato_fechamento_leva_ids_dia_de_brasilia_e_nada_de_texto_livre():
    f = dict(zip(fatos.CAB_FECHAMENTO, fatos.fato_fechamento([_fech()], _lig())[0]))
    assert (f["data_id"], f["usina_id"], f["equipe_id"], f["pessoa_id"]) == (20260930, 3, 41, 55)
    assert f["nota_pts"] == 72 and f["pontual"] == 1 and f["devolvida"] == 0 and f["usina_ligada_por"] == "de-para do Fracttal"
    assert f["fotos_qtd"] == 3 and f["vezes_programada_qtd"] == 2
    assert "texto com nome" not in [str(v) for v in f.values()] and "Inspeção" not in [str(v) for v in f.values()]
    # sem a dimensão de equipamento, vazio (nunca o código no lugar do ID)
    assert (f["equipamento_id"], f["equipamento_ligado_por"]) == (None, None)


def test_fechamento_ganha_equipamento_e_a_tarefa_casa_com_a_programacao():
    """08/10: o código do ativo estava em todos os fechamentos e nenhum tinha o equipamento_id; a tarefa_chave é a
    mesma conta da programação do PCM (programado × executado por OS + código + tarefa)."""
    ix = equipamento.indice(equipamento.membros([], {"x": ["THPN-PRM200-PGINVR1"]}, USINAS))
    linhas = fatos.fato_fechamento([_fech(), _fech(**{"Código do ativo": "GRID"})], _lig(),
                                   lambda c: equipamento.ligar(c, ix))
    f, g = (dict(zip(fatos.CAB_FECHAMENTO, l)) for l in linhas)
    assert f["equipamento_id"] == equipamento.equipamento_id("THPN-PRM200-PGINVR1")
    assert f["equipamento_ligado_por"] == equipamento.COM_USINA
    assert (g["equipamento_id"], g["equipamento_ligado_por"]) == (None, None)       # "GRID" não é equipamento
    assert f["tarefa_chave"] == programacao.tarefa_chave("inspecao ") == fatos.tarefa_chave("INSPEÇÃO")


def test_checklist_da_ronda_sem_os_liga_pela_data_e_inicio_e_nao_chuta():
    """Carga única de 06/10: a ronda sem OS ganha as respostas do registro dela no App, casando dia + início; ronda sem
    registro único fica fora; o e-mail só vira pessoa_id; sensor "Não se aplica" e vala fora da lista = vazio."""
    livro = [{"Data": "2026-09-30", "Usina": "Cliente Exemplo - Usina Exemplo 1 e 2 - PA", "Ativo da usina no Fracttal": "",
              "Região": "PR Oeste 01", "Tipo": "longa", "Início": "2026-10-01T01:30:00.000Z", "Fim": "2026-10-01T02:30:00.000Z"},
             {"Data": "2026-09-29", "Usina": "Cliente Exemplo - Usina Exemplo 1 e 2 - PA", "Início": "2026-09-29T12:00:00.000Z"}]
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
    # desde 08/10 o livro da carga única é FONTE do fato único de ronda
    assert catalogo.POR_ID["ronda_checklist"].parte_de == ("ronda",)


def test_qualidade_conta_mostra_o_que_faltou_e_a_versao_da_epoca():
    origem = [_fech(), _fech(Usina="Nobreak 1", **{"Código do ativo": "SPDA", "Região": "MT Sul 02"})]
    linhas = fatos.fato_fechamento(origem, _lig())
    q = dict(zip(fatos.CAB_QUALIDADE, fatos.qualidade("fechamento", "x", linhas, fatos.CAB_FECHAMENTO, origem, None, "t")))
    assert (q["linhas"], q["com_usina"], q["pct_usina"], q["pct_equipe"]) == (2, 1, 50.0, 50.0)
    assert "Nobreak 1 (1)" in q["sem_usina_exemplos"] and "MT Sul 02 (1)" in q["sem_equipe_exemplos"]
    assert (q["com_equipamento"], q["pct_equipamento"]) == (0, 0.0)
    assert q["pct_usina_versao"] is None and json.loads(q["extra"]) == {}     # sem histórico: vazio, não 0%
    # 1 casa decimal: o inteiro mostrava 99,7% como 100%
    assert fatos._pct(997, 1000) == 99.7 and fatos._pct(1, 3) == 33.3
    # a versão da época: a pessoa 55 com versão desde sempre acha; a usina 3 só desde 01/10 não acha o fato de 30/09
    hist = {"pessoas": [{"pessoa_id": 55, "valido_de_id": 19000101, "valido_ate_id": 99991231}],
            "usinas": [{"usina_id": 3, "valido_de": "2026-10-01", "valido_ate": None}]}
    q = dict(zip(fatos.CAB_QUALIDADE, fatos.qualidade("fechamento", "x", linhas, fatos.CAB_FECHAMENTO, origem, None,
                                                       "t", hist=hist, extra={"a": 1})))
    assert (q["pct_pessoa_versao"], q["pct_usina_versao"], json.loads(q["extra"])) == (100.0, 0.0, {"a": 1})
    # no empate, os exemplos saem pela ordem do texto: o mesmo banco lido em outra ordem (a outra máquina) dá o mesmo
    o2 = [_fech(Usina="Usina B", **{"Código do ativo": "SPDA"}), _fech(Usina="Usina A", **{"Código do ativo": "SPDA"})]
    ex = {fatos.qualidade("f", "x", fatos.fato_fechamento(o, _lig()), fatos.CAB_FECHAMENTO, o, None, "t")[13]
          for o in (o2, o2[::-1])}
    assert ex == {"Usina A (1); Usina B (1)"}


# ── a carga: grava, confere e não grava em dobro ──────────────────────────────────────────────────────────────────
def _aba(api, livro, aba, linhas):
    api.workbooks.setdefault(livro, {})
    if not linhas:
        api._id(livro, aba)["linhas"] = []
        return
    cab = list(linhas[0])
    api._id(livro, aba)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]


def _ronda(inicio, **kw):
    d = {"Data": "2026-09-30", "OS": "15400", "Usina": "Cliente Exemplo - Usina Exemplo 1 e 2 - PA",
         "Ativo da usina no Fracttal": "THPN-PRM200", "ID da OS no Fracttal": "154000", "Região": "PR Oeste 01",
         "Técnico": "Pessoa Inventada", "Tipo": "curta", "Situação da OS": "Criada", "Nota da ronda": 90, "Falhas": "",
         "Trackers apontados": 0, "Trackers respondidos": 0, "Início": inicio, "Fim": "2026-10-01T03:00:00.000Z"}
    d.update(kw)
    return d


def _pt(cod, **kw):
    d = {"Criada em": "2026-10-01T12:00:00.000Z", "Número": "PT-15377-0001", "OS": "15377", "Tarefa": "Tarefa x",
         "Código do ativo": cod, "Usina": "Cliente Exemplo - Usina Exemplo 1 e 2 - PA", "Região": "PR Oeste 01",
         "Solicitante (HMAC)": "abc", "Situação": "de_acordo", "Decidida em": "2026-10-01T14:30:00.000Z",
         "Atividades": "Uma; Duas", "Motivo": "texto livre"}
    d.update(kw)
    return d


# o banco_dados.json do PCM: 1 bloco planejado e 1 linha "foraDoPlano" (execução, outro grão: fica fora do fato)
PCM = {"geradoEm": "2026-10-05T12:00:00Z", "semanas": [{"week": "2026-W41", "dates": {"seg": "05/10"},
       "geradaEm": "2026-10-04T20:00:00", "rows": [
           {"codigo": "THPN-PRM200-TRFR1", "os_id": "15500", "tarefa": "Inspeção do trafo", "dia": "Segunda-feira",
            "h_ini": "08:00", "usina": "Cliente Exemplo - Usina Exemplo 1 e 2 - PA", "cluster": "PR Oeste 01", "duracao": 1.5,
            "resp_os": "Pessoa Inventada"},
           {"foraDoPlano": True, "codigo": "THPN-PRM200-FORA9", "os_id": "15501", "tarefa": "x", "dia": "Terça-feira"}]}]}


@pytest.fixture
def banco(tmp_path):
    api = ApiPGFalsa()
    _aba(api, "cadastro_nexus", "usinas", USINAS)
    _aba(api, "cadastro_nexus", "equipes", EQUIPES)
    _aba(api, "cadastro_nexus", "pessoas", [_p(1, 41, 100)])
    _aba(api, "cadastro_nexus", "de_para", DE_PARA)
    _aba(api, "fechamentos_app_campo", "Fechamentos", [_fech(), _fech(OS="15378", Tarefa="Outra")])
    # uma ronda com OS e uma sem OS; o checklist da carga única casa com a sem OS pelo Início
    _aba(api, "rondas_app_campo", "OS de ronda", [_ronda("2026-10-01T02:00:00.000Z"),
                                                  _ronda("2026-10-01T05:00:00.000Z", OS="", **{
                                                      "Situação da OS": "Não criada"})])
    _aba(api, "nexus_rondas_checklist", "fato_checklist_ronda", [
        {"ronda_id": "x", "data_id": 20261001, "usina_id": 3, "equipe_id": 41, "pessoa_id": 1, "tipo": "curta",
         "inicio": "2026-10-01T05:00:00.000Z", "fim": None, "sujidade": 3, "vegetacao": 2, "vala": "Obstruída",
         "ipoa_sujo": 0, "ghi_sujo": 1, "albedo_sujo": None, "usina_ligada_por": "de-para do Fracttal"}])
    # uma PT de dois ativos: 2 linhas, 1 PT
    _aba(api, "pt_app_campo", "PT", [_pt("THPN-PRM200-INVR1.1"), _pt("THPN-PRM200-INVR1.2")])
    fonte = tmp_path / "banco_dados.json"
    fonte.write_text(json.dumps(PCM), encoding="utf-8")
    cfg = {"GRIDCO_DB_API": BASE, "GRIDCO_SQL_TOKEN": "t", "TESTING": True, "NEXUS_PCM_TRABALHO": str(tmp_path),
           "NEXUS_PCM_FONTE": str(fonte)}
    return api, cfg


def test_carga_grava_os_livros_registrados_e_confere(banco):
    api, cfg = banco
    agora = datetime(2026, 10, 5, 15, 40, tzinfo=BRT)
    r = carga.rodar(cfg, api, agora=agora)
    assert r["gravado"]["nexus_fatos"]["fato_fechamento"] == 2 and r["pct_usina"] == 100
    assert r["gravado"]["nexus_dimensoes"]["dim_data"] == (calendario.FIM - calendario.INICIO).days + 1
    # cada livro gravado tem exatamente as abas registradas no catálogo (regra 10)
    for livro in ("nexus_fatos", "nexus_dimensoes", "nexus_equipamentos"):
        assert set(r["gravado"][livro]) == set(catalogo.LIVRO_POR_NOME[livro].abas), livro
    # a programação e a geração são montadas só no ensaio: a carga de hora em hora nunca as grava (decisões 7 e 8)
    assert "nexus_programacao" not in api.workbooks and "nexus_geracao" not in api.workbooks
    f = livros.ler(BASE, api, "nexus_fatos", "fato_fechamento")
    assert {x["usina_id"] for x in f} == {3} and {x["data_id"] for x in f} == {20260930}
    assert {x["equipamento_id"] for x in f} == {equipamento.equipamento_id("THPN-PRM200-PGINVR1")}
    # o fato único de ronda: a com OS, a sem OS com as respostas do checklist
    rd = {x["os"] or "sem": x for x in livros.ler(BASE, api, "nexus_fatos", "fato_ronda")}
    assert set(rd) == {"15400", "sem"} and rd["sem"]["vala_nivel"] == 3 and rd["sem"]["origem"] == "app_sem_os"
    assert rd["15400"]["equipamento_id"] == equipamento.equipamento_id("THPN-PRM200")
    assert "Pessoa Inventada" not in json.dumps(livros.ler(BASE, api, "nexus_fatos", "fato_ronda"))
    # a PT de dois ativos: 2 linhas, 1 PT
    p = livros.ler(BASE, api, "nexus_fatos", "fato_pt")
    assert len(p) == 2 and sum(x["primeira_linha_da_pt"] for x in p) == 1
    assert "texto livre" not in json.dumps(p)
    q = {x["fato"]: x for x in livros.ler(BASE, api, "nexus_fatos", "qualidade")}
    assert set(q) == {"fechamento", "ronda", "pt"} and q["fechamento"]["pct_equipamento"] == 100
    # a junção da época contra o histórico desta carga: a usina 3 tem versão "desde sempre" (antes de 08/10, 25%)
    assert [q[f]["pct_usina_versao"] for f in ("fechamento", "ronda", "pt")] == [100, 100, 100]
    assert q["fechamento"]["pct_pessoa_versao"] is None             # sem a chave do cadastro, nenhuma pessoa ligou
    h = livros.ler(BASE, api, "nexus_dimensoes", "pessoas_historico")
    assert [(x["pessoa_id"], x["vigente"], x["valido_de"]) for x in h] == [(1, "sim", "1900-01-01")]
    assert len(livros.ler(BASE, api, "nexus_dimensoes", historico.ABA_QUALIDADE)) == 2
    # a dimensão de equipamento: o código do plano do PCM entra; o da linha foraDoPlano, não
    dim = {x["codigo"] for x in livros.ler(BASE, api, "nexus_equipamentos", "dim_equipamento")}
    assert {"THPN-PRM200-PGINVR1", "THPN-PRM200-TRFR1", "THPN-PRM200-INVR1.1"} <= dim
    assert "THPN-PRM200-FORA9" not in dim
    # outra máquina 10 min depois: pula, não grava em dobro
    assert "pulou" in carga.rodar(cfg, api, agora=agora + timedelta(minutes=10))


def test_dimensao_de_equipamento_so_grava_quando_muda(banco):
    """~1 MB que muda por semana: regravar a cada hora seriam 24 trocas integrais por dia sem nada novo."""
    api, cfg = banco
    r1 = carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 15, 40, tzinfo=BRT))
    r2 = carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 16, 40, tzinfo=BRT))
    assert "nexus_equipamentos" in r1["gravado"] and "nexus_equipamentos" not in r2["gravado"]
    assert r2["equipamento"]["mudou"] is False and "nexus_fatos" in r2["gravado"]
    _aba(api, "pt_app_campo", "PT", [_pt("THPN-PRM200-INVR1.1"), _pt("THPN-PRM200-INVR9.9")])
    r3 = carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 17, 40, tzinfo=BRT))
    assert "nexus_equipamentos" in r3["gravado"]


def test_pcm_fora_do_ar_nao_grava_a_dimensao_mas_o_fato_tem_o_id(banco):
    """O PCM que não respondeu numa hora tiraria da dimensão o que só ele tem; o ID sai do próprio código, então o
    fato continua com o equipamento_id (a qualidade conta o que ficou fora da dimensão)."""
    api, cfg = banco
    cfg.pop("NEXUS_PCM_FONTE")
    r = carga.rodar(cfg, api, forcar=True)
    assert "nexus_equipamentos" not in r["gravado"] and r["equipamento"]["publicar"] is False
    assert r["pcm"] == "não lido" and "nexus_equipamentos" not in api.workbooks
    assert {x["equipamento_id"] for x in livros.ler(BASE, api, "nexus_fatos", "fato_fechamento")} == {
        equipamento.equipamento_id("THPN-PRM200-PGINVR1")}


def test_carga_seguinte_registra_a_mudanca_de_supervisor(banco):
    api, cfg = banco
    carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 15, 40, tzinfo=BRT))
    _aba(api, "cadastro_nexus", "pessoas", [_p(1, 41, 101, alterado_em="2026-10-06T13:00:00Z")])
    carga.rodar(cfg, api, agora=datetime(2026, 10, 6, 15, 40, tzinfo=BRT))
    h = livros.ler(BASE, api, "nexus_dimensoes", "pessoas_historico")
    assert [(x["supervisor_id"], x["valido_de"], x["valido_ate"], x["vigente"]) for x in h] == [
        (100, "1900-01-01", "2026-10-06", "não"), (101, "2026-10-06", None, "sim")]
    q = livros.ler(BASE, api, "nexus_dimensoes", "qualidade_historico")
    assert [(x["entidade"], x["sobreposicoes"], x["pulou_motivo"]) for x in q] == [("pessoas", 0, None),
                                                                                   ("usinas", 0, None)]


def test_historico_lido_vazio_segura_as_dimensoes_e_os_fatos_seguem(banco):
    """Regra 6 do histórico: a aba lida vazia com o livro já gravado é leitura falha; gravar trocaria o histórico por
    nada. O `nexus_dimensoes` não é gravado nesta hora; o `nexus_fatos` segue."""
    api, cfg = banco
    carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 15, 40, tzinfo=BRT))
    _aba(api, "nexus_dimensoes", "pessoas_historico", [])
    r = carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 16, 40, tzinfo=BRT))
    assert r["segurar_dimensoes"] is True and "nexus_dimensoes" not in r["gravado"] and "nexus_fatos" in r["gravado"]
    assert "pessoas" in r["historico_pulou"]


def _falhar_leitura(api, livro, aba):
    """A aba passa a responder 500 (a API fora do ar para ela): o `livros._linhas` sobe HTTPError."""
    sid = api.abas[(livro, aba)]["id"]
    get = api.get

    def get_falho(url, params=None, headers=None, timeout=None):
        if url.endswith(f"/api/sheets/{sid}/rows"):
            return Resposta(500, {})
        return get(url, params=params, headers=headers, timeout=timeout)
    api.get = get_falho


def test_ronda_repetida_fica_como_estava_e_o_fechamento_anda(banco):
    """Isolamento (revisão de 08/10): o grão quebrado (o mesmo Início duas vezes) num fato NOVO não pode parar o
    fato_fechamento, que funcionava antes dele. A aba da ronda fica como está no banco (gravar o livro sem ela a
    apagaria, troca integral), a qualidade diz o erro, e o fechamento novo entra."""
    api, cfg = banco
    carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 15, 40, tzinfo=BRT))
    antes = livros.ler(BASE, api, "nexus_fatos", "fato_ronda")
    _aba(api, "rondas_app_campo", "OS de ronda", [_ronda("2026-10-01T02:00:00.000Z"),
                                                  _ronda("2026-10-01T02:00:00.000Z")])
    _aba(api, "fechamentos_app_campo", "Fechamentos", [_fech(), _fech(OS="15378", Tarefa="Outra"),
                                                       _fech(OS="15379", Tarefa="Mais uma")])
    r = carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 16, 40, tzinfo=BRT))
    assert r["falhou"]["ronda"].startswith("GraoDuplicado") and r["fato_ronda"] is None
    assert r["gravado"]["nexus_fatos"]["fato_fechamento"] == 3 and "nexus_dimensoes" in r["gravado"]
    assert livros.ler(BASE, api, "nexus_fatos", "fato_ronda") == antes and len(antes) == 2
    q = {x["fato"]: x for x in livros.ler(BASE, api, "nexus_fatos", "qualidade")}
    ex = json.loads(q["ronda"]["extra"])
    assert ex["falhou_nesta_carga"].startswith("GraoDuplicado") and q["ronda"]["linhas"] == 2
    assert "falhou_nesta_carga" not in json.loads(q["fechamento"]["extra"])
    # banco novo (a aba nunca foi gravada): não há o que apagar, ela só não entra nesta hora
    api2, cfg2 = ApiPGFalsa(), cfg
    for (wb, aba), v in api.abas.items():
        if not wb.startswith("nexus_"):
            api2.workbooks.setdefault(wb, {})
            api2._id(wb, aba)["linhas"] = v["linhas"]
    r2 = carga.rodar(cfg2, api2, forcar=True)
    assert "fato_ronda" not in r2["gravado"]["nexus_fatos"] and r2["gravado"]["nexus_fatos"]["fato_fechamento"] == 3


def test_fonte_fora_do_ar_de_um_fato_novo_nao_para_o_fechamento(banco):
    """A PT (fonte nova) responde 500 numa hora: o fato_pt fica como estava; o fechamento e as dimensões andam."""
    api, cfg = banco
    carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 15, 40, tzinfo=BRT))
    _aba(api, "fechamentos_app_campo", "Fechamentos", [_fech(), _fech(OS="15378", Tarefa="Outra"),
                                                       _fech(OS="15379", Tarefa="Mais uma")])
    _falhar_leitura(api, "pt_app_campo", "PT")
    r = carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 16, 40, tzinfo=BRT))
    assert r["falhou"]["pt"].startswith("HTTPError") and r["gravado"]["nexus_fatos"]["fato_pt"] == 2
    assert r["gravado"]["nexus_fatos"]["fato_fechamento"] == 3 and "ronda" not in r["falhou"]
    # na qualidade (API de leitura aberta) vai só o tipo do erro: a mensagem pode trazer o valor que o causou
    q = {x["fato"]: x for x in livros.ler(BASE, api, "nexus_fatos", "qualidade")}
    assert json.loads(q["pt"]["extra"])["falhou_nesta_carga"] == "HTTPError"


def test_fonte_da_dimensao_fora_do_ar_nao_tira_o_equipamento_do_fechamento(banco):
    """Uma fonte que só a dimensão de equipamento lê (o de-para de trackers) responde 500: a dimensão não é gravada
    nesta hora e o fechamento liga pelo índice da dimensão GRAVADA (não perde o equipamento_id nem a hora)."""
    api, cfg = banco
    _aba(api, "de_para_trackers", "De-Para Trackers", [{"Fonte": "x", "UFV Supervisório": "u",
                                                        "Tracker Supervisório": "t", "Code Fracttal": "THPN-PRM200-TRK1"}])
    carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 15, 40, tzinfo=BRT))
    _falhar_leitura(api, "de_para_trackers", "De-Para Trackers")
    r = carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 16, 40, tzinfo=BRT))
    assert r["falhou"]["equipamento"].startswith("HTTPError") and r["equipamento"]["indice"] == "dimensão gravada"
    assert "nexus_equipamentos" not in r["gravado"] and "nexus_fatos" in r["gravado"]
    f = livros.ler(BASE, api, "nexus_fatos", "fato_fechamento")
    assert {(x["equipamento_id"], x["equipamento_ligado_por"]) for x in f} == {
        (equipamento.equipamento_id("THPN-PRM200-PGINVR1"), equipamento.COM_USINA)}


def test_historico_quebrado_segura_as_dimensoes_e_os_fatos_andam(banco, monkeypatch):
    api, cfg = banco
    carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 15, 40, tzinfo=BRT))

    def quebra(*a, **k):
        raise KeyError("coluna nova")
    monkeypatch.setattr(historico, "tabelas", quebra)
    r = carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 16, 40, tzinfo=BRT))
    assert r["falhou"]["historico"].startswith("KeyError") and r["segurar_dimensoes"] is True
    assert "nexus_dimensoes" not in r["gravado"] and "nexus_fatos" in r["gravado"]
    assert r["pct"]["fechamento"]["usina_versao"] is None           # sem histórico: vazio, não 0%


def test_gravacao_de_um_livro_que_falha_nao_segura_os_outros(banco):
    """O nexus_equipamentos (novo, gravado antes dos fatos) falha na gravação: o nexus_fatos e o nexus_dimensoes
    da mesma hora são gravados, e o erro sobe no fim (não fica calado)."""
    api, cfg = banco
    post = api.post

    def post_falho(url, headers=None, json=None, params=None, files=None, timeout=None):
        if url.endswith("/nexus_equipamentos/sync-xlsx"):
            return Resposta(502, {})
        return post(url, headers=headers, json=json, params=params, files=files, timeout=timeout)
    api.post = post_falho
    with pytest.raises(Exception, match="502"):
        carga.rodar(cfg, api, forcar=True)
    assert livros.ler(BASE, api, "nexus_fatos", "fato_fechamento") and livros.ler(BASE, api, "nexus_dimensoes",
                                                                                  "dim_data")


def test_origem_que_encolhe_aparece_e_ainda_grava(banco):
    """Herança do passo 1 (adiado pelo Levi em 08/10): a carga NÃO recusa a origem que encolheu; mostra."""
    api, cfg = banco
    carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 15, 40, tzinfo=BRT))
    _aba(api, "fechamentos_app_campo", "Fechamentos", [_fech()])
    r = carga.rodar(cfg, api, agora=datetime(2026, 10, 5, 16, 40, tzinfo=BRT))
    assert r["encolheram"] == {"fechamento": [2, 1]} and r["gravado"]["nexus_fatos"]["fato_fechamento"] == 1
    q = {x["fato"]: x for x in livros.ler(BASE, api, "nexus_fatos", "qualidade")}
    assert json.loads(q["fechamento"]["extra"])["linhas_na_carga_anterior"] == 2


def test_ensaio_monta_a_programacao_e_nao_grava_nada(banco):
    api, cfg = banco
    grava, montados, rel = carga.montar(cfg, api, datetime(2026, 10, 5, 15, 40, tzinfo=BRT), ensaio=True)
    assert api.syncs == 0 and programacao.LIVRO not in grava
    assert set(grava) <= {carga.LIVRO_DIM, carga.LIVRO_FATOS, equipamento.LIVRO}
    cab, linhas = montados[programacao.LIVRO][programacao.ABA]
    assert len(linhas) == 1 and rel["programacao"]["fora_do_plano"] == 1
    p = dict(zip(cab, linhas[0]))
    assert (p["usina_id"], p["equipe_id"], p["data_id_programada"]) == (3, 41, 20261005)
    assert p["equipamento_id"] == equipamento.equipamento_id("THPN-PRM200-TRFR1")
    assert "Pessoa Inventada" not in json.dumps(linhas)
    assert carga.montar(cfg, api, datetime(2026, 10, 5, 15, 40, tzinfo=BRT))[1] == {}     # sem ensaio, nada a mais


def test_apelido_de_coluna_de_geracao_so_com_o_de_para_das_abas(banco):
    """Sem os sistemas de aba publicados (decisão 8 do Levi), nenhuma coluna liga e nada é lido; publicados, a
    coluna "Inversor 1.1" da aba da usina 7 vira apelido do membro "<código da usina 7>-INVR1.1"."""
    api, cfg = banco
    _aba(api, "bd_thopen", "Aba Exemplo", [{"Data": "2026-10-04", "Inversor 1.1": 100.0, "Inversor 1.2": 90.0}])
    _, _, rel = carga.montar(cfg, api, datetime(2026, 10, 5, 15, 40, tzinfo=BRT))
    assert rel["equipamento"]["colunas_de_geracao"].startswith("de-para das abas")
    _aba(api, "cadastro_nexus", "de_para", DE_PARA + [{"usina_id": 7, "sistema": "BD_Thopen · aba",
                                                       "chave_externa": "Aba Exemplo", "casou_por": "nome"}])
    grava, _, rel = carga.montar(cfg, api, datetime(2026, 10, 5, 15, 40, tzinfo=BRT))
    apel = grava["nexus_equipamentos"]["equipamento_apelido"][1]
    assert [a[0] for a in apel if a[2] == "Aba Exemplo|Inversor 1.1"] == [equipamento.equipamento_id("THPN-PRM200-INVR1.1")]
    # a geração diária (só ensaio): a mesma aba, com usina e equipamento, sem gravar
    tab, inversor, rg = carga.montar_geracao(cfg, api, datetime(2026, 10, 5, 15, 40, tzinfo=BRT), apelidos=apel)
    assert rg["linhas_usina_dia"] == 1 and len(inversor) == 2 and rg["pct_usina"] == 100.0
    assert {l[3] for l in inversor} == {equipamento.equipamento_id("THPN-PRM200-INVR1.1"),
                                        equipamento.equipamento_id("THPN-PRM200-INVR1.2")}
    assert "nexus_geracao" not in api.workbooks


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
def test_tela_mostra_a_matriz_o_tipo_os_livros_e_a_qualidade(app, banco):
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
    assert "foto acumulada" in html and "montado, sem gravar" in html and "fonte de ronda" in html
    assert "nexus_equipamentos" in html and "registrado, ainda não" in html
    assert "Histórico das dimensões" in html and "Dimensão de equipamento" in html
    assert "Qualidade da ligação · Ronda" in html and "Qualidade da ligação · Permissão de trabalho" in html
    assert telas_dados._pct(99.7) == "99,7%" and telas_dados._pct("100.0") == "100%" and telas_dados._pct(None) == ""


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
