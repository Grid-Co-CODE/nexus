"""O "Agrupar em UMA OS com várias tarefas" no Performance do OS Creator Web (Levi, 13/10/2026: "No OS Creator Web não
tem o mecanismo de quando é selecionado vários ativos, agrupar em uma só tarefa e vira uma atividade que nem no OS
Creator Desktop! Veja o OS Creator Desktop e replique para o web").

O app de mesa (steps/performance.py, `PerfCriar`) faz, e a web agora faz igual:
  - com 2+ ativos, a caixa liga sozinha enquanto a pessoa não mexer nela (`_auto_agrupar`); com 1, não há o que agrupar;
  - agrupado, o título de TODAS as tarefas é o nome digitado, sem o prefixo [Ativo] (o Fracttal copia o título da 1ª
    tarefa para a OS), a OS pai é UMA para a OS inteira e a observação da OS vai à parte (`note_os`);
  - a criação é o `api.create_performance_os_agrupada`, e o resultado é UMA OS (ou as tarefas SEM número, dito alto).
O comportamento da tela (a caixa ligando sozinha, a pessoa desmarcando e a tela respeitando) foi conferido num Chrome sem
janela com o Fracttal dublado, fora da suíte. Nenhum teste vai à rede; nomes e usinas são de mentira (repositório público).
"""
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar as telas
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app, perf_web  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE, "os_web")
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
USINA = "Cliente X - Usina Exemplo - UF"


def _item(i, **kw):
    return {"asset": {"id": i, "code": f"TST-INV1{i}", "label": f"Inversor 1.{i}", "tipo": "Inversor", "usina": USINA},
            "plano_id_task": 900, "plano_id_item": 901, "linkar": True, "note": f"obs {i}", "os_pai": kw.get("os_pai", "")}


def _corpo(n=2, agrupar=True, **kw):
    return {"frase": "inspecao geral do inversor", "base": "Inspeção Geral do Inversor", "modo": "geracao",
            "evento": "2026-10-13T08:00", "programada": "2026-10-13T08:10", "gerar_ticket": False,
            "responsavel": {"id_personnel": 501, "name": "Pessoa Teste"}, "agrupar": agrupar,
            "itens": [_item(i + 1, os_pai=kw.get("os_pai_item", "")) for i in range(n)],
            "os_pai_os": kw.get("os_pai_os", ""), "obs_os": kw.get("obs_os", "")}


def test_agrupado_o_titulo_e_a_os_pai_sao_unicos():
    corpo = _corpo(3, os_pai_os="15000", os_pai_item="999", obs_os="Equipe vai na quarta")
    itens, kwargs, erro = perf_web.montar_itens(corpo)
    assert not erro and perf_web.quer_agrupar(corpo)
    assert [it["titulo"] for it in itens] == ["Inspeção Geral do Inversor"] * 3        # sem o prefixo [Ativo]
    assert [it["os_pai"] for it in itens] == ["15000"] * 3                               # a da linha não vai
    assert [it["note"] for it in itens] == ["obs 1", "obs 2", "obs 3"]                    # a de cada tarefa continua
    assert "note_os" not in kwargs and perf_web.obs_da_os(corpo) == "Equipe vai na quarta"


def test_sem_agrupar_ou_com_um_ativo_e_uma_os_por_ativo():
    itens, _kw, _e = perf_web.montar_itens(_corpo(2, agrupar=False, os_pai_item="999"))
    assert [it["titulo"] for it in itens] == ["", ""] and [it["os_pai"] for it in itens] == ["999", "999"]
    um = _corpo(1, os_pai_os="15000", os_pai_item="999")
    assert not perf_web.quer_agrupar(um)                                  # com 1 ativo não há o que agrupar
    itens, _kw, _e = perf_web.montar_itens(um)
    assert itens[0]["titulo"] == "" and itens[0]["os_pai"] == "999"


