# Kimball, passos 2 a 6 — desenho (08/10/2026)

Camada de dados do Nexus (`nexus/dados/`). Leia antes `nexus/dados/CLAUDE.md` (as 11 regras) e `catalogo.py`.
Origem: a auditoria Kimball de 08/10 (ronda em 3 fatos com domínios diferentes, PT com grão errado, histórico que só
acha versão para 1 de cada 4 fatos, nenhum fato com tipo nem medidas, sem dimensão de equipamento, PCM fora do banco,
geração em formato largo).

**Escopo.** Passo 3 (fato de ronda único e PT conformada), passo 5 (histórico SCD2), passo 6 (equipamento,
programação do PCM e geração em linhas) e o tipo/medidas de todo fato no catálogo. **Fora, por ordem do Levi
(08/10):** passo 0 (carga incremental que nunca encolhe o fato) e passo 1 (um dono só do cadastro, desligar a carga
do PC, reler o cadastro, recusar carga encolhida). Nada aqui implementa 0 ou 1; cada fato diz o que herda deles.

**Nada grava no banco a partir deste desenho.** O servidor da T.I. roda a carga de hora em hora com troca integral;
o dado novo entra quando o código for ao servidor (decisão do Levi). Construtor mede com `--ensaio`.

Todas as medidas são de 08/10/2026, por GET de leitura na API (`/api/sheets`, `/api/sheets/{id}/rows`), nos arquivos
locais já lidos e no `banco_dados.json` público do PCM. Nenhuma leitura do Fracttal.

---

## 1. Onde mora cada coisa (regra 10)

| Livro · aba | Novo? | Linhas hoje | xlsx | Cadência | Por quê aqui |
|---|---|---|---|---|---|
| `nexus_fatos · fato_ronda` | aba nova | 867 (+~15/dia) | < 0,1 MB | de hora em hora (:40) | mesma origem e cadência do fechamento |
| `nexus_fatos · fato_pt` | aba nova | 226 | < 0,1 MB | de hora em hora (:40) | idem |
| `nexus_dimensoes · pessoas_historico`, `usinas_historico` | colunas novas | 135 / 258 | — | de hora em hora | já existem |
| `nexus_dimensoes · qualidade_historico` | aba nova | 2 | — | de hora em hora | saúde do SCD2 |
| `nexus_ativos_fracttal · foto_ativos` | **livro novo** | 22.357 | ~1,3 MB | **carga única** (Levi grava) | foto do Fracttal que só existe em arquivo local; não pode ir num livro trocado a cada hora |
| `nexus_equipamentos · dim_equipamento`, `equipamento_apelido` | **livro novo** | 22.362 + ~5.800 | ~1 MB | a cada hora, **grava só quando muda** | 15× o tamanho do `nexus_dimensoes`, muda por semana |
| `nexus_programacao · fato_programacao` | **livro novo** | 5.876 (4 semanas) | ~0,4 MB | a cada hora, grava se o `geradoEm` mudou | ~76 mil linhas/ano: tomaria o `nexus_fatos` em meses |
| `nexus_geracao · fato_geracao_usina_dia` | **livro novo** | 45.745 | 1,7 MB | **diária** (depois da coleta noturna) | volume e cadência próprios |
| `fato_geracao_inversor_dia` | depende do passo 0 | ~704 mil | ~44 MB | diária | não cabe em troca integral (seção 7) |

Todo livro novo entra no `catalogo.py` **antes** de existir no banco e leva `qualidade` e `atualizacao`.

---

## 2. Catálogo: tipo e medidas em todo fato

O `Fato` ganha cinco campos (os testes passam a exigir os quatro primeiros em todo fato não aposentado):

```python
TIPOS_FATO = ("transacao", "snapshot_periodico", "snapshot_acumulado", "sem_medida")
SOMA = ("aditiva", "semi", "nao")      # semi: soma no tempo de uma usina, não entre usinas (ou o contrário)

@dataclass(frozen=True)
class Medida:
    coluna: str     # com a unidade no nome: _min _kwh _kwh_m2 _mm _pct _qtd _pts _nivel; indicador sem sufixo, só 1/0
    unidade: str    # "min", "kWh", "kWh/m²", "%", "qtd", "pts", "nível 1-5", "1/0"
    soma: str       # aditiva | semi | nao

Fato(..., tipo: str, medidas: tuple[Medida, ...], chave: tuple[str, ...], fontes: tuple[str, ...] = (),
     janela_origem: str = "")   # "90 dias (App)", "4 semanas (PCM)", "" = a fonte guarda tudo
```

