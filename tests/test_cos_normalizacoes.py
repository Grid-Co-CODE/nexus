"""Torre COS: a tela Normalizações (27/10/2026, Levi: "Gostaria de inserir no COS" a API de normalizações da Ronda COS)
— quando cada usina voltou, pela hora que o COS registrou, e se a OS dela já fechou no Fracttal.

As normalizações vêm do Andamento (`GET /api/normalizacoes`, incremental pelo `cursor`); o Nexus as guarda em memória
pelo `registro` e só filtra e conta (nexus/cos/normalizacoes.py). Nada aqui vai à rede, e os dados são fictícios."""
import urllib.parse

import pytest

from nexus.cos import andamento as AND
from nexus.cos import normalizacoes as NO

CHAVE = "chave-de-teste-do-andamento"
AGORA = AND.instante("2026-10-27T10:00:00-03:00")


def _n(registro, volta="2026-10-27T08:00:00-03:00", inicio="2026-10-27T07:00:00-03:00", fora=60, os="17001",
       cliente="CLIENTE A", usina="Usina Exemplo Um", severidade="ALTO", aberta=None, **mudar):
    n = {"registro": registro, "os": os, "os_relacionadas": [], "cliente": cliente, "usina_codigo": "EX-UM100",
         "usina": usina, "equipamentos": [], "tipo_falha": "FALHA_COMUNICACAO", "tipo_falha_rotulo": "Falha de comunicação",
         "severidade": severidade, "estado": "NORMALIZADO", "normalizada": True, "inicio": inicio, "normalizado_em": volta,
         "fora_min": fora, "hora_real": True, "fim_corrigido": False, "declarada_em": volta, "declarada_por": "pessoa",
         "desfeita_em": None, "encerrada_em": None, "encerrada_por": None, "os_aberta_no_fracttal": aberta,
         "informe": None, "fora_do_escopo_oem": False, "mudou_em": volta}
    n.update(mudar)
    return n


def _resp(itens, cursor="c1", mais=False, **mudar):
    d = {"versao": 1, "gerado_em": "2026-10-27T10:00:00-03:00", "cursor": cursor, "mais": mais, "normalizacoes": itens}
    d.update(mudar)
    return d


ABERTA = {"status": 2, "concluida_pct": 100, "varrida_em": "2026-10-27T09:43:00-03:00"}
ITENS = [
    _n("r1"),                                                                               # hoje, fechada
    _n("r2", volta="2026-10-19T05:53:00-03:00", inicio="2026-10-19T02:00:00-03:00", fora=233, os="16702",
       usina="Usina Exemplo Dois", cliente="CLIENTE B", severidade="CRITICO",
       aberta={"status": 1, "concluida_pct": 40, "varrida_em": "2026-10-27T09:13:00-03:00"}),   # 8 dias, aberta
    _n("r3", volta="2026-10-26T20:00:00-03:00", fora=30, aberta=ABERTA),                   # ontem, aberta
    _n("r4", volta="2026-10-26T09:00:00-03:00", hora_real=False, fora=0),                   # sem hora real
    _n("r5", volta="2026-10-25T09:00:00-03:00", normalizada=False, estado="TRATATIVA_REMOTA"),   # desfeita
    _n("r6", volta="2026-10-05T09:00:00-03:00", fora=600),                                  # 22 dias
]


@pytest.fixture(autouse=True)
def _limpa():
    AND.limpar_cache()
    NO.limpar()
    yield
    NO.limpar()


@pytest.fixture
def ligada(app):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002", NEXUS_COS_ANDAMENTO_CHAVE=CHAVE,
                      NEXUS_COS_ANDAMENTO_CLIENTES="Cliente A")
    return app


def _servir(monkeypatch, *respostas):
    """Cada pedido leva a próxima resposta (a última se repete). Guarda o `desde` de cada pedido."""
    pedidos, fila = [], list(respostas)

    def pedir(f, caminho, timeout=AND.TIMEOUT_S):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(caminho).query)
        pedidos.append((urllib.parse.urlsplit(caminho).path, q.get("desde", [""])[0], timeout))
        r = fila.pop(0) if len(fila) > 1 else fila[0]
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(AND, "_pedir", pedir)
    return pedidos


def _painel(**filtros):
    return NO.painel(AND.Leitura("", {"itens": ITENS, "carregando": False}), AGORA, **filtros)


# --- as contas -------------------------------------------------------------------------------------------------------

