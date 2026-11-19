"""O clone do Radar sem valor de contrato nem citação de cliente e de fornecedor (19/11/2026).

Levi, 19/11/2026: "`radar.html`: o valor de contrato e as citações de clientes passam a vir do banco, por uma rota que exige
login" e "Eu não aceito só censurar [...] quem tiver um acesso do Nexus vai ter a informação completa". O arquivo
versionado guarda fichas (`nexus/dados/textos_reservados.py`); a rota `/t/zeladoria/app`, que exige login, lê o livro do
banco e serve a página com o texto de volta em cada ficha: a mesma página de antes.

Tudo aqui é inventado e nada lê o banco de verdade; a conferência contra o banco (nenhum texto reservado de volta no
arquivo) roda só com o `.env`, como a trava de nomes."""
import base64
import re
from pathlib import Path

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import Cofre
from nexus.dados import textos_reservados as TR
from nexus.torres import zeladoria as Z

RAIZ = Path(__file__).resolve().parents[1]
CLONE = (RAIZ / "nexus" / "torres" / "zeladoria" / "clone" / "radar.html").read_text(encoding="utf-8")
CHAVE = base64.urlsafe_b64encode(b"z" * 32).decode()
BASE = "http://banco.exemplo.test"
AREA = "zeladoria_radar"
# os números que NÃO são dado: o zero do cartão, a tolerância de R$ 1, o exemplo do diesel e os exemplos de como digitar
VALORES_QUE_FICAM = {"R$ 0,00", "R$ 1", "R$ 2.000"}
MILHARES_QUE_FICAM = {"0.005", "1.234,56", "2.000", "250.000", "5.250"}


def test_o_clone_versionado_nao_traz_valor_em_reais_nem_numero_de_contrato():
    assert {v.rstrip(".,") for v in re.findall(r"R\$ ?\d[\d.,]*", CLONE)} <= VALORES_QUE_FICAM
    assert set(re.findall(r"(?<![\d.,#\w-])\d{1,3}\.\d{3}(?:,\d{2})?(?![\d.])", CLONE)) <= MILHARES_QUE_FICAM
    assert not re.search(r"\b\d+(?:[.,]\d+)? ?(?:mil|milh[ãõ][oe]s?)\b", CLONE)


def test_o_clone_versionado_traz_as_fichas_no_lugar_dos_nomes_e_dos_valores():
    fichas = TR.fichas_em(CLONE)
    assert len(fichas) >= 25
    for comeco in ("Zlcliente", "zlcliente", "Zlfornecedor", "zlfornecedor", "ZLVALOR", "ZLTRECHO"):
        assert any(f.startswith(comeco) for f in fichas), comeco
    # a ficha vale no lugar em que o nome estava: no nome de variável, na coluna do banco, na regra e no texto de tela
    assert re.search(r"\btemZlcliente\d\d\b", CLONE) and re.search(r"'faturamento_zlcliente\d\d'", CLONE)
    assert re.search(r"var CLIENTE_ALIAS = \{ ZLTRECHO\d\d \};", CLONE)


@pytest.fixture
def com_o_banco(app):
    """O banco de mentira com um texto inventado para cada ficha do clone."""
    api = ApiPGFalsa()
    textos = {f: f"[texto inventado {n:02d}]" for n, f in enumerate(TR.fichas_em(CLONE))}
    TR.publicar(AREA, textos, base=BASE, sessao=api, token="tk", cofre=Cofre(CHAVE))
    app.extensions["nexus_dados_sessao"] = api
    app.config.update(NEXUS_CHAVE_CADASTRO=CHAVE, GRIDCO_DB_API=BASE)
    return textos


def test_a_rota_com_login_devolve_o_texto_do_banco_no_lugar_de_cada_ficha(logado, com_o_banco):
    r = logado.get("/t/zeladoria/app")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and TR.fichas_em(html) == [] and "X-Nexus-Textos-Reservados" not in r.headers
    for ficha, texto in com_o_banco.items():
        assert html.count(texto) == CLONE.count(ficha), ficha
    # o resto da página é o do arquivo: fora o que a rota põe no alto e no fim (a configuração, os tokens, a ponte), o
    # miolo servido é a restauração, caractere por caractere
    restaurado = TR.restaurar(CLONE, com_o_banco)
    assert restaurado[100_000:len(restaurado) - 2_000] in html


