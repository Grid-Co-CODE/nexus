# A plataforma de zeladoria dentro do Nexus (desenho, 03/11/2026)

## Para que serve

O Radar de Fornecedores é a plataforma de zeladoria da operação: roçagem, limpeza de módulos e poda química nas usinas,
com cotação, aprovação, contratos, documentação dos fornecedores, financeiro do orçamento de zeladoria, criticidade de
vegetação e sujidade pelas rondas, cronograma e controle de danos. Hoje é um app à parte: um HTML só, publicado no Azure
Static Web Apps, com o banco num Supabase (Postgres, login e funções na nuvem), fora do banco da T.I.

O Levi quer a plataforma **inteira dentro do Nexus**, como uma torre nova: "trazer toda a estrutura da plataforma de
zeladoria com a mesma lógica e caminhos do BD, só que ao invés de Supabase virá tudo para o Nexus, com design do Nexus".
É a visão do Nexus: todos os setores no mesmo banco, ligados por ID, para cruzar a zeladoria com a geração, as rondas, o
PCM e os chamados.

## O que o Levi decidiu (03/11/2026)

1. **Telas: clonar o Radar.** O app entra no Nexus quase linha por linha, como o OS Creator Web entrou em 30/09
   (`nexus/torres/oscreator/README.md`). Muda só a conexão (o Supabase dá lugar ao Nexus) e o visual. A lógica e os
   testes do Radar continuam valendo.
2. **Troca: cópia paralela e depois a troca.** Enquanto as telas são feitas, o Nexus copia o Supabase só lendo, por um
   comando que se roda quando se quer comparar e no dia da troca. O laço de hora em hora saiu no corte de prazo de
   03/11. Quando tudo bater, o time que usa o Radar passa ao Nexus num dia combinado, e o Supabase fica só leitura.
   Precisa do acordo do dono do Radar (o HEAD de zeladoria).
3. **Cores: as do Nexus.** A 1ª versão teve preto, azul e lima só na torre; vendo a tela, o Levi trocou (03/11/2026):
   "bote aquele azul nexus para ficar no padrão nexus de planilha e cards".
4. **O Radar congela ao fim da etapa 2:** as novidades de tela e de regra param ali, e o clone vira a casa da
   zeladoria.

## Objetivos, fora do escopo e o que seria fracasso

**Objetivos**
- As 18 abas do Radar funcionando dentro do Nexus, com os dados reais e a mesma regra de negócio.
- As 39 tabelas do Radar no banco do Nexus (`db_performace`), com os mesmos nomes, registradas no catálogo de dados.
- Login pelo Nexus. Os papéis do Radar (HEAD, Analista, Outro) e as permissões por aba continuam.
- A ronda do Fracttal e as fotos lidas pelo Nexus, dentro da cota da empresa.
- Um dia de troca sem perda: toda linha do Supabase está no Nexus, conferida por contagem.

**Fora do escopo agora** (depois da troca, em outro desenho)
- Fatos conformados para análise (custo da zeladoria × geração, desempenho de fornecedor). As tabelas entram como estão;
  os fatos `fato_*` com `data_id`, `usina_id` e `fornecedor_id` vêm depois, a partir delas.
- Juntar a Criticidade do Radar com a tela Zeladoria do Campo · App. Hoje são duas contas da mesma coisa.
- Reescrever telas nas peças do Nexus.

**O que seria fracasso, mesmo funcionando**
- Uma regra do Radar perdida no caminho: valor, parcela ou aprovação que dá número diferente do Radar.
- Uma linha perdida na troca, ou duas pessoas salvando e uma apagando o que a outra fez sem aviso.
- Dado pessoal em claro no banco, que tem leitura aberta.
- Nome de colega ou dado real no repositório, que é público.
- O Nexus mais lento ou a cota do Fracttal estourada por causa da zeladoria.

## O Radar hoje (o que o clone tem de reproduzir)

O mapa completo, tabela por tabela, está no pacote recebido em 28/10/2026 (versão `f0b4cac`, a mesma do ar). Ele foi
feito pela leitura do código e precisa ser conferido com o retrato do banco (etapa 0).

