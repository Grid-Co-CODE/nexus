"""Fase 3 dos setores conversando (03/11/2026): o pedido a uma área com o prazo que quem pede escolhe (Levi: "Quem pede
sempre escolhe"), sobre insight, OS ou usina; o retorno da área; a Caixa, o sino e o Tempo de resposta; e o livro
`nexus_pedidos`. Nomes e textos inventados."""
from datetime import datetime, timedelta, timezone

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture: o banco falso)
from test_comando_insights import PESSOA, _aberta, _cliente, _codigo, limpo, motor_dublado  # noqa: F401  (fixtures)

from nexus.comando import motor as MO
from nexus.comando import pedidos as PD
from nexus.dados import catalogo, explica

SEG = {"email": "seg@exemplo.test", "nome": "Ciclana da Segurança", "perfil": ""}


def _de(app, pessoa):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario=dict(pessoa))
    return c


def _dia(n):
    return (PD.hoje() + timedelta(days=n)).isoformat()


def test_pedir_e_responder(app, banco, limpo):
    """Um pedido por área, com o prazo; o duplo clique não grava outro; só a área responde por ela; o texto e o nome só
    cifrados; o prazo é obrigatório, de hoje a um ano."""
    feito = PD.pedir("insight:R07:1", ["hseq", "campo"], _dia(2), PESSOA, "Trocar até sexta")
    assert [l["torre"] for l in feito] == ["hseq", "campo"] and len({l["pedido_id"] for l in feito}) == 2
    assert PD.pedir("insight:R07:1", ["hseq"], _dia(5), PESSOA) == []                 # já tem pedido aberto
    linhas = banco.linhas(PD.LIVRO, PD.ABA)
    assert [(l["evento"], l["torre"], l["prazo"]) for l in linhas] == [("pediu", "hseq", _dia(2)),
                                                                      ("pediu", "campo", _dia(2))]
    assert "Trocar" not in str(linhas) and "Fulana" not in str(linhas)
    hseq = feito[0]["pedido_id"]
    PD.responder(hseq, "andamento", SEG, "Recarga marcada", {"hseq"})
    assert PD.responder(hseq, "andamento", SEG, "Recarga marcada", {"hseq"}) == {}    # o mesmo retorno: não grava
    with pytest.raises(PD.Recusada):
        PD.responder(feito[1]["pedido_id"], "resolvido", SEG, "", {"hseq"})           # a área de outro setor
    p = PD.atual()[hseq]
    assert (p["status"], p["retorno"], p["retorno_por"], p["mensagem"], p["situacao"]) == (
        "andamento", "Recarga marcada", "Ciclana da Segurança", "Trocar até sexta", "no_prazo")
    assert p["primeira_resposta_em"] is not None and p["resolvido_em"] is None
    for ruim in (("insight:R07:1", ["hseq"], ""), ("insight:R07:1", ["hseq"], _dia(-1)),
                 ("insight:R07:1", ["hseq"], _dia(400)), ("os:12a", ["pcm"], _dia(1)), ("os:15000", [], _dia(1))):
        with pytest.raises(PD.Recusada):
            PD.pedir(ruim[0], ruim[1], ruim[2], PESSOA)
    # resolvido, a área pode receber outro pedido sobre o mesmo objeto
    PD.responder(hseq, "resolvido", SEG, "Feito", {"hseq"})
    assert [l["torre"] for l in PD.pedir("insight:R07:1", ["hseq"], _dia(1), PESSOA)] == ["hseq"]


def _l(i, pid, ev, quando, prazo="2026-11-05", st=None, torre="pcm", ob=("os", "15000")):
    return {"id": f"e{i:011d}", "registrado_em": quando + "Z", "pedido_id": pid, "objeto_tipo": ob[0],
            "objeto_id": ob[1], "evento": ev, "torre": torre, "status_retorno": st, "prazo": prazo}


