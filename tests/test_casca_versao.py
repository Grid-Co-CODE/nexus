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
    # só novidade e correção (19/10/2026, Levi: "deixe só novidade e correção, sempre os últimos 60 dias!")
    assert "mensagem sem tipo" not in html and "no ar</span>" in html
    assert "2 atualizações nos últimos 60 dias." in html


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


CORPO_REAL = """Levi, 14/10/2026: "Tire 'Importar do Excel' do módulo base".

- O item sai do menu da Base; /t/base/importar e /t/base/importar/aplicar (GET ou POST) levam ao Registro mestre, sem
  importar nada (favorito antigo ou prévia aberta não viram 404).
- Saem as views e os templates.
* E o recado da lista não manda mais a ela.

Prova: tests/test_cadastro_telas.py (o endereço leva ao Registro mestre) e o teste da vaga.

Co-Authored-By: Claude <noreply@anthropic.com>
"""


def test_o_corpo_vira_topicos_com_o_pedido_em_destaque_e_sem_a_prova():
    """14/10/2026, Levi: "Esse 'O que mudou em detalhe' está muito feio e bagunçado, poderia pontuar mais bonito para
    ficar melhor de ler. Não precisa desse Prova!"."""
    b = versao.blocos(CORPO_REAL)
    assert [x["tipo"] for x in b] == ["pedido", "lista"]
    assert b[0]["texto"] == "Levi, 14/10/2026: \"Tire 'Importar do Excel' do módulo base\"."
    assert b[1]["itens"] == [
        "O item sai do menu da Base; /t/base/importar e /t/base/importar/aplicar (GET ou POST) levam ao Registro mestre, "
        "sem importar nada (favorito antigo ou prévia aberta não viram 404).",
        "Saem as views e os templates.", "E o recado da lista não manda mais a ela."]
    assert versao.blocos("Só um parágrafo\nquebrado em duas linhas.") == [
        {"tipo": "paragrafo", "texto": "Só um parágrafo quebrado em duas linhas."}]
    assert versao.blocos("") == [] and versao.blocos("Provas: só isto.") == []


def test_a_aba_nao_mostra_horario_e_mostra_os_topicos(app, logado, monkeypatch):
    import re as _re
    log = (f"{SHA}\x1f2026-10-14T03:10:00Z\x1ffeat(base): sai a tela Importar do Excel - o endereco leva ao Registro"
           f"\x1f{CORPO_REAL}\x1e")
    monkeypatch.setattr(versao, "_git", lambda *a, **k: log if a[1] != "-1" else
                        f"{SHA}\x1f2026-10-14T03:10:00Z\x1ffeat(base): sai a tela\n")
    monkeypatch.setattr(casca, "_commit", lambda: "648c100")

    class Dia(datetime):                         # a data fica fixa: a aba só mostra os últimos 60 dias
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 14, 20, 0, tzinfo=tz)
    monkeypatch.setattr(versao, "datetime", Dia)
    versao.local.cache_clear()
    versao.historico.cache_clear()
    try:
        html = logado.get("/?aba=atualizacoes").get_data(as_text=True)
    finally:
        versao.local.cache_clear()
        versao.historico.cache_clear()
    aba = html.split('class="lead"', 1)[1].split('atu-rodape', 1)[0]
    assert not _re.search(r"\b\d{2}:\d{2}\b", aba)                          # nenhum horário na aba
    assert '<blockquote class="atu-pedido">' in aba and "<li>Saem as views e os templates.</li>" in aba
    assert "Prova" not in aba and "Co-Authored-By" not in aba and "<pre>" not in aba
    assert "<summary>O que mudou</summary>" in aba


def test_o_cartao_da_versao_tem_o_mesmo_recheio_das_outras_caixas():
    """14/10/2026, Levi: "Centralize esse Versão no Ar que está no início do Nexus, tá feião": o cartão é um link, e o
    espaço interno e a linha das caixas valiam só para <div>."""
    css = open("nexus/static/nexus.css", encoding="utf-8").read()
    assert ".gc-numeros>div,.gc-numeros>a{padding:18px 22px;border-left:1px solid var(--linha)}" in css



def test_a_aba_so_mostra_novidade_e_correcao_dos_ultimos_60_dias(app, logado, monkeypatch):
    """19/10/2026, Levi: "Em início > atualização deixe só novidade e correção sempre os últimos 60 dias!". A versão no
    ar pode ser um commit que não entra na lista (uma documentação): aí nenhum item leva o "no ar"."""
    doc = "dddd111222333444555666777888999000dddd"
    log = (f"{doc}\x1f2026-10-19T12:00:00-03:00\x1fdocs(base): o CLAUDE.md da base\x1f\x1e"
           "eeee111222333444555666777888999000eeee\x1f2026-10-18T12:00:00-03:00\x1ffeat(pcm): o quadro novo\x1f\x1e"
           "ffff111222333444555666777888999000ffff\x1f2026-09-01T12:00:00-03:00\x1ffix(campo): a foto da ronda\x1f\x1e"
           "1111111222333444555666777888999000aaaa\x1f2026-08-01T12:00:00-03:00\x1ffeat(base): velho demais\x1f\x1e"
           "2222111222333444555666777888999000bbbb\x1f2026-10-17T12:00:00-03:00\x1fMerge do setor Campo\x1f\x1e"
           "3333111222333444555666777888999000cccc\x1f2026-10-16T12:00:00-03:00\x1fperf(casca): mais rapido\x1f\x1e")
    monkeypatch.setattr(versao, "_git", lambda *a, **k: log if a[1] != "-1" else
                        f"{doc}\x1f2026-10-19T12:00:00-03:00\x1fdocs(base): o CLAUDE.md da base\n")
    monkeypatch.setattr(casca, "_commit", lambda: doc[:7])

    class Dia(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 19, 15, 0, tzinfo=tz)
    monkeypatch.setattr(versao, "datetime", Dia)
    versao.local.cache_clear()
    versao.historico.cache_clear()
    try:
        html = logado.get("/?aba=atualizacoes").get_data(as_text=True)
    finally:
        versao.local.cache_clear()
        versao.historico.cache_clear()
    aba = html.split('class="lead"', 1)[1]
    assert "o quadro novo" in aba and "a foto da ronda" in aba          # feat e fix dentro dos 60 dias
    assert "mais rapido" in aba and "Desempenho" in aba                 # e o perf (24/10/2026)
    for fora in ("velho demais", "o CLAUDE.md da base", "Merge do setor"):
        assert fora not in aba                                          # mais de 60 dias, docs e merge
    assert "no ar</span>" not in aba                                    # a versão no ar é a documentação
    assert "3 atualizações nos últimos 60 dias." in aba
    assert "Documentação" not in aba


def test_da_aba_corta_no_dia_do_pedido():
    from datetime import timedelta, timezone
    brt = timezone(timedelta(hours=-3))
    agora = datetime(2026, 10, 19, 12, 0, tzinfo=brt)
    itens = [{"tipo_id": "feat", "em": agora - timedelta(days=59, hours=23)},
             {"tipo_id": "fix", "em": agora - timedelta(days=60, hours=1)},
             {"tipo_id": "docs", "em": agora}, {"tipo_id": "feat", "em": None}]
    assert versao.da_aba(itens, agora) == [itens[0]]
