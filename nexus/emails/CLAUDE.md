# CLAUDE.md: os e-mails que o próprio Nexus manda (`nexus/emails/`, 25/11/2026)

Levi, 25/11/2026: "a informação do app de campo tem que chegar para o Nexus e o Nexus passa essa informação para os
e-mails"; "Tem e-mails que vão ser mandados só com dados do Nexus"; "É só a gente usar a mesma credencial"; "faça todas as
fases". Até 24/11 só o App de Campo mandava e-mail (o Nexus só controlava, `nexus/cadastro/CLAUDE.md`, "E-mails
automáticos"). A tela é a mesma: Base › E-mails automáticos, só administrador, com a seção "Do Nexus".

## O caminho de um e-mail

1. **Nasce** de três lados, e vira uma mensagem (`tipos.mensagem`: tipo "nx_...", referência sem nome nem e-mail, uma
   `chave` única, para quem e em cópia como `{email, papel}`, assunto e HTML):
   - o botão de teste (`nx_teste`) e o "mandar a prévia para mim" da tela;
   - a agenda dos e-mails criados na tela (`agenda.py` + `modelos.py`: "todo dia", "toda semana", "todo mês" ou só pelo
     "Mandar agora");
   - o evento do App de Campo (`evento_app.py`, a fase 3).
2. **Entra na fila** (`fila.py`): no disco da máquina que envia (`emails_fila.json` na pasta de dados). A mesma `chave`
   não entra duas vezes (a agenda que roda de novo depois de um reinício, o App que reenvia).
3. **A regra da tela vale** (`fila.aplicar`, a régua do App): desligado não manda e registra "desligado"; teste com
   lista manda só à lista, sem cópia, com "[Teste]"; normal com lista soma ou substitui. A regra mora no livro
   `nexus_email_regras` (`emails_controle.NEXUS`: o mesmo formato, cifra e assinatura do livro do App, num livro à parte
   porque o App conta como inválida a linha de tipo que ele não conhece). Sem ler a regra, não manda.
4. **O envio** (`envio.py`): Microsoft Graph, permissão de aplicativo Mail.Send, as MESMAS credenciais do registro do
   App de Campo no Entra ID, coladas em Base › Chaves das fontes, aba Nexus (`NEXUS_EMAIL_TENANT_ID`, `_CLIENT_ID`,
   `_CLIENT_SECRET`, `_REMETENTE`; o segredo é conferido ao gravar, pedindo o token, sem mandar e-mail). O segredo
   trocado no App tem de ser trocado aqui. Falhou: tenta de novo em 1, 5, 15, 30 e 60 min e de hora em hora; com 24 h,
   desiste e registra "falhou".
5. **O registro** (`registro.py`): um por destinatário, com o código HMAC (o mesmo do App), nunca o e-mail; o erro sem
   endereço. Diário no disco e o livro `nexus_email_envios · fato_envio_email` (35 dias, a cada 5 min quando muda), no MESMO
   desenho do Todos os envios do App: a tela lê os dois pela mesma conta (`emails_app.montar` com `catalogo=()`).

**Uma máquina só envia**: a chave `NEXUS_EMAIL_ENVIAR` = 1 (tela de Chaves ou .env), só no servidor. O PC do Levi roda
o mesmo código e, ligado nos dois, cada e-mail sairia duas vezes. O laço (`fila.ligar`, pelo `servir.py`) roda em toda
máquina servida e só dorme onde não envia; a tela diz em qual situação a máquina está.

## Quem recebe: o papel (`papeis.py`, a fase 2)

A lista fixa vale para todas as usinas; o papel acha a pessoa de cada uma. Da usina (a régua do De acordo da PT,
`decisao_pt.aprovadores`): Responsável UFV (o Responsável O&M da ficha), supervisor de campo da região (vaga aberta: o
coordenador), gestor de contrato. De setor (Base › Acessos › Pessoas e setores): TST (Segurança), COS, PCM, Supervisão
Campo, Engenharia. O e-mail da pessoa, nesta ordem: a ficha (cofre), o usuário do Fracttal ligado à ficha, o cadastro do
App ligado pelo nome, e o código da pessoa em Pessoas e setores. **Pessoa sem e-mail fica de fora e a prévia diz quem**;
nunca se inventa endereço. Na 1ª prévia (25/11/2026), 4 dos 10 Responsáveis UFV não tinham e-mail em lugar nenhum do
Nexus: é dado a completar no Registro mestre.

