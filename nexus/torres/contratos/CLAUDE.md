# CLAUDE.md — Contratos e clientes

Torre do menu "Contratos e clientes". Telas vivas: **Contestações** (13/10/2026) e **Acessos dos clientes** (14/10/2026).
Clientes, Onboarding, Comunicação por cliente e Portal ainda são placeholder (a view com a mesma rota vence a genérica).
As regras moram em `nexus/contratos/` (`contestacoes.py`, `acessos_clientes.py`); a view e o template, aqui.

## Contestações

Levi, 13/10/2026: "Contestação ligada ao Nexus: em contratos e clientes no Nexus pode ter um lugar para essas
contestações separando setores!"; "ficaria na API do PG, pode aplicar e construir!".

**De onde vem.** O cliente contesta um dia no Dashboard Thopen (5080): clica na barra do dia no gráfico Energia ×
Irradiação e marca geração, disponibilidade, desligamento, string, tracker e/ou ronda. O 5080 avisa no Teams (ronda →
O&M › Zeladoria, o resto → O&M › Performance) e grava no banco o livro `thopen_contestacoes` · `contestacoes`
(`thopen/contestacao_banco.py` do repositório da plataforma). O 5080 é a FONTE; no catálogo, fato
`contestacao_cliente` (área `contratos`), registrado antes da 1ª gravação; "quem grava" = Dashboard Thopen (5080)
(`telas.QUEM_GRAVA_ORIGEM`).

**Grão.** 1 linha = 1 contestação × 1 setor (as mesmas mensagens do Teams). Colunas: `id`, `contestacao_id` (junta as
duas linhas quando o cliente marcou dos dois lados), `recebida_em` (UTC), `data_id_recebida`, `data_id_contestada_ini` e
`_fim`, `usina` (o nome do 5080), `usina_id` (o de-para do 5080; vazio quando a usina tem dois ids, como Primavera),
`setor`, `itens` (só os do setor, `;`), `avisado_teams` (sim/não: o Teams do setor recebeu), `origem`
(`dashboard_thopen`) e `dados_cifrados`.

