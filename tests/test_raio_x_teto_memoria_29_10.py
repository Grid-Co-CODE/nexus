"""O teto de memória do Nexus no Raio-X (29/10/2026). Em cinco leituras de dois dias o Nexus ficou SEMPRE com ~700 MB
na memória (662, 689, 705, 707 e 710 MB) e o resto no swap, 1,5 a 2,2 GB, com 5,7 a 7 GB livres na máquina: o Linux só
troca assim quando o grupo do processo tem teto (o MemoryHigh/MemoryMax do systemd, o --memory do Docker). O Levi não
tem acesso ao servidor, então o Raio-X diz o teto pelo cgroup do próprio processo. Aqui o /proc e o /sys são de
mentira."""
from pathlib import Path

from nexus.casca import raio_x as R

TEMPLATES = Path(R.__file__).resolve().parents[1] / "templates"

MB = 1024 * 1024


def _sistema(monkeypatch, cgroup, arquivos, docker=False):
    monkeypatch.setattr(R, "_ler_proc", lambda nome: cgroup if nome == "self/cgroup" else "")
    monkeypatch.setattr(R, "_ler_arquivo", lambda caminho: arquivos.get(caminho))
    monkeypatch.setattr(R.os.path, "exists", lambda c: docker and c == "/.dockerenv")


def test_servico_do_systemd_com_teto(monkeypatch):
    base = "/sys/fs/cgroup/system.slice/nexus.service"
    _sistema(monkeypatch, "0::/system.slice/nexus.service\n", {
        f"{base}/memory.max": "max", f"{base}/memory.high": str(700 * MB), f"{base}/memory.swap.max": "max",
        f"{base}/memory.events": "low 0\nhigh 18234\nmax 0\noom 0\noom_kill 0\n"})
    t = R._teto_nexus()
    assert (t["high_mb"], t["max_mb"], t["swap_max_mb"]) == (700, None, None)
    assert (t["apertos"], t["no_teto"], t["oom"], t["onde"], t["conteiner"]) == (18234, 0, 0,
                                                                                 "/system.slice/nexus.service", False)


def test_conteiner_le_a_raiz_do_cgroup(monkeypatch):
    _sistema(monkeypatch, "0::/\n", {"/sys/fs/cgroup/memory.max": str(768 * MB),
                                     "/sys/fs/cgroup/memory.high": "max",
                                     "/sys/fs/cgroup/memory.swap.max": str(2048 * MB)}, docker=True)
    t = R._teto_nexus()
    assert (t["max_mb"], t["high_mb"], t["swap_max_mb"], t["conteiner"]) == (768, None, 2048, True)


def test_sem_teto(monkeypatch):
    base = "/sys/fs/cgroup/system.slice/nexus.service"
    _sistema(monkeypatch, "0::/system.slice/nexus.service\n", {
        f"{base}/memory.max": "max", f"{base}/memory.high": "max", f"{base}/memory.swap.max": "max"})
    t = R._teto_nexus()
    assert (t["max_mb"], t["high_mb"], t["swap_max_mb"]) == (None, None, None)


def test_cgroup_v1(monkeypatch):
    base = "/sys/fs/cgroup/memory/system.slice/nexus.service"
    _sistema(monkeypatch, "5:memory:/system.slice/nexus.service\n1:cpu:/x\n", {
        f"{base}/memory.limit_in_bytes": str(1024 * MB), f"{base}/memory.memsw.limit_in_bytes": str(3072 * MB)})
    t = R._teto_nexus()
    assert (t["max_mb"], t["swap_max_mb"]) == (1024, 2048)
    _sistema(monkeypatch, "5:memory:/\n", {"/sys/fs/cgroup/memory/memory.limit_in_bytes": str(2 ** 63 - 4096)})
    assert R._teto_nexus()["max_mb"] is None                        # o "sem teto" do v1 é um número gigante


def test_fora_do_linux():
    assert R._teto_nexus() is None or isinstance(R._teto_nexus(), dict)


def test_a_tela_mostra_o_teto(monkeypatch):
    from flask import Flask, render_template_string
    app = Flask(__name__, template_folder=str(TEMPLATES))
    trecho = (TEMPLATES / "raio_x.html").read_text(encoding="utf-8")
    linha = next(l for l in trecho.splitlines() if "Memória da máquina" in l)
    m = {"livre_gb": "7,0", "total_gb": "14,9", "tem_swap": True, "swap_gb": "2,0", "trocando_mb_s": "0",
         "nexus_mb": 707, "nexus_swap_mb": 1481, "pressao_mem": None, "pressao_io": None,
         "teto": {"onde": "/system.slice/nexus.service", "conteiner": False, "max_mb": None, "high_mb": 700,
                  "swap_max_mb": None, "apertos": 18234, "no_teto": 0, "oom": 0}}
    with app.app_context():
        h = render_template_string(linha, m=m)
        assert "Teto do Nexus</b>: aperta acima de 700 MB (grupo /system.slice/nexus.service)" in h
        assert "o Linux apertou o Nexus 18234 vezes" in h
        m["teto"].update(high_mb=None)
        assert "Teto do Nexus</b>: nenhum" in render_template_string(linha, m=m)


def test_conteiner_que_ve_o_caminho_do_host_le_a_raiz(monkeypatch):
    # sem o namespace de cgroup, o contêiner vê "/docker/<id>" no /proc, mas os arquivos dele estão na raiz do /sys
    _sistema(monkeypatch, "0::/docker/abc123\n", {"/sys/fs/cgroup/memory.max": str(1024 * MB)}, docker=True)
    assert R._teto_nexus()["max_mb"] == 1024