## Os e-mails criados na tela (`modelos.py`, `fontes.py`, a fase 4)

Nome, assunto, texto de abertura, FONTES (o que o Nexus já calcula; nenhuma régua nova), como sai ("um só" ou "um por
Responsável UFV, com as usinas dele", e "quem não tem pendência não recebe"), para quem e em cópia (papéis ou e-mails da
Grid e do cadastro) e a agenda. O livro `nexus_email_modelos` é só acréscimo e leva o modelo inteiro cifrado (chave HKDF
da NEXUS_PESSOA_HMAC, info `nexus:email:modelo/v1`); o nome e o assunto viram a linha do tipo e a referência, então a
tela recusa e-mail e nome de pessoa neles. **O e-mail novo nasce desligado** (`salvar` publica a regra "desligado"): liga
quem viu a prévia. A prévia (`/t/base/emails-automaticos/<id>/previa`) monta com os dados de agora, mensagem por mensagem,
quem recebe pelo nome e o e-mail numa moldura sem script; "Mandar esta para mim" põe só aquela na fila, como `nx_teste`.

A fonte "Pendências das usinas" é o Painel do responsável (`campo/painel_responsavel.montar` sobre a Visão do
responsável de 5 min) em e-mail: PT esperando o De acordo, OS atrasadas e pausadas com o motivo, usinas sem ronda há 7
dias ou mais, chamados de garantia abertos, extintores vencidos, usinas abaixo de 90% da meta; 12 linhas por seção e o
"e mais N" com o link do Painel do responsável. Pedido do Levi: o conteúdo passa por ele antes de ligar.

## O evento do App (`evento_app.py`, a fase 3: o lado do Nexus pronto, o do App a fazer)

O App continua sabendo quando um e-mail nasce e monta o texto; o Nexus decide quem recebe. `POST
/t/base/emails-automaticos/api/evento` (pública só para a assinatura, `auth.ROTAS_PUBLICAS`), com `X-Nexus-Ts` e
`X-Nexus-Assinatura` = HMAC-SHA256 de "<ts>." + o corpo, na chave HMAC-SHA256(NEXUS_PESSOA_HMAC, "nexus:email:evento").
Corpo: `tipo` (do App: `luvas_tst`, `seguranca_relato`, `pt_aviso`, `encaminhamento`), `id` único, `usina_id` ou
`local` (o nome do local no Fracttal), `referencia`, `assunto`, `html`, `sugeridos` (a reserva quando o papel não acha
ninguém). **202 = o Nexus cuida e o App não manda**; qualquer outra resposta (ou nenhuma em 20 s) = o App manda como
hoje. É a reserva: um reinício do Nexus nunca segura um aviso de segurança. Os papéis de cada um em `TIPOS_DO_APP` (as
luvas: TST e Responsável UFV, o pedido do Levi de 24/11/2026). Na tela, os quatro aparecem como "espera o App de Campo
entregar o evento" até o App passar a chamar.

## Como provar

`tests/test_emails_nexus.py` (a regra sobre a mensagem, a fila, o registro sem e-mail, o recuo e as 24 h, o desligado,
o livro à parte, o envio sem chaves e na prova, o token recusado sem segredo, os papéis, o modelo cifrado que nasce
desligado, a agenda, o um por responsável, a assinatura do App, o 202 e o 503, a tela, o editor, a prévia e a porta
pública). Na cópia de prova, `NEXUS_EMAIL_SAIDA_PASTA` faz o e-mail virar arquivo .html, e `NEXUS_EMAIL_ENVIOS_ARQUIVO`
põe o registro e a fila ao lado (nunca na pasta de dados de verdade); com `NEXUS_EMAIL_ENVIAR=1` e o laço ligado (a
cópia não roda o `servir.py`: ligue `fila.ligar(app)`), o teste sai de ponta a ponta. No servidor: colar as quatro
chaves, ligar o enviar só lá e mandar o teste do `nx_teste` para si.