CRIADORES = {"17001": "Fulana Operadora", "16702": "Ciclano Operador"}


def test_o_mes_corrente_no_padrao_e_a_desfeita_sai_da_lista():
    """Levi, 27/10/2026: "Pode tirar esses filtros de 7, 30 dias ou último dia"."""
    p = _painel()
    assert [i["registro"] for i in p.itens] == ["r1", "r3", "r4", "r2", "r6"]      # outubro, a mais recente primeiro
    assert p.desfeitas == 1
    assert NO.mes_pedido("x", AGORA) == NO.mes_pedido("2026-07", AGORA) == "2026-10"
    assert not hasattr(NO, "DIAS") and not hasattr(NO, "SEVERIDADES")


def test_a_faixa_conta_a_os_aberta_e_a_mediana_sem_a_hora_falsa():
    r = _painel().resumo
    assert (r["total"], r["abertas"], r["abertas_pct"], r["abertas_7d"], r["sem_hora_real"]) == (5, 2, 40, 1, 1)
    assert r["mediana"] == "2 h 26"                    # mediana de 60, 233, 30 e 600 (o 0 sem hora real fica fora)
    # o status do Fracttal não muda a faixa (senão a fatia aberta seria sempre 100%)
    assert _painel(status="processo").resumo == r


def test_os_filtros_cliente_usina_criado_por_status_e_texto():
    """Levi, 27/10/2026: "Filtros: Cliente, Usina, Criado por, Status fracttal, um filtro livre para digitar texto"."""
    def regs(**f):
        return [i["registro"] for i in _painel(criadores=CRIADORES, **f).itens]
    assert regs(cliente="CLIENTE B") == ["r2"]
    assert regs(usina="Usina Exemplo Dois") == ["r2"]
    assert regs(criado_por="Fulana Operadora") == ["r1", "r3", "r4", "r6"]
    assert regs(status="processo") == ["r2"] and regs(status="verificacao") == ["r3"]
    assert regs(status="fechada") == ["r1", "r4", "r6"]
    assert regs(busca="16702") == ["r2"] and regs(busca="exemplo dois") == ["r2"] and regs(busca="ciclano") == ["r2"]
    assert regs(status="inventado") == regs()                                       # valor estranho: sem o filtro


def test_as_opcoes_dos_filtros_contam_o_mes_antes_dos_filtros():
    p = _painel(cliente="CLIENTE B", criadores=CRIADORES)
    assert p.contagem["cliente"] == {"CLIENTE A": 4, "CLIENTE B": 1}
    assert p.contagem["usina"] == {"Usina Exemplo Dois": 1}                         # as usinas do cliente escolhido
    assert p.contagem["criado_por"] == {"Ciclano Operador": 1, "Fulana Operadora": 4}
    assert p.contagem["status"] == {"processo": 1, "verificacao": 1, "fechada": 3}
    assert p.contagem["sem_criador"] == 0
    assert _painel(criadores={"16702": "Ciclano Operador"}).contagem["sem_criador"] == 4     # 17001 ainda não lida


def test_a_os_aberta_diz_ha_quantos_dias_da_volta_e_a_varredura_mais_nova():
    p = _painel()
    i = {x["registro"]: x for x in p.itens}
    assert (i["r2"]["aberta"], i["r2"]["status"], i["r2"]["pct"], i["r2"]["aberta_ha_dias"]) == (True, "Em processo", 40, 8)
    assert (i["r3"]["status_card"], i["r3"]["aberta_ha_dias"]) == ("Em Verificação", 0)
    assert not i["r1"]["aberta"] and p.varredura.strftime("%H:%M") == "09:43"


def test_o_csv_leva_a_lista_filtrada_e_o_que_a_tela_resume():
    """Levi, 27/10/2026: "Botão de exportar csv"."""
    linhas = NO.csv_linhas(_painel(status="processo", criadores=CRIADORES))
    assert len(linhas) == 1 and len(linhas[0]) == len(NO.CSV_COLUNAS)
    d = dict(zip(NO.CSV_COLUNAS, linhas[0]))
    assert (d["OS"], d["Início"], d["Normalização"], d["Tempo fora (min)"]) == ("16702", "19/10/2026 02:00",
                                                                               "19/10/2026 05:53", 233)
    assert (d["Cliente"], d["Usina"], d["Criado por"], d["Status no Fracttal"], d["% concluída"]) == (
        "CLIENTE B", "Usina Exemplo Dois", "Ciclano Operador", "Em processo", 40)
    assert d["Severidade"] == "Critico" and d["Dias aberta depois da volta"] == 8 and d["Registrada"] == "registrada pelo COS"


