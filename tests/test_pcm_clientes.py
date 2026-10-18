"""O nome do cliente nas telas do PCM é o do cadastro do Nexus (Levi, 18/10/2026: "Use o nome do cliente no Nexus como
principal"). Os arquivos do PCM tiram o cliente do nome do site no Fracttal, e a grafia de lá não é a do cadastro
("Utragaz", "RenoGrid", "Greenyellow", "Semp"). Clientes, usinas e sites inventados."""
import json

import pytest
from pg_falso import ApiPGFalsa
from test_campo_visao import _aba

from nexus.campo import visao
from nexus.pcm import clientes as C
from nexus.pcm import fonte

CLIENTES = [{"cliente_id": 1, "nome": "Ultragaz"}, {"cliente_id": 2, "nome": "Renogrid"},
            {"cliente_id": 3, "nome": "GreenYellow"}, {"cliente_id": 4, "nome": "SEMP"}, {"cliente_id": 5, "nome": "Thopen"}]
USINAS = [{"usina_id": 10, "cliente_id": 1, "nome": "Usina U"}, {"usina_id": 11, "cliente_id": 2, "nome": "Usina R"},
          {"usina_id": 12, "cliente_id": 5, "nome": "Usina T"}, {"usina_id": 13, "cliente_id": 2, "nome": "Usina M"},
          {"usina_id": 14, "cliente_id": 5, "nome": "Usina N"}]
DE_PARA = [{"usina_id": 10, "sistema": "Fracttal · Classificação 1", "chave_externa": "Utragaz - Usina U - SP"},
           {"usina_id": 11, "sistema": "Fracttal · Classificação 1", "chave_externa": "RenoGrid - Usina R - MG"},
           {"usina_id": 12, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Usina T - SP"},
           # o mesmo começo de site em usinas de dois clientes: não dá para saber de quem é, não troca
           {"usina_id": 13, "sistema": "Fracttal · Classificação 1", "chave_externa": "Misto - Usina M - GO"},
           {"usina_id": 14, "sistema": "Fracttal · Classificação 1", "chave_externa": "Misto - Usina N - GO"},
           # outro sistema, com outro formato de nome: não entra na conta do começo do site
           {"usina_id": 10, "sistema": "API PV · usina", "chave_externa": "Outra Coisa - Usina U"}]


def test_o_mapa_pelo_nome_do_cadastro_e_pelo_site_do_fracttal():
    m = C.montar(CLIENTES, USINAS, DE_PARA)
    # a mesma grafia sem diferenciar maiúscula, acento e espaço
    assert [C.nome(t, m) for t in ("RenoGrid", "Greenyellow", "Semp", "THOPEN", " ultra gaz ")] == [
        "Renogrid", "GreenYellow", "SEMP", "Thopen", "Ultragaz"]
    # o erro de grafia do Fracttal, pela usina do site no de-para (por ID, não por palpite)
    assert C.nome("Utragaz", m) == "Ultragaz"
    # o que não casa fica como veio
    assert [C.nome(t, m) for t in ("Misto", "Outra Coisa", "Faro Energy", "Thopen;#Renogrid", "", None)] == [
        "Misto", "Outra Coisa", "Faro Energy", "Thopen;#Renogrid", "", None]


def test_aplicar_troca_so_o_campo_cliente_e_conta():
    m = C.montar(CLIENTES, USINAS, DE_PARA)
    dados = {"tarefas": [{"cliente": "Utragaz", "usina": "Utragaz - Usina U - SP"},
                         {"cliente": "Thopen;#Renogrid", "usina": "x"}, {"cliente": "Thopen"}],
             "resumo": {"usinas": [{"cliente": "RenoGrid", "nome": "RenoGrid"}]}, "clientes": ["Semp"]}
    assert C.aplicar(dados, m) == 2
    assert dados["tarefas"][0] == {"cliente": "Ultragaz", "usina": "Utragaz - Usina U - SP"}
    assert dados["tarefas"][1]["cliente"] == "Thopen;#Renogrid"
    assert dados["resumo"]["usinas"][0] == {"cliente": "Renogrid", "nome": "RenoGrid"}
    assert dados["clientes"] == ["Semp"]                    # só a chave "cliente" muda
    assert C.aplicar(dados, m) == 0                         # de novo, nada muda


@pytest.fixture
def com_banco(app, tmp_path):
    api = ApiPGFalsa()
    for aba, linhas in (("clientes", CLIENTES), ("usinas", USINAS), ("de_para", DE_PARA)):
        _aba(api, "cadastro_nexus", aba, linhas)
    arq = tmp_path / "gestao_pcm.json"
    arq.write_text(json.dumps({"tarefas": [{"cliente": "Utragaz", "usina": "Utragaz - Usina U - SP"},
                                           {"cliente": "RenoGrid", "usina": "RenoGrid - Usina R - MG"}]}), encoding="utf-8")
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_PCM_GESTAO_FONTE=str(arq))
    app.extensions["nexus_dados_sessao"] = api
    visao.limpar()
    with app.app_context():
        yield arq
    visao.limpar()


