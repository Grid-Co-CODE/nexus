"""Quem assumiu, concluiu, notificou e respondeu cada insight (03/11/2026): o livro `nexus_insights ·
fato_evento_insight`.

O Nexus é a FONTE: 1 linha por evento sobre 1 insight, só acrescenta. Os eventos:
- `assumiu`, `concluiu`, `reabriu`: o dono do insight (vale o último);
- `notificou`: quem gerencia avisa uma ou mais áreas (as torres em `para`) e pede retorno (Levi, 03/11/2026: "o manager
  quer algo como notificar as áreas e saber como está e receber retornos dessas áreas");
- `respondeu`: a área notificada (a torre em `para`, uma só) dá o retorno, com o status (`status_retorno`: recebido,
  andamento, resolvido) e o texto (vale o último de cada área).

Em claro: o id do insight (a regra e o objeto: "N01:16702"), a regra, a torre dona, o evento, as áreas, o status do
retorno, o dia e a pessoa por código; o nome de quem fez, a mensagem e o retorno, cifrados (o Cofre, como as Sugestões):
o banco tem leitura aberta. Registrado no catálogo antes da 1ª gravação (nexus/dados/CLAUDE.md, regra 10).
"""
import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros

LIVRO, NOME_LIVRO, ABA = "nexus_insights", "Nexus · insights (dono, notificações e retornos)", "fato_evento_insight"
CAB = ("id", "registrado_em", "data_id", "insight_id", "regra", "torre", "evento", "para", "status_retorno",
       "pessoa_id", "pessoa_hmac", "dados_cifrados")
EVENTOS = {"assumiu": "Assumido", "concluiu": "Concluído", "reabriu": "Reaberto", "notificou": "Notificado",
           "respondeu": "Respondido"}
DONO = ("assumiu", "concluiu", "reabriu")
# o retorno da área notificada; "pendente" é a área notificada que ainda não respondeu (não se grava)
RETORNOS = {"pendente": ("Aguardando retorno", "alerta"), "recebido": ("Recebido", "info"),
            "andamento": ("Em andamento", "info"), "resolvido": ("Resolvido", "ok")}