def test_por_mes_o_mes_inteiro_pela_hora_da_volta():
    """Levi, 27/10/2026: "a única mudança que quero é ver por mês"."""
    assert [(k, r) for k, r, _i, _f in NO.meses(AGORA)] == [("2026-10", "Outubro"), ("2026-09", "Setembro"),
                                                            ("2026-08", "Agosto")]
    assert [m[0] for m in NO.meses(AND.instante("2026-01-10T10:00:00-03:00"))] == ["2026-01", "2025-12", "2025-11"]
    assert NO.meses(AND.instante("2026-01-10T10:00:00-03:00"))[1][1] == "Dezembro de 2025"
    itens = ITENS + [_n("s1", volta="2026-09-30T23:59:00-03:00"), _n("o1", volta="2026-10-01T00:00:00-03:00")]
    p = NO.painel(AND.Leitura("", {"itens": itens}), AGORA, mes="2026-10")
    assert [i["registro"] for i in p.itens] == ["r1", "r3", "r4", "r2", "r6", "o1"]       # o mês todo, sem a desfeita
    p = NO.painel(AND.Leitura("", {"itens": itens}), AGORA, mes="2026-09")
    assert [i["registro"] for i in p.itens] == ["s1"] and p.resumo["total"] == 1
    assert NO.mes_pedido("2026-07", AGORA) == "2026-10" and NO.mes_pedido("2026-09", AGORA) == "2026-09"


def test_a_duracao_em_palavras():
    assert [NO.duracao(m) for m in (0, 59, 60, 75, 2879, 2880, 3000, None)] == [
        "0 min", "59 min", "1 h", "1 h 15", "47 h 59", "2 d", "2 d 2 h", "—"]


# --- a leitura incremental -----------------------------------------------------------------------------------------

def test_a_primeira_carga_pagina_e_depois_so_o_que_mudou(ligada, monkeypatch):
    pedidos = _servir(monkeypatch, _resp(ITENS[:3], "c1", mais=True), _resp(ITENS[3:], "c2"),
                      _resp([_n("r1", aberta=ABERTA)], "c3"))
    l = NO.ler(ligada.config, AGORA)
    assert len(l.dados["itens"]) == 6 and not l.dados["carregando"]
    # a 1ª carga desde o 1º dia do mês mais antigo da tela (em 27/10: 01/08), a página seguinte já pelo cursor
    assert pedidos[0][0] == "/api/normalizacoes" and pedidos[0][1] == "2026-08-01T00:00:00-03:00"
    assert [p[1] for p in pedidos[1:]] == ["c1"] and pedidos[0][2] == NO.TIMEOUT_S
    # dentro do minuto não pergunta de novo
    assert NO.ler(ligada.config, AGORA) and len(pedidos) == 2
    # passado o minuto, pergunta pelo cursor, e o mesmo registro que volta SUBSTITUI (não soma)
    monkeypatch.setattr(NO.time, "monotonic", lambda: 10 ** 9)
    l = NO.ler(ligada.config, AGORA)
    assert pedidos[-1][1] == "c2" and len(l.dados["itens"]) == 6
    assert next(n for n in l.dados["itens"] if n["registro"] == "r1")["os_aberta_no_fracttal"] == ABERTA


def test_a_carga_longa_continua_no_pedido_seguinte(ligada, monkeypatch):
    monkeypatch.setattr(NO, "PAGINAS_POR_PEDIDO", 2)
    pedidos = _servir(monkeypatch, _resp([_n("a")], "c1", mais=True), _resp([_n("b")], "c2", mais=True),
                      _resp([_n("c")], "c3"))
    l = NO.ler(ligada.config, AGORA)
    assert l.dados["carregando"] and len(l.dados["itens"]) == 2
    l = NO.ler(ligada.config, AGORA)                 # sem esperar o minuto: ainda carregando
    assert not l.dados["carregando"] and len(l.dados["itens"]) == 3 and pedidos[-1][1] == "c2"


