"""A ponte do site do SSO (nexus/sso/site/supabase-client.js), provada no node por tests/sso_ponte_node.js: o app do SSO
recebe dela o que recebia do supabase-js, e a Gestão entra pelo login do Nexus."""
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="sem node nesta máquina")
def test_ponte_do_site_no_node():
    r = subprocess.run(["node", str(RAIZ / "tests" / "sso_ponte_node.js"),
                        str(RAIZ / "nexus" / "sso" / "site" / "supabase-client.js")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok"
