# O mapa das usinas na Visão geral (desenho)

Levi, 18/10/2026: "Próximas peças: o mapa das usinas e as ocorrências com plano de ação. siga! Para o mapa podemos usar o
IBGE como a performance faz". O painel próprio de um supervisor tinha um painel "Localização" (mapa e lista das usinas, com
endereço e link do mapa).

## Decisões do Levi (quiz de 18/10/2026)

- **Lugar:** Lista | Mapa dentro da Visão geral, com os mesmos filtros (responsável, cliente, busca, equipe, o filtro do
  clique) e o mesmo clique nos blocos.
- **Cor do ponto:** o nível do bloco clicado; sem bloco, o nível da usina (o pior dos três).
- **Clique no ponto:** abre ao lado o resumo da usina (os alertas dos três blocos) e o link para a linha dela na lista.
- **Clima:** só as usinas; o clima segue no Mapa de risco da Performance.

## Decisões do construtor

- **O desenho do Mapa de risco** (`nexus/performance/clima/mapa.py`): o contorno dos estados do IBGE guardado no Nexus, a
  mesma projeção, o SVG feito no servidor. Nada de biblioteca de mapa nem de busca ao IBGE em tempo de execução.
- **A coordenada nunca vira texto:** ela abre só no servidor (`performance/clima/usinas.do_app`, o cadastro cifrado), e o
  navegador recebe o desenho. Por isso não há endereço nem link "como chegar" (no painel do supervisor havia).
- **O recorte:** os estados que têm usina na lista (o supervisor do Paraná vê o Paraná), com o ponto de cada usina dentro.
- **Usina sem coordenada** não some: o lado do mapa lista os nomes, para alguém corrigir o cadastro.
- **Sem o cadastro nesta máquina** (o teste, o PC sem o armazém), o mapa diz por quê e a lista continua.
- **O clique é um link** (`?ver=mapa&usina=<id>`), sem JavaScript, como o resto da tela.
