"""O mapa das usinas na Visão geral da Visão do responsável (18/10/2026).

Levi: "Para o mapa podemos usar o IBGE como a performance faz"; as decisões dele: Lista | Mapa dentro da Visão geral (os
mesmos filtros e o mesmo clique nos blocos), a cor do ponto pelo nível do bloco clicado (sem bloco, o nível da usina), o
clique no ponto abre o resumo da usina ao lado, e só as usinas no mapa (o clima segue no Mapa de risco da Performance).

O desenho é o do Mapa de risco (`nexus/performance/clima/mapa.py`): o contorno dos estados do IBGE, guardado uma vez no
Nexus, e a mesma projeção. A coordenada é campo sensível do cadastro (cifrada no armazém): ela abre só aqui, no processo do
Nexus, e o navegador recebe o desenho pronto. O número de latitude ou longitude nunca vira texto (a regra da seção do
Mapa de risco em `nexus/performance/CLAUDE.md`), como no mapa do Acompanhamento do PCM.

O recorte é o dos estados que têm usina na lista (com o ponto de cada usina dentro): o supervisor do Paraná vê o Paraná,
"Todos" vê o Brasil das usinas. Usina sem coordenada no cadastro não some: vai para `sem_coordenada`, que a tela lista.
"""
import logging
import time

from ..performance.clima import mapa as M

TTL_S = 300                       # o cadastro muda pouco; 5 min de cópia das coordenadas por app
MIN_GRAUS = 3.0                   # o recorte de uma usina só não vira um zoom de rua
ORDEM = {"ok": 0, "atencao": 1, "critico": 2}       # o que pede ação é desenhado por último: fica por cima
log = logging.getLogger("nexus.campo")


def desenho(usinas: list[dict], coordenadas: dict, bloco: str | None = None) -> dict:
    """O mapa das `usinas` (as linhas da Visão geral). `coordenadas` = {usina_id em texto: (lat, lon, uf)} do cadastro;
    `bloco` = o bloco destacado (a cor do ponto) ou None (o nível da usina). Devolve {"viewbox", "ufs": [{"d", "sigla",
    "x", "y"}], "pontos": [{"usina_id", "usina", "x", "y", "nivel"}], "sem_coordenada": [nomes]}; sem nenhuma usina com
    coordenada, `viewbox` None."""
    com, sem = [], []
    for u in usinas:
        c = coordenadas.get(str(u.get("usina_id")))
        (com if c else sem).append((u, c))
    sem_coord = [u.get("usina") or "" for u, _ in sem]
    if not com:
        return {"viewbox": None, "ufs": [], "pontos": [], "sem_coordenada": sem_coord}
    ufs = {c[2] for _, c in com if c[2]}
    caixas = [e.caixa for e in M.estados() if e.sigla in ufs]
    caixas += [(c[1], c[0], c[1], c[0]) for _, c in com]                 # o ponto de cada usina sempre dentro
    lon0, lat0 = min(x[0] for x in caixas), min(x[1] for x in caixas)
    lon1, lat1 = max(x[2] for x in caixas), max(x[3] for x in caixas)
    if lon1 - lon0 < MIN_GRAUS:
        meio = (lon0 + lon1) / 2
        lon0, lon1 = meio - MIN_GRAUS / 2, meio + MIN_GRAUS / 2
    if lat1 - lat0 < MIN_GRAUS:
        meio = (lat0 + lat1) / 2
        lat0, lat1 = meio - MIN_GRAUS / 2, meio + MIN_GRAUS / 2
    v = M.vista_de_caixa("responsaveis", "Usinas", lon0, lat0, lon1, lat1, margem=0.06)
    pontos = []
    for u, c in com:
        x, y = v.ponto(c[0], c[1])
        nivel = ((u.get(bloco) or {}).get("nivel") if bloco else u.get("nivel")) or "ok"
        pontos.append({"usina_id": u.get("usina_id"), "usina": u.get("usina") or "", "x": M._n(round(x, 1)),
                       "y": M._n(round(y, 1)), "nivel": nivel})
    pontos.sort(key=lambda p: ORDEM.get(p["nivel"], 0))
    return {"viewbox": v.viewbox, "pontos": pontos, "sem_coordenada": sem_coord,
            "ufs": [{"d": f.d, "sigla": f.sigla, "x": f.x, "y": f.y} for f in M.ufs_da_vista(v)]}


_GUARDA: dict = {}


def coordenadas() -> tuple[dict, str]:
    """({usina_id em texto: (lat, lon, uf)}, erro) das usinas em operação com coordenada no cadastro desta máquina, numa
    cópia de 5 min por app. Sem o cadastro (a chave, o armazém, o teste sem armazém), ({}, o porquê): a tela avisa."""
    from flask import current_app
    from ..performance.clima import usinas as CU
    chave = id(current_app._get_current_object())
    g = _GUARDA.get(chave)
    if g and time.monotonic() - g[0] < TTL_S:
        return g[1], g[2]
    try:
        cad = CU.do_app()
        coords, erro = {str(u.id): (u.lat, u.lon, u.uf) for u in cad.usinas}, ""
    except CU.SemCadastro as e:
        coords, erro = {}, str(e)
    except Exception as e:      # noqa: BLE001 — sem o cadastro, a lista continua; o mapa diz por quê
        log.exception("mapa das usinas: o cadastro não abriu")
        coords, erro = {}, f"{type(e).__name__}"
    _GUARDA[chave] = (time.monotonic(), coords, erro)
    return coords, erro


def limpar() -> None:
    _GUARDA.clear()
