# -*- coding: utf-8 -*-
"""Canal de atualização do Conversor: a pasta do SharePoint "Gridco > 4. O&M > 9.Pós Operação > 1. Performance",
que o OneDrive da equipe já sincroniza (é a mesma biblioteca do BD_Performance).

Pedido do Levi (10/11/2026): "jogue o .exe aqui... gostaria que se eu atualizasse algo já subisse para os usuários".
Cada release grava na pasta o instalador ("Conversor Grid Co - Instalar.exe") e o "Conversor Grid Co - versao.json";
o app de cada pessoa lê o versao.json ao abrir e, se a versão for maior, mostra "Atualizar para X — o que mudou"; o
clique copia o instalador da pasta e instala em silêncio (fecha, troca, abre de novo). Sem GitHub público e sem custo:
a pasta é interna. O GitHub de releases fica só de reserva, para quem não sincroniza a biblioteca."""
import json
import os

from conversor.nucleo import BD_PADRAO, BD_PERFORMANCE

NOME_INSTALADOR = "Conversor Grid Co - Instalar.exe"
NOME_VERSAO = "Conversor Grid Co - versao.json"
_SUB = ("9.Pós Operação", "1. Performance")


def _tupla(v):
    return tuple(int(p) if str(p).isdigit() else 0 for p in str(v or "").split("."))


def pasta_publicacao(caminho_bd_perf=None):
    """A pasta "1. Performance" na cópia local da biblioteca "4. O&M". Acha subindo a partir do BD_Performance (cada
    pessoa sincroniza num caminho: atalho "Grid Co_ - 4. O&M" no OneDrive ou a biblioteca inteira em "GRID CO\\...")."""
    candidatos = []
    for base in (caminho_bd_perf, BD_PADRAO[BD_PERFORMANCE]):
        if not base:
            continue
        p = os.path.dirname(base)
        for _ in range(8):
            if os.path.basename(p).lower().endswith("4. o&m"):
                candidatos.append(os.path.join(p, *_SUB))
                break
            novo = os.path.dirname(p)
            if novo == p:
                break
            p = novo
    for c in candidatos:
        if os.path.isdir(c):
            return c
    # o BD não está no caminho do Levi nem foi apontado: procura a biblioteca no OneDrive desta pessoa (11/11/2026, a
    # Lara sincroniza em "Shortcuts\GRID CO_ - 4. O&M" e o app dela ficou na 1.0.0 sem ver nenhuma versão)
    from conversor.nucleo import achar_biblioteca
    lib = achar_biblioteca("4. o&m")
    if lib and os.path.isdir(os.path.join(lib, *_SUB)):
        return os.path.join(lib, *_SUB)
    return candidatos[0] if candidatos else None


def ler_versao(pasta):
    """{'versao', 'notas', 'instalador'} do versao.json da pasta, ou None."""
    if not pasta:
        return None
    p = os.path.join(pasta, NOME_VERSAO)
    try:
        with open(p, encoding="utf-8-sig") as f:
            info = json.load(f)
    except (OSError, ValueError):
        return None
    inst = os.path.join(pasta, info.get("instalador") or NOME_INSTALADOR)
    notas = info.get("notas") or []
    return {"versao": str(info.get("versao") or "").strip(), "instalador": inst,
            "notas": notas if isinstance(notas, list) else [str(notas)],
            "tamanho": info.get("tamanho"), "sha256": info.get("sha256")}


def instalador_confere(info):
    """O instalador da pasta é o da versão anunciada? O versao.json é pequeno e chega antes; o instalador (17 MB) pode
    ainda ser o anterior no OneDrive da pessoa (Lara, 11/11/2026: rodou o da pasta e "ficou no 1.0.3"). Sem tamanho e
    sha256 no json (versões até a 1.0.4), confia no arquivo."""
    p = info.get("instalador")
    if not p or not os.path.isfile(p):
        return False
    if info.get("tamanho") and os.path.getsize(p) != int(info["tamanho"]):
        return False
    if info.get("sha256"):
        import hashlib
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest().lower() == str(info["sha256"]).lower()
    return True


def nova_versao(atual, caminho_bd_perf=None):
    """a info da versão da pasta se ela for MAIOR que a atual; senão None."""
    info = ler_versao(pasta_publicacao(caminho_bd_perf))
    if info and info["versao"] and _tupla(info["versao"]) > _tupla(atual):
        info["pronto"] = instalador_confere(info)
        return info
    return None
