"""A conferência das ligações: o que está GRAVADO no banco aponta para algo que existe?

Levi, 12/11/2026: "Quero uma análise das relações de dados e se as bases estão sendo lincadas da maneira correta". A
qualidade de cada fato (`fatos.qualidade`) diz quanto LIGOU na hora de montar; ninguém conferia depois se o ID gravado
ainda existe na dimensão, nem se a chave do fato se repete no que está no banco. A medida daquele dia foi feita à mão
(GET no banco inteiro, ~3 min): nos 19 fatos com IDs, nenhum ID órfão e nenhuma chave repetida, e dois achados que só ela
viu: 2.197 OS da FAMA com a data fora do calendário (o `dim_data` começava em 2025) e 3 linhas da programação com um
equipamento que a dimensão não tem. Aqui a mesma conferência roda sozinha, uma vez por dia, e a Governança mostra.

O que é conferido, tabela a tabela, lendo o banco PÁGINA A PÁGINA (a memória não cresce com a tabela; o Nexus é um
processo só e o servidor anda apertado):
- toda aba `fato_*` dos livros do Nexus (`nexus_*`) e as dimensões que apontam para outra (`TABELAS_FIXAS`); do livro de
  uma família por período (`nexus_geracao_inversor_AAAA_MM`), só o mais novo; a posição das pessoas
  (`nexus_equipe_pontos_*`) não é lida;
- cada coluna de ID (`alvo_da_coluna`): quantas linhas têm o ID e quantas apontam para um ID que a dimensão não tem (o
  ÓRFÃO). O `99991231` (vigente) e o `19000101` (início presumido) do histórico não são datas do calendário;
- a chave do fato, a do catálogo (`Fato.chave`): quantas linhas repetem uma chave que já apareceu.

Só conta: nenhum valor sai daqui (a API do banco tem leitura aberta, regra 8). Grava o resultado em
`nexus_conferencia · qualidade` (1 linha = 1 coluna de ID, ou a chave, de 1 tabela, na última conferência) e
`atualizacao`. A conferência que falha numa tabela diz o tipo do erro na linha dela e segue (regra 13).
"""
import logging
import re
import socket
import time
from datetime import datetime, timedelta, timezone

from . import catalogo, livros

log = logging.getLogger("nexus.dados")

LIVRO, NOME = "nexus_conferencia", "Nexus · conferência das ligações (ID órfão e chave repetida no que está gravado)"
ABA = "qualidade"
CAB = ["tabela", "fato", "coluna", "dimensao", "linhas", "preenchido_qtd", "orfaos_qtd", "orfaos_distintos_qtd",
       "chave_repetida_qtd", "erro", "conferido_em"]
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "tabelas_qtd", "colunas_qtd", "orfaos_qtd", "chave_repetida_qtd",
                   "como_ler"]
COMO_LER = ("1 linha = 1 coluna de ID (ou a chave) de 1 tabela; orfaos_qtd = linhas cujo ID não existe na dimensão; "
            "chave_repetida_qtd = linhas além da 1ª com a mesma chave")
CHAVE = "(chave)"
INTERVALO_H = 20                    # uma conferência por dia: a que tem menos de 20 h não se repete
_BRT = timezone(timedelta(hours=-3))
# a dimensão de cada alvo: (livro, aba, coluna do ID)
DIMENSOES = {"usina": ("cadastro_nexus", "usinas", "usina_id"), "pessoa": ("cadastro_nexus", "pessoas", "pessoa_id"),
             "equipe": ("cadastro_nexus", "equipes", "equipe_id"), "cliente": ("cadastro_nexus", "clientes", "cliente_id"),
             "data": ("nexus_dimensoes", "dim_data", "data_id"),
             "equipamento": ("nexus_equipamentos", "dim_equipamento", "equipamento_id")}
# as dimensões que apontam para outra dimensão (a própria coluna de ID de cada uma fica de fora: `propria`)
TABELAS_FIXAS = (("cadastro_nexus", "usinas", "usina_id"), ("cadastro_nexus", "pessoas", "pessoa_id"),
                 ("nexus_equipamentos", "dim_equipamento", "equipamento_id"),
                 ("nexus_equipamentos", "equipamento_apelido", None),
                 ("nexus_estrutura_usina", "dim_supervisorio", None), ("nexus_estrutura_usina", "dim_cabine", None),
                 ("nexus_estrutura_usina", "dim_inversor", None),
                 ("nexus_dimensoes", "usinas_historico", None), ("nexus_dimensoes", "pessoas_historico", None))
