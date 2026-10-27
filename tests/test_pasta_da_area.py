"""A trava da área de cada pessoa (`.github/workflows/pasta-da-area.yml`): o COS desde 05/10/2026 e a Engenharia desde
27/10/2026 (Levi: "gostaria que ele pudesse editar somente a parte de engenharia"). O GitHub não dá permissão por
pasta; a regra da main exige pull request com esta conferência verde. Aqui o script da conferência roda de verdade, no
bash, com um `gh` de mentira que devolve a lista de arquivos do pedido. Logins de mentira (repositório público)."""
import shutil
import subprocess
from pathlib import Path

import pytest

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pasta-da-area.yml"


def _job():
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load(WF.read_text(encoding="utf-8"))
    return d, d["jobs"]["pasta-da-area"]


def _bash():
    b = shutil.which("bash")
    # o bash do WSL (System32) não enxerga os caminhos do Windows: sem um bash de verdade, o teste do script pula
    if not b or "system32" in b.lower():
        pytest.skip("sem um bash POSIX neste computador")
    return b


def _roda(autor, arquivos, logins_cos="pessoa-cos", logins_eng="pessoa-eng", renomeados=()):
    """Roda o script da conferência: `arquivos` é a lista do pedido; `renomeados` são os nomes antigos."""
    _d, job = _job()
    passo = job["steps"][0]
    env = {k: str(v) for k, v in passo["env"].items() if not str(v).startswith("${{")}
    linhas = list(arquivos) + list(renomeados)
    env.update(GH_TOKEN="x", REPO="dono/repo", BASE="a", HEAD="b", AUTOR=autor, LOGINS_COS=logins_cos,
               LOGINS_ENGENHARIA=logins_eng, PATH=str(Path(_bash()).parent))
    # o gh de mentira: a contagem e a lista dos arquivos da comparação
    falso = ("gh() { case \"$*\" in *length*) echo %d;; *) printf '%%s\\n' %s;; esac; }\n"
             % (len(arquivos), " ".join("'%s'" % a for a in linhas)))
    # o script vai pela entrada, não pelo -c: no Windows, a linha de comando longa (300 arquivos) saía vazia e com 0
    r = subprocess.run([_bash(), "-s"], input=falso + passo["run"], env=env, capture_output=True, encoding="utf-8",
                       timeout=60)
    return r.returncode, r.stdout + r.stderr


ENG = ["nexus/torres/engenharia/__init__.py", "nexus/torres/engenharia/templates/engenharia/etm.html",
       "nexus/engenharia/etm.py", "nexus/static/engenharia.css", "nexus/static/engenharia-gaveta.js",
       "tests/test_engenharia_etm.py", "nexus/torres/engenharia/CLAUDE.md",
       "docs/superpowers/specs/2026-10-26-engenharia-etm-design.md"]


def test_a_conferencia_roda_a_versao_da_main_e_nao_executa_o_pedido():
    # pull_request_target roda o arquivo da main: o pedido não troca a própria conferência; e nada do pedido é baixado
    d, job = _job()
    gatilho = d.get("on") or d.get(True)          # o YAML lê "on" como True
    assert list(gatilho) == ["pull_request_target"]
    assert job["name"] == "pasta-da-area" and len(job["steps"]) == 1 and "uses" not in job["steps"][0]
    assert d["permissions"] == {"contents": "read", "pull-requests": "read"}


def test_quem_e_de_cada_area_mora_nas_variaveis_e_nao_no_arquivo():
    # o repositório é público e o login traz o nome da pessoa: só os administradores ficam escritos
    _d, job = _job()
    env = job["steps"][0]["env"]
    assert env["LOGINS_COS"] == "${{ vars.LOGINS_COS }}" and env["LOGINS_ENGENHARIA"] == "${{ vars.LOGINS_ENGENHARIA }}"
    assert env["LIVRES"].split() == ["Levi-6242", "admin-gridco"]


def test_quem_e_da_engenharia_passa_so_com_a_area_dela():
    ok, saida = _roda("pessoa-eng", ENG)
    assert ok == 0, saida
    # o catálogo dos dados, a ponte do OS Creator, a casca e a própria conferência são do Levi
    for fora in ("nexus/dados/catalogo.py", "nexus/torres/oscreator/ponte.py", "nexus/static/nexus.css",
                 ".github/workflows/pasta-da-area.yml", "nexus/torres/cos/__init__.py", "CLAUDE.md",
                 "docs/superpowers/specs/2026-10-09-performance-no-nexus-design.md"):
        ok, saida = _roda("pessoa-eng", ENG[:1] + [fora])
        assert ok == 1 and fora in saida, fora


def test_quem_e_do_cos_segue_so_com_a_do_cos():
    assert _roda("pessoa-cos", ["nexus/torres/cos/__init__.py", "nexus/cos/regra.py", "nexus/static/cos.css",
                                "tests/test_cos_ronda.py"])[0] == 0
    ok, saida = _roda("pessoa-cos", ["nexus/torres/cos/__init__.py", "nexus/engenharia/etm.py"])
    assert ok == 1 and "nexus/engenharia/etm.py" in saida


def test_administrador_passa_direto_e_login_sem_area_vai_para_o_levi():
    assert _roda("Levi-6242", ["nexus/dados/catalogo.py"])[0] == 0
    ok, saida = _roda("pessoa-nova", ENG[:1])
    assert ok == 1 and "não tem área" in saida


def test_o_login_casa_sem_caixa_e_quem_e_de_duas_areas_tem_as_duas():
    assert _roda("Pessoa-Eng", ENG[:1], logins_eng="pessoa-eng")[0] == 0
    assert _roda("pessoa-x", ["nexus/torres/cos/__init__.py", "nexus/engenharia/etm.py"], logins_cos="pessoa-x",
                 logins_eng="outra pessoa-x")[0] == 0


def test_renomear_de_fora_para_dentro_tambem_e_mexer_fora():
    ok, saida = _roda("pessoa-eng", ["nexus/engenharia/novo.py"], renomeados=["nexus/casca/__init__.py"])
    assert ok == 1 and "nexus/casca/__init__.py" in saida


def test_pedido_grande_demais_vai_para_o_levi():
    ok, saida = _roda("pessoa-eng", ["nexus/engenharia/a%d.py" % i for i in range(300)])
    assert ok == 1 and "grande demais" in saida