- **Um HTML só:** `public/index.html`, com 16,7 mil linhas, cerca de 1.050 funções, 59 mil caracteres de CSS e cerca
  de 120 testes Playwright que simulam o Supabase.
- **Ao entrar, carrega tudo:** um `select('*')` por tabela; o estado fica na memória do navegador.
- **Ao mudar qualquer coisa, salva o estado inteiro** (`persist()` → `syncTudo()`):
  - upsert de todas as linhas de cada tabela, por `id` (e por `chave` no `config`);
  - drena a fila de exclusões definitivas;
  - apaga e reinsere o `historico_valor` inteiro;
  - acrescenta só o `log` novo.

  Quase nenhuma tabela tem "atualizado em". A exclusão definitiva some sem rastro. A aba aberta há horas sobrescreve, ao
  salvar, o que outra pessoa mudou nas mesmas linhas.
- **O módulo novo do financeiro grava direto** (`fin_cenario`, `fin_cenario_item`, `fin_provisao`), com três funções no
  banco, cada uma numa transação e só para HEAD aprovado:
  - `fin_promover`: grava as provisões por mês e confere que a soma bate com o total;
  - `fin_definir_fornecedor`: liga o fornecedor ao item;
  - `fin_editar_provisao`: edita as provisões abertas e registra cada mudança no histórico.
- **Tabelas (39)**, no esquema `radar_fornecedores`. Cada uma tem uma view `public.rf_<tabela>`, que é a que o app usa;
  a `rf_fracttal_ultimas` não é cópia: agrega as rondas.

  | Assunto | Tabelas |
  |---|---|
  | Cadastros | `usinas`, `fornecedores`, `colaboradores`, `tipos_documento`, `documentos`, `regras_cliente_zeladoria` |
  | Cotação e aprovação | `fila_prioridade`, `periodos`, `cotacoes`, `historico_valor`, `simulacoes_aprovacao` |
  | Contratos e OS | `contratos_anuais`, `contrato_os`, `ordens_servico`, `servicos_zeladoria`, `danos_modulos` |
  | Financeiro | `financeiro_parcelas`, `financeiro_historico`, `fin_cenario`, `fin_cenario_item`, `fin_provisao`, `fin_provisao_vinculo`, `fin_fornecedor_alias`, `fin_provisao_historico` |
  | Criticidade e Fracttal | `criticidade_rondas`, `fracttal_rondas`, `fracttal_fotos`, `fracttal_sync` |
  | Cronograma | `cronograma_publico`, `cronograma_alteracoes` |
  | Equipe primarizada | seis tabelas (tipos de gasto, gastos, orçamento mensal, orçamento semanal, simulação de repasse, rota) com o primeiro nome do supervisor no nome |
  | Acesso e auditoria | `perfis`, `config`, `log` |

- **A usina** tem um id próprio (`USN-###`) e um `codigo` opcional do BD Operações. Não há id do Fracttal. Só algumas
  tabelas guardam o `usina_id`. As outras guardam texto em formatos diferentes ("Usina - Cliente", "Cliente - Usina",
  nome puro, "Cliente - Usina - UF"), e o app casa esses textos a cada tela, sem gravar o resultado. Em 08/10 entraram
  258 cópias `UFV-`, e é preciso medir quantas sobraram.
- **Fracttal** (`supabase/functions/fracttal-sync`): roda a cada 2 min pelo pg_cron.
  - Lê `GET /api/work_orders/` e os anexos das rondas.
  - Grava em `fracttal_*` e guarda as fotos no bucket `rondas-fotos`.
  - Relê a janela recente a cada 2 h e anda para trás no histórico até 2018.
  - Divide a cota de 200 pedidos/min da empresa com o Nexus.
- **API do cronograma** (`cronograma-api`): GET na internet com a chave `x-api-key`. Entrega um retrato sem fornecedor
  nem valores para um "app central da Grid". Ainda não se sabe quem consome.
