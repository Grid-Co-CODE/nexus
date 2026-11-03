"""A cópia do Radar para os três livros do Nexus, a partir da exportação do Supabase.

A exportação é UM JSON feito pelo SQL Editor do Supabase, com um SELECT só (03/11/2026). Ela traz os dados de cada
tabela do esquema `radar_fornecedores`, a view das últimas rondas, os tipos das colunas e as chaves primárias. O
caminho do desenho era um papel só de leitura com senha; ele saiu porque a exportação faz o mesmo sem senha e sem mudar
nada no banco do Radar. A cópia lê esse arquivo, que fica fora do repositório, junto do de-para de nomes.

O que ela garante, e o caso de cada um:
- Tabela que o mapa não conhece ou que falta na exportação: para antes de gravar qualquer livro (`TabelaDesconhecida`,
  `ExportacaoIncompleta`). Dado que some calado é o pior caso.
- Os valores gravados com o primeiro nome de alguém são renomeados pelo MESMO de-para da ferramenta do clone
  (`ferramentas/zeladoria_limpar_clone.py`). Exemplos: a chave `previsto_decidido_<nome>` do config, o escopo
  `<nome>` dentro do JSON guardado como texto, a origem `planilha_<nome>`. Só vale em texto com cara de identificador,
  sem maiúscula, sem @, sem ponto; nome de gente e e-mail ficam como estão, cifrados.
- Cada livro é conferido antes e depois de gravar (`livros.publicar`), e o relatório traz a contagem da origem ao lado
  da do Nexus. A aba `atualizacao` de cada livro guarda as colunas, os tipos do Postgres e a chave, que a leitura da
  torre usa para devolver cada valor no tipo certo.
"""
import json
import re
import unicodedata

from ..dados import livros
from . import guardar
from . import tabelas as T

NOMES_LIVROS = {T.LIVRO_APP: "Zeladoria · estado do app", T.LIVRO_FRACTTAL: "Zeladoria · rondas do Fracttal",
                T.LIVRO_HISTORICO: "Zeladoria · históricos"}
# o histórico só cresce e é conferido antes da troca: vai primeiro, e se ele recusar, nada mais é gravado
ORDEM = (T.LIVRO_HISTORICO, T.LIVRO_FRACTTAL, T.LIVRO_APP)
# a versão é a da última gravação pelo Nexus (0 = só a cópia do Supabase): a torre e a cópia leem dela
CAB_ATUALIZACAO = ["aba", "coluna", "tipo_pg", "chave", "linhas_origem", "copiado_em", "exportado_em", "versao"]
VIEW_ULTIMAS = "rf_fracttal_ultimas"

_IDENTIFICADOR = re.compile(r"^[a-z0-9_:\-]+$")


class ExportacaoIncompleta(ValueError):
    """A exportação não traz todas as tabelas do Radar: nada é gravado."""


class CopiaRecusada(RuntimeError):
    """O Nexus já gravou mudanças da zeladoria no banco (a troca aconteceu): a cópia do Supabase passaria por cima delas."""


class TrocaInsegura(ValueError):
    """A troca de nome estragaria um dado (duas chaves de JSON viram a mesma): nada é gravado."""


class NomeEmClaro(TrocaInsegura):
    """Um nome do de-para sobrou num texto que vai em claro para o banco (leitura aberta): nada é gravado."""


# Onde o clone renomeou valores que estão nos dados (revisão final de 03/11/2026: trocar por pedaço em QUALQUER texto
# minúsculo estragaria id, código e chave de usina): as chaves e o JSON do config, a ação do log, e as colunas de
# origem, escopo e tipo de qualquer tabela.
RENOMEIA = {("config", "chave"), ("config", "valor"), ("log", "acao")}
RENOMEIA_COLUNAS = {"origem", "escopo", "tipo"}
# nome de lugar não conta como nome de gente ("Santa Maria" é usina e cidade)
LUGARES = {"usina", "usinas", "usina_chave", "ufv", "cliente", "cidade", "estado", "uf", "regiao", "cluster",
           "base_equipe", "equipe_cluster", "concessionaria", "fabricante_modulos"}


def _renomeia(aba: str, coluna: str) -> bool:
    return (aba, coluna) in RENOMEIA or coluna in RENOMEIA_COLUNAS


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _vigiados(de_para: dict) -> list:
    """Os nomes que não podem ir em claro: a lista `_nomes` do de-para ou, sem ela, as chaves que são só letras."""
    nomes = (de_para or {}).get("_nomes") or [k for k in (de_para or {}) if re.fullmatch(r"[a-z]+", k)]
    return [re.compile(r"(?<![a-z0-9])" + re.escape(_sem_acento(n)) + r"(?![a-z0-9])") for n in nomes if n]


