"""Mapa de equipe: as chaves dos aparelhos e a regra de quem é coletado.

O Nexus Field (casca Android) recebe do Nexus uma chave POR APARELHO e a manda em `Authorization: Bearer <chave>` com as
posições. O banco só vê o HASH (sha256 da chave como o aparelho a envia): quem lê o livro não consegue se passar por um
técnico. A chave em claro existe só no retorno de `emitir` e nunca vai a log.

Aqui só há regra pura e o estado das chaves; os eventos esperam a gravação em lote numa `jornal.Fila` (no servidor,
espelhada em disco: o reinício antes da gravação não perde a chave emitida nem a revogada) e saem por `eventos_novos`.
"""
import base64
import hashlib
import secrets
import threading
from datetime import timedelta, timezone

from nexus.campo.equipe import CAB_APARELHOS  # a ordem das colunas de eventos_novos
from nexus.campo.equipe.jornal import Fila

_BRT = timezone(timedelta(hours=-3))


def _hash(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def _instante(agora) -> str:
    # mesmo formato dos outros fatos do Nexus (decisao_pt.py): UTC com Z; a hora que a pessoa vê é sempre Brasília
    return agora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _data_id(agora) -> int:
    # o dia é o de Brasília (regra 7 do nexus/dados/CLAUDE.md), não o do UTC
    return int(agora.astimezone(_BRT).strftime("%Y%m%d"))


def _novo_id() -> str:
    # letra + 11 hexadecimais: a API do banco infere o tipo da coluna e só algarismos voltaria número
    return "A" + secrets.token_hex(6)[:11]


class Chaveiro:
    """As chaves ativas (hash -> (pessoa_id, aparelho)) e a fila de eventos a publicar. A fila é um `jornal.Fila`: no
    servidor, espelhada em disco (o reinício antes da gravação não perde a chave emitida nem a revogada); sem ela, só
    memória."""

    def __init__(self, fila: Fila | None = None):
        self._trava = threading.Lock()
        self._ativas: dict[str, tuple[int, str]] = {}
        self._fila = fila if fila is not None else Fila()

    @staticmethod
    def _evento(agora, pessoa_id, aparelho, evento, chave_hash, app) -> list:
        d = {"evento_id": _novo_id(), "instante": _instante(agora), "data_id": _data_id(agora),
             "pessoa_id": pessoa_id, "aparelho": aparelho, "evento": evento, "chave_hash": chave_hash, "app": app}
        return [d[c] for c in CAB_APARELHOS]

    def emitir(self, pessoa_id: int, aparelho: str, app: str, agora) -> str:
        """A chave nova do par. Os eventos vão ao jornal ANTES de a chave valer: o disco que falha sobe `OSError` e nada
        muda (a velha segue valendo, a nova nunca existiu)."""
        chave = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
        h = _hash(chave)
        with self._trava:
            # uma chave por par pessoa+aparelho: a nova revoga a velha (celular reinstalado, login refeito)
            velhas = [v for v, par in self._ativas.items() if par == (pessoa_id, aparelho)]
            eventos = [self._evento(agora, pessoa_id, aparelho, "revogada", v, app) for v in velhas]
            self._fila.acrescentar(eventos + [self._evento(agora, pessoa_id, aparelho, "emitida", h, app)])
            for v in velhas:
                del self._ativas[v]
            self._ativas[h] = (pessoa_id, aparelho)
        return chave

    def quem(self, chave):
        """(pessoa_id, aparelho) da chave ativa, ou None. Nunca levanta: o que chega do aparelho é entrada hostil."""
        if not isinstance(chave, str) or not chave:
            return None
        try:
            h = _hash(chave)
        except Exception:
            return None
        with self._trava:
            return self._ativas.get(h)

    def revogar(self, chave, agora) -> bool:
        if not isinstance(chave, str) or not chave:
            return False
        h = _hash(chave)
        with self._trava:
            par = self._ativas.get(h)
            if par is None:
                return False
            # no jornal antes de cair: o reinício antes da gravação não pode fazer a chave revogada voltar a valer
            self._fila.acrescentar([self._evento(agora, par[0], par[1], "revogada", h, "")])
            del self._ativas[h]
            return True

    def eventos_novos(self) -> list[list]:
        """Linhas de CAB_APARELHOS ainda não publicadas; cada uma sai uma vez."""
        return self._fila.retirar()

    def devolver(self, linhas: list[list]) -> None:
        """A publicação falhou: os eventos voltam ao começo da fila para a próxima rodada (nenhum se perde)."""
        self._fila.devolver(linhas)

    def confirmar(self, linhas: list[list]) -> None:
        """A publicação deu certo: o jornal é aparado destas linhas."""
        self._fila.confirmar(linhas)

    def carregar(self, eventos: list[dict]) -> None:
        """Reconstrói as ativas no boot a partir do livro e do jornal (as linhas que o banco ainda não tem: a chave
        emitida ou revogada pouco antes do reinício). A API devolve tudo como texto e sem garantia de ordem: por isso
        vale o CONJUNTO (emitida e nunca revogada), não a sequência."""
        eventos = list(eventos) + [dict(zip(CAB_APARELHOS, l)) for l in self._fila.pendentes()]
        revogadas = {str(e.get("chave_hash")) for e in eventos if e.get("evento") == "revogada"}
        with self._trava:
            for e in eventos:
                h = str(e.get("chave_hash") or "")
                if e.get("evento") != "emitida" or not h or h in revogadas:
                    continue
                try:
                    self._ativas[h] = (int(e["pessoa_id"]), str(e.get("aparelho") or ""))
                except (KeyError, TypeError, ValueError):
                    continue


def coleta_vale(pessoa_id: int, tecnicos: dict, piloto: set) -> bool:
    """Só se coleta técnico de campo ativo (o dict de `pessoas_de_campo`) que esteja no piloto; fora da fase de
    piloto ainda não existe "todos", então piloto vazio = ninguém."""
    return pessoa_id in tecnicos and pessoa_id in piloto


def _sim(v) -> bool:
    # a API pode devolver 1/0, "1"/"0", True/False ou texto
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "sim", "s", "t", "yes")
    return bool(v)


def piloto_atual(decisoes: list[dict]) -> set:
    """A última decisão de cada técnico vale (por `instante`; empate = a ordem recebida)."""
    ultima: dict[int, tuple[str, bool]] = {}
    for d in decisoes:
        try:
            pid = int(d.get("pessoa_id"))
        except (TypeError, ValueError):
            continue
        inst = str(d.get("instante") or "")
        if pid not in ultima or inst >= ultima[pid][0]:
            ultima[pid] = (inst, _sim(d.get("no_piloto")))
    return {pid for pid, (_, sim) in ultima.items() if sim}
