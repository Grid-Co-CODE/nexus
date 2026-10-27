"""A Zeladoria no banco para o dashboard do cliente (26/10/2026, Levi: "agora faz a mesma tela no dashboard do cliente";
o Nexus publica a visão pronta e o 5080 só mostra): a visão usina × semana (`zeladoria.visao_do_banco`), o laço que
grava (`zeladoria_banco`) com o banco falso, as recusas (checklist velho, OS de zeladoria ausentes, grão) e o catálogo."""
from datetime import date, datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.campo import aprovacao, regras_app, ronda_checklist
from nexus.campo import zeladoria as Z
from nexus.campo import zeladoria_banco as ZB
from nexus.dados import catalogo
from nexus.dados.fatos import tarefa_chave

HOJE = date(2026, 10, 26)
AGORA = datetime(2026, 10, 26, 18, 32, tzinfo=timezone(timedelta(hours=-3)))
LIMPEZA = tarefa_chave("Acompanhamento - Limpeza de Módulos (Termografia se aplicável)")
SUPRESSAO = tarefa_chave("Acompanhamento - Supressão Vegetal")


def _ronda(uid, dia, os_=None, checklist=None, fim="10:00", tecnico="Fulano Souza"):
    return {"usina_id": uid, "data": dia, "fim": f"{dia}T{fim}:00", "os": os_, "checklist": checklist,
            "tecnico": tecnico, "tipo": "curta", "avulsa": False}


def _resp(suj, veg, vala="Limpa"):
    return {"sujidade": suj, "vegetacao": veg, "vala": vala, "sombreamento": "", "dejeto": "", "sensores_sujos": []}


def _tarefa(uid, os_, chave, status_os, estado, prog=None, fim=None):
    d = lambda iso: int(iso.replace("-", "")) if iso else None      # noqa: E731
    return {"usina_id": uid, "os": os_, "fracttal_os_id": 9000 + os_, "tarefa_chave": chave, "tipo_tarefa": "zeladoria",
            "status_os": status_os, "estado_tarefa": estado, "data_id_programada": d(prog), "data_id_fim": d(fim)}


def _dados(tarefas=None):
    cobertura = [{"usina_id": 1, "usina": "Altair", "cliente": "Thopen"}, {"usina_id": 2, "usina": "Brodowski 1",
                                                                          "cliente": "Thopen"}]
    todas = [_ronda(1, "2026-10-14", os_="500"), _ronda(1, "2026-10-16", os_="501", fim="11:00"),
             _ronda(1, "2026-10-21", os_="502"), _ronda(2, "2026-10-26", checklist=_resp(1, 1, "Suja")),
             _ronda(1, "2026-07-01", os_="503")]                       # antes das 12 semanas: fica fora
    resp = {"500": _resp(2, 5), "501": _resp(3, 4, "Obstruída"), "502": _resp(4, 2, "Não se aplica"),
            "503": _resp(5, 5)}
    return {"todas": todas, "cobertura": cobertura, "validacoes": [], "respostas": resp, "checklist_ate": "2026-10-26",
            "tarefas": tarefas if tarefas is not None else [
                _tarefa(1, 20, SUPRESSAO, "em_verificacao", "finalizada", "2026-10-17", "2026-10-19"),
                _tarefa(1, 21, LIMPEZA, "em_processo", "nao_iniciada", "2026-10-30")]}


def _por_semana(linhas):
    return {(l[2], l[0]): dict(zip(Z.CAB_BANCO, l)) for l in linhas}


