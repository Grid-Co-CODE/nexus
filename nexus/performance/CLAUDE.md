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
INPE (Programa Queimadas)". A **página de cada usina** (`/t/performance/clima/usina/<id>`, 07/10) acrescenta a irradiação
diária da NASA POWER (ver abaixo); a tela principal nunca chama a NASA.

**A tela (leitura rápida, aprovada pelo Levi em 07/10/2026), na ordem:** cabeçalho (filtro de cliente, "atualizada às HH:MM");
**faixa de 4 números** (Agir agora, Atenção, Sem alerta, Cobertura); **Agir agora**, um cartão por usina (motivo numa pílula,
frase principal, prova, contexto); **Por estado**, uma grade de 27 quadrados (esquema, não é mapa; o número é de usinas com
alerta no estado e a cor, a do pior nível); **Fontes** (de quando é cada dado); **Atenção**, uma matriz usina x aviso x foco x
os quatro dias do risco de fogo (as 20 primeiras; "Ver todas (N)" é `?todas=1`). A grade de estados e a matriz rolam DENTRO
da caixa em 375 px, nunca a página. Cada cartão e cada linha levam à página da usina.

| Fonte | O que traz | Cache | Endereço (troca por `NEXUS_CLIMA_*_URL`) |
|---|---|---|---|
| INMET avisos | JSON `{hoje, futuro}`; cada aviso com evento, severidade, início, fim e polígono (texto de JSON) | 30 min | `apiprevmet3.inmet.gov.br/avisos/ativos` (não documentado oficialmente) |
| INPE focos | CSV de 10 em 10 min (`lat,lon,satelite,data`, hora em UTC); vale a última hora = os 6 últimos arquivos | 10 min | `dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/10min/` |
| INPE risco de fogo | GeoTIFF por dia, `RF.PREV.T0..T3.tif` (hoje e D+1 a D+3), 0 a 1, pixel de ~1 km | 6 h se o T0 é o de hoje (sai ~06:30); **15 min enquanto não é** (pela data do arquivo, em Brasília: lido às 05:00, o arquivo de ontem não fica até as 11:01) | `dataserver-coids.inpe.br/.../riscofogo_meteorologia/previsto/risco_fogo/RF.PREV.T{d}.tif` |
| NASA POWER (só a página da usina) | JSON `properties.parameter.ALLSKY_SFC_SW_DWN` = {AAAAMMDD: kWh/m²/dia} (GHI), `-999` = não publicado | **12 h por usina** (um cache por usina; uma busca por vez em cada) | `power.larc.nasa.gov/api/temporal/daily/point?...` (`NEXUS_CLIMA_POWER_URL` leva `{lat}`, `{lon}`, `{inicio}`, `{fim}`) |

O código (sem Flask) está em `nexus/performance/clima/`: `geometria` (ponto em polígono e haversine), `geotiff` (leitor do
COG), `fontes` (os quatro clientes), `alertas` (as regras e os níveis), `leitura` (cache por fonte; o da NASA, por usina),
`irradiacao` (a série de 30 dias, o mês até agora e a geometria do gráfico), `usinas` (cadastro), `visao` (o que a tela e a página
da usina escrevem). As rotas são de `nexus/torres/performance/clima_tela.py`; o CSS, `nexus/static/clima.css`.

**Regras que custaram caro**
- **O Pillow não abre o GeoTIFF do INPE.** É um COG de 64 bits (BitsPerSample 64, LZW, tiles de 256, 8699 x 8899): o plugin
  TIFF do Pillow só tem modo para float de 32 bits (`UnidentifiedImageError`, "unknown pixel mode", medido com o 12.2), e
  rasterio e shapely estão vetados (sem dependência nova). `geotiff.py` lê só o cabeçalho e a tile de cada usina, por `Range`,
  e decodifica o LZW em Python puro (bytes idênticos aos do Pillow nas 1190 tiles do T0). Aceita **só o formato medido**
  (little-endian, tiles, LZW sem predictor, float64, EPSG:4326, PixelIsArea, escala + tiepoint no canto); o que mudar vira
  `GeoTiffErro` dizendo o que achou, e a tela diz que o formato do INPE mudou. Custo medido (160 usinas, 4 dias em paralelo):
  ~7 s e ~4,6 MB na leitura fria, uma vez a cada 6 h (ou quando o conjunto de usinas muda).
