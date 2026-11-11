"""A junção das partes A e B da FAMA (11/11/2026): a porta única do PCM (`fama_os._linhas_fama`) lê o livro que a parte A
grava (`nexus/dados/fama.ler_banco`) e devolve o que o Quadro e o adaptador do motor esperam: os IDs em número (o banco
pode devolver "10.0"), o título decifrado só em memória e nenhuma coluna cifrada. Sem a chave do cadastro, ou com outra,
a OS vale sem o título. Nenhum teste vai à rede."""
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.dados import conexao, fama
from nexus.dados import fato_os_fama as FO
from nexus.pcm import fama_os


def _linha(cofre, oid=10, titulo="Troca do inversor fictício"):
    return {"fama_os_id": f"{oid}.0", "fama_projeto_id": "7", "usina_id": "12.0", "usina_ligada_por": "manual",
            "data_id_criacao": "20261001", "data_id_prevista": 20261112.0, "data_id_fim": None,
            "status": "planned", "tipo": "Corrective", "severidade": "Urgent",
            "titulo_cifrado": cofre.cifrar(titulo, FO.contexto(oid, "titulo")),
            "descricao_cifrada": cofre.cifrar("texto livre do cliente", FO.contexto(oid, "descricao"))}


def _livro(monkeypatch, linhas):
    monkeypatch.setattr(conexao, "banco_de", lambda cfg: ("http://banco.falso", None))
    monkeypatch.setattr(fama, "ler_banco", lambda base, sessao: {FO.ABA: linhas, FO.ABA_DIM: [], "atualizacao": []})


def test_a_porta_le_o_livro_da_parte_a_com_os_ids_em_numero_e_o_titulo_decifrado(monkeypatch):
    chave = gerar_chave()
    _livro(monkeypatch, [_linha(Cofre(chave))])
    out = fama_os._linhas_fama({"NEXUS_CHAVE_CADASTRO": chave})
    assert len(out) == 1
    d = out[0]
    assert d["fama_os_id"] == 10 and d["usina_id"] == 12
    assert d["data_id_prevista"] == 20261112 and d["data_id_criacao"] == 20261001 and d["data_id_fim"] is None
    assert d["titulo"] == "Troca do inversor fictício"
    assert "titulo_cifrado" not in d and "descricao_cifrada" not in d and "descricao" not in d
    assert d["status"] == "planned" and fama_os.situacao(d["status"]) == "aberta"


def test_sem_a_chave_ou_com_outra_a_os_vale_sem_o_titulo(monkeypatch):
    _livro(monkeypatch, [_linha(Cofre(gerar_chave()))])
    assert fama_os._linhas_fama({})[0]["titulo"] is None
    assert fama_os._linhas_fama({"NEXUS_CHAVE_CADASTRO": gerar_chave()})[0]["titulo"] is None
    assert fama_os._linhas_fama({"NEXUS_CHAVE_CADASTRO": "nao-e-chave"})[0]["usina_id"] == 12


def test_antes_da_primeira_leitura_do_servidor_nenhuma_linha(monkeypatch):
    monkeypatch.setattr(conexao, "banco_de", lambda cfg: ("http://banco.falso", None))
    monkeypatch.setattr(fama, "ler_banco", lambda base, sessao: {})
    assert fama_os._linhas_fama({}) == []
