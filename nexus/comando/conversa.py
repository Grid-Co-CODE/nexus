"""A conversa presa ao objeto, com @menção de pessoa e de área (Fase 2 dos setores conversando, 03/11/2026): o livro
`nexus_conversas · fato_mensagem`.

Levi, 03/11/2026: "Preciso pensar em uma forma dos setores conversarem entre si de forma rastreável e clara com chats,
notificações...". Como as plataformas maduras fazem (ServiceNow, Jira, Linear): a conversa mora NO objeto (o insight, a
OS, a usina), não num chat solto, e a @menção avisa quem precisa ver.

O Nexus é a FONTE: 1 linha por evento, só acrescenta. Os eventos:
- `mensagem`: alguém escreve na conversa de um objeto, mencionando pessoas (pelo código do e-mail, `mencoes_pessoas`) e
  áreas (as torres, `mencoes_areas`: todo mundo cujo setor vê a torre);
- `leu`: a pessoa marcou como lidas as menções daquele objeto (escrever na conversa também conta como ler).

O objeto é `tipo:id`: `insight:R07:2`, `os:16702`, `usina:12`. Em claro: o objeto, o evento, as menções por código e por
torre, o dia e quem escreveu por código; o nome de quem escreveu e o texto, só cifrados (o Cofre): o banco tem leitura
aberta. Registrado no catálogo antes da 1ª gravação (nexus/dados/CLAUDE.md, regra 10).
"""
import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros
from . import estado as ES

LIVRO, NOME_LIVRO, ABA = "nexus_conversas", "Nexus · conversas com @menção", "fato_mensagem"
CAB = ("id", "registrado_em", "data_id", "objeto_tipo", "objeto_id", "evento", "mencoes_pessoas", "mencoes_areas",
       "pessoa_id", "pessoa_hmac", "dados_cifrados")
EVENTOS = ("mensagem", "leu")
TIPOS = {"insight": "Insight", "os": "OS", "usina": "Usina"}
_ID_RE = {"insight": ES.INSIGHT_RE, "os": re.compile(r"\d{1,9}"), "usina": re.compile(r"\d{1,9}")}
HMAC_RE = re.compile(r"[0-9a-f]{16,128}")
TEXTO_MAX = 1000
MENCOES_MAX = 20
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}

Recusada = ES.Recusada


def limpar() -> None:
    _CACHE.clear()


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def objeto(tipo, oid) -> str | None:
    """A chave `tipo:id` validada, ou None."""
    tipo, oid = _txt(tipo).lower(), _txt(oid)
    if tipo not in TIPOS or not _ID_RE[tipo].fullmatch(oid):
        return None
    return f"{tipo}:{oid}"


def _lista(v, padrao) -> list[str]:
    return [x for x in dict.fromkeys(t.strip().lower() for t in _txt(v).split(",")) if padrao.fullmatch(x)]


def _ctx(l: dict) -> str:
    return (f"banco/conversas/{_txt(l.get('id'))}/{_txt(l.get('objeto_tipo'))}:{_txt(l.get('objeto_id'))}/"
            f"{_txt(l.get('evento'))}/{_txt(l.get('pessoa_hmac')) or '-'}")


def ler(forcar: bool = False) -> dict:
    """{"linhas", "erro"}, cópia de 1 minuto. Leitura que falha devolve a última boa com o erro."""
    agora = time.time()
    g = _CACHE.get("livro")
    if g and not forcar and agora - g["lido_em"] < TTL_S:
        return g
    try:
        linhas = livros.ler(*ES._banco(), LIVRO, ABA)
    except Exception as ex:      # noqa: BLE001 — banco fora: as telas seguem sem as conversas
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(g, erro=erro) if g else {"linhas": [], "lido_em": None, "erro": erro}
    _CACHE["livro"] = {"linhas": linhas, "lido_em": agora, "erro": ""}
    return _CACHE["livro"]


