"""O Tipo e as duas Classificações da peça que a curadoria cadastra (12/11/2026, item 3 da 2ª rodada do Almoxarifado).

O PCM (11/11/2026): "Tipo e classificação: Pelo claude eu não consigo fazer direto essa parte, somente na tela do fracttal,
mas se você conseguisse que eu colocasse pelo Nexus ou com base nos que já existem e são parecidos ele indicasse e colocasse
automaticamente como sugestão." Até ali a tela dizia que o grupo, a criticidade e a Curva ABC "não se gravam pela API"
(o teste do PCM de 09/10); a prova de 12/11/2026 no Fracttal de verdade mostrou que o `item_insert` grava os três (`id_group`,
`id_group_1`, `id_group_2`, `estoque.GRUPOS`) e o `items_list` os devolve iguais.

Aqui mora o que liga a sugestão (o texto do catálogo do App: a Família, a Criticidade, a letra da Curva ABC) às opções do
Fracttal (o id e a descrição de cada uma, das próprias peças, `estoque.classificacoes`): a `chave` de cada lado, a conferência
do id que a página mandou e a cópia de 1 h das opções. A sugestão em si é da curadoria (`curadoria.sugerir_classificacao`, com
as mesmas parecidas da sigla). Puro, menos a cópia.

- **A chave** (`chave`): o Tipo casa pelo texto sem acento e sem caixa ("Proteção Elétrica" = "protecao eletrica"); a
  Classificação 1 pelo número do nível ("1.Essencial" é o 1; o texto sem número, pelo texto); a Classificação 2 pela letra do
  Rank (`letra_do_rank`: "2. Rank A" é A, a Curva do livro do App já é a letra), e o "1.Avariado" não é curva (chave vazia:
  nunca é escolhido sozinho).
- **Duas opções com a mesma chave** no mesmo campo perdem a chave: a sugestão não escolhe sozinha entre duas.
- **O id que a página manda é conferido contra as opções** (`conferir`): o id chutado não vai ao Fracttal.
"""
from __future__ import annotations

import re
import threading
import time
from collections import Counter

from ...dados.dominios import norm
from . import estoque as E

CAMPOS = tuple(E.GRUPOS)
ROTULO = {"tipo": "Tipo", "classificacao_1": "Classificação 1 (criticidade)", "classificacao_2": "Classificação 2 (Rank)"}
CURTO = {"tipo": "Tipo", "classificacao_1": "Classificação 1", "classificacao_2": "Classificação 2"}
TTL_S = 3600                    # a cópia das opções: a lista de peças são algumas páginas da cota de 200/min da empresa

_RANK = re.compile(r"(?:\d+\s*[.)-]?\s*)?(?:rank|curva)?\s*([abc])")
_NIVEL = re.compile(r"(\d+)")


def letra_do_rank(texto) -> str:
    """A letra da Curva ABC numa descrição de Rank do Fracttal ("2. Rank A" é "A", "3.Rank B" é "B") ou no livro do App, que já
    traz a letra ("A", "Curva B"). O "1.Avariado" não é curva, nem o "Rank D": vazio."""
    m = _RANK.fullmatch(norm(texto))
    return m.group(1).upper() if m else ""


def chave(campo: str, texto) -> str:
    """O que casa o texto do catálogo do App com a descrição da opção do Fracttal, campo a campo (ver o cabeçalho)."""
    if campo == "classificacao_2":
        return letra_do_rank(texto)
    t = norm(texto)
    if campo == "classificacao_1":
        m = _NIVEL.match(t)
        return m.group(1) if m else t
    return t


def opcoes(pares: dict) -> dict[str, list[dict]]:
    """As opções da tela: `{campo: [{"id", "descricao", "chave"}]}` a partir dos pares do `estoque.classificacoes`. A chave que
    duas opções do mesmo campo dividem fica vazia nas duas."""
    out = {}
    for campo in CAMPOS:
        lista = [{"id": str(i), "descricao": str(d), "chave": chave(campo, d)} for i, d in (pares or {}).get(campo, [])]
        repetidas = {k for k, n in Counter(o["chave"] for o in lista).items() if n > 1}
        for o in lista:
            if o["chave"] in repetidas:
                o["chave"] = ""
        out[campo] = lista
    return out


def conferir(escolhidos: dict | None, ops) -> dict[str, dict]:
    """`{campo: {"id", "descricao"}}` só dos campos que vieram com id, cada id conferido contra as opções (`ops`: as opções do
    `opcoes`, ou uma função que as dá, chamada só se algum id veio: sem id, nem se lê o Fracttal). `ValueError` (nada vai ao
    Fracttal) para o campo desconhecido e o id que não está nas opções."""
    vindos = {}
    for campo, valor in (escolhidos or {}).items():
        if campo not in CAMPOS:
            raise ValueError(f"Campo que a peça não tem: {str(campo)[:20]!r}.")
        v = str(valor or "").strip()
        if v:
            vindos[campo] = v
    if not vindos:
        return {}
    todas = ops() if callable(ops) else ops
    out = {}
    for campo, v in vindos.items():
        achada = next((o for o in (todas or {}).get(campo, []) if o["id"] == v), None)
        if achada is None:
            raise ValueError(f"O {CURTO[campo]} {v[:20]!r} não está nas opções do Fracttal: recarregue a página e escolha de "
                             "novo. Nada foi enviado ao Fracttal.")
        out[campo] = {"id": achada["id"], "descricao": achada["descricao"]}
    return out


def faltam(gravados: dict | None) -> list[str]:
    """Os campos que o cadastro deixou "sem" (o rótulo curto, na ordem da tela): é o que o PCM completa no Fracttal. Sem o
    registro (`None`: a decisão de antes de 12/11/2026, quando nada disso ia pela API), os três."""
    return [CURTO[c] for c in CAMPOS if not (gravados or {}).get(c)]


# ── a cópia de 1 h das opções ───────────────────────────────────────────────────────────────────────────────────────────
# As opções são da empresa (as mesmas para todo o PCM), e lê-las são algumas páginas da lista de peças: uma cópia na memória do
# processo, por 1 h. A trava só guarda a troca da cópia, nunca a leitura do Fracttal (o PCM inteiro esperaria por ela); duas
# primeiras leituras juntas leem as duas, e a última vale. O erro não fica guardado.
_COPIA: dict = {"quando": None, "opcoes": None}
_TRAVA = threading.Lock()


def guardadas(estoque, relogio=time.monotonic) -> dict[str, list[dict]]:
    """As opções da tela (`opcoes`), da cópia de 1 h ou lidas agora pelo `estoque` (o login do Fracttal de quem pede)."""
    agora = relogio()
    with _TRAVA:
        if _COPIA["opcoes"] is not None and agora - _COPIA["quando"] < TTL_S:
            return _COPIA["opcoes"]
    lidas = opcoes(estoque.classificacoes())
    with _TRAVA:
        _COPIA.update(quando=agora, opcoes=lidas)
    return lidas


def limpar() -> None:
    with _TRAVA:
        _COPIA.update(quando=None, opcoes=None)
