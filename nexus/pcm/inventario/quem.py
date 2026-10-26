"""Quem decidiu, nas colunas do livro do inventário (26/10/2026): `pessoa_hmac` (sempre que a pessoa tem e-mail) e
`pessoa_id` (quando o cadastro a acha). A régua e a curadoria gravam por aqui, para a pessoa entrar do mesmo jeito nas
duas.

O livro do inventário é lido pela API do banco, que é aberta: nome e e-mail nunca vão em coluna. O `pessoa_hmac` é o
`codigo_da_pessoa` (HMAC-SHA256 do e-mail com a NEXUS_PESSOA_HMAC, 24 hexadecimais), o mesmo código que o App manda; o
`pessoa_id` sai do cadastro por esse código (e-mail que bate em duas fichas não liga: ID errado é pior que ID nenhum).
Quem entra pela senha de administrador não tem e-mail: a decisão vale e vai sem pessoa (como a Técnicos por usina).

O `pessoa_id` é o único dado daqui que pode faltar sem a decisão deixar de valer: o cadastro lido no banco pode estar
fora do ar naquela hora, e o livro aceita a coluna vazia (o `pessoa_hmac` é o que liga a pessoa, e se traduz depois). Por
isso a leitura do cadastro falha para vazio, e só o que leu bem fica guardado.
"""
from __future__ import annotations

import time

_MAPA_S = 600                       # o mapa código -> pessoa_id fica guardado 10 minutos (decifra o cadastro inteiro)
_MAPA: dict = {"quando": 0.0, "mapa": {}}


def _mapa_de_codigos(cfg) -> dict:
    if _MAPA["mapa"] and time.time() - _MAPA["quando"] < _MAPA_S:
        return _MAPA["mapa"]
    try:
        from ...campo import visao
        from ...campo.ligacao_cadastro import mapas_de
        mapa = mapas_de(cfg, [], visao._livro("cadastro_nexus", "pessoas"))["hmac"]
    except Exception:       # noqa: BLE001 — sem o cadastro (banco fora, chave que não vale, teste): sem o pessoa_id
        return {}
    if mapa:
        _MAPA.update(quando=time.time(), mapa=mapa)
    return mapa


def limpar() -> None:
    _MAPA.update(quando=0.0, mapa={})


def colunas(cfg, pessoa: dict | None) -> dict:
    """`{"pessoa_hmac": ..., "pessoa_id": ...}` de quem decidiu, só com o que se sabe (sem e-mail, vazio). `pessoa` é o
    `{"email", "nome"}` da sessão; um `"id"` já resolvido por quem chama vale."""
    from ...campo.ligacao_cadastro import codigo_da_pessoa
    pessoa = pessoa or {}
    email = str(pessoa.get("email") or "").strip().lower()
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email) if email else None
    if not codigo:
        return {}
    pid = pessoa.get("id") or _mapa_de_codigos(cfg).get(codigo)
    return {"pessoa_hmac": codigo, **({"pessoa_id": pid} if pid else {})}
