"""perf_alvos.py: quem a Performance procura.

Os tipos de ativo da aba Performance (inversor, tracker, estação meteorológica), o nome curto do ativo e da usina para o título
da OS (`perf_os_nome`, `plano_base_nome`) e `get_performance_alvos`, que acha o ativo de cada plano (o tracker tem o plano no
ativo generalizado).

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""


# ═══════════════════ PERFORMANCE — OS por ativo a partir de plano ═══════════════════
PERF_TIPOS = ("Inversor", "Estrutura Trackers", "Estação Meteorológica")   # tipos da aba Performance
# Tipos que AGRUPAM trackers e por isso também podem receber a OS de tracker parado (Levi, 11/09).
# Medido no catálogo em 11/09: NCU existe como tipo de equipamento, 103 ativos, código
# `<USINA>-NCU1`. SKC e TCU ainda NÃO existem como equipamento de planta, só como peça de
# almoxarifado (bateria, antena); ficam declarados para o dia em que forem cadastrados, e até lá
# simplesmente não aparecem em usina nenhuma.
PERF_TIPOS_TRACKER_CONJUNTO = ("NCU", "SKC", "TCU")

# Tipos de equipamento que SÓ plantas têm — o discriminador entre PLANTA e MATERIAL/INVENTÁRIO.
# O catálogo tem materiais com "usina" e "cliente" próprios ("0,3P75 - G2", "0,6/1 kV"…), e
# qualquer lista de usinas montada sem este filtro os deixa vazar (aconteceu no COS em 07/07 e
# de novo no filtro do Histórico em 28/07). Espelho do _CARTEIRA_EQUIP das telas.
CARTEIRA_EQUIP = frozenset({"Inversor", "Cabine", "Tracker", "Estrutura Trackers",
                            "Estação Meteorológica", "Skid"})


def _usina_short(usina: str) -> str:
    """'Cliente - Usina - UF' → 'Usina' (miolo). Fallback: a string toda."""
    parts = [p.strip() for p in str(usina or "").split(" - ")]
    return (" - ".join(parts[1:-1]).strip() if len(parts) >= 3 else str(usina or "").strip()) or str(usina or "")


_CONECTIVOS = {"de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas", "com", "para"}


def _asset_short_name(a: dict) -> str:
    """Nome curto do ativo (do description): 'Inversor 1.1' / 'Tracker 5.100' / 'Estação Meteorológica'.
    O ativo da PRÓPRIA usina não tem nome de equipamento — o description dele é o nome da usina
    ('Thopen - Céu Azul 1 - PR') → devolve o TIPO ('Usina'). Sem isso o título saía com um pedaço
    do nome da usina no lugar do equipamento: '[Céu Azul 1][Thopen -]'."""
    import re
    desc = str(a.get("description") or "").split("{")[0].strip()
    if str(a.get("tipo_code") or "").upper() == "USINA":       # item-usina (_build_records)
        return str(a.get("tipo") or "").strip() or "Usina"
    if len([p for p in desc.split(" - ") if p.strip()]) >= 3:  # 'Cliente - Usina - UF' sem tipo_code
        return str(a.get("tipo") or "").strip() or "Usina"
    m = re.match(r"([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)?)\s+([\d.]+)", desc)
    if m:
        return f"{m.group(1)} {m.group(2)}".strip()
    toks = [t for t in desc.split() if t.strip("-–—·|/")]      # descarta separador solto ('Thopen -')
    if not toks:
        return a.get("code") or "?"
    if len(toks) > 2 and toks[1].lower().strip(".") in _CONECTIVOS:
        return " ".join(toks[:4])                              # 'Cabine de Medição' (não 'Cabine de')
    return " ".join(toks[:2])


def plano_base_nome(desc: str) -> str:
    """Nome do plano sem o prefixo '[...] - ' → 'Recomposição de String'."""
    import re
    d = str(desc or "").split("{")[0].strip()
    return re.sub(r"^\s*\[[^\]]*\]\s*[-–]\s*", "", d).strip()


def perf_os_nome(asset: dict, base: str) -> str:
    """Monta '[Equipamento] - base'.

    PADRÃO NOVO (27/07, decisão do Levi): era '[Usina][Equipamento] - descrição' e passou a ser
    só '[Equipamento] - descrição'. A usina já aparece na própria OS (ativo, local, cliente), e
    repeti-la no título consumia metade do espaço útil da lista — nomes como
    '[Sítio Batinga – Distrito de Água Fria][Estrutura Trackers 109.100]' não cabiam em lugar
    nenhum. Vale para Performance e COS, que é onde esta função é usada."""
    return f"[{api._asset_short_name(asset)}] - {base}".strip()


def _eh_tracker_generalizado(a: dict) -> bool:
    """O ativo-pai da usina, aquele que carrega o PLANO que as OS dos trackers individuais copiam.

    DUAS PALAVRAS, E NÃO A FRASE EXATA (Levi, 08/09: "não está carregando os trackers de Salto do
    Pirapora mesmo tendo esses ativos criados"). A regra exigia 'estrutura trackers' coladas, e o
    ativo de lá se chama 'Estrutura DE Trackers' — o `get_performance_alvos` não achava o
    generalizado, respondia "Não achei a Estrutura Trackers desta usina" e a lista abria vazia,
    com os 14 trackers cadastrados e invisíveis.

    Medido no catálogo de 08/09, 6.909 ativos do tipo: a régua nova muda a classificação de
    exatamente DOIS — 'SPP300-ETKR1' (Salto Pirapora 3) e 'THPN-FZL100-ETKR1' (Fazenda Limão 1),
    os dois escritos com o 'de'. Nenhum tracker individual é engolido: eles se chamam 'Tracker
    N.M' e não têm a palavra 'estrutura'.

    E NÃO basta ter 'estrutura': quatro usinas (Ouro Branco 1, Sorocaba 1, Santana do Ipanema 1,
    Cascavel 1) têm 'Estrutura FIXA' — são plantas sem tracker nenhum, e continuam, corretamente,
    sem generalizado."""
    if a.get("tipo") != "Estrutura Trackers":
        return False
    t = api._norm_txt(a.get("label") or a.get("description"))
    return "estrutura" in t and "tracker" in t


def get_performance_alvos(assets_usina: list, card_frase: str) -> dict:
    """Ativos selecionáveis de UMA usina p/ o card (ex.: 'recomposicao de string'). Inversor/Estação: cada
    ativo com o SEU plano. Tracker: plano do GENERALIZADO aplicado aos individuais (não-linkado).
    → {'is_tracker', 'ativos':[{asset, plano_id_task, plano_id_item, linkar}], 'base', 'erro'?}.
    Os planos vêm do catálogo dos planos, por ativo (`get_plans_for_assets(..., guardados=True)`, 31/10/2026): até então
    cada usina escolhida relia o plano de cada inversor."""
    frase = api._norm_txt(card_frase)
    uativos = [a for a in (assets_usina or []) if isinstance(a, dict) and a.get("tipo") in PERF_TIPOS]
    if "tracker" in frase:
        gen = next((a for a in uativos if api._eh_tracker_generalizado(a)), None)
        if not gen:
            return {"is_tracker": True, "ativos": [], "erro": "Não achei a Estrutura Trackers desta usina."}
        planos = [p for p in api.get_plans_for_assets([gen], guardados=True) if frase in api._norm_txt(p.get("description"))]
        if not planos:
            return {"is_tracker": True, "ativos": [], "erro": "A Estrutura Trackers não tem esse plano."}
        pt, pi = planos[0]["id_task"], gen.get("id")
        indiv = [a for a in uativos if a.get("tipo") == "Estrutura Trackers" and not api._eh_tracker_generalizado(a)]
        # O GENERALIZADO e as CONTROLADORAS entram na lista (Levi, 11/09). Antes só os trackers
        # individuais apareciam, e não havia como abrir uma OS que cobrisse um conjunto — que é
        # justamente o caso em que a quantidade de trackers parados deixa de ser 1. A tela mostra
        # um grupo de cada vez, com os individuais como padrão.
        conj = sorted((a for a in (assets_usina or [])
                       if isinstance(a, dict)
                       and str(a.get("tipo") or "").strip().upper() in PERF_TIPOS_TRACKER_CONJUNTO),
                      key=lambda a: str(a.get("code") or ""))
        # `linkar=False` para TODOS, inclusive o generalizado, que é o dono do plano. Ligar a OS
        # ao plano dele a faria contar como execução do plano de manutenção do ativo, mexendo no
        # cronograma do PCM por um efeito colateral que ninguém pediu. Aqui a OS nasce com as
        # subtarefas COPIADAS, igual à dos individuais.
        return {"is_tracker": True, "base": api.plano_base_nome(planos[0].get("description")),
                "ativos": [{"asset": a, "plano_id_task": pt, "plano_id_item": pi, "linkar": False}
                           for a in ([gen] + conj + indiv)]}
    # inversor / estação: cada ativo com o SEU plano
    cands = [a for a in uativos if a.get("tipo") in ("Inversor", "Estação Meteorológica")]
    planos = [p for p in api.get_plans_for_assets(cands, guardados=True) if frase in api._norm_txt(p.get("description"))]
    base = api.plano_base_nome(planos[0].get("description")) if planos else card_frase
    alvos = [{"asset": p["asset"], "plano_id_task": p["id_task"],
              "plano_id_item": p["asset"].get("id"), "linkar": True} for p in planos]
    # A ESTAÇÃO não tem o plano de coleta — ele mora no INVERSOR. Conferido em Brodowski 1: a ETM
    # tem 11 planos (MPM/MPS/MPA/Handover de estação) e NENHUM é o de coleta, então o filtro por
    # frase nunca devolvia a estação e o modo ETM abria com a lista vazia em toda usina.
    # Solução: a estação entra apontando para o plano do inversor, com `linkar=False` → OS avulsa
    # com as subtarefas COPIADAS. É o mesmo arranjo dos trackers individuais, cujo plano também
    # mora em outro ativo. Só vale para o card de coleta; nos outros, estação não faz sentido.
    if "coleta de dados" in frase and alvos:
        ja_tem = {a["asset"].get("id") for a in alvos}
        p0 = alvos[0]
        for est in uativos:
            if est.get("tipo") == "Estação Meteorológica" and est.get("id") not in ja_tem:
                alvos.append({"asset": est, "plano_id_task": p0["plano_id_task"],
                              "plano_id_item": p0["plano_id_item"], "linkar": False})
        # A USINA INTEIRA como alvo (Levi, 31/07): coletar geração de uma planta de 14 inversores
        # criava 14 OS para uma tarefa que é uma só. O item-usina entra pelo MESMO arranjo da
        # estação — plano do inversor, `linkar=False` — e vira UMA OS no ativo da planta.
        # Vem de `assets_usina` (não de `uativos`), porque o tipo 'Usina' não está em PERF_TIPOS.
        for u in (assets_usina or []):
            if (isinstance(u, dict) and u.get("tipo") == "Usina"
                    and u.get("id") and u.get("id") not in ja_tem):
                alvos.append({"asset": u, "plano_id_task": p0["plano_id_task"],
                              "plano_id_item": p0["plano_id_item"], "linkar": False})
                break                                   # uma planta tem um item-usina
    return {"is_tracker": False, "base": base, "ativos": alvos}


import api  # noqa: E402 — no fim: o `api` importa este módulo
