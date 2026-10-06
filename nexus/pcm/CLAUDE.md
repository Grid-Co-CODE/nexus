# CLAUDE.md — PCM (programação semanal)

A programação semanal do PCM dentro do Nexus. O desenho e as etapas estão em
`docs/superpowers/specs/2026-09-30-pcm-no-nexus-design.md`; leia antes de mexer.

**Regra de ouro:** o sistema atual segue no ar e intocado até o Nexus bater número a número com ele. Isso vale para o
gerador no PC do Fabrício, o robô do GitHub, o painel pcm.gridco.com.br e o `banco_dados.json` que o App de Campo lê.
Até a troca, tudo aqui é **sombra**: nada é publicado.

## Os módulos

| Arquivo | O que faz |
|---|---|
| `fonte.py` | lê o `banco_dados.json` do App (a semana que está valendo), com cópia de 5 min |
| `semana.py` | as contas das telas Semana e Tarefas e OS: aderência, horas por equipe, fora da jornada |
| `geracao.py` | roda o motor numa pasta por rodada, num subprocesso, a 1 pedido por segundo ao Fracttal |
| `insumos.py` | os insumos do motor guardados no Nexus, escritos na rodada no formato que o motor lê |
| `comparar.py` | compara a semana do Nexus com a do Fabrício, linha a linha |
| `telas.py` | as telas, penduradas na torre PCM (`registrar_pcm(bp)`) |
| `motor/` | **cópia idêntica** do motor do PCM: **não edite** (veja o `README.md` de lá) |

## Insumos: no Nexus, não em arquivo

Prioridades, Confiabilidade, Histórico, Feriados e Observações (por semana) moram em `insumos.py`. A cada geração, o
Nexus escreve os arquivos na pasta da rodada, com a mesma aba, a mesma linha de cabeçalho e a mesma posição de coluna
do original. A AUXILIAR sai do cadastro do Nexus (`auxiliar.py`, desde 02/10/2026). Da pasta do PCM só vem ainda o
`duracoes_aprendidas.json` (sombra: não muda a agenda).

- **AUXILIAR:** o motor lê seis colunas dela (UFV, RESPONSÁVEL O&M, CIDADE, a 1ª com "MWp", Equipe Cluster, Base
  Equipe). O MWp é a potência contratual. Equipe Cluster fora do padrão "UF Região NN" vai vazia: era uma aba vazia
  por usina com equipe local. Prova da S41 (02/10), com a mesma foto do Fracttal da geração oficial: agenda e pendentes
  idênticos; 48 linhas ganharam Responsável; mudam só as colunas de sombra (RPN novo e Desloc).
- **Provar mudança no motor ou nos insumos:** rode com a FOTO do Fracttal da pasta do PCM (`.cache_semanal_api.pkl`,
  `.cache_hist_api.pkl`, `_ativos_classificacao_cache.json`, `_usinas_coordenadas_cache.json`, TTLs altos, sem
  credencial). Ler o Fracttal horas depois muda a semana (S41: 157 tarefas a mais e 280 horários) e não prova nada.

- **Armazém:** `C:\GridcoAuto\nexus\pcm\insumos.json`, fora do OneDrive, com a versão anterior ao lado. Trocar pela
  API de dados é mexer só em `insumos.py`.
- **Na sombra:** "Importar da pasta do PCM" traz os arquivos do Fabrício antes de gerar, para as duas semanas partirem
  do mesmo dado. A tela avisa quando um arquivo dele mudou depois da importação.
- **Prova obrigatória** a cada mudança no formato: o que o motor lê do arquivo gerado pelo Nexus tem de ser igual ao
  que ele lia do original, com as mesmas leituras do `programacao_v7.py`. `tests/test_pcm_insumos.py` faz isso com
  dado de mentira; com os arquivos reais, rode a mesma comparação fora do repositório.

## A tela Gerar (`templates/pcm/gerar.html` + `_observacoes.html`, estilo em `static/pcm.css`)

Desde 05/10/2026 (Levi: "está confuso, separe por blocos"), em quatro blocos numerados, na ordem do trabalho: **1** o
que o motor precisa (insumos, em duas colunas, e "Importar da pasta do PCM"), **2** observações da semana (dias por
usina, OS fora, OS com dia fixo), **3** gerar em sombra, **4** últimas gerações. A semana se escolhe uma vez, no topo.

- **Dia de atendimento é verde SUAVE.** Tinta verde clara com texto verde = atende; contorno apagado = não atende.
  Até 05/10 o "atende" sem regra era cinza e a lista parecia desligada ("está tudo cinza"); o verde cheio que entrou
  no lugar, com borda e faixa verdes em toda usina, acendeu a lista inteira ("muito estourado, suavize"). Sem borda
  verde no cartão: a lista já é só de usinas marcadas.
- **A lista mostra só as usinas marcadas** (com dia restrito). As outras ficam na página, escondidas, e entram pelo
  "Adicionar usina" com os cinco dias: desmarcar um dia cria a regra `@usina` (Levi, 05/10: "quero que apareça só o
  que está marcado, o que não estiver só vai aparecer por um botão adicionar"). Usina mexida fica à vista até recarregar.
- **O padrão da semana é a última programação** (`insumos.observacoes_efetivas`). Semana sem nada salvo herda, da
  semana salva mais recente antes dela, só os dias por usina; OS fora e OS com dia fixo não passam. Semana salva,
  mesmo vazia, vale o que foi salvo. É herança de DADO: o `materializar` entrega ao motor o mesmo texto que a tela
  mostra, e a tela avisa "herdados da W41". Antes, a semana nova começava vazia e o PCM refazia as 46 restrições.
- O JavaScript do editor depende dos ids e classes (`#obs`, `#obs-form`, `.obs-ufr`, `.obs-dia`, `#obs-por-dia`,
  `.obs-bloco--usinas`...): a legenda usa `.obs-amostra` de propósito, porque um `.obs-dia` fora de uma regra vira
  clique de edição.
- Ver a tela sem login no navegador: renderize no processo (`test_client` + `session_transaction`, logado) e abra o
  HTML ao lado de uma cópia do `static/`. O Nexus em produção não recarrega template: depois de mudar, reinicie.

## Armadilhas já vividas

- **Gerar duas vezes a mesma semana distorcia tudo:** na S40, 415 tarefas viraram reprogramadas, e todas ganharam +1
  no "Nº vezes". Por isso a rodada parte do histórico de **antes** da semana (`geracao.preparar_historico`).
- **Cota do Fracttal:** 200 pedidos por minuto para a **empresa inteira**, divididos com o App de Campo. O motor anda
  a 1 por segundo, e a tela pede confirmação no horário de campo (seg a sex, das 06h às 18h).
- **Dois Fracttal no mesmo processo se quebram:** o `FRACTTAL_BASE_URL` do motor tem `/api/` e o do OS Creator não.
  Por isso o motor roda em subprocesso, com ambiente próprio e sem as variáveis `NEXUS_*`.
