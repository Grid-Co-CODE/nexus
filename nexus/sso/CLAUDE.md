# CLAUDE.md — SSO da zeladoria (a Integração de Segurança dos fornecedores) no banco do Nexus

O SSO é o app de saúde e segurança dos fornecedores da zeladoria (`sso-zeladoria.gridco.com.br`): integração por vídeo
com quiz e certificado, APR, checklist de EPI, vistoria antes e depois, diário de obra e o cronograma dos fornecedores, e
a Gestão (a equipe da Grid Co. aprova presenças e lê tudo). É um site estático no Cloudflare do HEAD da zeladoria, que
falava direto com o Supabase, o mesmo projeto do Radar. O pacote de migração (código byte a byte da produção, o esquema,
as permissões e os volumes) ficou fora do repositório, em `Downloads\Deploy\sso_pacote_2026-11-12` no PC do Levi.

Levi, 12/11/2026, com o Supabase parado (a cota estourou em 11/11): "vamos migrar, isso sim! pode pôr no mesmo banco do
Nexus"; e, no mesmo dia, **"Esse site fica a parte do nexus, o objetivo é apenas migrar os dados, tirar do supabase e
passar para o PG"**, escolhendo a API do Nexus para o site. O site fica no Cloudflare do HEAD, com a mesma cara; o Nexus
guarda os dados e responde no lugar do Supabase. Nada do SSO aparece no menu do Nexus. Quem mexe no SSO pelo Claude
Code (o HEAD da zeladoria) tem o roteiro em `ROTEIRO_CLAUDE_CODE.md`, nesta pasta.

## Como funciona

- **O site troca um arquivo só:** o `shared/supabase-client.js` dele pelo `site/supabase-client.js` desta pasta (o
  passo a passo do HEAD: `site/LEIA.md`). Esse arquivo é o `window.supabase` que o app já usa (`from().select().eq()`,
  `insert`, `update`, `delete`, `storage.from().upload`, `auth`, `rpc`), e fala com a API do Nexus em
  `https://app.gridco.com.br/t/sso`. O `/t/` porque o Caddy do servidor só manda ao Nexus os segmentos dele; um `/sso`
  cairia na Performance.
- **A API** (`api.py`, o blueprint `sso`): `/api/v/<view>` lê, `/api/gravar` grava, `/api/arquivo` envia arquivo,
  `/api/rpc/atualizar_progresso`; as duas funções do Supabase no mesmo caminho (`/functions/v1/iv-upload-arquivo`,
  `/functions/v1/iv-presenca-assinatura`) e os arquivos em `/storage/v1/object/public/<bucket>/<caminho>`, porque o JS do
  site monta esses endereços sozinho a partir do `IV_SUPABASE_URL`. O vídeo da sessão ativa sai em `/video/...`.
- **Rotas públicas, conscientes** (`auth.ROTAS_PUBLICAS`, a lista `api.PUBLICAS`; o teste cobra): o fornecedor não tem
  conta. Cada uma confere o passe ou cai na regra do anônimo, com o limite por IP (`limite.py`: largo, porque a equipe
  de uma usina sai pelo mesmo IP da operadora), o teto de tamanho e o `Origin` do site (`NEXUS_SSO_ORIGENS`, padrão
  `https://sso-zeladoria.gridco.com.br`; a resposta leva o CORS só para ele).
- **O endereço público, nunca o `request.host`** (`api.endereco_publico`): no servidor o pedido chega pelo proxy com o
  endereço interno (`10.32.28.19:5070`). Em 13/11/2026, o 1º dia do site no Nexus, toda vistoria, APR, EPI e diário com
  foto foi recusada ("endereço de arquivo que não é do SSO"), e o link do vídeo e das fotos da Gestão saía com o
  endereço interno. Vale `NEXUS_SSO_ENDERECO`; sem ela, a máquina local (o PC, a cópia de prova, os testes) usa o próprio
  endereço, e o resto, `https://app.gridco.com.br`. A página do administrador mostra o endereço público, a máquina e o
  IP que o Nexus vê. Prova atrás do proxy: a `porta_local.py` mantém o Host do navegador, como o Caddy por padrão, e
  não imita o servidor. Para provar, passe a cópia de prova por um repassador que troque o Host por um endereço interno e
  ponha `NEXUS_SSO_ENDERECO` com o endereço do repassador.
