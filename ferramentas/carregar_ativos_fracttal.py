"""MEDE a foto de ativos do Fracttal contra a dimensão de equipamento (passo 6a do Kimball, 08/10/2026). Não grava.

A dimensão de equipamento (`nexus/dados/equipamento.py`) só pode nascer do que as duas máquinas leem igual, o banco. A
lista completa de ativos do Fracttal existia só no cache que o OS Creator guardava em arquivo (o `assets_cache.json`, uma
foto por leitura), e este script a pôs UMA vez em `nexus_ativos_fracttal · foto_ativos` (11/10/2026, com `--gravar`).

Desde 31/10/2026 a foto é renovada toda noite pelo leitor dos ativos do servidor (`nexus/torres/oscreator/os_creator/
ativos_leitor.py`, a montagem e a gravação em `nexus/dados/foto_ativos.py`): uma máquina grava (regra 11 do
`nexus/dados/CLAUDE.md`), e é o servidor. O `--gravar` saiu daqui por isso: gravar do PC por cima da renovação da noite
trocaria a foto por um arquivo de outra máquina e apagaria a marca dos códigos que saíram do Fracttal.

Ficou a medição: monta a foto dos arquivos, lê o banco (GET) e o PCM público, monta a dimensão em memória e imprime as
contagens, ao lado das da foto que está no banco agora.

    python ferramentas/carregar_ativos_fracttal.py <foto_nova.json> [<foto_antiga.json>]

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
from nexus.dados import foto_ativos  # noqa: E402
from nexus.dados import livros  # noqa: E402


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
    if "--gravar" in sys.argv:
        raise SystemExit("o --gravar saiu (31/10/2026): a foto é renovada toda noite pelo leitor do servidor, e uma máquina "
                         "grava (regra 11 do nexus/dados/CLAUDE.md). Este script só mede.")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    nova = _ler_foto(args[0])
    antiga = _ler_foto(args[1]) if len(args) > 1 else None
    foto = eq.foto_linhas(nova, antiga)
    rel = foto_ativos.contar(foto)
    s = requests.Session()
    base = (os.environ.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
    try:
        rel["no_banco"] = foto_ativos.contar(foto_ativos.ler(base, s)[0])
    except Exception as e:                                   # noqa: BLE001 — a medição segue sem a do banco
        rel["no_banco"] = f"não li a foto do banco: {type(e).__name__}: {str(e)[:120]}"
    rel["dimensao_em_ensaio"] = ensaio(base, s, foto)
    rel["ensaio"] = "montado com o dado real; nada gravado"
    print(json.dumps(rel, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
