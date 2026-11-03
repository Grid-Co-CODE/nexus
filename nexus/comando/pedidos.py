"""O pedido entre áreas, com prazo, e o tempo de resposta de cada área (Fase 3 dos setores conversando, 03/11/2026): o
livro `nexus_pedidos · fato_pedido_area`.

Levi, 03/11/2026: "o manager quer algo como notificar as áreas e saber como está e receber retornos dessas áreas"; e,
na Fase 3, o prazo: "Quem pede sempre escolhe" (sem prazo padrão) e o pedido vale para o insight, a OS e a usina.

O Nexus é a FONTE: 1 linha por evento, só acrescenta. Os eventos:
- `pediu`: alguém pede retorno a uma área (a torre em `torre`) sobre um objeto (`insight:R07:2`, `os:16702`, `usina:12`),
  com o prazo (o dia, em `prazo`). Um pedido por área: quem pede a três áreas grava três linhas, cada uma com o seu
  `pedido_id`, e cada área responde e é medida sozinha;
- `respondeu`: a área pedida dá o retorno (`status_retorno`: recebido, andamento, resolvido) com o texto. Vale o último;
  o tempo até a 1ª resposta é o do 1º `respondeu`, e o tempo até resolver, o do 1º `resolvido`.

No prazo = resolvido até o fim do dia do prazo (Brasília). Atrasado = aberto depois do dia do prazo.

Em claro: o objeto, a área, o evento, o status, o prazo, o dia e a pessoa por código; o nome de quem fez, a mensagem e o
retorno, só cifrados (o Cofre): o banco tem leitura aberta. Registrado no catálogo antes da 1ª gravação
(nexus/dados/CLAUDE.md, regra 10). Até 03/11/2026 o notificar e o responder moravam no livro dos insights, que nunca
gravou nenhum (conferido no banco antes da troca).
"""
import json
import re
import statistics
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from ..dados import livros
from . import conversa as CV
from . import estado as ES

LIVRO, NOME_LIVRO, ABA = "nexus_pedidos", "Nexus · pedidos entre áreas, com prazo", "fato_pedido_area"
CAB = ("id", "registrado_em", "data_id", "pedido_id", "objeto_tipo", "objeto_id", "evento", "torre", "status_retorno",
       "prazo", "pessoa_id", "pessoa_hmac", "dados_cifrados")
EVENTOS = ("pediu", "respondeu")
RETORNOS = ES.RETORNOS
PEDIDO_RE = re.compile(r"p[0-9a-f]{11}")
PRAZO_MAX_DIAS = 365
TEXTO_MAX = 500
AREAS_MAX = 12
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}

Recusada = ES.Recusada


def limpar() -> None:
    _CACHE.clear()


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def hoje() -> date:
    return datetime.now(_BRT).date()


def _dia(v) -> date | None:
    try:
        return date.fromisoformat(_txt(v)[:10])
    except ValueError:
        return None


def _ctx(l: dict) -> str:
    return (f"banco/pedidos/{_txt(l.get('id'))}/{_txt(l.get('pedido_id'))}/{_txt(l.get('evento'))}/"
            f"{_txt(l.get('torre')) or '-'}/{_txt(l.get('pessoa_hmac')) or '-'}")


def ler(forcar: bool = False) -> dict:
    """{"linhas", "erro"}, cópia de 1 minuto. Leitura que falha devolve a última boa com o erro."""
    agora = time.time()
    g = _CACHE.get("livro")
    if g and not forcar and agora - g["lido_em"] < TTL_S:
        return g
    try:
        linhas = livros.ler(*ES._banco(), LIVRO, ABA)
    except Exception as ex:      # noqa: BLE001 — banco fora: as telas seguem sem os pedidos
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(g, erro=erro) if g else {"linhas": [], "lido_em": None, "erro": erro}
    _CACHE["livro"] = {"linhas": linhas, "lido_em": agora, "erro": ""}
    return _CACHE["livro"]


def situacao(p: dict, dia: date) -> tuple[str, str, str]:
    """(chave, rótulo, tom) do prazo de um pedido: atrasado, vence hoje, no prazo; e, resolvido, se foi no prazo."""
    prazo = p["prazo"]
    if p["status"] == "resolvido":
        if prazo and p["resolvido_em"] and p["resolvido_em"].date() > prazo:
            return "resolvido_fora", "Resolvido fora do prazo", "alerta"
        return "resolvido", "Resolvido no prazo", "ok"
    if prazo is None:
        return "sem_prazo", "Sem prazo", "info"
    falta = (prazo - dia).days
    if falta < 0:
        return "atrasado", f"Atrasado {-falta} {'dia' if falta == -1 else 'dias'}", "critico"
    if falta == 0:
        return "hoje", "Vence hoje", "alerta"
    return "no_prazo", f"Vence {prazo.strftime('%d/%m')}", "info"


