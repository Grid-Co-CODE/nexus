"""No horário útil, no máximo um reinício por hora (Levi, 16/11/2026: "1 reinício por hora"; DEPLOY.md, seção 8).

O caso: em 16/11/2026, das 15:37 às 15:41, três pushes na `main` reiniciaram o Nexus três vezes em 5 minutos. Cada
reinício zera as cópias prontas da memória, e por 15 a 20 minutos toda tela refaz a conta do zero ao mesmo tempo, no mesmo
processo: o Raio-X das 15:40 mostrava o processador do Nexus em 167%, 17 pedidos em andamento e o próprio Raio-X preso
41 s. Naquele dia foram 19 reinícios no horário útil (17 por dia na média dos 6 dias úteis anteriores).

A regra do `deploy/atualizar.sh`: o push isolado sobe em 2 min, como antes; depois de um reinício, o seguinte só sai uma
hora depois dele (segunda a sexta, das 7h às 19h de Brasília). Sobem na hora: o commit com `[agora]` na mensagem, o
`--forcar`, tudo fora do horário útil e qualquer coisa enquanto o Nexus no ar não responde o `/saude` (o conserto de um
commit que derrubou o Nexus não espera). Quem espera aparece no `/saude` e no cartão "Versão no ar" do Início.

Aqui: o script rodado no clone de mentira do `test_deploy_atualizar`, com o relógio pelo `NEXUS_AGORA`, e o que o Nexus
diz de quem espera."""
import time
from datetime import datetime, timedelta, timezone

import pytest
from test_deploy_atualizar import BASH, Servidor, _git

BRT = timezone(timedelta(hours=-3))
SEGUNDA_10H = int(datetime(2026, 11, 16, 10, 0, tzinfo=BRT).timestamp())
MIN = 60
INSTALOU = ["pip", "python", "systemctl"]

pytestmark = pytest.mark.skipif(BASH is None, reason="sem bash nesta máquina")


def _no_ar(tmp_path, quando=SEGUNDA_10H) -> Servidor:
    """O servidor com um reinício feito em `quando` (a 1ª rodada instala e reinicia, e marca a hora)."""
    s = Servidor(tmp_path)
    codigo, feito, saida = s.rodar(NEXUS_AGORA=str(quando))
    assert (codigo, feito) == (0, INSTALOU), saida
    return s


def _commit(s: Servidor, mensagem: str, arquivo: str = "leia.txt"):
    (s.origem / arquivo).write_text(mensagem + "\n")
    _git(s.origem, "add", arquivo)
    _git(s.origem, "commit", "-q", "-m", mensagem)


def _espera(s: Servidor) -> dict:
    arq = s.clone / ".git" / "nexus-espera"
    if not arq.exists():
        return {}
    return dict(x.split("=", 1) for x in arq.read_text().splitlines() if "=" in x)


def test_o_push_seguinte_espera_completar_a_hora_do_ultimo_reinicio(tmp_path):
    s = _no_ar(tmp_path)
    antes = s.head()
    s.commit("leia.txt", "novo\n")
    novo = _git(s.origem, "rev-parse", "--short", "HEAD")
    for minutos in (20, 59):
        codigo, feito, saida = s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + minutos * MIN))
        # nem o pip nem a conferência do boot rodam enquanto espera: a rodada do timer (2 em 2 min) não custa nada
        assert (codigo, feito) == (0, []), saida
        assert s.head() == antes, "a pasta do serviço andou sem reiniciar"
        assert "Reinício adiado" in saida and "11:00" in saida and "[agora]" in saida
        assert _espera(s) == {"commit": novo, "ate": str(SEGUNDA_10H + 60 * MIN)}
    codigo, feito, saida = s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 60 * MIN))
    assert (codigo, feito) == (0, INSTALOU), saida
    assert s.head() == novo and not _espera(s)
    # e a hora volta a contar do reinício que acabou de sair
    s.commit("leia.txt", "outro\n")
    assert s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 90 * MIN))[:2] == (0, [])
    assert s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 120 * MIN))[:2] == (0, INSTALOU)


