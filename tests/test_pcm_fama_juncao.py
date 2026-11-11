"""A junção das partes A e B da FAMA (11/11/2026): a porta única do PCM (`fama_os._linhas_fama`) lê o livro que a parte A
grava (`nexus/dados/fama.ler_banco`) e devolve o que o Quadro e o adaptador do motor esperam: os IDs em número (o banco
pode devolver "10.0"), o título decifrado só em memória e nenhuma coluna cifrada, e o `gerado_em` da aba `atualizacao`
(o batimento: a leitura da FAMA está viva?). Sem a chave do cadastro, ou com outra, a OS vale sem o título. Só o título
das OS abertas e em andamento é decifrado: a descrição nunca (revisão de 11/11/2026, item 2). Nenhum teste vai à rede."""
from nexus.cadastro import cifra
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.dados import conexao, fama
from nexus.dados import fato_os_fama as FO
from nexus.pcm import fama_os

GERADO_EM = "2026-11-11T14:40:00-03:00"


def _linha(cofre, oid=10, titulo="Troca do inversor fictício", status="planned", descricao=None):
    return {"fama_os_id": f"{oid}.0", "fama_projeto_id": "7", "usina_id": "12.0", "usina_ligada_por": "manual",
            "data_id_criacao": "20261001", "data_id_prevista": 20261112.0, "data_id_fim": None,
            "status": status, "tipo": "Corrective", "severidade": "Urgent",
            "titulo_cifrado": cofre.cifrar(titulo, FO.contexto(oid, "titulo")),
            "descricao_cifrada": descricao if descricao is not None else cofre.cifrar(
                "texto livre do cliente", FO.contexto(oid, "descricao"))}


def _livro(monkeypatch, linhas, gerado_em=GERADO_EM):
    monkeypatch.setattr(conexao, "banco_de", lambda cfg: ("http://banco.falso", None))
    monkeypatch.setattr(fama, "ler_banco", lambda base, sessao: {FO.ABA: linhas, FO.ABA_DIM: [],
                                                                 "atualizacao": [{"gerado_em": gerado_em}]})


def test_a_porta_le_o_livro_da_parte_a_com_os_ids_em_numero_e_o_titulo_decifrado(monkeypatch):
    chave = gerar_chave()
    _livro(monkeypatch, [_linha(Cofre(chave))])
    lido = fama_os._linhas_fama({"NEXUS_CHAVE_CADASTRO": chave})
    assert len(lido.linhas) == 1 and lido.gerado_em == GERADO_EM
    d = lido.linhas[0]
    assert d["fama_os_id"] == 10 and d["usina_id"] == 12
    assert d["data_id_prevista"] == 20261112 and d["data_id_criacao"] == 20261001 and d["data_id_fim"] is None
    assert d["titulo"] == "Troca do inversor fictício"
    assert "titulo_cifrado" not in d and "descricao_cifrada" not in d and "descricao" not in d
    assert d["status"] == "planned" and fama_os.situacao(d["status"]) == "aberta"


def test_sem_a_chave_ou_com_outra_a_os_vale_sem_o_titulo(monkeypatch):
    _livro(monkeypatch, [_linha(Cofre(gerar_chave()))])
    assert fama_os._linhas_fama({}).linhas[0]["titulo"] is None
    assert fama_os._linhas_fama({"NEXUS_CHAVE_CADASTRO": gerar_chave()}).linhas[0]["titulo"] is None
    assert fama_os._linhas_fama({"NEXUS_CHAVE_CADASTRO": "nao-e-chave"}).linhas[0]["usina_id"] == 12


def test_antes_da_primeira_leitura_do_servidor_nenhuma_linha_e_nenhum_batimento(monkeypatch):
    monkeypatch.setattr(conexao, "banco_de", lambda cfg: ("http://banco.falso", None))
    monkeypatch.setattr(fama, "ler_banco", lambda base, sessao: {})
    lido = fama_os._linhas_fama({})
    assert lido.linhas == [] and lido.gerado_em is None


def test_so_o_titulo_das_os_abertas_e_em_andamento_e_decifrado(monkeypatch):
    """Revisão de 11/11/2026, item 2: o PCM decifra só o título, e só das OS que viram cartão ou linha do motor (abertas e em
    andamento). A descrição nunca: é texto livre do cliente que o Quadro não mostra. Falha se a descrição for decifrada."""
    chave = gerar_chave()
    c = Cofre(chave)
    _livro(monkeypatch, [_linha(c, 10), _linha(c, 11, status="under execution"), _linha(c, 12, status="closed")])
    contextos = []
    decifrar = cifra.Cofre.decifrar

    def espia(self, valor, contexto):
        contextos.append(contexto)
        return decifrar(self, valor, contexto)
    monkeypatch.setattr(cifra.Cofre, "decifrar", espia)
    lido = fama_os._linhas_fama({"NEXUS_CHAVE_CADASTRO": chave})
    assert sorted(contextos) == [FO.contexto(10, "titulo"), FO.contexto(11, "titulo")]
    assert not any(x.endswith("/descricao") for x in contextos)
    assert [d["titulo"] for d in lido.linhas] == ["Troca do inversor fictício", "Troca do inversor fictício", None]


def test_a_descricao_com_a_cifra_quebrada_nao_apaga_o_titulo(monkeypatch):
    chave = gerar_chave()
    _livro(monkeypatch, [_linha(Cofre(chave), descricao="cf1:cifra-quebrada")])
    assert fama_os._linhas_fama({"NEXUS_CHAVE_CADASTRO": chave}).linhas[0]["titulo"] == "Troca do inversor fictício"
