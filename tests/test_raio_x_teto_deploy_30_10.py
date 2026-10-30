"""O Raio-X diz o que o deploy viu e fez com o teto de memória (30/10/2026). A 1ª versão do `deploy/atualizar.sh` que
tirava o teto (42e506c) rodou a cada 2 min e, às 15:13, o Raio-X ainda mostrava o nexus.service com 700 MB / 1 GB: o
Levi não tem acesso ao servidor nem ao journal, e ninguém via se o script tinha tirado, falhado ou se outra coisa punha o
teto de volta. Agora o script grava o que viu em `.git/nexus-teto` e o cartão da memória mostra. Aqui o arquivo é de
mentira."""
from pathlib import Path

from nexus.casca import raio_x as R

TEMPLATES = Path(R.__file__).resolve().parents[1] / "templates"
TI = "/etc/systemd/system/nexus.service.d/override.conf: MemoryHigh=700M MemoryMax=1G"


def _estado(tmp_path, monkeypatch, **campos):
    arq = tmp_path / "nexus-teto"
    base = {"quando": "2026-10-30T15:20:04-03:00", "unidade": "nexus.service", "grupo": "/system.slice/nexus.service",
            "piso_mb": "4096", "antes": "MemoryHigh=734003200 MemoryMax=1073741824", "fontes": "", "acao": "nada",
            "erro": "", "depois": "memory.high=max memory.max=max"}
    base.update(campos)
    arq.write_text("".join(f"{k}={v}\n" for k, v in base.items()), encoding="utf-8")
    monkeypatch.setattr(R, "ARQ_TETO_DEPLOY", arq)


def test_o_deploy_tirou_e_diz_onde_estava(tmp_path, monkeypatch):
    _estado(tmp_path, monkeypatch, acao="tirou", fontes=TI)
    t = R._teto_do_deploy()
    assert t["hora"] == "30/10 às 15:20" and t["texto"] == f"tirou o teto (estava em {TI})"


def test_sem_teto(tmp_path, monkeypatch):
    _estado(tmp_path, monkeypatch)
    assert R._teto_do_deploy()["texto"] == "sem teto abaixo de 4096 MB"


def test_o_teto_so_no_cgroup(tmp_path, monkeypatch):
    _estado(tmp_path, monkeypatch, acao="cgroup")
    assert R._teto_do_deploy()["texto"] == ("o teto estava só no cgroup, sem estar na unidade do systemd (alguém o escreve "
                                            "direto): escreveu max nele")


def test_o_que_falhou_vem_com_o_erro_e_onde_esta(tmp_path, monkeypatch):
    _estado(tmp_path, monkeypatch, acao="tirou", erro="o set-property falhou", fontes=TI,
            depois="memory.high=734003200 memory.max=1073741824")
    assert R._teto_do_deploy()["texto"] == (f"não conseguiu tirar o teto (o set-property falhou; está em {TI}; "
                                            "agora memory.high=734003200 memory.max=1073741824)")


def test_sem_o_arquivo_nao_diz_nada(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "ARQ_TETO_DEPLOY", tmp_path / "nao-existe")
    assert R._teto_do_deploy() is None


def test_a_tela_mostra_o_que_o_deploy_fez():
    from flask import Flask, render_template_string
    app = Flask(__name__, template_folder=str(TEMPLATES))
    trecho = (TEMPLATES / "raio_x.html").read_text(encoding="utf-8")
    linha = next(l for l in trecho.splitlines() if "Memória da máquina" in l)
    m = {"livre_gb": "6,9", "total_gb": "14,9", "tem_swap": True, "swap_gb": "2,0", "trocando_mb_s": "0",
         "nexus_mb": 714, "nexus_swap_mb": 1512, "pressao_mem": None, "pressao_io": None,
         "teto": {"onde": "/system.slice/nexus.service", "conteiner": False, "max_mb": 1024, "high_mb": 700,
                  "swap_max_mb": None, "apertos": 18802, "no_teto": 0, "oom": 0},
         "teto_deploy": {"hora": "30/10 às 15:20", "texto": f"tirou o teto (estava em {TI})"}}
    with app.app_context():
        h = render_template_string(linha, m=m)
        assert f"o deploy conferiu em 30/10 às 15:20: tirou o teto (estava em {TI})" in h
        m["teto_deploy"] = None
        assert "o deploy conferiu" not in render_template_string(linha, m=m)
