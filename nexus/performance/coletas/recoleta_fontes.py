# -*- coding: utf-8 -*-
"""A recoleta pelas fontes na tela Coletas: um cliente só para as rotas `/api/recoleta/<fonte>` da plataforma.

Levi (17/11/2026, no chat da Coleta): "quero formas de coletar os dados novamente pelas nossas fontes de dados e gerar uma
planilha para colar nos BDs... insere no NEXUS > PERFORMANCE > COLETAS". A pessoa escolhe a fonte, a usina, o período e o
que quer (geração, ETM, chuva); a plataforma busca na fonte (as credenciais moram só lá) e devolve o dado já com o nome
do BD; aqui ele vira `Celula` e passa pela MESMA `montagem.montar` da conversão de arquivo. Nada grava no BD.

O contrato é o da plataforma (`plataforma/CLAUDE.md`, "Recoleta por fonte para a Coletas do Nexus"; mudou lá, muda aqui):
- `GET /api/recoleta/<fonte>/plantas?formato=bd` -> {plantas: [{id, usina, destino}], max_dias, max_plantas, paga, teto,
  cota_restante}. A mesma planta pode ir para duas abas (Ouro Branco -> "Ouro Branco 1" e "2") e várias plantas para a
  mesma aba (Ceilândia 2 são 4 ids): a usina da tela é a ABA, com todos os ids dela.
- `POST /api/recoleta/<fonte>?formato=bd` {ids, ini, fim, geracao, etm, chuva, simular} -> {geracao: [{usina, inversor,
  data, kwh}], escalares: [{usina, data, coluna, valor}], avisos: [texto], dias_fora: [{usina, data}], consultas,
  cota_restante, teto}. Com `simular`, só {consultas, cota_restante, teto}: nada é buscado nem gasto.
- Nulo não vem (o 0.0 que vem é leitura). Erro de um dia no meio não vira status de erro: vem 200 com o aviso.
- Recusa: {erro} com 4xx/5xx; o `_pedir` do motor a transforma em `Falha` com o texto, que a tela mostra como veio.

Custo: as fontes pagas (`paga`) têm teto por dia e a reserva da coleta da noite, conferidos na plataforma. A tela mostra
o custo ANTES (`simular`). Quem pode usar é o Nexus que decide (`coletas_tela._pode_recoletar`: só o setor Performance).
"""
import datetime as dt
import json
import os
import threading
import time
import traceback

from . import motor  # noqa: F401 — o motor como `conversor`
from conversor import recoleta as _recoleta  # noqa: E402
from conversor.nucleo import Celula  # noqa: E402

# a ordem é a da tela: primeiro o que não gasta cota (combinado com o chat da Coleta em 17/11/2026)
FONTES = (("pg", "Banco da Thopen"), ("scada", "SCADA Grid Co."), ("apipv", "API PV · conta principal"),
          ("solaredge", "SolarEdge"), ("oem", "API PV · conta oem@"), ("sunop", "SunOp"), ("chuva", "Chuva · API PV"))
NOMES = dict(FONTES)
FONTE_DA_MONTAGEM = "Recoleta · %s"            # o nome que a planilha de saída mostra na coluna da fonte
Falha = _recoleta.Falha


def _rota(fonte, plantas=False):
    if fonte not in NOMES:
        raise Falha("Fonte desconhecida: %s." % fonte)
    return "/api/recoleta/%s%s?formato=bd" % (fonte, "/plantas" if plantas else "")