def test_prazo_e_tempo_de_resposta():
    """Atrasado = aberto depois do dia do prazo; vence hoje; no prazo = resolvido até o fim do dia do prazo (Brasília);
    o painel tem a mediana das horas até a 1ª resposta e até resolver, a área mais atrasada primeiro."""
    a, b, c, d = "p" + "a" * 11, "p" + "b" * 11, "p" + "c" * 11, "p" + "d" * 11
    linhas = [
        _l(1, a, "pediu", "2026-11-01T12:00:00.000"),                                  # pcm, prazo 05/11, sem resposta
        _l(2, b, "pediu", "2026-11-01T12:00:00.000", prazo="2026-11-06"),
        _l(3, b, "respondeu", "2026-11-01T14:00:00.000", st="recebido"),               # 2 h até a 1ª resposta
        _l(4, b, "respondeu", "2026-11-02T12:00:00.000", st="resolvido"),              # 24 h até resolver, no prazo
        _l(5, c, "pediu", "2026-11-01T12:00:00.000", prazo="2026-11-02", torre="hseq"),
        _l(6, c, "respondeu", "2026-11-04T12:00:00.000", st="resolvido", torre="hseq"),  # resolvido depois do prazo
        _l(7, d, "pediu", "2026-11-01T12:00:00.000", prazo="2026-11-07", torre="hseq"),
        _l(8, d, "respondeu", "2026-11-01T13:00:00.000", st="resolvido", torre="pcm"),   # outra área: fica fora
        _l(9, "lixo", "pediu", "2026-11-01T12:00:00.000"),
    ]
    peds = PD.pedidos(linhas, dia=datetime(2026, 11, 7).date())
    assert set(peds) == {a, b, c, d}
    assert (peds[a]["situacao"], peds[a]["sit_rotulo"]) == ("atrasado", "Atrasado 2 dias")
    assert (peds[b]["situacao"], peds[c]["situacao"], peds[d]["situacao"]) == ("resolvido", "resolvido_fora", "hoje")
    assert PD.pedidos(linhas, dia=datetime(2026, 11, 5).date())[a]["sit_rotulo"] == "Vence hoje"
    assert [p["id"] for p in sorted(peds.values(), key=PD.ordem)][:2] == [a, d]       # o atrasado, depois o de hoje
    pcm, hseq = PD.painel(peds)
    assert (pcm["torre"], pcm["atrasados"], pcm["abertos"], pcm["resolvidos"], pcm["pct_no_prazo"]) == ("pcm", 1, 1, 1, 100)
    assert (pcm["h_resposta"], pcm["h_resolver"]) == (2, 24)
    assert (hseq["sem_resposta"], hseq["pct_no_prazo"], hseq["h_resolver"]) == (1, 0, 72)
    assert [PD.duracao(h) for h in (0.25, 2, 24, 72, None)] == ["15 min", "2,0 h", "24 h", "3,0 dias", "sem dado"]


