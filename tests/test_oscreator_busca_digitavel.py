"""Responsável e usina digitáveis no OS Creator Web (Levi, 08/10/2026): "Conseguir digitar no responsável na criação de
OS" e "Conseguir digitar o nome da usina no filtro do histórico".

O componente é um só, o `os_busca.js` do clone: a tela marca o campo com `data-busca="1"` e ele põe a busca por cima do
<select> (que continua no formulário, escondido, guardando o MESMO valor de antes) ou dentro da lista de marcar do
Histórico. Aqui se confere:
  - que toda tela de criação de OS com o responsável numa lista marca o campo, e que o <select> continua com o mesmo id,
    name e values (o que vai ao servidor não muda);
  - que o Histórico marca as listas locais (Cliente, Usina...) e os checkboxes continuam com os mesmos valores;
  - as regras de casar (sem acento, sem caixa, palavra por palavra), rodando o próprio os_busca.js no node.
O comportamento no navegador (setas, Enter, Esc, texto inválido que volta e avisa, 375 px) foi conferido num Chrome sem
janela, fora da suíte (ver o README da torre). Nenhum teste faz rede; nomes e usinas são de mentira (repositório público).
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app, perf_web, solic_eng_web  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE, "os_web")
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
USINA = "Cliente X - Usina São Exemplo - UF"
CATALOGO = [
    {"id": 1, "code": "TST-INV11", "label": "Inversor 1.1", "description": "Inversor 1.1", "tipo": "Inversor",
     "usina": USINA, "cliente": "Cliente X"},
    {"id": 2, "code": "TST-INV12", "label": "Inversor 1.2", "description": "Inversor 1.2", "tipo": "Inversor",
     "usina": USINA, "cliente": "Cliente X"},
]
PESSOAS = [{"code": "A1", "name": "Ana Teste Silva", "id_personnel": 501},
           {"code": "J2", "name": "João Exemplo", "id_personnel": 502},
           {"code": "B3", "name": "Bruno Souza", "id_personnel": 503}]
USINAS = ["Cliente X - Usina São Exemplo - UF", "Cliente X - Usina Açude Exemplo - UF", "Cliente Y - Usina Três - UF",
          "Cliente Y - Usina Quatro - UF", "Cliente Z - Usina Cinco - UF", "Cliente Z - Usina Seis - UF"]


def _ler(rel):
    return (WEB / rel).read_text(encoding="utf-8")


# ── o componente é o comum, e cada tela marca o campo ───────────────────────────────────────────────────
# (template, trecho do <select> do responsável). O id e o resto do <select> são os de antes: só entrou o data-busca.
RESPONSAVEL = [
    ("templates/perf_criar.html", '<select id="cb_resp" data-busca="1">'),             # Performance (Geração, ETM...)
    ("templates/solic_eng.html", '<select id="cb_resp" data-busca="1" disabled>'),      # Nova solicitação · Engenharia
    ("templates/clonar.html", '<select id="cb_resp" data-busca="1">'),                  # Clonagem de OS
    ("templates/insp.html", '<select id="cb_resp" data-busca="1">'),                    # Inspeção de chamados
    ("templates/pcm.html", '<select id="cb_resp" data-busca="1" autocomplete="off">'),  # PCM
    ("templates/cos.html", '<select id="cb_resp" data-busca="1" aria-label="Requerido por">'),   # COS
    ("templates/solic_fila.html", '<select id="p_resp" data-busca="1">'),               # Fila do PCM: aprovar e criar
    ("templates/solic.html", '<select id="cb_tec" data-busca="1">'),                    # Solicitação: técnico sugerido
    ("templates/os_detalhe_conteudo.html", '<select data-resp-sel data-busca="1" aria-label="Responsável">'),  # trocar
]


@pytest.mark.parametrize("arquivo,trecho", RESPONSAVEL, ids=[a.split("/")[-1] for a, _ in RESPONSAVEL])
def test_toda_tela_de_criar_os_marca_o_responsavel_como_digitavel(arquivo, trecho):
    assert trecho in _ler(arquivo)


def test_o_componente_e_um_so_carregado_pela_base():
    """Uma busca só, no base.html de todas as telas. A Clonagem tinha a sua (um "filtrar pelo nome" separado do <select>);
    com a comum por cima ficavam duas caixas. Saiu."""
    assert '<script src="/os/static/os_busca.js" defer></script>' in _ler("templates/base.html")
    for t in ("perf_criar", "solic_eng", "clonar", "insp", "pcm", "cos", "solic_fila", "solic", "historico", "tradicional"):
        assert _ler(f"templates/{t}.html").startswith('{% extends "base.html" %}'), t
    assert "resp_busca" not in _ler("templates/clonar.html") and "resp_busca" not in _ler("static/clonar.js")
    js = _ler("static/os_busca.js")
    for regra in ("data-busca", "role', 'combobox'", "osm-fora", "'Escape'", "'Tab'", "'Enter'", "aria-activedescendant"):
        assert regra in js, regra
    # o diálogo de trocar responsável monta a busca antes de pôr o foco (senão o foco caía no <select> embrulhado)
    acoes = _ler("static/os_acoes.js")
    assert acoes.index("window.OsBusca.aplicar(caixa)") < acoes.index("const foco = caixa.querySelector")


def test_sair_da_busca_resolve_na_hora_do_clique():
    """Revisão de 08/10/2026: o blur resolvia 120 ms depois, e o clique no "Criar OS" chegava antes. No Chrome sem janela,
    o nome exato de outra pessoa digitado por cima da escolha, seguido do clique no Criar, mandava a escolha anterior.
    O blur resolve na hora."""
    js = _ler("static/os_busca.js")
    blur = re.search(r"inp\.addEventListener\('blur', (.*?)\);\n", js).group(1)
    assert "setTimeout" not in blur and "sair()" in blur


def test_esc_no_dialogo_fecha_primeiro_a_lista_da_busca():
    """Trocar responsável: com a lista aberta, o 1º Esc é da busca (fecha a lista); o 2º fecha o diálogo. Antes o Esc da
    captura na window fechava o diálogo inteiro."""
    acoes = _ler("static/os_acoes.js")
    i_lista = acoes.index(""".osb-in[aria-expanded="true"]""")
    assert i_lista < acoes.index("if (e.key === 'Escape' && aberto) { e.stopPropagation();")


def test_tradicional_casa_o_responsavel_sem_acento_pelo_componente():
    js = _ler("static/tradicional.js")
    assert "window.OsBusca.casa(nome, txt)" in js and "respBusca.addEventListener('keydown'" in js


# ── as telas, pelo app do clone ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def cli(monkeypatch):
    import requests

    def sem_rede(*a, **k):                    # a cota do Fracttal é da empresa: aqui nada sai da máquina
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    monkeypatch.setenv(solic_eng_web.ENV_RESPONSAVEIS, "Ana Teste;Bruno")
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(x) for x in CATALOGO])
    monkeypatch.setattr(api, "get_responsaveis", lambda *a, **k: [dict(p) for p in PESSOAS])
    monkeypatch.setattr(api, "get_labels", lambda *a, **k: [{"id": 7, "description": "PERFORMANCE"}])
    monkeypatch.setattr(api, "get_pessoas_contas", lambda *a, **k: {"pessoas": [{"id_account": 11, "nome": "Ana Teste Silva"}],
                                                                    "eu": 11})
    monkeypatch.setattr(api, "_code_to_loc", lambda *a, **k: {})
    monkeypatch.setattr(api, "_read_asset_cache", lambda *a, **k: [])
    linhas = [{"id": 900 + i, "folio": str(15000 + i), "cliente": u.split(" - ")[0], "usina": u, "tipo": "Inversor",
               "ativo": "Inversor 1.1", "descricao": "Teste", "status": "Em Processo", "data": "2026-10-07T10:00:00"}
              for i, u in enumerate(USINAS)]
    monkeypatch.setattr(api, "list_minhas_os", lambda *a, **k: [dict(x) for x in linhas])
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    return c


def _html(cli, url):
    r = cli.get(url)
    assert r.status_code == 200, (url, r.status_code)
    h = r.get_data(as_text=True)
    assert '<script src="/os/static/os_busca.js" defer></script>' in h, url
    return h


def test_telas_de_criar_os_saem_com_o_responsavel_digitavel_e_o_mesmo_select(cli):
    perf = _html(cli, "/os/performance/criar?frase=" + perf_web.FRASE_COLETA)
    assert '<select id="cb_resp" data-busca="1">' in perf and "(digite p/ pesquisar)" in perf
    # o rótulo aponta para o campo: sem o for=, o 1º controle dentro dele era o botão ↻, e clicar no texto
    # "Responsável" recarregava a lista e apagava a escolha (reproduzido no Chrome sem janela, 08/10/2026)
    assert '<label class="os-campo" for="cb_resp">' in perf
    eng = _html(cli, "/os/solicitacao/engenharia")
    assert '<select id="cb_resp" data-busca="1" disabled>' in eng
    assert '<select id="cb_resp" data-busca="1"' in _html(cli, "/os/chamados/inspecao")
    # Clonagem: as pessoas vêm no HTML; o value de cada uma é o id_personnel, como antes — é ele que vai no criar
    clo = _html(cli, "/os/clonar")
    sel = re.search(r'<select id="cb_resp" data-busca="1">(.*?)</select>', clo, re.S).group(1)
    assert re.findall(r'<option value="([^"]*)">', sel) == ["", "501", "503", "502"]       # em ordem de nome
    assert 'id="resp_busca"' not in clo


def test_historico_tem_busca_na_lista_de_usinas_com_os_mesmos_valores(cli):
    """A lista de marcar com 6 opções ou mais ganha a busca do os_busca (a regra é a mesma do <select>). A de Usina é
    marcada com data-busca e tem a caixa SEMPRE, mesmo com menos de 6 (catálogo fora do ar e período curto). Os
    checkboxes são os de antes: mesmo valor, sem name (o filtro de usina é local, no navegador)."""
    h = _html(cli, "/os/historico?atualizar=1")
    js = _ler("static/os_busca.js")
    assert "details.os-multi" in js and "querMulti" in js and "MIN_OPC = 6" in js
    bloco = re.search(r'<details class="os-multi hf-multi" data-nome="usina" data-local="1" data-busca="1">.*?</details>',
                      h, re.S).group(0)
    valores = re.findall(r'<input type="checkbox" value="([^"]*)"', bloco)
    assert sorted(valores) == sorted(USINAS) and len(valores) >= 6
    assert 'name="usina"' not in bloco
    assert '<details class="os-multi hf-multi" data-nome="cliente" data-local="1">' in h     # as outras: regra dos 6
    # o Status vale no servidor (vai no formulário com name="status") e continua como era
    assert '<details class="os-multi hf-multi" data-nome="status">' in h and 'name="status"' in h
    assert '<select name="pessoa">' in h and '<select name="etiqueta">' in h


# ── as regras de casar, no próprio os_busca.js ──────────────────────────────────────────────────────────
@pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")
def test_casa_sem_acento_sem_caixa_e_palavra_por_palavra():
    casos = [["João Exemplo", "joao"], ["João Exemplo", "JOÃO ex"], ["Ana Teste Silva", "silva ana"],
             ["Cliente X - Usina São Exemplo - UF", "sao exemplo"], ["Cliente X - Usina Açude Exemplo - UF", "acude"],
             ["Ana Teste Silva", ""], ["Ana Teste Silva", "  "], ["Bruno Souza", "brunoso"], ["Ana Teste Silva", "xyz"],
             ["Bruno Souza", "ana"]]
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = {String, Math, Object, console};"
              "vm.createContext(ctx); vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);"
              "const casos = JSON.parse(process.argv[2]);"
              "console.log(JSON.stringify({casa: casos.map(([t, f]) => ctx.OsBusca.casa(t, f)),"
              " norm: ctx.OsBusca.norm('  SÃO   Exemplo ')}));")
    r = subprocess.run(["node", "-e", script, str(WEB / "static" / "os_busca.js"), json.dumps(casos)],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["casa"] == [True, True, True, True, True, True, True, False, False, False]
    assert out["norm"] == "sao exemplo"
