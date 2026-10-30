"""As normalizações da Ronda COS no banco (29/10/2026, Levi: "calcule a disponibilidade por lá usando o de-para como
referência"; o Nexus grava e a plataforma faz a régua da Thopen): a linha do fato (a usina pelo código do Fracttal, só
o de uma usina; o dia de Brasília; as proteções em código; nada de nome nem texto livre), o laço que grava com o banco
falso (as linhas de antes da memória ficam, as recusas) e o catálogo. Dados fictícios."""
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.cos import andamento as AND
from nexus.cos import normalizacoes as NO
from nexus.cos import normalizacoes_banco as NB
from nexus.dados import catalogo, livros

AGORA = datetime(2026, 10, 29, 15, 22, tzinfo=timezone(timedelta(hours=-3)))
USINAS = [{"usina_id": 1, "codigo": "TSTE-AAA100", "excluido": ""},
          {"usina_id": 2, "codigo": "TSTE-BBB200", "excluido": ""},
          # o mesmo sufixo em dois clientes: o código sem o prefixo não liga (regra 4)
          {"usina_id": 3, "codigo": "TSTE-CCC300", "excluido": ""},
          {"usina_id": 4, "codigo": "OUTR-CCC300", "excluido": ""}]


def _n(registro, **kw):
    n = {"registro": registro, "os": "17001", "os_relacionadas": [], "os_aberta_por": "Fulana de Tal",
         "tecnico": "Beltrano Souza", "cliente": "THOPEN", "usina_codigo": "TSTE-AAA100", "usina": "Usina Teste 1",
         "equipamentos": [], "tipo_falha": "DESLIGAMENTO_USINA", "tipo_falha_rotulo": "Desligamento de usina",
         "severidade": "CRITICO", "estado": "NORMALIZADO", "normalizada": True,
         "inicio": "2026-10-27T09:00:00-03:00", "normalizado_em": "2026-10-27T10:30:00-03:00", "fora_min": 90,
         "hora_real": True, "fim_corrigido": False, "declarada_por": "pessoa", "geracao_parou": None,
         "protecoes": ["27ABC", "86"], "impacto": "texto livre do time", "detalhes": {"descricao": "relato"},
         "informe": {"resumo": "relato curto"}, "fora_do_escopo_oem": False, "mudou_em": "2026-10-27T10:31:00-03:00"}
    n.update(kw)
    return n


def _linha(n):
    return dict(zip(NB.CAB, NB.linha(n, NB.EQ.IndiceUsinas(USINAS))))


def test_a_linha_liga_a_usina_pelo_codigo_e_guarda_a_hora_da_volta():
    l = _linha(_n("r1"))
    assert (l["usina_id"], l["usina_ligada_por"], l["tipo_falha"], l["os"]) == (1, "código cheio", "DESLIGAMENTO_USINA",
                                                                                "17001")
    assert (l["inicio"], l["normalizado_em"], l["fora_min"]) == ("2026-10-27T09:00:00-03:00",
                                                                 "2026-10-27T10:30:00-03:00", 90)
    assert (l["data_id_inicio"], l["data_id_volta"], l["normalizada"], l["hora_real"]) == (20261027, 20261027, 1, 1)
    assert (l["protecoes"], l["geracao_parou"], l["equipamentos_codigos"], l["equipamentos_qtd"]) == ("27ABC;86", "",
                                                                                                    "", 0)


def test_o_dia_e_o_de_brasilia():
    # 02:30Z é o dia anterior em Brasília (regra 7)
    l = _linha(_n("r1", inicio="2026-10-28T02:30:00Z", normalizado_em="2026-10-28T04:00:00Z"))
    assert (l["data_id_inicio"], l["data_id_volta"]) == (20261027, 20261028)
    assert l["inicio"] == "2026-10-27T23:30:00-03:00"


def test_codigo_de_duas_usinas_ou_fora_do_cadastro_nao_liga():
    assert _linha(_n("r1", usina_codigo="CCC300"))["usina_id"] == ""
    sem = _linha(_n("r2", usina_codigo="TSTE-ZZZ900"))
    assert sem["usina_id"] == "" and sem["usina_ligada_por"] == "" and sem["usina_codigo"] == "TSTE-ZZZ900"


