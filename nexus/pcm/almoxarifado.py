"""A tela PCM → Almoxarifado (25/10/2026). Levi: "No fractall temos almoxarifado, gostaria de uma visão para a gestão
desse almoxarifado na parte de PCM"; a prévia foi aprovada no mesmo dia. Desenho:
docs/superpowers/specs/2026-10-25-almoxarifado-design.md.

A pergunta: que peça está abaixo do mínimo ou no limite, em que almoxarifado, e o que saiu nas OS? O dado é o que o App
de Campo publica da varredura diária do inventário do Fracttal (os livros e as contas em `nexus/dados/almoxarifado.py`,
as MESMAS da carga do histórico); o Nexus não chama o Fracttal.

De onde vem cada parte:
- o saldo, do ciclo mais novo dos livros do App quando os três (Ciclo, Itens, Saldo) são do mesmo ciclo e o ciclo leu
  90% da lista; senão, do último ciclo aplicado no histórico do Nexus (`nexus_almoxarifado`), com o aviso. Sem ciclo
  aplicado no Nexus (o ensaio, antes da NEXUS_ALMOX_GRAVAR), o aviso e nenhum número: número pela metade não vai à tela;
- o almoxarifado de TESTE (NEXUS_ALMOX_TESTE_IDS, 26/10/2026: a prova das gravações do inventário no Fracttal) não entra
  em nada daqui: as linhas dele saem do Saldo DEPOIS de os três livros serem conferidos como inteiros (o ciclo conta as
  do teste nas "Linhas de saldo"), senão todo ciclo com o teste viraria "chegou pela metade";
- o consumo, do `fato_peca_lancada` do Nexus (tudo desde o início, Levi, 25/10/2026); enquanto ele não existe, do livro
  Peças do App (90 dias), com a nota.
"""
from datetime import timedelta, timezone

from flask import current_app, render_template

from ..campo import visao
from ..dados import almoxarifado as A
from ..dados import fato_almoxarifado as F
from ..dados import livros
from ..dados.dominios import norm

TELA = "pecas"
_RECUSA = "recusada"


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _num(v) -> float:
    return A.numero(v) or 0.0


def _id(v) -> str:
    """O ID como texto, sem o ".0" que a API às vezes põe ("7.0" é o 7)."""
    t = _txt(v)
    return t[:-2] if t.endswith(".0") else t


def _abas(livro) -> dict:
    return visao._ciclo(("_abas", livro), lambda: livros.abas(visao._base(), visao._sessao(), livro))


def _quando(iso) -> str:
    d = visao._dt(iso)
    return d.astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m, %H:%M") if d else "?"


def _dia(data_id) -> str:
    t = _id(data_id)
    return f"{t[6:8]}/{t[4:6]}/{t[:4]}" if len(t) == 8 else ""


# ── as duas fontes do saldo, no mesmo formato ─────────────────────────────────────────────────────────────────────────

def _do_app(ciclo: dict, itens: list[dict], saldo: list[dict], b) -> dict:
    its = {_id(i.get("ID do item")): {"codigo": _txt(i.get("Código")), "nome": _txt(i.get("Nome")),
                                       "unidade": _txt(i.get("Unidade")), "familia": _txt(i.get("Família")),
                                       "avariado": _txt(i.get("Avariado")).lower() == "sim",
                                       "nao_lido": _txt(i.get("Lido")).lower() == "não"} for i in itens}
    linhas = [{"id_item": _id(s.get("ID do item")), "id_almox": _id(s.get("ID do almoxarifado")),
               "almox": _txt(s.get("Almoxarifado")), "usina_id": b.lig.usina_do_fracttal(
                   A.chave_do_local(s.get("Local do almoxarifado")) or ""),
               "saldo": A.numero(s.get("Saldo")), "minimo": A.numero(s.get("Mínimo"))} for s in saldo]
    return {"inicio": _txt(ciclo.get(A.INICIO)), "fim": _txt(ciclo.get("Fim do ciclo")),
            "lidos": ciclo.get("Itens lidos"), "total": ciclo.get("Itens na lista do Fracttal"), "itens": its,
            "linhas": linhas}


