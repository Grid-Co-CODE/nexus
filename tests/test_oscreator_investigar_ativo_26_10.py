"""O "Investigar ativo" do Tempo real (26/10/2026). Levi: "Gostaria de poder clicar com botão direito do mouse em cima do
inversor e ter a opção 'Investigar ativo'. Vai aproveitar o pré carregamento de histórico de OS do OS Creator filtrando
esse ativo, deve mostrar o período filtrado e eu devo conseguir fazer novos filtros e pesquisas pela visão."

A janela (`/os/historico/ativo`, `rotas_investigar.py`) lê a MESMA lista da Visão COS (a de "Todos", 30 dias,
`rotas.ler_lista`): aqui se conta cada ida ao Fracttal (de mentira) e se confere o ativo achado no catálogo do disco.
Nada sai da máquina."""
import datetime as dt
import sys

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app, rotas  # noqa: E402
from os_web import historico_store as HS  # noqa: E402
from os_web import investigar_web as IW  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
HOJE = dt.date.today()
CATALOGO = [
    {"id": 501, "code": "THPN-CGH100-INVR1.1", "description": "Inversor 1.1 { THPN-CGH100-INVR1.1 }",
     "cliente": "Thopen", "usina": "Thopen - Usina Teste - PA", "tipo_code": "INVR", "tipo": "Inversor"},
    {"id": 502, "code": "THPN-CGH100-INVR1.10", "description": "Inversor 1.10 { THPN-CGH100-INVR1.10 }",
     "cliente": "Thopen", "usina": "Thopen - Usina Teste - PA", "tipo_code": "INVR", "tipo": "Inversor"},
    {"id": 503, "code": "THPN-CGH100-INVR2.1", "description": "Inversor 2.1 { THPN-CGH100-INVR2.1 }",
     "cliente": "Thopen", "usina": "Thopen - Usina Teste - PA", "tipo_code": "INVR", "tipo": "Inversor"},
    {"id": 504, "code": "THPN-CGH100-CABN1", "description": "Cabine 1 { THPN-CGH100-CABN1 }",
     "cliente": "Thopen", "usina": "Thopen - Usina Teste - PA", "tipo_code": "CABN", "tipo": "Cabine"},
    {"id": 601, "code": "THPN-OUT100-INVR1.1", "description": "Inversor 1.1 { THPN-OUT100-INVR1.1 }",
     "cliente": "Thopen", "usina": "Thopen - Outra Usina - MG", "tipo_code": "INVR", "tipo": "Inversor"},
]


def _dia(dias_atras, hora="10:00:00"):
    return f"{(HOJE - dt.timedelta(days=dias_atras)).isoformat()}T{hora}"


def _os(i, data, codigos, usina="Usina Teste", status_id=1, tipo_tarefa="Corretiva", desc="OS de teste"):
    return {"id": i, "folio": str(20000 + i), "cliente": "Thopen", "usina": usina, "tipo": "Inversor",
            "ativo": "Inversor", "descricao": desc, "status_id": status_id, "status": api.WO_STATUS[status_id],
            "data": data, "tipo_tarefa": tipo_tarefa, "event_date": "", "data_fim": "", "note": "", "inicio": "",
            "gatilho": "", "etiquetas": [], "criado_por": "Alguém", "programada": "", "equipe": "",
            "codigos": list(codigos)}


class _Fracttal:
    def __init__(self, linhas):
        self.linhas, self.buscas, self.totais = list(linhas), [], []

    def list_minhas_os(self, **kw):
        self.buscas.append(kw)
        if isinstance(kw.get("info"), dict):
            kw["info"].update({"total": len(self.linhas), "cap": api.HISTORICO_CAP})
        de, ate = str(kw.get("de") or ""), str(kw.get("ate") or "9999")
        return [dict(x) for x in self.linhas if de[:10] <= x["data"][:10] <= ate]

    def pagina(self, *a, **k):
        self.totais.append(a)
        return {"total": len(self.linhas), "linhas": [], "tem_mais": False}