- **Dado pessoal:**
  - `colaboradores`: a tabela inteira, mais os documentos de colaborador (RG, CPF, ASO, vacinação);
  - `usinas`: responsável, técnico, eletricista, mantenedor e contatos;
  - `fornecedores`: contato, telefone, PIX e e-mail; às vezes a empresa é pessoa física;
  - `cotacoes`: avaliação de colaboradores e a equipe;
  - gastos da equipe primarizada: diárias de pessoa física;
  - `fracttal_rondas.tecnico`, os responsáveis de `danos_modulos` e `perfis.email`;
  - todo `*_por` e `quem`, que guardam e-mail;
  - textos livres (`obs`, `motivo`, `resumo`), que podem ter nomes.

## Como fica no Nexus

### A torre e o clone
- **Torre `zeladoria`** (`nexus/torres/zeladoria/`), com o `CLAUDE.md` dela. Não confundir com a tela Zeladoria do
  Campo · App, que continua onde está.
- O `index.html` do Radar entra como o clone, servido pela torre. O caminho é o mesmo do pacote, para que se possa
  comparar com o original arquivo a arquivo.
- **Não entram no repositório**, que é público:
  - o `CLAUDE.md` de 271 KB do Radar, que cita pessoas: o que importa dele vai, sem nomes, para o `CLAUDE.md` da torre;
  - a pasta `docs/` (planilhas, CSV e HTML com dado real de usinas e serviços);
  - as fixtures de teste com dado de cliente, até serem conferidas;
  - o `CLAUDE.md` do pacote, a chave pública do Supabase e o id do projeto.
- **Menu:**
  - as 18 abas do Radar viram telas da torre no menu do Nexus (Visão Geral, Usinas, Fornecedores, Criticidade,
    Prioridades, Rodadas, Aprovação, Serviços em Andamento, Histórico de Cotações, Histórico de Serviços, Farol
    Contratual, Planejamento, Contratos Anuais, Documentação, Financeiro, Controle de Danos, Lixeira e Usuários);
  - cada tela abre o clone na aba dela, e a barra lateral própria do clone some;
  - quem vê a torre é decidido pelo setor (Base → Acessos); dentro dela, o papel e as permissões por aba do Radar
    decidem, como hoje.

### A ponte (o `sb` falso)
O clone continua chamando `sb.from('rf_x')...`, `sb.rpc(...)`, `sb.auth...`, `sb.functions.invoke(...)` e
`sb.storage...`. No lugar da biblioteca do Supabase, o Nexus entrega um objeto `sb` que fala com as rotas da torre. Ele
precisa atender só o que o app usa:
- `select('*')`, com `eq`, `neq` e `order`;
- `insert`, `update` e `upsert`, por `id` e por `chave`;
- `delete` com `eq` e `neq`;
- as três RPCs `fin_*`;
- o `onAuthStateChange`, que devolve a pessoa do login do Nexus (o cadastro, a senha e o "esqueci a senha" do Radar
  saem: o login é o do Nexus);
- o `functions.invoke('fracttal-sync' | 'fracttal-fotos')`;
- o `storage.createSignedUrls` das fotos.

Toda rota da ponte exige sessão do Nexus e respeita o papel: escrita, só aprovado; `fin_*` e Usuários, só HEAD.

### Do login do Nexus ao papel no Radar (decisão minha)
- **A pessoa é casada pelo e-mail:** o do login do Nexus (Fracttal ou Microsoft) com o `perfis.email`, os dois
  normalizados. O `user_id` (uuid) de quem veio do Supabase é mantido, para não quebrar as chaves `permissoes_outro_*`
  nem o `decidido_por`. Quem é novo ganha um id novo da torre.
- **Quem está no `perfis` e não tem login no Nexus perderia o acesso na troca.** A lista sai na etapa 2, para o Levi
  dar acesso antes do dia.
- **Pessoa nova passa por dois portões, como hoje mais o do Nexus:** o administrador dá o setor Zeladoria em
  Base → Acessos; a pessoa entra e aparece como "pendente" em Usuários; o HEAD aprova e escolhe o papel.
