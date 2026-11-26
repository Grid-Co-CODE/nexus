"""Base > Equipamentos das usinas com o De-para junto (13/11/2026). Levi: "o equipamentos das usinas tem que ser junto do de
para de equipamentos, pois um complementa o outro"; "no de para do equipamento, tem que ser possível editar o equipamento
da usina"; e, sobre o lápis numa chave que a plataforma ainda lê da aba Excel, "Pergunta ao salvar".

O de-para é da plataforma e chega aqui pela ponte só de leitura (`nexus/cadastro/depara_fontes.py`). Nenhum teste vai à
rede: `ponte.enviar` é trocada por uma plataforma de mentira que responde o que a de verdade respondeu em 13/11/2026 (a
Céu Azul III, 60010: a fonte manda o INVERSOR05 duas vezes, ids 48400 e 48402, manda um INVERSOR09 que o cadastro não
tem, e não manda o INVERSOR07)."""
import json

import pytest

from nexus.cadastro import depara_fontes as DF
from nexus.cadastro import estrutura_usina as E
from nexus.performance import ponte
from test_base_equipamentos import JSON_, app_eq, banco, cli, cfg  # noqa: F401 — os fixtures

CHAVE_SSO = "c" * 40


class _Resp:
    def __init__(self, status, corpo, ok=True):
        self.status_code, self._corpo = status, corpo
        self.headers = {"Content-Type": "application/json", **({"X-Nexus-Leitura-Ok": "1"} if ok else {})}

    def json(self):
        return self._corpo


LISTA = {"contagem": {"usinas": 3}, "fontes": [
    {"id": "pv", "nome": "Thopen · API PV", "lida": True, "usinas": [
        {"fonte": "pv", "plant_id": 60010, "usina": "Brodowski  1 (90)", "pior": "atencao", "liga": "pelo nome",
         "inv_fonte": 4, "inv_esp": 3, "str_esp": 60, "edita_inversor": True, "edita_usina": True,
         "nomes_inversor": "o nome que a fonte manda", "sem_depara": "inversor",
         "alertas": [{"nivel": "atencao", "texto": "4 inversor(es) na fonte, 3 no cadastro"}]},
        {"fonte": "pv", "plant_id": 777, "usina": "Usina Fantasma (9)", "pior": "critico", "liga": "sem de-para",
         "edita_inversor": True, "edita_usina": True, "sem_depara": "usina",
         "alertas": [{"nivel": "critico", "texto": "sem de-para: o cadastro não tem “Usina Fantasma (9)”"}]}]},
    {"id": "sunop", "nome": "Athon", "lida": True, "usinas": [
        {"fonte": "sunop", "plant_id": "Brodowski 1 (90)", "usina": "Brodowski 1 (90)", "pior": "ok", "liga": "pelo nome",
         "edita_inversor": False, "edita_usina": False, "sem_depara": None, "alertas": []}]},
    {"id": "axis", "nome": "Axis", "lida": False, "usinas": []}]}

USINA_60010 = {
    "fonte": "pv", "id": "60010", "nome_interno": "Brodowski 1 (90)", "provisorio": None, "fonte_hoje_erro": None,
    "cadastro_usinas": [{"chave": "muito grande"}], "decisoes": {"x": 1},
    "alvos": [{"nome": "INVERSOR01", "exibicao": "Inversor 1.1", "esp": 20},
              {"nome": "INVERSOR02", "exibicao": "Inversor 1.2", "esp": 20},
              {"nome": "INVERSOR07", "exibicao": "Inversor 1.7", "esp": 18}],
    "inversores": [{"id": "48403", "nome": "INVERSOR01", "nome_api": "INVERSOR01", "origem": "nome", "na_fonte_hoje": True},
                   {"id": "48400", "nome": "INVERSOR02", "nome_api": "INVERSOR05", "origem": "tela", "na_fonte_hoje": True},
                   {"id": "48402", "nome": "", "nome_api": "INVERSOR05", "origem": "sem", "na_fonte_hoje": True},
                   {"id": "48405", "nome": "INVERSOR09", "nome_api": "INVERSOR09", "origem": "sem", "na_fonte_hoje": True}]}


@pytest.fixture(autouse=True)
def _limpo():
    DF.limpar()
    yield
    DF.limpar()


