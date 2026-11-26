"""O comentário avulso da Performance na ETM de uma usina, sem OS (Levi, 26/11/2026: "Na parte de ETMs, deve ser possível
uma pessoa adicionar um comentário. Daí tem daquela usina, ele já vai para o usuário e o comentário. Não precisa ser OS
alguma, mas é bom ter esse comentário avulso, certo? Para a gente ter um acompanhamento").

Até aqui a gaveta da usina da tela Performance › ETMs só comentava NUMA OS (o comentário da Engenharia, `os_acompanhamento`,
que vai também para a nota da OS no Fracttal). O que é da usina e de nenhuma OS (a estação que a equipe já sabe que está
sem sinal, o cliente avisado, o que se combinou) não tinha onde ficar.

O Nexus é a FONTE: livro `nexus_performance_etm`, registrado no catálogo antes da 1ª gravação (regra 10), com uma aba:
- `fato_comentario_etm_usina`: 1 linha = 1 comentário avulso da Performance na ETM de 1 usina. Só acrescenta.

A usina vai pela chave do nome com que a tela ETMs a mostra (o nome da usina no Fracttal, `usina_chave` = sha1 do nome
normalizado: texto que identifica entra como chave, regra 3) e, quando liga, pelo `usina_id` do cadastro (pelas OS de ETM
dela, `usina_ligada_por`). A API do banco tem LEITURA ABERTA (regra 8): quem fez (nome e e-mail) e o texto vão só CIFRADOS
(o Cofre, a chave do cadastro); a pessoa liga pelo código do e-mail (`pessoa_hmac`).
"""
import hashlib
import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros
from ..engenharia import acompanhamento as AC

LIVRO, NOME_LIVRO = "nexus_performance_etm", "Nexus · os comentários avulsos da Performance nas ETMs das usinas"
ABA = "fato_comentario_etm_usina"
CAB = ("id", "registrado_em", "data_id", "evento", "usina_chave", "usina_id", "usina_ligada_por", "pessoa_hmac",
       "dados_cifrados")
EVENTOS = ("comentario",)
TEXTO_MAX = AC.TEXTO_MAX
TTL_S = 60
PRAZO_S = 8                  # a gaveta lê o livro no clique: com a API do banco pendurada, no máximo isto
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}
Recusada = AC.Recusada
_txt, _int, _quando = AC._txt, AC._int, AC._quando


def limpar() -> None:
    _CACHE.clear()


def chave_usina(nome) -> str:
    """A chave da usina no fato: sha1 do nome com que a tela ETMs a mostra, sem diferença de caixa nem de espaço."""
    t = " ".join(str(nome or "").split()).casefold()
    return hashlib.sha1(t.encode("utf-8")).hexdigest() if t else ""


def _ctx(eid) -> str:
    return f"banco/performance_etm/{eid}/dados"


def _abre(cofre, l: dict) -> dict:
    if not cofre or not l.get("dados_cifrados"):
        return {}
    try:
        return json.loads(cofre.decifrar(_txt(l.get("dados_cifrados")), _ctx(_txt(l.get("id")))))
    except Exception:           # noqa: BLE001 — cifra de outra chave ou adulterada: sai sem texto (a gaveta conta)
        return {}


def _ler_banco(base: str, sessao) -> dict:
    a = livros.abas(base, sessao, LIVRO)
    return {"eventos": livros._linhas(base, sessao, a[ABA]) if ABA in a else []}


class _Curta:
    """A sessão do banco com prazo curto (a mesma das marcações das OS de ETM)."""

    def __init__(self, sessao):
        self._s = sessao

    def get(self, *a, **k):
        k["timeout"] = min(float(k.get("timeout") or PRAZO_S), PRAZO_S)
        return self._s.get(*a, **k)


