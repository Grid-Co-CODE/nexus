"""O `nexusPedir` (`nexus/templates/_pedir_js.html`, 08/11/2026), rodado no node com um fetch de mentira: o pedido de
dados de toda tela, com o endereço pelo nexusRota, a sessão vencida levando ao login e o erro do servidor como frase.

O caso que o criou: o mapa do desembaraço achou 61 fetch em 32 templates, e 13 arquivos tratando a sessão vencida cada um
do seu jeito (alguns não tratavam: a resposta 401 virava "erro ao ler JSON" na tela)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PEDIR = Path(__file__).resolve().parents[1] / "nexus" / "templates" / "_pedir_js.html"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")

PAGINA = r"""
const CENA = JSON.parse(process.argv[3]);
globalThis.window = globalThis;
const visto = {};
window.nexusRota = c => "/nexus" + c;
window.nexusEntrarDeNovo = u => { visto.entrar = u; };
window.fetch = (url, o) => {
  visto.url = url; visto.cred = o.credentials; visto.metodo = o.method || "GET";
  return Promise.resolve({ok: CENA.status < 400, status: CENA.status,
    json: () => CENA.corpo === null ? Promise.reject(new SyntaxError("não é JSON")) : Promise.resolve(CENA.corpo)});
};
eval(require("fs").readFileSync(process.argv[2], "utf8"));
nexusPedir("/t/pcm/x", CENA.opcoes || null).then(
  d => process.stdout.write(JSON.stringify({ok: true, d, visto})),
  e => process.stdout.write(JSON.stringify({ok: false, msg: e.message, status: e.status, login: !!e.login, visto})));
"""


def _rodar(tmp_path, status, corpo, opcoes=None):
    js = re.sub(r"\{#.*?#\}", "", PEDIR.read_text(encoding="utf-8"), flags=re.S)
    arq = tmp_path / "pedir.js"
    arq.write_text(js, encoding="utf-8")
    pagina = tmp_path / "pagina.js"
    pagina.write_text(PAGINA, encoding="utf-8")
    r = subprocess.run(["node", str(pagina), str(arq), json.dumps({"status": status, "corpo": corpo, "opcoes": opcoes})],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_resposta_boa_devolve_o_json_pelo_endereco_do_nexus(tmp_path):
    r = _rodar(tmp_path, 200, {"linhas": [1, 2]}, {"method": "POST"})
    assert r["ok"] and r["d"] == {"linhas": [1, 2]}
    assert r["visto"]["url"] == "/nexus/t/pcm/x" and r["visto"]["cred"] == "same-origin" and r["visto"]["metodo"] == "POST"


def test_sessao_encerrada_leva_ao_login(tmp_path):
    r = _rodar(tmp_path, 401, {"ok": False, "login": True, "sessao_encerrada": True, "entrar": "/nexus/entrar",
                               "erro": "A sua sessão terminou."})
    assert not r["ok"] and r["visto"]["entrar"] == "/nexus/entrar" and r["msg"] == "A sua sessão terminou."


def test_falta_o_fracttal_avisa_sem_tirar_a_pessoa_da_tela(tmp_path):
    r = _rodar(tmp_path, 401, {"ok": False, "login": True, "erro": "Entre pelo Fracttal."})
    assert not r["ok"] and r["login"] and "entrar" not in r["visto"] and r["msg"] == "Entre pelo Fracttal."


def test_erro_do_servidor_vira_a_frase_dele_ou_o_codigo(tmp_path):
    r = _rodar(tmp_path, 409, {"erro": "Outra pessoa gravou antes."})
    assert not r["ok"] and r["status"] == 409 and r["msg"] == "Outra pessoa gravou antes."
    r = _rodar(tmp_path, 502, None)                          # o proxy devolveu HTML, não JSON
    assert not r["ok"] and r["msg"] == "O Nexus respondeu 502."


def test_a_casca_carrega_o_pedir_depois_do_nexus_rota():
    base = (PEDIR.parent / "base.html").read_text(encoding="utf-8")
    assert base.index('{% include "_raiz_js.html" %}') < base.index('{% include "_pedir_js.html" %}')
    assert base.index('{% include "_entrar_de_novo_js.html" %}') < base.index('{% include "_pedir_js.html" %}')
