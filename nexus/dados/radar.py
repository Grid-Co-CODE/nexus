"""O radar do banco: toda tabela do banco tem dono no catálogo, e a tabela nova aparece sozinha.

Levi, 09/10/2026, depois do organograma: "verifique se aparece a cada tabela nova que aparece!". O organograma só
mostrava o que alguém tinha escrito no catálogo: um livro novo que a plataforma, o App ou um coletor criassem no banco
ficava invisível na Governança. O radar compara a listagem do banco (`/api/sheets`, a mesma que a prévia usa) com o
catálogo e põe cada aba numa caixa:

  fato       fonte ou destino de um fato (FATOS: `fontes`/`livro` e `conformado_em`) ou aba de livro do Nexus (LIVROS)
  usina      aba de usina dos livros "1 aba por usina" (BD_Thopen, BD_Performance): visível e não declarada como outra
             coisa
  conhecida  declarada em `catalogo.CONHECIDAS`, com o papel (dimensão, controle, apoio, candidata a fato...) e o porquê
  nova       nenhuma das anteriores: aparece na Governança, com a contagem no alto do organograma

A aba nova num livro conhecido também é nova (a declaração é aba por aba). A aba de livro do Nexus fora do LIVROS é
nova: é a regra 10 (registrar antes de criar) furada, e o radar mostra. Caso que provou (09/10): a aba `qualidade` do
`nexus_rondas_checklist` estava no banco desde a carga única de 06/10 e o LIVROS não a citava.

Limite conhecido: no BD_Thopen e no BD_Performance, aba nova e visível conta como aba de usina (saber se é de geração
pede o cabeçalho, uma leitura por aba). Se não for de geração, a prévia recusa as linhas; declare-a em CONHECIDAS.
"""
from . import catalogo, previa

CAIXAS = ("fato", "usina", "conhecida", "nova")


def classificar(abas: dict) -> dict:
    """{caixa: [tabela]} das abas da listagem do banco ({(livro, aba): meta}). Cada tabela: livro, aba, linhas,
    colunas, oculta (e papel e motivo, na conhecida). Na ordem da listagem do banco."""
    pares, por_usina = previa.cobertas()
    out = {c: [] for c in CAIXAS}
    for (livro, aba), meta in sorted(abas.items(), key=lambda kv: kv[1].get("id") or 0):
        t = {"livro": livro, "aba": aba, "linhas": meta.get("row_count"), "colunas": meta.get("column_count"),
             "oculta": (meta.get("visibility") or "visible") != "visible"}
        c = catalogo.conhecida(livro, aba)
        if (livro, aba) in pares:
            out["fato"].append(t)
        elif c is not None:
            out["conhecida"].append(dict(t, papel=c.papel, motivo=c.motivo))
        elif livro in por_usina and not t["oculta"]:
            out["usina"].append(t)
        else:
            out["nova"].append(t)
    return out


def resumo(abas: dict) -> dict:
    """O que a tela mostra: as contas de cada caixa, as novas, e as conhecidas por papel e por declaração (o porquê uma
    vez, com as abas dela que estão no banco). As de teste e as aposentadas só entram na conta (Levi, 09/10: "Não mostre
    aposentado")."""
    c = classificar(abas)
    grupos = {}
    for d in catalogo.CONHECIDAS:
        if d.papel in ("teste", "aposentada"):
            continue
        presentes = [a for a in d.abas if (d.livro, a) in abas]
        if presentes:
            grupos.setdefault(d.papel, []).append({"livro": d.livro, "abas": presentes, "motivo": d.motivo})
    ordem = list(catalogo.PAPEIS_CONHECIDA)
    return {"total": len(abas), "n": {k: len(v) for k, v in c.items()}, "novas": c["nova"],
            "conhecidas": [(catalogo.PAPEIS_CONHECIDA[p], grupos[p]) for p in ordem if p in grupos],
            "so_na_conta": sum(1 for t in c["conhecida"] if t["papel"] in ("teste", "aposentada"))}
