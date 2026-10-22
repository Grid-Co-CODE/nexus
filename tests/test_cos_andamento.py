"""Torre COS: Ronda padronizada e Parede de eventos pelo Andamento da Ronda COS (22/10/2026).

O Andamento é a fonte; o Nexus só lê (`GET /api/nexus/<cliente>`, chave de máquina no cabeçalho) e mostra. Nada aqui
vai à rede: a resposta do Andamento é falsa, e o teste que liga a fonte troca `_pedir` ou o `urlopen`."""
import io
import json
from datetime import datetime

import pytest

from nexus.cos import andamento as AND

CHAVE = "chave-de-teste-do-andamento"


def _dados(cliente="Cliente A", **mudar):
    d = {
        "versao": 1, "cliente": cliente, "gerado_em": "2026-10-22T13:04:00.000000-03:00",
        "fotografia_anterior": "2026-10-22T13:00:00.000000-03:00", "volta": "normalizada",
        "placar": {"usinas": 3, "critico_alto": 1, "atencao": 1, "operando": 1},
        "problemas": [
            {"id": "rede", "nome": "Rede concessionária", "vermelhas": 1, "amarelas": 0, "novas": 1, "voltas": 0},
            {"id": "inv", "nome": "Inversores", "vermelhas": 0, "amarelas": 1, "novas": 0, "voltas": 1},
            {"id": "com", "nome": "Comunicação", "vermelhas": 0, "amarelas": 0, "novas": 0, "voltas": 0},
        ],
        "desde_a_anterior": {"novas": 1, "atualizadas": 0, "voltas": 1},
        "usinas": [
            {"id": 3, "codigo": "EX-OK300", "cod": "OK300", "nome": "Usina Exemplo Verde", "cidade": "Cidade C", "uf": "SP",
             "cluster": "", "status": "ok", "status_rotulo": "Operando", "cor": "verde", "problema": None, "ocorrencias": []},
            {"id": 2, "codigo": "EX-AMA200", "cod": "AMA200", "nome": "Usina Exemplo Amarela", "cidade": "Cidade B",
             "uf": "PR", "cluster": "", "status": "medio", "status_rotulo": "Médio", "cor": "amar", "problema": "inv",
             "ocorrencias": [{"os": "90002", "registro": "r2", "severidade": "Médio", "severidade_classe": "medio",
                              "tipo_tarefa": "Corretiva", "tipo_falha": "Inversor desligado", "problema": "inv",
                              "equipamentos": ["Inversor 3"], "falha": "Inversor 3 sem gerar", "impacto": None,
                              "protecao": None, "abertura": "2026-10-21T09:00:00-03:00", "dias_aberta": 1,
                              "etapa": "Técnico acionado", "aguardando": [], "ultima_nota": None}]},
            {"id": 1, "codigo": "EX-VER100", "cod": "VER100", "nome": "Usina Exemplo Vermelha", "cidade": "Cidade A",
             "uf": "BA", "cluster": "", "status": "crit", "status_rotulo": "Crítico", "cor": "verm", "problema": "rede",
             "ocorrencias": [{"os": "90001", "registro": "r1", "severidade": "Crítico", "severidade_classe": "crit",
                              "tipo_tarefa": "Religamento", "tipo_falha": "Desligamento de usina", "problema": "rede",
                              "equipamentos": [], "falha": "Usina desligada, trip 27", "impacto": "Geração total interrompida",
                              "protecao": "27", "abertura": "2026-10-22T13:02:00-03:00", "dias_aberta": 0,
                              "etapa": "Identificada", "aguardando": ["concessionária"],
                              "ultima_nota": {"quando": "2026-10-22T13:03:10.000000-03:00",
                                              "texto": "Chamado aberto na concessionária."}},
                             {"os": "R-abc123", "registro": "r4", "severidade": "Alto", "severidade_classe": "alto",
                              "tipo_tarefa": None, "tipo_falha": "Falha de comunicação", "problema": "com",
                              "equipamentos": [], "falha": "Sem comunicação", "impacto": None, "protecao": None,
                              "abertura": "2026-10-22T13:04:00-03:00", "dias_aberta": 0, "etapa": "Identificada",
                              "aguardando": [], "ultima_nota": None}]},
        ],
        "eventos": [
            {"quando": "2026-10-22T13:02:00.000000-03:00", "retro": None, "usina_id": 1, "cod": "VER100",
             "nome": "Usina Exemplo Vermelha", "os": "90001", "problema": "rede", "situacao": "nova", "texto": "Usina desligada, trip 27"},
            {"quando": "2026-10-22T12:40:00.000000-03:00", "retro": None, "usina_id": 2, "cod": "AMA200",
             "nome": "Usina Exemplo Amarela", "os": "90003", "problema": "inv", "situacao": "normalizada", "texto": "Religamento Remoto."},
            {"quando": "2026-10-22T03:10:00.000000-03:00", "retro": None, "usina_id": 2, "cod": "AMA200",
             "nome": "Usina Exemplo Amarela", "os": "90002", "problema": "inv", "situacao": "atualizada", "texto": "Técnico a caminho."},
            {"quando": "2026-10-19T10:00:00.000000-03:00", "retro": None, "usina_id": 2, "cod": "AMA200",
             "nome": "Usina Exemplo Amarela", "os": "90002", "problema": "inv", "situacao": "nova", "texto": "Inversor 3 sem gerar"},
        ],
        "fotografias": [
            {"hora": "2026-10-22T13:00:00-03:00", "regiao": "SE", "regiao_rotulo": "Sudeste", "estado": "ENVIADO", "enviada_em": "2026-10-22T13:00:20-03:00"},
            {"hora": "2026-10-22T13:00:00-03:00", "regiao": "NNE", "regiao_rotulo": "Nordeste e Norte", "estado": "RETIDO", "enviada_em": None},
            {"hora": "2026-10-22T12:00:00-03:00", "regiao": None, "regiao_rotulo": None, "estado": "ENVIADO", "enviada_em": "2026-10-22T12:00:15-03:00"},
        ],
    }
    d.update(mudar)
    return d


