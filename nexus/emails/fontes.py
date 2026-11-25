"""O que um e-mail do Nexus pode trazer (25/11/2026): as FONTES que o modelo escolhe na tela (Base › E-mails automáticos ›
Novo e-mail). Nenhum número novo e nenhuma régua nova: cada fonte reorganiza uma conta que o Nexus já faz.

A primeira é a das pendências das usinas (Levi, 25/11/2026: "eu queria algo focado em pendências das usinas [...] precisa
passar por mim antes"): o Painel do responsável (`campo/painel_responsavel.montar`, a conta guardada de 5 min da Visão do
responsável) em e-mail, só o que pede ação. O modelo que a usa nasce desligado e só liga depois da prévia aprovada.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import modelo as M

LINHAS_MAX = 12


@dataclass
class Fonte:
    id: str
    nome: str
    descricao: str
    por_usina: bool                     # precisa das usinas do destinatário (o e-mail "um por Responsável UFV")
    render: Callable                    # (usinas: [linha da Visão], link: str) -> (html, tem_algo: bool)


def usinas_da_visao(cfg) -> list[dict]:
    """As usinas mobilizadas como a Visão do responsável as calcula (a cópia de 5 min), com o bloco Manutenção no limite
    padrão do PCM. Precisa de um app_context."""
    from ..campo import manutencao
    from ..campo import responsaveis as R
    d = R.visao_responsaveis().dados or {}
    return R.com_manutencao(d.get("usinas") or [], manutencao.LIMITE_PADRAO)


def _mais(n: int, link: str) -> str:
    if n <= 0:
        return ""
    return (f'<p style="margin:6px 0 0;font-size:12.5px;color:{M.COR["mudo"]};font-family:{M.FONTE}">e mais {n} no '
            f'Nexus: <a href="{M.h(link)}" style="color:{M.COR["tinta"]}">abrir o Painel</a></p>')


def _num(rotulo: str, valor, ruim: bool) -> str:
    cor = M.COR["critico"] if ruim else M.COR["tinta"]
    return (f'<td style="padding:10px 12px;border:1px solid {M.COR["linha"]};font-family:{M.FONTE}">'
            f'<div style="font-size:11px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;color:{M.COR["mudo"]}">'
            f'{M.h(rotulo)}</div><div style="font-size:22px;font-weight:700;color:{cor}">{M.h(valor)}</div></td>')


def _espera(minutos) -> str:
    if minutos is None:
        return "—"
    if minutos < 60:
        return f"{minutos} min"
    if minutos < 48 * 60:
        return f"{minutos // 60} h"
    return f"{minutos // 1440} dias"


def pendencias(usinas: list[dict], link: str) -> tuple[str, bool]:
    """As pendências das usinas, a que mais pede em cima: os números do alto e, embaixo, só as seções com algo. Sem
    pendência nenhuma, (texto curto, False): o modelo decide se manda assim mesmo."""
    from ..campo import painel_responsavel as P
    p = P.montar("", usinas)
    pts, pend, cham, ron, ext, perf = p["pts"], p["pendencias"], p["chamados"], p["rondas"], p["extintores"], p["perf"]
    tem = bool(pts["aguardando"] or pend["os"] or cham["abertos"] or ron["sem_7"] or ext["vencidos"] or perf["criticas"])
    if not tem:
        return M.paragrafo(f"Nenhuma pendência nas {len(usinas)} usinas hoje."), False
    nums = (_num("PT esperando", pts["aguardando"], bool(pts["paradas"])) + _num("OS pendentes", pend["os"], bool(pend["os"]))
            + _num("Chamados abertos", cham["abertos"], False) + _num("Sem ronda 7 dias", ron["sem_7"], bool(ron["sem_7"])))
    h = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;'
         f'margin:0 0 6px"><tr>{nums}</tr></table>')
    if pts["linhas"]:
        h += M.titulo_secao(f"PT esperando o De acordo ({pts['aguardando']}; {pts['paradas']} há mais de 2 h)")
        ls = pts["linhas"][:LINHAS_MAX]
        h += M.tabela(["Usina", "OS", "Esperando há"], [[x["usina"], x.get("os") or "—", _espera(x.get("idade_min"))]
                                                        for x in ls],
                      {i for i, x in enumerate(ls) if x.get("parada")})
        h += _mais(len(pts["linhas"]) - len(ls), link)
    if pend["grupos"]:
        h += M.titulo_secao(f"OS pendentes ({pend['os']}: {pend['atrasadas']} atrasada(s), {pend['pausadas']} pausada(s))")
        linhas, destaque = [], set()
        for g in pend["grupos"]:
            for i in g["itens"]:
                if len(linhas) >= LINHAS_MAX:
                    break
                if i["situacao"] == "Atrasada":
                    destaque.add(len(linhas))
                linhas.append([g["usina"], f"OS {i['os']}", i["situacao"], i["motivo"]])
        h += M.tabela(["Usina", "OS", "Situação", "Motivo"], linhas, destaque)
        h += _mais(sum(len(g["itens"]) for g in pend["grupos"]) - len(linhas), link)
    sem = [x for x in ron["linhas"] if x["situacao"] in ("nunca", "sem_ronda")]
    if sem:
        h += M.titulo_secao(f"Usinas sem ronda há 7 dias ou mais ({len(sem)})")
        ls = sem[:LINHAS_MAX]
        h += M.tabela(["Usina", "Última ronda"], [[x["usina"], (f"há {x['dias']} dias" if x["dias"] is not None
                                                                 else "nunca teve ronda pelo App")] for x in ls])
        h += _mais(len(sem) - len(ls), link)
    if cham["grupos"]:
        h += M.titulo_secao(f"Chamados de garantia abertos ({cham['abertos']})")
        linhas = []
        for g in cham["grupos"]:
            for i in g["itens"]:
                if len(linhas) < LINHAS_MAX:
                    linhas.append([g["usina"], i["ativo"], i["status"] or "—",
                                   f"{i['dias']} dias" if i["dias"] is not None else "—"])
        h += M.tabela(["Usina", "Ativo", "Status", "Aberto há"], linhas)
        h += _mais(cham["abertos"] - len(linhas), link)
    if ext["linhas"]:
        h += M.titulo_secao(f"Extintores vencidos ({ext['vencidos']})")
        ls = ext["linhas"][:LINHAS_MAX]
        h += M.tabela(["Usina", "Vencidos", "A vencer"], [[x["usina"], x["vencidos"], x["a_vencer"]] for x in ls],
                      set(range(len(ls))))
        h += _mais(len(ext["linhas"]) - len(ls), link)
    crit = [x for x in perf["linhas"] if x["situacao"] == "critico"]
    if crit:
        h += M.titulo_secao(f"Usinas abaixo de 90% da meta do mês ({len(crit)})")
        ls = crit[:LINHAS_MAX]
        h += M.tabela(["Usina", "Meta do mês"], [[x["usina"], f"{x['atingimento']:.0f}%"] for x in ls],
                      set(range(len(ls))))
        h += _mais(len(crit) - len(ls), link)
    return h, True


FONTES = {
    "pendencias_usinas": Fonte(
        "pendencias_usinas", "Pendências das usinas",
        "o que pede ação nas usinas de quem recebe: PT esperando o De acordo, OS atrasadas e pausadas (com o motivo), "
        "usinas sem ronda há 7 dias ou mais, chamados de garantia abertos, extintores vencidos e usinas abaixo de 90% "
        "da meta do mês. É o Painel do responsável, em e-mail", True, pendencias),
}
