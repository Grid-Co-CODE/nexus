"""Carga ÚNICA da foto de ativos do Fracttal para o banco (passo 6a do Kimball, 08/10/2026).

A dimensão de equipamento (`nexus/dados/equipamento.py`) só pode nascer do que as duas máquinas leem igual, o banco. A
lista completa de ativos do Fracttal só existe no cache que o OS Creator guardou em arquivo (o `assets_cache.json`, uma
foto por leitura). Este script põe essa foto UMA vez em `nexus_ativos_fracttal · foto_ativos`; a carga de hora em hora
lê dali e nunca o arquivo (o servidor tem outro, ou nenhum). Renovar a foto exige ler o Fracttal (a cota é da empresa):
fica para fora do horário de campo, por decisão do Levi.

Sem `--gravar`, só mede: monta a foto, lê o banco (GET) e o PCM público, monta a dimensão em memória e imprime
contagens. Com `--gravar` (quem grava é o Levi), publica o livro da foto e confere a contagem relida.

    python ferramentas/carregar_ativos_fracttal.py <foto_nova.json> [<foto_antiga.json>]
    python ferramentas/carregar_ativos_fracttal.py <foto_nova.json> [<foto_antiga.json>] --gravar

A foto antiga é opcional: dela entram só os códigos que a nova não tem (renomeados ou baixados), para o código antigo
que um fato ainda carrega continuar sendo membro.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from nexus.cadastro.ligacoes import BASE_API  # noqa: E402
from nexus.dados import equipamento as eq  # noqa: E402
from nexus.dados import livros  # noqa: E402

CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "como_ler"]


def _ler_foto(caminho) -> dict:
    d = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(d, dict) or not isinstance(d.get("assets"), list):
        raise SystemExit(f"{caminho}: não é o cache de ativos do OS Creator ({{'ts', 'assets'}})")
    return d


def _codigos_pcm() -> list:
    """Os códigos da programação do PCM (o mesmo `banco_dados.json` público que o App e o Nexus leem)."""
    from nexus.pcm import fonte
    lido = fonte.ler({})
    return [r.get("codigo") for s in (lido.dados or {}).get("semanas") or () for r in s.get("rows") or ()]


def ensaio(base, sessao, foto: list[list]) -> dict:
    """A dimensão montada com esta foto e o banco de hoje, sem gravar. As colunas de geração ficam de fora: a ligação
    aba → usina é da geração (passo 6c) e a carga de hora em hora é que as passa."""
    ler = lambda livro, aba: livros.ler(base, sessao, livro, aba)        # noqa: E731
    cod = {nome: [r.get(col) for r in ler(livro, aba)] for nome, livro, aba, col in eq.FONTES_BANCO}
    cod["pcm"] = _codigos_pcm()
    agora = datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="seconds")
    _tab, rel = eq.montar([dict(zip(eq.CAB_FOTO, l)) for l in foto], cod, ler("cadastro_nexus", "usinas"),
                          ler("de_para_trackers", "De-Para Trackers"), ler("gemeo_digital", "alias"), [],
                          agora=agora, maquina="ensaio")
    return rel


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    nova = _ler_foto(args[0])
    antiga = _ler_foto(args[1]) if len(args) > 1 else None
    foto = eq.foto_linhas(nova, antiga)
    rel = {"foto_ativos": len(foto), "sem_codigo": sum(1 for l in foto if not l[1]),
           "por_foto": {d: sum(1 for l in foto if l[5] == d) for d in sorted({l[5] for l in foto if l[5]})}}
    s = requests.Session()
    base = (os.environ.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
    if "--gravar" not in sys.argv:
        rel["dimensao_em_ensaio"] = ensaio(base, s, foto)
        rel["ensaio"] = "montado com o dado real; nada gravado"
        print(json.dumps(rel, ensure_ascii=False, indent=1))
        return
    from nexus import create_app
    config = create_app().config
    base = (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
    ja = livros.ler(base, s, eq.LIVRO_FOTO, eq.ABA_FOTO)
    if len(ja) > len(foto) and "--substituir" not in sys.argv:
        # a gravação troca o livro inteiro: rodar de novo com uma foto só apagaria os códigos antigos
        raise SystemExit(f"o banco já tem {len(ja)} linhas e esta foto tem {len(foto)}; nada gravado "
                         "(use --substituir se for de propósito)")
    agora = datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="seconds")
    tabelas = {eq.ABA_FOTO: (eq.CAB_FOTO, foto),
               "atualizacao": (CAB_ATUALIZACAO, [[agora, "pc", None, len(foto),
                                                  "carga única; foto_em = o dia da leitura do Fracttal"]])}
    rel["gravado"] = livros.publicar(eq.LIVRO_FOTO, eq.NOME_FOTO, tabelas, base=base,
                                     token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    print(json.dumps(rel, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
