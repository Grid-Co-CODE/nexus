"""De onde o Nexus lê a programação que está valendo.

Padrão: o MESMO banco_dados.json que o App de Campo e o painel do PCM leem (repositório do PCM no GitHub, publicado pelo
robô a cada rodada). Ler o mesmo arquivo é o que permite comparar número a número antes de o Nexus assumir.

`NEXUS_PCM_FONTE` (config do app ou variável de ambiente) troca a fonte: um endereço http(s) ou um arquivo local.
Nos testes, sem essa chave, NÃO se vai à rede: a tela mostra o aviso de fonte indisponível.
"""
import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass

URL_PADRAO = "https://raw.githubusercontent.com/fillipefigueiro-source/gridco-pcm-data/main/banco_dados.json"
# O robô publica a cada ~30 min; 5 min de cópia em memória poupa baixar 6 MB a cada clique sem ficar para trás.
TTL_S = 300
TIMEOUT_S = 30

_cache: dict[str, tuple[float, dict, float]] = {}
_trava = threading.Lock()


class FonteErro(RuntimeError):
    pass


@dataclass
class Leitura:
    dados: dict | None
    fonte: str
    baixado_em: float | None = None      # epoch da leitura que está em uso
    erro: str = ""                       # preenchido quando a última tentativa falhou
    velha: bool = False                  # True: a tentativa falhou e a tela mostra a última cópia boa


def endereco(config) -> str:
    return str(config.get("NEXUS_PCM_FONTE") or os.environ.get("NEXUS_PCM_FONTE") or URL_PADRAO)


def _validar(d) -> dict:
    if not isinstance(d, dict) or not isinstance(d.get("semanas"), list):
        raise FonteErro("o arquivo não tem a lista de semanas")
    if not any(isinstance(s, dict) and s.get("week") and isinstance(s.get("rows"), list) for s in d["semanas"]):
        raise FonteErro("nenhuma semana com linhas no arquivo")
    return d


def _baixar(fonte: str) -> dict:
    if fonte.startswith(("http://", "https://")):
        req = urllib.request.Request(fonte, headers={"User-Agent": "Nexus-GridCo/1 (programacao semanal)"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:        # noqa: S310 — endereço fixo ou do .env
            bruto = r.read()
    else:
        with open(fonte, "rb") as f:
            bruto = f.read()
    return _validar(json.loads(bruto.decode("utf-8")))


def ler(config) -> Leitura:
    fonte = endereco(config)
    if config.get("TESTING") and not (config.get("NEXUS_PCM_FONTE") or os.environ.get("NEXUS_PCM_FONTE")):
        return Leitura(None, fonte, erro="sem fonte configurada nos testes")
    local = not fonte.startswith(("http://", "https://"))
    agora = time.monotonic()
    with _trava:
        em_cache = _cache.get(fonte)
        if em_cache and not local and agora - em_cache[0] < TTL_S:
            return Leitura(em_cache[1], fonte, baixado_em=em_cache[2])
        try:
            dados = _baixar(fonte)
        except FileNotFoundError:
            erro = "arquivo não encontrado"
        except Exception as ex:      # noqa: BLE001 — rede, JSON quebrado, formato errado: tudo vira aviso na tela
            erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        else:
            _cache[fonte] = (agora, dados, time.time())
            return Leitura(dados, fonte, baixado_em=time.time())
        if em_cache:
            return Leitura(em_cache[1], fonte, baixado_em=em_cache[2], erro=erro, velha=True)
        return Leitura(None, fonte, erro=erro)
