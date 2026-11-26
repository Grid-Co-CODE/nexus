"""O controle dos e-mails automáticos do App de Campo pelo Nexus (24/11/2026): o livro `nexus_email_controle`.

Levi, pela sessão do App: "Gostaria de poder controlar esses e-mails automáticos ou ter pelo menos um controle! E
gostaria que estivesse no Nexus". O Nexus escreve a regra; o App (v380, no ar desde 24/11 12:45) relê a cada 5 minutos e
aplica. O contrato, fechado no mesmo dia com a sessão "App de campo sub", está no `nexus/cadastro/CLAUDE.md` (seção
"E-mails automáticos"); a conta do App é a `_email_regras` do function_app.py da v380.

1 linha = 1 mudança de 1 tipo (o ESTADO INTEIRO do tipo depois dela: ligado, modo, a lista, se substitui o padrão). Só
acrescenta: o histórico de quem mudou o quê sai das próprias linhas. Vale, por tipo, a linha válida de `alterado_em` mais
recente; no empate, a de baixo no livro. Sem nenhuma, o App segue com o App Setting dele.

O que vai em claro (a API do banco lê sem login): o tipo, ligado, modo, se substitui, quem mudou (HMAC do e-mail) e o
motivo, que a tela recusa com e-mail ou nome de pessoa. A lista de e-mails vai cifrada (AES-256-GCM numa chave HKDF da
NEXUS_PESSOA_HMAC, que o App tem; `cifra.aead_derivada`), amarrada ao tipo, e a linha vai assinada (HMAC da mesma
chave): sem a NEXUS_PESSOA_HMAC nada se grava, porque o App descartaria a linha.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from ..cadastro import cifra
from ..dados import livros

LIVRO, NOME_LIVRO, ABA = "nexus_email_controle", "Nexus · controle dos e-mails automáticos do App", "fato_email_regra"
# as colunas, nesta ordem, são o contrato com o App; coluna nova só no FIM, nos dois lados
CAB = ("tipo", "ligado", "modo", "destinatarios", "substitui_padrao", "alterado_por", "alterado_em", "motivo",
       "assinatura")
# os 7 tipos que o App conhece (EMAIL_TIPOS da v380): linha de outro tipo o App descarta
TIPOS = ("pt_aviso", "luvas_tst", "auditoria_diaria", "seguranca_semanal", "seguranca_relato", "encaminhamento",
         "avulso")
MODOS = ("normal", "teste")
ROTULO_CHAVE = b"nexus:email:controle"          # a chave da assinatura: HMAC(NEXUS_PESSOA_HMAC, este rótulo)
INFO_CIFRA = b"nexus:email:controle/v1"         # o info do HKDF da cifra da lista
MOTIVO_MIN, MOTIVO_MAX = 8, 200
LISTA_MAX = 30
# os destinatários digitados à mão (as caixas, como a do COS) só destes domínios: o e-mail sai pela conta da Grid, e um
# endereço de fora numa regra do Nexus é exatamente o vazamento que o controle existe para evitar
DOMINIOS = ("gridco.com.br", "gridco.com")
TTL_S = 60
_EMAIL = re.compile(r"[^\s<>()\[\],;:\"']+@[^\s<>()\[\],;:\"']+")
_EMAIL_INTEIRO = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Alvo:
    """De quem é a regra (25/11/2026): a do App de Campo (o livro do contrato com o App, os 7 tipos dele) ou a dos e-mails
    que o próprio Nexus manda (livro à parte, os tipos "nx_..." de `nexus/emails/tipos.py`). Mesmo formato, mesma cifra e
    mesma assinatura: uma conta só para os dois. Livro à parte porque o App descarta (e conta como inválida) a linha de
    tipo que ele não conhece."""

    def __init__(self, chave: str, livro: str, nome: str, aba: str, tipos, quem: str):
        self.chave, self.livro, self.nome, self.aba, self._tipos, self.quem = chave, livro, nome, aba, tipos, quem

    def tipos(self) -> tuple:
        return tuple(self._tipos() if callable(self._tipos) else self._tipos)


def _tipos_do_nexus() -> tuple:
    from ..emails import tipos
    return tipos.ids()


APP = Alvo("app", LIVRO, NOME_LIVRO, ABA, TIPOS, "o App")
NEXUS = Alvo("nexus", "nexus_email_regras", "Nexus · regras dos e-mails que o Nexus manda", ABA, _tipos_do_nexus,
             "o Nexus")


def alvo_do_tipo(tipo: str) -> Alvo:
    return NEXUS if str(tipo or "").startswith("nx_") else APP


class Recusada(ValueError):
    """Nada foi gravado; o texto diz por quê, para a tela."""


def _txt(v) -> str:
    """A célula como o App a lê (`_nexus_atr_txt`): sem espaço nas pontas, None = "", inteiro sem ".0"."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v if v is not None else "").strip()


