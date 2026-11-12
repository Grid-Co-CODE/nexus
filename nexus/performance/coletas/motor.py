# -*- coding: utf-8 -*-
"""Põe o motor do Conversor Grid Co. (a cópia idêntica em `_motor/conversor/`) no caminho de importação como o pacote
`conversor`, que é como os leitores dele se importam ("from conversor.nucleo import ...", "conversor.leitores.sal").

Por que não reescrever os imports da cópia: a cópia é byte a byte a da pasta da coleta (`ferramentas/
sincronizar_conversor.py` e o teste `test_coletas_motor.py`), então mudar um leitor lá e trazê-lo é copiar, sem
conversão. Importe este módulo ANTES de qualquer `conversor.*`; tudo na tela Coletas usa o mesmo `conversor` (dois nomes
para o mesmo arquivo dariam duas classes `AbaBD` e dois `Celula`)."""
import os
import sys

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_motor")
if PASTA not in sys.path:
    sys.path.insert(0, PASTA)

import conversor  # noqa: E402,F401
from conversor.versao import APP_VERSAO  # noqa: E402,F401

if os.path.dirname(os.path.abspath(conversor.__file__)) != os.path.join(PASTA, "conversor"):
    raise ImportError(f"o pacote 'conversor' veio de outro lugar ({conversor.__file__}), não da cópia do Nexus")
