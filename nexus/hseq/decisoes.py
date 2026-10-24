"""As decisões da Segurança sobre os extintores (24/10/2026): o Nexus é a FONTE.

Levi, 24/10/2026: "Opção da pessoa do setor de segurança editar a quantidade de extintores, quando alguém não reconhece o
extintor aparece como situação 'não reconhecida' a pessoa da Segurança pode aceitar e aí o extintor vai sumir ou
solicitar que o técnico faça uma nova ronda, se ele solicitar vai aparecer no app de campo 'ronda pendente' 'O TST
solicitou uma nova ronda'". E, sobre onde: "tem que ser feito na tabela geral de extintores e não só na tabela de
contestações, a tabela de contestações tem que servir para apontar para a usina, ao ir para a usina a TST resolve".

O dado (livro `nexus_hseq_extintores`, registrado em `nexus/dados/catalogo.py` antes da 1ª gravação; regras em
`nexus/dados/CLAUDE.md`), só acrescenta, e vale a última decisão:
- `fato_decisao_extintor`: 1 linha = 1 decisão da Segurança sobre 1 extintor NÃO RECONHECIDO, respondendo a UMA marca
  do App (`marca_dia`, o "Não reconhecido em"). `aceitar` = dar baixa (o extintor sai das telas do Nexus); `nova_ronda` =
  pedir à equipe uma nova ronda (o App lê e mostra a ronda pendente). Marca nova do App (outro dia) pede decisão nova;
  conferência depois da marca a desfaz no App, e o extintor volta às contas (existe).
- `fato_quantidade_extintores`: 1 linha = 1 decisão da Segurança sobre QUANTOS extintores existem em 1 usina, ao lado de
  quantos o cadastro tinha naquela hora. Não apaga nada do cadastro (que é do App): a tela mostra as duas contas, e a
  diferença é o que a TST e o App acertam. O motivo vai só cifrado (o Cofre, regra 8).
Em claro: os IDs, o código do extintor, a ação, os dias e os códigos HMAC. Cada linha vai assinada (`assinatura`, HMAC
com a chave derivada da NEXUS_PESSOA_HMAC): o App lê o livro pela leitura aberta da API e só aplica a linha assinada.

Quem decide: o administrador e quem é do setor Segurança (Base → Acessos), sempre com um login de pessoa (a senha de
administrador não diz quem é: o histórico guarda quem fez). Gravar troca o livro inteiro, relido do banco antes (leitura
que falha não grava), uma gravação por vez neste processo; o `livros.publicar` recusa gravar o livro menor.
"""
import hashlib
import hmac
import json
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..dados import fatos as D
from ..dados import livros

LIVRO, NOME_LIVRO = "nexus_hseq_extintores", "Nexus · decisões da Segurança sobre os extintores"
ABA_EXT, ABA_QTD = "fato_decisao_extintor", "fato_quantidade_extintores"
CAB_EXT = ("decidida_em", "data_id", "usina_id", "codigo", "acao", "marca_dia", "decidida_por_hmac", "assinatura")
CAB_QTD = ("decidida_em", "data_id", "usina_id", "quantidade_qtd", "no_cadastro_qtd", "decidida_por_hmac",
           "dados_cifrados", "assinatura")
ACOES = {"aceitar": "Aceito (baixa)", "nova_ronda": "Nova ronda pedida"}
SETOR = "seguranca"                          # o nome do setor sem acento nem caixa (Base → Acessos)
MOTIVO_MAX = 300
QTD_MAX = 500
TTL_S = 60
ROTULO_CHAVE = b"nexus:hseq:extintores"     # a chave da assinatura (a MESMA conta no App, quando ele ler este livro)
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def _agora() -> datetime:
    return datetime.now(_BRT)


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def pode_decidir(setor: dict | None, admin: bool) -> bool:
    """Aceitar, pedir nova ronda e editar a quantidade: o administrador e quem é do setor Segurança."""
    return bool(admin) or _norm((setor or {}).get("nome")) == SETOR


def _int(v) -> int | None:
    try:
        return int(float(v)) if D._txt(v) else None
    except (TypeError, ValueError):
        return None


# ── ler ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _arquivo_local(cfg) -> Path | None:
    p = cfg.get("NEXUS_HSEQ_DECISOES_ARQUIVO")
    return Path(p) if p else None


def _ler_cru(cfg) -> dict:
    """{aba: [linhas]} lidas agora. Livro que ainda não existe = vazio; erro de leitura sobe. Teste sem o arquivo nunca
    vai à rede (vale vazio)."""
    loc = _arquivo_local(cfg)
    if loc is not None:
        try:
            d = json.loads(loc.read_text(encoding="utf-8"))
        except FileNotFoundError:
            d = {}
        return {a: [dict(x) for x in d.get(a) or []] for a in (ABA_EXT, ABA_QTD)}
    if cfg.get("TESTING"):
        return {ABA_EXT: [], ABA_QTD: []}
    from ..pcm.motivos import _banco
    base, sessao = _banco(cfg)
    a = livros.abas(base, sessao, LIVRO)
    return {aba: (list(livros._linhas(base, sessao, a[aba])) if aba in a else []) for aba in (ABA_EXT, ABA_QTD)}


