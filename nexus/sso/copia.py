"""A cópia do SSO do Supabase para o banco do Nexus (12/11/2026), sob comando: `ferramentas/copiar_sso.py`.

A exportação saiu do SQL Editor do painel do Supabase em partes (o APR, o EPI com a vistoria, e o resto com os tipos,
as chaves e o inventário dos arquivos), porque o editor e o Chrome não aguentam uma célula só com tudo. Cada parte é um
JSON `{"parte", "gerado_em", "tabelas": {"esquema.tabela": [linhas]}}`; a do resto traz também `tipos`, `chaves` e
`arquivos`. A cópia junta as partes, confere que nenhuma tabela faltou, cifra pela regra de `tabelas.py` (o mesmo molde
da Zeladoria, `nexus/zeladoria/guardar.py`, com o contexto `sso/<aba>/<chave>/<coluna>`) e grava um livro por módulo,
cada um com a aba `atualizacao` (o tipo de cada coluna, a chave, quantas linhas vieram e a versão). O `livros.publicar`
confere a contagem de cada aba no banco depois de gravar.
"""
from __future__ import annotations

from ..dados import livros
from ..zeladoria import guardar
from ..zeladoria.copia import CAB_ATUALIZACAO
from . import tabelas as T

PREFIXO = "sso"


class ExportacaoIncompleta(ValueError):
    """Faltou parte, tabela, tipo ou chave na exportação: nada é gravado."""


class CopiaRecusada(RuntimeError):
    """O Nexus já gravou mudanças do SSO: a cópia do Supabase passaria por cima delas."""


def juntar(partes: list[dict]) -> dict:
    """As partes da exportação num dicionário só: {"tabelas", "tipos", "chaves", "arquivos", "exportado_em"}."""
    exp = {"tabelas": {}, "tipos": {}, "chaves": {}, "arquivos": None, "exportado_em": None}
    for p in partes:
        exp["tabelas"].update(p.get("tabelas") or {})
        exp["tipos"].update(p.get("tipos") or {})
        exp["chaves"].update(p.get("chaves") or {})
        if p.get("arquivos") is not None:
            exp["arquivos"] = p["arquivos"]
        g = p.get("gerado_em")
        exp["exportado_em"] = min(filter(None, (exp["exportado_em"], g)), default=None)
    faltam = [t for t in T.ORIGEM if t not in exp["tabelas"] or t not in exp["tipos"] or not exp["chaves"].get(t)]
    if faltam:
        raise ExportacaoIncompleta(f"a exportação do SSO está incompleta: falta {', '.join(faltam)}")
    if exp["arquivos"] is None:
        raise ExportacaoIncompleta("a exportação do SSO está incompleta: falta o inventário dos arquivos")
    return exp


def montar(partes: list[dict], *, cofre, agora) -> tuple[dict, dict]:
    """({livro: {aba: (cabeçalho, linhas)}}, relatório). Nada sai da máquina."""
    exp = juntar(partes)
    copiado_em = agora.isoformat(timespec="seconds")
    prontos = {lv: {} for lv in T.LIVROS}
    atualizacao = {lv: [] for lv in T.LIVROS}
    rel = {"exportado_em": exp["exportado_em"], "abas": {}}

    def por(aba, livro, colunas, linhas, chave):
        prontos[livro][aba] = guardar.para_aba(aba, colunas, linhas, cofre, chave, cifrada=T.coluna_cifrada,
                                               prefixo=PREFIXO)
        atualizacao[livro] += [[aba, c, t, chave, len(linhas), copiado_em, exp["exportado_em"], 0] for c, t in colunas]
        rel["abas"][aba] = {"origem": len(linhas), "nexus": None, "livro": livro}

    for origem, (aba, livro) in T.ORIGEM.items():
        colunas = [(c, t) for c, t in exp["tipos"][origem]]
        chave = exp["chaves"][origem].split(",")[0]
        por(aba, livro, colunas, exp["tabelas"][origem], chave)
    arquivos = [{"chave": f"{a.get('bucket')}/{a.get('caminho')}", **{c: a.get(c) for c, _t in T.COLUNAS_ARQUIVOS[1:]}}
                for a in exp["arquivos"]]
    por(T.ABA_ARQUIVOS, T.LIVRO_ARQUIVOS, T.COLUNAS_ARQUIVOS, arquivos, "chave")
    for livro in T.LIVROS:
        prontos[livro]["atualizacao"] = (list(CAB_ATUALIZACAO), atualizacao[livro])
    rel["linhas"] = sum(a["origem"] for a in rel["abas"].values())
    return prontos, rel


def versao_no_banco(base: str, sessao) -> int:
    """A maior versão gravada pelo Nexus nos livros do SSO (0 = só a cópia do Supabase, ou nada ainda)."""
    maior = 0
    for livro in T.LIVROS:
        ids = livros.abas(base, sessao, livro)
        if "atualizacao" not in ids:
            continue
        for linha in livros._linhas(base, sessao, ids["atualizacao"]):
            maior = max(maior, int(float(linha.get("versao") or 0)))
    return maior


def copiar(partes: list[dict], *, cofre, base: str, token: str, sessao, gravar: bool, agora,
           forcar: bool = False) -> dict:
    """Monta os livros e, com `gravar`, grava e confere cada um. Sem `gravar`, é o ensaio."""
    prontos, rel = montar(partes, cofre=cofre, agora=agora)
    rel["gravou"] = False
    if not gravar:
        return rel
    if not forcar and versao_no_banco(base, sessao) > 0:
        raise CopiaRecusada("o Nexus já gravou mudanças do SSO no banco: a cópia do Supabase passaria por cima delas")
    for livro in T.LIVROS:
        conferido = livros.publicar(livro, T.NOMES_LIVROS[livro], prontos[livro], base=base, token=token, sessao=sessao)
        for aba, n in conferido.items():
            if aba in rel["abas"]:
                rel["abas"][aba]["nexus"] = n
    rel["gravou"] = True
    return rel
