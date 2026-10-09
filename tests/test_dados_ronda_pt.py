"""Passo 3 do Kimball (08/10/2026): o fato único de ronda e a PT conformada, com os domínios de `dominios.py`.

Cada teste prova uma regra da spec (docs/superpowers/specs/2026-10-08-kimball-passos-2-a-6-design.md, seção 3) com
dados inventados: nomes, usinas e códigos daqui NÃO são de gente nem de usina real (o repositório é público)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.campo import ronda_avulsa
from nexus.campo.ligacao_cadastro import _norm
from nexus.dados import dominios as DOM
from nexus.dados import fato_pt as FP
from nexus.dados import fato_ronda as FR
from nexus.dados import fatos, livros

BRT = timezone(timedelta(hours=-3))
BASE = "http://pg.falso"
FRACTTAL = "Fracttal · Classificação 1"
USINAS = [{"usina_id": 7, "codigo": "XPT-ABC100", "nome": "Usina Exemplo 7"},
          {"usina_id": 8, "codigo": "DEF200", "nome": "Usina Exemplo 8"},
          {"usina_id": 9, "codigo": "GHI300"}, {"usina_id": 10, "codigo": "ZZZ-GHI300"}]   # GHI300 é de duas
DE_PARA = [{"usina_id": 3, "sistema": FRACTTAL, "chave_externa": "Cliente X - Usina Exemplo 3 - XX"}]
EQUIPES = [{"equipe_id": 41, "nome": "XX Norte 01"}, {"equipe_id": 42, "nome": "XX Sul 02"}]
NOME_A, NOME_B = "Fulano Exemplo da Silva", "Beltrana Exemplo Souza"
POR_NOME = {_norm(NOME_A): 55, _norm(NOME_B): 56}


def _lig():
    return fatos.Ligador(USINAS, DE_PARA, EQUIPES, {"hmac-a": 55, "hmac-b": 56})


def _app(inicio="2026-10-01T02:30:00.000Z", **kw):
    d = {"Data": "2026-09-30", "OS": "15001", "Usina": "Cliente X - Usina Exemplo 3 - XX",
         "Ativo da usina no Fracttal": "XPT-ABC100", "ID da OS no Fracttal": "9150010", "Região": "XX Norte 01",
         "Técnico": NOME_A, "Tipo": "curta", "Situação da OS": "Criada", "Nota da ronda": 95, "Falhas": "",
         "Trackers apontados": 0, "Trackers respondidos": 0, "Início": inicio, "Fim": "2026-10-01T03:10:00.000Z"}
    d.update(kw)
    return d


def _ck(inicio="2026-10-01T02:30:00.000Z", **kw):
    d = {"ronda_id": "x", "data_id": 20260930, "usina_id": 3, "equipe_id": 41, "pessoa_id": 55, "tipo": "longa",
         "inicio": inicio, "fim": "2026-10-01T04:00:00.000Z", "sujidade": 4, "vegetacao": 2, "vala": "Obstruída",
         "ipoa_sujo": 1, "ghi_sujo": 0, "albedo_sujo": None, "usina_ligada_por": "de-para do Fracttal"}
    d.update(kw)
    return d


def _av(rid="a1", **kw):
    d = {"id": rid, "lancada_em": "2026-10-07T12:00:00Z", "data_id": 20261007, "data": "2026-10-07",
         "inicio": "2026-10-07T08:00:00-03:00", "fim": "2026-10-07T09:30:00-03:00", "duracao_min": 90, "usina_id": 8,
         "equipe_id": 42, "pessoa_id": None, "pessoa_hmac": "hmac-b", "quem_cifrado": "cifrado", "tipo": "curta",
         "sujidade": 3, "vegetacao": 5, "sombreamento": "sim", "vala": "Suja", "ipoa_sujo": 1, "albedo_sujo": 0,
         "ghi_sujo": 0, "comentario_cifrado": "", "anula_id": "", "origem": "avulsa"}
    d.update(kw)
    return d


def _dic(linhas, cab=FR.CAB_RONDA):
    return [dict(zip(cab, l)) for l in linhas]


def _ronda(app=(), ck=(), av=(), **kw):
    linhas, oq = FR.fato_ronda(list(app), list(ck), list(av), _lig(), POR_NOME, **kw)
    return _dic(linhas), linhas, oq


# ── contrato: cabeçalho, medidas, domínio ─────────────────────────────────────────────────────────────────────────
def test_cabecalhos_do_contrato_e_nada_de_texto_pessoal():
    # 08/10 (ligação): + equipamento_ligado_por depois do equipamento_id (regra 5, linhagem; desenho seção 5)
    assert FR.CAB_RONDA == [
        "ronda_id", "origem", "data_id", "usina_id", "usina_ligada_por", "equipe_id", "pessoa_id", "pessoa_hmac",
        "pessoa_ligada_por", "equipamento_id", "equipamento_ligado_por", "os", "id_os_fracttal", "os_situacao",
        "tipo_ronda", "inicio", "fim", "duracao_min", "nota_pts", "falhas_qtd", "longa_pendente", "item_sem_foto", "acao_sem_registro",
        "checklist_incompleto", "sem_gps", "evidencia_incompleta", "trackers_apontados_qtd", "trackers_respondidos_qtd",
        "checklist_fonte", "sujidade_nivel", "vegetacao_nivel", "vala_nivel", "sombreamento", "ipoa_sujo", "ghi_sujo",
        "albedo_sujo"]
    assert FP.CAB_PT == [
        "pt_linha_id", "pt", "primeira_linha_da_pt", "os", "codigo_ativo", "data_id_criacao", "data_id_decisao",
        "usina_id", "usina_ligada_por", "equipe_id", "equipamento_id", "equipamento_ligado_por",
        "solicitante_pessoa_id", "solicitante_hmac",
        "decisor_pessoa_id", "decisor_hmac", "decisor_papel", "situacao", "decidida", "criada_em", "decidida_em",
        "espera_min", "parada", "respostas_nao_qtd", "atividades_qtd", "forcada", "efeito"]
    proibidas = ("nome", "email", "e-mail", "tecnico", "observacao", "comentario", "motivo", "tarefa", "atividades")
    for cab in (FR.CAB_RONDA, FP.CAB_PT):
        assert len(cab) == len(set(cab))
        # a contagem pode (atividades_qtd); o texto, não
        assert not [c for c in cab if any(p == c or (c.startswith(p + "_") and not c.endswith("_qtd"))
                                          for p in proibidas)]


@pytest.mark.parametrize("mod", [FR, FP])
def test_medidas_tem_unidade_no_nome_ou_sao_indicador(mod):
    sufixos = ("_min", "_kwh", "_kwh_m2", "_mm", "_pct", "_qtd", "_pts", "_nivel")
    cab = mod.CAB_RONDA if mod is FR else mod.CAB_PT
    assert mod.TIPO in ("transacao", "snapshot_periodico", "snapshot_acumulado", "sem_medida")
    assert mod.GRAO.startswith("1 linha") and mod.CHAVE[0] == cab[0]
    for col, unidade, soma in mod.MEDIDAS:
        assert col in cab, col
        assert soma in ("aditiva", "semi", "nao"), col
        assert col.endswith(sufixos) or unidade == "1/0", col


def test_dominios_antigos_traduzidos_linha_a_linha():
    """O mapeamento do que já está gravado (vala do App/checklist e da avulsa de 07/10; sensor do checklist e da
    avulsa de 07/10) é dado em `MAPA_ANTIGO`: cada linha dele é provada aqui."""
    for fonte, mapa in DOM.MAPA_ANTIGO["vala"].items():
        for antigo, novo in mapa.items():
            assert DOM.vala(antigo) == novo, (fonte, antigo)
    assert DOM.vala("obstruida ") == 3 and DOM.vala_fora("Suja") and not DOM.vala_fora("Não se aplica")
    for antigo, novo in DOM.MAPA_ANTIGO["sensor"]["checklist"].items():
        assert DOM.sensor(antigo) == novo, antigo
    for antigo, novo in DOM.MAPA_ANTIGO["sensor"]["avulsa_07_10"].items():
        assert DOM.sensor_avulsa(antigo) == novo, antigo
    # a API devolve texto às vezes: "1"/"0" do checklist valem o mesmo; o "0" da avulsa continua não verificado
    assert (DOM.sensor("1"), DOM.sensor("0"), DOM.sensor_avulsa("0"), DOM.sensor_avulsa("Limpo")) == (1, 0, None, 0)


def test_situacao_da_os_e_falhas_viram_dominio():
    assert [DOM.os_situacao(t) for t in ("Criada", "Em verificação", "Criada — fila parou: aviso inventado",
                                          "Não criada — conta desconectada", "", "outra coisa")] == [
        "criada", "em_verificacao", "criada_com_aviso", "nao_criada", None, None]
    achadas, desc = DOM.falhas("ação prescrita sem registro; ronda longa pendente; evidência incompleta (faltam "
                               "fotos); item sem foto de evidência; sem GPS; checklist incompleto; rótulo novo")
    assert achadas == set(DOM.INDICADORES_FALHA) and desc == ["rotulo novo"]
    assert DOM.pt_situacao("") == "aguardando" and DOM.pt_situacao("De acordo") == "de_acordo"
    assert DOM.pt_situacao("cancelada") is None


# ── fato_ronda ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_ronda_sem_os_mais_checklist_e_uma_linha():
    app = _app(OS=None, **{"ID da OS no Fracttal": None, "Ativo da usina no Fracttal": None,
                           "Situação da OS": "Não criada — conta desconectada"})
    d, _, oq = _ronda([app], [_ck()])
    assert len(d) == 1
    r = d[0]
    assert (r["origem"], r["os"], r["os_situacao"], r["checklist_fonte"]) == ("app_sem_os", None, "nao_criada",
                                                                               "carga_unica_sem_os")
    assert (r["sujidade_nivel"], r["vegetacao_nivel"], r["vala_nivel"]) == (4, 2, 3)
    assert (r["ipoa_sujo"], r["ghi_sujo"], r["albedo_sujo"]) == (1, 0, None)
    assert r["ronda_id"] == FR.chave("app", "2026-10-01T02:30:00.000Z") and oq[0]["checklist"] == "casou"


def test_ronda_com_os_e_campos_do_app():
    d, _, _ = _ronda([_app(Falhas="ronda longa pendente; sem GPS", **{"Situação da OS": "Criada — aviso inventado"})],
                     equip={"XPT-ABC100": 777}.get)
    r = d[0]
    assert (r["origem"], r["os"], r["id_os_fracttal"], r["equipamento_id"]) == ("app_os", "15001", "9150010", 777)
    assert (r["data_id"], r["usina_id"], r["usina_ligada_por"], r["equipe_id"]) == (20260930, 3, "de-para do Fracttal",
                                                                                    41)
    assert (r["os_situacao"], r["tipo_ronda"], r["duracao_min"], r["nota_pts"]) == ("criada_com_aviso", "curta", 40, 95)
    assert (r["falhas_qtd"], r["longa_pendente"], r["sem_gps"], r["item_sem_foto"]) == (2, 1, 1, 0)
    assert r["checklist_fonte"] is None and r["sujidade_nivel"] is None
    # sem o módulo de equipamento, vazio (nunca o código no lugar do ID)
    assert _ronda([_app()])[0][0]["equipamento_id"] is None


def test_data_id_de_inicio_as_02_30z_e_o_dia_anterior_e_duracao_fora_do_relogio():
    d, _, _ = _ronda([_app(inicio="2026-10-08T02:30:00.000Z", Fim="2026-10-08T13:00:00.000Z")])
    assert d[0]["data_id"] == 20261007 and d[0]["duracao_min"] is None        # 10,5 h: relógio errado


def test_checklist_sem_a_linha_do_app_continua_com_o_mesmo_ronda_id():
    """A janela do App é de 90 dias: a ronda de agosto sai do livro, a resposta do checklist fica no fato."""
    com_app, _, _ = _ronda([_app(OS=None)], [_ck()])
    sem_app, _, oq = _ronda([], [_ck()])
    assert len(sem_app) == 1 and sem_app[0]["ronda_id"] == com_app[0]["ronda_id"]
    r = sem_app[0]
    assert (r["origem"], r["data_id"], r["usina_id"], r["equipe_id"], r["pessoa_id"], r["pessoa_ligada_por"]) == (
        "app_sem_os", 20260930, 3, 41, 55, "cadastro")
    assert (r["vala_nivel"], r["tipo_ronda"], r["duracao_min"], r["os_situacao"]) == (3, "longa", 90, None)
    assert oq[0]["checklist"] == "so_no_livro"


def test_checklist_de_outra_usina_no_mesmo_inicio_nao_empresta_resposta():
    d, _, oq = _ronda([_app()], [_ck(usina_id=8)])
    assert len(d) == 1 and d[0]["checklist_fonte"] is None and d[0]["sujidade_nivel"] is None
    assert oq[0]["checklist"] == "conflito"


def test_checklist_completa_usina_e_equipe_que_o_app_nao_ligou():
    d, _, _ = _ronda([_app(Usina="nome que não casa", Região="Equipe fora do cadastro",
                           **{"Ativo da usina no Fracttal": "SEM-CODIGO"})], [_ck()])
    assert (d[0]["usina_id"], d[0]["usina_ligada_por"], d[0]["equipe_id"]) == (3, "de-para do Fracttal", 41)


def test_avulsa_anulada_fica_fora_e_a_anulacao_nao_vira_linha():
    linhas = [_av("a1"), _av("a2"), _av("a3", inicio="", anula_id="a2", origem="anulação")]
    assert FR.avulsas_validas(linhas) == ronda_avulsa.validas(linhas)        # a mesma regra da tela
    d, lin, oq = _ronda(av=linhas)
    assert [r["ronda_id"] for r in d] == [FR.chave("avulsa", "a1")]
    r = d[0]
    assert (r["origem"], r["data_id"], r["usina_id"], r["equipe_id"], r["checklist_fonte"]) == (
        "avulsa", 20261007, 8, None, "avulsa")                    # a equipe da avulsa é outro papel: vazio
    assert (r["pessoa_id"], r["pessoa_ligada_por"], r["pessoa_hmac"]) == (56, "hmac", "hmac-b")
    # "Suja" não existe no App: vazio; sensor 0 do formulário de 07/10 = não marcado, não "limpo"
    assert (r["vala_nivel"], r["sombreamento"], r["ipoa_sujo"], r["ghi_sujo"], r["albedo_sujo"]) == (None, 1, 1, None,
                                                                                                     None)
    assert (r["os"], r["nota_pts"], r["falhas_qtd"], r["duracao_min"]) == (None, None, None, 90)
    q = FR.qualidade_ronda(lin, oq, None, "t", avulsas=linhas)
    extra = json.loads(q["extra"])
    assert (extra["avulsa"], extra["anuladas"], extra["vala_fora"]) == (1, 1, 1)


def test_vala_obstruida_do_app_e_do_checklist_e_3_e_nao_se_aplica_e_vazio():
    d, _, _ = _ronda([_app(inicio="i1", OS=None), _app(inicio="i2", OS=None)],
                     [_ck(inicio="i1", vala="Obstruída"), _ck(inicio="i2", vala="Não se aplica"),
                      _ck(inicio="i3", vala="Obstruída")])
    assert [r["vala_nivel"] for r in d] == [3, None, 3]


def test_sensor_limpo_e_0_sujo_e_1_sem_resposta_e_vazio():
    d, _, _ = _ronda(ck=[_ck(ipoa_sujo="Sujo", ghi_sujo="Limpo", albedo_sujo="Não se aplica")])
    assert (d[0]["ipoa_sujo"], d[0]["ghi_sujo"], d[0]["albedo_sujo"]) == (1, 0, None)
    d, _, _ = _ronda(av=[_av(ipoa_sujo="Limpo", ghi_sujo="Sujo", albedo_sujo="")])     # avulsa de três estados
    assert (d[0]["ipoa_sujo"], d[0]["ghi_sujo"], d[0]["albedo_sujo"]) == (0, 1, None)


def test_pessoa_hmac_vence_nome_e_nome_so_liga_se_for_de_uma_pessoa():
    d, _, _ = _ronda([_app(inicio="i1", **{"Técnico (HMAC)": "hmac-b"}),      # nome de A, código de B: vale B
                      _app(inicio="i2"),                                       # só nome: liga pelo nome
                      _app(inicio="i3", **{"Técnico": "Nome Que Nao Existe"})])
    assert [(r["pessoa_id"], r["pessoa_ligada_por"], r["pessoa_hmac"]) for r in d] == [
        (56, "hmac", "hmac-b"), (55, "nome", None), (None, None, None)]
    # homônimo: o nome que é de duas pessoas não liga (o mapa pode vir com o conjunto de IDs)
    linhas, _ = FR.fato_ronda([_app()], [], [], _lig(), {_norm(NOME_A): {55, 57}})
    assert _dic(linhas)[0]["pessoa_id"] is None
    # o mapa do `mapas()` já vem sem o homônimo: o nome fora dele não liga
    linhas, _ = FR.fato_ronda([_app()], [], [], _lig(), {})
    assert _dic(linhas)[0]["pessoa_id"] is None


def test_nenhuma_celula_do_fato_contem_o_nome():
    fn = FR.codigo_do_nome("chave-de-teste")
    linhas, _ = FR.fato_ronda([_app(inicio="i1"), _app(inicio="i2", **{"Técnico": NOME_B})], [_ck(inicio="i9")],
                              [_av()], _lig(), POR_NOME, codigo_do_nome=fn)
    pedacos = {p.lower() for n in (NOME_A, NOME_B) for p in n.split() if len(p) > 3}
    for l in linhas:
        for v in l:
            assert not any(p in str(v).lower() for p in pedacos), v
    d = _dic(linhas)
    assert d[0]["pessoa_hmac"].startswith("n:") and d[0]["pessoa_hmac"] == fn(NOME_A.upper())   # chave durável
    assert FR.codigo_do_nome("") is None


def test_grao_ronda_id_repetido_e_erro():
    with pytest.raises(FR.GraoDuplicado):
        FR.fato_ronda([_app(), _app(OS="15002")], [], [], _lig(), POR_NOME)
    with pytest.raises(FR.GraoDuplicado):
        FR.fato_ronda([], [], [_av("a1"), _av("a1")], _lig(), POR_NOME)


def test_app_sem_inicio_fica_fora_e_conta():
    linhas, oq = FR.fato_ronda([_app(inicio="")], [_ck(inicio="i1"), _ck(inicio="i1", usina_id=8)], [], _lig(), POR_NOME)
    assert linhas == [] and len(oq) == 0
    assert oq.fora == {"app_sem_inicio": 1, "checklist_ambiguo": 2}


def test_qualidade_da_ronda_com_extra_uma_casa_e_versao_da_epoca():
    app = [_app(inicio=f"2026-10-0{k}T12:00:00.000Z") for k in range(1, 4)]
    app.append(_app(inicio="2026-10-05T12:00:00.000Z", Usina="Usina Que Nao Existe", Região="Equipe Nova 99",
                    **{"Ativo da usina no Fracttal": None}))
    linhas, oq = FR.fato_ronda(app, [_ck(inicio="i-velho", data_id=20260815)], [_av()], _lig(), POR_NOME)
    hist = {"usinas": [{"usina_id": 3, "valido_de": "2026-09-30", "valido_ate": None},
                       {"usina_id": 8, "valido_de_id": 19000101, "valido_ate_id": 99991231}],
            "pessoas": [{"pessoa_id": 55, "valido_de": "2026-10-02", "valido_ate": None}]}
    q = FR.qualidade_ronda(linhas, oq, "2026-10-08T10:50:00", "agora", avulsas=[_av()], hist=hist)
    assert (q["fato"], q["linhas"], q["com_usina"], q["pct_usina"]) == ("ronda", 6, 5, 83.3)
    assert "Usina Que Nao Existe (1)" in q["sem_usina_exemplos"] and "Equipe Nova 99 (1)" in q["sem_equipe_exemplos"]
    # usina 3 tem versão desde 30/09: as 4 do App (3 ligadas) + a do checklist de 15/08 -> 3 acham, 1 não; a avulsa (8) acha
    assert q["pct_usina_versao"] == 80.0
    assert q["pct_pessoa_versao"] == 50.0      # 55 desde 02/10: 02, 03 e 05/10 acham; 01/10, 15/08 e a 56 (sem histórico) não
    extra = json.loads(q["extra"])
    assert (extra["app_os"], extra["app_sem_os"], extra["avulsa"], extra["checklist"]) == (4, 1, 1, 2)
    assert extra["pessoa_por_nome"] == 4 and extra["pessoa_por_cadastro"] == 1 and extra["pessoa_por_hmac"] == 1
    assert FR.qualidade_ronda(linhas, oq, None, "t")["pct_usina_versao"] is None    # sem histórico, vazio
    assert set(fatos.CAB_QUALIDADE) <= set(q)


def test_ronda_lida_da_api_que_devolve_tudo_como_texto():
    """A API pode devolver número como texto ("7", "20260930"): o fato sai igual."""
    api = ApiPGFalsa(como_texto=True)
    ck = [_ck(inicio="i1"), _ck(inicio="i2", pessoa_id=None, ipoa_sujo=0)]
    livros.publicar("nexus_rondas_checklist", "x", {"fato_checklist_ronda": (list(ck[0]), [list(c.values()) for c in ck])},
                    base=BASE, token="t", sessao=api)
    lidos = livros.ler(BASE, api, "nexus_rondas_checklist", "fato_checklist_ronda")
    assert lidos[0]["usina_id"] == "3"
    d_txt = _ronda(ck=lidos)[0]
    d_int = _ronda(ck=ck)[0]
    assert d_txt == d_int


# ── fato_pt ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _pt(numero="PT-15001-0110-0900", cod="XPT-ABC100-INVR1.1", **kw):
    d = {"Criada em": "2026-10-01T02:00:00.000Z", "Número": numero, "OS": "15001", "Tarefa": "Tarefa inventada",
         "Código do ativo": cod, "Usina": "Cliente X - Usina Exemplo 3 - XX", "Região": "XX Norte 01",
         "Ativo": "Inversor inventado", "Solicitante (HMAC)": "hmac-a", "Situação": "de_acordo",
         "Decidida em": "2026-10-01T04:30:00.000Z", "Decidida por (HMAC)": "hmac-admin", "Papel de quem decidiu": "Admin",
         "Motivo": "", "Efeito": "anexada", "Respostas NÃO": 3, "Faltam": 0,
         "Atividades": "Atividade um; Atividade dois;", "Forçada": None, "1º aviso em": None,
         "1º aviso: motivo": "mensagem de erro inventada"}
    d.update(kw)
    return d


AGORA = datetime(2026, 10, 1, 9, 0, tzinfo=BRT)


def _fpt(pt, **kw):
    return [dict(zip(FP.CAB_PT, l)) for l in FP.fato_pt(pt, _lig(), agora=kw.pop("agora", AGORA), **kw)]


def test_pt_linha_id_unico_com_o_mesmo_numero_em_dois_ativos_e_primeira_linha_conta_as_pts():
    pts = [_pt(cod="XPT-ABC100-INVR1.2"), _pt(cod="XPT-ABC100-INVR1.1"), _pt(numero="PT-2", cod="DEF200-INVR3.1")]
    d = _fpt(pts, equip=lambda c: 900 if c.startswith("XPT") else None)
    assert len({r["pt_linha_id"] for r in d}) == 3
    assert d[0]["pt_linha_id"] == FR.chave("PT-15001-0110-0900", "XPT-ABC100-INVR1.2")
    assert [r["primeira_linha_da_pt"] for r in d] == [0, 1, 1] and sum(r["primeira_linha_da_pt"] for r in d) == 2
    assert [r["equipamento_id"] for r in d] == [900, 900, None]
    with pytest.raises(FR.GraoDuplicado):
        FP.fato_pt([_pt(), _pt(Tarefa="outra")], _lig(), agora=AGORA)        # mesmo número e ativo: grão quebrado


def test_pt_ids_papeis_de_data_e_nada_de_texto():
    r = _fpt([_pt(**{"Criada em": "2026-10-01T23:50:00.000Z", "Decidida em": "2026-10-02T03:30:00.000Z"})])[0]
    assert (r["data_id_criacao"], r["data_id_decisao"]) == (20261001, 20261002)   # 20:50 e 00:30 de Brasília
    assert (r["usina_id"], r["usina_ligada_por"], r["equipe_id"], r["solicitante_pessoa_id"]) == (
        3, "de-para do Fracttal", 41, 55)
    assert (r["decisor_pessoa_id"], r["decisor_hmac"], r["decisor_papel"]) == (None, "hmac-admin", "admin")
    assert (r["situacao"], r["decidida"], r["espera_min"], r["parada"]) == ("de_acordo", 1, 220, 1)
    assert (r["respostas_nao_qtd"], r["atividades_qtd"], r["forcada"], r["efeito"]) == (3, 2, 0, "anexada")
    texto = {"Tarefa inventada", "Inversor inventado", "mensagem de erro inventada", "Atividade um"}
    assert not any(str(v) in texto for v in r.values())
    # usina pelo código do ativo quando o nome não casa; código de duas usinas não liga
    d = _fpt([_pt(Usina="x", cod="DEF200-INVR1.1"), _pt(numero="PT-9", Usina="x", cod="GHI300-INVR1.1")])
    assert [(r["usina_id"], r["usina_ligada_por"]) for r in d] == [(8, "código do ativo"), (None, None)]


def test_espera_vazia_na_aguardando_e_parada_nao_volta_a_0():
    agu = _pt(Situação="aguardando", **{"Decidida em": None, "Decidida por (HMAC)": None, "Efeito": None,
                                        "Papel de quem decidiu": None})
    # carga às 01:10 de Brasília (04:10Z): esperando há 130 min -> parada
    r1 = _fpt([agu], agora=datetime(2026, 10, 1, 1, 10, tzinfo=BRT))[0]
    assert (r1["situacao"], r1["decidida"], r1["espera_min"], r1["parada"], r1["data_id_decisao"]) == (
        "aguardando", 0, None, 1, None)
    # carga seguinte: decidida 140 min depois de criada -> continua 1
    dec = dict(agu, Situação="de_acordo", **{"Decidida em": "2026-10-01T04:20:00.000Z"})
    r2 = _fpt([dec], agora=datetime(2026, 10, 1, 2, 10, tzinfo=BRT))[0]
    assert (r2["pt_linha_id"], r2["espera_min"], r2["parada"]) == (r1["pt_linha_id"], 140, 1)
    # aguardando há 30 min: não parada; decidida em 60 min: não parada; decidida sem data: vazio, nunca 0 inventado
    assert _fpt([agu], agora=datetime(2026, 9, 30, 23, 30, tzinfo=BRT))[0]["parada"] == 0
    assert _fpt([dict(dec, **{"Decidida em": "2026-10-01T03:00:00.000Z"})])[0]["parada"] == 0
    assert _fpt([dict(dec, **{"Decidida em": None})])[0]["parada"] is None


def test_qualidade_da_pt_com_extra():
    pts = [_pt(cod="A-1"), _pt(cod="A-2", Situação="aguardando", **{"Decidida em": None}),
           _pt(numero="PT-2", cod="B-1", Usina="Usina Que Nao Existe", Região="", **{"Decidida em": "2026-10-02T12:00:00Z"}),
           _pt(numero="PT-3", cod="C-1", Situação="cancelada"), {"Número": "", "Código do ativo": "X"}]
    linhas = FP.fato_pt(pts, _lig(), agora=AGORA)
    hist = {"pessoas": [{"pessoa_id": 55, "valido_de_id": 19000101, "valido_ate_id": 99991231}]}
    q = FP.qualidade_pt(linhas, pts, "2026-10-08T11:25:05", "agora", hist=hist)
    assert (q["fato"], q["linhas"], q["com_usina"], q["pct_usina"], q["pct_pessoa"]) == ("pt", 4, 3, 75.0, 100.0)
    assert q["pct_pessoa_versao"] == 100.0 and q["pct_usina_versao"] is None
    assert "Usina Que Nao Existe (1)" in q["sem_usina_exemplos"]
    e = json.loads(q["extra"])
    assert (e["pts"], e["situacao_de_acordo"], e["situacao_aguardando"], e["situacao_fora"]) == (3, 2, 1, 1)
    assert (e["decisor_ligado"], e["decisor_com_hmac"], e["decidida_em_outro_dia"], e["fora_sem_numero"]) == (0, 2, 2, 1)


# ── o checklist que o App manda na própria linha (v249 do App, 09/10/2026: "faz meu mano") ───────────────────────────
CK_APP = {"Sujidade dos módulos (1 a 5)": 2, "Tipos de sujidade": "Poeira / areia", "Altura da vegetação (1 a 5)": 5,
          "Vala de drenagem": "Limpa", "Piranômetro GHI": "Sujo", "Piranômetro IPOA": "Limpo",
          "Albedômetro": "Não se aplica", "Checklist da ronda": "Sujidade dos módulos: 2 [Poeira / areia]; Altura da vegetação: 5"}


def test_checklist_do_app_na_linha_vence_a_carga_unica():
    """A mesma ronda com o checklist na linha do App e na carga única (que diz outra coisa): vale o do App, a fonte."""
    d, _, oq = _ronda([_app(**CK_APP)], [_ck()])
    r = d[0]
    assert (r["checklist_fonte"], r["sujidade_nivel"], r["vegetacao_nivel"], r["vala_nivel"]) == ("app", 2, 5, 1)
    assert (r["ghi_sujo"], r["ipoa_sujo"], r["albedo_sujo"], r["sombreamento"]) == (1, 0, None, None)
    assert oq[0]["vala"] == "Limpa" and len(d) == 1                  # a carga única não vira outra linha


def test_linha_do_app_sem_checklist_usa_a_carga_unica_como_antes():
    d, _, _ = _ronda([_app()], [_ck()])
    assert (d[0]["checklist_fonte"], d[0]["sujidade_nivel"], d[0]["vala_nivel"]) == ("carga_unica_sem_os", 4, 3)


def test_checklist_do_app_sem_carga_unica_e_nao_se_aplica():
    d, _, _ = _ronda([_app(**{"Sujidade dos módulos (1 a 5)": None, "Altura da vegetação (1 a 5)": 3,
                              "Vala de drenagem": "Não se aplica", "Piranômetro GHI": "Não se aplica"})])
    r = d[0]
    assert (r["checklist_fonte"], r["sujidade_nivel"], r["vegetacao_nivel"], r["vala_nivel"], r["ghi_sujo"]) == (
        "app", None, 3, None, None)


def test_colunas_do_app_vazias_nao_viram_checklist():
    d, _, _ = _ronda([_app(**{c: "" for c in FR.APP_CHECKLIST.values()})])
    assert d[0]["checklist_fonte"] is None and d[0]["sujidade_nivel"] is None


def test_as_colunas_do_app_sao_as_que_o_app_manda():
    """Os nomes casam com o RONDAS_WB_COLUNAS da v249 do App (function_app.py): mudou lá, muda aqui."""
    assert set(FR.APP_CHECKLIST.values()) <= {
        "Técnico (HMAC)", "Sujidade dos módulos (1 a 5)", "Tipos de sujidade", "Altura da vegetação (1 a 5)",
        "Vala de drenagem", "Piranômetro GHI", "Piranômetro IPOA", "Albedômetro", "Checklist da ronda"}
