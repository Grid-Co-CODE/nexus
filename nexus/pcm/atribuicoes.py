"""Os técnicos por usina (17/10/2026): quem cobre cada usina, decidido pelo PCM no Nexus.

Levi, 17/10/2026: "cria uma estrutura que liga usina e técnico e o PCM pode editar a vontade"; "é normal usinas terem
dois técnicos e receberem de vez em quando mais técnicos"; "dá para trazer para o Nexus esse controle? quero tirar do
site de gestão". Até aqui a ligação morava em dois lugares que não se falavam: o `tecnico_om_id` do cadastro (UM por
usina) e a tabela `atribuicoes` do App de Campo (o papel `executa`, editado na tela Organização do site de gestão), que é
o que decide as usinas da aba Ronda. Desenho: `docs/superpowers/specs/2026-10-17-tecnicos-por-usina-design.md`.

O que `executa` quer dizer (conferido no código do App em 17/10): é a lista de usinas que a pessoa VÊ e pode rondar no
App, não "o designado". Por isso a lista de uma usina aqui é exatamente quem vê e pode rondar aquela usina.

O dado (livro `nexus_pcm_atribuicoes`, registrado em `nexus/dados/catalogo.py`; regras em `nexus/dados/CLAUDE.md`):
- `fato_decisao_atribuicao`: 1 linha = 1 decisão de pôr ou tirar 1 pessoa de 1 usina num papel. Só acrescenta; vale a
  última de cada (`usina_id`, `pessoa_id`, `papel`). `de_data_id`/`ate_data_id` fazem o apoio: com data final, deixa de
  valer depois daquele dia sem ninguém precisar tirar; com data de início, fica agendado até lá.
- Em claro: os IDs, o nome da usina no Fracttal (`usina_fracttal`, por onde o App acha a usina) e os códigos HMAC
  (`pessoa_hmac`, por onde o App acha a pessoa; `decidida_por_hmac`). A observação só cifrada (o Cofre). Cada linha vai
  assinada (`assinatura`): o App lê o livro pela leitura aberta da API e só aplica a linha assinada.
Gravar troca o livro inteiro, relido do banco antes (leitura que falha não grava), uma gravação por vez neste processo.
"""
import hashlib
import hmac
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..dados import fatos as D
from ..dados import livros

LIVRO, NOME_LIVRO = "nexus_pcm_atribuicoes", "Nexus · técnicos por usina (PCM)"
ABA = "fato_decisao_atribuicao"
CAB = ("decidida_em", "data_id", "usina_id", "usina_fracttal", "pessoa_id", "pessoa_hmac", "papel", "na_usina",
       "de_data_id", "ate_data_id", "origem", "decidida_por_hmac", "dados_cifrados", "assinatura")
PAPEIS = ("executa",)                    # a fase 3 acrescenta "responsavel" (o supervisor da usina)
ORIGENS = ("tela", "carga_inicial", "reemissao")
OBS_MAX = 300
TTL_S = 60
# deriva a chave da assinatura da NEXUS_PESSOA_HMAC (a mesma nos dois lados): a MESMA conta do App (pacote
# `_propostas/atribuicoes-nexus`); mudou aqui, muda lá no mesmo trabalho
ROTULO_CHAVE = b"nexus:pcm:atribuicoes"
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _data_id(d: datetime) -> int:
    return int(d.astimezone(_BRT).strftime("%Y%m%d"))


def hoje_id() -> int:
    """O dia de Brasília de agora (AAAAMMDD): o App grava em UTC, e 02:30Z ainda é o dia anterior aqui."""
    return _data_id(_agora())


def _sim(v) -> bool:
    return D._txt(v).lower() in ("sim", "1", "true", "s")


def _dia(v) -> int | None:
    """`AAAA-MM-DD` → AAAAMMDD; vazio → None; outro formato → Recusada."""
    s = D._txt(v)
    if not s:
        return None
    try:
        if len(s) != 10:
            raise ValueError(s)
        return int(date.fromisoformat(s).strftime("%Y%m%d"))
    except ValueError:
        raise Recusada(f"Data fora do formato (dia/mês/ano pelo calendário da tela): {s[:20]}") from None


