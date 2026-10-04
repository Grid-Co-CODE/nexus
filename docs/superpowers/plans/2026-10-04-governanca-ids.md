# Plano — toda base com ID e ligação (04/10/2026)

Pedido do Levi: "temos que ter planilha - ID e ligação. Nosso backend tem que ser forte para conversarmos com qualquer
setor." Mockup: `docs/mockups/governanca-ids.html`.

## Medido em 04/10

| Base | Usinas | Liga por | Casa com o cadastro |
|---|---|---|---|
| Cadastro Nexus (BD_Operações) | 258 | ID + código | 137 com código, 121 sem (52 em operação), 1 = "CÓDIGO" |
| BD_Performance / Base UFV | 157 | Código | 121/122 |
| Tickets / Base de dados - Usinas | 157 | Código da usina | 120/121 |
| AUXILIAR do PCM | 166 | nome | 146/166 |
| Fracttal (ativos, Classificação 1) | 155 | nome | 79/155 |
| Fracttal (código do equipamento, nos 2 formatos) | 142 | "MAB100-…" / "THPN-SDI100-…" | 132/142 (a 1ª medição deu 67: lia "THPN" como código) |
| BD_Thopen / Dados Gerais Usinas | 116 | nome (sem código) | 51/116 |

Script da medição: comparar o sufixo do código do cadastro ("ATHN-MAB100" → "MAB100") com a coluna de código de cada
base, e o nome normalizado (sem acento, sem " - UF").

## Regras

1. Toda tabela tem ID na 1ª coluna; nunca reaproveitado nem editado.
2. Linha que fala de usina, equipe ou pessoa guarda o ID dela, não só o nome. Nome é rótulo.
3. Base ou coluna nova só entra com a chave.

**Chave = ID numérico de cada cadastro** (decisão do Levi, 04/10: "puxar ID é mais leve e fica mais fácil entender
os inner joins"): `usina_id`, `cliente_id`, `equipe_id`, `pessoa_id`; depois `categoria_id`, município pelo código
IBGE, semana programada = `AAAA-Wnn` + versão. OS/tarefa seguem com o id do Fracttal. O código da usina e o nome em cada
sistema ficam na tabela `de_para` (usina_id, sistema, chave_externa, casou_por).

## Fases

| Fase | Quando | O quê | Pronto quando |
|---|---|---|---|
| 0 | segunda | S41 certa republicada (decisão Levi + PCM); 2ª geração da mesma semana = nova versão | Reprogramada da 2ª = da 1ª |
| 1 | semana 1 | código obrigatório, único e no formato; preencher 52 em operação, depois 69 a mobilizar | 177/177 em operação com código |
| 2 | semana 1–2 | tela de-para no Nexus: usina ↔ Fracttal ↔ bases da API, sugestão automática + confirmação | 100% das em operação ligadas |
| 3 | semana 2 | equipe, pessoa, categoria e município com ID | 0 ligação por texto no cadastro |
| 4 | semana 2–3 | motor do PCM e App leem por ID; prova com a foto do Fracttal | responsável em 100% das tarefas |
| 5 | semana 3–4 | API do Nexus por setor (token) + cadastro no PostgreSQL + guardião diário do % ligado | qualquer setor lê do Nexus |

## Estado (04/10)

- **Feito:** cadastro no PostgreSQL, workbook `cadastro_nexus` (clientes 16, equipes 145, pessoas 134, usinas 258,
  de_para 713, atualizacao). Publicar: `python ferramentas/publicar_cadastro.py` (`--ensaio` não envia). Conferido no
  banco: 0 FK quebrada, 0 dado pessoal em claro, 392/392 cifras abrem, reenvio sem mudança troca 1 linha.
- **S41:** só "Reprogramada" e "Nº vezes" refeitos pelo histórico de antes da semana (1.128 → 563); 0 outras células;
  1.119/1.119 iguais à geração certa. Publicar foi bloqueado pela permissão da sessão (repositório na conta do
  Fillipe): o Levi publicou em 04/10 00:41 (commit `22ab2ab`), arquivo idêntico ao conferido.
- Mockup das correções e do banco: `docs/mockups/correcoes-e-banco.html`.