AGORA = datetime(2026, 10, 22, 13, 5, tzinfo=AND._BRT)


@pytest.fixture(autouse=True)
def _limpa():
    AND.limpar_cache()
    yield
    AND.limpar_cache()


@pytest.fixture
def ligada(app):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002", NEXUS_COS_ANDAMENTO_CHAVE=CHAVE,
                      NEXUS_COS_ANDAMENTO_CLIENTES="Cliente A,Cliente B")
    return app


def _servir(monkeypatch, respostas: dict):
    """Troca o pedido HTTP: `respostas` diz o que cada caminho devolve (um dict, ou uma exceção a lançar)."""
    pedidos = []

    def pedir(f, caminho):
        pedidos.append(caminho)
        r = respostas.get(caminho)
        if isinstance(r, Exception):
            raise r
        if r is None:
            raise AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá")
        return r
    monkeypatch.setattr(AND, "_pedir", pedir)
    return pedidos


# --- a regra pura -----------------------------------------------------------------------------------------------------

def test_a_parede_ordena_do_mais_novo_e_respeita_a_janela():
    lt = AND.Leitura("Cliente A", _dados())
    p = AND.eventos([lt], AGORA, "24h")
    assert [(e["os"], e["situacao"]) for e in p["itens"]] == [("90001", "nova"), ("90003", "normalizada"), ("90002", "atualizada")]
    assert p["itens"][0]["hora"] == "13:02" and p["itens"][0]["hoje"] is True
    assert p["itens"][0]["problema_nome"] == "Rede concessionária" and p["itens"][0]["tom"] == "critico"
    assert p["itens"][0]["desde_a_anterior"] is True and p["itens"][1]["desde_a_anterior"] is False
    assert [e["os"] for e in AND.eventos([lt], AGORA, "8h")["itens"]] == ["90001", "90003"]
    assert len(AND.eventos([lt], AGORA, "7d")["itens"]) == 4
    assert AND.eventos([lt], AGORA, "qualquer")["janela"] == AND.JANELA_PADRAO     # janela desconhecida: a padrão


def test_a_parede_filtra_e_conta_antes_do_filtro():
    lt = AND.Leitura("Cliente A", _dados())
    p = AND.eventos([lt], AGORA, "24h", problema="inv")
    assert [e["os"] for e in p["itens"]] == ["90003", "90002"]
    assert p["contagem"]["problema"] == {"rede": 1, "inv": 2}                 # o número de cada filtro, antes dele
    assert p["contagem"]["situacao"] == {"nova": 1, "normalizada": 1, "atualizada": 1}
    assert [e["os"] for e in AND.eventos([lt], AGORA, "24h", situacao="normalizada")["itens"]] == ["90003"]


