"""O OS Creator Web: o Nexus é a referência e o oem acompanha (Levi, 06/10/2026: "sincronize a ferramenta usando o do
nexus como referência").

A cópia mora em `nexus/torres/oscreator/{os_creator,chamado_garantia}` com o mesmo caminho relativo do oem
(`oem/<x>` -> `nexus/torres/oscreator/<x>`). Mudança no OS Creator: faz aqui, prova aqui, e
`ferramentas/sincronizar_oscreator.py` leva para o oem (o 5090 do supervisório). O que é só do Nexus (o portão, o topo,
a moldura, o menu lateral) fica na `ponte.py`, nunca na cópia: por isso a cópia não pode importar nada do `nexus`, ou
o supervisório quebraria ao receber.

Três lados por arquivo, pelo `sincronia.json` (o hash de cada arquivo na última sincronia):
- igual nos dois: nada;
- mudou só no Nexus, ou é novo no Nexus: vai para o oem (o caminho normal);
- mudou só no oem (alguém mexeu no supervisório): NÃO é atropelado; a lista mostra, e `--trazer` traz para o Nexus;
- mudou nos dois: conflito, nada é copiado; resolver à mão.
Arquivo apagado no Nexus não é apagado no oem (lá também mora o app de desktop): a lista mostra.

Só vão os arquivos da cópia que estão no git do Nexus: o que é local da máquina fica fora, a começar pelo
`os_creator/.env`, que tem a credencial do Fracttal (06/10: 120 no git, 121 na pasta).
"""
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ_REPO = AQUI.parents[2]
PASTAS = ("os_creator", "chamado_garantia")
MANIFESTO = AQUI / "sincronia.json"
OEM_PADRAO = Path(os.environ.get("OEM_DIR") or r"C:\GridcoBuild\oem")
FORA = (".env",)            # nunca vai, nem que entre no git por engano: é a credencial de cada máquina
ESTADOS = ("igual", "levar", "trazer", "conflito")


def _hash(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.is_file() else None


def arquivos() -> list[str]:
    """Os arquivos da cópia que estão no git do Nexus, relativos a esta pasta."""
    pre = "nexus/torres/oscreator/"
    r = subprocess.run(["git", "ls-files", "--", *[pre + p for p in PASTAS]], cwd=RAIZ_REPO, capture_output=True,
                       text=True, encoding="utf-8", check=True)
    return sorted(l[len(pre):] for l in r.stdout.splitlines() if l.startswith(pre) and Path(l).name not in FORA)


def ler_manifesto(caminho: Path = MANIFESTO) -> dict:
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8")).get("arquivos") or {}
    except (OSError, ValueError):
        return {}


def gravar_manifesto(hashes: dict, caminho: Path = MANIFESTO):
    corpo = {"como_ler": "hash de cada arquivo da cópia na última sincronia com o oem (sincronia.py)",
             "atualizado_em": datetime.now().isoformat(timespec="seconds"), "arquivos": dict(sorted(hashes.items()))}
    Path(caminho).write_text(json.dumps(corpo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def estado(nexus_dir, oem_dir, lista: list[str], base: dict) -> dict:
    """{igual, levar, trazer, conflito, apagados}. Sem a sincronia anterior de um arquivo (base vazia) e com os dois
    lados diferentes, é conflito: na dúvida, ninguém atropela ninguém."""
    out = {e: [] for e in ESTADOS}
    for rel in lista:
        n, o, b = _hash(Path(nexus_dir) / rel), _hash(Path(oem_dir) / rel), base.get(rel)
        if n == o:
            out["igual"].append(rel)
        elif o is None or o == b:
            out["levar"].append(rel)
        elif n == b:
            out["trazer"].append(rel)
        else:
            out["conflito"].append(rel)
    out["apagados"] = sorted(set(base) - set(lista))
    return out


def importa_o_nexus(nexus_dir, lista: list[str]) -> list[str]:
    """Arquivo da cópia que importa o pacote `nexus`: no supervisório isso não existe."""
    ruins = []
    for rel in lista:
        if rel.endswith(".py"):
            t = (Path(nexus_dir) / rel).read_text(encoding="utf-8", errors="replace")
            if any(l.lstrip().startswith(("from nexus", "import nexus")) for l in t.splitlines()):
                ruins.append(rel)
    return ruins


def _copiar(rels, de, para, backup: Path) -> list[str]:
    feitos = []
    for rel in rels:
        alvo = Path(para) / rel
        if alvo.is_file():
            guarda = backup / rel
            guarda.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(alvo, guarda)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(de) / rel, alvo)
        feitos.append(rel)
    return feitos


def _base_nova(nexus_dir, lista, base, sincronizados) -> dict:
    nova = {rel: h for rel, h in base.items() if rel in lista}
    for rel in sincronizados:
        nova[rel] = _hash(Path(nexus_dir) / rel)
    return nova


def aplicar(nexus_dir, oem_dir, lista, base, backup: Path) -> tuple[list[str], dict]:
    """Leva para o oem o que mudou só no Nexus. Devolve (copiados, a base nova). O que o oem tinha antes vai para
    `backup`. Conflito e "mudou só no oem" ficam como estão."""
    ruins = importa_o_nexus(nexus_dir, lista)
    if ruins:
        raise RuntimeError("a cópia importa o pacote nexus (o supervisório quebraria): " + ", ".join(ruins))
    st = estado(nexus_dir, oem_dir, lista, base)
    feitos = _copiar(st["levar"], nexus_dir, oem_dir, backup)
    return feitos, _base_nova(nexus_dir, lista, base, st["igual"] + feitos)


def trazer(nexus_dir, oem_dir, lista, base, backup: Path) -> tuple[list[str], dict]:
    """Traz para o Nexus o que mudou só no oem (a versão do Nexus vai para `backup`)."""
    st = estado(nexus_dir, oem_dir, lista, base)
    feitos = _copiar(st["trazer"], oem_dir, nexus_dir, backup)
    return feitos, _base_nova(nexus_dir, lista, base, st["igual"] + feitos)