@pytest.fixture
def plataforma(monkeypatch):
    """A plataforma de mentira atrás da ponte: guarda cada pedido e responde pelo caminho."""
    pedidos = []

    def enviar(**pedido):
        pedidos.append(pedido)
        caminho = pedido["url"].split("://", 1)[1].split("/", 1)[1]
        if caminho == "api/admin/de-para":
            return _Resp(200, LISTA)
        if caminho == "api/admin/de-para/usina":
            q = dict(pedido["params"])
            if q.get("fonte") == "pv" and q.get("id") == "60010":
                return _Resp(200, USINA_60010)
            return _Resp(400, {"error": "esta fonte liga pelo nome que ela manda: corrija no cadastro"})
        return _Resp(403, {"error": "somente leitura (Nexus)"}, ok=False)
    monkeypatch.setattr(ponte, "enviar", enviar)
    return pedidos


CFG = {"NEXUS_PLATAFORMA_URL": "http://plataforma.local", "NEXUS_PLATAFORMA_TOKEN": "chave-de-leitura"}


def _est(*chaves):
    """Uma estrutura mínima: cada (usina_id, supervisorio_id, chave, substitui) e os inversores dela."""
    sup = [{"usina_id": u, "supervisorio_id": s, "usina_supervisorio": c, "substitui_aba": sub, "excluido": False}
           for u, s, c, sub in chaves]
    return {"supervisorios": sup + [{"usina_id": 9, "supervisorio_id": 99, "usina_supervisorio": "Usina Fantasma (9)",
                                     "substitui_aba": False, "excluido": True}], "cabines": [], "inversores": []}


# ── a leitura pela ponte ─────────────────────────────────────────────────────────────────────────────────────────────
def test_sem_a_ponte_configurada_nada_vai_a_rede(plataforma):
    lista = DF.ler_lista({})
    assert lista["fontes"] == [] and "não está ligada" in lista["erro"] and plataforma == []


def test_a_leitura_vai_pela_chave_de_leitura_com_tempo_curto_e_fica_guardada(plataforma):
    lista = DF.ler_lista(CFG)
    assert not lista["erro"] and len(lista["fontes"]) == 3
    p = plataforma[0]
    assert p["method"] == "GET" and p["headers"]["X-Nexus-Leitura"] == "chave-de-leitura" and p["timeout"] == DF.TEMPO_S
    DF.ler_lista(CFG)
    assert len(plataforma) == 1                      # guardada 2 min
    DF.ler_lista(CFG, forcar=True)
    assert len(plataforma) == 2


def test_a_resposta_sem_a_confirmacao_da_chave_nao_vale(monkeypatch):
    monkeypatch.setattr(ponte, "enviar", lambda **_p: _Resp(200, LISTA, ok=False))
    lista = DF.ler_lista(CFG)
    assert lista["fontes"] == [] and "não confirmou a leitura" in lista["erro"]


def test_a_usina_vem_sem_a_lista_do_cadastro_inteiro(plataforma):
    u = DF.ler_usina(CFG, "pv", 60010)
    assert "cadastro_usinas" not in u and "decisoes" not in u and len(u["inversores"]) == 4
    assert dict(plataforma[0]["params"]) == {"fonte": "pv", "id": "60010"}
    assert "corrija no cadastro" in DF.ler_usina(CFG, "sunop", "x")["erro"]


# ── as linhas do diagnóstico em cada usina do Nexus ──────────────────────────────────────────────────────────────────
def test_a_linha_chega_na_usina_pela_chave_com_os_espacos_e_a_de_fora_fica_a_parte(plataforma):
    est = _est((1, 10, "Brodowski 1 (90)", False))
    por, sem = DF.por_usina(DF.ler_lista(CFG), est)
    assert [(x["fonte"], x["supervisorio_id"]) for x in por[1]] == [("pv", 10), ("sunop", 10)]   # a pior primeiro
    assert [x["usina"] for x in sem] == ["Usina Fantasma (9)"]      # a chave excluída não liga
    r = DF.resumo(DF.ler_lista(CFG), est)
    assert r["luzes"] == {1: "alerta"} and r["pendentes"] == 1 and r["sem_par"] == 2 and r["linhas_ok"] == 1


