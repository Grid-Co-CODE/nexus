"""Ler e gravar livros (workbooks) na API do banco (db_performace), com a conferência ANTES e DEPOIS de gravar.

Regra da casa ("conferir antes e depois de gravar"): a gravação troca o livro inteiro (`sync-xlsx?replace=true`) e, em
seguida, cada aba é relida e a contagem de linhas tem de bater com a enviada; diferença vira erro, nunca silêncio. A API
não apaga livro: nome de livro novo é para sempre (escolha com cuidado, e registre no `catalogo.py`).

O livro que só cresce (Levi, 18/10/2026: "Proteger os livros do Nexus de gravar sobre leitura vazia") é declarado no
catálogo (`Livro.so_cresce`: as abas que nunca encolhem). Antes de trocá-lo, a gravação confere a listagem do banco e
recusa (`GravacaoRecusada`, nada gravado): a listagem incompleta (o livro diz que tem N abas e ela traz menos: quem
releu recebeu vazio e a troca apagaria o histórico), a aba que sumiria (o banco a tem e a gravação a deixa de fora) e a
aba que encolheria (menos linhas que o banco tem agora). Medido no banco real em 18/10/2026: o `row_count` da listagem é
o número de linhas que a leitura devolve, e o `sheet_count` do livro diz quantas abas ele tem. O livro da carga de hora
em hora não é desses: ele encolhe de propósito, pela janela de cada fonte.
"""
from ..cadastro.banco import MIME_XLSX, xlsx_bytes


class GravacaoErro(RuntimeError):
    pass


class GravacaoRecusada(GravacaoErro):
    """Nada foi gravado: o livro que só cresce ficaria menor do que está no banco, ou a listagem veio incompleta."""


def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _so_cresce(livro: str) -> tuple:
    """As abas que nunca encolhem, pelo catálogo (vazio = livro sem trava)."""
    l = _do_catalogo(livro)
    return tuple(l.so_cresce) if l else ()


def _do_catalogo(livro: str):
    from . import catalogo        # aqui dentro: o catálogo importa os fatos, e eles importam este módulo
    return catalogo.LIVRO_POR_NOME.get(livro)


def _conferir_antes(livro: str, w: dict, tabelas: dict, base: str, sessao, so: tuple) -> None:
    """A trava do livro que só cresce, antes da troca (ver o docstring do módulo). A aba que sumiria só conta se o
    catálogo a declara: a desconhecida não é dado do livro (a antiga `decisoes` das decisões de PT, que um Nexus velho
    gravava e não vale mais, sai na troca como sempre saiu; o radar da Governança mostra a aba que ninguém declarou)."""
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    listadas = {x["sheet_name"]: x for x in r.json() if x.get("workbook_key") == livro}
    n = _int(w.get("sheet_count"))
    if n and len(listadas) < n:
        raise GravacaoRecusada(f"{livro}: o banco diz que o livro tem {n} abas e a listagem trouxe {len(listadas)}; "
                               "não gravo por cima de uma leitura incompleta (tente de novo em instantes)")
    l = _do_catalogo(livro)
    declaradas = set(l.abas) if l else set(so)
    faltam = sorted((set(listadas) & declaradas) - set(tabelas))
    if faltam:
        raise GravacaoRecusada(f"{livro}: gravar sem a aba {', '.join(faltam)} a apagaria")
    for aba in so:
        tem = _int((listadas.get(aba) or {}).get("row_count"))
        vai = len(tabelas[aba][1]) if aba in tabelas else None
        if tem is not None and vai is not None and vai < tem:
            raise GravacaoRecusada(f"{livro}.{aba}: o banco tem {tem} linhas e a gravação levaria {vai}; livro que só "
                                   "cresce não encolhe")


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
    """Grava o livro inteiro e confere aba a aba. {aba: linhas}. Erro de gravação ou contagem diferente sobe; o livro
    que só cresce é conferido antes (`GravacaoRecusada`, nada gravado)."""
    h = {"Authorization": f"Bearer {token}"}
    r = sessao.get(f"{base}/api/workbooks", headers=h, timeout=60)
    r.raise_for_status()
    w = next((x for x in r.json() if x.get("key") == livro), None)
    so = _so_cresce(livro)
    if w is None:
        sessao.post(f"{base}/api/workbooks", headers=h, json={"key": livro, "display_name": nome},
                    timeout=60).raise_for_status()
    elif so:
        _conferir_antes(livro, w, tabelas, base, sessao, so)
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
