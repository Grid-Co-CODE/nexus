"""Os administradores do App de Campo, escolhidos no Nexus (05/11/2026, Base → Acessos → Administradores do App de Campo).

Levi, 05/11/2026, pela sessão do App de Campo: "os administradores do App de Campo e os técnicos por usina têm de ser
escolhidos no Nexus". Os técnicos já eram (PCM → Técnicos por usina, `atribuicoes.py`, que o App aplica desde 29/10);
quem é administrador do App ficava só no App. O contrato com o App (mudou aqui, muda lá no mesmo trabalho):
`_propostas/admins-app-nexus/LEIA.md` do app-campo-docs, com o vetor da assinatura (o mesmo do
`tests/test_pcm_admins_app.py`).

O dado: a aba `fato_admin_app` do livro `nexus_pcm_atribuicoes` (o que o App já lê de 5 em 5 min; no catálogo,
`decisao_admin_app`). 1 linha = 1 decisão de pôr ou tirar 1 pessoa como administrador do App. Só acrescenta; vale a
última de cada (`pessoa_hmac`, `papel`) pela `decidida_em` (empate: a que vem depois no livro), com `ativo = sim` e as
datas cobrindo hoje, no dia de Brasília. A conta é pelo código, não pelo `pessoa_id`, porque é pelo código que o App acha
a pessoa: tirar leva o código da linha que pôs, e a ficha cujo e-mail mudou é outra linha. Em claro: os IDs, o código e
quem decidiu (HMAC); a observação só cifrada (o App a ignora); cada linha assinada (HMAC com a chave derivada da
NEXUS_PESSOA_HMAC, rótulo `nexus:pcm:admins-app`), e o App só aplica a assinada. Sem a NEXUS_PESSOA_HMAC nada se grava
(a linha iria sem assinatura). Pessoa sem código não entra: o App não a reconheceria.

Gravar troca o livro inteiro, com as duas abas (`atribuicoes._gravar_cru`), sob a mesma trava dos técnicos.
"""
import hashlib
import hmac
import json
import time

from ..dados import fatos as D
from . import atribuicoes as A

PAPEIS = ("admin",)
ORIGENS = ("tela",)
OBS_MAX = 300
TTL_S = 60
# deriva a chave da assinatura da NEXUS_PESSOA_HMAC (a mesma nos dois lados): a MESMA conta do App; mudou aqui, muda lá
ROTULO_CHAVE = b"nexus:pcm:admins-app"
# a frase da recusa (o pedido de 05/11/2026): a pessoa sem código não vira administrador, porque o App não a acharia
SEM_CODIGO = ("sem e-mail na ficha nem usuário do Fracttal ligado: o App não a reconheceria; corrija o cadastro "
              "antes")
_CACHE: dict = {}

# o mesmo "nada foi gravado, o texto diz por quê" dos técnicos: a gravação passa pelo `_gravar_cru` de lá
Recusada = A.Recusada


def _chave_cache(cfg) -> str:
    return "admins:" + str(A._arquivo_local(cfg) or "banco")


def ler(cfg, forcar: bool = False) -> dict:
    """{"decisoes", "erro", "lido_em"}: a aba, guardada por 1 minuto. Leitura que falha devolve a última boa com `velha`
    e o erro; sem nenhuma, nenhuma decisão com o erro (a tela não deixa gravar sem saber o que há no banco)."""
    chave = _chave_cache(cfg)
    g = _CACHE.get(chave)
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        dec = [x for x in A._ler_cru(cfg, A.ABA_ADMIN) if D._txt(x.get("pessoa_hmac"))]
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e não deixa gravar
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if g:
            return dict(g, erro=erro, velha=True)
        return {"decisoes": [], "erro": erro, "lido_em": None}
    g = {"decisoes": dec, "erro": "", "lido_em": time.time()}
    _CACHE[chave] = g
    return g


def limpar() -> None:
    _CACHE.clear()


# ── a conta ───────────────────────────────────────────────────────────────────────────────────────────────────
def _chave(x: dict) -> tuple[str, str]:
    return D._txt(x.get("pessoa_hmac")), D._txt(x.get("papel"))


