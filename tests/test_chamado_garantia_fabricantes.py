"""A lista de fabricantes do chamado de garantia é a do Nexus > Chamados > Fabricantes (Levi, 20/10/2026):

    "1 - corrija canadian  2 - insira NCU e RSU  3 - Essa lista tem que ser a mesma do nexus > fabricantes: ele escolhe o
    fabricante o app já filtra se é inversor, cabine etc  4 - Se a lista de fabricantes do chamados > fabricantes tiver
    nome diferentes do fractall altere o nome em fabricante! ... quero também que quando a singrid adicione novos
    fabricantes em chamados > fabricantes apareça atualizado no app"

O que se trava aqui, no pacote `chamado_garantia` (o MESMO no OS Creator e no App de Campo):
- a marca no nome do ativo vale como palavra inteira e pelos apelidos do Fracttal (`APELIDOS_NO_FRACTTAL`);
- `registro`: as linhas da aba `os_creator · chamado_modelos` por cima do código, em memória e no lugar; fornecedor novo
  entra na lista dos tipos que atende e passa a ser reconhecido no nome; arquivado sai;
- o `chamado_modelos_store` do OS Creator aplica pela mesma regra (e o canal, que é só dele).
Nomes de ativo de mentira no formato do Fracttal: o repositório é público."""
import json
import sys

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import chamado_modelos_store as cms  # noqa: E402 — do clone (e ele põe a pasta do pacote no sys.path)
import chamado_spec as cs  # noqa: E402
from chamado_garantia import registro as R  # noqa: E402
from chamado_garantia import regras  # noqa: E402
from chamado_garantia import spec as sp  # noqa: E402


@pytest.fixture(autouse=True)
def _codigo_puro():
    """Cada teste começa e termina com o pacote no código (o `aplicar` mexe em estruturas do módulo)."""
    cms.aplicar({})
    yield
    cms.aplicar({})


def _ativo(desc, code="TST100-INVR1.1"):
    return {"code": code, "description": "%s     { %s }" % (desc, code), "label": "%s — %s" % (code, desc)}


def _linha(chave, **valor):
    return {"chave": chave, "valor": json.dumps(valor, ensure_ascii=False)}


# ── 1. a marca no nome do ativo ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("desc,marca", [
    ("Inversor 1.1 Huawei SUN2000-250KTL-H1", "Huawei"),
    ("Inversor 1.1 CANANDIAN SOLAR", "Canadian Solar"),           # como está no Fracttal (80 inversores, 20/10)
    ("Inversor (P.E.) 1.1  SUN2000-60KTL-H0", "Huawei"),          # só o modelo
    ("Inversor 1.1 HUAWEII SUN2000-100KTL", "Huawei"),
    ("Inversor 1.1 Sungrow SUN2000-100KTL-H1", "Sungrow"),        # o nome vale antes do apelido, como antes
    ("Tracker 1.100 AXIALtracker", "Axial"),
    ("Tracker 1.100 AXIALtracker1V", "Axial"),
    ("Tracker 1.100 STI H250 Dual Row", "STI"),
    ("Tracker 1.100 STI-H250", "STI"),
    ("Tracker 133.100 Trina Vanguard 1P", "Trina"),
    # o "STI" como pedaço de palavra era marca até 20/10 (16 cabines, skids e estações)
    ("Cabine 1 Sítio Araponga, S/N, Distrito de Justiniano de Serpa", ""),
    ("SKID 1 FAZENDA SÃO SEBASTIÃO, ZONA RURAL", ""),
    ("Estação Meteorológica Rua das Plásticas Elásticas", ""),
    ("Cabine 1 Rede coaxial", ""),
    ("NCU 1", ""),
])
def test_a_marca_vale_como_palavra_inteira_e_pelos_apelidos_do_fracttal(desc, marca):
    assert sp.marca_do_ativo(_ativo(desc)) == marca
    assert regras.marca_do_ativo(_ativo(desc)) == marca                # a regra é uma só


def test_o_codigo_da_usina_nao_e_marca():
    """Santo Inácio é STI100 no Fracttal: o código não faz os trackers dela virarem STI."""
    assert sp.marca_do_ativo(_ativo("Tracker 1.100", "STI100-ETKR1.100")) == ""


# ── 2. NCU e RSU pela marca dos trackers da mesma usina ────────────────────────────────────────────────────────
def test_ncu_e_rsu_pegam_a_marca_dos_trackers_da_usina():
    cat = [dict(_ativo("Tracker 1.%d STI Norland" % i, "TST100-ETKR1.%d" % i), usina="Usina Teste") for i in range(3)]
    ncu = dict(_ativo("NCU 1", "TST100-NCU1"), usina="Usina Teste", tipo="NCU")
    assert regras.descobrir_marca(ncu, cat) == "STI"
    rsu = dict(_ativo("RSU 2", "TST100-RSU2"), usina="Usina Teste", tipo="RSU")
    assert regras.descobrir_marca(rsu, cat) == "STI"
    # duas marcas na usina: não chuta
    cat.append(dict(_ativo("Tracker 9.1 Brametal", "TST100-ETKR9.1"), usina="Usina Teste"))
    assert regras.descobrir_marca(ncu, cat) == ""