# A lista de usinas de cada fonte fica guardada 10 min, para todo mundo (Levi, 18/11/2026: "a leitura de usinas da fonte
# demora muito, já fazemos essa leitura em performance > sala de controle"). Medido nesse dia: a plataforma responde em
# 0,2 a 0,7 s, menos a SolarEdge na 1ª chamada (44 s, a lista de sites vem da fonte na hora); com a lista guardada e
# aquecida ao abrir o painel (`aquecer`), trocar de fonte não espera. Uma busca por fonte de cada vez: quem pede a mesma
# fonte no meio espera a que já está indo, não dispara outra. A recusa não fica guardada. O saldo da cota que vem junto
# envelhece com a lista: `anotar_cota` o corrige a cada pedido de verdade, e o `simular` traz o número da hora.
#
# A lista NUNCA faz a pessoa esperar se já foi lida uma vez (Levi, na mesma tarde: "está demorando muito para aparecer a
# lista de usinas, lamentável"). Medido às 15:06: a plataforma levou 37,6 s na lista da API PV e na da Chuva (ela guarda
# a lista de plantas só 5 min e a API PV estava lenta), e os 10 min daqui se perdiam a cada publicação do Nexus (5 em
# 40 min nessa tarde). Agora a última lista boa de cada fonte dorme em disco (`guardar_em`, a pasta de dados do Nexus) e
# sai NA HORA, mesmo passados os 10 min ou depois de um reinício; a renovação corre em fundo e a resposta vem marcada
# `renovando`, para a tela perguntar de novo e trocar a lista se ela mudou. A lista velha não mostra saldo de cota (o
# número seria de outra hora). Só espera a plataforma quem nunca leu a fonte, ou a leu há mais de 7 dias.
VALE_PLANTAS_S = 600
VELHA_DEMAIS_S = 7 * 86400
TENTAR_DE_NOVO_S = 30                          # a renovação em fundo que falhou não se repete a cada clique
_PLANTAS = {}                                  # fonte -> (quando, resposta)
_TRAVAS = {f: threading.Lock() for f, _n in FONTES}
_TENTOU = {}                                   # fonte -> quando a última renovação em fundo começou
_PASTA = {"p": None}


def guardar_em(pasta):
    """Onde a última lista de cada fonte dorme entre um reinício e outro (quem diz é a rota; None = só na memória)."""
    _PASTA["p"] = pasta or None


def _arquivo(fonte):
    return os.path.join(_PASTA["p"], "plantas_%s.json" % fonte) if _PASTA["p"] else None


def _do_disco(fonte):
    try:
        with open(_arquivo(fonte), encoding="utf-8") as f:
            d = json.load(f)
        quando, r = float(d["quando"]), d["resposta"]
    except Exception:                          # noqa: BLE001 — sem arquivo, ou arquivo ruim: é como nunca ter lido
        return None
    if not isinstance(r, dict) or not r.get("plantas") or not 0 <= time.time() - quando <= VELHA_DEMAIS_S:
        return None
    return quando, r


def _buscar(fonte, chave):
    r = _recoleta._pedir(_rota(fonte, True), chave)
    r = r if isinstance(r, dict) else {"plantas": r or []}
    agora = time.time()
    _PLANTAS[fonte] = (agora, r)
    a = _arquivo(fonte)
    if a and r.get("plantas"):                 # a lista vazia não cobre a boa que está em disco
        try:
            os.makedirs(os.path.dirname(a), exist_ok=True)
            with open(a + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"quando": agora, "resposta": r}, f, ensure_ascii=False)
            os.replace(a + ".tmp", a)
        except OSError:
            traceback.print_exc()
    return r


def _renovar(fonte, chave):
    """Renova a lista em fundo, uma por fonte de cada vez. Falhou, a que estava fica (e a tela segue com ela)."""
    agora = time.time()
    if agora - _TENTOU.get(fonte, 0) < TENTAR_DE_NOVO_S:
        return
    _TENTOU[fonte] = agora

    def vai():
        if not _TRAVAS[fonte].acquire(blocking=False):
            return
        try:
            g = _PLANTAS.get(fonte)
            if not (g and time.time() - g[0] < VALE_PLANTAS_S):
                _buscar(fonte, chave)
        except Exception:                      # noqa: BLE001 — a recusa aparece no simular e no pedido de verdade
            pass
        finally:
            _TRAVAS[fonte].release()
    threading.Thread(target=vai, daemon=True, name="nexus-recoleta-" + fonte).start()


def plantas(fonte, chave):
    _rota(fonte, True)                         # recusa a fonte desconhecida antes de qualquer coisa
    g = _PLANTAS.get(fonte)
    if g is None:
        g = _do_disco(fonte)
        if g:
            g = _PLANTAS.setdefault(fonte, g)
    if g and time.time() - g[0] < VALE_PLANTAS_S:
        return g[1]
    if g:                                      # passou dos 10 min: sai a que temos, sem o saldo velho, e renova em fundo
        _renovar(fonte, chave)
        return dict(g[1], cota_restante=None, renovando=True)
    with _TRAVAS[fonte]:
        g = _PLANTAS.get(fonte)
        if g and time.time() - g[0] < VALE_PLANTAS_S:
            return g[1]
        return _buscar(fonte, chave)


