"""A fonte das telas da torre Campo · App no banco do Nexus: as linhas que o coletor grava na API do PG, entregues às
regras copiadas do App no formato das tabelas dele (qualidadelog, e o par rondaos/rondas da fila de verificação).
"""
import json

import pytest
import requests
from flask import Flask
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo import banco_campo, fonte_pg, regras_app, tabelas
from nexus.campo.coletor import contexto_do_tecnico

CHAVE = gerar_chave()
BASE = "http://pg.falso"


def _linha(id_t, folio, **kw):
    l = {"id_tarefa": id_t, "os": str(folio), "id_os": int(folio) * 10, "tarefa": f"Tarefa {id_t}", "tecnico_id": 7,
         "tecnico_cifrado": Cofre(CHAVE).cifrar("Técnico Um", contexto_do_tecnico(id_t)), "equipe": "SP 01",
         "regiao": "SP Interior", "ativo": "Usina A > Inversor 1", "codigo": "USA-INV1", "tipo": "Preventiva",
         "crit": "Alta", "status_os": 2, "status_tarefa": 3, "inicio": "2026-10-03T13:00:00",
         "fim": "2026-10-03T14:00:00", "verificacao": "2026-10-03T14:00:00", "aprovacao": None, "dur_prev_min": 30,
         "dur_real_min": 45, "rating": 4, "pelo_app": True, "ronda": False, "ronda_dia": None, "ronda_usina": None,
         "nota": 72, "nota_itens": "[]", "nota_placar": 100, "pontos_placar": 40, "n_fotos": 1, "n_desc": 1,
         "gps_fotos": True, "sub_ok": True, "todas_sub": True, "obs_ok": False, "devolvida": False,
         "lido_em": "2026-10-04T20:00:00", "regua": regras_app.CODIGO_APP}
    l.update(kw)
    return l


@pytest.fixture
def banco(tmp_path):
    api = ApiPGFalsa()
    linhas = [_linha(501, 15377),
              _linha(502, 15378, status_os=3, aprovacao="2026-10-04T11:00:00", devolvida=True),
              _linha(601, 15380, pelo_app=False, nota=None),
              _linha(701, 15390, ronda=True, ronda_dia="2026-10-03", ronda_usina="Usina B", nota=87)]
    banco_campo.gravar(linhas, banco_campo.resumo(linhas, "x", completa=True), base=BASE, token="t", sessao=api)
    ident = tmp_path / "identidades.json"
    ident.write_text(json.dumps({"porEmail": {"tec1@gridco.com.br": {"nome": "Técnico Um", "supervisor": "Sup A"}}}),
                     encoding="utf-8")
    app = Flask(__name__)
    app.config.update(TESTING=True, NEXUS_CAMPO_IDENTIDADES=str(ident))
    f = fonte_pg.Fornecedor({"GRIDCO_DB_API": BASE, "NEXUS_CHAVE_CADASTRO": CHAVE}, sessao=api)
    tabelas.usar_fornecedor(f)
    with app.app_context():
        yield f, api
    tabelas.usar_fornecedor(None)


def test_registro_no_formato_do_app(banco):
    reg = {e["os"]: e for e in tabelas.tabela("qualidadelog").query_entities("PartitionKey eq 'q'")}
    e = reg["15377"]
    assert e["qualidade"] == 72 and e["fx_dur_prev_min"] == 30 and e["fx_dur_real_min"] == 45 and e["fx_status"] == 2
    assert e["server_ts"] == "2026-10-03T14:00:00.000Z" and e["assinou"] and e["geo_ok"] and e["rev"] == ""
    assert e["nome"] == "Técnico Um" and e["email"] == "tec1@gridco.com.br"      # pelo cadastro do App, na hora
    assert reg["15378"]["rev"] == "aprovada" and reg["15378"]["foi_devolvida"]
    assert "pontual" not in e                     # o Fracttal não tem a hora de início no celular


def test_fora_do_app_e_ronda_nao_entram_no_registro(banco):
    assert {e["os"] for e in tabelas.tabela("qualidadelog").list_entities()} == {"15377", "15378"}


