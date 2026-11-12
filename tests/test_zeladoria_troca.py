"""A troca da Zeladoria (11/11/2026: o Supabase do Radar parou; o Nexus passa a ser a casa da zeladoria).

- o interruptor da gravação mora na pasta de dados da máquina e só o administrador mexe (/t/zeladoria/troca);
- quem está aprovado no Radar entra na Zeladoria do Nexus, mesmo sem setor;
- a função nova do financeiro, `fin_editar_motivo`, com a regra do banco do Radar.
Pessoas e e-mails fictícios; nada vai ao banco de verdade."""
import time

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)
from test_setor_telas import ANA, CAIO, _como, _sem_copias, setores  # noqa: F401  (fixtures e pessoas)

from nexus.zeladoria import acesso as ZA
from nexus.zeladoria import financeiro as F
from nexus.zeladoria import gravacao, leitura


@pytest.fixture(autouse=True)
def _limpo():
    gravacao._INTERRUPTOR.update(em=0.0, caminho=None, valor=None)
    ZA.esquecer()
    leitura.limpar()
    yield
    gravacao._INTERRUPTOR.update(em=0.0, caminho=None, valor=None)
    ZA.esquecer()
    leitura.limpar()


def _estado(perfis=()):
    return {"abas": {"perfis": list(perfis), "fin_provisao_historico": [], "financeiro_historico": []},
            "tipos": {}, "chaves": {}, "versao": 0, "versoes": {}, "copiado_em": "2026-11-12T02:40:00+00:00",
            "exportado_em": "2026-11-12T02:29:11+00:00"}


# ── o interruptor ──────────────────────────────────────────────────────────────────────────────────────────────


