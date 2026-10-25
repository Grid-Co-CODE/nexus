# CLAUDE.md — torres (uma pasta por área do menu)

Cada pasta em `nexus/torres/` é uma torre do menu lateral. Torre com regra própria tem o seu `CLAUDE.md` (ou
`README.md`) na pasta: **leia antes de mexer**.

| Torre | Estado | Onde está a regra |
|---|---|---|
| `cos/` | em construção pelo dev do COS; o Acompanhamento COS é a tela `/cos` da plataforma numa moldura (porta única) | `cos/CLAUDE.md` |
| `oscreator/` | clone do OS Creator Web servido em `/os/*` | `oscreator/README.md` |
| `performance/` | as telas da Plataforma de Performance (Tempo real, Painel NOC, Diagnóstico, Strings e trackers, Visão gerencial, Disponibilidade, Gêmeo digital, Rondas de Trackers) numa moldura com o passe da porta única (09/10/2026); Clima e risco e Mapa de risco = alertas públicos por usina (INMET e INPE), só leitura | `nexus/performance/CLAUDE.md` (seção "Porta única") |
| `pcm/` | telas da programação semanal, a Gestão PCM (Plano & Fila das manutenções, do painel do PCM) e o Acompanhamento PCM (14/10/2026: MPA, MPS, Radar de Backlog, Mapa e One Page do painel de acompanhamento do PCM O&M, do setor PCM; `nexus/pcm/acompanhamento`) | `nexus/pcm/CLAUDE.md` (o código mora em `nexus/pcm/`) |
| `base/`, `pessoas/` | telas do cadastro (BD_Operações); Base → Governança de dados é da camada de dados; Base → Acessos (quem é administrador, 11/10/2026) é do login | `nexus/cadastro/CLAUDE.md`, `nexus/dados/CLAUDE.md`, `nexus/casca/CLAUDE.md` (seção Acessos) |
| `campo/` | Visão do Nexus sobre o campo, sem Azure nem moldura: Atenção, PT, Rondas e Zeladoria são contas nossas (`nexus/campo/visao.py`); Aprovação e Triagem usam as regras copiadas do App; tudo pelos livros que o App grava no banco (Ordens, Imagens e Ranking saíram em 08/10/2026) | `campo/CLAUDE.md` |
| `hseq/` | a Mesa da Segurança (24/10/2026, a primeira, do setor Segurança: PT parada, extintor vencido e não reconhecido, usina sem luvas, e os de atenção, em cartões por responsável ou por cliente; a visão geral da TST com os filtros de cliente, UFV e Responsável UFV e a planilha de todas as pendências); Extintores (09/10/2026): vencido, perto de vencer e sem conferência há mais de 30 dias, por cliente (com o responsável e os técnicos de cada usina; 18/10/2026) e por responsável, com o relatório de cada cliente e usina em PDF e Excel nos três pontos da linha, com o Status por situação e o filtro de Status, e a Segurança decidindo na usina (24/10: o Aceitar do não reconhecido e o botão direito excluem o extintor, que vai para o histórico de Excluídos; nova ronda da usina nos três pontos); EPI e EPC: as luvas isolantes pela ronda diária, por responsável da usina; APR e PT: as Permissões de trabalho (vieram do Campo em 09/10, o código continua lá), com a PT e a APR; as outras telas placeholder | `hseq/CLAUDE.md` (as contas moram em `nexus/hseq/`) |
| `relatorios/` | a Central de emissão (13/10/2026): os relatórios do setor de quem entrou (todos, para o administrador), cada um uma tela que abre POR DENTRO dela (`Tela.dentro_de`: sem item no menu, acende a Central; quem tem um liberado vê a Central sem marcá-la). Hoje os três da Plataforma de Performance, na moldura: Criador de relatório, Relatório semanal (vieram da Performance) e Potência Ativa dos Inversores, os três DO setor Performance (`Tela.do_setor`: quem é da Performance os vê sem marcar; outro setor, pela marca em Base → Acessos) | docstring de `relatorios/__init__.py`; o mapa em `nexus/performance/CLAUDE.md` (seção "Porta única") Os quatro do PCM (14/10/2026: diário, tarde, fechamento e alerta) são NATIVOS do Nexus, do setor PCM: `nexus/pcm/relatorios` (`telas.registrar`); o Relatório executivo do PCM (Interno Grid, Cliente, Abertura da Semana) é cópia do JS do painel numa moldura, também do setor PCM: `nexus/pcm/relatorio_exec` (`registrar`). O setor dono de cada relatório se escolhe na própria Central, só pelo administrador (14/10/2026, `auth/dono_relatorio.py`). UMA estrutura em toda a Central (14/10/2026, Levi: "Use a mesma estrutura do print 1 para todos os relatórios de todos os setores"): à esquerda os blocos (`BLOCOS`/`lado` em `relatorios/__init__.py`, macro `relatorios/_lado.html`: "Relatórios Padrão PCM", "Relatório Gerencial PCM", "Relatórios Performance"), só com o que a pessoa vê; à direita a folha (PCM) ou a tela da plataforma (`relatorios/moldura.html`, a moldura de `performance/_porta.html` via `registrar_molduras(..., modelo=, extra=)`, sem título do Nexus em cima: o 2º cabeçalho saiu em 13/10/2026). Relatório novo entra num bloco (o teste reprova). |
| `engenharia/` | Mesa do engenheiro (a primeira tela, 18/10/2026: a mesa de cada um, com o que me encaminharam, o que está comigo e os críticos sem dono), Confiabilidade dos ativos (pelas OS de falha do Fracttal), com o acompanhamento dos ativos com sinal desde 18/10/2026 (pegar, encaminhar, diagnóstico, comentários; abas Em acompanhamento, Encerrados e Diagnósticos), e o Quadro da equipe, com a página da OS desde 24/10/2026 (status e prioridade da engenharia, comentários na nota da OS, Solicitar OS com a OS pai, o pulso das paradas); Criticidade, FMEA e Laudos ainda placeholder | `engenharia/CLAUDE.md` |
| `contratos/` | Contestações do cliente (13/10/2026, do Dashboard Thopen, por setor); Clientes, Onboarding, Comunicação e Portal ainda placeholder | `contratos/CLAUDE.md` |
| `chamados/` | Fabricantes e Garantias são atalhos para telas do OS Creator Web (`ponte.ATALHOS`); Solicitações de clientes ainda placeholder | o docstring da torre e `oscreator/README.md` |
| as demais (`comando/`) | só placeholder | — |

