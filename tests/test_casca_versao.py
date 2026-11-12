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
    # só novidade e correção (19/10/2026, Levi: "deixe só novidade e correção"), do mês de hoje (12/11/2026)
    assert "mensagem sem tipo" not in html and "no ar</span>" in html
    assert "2 atualizações em outubro de 2026." in html


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

    class Dia(datetime):                         # a data fica fixa: a aba abre no mês de hoje
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



def test_a_aba_so_mostra_novidade_e_correcao_do_mes(app, logado, monkeypatch):
    """19/10/2026, Levi: "Em início > atualização deixe só novidade e correção sempre os últimos 60 dias!"; desde
    12/11/2026 um mês por vez, o atual no padrão ("sempre filtrado no mês atual, que dê para filtrar em outros meses
    também"). A versão no ar pode ser um commit que não entra na lista (uma documentação): aí nenhum item leva o "no
    ar"."""
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
        setembro = logado.get("/?aba=atualizacoes&mes=2026-09").get_data(as_text=True).split('class="lead"', 1)[1]
        invalido = logado.get("/?aba=atualizacoes&mes=1999-01").get_data(as_text=True).split('class="lead"', 1)[1]
    finally:
        versao.local.cache_clear()
        versao.historico.cache_clear()
    aba = html.split('class="lead"', 1)[1]
    assert "em outubro de 2026, da mais nova" in aba and "o quadro novo" in aba       # o feat do mês
    assert "mais rapido" in aba and "Desempenho" in aba                 # e o perf (24/10/2026)
    for fora in ("a foto da ronda", "velho demais", "o CLAUDE.md da base", "Merge do setor"):
        assert fora not in aba                                          # os outros meses, docs e merge
    assert "no ar</span>" not in aba                                    # a versão no ar é a documentação
    assert "2 atualizações em outubro de 2026." in aba
    assert "Documentação" not in aba
    # o filtro de mês: os meses que têm commit, o atual marcado e como o "sem filtro" do padrão dos filtros
    assert 'name="mes" data-padrao="2026-10"' in aba and 'data-fo>' in aba
    assert '<option value="2026-10" selected>outubro de 2026</option>' in aba
    assert '<option value="2026-09">setembro de 2026</option>' in aba and '<option value="2026-08">' in aba
    assert "a foto da ronda" in setembro and "o quadro novo" not in setembro
    assert "1 atualização em setembro de 2026." in setembro and '<option value="2026-09" selected>' in setembro
    assert "em outubro de 2026, da mais nova" in invalido               # o mês que não existe cai no atual


def test_da_aba_fica_no_mes_e_na_pessoa():
    from datetime import timedelta, timezone
    brt = timezone(timedelta(hours=-3))
    agora = datetime(2026, 10, 19, 12, 0, tzinfo=brt)
    itens = [{"tipo_id": "feat", "em": agora, "pessoa": "fulano"},
             {"tipo_id": "fix", "em": datetime(2026, 10, 1, 0, 0, tzinfo=brt), "pessoa": "beltrana"},
             {"tipo_id": "fix", "em": datetime(2026, 9, 30, 23, 59, tzinfo=brt), "pessoa": "fulano"},
             {"tipo_id": "docs", "em": agora, "pessoa": "fulano"}, {"tipo_id": "feat", "em": None, "pessoa": "fulano"}]
    assert versao.da_aba(itens, "2026-10") == itens[:2]
    assert versao.da_aba(itens, "2026-10", ["beltrana"]) == [itens[1]]
    assert versao.da_aba(itens, "2026-09") == [itens[2]] and versao.da_aba(itens, "2026-08") == []
    # os meses do filtro: os que têm commit e o de hoje, do mais novo; o pedido que não está na lista cai no de hoje
    em_novembro = datetime(2026, 11, 2, 9, 0, tzinfo=brt)
    assert versao.meses(itens, em_novembro) == [("2026-11", "novembro de 2026"), ("2026-10", "outubro de 2026"),
                                                ("2026-09", "setembro de 2026")]
    assert versao.mes_pedido("2026-09", itens, em_novembro) == "2026-09"
    assert versao.mes_pedido("2026-07", itens, em_novembro) == versao.mes_pedido(None, itens, em_novembro) == "2026-11"


def test_a_pessoa_do_commit_junta_as_contas_da_mesma_pessoa():
    """O git traz a mesma pessoa em duas contas (o nome de usuário e o nome completo, com e-mails diferentes): a chave
    é o 1º nome, sem acento nem caixa."""
    assert versao.pessoa_de("Fulano-1234") == versao.pessoa_de("Fulano de Tal") == "fulano"
    assert versao.pessoa_de("Élia Souza") == "elia" and versao.pessoa_de("") == "" and versao.pessoa_de(None) == ""


