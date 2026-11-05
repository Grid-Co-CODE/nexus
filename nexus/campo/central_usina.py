"""A Central da usina (Levi, 04/11/2026: "Como temos uma visão para os supervisores em Central do Responsável podemos ter
como pesquisar a usina e ter uma central de informações daquela usina, performance, disponibilidade, sujidade,
pendências, chamados, PTs etc"; "inclua junto da central dos responsáveis, como aba alternativa"): a aba "Central da
usina" da Visão do responsável.

Nenhuma conta nova. A linha da usina é a MESMA da Visão (`responsaveis.montar`, com o bloco Manutenção no limite de
quem olha): a meta, o PR, a disponibilidade, a ronda, a limpeza, as PT esperando, os chamados abertos, os extintores e as
OS. O que a linha não traz vem da tela dona de cada coisa (Nexus centralizado, 12/10/2026): as ocorrências abertas
(Campo › Ocorrências), as pendências da Segurança (a Mesa do HSEQ), os técnicos da usina (PCM › Técnicos por usina,
a regra do App desde 29/10/2026) e os chamados finalizados no mês (o fato do quadro Acompanhamento de chamados). As PT
decididas no mês saíram com o quadro da PT (05/11/2026: o número da PT abre a lista do Painel).

Decisões do Levi (04/11/2026): o mês corrente na performance, na disponibilidade e no histórico de chamados;
nas pendências, as rondas, as OS atrasadas e pausadas, as ocorrências abertas e a Segurança; a busca com todas as usinas
mobilizadas, para quem abre a Visão (como a Visão, que deixa escolher qualquer responsável)."""
from . import ocorrencias as campo_oc
from . import visao

# a Segurança, na ordem da Mesa (o que pede ação primeiro), com o rótulo daqui
SEGURANCA = (("pts", "PT parada"), ("vencidos", "Extintor vencido"), ("nr", "Extintor não reconhecido"),
             ("sem_luvas", "Sem luvas"), ("perto", "Extintor a vencer"), ("sem_atual", "Extintor sem conferência"),
             ("luvas_semv", "Luvas sem verificação"), ("ronda", "Nova ronda de extintores pedida"))


def achar(usinas: list[dict], texto: str) -> int | None:
    """A usina pelo nome digitado (a busca sem o script), na regra do "Buscar por usina" das Rondas: o nome igual, sem
    acento nem caixa, ou o único que contém o que se digitou."""
    alvo = visao._norm_nome(texto or "")
    if not alvo:
        return None
    iguais = [u["usina_id"] for u in usinas if visao._norm_nome(u.get("usina") or "") == alvo]
    contem = [u["usina_id"] for u in usinas if alvo in visao._norm_nome(u.get("usina") or "")]
    return iguais[0] if iguais else (contem[0] if len(contem) == 1 else None)


def busca(usinas: list[dict], ordem) -> list[tuple]:
    """(usina_id, nome, "cliente · UF") de todas as usinas da Visão, na ordem do nome (`ordem`, a das Rondas)."""
    return sorted(((u["usina_id"], u["usina"], " · ".join(v for v in (u.get("cliente"), u.get("uf")) if v))
                   for u in usinas if u.get("usina_id") and u.get("usina")), key=lambda x: ordem(x[1]))


def linhas(u: dict, bloco: str, rotulos) -> list[dict]:
    """As linhas do detalhe de um bloco da Visão (`u[bloco]["det"]`) com estes rótulos, na ordem deles: a Central mostra
    a mesma linha (com os mesmos botões) que a Visão geral."""
    det = {i["rot"]: i for i in (u.get(bloco) or {}).get("det") or []}
    return [det[r] for r in rotulos if r in det]


