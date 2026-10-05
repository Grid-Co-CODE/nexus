"""Ler e gravar livros (workbooks) na API do banco (db_performace), com a conferência DEPOIS de gravar.

Regra da casa ("conferir antes e depois de gravar"): a gravação troca o livro inteiro (`sync-xlsx?replace=true`) e, em
seguida, cada aba é relida e a contagem de linhas tem de bater com a enviada; diferença vira erro, nunca silêncio. A API
não apaga livro: nome de livro novo é para sempre (escolha com cuidado, e registre no `catalogo.py`).
"""
from ..cadastro.banco import MIME_XLSX, xlsx_bytes


class GravacaoErro(RuntimeError):
    pass


def abas(base: str, sessao, livro: str) -> dict:
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    return {x["sheet_name"]: x["id"] for x in r.json() if x.get("workbook_key") == livro}


def _linhas(base, sessao, sid) -> list[dict]:
    out, offset = [], 0
    while True:
        r = sessao.get(f"{base}/api/sheets/{sid}/rows", params={"limit": 1000, "offset": offset}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        out += [dict(zip(x.get("headers") or [], x.get("values") or [])) for x in rows]
        if len(rows) < 1000:
            return out
        offset += 1000


def ler(base: str, sessao, livro: str, aba: str | None = None) -> list[dict]:
    """As linhas de uma aba (a 1ª, sem `aba`). Livro ou aba que não existe = vazio."""
    a = abas(base, sessao, livro)
    if not a:
        return []
    sid = a.get(aba) if aba else next(iter(a.values()))
    return _linhas(base, sessao, sid) if sid else []


def atualizado_em(base: str, sessao, livro: str) -> str | None:
    """Quando o livro foi gravado pela última vez (o que a API diz)."""
    r = sessao.get(f"{base}/api/workbooks", timeout=60)
    r.raise_for_status()
    for w in r.json():
        if w.get("key") == livro:
            return w.get("updated_at") or w.get("atualizado_em")
    return None


def publicar(livro: str, nome: str, tabelas: dict, *, base: str, token: str, sessao) -> dict:
    """Grava o livro inteiro e confere aba a aba. {aba: linhas}. Erro de gravação ou contagem diferente sobe."""
    h = {"Authorization": f"Bearer {token}"}
    r = sessao.get(f"{base}/api/workbooks", headers=h, timeout=60)
    r.raise_for_status()
    if livro not in {w.get("key") for w in r.json()}:
        sessao.post(f"{base}/api/workbooks", headers=h, json={"key": livro, "display_name": nome},
                    timeout=60).raise_for_status()
    r = sessao.post(f"{base}/api/workbooks/{livro}/sync-xlsx", headers=h, params={"replace": "true"},
                    files={"file": (f"{livro}.xlsx", xlsx_bytes(tabelas), MIME_XLSX)}, timeout=300)
    r.raise_for_status()
    gravado = abas(base, sessao, livro)
    conferido = {}
    for aba, (_cab, linhas) in tabelas.items():
        n = len(_linhas(base, sessao, gravado[aba])) if aba in gravado else 0
        if n != len(linhas):
            raise GravacaoErro(f"{livro}.{aba}: enviei {len(linhas)} linhas e o banco tem {n}")
        conferido[aba] = n
    return conferido