def pedidos(linhas: list[dict], cofre=None, dia: date | None = None) -> dict:
    """{pedido_id: {"id", "objeto", "torre", "prazo", "pedido_em", "pedido_por", "pedido_hmac", "mensagem", "status",
    "retorno", "retorno_por", "retorno_em", "primeira_resposta_em", "resolvido_em", "situacao", "sit_rotulo", "sit_tom"}},
    na ordem da gravação. Linha mexida (objeto, evento ou pedido fora do padrão) fica fora; resposta a pedido que não
    existe também."""
    dia = dia or hoje()
    out = {}
    for l in linhas:
        ob, ev = CV.objeto(l.get("objeto_tipo"), l.get("objeto_id")), _txt(l.get("evento"))
        pid, torre = _txt(l.get("pedido_id")), _txt(l.get("torre")).lower()
        q = ES._quando(l.get("registrado_em"))
        if not ob or ev not in EVENTOS or not PEDIDO_RE.fullmatch(pid) or not ES.TORRE_RE.fullmatch(torre) or q is None:
            continue
        dados = {}
        if cofre and l.get("dados_cifrados"):
            try:
                dados = json.loads(cofre.decifrar(l["dados_cifrados"], _ctx(l)))
            except Exception:    # noqa: BLE001 — linha mexida ou chave trocada: fica o evento, sem o texto
                dados = {}
        por = _txt((dados.get("quem") or {}).get("nome"))
        if ev == "pediu":
            if pid in out:
                continue
            out[pid] = {"id": pid, "objeto": ob, "torre": torre, "prazo": _dia(l.get("prazo")), "pedido_em": q,
                        "pedido_por": por, "pedido_hmac": _txt(l.get("pessoa_hmac")).lower(),
                        "mensagem": _txt(dados.get("nota")), "status": "pendente", "retorno": "", "retorno_por": "",
                        "retorno_em": None, "primeira_resposta_em": None, "resolvido_em": None}
            continue
        p = out.get(pid)
        st = _txt(l.get("status_retorno"))
        if p is None or p["torre"] != torre or st not in RETORNOS or st == "pendente":
            continue
        p.update(status=st, retorno=_txt(dados.get("nota")), retorno_por=por, retorno_em=q)
        p["primeira_resposta_em"] = p["primeira_resposta_em"] or q
        if st == "resolvido" and p["resolvido_em"] is None:
            p["resolvido_em"] = q
        if st != "resolvido":
            p["resolvido_em"] = None             # reaberto pela área: volta a contar
    for p in out.values():
        p["situacao"], p["sit_rotulo"], p["sit_tom"] = situacao(p, dia)
    return out


def atual() -> dict:
    """Os pedidos de agora, com os nomes e os textos decifrados (sem a chave, sem eles)."""
    try:
        cofre = ES._cofre()
    except Recusada:
        cofre = None
    return pedidos(ler()["linhas"], cofre)


def por_objeto(peds: dict) -> dict:
    """{objeto: [pedidos]}, o mais antigo primeiro."""
    out = {}
    for p in peds.values():
        out.setdefault(p["objeto"], []).append(p)
    return out


def ordem(p: dict) -> tuple:
    """O mais urgente primeiro: atrasado (o mais velho antes), vence hoje, no prazo (pelo prazo), sem prazo, resolvido."""
    peso = {"atrasado": 0, "hoje": 1, "no_prazo": 2, "sem_prazo": 3}.get(p["situacao"], 4)
    return peso, p["prazo"] or date.max, p["pedido_em"]


def prazo_valido(texto, dia: date | None = None) -> date:
    """O prazo escolhido por quem pede (Levi, 03/11/2026: "Quem pede sempre escolhe"): de hoje a um ano."""
    dia = dia or hoje()
    p = _dia(texto)
    if p is None:
        raise Recusada("Escolha o prazo do pedido")
    if p < dia:
        raise Recusada("O prazo já passou: escolha hoje ou um dia depois")
    if (p - dia).days > PRAZO_MAX_DIAS:
        raise Recusada("O prazo passou de um ano")
    return p


def _gravar(lido: list[dict], novas: list[dict]) -> None:
    base, sessao = ES._banco()
    try:
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in lido + novas])},
                        base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
    finally:
        limpar()


def _linha(agora, evento, quem, cofre, nota, **campos) -> dict:
    linha = {"id": "e" + uuid.uuid4().hex[:11],
             "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z",
             "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "evento": evento,
             "pessoa_id": quem["pessoa_id"], "pessoa_hmac": quem["hmac"], **campos}
    linha["dados_cifrados"] = cofre.cifrar(json.dumps({"quem": {"nome": quem["nome"], "email": quem["email"]},
                                                       "nota": nota}, ensure_ascii=False), _ctx(linha))
    return linha