def test_o_pedido_no_insight_a_caixa_o_sino_e_o_painel(app, banco, limpo, motor_dublado, monkeypatch):
    c = _cliente(app)
    html = _aberta(c, "/t/comando/insights")
    # a área de costume da regra já vem marcada; o prazo é obrigatório
    assert "Pedir retorno a uma área" in html and 'type="date" name="prazo"' in html and "required" in html
    assert 'value="hseq" checked' in html and 'value="campo" checked' in html
    r = c.post("/t/comando/pedido/acao", data={"codigo": _codigo(c), "objeto": "insight:R07:1", "acao": "pedir",
                                               "para": ["hseq", "campo"], "prazo": _dia(3), "nota": "Antes da auditoria",
                                               "voltar": "/t/comando/insights"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/insights#ins-R07-1")
    assert [l["torre"] for l in banco.linhas(PD.LIVRO, PD.ABA)] == ["hseq", "campo"]
    html = _aberta(c, "/t/comando/insights")
    prazo = (PD.hoje() + timedelta(days=3)).strftime("%d/%m")
    assert f"Pedido enviado a Segurança · HSEQ, Campo · App, com prazo até {prazo}." in html
    assert "Aguardando retorno" in html and f"Vence {prazo}" in html
    # sem o prazo, nada é gravado
    c.post("/t/comando/pedido/acao", data={"codigo": _codigo(c), "objeto": "insight:R07:1", "acao": "pedir",
                                           "para": ["pcm"], "voltar": "/t/comando/insights"})
    assert "Escolha o prazo do pedido. Nada foi gravado." in c.get("/t/comando/insights").get_data(as_text=True)
    assert len(banco.linhas(PD.LIVRO, PD.ABA)) == 2
    # a Segurança vê o pedido na Caixa e no sino, abre a página do insight e responde só pela área dela
    monkeypatch.setattr(MO, "torres_da_pessoa", lambda: {"hseq"})
    seg = _de(app, SEG)
    caixa = seg.get("/t/comando/caixa-de-entrada").get_data(as_text=True)
    secao = caixa.split("Pedidos para o seu setor", 1)[1].split("</ol>", 1)[0]
    assert "2 extintores vencidos" in secao and "Para Segurança · HSEQ" in secao and "Campo · App" not in secao
    assert "/t/comando/conversa/insight/R07:1#ped-insight-R07-1" in secao
    sino = caixa.split('class="sino-topo"', 1)[1].split("</details>", 1)[0]
    assert "1 pedido para o seu setor" in sino and "/t/comando/conversa/insight/R07:1" in sino
    pag = seg.get("/t/comando/conversa/insight/R07:1").get_data(as_text=True)
    assert "Responder por Segurança · HSEQ" in pag and "Responder por Campo · App" not in pag
    pid = next(l["pedido_id"] for l in banco.linhas(PD.LIVRO, PD.ABA) if l["torre"] == "hseq")
    seg.post("/t/comando/pedido/acao", data={"codigo": _codigo(seg, "/t/comando/caixa-de-entrada"),
                                             "objeto": "insight:R07:1", "acao": "responder", "pedido": pid,
                                             "status": "resolvido", "nota": "Extintores trocados",
                                             "voltar": "/t/comando/conversa/insight/R07:1"})
    assert [l["status_retorno"] for l in banco.linhas(PD.LIVRO, PD.ABA)] == [None, None, "resolvido"]
    # quem pediu vê o retorno; o painel mede a Segurança no prazo e o Campo sem resposta
    monkeypatch.setattr(MO, "torres_da_pessoa", lambda: None)
    assert "Extintores trocados" in _aberta(c, "/t/comando/insights")
    caixa = c.get("/t/comando/caixa-de-entrada").get_data(as_text=True)
    assert "Pedidos que você fez" in caixa and "Para Campo · App" in caixa
    painel = c.get("/t/comando/tempo-de-resposta").get_data(as_text=True)
    assert "Tempo de resposta" in painel and "Segurança · HSEQ" in painel and "Campo · App" in painel
    assert "<b>100%</b>" in painel and "1 de 1 resolvido" in painel and "Atrasados agora" in painel


def test_o_pedido_sobre_uma_os(app, banco, limpo, motor_dublado):
    """Sem insight: na página da OS, pedir ao PCM; a página mostra o pedido e a conversa."""
    c = _cliente(app)
    pag = c.get("/t/comando/conversa/os/15000").get_data(as_text=True)
    assert "Pedidos às áreas" in pag and "Nenhuma área foi chamada ainda." in pag and "Pedir retorno a uma área" in pag
    c.post("/t/comando/pedido/acao", data={"codigo": _codigo(c, "/t/comando/conversa/os/15000"), "objeto": "os:15000",
                                           "acao": "pedir", "para": ["pcm", "comando"], "prazo": _dia(0),
                                           "voltar": "/t/comando/conversa/os/15000"})
    assert [(l["objeto_tipo"], l["objeto_id"], l["torre"]) for l in banco.linhas(PD.LIVRO, PD.ABA)] == [
        ("os", "15000", "pcm")]                                       # o Comando não recebe pedido
    pag = c.get("/t/comando/conversa/os/15000").get_data(as_text=True)
    assert "Vence hoje" in pag and "Pedido por você" in pag


def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao():
    l = catalogo.LIVRO_POR_NOME[PD.LIVRO]
    assert l.abas == (PD.ABA,) and l.so_cresce == (PD.ABA,) and not l.no_banco
    f = catalogo.POR_ID["pedido_area"]
    assert f.livro == f"{PD.LIVRO} · {PD.ABA}" and f.chave[0] == PD.CAB[0] and "pessoa_hmac" in PD.CAB
    assert "pedido_area" in explica.RESUMO and "pedido_area" in explica.PARA_QUE
