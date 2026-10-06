"""Leva o OS Creator Web do Nexus (a referência) para o oem, o do supervisório (Levi, 06/10/2026). As regras estão em
`nexus/torres/oscreator/sincronia.py`.

    python ferramentas/sincronizar_oscreator.py              mostra o que mudou (não copia nada)
    python ferramentas/sincronizar_oscreator.py --aplicar    leva o que mudou só no Nexus para o oem e grava a sincronia
    python ferramentas/sincronizar_oscreator.py --trazer     traz o que mudou só no oem para o Nexus
    --oem <pasta>                                            outro oem (padrão C:\\GridcoBuild\\oem ou a variável OEM_DIR)

Copiar não reinicia o 5090 nem faz commit no oem (o oem é público: commit lá é decisão do Levi). Depois de --aplicar ou
--trazer, faça o commit do `nexus/torres/oscreator/sincronia.json` (e da cópia, no --trazer) no Nexus. O que o lado de
destino tinha antes fica em <pasta de dados do Nexus>/oscreator_backup/<data e hora>/.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus.cadastro.ligacoes import DADOS_PADRAO  # noqa: E402
from nexus.torres.oscreator import sincronia as S  # noqa: E402


def main():
    args = sys.argv[1:]
    oem = Path(args[args.index("--oem") + 1]) if "--oem" in args else S.OEM_PADRAO
    if not (oem / "os_creator").is_dir():
        sys.exit(f"não achei o oem em {oem} (use --oem <pasta>)")
    lista, base = S.arquivos(), S.ler_manifesto()
    st = S.estado(S.AQUI, oem, lista, base)
    print(f"oem: {oem}  |  {len(lista)} arquivos da cópia no git do Nexus")
    for chave, rotulo in (("levar", "mudou no Nexus, vai para o oem"), ("trazer", "mudou só no oem (não é atropelado)"),
                          ("conflito", "mudou nos dois: resolver à mão"), ("apagados", "apagado no Nexus (não apago no oem)")):
        if st[chave]:
            print(f"\n{rotulo}: {len(st[chave])}")
            for rel in st[chave][:40]:
                print("  ", rel)
    print(f"\niguais: {len(st['igual'])}")
    if "--aplicar" in args or "--trazer" in args:
        backup = DADOS_PADRAO / "oscreator_backup" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
        fazer = S.aplicar if "--aplicar" in args else S.trazer
        feitos, nova = fazer(S.AQUI, oem, lista, base, backup)
        S.gravar_manifesto(nova)
        destino = "oem" if fazer is S.aplicar else "Nexus"
        print(f"\ncopiados para o {destino}: {len(feitos)}" + (f"  (antes: {backup})" if feitos else ""))
        print("sincronia gravada em nexus/torres/oscreator/sincronia.json: faça o commit no Nexus")


if __name__ == "__main__":
    main()
