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


def test_o_pc_acorda_20_s_depois_do_servidor_na_carga_das_40(monkeypatch):
    """O PC e o servidor acordavam no mesmo segundo, liam a "última carga" antes de qualquer um gravar e gravavam os mesmos
    livros em dobro. O PC chega 20 s depois e já vê a gravação do servidor (e então pula)."""
    from datetime import datetime, timezone

    from nexus.dados import carga
    agora = datetime(2026, 11, 8, 13, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(carga, "_maquina", lambda: "servidor")
    no_servidor = carga._espera_s(agora)
    monkeypatch.setattr(carga, "_maquina", lambda: "pc")
    assert carga._espera_s(agora) == no_servidor + carga.ATRASO_DO_PC_S == no_servidor + 20
