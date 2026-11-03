"""O `deploy/atualizar.sh` tira o teto de memória baixo do serviço do Nexus (30/10/2026).

O caso: o Raio-X mostrou o `nexus.service` com MemoryHigh=700M e MemoryMax=1024M, posto no servidor (não está no
`deploy/nexus.service`). O Linux apertou o Nexus 132.576 vezes numa manhã: 670 MB na RAM e 2,8 GB no swap, com 6,8 GB
livres na máquina, e o "clonar OS" do OS Creator preso 13 min. Levi, 30/10/2026: "esse swap tá foda", e escolheu
"Tirar o teto pelo deploy". A 1ª versão (42e506c) só chamava o `systemctl set-property` e, às 15:13, o Raio-X ainda
mostrava o teto (18.802 apertos desde o restart das 14:38), com o deploy rodando a cada 2 min: Levi, "ainda indo para
swap, você não resolveu nada". Sem acesso ao servidor, não dá para ver por quê; daí os três caminhos, e o que o script
viu e fez gravado para o Raio-X mostrar:
- um drop-in próprio, `zz-nexus-sem-teto.conf` (o systemd aplica os drop-ins em ordem de NOME, de todas as pastas: o
  `override.conf` do `systemctl edit` vence o `50-MemoryHigh.conf` do set-property no próximo daemon-reload, o `zz-` não
  perde), com o daemon-reload só quando ele muda;
- o `set-property`, que vale na hora;
- o `max` escrito direto no cgroup do serviço, também quando quem põe o teto não é a unidade.
Teto acima do piso (4 GB, `NEXUS_MEMORIA_PISO_MB`) é decisão da T.I. e fica. Os falsos são os do test_deploy_atualizar.
"""
import pytest

from test_deploy_atualizar import BASH, Servidor

pytestmark = pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")

MB = 1024 * 1024
GRUPO = "system.slice/nexus.service"


def _unidade(s, **props):
    for prop, valor in props.items():
        (s.controle / f"show_{prop}").write_text(f"{valor}\n")


def _cgroup(s, **arquivos):
    pasta = s.cgroup / GRUPO
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, valor in arquivos.items():
        (pasta / nome.replace("_", ".")).write_text(f"{valor}\n")


def _no_cgroup(s, nome):
    return (s.cgroup / GRUPO / nome).read_text().strip()


def _feito(s):
    return [x for x in s.log.read_text().splitlines() if x.startswith("systemctl ")]


def _estado(s) -> dict:
    texto = (s.clone / ".git" / "nexus-teto").read_text(encoding="utf-8")
    return dict(l.split("=", 1) for l in texto.splitlines() if "=" in l)


DROPIN = "nexus.service.d/zz-nexus-sem-teto.conf"


def _teto_da_ti(s):
    """O teto como o servidor tinha: um override.conf com as duas linhas, a unidade e o cgroup com 700M e 1G."""
    ti = s.systemd / "nexus.service.d" / "override.conf"
    ti.parent.mkdir(parents=True, exist_ok=True)
    ti.write_text("[Service]\nMemoryHigh=700M\nMemoryMax=1G\n")
    _unidade(s, MemoryHigh=700 * MB, MemoryMax=1024 * MB, DropInPaths=ti.as_posix())
    _cgroup(s, memory_high=700 * MB, memory_max=1024 * MB)
    return ti


