"""Quem criou cada OS, para a tela Normalizações (27/10/2026, Levi: "Coluna de quem criou a OS" e o filtro "Criado por").
O Fracttal diz (o `created_by` do REST); o Nexus lê aos poucos, guarda, e no disco só cifrado. Nada aqui vai à rede, e
os nomes são fictícios."""
import pytest

from nexus.cadastro.cifra import gerar_chave
from nexus.campo import fracttal
from nexus.cos import criadores as CR


@pytest.fixture(autouse=True)
def _limpa():
    CR.limpar()
    yield
    CR.limpar()


@pytest.fixture
def cfg(app, tmp_path):
    app.config.update(NEXUS_DADOS=str(tmp_path), NEXUS_CHAVE_CADASTRO=gerar_chave())
    with app.app_context():
        yield app.config


def _ler(nomes, pedidos=None, recusar=()):
    def ler(path):
        folio = path.split("wo_folio=")[1].split("&")[0]
        if pedidos is not None:
            pedidos.append(folio)
        if folio in recusar:
            raise fracttal.Recusado("o Fracttal recusou por excesso de pedidos (HTTP 429)")
        return {"data": [{"wo_folio": folio, "created_by": nomes.get(folio, "")}]}
    return ler


def test_a_fila_le_na_ordem_da_tela_e_guarda(cfg):
    assert CR.nomes(["17003", "17001", "x", "17003", "17002"], cfg) == {"17003": None, "17001": None, "17002": None}
    assert CR.na_fila() == 3
    pedidos = []
    assert CR.ler_fila(cfg, _ler({"17001": "Fulana  Operadora", "17003": "Ciclano Operador"}, pedidos)) == 3
    assert pedidos == ["17003", "17001", "17002"]                     # a mais recente (o alto da tela) primeiro
    assert CR.nomes(["17001", "17002", "17003"], cfg) == {"17001": "Fulana Operadora", "17002": "",
                                                          "17003": "Ciclano Operador"}
    assert CR.na_fila() == 0                                          # lida uma vez, não volta à fila


def test_a_recusa_do_fracttal_devolve_a_os_a_fila(cfg):
    CR.nomes(["17001", "17002"], cfg)
    with pytest.raises(fracttal.Recusado):
        CR.ler_fila(cfg, _ler({"17001": "Fulana"}, recusar=("17002",)))
    assert CR.na_fila() == 1 and CR.nomes(["17001"], cfg) == {"17001": "Fulana"}


def test_o_reinicio_le_do_arquivo_cifrado(cfg, tmp_path):
    CR.nomes(["17001"], cfg)
    CR.ler_fila(cfg, _ler({"17001": "Fulana Operadora"}))
    arquivo = tmp_path / CR.ARQUIVO
    assert arquivo.exists() and "Fulana" not in arquivo.read_text(encoding="utf-8")      # o nome só cifrado
    CR.limpar()                                                       # o processo novo (o deploy)
    assert CR.nomes(["17001"], cfg) == {"17001": "Fulana Operadora"} and CR.na_fila() == 0
    # arquivo de outra chave: não abre, e lê de novo do Fracttal
    CR.limpar()
    cfg["NEXUS_CHAVE_CADASTRO"] = gerar_chave()
    assert CR.nomes(["17001"], cfg) == {"17001": None}


def test_sem_a_chave_do_cadastro_so_na_memoria(cfg, tmp_path):
    cfg["NEXUS_CHAVE_CADASTRO"] = ""
    CR.nomes(["17001"], cfg)
    CR.ler_fila(cfg, _ler({"17001": "Fulana"}))
    assert not (tmp_path / CR.ARQUIVO).exists() and CR.nomes(["17001"], cfg) == {"17001": "Fulana"}


def test_no_teste_nenhuma_linha_de_fundo_sai(cfg):
    CR.nomes(["17001"], cfg)
    assert CR._laco["thread"] is None
