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

## Clima e risco (06/10/2026): alertas públicos por usina, só leitura

Aba Performance → Clima e risco (`/t/performance/clima`). O Levi trouxe o pacote `gridco_meteo` (referência, fora do
repositório) e escolheu (06/10) começar pelos **alertas**: avisos do INMET, focos de queimada do INPE e risco de fogo do
INPE, todos públicos e de uso livre. A tela cruza isso com as usinas em operação do cadastro e se atualiza sozinha
(recarrega a cada 60 s; o que vai à rede é decidido pelo cache, não pela recarga). Atribuição no rodapé: "Dados: INMET,
INPE (Programa Queimadas)."

| Fonte | O que traz | Cache | Endereço (troca por `NEXUS_CLIMA_*_URL`) |
|---|---|---|---|
| INMET avisos | JSON `{hoje, futuro}`; cada aviso com evento, severidade, início, fim e polígono (texto de JSON) | 30 min | `apiprevmet3.inmet.gov.br/avisos/ativos` (não documentado oficialmente) |
| INPE focos | CSV de 10 em 10 min (`lat,lon,satelite,data`, hora em UTC); vale a última hora = os 6 últimos arquivos | 10 min | `dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/10min/` |
| INPE risco de fogo | GeoTIFF por dia, `RF.PREV.T0..T3.tif` (hoje e D+1 a D+3), 0 a 1, pixel de ~1 km | 6 h (sai ~06:30) | `dataserver-coids.inpe.br/.../riscofogo_meteorologia/previsto/risco_fogo/RF.PREV.T{d}.tif` |

O código (sem Flask) está em `nexus/performance/clima/`: `geometria` (ponto em polígono e haversine), `geotiff` (leitor do
COG), `fontes` (os três clientes), `alertas` (as regras), `leitura` (cache por fonte), `usinas` (cadastro), `visao` (o que a
tela escreve). A rota é `nexus/torres/performance/clima_tela.py`; o CSS, `nexus/static/clima.css`.

**Regras que custaram caro**
- **O Pillow não abre o GeoTIFF do INPE.** É um COG de 64 bits (BitsPerSample 64, LZW, tiles de 256, 8699 x 8899): o plugin
  TIFF do Pillow só tem modo para float de 32 bits (`UnidentifiedImageError`, "unknown pixel mode", medido com o 12.2), e
  rasterio e shapely estão vetados (sem dependência nova). `geotiff.py` lê só o cabeçalho e a tile de cada usina, por `Range`,
  e decodifica o LZW em Python puro (bytes idênticos aos do Pillow nas 1190 tiles do T0). Aceita **só o formato medido**
  (little-endian, tiles, LZW sem predictor, float64, EPSG:4326, PixelIsArea, escala + tiepoint no canto); o que mudar vira
  `GeoTiffErro` dizendo o que achou, e a tela diz que o formato do INPE mudou. Custo medido (160 usinas, 4 dias em paralelo):
  ~7 s e ~4,6 MB na leitura fria, uma vez a cada 6 h (ou quando o conjunto de usinas muda).
- **Pixel sem dado (-999):** o INPE não calcula onde não há vegetação (cidades, água e, às vezes, a própria usina: 1 de 40
  coordenadas de referência). Vale o MAIOR valor do quadrado de 5 x 5 pixels (~2 km), com a nota "entorno"; se nem o
  entorno tem dado, "sem dado (sem vegetação no entorno)" (não é alerta, e a tela lista essas usinas).
- **Faixas do risco de fogo** (as do `config.ALERTA` do pacote): mínimo < 0,15 ≤ baixo < 0,4 ≤ médio < 0,7 ≤ alto ≤ 0,95 <
  crítico; o valor é arredondado a 9 casas antes de comparar (o 0,70 em double pode chegar 0,6999999999999). Valor fora de
  0 a 1 é recusado: uma escala trocada acenderia o "crítico" em toda usina.
