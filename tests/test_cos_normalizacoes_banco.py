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



def test_o_relato_ao_cliente_entra_e_o_texto_livre_continua_fora():
    """09/11/2026: o relato que a Ronda COS monta por regras (sem copiar as notas) vai ao fato, para o Comentário do dia
    na Plataforma; o texto livre do time (impacto, detalhes, informe) segue fora. Sem o relato (o Andamento de antes),
    a coluna fica vazia."""
    relato = "Usina desligada de 27/10 às 09:00 a 27/10 às 10:30 (1 h 30 min). A usina voltou a gerar em 27/10 às 10:30."
    continua = "Continuação: Usina desligada de 27/10 às 09:00 a 27/10 às 10:30."
    l = _linha(_n("r1", relato_cliente=relato, relato_continuacao=continua))
    assert l["relato_cliente"] == relato and l["relato_continuacao"] == continua
    assert "texto livre" not in " ".join(str(v) for v in l.values())
    assert _linha(_n("r2"))["relato_cliente"] == "" and _linha(_n("r2"))["relato_continuacao"] == ""

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
    assert rel["gravado"] == {NB.ABA: 3, NB.ABA_ABERTAS: 0, NB.ABA_COMENTARIOS: 0, "atualizacao": 1}
    assert rel["antes_mantidas"] == 1
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
    assert catalogo.LIVRO_POR_NOME[NB.LIVRO].abas == (NB.ABA, NB.ABA_ABERTAS, NB.ABA_COMENTARIOS, "atualizacao")
    c = catalogo.POR_ID["comentario_dia"]
    assert c.conformado_em == f"{NB.LIVRO} · {NB.ABA_COMENTARIOS}" and c.tipo == NB.TIPO_COMENTARIOS
    assert c.grao == NB.GRAO_COMENTARIOS and c.chave == ("usina_codigo", "data_id")
    a = catalogo.POR_ID["ocorrencia_aberta"]
    assert a.conformado_em == f"{NB.LIVRO} · {NB.ABA_ABERTAS}" and a.chave == NB.CHAVE and a.tipo == NB.TIPO_ABERTAS
    assert a.grao == NB.GRAO_ABERTAS and {(m.coluna, m.unidade, m.soma) for m in a.medidas} == set(NB.MEDIDAS_ABERTAS)


# ── o pedido do Atualizar do Dashboard Thopen (03/11/2026) ─────────────────────────────────────────────────────────────
BRT = timezone(timedelta(hours=-3))


def test_o_pedido_do_atualizar_so_vale_depois_da_ultima_gravacao():
    # Levi, 03/11/2026: "sinto falta do botão 'Atualizar' (...) fiz umas alterações nas normalizações e precisava trazer"
    ped = [{"pedido_em": "2026-11-03T15:40:00-03:00"}, {"pedido_em": "2026-11-03T15:10:00-03:00"}, {"pedido_em": "x"}]
    ultima = datetime(2026, 11, 3, 15, 29, tzinfo=BRT)
    assert NB.pedido_a_atender(ped, ultima, None) == datetime(2026, 11, 3, 15, 40, tzinfo=BRT)
    assert NB.pedido_a_atender(ped, datetime(2026, 11, 3, 15, 41, tzinfo=BRT), None) is None   # a volta da hora levou
    assert NB.pedido_a_atender(ped, ultima, datetime(2026, 11, 3, 15, 40, tzinfo=BRT)) is None  # já gravado
    assert NB.pedido_a_atender([{"pedido_em": ""}], ultima, None) is None and NB.pedido_a_atender([], None, None) is None


def test_o_pedido_le_o_livro_so_quando_a_versao_muda_e_respeita_o_intervalo(app, monkeypatch):
    for k in ("pedido_visto", "pedido_feito", "pedida_em"):
        monkeypatch.setitem(NB._LACO, k, None)
    versao, leituras = ["v1"], []
    monkeypatch.setattr(livros, "atualizado_em", lambda base, s, livro: versao[0] if livro == NB.PEDIDO_LIVRO else None)
    monkeypatch.setattr(livros, "ler", lambda base, s, livro, aba=None: leituras.append((livro, aba)) or [
        {"pedido_em": "2026-11-03T15:40:00-03:00"}])
    assert NB._pedido(app.config, None, 1000.0) is None and not leituras        # sem a fonte do Andamento (o PC): nada
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.teste", NEXUS_COS_ANDAMENTO_CHAVE="k")
    monkeypatch.setattr(NB, "_ultima", lambda base, s: datetime(2026, 11, 3, 15, 41, tzinfo=BRT))
    assert NB._pedido(app.config, None, 1000.0) is None and leituras == [(NB.PEDIDO_LIVRO, NB.PEDIDO_ABA)]
    assert NB._pedido(app.config, None, 1060.0) is None and len(leituras) == 1    # a mesma versão: não relê
    versao[0] = "v2"
    monkeypatch.setattr(NB, "_ultima", lambda base, s: datetime(2026, 11, 3, 15, 29, tzinfo=BRT))
    assert NB._pedido(app.config, None, 1120.0) == datetime(2026, 11, 3, 15, 40, tzinfo=BRT)
    NB._LACO["pedida_em"] = 1120.0
    versao[0] = "v3"
    assert NB._pedido(app.config, None, 1180.0) is None and len(leituras) == 2    # 2 min entre duas voltas pedidas
    c = catalogo.conhecida(NB.PEDIDO_LIVRO, NB.PEDIDO_ABA)
    assert c and c.papel == "controle"
    from nexus.dados import telas
    assert ("igual", NB.PEDIDO_LIVRO, "Dashboard Thopen (5080)") in telas.QUEM_GRAVA_ORIGEM


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
    # sem a tag na fotografia nem na rota de 30 dias: a referência do que o COS cita ("Inversor 2.7"), sem o nome
    assert (l["equipamentos_codigos"], l["equipamentos_qtd"], l["equipamentos_de"]) == ("", 0, "")
    assert l["equipamentos_citados"] == "INV2.7"
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


