"""O que mudou nos atrasados (Segurança · HSEQ, 25/11/2026, a entrega 3 do mockup de Extintores aprovado pela
Segurança): "São pendências novas, ou as antigas mais as novas?".

A pessoa escolhe a data de início (7 dias atrás por padrão); o fim é hoje. Com os filtros da tela:
- **atrasados no início → atrasados hoje**;
- **continuam atrasados (antigos)**: estavam no início e ainda estão;
- **venceram depois (novos)**: estão hoje e não estavam no início;
- **resolvidos**: estavam no início e não estão mais;
- **atrasados por dia**: as barras de cada dia, os antigos (os do início) embaixo e os novos do período em cima.

De onde vem cada dia (`conjunto`):
- **hoje**: a tela de agora (a lista de extintores com as decisões da Segurança), a mesma conta da faixa de números;
- **dia com foto**: a foto diária (`extintores_historico`, a completa mais perto antes + as mudanças até o dia);
- **dia sem foto depois da 1ª foto**: lacuna (a API fora o dia inteiro). A barra não se desenha; o início que cai numa
  lacuna usa a última foto antes dele, e a tela diz;
- **antes da 1ª foto: estimado**. Pela validade de HOJE: o extintor estava atrasado na data X se a recarga ou o
  hidrostático dele venceu antes de X. A estimativa não sabe o que foi resolvido (o extintor recarregado depois tem a
  validade nova), então os resolvidos ficam "—" e o número e a barra dizem "estimado".
Os filtros da tela (cliente, usina, Responsável UFV, equipe, busca) valem também nos dias de foto: o código da foto
liga ao extintor de hoje; o que saiu da tela (excluído) liga pela usina dele.
"""
from datetime import date, timedelta

from . import extintores_historico as H

DIAS_PADRAO = 7
DIAS_MAX = 90                  # até quanto para trás a data de início vai (as barras de 90 dias ainda se leem)


def atrasado_em(x: dict, dia: date) -> bool:
    """A estimativa: a recarga ou o hidrostático (a validade de hoje) venceu antes do `dia`."""
    return any(f and f < dia for f in (x.get("fim2"), x.get("fim3")))


def comparar(cru: dict, atuais: list, hoje: date, de: date, passa, por_usina: dict) -> dict:
    """A conta da seção. `cru`, o livro da foto diária; `atuais`, os extintores da tela de agora (com as decisões, SEM
    os filtros); `passa(x)`, os filtros da tela; `por_usina`, {usina_id: um extintor de hoje dessa usina}, para filtrar o
    código da foto que não está mais na tela. Devolve os números, as listas e as barras."""
    de = max(min(de, hoje), hoje - timedelta(days=DIAS_MAX))
    por_cod = {x["codigo"]: x for x in atuais}
    gravados = H.dias_gravados(cru)
    primeira = min(gravados) if gravados else None

    def filtra(cod, uid):
        x = por_cod.get(cod) or por_usina.get(H._int(uid))
        return bool(x) and passa(dict(x, codigo=cod))

    def conjunto(dia):
        """(códigos atrasados no fim do dia, como): real, foto, estimado ou lacuna (None)."""
        if dia == hoje:
            return {x["codigo"] for x in atuais if x["situacao"] == "atrasado" and passa(x)}, "real"
        if primeira and dia >= primeira:
            if dia not in gravados:
                return None, "lacuna"
            est = H.estado_em(cru, dia) or {}
            return {c for c, r in est.items() if r.get("situacao") == "atrasado" and filtra(c, r.get("usina_id"))}, "foto"
        return {x["codigo"] for x in atuais if atrasado_em(x, dia) and passa(x)}, "estimado"

    inicio, como = conjunto(de)
    de_usado = de
    if inicio is None:                                  # o início caiu numa lacuna: a última foto antes dele
        antes = max((d for d in gravados if d < de), default=None)
        de_usado = antes or de
        inicio, como = conjunto(antes) if antes else ({x["codigo"] for x in atuais if atrasado_em(x, de) and passa(x)},
                                                      "estimado")
    agora, _ = conjunto(hoje)
    antigos, novos = inicio & agora, agora - inicio
    barras = []
    d = de
    while d <= hoje:
        s, c = conjunto(d)
        barras.append({"dia": d, "como": c, "antigos": len(s & inicio) if s is not None else None,
                       "novos": len(s - inicio) if s is not None else None})
        d += timedelta(days=1)

    def lista(cods):
        return sorted((por_cod[c] for c in cods if c in por_cod), key=lambda x: (x.get("vence") or date.max, x["usina"],
                                                                               x["codigo"]))
    return {"de": de, "de_usado": de_usado, "hoje": hoje, "como_inicio": como, "estimado": como == "estimado",
            "primeira_foto": primeira, "n_inicio": len(inicio), "n_hoje": len(agora),
            "antigos": lista(antigos), "novos": lista(novos),
            "resolvidos": None if como == "estimado" else len(inicio - agora), "barras": barras}


def grafico(barras: list, largura: int = 420, altura: int = 220) -> dict:
    """As medidas do SVG das barras empilhadas (desenhado no template, as cores pelas classes do `hseq.css`): o eixo, as
    marcas e cada barra com x, a largura e as alturas dos antigos e dos novos. A lacuna fica sem barra."""
    esq, base, topo = 32, altura - 28, 14
    n = max(1, len(barras))
    passo = (largura - esq - 6) / n
    larg = max(3.0, min(34.0, passo * 0.7))
    maior = max([(b["antigos"] or 0) + (b["novos"] or 0) for b in barras] + [1])
    # a escala em números redondos, 4 faixas: o menor passo de 1, 2, 5, 10, 20, 50... que cabe o maior dia
    tam, mult = 1, 1
    while tam * 4 < maior:
        for m in (1, 2, 5):
            if m * mult * 4 >= maior:
                tam = m * mult
                break
        else:
            mult *= 10
            continue
        break
    alto = tam * 4
    k = (base - topo) / alto
    rotulo_cada = max(1, -(-n // 12))                   # no máximo 12 datas no eixo
    out = []
    for i, b in enumerate(barras):
        x = esq + passo * i + (passo - larg) / 2
        a = (b["antigos"] or 0) * k
        nv = (b["novos"] or 0) * k
        out.append(dict(b, x=round(x, 1), w=round(larg, 1), ya=round(base - a, 1), ha=round(a, 1),
                        yn=round(base - a - nv, 1), hn=round(nv, 1), meio=round(x + larg / 2, 1),
                        total=None if b["antigos"] is None else b["antigos"] + b["novos"],
                        rotulo=(i % rotulo_cada == 0 or i == n - 1)))
    marcas = [{"v": tam * j, "y": round(base - tam * j * k, 1)} for j in range(5)]
    return {"largura": largura, "altura": altura, "esq": esq, "base": base, "barras": out, "marcas": marcas,
            "com_total": n <= 15}
