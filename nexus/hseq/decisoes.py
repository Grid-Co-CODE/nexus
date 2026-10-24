"""As decisões da Segurança sobre os extintores (24/10/2026): o Nexus é a FONTE.

Levi, 24/10/2026, em duas rodadas. A 1ª: a pessoa da Segurança, diante do extintor que a equipe não reconheceu, "pode
aceitar e aí o extintor vai sumir ou solicitar que o técnico faça uma nova ronda, se ele solicitar vai aparecer no app de
campo 'ronda pendente' 'O TST solicitou uma nova ronda'". A 2ª, que corrigiu a 1ª: "pedir uma nova ronda é uma nova ronda
do zero então será por usina, por extintor é só o botão de aceitar, quando a TST aceita o extintor é excluído e vai para
um histórico de extintores excluídos com o motivo 'Não reconhecido em campo'"; e, no lugar de editar a quantidade de
extintores da usina, "como cada extintor tem um cadastro unitário então o certo seria (...) clicar com o botão direito e
poder excluir o extintor".

O dado (livro `nexus_hseq_extintores`, registrado em `nexus/dados/catalogo.py` antes da 1ª gravação; regras em
`nexus/dados/CLAUDE.md`), só acrescenta:
- `fato_exclusao_extintor`: 1 linha = 1 exclusão (a baixa) de 1 extintor pela Segurança, com o motivo (`MOTIVOS`): o não
  reconhecido aceito leva "nao_reconhecido" e o dia da marca do App que aceitou (`marca_dia`); a exclusão pelo botão
  direito, "retirado", "duplicado" ou "outro". O excluído some das telas e das contas do Nexus e vai para o histórico
  de excluídos; volta sozinho se uma conferência de DEPOIS do dia da exclusão aparecer (o extintor existe).
- `fato_pedido_ronda`: 1 linha = 1 pedido da Segurança de uma NOVA RONDA de extintores, do zero, em 1 usina, com o nome
  que o App usa para a usina (`usina_app`). Fica pendente até TODOS os extintores da usina chegarem conferidos (ou
  marcados como não reconhecidos) DEPOIS do pedido, pela hora (`rondas_pendentes`, a mesma regra do App).
Em claro: os IDs, o código do extintor, o motivo (domínio), os dias e os códigos HMAC. Quem decidiu (o nome) e a
observação vão só cifrados (o Cofre, regra 8). Cada linha vai assinada (`assinatura`, HMAC com a chave derivada da
NEXUS_PESSOA_HMAC): o App lê o livro pela leitura aberta da API e só aplica a linha assinada.

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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..dados import fatos as D
from ..dados import livros

LIVRO, NOME_LIVRO = "nexus_hseq_extintores", "Nexus · decisões da Segurança sobre os extintores"
ABA_EXC, ABA_RONDA = "fato_exclusao_extintor", "fato_pedido_ronda"
CAB_EXC = ("decidida_em", "data_id", "usina_id", "codigo", "motivo", "marca_dia", "decidida_por_hmac", "dados_cifrados",
           "assinatura")
CAB_RONDA = ("decidida_em", "data_id", "usina_id", "usina_app", "decidida_por_hmac", "dados_cifrados", "assinatura")
# o motivo da exclusão (domínio fechado: valor fora não grava). O não reconhecido aceito é o único que vem do Aceitar
MOTIVOS = {"nao_reconhecido": "Não reconhecido em campo", "retirado": "Retirado da usina",
           "duplicado": "Duplicado no cadastro", "outro": "Outro motivo"}
MOTIVOS_DO_BOTAO_DIREITO = ("retirado", "duplicado", "outro")
SETOR = "seguranca"                          # o nome do setor sem acento nem caixa (Base → Acessos)
OBS_MAX = 300
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
    """Excluir extintor, aceitar o não reconhecido e pedir nova ronda: o administrador e quem é do setor Segurança."""
    return bool(admin) or _norm((setor or {}).get("nome")) == SETOR


def _int(v) -> int | None:
    try:
        return int(float(v)) if D._txt(v) else None
    except (TypeError, ValueError):
        return None


def _dia(iso) -> date | None:
    try:
        return date.fromisoformat(D._txt(iso)[:10])
    except ValueError:
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
        return {a: [dict(x) for x in d.get(a) or []] for a in (ABA_EXC, ABA_RONDA)}
    if cfg.get("TESTING"):
        return {ABA_EXC: [], ABA_RONDA: []}
    from ..pcm.motivos import _banco
    base, sessao = _banco(cfg)
    a = livros.abas(base, sessao, LIVRO)
    return {aba: (list(livros._linhas(base, sessao, a[aba])) if aba in a else []) for aba in (ABA_EXC, ABA_RONDA)}


def ler(cfg, forcar: bool = False) -> dict:
    """{"exclusoes", "rondas", "erro", "lido_em"}: o livro, guardado por 1 minuto. Leitura que falha devolve a última
    boa (`velha`) com o erro; sem nenhuma, nada, com o erro (a tela diz e não grava sem saber o que há)."""
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
        return {"exclusoes": [], "rondas": [], "erro": erro, "lido_em": None}
    g = {"exclusoes": cru[ABA_EXC], "rondas": cru[ABA_RONDA], "erro": "", "lido_em": time.time()}
    _CACHE[chave] = g
    return g


def limpar() -> None:
    _CACHE.clear()


def _ordem(linhas):
    """Da mais velha para a mais nova (a ordem do livro desempata duas no mesmo segundo)."""
    return [x for _i, x in sorted(enumerate(linhas), key=lambda t: (D._txt(t[1].get("decidida_em")), t[0]))]


def exclusoes_por_codigo(est: dict) -> dict:
    """{código: a última exclusão}."""
    out = {}
    for x in _ordem(est.get("exclusoes") or []):
        out[D._txt(x.get("codigo"))] = x
    return out


def excluido(x: dict, exc: dict | None) -> bool:
    """O extintor está excluído: há exclusão e nenhuma conferência num dia DEPOIS dela (a conferência depois prova que
    ele existe, e ele volta sozinho). No mesmo dia vale a exclusão."""
    if not exc:
        return False
    dia = _dia(exc.get("decidida_em"))
    conf = x.get("conferencia")
    return not (dia and conf and conf > dia)


def separar(extintores: list, nao_reconhecidos: list, est: dict) -> tuple[list, list, list]:
    """(extintores, não reconhecidos, excluídos): tira das duas listas da tela os que a Segurança excluiu e ainda valem
    (`excluido`); os excluídos vêm com a exclusão (`exclusao`) para o histórico."""
    exc = exclusoes_por_codigo(est)
    fora, ext, nr = [], [], []
    for lista, destino in ((extintores, ext), (nao_reconhecidos, nr)):
        for x in lista:
            e = exc.get(x["codigo"])
            if excluido(x, e):
                fora.append(dict(x, exclusao=e))
            else:
                destino.append(x)
    return ext, nr, fora


def _hora(iso) -> datetime | None:
    """Um ISO com hora (o `decidida_em` com -03:00, a "Recebida em" do App em UTC); sem fuso, Brasília."""
    try:
        d = datetime.fromisoformat(D._txt(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone(timedelta(hours=-3)))


def rondas_pendentes(est: dict, por_usina: dict, recebidas: dict) -> dict:
    """{usina_id: o último pedido de nova ronda ainda pendente, com `feitos` e `total`}. A ronda é do zero (Levi,
    24/10/2026: "pedir uma nova ronda é uma nova ronda do zero"): o pedido só sai quando TODOS os extintores atuais da
    usina (`por_usina` = {usina_id: [extintores]}, os excluídos já fora) têm conferência RECEBIDA pelo App depois dele
    (`recebidas` = {código: a hora}, a "Recebida em" do livro de conferências) ou marca de não reconhecido depois dele.
    Pela hora, não pelo dia: pedido às 10h e ronda às 14h do mesmo dia é atendido. A regra é a MESMA do App de Campo
    (combinada com ele em 24/10/2026, v296), que mostra a ronda pendente à equipe. A marca de não reconhecido só com o
    dia conta do dia seguinte ao pedido em diante (nunca dá por feito o que pode ter sido antes). Usina sem extintor
    nenhum segue pendente: nada prova a ronda."""
    ult = {}
    for x in _ordem(est.get("rondas") or []):
        uid = _int(x.get("usina_id"))
        if uid:
            ult[uid] = x
    out = {}
    for uid, x in ult.items():
        t = _hora(x.get("decidida_em"))
        exts = por_usina.get(uid) or []

        def feito(e):
            r, marca = recebidas.get(e.get("codigo")), e.get("marca_em")
            if t is None:
                return False
            if r and r > t:
                return True
            if marca:
                return marca > t
            return bool(e.get("nao_reconhecido") and e["nao_reconhecido"] > t.astimezone(timezone(timedelta(hours=-3))).date())
        n = sum(1 for e in exts if feito(e))
        if not exts or n < len(exts):
            out[uid] = dict(x, feitos=n, total=len(exts))
    return out


def historico(cfg, est: dict, extintores_por_codigo: dict) -> list[dict]:
    """O histórico de excluídos, a exclusão mais nova primeiro: {quando, codigo, usina_id, motivo, motivo_txt, marca_dia,
    quem, obs, ext (a linha do extintor no livro do App, se ainda estiver lá), voltou (o dia da conferência que o trouxe
    de volta)}. Quem e a observação saem decifrados; sem a chave do cadastro, vazios."""
    cofre = _cofre(cfg)
    out = []
    for x in reversed(_ordem(est.get("exclusoes") or [])):
        cod, quando = D._txt(x.get("codigo")), D._txt(x.get("decidida_em"))
        dados = _decifrar(cofre, x, _ctx("exclusao", cod, quando))
        e = extintores_por_codigo.get(cod)
        dia = _dia(quando)
        voltou = e["conferencia"] if e and e.get("conferencia") and dia and e["conferencia"] > dia else None
        out.append({"quando": quando, "codigo": cod, "usina_id": _int(x.get("usina_id")), "motivo": D._txt(x.get("motivo")),
                    "motivo_txt": MOTIVOS.get(D._txt(x.get("motivo")), D._txt(x.get("motivo"))),
                    "marca_dia": D._txt(x.get("marca_dia")), "quem": dados.get("quem", ""), "obs": dados.get("obs", ""),
                    "ext": e, "voltou": voltou})
    return out


# ── gravar ────────────────────────────────────────────────────────────────────────────────────────────────────
def assinatura(linha: dict, aba: str, chave_base: str) -> str:
    """HMAC-SHA256 em hex minúsculo com a chave derivada da NEXUS_PESSOA_HMAC (`ROTULO_CHAVE`): do texto
    "exclusao|código|motivo|marca_dia|decidida_em" ou "ronda|usina_id|usina_app|decidida_em". Sem chave: "" (o App não
    aplica a linha)."""
    base = (chave_base or "").strip()
    if not base:
        return ""
    chave = hmac.new(base.encode("utf-8"), ROTULO_CHAVE, hashlib.sha256).digest()
    if aba == ABA_EXC:
        partes = ("exclusao", linha.get("codigo"), linha.get("motivo"), linha.get("marca_dia"), linha.get("decidida_em"))
    else:
        partes = ("ronda", linha.get("usina_id"), linha.get("usina_app"), linha.get("decidida_em"))
    return hmac.new(chave, "|".join(D._txt(p) for p in partes).encode("utf-8"), hashlib.sha256).hexdigest()


def _cofre(cfg):
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        return None
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _ctx(tipo: str, chave, quando: str) -> str:
    return f"hseq/{tipo}/{chave}/{quando}"


def _decifrar(cofre, linha: dict, ctx: str) -> dict:
    cif = D._txt(linha.get("dados_cifrados"))
    if not cofre or not cif:
        return {}
    try:
        return json.loads(cofre.decifrar(cif, ctx))
    except Exception:  # noqa: BLE001 — cifra de outra chave ou linha mexida: sem os dados
        return {}


def _gravar_cru(cfg, cru: dict) -> None:
    """Troca o livro inteiro e confere (`livros.publicar` relê e compara a contagem). Na cópia de prova, o arquivo."""
    vazio = (lambda v: None if v in ("", None) else v)      # noqa: E731
    tabelas = {aba: (list(cab), [[vazio(x.get(c)) for c in cab] for x in cru[aba]])
               for aba, cab in ((ABA_EXC, CAB_EXC), (ABA_RONDA, CAB_RONDA))}
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


def _quem(cfg, usuario: dict | None) -> tuple[str, str]:
    """(o código de quem decide, o nome); sem login de pessoa (a senha de administrador), Recusada."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    email = str((usuario or {}).get("email") or "").strip().lower()
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email) if email else ""
    if not codigo:
        raise Recusada("Entre com o seu login (Microsoft ou Fracttal) para decidir: a senha de administrador não diz "
                       "quem é, e o histórico guarda quem fez.")
    return codigo, " ".join(str((usuario or {}).get("nome") or "").split())


