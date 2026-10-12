"""Os responsáveis de cada usina para o filtro da Visão gerencial (12/10/2026, Levi: "Quero um filtro de responsável ->
Visão gerencial").

A Visão gerencial é uma tela da Plataforma de Performance dentro da moldura do Nexus (porta única). O nome da pessoa só
existe decifrado aqui: no banco, o cadastro guarda as pessoas cifradas (`sensivel_cifrado`) e a plataforma não tem a
chave, de propósito. Então o Nexus entrega à tela, pela moldura (mesma origem, `postMessage`, só quando ela pede), o mapa
{nome da usina em qualquer base: {"om": responsável O&M, "gestor": gestor de contrato}}, e a plataforma filtra as linhas
dela. Nada de pessoa vai ao banco nem à plataforma por outro caminho.

O nome da usina no Gerencial é o das planilhas (BD_Thopen, BD_Performance), não o do cadastro: os apelidos vêm do de-para
publicado (`cadastro_nexus · de_para`, a seção Ligações entre bases da Governança). Medido em 12/10/2026 contra o
Gerencial do PC: 140 de 161 usinas casam (romano como número; a "Primavera" da planilha é a 1 e a 2 do cadastro, com os
mesmos responsáveis); as 21 que não casam não têm ligação publicada no de-para.
"""
from __future__ import annotations

import re
import time
import unicodedata

# as bases cujos nomes podem ser o da linha do Gerencial (e o do próprio cadastro)
SISTEMAS = ("BD_Performance · Base UFV", "BD_Thopen · Dados Gerais Usinas", "BD_Thopen · aba", "BD_Performance · aba",
            "BD_Operações")
CACHE_S = 600
_ROMANOS = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
_CACHE = {"t": 0.0, "mapa": None}


def chave(nome) -> str:
    """O nome para casar: sem acento, minúsculo, pontuação vira espaço, romano vira número ("Piracicaba I" = "Piracicaba
    1"). A MESMA conta está no gerencial.html da plataforma (`_chaveUsina`): mudou aqui, muda lá."""
    s = unicodedata.normalize("NFD", str(nome or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(_ROMANOS.get(t, t) for t in s.split())


def mapa(usinas, de_para, nome_de) -> dict:
    """`usinas` = [{"id", "nome", "om", "gestor"}] (os ids das pessoas), `de_para` = [{"usina_id", "sistema",
    "chave_externa"}], `nome_de(id)` = o nome da pessoa. → {chave do nome: {"om": nome | None, "gestor": nome | None}}.
    O nome que alcança duas ou mais usinas só fica se elas têm os MESMOS responsáveis; usina sem nenhum dos dois fica
    de fora (a tela diz quantas não têm responsável)."""
    por_id = {str(u["id"]): u for u in usinas or []}
    alcance = {}
    for u in por_id.values():
        alcance.setdefault(chave(u.get("nome")), set()).add(str(u["id"]))
    for d in de_para or []:
        uid = str(d.get("usina_id") or "")
        if d.get("sistema") in SISTEMAS and uid in por_id:
            alcance.setdefault(chave(d.get("chave_externa")), set()).add(uid)
    out = {}
    for k, ids in alcance.items():
        pares = {(por_id[i].get("om") or None, por_id[i].get("gestor") or None) for i in ids}
        if not k or len(pares) != 1:
            continue
        om, gestor = next(iter(pares))
        if om or gestor:
            out[k] = {"om": (nome_de(om) or None) if om else None, "gestor": (nome_de(gestor) or None) if gestor else None}
    return out


def do_cadastro() -> dict | None:
    """O mapa deste Nexus: o cadastro (decifrado aqui) e o de-para publicado no banco, com 10 min de cache. None sem o
    cadastro (sem a NEXUS_CHAVE_CADASTRO): a tela segue sem o filtro."""
    agora = time.time()
    if _CACHE["mapa"] is not None and agora - _CACHE["t"] < CACHE_S:
        return _CACHE["mapa"]
    from ..cadastro.telas import SemCadastro, servico
    try:
        srv = servico()
    except SemCadastro:
        return None
    usinas = [{"id": u.id, "nome": u.titulo, "om": u.valor("responsavel_om"), "gestor": u.valor("gestor_contrato")}
              for u in srv.registros("usinas")]
    try:
        from ..campo.visao import _livro            # o mesmo leitor do banco (cache de 2 min; teste nunca vai à rede)
        de_para = _livro("cadastro_nexus", "de_para")
    except Exception:                               # noqa: BLE001 — sem o de-para, casa só pelo nome do cadastro
        de_para = []
    m = mapa(usinas, de_para, lambda i: srv.titulo_de("pessoas", i))
    _CACHE.update(t=agora, mapa=m)
    return m