def test_ronda_liga_a_os_a_nota_da_ronda_na_fila(banco):
    r = regras_app._rondas_os_por_folio("2026-09-01")
    assert r["15390"]["ronda"] and r["15390"]["qualidade"] == 87 and r["15390"]["usina"] == "Usina B"
    # sem `finalizada`: a Triagem não conta esta ronda
    assert not any(e.get("finalizada") for e in tabelas.tabela("rondas").list_entities())


def test_so_liga_a_tela_que_tem_dado(banco):
    assert tabelas.configurado(("qualidadelog",))
    assert not tabelas.configurado(("rondas",))                 # Atenção e PT continuam no painel do App
    assert not tabelas.configurado(("qualidadelog", ("fracttaltokens", "cadastro")))


def test_banco_vazio_deixa_a_tela_no_app():
    tabelas.usar_fornecedor(fonte_pg.Fornecedor({"GRIDCO_DB_API": BASE}, sessao=ApiPGFalsa()))
    try:
        assert not tabelas.configurado(("qualidadelog",))
    finally:
        tabelas.usar_fornecedor(None)


class _ForaDoAr:
    def get(self, *a, **k):
        raise requests.ConnectionError("sem rota")


def test_banco_fora_do_ar_deixa_a_tela_no_app_e_anota():
    tabelas.usar_fornecedor(fonte_pg.Fornecedor({"GRIDCO_DB_API": BASE}, sessao=_ForaDoAr()))
    try:
        assert not tabelas.configurado(("qualidadelog",))
        tabelas.comecar_leitura()
        with pytest.raises(requests.ConnectionError):
            tabelas.tabela("qualidadelog").query_entities("PartitionKey eq 'q'")
        assert tabelas.erros_da_leitura() == ["qualidadelog (ConnectionError)"]
    finally:
        tabelas.usar_fornecedor(None)


def test_nao_grava_nas_tabelas_do_app(banco):
    with pytest.raises(PermissionError):
        tabelas.tabela("qualidadelog").upsert_entity({"PartitionKey": "q", "RowKey": "x"})


def test_le_o_banco_uma_vez_a_cada_5_min(banco):
    f, api = banco
    f.limpar()
    antes = len(api.tokens)
    lidas = [0]
    get = api.get

    def contar(url, **kw):
        if url.endswith("/api/sheets"):
            lidas[0] += 1
        return get(url, **kw)
    api.get = contar
    tabelas.tabela("qualidadelog").list_entities()
    tabelas.tabela("qualidadelog").list_entities()
    assert lidas[0] == 1 and len(api.tokens) == antes            # leitura não manda token


def test_sem_a_chave_o_nome_fica_em_branco(banco):
    f, api = banco
    tabelas.usar_fornecedor(fonte_pg.Fornecedor({"GRIDCO_DB_API": BASE}, sessao=api))
    e = tabelas.tabela("qualidadelog").query_entities("PartitionKey eq 'q'")[0]
    assert e["nome"] == "" and e["email"] == ""


def test_filtro_que_o_app_nao_mandava_e_recusado(banco):
    with pytest.raises(ValueError):
        tabelas.tabela("qualidadelog").query_entities("qualidade gt 3 or os eq '1'")


def test_coleta_pela_metade_deixa_a_tela_no_app():
    # 04/10: com 40 de ~2.900 OS calculadas, a Aprovação punha 2.846 tarefas em "fora do App"
    api = ApiPGFalsa()
    linhas = [_linha(501, 15377)]
    banco_campo.gravar(linhas, banco_campo.resumo(linhas, "x", completa=False, pendentes=2800), base=BASE, token="t",
                       sessao=api)
    tabelas.usar_fornecedor(fonte_pg.Fornecedor({"GRIDCO_DB_API": BASE}, sessao=api))
    try:
        assert not tabelas.configurado(("qualidadelog",))
    finally:
        tabelas.usar_fornecedor(None)
