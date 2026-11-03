"""A linha de uma tabela do Radar vira linha de aba do livro do Nexus, e volta igual.

Quatro cuidados, cada um com o caso que o pede:
- **O tipo.** O livro é xlsx, e a API pode devolver tudo como texto (`tests/pg_falso.py`, `como_texto=True`). A volta
  converte pelo tipo do Postgres que a cópia anotou na aba `atualizacao`: jsonb volta dict, boolean volta bool. Data e
  hora voltam como texto ISO, como o Supabase entregava ao app. Coluna json, jsonb ou lista vai SEMPRE como JSON: o
  jsonb que guarda só um texto ("ROÇAGEM") ou um número escrito como texto ("123") volta igual. O JSON estragado
  volta como veio e vai para o log, sem derrubar a leitura (revisão final de 03/11/2026).
- **A cifra.** Vai cifrado o que `tabelas.coluna_cifrada` diz (por padrão, todo texto; regra 8 de
  `nexus/dados/CLAUDE.md`), preso à linha e à coluna pelo contexto `zeladoria/<aba>/<chave>/<coluna>`. A cifra copiada
  para outra linha não abre.
  - Quando a própria chave da linha é dado pessoal (o apelido do fornecedor MEI), ela é cifrada com o contexto
    `zeladoria/<aba>/-/<coluna>`, e as outras colunas se prendem ao valor dela em claro.
  - O id lido como 5, "5", 5.0 ou "5.0" é o mesmo.
  - O que não abre (chave trocada, linha mexida) vira NAO_ABRE só em coluna de texto. Nas outras vira None, porque
    "(não abre)" é verdadeiro no JavaScript e mandaria o colaborador para a Lixeira. O log diz a aba e a coluna, nunca
    o valor.
- **O tamanho.** A célula do xlsx guarda no máximo 32.767 caracteres, e o `config` do Radar guarda tabelas inteiras em
  JSON. O valor maior que PARTE vai partido em colunas `<coluna>__p2`, `__p3`... O número de linhas nunca muda, e a
  conferência de contagem do `livros.publicar` continua valendo.
- **O vazio.** O texto vazio volta como None: o `xlsx_bytes` grava "" como célula vazia, porque o sync da API recusa
  texto vazio.
"""
import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal

from ..cadastro.cifra import CifraErro, Cofre
from .tabelas import coluna_cifrada

log = logging.getLogger(__name__)

PARTE = 32000
NAO_ABRE = "(não abre)"

_INTEIROS = {"integer", "bigint", "smallint"}
_DECIMAIS = {"numeric", "real", "double precision"}
_INTEIRO_COM_ZEROS = re.compile(r"^-?\d+\.0+$")


def _eh_json(tipo: str) -> bool:
    t = (tipo or "").lower()
    return t in ("json", "jsonb") or t.startswith("array") or t.endswith("[]")


def _eh_texto(tipo: str) -> bool:
    t = (tipo or "text").lower()
    return t in ("text", "character varying", "character", "varchar", "char", "citext", "name")


def _chave_txt(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = "" if v is None else str(v)
    return s.split(".")[0] if _INTEIRO_COM_ZEROS.match(s) else s


def _contexto(aba: str, chave_valor, coluna: str) -> str:
    return f"zeladoria/{aba}/{_chave_txt(chave_valor)}/{coluna}"


def _serializar(v, tipo: str):
    if v is None:
        return None
    if _eh_json(tipo):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (dict, list, tuple)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    return str(v)


def _partes(v) -> list:
    if not isinstance(v, str) or len(v) <= PARTE:
        return [v]
    return [v[i:i + PARTE] for i in range(0, len(v), PARTE)]


def para_aba(aba: str, colunas: list, linhas: list, cofre: Cofre, chave: str) -> tuple:
    """(cabeçalho, linhas) no formato do `livros.publicar`. `colunas` = [(nome, tipo do Postgres)], na ordem da tabela."""
    tipos = dict(colunas)
    nomes = [c for c, _t in colunas]
    chave_cifrada = coluna_cifrada(aba, chave, tipos.get(chave))
    prontas = []
    for linha in linhas:
        k = linha.get(chave)
        saida = {}
        for c in nomes:
            v = _serializar(linha.get(c), tipos[c])
            if v is not None and coluna_cifrada(aba, c, tipos[c]):
                texto = v if isinstance(v, str) else json.dumps(v)
                ctx = f"zeladoria/{aba}/-/{c}" if (c == chave and chave_cifrada) else _contexto(aba, k, c)
                v = cofre.cifrar(texto, ctx)
            saida[c] = _partes(v)
        prontas.append(saida)
    n_partes = {c: max([len(p[c]) for p in prontas] or [1]) for c in nomes}
    cab = nomes + [f"{c}__p{i}" for c in nomes for i in range(2, n_partes[c] + 1)]
    out = []
    for p in prontas:
        base = [p[c][0] for c in nomes]
        extra = [p[c][i - 1] if i <= len(p[c]) else None for c in nomes for i in range(2, n_partes[c] + 1)]
        out.append(base + extra)
    return cab, out


def _converter(v, tipo: str, aba: str, coluna: str):
    if v is None or v == "":
        return None
    t = (tipo or "").lower()
    if t in _INTEIROS:
        return v if isinstance(v, int) else int(Decimal(str(v)))
    if t in _DECIMAIS:
        return float(v)
    if t == "boolean":
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("true", "1", "t", "sim", "verdadeiro")
    if _eh_json(t):
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except ValueError:
            log.warning("zeladoria: %s.%s não é JSON válido; volta como texto", aba, coluna)
            return v
    return _chave_txt(v)


def _juntar(linha: dict, c: str):
    v = linha.get(c)
    i = 2
    while f"{c}__p{i}" in linha:
        parte = linha.get(f"{c}__p{i}")
        if parte not in (None, ""):
            v = ("" if v is None else str(v)) + str(parte)
        i += 1
    return v


def de_aba(aba: str, tipos: dict, linhas: list, cofre: Cofre, chave: str) -> list:
    """As linhas como o app do Radar as recebia do Supabase. `linhas` = o que o `livros.ler` devolve (dict por linha)."""
    chave_cifrada = coluna_cifrada(aba, chave, tipos.get(chave))
    out = []
    for linha in linhas:
        k = _juntar(linha, chave)
        if chave_cifrada and Cofre.eh_cifrado(k):
            try:
                k = cofre.decifrar(k, f"zeladoria/{aba}/-/{chave}")
            except CifraErro:
                k = None
        nova = {}
        for c, tipo in tipos.items():
            v = k if c == chave and chave_cifrada else _juntar(linha, c)
            if v not in (None, "") and coluna_cifrada(aba, c, tipo) and Cofre.eh_cifrado(v):
                try:
                    v = cofre.decifrar(v, _contexto(aba, k, c))
                except CifraErro:
                    log.warning("zeladoria: a cifra de %s.%s não abre", aba, c)
                    nova[c] = NAO_ABRE if _eh_texto(tipo) else None
                    continue
            if c == chave and chave_cifrada and k is None:
                log.warning("zeladoria: a cifra de %s.%s não abre", aba, c)
                nova[c] = NAO_ABRE if _eh_texto(tipo) else None
                continue
            nova[c] = _converter(v, tipo, aba, c)
        out.append(nova)
    return out