def test_a_mensagem_da_agrupada():
    m = perf_web.mensagem_agrupada({"ok": True, "folio": "16001", "n_criadas": 3, "n_img_ok": 2, "erros": [], "img_erro": [],
                                    "tickets": [], "aviso": None})
    assert m["mensagem"].startswith("OS 16001 criada com 3 tarefa(s).") and "2 imagem(ns)" in m["mensagem"]
    assert m["ok"] == 3 and m["folios"] == ["16001"] and not m["alerta"]
    # as tarefas existem e a OS numerada não saiu: dito alto, e a tela limpa (senão a pessoa cria tudo de novo)
    m = perf_web.mensagem_agrupada({"ok": True, "folio": None, "n_criadas": 2, "erros": ["TST-INV13: falhou"],
                                    "aviso": "não consegui juntá-las numa OS"})
    assert "SEM número de OS" in m["mensagem"] and m["ok"] == 2 and m["alerta"] and m["detalhes"] == ["TST-INV13: falhou"]
    m = perf_web.mensagem_agrupada({"ok": False, "erro": "Nenhuma tarefa criada: x"})
    assert m["ok"] == 0 and m["mensagem"] == "Nenhuma tarefa criada: x"


@pytest.fixture
def cli(monkeypatch):
    import requests

    def sem_rede(*a, **k):                    # a cota do Fracttal é da empresa: aqui nada sai da máquina
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [])
    chamadas = []
    monkeypatch.setattr(api, "create_performance_os_agrupada", lambda itens, **kw: chamadas.append(("agrupada", itens, kw)) or {
        "ok": True, "folio": "16001", "n_criadas": len(itens), "erros": [], "img_erro": [], "tickets": []})
    monkeypatch.setattr(api, "create_performance_os", lambda itens, **kw: chamadas.append(("separadas", itens, kw)) or [
        {"ok": True, "asset": it["asset"]["code"], "folio": str(16100 + i)} for i, it in enumerate(itens)])
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    c.chamadas = chamadas
    return c


def test_criar_agrupado_chama_a_agrupada_com_a_observacao_da_os(cli):
    r = cli.post("/os/api/performance/criar", json=_corpo(2, os_pai_os="15000", obs_os="Levar escada"))
    j = r.get_json()
    assert r.status_code == 200 and j["mensagem"] == "OS 16001 criada com 2 tarefa(s)." and j["folios"] == ["16001"]
    (qual, itens, kw), = cli.chamadas
    assert qual == "agrupada" and kw["note_os"] == "Levar escada" and kw["responsible_name"] == "Pessoa Teste"
    assert [it["titulo"] for it in itens] == ["Inspeção Geral do Inversor"] * 2 and [it["os_pai"] for it in itens] == ["15000"] * 2


def test_criar_sem_agrupar_continua_uma_os_por_ativo(cli):
    j = cli.post("/os/api/performance/criar", json=_corpo(2, agrupar=False)).get_json()
    assert j["ok"] == 2 and "2 OS criada(s)" in j["mensagem"]
    assert [c[0] for c in cli.chamadas] == ["separadas"] and "note_os" not in cli.chamadas[0][2]


def test_a_tela_tem_a_caixa_e_os_campos_da_os_inteira():
    html = (WEB / "templates" / "perf_criar.html").read_text(encoding="utf-8")
    assert 'id="ck_agrupar"' in html and "Agrupar em UMA OS com várias tarefas" in html
    assert 'id="w_agrupada" hidden' in html and 'id="ed_pai_os"' in html and 'id="ed_obs_os"' in html
    js = (WEB / "static" / "perf.js").read_text(encoding="utf-8")
    # a caixa liga sozinha só enquanto a pessoa não clicou nela; o envio leva o modo e os campos da OS inteira
    assert "agrupTocado = true" in js and "!agrupTocado" in js
    assert "agrupar: ag" in js and "os_pai_os:" in js and "obs_os:" in js
    css = (WEB / "static" / "os.css").read_text(encoding="utf-8")
    assert ".os-pagina.agrupada .os-tbl .c-pai" in css
