"""Os textos reservados (19/11/2026): o que não pode morar num repositório público mora cifrado no banco do Nexus.

Levi, 19/11/2026, depois da varredura do histórico: "Tirar os dados do repositório e levar para o banco do Nexus"; e o
critério, no mesmo dia: "Eu não aceito só censurar e aí quem tiver no Nexus vê as coisas incompletas, não. Tem que estar no
banco do Nexus e aí quem tiver um acesso do Nexus vai ter a informação completa". O repositório é público; valor de
contrato, citação de cliente e de fornecedor e o e-mail de um fabricante não ficam em arquivo versionado. Mas a tela de quem
está logado mostra tudo, como antes.

Como funciona. O arquivo versionado guarda uma FICHA no lugar do texto (no clone do Radar da Zeladoria, `Zlfornecedor01`,
`ZLVALOR03`; no OS Creator, a chave é o nome do fabricante). O texto mora no livro `nexus_textos_reservados ·
dim_texto_reservado` (no catálogo antes da 1ª gravação, regra 10), 1 linha por ficha de uma área: em claro só a área, a
ficha e a data; o texto, cifrado com o Cofre (`NEXUS_CHAVE_CADASTRO`) e preso à área e à ficha (copiado para outra linha,
não abre). A API do banco tem leitura aberta (regra 8): quem lê o livro por fora vê `cf1:...`. A rota que exige login lê,
decifra e devolve o texto no lugar da ficha (`restaurar`): a página servida é a de antes, caractere por caractere.

Quem grava é a ferramenta `ferramentas/textos_reservados.py`, à mão, com a lista de termos FORA do repositório. O livro só
cresce: ficha publicada não sai (o arquivo de uma versão antiga do Nexus ainda precisa dela).

Este módulo é puro até o `ler`, o único que precisa do Nexus rodando.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone

from . import livros

LIVRO, NOME_LIVRO, ABA = ("nexus_textos_reservados", "Nexus · textos reservados (fora do repositório público)",
                          "dim_texto_reservado")
CAB = ("texto_id", "area", "chave", "texto_cifrado", "atualizado_em")
# cada área é de quem lê: o clone do Radar da Zeladoria e o canal de abertura dos fabricantes do OS Creator
AREAS = ("zeladoria_radar", "oscreator_canal")
TTL_S = 300
TTL_ERRO_S = 60
# a ficha vale dentro de um nome do JS, de uma regex, de um texto de tela e de um comentário: só letras e dois algarismos.
# As palavras são fixas porque "Zl + letras + algarismos" solto também aparece por acaso no base64 de uma fonte embutida
# (medido no clone do Radar em 19/11/2026)
_PALAVRAS = ("cliente", "fornecedor", "valor", "trecho", "texto")
FICHA = re.compile("(?:" + "|".join(f"Zl{p}|zl{p}|ZL{p.upper()}" for p in _PALAVRAS) + r")\d{2}")
_BRT = timezone(timedelta(hours=-3))


class Recusada(ValueError):
    """Nada foi gravado nem trocado: o texto diz por quê (e nunca traz o texto reservado)."""


def _txt(v) -> str:
    return "" if v is None else str(v)


def _ctx(area: str, chave: str) -> str:
    return f"banco/textos_reservados/{area}/{chave}"


# ── o livro ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def abrir(linhas, cofre, area: str) -> dict:
    """{ficha: texto} de uma área, do que o banco devolveu. A linha que não abre (mexida, de outra chave, copiada de
    outra ficha) é pulada: uma linha estragada não tira as outras da tela."""
    out = {}
    for l in linhas or []:
        chave = _txt(l.get("chave"))
        if _txt(l.get("area")) != area or not chave:
            continue
        try:
            out[chave] = cofre.decifrar(l.get("texto_cifrado"), _ctx(area, chave))
        except Exception:        # noqa: BLE001 — CifraErro ou valor torto: a linha fica de fora
            continue
    return out


def publicar(area: str, textos: dict, *, base: str, sessao, token: str, cofre) -> dict:
    """Põe os textos de uma área no livro (o livro inteiro de novo, como os outros do Nexus) e LÊ DE VOLTA: cada texto
    publicado tem de abrir igual. Só acrescenta ou troca a ficha que mudou; a ficha que não veio e a outra área ficam
    como estavam, com a mesma cifra. Devolve {"antes", "depois", "novos", "mudados", "iguais"}."""
    if area not in AREAS:
        raise Recusada(f"área desconhecida: {area!r} (as áreas são {', '.join(AREAS)})")
    if not isinstance(textos, dict) or not textos:
        raise Recusada("nenhum texto para publicar")
    for chave, texto in textos.items():
        if not isinstance(chave, str) or not chave.strip() or chave != chave.strip():
            raise Recusada("há uma ficha vazia ou com espaço sobrando")
        if not isinstance(texto, str) or not texto:
            raise Recusada(f"a ficha {chave} veio sem texto")
    atuais = livros.ler_conferido(base, sessao, LIVRO, (ABA,))[ABA]
    linhas = [{c: l.get(c) for c in CAB} for l in atuais]
    por_id = {_txt(l["texto_id"]): l for l in linhas}
    ja = abrir(linhas, cofre, area)
    agora = datetime.now(_BRT).replace(microsecond=0).isoformat()
    novos, mudados, iguais = [], [], []
    for chave in sorted(textos):
        texto, tid = textos[chave], f"{area}/{chave}"
        if ja.get(chave) == texto:
            iguais.append(chave)
            continue
        nova = {"texto_id": tid, "area": area, "chave": chave, "texto_cifrado": cofre.cifrar(texto, _ctx(area, chave)),
                "atualizado_em": agora}
        if tid in por_id:
            por_id[tid].update(nova)
            mudados.append(chave)
        else:
            linhas.append(nova)
            por_id[tid] = nova
            novos.append(chave)
    if novos or mudados:
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in linhas])},
                        base=base, token=token, sessao=sessao)
        lido = abrir(livros.ler(base, sessao, LIVRO, ABA), cofre, area)
        faltam = sorted(c for c, t in textos.items() if lido.get(c) != t)
        if faltam:
            raise livros.GravacaoErro(f"{LIVRO}: a leitura de volta não devolveu igual {len(faltam)} ficha(s): "
                                      + ", ".join(faltam[:8]))
    return {"antes": len(atuais), "depois": len(linhas), "novos": novos, "mudados": mudados, "iguais": iguais}


# ── a ficha no arquivo ───────────────────────────────────────────────────────────────────────────────────────────────
def fichas_em(texto: str) -> list:
    """As fichas que o texto traz, sem repetir, em ordem."""
    return sorted(set(FICHA.findall(texto or "")))


def restaurar(texto: str, fichas: dict) -> str:
    """O texto com cada ficha trocada pelo texto dela. A mais longa primeiro (uma ficha nunca é o começo de outra,
    mas a ordem não pode depender disso)."""
    for ficha in sorted(fichas or {}, key=len, reverse=True):
        texto = texto.replace(ficha, fichas[ficha])
    return texto


def reservar(texto: str, termos: list) -> tuple:
    """(o texto com as fichas, {ficha: texto reservado}). `termos`, em ordem (o trecho comprido antes da palavra que
    ele contém): {"ficha", "texto", "vezes" (opcional: quantas vezes tem de aparecer), "onde" (opcional: só dentro
    destes contextos, para o texto curto que também aparece onde não é o dado)}.

    Para, sem devolver nada, quando um termo não casa como dito, e confere no fim que `restaurar` devolve o original
    idêntico. O motivo diz a ficha e o número do termo, nunca o texto reservado."""
    original, fichas = texto, {}
    ja = set(fichas_em(texto))
    for n, t in enumerate(termos or [], 1):
        ficha, alvo = _txt(t.get("ficha")), t.get("texto")
        if not FICHA.fullmatch(ficha):
            raise Recusada(f"termo {n}: ficha fora do formato (Zl, zl ou ZL + {', '.join(_PALAVRAS)} + dois algarismos)")
        if ficha in fichas:
            raise Recusada(f"termo {n}: ficha repetida ({ficha})")
        if ficha in ja or ficha in original:
            raise Recusada(f"termo {n}: o arquivo já traz a ficha {ficha}")
        if not isinstance(alvo, str) or not alvo:
            raise Recusada(f"termo {n} ({ficha}): sem o texto")
        onde = t.get("onde")
        if onde:
            for ctx in onde:
                if alvo not in ctx or ctx not in texto:
                    raise Recusada(f"termo {n} ({ficha}): o contexto dito não está no arquivo ou não traz o texto")
                texto = texto.replace(ctx, ctx.replace(alvo, ficha))
        else:
            vezes = texto.count(alvo)
            if not vezes:
                raise Recusada(f"termo {n} ({ficha}): o texto não aparece no arquivo")
            if t.get("vezes") is not None and vezes != int(t["vezes"]):
                raise Recusada(f"termo {n} ({ficha}): aparece {vezes} vezes, e não as {t['vezes']} vezes ditas")
            texto = texto.replace(alvo, ficha)
        fichas[ficha] = alvo
    if restaurar(texto, fichas) != original:
        raise Recusada("a volta não devolve o arquivo idêntico (um termo pegou um pedaço de outro): nada foi trocado")
    return texto, fichas


# ── a leitura dentro do Nexus ────────────────────────────────────────────────────────────────────────────────────────
def ler(area: str, forcar: bool = False) -> dict:
    """{"textos": {ficha: texto}, "erro", "ja_leu", "lido_em"} da área, com cópia de 5 minutos por app. A leitura que
    falha (banco fora, sem a chave do cadastro) devolve a última boa com o erro, e tenta de novo em 1 minuto; sem
    nenhuma leitura boa, `textos` vem vazio: quem chama mostra a ficha e avisa, nunca inventa o texto."""
    from flask import current_app

    from . import conexao
    guarda = current_app.extensions.setdefault("nexus_textos_reservados", {})
    g, agora = guarda.get(area), time.time()
    if g and not forcar and agora < g["vale_ate"]:
        return g
    try:
        chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
        if not chave:
            raise Recusada("este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): o texto reservado não abre")
        from ..cadastro.cifra import Cofre
        base, sessao = conexao.banco()
        novo = {"textos": abrir(livros.ler(base, sessao, LIVRO, ABA), Cofre(chave), area), "erro": "", "ja_leu": True,
                "lido_em": agora, "vale_ate": agora + TTL_S}
    except Exception as ex:      # noqa: BLE001 — banco fora, chave ausente ou torta: fica a última boa, com o motivo
        novo = {"textos": dict((g or {}).get("textos") or {}), "erro": f"{type(ex).__name__}: {str(ex)[:160]}",
                "ja_leu": bool((g or {}).get("ja_leu")), "lido_em": agora, "vale_ate": agora + TTL_ERRO_S}
    guarda[area] = novo
    return novo