def conversas(linhas: list[dict], cofre=None) -> dict:
    """{objeto: {"mensagens": [{"id", "quando", "quando_txt", "por", "pessoa_hmac", "texto", "pessoas", "areas"}],
    "leu": {hmac: quando}}}, na ordem da gravação. Linha mexida (objeto ou evento fora do padrão) fica fora."""
    out = {}
    for l in linhas:
        ob, ev = objeto(l.get("objeto_tipo"), l.get("objeto_id")), _txt(l.get("evento"))
        if not ob or ev not in EVENTOS:
            continue
        q = ES._quando(l.get("registrado_em"))
        if q is None:
            continue
        quem = _txt(l.get("pessoa_hmac")).lower()
        c = out.setdefault(ob, {"mensagens": [], "leu": {}})
        if ev == "leu":
            c["leu"][quem] = max(q, c["leu"].get(quem, q))
            continue
        dados = {}
        if cofre and l.get("dados_cifrados"):
            try:
                dados = json.loads(cofre.decifrar(l["dados_cifrados"], _ctx(l)))
            except Exception:    # noqa: BLE001 — linha mexida ou chave trocada: fica a mensagem, sem o texto
                dados = {}
        c["mensagens"].append({"id": _txt(l.get("id")), "quando": q, "quando_txt": q.strftime("%d/%m às %H:%M"),
                               "por": _txt((dados.get("quem") or {}).get("nome")), "pessoa_hmac": quem,
                               "texto": _txt(dados.get("texto")),
                               "pessoas": _lista(l.get("mencoes_pessoas"), HMAC_RE),
                               "areas": _lista(l.get("mencoes_areas"), ES.TORRE_RE)})
        # quem escreve leu o que veio antes
        c["leu"][quem] = max(q, c["leu"].get(quem, q))
    return out


def atual() -> dict:
    """As conversas de agora, com os nomes e os textos decifrados (sem a chave, sem eles)."""
    try:
        cofre = ES._cofre()
    except Recusada:
        cofre = None
    return conversas(ler()["linhas"], cofre)


def para_mim(convs: dict, meu_hmac: str, minhas_torres) -> list[dict]:
    """As menções que ainda não li: [{"objeto", "mensagem", "por_area"}], a mais nova primeiro. Menção à pessoa (o código
    do e-mail) ou a uma área que o setor dela vê (`minhas_torres`: None = todas, o administrador). A minha própria
    mensagem não me avisa."""
    meu = _txt(meu_hmac).lower()
    out = []
    for ob, c in convs.items():
        lido = c["leu"].get(meu) if meu else None
        for m in c["mensagens"]:
            if (meu and m["pessoa_hmac"] == meu) or (lido and m["quando"] <= lido):
                continue
            pessoal = bool(meu) and meu in m["pessoas"]
            areas = [a for a in m["areas"] if minhas_torres is None or a in minhas_torres]
            if pessoal or areas:
                out.append({"objeto": ob, "mensagem": m, "por_area": [] if pessoal else areas})
    # uma linha por conversa: a menção mais nova, com quantas há sem ler
    por_ob = {}
    for x in sorted(out, key=lambda x: x["mensagem"]["quando"], reverse=True):
        if x["objeto"] in por_ob:
            por_ob[x["objeto"]]["n"] += 1
        else:
            por_ob[x["objeto"]] = dict(x, n=1)
    return list(por_ob.values())


def registrar(ob: str, evento: str, usuario, texto: str = "", pessoas=None, areas=None) -> dict:
    """Grava uma mensagem (com as menções) ou o `leu` de quem marcou como lido. A mesma mensagem repetida em seguida pela
    mesma pessoa (o duplo clique, o F5) e o `leu` sem nada novo para ler não gravam outra linha."""
    if evento not in EVENTOS:
        raise Recusada("Ação desconhecida")
    tipo, _, oid = _txt(ob).partition(":")
    if objeto(tipo, oid) != ob:
        raise Recusada("Não achei esta conversa: recarregue a página")
    texto = "\n".join(" ".join(linha.split()) for linha in str(texto or "").strip().splitlines()).strip()
    pessoas = [p for p in dict.fromkeys(_txt(x).lower() for x in (pessoas or [])) if HMAC_RE.fullmatch(p)]
    areas = [a for a in dict.fromkeys(_txt(x).lower() for x in (areas or [])) if ES.TORRE_RE.fullmatch(a)]
    if evento == "mensagem":
        if not texto:
            raise Recusada("Escreva a mensagem")
        if len(texto) > TEXTO_MAX:
            raise Recusada(f"A mensagem passou de {TEXTO_MAX} caracteres")
        if len(pessoas) + len(areas) > MENCOES_MAX:
            raise Recusada(f"Mais de {MENCOES_MAX} menções numa mensagem")
    quem = ES._quem(usuario)
    cofre = ES._cofre()
    with _TRAVA:
        lido = livros.ler(*ES._banco(), LIVRO, ABA)
        c = conversas(lido, cofre).get(ob) or {"mensagens": [], "leu": {}}
        if evento == "mensagem" and c["mensagens"]:
            u = c["mensagens"][-1]
            if u["pessoa_hmac"] == quem["hmac"] and u["texto"] == texto:
                return {}
        if evento == "leu":
            ja = c["leu"].get(quem["hmac"])
            if not any(m["pessoa_hmac"] != quem["hmac"] and (ja is None or m["quando"] > ja) for m in c["mensagens"]):
                return {}
        agora = datetime.now(timezone.utc)
        linha = {"id": "m" + uuid.uuid4().hex[:11],
                 "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z",
                 "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "objeto_tipo": tipo, "objeto_id": oid,
                 "evento": evento, "mencoes_pessoas": ",".join(pessoas) or None, "mencoes_areas": ",".join(areas) or None,
                 "pessoa_id": quem["pessoa_id"], "pessoa_hmac": quem["hmac"]}
        if evento == "mensagem":
            linha["dados_cifrados"] = cofre.cifrar(json.dumps({"quem": {"nome": quem["nome"], "email": quem["email"]},
                                                               "texto": texto}, ensure_ascii=False), _ctx(linha))
        else:
            linha["dados_cifrados"] = None
        base, sessao = ES._banco()
        try:
            livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in lido + [linha]])},
                            base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
        finally:
            limpar()
    return linha


