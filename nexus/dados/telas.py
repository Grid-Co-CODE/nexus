"""Tela Base → Governança de dados: a matriz de barramento viva (do catálogo) e a qualidade da última carga.

Levi, 05/10/2026: "prioridade 0 para a governança e controle de dados". A tela mostra o que existe, de onde vem, o que
é cada linha (grão) e quanto de cada fato liga por ID. A qualidade vem do banco (`nexus_fatos · qualidade`, gravada pela
carga de hora em hora); sem ela, a tela mostra só o catálogo e avisa.

08/10/2026 (auditoria Kimball): a matriz mostra também o TIPO de cada fato, a chave, as medidas (com a unidade e se
somam) e quanto a fonte guarda; os livros do Nexus (registrados antes de existir: regra 10); a saúde do histórico
(`nexus_dimensoes · qualidade_historico`) e o resumo da dimensão de equipamento (`nexus_equipamentos · qualidade`).

08/10/2026, Levi: "Quero uma visão de cima da governança também, teria como fazer um organograma??". Segunda visão da
mesma tela: a raiz com os números do resumo, os setores (o `area` de cada fato, com o nome da torre dona), os fatos de
cada setor pelo estado e as dimensões conformadas que ligam os setores. Tudo sai do catálogo (`organograma`), nada de
lista à mão; a qualidade é a mesma da última carga.

09/10/2026, Levi, depois de usar: o organograma é o padrão e a matriz a segunda (`?ver=matriz`); o aposentado some das
duas visões ("se ele é inútil deixe em sua inutilidade"); as fontes de outro fato ficam abertas no setor (os dados delas
são usados: alimentam o fato onde ganham os IDs); a gaveta cresce com o que tem a mostrar e fala para quem não é da área
de dados (`explica.py`); e mostra a tabela de verdade, só para ler (`previa.py`).
"""
import json
import math
import re
import time
from datetime import datetime

from flask import abort, current_app, render_template, request, session, url_for

from . import carga, catalogo, equipamento, explica, historico, livros, previa, programacao, radar

_CACHE = {"t": 0.0, "v": None}
TTL_S = 300
# o que a tela mostra do `nexus_equipamentos · qualidade` (formato longo: grupo, item)
_EQ_RESUMO = (("dimensão", "membros"), ("dimensão", "na foto do Fracttal"), ("dimensão", "com usina_id"),
              ("dimensão", "com pai_id"))


def _ultima_qualidade():
    if _CACHE["v"] is not None and time.time() - _CACHE["t"] < TTL_S:
        return _CACHE["v"]
    import requests
    s = current_app.extensions.get("nexus_dados_sessao")
    if s is None and current_app.config.get("TESTING"):
        return {"qualidade": {}, "atualizacao": {}, "historico": [], "equipamento": [],
                "erro": "teste sem banco", "radar": None, "radar_erro": "teste sem banco"}  # teste nunca vai à rede
    s = s or requests.Session()
    base = carga._base(current_app.config)
    try:
        q = {l.get("fato"): l for l in livros.ler(base, s, carga.LIVRO_FATOS, "qualidade")}
        # a programação do PCM tem livro próprio desde 08/10/2026 (`nexus_programacao`, mescla por semana)
        q.update({l.get("fato"): l for l in livros.ler(base, s, programacao.LIVRO, "qualidade")})
        at = next(iter(livros.ler(base, s, carga.LIVRO_FATOS, "atualizacao")), {})
        hq = livros.ler(base, s, carga.LIVRO_DIM, historico.ABA_QUALIDADE)
        eq = {(l.get("grupo"), l.get("item")): l for l in livros.ler(base, s, equipamento.LIVRO, "qualidade")}
        v = {"qualidade": q, "atualizacao": at, "historico": hq,
             "equipamento": [(item, eq[(g, item)]) for g, item in _EQ_RESUMO if (g, item) in eq], "erro": None}
    except Exception as e:      # noqa: BLE001 — banco fora do ar: a tela mostra o catálogo
        v = {"qualidade": {}, "atualizacao": {}, "historico": [], "equipamento": [], "erro": f"{type(e).__name__}"}
    # o radar do banco (09/10/2026): a lista de todas as abas, comparada com o catálogo. Falhar aqui não apaga a qualidade
    try:
        v.update(radar=radar.resumo(previa._abas(base, s)), radar_erro=None)
    except Exception as e:      # noqa: BLE001
        v.update(radar=None, radar_erro=type(e).__name__)
    _CACHE.update(t=time.time(), v=v)
    return v


