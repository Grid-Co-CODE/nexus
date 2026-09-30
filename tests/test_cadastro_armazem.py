"""Armazém local do ensaio: um JSON fora do OneDrive, com versão por linha, histórico e cópia antes de trocar."""
import json

import pytest

from nexus.cadastro.armazem import ArmazemLocal, Conflito


@pytest.fixture
def arm(tmp_path):
    return ArmazemLocal(tmp_path / "cadastro.json")


def _linha(id_, versao=1, **campos):
    return {"id": id_, "_versao": versao, **campos}


def test_arquivo_inexistente_e_cadastro_vazio(arm):
    assert arm.ler("usinas") == []


def test_inserir_persiste_em_disco(arm, tmp_path):
    arm.inserir("usinas", _linha("UFV-1", nome="Brodowski"))
    outro = ArmazemLocal(tmp_path / "cadastro.json")         # como um restart do servidor
    assert outro.ler("usinas") == [_linha("UFV-1", nome="Brodowski")]


def test_inserir_id_repetido_recusa(arm):
    arm.inserir("usinas", _linha("UFV-1"))
    with pytest.raises(ValueError):
        arm.inserir("usinas", _linha("UFV-1"))


def test_gravar_com_a_versao_lida_troca_e_guarda_a_anterior(arm):
    arm.inserir("usinas", _linha("UFV-1", nome="Brodowski"))
    arm.gravar("usinas", _linha("UFV-1", versao=2, nome="Brodowski 1"), versao_esperada=1)
    assert arm.ler("usinas")[0]["nome"] == "Brodowski 1"
    assert [h["nome"] for h in arm.historico("usinas", "UFV-1")] == ["Brodowski"]


def test_gravar_com_versao_velha_e_conflito_e_nao_muda_nada(arm):
    # Duas pessoas abriram a mesma ficha; a segunda a salvar não pode apagar o que a primeira gravou.
    arm.inserir("usinas", _linha("UFV-1", nome="A"))
    arm.gravar("usinas", _linha("UFV-1", versao=2, nome="B"), versao_esperada=1)
    with pytest.raises(Conflito) as erro:
        arm.gravar("usinas", _linha("UFV-1", versao=2, nome="C"), versao_esperada=1)
    assert erro.value.atual["nome"] == "B"
    assert arm.ler("usinas")[0]["nome"] == "B"


def test_gravar_registro_inexistente_recusa(arm):
    with pytest.raises(KeyError):
        arm.gravar("usinas", _linha("UFV-9", versao=2), versao_esperada=1)


def test_substituir_faz_copia_antes_e_guarda_historico(arm, tmp_path):
    arm.inserir("usinas", _linha("UFV-1", nome="A"))
    copia = arm.substituir({"usinas": [_linha("UFV-1", versao=2, nome="B"), _linha("UFV-2", nome="C")]},
                           {"quem": "importação", "arquivo": "BD.xlsx"})
    assert copia is not None and copia.exists()
    assert json.loads(copia.read_text(encoding="utf-8"))["entidades"]["usinas"][0]["nome"] == "A"
    assert [x["nome"] for x in arm.ler("usinas")] == ["B", "C"]
    assert [h["nome"] for h in arm.historico("usinas", "UFV-1")] == ["A"]
    assert arm.importacoes()[0]["arquivo"] == "BD.xlsx"


def test_substituir_so_mexe_nas_entidades_enviadas(arm):
    arm.inserir("equipes", _linha("E-001", nome="SP Leste 01"))
    arm.substituir({"usinas": [_linha("UFV-1")]}, {"quem": "x"})
    assert arm.ler("equipes")[0]["nome"] == "SP Leste 01"


def test_auditoria_mais_nova_primeiro(arm):
    arm.auditar({"acao": "criou", "id": "UFV-1"})
    arm.auditar({"acao": "alterou", "id": "UFV-1"})
    assert [e["acao"] for e in arm.auditoria()] == ["alterou", "criou"]


def test_arquivo_fica_sempre_json_valido(arm, tmp_path):
    for i in range(5):
        arm.inserir("usinas", _linha(f"UFV-{i}"))
    json.loads((tmp_path / "cadastro.json").read_text(encoding="utf-8"))
    assert not list(tmp_path.glob("*.tmp"))