def test_a_falha_guarda_o_que_ja_veio_e_explica_o_404(ligada, monkeypatch):
    _servir(monkeypatch, AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá", 404))
    l = NO.ler(ligada.config, AGORA)
    assert l.dados is None and "ainda não tem a rota das normalizações" in l.erro
    NO.limpar()
    _servir(monkeypatch, _resp(ITENS), AND.FonteErro("o Andamento não respondeu (TimeoutError)"))
    assert len(NO.ler(ligada.config, AGORA).dados["itens"]) == 6
    monkeypatch.setattr(NO.time, "monotonic", lambda: 10 ** 9)
    l = NO.ler(ligada.config, AGORA)
    assert l.velha and len(l.dados["itens"]) == 6 and "não respondeu" in l.erro
    NO.limpar()
    _servir(monkeypatch, _resp(ITENS, versao=2))
    assert "versão 2 das normalizações" in NO.ler(ligada.config, AGORA).erro


def test_o_que_passou_da_janela_sai_da_memoria(ligada, monkeypatch):
    _servir(monkeypatch, _resp(ITENS + [_n("velha", volta="2026-07-31T23:00:00-03:00")]))
    assert {n["registro"] for n in NO.ler(ligada.config, AGORA).dados["itens"]} == {f"r{i}" for i in range(1, 7)}


# --- a tela ----------------------------------------------------------------------------------------------------------

def test_a_tela(ligada, logado, monkeypatch):
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    _servir(monkeypatch, _resp(ITENS))
    html = logado.get("/t/cos/normalizacoes").get_data(as_text=True)
    assert html.index('data-folio="17001"') < html.index('data-folio="16702"')
    assert "Em processo 40%" in html and "aberta 8 dias depois da volta" in html
    assert 'data-status="Em Processo"' in html and "NexusOsCard" in html
    assert "sem hora real" in html and "2 h 26" in html and "fora da lista" in html
    # as colunas na ordem pedida, sem a severidade; o "Como se conta" na exclamação ao lado do título
    cab = html.split("<thead>", 1)[1].split("</thead>", 1)[0]
    assert [c.split(">")[-1] for c in cab.split("</th>")[:-1]] == ["OS", "Início", "Normalização", "Cliente", "Usina",
                                                                  "Operador", "No Fracttal"]
    assert "Severidade" not in cab and "Crítico" not in html and 'class="hs-aviso"' in html
    assert "Último dia" not in html and "Últimos 7 dias" not in html
    assert "lendo no Fracttal" in html                       # sem o Fracttal no teste, quem criou ainda não foi lido
    assert "varredura do Fracttal às <b>09:43</b>" in html
    html = logado.get("/t/cos/normalizacoes?mes=2026-10").get_data(as_text=True)
    assert 'aria-current="page">Outubro<' in html and 'data-folio="16702"' in html and "Setembro" in html
    html = logado.get("/t/cos/normalizacoes?status=processo").get_data(as_text=True)
    assert 'data-folio="16702"' in html and 'data-folio="17001"' not in html and "Limpar os filtros" in html
    # o CSV, com os filtros, e o texto que o Excel leria como fórmula vai com apóstrofo
    _servir(monkeypatch, _resp(ITENS + [_n("rx", os="17009", informe={"resumo": "=HYPERLINK(1)"})]))
    NO.limpar()
    r = logado.get("/t/cos/normalizacoes?formato=csv&q=17009")
    corpo = r.data.decode("utf-8")
    assert r.status_code == 200 and r.mimetype == "text/csv" and "normalizacoes-2026-10.csv" in r.headers["Content-Disposition"]
    assert corpo.startswith("\ufeffOS;") and "17009" in corpo and "'=HYPERLINK(1)" in corpo and "17001" not in corpo


def test_a_tela_sem_fonte(ligada, app, logado):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="", NEXUS_COS_ANDAMENTO_CHAVE="")
    assert "não está ligada neste servidor" in logado.get("/t/cos/normalizacoes").get_data(as_text=True)


def test_a_tela_vem_depois_das_os_em_aberto():
    from nexus.torres.cos import TORRE
    ids = [t.id for t in TORRE.telas]
    assert ids.index("normalizacoes") == ids.index("os-abertas") + 1


def test_nao_ha_chave_nem_endereco_na_tela(ligada, logado, monkeypatch):
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    _servir(monkeypatch, AND.FonteErro("o Andamento recusou a chave do Nexus", 401))
    html = logado.get("/t/cos/normalizacoes").get_data(as_text=True)
    assert "recusou a chave" in html and CHAVE not in html and "andamento.exemplo" not in html