def _conferir_claro(aba: str, colunas: list, linhas: list, vigiados: list) -> None:
    from .tabelas import coluna_cifrada
    for c, tipo in colunas:
        if c in LUGARES or coluna_cifrada(aba, c, tipo):
            continue
        for linha in linhas:
            v = linha.get(c)
            if v is None or isinstance(v, (bool, int, float)):
                continue
            texto = _sem_acento(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
            if any(p.search(texto) for p in vigiados):
                raise NomeEmClaro(f"{aba}.{c}: sobrou um nome do de-para num texto que vai em claro; acrescente a troca "
                                  "ao de-para ou revise a coluna antes de copiar")


def _trocas(de_para: dict) -> list:
    """As entradas do de-para que valem para dado (minúsculas, com cara de identificador), da mais longa para a mais
    curta: `planilha_<nome>` antes de `<nome>`."""
    pares = [(k, v) for k, v in (de_para or {}).items() if not k.startswith("_") and re.fullmatch(r"[a-z0-9_]+", k)]
    return sorted(pares, key=lambda kv: len(kv[0]), reverse=True)


def renomear(valor, trocas: list):
    """(valor renomeado, quantos textos mudaram). Entra no JSON guardado como texto e nas chaves e valores de dict."""
    if isinstance(valor, dict):
        out, n = {}, 0
        for k, v in valor.items():
            k2, nk = renomear(k, trocas)
            v2, nv = renomear(v, trocas)
            if k2 in out or (nk and k2 in valor):
                raise TrocaInsegura(f"a troca de nome faria duas chaves de JSON virarem {k2!r}")
            out[k2] = v2
            n += nk + nv
        return out, n
    if isinstance(valor, list):
        pares = [renomear(v, trocas) for v in valor]
        return [p[0] for p in pares], sum(p[1] for p in pares)
    if not isinstance(valor, str):
        return valor, 0
    s = valor.strip()
    if s[:1] in ("{", "["):
        try:
            dentro = json.loads(s)
        except ValueError:
            return valor, 0
        novo, n = renomear(dentro, trocas)
        return (json.dumps(novo, ensure_ascii=False, separators=(",", ":")), n) if n else (valor, 0)
    if not _IDENTIFICADOR.match(valor):
        return valor, 0
    novo = valor
    for velho, troca in trocas:
        novo = novo.replace(velho, troca)
    return novo, int(novo != valor)


def sql_exportacao(de_para: dict) -> str:
    """A consulta que se cola no SQL Editor do Supabase para exportar o Radar (03/11/2026): um SELECT só, que devolve uma
    linha com o JSON que `copiar` lê. As seis tabelas da equipe levam o primeiro nome do supervisor; ele sai do de-para
    (a entrada que vira "equipe"), que fica fora do repositório. Por isso a consulta é montada aqui, e não guardada."""
    nome = next((k for k, v in (de_para or {}).items()
                 if v == "equipe" and not k.startswith("_") and re.fullmatch(r"[a-z]+", k)), None)
    if not nome:
        raise ValueError("o de-para não diz o nome da equipe primarizada (a entrada que vira \"equipe\")")
    tabelas = [a.replace("_equipe", f"_{nome}") for a in T.TABELAS if a != "fracttal_ultimas"]
    pares = ",\n".join(f"    '{t}', (select coalesce(json_agg(x), '[]'::json) from radar_fornecedores.{t} x)"
                        for t in tabelas)
    return f"""-- Exportação do Radar para a cópia do Nexus. SÓ LEITURA: um SELECT, nada muda no banco do Radar.
-- Sai uma linha com um JSON: os dados de cada tabela, os tipos das colunas e as chaves primárias.
select json_build_object(
  'gerado_em', now(),
  'tipos', (select json_object_agg(table_name, cols) from (
      select table_name, json_agg(json_build_array(column_name, data_type) order by ordinal_position) as cols
        from information_schema.columns
       where table_schema = 'radar_fornecedores' or (table_schema = 'public' and table_name = 'rf_fracttal_ultimas')
       group by table_name) z),
  'chaves', (select json_object_agg(c.relname, (select string_agg(a.attname, ',' order by a.attnum)
               from pg_index i join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
              where i.indrelid = c.oid and i.indisprimary))
               from pg_class c join pg_namespace n on n.oid = c.relnamespace
              where n.nspname = 'radar_fornecedores' and c.relkind = 'r'),
  'ultimas', (select coalesce(json_agg(x), '[]'::json) from public.rf_fracttal_ultimas x),
  'tabelas', json_build_object(
{pares}
  )
) as exportacao;"""


def _maior_celula(abas: dict) -> int:
    return max((len(str(v)) for cab, linhas in abas.values() for l in linhas for v in l if v is not None), default=0)


def montar(exp: dict, *, de_para: dict, cofre, agora) -> tuple:
    """({livro: {aba: (cab, linhas)}}, relatório sem a gravação). Nada vai à rede."""
    # o mapa vem do ESQUEMA inteiro (os tipos), não só do que a consulta exportou: a tabela nova aparece nos tipos
    nomes = sorted((set(exp.get("tipos") or {}) | set(exp.get("tabelas") or {})) - {VIEW_ULTIMAS})
    mapa = T.mapa_de_tabelas(nomes)
    sem_dado = [n for n in nomes if n not in (exp.get("tabelas") or {})]
    if sem_dado:
        raise ExportacaoIncompleta(f"a exportação não traz os dados de: {', '.join(sem_dado)}")
    esperadas = {a for a in T.TABELAS if a != "fracttal_ultimas"}
    faltam = sorted(esperadas - set(mapa.values()))
    if faltam:
        raise ExportacaoIncompleta(f"a exportação não traz {len(faltam)} tabela(s) do Radar: {', '.join(faltam)}")
    trocas = _trocas(de_para)
    vigiados = _vigiados(de_para)
    fontes = [(mapa[n], exp["tipos"].get(n) or [], exp["chaves"].get(n), exp["tabelas"][n]) for n in nomes]
    tipos_view = exp["tipos"].get(VIEW_ULTIMAS) or []
    chave_view = "usina_chave" if any(c == "usina_chave" for c, _t in tipos_view) else (tipos_view[0][0] if tipos_view else "")
    fontes.append(("fracttal_ultimas", tipos_view, chave_view, exp.get("ultimas") or []))
    livros_prontos = {l: {} for l in ORDEM}
    atualizacao = {l: [] for l in ORDEM}
    rel = {"abas": {}, "trocas": 0, "exportado_em": exp.get("gerado_em")}
    copiado_em = agora.isoformat(timespec="seconds")
    for aba, cols, chave, linhas in fontes:
        colunas = [(c, t) for c, t in cols]
        if not colunas:
            raise ExportacaoIncompleta(f"a exportação não traz as colunas de {aba}")
        chave = (chave or colunas[0][0]).split(",")[0]
        renomeadas = []
        for linha in linhas:
            nova = {}
            for c, v in linha.items():
                if _renomeia(aba, c):
                    v, n = renomear(v, trocas)
                    rel["trocas"] += n
                nova[c] = v
            renomeadas.append(nova)
        _conferir_claro(aba, colunas, renomeadas, vigiados)
        livro = T.TABELAS[aba]
        livros_prontos[livro][aba] = guardar.para_aba(aba, colunas, renomeadas, cofre, chave)
        atualizacao[livro] += [[aba, c, t, chave, len(linhas), copiado_em, exp.get("gerado_em"), 0] for c, t in colunas]
        rel["abas"][aba] = {"origem": len(linhas), "nexus": None}
    for livro in ORDEM:
        livros_prontos[livro]["atualizacao"] = (list(CAB_ATUALIZACAO), atualizacao[livro])
    rel["maior_celula"] = max(_maior_celula(l) for l in livros_prontos.values())
    return livros_prontos, rel


def _versao_no_banco(base: str, sessao) -> int:
    v = 0
    for livro in ORDEM:
        ids = livros.abas(base, sessao, livro)
        if "atualizacao" in ids:
            v = max([v] + [int(float(l.get("versao") or 0)) for l in livros._linhas(base, sessao, ids["atualizacao"])])
    return v


def copiar(exp: dict, *, de_para: dict, cofre, base: str, token: str, sessao, gravar: bool, agora,
           forcar: bool = False) -> dict:
    """Monta os três livros e, com `gravar`, grava e confere cada um. Sem `gravar`, é o ensaio: nada sai da máquina.
    Depois que o Nexus gravou alguma mudança (versão > 0), a cópia recusa (`CopiaRecusada`), salvo `forcar`."""
    prontos, rel = montar(exp, de_para=de_para, cofre=cofre, agora=agora)
    rel["gravou"] = False
    if not gravar:
        return rel
    if not forcar and _versao_no_banco(base, sessao) > 0:
        raise CopiaRecusada("o Nexus já gravou mudanças da zeladoria no banco: a cópia do Supabase passaria por cima "
                            "delas (use --forcar só se tiver certeza)")
    for livro in ORDEM:
        conferido = livros.publicar(livro, NOMES_LIVROS[livro], prontos[livro], base=base, token=token, sessao=sessao)
        for aba, n in conferido.items():
            if aba in rel["abas"]:
                rel["abas"][aba]["nexus"] = n
    rel["gravou"] = True
    return rel