## Como funciona

- `__init__.py` da torre declara `TORRE` (`modelo.Torre` com as `Tela`s) e `bp = TORRE.criar_blueprint(__name__)`.
  `nexus/torres/__init__.py` descobre a pasta sozinho (`pkgutil`); não há lista para editar.
- Toda tela nasce como placeholder genérico. **Para construir uma tela**, crie a view no `bp` da torre com a mesma
  rota (`@bp.route("/mesa")`): a específica vence o placeholder, e a tela fica verde no menu sozinha.
- **Tela que sai não vira 404:** tire a `Tela` da `TORRE` (sai do menu e do Início) e deixe a rota respondendo um
  redirecionamento (com `na_raiz`) para a tela que ficou no lugar, para quem tinha o endereço salvo. Caso: Base → Listas
  saiu em 11/10/2026 e o `/t/base/listas` leva à Governança de dados (`nexus/cadastro/CLAUDE.md`).
- Templates em `nexus/torres/<torre>/templates/<torre>/`.
- **Endereço nunca a partir da raiz** (09/10/2026): o Nexus pode rodar debaixo de um prefixo (`NEXUS_PREFIXO`: `/nexus` no servidor até a fase 4; hoje na raiz, e o
  prefixo é a volta), e aí um
  `href="/t/..."`, `redirect("/t/...")` ou `fetch("/os/...")` cru cai na plataforma de Performance. No template,
  `{{ raiz }}/t/...`, `url_for(...)` ou `{{ endereco|na_raiz }}` (o que vem montado do Python); no Python,
  `na_raiz("/t/...")` (`nexus/prefixo.py`); no JavaScript, `nexusRota("/t/...")`. Endereço relativo (`?filtro=...`) não
  precisa de nada. `tests/test_prefixo.py` percorre as telas e varre templates, `.js` e `redirect`: o esquecimento quebra
  o teste. Regra completa em `nexus/casca/CLAUDE.md`, seção do prefixo.