**O que é do cliente vai só cifrado** (regra 8: a API do banco tem leitura aberta): nome, contato, mensagem e o que ele
via na tela naquele dia (geração, irradiação, disponibilidade, trackers, strings, comentário, ronda) num JSON em
`dados_cifrados`. Cifra **assimétrica** (X25519 + HKDF-SHA256 com a pública efêmera de sal + AES-256-GCM; prefixo
`cx1:`): o 5080, público, tem só a chave PÚBLICA (`THOPEN_CONTESTACAO_CHAVE_PUBLICA`) e não abre nada, nem o que ele
mesmo gravou; o Nexus abre com a PRIVADA (`NEXUS_CONTESTACAO_CHAVE_PRIVADA`, opcional no `config.py`): a que o administrador cola em Base → Chaves das fontes,
aba Nexus (14/10/2026: cifrada na pasta de dados do servidor, sem a T.I. e sem reiniciar) e, sem ela, a do `.env`
(`auth.chaves.valor`; regra em `nexus/casca/CLAUDE.md`, "Chaves do Nexus"). A tela sem chave leva a esse lugar. A cifra é presa à
linha (contexto `thopen_contestacoes/<id>/dados` como dado associado): copiada para outra linha, "não abre". O decifrado
vive só na memória da tela. Sem a chave, a tela lista as contestações com "cifrado" no lugar do cliente e diz por quê.
**O par de 13/10/2026** está em `C:\GridcoAuto\entrega-ti\contestacoes-chaves-2026-10-13\` (a privada no
`.segredo`, nunca impressa): perder a privada é perder o que já foi gravado; a cópia em cofre é item da virada.

**A tela.** Uma aba por setor com a contagem; a mais nova em cima: quando chegou (Brasília), a usina, o dia contestado,
o que contesta, o cliente e o contato, a mensagem, o que ele via na tela, se o Teams do setor recebeu ("não recebeu" = a
contestação só está aqui) e o responsável. Tela nova nasce FECHADA para os setores (Base → Acessos): o administrador vê;
marcar "Contestações" para Performance, COS e Zeladoria. **Que setor recebe o quê** (o 5080 decide, `thopen/contestacao.py`):
geração, string e tracker → Performance; disponibilidade e desligamento → COS (Levi, 15/10/2026: "Disponibilidade e
desligamento vão para o setor de COS"); ronda → Zeladoria.

**Cada setor vê só a sua** (Levi, 15/10/2026: "O setor só vê a contestação do próprio setor, exceto administrador"):
`_setores_visiveis` — administrador (a lista de agora; o Nexus recalcula `session["admin"]` a cada pedido), todas; quem
tem setor, só a de mesmo nome (os setores do Nexus são "Performance", "COS" e "Zeladoria", como os das contestações); outro
setor, nenhuma ("Nenhuma contestação para o seu setor"); portão por setor desligado (`NEXUS_ACESSO_POR_SETOR=0`,
testes), todas. **O servidor barra**, não só a tela: o card e as ações de uma contestação de outro setor dão 404.

**O acompanhamento** (Levi, 15/10/2026: "um botão 'Pegar para mim' ao clicar nesse botão o usuário se torna o
responsável por aquela demanda. Ao clicar na linha, vai aparecer um card sobrepondo a tela com um blur de fundo onde o
responsável poderá inserir atualizações sobre a demanda com data e hora salva"), em `nexus/contratos/tratamento.py`:
- **Pegar para mim**: quem entrou com login de pessoa (Fracttal ou Microsoft; a senha de administrador não diz quem é)
  vira o responsável. Com dono, só o administrador passa para si ("Assumir" na linha).
- **O card** (o `<dialog class="cr-modal">` da Visão do responsável, fundo desfocado): a contestação, o cliente, o
  responsável desde quando e as atualizações (a mais nova em cima, com data, hora e quem). Só o responsável de agora
  escreve; o resto do setor lê. A atualização grava sem sair do card e a contagem da linha acompanha na hora (o evento
  `close` do `<dialog>` não disparou no navegador do painel: nada depende dele).
- **O dado**: livro `nexus_contestacoes_tratamento` · `fato_tratamento_contestacao` (fato `tratamento_contestacao` no
  catálogo, registrado antes da 1ª gravação). 1 linha = 1 evento (`responsavel` ou `atualizacao`) sobre a linha do
  `thopen_contestacoes` (`contestacao_linha_id`); só acrescenta, sob a trava, relido antes e conferido depois. O
  responsável é o do último `responsavel` **pela ordem de gravação** (dois eventos no mesmo segundo ficavam na ordem do
  id, ao acaso). Quem (nome e e-mail) e o texto só cifrados (Cofre, a chave do cadastro); a pessoa pelo `pessoa_hmac`.

**Ainda não tem** (fica para quando o Levi pedir): status da demanda (concluída), soltar a demanda, filtro por usina ou
cliente, outros dashboards.

**Como provar.** `python -m pytest -q tests/test_contratos_contestacoes.py` (banco falso; com
`PLATAFORMA_REPO=<clone da plataforma>` o teste cruzado cifra com o código do 5080 e abre aqui). Em 13/10/2026, ponta a
ponta no banco de verdade: uma contestação TESTE pelo clique no gráfico do 5080 de ensaio (Guaratinguetá V, 06/10,
Geração + Ronda) gravou 2 linhas (Performance e Zeladoria); lida pela API aberta, nenhum nome, e-mail, mensagem ou kWh
em claro; esta tela, com a privada, abriu as duas. Essa linha TESTE ficou no livro (mensagem "Pode desconsiderar").

## Acessos dos clientes

Levi, 14/10/2026: "É possível implementarmos uma visão de login e senha para o dashboard thopen?" — contas **por pessoa,
ligada a um cliente**, administradas **aqui**; o painel sobe no servidor da T.I. em
`https://app.gridco.com.br/performance/` (entrada em `/performance/login`). Spec no repositório da plataforma:
`docs/superpowers/specs/2026-10-14-thopen-login-por-pessoa-design.md`.

