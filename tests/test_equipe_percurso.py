"""O percurso do técnico no Mapa de equipe (10/11/2026; Levi, pela sessão Nexus Field: "mostra só o ponto de localização
e caso a pessoa queira, consegue ver o percurso que aquela pessoa fez em determinado período de dias e horas!").

Aqui o que fica por trás da tela: os pontos do período no serviço (do diário de 7 dias, na ordem, só da pessoa), a
malha de municípios que dá o fundo do desenho (só do disco: o pedido nunca espera o IBGE) e o registro da LGPD de quem
abriu o percurso de quem e de que período, até o livro do banco. A tela está em `test_equipe_tela.py`.

Banco de mentira (`ApiPGFalsa`), relógio parado, coordenadas e pessoas inventadas; nada vai à rede."""
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo.equipe import ABA_ACESSOS, CAB_ACESSOS, LIVRO_ACESSOS
from nexus.campo.equipe import acessos as AC
from nexus.campo.equipe import municipios as MU
from nexus.campo.equipe import servico as S
from nexus.campo.equipe.gravador import Gravador

AGORA = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)      # 12:00 em Brasília


@pytest.fixture
def ambiente(app, tmp_path):
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="token-de-teste")
    app.extensions["nexus_dados_sessao"] = api
    srv = S.Servico(app, tmp_path, Cofre(gerar_chave()), agora=AGORA)
    yield api, srv, Gravador(app, srv, usinas=lambda: {})
    app.extensions.pop("nexus_dados_sessao", None)


def _lote(*pontos):
    """[(instante UTC, lat, lon, mov)] -> o lote do contrato (o celular em Brasília)."""
    return {"fuso": -180, "pontos": [{"t": int(i.timestamp() * 1000), "lat": lat, "lon": lon, "prec": 8.0, "mov": mov}
                                     for i, lat, lon, mov in pontos]}


BRT = timezone(timedelta(hours=-3))


def _h(dias, hora, minuto=0):
    """O instante UTC do dia `dias` antes de hoje (Brasília), na hora de Brasília pedida."""
    dia = AGORA.astimezone(BRT) - timedelta(days=dias)
    return dia.replace(hour=hora, minute=minuto, second=0, microsecond=0).astimezone(timezone.utc)


def test_o_percurso_e_o_do_periodo_em_ordem_e_so_da_pessoa(ambiente):
    _api, srv, _g = ambiente
    # ontem das 16:50 às 21:59 (como o do Levi de 09/11) e hoje de manhã; o outro técnico no mesmo período
    ontem = [(_h(1, 16, 50), -16.601, -49.101, True), (_h(1, 18, 0), -16.602, -49.102, False),
             (_h(1, 21, 59), -16.603, -49.103, True)]
    hoje = [(_h(0, 7, 10), -16.604, -49.104, True)]
    # chegam fora de ordem, em dois lotes (a fila do celular sobe na manhã seguinte)
    assert srv.receber(1, _lote(*reversed(ontem)), AGORA) == 3
    assert srv.receber(1, _lote(*hoje), AGORA) == 1
    assert srv.receber(2, _lote((_h(1, 17, 0), -16.9, -49.9, True)), AGORA) == 1
    trilha = srv.percurso(1, _h(1, 6), _h(1, 22), AGORA)
    assert [p["instante"] for p in trilha] == ["2026-11-09T19:50:00Z", "2026-11-09T21:00:00Z", "2026-11-10T00:59:00Z"]
    assert [p["lat"] for p in trilha] == [-16.601, -16.602, -16.603] and all(p["pessoa_id"] == 1 for p in trilha)
    # o período de dois dias leva os dois, e o fim do período corta
    assert len(srv.percurso(1, _h(1, 6), _h(0, 12), AGORA)) == 4
    assert len(srv.percurso(1, _h(1, 6), _h(1, 18), AGORA)) == 2            # 18:00 entra (o fim é fechado)
    assert srv.percurso(1, _h(0, 8), _h(0, 12), AGORA) == []


