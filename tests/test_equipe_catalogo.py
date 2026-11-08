"""Mapa de equipe (08/11/2026): o dado entra no catálogo ANTES da 1ª gravação (regra 10 da casa)."""
from datetime import date

from nexus.campo import equipe as EQ
from nexus.dados import catalogo, explica

FATOS = {  # id do fato -> (livro, aba, cabeçalho)
    "ponto_equipe": (EQ.LIVRO_PONTOS_MOLDE, EQ.ABA_PONTOS, EQ.CAB_PONTOS),
    "deslocamento_equipe": (EQ.LIVRO_DESLOC_MOLDE, EQ.ABA_DESLOC, EQ.CAB_DESLOC),
    "evento_aparelho": (EQ.LIVRO_APARELHOS, EQ.ABA_APARELHOS, EQ.CAB_APARELHOS),
    "decisao_piloto": (EQ.LIVRO_PILOTO, EQ.ABA_PILOTO, EQ.CAB_PILOTO),
    "acesso_mapa": (EQ.LIVRO_ACESSOS, EQ.ABA_ACESSOS, EQ.CAB_ACESSOS),
}


def test_os_livros_do_mapa_estao_no_catalogo_antes_da_1a_gravacao():
    for fid, (livro, aba, cab) in FATOS.items():
        f = catalogo.POR_ID[fid]
        assert f.area == "campo" and f.grao.startswith("1 linha") and f.fontes
        assert f.livro == f"{livro} · {aba}" and f.chave[0] == cab[0]
        # sem medida se e só se não há medida (tests/test_dados_camada.py)
        assert (f.tipo == "sem_medida") == (f.medidas == ())
        assert fid in explica.RESUMO and fid in explica.PARA_QUE
    # só o deslocamento mede: duração e distância, que somam
    d = catalogo.POR_ID["deslocamento_equipe"]
    assert d.tipo == "transacao"
    assert [(m.coluna, m.unidade, m.soma) for m in d.medidas] == [
        ("duracao_min", "min", "aditiva"), ("distancia_km", "km", "aditiva")]
    for fid in ("ponto_equipe", "evento_aparelho", "decisao_piloto", "acesso_mapa"):
        assert catalogo.POR_ID[fid].tipo == "sem_medida"
    # a coordenada só existe cifrada
    assert "cifr" in catalogo.POR_ID["ponto_equipe"].observacao
    # os 3 livros fixos só crescem e ainda não estão no banco
    for nome, aba in ((EQ.LIVRO_APARELHOS, EQ.ABA_APARELHOS), (EQ.LIVRO_PILOTO, EQ.ABA_PILOTO),
                      (EQ.LIVRO_ACESSOS, EQ.ABA_ACESSOS)):
        l = catalogo.LIVRO_POR_NOME[nome]
        assert l.abas == (aba,) and l.so_cresce == (aba,) and not l.no_banco
    # os de período reconhecidos pela família
    assert catalogo.da_familia("nexus_equipe_pontos_2026_11_08", EQ.ABA_PONTOS)
    assert catalogo.da_familia("nexus_equipe_deslocamentos_2026_11", EQ.ABA_DESLOC)
    assert EQ.livro_pontos(date(2026, 11, 8)) == "nexus_equipe_pontos_2026_11_08"
    assert EQ.livro_deslocamentos(date(2026, 11, 8)) == "nexus_equipe_deslocamentos_2026_11"


def test_as_reguas_do_desenho_moram_num_lugar_so():
    assert EQ.JANELA_H == (6, 22) and EQ.GUARDA_PONTOS_DIAS == 7 and EQ.GUARDA_DESLOC_DIAS == 365
    assert EQ.MAX_PONTOS == 200 and EQ.SEM_SINAL_MIN == 30 and EQ.RAIO_USINA_KM == 1.0
    assert EQ.ORIGEM_APP == "https://gridco-campo-mw.azurewebsites.net"