def ler(forcar: bool = False) -> dict:
    """{"eventos", "lido_em", "erro"}, guardado por 1 minuto. A leitura que falha devolve a última boa com o erro; o livro
    que existe e veio sem a aba é leitura incompleta, não "nenhum comentário"."""
    g = _CACHE.get("livro")
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    f = _CACHE.get("falha")
    if f and not forcar and time.time() - f["em"] < TTL_S:
        return dict(g, erro=f["erro"], velha=True) if g else {"eventos": [], "lido_em": None, "erro": f["erro"]}
    try:
        base, sessao = AC._banco()
        curta = _Curta(sessao)
        d = _ler_banco(base, curta)
        token = current_app.config.get("GRIDCO_SQL_TOKEN")
        if not d["eventos"] and token and livros.existe(LIVRO, base=base, token=token, sessao=curta):
            raise livros.GravacaoRecusada(f"{LIVRO}: o livro existe e a aba dos comentários não veio na leitura")
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a gaveta diz e os comentários das OS seguem
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        _CACHE["falha"] = {"em": time.time(), "erro": erro}
        if g:
            return dict(g, erro=erro, velha=True)
        return {"eventos": [], "lido_em": None, "erro": erro}
    _CACHE.pop("falha", None)
    g = dict(d, lido_em=time.time(), erro="")
    _CACHE["livro"] = g
    return g


def da_usina(eventos: list[dict], nome) -> tuple[list[dict], int]:
    """(os comentários avulsos da usina, o mais novo primeiro: {"nome", "quando", "texto", "iso"}; quantos não abriram)."""
    ch = chave_usina(nome)
    if not ch:
        return [], 0
    cofre = AC._cofre_ou_nada()
    out, ilegiveis = [], 0
    for l in eventos or []:
        if _txt(l.get("usina_chave")) != ch or _txt(l.get("evento")) not in EVENTOS:
            continue
        d = _abre(cofre, l)
        if not _txt(d.get("texto")):
            ilegiveis += 1
            continue
        q = _quando(l.get("registrado_em"))
        out.append({"nome": _txt((d.get("quem") or {}).get("nome")) or "alguém", "texto": _txt(d.get("texto")),
                    "quando": q.astimezone(_BRT).strftime("%d/%m/%Y %H:%M") if q else "",
                    "iso": q.isoformat() if q else "", "_q": q or datetime.min.replace(tzinfo=timezone.utc)})
    out.sort(key=lambda c: c["_q"], reverse=True)
    for c in out:
        c.pop("_q")
    return out, ilegiveis


def texto_do_comentario(texto) -> str:
    t = _txt(texto)
    if not t:
        raise Recusada("Escreva o comentário antes de salvar")
    if len(t) > TEXTO_MAX:
        raise Recusada(f"O comentário passou de {TEXTO_MAX} caracteres")
    return t


def _evento(cofre, quem: dict, usina: dict, texto: str, quando: datetime | None = None) -> dict:
    eid = uuid.uuid4().hex[:12]
    agora = (quando or datetime.now(timezone.utc)).astimezone(timezone.utc)
    dados = {"quem": {"nome": quem["nome"], "email": quem["email"]}, "texto": texto}
    return {"id": eid, "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "evento": "comentario",
            "usina_chave": chave_usina(usina.get("nome")), "usina_id": _int(usina.get("usina_id")),
            "usina_ligada_por": _txt(usina.get("usina_ligada_por")) or None, "pessoa_hmac": quem["hmac"],
            "dados_cifrados": cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(eid))}


def _reler() -> dict:
    """O livro relido do banco agora, sem a cópia. Com o livro no banco, a aba que não veio é leitura incompleta: gravar
    sobre ela apagaria o que há (a troca do livro é integral)."""
    base, sessao = AC._banco()
    lido = _ler_banco(base, sessao)
    if not lido["eventos"] and livros.existe(LIVRO, base=base, token=current_app.config["GRIDCO_SQL_TOKEN"],
                                             sessao=sessao):
        raise livros.GravacaoRecusada(f"{LIVRO}: os comentários não vieram na leitura do banco; não gravo por cima (tente "
                                      "de novo em instantes)")
    return lido


def comentar(usina: dict, texto, usuario, pode: bool) -> dict:
    """Grava o comentário avulso. `usina` = {"nome" (o da tela ETMs), "usina_id", "usina_ligada_por"}."""
    quem = AC._quem(usuario, pode, "comenta na ETM da usina", dono="da Performance")
    t = texto_do_comentario(texto)
    if not chave_usina(usina.get("nome")):
        raise Recusada("Comentário sem a usina: recarregue a página")
    cofre = AC._cofre()
    with _TRAVA:
        lido = _reler()
        novo = _evento(cofre, quem, usina, t)
        base, sessao = AC._banco()
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[e.get(c) for c in CAB] for e in lido["eventos"] + [novo]])},
                        base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
        limpar()
    return novo
