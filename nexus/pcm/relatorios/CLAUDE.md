# CLAUDE.md — relatórios do PCM na Central de emissão

Levi, 14/10/2026, com o print da tela Relatórios do painel do PCM (pcm.gridco.com.br): "Quero trazer esses quatro
relatórios para a plataforma, com as mesmas métricas e parâmetros e estilos. Comece a desenvolver para o Nexus".
Os quatro: **Relatório diário de manutenção**, **Recuperação da tarde**, **Fechamento da semana** e **Alerta da
programação**. No mesmo pedido vieram os três tipos do "Relatório executivo" da aba Gestão PCM do painel (Interno Grid,
Cliente, Abertura da Semana): são outro código, só em JavaScript (`js/relatorio_exec.js` do PCM), e vieram como cópia
numa moldura em `nexus/pcm/relatorio_exec` (tela `pcm-executivo`, ver o CLAUDE.md de lá).

## De onde vem cada coisa

- **As contas e a folha** são CÓPIA do Python do PCM (`relatorio_diario.py` e `relatorios_semana.py` do repositório
  `fillipefigueiro-source/gridco-pcm-data`): é o Python que gerava os relatórios arquivados e os e-mails (o
  `js/relatorios.js` do painel era o espelho dele no navegador). Um módulo por relatório: `diario.py`, `tarde.py` (lá a
  pasta é "matinal"), `fechamento.py`, `alerta.py` (as 17 checagens); o comum em `regras.py`.
- **As entradas** são os mesmos arquivos do mesmo repositório (`dados.py`, pelo `nexus/pcm/fonte.py`, cópia de 5 min):
  `banco_dados.json` e `gestao_pcm.json` (obrigatórios), `gerencial.json`, `engenharia.json`, `operacoes.json` e
  `relatorios/feriados.json` (sem eles a parte deles sai vazia, como no PCM). Nada vai ao Fracttal.
- **O setor:** os quatro nascem do setor PCM (quem é do PCM os vê sem marcar); o administrador troca o setor de cada
  um na Central de emissão, seção "Setor de cada relatório" (`nexus/auth/dono_relatorio.py`).
- **A tela** é a da tela Relatórios do painel (`telas.py`, `templates/relatorios/pcm.html` da torre Relatórios,
  `static/relatorios-pcm.css` e `static/relatorios.js`): os blocos da Central no lugar do "1 · Tipo" (14/10/2026, Levi:
  "Use a mesma estrutura do print 1 para todos os relatórios de todos os setores": "Relatórios Padrão PCM" com os
  quatro e, abaixo, "Relatório Gerencial PCM"), "Período e recorte" (dia ou semana, cliente, cluster ou supervisor, em
  cascata como as outras telas do PCM), Gerar, a folha ao lado (na moldura, reduzida inteira para caber, como a
  impressão do Chrome) com "Imprimir / PDF" e "Abrir em nova aba", e os emitidos automaticamente.