# ── quem pode ser mencionado ─────────────────────────────────────────────────────────────────────────────────────────
def pessoas_mencionaveis() -> list[dict]:
    """[{"hmac", "nome", "setor"}]: quem tem setor hoje (Base → Acessos → Pessoas e setores: a última decisão de cada
    pessoa do Fracttal) e o código do e-mail; o nome vem do pessoal do Fracttal (guardado 1 h, só na memória e na tela,
    como a lista da Engenharia). Só é lida quando alguém digita @ (a tela pede /conversa/pessoas), nunca no carregar."""
    from ..cadastro import fracttal_pessoal as FP
    from ..cadastro import setores as S
    st = S.ler(*ES._banco())
    nome_setor = {s["setor_id"]: s["nome"] for s in S.ativos(st.get("setores") or [])}
    ultima = {}
    for d in sorted(st.get("decisoes") or [], key=lambda x: str(x.get("decidida_em") or "")):
        ultima[str(d.get("fracttal_id"))] = d
    nomes = {str(p.get("id")): p.get("nome") for p in (FP.ler_pessoal().get("pessoas") or [])}
    out = [{"hmac": _txt(d["pessoa_hmac"]).lower(), "nome": nomes[fid], "setor": nome_setor[d["setor_id"]]}
           for fid, d in ultima.items()
           if d.get("pessoa_hmac") and d.get("setor_id") in nome_setor and nomes.get(fid)]
    return sorted(out, key=lambda p: p["nome"].lower())


# ── o sino só lê cópias ──────────────────────────────────────────────────────────────────────────────────────────────
_RENOVANDO: dict = {"thread": None}


def copias() -> tuple[list[dict], list[dict]]:
    """(as linhas das conversas, as linhas dos eventos dos insights) das cópias de 1 minuto, para o sino de toda página.
    Sem cópia ou com a cópia vencida, a leitura começa por trás e o sino usa o que tem: quem foi mencionado vê o número
    sem precisar abrir a Caixa antes, e nenhuma página espera o banco."""
    agora = time.time()
    c, e = _CACHE.get("livro"), ES._CACHE.get("livro")
    velha = any(x is None or not x.get("lido_em") or agora - x["lido_em"] >= TTL_S for x in (c, e))
    if velha and not current_app.config.get("TESTING"):
        t = _RENOVANDO["thread"]
        if t is None or not t.is_alive():
            app = current_app._get_current_object()

            def rodar():
                with app.app_context():
                    for ler_um in (ler, ES.ler):
                        try:
                            ler_um(forcar=True)
                        except Exception:    # noqa: BLE001 — o sino só fica com a cópia de antes
                            current_app.logger.warning("sino: a cópia das conversas não renovou", exc_info=True)
            t = threading.Thread(target=rodar, name="nexus-conversas", daemon=True)
            _RENOVANDO["thread"] = t
            t.start()
    return (c or {}).get("linhas") or [], (e or {}).get("linhas") or []