| Fato (id) | Tipo | Chave do fato | Medidas (soma) | Janela da origem |
|---|---|---|---|---|
| fechamento | **foto acumulada** (revisão de 08/10: a revisão muda a linha) | `fechamento_id` | nota_pts (nao); fotos_qtd, fotos_com_descricao_qtd, pecas_qtd, xp_pts, previsto_min, execucao_min, vezes_reprogramada_qtd (aditiva); 8 indicadores 1/0 | 90 dias |
| **ronda** (une ronda, ronda_checklist, ronda_avulsa) | **foto acumulada** (revisão de 08/10: a situação da OS anda) | `ronda_id` | seção 3.1 | 90 dias (App) |
| pt | snapshot acumulado | `pt_linha_id` | espera_min, respostas_nao_qtd, atividades_qtd (aditiva); parada, decidida, primeira_linha_da_pt (1/0) | 90 dias |
| decisao_pt (Nexus) | sem medida | `decidida_em` + `pt` | — | o Nexus é a fonte |
| decisao (painel) | transação | (falta: mistura 3 eventos, GR-3) | — | 90 dias |
| zeladoria | transação | (a definir quando houver linha) | fotos_qtd, respostas_nao_qtd | 90 dias |
| fechamento_coletor | transação (aposentado) | — | — | — |
| **geracao_usina_dia** (substitui geracao_thopen e geracao_demais) | snapshot periódico (dia) | `geracao_usina_id` | energia_medidor_kwh, energia_inversores_kwh (aditiva); ipoa_kwh_m2, ghi_kwh_m2, chuva_mm (semi); disponibilidade_pct (nao); validado (1/0) | a fonte guarda tudo |
| **geracao_inversor_dia** | snapshot periódico (dia) | `geracao_id` | energia_kwh (aditiva); kwh_fora_da_faixa (1/0) | a fonte guarda tudo |
| meta_mensal | snapshot periódico (mês) | usina × mês | meta_kwh (aditiva); pr_pct (nao); ipoa_meta_kwh_m2 (semi) | — |
| falha_string | **dividir em dois** (GR-2): episódio = snapshot acumulado; inversor × dia = snapshot periódico | — | perda_kwh (aditiva) | — |
| falha_tracker | snapshot acumulado | episódio | perda_kwh (aditiva), duracao_min (aditiva) | — |
| parada_tracker | transação | parada | duracao_min (aditiva) | — |
| perda_equipamento | snapshot periódico (dia) | usina × dia × equipamento × parcela | perda_kwh (aditiva) | — |
| ticket | snapshot acumulado | (falta ID em 57 de 774) | indisponibilidade_min, impacto_kwh | — |
| **programacao** | snapshot periódico (semana) | `programacao_id` | seção 6 | **4 semanas** |

- `fato_fechamento` tem 6 medidas sem unidade no nome (`nota`, `fotos`, `fotos_com_descricao`, `pecas`, `xp`,
  `vezes_reprogramada`). Renomear junto com a entrada do `equipamento_id`: hoje há 0 leitores do `nexus_fatos` fora de
  `nexus/dados` (auditoria, grep).
- `CAB_QUALIDADE` ganha `com_equipamento`, `pct_equipamento`, `pct_usina_versao`, `pct_pessoa_versao` (fatos que acham
  **exatamente 1** versão no histórico) e `extra` (JSON curto com contagens do fato: `{"checklist": 125, "anuladas": 0}`).
  Os percentuais passam a ter 1 casa decimal (o inteiro escondia 99,7 → 100).

Testes do catálogo: todo fato ativo tem `tipo` em `TIPOS_FATO` e `chave`; `sem_medida` ⇔ `medidas == ()`; toda
`Medida.coluna` termina num sufixo de unidade ou é indicador; todo livro citado por um fato `conformado` segue a regra
10 (`nexus_<assunto>`, aba `fato_`/`dim_`).

---

## 3. Passo 3 — um fato só de ronda e a PT conformada

### 3.1 `fato_ronda`

**Grão: 1 linha = 1 ronda realizada.** Une as rondas do App com e sem OS (`rondas_app_campo`), o checklist da carga
única (`nexus_rondas_checklist`) e as avulsas válidas (`nexus_rondas_avulsas`). Tipo: foto acumulada (revisão de
08/10: a "Situação da OS" anda de "em verificação" para "criada"; declarada transação, o passo 0 a congelaria).

