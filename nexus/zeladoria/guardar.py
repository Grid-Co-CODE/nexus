"""A linha de uma tabela do Radar vira linha de aba do livro do Nexus, e volta igual.

Três cuidados, cada um com o caso que o pede:
- O tipo: o livro é xlsx e a API pode devolver tudo como texto (`tests/pg_falso.py`, `como_texto=True`). Por isso a
  volta converte pelo tipo do Postgres que a cópia anotou na aba `atualizacao` (jsonb volta dict, boolean volta bool).
  Data e hora voltam como texto ISO, como o Supabase entregava ao app.
- A cifra: o dado pessoal, o texto livre e o nome do fornecedor vão cifrados (`tabelas.coluna_cifrada`, regra 8 de
  `nexus/dados/CLAUDE.md`), presos à linha e à coluna pelo contexto `zeladoria/<aba>/<chave>/<coluna>`. A cifra copiada
  para outra linha não abre. A que não abre (chave trocada, linha mexida) volta como NAO_ABRE: a tela continua de pé e
  o log diz a aba e a coluna, nunca o valor.
- O tamanho: a célula do xlsx guarda no máximo 32.767 caracteres, e o `config` do Radar guarda tabelas inteiras em JSON.
  O valor maior que PARTE vai partido em colunas `<coluna>__p2`, `__p3`...; o número de linhas nunca muda, e a conferência
  de contagem do `livros.publicar` continua valendo.

O texto vazio volta como None: o `xlsx_bytes` grava "" como célula vazia, porque o sync da API recusa texto vazio.
"""
import json
import logging
from datetime import date, datetime
from decimal import Decimal

from ..cadastro.cifra import CifraErro, Cofre
from .tabelas import coluna_cifrada

log = logging.getLogger(__name__)

PARTE = 32000
NAO_ABRE = "(não abre)"

_INTEIROS = {"integer", "bigint", "smallint"}
_DECIMAIS = {"numeric", "real", "double precision"}
_JSON = {"json", "jsonb"}


def _chave_txt(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return "" if v is None else str(v)


def _contexto(aba: str, chave_valor, coluna: str) -> str:
    return f"zeladoria/{aba}/{_chave_txt(chave_valor)}/{coluna}"


def _serializar(v):
    if v is None or isinstance(v, (bool, int, float, str)):
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
    nomes = [c for c, _t in colunas]
    prontas = []
    for linha in linhas:
        k = linha.get(chave)
        saida = {}
        for c in nomes:
            v = _serializar(linha.get(c))
            if v is not None and coluna_cifrada(aba, c):
                v = cofre.cifrar(v if isinstance(v, str) else json.dumps(v), _contexto(aba, k, c))
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


def _converter(v, tipo: str):
    if v is None or v == "":
        return None
    t = (tipo or "").lower()
    if t in _INTEIROS:
        return int(float(v))
    if t in _DECIMAIS:
        return float(v)
    if t == "boolean":
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("true", "1", "t", "sim", "verdadeiro")
    if t in _JSON or t.startswith("array") or t.endswith("[]"):
        return json.loads(v) if isinstance(v, str) else v
    return _chave_txt(v)


def de_aba(aba: str, tipos: dict, linhas: list, cofre: Cofre, chave: str) -> list:
    """As linhas como o app do Radar as recebia do Supabase. `linhas` = o que o `livros.ler` devolve (dict por linha)."""
    out = []
    for linha in linhas:
        k = linha.get(chave)
        nova = {}
        for c, tipo in tipos.items():
            v = linha.get(c)
            i = 2
            while f"{c}__p{i}" in linha:
                parte = linha.get(f"{c}__p{i}")
                if parte not in (None, ""):
                    v = ("" if v is None else str(v)) + str(parte)
                i += 1
            if v not in (None, "") and coluna_cifrada(aba, c) and Cofre.eh_cifrado(v):
                try:
                    v = cofre.decifrar(v, _contexto(aba, k, c))
                except CifraErro:
                    log.warning("zeladoria: a cifra de %s.%s (linha %s) não abre", aba, c, _chave_txt(k))
                    nova[c] = NAO_ABRE
                    continue
            nova[c] = _converter(v, tipo)
        out.append(nova)
    return out
