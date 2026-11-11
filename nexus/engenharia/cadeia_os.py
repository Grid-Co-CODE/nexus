"""As OS incluídas à mão na cadeia do Raio X da OS (Levi, 11/11/2026: "um campo na mesma altura de 'A cadeia do chamado',
esse campo será digitável no tamanho de 6 dígitos, dentro dele terá um subtexto de 'Incluir OS' que a pessoa digita a OS e
ela é incluída na cadeia das OSs, a pessoa pode renomear como ficará a nomenclatura dessa OS na cadeia"). No quiz: a OS
incluída aparece SÓ no Raio X da OS em que foi incluída (não vira um grupo).

A cadeia de sempre (a OS e as filhas pelo `id_parent_wo` do Fracttal) não muda: a incluída entra depois dela, com o nome
que a pessoa der ("OS incluída" se não der), e pode ser renomeada ou tirada. Nada vai ao Fracttal.

O livro `nexus_cadeia_os · fato_os_na_cadeia`, registrado no catálogo antes da 1ª gravação (regra 10 de nexus/dados): 1
linha = 1 evento (incluiu, renomeou, tirou) de 1 OS incluída na cadeia de 1 OS. Só acrescenta: renomear e tirar apontam a
inclusão pelo `alvo_id`, e o estado de agora sai dos eventos na ordem da gravação. Em claro: as duas OS (o id do Fracttal e o
nº) e o código de quem fez (`pessoa_hmac`); o nome dado na cadeia e quem fez (nome e e-mail), só cifrados (o Cofre): o nome
é texto livre, e a API do banco tem leitura aberta (regra 8). Quem pode é quem pode mexer na página da OS (`pode`, o mesmo
do status e dos comentários)."""
import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros
from . import acompanhamento as AC

LIVRO, NOME_LIVRO, ABA = "nexus_cadeia_os", "Nexus · OS incluídas na cadeia do Raio X da OS", "fato_os_na_cadeia"
CAB = ("id", "registrado_em", "data_id", "evento", "os_id", "os_folio", "incluida_id", "incluida_folio", "alvo_id",
       "pessoa_hmac", "dados_cifrados")
EVENTOS = ("incluiu", "renomeou", "tirou")
ROTULO_PADRAO = "OS incluída"
ROTULO_MAX = 60
NUMERO = re.compile(r"\d{1,6}")       # o nº da OS: até 6 dígitos (o campo do pedido)
TTL_S = 60
PRAZO_S = 8                           # a página lê o livro no caminho do clique: o banco pendurado não a segura
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}
Recusada = AC.Recusada
_txt, _int = AC._txt, AC._int


def limpar() -> None:
    _CACHE.clear()


def _ctx(eid) -> str:
    return f"banco/cadeia_os/{eid}/dados"


class _Curta:
    def __init__(self, sessao):
        self._s = sessao

    def get(self, *a, **k):
        k["timeout"] = min(float(k.get("timeout") or PRAZO_S), PRAZO_S)
        return self._s.get(*a, **k)


def _ler_banco(base: str, sessao) -> list[dict]:
    a = livros.abas(base, sessao, LIVRO)
    return livros._linhas(base, sessao, a[ABA]) if ABA in a else []


def ler(forcar: bool = False) -> dict:
    """{"eventos", "lido_em", "erro"}, guardado por 1 minuto; a falha também (a página diz que não leu e não deixa
    gravar). O livro que existe e veio sem a aba é leitura incompleta, não "nada"."""
    g = _CACHE.get("livro")
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    f = _CACHE.get("falha")
    if f and not forcar and time.time() - f["em"] < TTL_S:
        return dict(g, erro=f["erro"], velha=True) if g else {"eventos": [], "lido_em": None, "erro": f["erro"]}
    try:
        base, sessao = AC._banco()
        curta = _Curta(sessao)
        eventos = _ler_banco(base, curta)
        token = current_app.config.get("GRIDCO_SQL_TOKEN")
        if not eventos and token and livros.existe(LIVRO, base=base, token=token, sessao=curta):
            raise livros.GravacaoRecusada(f"{LIVRO}: o livro existe e a aba dos eventos não veio na leitura")
    except Exception as ex:      # noqa: BLE001 — banco fora: a página diz e não deixa gravar
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        _CACHE["falha"] = {"em": time.time(), "erro": erro}
        return dict(g, erro=erro, velha=True) if g else {"eventos": [], "lido_em": None, "erro": erro}
    _CACHE.pop("falha", None)
    g = {"eventos": eventos, "lido_em": time.time(), "erro": ""}
    _CACHE["livro"] = g
    return g


def _abre(cofre, l: dict) -> dict:
    if not cofre or not l.get("dados_cifrados"):
        return {}
    try:
        return json.loads(cofre.decifrar(_txt(l.get("dados_cifrados")), _ctx(_txt(l.get("id")))))
    except Exception:           # noqa: BLE001 — cifra de outra chave ou mexida: sai com o nome padrão
        return {}