Medido no `rondas_app_campo` (867 linhas, Data de 11/08 a 08/10): 743 com OS e 124 sem OS (o catálogo diz "1 OS de
ronda": errado). `Início` preenchido em 867 e único sozinho (0 repetições); (Data, Usina, Início) também único; OS
única nas 743. O checklist (125 linhas) casa 1 para 1 por `usina_id` + `inicio`: 124 com ronda sem OS e 1 com a ronda
que ganhou OS depois. O livro `nexus_rondas_avulsas` ainda não existe no banco (0 linhas).

**Chave do fato.** `ronda_id = sha1("app|" + Início)[:16]` para a ronda do App (o carimbo do aparelho, com
milissegundos, é estável; o nome da usina no Fracttal não é) e `sha1("avulsa|" + id)[:16]` para a avulsa. A linha do
checklist cuja ronda saiu da janela do App continua no fato (origem `app_sem_os`, lida do próprio livro do checklist)
com o mesmo `ronda_id`: as 125 respostas não somem em ~09/11.

| Coluna | Conteúdo |
|---|---|
| `ronda_id`, `origem` | origem ∈ `app_os`, `app_sem_os`, `avulsa` |
| `data_id` | dia de Brasília do `Início` (o `Data` do App difere em 1 de 867) |
| `usina_id`, `usina_ligada_por` | `Ligador.usina(Usina, Ativo da usina no Fracttal)`: 865/867 (861 de-para, 4 código) |
| `equipe_id` | papel **registro**: a `Região` do App (856/867). Na avulsa, vazio (a avulsa não registra equipe; a equipe da usina vem do `usinas_historico`) |
| `pessoa_id`, `pessoa_hmac`, `pessoa_ligada_por` | seção "Pessoa" |
| `equipamento_id` | o ativo da usina no Fracttal (a OS de ronda é sobre a usina): 743/743 com OS |
| `os`, `id_os_fracttal` | dimensão degenerada (vazio sem OS) |
| `os_situacao` | `criada` 412, `em_verificacao` 282, `criada_com_aviso` 49, `nao_criada` 124 (o texto do App vira domínio; o motivo longo fica fora) |
| `tipo_ronda` | `curta` 724 / `longa` 143 |
| `inicio`, `fim`, `duracao_min` | duração 0 a 480 min, senão vazio (a regra do App) |
| `nota_pts` | nota do App (867/867); avulsa vazio |
| `falhas_qtd` + 6 indicadores 1/0 | `longa_pendente` 276, `item_sem_foto` 116, `acao_sem_registro` 61, `checklist_incompleto` 7, `sem_gps` 2, `evidencia_incompleta` 2 (os 6 rótulos que o App gera; 421 rondas com alguma) |
| `trackers_apontados_qtd`, `trackers_respondidos_qtd` | do App |
| `checklist_fonte` | `app` (passo 2), `carga_unica_sem_os`, `avulsa`, `carga_unica_texto_os` (só se o Levi aprovar, abaixo); vazio = sem checklist |
| `sujidade_nivel`, `vegetacao_nivel` | 1 a 5; outro valor = vazio |
| `vala_nivel` | **domínio único**: 1 limpa, 2 parcial, 3 obstruída; "Não se aplica" e sem resposta = vazio |
| `sombreamento` | 1/0 (só a avulsa tem); o campo do App veio 1 vez em 804, com texto livre: **não entra** |
| `ipoa_sujo`, `ghi_sujo`, `albedo_sujo` | **1 = sujo, 0 = verificado limpo, vazio = não verificado ou não se aplica** |

Os domínios (`VALA`, `SENSOR`) moram numa constante só, em `nexus/dados/dominios.py`, importada pelo fato e pela
avulsa. Hoje divergem: o App e o checklist usam {Limpa, Parcial, Obstruída, Não se aplica} (texto da OS: Parcial 296,
Limpa 279, Obstruída 127, Não se aplica 84); a avulsa usa {Limpa, Parcial, **Suja**, Não se aplica} e grava sensor não
marcado como 0 ("limpo" sem ter sido visto). Como o livro da avulsa ainda tem 0 linhas, **corrigir a avulsa antes da
1ª gravação** custa só o formulário: vala no domínio do App e sensor com três estados (Limpo, Sujo, Não verifiquei).

**Respostas do checklist das rondas com OS.** Hoje só existem no texto da OS do Fracttal, guardado num arquivo local
(`C:\GridcoAuto\nexus\campo\rondas_aprovadas.json`: 804 respostas, fim de 13/08 a 05/10, completo até 07/10) e na
fila em memória (as "em verificação"). Medido: o arquivo cobre **602 das 743** rondas com OS (81%); faltam 141, 138
delas de outubro (99 "Em verificação", 23 "APR: a ronda não…", 8 "Fracttal barrou…"). **Decisão de desenho: a carga de
hora em hora NÃO lê esse arquivo.** Ele é de uma máquina (o PC tem um, o servidor outro) e a carga roda nas duas
(41 cargas do PC e 37 do servidor na auditoria): o fato trocaria de conteúdo a cada hora conforme a máquina. Caminhos:
1. **Recomendado:** o App manda as respostas no `rondas_app_campo` (colunas novas, com e sem OS), no mesmo release do
   passo 2 (técnico em HMAC). O App tem as respostas no registro de toda ronda: a janela inteira ganha checklist.
2. Carga única das 602 respostas do arquivo (como a de 06/10), num livro de carga única, `checklist_fonte =
   carga_unica_texto_os`. Grava o Levi.
3. Nada: cobertura do checklist fica em 125/867 (14%).

Cobertura de `sujidade_nivel` no fato: hoje 124/867 (14,3%); com (2) ~726/867 (~84%); com (1) ~100% da janela.

**Pessoa.** O fato nunca leva o nome. A ligação aceita os dois jeitos e o HMAC vence:
- `Técnico (HMAC)` (quando o App mandar, passo 2) → `pessoa_id` pelo mapa HMAC do cadastro; `pessoa_hmac` = o código.
- `Técnico` (nome em claro, hoje) → `pessoa_id` só se o nome (normalizado como `ligacao_cadastro._norm`) é de **uma**
  pessoa do cadastro (nome e nome padrão decifrados na memória). Medido: 79 nomes, 75 ligam a 1 pessoa, 0 ambíguos,
  4 sem pessoa; **794/867 rondas (91,6%)**.
- `pessoa_ligada_por` ∈ `hmac`, `nome`, `cadastro` (checklist/avulsa já gravados com `pessoa_id`).
- Chave durável para religar (KC-4): com o HMAC, `pessoa_hmac`. Só com o nome, o desenho propõe `pessoa_hmac =
  "n:" + HMAC(NEXUS_PESSOA_HMAC, nome normalizado)`; o `Ligador` calcula o mesmo código para o nome de cada pessoa do
  cadastro e religa quando ela entrar. **Decisão do Levi** (seção 9).

**Avulsa anulada.** O fato traz só `ronda_avulsa.validas()`: a ronda anulada não foi realizada e a linha de anulação
não é ronda. A qualidade conta as anuladas em `extra`. O livro-fonte da avulsa continua só-acréscimo. Antes da 1ª
gravação dele, a linha de anulação deveria sair **sem** `data_id` e `usina_id` (hoje vai com os dois, e um
`COUNT(*)` por usina e dia no livro aberto conta 2 para uma ronda anulada: GR-7).

**Herda do passo 0.** O fato é refeito a cada hora a partir do App (janela de 90 dias): a ronda do App de 11/08 sai do
fato por volta de **09/11/2026**. O checklist (livro próprio) e a avulsa (o Nexus é a fonte) não se perdem. Com o
passo 0, o fato vira atualização por `ronda_id` (não só acréscimo) e a anulação de avulsa passa a ser uma remoção pelo
`ronda_id`.

**Exposição (GS-1).** O fato não abre nada que o `rondas_app_campo` aberto ao lado já não abra (nome + nota da ronda,
861/861). O nome some da fonte com o passo 2; a purga do histórico por linha da API é com a T.I.

### 3.2 `fato_pt`

**Grão medido: 1 linha = 1 PT × ativo.** `pt_app_campo` tem 226 linhas e 220 números (4 números repetem 2 a 3 vezes);
(Número, Código do ativo) é único nas 226; (Número, Tarefa) repete 5. Nas repetidas mudam `Criada em`, `Código do
ativo`, `Ativo` e `Decidida em`: o App decide por linha. Tipo: **snapshot acumulado** (a linha muda quando a PT é
decidida).

| Coluna | Conteúdo / medida |
|---|---|
| `pt_linha_id` | `sha1(Número + "|" + Código do ativo)[:16]` |
| `pt`, `os`, `codigo_ativo` | degeneradas (OS em 226/226) |
| `primeira_linha_da_pt` | 1 na 1ª linha de cada número (pelo código): `SUM` = PTs distintas (220) |
| `data_id_criacao`, `data_id_decisao` | papéis, dia de Brasília. 53 das 197 decididas foram decididas em outro dia |
| `usina_id`, `usina_ligada_por` | 224/226 (221 de-para, 3 código) |
| `equipe_id` | papel registro (`Região`): 221/226 |
| `equipamento_id` | 226/226 |
| `solicitante_pessoa_id`, `solicitante_hmac` | 202/226 (89,4%); 36 códigos distintos |
| `decisor_pessoa_id`, `decisor_hmac`, `decisor_papel` | **0/197 ligam**: 6 códigos distintos, todos com papel "Admin" (contas fora do cadastro) |
| `situacao` | domínio `aguardando` (29), `de_acordo` (197), `negada` (0 hoje) |
| `decidida` | 1/0 |
| `espera_min` | `Decidida em − Criada em`; só decididas. Mediana 131 min; 0 negativas |
| `parada` | 1 se esperou mais de 120 min (decidida) ou se, aguardando, já passou de 120 min na carga: uma vez 1, fica 1. 101/197 decididas |
| `respostas_nao_qtd`, `atividades_qtd` | contagens (as atividades são lista de 76 itens; o texto não entra) |
| `forcada`, `efeito` | 1/0 (vazio em 226 hoje); `efeito` domínio (`anexada` 197) |

Fora: `Motivo` (vazio), `1º aviso: motivo` (223 linhas com a mensagem de erro do e-mail, não é dado da PT), `Ativo`
(texto; o `equipamento_id` já diz qual é).

**A decisão do Nexus (`nexus_pt_decisoes`, 0 linhas no banco)** grava por número e pega a 1ª linha da PT (GR-4): numa
PT de 3 ativos, não diz a qual vale. Antes da 1ª gravação: levar `codigo_ativo` e a aba `fato_decisao_pt` (GS-6).
**Decisão do Levi:** a decisão do Nexus vale para a PT inteira ou por ativo, como o App.

**Herda do passo 0.** PT desde 28/09 no livro do App: perde a partir de ~27/12/2026. Com o passo 0, o fato é
atualização por `pt_linha_id` (snapshot acumulado), não acréscimo.

**Testes (ronda e PT), com `tests/pg_falso.py`:** ronda sem OS + checklist = 1 linha; checklist sem a linha do App
continua no fato com o mesmo `ronda_id`; avulsa anulada fora e anulação não vira linha; vala "Obstruída" do App e do
checklist = 3, "Não se aplica" = vazio; sensor "Limpo" = 0, "Sujo" = 1, sem resposta = vazio; nome de duas pessoas não
liga; HMAC vence o nome; **nenhuma célula do fato contém o nome** (varredura); `data_id` de um início às 02:30Z cai no
dia anterior; `pt_linha_id` único com o mesmo número em 2 ativos; `primeira_linha_da_pt` soma o nº de PTs; `espera_min`
vazio na aguardando; `parada` não volta a 0; qualidade com `extra`.

---

## 4. Passo 5 — histórico SCD2 que acha exatamente 1 versão

Medido hoje: `pessoas_historico` 135 linhas, `valido_de` 30/09 em 134; `usinas_historico` 258, 30/09 em 257.

| Fato | Pessoa: acham 1 versão hoje → no desenho | Usina: hoje → no desenho |
|---|---|---|
| fato_fechamento (13/08 a 08/10) | 697/2.743 (25,4%) → 2.743 (100%) | 766/2.898 (26,4%) → 2.898 (100%) |
| fato_checklist_ronda | 7/113 (6,2%) → 100% | 7/125 (5,6%) → 100% |
| fato_ronda (App, a montar) | 170/794 (21,4%) → 100% | 185/865 (21,4%) → 100% |
| fato_pt (desde 28/09) | 202/202 → 202 | 224/224 → 224 |

(simulação: `valido_de_id <= data_id < valido_ate_id` com o histórico lido do banco e a 1ª versão de cada membro
recuada para 19000101.)

**Cabeçalho novo** (mesmas abas): `<id>, <rastreados…>, versao, valido_de, valido_ate, valido_de_id, valido_ate_id,
vigente, inicio_presumido`. `valido_de`/`valido_ate` seguem em texto AAAA-MM-DD (aberto = vazio) para quem já lê;
`valido_de_id`/`valido_ate_id` são inteiros como o `data_id` (aberto = 99991231). `versao` = 1, 2… por membro.

**Regras de `historico.atualizar` (pura):**
1. **1ª versão de todo membro** começa em `1900-01-01` (`19000101`) com `inicio_presumido = 1`: "antes de existir
   histórico, vale o que se sabia na 1ª carga". Quem quer só o que foi visto filtra `inicio_presumido = 0`. Membro novo
   nasce do mesmo jeito (dimensão que chega atrasada). **Migração na próxima carga:** a versão de menor `valido_de` de
   cada membro já gravado passa a 1900-01-01 + presumido (idempotente).
2. **Dia de Brasília em tudo.** `alterado_em` vem em UTC ("…Z"): 133 de 134 pessoas têm 30/09 02:xxZ, que é 29/09 em
   Brasília.
3. **Data da troca** = dia de Brasília do `alterado_em` da linha, limitado a [`valido_de` da vigente, hoje]. (Hoje é o
   dia da carga; o `alterado_em` é a última edição de qualquer campo, sempre ≤ hoje e ≥ a troca rastreada.)
4. **Duas mudanças no mesmo dia:** se a vigente começou no mesmo dia da troca, ela é sobrescrita: nada de versão de
   duração zero; o dia fica com o último estado (grão diário, escrito no docstring).
5. **Reentrada** (membro com versão fechada que volta): abre em **hoje**, nunca no `alterado_em` antigo (hoje reabre
   no passado e sobrepõe).
6. **Ausência não fecha.** Só `excluido = sim` fecha uma versão (o cadastro não apaga linha; ausência é leitura falha
   ou publicação menor). Cadastro lido vazio, ou histórico anterior lido vazio quando `nexus_dimensoes · atualizacao`
   existe: o histórico **não anda** nesta carga (repete o anterior) e a qualidade diz o motivo.
7. **Conferir antes de publicar:** por membro, sem sobreposição, sem buraco (`valido_ate` = `valido_de` da seguinte) e
   exatamente 1 vigente. Falhou: publica o histórico anterior sem mudança e registra.

Função pura `da_epoca(historico, id, data_id) -> linha | None`, usada pela qualidade e pelos testes.
`nexus_dimensoes · qualidade_historico`: `entidade, membros, versoes, presumidas, sobreposicoes, buracos,
sem_vigente, ausentes_na_leitura, pulou_motivo, gerado_em`. A qualidade dos fatos ganha `pct_*_versao` (seção 2).

**Herda dos passos 0 e 1.** O histórico continua refeito a partir de si mesmo e regravado inteiro a cada hora: as
regras 6 e 7 seguram a leitura vazia e a sobreposição, não um histórico anterior lido pela metade com 200 (isso é o log
só-acréscimo do passo 0). Com dois donos do cadastro (passo 1), uma publicação antiga do outro lado vira "mudança"
real; nada aqui impede.

**Testes:** fato anterior à 1ª carga acha 1 versão (presumida); migração idempotente; reentrada abre em hoje sem
sobrepor; cadastro vazio não fecha ninguém; ausente sem `excluido` continua vigente; `excluido = sim` fecha; duas
trocas no dia = 1 versão; `alterado_em` 02:30Z vira o dia anterior; entidade usinas; conferência que acha sobreposição
não publica; todo fato dos fixtures acha exatamente 1 versão.

---

## 5. Passo 6a — dimensão de equipamento

**Espinha: o código do ativo do Fracttal**, canônico (maiúsculo, sem espaço), nos dois formatos: "ABC100-INVR2.4" e
"XYZ-DEF100-INVR11.1" (prefixo do cliente). Está em 2.907/2.907 fechamentos e 226/226 PT.

**Membros** (só de fontes que as duas máquinas leem igual, ou seja, do banco):
- a **foto de ativos do Fracttal** que o OS Creator já guardou em arquivo: a de 22/09/2026 (21.638 ativos, 21.634
  códigos, com `id`, `id_parent`, `tipo_code`, descrição) e os 719 códigos que só a de 21/06 tem (renomeados ou
  baixados). Entra **uma vez** no livro `nexus_ativos_fracttal · foto_ativos` (carga única, `--ensaio` por padrão;
  quem grava é o Levi). Atualizar a foto exige ler o Fracttal: fica para depois, fora do horário de campo;
- os códigos dos livros do banco: fechamentos (1.679), PT (189), rondas (109), `campo_nexus` (3.806),
  `de_para_trackers` (4.313) e a programação do PCM (2.345).

União das fontes: 8.782 códigos, **8.773 nas duas fotos (99,9%)**. Dimensão: **22.362 membros**. O `os_falhas.json`
(2.337 códigos, local) já está 99,6% nas fotos: não precisa entrar.

**ID estável entre máquinas e cargas:** `equipamento_id = int(sha1("fracttal:" + codigo).hexdigest()[:13], 16)`.
- 52 bits: menor que 2^53, exato no JSON, no JavaScript e no número do xlsx. Medido nos 22.362: **0 colisões**. Colisão
  futura = a carga recusa (teste).
- Sem registro, sem "maior + 1", sem ordem: PC e servidor calculam o mesmo número sem conversar; o fato não precisa
  ler a dimensão para pôr o ID, e o membro que some e volta volta com o mesmo ID.
- Contra o **registro só-acréscimo no banco com ordem determinística**: precisa de um escritor só (passo 1, adiado) e
  de ler antes de gravar; com duas máquinas, as duas dão o próximo número a códigos diferentes, o defeito do cadastro.
  Numerar pela ordem do código renumera ao entrar um código no meio.
- Custo: código renomeado no Fracttal vira membro novo. Medido: 8 de 2.137 `id_item` do `os_falhas.json` têm hoje
  outro código na foto (0,4%). A dimensão guarda `fracttal_item_id`; a qualidade lista o item com 2 códigos.

**`dim_equipamento`:** `equipamento_id, codigo, descricao, usina_id, usina_ligada_por, motivo_sem_usina, familia,
tipo_fracttal, pai_id, fracttal_item_id, na_foto (1/0), foto_em, fontes_qtd`.
- `usina_id` pelo código da usina dentro do código (`codigo_do_equipamento`), só se for de **uma** usina: 19.593 de
  22.362 (87,6%: 12.122 pelo sufixo único, 7.471 pelo código cheio); 1.910 com código fora do cadastro, 689 sem código
  de usina, 170 de 2+ usinas (`motivo_sem_usina`). Nos códigos das fontes: 98,2%.
- `familia` = o prefixo depois do código da usina (ETKR, INVR, DINV, SSPV, ESTM…; `USINA` quando o código é só a
  usina): 31 famílias. `tipo_fracttal` = `tipo_code` da foto (68 tipos). São atributos diferentes: batem em 16.612 de
  21.638 (a família é o grupo: ESTM contém PRN, SDT…).
- `pai_id` pela `id_parent` da foto: 21.048 de 21.638 têm o pai na foto.

**`equipamento_apelido`** (o modelo do `de_para`): `equipamento_id, sistema, chave_externa, casou_por`.
- `Supervisório · tracker`: o `de_para_trackers` (fonte | usina no supervisório | tracker → `Code Fracttal`): 4.313
  linhas, 0 chaves repetidas, nenhum código com 2 apelidos; `casou_por` = "Como casou" (1.430 dizem "CONFIRMAR").
- `Gêmeo · equipamento`: o tracker do gêmeo pelo `alias` (sistema bd_trackers) → `de_para_trackers`: 332 de 550 (o
  código do gêmeo casa 0% direto). Inversor e string do gêmeo: sem caminho ainda.
- `BD_Thopen · coluna` / `BD_Performance · coluna`: "aba|Inversor n.m" → `<código da usina>-INVRn.m`: 1.108 de 1.489
  colunas das abas já ligadas (74%), `casou_por = "número do inversor"`.
- Chave externa que aponta para 2 equipamentos não liga.

**`equipamento_id` nos fatos** (com `equipamento_ligado_por`): só quando o código está na foto **ou** tem código de
usina; senão vazio. `fato_fechamento` 2.906/2.907 (1 fora do padrão), `fato_pt` 226/226, `fato_ronda` 743/743 com OS,
`fato_programacao` 5.873/5.876.

**Livro e cadência:** `nexus_equipamentos` (`dim_equipamento`, `equipamento_apelido`, `qualidade`, `atualizacao`),
~1 MB; a carga de hora em hora monta e **só publica quando o sha das linhas difere** do gravado em `atualizacao`.

**Herda do passo 0:** membro que só existe num fato de janela de 90 dias some da dimensão quando sai da janela
(mas volta com o mesmo ID). "Membro nunca sai" exige ler a dimensão anterior: é o passo 0. As fotos seguram 99,9%.

**Testes:** os dois formatos; código de 2 usinas sem `usina_id`; ID igual em duas execuções e < 2^53; colisão recusa;
família e pai; apelido ambíguo não liga; fato com código inválido fica vazio; o membro não depende da máquina (montado
só do `pg_falso`).

---

## 6. Passo 6b — programação do PCM no banco (`fato_programacao`)

**Fonte:** `banco_dados.json` do repositório público do PCM (`URL_PADRAO` de `nexus/pcm/fonte.py`), lido por
`fonte.ler`. Medido: **só as 4 semanas mais recentes** (W38 a W41, `fonte` = "gerar_pcm_json.py (4 semanas)"), 5.876
linhas (1.326 a 1.789 por semana), 35 campos, 2.231 OS, 2.345 códigos; o robô publica a cada ~30 min (5.894 versões
desde 29/05/2026 no histórico do git).

**Grão medido: 1 linha = 1 bloco de agenda de uma tarefa na semana** (semana × OS × código × tarefa × dia × hora de
início: 0 repetições). (semana, OS, código, tarefa) repete 37 vezes: a tarefa partida em dois dias ou horários. 820
das 4.422 tarefas aparecem em 2 ou mais semanas (reprogramadas). Tipo: **snapshot periódico semanal** (o plano
publicado + o estado na última leitura; a semana passada + 7 dias fica congelada).

| Coluna | Conteúdo / medida |
|---|---|
| `programacao_id` | `sha1(semana|os|codigo|tarefa_chave|dia|h_ini)[:16]` |
| `data_id_semana`, `data_id_programada` | a segunda-feira da semana ISO e o dia do bloco (`dia` + `dates`) |
| `data_id_criacao_os`, `data_id_fim_execucao` | papéis (`dataCriacao`, `dataFinal`: 2.349 preenchidas) |
| `usina_id`, `usina_ligada_por` | `Ligador.usina(usina, codigo)`: **5.870/5.876** (5.782 de-para "Fracttal · Classificação 1", 88 código) |
| `equipe_id` | o `cluster` ("Equipe Cluster") pelo nome: 5.813 (98,9%); 2 clusters fora do cadastro (63 linhas) |
| `pessoa_id_tecnico` | `resp_os` pelo nome, só se de 1 pessoa: 47 de 69 nomes, **5.060 linhas (86,1%)** |
| `pessoa_id_responsavel` | `responsavel` pelo nome: 7/7 nomes, 5.876 linhas |
| `equipamento_id`, `codigo_ativo`, `os` | 5.873 códigos válidos; OS degenerada |
| `tarefa_chave` | `sha1(texto da tarefa normalizado)[:12]`; o texto não entra. **Função única em `fatos.py`, usada também no `fato_fechamento`**: programado × executado casa (OS, código, tarefa) em 1.763 de 1.765 pares com (OS, código) |
| `tipo_tarefa` | domínio de 16 (MPM 1.064, Inspeção 1.014, Corretiva 718…) |
| `criticidade_rotulo`, `criticidade_pts` | a coluna mistura rótulo (Médio, Alto, Muito alto, Baixo: 2.410) e número (3.466): duas colunas (KC-1) |
| `primeiro_bloco` | 1 no 1º bloco da tarefa na semana: `SUM` = tarefas programadas |
| `duracao_min`, `deslocamento_min` | `duracao` e `desloc` vêm em horas (mediana 1,0 h; `h_fim − h_ini` = duração em 5.094/5.876) |
| `hora_inicio` | HH:MM |
| `reprogramada`, `termo`, `paralelo`, `nova_os`, `rolada` | 1/0 (vazio onde a fonte não diz: 2.143) |
| `vezes_reprogramada_qtd` | inteiro |
| `status_execucao`, `status_os` | domínios de 4 e 3 |
| `semana_gerada_em`, `lido_em` | linhagem |

Fora: `relatorio` (texto livre, 674), `etiquetas` (JSON, 721: ponte futura), `historico` (vazio), `mttr_*` (constante).

**Livro e cadência:** `nexus_programacao` (`fato_programacao`, `qualidade`, `atualizacao`); de hora em hora, grava só
se o `geradoEm` mudou. ~1.500 linhas/semana: ~76 mil/ano.

**Herda do passo 0 — o pior caso dos cinco:** a fonte guarda 4 semanas. Com troca integral, o fato nunca passa de 4
semanas e cada semana some 4 semanas depois. Só serve com "a semana da fonte substitui a mesma semana no banco; as
outras ficam" (merge por semana), que é o passo 0. Histórico anterior a W38: está no git público (1 versão por
semana, W22 a W37), carga única possível sem tocar no Fracttal. **Decisão do Levi** (seção 9).

