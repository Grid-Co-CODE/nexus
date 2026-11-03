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

from ..dados import livros
from . import guardar
from . import tabelas as T

NOMES_LIVROS = {T.LIVRO_APP: "Zeladoria · estado do app", T.LIVRO_FRACTTAL: "Zeladoria · rondas do Fracttal",
                T.LIVRO_HISTORICO: "Zeladoria · históricos"}
# o histórico só cresce e é conferido antes da troca: vai primeiro, e se ele recusar, nada mais é gravado
ORDEM = (T.LIVRO_HISTORICO, T.LIVRO_FRACTTAL, T.LIVRO_APP)
CAB_ATUALIZACAO = ["aba", "coluna", "tipo_pg", "chave", "linhas_origem", "copiado_em", "exportado_em"]
VIEW_ULTIMAS = "rf_fracttal_ultimas"

_IDENTIFICADOR = re.compile(r"^[a-z0-9_:\-]+$")


class ExportacaoIncompleta(ValueError):
    """A exportação não traz todas as tabelas do Radar: nada é gravado."""


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
        return (json.dumps(novo, ensure_ascii=False), n) if n else (valor, 0)
    if not _IDENTIFICADOR.match(valor):
        return valor, 0
    novo = valor
    for velho, troca in trocas:
        novo = novo.replace(velho, troca)
    return novo, int(novo != valor)


def _maior_celula(abas: dict) -> int:
    return max((len(str(v)) for cab, linhas in abas.values() for l in linhas for v in l if v is not None), default=0)


def montar(exp: dict, *, de_para: dict, cofre, agora) -> tuple:
    """({livro: {aba: (cab, linhas)}}, relatório sem a gravação). Nada vai à rede."""
    nomes = list(exp.get("tabelas") or {})
    mapa = T.mapa_de_tabelas(nomes)
    esperadas = {a for a in T.TABELAS if a != "fracttal_ultimas"}
    faltam = sorted(esperadas - set(mapa.values()))
    if faltam:
        raise ExportacaoIncompleta(f"a exportação não traz {len(faltam)} tabela(s) do Radar: {', '.join(faltam)}")
    trocas = _trocas(de_para)
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
                nova[c], n = renomear(v, trocas)
                rel["trocas"] += n
            renomeadas.append(nova)
        livro = T.TABELAS[aba]
        livros_prontos[livro][aba] = guardar.para_aba(aba, colunas, renomeadas, cofre, chave)
        atualizacao[livro] += [[aba, c, t, chave, len(linhas), copiado_em, exp.get("gerado_em")] for c, t in colunas]
        rel["abas"][aba] = {"origem": len(linhas), "nexus": None}
    for livro in ORDEM:
        livros_prontos[livro]["atualizacao"] = (list(CAB_ATUALIZACAO), atualizacao[livro])
    rel["maior_celula"] = max(_maior_celula(l) for l in livros_prontos.values())
    return livros_prontos, rel


def copiar(exp: dict, *, de_para: dict, cofre, base: str, token: str, sessao, gravar: bool, agora) -> dict:
    """Monta os três livros e, com `gravar`, grava e confere cada um. Sem `gravar`, é o ensaio: nada sai da máquina."""
    prontos, rel = montar(exp, de_para=de_para, cofre=cofre, agora=agora)
    rel["gravou"] = False
    if not gravar:
        return rel
    for livro in ORDEM:
        conferido = livros.publicar(livro, NOMES_LIVROS[livro], prontos[livro], base=base, token=token, sessao=sessao)
        for aba, n in conferido.items():
            if aba in rel["abas"]:
                rel["abas"][aba]["nexus"] = n
    rel["gravou"] = True
    return rel
