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
A trava não fica cega quando a listagem de livros falha (revisão final, 18/10/2026): o livro que só cresce e não veio no
/api/workbooks, mas tem abas listadas, é recusado (antes ele era "criado" e trocado sem conferência); e, sem o
`sheet_count` e sem nenhuma aba listada, também (só o 0 dito pelo banco, o livro criado e nunca gravado, segue).
"""
from ..cadastro.banco import MIME_XLSX, xlsx_bytes


class GravacaoErro(RuntimeError):
    pass


class GravacaoRecusada(GravacaoErro):
    """Nada foi gravado: o livro que só cresce ficaria menor do que está no banco, ou a listagem veio incompleta."""


class LeituraIncompleta(RuntimeError):
    """A listagem do banco não trouxe o que o livro tem: é "não li", nunca "livro vazio" (`abas_conferidas`)."""


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
    l = catalogo.LIVRO_POR_NOME.get(livro)
    if l is None:
        # o livro de uma família (um por mês: nexus_almoxarifado_saldo_2026_10) tem a trava do molde no catálogo
        # (25/10/2026: sem isto, a foto do saldo do mês, que só cresce, ficava sem trava)
        molde = next((m for p, m in catalogo.FAMILIAS.items() if p.match(livro)), None)
        l = catalogo.LIVRO_POR_NOME.get(molde) if molde else None
    return l


def _conferir_antes(livro: str, w: dict, tabelas: dict, base: str, sessao, so: tuple) -> None:
    """A trava do livro que só cresce, antes da troca (ver o docstring do módulo). A aba que sumiria só conta se o
    catálogo a declara: a desconhecida não é dado do livro (a antiga `decisoes` das decisões de PT, que um Nexus velho
    gravava e não vale mais, sai na troca como sempre saiu; o radar da Governança mostra a aba que ninguém declarou)."""
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    listadas = {x["sheet_name"]: x for x in r.json() if x.get("workbook_key") == livro}
    n = _int(w.get("sheet_count"))
    if not listadas and n is None:
        raise GravacaoRecusada(f"{livro}: o banco não disse quantas abas o livro tem e a listagem não trouxe nenhuma; "
                               "não gravo por cima (tente de novo em instantes)")
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


def _conferir_livro_novo(livro: str, base: str, sessao) -> None:
    """O livro que só cresce e não veio na listagem de livros: se a de abas traz abas dele, ele existe e a listagem de
    livros falhou; criar e trocar apagaria o histórico."""
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    n = sum(1 for x in r.json() if x.get("workbook_key") == livro)
    if n:
        raise GravacaoRecusada(f"{livro}: a listagem de livros não trouxe o livro, mas a de abas traz {n}; não gravo por "
                               "cima (tente de novo em instantes)")


def abas(base: str, sessao, livro: str) -> dict:
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    return {x["sheet_name"]: x["id"] for x in r.json() if x.get("workbook_key") == livro}


def _conferir(livro: str, w: dict | None, a: dict, declaradas) -> None:
    """A conferência da listagem de um livro que se lê para gravar por cima (o `w` do /api/workbooks, as abas `a` do
    /api/sheets): sobe `LeituraIncompleta` quando o livro existe e a listagem traz menos abas que o `sheet_count` dele, ou não
    traz uma aba `declarada`. O livro que não existe passa (é vazio), e o criado e nunca gravado (`sheet_count` 0) também."""
    if w is None:
        return
    n = _int(w.get("sheet_count"))
    if n == 0 and not a:
        return
    if n is not None and len(a) < n:
        raise LeituraIncompleta(f"{livro}: o banco diz que o livro tem {n} abas e a listagem trouxe {len(a)}")
    faltam = [x for x in declaradas if x not in a]
    if faltam:
        raise LeituraIncompleta(f"{livro}: a listagem não trouxe a aba {', '.join(faltam)} do livro que existe")


def abas_conferidas(base: str, sessao, livro: str, declaradas) -> dict:
    """{aba: id} do livro, conferido com o /api/workbooks, para quem lê e grava por cima (achado 6 da revisão de
    05/11/2026): o `abas` sozinho devolvia {} quando a listagem omitia o livro por um instante, quem lia via "livro
    vazio" e a gravação seguinte trocaria o livro só com a linha nova. A conferência é a `_conferir`."""
    r = sessao.get(f"{base}/api/workbooks", timeout=60)
    r.raise_for_status()
    w = next((x for x in r.json() if x.get("key") == livro), None)
    a = abas(base, sessao, livro)
    _conferir(livro, w, a, declaradas)
    return a