def _do_nexus(ult: dict, abas_nx: dict, teste: frozenset | set = frozenset()) -> dict | None:
    """O último ciclo aplicado no histórico: a foto dele no livro do mês e as dimensões do Nexus. `teste`: os
    almoxarifados de teste (a carga não grava mais as linhas deles, mas o ID pode ser posto depois de uma já gravada)."""
    mes = F.livro_do_mes(int(float(_id(ult.get("data_id")))))
    if F.ABA_SALDO not in _abas(mes):
        return None
    inicio = _txt(ult.get("ciclo_inicio"))
    foto = [l for l in visao._livro(mes, F.ABA_SALDO)
            if _txt(l.get("ciclo_inicio")) == inicio and _id(l.get("id_almoxarifado")) not in teste]
    almox = {_id(a.get("id_almoxarifado")): _txt(a.get("nome"))
             for a in (visao._livro(F.LIVRO, F.ABA_DIM_ALMOX) if F.ABA_DIM_ALMOX in abas_nx else [])}
    # só os itens que estão na foto (a revisão de 25/10/2026): a dimensão guarda todo item já visto, inclusive os
    # desativados há meses, e o item não lido no ciclo apareceria como "sem saldo em nenhum almoxarifado"
    na_foto = {_id(l.get("id_item")) for l in foto}
    its = {_id(i.get("id_item")): {"codigo": _txt(i.get("codigo")), "nome": _txt(i.get("nome")),
                                    "unidade": _txt(i.get("unidade")), "familia": _txt(i.get("familia")),
                                    "avariado": _txt(i.get("avariado")) in ("1", "1.0"), "nao_lido": False}
           for i in (visao._livro(F.LIVRO, F.ABA_DIM_ITEM) if F.ABA_DIM_ITEM in abas_nx else [])
           if _id(i.get("id_item")) in na_foto}
    linhas = [{"id_item": _id(l.get("id_item")), "id_almox": _id(l.get("id_almoxarifado")),
               "almox": almox.get(_id(l.get("id_almoxarifado")), _id(l.get("id_almoxarifado"))),
               "usina_id": int(float(_id(l.get("usina_id")))) if _id(l.get("usina_id")) else None,
               "saldo": A.numero(l.get("saldo_qtd")), "minimo": A.numero(l.get("minimo_qtd"))} for l in foto]
    return {"inicio": inicio, "fim": _txt(ult.get("fim")), "lidos": ult.get("itens_lidos_qtd"),
            "total": ult.get("itens_lista_qtd"), "itens": its, "linhas": linhas}


# ── as partes da tela ────────────────────────────────────────────────────────────────────────────────────────────────

def _usina(b, uid) -> str | None:
    u = b.por_id.get(uid) if uid else None
    return _txt(u.get("nome")) if u else None


def _partes(fonte: dict, b) -> dict:
    its, out = fonte["itens"], []
    for l in fonte["linhas"]:
        i = its.get(l["id_item"], {})
        sit = A.situacao(l["saldo"], l["minimo"])
        # saldo vazio (o Fracttal não deu o número) é "não informado": fora da Reposição e das contas (a revisão de
        # 25/10/2026: virava "abaixo, falta 2" e uma "zerada" no cartão)
        cod, nome = i.get("codigo") or l["id_item"], i.get("nome", "")
        out.append(dict(l, codigo=cod, nome=nome, familia=i.get("familia", ""), unidade=(i.get("unidade") or "").lower(),
                        avariado=i.get("avariado", False), situacao=sit, usina=_usina(b, l["usina_id"]),
                        falta=max((l["minimo"] or 0) - l["saldo"], 0) if l["saldo"] is not None else 0,
                        busca=norm(f"{cod} {nome}")))
    abaixo = sorted((x for x in out if x["situacao"] == "abaixo"), key=lambda x: -x["falta"])
    limite = sorted((x for x in out if x["situacao"] == "no_limite"), key=lambda x: (x["almox"], x["codigo"]))
    for x in abaixo + limite:
        x["pct"] = min(100, round(100 * x["saldo"] / x["minimo"])) if x["minimo"] else 0
    cards = {}
    for x in out:
        c = cards.setdefault(x["id_almox"], {"id": x["id_almox"], "nome": x["almox"], "usina": x["usina"], "pecas": 0,
                                             "abaixo": 0, "no_limite": 0, "sem_minimo": 0, "zeradas": 0, "ok": 0,
                                             "nao_informado": 0})
        c["pecas"] += 1
        c["abaixo"] += x["situacao"] == "abaixo"
        c["no_limite"] += x["situacao"] == "no_limite"
        c["sem_minimo"] += not (x["minimo"] and x["minimo"] > 0)
        c["zeradas"] += x["saldo"] == 0
        c["ok"] += x["situacao"] == "ok"
        c["nao_informado"] += x["situacao"] == "nao_informado"
    for c in cards.values():
        c["pct_ok"] = round(100 * c["ok"] / c["pecas"]) if c["pecas"] else 0
    catalogo = []
    for iid, i in its.items():
        onde = [x for x in out if x["id_item"] == iid and (x["saldo"] or 0) > 0]
        catalogo.append(dict(i, id=iid, total=sum(x["saldo"] for x in onde), almoxes=[x["almox"] for x in onde],
                             onde=[f"{x['almox']}: {x['saldo']:g}" for x in onde],
                             busca=norm(f"{i.get('codigo', '')} {i.get('nome', '')}")))
    catalogo.sort(key=lambda c: (c["familia"], c["codigo"]))
    sem_min = {}
    for x in out:
        if not (x["minimo"] and x["minimo"] > 0) and x["situacao"] != "nao_informado":
            sem_min[x["almox"]] = sem_min.get(x["almox"], 0) + 1
    kpis = {"almoxarifados": len(cards), "com_saldo": len({x["id_item"] for x in out if (x["saldo"] or 0) > 0}),
            "abaixo": len(abaixo), "no_limite": len(limite), "sem_minimo": sum(sem_min.values()),
            "avariadas": sum(1 for i in its.values() if i.get("avariado"))}
    return {"kpis": kpis, "reposicao": abaixo + limite, "linhas": out,
            "por_almoxarifado": sorted(cards.values(), key=lambda c: c["nome"]), "catalogo": catalogo,
            "cadastro": {"sem_minimo": [{"almoxarifado": a, "n": n} for a, n in sorted(sem_min.items())],
                         "avariadas": [x for x in out if x["avariado"] and (x["saldo"] or 0) > 0]}}