def ler(cfg, forcar: bool = False) -> dict:
    """{"extintor", "quantidade", "erro", "lido_em"}: o livro, guardado por 1 minuto. Leitura que falha devolve a
    última boa (`velha`) com o erro; sem nenhuma, nada, com o erro (a tela não deixa gravar sem saber o que há)."""
    chave = str(_arquivo_local(cfg) or "banco")
    g = _CACHE.get(chave)
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        cru = _ler_cru(cfg)
    except Exception as ex:  # noqa: BLE001 — banco fora, rede: a tela diz
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if g:
            return dict(g, erro=erro, velha=True)
        return {"extintor": [], "quantidade": [], "erro": erro, "lido_em": None}
    g = {"extintor": cru[ABA_EXT], "quantidade": cru[ABA_QTD], "erro": "", "lido_em": time.time()}
    _CACHE[chave] = g
    return g


def limpar() -> None:
    _CACHE.clear()


def _ordem(linhas):
    """Da mais velha para a mais nova (a ordem do livro desempata duas no mesmo segundo)."""
    return [x for _i, x in sorted(enumerate(linhas), key=lambda t: (D._txt(t[1].get("decidida_em")), t[0]))]


def por_extintor(est: dict) -> dict:
    """{(código, marca_dia): a última decisão}: a decisão vale para a marca do App a que respondeu."""
    out = {}
    for x in _ordem(est.get("extintor") or []):
        out[(D._txt(x.get("codigo")), D._txt(x.get("marca_dia")))] = x
    return out


def por_usina(est: dict) -> dict:
    """{usina_id: a última decisão de quantidade}."""
    out = {}
    for x in _ordem(est.get("quantidade") or []):
        uid = _int(x.get("usina_id"))
        if uid:
            out[uid] = x
    return out


def aplicar(nao_reconhecidos: list, est: dict) -> tuple[list, list]:
    """(os que seguem esperando a Segurança, os aceitos). O aceito sai da tela (a baixa); o de nova ronda segue, com o
    dia do pedido em `nova_ronda_em` (o App ainda não conferiu de novo). A decisão vale para a marca daquele dia: marca
    nova do App pede decisão nova."""
    dec = por_extintor(est)
    seguem, aceitos = [], []
    for x in nao_reconhecidos:
        d = dec.get((x["codigo"], x["nao_reconhecido"].isoformat()))
        acao = D._txt(d.get("acao")) if d else ""
        if acao == "aceitar":
            aceitos.append(x)
            continue
        y = dict(x)
        y["nova_ronda_em"] = D._txt(d.get("decidida_em"))[:10] if acao == "nova_ronda" else ""
        seguem.append(y)
    return seguem, aceitos


# ── gravar ────────────────────────────────────────────────────────────────────────────────────────────────────
def assinatura(linha: dict, aba: str, chave_base: str) -> str:
    """HMAC-SHA256 em hex minúsculo com a chave derivada da NEXUS_PESSOA_HMAC (`ROTULO_CHAVE`): do texto
    "extintor|código|ação|marca_dia|decidida_em" ou "quantidade|usina_id|quantidade_qtd|decidida_em". Sem chave: ""
    (o App não aplica a linha)."""
    base = (chave_base or "").strip()
    if not base:
        return ""
    chave = hmac.new(base.encode("utf-8"), ROTULO_CHAVE, hashlib.sha256).digest()
    if aba == ABA_EXT:
        partes = ("extintor", linha.get("codigo"), linha.get("acao"), linha.get("marca_dia"), linha.get("decidida_em"))
    else:
        partes = ("quantidade", linha.get("usina_id"), linha.get("quantidade_qtd"), linha.get("decidida_em"))
    return hmac.new(chave, "|".join(D._txt(p) for p in partes).encode("utf-8"), hashlib.sha256).hexdigest()


def _cofre(cfg):
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        return None
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _ctx(usina_id, quando: str) -> str:
    return f"hseq/quantidade/{usina_id}/{quando}"


def motivo(cfg, linha: dict) -> str:
    """O motivo da decisão de quantidade, decifrado (sem a chave do cadastro ou com cifra de outra chave: vazio)."""
    cofre, cif = _cofre(cfg), D._txt(linha.get("dados_cifrados"))
    if not cofre or not cif:
        return ""
    try:
        return D._txt(json.loads(cofre.decifrar(cif, _ctx(_int(linha.get("usina_id")), D._txt(linha.get("decidida_em"))))
                                 ).get("motivo"))
    except Exception:  # noqa: BLE001
        return ""