INSIGHT_RE = re.compile(r"[A-Z]\d{2}:[^\s]{1,160}")
TORRE_RE = re.compile(r"[a-z][a-z0-9-]{1,30}")
TEXTO_MAX = 500
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê."""


def limpar() -> None:
    _CACHE.clear()


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _banco():
    from ..campo import visao
    return visao._base(), visao._sessao()


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela o nome não vai cifrado")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _ctx(l: dict) -> str:
    return (f"banco/insights/{_txt(l.get('id'))}/{_txt(l.get('insight_id'))}/{_txt(l.get('evento'))}/"
            f"{_txt(l.get('para')) or '-'}/{_txt(l.get('pessoa_hmac')) or '-'}")


def _quem(usuario) -> dict:
    email = str((usuario or {}).get("email") or "").strip().lower()
    if not email:
        raise Recusada("Entre com o seu login (Microsoft ou Fracttal): a senha de administrador não diz quem é a pessoa")
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    cfg = current_app.config
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not codigo:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    nome = " ".join(str((usuario or {}).get("nome") or "").split()) or email
    from ..campo import visao
    try:
        pid = visao.pessoa_do_login(email, nome)
    except Exception:            # noqa: BLE001 — sem cadastro: fica o código do e-mail
        pid = None
    return {"email": email, "nome": nome, "hmac": codigo.lower(), "pessoa_id": pid}


def ler(forcar: bool = False) -> dict:
    """{"linhas", "erro"}, cópia de 1 minuto. Leitura que falha devolve a última boa com o erro."""
    agora = time.time()
    g = _CACHE.get("livro")
    if g and not forcar and agora - g["lido_em"] < TTL_S:
        return g
    try:
        linhas = livros.ler(*_banco(), LIVRO, ABA)
    except Exception as ex:      # noqa: BLE001 — banco fora: as telas seguem sem o estado
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(g, erro=erro) if g else {"linhas": [], "lido_em": None, "erro": erro}
    _CACHE["livro"] = {"linhas": linhas, "lido_em": agora, "erro": ""}
    return _CACHE["livro"]


def _quando(v):
    try:
        return datetime.fromisoformat(_txt(v).replace("Z", "+00:00")).astimezone(_BRT)
    except ValueError:
        return None


def _areas(v) -> list[str]:
    return [t for t in (x.strip() for x in _txt(v).split(",")) if TORRE_RE.fullmatch(t)]


def estado(linhas: list[dict], cofre=None) -> dict:
    """{insight_id: {"evento" (o último de dono, ou ""), "rotulo", "quando_txt", "por", "pessoa_hmac", "nota",
    "pedidos": {torre: {"pedido_em", "pedido_por", "mensagem", "status", "retorno", "retorno_por", "retorno_em"}}}},
    na ordem da gravação. Evento desconhecido fica fora."""
    out = {}
    for l in linhas:
        iid, ev = _txt(l.get("insight_id")), _txt(l.get("evento"))
        if not INSIGHT_RE.fullmatch(iid) or ev not in EVENTOS:
            continue
        dados = {}
        if cofre and l.get("dados_cifrados"):
            try:
                dados = json.loads(cofre.decifrar(l["dados_cifrados"], _ctx(l)))
            except Exception:    # noqa: BLE001 — linha mexida ou chave trocada: fica o evento, sem o texto
                dados = {}
        q = _quando(l.get("registrado_em"))
        quando = q.strftime("%d/%m às %H:%M") if q else ""
        por = _txt((dados.get("quem") or {}).get("nome"))
        e = out.setdefault(iid, {"evento": "", "rotulo": "", "quando_txt": "", "por": "", "pessoa_hmac": "", "nota": "",
                                 "pedidos": {}})
        if ev in DONO:
            e.update(evento=ev, rotulo=EVENTOS[ev], quando_txt=quando, por=por,
                     pessoa_hmac=_txt(l.get("pessoa_hmac")).lower(), nota=_txt(dados.get("nota")))
        elif ev == "notificou":
            for t in _areas(l.get("para")):
                e["pedidos"][t] = {"pedido_em": quando, "pedido_por": por, "mensagem": _txt(dados.get("nota")),
                                   "status": "pendente", "retorno": "", "retorno_por": "", "retorno_em": ""}
        else:                    # respondeu: a área (uma só) que foi notificada
            t = (_areas(l.get("para")) or [""])[0]
            st = _txt(l.get("status_retorno"))
            if t in e["pedidos"] and st in RETORNOS and st != "pendente":
                e["pedidos"][t].update(status=st, retorno=_txt(dados.get("nota")), retorno_por=por, retorno_em=quando)
    return out


def atual() -> dict:
    """O estado de agora, com os nomes e os textos decifrados (sem a chave, sem eles)."""
    try:
        cofre = _cofre()
    except Recusada:
        cofre = None
    return estado(ler()["linhas"], cofre)


def registrar(insight: dict, evento: str, usuario, nota: str = "", para=None, status: str = "") -> dict:
    """Grava um evento sobre um insight que o motor apontou. `para` = as áreas (torres) no `notificou`, ou a área que
    responde no `respondeu`; `status` = o retorno no `respondeu`. A mesma coisa repetida (o duplo clique, o F5) não
    grava outra linha: o mesmo dono, a área já notificada e ainda sem resposta, o mesmo retorno."""
    if evento not in EVENTOS:
        raise Recusada("Ação desconhecida")
    iid = _txt(insight.get("id"))
    if not INSIGHT_RE.fullmatch(iid):
        raise Recusada("Não achei este insight: recarregue a página")
    nota = " ".join(str(nota or "").split())
    if len(nota) > TEXTO_MAX:
        raise Recusada(f"O texto passou de {TEXTO_MAX} caracteres")
    areas = [t for t in dict.fromkeys(para or []) if TORRE_RE.fullmatch(_txt(t))]
    if evento == "notificou" and not areas:
        raise Recusada("Escolha ao menos uma área para notificar")
    if evento == "respondeu":
        if len(areas) != 1:
            raise Recusada("Diga qual área está respondendo")
        if status not in RETORNOS or status == "pendente":
            raise Recusada("Escolha Recebido, Em andamento ou Resolvido")
    quem = _quem(usuario)
    cofre = _cofre()
    with _TRAVA:
        lido = livros.ler(*_banco(), LIVRO, ABA)
        e = estado(lido, cofre).get(iid) or {"evento": "", "pedidos": {}}
        if evento in DONO and e["evento"] == evento:
            return {}
        if evento == "notificou":
            areas = [t for t in areas if (e["pedidos"].get(t) or {}).get("status") in (None, "resolvido")]
            if not areas:
                return {}
        if evento == "respondeu":
            p = e["pedidos"].get(areas[0])
            if not p:
                raise Recusada("Esta área não foi notificada sobre este insight")
            if p["status"] == status and p["retorno"] == nota:
                return {}
        agora = datetime.now(timezone.utc)
        linha = {"id": "i" + uuid.uuid4().hex[:11],
                 "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z",
                 "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "insight_id": iid,
                 "regra": _txt(insight.get("regra")), "torre": _txt(insight.get("torre")), "evento": evento,
                 "para": ",".join(areas) or None, "status_retorno": status if evento == "respondeu" else None,
                 "pessoa_id": quem["pessoa_id"], "pessoa_hmac": quem["hmac"]}
        linha["dados_cifrados"] = cofre.cifrar(json.dumps({"quem": {"nome": quem["nome"], "email": quem["email"]},
                                                           "nota": nota}, ensure_ascii=False), _ctx(linha))
        base, sessao = _banco()
        try:
            livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in lido + [linha]])},
                            base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
        finally:
            limpar()
    return linha
