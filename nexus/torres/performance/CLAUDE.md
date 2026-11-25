# CLAUDE.md — torre Performance

| Tela | Estado | De onde vem |
|---|---|---|
| Tempo real, Painel NOC, Diagnóstico, Strings e trackers, Visão gerencial, Disponibilidade, Gêmeo digital, Rondas de Trackers, Comentários (desde 03/11/2026; o Criador de relatório e o Relatório semanal foram para Relatórios → Central de emissão em 13/10/2026; os endereços antigos levam para lá) | a tela da Plataforma de Performance numa moldura (porta única, 09/10/2026): o passe abre a sessão da plataforma e ela desenha a tela, com leitura e gravação. Sem a `NEXUS_SSO_CHAVE`, "Performance ainda não ligada neste servidor"; o Tempo real, nesse caso, cai na ponte de 04/10 (só leitura), se ela estiver configurada. Diagnóstico = seletor de usina (a lista do Painel NOC, lida pelo navegador) e o diagnóstico dela. Sem a faixa "<tela> · Plataforma de Performance" (13/10/2026, "suma esse 2° cabeçalho"): só o Diagnóstico tem a linha, com o seletor. O Painel NOC tem modo TV (11/10/2026): o botão "Modo TV" no topo do Nexus, ao lado do Tema (até 13/10/2026 na faixa), e o `?tv=1` sem a casca, com o mesmo passe e a mesma renovação da sessão da plataforma; a TV dura enquanto valer a sessão do Nexus de quem a abriu (pelo Fracttal, ~12 h a partir do LOGIN), com o prazo à vista nos controles e, na última meia hora, num aviso no canto | as views saem de `registrar_molduras` (`nexus/torres/moldura.py`; `tv={"noc"}` no `__init__.py` daqui), o mapa e o passe de `nexus/performance/porta.py`, os templates `performance/moldura.html` e `performance/moldura_tv.html` e o `nexus/static/porta.js`: leia as seções "Porta única" e "Modo TV do Painel NOC" de `nexus/performance/CLAUDE.md` |
| Clima e risco | foi para a Usinas 360° em 24/11/2026 (`/t/campo/clima`, `torres/campo/clima_tela.py`; Levi: "clima e risco vai para usinas 360"); `/t/performance/clima/...` responde 308 (`mapa_tela.py`) | `nexus/performance/clima/` (a regra fica aqui) |
| Quadro da equipe (04/11/2026) | o Quadro da equipe da Engenharia clonado para a Performance (Levi: "clone o quadro de equipe da engenharia para o time de performance com as pessoas da performance"; "tira do BASE > ACESSOS > PESSOAS E SETORES"): supercards por pessoa, a faixa de números e o kanban das OS do Fracttal, o mesmo template. A mesma leitura que não some do quadro da Engenharia (10/11/2026: cada pessoa à parte, a última leitura no disco em `quadro_equipe_performance.json.gz`). **A equipe é o setor Performance** de Base → Acessos → Pessoas e setores (a última decisão de cada pessoa, livro `nexus_setores`), pelo id do Fracttal guardado na decisão (sem casar nome; homônimo fora); pessoa do setor que o Fracttal não tem sai em "Não achei no Fracttal: id N". **O clique abre a página da OS da Engenharia** (09/11/2026, Levi: "quando clico na parte de performance não abre a tela personalizada"; até então era o card do OS Creator), `/t/engenharia/equipe/os/<nº>?de=performance`: a página é do chat da Engenharia e não é copiada, para herdar o que ela ganhar (o editar o início e o fim da atividade, o anexo). O `?de=performance` diz de onde a pessoa veio; a volta para este quadro e a passagem do setor Performance pelo portão da página são da Engenharia. **Os Parâmetros** (09/11/2026, Levi: "no estilo de filtros do OS Creator, suspenso porém ao salvar o parâmetro deixa filtrado fixo mesmo que carregue ou reinicie"): depois da busca, o painel suspenso do modelo A do Histórico com Responsável e Etiqueta (listas com busca) e o Salvar; o salvo fica no localStorage do navegador (`kb_parametros_<area>`, um por quadro), some o supercard de quem ficou fora e aparece como etiqueta com × embaixo da barra. A faixa de números do topo segue sendo a da equipe toda. Vale nos dois quadros (o template é um só). **O pulso** da OS aberta parada há mais de 7 dias conta só o Fracttal (a mexida nas tarefas e a criação): a Performance não tem livro de OS. Do setor Performance (`do_setor`): quem é dele vê sem marcar em Acessos. Estado próprio (a cópia de 5 min, o "pronto antes de abrir" de 2 h e a leitura 330 s depois de subir, no `instalar` da Engenharia), separado do quadro da Engenharia | `nexus/performance/quadro_equipe.py` (a leitura, reusa `nexus/engenharia/os_equipe.py`), a rota `equipe()` no `__init__.py` daqui (os supercards e a faixa são os da torre Engenharia), o template `engenharia/equipe.html` com `area="performance"`. Prova: `python -m pytest -q tests/test_performance_quadro_equipe.py` (a rota calcula o pulso com `datetime.now`; o teste para esse relógio em AGORA, senão quebra quando as OS do teste passam dos 7 dias, como em 09/11/2026) |
| Mapa de risco | saiu em 24/11/2026 (Levi: "Mapa de risco pode tirar. Já está tudo lá na parte de mapa de equipe"): `/t/performance/clima/mapa` leva ao Mapa de equipe com as usinas e o clima (`/t/campo/equipe?ver=usinas&clima=1`); a tela, o modo TV, os `_mapa_*.html` e o `clima-mapa.js/.css` foram apagados | o modelo `nexus/performance/clima/mapa.py` segue (o Mapa de equipe o usa) |
| ETMs (24/11/2026) | as OS das estações meteorológicas, que vieram da Engenharia: Estações em Aberto, Planner, Histórico e Fechamentos, com a cópia em disco e o chat da usina com caixa de comentar (seção "ETMs", abaixo) | Fracttal (cópia em disco) e o livro `nexus_engenharia_etm` |

