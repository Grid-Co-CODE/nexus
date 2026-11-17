"""O dossiê do cliente em Markdown, com as UFVs pontuadas (16/11/2026).

Levi, com a Nexus IA da carteira no ar: "seria interessante o dossiê em .MD do cliente! Pontuando as UFVs!". E, com o
exemplo da Athon na mão, as três escolhas: a régua do Score de saúde do mockup R18 MAIS a disponibilidade (sem ela, a
Capitão Poço 100, com 85,3% em novembro e 26,4 h parada, saía com 80, "em dia"); uso interno e para leitura por IA (traz
as OS e o status dos chamados, não é para mandar ao cliente); e o botão no Comando › Usinas, filtrado por um cliente.

O que é: o dossiê da carteira (`carteira_ia.montar`) só com as usinas do cliente, e na frente o ranking das UFVs, da
pior para a melhor, cada uma com o que tirou pontos. Os números são os da carteira (a régua de cada tela dona); a
pontuação é a única conta nova, e mora aqui. Sem o nome das pessoas, como o da carteira.

Puro: nada de rede, banco nem Flask. Quem junta as fontes é a rota (`torres/comando/__init__.cliente_dossie_md`).
"""
from __future__ import annotations

from datetime import datetime

from . import carteira_ia as CI

VERSAO = 1

# ── a régua (16/11/2026, Levi: "R18 + disponibilidade") ──────────────────────────────────────────────────────────────
# Cada usina começa com 100 e perde pelo que pesa hoje. Do mockup R18: a meta do mês abaixo de 95% (0,6 ponto por ponto
# percentual, até 35), o estado de agora no COS, a OS fora do prazo (aqui: a urgente não iniciada, religamento ou
# corretiva emergencial, e a atrasada na régua do PCM), o PPCI vencido (aqui: o extintor vencido da Segurança), 3 ou mais
# religamentos no mês (aqui: os desligamentos do COS) e o dado suspeito (aqui: a disponibilidade do mês sem publicar). A
# pendência da EPC do R18 ficou fora: o Nexus não tem essa fonte. A disponibilidade entrou na escolha do Levi: 1 ponto
# por ponto percentual abaixo de 98%, até 20.
META_CORTE, META_PESO, META_TETO = 95.0, 0.6, 35
DISP_CORTE, DISP_PESO, DISP_TETO = 98.0, 1.0, 20
ESTADO = {"critico": ("Crítico agora no COS", 20), "atencao": ("Atenção agora no COS", 8),
          "sem_com": ("Sem comunicação agora no COS", 6)}
POR_URGENTE, POR_ATRASADA = 12, 5
EXTINTOR = 10
DESLIG_MIN, DESLIG = 3, 8
SEM_DISP = 3
EM_DIA, ATENCAO = 80, 55             # 80 a 100 em dia; 55 a 79 atenção; abaixo de 55 risco


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def pontuar(b: dict, mes: str = "mês") -> tuple[int, list[tuple[str, int]]]:
    """(pontos de 0 a 100, [(o que tirou pontos, quantos)]) de uma usina, pelos números crus da carteira
    (`carteira_ia.montar(...)["brutos"][nome]`)."""
    pontos, porque = 100, []

    def tira(motivo: str, n: int) -> None:
        nonlocal pontos
        if n > 0:
            pontos -= n
            porque.append((motivo, n))

    at, disp = b.get("atingimento"), b.get("disp")
    if at is not None and at < META_CORTE:
        tira(f"Meta de {mes} em {CI._pct(at)}", min(META_TETO, round((META_CORTE - at) * META_PESO)))
    if disp is None:
        tira(f"Disponibilidade de {mes} sem publicar", SEM_DISP)
    elif disp < DISP_CORTE:
        tira(f"Disponibilidade de {mes} em {CI._pct(disp)}", min(DISP_TETO, round((DISP_CORTE - disp) * DISP_PESO)))
    if b.get("estado") in ESTADO:
        tira(*ESTADO[b["estado"]])
    urg, atr = b.get("urgentes") or 0, b.get("atrasadas") or 0
    tira(_plural(urg, "OS urgente não iniciada", "OS urgentes não iniciadas"), POR_URGENTE * urg)
    tira(_plural(atr, "OS atrasada", "OS atrasadas"), POR_ATRASADA * atr)
    if (b.get("extintores") or 0) > 0:
        tira(_plural(b["extintores"], "extintor vencido", "extintores vencidos"), EXTINTOR)
    if (b.get("desligamentos") or 0) >= DESLIG_MIN:
        tira(f"{b['desligamentos']} desligamentos em {mes}", DESLIG)
    return max(0, pontos), porque


def nivel(pontos: int) -> str:
    return "em dia" if pontos >= EM_DIA else ("atenção" if pontos >= ATENCAO else "risco")


