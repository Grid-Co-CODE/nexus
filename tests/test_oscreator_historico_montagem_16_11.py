"""O Histórico de OS sem trabalho repetido (16/11/2026, Levi: "qual o motivo do processador estar estourando assim?").

O caso: Raio-X das 16:01 de 16/11/2026, um `GET /os/historico` há 3 min 39 s "trabalhando", com o Nexus de 117% a 272% de
processador depois de três reinícios em 5 min. Lido o código (o teto é de 2.000 linhas e montar as 2.000 custa 0,2 s
sozinho), o que custava era a multiplicação, num processo que só roda uma conta por vez:
- as linhas guardadas não tinham trava: N pedidos juntos (as abas abertas, o "Tentar de novo" aos 45 s) montavam N vezes;
- as linhas guardadas eram jogadas fora a cada leitura de 5 min das solicitações, mesmo sem nada novo nelas;
- o solicitante de cada linha copiava e varria a leitura inteira (2.000 linhas x a leitura, a cada pedido);
- o círculo de carga perguntava o progresso de 350 em 350 ms sem esperar a resposta: com o servidor lento as perguntas se
  empilhavam (cada uma ocupa uma thread e uma vaga do teto do OS Creator).
Nenhum conserto muda o que a tela mostra. Nomes e números inventados."""
import re
import threading
import time
import types
from pathlib import Path

import pytest

from nexus.comando import solicitacoes_fracttal as SF

RAIZ = Path(__file__).resolve().parents[1]
CARGA_JS = RAIZ / "nexus" / "torres" / "oscreator" / "os_creator" / "os_web" / "static" / "carga.js"


@pytest.fixture
def HS():
    from test_oscreator_historico_aplicar import cli  # noqa: F401 — põe o clone no caminho de importação
    from os_web import historico_store
    return historico_store


# ── as linhas montadas uma vez, também com os pedidos juntos ───────────────────────────────────
def test_pedidos_juntos_montam_as_linhas_uma_vez_so(HS):
    lista = types.SimpleNamespace(html={})
    entrou, soltar, vezes, saidas = threading.Event(), threading.Event(), [], []

    def montar():
        vezes.append(1)
        entrou.set()
        assert soltar.wait(10)
        return "<tr>linhas</tr>"

    def pedir():
        saidas.append(HS.html_das_linhas(lista, ("criadas", ""), montar))
    fios = [threading.Thread(target=pedir) for _ in range(6)]
    fios[0].start()
    assert entrou.wait(10)
    for f in fios[1:]:
        f.start()
    soltar.set()
    for f in fios:
        f.join(15)
    assert len(vezes) == 1, f"as linhas foram montadas {len(vezes)} vezes para 6 pedidos juntos"
    assert saidas == ["<tr>linhas</tr>"] * 6
    assert lista.html[("criadas", "")] == "<tr>linhas</tr>"
    # depois de pronta, nem espera nem monta
    assert HS.html_das_linhas(lista, ("criadas", ""), lambda: 1 / 0) == "<tr>linhas</tr>"


def test_outra_visao_ou_outra_lista_nao_espera_a_montagem_alheia(HS):
    a, b = types.SimpleNamespace(html={}), types.SimpleNamespace(html={})
    entrou, soltar = threading.Event(), threading.Event()

    def lenta():
        entrou.set()
        assert soltar.wait(10)
        return "A"
    fio = threading.Thread(target=lambda: HS.html_das_linhas(a, ("criadas", ""), lenta))
    fio.start()
    assert entrou.wait(10)
    try:
        t0 = time.monotonic()
        assert HS.html_das_linhas(a, ("cos", ""), lambda: "COS") == "COS"          # outra visão da mesma lista
        assert HS.html_das_linhas(b, ("criadas", ""), lambda: "B") == "B"          # a mesma visão de outra lista
        assert time.monotonic() - t0 < 5, "ficou esperando uma montagem que não é a dela"
    finally:
        soltar.set()
        fio.join(15)


def test_a_montagem_que_quebra_nao_prende_nem_envenena_quem_espera(HS):
    lista = types.SimpleNamespace(html={})
    entrou, soltar, erros = threading.Event(), threading.Event(), []

    def quebra():
        entrou.set()
        assert soltar.wait(10)
        raise RuntimeError("modelo quebrado (de mentira)")

    def dono():
        try:
            HS.html_das_linhas(lista, ("criadas", ""), quebra)
        except RuntimeError as e:
            erros.append(str(e))
    saida = []
    f1 = threading.Thread(target=dono)
    f1.start()
    assert entrou.wait(10)
    f2 = threading.Thread(target=lambda: saida.append(HS.html_das_linhas(lista, ("criadas", ""), lambda: "boa")))
    f2.start()
    soltar.set()
    f1.join(15)
    f2.join(15)
    assert erros == ["modelo quebrado (de mentira)"]                 # o erro vai a quem montava
    assert saida == ["boa"] and lista.html[("criadas", "")] == "boa"  # quem esperava monta a sua, e ela fica guardada
    assert not HS._MONTANDO                                           # nada fica marcado como "em montagem"


# ── o solicitante de cada linha: sem copiar nem varrer a leitura a cada OS ──────────────────────────────────
class _Contada(list):
    """A leitura de 5 min que conta quantas vezes foi percorrida."""
    voltas = 0

    def __iter__(self):
        type(self).voltas += 1
        return super().__iter__()


@pytest.fixture
def leitura(monkeypatch):
    SF.limpar()
    monkeypatch.setattr(SF, "_ligado", lambda app: False)             # nenhuma leitura sai daqui
    _Contada.voltas = 0
    yield
    SF.limpar()


