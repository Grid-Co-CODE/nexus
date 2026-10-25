# CLAUDE.md — cadastro (o BD_Operações fora da planilha)

O registro mestre do Nexus: usinas, clientes, pessoas, equipes, regiões de campo e listas, com os mesmos dados do
BD_Operações (a região de campo vem da estrutura de O&M de 10/2026), mas editáveis numa tela. As telas ficam nas torres
Base (Registro mestre, Clientes, Equipes, Equipamentos das usinas, Regiões de campo, Qualidade do cadastro) e Pessoas
(Colaboradores Operação). A tela Importar do Excel saiu em 14/10/2026 (Levi: "Tire 'Importar do Excel' do módulo base"):
`/t/base/importar` leva ao Registro mestre, sem importar nada; a importação segue por comando (abaixo). Desde 15/10/2026 o
BD_Operações novo exporta CSV, e o Registro mestre tem **Atualizar pelo CSV** (`importar_csv.py`, seção própria abaixo).

**A tela Listas saiu em 11/10/2026** (Levi: "pode tirar listas pois a governança faz mais sentido"): `/t/base/listas`
responde um redirecionamento para Base → Governança de dados (quem tinha o endereço salvo não cai num 404; o POST de uma
tela velha aberta também só redireciona, sem gravar). **As listas continuam no cadastro** (o `armazem` guarda,
`srv.listas()` lê): as caixas de seleção das fichas, a importação do BD_Operações (que traz as listas das abas Auxiliar
e Parametros e mantém o que o Nexus incluiu) e a estrutura de campo (`estrutura_campo.aplicar` inclui os vínculos novos
por `srv.adicionar_valor`) usam. Valor fora da lista na ficha recusa dizendo que a lista vem do BD_Operações; a
pendência "Valores parecidos na mesma lista" aparece na Qualidade sem link (não há tela para abrir).

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
| `ligacoes.py` + `telas_ligacoes.py` | seção Ligações entre bases, no fim de Base → Governança de dados (até 11/10/2026 era a tela Base → Ligações): lê as bases, mostra os buracos, grava as decisões |
| `importar.py` | importa o `BD_Operacoes.xlsx` (por comando desde 14/10/2026: a tela saiu) e monta a prévia do que muda antes de gravar |
| `importar_csv.py` | Base → Registro mestre → Atualizar pelo CSV: o CSV do BD_Operações novo, usina a usina pela ficha, com prévia por coluna (15/10/2026) |
| `estrutura_campo.py` | a carga única da estrutura de O&M de 10/2026 (regiões de campo, código e região das equipes) e a conferência dela (`ferramentas/importar_estrutura_campo.py`) |
| `fracttal_pessoal.py` + `telas_fracttal.py` | tela Base → Acessos → Pessoas e setores: o pessoal do Fracttal ao lado do cadastro de pessoas (12/10/2026) |
| `setores.py` | o setor de cada pessoa do Fracttal e a lista de setores, no livro `nexus_setores` do banco (12/10/2026) |
| `estrutura_usina.py` + `telas_equipamentos.py` | tela Base → Equipamentos das usinas: a usina ligada à mão às chaves do supervisório e os equipamentos dela nas colunas da aba Equipamentos (cabines, inversores, strings, potência), no livro `nexus_estrutura_usina` (13/10/2026; sem Fracttal na tela) |
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

- **Endereço nunca a partir da raiz** (porta única, 09/10/2026): as fichas, a lista, as Ligações, a Prévia, a
  Qualidade e a Visão saem com `{{ raiz }}`/`url_for`/`|na_raiz`, e os redirecionamentos de `telas.py` e
  `telas_ligacoes.py`, com `na_raiz` (o Nexus pode rodar debaixo de um prefixo: `/nexus` no servidor até a fase 4, hoje na raiz).
  Regra completa em `nexus/casca/CLAUDE.md` (o prefixo `/nexus`); o esquecimento quebra `tests/test_prefixo.py`.
- **Base · Chaves das fontes** (`chaves-fontes`, 09/10/2026) não é tela do cadastro: é o `/tokens` da Plataforma de
  Performance numa moldura, só para administrador do Nexus (`nexus/performance/CLAUDE.md`, seção "Porta única").
- **Base · Acessos** (`acessos`, 11/10/2026) também não é tela do cadastro: é quem é administrador do Nexus (a
  `NEXUS_ADMINS` e a lista da tela, num JSON da pasta de dados, fora do banco de propósito) e quem entrou em 30 dias. O
  código mora em `nexus/auth/` (`acessos.py`, `telas_acessos.py`); regras em `nexus/casca/CLAUDE.md`, seção "Acessos".
  Usa a página "só para administradores" do Cadastro (`cadastro/sem_permissao.html`, com `area` e `eyebrow`).
- **ID simples por cadastro** (1, 2, 3...). O IDUsina da planilha (UFV-001) fica em `id_bd` e é a chave da
  reimportação. Cliente tem cadastro próprio, com ID, porque há usinas de mesmo nome de clientes diferentes.
- **A chave de tudo é o ID numérico do cadastro** (decisão do Levi, 04/10: inner join por ID). O código da usina e o
  nome em cada sistema vivem na tabela `de_para`, nunca como chave. Plano: `docs/superpowers/plans/2026-10-04-governanca-ids.md`.
  Pelo código, 99% das linhas das outras bases casam; pelo nome, de 44% a 87%. 121 usinas estão sem código (52 em
  operação). A Matões 100 (usina 37) tem "CÓDIGO" escrito como valor na planilha; no Nexus é ATHN-MTS100 (04/10).

## Importar o BD_Operações (`importar.py`)

- Caminho: por comando (a tela Base → Importar do Excel saiu em 14/10/2026, a pedido do Levi): `montar` → conferir o
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

## Atualizar pelo CSV do BD_Operações novo (`importar_csv.py`, `/t/base/registro-mestre/atualizar`; 15/10/2026)

