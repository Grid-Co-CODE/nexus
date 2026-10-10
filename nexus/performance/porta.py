"""A porta única com a plataforma de Performance (09/10/2026): o mapa das telas e o passe. Regra sem Flask.

Levi, 09/10/2026: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo, precisamos
trazer o tempo real de performance painel para o Nexus". Desenho aprovado: "uma porta, dois motores"
(`docs/superpowers/specs/2026-10-09-performance-no-nexus-design.md`). O Nexus é a porta (menu, login, endereço); a
plataforma continua o motor e desenha as próprias telas dentro de uma moldura (iframe) do Nexus.

Duas partes, as mesmas do `plataforma/porta_nexus.py` do PerformancePainel (que é a cópia; o dono do mapa é este):

1. O MAPA das telas (spec 5.6). Fonte única: dá o destino que o passe pode pedir (nada de redirecionamento aberto), o
   `?p=` que o Nexus aceita (favorito, F5) e o item do menu que acende quando a moldura avisa onde está. O teste
   `tests/test_porta_mapa.py` confere este mapa contra o texto canônico da plataforma (e, com `PLATAFORMA_REPO`, contra
   o próprio arquivo dela).
2. O PASSE (spec 5.2): `base64url(json) + "." + base64url(HMAC-SHA256(json))` com a chave `NEXUS_SSO_CHAVE`. O JSON:
       {"v": 1, "email": "...", "nome": "...", "admin": false, "destino": "/tempo-real",
        "vence": <epoch em segundos, 60 s à frente>, "numero": "<aleatório, 16 a 128 de [A-Za-z0-9_-]>"}
   Vai por POST no campo `passe` de `/painel/nexus/entrar`, NUNCA na URL: leva o e-mail e não pode ficar em log de
   proxy nem no histórico do navegador. Muda a cada abertura (número novo) e vale 60 s; a plataforma guarda os números
   usados e recusa o repetido.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from collections import namedtuple
from urllib.parse import unquote, urlsplit

# ── 1. O mapa das telas ──────────────────────────────────────────────────────────────────────────────────────────────
# torre e tela = o id no Nexus (`/t/<torre>/<tela>`); caminho = a entrada da tela na plataforma (padrão com `<x>` quando
# a tela pede um parâmetro: o Diagnóstico abre pela usina escolhida no seletor); tambem = outros caminhos que são a MESMA
# tela (o Nexus acende o item por eles); so_admin = só administrador do Nexus abre. `<x>` é um segmento; `<path:x>`, o
# resto do caminho. Mudou aqui, muda na plataforma (`porta_nexus.MAPA`) e no texto do teste: os dois lados comparam.
TelaDaPlataforma = namedtuple("TelaDaPlataforma", "torre tela nome caminho tambem so_admin")

MAPA = (
    # O Tempo real é a Entrada nível 2 da plataforma (cards por fonte); o nível 3 é /tempo-real/<fonte>, que embute
    # /monitor?fonte=…&embed=1. O /monitor sem moldura (os atalhos do Painel NOC) é a mesma tela.
    TelaDaPlataforma("performance", "tempo-real", "Tempo real", "/tempo-real", ("/tempo-real/<fonte>", "/monitor"),
                     False),
    TelaDaPlataforma("performance", "noc", "Painel NOC", "/painel", (), False),
    # Diagnóstico = o diagnóstico da usina, aberto pelo seletor de usina do Nexus (Levi, 09/10/2026: "OK, cuida!")
    TelaDaPlataforma("performance", "diagnostico", "Diagnóstico", "/painel/usina/<id>", (), False),
    TelaDaPlataforma("performance", "strings-trackers", "Strings e trackers", "/painel/falhas", (), False),
    TelaDaPlataforma("performance", "gerencial", "Visão gerencial", "/gerencial", (), False),
    TelaDaPlataforma("performance", "disponibilidade", "Disponibilidade", "/gerencial/disponibilidade", (), False),
    TelaDaPlataforma("performance", "relatorio", "Criador de relatório", "/relatorio", (), False),
    TelaDaPlataforma("performance", "relatorio-semanal", "Relatório semanal", "/relatorio/semanal", (), False),
    # O gêmeo é outro processo, servido pelo proxy /gemeo/* da plataforma: tudo debaixo dele é a mesma tela (o Painel
    # NOC abre /gemeo/usina/<id>).
    TelaDaPlataforma("performance", "gemeo", "Gêmeo digital", "/gemeo/", ("/gemeo/<path:resto>",), False),
    TelaDaPlataforma("performance", "historico-plataforma", "Histórico da plataforma", "/historico-plataforma", (),
                     False),
    TelaDaPlataforma("performance", "monitor-ronda", "Monitor da ronda", "/ronda/monitor", (), False),
    TelaDaPlataforma("cos", "acompanhamento", "Acompanhamento COS", "/cos", (), False),
    # /tokens grava as chaves das fontes (SunOp, Axis, Plataforma): administração, só admin do Nexus (spec 5.3)
    TelaDaPlataforma("base", "chaves-fontes", "Chaves das fontes", "/tokens", (), True),
)

# As duas rotas da porta na plataforma: não são telas, mas o Nexus as escreve (o formulário do passe e o Sair).
ENTRAR = "/painel/nexus/entrar"
SAIR = "/painel/nexus/sair"


def _fonte_do_padrao(padrao: str) -> str:
    """O padrão como expressão regular que vale igual no Python e no JavaScript do navegador (sem o `\\-` do
    `re.escape`, que o JavaScript com a bandeira `u` recusa)."""
    rx = ""
    for parte in re.split(r"(<[^>]+>)", padrao):
        if parte.startswith("<path:"):
            rx += r"[^?#]+"
        elif parte.startswith("<"):
            rx += r"[^/?#]+"
        else:
            rx += re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", parte)
    return "^" + rx + "$"


_PADROES = tuple((t, re.compile(_fonte_do_padrao(p))) for t in MAPA for p in (t.caminho,) + tuple(t.tambem))


def tela_do_caminho(caminho):
    """A tela do mapa a que o caminho (a query não conta) pertence, ou None."""
    c = str(caminho or "").split("?", 1)[0]
    for t, rx in _PADROES:
        if rx.match(c):
            return t
    return None


def da_torre(torre_id: str) -> list:
    return [t for t in MAPA if t.torre == torre_id]


def concreto(t: TelaDaPlataforma) -> bool:
    """A entrada da tela é um caminho que abre sozinho (o Diagnóstico precisa da usina: `/painel/usina/<id>`)."""
    return "<" not in t.caminho


_RX_PROIBIDO = re.compile(r"[\x00-\x20\x7f\\#<>\"'`]")


def destino_permitido(destino) -> str | None:
    """O destino, se for uma tela do mapa; None senão. A MESMA regra do `porta_nexus.destino_permitido` da plataforma
    (o teste compara as duas): só caminho local (uma barra, sem esquema nem host), sem espaço, controle, aspas, barra
    invertida nem fragmento; a query passa (o favorito `?p=/monitor?fonte=pv&embed=1`). `//outro.site` e `/\\outro`
    caem aqui: nada de redirecionamento aberto."""
    if not isinstance(destino, str) or not destino or len(destino) > 2048:
        return None
    if not destino.startswith("/") or destino.startswith("//") or _RX_PROIBIDO.search(destino):
        return None
    caminho = destino.split("?", 1)[0]
    # Segmento de ponto, escrito ou CODIFICADO (revisão de 10/10/2026): '/gemeo/%2e%2e/tokens' casava com
    # /gemeo/<path:resto>, e o navegador resolve o %2e%2e como '..' (vai a /tokens); pelo `?p=/gemeo/%252e%252e/...` a
    # moldura ia a qualquer caminho da mesma origem, fora do mapa. Barra e barra invertida codificadas também não: viram
    # outro segmento numa camada que decodifica. O '%' de um nome de usina (o seletor do Diagnóstico) segue valendo.
    for segmento in caminho.split("/"):
        claro = unquote(segmento)
        if claro in (".", "..") or "/" in claro or "\\" in claro:
            return None
    return destino if tela_do_caminho(caminho) else None


def texto_canonico_do_mapa() -> str:
    """Uma linha por tela, na ordem do mapa: `torre|tela|caminho|tambem separados por espaço|admin ou vazio`. É o
    mesmo texto da plataforma (`porta_nexus.texto_canonico_do_mapa`); o nome de exibição fica de fora de propósito,
    para cada lado acertar a grafia sem quebrar o outro."""
    return "\n".join(f"{t.torre}|{t.tela}|{t.caminho}|{' '.join(t.tambem)}|{'admin' if t.so_admin else ''}"
                     for t in MAPA)


def assinatura_do_mapa() -> str:
    return hashlib.sha256(texto_canonico_do_mapa().encode("utf-8")).hexdigest()[:16]


def padroes_do_navegador(t: TelaDaPlataforma) -> list[str]:
    """As expressões da tela para o JavaScript da moldura (acender o item do menu pelo caminho que a moldura avisa)."""
    return [_fonte_do_padrao(p) for p in (t.caminho,) + tuple(t.tambem)]


# ── 2. O passe ───────────────────────────────────────────────────────────────────────────────────────────────────────
VALIDADE_S = 60                  # o passe vale 60 s (spec 5.2)
CHAVE_MINIMA = 32                # NEXUS_SSO_CHAVE: 32 caracteres ou mais, aleatória; a plataforma recusa a curta igual
# Quem entrou pela senha de administrador não é uma pessoa: o passe precisa de um e-mail (a plataforma guarda quem
# grava), e este é o da reserva, num domínio que não existe (`.invalid`, RFC 2606). Com PLATAFORMA_ANALISTAS=* ele é
# analista; numa lista fechada, precisa estar nela.
EMAIL_DA_SENHA_DE_ADMIN = "admin@nexus.invalid"
NOME_DA_SENHA_DE_ADMIN = "Administrador do Nexus (senha)"


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).decode("ascii").rstrip("=")


def motivo_da_chave(chave) -> str | None:
    """Por que a chave não serve (None = serve). Nunca diz o valor: a mensagem vai para a tela."""
    c = str(chave or "").strip()
    if not c:
        return "falta a NEXUS_SSO_CHAVE no .env do Nexus (a mesma chave vai na plataforma)"
    if len(c) < CHAVE_MINIMA:
        return f"a NEXUS_SSO_CHAVE tem menos de {CHAVE_MINIMA} caracteres (a plataforma também a recusa)"
    return None


def montar_passe(chave: str, email: str, nome: str, admin: bool, destino: str, agora: float | None = None,
                 numero: str | None = None) -> str:
    """O passe assinado. `destino` tem de passar no `destino_permitido` (a plataforma confere de novo). Cada chamada
    gera um número novo: duas aberturas nunca têm o mesmo passe."""
    if destino_permitido(destino) is None:
        raise ValueError("o destino não é uma tela do mapa")
    if motivo_da_chave(chave):
        raise ValueError("chave do passe inválida")
    dados = {"v": 1, "email": str(email or "").strip(), "nome": str(nome or "").strip()[:120],
             "admin": bool(admin), "destino": destino,
             "vence": int(time.time() if agora is None else agora) + VALIDADE_S,
             "numero": numero or secrets.token_urlsafe(24)}
    corpo = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assinatura = hmac.new(str(chave).strip().encode("utf-8"), corpo, hashlib.sha256).digest()
    return _b64(corpo) + "." + _b64(assinatura)


# ── 3. Onde está a plataforma, para o NAVEGADOR ──────────────────────────────────────────────────────────────────────
_LOCAL = ("localhost", "127.0.0.1", "::1", "[::1]")


def base_da_plataforma(valor) -> str:
    """A base dos endereços da plataforma que o navegador pede ('' = a própria origem do Nexus, o servidor e a porta
    local do PC). `NEXUS_PLATAFORMA_URL` com valor vira `https://servidor[:porta][/caminho]`, sem barra no fim.

    A moldura só abre na MESMA origem do Nexus: a plataforma manda `frame-ancestors 'self'` e o aviso de rota
    (`postMessage`) vai só para a origem dela. Uma URL de outra origem não quebra o Nexus, mas a moldura fica em branco
    (o JavaScript da tela avisa). ValueError com o motivo se a URL não serve."""
    texto = str(valor or "").strip()
    if not texto:
        return ""
    if re.search(r"[\x00-\x20\x7f\\]", texto):
        raise ValueError("NEXUS_PLATAFORMA_URL tem espaço, barra invertida ou caractere de controle")
    partes = urlsplit(texto)
    if partes.scheme not in ("http", "https") or not partes.hostname or partes.query or partes.fragment \
            or partes.username or partes.password:
        raise ValueError("NEXUS_PLATAFORMA_URL tem de ser https://servidor[:porta], sem usuário, consulta nem âncora")
    if partes.scheme == "http" and partes.hostname not in _LOCAL:
        raise ValueError("NEXUS_PLATAFORMA_URL tem de ser https fora da máquina local: o passe leva o e-mail")
    return texto.rstrip("/")


def _local(nome: str) -> bool:
    nome = (nome or "").lower()
    return nome in _LOCAL or nome.endswith(".localhost")


def motivo_da_origem(base: str, host_do_pedido: str) -> str | None:
    """Por que a base não serve a ESTE pedido (None = serve). Revisão de 10/10/2026: a base em loopback (a
    NEXUS_PLATAFORMA_URL interna do servidor, que a ponte de 04/10 pode usar) com o Nexus aberto por um endereço de fora
    faria o navegador de quem visita mandar o passe, com o e-mail dele, à porta local da PRÓPRIA máquina. No PC (o Nexus
    aberto em localhost, ou num nome .localhost da porta local) a mesma base é a da cópia local e segue valendo. O
    `porta.js` confere de novo a origem no navegador e não envia nada para outra."""
    if not base:
        return None
    alvo = urlsplit(base).hostname or ""
    quem = urlsplit("//" + str(host_do_pedido or "")).hostname or ""
    if _local(alvo) and quem and not _local(quem):
        return ("a NEXUS_PLATAFORMA_URL aponta para a própria máquina do servidor, e o Nexus foi aberto por outro "
                "endereço: o navegador mandaria o passe à máquina de quem visita. Ela tem de ser o mesmo endereço do "
                "Nexus (ou vazia)")
    return None