**Testes:** a tarefa partida em 2 dias = 2 linhas e 1 `primeiro_bloco`; `programacao_id` único; usina pelo de-para e,
sem par, pelo código; cluster fora do cadastro = vazio; nome de 2 pessoas não liga e nenhum nome no fato; criticidade
dividida; duração em minutos; semana ISO → segunda-feira; `tarefa_chave` igual para o mesmo texto no PCM e no App.

---

## 7. Passo 6c — geração em linhas

**Medido nas fontes (1 aba por usina, inversor por coluna):**

| | `bd_thopen` | `bd_performance` |
|---|---|---|
| abas / de geração | 108 / 99 (todas com nome de usina) | 63 / 53 (10 com nome = código, 43 com nome) |
| linhas usina × dia | 28.224 (0 dias repetidos) | 17.564 (17.521 dias; 43 sem data) |
| período | 01/08/2025 a 22/03/2027 (2.373 linhas de dia futuro pré-criadas; 92 células futuras preenchidas) | 01/01/2025 a 22/11/2026 (1.103 linhas futuras) |
| colunas de inversor | 1.340 ("Inversor n.m"; 4 abas usam outro rótulo) | 908 |
| células inversor × dia | 370.556 (78 texto: "#N/A" 48, vírgula decimal 30; máx 39,1 milhões = leitura acumulada) | 333.556 (262 negativas, 271 texto) |
| colunas da usina | Energia Produzida (kWh) 27.853, IPOA 23.255, GHI 13.454, Chuva 9.161, Disponibilidade 25.079, Validação 1/0, SKID n (kWh) | IPOA DEF 16.220, IPOA 8.789, GHI 8.126, Multimedidor 4.938, Validação 1/0 |

