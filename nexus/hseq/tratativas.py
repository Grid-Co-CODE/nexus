"""As tratativas dos extintores (Segurança · HSEQ, 24/11/2026): o que a Segurança fez com o cliente ou com a usina que
tem extintor vencido, e quando.

O pedido (o mockup de Extintores aprovado pela Segurança, entrega 2): a coluna Evolução da tabela por cliente mostra a
última tratativa (o que foi feito e quando), quantas há e quem registrou a última, com o "Ver histórico" e o
"Registrar". Tipos: Cliente notificado por e-mail, Recarga agendada, OS de recarga aberta, Troca realizada, Aguardando
cliente e Outro.

O dado, num livro SÓ DELAS (`nexus_hseq_extintores_tratativas`, no `catalogo.py` antes da 1ª gravação; a Segurança,
25/11/2026: o pedido era uma aba no livro das decisões, `nexus_hseq_extintores`, que o App de Campo lê a cada 5 min, e
não deu para confirmar no código do App que ele ignora uma aba nova), só acrescenta:
- `fato_tratativa_extintor`: 1 linha = 1 tratativa. `escopo` cliente (vale para o cliente inteiro: o `cliente_id` do
  cadastro, nunca o nome, e o `usina_id` vazio) ou usina (o `usina_id` e o `cliente_id` dela). `data_id` é o dia que a
  pessoa escolhe (hoje por padrão, nunca no futuro); `decidida_em`, a hora em que gravou. Quem registrou só pelo
  código (HMAC); o nome e a observação (até 300 letras) só cifrados (o Cofre, regra 8), como nas decisões. Assinada
  (HMAC, rótulo `nexus:hseq:tratativas`), para o livro dizer se a linha foi mexida fora do Nexus.

Qual aparece em cada linha da tabela (`ultima`): no cliente, a mais nova entre as do cliente e as das usinas dele; na
usina, a mais nova que vale para ela, contando as do cliente inteiro. "A mais nova" é pelo dia da tratativa e, no
mesmo dia, pela hora em que foi gravada.

Quem registra: o mesmo de quem decide nos extintores (o administrador e o setor Segurança, `decisoes.pode_decidir`),
sempre com login de pessoa (`decisoes._quem`).
"""
import hashlib
import hmac
import json
import threading
import time
from datetime import date, datetime
from pathlib import Path

from ..dados import fatos as D
from ..dados import livros
from . import decisoes as DEC

LIVRO, NOME_LIVRO = "nexus_hseq_extintores_tratativas", "Nexus · tratativas da Segurança sobre os extintores"
ABA = "fato_tratativa_extintor"
CAB = ("decidida_em", "data_id", "cliente_id", "usina_id", "escopo", "tipo", "decidida_por_hmac", "dados_cifrados",
       "assinatura")
TIPOS = {"email": "Cliente notificado por e-mail", "recarga_agendada": "Recarga agendada",
         "os_recarga": "OS de recarga aberta", "troca": "Troca realizada", "aguardando": "Aguardando cliente",
         "outro": "Outro"}
ESCOPOS = ("cliente", "usina")
OBS_MAX = DEC.OBS_MAX
TTL_S = 60
ROTULO_CHAVE = b"nexus:hseq:tratativas"
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(DEC.Recusada):
    """Nada foi gravado: o texto diz por quê (a tela mostra, como nas decisões)."""


def _agora() -> datetime:
    """O relógio da tela (`visao._agora`, Brasília): a data da caixa e o "não no futuro" contam o mesmo dia."""
    from ..campo import visao
    return visao._agora()


def _int(v) -> int | None:
    try:
        return int(float(v)) if D._txt(v) else None
    except (TypeError, ValueError):
        return None


# ── ler ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _arquivo_local(cfg) -> Path | None:
    p = cfg.get("NEXUS_HSEQ_TRATATIVAS_ARQUIVO")
    return Path(p) if p else None