def _hora(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return ""


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(v) -> str:
    """99.7 -> "99,7%", 100.0 -> "100%", vazio -> "" (a qualidade tem 1 casa desde 08/10; a API pode devolver texto)."""
    x = _num(v)
    if x is None:
        return ""
    return f"{int(x)}%" if x == int(x) else f"{x:.1f}%".replace(".", ",")


def _extra(v) -> dict:
    try:
        d = json.loads(v or "{}")
    except (TypeError, ValueError):
        return {}
    return {k: x for k, x in d.items() if isinstance(x, (int, float, str)) and not isinstance(x, bool)}


# ── o organograma (08/10/2026) ────────────────────────────────────────────────────────────────────────────────────
# a primeira é o padrão (Levi, 09/10/2026: "Deixe organograma como padrão, Matriz em segundo")
VISOES = ("organograma", "matriz")

# O estado de cada fato na visão de cima: a palavra (nunca só a cor), o tom do semáforo da casa (tokens do nexus.css, um
# matiz por degrau: conformado verde, montado amarelo, origem laranja, fora do banco vermelho) e o que quer dizer (o
# docstring do catálogo, sem repetir a palavra). A fonte de outro fato fica neutra: não conta (`catalogo.ativos`), mas
# aparece aberta no setor, porque os dados dela alimentam o fato onde ganham os IDs (Levi, 09/10: "estamos usando os
# dados? fazemos ligações? Se sim já deixa expandido"). Era "parte de", que não dizia isso. O aposentado não aparece
# (a entrada fica para o teste de que todo estado do catálogo tem palavra).
ESTADO_ORG = {"conformado": ("conformado", "ok", "gravado no banco com os IDs do Nexus"),
              "montado": ("montado", "alerta", "o Nexus monta com os IDs; gravar espera decisão"),
              "origem": ("origem", "severo", "só como a fonte grava, sem os IDs do Nexus"),
              "fora": ("fora do banco", "critico", "nem no banco nem montado"),
              "parte": ("fonte", "neutro", "tabela crua que alimenta outro fato; as ligações por ID são feitas nele"),
              "aposentado": ("aposentado", "neutro", "a fonte não vale mais")}
# A situação do fato em uma frase, na gaveta (09/10/2026: a linguagem para quem quer saber para que a tabela serve)
ESTADO_FRASE = {
    "conformado": "Pronta: o Nexus grava esta tabela no banco com os IDs dele, e ela se cruza com as dos outros "
                  "setores sem conversão.",
    "montado": "Quase pronta: o Nexus já monta esta tabela com os IDs, mas ainda não grava no banco (espera uma "
               "decisão).",
    "origem": "Como a fonte grava: o Nexus ainda não monta esta tabela no padrão dele (com os IDs em todas as "
              "ligações). Cruzar com as outras depende de como cada coluna liga, na tabela abaixo.",
    "fora": "Fora do banco: ainda não está no banco de dados nem é montada pelo Nexus.",
    "parte": "Tabela de origem: os dados daqui alimentam {alimenta}, e é lá que ganham os IDs do Nexus.",
    "aposentado": "Aposentada: a fonte não vale mais.",
}
# a ordem dos degraus na barra de cada setor (do pronto ao que falta) e o plural da contagem
DEGRAUS = (("conformado", "conformado", "conformados"), ("montado", "montado", "montados"),
           ("origem", "de origem", "de origem"), ("fora", "fora do banco", "fora do banco"))
TIPO_EXPLICA = {"transacao": "1 linha por acontecimento, não muda depois",
                "snapshot_periodico": "o estado no fim de cada período (dia, semana, mês)",
                "snapshot_acumulado": "a linha muda até fechar (soma de duas cargas conta em dobro)",
                "sem_medida": "só registra que aconteceu: conta-se linhas"}
# o mesmo tipo dito para quem não conhece o Kimball (a palavra técnica fica em "Para quem mantém o dado")
TIPO_FRASE = {"transacao": "É um acontecimento por linha, que não muda depois de gravado.",
              "snapshot_periodico": "É o retrato de um período (um dia, uma semana ou um mês).",
              "snapshot_acumulado": "A linha muda até o caso fechar: por isso, somar duas cargas conta em dobro.",
              "sem_medida": "Não tem número para somar: o que se conta é quantas vezes aconteceu."}
SOMA_ROTULO = {"aditiva": "sim", "semi": "só num sentido (no tempo, de uma usina só)",
               "nao": "não: use média, mínimo ou máximo"}
# o que quer dizer cada jeito de ligar, na legenda da gaveta (só os que o fato usa)
LIGA_FRASE = {"id": "liga direto ao cadastro do Nexus: o jeito certo",
              "cod": "liga por um código de outro sistema, que precisa do de-para",
              "hmac": "a pessoa como um código tirado do e-mail, sem o e-mail em claro",
              "nome": "liga pelo nome escrito: grafia diferente quebra a ligação",
              "largo": "um equipamento por coluna: precisa virar linhas antes de ligar",
              "prop": "um cadastro que só esta tabela usa"}
# o que a qualidade grava por dimensão (as mesmas colunas da matriz)
PCT_DIM = {"data": "pct_data", "usina": "pct_usina", "equipe": "pct_equipe", "pessoa": "pct_pessoa",
           "equipamento": "pct_equipamento"}
# Quem grava cada livro de ORIGEM. O catálogo registra quem grava só os livros do Nexus (`LIVROS.quem_grava`); os de
# origem são de outros sistemas e não têm esse campo, e a família do nome diz qual é (derivado aqui, sem mexer no
# catálogo). Livro de família nova cai em "a declarar" e aparece assim na tela: a lacuna fica à vista.
QUEM_GRAVA_ORIGEM = (
    ("sufixo", "_app_campo", "App de Campo"),                    # o servidor do App grava de hora em hora (aos :25)
    ("igual", "pcm", "robô do PCM"),                             # o banco_dados.json do PCM (GitHub), fora do banco
    ("igual", "falhas_performance", "plataforma de performance"),
    ("prefixo", "plataforma_", "plataforma de performance"),    # plataforma_series, plataforma_estado
    ("prefixo", "bd_", "coletor da API PV"),                     # bd_thopen e bd_performance
    ("igual", "gemeo_digital", "gêmeo digital"),
    ("igual", "tickets_performance", "planilha de tickets (sincronizada) e OS Creator"),
    ("igual", "campo_nexus", "coletor do Fracttal do Nexus (desligado em 05/10)"),
    ("prefixo", "nexus_", "Nexus"),                              # livro do Nexus fora do LIVROS: viola a regra 10
)
A_DECLARAR = "a declarar"
TRILHA_MAX_FATOS = 6        # na visão larga, um setor com mais fatos que isto ganha outra coluna (até 3)


def _nome_do_livro(texto: str) -> str:
    """'fechamentos_app_campo · Fechamentos' -> 'fechamentos_app_campo'. O 'fora do banco: ...' fica inteiro."""
    return str(texto or "").split(" · ", 1)[0].strip()


def quem_grava(texto: str) -> tuple[str, str]:
    """(quem grava, quando) o livro de `texto` ("livro · aba"): o `LIVROS` do catálogo primeiro; senão a família do
    nome (`QUEM_GRAVA_ORIGEM`); senão `A_DECLARAR`."""
    nome = _nome_do_livro(texto)
    lv = catalogo.LIVRO_POR_NOME.get(nome)
    if lv:
        return lv.quem_grava, lv.cadencia
    for como, padrao, quem in QUEM_GRAVA_ORIGEM:
        if ((como == "igual" and nome == padrao) or (como == "prefixo" and nome.startswith(padrao))
                or (como == "sufixo" and nome.endswith(padrao))):
            return quem, ""
    return A_DECLARAR, ""


def _livro(texto: str) -> dict:
    """O livro com quem grava. No livro do Nexus o `quem_grava` do catálogo é o caminho do código ("nexus/dados/carga.py"):
    o cartão e a gaveta dizem "Nexus" (09/10/2026, a linguagem para quem não é da área de dados) e o caminho fica em
    letra pequena na gaveta, para quem mantém."""
    quem, cadencia = quem_grava(texto)
    nome = _nome_do_livro(texto)
    do_nexus = nome in catalogo.LIVRO_POR_NOME
    return {"texto": texto, "livro": nome, "quem": quem, "cadencia": cadencia,
            "quem_amigavel": "Nexus" if do_nexus else quem, "quem_tecnico": quem if do_nexus else ""}


def _setor(area: str, torres: dict) -> dict:
    """O rótulo e o ícone do setor saem da torre dona (o `area` do fato é o id da torre); área sem torre (um "cadastro",
    por exemplo) vira o próprio nome, legível."""
    t = torres.get(area)
    if t is not None:
        return {"id": area, "rotulo": t.nome, "icone": t.icone}
    return {"id": area, "rotulo": area.replace("_", " ").capitalize(), "icone": "database"}


def _curto(quem: str) -> str:
    """No cartão, quem grava sem o parêntese ('... programacao.py (o histórico: ferramentas/...)'); a gaveta diz tudo."""
    return re.sub(r"\s*\(.*?\)", "", quem).strip() or quem


def _mais(itens: list) -> str:
    """Até 2 nomes inteiros; com mais, o 1º e quantos faltam (o fato único de ronda tem 3 fontes)."""
    return " + ".join(itens) if len(itens) <= 2 else f"{itens[0]} +{len(itens) - 1}"


def _contagem(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def _cartao(f: catalogo.Fato, ql: dict | None, setor: dict) -> dict:
    # estado que o catálogo ganhe depois desta tela: a palavra do catálogo, neutro, até alguém dar o tom dele aqui
    estado, tom, explica_estado = ESTADO_ORG.get(f.estado,
                                                 (catalogo.ESTADOS_FATO.get(f.estado, f.estado), "neutro", ""))
    # as fontes (o livro · aba de cada uma, com quem grava); sem `fontes` declaradas, o próprio `livro`. A programação do
    # PCM mora "fora do banco" e a fonte declarada é o arquivo do robô do PCM
    fontes = [_livro(x) for x in (f.fontes or (f.livro,))]
    if f.livro.startswith("fora do banco"):
        livros_card = [f.livro]
    else:
        livros_card = list(dict.fromkeys(l["livro"] for l in fontes))
    nexus = None
    if f.conformado_em:
        nexus = _livro(f.conformado_em)
        nexus["grava"] = f.estado == "conformado"     # montado: o destino registrado, ainda sem gravar
    dims = []
    for did, nome, _onde, _chave in catalogo.DIMENSOES:
        est, col = f.dims.get(did, ("nao", ""))
        v = ql.get(PCT_DIM[did]) if (ql and did in PCT_DIM and f.estado == "conformado") else None
        dims.append({"id": did, "nome": nome, "estado": est, "rotulo": catalogo.ESTADOS.get(est, est), "col": col,
                     "pct": _pct(v) if v not in (None, "") else ""})
    # a gaveta mostra só as dimensões que o fato tem (as que faltam, numa linha), com a legenda dos jeitos que ele usa
    com = [d for d in dims if d["estado"] != "nao"]
    parte_de = [catalogo.POR_ID[p].nome if p in catalogo.POR_ID else p for p in f.parte_de]
    frase = ESTADO_FRASE.get(f.estado, explica_estado)
    if "{alimenta}" in frase:
        frase = frase.format(alimenta=_lista(parte_de) or "outro fato")
    return {"id": f.id, "nome": f.nome, "estado": f.estado, "estado_rotulo": estado, "tom": tom,
            "estado_explica": explica_estado, "estado_frase": frase, "setor": setor["rotulo"],
            "resumo": explica.RESUMO.get(f.id, ""), "para_que": explica.PARA_QUE.get(f.id, ""),
            "tipo": catalogo.TIPO_ROTULO.get(f.tipo, f.tipo), "tipo_explica": TIPO_EXPLICA.get(f.tipo, ""),
            "tipo_frase": TIPO_FRASE.get(f.tipo, ""),
            "grao": f.grao, "grao_curto": re.sub(r"^1 linha = ", "", f.grao), "chave": f.chave,
            "janela": f.janela_origem, "observacao": f.observacao,
            "medidas": [{"coluna": m.coluna, "unidade": m.unidade,
                         "soma": ("sim: a soma diz quantas" if m.unidade == "1/0" and m.soma == "aditiva"
                                  else SOMA_ROTULO.get(m.soma, m.soma))}
                        for m in f.medidas],
            "fontes": fontes, "nexus": nexus, "livros_card": _mais(livros_card),
            "quem_card": _mais([_curto(q) for q in dict.fromkeys(l["quem_amigavel"] for l in fontes)]),
            "parte_de": parte_de, "alimenta": _lista(parte_de), "dims": dims, "dims_com": com,
            "dims_sem": [d["nome"] for d in dims if d["estado"] == "nao"], "tem_pct": any(d["pct"] for d in com),
            "legenda": [(e, catalogo.ESTADOS.get(e, e), LIGA_FRASE.get(e, ""))
                        for e in dict.fromkeys(d["estado"] for d in com)],
            "q": ql or None}


def _lista(nomes: list) -> str:
    """['a', 'b', 'c'] -> 'a, b e c'."""
    return " e ".join(", ".join(nomes).rsplit(", ", 1)) if nomes else ""


def organograma(torres, q: dict) -> dict:
    """A visão de cima, toda do catálogo: a raiz (as contas do `catalogo.resumo`, mais os de origem, que o resumo não
    separa), os setores na ordem em que aparecem no catálogo (a mesma da matriz), os cartões de cada setor (os ativos e,
    à parte, os que viraram fonte de outro fato ou se aposentaram) e as dimensões conformadas com quantos fatos ativos
    ligam a cada uma por ID e por outro caminho. `torres`: as torres do app (o nome e o ícone de cada setor)."""
    por_torre = {t.id: t for t in (torres or ())}
    ativos = catalogo.ativos()
    ids_ativos = {f.id for f in ativos}
    conta = dict(catalogo.resumo(), origem=sum(1 for f in ativos if f.estado == "origem"))
    setores = {}
    for f in catalogo.FATOS:
        if f.estado == "aposentado":        # Levi, 09/10/2026: "Não mostre aposentado"
            continue
        s = setores.get(f.area)
        if s is None:
            s = setores[f.area] = dict(_setor(f.area, por_torre), ativos=[], fontes=[])
        (s["ativos"] if f.id in ids_ativos else s["fontes"]).append(_cartao(f, q.get(f.id), s))
    for s in setores.values():
        n = len(s["ativos"])
        s["n"] = n
        s["por_estado"] = {e: sum(1 for c in s["ativos"] if c["estado"] == e) for e, _, _ in DEGRAUS}
        s["conformados"] = s["por_estado"]["conformado"]
        s["resumo_estados"] = ", ".join(_contagem(s["por_estado"][e], um, varios)
                                        for e, um, varios in DEGRAUS if s["por_estado"][e]) or "nenhum fato ativo"
        # na visão larga, um setor com muitos fatos ganha colunas (até 3), para a árvore não virar uma torre só; a ordem
        # desce pela 1ª coluna e continua na 2ª, e as linhas das colunas ficam alinhadas
        s["trilhas"] = max(1, min(3, math.ceil(n / TRILHA_MAX_FATOS)))
        s["linhas"] = max(1, math.ceil(n / s["trilhas"]))
        for i, c in enumerate(s["ativos"]):
            c["topo_de_coluna"] = i % s["linhas"] == 0
            c["fim_de_coluna"] = (i + 1) % s["linhas"] == 0 or i == n - 1
    lista = list(setores.values())
    dims = []
    ordem_estados = list(catalogo.ESTADOS)
    for did, nome, onde, chave in catalogo.DIMENSOES:
        estados = [f.dims.get(did, ("nao", ""))[0] for f in ativos]
        # os outros caminhos na ordem da legenda da matriz (código, código da pessoa, nome, colunas, próprio); um estado
        # que o catálogo ainda não conhece vai no fim, mas aparece
        outros = sorted((e for e in dict.fromkeys(estados) if e not in ("id", "nao")),
                        key=lambda e: ordem_estados.index(e) if e in ordem_estados else len(ordem_estados))
        usam = {}
        for f in ativos:
            if f.dims.get(did, ("nao",))[0] != "nao":
                usam[f.area] = usam.get(f.area, 0) + 1
        dims.append({"id": did, "nome": nome, "mestre": onde, "chave": chave, "por_id": estados.count("id"),
                     "por_outro": sum(estados.count(e) for e in outros), "sem": estados.count("nao"),
                     "outros": [(e, catalogo.ESTADOS.get(e, e), estados.count(e)) for e in outros],
                     "setores": [(s["rotulo"], usam[s["id"]]) for s in lista if s["id"] in usam]})
    return {"conta": conta, "setores": lista, "dimensoes": dims, "trilhas": sum(s["trilhas"] for s in lista) or 1}


def registrar_governanca(bp):
    @bp.route("/governanca")
    def governanca():
        v = _ultima_qualidade()
        ver = request.args.get("ver") if request.args.get("ver") in VISOES else VISOES[0]
        grupos = {}
        for f in catalogo.FATOS:
            if f.estado != "aposentado":        # Levi, 09/10/2026: "Não mostre aposentado" (nas duas visões)
                grupos.setdefault(f.area, []).append(f)
        org = organograma(current_app.extensions.get("nexus_torres"), v["qualidade"]) if ver == "organograma" else None
        return render_template("dados/governanca.html", torre=bp.name, catalogo=catalogo, grupos=grupos,
                               resumo=catalogo.resumo(), q=v["qualidade"], atualizacao=v["atualizacao"],
                               hist_q=v["historico"], eq_q=v["equipamento"], erro=v["erro"], hora=_hora, pct=_pct,
                               num=_num, extra=_extra, ver=ver, org=org, degraus=DEGRAUS, estado_org=ESTADO_ORG,
                               url_matriz=url_for(f"{bp.name}.governanca", ver="matriz"),
                               url_organograma=url_for(f"{bp.name}.governanca"),
                               url_tabela=url_for(f"{bp.name}.governanca_tabela"), radar=v.get("radar"),
                               radar_erro=v.get("radar_erro"), admin=bool(session.get("admin")),
                               milhar=previa._milhar)

    @bp.route("/governanca/tabela")
    def governanca_tabela():
        """A tabela do fato, só para ler: o pedaço de HTML que a gaveta do organograma põe ao lado dela. Com `nova`, a
        tabela nova do radar (só administrador, e só se ainda for nova)."""
        if request.args.get("nova"):
            r = previa.responder_nova(request.args.get("livro", ""), request.args.get("aba_nova", ""), request.args)
            if r is None:
                abort(404)
            return r
        f = catalogo.POR_ID.get(request.args.get("fato", ""))
        if f is None or f.estado == "aposentado":
            abort(404)
        return previa.responder(f, request.args)