Levi, 15/10/2026, com o `operacao_usinas_2026-10-15.csv`: "Esse é o novo BD_Operações, conseguimos atualizar os dados do
Nexus com esse CSV? daqui a duas semanas vamos ter acesso em tempo real a esses dados". O CSV tem 258 usinas, 73 colunas,
`;` e decimal com vírgula. A tela (admin, botão "Atualizar pelo CSV" no Registro mestre) recebe o arquivo, mostra a
prévia **por coluna** e aplica só as colunas marcadas. Desenho da prévia (Levi, 16/10, sobre a 1ª versão, uma tabela
larga com uma linha "Ver as mudanças" embaixo de cada coluna: "muito espaçado, confuso"; o mockup aprovado: "Ficou bem
melhor!"): uma linha por coluna com caixa de marcar, agrupada pela seção da ficha (`USINAS.secoes`), a contagem e as
marcas "resume"/"sensível" à direita; clicar abre o usina a usina na própria linha (hoje → no CSV; a pessoa casada pelo
nome contido aparece com o nome do CSV em cinza ao lado); o que não casou vira aviso no topo; "Fica como está" e as
colunas sem campo ficam recolhidos; o botão Aplicar fica preso ao rodapé e diz quantas colunas vai aplicar. **A mesma regra (`proposta` + `aplicar`) é a que a fonte em tempo real vai usar**: troca a
leitura do arquivo pelas linhas da fonte.

Diferente da importação do `.xlsx` (que monta a carga inteira e marca como excluído o que não vem), aqui nada é criado
nem excluído: grava **usina a usina pela ficha** (`Servico.salvar`, versão + auditoria), só o que mudou. Regras, com o
caso que criou cada uma (as três primeiras são decisões do Levi no mesmo dia):

- **Equipe = a do CSV** ("Trocar pela do CSV"), pelo nome sem maiúscula/acento; a que não existe é criada sem código nem
  região. Em 15/10: 56 usinas mudam (as equipes por usina, "MGLGPRT02", "Pedra do Sal 1"..., viram as agrupadas que já
  existiam sem usina, "Pedra do Sal 1 a 4"), 2 criadas (Barreiras, Máquinas 1 a 2). "0" = vazio, "N/A" = não tem.
- **Célula vazia não apaga** ("Manter o do Nexus"): em 15/10, 50 latitudes, 36 modelos de tracker, 30 datas...
- **Valor de lista novo entra na lista** ("Aplicar os novos"): os status AGUARDANDO LIBERAÇÃO e PRONTA PARA MOBILIZAR.
  Só acento/maiúscula/hífen/espaço não é valor novo ("Centro Oeste" = "Centro-Oeste"); uma grafia só para todas as usinas.
- **Arredondamento fica o do Nexus**: 7,049 no CSV × 7,0488 no Nexus (o CSV mostra 3 casas). O mesmo número não conta
  como arredondado; texto com o mesmo número ("23.1" × "23,1", Tensão de linha) não muda.
- **Campo automático** (receita mensal = preço por MWp × potência): o CSV com a mesma conta não congela o valor.
- **"CÓDIGO" no código** (a Matões 100) não troca: é o código que liga ao Fracttal.
- **Pessoa (Responsável O&M) pelo nome contido**: o CSV traz o nome completo ("Fulana Rodrigues Prado", "Ciclano
  Araújo Rocha"; nomes fictícios, o repositório é público) e o cadastro o curto ("Fulana Prado", "Ciclano Araújo").
  Casa pelo nome inteiro, pelo nome padrão ou pelo nome do cadastro contido no do CSV, na ordem, com o mesmo primeiro
  nome e ao menos dois nomes, quando **uma** ficha serve (duas = não adivinha). Em 15/10: 158 usinas mudam de
  responsável; pelo nome inteiro, 203 ficariam sem par (com a regra, 3). Quem não está no cadastro ganha ficha (abaixo:
  até 16/10 ficava o responsável antigo, e o Levi não quis "que siga com os dados antigos"). Cliente só casa pelo nome
  exato.
- **"O CSV resume"**: o valor do CSV contido no do Nexus, que diz mais do que unidade ("SUN2000-250KTL-H1 +
  SUN2000-330KTL-H1" → "SUN2000-250KTL-H1"; "250 kW / 275 kVA" → "250"; "575 Wp" → "575" NÃO é resumo), é marcado na
  prévia para a pessoa decidir a coluna. Em 15/10: 48 marcas (fabricante dos módulos 11, concessionária 10, modelo do
  inversor 9...).
- Link do mapa que não é endereço (11 usinas com coordenada em graus no lugar do link) fica de fora, listado.
- As 19 colunas sem campo no Nexus (Mobilizado?, Impeditivo, Próximo passo, Pessoas a contratar, os kits...) ficam de
  fora e a prévia as lista.
- **AS PESSOAS DA USINA SÃO AS DO CSV** (Levi, 16/10: "não quero que siga com os dados antigos, tem que aplicar no Nexus
  também! Entenda... a regra ainda não é o Nexus, temos que nos adaptar as informações que vem"). O Responsável O&M e
  o técnico, o eletricista e o mantenedor de CADA usina vão para a própria usina (não saem mais só da equipe da pessoa):
  os três saem da "Pessoas da equipe" DELA ("Nome (Cargo), Nome (Cargo · Desligado)"; só a vírgula separa: "Manuel ...
  da Silva e Silva" é um nome só); quem atende duas equipes aparece nas duas (eram 4 em 16/10, que a ficha de uma equipe
  só deixava de fora); o CSV que lista a equipe sem um dos três deixa a usina SEM ele (o marcador "-", que no banco vai
  vazio e não deixa o Nexus deduzir pela equipe), em vez de herdar o técnico fixado no BD antigo; célula vazia não mexe.
  Na prévia são as colunas "Técnico O&M (Pessoas da equipe)" e afins, na seção Equipe e contatos. **16/10, real:** o
  técnico mudou em 62 usinas (7 ganharam; 55 ficaram sem, porque o Nexus mostrava como técnico quem o CSV diz ser
  mantenedor ou eletricista, como um mantenedor de duas usinas da mesma equipe na BA): usinas com técnico 203 → 150.
- **Quem não tem ficha ganha uma** (Levi, 16/10: "procure esses 5 no fractall, faça a relação e adicione no Nexus, não
  podemos ficar sem informação! Se adapte"): o Responsável O&M como Supervisor de Campo (como a importação antiga), o
  resto como Colaborador de campo com o cargo ("Técnico de O&M" → Técnico O&M, "Eletricista", "Mantenedor"/"Man") e a
  equipe do CSV, Ativo, com o nome e o **e-mail da conta do Fracttal** quando ela existe (é o e-mail que liga a ficha
  ao Fracttal, o critério do login; o pessoal vem de `fracttal_pessoal.ler_pessoal()`, 1 hora; Fracttal fora = nasce sem
  e-mail). Desligado sem ficha não entra; nome que serve a duas fichas não liga nem cria (aviso). A conta do Fracttal
  acha a ficha de outro nome pelo e-mail. Da ficha que existe, completa só o VAZIO (cargo, status, e-mail) e a equipe
  quando o CSV dá uma só. Os valores de vínculo, cargo e status que a lista não tem entram com os valores novos.
  Em 16/10: duas pessoas com conta ativa e sem ficha nasceram; 29 fichas completadas (24
  mantenedores sem cargo e status, 5 e-mails conferidos nome a nome). Na prévia, o grupo "Colaboradores".
- **A pessoa casa também pelo NOME PADRÃO calculado** (`_indice_pessoas`): o furo de 16/10 era casar só pelo nome
  completo, e o CSV escrevia o nome com uma letra trocada ou com a partícula do sobrenome separada, onde a ficha a tem
  junta; o nome padrão da ficha (o primeiro e o último nome) está contido no nome do CSV. Duas dessas pessoas não têm
  conta no Fracttal (ficha certa, nada a relacionar).
  não têm conta no Fracttal (ficha certa, nada a relacionar).

**Onde grava:** no cadastro da máquina em que a tela abre (`NEXUS_ARMAZEM_LOCAL`: o do servidor em app.gridco.com.br; o do
PC em `C:\GridcoAuto\nexus\cadastro_ensaio.json`). Os dois e a cópia no banco (`cadastro_nexus`) são donos
separados: aplicar no servidor não muda o PC nem o banco (os "dois donos do ID": equipe criada num não existe no outro).
**As telas de campo leem o BANCO** (`campo/visao.py`, chamados, Acessos → Pessoas e setores: `cadastro_nexus`), não o arquivo:
para o responsável novo chegar nelas, aplique no PC e publique (`ferramentas/publicar_cadastro.py --bases-guardadas`,
com `--ensaio` e a comparação com o banco antes). Foi o caminho de 16/10/2026 (Levi: "mude logo pois precisamos da
informação de responsáveis, técnicos, usinas"): o banco era igual ao PC (0 diferenças, publicado do PC em 12/10); depois
do CSV, 2 inseridas, 320 atualizadas (251 usinas, 66 pessoas cujo supervisor calculado segue o responsável novo, 2
de-para), 0 apagadas; conferido decifrando o sensível das 258. **Atualize os dois donos antes de publicar de qualquer
um:** o "Publicar no banco" do servidor (Governança de dados) publica o arquivo DELE, e com o cadastro antigo lá o banco
voltaria atrás. O CSV não traz técnico: o Técnico O&M sai da equipe de cada pessoa (Colaboradores); em 16/10, 55
usinas sem técnico, 32 delas com "Pessoas da equipe" no CSV (coluna sem campo no Nexus).

**Tempo:** cada usina é uma gravação do arquivo inteiro: 251 usinas levaram 32 s no PC (a prévia, 0,2 s). A tela avisa
e o botão trava depois do primeiro clique (a prévia vale uma vez; o segundo pedido diria "venceu" enquanto o primeiro
grava). A prévia vive 30 min na memória do processo; o resultado volta por 303.

**Prova:** `tests/test_cadastro_atualizar_csv_15_10.py` (cada regra, a tela, só admin, pedido de outro site, só as
colunas marcadas, quem salvou a ficha depois da prévia ganha, a segunda prévia vazia). Com o arquivo real, numa CÓPIA
do cadastro do PC (15/10): 258/258 casadas, 251 mudam em 22 colunas, aplicar 251 com 0 erro e 0 conflito, e a prévia
de novo dá 0; pela tela (cópia), 20 de 22 colunas → 248 usinas.

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

## Pessoas e setores, a antiga Integração Fracttal (`fracttal_pessoal.py`, `telas_fracttal.py`; 12/10/2026)

**Mora em Base → Acessos, aba Pessoas e setores** (`/t/base/acessos?aba=pessoas`, desde 25/10/2026; Levi: "gostaria que
não tivesse uma tela só para integração fractall e sim fosse para acessos"). O `/t/base/fracttal` leva à aba, com os
filtros; a aba de telas e administradores não lê o Fracttal. **A busca e os filtros são da própria página** (Levi, no
mesmo dia: "cada pesquisa faz um carregamento novo na tabela que já está carregada"): todas as linhas vêm, cada uma com o
que cada filtro olha (`data-f-*`, `static/filtro-local.js`), e as de fora do filtro do endereço chegam escondidas; o
setor gravado na linha muda o filtro dela na hora (`static/acessos-pessoas.js`). **O campo Setor de cada linha vem só
com o setor dela** e a lista inteira entra ao tocar nele (o `<template id="fr-opcoes">`): com a lista em cada linha a
página passava de 300 KB (medido com 180 pessoas: 319 KB). **O Fracttal ligado às fichas fica guardado 2 min**
(`telas_fracttal._dados`, `RELACAO_S`): vencido, a cópia na hora e a releitura por trás, uma por vez (a 1ª abertura
fria levava ~2,4 s no PC); o "Ler o Fracttal de novo" lê na hora; leitura ruim não fica guardada. Prova:
`tests/test_base_acessos_pessoas_25_10.py` e `tests/test_base_fracttal.py`.


Levi: "Temos a relação do time de campo, precisamos da relação do pessoal do fractall e também posteriormente vamos
precisar relacionar os setores, mas não tenho uma base em mãos agora para setores". O cadastro de pessoas é a "Relação
Geral Colaboradores" (o time de campo: 124 colaboradores de campo e 10 supervisores em 12/10); o Fracttal tem o pessoal
inteiro. A tela põe as 150 pessoas do Fracttal (o `personnel`, 2 pedidos de 100, guardados por 1 hora; "Ler o Fracttal
de novo" força) ao lado das fichas, pelo **critério do login** (`visao.pessoa_do_login`): o e-mail da ficha ou, sem ele,
o nome de UMA ficha (completo, primeiro e último, ou o do e-mail); nome de duas fichas não liga, e a mesma ficha para
duas contas fica marcada. Mostra também as fichas sem conta no Fracttal (as ativas; "ver todas" inclui desligado e sem
status). **Medido em 12/10:** 150 no Fracttal (90 administradores, 54 de leitura, 6 sem acesso), 62 com ficha, 88 sem
ficha, 72 fichas sem conta (19 ativas). 1ª visita 2,5 s; depois, 0,02 s. **Origem** pelo domínio do e-mail
(`DOMINIOS_GRID`: gridco.com.br e gridco.com): das 88 sem ficha, 45 são da Grid Co. (o escritório: PCM, COS, engenharia,
gestão; a falta de verdade) e 43 externas (clientes com acesso de leitura, pelo domínio da empresa deles, e
e-mails pessoais); filtro Origem e a etiqueta "externo" na linha.
- **Setor** (`setores.py`; Levi, 12/10: "Como faço para definir um setor???? tem que dar possibilidade"): o Fracttal
  não diz o setor de ninguém (grupo 1, grupo 2 e campos próprios vazios nas 150) e não há base, então a lista nasce na
  tela. Botão **Setores** (ao lado da contagem): criar, renomear, excluir (só setor sem ninguém; o ID do excluído não
  volta). Na linha, a caixa Setor grava na hora, sem recarregar (fetch; o resultado no aviso do canto e na borda da
  caixa: texto na linha mudava a largura da coluna); marcar várias abre a barra "Pôr no setor" embaixo. Filtro Setor (com
  "Sem setor") e a busca acham pelo nome do setor. Grava no livro **`nexus_setores`** (`dim_setor` + `fato_decisao_setor`,
  só acrescenta, vale a última decisão de cada pessoa; regras em `nexus/dados/CLAUDE.md`, "Setor do pessoal"): a pessoa
  pelo `fracttal_id` (id_personnel), a ficha (`pessoa_id`, `pessoa_ligada_por`) e o código do e-mail, **nunca nome nem
  e-mail**. Antes de gravar, relê o livro do banco; leitura que falha não grava (gravaria por cima). POST só da própria
  página (`_de_outro_site`) e só administrador. Sem `GRIDCO_SQL_TOKEN` ou com o banco fora, a tela avisa e a caixa
  fica só para ver. O livro nasce com o 1º setor criado (registrado no catálogo antes).
- **Desenho (12/10, Levi):** sem o título "Pessoal do Fracttal" ("não serve de nada"; os filtros saíram do cartão, como
  na lista de Colaboradores), sem a coluna Código e o "Como liga" virou a dica do (!) ao lado de "Ler o Fracttal de
  novo" (passar o mouse ou focar; Esc fecha).
- **Só administrador** (nome e e-mail de todo o pessoal ficam na tela e na memória, nunca no banco). Prova:
  `tests/test_base_fracttal.py` (a ligação, o setor no banco falso, as recusas, a tela e o catálogo). Conferido em
  12/10 numa cópia com o banco e o Fracttal reais e o livro dos setores num arquivo local (6 setores, 1 pela linha,
  4 pela barra, filtro, celular).

## Equipamentos das usinas (`estrutura_usina.py`, `telas_equipamentos.py`, `/t/base/equipamentos`; 13/10/2026)

Levi, 13/10/2026 (o atalho do Tempo real abria o editor do de-para da plataforma na fonte errada): "Temos que substituir a
aba equipamentos aproveitando o que tem lá e usando o Nexus como ponto de partida a partir daquele produto. Precisamos
ligar a usina do Fractal com Usina cadastrada no registro mestre com usina do supervisório para aí poder ligar os
inversores, quantidade de cabines, quantidade de inversor por cabine, quantidade de strings por inversor, potência sendo
calculado pelo kwp da usina e das cabines... precisamos ter uma versatilidade no Nexus, não pode ser âncora". E: "Não
quero que faça as conexões automaticamente, quero poder ver e fazer de forma versátil, pq se só você fizer vai ficar fácil
de entender para você, quando eu for fazer não vou entender nada".

- **Sem Fracttal na tela (13/10/2026, Levi: "já temos a ligação com o Fractall pelo registro mestre que é o código da
  UFV, só precisamos ligar o que aparece no repositório do que vai aparecer lá na plataforma de tempo real, então tem que
  funcionar mais como uma tabela que nem era na TEquipamentos do BD_Performance, você está complicando sem necessidade
  alguma!"; ligar ao OS Creator fica para depois).** Saíram o passo "Nome no Fracttal", o ativo do Fracttal de cada
  cabine e inversor (com o "Sugerir ativos pelo nome") e a leitura dos ~22 mil ativos ao abrir a usina (6,7 s medidos do
  PC). As rotas `/equipamentos/fracttal` e `/equipamentos/ativos` e os campos `equipamento_id`/`codigo_fracttal` do
  livro ficam (o que já foi gravado segue no Salvar, intacto); a "Usina Fractall" da visão continua vindo das Ligações.
  Desde 20/10/2026 quem grava os dois campos é o **de-para do tempo real** (abaixo), com o ID derivado do código; esta
  tela continua sem mostrá-los.
- **Ligar pela aba Equipamentos (13/10/2026, à tarde; Levi: "Em "Equipamentos da Usinas" ligue automaticamente pelos
  dados que temos na aba equipamentos do BD_Performance!" — o "não quero conexões automáticas" da manhã ficou para trás).**
  A seção do topo da tela e o POST `/equipamentos/ligar-aba` (`estrutura_usina.proposta_pela_aba` +
  `ligar_pela_aba`): cada chave da aba liga à usina do Registro mestre pela **Usina Fractall** dela, no de-para do
  Fracttal das Ligações (`ligacoes.ler`; exato ou o ÚNICO de mesmo nome normalizado), o mesmo ciclo das Ligações entre
  bases. **Não chuta** (cada uma sai na lista "não ligam sozinhas", com o motivo): chave sem Usina Fractall, com dois
  nomes do Fracttal (a Rodrigues 2), com nome fora das Ligações, ignorado (Colíder: tarefa interna) ou de duas usinas,
  usina fora do Registro mestre, e chave que as Ligações ignoram ou ligam a OUTRA usina nas abas de geração (`BD_Thopen
  · aba`, `BD_Performance · aba`): a "AP. do Taboado" tem na aba o nome do Fracttal da Aparecida do Taboado 1 e 2, mas
  é outra usina, fora da operação. A estrutura vem da aba como o "Trazer da aba" (`estrutura_da_aba`): a chave da usina
  é a única com a linha UFV, a cabine é da usina pelo nome (UG e Equipamento Parente), o nome de inversor repetido entre
  chaves ganha a chave no nome, e o mesmo nome no supervisório duas vezes na mesma chave fica só no 1º (aviso). **Só
  usina SEM estrutura gravada**: a que já tem algo (à mão ou de uma rodada anterior) fica como está, e a chave nova dela
  vai para a lista "não ligam sozinhas" com o que fazer (ligar a chave e usar o "Trazer da aba"); o botão conta só o que
  ele de fato grava (no servidor, logo depois da 1ª rodada, ele oferecia "Ligar 1 chave" e não ligava nada). Nasce
  FORA do lugar da aba (a visão segue vazia; os leitores não mudam até alguém marcar). Uma gravação só, com o livro
  relido dentro da trava. Medido no dado real em 13/10, com o de-para do PC de 12/10: 262 das 301 chaves em 123 usinas,
  251 cabines, 1.932 inversores, 29.148 strings; 38 de fora (19 sem Usina Fractall, 13 com o nome fora das Ligações, 5
  ignoradas, 1 com dois nomes). **Gravado em 13/10/2026 pela 5070** (o livro tinha só a CPP100 que o Levi ligou à mão):
  +262 chaves, +251 cabines, +1.932 inversores, +29.148 strings, visão e "no lugar da aba" seguem em 0. Conferido pela
  tela: 160 das 263 chaves iguais à aba; as outras com as diferenças do modelo (a cabine é da usina e sai na chave da
  usina, a potência da UFV é a do Registro mestre, o nome do Fracttal vem das Ligações, nome de inversor repetido entre
  chaves). Prova: `tests/test_equipamentos_ligar_pela_aba.py`.
- **O ponto de partida é a usina do Registro mestre.** À esquerda, as 258 usinas (busca enquanto se digita; filtro de
  CLIENTE, o da ficha no Registro mestre, com quantas usinas cada um tem e "Sem cliente" (13/10/2026, Levi: "tem que dar
  para filtrar o cliente!"); filtros sem chave, sem inversores, potência que não fecha; os filtros seguem ao abrir uma
  usina e depois de cada gravação); à direita, a usina aberta em 2 passos.
- **1. Chaves do supervisório:** a "Usina Supervisório" da aba Equipamentos (`bd_performance · Equipamentos`), a chave que
  a plataforma usa por dentro. Uma usina pode ter várias; **uma chave serve a uma usina só** (a de outra usina é
  recusada). As opções vêm ordenadas, com o porquê escrito ("nome parecido"), nenhuma escolhida. Chave digitada que não está na aba liga, com aviso para conferir o nome exato. **Desligar a chave nunca
  apaga inversor:** os que chegavam por ela ficam na usina sem chave, à vista para ganhar outra.
- **2. Equipamentos, nas colunas da aba** (editor em JavaScript sobre um rascunho; só o Salvar grava, de uma vez, por
  fetch com JSON, e recebe de volta o estado gravado com os IDs novos, sem recarregar). As tabelas usam os nomes da aba:
  Cabines (UG): Equipamento, Potência (kWp), N de Inversores; Inversores: Usina Supervisório, Equipamento, Equipamento
  Supervisório, Equipamento Parente, Potência (kWp), Strings Ativas. **A cabine é da usina** e o inversor diz a chave por
  onde chega, o nome lá (`equipamento_supervisorio`), a cabine, kWp e strings esperadas. Porque na aba a
  UG fica numa chave e os inversores dela em outra (a Altair: "Altair" com a UFV e as 5 UG, e "Altair 1 (73)" a
  "Altair 5 (77)" com os inversores; 1.311 dos 2.201 inversores da aba apontam para UG de outra chave). Ajudas, todas
  só no rascunho: **Trazer da aba** (as chaves ligadas; só preenche o vazio e nunca apaga; nome repetido de outra chave
  ganha a chave no nome), **Gerar inversores** numa cabine ("Inversor c.n", continuando a numeração), **Distribuir
  potência** (cabine sem kWp = o que falta da usina ÷ as vazias; inversor sem kWp = o que falta da cabine ÷ os vazios).
- **Potência:** a da usina é a **real** do Registro mestre (`potencia_real`, MWp × 1.000) e, sem ela, a contratual (a
  tela diz qual). Medido em 13/10: a aba bate com a real (Araputanga 1: real 3,469 MWp, contratual 3,25; UFV da aba
  3.469,2 kWp); 68 das 258 usinas não têm a real. Conferência contra a soma das cabines e a dos inversores: até 0,5% fecha
  (verde), até 5% perto (amarelo), acima não fecha (vermelho). Inversor sem kWp conta o da cabine ÷ os inversores dela,
  e a soma diz quanto é calculado. A linhagem do kWp gravado (`potencia_regra`, 20/10/2026): o número que o Salvar desta
  tela devolve igual guarda a regra que tinha (o kWp que o de-para calculou segue `real_por_string`); número novo, o
  digitado e o do "Distribuir potência", é `informada`; o que veio da aba (o "Ligar pela aba") e o de antes de 20/10
  ficam vazios. O código do Fracttal trocado por aqui apaga o Conferido (era daquele código).
- **O livro `nexus_estrutura_usina`** (no catálogo antes de existir; nasce com a 1ª chave ligada): `dim_supervisorio`,
  `dim_cabine`, `dim_inversor`, estado atual (troca integral do livro inteiro, relido do banco sob trava antes de cada
  gravação; leitura que falha não grava). ID = maior + 1 e não volta; excluir marca `excluido = sim`; indicador 1/0
  (regra 3); quem mudou só em `alterado_por_hmac` (regra 8; o e-mail vai ao log da máquina). **Selo:** o Salvar leva a
  impressão do que a usina tinha quando a tela abriu (só os campos do negócio, para a data relida não dar mudança
  falsa); se outra aba ou pessoa mudou a usina no meio, nada grava e a tela pede para recarregar. A ordem é gravada
  (tirar um inversor muda a ordem dos seguintes, e isso conta como mudança). **Colunas de 20/10/2026, no FIM** (depois
  do controle, para quem lê por posição; a linha gravada antes lê vazio): `dim_cabine.potencia_regra`;
  `dim_inversor.potencia_regra`, `fracttal_ligado_por` e `conferido_em` (listas fechadas em
  `nexus/dados/dominios.py`; fora da lista = vazio). Entram no selo, menos a data do Conferido: o selo de toda usina
  mudou uma vez, no deploy delas (a aba aberta antes pede para recarregar).
- **A aba Equipamentos não muda** (o BD é do Levi e da equipe, nunca se mata). Medido em 13/10: 2.602 linhas, 301
  chaves, 247 UG, 2.201 inversores (214 sem nome no supervisório), 85 usinas de exibição com mais de uma chave, só UFV,
  UG e inversor (e 8 linhas vazias); "Chave" e "Chave 2" são concatenações de fórmula e "Observações" é texto livre.
- **No lugar da aba (as fases 2 a 5, 13/10/2026; Levi: "pode fazer todas as fases! vamos pra cima!").** Cada chave tem,
  no `dim_supervisorio`: o **nome de exibição** (`usina_exibicao`, o "Usina" da aba: nasce dela ao ligar e no Trazer da
  aba; vazio = o do Registro mestre), a **chave da usina** (`principal`, uma por usina: a 1ª ligada; o Trazer da aba a
  passa para a chave que tem a UFV na aba; desligá-la passa para a 1ª das que ficam) e a marca **no lugar da aba**
  (`substitui_aba`, nasce desmarcada: marcar é decisão). As marcadas saem numa **visão no formato da aba**
  (`aba_equipamentos`: as colunas da aba, com os IDs no fim), refeita a cada gravação da tela com o que ela sabe do
  Registro mestre e das Ligações (`info`: nome, cliente, potência real/contratual, 1º nome do Fracttal); só regrava se
  mudou. A UFV e as UG saem na chave da usina, com "Usina Supervisório" vazia quando a chave é o próprio nome de
  exibição (como 103 das 146 UFV da aba); o inversor sai sempre com a chave e com "Inversor " na frente se o nome não
  começar assim (os leitores só contam o que começa). Inversor sem chave não sai.
- **Os leitores trocam as linhas das chaves da visão** (tiram da aba as de UFV, UG e inversor dessas chaves, pela chave
  efetiva "Usina Supervisório" ou, sem ela, "Usina", e põem as da visão; o resto segue da aba): a **plataforma**
  (`plataforma/estrutura_nexus.py`: o cadastro, o mapa do "Usina Fractall" e a disponibilidade; relê sozinha quando a
  visão muda; `ESTRUTURA_NEXUS=0` desliga; `/api/estrutura-nexus` diz o que entrou), o **gêmeo** (`gemeo/gemeo/ingest/
  cadastro.py`, a versão do cadastro leva o `updated_at` do livro), as **Ligações** daqui (a ponte aba → Fracttal) e o
  **coletor** (`load_name_mapping`, DESLIGADO por padrão: liga com `COLETOR_ESTRUTURA_NEXUS=1` ou `[nexus]
  estrutura_no_lugar_da_aba = sim` no config.ini, e na 22:30 só depois de build e release, que são do Levi). A mesma
  regra (`sobrepor`) nos quatro: mudou num, muda nos outros. **A linha da visão herda a grafia da aba** quando a chave
  bate pelo `texto` (espaços juntados; 20/10/2026): o Nexus guarda "Assis Chateaubriand Skid 1 (79)" e a aba e a API PV
  escrevem "Assis Chateaubriand  Skid 1 (79)", com espaço DUPLO; a plataforma busca o cadastro pela grafia exata da
  fonte, e a Skid 1 marcada perdia as strings esperadas, os nomes, o kWp e o Full O&M no tempo real. Vale a grafia da 1ª
  linha da aba com a chave, na "Usina Supervisório" (ou na "Usina") e no "Chave"/"Chave 2"; chave só do Nexus segue
  como ele grava. **O "Usina Fractall" também herda** (2ª revisão final, 21/10/2026), pela MESMA chave e quando o `texto`
  bate (só os espaços mudam): a plataforma acha a usina no índice do Fracttal pela description EXATA, e a Belo Jardim
  (usina 32, "Thopen - Belo Jardim  1 - PE", espaço duplo na aba, no Fracttal e nas Ligações) marcada com o nome de
  espaços juntados ficava "fora do Fracttal" (sem o badge de OS, sem as OS no Diagnóstico e com a cascata de queda em 0).
  Nos três leitores que este trabalho mexe: `sobrepor` daqui (as Ligações), `plataforma/estrutura_nexus.py`
  (`grafias_fracttal` + `herda_grafia`) e o gêmeo (`sobrepor_nexus`). O coletor não foi mexido (há trabalho de outra
  sessão sem commit lá; ele não usa o "Usina Fractall" no `load_name_mapping` e está desligado por padrão).
- **Antes de marcar, a tela compara** (`comparar_usina` → `comparar_chave`): chave a chave, a aba contra a visão do que
  está SALVO (nome de exibição, Fracttal, cliente, Full O&M, String Box, UFV e o total de inversores, cabines e kWp, e
  cada inversor: nome, cabine, kWp, strings, o que só está de um lado). Coluna "Diferença com a aba": "igual à aba", "N
  diferenças" (clique abre a lista) ou "fora da aba"; com rascunho não salvo diz "(do que está salvo)". Salvar uma chave
  recém-marcada que ainda tem diferença pede confirmação. O botão **Refazer a visão** (no topo, com chave marcada) é para
  quando o Registro mestre ou o Fracttal mudaram fora da tela. A comparação olha só o que a aba tem: o "Código
  Fracttal" da visão não conta (a chave com o ativo ligado continua "igual à aba"). Desde 20/10/2026 ela devolve
  também `itens` (cada diferença com o `tipo`), que o de-para do tempo real usa para decidir se a chave vale no lugar da aba (abaixo).
  Duas regras de 21/10/2026 (2ª revisão final): o **nome de exibição** é conferido contra TODOS os "Usina" das linhas da
  chave na aba (`agrupar_aba` guarda `usinas`, e o `usina` é o das linhas de inversor): na Taguaí (usina 136) a 1ª linha
  da "Taguaí 1 (173)" é uma UFV solta com Usina "Taguaí 1 (173)" e os inversores dizem "Taguaí"; o "Ligar pela aba"
  guardava o da UFV solta, a visão o escrevia em todos os inversores, a comparação (só com a 1ª linha) não via e o
  USINA_GRUPO dos leitores trocava. Hoje o "Ligar pela aba" semeia "Taguaí"; as duas chaves do banco de 20/10 (com
  "Taguaí 1 (173)" e "Taguaí 2 (174)") não valem no lugar da aba, e **acertar a exibição no Nexus NÃO basta** (3ª
  revisão, 21/10/2026): a chave tem na aba os dois "Usina" (a UFV solta com "Taguaí 1 (173)", os inversores com
  "Taguaí"), e qualquer exibição que o Nexus tenha difere de um deles. Só tirar da aba as duas linhas de UFV solta
  ("Taguaí 1 (173)" e "Taguaí 2 (174)", linhas 2213-2214 da aba) faz a usina valer; não foi feito. O **nome do Fracttal** é comparado pelo `texto` sem caixa (o
  acento conta, os espaços não): espaço o `sobrepor` resolve; acento ("Taguai" × "Taguaí") é outra description no índice.
- **De-para do tempo real (20/10/2026; Levi, com o protótipo do "Modo de-para": "Boa, é isso mesmo. Implementa no tempo
  real e adapta na base o de-para").** O "Modo de-para" do Tempo real e a Base · De-para de equipamentos (telas da
  plataforma, abertas pela porta única na MESMA origem) leem e gravam a estrutura por duas rotas JSON desta tela, só
  administrador (`_tela`) e só da mesma origem (`_de_outro_site`, o GET inclusive). O livro é do Nexus (um escritor por
  livro: a troca integral sob a trava deste processo); a ponte fonte → chave continua no `nexus_depara` da plataforma, e
  o Salvar da plataforma grava primeiro aqui e depois a ponte. O contrato:
  - `GET /t/base/equipamentos/depara/estado?chaves=A|B` (ou `?usinas=93,108`) → `{ok, usinas: [{usina_id, nome,
    codigo, selo, kwp, kwp_de ("real"|"contratual"|null), chaves: [{supervisorio_id, usina_supervisorio, principal,
    substitui_aba}], cabines: [{cabine_id, nome, codigo_fracttal, potencia_kwp, potencia_regra}], inversores:
    [{inversor_id, supervisorio_id, usina_supervisorio, nome, equipamento_supervisorio, cabine_id,
    strings_esperadas_qtd, potencia_kwp, codigo_fracttal, equipamento_id, potencia_regra, fracttal_ligado_por,
    conferido_em}]}], chaves_sem_usina, usinas_fora_do_registro, gravando}`: a usina INTEIRA de cada chave, relida do
    banco (o selo que sai daqui é o que o salvar confere; a cópia de 1 minuto de outra máquina daria 409 em seguida).
    `gravando` (2ª revisão final, 21/10/2026) = há um salvar do de-para em curso neste processo (da chegada do pedido à
    resposta, `estrutura_usina.em_curso`) ou a trava do livro ocupada: no estouro de 180 s e no 502/504 do proxy o pedido
    abandonado continua aqui (o waitress serve em threads), e o estado relido na hora devolvia o selo de antes (provado com
    o `livros.publicar` segurado). A tela espera o `gravando` cair antes de concluir "está como antes".
  - `POST /t/base/equipamentos/depara/salvar` `{itens: [{usina_supervisorio, usina_id, selo, inversores:
    [{equipamento_supervisorio, nome, strings, cabine_codigo_fracttal, codigo_fracttal, conferido}]}]}` (o `nome` é o
    do cadastro: a tela passou a mandar na 2ª revisão de 20/10) → `{ok, usinas (o estado novo, como o GET), kwp:
    {inversor_id: kWp}, visao_mudou, erros: [], avisos: [{usina_id, usina_supervisorio, tipo, texto}], mudancas,
    cabines_excluidas: [{cabine_id, usina_id, nome}], marcacao: [{usina_id, usina_supervisorio, principal, marcada,
    fora_da_regra: [textos]}]}`. O `tipo` do aviso é curto e ESTÁVEL (`estrutura_usina.TIPOS_AVISO`: `semeada_pela_aba`,
    `nao_marcada`, `sem_potencia`, `sem_strings`, `cabine_fora_do_padrao`, `cabine_excluida`, `cabine_sem_inversores`;
    `usina_supervisorio` vazio = aviso da usina inteira); a `marcacao` diz, chave a chave conferida, se passou a valer no
    lugar da aba e por que não. Recusa `{ok: false, motivo}` e, quando a recusa é de UMA usina, também `usina_id` e
    `usina_supervisorio` da culpada (a tela tira só ela do lote e reenvia o resto, no máximo 3 vezes; antes uma recusa
    derrubava até 50 chaves sem dizer de quem era): 400 o pedido torto (código fora da dimensão ou de outro tipo, strings
    que não são inteiro maior que zero, usina fora do Registro mestre), 409 o conflito com o gravado (selo velho, chave
    de outra usina, código em outro inversor, UG de mesmo número com outro código, inversor de outra chave, sem strings
    que já cobrem o Registro, a chave fora da aba E do livro, a chave irmã da aba fora do livro), 503 o banco, a
    dimensão, a aba (para semear) ou o token fora.
  - As regras (`estrutura_usina.salvar_depara`, num só `_gravar`): **remendo**, nunca exclui o que não veio (código,
    cabine ou strings vazios no pedido = não mexe); o selo de cada usina conferido antes de mexer em qualquer uma (um
    que não confere recusa tudo); a chave liga à usina como o `ligar_supervisorio`.
  - **A chave que o livro ainda não tem nasce SEMEADA PELA ABA (2ª revisão, 20/10/2026), antes do remendo**
    (`_semear_pela_aba`, o mesmo `estrutura_da_aba` do "Ligar pela aba"): Full O&M, String Box, o nome de exibição, as
    UG e TODOS os inversores da aba com o nome, as strings e o kWp da aba. Caso: a Coração 2 (usina 77, nada no Nexus)
    nascia com Full O&M = Não, só com os inversores que leram naquela hora e com o nome do código ("Inversor 2.1" no
    lugar do "Inversor 1.1" da aba, a coluna do BD); marcada, a usina saía de trackers, PR e ocorrências e o INVERSOR04
    parado deixava de ser esperado. A semeada só é a chave da usina (`principal`) se a usina não tem uma E a aba põe a
    UFV ou as UG nela (a "Coração 2 (112)" só tem inversores; a UFV está na "Coração 2"). A cabine de mesmo nome que a
    usina já tem é a mesma; o nome de inversor que a usina já usa em outra chave ganha a chave no nome (como no "Ligar
    pela aba": na Coração 1 e 2 as duas chaves têm "Inversor 1.1", e a 2ª semeada fica com "Inversor 1.1 · Coração 2
    (112)", que difere da aba e por isso não marca). Sem a aba lida, a chave nova é recusada (503), para não nascer pela
    metade. **A chave que não está na aba NEM no livro é recusada (409, com a culpada; 2ª revisão final, 21/10/2026):** era
    a "Nova chave" da tela (o nome que a fonte manda). Ela nunca vale no lugar da aba (os leitores não a conhecem), e
    gravada virava a chave da usina (`principal`) e prendia os códigos do Fracttal nos inversores dela: na Pharma 2 (usina
    108) vazia, a "PHARMA 2 API" criava "Inversor 2.1" a "2.6" com os THPN-PHS100-INVR2.x, e a "Pharma 2" da aba com os
    mesmos códigos levava 409 para sempre (o de-para não solta código). A tela tirou a opção; a chave nova liga na Base >
    Equipamentos das usinas, à vista. **A chave da aba que é da MESMA usina e não está no livro nem no pedido recusa a
    usina** (409, `irmas_da_aba`: a usina de cada chave da aba pela regra do "Ligar pela aba", a Usina Fractall nas
    Ligações, com o livro vazio; `telas_equipamentos._irmas_da_aba`): a regra do kWp dividiria o Registro só pelas strings
    das chaves do Nexus (a Coração 2 sozinha, 250 → 812,5 kWp, e a usina somaria 6.500 nos leitores contra 3.250). Na aba
    real a Usina Fractall da "Coração 1 (111)" é "Thopen - Coração 1 - SC", que as Ligações não têm: lá quem pega é a
    tela (as duas plantas estão na `pv`, e ela pede para salvar juntas). Medido com as Ligações reais: nenhuma das 66
    usinas da medida abaixo é recusada por isto.
  - **O inversor** se acha pela chave + nome no supervisório; sem ele, pelo NOME dentro da usina (o `nome` do pedido,
    senão o da aba para a chave e o nome no supervisório): o achado SEM nome no supervisório ganha o do pedido (os 214
    da aba de 13/10 sem ele, a Aquiraz 1 entre eles); o achado em OUTRA chave da usina recusa a usina (409, "o de-para
    dele é por essa chave": a Cambé pela chave de exibição "Cambé", com os inversores na "Cambé (85)"); o achado na
    mesma chave com OUTRO nome no supervisório também recusa (409: trocar o nome no supervisório é na Base > Equipamentos,
    à vista). Sem nenhum, o novo nasce com o `nome` do pedido, senão o da aba, e só então o "Inversor N.M" do código (o
    número do CÓDIGO, nunca da descrição: pela descrição com a marca, 2,2% de acerto na frota). O nome do que já existe
    NUNCA muda (decisão 5: é a coluna do BD).
  - **Só vale no lugar da aba o que difere da aba APENAS pela regra (2ª revisão, 20/10/2026; a decisão 1 do Levi era
    marcar toda chave salva, e a revisão provou o estrago na Coração 2 e no que a tela Equipamentos já listava: 103 de
    263 chaves diferentes em 13/10).** Depois do remendo, cada chave do pedido ainda não marcada é comparada com a aba
    (`comparar_chave`, que dá cada diferença com o `tipo`) e só marca se TODA diferença for da regra (`fora_da_regra`):
    as strings corretas; o kWp de inversor e de cabine que a regra calculou (linhagem `real_por_string`/
    `contratual_por_string`); a cabine pela CABN (a cabine que só o Nexus tem e a do inversor que mudou de UG têm o
    código; a UG que só a aba tem vale quando todas as UG vivas já são CABN); a potência da UFV quando vem do Registro
    mestre e o "N de Inversores" da UFV, que o Nexus conta (com a aba real a "Itajá" tem 2.596,16 × 2.596,0 e "—" × 8:
    só marca por isto); e o "Código Fracttal" (que a comparação nem olha). Qualquer outra (Full O&M, String Box, nome do
    inversor, exibição, nome no Fracttal, cliente, inversor de um lado só, a chave fora da aba, a UFV em outra chave)
    GRAVA a estrutura, NÃO marca e vai nos avisos (`nao_marcada`: "não vale no lugar da aba porque: ..."). A chave já
    marcada não é mais conferida (fica marcada, menos no caso da usina segura abaixo). A aba que não se leu (a rota manda
    `None`) não marca nada.
    **A usina vale por INTEIRO ou nada (2ª revisão final e 3ª revisão, 21/10/2026; `_marcar`):** todas as chaves da usina
    que ainda seguem com a aba são conferidas JUNTAS (as do pedido, a da UFV e das cabines e as outras com inversor no
    Nexus ou na aba) e só marcam se TODAS passarem, **sem exceção**; a que não passa segura as outras (`nao_marcada` com
    "“X”, da mesma usina, não vale(m) no lugar da aba, e a usina vale por inteiro ou nada", e um aviso da usina com
    quanto os leitores somariam se só as outras marcassem). Por quê: a regra recalcula o kWp da usina inteira, e marcar
    só parte deixava os leitores misturando a UFV e as UG do Nexus com inversores da aba (a Assis só com a Skid 1: UFV
    6.296 e inversores 6.446,0, +2,4%; a Rodrigues II: 2.116,8 × 2.339,4; a "Itajá" marcada sozinha com a UG 01 excluída
    e os inversores da Itaja 1, da aba, apontando para ela). Até a 3ª revisão a chave do pedido IGUAL à aba marcava
    sozinha ("os leitores não mudam com ela"), e era a porta do estado parcial: a Itaja 2 marcada sozinha e, no Salvar
    seguinte da Itaja 1 com 20 strings, levando 316,18 por inversor aos leitores (2.596 ÷ 156 × 19) ao lado da UG 02 da
    aba com 1.298,08. **A já marcada numa usina que fica segura:** se este Salvar mudou a visão dela (o que ela leva aos
    leitores, linha a linha contra a do começo do Salvar), ela VOLTA para a aba (`substitui_aba = 0`, aviso
    `nao_marcada` "valia no lugar da aba e voltou para a aba: este Salvar mudou o que ela leva aos leitores..."; na
    `marcacao`, `marcada: false`); é a mesma mistura pela outra porta (a chave marcada na Base > Equipamentos, ou a
    principal marcada sozinha antes desta regra). Se a visão dela não mudou, fica como está (tirá-la mudaria os leitores
    sem motivo). Na Itajá salvando só a Itaja 1, as três marcam (a Itaja 2 é conferida junto). A chave da UFV, que não é
    planta da API PV, entra sempre na conferência: sem ela a UG com o código da CABN e o kWp da soma ficariam fora dos
    leitores.
  - **Cabine = sempre a CABN do Fracttal** (decisão 2): "UG NN" pelo número da CABN (CABN2 → UG 02; o nome segue "UG"
    porque os leitores só reconhecem cabine assim); adota a UG de mesmo número ainda sem código (a da aba), cria se não
    houver; a UG de mesmo número com OUTRO código recusa a usina (Ipixuna do Pará, usina 56: a Santa Cecilia 1 é
    IPX100-CABN1 e a 2 é 2C-IPX100-CABN1, duas árvores no Fracttal, as duas "UG 01"). **A cabine SEM código do Fracttal
    e sem inversor no Nexus sai, a cada Salvar da usina (ajuste B; 3ª revisão: não só a que este Salvar esvaziou):**
    exclusão lógica (`excluido = sim`, conta nas `mudancas`, vai em `cabines_excluidas` e no aviso `cabine_excluida`).
    Pharma II: os inversores vão para a UG 02 da THPN-PHS100-CABN2 e a UG 01 da aba sai. **O guarda da cabine órfã**
    (21/10/2026), com a chave da UFV e das cabines no lugar da aba: (1) a UG para a qual uma chave que segue com a aba
    ainda aponta na aba ("Equipamento Parente") fica, com o aviso `cabine_sem_inversores` (sem ela os inversores dessa
    chave ficariam numa UG que os leitores não têm), e sai no Salvar em que nenhuma chave que segue com a aba apontar
    mais para ela; até a 3ª revisão só a recém-esvaziada era olhada, e a UG 01 da Itajá que o guarda segurou ficava no
    Nexus para sempre, indo aos leitores vazia e com o kWp antigo depois que a Itaja 1 passava a valer. (2) Com a chave da
    UFV JÁ valendo no começo do Salvar, mover de cabine os inversores de uma chave que seguia e segue com a aba **recusa a
    usina** (409, com a culpada: "a chave da UFV vale no lugar da aba e “X” segue com a aba: mover os inversores de “X”
    de cabine deixaria a UFV e as UG dos leitores sem fechar; acerte “X” ou salve as chaves juntas"): a "Itajá" marcada
    na Base e a Itaja 1 (Full O&M diferente na aba) levada para a CABN2 deixava a UG 02 com 2.596 kWp nos leitores e só
    os 1.298,08 da Itaja 2 apontando para ela. Com a Itaja 1 acertada, o mesmo Salvar marca as três e a UG 01 sai. Por
    quê, leitor a leitor: na **disponibilidade** da plataforma (`plataforma/disponibilidade.py`,
    `montar_catalogo`) toda linha UG entra em `ugs`, com kWp ou sem, e `n_cab` conta; a UG 01 vazia daria 2 cabines à
    Pharma II e desligaria a régua "site agrupado com 1 cabine por usina → a Cabine N é a usina N"
    (`disponibilidade.py:415`; a THPN-PHS100 é um site só para as Pharmas 2, 3 e 4); a cascata por inversor usa o
    "Equipamento Parente" e não muda. O **gêmeo** só usa a UG como agrupador quando a usina não tem UFV (a visão sempre
    tem). A cabine COM código do Fracttal (uma CABN) nunca sai por este caminho: fica, com o aviso
    `cabine_sem_inversores`. **Cabine cujo nome não é "UG NN"** (a "UFV" da Aparecida do Taboado, usina 11, e a "PEI" da
    usina 85, vindas do "Equipamento Parente" da aba no "Ligar pela aba") fica fora da conta do kWp e NÃO sai como linha
    de UG na visão (`visao_da_usina`): uma linha de Equipamento "UFV" com o kWp dela (458) seria lida pela plataforma e
    pelas Falhas como a usina (2.422); aviso `cabine_fora_do_padrao`. O inversor dela segue com o "Equipamento Parente"
    que tem.
  - **Ativo do Fracttal:** o `equipamento_id` é DERIVADO do código no servidor (`equipamento.equipamento_id`), nunca o do
    pedido, e o código tem de ser membro da `dim_equipamento` (o THPN-PHS100, sem usina na dimensão, é membro e liga);
    a dimensão com outro ID para o código recusa. Inversor só INVRn.m, cabine só CABNn. Um código num inversor vivo só
    da frota, conferido depois de aplicar (a troca entre dois inversores passa; a culpada é a usina que o recebeu).
  - **kWp, a regra do Levi, na usina INTEIRA** (todos os inversores vivos, não só os do pedido: na Itajá, só a Itaja 1
    daria 649 kWp por inversor em vez de 324,5): kWp do Registro mestre (`potencia_real` × 1.000; sem a real, a
    contratual, decisão 3 alterada em 20/10) ÷ Σ strings corretas × strings do inversor, inclusive o kWp que era
    `informada`; a cabine = a soma dos inversores dela, dos valores sem arredondar (a Pharma II fecha 990,0). O Registro
    divergente da aba (Linhares 1 ×3,19, Diamantino ×0,5, Coração, Assis 6.296 contra 6.483,4) NÃO muda a regra: o
    Levi decidiu "aplica direto", e a tela mostra "kWp de hoje → novo". Nunca 0 nem vazio por cima de dado:
    - **sem a real E sem a contratual**, o kWp e a linhagem ficam COMO ESTAVAM, com o aviso `sem_potencia` (até a 2ª
      revisão viravam branco na usina inteira, o digitado à mão inclusive, e a chave marcada perdia o kWp nos leitores);
    - **o inversor vivo sem strings corretas** guarda o kWp de antes, e esse kWp é DESCONTADO do Registro antes de
      dividir pelos que têm strings: a usina continua somando o Registro (aviso `sem_strings`, com os nomes e o kWp de
      cada um). Sem o desconto a Sapopema, com 2 dos 20 sem strings, ia a 3.515,6 kWp contra 3.196 (+10%); com ele, os
      18 ficam com (3.196 − 319,6) ÷ 288 × 16 = 159,8 e a usina soma 3.196,0. Se o descontado já cobre o Registro, a
      usina é recusada (409, não sobra kWp). A tela faz a MESMA conta (`plataforma/static/depara_tabela.js`).
    O kWp e a origem vêm do `_usinas` da tela (o Registro DESTA máquina: o servidor e o PC podem divergir até o
    Publicar, ver "dois donos" acima).
  - **Conferido:** `fracttal_ligado_por` = `conferido` ou `sugestao` (com código; sem código, vazio); `conferido_em` =
    a hora (UTC) da 1ª vez com aquele código (conferir de novo não muda nada; desconferir apaga).
  - A visão leva o "Código Fracttal" (inversor e UG) depois dos IDs; os leitores de fora (a plataforma
    `estrutura_nexus.py`, o gêmeo, o coletor) mudam no mesmo trabalho, e o `sobrepor` herda a grafia da aba (acima). O
    "Usina Fractall" da visão sai COMO as Ligações o escrevem (só sem as pontas, nunca com o `texto`: 21/10/2026, a Belo
    Jardim acima).
  - **Prova:** `tests/test_base_equipamentos_depara.py` (51 casos; os 3 da 3ª revisão de 21/10, que falham no código
    de antes: a "Itajá" já valendo e a Itaja 1 movida de cabine recusada com 409 (e, acertada, as três marcam e a UG 01
    sai), a UG vazia que o guarda segurou saindo quando a Itaja 1 passa a valer, a Itaja 2 já marcada voltando para a aba
    quando o Salvar da Itaja 1 muda a visão dela (e ficando quando não muda); e a diferença fora da regra sem a exceção
    da chave igual à aba. Os 11 da 2ª revisão final: a Nova chave
    recusada e a chave da aba que passa com os mesmos códigos, a Assis só com a Skid 1 conferida inteira e os leitores
    fechando, a Assis segura pela Skid 3, a Rodrigues II segura pela principal, a Itajá sem a cabine órfã,
    a Coração 2 recusada sem a irmã e as duas juntas, a Belo Jardim (os dois nomes) e o acento, a
    Taguaí, o `gravando` durante e antes da trava; e 12 mutações, cada regra nova quebrada de propósito derruba um teste:
    `scratchpad/depara/r3/mutar_r3.py`. Os 38 de antes: a regra na Itajá e na Pharma II, a contratual na
    Aquiraz 1 semeada, o kWp que fica sem as duas potências, o desconto dos sem strings e a recusa quando não sobra, a
    cabine "UFV" fora da conta e da visão, o remendo, o Conferido, a Coração 2 semeada pela aba com os 4 inversores e o
    nome da aba, a aba não lida, o nome do inversor novo pelo pedido e pela aba, o casar pelo nome sem o nome no
    supervisório, o inversor de outra chave, as três chaves da Itajá marcadas, a diferença fora da regra que grava e não
    marca — cliente, Full O&M da UFV e da chave, nome —, o inversor só do Nexus, a já marcada que fica, a CABN vazia que
    fica, o `fora_da_regra` pelo tipo, as recusas com a culpada, o código num inversor só, a comparação que ignora a
    coluna, o `sobrepor` que herda a grafia na Assis Skid 1 com os mapas da plataforma pela chave da API, a linhagem da
    tela, colunas no fim, só admin e mesma origem) e 17 mutações da 2ª rodada (cada regra nova quebrada de propósito
    derruba um teste). **Com o dado real, em memória** (a cópia do banco por GET de 20/10 e a aba real
    `BD_Performance_copia.xlsx`; nada gravado fora; script e saída em `scratchpad/depara/r2_nexus/prova_r2*` e, com as
    regras de 21/10, `scratchpad/depara/r3/medida_r3*`): Itajá 8 ×
    324,5 = 2.596,0, UG 01/02 1.298,0 com a CABN e as TRÊS chaves marcadas; salvar de novo = 0 mudanças, 0 gravações; os
    1.924 inversores das outras usinas sem nenhum valor diferente. Pharma II 4 × 169,024 + 2 × 156,951, UG 02 990,0, UG
    01 excluída, marcada. Coração 2 semeada (Full O&M Sim, 4 inversores "Inversor 1.x", o INVERSOR04 com 20 strings,
    812,5 kWp pela regra) e NÃO marcada: o nome no Fracttal da aba é vazio e o das Ligações é "Thopen - Coração 1 e 2 -
    SC". Assis Skid 1 marcada e, pela chave da API (espaço duplo), ESPERADO_INV, EQUIP_NAMES, USINA_DISPLAY,
    EQUIP_PARENTE e FULL_OM iguais a antes, POWER_INV com o kWp da regra (323,4 → 314,052: o Registro tem a contratual
    6.296) e o FRAC_COD_INV novo; pela grafia do Nexus, nada. Sapopema marcada, soma 3.196,0. Aquiraz 1: os 10 ganham o
    nome no supervisório pelo nome do cadastro e 326 kWp (contratual), e a chave NÃO marca (a aba não tem o nome no
    supervisório: a comparação vê 10 inversores de cada lado). **Medida da marca nas fontes da API PV** (pv, semp,
    alveslima, 2capi: as 130 plantas do levantamento salvas como a tela mandaria, com o nome do cadastro, as strings do
    Nexus ou da aba, o código e a CABN verdadeiros e Conferido; regras de 21/10, com as Ligações reais): 119 chaves do
    pedido em 66 usinas; **84 marcadas, 23 não (diferença própria), 6 seguras pela usina, 6 recusadas**; fora do pedido,
    as 43 chaves da UFV conferidas e 32 marcadas; 48 usinas inteiras no lugar da aba, 15 sem nenhuma chave marcada, e
    **0 no estado misto** (eram 6: Junco, Parelhas, Rodrigues I, Saturnino 1, Senador Elói I, Tanabi, com a UFV do Nexus e
    inversores da aba). Na 2ª rodada (as regras de 20/10) eram 92 marcadas, 21 não e 6 recusadas, com 39 das 43 da UFV
    marcadas. A 3ª revisão (sem a exceção da chave igual à aba, a volta da já marcada, o 409 e a limpeza das UG vazias)
    não muda a medida (84/23/6/6, 0 misto, nenhum 409 novo): o banco de 20/10 não tem chave marcada. A limpeza tira 18
    cabines contra 17: a mais é a UG 01 da Nova Londrina 2 (usina 103), vazia e sem código já antes do Salvar, e nenhum
    inversor da aba aponta para ela (os 10 estão na UG 02). Por que não: inversor só no Nexus 10 (o "(OLD)", "Cancelado", "xxxx" que a API ainda lista: a tela tem o
    "deixar de fora"), nome no Fracttal 6 (Brodowski "(sem Classificação 1) BWK100" nas Ligações, Coração, Santo Antônio
    da Platina), a UG que só a aba tem 5 (Ouro Branco 1 a 5), o nome de exibição 2 (Taguaí 1 e 2, a regra nova), nome do
    inversor 1 (Coração 2, o "· chave"), a cabine só no Nexus 1, a UFV em outra chave 1. As seguras: Junco 2.1 a 2.3 (pela
    Junco 1), Primavera 2 (116) (pela "Primavera 2"), Rodrigues 2.2 e 2.3 (pela 2.1). A Belo Jardim marca e os leitores
    seguem com "Thopen - Belo Jardim  1 - PE" (espaço duplo). As recusadas: Ipixuna do Pará (as duas CABN1, 3 chaves), Jucurutu (o "INVERSOR01 - OLD" da fonte casa com o de outra
    chave, 2) e Pharma 2 pela grafia da fonte de 20/10 ("Inversor 1.1" contra o "INVERSOR01" gravado, 1). Fora da conta: 4
    plantas sem chave na aba (a tela pede a escolha: Itaja 1/2 (228/229), Pharma 3/4) e 2 usinas com código repetido
    (Embu Guaçu, Indaiatuba: pendência "inversor repetido" na tela). **Gravar em produção é com o OK do Levi**; a
    Pharmas espera a foto do Fracttal renovada (PHS100 × PHS200/300/400, `nexus/dados/CLAUDE.md`).
- **Provas (13/10):** `tests/test_base_equipamentos.py` (20, entre eles a usina montada igual à aba: a comparação diz
  igual e `agrupar_aba(sobrepor(aba, visão)) == agrupar_aba(aba)`); na plataforma, `tests/test_estrutura_nexus.py` (os 13
  mapas do cadastro iguais com a estrutura igual à aba, e a esperada acompanha o Nexus quando muda); no gêmeo e no
  coletor, os testes de cada um. Com dado real, numa cópia (5071) com o banco só na memória: a **Altair** (6 chaves, 5
  cabines, 40 inversores) pelo Trazer da aba deu "igual à aba" nas 6 e, com as 6 no lugar da aba (46 linhas na visão), o
  cadastro da plataforma carregado com a aba real ficou com os **13 mapas iguais** (a UFV difere em 5e-12 kWp: a aba guarda
  o resultado de uma fórmula, o Nexus usa a potência real do Registro mestre).
- **Só administrador** (o Registro mestre e a gravação no banco; `_tela`); os POST só da própria página
  (`_de_outro_site`). Prova: `tests/test_base_equipamentos.py` (a aba agrupada, chave de uma usina só, desligar sem
  apagar inversor, criar/atualizar/excluir com ID que não volta, as recusas sem gravar nada, selo, sem token e banco
  fora, regra 8, ativos, a tela, a decisão do Fracttal pelas Ligações, catálogo e menu). Conferido em 13/10 numa cópia
  (5071) com o Registro, o Fracttal das Ligações e o banco reais para LER e a gravação só na memória de um proxy (o livro
  no banco é para sempre): Araputanga 1 de ponta a ponta (chave pela sugestão, Trazer da aba: 1 cabine, 10 inversores e
  236 strings, potência fechando com a real, os 10 ativos pelo nome, salvar duas vezes = "Nada mudou") e Ipixuna do
  Pará 1 à mão (chave digitada, 2 cabines, 8 inversores gerados, distribuir fechando 6.804 kWp, nome repetido recusado),
  no celular sem rolagem lateral e no tema claro.

## As listas montadas uma vez por versão (`telas._lista`, `cadastro/_lista_linhas.html`; 19/10/2026)

Levi, 19/10/2026: "faça 2 e 3" (o Registro mestre entre os pesos do Nexus). O Registro mestre são ~300 usinas x 53
colunas (a maioria escondida: o seletor de colunas mostra sem recarregar), e a página tinha 1,3 MB e gastava 0,31 a
0,42 s de processador a cada visita no PC, para a mesma tabela.

- As linhas de toda lista do cadastro (Registro mestre, Clientes, Equipes, Regiões de campo, Colaboradores) saem do
  `_lista_linhas.html` e ficam guardadas (`_LINHAS_PRONTAS`, as últimas 40) pela chave: o arquivo do armazém e a marca
  dele (muda a cada gravação, inclusive por fora do Nexus), a lista, o dia (os avisos olham a data), a busca, os filtros,
  as colunas à vista e a raiz do endereço. Gravou, a próxima visita monta de novo.
- Sem o espaço em branco entre as células e sem o `class=""` vazio: a mesma tabela, 936 KB.
- Depois: 0,02 a 0,03 s por visita. Prova: `tests/test_pcm_e_registro_leves_19_10.py` (montadas uma vez; outra busca e
  outras colunas, outra chave; gravou, monta de novo).

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
- **A decisão à mão vai como "manual (dd/mm)", sem quem** (13/10/2026): até então ia o `quem` da decisão, e no login
  pelo Fracttal o `_quem()` era a sessão inteira (e-mail, nome e perfil) e caía no `casou_por` de um livro de leitura
  aberta (regra 8). Agora o `_quem()` é só o e-mail (ou "admin"), que fica na decisão local (`de_para_regras.json`) e a
  seção Ligações mostra; o banco recebe só o dia. As decisões guardadas até 13/10 tinham "Levi (pelo Claude)" e
  "Levi (aprovado no chat em 06/10/2026)": o próximo Publicar no banco já sai sem o nome.
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
- **Ligações entre bases**, a seção do fim de Base → Governança de dados (`/t/base/governanca#ligacoes`; até 11/10/2026 a tela `/t/base/ligacoes`, que hoje redireciona para lá com os filtros — Levi: "essa visão de Base > Ligações entre bases vire uma seção no final de Governança de dados"; só admin com o cadastro ligado, os outros veem o aviso): "Ler as bases de novo" grava `de_para_atual.json` (as
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