def test_comunicacao_com_e_sem_a_geracao_parada_e_os_equipamentos():
    l = _linha(_n("r1", tipo_falha="FALHA_COMUNICACAO", geracao_parou=True, protecoes=[],
                  equipamentos=[{"codigo": "TSTE-AAA100-CABN2", "nome": "Cabine 2"},
                                {"codigo": "tste-aaa100-cabn 3", "nome": "Cabine 3"}]))
    assert (l["geracao_parou"], l["protecoes"], l["equipamentos_codigos"], l["equipamentos_qtd"]) == (
        1, "", "TSTE-AAA100-CABN2;TSTE-AAA100-CABN3", 2)
    assert _linha(_n("r2", tipo_falha="FALHA_COMUNICACAO", geracao_parou=False))["geracao_parou"] == 0


def test_desfeita_e_sem_hora_real_ficam_marcadas():
    l = _linha(_n("r1", normalizada=False, hora_real=False, normalizado_em=None, fora_min=None))
    assert (l["normalizada"], l["hora_real"], l["normalizado_em"], l["data_id_volta"], l["fora_min"]) == (0, 0, "", "",
                                                                                                        "")


def test_protecao_so_em_codigo_curto_sem_repetir():
    assert NB.protecoes(["27abc", "86", "86", "78/81", "Religada remotamente as 15:43 com trip", ""]) == "27ABC;86;78/81"


def test_nenhum_nome_nem_texto_livre_no_fato():
    l = _linha(_n("r1"))
    valores = " ".join(str(v) for v in l.values())
    for proibido in ("Fulana", "Beltrano", "texto livre", "relato", "Usina Teste"):
        assert proibido not in valores
    assert not {"tecnico", "os_aberta_por", "impacto", "detalhes", "informe", "usina"} & set(NB.CAB)


def test_fato_ordenado_pelo_registro_e_conta_as_ligadas():
    linhas, rel = NB.fato([_n("r2"), _n("r1", usina_codigo="TSTE-ZZZ900"), {"sem": "registro"}], USINAS)
    assert [l[0] for l in linhas] == ["r1", "r2"]
    assert rel == {"linhas": 2, "ligadas": 1, "sem_usina": ["TSTE-ZZZ900"]}


# ── o laço que grava ────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def banco(app):
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="token-de-teste")
    livros.publicar("cadastro_nexus", "cadastro", {"usinas": (("usina_id", "codigo", "excluido"),
                                                              [[u["usina_id"], u["codigo"], u["excluido"]]
                                                               for u in USINAS])},
                    base="http://pg.falso", token="token-de-teste", sessao=api)
    return api


def _leitura(itens, carregando=False):
    return AND.Leitura("", {"itens": itens, "carregando": carregando})


def test_grava_o_fato_e_a_atualizacao_e_mantem_o_que_a_memoria_nao_guarda(app, banco):
    antigo = dict(zip(NB.CAB, NB.linha(_n("r0", inicio="2026-09-20T09:00:00-03:00",
                                          normalizado_em="2026-09-20T11:00:00-03:00"), NB.EQ.IndiceUsinas(USINAS))))
    livros.publicar(NB.LIVRO, NB.NOME_LIVRO, {NB.ABA: (NB.CAB, [[antigo[c] for c in NB.CAB]])},
                    base="http://pg.falso", token="token-de-teste", sessao=banco)
    with app.app_context():
        rel = NB.publicar(app.config, banco, agora=AGORA, forcar=True,
                          leitura=_leitura([_n("r1"), _n("r2", usina_codigo="TSTE-BBB200")]))
    assert rel["gravado"] == {NB.ABA: 3, NB.ABA_ABERTAS: 0, "atualizacao": 1} and rel["antes_mantidas"] == 1
    assert [(r["registro"], r["usina_id"]) for r in banco.linhas(NB.LIVRO, NB.ABA)] == [("r0", 1), ("r1", 1), ("r2", 2)]
    a = banco.linhas(NB.LIVRO, "atualizacao")[0]
    assert (a["linhas_qtd"], a["desde"], a["ligadas_qtd"]) == (3, NO.inicio_da_guarda(AGORA).date().isoformat(), 3)


