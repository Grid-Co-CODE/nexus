# Desempenho do Nexus: o roteiro do chat de desempenho

Levi, 20/10/2026: "O que você acha de um chat só para essas otimizações de performance da plataforma? Acho que com a
construção constante do nexus sempre vai ter algo para revisar e corrigir!". Este arquivo é o ponto de partida desse
chat: como investigar, as regras de prova, o que já foi corrigido (para não refazer) e a fila. Correção feita: a linha
da fila sai e entra uma linha em "O que já foi feito", no mesmo commit.

## Como começa cada pedido

- **O print do Raio-X** (`/t/base/raio-x`, só administrador) NA HORA da lentidão, a tela ou a ação e a hora. Sem o
  print, pedir: em 20/10 ele mostrou que dois casos que pareciam "conta fria" eram outra coisa.
- **Houve deploy nos 5 min antes?** `curl https://app.gridco.com.br/saude` dá o commit no ar e `git log origin/main` a
  hora. Todo push na main reinicia o servidor em 1 a 5 min, e a pré-carga só passa 5 min depois: nesse intervalo, a 1ª
  abertura de cada tela é fria (até ~15 s nas pesadas).

## Como ler o Raio-X

| O que aparece | Quer dizer | Onde olhar primeiro |
|---|---|---|
| Pedido parado numa linha `with <trava>` | trava no caminho de todo pedido | quem mais pega a trava e o que faz dentro dela (disco? rede?). Caso de 20/10: o portão esperava a trava presa no `fsync` de cada login |
| "esperando a rede" no Fracttal (`api.*`) | o Fracttal lento, ou a tela pedindo demais | dá para servir a cópia guardada e reler por trás? o mesmo pedido repetido por pessoa ou por visita? |
| "esperando a rede" no banco (`livros.*`, `banco_campo`) | o banco (a API `db_performace` mora na MESMA máquina) | contas frias juntas, renovações por trás demais, `VAGAS_BANCO` |
| "trabalhando" e o Processador do Nexus perto de 100% | o processo segura o GIL: um laço Python | a tarefa "trabalhando" (pré-carga, PDF, renovar) e o laço dela |
| "trabalhando" com o Nexus baixo e, no Raio-X, esperando o disco alto, swap trocando ou memória parada | a MÁQUINA (disco, memória), não o código | o que lê ou grava disco ou ocupa memória; sendo a máquina mesmo, os números vão ao Levi para a T.I. |
| Lento só nos ~5 min depois de um push | conta fria pós-deploy | a fila, item "Conta fria pós-deploy" |

O Raio-X e o que cada número quer dizer: `nexus/casca/CLAUDE.md`, seção "Nexus lento".

## Regras de prova de toda correção

1. Achar ONDE o pedido espera antes de mexer (o Raio-X, a pilha, uma medida). Nada de corrigir por palpite.
2. Um teste que reproduz: falha no código de antes e passa no novo. O Fracttal, o banco e o disco são de mentira; o
   `conftest.py` recusa a rede e as fontes pagas.
3. Mutação: desfazer cada parte da correção derruba o teste dela.
4. Medir antes e depois e dizer o número (num processo novo, com o mesmo dado). Mudou a leitura de um dado: comparar
   valor a valor (confiabilidade de dado é a prioridade 1).
5. Suíte inteira (`python -m pytest -q`) antes do push. No OS Creator: `python ferramentas/sincronizar_oscreator.py
   --aplicar` só quando o "vai para o oem" lista só os seus arquivos, e a suíte do oem na pasta dele (`cd
   C:\GridcoBuild\oem` e `python -m pytest -rN tests`).
6. Push é deploy: conferir o `/saude` com o commit. Juntar as correções do dia num push quando der (cada push esfria o
   servidor).
7. O `.md` da área tocada é atualizado no mesmo commit, e este arquivo também.

## Convivência com as outras frentes

