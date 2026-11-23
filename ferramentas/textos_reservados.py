"""Os textos reservados: tirar de um arquivo versionado o que não pode morar no repositório público e pôr no banco do Nexus.

Regra e desenho: `nexus/dados/textos_reservados.py`. A lista de termos fica FORA do repositório (ela É o dado reservado):
um JSON `[{"ficha": "Zlfornecedor01", "texto": "...", "vezes": 3, "onde": ["..."]}, ...]` (para `reservar`) ou
`{"chave": "texto"}` (para `publicar` uma área que não usa ficha em arquivo, como o canal dos fabricantes).

A ordem de sempre, com o `.env` do Nexus (`--env`, padrão o da raiz):

    python -I ferramentas/textos_reservados.py reservar --area zeladoria_radar --arquivo <arquivo> --termos <termos.json>
        ensaio: troca na memória, confere que a volta devolve o arquivo idêntico e diz quantas vezes cada ficha entrou
    python -I ferramentas/textos_reservados.py publicar --area zeladoria_radar --termos <termos.json>
        grava as fichas no banco (cifradas) e lê de volta
    python -I ferramentas/textos_reservados.py reservar ... --gravar
        só grava o arquivo se o BANCO devolver o original idêntico (as fichas lidas de lá, não as do termos.json)
    python -I ferramentas/textos_reservados.py conferir --area zeladoria_radar --arquivo <arquivo>
        lê o banco, restaura o arquivo na memória e diz o sha256 e as fichas sem texto (a prova de antes e depois)
    python -I ferramentas/textos_reservados.py listar --area zeladoria_radar
        as fichas da área e o tamanho de cada texto (o texto mesmo, só com --abrir, no terminal de quem tem a chave)

Nada aqui imprime o texto reservado sem o `--abrir`.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nexus.dados import livros  # noqa: E402
from nexus.dados import textos_reservados as TR  # noqa: E402


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


CRLF, LF = chr(13) + chr(10), chr(10)


def _ler_arquivo(caminho: str) -> str:
    """O arquivo com fim de linha LF, que é como o git guarda e o servidor serve (no Windows o disco tem CRLF): o texto
    reservado de mais de uma linha vai para o banco com LF, e a página restaurada sai idêntica à de antes."""
    with open(caminho, encoding="utf-8", newline="") as f:
        return f.read().replace(CRLF, LF)


def _gravar_arquivo(caminho: str, texto: str) -> None:
    """Grava com o fim de linha que o arquivo tinha no disco."""
    with open(caminho, encoding="utf-8", newline="") as f:
        era_crlf = CRLF in f.read()
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        f.write(texto.replace(LF, CRLF) if era_crlf else texto)


def _banco(args):
    """(base, sessao, token, cofre) pelo .env dito. A sessão é a de sempre; quem grava é só o `publicar`."""
    import requests
    from dotenv import dotenv_values

    from nexus.cadastro.cifra import Cofre
    from nexus.cadastro.ligacoes import BASE_API
    env = {k: v for k, v in dotenv_values(args.env or (RAIZ / ".env")).items() if v}
    if not env.get("NEXUS_CHAVE_CADASTRO"):
        raise SystemExit("sem NEXUS_CHAVE_CADASTRO no .env (use --env <caminho do .env do Nexus>)")
    base = (env.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
    return base, requests.Session(), env.get("GRIDCO_SQL_TOKEN") or "", Cofre(env["NEXUS_CHAVE_CADASTRO"])


def _termos(caminho: str):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def _do_banco(args) -> dict:
    base, sessao, _token, cofre = _banco(args)
    return TR.abrir(livros.ler(base, sessao, TR.LIVRO, TR.ABA), cofre, args.area)


def reservar(args) -> int:
    original = _ler_arquivo(args.arquivo)
    novo, fichas = TR.reservar(original, _termos(args.termos))
    print(f"arquivo: {len(original)} caracteres, sha256 {_sha(original)[:16]}; com as fichas: sha256 {_sha(novo)[:16]}")
    for ficha in sorted(fichas):
        print(f"  {ficha:22} entrou {novo.count(ficha)} vez(es); texto de {len(fichas[ficha])} caracteres")
    print(f"a volta devolve o arquivo idêntico: {TR.restaurar(novo, fichas) == original} ({len(fichas)} fichas)")
    if not args.gravar:
        print("ensaio: nada gravado (publique as fichas e rode de novo com --gravar)")
        return 0
    banco = _do_banco(args)
    if TR.restaurar(novo, banco) != original:
        faltam = [f for f in sorted(fichas) if banco.get(f) != fichas[f]]
        print(f"NÃO GRAVEI: o banco não devolve o original ({len(faltam)} ficha(s) sem o texto igual: {', '.join(faltam[:10])})")
        return 1
    _gravar_arquivo(args.arquivo, novo)
    print(f"gravado: {args.arquivo} (o banco devolve o original idêntico, sha256 {_sha(original)[:16]})")
    return 0


def publicar(args) -> int:
    t = _termos(args.termos)
    textos = {x["ficha"]: x["texto"] for x in t} if isinstance(t, list) else dict(t)
    base, sessao, token, cofre = _banco(args)
    if not token:
        raise SystemExit("sem GRIDCO_SQL_TOKEN no .env: não há como gravar")
    antes = TR.abrir(livros.ler(base, sessao, TR.LIVRO, TR.ABA), cofre, args.area)
    print(f"antes: {len(antes)} ficha(s) da área {args.area} no banco")
    r = TR.publicar(args.area, textos, base=base, sessao=sessao, token=token, cofre=cofre)
    depois = TR.abrir(livros.ler(base, sessao, TR.LIVRO, TR.ABA), cofre, args.area)
    iguais = sum(1 for c, v in textos.items() if depois.get(c) == v)
    print(f"depois: {len(depois)} ficha(s) da área; linhas do livro {r['antes']} -> {r['depois']}; "
          f"novas {len(r['novos'])}, mudadas {len(r['mudados'])}, já iguais {len(r['iguais'])}")
    print(f"leitura de volta: {iguais} de {len(textos)} textos abrem iguais ao que foi mandado")
    perdidas = sorted(set(antes) - set(depois))
    if perdidas or iguais != len(textos):
        print(f"ERRO: {len(perdidas)} ficha(s) que existiam sumiram ou a leitura de volta não bate")
        return 1
    return 0


def conferir(args) -> int:
    banco = _do_banco(args)
    versionado = _ler_arquivo(args.arquivo)
    restaurado = TR.restaurar(versionado, banco)
    faltam = [f for f in TR.fichas_em(versionado) if f not in banco]
    print(f"versionado: sha256 {_sha(versionado)[:16]} ({len(TR.fichas_em(versionado))} fichas diferentes)")
    print(f"restaurado pelo banco: {len(restaurado)} caracteres, sha256 {_sha(restaurado)}")
    print(f"fichas do arquivo sem texto no banco: {len(faltam)}" + (f" ({', '.join(faltam[:10])})" if faltam else ""))
    if args.contra:
        igual = restaurado == _ler_arquivo(args.contra)
        print(f"igual ao arquivo de referência ({args.contra}): {igual}")
        return 0 if igual and not faltam else 1
    return 1 if faltam else 0


def listar(args) -> int:
    banco = _do_banco(args)
    print(f"{len(banco)} ficha(s) na área {args.area}")
    for ficha in sorted(banco):
        print(f"  {ficha:24} {len(banco[ficha])} caracteres" + (f": {banco[ficha]!r}" if args.abrir else ""))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)
    for nome, fn in (("reservar", reservar), ("publicar", publicar), ("conferir", conferir), ("listar", listar)):
        s = sub.add_parser(nome)
        s.add_argument("--area", required=True, choices=TR.AREAS)
        s.add_argument("--env", help="o .env do Nexus (padrão: o da raiz deste repositório)")
        s.set_defaults(fn=fn)
        if nome in ("reservar", "conferir"):
            s.add_argument("--arquivo", required=True)
        if nome in ("reservar", "publicar"):
            s.add_argument("--termos", required=True, help="o JSON dos termos, FORA do repositório")
        if nome == "reservar":
            s.add_argument("--gravar", action="store_true")
        if nome == "conferir":
            s.add_argument("--contra", help="um arquivo de referência (o original de antes) para comparar o restaurado")
        if nome == "listar":
            s.add_argument("--abrir", action="store_true", help="mostra o texto (só no terminal de quem tem a chave)")
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except TR.Recusada as e:
        print(f"RECUSADO: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
