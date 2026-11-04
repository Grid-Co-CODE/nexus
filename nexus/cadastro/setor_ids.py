"""Os setores que o CÓDIGO conhece, pelo `setor_id` do `dim_setor` (livro `nexus_setores`; Base → Acessos → Pessoas e
setores).

04/11/2026, Levi, antes de renomear setores: "logo mais vou fazer alterações, não podemos ficar dependente de texto". Até
aqui o código achava o setor pelo NOME, sem acento nem caixa: renomear quebrava calado, sem erro, e o "Responsável UFV" do
banco já não casava com o "Responsáveis UFV" do código (as telas do PCM e do Campo que são do setor 10 não abriam
sozinhas para ele, e ele não marcava o motivo das tarefas). O ID nunca muda nem volta a ser usado (excluir só marca
`excluido`, `cadastro/setores.py`); o nome fica só para mostrar.

Setor novo que o código precise conhecer: o ID dele aqui, lido em Base → Acessos → Pessoas e setores (ou no livro), e o
`tests/test_setor_por_id.py` cobra que toda tela e toda regra usam um destes.
"""
ENGENHARIA = 1
PERFORMANCE = 2
ZELADORIA = 3
SEGURANCA = 4
COS = 5
SUPERVISAO_CAMPO = 6
CHAMADOS = 7
PCM = 9
RESPONSAVEL_UFV = 10

# os IDs desta lista, para o teste e para quem precisa conferir
TODOS = frozenset({ENGENHARIA, PERFORMANCE, ZELADORIA, SEGURANCA, COS, SUPERVISAO_CAMPO, CHAMADOS, PCM, RESPONSAVEL_UFV})
