"""O limite do que um endereço de IP manda ao SSO sem login, por hora.

Os formulários do fornecedor são públicos (o fornecedor não tem conta), então qualquer um poderia encher o disco do
servidor ou os livros do banco. Os tetos são largos, porque a equipe de uma usina sai pelo mesmo IP da operadora do
celular (o CGNAT põe muita gente atrás de um endereço): uma vistoria leva umas 40 fotos, e um diário, fotos e vídeos.
Um processo só do Nexus (o waitress com threads), então a conta fica na memória; reiniciar zera, e não faz mal.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

JANELA_S = 3600
TETOS = {
    "envio": 120,                     # linhas enviadas (APR, EPI, vistoria, diário, presença, visualização)
    "arquivo": 600,                   # arquivos enviados
    "bytes": 3 * 1024 ** 3,           # o que esses arquivos somam
    "consulta": 600,                  # leituras sem login (a sessão ativa, a visualização, o nome do link de assinatura)
    "progresso": 2000,                # o progresso do vídeo (o app manda a cada 4 s)
    "envio_bytes": 50 * 1024 ** 2,    # o que as linhas enviadas somam (a maior linha real tem 130 KB)
    # os tetos de TODOS os anônimos juntos (o IP "*"): vários endereços não enchem o banco nem o disco do servidor
    # (revisão de 12/11/2026)
    "todos_envio_bytes": 500 * 1024 ** 2,
    "todos_bytes": 10 * 1024 ** 3,
}
TODOS = "*"
_CONTAS = defaultdict(deque)          # (ip, tipo) -> deque[(quando, quanto)]
_TRAVA = threading.Lock()


def passou(ip: str, tipo: str, quanto: int = 1, *, agora: float | None = None) -> bool:
    """Conta e diz se o IP passou do teto do tipo na última hora (o que passou não conta)."""
    agora = time.time() if agora is None else agora
    chave = (ip or "?", tipo)
    with _TRAVA:
        fila = _CONTAS[chave]
        while fila and agora - fila[0][0] > JANELA_S:
            fila.popleft()
        if sum(q for _t, q in fila) + quanto > TETOS[tipo]:
            return True
        fila.append((agora, quanto))
        if len(_CONTAS) > 50000:           # o teto da própria conta: some quem não manda nada há uma hora
            for k in [k for k, f in _CONTAS.items() if not f or agora - f[-1][0] > JANELA_S]:
                del _CONTAS[k]
        return False


def zerar() -> None:
    with _TRAVA:
        _CONTAS.clear()
