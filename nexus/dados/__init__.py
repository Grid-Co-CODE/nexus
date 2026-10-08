"""A camada de dados do Nexus: dimensões conformadas e fatos com IDs (método Kimball). Regras em `CLAUDE.md` desta pasta.

- `catalogo.py`: a matriz de barramento como dado (fonte única da tela, dos testes e da documentação): fatos com tipo,
  chave e medidas, dimensões e os livros do Nexus (registrados antes de existir).
- `calendario.py`, `historico.py`: as dimensões que o Nexus gera (data, feriados, histórico SCD2 de pessoas e usinas).
- `equipamento.py`: a dimensão de equipamento (código do ativo do Fracttal) e os apelidos de cada sistema.
- `fatos.py` (fechamento e a qualidade), `fato_ronda.py`, `fato_pt.py`, `programacao.py`, `geracao.py`: os fatos;
  `dominios.py`: as listas fechadas de valores. `livros.py`: ler e gravar na API do banco, conferindo.
- `carga.py`: a carga de hora em hora (aos :40) e a montagem diária da geração. `telas.py`: Base → Governança de dados.
"""


def instalar(app) -> None:
    """Liga a carga de hora em hora onde há o token de escrita. Quem chama é o app.py e o servir.py, nunca o
    create_app: os testes não podem ligar nada que fale com a rede. `NEXUS_CARGA_DADOS=0` desliga nesta máquina."""
    if app.config.get("TESTING") or not app.config.get("GRIDCO_SQL_TOKEN"):
        return
    if str(app.config.get("NEXUS_CARGA_DADOS") or "").strip() == "0":
        return
    from .carga import ligar
    ligar(app)
