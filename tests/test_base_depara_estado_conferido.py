"""O estado do de-para só relê o livro da estrutura quando o banco diz que ele mudou (Desempenho, 11/11/2026).

O caso (Levi, 11/11: "temos tanto na base > de-para equipamentos quanto no tempo real e sempre roda uma leitura do
fractal"): medido no ar às 09:34, a Base → De-para de equipamentos levou ~14 s para abrir e nenhum pedido foi ao Fracttal
(as 70 árvores saíram da foto dos ativos de 06/11, que a leitura do OS Creator renova toda noite, em ~50 ms cada). Quem
segurava a tela eram os 4 pedidos ao `/t/base/equipamentos/depara/estado`, um atrás do outro (3,3 + 4,7 + 1,6 + 3,0 s):
cada um relia o livro `nexus_estrutura_usina` inteiro (1.932 inversores, 251 cabines, 263 chaves e a visão), porque o selo
que sai dali é o que o salvar confere e a cópia de 1 minuto de outra máquina daria 409. A marca do livro no banco (o
`updated_at` do /api/workbooks, que anda a cada gravação: a última linha às 08:57:18 de 06/11 e o livro às 08:57:21) diz
se ele mudou sem reler as linhas; mudou, ou a leitura atravessou uma gravação, ou o banco não deu a marca: relê como antes.
"""
from test_base_equipamentos_depara import (  # noqa: F401 — as fixtures e a Itajá do banco
    BASE, CH1, ITAJA, _estado, _monta_itaja, _sem_copias, _u, app_dp, banco, cfg, cli)

from nexus.cadastro import estrutura_usina as E


def _itaja(cli):
    return next(u for u in _estado(cli, chaves=CH1)["usinas"] if u["usina_id"] == ITAJA)


def test_o_estado_nao_rele_o_livro_que_nao_mudou(cli, cfg, banco):
    _monta_itaja(cfg, banco)
    primeiro = _itaja(cli)
    lidas = banco.paginas_lidas
    for _abertura in range(3):                                          # os pedidos seguintes da mesma abertura
        assert _itaja(cli) == primeiro
    assert banco.paginas_lidas == lidas, f"{banco.paginas_lidas - lidas} páginas relidas de um livro que não mudou"


def test_o_livro_gravado_por_outra_maquina_e_relido_e_o_selo_acompanha(cli, cfg, banco):
    """O Nexus do PC e o do servidor gravam o mesmo livro: a cópia daqui não pode esconder a gravação de lá."""
    _monta_itaja(cfg, banco)
    antes = _itaja(cli)
    copia = E._CACHE["livro"]
    E.ligar_supervisorio(ITAJA, "Itaja 3 (553)", cfg, BASE, banco, exibicao_aba="Itajá")   # a gravação "de lá"
    E._CACHE["livro"] = copia                                           # e este processo com a cópia de antes
    depois = _itaja(cli)
    assert depois["selo"] != antes["selo"] and "Itaja 3 (553)" in [c["usina_supervisorio"] for c in depois["chaves"]]
    assert depois["selo"] == E.selo(_u(cfg, banco, ITAJA))


def test_a_leitura_que_atravessa_uma_gravacao_nao_vale_como_conferida(cli, cfg, banco, monkeypatch):
    """A gravação de outra máquina no meio da leitura: as páginas podem ser de antes e de depois dela. A marca guardada é
    a lida ANTES das linhas, e o pedido seguinte relê."""
    _monta_itaja(cfg, banco)
    E._CACHE.clear()
    real = banco.get

    def grava_no_meio(url, **kw):
        if "/rows" in url and not grava_no_meio.feito:
            grava_no_meio.feito = True
            banco.marcas[E.LIVRO] = "2026-11-11T09:00:00-03:00"        # outra máquina gravou durante a leitura
        return real(url, **kw)
    grava_no_meio.feito = False
    monkeypatch.setattr(banco, "get", grava_no_meio)
    _itaja(cli)
    lidas = banco.paginas_lidas
    _itaja(cli)
    assert banco.paginas_lidas > lidas, "a leitura que atravessou uma gravação foi guardada como conferida"
    lidas = banco.paginas_lidas
    _itaja(cli)
    assert banco.paginas_lidas == lidas                                       # relida inteira, agora vale


def test_sem_a_marca_do_banco_le_o_livro_a_cada_pedido_como_antes(cli, cfg, banco):
    _monta_itaja(cfg, banco)
    banco.marcas.clear()                                                # a API sem o updated_at
    _itaja(cli)
    lidas = banco.paginas_lidas
    _itaja(cli)
    assert banco.paginas_lidas > lidas


def test_a_abertura_pede_todas_as_chaves_num_pedido_so(cli, cfg, banco):
    """A tela pedia o estado em lotes de 50 chaves, um atrás do outro (3 pedidos para as ~150 chaves da Base), e cada
    pedido no servidor custa a conferência da marca no banco (0,6 a 2,3 s no ar, 11/11/2026). O estado aceita a frota
    inteira num pedido; o salvar segue com 50."""
    _monta_itaja(cfg, banco)
    chaves = [CH1] + [f"Chave sem usina {n} ({n})" for n in range(1, 300)]
    j = _estado(cli, chaves="|".join(chaves))
    assert [u["usina_id"] for u in j["usinas"]] == [ITAJA] and len(j["chaves_sem_usina"]) == 299
    r = cli.get("/t/base/equipamentos/depara/estado", query_string={"usinas": ",".join(str(n) for n in range(E.MAX_ESTADO + 1))})
    assert r.status_code == 400 and not r.get_json()["ok"]
    assert E.MAX_DEPARA == 50                                           # o salvar não muda
