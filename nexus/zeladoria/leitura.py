"""A leitura dos três livros da zeladoria para a torre: decifra, devolve no tipo certo e filtra como o Radar pedia.

Até a troca a torre só lê (desenho: docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md). O estado inteiro
fica em memória por 5 minutos: o clone pede cerca de 36 tabelas ao abrir, e cada uma sai daqui, sem ir ao banco de novo.

Duas regras da casa valem aqui:
- **Número pela metade não vai para a tela.** Se um livro, uma aba ou a aba `atualizacao` falta, ou se a contagem lida
  difere da que a cópia gravou, o estado é `CopiaAusente`. A tela diz que a cópia não está lá e não mostra um Radar
  vazio como se não houvesse dado.
- **Quem não está aprovado no Radar só vê a própria linha de `perfis`**, como no RLS do Supabase. A pessoa é casada
  pelo e-mail do login do Nexus. O administrador do Nexus sem linha vale como HEAD aprovado.
"""
import hashlib
import threading
import time

from flask import current_app

from ..cadastro.cifra import CifraErro, Cofre
from ..dados import livros
from . import guardar
from . import tabelas as T

CACHE_S = 300
LIVROS = (T.LIVRO_APP, T.LIVRO_FRACTTAL, T.LIVRO_HISTORICO)
ADMIN_ID = "nexus-admin"

_TRAVA = threading.Lock()
_CACHE = {"em": 0.0, "estado": None}


class CopiaAusente(RuntimeError):
    """A cópia do Radar não está inteira no banco: a tela avisa em vez de mostrar dado pela metade."""


def limpar() -> None:
    with _TRAVA:
        _CACHE.update(em=0.0, estado=None)


def _sessao():
    s = current_app.extensions.get("nexus_dados_sessao")
    if s is None and current_app.config.get("TESTING"):
        raise CopiaAusente("teste sem banco")         # teste nunca vai à rede
    if s is None:
        import requests
        s = requests.Session()
    return s


def _base(config) -> str:
    from ..cadastro.ligacoes import BASE_API
    return (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def _ler(config) -> dict:
    try:
        cofre = Cofre(config.get("NEXUS_CHAVE_CADASTRO") or "")
    except CifraErro:
        raise CopiaAusente("a chave do cadastro (NEXUS_CHAVE_CADASTRO) falta neste Nexus") from None
    base, sessao = _base(config), _sessao()
    abas_lidas, copiado_em, exportado_em = {}, None, None
    for livro in LIVROS:
        ids = livros.abas(base, sessao, livro)
        if "atualizacao" not in ids:
            raise CopiaAusente(f"a cópia do Radar ainda não foi feita ({livro} não está no banco)")
        tipos, chaves, origem = {}, {}, {}
        # `_linhas` (e não `ler`): uma listagem do banco por livro, não uma por aba
        for l in livros._linhas(base, sessao, ids["atualizacao"]):
            aba = str(l.get("aba") or "")
            tipos.setdefault(aba, {})[str(l.get("coluna"))] = str(l.get("tipo_pg") or "text")
            chaves[aba] = str(l.get("chave") or "id")
            origem[aba] = int(float(l.get("linhas_origem") or 0))
            copiado_em, exportado_em = l.get("copiado_em") or copiado_em, l.get("exportado_em") or exportado_em
        for aba in (a for a, lv in T.TABELAS.items() if lv == livro):
            if aba not in ids or aba not in tipos:
                raise CopiaAusente(f"a cópia do Radar está incompleta: falta {aba}")
            linhas = livros._linhas(base, sessao, ids[aba])
            if len(linhas) != origem[aba]:
                raise CopiaAusente(f"a cópia do Radar está pela metade: {aba} tem {len(linhas)} de {origem[aba]}")
            abas_lidas[aba] = guardar.de_aba(aba, tipos[aba], linhas, cofre, chaves[aba])
    return {"abas": abas_lidas, "copiado_em": copiado_em, "exportado_em": exportado_em}


def estado(config) -> dict:
    """{"abas": {aba: [linha]}, "copiado_em", "exportado_em"}, com cache de CACHE_S. CopiaAusente sem a cópia inteira."""
    with _TRAVA:
        if _CACHE["estado"] is not None and time.time() - _CACHE["em"] < CACHE_S:
            return _CACHE["estado"]
        est = _ler(config)
        _CACHE.update(em=time.time(), estado=est)
        return est


def _email(v) -> str:
    return str(v or "").strip().lower()


def quem_sou(est: dict, usuario: dict | None, admin: bool) -> dict:
    """{"id", "email", "papel", "status"} da pessoa do login do Nexus, no `perfis` do Radar."""
    email_login = str((usuario or {}).get("email") or "").strip()
    alvo = _email(email_login)
    for p in est["abas"].get("perfis", []):
        if alvo and _email(p.get("email")) == alvo:
            return {"id": p.get("user_id"), "email": p.get("email"), "papel": p.get("papel"), "status": p.get("status")}
    if admin:
        return {"id": ADMIN_ID, "email": email_login or "administrador", "papel": "HEAD", "status": "aprovado"}
    return {"id": "nexus:" + hashlib.sha1(alvo.encode()).hexdigest()[:12], "email": email_login, "papel": None,
            "status": "pendente"}


def _igual(a, b) -> bool:
    return a == b or (a is not None and b is not None and str(a) == str(b))


def linhas(est: dict, view: str, filtros: list, ordem: tuple | None, quem: dict) -> list:
    """As linhas de uma view `rf_<tabela>` como o PostgREST devolvia ao app: filtros `eq`/`neq` e a ordem.
    TabelaDesconhecida para a view que o Radar não tem."""
    aba = T.aba_da_view(view)
    aprovado = quem.get("status") == "aprovado"
    if aba == "perfis":
        base = [dict(p) for p in est["abas"].get("perfis", [])]
        if quem.get("id") == ADMIN_ID:
            base.append({"user_id": ADMIN_ID, "email": quem.get("email"), "papel": "HEAD", "status": "aprovado"})
        # a lista inteira (com o e-mail de todos) é da tela Usuários, que é só do HEAD; os demais veem a própria linha
        # (revisão final de 03/11/2026)
        if not (aprovado and quem.get("papel") == "HEAD"):
            base = [p for p in base if _igual(p.get("user_id"), quem.get("id"))]
    else:
        base = [dict(l) for l in est["abas"].get(aba, [])] if aprovado else []
    for op, col, val in filtros:
        base = [l for l in base if _igual(l.get(col), val) == (op == "eq")]
    if ordem:
        col, desc = ordem
        com = sorted((l for l in base if l.get(col) is not None), key=lambda l: (str(type(l[col])), l[col]),
                     reverse=desc)
        base = com + [l for l in base if l.get(col) is None]
    return base


def folios(est: dict) -> set:
    """As OS que são ronda da zeladoria na cópia: só delas a torre pede foto ao Fracttal (a cota é da empresa, e a foto
    de outra OS não é da zeladoria; revisão final de 03/11/2026)."""
    out = set()
    for aba in ("fracttal_rondas", "fracttal_fotos", "fracttal_ultimas"):
        for l in est["abas"].get(aba, []):
            f = l.get("folio")
            if f is not None:
                out.add(str(int(f)) if isinstance(f, (int, float)) else str(f).strip())
    return out
