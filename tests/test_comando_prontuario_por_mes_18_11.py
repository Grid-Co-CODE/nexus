"""O prontuário e o Nexus IA Insights por mês (Levi, 18/11/2026, com o Insights dizendo "Outubro teve 7 desligamentos;
novembro está em 91% da meta"): "O insights e todo o prontuário deve funcionar por mês! Começando por outubro mas quando
eu abrir o prontuário quero sempre no mês vigente, o que fica pendente do último mês ou dia ainda aparece porém em
relação a meta, PR, geração tem que ser do mês atual, o que foi feito no ativo".

1ª parte (este arquivo começa por ela): o diagnóstico do dia fala do MÊS CORRENTE. O dossiê traz o mês a mês desde
outubro, e a IA misturava os dois na situação. O que vem de mês anterior só entra se ainda está em aberto, como
pendência, sem os números de performance daquele mês."""
from nexus.comando import diagnostico as DG


def test_o_diagnostico_do_dia_e_do_mes_corrente_e_o_mes_anterior_so_entra_como_pendencia():
    p = DG.PEDIDO
    regra = next(l for l in p.splitlines() if l.startswith("- O diagnóstico é do MÊS CORRENTE"))
    # os números de performance e o que foi feito são os deste mês
    for trecho in ("meta", "PR", "geração", "disponibilidade", "desligamentos", "o que foi feito"):
        assert trecho in regra, trecho
    # o mês anterior não entra na situação; o que ficou aberto dele entra como pendência, sem a performance de lá
    assert "mês anterior" in regra and "pendência" in regra and "ainda está em aberto" in regra
    # a regra vem antes das listas, junto da situação (é ela que a IA escreve primeiro)
    assert p.index("- O diagnóstico é do MÊS CORRENTE") < p.index("- tem_que_fazer:")
