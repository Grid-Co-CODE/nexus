"""Mapa de equipe: o registro de quem abriu o mapa ou a rota de quem (auditoria da LGPD).

Só em memória até o gravador em lote levar ao banco (`nexus_equipe_acessos`). Quem abriu entra pelo código HMAC (o e-mail
nunca vai ao banco); `pessoa_id` é o da ficha, quando há."""
import secrets
import threading
from datetime import timedelta, timezone

from nexus.campo.equipe import CAB_ACESSOS

_BRT = timezone(timedelta(hours=-3))
ACOES = ("abriu_mapa", "abriu_rota")


class Registro:
    def __init__(self):
        self._trava = threading.Lock()
        self._fila: list[list] = []

    def acrescentar(self, acao: str, pessoa_id, pessoa_hmac: str, alvo_pessoa_id, usina_id, agora) -> None:
        d = {"acesso_id": "C" + secrets.token_hex(6)[:11],       # letra + hexadecimal (o tipo vem da coluna)
             "instante": agora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "pessoa_id": pessoa_id,
             "pessoa_hmac": pessoa_hmac, "acao": acao, "alvo_pessoa_id": alvo_pessoa_id, "usina_id": usina_id}
        with self._trava:
            self._fila.append([d[c] for c in CAB_ACESSOS])

    def novos(self) -> list[list]:
        """Linhas de CAB_ACESSOS ainda não publicadas; cada uma sai uma vez."""
        with self._trava:
            fila, self._fila = self._fila, []
        return fila

    def devolver(self, linhas: list[list]) -> None:
        """A publicação falhou: as linhas voltam ao começo da fila para a próxima rodada."""
        with self._trava:
            self._fila = list(linhas) + self._fila
