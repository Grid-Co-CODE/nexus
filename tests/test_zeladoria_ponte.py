"""A ponte da zeladoria (nexus/static/zeladoria/ponte.js), provada no node por tests/zeladoria_ponte_node.js: o que o
clone do Radar recebia do supabase-js, agora vindo das rotas da torre (ver o comentário do .js)."""
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def test_a_ponte_no_node():
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    r = subprocess.run(["node", str(RAIZ / "tests" / "zeladoria_ponte_node.js"),
                        str(RAIZ / "nexus" / "static" / "zeladoria" / "ponte.js")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0, (r.stdout + r.stderr)[-1500:]
    assert r.stdout.startswith("ok:")
