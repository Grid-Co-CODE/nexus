"""Limitações de potência dos inversores, em Usinas 360° (19/11/2026).

Levi, 19/11/2026: "crie, na parte de usina 360, um campo onde as pessoas consigam colocar limitações de potência dos
inversores. E aí vai ser usado também para o cálculo dos expurgos. Aí aquela limitação de potência pode ser de todos os
inversores ou só de alguns, de acordo com os inversores do fractal". O cadastro tem os campos da aba "Inv. com lim. de
potência" da planilha de tickets, que o time usa hoje. Tudo inventado; o banco é o de mentira dos testes do Campo."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from nexus.cadastro.cifra import Cofre
from nexus.campo import limitacoes as L
from nexus.dados import catalogo

from test_campo_visao import CHAVE_CADASTRO, _aba, banco  # noqa: F401  (banco é fixture)

BRT = timezone(timedelta(hours=-3))
INV = ["THPN-ALT100-INVR1.1", "THPN-ALT100-INVR1.2", "THPN-ALT100-INVR1.3"]
CONTA = {"email": "analista.teste@exemplo.test", "nome": "Analista Teste"}
URL = "/t/campo/limitacoes"


@pytest.fixture
def com_inversores(banco):
    _aba(banco, "nexus_equipamentos", "dim_equipamento",
         [{"equipamento_id": 700 + k, "codigo": c, "descricao": f"Inversor 1.{k + 1}", "familia": "INVR", "usina_id": 1}
          for k, c in enumerate(INV)] +
         [{"equipamento_id": 800, "codigo": "THPN-ALT100-CABN1", "descricao": "Cabine 1", "familia": "CABN", "usina_id": 1}])
    from nexus.cadastro import estrutura_usina
    estrutura_usina._CACHE.pop("ativos", None)
    L.limpar()
    yield banco
    L.limpar()


def _dados(**kw):
    d = {"usina_id": "1", "inversores": INV[:2], "potencia_nominal_kw": "250", "limite_pct": "90",
         "causa": "Vazamento no trafo da cabine 1", "responsabilidade": "nao", "clipagem": "problemas",
         "inicio": "2026-11-10T08:00", "fim": "", "comentario_cliente": "Limitação pedida pela distribuidora",
         "comentario_geral": "Aguardando a troca do trafo"}
    d.update(kw)
    return d


# ── o catálogo e o domínio ───────────────────────────────────────────────────────────────────────────────────────────
def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao_e_so_cresce():
    l = catalogo.LIVRO_POR_NOME[L.LIVRO]
    assert L.LIVRO == "nexus_limitacao_inversor" and l.abas == (L.ABA,) and l.so_cresce == (L.ABA,)
    assert catalogo.aba_segue_a_regra(L.ABA)
    assert any(f.livro == f"{L.LIVRO} · {L.ABA}" for f in catalogo.FATOS)


def test_salvar_grava_cifrado_com_os_inversores_e_o_periodo(app, com_inversores):
    with app.test_request_context():
        r = L.salvar(_dados(), CONTA)
        [x] = com_inversores.linhas(L.LIVRO, L.ABA)
        assert x["evento"] == "registrou" and x["usina_id"] == 1 and x["inversores"] == ";".join(INV[:2])
        assert (x["inversores_qtd"], x["potencia_nominal_kw"], x["limite_pct"]) == (2, 250.0, 90.0)
        assert (x["data_id_inicio"], x["data_id_fim"], x["responsabilidade_grid"], x["clipagem"]) == (20261110, None, "nao", "problemas")
        bruto = json.dumps(x, ensure_ascii=False)
        assert "trafo" not in bruto and "Analista" not in bruto and "analista.teste" not in bruto     # nada em claro
        d = json.loads(Cofre(CHAVE_CADASTRO).decifrar(x["dados_cifrados"], f"banco/limitacoes/{x['versao_id']}"))
        assert d["causa"].startswith("Vazamento") and d["nome"] == "Analista Teste"
        [v] = L.vigentes()
        assert v["limitacao_id"] == r["limitacao_id"] and v["situacao"] == "em_andamento" and v["causa"].startswith("Vazamento")
        assert v["inversores"] == INV[:2] and v["todos"] is False and v["kw_limitados"] == 50.0      # 2 × 250 × 10%


def test_todos_os_inversores_guarda_a_marca_e_quantos_eram(app, com_inversores):
    with app.test_request_context():
        L.salvar(_dados(inversores=[], todos="1"), CONTA)
        [x] = com_inversores.linhas(L.LIVRO, L.ABA)
        assert (x["inversores"], x["inversores_qtd"]) == ("*", 3)
        [v] = L.vigentes()
        assert v["todos"] is True and v["kw_limitados"] == 75.0


@pytest.mark.parametrize("mudanca, motivo", [
    ({"inicio": ""}, "início"),
    ({"fim": "2026-11-09T08:00"}, "fim"),
    ({"limite_pct": "0"}, "limite"), ({"limite_pct": "100"}, "limite"), ({"limite_pct": "abc"}, "limite"),
    ({"responsabilidade": ""}, "responsabilidade"),
    ({"inversores": []}, "inversor"),
    ({"inversores": ["THPN-OUTRA-INVR9"]}, "inversor"),
    ({"potencia_nominal_kw": "-5"}, "potência"),
    ({"usina_id": "999"}, "usina"),
])
def test_salvar_recusa_o_que_nao_fecha_sem_gravar_nada(app, com_inversores, mudanca, motivo):
    with app.test_request_context():
        with pytest.raises(L.Recusada) as e:
            L.salvar(_dados(**mudanca), CONTA)
        assert motivo in str(e.value).lower()
        assert com_inversores.linhas(L.LIVRO, L.ABA) == []


def test_sem_a_potencia_nominal_salva_e_avisa_que_nao_entra_no_expurgo(app, com_inversores):
    with app.test_request_context():
        L.salvar(_dados(potencia_nominal_kw=""), CONTA)
        [v] = L.vigentes()
        assert v["kw_limitados"] is None and "não entra no cálculo do expurgo" in v["aviso"]


def test_sem_login_com_email_nao_grava():
    with pytest.raises(L.Recusada):
        L.salvar(_dados(), {"nome": "Administrador"})


def test_editar_encerrar_e_excluir_fazem_versoes_e_vale_a_ultima(app, com_inversores):
    with app.test_request_context():
        lid = L.salvar(_dados(), CONTA)["limitacao_id"]
        L.salvar(_dados(limite_pct="80", limitacao_id=lid), CONTA)
        L.encerrar(lid, CONTA, quando=datetime(2026, 11, 15, 17, 0, tzinfo=BRT))
        [v] = L.vigentes()
        assert (v["limite_pct"], v["fim_txt"], v["situacao"]) == (80.0, "15/11/2026 17:00", "encerrada")
        assert [x["evento"] for x in com_inversores.linhas(L.LIVRO, L.ABA)] == ["registrou", "alterou", "encerrou"]
        L.excluir(lid, CONTA)
        assert L.vigentes() == [] and len(com_inversores.linhas(L.LIVRO, L.ABA)) == 4      # o histórico fica
        with pytest.raises(L.Recusada):
            L.excluir("nao-existe", CONTA)


def test_o_mesmo_envio_duas_vezes_nao_duplica(app, com_inversores):
    with app.test_request_context():
        d = _dados(novo_id="abc123def456")
        L.salvar(d, CONTA)
        L.salvar(d, CONTA)
        assert len(L.vigentes()) == 1 and len(com_inversores.linhas(L.LIVRO, L.ABA)) == 1


def test_no_periodo_devolve_o_que_vale_em_cada_usina(app, com_inversores):
    """O que o cálculo do expurgo vai ler: as limitações de uma usina que tocam o período."""
    with app.test_request_context():
        L.salvar(_dados(inicio="2026-10-20T08:00", fim="2026-10-25T18:00"), CONTA)
        L.salvar(_dados(inicio="2026-11-10T08:00"), CONTA)
        nov = L.no_periodo(1, datetime(2026, 11, 1, tzinfo=BRT), datetime(2026, 12, 1, tzinfo=BRT))
        out = L.no_periodo(1, datetime(2026, 10, 1, tzinfo=BRT), datetime(2026, 11, 1, tzinfo=BRT))
        assert [v["inicio_txt"][:5] for v in nov] == ["10/11"] and [v["inicio_txt"][:5] for v in out] == ["20/10"]
        assert L.no_periodo(2, datetime(2026, 11, 1, tzinfo=BRT), datetime(2026, 12, 1, tzinfo=BRT)) == []


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def _analista(cliente):
    from conftest import SENHA_TESTE
    cliente.post("/entrar", data={"senha": SENHA_TESTE})
    with cliente.session_transaction() as s:
        s["usuario"] = dict(CONTA, perfil="")
    return cliente


def test_a_tela_esta_em_usinas_360_logo_abaixo_de_usinas(app):
    from nexus.torres.campo import TORRE
    ids = [t.id for t in TORRE.telas]
    assert ids[ids.index("usinas") + 1] == "limitacoes" and TORRE.tela("limitacoes").nome == "Limitações de potência"


def test_a_tela_lista_e_o_formulario_traz_os_inversores_do_fracttal(cliente, app, com_inversores):
    c = _analista(cliente)
    html = c.get(URL + "?usina=1").get_data(as_text=True)
    assert "Limitações de potência" in html and 'class="gc-explica' in html
    assert all(f'value="{k}"' in html for k in INV) and "THPN-ALT100-CABN1" not in html          # só os inversores
    assert 'name="todos"' in html and 'name="responsabilidade"' in html and "Nenhuma limitação registrada" in html
    r = c.post(URL, data=dict(_dados(), acao="salvar"))
    assert r.status_code == 303
    html = c.get(URL).get_data(as_text=True)
    assert "Altair" in html and "Vazamento no trafo" in html and "90%" in html and "Em andamento" in html


def test_a_tela_recusa_com_o_motivo_e_guarda_o_que_foi_digitado(cliente, com_inversores):
    c = _analista(cliente)
    html = c.post(URL, data=dict(_dados(limite_pct="0"), acao="salvar")).get_data(as_text=True)
    assert "limite" in html.lower() and "Vazamento no trafo da cabine 1" in html


def test_pedido_de_outro_site_e_recusado(cliente, com_inversores):
    c = _analista(cliente)
    assert c.post(URL, data=dict(_dados(), acao="salvar"), headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert com_inversores.linhas(L.LIVRO, L.ABA) == []


def test_sem_login_com_email_a_tela_mostra_mas_nao_deixa_registrar(logado, com_inversores):
    html = logado.get(URL + "?usina=1").get_data(as_text=True)
    assert "Entre com o seu login" in html and "disabled" in html


def test_sem_banco_a_tela_abre_e_diz_o_que_faltou(logado):
    r = logado.get(URL)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Não li o cadastro" in html and "Nenhuma limitação registrada" in html