- **A margem da prévia** (Levi, 14/10/2026: "deixa o texto comendo um pouco a margem da página ... quando eu transformo
  em PDF fica normal!"): tabela que não quebra linha passa da largura do A4 e a prévia alarga a folha até o conteúdo;
  o `scrollWidth` não conta a margem da direita do papel, e o texto encostava na borda, com uma barra de rolagem por
  cima. Agora a folha alargada ganha a mesma margem dos dois lados e não rola por dentro (`ajustar` no
  `static/relatorios.js`). Medido no diário de 13/10: 45 px de cada lado, a folha com 974 px.
- **A emissão automática** (`agenda.py`) segue os horários do robô do PCM: diário na 1ª volta depois das 06:00 (sobre
  ontem, todo dia); tarde depois das 13:00 de dia útil (feriado não pula); fechamento na sexta depois das 17:00, sem
  recuperar no sábado; alerta quando aparece semana mais nova que a ativa no banco_dados (publicada pelo Nexus ou pelo
  PC do PCM) e de novo quando ela é republicada (`geradaEm`). Uma thread por processo (`app.py`, `servir.py`), volta a
  cada 5 min, `NEXUS_PCM_RELATORIOS_AUTO=0` desliga numa máquina. "Já emitido" é a folha guardada: o servidor que
  reinicia (todo push) emite o que faltou e não emite duas vezes.
- **O arquivo** (`arquivo.py`): `<pasta de dados>/pcm/relatorios/<tipo>/<ref>.html`, diário e tarde por 30 dias,
  fechamento e alerta sem limpeza, como o `relatorios/` do PCM. É documento, não dado: não vai ao banco. O que a emissão
  precisa saber de volta vai em `<meta name="nexus-...">` no próprio HTML.
- **E-mail:** não há. O PCM tinha o envio e nunca enviou (SMTP nunca configurado; as 60 emissões diziam "SMTP não
  configurado"); o servidor do Nexus não tem saída de e-mail.

## O que mudou de propósito (e só isto)

- **Números no formato brasileiro**, como a tela do painel (o JS): "66,8 h", "1.469 h", e o meio arredonda para cima
  (82,5% vira 83%). O Python do PCM escrevia "66.8 h" e arredondava o meio para o par.
- **O texto que apontava para o painel** aponta para o Nexus (`regras.TROCAS_DE_TEXTO`): o rodapé diz "Relatório gerado
  pelo Nexus · app.gridco.com.br"; "no painel → Semana" vira "no Nexus → PCM → Tarefas e OS"; "módulo Confiabilidade"
  vira "Engenharia → Confiabilidade"; o "Responder este e-mail" saiu (não há e-mail).
- **O subtítulo do diário** diz "o que aconteceu ontem" no automático (sempre ontem) e "no dia" sob demanda (como o JS).
- **O recorte** da emissão sob demanda é o do JS (`rowsDe`, `tarefasG`, `eventosGer`): cliente igual; "cluster /
  supervisor" casa com o cluster OU com o responsável. Recorta as linhas, as tarefas da Gestão PCM e os religamentos;
  o resumo de capacidade, as pendências e a qualidade (Alerta), a engenharia e o backlog do fechamento ficam da empresa
  toda, como lá; o backlog do diário com recorte é o das tarefas do recorte (como lá).
- **A logo** é a do PCM (`static/grid-h-verde.png`), embutida na folha para ela abrir sozinha.

## Como provar

- **Contas iguais às do PCM, byte a byte:** `python ferramentas/prova_relatorios_pcm.py <cópia do repositório do PCM>`
  roda as duas versões sobre os MESMOS arquivos, com o Nexus no formato do Python (`regras.modo_original`) e as trocas de
  texto desfeitas. Em 14/10/2026: **25 de 25 folhas iguais** (10 diários, 8 tardes, 4 fechamentos e 4 alertas, W39 a
  W42); com a meta mudada de 85 para 80, 6 de 12 deram diferente (a prova pega). Mudou uma regra aqui? Rode de novo.
  Regerar hoje não reproduz o arquivado de lá: o dado muda (as causas de uma semana velha já mudaram).
- **Testes:** `tests/test_relatorios_pcm.py` (PCM de mentira: as contas, o formato, o recorte, a tela, o setor PCM, os
  horários da emissão, a pasta) e `tests/test_relatorios_central_13_10.py`.
- **Na tela:** cópia de prova (`ferramentas/subir_copia_de_prova.py`) com `NEXUS_PCM_*_FONTE` apontando para os arquivos
  de uma cópia do repositório do PCM; em 14/10 o diário de 13/10 saiu com 56% de aderência (45 de 80), 92 não
  programadas, 41 religamentos e 2.112 de backlog atrasado.

## Riscos conhecidos (vêm do PCM, ficaram iguais)

- "OS" nas listas do diário é contagem de tarefas (a OS com 3 tarefas aparece 3 vezes), como lá.
- A tendência do fechamento usa só as semanas que estão no `banco_dados.json` (ele guarda 4).
- A capacidade é fixa em 44 h por cluster no gerador do banco_dados (`gerar_pcm_json.py`), e o `hh_util` não soma o
  deslocamento, mas o KPI de HH soma.
- Os feriados são os de 2026 da planilha do PCM (`relatorios/feriados.json`); 2027 depende de lá.
- O `operacoes.json` do PCM está parado desde 09/09: o recuo de cidade do Alerta pode sair como "UF xx".
