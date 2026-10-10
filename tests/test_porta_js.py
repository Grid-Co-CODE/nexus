"""As contas do porta.js (porta única, 09/10/2026), rodadas no node: o seletor de usina do Diagnóstico (a mesma regra do
Painel NOC da plataforma, com os mesmos endereços de diagnóstico), o item que acende pelo caminho que a moldura avisa
(as expressões vêm do mapa do servidor) e o endereço que o Nexus mostra (`?p=` só fora da entrada padrão). A parte que
mexe na página (o envio do passe, o postMessage, a lista lida da plataforma) se confere no navegador, pela porta local."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nexus.performance import porta

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "porta.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")

TELAS = [{"url": f"/nexus/t/{t.torre}/{t.tela}", "nome": t.nome, "caminho": t.caminho if porta.concreto(t) else "",
          "padroes": porta.padroes_do_navegador(t)} for t in porta.MAPA]


def rodar(expressao, **valores):
    script = ("const P = require(process.argv[1]); const V = JSON.parse(process.argv[2]);"
              f"process.stdout.write(JSON.stringify({expressao}));")
    r = subprocess.run(["node", "-e", script, str(JS), json.dumps(valores)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_o_seletor_usa_os_enderecos_do_painel_noc():
    macro = {"usinas": [
        {"usina": "Usina Ágata", "plant_id": 297410, "fonte": "API PV", "cliente": "Cliente A"},
        {"usina": "Pau D'Arco", "plant_id": "pda-1", "fonte": "Athon"},
        {"usina": "Sem Drill", "plant_id": 5, "fonte": "GreenYellow"},          # sem drill no NOC, fora daqui também
        {"usina": "Lagoa 1", "plant_id": 77, "fonte": "Thopen"},
    ]}
    ger = {"usinas": [
        {"usina": "Usina Agata", "cliente": "Cliente G"},       # casa com a Ágata (sem acento): não repete
        {"usina": "Lagoa", "cliente": "Cliente L"},             # casa com "Lagoa 1" pelo começo, sozinho
        {"usina": "Só Gerencial", "cliente": "Cliente H"},      # só no Gerencial: diagnóstico histórico
        {"usina": "Sem Aba", "cliente": "Cliente H", "sem_dado": True},
    ]}
    lista = rodar("P.usinasDoSeletor(V.macro, V.ger)", macro=macro, ger=ger)
    por_nome = {u["nome"]: u for u in lista}
    assert set(por_nome) == {"Usina Ágata", "Pau D'Arco", "Lagoa 1", "Só Gerencial"}
    assert por_nome["Usina Ágata"]["valor"] == "/painel/usina/297410?fonte=pv&nome=Usina%20%C3%81gata"
    assert por_nome["Usina Ágata"]["grupo"] == "Cliente G"           # o cliente do Gerencial, como no NOC
    assert por_nome["Pau D'Arco"]["valor"] == "/painel/usina/pda-1?fonte=athon&nome=Pau%20D%27Arco"
    assert por_nome["Lagoa 1"]["valor"] == "/painel/usina/77?fonte=pg&nome=Lagoa%201"
    assert por_nome["Só Gerencial"]["valor"] == \
        "/painel/usina/so%20gerencial?hist=1&cliente=Cliente%20H&nome=S%C3%B3%20Gerencial"
    # todo endereço do seletor passa na regra do passe (a plataforma recusaria o que tivesse aspa, por exemplo)
    for u in lista:
        assert porta.destino_permitido(u["valor"]) == u["valor"], u
        assert porta.tela_do_caminho(u["valor"]).tela == "diagnostico"


def test_o_seletor_sem_gerencial_fica_com_as_de_fonte_ao_vivo():
    lista = rodar("P.usinasDoSeletor(V.macro, null)", macro={"usinas": [{"usina": "B", "plant_id": 2, "fonte": "2C"},
                                                                         {"usina": "A", "plant_id": 1, "fonte": "Axis"}]})
    # sem o cliente do Gerencial, o grupo é a fonte; a ordem é grupo, depois nome
    assert [(u["grupo"], u["nome"]) for u in lista] == [("2C", "B"), ("Axis", "A")]
    assert rodar("P.usinasDoSeletor(null, null)") == []


@pytest.mark.parametrize("caminho, url", [
    ("/tempo-real", "/nexus/t/performance/tempo-real"), ("/monitor?fonte=pv&embed=1", "/nexus/t/performance/tempo-real"),
    ("/painel", "/nexus/t/performance/noc"), ("/painel/usina/12?fonte=pv", "/nexus/t/performance/diagnostico"),
    ("/gemeo/usina/3", "/nexus/t/performance/gemeo"), ("/cos", "/nexus/t/cos/acompanhamento"),
    ("/tokens", "/nexus/t/base/chaves-fontes"), ("/gerencial/disponibilidade", "/nexus/t/performance/disponibilidade"),
])
def test_o_item_que_acende_e_o_do_mapa(caminho, url):
    t = rodar("P.telaDoCaminho(V.telas, V.c)", telas=TELAS, c=caminho)
    assert t["url"] == url
    # a mesma resposta do Python
    assert porta.tela_do_caminho(caminho).tela == url.rsplit("/", 1)[1]


@pytest.mark.parametrize("caminho", ["/login", "/", "/os/", "/painel/nexus/entrar", "/gemeo", "/api/macro"])
def test_fora_do_mapa_nada_acende(caminho):
    assert rodar("P.telaDoCaminho(V.telas, V.c)", telas=TELAS, c=caminho) is None


def test_o_endereco_no_nexus_so_leva_p_fora_da_entrada_padrao():
    noc = next(t for t in TELAS if t["url"].endswith("/noc"))
    diag = next(t for t in TELAS if t["url"].endswith("/diagnostico"))
    assert rodar("P.enderecoNoNexus(V.t, '/painel')", t=noc) == "/nexus/t/performance/noc"
    assert rodar("P.enderecoNoNexus(V.t, '/painel?x=1')", t=noc) == "/nexus/t/performance/noc?p=%2Fpainel%3Fx%3D1"
    assert rodar("P.enderecoNoNexus(V.t, '/painel/usina/1?nome=A%20B')", t=diag) == \
        "/nexus/t/performance/diagnostico?p=%2Fpainel%2Fusina%2F1%3Fnome%3DA%2520B"


def test_so_caminho_local_da_plataforma_e_aceito_no_aviso_da_moldura():
    assert rodar("['/painel', '/x?y=1'].map(P.caminhoAceito)") == [True, True]
    assert rodar("['//evil.example', '/\\\\evil', 'https://evil.example/', '', null, 5].map(P.caminhoAceito)") == \
        [False] * 6


# ── a página: nada sai para outra origem (revisão de 10/10/2026) ─────────────────────────────────────────────────────
FALSA = Path(__file__).resolve().parent / "porta_pagina_falsa.js"
PAGINA = "https://app.exemplo.test/nexus/t/performance/noc"


def pagina(**cfg):
    cfg.setdefault("pagina", PAGINA)
    r = subprocess.run(["node", str(FALSA), str(JS), json.dumps(cfg)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _dados(plataforma, **extra):
    return {"plataforma": plataforma, "url": "/nexus/t/performance/noc", "destino": "/painel", "telas": TELAS,
            "passe_lista": "", **extra}


@pytest.mark.parametrize("plataforma", ["", "https://app.exemplo.test"])
def test_na_mesma_origem_o_passe_vai(plataforma):
    feito = pagina(dados=_dados(plataforma), moldura=True)
    assert feito["envios"] == 1 and feito["alerta"] is None and feito["pedidos"] == []


@pytest.mark.parametrize("plataforma", ["http://127.0.0.1:5050", "https://outra.exemplo.test", "http://app.exemplo.test"])
def test_em_outra_origem_o_passe_nao_sai(plataforma):
    """O porta.js avisava e enviava o formulário assim mesmo: com a NEXUS_PLATAFORMA_URL interna do servidor
    (http://127.0.0.1:...), cada visitante mandava um passe válido, com o e-mail dele, à porta local da própria máquina."""
    feito = pagina(dados=_dados(plataforma), moldura=True)
    assert feito["envios"] == 0 and feito["pedidos"] == []
    assert "outra origem" in feito["alerta"]


def test_o_diagnostico_em_outra_origem_nao_le_a_lista_nem_abre_sessao():
    dados = _dados("http://127.0.0.1:5050", destino="", passe_lista="passe-da-lista", url="/nexus/t/performance/diagnostico")
    assert pagina(dados=dados, seletor=True)["pedidos"] == []
    # na mesma origem, o de sempre: lê a lista, leva 401 e abre a sessão com o passe da lista
    feito = pagina(dados={**dados, "plataforma": ""}, seletor=True)
    assert [(x["metodo"], x["url"]) for x in feito["pedidos"][:2]] == [
        ("GET", "https://app.exemplo.test/api/macro"), ("POST", "https://app.exemplo.test/painel/nexus/entrar")]



# ── a sessão da plataforma vencida ou vencendo (auditoria A5 da porta única, 10/10/2026) ──────────────────────────────
# O protocolo combinado com a plataforma: a página dela em modo Nexus, ao receber 401 numa chamada de dado, manda
# {tipo: "nexus:sessao-vencida", caminho} à moldura; a moldura pede um passe novo ao Nexus e reabre a mesma tela, no
# máximo 1 vez a cada 60 s. E renova sozinha a cada 11 h (a sessão do passe vale 12 h). O caso: o Painel NOC desenhava
# "Energia perdida 0,0 MWh" depois das 12 h.
RENOVAR = "/nexus/t/performance/noc/passe"
URL_RENOVAR = "https://app.exemplo.test" + RENOVAR
ENTRAR_PLATAFORMA = "https://app.exemplo.test/painel/nexus/entrar"
PASSE_NOVO = {URL_RENOVAR: {"status": 200, "json": {"ok": True, "passe": "passe-novo", "destino": "/painel"}}}
VENCIDA = {"tipo": "nexus:sessao-vencida", "caminho": "/painel?x=1"}


def _renova(passos, respostas=None, **extra):
    return pagina(dados=_dados("", renovar=RENOVAR, **extra), moldura=True, respostas=respostas or PASSE_NOVO,
                  passos=passos)


def _corpos_para(feito, url):
    return [c for p, c in zip(feito["pedidos"], feito["corpos"]) if p["url"] == url]


def test_as_regras_puras_da_reabertura():
    assert rodar("[P.podeReabrir(0, 5), P.podeReabrir(1000, 60999), P.podeReabrir(1000, 61000)]") == [True, False, True]
    assert rodar("P.caminhoParaReabrir(V.telas, '/cos', '/painel')", telas=TELAS) == "/cos"
    # fora do mapa (o login da plataforma) ou o que não é caminho local: o último caminho que a moldura avisou
    for ruim in ["/login", "//evil.example/painel", "https://evil.example/painel", None, 5]:
        assert rodar("P.caminhoParaReabrir(V.telas, V.r, '/painel')", telas=TELAS, r=ruim) == "/painel", ruim
    assert rodar("P.RENOVA_A_CADA_MS") == 11 * 3600 * 1000


def test_a_sessao_vencida_pede_passe_novo_e_reabre_a_mesma_tela():
    feito = _renova([{"mensagem": VENCIDA}])
    assert _corpos_para(feito, URL_RENOVAR) == ["p=%2Fpainel%3Fx%3D1"]          # o caminho que a plataforma mandou
    # a moldura abriu na carga (o passe da página) e reabriu com o passe novo
    assert feito["envios"] == 2 and feito["passes"] == ["passe-da-pagina", "passe-novo"]
    assert feito["alerta"] is None


def test_no_maximo_uma_reabertura_a_cada_60_s():
    feito = _renova([{"mensagem": VENCIDA}, {"avancar": 30 * 1000}, {"mensagem": VENCIDA}])
    assert len(_corpos_para(feito, URL_RENOVAR)) == 1 and feito["envios"] == 2
    assert "venceu de novo" in feito["alerta"]
    # passados os 60 s, reabre de novo
    feito = _renova([{"mensagem": VENCIDA}, {"avancar": 61 * 1000}, {"mensagem": VENCIDA}])
    assert len(_corpos_para(feito, URL_RENOVAR)) == 2 and feito["envios"] == 3


@pytest.mark.parametrize("passo", [{"mensagem": VENCIDA, "origem": "https://outra.exemplo.test"},
                                   {"mensagem": VENCIDA, "de": "outra"},
                                   {"mensagem": {"tipo": "nexus:outra-coisa", "caminho": "/painel"}}])
def test_aviso_de_outra_origem_ou_de_outra_janela_e_ignorado(passo):
    """A mesma conferência do "nexus:rota": só a moldura, só a origem da plataforma."""
    feito = _renova([passo])
    assert _corpos_para(feito, URL_RENOVAR) == [] and feito["envios"] == 1


def test_caminho_fora_do_mapa_reabre_o_ultimo_que_a_moldura_avisou():
    feito = _renova([{"mensagem": {"tipo": "nexus:rota", "caminho": "/cos"}},
                     {"mensagem": {"tipo": "nexus:sessao-vencida", "caminho": "/login?next=/cos"}}])
    assert _corpos_para(feito, URL_RENOVAR) == ["p=%2Fcos"]


def test_com_a_sessao_do_nexus_encerrada_a_janela_vai_ao_login():
    respostas = {URL_RENOVAR: {"status": 401, "json": {"ok": False, "sessao_encerrada": True,
                                                       "entrar": "/nexus/entrar?motivo=venceu"}}}
    feito = _renova([{"mensagem": VENCIDA}], respostas)
    assert feito["entrarDeNovo"] == "/nexus/entrar?motivo=venceu" and feito["envios"] == 1
    # sem sessão nenhuma o portão responde com o salto ao Entrar (o fetch vê opaqueredirect)
    feito = _renova([{"mensagem": VENCIDA}], {URL_RENOVAR: {"status": 0, "tipo": "opaqueredirect"}})
    assert feito["entrarDeNovo"] == "" and feito["envios"] == 1


def test_o_nexus_sem_passe_avisa_e_nao_mexe_na_moldura():
    feito = _renova([{"mensagem": VENCIDA}], {URL_RENOVAR: {"status": 500}})
    assert feito["envios"] == 1 and "não conseguiu renov" in feito["alerta"]


def test_a_renovacao_sozinha_a_cada_11_h_sem_recarregar_a_tela():
    """A aba aberta (a TV do NOC): antes das 12 h, um passe novo abre outra sessão na plataforma, por fetch (o 303 não é
    seguido), sem recarregar a moldura (nada do que a pessoa tinha na tela se perde)."""
    respostas = {**PASSE_NOVO, ENTRAR_PLATAFORMA: {"status": 0, "tipo": "opaqueredirect"}}
    antes = _renova([{"avancar": 10 * 3600 * 1000}, {"intervalo": True}, {"visivel": True}], respostas)
    assert antes["intervalos"] >= 1 and _corpos_para(antes, URL_RENOVAR) == []          # 10 h: ainda não
    feito = _renova([{"avancar": 11 * 3600 * 1000}, {"intervalo": True}, {"intervalo": True}], respostas)
    assert _corpos_para(feito, URL_RENOVAR) == ["p=%2Fpainel"]                          # uma vez só
    assert _corpos_para(feito, ENTRAR_PLATAFORMA) == ["passe=passe-novo"]
    assert feito["envios"] == 1                                                          # a moldura não recarregou
    # e de novo 11 h depois
    feito = _renova([{"avancar": 11 * 3600 * 1000}, {"intervalo": True}, {"avancar": 11 * 3600 * 1000},
                     {"visivel": True}], respostas)
    assert len(_corpos_para(feito, ENTRAR_PLATAFORMA)) == 2


def test_a_renovacao_sozinha_acompanha_o_caminho_da_moldura():
    respostas = {**PASSE_NOVO, ENTRAR_PLATAFORMA: {"status": 0, "tipo": "opaqueredirect"}}
    feito = _renova([{"mensagem": {"tipo": "nexus:rota", "caminho": "/gerencial"}}, {"avancar": 11 * 3600 * 1000},
                     {"intervalo": True}], respostas)
    assert _corpos_para(feito, URL_RENOVAR) == ["p=%2Fgerencial"]


@pytest.mark.parametrize("plataforma", ["http://127.0.0.1:5050", "https://outra.exemplo.test"])
def test_em_outra_origem_nada_renova(plataforma):
    feito = pagina(dados=_dados(plataforma, renovar=RENOVAR), moldura=True, respostas=PASSE_NOVO,
                   passos=[{"mensagem": VENCIDA, "origem": plataforma}, {"avancar": 12 * 3600 * 1000},
                           {"intervalo": True}])
    assert feito["pedidos"] == [] and feito["envios"] == 0
