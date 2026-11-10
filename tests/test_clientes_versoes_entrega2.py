"""As versões do cliente, entrega 2 (09-10/11/2026, Levi pelo Scrum master: "pode dar o cartão verde para a visão do
cliente"): o Quadro da semana, os Extintores, o EPI e EPC, o Almoxarifado e os Laudos, cada um só nas usinas do cliente
da sessão e no mês do topo, só leitura, sem nome de técnico, custo, horas nem comentário interno.

O que estes testes seguram: a conta de cada versão (a função pura de `nexus/campo/versao_cliente.py`) recorta pelas
usinas do cliente, e a tela, logado como cliente, mostra só as dele, sem os campos da Grid, e as sub-rotas da tela da
Grid não abrem para ele."""
import json
from datetime import date, timedelta

import pytest
from test_campo_responsaveis import manut, tela  # noqa: F401  (fixtures)
from test_campo_visao import banco  # noqa: F401
from test_campo_visao_cliente_0511 import cliente_tela  # noqa: F401
from test_campo_visao import _dia
from test_hseq_epi import luvas  # noqa: F401  (fixture)
from test_hseq_extintores import com_cadastro, com_livro  # noqa: F401  (fixtures)
from test_pcm_almoxarifado import almox  # noqa: F401  (fixture)

from nexus.auth import clientes as CL
from nexus.auth import setor_telas as ST
from nexus.cadastro import setor_ids as SID
from nexus.campo import versao_cliente as VCL
from nexus.pcm import quadro as Q

EMAIL = "compras@cliente-exemplo.test"
SENHA = "senha do cliente 1"