- **Abrir uma OS do Fracttal em qualquer tela** (os setores se conversam, Levi 08/10/2026): o card do Histórico do OS
  Creator, sem cópia. `{% include "oscreator/card_os_abrir.html" %}` e `NexusOsCard.abrir(id_work_order, {status})`;
  regra em `oscreator/README.md` ("O card da OS em qualquer torre"). Quem usa: o Quadro da equipe da Engenharia. Para o
  card já estar lido quando a pessoa clicar, `NexusOsCard.prepararAoParar(elemento, id_work_order)` no cartão (o mouse
  parado 250 ms pede a leitura; regras e teto em "O card começa a carregar antes do clique", no mesmo README).
- **Coisa parecida, o mesmo desenho** (Levi, 08/10/2026: "Precisamos padronizar a estética para que coisas parecidas
  não pareçam completamente diferentes"). Quadro de OS (colunas e cartões): o do Quadro da equipe da Engenharia (`kb-*`
  em `nexus/static/engenharia.css`), que o Acompanhamento de chamados do OS Creator já copia. Faixa de números: o modelo
  do Acompanhamento de chamados (rótulo em cima, número colorido pela gravidade, o detalhe ao lado), que o Quadro da
  equipe já usa (`kb-kpis`). Tela nova com quadro ou faixa de números parte de um deles; mudou o desenho num, leve ao
  outro.
- **Tela da Plataforma de Performance numa torre** (porta única, 09/10/2026): declare a `Tela` na `TORRE` com o id do mapa (`nexus/performance/porta.py`, `MAPA`) e chame `registrar_molduras(bp, TORRE)` (`nexus/torres/moldura.py`) depois do `criar_blueprint`; a view, o passe, o `?p=`, o item que acende e a rota do passe novo (`/t/<torre>/<tela>/passe`, que renova a sessão da plataforma: auditoria A5, 10/10/2026) vêm de lá. Tela nova no mapa muda também a cópia da plataforma (`plataforma/porta_nexus.py`) e o texto canônico dos dois testes. Modo TV (11/10/2026, hoje só o Painel NOC): `registrar_molduras(bp, TORRE, tv={"<tela>"})` põe o botão "Modo TV" no topo do Nexus (o bloco `topo_acoes` do `base.html`; até 13/10/2026 na faixa, que saiu) e responde `?tv=1` sem a casca (`performance/moldura_tv.html`), com o mesmo passe e a mesma renovação; não mexe no mapa. A TV dura o que durar a sessão do Nexus de quem a abriu (pelo Fracttal, ~12 h a partir do login; o prazo fica à vista nela): ver "Modo TV do Painel NOC" em `nexus/performance/CLAUDE.md`. `moldura.py` é um módulo solto em `nexus/torres/`, como o `modelo.py`: a descoberta só olha os pacotes, então ele não vira torre.
- **Tela nova que lê o Fracttal ao abrir entra na `FORA` de `nexus/auth/pre_carga.py`** (12/10/2026): a pré-carga
  abre por trás as telas de quem tem setor, e a cota do Fracttal (200/min) é da empresa inteira. Se esquecer, a
  pré-carga anota a tela na 1ª vez, tira ela da volta e o log avisa.
- `montar_menu` mostra só as telas que o setor da pessoa vê (`liberadas`, chaves `torre/tela`; None = tudo) e tira a
  torre sem nenhuma. A cadeira, que punha a torre dela primeiro, saiu em 12/10/2026 (Base → Acessos).
- O módulo-modelo chama `modelo.py`, não `base.py`: `base` colidia com o pacote da torre Base.
