"""Mapa de equipe: o gravador em lote (08/11/2026). Banco em memória (`ApiPGFalsa`); coordenadas, pessoas e chaves de
mentira. O relógio é o da rodada (argumento), nunca o do sistema."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo.equipe import (ABA_ACESSOS, ABA_APARELHOS, ABA_DESLOC, ABA_PONTOS, CAB_ACESSOS, CAB_DESLOC, CAB_PONTOS,
                                LIVRO_ACESSOS, LIVRO_APARELHOS, livro_deslocamentos, livro_pontos)
from nexus.campo.equipe import pontos as PT
from nexus.campo.equipe import servico as S
from nexus.campo.equipe.gravador import Gravador

AGORA = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)       # 12:00 em Brasília
USINAS = {"1": (-23.00, -46.00, "SP"), "2": (-23.10, -46.00, "SP")}


@pytest.fixture
def ambiente(app, tmp_path):
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="token-de-teste")
    app.extensions["nexus_dados_sessao"] = api
    srv = S.Servico(app, tmp_path, Cofre(gerar_chave()), agora=AGORA)
    g = Gravador(app, srv, usinas=lambda: USINAS)
    yield api, srv, g
    app.extensions.pop("nexus_dados_sessao", None)


def _ponto(srv, pessoa, minutos_antes, lat, lon, agora=AGORA):
    t = int((agora - timedelta(minutes=minutos_antes)).timestamp() * 1000)
    lote = {"fuso": -180, "pontos": [{"t": t, "lat": lat, "lon": lon, "prec": 10, "mov": True}]}
    srv.diario.acrescentar(PT.aceitar(pessoa, lote, agora, srv.cofre))


def _livro_com(api, livro, aba, cab, valores):
    api.workbooks[livro] = {}
    api._id(livro, aba)["linhas"] = [{"headers": list(cab), "values": v} for v in valores]


def test_o_gravador_publica_so_o_dia_que_mudou(ambiente):
    api, srv, g = ambiente
    _ponto(srv, 7, 60, -23.0, -46.0)
    g.rodada(AGORA)
    antes = api.syncs
    assert len(api.linhas(livro_pontos(AGORA.date()), ABA_PONTOS)) == 1
    g.rodada(AGORA + timedelta(minutes=5))              # nada novo: nenhuma gravação
    assert api.syncs == antes
    _ponto(srv, 7, 30, -23.001, -46.0)
    g.rodada(AGORA + timedelta(minutes=10))
    assert api.syncs > antes
    assert len(api.linhas(livro_pontos(AGORA.date()), ABA_PONTOS)) == 2


def test_o_gravador_nao_publica_dia_vazio_por_cima(ambiente):
    api, srv, g = ambiente
    livro = livro_pontos(AGORA.date())
    _livro_com(api, livro, ABA_PONTOS, CAB_PONTOS, [["Pabc", 20261108, "2026-11-08T13:00:00Z", 7, "c"]])
    g.rodada(AGORA)
    assert api.syncs == 0
    assert len(api.linhas(livro, ABA_PONTOS)) == 1


def test_diario_com_menos_que_o_banco_nao_encolhe_o_dia(ambiente, caplog):
    api, srv, g = ambiente
    livro = livro_pontos(AGORA.date())
    _livro_com(api, livro, ABA_PONTOS, CAB_PONTOS,
               [[f"P{i:02d}", 20261108, "2026-11-08T13:00:00Z", 7, "c"] for i in range(3)])
    _ponto(srv, 7, 60, -23.0, -46.0)                    # 1 ponto no diário x 3 no banco
    with caplog.at_level("WARNING"):
        g.rodada(AGORA)
    assert api.syncs == 0 and len(api.linhas(livro, ABA_PONTOS)) == 3
    assert "menos pontos que o banco" in caplog.text


def test_o_livro_do_dia_nao_tem_coordenada_em_claro(ambiente):
    api, srv, g = ambiente
    _ponto(srv, 7, 60, -23.123456, -46.654321)
    g.rodada(AGORA)
    linhas = api.linhas(livro_pontos(AGORA.date()), ABA_PONTOS)
    assert list(linhas[0]) == list(CAB_PONTOS)
    texto = json.dumps(linhas)
    assert "23.123456" not in texto and "46.654321" not in texto and '"lat"' not in texto
    # e a cifra abre, de volta, na coordenada
    dado = json.loads(srv.cofre.decifrar(linhas[0]["cifra"], f"equipe/ponto/{linhas[0]['ponto_id']}"))
    assert dado["lat"] == -23.123456


def test_o_diario_local_com_mais_de_7_dias_some(ambiente):
    api, srv, g = ambiente
    velho = AGORA - timedelta(days=6, hours=2)          # dentro da guarda quando entra
    _ponto(srv, 7, 0, -23.0, -46.0, agora=velho)
    assert srv.diario.do_dia(velho.date())
    g.rodada(AGORA + timedelta(days=3))                 # 3 dias depois já passou de 7
    assert srv.diario.do_dia(velho.date()) == []


def test_os_deslocamentos_do_mes_nao_duplicam_ao_republicar(ambiente):
    api, srv, g = ambiente
    _ponto(srv, 7, 90, -23.0, -46.0)
    _ponto(srv, 7, 60, -23.05, -46.0)
    _ponto(srv, 7, 30, -23.1, -46.0)
    g.rodada(AGORA)
    livro = livro_deslocamentos(AGORA.date())
    linhas = api.linhas(livro, ABA_DESLOC)
    assert len(linhas) == 1 and (linhas[0]["usina_id_saida"], linhas[0]["usina_id_chegada"]) == (1, 2)
    antes = api.syncs
    g.rodada(AGORA + timedelta(minutes=5))              # o mesmo gravador: nada mudou, nada grava
    assert api.syncs == antes
    g2 = Gravador(g._app, srv, usinas=lambda: USINAS)   # reinício: a memória do gravador se perdeu
    g2.rodada(AGORA + timedelta(minutes=10))
    assert len(api.linhas(livro, ABA_DESLOC)) == 1      # o mês relido já tinha o trecho: não duplica


def test_o_mes_une_o_que_o_banco_ja_tinha_com_o_recalculado(ambiente):
    api, srv, g = ambiente
    livro = livro_deslocamentos(AGORA.date())
    _livro_com(api, livro, ABA_DESLOC, CAB_DESLOC, [
        ["Dantigo0000", 20261103, 9, 2, 1, "2026-11-03T12:00:00Z", "2026-11-03T12:30:00Z", 30, 11.1]])
    _ponto(srv, 7, 90, -23.0, -46.0)
    _ponto(srv, 7, 30, -23.1, -46.0)
    g.rodada(AGORA)
    ids = {l["deslocamento_id"] for l in api.linhas(livro, ABA_DESLOC)}
    assert len(ids) == 2 and "Dantigo0000" in ids


def test_os_eventos_de_aparelho_entram_sem_apagar_os_que_ja_estavam(ambiente):
    api, srv, g = ambiente
    srv.chaveiro.emitir(7, "cel-1", "app", AGORA)
    g.rodada(AGORA)
    srv.chaveiro.emitir(8, "cel-2", "app", AGORA)
    g.rodada(AGORA + timedelta(minutes=5))
    linhas = api.linhas(LIVRO_APARELHOS, ABA_APARELHOS)
    assert [l["pessoa_id"] for l in linhas] == [7, 8]
    assert srv.chaveiro.eventos_novos() == []           # a fila foi esvaziada pelo gravador


def test_evento_que_nao_gravou_volta_a_fila(ambiente, monkeypatch):
    api, srv, g = ambiente
    srv.chaveiro.emitir(7, "cel-1", "app", AGORA)
    srv.registro.acrescentar("abriu_mapa", 1, "hmac-x", None, None, AGORA)

    with monkeypatch.context() as m:
        def cai(*a, **k):
            raise RuntimeError("banco fora")
        m.setattr("nexus.dados.livros.publicar", cai)
        g.rodada(AGORA)                                 # nenhum passo derruba a rodada
    assert api.syncs == 0
    g.rodada(AGORA + timedelta(minutes=5))              # o banco voltou: as linhas guardadas entram
    assert len(api.linhas(LIVRO_APARELHOS, ABA_APARELHOS)) == 1
    assert len(api.linhas(LIVRO_ACESSOS, ABA_ACESSOS)) == 1


def test_o_registro_de_acessos_vira_linhas_do_livro(ambiente):
    api, srv, g = ambiente
    srv.registro.acrescentar("abriu_rota", 1, "hmac-x", 7, 2, AGORA)
    g.rodada(AGORA)
    (l,) = api.linhas(LIVRO_ACESSOS, ABA_ACESSOS)
    assert list(l) == list(CAB_ACESSOS)
    assert (l["acao"], l["pessoa_hmac"], l["alvo_pessoa_id"], l["usina_id"], l["data_id"]) == \
        ("abriu_rota", "hmac-x", 7, 2, 20261108)
    assert l["instante"] == "2026-11-08T15:00:00Z" and l["acesso_id"].startswith("C")


def test_um_passo_que_cai_nao_para_os_outros(ambiente, monkeypatch):
    api, srv, g = ambiente
    _ponto(srv, 7, 60, -23.0, -46.0)
    srv.registro.acrescentar("abriu_mapa", 1, "hmac-x", None, None, AGORA)

    def cai():
        raise RuntimeError("sem coordenadas")
    monkeypatch.setattr(g, "_coordenadas_das_usinas", cai)
    g.rodada(AGORA)
    assert len(api.linhas(livro_pontos(AGORA.date()), ABA_PONTOS)) == 1
    assert len(api.linhas(LIVRO_ACESSOS, ABA_ACESSOS)) == 1
