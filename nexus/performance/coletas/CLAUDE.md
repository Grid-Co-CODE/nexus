# CLAUDE.md — Coletas (Performance > Coletas)

O Conversor Grid Co. (o .exe do backoffice) dentro do Nexus (Levi, 11/11/2026: "Quero uma aba na performance do nexus de
controle de coleta! monte com base no .exe"; antes: "faz a mesma coisa que faz nas coletas só que lá no nexus, ficaria mais
fácil para todo mundo, e leria direto do PG!"). A pessoa solta os relatórios de portal, SCADA ou datalogger; a tela
reconhece a fonte e a usina pelo conteúdo e devolve a planilha para colar no BD_Performance ou no BD_Thopen. **Nada vai
ao BD nem ao banco por aqui**: o BD segue a fonte (regra de 11/10/2026) e o `sync-xlsx?replace=true` da coleta apagaria
qualquer gravação direta na subida seguinte. O .exe segue de reserva até esta tela estar redonda (regra de 04/10/2026).

## Peças

| Arquivo | Para quê |
|---|---|
| `_motor/conversor/` | o motor do Conversor, **cópia idêntica** (byte a byte) da pasta da coleta (`coleta API PV\ferramentas\conversor\conversor`, menos o `app.py` da janela). Não edite aqui: mude lá e rode `python ferramentas/sincronizar_conversor.py` |
| `motor.py` | põe `_motor/` no caminho como o pacote `conversor` (é como os leitores se importam); importe-o antes de qualquer `conversor.*` |
| `pg.py` | o BD lido do banco com a cara do `nucleo.BD` do Conversor (`abas`, `aba`, `estilos`, `lido_em`), com o mapa de fórmulas por cima; uma leitura por subida, guardada 10 min |
| `servico.py` | uma `Sessao` do Conversor por navegador (a pasta temporária dela, os envios em lotes, o reconhecimento em fundo, o BD em Excel solto junto, o separar formato novo) e a leitura do relatório de furos |
| `nexus/torres/performance/coletas_tela.py` | as rotas: a casca (`/coletas`), a página do Conversor (`/coletas/app`), `/coletas/api/<método>` (a lista `METODOS`), `/coletas/arquivo`, `/coletas/planilha/<i>`, `/coletas/furos` |
| `templates/performance/coletas_app.html` e `static/coletas/furos.js` | **GERADOS** da tela do .exe por `ferramentas/portar_tela_conversor.py` (as trocas e o porquê de cada uma estão lá). Não edite: mude o .exe e rode o `sincronizar_conversor.py` |

A regra (leitores, regras de colar, planilha de saída) é a do Conversor: leia o `CLAUDE.md` da pasta do Conversor na
coleta antes de mexer num leitor. Aqui só mora o que muda por ser um servidor.

## O BD vem do banco — e por que precisa do mapa de fórmulas

O banco (`db_performace`) tem, de cada aba, o número da linha no Excel (`row_number`), o cabeçalho, os valores e a hora
da subida (`updated_at`): basta para dizer "cole na célula C123" e não cobrir dado. **Não tem fórmula nem cor**: o
`sync_gridco_api.py` da coleta sobe só valores (decisão de 27/08/2026), e a fórmula sem valor em cache chega vazia. O
Conversor depende de toda fórmula, célula a célula (a mesma coluna é valor num dia e fórmula no outro: a Energia da Nova
Iguaçu é digitada até 08/11/2026 e `=SUM(T_Nova_Iguaçu[[#This Row],...]])` a partir de 09/11): não escreve em célula que é
fórmula (o IPOA da Vitesse = Hortina; o da Salvales de 21 a 25/10 = Carosa) e parte o bloco de colar onde ela aparece.

A escolha do Levi (11/11/2026, "Aceito também sua recomendação"): **a coleta sobe, na mesma subida de cada BD, o livro
`bd_formulas`** (registrado em `CONHECIDAS` do `nexus/dados/catalogo.py` antes de existir):
- `formulas_bd_performance` / `formulas_bd_thopen`: 1 linha por célula que é fórmula no Excel —
  `aba, linha (do Excel), coluna (1-based), cabecalho, formula (o texto, com "="), subida_em`;
- `abas_bd_performance` / `abas_bd_thopen`: 1 linha por aba do Excel naquela subida — `aba, linhas, colunas, subida_em`.

Sem o mapa, ou com o mapa de outra subida (mais de 30 min antes do `updated_at` do BD), **o BD do banco não é usado**: o
botão do BD fica vermelho, a faixa diz o motivo, e a pessoa solta o BD em Excel junto com os arquivos (ou clica no botão
do BD) — o mesmo caminho do .exe. Quem sobe o mapa é a coleta (chat Coleta de Dados); até ele existir, a tela funciona
só com o Excel solto.

- **Abas velhas:** a aba renomeada no Excel fica velha no banco (o `replace=true` só troca as abas que sobem: "Vitesse",
  "Carosa", "Salvales", "Hortina" e "SunPower" pararam em 30/09/2026; hoje são "Quixadá 2 (Vitesse)", "Aquiraz 2
  (Carosa)", "Aquiraz 1 (Salvales)", "Quixadá 1 (Hortina)" e "Cascavel (Sunpower)"). Vale só a aba da lista `abas_<bd>`.
- **A cor não sobe:** a planilha de colar sai sem o amarelo e o vermelho do BD. A regra de não cobrir dado olha o valor.
- **O banco anda atrás do Excel:** o que a equipe digitou depois da última subida não está lá. Toda conversão com o BD
  do banco leva o aviso "veio do banco, da subida de dd/mm às HH:MM: confira os dias de dd/mm em diante".

## O que muda por ser um servidor

- **Uma sessão por navegador** (`session["coletas_id"]`, nada de e-mail na chave), com a pasta temporária dela; some
  parada há 3 h ou no Limpar / Nova conversão. Os arquivos soltos não ficam no Nexus, salvo o formato que ninguém
  conhece: "separar para o Levi" grava em `<NEXUS_DADOS>/coletas/formatos_novos/` (no .exe era a pasta ao lado do BD).
- **Um arquivo por pedido** (o teto de envio do Nexus é 25 MB por pedido): a tela abre um lote, sobe cada arquivo e fecha
  o lote; as partes do mesmo datalogger ficam na mesma pasta do lote (os leitores da Apolo e da Polaris procuram as irmãs
  ali). O arquivo maior que 25 MB fica de fora com aviso.
- **A data do arquivo é a do computador de quem soltou** (`File.lastModified` -> `os.utime`): o "só dia fechado" usa a
  data do arquivo como a hora da baixa (o mensal da Sal baixado 08/11 12:41 traz o 08/11 pela metade).
- **O BD em Excel solto junto** (nome `BD_Performance*.xlsx` / `BD_Thopen*.xlsx`, ou pelo botão do BD) entra no lugar do
  banco para aquela sessão; o Limpar volta ao banco. **A leitura do banco nunca passa por cima do Excel** (12/11/2026, o 1º
  uso do Levi: o BD_Thopen em Excel entrou enquanto o banco era lido em fundo, e a leitura, terminando depois, o tirou; a
  conversão saiu com "BD_Thopen não foi lido"): a troca é sob a trava da sessão e o banco só entra onde não há Excel.
- **Furos de coleta:** o relatório `Furos_Coleta_Performance_*.html` (gerado fora) sobe pelo "Abrir relatório" e fica em
  `<NEXUS_DADOS>/coletas/furos/`: todos veem o mesmo (como a pasta da equipe no .exe). As confirmações de cada pessoa
  ficam no navegador dela (como no HTML original); **confirmação compartilhada é dado novo no banco**: catálogo antes e
  decisão do Levi.

## Os filtros dos Furos: o modelo do Histórico de OS (12/11/2026)

Levi: "arrume esses filtros para ficar no padrão exatamente dos filtros de Histórico de OS com o mesmo estilo e
funcionalidades!". `static/coletas/filtros.js` monta, por fora da tela gerada, o modelo A do Histórico (README do OS Creator,
"Os filtros do Histórico só valem no Aplicar"), com o CSS da Zeladoria (`static/zeladoria/filtros.css`, as `zf-*`, a cópia do
Histórico) e a barra em `static/coletas/coletas.css`: a busca na barra (filtra enquanto se digita), o botão Filtros com a
contagem verde (a busca não conta), o painel suspenso com Aplicar (nada filtra antes), o ponto no campo que mudou, as
etiquetas azuis com × (aplica na hora) e o Limpar tudo (os filtros, a busca e os da coluna da tabela); Esc e clique fora
descartam. Cliente, Carteira, Fonte, Status e Situação são **listas digitáveis de marcar vários** (nenhum = todos; a
Situação passa a usina que cumpre QUALQUER uma das marcadas); as três chaves que mudam a conta (zerado como furo, OS como
ausência esperada, confirmados como OK) ficam no painel como marcas, com etiqueta quando desligadas. O `furos.js` gerado
lê os vários valores pelas trocas `FUROS_VARIOS` do `portar_tela_conversor.py` (os `<select>` do .exe viram `multiple`).
Nenhum filtro novo nem padrão novo: os mesmos campos do .exe. As caixas "Falta: Inversores / IPOA / GHI" do 1.0.10
entram no painel como marcas (ligadas = sem filtro, etiqueta quando desligadas).

**1.0.12 (13/11/2026), a tela 3 enxuta do .exe:** abre no "Para coletar"; na frente, Mês, busca, Fonte, Falta e 4 números;
o resto no "Mais filtros" (details), no "Mais opções" (menu) e no "Como ler esta tela". No Nexus a barra da frente fica e
o `filtros.js` põe nela, depois do Mês, a busca com lupa e o botão Filtros; Fonte, Falta, o "Mais filtros" e o "Limpar
filtros" do .exe ficam escondidos (`cf-oculto`), porque estão no painel e nas etiquetas. O "Filtro em cada coluna da
tabela" (`fzColF`) é marca com padrão DESLIGADO (o 3º item de `MARCAS`).

## As abas "Para coletar" (1.0.10) e "Baixa performance" (1.0.11), 13/11/2026

As duas precisam do Python além do relatório de furos; no .exe usam o BD que a janela leu, aqui:

- **Onde buscar no portal** (`/coletas/furos/portal` -> `servico.furos_portal`): a aba Equipamentos do BD_Performance. Com
  o Excel solto, o `furos.portal` do .exe; sem ele, a mesma aba no banco (`bd_performance · Equipamentos`, guardada 10 min),
  lida por `portal_de_linhas`, que repete a leitura do .exe linha a linha. Prova de 13/11: banco = Excel, 131 usinas.
- **Ronda** e **confirmações** ficam no navegador de cada pessoa (localStorage `nexus.coletas.furos.ronda` / `.conf`):
  no .exe era o `furos.json` do PC.
- **Mural** (`api/furos_mural` -> `servico.furos_mural`): a conta é o `mural.calcular` do .exe. Sem Excel solto, lê os
  **valores** do banco por `pg.BDdoBanco(so_valores=True)`: ler não precisa do mapa de fórmulas (que só protege a
  colagem), então o mural funciona mesmo antes do `bd_formulas` existir. A potência (kWh/kWp) vem da mesma aba
  Equipamentos (`potencias_de_linhas` = `mural.potencias`). A 1ª conta lê o BD inteiro do banco: **~40 s e pico de ~60 MB**
  (medido 13/11); o resultado fica guardado por (mês, ontem, subida de cada BD) e o BD é solto. Prova de 13/11 até 11/11:
  193 inversores, 177 iguais ao .exe com os BDs em Excel; os 16 restantes eram a Segredo de 11/11, mudada no Excel às 09:21
  depois da subida (01:19): diferença de dado, não de regra.
- Trazer uma versão do .exe que a Coleta ainda está mexendo: a pasta pode ter trabalho sem release (o `mural.py` estava lá
  antes da 1.0.11). Sincronize do commit da release (`git archive <release>` da pasta `ferramentas/conversor/conversor`
  para fora e `--origem` nela, mantendo o fim de linha da pasta) ou espere a pasta ficar limpa.

## Como provar

- `python -m pytest -q tests/test_coletas.py`. O que importa: `test_o_bd_do_banco_da_a_mesma_conversao_que_o_excel`
  monta o banco a partir de um Excel com fórmulas (valores-only, como a subida faz) e confere que a tabela, os avisos e
  o bloco colado (Ctrl+V em Python, célula a célula) são **iguais** aos do BD lido do Excel, com a fórmula do IPOA intocada.
- `test_a_copia_e_a_tela_batem_com_a_pasta_da_coleta` quebra quando o .exe mudou e a cópia não (pula no servidor).
- Na tela: soltar um relatório da Sal com o BD em Excel; o botão do BD diz "Excel · dd/mm HH:MM"; o resultado igual ao
  do .exe com o mesmo arquivo e o mesmo BD.
