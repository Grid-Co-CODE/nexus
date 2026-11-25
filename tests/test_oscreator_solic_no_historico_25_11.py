"""O Histórico de solicitações pelo caminho do Histórico de OS (Levi, 25/11/2026: "faz na parte do histórico ter o mesmo
caminho. E aí vai ter acesso ao histórico de solicitação, que eu acho que tá meio escondido para os supervisores"; as
colunas: "quem criou [...] qual foi o ativo, qual é a descrição, quando foi que foi solicitado, qual foi a OS gerada, quando
a OS foi criada"). O Fracttal e a lista central de OS são falsos; nomes e números inventados."""
import re
from types import SimpleNamespace

from test_oscreator_solic_pcm import NEGA, WEB, _dados, cli, lancador, rs  # noqa: F401  (cli é fixture)


def test_o_historico_de_os_leva_as_solicitacoes_e_volta():
    h = (WEB / "templates" / "historico.html").read_text(encoding="utf-8")
    seg = h.split('<div class="fl-seg" role="group" aria-label="Visão">', 1)[1].split("</div>", 1)[0]
    assert '<a href="/os/solicitacao/historico"' in seg and ">Solicitações</a>" in seg
    # o Início: o atalho no cartão do Histórico de OS
    card = next(c for c in lancador.CONSULTA if c["chave"] == "hist")
    assert {"rotulo": "Solicitações", "href": "/os/solicitacao/historico"} in card["portas"]


def test_a_pagina_das_solicitacoes_tem_a_barra_de_volta_e_as_colunas(cli, monkeypatch):
    import os_central
    criada = SimpleNamespace(data="2026-10-13T14:30:00")                     # em UTC, como o Fracttal grava
    monkeypatch.setattr(os_central, "atual", lambda: SimpleNamespace(por_id={14002: criada}, por_folio={}))
    # aberta a todos (a Área do Solicitante): quem não é do PCM também entra
    h = cli.get("/os/solicitacao/historico", environ_overrides={rs.AREA_PCM: NEGA}).get_data(as_text=True)
    barra = h.split('<div class="fl-seg spc-hist-visoes"', 1)[1].split("</div>", 1)[0]
    assert re.findall(r">([^<>]+)</a>", barra) == ["Histórico Geral", "Atribuídas a mim", "Visão COS", "Solicitações"]
    assert '<a class="on" href="/os/solicitacao/historico" aria-current="page">Solicitações</a>' in barra
    assert 'href="/os/historico?modo=criadas"' in barra
    cab = re.findall(r"<th>([^<]+)</th>", h.split('<table class="spc-tbl">', 1)[1].split("</thead>", 1)[0])
    assert cab == ["Nº", "Criado por", "Cliente", "Usina", "Ativo", "Descrição", "Solicitada em", "Status", "OS gerada",
                   "OS criada em"]
    linhas = {l["id"]: l for l in _dados(h, "hs_dados")["linhas"]}
    # a OS 777 (id 14002) da lista central: criada às 11:30 de Brasília; sem OS, sem a data
    assert linhas[5002]["os_folio"] == 777 and linhas[5002]["os_criada"] == "13/10/2026 11:30"
    assert linhas[5001]["os_criada"] == ""
    assert {l["id"]: l["os_criada"] for l in cli.get("/os/api/solic/historico").get_json()["linhas"]}[5002] == "13/10/2026 11:30"
    js = (WEB / "static" / "solic_hist.js").read_text(encoding="utf-8")
    assert "d.os_criada" in js and 'colspan="10"' in js and "'OS criada em'" in js and "esc(d.criado_por || '—')" in js


def test_sem_a_lista_central_a_coluna_fica_vazia_e_a_pagina_abre(cli, monkeypatch):
    import os_central

    def fora():
        raise RuntimeError("a lista central não respondeu")
    monkeypatch.setattr(os_central, "atual", fora)
    h = cli.get("/os/solicitacao/historico")
    assert h.status_code == 200
    assert all(l["os_criada"] == "" for l in _dados(h.get_data(as_text=True), "hs_dados")["linhas"])