- **A Gestão entra pelo login do Nexus.** Sem passe, a página da Gestão vai a `/t/sso/voltar?para=<a Gestão>`, que
  exige o login (Fracttal ou senha de administrador; o setor não conta: `sso.voltar` está nos `LIVRES` do portão de
  setor) e volta com o passe no fragmento (`#nexus_sso=`, que não vai a servidor nenhum). O passe (`regras.py`) diz só o
  e-mail do login (ou que é o administrador), vale 8 h e vai no `Authorization`, como o token do Supabase ia. O
  "administrador" do passe é reconferido a cada pedido na lista de agora; o da senha de administrador (sem e-mail) vale
  2 h. Sair do Nexus não apaga o passe já emitido (o "Sair" do site apaga o dele). O `para` só aceita o endereço do site
  e o caminho `/gestao`.
- **O perfil:** a pessoa é casada pelo e-mail do login com o `iv_perfis` (como a Zeladoria com o `perfis` do Radar); sem
  linha, o id é um uuid fixo do e-mail, e o app cria a linha "pendente" (o servidor força o pendente e o próprio id). O
  administrador do Nexus ganha a linha aprovada no 1º acesso (`/api/eu`), com ou sem e-mail.

## Quem pode o quê (o RLS da seção 7.2 do pacote, `esquema.py`)

- **Fornecedor (sem passe):** só envia. Lê só o que o formulário precisa: a sessão ativa, a própria visualização pelo id
  (a lista inteira, que o RLS deixava, não sai) e as usinas do diário. Na linha dele, o servidor decide os campos dele
  (`DO_SERVIDOR`: a presença nasce "pendente" e origem "app", sem aprovação nem certificado; a vistoria sem marca de
  edição), confere que a sessão está ativa e que todo endereço dentro da linha é arquivo deste Nexus num bucket do SSO ou
  assinatura desenhada (`data:image/...`), e a fase da vistoria só "antes" ou "depois". Tetos (revisão de 12/11/2026,
  contra encher a memória e o disco do servidor): até 20 linhas e 2 MB por pedido, 1 MB por linha (a maior real tem
  130 KB), e por hora 120 linhas e 50 MB por IP, 500 MB de linhas e 10 GB de arquivos de todos os anônimos juntos.
- **Pendente:** só a própria linha do perfil. **Aprovado:** tudo, como o `is_gestao_aprovada()`.
- **O que o Postgres garantia** (`esquema.py`, copiado do `schema_sso_atual.sql`): os padrões (`gen_random_uuid()`,
  `now()`, as listas vazias, os textos do certificado), as obrigatórias, as listas fechadas (os CHECK), a chave
  repetida. A linha nova tem todas as colunas (o que não veio fica nulo). O cronograma_historico só recebe linha nova.

## A gravação

O gravador da Zeladoria (`nexus/zeladoria/gravacao.Gravador`), com o mapa do SSO (`gravacao.GravadorSSO`: as
`TABELAS`, o diário `<NEXUS_DADOS>/sso/diario.jsonl` cifrado com o contexto `sso/diario`, o prefixo da cifra `sso`):
a mudança entra na hora no estado e no diário; o lote (2 s sem mudança ou 20 s) grava os livros que mudaram pelo
`livros.publicar`, conferindo antes e depois, e só então esvazia o diário; ao subir, o diário se reaplica. As abas que
nunca encolhem (`tabelas.SO_CRESCE`: as presenças, as visualizações, a APR, a vistoria, as usinas do diário, o histórico
e o inventário) têm a trava `so_cresce` do catálogo. A lista de usinas do diário não: o fornecedor escreve nela sem lista
fechada (já escreveu o nome de uma pessoa), e o administrador tira o que não é usina na página `/t/sso/admin`.

- **Uma máquina grava:** a mesma da Zeladoria (o interruptor da página da troca, `/t/zeladoria/troca`, ligado no servidor
  desde 12/11/2026). `NEXUS_SSO_GRAVA` (1 ou 0) vence onde existir. Onde não grava, a API responde 503 "este Nexus não
  guarda o SSO", e o site mostra o erro sem perder o que foi digitado.
- **A 1ª leitura** dos sete livros leva ~40 s (o APR tem 4,8 MB): o `servir.py` aquece por trás ao subir
  (`api.aquecer_ao_subir`), e o pedido nunca espera a leitura: sem o gravador carregado, ela começa por trás e o pedido
  volta 503 "carregando" (revisão de 12/11/2026: 32 pedidos esperando os 40 s tomavam todas as threads e paravam o Nexus
  inteiro). Toda falha da leitura espera 30 s antes da próxima tentativa.
- **O progresso do vídeo** (o bug da seção 6 do pacote: o app chamava `rpc("atualizar_progresso")` e a função estava em
  outro esquema; 0 de 52 visualizações tinham progresso): grava pelo Nexus, com a regra da função do banco (concluído
  com o maior entre 97% e a duração menos 3 s) e um degrau de 30 s (o app manda a cada 4 s; sem o degrau, o livro da
  integração seria regravado sem parar).
