"""Prova de que os quatro relatórios do PCM no Nexus fazem as MESMAS contas que o Python do PCM (14/10/2026).

Roda as duas versões sobre os MESMOS arquivos (uma cópia do repositório do PCM: os JSON, o relatorio_diario.py, o
relatorios_semana.py e o novo.html, de onde sai a logo de lá) e compara a folha byte a byte, com o Nexus no formato de
número do Python (`regras.modo_original`), as trocas de texto de propósito desfeitas (`regras.TROCAS_DE_TEXTO`) e a logo
trocada por uma marca nas duas. Diferença em qualquer byte = as contas ou o texto divergiram.

    python ferramentas/prova_relatorios_pcm.py <pasta do repositório do PCM> [--dias 10]

Os feriados entram nas duas pelo relatorios/feriados.json (no PCM, o Alerta lia a planilha da pasta do PCM, que não está
no repositório). Não vai à rede: só lê a pasta.
"""
import argparse
import importlib
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nexus.pcm.relatorios import alerta, dados as D, diario, fechamento, regras, tarde  # noqa: E402

_LOGO = re.compile(r'<img class="logo"[^>]*>|<div class="logo-txt">Grid Co\.</div>')


def _normal(texto: str) -> str:
    return _LOGO.sub("<LOGO>", texto)


def _desfazer_trocas(texto: str) -> str:
    for nexus, pcm in regras.TROCAS_DE_TEXTO:
        texto = texto.replace(nexus, pcm)
    return texto


def _diferenca(a: str, b: str) -> str:
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    return f"byte {i}: PCM …{a[max(0, i - 80):i + 80]!r}…\n          Nexus …{b[max(0, i - 80):i + 80]!r}…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcm", help="pasta do repositório do PCM")
    ap.add_argument("--dias", type=int, default=10, help="quantos dias para trás no diário e na tarde")
    a = ap.parse_args()
    pasta = Path(a.pcm).resolve()
    os.environ["PCM_PROG_DIR"] = str(pasta)          # o relatorio_diario.py lê os arquivos daqui (BASE)
    sys.path.insert(0, str(pasta))
    rd = importlib.import_module("relatorio_diario")
    rs = importlib.import_module("relatorios_semana")

    ent = D.de_pasta(pasta)
    hoje = datetime.now(regras.BRT).date()
    falhas, conferidas = [], 0

    def comparar(nome, pcm_html, nexus_html):
        nonlocal conferidas
        conferidas += 1
        p, x = _normal(pcm_html), _desfazer_trocas(_normal(nexus_html))
        if p != x:
            falhas.append(f"{nome}: {_diferenca(p, x)}")
            print(f"DIFERENTE  {nome}")
        else:
            print(f"igual      {nome}  ({len(p):,} bytes)")

    with regras.modo_original():
        for k in range(1, a.dias + 1):
            dia = hoje - timedelta(days=k)
            gerado = datetime.combine(dia + timedelta(days=1), datetime.min.time(), regras.BRT).replace(hour=6, minute=10)
            comparar(f"diário {dia}", rd.montar_html(rd.calcular(dia), dia, gerado),
                     diario.montar_html(diario.calcular(ent, dia), dia, gerado))
            if dia.weekday() < 5:
                corte = datetime.combine(dia, datetime.min.time(), regras.BRT).replace(hour=13, minute=5)
                comparar(f"tarde  {dia}", rd.montar_html_matinal(rd.calcular_matinal(dia), dia, corte),
                         tarde.montar_html(tarde.calcular(ent, dia), dia, corte))
        dados_pcm = {"bd": ent["bd"], "gestao": ent["gestao"], "gerencial": ent["gerencial"],
                     "engenharia": ent["engenharia"], "operacoes": ent["operacoes"], "feriados": ent["feriados"]}
        for w in sorted(s["week"] for s in ent["bd"].get("semanas", [])):
            gerado = datetime.combine(regras.semana_seg(w) + timedelta(days=4), datetime.min.time(), regras.BRT).replace(hour=17, minute=20)
            ori = rs.fechamento_semana(dados_pcm, w, gerado, logo=rd.logo_html())
            nex = fechamento.gerar(ent, w, gerado)
            comparar(f"fechamento {w}", ori["html"], nex["html"])
            ori = rs.alerta_programacao(dados_pcm, w, gerado, logo=rd.logo_html())
            nex = alerta.gerar(ent, w, gerado)
            comparar(f"alerta     {w}", ori["html"], nex["html"])
    print(f"\n{conferidas - len(falhas)} de {conferidas} folhas iguais byte a byte.")
    for f in falhas:
        print("\n" + f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