def test_o_solicitante_de_2000_linhas_nao_varre_a_leitura_2000_vezes(leitura):
    SF._ESTADO["linhas"] = _Contada({"wid": 1000 + i, "nome": "Pessoa %d" % i} for i in range(300))
    SF._MAPA["por_wid"] = {5: {"wid": 5, "nome": "Pessoa Antiga"}}
    _Contada.voltas = 0
    nomes = [SF.solicitante_da_os(1000 + (i % 300)) for i in range(2000)]
    assert nomes[:3] == ["Pessoa 0", "Pessoa 1", "Pessoa 2"] and nomes[299] == "Pessoa 299"
    assert SF.solicitante_da_os(5) == "Pessoa Antiga" and SF.solicitante_da_os(7) == "" and SF.solicitante_da_os("x") == ""
    assert _Contada.voltas <= 2, f"a leitura de 5 min foi percorrida {_Contada.voltas} vezes para 2.003 linhas"


def test_a_leitura_de_5_min_vence_o_mapa_e_a_primeira_linha_da_os_vence(leitura):
    SF._ESTADO["linhas"] = [{"wid": 1, "nome": "Da Leitura"}, {"wid": 1, "nome": "Repetida"}, {"wid": 2, "nome": ""}]
    SF._MAPA["por_wid"] = {1: {"wid": 1, "nome": "Do Mapa"}, 2: {"wid": 2, "nome": "Do Mapa 2"}, 3: {"wid": 3, "nome": "Só No Mapa"}}
    assert SF.solicitante_da_os(1) == "Da Leitura"
    assert SF.solicitante_da_os(2) == ""              # a linha da leitura vale, mesmo sem nome (como antes)
    assert SF.solicitante_da_os(3) == "Só No Mapa"
    # a leitura nova troca a resposta na hora
    SF._ESTADO["linhas"] = [{"wid": 1, "nome": "Outra Pessoa"}]
    assert SF.solicitante_da_os(1) == "Outra Pessoa" and SF.solicitante_da_os(2) == "Do Mapa 2"


# ── a versão que joga as linhas guardadas fora: só quando o solicitante de alguma OS muda ───────────────────
def _renovar_com(monkeypatch, linhas):
    monkeypatch.setattr(SF, "ler_rest", lambda **k: [dict(x) for x in linhas])
    monkeypatch.setattr(SF, "_motivos", lambda linhas: None)
    SF._renovar(None)


def test_a_leitura_de_5_min_igual_nao_muda_a_versao(leitura, monkeypatch):
    a = [{"wid": 1, "folio": "15001", "nome": "Pessoa Um"}, {"wid": 2, "folio": "15002", "nome": "Pessoa Dois"}]
    _renovar_com(monkeypatch, a)
    v1 = SF.versao_do_mapa()
    _renovar_com(monkeypatch, a)                       # 5 min depois, as mesmas solicitações
    assert SF.versao_do_mapa() == v1, "a leitura igual jogaria fora as linhas montadas do Histórico"
    # outro campo da solicitação mudou, quem pediu não: as linhas guardadas seguem valendo
    _renovar_com(monkeypatch, [dict(a[0], status="outro"), a[1]])
    assert SF.versao_do_mapa() == v1


@pytest.mark.parametrize("nova", [
    [{"wid": 1, "nome": "Pessoa Um"}, {"wid": 2, "nome": "Pessoa Dois"}, {"wid": 3, "nome": "Pessoa Três"}],   # OS nova
    [{"wid": 1, "nome": "Pessoa Um"}, {"wid": 2, "nome": "Outro Nome"}],                                       # nome trocado
    [{"wid": 1, "nome": "Pessoa Um"}],                                                                         # saiu uma
])
def test_a_leitura_de_5_min_com_solicitante_novo_muda_a_versao(leitura, monkeypatch, nova):
    _renovar_com(monkeypatch, [{"wid": 1, "nome": "Pessoa Um"}, {"wid": 2, "nome": "Pessoa Dois"}])
    v1 = SF.versao_do_mapa()
    _renovar_com(monkeypatch, nova)
    assert SF.versao_do_mapa() != v1


def test_o_mapa_do_dia_novo_muda_a_versao(leitura, monkeypatch):
    v1 = SF.versao_do_mapa()
    monkeypatch.setattr(SF, "ler_rest", lambda **k: [{"wid": 9, "nome": "Pessoa Nove"}])
    SF._renovar_mapa(None)
    assert SF.versao_do_mapa() != v1


# ── o círculo de carga não empilha perguntas ─────────────────────────────────────────────────
def test_o_circulo_so_pergunta_o_progresso_depois_da_resposta_anterior():
    """Com o servidor lento, a pergunta de 350 ms saía de novo antes de a anterior voltar: em 3 min 39 s, ~600 por aba,
    cada uma numa thread do waitress e numa vaga do teto do OS Creator."""
    js = CARGA_JS.read_text(encoding="utf-8")
    bloco = js.split("relogio = setInterval(function () {", 1)[1].split("}, 350);", 1)[0]
    assert "/os/historico/progresso" in bloco
    guarda = re.search(r"if \((\w+)\) return;\s*\1 = true;", bloco)
    assert guarda, "a pergunta do progresso sai sem conferir se a anterior já voltou"
    nome = guarda.group(1)
    # a marca baixa quando a resposta chega E quando o pedido falha (senão o círculo nunca mais perguntaria)
    assert re.search(r"\.then\(function \(\) \{ %s = false; \}, function \(\) \{ %s = false; \}\)" % (nome, nome), bloco) \
        or bloco.count("%s = false" % nome) >= 2
    # e cada círculo novo começa sem a marca de um anterior
    antes = js.split("relogio = setInterval(function () {", 1)[0].rsplit("function mostrar(", 1)[1]
    assert "%s = false" % nome in antes
