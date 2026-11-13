# -*- coding: utf-8 -*-
"""Recoleta pela API PV (Levi, 13/11/2026: "deve ter algum campo para fazer uma recoleta pela API... a pessoa seleciona a
usina, seleciona o período... se ela quer recoletar geração, ETM... vai mostrar da mesma forma que já mostra, o que não
está batendo fica em amarelo").

O app NÃO fala com a API PV: a senha dela não pode viajar dentro do .exe (o coletor já teve isso). Ele pede ao servidor
da plataforma (`/api/recoleta/apipv`, plataforma/recoleta_apipv.py no Projeto API PV), que entra na API com a conta da
coleta e devolve o dado CRU por planta do supervisório; aqui o de-para é o da aba Equipamentos do BD_Performance (o mesmo
do coletor: planta e equipamento do supervisório -> aba e coluna do BD) e as células vão para a MESMA montagem da
conversão de arquivo (amarelo = valor novo, 0 nunca cobre dado, só dia fechado, planilha para colar). Nada é gravado no BD.

Chave: o servidor só atende quem manda `X-Recoleta-Chave`. Ela mora no arquivo "Conversor Grid Co - recoleta.txt" da
pasta de publicação (a mesma do versao.json, que só a equipe sincroniza); `CONVERSOR_RECOLETA_CHAVE` no ambiente vence.
Custo: cada planta × dia gasta 1 consulta da cota da API PV para a geração e 1 para a ETM; o servidor tem teto por dia.
"""
import datetime as dt
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request

from conversor.nucleo import BD_PERFORMANCE, BD_THOPEN, Celula

SERVIDOR = os.environ.get("CONVERSOR_SERVIDOR", "https://app.gridco.com.br").rstrip("/")
ARQ_CHAVE = "Conversor Grid Co - recoleta.txt"
FONTE = "API PV (recoleta)"
MAX_DIAS = 7                     # o servidor recusa mais; o período maior vai em fatias, com o andamento na tela


class Falha(Exception):
    pass


def chave(caminho_bd_perf=None):
    v = os.environ.get("CONVERSOR_RECOLETA_CHAVE", "").strip()
    if v:
        return v
    from conversor import atualizacao
    pasta = atualizacao.pasta_publicacao(caminho_bd_perf)
    p = os.path.join(pasta, ARQ_CHAVE) if pasta else None
    if not p or not os.path.isfile(p):
        return ""
    with open(p, encoding="utf-8") as f:
        return f.read().strip()


