# CLAUDE.md — camada de dados (governança: PRIORIDADE 0)

Levi, 05/10/2026: **"prioridade 0 para a governança e controle de dados"**; "precisamos construir e manter uma base
sólida para futuras análises correlacionadas" — e vão entrar dados de chamados, engenharia, mais PCM, segurança, mais
inversores. Esta pasta é o lugar onde esses dados viram uma base só, ligada por ID, no método **Kimball**:

- **Fato** = um acontecimento por linha (um fechamento, uma ronda, um chamado, a geração de um dia). Tem as medidas
  (nota, kWh, minutos) e os IDs de quando, onde, quem e em quê.
- **Dimensão** = o cadastro de referência, com ID numérico. **Uma só por assunto** (conformada): a mesma usina para todos
  os setores. É ela que deixa cruzar Campo × Performance × PCM × Chamados sem conversão.
- **Grão** = o que exatamente é UMA linha do fato. Sem ele escrito, dois relatórios contam coisas diferentes.

**Leia esta página antes de mexer em qualquer dado que vá para o banco.** Fonte nova segue o passo a passo abaixo.

## O que existe (05/10/2026)

| Peça | Onde | O que é |
|---|---|---|
| Catálogo (a matriz de barramento) | `catalogo.py` | os 15 fatos e as 7 dimensões, o grão e como cada fato liga a cada dimensão. **Fonte única**: a tela, os testes e esta página leem dele |
| Calendário | `calendario.py` → `nexus_dimensoes · dim_data` | 1 linha por dia, 2025 a 2027: `data_id` (AAAAMMDD), semana ISO, mês, trimestre, fim de semana, feriado nacional, dia útil |
| Feriados locais | → `nexus_dimensoes · feriados_locais` | estaduais e municipais (UF, município), cruzam com a usina pela cidade |
| Histórico (SCD tipo 2) | `historico.py` → `pessoas_historico`, `usinas_historico` | válido de / até de equipe, supervisor, cargo e status da pessoa; de cliente, equipe, responsáveis e região da usina |
| Checklist da ronda sem OS (carga única) | `fatos.py` → `nexus_rondas_checklist · fato_checklist_ronda` | 1 linha = 1 ronda do App que ficou sem OS, com sujidade, vegetação, vala e sensores; liga ao `rondas_app_campo` por `usina_id` + `inicio`. **Não é rotina** (ver abaixo) |
| 1º fato com IDs | `fatos.py` → `nexus_fatos · fato_fechamento` | o fechamento de OS do App, com `data_id`, `usina_id`, `equipe_id`, `pessoa_id` |
| Qualidade da ligação | → `nexus_fatos · qualidade` | por fato: quanto ligou a cada dimensão e exemplos do que faltou |
| Carga | `carga.py` (+ `ferramentas/carregar_dados.py`) | de hora em hora, aos :40, grava os dois livros e confere aba a aba |
| Tela | `telas.py`, Base → **Governança de dados** | a matriz viva e as barras de qualidade |

1ª carga real (05/10, 15:37, 12,6 s): 2.512 fechamentos — data 100%, usina 99,7% (2.486 pelo de-para do Fracttal, 18 pelo
código do ativo), equipe 98%, pessoa 95%. O que não ligou: "Nobreak 1", "SPDA", "Inversor 1.1 Huawei" (o App gravou o
equipamento no lugar da usina), "Grid Co." e Solier Cascavel (sem de-para); equipe "MT Sul 02" (não está no cadastro) e
19 sem região. Feriados: os 12 nacionais de 2026 do PCM batem dia a dia com a lista calculada pela Páscoa.

**O Nexus como fonte (05/10/2026):** a decisão da PT assinada no Nexus (`nexus/campo/decisao_pt.py`) grava
`nexus_pt_decisoes · decisoes` (grão: 1 linha = 1 decisão). Já nasce com `data_id`, `usina_id` e a pessoa como HMAC;
o motivo vai mascarado (e-mail e número viram marcador), porque o técnico lê e a API é de leitura aberta.

