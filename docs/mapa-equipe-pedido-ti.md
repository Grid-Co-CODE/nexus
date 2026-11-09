# Mapa de equipe: pedido de limpeza à T.I.

Texto para o Levi enviar à T.I. Data da decisão: 08/11/2026.

---

**Assunto:** Nexus, Mapa de equipe: limpeza periódica de dois grupos de planilhas no banco da API

Olá, pessoal da T.I.,

O Nexus passa a guardar a localização dos técnicos de campo que usam o Nexus Field (o Mapa de equipe). Por causa da
LGPD, a guarda foi decidida por mim em 08/11/2026: **7 dias** para os pontos de posição e **1 ano** para o resumo dos
deslocamentos entre usinas. O Nexus já deixa de usar e de mostrar ponto com mais de 7 dias, mas quem apaga do banco é a
T.I. Peço a vocês três coisas.

**1. Apagar todo dia os pontos com mais de 7 dias.**
No banco que fica por trás da API (`https://app.gridco.com.br/db_performace`), as planilhas (livros) com nome
`nexus_equipe_pontos_AAAA_MM_DD`, uma por dia (por exemplo `nexus_equipe_pontos_2026_11_08`). Apaguem inteira a planilha
cuja data (AAAA_MM_DD no nome) tenha mais de 7 dias. Ela guarda a coordenada cifrada, mas continua sendo dado de
localização de pessoa.

**2. Apagar todo mês os deslocamentos com mais de 12 meses.**
As planilhas `nexus_equipe_deslocamentos_AAAA_MM`, uma por mês (por exemplo `nexus_equipe_deslocamentos_2026_11`).
Apaguem inteira a planilha cujo mês (AAAA_MM no nome) tenha mais de 12 meses.

**Como listar:** são só as planilhas cujo nome começa com `nexus_equipe_pontos_` ou `nexus_equipe_deslocamentos_`.
**Não apaguem** as outras três do Mapa de equipe, que são o histórico e a auditoria e não têm prazo de limpeza:
`nexus_equipe_aparelhos`, `nexus_equipe_piloto` e `nexus_equipe_acessos`. Nenhuma outra planilha `nexus_*` entra nesta limpeza.

**3. Cópias de segurança e histórico de versões.**
Peço que confirmem que o backup e o histórico de versões do banco não guardam essas planilhas por mais tempo do que a
guarda acima (7 dias para os pontos, 12 meses para os deslocamentos). Se guardarem, por favor me avisem o prazo real e
me digam como encurtar ou excluir esses itens também, porque a guarda só vale se valer nas cópias.

Nada muda no servidor de vocês: a gravação do Mapa de equipe é ligada por mim, pela tela do próprio Nexus. Vou ligar
hoje, 09/11, para um piloto com 1 ou 2 técnicos. Como o primeiro ponto completa 7 dias em 16/11, preciso da limpeza dos
pontos rodando até 15/11. Podem me confirmar quando estiver rodando?

Se preferirem outra forma de fazer a limpeza (um agendamento seu, por exemplo), sem problema: o que importa é o prazo.
Podem me confirmar quando a rotina estiver rodando?

Obrigado,
Levi

---

## Para quem for conferir (nota interna, não faz parte do texto)

- A origem da regra está em `nexus/dados/catalogo.py` (fatos `ponto_equipe` e `deslocamento_equipe`, e as famílias de livro) e
  em `nexus/torres/campo/CLAUDE.md`, seção "Mapa de equipe".
- Os livros ainda não existem no banco: nascem com a primeira gravação, quando a gravação for ligada em Base → Chaves →
  Nexus (`NEXUS_EQUIPE_GRAVA` = 1, no servidor; desde 09/11/2026 pela tela, sem variável da T.I.). A limpeza só tem o que
  apagar depois disso. Decisão do Levi em 09/11/2026: ligar no mesmo dia, para o piloto de 1 ou 2 técnicos, com esta
  carta indo à T.I. junto; o primeiro ponto completa 7 dias em 16/11, então a limpeza dos pontos tem de rodar até 15/11
  (sem ela, a localização fica no banco além dos 7 dias do aviso ao técnico).
- Para conferir depois da primeira rodada de limpeza: listar as abas do banco e ver que nenhum
  `nexus_equipe_pontos_*` tem mais de 7 dias.
