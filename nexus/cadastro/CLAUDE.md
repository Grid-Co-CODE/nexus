# CLAUDE.md — cadastro (o BD_Operações fora da planilha)

O registro mestre do Nexus: usinas, clientes, pessoas, equipes e listas, com os mesmos dados do BD_Operações, mas
editáveis numa tela. As telas ficam nas torres Base (Registro mestre, Clientes, Equipes, Listas, Importar do Excel,
Qualidade do cadastro) e Pessoas (Colaboradores Operação).

## Os módulos

| Arquivo | O que faz |
|---|---|
| `esquema.py` | **cada campo declarado uma vez**: tipo, seção, coluna do BD, se é sensível, se aparece na lista |
| `tipos.py` | validação e normalização por tipo (CPF, telefone, data, coordenada, moeda...) |
| `calculos.py` | as fórmulas do BD_Operações portadas (conferidas célula a célula contra o Excel) |
| `cifra.py` | AES-256-GCM no dado sensível, amarrado ao contexto (entidade, registro, campo), e selo HMAC da linha |
| `armazem.py` | onde o dado mora; hoje `ArmazemLocal` |
| `servico.py` | ler, salvar e versionar registros; quem chama não fala com o armazém direto |
| `importar.py` | importa o `BD_Operacoes.xlsx` e mostra a prévia do que muda antes de gravar |
| `telas.py` | as rotas, penduradas nas torres Base e Pessoas |

Campo novo entra em `esquema.py`, e as telas, a importação e a lista acompanham sozinhas.

## Onde o dado mora

- **Ensaio local:** `C:\GridcoAuto\nexus\cadastro_ensaio.json`, fora do OneDrive e do AppData, com o sensível cifrado.
  A API de dados entra depois, só com o OK do Levi, porque criar o workbook lá é permanente.
- **A chave da cifra** é a `NEXUS_CHAVE_CADASTRO` do `.env`. **Sem ela, CPF, telefone, endereço e receita não
  voltam.** Ela precisa de uma cópia num cofre.
- **Pessoa vai cifrada inteira**, porque quase todo campo identifica alguém. Na usina vão cifrados receita, CNPJ,
  contatos, endereço, CEP e coordenadas. As coordenadas são cifradas no arquivo, mas aparecem na tela sem pedir para
  revelar (`mascarar=False`).

## Regras que já custaram caro

- **ID simples por cadastro** (1, 2, 3...). O IDUsina da planilha (UFV-001) fica em `id_bd` e é a chave da
  reimportação. Cliente tem cadastro próprio, com ID, porque há usinas de mesmo nome de clientes diferentes.
- **Abrir e salvar sem mexer não pode mudar nada.** Já aconteceu de um select sem o valor atual trocar o valor calado.
  Há teste que lê o formulário como o navegador.
- Nos campos de pessoa da usina (técnico, eletricista...), três valores diferentes: **"N/A"** = a usina não tem
  ("Não se aplica"), **"N/I"** = não informado, e **vazio** = automático. "N/A" e "N/I" não são nome de pessoa.
- **Mudança de regra pede prova:** `python -m pytest -q` e as mutações (quebrar a regra de propósito e ver o teste
  acusar). Antes de rodar mutação, saiba quem pode reiniciar o servidor do Nexus no meio dela.