def test_a_mesma_normalizacao_que_muda_troca_a_linha(app, banco):
    with app.app_context():
        NB.publicar(app.config, banco, agora=AGORA, forcar=True, leitura=_leitura([_n("r1")]))
        NB.publicar(app.config, banco, agora=AGORA, forcar=True,
                    leitura=_leitura([_n("r1", normalizado_em="2026-10-27T11:00:00-03:00", fim_corrigido=True)]))
    gravadas = banco.linhas(NB.LIVRO, NB.ABA)
    assert len(gravadas) == 1 and gravadas[0]["normalizado_em"] == "2026-10-27T11:00:00-03:00"


def test_gravou_ha_menos_de_50_min_pula(app, banco, monkeypatch):
    monkeypatch.setattr(NB, "_ultima", lambda base, s: AGORA - timedelta(minutes=20))
    with app.app_context():
        assert "pulou" in NB.publicar(app.config, banco, agora=AGORA, leitura=_leitura([_n("r1")]))
    assert not banco.linhas(NB.LIVRO, NB.ABA)


def test_sem_token_ou_sem_cadastro_nao_grava(app, banco):
    app.config["GRIDCO_SQL_TOKEN"] = ""
    with app.app_context():
        assert "erro" in NB.publicar(app.config, banco, agora=AGORA, forcar=True, leitura=_leitura([_n("r1")]))
    app.config["GRIDCO_SQL_TOKEN"] = "token-de-teste"
    vazio = ApiPGFalsa()
    with app.app_context():
        assert "recusou" in NB.publicar(app.config, vazio, agora=AGORA, forcar=True, leitura=_leitura([_n("r1")]))
    assert not vazio.linhas(NB.LIVRO, NB.ABA)


def test_memoria_pela_metade_ou_velha_nao_grava(app, monkeypatch):
    monkeypatch.setattr(NO, "ler", lambda config, agora=None: _leitura([_n("r1")], carregando=True))
    leitura, motivo = NB.memoria_completa(app.config, AGORA, espera_s=0)
    assert leitura is None and "não terminou" in motivo
    monkeypatch.setattr(NO, "ler", lambda config, agora=None: AND.Leitura("", {"itens": [], "carregando": False},
                                                                           erro="o Andamento recusou", velha=True))
    leitura, motivo = NB.memoria_completa(app.config, AGORA, espera_s=0)
    assert leitura is None and "velha" in motivo


def test_sem_a_fonte_do_andamento_so_pula(app):
    with app.app_context():
        assert "pulou" in NB.publicar(app.config, ApiPGFalsa(), agora=AGORA)


def test_o_laco_nao_liga_desligado(app, monkeypatch):
    app.config["NEXUS_NORMALIZACOES_PUBLICAR"] = "0"
    monkeypatch.setitem(NB._LACO, "thread", None)
    NB.ligar(app)
    assert NB._LACO["thread"] is None


def test_catalogo_bate_com_o_modulo():
    f = catalogo.POR_ID["normalizacao"]
    assert f.conformado_em == f"{NB.LIVRO} · {NB.ABA}" and f.chave == NB.CHAVE and f.tipo == NB.TIPO
    assert f.grao == NB.GRAO and {(m.coluna, m.unidade, m.soma) for m in f.medidas} == set(NB.MEDIDAS)
    assert catalogo.LIVRO_POR_NOME[NB.LIVRO].abas == (NB.ABA, NB.ABA_ABERTAS, "atualizacao")
    a = catalogo.POR_ID["ocorrencia_aberta"]
    assert a.conformado_em == f"{NB.LIVRO} · {NB.ABA_ABERTAS}" and a.chave == NB.CHAVE and a.tipo == NB.TIPO_ABERTAS
    assert a.grao == NB.GRAO_ABERTAS and {(m.coluna, m.unidade, m.soma) for m in a.medidas} == set(NB.MEDIDAS_ABERTAS)


