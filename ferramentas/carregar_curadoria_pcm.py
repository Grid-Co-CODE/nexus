"""Carrega no banco a curadoria do PCM (o arquivo `scripts/curadoria.json` do painel de acompanhamento do PCM O&M) para o
Acompanhamento do Nexus (14/10/2026).

A curadoria é a decisão da reunião de PCM sobre cada MPA e MPS acompanhada (grupo, prazo, o que falta...). No painel
ela era um arquivo no computador de quem o mantinha; no Nexus é o livro `nexus_pcm_curadoria`, cifrado com a chave do
cadastro (regras em `nexus/pcm/acompanhamento/curadoria.py`). A regra do responsável da Manutenção (quem cuida do Norte e
Nordeste e quem cuida do resto) entra pelos argumentos: no painel ela estava no código.

Sem `--gravar`, só mostra o que gravaria (nada sai da máquina). Com `--gravar`, grava (usa a `GRIDCO_SQL_TOKEN` e a
`NEXUS_CHAVE_CADASTRO` do .env do Nexus, sem imprimir nenhuma) e relê o livro para conferir que todos os itens abrem.

    python ferramentas/carregar_curadoria_pcm.py <curadoria.json> --nne "<nome>" --outros "<nome>" [--gravar]
"""
import argparse
import collections
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("arquivo", type=Path, help="o curadoria.json do painel do PCM")
    ap.add_argument("--nne", default="", help="o responsável da Manutenção do Norte e Nordeste")
    ap.add_argument("--outros", default="", help="o responsável da Manutenção do Sul, Sudeste e Centro-Oeste")
    ap.add_argument("--gravar", action="store_true", help="grava no banco (sem isto, só mostra)")
    a = ap.parse_args()

    from nexus import create_app
    from nexus.pcm.acompanhamento import curadoria as CUR

    itens, man = CUR.de_arquivo(a.arquivo)
    if a.nne or a.outros:
        man = {"nne": a.nne, "outros": a.outros}
    grupos = collections.Counter((it.get("tipo"), it.get("grupo")) for it in itens)
    print(f"{len(itens)} itens ({', '.join(f'{t} grupo {g}: {n}' for (t, g), n in sorted(grupos.items(), key=str))}); "
          f"regra da Manutenção: {'sim' if man else 'não'}")
    ids = [CUR.item_id(it) for it in itens]
    if len(set(ids)) != len(ids):
        raise SystemExit("Dois itens com o mesmo tipo, usina e OS: confira o arquivo antes de gravar.")
    if not a.gravar:
        print("Nada gravado (sem --gravar).")
        return

    app = create_app()
    # a chave de gravação não é NEXUS_*: rodando de uma worktree sem o .env, ela vem do ambiente (nunca impressa)
    if os.environ.get("GRIDCO_SQL_TOKEN") and not app.config.get("GRIDCO_SQL_TOKEN"):
        app.config["GRIDCO_SQL_TOKEN"] = os.environ["GRIDCO_SQL_TOKEN"]
    with app.app_context():
        from nexus.auth import setor_telas
        base, sessao = setor_telas._banco()
        r = CUR.gravar(itens, man, app.config, base, sessao, origem="painel do PCM (curadoria.json)")
        print(f"Gravado: {r['gravadas']} decisões, {r['tiradas']} itens tirados.")
        lido = CUR.ler(app.config, base, sessao, forcar=True)
        if lido["erro"]:
            raise SystemExit(f"Relido com erro: {lido['erro']}")
        abertos = {it["id"] for it in lido["itens"]}
        faltam = [i for i in ids if i not in abertos]
        print(f"Relido do banco: {len(lido['itens'])} itens abertos, {lido['ilegiveis']} ilegíveis, "
              f"regra da Manutenção {'ok' if lido['manutencao'] else 'ausente'}; faltam {len(faltam)}.")
        if faltam or lido["ilegiveis"]:
            raise SystemExit("A conferência não fechou: veja acima.")


if __name__ == "__main__":
    main()
