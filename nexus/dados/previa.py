"""A tabela de um fato, só para ler, ao lado do detalhe no organograma da governança.

Levi, 09/10/2026: "Ao clicar no card de uma tabela tem que ter um botão ao lado esquerdo do 'X' em formato de tabela,
que quando clico preenche o lado esquerdo ao lado da visão lateral com a tabela referida. Ficará somente para leitura,
mas é importante para os stakeholders entenderem o funcionamento e quais dados estão sendo salvos."

O que a prévia pode ler sai do catálogo e de mais nada: as fontes do fato (`fontes`, senão o `livro`) e o livro do Nexus
(`conformado_em`). Nenhum parâmetro da URL vira nome de livro: a rota recebe o fato e o número da tabela na lista dele.
A aba de usina (as fontes "1 aba por usina" do BD_Thopen e do BD_Performance) é a aba visível que o catálogo não
declara como outra coisa (`catalogo.CONHECIDAS`) e só mostra linhas se o cabeçalho for de geração (a regra de
`geracao.abas_de_geracao`): a prévia não vira uma porta para a aba "Clientes" do BD_Thopen nem para o `cadastro_nexus`.
A exceção é a tabela NOVA do radar (`radar.py`, 09/10/2026): ela abre pelo nome, mas só para administrador e só se o
radar, relido na hora, ainda a classificar como nova.

Lê só a página pedida (`/api/sheets/{id}/rows?limit=&offset=`), nunca a aba inteira: a `plataforma_series ·
trk_eventos` passa de 119 mil linhas. Abre no fim da tabela, na ordem dela: nos livros que só acrescentam (os do App, os
da geração) o fim é o mais novo, mas nem todo livro é assim (o `fato_programacao` termina na W38, gravada depois das
W21 a W37), então a tela diz "o fim da tabela", nunca "as mais novas". E-mail vira "[e-mail]" em qualquer célula: a
tela não precisa mostrar o e-mail de ninguém.
"""
import re
import time
from datetime import datetime

from flask import current_app, render_template, session

from . import carga, catalogo, geracao

LIMITE = 50                 # linhas por página
CELULA_MAX = 120            # texto maior que isto aparece cortado (o inteiro fica no title)
TTL_ABAS_S = 300
TTL_PAGINA_S = 120
POR_USINA = "1 aba por usina"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

_ABAS = {"t": 0.0, "v": None}
_LIVROS_EM = {"t": 0.0, "v": None}
_PAGINAS: dict = {}


def limpar_cache():
    _ABAS.update(t=0.0, v=None)
    _LIVROS_EM.update(t=0.0, v=None)
    _PAGINAS.clear()


def _par(texto: str) -> tuple[str, list[str]]:
    """'livro · aba1, aba2' -> ('livro', ['aba1', 'aba2'])."""
    livro, _, resto = str(texto or "").partition(" · ")
    return livro.strip(), [a.strip() for a in resto.split(", ") if a.strip()]


def alvos(f) -> list[dict]:
    """As tabelas que a prévia de `f` pode mostrar, na ordem da lista de escolha: a do Nexus (com os IDs) primeiro,
    depois as de origem. `fora`: a fonte não está no banco (o arquivo do robô do PCM), só a frase."""
    out = []
    if f.conformado_em:
        livro, abas = _par(f.conformado_em)
        out.append({"livro": livro, "aba": abas[0] if abas else "", "papel": "nexus", "por_usina": False})
    for texto in (f.fontes or (f.livro,)):
        # a programação do PCM: o fato diz "fora do banco: ..." e a fonte declarada é o arquivo do robô do PCM
        fora = f.livro.startswith("fora do banco") and not texto.startswith("nexus_")
        if texto.startswith("fora do banco") or fora:
            out.append({"livro": "", "aba": "", "papel": "origem", "por_usina": False,
                        "fora": texto if texto.startswith("fora do banco") else f.livro})
            continue
        livro, abas = _par(texto)
        for aba in abas or [""]:
            por = aba.startswith(POR_USINA)
            out.append({"livro": livro, "aba": "" if por else aba, "papel": "origem", "por_usina": por})
    lista, vistos = [], set()
    for a in out:
        k = (a["livro"], a["aba"], a["por_usina"], a.get("fora"))
        if k not in vistos:
            vistos.add(k)
            a["rotulo"] = _rotulo(a)
            lista.append(a)
    return lista