def _gravar_cru(cfg, cru: dict) -> None:
    """Troca o livro inteiro e confere (`livros.publicar` relê e compara a contagem). Na cópia de prova, o arquivo."""
    vazio = (lambda v: None if v in ("", None) else v)      # noqa: E731
    tabelas = {aba: (list(cab), [[vazio(x.get(c)) for c in cab] for x in cru[aba]])
               for aba, cab in ((ABA_EXT, CAB_EXT), (ABA_QTD, CAB_QTD))}
    loc = _arquivo_local(cfg)
    if loc is not None:
        loc.parent.mkdir(parents=True, exist_ok=True)
        tmp = loc.with_suffix(".tmp")
        tmp.write_text(json.dumps({a: [dict(zip(cab, l)) for l in corpo] for a, (cab, corpo) in tabelas.items()},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(loc)
        return
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    from ..pcm.motivos import _banco
    base, sessao = _banco(cfg)
    livros.publicar(LIVRO, NOME_LIVRO, tabelas, base=base, token=token, sessao=sessao)


def _quem(cfg, usuario: dict | None) -> str:
    """O código de quem decide; sem login de pessoa (a senha de administrador), Recusada: o histórico guarda quem fez."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    email = str((usuario or {}).get("email") or "").strip().lower()
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email) if email else ""
    if not codigo:
        raise Recusada("Entre com o seu login (Microsoft ou Fracttal) para decidir: a senha de administrador não diz "
                       "quem é, e o histórico guarda quem fez.")
    return codigo


def _gravar(cfg, aba: str, nova: dict) -> None:
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        raise Recusada("Este Nexus não tem a NEXUS_PESSOA_HMAC: a linha iria sem assinatura e o App não a aplicaria. "
                       "Nada foi gravado.")
    with _TRAVA:
        try:
            cru = _ler_cru(cfg)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler as decisões no banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.") from ex
        nova["assinatura"] = assinatura(nova, aba, cfg.get("NEXUS_PESSOA_HMAC"))
        cru[aba] = cru[aba] + [nova]
        _gravar_cru(cfg, cru)
        _CACHE[str(_arquivo_local(cfg) or "banco")] = {"extintor": cru[ABA_EXT], "quantidade": cru[ABA_QTD], "erro": "",
                                                       "lido_em": time.time()}


def decidir_extintor(cfg, *, extintor: dict, acao: str, usuario: dict | None, pode: bool) -> str:
    """Aceitar ou pedir nova ronda para UM não reconhecido (`extintor`, a linha da tela, que ainda espera a
    Segurança). O texto do que foi feito; Recusada com o motivo quando não vale."""
    if not pode:
        raise Recusada("Só quem é da Segurança ou administrador decide os extintores não reconhecidos.")
    if acao not in ACOES:
        raise Recusada("Ação que o Nexus não conhece.")
    quem = _quem(cfg, usuario)
    agora = _agora()
    _gravar(cfg, ABA_EXT, {"decidida_em": agora.isoformat(timespec="seconds"), "data_id": int(agora.strftime("%Y%m%d")),
                           "usina_id": extintor.get("usina_id") or "", "codigo": extintor["codigo"], "acao": acao,
                           "marca_dia": extintor["nao_reconhecido"].isoformat(), "decidida_por_hmac": quem})
    return (f"{extintor['ext']} aceito: sai da {extintor['usina']}." if acao == "aceitar"
            else f"Nova ronda pedida para o {extintor['ext']} da {extintor['usina']}.")


def decidir_quantidade(cfg, *, usina_id: int, usina: str, no_cadastro: int, quantidade, motivo_txt: str,
                       usuario: dict | None, pode: bool) -> str:
    """Quantos extintores existem na usina, segundo a Segurança (ao lado de quantos o cadastro tem agora)."""
    if not pode:
        raise Recusada("Só quem é da Segurança ou administrador edita a quantidade de extintores.")
    if not usina_id:
        raise Recusada("Esta usina não está no cadastro do Nexus: acerte o cadastro antes de editar a quantidade.")
    n = _int(quantidade)
    if n is None or not 0 <= n <= QTD_MAX:
        raise Recusada(f"A quantidade é um número de 0 a {QTD_MAX}.")
    texto = " ".join(D._txt(motivo_txt).split())[:MOTIVO_MAX]
    quem = _quem(cfg, usuario)
    agora = _agora()
    quando = agora.isoformat(timespec="seconds")
    nova = {"decidida_em": quando, "data_id": int(agora.strftime("%Y%m%d")), "usina_id": usina_id, "quantidade_qtd": n,
            "no_cadastro_qtd": no_cadastro, "decidida_por_hmac": quem, "dados_cifrados": ""}
    if texto:
        cofre = _cofre(cfg)
        if cofre is None:
            raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): o motivo vai cifrado, e sem "
                           "ela nada é gravado.")
        nova["dados_cifrados"] = cofre.cifrar(json.dumps({"motivo": texto}, ensure_ascii=False), _ctx(usina_id, quando))
    _gravar(cfg, ABA_QTD, nova)
    return f"Quantidade da {usina}: {n} extintor{'es' if n != 1 else ''} (o cadastro tem {no_cadastro})."
