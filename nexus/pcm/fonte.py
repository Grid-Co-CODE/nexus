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
import urllib.error
import urllib.request
from dataclasses import dataclass

URL_PADRAO = "https://raw.githubusercontent.com/fillipefigueiro-source/gridco-pcm-data/main/banco_dados.json"
# O repositório do PCM (o robô do App mora nele). A publicação da semana (publicar.py) e o plano publicado que o
# histórico lê (historico_banco.py) vão nele; trocar de dono (o repositório sai da conta do Fillipe até 03/11) é mudar
# NEXUS_PCM_REPO, sem tocar no código.
REPO_PADRAO = "fillipefigueiro-source/gridco-pcm-data"
RAMO_PADRAO = "main"
# O robô publica a cada ~30 min; 5 min de cópia em memória poupa baixar 6 MB a cada clique sem ficar para trás.
TTL_S = 300
TIMEOUT_S = 30

# fonte -> (monotonic da última conferência, dados, epoch do download, ETag do GitHub)
_cache: dict[str, tuple[float, dict, float, str | None]] = {}
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


def repositorio(config) -> tuple[str, str]:
    """(dono/repositório, ramo) do repositório do PCM."""
    repo = str(config.get("NEXUS_PCM_REPO") or os.environ.get("NEXUS_PCM_REPO") or REPO_PADRAO).strip("/")
    ramo = str(config.get("NEXUS_PCM_RAMO") or os.environ.get("NEXUS_PCM_RAMO") or RAMO_PADRAO)
    return repo, ramo


def endereco(config) -> str:
    return str(config.get("NEXUS_PCM_FONTE") or os.environ.get("NEXUS_PCM_FONTE") or URL_PADRAO)


def _validar(d) -> dict:
    if not isinstance(d, dict) or not isinstance(d.get("semanas"), list):
        raise FonteErro("o arquivo não tem a lista de semanas")
    if not any(isinstance(s, dict) and s.get("week") and isinstance(s.get("rows"), list) for s in d["semanas"]):
        raise FonteErro("nenhuma semana com linhas no arquivo")
    return d


def _baixar(fonte: str, validar=_validar, etag: str | None = None) -> tuple[dict | None, str | None]:
    """(dados, ETag). Com o ETag da cópia que já está em memória, o GitHub responde 304 se o arquivo não mudou, e os
    dados vêm None: medido em 08/10/2026, o gestao_pcm.json (14,7 MB) levava 1,3 s para baixar e ler a cada 5 min;
    a conferência que dá 304 leva ~40 ms."""
    if fonte.startswith(("http://", "https://")):
        cab = {"User-Agent": "Nexus-GridCo/1 (programacao semanal)"}
        if etag:
            cab["If-None-Match"] = etag
        try:
            with urllib.request.urlopen(urllib.request.Request(fonte, headers=cab), timeout=TIMEOUT_S) as r:  # noqa: S310 — endereço fixo ou do .env
                bruto, etag = r.read(), r.headers.get("ETag")
        except urllib.error.HTTPError as ex:
            if ex.code == 304 and etag:
                return None, etag
            raise
    else:
        with open(fonte, "rb") as f:
            bruto, etag = f.read(), None
    return validar(json.loads(bruto.decode("utf-8"))), etag


def ler(config) -> Leitura:
    return _ler(config, "NEXUS_PCM_FONTE", URL_PADRAO, _validar)


# Gestão PCM (07/10/2026): o gestao_pcm.json (as tarefas do ano, ~14 MB, que o robô gestao-pcm.yml regrava) e o
# mpas.json (a planilha da Gerencial, CIFRADA: o repositório é público), do mesmo repositório do PCM.
URL_GESTAO = URL_PADRAO.rsplit("/", 1)[0] + "/gestao_pcm.json"
URL_MPAS = URL_PADRAO.rsplit("/", 1)[0] + "/mpas.json"


def _validar_gestao(d) -> dict:
    if not isinstance(d, dict) or not isinstance(d.get("tarefas"), list):
        raise FonteErro("o arquivo não tem a lista de tarefas")
    return d


def _validar_mpas(d) -> dict:
    if not isinstance(d, dict) or not all(d.get(k) for k in ("salt", "iv", "ct", "iter")):
        raise FonteErro("o arquivo da Gerencial não tem o pacote cifrado")
    return d


def ler_gestao(config) -> Leitura:
    return _ler(config, "NEXUS_PCM_GESTAO_FONTE", URL_GESTAO, _validar_gestao)


def ler_mpas(config) -> Leitura:
    return _ler(config, "NEXUS_PCM_MPAS_FONTE", URL_MPAS, _validar_mpas)


def _ler(config, chave: str, padrao: str, validar) -> Leitura:
    fonte = str(config.get(chave) or os.environ.get(chave) or padrao)
    if config.get("TESTING") and not (config.get(chave) or os.environ.get(chave)):
        return Leitura(None, fonte, erro="sem fonte configurada nos testes")
    local = not fonte.startswith(("http://", "https://"))
    agora = time.monotonic()
    with _trava:
        em_cache = _cache.get(fonte)
        if em_cache and not local and agora - em_cache[0] < TTL_S:
            return Leitura(em_cache[1], fonte, baixado_em=em_cache[2])
        try:
            dados, etag = _baixar(fonte, validar, em_cache[3] if em_cache and not local else None)
        except FileNotFoundError:
            erro = "arquivo não encontrado"
        except Exception as ex:      # noqa: BLE001 — rede, JSON quebrado, formato errado: tudo vira aviso na tela
            erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        else:
            if dados is None:        # 304: o arquivo não mudou, a cópia em memória vale mais 5 min
                _cache[fonte] = (agora, em_cache[1], em_cache[2], etag)
                return Leitura(em_cache[1], fonte, baixado_em=em_cache[2])
            _cache[fonte] = (agora, dados, time.time(), etag)
            return Leitura(dados, fonte, baixado_em=time.time())
        if em_cache:
            return Leitura(em_cache[1], fonte, baixado_em=em_cache[2], erro=erro, velha=True)
        return Leitura(None, fonte, erro=erro)
