"""A foto do código do Nexus, para desembaraçar sem mudar o comportamento (skill untangle-codebase, 07/11/2026).

    python .claude/skills/untangle-codebase/foto.py tirar  <saida.json>
    python .claude/skills/untangle-codebase/foto.py comparar <antes.json> <depois.json>
    python .claude/skills/untangle-codebase/foto.py mapa <foto.json>
    python .claude/skills/untangle-codebase/foto.py quem <arquivo> [<arquivo> ...]

`tirar` guarda três coisas da pasta onde roda (a raiz do repositório): as rotas do app (regra, endpoint, métodos), os
nomes do alto de cada módulo de `nexus/` (e se cada um nasce ali ou é importado de outro) e quem lê cada nome de fora
(`from M import x`, `M.x` e `monkeypatch.setattr(M, "x")`, em `nexus/`, `tests/`, `ferramentas/` e `app.py`).

`comparar` diz o que a mudança quebrou e a suíte pode não pegar:
- ROTA: rota que sumiu ou mudou de endpoint ou de método (o App de Campo e a Performance chamam rotas que nenhum teste chama);
- QUEBRA: alguém lê um nome que não existe mais no módulo (o import dentro de função só quebra quando a função roda; o
  `ruff --fix` de import "sem uso" apaga o que outro módulo lê através daquele arquivo);
- PATCH: um teste troca `M.x`, mas `x` passou a ser importado em M de outro módulo: quem chama `x` de lá não vê a troca,
  e o teste passa a testar outra coisa (ou ir ao banco) sem falhar;
- SAIU: nome que nascia num módulo e não nasce em mais nenhum (é apagar, e apagar precisa do OK do Levi).
Sai com código 1 quando há ROTA, QUEBRA ou PATCH.

`mapa` é a primeira entrega de uma faxina, sem mudar nada: os gigantes, a seta invertida (área lendo torre), as áreas
que se importam nos dois sentidos, as funções de corpo idêntico (unificar), as que ninguém lê no Python (candidatas a
apagar, ainda sem o grep de templates, JS e deploy) e os módulos mais trocados por monkeypatch (risco de PATCH ao mover).

`quem` diz se outra sessão está mexendo nos arquivos (worktree com mudança solta ou commit que não subiu) e quantos
commits a main teve neles nos últimos 7 dias.
"""
import ast
import collections
import hashlib
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path.cwd()
PASTAS_QUE_LEEM = ("nexus", "tests", "ferramentas")


def _nome_do_modulo(arquivo: Path) -> str:
    partes = list(arquivo.relative_to(RAIZ).with_suffix("").parts)
    if partes[-1] == "__init__":
        partes = partes[:-1]
    return ".".join(partes)


def _arvore(arquivo: Path):
    try:
        return ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    except (SyntaxError, UnicodeDecodeError) as erro:
        print(f"aviso: não li {arquivo}: {erro}", file=sys.stderr)
        return None


def _absoluto(modulo_do_arquivo: str, eh_pacote: bool, no: ast.ImportFrom) -> str:
    if not no.level:
        return no.module or ""
    base = modulo_do_arquivo.split(".")
    if not eh_pacote:
        base = base[:-1]
    base = base[: len(base) - (no.level - 1)]
    return ".".join(base + ([no.module] if no.module else []))


def _modulos() -> dict:
    """{modulo: arquivo} de tudo o que é Python em nexus/."""
    return {_nome_do_modulo(a): a for a in sorted((RAIZ / "nexus").rglob("*.py"))}