- **A borda do polígono conta como dentro** (o `contains` do shapely a exclui): um aviso que encosta na usina vale.
- **Gravidade, três degraus (semáforo):** Crítico = "Grande Perigo", foco a até 5 km ou risco crítico; Alto = "Perigo" ou
  risco alto; Atenção = "Perigo Potencial". O foco é sempre crítico (é evento, não previsão). Desempate: tem foco, mais
  tipos de alerta, foco mais perto, aviso mais grave, nome. Risco médio não é alerta.
- **Fonte fora:** a última leitura boa é servida com o erro e a hora ("INMET fora agora; última leitura boa às HH:MM"), nunca
  como fresca; sem leitura boa, o número é "—" (nunca 0) e a lista diz que não inclui aquela fonte. Depois de uma falha,
  60 s sem insistir; uma busca por vez (quem chega no meio recebe a última boa, sem esperar a rede).
- **Usinas e coordenadas** vêm do cadastro (`nexus/cadastro/`): em operação, latitude e longitude cifradas e abertas só no
  processo do Nexus. A coordenada **nunca** vai à tela, ao log nem ao `repr` da usina. Usina em operação sem coordenada
  utilizável, ou com coordenada fora do Brasil (0 e 0, sinal ou latitude e longitude trocadas), aparece numa linha própria:
  nunca some. O risco de fogo é lido para TODAS as usinas com coordenada (o cache vale pelo conjunto de pontos); o filtro
  por cliente é só da tela.
- **O texto do aviso é de terceiros:** só entra escapado, e a cor do aviso nem é lida. Aviso sem polígono utilizável é
  contado e dito na fonte, não some.
- **Focos:** a hora vem da coluna `data` (UTC), não do nome do arquivo (satélite polar chega atrasado); sem arquivo novo há
  mais de 30 min, a fonte fica em atenção. Um foco é um pixel com fogo detectado, não um incêndio confirmado.
- **Nenhum teste vai à rede:** `leitura.usar_sessao` e `leitura.usar_relogio` injetam a sessão falsa e o relógio; com
  `TESTING` e sem sessão injetada a fonte diz "sem fonte nos testes". O COG dos testes é montado no próprio teste
  (`tests/clima_cog.py`: contêiner à mão, LZW comprimido pelo Pillow), sem binário no repositório. Teste sem
  `NEXUS_ARMAZEM_LOCAL` se recusa a abrir o cadastro de verdade.

**Fase 1 só lê, e nada é gravado no banco.** Histórico de aviso, foco ou risco seria fato novo da governança de dados
(`nexus/dados/CLAUDE.md`: entra primeiro no catálogo, com grão e dimensões): é outra fase.

**Fase 2 (fora desta entrega) e por quê:** previsão de vento, chuva e convecção, os testes T1 a T5 de confiabilidade do POA
e do GHI e a substituição de ETM do `gridco_meteo` dependem do Open-Meteo, cuja API grátis é só para uso não comercial.
Antes de ligar isso, decidir a licença: plano pago, ou servidor interno do Open-Meteo (ERA5 e previsão, uso comercial livre)
mais o CAMS/SoDa para a radiação de satélite. Cada troca de fonte pede recalibrar os parâmetros.

**Servidor da T.I.:** precisa de saída para `apiprevmet3.inmet.gov.br` e `dataserver-coids.inpe.br` (`DEPLOY.md`, seções 0 e
7c); sem elas a tela abre e mostra as fontes como "fora agora".

Como provar: `python -m pytest -q tests/test_clima_*.py tests/test_torre_performance_clima.py`. Ao vivo (06/10/2026, 40
coordenadas de referência, só leitura): 25 usinas dentro de algum aviso, 1 com foco a 1,9 km, 18 com risco alto ou crítico;
1,6 s e 0,7 MB por dia de risco. Mudou o leitor do GeoTIFF? Confira as tiles contra o Pillow (monte um mini-TIFF de uma faixa
com `int32` no lugar de `double`: os bytes são os mesmos) antes de confiar.
