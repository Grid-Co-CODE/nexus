# CLAUDE.md — torres (uma pasta por área do menu)

Cada pasta em `nexus/torres/` é uma torre do menu lateral. Torre com regra própria tem o seu `CLAUDE.md` (ou
`README.md`) na pasta: **leia antes de mexer**.

| Torre | Estado | Onde está a regra |
|---|---|---|
| `cos/` | em construção pelo dev do COS; o Acompanhamento COS é a tela `/cos` da plataforma numa moldura (porta única) | `cos/CLAUDE.md` |
| `oscreator/` | clone do OS Creator Web servido em `/os/*` | `oscreator/README.md` |
| `performance/` | as telas da Plataforma de Performance (Tempo real, Painel NOC, Diagnóstico, Strings e trackers, Visão gerencial, Disponibilidade, Criador de relatório, Relatório semanal, Gêmeo digital, Histórico da plataforma, Monitor da ronda) numa moldura com o passe da porta única (09/10/2026); Clima e risco e Mapa de risco = alertas públicos por usina (INMET e INPE), só leitura | `nexus/performance/CLAUDE.md` (seção "Porta única") |
| `pcm/` | telas da programação semanal e a Gestão PCM (Plano & Fila das manutenções, do painel do PCM) | `nexus/pcm/CLAUDE.md` (o código mora em `nexus/pcm/`) |
| `base/`, `pessoas/` | telas do cadastro (BD_Operações); Base → Governança de dados é da camada de dados | `nexus/cadastro/CLAUDE.md`, `nexus/dados/CLAUDE.md` |
| `campo/` | Visão do Nexus sobre o campo, sem Azure nem moldura: Atenção, PT, Rondas e Zeladoria são contas nossas (`nexus/campo/visao.py`); Aprovação e Triagem usam as regras copiadas do App; tudo pelos livros que o App grava no banco (Ordens, Imagens e Ranking saíram em 08/10/2026) | `campo/CLAUDE.md` |
| `hseq/` | Extintores (09/10/2026): vencido, perto de vencer e sem conferência há mais de 30 dias, por usina e dia, por supervisor de campo e por gestor de contrato, com o relatório em PDF; EPI e EPC: as luvas isolantes pela ronda diária; APR e PT: as Permissões de trabalho (vieram do Campo em 09/10, o código continua lá), com a PT e a APR; as outras telas placeholder | `hseq/CLAUDE.md` (as contas moram em `nexus/hseq/`) |
| as demais | só placeholder | — |

## Como funciona

- `__init__.py` da torre declara `TORRE` (`modelo.Torre` com as `Tela`s) e `bp = TORRE.criar_blueprint(__name__)`.
  `nexus/torres/__init__.py` descobre a pasta sozinho (`pkgutil`); não há lista para editar.
- Toda tela nasce como placeholder genérico. **Para construir uma tela**, crie a view no `bp` da torre com a mesma
  rota (`@bp.route("/mesa")`): a específica vence o placeholder, e a tela fica verde no menu sozinha.
- Templates em `nexus/torres/<torre>/templates/<torre>/`.
- **Endereço nunca a partir da raiz** (09/10/2026): no servidor o Nexus mora em `/nexus` (`NEXUS_PREFIXO`), e um
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
- **Tela da Plataforma de Performance numa torre** (porta única, 09/10/2026): declare a `Tela` na `TORRE` com o id do mapa (`nexus/performance/porta.py`, `MAPA`) e chame `registrar_molduras(bp, TORRE)` (`nexus/torres/moldura.py`) depois do `criar_blueprint`; a view, o passe, o `?p=`, o item que acende e a rota do passe novo (`/t/<torre>/<tela>/passe`, que renova a sessão da plataforma: auditoria A5, 10/10/2026) vêm de lá. Tela nova no mapa muda também a cópia da plataforma (`plataforma/porta_nexus.py`) e o texto canônico dos dois testes. `moldura.py` é um módulo solto em `nexus/torres/`, como o `modelo.py`: a descoberta só olha os pacotes, então ele não vira torre.
- `montar_menu` põe a torre da cadeira escolhida primeiro.
- O módulo-modelo chama `modelo.py`, não `base.py`: `base` colidia com o pacote da torre Base.