# ── as ocorrências ainda abertas (30/10/2026) ──────────────────────────────────────────────────────────────────────────
def _oc(registro, **kw):
    """Uma ocorrência aberta como a fotografia do Andamento manda (o tipo pelo rótulo, os nomes dos equipamentos)."""
    o = {"os": "16958", "registro": registro, "severidade": "Médio", "severidade_classe": "medio",
         "tipo_tarefa": "Corretiva", "tipo_falha": "Desligamento de inversor", "problema": "inv",
         "equipamentos": ["Inversor 2.7"], "falha": "Inversor sem gerar, relato do time", "impacto": "texto livre",
         "protecao": None, "abertura": "2026-07-12T08:00:00-03:00", "dias_aberta": 110, "etapa": "Aguardando peça",
         "aguardando": ["peça"], "ultima_nota": {"quando": "2026-10-29T10:00:00-03:00", "texto": "nota do time"}}
    o.update(kw)
    return o


def _foto(*por_usina):
    return {"usinas": [{"id": i, "codigo": cod, "nome": "Usina Teste", "ocorrencias": list(ocs)}
                       for i, (cod, ocs) in enumerate(por_usina)]}


def test_aberta_com_o_codigo_do_tipo_pelas_normalizacoes_e_a_usina_pelo_codigo():
    linhas, rel = NB.abertas(_foto(("TSTE-AAA100", [_oc("a1")])), [], [_n("r1", tipo_falha="DESLIGAMENTO_INVERSOR",
                                                                         tipo_falha_rotulo="Desligamento de inversor")],
                             USINAS)
    l = dict(zip(NB.CAB_ABERTA, linhas[0]))
    assert (l["registro"], l["os"], l["cliente"], l["usina_id"], l["usina_ligada_por"]) == ("a1", "16958", "THOPEN", 1,
                                                                                            "código cheio")
    assert (l["tipo_falha"], l["etapa"], l["dias_aberta_qtd"], l["inicio"], l["data_id_inicio"]) == (
        "DESLIGAMENTO_INVERSOR", "Aguardando peça", 110, "2026-07-12T08:00:00-03:00", 20260712)
    # sem a tag na fotografia nem na rota de 30 dias: a régua conta pelo tipo, e a aba diz que veio sem
    assert (l["equipamentos_codigos"], l["equipamentos_qtd"], l["equipamentos_de"]) == ("", 0, "")
    assert rel == {"abertas": 1, "abertas_ligadas": 1, "abertas_ja_normalizadas": 0,
                   "abertas_equipamentos_de": {"sem": 1}}


def test_aberta_completa_pela_rota_de_30_dias_e_o_rotulo_sem_normalizacao_vira_codigo():
    extra = {"registro": "a1", "ativos": ["tste-aaa100-invr2.7"], "tipo_falha_codigo": "INVERSOR_OFFLINE",
             "inicio": "2026-10-28T02:30:00Z", "protecoes": ["59C"]}
    l = dict(zip(NB.CAB_ABERTA, NB.abertas(_foto(("TSTE-AAA100", [_oc("a1", protecao="27")])), [extra], [],
                                           USINAS)[0][0]))
    assert (l["equipamentos_codigos"], l["equipamentos_de"], l["tipo_falha"]) == ("TSTE-AAA100-INVR2.7", "ocorrencias",
                                                                                  "INVERSOR_OFFLINE")
    # o início da falha é o da rota de 30 dias (o dia de Brasília), e as proteções das duas, sem repetir
    assert (l["inicio"], l["data_id_inicio"], l["protecoes"]) == ("2026-10-27T23:30:00-03:00", 20261027, "27;59C")
    # a tag da própria fotografia vence; o rótulo que nenhuma normalização trouxe vira código pelo texto
    l = dict(zip(NB.CAB_ABERTA, NB.abertas(_foto(("TSTE-AAA100", [_oc("a2", ativos=["TSTE-AAA100-CABN1"],
                                                                      tipo_falha="Desligamento de cabine")])),
                                           [], [], USINAS)[0][0]))
    assert (l["equipamentos_codigos"], l["equipamentos_de"], l["tipo_falha"]) == ("TSTE-AAA100-CABN1", "fotografia",
                                                                                  "DESLIGAMENTO_DE_CABINE")


