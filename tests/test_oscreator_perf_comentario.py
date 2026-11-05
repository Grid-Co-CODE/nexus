"""O comentário automático da OS de Performance criada (03/11/2026, Levi: "quando eu crio uma OS de performance já vira um
comentário automático: '<Levi> criou uma OS de <String> para o <inversor X>' + 'Observação da OS'").

O OS Creator Web é quem sabe que a OS saiu e com que nº: a resposta do `/os/api/performance/criar` leva `comentario`
(`perf_web.criadas_para_comentario`: o nº, o ativo e a observação de cada OS que saiu), e a página (`perf.js`) manda isso
à Plataforma de Performance, que grava na conversa da usina, um comentário por nº (a regra e o texto são de lá:
`plataforma/comentarios.py` e `tests/test_comentarios.py` do PerformancePainel). Aqui: sucesso, falha (sem nº, nada) e a
agrupada (uma OS só). Nenhum teste vai à rede; nomes e usinas são de mentira (repositório público).
"""
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app, perf_web  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE, "os_web")
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira


def _item(i):
    return {"asset": {"id": i, "code": f"TST-INV1{i}", "label": f"Inversor 1.{i}", "tipo": "Inversor"},
            "plano_id_task": 900, "plano_id_item": 901, "linkar": True, "note": f"strings {i} sem corrente"}


def _corpo(n=2, agrupar=False, obs_os=""):
    return {"frase": "recomposicao de string", "base": "Recomposição de String", "modo": "geracao",
            "evento": "2026-11-03T08:00", "programada": "2026-11-03T08:10", "gerar_ticket": False,
            "responsavel": {"id_personnel": 501, "name": "Pessoa Teste"}, "agrupar": agrupar,
            "itens": [_item(i + 1) for i in range(n)], "os_pai_os": "", "obs_os": obs_os}


def test_cada_os_que_saiu_com_numero_vai_para_o_comentario():
    itens, _kw, erro = perf_web.montar_itens(_corpo(3))
    assert not erro
    res = [{"ok": True, "asset": "Inversor 1.1", "folio": 16100}, {"ok": False, "asset": "Inversor 1.2", "erro": "x"},
           {"ok": True, "asset": "Inversor 1.3", "folio": None}]
    c = perf_web.criadas_para_comentario(itens, res, _corpo(3), False)
    assert c["tipo"] and "String" in c["tipo"]
    assert c["criadas"] == [{"folio": "16100", "ativo": "Inversor 1.1", "observacao": "strings 1 sem corrente"}]
    # nenhuma saiu: nada a comentar
    assert perf_web.criadas_para_comentario(itens, [{"ok": False, "erro": "x"}] * 3, _corpo(3), False)["criadas"] == []
    assert perf_web.criadas_para_comentario(itens, None, _corpo(3), False)["criadas"] == []


def test_a_agrupada_e_um_comentario_so():
    corpo = _corpo(2, agrupar=True, obs_os="Equipe vai na quarta")
    itens, _kw, _e = perf_web.montar_itens(corpo)
    c = perf_web.criadas_para_comentario(itens, {"ok": True, "folio": "16001", "n_criadas": 2}, corpo, True)
    assert c["criadas"] == [{"folio": "16001", "ativo": "Inversor 1.1, Inversor 1.2", "observacao": "Equipe vai na quarta"}]
    # as tarefas sem a OS numerada, ou a criação que falhou: sem nº, sem comentário
    assert perf_web.criadas_para_comentario(itens, {"ok": True, "folio": None}, corpo, True)["criadas"] == []
    assert perf_web.criadas_para_comentario(itens, {"ok": False, "erro": "x"}, corpo, True)["criadas"] == []


@pytest.fixture
def cli(monkeypatch):
    import requests

    def sem_rede(*a, **k):
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [])
    monkeypatch.setattr(perf_web, "SUBTAREFAS_PADRAO", None)       # o gancho do Nexus que outro teste ligou não vale aqui
    monkeypatch.setattr(api, "create_performance_os", lambda itens, **kw: [
        {"ok": i != 1, "asset": it["asset"]["label"], **({"folio": str(16100 + i)} if i != 1 else {"erro": "falhou"})}
        for i, it in enumerate(itens)])
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    return c


def test_a_resposta_da_criacao_leva_o_comentario(cli):
    j = cli.post("/os/api/performance/criar", json=_corpo(3)).get_json()
    assert j["ok"] == 2 and j["falhas"] == 1
    assert [c["folio"] for c in j["comentario"]["criadas"]] == ["16100", "16102"]       # a que falhou fica de fora
    assert [c["ativo"] for c in j["comentario"]["criadas"]] == ["Inversor 1.1", "Inversor 1.3"]


def test_a_pagina_manda_o_comentario_so_quando_a_os_saiu():
    js = (WEB / "static" / "perf.js").read_text(encoding="utf-8")
    assert "if (r.ok && j.ok) comentarNaPlataforma(j.comentario, cbUsi.value);" in js
    i = js.index("function comentarNaPlataforma(")
    corpo = js[i:i + 1400]
    assert "if (!c || !Array.isArray(c.criadas) || !c.criadas.length) return;" in corpo
    # URL completa (a camada do servidor punha o prefixo do Nexus em fetch começado por "/") e a chave do link
    assert "new URL('/api/state/comment/os', location.href)" in corpo and ".get('comentario')" in corpo
