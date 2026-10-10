"""Confere, ANTES do restart, que o Python do serviço sobe o Nexus (auditoria A6 da porta única, 10/10/2026).

O `atualizar.sh` reinicia o serviço depois do `git pull`. Se uma dependência nova não estiver instalada, o Nexus novo
não sobe e o `Restart=always` do systemd o deixa caindo em laço: com o Nexus na raiz de app.gridco.com.br, a entrada da
empresa vira 502. O caso que criou isto: o `reportlab` entrou no requirements.txt em 09/10 e é importado no boot (o
relatório dos extintores, `nexus/hseq/relatorio.py`); um pip que falhasse deixava o Nexus fora no restart seguinte.

Aqui se importa o que o boot importa: as dependências do requirements.txt e o próprio Nexus como o `servir.py` o monta
(o `create_app` com todas as torres), com uma configuração de mentira. Não lê o `.env`, não vai à rede, não grava nada e
não liga timer nenhum (as leituras do Fracttal ao subir são do `instalar` do Campo, que aqui só é importado). Falhou, o
script para antes do restart e o Nexus de antes segue no ar.

Uso (o atualizar.sh chama assim, com o Python do .venv):  .venv/bin/python -B deploy/conferir_boot.py
"""
import importlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# As do requirements.txt que o Nexus importa. O PyQt6 fica de fora de propósito: sem ele só a tela de Engenharia do OS
# Creator embutido avisa, e o Nexus sobe (requirements.txt). O pytest é da suíte, não do serviço.
DEPENDENCIAS = ("flask", "dotenv", "waitress", "openpyxl", "cryptography", "requests", "pandas", "PIL", "reportlab")


def main() -> int:
    sys.path.insert(0, str(RAIZ))
    faltam = []
    for nome in DEPENDENCIAS:
        try:
            importlib.import_module(nome)
        except Exception as e:                   # noqa: BLE001 — ImportError, ou o que um pacote quebrado levantar
            faltam.append(f"{nome} ({type(e).__name__}: {e})")
    if faltam:
        print("ERRO: o Python do serviço não importa: " + "; ".join(faltam), file=sys.stderr)
        return 1
    try:
        from nexus import create_app
        # o que o servir.py importa além do create_app
        from nexus.campo import instalar as _campo                # noqa: F401
        from nexus.dados import instalar as _dados                # noqa: F401
        from nexus.engenharia import instalar as _engenharia      # noqa: F401
        app = create_app({"NEXUS_SECRET_KEY": "conferencia-do-deploy", "NEXUS_SENHA_ADMIN": "conferencia-do-deploy"})
    except Exception as e:                       # noqa: BLE001 — qualquer erro no boot para o deploy antes do restart
        print(f"ERRO: o Nexus não monta: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"Boot conferido: {len(DEPENDENCIAS)} dependências, {len(app.extensions['nexus_torres'])} torres e "
          f"{len(list(app.url_map.iter_rules()))} rotas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