def _consumo(pecas_nx: list[dict] | None, pecas_app: list[dict], fonte: dict) -> tuple[list[dict], str]:
    its = fonte["itens"] if fonte else {}
    nomes = {l["id_almox"]: l["almox"] for l in (fonte or {}).get("linhas", [])}
    out = []
    if pecas_nx is not None:
        for p in pecas_nx:
            lancada = _id(p.get("lancada")) == "1"
            out.append({"data_id": _id(p.get("data_id")), "os": _txt(p.get("os")), "id_item": _id(p.get("id_item")),
                        "codigo": _txt(p.get("codigo")), "quantidade": _num(p.get("quantidade_qtd")),
                        "id_almox": _id(p.get("id_almoxarifado")),
                        "situacao": "lançada" if lancada else _RECUSA, "recusa": _txt(p.get("recusa"))})
        origem = "nexus"
    else:
        for p in pecas_app:
            iso = _txt(p.get("Usada em")) or _txt(p.get("Recebido em"))
            d = visao._dt(iso)
            out.append({"data_id": d.astimezone(timezone(timedelta(hours=-3))).strftime("%Y%m%d") if d else "",
                        "os": _txt(p.get("OS")), "id_item": _id(p.get("ID do item")), "codigo": _txt(p.get("Código")),
                        "quantidade": _num(p.get("Quantidade")), "id_almox": _id(p.get("ID do almoxarifado")),
                        "situacao": "lançada" if _txt(p.get("Situação")).lower() == "lançada" else _RECUSA,
                        "recusa": _txt(p.get("Motivo da recusa")) or ("outro" if _txt(p.get("Situação")).lower()
                                                                       != "lançada" else "")})
        origem = "app"
    for c in out:
        i = its.get(c["id_item"], {})
        c.update(nome=i.get("nome", ""), familia=i.get("familia", ""), almox=nomes.get(c["id_almox"], c["id_almox"]),
                 dia=_dia(c["data_id"]), busca=norm(f"{c['codigo']} {i.get('nome', '')} {c['os']}"))
    out.sort(key=lambda c: (c["data_id"], c["os"]))
    return out, origem


