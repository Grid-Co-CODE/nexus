"""catalogos_leitor.py: as pessoas do catálogo lidas pelo PRÓPRIO servidor, pelo REST da empresa (31/10/2026, etapa 4 do canto
central; tarefa 4.1).

O par do `catalogos.py` como o `ativos_leitor` é do `ativos_central`: lá mora o catálogo (guardar e entregar); aqui, o laço que
o renova pela credencial da empresa, a única parte que importa o `nexus`. O REST `personnel` do cadastro
(`nexus/cadastro/fracttal_pessoal.py`), às 05h, 11h, 17h e 23h de Brasília no minuto `minutos_ocupados.CATALOGOS_PESSOAS`, 1
pedido por segundo, contado como `fundo:nexus-catalogos:pessoas`. Só troca as pessoas se o REST trouxer os campos que as telas
usam (`CAMPOS_REST`) e bater com o RPC (`_confere`); senão nada muda, e o estado diz por quê.

Só o `servir.py` liga (`ligar`); o `app.py` (o PC) e os testes seguem sem ele. Sem a credencial REST ele não liga, o estado diz
por quê, e as pessoas seguem pelo RPC, com a sessão de quem usa.
"""
from __future__ import annotations

import contextlib
import logging
import threading

import catalogos
from nexus.casca import minutos_ocupados as _MO

log = logging.getLogger("oscreator.catalogos")

CHAVE = "oscreator_catalogos"
CAMPOS_MIN_PCT = 99.0           # do pessoal do REST, as linhas que trazem cada campo que as telas usam
PARIDADE_MIN_PCT = 95.0         # da lista de responsáveis, o que o REST e o RPC têm em comum (nos dois sentidos)
ENCOLHE_MAX_PCT = 10            # o REST com menos pessoas que isto do catálogo de agora não troca (página perdida)
# o laço das pessoas pelo REST (só o servidor): as horas de Brasília e o minuto da lista única de minutos ocupados do Nexus
HORAS = (5, 11, 17, 23)
MINUTO = _MO.CATALOGOS_PESSOAS
_H = 3600
_BRT_S = -3 * _H

_MOTIVO_DESLIGADO = "não ligado (só o servir.py liga o laço das pessoas pelo REST)"
_ESTADO: dict = {"ligado": False, "motivo": _MOTIVO_DESLIGADO, "credencial": None, "ultima": None}
_APP: dict = {"app": None}


def reiniciar() -> None:
    """Desligado (o `catalogos.reiniciar` chama: os testes)."""
    _ESTADO.update(ligado=False, motivo=_MOTIVO_DESLIGADO, credencial=None, ultima=None)
    _APP["app"] = None


# ── a conferência ──────────────────────────────────────────────────────────────────────────────────────────────────────
# Os campos que as telas usam do pessoal, e os nomes com que o REST pode trazê-los. O cadastro (`fracttal_pessoal.da_api`)
# conhece do REST `personnel` o id, o código, o nome, o e-mail, o acesso e a conta ativa; o `active` (o pessoal ATIVO, a lista
# das telas) e o `id_account` (quem criou a OS: "criadas por mim" e o "Criado por") nunca foram vistos lá. A sondagem não pôde
# ser feita antes de construir (este computador não lê o Fracttal com a credencial da empresa): é esta conferência, a cada
# leitura, que a faz. Faltou um, a leitura não troca nada, e o estado diz qual.
CAMPOS_REST = (("id_personnel", ("id_personnel",)), ("code", ("code",)), ("nome", ("full_name", "name")),
               ("active", ("active",)), ("id_account", ("id_account",)), ("email", ("email", "account_email")))


class _Recusa(RuntimeError):
    """A leitura REST que veio, mas não serve (sem os campos, sem bater com o RPC, encolhida): nada muda."""


def campos_que_faltam(linhas: list) -> list:
    """Os campos de `CAMPOS_REST` que vêm em menos de `CAMPOS_MIN_PCT` das linhas (a chave, mesmo com o valor vazio)."""
    if not linhas:
        return [n for n, _c in CAMPOS_REST]
    faltam = []
    for nome, chaves in CAMPOS_REST:
        tem = sum(1 for p in linhas if any(k in p for k in chaves))
        if tem * 100 < len(linhas) * CAMPOS_MIN_PCT:
            faltam.append(nome)
    return faltam


def de_rest(p: dict) -> dict:
    """Uma pessoa do REST no formato do `api.ler_pessoal` (o do RPC chama o id de `id`; o REST, de `id_personnel`)."""
    nome = str(p.get("full_name") or p.get("name") or "").strip()
    return {"id_personnel": p.get("id_personnel"), "code": p.get("code"), "name": nome, "active": p.get("active"),
            "id_account": p.get("id_account"), "email": str(p.get("account_email") or p.get("email") or "").strip().lower()}


