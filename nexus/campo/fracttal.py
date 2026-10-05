"""O Fracttal lido pelo Nexus para as telas da torre Campo · App: só GET, um pedido por vez (Levi, 04/10/2026).

As regras copiadas do App (regras_app.py) chamam fx(path) para ler a fila de verificação (OS em revisão, status 2).
Aqui isso vira um GET com a credencial do OS Creator (a mesma do motor do PCM, nexus.pcm.geracao.credencial).
A cota de 200 pedidos por minuto é da EMPRESA inteira e o App de Campo vive dela: o App busca 6 páginas de uma vez,
aqui elas vêm uma por vez, com intervalo mínimo, e o cache de 10 min do próprio _fila_bruta segura o resto. Recusa
(406/429) não espera nem insiste: sobe como erro e a tela avisa.
"""
import threading
import time

BASE = "https://app.fracttal.com"
INTERVALO_S = 0.5            # no máximo 2 pedidos por segundo saem daqui
_TRAVA = threading.Lock()
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
    with _TRAVA:
        espera = INTERVALO_S - (time.time() - _ULTIMO[0])
        if espera > 0:
            time.sleep(espera)
        try:
            r = requests.get(f"{BASE}/api/{path.lstrip('/')}", timeout=30,
                             headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
        finally:
            _ULTIMO[0] = time.time()
    if r.status_code in (406, 429):
        raise Recusado(f"o Fracttal recusou por excesso de pedidos (HTTP {r.status_code}); a fila não foi lida")
    r.raise_for_status()
    return r.json()
