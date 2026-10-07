"""Clima e risco (06/10/2026): alertas públicos por usina, sem Flask. Ver `nexus/performance/CLAUDE.md`, seção "Clima e risco".

Fase 1 só lê, e nada é gravado no banco: aviso do INMET, foco de queimada e risco de fogo do INPE, cruzados com as
coordenadas do cadastro em três níveis (Agir agora, Atenção, Sem alerta; 07/10). A página de cada usina acrescenta a irradiação
diária da NASA POWER (07/10, grátis, sem chave, medida contra as ETMs de 40 usinas). Previsão de irradiância e a comparação com
a ETM de cada usina ficam para a próxima etapa.

    geometria   ponto em polígono e distância, em Python puro (sem shapely)
    geotiff     leitor mínimo do GeoTIFF do INPE (sem rasterio): o Pillow não abre o arquivo, que é float de 64 bits
    fontes      os quatro clientes públicos (INMET, focos, risco de fogo, NASA POWER)
    alertas     as regras: aviso que contém a usina, foco a até 5 km, classe do risco de fogo, os três níveis
    leitura     cache por fonte (TTL, janela de falha, uma busca por vez, última leitura boa); a NASA, um por usina
    irradiacao  a série dos últimos 30 dias, o mês até agora e a geometria do gráfico (puro)
    usinas      usinas em operação e coordenadas, do cadastro
    mapa        o Mapa de risco: contorno do IBGE, projeção, recorte por região e as camadas do SVG
    visao       o que a tela e a página da usina mostram
"""