def arquivo(cliente: str, agora: datetime) -> str:
    """"Sal Energia" -> "dossie-cliente-sal-energia-2026-11-16.md" (sem acento: vai no cabeçalho do download)."""
    return f"dossie-cliente-{CI._chave(cliente).replace(' ', '-') or 'sem-nome'}-{agora:%Y-%m-%d}.md"


def montar(cliente: str, dz: dict, agora: datetime) -> dict:
    """{"texto": o dossiê do cliente em Markdown, "arquivo": o nome do download, "ranking": [(usina, pontos, nível,
    [(motivo, pontos)])], "media"}. `dz` = o dossiê da carteira já recortado nas usinas do cliente."""
    mes, brutos = dz.get("mes") or "mês", dz.get("brutos") or {}
    ranking = sorted(((nome, *pontuar(b, mes)) for nome, b in brutos.items()), key=lambda x: (x[1], x[0].lower()))
    ranking = [(nome, p, nivel(p), porque) for nome, p, porque in ranking]
    media = round(sum(p for _n, p, _v, _w in ranking) / len(ranking)) if ranking else None
    conta = {v: sum(1 for _n, _p, nv, _w in ranking if nv == v) for v in ("risco", "atenção", "em dia")}
    sem_cos = sum(1 for b in brutos.values() if b.get("estado") not in ESTADO and b.get("estado") != "normal")

    cab = [f"# Dossiê do cliente {cliente}", "",
           f"- Documento: dossiê do cliente {cliente}, gerado pelo Nexus, para uso interno e para leitura por IA "
           f"(formato {VERSAO})",
           f"- Gerado em: {agora.strftime('%d/%m/%Y às %H:%M')}, horário de Brasília",
           "- Uso interno: traz as OS e o status dos chamados no fabricante; não é para mandar ao cliente",
           "- Pessoas: não constam (nem responsáveis nem técnicos)", "",
           "## Como ler", "",
           "- A seção 1 é a pontuação de cada UFV, pela régua dela; as outras são o dossiê da carteira só com as usinas do cliente."]
    cab += list(dz.get("como_ler") or [])

    regua = [
        "A régua: cada usina começa com 100 pontos e perde pelo que pesa hoje.",
        f"- Meta de {mes} abaixo de {CI._num(META_CORTE, 0)}%: {CI._num(META_PESO, 1)} ponto por ponto percentual que "
        f"falta, até {META_TETO}.",
        f"- Disponibilidade de {mes} abaixo de {CI._num(DISP_CORTE, 0)}%: {CI._num(DISP_PESO, 0)} ponto por ponto "
        f"percentual que falta, até {DISP_TETO}; sem a disponibilidade publicada: {SEM_DISP}.",
        "- Estado agora no COS: " + "; ".join(f"{t.split(' agora')[0].lower()} {n}" for t, n in ESTADO.values()) + ".",
        f"- OS urgente não iniciada (religamento, religamento remoto ou corretiva emergencial): {POR_URGENTE} cada; OS "
        f"atrasada (régua do PCM, programada há mais de 10 dias): {POR_ATRASADA} cada.",
        f"- Extintor vencido: {EXTINTOR}; {DESLIG_MIN} ou mais desligamentos no mês: {DESLIG}.",
        f"- Nível: {EM_DIA} a 100 em dia; {ATENCAO} a {EM_DIA - 1} atenção; abaixo de {ATENCAO} risco. O mínimo é 0."]
    resumo = ([f"- Usinas: {len(ranking)}; pontuação média: {media} de 100; em risco: {conta['risco']}; em atenção: "
               f"{conta['atenção']}; em dia: {conta['em dia']}"] if ranking else ["- Nenhuma usina deste cliente."])
    if sem_cos:
        resumo.append(f"- {_plural(sem_cos, 'usina sem leitura', 'usinas sem leitura')} do COS agora: o estado não "
                      "tirou pontos delas.")
    tabela = (["", "Da pior para a melhor:", ""] + CI._tabela(
        ["#", "Usina", "Pontos", "Nível", "O que tirou pontos"],
        [[str(i), nome, str(p), nv, "; ".join(f"{t} (−{n})" for t, n in porque) or "nada"]
         for i, (nome, p, nv, porque) in enumerate(ranking, 1)]) + [""]) if ranking else [""]

    secoes = [("Pontuação das UFVs", "os números da seção 3 e o estado de agora no COS, pela régua abaixo",
               resumo + tabela + regua)]
    for titulo, fonte, corpo in dz.get("secoes") or []:
        if titulo == "Resumo da carteira":
            titulo = "Resumo do cliente"
            corpo = [l for l in corpo if not l.startswith("- Por cliente:")]
        secoes.append((titulo, fonte, corpo))
    texto = CI.juntar(cab, secoes)
    return {"texto": texto, "arquivo": arquivo(cliente, agora), "ranking": ranking, "media": media}
