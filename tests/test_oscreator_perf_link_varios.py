"""O link de criar OS de Performance com VÁRIOS inversores (16/11/2026, a Sala de controle da Plataforma de Performance).

Levi: "1 OS só para todos [...] E a data do evento foi quando aconteceu". A Sala marca os inversores e abre a tela de
criar OS com `ativo` e `obs` repetidos (na mesma ordem), `obs_os` (a observação da OS inteira) e `evento`. A tela marca
todos, e com mais de um o agrupar em UMA OS entra sozinho, como já era. O link antigo, de um ativo, segue igual.
Nenhum teste vai à rede; nomes e usinas são de mentira (repositório público).
"""
import datetime as dt
import sys
from pathlib import Path

from werkzeug.datastructures import MultiDict

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

from os_web import perf_web  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE, "os_web")


def test_o_link_antigo_de_um_ativo_segue_igual():
    s = perf_web.sugestao_do_link(MultiDict([("usina", "Usina Teste 1"), ("ativo", "Inversor 1.2"),
                                             ("obs", "String 4 com corrente nula"), ("os_pai", "123"), ("resp", "Pessoa")]))
    assert (s["usina"], s["ativo"], s["obs"], s["os_pai"], s["resp"]) == (
        "Usina Teste 1", "Inversor 1.2", "String 4 com corrente nula", "123", "Pessoa")
    assert s["lista"] == [{"ativo": "Inversor 1.2", "obs": "String 4 com corrente nula"}]
    assert s["obs_os"] == "" and s["evento"] == ""


def test_varios_ativos_cada_um_com_a_sua_observacao_na_ordem():
    s = perf_web.sugestao_do_link(MultiDict([("usina", "Usina Teste 1"), ("ativo", "Inversor 1.2"), ("obs", "a"),
                                             ("ativo", "Inversor  1.4"), ("obs", "b"), ("ativo", "Inversor 2.1"),
                                             ("obs_os", "Usina Teste 1. Texto da OS inteira."), ("evento", "2026-11-03T08:00")]))
    assert s["lista"] == [{"ativo": "Inversor 1.2", "obs": "a"}, {"ativo": "Inversor 1.4", "obs": "b"},
                          {"ativo": "Inversor 2.1", "obs": ""}]
    assert s["obs_os"] == "Usina Teste 1. Texto da OS inteira."
    assert s["evento"] == "2026-11-03T08:00"


def test_evento_fora_do_formato_ou_no_futuro_nao_entra():
    futuro = (dt.datetime.now(perf_web.BRT) + dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    for ruim in ("ontem", "2026-11-03", "03/11/2026 08:00", futuro, "2026-11-03T08:00<script>"[:40]):
        s = perf_web.sugestao_do_link(MultiDict([("ativo", "Inversor 1.2"), ("evento", ruim)]))
        assert s["evento"] in ("", "2026-11-03T08:00"), ruim       # o corte em 16 caracteres deixa só a data e a hora
    assert perf_web.sugestao_do_link(MultiDict([("evento", futuro)]))["evento"] == ""


def test_a_lista_tem_teto():
    s = perf_web.sugestao_do_link(MultiDict([("ativo", f"Inversor 1.{i}") for i in range(90)]))
    assert len(s["lista"]) == perf_web.SUGESTAO_ATIVOS_MAX


def test_a_tela_recebe_a_lista_e_marca_todos():
    html = (WEB / "templates" / "perf_criar.html").read_text(encoding="utf-8")
    js = (WEB / "static" / "perf.js").read_text(encoding="utf-8")
    rotas = (WEB / "rotas.py").read_text(encoding="utf-8")
    assert "sugestao=perf_web.sugestao_do_link(request.args)" in rotas
    assert 'data-sug-lista="{{ sugestao.lista | tojson | forceescape }}"' in html
    assert 'data-sug-obsos="{{ sugestao.obs_os }}"' in html and 'data-sug-evento="{{ sugestao.evento }}"' in html
    assert "sugLista.forEach(s => {" in js and "checked.add(al.id)" in js
    assert "$('ed_obs_os').value = sugObsOs" in js           # a observação da OS inteira, só com mais de um ativo
    assert "$('dt_prog').value = root.dataset.sugEvento" in js
