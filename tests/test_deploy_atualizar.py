"""O `deploy/atualizar.sh` (auditoria A6 da porta única e revisão adversarial, 10/10/2026).

O caso: o `reportlab` entrou no requirements.txt em 09/10 e é importado no boot (o relatório dos extintores). O script
só rodava o pip quando o `requirements.txt` mudava ENTRE o commit de antes e o de depois do pull. Se o pip falhasse na 1ª
rodada (sem saída para o pypi, por exemplo), o `set -e` parava antes do restart, com o código novo já no disco; a 2ª
rodada (o timer, 2 min depois) via o mesmo commit e dizia "nada a fazer", e com `--forcar` pulava o pip e reiniciava: o
Nexus novo não subia e o `Restart=always` o deixava caindo em laço, com a entrada da empresa em 502. A A6 pôs o pip e a
conferência do boot antes de todo restart; a revisão adversarial achou que o `git pull` continuava ANTES dos dois: com o
pip ou a conferência falhando, o script saía sem reiniciar, mas a pasta do serviço já estava no commit que não sobe, e
qualquer restart fora do script (reboot, queda com Restart=always, o `systemctl restart nexus` do DESFAZER) subia ele.
Agora:
- o commit novo é conferido FORA da pasta do serviço (`git fetch` + `git archive` numa pasta temporária): o pip instala
  o requirements.txt dele e o `conferir_boot.py` dele importa o Nexus dele; só depois de os dois passarem a pasta do
  serviço anda (`git merge --ff-only`) e o serviço reinicia;
- se a pasta do serviço já estava fora do último commit instalado (um `git pull` à mão, ou o script antigo que parou no
  meio) e a conferência falha, ela volta ao instalado (`git reset --keep`), que é o que está no ar;
- "nada a fazer" é quando o commit do GitHub é o último INSTALADO (a marca em `.git/nexus-instalado`): a rodada que parou
  no meio é completada pela seguinte.
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
    blocos = _blocos_if(linhas, '"$antes" != "$alvo"')
    assert blocos, "o if do commit novo mudou de nome: atualize este teste"
    for ini, fim in blocos + _blocos_if(linhas, "git diff"):
        assert not any(ini <= i <= fim for i in pip), f"o pip está dentro do if das linhas {ini + 1}-{fim + 1}"


def test_pip_e_conferencia_do_boot_vem_antes_de_mexer_na_pasta_do_servico():
    texto = SCRIPT.read_text(encoding="utf-8")
    codigo = "\n".join(x for x in texto.splitlines() if not x.lstrip().startswith("#"))
    assert (codigo.index("git fetch") < codigo.index("pip install") < codigo.index("conferir_boot.py")
            < codigo.index("merge --ff-only") < codigo.index("systemctl restart"))
    # o pull trocava a pasta do serviço ANTES de conferir (revisão adversarial de 10/10/2026)
    assert "git pull" not in codigo
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
    # o /saude do Nexus que acabou de subir responde com o commit do clone; com o arquivo "saude" no controle, com ele
    # (o processo velho, que segue no ar enquanto a pasta mudou)
    "curl": ('if [ -e "$NEXUS_TESTE_CONTROLE/saude" ]; then cat "$NEXUS_TESTE_CONTROLE/saude"; '
             'else printf \'{"commit":"%s","ok":true}\' "$(git rev-parse --short HEAD)"; fi'),
}
# o pip falso guarda o requirements.txt que recebeu; o python falso, o leia.txt da árvore que conferiu (a do commit novo,
# e não a da pasta do serviço) e o commit em que a pasta do serviço estava naquela hora
_PIP = r"""echo "pip $*" >> "$NEXUS_TESTE_LOG"
while [ $# -gt 0 ]; do
  if [ "$1" = "-r" ]; then cat "$2" > "$NEXUS_TESTE_CONTROLE/pip_requisitos"; fi
  shift
done
[ ! -e "$NEXUS_TESTE_CONTROLE/pip_falha" ]"""
_PYTHON = r"""echo "python $*" >> "$NEXUS_TESTE_LOG"
arq="${@: -1}"
arvore="$(dirname "$(dirname "$arq")")"
cat "$arvore/leia.txt" > "$NEXUS_TESTE_CONTROLE/python_viu" 2>/dev/null || echo "(sem leia.txt)" > "$NEXUS_TESTE_CONTROLE/python_viu"
git rev-parse --short HEAD > "$NEXUS_TESTE_CONTROLE/servico_na_conferencia"
[ ! -e "$NEXUS_TESTE_CONTROLE/boot_falha" ]"""


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

    def head(self) -> str:
        """O commit em que a pasta do serviço (o clone) está."""
        return _git(self.clone, "rev-parse", "--short", "HEAD")

    def controle_txt(self, nome: str) -> str:
        return (self.controle / nome).read_text().strip()

    def falhar(self, o_que: str, sim: bool = True):
        alvo = self.controle / o_que
        if sim:
            alvo.write_text("1")
        elif alvo.exists():
            alvo.unlink()

    def rodar(self, *args, script: Path | None = None, cwd: Path | None = None,
              **env_extra) -> tuple[int, list[str], str]:
        """(código de saída, o que o script fez nos falsos nesta rodada, saída)."""
        self.log.write_text("")
        env = dict(os.environ, NEXUS_TESTE_LOG=self.log.as_posix(), NEXUS_TESTE_CONTROLE=self.controle.as_posix(),
                   # os falsos primeiro; depois a pasta do bash (readlink, seq, tee... mesmo sem o Git no PATH)
                   PATH=os.pathsep.join([str(self.bin), str(Path(BASH).parent), os.environ.get("PATH", "")]),
                   **env_extra)
        script = script or self.clone / "deploy" / "atualizar.sh"
        r = subprocess.run([BASH, script.as_posix(), *args], cwd=str(cwd or self.clone),
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


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_pip_que_falha_nao_mexe_na_pasta_do_servico(tmp_path):
    """Revisão adversarial de 10/10/2026: o `git pull` vinha antes do pip, e a pasta ficava no commit que não instalou."""
    s = Servidor(tmp_path)
    assert s.rodar()[0] == 0
    instalado = s.head()
    s.commit("requirements.txt", "flask==3.1.3\nreportlab==5.0.0\n")
    s.falhar("pip_falha")
    codigo, feito, saida = s.rodar()
    assert codigo != 0 and feito == ["pip"], saida
    assert s.head() == instalado                              # um reboot agora sobe o que estava no ar
    assert "reportlab" in s.controle_txt("pip_requisitos")    # o pip tentou o requirements.txt do commit NOVO
    # a seguinte, com o pypi de volta, instala e só então anda com a pasta
    s.falhar("pip_falha", False)
    codigo, feito, saida = s.rodar()
    assert (codigo, feito) == (0, ["pip", "python", "systemctl"]), saida
    assert s.head() != instalado and s.head() == _git(s.origem, "rev-parse", "--short", "HEAD")


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_o_boot_e_conferido_no_commit_novo_fora_da_pasta_do_servico(tmp_path):
    s = Servidor(tmp_path)
    s.commit("leia.txt", "versao 1\n")
    assert s.rodar()[0] == 0
    instalado = s.head()
    s.commit("leia.txt", "versao 2 que nao sobe\n")
    s.falhar("boot_falha")
    codigo, feito, saida = s.rodar()
    assert codigo != 0 and feito == ["pip", "python"], saida
    assert s.controle_txt("python_viu") == "versao 2 que nao sobe"      # conferiu o código NOVO...
    assert s.controle_txt("servico_na_conferencia") == instalado        # ...com a pasta do serviço parada no de antes
    assert s.head() == instalado and (s.clone / "leia.txt").read_text() == "versao 1\n"
    assert "segue no ar" in saida
    # o conserto chega: confere, anda com a pasta e reinicia
    s.falhar("boot_falha", False)
    s.commit("leia.txt", "versao 3\n")
    codigo, feito, saida = s.rodar()
    assert (codigo, feito) == (0, ["pip", "python", "systemctl"]), saida
    assert s.controle_txt("python_viu") == "versao 3" and (s.clone / "leia.txt").read_text() == "versao 3\n"


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_a_pasta_deixada_num_commit_nao_instalado_volta_ao_instalado_quando_a_conferencia_falha(tmp_path):
    """O que o script antigo deixava (ou um `git pull` à mão): a pasta no commit novo, que não sobe, e o serviço no de
    antes. A conferência falhou: a pasta volta ao instalado, e um reboot sobe o que estava no ar."""
    s = Servidor(tmp_path)
    assert s.rodar()[0] == 0
    instalado = s.head()
    s.commit("leia.txt", "nao sobe\n")
    _git(s.clone, "pull", "-q", "--ff-only")                 # o script antigo, ou a T.I. à mão
    assert s.head() != instalado
    s.falhar("boot_falha")
    codigo, feito, saida = s.rodar()
    assert codigo != 0 and feito == ["pip", "python"], saida
    assert s.head() == instalado and not (s.clone / "leia.txt").exists()
    assert "voltou" in saida


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_arquivo_mexido_a_mao_no_servidor_nao_se_perde(tmp_path):
    """O `merge --ff-only` (e o `reset --keep`) não apagam o que foi mexido à mão no servidor: param antes."""
    s = Servidor(tmp_path)
    s.commit("leia.txt", "versao 1\n")
    assert s.rodar()[0] == 0
    s.commit("leia.txt", "versao 2\n")
    (s.clone / "leia.txt").write_text("mexido no servidor\n")
    codigo, feito, saida = s.rodar()
    assert codigo != 0 and "systemctl" not in feito, saida
    assert (s.clone / "leia.txt").read_text() == "mexido no servidor\n"


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_sem_a_marca_a_pasta_volta_ao_commit_que_o_saude_diz(tmp_path):
    """A transição: o script antigo não gravava a marca e puxava antes do pip. Se o pip dele falhou, o processo velho
    segue no ar e a pasta ficou no commit novo. Na rodada seguinte (já com este script), a conferência falha de novo, e o
    commit que está no ar vem do /saude."""
    s = Servidor(tmp_path)
    assert s.rodar()[0] == 0
    no_ar = s.head()
    marca = s.clone / ".git" / "nexus-instalado"
    marca.unlink()                                           # o servidor nunca rodou o script novo
    (s.controle / "saude").write_text('{"commit":"%s","ok":true}' % no_ar)
    s.commit("leia.txt", "nao sobe\n")
    _git(s.clone, "pull", "-q", "--ff-only")                 # o script antigo puxou, e o pip dele falhou
    s.falhar("pip_falha")
    codigo, feito, saida = s.rodar()
    assert codigo != 0 and feito == ["pip"], saida
    assert s.head() == no_ar and "voltou" in saida
    # sem a marca e sem o /saude responder, não há como saber o que está no ar: a pasta fica como está
    _git(s.clone, "merge", "-q", "--ff-only", "origin/main")
    (s.controle / "saude").write_text("")
    codigo, feito, saida = s.rodar()
    assert codigo != 0 and s.head() != no_ar, saida


@pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")
def test_na_primeira_vez_o_script_novo_roda_de_fora_com_nexus_raiz(tmp_path):
    """O servidor ainda tem o script antigo: o novo, tirado do commit buscado, roda de /tmp sobre a pasta do serviço."""
    s = Servidor(tmp_path)
    fora = tmp_path / "fora" / "atualizar.sh"
    fora.parent.mkdir()
    fora.write_bytes(SCRIPT.read_bytes().replace(b"\r\n", b"\n"))
    s.commit("leia.txt", "versao nova\n")
    codigo, feito, saida = s.rodar(script=fora, cwd=tmp_path, NEXUS_RAIZ=s.clone.as_posix())
    assert (codigo, feito) == (0, ["pip", "python", "systemctl"]), saida
    assert s.head() == _git(s.origem, "rev-parse", "--short", "HEAD")
    assert (s.clone / ".git" / "nexus-instalado").read_text().strip() == s.head()
