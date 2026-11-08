"""Os fechamentos que o Nexus calcula, na API do PG (db_performace), workbook `campo_nexus` (Levi, 04/10/2026: "não
aceito esse JSON como banco de dados pois temos a API do PG"; "pode gravar na API do PG e ligar as telas").

Uma linha por TAREFA que entrou na fila de verificação do Fracttal: a nota da régua do App calculada com o que o
Fracttal guarda (nota_fracttal.py) e os campos do Fracttal que as telas usam, os mesmos que o `_enriquecer_qlog` do App
copia toda madrugada para o registro dele (tipo, criticidade, status, área, ativo, datas, durações, avaliação).

O nome do técnico vai CIFRADO (NEXUS_CHAVE_CADASTRO, o cofre do cadastro): a leitura da API não pede credencial. Sem a
chave, vai só o id do Fracttal. E-mail não vai: quem casa o técnico com o cadastro é a tela, na hora.

Só a LEITURA vive aqui: o coletor que gravava este workbook saiu do código em 08/11/2026 (aposentado desde 05/10); o
livro que ele deixou no banco é a reserva da fonte das telas (`fonte_pg.py`).
"""
WORKBOOK = "campo_nexus"
ABA = "fechamentos"
ABA_ATUALIZACAO = "atualizacao"
# Levi, 05/10/2026: "esses dados de ronda têm sim que ir para a API, guardados como informação de ronda, salvando o
# número da OS e todas essas informações". Uma linha por OS de ronda, com o que o App escreveu nela no Fracttal.
ABA_RONDAS = "rondas"
BASE_API = "https://app.gridco.com.br/db_performace"

INTEIRAS = ("id_tarefa", "id_os", "tecnico_id", "status_os", "status_tarefa", "dur_prev_min", "dur_real_min", "rating",
            "nota", "nota_placar", "pontos_placar", "n_fotos", "n_desc", "ronda_duracao_min", "usina_id", "pessoa_id")
SIM_NAO = ("pelo_app", "ronda", "gps_fotos", "sub_ok", "todas_sub", "obs_ok", "devolvida", "completa", "ronda_lida")
COLUNAS = ("id_tarefa", "os", "id_os", "tarefa", "tecnico_id", "tecnico_cifrado", "usina_id", "pessoa_id", "equipe",
           "regiao", "ativo", "codigo",
           "tipo", "crit", "status_os", "status_tarefa", "inicio", "fim", "verificacao", "aprovacao", "dur_prev_min",
           "dur_real_min", "rating", "pelo_app", "ronda", "ronda_dia", "ronda_usina", "ronda_duracao_min", "ronda_hora_ini",
           "ronda_hora_fim", "ronda_respostas", "ronda_pendencias", "ronda_lida", "nota", "nota_itens", "nota_placar",
           "pontos_placar", "n_fotos", "n_desc", "gps_fotos", "sub_ok", "todas_sub", "obs_ok", "devolvida", "lido_em",
           "regua")


def _int(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _sim_nao(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("sim", "true", "1")


def normalizar(linha: dict) -> dict:
    """A linha no formato do Nexus: inteiros como int, sim/não como bool, vazio como None."""
    out = {}
    for c in COLUNAS:
        v = linha.get(c)
        if c in INTEIRAS:
            v = _int(v)
        elif c in SIM_NAO:
            v = _sim_nao(v)
        elif v is not None:
            v = str(v)
            v = v if v.strip() else None
        out[c] = v
    return out


def _abas(base, s) -> dict:
    r = s.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    return {x["sheet_name"]: x["id"] for x in r.json() if x.get("workbook_key") == WORKBOOK}


def _linhas_da_aba(base, s, sid) -> list[dict]:
    out, offset = [], 0
    while True:
        r = s.get(f"{base}/api/sheets/{sid}/rows", params={"limit": 1000, "offset": offset}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        out += [dict(zip(x.get("headers") or [], x.get("values") or [])) for x in rows]
        if len(rows) < 1000:
            return out
        offset += 1000


def ler_tudo(base: str = BASE_API, sessao=None) -> tuple[dict, dict]:
    """({id_tarefa: linha}, a linha da aba de atualização). Workbook ainda inexistente = vazio."""
    import requests
    s = sessao or requests
    base = base.rstrip("/")
    abas = _abas(base, s)
    out, atualizacao = {}, {}
    if ABA in abas:
        for bruta in _linhas_da_aba(base, s, abas[ABA]):
            l = normalizar(bruta)
            if l["id_tarefa"] is not None:
                out[l["id_tarefa"]] = l
    if ABA_ATUALIZACAO in abas:
        atualizacao = next(iter(_linhas_da_aba(base, s, abas[ABA_ATUALIZACAO])), {})
    return out, atualizacao


def ler_rondas(base: str = BASE_API, sessao=None) -> list[dict]:
    """As linhas da aba de rondas, como a API devolve."""
    import requests
    s = sessao or requests
    base = base.rstrip("/")
    abas = _abas(base, s)
    return _linhas_da_aba(base, s, abas[ABA_RONDAS]) if ABA_RONDAS in abas else []


def ler(base: str = BASE_API, sessao=None) -> dict:
    """{id_tarefa: linha} do que está no banco."""
    return ler_tudo(base, sessao)[0]
