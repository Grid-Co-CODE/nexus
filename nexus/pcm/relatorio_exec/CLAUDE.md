# CLAUDE.md — Relatório executivo do PCM (cópia do painel)

Levi, 14/10/2026, com o print do modal "Relatório executivo" da aba Gestão PCM do painel do PCM: "Quero trazer esses três
relatórios para a plataforma, com as mesmas métricas e parâmetros e estilos". Os três tipos: **Interno Grid**,
**Cliente** e **Abertura da Semana**. Sobre a versão Cliente mostrar rolagens e o "Não coube": "O nexus não está
disponível para o cliente, é só para a organização mesmo!", e por isso ela fica igual à do PCM.

## O que é

- **CÓPIA**, não reescrita: `relatorio_exec.js` e `relatorio_exec.css` são os do repositório do PCM
  (`fillipefigueiro-source/gridco-pcm-data`; iguais ao `main` de lá em 14/10/2026, `e6cdab4`); `gpv_cel.css` são as
  linhas 86 a 92 do `css/preventivas.css` de lá (as células coloridas que a folha usa); `painel_pcm.js` são os trechos do
  `js/app.js` e do `js/preventivas.js` que o relatório chama (o escopo do login, a situação de cada MPA/MPS e a Fila da
  Gerencial), copiados linha a linha pelo `ferramentas/copiar_painel_pcm.py`, com a faixa de cada um no comentário.
  **Não edite nenhum deles**: o `tests/test_relatorios_pcm_executivo.py` confere o hash de cada um (`COPIAS` no
  `__init__.py`, com o fim de linha normalizado).
  - Por que cópia: no PCM o relatório roda inteiro no navegador (~1.300 linhas, com o formato de número e de data do
    navegador). Reescrever em Python byte a byte levaria horas e arriscaria divergir nos detalhes; a cópia dá os mesmos
    números, parâmetros e visual por construção. É o mesmo caminho do motor do PCM (`nexus/pcm/motor`) e do OS Creator.
- **A costura** (`apoio.js`, escrito aqui, o único JS daqui que se edita): o `S` do login é sempre administrador (o
  Nexus é só da organização); o `GESTAO_DB` é o gestao_pcm.json lido do Nexus; a Gerencial vem do `gerencial.json`; e a
  partida pela Central (`rxPartir`) põe a escolha do endereço nos campos que o `rexGerar` lê (os mesmos ids do modal do
  painel, escondidos), gera a folha e avisa a Central (`postMessage`) que ela ficou pronta ou o que deu errado (o `alert`
  do painel vira esse aviso). Não declare aqui nada que já esteja no `painel_pcm.js`: nome declarado duas vezes quebra o
  JS da moldura (o teste confere).
- **Ao servir** (`TROCAS_JS`), e só ao servir: os emojis da interface saem (regra do Nexus) e "Voltar ao painel" vira
  "Voltar". A cópia no disco segue idêntica.
- **A tela** (14/10/2026, Levi: "Use a mesma estrutura do print 1 para todos os relatórios de todos os setores"; o print 1
  era a tela do Relatório diário) segue a estrutura de toda a Central de emissão (`/t/relatorios/pcm-executivo?tipo=`, do
  setor PCM, setor trocável na Central):
  - à esquerda, os blocos da Central (os três tipos são itens do bloco "Relatório Gerencial PCM", `TIPOS`) e o período e
    o escopo do modal do painel: os cinco períodos prontos (`PRESETS`, com a conta do `rexPreset` de lá no
    `static/relatorios.js`), De/Até, Cliente, Equipe Cluster, Usinas (a cascata do `rexEscopoMuda`: o cliente filtra as
    usinas pelo começo do nome) e "Desconsiderar preventivas criadas no período". A Abertura da Semana não tem período
    (no painel ela usa a semana mais recente da programação);
  - à direita, a folha: o documento da moldura (`.../painel/?...&gerar=1`, modo "previa" do `painel_html`), em papel
    branco e sem a barra do painel; "Imprimir / PDF" é o da Central e imprime só a folha (o CSS de impressão do PCM).
    "Abrir em nova aba" abre o mesmo documento no modo "aba", com a barra do painel. Sem `gerar`, o documento é a tela
    de partida do painel (o botão que abre o modal do PCM), para quem chegar direto.