- Este chat mexe no código das outras frentes só para deixar mais rápido, SEM mudar o que a tela faz ou mostra. Se a
  correção muda comportamento (o que aparece, quando atualiza), avisar o Levi antes.
- Mudança visual: mostrar ao Levi (print) antes de subir.
- Commit só dos próprios arquivos, num worktree do `origin/main` atualizado, com rebase antes do push.
- A cota do Fracttal é de 200 pedidos por minuto para a EMPRESA (o App de Campo vive dela): cópia guardada e releitura
  por trás, nunca pedido a mais.

## O que já foi feito (não refazer; o porquê está no commit)

| Data | Sintoma | Causa | Correção | Commit |
|---|---|---|---|---|
| 12/10 | telas lentas no 1º clique | as cópias do servidor vazias | pré-carga das telas de quem tem setor | `8188864` |
| 13/10 | travamentos sem rastro | nada registrava o pedido preso | registro dos pedidos presos | `905347d` |
| 14/10 | `/saude` até 60 s | o OS Creator esperando o Fracttal segurava as threads | Raio-X; teto de 16 threads para o OS Creator, servidor com 32 | `cbed995`, `948af6d` |
| 14/10 | "clico no OS Creator e fica carregando" | a tela inicial esperava o selo da Performance no Fracttal | a tela sai sem esperar; contagens 6 h na memória | `bb91eb0` |
| 14/10 | PDF dos extintores pesado | cada foto inteira | cópia de 600 px de cada foto, feita uma vez | `d8f8d85` |
| 19/10 | Visão do responsável fria de 26 a 46 s | 23 a 27 listagens e abas página por página | pré-leitura numa listagem só, páginas em paralelo | `43b5a93` |
| 19/10 | o filtro da Visão relia o banco | ocorrências e sites relidos a cada filtro | o filtro não espera o banco | `695b487` |
| 19/10 | Nexus travado das 14:47 às 15:06 | gravações zeravam TODO o Campo; contas frias em dobro | só o que mudou sai; uma conta fria por chave; teto de 6 leituras do banco | `c77da9b` |
| 19/10 | Extintores pesado | todas as fotos de uma vez | página leve, foto só no clique | `bfab36f` |
| 19/10 | Histórico do OS Creator, 2.000 OS por pessoa, 43 s | a lista repetida por pessoa e a cada 10 min | lista dividida, soma só as novas, linhas montadas uma vez; catálogos 10 min; catálogo de ativos na memória | `e5e3e02` |
| 19/10 | Gerar a semana, Quadro e Registro mestre lentos | a conta refeita a cada visita | serviço e índices reaproveitados, linhas montadas uma vez por versão | `e52cde5` |
| 19/10 | Acompanhamento relido por pessoa; anexos pelo id errado | cópia por pessoa; o id do modelo da tarefa | quadro dividido por quem vê o mesmo; id da tarefa da OS | `6bab274` |
| 20/10 | Visão do responsável "um parto" (08:56) | o portão esperava a trava presa no `fsync` de cada login | leitura sem trava, trava por arquivo | `1889303` |
| 20/10 | tela de um chamado em 39 s (09:56) | relia a lista inteira na frente de quem abriu | cópia vencida e releitura por trás, sem reler as fechadas | `c70d778` |
| 20/10 | `GET /os/` em 18 s (10:08) com o Nexus a 13% | a máquina engasgada, sem número para provar | o Raio-X mostra memória, swap e espera do disco | `65c25e7` |
| 20/10 | PDF da OS ~2 min (09:56), em `gerar` | o reportlab decodificava cada foto em RGB só para dar nome a ela (2,25 MB por foto até o fim: +1 GB com 200) | o JPEG do `reduzir` entra como veio; 200 fotos no PC: `gerar` de 3,2 a 4,0 s para 0,3 s, rota de +1.068 MB para +128 MB, o mesmo PDF | `23c3c73` |
| 20/10 | o 2º PDF da mesma OS reduzia todas as fotos de novo | o `reduzir` (~90 ms de CPU por foto no PC) a cada PDF | a cópia de 1000 px guardada pelo hash da foto original (o caminho no S3 pode voltar com outra foto); 200 fotos no PC: o 2º PDF de 5,1 a 5,5 s para 0,8 s | `8ec1999` |
| 20/10 | volta da tela de um chamado ao Acompanhamento "travada" | quadro de 3 min, e cada gravação da tela (ticket, finalizar, responsável) apagava o quadro: a volta relia a lista e os tickets do Fracttal | quadro de 30 min (Levi: "só pesquisar caso a singrid clique em atualizar"), a gravação ajusta a cópia, o teto da memória a tira por último | `d59aef1` (chat de chamados) |
| 20/10 | 3 testes do oem falhando desde 14/10; com a sessão do Fracttal caída, a tela inicial do OS Creator não voltava ao login | `bb91eb0` tirou o selo de dentro da tela (ela não espera o Fracttal) e o 401 do `/os/api/selo` era ignorado | o script do selo leva ao login com o 401 (como o `acomp.js`), conferido no navegador; os 3 testes do oem cobram o selo pelo `/os/api/selo` (no disco do oem, sem commit lá: decisão do Levi) | este |

