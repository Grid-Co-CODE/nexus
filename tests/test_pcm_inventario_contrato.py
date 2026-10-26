"""O inventário do almoxarifado no PCM (26/10/2026, Levi): o contrato do livro das contagens que o App de Campo
publica, o "não contei" que nunca é zero e o almoxarifado de teste que fica fora das telas e do histórico. Desenho:
docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md (seções 4.1, 5 e 6)."""
from datetime import datetime
from pathlib import Path

from test_campo_visao import BRT, banco  # noqa: F401  (banco é fixture)
from test_dados_almoxarifado import ALMOX_LIVRO, BASE, CFG, IRC, MES, NOB, _api, _saldo
from test_pcm_almoxarifado import _semear as _semear_app
from test_pcm_almoxarifado import ALT, _s

from nexus import config
from nexus.campo import visao
from nexus.dados import almoxarifado as A

RAIZ = Path(__file__).resolve().parent.parent


# ── o contrato do livro das contagens ────────────────────────────────────────────────────────────────────────────────

def test_contrato_das_contagens():
    """O contrato com o App, na ordem (coluna nova só no FIM, dos dois lados). Quem contou vai como HMAC do e-mail:
    o livro é lido pela API aberta e o repositório é público, e-mail nunca."""
    assert A.LIVRO_CONTAGENS == "almoxarifado_contagens_app_campo" and A.ABA_CONTAGENS == "Contagens"
    assert A.COLUNAS_CONTAGENS == ("ID da contagem", "Enviada em", "Contada em", "ID do almoxarifado", "Usina", "Tipo",
                                   "ID do item", "Código", "Contado", "Identificado como", "Descrição", "Foto",
                                   "Contou (HMAC)", "ID da linha")
    assert "Contou (HMAC)" in A.COLUNAS_CONTAGENS and len(A.COLUNAS_CONTAGENS) == 14
    assert A.COLUNAS_CONTAGENS[-1] == "ID da linha"      # coluna nova só no FIM, dos dois lados
    assert not any("e-mail" in c.lower() or "email" in c.lower() for c in A.COLUNAS_CONTAGENS)
    assert A.TIPOS_CONTAGEM == ("item", "identificar", "fora_do_catalogo")


def test_contado_vazio_nao_e_zero():
    """Em branco é "não contei" (a peça não será tocada); só o 0 digitado é "zerar". A API devolve tudo como texto, e o
    sync-xlsx escreve o vazio como "None": virar 0 zeraria o estoque de uma peça que ninguém contou."""
    assert A.contado("") is None and A.contado(None) is None and A.contado("   ") is None
    assert A.contado("None") is None and A.contado("none") is None
    assert A.contado("0") == 0.0 and A.contado(0) == 0.0 and A.contado("0,0") == 0.0
    assert A.contado("3,0") == 3.0 and A.contado("3.0") == 3.0 and A.contado(3) == 3.0 and A.contado(" 12 ") == 12.0
    assert A.contado("abc") is None and A.contado(True) is None
    assert A.contado("nan") is None and A.contado("inf") is None        # número que não é número: não contou


def test_ids_de_teste_da_configuracao():
    assert A.ids_de_teste({}) == set() and A.ids_de_teste(None) == set()
    assert A.ids_de_teste({"NEXUS_ALMOX_TESTE_IDS": ""}) == set()
    assert A.ids_de_teste({"NEXUS_ALMOX_TESTE_IDS": "999"}) == {"999"}
    assert A.ids_de_teste({"NEXUS_ALMOX_TESTE_IDS": " 999 , 1000,, "}) == {"999", "1000"}
    assert A.ids_de_teste({"NEXUS_ALMOX_TESTE_IDS": 999}) == {"999"}


