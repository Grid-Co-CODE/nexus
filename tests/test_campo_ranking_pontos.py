"""Ranking de pontos (13/10/2026, Levi: "Quero que traga o ranking de pontos dos técnicos para o Nexus. Cria uma seção de
Ranking de Pontos no App de Campo!"). O placar é o do ciclo do App (`_ciclo_v2`, régua PLACAR_V2), que o App publica no
livro `ranking_app_campo`; o Nexus mostra o que veio, sem recalcular. Pessoas de mentira, no banco falso do
test_campo_visao; a pessoa chega como o código (HMAC) do e-mail, e o nome sai do cadastro do App."""
import json
import re
from pathlib import Path

import pytest

from nexus.campo import visao
from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.dados import catalogo
from test_campo_visao import CHAVE, _aba, banco  # noqa: F401  (fixture)

PESSOAS = {"ana@exemplo.test": "Ana Maria Souza", "bruno@exemplo.test": "Bruno Lima", "carla@exemplo.test": "Carla Dias",
           "davi@exemplo.test": "Davi Rocha", "eva@exemplo.test": "Eva Prado"}
REGUA = {"Piso da nota": 70, "Teto de tarefas": 70, "Anulação máxima": 35, "Teto das rondas (pts)": 250,
         "Mínimo de tarefas": 10, "Mínimo de cumprimento (%)": 70, "Bônus programação (%)": 20,
         "Bônus preventivas (%)": 25}
SEM_DONO = "f" * 24


def _linha(mes, email, total, posicao=None, regiao="SP Norte 01", motivo="", regua="ligado", **extra):
    linha = {"Mês": mes, "Posição": posicao, "No ciclo": "Sim" if posicao else "Não", "Motivo fora do ciclo": motivo,
             "Técnico (HMAC)": codigo_da_pessoa(CHAVE, email) if email else SEM_DONO, "Região": regiao,
             "Total (pts)": total, "Tarefas (pts)": total - 300, "Rondas (pts)": 200, "Bônus (pts)": 100,
             "Bônus programação (pts)": 60, "Bônus preventivas (pts)": 40, "Tarefas registradas": 40, "OS distintas": 30,
             "Tarefas contadas": 38, "Acima do teto": 0, "Abaixo do piso": 2, "Anuladas": 2, "Devolvidas": 1,
             "Nota média": 88, "Rondas": 9, "Rondas no teto": "Não", "Programado": 20, "Concluído": 18,
             "Cumprimento (%)": 90, "Pontualidade (%)": 75, "Sequência (dias)": 4, "Sem GPS": 1, "Régua": regua,
             "Calculado em": "2026-10-13T21:25:00Z", **REGUA}
    linha.update(extra)
    return linha


OUTUBRO = [_linha("2026-10", "bruno@exemplo.test", 1137, 2), _linha("2026-10", "ana@exemplo.test", 1480, 1),
           _linha("2026-10", "carla@exemplo.test", 905, 3, regiao="SC Oeste 01"),
           _linha("2026-10", "davi@exemplo.test", 640, 4, regiao="SC Oeste 01"),
           _linha("2026-10", "eva@exemplo.test", 210, motivo="6 tarefas registradas — o mínimo é 10", regiao="SC Oeste 01")]
SETEMBRO = [_linha("2026-09", "carla@exemplo.test", 1500, 1, regiao="SC Oeste 01"),
            _linha("2026-09", "ana@exemplo.test", 1200, 2)]


@pytest.fixture
def ranking(banco, app):          # noqa: F811
    Path(app.config["NEXUS_CAMPO_IDENTIDADES"]).write_text(
        json.dumps({"porEmail": {e: {"nome": n} for e, n in PESSOAS.items()}}), encoding="utf-8")
    _aba(banco, "ranking_app_campo", "Ranking", OUTUBRO + SETEMBRO)
    visao.limpar()
    return banco


