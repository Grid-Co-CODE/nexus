# Tempo real no Nexus — desenho (04/10/2026)

Torre **Performance**, aba **Tempo real**. Primeiro passo para a Plataforma de Performance morar 100% no Nexus.

## 1. Decisões do Levi (04/10/2026)

- "Trazer o tempo real para o meu repositório do Nexus": a tela do Nexus **lendo a plataforma**, "adaptada conforme o
  Nexus", no supervisório do Nexus (as 7 abas da torre Performance), **em paralelo por enquanto**.
- Conteúdo: **tudo da plataforma, só leitura** — a Entrada e o Monitoramento inteiros (tabelas de strings, ETM e
  trackers, drill do inversor, curvas, PR, perdas).
- Abordagem: **ponte viva** — o Nexus serve as páginas da própria plataforma, com o visual do Nexus por cima, e só
  deixa passar leitura.
- Rumo: "em um futuro próximo a plataforma fique 100% no Nexus". Este passo é desenhado para ser a primeira fase
  dessa mudança (seção 10).

## 2. Escopo deste passo

**Dentro:**
- A aba `/t/performance/tempo-real` do Nexus mostra, dentro da casca (menu lateral à vista), a Entrada da plataforma
  no nível 2 (os cards por cliente e fonte) e, ao clicar, o Monitoramento da fonte — tudo o que a plataforma mostra.
- Só leitura, garantido em três camadas (seção 5).
- Visual do Nexus aplicado por cima (seção 6).
- As correções no modo sub-caminho da plataforma que a ponte precisa (seção 4.2).

**Fora (passos seguintes):** as outras 6 abas da torre (Painel NOC, Diagnóstico, Strings e trackers, Visão gerencial,
Criador de relatório, Gêmeo digital); login por pessoa e carteira por supervisor (o Nexus ainda entra só com a senha
de admin); qualquer ação que grava (cadeado, comentário, ticket, OS) — continua na plataforma.

## 3. Arquitetura

```
navegador ──► Nexus (login do Nexus)
               /t/performance/tempo-real            página do Nexus: casca + moldura
               /t/performance/plataforma/<caminho>  PONTE: GET (e 3 POSTs de consulta) ──────────────┐
                                                                                                       ▼
                                                    Plataforma de Performance (5050 local ou app.gridco.com.br)
                                                    cabeçalhos: X-Nexus-Leitura: <chave>
                                                                X-Forwarded-Prefix: /t/performance/plataforma
```

- O navegador fala **só com o Nexus**. A ponte leva o pedido à plataforma de servidor para servidor e devolve a
  resposta, ajustada (seção 4.1).
- A plataforma continua sendo o **motor**: coleta, caches, réguas. O Nexus não faz nenhuma requisição a mais à
  SunOp, à API PV ou ao banco — só lê o que a plataforma já serve (o web dela serve o cache; ela não reconstrói no
  pedido).
- Com `X-Forwarded-Prefix`, a plataforma já sabe rodar debaixo de um caminho: põe o prefixo no `SCRIPT_NAME` e injeta
  no HTML um calço que reescreve `fetch`, XHR e links (`_SHIM_PREFIXO`, feito para a T.I. hospedar a plataforma em
  sub-caminho). As chamadas da página voltam para a ponte sem a ponte reescrever HTML.

## 4. Componentes

### 4.1 Nexus

| Peça | O que faz |
|---|---|
| `nexus/performance/ponte.py` | Regra sem Flask, testável: decide se um pedido passa (método + caminho), monta o pedido à plataforma (URL, cabeçalhos, tempo-limite) e ajusta a resposta (injeta o visual e o guarda de leitura no HTML; filtra cabeçalhos). |
| `nexus/performance/CLAUDE.md` | O porquê da ponte, a lista do que passa, como provar. |
| `nexus/torres/performance/__init__.py` | Rota da tela `tempo-real` (moldura) e a rota da ponte `/plataforma/<caminho>`. |
| `nexus/torres/performance/templates/performance/tempo_real.html` | Casca + faixa ("Plataforma de Performance · somente leitura", "Abrir na plataforma") + moldura. |
| `nexus/config.py` | Opcionais `NEXUS_PLATAFORMA_URL` e `NEXUS_PLATAFORMA_TOKEN`. Sem elas o Nexus sobe e só a aba diz o que falta. |

A rota da ponte fica debaixo da torre (`/t/performance/plataforma/...`), então o portão de login do Nexus vale
sozinho. A ponte **não repassa `Set-Cookie`** da plataforma ao navegador, não manda o cookie do Nexus à plataforma e
não repassa cabeçalhos de salto (`Connection`, `Transfer-Encoding`, `Content-Encoding`, `Content-Length`).