def _ultimas(decisoes: list[dict]) -> dict:
    """{(pessoa_hmac, papel): a última decisão}, pela hora gravada; no empate, a de depois no livro (a ordenação é
    estável)."""
    out = {}
    for x in sorted(decisoes, key=lambda x: D._txt(x.get("decidida_em"))):
        if _chave(x)[0]:
            out[_chave(x)] = x
    return out


def atuais(est: dict, hoje: int) -> dict:
    """Os administradores que valem hoje (`status` "vale") ou começam depois (`status` "agendado"); os tirados e os
    que já acabaram não entram. O último dia ainda vale; o dia de início já vale. O App conta só os "vale"."""
    out = {}
    for k, x in _ultimas(est.get("decisoes") or []).items():
        if not A._sim(x.get("ativo")):
            continue
        de, ate = A._int_ou_none(x.get("de_data_id")), A._int_ou_none(x.get("ate_data_id"))
        if ate and ate < hoje:
            continue
        out[k] = dict(x, status="agendado" if de and de > hoje else "vale")
    return out


def assinatura(linha: dict, chave_base: str) -> str:
    """HMAC-SHA256 em hex minúsculo do texto "admin_app|pessoa_hmac|papel|ativo|de_data_id|ate_data_id|decidida_em",
    com a chave derivada da NEXUS_PESSOA_HMAC (`ROTULO_CHAVE`). Data vazia vira "". Sem chave: "" (o App não aplica)."""
    base = (chave_base or "").strip()
    if not base:
        return ""
    chave = hmac.new(base.encode("utf-8"), ROTULO_CHAVE, hashlib.sha256).digest()
    txt = "|".join(("admin_app", D._txt(linha.get("pessoa_hmac")), D._txt(linha.get("papel")),
                    D._txt(linha.get("ativo")), D._txt(linha.get("de_data_id")), D._txt(linha.get("ate_data_id")),
                    D._txt(linha.get("decidida_em"))))
    return hmac.new(chave, txt.encode("utf-8"), hashlib.sha256).hexdigest()


def _ctx(pessoa_id, quando: str) -> str:
    return f"pcm/admins_app/{pessoa_id}/{quando}"


def historico(cfg, est: dict) -> list[dict]:
    """As decisões, da mais nova à mais antiga: {quando, pessoa_id, pessoa_hmac, acao ("pôs" | "tirou"), de, ate,
    origem, quem_hmac, obs}. A observação sai decifrada; sem a chave do cadastro, vazia."""
    cofre = A._cofre(cfg)
    out = []
    # a mais nova primeiro; duas no mesmo segundo, a gravada depois primeiro (a ordem do livro desempata)
    ordem = sorted(enumerate(est.get("decisoes") or []), key=lambda t: (D._txt(t[1].get("decidida_em")), t[0]),
                   reverse=True)
    for _i, x in ordem:
        quando, pid = D._txt(x.get("decidida_em")), A._int_ou_none(x.get("pessoa_id"))
        obs = ""
        if cofre and D._txt(x.get("dados_cifrados")):
            try:
                obs = D._txt(json.loads(cofre.decifrar(D._txt(x.get("dados_cifrados")), _ctx(pid, quando))).get("obs"))
            except Exception:    # noqa: BLE001 — cifra de outra chave ou linha mexida: sem a observação
                obs = ""
        out.append({"quando": quando, "pessoa_id": pid, "pessoa_hmac": D._txt(x.get("pessoa_hmac")),
                    "acao": "pôs" if A._sim(x.get("ativo")) else "tirou",
                    "de": A._int_ou_none(x.get("de_data_id")), "ate": A._int_ou_none(x.get("ate_data_id")),
                    "origem": D._txt(x.get("origem")), "quem_hmac": D._txt(x.get("decidida_por_hmac")), "obs": obs})
    return out