def test_o_interruptor_mora_na_pasta_de_dados_e_a_variavel_vence(app, tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_ZELADORIA_GRAVA", raising=False)
    cfg = app.config
    cfg["NEXUS_ZELADORIA_GRAVA"] = ""
    assert gravacao.ativo(cfg) is False                       # teste sem NEXUS_DADOS: nunca lê a pasta real
    with pytest.raises(gravacao.Recusa):
        gravacao.ligar(cfg, True, "adm@exemplo.test")
    cfg["NEXUS_DADOS"] = str(tmp_path)
    assert gravacao.ativo(cfg) is False                       # sem arquivo: desligada
    gravacao.ligar(cfg, True, "adm@exemplo.test")
    assert gravacao.ativo(cfg) is True and (tmp_path / "zeladoria" / "gravacao.json").exists()
    cfg["NEXUS_ZELADORIA_GRAVA"] = "0"
    assert gravacao.ativo(cfg) is False and gravacao.forcada(cfg) == "0"
    cfg["NEXUS_ZELADORIA_GRAVA"] = ""
    gravacao.ligar(cfg, False, "adm@exemplo.test")
    assert gravacao.ativo(cfg) is False


def test_a_pagina_da_troca_e_so_do_administrador_e_liga_com_a_copia(app, logado, tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_ZELADORIA_GRAVA", raising=False)
    app.config.update(NEXUS_ZELADORIA_GRAVA="", NEXUS_DADOS=str(tmp_path))
    monkeypatch.setattr(leitura, "estado", lambda cfg: _estado())
    subiu = []
    monkeypatch.setattr(gravacao, "do_app", lambda cfg: subiu.append(1))
    c = _como(app, "outra@exemplo.test")
    assert c.get("/t/zeladoria/troca").status_code == 403
    html = logado.get("/t/zeladoria/troca").get_data(as_text=True)
    assert "Desligada" in html and "Ligar a gravação" in html
    r = logado.post("/t/zeladoria/troca", data={"ligar": "1"})
    assert r.status_code == 302 and gravacao.ativo(app.config) and subiu == [1]
    assert "Ligada" in logado.get("/t/zeladoria/troca").get_data(as_text=True)
    assert logado.post("/t/zeladoria/troca", data={"ligar": "0"}).status_code == 302
    assert gravacao.ativo(app.config) is False
    # onde a variável decide, o botão não muda nada e diz isso
    app.config["NEXUS_ZELADORIA_GRAVA"] = "0"
    html = logado.post("/t/zeladoria/troca", data={"ligar": "1"}).get_data(as_text=True)
    assert "NEXUS_ZELADORIA_GRAVA" in html and gravacao.ativo(app.config) is False


# ── o aprovado no Radar entra ──────────────────────────────────────────────────────────────────────────────────


def _copia_em_memoria(perfis):
    leitura._CACHE.update(em=time.time(), estado=_estado(perfis))


def test_aprovado_no_radar_sem_setor_entra_na_zeladoria(app, setores, monkeypatch):
    monkeypatch.setattr(leitura, "estado", lambda cfg: leitura._CACHE["estado"])
    _copia_em_memoria([{"user_id": "u1", "email": CAIO.upper(), "papel": "Analista", "status": "aprovado"}])
    c = _como(app, CAIO)
    html = c.get("/").get_data(as_text=True)
    assert "Sem setor" not in html and 'data-torre="zeladoria"' in html
    assert c.get("/t/zeladoria/visao-geral").status_code == 200
    assert c.get("/t/cos/mesa").status_code == 403                    # só o que o setor Zeladoria vê
    # pendente (ou fora do perfis) continua sem setor
    _copia_em_memoria([{"user_id": "u1", "email": CAIO, "papel": None, "status": "pendente"}])
    assert "Sem setor, fale com o responsável." in _como(app, CAIO).get("/").get_data(as_text=True)


def test_aprovado_no_radar_com_outro_setor_ganha_a_zeladoria(app, setores, monkeypatch):
    monkeypatch.setattr(leitura, "estado", lambda cfg: leitura._CACHE["estado"])
    c = _como(app, ANA)
    assert 'data-torre="zeladoria"' not in c.get("/").get_data(as_text=True)
    _copia_em_memoria([{"user_id": "u2", "email": ANA, "papel": "Analista", "status": "aprovado"}])
    c = _como(app, ANA)
    html = c.get("/").get_data(as_text=True)
    assert "Setor: <b>Performance</b>" in html and 'data-torre="zeladoria"' in html


def test_sem_a_copia_em_memoria_ninguem_espera_o_banco(app):
    with app.app_context():
        assert ZA.aprovado(app, CAIO) is False                    # no teste a carga por trás nem sai


# ── fin_editar_motivo ──────────────────────────────────────────────────────────────────────────────────────────


HEAD = {"status": "aprovado", "papel": "HEAD", "email": "head@exemplo.test"}
ANALISTA = {"status": "aprovado", "papel": "Analista", "email": "analista@exemplo.test"}


def _hist():
    est = _estado()
    est["abas"]["fin_provisao_historico"] = [
        {"id": 7, "motivo": "erro de digitação", "quem": "analista@exemplo.test"},
        {"id": 8, "motivo": "outro", "quem": "head@exemplo.test", "motivo_original": "o primeiro"}]
    est["abas"]["financeiro_historico"] = [
        {"id": "H1", "quem": "analista@exemplo.test", "campos": {"valor": [1, 2], "_motivo": "velho"}},
        {"id": "H2", "quem": "analista@exemplo.test", "campos": {"valor": [1, 2]}}]
    return est


def test_editar_motivo_guarda_o_original_uma_vez():
    ops, n = F.fin_editar_motivo(_hist(), HEAD, {"p_origem": "provisao", "p_ids": ["7", 8], "p_motivo": " certo "},
                                 agora="2026-11-12T00:00:00+00:00")
    assert n == 2 and ops[0]["view"] == "rf_fin_provisao_historico"
    l7, l8 = ops[0]["linhas"]
    assert (l7["motivo"], l7["motivo_original"], l7["motivo_editado_por"]) == ("certo", "erro de digitação",
                                                                                "head@exemplo.test")
    assert l8["motivo_original"] == "o primeiro"                       # o 1º motivo não se perde na 2ª edição
    ops, n = F.fin_editar_motivo(_hist(), ANALISTA, {"p_origem": "parcela", "p_ids": ["H1", "H2"], "p_motivo": "novo"})
    assert n == 1 and ops[0]["linhas"][0]["campos"]["_motivo_original"] == "velho"   # a H2 não tinha motivo


def test_editar_motivo_recusa_como_o_banco():
    casos = [(ANALISTA, {"p_origem": "provisao", "p_ids": [8], "p_motivo": "x"}, "só quem fez"),
             (HEAD, {"p_origem": "provisao", "p_ids": [7], "p_motivo": "  "}, "não pode ficar vazio"),
             (HEAD, {"p_origem": "provisao", "p_ids": [], "p_motivo": "x"}, "nenhuma alteração"),
             (HEAD, {"p_origem": "outra", "p_ids": [7], "p_motivo": "x"}, "origem inválida"),
             (HEAD, {"p_origem": "parcela", "p_ids": ["H2"], "p_motivo": "x"}, "não encontrada"),
             ({"status": "pendente"}, {"p_origem": "provisao", "p_ids": [7], "p_motivo": "x"}, "não aprovado")]
    for quem, args, msg in casos:
        with pytest.raises(F.FinErro, match=msg):
            F.fin_editar_motivo(_hist(), quem, args)
    assert "fin_editar_motivo" in F.FUNCOES
