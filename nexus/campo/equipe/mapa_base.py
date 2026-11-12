"""O mapa base do Brasil do Mapa de equipe (11/11/2026).

Levi, com o guia e a prévia do Willian: "Quero que utilize essa referência para completar nosso mapa" (só o Brasil, sem
3D, no estilo do Nexus). O mapa de ruas é NOSSO: nenhum bloco de terceiro vê a região que o COS está olhando (o guia, LGPD
item 2). É um arquivo PMTiles do Brasil (os dados do OpenStreetMap no esquema do Protomaps, recortados do build diário
pela `ferramentas/mapa_base_brasil.py`; 2,39 GB até o zoom 14 em 11/11/2026), grande demais para o git: sobe pelo próprio
Nexus em partes (escolha do Levi: "Upload pelo Nexus"), em Base > Mapa base, só administrador, e o MapLibre o lê por
pedaço (HTTP Range) na rota `/t/campo/equipe/mapa-base.pmtiles`.

A subida: `iniciar` (o tamanho e, se houver, o SHA-256 que a ferramenta imprimiu) abre o `.parcial`; cada `parte` chega
no deslocamento seguinte (a página retoma de onde parou) e é conferida pelo SHA-256 dela; `concluir` confere o arquivo
inteiro (o tamanho, o SHA-256 se foi dado, o cabeçalho do PMTiles v3 com blocos MVT e as faixas dentro do arquivo) e só
então troca o que estava no ar (`os.replace`, atômico). Arquivo que não confere não derruba o que estava no ar.

Sem o arquivo, o Mapa de equipe usa o desenho dos estados de antes (o mesmo SVG): o deploy não depende do upload.
"""
import hashlib
import json
import os
import shutil
import struct
from datetime import datetime, timezone
from pathlib import Path

from ...cadastro.ligacoes import pasta_dados

NOME = "brasil.pmtiles"
PARCIAL = NOME + ".parcial"
FICHA = "brasil.json"
FICHA_PARCIAL = "brasil.parcial.json"
PARTE_MAX = 8 * 1024 * 1024             # o Nexus aceita 25 MB por pedido; 8 MB passa por qualquer proxy no caminho
FOLGA_DISCO = 512 * 1024 * 1024         # o disco do servidor fica com meio GB livre depois do arquivo
TAMANHO_MAX = 8 * 1024 ** 3             # o Brasil até o zoom 15 dá 5,8 GB; mais que 8 GB é engano
MAGICO = b"PMTiles"


class Recusa(Exception):
    def __init__(self, status: int, texto: str, **extra):
        super().__init__(texto)
        self.status, self.texto, self.extra = status, texto, extra


def pasta(cfg) -> Path:
    return pasta_dados(cfg) / "mapa"


def arquivo(cfg) -> Path | None:
    """O arquivo no ar, ou None (o Mapa de equipe usa o desenho dos estados)."""
    try:
        p = pasta(cfg) / NOME
    except RuntimeError:
        return None
    return p if p.is_file() else None


