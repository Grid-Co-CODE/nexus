"""Compara duas gerações da MESMA semana, linha a linha: a oficial (a do PCM) e a do Nexus.

Chave da linha: OS + código do equipamento + tarefa (a mesma tarefa aparece em mais de um ativo da OS). Compara equipe,
dia, hora, duração, reprogramada, nº de vezes e RPN; e as pendentes. É a mesma conta do sombra/comparar.py do plano,
testada nas duas gerações da semana 40 (417 reprogramadas por engano, +1 vez nas 1.011 que estavam nas duas).
"""
import re
from collections import Counter

import openpyxl

CAMPOS = ["Equipe", "Dia", "Hora Início", "Duração (h)", "Reprogramada", "Nº vezes programada", "RPN/Prioridade"]


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return ("%.2f" % v).rstrip("0").rstrip(".")
    return str(v).strip()


def ler(caminho) -> tuple[dict, Counter]:
    """(linhas por chave, pendentes por chave) de uma Programação Semana XX.xlsx."""
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    linhas, pend, dup = {}, Counter(), 0
    try:
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            cab = next(it, None)
            if not cab or "OSs ID" not in cab:
                continue
            ix = {c: i for i, c in enumerate(cab)}
            for r in it:
                if not r or r[ix["OSs ID"]] in (None, ""):
                    continue
                chave = (_txt(r[ix["OSs ID"]]),
                         _txt(r[ix["Código Equipamento"]]) if "Código Equipamento" in ix else "",
                         _txt(r[ix["Tarefa"]]) if "Tarefa" in ix else "")
                if ws.title == "_Pendentes":
                    pend[chave] += 1
                    continue
                if ws.title.startswith("_"):
                    continue
                reg = {c: _txt(r[ix[c]]) if c in ix else "" for c in CAMPOS}
                reg["Equipe"] = reg["Equipe"] or ws.title
                # "Quarta-feira (01/10) [NOTURNO]": a marcação vira campo próprio
                reg["Marcação"] = " ".join(re.findall(r"\[[^\]]+\]", reg["Dia"]))
                reg["Dia"] = re.sub(r"\s*\[[^\]]+\]", "", reg["Dia"]).strip()
                if chave in linhas:
                    dup += 1
                    chave = chave + ("#%d" % dup,)
                linhas[chave] = reg
    finally:
        wb.close()
    return linhas, pend


def comparar(oficial, nexus) -> dict:
    A, pa = ler(oficial)
    B, pb = ler(nexus)
    comuns = sorted(set(A) & set(B))
    so_a, so_b = sorted(set(A) - set(B)), sorted(set(B) - set(A))
    dif, exemplos = Counter(), {}
    for k in comuns:
        for c in CAMPOS + ["Marcação"]:
            if A[k][c] != B[k][c]:
                dif[c] += 1
                exemplos.setdefault(c, {"os": k[0], "oficial": A[k][c], "nexus": B[k][c]})
    iguais = sum(1 for k in comuns if all(A[k][c] == B[k][c] for c in CAMPOS + ["Marcação"]))
    return {
        "linhas_a": len(A), "linhas_b": len(B), "comuns": len(comuns), "iguais": iguais,
        "so_a": len(so_a), "so_b": len(so_b),
        "os_so_a": sorted({k[0] for k in so_a})[:15], "os_so_b": sorted({k[0] for k in so_b})[:15],
        "diferencas": dict(dif.most_common()), "exemplos": exemplos,
        "pendentes_a": sum(pa.values()), "pendentes_b": sum(pb.values()), "pendentes_iguais": pa == pb,
        "identicas": not so_a and not so_b and not dif and pa == pb,
    }


def resumo(caminho) -> dict:
    linhas, pend = ler(caminho)
    return {"linhas": len(linhas), "pendentes": sum(pend.values()),
            "equipes": len({r["Equipe"] for r in linhas.values()})}