| Coletas | desde 11/11/2026: o Conversor Grid Co. do backoffice (o .exe) dentro do Nexus: Arquivos, Resultado e Furos de coleta. O BD vem do banco com o mapa de fórmulas que a coleta sobe (livro `bd_formulas`); sem ele, o BD em Excel solto junto. A saída é a planilha para colar, nada vai ao BD. Desde 16/11/2026 tem a sub-aba **Furos de coleta** (`/coletas/furos-de-coleta`): o relatório R01 da analista calculado pelo Nexus (banco + COS), com a validação de todos no servidor | `coletas_tela.py` e `furos_tela.py` (rotas), `performance/coletas_furos.html` com `static/coletas-furos.js` (a aba dos furos), `performance/coletas.html` (a casca com o "!") e `performance/coletas_app.html` (GERADO da tela do .exe por `ferramentas/portar_tela_conversor.py`), `nexus/static/coletas/furos.js` (gerado): leia `nexus/performance/coletas/CLAUDE.md` |

A regra mora em `nexus/performance/`; aqui ficam as rotas e os templates. As molduras seguem o padrão do OS Creator (`.conteudo--moldura`), com as classes `.porta-*` no `nexus.css` (as `.ponte-*` são da ponte de 04/10, a reserva do Tempo real). Os ids das telas que já existiam não mudaram (viraram endereço e favorito); Acompanhamento COS (torre COS) e Chaves das fontes (torre Base, só admin) usam a mesma moldura. A moldura em si (o passe, o iframe e o `porta.js`) fica em `_porta.html` desde 14/10/2026, porque também entra na coluna da direita da Central de emissão (`relatorios/moldura.html`); e `registrar_molduras(..., abas=...)` põe abas acima dela, a da plataforma e páginas do Nexus ao lado (Chaves das fontes → Fontes da Performance | Nexus).

Strings e trackers grava no banco do Nexus (20/10/2026, o Vincular OS): a OS ligada a cada falha de string ou tracker vai ao livro `nexus_falhas · fato_decisao_vinculo_os`, gravado e lido pela própria plataforma. O Nexus só o cataloga: grão, colunas e regras em `nexus/dados/CLAUDE.md` ("Vínculo de OS às falhas").

**Sala de controle** (16/11/2026; o dono: "uma visão parecida com essa para performance", a partir do Control room de um
portal de fora): mais uma tela da Plataforma de Performance na moldura (`/painel/sala-de-controle`), logo depois do Tempo
real no menu. A fonte do tempo real na lateral, o que falta acompanhar na frente, e a usina com as strings, os trackers e a
estação. Nesta 1ª entrega ela só lê. A tela, as regras do dono e as próximas entregas estão na plataforma:
`docs/sala-de-controle.md` e `plataforma/CLAUDE.md` (seção "Sala de controle da Performance"). O mapa da porta única passou
a 17 telas (assinatura `db2b2cf9380d2b67`, nos dois lados). Quem a vê: marcar em Base → Acessos, como as outras.

**A Sala de controle lê o "abaixo dos demais" daqui** (16/11/2026, entrega 3 dela): `GET /t/performance/sala-de-controle/abaixo?mes=`
(`sala_tela.py`) devolve o mesmo resultado do mural da Coletas (`servico.furos_mural`, só com os BDs do banco), para a
tela da plataforma mostrar sem refazer a conta. Abre para quem tem a tela "Sala de controle" (o caminho fica debaixo
dela), sem depender de ter a Coletas; o resultado fica no mesmo cofre do mural. Prova: `tests/test_coletas.py`
(`test_a_sala_de_controle_le_o_abaixo_dos_demais_daqui`).

