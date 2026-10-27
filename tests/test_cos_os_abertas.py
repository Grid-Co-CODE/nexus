"""Torre COS: a tela OS em aberto (27/10/2026) — o Panorama da Ronda COS no Nexus: que OS o COS abriu e seguem abertas
no Fracttal, e há quanto tempo?

As OS vêm do Andamento (`GET /api/nexus/os-abertas`, já com os cortes, a situação e o alerta de lá); os filtros, as
contas e a idade são do Nexus (nexus/cos/os_abertas.py). Nada aqui vai à rede, e os dados são fictícios."""
from datetime import datetime

import pytest

from nexus.cos import andamento as AND
from nexus.cos import os_abertas as OA

CHAVE = "chave-de-teste-do-andamento"
AGORA = AND.instante("2026-10-27T10:00:00-03:00")


def _os(folio, criada="2026-10-27T08:00:00-03:00", situacao="pendente", cliente="CLIENTE A", usina="Usina Exemplo Um",
        codigo="EX-UM100", tipo="Religamento", registro="TRATATIVA_REMOTA", em_alerta=False, **mudar):
    o = {"folio": folio, "id_work_order": folio + 900000, "status": 1, "criada_em": criada, "primeira_tarefa": None,
         "cliente": cliente, "usina_codigo": codigo, "usina": usina, "rota": None, "ativos": [f"{codigo}-SKID1"],
         "ativo_nome": "SKID 1", "tipo": tipo, "classificacao": None, "prioridade": None,
         "concluida_pct": 100 if situacao == "concluida" else 0, "situacao": situacao, "registro_estado": registro,
         "reconhecida_em": None, "em_alerta": em_alerta}
    o.update(mudar)
    return o


def _dados(os_, **mudar):
    d = {"versao": 1, "gerado_em": "2026-10-27T10:00:00-03:00", "varredura_em": "2026-10-27T09:43:00-03:00",
         "horas_para_alerta": 1, "os": os_, "truncado": False,
         "cortes": {"na_varredura": 40, "fora_do_cos": 30, "usina_de_teste": 1, "assunto_encerrado": 2}}
    d.update(mudar)
    return d


OS_ = [
    _os(101, criada="2026-06-01T10:00:00-03:00", em_alerta=True, registro=None),                    # 148 dias
    _os(102, criada="2026-09-20T10:00:00-03:00", situacao="concluida", cliente="CLIENTE B",          # 37 dias, feita
        usina="Usina Exemplo Dois", codigo="EX-DOIS100", tipo="Corretiva Emergencial"),
    _os(103, criada="2026-10-22T10:00:00-03:00", em_alerta=True, tipo="Religamento Remoto"),        # 5 dias
    _os(104, criada="2026-10-27T09:30:00-03:00", reconhecida_em="2026-10-27T09:40:00-03:00"),       # 30 min
]


def _painel(**filtros):
    return OA.painel(AND.Leitura("", _dados(OS_)), AGORA, **filtros)


# --- as contas -------------------------------------------------------------------------------------------------------

def test_a_situacao_padrao_e_a_pendente_e_as_pilulas_contam_todas():
    """O padrão é o que a tela promete (o pendente); a pílula da outra situação mostra o tamanho dela."""
    p = _painel()
    assert [i["folio"] for i in p.itens] == [101, 103, 104]
    assert p.contagem["situacao"] == {"pendente": 3, "concluida": 1, "todas": 4}
    assert [i["folio"] for i in _painel(situacao="concluida").itens] == [102]
    assert [i["folio"] for i in _painel(situacao="todas").itens] == [101, 102, 103, 104]
    assert _painel(situacao="qualquer").contagem["situacao"]["pendente"] == 3      # valor estranho: o padrão


def test_a_faixa_conta_sobre_a_situacao_e_o_alerta_e_do_painel():
    p = _painel()
    assert p.resumo == {"total": 3, "acima_30": 1, "acima_90": 1, "sem_registro": 1, "em_alerta": 2}
    assert p.contagem["faixa"] == {"0-7": 2, "7-30": 0, "30-90": 0, "90+": 1}
    # na lista das feitas o alerta continua o do painel: OS em alerta é sempre pendente, e o número não some ao trocar
    assert _painel(situacao="concluida").resumo["em_alerta"] == 2