def test_chave_do_almoxarifado_de_teste_e_opcional_e_documentada():
    assert "NEXUS_ALMOX_TESTE_IDS" in config.OPCIONAIS
    assert "NEXUS_ALMOX_TESTE_IDS=" in RAIZ.joinpath(".env.example").read_text("utf-8")
    # o valor chega do .env à configuração do app como qualquer opcional
    cfg = config.carregar_config({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": "s", "NEXUS_ALMOX_TESTE_IDS": "999"})
    assert A.ids_de_teste(cfg) == {"999"}


# ── o almoxarifado de teste fora das telas e do histórico ────────────────────────────────────────────────────────────

def test_almoxarifado_de_teste_fora_das_telas(app, banco, monkeypatch):  # noqa: F811
    """A prova das gravações no Fracttal é num almoxarifado de teste, nunca num de usina: ele não pode inflar os
    números do PCM (abaixo do mínimo, almoxarifados) nem a fila de reposição. Os livros do App continuam inteiros: o
    ciclo diz quantas linhas o Saldo tem (as do teste incluídas), e o filtro vem depois dessa conferência."""
    from nexus.pcm import almoxarifado as T
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 25, 10, 0, tzinfo=BRT))
    _semear_app(banco, saldo_extra=[_s(1, 999, ALT, 0, 5)])           # no teste: zerado e abaixo do mínimo
    visao.limpar()
    antes = T.montar().dados
    assert antes["estado"] == "ok" and antes["kpis"]["almoxarifados"] == 3 and antes["kpis"]["abaixo"] == 2
    app.config.update(NEXUS_ALMOX_TESTE_IDS="999")
    visao.limpar()
    d = T.montar().dados
    assert d["estado"] == "ok" and d["aviso"] == "", d["aviso"]      # o ciclo não foi tratado como "pela metade"
    assert d["kpis"]["almoxarifados"] == 2 and d["kpis"]["abaixo"] == 1
    assert "999" not in {x["id_almox"] for x in d["linhas"]}
    assert "999" not in {x["id_almox"] for x in d["reposicao"]}
    assert "999" not in {c["id"] for c in d["por_almoxarifado"]}
    assert "Almoxarifado 999" not in d["almoxarifados"]
    assert all("Almoxarifado 999" not in c["almoxes"] for c in d["catalogo"])


def test_almoxarifado_de_teste_fora_da_foto_do_historico():
    """O histórico só cresce: uma linha do teste gravada no livro do mês ficaria para sempre nas contas do PCM. A foto
    e a dimensão do almoxarifado saem sem ele; a conferência do ciclo (`Linhas de saldo`) segue pelo livro inteiro do
    App, senão todo ciclo com o teste seria recusado como "pela metade"."""
    from nexus.dados import carga
    teste = [_saldo(1, 999, IRC, 0, 5)]
    api = _api(saldo_extra=teste)
    r = carga.gerar_almoxarifado(dict(CFG, NEXUS_ALMOX_TESTE_IDS="999"), api)
    assert "nao_aplica" not in r and r["saldo_linhas"] == 3 and r["almoxarifados"] == 2, r
    assert {l["id_almoxarifado"] for l in api.linhas(MES, "fato_saldo_almox")} == {"123021", "123675"}
    assert len(api.linhas(MES, "fato_saldo_almox")) == 3
    assert {l["id_almoxarifado"] for l in api.linhas(ALMOX_LIVRO, "dim_almoxarifado")} == {"123021", "123675"}
    # sem a chave, o mesmo livro do App entra inteiro (a prova de que o teste acima enxerga a diferença)
    inteiro = _api(saldo_extra=teste)
    r = carga.gerar_almoxarifado(CFG, inteiro)
    assert r["saldo_linhas"] == 4 and r["almoxarifados"] == 3


# ── o fato no catálogo ───────────────────────────────────────────────────────────────────────────────────────────────

def test_contagem_no_catalogo():
    """Fonte nova entra primeiro no catálogo (PRIORIDADE 0), com o grão e as dimensões declarados; livro novo do App não
    pode aparecer como "novo" no radar da Governança."""
    from nexus.dados import catalogo, explica
    f = catalogo.POR_ID["contagem_inventario"]
    assert f.estado == "origem" and f.area == "pcm" and not f.conformado_em
    assert f.janela_origem == "90 dias (App)"
    assert f.fontes == (f"{A.LIVRO_CONTAGENS} · {A.ABA_CONTAGENS}",) and f.livro == f.fontes[0]
    assert f.grao.startswith("1 linha") and "peça" in f.grao and f.tipo in catalogo.TIPOS_FATO
    # a origem é como o App grava: usina pelo nome do Fracttal, pessoa pelo HMAC, o item no cadastro próprio do
    # almoxarifado (o mesmo `prop` do saldo); os IDs do Nexus vêm com o fato conformado, numa fase seguinte
    assert (f.dims["usina"][0], f.dims["pessoa"][0], f.dims["equipamento"][0]) == ("nome", "hmac", "prop")
    assert f.dims["data"][0] == "cod" and f.dims["cliente"][0] == f.dims["equipe"][0] == "nao"
    # a chave é a contagem e o ID da linha (um por peça, do App): duas peças fora do catálogo com a mesma descrição na
    # mesma contagem não podem colidir
    assert f.chave == ("ID da contagem", "ID da linha") and set(f.chave) <= set(A.COLUNAS_CONTAGENS)
    assert f.tipo == "transacao" and [m.coluna for m in f.medidas] == ["contado_qtd"]
    assert all(catalogo.medida_valida(m) for m in f.medidas)
    assert explica.RESUMO.get(f.id) and explica.PARA_QUE.get(f.id)
    assert 15 <= len(explica.RESUMO[f.id]) <= 70 and not explica.RESUMO[f.id].endswith(".")
    assert explica.PARA_QUE[f.id].endswith(".") and len(explica.PARA_QUE[f.id]) >= 80