def test_o_percurso_nunca_passa_dos_7_dias(ambiente):
    """A guarda da LGPD vale no percurso como no mapa: o ponto com mais de 7 dias nunca é usado, mesmo pedido."""
    _api, srv, _g = ambiente
    srv.receber(1, _lote((AGORA - timedelta(days=6, hours=23), -16.6, -49.1, True),
                         (AGORA - timedelta(days=2), -16.7, -49.2, True)), AGORA - timedelta(days=1))
    depois = AGORA + timedelta(hours=2)          # o 1º ponto passou dos 7 dias
    assert [p["lat"] for p in srv.percurso(1, AGORA - timedelta(days=30), depois, depois)] == [-16.7]


def test_o_registro_do_percurso_leva_o_periodo_ao_livro(ambiente):
    """Cada abertura do percurso entra no registro da LGPD: quem viu o percurso de quem e de que período."""
    api, srv, g = ambiente
    srv.registro.acrescentar("abriu_percurso", 20, "hmac-x", 1, None, AGORA, periodo=(_h(1, 6), _h(1, 22)))
    srv.registro.acrescentar("abriu_mapa", 20, "hmac-x", None, None, AGORA)
    g.rodada(AGORA)
    linhas = api.linhas(LIVRO_ACESSOS, ABA_ACESSOS)
    assert [list(l) for l in linhas] == [list(CAB_ACESSOS)] * 2
    perc, mapa = linhas
    assert (perc["acao"], perc["alvo_pessoa_id"], perc["periodo_de"], perc["periodo_ate"]) == \
        ("abriu_percurso", 1, "2026-11-09T09:00:00Z", "2026-11-10T01:00:00Z")
    assert (mapa["acao"], mapa["periodo_de"], mapa["periodo_ate"]) == ("abriu_mapa", None, None)
    assert "abriu_percurso" in AC.ACOES


def test_a_linha_da_fila_de_antes_do_periodo_ainda_vai_ao_banco(ambiente):
    """A fila de acessos em disco (`equipe/fila_acessos.jsonl`) pode ter, no deploy, linhas gravadas com o cabeçalho de
    antes (8 colunas, sem o período): elas vão ao banco com o período vazio, e não ficam presas na fila para sempre."""
    api, srv, g = ambiente
    velha = ["Cantiga00001", "2026-11-10T14:00:00Z", 20261110, 20, "hmac-x", "abriu_mapa", None, None]
    assert len(velha) == len(CAB_ACESSOS) - 2
    srv.registro._fila.acrescentar([velha])
    g.rodada(AGORA)
    (l,) = api.linhas(LIVRO_ACESSOS, ABA_ACESSOS)
    assert l["acesso_id"] == "Cantiga00001" and l["periodo_de"] is None and l["periodo_ate"] is None
    assert srv.registro.novos() == []                    # saiu da fila


def test_os_municipios_do_fundo_do_percurso_vem_so_do_disco(tmp_path):
    """O fundo do percurso é a malha de municípios do IBGE dos estados que a caixa toca, a mesma do "Cidade/UF": sem ela
    no disco, o pedido não espera (manda a ida para o fundo e sai sem os municípios); com ela, os que a caixa toca."""
    from test_equipe_municipios import IBGE, Fundo
    ibge, fundo = IBGE(), Fundo()
    caixa = (-49.3, -16.7, -49.1, -16.5)                     # dentro de Goiás, no município Um da malha de mentira
    assert MU.na_caixa(caixa, pasta=tmp_path, baixar=ibge, iniciar=fundo) == []
    assert ibge.pedidos == [] and len(fundo.alvos) >= 1
    fundo.terminar()
    nomes = {nome for nome, _pol, _caixa in MU.na_caixa(caixa, pasta=tmp_path, baixar=ibge, iniciar=fundo)}
    assert "Cidade Um Teste" in nomes and "Cidade Quatro Teste" not in nomes      # o Quatro fica longe da caixa
    MU.limpar()