def test_a_linha_que_escreve_a_exibicao_chega_pela_exibicao_de_uma_chave_so():
    """A API PV escreve "Alto Paraná 1" (a exibição); a chave é "Alto Parana 1 (40)". Exibição de duas chaves não liga."""
    est = {"supervisorios": [
        {"usina_id": 3, "supervisorio_id": 30, "usina_supervisorio": "Alto Parana 1 (40)", "usina_exibicao": "Alto Paraná 1",
         "substitui_aba": False, "excluido": False},
        {"usina_id": 4, "supervisorio_id": 41, "usina_supervisorio": "Altair 1 (73)", "usina_exibicao": "Altair",
         "substitui_aba": False, "excluido": False},
        {"usina_id": 4, "supervisorio_id": 42, "usina_supervisorio": "Altair 2 (74)", "usina_exibicao": "Altair",
         "substitui_aba": False, "excluido": False}]}
    lista = {"fontes": [{"id": "pv", "nome": "API PV", "usinas": [
        {"fonte": "pv", "plant_id": 1, "usina": "Alto Paraná 1", "pior": "ok"},
        {"fonte": "pv", "plant_id": 2, "usina": "Altair", "pior": "ok"},
        {"fonte": "pv", "plant_id": 3, "usina": "Altair 2 (74)", "pior": "ok"}]}]}
    por, sem = DF.por_usina(lista, est)
    assert [(x["plant_id"], x["supervisorio_id"]) for x in por[3]] == [(1, 30)]
    assert [(x["plant_id"], x["supervisorio_id"]) for x in por[4]] == [(3, 42)]
    assert [x["usina"] for x in sem] == ["Altair"]


def test_a_luz_da_usina_sem_fonte_fica_apagada_e_nunca_verde():
    assert DF.luz([]) is None
    assert DF.luz([{"luz": "ok"}, {"luz": "critico"}, {"luz": "alerta"}]) == "critico"


# ── os pares ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_os_pares_da_ceu_azul_repetido_sem_par_e_o_que_nao_chega():
    invs = [{"id": 501, "nome": "Inversor 1.1", "equipamento_supervisorio": "INVERSOR01"},
            {"id": 502, "nome": "Inversor 1.2", "equipamento_supervisorio": ""},
            {"id": 507, "nome": "Inversor 1.7", "equipamento_supervisorio": "INVERSOR07"}]
    p = DF.pares(USINA_60010, invs)
    assert [(x["fonte"], x["modo"], x["inversor_id"]) for x in p["linhas"]] == [
        ("INVERSOR01", "ok", 501), ("INVERSOR05", "decidido", 502), ("INVERSOR05", "sem", None),
        ("INVERSOR09", "sem", None)]
    # o INVERSOR02 do cadastro não tem o nome no supervisório no Nexus: casa pelo nome do equipamento ("Inversor 1.2",
    # a exibição dele), e o lápis abre o 502
    assert p["linhas"][1]["alvo"] == {"nome": "INVERSOR02", "exibicao": "Inversor 1.2", "esp": 20}
    assert [x["repetido"] for x in p["linhas"]] == [False, True, True, False]
    assert [(s["alvo"]["nome"], s["inversor_id"]) for s in p["sobra"]] == [("INVERSOR07", 507)]


def test_o_inversor_do_nexus_casa_pelo_nome_do_equipamento_quando_falta_o_do_supervisorio():
    alvo = {"nome": "INVERSOR02", "exibicao": "Inversor 1.2"}
    assert DF._inversor_do_nexus(alvo, [{"id": 1, "nome": "Inversor 1.2", "equipamento_supervisorio": ""}])["id"] == 1
    assert DF._inversor_do_nexus(alvo, [{"id": 1, "nome": "Inversor 9", "equipamento_supervisorio": "X"}]) is None


def test_o_cartao_da_fonte_que_liga_pelo_nome_mostra_o_cadastro_para_o_lapis(plataforma):
    est = {"supervisorios": [{"supervisorio_id": 10, "usina_supervisorio": "Brodowski 1 (90)", "substitui_aba": True}],
           "inversores": [{"inversor_id": 5, "supervisorio_id": 10, "nome": "Inversor 1.1",
                           "equipamento_supervisorio": "INVERSOR01"}]}
    por, _ = DF.por_usina(DF.ler_lista(CFG), _est((1, 10, "Brodowski 1 (90)", True)))
    cs = DF.cartoes(CFG, por[1], est)
    pv, athon = cs
    assert pv["no_lugar_da_aba"] and [x["modo"] for x in pv["linhas"]] == ["ok", "decidido", "sem", "sem"]
    assert pv["linhas"][0]["inversor_id"] == 5
    assert not athon["edita_inversor"] and athon["linhas"] == [] and "corrige no cadastro" in athon["nota"]
    assert athon["sobra"] == [{"alvo": {"nome": "INVERSOR01", "exibicao": "Inversor 1.1", "esp": None}, "inversor_id": 5,
                               "so_cadastro": True}]


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def _liga_brodowski(cli):
    r = cli.post("/t/base/equipamentos/chave", data={"usina": 1, "acao": "ligar", "chave": "Brodowski 1 (90)"})
    assert r.status_code == 303