def _ler_cru(cfg) -> list[dict]:
    """As linhas lidas agora. Livro que ainda não existe = vazio; erro de leitura sobe. Teste sem o arquivo nunca vai à
    rede."""
    loc = _arquivo_local(cfg)
    if loc is not None:
        try:
            return [dict(x) for x in json.loads(loc.read_text(encoding="utf-8")).get(ABA) or []]
        except FileNotFoundError:
            return []
    if cfg.get("TESTING"):
        return []
    from ..pcm.motivos import _banco
    base, sessao = _banco(cfg)
    a = livros.abas_conferidas(base, sessao, LIVRO, (ABA,))      # "não li" não vira "nenhuma tratativa"
    return list(livros._linhas(base, sessao, a[ABA])) if ABA in a else []


def ler(cfg, forcar: bool = False) -> dict:
    """{"linhas", "erro", "lido_em"}, guardado por 1 minuto. Leitura que falha devolve a última boa com o erro."""
    chave = str(_arquivo_local(cfg) or "banco")
    g = _CACHE.get(chave)
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        linhas = _ler_cru(cfg)
    except Exception as ex:  # noqa: BLE001 — banco fora, rede: a tela diz
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(g, erro=erro, velha=True) if g else {"linhas": [], "erro": erro, "lido_em": None}
    g = _CACHE[chave] = {"linhas": linhas, "erro": "", "lido_em": time.time()}
    return g


def limpar() -> None:
    _CACHE.clear()


# ── o que a tela mostra ───────────────────────────────────────────────────────────────────────────────────────
def _ctx(quando: str) -> str:
    return f"hseq/tratativa/{quando}"


def _dia(data_id) -> date | None:
    try:
        return datetime.strptime(D._txt(data_id)[:8], "%Y%m%d").date()
    except ValueError:
        return None


def lista(cfg, est: dict) -> list[dict]:
    """As tratativas decifradas, da mais nova para a mais velha: {quando, dia, escopo, cliente_id, usina_id, tipo,
    tipo_txt, quem, obs}. Sem a chave do cadastro, quem e a observação vazios."""
    cofre = DEC._cofre(cfg)
    out = []
    for x in est.get("linhas") or []:
        quando = D._txt(x.get("decidida_em"))
        dados = DEC._decifrar(cofre, x, _ctx(quando))
        tipo = D._txt(x.get("tipo"))
        out.append({"quando": quando, "dia": _dia(x.get("data_id")), "escopo": D._txt(x.get("escopo")),
                    "cliente_id": _int(x.get("cliente_id")), "usina_id": _int(x.get("usina_id")), "tipo": tipo,
                    "tipo_txt": TIPOS.get(tipo, tipo), "quem": dados.get("quem", ""), "obs": dados.get("obs", "")})
    return sorted(out, key=lambda t: (t["dia"] or date.min, t["quando"]), reverse=True)


def do_cliente(todas: list, cliente_id) -> list:
    """As do cliente: as do cliente inteiro e as de cada usina dele."""
    return [t for t in todas if cliente_id and t["cliente_id"] == cliente_id]


def da_usina(todas: list, usina_id, cliente_id) -> list:
    """As que valem para a usina: as dela e as do cliente inteiro dela."""
    return [t for t in todas if (usina_id and t["escopo"] == "usina" and t["usina_id"] == usina_id)
            or (cliente_id and t["escopo"] == "cliente" and t["cliente_id"] == cliente_id)]


def resumo(ts: list) -> dict | None:
    """A Evolução de uma linha: a última (a mais nova) e quantas; None sem nenhuma."""
    return {"ultima": ts[0], "n": len(ts)} if ts else None


# ── gravar ────────────────────────────────────────────────────────────────────────────────────────────────────
def assinatura(linha: dict, chave_base: str) -> str:
    """HMAC-SHA256 em hex, com a chave derivada da NEXUS_PESSOA_HMAC (`ROTULO_CHAVE`), do texto
    "tratativa|escopo|cliente_id|usina_id|tipo|data_id|decidida_em". Sem chave, ""."""
    base = (chave_base or "").strip()
    if not base:
        return ""
    chave = hmac.new(base.encode("utf-8"), ROTULO_CHAVE, hashlib.sha256).digest()
    partes = ("tratativa", linha.get("escopo"), linha.get("cliente_id"), linha.get("usina_id"), linha.get("tipo"),
              linha.get("data_id"), linha.get("decidida_em"))
    return hmac.new(chave, "|".join(D._txt(p) for p in partes).encode("utf-8"), hashlib.sha256).hexdigest()