- **O link de assinatura** (`/campo/assinar.html?id=`): o GET dá só o nome e se já assinou; o POST grava só se ainda não
  há assinatura, com as mesmas mensagens da função do Supabase.

## A cifra

O molde da Zeladoria (`nexus/zeladoria/guardar.py`, com a regra de `tabelas.coluna_cifrada` e o contexto
`sso/<aba>/<chave>/<coluna>`). Todo texto, JSON e lista vai cifrado: nome, CPF, telefone, e-mail, empresa, as
assinaturas em base64, os formulários inteiros e **todo texto que o fornecedor escreve sem lista fechada** (12/11/2026:
um fornecedor digitou o nome de uma pessoa como usina em 5 vistorias e na lista do diário, que a 1ª cópia tinha deixado
em claro; a revisão do mesmo dia achou a mesma porta no número da OS, no serviço da vistoria e do diário e no número do
certificado). Em claro só ids, datas e o que é lista fechada e conferida: os estados, a origem, a fase da vistoria e o
serviço do EPI. A leitura aceita o texto em claro da cópia antiga (só
decifra o que está cifrado), e o botão "Regravar cifrado" da página do administrador regrava os sete livros com a regra
de agora. **Feito no servidor em 12/11/2026** (os sete livros na versão 1; conferido no banco por GET: a usina, o número
da OS, o serviço, o número do certificado e a lista de usinas do diário, 0 em claro). A página diz "Regravando" enquanto o
lote grava, relê a situação a cada 3 s (`/t/sso/admin/situacao`) e diz "Pronto" ou o erro; o 2º clique durante a
regravação não pede outra. Caso: na 1ª vez a página ficou em "gravando…" sem se atualizar, e o Levi não soube que tinha
terminado. O histórico de cada linha na API ainda guarda o valor antigo (só a T.I. apaga).
A assinatura grande passa de 32 mil caracteres e vai partida em colunas `__p2`, `__p3`...

## O que está no banco do Nexus

Um livro cifrado por módulo (`tabelas.py`), cada aba com o nome da view que o app usa, mais a aba `atualizacao` (o tipo
de cada coluna, a chave, quantas linhas, a versão):

| Livro | Abas |
|---|---|
| `nexus_sso_integracao` | `iv_sessoes_video`, `iv_visualizacoes`, `iv_presencas`, `iv_perfis` |
| `nexus_sso_apr` | `apr_submissoes` |
| `nexus_sso_epi` | `epi_submissoes` |
| `nexus_sso_vistoria` | `vistoria_checklists` (a tabela solta `public.checklists` do Supabase; o app pede "checklists") |
| `nexus_sso_diario` | `diario_registros`, `diario_usinas` |
| `nexus_sso_cronograma` | `cronograma_periodos`, `cronograma_historico` (só cresce), `cronograma_fornecedores` |
| `nexus_sso_arquivos` | `arquivos`: o inventário dos 5.079 arquivos do Storage (bucket, caminho, tamanho, tipo) |

## Os arquivos (fotos, vídeos, PDFs dos certificados)

No disco do servidor, `<NEXUS_DADOS>/sso/arquivos/<bucket>/<caminho>`, com o mesmo bucket e caminho do Storage
(`arquivos.py`). ~1,5 GB por mês em outubro de 2026: grande demais para o banco.
- **Quem envia:** o fornecedor nos buckets dos formulários (`apr-arquivos`, `epi-fotos`, `checklist-fotos`,
  `diario-midia`), nunca por cima de um arquivo que já existe nem no caminho de um arquivo antigo do inventário (a foto
  plantada passaria por prova na Gestão e por resgatada); a Gestão em todos, com o `upsert` (o certificado corrigido
  sobrescreve). O teto do corpo vale ANTES de ler o formulário (`api._limitar_arquivo`): depois da 1ª leitura do
  `request.form`, o Flask já conferiu com o limite geral de 25 MB, e o vídeo de 28 MB voltava 413. O tipo pelos primeiros bytes (foto, vídeo, PDF; nunca HTML). Tetos: foto 15 MB, vídeo do diário 50 MB (o
  maior que chegou tinha 45,8 MB), vídeo da integração 200 MB. O disco com menos de 2 GB livres recusa.