Total: **45.745** usina × dia e **~704 mil** inversor × dia (~2.250 inversores: ~820 mil linhas novas por ano).
xlsx medido com o `xlsx_bytes` da casa: 45.745 linhas = 1,7 MB (7 s); 100 mil linhas de inversor = 6,3 MB (17 s) →
704 mil ≈ 44 MB.

**`fato_geracao_usina_dia`** (snapshot periódico diário). `geracao_usina_id = sha1(fonte|aba|data)[:16]`; `data_id`;
`usina_id`, `usina_ligada_por`, `usina_motivo`; `fonte`, `aba`; `energia_medidor_kwh` (Energia Produzida / Multimedidor);
`ipoa_kwh_m2` (no `bd_performance`, a coluna "DEF"; decisão da Performance), `ghi_kwh_m2`, `chuva_mm`,
`disponibilidade_pct`, `validado` (1/0); e, **declarados agregados do inversor × dia**: `energia_inversores_kwh`,
`inversores_com_dado_qtd`, `inversores_qtd`. Dia futuro não é fato (fica fora e conta na qualidade). Texto
("#N/A") = vazio e conta; vírgula decimal é lida.

**`fato_geracao_inversor_dia`** (snapshot periódico diário). Grão: 1 linha = inversor × dia com valor.
`geracao_id = sha1(fonte|aba|coluna|data)[:16]`; `data_id`, `usina_id`, `equipamento_id` (+ `_ligado_por`, pelo
apelido `BD_* · coluna`: 74%), `fonte`, `aba`, `inversor` (o rótulo da coluna), `energia_kwh`, `kwh_fora_da_faixa`
(1/0: negativo ou acima do teto → `energia_kwh` vazio). Teto: decisão (seção 9).

