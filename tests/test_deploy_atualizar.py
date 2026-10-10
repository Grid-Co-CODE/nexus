"""O `deploy/atualizar.sh` (auditoria A6 da porta única, 10/10/2026).

O caso: o `reportlab` entrou no requirements.txt em 09/10 e é importado no boot (o relatório dos extintores). O script
só rodava o pip quando o `requirements.txt` mudava ENTRE o commit de antes e o de depois do pull. Se o pip falhasse na 1ª
rodada (sem saída para o pypi, por exemplo), o `set -e` parava antes do restart, com o código novo já no disco; a 2ª
rodada (o timer, 2 min depois) via o mesmo commit e dizia "nada a fazer", e com `--forcar` pulava o pip e reiniciava: o
Nexus novo não subia e o `Restart=always` o deixava caindo em laço, com a entrada da empresa em 502. Agora:
- o pip roda SEMPRE antes de todo restart (é idempotente e rápido quando nada mudou);
- o boot é conferido antes do restart (`deploy/conferir_boot.py`): falhou, para ali e o Nexus de antes segue no ar;
- "nada a fazer" é quando o commit do clone é o último INSTALADO (a marca em `.git/nexus-instalado`), e não o de antes do
  pull: a rodada que parou no meio é completada pela seguinte.
Aqui: o texto do script (em qualquer máquina), o `conferir_boot.py` de verdade, e o script rodado num clone de mentira
com o bash do Git (no Windows) ou o do sistema, com `sudo`, `systemctl` e `curl` falsos.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "deploy" / "atualizar.sh"
CONFERIR = RAIZ / "deploy" / "conferir_boot.py"


# ── o texto do script ─────────────────────────────────────────────────────────────────────────────────────────────────
def _blocos_if(linhas, condicao):
    """Os trechos (início, fim) de cada `if` cuja linha tem `condicao`, casando o `fi` pelo aninhamento."""
    blocos = []
    for i, linha in enumerate(linhas):
        if re.match(r"\s*(if|elif)\b", linha) and condicao in linha:
            nivel = 0
            for j in range(i, len(linhas)):
                if re.match(r"\s*if\b", linhas[j]):
                    nivel += 1
                if re.match(r"\s*fi\b", linhas[j]):
                    nivel -= 1
                    if nivel == 0:
                        blocos.append((i, j))
                        break
    return blocos


def test_o_pip_nao_depende_de_vir_commit_novo():
    linhas = SCRIPT.read_text(encoding="utf-8").splitlines()
    pip = [i for i, x in enumerate(linhas) if "pip install" in x and not x.lstrip().startswith("#")]
    assert pip, "o script não instala as dependências"
    # nem no if do commit novo, nem no do "o requirements.txt mudou" (o git diff), como era até 10/10
    for ini, fim in _blocos_if(linhas, '"$antes" != "$depois"') + _blocos_if(linhas, "git diff"):
        assert not any(ini <= i <= fim for i in pip), f"o pip está dentro do if das linhas {ini + 1}-{fim + 1}"


def test_pip_e_conferencia_do_boot_vem_antes_do_restart():
    texto = SCRIPT.read_text(encoding="utf-8")
    codigo = "\n".join(x for x in texto.splitlines() if not x.lstrip().startswith("#"))
    assert codigo.index("pip install") < codigo.index("conferir_boot.py") < codigo.index("systemctl restart")
    assert "set -euo pipefail" in codigo


# ── o conferir_boot.py de verdade ─────────────────────────────────────────────────────────────────────────────────────
# a saída do Python filho em UTF-8 também no console do Windows (no servidor já é)
_ENV_UTF8 = dict(os.environ, PYTHONIOENCODING="utf-8")


def test_o_boot_conferido_passa_nesta_maquina():
    r = subprocess.run([sys.executable, "-B", str(CONFERIR)], capture_output=True, text=True, encoding="utf-8",
                       timeout=300, cwd=str(RAIZ), env=_ENV_UTF8)
    assert r.returncode == 0, r.stderr
    assert "Boot conferido" in r.stdout


@pytest.mark.parametrize("falta", ["reportlab", "waitress", "nexus.hseq.relatorio"])
def test_sem_uma_dependencia_do_boot_a_conferencia_falha(falta):
    """O módulo vira None em sys.modules: o `import` dele levanta ImportError, como sem o pacote instalado."""
    script = ("import runpy, sys; sys.modules[%r] = None; runpy.run_path(%r, run_name='__main__')" % (falta, str(CONFERIR)))
    r = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, encoding="utf-8",
                       timeout=300, cwd=str(RAIZ), env=_ENV_UTF8)
    assert r.returncode == 1
    assert "ERRO" in r.stderr and "Boot conferido" not in r.stdout


# ── o script rodado num clone de mentira ─────────────────────────────────────────────────────────────────────────────
def _bash():
    if os.name == "nt":
        # o bash do Git (o do System32 é o do WSL, que não enxerga estes caminhos). O Git\usr\bin\bash.exe, e não o
        # Git\bin\bash.exe: este é um lançador que põe /mingw64/bin e /usr/bin na frente do PATH, e os comandos falsos
        # (sudo, systemctl, curl) não seriam achados
        git = shutil.which("git")
        if not git:
            return None
        # Git\cmd\git.exe (no PATH do Windows) ou Git\mingw64\bin\git.exe (no PATH do próprio bash do Git)
        for base in Path(git).resolve().parents[:3]:
            c = base / "usr" / "bin" / "bash.exe"
            if c.exists():
                return str(c)
        return None
    return shutil.which("bash")


BASH = _bash()

_FALSOS = {
    # roda como root; o dono do clone e o do .venv são um "dono" qualquer
    "id": 'if [ "${1:-}" = "-u" ]; then echo 0; else echo "uid=0(root)"; fi',
    "stat": 'echo dono',
    "sudo": 'if [ "${1:-}" = "-u" ]; then shift 2; fi; exec "$@"',
    "systemctl": 'echo "systemctl $*" >> "$NEXUS_TESTE_LOG"',
    "sleep": ':',
    # o /saude do Nexus que acabou de subir responde com o commit do clone
    "curl": 'printf \'{"commit":"%s","ok":true}\' "$(git rev-parse --short HEAD)"',
}
_PIP = 'echo "pip $*" >> "$NEXUS_TESTE_LOG"; [ ! -e "$NEXUS_TESTE_CONTROLE/pip_falha" ]'
_PYTHON = 'echo "python $*" >> "$NEXUS_TESTE_LOG"; [ ! -e "$NEXUS_TESTE_CONTROLE/boot_falha" ]'


def _executavel(caminho: Path, corpo: str):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(("#!/usr/bin/env bash\n" + corpo + "\n").encode())
    caminho.chmod(0o755)


def _git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=Teste", "-c", "user.email=teste@exemplo.com", "-c", "core.autocrlf=false",
                        "-c", "gc.auto=0", *args], cwd=str(cwd), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class Servidor:
    """Um 'origem' (o GitHub) e um clone 'servidor' com o atualizar.sh desta árvore, o .venv e os comandos falsos."""

    def __init__(self, base: Path):
        self.origem, self.clone, self.bin = base / "origem", base / "servidor", base / "bin"
        self.controle, self.log = base / "controle", base / "log.txt"
        self.controle.mkdir()
        self.origem.mkdir()
        _git(self.origem, "init", "-q", "-b", "main")
        self.commit("requirements.txt", "flask==3.1.3\n")
        _git(base, "clone", "-q", str(self.origem), str(self.clone))
        (self.clone / ".git" / "info" / "exclude").write_text("deploy/\n.venv/\n")
        script = self.clone / "deploy" / "atualizar.sh"
        script.parent.mkdir()
        script.write_bytes(SCRIPT.read_bytes().replace(b"\r\n", b"\n"))
        _executavel(self.clone / ".venv" / "bin" / "pip", _PIP)
        _executavel(self.clone / ".venv" / "bin" / "python", _PYTHON)
        for nome, corpo in _FALSOS.items():
            _executavel(self.bin / nome, corpo)

    def commit(self, arquivo: str, texto: str):
        (self.origem / arquivo).write_text(texto)
        _git(self.origem, "add", arquivo)
        _git(self.origem, "commit", "-q", "-m", f"muda {arquivo}")

    def falhar(self, o_que: str, sim: bool = True):
        alvo = self.controle / o_que
        if sim:
            alvo.write_text("1")
        elif alvo.exists():
            alvo.unlink()

    def rodar(self, *args) -> tuple[int, list[str], str]:
        """(código de saída, o que o script fez nos falsos nesta rodada, saída)."""
        self.log.write_text("")
        env = dict(os.environ, NEXUS_TESTE_LOG=self.log.as_posix(), NEXUS_TESTE_CONTROLE=self.controle.as_posix(),
                   # os falsos primeiro; depois a pasta do bash (readlink, seq, tee... mesmo sem o Git no PATH)
                   PATH=os.pathsep.join([str(self.bin), str(Path(BASH).parent), os.environ.get("PATH", "")]))
        r = subprocess.run([BASH, (self.clone / "deploy" / "atualizar.sh").as_posix(), *args], cwd=str(self.clone),
                           env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
        feito = [x.split()[0] for x in self.log.read_text().splitlines() if x.strip()]
        return r.returncode, feito, r.stdout + r.stderr


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_a_rodada_que_parou_no_pip_e_completada_pela_seguinte(tmp_path):
    s = Servidor(tmp_path)
    # 1ª vez com o script novo: sem a marca, instala, confere e reinicia uma vez
    codigo, feito, saida = s.rodar()
    assert (codigo, feito) == (0, ["pip", "python", "systemctl"]), saida
    assert s.rodar()[:2] == (0, [])                                   # depois, sem commit novo: nada a fazer

    # commit novo com dependência nova, e o pip falha (sem saída para o pypi): para antes do restart
    s.commit("requirements.txt", "flask==3.1.3\nreportlab==5.0.0\n")
    s.falhar("pip_falha")
    codigo, feito, saida = s.rodar()
    assert codigo != 0 and feito == ["pip"], saida
    # a rodada seguinte (o timer, sem commit novo) NÃO diz "nada a fazer": completa a instalação e reinicia
    s.falhar("pip_falha", False)
    codigo, feito, saida = s.rodar()
    assert (codigo, feito) == (0, ["pip", "python", "systemctl"]), saida
    assert s.rodar()[:2] == (0, [])


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_forcar_reinstala_e_o_boot_que_nao_sobe_nao_reinicia(tmp_path):
    s = Servidor(tmp_path)
    assert s.rodar()[0] == 0
    # --forcar sem commit novo: o pip roda assim mesmo (antes ele era pulado e o restart subia sem a dependência)
    codigo, feito, saida = s.rodar("--forcar")
    assert (codigo, feito) == (0, ["pip", "python", "systemctl"]), saida
    # commit novo sem mudar o requirements.txt, e o boot não sobe (um import quebrado): nada de restart
    s.commit("leia.txt", "x\n")
    s.falhar("boot_falha")
    codigo, feito, saida = s.rodar()
    assert codigo != 0 and feito == ["pip", "python"], saida
    assert "segue no ar" in saida
    s.falhar("boot_falha", False)
    assert s.rodar()[:2] == (0, ["pip", "python", "systemctl"])
