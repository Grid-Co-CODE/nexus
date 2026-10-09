# CLAUDE.md — torre Performance

| Tela | Estado | De onde vem |
|---|---|---|
| Tempo real | plataforma inteira, só leitura, pela ponte (04/10/2026) | `nexus/performance/ponte.py` — leia `nexus/performance/CLAUDE.md` |
| Clima e risco | alertas públicos por usina (avisos do INMET, focos e risco de fogo do INPE) em três níveis (Agir agora, Atenção, Sem alerta), só leitura, atualiza sozinha (06/10/2026; leitura rápida e página por usina com a irradiação da NASA POWER em 07/10/2026; didática em 09/10/2026: o que fazer, o que pode acontecer, o porquê de cada usina, avisos iguais juntos e "Entenda os alertas", textos em `clima/explica.py`) | `nexus/performance/clima/` (regra), `clima_tela.py` (rotas: a tela e `/clima/usina/<id>`), `nexus/static/clima.css`: leia a seção "Clima e risco" de `nexus/performance/CLAUDE.md` |
| Mapa de risco | o Clima e risco num mapa do Brasil (SVG do servidor, sem JS): estados do IBGE, avisos do INMET, focos do INPE e as usinas na cor do nível; `?regiao=` refaz o recorte; mesmas fontes e mesmo cache da lista (07/10/2026); legenda à esquerda e, à direita, a tabela das usinas com o risco e o motivo resumido (09/10/2026). O endereço é `/t/performance/clima/mapa`: o id da `Tela` é `clima/mapa`, com barra | `nexus/performance/clima/mapa.py` (regra), `mapa_tela.py` (rota), `nexus/static/clima-mapa.css` e `nexus/static/clima/ibge-ufs-minima.geojson` (o contorno, guardado no repositório): leia a seção "Mapa de risco" de `nexus/performance/CLAUDE.md` |
| Painel NOC, Diagnóstico, Strings e trackers, Visão gerencial, Criador de relatório, Gêmeo digital | placeholder | fase 2: cada uma entra na lista de leitura da plataforma e ganha a sua moldura pela mesma ponte |

A regra mora em `nexus/performance/`; aqui ficam as rotas e os templates. A moldura segue o padrão do OS Creator (`.conteudo--moldura` + classes `.ponte-*` no `nexus.css`).