def pessoas(uid: int, b, atribuicoes: dict | None) -> dict:
    """O Supervisor de Campo e o Gestor (a estrutura de O&M do cadastro, `_Base.onde`) e os técnicos que a tela Técnicos
    por usina do PCM põe nela hoje (`atribuicoes` = `pcm.atribuicoes.atuais`, só os que valem). Sem as atribuições
    (None), a lista fica vazia e a tela diz que não leu."""
    o = b.onde(uid)
    pids = sorted({pid for (u, pid, _papel), x in (atribuicoes or {}).items()
                   if u == uid and pid and x.get("status") == "vale"})
    nomes = b.nomes(pids) if pids else {}
    return {"supervisor": o.get("supervisor_campo") or "", "gestor": o.get("gestor") or "",
            "tecnicos": sorted({nomes.get(p) for p in pids if nomes.get(p)}, key=visao._norm_nome)}


def ocorrencias(uid: int, est: dict) -> list[dict]:
    """As ocorrências abertas da usina, na ordem da tela Ocorrências (`ocorrencias.ordenar`: a do prazo mais perto
    primeiro), com a cor da etiqueta da Visão geral pela criticidade."""
    abertas = [o for o in est.values() if o.get("aberta") and o.get("usina_id") == uid]
    return [dict(o, cor=campo_oc.COR_ETIQUETA.get(o.get("criticidade"), "neutro"),
                 crit_txt=campo_oc.CRITICIDADES.get(o.get("criticidade"), o.get("criticidade") or ""))
            for o in campo_oc.ordenar(abertas)]


def _dm(d) -> str:
    s = str(d or "")[:10]
    return f"{s[8:10]}/{s[5:7]}" if len(s) == 10 else s


def _item_seguranca(k: str, x: dict) -> dict:
    """Uma linha da Segurança no texto da Visão (o extintor como no detalhe de Extintores dela; a PT com o botão que abre
    a PT por cima, `pt`)."""
    if k == "pts":
        return {"forte": f"OS {x.get('os') or x.get('numero')}", "txt": str(x.get("tarefa") or "")[:60],
                "pt": {"numero": x.get("numero"), "codigo": x.get("codigo") or "", "titulo": x.get("tarefa") or ""}}
    if k in ("sem_luvas", "luvas_semv"):
        if k == "sem_luvas":
            return {"forte": "", "txt": f"desde {_dm(x.get('desde'))}" if x.get("desde") else ""}
        return {"forte": "", "txt": f"última verificação há {x['dias']} dias" if x.get("dias") is not None
                else "nunca verificadas na ronda"}
    if k == "ronda":
        return {"forte": "", "txt": f"pedida em {_dm(x.get('pedida_em'))} · {x.get('feitos', 0)} de {x.get('total', 0)} "
                                    "extintores conferidos de novo"}
    onde = " · ".join(v for v in (x.get("local") or "", x.get("posicao") or "") if v)
    if k == "vencidos":
        txt = f"{x.get('vence_qual') or 'validade'} venceu em {_dm(x.get('vence'))}"
    elif k == "perto":
        txt = f"{x.get('vence_qual') or 'validade'} vence em {x.get('dias_vence')} dias"
    elif k == "sem_atual":
        txt = (f"sem conferência há {x.get('dias_conferencia')} dias" if x.get("dias_conferencia") is not None
               else "nunca conferido")
    else:
        txt = "não reconhecido em campo, esperando a Segurança"
    return {"forte": f"Extintor {x.get('ext') or x.get('codigo') or ''}".strip(),
            "txt": (f"({onde[:40]}) " if onde else "") + txt}


def seguranca(uid: int, listas: dict) -> list[dict]:
    """As pendências da Segurança na usina: as listas da Mesa (`hseq._pendencias`, a mesma conta da Mesa, do e-mail
    semanal e da planilha) só com as linhas dela, na ordem da Mesa."""
    out = []
    for k, rot in SEGURANCA:
        itens = [x for x in listas.get(k) or [] if x.get("usina_id") == uid]
        if itens:
            out.append({"chave": k, "rot": rot, "n": len(itens), "itens": [_item_seguranca(k, x) for x in itens]})
    return out
