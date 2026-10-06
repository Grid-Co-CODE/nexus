"""O Fracttal lido pelo Nexus para as telas da torre Campo · App: só GET, um pedido por vez (Levi, 04/10/2026).

As regras copiadas do App (regras_app.py) chamam fx(path) para ler a fila de verificação (OS em revisão, status 2).
Aqui isso vira um GET com a credencial do OS Creator (a mesma do motor do PCM, nexus.pcm.geracao.credencial).
A cota de 200 pedidos por minuto é da EMPRESA inteira e o App de Campo vive dela.

**O gargalo da Aprovação de OS** (Levi, 05/10/2026: "por qual motivo demora tanto se no histórico de OS do OS Creator
carrega tão rápido?"): a fila em verificação tem ~5.500 tarefas e o REST do Fracttal entrega no máximo 100 por pedido
(medido: limit=1000 devolve 99), então são 55 páginas; cada uma leva ~1,1 s, e até 05/10 elas saíam UMA POR VEZ com
0,5 s de folga: ~90 s. O histórico do OS Creator é rápido porque pergunta outra coisa: o RPC com o login da pessoa, com
o período e o "criado por" filtrados NO SERVIDOR (poucas OS, 200 por página, 6 de uma vez). Agora saem até 4 pedidos
ao mesmo tempo, no máximo 4 por segundo (~15 s para a fila inteira; o App busca 6 de uma vez). Recusa (406/429) dentro
de uma tela sobe na hora; em segundo plano (a releitura da fila), espera 5 s e 10 s e tenta de novo, para uma recusa
não jogar fora as outras 54 páginas.
"""
import threading
import time

from flask import has_request_context

BASE = "https://app.fracttal.com"
INTERVALO_S = 0.25           # no máximo 4 pedidos por segundo saem daqui
SIMULTANEOS = 4              # e no máximo 4 ao mesmo tempo
ESPERAS_RECUSA_S = (5, 10)   # em segundo plano: duas novas tentativas depois de um 406/429
_TRAVA = threading.Lock()
_VAGAS = threading.BoundedSemaphore(SIMULTANEOS)
_ULTIMO = [0.0]
_TOKEN = {"v": "", "exp": 0.0}
_FORNECEDOR = None           # testes: função path -> resposta (dict/list), sem rede


class Recusado(RuntimeError):
    pass


def usar_fornecedor(fornecedor):
    global _FORNECEDOR
    _FORNECEDOR = fornecedor
    _TOKEN.update(v="", exp=0.0)


def _credencial():
    from flask import current_app, has_app_context
    if not has_app_context():
        return None
    from ..pcm.geracao import credencial
    cred = credencial(current_app.config)
    return cred if cred.ok else None


def configurado() -> bool:
    return _FORNECEDOR is not None or _credencial() is not None


def _token() -> str:
    if _TOKEN["v"] and time.time() < _TOKEN["exp"] - 60:
        return _TOKEN["v"]
    # As páginas da fila vêm de threads (o _fx_wo_paralelo do App), fora do contexto do Flask: o token sai da 1ª
    # chamada, que é a do total, feita no contexto da tela.
    cred = _credencial()
    if cred is None:
        raise Recusado("sem a credencial do Fracttal (a do OS Creator)")
    import requests
    r = requests.post(f"{BASE}/oauth/token", timeout=20, data={
        "grant_type": "client_credentials", "client_id": cred.client_id, "client_secret": cred.client_secret})
    r.raise_for_status()
    j = r.json()
    _TOKEN["v"] = j.get("access_token") or ""
    _TOKEN["exp"] = time.time() + float(j.get("expires_in") or 3600)
    if not _TOKEN["v"]:
        raise Recusado("o Fracttal autenticou sem devolver o token")
    return _TOKEN["v"]


def ler(path: str, method: str = "GET", body=None):
    if method.upper() != "GET" or body is not None:
        # defesa: as regras copiadas desta torre só leem; nada do Nexus escreve no Fracttal por aqui
        raise Recusado("o Nexus não escreve no Fracttal")
    if _FORNECEDOR is not None:
        return _FORNECEDOR(path)
    import requests
    token = _token()
    esperas = () if has_request_context() else ESPERAS_RECUSA_S
    for tentativa in range(len(esperas) + 1):
        with _TRAVA:                 # só o ritmo de saída fica em fila; os pedidos andam juntos
            espera = INTERVALO_S - (time.time() - _ULTIMO[0])
            if espera > 0:
                time.sleep(espera)
            _ULTIMO[0] = time.time()
        with _VAGAS:
            r = requests.get(f"{BASE}/api/{path.lstrip('/')}", timeout=30,
                             headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
        if r.status_code not in (406, 429):
            break
        if tentativa < len(esperas):
            time.sleep(esperas[tentativa])
    if r.status_code in (406, 429):
        raise Recusado(f"o Fracttal recusou por excesso de pedidos (HTTP {r.status_code}); a fila não foi lida")
    r.raise_for_status()
    return r.json()