def _int_ou_none(v) -> int | None:
    try:
        return int(float(v)) if D._txt(v) else None
    except (TypeError, ValueError):
        return None


# ── o livro: o banco, ou um arquivo na cópia de prova ─────────────────────────────────────────────────────────
def _arquivo_local(cfg) -> Path | None:
    p = cfg.get("NEXUS_PCM_ATRIBUICOES_ARQUIVO")
    return Path(p) if p else None


def _ler_cru(cfg) -> list[dict]:
    """As linhas da aba, lidas agora. Livro que ainda não existe = vazio; erro de leitura sobe. Teste sem o arquivo
    nunca vai à rede (vale vazio)."""
    loc = _arquivo_local(cfg)
    if loc is not None:
        try:
            d = json.loads(loc.read_text(encoding="utf-8"))
        except FileNotFoundError:
            d = {}
        return [dict(x) for x in d.get(ABA) or []]
    if cfg.get("TESTING"):
        return []
    from .motivos import _banco
    base, sessao = _banco(cfg)
    a = livros.abas(base, sessao, LIVRO)
    return list(livros._linhas(base, sessao, a[ABA])) if ABA in a else []


def _gravar_cru(cfg, linhas: list[dict]) -> None:
    """Troca o livro inteiro e confere (`livros.publicar` relê e compara a contagem). Na cópia de prova, o arquivo."""
    vazio = (lambda v: None if v in ("", None) else v)      # noqa: E731
    corpo = [[vazio(x.get(c)) for c in CAB] for x in linhas]
    loc = _arquivo_local(cfg)
    if loc is not None:
        loc.parent.mkdir(parents=True, exist_ok=True)
        tmp = loc.with_suffix(".tmp")
        tmp.write_text(json.dumps({ABA: [dict(zip(CAB, l)) for l in corpo]}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(loc)
        return
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    from .motivos import _banco
    base, sessao = _banco(cfg)
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), corpo)}, base=base, token=token, sessao=sessao)


def ler(cfg, forcar: bool = False) -> dict:
    """{"decisoes", "erro", "lido_em"}: o livro, guardado por 1 minuto. Leitura que falha devolve a última boa com `velha`
    e o erro; sem nenhuma, nenhuma decisão com o erro (a tela não deixa gravar sem saber o que há no banco)."""
    chave = str(_arquivo_local(cfg) or "banco")
    g = _CACHE.get(chave)
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        dec = [x for x in _ler_cru(cfg) if _int_ou_none(x.get("usina_id")) and _int_ou_none(x.get("pessoa_id"))]
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
def _chave(x: dict) -> tuple[int, int, str]:
    return _int_ou_none(x.get("usina_id")), _int_ou_none(x.get("pessoa_id")), D._txt(x.get("papel"))


def _ultimas(decisoes: list[dict]) -> dict:
    """{(usina_id, pessoa_id, papel): a última decisão}, pela hora gravada (a ordem do livro desempata)."""
    out = {}
    for x in sorted(decisoes, key=lambda x: D._txt(x.get("decidida_em"))):
        out[_chave(x)] = x
    return out


def atuais(est: dict, hoje: int) -> dict:
    """As ligações que valem hoje (`status` "vale") ou começam depois (`status` "agendado"); as tiradas e as que já
    acabaram não entram. O último dia do apoio ainda vale; o dia de início já vale."""
    out = {}
    for k, x in _ultimas(est.get("decisoes") or []).items():
        if not _sim(x.get("na_usina")):
            continue
        de, ate = _int_ou_none(x.get("de_data_id")), _int_ou_none(x.get("ate_data_id"))
        if ate and ate < hoje:
            continue
        out[k] = dict(x, status="agendado" if de and de > hoje else "vale")
    return out


