# CLAUDE.md — torre Performance

| Tela | Estado | De onde vem |
|---|---|---|
| Tempo real, Painel NOC, Diagnóstico, Strings e trackers, Visão gerencial, Disponibilidade, Gêmeo digital, Rondas de Trackers, Comentários (desde 03/11/2026; o Criador de relatório e o Relatório semanal foram para Relatórios → Central de emissão em 13/10/2026; os endereços antigos levam para lá) | a tela da Plataforma de Performance numa moldura (porta única, 09/10/2026): o passe abre a sessão da plataforma e ela desenha a tela, com leitura e gravação. Sem a `NEXUS_SSO_CHAVE`, "Performance ainda não ligada neste servidor"; o Tempo real, nesse caso, cai na ponte de 04/10 (só leitura), se ela estiver configurada. Diagnóstico = seletor de usina (a lista do Painel NOC, lida pelo navegador) e o diagnóstico dela. Sem a faixa "<tela> · Plataforma de Performance" (13/10/2026, "suma esse 2° cabeçalho"): só o Diagnóstico tem a linha, com o seletor. O Painel NOC tem modo TV (11/10/2026): o botão "Modo TV" no topo do Nexus, ao lado do Tema (até 13/10/2026 na faixa), e o `?tv=1` sem a casca, com o mesmo passe e a mesma renovação da sessão da plataforma; a TV dura enquanto valer a sessão do Nexus de quem a abriu (pelo Fracttal, ~12 h a partir do LOGIN), com o prazo à vista nos controles e, na última meia hora, num aviso no canto | as views saem de `registrar_molduras` (`nexus/torres/moldura.py`; `tv={"noc"}` no `__init__.py` daqui), o mapa e o passe de `nexus/performance/porta.py`, os templates `performance/moldura.html` e `performance/moldura_tv.html` e o `nexus/static/porta.js`: leia as seções "Porta única" e "Modo TV do Painel NOC" de `nexus/performance/CLAUDE.md` |
| Clima e risco | alertas públicos por usina (avisos do INMET, focos e risco de fogo do INPE) em três níveis (Agir agora, Atenção, Sem alerta), só leitura, atualiza sozinha (06/10/2026; leitura rápida e página por usina com a irradiação da NASA POWER em 07/10/2026; didática em 09/10/2026: o que fazer, o que pode acontecer, o porquê de cada usina, avisos iguais juntos e "Entenda os alertas", textos em `clima/explica.py`) | `nexus/performance/clima/` (regra), `clima_tela.py` (rotas: a tela e `/clima/usina/<id>`), `nexus/static/clima.css`: leia a seção "Clima e risco" de `nexus/performance/CLAUDE.md` |
| Quadro da equipe (04/11/2026) | o Quadro da equipe da Engenharia clonado para a Performance (Levi: "clone o quadro de equipe da engenharia para o time de performance com as pessoas da performance"; "tira do BASE > ACESSOS > PESSOAS E SETORES"): supercards por pessoa, a faixa de números e o kanban das OS do Fracttal, o mesmo template. A mesma leitura que não some do quadro da Engenharia (10/11/2026: cada pessoa à parte, a última leitura no disco em `quadro_equipe_performance.json.gz`). **A equipe é o setor Performance** de Base → Acessos → Pessoas e setores (a última decisão de cada pessoa, livro `nexus_setores`), pelo id do Fracttal guardado na decisão (sem casar nome; homônimo fora); pessoa do setor que o Fracttal não tem sai em "Não achei no Fracttal: id N". **O clique abre a página da OS da Engenharia** (09/11/2026, Levi: "quando clico na parte de performance não abre a tela personalizada"; até então era o card do OS Creator), `/t/engenharia/equipe/os/<nº>?de=performance`: a página é do chat da Engenharia e não é copiada, para herdar o que ela ganhar (o editar o início e o fim da atividade, o anexo). O `?de=performance` diz de onde a pessoa veio; a volta para este quadro e a passagem do setor Performance pelo portão da página são da Engenharia. **Os Parâmetros** (09/11/2026, Levi: "no estilo de filtros do OS Creator, suspenso porém ao salvar o parâmetro deixa filtrado fixo mesmo que carregue ou reinicie"): depois da busca, o painel suspenso do modelo A do Histórico com Responsável e Etiqueta (listas com busca) e o Salvar; o salvo fica no localStorage do navegador (`kb_parametros_<area>`, um por quadro), some o supercard de quem ficou fora e aparece como etiqueta com × embaixo da barra. A faixa de números do topo segue sendo a da equipe toda. Vale nos dois quadros (o template é um só). **O pulso** da OS aberta parada há mais de 7 dias conta só o Fracttal (a mexida nas tarefas e a criação): a Performance não tem livro de OS. Do setor Performance (`do_setor`): quem é dele vê sem marcar em Acessos. Estado próprio (a cópia de 5 min, o "pronto antes de abrir" de 2 h e a leitura 330 s depois de subir, no `instalar` da Engenharia), separado do quadro da Engenharia | `nexus/performance/quadro_equipe.py` (a leitura, reusa `nexus/engenharia/os_equipe.py`), a rota `equipe()` no `__init__.py` daqui (os supercards e a faixa são os da torre Engenharia), o template `engenharia/equipe.html` com `area="performance"`. Prova: `python -m pytest -q tests/test_performance_quadro_equipe.py` (a rota calcula o pulso com `datetime.now`; o teste para esse relógio em AGORA, senão quebra quando as OS do teste passam dos 7 dias, como em 09/11/2026) |
| Mapa de risco | o Clima e risco num mapa do Brasil (SVG do servidor): estados do IBGE, avisos do INMET, focos do INPE e as usinas na cor do nível; `?regiao=` refaz o recorte; mesmas fontes e mesmo cache da lista (07/10/2026); à direita, a tabela das usinas com o risco e o motivo resumido (09/10/2026); desde 27/10/2026, a tela enxuta: cabeçalho de uma linha com o "!" do como ler (o desenho do aviso dos Extintores), os níveis numa faixa em cima do mapa e os filtros com a chave de cores na lateral esquerda. Desde 09/10/2026: camada de fundo (avisos, risco de fogo ou densidade de focos, em quadrados), camadas de cima, filtros e busca, zoom e dica (`clima-mapa.js`), tela cheia e o modo TV (`?tv=1`, sem a casca, com giro das camadas e releitura no ritmo dos caches); as fontes por extenso. O endereço é `/t/performance/clima/mapa`: o id da `Tela` é `clima/mapa`, com barra | `nexus/performance/clima/mapa.py` e `calor.py` (regra), `mapa_tela.py` (rota), templates `mapa.html`, `mapa_tv.html` e os pedaços `_mapa_*.html`, `nexus/static/clima-mapa.css`, `clima-mapa.js` e `nexus/static/clima/ibge-ufs-minima.geojson` (o contorno, guardado no repositório): leia a seção "Mapa de risco" de `nexus/performance/CLAUDE.md` |

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