def test_aberta_ja_normalizada_sai_e_a_sem_os_fica_sem_o_codigo_interno():
    foto = _foto(("TSTE-AAA100", [_oc("r1"), _oc("a2", os="R-abc123"), _oc("a2"), {"sem": "registro"}]),
                 ("TSTE-ZZZ900", [_oc("a3")]))
    linhas, rel = NB.abertas(foto, [], [_n("r1")], USINAS)
    assert [(l[0], l[1], l[4]) for l in linhas] == [("a2", "", 1), ("a3", "16958", "")]
    assert (rel["abertas"], rel["abertas_ligadas"], rel["abertas_ja_normalizadas"]) == (2, 1, 1)
    # a normalização desfeita reabre: a ocorrência aberta conta
    assert [l[0] for l in NB.abertas(foto, [], [_n("r1", normalizada=False)], USINAS)[0]] == ["a2", "a3", "r1"]


def test_aberta_sem_nome_nem_texto_livre():
    l = dict(zip(NB.CAB_ABERTA, NB.abertas(_foto(("TSTE-AAA100", [_oc("a1")])), [], [], USINAS)[0][0]))
    valores = " ".join(str(v) for v in l.values())
    for proibido in ("relato", "texto livre", "nota do time", "Usina Teste", "Inversor 2.7"):
        assert proibido not in valores
    assert not {"falha", "impacto", "ultima_nota", "aguardando", "equipamentos", "usina"} & set(NB.CAB_ABERTA)


def test_grava_as_abertas_e_na_falha_da_fotografia_o_retrato_de_antes_fica(app, banco):
    ab = NB.abertas(_foto(("TSTE-AAA100", [_oc("a1")])), [], [], USINAS)
    with app.app_context():
        rel = NB.publicar(app.config, banco, agora=AGORA, forcar=True, leitura=_leitura([_n("r1")]),
                          abertas_lidas=(ab[0], "2026-10-29T15:21:00-03:00", ab[1]))
    assert rel["gravado"] == {NB.ABA: 1, NB.ABA_ABERTAS: 1, "atualizacao": 1}
    a = banco.linhas(NB.LIVRO, "atualizacao")[0]
    assert (a["abertas_em"], a["abertas_qtd"]) == ("2026-10-29T15:21:00-03:00", 1)
    with app.app_context():
        rel = NB.publicar(app.config, banco, agora=AGORA + timedelta(hours=1), forcar=True,
                          leitura=_leitura([_n("r1")]), abertas_lidas=(None, "", {"abertas_mantidas": "caiu"}))
    assert rel["abertas_mantidas"] == "caiu" and [r["registro"] for r in banco.linhas(NB.LIVRO, NB.ABA_ABERTAS)] == ["a1"]
    a = banco.linhas(NB.LIVRO, "atualizacao")[0]
    assert (a["abertas_em"], a["abertas_qtd"]) == ("2026-10-29T15:21:00-03:00", 1)


def test_ler_abertas_pela_fotografia_e_a_rota_de_30_dias(app, monkeypatch):
    pedidos = []
    monkeypatch.setattr(AND, "ler", lambda config, cliente: pedidos.append(cliente) or AND.Leitura(
        cliente, _foto(("TSTE-AAA100", [_oc("a1")])), lido_em=AGORA.timestamp()))
    monkeypatch.setattr(AND, "ler_ocorrencias", lambda config, cliente, dias: pedidos.append((cliente, dias)) or
                        AND.Leitura(cliente, None, erro="caiu"))
    linhas, em, rel = NB.ler_abertas(app.config, [], USINAS, AGORA)
    assert pedidos == ["Thopen", ("Thopen", 30)] and len(linhas) == 1 and em == "2026-10-29T15:22:00-03:00"
    assert rel["abertas_sem_complemento"] == "caiu"
    monkeypatch.setattr(AND, "ler", lambda config, cliente: AND.Leitura(cliente, {"usinas": []}, erro="x", velha=True))
    assert NB.ler_abertas(app.config, [], USINAS, AGORA)[0] is None