# ── a visão ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_visao_usina_por_semana_com_a_leitura_e_a_recomendacao_da_semana():
    d = _dados()
    linhas, rel = Z.visao_do_banco(d["todas"], d["cobertura"], d["respostas"], d["validacoes"], d["tarefas"], HOJE)
    assert Z.SEMANAS_NO_BANCO == 12 and len(Z.CAB_BANCO) == 20
    v = _por_semana(linhas)
    assert set(v) == {(1, "2026-W42"), (1, "2026-W43"), (2, "2026-W44")}     # só usina × semana com leitura
    assert (rel["usinas"], rel["linhas"], rel["vala_fora"]) == (2, 3, 1)
    w42 = v[(1, "2026-W42")]
    # duas leituras na semana: vale a última (16/10: vegetação 4, sujidade 3), com a OS e a data dela
    assert (w42["vegetacao_nivel"], w42["sujidade_nivel"], w42["leituras_qtd"]) == (4, 3, 2)
    assert (w42["data_id_semana"], w42["data_id_leitura"], w42["os"], w42["vala"]) == (20261012, 20261016, 501,
                                                                                        "Obstruída")
    # vegetação 4: supressão vegetal em até 7 dias; a supressão de 19/10 veio depois da leitura = feita
    assert w42["recomendacao"] == "supressao_vegetal"
    assert (w42["situacao_vegetacao"], w42["data_id_prazo_vegetacao"], w42["data_id_situacao_vegetacao"],
            w42["os_zeladoria_vegetacao"]) == ("feita", 20261023, 20261019, 20)
    assert w42["situacao_sujidade"] is None and w42["data_id_prazo_sujidade"] is None
    # a última supressão é a de ATÉ o fim da semana: a de 19/10 não está na W42 (fim em 18/10), está na W43
    assert w42["data_id_ultima_supressao"] is None and w42["data_id_ultima_limpeza"] is None
    assert v[(1, "2026-W43")]["data_id_ultima_supressao"] == 20261019
    w43 = v[(1, "2026-W43")]
    # sujidade 4 em 21/10: limpeza de módulos, programada para 30/10 (a OS 21 aberta)
    assert (w43["recomendacao"], w43["situacao_sujidade"], w43["data_id_situacao_sujidade"],
            w43["os_zeladoria_sujidade"], w43["data_id_prazo_sujidade"]) == (
        "limpeza_modulos", "programada", 20261030, 21, 20261028)
    assert w43["vala"] == "Não se aplica"
    # a avulsa sem OS: sem OS de ronda; o "Suja" do formulário antigo não é do domínio: vazio e conta
    w44 = v[(2, "2026-W44")]
    assert (w44["os"], w44["vala"], w44["recomendacao"]) == (None, None, None)


def test_visao_sem_nome_e_so_com_codigos_do_dominio():
    d = _dados()
    linhas, _ = Z.visao_do_banco(d["todas"], d["cobertura"], d["respostas"], d["validacoes"], d["tarefas"], HOJE)
    texto = {c: {l[i] for l in linhas if isinstance(l[i], str)} for i, c in enumerate(Z.CAB_BANCO)}
    assert not any("Fulano" in str(x) for l in linhas for x in l)                          # regra 8: nenhum nome
    assert {c for c, v in texto.items() if v} <= {"semana", "vala", "recomendacao", "situacao_vegetacao",
                                                  "situacao_sujidade"}
    assert texto["vala"] <= {"Limpa", "Parcial", "Obstruída", "Não se aplica"}
    assert texto["situacao_vegetacao"] | texto["situacao_sujidade"] <= set(Z.SITUACAO_NO_BANCO.values())
    # sem as OS de zeladoria, a situação é "sem dado", nunca "a programar"
    sem, _ = Z.visao_do_banco(d["todas"], d["cobertura"], d["respostas"], d["validacoes"], [], HOJE)
    assert {r["situacao_vegetacao"] for r in _por_semana(sem).values() if r["situacao_vegetacao"]} == {"sem_dado"}


# ── o laço que grava ────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def banco(app):
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="token-de-teste")
    return api


def test_grava_a_visao_e_a_atualizacao_e_confere(app, banco):
    with app.app_context():
        rel = ZB.publicar(app.config, banco, agora=AGORA, dados=_dados(), conferir_checklist=False)
    assert rel["gravado"] == {ZB.ABA: 3, "atualizacao": 1}
    gravadas = banco.linhas(ZB.LIVRO, ZB.ABA)
    assert [(r["usina_id"], r["semana"]) for r in gravadas] == [(1, "2026-W42"), (1, "2026-W43"), (2, "2026-W44")]
    a = banco.linhas(ZB.LIVRO, "atualizacao")[0]
    assert (a["semana_corrente"], a["semanas_qtd"], a["linhas_qtd"], a["usinas_qtd"], a["checklist_ate"]) == (
        "2026-W44", 12, 3, 2, "2026-10-26")



def test_gravou_ha_menos_de_50_min_ou_durante_a_conta_pula(app, banco, monkeypatch):
    monkeypatch.setattr(ZB, "_ultima", lambda base, s: AGORA - timedelta(minutes=20))
    with app.app_context():
        assert "pulou" in ZB.publicar(app.config, banco, agora=AGORA, dados=_dados(), conferir_checklist=False)
    vezes = []

    def ultima(base, s):        # a outra volta gravou enquanto esta fazia a conta: confere de novo antes de gravar
        vezes.append(1)
        return None if len(vezes) == 1 else AGORA + timedelta(minutes=1)
    monkeypatch.setattr(ZB, "_ultima", ultima)
    with app.app_context():
        rel = ZB.publicar(app.config, banco, agora=AGORA, dados=_dados(), conferir_checklist=False)
    assert "pulou" in rel and banco.syncs == 0 and len(vezes) == 2


