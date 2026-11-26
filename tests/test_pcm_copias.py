"""A conferência das cópias do PCM com o PCM de AGORA (24/11/2026, `nexus/pcm/copias_pcm.py`; Levi: "Todas as mudanças
que a gente fizer na programação semanal e tudo mais, tem que se refletir nos relatórios do PCM também. A gente tem que
garantir que isso seja feito").

O caso: o Relatório Executivo do Nexus ficou com a cópia de 14/10 do JS do painel depois de o PCM mudar o relatório em
09/11 e 16/11, e ninguém soube (a W47 da Athon: 55% aqui, 57% lá). O que se prova: sem mudança no PCM, nenhum aviso; a
mudança em cada tipo de cópia (inteira, o trecho do css e os trechos do painel) aparece na parte certa; rede fora não
inventa aviso; toda cópia do PCM que existe na pasta está na conferência; e o aviso aparece nas duas telas."""
import re
from pathlib import Path

from nexus.pcm import copias_pcm as CP
from nexus.pcm import relatorio_exec as R
from test_relatorios_pcm_executivo import URL, dados_pcm  # noqa: F401 (fixture)

AQUI = Path(CP.__file__).resolve().parent


def _pcm_igual() -> dict:
    """Os arquivos do PCM remontados a partir das cópias daqui: o PCM "de agora" sem nenhuma mudança."""
    arqs = {do_pcm: CP._texto((AQUI / copia).read_bytes()) for copia, do_pcm in CP.INTEIROS.items()}
    copia, do_pcm, de, _ = CP.GPV
    gpv = CP._texto((AQUI / copia).read_bytes()).strip("\n").split("\n")
    arqs[do_pcm] = "\n".join(["/* antes */"] * (de - 1) + gpv + ["/* depois */"])
    # os trechos do painel_pcm.js de volta às linhas de onde vieram
    painel = CP._texto((AQUI / CP.PAINEL).read_bytes())
    cabs = list(re.finditer(r"\n// ── (\S+), linhas (\d+)-(\d+): [^\n]*──\n", painel))
    linhas: dict[str, dict[int, str]] = {}
    for i, m in enumerate(cabs):
        fim = cabs[i + 1].start() if i + 1 < len(cabs) else len(painel)
        corpo = painel[m.end():fim][:-1].split("\n")
        for k, linha in enumerate(corpo):
            linhas.setdefault(m.group(1), {})[int(m.group(2)) + k] = linha
    for arq, ls in linhas.items():
        arqs[arq] = "\n".join(ls.get(n, "// outra linha do painel") for n in range(1, max(ls) + 1))
    return arqs


def test_sem_mudanca_no_pcm_nao_ha_aviso():
    arqs = _pcm_igual()
    r = CP.conferir(baixar=arqs.__getitem__)
    assert r["diferentes"] == [] and not r["erro"], r


def test_cada_mudanca_no_pcm_aparece_na_parte_dela():
    for do_pcm, parte, copia in (("js/relatorio_exec.js", "relatorio_exec", "relatorio_exec/relatorio_exec.js"),
                                 ("programacao_v7.py", "motor", "motor/programacao_v7.py")):
        arqs = _pcm_igual()
        arqs[do_pcm] += "\n// mudou no PCM"
        r = CP.conferir(baixar=arqs.__getitem__)
        assert [(d["copia"], d["parte"]) for d in r["diferentes"]] == [(copia, parte)], r
    # o trecho do css e os trechos do painel: a linha copiada mudou lá
    arqs = _pcm_igual()
    arqs["css/preventivas.css"] = arqs["css/preventivas.css"].replace(".gpv-cel.ok", ".gpv-cel.bom", 1)
    arqs["js/app.js"] = arqs["js/app.js"].replace("function", "async function", 1)
    r = CP.conferir(baixar=arqs.__getitem__)
    assert [d["copia"] for d in r["diferentes"]] == ["relatorio_exec/gpv_cel.css", "relatorio_exec/painel_pcm.js"]
    assert all(d["parte"] == "relatorio_exec" for d in r["diferentes"])


def test_a_copia_do_executivo_cita_o_papel_e_nao_o_nome():
    """O repositório do Nexus é público: o comentário do PCM com quem decidiu vira o papel, na cópia e na conferência."""
    assert R.para_a_copia("(decisão do Fulano, 16/11/2026)") == "(decisão do PCM, 16/11/2026)"
    assert R.para_a_copia("(decisão da Beltrana, 01/12)") == "(decisão do PCM, 01/12)"
    assert R.para_a_copia("decisão do PCM, 16/11") == "decisão do PCM, 16/11"


def test_rede_fora_nao_inventa_aviso():
    def fora(_):
        raise OSError("sem rede")
    r = CP.conferir(baixar=fora)
    assert r["diferentes"] == [] and "sem rede" in r["erro"]


def test_toda_copia_do_pcm_esta_na_conferencia():
    """Cópia nova do PCM numa das duas pastas tem de entrar na conferência, senão ela atrasa calada de novo."""
    conferidas = set(CP.INTEIROS) | {CP.GPV[0], CP.PAINEL}
    copias = {f"relatorio_exec/{n}" for n in R.COPIAS} | {f"motor/{p.name}" for p in (AQUI / "motor").glob("*.py")}
    assert copias <= conferidas, copias - conferidas


def test_o_aviso_nas_duas_telas(app, logado, dados_pcm):  # noqa: F811
    assert "está diferente do relatório do PCM" not in logado.get(URL).get_data(as_text=True)
    app.config["NEXUS_PCM_COPIAS_TESTE"] = {"diferentes": [
        {"copia": "relatorio_exec/relatorio_exec.js", "do_pcm": "js/relatorio_exec.js", "parte": "relatorio_exec"},
        {"copia": "motor/programacao_v7.py", "do_pcm": "programacao_v7.py", "parte": "motor"}]}
    html = logado.get(URL).get_data(as_text=True)
    assert "O relatório do Nexus está diferente do relatório do PCM" in html and "js/relatorio_exec.js" in html
    assert "programacao_v7.py" not in html            # o motor avisa na tela dele, não aqui
    html = logado.get("/t/pcm/gerar").get_data(as_text=True)
    assert "O motor do Nexus está diferente do" in html and "programacao_v7.py" in html
    assert "js/relatorio_exec.js" not in html