def _nomes_do_alto(modulo: str, arquivo: Path, arvore) -> dict:
    """{nome: origem}: 'nasce' (def, class, atribuição) ou 'import:<modulo de onde vem>'."""
    nomes = {}

    def ver(corpo):
        for no in corpo:
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nomes[no.name] = "nasce"
            elif isinstance(no, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
                for alvo in alvos:
                    for n in ast.walk(alvo):
                        if isinstance(n, ast.Name):
                            nomes.setdefault(n.id, "nasce")
            elif isinstance(no, ast.Import):
                for a in no.names:
                    nomes[a.asname or a.name.split(".")[0]] = "import:" + a.name
            elif isinstance(no, ast.ImportFrom):
                origem = _absoluto(modulo, arquivo.name == "__init__.py", no)
                for a in no.names:
                    if a.name != "*":
                        nomes[a.asname or a.name] = f"import:{origem}.{a.name}"
            elif isinstance(no, (ast.If, ast.Try, ast.With)):
                ver(no.body)
                for h in getattr(no, "handlers", []):
                    ver(h.body)
                ver(getattr(no, "orelse", []))
                ver(getattr(no, "finalbody", []))

    ver(arvore.body)
    return nomes


def _consumo(arquivo: Path, arvore, modulos: dict) -> list:
    """[modulo, nome, como, onde] de cada leitura de um nome de módulo do nexus, neste arquivo."""
    rel = arquivo.relative_to(RAIZ).as_posix()
    modulo = _nome_do_modulo(arquivo)
    eh_pacote = arquivo.name == "__init__.py"
    apelidos, achados = {}, []
    for no in ast.walk(arvore):                                    # primeiro os apelidos de módulo do arquivo inteiro
        if isinstance(no, ast.Import):
            for a in no.names:
                if a.name in modulos and a.asname:
                    apelidos[a.asname] = a.name
        elif isinstance(no, ast.ImportFrom):
            origem = _absoluto(modulo, eh_pacote, no)
            for a in no.names:
                completo = f"{origem}.{a.name}"
                if completo in modulos:
                    apelidos[a.asname or a.name] = completo
                elif origem in modulos and a.name != "*":
                    achados.append([origem, a.name, "from", f"{rel}:{no.lineno}"])
    for no in ast.walk(arvore):
        if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name) and no.value.id in apelidos:
            achados.append([apelidos[no.value.id], no.attr, "attr", f"{rel}:{no.lineno}"])
        elif (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "setattr"
              and no.args):
            alvo = no.args[0]
            if (isinstance(alvo, ast.Name) and alvo.id in apelidos and len(no.args) > 1
                    and isinstance(no.args[1], ast.Constant) and isinstance(no.args[1].value, str)):
                achados.append([apelidos[alvo.id], no.args[1].value, "patch", f"{rel}:{no.lineno}"])
            elif isinstance(alvo, ast.Constant) and isinstance(alvo.value, str) and alvo.value.startswith("nexus."):
                mod, _, nome = alvo.value.rpartition(".")
                if mod in modulos:
                    achados.append([mod, nome, "patch", f"{rel}:{no.lineno}"])
    return achados


def _corpos_e_funcoes(arvore) -> tuple:
    """{nome: impressão do corpo} das funções do alto com 2+ comandos (sem a docstring), e as funções e classes do alto
    sem decorador (as com decorador, como as rotas, são chamadas pelo Flask)."""
    corpos, funcoes = {}, []
    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not no.decorator_list:
            funcoes.append(no.name)
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            corpo = no.body
            if corpo and isinstance(corpo[0], ast.Expr) and isinstance(getattr(corpo[0], "value", None), ast.Constant):
                corpo = corpo[1:]
            if len(corpo) >= 2:
                texto = ast.dump(no.args) + "".join(ast.dump(c) for c in corpo)
                corpos[no.name] = hashlib.md5(texto.encode()).hexdigest()[:12]
    return corpos, funcoes


def _rotas() -> list:
    sys.path.insert(0, str(RAIZ))
    from nexus import create_app                                    # sem .env: a config de teste, como o conftest
    app = create_app({"NEXUS_SECRET_KEY": "foto", "NEXUS_SENHA_ADMIN": "foto", "TESTING": True})
    return sorted([r.rule, r.endpoint, ",".join(sorted(r.methods - {"HEAD", "OPTIONS"}))]
                  for r in app.url_map.iter_rules())