def _ids_responsaveis(linhas) -> set:
    return {p.get("id_personnel") for p in linhas if p.get("name") and p.get("active") is not False}


def _confere(novas: list) -> str:
    """O motivo de a leitura REST não servir, ou "". Encolheu demais contra o catálogo de agora (página perdida); ou é a 1ª
    contra um catálogo do RPC e não bate com ele: a lista de responsáveis (o mesmo campo com outro sentido mudaria quem as
    telas mostram), e, das pessoas em comum, a conta e o e-mail (o mesmo id com outra conta muda o dono do "criadas por mim";
    com outro e-mail, quem a pessoa logada é; revisão da 4.1). A 1ª leitura REST que já valeu precisa desse catálogo para
    conferir (a 1ª noite dos ativos, REST x RPC): sem ele (a máquina nova, sem cópia), espera a 1ª tela que o lê pela sessão
    de alguém."""
    atual, fonte = catalogos.pessoas_guardadas()
    if not atual:
        if not catalogos.rest_bom_em():
            return "ainda não há o catálogo do RPC para conferir a 1ª leitura REST (a 1ª tela o lê pela sessão de quem usa)"
        return ""
    if len(novas) * 100 < len(atual) * (100 - ENCOLHE_MAX_PCT):
        return "o REST trouxe %d pessoas e o catálogo tem %d (encolheu mais que %d%%)" % (len(novas), len(atual),
                                                                                           ENCOLHE_MAX_PCT)
    if fonte != "rpc":
        return ""
    r, n = _ids_responsaveis(atual), _ids_responsaveis(novas)
    comum = len(r & n)
    if not (r and n and comum * 100 >= len(r) * PARIDADE_MIN_PCT and comum * 100 >= len(n) * PARIDADE_MIN_PCT):
        return ("o pessoal ativo do REST (%d) não bate com o do RPC (%d): %d em comum, abaixo de %d%% nos dois sentidos" % (
            len(n), len(r), comum, PARIDADE_MIN_PCT))
    antes = {p.get("id_personnel"): p for p in atual if p.get("id_personnel") is not None}
    depois = {p.get("id_personnel"): p for p in novas if p.get("id_personnel") is not None}
    ids = antes.keys() & depois.keys()
    for campo, rotulo in (("id_account", "a conta (id_account)"), ("email_h", "o e-mail")):
        iguais = sum(1 for i in ids if antes[i].get(campo) == depois[i].get(campo))
        if iguais * 100 < len(ids) * PARIDADE_MIN_PCT:
            return "%s do REST não bate com o do RPC: %d de %d pessoas em comum iguais, abaixo de %d%%" % (
                rotulo, iguais, len(ids), PARIDADE_MIN_PCT)
    return ""


# ── a leitura ──────────────────────────────────────────────────────────────────────────────────────────────────────────
@contextlib.contextmanager
def _origem(assunto: str):
    """O laço conta no contador do Fracttal com o nome dele (`fundo:nexus-catalogos:<assunto>`)."""
    try:
        from nexus.casca import fracttal_conta
    except Exception:                                               # noqa: BLE001 — sem o contador, a leitura segue
        yield
        return
    with fracttal_conta.origem("fundo:nexus-catalogos:" + assunto):
        yield


def ler_pessoas_rest(ler=None) -> dict:
    """As pessoas pelo REST `personnel` do cadastro (`fracttal_pessoal.ler_paginas`, o cliente e o ritmo do
    `nexus/campo/fracttal.py`), pela credencial da empresa, 1 pedido por segundo, contadas como `fundo:nexus-catalogos:pessoas`.
    Troca o catálogo só se a leitura trouxe os campos que as telas usam (`CAMPOS_REST`) e passou na conferência (`_confere`);
    senão nada muda, o motivo vai ao estado, e as pessoas seguem pelo RPC quando vencerem. Devolve o relatório."""
    rel = {"inicio": catalogos.relogio(), "fim": None, "pedidos": 0, "linhas": 0, "resultado": "", "erro": ""}
    conta = [0]
    if ler is None:
        from nexus.campo import fracttal
        ler = fracttal.ler

    def contando(path):
        if conta[0]:
            catalogos.dormir(catalogos.PAUSA_S)
        conta[0] += 1
        return ler(path)
    ger = catalogos.geracao()
    try:
        with _origem("pessoas"):
            from nexus.cadastro import fracttal_pessoal
            brutas = [p for p in fracttal_pessoal.ler_paginas(contando) if isinstance(p, dict)]
        rel["linhas"] = len(brutas)
        faltam = campos_que_faltam(brutas)
        if faltam:
            raise _Recusa("o REST do pessoal não trouxe %s (as telas usam): as pessoas seguem pelo RPC" % ", ".join(faltam))
        valor = catalogos.preparar_pessoas([de_rest(p) for p in brutas])
        motivo = _confere(valor)
        if motivo:
            raise _Recusa(motivo + ": fica o catálogo do RPC")
        if not catalogos.instalar("pessoas", valor, "rest", ger):
            raise _Recusa("o processo reiniciou no meio da leitura")
        catalogos.anotar_leitura_rest(True)
        rel["resultado"] = "%d pessoas pelo REST" % len(valor)
    except _Recusa as e:
        rel["erro"] = rel["resultado"] = str(e)
        catalogos.anotar_leitura_rest(False, str(e))
        log.warning("catálogos: as pessoas pelo REST: %s", e)
    except Exception as e:                                          # noqa: BLE001 — Fracttal fora, credencial, cota: fica o de antes
        rel["erro"] = catalogos.motivo_do_erro(e)
        rel["resultado"] = "nada mudou: " + rel["erro"]
        catalogos.anotar_leitura_rest(False, rel["erro"])
        log.warning("catálogos: as pessoas pelo REST falharam (%s)", rel["erro"])
    finally:
        rel.update(pedidos=conta[0], fim=catalogos.relogio())
        _ESTADO["ultima"] = rel
    return rel