def _rotulo(a: dict) -> str:
    if a.get("fora"):
        return f"Fora do banco: {a['fora'].removeprefix('fora do banco:').strip()}"
    nome = f"{a['livro']} ({POR_USINA})" if a["por_usina"] else " · ".join(x for x in (a["livro"], a["aba"]) if x)
    return f"No Nexus, com os IDs: {nome}" if a["papel"] == "nexus" else f"Origem: {nome}"


_COBERTAS = {}


def cobertas() -> tuple[frozenset, frozenset]:
    """(as (livro, aba) que são fonte ou destino de algum fato, ou aba de livro do Nexus; os livros "1 aba por usina").
    Sai do catálogo, que não muda com o processo no ar: calculado uma vez."""
    if not _COBERTAS:
        pares, por_usina = set(), set()
        for f in catalogo.FATOS:
            for a in alvos(f):
                if a.get("fora"):
                    continue
                if a["por_usina"]:
                    por_usina.add(a["livro"])
                else:
                    pares.add((a["livro"], a["aba"]))
        pares |= {(lv.nome, aba) for lv in catalogo.LIVROS for aba in lv.abas}
        _COBERTAS.update(pares=frozenset(pares), por_usina=frozenset(por_usina))
    return _COBERTAS["pares"], _COBERTAS["por_usina"]


def _abas(base, sessao) -> dict:
    """{(livro, aba): {id, row_count, visibility, ...}} de todas as abas do banco (cache de 5 min)."""
    if _ABAS["v"] is not None and time.time() - _ABAS["t"] < TTL_ABAS_S:
        return _ABAS["v"]
    r = sessao.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    v = {(x.get("workbook_key"), x.get("sheet_name")): x for x in r.json()}
    _ABAS.update(t=time.time(), v=v)
    return v


def _atualizado_em(base, sessao, livro: str) -> str:
    if _LIVROS_EM["v"] is None or time.time() - _LIVROS_EM["t"] >= TTL_ABAS_S:
        try:
            r = sessao.get(f"{base}/api/workbooks", timeout=60)
            r.raise_for_status()
            _LIVROS_EM.update(t=time.time(), v={w.get("key"): w.get("updated_at") or "" for w in r.json()})
        except Exception:       # noqa: BLE001 — a hora é enfeite: sem ela a prévia sai igual
            return ""
    try:
        return datetime.fromisoformat(str(_LIVROS_EM["v"].get(livro) or "")).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return ""


def abas_de_usina(abas: dict, livro: str) -> list[str]:
    """As abas de usina do livro, na ordem do banco: as visíveis que não são fonte de outro fato (a "Dados Mensais" é da
    meta mensal) nem estão declaradas no catálogo como outra coisa (`catalogo.CONHECIDAS`: cadastro, histórico...)."""
    pares = cobertas()[0]
    xs = [x for (wb, nome), x in abas.items() if wb == livro and (wb, nome) not in pares
          and not catalogo.conhecida(wb, nome) and (x.get("visibility") or "visible") == "visible"]
    return [x["sheet_name"] for x in sorted(xs, key=lambda x: x.get("id") or 0)]