def test_uma_tela_so_sem_numeros_no_alto_e_as_tres_luzes_na_lista(app_eq, cli, plataforma):
    """17/11/2026, Levi: "Tire esse KPIS" e "Da para deixar tudo numa tela só!": sem a aba De-para e sem os quatro
    números. Desde 25/11/2026 as abas de cima são as de "Metas e equipamentos" (as Metas das usinas ao lado; o de-para
    segue dentro dos Equipamentos)."""
    app_eq.config.update(CFG)
    _liga_brodowski(cli)
    html = cli.get("/t/base/equipamentos").get_data(as_text=True)
    abas = html.split('class="gc-subabas"', 1)[1].split("</nav>", 1)[0]
    assert abas.count("<a ") == 2 and "Metas das usinas" in abas and ">De-para<" not in abas
    assert 'class="eqx-kpis"' not in html and "Usinas com equipamentos" not in html
    lista = html.split('id="eq-itens"')[1]
    assert 'aria-label="Chave: ok; equipamentos: atenção; fonte: atenção"' in lista
    assert 'aria-label="Chave: falta; equipamentos: sem leitura; fonte: sem leitura"' in lista   # Matões 100
    # os filtros no padrão do Histórico de OS, na lateral: listas de marcar, e dentro da lista vale qualquer um
    assert 'data-fo>' in html and 'name="filtro" multiple' in html and 'name="cliente" multiple' in html
    html = cli.get("/t/base/equipamentos?filtro=depara").get_data(as_text=True)
    itens = html.split('id="eq-itens"')[1]
    assert "Brodowski" in itens and "Matões 100" not in itens
    itens = cli.get("/t/base/equipamentos?filtro=depara&filtro=sem_chave").get_data(as_text=True).split('id="eq-itens"')[1]
    assert "Brodowski" in itens and "Matões 100" in itens