@pytest.fixture
def dados(app, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    ST.limpar()
    yield app.config
    ST.limpar()


def _cliente(app, dados, telas):
    """O cliente 1 (Thopen: Altair e Brodowski 1) logado, com `telas` marcadas para o setor Clientes."""
    with app.test_request_context():
        ST.gravar(SID.CLIENTES, telas, ST.telas_do_cliente_possiveis(), dados, "http://pg.falso",
                  app.extensions["nexus_dados_sessao"], "admin@exemplo.test")
        _e, token = CL.adicionar(dados, EMAIL, 1, "Thopen", "admin@exemplo.test")
        CL.definir_senha(dados, token, SENHA, SENHA)
    ST.limpar()
    c = app.test_client()
    c.post("/entrar", data={"cliente_email": EMAIL, "cliente_senha": SENHA})
    return c


# ── Quadro da semana ─────────────────────────────────────────────────────────────────────────────────────────────────
def _semana(dia: date, rows: list[dict]) -> dict:
    a, s, _d = dia.isocalendar()
    return {"week": f"{a}-W{s:02d}", "rows": rows}


def _tarefa(os_id, usina, dia: date, status="Finalizados", tarefa="[Grid Co.] - MPM - Inversor", codigo="", tipo="MPM"):
    k = Q.DIAS[dia.weekday()]
    return {"os_id": os_id, "usina": usina, "cliente": "Thopen", "dia": f"{Q.NOMES_DIA[k]} ({dia:%d/%m})",
            "tarefa": tarefa, "codigo": codigo, "tipo": tipo, "status_bd": status, "responsavel": "Técnico Secreto",
            "resp_os": "Supervisor Secreto", "duracao": "3:00", "relatorio": "comentário interno da Grid",
            "h_ini": "08:00", "h_fim": "11:00", "cluster": "SP Norte"}


def test_o_quadro_do_cliente_conta_por_usina_e_por_os():
    hoje = date(2026, 11, 10)                       # terça; a semana passada também é de novembro
    seg_passada, seg = date(2026, 11, 2), date(2026, 11, 9)
    semanas = [
        _semana(seg_passada, [_tarefa("100", "Altair", seg_passada + timedelta(days=4), status="Não Iniciada"),
                              _tarefa("200", "Coração 1", seg_passada)]),
        # a OS 100 rolou para esta semana e foi feita; a 101 está por vir; a 102 foi pausada
        _semana(seg, [_tarefa("100", "Altair", seg + timedelta(days=1)),
                      _tarefa("101", "Brodowski 1", seg + timedelta(days=3), status="Não Iniciada", tipo="Corretiva"),
                      _tarefa("102", "Altair", seg, status="pausado"),
                      _tarefa("102", "Altair", seg, tarefa="[Grid Co.] - MPM - Trafo")]),
    ]
    ids = {"Altair": 1, "Brodowski 1": 2, "Coração 1": 3}
    r = VCL.quadro(semanas, ids.get, {1, 2}, date(2026, 11, 1), hoje, {1: "Altair", 2: "Brodowski 1"})
    assert (r["n"], r["feitas"], r["abertas"], r["usinas"]) == (3, 1, 2, 2)
    altair = next(u for u in r["linhas"] if u["usina"] == "Altair")
    oss = {o["os"]: o for o in altair["oss"]}
    # a tarefa que rolou conta uma vez, com o estado da semana mais nova
    assert oss["100"]["tarefas"] == 1 and oss["100"]["situacao"] == "concluída"
    assert oss["100"]["dia"] == date(2026, 11, 6) and oss["100"]["ate"] == date(2026, 11, 10)
    assert oss["102"]["situacao"] == "pausada" and oss["102"]["tarefas"] == 2
    brod = next(u for u in r["linhas"] if u["usina"] == "Brodowski 1")
    assert brod["oss"][0]["situacao"] == "programada" and brod["proxima"] == date(2026, 11, 12)
    # nada da Grid na conta, e a usina do outro cliente fora
    assert "Secreto" not in str(r) and "interno" not in str(r) and "200" not in {o["os"] for u in r["linhas"]
                                                                                 for o in u["oss"]}
    # o mês que o arquivo não cobre inteiro diz de quando é a semana mais antiga; o mês sem nada, vazio
    out = VCL.quadro(semanas, ids.get, {1, 2}, date(2026, 10, 1), hoje)
    assert out["n"] == 0 and out["desde"] == seg_passada
    assert VCL.quadro([], ids.get, {1, 2}, date(2026, 11, 1), hoje)["sem_programacao"]
    # novembro de 2026 começa num domingo: o arquivo que vem de 02/11 cobre todos os dias úteis, e o aviso não sai
    assert r["desde"] is None
    assert VCL.quadro(semanas[1:], ids.get, {1, 2}, date(2026, 11, 1), hoje)["desde"] == seg


def test_o_quadro_na_tela_do_cliente(app, dados, cliente_tela, tmp_path):
    hoje = Q.hoje()
    fonte = tmp_path / "banco_dados.json"
    fonte.write_text(json.dumps({"semana_ativa": _semana(hoje, [])["week"], "semanas": [
        _semana(hoje, [_tarefa("7101", "Altair", hoje), _tarefa("7102", "Coração 1", hoje)])]}), encoding="utf-8")
    app.config["NEXUS_PCM_FONTE"] = str(fonte)
    c = _cliente(app, dados, ["campo/cliente", "pcm/quadro"])
    html = c.get("/t/pcm/quadro?semana=2020-W01&equipe=SP%20Norte").get_data(as_text=True)
    assert "Programação nas suas usinas" in html and "Altair" in html and "Coração 1" not in html
    assert 'href="/t/campo/cliente/os/7101?volta=/t/pcm/quadro"' in html and "7102" not in html
    assert "Secreto" not in html and "interno" not in html and "Reprogramar" not in html
    # as sub-rotas do Quadro são da Grid
    assert c.get("/t/pcm/quadro/reprogramacoes").status_code == 403
    assert c.post("/t/pcm/quadro/motivo", data={}).status_code == 403


# ── Extintores ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_os_extintores_do_cliente(app, dados, com_cadastro):
    """O livro de 09/10/2026 (test_hseq_extintores): Altair com um vencido, um perto de vencer e um em dia; Brodowski 1
    sem validade; Coração 1 é do outro cliente."""
    from nexus.hseq import decisoes as DEC
    from nexus.hseq import extintores as EXT
    with app.test_request_context():
        d = EXT.extintores().dados
    todas, _nr, _exc = DEC.separar(d["extintores"], d["nao_reconhecidos"], {})
    r = VCL.extintores(todas, {1, 2}, date(2026, 10, 1))
    assert (r["n"], r["usinas"], r["atrasados"], r["perto"]) == (4, 2, 1, 1)
    assert (r["conferidos_mes"], r["vencem_mes"]) == (2, 1)        # conferidos em 01 e 05/10; a recarga de 10/2026
    alt = r["linhas"][0]
    assert alt["usina"] == "Altair" and [i["ext"] for i in alt["itens"]] == ["EXT01", "EXT02", "EXT03"]
    assert alt["itens"][0]["situacao"] == "Atrasado" and alt["ultima"] == date(2026, 10, 5)
    assert "Técnico Alfa" not in str(r) and "Supervisora" not in str(r) and "COR100" not in str(r)
    # pela tela, logado como cliente: sem os botões, as fotos, os relatórios nem os nomes
    c = _cliente(app, dados, ["campo/cliente", "hseq/extintores"])
    html = c.get("/t/hseq/extintores?cliente=Outro%20Cliente").get_data(as_text=True)
    assert "Extintores nas suas usinas" in html and "Altair" in html and "Coração 1" not in html
    for interno in ("Técnico Alfa", "Eletricista Beta", "Supervisora", "relatorio.pdf", "Pedir nova ronda",
                    "Planilha da TST", "data-codigo"):
        assert interno not in html, interno
    assert c.get("/t/hseq/extintores/usina?usina=Altair").status_code == 403
    assert c.get("/t/hseq/extintores/foto/ALT100-INFC1-PPCI-EXT01.jpg").status_code == 403
    assert c.get("/t/hseq/extintores/relatorio.pdf").status_code == 403


# ── EPI e EPC ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_as_luvas_do_cliente(app, dados, luvas):
    """O banco do test_hseq_epi: Altair respondeu Sim há 3 dias e Não ontem; Brodowski 1, Sim anteontem; Coração 1 é do
    outro cliente."""
    from nexus.hseq import epi as EPI
    with app.test_request_context():
        linhas = EPI.luvas().dados["usinas"]
    alt = next(x for x in linhas if x["usina"] == "Altair")
    # o mês de cada resposta, de TODAS as respostas (não só as 8 do histórico)
    assert sum(m["n"] for m in alt["por_mes"].values()) == 2 and sum(m["nao"] for m in alt["por_mes"].values()) == 1
    ontem = date.fromisoformat(_dia(1))
    r = VCL.epi(linhas, {1, 2}, ontem.replace(day=1))
    assert [u["usina"] for u in r["linhas"]] == ["Altair", "Brodowski 1"]           # o mais grave primeiro
    assert (r["sem_luvas"], r["com_luvas"], r["usinas"]) == (1, 1, 2)
    assert r["linhas"][0]["luvas"] is False and r["linhas"][0]["mes_nao"] == 1
    assert "Fulano" not in str(r)
    c = _cliente(app, dados, ["campo/cliente", "hseq/epi"])
    html = c.get("/t/hseq/epi?responsavel=x").get_data(as_text=True)
    assert "Luvas isolantes nas suas usinas" in html and "Brodowski 1" in html and "Coração 1" not in html
    assert "Fulano" not in html and "/fotos" not in html
    assert 'href="/t/campo/cliente/os/500?volta=/t/hseq/epi"' in html


# ── Almoxarifado ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_almoxarifado_do_cliente(app, dados, almox):
    """O banco do test_pcm_almoxarifado (25/10/2026): o almoxarifado 10 é da Altair (SP-1 abaixo do mínimo, SP-2 no
    limite, a SP-1 saiu na OS 16885 em 24/10); o 20 não ligou a usina nenhuma."""
    from nexus.pcm import almoxarifado as T
    with app.test_request_context():
        d = T.montar().dados
    r = VCL.almoxarifado(d, {1, 2}, date(2026, 10, 1))
    assert (r["n"], r["pecas"], r["abaixo"], r["no_limite"], r["saidas_mes"]) == (1, 2, 1, 1, 1)
    a = r["almoxarifados"][0]
    assert a["usina"] == "Altair" and [p["codigo"] for p in a["pecas"]] == ["SP-1", "SP-2"]
    assert a["saidas"][0]["os"] == "16885" and a["saidas"][0]["dia"] == "2026-10-24"
    assert VCL.almoxarifado(d, {1, 2}, date(2026, 9, 1))["saidas_mes"] == 0
    assert "custo" not in str(r) and "Almoxarifado 20" not in str(r)
    c = _cliente(app, dados, ["campo/cliente", "pcm/pecas"])
    html = c.get("/t/pcm/pecas").get_data(as_text=True)
    assert "Peças nas suas usinas" in html and "Fusível 10A" in html and "Almoxarifado 20" not in html
    assert "R$" not in html and "Inventário" not in html and "recusad" not in html
    assert 'href="/t/campo/cliente/os/16885?volta=/t/pcm/pecas"' in html
    assert c.get("/t/pcm/pecas/almox/10").status_code == 403
    assert c.get("/t/pcm/pecas/inventario").status_code == 403