**Ligação aba → `usina_id`.** A regra da casa: sistema novo entra no `de_para` do cadastro: `BD_Thopen · aba` e
`BD_Performance · aba` (chave = nome da aba), acrescentados em `nexus/cadastro/ligacoes.FONTES_API` e casados pelo
`banco.de_para` (código, nome, `casamento.casar`). Medido o que casaria:
- `bd_thopen` (99): **84** exatos (77 pelo nome da aba e 7 pela coluna Usina, iguais às chaves do sistema que já existe,
  `BD_Thopen · Dados Gerais Usinas`), +4 pelo casamento por nome do cliente, **11 sem par**;
- `bd_performance` (53): **10** pelo código (aba = código de 1 usina), 2 pelo de-para de outro sistema, 32 só pelo
  casamento por nome contra **todos** os clientes (frágil: conferir na tela Ligações), **9 sem par**. O sistema que já
  existe (`BD_Performance · Base UFV`, chaves em código com prefixo) casa 0 abas.

**A publicação do cadastro com esses sistemas é do Levi (passo 1 adiado).** Até lá o fato sai com `usina_id` vazio e
`usina_motivo = "aba sem de-para publicado"`; a qualidade mostra 0% de usina na geração, de propósito.

**Livro e cadência:** `nexus_geracao` (`fato_geracao_usina_dia`, `qualidade`, `atualizacao`), diária, depois da coleta
noturna que grava `bd_thopen`/`bd_performance` (~00:10): por exemplo 01:40, com a mesma trava de "uma máquina por vez".
O inversor × dia **não cabe** em troca integral (44 MB/dia, e a conferência relê ~700 páginas): ou espera o passo 0
(acréscimo por dia, um livro só), ou um livro por mês `nexus_geracao_inversor_AAAA_MM` (~67 mil linhas ≈ 4,2 MB;
refaz só o mês corrente e o anterior; 12 nomes para sempre por ano). **Decisão do Levi.**