## A fila

1. **Push só de documentação também reinicia o servidor** (`deploy/atualizar.sh`): pular o restart quando o commit novo
   só muda `.md`, para um documento não esfriar as telas de todo mundo. Mexe no deploy do servidor: prova com cuidado.
2. **Ler o Raio-X novo numa lentidão:** máquina trocando swap ou esperando o disco = memória ou disco do servidor (o
   notebook, 4 núcleos, com o banco na mesma máquina). Levar os números ao Levi. O PDF da OS de 09:56 segurava +1 GB
   (200 fotos) e às 10:08 a máquina engasgou: depois do deploy, um PDF grande com o Raio-X aberto confirma se era isso.
3. **Clima e risco:** 21 s de processador na 1ª carga (o LZW do GeoTIFF do INPE em Python puro, 183 pedidos; volta a cada
   6 h, a cada deploy e a cada 15 min com o INPE atrasado). Proposta: o decodificador do Pillow (em C) por tile e uma
   cópia em disco.
4. **Conta fria pós-deploy** (~15 s na 1ª abertura de uma tela nos ~5 min depois de cada push). Opções: agrupar os
   deploys (no máximo um reinício a cada 30 min, por exemplo) ou uma cópia em disco das abas lidas (servir a última com
   a hora dela e renovar por trás). É parâmetro: perguntar ao Levi antes.

## Onde está cada peça

- Raio-X `nexus/casca/raio_x.py` e `nexus/templates/raio_x.html`; pedidos presos `nexus/casca/presos.py`; teto do OS
  Creator `nexus/casca/teto_os.py`. Regras em `nexus/casca/CLAUDE.md`.
- Contas do Campo: `nexus/campo/visao.py` (`_ler`: a cópia de 5 min sai na hora e se refaz por trás; `_fria`: uma conta
  fria por chave; `VAGAS_BANCO`; `manter_quente`; `carregar`: a pré-leitura).
- Pré-carga `nexus/auth/pre_carga.py`; portão e acessos `nexus/auth/__init__.py` e `nexus/auth/acessos.py`.
- OS Creator: `nexus/torres/oscreator/os_creator/` (`api.py` fala com o Fracttal; `os_web/rotas.py` e o `_memo`;
  `historico_store.py`; `rotas_acomp.py`). Regras no `nexus/torres/oscreator/README.md`.
- Medir uma tela fria: num processo novo, `create_app` com o `.env` do Nexus vivo e uma senha de administrador
  descartável, contando o `requests.Session.request` e recusando o Fracttal (só leitura no banco).