def _pedir(rota, chave_, corpo=None, timeout=180):
    if not chave_:
        raise Falha("Sem a chave da recoleta neste computador: falta o arquivo \"%s\" na pasta 1. Performance "
                    "(a mesma das versões do Conversor). Peça ao Levi." % ARQ_CHAVE)
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(SERVIDOR + rota, data=dados, method="POST" if corpo is not None else "GET",
                                 headers={"X-Recoleta-Chave": chave_, "Content-Type": "application/json",
                                          "User-Agent": "Conversor Grid Co"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("erro")
        except Exception:
            msg = None
        raise Falha(msg or "o servidor respondeu HTTP %d" % e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Falha("sem resposta do servidor da Grid Co. (%s)" % getattr(e, "reason", e))


def chave_nome(nome):
    """A chave do coletor (`coletar_pvoperation.chave_nome`): sem o " (NNN)" do supervisório, sem acento, sem espaço,
    sem caixa. A API escreve "Ceilandia 1.1 (89)" e o cadastro "Ceilândia 1.1 (89)"; a Rodrigues 2 virou "INVERSOR01"."""
    s = re.sub(r"\s*\(\d+\)\s*$", "", str(nome or "")).strip()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"\s+", "", s).lower()


def mapa(portal, plantas_api):
    """Quem dá para recoletar. portal = furos.portal (aba Equipamentos: {usina: {"plantas", "inv": {inv: [planta, eq]}}});
    plantas_api = [{"id", "nome", "cadastro"}] do servidor. Devolve {usina: {"plantas": [(id, nome no portal)],
    "inv": {(id, chave do equipamento): "Inversor N.M"}, "sem": [planta sem par na API]}}, só usinas com alguma planta."""
    por_chave = {}
    for p in plantas_api:
        for n in {chave_nome(p.get("nome")), chave_nome(p.get("cadastro"))} - {""}:
            por_chave.setdefault(n, set()).add(int(p["id"]))
    out = {}
    for usina, u in portal.items():
        ids, sem = [], []
        for pl in u.get("plantas") or []:
            achou = por_chave.get(chave_nome(pl)) or set()
            if len(achou) == 1:                            # duas plantas da API com o mesmo nome: não adivinha
                ids.append((next(iter(achou)), pl))
            else:
                sem.append(pl)
        if not ids:
            continue
        de_pl = {chave_nome(pl): i for i, pl in ids}
        inv = {}
        for nome_inv, (pl, eq) in (u.get("inv") or {}).items():
            i = de_pl.get(chave_nome(pl))
            if i is not None and eq:
                inv[(i, chave_nome(eq))] = nome_inv
        out[usina] = {"plantas": ids, "inv": inv, "sem": sem}
    return out


def destino_de(ctx, usina):
    """O BD que tem a aba: a coleta da API PV preenche o BD_Thopen; a do BD_Performance também vale se a aba for dele."""
    for d in (BD_THOPEN, BD_PERFORMANCE):
        if ctx.aba(d, usina):
            return d
    return None


def fatias(ini, fim, n=MAX_DIAS):
    out, a = [], ini
    while a <= fim:
        b = min(fim, a + dt.timedelta(days=n - 1))
        out.append((a, b))
        a = b + dt.timedelta(days=1)
    return out


def pedir_fatia(chave_, ids, ini, fim, geracao, etm):
    return _pedir("/api/recoleta/apipv", chave_, {"ids": list(ids), "ini": ini.isoformat(), "fim": fim.isoformat(),
                                                  "geracao": bool(geracao), "etm": bool(etm)})


def plantas(chave_):
    return _pedir("/api/recoleta/apipv/plantas", chave_)


def celulas(respostas, usina, destino, m, geracao, etm):
    """Respostas do servidor (uma por fatia) -> ([Celula], [aviso]). Equipamento sem de-para vira aviso (o coletor
    também não o grava); IPOA/GHI da usina com várias plantas: a 1ª planta do cadastro que tem estação."""
    cel, avisos, sem_depara, falhas = [], [], set(), []
    ordem = [i for i, _ in m["plantas"]]
    nome_pl = dict(m["plantas"])
    irr = {}                                               # (dia, "IPOA"/"GHI") -> [(ordem da planta, valor)]
    for r in respostas:
        for sid, pl in (r.get("plantas") or {}).items():
            i = int(sid)
            for iso, d in (pl.get("dias") or {}).items():
                dia = dt.date.fromisoformat(iso)
                if d.get("erro"):
                    falhas.append("%s %s: %s" % (nome_pl.get(i, sid), dia.strftime("%d/%m"), d["erro"]))
                    continue
                if geracao:
                    for eq, v in (d.get("ger") or {}).items():
                        col = m["inv"].get((i, chave_nome(eq)))
                        if col is None:
                            sem_depara.add("%s · %s" % (nome_pl.get(i, sid), eq))
                        elif isinstance(v, (int, float)):
                            cel.append(Celula(destino, usina, dia, col, round(float(v), 2)))
                if etm:
                    for k, col in (("ipoa", "IPOA"), ("ghi", "GHI")):
                        if isinstance(d.get(k), (int, float)):
                            irr.setdefault((dia, col), []).append((ordem.index(i) if i in ordem else 99, d[k]))
    for (dia, col), vs in sorted(irr.items()):
        cel.append(Celula(destino, usina, dia, col, round(float(sorted(vs)[0][1]), 4)))      # 4 casas, como o BD e o servidor
    if sem_depara:
        avisos.append(("leve", "%d equipamento(s) da API sem de-para na aba Equipamentos (a coleta também não os grava): %s"
                       % (len(sem_depara), ", ".join(sorted(sem_depara)[:8]) + (" ..." if len(sem_depara) > 8 else ""))))
    if m.get("sem"):
        avisos.append(("leve", "planta(s) do cadastro sem par na API PV, fora da recoleta: %s" % ", ".join(m["sem"])))
    if falhas:
        avisos.append(("erro", "a API PV não respondeu para %d dia(s): %s" % (len(falhas), "; ".join(falhas[:6]))))
    return cel, avisos
