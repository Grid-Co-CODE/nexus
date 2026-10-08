"""A carga da camada de dados à mão (a mesma que o Nexus roda de hora em hora, aos :40). Imprime só contagens.

    python ferramentas/carregar_dados.py --ensaio     monta com o dado real e NÃO grava (medir antes de gravar)
    python ferramentas/carregar_dados.py --ensaio --sem-geracao     idem, sem ler as 171 abas de geração (~1 min)
    python ferramentas/carregar_dados.py              grava se a última carga tiver mais de 50 min
    python ferramentas/carregar_dados.py --forcar     grava agora

O `--ensaio` mostra também o que ainda NÃO é gravado (08/10/2026, decisões 7 e 8 do Levi): a programação do PCM e a
geração em linhas. Para cada aba: linhas, chave repetida (tem de ser 0) e o tamanho do xlsx que seria enviado.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from nexus import create_app  # noqa: E402
from nexus.cadastro.banco import xlsx_bytes  # noqa: E402
from nexus.dados import carga, geracao  # noqa: E402

# a chave de cada aba (o grão): repetida = o fato conta em dobro
_CHAVE = {"pessoas_historico": ("pessoa_id", "versao"), "usinas_historico": ("usina_id", "versao"),
          "dim_equipamento": ("equipamento_id",), "dim_data": ("data_id",)}


def _repetidas(aba: str, cab: list, linhas: list) -> int | None:
    cols = _CHAVE.get(aba) or ((cab[0],) if aba.startswith("fato_") else None)
    if not cols:
        return None
    i = [cab.index(c) for c in cols]
    cont = Counter(tuple(l[k] for k in i) for l in linhas)
    return sum(n - 1 for n in cont.values() if n > 1)


def _medir(livros: dict, grava: bool) -> dict:
    out = {}
    for livro, tabelas in livros.items():
        t = time.time()
        mb = round(len(xlsx_bytes(tabelas)) / 1e6, 2)
        out[livro] = {"grava_na_carga": grava, "xlsx_mb": mb, "xlsx_s": round(time.time() - t, 1),
                      "abas": {aba: {"linhas": len(l), "chave_repetida": _repetidas(aba, cab, l)}
                               for aba, (cab, l) in tabelas.items()}}
    return out


def main():
    app = create_app()
    ensaio = "--ensaio" in sys.argv
    with app.app_context():
        if ensaio:
            s = requests.Session()
            t0 = time.time()
            grava, montados, rel = carga.montar(app.config, s, ensaio=True)
            rel["tempo_montar_s"] = round(time.time() - t0, 1)
            if "--sem-geracao" not in sys.argv:
                # os apelidos da dimensão montada AGORA (o equipamento do inversor vem só deles), não os publicados
                eqt = grava.get("nexus_equipamentos") or montados.get("nexus_equipamentos") or {}
                apel = eqt.get("equipamento_apelido", (None, []))[1]
                tab_g, inversor, rel_g = carga.montar_geracao(app.config, s, apelidos=apel)
                montados["nexus_geracao"] = tab_g
                # o inversor × dia não vai a livro nenhum (não cabe em troca integral): mede-se aqui
                rel_g["linhas_inversor_dia"] = len(inversor)
                rel_g["inversor_chave_repetida"] = _repetidas("fato_geracao_inversor_dia", geracao.CAB_INVERSOR_DIA,
                                                              inversor)
                rel["geracao"] = rel_g
            rel["livros"] = {**_medir(grava, True), **_medir(montados, False)}
            rel["ensaio"] = "montado com o dado real; nada gravado"
        else:
            rel = carga.rodar(app.config, requests.Session(), forcar="--forcar" in sys.argv)
    print(json.dumps(rel, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