# ── gravar ────────────────────────────────────────────────────────────────────────────────────────────────────
def decidir(cfg, *, pessoa_id, pessoa_hmac: str, ativo: bool, usuario: dict | None, obs: str = "", de: str = "",
            ate: str = "", papel: str = "admin", origem: str = "tela") -> dict:
    """Pôr (`ativo`) ou tirar uma pessoa dos administradores do App. {"gravou", "texto"}; `Recusada` com o motivo quando
    não vale. Tirar: o `pessoa_hmac` da linha que pôs (o que vale hoje)."""
    from .motivos import _quem
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        # sem a chave a linha iria sem assinatura e o App a descartaria: o Nexus diria uma coisa e o App faria outra
        raise Recusada("Este Nexus não tem a NEXUS_PESSOA_HMAC: a linha iria sem assinatura e o App não a aplicaria. "
                       "Nada foi gravado.")
    papel = D._txt(papel)
    if papel not in PAPEIS:
        raise Recusada(f"Papel que o Nexus não conhece: {papel[:20]}.")
    if origem not in ORIGENS:
        raise Recusada(f"Origem que o Nexus não conhece: {origem[:20]}.")
    pid, codigo = A._int_ou_none(pessoa_id), D._txt(pessoa_hmac)
    if not pid or pid <= 0:
        raise Recusada("Faltou a pessoa: atualize a página.")
    if not codigo:
        raise Recusada(f"Pessoa {pid}: {SEM_CODIGO}.")
    ativo = bool(ativo)
    de_id, ate_id = (A._dia(de), A._dia(ate)) if ativo else (None, None)
    if de_id and ate_id and ate_id < de_id:
        raise Recusada("A data final vem antes da data de início.")
    obs = " ".join(D._txt(obs).split())[:OBS_MAX]
    quem_hmac = _quem(cfg, usuario)[0]
    with A._TRAVA:
        try:
            cru = A._ler_cru(cfg, A.ABA_ADMIN)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler os administradores do App no banco ({type(ex).__name__}): nada foi "
                           "gravado, para não apagar o que já está lá.") from ex
        agora, hoje = A._agora(), A.hoje_id()
        if ate_id and ate_id < hoje:
            raise Recusada("A data final já passou: nada foi gravado.")
        ult = _ultimas(cru).get((codigo, papel))
        vale = ult is not None and (codigo, papel) in atuais({"decisoes": [ult]}, hoje)
        if not ativo and not vale:
            raise Recusada("Essa pessoa já não é administradora do App de Campo (alguém mudou agora): atualize a "
                           "página.")
        # a mesma decisão não grava de novo: já vale, com as mesmas datas
        if ativo and vale and A._int_ou_none(ult.get("de_data_id")) == de_id \
                and A._int_ou_none(ult.get("ate_data_id")) == ate_id:
            _CACHE[_chave_cache(cfg)] = {"decisoes": cru, "erro": "", "lido_em": time.time()}
            return {"gravou": False, "texto": "Nada mudou."}
        quando = A._iso(agora)
        nova = {"decidida_em": quando, "data_id": A._data_id(agora), "pessoa_id": pid, "pessoa_hmac": codigo,
                "papel": papel, "ativo": "sim" if ativo else "nao", "de_data_id": de_id or "",
                "ate_data_id": ate_id or "", "origem": origem, "decidida_por_hmac": quem_hmac, "dados_cifrados": ""}
        if obs:
            cofre = A._cofre(cfg)
            if cofre is None:
                raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): a observação vai "
                               "cifrada, e sem ela nada é gravado.")
            nova["dados_cifrados"] = cofre.cifrar(json.dumps({"obs": obs}, ensure_ascii=False), _ctx(pid, quando))
        nova["assinatura"] = assinatura(nova, cfg.get("NEXUS_PESSOA_HMAC"))
        A._gravar_cru(cfg, cru + [nova], A.ABA_ADMIN)
        # o que acabou de ser lido e gravado vale como a leitura de agora: a tela não volta ao banco em seguida
        _CACHE[_chave_cache(cfg)] = {"decisoes": cru + [nova], "erro": "", "lido_em": time.time()}
    return {"gravou": True, "texto": "Administrador do App posto." if ativo else "Administrador do App tirado."}
