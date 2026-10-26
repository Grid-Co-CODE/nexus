# ETMs na Engenharia: a visão do app de ETM dentro do Nexus (26/10/2026)

## O pedido

Levi, 26/10/2026, com o zip do app de ETM: "Quero que inclua essa visão de ETMs no Nexus, engenharia, aba própria. Deixe
o design alá Nexus!". Respostas do quiz do mesmo dia:
- **Histórico:** "Traz 1 vez, para as OSs em aberto bota esses comentários na nota da OS."
- **Entrega:** por partes.
- **Comentário:** vai também para a nota da OS no Fracttal, como no Quadro da equipe.

## O que é o app de ETM

App desktop da Engenharia (FastAPI + HTML/JS, empacotado num .exe, porta 8123) que acompanha as OS das Estações
Meteorológicas (ETM) por cima do Fracttal. Quatro telas: **Planner** (quadro Não iniciadas, Em andamento, Finalizadas e,
por filtro, Canceladas; filtros de cliente, usina, criado por, solicitante, responsável, tipo de trabalho Análise de
Engenharia / Campo, período e canceladas), **Histórico** (cliente → usina → OS, com o "chat da usina"), **Estações em
Aberto** (usinas com OS aberta para a engenharia e as "em acompanhamento"; "Finalizar pela Engenharia" em lote) e
**Fechamentos** (por semana, pelo Fracttal ou pela Engenharia). O detalhe da OS traz o checklist (subtarefas com as
respostas), os comentários e cinco marcações da equipe: **diagnóstico** (Falha de Equipamento, Falha de Comunicação,
Sujidade, Outro), **status pós-OS** (Chamado de Garantia, Alinhamento com o Cliente, Regularizado), **etiquetas** (OS em
campo, Stand By, Validação Final; várias), **Em acompanhamento** e **Finalizado pela Engenharia** (liga/desliga). Os
comentários e as marcações moram como Issues e labels num repositório privado do GitHub; o autor é um nome digitado.

Segurança: o Nexus não usa nenhuma credencial do app de ETM. Lê o Fracttal com a dele e o GitHub com o token do .env.

## Decisões

- **A aba:** tela nova `etm` ("ETMs") na torre Engenharia, no desenho do Nexus (tokens, tema escuro e claro, sem emoji,
  endereços pela raiz). O quadro segue o do Quadro da equipe (`kb-*`); a OS abre na página da OS da Engenharia
  (`os_quadro.html`), com o painel da ETM no lugar do status e da prioridade.
- **A leitura (medida em 26/10/2026, só leitura):** `items?field_1=Estação Meteorológica` dá as 172 ETMs (2 páginas) e
  `work_orders?items_log_description=Estação Meteorológica` dá as 1213 OS delas (13 páginas, todas de ETM). São 15
  pedidos por leitura, contra os 172 do app (um por ETM). Fica a OS cujo código está entre os das ETMs; a cópia vale 5 min
  e é relida por trás enquanto a tela é usada (o mesmo do `os_equipe`), no ritmo do leitor do Nexus (o limite do Fracttal
  é por empresa).
- **Quais OS entram (a regra do app, sem nome no código):** Corretivas e Administrativas de ETM, mais as de ETM com
  responsável ou solicitante da Engenharia ou de Chamados. O solicitante do Fracttal é texto livre: casa sem acento nem
  caixa pelo nome do Fracttal das pessoas dos setores.
- **Engenharia, Chamados e Campo** (Levi, 26/10/2026, depois da 1ª entrega: "Engenharia e Chamados vai pelas pessoas dos
  setores, Campo é o restante!"): o setor do responsável pelo id do Fracttal, em Base → Acessos → Pessoas e setores
  (`nexus_setores`); quem não é de nenhum dos dois é Campo. No lugar do "Análise de Engenharia × Campo" do app.
- **A coluna:** a da OS (`id_status_work_order` 3 Finalizada, 4 Cancelada); aberta, "Não iniciada" quando nenhuma tarefa
  começou, senão "Em andamento". A OS de várias tarefas é uma só (agrupada pelo nº).
- **Onde mora o que a equipe marca:** livro novo `nexus_engenharia_etm`, registrado no catálogo antes da 1ª gravação:
  `fato_classificacao_etm` (1 linha = 1 marcação numa OS: `diagnostico`, `status_pos`, `etiqueta`, `acompanhamento` ou
  `finalizado`; só acrescenta, o estado é o do último evento) e as três dim das listas fixas
  (`dim_diagnostico_etm`, `dim_status_pos_etm`, `dim_etiqueta_etm`). Quem fez vai cifrado e pelo `pessoa_hmac`, a OS pelo
  id e pelo nº, o ativo pelo `equipamento_id`, a usina pelo `usina_id` (como o `nexus_engenharia_os`).
- **Os comentários** são os da Engenharia na OS: o livro `nexus_engenharia_os` (evento `comentario`) e a nota da OS no
  Fracttal pela ponte do OS Creator, na sessão do Fracttal da pessoa, com as mesmas regras do Quadro da equipe (OS
  concluída, cancelada ou de várias tarefas fica só no Nexus). O autor é quem está logado no Nexus.
- **O histórico do app (uma vez):** um painel só do administrador na tela ETMs lê o repositório do app (token e
  repositório no `.env`, `NEXUS_ETM_GITHUB_TOKEN` e `NEXUS_ETM_GITHUB_REPO`, nunca no código: o nome do repositório
  traz o nome de uma pessoa) e mostra a prévia (N comentários em M OS; K abertas recebem a nota). Ao gravar: os
  comentários entram no `nexus_engenharia_os` com o autor e a data originais (dentro da cifra; o `data_id` é o dia
  original) e as marcações atuais no `nexus_engenharia_etm`; nas OS abertas, os comentários vão para a nota da OS, os de
  cada OS numa escrita só, do mais antigo ao mais novo, na sessão do Fracttal de quem importa. Importar de novo não
  duplica (a chave é o id do comentário no GitHub).

## Por partes

1. **Agora:** a tela ETMs com o Planner (as quatro colunas, os filtros do app e os contadores), o detalhe da OS (a página
   da OS da Engenharia com o painel da ETM, o checklist e os comentários), o livro, o catálogo e o painel do histórico.
2. **Depois (26/10/2026, Levi: "sinto falta daquelas outras seções também. A de histórico, e a de ETMs em aberto"):**
   as abas Histórico (cliente → usina → OS e o chat da usina) e Estações em Aberto (com o "Finalizar pela Engenharia" em
   lote), com o nome curto da usina, o filtro que vale no clique e sem o filtro do solicitante. Ficam os Fechamentos
   (por semana, pelo Fracttal e pela Engenharia).

## Provas

Testes com o Fracttal, o banco e o GitHub falsos (nada vai à rede): a regra de quais OS entram e a coluna, o livro e o
estado das marcações, o comentário na nota, a importação (prévia, gravação, sem duplicar, nota só nas abertas), o
catálogo, o tema e o prefixo. A tela conferida na cópia de prova (desktop e 375 px, escuro e claro).

## Fica para quem constrói

Os nomes das funções e dos módulos, o desenho fino do cartão (no padrão `kb-card`) e dos filtros, e a ordem das tarefas.