# ── o laço (só o servidor) ─────────────────────────────────────────────────────────────────────────────────────────────
def proximo_passo(agora: float) -> float:
    """Os segundos até a próxima leitura das pessoas pelo REST: às `HORAS` de Brasília, no minuto da lista única de minutos
    ocupados (`minutos_ocupados.CATALOGOS_PESSOAS`). Estando no instante de uma, a próxima é a seguinte."""
    local = agora + _BRT_S
    dia0 = (local // 86400) * 86400
    cands = [dia0 + d * 86400 + h * _H + MINUTO * 60 for d in (0, 1) for h in HORAS]
    return min(t for t in cands if t > local) - local


def _laco() -> None:
    while True:
        catalogos.dormir(proximo_passo(catalogos.relogio()))
        app = _APP["app"]
        try:
            with app.app_context():
                rel = ler_pessoas_rest()
            log.info("catálogos: as pessoas pelo REST: %s (%d pedidos)", rel["resultado"], rel["pedidos"])
        except Exception:                                           # noqa: BLE001 — o laço nunca derruba o Nexus
            log.exception("catálogos: o laço das pessoas quebrou")


def estado() -> dict:
    """O laço, para o `catalogos.estado()` (que junta a última leitura boa e a última falha, as do disco): se está ligado e
    por quê não, onde está a credencial, a próxima leitura e o relatório da última."""
    agora = catalogos.relogio()
    ult = _ESTADO.get("ultima")
    return {"ligado": bool(_ESTADO["ligado"]), "motivo": _ESTADO["motivo"], "credencial": _ESTADO["credencial"],
            "proxima": agora + proximo_passo(agora) if _ESTADO["ligado"] else None,
            "ultima": dict(ult) if isinstance(ult, dict) else None}


def ligar(app) -> None:
    """Liga o laço das pessoas pelo REST neste app (SÓ o `servir.py`, o servidor): diz aos catálogos onde mora a cópia em disco
    (`ponte.ligar_catalogos`, o mesmo que a criação do clone faz) e abre o laço (fora dos testes). Sem a credencial REST do
    Fracttal, não liga: o estado diz por quê, e as pessoas seguem pelo RPC, com a sessão de quem usa. Ligar de novo no mesmo app
    não faz nada."""
    if CHAVE in app.extensions:
        return
    app.extensions[CHAVE] = _ESTADO
    try:
        from nexus.torres.oscreator import ponte
        ponte.ligar_catalogos(app)
    except Exception:                                               # noqa: BLE001 — sem a pasta, os catálogos vivem na memória
        log.exception("catálogos: não liguei a pasta de dados")
    from nexus.pcm.geracao import credencial
    cred = credencial(app.config)
    if not cred.ok:
        _ESTADO.update(ligado=False, motivo="sem a credencial REST do Fracttal (FRACTTAL_CLIENT_ID e FRACTTAL_CLIENT_SECRET): "
                                            "as pessoas seguem pelo RPC, com a sessão de quem usa")
        catalogos.ligar_leitor(ligado=False, estado=estado)
        log.warning("catálogos: %s", _ESTADO["motivo"])
        return
    _APP["app"] = app
    _ESTADO.update(ligado=True, motivo="", credencial=cred.onde)
    catalogos.ligar_leitor(ligado=True, estado=estado)
    if not app.config.get("TESTING"):
        threading.Thread(target=_laco, name="nexus-catalogos", daemon=True).start()
