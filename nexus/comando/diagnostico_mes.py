"""O mês fechado no prontuário: os meses que existem, o dossiê do mês e o Nexus IA Insights do mês (18/11/2026).

Levi: "O insights e todo o prontuário deve funcionar por mês! Começando por outubro mas quando eu abrir o prontuário quero
sempre no mês vigente, o que fica pendente do último mês ou dia ainda aparece porém em relação a meta, PR, geração tem que
ser do mês atual, o que foi feito no ativo". E, à pergunta se o mês fechado teria um diagnóstico da IA ou só os números:
"Sim! Com direito a relatório e tudo".

- Os meses vão do vigente até `PRIMEIRO_MES` (outubro de 2026, o 1º mês do banco de performance). O vigente é o
  prontuário de sempre, com o diagnóstico do dia; o fechado tem a página do fechamento.
- Os dados do mês são os do relatório em PDF (`campo/relatorio_usina.dados`), que já recortava o mês: a performance, as
  paradas do COS, as rondas, as tarefas executadas, a zeladoria e os chamados do mês, mais o que está aberto HOJE.
- O dossiê do mês (`dossie`) é o texto que a IA lê: os números com o nome deles, "sem dado" no que falta, sem o nome
  das pessoas.
- O diagnóstico do mês é UM por usina por mês, guardado em `<NEXUS_DADOS>/ia/diagnosticos/mes/AAAA-MM/<usina>.json`
  (a trava e o guardado são os do diagnóstico do dia, com a chave do mês). Vai em Busca; o número de desligamentos é
  conferido com o do mês e, se não bate, refaz uma vez pensando (a mesma regra do diagnóstico do dia).
- O que NÃO dá: ver as pendências como estavam no fim do mês. As fontes só guardam o que está aberto agora; por isso a
  seção se chama "o que segue pendente hoje".
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime

from . import diagnostico as DG
from . import ia as IA

log = logging.getLogger(__name__)

PRIMEIRO_MES = "2026-10"         # o 1º mês do banco de performance (`fato_meta_usina_mes`): antes dele não há o que mostrar
SEM_DADO = "sem dado"
MAX_PARADAS = 30                 # as paradas listadas no dossiê do mês (na Capitão Poço 100, outubro teve 81)
MAX_ITENS = {"pesou": 4, "feito": 4, "pendente": 4}
MAX_ITEM, MAX_SITUACAO = 160, 320
_NOMES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro",
          "dezembro")

PEDIDO = """Faça o DIAGNÓSTICO DO MÊS FECHADO desta usina para o supervisor e o gestor dela. O texto acima é o fechamento do mês: os números do mês, o que foi feito no ativo e o que segue pendente hoje. Seja direto.
Responda SÓ com o bloco abaixo, em JSON válido, sem nada antes ou depois, sem markdown e sem citar as seções (§). Este formato vale acima do limite de palavras.
<diagnostico>{"situacao": "...", "pesou": [{"texto": "...", "os": null}], "feito": [{"texto": "...", "os": null}], "pendente": [{"texto": "...", "os": null}]}</diagnostico>
- situacao: uma ou duas frases, a conclusão primeiro: como o mês fechou (meta, PR e disponibilidade, com o número) e o motivo principal.
- pesou: o que mais tirou geração ou disponibilidade no mês, do maior para o menor, cada um com o número do fechamento que o sustenta; no máximo quatro itens curtos.
- feito: o que foi feito no ativo no mês (rondas, manutenção, zeladoria, chamados finalizados); no máximo quatro itens curtos.
- pendente: o que segue aberto hoje, da seção "O que segue pendente hoje"; no máximo quatro itens curtos.
- Use só os números do fechamento, cada um com o nome que ele tem lá. O número de desligamentos é o da linha "Desligamentos (a geração parou)"; não conte a lista das paradas e não use outro número no lugar.
- O que o fechamento marca como "sem dado" ou "sem leitura" não vira item nem conclusão: não é zero.
- Fale só deste mês. Não invente causa, OS ou número.
- "os": o número de uma OS citada no fechamento e ligada ao item, ou null.
- Lista vazia quando não houver nada."""


# ── os meses ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def meses(hoje: date) -> list[tuple[str, str, bool]]:
    """[("AAAA-MM", "Novembro de 2026", é o vigente)], do vigente até `PRIMEIRO_MES`, o mais novo primeiro."""
    out, a, m = [], hoje.year, hoje.month
    while f"{a:04d}-{m:02d}" >= PRIMEIRO_MES:
        out.append((f"{a:04d}-{m:02d}", f"{_NOMES[m - 1].capitalize()} de {a}", (a, m) == (hoje.year, hoje.month)))
        a, m = (a, m - 1) if m > 1 else (a - 1, 12)
    return out


def mes_fechado(valor, hoje: date) -> str | None:
    """O mês pedido, se é um mês FECHADO que o prontuário tem (de `PRIMEIRO_MES` até o anterior ao vigente). None para o
    vigente, o de antes do banco e o que não é mês: aí vale o prontuário de sempre."""
    v = str(valor or "").strip()
    return v if any(m == v and not vigente for m, _r, vigente in meses(hoje)) else None


# ── o dossiê do mês ──────────────────────────────────────────────────────────────────────────────────────────────────
def _br(x, casas: int = 1) -> str:
    return f"{float(x):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dm(d) -> str:
    return f"{d.day:02d}/{d.month:02d}" if d else ""


def desligamentos(d: dict) -> int | None:
    """Os desligamentos do mês (as paradas do COS em que a geração parou). None: as paradas não foram lidas."""
    rel = d.get("religamentos")
    return None if rel is None else sum(1 for x in rel if x.get("parou"))


def dossie(d: dict) -> str:
    """O fechamento do mês em texto, para a IA: `d` é o `relatorio_usina.dados` do mês. Cada número com o nome dele; o
    que falta é "sem dado"; o tema que não abriu é "sem leitura" (nunca zero)."""
    erros = d.get("erros") or {}
    out = [f"# Fechamento de {d.get('mes_txt')} da usina {d.get('usina')}", "",
           f"- Documento: o mês fechado da usina, montado pelo Nexus para leitura por IA. Cliente: {d.get('cliente') or SEM_DADO}.",
           f"- Mês: {d.get('mes_txt')}, de {_dm(d.get('ini'))} a {_dm(d.get('fim'))}. Pessoas: citadas pelo papel, sem o nome.",
           '- "sem dado" quer dizer que a fonte não tem o valor: não é zero. "sem leitura" quer dizer que a fonte não abriu.',
           "", "## 1. Performance do mês", ""]
    if "perf" in erros or not d.get("perf"):
        out.append("- Performance: sem leitura.")
    else:
        meta, disp = d["perf"].get("meta") or {}, d["perf"].get("disp") or {}
        if meta.get("prod_kwh") is not None and meta.get("meta_kwh"):
            cob = f" ({meta.get('dias_cob')} de {meta.get('dias_mes')} dias medidos)" if meta.get("dias_cob") and meta.get("dias_mes") else ""
            ating = f"{_br(meta['atingimento'], 0)}% da meta de " if meta.get("atingimento") is not None else "meta de "
            out.append(f"- Geração: {_br(meta['prod_kwh'] / 1000)} MWh, {ating}{_br(meta['meta_kwh'] / 1000)} MWh{cob}")
        else:
            out.append(f"- Geração e meta: {SEM_DADO}")
        out.append("- PR do mês: " + (f"{_br(meta['pr'])}%" + (f" (previsto: {_br(meta['pr_meta'])}%)" if meta.get("pr_meta") is not None else "")
                                      if meta.get("pr") is not None else SEM_DADO))
        out.append("- Disponibilidade do mês: " + (f"{_br(disp['disp'])}%" + (f"; {_br(disp['h_perdidas'])} h paradas" if disp.get("h_perdidas") is not None else "")
                                                   if disp.get("disp") is not None else SEM_DADO))
        oss = (d["perf"].get("oss") or {}).get("oss") or []
        out.append(f"- Eventos que tiraram disponibilidade no mês: {len(oss)}")
        for x in oss[:MAX_PARADAS]:
            sol = f"{_br((x.get('sol_min') or 0) / 60)} h de sol" if x.get("sol_min") is not None else ""
            perda = f"perda de {_br(x['perda_kwh'], 0)} kWh" if x.get("perda_kwh") is not None else ""
            out.append("  - " + " · ".join(p for p in (f"{x.get('inicio')} a {x.get('fim') or 'em aberto'}", str(x.get("tipo") or ""),
                                                       str(x.get("escopo") or ""), sol, perda) if p))
    out += ["", "## 2. Paradas registradas pelo COS no mês", ""]
    rel = d.get("religamentos")
    if "religamentos" in erros or rel is None:
        out.append("- Paradas do COS: sem leitura.")
    else:
        out.append(f"- Desligamentos (a geração parou): {desligamentos(d)}")
        out.append(f"- Registros sem a geração parar (não é desligamento): {sum(1 for x in rel if not x.get('parou'))}")
        lista = rel if len(rel) <= MAX_PARADAS else rel[-MAX_PARADAS:]
        if len(rel) > MAX_PARADAS:
            out.append(f"- Abaixo, as {MAX_PARADAS} paradas mais recentes do mês (de {len(rel)}): os números de cima contam todas.")
        for x in lista:
            ini = x.get("ini")
            out.append("- " + " · ".join(p for p in (
                f"{ini:%d/%m %H:%M}" if ini else "", str(x.get("tipo") or ""), str(x.get("fora") or ""),
                "desligamento (a geração parou)" if x.get("parou") else "não é desligamento (a geração não parou)",
                f"OS {x['os']}" if x.get("os") else "", f"proteções: {x['protecoes']}" if x.get("protecoes") else "",
                str(x.get("relato") or "")[:220]) if p))
    out += ["", "## 3. O que foi feito no ativo no mês", ""]
    if "rondas" in erros or d.get("rondas") is None:
        out.append("- Rondas: sem leitura.")
    else:
        rs = d["rondas"]
        out.append(f"- Rondas feitas no mês: {len(rs)}")
        for r in rs:
            dia = str(r.get("data") or "")
            lido = "; ".join(p for p in (f"sujidade {r['sujidade']}" if r.get("sujidade") is not None else "",
                                          f"vegetação {r['vegetacao']}" if r.get("vegetacao") is not None else "",
                                          f"vala {r['vala']}" if r.get("vala") else "") if p)
            out.append(f"  - {dia[8:10]}/{dia[5:7]} · ronda {r.get('tipo') or ''}".rstrip() + (f" · {lido} (níveis de 1 a 5; 5 é o pior)" if lido else ""))
    if "manut" in erros or not d.get("manut"):
        out.append("- Manutenção: sem leitura.")
    else:
        mt = d["manut"]
        feitas = mt.get("feitas") or []
        tot = sum(x["tarefas"] for x in feitas)
        out.append(f"- Tarefas de manutenção executadas no mês: {tot}" + (
            " (" + "; ".join(f"{x['tipo']}: {x['tarefas']} em {x['os']} OS" for x in feitas) + ")" if feitas else ""))
        if mt.get("zeladoria"):
            out.append("- Zeladoria feita em: " + ", ".join(_dm(x) for x in mt["zeladoria"]))
    ch = d.get("chamados")
    if "chamados" in erros or ch is None:
        out.append("- Chamados de garantia: sem leitura.")
    else:
        ini, mes = d.get("ini"), ch.get("mes") or []
        fin = [c for c in mes if c.get("situacao") == "concluido" and c.get("fim") and ini and (c["fim"].year, c["fim"].month) == (ini.year, ini.month)]
        abertos = [c for c in mes if c.get("ini") and ini and (c["ini"].year, c["ini"].month) == (ini.year, ini.month)]
        out.append(f"- Chamados de garantia abertos no mês: {len(abertos)}")
        for c in abertos:
            out.append(f"  - OS {c.get('os')} · {c.get('equip')} · {c.get('fabricante') or 'fabricante ' + SEM_DADO} · aberto em {_dm(c.get('ini'))} · "
                       + ("finalizado em " + _dm(c["fim"]) if c.get("situacao") == "concluido" and c.get("fim") else "segue aberto hoje"))
        out.append(f"- Chamados de garantia finalizados no mês: {len(fin)}")
        for c in fin:
            if c not in abertos:
                out.append(f"  - OS {c.get('os')} · {c.get('equip')} · {c.get('fabricante') or 'fabricante ' + SEM_DADO} · finalizado em {_dm(c.get('fim'))}")
    hoje = d.get("hoje")
    out += ["", f"## 4. O que segue pendente hoje ({hoje:%d/%m/%Y})" if hoje else "## 4. O que segue pendente hoje", ""]
    if d.get("manut") and "manut" not in erros:
        ab = d["manut"].get("abertas") or []
        out.append(f"- OS em aberto hoje: {sum(x['os'] for x in ab)}" + (" (" + "; ".join(f"{x['tipo']}: {x['os']}" for x in ab) + ")" if ab else ""))
    else:
        out.append("- OS em aberto hoje: sem leitura.")
    out.append(f"- Chamados de garantia em aberto hoje: {ch.get('em_aberto', 0)}" if ch is not None and "chamados" not in erros
               else "- Chamados de garantia em aberto hoje: sem leitura.")
    out.append("- As pendências são as de hoje: o Nexus não guarda como elas estavam no último dia do mês.")
    return "\n".join(out).rstrip() + "\n"


# ── a resposta da IA ─────────────────────────────────────────────────────────────────────────────────────────────────
def _os_do_mes(d: dict) -> dict[str, str]:
    """{OS: o tipo dela} das OS que o fechamento cita: a parada do COS abre o card ("religamento"), o chamado abre o Raio
    X ("chamado"). A OS que não está aqui não vira link."""
    mapa = {str(c.get("os")): "chamado" for c in (d.get("chamados") or {}).get("mes") or [] if c.get("os")}
    mapa.update({str(x["os"]): "religamento" for x in d.get("religamentos") or [] if x.get("os")})
    return mapa


def ler(texto: str, d: dict) -> dict | None:
    """O JSON da resposta -> {situacao, pesou, feito, pendente}, cada item {texto, os, os_tipo}. None quando não veio o
    JSON. A OS que o fechamento não cita sai do item."""
    m = DG._RX_BLOCO.search(texto or "")
    bruto = m.group(1) if m else (texto or "")
    i, f = bruto.find("{"), bruto.rfind("}")
    if i < 0 or f <= i:
        return None
    try:
        j = json.loads(bruto[i:f + 1])
    except ValueError:
        return None
    if not isinstance(j, dict) or not str(j.get("situacao") or "").strip():
        return None
    mapa = _os_do_mes(d)
    out = {"situacao": DG._limpo(j.get("situacao"), MAX_SITUACAO)}
    out["situacao_os"] = {n: mapa[n] for n in re.findall(r"(?<![\d.,])(\d{4,6})(?![\d.,]\d)", out["situacao"]) if n in mapa}
    for lista in MAX_ITENS:
        itens = []
        for x in (j.get(lista) or [])[:MAX_ITENS[lista]]:
            if isinstance(x, str):
                x = {"texto": x}
            if not isinstance(x, dict):
                continue
            txt = DG._limpo(x.get("texto") or x.get("item") or x.get("acao"), MAX_ITEM)
            if not txt:
                continue
            os_ = str(x.get("os") or "").strip()
            os_ = os_ if os_ in mapa else ""
            itens.append({"texto": txt, "os": os_, "os_tipo": mapa.get(os_, "")})
        out[lista] = itens
    return out


def conferir(diag: dict | None, d: dict) -> list[str]:
    """O que o diagnóstico do mês diz e o fechamento não sustenta: cada "N desligamentos" tem que ser o número do mês
    (a mesma conferência do diagnóstico do dia; o caso: `diagnostico.conferir`)."""
    n_mes = desligamentos(d)
    if not diag or n_mes is None:
        return []
    textos = [diag.get("situacao") or ""] + [x.get("texto") or "" for lista in MAX_ITENS for x in diag.get(lista) or []]
    fora = sorted({int(n) for t in textos for n in DG._RX_DESLIGAMENTOS.findall(t)} - {n_mes})
    return [f"{n} desligamento{'' if n == 1 else 's'}: o fechamento do mês tem {n_mes}" for n in fora]


# ── o guardado do mês ────────────────────────────────────────────────────────────────────────────────────────────────
def chave(mes: str) -> str:
    """A pasta do guardado do mês, dentro da dos diagnósticos (`diagnostico._pasta`): "mes/AAAA-MM"."""
    return f"mes/{mes}"


def guardado(cfg, usina_id: int, mes: str) -> dict | None:
    return DG.guardado(cfg, usina_id, chave(mes))


def gerar(cfg, usina_id: int, d: dict) -> dict:
    """Faz o diagnóstico do mês, guarda e solta a trava. Roda numa thread à parte (a rota não espera); no teste, na
    hora. Em Busca; o número de desligamentos que não bate com o do mês refaz uma vez pensando."""
    mes = d["mes"]
    pasta = DG._pasta(cfg, chave(mes))
    texto = dossie(d)
    tokens = round(len(texto) / 4)

    def uma_vez(pensar: bool):
        rs = IA.perguntar(cfg, [DG.modelo(cfg)], texto, PEDIDO, pensar=pensar)
        IA.registrar(cfg, usina_id, f"[diagnóstico do mês {mes}]", rs, "diagnostico-do-mes", tokens)
        r = rs[0] if rs else {"ok": False, "erro": "Nenhuma IA ligada para o diagnóstico."}
        return r, (ler(r.get("texto") or "", d) if r.get("ok") else None)

    try:
        r, diag = uma_vez(DG.PENSAR)
        falhas, refeito = conferir(diag, d), False
        if falhas and not DG.PENSAR:
            r2, diag2 = uma_vez(True)
            if r2.get("ok") and diag2:
                r, diag, falhas, refeito = r2, diag2, conferir(diag2, d), True
        agora = datetime.now(IA._BRT)
        g = {"usina_id": int(usina_id), "mes": mes, "mes_txt": d.get("mes_txt") or "", "ts": time.time(),
             "gerado_em": agora.isoformat(timespec="seconds"), "ok": bool(r.get("ok")), "modelo": r.get("id") or "",
             "rotulo": r.get("rotulo") or "", "troca": r.get("troca") or "", "erro": r.get("erro") or "", "ms": r.get("ms"),
             "versao": DG.VERSAO}
        if r.get("ok"):
            g["diag"] = diag
            g["texto"] = "" if diag else IA.limpar_citacoes(r.get("texto") or "")[:3000]
            if refeito:
                g["refeito"] = True
            if falhas:
                g["conferir"] = falhas
        if pasta:
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / f"{int(usina_id)}.json").write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
        return g
    except Exception as ex:      # noqa: BLE001 — a thread não pode morrer calada
        log.exception("Diagnóstico do mês %s: a usina %s falhou", mes, usina_id)
        return {"ok": False, "erro": f"Falhou ({type(ex).__name__})."}
    finally:
        DG.soltar(cfg, usina_id, chave(mes))


def para_tela(g: dict) -> dict:
    """O que a tela recebe: o estado, o mês e o diagnóstico (sem o registro interno)."""
    if not g.get("ok"):
        return {"estado": "erro", "erro": g.get("erro") or "A IA não respondeu.", "mes": g.get("mes") or ""}
    em = g.get("gerado_em") or ""
    return {"estado": "pronto" if g.get("diag") else "texto", "diag": g.get("diag"), "texto": g.get("texto") or "",
            "mes": g.get("mes") or "", "mes_txt": g.get("mes_txt") or "", "rotulo": g.get("rotulo") or "",
            "troca": g.get("troca") or "", "hora": em[11:16], "data": f"{em[8:10]}/{em[5:7]}" if len(em) >= 10 else "",
            **({"conferir": g["conferir"]} if g.get("conferir") else {})}