NAO_LER = ("nexus_equipe_pontos",)              # a posição de cada pessoa (LGPD): não se lê para contar
FORA_DO_CALENDARIO = (99991231, 19000101)       # o vigente e o início presumido do histórico
_FAMILIA = re.compile(r"_\d{4}_\d{2}(_\d{2})?$")


def _id(v):
    """O ID como o banco o devolve (93, 93.0, "93", "93.0") num inteiro; o que não é número fica texto; vazio = None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, float):
        return None if v != v else (int(v) if v.is_integer() else v)
    if isinstance(v, int):
        return v
    t = str(v).strip()
    if not t or t.lower() in ("none", "nan", "null"):
        return None
    m = re.fullmatch(r"(-?\d+)(?:\.0+)?", t)
    return int(m.group(1)) if m else t


def alvo_da_coluna(coluna: str) -> str | None:
    """A dimensão para a qual a coluna aponta, pelo nome dela (a regra 3 da casa: `data_id`, `usina_id`, `equipe_id`,
    `pessoa_id`, `equipamento_id`, com o papel depois ou antes), ou None. A linhagem (`usina_ligada_por`) e o HMAC não são
    ID. `geracao_usina_id` é a chave do fato de geração e `fama_tipo_equipe_id` é do catálogo da FAMA: por isso a usina e
    a equipe só valem pelo nome exato (ou `usina_id_<papel>`), não por terminar assim."""
    c = str(coluna or "").strip().lower()
    if not c or "ligad" in c or c.endswith(("_hmac", "_chave")):
        return None
    if c.startswith("data_id") or c in ("valido_de_id", "valido_ate_id"):
        return "data"
    if c == "usina_id" or c.startswith("usina_id_"):
        return "usina"
    if "pessoa_id" in c:
        return "pessoa"
    if c in ("equipe_id", "cliente_id", "equipamento_id"):
        return c[:-3]
    return None


def fato_da_tabela(livro: str, aba: str):
    """O fato do catálogo que mora (ou nasce) nesta tabela, ou None. O livro de uma família (`..._AAAA_MM`) casa pelo molde."""
    fam = _FAMILIA.sub("", livro)
    for f in catalogo.FATOS:
        for alvo in (f.conformado_em, f.livro):
            p = [t.strip() for t in str(alvo or "").split("·")]
            if len(p) < 2 or aba not in [t.strip() for t in p[1].split(",")]:
                continue
            molde = re.sub(r"_AAAA_MM(_DD)?$", "", p[0])
            if p[0] == livro or (molde != p[0] and molde == fam):
                return f
    return None


def tabelas_a_conferir(abas: dict) -> list[tuple]:
    """[(livro, aba, a coluna do próprio ID ou None)] da listagem do banco ({(livro, aba): meta}), em ordem: as fixas que
    existem, depois os fatos do Nexus; de cada família, só o livro mais novo."""
    out = [(l, a, propria) for l, a, propria in TABELAS_FIXAS if (l, a) in abas]
    novo = {}
    for livro, aba in sorted(abas):
        if not livro.startswith("nexus") or not aba.startswith("fato_") or livro.startswith(NAO_LER):
            continue
        fam = _FAMILIA.sub("", livro)
        if fam == livro:
            out.append((livro, aba, None))
        elif novo.get((fam, aba), "") < livro:
            novo[(fam, aba)] = livro
    return out + [(livro, aba, None) for (_fam, aba), livro in sorted(novo.items())]


def _paginas(base, sessao, sid):
    offset = 0
    while True:
        rows = livros.pagina(base, sessao, sid, offset)
        yield rows
        if len(rows) < livros.PAGINA:
            return
        offset += livros.PAGINA


def ids_da_dimensao(base, sessao, abas: dict, alvo: str) -> set | None:
    """Os IDs que a dimensão tem, ou None quando ela não está no banco (a coluna que aponta para ela não é conferida)."""
    livro, aba, col = DIMENSOES[alvo]
    if (livro, aba) not in abas:
        return None
    out = set()
    for pg in _paginas(base, sessao, abas[(livro, aba)]["id"]):
        out.update(_id(x.get(col)) for x in pg)
    out.discard(None)
    return out


def conferir_tabela(paginas, dims: dict, chave=(), propria: str | None = None) -> dict:
    """{"linhas", "colunas": {coluna: {alvo, preenchido, orfaos, distintos}}, "repetidas"} de uma tabela lida em páginas
    (listas de dicionários). `dims` = {alvo: conjunto de IDs, ou None = dimensão fora do banco}. `repetidas` = None
    quando o fato não tem chave no catálogo ou a tabela não traz as colunas dela."""
    cols, n, vistos, repetidas, orf = None, 0, set(), 0, {}
    tem_chave = False
    for pg in paginas:
        for x in pg:
            if cols is None:
                cols = {c: alvo_da_coluna(c) for c in x if c != propria}
                cols = {c: {"alvo": a, "preenchido": 0, "orfaos": 0} for c, a in cols.items()
                        if a and dims.get(a) is not None}
                orf = {c: set() for c in cols}
                tem_chave = bool(chave) and all(k in x for k in chave)
            n += 1
            for c, m in cols.items():
                v = _id(x.get(c))
                if v is None:
                    continue
                m["preenchido"] += 1
                if m["alvo"] == "data" and v in FORA_DO_CALENDARIO:
                    continue
                if v not in dims[m["alvo"]]:
                    m["orfaos"] += 1
                    orf[c].add(v)
            if tem_chave:
                k = tuple(str(_id(x.get(c))) for c in chave)
                if k in vistos:
                    repetidas += 1
                else:
                    vistos.add(k)
    for c, m in (cols or {}).items():
        m["distintos"] = len(orf[c])
    return {"linhas": n, "colunas": cols or {}, "repetidas": repetidas if tem_chave else None}


def conferir(base, sessao, agora: datetime | None = None) -> tuple[list[list], dict]:
    """(as linhas de CAB, o resumo) do banco como está agora. Só lê."""
    iso = (agora or datetime.now(_BRT)).isoformat(timespec="seconds")
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    abas = {(x["workbook_key"], x["sheet_name"]): x for x in r.json()}
    dims = {alvo: ids_da_dimensao(base, sessao, abas, alvo) for alvo in DIMENSOES}
    linhas, resumo = [], {"tabelas": 0, "colunas": 0, "orfaos": 0, "repetidas": 0, "erros": 0, "problemas": []}
    for livro, aba, propria in tabelas_a_conferir(abas):
        nome, f = f"{livro} · {aba}", fato_da_tabela(livro, aba)
        fid = f.id if f else None
        try:
            t = conferir_tabela(_paginas(base, sessao, abas[(livro, aba)]["id"]), dims, f.chave if f else (), propria)
        except Exception as e:      # noqa: BLE001 — uma tabela que não lê não para a conferência das outras (regra 13)
            log.warning("conferência das ligações: %s não foi lida (%s)", nome, type(e).__name__)
            linhas.append([nome, fid, None, None, None, None, None, None, None, type(e).__name__, iso])
            resumo["erros"] += 1
            continue
        resumo["tabelas"] += 1
        for c, m in t["colunas"].items():
            linhas.append([nome, fid, c, m["alvo"], t["linhas"], m["preenchido"], m["orfaos"], m["distintos"], None, None, iso])
            resumo["colunas"] += 1
            resumo["orfaos"] += m["orfaos"]
            if m["orfaos"]:
                resumo["problemas"].append({"tabela": nome, "coluna": c, "dimensao": m["alvo"], "linhas": t["linhas"],
                                            "orfaos": m["orfaos"], "distintos": m["distintos"]})
        if t["repetidas"] is not None:
            linhas.append([nome, fid, CHAVE, None, t["linhas"], None, None, None, t["repetidas"], None, iso])
            resumo["repetidas"] += t["repetidas"]
            if t["repetidas"]:
                resumo["problemas"].append({"tabela": nome, "coluna": CHAVE, "linhas": t["linhas"],
                                            "repetidas": t["repetidas"]})
    return linhas, dict(resumo, conferido_em=iso)


def ultima(base, sessao, abas: dict | None = None) -> dict | None:
    """O que a Governança mostra: a última conferência gravada ({gerado_em, tabelas, colunas, orfaos, repetidas, erros,
    problemas}), ou None quando ela ainda não rodou. A API pode devolver tudo como texto. `abas` = a listagem do banco
    que a tela já tem ({(livro, aba): meta}): com ela, nenhuma listagem a mais (cada uma custa ~0,5 a 1,5 s)."""
    def n(v):
        v = _id(v)
        return v if isinstance(v, int) else 0

    def ler(aba):
        if abas is None:
            return livros.ler(base, sessao, LIVRO, aba)
        m = abas.get((LIVRO, aba))
        return livros.linhas_da_aba(base, sessao, m["id"]) if m else []
    at = ler("atualizacao")
    if not at:
        return None
    a = at[-1]
    problemas, erros = [], 0
    for x in ler(ABA):
        if str(x.get("erro") or "").strip():
            erros += 1
        elif n(x.get("orfaos_qtd")):
            problemas.append({"tabela": x.get("tabela"), "coluna": x.get("coluna"), "dimensao": x.get("dimensao"),
                              "linhas": n(x.get("linhas")), "orfaos": n(x.get("orfaos_qtd")),
                              "distintos": n(x.get("orfaos_distintos_qtd"))})
        elif n(x.get("chave_repetida_qtd")):
            problemas.append({"tabela": x.get("tabela"), "coluna": CHAVE, "linhas": n(x.get("linhas")),
                              "repetidas": n(x.get("chave_repetida_qtd"))})
    return {"gerado_em": str(a.get("gerado_em") or ""), "tabelas": n(a.get("tabelas_qtd")), "colunas": n(a.get("colunas_qtd")),
            "orfaos": n(a.get("orfaos_qtd")), "repetidas": n(a.get("chave_repetida_qtd")), "erros": erros,
            "problemas": problemas}


def _velha(gerado_em, agora: datetime) -> bool:
    try:
        quando = datetime.fromisoformat(str(gerado_em))
    except ValueError:
        return True
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=_BRT)
    return agora - quando >= timedelta(hours=INTERVALO_H)


def rodar(config, sessao=None, *, gravar: bool = True, forcar: bool = False, agora: datetime | None = None) -> dict:
    """Confere e grava, no máximo uma vez a cada `INTERVALO_H` (o PC e o servidor podem estar no ar juntos: quem acha a
    conferência do dia feita não repete). Devolve o resumo, ou {"pulou": motivo}."""
    import requests

    from .conexao import base_de
    agora = agora or datetime.now(_BRT)
    base, s = str(base_de(config)).rstrip("/"), sessao or requests.Session()
    token = config.get("GRIDCO_SQL_TOKEN")
    if gravar and not token:
        return {"pulou": "sem a chave de gravação do banco (GRIDCO_SQL_TOKEN)"}
    if not forcar:
        at = livros.ler(base, s, LIVRO, "atualizacao")
        if at and not _velha(at[-1].get("gerado_em"), agora):
            return {"pulou": "já conferido hoje"}
    t0 = time.time()
    linhas, resumo = conferir(base, s, agora)
    resumo["duracao_s"] = round(time.time() - t0, 1)
    if gravar:
        livros.publicar(LIVRO, NOME, {
            ABA: (CAB, linhas),
            "atualizacao": (CAB_ATUALIZACAO, [[resumo["conferido_em"], socket.gethostname(), resumo["duracao_s"],
                                               resumo["tabelas"], resumo["colunas"], resumo["orfaos"],
                                               resumo["repetidas"], COMO_LER]])}, base=base, token=token, sessao=s)
    log.info("conferência das ligações: %s tabelas, %s colunas de ID, %s órfãos, %s chaves repetidas, %s s",
             resumo["tabelas"], resumo["colunas"], resumo["orfaos"], resumo["repetidas"], resumo["duracao_s"])
    return resumo
