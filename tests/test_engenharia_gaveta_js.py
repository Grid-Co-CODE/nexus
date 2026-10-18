"""A resposta das ações da gaveta do acompanhamento (engenharia-gaveta.js), rodada no node.

Revisão final de 18/10/2026: o fetch punha na gaveta o que viesse. Com a sessão vencida, o portão responde 302 e o fetch
segue até a página de login, que entrava inteira na gaveta; com a sessão do Fracttal encerrada, o JSON 401 aparecia cru;
e nos dois o texto digitado se perdia. O molde é o card das Contestações: login = recarregar a página; HTTP de erro =
falha, sem trocar a gaveta (o formulário com o texto continua)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "engenharia-gaveta.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")

RODAR = r"""
globalThis.window = globalThis;
require(process.argv[1]);
const casos = JSON.parse(process.argv[2]);
Promise.all(casos.map(c => window.egGaveta.resposta({redirected: c.redirected, url: c.url, ok: c.status < 400,
  status: c.status, text: () => Promise.resolve(c.corpo)}))).then(r => console.log(JSON.stringify(r)));
"""


def test_a_resposta_da_gaveta_separa_login_falha_e_gaveta():
    casos = [{"redirected": True, "url": "http://n.test/entrar?next=%2Ft%2Fengenharia", "status": 200, "corpo": "<html>"},
             {"redirected": False, "url": "http://n.test/t/engenharia/x", "status": 401, "corpo": '{"login": true}'},
             {"redirected": False, "url": "http://n.test/t/engenharia/x", "status": 500, "corpo": "erro"},
             {"redirected": False, "url": "http://n.test/t/engenharia/x", "status": 200, "corpo": "<div>gaveta</div>"}]
    r = subprocess.run(["node", "-e", RODAR, str(JS), json.dumps(casos)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert [o["acao"] for o in out] == ["login", "login", "falha", "mostrar"]
    assert "HTTP 500" in out[2]["msg"] and out[3]["html"] == "<div>gaveta</div>"