def test_o_push_isolado_sobe_na_hora(tmp_path):
    s = _no_ar(tmp_path)
    s.commit("leia.txt", "novo\n")
    codigo, feito, saida = s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 61 * MIN))
    assert (codigo, feito) == (0, INSTALOU), saida
    assert "adiado" not in saida


@pytest.mark.parametrize("marca", ["[agora]", "[AGORA]"])
def test_o_commit_marcado_agora_sobe_na_hora_e_leva_os_que_esperavam(tmp_path, marca):
    s = _no_ar(tmp_path)
    antes = s.head()
    s.commit("leia.txt", "comum\n")
    assert s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 5 * MIN))[:2] == (0, [])
    _commit(s, f"fix(os): a tela quebrada {marca}")
    codigo, feito, saida = s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 7 * MIN))
    assert (codigo, feito) == (0, INSTALOU), saida
    assert s.head() != antes and not _espera(s)


def test_a_marca_no_corpo_do_commit_tambem_vale(tmp_path):
    s = _no_ar(tmp_path)
    (s.origem / "leia.txt").write_text("corpo\n")
    _git(s.origem, "add", "leia.txt")
    _git(s.origem, "commit", "-q", "-m", "fix(os): a tela quebrada", "-m", "Urgente: produção parada. [agora]")
    assert s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 5 * MIN))[:2] == (0, INSTALOU)


@pytest.mark.parametrize("quando, o_que", [
    (datetime(2026, 11, 16, 19, 0, tzinfo=BRT), "segunda às 19h"),
    (datetime(2026, 11, 16, 6, 30, tzinfo=BRT), "segunda às 6h30"),
    (datetime(2026, 11, 14, 10, 0, tzinfo=BRT), "sábado às 10h"),
    (datetime(2026, 11, 15, 15, 0, tzinfo=BRT), "domingo às 15h"),
])
def test_fora_do_horario_util_nada_muda(tmp_path, quando, o_que):
    t = int(quando.timestamp())
    s = _no_ar(tmp_path, t - 5 * MIN)
    s.commit("leia.txt", "novo\n")
    codigo, feito, saida = s.rodar(NEXUS_AGORA=str(t))
    assert (codigo, feito) == (0, INSTALOU), f"{o_que}: {saida}"


@pytest.mark.parametrize("quando", [datetime(2026, 11, 16, 7, 0, tzinfo=BRT), datetime(2026, 11, 20, 18, 59, tzinfo=BRT)])
def test_as_bordas_do_horario_util_esperam(tmp_path, quando):
    t = int(quando.timestamp())
    s = _no_ar(tmp_path, t - 5 * MIN)
    s.commit("leia.txt", "novo\n")
    assert s.rodar(NEXUS_AGORA=str(t))[:2] == (0, [])


def test_o_forcar_passa_por_cima(tmp_path):
    s = _no_ar(tmp_path)
    s.commit("leia.txt", "novo\n")
    codigo, feito, saida = s.rodar("--forcar", NEXUS_AGORA=str(SEGUNDA_10H + 5 * MIN))
    assert (codigo, feito) == (0, INSTALOU), saida


def test_com_o_nexus_fora_do_ar_o_conserto_nao_espera(tmp_path):
    """O commit que monta e não sobe (o `.env`, por exemplo) deixa o Nexus fora: o conserto que vem 5 min depois sobe já."""
    s = _no_ar(tmp_path)
    s.commit("leia.txt", "conserto\n")
    (s.controle / "saude").write_text("502 Bad Gateway")
    codigo, feito, saida = s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 5 * MIN))
    assert feito == INSTALOU, saida
    assert "adiado" not in saida


def test_o_intervalo_zero_desliga_a_regra(tmp_path):
    s = _no_ar(tmp_path)
    s.commit("leia.txt", "novo\n")
    codigo, feito, saida = s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 5 * MIN), NEXUS_REINICIO_INTERVALO_S="0")
    assert (codigo, feito) == (0, INSTALOU), saida