def test_grava_as_abertas_e_na_falha_da_fotografia_o_retrato_de_antes_fica(app, banco, monkeypatch):
    monkeypatch.setattr(NB, "COMENTARIOS_SO_DAS_USINAS", frozenset({"TSTE-AAA100"}))
    ab = NB.abertas(_foto(("TSTE-AAA100", [_oc("a1")])), [], [], USINAS)
    with app.app_context():
        rel = NB.publicar(app.config, banco, agora=AGORA, forcar=True, leitura=_leitura([_n("r1")]),
                          abertas_lidas=(ab[0], "2026-10-29T15:21:00-03:00", ab[1]))
    # a aberta desde 12/07 NÃO vira comentário (09/11/2026: repetida em todo dia, o dono mandou tirar), nem na usina liberada
    assert rel["gravado"] == {NB.ABA: 1, NB.ABA_ABERTAS: 1, NB.ABA_COMENTARIOS: 0, "atualizacao": 1}
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


def test_os_equipamentos_citados_pelo_nome_viram_referencia_curta():
    assert NB.citados(["Inversor 2.7", "inv 1.10", "Cabine 2", "SKID 3", "QGBT 1", "Inversor 2.7", "Relé 1"]) == (
        "INV2.7;INV1.10;CAB2;CAB3;CAB1")
    assert NB.citados(None) == "" and NB.citados(["Datalogger"]) == ""


# --- o comentário de cada dia para a Plataforma de Performance (09/11/2026) -------------------------------------------

DESDE = datetime(2026, 10, 1, tzinfo=NB._BRT)
AGORA_DIA = datetime(2026, 11, 9, 12, 0, tzinfo=NB._BRT)
REL = "Cabine 1 desligada de 25/10 às 12:41 a 27/10 às 11:25 (1 dia e 22 h). A Cabine 1 voltou a gerar em 27/10 às 11:25."
CONT = "Continuação: Cabine 1 desligada de 25/10 às 12:41 a 27/10 às 11:25."


def _fato(*ns):
    idx = NB.EQ.IndiceUsinas(USINAS)
    return [NB.linha(n, idx) for n in ns]


def _por_dia(linhas):
    return {r["dia"]: r for r in (dict(zip(NB.CAB_COMENTARIO, l)) for l in linhas)}


def test_o_relato_no_primeiro_dia_e_a_continuacao_nos_seguintes():
    """A ocorrência de 25/10 12:41 a 27/10 11:25: o relato inteiro em 25/10, a linha curta em 26 e 27/10."""
    linhas = NB.comentarios_do_dia(_fato(_n("r1", os="17470", inicio="2026-10-25T12:41:00-03:00",
                                             normalizado_em="2026-10-27T11:25:00-03:00", relato_cliente=REL,
                                             relato_continuacao=CONT)), [], AGORA_DIA, DESDE)
    d = _por_dia(linhas)
    assert list(d) == ["2026-10-25", "2026-10-26", "2026-10-27"]
    assert d["2026-10-25"]["relato_do_dia"] == REL and d["2026-10-26"]["relato_do_dia"] == CONT
    assert d["2026-10-27"]["relato_do_dia"] == CONT
    assert (d["2026-10-25"]["usina_codigo"], d["2026-10-25"]["usina_id"], d["2026-10-25"]["data_id"]) == \
        ("TSTE-AAA100", 1, 20261025)
    assert (d["2026-10-26"]["registros"], d["2026-10-26"]["os"], d["2026-10-26"]["ocorrencias_qtd"]) == ("r1", "17470", 1)


