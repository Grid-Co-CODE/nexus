# CLAUDE.md — Coletas (Performance > Coletas)

O Conversor Grid Co. (o .exe do backoffice) dentro do Nexus (Levi, 11/11/2026: "Quero uma aba na performance do nexus de
controle de coleta! monte com base no .exe"; antes: "faz a mesma coisa que faz nas coletas só que lá no nexus, ficaria mais
fácil para todo mundo, e leria direto do PG!"). A pessoa solta os relatórios de portal, SCADA ou datalogger; a tela
reconhece a fonte e a usina pelo conteúdo e devolve a planilha para colar no BD_Performance ou no BD_Thopen. **Nada vai
ao BD nem ao banco por aqui**: o BD segue a fonte (regra de 11/10/2026) e o `sync-xlsx?replace=true` da coleta apagaria
qualquer gravação direta na subida seguinte. O .exe segue de reserva até esta tela estar redonda (regra de 04/10/2026).

## Peças

| Arquivo | Para quê |
|---|---|
| `_motor/conversor/` | o motor do Conversor, **cópia idêntica** (byte a byte) da pasta da coleta (`coleta API PV\ferramentas\conversor\conversor`, menos o `app.py` da janela). Não edite aqui: mude lá e rode `python ferramentas/sincronizar_conversor.py` |
| `motor.py` | põe `_motor/` no caminho como o pacote `conversor` (é como os leitores se importam); importe-o antes de qualquer `conversor.*` |
| `pg.py` | o BD lido do banco com a cara do `nucleo.BD` do Conversor (`abas`, `aba`, `estilos`, `lido_em`), com o mapa de fórmulas por cima; uma leitura por subida, guardada 10 min |
| `servico.py` | uma `Sessao` do Conversor por navegador (a pasta temporária dela, os envios em lotes, o reconhecimento em fundo, o BD em Excel solto junto, o separar formato novo) e a leitura do relatório de furos |
| `nexus/torres/performance/coletas_tela.py` | as rotas: a casca (`/coletas`), a página do Conversor (`/coletas/app`), `/coletas/api/<método>` (a lista `METODOS`), `/coletas/arquivo`, `/coletas/planilha/<i>`, `/coletas/furos` |
| `furos_r01.py` | o motor dos furos de coleta: a regra do R01 da analista (estados, d-2, Ultragaz, COS, cruzamento de 6 h), sem ler arquivo nenhum |
| `furos_fonte.py` | de onde o motor tira cada dado no servidor (BDs do banco, paradas do COS, outubro congelado) e a conta em segundo plano |
| `furos_conf.py` | as validações de todos (`confirmacoes_furos.json`) e as paradas congeladas do HTML R01, em `<NEXUS_DADOS>/coletas/furos/` |
| `nexus/torres/performance/furos_tela.py` | as rotas da aba Furos de coleta: `/coletas/furos-de-coleta` (a tela), `/coletas/furos/r01` (a conta), `.../conf` (ler e gravar validação), `.../importar` |
| `templates/performance/coletas_furos.html`, `static/coletas-furos.js` e `.css` | a aba Furos de coleta, tela do Nexus (não é gerada): a conta da tela da analista no desenho do DESIGN.md |
| `templates/performance/coletas_app.html` e `static/coletas/furos.js` | **GERADOS** da tela do .exe por `ferramentas/portar_tela_conversor.py` (as trocas e o porquê de cada uma estão lá). Não edite: mude o .exe e rode o `sincronizar_conversor.py` |

A regra (leitores, regras de colar, planilha de saída) é a do Conversor: leia o `CLAUDE.md` da pasta do Conversor na
coleta antes de mexer num leitor. Aqui só mora o que muda por ser um servidor.

## O BD vem do banco — e por que precisa do mapa de fórmulas

O banco (`db_performace`) tem, de cada aba, o número da linha no Excel (`row_number`), o cabeçalho, os valores e a hora
da subida (`updated_at`): basta para dizer "cole na célula C123" e não cobrir dado. **Não tem fórmula nem cor**: o
`sync_gridco_api.py` da coleta sobe só valores (decisão de 27/08/2026), e a fórmula sem valor em cache chega vazia. O
Conversor depende de toda fórmula, célula a célula (a mesma coluna é valor num dia e fórmula no outro: a Energia da Nova
Iguaçu é digitada até 08/11/2026 e `=SUM(T_Nova_Iguaçu[[#This Row],...]])` a partir de 09/11): não escreve em célula que é
fórmula (o IPOA da Vitesse = Hortina; o da Salvales de 21 a 25/10 = Carosa) e parte o bloco de colar onde ela aparece.

A escolha do Levi (11/11/2026, "Aceito também sua recomendação"; 16/11/2026, "Faça ler pelo PG mesmo", e a subida da
coleta passou a levar o mapa): **a coleta sobe, logo depois de cada BD, o livro `bd_formulas`** (em `CONHECIDAS` do
`nexus/dados/catalogo.py`). Quem escreve é o `src/mapa_formulas.py` da coleta, chamado pelo `sync_gridco_api.py` depois
da linha "REAL" do BD (o log do fechamento mostra "mapa de formulas: OK ..."); a falha no mapa nunca segura o BD.
- `formulas_bd_performance` / `formulas_bd_thopen`: 1 linha por **trecho** de células com fórmula seguidas na mesma
  coluna — `aba, coluna (1-based), linha_de, linha_ate (do Excel), cabecalho, formula (o texto da 1ª célula, sem "="),
  subida_em`. Uma linha por célula seriam 167 mil linhas toda noite; em trechos são ~1.400 (Excel de 16/11/2026). O
  texto é só para quem lê o banco: o Conversor só pergunta SE a célula é fórmula (`nucleo.formula`). Sem o "=" porque
  no .xlsx do mapa o openpyxl o gravaria como fórmula de verdade, que chega vazia.
- `abas_bd_performance` / `abas_bd_thopen`: 1 linha por aba do Excel naquela subida — `aba, linhas, colunas, subida_em`.

Por que o valor sozinho não basta (medido 16/11/2026, os dois Excel contra o banco): desde 01/10 são 7.319 células com
fórmula no BD_Performance e 16.594 no BD_Thopen, e o banco traz o valor de cada uma como número digitado (183 vazias, no
BD_Thopen). Sem o mapa, o bloco de colar levaria a "Energia Produzida" (`=SUM(T_...[[#This Row],[Inversor 1.1]:...])`),
o IPOA DEF e a Validação como valor parado: colado, a energia ficaria errada quando os inversores fossem preenchidos.
**Prova do mapa** (16/11/2026, sem gravar nada): o mapa do Excel de hoje + o BD do banco, lidos por este `pg.py`,
marcam como fórmula as mesmas 61.700 células do BD_Performance e 77.308 do BD_Thopen que o Excel (0 diferença; a única
"a mais" era uma fórmula de matriz da Sete Lagoas, que o openpyxl devolve como objeto). Ensaio no `zz_teste_claude_apagar`:
o importador devolve o mapa igual (o texto com quebra de linha volta com outra quebra, sem importância).

Sem o mapa, com o mapa de outra subida (mais de 30 min antes do `updated_at` do BD) ou com um mapa sem nenhum trecho
legível (o formato mudou), **o BD do banco não é usado**: o botão do BD fica vermelho, a faixa diz o motivo, e a pessoa
solta o BD em Excel junto com os arquivos (ou clica no botão do BD) — o mesmo caminho do .exe. Mudou o formato do mapa:
**publique este leitor ANTES** de a coleta subir o formato novo (o leitor velho leria o novo sem marcar fórmula nenhuma;
por isso o "nenhum trecho legível" recusa).

- **Abas velhas:** a aba renomeada no Excel fica velha no banco (o `replace=true` só troca as abas que sobem: "Vitesse",
  "Carosa", "Salvales", "Hortina" e "SunPower" pararam em 30/09/2026; hoje são "Quixadá 2 (Vitesse)", "Aquiraz 2
  (Carosa)", "Aquiraz 1 (Salvales)", "Quixadá 1 (Hortina)" e "Cascavel (Sunpower)"). Vale só a aba da lista `abas_<bd>`.
- **A cor não sobe:** a planilha de colar sai sem o amarelo e o vermelho do BD. A regra de não cobrir dado olha o valor.
- **O banco anda atrás do Excel:** o que a equipe digitou depois da última subida não está lá. Toda conversão com o BD
  do banco leva o aviso "veio do banco, da subida de dd/mm às HH:MM: confira os dias de dd/mm em diante". A subida é a
  do fechamento das 23:30; se ele cai, o banco fica na anterior (15/11/2026: caiu às 00:12 e o banco ficou na de 14/11).

## O que muda por ser um servidor

- **Uma sessão por navegador** (`session["coletas_id"]`, nada de e-mail na chave), com a pasta temporária dela; some
  parada há 3 h ou no Limpar / Nova conversão. Os arquivos soltos não ficam no Nexus, salvo o formato que ninguém
  conhece: "separar para o Levi" grava em `<NEXUS_DADOS>/coletas/formatos_novos/` (no .exe era a pasta ao lado do BD).
- **Um arquivo por pedido** (o teto de envio do Nexus é 25 MB por pedido): a tela abre um lote, sobe cada arquivo e fecha
  o lote; as partes do mesmo datalogger ficam na mesma pasta do lote (os leitores da Apolo e da Polaris procuram as irmãs
  ali). O arquivo maior que 25 MB fica de fora com aviso.
- **A data do arquivo é a do computador de quem soltou** (`File.lastModified` -> `os.utime`): o "só dia fechado" usa a
  data do arquivo como a hora da baixa (o mensal da Sal baixado 08/11 12:41 traz o 08/11 pela metade).
- **O BD em Excel solto junto** (nome `BD_Performance*.xlsx` / `BD_Thopen*.xlsx`, ou pelo botão do BD) entra no lugar do
  banco para aquela sessão; o Limpar volta ao banco. **A leitura do banco nunca passa por cima do Excel** (12/11/2026, o 1º
  uso do Levi: o BD_Thopen em Excel entrou enquanto o banco era lido em fundo, e a leitura, terminando depois, o tirou; a
  conversão saiu com "BD_Thopen não foi lido"): a troca é sob a trava da sessão e o banco só entra onde não há Excel.
- **A sessão aberta acompanha o banco** (16/11/2026): o `estado` confere o banco no máximo a cada minuto
  (`RELER_S`), e o mapa que chegou depois, ou a subida nova, entram sozinhos. Antes, a tela aberta antes de o mapa
  subir seguia pedindo o Excel (a leitura que falhou nunca era refeita), e a aberta de um dia para o outro ficava na
  subida velha. Nunca no meio de uma conversão (o Contexto do motor usa o mesmo dicionário de BDs), nunca por cima do
  Excel solto, e o banco que falha agora não tira o BD bom que a sessão já tem.
- **Furos de coleta:** desde 16/11/2026 a conta é do Nexus (seção abaixo) e a validação é de todos, guardada no servidor.
  O relatório `Furos_Coleta_Performance_*.html` gerado fora, que subia pelo "Abrir relatório" e fica em
  `<NEXUS_DADOS>/coletas/furos/`, virou a reserva de quando a conta não sai (o banco fora na 1ª vez).

## Furos de coleta: o R01 da analista calculado pelo Nexus (16/11/2026)

Levi, com o documento `Regras_e_Cruzamentos_Furos_Coleta_GridCo_R01.md` da analista de Performance: "upgradae para a parte de coleta da
performance no nexus". Até aqui o relatório era gerado à mão no PC dela (a pasta `Gerador_Furos_Coleta`: extract2.py,
oscross.py, ocn.py, build2.py, ~3 min) e subia como HTML; cada pessoa validava no próprio navegador. As decisões do Levi:
**o Nexus vira a fonte** (a conta e as validações), **outubro congelado** (as paradas dele vêm do HTML R01), **a tela do R01
no Nexus** e **valida quem tem a tela Coletas** (fica quem e quando). E o desenho: "Pega o estilo do Nexus [...] deixar fácil
para novos usuários entenderem melhor [...] melhor espaçamento, título, leitura em F".

**O que é.** Célula = equipamento × dia. A aba **Furos de coleta** (`/t/performance/coletas/furos-de-coleta`, sub-aba da tela
Coletas, ao lado do Conversor) mostra, por usina, o que falta de geração, IPOA e GHI até anteontem (d-2), o que uma parada
explica e o que já foi validado.

**De onde vem cada coisa** (`furos_fonte.py`):
- **BDs, Info Geral e Base UFV: do banco** (Levi: "Faça ler pelo PG mesmo [...] em tese, no dia a dia, para um ser igual ao
  outro"). A leitura inteira leva ~30 s e fica guardada até a próxima subida (o `updated_at` dos livros `bd_performance` e
  `bd_thopen`). O banco tem UMA subida por noite: o que a equipe cola no Excel durante o dia só aparece depois dela. A tela
  avisa quando a subida não cobre d-2 (`fontes.bd_atrasado`): em 16/11 a última era a de sábado 14/11 23:47, e o dia 14
  inteiro aparecia como furo.
- **Aba velha:** o banco não apaga a aba renomeada. Sai a que termina antes do mês em que a maioria das abas termina
  (`furos_r01.velhas`): a "Iramaia" (parou em 31/10, hoje "Iramaia II") entrava em outubro como usina a mais. Quando o
  `bd_formulas` subir, a lista de abas dele é a régua certa.
- **Paradas de novembro em diante:** as MESMAS linhas do "Exportar CSV" da tela Ocorrências do COS, montadas pela mesma função
  (`nexus/cos/normalizacoes.csv_linhas`) sobre as normalizadas guardadas e as em andamento: é o `ocorrencias-2026-11*.csv`
  que a analista baixava, sem baixar. O COS só está ligado no servidor; sem ele a tela avisa e novembro sai sem paradas (mais
  furo, nunca menos).
- **Outubro** (OS do Fracttal + tickets, "não alterar", §6.6 do documento) e os tickets de outubro que entram em novembro
  (na prova, PEII até 04/11 e PEIII até 06/11): **congelados** do HTML R01 (`furos_conf.Congeladas`,
  `paradas_congeladas.json`). A cobertura é refeita com a regra de 6 h sobre os estados de agora. Um mês congelado só troca
  por um HTML gerado depois (o `gen` dele): importar relatório velho não desfaz.

**A regra** é a do documento da analista, portada função a função em `furos_r01.py` (o cabeçalho dele lista cada regra e o caso
que a criou): os estados o/v/x/z/p/d/a/e, d-2 sem tolerância, o último dia do mês, a régua da Ultragaz (5× a mediana), a
linha sem Usina e a data repetida, 6 h na janela 06-18 h, UFV/UG/Inversor, a OS 16493, o E1, "Geração parou" = sim, a usina
agrupada e os aliases do COS (quatro ainda "supostos", esperando a analista). Mudou a regra dela: muda lá e no caso de
`tests/test_coletas_furos_r01.py`.

**As validações** (`furos_conf.py`; `confirmacoes_furos.json` no formato do §8.4, mais `q`, quem): ficam FORA do banco porque
o comentário do analista e o nome da pessoa não podem ir para fato de leitura aberta (regra 8 do `nexus/dados/CLAUDE.md`).
A REGRA PERMANENTE da analista (13/11/2026): nunca perder o que está salvo. Por isso: importar só acrescenta ou atualiza (vence o
`t` mais recente); cópia em `confirmacoes_backup/` antes de importar e na 1ª gravação do dia; toda mudança vai para o
`historico_confirmacoes.jsonl` (o antes, o depois, quem, quando); a tela manda só o que mudou, com o `t` que viu, e se outra
pessoa gravou a mesma chave antes NADA do pedido entra (409) e a tela recarrega; arquivo ilegível nunca é sobrescrito.
**Antes de mexer no formato ou na fusão, rode os testes de `furos_conf`: perder validação é o erro que não pode acontecer.**

**A tela** (`performance/coletas_furos.html`, `static/coletas-furos.js` e `.css`): a conta da tela da analista (itens, "UFV toda",
Geração/ETM, validação por dia, vigência, sugestões, CSV) portada do template2.html dela, no desenho do `DESIGN.md`. Os
filtros são os do `static/filtros-os.js` (o padrão do Histórico de OS). Não tem "Salvar HTML"; Exportar e Importar ficam
em "Validações". Saíram de propósito o filtro em cada coluna (o painel cobre) e os emojis.

**O desenho de 19/11/2026.** Levi: "ao clicar, tá aparecendo uma linha grossa por campo que tá faltando [...] esse motivo
não precisa tanto se a gente tem informação [...] linka com as ocorrências de normalizações ou que está em aberto que a
gente tem no COS [...] se naquele dia teve desligamento, foi de que horas até que horas [...] mais visual também, por
cliente [...] por tamanho do furo [...] diminua as informações". Medido na bancada antes: abrir a Crateús dava um painel
de 4.989 px com 40 linhas de validação (uma por item, cinco campos cada). Ficou assim:
- **a cor é a CAUSA do furo pelo COS** (2ª rodada do mesmo dia; Levi: "é justificado se foi queda. Agora, se foi falha
  de comunicação, a gente tem que resolver isso [...] uma cor para o que foi justificado em questão de geração, uma cor
  que tem furo e foi falha de comunicação [...] e conseguir filtrar esses pontos [...] melhora o contraste"). Na tira, no
  mapa e nas barras: **roxo** (o token `--semcom`) = furo pendente num dia em que o COS registrou falha de comunicação
  DA USINA (qualquer trecho do dia; a usina gerava e o dado não veio: resolver); **rosa** (`--anomalo`) = a falha de
  comunicação que o COS registrou só nos inversores com furo (desde 24/11, abaixo); sem justificativa no COS, **vermelho** = a usina
  toda sem dado no dia (o item "UFV toda", ou todos os equipamentos de geração) e **laranja** = parcial, um inversor ou
  alguns (3ª rodada: "vermelho total é porque caiu a usina inteira [...] tal cor, é porque caiu parcialmente"); com um
  **traço azul embaixo**, o COS tem uma queda curta no dia, que não justifica; **vazado** = falta só IPOA ou GHI;
  **azul** = a usina toda justificada por queda (a regra do R01; a queda que pegou só parte da usina, com o resto da
  geração com dado, é verde desde 24/11); **verde cheio** = completo OU validado, a mesma cor ("a validação já
  tem que ser automática [...] teve todas as gerações, automaticamente vai ficar verde": o dia com todo o dado é o
  validado automático; o motivo da equipe continua para o furo que não tem dado).
  Perguntado, o Levi **manteve as 6 h de sol** para a queda justificar (19/11/2026, com os números: 123 dias de furo em 35
  usinas só com queda curta, mediana 1,7 h): a conta do R01 não mudou. Atenção: a falha de comunicação EM ABERTO pinta
  todos os dias desde que abriu; em 19/11 eram 35 abertas, 21 há mais de 30 dias (Ipixuna 1 e 2 desde 09/01, Crateús
  desde 23/08): o mês inteiro dessas usinas sai roxo, e o registro velho no COS é ele mesmo um ponto a resolver;
- **sem KPIs no alto** (3ª rodada: "Esses KPIs aí não servem de nada, sendo que tem a mesma coisa sendo dita embaixo"):
  **a legenda é FIXA no alto da lista ao rolar** (`position:sticky` embaixo do `--topo`), com quantas usinas, a troca
  Tabela/Kanban e cada cor com os dias dela; o clique na cor troca a Situação por aquele ponto e o 2º clique volta ao
  padrão. Ordem pedida: o resto à esquerda (completo/validado, justificado por queda, falha de comunicação) e **os
  vermelhos juntos à direita** (usina toda, parcial, com queda curta, só IPOA ou GHI). Conta com os outros filtros e sem
  o de Situação. A completude foi para a linha das fontes. Saíram também a faixa colorida à esquerda de cada linha ("essa
  barra lateral [...] eu não tô entendendo para que serve"), o "Mais números", os selos e a visão "Detalhe por
  equipamento" (o CSV continua com tudo). **Embaixo da legenda prendem também o cabeçalho da tabela e o de cada coluna
  do Kanban** (4ª rodada: "não deve sumir o cabeçalho [...] nem da tabela, nem do Kanban"): a altura da legenda vai
  para `--fr-cab-h` (um `ResizeObserver`) e os dois prendem em `--topo + --fr-cab-h`. Para isso a caixa da tabela NÃO
  rola de lado na tela larga (rolagem própria prende o `sticky` nela); abaixo de 900 px volta a rolar. O "Tamanho do
  furo por cliente" recolhe ("pode ser recolhível também, para ocupar menos espaço"), e o navegador lembra a escolha;
- **a lista abre só no "Furo pendente"** (o padrão da Situação; Levi: "tirasse dessa lista [...] o que está
  justificado"); a etiqueta mostra o filtro e o × traz as outras. Opções de Situação para cada cor da legenda;
- **Kanban** ("dá para ter em Kanban também?"): uma coluna por causa (falha de comunicação, usina toda, parcial, só IPOA
  ou GHI; e "sem furo pendente" quando o filtro as traz), a usina na causa com mais dias; o cartão tem a tira e abre a
  usina na tabela;
- **o peso do furo por cliente** (era o "tamanho", a soma dos dias; virou peso em 24/11, abaixo): uma barra por cliente
  (por carteira no BD_Thopen), o maior peso em cima, nas cores da tira. O clique filtra;
- **a lista**: usina, a **tira do mês** (o `title` de cada dia diz a causa e a ocorrência do COS com as horas), o furo
  pendente em dias com o que falta numa linha, e os dias com falha de comunicação. Ordem: o maior furo primeiro;
- **a aba "3 · Furos de coleta" do Conversor saiu da tela do Nexus** ("o furo de coleta no conversor pode tirar. Se já
  tem furo de coleta do lado, não tem porque ter"): uma troca no `ferramentas/portar_tela_conversor.py` esconde o botão
  da aba; no .exe ela fica;
- **o Mês** fica na linha e na altura da busca e do Filtros, sem o rótulo em cima ("tá desalinhado [...] tá feião");
- **o detalhe**: "O que o COS registrou" (só as dos dias com furo e as que explicam o dia; "Ver as N" mostra todas):
  início → fim ou "em aberto", a duração, a falha, o equipamento, a OS, se a geração parou, e a etiqueta "explica o dia"
  ou "no dia do furo". Embaixo, o **mapa do mês** com a linha do COS no alto, e a validação NELE: clica-se no dia com
  furo (ou no nome da linha, que marca os pendentes dela) e uma barra só valida (motivo, vigência, comentário). Item com
  todos os dias de furo marcados recebe o motivo do item inteiro (`setConf`, com a vigência); marcado em parte, só os
  dias, neste mês (`setDays`), como o "Só alguns dias" da analista. Comentário sem motivo grava só o comentário. **Os
  inversores com o MESMO furo nos mesmos dias (mesmas cores, mesma validação, mesma marcação) viram uma linha**: em
  novembro, 500 linhas de inversor viraram 75; a Crateús, de 40 para 2 de inversor (o painel caiu para 1.297 px). As
  funções do modelo da validação (`setConf`, `setDays`, `setObs`, a sincronização) não mudaram.

**O desenho de 24/11/2026** (Levi, na Nova Xavantina 1: "está vindo umas informações que dão falso negativo"). Só a
tela (`static/coletas-furos.js`, `.css` e o template); a conta do R01 não mudou. Medido antes com o banco e o CSV do COS
de 23/11: a Nova Xavantina 1 tinha 16 dias roxos e 6 azuis, e nenhum dos dois era o que parecia.
- **O alcance da falha de comunicação** ("é só o inversor com falha de comunicação, o resto está verde [...] tem que ter
  uma cor só para inversor"). A falha do Inversor 2.4, EM ABERTO no COS desde 22/06, tocava todos os dias de novembro, e a
  regra antiga pintava de roxo todo dia com furo, até o do IPOA. Agora a ocorrência que cita inversores no campo
  Equipamentos ("Inversor 2.4", "UG 1": `alvoCom`, a mesma casa de nome do `_casa_equip`) vale só para eles. Dia com TODOS
  os inversores pendentes citados = **rosa**, "falha de comunicação no inversor" (o resto do furo do dia, como o IPOA,
  continua no mapa como sem dado); se os citados são a geração inteira (a usina de um inversor só), é roxo. Sem inversor
  citado (vazio, cabine, relé, SKID, estação, 92 + 40 das 157 de comunicação no CSV de 23/11) ou com nome que não casa,
  vale para a usina, como antes. No mapa do mês a linha já é o equipamento: o furo dele com a falha registrada segue
  roxo, e o dos outros não. O verde-água foi testado e some ao lado do verde na tira de 11 px: ficou o rosa, que nenhuma
  outra cor da tira usa (no mapa ele é o "valor anômalo", por isso o mapa não o usa para isto).
- **A queda parcial** ("a queda foi parcial"; escolha dele: verde, a queda no detalhe). De 01 a 05/11 o "Desligamento de
  usina" justificava 15 inversores e os outros 10 tinham dado: o dia saía azul, como se a usina toda tivesse caído. Agora,
  com algum equipamento de geração com dado no dia (`o` ou `a`), o dia é completo (verde) e o `title` diz quem a queda
  justificou; o azul é a usina toda parada pela queda.
- **O peso** ("ele mostra por quantidade e não tá adiantando muito [...] Apollo só tem 3 usinas, as 3 estão com furo [...]
  tem que mostrar esse peso"; escolha dele, entre esta e a % das usinas com furo: a % dos dias das usinas). A barra é dias
  com furo pendente ÷ (usinas × dias verificados), de 0 a 100%: a Thopen, com 98 usinas, não esmaga quem tem 3. Na prova
  de 01 a 22/11: Apolo 38 de 66 = 58%, SEMP 2 de 44 = 5% (pela % das usinas, as duas dariam 100%, e 8 dos 12 clientes
  empatavam). No BD_Thopen o cliente é um só, e a barra sai por carteira ("Sem carteira" para as 12 sem).
- **Um BD por vez** ("tem que começar a separar BD performance e BD operações. Para isso é bem direcionado"; o "BD
  operações" é o BD_Thopen, e a escolha dele foi a tela toda). A troca "BD_Performance | BD_Thopen" no alto filtra as
  usinas do mês para a legenda, o peso, a lista, o Kanban e o CSV (`P()`); o seletor Fonte saiu do painel. O navegador
  lembra a escolha (`nexus.furos.bd`); trocar de BD limpa Cliente e Carteira, que não existem no outro.
- Prova: a bancada (`bancada_furos.py` na porta 8804 com o CSV do COS de 23/11) e
  `test_a_tela_separa_o_bd_pesa_o_cliente_e_da_o_alcance_da_comunicacao`. Nova Xavantina 1 depois: 01 a 05 e 09/11
  verdes (o `title` diz "justificado por queda: 15 equipamentos (Inversor 2.1 a 3.5)"), 06 a 08 e 10 a 22/11 rosa (Inversor
  2.4); o IPOA desses dias no mapa sai vermelho, não roxo.

**O COS na tela** (`furos_r01.ocorrencias_cos`, a chave `oc` de cada usina). Toda ocorrência do COS da usina que toca o
mês verificado, normalizada ou em aberto (a aberta vai até a hora da conta), com início, fim, falha, equipamentos, OS, se
a geração parou e se a regra a usou ("explica o dia" = está nas paradas `os` da usina, pela OS e o início). **Não mexe na
conta**: entram também a de menos de 6 h e a de "Geração parou" = não ou vazio (a falha de comunicação com a usina
gerando é exatamente o furo a coletar). Fora do escopo, como no R01: a OS 16493 e o E1. Na usina agrupada, a ocorrência
de um inversor vai só para a aba onde ele existe. Prova de 19/11 com o banco e o CSV do COS de 18/11: a conta com e sem
`oc` é idêntica (e o teste `test_o_cos_inteiro_do_mes_vai_para_a_tela_com_as_horas_sem_mexer_na_conta`); 873
ocorrências em 119 das 148 usinas; o JSON da conta foi de 460 KB para 546 KB.

**A tela 3 do Conversor** segue com "Para coletar" e "Baixa performance", lendo a mesma conta por `/coletas/furos` (as
validações de todos vão no `conf_arquivo`, na forma que ela entende: `furos_conf.para_tela3`). O Resumo e o Detalhe do .exe
e o "Mais opções" somem pelo `static/coletas/filtros.js`, e no lugar fica o caminho "Validar os furos". O "Abrir relatório"
(a rota continua) guarda o HTML e importa as marcações e as paradas congeladas dele.

**A conta** roda em fundo (`furos_fonte.Servico`): a cada 10 min, na virada do dia e a cada subida. O último resultado fica
em `furos_calculo.json` (o reinício não deixa a tela vazia). Bancada no PC: `NEXUS_FUROS_COS_CSV` aponta o CSV exportado do
COS e `NEXUS_FUROS_RELOGIO` fixa a hora.

**Só a 1ª conta faz a tela esperar** (sem resultado nenhum ainda; Levi, 16/11/2026, na 1ª abertura no servidor: "demora
para ler hein"). Três coisas a encurtam: as abas do banco são lidas de 8 em 8 ao mesmo tempo (`LEITURAS_JUNTAS`; do PC:
28,8 s uma a uma, 12,3 s de 8 em 8, resultado idêntico, e a conta em si leva 0,1 s); o COS é lido junto com o banco, não
depois; e abrir a Coletas (a casca, `coletas_tela._aquecer_furos`) já começa a conta, antes do clique na aba. Nos testes o
aquecer só liga com `NEXUS_FUROS_AQUECER`. Depois da 1ª vez a aba abre na hora com a última conta e refaz em fundo.

**Para pôr no ar (uma vez):** na aba, Validações > Importar, o `confirmacoes_furos.json` da analista e depois o
`Furos_Coleta_Performance_GridCo_R01.html` (as 122 validações e as paradas de outubro). Sem isso a tela avisa que outubro
está sem as paradas.

**Como provar.** `python -m pytest -q tests/test_coletas_furos_r01.py` (os casos do §11 da analista em miniatura, as validações e
as rotas). E a prova contra o relatório de verdade, feita em 16/11/2026 com o HTML R01 das 11:13:
1. o motor com os MESMOS insumos da analista (BDs em Excel, o CSV do COS das 08:20, outubro congelado): outubro igual nas 74.927
   células, 1.189 coberturas e 186 paradas; novembro igual nas 635 coberturas e 77 paradas, com 185 células diferentes de
   33.838, todas dado que entrou no Excel depois das 11:13 (Gravatá II, Iramaia II, Rio do Peixe, Sete Lagoas, MTS200,
   TIM200); 566 registros do COS usados, como no §6.8;
2. o banco contra o Excel: outubro 0 diferença nas 74.927 células; novembro só o que entrou depois da subida de 14/11;
3. a tela: em outubro, as 144 usinas iguais à conta do HTML da analista com as 122 validações dela, em 11 números por usina; os
   totais dela em novembro (103 com falha, 67 Geração, 89 ETM, 53 os dois) saem do mesmo calc rodado fora do navegador.
O banco tem 4 abas da Thopen que o Excel da pasta não tem (Santana, Santo Anastácio, Sapopema e Saturnino): no Nexus são
148 usinas, no HTML da analista 144.

## Os filtros dos Furos: o modelo do Histórico de OS (12/11/2026)

Levi: "arrume esses filtros para ficar no padrão exatamente dos filtros de Histórico de OS com o mesmo estilo e
funcionalidades!". `static/coletas/filtros.js` monta, por fora da tela gerada, o modelo A do Histórico (README do OS Creator,
"Os filtros do Histórico só valem no Aplicar"), com o CSS da Zeladoria (`static/zeladoria/filtros.css`, as `zf-*`, a cópia do
Histórico) e a barra em `static/coletas/coletas.css`: a busca na barra (filtra enquanto se digita), o botão Filtros com a
contagem verde (a busca não conta), o painel suspenso com Aplicar (nada filtra antes), o ponto no campo que mudou, as
etiquetas azuis com × (aplica na hora) e o Limpar tudo (os filtros, a busca e os da coluna da tabela); Esc e clique fora
descartam. Cliente, Carteira, Fonte, Status e Situação são **listas digitáveis de marcar vários** (nenhum = todos; a
Situação passa a usina que cumpre QUALQUER uma das marcadas); as três chaves que mudam a conta (zerado como furo, OS como
ausência esperada, confirmados como OK) ficam no painel como marcas, com etiqueta quando desligadas. O `furos.js` gerado
lê os vários valores pelas trocas `FUROS_VARIOS` do `portar_tela_conversor.py` (os `<select>` do .exe viram `multiple`).
Nenhum filtro novo nem padrão novo: os mesmos campos do .exe. As caixas "Falta: Inversores / IPOA / GHI" do 1.0.10
entram no painel como marcas (ligadas = sem filtro, etiqueta quando desligadas).

**16/11/2026:** o Resumo por usina e o Detalhe por equipamento (e o "Mais opções") saíram da tela 3: a validação mudou para a
aba Furos de coleta do Nexus (seção acima). Este painel segue servindo o "Para coletar" e o "Baixa performance".

**1.0.12 (13/11/2026), a tela 3 enxuta do .exe:** abre no "Para coletar"; na frente, Mês, busca, Fonte, Falta e 4 números;
o resto no "Mais filtros" (details), no "Mais opções" (menu) e no "Como ler esta tela". No Nexus a barra da frente fica e
o `filtros.js` põe nela, depois do Mês, a busca com lupa e o botão Filtros; Fonte, Falta, o "Mais filtros" e o "Limpar
filtros" do .exe ficam escondidos (`cf-oculto`), porque estão no painel e nas etiquetas. O "Filtro em cada coluna da
tabela" (`fzColF`) é marca com padrão DESLIGADO (o 3º item de `MARCAS`).

## As abas "Para coletar" (1.0.10) e "Baixa performance" (1.0.11), 13/11/2026

As duas precisam do Python além do relatório de furos; no .exe usam o BD que a janela leu, aqui:

- **Onde buscar no portal** (`/coletas/furos/portal` -> `servico.furos_portal`): a aba Equipamentos do BD_Performance. Com
  o Excel solto, o `furos.portal` do .exe; sem ele, a mesma aba no banco (`bd_performance · Equipamentos`, guardada 10 min),
  lida por `portal_de_linhas`, que repete a leitura do .exe linha a linha. Prova de 13/11: banco = Excel, 131 usinas.
- **Ronda** e **confirmações** ficam no navegador de cada pessoa (localStorage `nexus.coletas.furos.ronda` / `.conf`):
  no .exe era o `furos.json` do PC.
- **Mural** (`api/furos_mural` -> `servico.furos_mural`): a conta é o `mural.calcular` do .exe. Sem Excel solto, lê os
  **valores** do banco por `pg.BDdoBanco(so_valores=True)`: ler não precisa do mapa de fórmulas (que só protege a
  colagem), então o mural funciona mesmo antes do `bd_formulas` existir. A potência (kWh/kWp) vem da mesma aba
  Equipamentos (`potencias_de_linhas` = `mural.potencias`). A 1ª conta lê o BD inteiro do banco: **~40 s e pico de ~60 MB**
  (medido 13/11); o resultado fica guardado por (mês, ontem, subida de cada BD) e o BD é solto. Prova de 13/11 até 11/11:
  193 inversores, 177 iguais ao .exe com os BDs em Excel; os 16 restantes eram a Segredo de 11/11, mudada no Excel às 09:21
  depois da subida (01:19): diferença de dado, não de regra.
- **Paradas do COS/Fracttal** (1.0.13; `api/furos_paradas` -> `servico.furos_paradas` = `paradas.carregar` do .exe): o
  livro `falhas_performance` do db_performace por urllib, sem login, guardado 30 min no processo; sem rede vem {"erro"} e a
  tela segue sem explicação. O mural recebe as mesmas paradas (`calcular(..., paradas_dados=)`) e continua guardado pela
  subida dos BDs, como no .exe; só a conta feita com as paradas fora do ar não fica guardada. Nos testes as paradas são
  dubladas (`_paradas_sem_rede` em tests/test_coletas.py). Prova de 13/11 até 11/11: 130 usinas com parada, 21 OS abertas;
  mural 177/193 iguais ao .exe em dias E status (os 16 de novo a Segredo).
- **Recoleta pela fonte (1.0.14), LIGADA por permissão** (17/11/2026; de 13 a 17/11 ficou desligada para todos). Levi, no
  chat da Coleta: "quero formas de coletar os dados novamente pelas nossas fontes de dados e gerar uma planilha para colar
  nos BDs"; aqui: "pode!", com a permissão à parte. A pessoa escolhe usina, período e o que quer; a plataforma busca na
  fonte e devolve o dado cru; a Coletas passa pela MESMA `montagem.montar` e sai a prévia e a planilha de colar. Nada grava.
  - **Quem pode: só quem é do setor Performance** (Levi, 17/11/2026, pelo chat da Coleta: "só quem é do setor
    Performance", também nas fontes pagas; antes ele tinha dito "só admin" e corrigiu). É a tela `coletas/recoleta`
    ("Recoleta pelas fontes", `dentro_de="coletas"`, sem item no menu) com `do_setor=SID.PERFORMANCE`: quem é do setor a
    tem sem marcar nada; outro setor só se o Levi marcar em Base > Acessos; o administrador sempre pode. Ter a Coletas não
    basta: a recoleta gasta cota paga (a da API PV é dividida com a coleta da noite; em 14/11 uma recoleta de 3 dias a
    esgotou e 75 usinas ficaram sem resposta). Sem a tela, o botão "Recoletar pela API" sai escondido e os `recoleta_*`
    respondem 403 (`coletas_tela._pode_recoletar`). A plataforma não sabe quem é a pessoa (a chave é uma só): a trava é
    daqui.
  - **Os quatro métodos** (`SessaoNexus.recoleta_opcoes/_fatias/_parte/_montar`) são cópia dos da Api do .exe (app.py),
    com duas trocas: o "onde está na fonte" vem da aba Equipamentos do banco (`furos_portal`) e a chave vem do ambiente.
  - **A chave** (`servico.chave_recoleta`): a `CONVERSOR_RECOLETA_CHAVE` do .env, se a T.I. puser, ou o HMAC-SHA256 da
    `NEXUS_SSO_CHAVE` com o rótulo `nexus/coletas/recoleta/v1`. Nada no git (o repositório é público). A plataforma tem
    de aceitar esse HMAC ao lado da chave do .exe (`plataforma/recoleta_apipv.py`); enquanto não aceitar, a tela mostra a
    recusa da plataforma e nada é gasto.
  - **As travas de custo moram na plataforma** (`recoleta_apipv.py`): a reserva da coleta da noite, o teto de 150 consultas
    por dia e 8 plantas × 7 dias por pedido. A tela mostra o custo e o que resta antes de a pessoa confirmar.
  - **As sete fontes** (17/11/2026): `recoleta_fontes.py` (o cliente único das rotas `/api/recoleta/<fonte>?formato=bd`
    da plataforma, dona da regra e da credencial de cada fonte) e `static/coletas/recoleta.js` (do NEXUS, por cima do
    painel gerado do .exe: o seletor de Fonte, a chave Chuva e o custo antes de buscar). Fontes, na ordem da tela (primeiro
    o que não gasta cota): banco da Thopen (`pg`), SCADA Grid Co. (`scada`), API PV conta principal (`apipv`), SolarEdge,
    API PV conta oem@ (`oem`), SunOp e chuva. Os métodos `fontes_*` da sessão: `fontes_plantas` (a usina da tela é a ABA
    do BD, com todos os ids dela; fica de fora a que não tem aba ou cujo BD não foi lido, e a tela diz), `fontes_simular`
    (o custo, sem buscar nada), `fontes_plano` + `fontes_parte` (um pedido por vez, dentro dos tetos `max_plantas` e
    `max_dias` que cada fonte informa) e `fontes_montar` (a MESMA `montagem.montar`). Regras que vêm do contrato: nulo não
    vem e nunca vira 0; a chuva só preenche célula vazia; o dia que a fonte marca como fora do ar ENTRA com aviso severo
    e a pessoa decide (a Crateus tem 40 de 50 inversores parados de verdade); a fonte que não devolve nada vira erro com
    o motivo, não planilha vazia. A recusa da plataforma (teto, reserva da noite, fonte fora) chega à tela como veio.
    O script da tela só é servido a quem pode recoletar.
  - **A lista de usinas sem demora** (18/11/2026, Levi: "a leitura de usinas da fonte demora muito"). Medido: a demora
    era daqui, não da plataforma (que responde em 0,2 a 0,7 s): para saber quais usinas têm aba, o `fontes_plantas` lia
    do banco a aba INTEIRA de cada uma (14 s para as 75 da API PV). Agora confere só o NOME da aba (`ctx.abas`); quem lê a
    aba é a montagem, e só a da usina pedida. A exceção é a SolarEdge, cuja lista a plataforma busca na fonte na 1ª
    chamada (44 s): por isso a lista de cada fonte fica guardada 10 min no processo (`recoleta_fontes._PLANTAS`, uma
    busca por fonte de cada vez, a recusa não fica guardada) e abrir o painel (`fontes_lista`) já a busca em fundo para
    todas (`aquecer`). O saldo da cota que vem na lista é corrigido a cada pedido de verdade (`anotar_cota`); o custo
    antes de buscar vem sempre do `simular`, na hora.
  - **A lista já lida aparece na hora, sempre** (18/11/2026, Levi, na mesma tarde: "está demorando muito para aparecer
    a lista de usinas, lamentável"). Medido às 15:06, as sete rotas `/plantas` ao mesmo tempo: 0,4 a 3 s, menos a da API
    PV e a da Chuva, 37,6 s cada (a plataforma guarda a lista de plantas da API PV só 5 min e a API PV estava lenta); e
    os 10 min daqui se perdiam a cada publicação do Nexus (5 em 40 min nessa tarde). Agora a última lista boa de cada
    fonte dorme em disco (`<pasta de dados>/coletas/recoleta/plantas_<fonte>.json`; a rota diz onde, `RF.guardar_em`) e
    sai na hora mesmo passados os 10 min ou depois de um reinício: a renovação corre em fundo (uma por fonte, nova
    tentativa só depois de 30 s) e a resposta vem com `renovando: true` e SEM o saldo de cota (o número seria de outra
    hora; o `simular` traz o da hora). A tela pergunta de novo de 5 em 5 s, por até 1 min, e troca a lista quando a nova
    chega, mantendo a usina escolhida; nunca no meio de uma busca. Só espera a plataforma quem nunca leu a fonte ou a
    leu há mais de 7 dias. A renovação que falha deixa a lista que estava; a lista vazia não cobre a boa do disco. A
    usina que saiu da fonte nesse intervalo é recusada pela plataforma no pedido, com o motivo.
  - **A Fonte e a Usina são a lista digitável do Nexus** (18/11/2026, Levi, sobre a caixa nativa do navegador: "essa
    lista de usinas também tá escrota, quero ao estilo nexus!"): as `zf-*` do Histórico de OS (`static/zeladoria/
    filtros.css`), de uma escolha, com a busca, as setas e o Esc; a caixa nativa do .exe fica escondida. O ajuste de
    tamanho mora em `static/coletas/coletas.css` (`.rc-lista`).
  - **A lista não vence com o reinício do Nexus** (18/11/2026, Levi, com o painel aberto e uma publicação no meio:
    "a lista fica vencendo ainda, resolva!"). O que a recoleta guarda (a lista da fonte, o plano, as respostas) mora na
    memória da sessão, e o Nexus reinicia a cada publicação. O `fontes_simular` e o `fontes_plano` refazem a lista
    sozinhos (`_rf_ou_refaz`, com a chave que a rota passa; espera os BDs do banco ficarem prontos); só a busca perdida
    no MEIO volta com `refazer: true`, e a tela recomeça a busca sozinha, uma vez (`ir(true)` no recoleta.js). A usina
    que saiu da lista da fonte dá o motivo, não "venceu".
  - Prova: `tests/test_coletas_recoleta_fontes.py` (plataforma dublada com as respostas do contrato) e, da recoleta do
    .exe, `test_a_recoleta_busca_na_fonte_e_sai_pela_mesma_montagem` e `test_a_recoleta_so_abre_para_quem_tem_a_tela_dela`.
- **1.0.15 (19/11/2026), o ETM do supervisório com a comunicação no alto:** a Coletas mostrou o "ETM (1).csv" da São
  Bento V (export do supervisório, 10 a 19/11) como "formato novo" (Levi: "o coletor do nexus levou como formato novo"). O
  export vem ordenado pelo nome do ponto, e as linhas de `Comunicação_Solarimetrica` vêm antes da irradiação; o
  `polaris_etm` só olhava as 5 primeiras linhas. Sem irradiação no alto, ele olha a 1ª coluna do arquivo todo, como o
  leitor da Apolo (só `leitores/polaris.py`; contrato e tela iguais). Sincronizado do commit da release (coleta `364edb3`).
- Trazer uma versão do .exe que a Coleta ainda está mexendo: a pasta pode ter trabalho sem release (o `mural.py` estava lá
  antes da 1.0.11). Sincronize do commit da release (`git archive <release>` da pasta `ferramentas/conversor/conversor`
  para fora e `--origem` nela, mantendo o fim de linha da pasta) ou espere a pasta ficar limpa.

## Como provar

- `python -m pytest -q tests/test_coletas.py`. O que importa: `test_o_bd_do_banco_da_a_mesma_conversao_que_o_excel`
  monta o banco a partir de um Excel com fórmulas (valores-only, como a subida faz) e confere que a tabela, os avisos e
  o bloco colado (Ctrl+V em Python, célula a célula) são **iguais** aos do BD lido do Excel, com a fórmula do IPOA intocada.
- `test_a_copia_e_a_tela_batem_com_a_pasta_da_coleta` quebra quando o .exe mudou e a cópia não (pula no servidor).
- Na tela: soltar um relatório da Sal com o BD em Excel; o botão do BD diz "Excel · dd/mm HH:MM"; o resultado igual ao
  do .exe com o mesmo arquivo e o mesmo BD.