def incluidas(eventos: list[dict], os_id, cofre=None) -> list[dict]:
    """As OS incluídas hoje na cadeia da OS `os_id` (o id do Fracttal), na ordem em que entraram:
    [{"id" (da inclusão), "folio", "incluida_id", "rotulo"}]."""
    alvo = _txt(_int(os_id))
    ativas: dict[str, dict] = {}
    for l in eventos or []:
        if _txt(_int(l.get("os_id"))) != alvo:
            continue
        ev = _txt(l.get("evento"))
        if ev == "incluiu":
            d = _abre(cofre, l)
            ativas[_txt(l.get("id"))] = {"id": _txt(l.get("id")), "folio": _txt(l.get("incluida_folio")),
                                         "incluida_id": _int(l.get("incluida_id")),
                                         "rotulo": _txt(d.get("rotulo")) or ROTULO_PADRAO}
        elif ev == "renomeou" and _txt(l.get("alvo_id")) in ativas:
            ativas[_txt(l.get("alvo_id"))]["rotulo"] = _txt(_abre(cofre, l).get("rotulo")) or ROTULO_PADRAO
        elif ev == "tirou":
            ativas.pop(_txt(l.get("alvo_id")), None)
    return list(ativas.values())


def do_banco(os_id) -> tuple[list[dict], str]:
    """(as incluídas na cadeia desta OS, o erro de leitura ou ""), para a página."""
    lido = ler()
    erro = "" if lido.get("lido_em") else (lido.get("erro") or "").split(":")[0]
    return incluidas(lido["eventos"], os_id, AC._cofre_ou_nada()), erro


def rotulo(texto) -> str:
    t = " ".join(_txt(texto).split())
    if len(t) > ROTULO_MAX:
        raise Recusada(f"O nome na cadeia passou de {ROTULO_MAX} caracteres")
    return t or ROTULO_PADRAO


def numero(texto) -> str:
    t = _txt(texto).lstrip("0") or _txt(texto)
    if not NUMERO.fullmatch(_txt(texto)):
        raise Recusada("Digite o nº da OS, só números (até 6 dígitos)")
    return t


def _evento(cofre, evento: str, quem: dict, os_: dict, *, incluida_id=None, incluida_folio="", alvo_id=None,
            rotulo_: str = "") -> dict:
    eid = uuid.uuid4().hex[:12]
    agora = datetime.now(timezone.utc)
    dados = {"quem": {"nome": quem["nome"], "email": quem["email"]}}
    if rotulo_:
        dados["rotulo"] = rotulo_
    return {"id": eid, "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "evento": evento,
            "os_id": _int(os_.get("wid")), "os_folio": _txt(os_.get("folio")), "incluida_id": _int(incluida_id),
            "incluida_folio": _txt(incluida_folio) or None, "alvo_id": alvo_id, "pessoa_hmac": quem["hmac"],
            "dados_cifrados": cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(eid))}


def _reler() -> list[dict]:
    """O livro relido agora, sem a cópia: gravar sobre uma leitura incompleta apagaria o que há."""
    base, sessao = AC._banco()
    eventos = _ler_banco(base, sessao)
    if not eventos and livros.existe(LIVRO, base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao):
        raise livros.GravacaoRecusada(f"{LIVRO}: os eventos não vieram na leitura do banco; não gravo por cima (tente "
                                      "de novo em instantes)")
    return eventos


def _publicar(eventos: list[dict]) -> None:
    base, sessao = AC._banco()
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[e.get(c) for c in CAB] for e in eventos])},
                    base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
    limpar()


def _gravar(os_: dict, usuario, pode: bool, faz) -> dict:
    quem = AC._quem(usuario, pode, "muda a cadeia da OS")
    if not _int(os_.get("wid")):
        raise Recusada("OS sem o id do Fracttal: recarregue a página")
    cofre = AC._cofre()
    with _TRAVA:
        eventos = _reler()
        ativas = incluidas(eventos, os_["wid"], cofre)
        novo = faz(cofre, quem, ativas)
        _publicar(eventos + [novo])
    return novo


def incluir(os_: dict, folio_incluida, incluida_id, usuario, pode: bool, rotulo_texto="") -> dict:
    """Inclui a OS `folio_incluida` (conferida no Fracttal por quem chama: `incluida_id`) na cadeia da OS `os_`."""
    n = numero(folio_incluida)
    r = rotulo(rotulo_texto)
    if n == _txt(os_.get("folio")):
        raise Recusada(f"A OS {n} é a própria OS desta página")

    def faz(cofre, quem, ativas):
        if any(a["folio"] == n for a in ativas):
            raise Recusada(f"A OS {n} já está na cadeia")
        return _evento(cofre, "incluiu", quem, os_, incluida_id=incluida_id, incluida_folio=n, rotulo_=r)
    return _gravar(os_, usuario, pode, faz)


def _da_cadeia(ativas: list[dict], inclusao_id) -> dict:
    a = next((x for x in ativas if x["id"] == _txt(inclusao_id)), None)
    if a is None:
        raise Recusada("Essa OS não está mais na cadeia: recarregue a página")
    return a


def renomear(os_: dict, inclusao_id, rotulo_texto, usuario, pode: bool) -> dict:
    r = rotulo(rotulo_texto)

    def faz(cofre, quem, ativas):
        a = _da_cadeia(ativas, inclusao_id)
        if a["rotulo"] == r:
            raise Recusada("Nada mudou")
        return _evento(cofre, "renomeou", quem, os_, incluida_id=a["incluida_id"], incluida_folio=a["folio"],
                       alvo_id=a["id"], rotulo_=r)
    return _gravar(os_, usuario, pode, faz)


def tirar(os_: dict, inclusao_id, usuario, pode: bool) -> dict:
    def faz(cofre, quem, ativas):
        a = _da_cadeia(ativas, inclusao_id)
        return _evento(cofre, "tirou", quem, os_, incluida_id=a["incluida_id"], incluida_folio=a["folio"],
                       alvo_id=a["id"])
    return _gravar(os_, usuario, pode, faz)
