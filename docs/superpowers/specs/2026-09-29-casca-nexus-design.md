# Nexus · Casca (fase 0) · Desenho

**Data:** 29/09/2026 · **Responsável:** Levi Maia · **Repositório:** `Grid-Co-CODE/nexus` (privado)
**Base de produto:** specs R00 a R13 do Fillipe Figueiró (SharePoint `Gridco/4. O&M/6.Gerencial/10. Nexus`).

## 1. Objetivo

Levantar a casca do Nexus: login por senha de admin, menu por torre que se reorganiza pela cadeira
escolhida e telas vazias que dizem o que cada uma vai ser. Nenhuma tela mostra dado de operação nesta
fase.

A casca existe para duas coisas:
1. ser o lugar onde cada torre é plugada sem mexer nas outras (o programador do COS começa pela torre COS);
2. fixar desde o primeiro commit como uma torre se registra, o portão de login e o tema visual.

**Regra de origem de dado (vale para as próximas fases):** o Nexus não lê nenhum arquivo Excel nem nada
do OneDrive. Todo dado vem da API `db_performace` (PostgreSQL da T.I.).

## 2. Fora desta fase

- **Login Microsoft (Entra).** Deixado de lado por decisão do Levi em 29/09. O portão de login é um
  ponto só (`nexus/auth/`), então o Microsoft entra ali depois, sem mexer nas torres.
- Acessos por pessoa (e-mail → cadeira) e o workbook `nexus_estado`: dependem de identidade por pessoa,
  que só vem com o login Microsoft.
- Dado real em qualquer tela (registro mestre, linha do tempo, regras de correlação).
- Deploy no servidor, chave de deploy, GitHub Actions.
- Lista completa de cadeiras do book R02 (o Levi passa depois).

## 3. Estrutura do repositório

```
app.py                      cria o app (create_app) e sobe na porta 5070 em modo local
nexus/
  config.py                 lê o .env, valida as variáveis obrigatórias, aborta o boot se faltar
  auth/                     Blueprint: /entrar, /sair e o portão de login
  casca/                    Blueprint: Início, troca de cadeira, /saude, menu e layout
  cadeiras.py               catálogo de cadeiras (dado versionado)
  torres/
    __init__.py             descobre as pastas de torre e registra cada uma
    modelo.py               classes Torre e Tela, view genérica de placeholder
    comando/ cos/ pcm/ performance/ engenharia/ chamados/ contratos/ relatorios/
    pessoas/ campo/ hseq/ base/        uma pasta por torre
  templates/  static/
tests/
.env.example  .gitignore  requirements.txt  CLAUDE.md  README.md
```

`.gitignore` cobre `.env`, `__pycache__/`, `.pytest_cache/`, `logs/`.

## 4. Configuração

Variáveis no `.env` (local: máquina do Levi; servidor: `/etc/nexus/nexus.env`, fase de deploy). O
`.env.example` lista só os nomes.

| Variável | Obrigatória | Uso |
|---|---|---|
| `NEXUS_SECRET_KEY` | sim | assinatura do cookie de sessão |
| `NEXUS_SENHA_ADMIN` | sim | senha de entrada |

`config.py` lê o `.env` ao lado do `app.py` (caminho absoluto a partir do próprio arquivo), confere a
lista no boot e, se faltar uma obrigatória, o processo não sobe e a mensagem diz o nome da variável
(nunca o valor). Motivo: o coletor já ficou sem credencial em silêncio depois de uma mudança de pasta, e
ninguém percebeu até a coleta falhar.

## 5. Autenticação

- `/entrar` (GET mostra o formulário, POST confere). Comparação com `hmac.compare_digest`.
- Limite de tentativas: 5 erros por IP em 15 minutos bloqueiam novas tentativas daquele IP até a janela
  passar (em memória; zera no restart, aceitável para uma casca).
- Sessão: cookie `HttpOnly`, `SameSite=Lax`, `Secure` fora do localhost, validade de 12 h.
- **Portão:** `before_request` exige sessão em toda rota, exceto `auth.entrar`, `casca.saude` e `static`.
  Sem sessão, redireciona para `/entrar?next=<caminho>`; o `next` só é aceito se for caminho relativo
  do próprio site (evita redirecionamento aberto).
- Quem entra pela senha é **admin**: vê todas as torres e escolhe em qual cadeira "sentar".
- Não existe modo sem login, nem em desenvolvimento.

## 6. Cadeiras e menu

**Catálogo** (`nexus/cadeiras.py`), com as dez cadeiras da spec R06 e a torre inicial de cada uma:

| id | Cadeira | Torre inicial |
|---|---|---|
| `dir` | Diretoria de Operações | Comando |
| `head` | Head de Operação de Ativos | Comando |
| `ctr` | Coordenador de Operação e Contratos | Contratos e clientes |
| `sct` | Supervisor de Contratos | Contratos e clientes |
| `cos` | Supervisor do COS | COS |
| `op` | Operador do COS | COS |
| `man` | Coordenador de Manutenção | Campo · App |
| `scp` | Supervisor de Campo | Campo · App |
| `pcm` | Coordenador de PCM | PCM |
| `perf` | Coordenadora de Pós-Operação — Performance | Performance |

Cadeira nova entra no fim da lista; id publicado nunca muda.

**Sentar na cadeira:** seletor na barra superior (`POST /cadeira`), guardado na sessão. Sem cadeira
escolhida, o menu segue a ordem do catálogo de torres.

**Menu:** o **Início é um botão** fixo no topo (link direto para `/`, sem sub-itens; pedido do Levi em
29/09: uma torre "Início" cujo primeiro sub-item era o próprio Início não fazia sentido). Abaixo dele, a
torre inicial da cadeira, expandida e marcada como "sua"; as demais recolhidas, na ordem do catálogo. A
torre da tela atual também fica expandida.