def test_os_filtros_e_as_pilulas_que_nao_encolhem():
    """As pílulas de cliente, tipo e idade contam ANTES dos filtros: um contador que encolhe ao filtrar não diz mais
    quanto existe."""
    p = _painel(situacao="todas", cliente="CLIENTE B")
    assert [i["folio"] for i in p.itens] == [102]
    assert p.contagem["cliente"] == {"CLIENTE A": 3, "CLIENTE B": 1}
    assert [i["folio"] for i in _painel(tipo="religamento remoto").itens] == [103]      # sem caixa
    assert [i["folio"] for i in _painel(faixa="90+").itens] == [101]
    assert [i["folio"] for i in _painel(sem_registro=True).itens] == [101]
    assert [i["folio"] for i in _painel(busca="103").itens] == [103]                     # o nº da OS, exato
    assert [i["folio"] for i in _painel(situacao="todas", busca="dois100-skid").itens] == [102]   # o ativo


def test_a_idade_em_horas_ate_dois_dias_e_nunca_negativa():
    assert OA.aberta_ha(30) == "30 h" and OA.aberta_ha(47) == "47 h" and OA.aberta_ha(48) == "2 dias"
    assert OA.idade(AND.instante("2026-10-27T11:00:00-03:00"), AGORA) == (0, 0)          # o relógio do Fracttal à frente
    assert [OA.faixa_de(d) for d in (0, 6, 7, 29, 30, 89, 90, 400)] == ["0-7", "0-7", "7-30", "7-30", "30-90",
                                                                         "30-90", "90+", "90+"]
    i = {x["folio"]: x for x in _painel(situacao="todas").itens}
    assert (i[104]["aberta_ha"], i[103]["aberta_ha"], i[101]["dias"]) == ("0 h", "5 dias", 148)


def test_o_status_e_o_registro_em_palavras():
    i = {x["folio"]: x for x in _painel(situacao="todas").itens}
    assert (i[101]["status"], i[101]["status_card"]) == ("Em processo", "Em Processo")
    assert i[101]["registro"] == OA.SEM_REGISTRO and i[101]["sem_registro"]
    assert i[103]["registro"] == ("Tratativa remota", "info")


def test_a_varredura_velha_e_a_que_nunca_passou():
    """A varredura lá roda de 30 em 30 min: três passagens perdidas e a tela avisa que a lista pode ter OS já fechadas."""
    assert not _painel().varredura_velha
    velha = OA.painel(AND.Leitura("", _dados(OS_, varredura_em="2026-10-27T08:20:00-03:00")), AGORA)
    assert velha.varredura_velha
    nunca = OA.painel(AND.Leitura("", _dados([], varredura_em=None)), AGORA)
    assert nunca.varredura is None and not nunca.varredura_velha
    assert OA.painel(AND.Leitura("", None, erro="x"), AGORA) is None


# --- a leitura -------------------------------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _limpa():
    AND.limpar_cache()
    yield
    AND.limpar_cache()


@pytest.fixture
def ligada(app):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002", NEXUS_COS_ANDAMENTO_CHAVE=CHAVE,
                      NEXUS_COS_ANDAMENTO_CLIENTES="Cliente A")
    return app


def _servir(monkeypatch, resposta):
    pedidos = []

    def pedir(f, caminho):
        pedidos.append(caminho)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
    monkeypatch.setattr(AND, "_pedir", pedir)
    return pedidos