@pytest.fixture
def fr(monkeypatch):
    import requests

    def sem_rede(*a, **k):                    # a cota do Fracttal é da empresa: aqui nada sai da máquina
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    f = _Fracttal([
        _os(1, _dia(2), ["THPN-CGH100-INVR1.1"], tipo_tarefa="Religamento", desc="Religar o inversor"),
        _os(2, _dia(5), ["THPN-CGH100-INVR1.10"], desc="Outro inversor, mesmo começo de número"),
        _os(3, _dia(8), ["THPN-CGH100-INVR2.1", "THPN-CGH100-INVR1.1"], desc="OS agrupada de dois inversores"),
        _os(4, _dia(12), ["THPN-CGH100"], desc="A usina inteira", tipo_tarefa="Religamento"),
        _os(5, _dia(20), ["THPN-CGH100-INVR1.1"], status_id=3, tipo_tarefa="Preventiva", desc="Preventiva antiga"),
        _os(6, _dia(3), ["THPN-OUT100-INVR1.1"], usina="Outra Usina", desc="Mesmo número em outra usina"),
        _os(7, _dia(60), ["THPN-CGH100-INVR1.1"], desc="Fora dos 30 dias"),
    ])
    monkeypatch.setattr(api, "list_minhas_os", f.list_minhas_os)
    monkeypatch.setattr(api, "list_minhas_os_pagina", f.pagina)
    monkeypatch.setattr(api, "get_labels", lambda *a, **k: [])
    monkeypatch.setattr(api, "get_pessoas_contas", lambda *a, **k: {"pessoas": [], "eu": None})
    monkeypatch.setattr(api, "_code_to_loc", lambda *a, **k: {})
    monkeypatch.setattr(api, "_read_asset_cache", lambda *a, **k: [])
    monkeypatch.setattr(api, "_catalogo_cru", lambda: {"assets": [dict(a) for a in CATALOGO]})
    monkeypatch.setattr(rotas, "_em_segundo_plano", lambda fn: fn())
    relogio = {"t": 1000.0}
    monkeypatch.setattr(HS, "_relogio", lambda: relogio["t"])
    yield f
    HS.limpar()


def _cliente(email="pessoa1@exemplo.invalid"):
    c = criar_app(segredo="teste", testing=False).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": email, "perfil": "ADMINISTRATOR"}
    return c


def _inv(c, q="codigo=THPN-CGH100-INVR1.1&usina=Thopen%20-%20Usina%20Teste%20-%20PA&nome=Inversor%201.1"):
    r = c.get("/os/historico/ativo?" + q)
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _linha(html, folio):
    i = html.index(f">{folio}</a>")
    return html[html.rindex("<tr ", 0, i):i]


# ── o catálogo: o código manda; sem ele, o número do inversor na usina ─────────────────────────────────────────────────
def test_o_ativo_sai_do_catalogo_pelo_codigo_da_plataforma():
    a = IW.resolver(CATALOGO, "thpn-cgh100-invr1.1", "qualquer", "x")
    assert a["code"] == "THPN-CGH100-INVR1.1" and a["como"] == "codigo" and not a["aviso"]
    assert a["nome"] == "Inversor 1.1" and a["usina_curta"] == "Usina Teste" and a["cliente"] == "Thopen"


def test_o_codigo_derivado_que_nao_existe_cai_no_nome_e_avisa():
    """O derivado erra onde a árvore do Fracttal mudou (Pharma II: THPN-PHS200-INVR1.1 contra THPN-PHS100-INVR2.1): o código
    que não está no catálogo não vira "nenhuma OS"."""
    a = IW.resolver(CATALOGO, "THPN-CGH200-INVR1.1", "Thopen - Usina Teste - PA", "Inversor 01.01")
    assert a["code"] == "THPN-CGH100-INVR1.1" and a["como"] == "nome"
    assert "THPN-CGH200-INVR1.1 não está no catálogo" in a["aviso"]
    # o 1.1 não casa com o 1.10, e o nome curto da usina também serve
    assert IW.resolver(CATALOGO, "", "Usina Teste", "Inversor 1.10")["code"] == "THPN-CGH100-INVR1.10"


def test_sem_o_ativo_fica_a_usina_inteira_e_sem_usina_so_o_aviso():
    a = IW.resolver(CATALOGO, "", "Thopen - Usina Teste - PA", "Inversor 9.9")
    assert a["code"] == "" and a["usina_curta"] == "Usina Teste" and "usina inteira" in a["aviso"]
    b = IW.resolver(CATALOGO, "NADA-1", "Usina Que Nao Existe", "Inversor 1.1")
    assert b["code"] == "" and b["usina_curta"] == "" and "não achei a usina" in b["aviso"]
    assert IW.resolver([], "", "", "")["aviso"]


def test_numero_do_nome_e_do_codigo():
    assert IW.numero("Inversor 01.02") == "1.2" and IW.numero("Inversor 1.1 (UG 02)") == "1.1"
    assert IW.numero_do_codigo("THPN-CGH100-INVR1.10") == "1.10" and IW.numero_do_codigo("APG100-INVR3") == "3"


def test_os_codigos_de_cada_item_da_os():
    assert api._extrai_codigos("Inversor 1.1 { A-INVR1.1 }, Inversor 2.1 {A-INVR2.1}") == ["A-INVR1.1", "A-INVR2.1"]
    assert api._extrai_codigos("") == [] and api._extrai_codigos(None) == []
    linha = api._shape_wo_row({"id": 1, "items_log_descriptions": ["X { A-INVR1.1 }", "Y { A-INVR2.1 }"]})
    assert linha["codigos"] == ["A-INVR1.1", "A-INVR2.1"]