def _gravar(cfg, aba: str, nova: dict, ctx: str, dados: dict) -> None:
    if not str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip():
        raise Recusada("Este Nexus não tem a NEXUS_PESSOA_HMAC: a linha iria sem assinatura e o App não a aplicaria. "
                       "Nada foi gravado.")
    dados = {k: v for k, v in dados.items() if v}
    if dados.get("obs") and _cofre(cfg) is None:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): a observação vai cifrada, e sem "
                       "ela nada é gravado.")
    cofre = _cofre(cfg)
    nova["dados_cifrados"] = cofre.cifrar(json.dumps(dados, ensure_ascii=False), ctx) if cofre and dados else ""
    with _TRAVA:
        try:
            cru = _ler_cru(cfg)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler as decisões no banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.") from ex
        nova["assinatura"] = assinatura(nova, aba, cfg.get("NEXUS_PESSOA_HMAC"))
        cru[aba] = cru[aba] + [nova]
        _gravar_cru(cfg, cru)
        _CACHE[str(_arquivo_local(cfg) or "banco")] = {"exclusoes": cru[ABA_EXC], "rondas": cru[ABA_RONDA], "erro": "",
                                                       "lido_em": time.time()}


def excluir(cfg, *, extintor: dict, motivo: str, usuario: dict | None, pode: bool, obs: str = "") -> str:
    """Exclui (dá baixa) UM extintor: o não reconhecido aceito (`motivo` nao_reconhecido, com a marca do App) ou o de
    qualquer linha pelo botão direito (retirado, duplicado, outro). O texto do que foi feito; Recusada com o motivo."""
    if not pode:
        raise Recusada("Só quem é da Segurança ou administrador exclui extintores.")
    if motivo not in MOTIVOS:
        raise Recusada("Motivo que o Nexus não conhece: escolha um da lista.")
    marca = extintor.get("nao_reconhecido")
    if motivo == "nao_reconhecido" and not marca:
        raise Recusada("Este extintor não está marcado como não reconhecido: use o botão direito para excluir.")
    texto = " ".join(D._txt(obs).split())[:OBS_MAX]
    if motivo == "outro" and not texto:
        raise Recusada("Para \"Outro motivo\", escreva qual.")
    codigo, nome = _quem(cfg, usuario)
    agora = _agora()
    quando = agora.isoformat(timespec="seconds")
    _gravar(cfg, ABA_EXC, {"decidida_em": quando, "data_id": int(agora.strftime("%Y%m%d")),
                           "usina_id": extintor.get("usina_id") or "", "codigo": extintor["codigo"], "motivo": motivo,
                           "marca_dia": marca.isoformat() if motivo == "nao_reconhecido" else "",
                           "decidida_por_hmac": codigo},
            _ctx("exclusao", extintor["codigo"], quando), {"quem": nome, "obs": texto})
    return f"{extintor['ext']} excluído da {extintor['usina']} ({MOTIVOS[motivo].lower()}); está no histórico de excluídos."


def pedir_ronda(cfg, *, usina_id: int, usina: str, usina_app: str, usuario: dict | None, pode: bool) -> str:
    """Pede à equipe uma NOVA RONDA de extintores, do zero, na usina (o App mostra a ronda pendente)."""
    if not pode:
        raise Recusada("Só quem é da Segurança ou administrador pede nova ronda.")
    if not usina_id:
        raise Recusada("Esta usina não está no cadastro do Nexus: acerte o cadastro antes de pedir a ronda.")
    if not D._txt(usina_app):
        raise Recusada("Não achei o nome que o App usa para esta usina: atualize a página.")
    codigo, nome = _quem(cfg, usuario)
    agora = _agora()
    quando = agora.isoformat(timespec="seconds")
    _gravar(cfg, ABA_RONDA, {"decidida_em": quando, "data_id": int(agora.strftime("%Y%m%d")), "usina_id": usina_id,
                             "usina_app": D._txt(usina_app), "decidida_por_hmac": codigo},
            _ctx("ronda", usina_id, quando), {"quem": nome})
    return f"Nova ronda de extintores pedida para a {usina}: o App mostra à equipe como ronda pendente."
