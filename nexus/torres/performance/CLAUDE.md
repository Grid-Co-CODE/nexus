# CLAUDE.md — torre Performance

| Tela | Estado | De onde vem |
|---|---|---|
| Tempo real | plataforma inteira, só leitura, pela ponte (04/10/2026) | `nexus/performance/ponte.py` — leia `nexus/performance/CLAUDE.md` |
| Clima e risco | alertas públicos por usina (avisos do INMET, focos e risco de fogo do INPE) em três níveis (Agir agora, Atenção, Sem alerta), só leitura, atualiza sozinha (06/10/2026; leitura rápida em 07/10/2026) | `nexus/performance/clima/` (regra), `clima_tela.py` (rota), `nexus/static/clima.css`: leia a seção "Clima e risco" de `nexus/performance/CLAUDE.md` |
| Painel NOC, Diagnóstico, Strings e trackers, Visão gerencial, Criador de relatório, Gêmeo digital | placeholder | fase 2: cada uma entra na lista de leitura da plataforma e ganha a sua moldura pela mesma ponte |

A regra mora em `nexus/performance/`; aqui ficam as rotas e os templates. A moldura segue o padrão do OS Creator (`.conteudo--moldura` + classes `.ponte-*` no `nexus.css`).