def test_periodo_e_janela_carregada():
    assert IW.periodo("", "", HOJE)[:2] == ((HOJE - dt.timedelta(days=30)).isoformat(), HOJE.isoformat())
    assert IW.periodo("2026-10-20", "2026-10-01", dt.date(2026, 10, 26))[:2] == ("2026-10-01", "2026-10-20")
    assert IW.periodo("2026-10-01", "2027-01-01", dt.date(2026, 10, 26))[1] == "2026-10-26"
    hoje = dt.date(2026, 10, 26)
    assert IW.janela_carregada("2026-10-10", "2026-10-20", hoje) == ("2026-09-26", "2026-10-26")
    assert IW.janela_carregada("2026-08-01", "2026-10-26", hoje) is None


# ── a janela: a lista da Visão COS, sem uma busca a mais ───────────────────────────────────────────────────────────────
def test_a_janela_usa_a_lista_que_a_visao_cos_ja_carregou(fr):
    c = _cliente()
    assert c.get("/os/historico?modo=cos").status_code == 200
    assert len(fr.buscas) == 1 and fr.buscas[0]["id_account"] == "TODOS"
    html = _inv(c)
    assert len(fr.buscas) == 1                         # nenhuma ida ao Fracttal: a lista é a mesma
    # as do ativo à vista; a da usina inteira e a do outro inversor, escondidas (o "A usina inteira" mostra)
    for f in ("20001", "20003", "20005"):
        assert 'data-ativo="1"' in _linha(html, f) and " hidden" not in _linha(html, f), f
    for f in ("20002", "20004"):
        assert 'data-ativo="0"' in _linha(html, f) and " hidden" in _linha(html, f), f
    assert "20006" not in html and "20007" not in html   # outra usina; fora dos 30 dias
    assert "Este ativo <b>3</b>" in html and "A usina inteira <b>5</b>" in html
    assert "THPN-CGH100-INVR1.1" in html and "pelo código da plataforma" in html


def test_a_primeira_janela_carrega_a_lista_que_a_visao_cos_vai_usar(fr):
    c = _cliente()
    _inv(c)
    assert len(fr.buscas) == 1
    c.get("/os/historico?modo=cos")
    assert len(fr.buscas) == 1


def test_o_periodo_dentro_dos_30_dias_recorta_sem_ir_ao_fracttal(fr):
    c = _cliente()
    _inv(c)
    de, ate = (HOJE - dt.timedelta(days=10)).isoformat(), HOJE.isoformat()
    html = _inv(c, f"codigo=THPN-CGH100-INVR1.1&usina=Usina%20Teste&nome=Inversor%201.1&de={de}&ate={ate}")
    assert len(fr.buscas) == 1
    assert "20001" in html and "20003" in html and "20005" not in html     # a de 20 dias saiu do recorte
    assert "Este ativo <b>2</b>" in html and f'value="{de}"' in html


def test_o_periodo_fora_dos_30_dias_le_a_lista_daquele_periodo(fr):
    c = _cliente()
    _inv(c)
    de = (HOJE - dt.timedelta(days=90)).isoformat()
    html = _inv(c, f"codigo=THPN-CGH100-INVR1.1&usina=Usina%20Teste&nome=Inversor%201.1&de={de}")
    assert len(fr.buscas) == 2 and fr.buscas[1]["de"] == de and fr.buscas[1]["id_account"] == "TODOS"
    assert "20007" in html and "sai dos 30 dias já carregados" in html


def test_a_janela_guarda_o_janela_1_e_o_pedido_nos_filtros(fr):
    html = _inv(_cliente(), "codigo=THPN-CGH100-INVR1.1&usina=Usina%20Teste&nome=Inversor%201.1&janela=1&rotulo=Inv%201.1")
    assert '<input type="hidden" name="janela" value="1">' in html
    assert 'name="codigo" value="THPN-CGH100-INVR1.1"' in html and 'name="rotulo" value="Inv 1.1"' in html
    assert "Período (criação da OS)" in html and 'data-nome="status"' in html and 'data-nome="tarefa"' in html
    assert 'id="iv_busca"' in html and "os_acoes.js" in html and 'id="os_card"' in html


def test_sem_o_ativo_a_janela_abre_na_usina_inteira_com_o_aviso(fr):
    html = _inv(_cliente(), "codigo=&usina=Usina%20Teste&nome=Inversor%209.9")
    assert 'name="escopo" id="iv_escopo" value="usina"' in html
    assert "20004" in html and " hidden" not in _linha(html, "20004")
    assert "usina inteira" in html and "Nenhuma OS da usina no período" in html


def test_sem_o_login_do_fracttal_vai_ao_login_do_os_creator(fr):
    c = criar_app(segredo="teste", testing=False).test_client()
    r = c.get("/os/historico/ativo?codigo=X")
    assert r.status_code == 302 and "/os/login" in r.headers["Location"]


def test_o_historico_segue_igual_depois_de_a_leitura_sair_da_rota(fr):
    """`rotas.ler_lista` saiu de dentro do `historico`: a tela de sempre mostra as mesmas OS, com a mesma busca."""
    html = _cliente().get("/os/historico?modo=cos").get_data(as_text=True)
    for f in ("20001", "20002", "20003", "20004", "20005", "20006"):
        assert f">{f}</a>" in html, f
    assert "Lista das " in html