# ── o teste fora da Base → Ligações e fora da reserva do histórico ───────────────────────────────────────────────────────

def test_almoxarifado_de_teste_fora_da_ligacao(monkeypatch):
    """O local do almoxarifado de teste ("Cliente - Usina - UF") não é usina para ligar: sem o filtro, ele apareceria na
    Base → Ligações como um local do Fracttal sem usina, para alguém ligar à mão."""
    import requests
    from pg_falso import ApiPGFalsa
    from test_campo_visao import _aba
    from nexus.cadastro import ligacoes as L
    api = ApiPGFalsa()
    for _sis, wb, aba, *_r in L.FONTES_API:
        _aba(api, wb, aba, [])
    for _sis, wb, ref in L.FONTES_ABA:
        _aba(api, wb, ref, [])
    teste = "// Teste/ Teste - Local de Teste - PA/"
    _aba(api, A.LIVRO_SALDO, A.ABA_SALDO, [_saldo(1, 123675, NOB, 1, 1), _saldo(1, 999, teste, 1, 1)])
    monkeypatch.setattr(requests, "get", api.get)
    monkeypatch.setattr(L, "fracttal", lambda config: [])
    com = L.fontes({"GRIDCO_DB_API": BASE})
    assert [i["chave"] for i in com[L.FRACTTAL]] == ["RenoGrid - Nobres 1 - MT", "Teste - Local de Teste - PA"]
    sem = L.fontes({"GRIDCO_DB_API": BASE, "NEXUS_ALMOX_TESTE_IDS": "999"})
    assert [i["chave"] for i in sem[L.FRACTTAL]] == ["RenoGrid - Nobres 1 - MT"]


def test_almoxarifado_de_teste_fora_da_reserva_do_historico(app, banco, monkeypatch):  # noqa: F811
    """A reserva (o ciclo do App recusado, a tela mostra a foto guardada no histórico) também deixa o teste de fora: o ID
    pode ser posto na chave DEPOIS de a carga já ter gravado a linha dele no livro do mês."""
    from nexus.dados import carga
    from nexus.pcm import almoxarifado as T
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 25, 10, 0, tzinfo=BRT))
    _semear_app(banco, saldo_extra=[_s(1, 999, ALT, 0, 5)])
    carga.gerar_almoxarifado(CFG, banco)                       # sem a chave: a linha do teste vai para o histórico
    assert "999" in {l["id_almoxarifado"] for l in banco.linhas(MES, "fato_saldo_almox")}
    _semear_app(banco, saldo_inicio="2026-10-26T03:00:05Z", saldo_extra=[_s(1, 999, ALT, 0, 5)])  # o Saldo é de outro ciclo
    visao.limpar()
    antes = T.montar().dados
    assert antes["aviso"].startswith("Os livros do App chegaram de ciclos diferentes")        # é a reserva
    assert "999" in {x["id_almox"] for x in antes["linhas"]} and antes["kpis"]["almoxarifados"] == 3
    app.config.update(NEXUS_ALMOX_TESTE_IDS="999")
    visao.limpar()
    d = T.montar().dados
    assert d["estado"] == "ok" and d["aviso"].startswith("Os livros do App chegaram de ciclos diferentes")
    assert "999" not in {x["id_almox"] for x in d["linhas"]} and "999" not in {x["id_almox"] for x in d["reposicao"]}
    assert d["kpis"]["almoxarifados"] == 2 and d["kpis"]["abaixo"] == 1
    assert "999" not in {c["id"] for c in d["por_almoxarifado"]}