- **O arquivo do INPE troca todo dia, às ~06:30, e o leitor sabe disso:** o cabeçalho (os offsets das tiles) é de um arquivo, e
  as tiles saem por `Range` com `If-Range` = o Last-Modified da 1ª resposta. Se o arquivo mudar no meio, o servidor manda o
  novo inteiro (200) e o leitor levanta `GeoTiffErro` ("foi trocado no meio da leitura"), em vez de decodificar a tile de um
  arquivo pelos offsets de outro (lixo ou, pior, um número plausível de outro dia). Conferido ao vivo: o servidor do INPE
  responde 206 ao `If-Range` com o Last-Modified exato. Sem Last-Modified a leitura funciona, e a fonte fica em atenção.
- **Pixel sem dado (-999):** o INPE não calcula onde não há vegetação (cidades, água e, às vezes, a própria usina: 1 de 40
  coordenadas de referência). Vale o MAIOR valor do quadrado de 5 x 5 pixels (~2 km), com a nota "entorno"; se nem o
  entorno tem dado, "sem dado (sem vegetação no entorno)" (não é alerta, e a tela lista essas usinas). Valor NEGATIVO que
  não é o nodata (-999) também é "sem dado", só naquele ponto (`GeoTiff.piso`): vale o entorno, e o dia não cai. Uma usina
  fora da grade do INPE nos quatro dias entra na mesma lista, com o motivo "fora da grade do INPE".
- **Faixas do risco de fogo** (as do `config.ALERTA` do pacote): mínimo < 0,15 ≤ baixo < 0,4 ≤ médio < 0,7 ≤ alto ≤ 0,95 <
  crítico; o valor é arredondado a 9 casas antes de comparar (o 0,70 em double pode chegar 0,6999999999999). Valor ACIMA de 1
  derruba o dia: uma escala trocada (0 a 100) acenderia o "crítico" em toda usina.
- **A borda do polígono conta como dentro** (o `contains` do shapely a exclui): um aviso que encosta na usina vale.
- **Os três níveis da usina (07/10/2026), regra em `alertas.py`:** o caso que os criou foi 06/10, na seca: 145 das 154
  usinas apareciam "com alerta" (baixa umidade e risco de fogo alto cobrindo o Nordeste e o Centro-Oeste) e só 3 pediam ação.
  **Agir agora** = foco a até 5 km (é evento, não previsão); OU aviso do INMET "Grande Perigo" de qualquer evento; OU aviso
  "Perigo" de tempestade, chuvas intensas, acumulado de chuva, vendaval, ventos costeiros ou granizo (comparados sem acento,
  sem caixa e pelo nome inteiro; evento fora da lista em Perigo vai para Atenção, nunca some). **Atenção** = qualquer outro
  aviso, em vigor ou futuro; OU risco de fogo alto ou crítico em algum dos quatro dias. **Sem alerta** = nada disso, e só se
  diz com as TRÊS fontes lidas. Aviso futuro conta (a tela diz quando começa). Dentro de cada nível, a ordem é a gravidade que já
  existia (3 = Grande Perigo, foco ou risco crítico; 2 = Perigo ou risco alto; 1 = Perigo Potencial) e, no empate: tem foco,
  mais tipos de alerta, foco mais perto, aviso mais grave, nome. Risco médio não é alerta. Com o arquivo de ontem do INPE (lido
  antes das ~06:30) o dia "Ontem" ainda conta como um dos quatro (a fonte já está em atenção e o rótulo diz o dia certo).
- **A tela não pode parecer "tudo bem" quando a fonte não foi lida inteira** (revisão de 06/10/2026). Fonte fora: a última
  leitura boa é servida com o erro e a hora ("INMET fora agora; última leitura boa às HH:MM"), nunca como fresca; sem leitura
  boa, o número é "—" (nunca 0). "Sem alerta" só é contado com as três fontes lidas (senão "—" e "não dá para dizer"); "Agir
  agora" vive de avisos e focos, "Atenção" de avisos e risco de fogo, e cada um só vira "—" quando NENHUMA das suas fontes foi
  lida. Seção vazia sem ter lido o que ela usa NÃO diz "nenhuma usina para agir agora": diz "Sem leitura de X: não dá para
  dizer que não há alerta" (só das fontes que ELA usa: o risco de fogo velho não tira o "agir agora"). A nota separa "Lendo
  agora: X" (a fonte ainda está sendo lida pela primeira vez; a tela volta em 10 s, não em 60) de "Os números da faixa e as
  listas não incluem: X" (a fonte está fora). Fonte lida só em parte (aviso sem polígono, arquivo de focos que falhou,
  linhas ilegíveis, dia do risco sem leitura), velha ou com o dado atrasado (focos parados há mais de 30 min, previsão de
  outro dia, sem Last-Modified) fica em atenção, nunca "ok": os números da faixa que dependem dela repetem o qualificador
  ("INMET: parcial", "focos: arquivos até 14:10", "INMET: dado de HH:MM") e, quando o número é 0, ficam âmbar em vez de
  verdes; na matriz, a célula de uma fonte sem leitura diz "sem leitura" (o "—" é "li e não há"). Uma
  fonte que "lê" mas não entende nada é erro, não "0": focos com todas as linhas ilegíveis, ou INMET com avisos e nenhum
  localizável, caem na última leitura boa com o erro. Depois de uma falha, 60 s sem insistir; uma busca por vez (quem chega
  no meio recebe a última boa, sem esperar a rede); cada falha vai ao log (WARNING `clima: <fonte> fora: <motivo curto>`,
  uma linha por falha, sem dado de usina), e uma busca interrompida (Ctrl+C) solta a trava.