- **Quem abre:** só com o link assinado (`?a=`, 12 h) que a Gestão recebe ao ler: toda URL de arquivo dentro das linhas
  (`/storage/v1/object/public/...`, de qualquer endereço, inclusive as antigas do Supabase) sai trocada pelo endereço do
  Nexus com a assinatura, e o que a Gestão manda de volta vai ao banco sem ela. O `<img>` e o html2canvas do PDF não
  mandam o passe, por isso a assinatura no endereço (e o CORS para o site). No Supabase os buckets eram públicos. O envio
  devolve o link assinado também ao fornecedor, para a miniatura da foto que ele acabou de anexar (a vistoria e o diário
  mostram a foto pelo endereço; sem a assinatura ela aparecia quebrada), e a linha dele vai ao banco sem a assinatura. O
  vídeo da sessão ativa abre sem login (`/video/...`, com o Range).
- **Os antigos (~2,5 GB) ficaram travados no Supabase** desde 11/11/2026 (402 até pelo painel): aparecem quebrados até o
  resgate. A página do administrador (`/t/sso/admin`) recebe uma pasta baixada de um bucket e põe cada arquivo no caminho
  do inventário que termina igual. **O vídeo da integração (28 MB) também ficou lá:** até o administrador enviá-lo pela
  mesma página (ou a Gestão, em Sessões / Quiz), a integração não passa do vídeo.

## A cópia (feita uma vez, em 12/11/2026)

1. **Exportar no SQL Editor do Supabase** (o painel ainda lê o banco), em três partes: o APR; o EPI com a vistoria; e o
   resto com os tipos (`format_type`), as chaves primárias e o inventário (`storage.objects` dos sete buckets). Salvas
   fora do repositório (`Downloads\Deploy\sso_2026-11-12`): têm dado pessoal.
2. **Ensaiar:** `python ferramentas/copiar_sso.py --pasta <pasta das partes>` (só conta). **Gravar:** com `--gravar`.
   Depois que o Nexus gravar alguma mudança (versão acima de 0), a cópia recusa passar por cima.

Contagens da exportação de 12/11/2026: sessões 1, visualizações 52, presenças 31, perfis 5, APR 162, EPI 78, vistorias
85, diário 104, usinas 54, cronograma 8, histórico 62, fornecedores 8, arquivos 5.079.

## Como provar

- `python -m pytest tests/test_sso_api.py tests/test_sso_copia.py tests/test_sso_ponte.py -q` (com o `.env`): o
  fornecedor envia e não lê, o pendente só vê o perfil dele, o aprovado vê com os links assinados e aprova, a linha do
  fornecedor nasce pendente, as obrigatórias e as listas fechadas, o link de outro site recusado, o limite por IP, o
  arquivo só com a assinatura, o certificado que sobrescreve, o vídeo ativo sem login, o progresso em degraus, o link de
  assinatura uma vez, o diário que se reaplica, a cifra no banco e a usina em claro antiga regravada cifrada; a ponte do
  site no node (`tests/sso_ponte_node.js`).
- **A prova de ponta a ponta (12/11/2026):** a cópia de prova (`ferramentas/subir_copia_de_prova.py --porta 5171`, com
  `NEXUS_SSO_GRAVA=1`, `NEXUS_SSO_ORIGENS=http://127.0.0.1:5187`, `NEXUS_DADOS` de rascunho e uma `NEXUS_SECRET_KEY`
  descartável, para o passe tirado nela não valer fora) e o site do pacote servido em `127.0.0.1:5187` com o arquivo
  novo (só a linha `var NEXUS` trocada). Feitos pelo site, com dado fictício e o banco real só lido: a integração
  inteira (vídeo enviado pela página do administrador, quiz, assinatura, presença), a APR com foto, o EPI, a vistoria e
  o diário com foto, o fornecedor lendo 0 linhas; a Gestão pelo login do Nexus (as 11 abas, 9 aprovações), o perfil com
  assinatura, a aprovação com o certificado (PDF de 587 KB no disco), o certificado e a foto da APR abrindo só com a
  assinatura (sem ela, 403), e o Excel das cinco abas (APR 163 linhas, EPI 78, vistoria 85, diário 104). A página do
  administrador no computador e a 375 px, sem rolar de lado.

## O que falta

- **O HEAD publicar o arquivo novo no site** (`site/LEIA.md`). Até lá, o site segue falando com o Supabase parado.
- **O vídeo da integração** no Nexus (página do administrador): sem ele, a integração não passa do vídeo.
- **Os gestores entrarem no Nexus:** o login é o do Fracttal (ou a conta Microsoft, quando a T.I. ligar); quem não tem
  conta lá não chega à Gestão.
- **Os arquivos antigos:** resgatar se o Storage do Supabase voltar, pelo inventário.
- **Arquivo órfão:** o fornecedor envia as fotos antes da linha; foto de um envio que falhou fica no disco sem dono.
