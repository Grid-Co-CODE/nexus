# CLAUDE.md — Relatório executivo do PCM (cópia do painel)

Levi, 14/10/2026, com o print do modal "Relatório executivo" da aba Gestão PCM do painel do PCM: "Quero trazer esses três
relatórios para a plataforma, com as mesmas métricas e parâmetros e estilos". Os três tipos: **Interno Grid**,
**Cliente** e **Abertura da Semana**. Sobre a versão Cliente mostrar rolagens e o "Não coube": "O nexus não está
disponível para o cliente, é só para a organização mesmo!", e por isso ela fica igual à do PCM.

## O que é

- **CÓPIA**, não reescrita: `relatorio_exec.js` e `relatorio_exec.css` são os do repositório do PCM
  (`fillipefigueiro-source/gridco-pcm-data`, commit `fb21576`, 14/10/2026); `gpv_cel.css` são as linhas 86 a 92 do
  `css/preventivas.css` de lá (as células coloridas que a folha usa). **Não edite**: o `tests/test_relatorios_pcm_executivo.py`
  confere o hash de cada um (`COPIAS` no `__init__.py`, com o fim de linha normalizado).
  - Por que cópia: no PCM o relatório roda inteiro no navegador (~1.300 linhas, com o formato de número e de data do
    navegador). Reescrever em Python byte a byte levaria horas e arriscaria divergir nos detalhes; a cópia dá os mesmos
    números, parâmetros e visual por construção. É o mesmo caminho do motor do PCM (`nexus/pcm/motor`) e do OS Creator.
- **A costura** (`apoio.js`, escrito aqui): o que o JS espera do painel. As funções do painel vêm copiadas como estão
  (`gpScopedTarefas` e `_cliEq` do `js/app.js`, `GPV_RX` do `js/preventivas.js`); o `S` do login é sempre administrador
  (o Nexus é só da organização), e o `GESTAO_DB` é o gestao_pcm.json lido do Nexus. A Gerencial cifrada (MPAS) não vem:
  sem ela o JS mostra "tarefas abertas há +30 dias" no lugar de "MPA/MPS atrasadas", como no painel sem a senha.
- **Ao servir** (`TROCAS_JS`), e só ao servir: os emojis da interface saem (regra do Nexus) e "Voltar ao painel" vira
  "Voltar". A cópia no disco segue idêntica.
- **A tela** é a da Central de emissão (`/t/relatorios/pcm-executivo`, do setor PCM, setor trocável na Central). Ela traz
  uma moldura (`.../painel/`) com o documento do PCM: a tela de partida (o botão abre o modal do PCM), o modal com os
  tipos, o período e o escopo, e a folha com "Imprimir / PDF". A moldura isola o CSS do PCM do CSS do Nexus.
- **Os dados** saem do `nexus/pcm/fonte.py` (cópia de 5 min no servidor, ETag no GitHub), ao lado da moldura
  (`.../painel/gestao_pcm.json`, `banco_dados.json` e `confiabilidade.json`, porque o JS os lê pelo endereço relativo),
  compactados com gzip (o gestao_pcm.json de 14/10/2026: 14,9 MB; compactado, 0,75 MB) e guardados por versão do arquivo.

## Como atualizar quando o PCM mudar o relatório

1. Copie de novo os três arquivos do repositório do PCM (o `gpv_cel.css` são as linhas das `.gpv-cel` do
   `css/preventivas.css`).
2. Rode `python -X utf8 -c "from nexus.pcm import relatorio_exec as R; print({n: R.hash_da_copia(n) for n in R.COPIAS})"`
   e ponha os hashes novos em `COPIAS`, com o commit de lá em `ORIGEM`.
3. Se o JS passou a usar outra função do painel, traga-a para o `apoio.js` (copiada como está).
4. Rode os testes e abra a tela numa cópia de prova com dado real.