def test_a_leitura_confere_o_contrato_e_explica_o_404(ligada, monkeypatch):
    _servir(monkeypatch, AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá", 404))
    assert "ainda não tem a rota das OS abertas" in AND.ler_os_abertas(ligada.config).erro
    AND.limpar_cache()
    _servir(monkeypatch, _dados(OS_, versao=2))
    assert "versão 2 das OS abertas" in AND.ler_os_abertas(ligada.config).erro
    AND.limpar_cache()
    _servir(monkeypatch, {"versao": 1, "os": []})
    assert "não tem as OS abertas" in AND.ler_os_abertas(ligada.config).erro


def test_na_falha_fica_a_ultima_leitura_boa(ligada, monkeypatch):
    pedidos = _servir(monkeypatch, _dados(OS_))
    assert AND.ler_os_abertas(ligada.config).dados["os"]
    assert AND.ler_os_abertas(ligada.config).dados["os"] and pedidos == ["/api/nexus/os-abertas"]   # a cópia de 60 s
    monkeypatch.setattr(AND.time, "monotonic", lambda: 10 ** 9)
    _servir(monkeypatch, AND.FonteErro("o Andamento não respondeu (TimeoutError)"))
    l = AND.ler_os_abertas(ligada.config)
    assert l.velha and l.dados["os"] and "não respondeu" in l.erro


# --- a tela ----------------------------------------------------------------------------------------------------------

def test_a_tela(ligada, logado, monkeypatch):
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    pedidos = _servir(monkeypatch, _dados(OS_))
    html = logado.get("/t/cos/os-abertas").get_data(as_text=True)
    assert pedidos == ["/api/nexus/os-abertas"]
    # a mais antiga primeiro, com a idade, o registro e o alerta
    assert html.index('data-folio="101"') < html.index('data-folio="103"') < html.index('data-folio="104"')
    assert 'data-folio="102"' not in html                                       # feita: fora do padrão
    assert "148 dias" in html and 'cn-pill cn-alerta">Sem registro<' in html and 'cn-pill cn-critico">Em alerta<' in html
    assert "Reconhecida 27/10 09:40" in html and "varredura do Fracttal às <b>09:43</b>" in html
    # a OS abre no card do Fracttal, com o id e o status que o card espera
    assert 'data-wo="900101"' in html and 'data-status="Em Processo"' in html and "NexusOsCard" in html
    assert "30 de tipos que o COS não abre, 1 da usina de teste e" in html
    html = logado.get("/t/cos/os-abertas?situacao=concluida").get_data(as_text=True)
    assert 'data-folio="102"' in html and 'cn-pill cn-ok">100%<' in html and 'data-folio="101"' not in html


def test_a_tela_sem_fonte_e_com_o_andamento_antigo(ligada, app, logado, monkeypatch):
    _servir(monkeypatch, AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá", 404))
    html = logado.get("/t/cos/os-abertas").get_data(as_text=True)
    assert "Ainda não tem a rota das OS abertas" in html or "ainda não tem a rota das OS abertas" in html
    app.config.update(NEXUS_COS_ANDAMENTO_URL="", NEXUS_COS_ANDAMENTO_CHAVE="")
    assert "não está ligada neste servidor" in logado.get("/t/cos/os-abertas").get_data(as_text=True)


def test_a_tela_vem_depois_da_passagem_de_turno():
    from nexus.torres.cos import TORRE
    ids = [t.id for t in TORRE.telas]
    assert ids.index("os-abertas") == ids.index("turno") + 1


def test_nao_ha_nome_de_pessoa_na_tela(ligada, logado, monkeypatch):
    """O Andamento não manda nome nem texto livre; se um dia mandar, a tela não os mostra (só lê os campos que conhece)."""
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    com_nome = [_os(201, responsavel="Pessoa Ficticia", criada_por="Outra Ficticia", descricao="ligar para 99999-0000")]
    _servir(monkeypatch, _dados(com_nome))
    html = logado.get("/t/cos/os-abertas").get_data(as_text=True)
    assert 'data-folio="201"' in html
    assert "Ficticia" not in html and "99999-0000" not in html


def test_o_horario_da_tela_e_o_de_brasilia():
    i = _painel(situacao="todas").itens[0]
    assert isinstance(i["criada"], datetime) and i["criada"].strftime("%d/%m/%Y %H:%M") == "01/06/2026 10:00"
