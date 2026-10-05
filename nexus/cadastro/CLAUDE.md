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
| `banco.py` | publica o cadastro no PostgreSQL com ID e ligação por ID (`ferramentas/publicar_cadastro.py`) |
| `casamento.py` | casa o nome de uma base sem código (BD_Thopen) com a usina do cadastro |
| `ligacoes.py` + `telas_ligacoes.py` | tela Base → Ligações entre bases: lê as bases, mostra os buracos, grava as decisões |
| `importar.py` | importa o `BD_Operacoes.xlsx` e mostra a prévia do que muda antes de gravar |
| `telas.py` | as rotas, penduradas nas torres Base e Pessoas |

Campo novo entra em `esquema.py`, e as telas, a importação e a lista acompanham sozinhas.

## Onde o dado mora

- **Fonte (onde se edita):** `C:\GridcoAuto\nexus\cadastro_ensaio.json` (servidor: `dados/cadastro_ensaio.json`), fora
  do OneDrive e do AppData, com o sensível cifrado. **Cópia para os outros setores:** o workbook `cadastro_nexus` no
  PostgreSQL (seção "No banco" abaixo), publicado por comando desde 04/10.
- **A chave da cifra** é a `NEXUS_CHAVE_CADASTRO` do `.env`. **Sem ela, CPF, telefone, endereço e receita não
  voltam.** Ela precisa de uma cópia num cofre.
- **Pessoa vai cifrada inteira**, porque quase todo campo identifica alguém. Na usina vão cifrados receita, CNPJ,
  contatos, endereço, CEP e coordenadas. As coordenadas são cifradas no arquivo, mas aparecem na tela sem pedir para
  revelar (`mascarar=False`).

## Regras que já custaram caro

- **ID simples por cadastro** (1, 2, 3...). O IDUsina da planilha (UFV-001) fica em `id_bd` e é a chave da
  reimportação. Cliente tem cadastro próprio, com ID, porque há usinas de mesmo nome de clientes diferentes.
- **A chave de tudo é o ID numérico do cadastro** (decisão do Levi, 04/10: inner join por ID). O código da usina e o
  nome em cada sistema vivem na tabela `de_para`, nunca como chave. Plano: `docs/superpowers/plans/2026-10-04-governanca-ids.md`.
  Pelo código, 99% das linhas das outras bases casam; pelo nome, de 44% a 87%. 121 usinas estão sem código (52 em
  operação) e uma tem "CÓDIGO" escrito como valor.

## No banco (PostgreSQL): `banco.py`

- Workbook `cadastro_nexus` da API db_performace: `clientes`, `equipes`, `pessoas`, `usinas`, `de_para`,
  `atualizacao`. ID inteiro na 1ª coluna; referência vira `<campo>_id` (inteiro). Publicar:
  `python ferramentas/publicar_cadastro.py` (`--ensaio` monta e grava só o xlsx local). Precisa de `GRIDCO_SQL_TOKEN`
  no `.env`.
- O sensível vai numa coluna `sensivel_cifrado` (contexto `banco/<entidade>/<id>`), que só o Nexus abre. Da pessoa,
  só vínculo, cargo, equipe, status e supervisor vão em claro. **`ucs` vai cifrada:** no BD é o número da UC, não a
  quantidade (achado no 1º envio).
- **Texto cifrado é reaproveitado se o conteúdo não mudou:** o nonce é aleatório e a API guarda histórico por linha;
  sem isso, cada envio regravaria todas as linhas. Reenvio sem mudança = 1 linha (a data).
- **`de_para` tem uma linha por chave externa de cada base**, ligada ou não: `usina_id` vazio + `casou_por` diz por
  quê ("sem par no cadastro", "ignorado: …", "conflito com o de-para de trackers"). O "% ligado" sai daí.
- Ordem: regra de ignorar → código (com o prefixo do cliente, depois só "AAA999"; "IPX100" é de 2C e de Thopen, não
  casa) → nome do Fracttal → casamento por nome (`casamento.py`, para base sem código) → dica do de-para de trackers.
  Nome ou código que serve a duas usinas **não** casa.
