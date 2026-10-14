# CLAUDE.md — Contratos e clientes

Torre do menu "Contratos e clientes". Tela viva: **Contestações** (13/10/2026). Clientes, Onboarding, Comunicação por
cliente e Portal ainda são placeholder (a view com a mesma rota vence a genérica). A conta mora em
`nexus/contratos/contestacoes.py`; a view e o template, aqui.

## Contestações

Levi, 13/10/2026: "Contestação ligada ao Nexus: em contratos e clientes no Nexus pode ter um lugar para essas
contestações separando setores!"; "ficaria na API do PG, pode aplicar e construir!".

**De onde vem.** O cliente contesta um dia no Dashboard Thopen (5080): clica na barra do dia no gráfico Energia ×
Irradiação e marca geração, disponibilidade, desligamento, string, tracker e/ou ronda. O 5080 avisa no Teams (ronda →
O&M › Zeladoria, o resto → O&M › Performance) e grava no banco o livro `thopen_contestacoes` · `contestacoes`
(`thopen/contestacao_banco.py` do repositório da plataforma). O 5080 é a FONTE; no catálogo, fato
`contestacao_cliente` (área `contratos`), registrado antes da 1ª gravação; "quem grava" = Dashboard Thopen (5080)
(`telas.QUEM_GRAVA_ORIGEM`).

**Grão.** 1 linha = 1 contestação × 1 setor (as mesmas mensagens do Teams). Colunas: `id`, `contestacao_id` (junta as
duas linhas quando o cliente marcou dos dois lados), `recebida_em` (UTC), `data_id_recebida`, `data_id_contestada_ini` e
`_fim`, `usina` (o nome do 5080), `usina_id` (o de-para do 5080; vazio quando a usina tem dois ids, como Primavera),
`setor`, `itens` (só os do setor, `;`), `avisado_teams` (sim/não: o Teams do setor recebeu), `origem`
(`dashboard_thopen`) e `dados_cifrados`.

**O que é do cliente vai só cifrado** (regra 8: a API do banco tem leitura aberta): nome, contato, mensagem e o que ele
via na tela naquele dia (geração, irradiação, disponibilidade, trackers, strings, comentário, ronda) num JSON em
`dados_cifrados`. Cifra **assimétrica** (X25519 + HKDF-SHA256 com a pública efêmera de sal + AES-256-GCM; prefixo
`cx1:`): o 5080, público, tem só a chave PÚBLICA (`THOPEN_CONTESTACAO_CHAVE_PUBLICA`) e não abre nada, nem o que ele
mesmo gravou; o Nexus abre com a PRIVADA (`NEXUS_CONTESTACAO_CHAVE_PRIVADA`, opcional no `config.py`). A cifra é presa à
linha (contexto `thopen_contestacoes/<id>/dados` como dado associado): copiada para outra linha, "não abre". O decifrado
vive só na memória da tela. Sem a chave, a tela lista as contestações com "cifrado" no lugar do cliente e diz por quê.
**O par de 13/10/2026** está em `C:\GridcoAuto\entrega-ti\contestacoes-chaves-2026-10-13\` (a privada no
`.segredo`, nunca impressa): perder a privada é perder o que já foi gravado; a cópia em cofre é item da virada.

**A tela.** Uma aba por setor (Performance, Zeladoria) com a contagem; a mais nova em cima: quando chegou (Brasília), a
usina, o dia contestado, o que contesta, o cliente e o contato, a mensagem, o que ele via na tela e se o Teams do setor
recebeu ("não recebeu" = a contestação só está aqui). Tela nova nasce FECHADA para os setores (Base → Acessos): o
administrador vê; marcar "Contestações" para Performance e Zeladoria.

**Ainda não tem** (fica para quando o Levi pedir): marcar como respondida/quem respondeu (seria um livro do Nexus,
`nexus_contestacoes_tratamento`, registrado antes de criar), filtro por usina ou cliente, outros dashboards.

**Como provar.** `python -m pytest -q tests/test_contratos_contestacoes.py` (banco falso; com
`PLATAFORMA_REPO=<clone da plataforma>` o teste cruzado cifra com o código do 5080 e abre aqui). Em 13/10/2026, ponta a
ponta no banco de verdade: uma contestação TESTE pelo clique no gráfico do 5080 de ensaio (Guaratinguetá V, 06/10,
Geração + Ronda) gravou 2 linhas (Performance e Zeladoria); lida pela API aberta, nenhum nome, e-mail, mensagem ou kWh
em claro; esta tela, com a privada, abriu as duas. Essa linha TESTE ficou no livro (mensagem "Pode desconsiderar").