A ponte **tira o `force=1`** dos pedidos. Na plataforma, o "Atualizar" das abas de trackers manda
`/api/<fonte>/trackers/parados?force=1`, e o web refaz as curvas na hora — na SunOp, isso é cota. Pelo Nexus, ler é ler
o que o motor já montou; o ciclo dele atualiza sozinho.

### 4.2 Plataforma (repositório PerformancePainel)

Tudo abaixo é inofensivo quando a plataforma roda na raiz e sem a chave, que é como ela roda hoje.

| Peça | O que faz |
|---|---|
| `plataforma/leitura_nexus.py` | Lista fechada do que a chave de leitura alcança: as páginas (`/tempo-real`, `/tempo-real/<fonte>`, `/monitor`), os prefixos de API que as duas páginas leem (GET) e os 3 POSTs que são consulta (`/api/os-performance/counts`, `/api/os-creator/fractall-usinas`, `/api/etm/os`). Função pura `permitido(metodo, caminho) -> bool`. |
| `_auth_gate` (`app.py`) | Com `X-Nexus-Leitura` igual a `NEXUS_LEITURA_TOKEN` (`hmac.compare_digest`): passa só o que `permitido` aceita; o resto leva **403** `{"error": "somente leitura (Nexus)"}`. Chave errada: 401. Sem a variável configurada, o cabeçalho é ignorado. |
| Entrada: nível pelo caminho | `location.pathname` sem o `window.APP_PREFIX` antes do `split` — hoje, debaixo de prefixo, o nível 2 e o 3 não abrem. |
| Entrada: moldura do Monitoramento | `fr.src = (window.__pfx || String)("/monitor?...")` nos dois pontos — o calço não pega `src` de moldura. |
| `_SHIM_PREFIXO` | Corrige também o link criado pelo JavaScript depois da carga (clique em captura) e o `window.open`. Hoje só os `<a>` presentes no `DOMContentLoaded` ganham o prefixo. |
| `_injeta_prefixo` | Põe o prefixo nos atributos `src`, `href` e `action` absolutos do HTML, no servidor. Hoje o `<script src="/static/notif.js">`, o logo e os links escritos no HTML pedem a raiz do domínio — debaixo do Nexus, a raiz é o Nexus. |

Um teste na plataforma confere a lista do `leitura_nexus` contra as rotas `/api/...` citadas nas duas páginas: rota
nova numa página sem entrar na lista quebra o teste, em vez de a aba do Nexus ficar em branco calada.

## 5. Só leitura, em três camadas

1. **Portão da plataforma** (a garantia): com a chave de leitura, toda gravação leva 403. É o que vale mesmo se as
   camadas de cima falharem.
2. **Ponte do Nexus**: recusa antes de sair qualquer método que não seja GET/HEAD, exceto os 3 POSTs de consulta.
   Responde 403 com a mesma mensagem.
3. **Página**: o script que a ponte injeta segura, no navegador, todo POST que grava — não envia e mostra "Somente
   leitura no Nexus: faça isto na plataforma". O CSS injetado esconde os controles mais visíveis de gravação (topo da
   Entrada com o Atualizar, cadeado, comentário, OS atribuída, marcar desligada, ticket, acompanhamento, Criar OS). A
   lista exata de seletores sai de uma varredura da página no navegador, no plano.

## 6. Visual do Nexus

A plataforma e o Nexus usam o mesmo Design System (navy `#090d18`/`#161d30`, verde `#a3d900`). A ponte injeta, só
nas páginas servidas por ela:
- a fonte do Nexus (Poppins/Raleway) no lugar da Inter;
- fundo liso do Nexus (sem o brilho radial da Entrada);
- o topo próprio da plataforma escondido (o do Nexus já está na casca) e a Entrada direto no nível 2.

O que fica igual de propósito: tabelas, cores de status, régua, drill, gráficos. A régua de status roda no
JavaScript da página (`_strStatus`, `_strReclassifica`): reproduzir em outra tela seria arriscar o Nexus e a
plataforma dizerem coisas diferentes.

## 7. Erros

