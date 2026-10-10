# CLAUDE.md — cadastro (o BD_Operações fora da planilha)

O registro mestre do Nexus: usinas, clientes, pessoas, equipes, regiões de campo e listas, com os mesmos dados do
BD_Operações (a região de campo vem da estrutura de O&M de 10/2026), mas editáveis numa tela. As telas ficam nas torres
Base (Registro mestre, Clientes, Equipes, Regiões de campo, Listas, Importar do Excel, Qualidade do cadastro) e Pessoas
(Colaboradores Operação).

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
| `estrutura_campo.py` | a carga única da estrutura de O&M de 10/2026 (regiões de campo, código e região das equipes) e a conferência dela (`ferramentas/importar_estrutura_campo.py`) |
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
  operação). A Matões 100 (usina 37) tem "CÓDIGO" escrito como valor na planilha; no Nexus é ATHN-MTS100 (04/10).

## Importar o BD_Operações (`importar.py`)

- Caminho: tela Base → Importar do Excel (prévia, depois gravar). Por comando, o mesmo é `montar` → conferir o
  `resumo` → `srv.aplicar_carga(carga, quem=QUEM_IMPORTACAO)` + `srv.auditar(...)`, que guarda uma cópia em
  `C:\GridcoAuto\nexus\backups\`. Depois, `ferramentas/publicar_cadastro.py --ensaio` e sem `--ensaio`. O Nexus no ar
  relê o arquivo sozinho (o cache segue o mtime), sem reiniciar.
- **A responsável pelo BD_Operações ainda mexe nele** (reestruturação de 05/10). O Levi sobe as atualizações à mão até a
  planilha ficar pronta (07/10). Em toda importação, olhe o que cada campo faria: preenche, apaga ou troca. Um campo
  que **apaga** em bloco quase sempre quer dizer que a planilha mudou de forma, e não de dado.
- **Coluna que sumiu não apaga o campo:** fica o valor do Nexus e o aviso diz qual coluna é. Em 07/10 a "RESPONSÁVEL
  O&M" saiu da planilha, e importar apagaria o responsável de 211 usinas, que o PCM usa. Em 08/10 ela voltou, com a
  região no lugar da pessoa (próximo item).
- **Região no lugar de pessoa = vaga** (estrutura de O&M de 10/2026): no BD de 08/10 a RESPONSÁVEL O&M tem 6 valores,
  1 pessoa (45 usinas) e 5 rótulos de região ("NE · Fortaleza-CE e Teresina-PI", "SE · Oeste de SP", "Sul ·
  Maringá-PR"...; 213 usinas): a região onde a vaga de Supervisor de Campo está aberta. Texto que não é pessoa do
  cadastro e é região (`importar.eh_rotulo_de_regiao`: tem "·", é macrorregião com traço ou número, ou o nome de uma
  região de campo do cadastro) NÃO cria pessoa: o Responsável O&M fica vazio e a região vai para `responsavel_om_vaga`
  (a lista mostra "Vaga · <região>"). A prévia tem o bloco "Vagas de Supervisor de Campo" (região, usinas e quantas
  tinham pessoa no Nexus e a perdem) e o aviso diz o total. O mesmo vale para o supervisor digitado na Relação Geral
  e para a lista Supervisor do Auxiliar; a comparação do supervisor calculado conta região × vaga como igual. Pessoa
  nova pela RESPONSÁVEL O&M nasce "Supervisor de Campo" (era "Supervisor"). O PCM recebe a região na AUXILIAR
  (`nexus/pcm/auxiliar.py`), como a AUXILIAR do BD traria.
- **A equipe guarda o código e a região de campo entre importações** (não vêm da planilha): sem isso, cada importação
  apagaria a região de todas as equipes.
- **Célula com o próprio nome da coluna** ("CÓDIGO" no código) é cabeçalho colado por engano: fica o valor do Nexus.
- **Preço por MWp:** 70 usinas têm a receita como `=preço * POTÊNCIA CONTRATUAL`. O preço vira campo e a receita fica
  automática. A regra não depende do nome da tabela do Excel: em 07/10 a tabela foi recriada como `Operacoes4`, e o
  preço das 70 usinas seria apagado.
- Importação de 07/10: o Gestor de Contrato foi preenchido em 159 usinas (coluna nova). Uma pessoa veio com "desistiu" na
  coluna Cluster e virou a equipe 146. O certo é Status = Desligado; quando a planilha for corrigida, a próxima
  importação marca essa equipe como excluída.

## Estrutura de O&M de 10/2026: regiões de campo (`esquema.REGIOES_CAMPO`, `estrutura_campo.py`)

Levi, 08/10/2026, sobre a "Nova Estrutura O&M Equipe": "pode adaptar, deixa as vagas preparadas". Gerência de O&M →
Coordenação de Campo → **Supervisor de Campo** (1 por região de campo: lidera a equipe da região, **aprova e fecha as
OS**) → equipes volantes (E-01 a E-40). Em paralelo, o **Supervisor PM** = o Gestor de contrato (cliente, contrato,
SLA), por usina. O "Supervisor" de antes virou essas duas figuras; quem tem esse vínculo no cadastro é, na prática,
Gestor de contrato.
- **Região de campo** (Base → Regiões de campo, lista e ficha como as outras): nome, base, Supervisor de Campo e
  Coordenador de Campo (pessoas do cadastro). **Vazio é vaga** (`Campo.vazio`): a tela escreve "Vaga" no azul
  tracejado (`.cad-vaga`), nunca como erro nem pendência. A ficha lista as equipes da região; a lista diz quantas
  equipes com usina em operação ainda estão sem região.
- **Equipe**: `codigo` (E-xx, único) e `regiao_campo` (ref). A ficha da equipe diz a região e o Supervisor de Campo;
  a da usina, a região (pela equipe). Filtro de região na lista de Equipes.
- **Vínculos**: "Supervisor de Campo" e "Coordenador de Campo" entraram; "Gestor de contrato" aparece como "Gestor de
  contrato (Supervisor PM)" e "Supervisor" como "Supervisor (legado)" (`esquema.ROTULOS_LISTA`): o valor GRAVADO não
  mudou, para não quebrar ficha, banco e telas. **"COS"** entrou em 09/10/2026: é o campo da relação de quem é do COS
  (Levi: a PT pode ser aprovada por "pessoa do COS ... precisamos ter um campo onde fazemos essa relação"); a pessoa
  com esse vínculo (Pessoas > Colaborador, publicada no banco) pode dar o De acordo nas PT. Em 09/10 o cadastro não
  tinha ninguém do COS (só os colaboradores de campo e os supervisores legados).
- **Carga única** (`python ferramentas/importar_estrutura_campo.py <csv>`; ensaio por padrão, `--aplicar` grava no
  armazém LOCAL com cópia em `backups\<arquivo>_<data>_antes_estrutura_campo.json` e confere). O CSV
  (`C:\GridcoAuto\nexus\estrutura_campo_2026-10.csv`, fora do git) tem região, base, código e equipe. A equipe casa
  pelo nome exato; sem ele, sem acento/caixa/espaço, e só se for UMA viva; o resto vai para "fora" com o motivo. A
  região que já existe é reaproveitada (rodar de novo não muda nada) e a pessoa nunca vem do CSV. **Aplicada em 08/10
  no PC:** 8 regiões (todas com as duas vagas abertas), 34 das 39 equipes casadas pelo nome exato; fora (nenhuma
  equipe com o nome no cadastro nem no BD_Operações de 08/10: são equipes a criar): E-08 DF Oeste 01, E-16 MT Sul 02,
  E-10 ES Leste 01, E-31 SP Norte 01, E-25 PR Oeste 03. Usinas em operação por região: Norte-01 7, Nordeste 01 11,
  Nordeste 02 16, Centro Oeste 01 8, Sudeste 01 7, Sudeste 03 3, Sudeste 02 13, Sul 01 15; 97 sem região (equipes de
  fora da estrutura: as de uma usina só e as que não estão no CSV). Conferido no JSON cru: usinas, pessoas e clientes
  idênticos byte a byte; 34 equipes mudaram só em código, região e versão; +2 valores na lista de vínculos. O nome
  "Norte-01" veio com hífen no CSV (as outras com espaço): corrige-se na ficha.
- **Cuidado com um Nexus que subiu antes deste código** (o 5070 local de 08/10): ele não conhece os campos novos da
  equipe; salvar uma equipe ou importar o BD por ele regrava a equipe SEM o código e a região. Reinicie-o com este
  código antes de editar equipe pela tela.
- **A carga foi só no armazém do PC.** O servidor tem o próprio `dados/cadastro_ensaio.json` (os dois donos do
  cadastro: o passo 1 adiado, `nexus/dados/CLAUDE.md`): lá a tela Regiões de campo fica vazia, e uma publicação feita
  de lá (troca integral) mandaria a aba `regioes_campo` vazia e as equipes sem região, apagando a estrutura do banco.
  Publique só do PC, ou rode a mesma carga no servidor antes.
- **Falta:** criar as 5 equipes de fora (com código e região); pôr o Supervisor de Campo e o Coordenador quando
  existirem (a ficha da pessoa com vínculo "Supervisor de Campo"/"Coordenador de Campo" e o e-mail do Fracttal, que é
  como o login acha a pessoa); publicar; o histórico (SCD2) da região da equipe e do supervisor da região ainda não
  existe (o `historico.py` guarda só pessoa e usina).

## No banco (PostgreSQL): `banco.py`

- Workbook `cadastro_nexus` da API db_performace: `clientes`, `equipes`, `pessoas`, `usinas`, `regioes_campo`,
  `de_para`, `atualizacao`. ID inteiro na 1ª coluna; referência vira `<campo>_id` (inteiro). Publicar:
  `python ferramentas/publicar_cadastro.py` (`--ensaio` monta e grava só o xlsx local; `--bases-guardadas` usa a última
  leitura das bases da tela Ligações, como o botão "Publicar no banco" da tela, sem ler de novo). Precisa de
  `GRIDCO_SQL_TOKEN` no `.env`.
- **`regioes_campo`** (10/2026): `regiao_campo_id`, nome, base, `supervisor_campo_id` e `coordenador_campo_id` (pessoa
  só por ID: o nome fica no `sensivel_cifrado` da ficha dela), `supervisor_campo_vaga`/`coordenador_campo_vaga`
  (sim/não, para não deduzir a vaga do ID vazio) e `ordem`. Coluna nova de aba que já existia vai no FIM, depois do
  `sensivel_cifrado` (`banco.COLUNAS_NO_FIM`: `equipes.codigo`, `equipes.regiao_campo_id`,
  `usinas.responsavel_om_vaga`), e a `atualizacao` ganhou `regioes_campo` no fim: quem lê por posição não se perde.
  **Ensaio de 08/10** (`--ensaio --bases-guardadas`, comparado com o banco por GET): clientes 16→16, equipes 146→146,
  pessoas 134→134, usinas 258→258, de_para 876→876 (as mesmas linhas), `regioes_campo` 0→8; nenhum ID some, nenhuma
  coluna sai, as de antes na mesma posição, nenhum valor das colunas de antes muda e nenhuma cifra é refeita. **Ainda
  não publicado** (é do Levi).
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
- **Geração em linhas (08/10/2026): sistemas `BD_Thopen · aba` e `BD_Performance · aba`** (`ligacoes.FONTES_ABA`;
  chave = o nome da aba de geração, a mesma regra de `nexus.dados.geracao.abas_de_geracao`). "Ler as bases de novo" faz
  +171 leituras de 1 linha (~8 s) e lê a tabela Equipamentos. Os caminhos, nesta ordem:
  1. **O ciclo pela tabela Equipamentos do BD_Performance** (Levi, 08/10: "usa a tabela equipamentos da BD_Performance
     como base de de-para, se liga ao fractall e aí você ligaria o fractal as usinas do BD_Operações"). A "Usina" da
     tabela é o nome que as abas das DUAS bases usam (a aba ou a coluna Usina dela); a "Usina Fractall" é a Classificação
     1 do Fracttal, chave do sistema FRACTTAL. A aba leva `ponte` e `banco._pela_ponte` liga à usina a que o FRACTTAL
     liga aquele nome (exato ou, sem ele, a ÚNICA chave de mesmo nome normalizado: "Saturnino 1  - RJ" com 2 espaços,
     "Nobres 1 - CE" no Fracttal × "- MT" na tabela). `casou_por` = "equipamentos → Fracttal (<como o Fracttal ligou>)".
     Não chuta: usina com 2 nomes do Fracttal na tabela (a "Rodrigues 2": a linha UFV diz Rodrigues 1), chave do Fracttal
     de 2 usinas ou ignorada, e caminho antigo que diz OUTRA usina (`conflito: …`) não ligam pela ponte.
  2. Sem a ponte, o de antes: a aba do BD_Thopen herda a linha de mesmo nome do "Dados Gerais Usinas" (`igual_a`); a do
     BD_Performance vai pelo "Código Fractal" da "Info Geral" (`codigo_de`, "código (Info Geral)"); depois o nome.
  Decisão da tela (ligar, ignorar) vence a ponte: a "AP. do Taboado" fecharia pelo ciclo, mas está ignorada (fora da
  operação, 04/10). Medido em 08/10, calculado sem publicar (Fracttal = o publicado em 07/10): BD_Thopen 100 abas: 78
  pelo ciclo, 9 pelo Dados Gerais, 1 pelo Dados Gerais a 2 usinas (Primavera: a geração não liga), 11 ignoradas, 1 sem
  usina ("zz Rodrigues"); BD_Performance 53: 51 pelo ciclo, 2 pela Info Geral (Colíder 1 e 2). Onde o ciclo e o caminho
  antigo ligam os dois (129 abas), dão a mesma usina em 128 e nenhum conflito; na 129ª, a "Nova Londrina 1", o Dados
  Gerais dava 2 usinas e o ciclo decide uma. A lista das abas que o ciclo não fecha, com o motivo: `C:\GridcoAuto\nexus\
  geracao_de_para_faltando.csv` (fora do git). Os sistemas antigos saem idênticos (876 linhas, 0 diferenças contra o
  publicado). **Ainda não publicado** (é do Levi, passo 1/decisão 8): até lá o `usina_id` da geração fica 0%.
- **A regra de ignorar "Grid Co." do Fracttal pega "RenoGrid - Colíder 1/2" por acaso** (`ignorado` compara texto
  normalizado contido: "renoGRID COlider"). As duas chaves estão fora do de-para do Fracttal desde 04/10; trocar a regra
  por chave exata na tela Ligações.
- **A foto do Fracttal de 05/10 da pasta do PCM não abre neste PC** (`ModuleNotFoundError: pyarrow`: o motor do PCM a
  gravou com strings do pyarrow). O `fracttal()` pega a mais nova e "Ler as bases de novo" quebra (e o
  `publicar_cadastro.py` sem `--bases-guardadas` também, ainda em 08/10); as fotos das rodadas do Nexus (02/10) abrem.
  Instalar o `pyarrow` ou apontar outra foto.
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
  acusar). Antes de rodar mutação, saiba quem pode reiniciar o servidor do Nexus no meio dela (ou mute uma CÓPIA do
  repositório: o clone do OS Creator passa de 260 caracteres de caminho; use o nome curto 8.3 da pasta).
- Prova da estrutura de campo: `tests/test_cadastro_estrutura_campo.py` (a região com as vagas e a vaga que não é
  pendência, as telas e o abrir-e-salvar sem mudar nada, os rótulos dos vínculos, a região na RESPONSÁVEL O&M que vira
  vaga com a prévia, a equipe que não perde a região na importação, o banco sem nome em claro e com as colunas novas no
  fim, a carga única: exato, normalizado, ambíguo, excluída, código de outra equipe, rodar de novo, e a conferência).
