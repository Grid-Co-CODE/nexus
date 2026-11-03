"""O clone do app do Radar (nexus/torres/zeladoria/clone/radar.html), limpo pelo ferramentas/zeladoria_limpar_clone.py.

Ele entra no repositório público sem o Supabase (sem endereço, sem chave, sem o carregador das CDNs) e sem e-mail de
gente; os nomes de colega o test_sem_nomes_no_repositorio.py cobre. Os dois marcadores são onde a torre, ao servir,
põe a configuração e a ponte (nexus/static/zeladoria/ponte.js)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CLONE = RAIZ / "nexus" / "torres" / "zeladoria" / "clone" / "radar.html"


@pytest.fixture(scope="module")
def html():
    return CLONE.read_text(encoding="utf-8")


def test_sem_supabase(html):
    for proibido in ("supabase.co", "sb_publishable", "cdn.jsdelivr.net/npm/@supabase", "unpkg.com/@supabase",
                     "SUPABASE_URL", "SUPABASE_ANON_KEY"):
        assert proibido not in html, proibido
    assert html.count("window.supabase.createClient()") == 1


def test_marcadores(html):
    assert html.count("<!--ZELADORIA:CONFIG-->") == 1 and html.count("<!--ZELADORIA:PONTE-->") == 1
    assert html.index("<!--ZELADORIA:CONFIG-->") < html.index("<script")      # a configuração vem antes de tudo


def test_abre_na_aba_pedida(html):
    assert "tab: (window.ZELADORIA_ABA || 'overview')" in html


def test_sem_email_da_empresa(html):
    assert not re.search(r"[\w.+-]+@gridco\.com\.br", html, re.IGNORECASE)


def test_js_valido(html, tmp_path):
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    scripts = re.findall(r"<script(?: id=\"[^\"]*\")?>(.*?)</script>", html, re.S)
    assert len(scripts) >= 2
    for i, js in enumerate(scripts):
        arq = tmp_path / f"s{i}.js"
        arq.write_text(js, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-800:]


def test_origem_da_planilha_sem_nome_de_gente(html):
    """A planilha histórica levava o primeiro nome de quem a mantinha, no comentário e no valor gravado (`origem`).
    O valor passa a ser `planilha_historica`, aqui e nos dados copiados (a cópia aplica o mesmo de-para)."""
    assert "planilha_historica:1" in html and "origem='planilha_historica'" in html


def test_rota_da_equipe_casa_pelo_comeco(html):
    """O cronograma importado (arquivo do PCM) escreve "Rota do <supervisor>" com o nome de verdade: a regra que
    reconhecia a rota pelo nome não pode depender dele, senão as paradas da rota viram cotação."""
    assert "rota (do )?equipe" not in html
    assert html.count(r"/^\s*rota\b") == 3 and r"/^\s*rota\b|eco ?clean" in html     # 2 sozinhas + 1 na alternância
