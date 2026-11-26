# -*- coding: utf-8 -*-
"""Base › Metas e equipamentos (25/11/2026). Levi: "Expõe as 43 usinas de fora para o time de Performance!"; "na parte de
base [...] equipamento das usinas e metas. Eu gostaria que fossem um só, escrito metas e equipamentos. E a pessoa clica,
ela vai poder ver as metas das usinas, vai poder ver os equipamentos das usinas e vai poder fazer o de para ali [...] o que
a gente atualizar no de para vai atualizar na sala de controle. Essa é a regra."

Aqui se confere: um item só no menu (as Metas por dentro), as duas abas nas duas páginas, o setor Performance abrindo e
gravando (até ali, só administrador), outro setor de fora, e o Salvar de quem é da Performance passando a usina pronta a
valer pelo Nexus (a visão que a Sala de controle lê). Nomes de mentira (repositório público)."""
import pytest
from test_base_equipamentos_depara import (CH1, CH2, CH_USINA, ITAJA, _marca, _monta_itaja, _salvar_base,  # noqa: F401
                                           _sem_copias, app_dp, banco, cfg)

from nexus.cadastro import setor_ids as SID

PERF = {"email": "analista.perf@exemplo.com.br", "nome": "Analista Performance"}


def _como(app, setor_id, telas):
    """Um cliente logado sem ser administrador, do setor `setor_id`, com as `telas` liberadas."""
    from nexus.auth import setor_telas as ST
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, False, PERF
    return c, (lambda: {"tudo": False, "telas": set(telas), "setor": {"id": setor_id, "nome": "x"}, "erro": ""}), ST


def test_um_item_so_no_menu_com_as_metas_por_dentro_e_do_setor_performance(app_dp):
    from nexus.auth import setor_telas as ST
    from nexus.torres.base import TORRE
    eq, metas = TORRE.tela("equipamentos"), TORRE.tela("metas")
    assert eq.nome == "Metas e equipamentos" and not eq.dentro_de
    assert metas.dentro_de == "equipamentos"                                  # sai do menu, acende o item de cima
    with app_dp.test_request_context():
        assert {"base/equipamentos", "base/metas"} <= ST.das_do_setor({"id": SID.PERFORMANCE})
        assert "base/equipamentos" not in ST.das_do_setor({"id": SID.COS})


def test_as_duas_abas_nas_duas_paginas(app_dp):
    c = app_dp.test_client()
    from conftest import SENHA_TESTE
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    for url, atual in (("/t/base/equipamentos", "Equipamentos das usinas e de-para"), ("/t/base/metas", "Metas das usinas")):
        html = c.get(url).get_data(as_text=True)
        assert '<h1 class="titulo-pagina">Metas e equipamentos</h1>' in html, url
        assert 'href="/t/base/equipamentos"' in html and 'href="/t/base/metas"' in html
        assert f'aria-current="page">{atual}</a>' in html


def test_o_setor_performance_abre_e_o_salvar_dele_vale_na_sala(app_dp, cfg, banco, monkeypatch):
    """Quem é da Performance (sem ser administrador) abre a tela e grava; o Salvar da usina pronta passa as três chaves da
    Itajá a valer pelo Nexus, a visão que a Sala de controle lê (a regra: o que se atualiza no de-para vale na Sala)."""
    c, acesso, ST = _como(app_dp, SID.PERFORMANCE, {"base/equipamentos", "base/metas"})
    monkeypatch.setattr(ST, "acesso", acesso)
    html = c.get("/t/base/equipamentos").get_data(as_text=True)
    assert c.get("/t/base/equipamentos").status_code == 200 and "Metas e equipamentos" in html
    assert c.get("/t/base/metas").status_code == 200
    _monta_itaja(cfg, banco)
    assert _marca(banco) == {CH_USINA: 0, CH1: 0, CH2: 0}
    j = _salvar_base(c, cfg, banco, ITAJA)
    assert j["ok"] and "Vale pelo Nexus na Sala de controle" in j["aviso"], j
    assert _marca(banco) == {CH_USINA: 1, CH1: 1, CH2: 1}


def test_outro_setor_e_o_portao_desligado_nao_abrem(app_dp, monkeypatch):
    c, acesso, ST = _como(app_dp, SID.COS, {"cos/ocorrencias"})
    monkeypatch.setattr(ST, "acesso", acesso)
    assert c.get("/t/base/equipamentos").status_code == 403
    assert c.post("/t/base/equipamentos/salvar", json={}, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 403
    # o portão por setor desligado ("tudo", sem setor): quem não é administrador não abre
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": True, "telas": set(), "setor": None, "erro": ""})
    assert c.get("/t/base/equipamentos").status_code == 403
