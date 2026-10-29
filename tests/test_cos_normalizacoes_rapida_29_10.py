"""COS > Normalizações sem recarregar a cada filtro (29/10/2026). Levi: "gostaria de saber pq COS > Normalizações demora
tanto para carregar sendo que eu carrego a primeira vez e ele inventa de carregar sempre que clico, tem como otimizar?".
Medido com ~1.000 normalizações por mês (o volume real é ~340 por semana): cada filtro recarregava a página inteira
(1,1 MB sem filtro) e, passado o minuto da cópia, o clique esperava a Ronda COS responder (com ela a 3 s, o filtro levou
3,2 s, e todos os que abriam a tela esperavam juntos). O que estes testes seguram: todas as linhas do mês vêm, com o que
cada filtro olha, e as de fora do filtro do endereço chegam escondidas; as contas da faixa vêm em cada linha; e a cópia
vencida volta na hora, com a releitura por trás. Nada vai à rede; os dados são fictícios."""
import re
import threading
import time

from test_cos_normalizacoes import AGORA, ITENS, _limpa, _n, _resp, _servir, ligada  # noqa: F401 (fixtures)

from nexus.cos import andamento as AND
from nexus.cos import normalizacoes as NO


def _linha(html, folio):
    i = html.index(f'data-folio="{folio}"')
    return html[html.rindex("<tr", 0, i):html.index(">", i)]


def _visivel(html, folio):
    return " hidden" not in _linha(html, folio)


def test_todas_as_linhas_do_mes_vem_e_o_filtro_e_da_pagina(ligada, logado, monkeypatch):
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    _servir(monkeypatch, _resp(ITENS))
    html = logado.get("/t/cos/normalizacoes?status=processo&q=exemplo").get_data(as_text=True)
    assert all(f'data-folio="{f}"' in html for f in ("17001", "16702"))      # as do mês vêm todas
    assert _visivel(html, "16702") and not _visivel(html, "17001")
    l = _linha(html, "16702")
    assert 'data-f-status="processo"' in l and 'data-f-cliente="CLIENTE B"' in l and 'data-f-usina="Usina Exemplo Dois"' in l
    assert 'data-f-criado_por="Ciclano Operador"' in l and 'data-f-tecnico="Tecnica Dois"' in l
    assert 'data-f-falha="Falha de comunicação"' in l and 'data-os="16702"' in l
    assert 'data-aberta="1"' in l and 'data-dias="8"' in l and 'data-fora="233"' in l and 'data-hr="1"' in l
    assert re.search(r'data-f-busca="16702 [^"]*cliente b [^"]*usina exemplo dois[^"]*ciclano operador', l)
    assert html.count('data-hr="0"') == 1                                     # a sem hora real (r4)
    assert 'onchange="this.form.submit()"' not in html and "cos/normalizacoes.js" in html
    assert 'id="cos-norm-filtros"' in html and 'data-norm-vazio' in html and 'data-norm-limpar' in html
    # a faixa e as contas das opções continuam as do servidor (o JS só as refaz ao filtrar)
    assert 'data-norm-r="total">5<' in html                # sem o status: as 5 do mês com "exemplo"


def test_a_copia_vencida_volta_na_hora_e_a_releitura_e_por_tras(ligada, monkeypatch):
    pedidos = _servir(monkeypatch, _resp(ITENS))
    NO.ler(ligada.config, AGORA)
    assert len(pedidos) == 1
    solta, chegou = threading.Event(), []
    certo = AND._pedir

    def pedir(f, caminho, timeout=AND.TIMEOUT_S):
        chegou.append(caminho)
        solta.wait(5)                                       # a Ronda COS demora a responder
        return certo(f, caminho, timeout)
    monkeypatch.setattr(AND, "_pedir", pedir)
    for st in NO._estado.values():
        st["perguntado"] -= NO.TTL_S + 1
    t0 = time.monotonic()
    l = NO.ler(ligada.config, AGORA)
    assert time.monotonic() - t0 < 1 and len(l.dados["itens"]) == 6          # vencida: a cópia, na hora
    NO.ler(ligada.config, AGORA)                                             # já relendo: não abre outra releitura
    assert sum(th.name == "nexus-cos-normalizacoes" for th in threading.enumerate()) == 1
    fim = time.monotonic() + 5
    while not chegou:
        assert time.monotonic() < fim
        time.sleep(0.01)
    solta.set()
    while any(st.get("renovando") for st in NO._estado.values()):
        assert time.monotonic() < fim
        time.sleep(0.02)
    assert len(chegou) == 1 and len(pedidos) == 2
    assert all(time.monotonic() - st["perguntado"] < 5 for st in NO._estado.values())


def test_sem_copia_a_primeira_leitura_e_na_hora(ligada, monkeypatch):
    pedidos = _servir(monkeypatch, _resp([_n("a")], "c1", mais=True), _resp([_n("b")], "c2"))
    l = NO.ler(ligada.config, AGORA)
    assert len(pedidos) == 2 and len(l.dados["itens"]) == 2 and not l.dados["carregando"]
