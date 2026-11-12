# -*- coding: utf-8 -*-
"""Traz o motor do Conversor Grid Co. para a tela Coletas do Nexus (Performance > Coletas, 11/11/2026).

O Conversor (o .exe do backoffice) mora na pasta da coleta, `ferramentas/conversor/conversor/`. A regra dele (leitores,
montagem, sessão) é UMA só: a tela do Nexus usa uma CÓPIA IDÊNTICA, byte a byte, em
`nexus/performance/coletas/_motor/conversor/`. Mudou um leitor lá, rode isto e suba o Nexus no mesmo trabalho; o teste
`tests/test_coletas_motor.py` quebra quando a cópia e a pasta da coleta divergem (só onde a pasta existe: no servidor
ela não existe e o teste pula).

Fica de fora o que é só da janela do Windows: `app.py` (pywebview). O `atualizacao.py` vem porque o `furos.py` o
importa (o Nexus não usa a release dele). A tela (`ui/index.html` e `ui/furos.js`) é GERADA para o Nexus por `portar_tela_conversor.py`, com as trocas
de quem roda num servidor (lá está o porquê de cada uma): `templates/performance/coletas_app.html` e
`static/coletas/furos.js`.

Uso: python ferramentas/sincronizar_conversor.py [--origem <pasta conversor/conversor>] [--conferir]
"""
import argparse
import filecmp
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portar_tela_conversor as portar  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "nexus", "performance", "coletas", "_motor", "conversor")
ORIGEM_PADRAO = os.path.join(os.path.expanduser("~"), "OneDrive - GRID CO", "Área de Trabalho", "temp", "coleta API PV",
                             "ferramentas", "conversor", "conversor")
FORA = {"app.py"}            # o atualizacao.py vem: o furos.py acha as pastas por ele (o Nexus não usa a release)


def arquivos(origem):
    """Os .py do motor, relativos à pasta `conversor/` (sem a casca da janela nem o __pycache__)."""
    out = []
    for raiz, pastas, nomes in os.walk(origem):
        pastas[:] = [p for p in pastas if p not in ("__pycache__", "ui")]
        for n in nomes:
            rel = os.path.relpath(os.path.join(raiz, n), origem)
            if n.endswith(".py") and rel not in FORA:
                out.append(rel)
    return sorted(out)


def diferencas(origem, destino=DESTINO):
    """(faltam no Nexus ou diferentes, sobram no Nexus) — vazio e vazio = cópia idêntica."""
    lado = set(arquivos(origem))
    nexus = set(arquivos(destino)) if os.path.isdir(destino) else set()
    dif = sorted(r for r in lado if r not in nexus or not filecmp.cmp(os.path.join(origem, r),
                                                                     os.path.join(destino, r), shallow=False))
    return dif, sorted(nexus - lado)


def sincronizar(origem, destino=DESTINO):
    dif, sobra = diferencas(origem, destino)
    for r in dif:
        os.makedirs(os.path.dirname(os.path.join(destino, r)), exist_ok=True)
        shutil.copyfile(os.path.join(origem, r), os.path.join(destino, r))
    for r in sobra:
        os.remove(os.path.join(destino, r))
    return dif, sobra


def tela_difere(origem):
    """Os arquivos gerados da tela que não batem com o que a tela do .exe geraria agora."""
    pagina, furos = portar.gerar(os.path.join(origem, "ui"))
    out = []
    for caminho, texto in ((portar.PAGINA, pagina), (portar.FUROS_JS, furos)):
        atual = open(caminho, encoding="utf-8").read() if os.path.isfile(caminho) else None
        if atual != texto:
            out.append(os.path.relpath(caminho, RAIZ))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origem", default=os.environ.get("CONVERSOR_DIR") or ORIGEM_PADRAO)
    ap.add_argument("--conferir", action="store_true", help="só diz o que difere, não copia")
    a = ap.parse_args()
    if not os.path.isdir(a.origem):
        sys.exit(f"não achei a pasta do Conversor: {a.origem}")
    dif, sobra = diferencas(a.origem) if a.conferir else sincronizar(a.origem)
    if a.conferir:
        dif += tela_difere(a.origem)
    else:
        dif += [os.path.relpath(c, RAIZ) for c in portar.escrever(os.path.join(a.origem, "ui"))]
    verbo = "difere" if a.conferir else "copiado"
    for r in dif:
        print(f"{verbo}: {r}")
    for r in sobra:
        print(f"{'sobra' if a.conferir else 'removido'}: {r}")
    print("cópia idêntica" if not (dif or sobra) and a.conferir else f"{len(dif)} arquivo(s), {len(sobra)} removido(s)")
    return 1 if a.conferir and (dif or sobra) else 0


if __name__ == "__main__":
    sys.exit(main())
