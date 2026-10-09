"""Acompanhamento de chamados do OS Creator Web com a estética do Quadro da equipe da Engenharia (Levi, 08/10/2026:
"Precisamos padronizar a estética para que coisas parecidas não pareçam completamente diferentes, nesse caso gostei mais
da estética do da engenharia porém o card de KPIS eu gostei mais do de chamados").

Conferido aqui, com o Fracttal FALSO (a lista e os tickets são dublês; nada vai à rede):
- o cartão novo traz o nº da OS, o estado no canto, o ativo, onde, as etiquetas e o responsável;
- o quadro mantém o que os filtros, a contagem, o vazio, o Limpar filtros e o clique usam (acomp.js não mudou);
- a faixa de números (a que o Levi gosta) ficou como estava;
- o estado curto do cartão e a cor do avatar (acomp_web, puro).
Nomes e números são de mentira: o repositório é público."""
import datetime as dt
import re
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import chamados_obs_store as obs_store  # noqa: E402
from os_web import acomp_web as aw  # noqa: E402
from os_web import criar_app, rotas  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE) / "os_web"
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
HOJE = dt.datetime(2026, 9, 27, 10, 0)
EQUIPE_ID, EQUIPE_NOME = 900001, "Analista Teste"
NOTA = """[CHAMADO] Acompanhamento — STI · Estrutura Trackers
OS de campo: 9101 · Inspeção: 9102 · Ativo: TST100-ETKR1.100
Data da falha: 10/09/2026 13:28 · Menos de 7 dias: Sim"""


def _linha(i, folio, status=1, data="2026-09-20T12:00:00", data_fim="", resp_id=EQUIPE_ID, resp=EQUIPE_NOME):
    return {"id": i, "folio": str(folio), "cliente": "Cliente Teste", "usina": "Usina Teste 1", "ativo": "Tracker 1.100 TST",
            "tipo": "Estrutura Trackers", "tipo_tarefa": "Administrativa", "note": NOTA,
            "descricao": "[Tracker 1.100 TST] - Acompanhamento de chamado STI", "status_id": status,
            "status": api.WO_STATUS.get(status), "data": data, "data_fim": data_fim, "atribuido_a": resp,
            "id_atribuido": resp_id}


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_ID", str(EQUIPE_ID))
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_NOME", EQUIPE_NOME)
    monkeypatch.setattr(aw, "agora_brt", lambda: HOJE)
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})
    # o banco da Gridco: a última observação da 9104 foi ontem (a régua da cobrança do "Ticket aberto")
    monkeypatch.setattr(obs_store, "listar", lambda forcar=False: [
        {"id": "o1", "quando": "2026-09-26T09:00:00-03:00", "os": "9104", "ativo": "", "tipo": "obs", "texto": "x",
         "quem": "", "email": "", "extra": {}}])
    yield
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()


@pytest.fixture
def quadro(monkeypatch):
    """Chegou há 7 dias (9103), com o fornecedor (9104, ticket TK-2), finalizada em 26/09 (9105), uma no nome de outra
    pessoa (9106) e uma cujo ticket não deu para ler (9107)."""
    monkeypatch.setattr(api, "list_chamados", lambda **k: [
        _linha(1, 9103), _linha(2, 9104), _linha(3, 9105, status=3, data_fim="2026-09-26T12:00:00"),
        _linha(4, 9106, data="2026-09-25T12:00:00", resp_id=900002, resp="Técnico Teste"),
        _linha(5, 9107, data="2026-09-27T12:00:00")])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {2: "TK-2", 3: "TK-3", 5: None})
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": EQUIPE_NOME, "email": "teste@exemplo.invalid", "perfil": ""}
    return c.get("/os/chamados/acompanhamento").get_data(as_text=True)


def _coluna(h, chave):
    """Do começo da coluna até o começo da próxima (a última vai até o fim da página)."""
    return next(p for p in h.split('data-col="')[1:] if p.startswith(chave + '"'))


def _cartao(h, folio):
    ini = h.index('href="/os/chamados/acompanhamento/%s"' % folio)
    return h[h.rindex("<a ", 0, ini):h.index("</a>", ini)]


# ── o cartão novo ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_cartao_traz_os_campos_do_quadro_da_engenharia(quadro):
    c = _cartao(quadro, 9103)
    assert 'class="card cr k-a"' in c                                   # a fila (vermelha) e o fio da idade (âmbar)
    assert '<span class="k-os">OS 9103</span>' in c                     # o nº da OS em verde, mono
    assert '<span class="tag u-a">7 d</span>' in c                      # o estado no canto, colorido pela idade
    assert '<div class="k-tit">Tracker 1.100 TST</div>' in c            # o ativo em negrito
    assert '<div class="k-onde">TST100-ETKR1.100 · Cliente Teste · Usina Teste 1</div>' in c
    for chip in ('<span class="k-chip k-forn">STI</span>', '<span class="k-chip">Estrutura Trackers</span>',
                 '<span class="k-chip">inspeção 9102</span>'):
        assert chip in c                                                # fornecedor, tipo de ativo, inspeção de origem
    av = re.search(r'<span class="k-av k-av(\d)" aria-hidden="true">([^<]+)</span>', c)
    assert av and av.group(2) == "AT" and int(av.group(1)) == aw.cor_avatar(EQUIPE_NOME)
    assert '<span class="k-quem">Analista Teste</span>' in c
    assert 'title="chegou há 7 dias"' in c                              # a frase inteira continua no title