def test_a_parada_da_noite_nao_explica_o_dia():
    """De 07/10 19:27 a 08/10 07:40 (a OS 15789 de Primavera): só 08/10 tem sol parado."""
    linhas = NB.comentarios_do_dia(_fato(_n("r1", inicio="2026-10-07T19:27:00-03:00",
                                             normalizado_em="2026-10-08T07:40:00-03:00", relato_cliente="Relato.",
                                             relato_continuacao="Continuação.")), [], AGORA_DIA, DESDE)
    d = _por_dia(linhas)
    assert list(d) == ["2026-10-08"] and d["2026-10-08"]["relato_do_dia"] == "Relato."


def test_duas_no_mesmo_dia_uma_por_linha_pela_hora_e_sem_relato_nao_entra():
    """O 25/10 da Aparecida: o fim da 17393 e o começo da 17470, na ordem; a normalizada sem relato fica de fora."""
    linhas = NB.comentarios_do_dia(_fato(
        _n("r2", os="17470", inicio="2026-10-25T12:41:00-03:00", normalizado_em="2026-10-27T11:25:00-03:00",
           relato_cliente="Segunda.", relato_continuacao="Segunda, continuação."),
        _n("r1", os="17393", inicio="2026-10-23T16:55:00-03:00", normalizado_em="2026-10-25T12:04:00-03:00",
           relato_cliente="Primeira.", relato_continuacao="Primeira, continuação."),
        _n("r3", os="17999", inicio="2026-10-25T09:00:00-03:00", normalizado_em="2026-10-25T10:00:00-03:00"),
    ), [], AGORA_DIA, DESDE)
    d = _por_dia(linhas)["2026-10-25"]
    assert d["relato_do_dia"] == "Primeira, continuação.\nSegunda."
    assert (d["registros"], d["os"], d["ocorrencias_qtd"]) == ("r1;r2", "17393;17470", 2)


def test_a_aberta_em_atendimento_com_o_equipamento_citado():
    """A aberta não tem relato (falta a volta): o evento, desde quando, e que segue em atendimento, até hoje."""
    aberta = dict.fromkeys(NB.CAB_ABERTA, "")
    aberta.update(registro="a1", os="18001", cliente="THOPEN", usina_codigo="TSTE-AAA100", usina_id=1,
                  tipo_falha="DESLIGAMENTO_CABINE", equipamentos_citados="CAB2", inicio="2026-11-08T10:15:00-03:00")
    linhas = NB.comentarios_do_dia([], [[aberta[c] for c in NB.CAB_ABERTA]], AGORA_DIA, DESDE)
    d = _por_dia(linhas)
    assert list(d) == ["2026-11-08", "2026-11-09"]
    assert d["2026-11-08"]["relato_do_dia"] == "Cabine 2 desligada desde 08/11 às 10:15, em atendimento pelo COS."
    assert d["2026-11-09"]["relato_do_dia"] == "Continuação: Cabine 2 desligada desde 08/11 às 10:15, em atendimento pelo COS."


def test_o_comentario_do_dia_so_da_aparecida_do_taboado(app, banco):
    """09/11/2026, o dono: "VOLTA TUDO AO NORMAL URGENTE" e "deixe somente as de aparecida do taboado". A outra usina
    fica sem linha (a Plataforma volta à dela); a Aparecida (ADT100) mantém o comentário; a aba continua no livro."""
    assert NB.COMENTARIOS_SO_DAS_USINAS == frozenset({"ADT100"})
    with app.app_context():
        rel = NB.publicar(app.config, banco, agora=AGORA, forcar=True,
                          leitura=_leitura([_n("r1", relato_cliente=REL, relato_continuacao=CONT),
                                            _n("r2", usina_codigo="ADT100", relato_cliente=REL, relato_continuacao=CONT)]))
    gravadas = banco.linhas(NB.LIVRO, NB.ABA_COMENTARIOS)
    assert [(g["usina_codigo"], g["dia"]) for g in gravadas] == [("ADT100", "2026-10-27")]
    assert rel["comentarios_dias"] == 1 and rel["gravado"][NB.ABA] == 2


def test_a_gravacao_leva_o_comentario_do_dia(app, banco, monkeypatch):
    monkeypatch.setattr(NB, "COMENTARIOS_SO_DAS_USINAS", frozenset({"TSTE-AAA100"}))
    with app.app_context():
        rel = NB.publicar(app.config, banco, agora=AGORA, forcar=True,
                          leitura=_leitura([_n("r1", relato_cliente=REL, relato_continuacao=CONT)]))
    gravadas = banco.linhas(NB.LIVRO, NB.ABA_COMENTARIOS)
    assert rel["comentarios_dias"] == len(gravadas) == 1
    assert (gravadas[0]["usina_codigo"], gravadas[0]["dia"], gravadas[0]["relato_do_dia"]) == ("TSTE-AAA100", "2026-10-27", REL)
