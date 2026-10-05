# CLAUDE.md — Performance (regra da torre, sem Flask)

## Ponte para a Plataforma de Performance (04/10/2026)

A aba Performance → Tempo real mostra a Entrada e o Monitoramento da própria plataforma (Levi: "tudo da plataforma,
só leitura", "em paralelo por enquanto"). Fase 1 de cinco para a plataforma morar 100% no Nexus: ver o spec
`docs/superpowers/specs/2026-10-04-tempo-real-no-nexus-design.md`, seção 10.

- O navegador fala só com o Nexus. `ponte.py` leva o pedido à plataforma com `X-Nexus-Leitura`
  (`NEXUS_PLATAFORMA_TOKEN` = `NEXUS_LEITURA_TOKEN` da plataforma) e `X-Forwarded-Prefix: /t/performance/plataforma`.
  A plataforma devolve as páginas com o prefixo (`_SHIM_PREFIXO` + atributos): a ponte não reescreve HTML, só injeta
  o visual (`#nexus-visual`) e o guarda (`#nexus-leitura`).
- **Só leitura em três camadas:** portão da plataforma (403 com a chave), `pode_passar` aqui, guarda no navegador.
  Os únicos POSTs: `POSTS_DE_CONSULTA` (a mesma lista do `leitura_nexus.py` da plataforma — mudou lá, muda aqui).
- **Os parâmetros que disparam trabalho saem de todo pedido** (`PARAMETROS_QUE_DISPARAM`: `force`, `forcar`, `run`, `backfill` — a mesma lista do `leitura_nexus.py` da plataforma, que recusa esses nomes com a chave): o "Atualizar" das páginas leria a SunOp na hora (cota). Pelo Nexus, lê-se o que o motor já montou.
- **A API PV fica de fora, por enquanto** (Levi, 05/10/2026: "por hora não puxa nada da API da thopen, estou tentando
  economizar requests e tenho medo que duplique as chamadas"). A API PV (`*.pvoperation.com*`) atende Thopen, SEMP, Alves
  Lima e 2C-API. O detalhe que abre a usina nela na hora (`NEGADOS_API_PV`: inversores da usina, drill/curva/CSV de
  trackers, a lista de trackers de SEMP/Alves Lima/2C, strings de uma usina, curva da estação) é 403 com `AVISO_API_PV`
  e nem sai do Nexus; o que a plataforma já tem guardado (tabela, lista de trackers da Thopen, acervo) passa. A
  plataforma faz o mesmo do lado dela (`leitura_nexus.NEGADOS_API_PV`, mesma lista) e, além disso, não fala com a API PV
  em pedido do Nexus nem monta cache por ele (`instalar_trava_api_pv`, `_swr`, Entrada) — prova com a rede cortada em
  `tests/test_nexus_sem_api_pv.py` da plataforma. Para liberar depois: tirar a rota das DUAS listas.
- **Caminho com "?" ou "#" é recusado (400)**: o Flask decodifica `%3F`/`%23` dentro do caminho, e a query escondida passaria por fora do filtro. O caminho à plataforma sempre começa com "/" (com `@host` sem barra, a chave iria para outro servidor).
- **Cabeçalhos em qualquer caixa**: `ajustar_resposta` casa por minúsculo e devolve os nomes canônicos; sem isso, um `content-type` minúsculo (Cloudflare, HTTP/2) mandaria o HTML sem o guarda.
- Não passa `Set-Cookie` nem o cookie do Nexus; tempo-limite 150 s (o drill da API PV leva até 120 s).
- **No máximo 4 pedidos ao mesmo tempo** (`_VAGAS`, espera de 2 s, depois `Ocupada` → 503 "Ponte ocupada"): cada pedido
  segura uma thread do Nexus por até 150 s, e sem teto uma plataforma lenta esgota as threads e trava a casca inteira.
  A vaga volta num `finally`; uma única `requests.Session` (`_SESSAO`) reaproveita a conexão.
- **Salto (3xx) só no mesmo servidor, até 3** (`allow_redirects=False` no pedido; `enviar` segue sozinha): o `requests`
  seguiria para qualquer host levando `X-Nexus-Leitura`. Outro esquema/host/porta → `RedirecionamentoRecusado`
  (`ForaDoAr`); salto para `/login` volta como está e a rota diz "a plataforma recusou a chave" (sem sessão e sem a chave
  valendo, a plataforma manda o pedido para o login dela). `NEXUS_PLATAFORMA_URL` com `http://` fora de
  localhost/127.0.0.1/::1 é recusada antes de qualquer rede: a chave iria em texto puro.
  `Location` com `\`, espaço ou controle é recusada (crua, antes do `urljoin`, que engole tabulação) e a origem é
  conferida pela URL que o `requests` vai usar (`Request.prepare()`, lida pelo `urllib3.parse_url` E pelo `urlparse` do
  adaptador do requests 2.34; se os dois discordam, recusa), não pelo `urlsplit`
  (04/10/2026: `//evil.com\@plat/x` passava pelo `urlsplit` e o urllib3 conectava em evil.com, com a chave). URL
  malformada (porta inválida, colchete solto: o `urljoin` do Python 3.14 levanta `ValueError`) é
  `RedirecionamentoRecusado`, nunca `ValueError`/500. A exceção traz o `motivo` (outro servidor, redirecionamentos
  demais, endereço inválido) e a rota o mostra.
  **O `requests` lê a Location sozinho no `Session.send`, mesmo com `allow_redirects=False`** (preenche `r._next`): o
  `urlparse` e o `latin1 -> utf8` dele levantam `ValueError` (`UnicodeDecodeError` incluso) DENTRO de `_SESSAO.request`,
  antes de a ponte ver a resposta; `_seguir` captura esse `ValueError` em volta do envio e recusa (502, não 500). A
  ponte relê a Location em UTF-8 como o requests (`encode("latin-1").decode("utf-8")`) antes das travas. **Teste
  de salto com sessão falsa não vê isso** (04/10/2026: os testes passavam e a rota dava 500): use
  `tests/sessao_real_sem_rede.py` (`requests.Session` real com adaptador falso montado, sem rede).
- **A `NEXUS_PLATAFORMA_URL` é lida do mesmo jeito** (`ponte.origem_configurada`, usada pela rota): barra invertida,
  espaço ou controle, ou URL que não é http(s), vira a página "Ponte não configurada" sem nenhuma chamada de rede; a
  regra "http só em localhost/127.0.0.1/::1" usa esquema e host dessa leitura, não do `urlsplit`
  (04/10/2026: `http://evil.com\@localhost:5050` parecia localhost e o `requests` ia para evil.com em texto puro).
- **Falha fechada se a plataforma não cumpre a chave:** resposta 2xx sem `X-Nexus-Leitura-Ok: 1` (cabeçalho que o
  `_auth_gate` da plataforma só põe quando aceitou a chave) não é mostrada. Plataforma sem `NEXUS_LEITURA_TOKEN` ignora
  a chave e deixa passar até gravação, e a ponte não tinha como saber.
- `montar_pedido` recusa (`ValueError`) caminho sem "/" inicial ou com "?"/"#", além do 400 da rota: a regra vale
  também para quem chamar a função sem passar pela rota.
- Controle de gravação que aparecer na tela (seletor novo na plataforma): acrescentar em `_VISUAL`, com o atributo REAL
  da página (`onclick`, `onchange` ou `oninput`; confira no HTML da plataforma) e só o controle, nunca um contêiner de
  dado. Mesmo sem isso, o guarda não deixa gravar.

## Risco conhecido (fase 1): mesma origem

O HTML da plataforma roda na origem do Nexus, com a sessão do administrador. O guarda (`#nexus-leitura`) só embrulha
`fetch`: um script injetado numa página da plataforma (texto de terceiro ou de usuário que chegue ao HTML sem escape)
poderia usar a sessão do Nexus por outros caminhos (`XMLHttpRequest`, formulário, `window.open`). A correção de verdade é
servir a ponte em **outra origem** (subdomínio ou porta, cookie próprio), antes do login por pessoa (fase 3). Até lá,
todo texto de terceiro ou de usuário nas páginas da plataforma passa por `_he`. Levi aceitou o risco por agora
(04/10/2026); a origem separada entra antes do login por pessoa (fase 3).

Como provar: `tests/test_performance_ponte.py`, `tests/test_torre_performance.py` e, na tela, o Nexus local contra a
plataforma local — mesmo número do card nos dois no mesmo minuto.