def _gravar_cru(cfg, linhas: list) -> None:
    vazio = (lambda v: None if v in ("", None) else v)      # noqa: E731
    tabelas = {ABA: (list(CAB), [[vazio(x.get(c)) for c in CAB] for x in linhas])}
    loc = _arquivo_local(cfg)
    if loc is not None:
        loc.parent.mkdir(parents=True, exist_ok=True)
        tmp = loc.with_suffix(".tmp")
        tmp.write_text(json.dumps({ABA: [dict(zip(CAB, l)) for l in tabelas[ABA][1]]}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(loc)
        return
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    from ..pcm.motivos import _banco
    base, sessao = _banco(cfg)
    livros.publicar(LIVRO, NOME_LIVRO, tabelas, base=base, token=token, sessao=sessao)


def data_da_tela(texto: str, hoje: date) -> date:
    """O dia que a pessoa escolheu, em dd/mm/aaaa (vazio = hoje); no futuro ou fora do formato, Recusada."""
    t = D._txt(texto)
    if not t:
        return hoje
    try:
        d = datetime.strptime(t, "%d/%m/%Y").date()
    except ValueError:
        raise Recusada("A data vai como dd/mm/aaaa (ex.: 23/11/2026).") from None
    if d > hoje:
        raise Recusada("A tratativa não pode ter data no futuro.")
    return d


def registrar(cfg, *, escopo: str, cliente_id, usina_id, tipo: str, dia: str, obs: str, usuario: dict | None,
              pode: bool) -> str:
    """Grava UMA tratativa. O texto do que foi feito; Recusada com o motivo. Quem chama confere que a usina e o cliente
    existem na tela (a torre)."""
    if not pode:
        raise Recusada("Só quem é da Segurança ou administrador registra tratativas.")
    if tipo not in TIPOS:
        raise Recusada("Escolha o que foi feito.")
    if escopo not in ESCOPOS:
        raise Recusada("Escolha para quem vale: o cliente inteiro ou uma usina dele.")
    cid, uid = _int(cliente_id), _int(usina_id)
    if escopo == "cliente" and not cid:
        raise Recusada("Este cliente não está no cadastro do Nexus: registre a tratativa numa usina dele.")
    if escopo == "usina" and not uid:
        raise Recusada("Esta usina não está no cadastro do Nexus: acerte o cadastro antes de registrar.")
    texto = " ".join(D._txt(obs).split())
    if len(texto) > OBS_MAX:
        raise Recusada(f"A observação vai até {OBS_MAX} letras.")
    if tipo == "outro" and not texto:
        raise Recusada("Para \"Outro\", escreva na observação o que foi feito.")
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        raise Recusada("Este Nexus não tem a NEXUS_PESSOA_HMAC: nada foi gravado.")
    agora = _agora()
    d = data_da_tela(dia, agora.date())
    codigo, nome = DEC._quem(cfg, usuario)
    cofre = DEC._cofre(cfg)
    if texto and cofre is None:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): a observação vai cifrada, e sem "
                       "ela nada é gravado.")
    quando = agora.isoformat(timespec="seconds")
    dados = {k: v for k, v in {"quem": nome, "obs": texto}.items() if v}
    nova = {"decidida_em": quando, "data_id": int(d.strftime("%Y%m%d")), "cliente_id": cid or "",
            "usina_id": uid if escopo == "usina" else "", "escopo": escopo, "tipo": tipo, "decidida_por_hmac": codigo,
            "dados_cifrados": cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(quando)) if cofre and dados else ""}
    nova["assinatura"] = assinatura(nova, cfg.get("NEXUS_PESSOA_HMAC"))
    with _TRAVA:
        try:
            linhas = _ler_cru(cfg)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler as tratativas no banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.") from ex
        linhas = linhas + [nova]
        _gravar_cru(cfg, linhas)
        _CACHE[str(_arquivo_local(cfg) or "banco")] = {"linhas": linhas, "erro": "", "lido_em": time.time()}
    return f"Tratativa registrada: {TIPOS[tipo].lower()} em {d:%d/%m/%Y}."