def assinatura(linha: dict, chave_base: str) -> str:
    """HMAC-SHA256 em hex minúsculo do texto
    "atribuicao|usina_fracttal|pessoa_hmac|papel|na_usina|de_data_id|ate_data_id|decidida_em", com a chave derivada da
    NEXUS_PESSOA_HMAC (`ROTULO_CHAVE`). Data vazia vira "". Sem chave: "" (o App não aplica a linha)."""
    base = (chave_base or "").strip()
    if not base:
        return ""
    chave = hmac.new(base.encode("utf-8"), ROTULO_CHAVE, hashlib.sha256).digest()
    txt = "|".join(("atribuicao", D._txt(linha.get("usina_fracttal")), D._txt(linha.get("pessoa_hmac")),
                    D._txt(linha.get("papel")), D._txt(linha.get("na_usina")), D._txt(linha.get("de_data_id")),
                    D._txt(linha.get("ate_data_id")), D._txt(linha.get("decidida_em"))))
    return hmac.new(chave, txt.encode("utf-8"), hashlib.sha256).hexdigest()


def _cofre(cfg):
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        return None
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _ctx(usina_id, pessoa_id, quando: str) -> str:
    return f"pcm/atribuicoes/{usina_id}/{pessoa_id}/{quando}"


def historico(cfg, est: dict, usina_id: int) -> list[dict]:
    """As decisões de uma usina, da mais nova à mais antiga: {quando, pessoa_id, acao ("pôs" | "tirou"), de, ate,
    origem, quem_hmac, obs}. A observação sai decifrada; sem a chave do cadastro, vazia."""
    cofre = _cofre(cfg)
    out = []
    # a mais nova primeiro; duas no mesmo segundo, a gravada depois primeiro (a ordem do livro desempata)
    ordem = sorted(enumerate(est.get("decisoes") or []), key=lambda t: (D._txt(t[1].get("decidida_em")), t[0]),
                   reverse=True)
    for _i, x in ordem:
        if _int_ou_none(x.get("usina_id")) != usina_id:
            continue
        quando, pid = D._txt(x.get("decidida_em")), _int_ou_none(x.get("pessoa_id"))
        obs = ""
        if cofre and D._txt(x.get("dados_cifrados")):
            try:
                obs = D._txt(json.loads(cofre.decifrar(D._txt(x.get("dados_cifrados")),
                                                      _ctx(usina_id, pid, quando))).get("obs"))
            except Exception:    # noqa: BLE001 — cifra de outra chave ou linha mexida: sem a observação
                obs = ""
        out.append({"quando": quando, "pessoa_id": pid, "acao": "pôs" if _sim(x.get("na_usina")) else "tirou",
                    "de": _int_ou_none(x.get("de_data_id")), "ate": _int_ou_none(x.get("ate_data_id")),
                    "origem": D._txt(x.get("origem")), "quem_hmac": D._txt(x.get("decidida_por_hmac")), "obs": obs})
    return out


# ── gravar ────────────────────────────────────────────────────────────────────────────────────────────────────
def _linha(cfg, p: dict, quem_hmac: str, origem: str, agora: datetime, hoje: int, ultimas: dict) -> dict | None:
    """A linha nova de um pedido, ou None quando nada muda. Recusada com o motivo quando o pedido não vale."""
    papel = D._txt(p.get("papel") or "executa")
    if papel not in PAPEIS:
        raise Recusada(f"Papel que o Nexus não conhece: {papel[:20]}.")
    if origem not in ORIGENS:
        raise Recusada(f"Origem que o Nexus não conhece: {origem[:20]}.")
    uid, pid = _int_ou_none(p.get("usina_id")), _int_ou_none(p.get("pessoa_id"))
    if not uid or not pid:
        raise Recusada("Faltou a usina ou a pessoa: atualize a página.")
    na = bool(p.get("na_usina"))
    de, ate = (_dia(p.get("de")), _dia(p.get("ate"))) if na else (None, None)
    if de and ate and ate < de:
        raise Recusada("A data final vem antes da data de início.")
    if ate and ate < hoje:
        raise Recusada("A data final já passou: um apoio que já acabou não precisa ser lançado.")
    obs = " ".join(D._txt(p.get("obs")).split())[:OBS_MAX]
    ult = ultimas.get((uid, pid, papel))
    vale_agora = bool(ult) and (uid, pid, papel) in atuais({"decisoes": [ult]}, hoje)
    if not na and not vale_agora:
        raise Recusada("Essa pessoa já não está nesta usina (alguém mudou agora): atualize a página.")
    # a mesma decisão não grava de novo; o nome da usina no Fracttal e o código da pessoa contam (é o que o App lê:
    # a reemissão depois de a usina mudar de nome no Fracttal precisa gravar)
    if ult is not None and _sim(ult.get("na_usina")) == na and (
            not na or (vale_agora and _int_ou_none(ult.get("de_data_id")) == de
                       and _int_ou_none(ult.get("ate_data_id")) == ate
                       and D._txt(ult.get("usina_fracttal")) == D._txt(p.get("usina_fracttal"))
                       and D._txt(ult.get("pessoa_hmac")) == D._txt(p.get("pessoa_hmac")))):
        return None
    quando = _iso(agora)
    nova = {"decidida_em": quando, "data_id": _data_id(agora), "usina_id": uid,
            "usina_fracttal": D._txt(p.get("usina_fracttal")), "pessoa_id": pid,
            "pessoa_hmac": D._txt(p.get("pessoa_hmac")), "papel": papel, "na_usina": "sim" if na else "nao",
            "de_data_id": de or "", "ate_data_id": ate or "", "origem": origem, "decidida_por_hmac": quem_hmac,
            "dados_cifrados": ""}
    if obs:
        cofre = _cofre(cfg)
        if cofre is None:
            raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): a observação vai cifrada, e "
                           "sem ela nada é gravado.")
        nova["dados_cifrados"] = cofre.cifrar(json.dumps({"obs": obs}, ensure_ascii=False), _ctx(uid, pid, quando))
    nova["assinatura"] = assinatura(nova, cfg.get("NEXUS_PESSOA_HMAC"))
    return nova