LOG_PESSOAS = (
    "a111111222333444555666777888999000aaaa\x1f2026-11-12T10:00:00-03:00\x1ffeat(pcm): o quadro novo\x1f\x1fFulano-1234\x1fp1\x1e"
    "a222111222333444555666777888999000aaaa\x1f2026-11-11T10:00:00-03:00\x1ffix(campo): a foto da ronda\x1f\x1fFulano de Tal\x1fp1\x1e"
    "a333111222333444555666777888999000aaaa\x1f2026-11-11T09:00:00-03:00\x1fdocs(base): o CLAUDE.md\x1f\x1fFulano-1234\x1fp1\x1e"
    "a444111222333444555666777888999000aaaa\x1f2026-11-10T10:00:00-03:00\x1fMerge do setor Campo\x1f\x1fFulano-1234\x1fp1 p2\x1e"
    "a555111222333444555666777888999000aaaa\x1f2026-11-10T09:00:00-03:00\x1ffeat(cos): o filtro da Beltrana\x1f\x1fBeltrana Souza\x1fp1\x1e"
    "a666111222333444555666777888999000aaaa\x1f2026-10-30T09:00:00-03:00\x1fperf(casca): mais rapido\x1f\x1fBeltrana Souza\x1fp1\x1e"
    "a777111222333444555666777888999000aaaa\x1f2026-10-29T09:00:00-03:00\x1ffix(base): o de outubro\x1f\x1fCicrano Lima\x1fp1\x1e")


def test_os_cartoes_de_commits_por_pessoa_e_o_filtro_por_pessoa_e_por_mes(app, logado, monkeypatch):
    """12/11/2026, Levi: "em início, atualizações, ao lado das atualizações, tivesse os cards de quantos commits as
    pessoas que estão mexendo no Nexus fizeram. E clicando nas pessoas vai ficar filtrado. E também que esteja sempre
    filtrado no mês atual, que dê para filtrar em outros meses também". O cartão conta todo commit do mês da pessoa (as
    duas contas do git juntas), sem os merges, e diz quantos são novidade, correção e desempenho."""
    monkeypatch.setattr(versao, "_git", lambda *a, **k: LOG_PESSOAS if a[1] != "-1" else
                        "a111111222333444555666777888999000aaaa\x1f2026-11-12T10:00:00-03:00\x1ffeat(pcm): o quadro novo\n")
    monkeypatch.setattr(casca, "_commit", lambda: "a111111")

    class Dia(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 12, 15, 0, tzinfo=tz)
    monkeypatch.setattr(versao, "datetime", Dia)
    versao.local.cache_clear()
    versao.historico.cache_clear()
    try:
        # o registro do git pede o autor e os pais no fim
        pedido = []
        versao.historico.cache_clear()
        monkeypatch.setattr(versao, "_git", lambda *a, **k: (pedido.append(a), LOG_PESSOAS)[1] if a[1] != "-1" else
                            "a111111222333444555666777888999000aaaa\x1f2026-11-12T10:00:00-03:00\x1ffeat(pcm): o quadro novo\n")
        html = logado.get("/?aba=atualizacoes").get_data(as_text=True)
        assert any(x.endswith("%x1f%an%x1f%P%x1e") for x in pedido[0])
        dela = logado.get("/?aba=atualizacoes&autor=beltrana").get_data(as_text=True)
        outubro = logado.get("/?aba=atualizacoes&mes=2026-10&autor=cicrano").get_data(as_text=True)
        estranho = logado.get("/?aba=atualizacoes&autor=ninguem").get_data(as_text=True)
    finally:
        versao.local.cache_clear()
        versao.historico.cache_clear()

    def cartoes(pagina):
        return pagina.split('class="atu-pessoas"', 1)[1].split("</aside>", 1)[0]

    def lista(pagina):
        return pagina.split('class="atualizacoes"', 1)[1].split('class="atu-pessoas"', 1)[0]

    lado = cartoes(html)
    assert "Commits em novembro de 2026" in lado
    # Fulano: 3 commits (o merge não conta), 1 novidade, 1 correção e 1 de outro tipo; o nome de gente, não o de usuário
    assert lado.index("Fulano de Tal") < lado.index("Beltrana Souza") and "Fulano-1234" not in lado
    fulano = lado.split("Fulano de Tal", 1)[1].split("</a>", 1)[0]
    assert '<b class="atu-pessoa-n">3</b>' in fulano and ">Novidade 1<" in fulano and ">Correção 1<" in fulano
    assert ">outros 1<" in fulano and "Desempenho" not in fulano
    assert '<b class="atu-pessoa-n">1</b>' in lado.split("Beltrana Souza", 1)[1].split("</a>", 1)[0]
    assert '<span class="atu-pessoa-nome">Todos</span><b class="atu-pessoa-n">4</b>' in lado
    assert "Cicrano" not in lado                                        # só commit em outubro
    # o clique no cartão filtra por aquela pessoa; sem filtro, o "Todos" é o marcado
    assert 'href="/?aba=atualizacoes&amp;autor=beltrana"' in lado and 'href="/?aba=atualizacoes" aria-current="true"' in lado
    assert "o quadro novo" in lista(html) and "o filtro da Beltrana" in lista(html) and "o de outubro" not in lista(html)
    assert "3 atualizações em novembro de 2026." in html
    assert '<option value="fulano">Fulano de Tal (3)</option>' in html and 'name="autor" multiple' in html
    # filtrado por ela: só as dela na lista; os cartões seguem todos, o dela marcado, e o clique nele volta a todas
    assert "o filtro da Beltrana" in lista(dela) and "o quadro novo" not in lista(dela)
    assert "1 atualização em novembro de 2026, de Beltrana Souza." in dela
    ela = cartoes(dela).split("Beltrana Souza", 1)[0].rsplit("<a ", 1)[1]
    assert 'href="/?aba=atualizacoes"' in ela and 'aria-current="true"' in ela
    assert "Fulano de Tal" in cartoes(dela) and '<option value="beltrana" selected>' in dela
    # outro mês: os cartões e a lista são os dele, e o clique guarda o mês
    assert "Commits em outubro de 2026" in cartoes(outubro) and "Cicrano Lima" in cartoes(outubro)
    assert "o de outubro" in lista(outubro) and "mais rapido" not in lista(outubro)
    assert 'href="/?aba=atualizacoes&amp;mes=2026-10&amp;autor=beltrana"' in cartoes(outubro)
    # a pessoa que não existe no mês não filtra nada
    assert "3 atualizações em novembro de 2026." in estranho