def _sim(v) -> bool:
    return _txt(v).lower() == "sim"


def agora_iso() -> str:
    """ISO UTC com segundos, como o contrato pede ("2026-11-24T15:51:04Z")."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── a conta (a mesma do App; mudou aqui, muda lá) ─────────────────────────────────────────────────────────────
def _base(chave_base) -> str:
    return str(chave_base or "").strip()


def assinatura(linha: dict, chave_base: str) -> str:
    """HMAC-SHA256 em hex minúsculo de "tipo|ligado|modo|destinatarios|substitui_padrao|alterado_em", com a chave
    HMAC-SHA256(NEXUS_PESSOA_HMAC, "nexus:email:controle"). Sem chave: ""."""
    base = _base(chave_base)
    if not base:
        return ""
    chave = hmac.new(base.encode("utf-8"), ROTULO_CHAVE, hashlib.sha256).digest()
    texto = "|".join(_txt(linha.get(k)) for k in
                     ("tipo", "ligado", "modo", "destinatarios", "substitui_padrao", "alterado_em"))
    return hmac.new(chave, texto.encode("utf-8"), hashlib.sha256).hexdigest()


def _contexto(tipo: str) -> str:
    return f"nexus/email-controle/{tipo}"


def cifrar_lista(lista: list[str], tipo: str, chave_base: str) -> str:
    """A lista (já normalizada) cifrada no formato "cf1:"; vazia = "" (o App lê como lista vazia)."""
    if not lista:
        return ""
    aead = cifra.aead_derivada(_base(chave_base).encode("utf-8"), INFO_CIFRA)
    return cifra.cifrar_com(aead, json.dumps(list(lista), ensure_ascii=False), _contexto(tipo))


def abrir_lista(valor, tipo: str, chave_base: str) -> list[str]:
    """A lista de e-mails do campo cifrado ("" = vazia). Fora do formato, cifra que não abre ou que não é lista:
    `cifra.CifraErro` (a linha não vale, como no App)."""
    v = _txt(valor)
    if not v:
        return []
    aead = cifra.aead_derivada(_base(chave_base).encode("utf-8"), INFO_CIFRA)
    texto = cifra.decifrar_com(aead, v, _contexto(tipo))
    try:
        lst = json.loads(texto)
    except ValueError:
        raise cifra.CifraErro("a lista aberta não é JSON") from None
    if not isinstance(lst, list):
        raise cifra.CifraErro("a lista aberta não é lista")
    return normalizar_lista(lst)


def normalizar_lista(xs) -> list[str]:
    """Minúsculas, sem espaço, sem repetição, na ordem; o que não tem "@" sai (a régua `_email_lista` do App)."""
    out = []
    for x in xs or []:
        x = str(x or "").strip().lower()
        if "@" in x and x not in out:
            out.append(x)
    return out


def conferir(linha: dict, chave_base: str, alvo: Alvo | None = None) -> tuple[bool, str, list[str]]:
    """(vale, o motivo de não valer, a lista aberta). As regras do App, na mesma ordem."""
    alvo = alvo or APP
    tipo, ligado, modo = _txt(linha.get("tipo")), _txt(linha.get("ligado")).lower(), _txt(linha.get("modo")).lower()
    sub, em = _txt(linha.get("substitui_padrao")).lower(), _txt(linha.get("alterado_em"))
    if tipo not in alvo.tipos():
        return False, f"tipo que {alvo.quem} não conhece", []
    if ligado not in ("sim", "não", "nao") or modo not in MODOS or sub not in ("sim", "não", "nao", ""):
        return False, "valor fora do domínio", []
    if not em:
        return False, "sem a hora da mudança", []
    a = _txt(linha.get("assinatura")).lower()
    if not a or not hmac.compare_digest(a.encode("utf-8"), assinatura(linha, chave_base).encode("utf-8")):
        return False, "assinatura não confere", []
    try:
        return True, "", abrir_lista(linha.get("destinatarios"), tipo, chave_base)
    except cifra.CifraErro:
        return False, "a lista cifrada não abre", []


def regra_da_linha(linha: dict, lista: list[str]) -> dict:
    return {"tipo": _txt(linha.get("tipo")), "ligado": _sim(linha.get("ligado")),
            "modo": _txt(linha.get("modo")).lower(), "destinatarios": list(lista),
            "substitui": _sim(linha.get("substitui_padrao")), "alterado_em": _txt(linha.get("alterado_em")),
            "alterado_por": _txt(linha.get("alterado_por")), "motivo": _txt(linha.get("motivo"))}


def vigentes(linhas: list[dict], chave_base: str, alvo: Alvo | None = None) -> dict:
    """{tipo: regra} das que valem, pela régua do App: a válida de `alterado_em` mais recente, no empate a de baixo."""
    melhor = {}
    for ln in linhas:
        ok, _m, lista = conferir(ln, chave_base, alvo)
        if not ok:
            continue
        r = regra_da_linha(ln, lista)
        if r["tipo"] not in melhor or r["alterado_em"] >= melhor[r["tipo"]]["alterado_em"]:
            melhor[r["tipo"]] = r
    return melhor


def efeito(regra: dict | None, quem: str = "o App") -> str:
    """O que quem manda faz com a regra, numa frase (a régua `_email_controle` da v380, a mesma da fila do Nexus)."""
    if not regra:
        return ("segue o App Setting (sem regra do Nexus)" if quem == "o App"
                else "segue o destino padrão do e-mail (sem regra)")
    if not regra["ligado"]:
        return f"desligado: {quem} não manda e registra \"desligado\""
    n = len(regra["destinatarios"])
    if regra["modo"] == "teste" and n:
        return f"teste: só para a lista ({n}), sem cópia, com \"[Teste]\" no assunto"
    if not n:
        return "ligado, para o destino padrão" + (" do App" if quem == "o App" else "")
    if regra["substitui"]:
        return f"ligado, só para a lista ({n}), sem cópia"
    return f"ligado, para o destino padrão mais a lista ({n})"


# ── o histórico: as próprias linhas ────────────────────────────────────────────────────────────────────────────
def historico(linhas: list[dict], chave_base: str, tipo: str | None = None, alvo: Alvo | None = None) -> list[dict]:
    """As mudanças, da mais nova à mais antiga: {quando, tipo, quem_hmac, motivo, vale, porque, regra, mudou: [textos],
    entrou, saiu}. O "de → para" é contra a válida anterior do mesmo tipo (a inválida não muda nada no App)."""
    out, anterior = [], {}
    ordem = sorted(enumerate(linhas), key=lambda t: (_txt(t[1].get("alterado_em")), t[0]))
    for _i, ln in ordem:
        t = _txt(ln.get("tipo"))
        ok, porque, lista = conferir(ln, chave_base, alvo)
        r = regra_da_linha(ln, lista)
        mudou, entrou, saiu = [], [], []
        if ok:
            a = anterior.get(t)
            if a is None:
                mudou.append("1ª regra do Nexus: " + efeito(r))
            else:
                if a["ligado"] != r["ligado"]:
                    mudou.append("ligou" if r["ligado"] else "desligou")
                if a["modo"] != r["modo"]:
                    mudou.append(f"modo {a['modo']} → {r['modo']}")
                if a["substitui"] != r["substitui"] and r["destinatarios"]:
                    mudou.append("passou a substituir o padrão" if r["substitui"] else "passou a somar ao padrão")
                entrou = [e for e in r["destinatarios"] if e not in a["destinatarios"]]
                saiu = [e for e in a["destinatarios"] if e not in r["destinatarios"]]
                if not (mudou or entrou or saiu):
                    mudou.append("sem mudança (só o motivo)")
            anterior[t] = r
        if tipo is None or t == tipo:
            out.append({"quando": r["alterado_em"], "tipo": t, "quem_hmac": r["alterado_por"], "motivo": r["motivo"],
                        "vale": ok, "porque": porque, "regra": r if ok else None, "mudou": mudou, "entrou": entrou,
                        "saiu": saiu})
    return list(reversed(out))


# ── o livro: o banco, ou um arquivo na cópia de prova ─────────────────────────────────────────────────────────
def _arquivo_local(cfg) -> Path | None:
    p = cfg.get("NEXUS_EMAIL_CONTROLE_ARQUIVO")
    return Path(p) if p else None


def _chave_arquivo(alvo: Alvo) -> str:
    # o arquivo da cópia de prova guarda os dois: a regra do App na chave de sempre, a do Nexus noutra
    return alvo.aba if alvo is APP else f"{alvo.chave}:{alvo.aba}"


def _ler_cru(cfg, alvo: Alvo | None = None) -> list[dict]:
    """As linhas, lidas agora. Livro que ainda não existe = vazio; erro de leitura sobe, e a listagem que não traz a aba
    do livro que existe também (`livros.abas_conferidas`). Teste sem o arquivo nunca vai à rede."""
    loc = _arquivo_local(cfg)
    if loc is not None:
        try:
            d = json.loads(loc.read_text(encoding="utf-8"))
        except FileNotFoundError:
            d = {}
        return [dict(x) for x in d.get(_chave_arquivo(alvo or APP)) or []]
    if cfg.get("TESTING"):
        return []
    alvo = alvo or APP
    from ..dados.conexao import banco_de
    base, sessao = banco_de(cfg)
    a = livros.abas_conferidas(base, sessao, alvo.livro, (alvo.aba,))
    return list(livros._linhas(base, sessao, a[ABA])) if ABA in a else []


def _gravar_cru(cfg, linhas: list[dict], alvo: Alvo | None = None) -> None:
    """Troca o livro inteiro (a API não acrescenta linha) e confere: `livros.publicar` relê e compara a contagem, e o
    catálogo o declara `so_cresce` (a gravação que encolheria é recusada). Na cópia de prova, o arquivo."""
    corpo = [[(None if x.get(c) in ("", None) else x.get(c)) for c in CAB] for x in linhas]
    alvo = alvo or APP
    loc = _arquivo_local(cfg)
    if loc is not None:
        loc.parent.mkdir(parents=True, exist_ok=True)
        try:
            d = json.loads(loc.read_text(encoding="utf-8"))
        except FileNotFoundError:
            d = {}
        d[_chave_arquivo(alvo)] = [dict(zip(CAB, l)) for l in corpo]
        tmp = loc.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(loc)
        return
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    from ..dados.conexao import banco_de
    base, sessao = banco_de(cfg)
    livros.publicar(alvo.livro, alvo.nome, {alvo.aba: (list(CAB), corpo)}, base=base, token=token, sessao=sessao)


def ler(cfg, forcar: bool = False, alvo: Alvo | None = None) -> dict:
    """{"linhas", "erro", "lido_em"}, guardado 1 minuto. Leitura que falha devolve a última boa com o erro; sem nenhuma,
    vazio com o erro (a tela não deixa gravar sem saber o que há no livro)."""
    alvo = alvo or APP
    chave = (str(_arquivo_local(cfg) or "banco"), alvo.chave)
    g = _CACHE.get(chave)
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        linhas = _ler_cru(cfg, alvo)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e não deixa gravar
        erro = f"{type(ex).__name__}"
        return dict(g, erro=erro, velha=True) if g else {"linhas": [], "erro": erro, "lido_em": None}
    g = {"linhas": linhas, "erro": "", "lido_em": time.time()}
    _CACHE[chave] = g
    return g


def limpar() -> None:
    _CACHE.clear()


# ── o que a tela manda ────────────────────────────────────────────────────────────────────────────────────────
def _sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s.lower()).split())


def conferir_motivo(motivo, nomes=()) -> str:
    """O motivo como vai ao livro (em claro: a API lê sem login). `Recusada` sem motivo, curto, longo, com e-mail ou com
    o nome de uma pessoa (o nome inteiro ou o primeiro e o último, de `nomes`)."""
    m = " ".join(str(motivo or "").split())
    if len(m) < MOTIVO_MIN:
        raise Recusada(f"Escreva o motivo da mudança (ao menos {MOTIVO_MIN} letras): nada foi gravado.")
    if len(m) > MOTIVO_MAX:
        raise Recusada(f"O motivo passa de {MOTIVO_MAX} letras: resuma. Nada foi gravado.")
    if _EMAIL.search(m) or "@" in m:
        raise Recusada("O motivo vai em claro para o banco, que qualquer sistema lê: tire o e-mail dele. Nada foi "
                       "gravado.")
    alvo = f" {_sem_acento(m)} "
    for n in nomes:
        p = _sem_acento(n).split()
        if len(p) < 2:
            continue
        for cand in {" ".join(p), f"{p[0]} {p[-1]}"}:
            if f" {cand} " in alvo:
                raise Recusada("O motivo vai em claro para o banco, que qualquer sistema lê: tire o nome da pessoa "
                               "(cite o papel, como \"a TST\" ou \"o supervisor\"). Nada foi gravado.")
    return m


def conferir_destinatarios(xs, conhecidos=()) -> list[str]:
    """A lista da regra: e-mails inteiros, minúsculos, sem repetição. O e-mail de uma pessoa conhecida (o cadastro, o
    Fracttal) vale; o digitado (a caixa do COS) só de `DOMINIOS`."""
    conhecidos = {str(c or "").strip().lower() for c in conhecidos}
    out = []
    for x in xs or []:
        e = str(x or "").strip().lower()
        if not e:
            continue
        if not _EMAIL_INTEIRO.match(e):
            raise Recusada(f"\"{e[:60]}\" não é um e-mail inteiro: nada foi gravado.")
        if e not in conhecidos and e.rsplit("@", 1)[1] not in DOMINIOS:
            raise Recusada(f"{e}: só e-mail da Grid ({', '.join('@' + d for d in DOMINIOS)}) ou de uma pessoa do "
                           "cadastro. Nada foi gravado.")
        if e not in out:
            out.append(e)
    if len(out) > LISTA_MAX:
        raise Recusada(f"A lista passa de {LISTA_MAX} destinatários: nada foi gravado.")
    return out


def montar_linha(*, tipo: str, ligado: bool, modo: str, destinatarios: list[str], substitui: bool, quem_hmac: str,
                 motivo: str, chave_base: str, alterado_em: str) -> dict:
    """A linha pronta, cifrada e assinada (sem conferir o pedido: quem chama é o `publicar`, e o teste)."""
    lista = normalizar_lista(destinatarios)
    ln = {"tipo": tipo, "ligado": "sim" if ligado else "não", "modo": modo,
          "destinatarios": cifrar_lista(lista, tipo, chave_base),
          "substitui_padrao": ("sim" if substitui else "não") if lista else "não",
          "alterado_por": quem_hmac or "", "alterado_em": alterado_em, "motivo": motivo}
    ln["assinatura"] = assinatura(ln, chave_base)
    return ln


def publicar(cfg, *, tipo: str, ligado: bool, modo: str, destinatarios, substitui: bool, motivo, quem_hmac: str,
             nomes=(), conhecidos=(), confirmou_critico: bool = False, criticos=(), alvo: Alvo | None = None) -> dict:
    """Acrescenta UMA linha (a mudança) e grava o livro. {"linha", "regra", "mudou"}; `Recusada` quando não vale.
    Nada se grava sem a NEXUS_PESSOA_HMAC (o App descartaria a linha), sem ler o livro antes, nem igual à que vale."""
    chave = _base(cfg.get("NEXUS_PESSOA_HMAC"))
    if not chave:
        raise Recusada("Este Nexus não tem a NEXUS_PESSOA_HMAC: a regra iria sem assinatura e o App a descartaria. Nada "
                       "foi gravado.")
    alvo = alvo or alvo_do_tipo(tipo)
    if tipo not in alvo.tipos():
        raise Recusada(f"Tipo de e-mail que {alvo.quem} não conhece: nada foi gravado.")
    modo = str(modo or "").strip().lower()
    if modo not in MODOS:
        raise Recusada("Modo que o App não conhece: nada foi gravado.")
    lista = conferir_destinatarios(destinatarios, conhecidos)
    if ligado and modo == "teste" and not lista:
        # no App, o teste sem lista funciona como normal: o e-mail sairia para todos achando que é teste
        raise Recusada("O modo teste precisa da lista de quem recebe o teste: sem ela o App manda para todos, como no "
                       "normal. Nada foi gravado.")
    m = conferir_motivo(motivo, nomes)
    with _TRAVA:
        est = ler(cfg, forcar=True, alvo=alvo)
        if est["erro"]:
            raise Recusada(f"Não consegui ler o livro do controle agora ({est['erro']}): nada foi gravado, para não "
                           "apagar o que já está lá.")
        linhas = list(est["linhas"])
        atual = vigentes(linhas, chave, alvo).get(tipo)
        if not ligado and tipo in criticos and not confirmou_critico and (atual is None or atual["ligado"]):
            raise Recusada("Desligar este e-mail pede a confirmação: marque que quem recebe deixa de saber.")
        nova = {"ligado": bool(ligado), "modo": modo, "destinatarios": lista,
                "substitui": bool(substitui) if lista else False}
        # a mesma lista em outra ordem é a mesma regra (o App manda para todos de uma vez)
        if atual and all((set(atual[k]) == set(v)) if k == "destinatarios" else atual[k] == v for k, v in nova.items()):
            return {"linha": None, "regra": atual, "mudou": False}
        em = agora_iso()
        ultimo = max((_txt(x.get("alterado_em")) for x in linhas), default="")
        if em <= ultimo:
            # duas mudanças no mesmo segundo (ou o relógio desta máquina atrás de outra): a nova tem de vencer também
            # pela hora, não só pela ordem no livro
            em = _um_segundo_depois(ultimo if re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", ultimo) else em)
        ln = montar_linha(tipo=tipo, ligado=ligado, modo=modo, destinatarios=lista, substitui=nova["substitui"],
                          quem_hmac=quem_hmac, motivo=m, chave_base=chave, alterado_em=em)
        _gravar_cru(cfg, linhas + [ln], alvo)
        limpar()
        ok, porque, aberta = conferir(ln, chave, alvo)
        if not ok or aberta != lista:          # a ida e a volta, na própria máquina: nunca deveria acontecer
            raise Recusada(f"A linha gravada não confere ({porque or 'a lista mudou'}): avise o responsável do Nexus.")
        return {"linha": ln, "regra": regra_da_linha(ln, lista), "mudou": True}


def _um_segundo_depois(iso: str) -> str:
    from datetime import timedelta
    d = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) + timedelta(seconds=1)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")
