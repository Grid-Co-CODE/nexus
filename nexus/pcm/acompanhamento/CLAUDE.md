# CLAUDE.md — PCM → Acompanhamento (o painel de acompanhamento do PCM O&M no Nexus)

Levi, 14/10/2026, com o pacote de integração do "Painel PCM O&M" (`pacote-integracao-painel-pcm.zip`: o INTEGRACAO.md,
os scripts do pipeline e o `dash_template.html`): "Quero que libere na seção de PCM essa visão de acompanhamento. O design
quero alá Nexus, não quero que copie o design, mas as estruturas quero sim que mantenha!".

## O que é

A tela `/t/pcm/acompanhamento` (PCM → Acompanhamento PCM, do setor PCM: `Tela.do_setor`) com as cinco abas do painel:
**MPA**, **MPS** (as preventivas anuais e semestrais acompanhadas pela reunião de PCM, em 4 grupos), **Radar de Backlog**
(OS em processo abertas há mais de 25 dias), **Mapa** (a carga dos times por cluster ou usina e a mobilização entre duas
usinas) e **One Page** (o fechamento da semana em páginas de papel, com "Imprimir / PDF").

- **As estruturas são as do painel**, uma a uma: os filtros laterais de seleção múltipla que se cruzam (com a contagem
  de cada opção), a pesquisa geral por aba, os cartões que filtram, os destaques, o gráfico de pendências × atraso, as
  barras que filtram, as tabelas ordenáveis com "Mostrar mais", o espelho da Gerencial, as notas "Como ler", o mapa
  com zoom e arrasto, a rota com distância e tempo e as páginas do One Page. A lógica de tela é a do `dash_template.html`
  portada para o `static/pcm-acomp.js` (com os mesmos nomes de peça: `passes`, `renderPM`, `renderBKL`...).
- **O desenho é o do Nexus**: os tokens do tema (claro e escuro), os componentes gc-*, os ícones Phosphor, o aviso
  `pcm-aviso` e a fonte `pcm-fonte`; nada de emoji, nada de cor fixa (`static/pcm-acomp.css`; o papel do One Page usa
  os tokens `--papel-*`, iguais nos dois temas). Sem o seletor de tema próprio do painel (o do Nexus manda) e sem o
  html2canvas/jsPDF: o PDF sai do "Imprimir / PDF" do navegador, só com as páginas (`html.pa-imprime-op` + `@page`).
- **O estado vai no endereço** (`?aba=`), como nas outras telas do PCM.

## De onde vem cada número (a regra do Nexus centralizado: o número de uma tela é o da tela dona dele)

O contrato é o do painel (`DATA`, `EXTRA`, `COLAB`, seção 6 do INTEGRACAO.md), montado em `dados.py` com as fontes que
o Nexus já usa. O que mudou em relação ao painel, e por quê:

