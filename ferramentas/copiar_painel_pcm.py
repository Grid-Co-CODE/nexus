"""Copia para o Nexus os trechos do painel do PCM que o Relatório executivo usa (14/10/2026).

O `js/relatorio_exec.js` do painel chama funções que moram no `js/app.js` e no `js/preventivas.js` de lá (o escopo do
login, a situação de cada MPA/MPS, a Fila da Gerencial). Este script as copia LINHA A LINHA, pelas faixas de `TRECHOS`,
para `nexus/pcm/relatorio_exec/painel_pcm.js`, cada uma com a origem num comentário; não edita nada. Quando o PCM
mexer nesses arquivos, confira as faixas (as funções podem ter mudado de linha), rode de novo e ponha o hash novo em
`COPIAS` (o teste diz qual). Não vai à rede: só lê a pasta.

    python ferramentas/copiar_painel_pcm.py <pasta do repositório do PCM> <commit de lá>
"""
import argparse
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "nexus" / "pcm" / "relatorio_exec" / "painel_pcm.js"

# (arquivo, primeira linha, última linha, para que serve) — main e6cdab4 do repositório do PCM, 14/10/2026
TRECHOS = [
    ("js/app.js", 206, 206, "o cliente igual sem caixa (usado pelo gpScopedTarefas)"),
    ("js/app.js", 2965, 2971, "as tarefas do escopo do login (no Nexus, sempre a visão de administrador)"),
    ("js/app.js", 582, 582, "a Gerencial aberta (MP); o pacote cifrado não vem ao navegador no Nexus"),
    ("js/app.js", 638, 650, "a situação de cada MPA/MPS (mesma regra do site MPAS)"),
    ("js/preventivas.js", 41, 41, "o estado da Gerencial (no Nexus: 'ok' quando o servidor a abriu)"),
    ("js/preventivas.js", 47, 67, "o nome da usina normalizado e a última observação datada"),
    ("js/preventivas.js", 118, 126, "a criticidade em três baldes"),
    ("js/preventivas.js", 149, 149, "a sigla da preventiva na tarefa"),
    ("js/preventivas.js", 177, 181, "dias desde uma data e o hoje"),
    ("js/preventivas.js", 334, 373, "a Fila das MPA/MPS: Gerencial + Fracttal (o 'MPA/MPS atrasadas' do relatório)"),
]


def gerar(pcm: Path, commit: str) -> str:
    partes = [
        "/* Trechos do painel do PCM (repositório fillipefigueiro-source/gridco-pcm-data, main " + commit + ") que o\n"
        "   relatorio_exec.js usa, copiados LINHA A LINHA, sem editar, pelo ferramentas/copiar_painel_pcm.py (as faixas\n"
        "   de linha de cada trecho estão no comentário dele). NÃO EDITE: o teste confere o hash (COPIAS no\n"
        "   __init__.py). Para atualizar, veja o CLAUDE.md desta pasta. */\n"
    ]
    for arq, de, ate, porque in TRECHOS:
        linhas = (pcm / arq).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
        partes.append(f"\n// ── {arq}, linhas {de}-{ate}: {porque} ──\n")
        partes.append("\n".join(linhas[de - 1:ate]) + "\n")
    return "".join(partes)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pcm", type=Path, help="a pasta do repositório do PCM (com js/app.js e js/preventivas.js)")
    ap.add_argument("commit", help="o commit de lá, para o cabeçalho")
    a = ap.parse_args()
    DESTINO.write_text(gerar(a.pcm, a.commit), encoding="utf-8", newline="\n")
    print(f"ok: {DESTINO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
