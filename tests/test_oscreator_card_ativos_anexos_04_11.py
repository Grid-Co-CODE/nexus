"""O card da OS de vários ativos e o Histórico (Levi, 04/11/2026):
- "quero que os ativos fiquem mais organizados": na ordem natural (1.1, 1.2 ... 1.10, e não 1.1, 1.10, 1.2) e em etiquetas;
- "quero que dê para ver o anexo especificamente daquela tarefa e dê para baixar tudo de uma vez, o download sai com o nome
  do ativo!": cada anexo sabe a tarefa dele, o ativo mostra quantos tem e abre só os dele, e o .zip tem a pasta e o nome do
  ativo em cada arquivo;
- "no Histórico ... no ativo apareça 'VÁRIOS' ao invés de aparecer o 1° ativo".
O Fracttal é de mentira (o dos testes do card); nomes e códigos inventados."""
import re
from pathlib import Path
from types import SimpleNamespace

from test_oscreator_card_tarefas import WID, Fracttal, _blocos, _card, _item, _tarefa, api  # noqa: F401

import os_anexos  # noqa: E402 — o clone já está no sys.path (test_oscreator_card_tarefas)
from os_web import os_acoes_web as regra  # noqa: E402
from os_web import rotas  # noqa: E402

WEB = Path(api.__file__).parent / "os_web"


def _os(monkeypatch, tarefas, itens):
    monkeypatch.setattr(api, "_rpc_call", Fracttal(tarefas, itens).rpc)
    return _card()


def test_os_ativos_vem_na_ordem_natural_e_em_etiquetas(monkeypatch):
    ks = (1, 10, 2, 11, 3)                                       # a ordem em que o Fracttal devolve
    html = _os(monkeypatch, [_tarefa(k) for k in ks], [_item(k, n) for k in ks for n in (1, 2)])
    nomes = [re.search(r"<b>(Inversor 1\.\d+)", b).group(1) for _t, b in _blocos(html)]
    assert nomes == ["Inversor 1.1", "Inversor 1.2", "Inversor 1.3", "Inversor 1.10", "Inversor 1.11"]
    numeros = [re.search(r'det-tarefa-n">(\d+)<', b).group(1) for _t, b in _blocos(html)]
    assert numeros == ["1", "2", "3", "4", "5"]                  # o número da tarefa acompanha a ordem
    banner = html[html.index('class="det-card det-banner"'):html.index('class="det-cols"')]
    assert "Ativos (5)</span>" in banner and " · " not in banner
    assert [x.strip() for x in re.findall(r'class="det-ativo">([^<]+)<', banner)] == nomes   # etiquetas, na mesma ordem


def test_cada_ativo_tem_o_botao_dos_anexos_dele():
    html = (WEB / "templates" / "os_detalhe_conteudo.html").read_text(encoding="utf-8")
    js = (WEB / "static" / "os_acoes.js").read_text(encoding="utf-8")
    assert 'data-acao="anexos-tarefa" data-tarefa-id="{{ g.id }}"' in html and 'data-n-tarefa="{{ g.id }}"' in html
    assert 'data-ativo="{{ g.ativo }}"' in html
    assert "'anexos-tarefa'(d, b)" in js and "ativos: ativos || {}, tarefa: tarefa || ''" in js and "j.por_tarefa" in js


def test_cada_anexo_de_subtarefa_sabe_a_tarefa_dele(monkeypatch):
    itens = [{"num_attachments": 1, "id_work_order_task": 70011, "id_work_orders_tasks_form_items": 5,
              "description": "Coleta de dados de geração"}]
    monkeypatch.setattr(api, "_leitura_da_os", lambda *a, **k: itens)
    monkeypatch.setattr(api, "_rpc_call", lambda m, p, *a, **k: {"data": [{"type": 1, "value": "x/y/print.jpg"},
                                                                          {"type": 3, "value": "", "description": "ok"}]})
    monkeypatch.setattr(api, "s3_get_url", lambda v: None)
    out = os_anexos.get_os_subtarefa_anexos(WID)
    assert [a["id_tarefa"] for a in out] == [70011, 70011]
    assert {x["tarefa"] for x in regra.itens_subtarefas(out, WID)} == {"70011"}


def test_o_zip_tem_a_pasta_e_o_nome_do_ativo():
    itens = [{"nome": "print.jpg", "value": "x/a/print.jpg", "subtarefa": "Coleta", "tarefa": "11"},
             {"nome": "print.jpg", "value": "x/b/print.jpg", "subtarefa": "Coleta", "tarefa": "12"},
             {"nome": "nota", "descricao": "geração ok", "subtarefa": "Coleta", "tarefa": "11", "is_text": True}]
    ativos = {"11": "Inversor 1.1 Sungrow", "12": "Inversor 1.2 Sungrow"}
    assert [p["caminho"] for p in regra.plano_do_zip(itens, ativos)] == [
        "Inversor 1.1 Sungrow/Inversor 1.1 Sungrow - 01 - print.jpg",
        "Inversor 1.2 Sungrow/Inversor 1.2 Sungrow - 01 - print.jpg",
        "Inversor 1.1 Sungrow/Inversor 1.1 Sungrow - 02 - nota.txt"]
    assert [p["caminho"] for p in regra.plano_do_zip(itens)][:2] == ["Coleta/01 - print.jpg", "Coleta/02 - print.jpg"]
    assert regra.plano_do_zip(itens, {"11": "a/../b:c"})[0]["caminho"].startswith("a_.._b_c/")   # só nome de arquivo


def test_o_historico_diz_varios_na_os_de_mais_de_um_ativo():
    lista = SimpleNamespace(preparada=False, linhas=[
        {"ativo": "Inversor 1.1 Sungrow", "tipo": "Inversor", "codigos": ["TST-INV1.1", "TST-INV1.2"]},
        {"ativo": "Inversor 1.1 Sungrow", "tipo": "Inversor", "codigos": ["TST-INV1.1", "TST-INV1.1"]},
        {"ativo": "Tracker 2.1", "tipo": "Tracker", "codigos": []}])
    rotas.preparar_linhas(lista)
    assert [l["_ativo_curto"] for l in lista.linhas][0] == "Vários" and lista.linhas[0]["_n_ativos"] == 2
    assert lista.linhas[1]["_ativo_curto"] != "Vários" and lista.linhas[2]["_ativo_curto"] != "Vários"
    tpl = (WEB / "templates" / "_historico_linhas.html").read_text(encoding="utf-8")
    assert 'data-csv="Vários ({{ l._n_ativos }})">Vários</td>' in tpl
