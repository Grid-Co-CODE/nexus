"""O chamado em aberto de um ativo, para a Inspeção de chamados não abrir outro (25/11/2026).

A fonte é a mesma foto que o App de Campo lê desde a v333 (a ronda de trackers) e a v361 (a OS que não pergunta "ficou
resolvido em campo?" no ativo com chamado aberto): o livro `nexus_chamados_abertos · fato_chamado_aberto`, que o servidor
regrava de 10 em 10 minutos a partir da lista central de OS (`nexus/torres/oscreator/chamados_abertos.py`). Uma fonte só
para as duas pontas: o App e a web dizem a mesma coisa sobre o mesmo ativo.

O caso: uma corretiva de tracker ganhou duas cadeias de chamado (inspeção e administrativa) com 4 dias entre elas, porque
o "Abrir chamado" da web não olhava se o ativo já tinha uma.

Sem a leitura (banco fora, livro que não abre): None, e a criação segue como antes. É a regra do App na OS ("não li" não
cala a pergunta); a do App na ronda, mais dura (503 e fila), é de quem não tem uma pessoa olhando a tela.
"""
from __future__ import annotations

import logging
import re
import threading
import time

log = logging.getLogger(__name__)

TTL_S = 60            # a foto muda de 10 em 10 min; 1 min de memória poupa o banco quando a equipe cria várias seguidas
_MEMO = {"t": 0.0, "por": None}
_TRAVA = threading.Lock()


def canon(code) -> str:
    """O código do ativo como o Nexus liga (o `_cod_canon` do App): sem espaço e em maiúsculas."""
    return re.sub(r"\s+", "", str(code or "")).upper()


def _num(v) -> str:
    """O nº da OS como texto: a API devolve tipado (20475.0) e vazio vira ''."""
    s = str(v if v is not None else "").strip()
    return s.split(".")[0] if re.fullmatch(r"\d+\.0+", s) else s


def _ler() -> dict:
    """{código canônico: {inspecao, adm, coluna}} da foto do banco."""
    from nexus.dados import fato_chamado_aberto as F
    from nexus.dados import livros
    from nexus.dados.conexao import banco
    base, sessao = banco()
    por = {}
    for linha in livros.ler(base, sessao, F.LIVRO, F.ABA):
        c = canon(linha.get("codigo"))
        if c:
            por[c] = {"inspecao": _num(linha.get("inspecao_folio")), "adm": _num(linha.get("adm_folio")),
                      "coluna": str(linha.get("coluna") or "")}
    return por


def do_ativo(code) -> dict | None:
    """O chamado em aberto do ativo ({inspecao, adm, coluna}) ou None (sem chamado, ou sem a leitura)."""
    c = canon(code)
    if not c:
        return None
    with _TRAVA:
        if _MEMO["por"] is None or time.time() - _MEMO["t"] >= TTL_S:
            try:
                _MEMO.update(por=_ler(), t=time.time())
            except Exception as e:      # noqa: BLE001 — sem a foto, cria como antes (o recado fica no log)
                log.warning("chamado aberto: não li a foto do Nexus (%s): %s", type(e).__name__, str(e)[:160])
                return None
        return _MEMO["por"].get(c)


def esquecer() -> None:
    """Zera a memória (os testes)."""
    with _TRAVA:
        _MEMO.update(t=0.0, por=None)