def test_a_parede_junta_os_clientes_e_o_filtro_de_cliente():
    a = AND.Leitura("Cliente A", _dados())
    b = AND.Leitura("Cliente B", _dados("Cliente B", eventos=[
        {"quando": "2026-10-22T13:04:00-03:00", "retro": None, "usina_id": 9, "cod": "BBB900", "nome": "Usina Exemplo B",
         "os": "90009", "problema": "com", "situacao": "nova", "texto": "Sem comunicação"}]))
    sem = AND.Leitura("Cliente C", None, erro="o Andamento não respondeu")
    assert [e["cliente"] for e in AND.eventos([a, b, sem], AGORA, "24h")["itens"]][:2] == ["Cliente B", "Cliente A"]
    assert {e["cliente"] for e in AND.eventos([a, b], AGORA, "24h", cliente="Cliente B")["itens"]} == {"Cliente B"}


def test_a_ronda_lista_as_usinas_com_ocorrencia_vermelhas_primeiro():
    r = AND.ronda(AND.Leitura("Cliente A", _dados()))
    assert [u["cod"] for u in r["usinas"]] == ["VER100", "AMA200"]
    assert [u["tom"] for u in r["usinas"]] == ["critico", "alerta"]
    assert r["usinas"][0]["ocorrencias"][0]["tom"] == "critico" and r["usinas"][1]["ocorrencias"][0]["tom"] == "alerta"
    assert [o["os_rotulo"] for o in r["usinas"][0]["ocorrencias"]] == ["OS 90001", "ainda sem OS"]
    assert r["usinas"][0]["ocorrencias"][0]["nota"]["quando"] == "22/10 13:03"
    assert [p["id"] for p in r["problemas"]] == ["rede", "inv"]                # problema zerado sai do quadro
    assert r["gerado_em"].strftime("%H:%M") == "13:04" and r["anterior"].strftime("%H:%M") == "13:00"
    assert AND.ronda(AND.Leitura("Cliente A", None)) is None


def test_as_fotografias_uma_linha_por_hora_com_cada_regiao():
    f = AND.fotografias_por_hora(_dados())
    assert [x["rotulo"] for x in f] == ["22/10 13:00", "22/10 12:00"]
    assert [(e["regiao"], e["rotulo"], e["enviada"]) for e in f[0]["envios"]] == [
        ("Nordeste e Norte", "retida até zerar as pendências", ""), ("Sudeste", "enviada", "13:00")]
    assert f[0]["tom"] == "alerta" and f[1]["tom"] == "ok"
    assert f[1]["envios"][0]["regiao"] == "Todas as usinas"


def test_outra_versao_do_contrato_e_recusada():
    with pytest.raises(AND.FonteErro, match="versão 2"):
        AND.validar(_dados(versao=2))
    with pytest.raises(AND.FonteErro, match="usinas"):
        AND.validar({**_dados(), "usinas": None})


# --- a leitura --------------------------------------------------------------------------------------------------------

def test_sem_configuracao_nos_testes_nao_vai_a_rede(app, monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("foi à rede")
    monkeypatch.setattr(AND.urllib.request, "urlopen", proibido)
    # mesmo com a fonte no .env da máquina: nos testes vale só a config do app
    monkeypatch.setattr(AND, "ler_ambiente", lambda: {AND.URL: "http://andamento.exemplo:3002", AND.CHAVE: "k"})
    assert AND.fonte(app.config).ligada is False
    assert AND.clientes(app.config) == ([], "")
    assert "não está ligada" in AND.ler(app.config, "Cliente A").erro


def test_o_pedido_leva_a_chave_no_cabecalho_e_o_cliente_no_caminho(ligada, monkeypatch):
    vistos = []

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout):
        vistos.append((req.full_url, req.get_header("X-nexus-chave"), timeout))
        return Resposta(json.dumps(_dados("Apolo Energia")).encode())
    monkeypatch.setattr(AND.urllib.request, "urlopen", urlopen)
    lt = AND.ler(ligada.config, "Apolo Energia")
    assert lt.dados["cliente"] == "Apolo Energia" and not lt.erro
    assert vistos == [("http://andamento.exemplo:3002/api/nexus/Apolo%20Energia", CHAVE, AND.TIMEOUT_S)]
    AND.ler(ligada.config, "Apolo Energia")
    assert len(vistos) == 1                                                    # 30 s de cópia em memória


