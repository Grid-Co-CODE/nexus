# Engenharia: o acompanhamento dos ativos com sinal na Confiabilidade — desenho

18/10/2026. Pedido e decisões do Levi nesta data (rascunhos 1 e 2 mostrados no navegador; o 2 aprovado: "Pode
seguir", e guardado em `docs/mockups/engenharia-acompanhamento.html`, com dados de mentira). O que é escolha do Claude
está marcado **[escolha do Claude]**.

## Por que

A Confiabilidade (`/t/engenharia/confiabilidade`) mostra os ativos que acenderam (crítico, atenção, monitorar) pelas OS
de falha do Fracttal, mas o sinal não tem dono nem história: ninguém sabe quem está olhando aquele inversor, o que já se
descobriu nem quando a análise acabou. O Levi quer "um canto focado na engenharia" que comece um **ecossistema**: a
Engenharia primeiro, e o mesmo jeito de trabalhar depois nos outros setores ("vamos começar pelo setor de engenharia
para aplicar nos demais setores").

O pedido, nas palavras dele:
1. "Temos confiabilidade."
2. "A ideia seria os membros de engenharia ou administradores pegar aqueles ativos com sinal para acompanhar ou alguém
   da engenharia poder encaminhar para a pessoa ver!"
3. "Após a pessoa pegar para acompanhar ela pode dar comentários e dizer motivos." Com data de início da análise, data
   de fim da análise, comentários e diagnóstico ("comunicação, disjuntor", a lista que ele começou).
4. "Em confiabilidade precisa ter um campo para saber o que está sendo acompanhado, o que está sendo acompanhado sai de
   ativos com sinal e passam para em acompanhamento."

Liga com a visão do Nexus (CLAUDE.md da raiz): o diagnóstico de cada ativo, com data e ligado por ID (ativo, usina,
pessoa, dia), é o começo de uma base para "fazer previsões e diagnósticos de forma que faça sentido".

## Objetivos

1. **Pegar e Encaminhar** um ativo com sinal, no cartão da lista e na gaveta do ativo.
2. **Aba Em acompanhamento**: o ativo pego sai de Ativos com sinal e vem para cá, com quem está com ele.
3. **O acompanhamento na gaveta do ativo**: início e fim da análise, diagnóstico, comentários com data e hora, o aviso
   de falha nova e os acompanhamentos anteriores do ativo.
4. **Encerrar** preenchendo o fim da análise com o diagnóstico; **aba Encerrados** com os encerrados.
5. **Cadastro de diagnósticos** editável pela Engenharia.
6. **Tudo no banco**, num livro novo registrado no catálogo antes da 1ª gravação (governança é a prioridade 0).

## Não objetivos

- A **Mesa do engenheiro** (a página de entrada da Engenharia): o Levi escolheu "depois", e com os acompanhamentos de
  cada pessoa em destaque quando vier.
- Levar o acompanhamento aos outros setores agora, ou fazer um componente genérico para isso. Fica o jeito descrito aqui
  para ser repetido.
- Avisar por e-mail ou Teams quem recebeu um encaminhamento: o Nexus não tem SMTP. Quem recebe vê na tela
  **[escolha do Claude]**.
- Escrever no Fracttal (abrir OS, mudar responsável): o acompanhamento mora no Nexus.
- Mudar as contas da Confiabilidade (sinal, nível, P90, MTBF, MTTR, disponibilidade) ou a aba Indicadores.
- Reabrir um acompanhamento encerrado **[escolha do Claude]**: o ativo volta a ser acompanhado quando falhar de novo.

## Antiobjetivos (seria um fracasso mesmo funcionando)

- Comentário, nome ou e-mail em claro no banco (a API tem leitura aberta).
- O ativo sumir de Ativos com sinal sem estar em Em acompanhamento nem em Encerrados.
- O ativo encerrado voltar à lista todo dia por causa das falhas antigas que já foram analisadas.
- O número da aba diferente da lista que ela mostra, ou a tela dizendo "nenhum" quando o banco não respondeu.
- Planilha, JSON em disco ou OneDrive como lugar do dado.

## As decisões do Levi (18/10/2026)

| Assunto | Decisão |
|---|---|
| Onde fica o acompanhamento | Na **gaveta do ativo** que a Confiabilidade já abre no clique (não um card novo por cima) |
| Fim da análise | **O dia em que a análise terminou.** Preencher o fim, junto com o diagnóstico, encerra; não há outro botão |
| Depois de encerrado | O encerrado vai para o histórico (aba Encerrados e gaveta). O ativo **só volta** a Ativos com sinal **com falha nova** depois do fim, com a marca "já acompanhado: diagnóstico X em DD/MM" |
| Encaminhar | **Só para pessoas da Engenharia.** Quem recebe passa a acompanhar e vê em Em acompanhamento |
| Lista de diagnósticos | **Cadastro editável**: a Engenharia cria, renomeia e exclui, numa aba de cadastro, como os motivos do PCM. Começa com Comunicação e Disjuntor |
| Quem escreve | Não ficou "só quem acompanha escreve": qualquer pessoa da Engenharia ou administrador comenta, muda as datas e o diagnóstico |
| Aviso de falha nova | Fica: o cartão e a gaveta mostram as falhas que o ativo teve desde que entrou em acompanhamento |
| Comentários | Ficam com data, hora e quem escreveu, o mais novo em cima; nenhum é apagado |
| Soltar o ativo | Não tem: quem pegou por engano encaminha para outra pessoa ou encerra. Consequência aceita: encerrar um pego por engano grava um diagnóstico sem análise e tira o ativo de Ativos com sinal até falhar de novo. Para separar esses na análise, a Engenharia pode cadastrar um diagnóstico como "Sem análise" (o cadastro é dela) |
| Histórico | Na gaveta do ativo **e** numa aba Encerrados |
| Filtros da aba Em acompanhamento | Os de hoje (cliente, usina, família, criticidade, nível, busca) **e** "Quem acompanha" |
| Filtros da aba Encerrados | Os de hoje **e** "Quem acompanhava" (sem filtro de diagnóstico) |
| Mesa do engenheiro | Depois |

## Como funciona

### O caminho de um ativo

```
Ativos com sinal ──Pegar / Encaminhar──> Em acompanhamento ──fim + diagnóstico──> Encerrados
       ^                                      (Encaminhar troca quem acompanha)          |
       └──────────── só com falha nova depois do fim, com a marca "já acompanhado" ──────┘
```

### As abas

`Ativos com sinal (n)` · `Em acompanhamento (n)` · `Encerrados (n)` · `Indicadores` · `Diagnósticos`. A aba usa o
parâmetro `aba` que já existe; os números das abas contam com os filtros de agora, como a de hoje.

- **Ativos com sinal**: a lista de hoje **menos** os ativos com acompanhamento aberto **menos** os que têm um
  acompanhamento encerrado e nenhuma falha nova depois do fim do último. O que voltou com falha nova leva a etiqueta
  "já acompanhado · <diagnóstico> em <DD/MM do fim>". O cartão ganha os botões **Pegar para acompanhar** e
  **Encaminhar** (para quem pode; ver Permissões).
- **Em acompanhamento**: um cartão por acompanhamento aberto (rascunho 2, parte 1): o nível de agora (ou "sem sinal
  agora" **[escolha do Claude]**: o acompanhamento não depende do sinal, fica até ser encerrado), nome, código, usina,
  "Com <pessoa> desde DD/MM" (e "encaminhado por <pessoa>" quando foi), "análise desde DD/MM", o diagnóstico (ou "a
  definir"), quantos comentários, "<n> falha(s) nova(s) desde que entrou" quando houver, o último comentário (trecho,
  quem e quando) e, à direita, as falhas em 30 dias **quando entrou**. Filtros: os de hoje e **Quem acompanha** (só
  nesta aba). O nível do filtro é o de agora **[escolha do Claude]**.
- **Encerrados**: um cartão por acompanhamento encerrado, o mais recente em cima (rascunho 2, parte 4): selo
  "Encerrado", nome, código, usina, quem acompanhava, "análise DD/MM → DD/MM/AAAA", o diagnóstico, quantos comentários e
  "sem falha nova desde o fim" ou "voltou com falha nova em DD/MM". O mesmo ativo pode aparecer mais de uma vez (um
  cartão por acompanhamento). Filtros: os de hoje e **Quem acompanhava** (quem estava com o ativo ao encerrar; o mesmo
  parâmetro do "Quem acompanha", que só aparece nestas duas abas). Aqui o nível do filtro é o **da entrada**
  (`nivel_na_entrada`): encerrado quase nunca tem sinal agora **[escolha do Claude]**.
- **Diagnósticos**: o cadastro (nome e descrição opcional; renomear e excluir na própria linha, como o Cadastro de
  motivos do PCM). Excluir marca `excluido = sim` e o ID não volta: os acompanhamentos antigos continuam apontando para
  ele e o nome aparece neles; o excluído não aparece mais na escolha. Só aparece para quem pode editar.

O painel ao lado (Onde está o problema, Criticidade, Clientes com sinal) e a faixa de indicadores continuam sobre todos
os ativos com sinal, acompanhados ou não: descrevem a frota **[escolha do Claude]**.

### A gaveta do ativo

O clique no cartão, em qualquer das três abas, abre a gaveta que existe hoje (MTBF, MTTR, disponibilidade, "Por que
acendeu", as últimas OS) com dois blocos novos (rascunho 2, partes 2 e 3):

- **Acompanhamento**, logo depois dos números do ativo:
  - sem acompanhamento aberto: "Ninguém acompanha este ativo." e os botões Pegar para acompanhar e Encaminhar;
  - aberto: com quem está e desde quando (e quem encaminhou), o botão Encaminhar, o aviso de falha nova (as OS: número,
    tipo e dia), os campos **Início da análise**, **Fim da análise** e **Diagnóstico**, com o botão **Salvar** e a
    frase "Preencher o fim (com o diagnóstico) encerra o acompanhamento: o ativo vai para Encerrados"; os
    **Comentários** (caixa de texto, **Salvar comentário** e a lista, o mais novo em cima, com data, hora e quem);
  - encerrado: o mesmo, só para ler.
- **Acompanhamentos anteriores**: os encerrados daquele ativo (datas, diagnóstico, quem, quantos comentários; abre os
  comentários de cada um **[escolha do Claude]**).

Ativo sem sinal hoje (em acompanhamento ou encerrado) abre a gaveta com os números dele e "sem sinal nos últimos 30
dias" no lugar de "Por que acendeu".

Salvar, comentar e encaminhar gravam **sem sair da gaveta** (como o card das Contestações); a lista atrás acompanha.
Pegar e Encaminhar um ativo de Ativos com sinal tiram o cartão de lá na hora.

### Permissões

- **Ver** a Confiabilidade e as abas: quem a tela deixa hoje (o setor da pessoa, Base → Acessos). Quem vê e não pode
  agir lê tudo, sem botões. O setor Engenharia já vê a Confiabilidade: medido em 18/10/2026 no banco
  (`nexus_setor_telas`, a última decisão do setor 1 libera `engenharia/confiabilidade`, `equipe`, `criticidade`, `fmea`
  e `laudos`); nada muda no acesso.
- **Agir** (pegar, encaminhar, salvar, comentar, encerrar, editar o cadastro de diagnósticos): quem é do **setor
  Engenharia** ou **administrador**, com **login de pessoa** (Microsoft ou Fracttal). A senha de administrador não diz
  quem é a pessoa: com ela, a tela mostra e recusa a ação, como nas Contestações.
- **Receber** um encaminhamento: só pessoas do setor Engenharia (a lista do botão Encaminhar). O setor é o de
  `nexus/cadastro/setores.py` (livro `nexus_setores`): medido em 18/10/2026 no banco, o setor "Engenharia" existe e tem 6
  pessoas, todas com o código do e-mail (`pessoa_hmac`). O nome na lista vem do pessoal do Fracttal
  (`nexus/cadastro/fracttal_pessoal.py`, guardado 1 h), pelo `fracttal_id` da decisão do setor.

### As regras

1. **Pegar** só ativo que está em Ativos com sinal. Pegar começa um acompanhamento com a pessoa do login e o início da
   análise em hoje (dia de Brasília). Dois pegando ao mesmo tempo: o segundo recebe "já está com <pessoa>".
2. **Encaminhar** escolhe uma pessoa do setor Engenharia diferente de quem acompanha agora. Num ativo de Ativos com
   sinal, começa o acompanhamento com quem recebeu; num acompanhamento aberto, troca quem acompanha. Encaminhar para si
   mesmo é o jeito de assumir.
3. **Início da análise**: começa em hoje e pode ser mudado; não pode ser depois de hoje nem depois do fim.
4. **Encerrar** é salvar com o fim preenchido: exige o diagnóstico; o fim não pode ser antes do início nem depois de
   hoje. Encerrado fica só para ler: não muda data, diagnóstico nem recebe comentário **[escolha do Claude]**.
5. **Comentário**: de 1 a 2.000 caracteres (o teto das Contestações), com a data e a hora da gravação e quem escreveu;
   nunca editado nem apagado.
6. **Falha nova** é uma OS de corretiva ou corretiva emergencial que não é serviço registrado como corretiva: a mesma
   conta do sinal (`confiabilidade.TIPOS_SINAL` e `RX_SERVICO`), para o aviso e o retorno baterem com a lista
   **[escolha do Claude]**. Conta pela data de criação da OS:
   - "desde que entrou": criada depois da gravação do evento que começou o acompanhamento (o início da análise pode ser
     anterior, e as falhas até ali já eram conhecidas de quem pegou);
   - "depois do fim": criada a partir do dia seguinte ao fim da análise, no dia de Brasília (o dia do fim conta como
     analisado). É a regra do Levi ao pé da letra ("só volta se falhar depois do fim"), também quando o fim é anterior
     ao dia em que se encerra: a falha que chegou entre o fim e o encerramento é depois da análise, e o ativo volta a
     Ativos com sinal ao encerrar. Para isso não pegar ninguém de surpresa, a gaveta avisa antes de gravar: "Há <n>
     falha(s) depois desta data de fim: o ativo volta para Ativos com sinal ao encerrar" **[escolha do Claude]**. O
     "voltou com falha nova em DD/MM" dos Encerrados é o dia da 1ª falha depois do fim.
7. Ativo com acompanhamento aberto **não** aparece em Ativos com sinal, mesmo que o sinal cresça: o aviso de falha nova
   mostra o crescimento.

### O dado (governança, prioridade 0)

Livro novo **`nexus_engenharia_acompanhamento`**, registrado em `catalogo.LIVROS` e o fato em `catalogo.FATOS` antes da
1ª gravação (regra 10), com o "para que serve" em `explica.py` (`RESUMO` e `PARA_QUE`; o teste cobra). O Nexus é a
FONTE. Duas abas, gravadas sempre juntas (gravar sem uma a apagaria):

- **`fato_acompanhamento_ativo`** — **1 linha = 1 evento sobre 1 acompanhamento de 1 ativo**. Tipo transação: só
  acrescenta; nada se edita nem se apaga. Eventos: `pegou`, `encaminhou`, `dados` (mudou o início ou o diagnóstico),
  `comentario`, `encerrou` (o fim e o diagnóstico). O estado de agora se lê dos eventos, na ordem da gravação (o mesmo
  cuidado das Contestações: dois eventos no mesmo segundo ficam na ordem em que foram gravados): quem acompanha é o do
  último `pegou`/`encaminhou`; início e diagnóstico, o último valor; encerrado, quem tem `encerrou`.
  - Em claro: `id`, `registrado_em` (UTC), `data_id` (o dia de Brasília do evento), `acompanhamento_id`, `evento`,
    `codigo_ativo`, `equipamento_id` (`nexus/dados/equipamento.py`, o mesmo número da dimensão), `usina_id` e
    `usina_ligada_por` (a ligação que a Confiabilidade já faz com o cadastro; não liga = vazio, nunca chutar),
    `pessoa_hmac` (quem fez), `responsavel_hmac` (quem acompanha depois do evento), `diagnostico_id`,
    `data_id_inicio_analise`, `data_id_fim_analise` e, no evento que começa, a foto do sinal na entrada
    (`nivel_na_entrada`, `falhas_30d_qtd`, `falhas_7d_qtd`).
  - Só **cifrado** (o Cofre, a chave do cadastro, como as Contestações), num campo `dados_cifrados`: o nome e o e-mail de
    quem fez, o nome de quem passou a acompanhar e o texto do comentário.
- **`dim_diagnostico`** — 1 linha = 1 diagnóstico do cadastro (`diagnostico_id` 1, 2, 3..., nome, descrição, criado,
  alterado, `excluido`, `alterado_por_hmac`). Antes da 1ª gravação vale o cadastro inicial (Comunicação, Disjuntor), que
  entra no banco junto com a 1ª gravação, como os motivos do PCM.

Gravar troca o livro inteiro, relido do banco antes (leitura que falha não grava), uma gravação por vez no processo
(trava), e `livros.publicar` confere a contagem depois. Duas máquinas gravando no mesmo segundo ainda podem perder um
evento: o mesmo risco aceito nos setores e nas Contestações. A tela lê o livro com uma cópia curta, refeita na hora por
quem acabou de gravar (quem pegou tem de se ver com o ativo).

No catálogo: área `engenharia`; dimensões data (id: `data_id`; papéis `data_id_inicio_analise`,
`data_id_fim_analise`), usina (id), equipamento (id) e pessoa (código: `pessoa_hmac`, `responsavel_hmac`).

## Onde mexe

| Peça | Arquivo |
|---|---|
| Regras e o livro | `nexus/engenharia/acompanhamento.py` (novo; o modelo é `nexus/contratos/tratamento.py` e o cadastro de `nexus/pcm/motivos.py`) |
| As contas que faltam | `nexus/engenharia/confiabilidade.py`: as datas de criação das falhas de cada ativo além dos 30 dias, para o aviso e o retorno |
| Tela e ações | `nexus/torres/engenharia/__init__.py`, `templates/engenharia/confiabilidade.html`, `nexus/static/engenharia.css` |
| Catálogo | `nexus/dados/catalogo.py` (`FATOS`, `LIVROS`), `nexus/dados/explica.py` |
| Documentação | `nexus/torres/engenharia/CLAUDE.md`, `nexus/dados/CLAUDE.md` (o que existe), a linha da Engenharia na tabela do `CLAUDE.md` da raiz e na de `nexus/torres/CLAUDE.md` |
| Testes | `tests/test_engenharia_acompanhamento.py` (novo), `tests/test_dados_camada.py` (catálogo) |

## Restrições

- Repositório público: nenhum nome de colega no código, nos testes nem nos `.md` (fixture com nome fictício;
  `tests/test_sem_nomes_no_repositorio.py`, que só roda com o `.env` na worktree).
- Cor só por token do `nexus.css`, nos temas escuro e claro (`tests/test_tema.py`); o desenho é o da Confiabilidade
  (`eg-*`). Texto da tela em pt-BR, sem emoji.
- Endereço nunca a partir da raiz: `na_raiz`, `|na_raiz`, `nexusRota` (`tests/test_prefixo.py`).
- Ação por POST com a conferência de origem que as telas já usam (`_de_outro_site`); nome ou e-mail nunca em URL.
- Funciona a 375 px: a gaveta já ocupa a tela inteira no celular; os campos ficam um embaixo do outro.
- O 5070 não é reiniciado; push na `main` só com o OK do Levi.

## Escolhas do Claude (para conferir)

1. Encerrado não reabre e fica só para ler.
2. Sem aviso fora da tela (e-mail, Teams).
3. "Falha nova" pela mesma conta do sinal (corretiva e corretiva emergencial, serviço fora), contada da gravação do
   início do acompanhamento e do dia seguinte ao fim.
4. Acompanhamento aberto fica na aba mesmo sem sinal ("sem sinal agora"); o filtro de nível usa o nível de agora em
   Em acompanhamento e o da entrada em Encerrados.
5. O painel ao lado e a faixa de números continuam sobre todos os ativos com sinal.
6. Na gaveta, os acompanhamentos anteriores abrem os comentários deles.
7. A aba do cadastro chama-se "Diagnósticos" e só aparece para quem pode editar.
8. Encerrar com falha depois da data de fim avisa, antes de gravar, que o ativo volta para Ativos com sinal.
9. A prova não grava no banco de verdade (o livro é para sempre e a API não apaga): os testes usam o banco falso
   (`tests/pg_falso.py`), a tela é conferida numa cópia renderizada pelo cliente de teste e servida estática (desktop e
   375 px) e numa cópia de prova noutra porta, só lendo. O livro nasce no 1º "Pegar" de verdade, depois do deploy.

## Fica para o construtor

Os nomes das rotas e se a resposta é JSON ou o pedaço da gaveta já montado; a cópia curta da leitura; como a
Confiabilidade entrega as datas das falhas de cada ativo; a ordem dos cartões dentro de Em acompanhamento (sugestão:
quem tem falha nova primeiro, depois o nível); o texto exato das mensagens de recusa.

## Como provar

- `python -m pytest -q` na worktree com o `.env` (inclui `test_sem_nomes_no_repositorio.py`, `test_tema.py`,
  `test_prefixo.py`, `test_dados_camada.py` e o novo `test_engenharia_acompanhamento.py`: pegar, encaminhar só para a
  Engenharia, quem pode agir, encerrar exige fim e diagnóstico, as datas, comentário só cifrado no livro, falha nova
  desde que entrou, o retorno só com falha nova, as abas e os números, o cadastro com exclusão sem reaproveitar ID, banco
  fora sem "nenhum" falso).
- A tela nas três abas e na gaveta, nos dois temas, em desktop e em 375 px.