def _todas(base, sessao, sid) -> list[dict]:
    out, offset = [], 0
    while True:
        r = sessao.get(f"{base}/api/sheets/{sid}/rows", params={"limit": 1000, "offset": offset}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        out += rows
        if len(rows) < 1000:
            return out
        offset += 1000


def _linhas_da_pagina(base, sessao, meta: dict, offset: int, limite: int) -> list[dict]:
    """[{headers, values}] da janela pedida (cache de 2 min por aba e janela)."""
    k = (meta["id"], offset, limite)
    t, v = _PAGINAS.get(k, (0.0, None))
    if v is not None and time.time() - t < TTL_PAGINA_S:
        return v
    r = sessao.get(f"{base}/api/sheets/{meta['id']}/rows", params={"limit": limite, "offset": offset}, timeout=60)
    r.raise_for_status()
    rows = r.json()
    rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
    if len(_PAGINAS) > 200:
        _PAGINAS.clear()
    _PAGINAS[k] = (time.time(), rows)
    return rows


def _celula(v) -> tuple[str, str]:
    """(o texto da célula, o title com o texto inteiro quando cortado)."""
    if isinstance(v, dict) and "$dt" in v:       # data que a API devolve como objeto
        v = v["$dt"]
    if v is None:
        return "", ""
    if isinstance(v, float):
        # o número como a planilha mostra: 41782.399999999994 (o resto binário do float) vira 41782.4
        v = int(v) if v.is_integer() else f"{v:.12g}"
    s = _EMAIL.sub("[e-mail]", " ".join(str(v).split()))
    return (s[:CELULA_MAX - 1] + "…", s) if len(s) > CELULA_MAX else (s, "")


def pagina(base, sessao, meta: dict, ini: int | None = None, limite: int = LIMITE) -> dict:
    """`limite` linhas a partir da linha `ini` (1 = a 1ª da tabela; sem `ini`, as últimas), na ordem da tabela. Pela
    1ª linha, e não pela página contada do fim: assim o Início mostra 1 a 50 (contada do fim, a 1ª página de uma aba de
    14.276 linhas tinha 26). Sem a contagem de linhas na listagem (o banco falso dos testes), lê a aba e conta."""
    total = meta.get("row_count")
    if total is None:
        todas = _todas(base, sessao, meta["id"])
        total = len(todas)
    ultimo = max(1, total - limite + 1)            # a 1ª linha da última página
    ini = ultimo if ini is None else min(max(1, ini), ultimo)
    de, ate = ini - 1, min(total, ini - 1 + limite)
    if meta.get("row_count") is None:
        rows = todas[de:ate]
    else:
        rows = _linhas_da_pagina(base, sessao, meta, de, ate - de) if ate > de else []
    colunas = []
    for x in rows:
        for c in x.get("headers") or []:
            if c not in colunas:
                colunas.append(c)
    linhas = []
    for i, x in enumerate(rows):
        valores = dict(zip(x.get("headers") or [], x.get("values") or []))
        linhas.append((de + i + 1, [_celula(valores.get(c)) for c in colunas]))
    return {"colunas": colunas, "linhas": linhas, "total": total, "ini": ini if rows else 0, "fim": de + len(rows),
            "no_comeco": ini == 1, "no_fim": ini == ultimo, "anterior": max(1, ini - limite),
            "proxima": min(ultimo, ini + limite), "ultimo": ultimo}


def _sessao():
    s = current_app.extensions.get("nexus_dados_sessao")
    if s is None and current_app.config.get("TESTING"):
        return None                                 # teste nunca vai à rede
    if s is None:
        import requests
        s = requests.Session()
    return s


def _milhar(n) -> str:
    """14276 -> '14.276'."""
    return f"{int(n):,}".replace(",", ".")


def _int(v, padrao: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return padrao


def responder_nova(livro: str, aba: str, args):
    """A prévia de uma tabela NOVA do radar (fora do catálogo): só para administrador (o catálogo ainda não diz o que ela
    guarda) e só se o radar, com a listagem do banco relida, ainda a classifica como nova."""
    from . import radar
    alvo = {"livro": livro, "aba": aba, "papel": "nova", "por_usina": False}
    alvo["rotulo"] = f"Nova no banco: {livro} · {aba}"
    ctx = {"fato": None, "alvos": [alvo], "t": 0, "alvo": alvo, "erro": None, "dados": None, "milhar": _milhar,
           "abas_usina": [], "aba": aba, "existe": {0: True}, "atualizada": "", "recusada": False}
    if not session.get("admin"):
        ctx["erro"] = "só administrador vê as linhas de uma tabela que o catálogo ainda não conhece"
        return render_template("dados/_tabela.html", **ctx)
    sessao = _sessao()
    if sessao is None:
        ctx["erro"] = "teste sem banco"
        return render_template("dados/_tabela.html", **ctx)
    base = carga._base(current_app.config)
    try:
        abas = _abas(base, sessao)
    except Exception as e:      # noqa: BLE001
        ctx["erro"] = type(e).__name__
        return render_template("dados/_tabela.html", **ctx)
    if (livro, aba) not in {(t["livro"], t["aba"]) for t in radar.classificar(abas)["nova"]}:
        return None                                 # já não é nova (ou nunca foi): a rota responde 404
    ctx["atualizada"] = _atualizado_em(base, sessao, livro)
    try:
        ctx["dados"] = pagina(base, sessao, abas[(livro, aba)], _int(args.get("ini"), None))
    except Exception as e:      # noqa: BLE001
        ctx["erro"] = type(e).__name__
    return render_template("dados/_tabela.html", **ctx)


def responder(f, args):
    """O pedaço de HTML da prévia de `f` (o JavaScript do organograma põe ao lado da gaveta)."""
    lista = alvos(f)
    ctx = {"fato": f, "alvos": lista, "t": 0, "alvo": None, "erro": None, "dados": None, "milhar": _milhar,
           "abas_usina": [], "aba": "", "existe": {}, "atualizada": "", "recusada": False}
    sessao = _sessao()
    if sessao is None:
        ctx["erro"] = "teste sem banco"
        return render_template("dados/_tabela.html", **ctx)
    base = carga._base(current_app.config)
    try:
        abas = _abas(base, sessao)
    except Exception as e:      # noqa: BLE001 — banco fora do ar: a prévia diz isso, a gaveta segue
        ctx["erro"] = type(e).__name__
        return render_template("dados/_tabela.html", **ctx)
    existe = {i: (a["por_usina"] and bool(abas_de_usina(abas, a["livro"]))) or (a["livro"], a["aba"]) in abas
              for i, a in enumerate(lista)}
    # sem escolha, a 1ª tabela que existe no banco (a do Nexus, quando já está lá)
    t = _int(args.get("t"), -1)
    if not 0 <= t < len(lista):
        t = next((i for i in range(len(lista)) if existe[i]), 0)
    alvo = lista[t]
    ctx.update(t=t, alvo=alvo, existe=existe)
    if alvo.get("fora") or not existe[t]:
        return render_template("dados/_tabela.html", **ctx)
    aba = alvo["aba"]
    if alvo["por_usina"]:
        ctx["abas_usina"] = abas_de_usina(abas, alvo["livro"])
        aba = args.get("aba") if args.get("aba") in ctx["abas_usina"] else ctx["abas_usina"][0]
    meta = abas[(alvo["livro"], aba)]
    ctx.update(aba=aba, atualizada=_atualizado_em(base, sessao, alvo["livro"]))
    try:
        dados = pagina(base, sessao, meta, _int(args.get("ini"), None))
    except Exception as e:      # noqa: BLE001
        ctx["erro"] = type(e).__name__
        return render_template("dados/_tabela.html", **ctx)
    if alvo["por_usina"] and dados["colunas"]:
        if not geracao.abas_de_geracao({aba: [dict.fromkeys(dados["colunas"])]}):
            ctx["recusada"] = True                  # aba de outro assunto: nenhuma linha sai
            return render_template("dados/_tabela.html", **ctx)
    ctx["dados"] = dados
    return render_template("dados/_tabela.html", **ctx)