def _texto(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ── a conta: o placar como o App publicou ────────────────────────────────────────────────────────────────────────────
def test_o_placar_vem_como_o_app_publicou_na_ordem_dele(ranking):
    d = visao.ranking_pontos().dados
    assert [m["mes"] for m in d["meses"]] == ["2026-10", "2026-09"]            # o mais novo primeiro
    out = d["meses"][0]
    assert [(p["posicao"], p["tecnico"], p["total"]) for p in out["classificacao"]] == [
        (1, "Ana Souza", 1480), (2, "Bruno Lima", 1137), (3, "Carla Dias", 905), (4, "Davi Rocha", 640)]
    assert [(p["tecnico"], p["motivo"]) for p in out["fora"]] == [("Eva Prado", "6 tarefas registradas — o mínimo é 10")]
    assert out["vale"] == "ligado" and out["regua"]["piso"] == 70 and out["regua"]["ronda_teto"] == 250
    assert out["calculado_em"] == "2026-10-13T21:25:00Z" and d["sem_nome"] == 0


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_tela_mostra_o_podio_a_classificacao_e_quem_esta_fora(ranking, logado):
    html = logado.get("/t/campo/ranking").get_data(as_text=True)
    t = _texto(html)
    podio = _texto(html.split('class="rk-podio"', 1)[1].split('class="cn-numeros"', 1)[0])
    assert re.search(r"1º lugar Ana Souza SP Norte 01 1\.480 pts .*2º lugar Bruno Lima .*1\.137 pts .*3º lugar Carla Dias", podio)
    assert "Davi Rocha" not in podio                                               # o pódio são três
    assert "No ciclo 4 técnicos classificados" in t and "Fora do ciclo 1 " in t and "Líder 1.480 pontos" in t
    assert "Média no ciclo 1.040 pontos por técnico classificado" in t           # (1480+1137+905+640)/4
    fora = _texto(html.split("Fora do ciclo</h2>", 1)[1])
    assert "Eva Prado SC Oeste 01 210 40 90% 6 tarefas registradas — o mínimo é 10" in fora
    # a régua do mês, com os números que o App publicou
    regua = _texto(html.split("Como o App calcula.", 1)[1])
    for trecho in ("piso (70)", "as 70 melhores", "(até 35)", "teto de 250 pontos", "+20% com a programação",
                   "até +25% pelas preventivas", "menos de 10 tarefas", "menos de 70% do programado"):
        assert trecho in regua, trecho
    assert "calculado em 13/10 18:25" in t                                        # 21:25Z = 18:25 de Brasília
    assert "a régua deste placar está" not in t.lower()                           # ligada: sem aviso


def test_o_mes_anterior_e_a_regiao_mantem_a_posicao_do_ciclo(ranking, logado):
    t = _texto(logado.get("/t/campo/ranking?mes=2026-09").get_data(as_text=True))
    assert "1º lugar Carla Dias" in t and "2º lugar Ana Souza" in t and "Bruno Lima" not in t
    html = logado.get("/t/campo/ranking?regiao=SC+Oeste+01").get_data(as_text=True)
    t = _texto(html)
    assert "Ana Souza" not in t and "Bruno Lima" not in t
    # a posição é a do ciclo inteiro (a que o técnico vê no App), mesmo com a região escolhida
    assert "3º lugar no ciclo Carla Dias" in t and "4º lugar no ciclo Davi Rocha" in t
    assert '<option value="SC Oeste 01" selected>' in html
    # região que não existe no mês = todas
    assert "Ana Souza" in _texto(logado.get("/t/campo/ranking?regiao=Nenhuma").get_data(as_text=True))


def test_codigo_sem_dono_fica_sem_nome_e_nunca_aparece(ranking, logado):
    _aba(ranking, "ranking_app_campo", "Ranking", OUTUBRO + [_linha("2026-10", None, 300, 5)])
    visao.limpar()
    html = logado.get("/t/campo/ranking").get_data(as_text=True)
    assert SEM_DONO not in html and codigo_da_pessoa(CHAVE, "ana@exemplo.test") not in html
    assert "1 linha do placar veio sem nome" in _texto(html)


def test_regua_em_sombra_avisa_que_o_tecnico_ve_a_de_antes(ranking, logado):
    _aba(ranking, "ranking_app_campo", "Ranking", [_linha("2026-10", "ana@exemplo.test", 900, 1, regua="sombra")])
    visao.limpar()
    t = _texto(logado.get("/t/campo/ranking").get_data(as_text=True))
    assert "A régua deste placar está sombra no App: os técnicos ainda veem a pontuação de antes." in t


def test_sem_o_livro_a_tela_explica(banco, logado):    # noqa: F811
    visao.limpar()
    t = _texto(logado.get("/t/campo/ranking").get_data(as_text=True))
    assert "O ranking ainda não chegou do App." in t and "rk-podio" not in t


# ── o menu, o endereço e o catálogo ──────────────────────────────────────────────────────────────────────────────────
def test_o_ranking_de_pontos_e_uma_tela_do_campo_e_o_endereco_nao_cai_mais_na_central(app, logado):
    from nexus.torres.campo import TELAS_QUE_SAIRAM, TORRE
    assert TORRE.tela("ranking").nome == "Ranking de pontos" and "ranking" not in TELAS_QUE_SAIRAM
    menu = logado.get("/t/campo/zeladoria").get_data(as_text=True)
    assert 'href="/t/campo/ranking"' in menu and "Ranking de pontos" in menu
    assert logado.get("/t/campo/ranking").status_code == 200
    for saiu in ("os", "imagens"):                                                 # essas continuam levando à Central
        r = logado.get(f"/t/campo/{saiu}")
        assert r.status_code == 302 and r.headers["Location"].endswith("/t/campo/atencao")


def test_o_livro_do_ranking_esta_no_catalogo_de_dados():
    f = next(x for x in catalogo.FATOS if x.id == "ranking_pontos")
    assert f.livro == "ranking_app_campo · Ranking" and f.area == "campo" and f.tipo == "snapshot_acumulado"
    assert f.chave == ("Mês", "Técnico (HMAC)") and f.dims["pessoa"][0] == "hmac"
    assert all(catalogo.medida_valida(m) for m in f.medidas)


# ── o contrato com o App ─────────────────────────────────────────────────────────────────────────────────────────────
# As colunas que o App publica, na ordem dele (o NEXUS_COLUNAS["ranking"] do function_app.py; o pacote
# C:\GridcoBuild\app-campo-docs\_propostas\ranking-pontos-nexus, cujo teste tem a MESMA lista). A tela lê pelo nome:
# coluna escrita errada aqui virava zero na tela, sem erro. Coluna nova só no FIM, dos dois lados.
COLUNAS_DO_APP = ["Mês", "Posição", "No ciclo", "Motivo fora do ciclo", "Técnico (HMAC)", "Região", "Total (pts)",
                  "Tarefas (pts)", "Rondas (pts)", "Bônus (pts)", "Bônus programação (pts)", "Bônus preventivas (pts)",
                  "Tarefas registradas", "OS distintas", "Tarefas contadas", "Acima do teto", "Abaixo do piso",
                  "Anuladas", "Devolvidas", "Nota média", "Rondas", "Rondas no teto", "Programado", "Concluído",
                  "Cumprimento (%)", "Pontualidade (%)", "Sequência (dias)", "Sem GPS", "Régua", "Calculado em",
                  "Piso da nota", "Teto de tarefas", "Anulação máxima", "Teto das rondas (pts)", "Mínimo de tarefas",
                  "Mínimo de cumprimento (%)", "Bônus programação (%)", "Bônus preventivas (%)"]


def test_a_tela_so_le_colunas_que_o_app_publica():
    import inspect
    fonte = inspect.getsource(visao._pessoa_do_ranking) + inspect.getsource(visao.ranking_pontos)
    lidas = set(re.findall(r'(?:r\.get|n)\("([^"]+)"\)', fonte)) | {c for _k, c in visao._REGUA_RANKING}
    assert lidas and lidas <= set(COLUNAS_DO_APP), lidas - set(COLUNAS_DO_APP)
    # e o livro de mentira destes testes é o do App, na ordem dele
    assert list(_linha("2026-10", "ana@exemplo.test", 100, 1).keys()) == COLUNAS_DO_APP
