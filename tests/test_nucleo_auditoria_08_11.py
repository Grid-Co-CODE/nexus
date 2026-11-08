"""Achados pequenos da auditoria ponytail do núcleo (08/11/2026)."""
import pytest


class _R:
    def __init__(self, status, reset=None):
        self.status_code, self.headers = status, ({"ratelimit-reset": reset} if reset is not None else {})

    def json(self):
        return {"ok": True}


@pytest.mark.parametrize("reset", ["120", "Wed, 21 Oct 2026 07:28:00 GMT"])
def test_o_rest_do_fracttal_nao_dorme_mais_de_5_s_dentro_do_pedido(app, monkeypatch, reset):
    """O cabeçalho `ratelimit-reset` do Fracttal não tinha teto: 120 segurava uma thread do OS Creator por 120 s, e uma data
    (não número) dava ValueError e 500."""
    from nexus.torres.oscreator import ponte
    ponte.clone(app)
    import api as os_api
    respostas = [_R(429, reset), _R(200)]
    dormiu = []
    monkeypatch.setattr(os_api, "_headers", lambda: {})
    monkeypatch.setattr(os_api.requests, "request", lambda *a, **k: respostas.pop(0))
    monkeypatch.setattr(os_api.time, "sleep", dormiu.append)
    assert os_api._req("GET", "work_orders") == {"ok": True}
    assert len(dormiu) == 1 and 0 < dormiu[0] <= 5