**Recolher:** botão na barra superior (e tecla `[` fora de campos de texto) alterna o menu entre
expandido (256 px) e um trilho de 64 px só com os ícones; o nome da torre aparece ao passar o mouse, e o
clique no ícone leva à primeira tela da torre. O estado fica em `localStorage` `nexus.menu` (lido antes
de pintar, para não piscar). No celular não se aplica: lá o menu fica atrás do botão Menu.

## 7. Torres

Cada pasta em `nexus/torres/` expõe `TORRE` (id, nome, ordem, telas) e um Blueprint com prefixo
`/t/<id_torre>`. `torres/__init__.py` percorre as pastas e registra todas; torre nova não pede mudança
em outro arquivo. Tela sem view própria cai na view genérica de placeholder: nome, pergunta que responde,
fonte prevista e "em construção".

Telas iniciais (placeholder), tiradas das specs R01 a R13:

| Torre | Telas |
|---|---|
| Comando | Sala de comando, Caixa de entrada, Kanban, Nexus Insights, Usinas, Metas do book |
| COS | Mesa do operador, Ocorrências, Ronda padronizada, Acionamentos e distribuidoras, Desempenho da equipe, Parede de eventos, Religamentos, Passagem de turno |
| PCM | Semana, Insights, Tarefas e OS, Chamados por etiqueta, Gestão PCM, Disponibilidade, PCM 52 Semanas, Torre de controle, Peças e sobressalentes |
| Performance | Tempo real, Painel NOC, Diagnóstico, Strings e trackers, Visão gerencial, Criador de relatório, Gêmeo digital |
| Engenharia | Confiabilidade, Matriz de criticidade, FMEA e causa raiz, Laudos MPS/MPA |
| Chamados | Fabricantes, Tickets de performance, Clientes, Garantias |
| Contratos e clientes | Clientes, Onboarding de cliente, Comunicação por cliente, Portal do cliente |
| Relatórios | Central de emissão |
| Pessoas | Plantão e sobreaviso, Escala de sobreaviso, Equipes e capacidade, Cadeiras e RACI, Academy, Lições aprendidas |
| Campo · App | Central de atenção, Aprovação de OS, Ordens de serviço, Rondas, Ranking, Triagem de qualidade, Imagens da ronda, Rotas do dia |
| Segurança · HSEQ | Riscos, APR e PT, DSS, Incidentes |
| Base | Registro mestre, Integração Fracttal, Nexus IA, Notificações, Estrutura R02, Como usar o Nexus, Visão e roadmap |

## 8. Rotas

| Rota | Quem | O quê |
|---|---|---|
| `/` | logado | Início (da casca) |
| `/t/<torre>/<tela>` | logado | tela da torre |
| `/cadeira` (POST) | logado | sentar em outra cadeira (só na sessão) |
| `/entrar`, `/sair` | todos | login por senha |
| `/saude` | público | `{"ok": true, "commit": "<hash curto ou 'local'>"}`, sem mais nada |

## 9. Visual

Segue o Design System Grid Co. (tokens `gc-*`, tema escuro):
- fundo `#090d18`, blocos `#161d30`, `superficie-2` `#1c2640`, hover `#243154`, barra `#0d1526`;
  verde Grid `#a3d900` só como superfície, `verde-texto` `#c4e755` para texto verde. Nunca lilás; o
  navy arroxeado do mockup (`#191528`) não é usado.
- Raleway nos títulos, Poppins na interface, IBM Plex Mono em códigos e carimbos.
- Logotipo `grid-h-branco.png` na barra (copiado de `plataforma/static/logos/`).
- Sem emoji; severidade por cor e palavra. Todo texto em pt-BR, comentários de código também.
- Barra superior: marca Grid Co. + Nexus, seletor de cadeira, Sair. Menu lateral por torre; abaixo de
  820 px o menu vai para cima da página.
- Sem animação decorativa; `prefers-reduced-motion` respeitado.

## 10. Testes

`python -m pytest -q`, com o cliente de teste do Flask:

1. nenhuma rota fora da lista pública abre sem sessão (percorre o `url_map` inteiro);
2. senha errada não abre sessão; a sexta tentativa errada do mesmo IP é bloqueada;
3. `next` externo é recusado depois do login;
4. todas as pastas de torre são registradas, e cada tela do catálogo responde 200 logado;
5. boot falha, com o nome da variável, se faltar uma obrigatória;
6. o menu põe a torre inicial da cadeira no topo; o Início é link direto, sem grupo; o botão de recolher existe;
7. cadeira inexistente no `POST /cadeira` é recusada;
8. `/saude` responde sem sessão e não expõe nada além de `ok` e `commit`.

## 11. Critérios de pronto

- `python app.py` sobe em `http://localhost:5070` com o `.env` preenchido e falha claro sem ele.
- Os testes passam.
- Validado no navegador: login, troca de cadeira mudando o menu, abrir uma tela de cada torre, celular.
- `CLAUDE.md` do repositório com as convenções (pt-BR, sem emoji, navy, comentário explica o porquê,
  segredos fora do git).

## 12. Decisões em aberto

1. Quando o login Microsoft volta, e com ele os acessos por pessoa (a decisão já tomada: estado no
   workbook `nexus_estado` da API, com o e-mail guardado como HMAC, porque dado pessoal não vai em claro para a API).
2. Endereço no servidor (subdomínio próprio ou caminho em `app.gridco.com.br`). Atenção ao Caddy.
3. Lista completa de cadeiras e se cada cadeira vê só as torres dela ou todas (hoje: todas).