def _ler(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _gravar(p: Path, dado: dict) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dado, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def estado(cfg) -> dict:
    """{"pronto": {tamanho, sha256, enviado_em, por, zoom} | None, "parcial": {tamanho, sha256, recebido} | None}."""
    p = pasta(cfg)
    pronto = None
    if (p / NOME).is_file():
        pronto = _ler(p / FICHA) or {}
        pronto["tamanho"] = (p / NOME).stat().st_size
    parcial = None
    ficha = _ler(p / FICHA_PARCIAL)
    if ficha and (p / PARCIAL).is_file():
        parcial = {**ficha, "recebido": (p / PARCIAL).stat().st_size}
    return {"pronto": pronto, "parcial": parcial}


def iniciar(cfg, tamanho, sha256: str, por: str) -> dict:
    """Abre a subida (ou retoma a do mesmo tamanho e do mesmo SHA-256). Recusa o tamanho absurdo e o disco sem espaço."""
    try:
        tamanho = int(tamanho)
    except (TypeError, ValueError):
        raise Recusa(400, "Tamanho do arquivo inválido.")
    sha256 = str(sha256 or "").strip().lower()
    if not 1024 <= tamanho <= TAMANHO_MAX:
        raise Recusa(400, f"Tamanho fora do esperado ({tamanho} bytes): o mapa base do Brasil tem de 1 a 8 GB.")
    if sha256 and (len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256)):
        raise Recusa(400, "SHA-256 inválido: são 64 caracteres de 0 a 9 e de a a f.")
    p = pasta(cfg)
    p.mkdir(parents=True, exist_ok=True)
    ficha = _ler(p / FICHA_PARCIAL)
    if ficha and ficha.get("tamanho") == tamanho and ficha.get("sha256", "") == sha256 and (p / PARCIAL).is_file():
        return estado(cfg)
    ja = (p / PARCIAL).stat().st_size if (p / PARCIAL).is_file() else 0
    if shutil.disk_usage(p).free + ja < tamanho + FOLGA_DISCO:
        livre = shutil.disk_usage(p).free / 1024 ** 3
        raise Recusa(507, f"Sem espaço no disco do servidor: o arquivo tem {tamanho / 1024 ** 3:.2f} GB e há "
                          f"{livre:.2f} GB livres (é preciso deixar meio GB de folga).")
    with open(p / PARCIAL, "wb"):
        pass
    _gravar(p / FICHA_PARCIAL, {"tamanho": tamanho, "sha256": sha256, "por": por,
                                "inicio": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return estado(cfg)


def parte(cfg, offset, dados: bytes, sha256_da_parte: str) -> int:
    """Junta uma parte no fim do `.parcial`. Ela tem de vir no deslocamento seguinte e bater com o SHA-256 dela."""
    p = pasta(cfg)
    ficha = _ler(p / FICHA_PARCIAL)
    if not ficha or not (p / PARCIAL).is_file():
        raise Recusa(409, "Nenhuma subida aberta: comece de novo.", recebido=0)
    recebido = (p / PARCIAL).stat().st_size
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        raise Recusa(400, "Deslocamento inválido.", recebido=recebido)
    if offset != recebido:
        raise Recusa(409, f"Parte fora de ordem: o servidor tem {recebido} bytes e esta começa em {offset}.",
                     recebido=recebido)
    if len(dados) > PARTE_MAX:
        raise Recusa(413, f"Parte maior que {PARTE_MAX // 1024 ** 2} MB.", recebido=recebido)
    if not dados or hashlib.sha256(dados).hexdigest() != str(sha256_da_parte or "").strip().lower():
        raise Recusa(400, "A parte chegou diferente do que saiu (o SHA-256 não confere): ela será mandada de novo.",
                     recebido=recebido)
    if recebido + len(dados) > ficha["tamanho"]:
        raise Recusa(400, "A parte passa do tamanho do arquivo.", recebido=recebido)
    with open(p / PARCIAL, "ab") as f:
        f.write(dados)
    return recebido + len(dados)


def conferir_cabecalho(cab: bytes, tamanho: int) -> dict:
    """O cabeçalho do PMTiles v3 (127 bytes): a versão, os blocos vetoriais (MVT) e as faixas dentro do arquivo. Devolve
    {min_zoom, max_zoom}; levanta Recusa se não confere."""
    if len(cab) < 127 or cab[:7] != MAGICO or cab[7] != 3:
        raise Recusa(400, "O arquivo não é um PMTiles versão 3 (o cabeçalho não confere).")
    (raiz, raiz_n, meta, meta_n, folhas, folhas_n, dados, dados_n,
     _end, _ent, _cont) = struct.unpack("<QQQQQQQQQQQ", cab[8:96])
    tipo, zmin, zmax = cab[99], cab[100], cab[101]
    if tipo != 1:
        raise Recusa(400, "O PMTiles não é de blocos vetoriais (MVT): não é o mapa base.")
    for nome, ini, n in (("o diretório raiz", raiz, raiz_n), ("os metadados", meta, meta_n),
                         ("os diretórios", folhas, folhas_n), ("os blocos", dados, dados_n)):
        if ini + n > tamanho:
            raise Recusa(400, f"O PMTiles está cortado: {nome} passam do fim do arquivo.")
    return {"min_zoom": zmin, "max_zoom": zmax}


def concluir(cfg, por: str) -> dict:
    """Confere o arquivo inteiro e troca o que estava no ar. Não conferiu: o `.parcial` sai e o que estava no ar fica."""
    p = pasta(cfg)
    ficha = _ler(p / FICHA_PARCIAL)
    if not ficha or not (p / PARCIAL).is_file():
        raise Recusa(409, "Nenhuma subida aberta.")
    recebido = (p / PARCIAL).stat().st_size
    if recebido != ficha["tamanho"]:
        raise Recusa(409, f"Faltam partes: chegaram {recebido} de {ficha['tamanho']} bytes.", recebido=recebido)
    h = hashlib.sha256()
    with open(p / PARCIAL, "rb") as f:
        cab = f.read(127)
        h.update(cab)
        for b in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(b)
    sha = h.hexdigest()
    try:
        if ficha.get("sha256") and sha != ficha["sha256"]:
            raise Recusa(400, f"O SHA-256 do arquivo recebido ({sha}) não é o informado ({ficha['sha256']}).")
        zoom = conferir_cabecalho(cab, recebido)
    except Recusa:
        cancelar(cfg)
        raise
    os.replace(p / PARCIAL, p / NOME)
    pronto = {"sha256": sha, "por": por, "enviado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              **zoom}
    _gravar(p / FICHA, pronto)
    (p / FICHA_PARCIAL).unlink(missing_ok=True)
    return {**pronto, "tamanho": recebido}


def cancelar(cfg) -> None:
    p = pasta(cfg)
    (p / PARCIAL).unlink(missing_ok=True)
    (p / FICHA_PARCIAL).unlink(missing_ok=True)