def test_sem_commit_novo_segue_nada_a_fazer_e_sem_espera(tmp_path):
    s = _no_ar(tmp_path)
    codigo, feito, saida = s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 5 * MIN))
    assert (codigo, feito) == (0, []) and "nada a fazer" in saida and not _espera(s)


def test_a_rodada_que_parou_no_pip_nao_conta_como_reinicio(tmp_path):
    """Só o restart marca a hora: a instalação que falhou antes dele não empurra o próximo reinício."""
    s = _no_ar(tmp_path)
    s.commit("requirements.txt", "flask==3.1.3\nreportlab==5.0.0\n")
    s.falhar("pip_falha")
    codigo, feito, _ = s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 61 * MIN))
    assert codigo != 0 and feito == ["pip"]
    s.falhar("pip_falha", False)
    assert s.rodar(NEXUS_AGORA=str(SEGUNDA_10H + 63 * MIN))[:2] == (0, INSTALOU)


# ── o que o Nexus diz de quem espera ───────────────────────────────────────────────────────
def _arquivo(tmp_path, monkeypatch, commit="abc1234", ate=None):
    from nexus.casca import versao
    arq = tmp_path / "nexus-espera"
    if ate is not None:
        arq.write_text(f"commit={commit}\nate={int(ate)}\n", encoding="utf-8")
    monkeypatch.setattr(versao, "ARQ_ESPERA", arq)
    return versao


def test_o_saude_e_o_cartao_dizem_o_commit_que_espera(cliente, tmp_path, monkeypatch):
    ate = time.time() + 20 * MIN
    versao = _arquivo(tmp_path, monkeypatch, ate=ate)
    hora = datetime.fromtimestamp(int(ate), BRT).strftime("%H:%M")
    assert versao.espera_do_deploy() == {"curto": "abc1234", "sobe_as": hora}
    r = cliente.get("/saude").get_json()
    assert r["ok"] is True and r["commit"] and r["espera"] == {"curto": "abc1234", "sobe_as": hora}


@pytest.mark.parametrize("conteudo", [None, "", "commit=abc1234\n", "commit=abc1234\nate=ontem\n", "ate=123\n", "lixo"])
def test_sem_espera_o_saude_fica_como_sempre(cliente, tmp_path, monkeypatch, conteudo):
    versao = _arquivo(tmp_path, monkeypatch)
    if conteudo is not None:
        versao.ARQ_ESPERA.write_text(conteudo, encoding="utf-8")
    assert versao.espera_do_deploy() is None
    assert cliente.get("/saude").get_json() == {"ok": True, "commit": cliente.get("/saude").get_json()["commit"]}