def pedir(ob: str, areas, prazo, usuario, nota: str = "") -> list[dict]:
    """Pede retorno às áreas sobre um objeto, com o prazo escolhido. A área que já tem pedido aberto sobre o mesmo objeto
    não ganha outro (o duplo clique, o F5); devolve as linhas gravadas (vazio = nada novo)."""
    tipo, _, oid = _txt(ob).partition(":")
    if CV.objeto(tipo, oid) != ob:
        raise Recusada("Não achei este objeto: recarregue a página")
    areas = [a for a in dict.fromkeys(_txt(x).lower() for x in (areas or [])) if ES.TORRE_RE.fullmatch(a)]
    if not areas:
        raise Recusada("Escolha ao menos uma área")
    if len(areas) > AREAS_MAX:
        raise Recusada(f"Mais de {AREAS_MAX} áreas num pedido")
    prazo = prazo_valido(prazo)
    nota = " ".join(str(nota or "").split())
    if len(nota) > TEXTO_MAX:
        raise Recusada(f"O texto passou de {TEXTO_MAX} caracteres")
    quem = ES._quem(usuario)
    cofre = ES._cofre()
    with _TRAVA:
        lido = livros.ler(*ES._banco(), LIVRO, ABA)
        abertas = {p["torre"] for p in pedidos(lido, cofre).values() if p["objeto"] == ob and p["status"] != "resolvido"}
        agora = datetime.now(timezone.utc)
        novas = [_linha(agora, "pediu", quem, cofre, nota, pedido_id="p" + uuid.uuid4().hex[:11], objeto_tipo=tipo,
                        objeto_id=oid, torre=a, status_retorno=None, prazo=prazo.isoformat())
                 for a in areas if a not in abertas]
        if novas:
            _gravar(lido, novas)
    return novas


def responder(pedido_id: str, status: str, usuario, nota: str = "", minhas_torres=None) -> dict:
    """A área pedida dá o retorno. `minhas_torres` = as torres que o setor de quem responde vê (None = todas, o
    administrador): só quem é da área responde por ela. O mesmo retorno repetido não grava outra linha."""
    pid = _txt(pedido_id)
    if not PEDIDO_RE.fullmatch(pid):
        raise Recusada("Não achei este pedido: recarregue a página")
    if status not in RETORNOS or status == "pendente":
        raise Recusada("Escolha Recebido, Em andamento ou Resolvido")
    nota = " ".join(str(nota or "").split())
    if len(nota) > TEXTO_MAX:
        raise Recusada(f"O texto passou de {TEXTO_MAX} caracteres")
    quem = ES._quem(usuario)
    cofre = ES._cofre()
    with _TRAVA:
        lido = livros.ler(*ES._banco(), LIVRO, ABA)
        p = pedidos(lido, cofre).get(pid)
        if p is None:
            raise Recusada("Não achei este pedido: recarregue a página")
        if minhas_torres is not None and p["torre"] not in minhas_torres:
            raise Recusada("Só quem é da área pedida responde por ela")
        if p["status"] == status and p["retorno"] == nota:
            return {}
        tipo, _, oid = p["objeto"].partition(":")
        linha = _linha(datetime.now(timezone.utc), "respondeu", quem, cofre, nota, pedido_id=pid, objeto_tipo=tipo,
                       objeto_id=oid, torre=p["torre"], status_retorno=status, prazo=p["prazo"].isoformat()
                       if p["prazo"] else None)
        _gravar(lido, [linha])
    return linha


# ── o tempo de resposta de cada área ─────────────────────────────────────────────────────────────────────────────────
def _horas(a, b) -> float | None:
    return (b - a).total_seconds() / 3600 if a and b else None


def _mediana(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def painel(peds: dict) -> list[dict]:
    """Uma linha por área pedida: quantos pedidos, abertos, atrasados agora, resolvidos e quantos no prazo, e a mediana
    das horas até a 1ª resposta e até resolver. A mais atrasada primeiro."""
    por = {}
    for p in peds.values():
        por.setdefault(p["torre"], []).append(p)
    out = []
    for torre, ps in por.items():
        resolvidos = [p for p in ps if p["status"] == "resolvido"]
        no_prazo = sum(1 for p in resolvidos if p["situacao"] == "resolvido")
        out.append({"torre": torre, "total": len(ps), "abertos": sum(1 for p in ps if p["status"] != "resolvido"),
                    "sem_resposta": sum(1 for p in ps if p["status"] == "pendente"),
                    "atrasados": sum(1 for p in ps if p["situacao"] == "atrasado"),
                    "resolvidos": len(resolvidos), "no_prazo": no_prazo,
                    "pct_no_prazo": round(100 * no_prazo / len(resolvidos)) if resolvidos else None,
                    "h_resposta": _mediana(_horas(p["pedido_em"], p["primeira_resposta_em"]) for p in ps),
                    "h_resolver": _mediana(_horas(p["pedido_em"], p["resolvido_em"]) for p in resolvidos)})
    return sorted(out, key=lambda x: (-x["atrasados"], -x["abertos"], x["torre"]))


def duracao(h: float | None) -> str:
    """As horas em palavras curtas: "40 min", "5 h", "2,5 dias"."""
    if h is None:
        return "sem dado"
    if h < 1:
        return f"{max(1, round(h * 60))} min"
    if h < 48:
        return f"{h:.0f} h" if h >= 10 else f"{h:.1f} h".replace(".", ",")
    return f"{h / 24:.1f} dias".replace(".", ",")