- **Irradiação diária: NASA POWER (07/10/2026).** Escolhida pela medida contra as ETMs de 40 usinas (maio a setembro/2026, 2.642
  dias válidos): erro mediano de 7,4% no dia e de 3,9% no mês, 84% dos meses dentro de 10%; melhor que o satélite cru do
  Open-Meteo (5,7% no mês), grátis, sem chave e de uso livre (citar "NASA LaRC POWER"). A grade é de cerca de 50 km: vale para
  o total do mês e para achar ETM fora, não para analisar uma hora; revalidar de outubro a março (a medida é de seca).
  Formato conferido ao vivo: `properties.parameter.ALLSKY_SFC_SW_DWN` com chaves AAAAMMDD, a unidade em
  `parameters.ALLSKY_SFC_SW_DWN.units` ("kW-hr/m^2/day") e `header.fill_value` -999. **A NASA atrasa uns 5 dias** (em 07/10, o último
  dia era 02/10) e o que não saiu vem -999, que aqui é `None`, NUNCA zero; também vem um -999 ISOLADO no meio da série (visto em
  07/09), que é buraco: parte a linha do gráfico e a soma do mês diz quantos dias faltaram. Um fim no futuro ela corta em hoje;
  data ou latitude inválida volta HTTP 422. Formato diferente (não JSON, sem a série, data fora de AAAAMMDD, valor que não é
  número, fora de 0 a 15 kWh/m²/dia, unidade que não é kWh/m²/dia, outro valor de preenchimento) é erro explícito, nunca número lido do jeito
  errado. A coordenada vai no pedido com 2 casas (~1 km: a posição exata da usina não precisa chegar a um servidor de fora) e
  nunca aparece na página nem no log. Só a página da usina chama (um pedido por usina, 12 h de cache, os 40 dias que terminam
  hoje), com última leitura boa servida com a hora e 60 s sem insistir depois de falha, como as outras fontes.