**Carga única do checklist das rondas sem OS (06/10/2026).** Levi: "Atualize o banco de dados com essas rondas passadas
sem OS, mas não será rotina". A ronda sem OS não tem o texto da OS no Fracttal, de onde o Nexus lê sujidade e vegetação;
as respostas só existiam no registro da ronda no App. Foram exportadas UMA vez da tabela de rondas do App (pela conta do
Levi, com o `az`; o Nexus não lê o Azure) e gravadas por `ferramentas/carregar_checklist_rondas_sem_os.py`, num livro
próprio (o `nexus_fatos` é regravado inteiro a cada hora e apagaria a aba). Medido e gravado em 06/10: 125 rondas sem OS
de 11/08 a 06/10, 125 casaram 1 para 1 por dia + início; data, usina e equipe 100%, pessoa 90% (as 12 do Frank Melo: o
e-mail dele não está no cadastro); 0 diferença de sujidade/vegetação contra o App, nenhum e-mail no livro. Ronda sem OS
depois de 06/10 não entra aqui.

## As regras (valem para todo dado novo)

1. **Grão escrito antes de tudo** ("1 linha = …"). Fonte larga (um inversor por coluna, como o BD_Thopen) vira linhas
   (usina × inversor × dia) antes de entrar.
2. **Dimensão é uma só.** Mestres: `cadastro_nexus` (usina, cliente, equipe, pessoa, e o `de_para` com o que cada
   sistema chama de cada usina) e `nexus_dimensoes` (data e os históricos). Cópia de cadastro em outro livro (o "Dados
   Gerais Usinas" do BD_Thopen, a usina do gêmeo, a aba de usinas dos tickets) não é fonte: aponta para o ID.
3. **O fato guarda IDs, medidas e chaves de negócio.** IDs: `data_id`, `usina_id`, `equipe_id`, `pessoa_id` (e
   `equipamento_id` quando existir). Medidas numéricas com a unidade no nome (`_min`, `_kwh`, `_pct`). Indicador sim/não
   como 1/0 (soma e média). Número da OS fica no fato (dimensão degenerada).
4. **Não liga = vazio. Nunca chutar ID.** Código que é de duas usinas não liga (IPX100 é da 2C e da Thopen: `2C-IPX100` e `THPN-IPX100`). A lacuna
   aparece na qualidade e se conserta **no cadastro** (de-para, equipe que falta), nunca no fato.
5. **Linhagem:** o fato diz por onde ligou (`usina_ligada_por`). A qualidade diz quantos por cada caminho.
6. **Histórico:** atributo que muda e muda a análise (equipe/supervisor da pessoa, responsável da usina) vai no
   `*_historico`. Para atribuir ao supervisor "da época": a linha da pessoa com `valido_de <= dia < valido_ate`.
7. **Data:** sempre o dia de Brasília (o App grava em UTC). Fato com mais de uma data usa "papéis":
   `data_id_abertura`, `data_id_fim`.
8. **Segurança:** a API do banco tem LEITURA ABERTA. No fato: nada de nome, e-mail, telefone nem texto livre (a
   observação escrita no App ficou fora por isso). Pessoa só como `pessoa_id`; vinda de fora, como HMAC do e-mail
   (`NEXUS_PESSOA_HMAC`). Sensível do cadastro, só cifrado (`sensivel_cifrado`).
9. **Conferir depois de gravar:** `livros.publicar` relê cada aba e compara a contagem; diferença é erro.
10. **Livro no banco é para sempre** (a API não apaga): nome `nexus_<assunto>`, abas `fato_<processo>`,
    `dim_<assunto>`, `<dimensão>_historico`, `qualidade`, `atualizacao`. Registre no catálogo antes de criar.
11. **Uma carga por hora, uma máquina por vez:** grava só se a última tiver mais de 50 min. PC e servidor podem estar no
    ar juntos sem gravar em dobro. `NEXUS_CARGA_DADOS=0` desliga numa máquina.

## Como entra um dado novo (o passo a passo do Claude)

1. **Entender o processo:** o que acontece, quem é o dono (a torre), de onde vem (App, Fracttal, planilha, API de
   fornecedor), com que frequência, quantas linhas por dia.
2. **Declarar o grão.** Uma linha = um quê? Se a fonte mistura grãos (o mesmo livro com ticket e com OS), são dois fatos.
3. **Mapear cada dimensão** (data, usina, cliente, equipe, pessoa, equipamento, OS): o que a fonte traz, a chave de cada
   uma (código, nome, ID de outro sistema) e por onde vai ligar. Sistema novo chamando usina de outro jeito = entra no
   `de_para` do cadastro (tela Base → Ligações), não num mapa escondido no código.
4. **Registrar no `catalogo.py`** (`Fato`, estado `origem`) com o livro, o grão e cada ligação. A tela já passa a
   mostrar a lacuna.
5. **Pessoa?** Confirmar que nada pessoal vai em claro (regra 8).
6. **Construir o fato conformado** em `fatos.py` (`fato_<processo>`, `CAB_<PROCESSO>`), com a linha de qualidade, e
   ligar em `carga.montar`.
7. **Testes** (`tests/test_dados_camada.py` como modelo): a ligação (inclusive o "não chuta"), o grão, a qualidade e a
   carga com o `tests/pg_falso.py`.
8. **Medir com o dado real ANTES de gravar:** `python ferramentas/carregar_dados.py --ensaio`. Abaixo de 98% em data ou
   usina: achar o porquê e consertar no cadastro antes de seguir.
9. **Gravar e conferir:** `python ferramentas/carregar_dados.py --forcar`; a tela mostra as barras.
10. **Atualizar** o catálogo (estado `conformado`, `conformado_em`) e esta página (o que existe, a 1ª medida).

### O que olhar em cada frente que vem

- **Chamados** (tickets de performance, solicitações do Fracttal): 1 linha = 1 chamado. Duas datas (abertura e fim:
  `data_id_abertura`, `data_id_fim`). Usina pelo "Código da usina" (o de-para "Tickets · Base de dados - Usinas" já
  existe). Supervisor e responsável vêm em NOME: ligar ao `pessoa_id` pelo nome do cadastro, só nome que é de UMA pessoa.
  Equipamento em texto: depende da dimensão de equipamento. Medidas: horas de indisponibilidade, kWh de impacto.
- **Engenharia** (garantias, laudos, projetos): o centro é o EQUIPAMENTO. Criar antes a dimensão de equipamento
  (pendência 1).
- **Mais PCM**: a programação semanal hoje está fora do banco. Fato `programacao` (tarefa × semana; a semana é o
  `data_id` da segunda-feira), usina pela Classificação 1 do Fracttal (de-para já existe), equipe pela "Equipe Cluster",
  técnico do Fracttal ligado à pessoa (acrescentar o ID de pessoa do Fracttal como sistema no cadastro), OS e código do
  equipamento. Backlog e execução são outros fatos (outro grão).
- **Segurança** (PT, APR, incidentes, EPI): a PT já chega do App (`pt_app_campo`, pessoa por HMAC): conformar como os
  fechamentos. Incidente: 1 linha = 1 ocorrência; pessoas envolvidas só por ID; tipo e gravidade como lista pequena.
- **Mais inversores e fontes de equipamento:** cada fonte registra o código que ela usa para cada equipamento como
  apelido (o modelo do `gemeo_digital · alias`: usina, equipamento, sistema, valor). Série de 5 min ou de hora fica na
  fonte ou no gêmeo; no banco do Nexus entra o agregado diário (inversor × dia), com `equipamento_id`.

## Pendências, em ordem

1. **Dimensão de equipamento** a partir do `gemeo_digital · equipamento` (9.918) + `alias` (917) + `de_para_trackers`
   (4.745), com `equipamento_id` ligado à usina. Destrava chamados, engenharia e perdas por equipamento.
2. **Conformar o resto do App:** ronda, PT, decisões, zeladoria (mesmos livros, mesmo `Ligador`).
3. **Usina única:** o gêmeo e o BD_Thopen apontando para o `usina_id`.
4. **Programação do PCM no banco.**
5. **Geração em linhas** (BD_Thopen e BD_Performance: usina × inversor × dia).
6. **Lacunas medidas em 05/10:** equipe "MT Sul 02" no cadastro; Solier Cascavel e "Grid Co." no de-para.

## Como provar

- `python -m pytest -q tests/test_dados_camada.py` (catálogo, calendário, histórico, ligação, carga que grava e confere,
  "não grava em dobro", gravação que perde linha vira erro, a tela).
- `python ferramentas/carregar_dados.py --ensaio` mede com o dado real sem gravar.
- Base → Governança de dados: as barras da última carga e a hora dela.