# ── 3. a lista é a do Nexus > Fabricantes ──────────────────────────────────────────────────────────────────────
def test_sem_nada_no_banco_vale_o_codigo():
    R.aplicar({})
    assert R.fornecedores("Inversor") == ["Canadian Solar", "Huawei", "Sungrow"]
    assert R.fornecedores("NCU") == ["Brametal", "STI", "Soltec"]
    assert R.fornecedores("Cabine") == ["Convert"]
    assert set(R.semente()) == {"BASE", *("TIPO:" + t for t in sp.POR_TIPO),
                                *("MARCA:" + m for m in ("Axial", "Brametal", "Canadian Solar", "Convert", "Huawei",
                                                         "Hukseflux", "Romiotto", "STI", "Soltec", "Sungrow", "Trina"))}


def test_fornecedor_novo_no_banco_entra_na_lista_do_tipo_e_e_reconhecido_no_nome():
    banco = R.de_linhas([_linha("MARCA:Fronius", subtarefas=[], canal="Portal Fronius", atende=["Inversor"],
                                arquivado=False, versao="2026-10-20T10:00:00-03:00", por="Analista Teste")])
    R.aplicar(banco)
    assert R.fornecedores("Inversor") == ["Canadian Solar", "Fronius", "Huawei", "Sungrow"]
    assert "Fronius" not in R.fornecedores("Estrutura Trackers")          # só nos tipos que ele atende
    assert sp.marca_do_ativo(_ativo("Inversor 1.1 Fronius Symo 20.0")) == "Fronius"
    # as listas que outros módulos importaram são as MESMAS (o aplicar troca no lugar)
    from chamado_garantia import POR_FABRICANTE, TIPOS_DA_MARCA
    assert POR_FABRICANTE is sp.POR_FABRICANTE and "Fronius" in POR_FABRICANTE and "Fronius" in TIPOS_DA_MARCA
    # a inspeção do Fronius tem a base e o bloco do inversor
    assert len(sp.subtarefas("Inversor", "Fronius")) == len(sp.BASE) + len(sp.POR_TIPO["Inversor"])


def test_arquivado_sai_da_lista_e_o_clone_segue_o_original():
    banco = R.de_linhas([_linha("MARCA:Sungrow", subtarefas=[], canal="", atende=["Inversor"], arquivado=True,
                                versao="2026-10-20T10:00:00-03:00", por="Analista Teste")])
    R.aplicar(banco)
    assert "Sungrow" not in R.fornecedores("Inversor")
    assert sp.POR_FABRICANTE["Brametal"] is sp.POR_FABRICANTE["STI"]


def test_linha_estragada_e_chave_estranha_sao_puladas_e_a_mais_nova_vence():
    linhas = [{"chave": "MARCA:Quebrada", "valor": "{nao é json"}, {"chave": "OUTRA:Coisa", "valor": "{}"},
              _linha("MARCA:Kaco", subtarefas=[], atende=["Inversor"], versao="2026-10-01T10:00:00-03:00"),
              _linha("MARCA:Kaco", subtarefas=[], atende=["Inversor", "Skid"], versao="2026-10-02T10:00:00-03:00")]
    banco = R.de_linhas(linhas)
    assert list(banco) == ["MARCA:Kaco"] and banco["MARCA:Kaco"]["atende"] == ["Inversor", "Skid"]
    R.aplicar(banco)
    assert "Kaco" in R.fornecedores("Skid")


# ── o OS Creator aplica pela mesma regra ────────────────────────────────────────────────────────────────────────
def test_o_os_creator_aplica_pelo_pacote_e_o_canal_e_dele():
    assert cms.semente() == R.semente(cms._ORIG["CANAL"]) and cms.semente()["MARCA:Huawei"]["canal"] == cs.CANAL["Huawei"]
    banco = R.de_linhas([_linha("MARCA:Fronius", subtarefas=[], canal="Portal Fronius", atende=["Inversor"],
                                versao="2026-10-20T10:00:00-03:00", por="Analista Teste")])
    cms.aplicar(banco)
    assert cs.CANAL["Fronius"] == "Portal Fronius" and "Fronius" in sp.marcas_para("Inversor")
    assert cms.efetivo(banco)["MARCA:Fronius"]["origem"] == "banco"
    cms.aplicar({})
    assert "Fronius" not in cs.CANAL and "Fronius" not in sp.marcas_para("Inversor")
