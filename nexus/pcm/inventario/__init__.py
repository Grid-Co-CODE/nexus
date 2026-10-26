"""O inventário do almoxarifado (Levi, 26/10/2026): o técnico conta as peças no App, o PCM revisa e aprova, e o Nexus grava o
saldo contado no estoque do Fracttal. Desenho: `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`; o que o
Fracttal de verdade aceita (os métodos, os corpos, as respostas): `...-passo0.md`.

`estoque` é o adaptador: a ÚNICA porta de leitura e gravação de estoque no Fracttal. Quem grava, ajusta a régua ou cria peça
fala só com ele (ou com o `EstoqueFalso` dos testes). `contas` são as contas do inventário (situação de cada peça, contado
efetivo com a curadoria, a contagem mais nova que substitui as velhas, a janela de aprovação), puras: quem lê o livro, mostra
o lote e grava chama as mesmas. `leitura` lê as contagens que o App publica e o estado de cada uma pelos eventos do livro
do inventário. As telas e a gravação em segundo plano entram nas tarefas seguintes.
"""