**Herda do passo 0/1:** as fontes guardam a história desde 2025: a troca integral diária não perde passado. Herda o
"encolher": aba regravada vazia ou menor faz o fato encolher sem aviso (a guarda é do passo 1); até lá, a qualidade
compara os dias por aba com a carga anterior e mostra a diferença.

**Testes:** aba larga → linhas (1 por inversor com valor); "#N/A" e vazio não viram linha; vírgula decimal; negativo
e acima do teto = vazio + 1; dia futuro fora; `energia_inversores_kwh` = soma das linhas; aba sem de-para = `usina_id`
vazio com motivo; código de 2 usinas não liga; `Inversor 2.4` liga a `<usina>-INVR2.4` só se o código existe.

---

## 8. Ordem de construção

1. **Catálogo** (`Medida`, `tipo`, `medidas`, `chave`, `fontes`, `janela_origem`) e `CAB_QUALIDADE`: uma pessoa só,
   antes dos outros, porque todos mexem nas mesmas linhas.
2. Em paralelo: **histórico** (só `historico.py` + `carga.py` na parte do histórico); **equipamento** (módulo novo);
   **ronda e PT** (depende do `equipamento_id`: até o módulo existir, a coluna fica vazia); **programação** e
   **geração** (módulos novos, sem gravação ligada).
