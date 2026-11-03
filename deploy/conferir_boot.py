"""Confere, ANTES do restart, que o Python do serviço sobe o Nexus (auditoria A6 da porta única, 10/10/2026).

Se uma dependência nova não estiver instalada, o Nexus novo não sobe e o `Restart=always` do systemd o deixa caindo em
laço: com o Nexus na raiz de app.gridco.com.br, a entrada da empresa vira 502. O caso que criou isto: o `reportlab`
entrou no requirements.txt em 09/10 e é importado no boot (o relatório dos extintores, `nexus/hseq/relatorio.py`); um
pip que falhasse deixava o Nexus fora no restart seguinte.

Aqui se importa o que o boot importa: as dependências do requirements.txt e o próprio Nexus como o `servir.py` o monta
(o `create_app` com todas as torres), com uma configuração de mentira. Não lê o `.env`, não vai à rede, não grava nada e
não liga timer nenhum (as leituras do Fracttal ao subir são do `instalar` do Campo, que aqui só é importado).

O Nexus importado é o da pasta em que ESTE arquivo está (ele a põe na frente do sys.path). O `atualizar.sh` o roda a
partir do commit novo extraído numa pasta temporária, fora da pasta do serviço (revisão adversarial de 10/10/2026: o
`git pull` vinha antes da conferência, e a pasta do serviço ficava no código que não sobe). Falhou, o script para, a
pasta do serviço não anda e o Nexus de antes segue no ar.

Uso (o atualizar.sh chama assim, com o Python do .venv):  .venv/bin/python -B <pasta do commit>/deploy/conferir_boot.py
À mão, para conferir a pasta do serviço:                   .venv/bin/python -B deploy/conferir_boot.py
"""
import importlib
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# As do requirements.txt que o Nexus importa (o PyQt6 saiu dele em 31/10/2026: nada o importa). O pytest é da suíte, não do
# serviço.
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
    # o clone do OS Creator, ao ser importado, cria a pasta de dados dele (`api._data_dir`, em APPDATA ou no HOME): aqui ela é uma
    # pasta temporária, e a conferência não grava nada fora dela
    pasta = tempfile.TemporaryDirectory(prefix="conferir-boot-")
    os.environ["APPDATA"] = os.environ["XDG_DATA_HOME"] = pasta.name
    try:
        from nexus import create_app
        # o que o servir.py importa além do create_app
        from nexus.campo import instalar as _campo                # noqa: F401
        from nexus.dados import instalar as _dados                # noqa: F401
        from nexus.engenharia import instalar as _engenharia      # noqa: F401
        # e o que o servir.py liga ao subir: o contador do Fracttal e o uso do OS Creator, e os três leitores do clone (por eles o
        # `ativos_central`, a `os_central`, o `catalogos`, o `api`...). Antes o clone só carregava no 1º pedido ao /os/; agora o
        # `servir.py` o importa na subida, e um clone quebrado que o portão não pegasse deixaria o serviço caindo em laço. Só
        # importa, sem ligar: nenhum laço abre aqui (31/10/2026, revisão final)
        from nexus.casca import fracttal_conta, uso_os            # noqa: F401
        from nexus.torres.oscreator import ponte
        for nome_do_leitor in ponte.LEITORES_DO_CLONE:
            ponte.modulo_do_clone(nome_do_leitor)
        app = create_app({"NEXUS_SECRET_KEY": "conferencia-do-deploy", "NEXUS_SENHA_ADMIN": "conferencia-do-deploy"})
    except Exception as e:                       # noqa: BLE001 — qualquer erro no boot para o deploy antes do restart
        print(f"ERRO: o Nexus não monta: {type(e).__name__}: {e}", file=sys.stderr)
        pasta.cleanup()
        return 1
    print(f"Boot conferido: {len(DEPENDENCIAS)} dependências, {len(app.extensions['nexus_torres'])} torres, "
          f"{len(list(app.url_map.iter_rules()))} rotas e os {len(ponte.LEITORES_DO_CLONE)} leitores do OS Creator importados.")
    pasta.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