def test_o_nexus_procura_os_arquivos_do_deploy_na_pasta_do_git_que_o_git_diz(tmp_path, monkeypatch):
    """O `atualizar.sh` grava na pasta do `git rev-parse --git-dir`. Com o `<raiz>/.git` de cabeça, num clone em que o `.git`
    é um arquivo (worktree, pasta do git à parte) o Nexus não achava nada, calado: o Raio-X do servidor sem o "o deploy
    conferiu em ..." (16/11/2026)."""
    from nexus.casca import raio_x as R
    from nexus.casca import versao
    pasta = tmp_path / "git-a-parte"
    pasta.mkdir()
    chamadas = []
    monkeypatch.setattr(versao, "_git", lambda *a, **k: chamadas.append(a) or str(pasta) + "\n")
    monkeypatch.setattr(versao, "ARQ_ESPERA", None)
    monkeypatch.setattr(R, "ARQ_TETO_DEPLOY", None)
    versao.pasta_do_git.cache_clear()
    try:
        assert versao.pasta_do_git() == pasta and chamadas == [("rev-parse", "--absolute-git-dir")]
        assert versao.espera_do_deploy() is None and R._teto_do_deploy() is None      # sem os arquivos
        (pasta / "nexus-espera").write_text("commit=abc1234\nate=%d\n" % (time.time() + 600), encoding="utf-8")
        (pasta / "nexus-teto").write_text("quando=2026-11-16T10:00:00-03:00\npiso_mb=4096\nacao=nada\n", encoding="utf-8")
        assert versao.espera_do_deploy()["curto"] == "abc1234"
        assert R._teto_do_deploy()["texto"] == "sem teto abaixo de 4096 MB"
        assert len(chamadas) == 1                                  # o git é perguntado uma vez por processo
        # sem git (a vitrine, a pasta copiada): a pasta de sempre, sem quebrar
        versao.pasta_do_git.cache_clear()
        monkeypatch.setattr(versao, "_git", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sem git")))
        assert versao.pasta_do_git().name == ".git" and versao.espera_do_deploy() is None
    finally:
        versao.pasta_do_git.cache_clear()


def test_no_servidor_o_raio_x_diz_por_que_nao_leu_o_arquivo_do_deploy(tmp_path, monkeypatch):
    """Depois do deploy de 16/11/2026 o Raio-X do servidor seguiu sem o "o deploy conferiu em ...", com a pasta do git
    certa: o arquivo não abre, e de fora não se sabe por quê. Onde há o teto do processo (o Linux do servidor), a linha
    passa a dizer o motivo e o caminho; no PC, sem o arquivo, segue sem dizer nada."""
    from pathlib import Path

    from nexus.casca import raio_x as R
    falta = tmp_path / "nexus-teto"
    monkeypatch.setattr(R, "ARQ_TETO_DEPLOY", falta)
    assert R._teto_do_deploy() is None                                         # o PC: nada
    d = R._teto_do_deploy(diagnostico=True)
    assert d == {"hora": "?", "texto": f"não leu o arquivo que o deploy grava: não existe ({falta})"}
    falta.write_text("quando=2026-11-16T10:00:00-03:00" + chr(10) + "acao=nada" + chr(10), encoding="utf-8")
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: (_ for _ in ()).throw(PermissionError(13, "negado")))
    d = R._teto_do_deploy(diagnostico=True)
    assert d["texto"] == f"não leu o arquivo que o deploy grava: PermissionError ({falta})"
    # e quem liga o diagnóstico é a presença do teto do processo (só o Linux tem)
    fonte = __import__("inspect").getsource(R._maquina)
    assert "_teto_do_deploy(diagnostico=teto is not None)" in fonte


def test_o_script_deixa_os_dois_arquivos_legiveis_para_o_nexus():
    """O script roda como root e grava como o dono do clone; o Nexus pode rodar como outro usuário."""
    from test_deploy_atualizar import SCRIPT
    texto = SCRIPT.read_text(encoding="utf-8")
    assert texto.count('chmod a+r "$ESPERA"') == 1 and 'chmod a+r "$ARQ_TETO"' in texto
    assert texto.index('como tee "$ESPERA"') < texto.index('chmod a+r "$ESPERA"')
    assert texto.index('como tee "$ARQ_TETO"') < texto.index('chmod a+r "$ARQ_TETO"')


def test_a_espera_vencida_ha_mais_de_dez_minutos_nao_aparece(tmp_path, monkeypatch):
    """O timer parado (ou o arquivo esquecido) não deixa o aviso para sempre: o reinício sai em até 2 min depois da hora."""
    versao = _arquivo(tmp_path, monkeypatch, ate=time.time() - 11 * MIN)
    assert versao.espera_do_deploy() is None
    versao = _arquivo(tmp_path, monkeypatch, ate=time.time() - 3 * MIN)
    assert versao.espera_do_deploy() is not None
    versao = _arquivo(tmp_path, monkeypatch, commit="", ate=time.time() + 20 * MIN)       # sem o commit, não há o que dizer
    assert versao.espera_do_deploy() is None