**Quem grava o quê.** O Nexus grava as contas (`nexus_acessos_clientes` · `dim_conta_cliente`, no `catalogo.LIVROS`); o
5080 grava as senhas (`thopen_acessos` · `senhas`, em `CONHECIDAS`) e lê as contas a cada 2 min. Um livro por sistema:
nenhum sobrescreve o do outro. Esta tela só lê das senhas QUANDO cada conta definiu (nunca a senha).

**Grão e colunas.** 1 linha = 1 conta, o estado atual (o livro é trocado inteiro sob a trava, relido antes e conferido
depois pelo `livros.publicar`): `conta_id`, `carteiras` (`;`, na ordem Thopen, Copel, Matrix, Polaris; o papel `grid`
leva todas), `papel` (`cliente` ou `grid`: só a Grid força a releitura e grava os Comentários adicionais no painel),
`status` (`ativa`/`desativada`), `convite_hash` (sha256 do token), `convite_expira` (UTC, 72 h), `criada_em`,
`alterada_em`, `alterada_por_hmac` (`NEXUS_PESSOA_HMAC` do e-mail; "admin" na senha de administrador), `dados_5080` e
`dados_nexus`.

**O que é da pessoa vai só cifrado** (regra 8), duas vezes: `dados_5080` selado para a PÚBLICA do painel
(`NEXUS_ACESSOS_5080_PUBLICA`, colada em Base → Chaves do Nexus; X25519 + HKDF-SHA256 + AES-256-GCM, a receita do
`thopen/acessos.py`, info `thopen-acessos/v1`, contexto `nexus_acessos_clientes/<conta_id>/dados_5080`) e `dados_nexus`
no Cofre (a chave do cadastro), para esta tela. O espelho das contestações: lá o Nexus tem a privada; aqui, a pública.
Sem a pública, a tela avisa e não cria conta nem link.

**O link.** Uso único, 72 h, `<NEXUS_THOPEN_URL>/convite/<token>` (padrão `https://app.gridco.com.br/performance`). O
token só aparece uma vez, na tela (guardado na sessão até a volta do 303; `Cache-Control: no-store`), para mandar pelo
Teams ou WhatsApp (o e-mail do servidor está barrado no tenant); no banco, só o sha256. "Gerar link" troca o anterior e
sela o nome e o e-mail de novo para a pública EM USO: trocado o par do painel, é assim que a conta volta a abrir lá. Link
usado = o 5080 achou a linha de senha com o mesmo hash. Desativar apaga o link pendente e tira a pessoa do painel em até
2 min (a releitura do 5080).

**Quem pode.** Ver a lista: quem tem a tela (tela nova nasce FECHADA para os setores; o administrador vê). Agir (nova
conta, gerar link, desativar, reativar): só administrador (`session["admin"]`), POST só da própria página
(`_de_outro_site`) e com o código do formulário guardado na sessão. E-mail repetido é recusado ("gere um link novo").

**Como provar.** `python -m pytest -q tests/test_contratos_acessos_clientes.py` (banco falso; com
`PLATAFORMA_REPO=<clone da plataforma>` o teste cruzado sela aqui e abre com o código do 5080, e confere livro, aba,
carteiras, contexto e o hash do token). Em 14/10/2026, ponta a ponta no banco de verdade (Nexus de ensaio na 5072 e 5080
com `THOPEN_LOGIN=1` em `/performance` na 5088): conta TESTE criada nesta tela → lida pela API aberta, nada em claro →
o link abriu "Definir senha" com o nome (o 5080 abriu o selo) → senha definida, a linha de senha gravada (`cs1:`) → o
painel com só a carteira Thopen; outra usina, outra carteira e o Atualizar deram 403 → o mesmo link de novo: "já foi
usado" → sair e entrar pelo e-mail → desativada aqui às 14:11:02, fora do painel às 14:11:39. A conta TESTE ficou no
livro, DESATIVADA (a API não apaga).