def test_as_telas_do_pcm_recebem_o_nome_do_nexus(app, com_banco):
    """A Gestão PCM, o Fora da programação, os relatórios e o Acompanhamento leem os arquivos pelo `fonte`: o cliente
    chega com o nome do cadastro. O arquivo do PCM não muda (o que vai ao App e ao PCM não passa por aqui)."""
    tarefas = fonte.ler_gestao(app.config).dados["tarefas"]
    assert [t["cliente"] for t in tarefas] == ["Ultragaz", "Renogrid"]
    assert [t["usina"] for t in tarefas] == ["Utragaz - Usina U - SP", "RenoGrid - Usina R - MG"]
    assert json.loads(com_banco.read_text(encoding="utf-8"))["tarefas"][0]["cliente"] == "Utragaz"


def test_sem_o_banco_o_nome_fica_como_veio(app, tmp_path):
    arq = tmp_path / "gestao_pcm.json"
    arq.write_text(json.dumps({"tarefas": [{"cliente": "Utragaz"}]}), encoding="utf-8")
    app.config["NEXUS_PCM_GESTAO_FONTE"] = str(arq)
    with app.app_context():                                 # teste sem o banco falso: o Nexus não vai à rede
        assert fonte.ler_gestao(app.config).dados["tarefas"][0]["cliente"] == "Utragaz"
    assert fonte.ler_gestao(app.config).dados["tarefas"][0]["cliente"] == "Utragaz"     # fora do app: idem


def test_o_quadro_da_rodada_tambem(app, com_banco, tmp_path, monkeypatch):
    """O Quadro da semana monta a semana da rodada pela planilha do motor (o cliente sai do nome do site)."""
    from nexus.pcm import quadro
    arq = tmp_path / "sombra.xlsx"
    arq.write_bytes(b"planilha")
    monkeypatch.setattr(quadro.C, "linhas_da_planilha", lambda caminho: (
        [{"Ativo (Usina)": "Utragaz - Usina U - SP", "Dia": "Segunda (20/10)"}], [{"Ativo": "RenoGrid - Usina R - MG"}]))
    sem = quadro.semana_do_rascunho(arq, "2026-W43")
    assert (sem["rows"][0]["cliente"], sem["pendentes"][0]["cliente"]) == ("Ultragaz", "Renogrid")
    assert sem["rows"][0]["usina"] == "Utragaz - Usina U - SP"


def test_as_observacoes_da_semana_tambem(app, com_banco):
    from nexus.pcm import observacoes as O
    us = O.usinas_por_dia([], ["Utragaz - Usina U - SP", "Thopen - Usina T - SP"])
    assert [(u["cliente"], u["fracttal"]) for u in us] == [("Thopen", "Thopen - Usina T - SP"),
                                                           ("Ultragaz", "Utragaz - Usina U - SP")]


def test_a_marca_antiga_do_fora_da_programacao_tambem(app, com_banco, tmp_path):
    """A marca guarda (cifrado) o cliente da tarefa de quando foi feita: a de antes da troca tem a grafia do arquivo."""
    from test_campo_visao import CHAVE_CADASTRO

    from nexus.pcm import motivos as M
    cfg = app.config
    cfg.update(NEXUS_PCM_MOTIVOS_ARQUIVO=str(tmp_path / "motivos.json"), NEXUS_CHAVE_CADASTRO=CHAVE_CADASTRO)
    M.limpar()
    mid = next(m["id"] for m in M.ativos(M.ler(cfg, forcar=True)) if m["nome"] == "Aguardando material")
    M.marcar(cfg, {"os": "901", "codigo": "THPN-ALT100-INVR1", "tarefa": "Troca de fusível", "tipo": "Corretiva",
                   "usina": "Utragaz - Usina U - SP", "cliente": "Utragaz"}, mid, "",
             {"email": "pessoa@exemplo.test", "nome": "Pessoa Fictícia"})
    vig = M.vigentes(cfg, M.ler(cfg, forcar=True))
    assert [m["cliente"] for k, m in vig.items() if k != "_ilegiveis"] == ["Ultragaz"]
    M.limpar()