def ler_conferido(base: str, sessao, livro: str, declaradas) -> dict:
    """{aba: [linhas]} das `declaradas`, para quem lê e grava por cima, com UMA listagem de abas (12/11/2026, a revisão das
    Usinas e almoxarifados, M5: cada livro do Nexus repetia esta leitura, e chamava o /api/sheets duas vezes): a conferência
    da listagem (`_conferir`) e a de cada aba, que não pode voltar com menos linhas do que o `row_count` dela diz (a página
    curta: sem isto, a gravação seguinte apagaria as linhas que não vieram). A aba que não existe é vazia."""
    r = sessao.get(f"{base}/api/workbooks", timeout=60)
    r.raise_for_status()
    w = next((x for x in r.json() if x.get("key") == livro), None)
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    listadas = {x["sheet_name"]: x for x in r.json() if x.get("workbook_key") == livro}
    _conferir(livro, w, {n: x["id"] for n, x in listadas.items()}, declaradas)
    out = {}
    for aba in declaradas:
        meta = listadas.get(aba)
        if meta is None:
            out[aba] = []
            continue
        lidas = list(_linhas(base, sessao, meta["id"]))
        n = _int(meta.get("row_count"))
        if n is not None and len(lidas) < n:
            raise LeituraIncompleta(f"{livro}.{aba}: li {len(lidas)} linhas e o banco diz {n}")
        out[aba] = lidas
    return out

PAGINA = 1000


def pagina(base, sessao, sid, offset: int) -> list[dict]:
    """Uma página (até PAGINA linhas) de uma aba, a partir de `offset`, na ordem do banco. A que vem com menos de PAGINA
    linhas é a última."""
    r = sessao.get(f"{base}/api/sheets/{sid}/rows", params={"limit": PAGINA, "offset": offset}, timeout=60)
    r.raise_for_status()
    rows = r.json()
    rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
    return [dict(zip(x.get("headers") or [], x.get("values") or [])) for x in rows]


def _linhas(base, sessao, sid) -> list[dict]:
    out, offset = [], 0
    while True:
        rows = pagina(base, sessao, sid, offset)
        out += rows
        if len(rows) < PAGINA:
            return out
        offset += PAGINA


# público para quem já tem o id da aba (a ligação do cadastro, `cadastro/ligacao_campo.py`, 08/11/2026)
linhas_da_aba = _linhas


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


def existe(livro: str, *, base: str, token: str, sessao) -> bool:
    """O livro está na listagem do banco (/api/workbooks, a mesma que o `publicar` consulta para criá-lo)."""
    r = sessao.get(f"{base}/api/workbooks", headers={"Authorization": f"Bearer {token}"}, timeout=60)
    r.raise_for_status()
    return any(w.get("key") == livro for w in r.json())


def publicar(livro: str, nome: str, tabelas: dict, *, base: str, token: str, sessao) -> dict:
    """Grava o livro inteiro e confere aba a aba. {aba: linhas}. Erro de gravação ou contagem diferente sobe; o livro
    que só cresce é conferido antes (`GravacaoRecusada`, nada gravado)."""
    h = {"Authorization": f"Bearer {token}"}
    r = sessao.get(f"{base}/api/workbooks", headers=h, timeout=60)
    r.raise_for_status()
    w = next((x for x in r.json() if x.get("key") == livro), None)
    so = _so_cresce(livro)
    if w is None:
        if so:
            _conferir_livro_novo(livro, base, sessao)
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
