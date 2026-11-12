"""Os livros do SSO lidos do banco do Nexus e decifrados, com as linhas como o app as recebia do Supabase."""
from __future__ import annotations

from ..dados import livros
from ..zeladoria import guardar
from . import tabelas as T
from .copia import PREFIXO


class CopiaAusente(RuntimeError):
    """O livro, a aba ou a contagem faltam no banco: a cópia não foi feita (ou ficou pela metade)."""


def ler_banco(base: str, sessao, cofre) -> dict:
    """{"abas": {aba: [linha]}, "tipos", "chaves", "exportado_em", "copiado_em", "versao"}."""
    abas, tipos, chaves, origem = {}, {}, {}, {}
    exportado_em = copiado_em = None
    versao = 0
    for livro in T.LIVROS:
        ids = livros.abas(base, sessao, livro)
        if "atualizacao" not in ids:
            raise CopiaAusente(f"a cópia do SSO ainda não foi feita ({livro} não está no banco)")
        for l in livros._linhas(base, sessao, ids["atualizacao"]):
            aba = str(l.get("aba") or "")
            tipos.setdefault(aba, {})[str(l.get("coluna"))] = str(l.get("tipo_pg") or "text")
            chaves[aba] = str(l.get("chave") or "id")
            origem[aba] = int(float(l.get("linhas_origem") or 0))
            exportado_em = l.get("exportado_em") or exportado_em
            copiado_em = l.get("copiado_em") or copiado_em
            versao = max(versao, int(float(l.get("versao") or 0)))
        for aba in (a for a, lv in T.TABELAS.items() if lv == livro):
            if aba not in ids or aba not in tipos:
                raise CopiaAusente(f"a cópia do SSO está incompleta: falta {aba}")
            linhas = livros._linhas(base, sessao, ids[aba])
            if len(linhas) != origem[aba]:
                raise CopiaAusente(f"a cópia do SSO está pela metade: {aba} tem {len(linhas)} de {origem[aba]}")
            abas[aba] = guardar.de_aba(aba, tipos[aba], linhas, cofre, chaves[aba], cifrada=T.coluna_cifrada,
                                       prefixo=PREFIXO)
    return {"abas": abas, "tipos": tipos, "chaves": chaves, "exportado_em": exportado_em, "copiado_em": copiado_em,
            "versao": versao}
