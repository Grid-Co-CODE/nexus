# DESIGN.md — o visual do Nexus

O lugar único para consultar antes de desenhar ou mexer numa tela (Levi, 29/10/2026: "tem que ter um .MD só para design
para ser consultado"). A verdade das cores é o `nexus/static/nexus.css` (os dois blocos de tokens no topo dele); este
arquivo diz quais usar, para quê e as regras que os testes cobram. Regra mudou: corrija aqui e no `nexus.css` juntos.

## 1. As regras (valem para toda tela)

- **Tema escuro navy é o padrão e não muda.** O claro (08/10/2026) é escolha da pessoa, pelo botão do topo. Toda tela
  funciona nos dois.
- **Nunca lilás.** O navy arroxeado do mockup (`#191528`) não entra como fundo.
- **Cor só por token.** Nada de `#hex` ou `rgba()` em regra de CSS, nem em `style=`, `<style>` ou `fill=` de template.
  Cor nova = token novo nos DOIS blocos do `nexus.css`, com o valor do escuro e o do claro. `tests/test_tema.py` cobra.
- **Sem emoji na interface.** Severidade é cor e palavra juntas ("Agir agora" em vermelho, nunca só a bolinha).
- **Tudo em pt-BR**, inclusive comentários, `title` e `aria-label`.
- **Sem animação decorativa**; `prefers-reduced-motion` desliga toda transição.
- **No claro nada esmaece por opacidade** (linha concluída, cartão cancelado): vira `--superficie-2` com texto `--mudo`,
  porque a opacidade derrubava o contraste a 2,4–3,5:1 no branco.
- **Verde Grid é superfície, não texto, no claro:** o `#a9db21` dá 1,6:1 no branco. Texto verde é sempre `--verde-texto`.
- **Explicação mora no "!" amarelo ao lado do título** (05/11/2026, Levi: "Disclaimers de 'entenda o que aconteceu'
  'o que é' precisa estar em um símbolo de exclamação amarelo no estilo segurança > extintores ... padrão nexus!"):
  "Entenda esta tela", "De onde vem", "Como se conta", "Como funciona", "Como ler", "Como vale", "O que é" e a
  legenda de termos nunca ficam soltos na tela, nem no pé dela. Componente na seção 6; `tests/test_explica_padrao.py`
  cobra, em `<b>` ou em `<strong>` (o "Como vale." em `<strong>` passava até a revisão de 05/11/2026).
- **Contraste AA (4,5:1)** em todo texto do claro, sobre o branco, o `#f5f6f8`, o `#eceef2` e o fundo "-suave".

## 2. Cores

As principais. A lista completa (transparências por alfa, séries de gráfico, mapa, papel de impressão) está no
`nexus.css`, comentada.

| Token | Escuro | Claro | Para quê |
|---|---|---|---|
| `--fundo` | `#090d18` | `#fcfcfc` | fundo da página |
| `--superficie` | `#161d30` | `#ffffff` | cartão, bloco, tabela |
| `--superficie-2` | `#1c2640` | `#f5f6f8` | seção, cabeçalho de tabela, linha em hover |
| `--superficie-3` | `#243154` | `#eceef2` | hover forte, cartão em foco |
| `--barra` | `#0d1526` | `#eef2f7` | barras e trilhos |
| `--tinta` | `#e9eef6` | `#1f2937` | texto principal |
| `--tinta-2` | `#c3cad7` | `#475569` | texto secundário, corpo de parágrafo |
| `--mudo` | `#96a0b4` | `#5a6475` | rótulo, legenda, o que é menos importante |
| `--linha` / `--linha-forte` | branco 9% / 16% | navy 10% / 18% | bordas e divisórias |
| `--verde` | `#a3d900` | `#a9db21` | botão primário, aba ativa, barra: SUPERFÍCIE |
| `--verde-texto` | `#c4e755` | `#566610` | texto verde (o eyebrow, um link de destaque) |
| `--sobre-verde` | `#191528` | `#0d1526` | texto em cima do verde |
| `--foco` | `#a3d900` | `#566610` | contorno do foco do teclado |

O topo é navy com o logo branco nos dois temas (o bloco do escuro vale de novo dentro do `.topo`).

**O semáforo.** O token simples é para TEXTO (a palavra, a bolinha do `gc-status`). O `-suave` é o fundo da etiqueta.
O `-cheio` é para ÁREA: barra, borda grossa de destaque, preenchimento com texto escuro por cima (`--sobre-cheio`).

| Nível | Texto escuro / claro | Área (`-cheio`) escuro / claro | Palavra de exemplo |
|---|---|---|---|
| ok | `#4ade80` / `#166b36` | `#4ade80` / `#3dbb68` | Operando, Em dia |
| alerta | `#ffd83d` / `#7a5200` | `#ffd83d` / `#f0b429` | Atenção |
| severo | `#ff9f43` / `#a33d00` | `#ff8f3c` / `#f59342` | Severo |
| crítico | `#ff5b6e` / `#b42230` | `#ff5b6e` / `#ef5d6e` | Agir agora |
| info | `#7fb8ff` / `#0a5fc4` | `#7fb8ff` / `#5c9cf5` | Em análise, Desempenho |
| sem comunicação | `#b39dff` / `#7442d1` | — | Sem comunicação |

**Fica igual nos dois temas, de propósito:** a foto ampliada é sempre escura (`--foto-*`); a assinatura e a folha de
impressão são sempre papel branco (`--papel-*`); a cor de DADO (a da pessoa no Quadro da equipe, a da etiqueta do
Fracttal) é a mesma nos dois, com texto escuro por cima. A página da Plataforma no Tempo real fica no escuro dela.

**A torre Zeladoria usa a paleta do Nexus** (Levi, 03/11/2026, depois de ver a 1ª versão em preto, azul e lima: "bote aquele azul nexus para ficar no padrão nexus de planilha e cards"). O clone do Radar não carrega o `nexus.css` (as regras dele brigariam com as do clone): a torre põe na página só os blocos de token do `nexus.css` (`tokens_do_nexus`, tirados do arquivo ao servir), e o bloco `zeladoria-paleta` aponta cada variável do clone para um token (`--bg` = `--fundo`, `--surface` = `--superficie`, `--accent` = `--verde`...). O botão do clone é o retângulo do `gc-btn`. O tema é o do Nexus: o `<html>` do clone leva `data-theme` (o do Radar) e `data-tema="claro"` (o do Nexus). Detalhe em `nexus/torres/zeladoria/CLAUDE.md`.

**Gráficos e mapa:** as séries (`--serie-*`) e as rampas de calor do Mapa de risco (`--calor-*`, um matiz por rampa,
luminosidade monótona) já têm token nos dois temas. Série nova passa pelo validador do dataviz antes de virar token.

## 3. Tipografia

| Uso | Fonte | Medida |
|---|---|---|
| Título da página (`.titulo-pagina`) | Raleway 800 (`--font-display`) | 30px / 36px |
| Interface e texto (`body`) | Poppins (`--font-sans`) | 14px / 1.5 |
| Parágrafo de abertura (`.lead`) | Poppins | 15px / 1.6, até 760px de largura |
| Eyebrow (`.gc-eyebrow`, a torre acima do título) | Poppins 500, MAIÚSCULA, verde-texto | 12px, espaçamento 2px |
| Título de seção (`.ui-kicker`) | Poppins 700, MAIÚSCULA, mudo | 10px, espaçamento .14em |
| Rótulo de campo e de número (`.gc-rotulo`, `.gc-numeros .r`) | Poppins 700, MAIÚSCULA, mudo | 11px |
| Número grande (`.gc-numeros .v`) | Poppins 600 | 27px / 32px |
| Código, commit, carimbo (`.gc-dado`, `code`) | IBM Plex Mono (`--font-mono`) | 13px |

Número em coluna ou em cartão leva `.gc-num` (algarismos de largura igual). As fontes vêm do Google Fonts (Poppins
400–700, Raleway 700–800, IBM Plex Mono 400–500), carregadas no `base.html`.

## 4. Medidas e tela pequena

- Raios: `--raio-tag` 6px (etiqueta), `--raio-controle` 8px (botão, campo), `--raio-md` 10px (cartão, caixa).
- Topo: `--topo` 60px.
- **Menu recolhido (trilho de ícones):** passar o mouse num ícone abre ao lado a caixa com o nome da área e as telas
  dela (`.menu-voo`, o verde da tela pronta e a tela aberta, como no menu aberto); o clique no ícone leva à 1ª tela.
- **Até 820px:** o menu sai da lateral e abre pelo botão "Menu" (um checkbox, sem JavaScript); some o nome de quem
  entrou.
- **De 821 a 1180px:** o menu estreita (196px) e o setor do topo encolhe.
- **Até 1180px:** o botão de tema mostra só o ícone.
- **A prova é a 375px:** nenhuma rolagem lateral da página (tabela larga rola dentro da própria caixa).
- **As larguras de quebra (`@media`) são seis:** 480 (celular pequeno), 640 (celular), 820 (o menu vira botão), 900
  (tablet), 1100 (desktop estreito) e 1180 (o menu estreito). O par de cada uma vale (`max-width:639px` com
  `min-width:640px`). Em 08/11/2026 havia mais de 15 larguras diferentes, e o responsivo de uma tela não batia com o da
  vizinha; as antigas estão em `tests/test_larguras_de_quebra.py` e só diminuem (sai a da tela conferida a 375px e no
  desktop com a largura padrão mais perto). CSS novo com outra largura não passa no teste.

## 5. Como uma tela se monta

De cima para baixo, no `{% block conteudo %}` (exemplo vivo: `nexus/templates/inicio.html`):

1. `p.gc-eyebrow`: a torre (ou o setor).
2. `h1.titulo-pagina`: o nome da tela, com o "!" das explicações ao lado (`div.gc-titulo-explica`, seção 6).
3. `p.lead`: a pergunta que a tela responde, em uma ou duas frases.
4. `nav.gc-subabas` (se houver abas): a ativa leva `aria-current="page"` e ganha o sublinhado verde.
5. `div.gc-numeros`: os números do alto, cada um com `.r` (rótulo), `.v` (valor, `.gc-num`) e `.d` (o
   que o número quer dizer).
6. `h2.ui-kicker` antes de cada seção, e o conteúdo (tabela, cartões, lista).
7. `p.aviso` para o que a pessoa precisa saber AGORA (sem dado, setor sem tela, leitura que falhou); `.mudo` para a nota
   que muda com o dado. Como a tela funciona e de onde vem o dado não ficam aqui: vão para o "!" do título.

Dado que veio pela metade não vai para a tela: a tela diz o que falta (`CLAUDE.md` raiz, "Confiabilidade antes de
tela"). Como criar a tela de uma torre (a rota, o template, o menu): `nexus/torres/CLAUDE.md`.

## 6. Componentes

- **Botão** `.gc-btn` + uma variante: `--primario` (verde, a ação principal), `--contorno` (a ação
  secundária), `--fantasma` (ação discreta, como no topo). O `--ui` que aparece nos templates não tem regra no CSS: não
  muda nada.
- **Etiqueta de situação** `.gc-status` + `--ok`, `--alerta`, `--critico`, `--info` ou `--neutro`: bolinha e palavra
  na cor do nível, sobre o `-suave`. Sempre com a palavra.
- **O "!" das explicações** (`nexus/templates/_explica.html`, o padrão de toda tela desde 05/11/2026; nasceu em
  Segurança → Extintores): o círculo amarelo com "!" ao lado do título; o clique abre a caixa por cima da tela, com a
  borda bevel amarela, e clicar fora ou o Esc fecha (`base.html`). No celular a caixa fica presa à tela, com 16px de
  cada lado. Uma tela tem UM "!": explicações diferentes viram parágrafos dele, na ordem em que se lê. Uso:
  `{% from "_explica.html" import explica %}`, o h1 dentro de `<div class="gc-titulo-explica">` e, logo depois dele,
  `{% call explica('Entenda esta tela') %}<p><b>De onde vem.</b> ...</p>{% endcall %}`. Legenda de termos coloridos:
  `explica(titulo, pe, termos=True)` com `termo('Atrasado', 'critico')` e `<dd>`. O que NÃO vai para o "!": erro,
  dado faltando, aviso que muda com o dado e a instrução de uma ação (esses ficam onde a pessoa age).
- **Chip** `.gc-chip`: filtro ou escolha que liga e desliga (redondo, com borda).
- **Campo** `.gc-campo`, com `.gc-rotulo` acima e `.gc-ajuda` abaixo (`.gc-ajuda--erro` quando errado).
- **Cartão de torre** `.card-torre`: o ícone em verde-texto, o nome e a contagem à direita. Sem tela pronta, ele não é
  link e diz "Em construção".
- **Bloco que recolhe:** `<details>`/`<summary>` sem JavaScript, com a seta desenhada no CSS (duas bordas giradas) e o
  marcador do navegador escondido. Exemplos: o dia das Atualizações (`.atu-dia`, a seta à esquerda e o total na ponta
  direita) e a Sugestão (`.sug-dobra`).
- **Ícones:** Phosphor regular, `<i class="ph ph-<nome>">` (a folha vem do unpkg no `base.html`). No topo, o ícone do
  tema é desenhado no CSS, sem `<svg>`: as telas com gráfico procuram o primeiro `<svg>` da página.

## 7. Como provar uma mudança de visual

- `python -m pytest -q tests/test_tema.py`: os dois blocos com os mesmos tokens, o escuro congelado
  (`ESCURO_DE_SEMPRE`), nenhuma cor fixa nos `.css` e templates, todo `var()` existe e o contraste AA do claro.
- A tela no navegador, **nos dois temas, no desktop e a 375px**: sem rolagem lateral, sem erro de JavaScript, todo
  texto legível. Numa cópia de prova, nunca na 5070 (`CLAUDE.md` raiz, "Para provar uma mudança").

Mais detalhe: o tema e como ele chega (cookie, botão, OS Creator) em `nexus/casca/CLAUDE.md`, seção "Tema escuro
(padrão) e claro"; o desenho original da casca em `docs/superpowers/specs/2026-09-29-casca-nexus-design.md`, seção 9.
