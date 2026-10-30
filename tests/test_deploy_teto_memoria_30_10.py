"""O `deploy/atualizar.sh` tira o teto de memória baixo do serviço do Nexus (30/10/2026).

O caso: o Raio-X mostrou o `nexus.service` com MemoryHigh=700M e MemoryMax=1024M, posto no servidor (não está no
`deploy/nexus.service`). O Linux apertou o Nexus 132.576 vezes numa manhã: 670 MB na RAM e 2,8 GB no swap, com 6,8 GB
livres na máquina, e o "clonar OS" do OS Creator preso 13 min. Levi, 30/10/2026: "esse swap tá foda", e escolheu
"Tirar o teto pelo deploy". O script roda como root a cada 2 min; em toda rodada (também na de "nada a fazer"), o
MemoryHigh ou MemoryMax abaixo do piso (4 GB, `NEXUS_MEMORIA_PISO_MB`) vira `infinity` pelo `systemctl set-property`, que
vale na hora, sem restart. Teto acima do piso é decisão da T.I. e fica. Os falsos são os do test_deploy_atualizar.
"""
import pytest

from test_deploy_atualizar import BASH, Servidor

pytestmark = pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")

MB = 1024 * 1024


def _teto(s, **props):
    for prop, valor in props.items():
        (s.controle / f"teto_{prop}").write_text(f"{valor}\n")


def _sets(s):
    return [x for x in s.log.read_text().splitlines() if x.startswith("systemctl set-property")]


def test_o_teto_do_servidor_sai_mesmo_sem_commit_novo(tmp_path):
    s = Servidor(tmp_path)
    assert s.rodar()[0] == 0                                           # instalado: as próximas são "nada a fazer"
    _teto(s, MemoryHigh=700 * MB, MemoryMax=1024 * MB)
    codigo, feito, saida = s.rodar()
    assert codigo == 0 and feito == ["systemctl"], saida
    assert _sets(s) == ["systemctl set-property nexus MemoryHigh=infinity MemoryMax=infinity"]
    assert "teto de memória" in saida and "nada a fazer" in saida


def test_teto_acima_do_piso_e_da_ti_e_fica(tmp_path):
    s = Servidor(tmp_path)
    _teto(s, MemoryHigh=6 * 1024 * MB, MemoryMax="infinity")
    codigo, feito, saida = s.rodar()
    assert codigo == 0 and _sets(s) == [] and feito == ["pip", "python", "systemctl"], saida


def test_so_o_que_esta_abaixo_do_piso_sai(tmp_path):
    s = Servidor(tmp_path)
    s.rodar()
    _teto(s, MemoryHigh="infinity", MemoryMax=1024 * MB)
    s.rodar()
    assert _sets(s) == ["systemctl set-property nexus MemoryMax=infinity"]
    _teto(s, MemoryHigh=3072 * MB, MemoryMax=4096 * MB)               # 3 GB sai; 4 GB, o piso, fica
    s.rodar()
    assert _sets(s) == ["systemctl set-property nexus MemoryHigh=infinity"]
    _teto(s, MemoryHigh=2048 * MB, MemoryMax="infinity")
    s.rodar(NEXUS_MEMORIA_PISO_MB="1024")                              # o piso é configurável
    assert _sets(s) == []


def test_o_set_property_que_falha_nao_segura_o_deploy(tmp_path):
    s = Servidor(tmp_path)
    _teto(s, MemoryHigh=700 * MB)
    s.falhar("set_falha")
    codigo, feito, saida = s.rodar()
    assert codigo == 0 and feito == ["systemctl", "pip", "python", "systemctl"], saida
    assert "AVISO" in saida