def test_ticket_aberto_finalizado_e_os_avisos(quadro):
    tk = _cartao(quadro, 9104)
    assert '<span class="k-chip k-tk">Ticket TK-2</span>' in tk and '<span class="tag u-m">1 d sem atualização</span>' in tk
    fim = _cartao(quadro, 9105)
    assert 'class="card cg k-m fim"' in fim and '<span class="tag u-m">fechado 26/09</span>' in fim
    fora = _cartao(quadro, 9106)
    assert '<span class="k-quem k-fora">no nome de Técnico Teste</span>' in fora
    nao_lido = _cartao(quadro, 9107)
    assert '<div class="dono">não consegui ler o ticket desta OS agora</div>' in nao_lido
    assert '<span class="tag u-m">hoje</span>' in nao_lido


def test_o_quadro_mantem_o_que_os_filtros_e_o_clique_usam(quadro):
    """O acomp.js não mudou: ele acha as colunas por .col, os cartões por .card, a contagem por [data-n], o vazio por
    [data-vazio] e filtra pelos data-* do cartão. O cartão inteiro continua sendo o link do chamado."""
    assert [m for m in re.findall(r'data-col="(\w+)"', quadro)] == ["chegou", "ticket", "fim"]
    chegou, ticket, fim = (_coluna(quadro, k) for k in ("chegou", "ticket", "fim"))
    assert "<em data-n>3</em>" in chegou and "<em data-n>1</em>" in ticket and "<em data-n>1</em>" in fim
    for col, vazio in ((chegou, "Nenhuma OS esperando ticket."), (ticket, "Nenhum ticket aberto no fornecedor."),
                       (fim, "Nenhum chamado finalizado nos últimos 90 dias.")):
        assert re.search(r'<p class="vazio oculto" data-vazio>%s</p>' % re.escape(vazio), col)
        assert col.index("data-vazio") > col.index('<div class="cards">')    # o vazio mora dentro da coluna
    c = _cartao(quadro, 9103)
    for attr in ('href="/os/chamados/acompanhamento/9103"', 'data-marca="STI"', 'data-cliente="Cliente Teste"',
                 'data-tipo="Estrutura Trackers"', 'data-equipe="1"', 'data-busca="9103 9102 9101 tst100-etkr1.100'):
        assert attr in c
    assert 'data-equipe="0"' in _cartao(quadro, 9106)
    for f in ("marca", "cliente", "tipo", "equipe", "busca"):
        assert 'data-f="%s"' % f in quadro
    assert "data-limpar>Limpar filtros</button>" in quadro and 'href="/os/chamados/acompanhamento?atualizar=1"' in quadro
    assert '<script src="/os/static/acomp.js"></script>' in quadro
    # a faixa de números ficou como estava (é a que o Levi gosta)
    assert '<div class="lbl">Sem ticket</div><div class="linha"><span class="val r">3</span>' in quadro
    assert 'a mais antiga: <b>9103</b>, 7 dias' in quadro


# ── a regra pura ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_estado_curto_no_jeito_da_engenharia():
    curto = lambda **k: aw.cartao(_linha(1, 9103, **k), "", "", HOJE)["tempo_curto"]  # noqa: E731
    assert curto(data="2026-09-27T12:00:00") == "hoje"
    assert curto(data="2026-09-26T12:00:00") == "1 d"
    assert curto(data="2026-08-23T12:00:00") == "35 d"
    tk = aw.cartao(_linha(1, 9103, data="2026-09-01T12:00:00"), "TK-9", "2026-09-18T09:00:00-03:00", HOJE)
    assert (tk["tempo_curto"], tk["tempo"]) == ("9 d sem atualização", "há 9 dias sem atualização")
    assert aw.cartao(_linha(1, 9103), "TK-9", "2026-09-27T08:00:00-03:00", HOJE)["tempo_curto"] == "atualizado hoje"
    f = aw.cartao(_linha(1, 9103, status=3, data_fim="2026-09-26T12:00:00"), "TK-9", "", HOJE)
    assert (f["tempo_curto"], f["tempo"]) == ("fechado 26/09", "em 26/09")      # a frase de antes não mudou
    assert aw.cartao(_linha(1, 9103, status=2), "", "", HOJE, finalizado="2026-09-26T11:30:00-03:00")["tempo_curto"] == \
        "em verificação 26/09"
    assert aw.cartao(_linha(1, 9103, status=4), "", "", HOJE)["tempo_curto"] == "cancelado"


def test_a_cor_do_avatar_e_a_mesma_para_a_mesma_pessoa():
    assert aw.cor_avatar("Analista Teste") == aw.cor_avatar("analista  TESTE") == aw.cor_avatar("Análista Teste")
    assert {aw.cor_avatar(n) for n in ("Ana", "Bruno", "Carla", "Diego", "Elisa", "Fabio", "Gil")} <= set(range(aw.CORES_AVATAR))
    assert aw.cor_avatar("") == 0
    css = (WEB / "static" / "chamados.css").read_text(encoding="utf-8")
    assert sorted(int(n) for n in re.findall(r"\.k-av(\d)\{", css)) == list(range(aw.CORES_AVATAR))


def test_toda_classe_do_cartao_novo_tem_regra_no_css():
    """Um nome de classe com erro de digitação deixaria o pedaço do cartão sem estilo, em silêncio."""
    html = (WEB / "templates" / "acomp.html").read_text(encoding="utf-8")
    css = (WEB / "static" / "chamados.css").read_text(encoding="utf-8")
    usadas = set(re.findall(r"\bk-(?:cab|os|tit|onde|etq|chip|forn|tk|pe|av|quem|fora)\b", html))
    assert len(usadas) == 12
    assert [c for c in sorted(usadas) if "." + c not in css] == []
    assert ".card.k-r{" in css and ".card.k-a{" in css and "--k:var(--ok)" in css     # o fio da idade