def test_o_teto_sai_pelo_dropin_pelo_set_property_e_pelo_cgroup_mesmo_sem_commit_novo(tmp_path):
    s = Servidor(tmp_path)
    assert s.rodar()[0] == 0                                           # instalado: as próximas são "nada a fazer"
    ti = _teto_da_ti(s)
    codigo, feito, saida = s.rodar()
    assert codigo == 0 and "nada a fazer" in saida, saida
    assert _feito(s) == ["systemctl daemon-reload",
                         "systemctl set-property nexus.service MemoryHigh=infinity MemoryMax=infinity"]
    dropin = (s.systemd / DROPIN).read_text()
    assert "MemoryHigh=infinity" in dropin and "MemoryMax=infinity" in dropin and "[Service]" in dropin
    assert (_no_cgroup(s, "memory.high"), _no_cgroup(s, "memory.max")) == ("max", "max")
    e = _estado(s)
    assert e["acao"] == "tirou" and e["erro"] == "" and e["grupo"] == "/" + GRUPO
    assert f"{ti.as_posix()}: MemoryHigh=700M MemoryMax=1G" in e["fontes"]
    assert f"memory.high={700 * MB}" in e["antes"] and e["depois"] == "memory.high=max memory.max=max"


def test_o_dropin_que_ja_esta_certo_nao_rele_o_systemd_de_novo(tmp_path):
    s = Servidor(tmp_path)
    s.rodar()
    _teto_da_ti(s)
    s.rodar()
    _cgroup(s, memory_high=700 * MB, memory_max=1024 * MB)           # o teto voltou (outro daemon-reload, outro restart)
    s.rodar()
    assert _feito(s) == ["systemctl set-property nexus.service MemoryHigh=infinity MemoryMax=infinity"]
    assert _no_cgroup(s, "memory.high") == "max"


def test_teto_acima_do_piso_e_da_ti_e_fica(tmp_path):
    s = Servidor(tmp_path)
    _unidade(s, MemoryHigh=6 * 1024 * MB)
    _cgroup(s, memory_high=6 * 1024 * MB, memory_max="max")
    codigo, feito, saida = s.rodar()
    assert codigo == 0 and feito == ["pip", "python", "systemctl"], saida
    assert not (s.systemd / DROPIN).exists() and _no_cgroup(s, "memory.high") == str(6 * 1024 * MB)
    assert _estado(s)["acao"] == "nada"


def test_o_piso(tmp_path):
    s = Servidor(tmp_path)
    s.rodar()
    _unidade(s, MemoryHigh=3072 * MB, MemoryMax=4096 * MB)            # 3 GB sai; 4 GB, o piso, fica
    s.rodar()
    assert _feito(s)[-1] == "systemctl set-property nexus.service MemoryHigh=infinity MemoryMax=infinity"
    (s.systemd / DROPIN).unlink()
    _unidade(s, MemoryHigh=4096 * MB, MemoryMax=4096 * MB)
    s.rodar()
    assert _feito(s) == []
    _unidade(s, MemoryHigh=2048 * MB)
    s.rodar(NEXUS_MEMORIA_PISO_MB="1024")                              # o piso é configurável
    assert _feito(s) == []


def test_o_teto_que_so_esta_no_cgroup_sai_direto_dele(tmp_path):
    # a unidade sem teto e o cgroup com: quem põe não é o systemd (um script que escreve no cgroup)
    s = Servidor(tmp_path)
    s.rodar()
    _cgroup(s, memory_high=700 * MB, memory_max="max")
    codigo, feito, saida = s.rodar()
    assert codigo == 0 and _feito(s) == [] and not (s.systemd / DROPIN).exists(), saida
    assert _no_cgroup(s, "memory.high") == "max"
    assert _estado(s)["acao"] == "cgroup"


def test_o_que_falha_avisa_e_nao_segura_o_deploy(tmp_path):
    s = Servidor(tmp_path)
    _teto_da_ti(s)
    s.falhar("set_falha")
    codigo, feito, saida = s.rodar()
    assert codigo == 0 and feito == ["systemctl", "systemctl", "pip", "python", "systemctl"], saida
    assert "AVISO" in saida and "set-property" in _estado(s)["erro"]


def test_sem_teto_o_estado_diz_que_conferiu(tmp_path):
    s = Servidor(tmp_path)
    codigo, feito, saida = s.rodar()
    assert codigo == 0 and feito == ["pip", "python", "systemctl"], saida
    e = _estado(s)
    assert e["acao"] == "nada" and e["quando"].startswith("20") and e["piso_mb"] == "4096"