| Peça | No painel do PCM | Aqui |
|---|---|---|
| OS, tarefas, totais, títulos | 4 consultas SQL ao Fracttal, feitas à mão pelo Claude | o `gestao_pcm.json` (a Gestão PCM): OS em processo = `osStatus` "Em processo", tarefa feita = `estado` "Finalizada"; os agregados são os da consulta do painel (o MAIOR tipo/usina/cluster/responsável, a menor data de manutenção e de criação, o menor título) |
| Programação e "executada" | a Programação Semanal (xlsx); executada = OS + código concluídos no Fracttal na semana | o `banco_dados.json` (as 4 semanas que o Nexus gera e publica); executada = a régua do Fechamento da semana do Nexus (`relatorios.regras.fin`: status Finalizados na linha do plano). O próprio painel avisava que a régua dele divergia do relatório oficial (31% contra 63% na semana 41) |
| Rolagens | o `Historico_Programacoes.xlsx` | o "Nº vezes programada" (`vezes`) das linhas do banco_dados; só entra quem rolou (2 ou mais) |
| Gerencial (aba MPAS) | o xlsx do OneDrive | o `mpas.json` aberto pelo servidor com a `NEXUS_PCM_MPAS_SENHA` (a senha do login de administrador do painel do PCM), na mesma cópia da Gestão PCM (`telas._gerencial`). Sem a senha, o espelho e o atraso ficam de fora e a tela diz por quê |
| Atraso das MPA/MPS | a agenda do Painel MPAs e MPSs (outro projeto) | a Fila da Gestão PCM (`gestao.fila_gerencial`): da Data Prevista até hoje, para a não concluída. Sem a linha da Gerencial (ou sem a planilha: o servidor sem a senha), a regra da Fila sem a planilha (`gestao.fila_fracttal`): da Data Programada mais antiga das tarefas de MPA/MPS da OS no Fracttal (`atraso_fonte` "Fracttal"; numa cadeia, a OS mais atrasada). 15/10/2026, Levi: "A dispersão não está funcionando direito": sem a senha no servidor, nenhuma MPA tinha atraso e os pontos iam para fora da escala; hoje o gráfico só desenha quem tem atraso e diz quantas ficaram fora |
| "Bloqueios para finalização" | a coluna da Gerencial | ainda NÃO vem no mpas.json: vale a classificação da curadoria (`bl`), como o painel fazia quando a coluna estava vazia |
| Curadoria (grupo, prazo, o que falta...) | `scripts/curadoria.json`, no computador de quem mantinha | o livro `nexus_pcm_curadoria · fato_decisao_curadoria`, cifrado (`curadoria.py`); 1ª carga do arquivo de 14/10/2026 por `ferramentas/carregar_curadoria_pcm.py`. A regra do responsável da Manutenção (Norte e Nordeste × o resto) é um item da curadoria (no painel estava no código) |
| Pendências, total, progresso | recalculados do Fracttal e regravados na curadoria | recalculados do `gestao_pcm.json` a cada leitura (nunca gravados); `manual: true` trava, a cadeia de OS soma as OS |
| Coordenadas e mapa | cache + KMZ + Fracttal; latitude e longitude no navegador | o cadastro do Nexus (`performance/clima/usinas.do_app`), ligado ao nome do Fracttal pelo de-para publicado (sistema "Fracttal · Classificação 1") e, sem ele, pelo nome. A coordenada NUNCA sai do servidor (regra do Mapa de risco): o navegador recebe o ponto já projetado (a projeção do `performance/clima/mapa.py`) e a distância já medida (`/t/pcm/acompanhamento/rota`) |
| Equipe por cluster | o `COLAB_DATA` de outro painel | as pessoas ativas do cadastro: só nome, cargo e cluster (LGPD) |
| Supervisor do cluster | o mais frequente na programação; reserva, a Gerencial | o Supervisor de Campo da região da equipe no cadastro; sem ele, o mais frequente na programação; sem ele, a Gerencial |

## As rotas

- `/t/pcm/acompanhamento` (`?aba=mpa|mps|bkl|map|op`): a tela; leve (a pré-carga a abre).
- `/t/pcm/acompanhamento/dados.json`: o contrato + `AVISOS` + `FONTES`, compactado com gzip, guardado 2 minutos e pela
  versão de cada fonte.
- `/t/pcm/acompanhamento/rota?o=&d=`: `{"km", "perto"}` (linha reta e as 6 usinas mais perto da origem). Nada de coordenada.
As três seguem a marca da tela no portão de setor.

## Como provar

- `python -m pytest -q tests/test_pcm_acompanhamento.py` (as contas, a curadoria cifrada no banco de mentira, o mapa sem
  número de coordenada no JSON, as rotas, o setor e o `node --check` do JS).
- A tela, numa cópia de prova (`ferramentas/subir_copia_de_prova.py`) com os JSON reais do PCM (`NEXUS_PCM_GESTAO_FONTE`,
  `NEXUS_PCM_FONTE`), a curadoria num arquivo (`NEXUS_PCM_CURADORIA_ARQUIVO`, só fora do servidor), uma Gerencial
  sintética cifrada (`prova_gestao.gerencial_sintetica`) e o cadastro do PC (armazém e chave do .env, nunca impressos).
  Em 14/10/2026: 42 MPAs e 13 MPSs, 115 OS no Radar, 432 OS em andamento com 2.431 tarefas, 158 usinas no mapa (4 com
  carga e sem coordenada), One Page da semana 41 com 12 páginas e 43% de execução (416 de 963).

## O que falta (dito ao Levi)

- A tela de edição da curadoria (o PCM decide na reunião e muda grupo, prazo, o que falta): hoje ela entra pela carga.
- A coluna "Bloqueios para finalização" no `mpas.json` (o publicador da Gerencial é do PCM).
- O "MPA/MPS atrasadas" e o espelho dependem da `NEXUS_PCM_MPAS_SENHA` no servidor (DEPLOY.md, seção 7h).
