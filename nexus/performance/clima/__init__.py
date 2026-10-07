"""Clima e risco (06/10/2026): alertas públicos por usina, sem Flask. Ver `nexus/performance/CLAUDE.md`, seção "Clima e risco".

Fase 1 só lê, e nada é gravado no banco: aviso do INMET, foco de queimada e risco de fogo do INPE, cruzados com as
coordenadas do cadastro. Previsão e testes de irradiância ficam para a fase 2 (dependem da licença do Open-Meteo).

    geometria   ponto em polígono e distância, em Python puro (sem shapely)
    geotiff     leitor mínimo do GeoTIFF do INPE (sem rasterio): o Pillow não abre o arquivo, que é float de 64 bits
    fontes      os três clientes públicos
    alertas     as regras: aviso que contém a usina, foco a até 5 km, classe do risco de fogo
    leitura     cache por fonte (TTL, janela de falha, uma busca por vez, última leitura boa)
    usinas      usinas em operação e coordenadas, do cadastro
    mapa        o Mapa de risco: contorno do IBGE, projeção, recorte por região e as camadas do SVG
    visao       o que a tela mostra
"""