- **A senha de administrador do Nexus**, que não tem pessoa, vale como HEAD na torre. O `*_por` grava "administrador".

### Onde o dado mora
- **Livros no `db_performace`, registrados no catálogo antes de criar** (`catalogo.LIVROS`; a regra 10 de
  `nexus/dados/CLAUDE.md`). Nome de livro é para sempre. Proposta (minha):
  - `nexus_zeladoria_app`: o estado do app, uma aba por tabela, com o mesmo nome da tabela do Radar;
  - `nexus_zeladoria_fracttal`: rondas, fotos (o índice, não o arquivo) e o cursor; grava o laço do Fracttal;
  - `nexus_zeladoria_historico`: `log`, `financeiro_historico`, `fin_provisao_historico` e `cronograma_alteracoes`;
    declarado `so_cresce`.

  O livro `nexus_zeladoria`, que já existe (a visão da tela Zeladoria do Campo para o dashboard do cliente), não é
  tocado.
- **Mesmos nomes de tabela e de coluna**, com três exceções:
  - as seis tabelas da equipe primarizada trocam o nome do supervisor por `equipe`: `tipos_gasto_equipe`,
    `gastos_equipe`, `orcamento_equipe`, `orcamento_equipe_semanal`, `simulacao_repasse_equipe` e `rota_equipe`. A
    ponte traduz o nome antigo, e o clone é renomeado na etapa 3;
  - a aba ganha as colunas de controle `_versao` e `_alterado_em`, que a ponte usa e o app não vê;
  - as colunas de dado pessoal vão cifradas (abaixo).

  As abas não seguem o `fato_`/`dim_`: elas entram em `catalogo.ABAS_FORA_DA_REGRA`, com o motivo ("cópia fiel das
  tabelas do Radar; os fatos vêm depois, a partir delas"), e no `explica.py`.
- **Dado pessoal cifrado no banco**, com a chave do cadastro (o mesmo `sensivel_cifrado` do cofre). O servidor do Nexus
  decifra na hora de entregar ao clone, só a quem tem sessão e papel. A lista de colunas é a da seção anterior, conferida
  com o retrato. Texto livre vai cifrado inteiro. `*_por` e `quem` passam a guardar o login do Nexus, cifrado.
- **O nome do fornecedor vai cifrado, sempre.** Fornecedor MEI tem nome de pessoa, e não há como separar com
  segurança o MEI da empresa. Isso vale para `fornecedores.empresa`, o nome nas parcelas, nas `fin_*` e no
  `fin_fornecedor_alias`. O casamento por nome continua no navegador, depois de decifrado. No servidor, as `fin_*`
  trabalham pelo id. A análise futura liga pelo id do fornecedor, nunca pelo nome.
- **Valores de contrato e de pagamento vão em claro, ao lado do id do fornecedor.** Não são dado pessoal sem o nome, e
  são a razão de o dado estar no Nexus (decisão minha; o banco tem leitura aberta).
- **JSON maior que a célula:** o xlsx guarda no máximo 32.767 caracteres por célula. O `config` e o `cronograma_publico`
  têm JSON grande, então o valor que passar disso vai partido em linhas numeradas, e a ponte remonta. Medir o maior na
  etapa 0.
- **A usina liga ao cadastro.** A aba `usinas` fica, porque o app depende dos campos dela, mas ganha o `usina_id` do
  `cadastro_nexus`, pelo de-para (Base → Ligações), sem chute (regra 4). Usina `USN-` sem ligação aparece na qualidade.
  Os textos de usina das outras tabelas não são reescritos agora: o clone continua casando como hoje.

### Gravar sem apagar o que o outro fez
- A ponte guarda o retrato do que carregou. Quando o `syncTudo` manda o estado inteiro, ela envia ao servidor só as
  linhas que mudaram desde aquele retrato, com a `_versao` de cada uma, e as exclusões.
- O servidor, numa trava por livro (como `decisao_pt.py` e `observacao_responsavel.py`):
  - confere a versão de cada linha;
  - aplica as mudanças;
  - grava o livro inteiro;
  - relê e confere a contagem (`livros.publicar`).
- **A regra do conflito (simples, corte de prazo de 03/11):**
  - O livro tem uma versão. Se outra pessoa salvou depois do retrato, o servidor recusa a gravação inteira, nada entra.
    O clone avisa ("outra pessoa salvou antes de você"), relê o banco, reaplica por cima as linhas que a pessoa editou e
    salva de novo.
  - Assim, a mudança do outro numa linha que a pessoa não mexeu fica. Na linha que os dois mexeram, vale a última, como
    no Radar de hoje, e o aviso diz quais foram. Com o HEAD e poucos analistas usando, isso basta. A comparação linha a
    linha, lado a lado, fica para quando houver necessidade.
  - O id novo gerado no navegador ("maior + 1") que já existir no servidor não sobrescreve: o servidor devolve o
    próximo id livre, e o clone troca o id antes de reenviar.
  - O `cronograma_publico`, que qualquer navegador regrava, é derivado: fica com o último que gravou.
- O "Salvo" do clone só acende depois que o banco confirmou.
- **Tempo do "Salvo":** a meta é até 3 s. A ponte sabe quais tabelas mudaram e grava só o livro delas. Na etapa 1 o
  tempo é medido com o tamanho real. Se passar da meta, o `nexus_zeladoria_app` se divide por assunto (cadastros,
  cotação, contratos, financeiro), e cada salvamento troca só o livro do assunto mexido. O Radar tem pouca gente ao
  mesmo tempo: o HEAD e alguns analistas.
- **Exclusão definitiva deixa rastro:** a linha sai da aba, e o que saiu, quem tirou e quando vão para o `log`.
- **As RPCs `fin_*` viram funções Python** com a mesma conferência, aplicadas numa gravação só: ou tudo entra, ou nada.
- **Uma máquina grava:** só o servidor (`app.gridco.com.br`) tem a gravação ligada (`NEXUS_ZELADORIA_GRAVA=1`). No PC,
  a torre abre só para leitura, com aviso. Dois Nexus no ar com memórias diferentes apagariam um ao outro.

### Fracttal, fotos e a API do cronograma
- **Até a troca, o Nexus não lê rondas no Fracttal para a zeladoria:** copia as `fracttal_*` do Supabase, junto com o
  resto. O botão Sincronizar fica escondido, porque quem sincroniza ainda é o Radar.
- **As fotos de uma ronda já funcionam na torre só leitura (etapa 2):** o Nexus pede ao Fracttal só os anexos daquela
  ronda, na hora do clique, com cache (são poucos pedidos, dentro da cota). Assim não é preciso nenhuma chave do bucket
  do Supabase.
- **Depois da troca:**
  - um laço do Nexus lê as rondas no horário livre da tabela de laços (`nexus/casca/CLAUDE.md`), dentro da cota, e de
    preferência aproveitando a leitura de OS que o Nexus já faz, em vez de pedir de novo;
  - o pg_cron do Supabase é desligado no mesmo dia;
  - as fotos passam a ser pedidas ao Fracttal na hora, com cache, como faz o `fracttal-fotos`;
  - o histórico do bucket fica no Supabase só leitura até se decidir o que fazer com ele.
- **API do cronograma:** uma rota do Nexus com o mesmo contrato (GET, `x-api-key` pelas Chaves do Nexus, o mesmo JSON),
  incluída de propósito em `ROTAS_PUBLICAS`. Antes da troca, é preciso descobrir quem a consome e combinar a mudança de
  endereço.

### Visual
- Os tokens do `nexus.css` entram no clone, e as variáveis do Radar apontam para eles, nos dois temas.
- A casca (topo e menu) continua a do Nexus.
- O CSS do clone (cerca de 40 variáveis e 116 cores fixas) passa a usar os tokens. Nenhum `#hex` nem `rgba()` fica em
  regra de CSS (regra da casa). **Por script (corte de prazo de 03/11):**
  - as ~40 variáveis do Radar são redefinidas com os tokens da torre, e isso já resolve a maior parte;
  - as cores fixas que sobrarem trocam pelo token mais próximo, por uma tabela de-para revisada uma vez.
- Os 361 emojis da interface (63 diferentes) saem, também por script com uma tabela de-para: viram palavra ou ícone de
  traço, como no resto do Nexus.
- O layout tem de funcionar em 375 px.

## As regras do Nexus que o clone tem de cumprir

- **Nenhum nome de colega no repositório.** O código do Radar cita pessoas: cerca de 700 vezes no app e 230 nos testes,
  em identificadores, rótulos e comentários (exemplo: o card da fila que leva o nome do aprovador). Tudo vira papel:
  HEAD, analista, supervisor da equipe primarizada. O `tests/test_sem_nomes_no_repositorio.py` tem de passar com o
  `.env`.
- **Endereço nunca a partir da raiz:** `nexusRota()` no JavaScript (`tests/test_prefixo.py`).
- **Sem emoji. Cor só por token. Tudo em pt-BR.**
- **Toda rota exige login**, exceto a da API do cronograma, que entra em `ROTAS_PUBLICAS` com a chave.
- **Tela que lê o Fracttal ao abrir entra na `FORA` da pré-carga.**
- **`CLAUDE.md` da torre e uma linha na tabela de áreas do `CLAUDE.md` da raiz.**

## Etapas, com horas medidas no código

Cada etapa tem uma entrega própria e só sobe com o OK do Levi.

| # | Etapa | O que entrega | Horas |
|---|---|---|---|
| 0 | Retrato e acesso | O Levi roda o `retrato_do_banco.sql` (contagens, colunas reais, regras, funções) e cria no Supabase um papel só de leitura (SELECT no `radar_fornecedores`). A conexão desse papel vai para as Chaves do Nexus, não para o chat. Combinar com o dono do Radar. | 0,5 (+15 min do Levi) |
| 1 | Cópia sob comando | Um comando (`ferramentas/`) que lê o Supabase só leitura, pelo pooler do Supabase (IPv4), e grava as 39 tabelas nos três livros, com as colunas pessoais cifradas. Roda-se para comparar e no dia da troca; não há laço de hora em hora. Precisa de um driver Postgres, que o Nexus ainda não usa (o `pg8000` é Python puro e grátis). Roda no servidor se ele alcançar o pooler (a 1ª coisa a medir); se não, no PC, a única máquina a gravar esses livros até a troca (regra 11). Catálogo, `explica.py`, trava `so_cresce` no histórico, conferência de contagem Supabase × Nexus. Testes com `tests/pg_falso.py`. | 3 a 4 |
| 2 | Torre só leitura | Torre, clone e ponte de leitura. Login do Nexus no lugar do Supabase Auth. Papel pelo `perfis` ligado ao login do Nexus. As 18 telas no menu, as fotos da ronda pedidas ao Fracttal no clique e o aviso "cópia do Radar: edite no Radar até a troca". É o primeiro momento em que o Levi vê o Radar no Nexus com dado real. | 3 a 4 |
| 3 | Visual e nomes, por script | As ~40 variáveis do CSS redefinidas com os tokens e as três cores, as cores fixas e os 63 emojis por tabelas de-para, nos dois temas e em 375 px. Os nomes de pessoas (identificadores, rótulos, comentários) e as seis tabelas renomeados em lote. Os ~120 testes do Radar rodando contra a ponte, que tem a mesma cara do Supabase. | 4 a 5 |
| 4 | Gravação | Versão do livro com aviso e reaplicação, exclusão com rastro, as três `fin_*` em Python. Gravação ligada só no servidor e testada na cópia de prova. | 3 a 4 |
| 5 | Fracttal e cronograma | Leitura das rondas dentro da cota (portando o `fracttal-sync`), botão Sincronizar, rota do cronograma com chave. | 3 |
| 6 | Usinas e troca | De-para das usinas `USN-` com o cadastro (o Levi na Base → Ligações). Ensaio da troca na cópia de prova. No dia: última cópia, conferência, gravação ligada, Supabase só leitura, cron desligado e o consumidor da API avisado. | 1 a 2 |
|   | **Total** | | **cerca de 20 (18 a 22)** |

**O Radar congela ao fim da etapa 2** (Levi, 03/11/2026). O congelamento vale para as telas e a lógica; os dados
continuam sendo editados no Radar até a troca. A partir da etapa 2 o clone é a casa da zeladoria, como o OS Creator
desde 31/10. As etapas 3 e 4 mexem direto no clone, sem script reaplicável. O que o time do Radar mudar entre o
`f0b4cac` e o congelamento é trazido uma vez, comparando os commits do repositório da zeladoria, antes de a etapa 3
começar. Combinar com o dono do Radar a data do congelamento faz parte da etapa 0.

## Dúvidas que o banco ou o dono do Radar respondem (antes da etapa 1)

1. As contagens reais de cada tabela, o tamanho dos JSON do `config` e quantas parcelas foram duplicadas quando o PCM
   renumerou.
2. Os tipos, as chaves e as restrições reais fora das `fin_*`, e se as migrações do financeiro de 27/10 estão aplicadas
   (os SQL dizem "NÃO APLICADO"; o `CLAUDE.md` do Radar diz aplicado).
3. O SQL da `rf_fracttal_ultimas`: ela exclui a OS cancelada? O que conta em `total_rondas`?
4. O que existe hoje em `usinas` depois das 258 cópias `UFV-`, e se o `codigo` bate com o `cadastro_nexus`.
5. Se `quem` e `*_por` são sempre e-mail.
6. Quem consome a API do cronograma.
7. Se o dono do Radar concorda com a troca e com o congelamento ao fim da etapa 2, e quem passa a programar a zeladoria
   depois. Se for alguém de fora dos administradores, a torre entra na conferência `pasta-da-area`, como COS, Engenharia
   e Segurança.

## Decisões minhas (para o Levi conferir)

- Os nomes dos três livros e a divisão entre eles.
- Valores em claro, com o id do fornecedor; o nome do fornecedor (por causa do MEI), o dado pessoal e o texto livre
  cifrados.
- As seis tabelas renomeadas para `*_equipe`.
- A gravação ligada só no servidor; no PC, a torre só lê.
- O conflito simples, pela versão do livro: quem salvou depois recebe o aviso, o clone relê e reaplica o que a pessoa
  editou. Na mesma linha, vale a última, como no Radar, mas com aviso.
- A meta de até 3 s para o "Salvo", medida nas etapas 1 e 4; se estourar, um livro por assunto.
- O casamento do login pelo e-mail, com o uuid do Supabase mantido; a senha de administrador vale HEAD.
- Até a troca, nada de leitura de rondas no Fracttal para a zeladoria (só as fotos, no clique); depois, fotos pedidas
  na hora em vez de guardadas.
- A cópia por comando, no servidor se ele alcançar o Supabase; se não, no PC.
- Os emojis saem, por regra do Nexus, mesmo sendo "a mesma lógica".

## Como provar

- **Cada etapa:** `python -m pytest -q` (com o `.env`, para o teste de nomes rodar), mais a tela na cópia de prova
  (`ferramentas/subir_copia_de_prova.py`) em desktop e em 375 px.
- **Cópia:** a contagem de cada tabela no Supabase é igual à da aba no Nexus, na tela da Governança. Uma amostra de
  linhas, decifrada, é igual à do Supabase.
- **Lógica:** os ~120 testes do Radar passam contra a ponte. Visão Geral, Financeiro (Mês a mês) e Farol Contratual dão
  os mesmos números no Radar e no Nexus, no mesmo dia, com a mesma cópia.
- **Conflito:** duas abas salvando ao mesmo tempo. A segunda recebe o aviso, e as linhas que só a primeira mexeu continuam lá.
- **Troca:** ensaio completo na cópia de prova antes do dia.
