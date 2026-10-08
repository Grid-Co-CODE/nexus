"""A AUXILIAR do motor sai do cadastro do Nexus (nexus/pcm/auxiliar.py), lida do jeito que o motor lê."""
import pandas as pd
import pytest

from nexus.cadastro.armazem import ArmazemLocal
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.cadastro.servico import Carga, Servico
from nexus.cadastro.tipos import Legado
from nexus.pcm import auxiliar as A


def cadastro_de_teste(caminho):
    s = Servico(ArmazemLocal(caminho), Cofre(gerar_chave()))
    s.aplicar_carga(Carga(
        entidades={
            "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Thopen"}}],
            "equipes": [{"id": "1", "ordem": 1, "valores": {"nome": "SP Norte 02"}},
                        {"id": "2", "ordem": 2, "valores": {"nome": "Rio do Fogo 1"}}],
            "pessoas": [{"id": "1", "ordem": 1, "valores": {"nome": "Carla Maria Souza", "vinculo": "Supervisor"}}],
            "usinas": [
                {"id": "1", "ordem": 1, "valores": {
                    "nome": "Altair", "cliente": "1", "status": "OPERAÇÃO", "equipe": "1", "responsavel_om": "1",
                    "potencia_contratual": 6.898, "potencia_real": 7.1, "cidade": "Altair", "uf": "SP",
                    "base_equipe": "Guaraci/SP", "codigo": "THPN-ALT100", "id_bd": "UFV-001"}},
                {"id": "2", "ordem": 2, "valores": {
                    "nome": "Rio do Fogo 1", "cliente": "1", "status": "OPERAÇÃO", "equipe": "2",
                    "responsavel_om": "N/A", "base_equipe": "N/I", "potencia_contratual": Legado("a definir")}},
            ],
        },
        listas={"status_usina": ["OPERAÇÃO", "A MOBILIZAR"], "uf": ["SP"], "vinculo": ["Supervisor"]},
        origem={"arquivo": "teste.xlsx"},
    ), quem="importação")
    return s


@pytest.fixture
def srv(tmp_path):
    return cadastro_de_teste(tmp_path / "cadastro.json")


def test_auxiliar_sai_no_formato_que_o_motor_le(srv, tmp_path):
    destino = tmp_path / A.NOME
    r = A.escrever(srv, destino)
    assert r == {"usinas": 2, "sem_responsavel": 1, "sem_equipe": 1}
    # a mesma leitura do fonte_bd_api.df_auxiliar()
    df = pd.read_excel(destino, sheet_name="Operacoes_1")
    alt = df[df["UFV"] == "Thopen - Altair"].iloc[0]
    assert alt["RESPONSÁVEL O&M"] == "Carla Souza"            # o nome padrão, como na AUXILIAR
    assert alt["CIDADE"] == "Altair" and alt["Base Equipe"] == "Guaraci/SP" and alt["Equipe Cluster"] == "SP Norte 02"
    # o motor pega a PRIMEIRA coluna com MWP: tem de ser a potência contratual
    mwp = next(c for c in df.columns if "MWP" in str(c).upper())
    assert alt[mwp] == pytest.approx(6.898)
    resp = next(c for c in df.columns if "RESPONS" in c.upper() and "O&M" in c.upper())
    assert resp == "RESPONSÁVEL O&M"


def test_marcador_e_equipe_local_viram_celula_vazia(srv, tmp_path):
    destino = tmp_path / A.NOME
    A.escrever(srv, destino)
    rio = pd.read_excel(destino).set_index("UFV").loc["Thopen - Rio do Fogo 1"]
    assert pd.isna(rio["RESPONSÁVEL O&M"]) and pd.isna(rio["Base Equipe"])      # "N/A" e "N/I" não são nome
    assert pd.isna(rio["Equipe Cluster"])          # equipe local: o motor abriria uma aba vazia para ela
    assert pd.isna(rio["CAPACIDADE INSTALADA (MWp)"])                          # texto herdado não vira porte


def test_estado_diz_de_onde_vem_e_o_que_falta(srv):
    ok = A.estado({"TESTING": True, "NEXUS_PCM_CADASTRO_TESTE": srv})
    assert ok["ok"] and "2 usinas" in ok["detalhe"] and "1 sem responsável" in ok["detalhe"]
    falta = A.estado({"TESTING": True})
    assert not falta["ok"] and "cadastro do Nexus" in falta["detalhe"]


def test_sem_chave_do_cadastro_nao_gera(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_CHAVE_CADASTRO", raising=False)
    with pytest.raises(A.SemCadastro):
        A.servico({"NEXUS_ARMAZEM_LOCAL": str(tmp_path / "x.json")})


def test_o_nome_do_arquivo_e_o_que_o_motor_procura():
    """08/10/2026: o nome do arquivo da AUXILIAR leva o de quem montou a planilha e o repositório é público; o Nexus o lê
    da cópia do motor (que não se edita) em vez de repeti-lo. Se o motor mudar o jeito de dizer o nome, isto acusa."""
    from pathlib import Path
    motor = (Path(A.__file__).parent / "motor" / "fonte_bd_api.py").read_text(encoding="utf-8")
    assert A.NOME.startswith("AUXILIAR - ") and A.NOME.endswith(".xlsx") and f'"{A.NOME}"' in motor