def tirar(saida: str) -> None:
    modulos = _modulos()
    nomes, usa, consumo, corpos, funcoes, linhas = {}, {}, [], {}, {}, {}
    for mod, arquivo in modulos.items():
        arvore = _arvore(arquivo)
        if arvore is not None:
            nomes[mod] = _nomes_do_alto(mod, arquivo, arvore)
            corpos[mod], funcoes[mod] = _corpos_e_funcoes(arvore)
            linhas[mod] = arquivo.read_text(encoding="utf-8").count("\n")
            usa[mod] = sorted({n.id for n in ast.walk(arvore) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)})
    leitores = [RAIZ / "app.py"] + [a for p in PASTAS_QUE_LEEM for a in sorted((RAIZ / p).rglob("*.py"))]
    for arquivo in leitores:
        if arquivo.exists() and ".claude" not in arquivo.parts:
            arvore = _arvore(arquivo)
            if arvore is not None:
                consumo += _consumo(arquivo, arvore, modulos)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    sujo = bool(subprocess.run(["git", "status", "--porcelain", "--", "nexus", "tests", "app.py"],
                               capture_output=True, text=True).stdout.strip())
    foto = {"commit": commit + ("+mudanca" if sujo else ""), "rotas": _rotas(), "nomes": nomes, "usa": usa, "consumo": consumo,
            "corpos": corpos, "funcoes": funcoes, "linhas": linhas}
    Path(saida).write_text(json.dumps(foto, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"foto de {foto['commit']}: {len(foto['rotas'])} rotas, {len(nomes)} módulos, {len(consumo)} leituras -> {saida}")


def comparar(antes_json: str, depois_json: str) -> int:
    antes = json.loads(Path(antes_json).read_text(encoding="utf-8"))
    depois = json.loads(Path(depois_json).read_text(encoding="utf-8"))
    graves, avisos = [], []

    ra, rd = {r[0]: r for r in antes["rotas"]}, {r[0]: r for r in depois["rotas"]}
    for regra in sorted(ra.keys() - rd.keys()):
        graves.append(f"ROTA que sumiu: {regra} ({ra[regra][1]})")
    for regra in sorted(ra.keys() & rd.keys()):
        if ra[regra] != rd[regra]:
            graves.append(f"ROTA que mudou: {regra}: {ra[regra][1:]} -> {rd[regra][1:]}")
    for regra in sorted(rd.keys() - ra.keys()):
        avisos.append(f"rota nova: {regra} ({rd[regra][1]})")

    na, nd = antes["nomes"], depois["nomes"]
    usa = depois.get("usa", {})

    def leitores(foto):
        """{(modulo, nome): módulos do nexus que leem modulo.nome}, para achar quem deixou de ler pelo módulo antigo."""
        r = collections.defaultdict(set)
        for m, n, como, onde in foto["consumo"]:
            if como != "patch" and onde.startswith("nexus/"):
                r[(m, n)].add(_modulo_de(onde))
        return r
    leu_antes, le_agora = leitores(antes), leitores(depois)
    vistos = set()
    for mod, nome, como, onde in depois["consumo"]:
        chave = (mod, nome, como, onde)
        if chave in vistos:
            continue
        vistos.add(chave)
        existe_antes = nome in na.get(mod, {}) or f"{mod}.{nome}" in na
        existe_agora = nome in nd.get(mod, {}) or f"{mod}.{nome}" in nd
        if not existe_agora and existe_antes:
            graves.append(f"QUEBRA: {onde} lê {mod}.{nome} ({como}), que não existe mais")
        elif como == "patch" and existe_agora and existe_antes:
            o_antes, o_agora = na[mod].get(nome, ""), nd[mod].get(nome, "")
            if o_antes == "nasce" and o_agora.startswith("import:"):
                # a troca em M só vale para quem lê o nome pelo M. Quem chama de dentro da casa nova (ou de quem importa
                # de lá) segue com a função de verdade: o teste passa sem testar o que diz
                casa, _, real = o_agora[7:].rpartition(".")      # o nome na casa nova pode ser outro (_sessao -> sessao)
                fora = {m for m in nd if m != mod and (
                    (m == casa and real in usa.get(m, ()))
                    or any(o == f"import:{casa}.{real}" and x in usa.get(m, ()) for x, o in nd[m].items()))}
                fora |= {m for m in le_agora.get((casa, real), ()) if m != mod}
                fora = sorted(fora)
                if fora:
                    graves.append(f"PATCH que não pega mais: {onde} troca {mod}.{nome}, mas {nome} agora mora em "
                                  f"{casa} e é chamado de {', '.join(fora[:3])}, que não vê a troca")
                else:
                    avisos.append(f"patch segue pegando: {onde} troca {mod}.{nome} (veio de {casa}; os chamadores "
                                  f"ficaram em {mod})")
        if como == "patch" and existe_agora:
            # quem lia M.x e passou a ler de outro lugar escapa da troca do teste em M.x
            saiu = sorted(leu_antes.get((mod, nome), set()) - le_agora.get((mod, nome), set()) - {mod})
            saiu = [m for m in saiu if m in nd]
            if saiu:
                graves.append(f"PATCH que não pega mais: {onde} troca {mod}.{nome}, mas {', '.join(saiu[:3])} "
                              f"deixou de ler por {mod}")

    # onde o nome passou a nascer: só conta módulo em que ele não nascia antes (homônimo antigo é outra função)
    nasceu_agora = {}
    for m, ns in nd.items():
        for n, o in ns.items():
            if o == "nasce" and na.get(m, {}).get(n) != "nasce":
                nasceu_agora.setdefault(n, []).append(m)
    for mod, ns in sorted(na.items()):
        for nome, origem in sorted(ns.items()):
            if origem != "nasce" or nd.get(mod, {}).get(nome) == "nasce":
                continue
            if nome in nasceu_agora:
                avisos.append(f"mudou de casa: {mod}.{nome} -> {', '.join(sorted(nasceu_agora[nome])[:3])}")
            else:
                avisos.append(f"SAIU: {mod}.{nome} não nasce em módulo nenhum (apagar precisa do OK do Levi)")
    for mod in sorted(na.keys() - nd.keys()):
        avisos.append(f"módulo que sumiu: {mod}")

    print(f"antes {antes['commit']}  depois {depois['commit']}")
    for linha in graves:
        print("  " + linha)
    for linha in avisos:
        print("  " + linha)
    print(f"{len(graves)} grave(s), {len(avisos)} aviso(s)" + ("" if graves else ": nada quebrou pela foto"))
    return 1 if graves else 0


def _area(mod: str) -> str:
    partes = mod.split(".")
    if len(partes) >= 3 and partes[1] == "torres":
        return "torres." + partes[2]
    return partes[1] if len(partes) > 1 else mod


def _modulo_de(onde: str) -> str:
    caminho = onde.rsplit(":", 1)[0].removesuffix(".py").removesuffix("/__init__")
    return caminho.replace("/", ".")


def mapa(foto_json: str) -> None:
    foto = json.loads(Path(foto_json).read_text(encoding="utf-8"))
    nomes, usa, linhas = foto["nomes"], foto["usa"], foto["linhas"]
    print(f"mapa de {foto['commit']} (nada mudou; é a lista para o Levi escolher)")

    print("\n== Gigantes (linhas)")
    for mod, n in sorted(linhas.items(), key=lambda x: -x[1])[:12]:
        print(f"  {n:5}  {mod}  [{_area(mod)}]")

    # torre é a pasta de nexus/torres/ que declara TORRE (moldura e modelo são a estrutura de todas, não telas)
    torres = {m for m, ns in nomes.items() if m.count(".") == 2 and m.startswith("nexus.torres.") and "TORRE" in ns}
    setas, invertidas = collections.Counter(), collections.defaultdict(set)
    for mod, nome, como, onde in foto["consumo"]:
        if not onde.startswith("nexus/") or como == "patch":
            continue
        leitor = _modulo_de(onde)
        de, para = _area(leitor), _area(mod)
        if de != para:
            setas[(de, para)] += 1
            if ".".join(mod.split(".")[:3]) in torres and not leitor.startswith("nexus.torres"):
                invertidas[(leitor, mod)].add(onde.rsplit(":", 1)[1])
    print("\n== Seta invertida: área lendo torre (a peça desce da torre para a área)")
    for (leitor, mod), ls in sorted(invertidas.items()):
        print(f"  {leitor} -> {mod}  (linhas {', '.join(sorted(ls, key=int)[:5])})")
    print("\n== Áreas que se leem nos dois sentidos (leituras de lá / de cá)")
    for (a, b), n in sorted(setas.items(), key=lambda x: -x[1]):
        if a < b and setas.get((b, a)):
            print(f"  {a} <-> {b}  {n} / {setas[(b, a)]}")

    grupos = collections.defaultdict(list)
    for mod, cs in foto["corpos"].items():
        for nome, h in cs.items():
            grupos[h].append(f"{mod}.{nome}")
    iguais = sorted((g for g in grupos.values() if len(g) > 1), key=lambda g: -len(g))
    print(f"\n== Corpo idêntico (unificar): {len(iguais)} grupos")
    for g in iguais[:15]:
        print(f"  {len(g)}x  " + ", ".join(g[:4]) + (" ..." if len(g) > 4 else ""))

    lidos = {(m, n) for m, n, _, _ in foto["consumo"]}
    soltos = []
    for mod, ns in sorted(nomes.items()):
        for nome, origem in ns.items():
            if (origem == "nasce" and not nome.startswith("__") and nome in foto["funcoes"].get(mod, [])
                    and nome not in usa.get(mod, []) and (mod, nome) not in lidos
                    and not any(nome in usa.get(m, []) and nomes[m].get(nome, "").startswith(f"import:{mod}.")
                                for m in nomes)):
                soltos.append(f"{mod}.{nome}")
    print(f"\n== Função ou classe que ninguém chama no Python (candidatas a apagar: {len(soltos)}; antes, grep em "
          "templates, JS, deploy, ferramentas e .github, e o OK do Levi)")
    for s in soltos[:40]:
        print("  " + s)

    trocas = collections.Counter(m for m, _, como, _ in foto["consumo"] if como == "patch")
    print("\n== Mais trocados por monkeypatch (mover daqui pede a foto com atenção ao PATCH)")
    for mod, n in trocas.most_common(12):
        print(f"  {n:4}  {mod}")


def quem(arquivos: list) -> None:
    """Quem mais mexe nestes arquivos: as worktrees com mudança solta ou commit que ainda não está no origin/main, e os
    commits da main dos últimos 7 dias. Arquivo com trabalho aberto fica para depois (partir em cima dele é conflito)."""
    def git(*args, pasta=None):
        r = subprocess.run(["git", *(["-C", pasta] if pasta else []), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.stdout.strip()
    pastas = [l[9:] for l in git("worktree", "list", "--porcelain").splitlines() if l.startswith("worktree ")]
    aberto = False
    for pasta in pastas:
        solto = git("status", "--porcelain", "--", *arquivos, pasta=pasta)
        sem_subir = git("log", "--oneline", "--no-merges", "origin/main..HEAD", "--", *arquivos, pasta=pasta)
        if solto or sem_subir:
            aberto = True
            print(f"TRABALHO ABERTO em {pasta}")
            for linha in (solto + "\n" + sem_subir).strip().splitlines():
                print("    " + linha[:110])
    recentes = git("log", "origin/main", "--since=7 days", "--format=%h %ad %s", "--date=short", "--", *arquivos)
    n = len(recentes.splitlines()) if recentes else 0
    print(f"main, últimos 7 dias: {n} commit(s)")
    for linha in recentes.splitlines()[:5]:
        print("    " + linha[:110])
    print("fica para depois (ou combine com o Levi)" if aberto else
          "sem trabalho aberto" + (", mas mexido nesta semana: rebase logo antes do push" if n else ""))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 3 and sys.argv[1] == "quem":
        quem(sys.argv[2:])
        sys.exit(0)
    if len(sys.argv) == 3 and sys.argv[1] == "tirar":
        tirar(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "mapa":
        mapa(sys.argv[2])
    elif len(sys.argv) == 4 and sys.argv[1] == "comparar":
        sys.exit(comparar(sys.argv[2], sys.argv[3]))
    else:
        print(__doc__)
        sys.exit(2)