- **Os dados** saem do `nexus/pcm/fonte.py` (cópia de 5 min no servidor, ETag no GitHub), ao lado da moldura
  (`.../painel/gestao_pcm.json`, `banco_dados.json` e `confiabilidade.json`, porque o JS os lê pelo endereço relativo),
  compactados com gzip (o gestao_pcm.json de 14/10/2026: 14,9 MB; compactado, 0,75 MB) e guardados por versão do arquivo.
- **A Gerencial** (Levi, 14/10/2026: "traz a Gerencial cifrada para aparecer o MPA/MPS"): o `mpas.json` do PCM é
  cifrado (o repositório é público) e a senha é a do **login de administrador do painel do PCM** (o painel guarda a
  senha do login na sessão e abre a Gerencial com ela). No Nexus quem abre é o servidor, com a `NEXUS_PCM_MPAS_SENHA`
  do .env, na mesma cópia da Gestão PCM (`nexus/pcm/telas.py`, `_gerencial`), e o `.../painel/gerencial.json` entrega
  à moldura só o que a Fila lê (`manut` e `bd`), para quem a tela deixa entrar. Com ela, o Interno Grid mostra "MPA/MPS
  atrasadas" e cita "+ Gerencial (aba MPAS)"; sem ela (ou com a senha errada), 503 e o relatório sai como no painel sem a
  senha: "tarefas abertas há +30 dias". A versão Cliente nunca mostra a Gerencial (regra do painel).

## Como provar

- `python -m pytest -q tests/test_relatorios_pcm_executivo.py tests/test_relatorios_blocos.py`.
- A folha, numa cópia de prova com os JSON reais do PCM (`ferramentas/subir_copia_de_prova.py`, com
  `NEXUS_PCM_GESTAO_FONTE`, `NEXUS_PCM_FONTE` e `NEXUS_PCM_CONFIABILIDADE_FONTE` apontando para uma cópia do repositório
  de lá). Sem a senha real, a Gerencial se prova com uma sintética cifrada com senha de prova
  (`nexus/pcm/prova_gestao.py`, `gerencial_sintetica`, e `NEXUS_PCM_MPAS_FONTE`/`NEXUS_PCM_MPAS_SENHA`). Em 14/10/2026,
  01 a 14/10: 1.136 OSs criadas, 1.059 finalizadas, 14% de aderência (138/964), 153 corretivas abertas, iguais às do
  painel.

## Como atualizar quando o PCM mudar o relatório

1. Copie de novo o `js/relatorio_exec.js`, o `css/relatorio_exec.css` e as linhas das `.gpv-cel` do
   `css/preventivas.css` (o `gpv_cel.css`).
2. Se o `js/app.js` ou o `js/preventivas.js` mudaram, confira as faixas de `TRECHOS` no `ferramentas/copiar_painel_pcm.py`
   (as funções podem ter mudado de linha) e rode `python ferramentas/copiar_painel_pcm.py <pasta do PCM> <commit>`. Se o
   relatório passou a chamar outra função do painel, acrescente a faixa dela lá (nunca no `apoio.js`).
3. Rode `python -X utf8 -c "from nexus.pcm import relatorio_exec as R; print({n: R.hash_da_copia(n) for n in R.COPIAS})"`
   e ponha os hashes novos em `COPIAS`, com o commit de lá em `ORIGEM`.
4. Se o modal do painel mudou (outro período pronto, outro campo), acompanhe a coluna da esquerda
   (`relatorios/pcm_executivo.html`, `PRESETS`, `static/relatorios.js`) e os ids que o `rxPartir` preenche.
5. Rode os testes e abra a tela numa cópia de prova com dado real.