3. Cada um mede com `ferramentas/carregar_dados.py --ensaio` e atualiza o `nexus/dados/CLAUDE.md` (o que existe, a 1ª
   medida, as pendências reescritas).

---

## 9. Decisões do Levi

1. **Checklist das rondas com OS:** pedir ao App as respostas no `rondas_app_campo` no release do passo 2
   (recomendado) e/ou carga única das 602 do arquivo local.
2. **Chave durável da pessoa que só vem por nome** (ronda hoje, PCM sempre): guardar `"n:" + HMAC(nome)` no fato para
   religar depois (recomendado) ou aceitar que a linha sem pessoa nunca religa depois do passo 0.
3. **Avulsa antes da 1ª gravação:** vala no domínio do App (sai "Suja"), sensor com três estados, anulação sem
   `data_id`/`usina_id`.
4. **PT:** a decisão do Nexus vale para a PT inteira ou por ativo; e quem são as 6 contas "Admin" que decidem (0/197
   ligam ao cadastro).
5. **SCD2:** aceitar a 1ª versão "desde sempre" com `inicio_presumido = 1` (o revisor da auditoria chamou de chute; o
   desenho deixa o chute marcado e filtrável).
6. **Equipamento:** ID derivado do código (recomendado) × registro só-acréscimo (só depois do passo 1); gravar a carga
   única das duas fotos de ativos; quando reler o Fracttal para renovar a foto.
7. **Programação:** só vai ao banco com o passo 0 (recomendado) ou antes, com merge por semana próprio; carga única
   das semanas W22 a W37 do histórico do git público.
8. **Geração:** publicar o cadastro com `BD_Thopen · aba` e `BD_Performance · aba` (passo 1) e conferir as 32 abas do
   `bd_performance` casadas só pelo nome; se pode usar já o sistema `BD_Thopen · Dados Gerais Usinas` (84 abas
   exatas) enquanto isso; o teto de kWh/dia por inversor (proposta: `potencia_inversores` do cadastro × 24 h; sem
   potência, só o negativo cai); qual IPOA do `bd_performance` vale (DEF, ETM ou o simples); inversor × dia com o passo
   0 ou em livros mensais.
9. **Equipes que faltam no cadastro** (2 clusters do PCM, "MT Sul 02" do App) e as 4 pessoas das rondas sem ficha
   (73 rondas): se conserta no cadastro, não no fato.
