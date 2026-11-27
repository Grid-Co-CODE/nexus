r"""Gera o NexusPCM.exe (um arquivo só, sem instalar Python) com o PyInstaller.

Uso (nesta pasta): python construir.py [pasta de saída]. A saída padrão fica FORA do repositório
(%LOCALAPPDATA%/NexusPCM-build): o .exe não entra no git; vai para a página de versões do GitHub (o link
"Baixar o aplicativo" da tela Gerar a semana aponta para a última).
"""
import os
import sys
from pathlib import Path

import PyInstaller.__main__

AQUI = Path(__file__).resolve().parent
saida = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("LOCALAPPDATA", ".")) / "NexusPCM-build"
PyInstaller.__main__.run([
    str(AQUI / "nexus_pcm.py"), "--name", "NexusPCM", "--onefile", "--windowed", "--noconfirm", "--clean",
    "--distpath", str(saida / "dist"), "--workpath", str(saida / "build"), "--specpath", str(saida),
    # o motor vem no pacote de cada rodada, à parte: o .exe precisa ter o que ele importa
    "--hidden-import", "pandas", "--hidden-import", "openpyxl", "--hidden-import", "requests",
    "--hidden-import", "numpy", "--collect-submodules", "openpyxl",
])
print("pronto:", saida / "dist" / "NexusPCM.exe")