**O novo da Sala de controle no sino do topo** (16/11/2026): `nexus/performance/sala_novas.py` pergunta à plataforma, pela
ponte de leitura, o novo de quem está na sessão (`/api/sala/novas?pessoa=<e-mail>`; a regra é de lá) e o `casca._perf_do_sino`
o põe no sino, por USINA ("3 strings em 2 inversores · 5 trackers"), só para quem tem a tela. O sino nunca espera a
plataforma: vale a cópia de 2 min por pessoa, lida por trás; a falha é tentada de novo depois de 5 min. O número do sino
soma as USINAS, não as strings. Some quando a pessoa abre o inversor (ou os trackers) na Sala. Prova:
`tests/test_sala_novas_sino.py`.
O clique abre a Sala NA usina e nos equipamentos citados (22/11/2026, Levi: "tem que abrir exatamente na usina e nos
equipamentos citados, se não, não serve"): a plataforma manda QUAIS inversores (`inv`) e trackers (`trk`) e o
`sala_novas.link` monta `/t/performance/sala-de-controle?p=/painel/sala-de-controle?usina=&aba=&inv=&trk=`. O destino da
porta vale até 2048 letras: a lista que não cabe sai do link (os trackers primeiro, depois os inversores) e a Sala aponta
o novo da usina pela mesma regra. Quem lê o link é a Sala (`irParaNovo` no `sala_controle.html` da plataforma).

**A Sala de controle lê o que o Monitoramento do COS lê** (16/11/2026; Levi: "A lista de usinas do Monitoramento do COS
[...] puxe a lista"): `GET /t/performance/sala-de-controle/cos/usinas` (as usinas do Monitoramento, pelo
`andamento.ler_geracao` e o `cos.monitoramento._linha`) e `/cos/inversores` (os cartões do SCADA da Ronda COS enxutos, pelo
`andamento.ler_ao_vivo`, 30 s de cópia), em `sala_tela.py`. É a chave do Andamento deste servidor que lê; a tela da
plataforma só pede ao Nexus. Abre para quem tem a tela da Sala, sem depender de ter o Monitoramento do COS. Prova:
`tests/test_cos_monitoramento.py` (os três últimos testes). **E as strings do dia** (16/11, noite; "a leitura das
strings e inversores na API COS > MONITORAMENTO é super rápida [...] aplique"): `/cos/entradas?inv=<logger>:<modbus>&dia=`
devolve o EntradasDoDia da Ronda COS sem mexer, pela mesma `ler_ao_vivo` e as mesmas cópias da janela dos inversores
(60 s hoje, que vai sem o dia; 1 h o dia que passou). A Sala usa na curva de strings das usinas da API PV com logger. Desde 17/11 o `/cos/inversores` manda também `ss`
(o índice e a corrente de agora de cada string): a Sala confere por ele a ligação do inversor antes de usar a curva.

**A janela de criar OS da Sala de controle** (19/11/2026; Levi: "quando tiver deslogado do Fractal, aparecer só um pop-up
só um cardzinho no meio para logar, porque ele redireciona para uma aba do OS Creator que eu não consigo voltar para a sala
de comando"; "dobre o tamanho também do card do OS Creator quando abre"; "quando eu selecionasse um item e ele fosse
reconhecido no Fractal, ele também já aparecesse ali no topo do OS Creator"). A Sala abre `/os/performance/criar?...&janela=1
&origem=sala-de-controle...` num iframe dela (frames: a casca do Nexus > a Sala, página da plataforma > a janela). O que o
Nexus faz para ela:
- **O login que cai na janela não leva a pessoa embora.** São duas portas: (a) o Nexus aberto pelo **Fracttal** cuja sessão
  caiu: a ponte `encerrar` → `/entrar` dentro da janela, e o `entrar.html` chama `window.parent.gcSalaEntrar(motivo)` quando
  o pai não é o topo, é da mesma origem e tem a função (senão, troca a janela de cima como sempre); a Sala mostra o cartão
  e abre o Entrar numa janela à parte com `next=/t/_janela/entrou`, que avisa a Sala (`{gc: "nexus-entrou"}`, só para a
  mesma origem) e fecha (`casca.janela_entrou`, no `setor_telas.LIVRES`). (b) O Nexus aberto pela **Microsoft** (ou pela
  senha de administrador) sem o login do Fracttal do OS Creator: o `exige_sessao` manda ao `/os/login`, e o login saía da
  moldura pelo `__osTopo` da ponte, que sobe até a página de baixo da casca, a própria Sala. Agora o `_tela_login` diz
  `em_janela` quando o `next` traz `janela=1` e `origem=sala-de-controle...`, e o login fica na janela, maior (`os-sala`);
  depois de entrar, o `next` volta à criação na mesma janela. **Atenção para a Sala:** no caso (b) o `/os/_nexus/sessao`
  responde `{"ok": true}` (só confere quem entrou pelo Fracttal); quem diz se o OS Creator tem o login do Fracttal é o
  `/os/_nexus/quem` (e-mail vazio = não tem).
- **Maior para ler:** `html.os-sala{zoom:1.5}` (os.css do OS Creator), posto pelo `<head>` do `base.html` só com `janela=1`
  e `origem=sala-de-controle`; a janela do Tempo real e a do prontuário (também `janela=1`) seguem como estavam.
- **Os reconhecidos no topo:** o `perf.js` (`comSugeridosNoTopo`, `avisoDoTopo`) põe os ativos do link que o Fracttal
  reconheceu no topo da tabela (na ordem em que vieram, uma vez: marcar e desmarcar não reordena) e o aviso
  `#sug_topo` no alto da tela; o que não foi achado vai no mesmo aviso, em cor de alerta. No plano de tracker, "Não achei
  ... no de-para de trackers desta usina com o Fracttal" (serve à usina sem de-para e ao id errado numa usina com de-para;
  antes dizia "Não há de-para" mesmo quando só aquele id não batia, 19/11/2026): a lista já é só de estruturas de tracker (o
  `perf_alvos.get_performance_alvos` do plano de tracker devolve o generalizado, os conjuntos e os individuais, nada mais).
  A usina do link que não se acha (`avisoUsinaFalta`, 19/11/2026) também vai no aviso: conferido em produção, a Sala
  mandava "PEII" e o Fracttal tem "Axis - Petrolina 2 - PE"; o perf.js só casa por igual ou contém, nada era escolhido e o
  aviso ficava escondido. A Sala passou a mandar o nome do Fracttal (a "Usina Fractall" do cadastro, o mesmo de-para do
  Criar OS do Tempo real: `/api/os-creator/fractall-usinas` da plataforma).
- Prova: `tests/test_sala_janela_19_11.py` (o Entrar e o recorte dos sugeridos rodados no node).

## Limitações de potência (19/11/2026; `nexus/campo/limitacoes.py`, `limitacoes_tela.py`, `performance/limitacoes.html`)

Levi, 19/11/2026: "crie [...] um campo onde as pessoas consigam colocar limitações de potência dos inversores. E aí vai
ser usado também para o cálculo dos expurgos. Aí aquela limitação de potência pode ser de todos os inversores ou só de
alguns, de acordo com os inversores do fractal". Nasceu na Usinas 360° e, na mesma noite, veio para cá: "limitação de
potência quero na parte de performance e quero algo bem feito e construído!". É o 1º pedaço dos expurgos de contrato (os
outros: o cálculo na nota do contrato e o cruzamento com a planilha de tickets).

- **A tela** (`/t/performance/limitacoes`, logo depois de Disponibilidade; `do_setor=PERFORMANCE`). De cima para baixo:
  o parecer numa frase (`limitacoes.resumo`: quantas em andamento, em quantas usinas, inversores, kW retidos, o que vai
  para o expurgo e o que está sem a potência); cinco cartões (em andamento, usinas, inversores, potência retida agora,
  sem potência informada, este em âmbar quando > 0); o painel "Registrar uma limitação" FECHADO (abre pelo botão do alto,
  pela usina escolhida, por `?editar=` ou quando a gravação foi recusada); as usinas em andamento, a de mais kW retidos
  primeiro, cada uma com o MAPA dos inversores do Fracttal (`mapa_da_usina`: o aceso está limitado agora, com o %) e a
  tabela das limitações; as encerradas num `<details>` fechado no fim.
- **O formulário**: escolhida a usina (GET `?usina=`), os inversores do Fracttal viram quadrinhos clicáveis (família
  INVR da dimensão de equipamento, `estrutura_usina.ativos_da_usina`, a mesma régua de código que a disponibilidade usa);
  o que já tem limitação em andamento vem tracejado com "já limitado desde dd/mm (pct%)". "Todos os inversores" apaga a
  escolha um a um. A conta da potência retida aparece enquanto se digita (`static/limitacoes.js`, só prévia; a que vale
  é a do servidor). Responsabilidade em três botões: "Não · expurgo", "Parcial", "Sim · da Grid". O "!" ao lado do
  título explica cada campo.
- **Os campos** são os da aba "Inv. com lim. de potência" da planilha de tickets (90 linhas, parada desde 09/2026), para o
  time trocar a planilha pelo Nexus: inversores, potência nominal de cada um (kW), limite em % da nominal liberado, causa,
  responsabilidade da Grid Co. (sim, não, parcial: é ela que decide o expurgo), clipagem (a "Gravidade" da planilha),
  início, fim (vazio = segue limitado) e os comentários para o cliente e geral.
- **O livro** `nexus_limitacao_inversor · fato_versao_limitacao` (no catálogo antes da 1ª gravação; só cresce): 1 linha =
  1 versão (registrou, alterou, encerrou, excluiu); vale a última de cada `limitacao_id`. A causa, os comentários e o nome
  de quem registrou vão cifrados (regra 8). O mesmo envio duas vezes não duplica (`novo_id`).
- **Quem registra**: quem entrou com o login (Fracttal ou Microsoft); a senha de administrador não diz quem é, e o
  formulário fica desligado com o aviso.
- **Sem a potência nominal** a limitação é guardada, mas não entra no cálculo do expurgo (a lista mostra "sem a
  potência", o cartão conta); nada de potência inventada. A potência AC nominal por inversor não existe no Nexus (só o
  kWp DC da Base › Equipamentos, e ligado ao código do Fracttal em poucos inversores).
- **Para o expurgo**: `limitacoes.no_periodo(usina_id, inicio, fim)` devolve as que tocam o período, com `kw_limitados`
  (nominal × inversores × (1 − limite)).
- Sem banco, a tela abre e diz o que faltou. Prova: `tests/test_campo_limitacoes_19_11.py` (banco de mentira). Bancada
  local com dado de mentira: `limitacoes_bancada.py` no scratchpad da conversa (porta 5107).

## Metas das usinas (protótipo de 25/11/2026; `metas_tela.py`, `nexus/performance/metas_pvsyst.py`, `performance/metas.html`)

Levi, 24/11/2026: "É por eles [os PVsyst] que a gente preenche as metas [...] das usinas que não são da Thopen [...] a
ideia seria a gente anexar esses PVSys e já preencher automático na meta"; e, vendo o protótipo (25/11): editar com o
registro das edições, entrada manual, "que nem no Excel, a pessoa pegar e colar", e "todas as colunas [...] centralizadas,
horizontal e verticalmente".

- **De onde vem**: o PDF do PVsyst (pypdf), a tabela "Balances and main results" e o resumo P50/P70/P90. Energia em kWh ou
  MWh (Iramaia II vem em kWh, Gravatá em MWh): tudo vira kWh. Conferências: soma dos 12 meses = linha do ano = P50 do resumo.
- **A conta** (o formato da aba Info Mensal): P50 = E_Grid; P90 = P50 × (P90 ÷ P50 do ano); P75 = P50 − (P50 − P90) ×
  0,6745 ÷ 1,2816; PR do mês; IPOA = GlobInc; GHI = GlobHor. Ano 1 do PVsyst, sem degradação. Sem P90 no relatório, P90 e
  P75 ficam vazios (não se inventa).
- **A grade**: 12 meses × 6 campos, cada célula um campo de texto (pt-BR, PR em %). Colar com tabulação/quebra espalha para
  a direita e para baixo a partir da célula; texto que não é número fica como estava e é dito. Célula editada ganha borda
  (contra o que se abriu). Embaixo, em cinza, a meta de hoje da Info Mensal (meta, NÃO o realizado), com a diferença acima
  de 2%. A Info Mensal e a Info Geral são lidas uma vez e guardadas 10 min (`meta_atual`).
- **Salvar**: o P50 é obrigatório nos 12 meses; kWp do PVsyst > 5% diferente do da Info Geral pede confirmação. Cada Salvar
  entra no registro: quem, quando, origem ("PVsyst", "PVsyst editado", "manual") e cada valor de quanto para quanto.
- **Onde fica**: `<pasta de dados>/metas_pvsyst/metas.json` + `pdf/<sha>.pdf`, uma meta por usina. NÃO é livro do banco
  (livro é para sempre: o formato espera a validação), e a Sala de controle e o Gerencial seguem com a Info Mensal até lá.
- **Fora**: usinas da Thopen (a Thopen manda a própria meta no banco).
- Prova: `tests/test_performance_metas_pvsyst_25_11.py` (relatório inventado; o texto do PDF é dublado na rota).

## ETMs (24/11/2026, vieram da Engenharia; a tela é de 26/10/2026)

Levi, 24/11/2026: "a parte de ETM agora vem para performance. Então, toda a parte de engenharia ETMs, eu quero que você
traga para dentro da performance". A tela mora em `etm_tela.py` e `templates/performance/etm.html`; a regra segue em
`nexus/engenharia/etm.py` (a leitura do Fracttal), `etm_marcas.py` (o livro `nexus_engenharia_etm`, nome que não muda) e
`etm_historico.py`; a página da OS de ETM é a da Engenharia (`torres/engenharia._pagina_da_os`, uma só para o Quadro, o
Garantias e as ETMs). O endereço antigo `/t/engenharia/etm/...` responde 308 para cá, e a marca de "engenharia/etm" em Base
→ Acessos vale para "performance/etm" (`setor_telas.RENOMEADAS`). O que mudou na vinda:

- **Quem age** (as marcações, o Finalizar em lote): o setor Performance e o administrador (`torres/engenharia._quem_pode_etm`;
  até 24/11 eram a Engenharia e o administrador). A Engenharia com a tela marcada lê. Os textos de dono dizem Performance
  ("Abertas para a Performance", "Finalizar pela Performance", "Marcações da Performance"); o grupo **Engenharia / Chamados /
  Campo** do filtro Tipo de trabalho não mudou: é o setor de quem está com a OS no Fracttal.
- **A cópia em disco** (Levi: "Não está salvando na tela as ETMs que carregaram. Então, toda vez que sai e volta, lê o
  fractal tudo de novo e dá uma recusa de leitura do fractal. Tem que ver como é que o OS Creator está fazendo com a parte de
  histórico"). Causa: a cópia era só da memória e o servidor reinicia a cada push (~10 por dia útil); a 1ª pessoa depois de
  cada reinício esperava as 15 páginas na hora, no meio das leituras de subida dos outros, e o Fracttal recusava. Agora, no
  molde do OS Creator (`os_central`/`os_disco`) e das OS de falha: `<pasta de dados>/performance/etm.json.gz` depois de cada
  leitura boa (troca de uma vez), lida na subida sem pedido ao Fracttal, com a idade de verdade; com cópia, a tela nunca
  espera o Fracttal (relê por trás) e a recusa vai para o canto da hora ("releitura das HH:MM recusada pelo Fracttal; mostrando a cópia guardada"), sem esconder a tela. A cópia de outro dia mostra a data. Arquivo ilegível ou de outro formato é ignorado.
- **A volta da OS relê só ela**: depois de trocar o responsável, a página da OS volta com `?releia=<nº>` (`etm.reler_os`: um
  pedido, `work_orders?wo_folio=`), em vez do `?atualizar=1` que relia as 15 páginas na hora. A recusa dessa OS deixa a
  cópia como estava e a tela diz. O `?atualizar=1` (o histórico do app trazido) relê tudo por trás.
- **Abre nas Estações em Aberto** (Levi: "Eu queria que sempre começasse com estações em aberto"): a aba é a primeira e a
  vista nova começa nela. Quem VOLTA (da página de uma OS de ETM, o voltar do navegador, o F5, a volta que relê) cai onde
  estava; quem ENTRA pelo menu ou por um link começa do zero (`voltou()` no JS).
- **Comentar nas ETMs da usina** (Levi: "a gente consiga também até comentar nas ETMs daquela usina"): o quadro da usina nas
  Estações em Aberto tem o **Chat da usina** (a gaveta do Histórico), e a gaveta tem a caixa **Comentar na OS**: a lista das
  OS da usina (as abertas para a Performance primeiro, sem as canceladas), o texto e o Comentar, pelo MESMO caminho da
  página da OS (`/os/_nexus/engenharia/os/<wid>/comentar`: a nota da OS na sessão do Fracttal da pessoa e o livro
  `nexus_engenharia_os`; OS fechada fica só no Nexus, e a resposta diz). Quem não comenta na página da OS
  (`_quem_pode_na_os`) lê o chat sem a caixa. O `de` do login do Fracttal pode ser `/t/performance/etm`
  (`oscreator/ponte._PAGINA_DA_OS`).
- **A 2ª rodada (25/11/2026, no print das Estações em Aberto)**, o que vale hoje no lugar do que diz abaixo:
  - **os filtros** no modelo do Histórico de OS do OS Creator (Levi: "padronizar ali com os filtros do histórico de OS do OS
    Creator [...] o filtro que você expande"): a barra com a busca, o botão Filtros (com quantos estão aplicados) e as
    etiquetas dos aplicados (o × tira aquele); o painel suspenso com os seletores e o período, o Aplicar fecha e o × (ou o
    Esc) desfaz o que mudou desde que abriu. A coluna da esquerda, o "Mostrando N OS" e os textos de ajuda saíram (Levi:
    "essa porcaria só pesa os olhos"; "ninguém vai ler"), o rodapé do Planner também;
  - **as Estações em Aberto em duas visões** (Levi: "a visão das várias OSs [...] e a visão em si das ATMs"): **ETMs**, os
    cartões enxutos (o nome numa linha que só quebra entre palavras, o cliente e as OS na 2ª, o tempo em aberto embaixo;
    antes o selo ao lado espremia o nome letra a letra) com as em acompanhamento abaixo; **OS**, o quadro das OS abertas
    para a Performance. A visão fica guardada (`vista.abModo`);
  - **a gaveta da usina** (Levi: "quando eu clico no quadrado da ATM, ele filtra direto e eu não consigo voltar"): o clique
    no cartão abre a gaveta; fechar (×, Esc, o véu) volta aos cartões. Nela: o cabeçalho (ETMs, OS, abertas, a mais antiga),
    **Nova demanda**, **Finalizar pela Performance** e **Todas as OS** (o Histórico da usina), a caixa **Comentar na OS** e a
    **linha do tempo** em ordem cronológica, a mais nova primeiro: a OS aberta, a finalizada no Fracttal, a encerrada pela
    Performance e os comentários (o `iso` do comentário vem do `/etm/usina/comentarios`). O Chat da usina do Histórico abre
    a mesma gaveta; quem volta (da OS, da demanda, o F5) com ela aberta a vê abrir de novo;
  - **a Nova demanda** (Levi: "alguém da performance poder passar para outra pessoa da performance"): a da Caixa de
    entrada, como a do chamado de Garantias; `/etm/usina/demanda` dá a chave do formulário, as pessoas do setor Performance
    (menos quem pede), os temas da Performance sem os da área Chamados ("Verificação de ativo" já escolhido,
    `etm_tela.TEMA_DA_ETM`), a usina do Nexus e as OS que dá para vincular (as abertas de ETM que o retrato das OS,
    `fato_tarefa_os`, tem: a Caixa recusa OS fora da usina). As listas são as digitáveis do Nexus (`lista-sugestoes.js`). O
    Enviar vai à rota de sempre com `?etm=1` e volta para cá com o aviso (`demandas_tela._no_chamado("etm", ...)`).
- **As demandas na linha do tempo** (25/11/2026, Levi: "Quando eu criar uma nova demanda, vai aparecer também na linha do
  tempo? Tem que aparecer [...] Na linha do tempo da OS"): `etm_tela.demandas_das` pega as demandas da Caixa de entrada que
  citam uma OS de ETM da usina (o `oss` da demanda: a da abertura e as das mensagens) ou a usina do Nexus (pelo retrato das
  OS). Na gaveta (vêm junto do `/etm/usina/comentarios`): quem pediu → para quem, o tema, a situação, o último passo e o
  link para a Caixa. Na página da OS de ETM (`_pagina_da_os`): as que citam aquela OS, na linha do tempo dela. O banco das
  demandas fora não derruba nenhuma das duas: a gaveta diz.
- **Prova:** `tests/test_performance_etm.py` (a cópia, a OS relida, os endereços antigos, o menu, a gaveta, a Nova demanda
  e o JS no node) e os de antes, `tests/test_engenharia_etm*.py`. Bancada local: scratchpad `bancada_etm.py` (OS inventadas).
- **Depois:** a regra (`nexus/engenharia/etm*.py`) ainda mora na pasta da Engenharia, que tem a trava de PR do programador
  da área: mudar de pasta quando a Performance for mexer nela de novo.

### Como a tela era (26/10/2026), no que segue valendo

Levi, com o zip do app de ETM da Engenharia (desktop, FastAPI, um .exe por máquina): "Quero que inclua essa visão de
ETMs no Nexus, engenharia, aba própria. Deixe o design alá Nexus!". No quiz: o histórico do app vem uma vez, e nas OS
em aberto os comentários vão também para a nota da OS; entrega por partes; o comentário da ETM vai para a nota da OS,
como no Quadro da equipe. Desenho em `docs/superpowers/specs/2026-10-26-engenharia-etm-design.md`; plano em
`docs/superpowers/plans/2026-10-26-engenharia-etm.md`.

- **A tela:** `/t/performance/etm` (`etm()`, `performance/etm.html`, do setor Performance), as abas do app no desenho do Nexus
  (Levi, 26/10/2026: "o deploy que te mandei tinham abas só disso!"): **Estações em Aberto**, **Planner**,
  **Histórico** e **Fechamentos**, com a faixa de números em cima. A aba, a usina aberta e os filtros ficam no `sessionStorage` da aba do
  navegador: a volta da OS (`?atualizar=1`) cai no mesmo lugar; o endereço leva a aba (`#historico`, `#abertas`).
- **O Planner:** à esquerda a coluna de filtros do Acompanhamento PCM (Levi, 26/10/2026: "o estilo de lista dos filtros
  está todo bugado e torto, deixe no nível do nexus!" e "tem um espaço livre do lado esquerdo que está sendo mau
  utilizado"): a pesquisa geral, os seletores Cliente, Usina, Tipo de trabalho, Status da OS, Criado por e Responsável
  (a busca, as caixas de marcar com a conta de cada opção com os outros filtros, Selecionar todos e Limpar; o painel
  abre dentro da coluna, que rola sozinha), o período e "Redefinir filtros"; à direita o quadro, com as colunas Não
  iniciadas, Em andamento, Finalizadas e Canceladas (a coluna do quadro levada à do app: a verificação ainda está em
  andamento) e, na coluna Em andamento, os filtros Em andamento e Em verificação (09/11/2026, Levi: "ao invés de 'OS
  em campo', 'Stand By' e 'Validação Final' quero filtros do que está em andamento e o que está em verificação"; a
  `fase` de cada OS: "verificacao" a que está na coluna Em verificação do Quadro da equipe; as etiquetas seguem nos
  cartões). **O clique filtra** (Levi: "não precisa desse botão
  "aplicar" clicou já filtrou!"): a caixa marcada vale na hora e o painel fica aberto, na mesma busca e rolagem; nada
  ou tudo marcado é Todos. O Solicitante saiu ("tire o filtro do solicitante!"; segue na pesquisa geral). A **usina vai
  curta** ("o nome da usina está vindo completo, o ideal seria sem a informação do nome do cliente e estado!",
  `etm.usina_curta`: do "Cliente - Usina - UF" fica o meio; se não sobra nada, o nome inteiro); o filtro guarda o nome
  inteiro, porque duas usinas de clientes diferentes podem ter o mesmo nome curto (aí a opção leva o cliente). O
  **Status da OS** (o do Fracttal: Em Processo, Em Verificação, Concluída, Cancelada) entrou no lugar do "mostrar
  canceladas": sem marcar, as canceladas ficam de fora. Abaixo de 1100 px a coluna sobe para cima do quadro, com os
  seletores em duas colunas. Faixa: Abertas no Fracttal, Abertas para a Performance (a regra das "Estações em Aberto" do
  app: a OS só sai com o diagnóstico ou o finalizado, não quando o Fracttal fecha), Em acompanhamento e Finalizadas em
  30 dias. Sem ler o livro das marcações, a tela diz e as duas contas dele ficam "—".
- **O Histórico** (a visão histórica do app): os clientes, as usinas de cada um (pelas ETMs, com quantas ETMs e OS; a
  usina sem OS também aparece, como no app) e a lista das OS da usina, a mais nova primeiro, com o status do Fracttal,
  as marcações e quantos comentários cada uma tem (contados pelas linhas do `nexus_engenharia_os`, sem abrir a cifra),
  o período, as canceladas e o **Chat da usina** (os comentários da Engenharia em todas as OS dela, numa gaveta, lidos no
  clique pelo `/etm/usina/comentarios`: a cifra abre só para as OS da usina; o comentário cuja cifra não abre, de outra
  chave do cofre, é contado e a gaveta diz). A busca acha a usina em todos os clientes, sem acento nem caixa. Sem a
  coluna de filtros: a navegação é a do app.
- **As Estações em Aberto** (a visão atual do app): as usinas com OS aberta para a Engenharia (a mesma regra da faixa),
  com quantas OS e há quanto tempo (a OS mais antiga; alerta a partir de 7 dias), e as **Estações em Acompanhamento**
  (as usinas com OS marcada Em acompanhamento). A coluna de filtros vale aqui também, menos o Status da OS (a regra é a
  da aba). O clique abre o quadro da usina, com **Finalizar pela Performance** em lote (só quem é da Performance ou
  administrador): as OS da coluna Finalizadas que a pessoa vê, conferidas no servidor (`/etm/finalizar`) na última
  leitura do Fracttal (da usina e finalizadas nele) e no livro (sem diagnóstico nem o finalizado), numa gravação só
  (`etm_marcas.finalizar_lote`); a resposta diz as que já estavam encerradas e as que não estão mais finalizadas. O
  pedido torto (sem a usina, a lista que não é lista, mais de 500 OS) volta 400; enquanto o pedido está no ar o botão
  fica desligado, e a resposta só aparece na usina do pedido. E **Ver histórico desta usina**, que abre a usina no
  Histórico. As duas rotas (`/etm/finalizar` e `/etm/usina/comentarios`) respondem 503 "lendo" com a cópia ainda
  vazia, logo depois de subir: "nenhum comentário" ou "não está mais finalizada" seria mentira. A página só se recarrega sozinha (8 s) enquanto a 1ª leitura está em curso; com o Fracttal recusando ela mostra o erro e para (auditoria de 08/11/2026: a aba esquecida recarregava de 8 em 8 s, cada vez com uma leitura). Sem o livro das marcações, a aba diz e não lista nada
  (não dá para saber o que está aberto para a Engenharia).
- **A leitura** (`nexus/engenharia/etm.py`, medida em 26/10/2026, só leitura): `items?field_1=Estação Meteorológica` dá
  as 172 ETMs (a descrição confere) e `work_orders?items_log_description=Estação Meteorológica` as 1213 OS delas: 15
  pedidos, contra os 172 do app (um por ETM). Fica a OS cujo código é de ETM, uma por número, no cartão do Quadro
  (`os_equipe._cartao`). A usina de cada ETM (`groups_1_description` do ativo) dá as usinas do Histórico; a da OS
  usa o mesmo nome limpo ("Usina não identificada" sem o grupo), senão o espaço dobrado separava uma usina em duas. No teto de páginas a leitura é recusada (um filtro ignorado viraria o Fracttal inteiro). Cópia
  de 5 min, relida por trás enquanto a tela é usada e 270 s depois de subir (`etm.manter_quente`, no `instalar`).
- **Engenharia, Chamados e Campo** (Levi, 26/10/2026: "Engenharia e Chamados vai pelas pessoas dos setores, Campo é o
  restante!"): o setor de quem está com a OS, pelo id do Fracttal, nos setores de Base → Acessos → Pessoas e setores
  (`nexus_setores`, a última decisão de cada pessoa; pelo setor_id, `etm.GRUPO_DO_SETOR`). O grupo **Chamados é o setor
  Performance** desde 13/11/2026 (Levi: "o setor vira performance mas continua na aba chamados"; em 05/11 o setor
  Chamados foi excluído e as pessoas dele foram para a Performance, e o grupo, achado pelo nome, ficou vazio). Cada
  cartão tem o selo (azul, verde, neutro), os três filtram e a faixa conta as abertas de cada um. Sem o banco dos
  setores, a Engenharia vem da lista do Quadro da equipe (pelo nome), Chamados não se separa e a tela diz. Medido em
  26/10/2026: 7 pessoas na Engenharia e 2 em Chamados, 260 OS na tela (54, 1 e 205).
- **Quais OS entram:** a regra do app sem nome no código. Corretivas e Administrativas de ETM, mais as de responsável ou
  solicitante da Engenharia ou de Chamados (o solicitante é texto livre: casa pelo nome do Fracttal das pessoas dos
  setores, `fracttal_pessoal`).
- **A OS de ETM:** `/t/engenharia/etm/os/<nº>`, a mesma página da OS do Quadro (`_pagina_da_os`, uma só para as duas
  telas) com o painel "Marcações da Engenharia" no lugar de Status e prioridade (o diagnóstico e o status pós-OS num
  formulário; a etiqueta, o acompanhamento e o finalizado um botão cada; só a Performance grava, pelo
  `/etm/os/<nº>/marcar`), o "Checklist da OS" (as subtarefas e as respostas, na ordem do Fracttal), as marcações na
  linha do tempo junto dos comentários e os números Diagnóstico, Status pós-OS, Em aberto e Última atualização. A volta
  e a troca de responsável voltam para ETMs; a OS que não é de ETM abre a página comum.
- **O livro das marcações:** `nexus_engenharia_etm` (`nexus/engenharia/etm_marcas.py`; regra no `nexus/dados/CLAUDE.md`),
  um evento por marcação, as listas do app nas três dim. Os comentários são os da OS da Engenharia
  (`nexus_engenharia_os`), que vão para a nota da OS com as mesmas travas do Quadro.
- **O histórico do app, uma vez:** o painel "Trazer o histórico do app de ETM" (só o administrador, no pé da tela) lê o
  repositório privado do app no GitHub (`NEXUS_ETM_GITHUB_TOKEN` e `NEXUS_ETM_GITHUB_REPO` no .env: o nome do
  repositório traz o de uma pessoa), mostra a prévia e grava por trás (`nexus/engenharia/etm_historico.py`; a ponte
  `/os/_nexus/engenharia/etm/historico`, porque a nota vai na sessão do Fracttal de quem importa). Os comentários
  ("**Autor:**\ntexto" no app) entram com o autor e a data de lá (`origem` "app_etm" e o id do comentário); as labels
  viram as marcações atuais, com a data em que foram postas. Nas OS em aberto, os comentários vão para a nota da OS numa
  escrita por OS, do mais antigo ao mais novo; a nota que falha deixa os comentários daquela OS para a próxima. Trazer
  de novo não repete nada (o id no livro e a linha que já está na nota).
- **Segurança:** o Nexus não usa nenhuma credencial do app de ETM: lê o Fracttal com a dele e o GitHub com o token do
  .env.
- **Os Fechamentos** (Levi, 26/10/2026: "Pode fazer a aba Fechamentos por semana, como no app."): quantas OS fecharam
  em cada semana (de segunda a domingo, a conta em UTC para o fuso não mudar o dia), da mais nova para a mais velha,
  com a barra do tamanho de cada semana perto da maior; a semana abre no clique e mostra os cartões, com o dia do
  fechamento. Duas visões, como no app: **no Fracttal** (as finalizadas, pelo dia do fim) e **pela Performance** (o dia
  em que ela encerrou a OS: o diagnóstico ou o finalizado, o que veio por último, de qualquer status no Fracttal;
  `etm_marcas.encerrada_em`, e desligado o finalizado vale o diagnóstico). A coluna de filtros vale aqui, menos o
  Status da OS, e o período passa a ser o da data do fechamento. Sem o livro das marcações, a visão pela Engenharia diz
  e não lista nada.
- **Prova:** `tests/test_engenharia_etm.py` e `tests/test_engenharia_etm_historico.py` (Fracttal, banco e GitHub falsos).