def test_contagem_por_tipo_na_ordem_da_aba():
    itens = [{"tipo_id": "fix"}, {"tipo_id": "perf"}, {"tipo_id": "fix"}, {"tipo_id": "feat"}]
    assert versao.contagem(itens) == [("feat", "Novidade", 1), ("fix", "Correção", 2), ("perf", "Desempenho", 1)]
    assert versao.contagem([{"tipo_id": "fix"}]) == [("fix", "Correção", 1)]       # tipo sem item não aparece


def test_os_dias_antes_de_hoje_ficam_recolhidos_com_a_contagem(app, logado, monkeypatch):
    """29/10/2026, Levi: "gostaria que os dias que fossem anteriores a hoje ficassem recolhidos e contando a quantidade
    de correção, novidade e desempenho". Hoje aberto; cada dia diz no cabeçalho quantos de cada tipo; o dia que tem o
    commit no ar diz isso também, recolhido ou não."""
    no_ar = "9999111222333444555666777888999000ffff"
    log = ("1111111222333444555666777888999000aaaa\x1f2026-10-29T09:00:00-03:00\x1ffeat(pcm): o quadro de hoje\x1f\x1e"
           "2222111222333444555666777888999000bbbb\x1f2026-10-28T18:00:00-03:00\x1ffix(campo): a foto da ronda\x1f\x1e"
           "3333111222333444555666777888999000cccc\x1f2026-10-28T17:00:00-03:00\x1ffix(base): o filtro\x1f\x1e"
           "4444111222333444555666777888999000dddd\x1f2026-10-28T16:00:00-03:00\x1fperf(casca): mais rapido\x1f\x1e"
           "5555111222333444555666777888999000eeee\x1f2026-10-28T15:00:00-03:00\x1fdocs(base): fora da aba\x1f\x1e"
           f"{no_ar}\x1f2026-10-20T10:00:00-03:00\x1ffeat(hseq): os extintores\x1f\x1e")
    monkeypatch.setattr(versao, "_git", lambda *a, **k: log if a[1] != "-1" else
                        f"{no_ar}\x1f2026-10-20T10:00:00-03:00\x1ffeat(hseq): os extintores\n")
    monkeypatch.setattr(casca, "_commit", lambda: no_ar[:7])

    class Dia(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 29, 15, 0, tzinfo=tz)
    monkeypatch.setattr(versao, "datetime", Dia)
    versao.local.cache_clear()
    versao.historico.cache_clear()
    try:
        html = logado.get("/?aba=atualizacoes").get_data(as_text=True)
    finally:
        versao.local.cache_clear()
        versao.historico.cache_clear()
    hoje, ontem, dia20 = html.split('<details class="atu-dia"')[1:]
    assert hoje.split(">", 1)[0].strip() == "open" and ">Hoje</h2>" in hoje
    assert "open" not in ontem.split(">", 1)[0] and ">Ontem</h2>" in ontem
    cab = ontem.split("</summary>", 1)[0]
    assert ">Correção 2<" in cab and ">Desempenho 1<" in cab and "Novidade" not in cab
    assert 'class="atu-dia-total" title="3 atualizações no dia">3<' in cab       # o total na ponta (29/10/2026)
    assert ">Novidade 1<" in hoje.split("</summary>", 1)[0] and 'title="1 atualização no dia">1<' in hoje
    cab20 = dia20.split("</summary>", 1)[0]
    assert "open" not in dia20.split(">", 1)[0] and ">20/10/2026</h2>" in cab20 and "no ar</span>" in cab20
    assert "a foto da ronda" in ontem and "fora da aba" not in html     # o item segue lá dentro, só recolhido