def test_sem_as_os_de_zeladoria_ou_sem_o_token_nao_grava(app, banco):
    with app.app_context():
        rel = ZB.publicar(app.config, banco, agora=AGORA, dados=_dados(tarefas=[]), conferir_checklist=False)
    assert "recusou" in rel and "nexus_os" in rel["recusou"] and not banco.linhas(ZB.LIVRO, ZB.ABA)
    app.config["GRIDCO_SQL_TOKEN"] = ""
    with app.app_context():
        assert "erro" in ZB.publicar(app.config, banco, agora=AGORA, dados=_dados(), conferir_checklist=False)


def test_checklist_velho_nao_grava_e_pede_a_releitura(app, banco, monkeypatch):
    pedidos = []
    monkeypatch.setattr(ronda_checklist, "pedir_releitura", lambda app=None: pedidos.append("aprovadas"))
    monkeypatch.setattr(aprovacao, "_pedir_releitura", lambda: pedidos.append("fila"))
    agora_s = AGORA.timestamp()
    ronda_checklist.limpar()
    try:
        with app.app_context():
            # nunca lido por inteiro nesta máquina
            assert "ainda não foi completa" in ZB.checklist_novo(agora_s)
            ronda_checklist._APROVADAS.update(ate="2026-10-26", ts=agora_s - 4 * 3600, erro="HTTP 429")
            assert "há mais de 3 h" in ZB.checklist_novo(agora_s) and "429" in ZB.checklist_novo(agora_s)
            ronda_checklist._APROVADAS.update(ts=agora_s - 600, erro="")
            regras_app._FILA_CACHE["t"] = agora_s - 7 * 3600            # a fila da Aprovação velha: pede e não grava
            assert "pedi a releitura" in ZB.checklist_novo(agora_s) and "fila" in pedidos
            regras_app._FILA_CACHE["t"] = agora_s - 3600
            assert ZB.checklist_novo(agora_s) == ""
            assert "aprovadas" in pedidos                             # toda volta pede a releitura das aprovadas
            ronda_checklist._APROVADAS.update(ts=0.0)
            rel = ZB.publicar(app.config, banco, agora=AGORA, dados=_dados())
        assert "recusou" in rel and not banco.linhas(ZB.LIVRO, ZB.ABA)
    finally:
        ronda_checklist.limpar()
        regras_app._FILA_CACHE.pop("t", None)


def test_o_laco_nao_liga_no_pc_nem_desligado(app, monkeypatch):
    ligados = []
    monkeypatch.setattr(ZB.threading, "Thread", lambda *a, **k: ligados.append(k) or type(
        "T", (), {"start": lambda self: None})())
    monkeypatch.setitem(ZB._LACO, "thread", None)
    for chave in ("NEXUS_CAMPO_AQUECER", "NEXUS_ZELADORIA_PUBLICAR"):
        app.config.update({"NEXUS_CAMPO_AQUECER": "1", "NEXUS_ZELADORIA_PUBLICAR": "1", chave: "0"})
        ZB.ligar(app)
        assert not ligados, chave
    app.config.update(NEXUS_CAMPO_AQUECER="1", NEXUS_ZELADORIA_PUBLICAR="1")
    ZB.ligar(app)
    assert ligados and ligados[0]["name"] == "nexus-zeladoria-banco"


# ── o catálogo ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_livro_registrado_antes_de_existir_e_a_visao_fora_da_regra_com_motivo():
    livro = catalogo.LIVRO_POR_NOME[ZB.LIVRO]
    assert livro.abas == (ZB.ABA, "atualizacao") and not livro.so_cresce
    assert ZB.ABA in catalogo.ABAS_FORA_DA_REGRA and catalogo.aba_segue_a_regra(ZB.ABA)
    assert "NEXUS_ZELADORIA_PUBLICAR" in livro.quem_grava
    # nasceu na 1ª volta do servidor (27/10/2026 08:48, 687 linhas), conferida por GET
    assert livro.no_banco


def test_checklist_ate_nao_passa_de_hoje(app, banco):
    """A 1ª gravação disse checklist_ate = 28/10 num 27/10 (OS aprovada com a data de fim adiante no Fracttal)."""
    d = dict(_dados(), checklist_ate="2026-10-28")
    with app.app_context():
        ZB.publicar(app.config, banco, agora=AGORA, dados=d, conferir_checklist=False)
    assert banco.linhas(ZB.LIVRO, "atualizacao")[0]["checklist_ate"] == "2026-10-26"