def anotar_cota(fonte, resta):
    g = _PLANTAS.get(fonte)
    if g and resta is not None:
        g[1]["cota_restante"] = resta


def aquecer(chave):
    """Ao abrir o painel: busca em fundo a lista de cada fonte que ainda não está guardada. Não espera nem levanta."""
    def vai(fonte):
        try:
            plantas(fonte, chave)
        except Exception:                      # noqa: BLE001 — aquecer é extra: a tela pede de novo e mostra o motivo
            pass
    if not chave:
        return
    for fonte, _nome in FONTES:
        g = _PLANTAS.get(fonte)
        if not (g and time.time() - g[0] < VALE_PLANTAS_S):
            threading.Thread(target=vai, args=(fonte,), daemon=True, name="nexus-recoleta-" + fonte).start()


def por_usina(lista):
    """{aba do BD: {"destino", "ids": [...]}} das plantas da fonte: a usina da tela é a aba, com todos os ids dela."""
    out = {}
    for p in lista or []:
        usina, destino = str(p.get("usina") or "").strip(), str(p.get("destino") or "").strip()
        if not usina or not destino or p.get("id") in (None, ""):
            continue
        u = out.setdefault(usina, {"destino": destino, "ids": []})
        if str(p["id"]) not in u["ids"]:
            u["ids"].append(str(p["id"]))
    return out


def plano(ids, ini, fim, max_plantas, max_dias):
    """Os pedidos de uma recoleta: [(ids do pedido, ini, fim)], cada um dentro dos tetos da fonte."""
    n_p, n_d = max(1, int(max_plantas or 8)), max(1, int(max_dias or 7))
    blocos = [ids[i:i + n_p] for i in range(0, len(ids), n_p)]
    return [(b, a, z) for a, z in _recoleta.fatias(ini, fim, n_d) for b in blocos]


def pedir(fonte, chave, ids, ini, fim, geracao, etm, chuva, simular=False):
    corpo = {"ids": list(ids), "ini": ini.isoformat(), "fim": fim.isoformat(), "geracao": bool(geracao), "etm": bool(etm),
             "chuva": bool(chuva), "simular": bool(simular)}
    return _recoleta._pedir(_rota(fonte), chave, corpo, timeout=300)


def _dia(txt):
    try:
        return dt.date.fromisoformat(str(txt)[:10])
    except ValueError:
        return None


def celulas(respostas, usina, destino):
    """As respostas da plataforma viram células do BD. -> (células, [(nível, texto)]). Só entra o que é da aba pedida (a
    planta que alimenta duas abas devolve as duas). A chuva só preenche a célula vazia (regra da coleta); o dia que a
    fonte marcou como fora do ar ENTRA com aviso severo, e a pessoa decide (a Crateus tem 40 de 50 inversores parados de
    verdade e cairia nisso todo dia)."""
    cel, avisos, visto = [], [], set()
    for r in respostas:
        for g in r.get("geracao") or []:
            d = _dia(g.get("data"))
            if g.get("usina") != usina or d is None or g.get("kwh") is None or not g.get("inversor"):
                continue
            k = ("g", g["inversor"], d)
            if k not in visto:
                visto.add(k)
                cel.append(Celula(destino, usina, d, str(g["inversor"]), float(g["kwh"])))
        for e in r.get("escalares") or []:
            d = _dia(e.get("data"))
            if e.get("usina") != usina or d is None or e.get("valor") is None or not e.get("coluna"):
                continue
            k = ("e", e["coluna"], d)
            if k not in visto:
                visto.add(k)
                chuva = "chuva" in str(e["coluna"]).lower()
                cel.append(Celula(destino, usina, d, str(e["coluna"]), float(e["valor"]), None, chuva))
        for t in r.get("avisos") or []:
            item = ("severo" if "fora do ar" in str(t) else "leve", str(t))
            if item not in avisos:
                avisos.append(item)
    return cel, avisos
