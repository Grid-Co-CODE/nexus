"""Carga única da estrutura de O&M de 10/2026 no cadastro LOCAL do Nexus (as regiões de campo, com as vagas, e o código e
a região de cada equipe volante). A regra está em nexus/cadastro/estrutura_campo.py; o porquê, em nexus/cadastro/CLAUDE.md.

    python ferramentas/importar_estrutura_campo.py <csv>             ensaio (o padrão): diz o que faria, não grava nada
    python ferramentas/importar_estrutura_campo.py <csv> --aplicar   grava no armazém local, com cópia antes, e confere

O CSV (';', UTF-8) tem regiao_campo, base_regiao, codigo_equipe, equipe e base_equipe; mora fora do git
(C:\\GridcoAuto\\nexus\\estrutura_campo_2026-10.csv). NADA vai ao banco: a publicação é a de sempre
(`python ferramentas/publicar_cadastro.py --ensaio`, depois sem `--ensaio`). Lê do .env do Nexus a NEXUS_CHAVE_CADASTRO
(nunca impressa) e o NEXUS_ARMAZEM_LOCAL. Imprime regiões, equipes e contagens; nome de pessoa, nunca (a região nasce vaga).

Atenção (08/10/2026): um Nexus que subiu ANTES deste código não conhece os campos novos da equipe. Se alguém salvar uma
equipe, ou importar o BD_Operações, por ele, a equipe é regravada sem o código e a região. Reinicie o Nexus local com
este código antes de editar equipe pela tela.
"""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from nexus.cadastro import estrutura_campo as E  # noqa: E402
from nexus.cadastro.armazem import ArmazemLocal  # noqa: E402
from nexus.cadastro.cifra import Cofre  # noqa: E402
from nexus.cadastro.servico import Servico  # noqa: E402
from nexus.cadastro.telas import ARMAZEM_PADRAO  # noqa: E402
from nexus.config import ler_ambiente  # noqa: E402


def relatorio(plano: E.Plano) -> list[str]:
    linhas = [f"Regiões de campo ({len(plano.regioes)}):"]
    for r in plano.regioes:
        n_eq = sum(1 for c in plano.casadas if c["regiao"] == r["nome"])
        linhas.append(f"  {r['ordem']}. {r['nome']} · base {r['base']} · "
                      f"{'já existe (ID ' + str(r['id']) + ')' if r['id'] else 'nova, com as vagas abertas'} · "
                      f"{n_eq} equipe(s) casada(s) · {plano.usinas_por_regiao.get(r['nome'], 0)} usina(s) em operação")
    linhas.append(f"  Sem região de campo: {plano.usinas_por_regiao.get(E.SEM_REGIAO, 0)} usina(s) em operação "
                  "(equipes de fora da estrutura)")
    total = len(plano.casadas) + len(plano.fora)
    por_como = {k: sum(1 for c in plano.casadas if c["como"] == k) for k in ("exato", "normalizado")}
    linhas.append(f"Equipes do CSV: {total}; casaram {len(plano.casadas)} (pelo nome exato {por_como['exato']}, "
                  f"sem acento/caixa/espaço {por_como['normalizado']}); fora {len(plano.fora)}")
    for c in plano.casadas:
        if c["como"] != "exato":
            linhas.append(f"  casou sem acento/caixa/espaço: {c['codigo']} {c['equipe_csv']!r} = {c['nome_cadastro']!r} "
                          f"(ID {c['equipe_id']})")
    for f in plano.fora:
        linhas.append(f"  FORA: {f['codigo']} {f['equipe_csv']} ({f['regiao']}): {f['motivo']}")
    trocas = [c for c in plano.casadas if c["muda"] and any(a for a, _ in c["muda"].values())]
    for c in trocas:
        linhas.append(f"  TROCA na equipe {c['equipe_id']} ({c['nome_cadastro']}): " + "; ".join(
            f"{k}: {a!r} -> {d!r}" for k, (a, d) in c["muda"].items()))
    if plano.vinculos_faltando:
        linhas.append("Vínculos que entram na lista: " + ", ".join(plano.vinculos_faltando))
    linhas += [f"Aviso: {a}" for a in plano.avisos]
    return linhas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--aplicar", action="store_true", help="grava no armazém local (sem isto, só o ensaio)")
    a = ap.parse_args()
    env = ler_ambiente()
    if not env.get("NEXUS_CHAVE_CADASTRO"):
        sys.exit("falta NEXUS_CHAVE_CADASTRO no .env do Nexus")
    caminho = Path(env.get("NEXUS_ARMAZEM_LOCAL") or ARMAZEM_PADRAO)
    if not caminho.exists():
        sys.exit(f"o armazém do cadastro não está nesta máquina: {caminho}")
    srv = Servico(ArmazemLocal(caminho), Cofre(env["NEXUS_CHAVE_CADASTRO"]))
    try:
        linhas = E.ler_csv(Path(a.csv).read_text(encoding="utf-8"))
    except E.EstruturaErro as e:
        sys.exit(f"CSV recusado: {e}")
    plano = E.planejar(srv, linhas)
    print(f"armazém: {caminho}")
    print("\n".join(relatorio(plano)))
    if not a.aplicar:
        print("ENSAIO: nada gravado. Para gravar no armazém local: --aplicar")
        return
    pasta = caminho.parent / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    copia = pasta / f"{caminho.stem}_{datetime.now():%Y%m%d_%H%M%S}_antes_estrutura_campo.json"
    shutil.copy2(caminho, copia)
    print(f"cópia de antes: {copia}")
    antes = E.foto(srv)
    res = E.aplicar(srv, plano)
    srv._cache = None
    problemas = E.conferir(Servico(ArmazemLocal(caminho), Cofre(env["NEXUS_CHAVE_CADASTRO"])), plano, antes)
    print(f"gravado: {len(res['regioes'])} regiões, {res['equipes_gravadas']} equipe(s) com código e região")
    for e in res["erros"]:
        print(f"ERRO: {e}")
    if problemas:
        print("CONFERÊNCIA FALHOU:")
        for p in problemas:
            print(f"  {p}")
        sys.exit(f"a cópia de antes está em {copia}")
    print("conferido: as regiões, o código e a região das equipes casadas; usinas, pessoas e clientes intactos")


if __name__ == "__main__":
    main()