def test_as_fontes_da_usina_na_mesma_tela_com_os_cartoes_por_fetch(app_eq, cli, plataforma):
    """As fontes que chegam ficam em "Fontes de dados" da usina, na mesma página do editor; sem o lápis dos cartões (o
    dpx-dados): dois rascunhos da mesma usina na mesma página brigariam pelo selo."""
    app_eq.config.update(CFG)
    _liga_brodowski(cli)
    html = cli.get("/t/base/equipamentos?usina=1").get_data(as_text=True)
    assert "/static/cadastro-depara.js" in html and 'id="dpx"' in html and 'id="fontes"' in html
    assert 'id="passo-chave"' in html and 'id="eq-editor"' in html and 'id="dpx-dados"' not in html
    # as chaves recolhidas (Levi: "essa parte de chaves quero recolhida")
    assert '<details class="cad-secao eq-passo ace-recolhe" id="passo-chave">' in html
    j = cli.get("/t/base/equipamentos/fontes?usina=1", headers=JSON_).get_json()
    assert j["ok"] and [c["fonte"] for c in j["cartoes"]] == ["pv", "sunop"]
    assert [x["fonte"] for x in j["cartoes"][0]["linhas"]] == ["INVERSOR01", "INVERSOR05", "INVERSOR05", "INVERSOR09"]
    # usina fora do Registro e pedido de outro site: nada
    assert cli.get("/t/base/equipamentos/fontes?usina=999").status_code == 400
    assert cli.get("/t/base/equipamentos/fontes?usina=1", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_a_fonte_que_nao_chega_em_usina_nenhuma_se_liga_na_usina(app_eq, cli, plataforma):
    """17/11/2026, Levi, no Rio do Peixe I e II: "Diz que nenhuma fonte chega na usina sendo que temos SCADA Grid Apolo!
    [...] vai ter uma parte onde eu escolho qual a fonte de dados e ele tenta lincar [...] caso não consiga eu mesmo
    linko". Sem usina aberta, a lista delas; com a usina aberta, o Ligar com a fonte para escolher."""
    app_eq.config.update(CFG)
    html = cli.get("/t/base/equipamentos").get_data(as_text=True)
    assert "Fontes que não chegam em usina nenhuma" in html and "Usina Fantasma (9)" in html
    html = cli.get("/t/base/equipamentos?usina=1").get_data(as_text=True)
    sel = html.split('id="eq-fonte"')[1].split("</select>")[0]
    assert 'value="Usina Fantasma (9)"' in sel and 'name="chave_nova"' in html.split('class="eq-form eq-guarda eq-fonte-ligar"')[1]


def test_a_fonte_mais_parecida_com_a_usina_vem_escolhida():
    from nexus.cadastro import telas_equipamentos as TE
    linhas = [{"fonte_nome": "Thopen · API PV", "usina": "Usina Fantasma (9)", "luz": "critico"},
              {"fonte_nome": "scadaGridco · Apolo", "usina": "Rio do Peixe I e II", "luz": "ok"},
              {"fonte_nome": "Axis", "usina": "", "luz": "ok"}]
    f = TE.fontes_livres(linhas, "Rio do Peixe I e II")
    assert [x["chave"] for x in f] == ["Rio do Peixe I e II", "Usina Fantasma (9)"] and f[0].get("sugerida")
    assert not f[1].get("sugerida")
    # nada parecido: nenhuma vem escolhida (a pessoa escolhe)
    assert not any(x.get("sugerida") for x in TE.fontes_livres(linhas, "Marabá 200"))


def test_sem_a_ponte_a_tela_abre_e_diz_que_nao_leu(cli, plataforma):
    html = cli.get("/t/base/equipamentos?aba=depara").get_data(as_text=True)
    assert "Sem leitura do de-para da plataforma" in html and plataforma == []


def test_a_janela_da_plataforma_leva_o_passe_ao_editor_da_usina(app_eq, cli):
    html = cli.get("/t/base/equipamentos/fontes/janela?editar=pv|60010")
    assert html.status_code == 400 and "não abre neste servidor" in html.get_data(as_text=True)   # porta desligada
    app_eq.config.update(NEXUS_SSO_CHAVE=CHAVE_SSO)
    r = cli.get("/t/base/equipamentos/fontes/janela?editar=pv|60010")
    texto = r.get_data(as_text=True)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    assert 'action="/painel/nexus/entrar"' in texto and 'target="dpj-moldura"' in texto and "data-nexus" not in texto
    passe = texto.split('name="passe" value="')[1].split('"')[0]
    from test_porta_mapa import _decodificar
    assert _decodificar(passe)[0]["destino"] == "/admin/de-para?janela=1&editar=pv%7C60010"
    assert cli.get("/t/base/equipamentos/fontes/janela?editar=").status_code == 400


def test_o_de_para_completo_sai_do_menu_e_acende_equipamentos():
    from nexus.torres.base import TORRE
    t = next(x for x in TORRE.telas if x.id == "de-para-equipamentos")
    assert t.dentro_de == "equipamentos"


def test_salvar_pela_aba_de_para_passa_a_chave_a_valer(app_eq, cli, plataforma):
    """O lápis grava pela mesma rota do Salvar, com a chave marcada no lugar da aba quando a pessoa escolhe."""
    app_eq.config.update(CFG)
    _liga_brodowski(cli)
    html = cli.get("/t/base/equipamentos?usina=1").get_data(as_text=True)
    d = json.loads(html.split('id="eq-dados">')[1].split("</script>")[0])
    ch = dict(d["chaves"][0], substitui_aba=True)
    corpo = {"usina_id": 1, "selo": d["selo"], "chaves": [ch], "cabines": [],
             "inversores": [{"id": None, "nome": "Inversor 1.9", "chave": ch["supervisorio_id"], "cabine": None,
                             "equipamento_supervisorio": "INVERSOR09", "potencia_kwp": None, "strings_esperadas_qtd": 18}]}
    j = cli.post(d["salvar_url"], json=corpo, headers=JSON_).get_json()
    assert j["ok"] and j["editor"]["chaves"][0]["substitui_aba"] is True
    assert j["editor"]["inversores"][0]["equipamento_supervisorio"] == "INVERSOR09"
