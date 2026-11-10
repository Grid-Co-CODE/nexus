"""Mapa de equipe: o registro de quem abriu o mapa, a rota ou o percurso de quem (auditoria da LGPD). O percurso
(10/11/2026) leva junto o período visto (`periodo`), para responder "quem viu o percurso de quem e de que período".

A linha vai a um jornal cifrado em disco (`jornal.Fila`) ANTES de o mapa ou a rota abrir, e de lá o gravador em lote a
leva ao banco (`nexus_equipe_acessos`): o reinício antes da gravação (todo push reinicia o servidor) não apaga a trilha
(revisão final de 08/11/2026). O disco que falha sobe `OSError`, e a tela não abre sem o registro. Quem abriu entra pelo
código HMAC (o e-mail nunca vai ao banco); `pessoa_id` é o da ficha do e-mail exato, quando há."""
import secrets
from datetime import timedelta, timezone

from nexus.campo.equipe import CAB_ACESSOS
from nexus.campo.equipe.jornal import Fila

_BRT = timezone(timedelta(hours=-3))
ACOES = ("abriu_mapa", "abriu_rota", "abriu_percurso")
_UTC = "%Y-%m-%dT%H:%M:%SZ"


class Registro:
    def __init__(self, fila: Fila | None = None):
        self._fila = fila if fila is not None else Fila()

    def acrescentar(self, acao: str, pessoa_id, pessoa_hmac: str, alvo_pessoa_id, usina_id, agora,
                    periodo=None) -> None:
        """`periodo` = (de, até), os instantes do percurso visto (só no abriu_percurso)."""
        de, ate = periodo if periodo else (None, None)
        d = {"acesso_id": "C" + secrets.token_hex(6)[:11],       # letra + hexadecimal (o tipo vem da coluna)
             "instante": agora.astimezone(timezone.utc).strftime(_UTC),
             "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "pessoa_id": pessoa_id,
             "pessoa_hmac": pessoa_hmac, "acao": acao, "alvo_pessoa_id": alvo_pessoa_id, "usina_id": usina_id,
             "periodo_de": de.astimezone(timezone.utc).strftime(_UTC) if de else None,
             "periodo_ate": ate.astimezone(timezone.utc).strftime(_UTC) if ate else None}
        self._fila.acrescentar([[d[c] for c in CAB_ACESSOS]])

    def novos(self) -> list[list]:
        """Linhas de CAB_ACESSOS ainda não publicadas; cada uma sai uma vez."""
        return self._fila.retirar()

    def devolver(self, linhas: list[list]) -> None:
        """A publicação falhou: as linhas voltam ao começo da fila para a próxima rodada."""
        self._fila.devolver(linhas)

    def confirmar(self, linhas: list[list]) -> None:
        """A publicação deu certo: o jornal é aparado destas linhas."""
        self._fila.confirmar(linhas)