| Situação | O que aparece |
|---|---|
| `NEXUS_PLATAFORMA_URL` ou `_TOKEN` ausente | A aba diz qual variável falta. O resto do Nexus sobe normal. |
| Plataforma fora do ar ou sem resposta em 150 s | Página do Nexus: "Plataforma de Performance sem resposta (HH:MM)", com "Tentar de novo". O drill da API PV leva até 120 s; 150 s cobre. |
| Plataforma recusa a chave (401) | "A plataforma recusou a chave de leitura do Nexus" — sem mostrar a chave. |
| Rota fora da lista (403) | A mensagem de somente leitura. |

## 8. Segurança

- Os dois repositórios são públicos: a chave mora só no `.env` do Nexus e no `.env`/`tokens.txt` da plataforma.
  Nunca em commit, log ou mensagem de erro.
- A chave só abre leitura, e só das rotas da lista. Ela não alcança `/api/tokens`, a ronda, a coleta nem nada que
  dispare trabalho pesado.
- Quem vê a aba já passou pelo login do Nexus.

## 9. Como provar

- **Testes da plataforma:** `permitido` (páginas, GET da lista, os 3 POSTs, gravações recusadas); portão (chave certa
  e GET → 200; chave certa e gravação → 403; chave errada → 401; sem variável → cabeçalho ignorado); a lista cobre as
  rotas das duas páginas; o caminho da Entrada com prefixo (node, como os testes de lógica do Monitoramento).
- **Testes do Nexus:** a ponte decide, monta e ajusta (plataforma falsa); a aba exige login; sem configuração, a aba
  avisa; plataforma fora → página de erro; `Set-Cookie` não passa.
- **Na tela:** Nexus local (5070) contra a plataforma local (5050), desktop e 375 px; a Entrada abre no nível 2, o
  card leva ao Monitoramento, o drill do inversor abre, um clique num controle de gravação mostra o aviso e não grava
  (conferir no `ufv_state.json` antes e depois). **Mesmo número dos dois lados**: no mesmo minuto, as contagens de um
  card e o frescor ("atualizado às") iguais na plataforma e no Nexus.

## 10. Rumo à plataforma 100% no Nexus

A ponte é a fase 1 de uma mudança de casa em cinco fases. Em todas, a regra de 04/10 vale: **em paralelo**; nada
desliga na plataforma antes de o Levi dizer que o Nexus está redondo.

| Fase | O que muda | Por que nessa ordem |
|---|---|---|
| 1. Tempo real pela ponte (este desenho) | A aba do Nexus mostra a plataforma, só leitura. | Prova a ponte, o prefixo e o só leitura com a tela mais usada. |
| 2. As outras 6 abas pela mesma ponte | Painel NOC (`/painel`), Diagnóstico, Strings e trackers (`/painel/falhas`), Visão gerencial (`/gerencial`), Criador de relatório (`/relatorio`), Gêmeo (`/gemeo/`). Cada uma: entra na lista de leitura e ganha a sua moldura. | Cada aba é um passo pequeno; nenhuma muda o motor. |
| 3. As telas mudam de casa | O HTML das telas passa para o repositório do Nexus e é servido pelo Nexus; os dados seguem pela ponte (`/t/performance/plataforma/api/...`). As ações (cadeado, ticket, OS) passam a gravar pelo Nexus, com o login por pessoa. | Quem usa já está no Nexus; a plataforma vira só API. |
| 4. O motor muda de casa | Coleta, worker, réguas e caches viram um pacote do Nexus. **Uma coleta só de cada vez:** duas coletas juntas dobram o gasto da SunOp (teto de 3.000/dia) e da cota histórica da API PV. | É a parte grande (~29 mil linhas); fica por último porque é a que mais pode quebrar dado. |
| 5. A plataforma desliga | `app.gridco.com.br` passa a redirecionar para o Nexus. | Só depois de o Nexus provar tudo em paralelo. |

O caminho `/t/performance/plataforma/` é a fronteira estável: nas fases 3 e 4 ele passa a apontar para o motor dentro
do Nexus, sem mudar as telas.

## 11. Riscos

- **A plataforma muda quase todo dia.** Ponte viva é justamente para isso: o Nexus mostra sempre a versão do dia.
  O que pode quebrar é a lista de leitura (rota nova) e os seletores escondidos; o teste da lista pega o primeiro, e o
  guarda de POST cobre o segundo (o controle aparece, mas não grava).
- **Moldura dentro de moldura** (Nexus → Entrada → Monitoramento): a altura do Monitoramento vem por `postMessage`
  (`gc: "altura"`); a moldura do Nexus rola por dentro. Conferir em 375 px.
- **Plataforma lenta no drill da API PV:** o pedido fica preso na ponte até 150 s. Aceitável na fase 1 (é o mesmo
  tempo que a plataforma leva sozinha).