def montar():
    """Tudo o que a tela mostra (cópia de 5 min e renovada por trás, como as telas do Campo)."""
    def calcular():
        abas_app = {l: _abas(l) for l in (A.LIVRO_CICLO, A.LIVRO_ITENS, A.LIVRO_SALDO, A.LIVRO_PECAS)}
        if not all(abas_app[l] for l in (A.LIVRO_CICLO, A.LIVRO_ITENS, A.LIVRO_SALDO)):
            return {"estado": "sem_livro"}
        ciclo, itens = visao._livro(A.LIVRO_CICLO, A.ABA_CICLO), visao._livro(A.LIVRO_ITENS, A.ABA_ITENS)
        saldo = visao._livro(A.LIVRO_SALDO, A.ABA_SALDO)
        pecas_app = visao._livro(A.LIVRO_PECAS, A.ABA_PECAS) if abas_app[A.LIVRO_PECAS] else []
        abas_nx = _abas(F.LIVRO)
        b, aviso = visao._Base(), ""
        ciclos = visao._livro(F.LIVRO, F.ABA_CICLO) if F.ABA_CICLO in abas_nx else []
        anulados = {_txt(c.get("ciclo_inicio")) for c in ciclos if _id(c.get("anulado")) == "1"}
        bons = [c for c in ciclos if _txt(c.get("situacao")) == "aplicado" and _id(c.get("anulado")) != "1"]
        inicio = A.ciclo_comum(ciclo, itens, saldo)
        # por que o ciclo do App não serve (a revisão de 25/10/2026: os livros que chegaram pela metade e o ciclo
        # anulado no Nexus também vão para a reserva)
        porque = ("Os livros do App chegaram de ciclos diferentes" if not inicio
                  else f"Os livros do App chegaram pela metade ({A.conferir_ciclo(ciclo, itens, saldo)})"
                  if A.conferir_ciclo(ciclo, itens, saldo)
                  else "O último ciclo do App leu menos de 90% dos itens" if not A.completo(ciclo[0])
                  else f"O ciclo de {_quando(inicio)} foi anulado no Nexus" if inicio in anulados else "")
        cfg = current_app.config
        if not porque:
            # o teste sai AGORA, depois de `conferir_ciclo` (que conta as linhas do livro inteiro)
            fonte = _do_app(ciclo[0], itens, A.sem_almoxarifado_de_teste(saldo, cfg), b)
            antes = [c for c in bons if _txt(c.get("ciclo_inicio")) != inicio]
            n_antes = A.numero(max(antes, key=lambda c: _txt(c.get("ciclo_inicio"))).get("itens_lista_qtd")) if antes \
                else None
            n_agora = A.numero(fonte["total"])
            if n_antes and n_agora is not None and n_agora < A.COMPLETUDE_MIN * n_antes:
                aviso = (f"O Fracttal listou {n_agora:g} itens, {n_antes - n_agora:g} a menos que no ciclo anterior: "
                         "confira se o catálogo foi limpo.")
        else:
            fonte = _do_nexus(max(bons, key=lambda c: _txt(c.get("ciclo_inicio"))), abas_nx,
                              A.ids_de_teste(cfg)) if bons else None
            if not fonte:
                return {"estado": "incoerente",
                        "aviso": f"{porque}, e o Nexus ainda não guardou um ciclo bom: nenhum número até o próximo."}
            aviso = f"{porque}: mostrando o saldo de {_quando(fonte['inicio'])}."
        fim = visao._dt(fonte["fim"] or fonte["inicio"])
        if fim and visao._agora() - fim > timedelta(hours=A.CICLO_VELHO_H):
            aviso = (aviso + " " if aviso else "") + (f"Saldo de {_quando(fonte['fim'] or fonte['inicio'])}: a "
                                                       "varredura do App não publicou desde então.")
        d = _partes(fonte, b)
        pecas_nx = visao._livro(F.LIVRO, F.ABA_PECA) if F.ABA_PECA in abas_nx else None
        d["consumo"], d["consumo_fonte"] = _consumo(pecas_nx, pecas_app, fonte)
        d["kpis"]["lancadas"] = sum(1 for c in d["consumo"] if c["situacao"] == "lançada")
        d["kpis"]["recusadas"] = sum(1 for c in d["consumo"] if c["situacao"] == _RECUSA)
        d["cadastro"]["recusadas"] = [c for c in d["consumo"] if c["situacao"] == _RECUSA]
        n = (lambda v: f"{A.numero(v):g}" if A.numero(v) is not None else "?")        # "574.0" da API vira "574"
        d.update(estado="ok", aviso=aviso, ciclo={"fim": _quando(fonte["fim"] or fonte["inicio"]),
                                                  "lidos": n(fonte["lidos"]), "total": n(fonte["total"])},
                 almoxarifados=sorted({x["almox"] for x in d["linhas"]}),
                 familias=sorted({i["familia"] for i in fonte["itens"].values() if i["familia"]}))
        return d
    return visao._ler(("pcm_almoxarifado",), calcular)


def registrar(bp) -> None:
    @bp.route(f"/{TELA}", endpoint=TELA)
    def tela():
        g = montar()
        return render_template("pcm/almoxarifado.html", d=g.dados or {}, erro=g.erro)