def decidir_varias(cfg, pedidos: list[dict], usuario: dict | None, origem: str) -> int:
    """Várias decisões numa gravação só (a carga inicial, a reemissão). Cada pedido tem as chaves de `decidir`. Devolve
    quantas linhas entraram; o pedido que não muda nada não entra, e um pedido recusado recusa todos."""
    from .motivos import _quem
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        # sem a chave a linha iria sem assinatura e o App a descartaria: o Nexus diria uma coisa e o App faria outra
        raise Recusada("Este Nexus não tem a NEXUS_PESSOA_HMAC: a linha iria sem assinatura e o App não a aplicaria. "
                       "Nada foi gravado.")
    quem_hmac = _quem(cfg, usuario)[0]
    with _TRAVA:
        try:
            cru = _ler_cru(cfg)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler os técnicos por usina no banco ({type(ex).__name__}): nada foi gravado, "
                           "para não apagar o que já está lá.") from ex
        agora, hoje = _agora(), hoje_id()
        ultimas = _ultimas(cru)
        novas = []
        for p in pedidos:
            n = _linha(cfg, p, quem_hmac, origem, agora, hoje, ultimas)
            if n is not None:
                novas.append(n)
                ultimas[_chave(n)] = n
        if novas:
            _gravar_cru(cfg, cru + novas)
        # o que acabou de ser lido (e gravado) vale como a leitura de agora: a tela não volta ao banco em seguida
        _CACHE[str(_arquivo_local(cfg) or "banco")] = {"decisoes": cru + novas, "erro": "", "lido_em": time.time()}
        return len(novas)


def decidir(cfg, *, usina_id: int, usina_fracttal: str, pessoa_id: int, pessoa_hmac: str, na_usina: bool,
            usuario: dict | None, de: str = "", ate: str = "", obs: str = "", origem: str = "tela",
            papel: str = "executa") -> dict:
    """Pôr (`na_usina`) ou tirar uma pessoa de uma usina. {"gravou", "texto"}; Recusada com o motivo quando não vale."""
    n = decidir_varias(cfg, [{"usina_id": usina_id, "usina_fracttal": usina_fracttal, "pessoa_id": pessoa_id,
                              "pessoa_hmac": pessoa_hmac, "na_usina": na_usina, "de": de, "ate": ate, "obs": obs,
                              "papel": papel}], usuario, origem)
    if not n:
        return {"gravou": False, "texto": "Nada mudou."}
    return {"gravou": True, "texto": "Técnico posto na usina." if na_usina else "Técnico tirado da usina."}