def test_o_erro_diz_o_que_aconteceu_e_nunca_a_chave(ligada, monkeypatch):
    def urlopen(req, timeout):
        raise AND.urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
    monkeypatch.setattr(AND.urllib.request, "urlopen", urlopen)
    lt = AND.ler(ligada.config, "Cliente A")
    assert lt.dados is None and lt.erro == "o Andamento recusou a chave do Nexus" and CHAVE not in lt.erro


def test_na_falha_a_ultima_leitura_boa_fica_dita_velha(ligada, monkeypatch):
    _servir(monkeypatch, {"/api/nexus/Cliente%20A": _dados()})
    assert AND.ler(ligada.config, "Cliente A").velha is False
    _servir(monkeypatch, {"/api/nexus/Cliente%20A": AND.FonteErro("o Andamento não respondeu (URLError)")})
    monkeypatch.setattr(AND, "TTL_S", -1)                                     # a cópia venceu
    lt = AND.ler(ligada.config, "Cliente A")
    assert lt.velha is True and lt.dados["cliente"] == "Cliente A" and "não respondeu" in lt.erro


def test_sem_a_lista_na_configuracao_os_clientes_vem_do_andamento(ligada, monkeypatch):
    ligada.config["NEXUS_COS_ANDAMENTO_CLIENTES"] = ""
    pedidos = _servir(monkeypatch, {"/api/nexus/clientes": {"clientes": ["Cliente A", "Cliente B"]}})
    assert AND.clientes(ligada.config) == (["Cliente A", "Cliente B"], "")
    AND.clientes(ligada.config)
    assert pedidos == ["/api/nexus/clientes"]                                   # 5 min de cópia


# --- as telas ---------------------------------------------------------------------------------------------------------

def test_as_telas_sem_a_fonte_dizem_que_ela_nao_esta_ligada(logado):
    for tela in ("ronda", "eventos"):
        html = logado.get(f"/t/cos/{tela}").get_data(as_text=True)
        assert "ainda não está ligada neste servidor" in html and "NEXUS_COS_ANDAMENTO_CHAVE" in html


def test_a_tela_da_ronda_mostra_o_cliente_e_as_usinas(ligada, logado, monkeypatch):
    _servir(monkeypatch, {"/api/nexus/Cliente%20A": _dados(), "/api/nexus/Cliente%20B": _dados("Cliente B")})
    r = logado.get("/t/cos/ronda")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Usina Exemplo Vermelha" in html and "OS 90001" in html and "Chamado aberto na concessionária." in html
    assert "Usina Exemplo Verde" not in html                                    # verde não entra na lista
    assert "ainda sem OS" in html and "R-abc123" not in html and "22/10 13:03" in html
    assert "retida até zerar as pendências" in html and "Rede concessionária" in html
    assert 'aria-current="page">Cliente A<' in html
    assert CHAVE not in html
    html_b = logado.get("/t/cos/ronda?cliente=Cliente%20B").get_data(as_text=True)
    assert 'aria-current="page">Cliente B<' in html_b
    assert 'aria-current="page">Cliente A<' in logado.get("/t/cos/ronda?cliente=Outro").get_data(as_text=True)


def test_a_tela_da_ronda_com_o_andamento_fora_do_ar(ligada, logado, monkeypatch):
    _servir(monkeypatch, {})
    html = logado.get("/t/cos/ronda").get_data(as_text=True)
    assert "O Andamento não tem este cliente" in html and CHAVE not in html


def test_a_parede_mostra_os_eventos_e_filtra(ligada, logado, monkeypatch):
    _servir(monkeypatch, {"/api/nexus/Cliente%20A": _dados(), "/api/nexus/Cliente%20B": _dados("Cliente B", eventos=[])})
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    html = logado.get("/t/cos/eventos?janela=7d").get_data(as_text=True)
    assert html.count("<tr") - 1 == 4                                            # o cabeçalho e as quatro linhas
    assert "Usina Exemplo Vermelha" in html and "Religamento Remoto." in html
    so = logado.get("/t/cos/eventos?janela=7d&situacao=normalizada").get_data(as_text=True)
    assert "Religamento Remoto." in so and "Técnico a caminho." not in so
    assert CHAVE not in html


def test_a_parede_diz_qual_cliente_ficou_de_fora(ligada, logado, monkeypatch):
    _servir(monkeypatch, {"/api/nexus/Cliente%20A": _dados()})
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    html = logado.get("/t/cos/eventos").get_data(as_text=True)
    assert "Cliente B: o Andamento não tem este cliente" in html and "Os eventos dele ficam de fora" in html
    assert "Usina Exemplo Vermelha" in html