- **A página da usina:** cabeçalho (nome, cliente, UF, nível), os alertas dela (por que agir, avisos com a vigência, foco, risco dos
  quatro dias), a irradiação (gráfico SVG feito no servidor com a conta do desenho aprovado, mês até agora com "até que dia a
  NASA publicou" e quantos dias faltaram no meio, tabela dia a dia recolhida) e as fontes com a hora de cada uma. O que a NASA
  ainda não publicou é uma FAIXA no fim do gráfico, nunca uma queda a zero. Usina que não existe: 404; sem coordenada ou com
  coordenada fora do Brasil: 200 dizendo o que falta, sem ir a fonte nenhuma. NASA fora ou com formato diferente: a página
  responde e os alertas seguem.
- **Comparação com a ETM: próxima etapa (investigado em 07/10/2026, só leitura da API de dados).** O GHI medido da usina EXISTE:
  a coluna `GHI (kWh/m²)` é a mesma nas abas por usina de `bd_thopen` (108 abas) e `bd_performance` (63), gravada pelo
  coletor com o GHI integrado no dia da estação (`docs/api-pv-operation.md`: `day_meteo` hoje, `custom_query meteo` nos dias
  passados), em kWh/m² por dia. A coluna e a unidade são certas (a coluna do IPOA, ao contrário, muda de nome: `IPOA (kWh/m²)`,
  `... DEF`, `... ETM`). O que NÃO é certo é a **ligação usina do cadastro x aba**: no `bd_performance`, nenhuma das 136 chaves
  ligadas do de-para (o código com prefixo do cliente, no formato `XXXX-ABC100`) é o nome de uma aba, e o nome da usina na Base UFV
  só é o de uma aba em 17 de 122; no `bd_thopen`, 79 das 89 chaves ligadas são o nome exato de uma aba e 10 não (o nome com
  número no de-para e a aba sem ele, ou o contrário), e 5 usinas têm duas chaves. Sem a ligação a tela NÃO compara: um "conferir a
  ETM" na usina errada seria pior do que nenhum. Para fechar: guardar no de-para (ou numa decisão da tela Ligações) a aba do GHI
  de cada usina; o resto é barato (a coluna, a unidade e o limite de 10% já estão decididos). Dado a ter em conta: o dia de hoje
  é parcial, e a leitura vazia, zero ou acima de 12 kWh/m² não vale.
- **Hoje, D+1, D+2 e D+3 pela data do calendário:** a data do arquivo (Last-Modified, em Brasília) mais k. Com o arquivo de
  ontem (lido antes das ~06:30), o T0 é "Ontem" e o T1 é "Hoje": chamar de "Hoje" a previsão de ontem seria mentir sobre o dia.
- **Usinas e coordenadas** vêm do cadastro (`nexus/cadastro/`): em operação, latitude e longitude cifradas e abertas só no
  processo do Nexus. A coordenada **nunca** vai à tela, ao log nem ao `repr` da usina (a única saída dela é o pedido à NASA, com 2
  casas). Usina em operação sem coordenada
  utilizável, ou com coordenada fora do Brasil (0 e 0, sinal ou latitude e longitude trocadas), aparece numa linha própria:
  nunca some. O risco de fogo é lido para TODAS as usinas com coordenada (o cache vale pelo conjunto de pontos); o filtro
  por cliente é só da tela.
- **O texto do aviso é de terceiros:** só entra escapado, e a cor do aviso nem é lida. Aviso sem polígono utilizável é
  contado e dito na fonte (atenção), não some. O mesmo aviso nas duas listas (`hoje` e `futuro`) conta uma vez; a chave é
  (id, polígono, início, fim), porque o mesmo id com polígono ou vigência diferente é OUTRO aviso. Início e fim vêm em horário
  de Brasília (UTC-3, sem horário de verão desde 2019) e sem fuso no texto; uma data sem hora no FIM vale até 23:59:59 daquele
  dia, e não até 00:00.
- **Focos:** a hora vem da coluna `data` (UTC), não do nome do arquivo (satélite polar chega atrasado); sem arquivo novo há
  mais de 30 min, a fonte fica em atenção, assim como arquivo que falhou ou linha ilegível (contadas e ditas). Um foco é um
  pixel com fogo detectado, não um incêndio confirmado.
- **Nenhum teste vai à rede:** `leitura.usar_sessao` e `leitura.usar_relogio` injetam a sessão falsa e o relógio; com
  `TESTING` e sem sessão injetada a fonte diz "sem fonte nos testes". O COG dos testes é montado no próprio teste
  (`tests/clima_cog.py`: contêiner à mão, LZW comprimido pelo Pillow), sem binário no repositório; a NASA é
  `tests/clima_power.py` (a série inventada, no formato real medido) e a tela e a página da usina dividem o mundo inventado de
  `tests/clima_mundo.py`. Teste sem `NEXUS_ARMAZEM_LOCAL` se recusa a abrir o cadastro de verdade.

**Fase 1 só lê, e nada é gravado no banco.** Histórico de aviso, foco ou risco seria fato novo da governança de dados
(`nexus/dados/CLAUDE.md`: entra primeiro no catálogo, com grão e dimensões): é outra fase.

**Fase 2 (fora desta entrega) e por quê:** a irradiação DIÁRIA por usina entrou em 07/10 pela NASA POWER (grátis, sem licença
a decidir); continuam fora a previsão de vento, chuva e convecção, os testes T1 a T5 de confiabilidade do POA e do GHI e a
substituição de ETM do `gridco_meteo`, que dependem do Open-Meteo, cuja API grátis é só para uso não comercial. Antes de ligar
isso, decidir a licença: plano pago, ou servidor interno do Open-Meteo (ERA5 e previsão, uso comercial livre) mais o CAMS/SoDa
para a radiação de satélite. Cada troca de fonte pede recalibrar os parâmetros. A comparação com a ETM de cada usina também é
próxima etapa (ver "Comparação com a ETM", acima).

**Servidor da T.I.:** precisa de saída para `apiprevmet3.inmet.gov.br`, `dataserver-coids.inpe.br` e `power.larc.nasa.gov`
(`DEPLOY.md`, seções 0 e 7c); sem elas a tela abre e mostra as fontes como "fora agora".

Como provar: `python -m pytest -q tests/test_clima_*.py tests/test_torre_performance_clima*.py`. Ao vivo (06/10/2026, 40
coordenadas de referência, só leitura): 25 usinas dentro de algum aviso, 1 com foco a 1,9 km, 18 com risco alto ou crítico;
1,6 s e 0,7 MB por dia de risco. Mudou o leitor do GeoTIFF? Confira as tiles contra o Pillow (monte um mini-TIFF de uma faixa
com `int32` no lugar de `double`: os bytes são os mesmos) antes de confiar.