- **Fracttal:** o código da usina sai do código de equipamento, nos dois formatos "MAB100-INVR2.4" e
  "THPN-SDI100-INVR11.1" (`codigo_do_equipamento`; ler só o 1º pedaço deu 47% em 04/10). Ativo **sem Classificação 1**
  não é "sem usina": a usina sai do código e, sem código, da "Localização ou parte de" ("// Thopen/ Thopen - Brodowski
  1 - SP/…"). Assim BWK200 e "Transformador 2" acham Brodowski e Nobres (Levi, 04/10: "você sabe que é Brodowski e
  Nobres").
- **`casamento.py` (BD_Thopen, sem código):** romano → número, "1 e 2"/"1 a 4" abertos, usina sem número = a "1".
  Nome igual casa mesmo com cidade/estado diferente (o BD_Thopen erra: Saturnino "no PR", Sítio dos Nogueiras "no MT")
  e fica anotado; nome só-base precisa de localização igual e potência (±15%) — é o que separa "Ouro Branco I" (PR) da
  "Ouro Branco" (AL) e "AP. do Taboado" (0,41 MWp) da "Aparecida do Taboado 1 e 2". **Nunca cruza cliente:** E1 é E1,
  não Thopen, com usinas diferentes de mesmo nome (Levi, 04/10).
- **Decisões** moram em `C:\GridcoAuto\nexus\de_para_regras.json` (servidor: `dados/de_para_regras.json`), fora do
  git: `ignorar` (regra fixa "contem" ou chave exata da tela), `ligar` e `desligar` (chave → usina_id, vence o
  automático) e `ausencia` (usina ou cliente inteiro que a base não precisa ter). Fixas: teste, "Grid Co." e Porteiras.
- **Tela Base → Ligações entre bases** (`/t/base/ligacoes`): "Ler as bases de novo" grava `de_para_atual.json` (as
  fontes lidas + o de_para; ~6–11 s); decidir reaplica sem rede; "Publicar no banco" manda ao `cadastro_nexus`. Abas:
  Buracos (com sugestões e ligar/ignorar), Ligado por nome (confirmar/desligar), Usinas fora (ausência esperada por
  cliente) e Decisões (desfazer).
- **Sugestão nunca cruza cliente** nem passa pelas travas do casamento (número diferente, cidade diferente, potência
  40%+ diferente): na 1ª versão real (04/10) ela sugeria "E1 - Andradina 1" para a Andradina da Thopen, "Marajoara 1"
  a 100% para a Marajoara 2 e "Ouro Branco" (AL) para as de Bandeirantes (PR). Hoje os 73 buracos não têm par no
  cadastro e a tela diz "nenhuma parecida".
- **Teste da tela nunca grava na pasta real:** em 04/10 um teste gravou no arquivo de regras de verdade (o `create_app`
  não repassava `NEXUS_DADOS`). Hoje `pasta_dados` recusa em TESTING sem `NEXUS_DADOS`.
- Medido em 04/10 (no banco): BD_Operações 258/258, Fracttal 139/144, Tickets 136/156, BD_Performance 136/156,
  BD_Thopen 87/115. Os que sobram não estão no cadastro (20 usinas da Thopen em negociação nas bases da API; 28 do
  BD_Thopen como Ouro Branco I–V, Delmiro Gouvea 1–4, Lyon; no Fracttal, Solier Cascavel, Marajoara 2 e Porto Real 2/3
  da Thopen).
- Antes de publicar mudança de regra: `--ensaio` e a conferência (nada sensível em claro, todo FK acha o par, toda
  cifra abre). A API não apaga workbook: o `cadastro_nexus` é para sempre.
- **Abrir e salvar sem mexer não pode mudar nada.** Já aconteceu de um select sem o valor atual trocar o valor calado.
  Há teste que lê o formulário como o navegador.
- Nos campos de pessoa da usina (técnico, eletricista...), três valores diferentes: **"N/A"** = a usina não tem
  ("Não se aplica"), **"N/I"** = não informado, e **vazio** = automático. "N/A" e "N/I" não são nome de pessoa.
- **Mudança de regra pede prova:** `python -m pytest -q` e as mutações (quebrar a regra de propósito e ver o teste
  acusar). Antes de rodar mutação, saiba quem pode reiniciar o servidor do Nexus no meio dela.