def test_sem_login_a_rota_nao_entrega_a_pagina(cliente, com_o_banco):
    r = cliente.get("/t/zeladoria/app")
    assert r.status_code in (302, 401, 403) and "[texto inventado " not in r.get_data(as_text=True)


def test_sem_o_banco_a_pagina_abre_com_as_fichas_e_avisa_no_cabecalho_sem_guardar_o_erro(logado, app):
    r = logado.get("/t/zeladoria/app")                      # o teste sem banco: nenhuma leitura boa ainda
    assert r.status_code == 200 and TR.fichas_em(r.get_data(as_text=True)) == TR.fichas_em(CLONE)
    assert r.headers["X-Nexus-Textos-Reservados"] == f"faltam {len(TR.fichas_em(CLONE))}"
    # o banco volta: a página seguinte já vem inteira (o erro não fica guardado na cópia da página)
    api = ApiPGFalsa()
    TR.publicar(AREA, {f: "ok" for f in TR.fichas_em(CLONE)}, base=BASE, sessao=api, token="tk", cofre=Cofre(CHAVE))
    app.extensions["nexus_dados_sessao"] = api
    app.config.update(NEXUS_CHAVE_CADASTRO=CHAVE, GRIDCO_DB_API=BASE)
    with app.app_context():
        TR.ler(AREA, forcar=True)
    r = logado.get("/t/zeladoria/app")
    assert TR.fichas_em(r.get_data(as_text=True)) == [] and "X-Nexus-Textos-Reservados" not in r.headers


def test_a_ficha_nova_sem_texto_no_banco_aparece_no_cabecalho(logado, app, monkeypatch):
    api = ApiPGFalsa()
    fichas = TR.fichas_em(CLONE)
    TR.publicar(AREA, {f: "ok" for f in fichas[1:]}, base=BASE, sessao=api, token="tk", cofre=Cofre(CHAVE))
    app.extensions["nexus_dados_sessao"] = api
    app.config.update(NEXUS_CHAVE_CADASTRO=CHAVE, GRIDCO_DB_API=BASE)
    r = logado.get("/t/zeladoria/app")
    assert r.headers["X-Nexus-Textos-Reservados"] == "faltam 1" and TR.fichas_em(r.get_data(as_text=True)) == fichas[:1]


def test_nenhum_texto_reservado_voltou_para_o_arquivo_versionado():
    """Com o `.env` (a chave do cadastro) e o banco: nenhum texto reservado da Zeladoria aparece no clone versionado. É o
    que pega quem escreveu de novo o nome do fornecedor ou o valor na ajuda de uma tela. Sem a chave ou o banco, pula."""
    import requests

    from nexus.cadastro.ligacoes import BASE_API
    from nexus.config import ler_ambiente
    from nexus.dados import livros
    env = ler_ambiente()
    if not env.get("NEXUS_CHAVE_CADASTRO"):
        pytest.skip("sem NEXUS_CHAVE_CADASTRO nesta máquina: os textos reservados não abrem")

    class SoLeitura:            # só GET: este teste nunca grava no banco
        def get(self, *a, **k):
            return requests.get(*a, **k)
    try:
        linhas = livros.ler((env.get("GRIDCO_DB_API") or BASE_API).rstrip("/"), SoLeitura(), TR.LIVRO, TR.ABA)
    except requests.RequestException as e:
        pytest.skip(f"sem acesso ao banco do Nexus ({type(e).__name__})")
    textos = TR.abrir(linhas, Cofre(env["NEXUS_CHAVE_CADASTRO"]), AREA)
    if not textos:
        pytest.skip("o livro dos textos reservados ainda não tem a área da Zeladoria")
    # o texto curto (o preço "1.6", a sigla de 2 letras) também é número e cor: esses a ferramenta reserva pelo contexto
    voltou = sorted(f for f, t in textos.items() if len(t) >= 5 and t in CLONE)
    assert not voltou, "texto reservado de volta no clone (só a ficha; o texto nunca vai para a saída): " + ", ".join(voltou)
    assert not [f for f in TR.fichas_em(CLONE) if f not in textos], "ficha no clone sem texto no banco"


def test_a_torre_le_o_clone_pelo_modulo_dos_textos_reservados():
    assert Z.AREA_RESERVADA == AREA
