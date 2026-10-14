"""A versão no ar e as Atualizações do Início (13/10/2026). À tarde, Levi: "Quero que no início do Nexus diga quando foi o
último commit para eu acompanhar se está realmente subindo automático para o server". À noite: "tire as informações de
github, preso em 24hrs e essas observações abaixo do commit" e "Inclua no início uma sub aba de atualizações mostrando as
últimas atualizações dos commits e o que mudou! Ao clicar em versão no ar já leva para lá!". Nada vai à rede."""
from datetime import datetime

import pytest

from nexus import casca
from nexus.casca import versao

SHA = "648c1007e956e9faf6c465c1bd6402b1960beed0"
LOG = (f"{SHA}\x1f2026-10-13T17:45:37Z\x1ffeat(base): Equipamentos das usinas liga pela aba - cada chave vai a usina"
       "\x1fCorpo da mensagem.\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n\x1e"
       "aaaa111222333444555666777888999000aaaa\x1f2026-10-12T12:00:00-03:00\x1ffix(campo): a foto ampliada\x1f\x1e"
       "bbbb111222333444555666777888999000bbbb\x1f2026-10-12T11:00:00-03:00\x1fmensagem sem tipo\x1f\x1e")


@pytest.fixture
def git(monkeypatch):
    def falso(*args, **k):
        if args[0] == "log" and args[1] == "-1":
            return f"{SHA}\x1f2026-10-13T17:45:37Z\x1ffeat(base): Equipamentos das usinas liga pela aba\n"
        return LOG
    monkeypatch.setattr(versao, "_git", falso)
    monkeypatch.setattr(casca, "_commit", lambda: "648c100")
    versao.local.cache_clear()
    versao.historico.cache_clear()
    yield
    versao.local.cache_clear()
    versao.historico.cache_clear()


def test_o_cartao_so_tem_a_hora_o_commit_e_o_no_ar_desde_e_leva_as_atualizacoes(app, logado, git):
    html = logado.get("/").get_data(as_text=True)
    cartao = html.split('class="versao-no-ar"', 1)[1].split("</a>", 1)[0]
    assert "Versão no ar" in cartao and "13/10 14:45" in cartao and "<code>648c100</code>" in cartao
    assert "no ar desde" in cartao
    assert '<a class="versao-no-ar" href="/?aba=atualizacoes"' in html
    # nem GitHub, nem pedidos presos, nem o assunto do commit embaixo
    for fora in ("GitHub", "preso", "Equipamentos das usinas liga pela aba", "gc-status"):
        assert fora not in cartao
    assert 'aria-current="page">Visão geral</a>' in html and ">Atualizações</a>" in html


def test_a_aba_atualizacoes_lista_os_commits_por_dia_com_o_que_mudou(app, logado, git, monkeypatch):
    class Hoje(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 13, 20, 0, tzinfo=tz)
    monkeypatch.setattr(versao, "datetime", Hoje)
    html = logado.get("/?aba=atualizacoes").get_data(as_text=True)
    assert 'aria-current="page">Atualizações</a>' in html
    assert ">Hoje</h2>" in html and ">Ontem</h2>" in html
    assert "Novidade" in html and "Correção" in html and ">base<" in html
    assert "Equipamentos das usinas liga pela aba" in html and "cada chave vai a usina" in html
    assert "Corpo da mensagem." in html and "Co-Authored-By" not in html        # a coautoria não aparece
    assert "mensagem sem tipo" in html and "no ar</span>" in html
    assert "Os últimos 3 commits do Nexus." in html


def test_sem_git_o_cartao_diz_traco_e_a_aba_diz_por_que(app, logado, monkeypatch):
    def sem_git(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(versao, "_git", sem_git)
    versao.local.cache_clear()
    versao.historico.cache_clear()
    try:
        assert "—" in logado.get("/").get_data(as_text=True).split('class="versao-no-ar"', 1)[1][:300]
        assert "Sem o histórico de atualizações" in logado.get("/?aba=atualizacoes").get_data(as_text=True)
    finally:
        versao.local.cache_clear()
        versao.historico.cache_clear()


def test_a_aba_exige_login(cliente):
    assert cliente.get("/?aba=atualizacoes").status_code in (302, 401)
