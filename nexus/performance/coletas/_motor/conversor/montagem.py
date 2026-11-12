# -*- coding: utf-8 -*-
"""Regras de colar no BD e a planilha de saída — iguais para todas as fontes.

O que entra (regras do Levi, valem para tudo que vai ao BD):
- "COLETA SÓ O QUE FOR A MAIS OU NÃO TEM NADA": célula vazia no BD recebe o valor; célula com número só é trocada se o
  arquivo traz MAIS (valor parcial ou travado da API — Altair 1.3 em nov/2026: o BD com ~318 kWh todo dia, o portal
  com o dia real, ~1.026). Diferença
  de até 1% fica com o BD (o portal da Taguaí vem 0,2-0,7% acima do BD todo dia; não é dia parcial).
- "não pode colar 0 se já tem dado de geração" (20/10/2026): 0 ou valor menor nunca cobre número do BD.
- Fórmula do BD não se toca (Vitesse: IPOA = Hortina; Salvales 21-25/10: IPOA = Carosa com a estação quebrada).
- Dia com colunas trocadas: se no mesmo dia algum inversor vem MENOR que o BD, nada daquele dia é trocado — só o vazio
  entra (Mandaguaçu 4, 16-21/10/2026: metade dos inversores maior, metade menor = colunas trocadas na API).
- Fora do padrão fica FORA do bloco e vira aviso (contador acumulado: Carosa 10/10/2026, inversor 1 com 6.668,2 e os
  outros em 0, contra ~1.400 num dia comum). Dia com todos os inversores em 0 também fica fora: pode ser o portal que
  não leu. "Se não tem o dado não tem motivo para inventar" (06/11/2026) — quem sabe o que houve digita.
- Só dia fechado (antes de hoje).

Como sai a planilha: por aba do BD, um retângulo que é CÓPIA do BD (mesmas linhas, mesmas colunas, na ordem do BD)
cobrindo TODOS os dias e colunas que o arquivo trouxe, também os que já estão certos (Levi, 10/11/2026), com os
valores novos em amarelo (valor colado à mão vai em amarelo no BD). A célula que já estava no BD é repetida com
o valor e a cor dela — colar o bloco inteiro não muda nada além do que é novo, nem com Ctrl+V comum. Coluna com
fórmula dentro do retângulo parte o bloco em dois: fórmula de tabela ("=SUM(T_Tucano...[[#This Row],...]])") ou de
outra aba não sobrevive a copiar e colar entre pastas de trabalho.
"""
import collections
import datetime as dt
import os
import re
import statistics

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as L

from conversor.nucleo import ETM_SOLTAS, SEM_USINA, br, formula, norm_col, vazio

AMARELO = "FFFFFF00"
CINZA = PatternFill("solid", fgColor="D9D9D9")
MAIS_QUE = 0.01                 # "a mais" = 1% acima do BD (abaixo disso é arredondamento do portal)
FORA_DO_PADRAO = 1.8            # x o valor típico da coluna
ETM_MAX = {"ipoa": 12.0, "ghi": 12.0}      # kWh/m² num dia: acima disso é unidade errada (J/m², Wh/m²)
TEMP_MAX = 90.0


def _tol(b):
    return 0.006 + abs(b) * 0.0005


def _tipo_col(cab):
    h = norm_col(cab)
    if h.startswith("inversor"):
        return "inversor"
    if h.startswith("ipoa"):
        return "ipoa"
    if h.startswith("ghi"):
        return "ghi"
    if h.startswith("temp"):
        return "temperatura"
    return "outro"


class Aviso(dict):
    def __init__(self, nivel, texto, aba=None, destino=None):
        super().__init__(nivel=nivel, texto=texto, aba=aba, destino=destino)


def _juntar(celulas, avisos):
    """{(destino, aba): {(data, coluna do leitor): (valor, fonte)}}; dois arquivos com valores diferentes = o maior."""
    out = collections.defaultdict(dict)
    for c, fonte in celulas:
        if c.valor is None:
            continue
        k = (c.data, c.coluna)
        velho = out[(c.destino, c.aba)].get(k)
        v = float(c.valor)
        if velho is not None and abs(velho[0] - v) > _tol(velho[0]):
            avisos.append(Aviso("leve", "%s %s: dois arquivos com valores diferentes (%g e %g); ficou o maior"
                                % (br(c.data), c.coluna, velho[0], v), c.aba, c.destino))
            v = max(v, velho[0])
        out[(c.destino, c.aba)][k] = (v, fonte, bool(c.so_vazio) or bool(velho and velho[2]),
                                      bool(c.confirmado) or bool(velho and velho[3]),
                                      c.nota or (velho[4] if velho else None))
    return out


def _classificar(ab, vals, hoje, avisos, destino):
    """Decide célula a célula. Devolve (novos {(linha, j): (valor, troca?)}, contagem, fontes)."""
    cont = collections.Counter()
    colunas = {}
    fontes = set()
    por_dia = collections.defaultdict(dict)                   # data -> {j: valor}
    sem_coluna, sem_linha = set(), set()
    so_vazio, confirmados, notas = set(), set(), {}
    for (d, nome), (v, fonte, sv, conf, nota) in vals.items():
        fontes.add(fonte)
        if d >= hoje:
            cont["hoje"] += 1
            continue
        j = colunas.get(nome)
        if j is None:
            j = colunas[nome] = ab.col(nome)
        if j is None:
            sem_coluna.add(nome)
            continue
        if d not in ab.datas:
            sem_linha.add(d)
            continue
        por_dia[d][j] = v
        if sv:
            so_vazio.add((d, j))
        if conf:
            confirmados.add((d, j))
        if nota:
            notas[(d, j)] = nota
    for n in sorted(sem_coluna):
        # temperatura é "se tiver" (Levi, 10/11/2026: "o que não tem fica nulo mesmo, não é obrigação"): aba sem a
        # coluna (as do BD_Thopen não têm) não é erro
        avisos.append(Aviso("info" if n == "Temperatura" else "erro",
                            "a aba não tem a coluna %r — esses valores ficaram de fora" % n, ab.nome, destino))
    if sem_linha:
        avisos.append(Aviso("leve", "a aba não tem as linhas de %s — crie as linhas do mês antes de colar e converta "
                            "de novo" % _faixa_datas(sorted(sem_linha)), ab.nome, destino))
    if cont["hoje"]:
        avisos.append(Aviso("info", "%d valores de hoje em diante ficaram de fora (só dia fechado)" % cont["hoje"],
                            ab.nome, destino))

    tipo = {j: _tipo_col(ab.cab[j]) for d in por_dia for j in por_dia[d]}
    # valor típico por coluna: mediana do que é positivo no arquivo e nos últimos 60 dias do BD
    tipico = {}
    for j in {j for d in por_dia for j in por_dia[d]}:
        if tipo[j] != "inversor":
            continue
        # o típico vem do PRÓPRIO arquivo; o BD só completa quando o arquivo tem poucos dias. Com o BD na média, o dia
        # inteiro do portal parecia 2x o típico onde a API gravou dia parcial (Mandaguaçu 17-20/10/2026: BD 0 ou ~700,
        # portal 900-1.300) e ficava fora do bloco — justo o caso que o mensal veio resolver
        serie = [v for d in por_dia for jj, v in por_dia[d].items() if jj == j and v > 0]
        if len(serie) < 5:
            ult = sorted(ab.datas)[-60:]
            serie += [b for b in (ab.valor(d, j) for d in ult) if isinstance(b, (int, float)) and b > 0]
        tipico[j] = statistics.median(serie) if len(serie) >= 5 else None

    novos = {}
    formulas = collections.defaultdict(list)
    outra_fonte = collections.defaultdict(list)
    menores = collections.defaultdict(list)
    for d in sorted(por_dia):
        linha = ab.datas[d]
        dia = por_dia[d]
        inv = {j: v for j, v in dia.items() if tipo[j] == "inversor"}
        # o 0 que o leitor confirmou (contador total parado no dia: a usina não gerou) é leitura, não falta de leitura
        if len(inv) >= 2 and all(v == 0 for v in inv.values()) and not all((d, j) in confirmados for j in inv):
            vazios = [j for j in inv if vazio(ab.valor(d, j))]
            if vazios:
                avisos.append(Aviso("leve", "%s: todos os inversores em 0 no arquivo — ficou fora; se a usina parou "
                                    "mesmo, digite os 0 à mão" % br(d), ab.nome, destino))
                cont["fora"] += len(vazios)
            inv = {}
            dia = {j: v for j, v in dia.items() if tipo[j] != "inversor"}
        # "menor" que acusa coluna trocada é mais de 1% abaixo do BD: 0,1 kWh de arredondamento do portal não conta
        trocadas = [j for j, v in inv.items() if isinstance(ab.valor(d, j), (int, float))
                    and v < ab.valor(d, j) * (1 - MAIS_QUE) - 0.01]
        for j, v in sorted(dia.items()):
            b = ab.valor(d, j)
            nome = ab.cab[j]
            if formula(b):
                formulas[j].append(d)
                continue
            if tipo[j] in ETM_MAX and not (0 <= v <= ETM_MAX[tipo[j]]):
                avisos.append(Aviso("severo", "%s %s: %g kWh/m² fora do possível num dia — ficou fora (unidade "
                                    "errada?)" % (br(d), nome, v), ab.nome, destino))
                cont["fora"] += 1
                continue
            if tipo[j] == "temperatura" and not (-5 <= v <= TEMP_MAX):
                avisos.append(Aviso("severo", "%s %s: %g °C fora do possível — ficou fora" % (br(d), nome, v),
                                    ab.nome, destino))
                cont["fora"] += 1
                continue
            if v < 0:
                cont["fora"] += 1
                avisos.append(Aviso("severo", "%s %s: valor negativo (%g) — ficou fora" % (br(d), nome, v),
                                    ab.nome, destino))
                continue
            t = tipico.get(j)
            # "fora do padrão" é o inversor que foge da coluna E dos outros inversores do mesmo dia: o contador
            # acumulado é de um só (Carosa 10/10: 6.668,2 com os outros em 0). Dia de sol forte depois de semanas de
            # nuvem sobe todos juntos e é dado bom (Aparecida do Taboado 1 e 2, 01/11/2026: ~575 e ~720 kWh, 1,9x a
            # mediana do mês, contador total fechando com o diário)
            irmaos = [x for jj, x in inv.items() if jj != j and x > 0]
            dia_tip = statistics.median(irmaos) if len(irmaos) >= 2 else 0
            fora = (tipo[j] == "inversor" and t and t > 50 and v > FORA_DO_PADRAO * t
                    and not (dia_tip and v <= FORA_DO_PADRAO * dia_tip))
            if vazio(b):
                if fora:
                    cont["fora"] += 1
                    avisos.append(Aviso("severo", "%s %s: %.1f kWh, %.1fx o típico da coluna (%.0f) — provável "
                                        "contador acumulado; ficou fora, confira no portal" % (br(d), nome, v, v / t, t),
                                        ab.nome, destino))
                    continue
                novos[(linha, j)] = (v, False, notas.get((d, j)))
                cont["novo"] += 1
            elif isinstance(b, (int, float)):
                if abs(v - b) <= _tol(b):
                    cont["igual"] += 1
                elif v > b * (1 + MAIS_QUE) + 0.01:
                    if (d, j) in so_vazio:
                        cont["so_vazio"] += 1
                        continue
                    if trocadas and j in inv:
                        cont["trocadas"] += 1
                        continue
                    if not _mesma_fonte(ab, por_dia, d, j):
                        cont["outra_fonte"] += 1
                        outra_fonte[j].append(d)
                        continue
                    if fora:
                        cont["fora"] += 1
                        avisos.append(Aviso("severo", "%s %s: o BD tem %g e o arquivo %.1f (%.1fx o típico) — ficou "
                                            "fora, confira no portal" % (br(d), nome, b, v, v / t), ab.nome, destino))
                        continue
                    novos[(linha, j)] = (v, True, notas.get((d, j)))
                    cont["troca"] += 1
                    avisos.append(Aviso("info", "%s %s: troca %g por %g (dia parcial no BD)" % (br(d), nome, b, v),
                                        ab.nome, destino))
                elif v > b:
                    cont["quase"] += 1
                else:
                    cont["menor"] += 1
                    menores[j].append(d)
            else:
                cont["texto"] += 1
                avisos.append(Aviso("leve", "%s %s: o BD tem o texto %r — não troquei (arquivo: %g)"
                                    % (br(d), nome, b, v), ab.nome, destino))
        if trocadas and any(j in inv and isinstance(ab.valor(d, j), (int, float)) and
                            v > ab.valor(d, j) * (1 + MAIS_QUE) + 0.01 for j, v in inv.items()):
            avisos.append(Aviso("severo", "%s: no mesmo dia uns inversores vêm maiores e outros menores que o BD "
                                "(%s menor) — parece coluna trocada; não troquei nada nesse dia"
                                % (br(d), ", ".join(ab.cab[j] for j in trocadas[:3])), ab.nome, destino))
    for j, ds in formulas.items():
        avisos.append(Aviso("info", "%s: %d dia(s) com fórmula no BD (%s a %s) — não troquei"
                            % (ab.cab[j], len(ds), ds[0].strftime("%d/%m"), ds[-1].strftime("%d/%m")),
                            ab.nome, destino))
    if outra_fonte:
        ds = sorted({d for x in outra_fonte.values() for d in x})
        avisos.append(Aviso("leve", "%d valor(es) maiores que o BD em %s não entraram: nos dias vizinhos o BD não bate "
                            "com este arquivo (o BD parece vir de outra fonte nesses dias) — confira antes de trocar à "
                            "mão" % (cont["outra_fonte"], _faixa_datas(ds)), ab.nome, destino))
    if menores:
        ds = sorted({d for x in menores.values() for d in x})
        avisos.append(Aviso("info", "%d valor(es) do arquivo menores que o BD (%s) — ficou o do BD (0 nunca cobre dado)"
                            % (cont["menor"], _faixa_datas(ds)), ab.nome, destino))
    return novos, cont, fontes, por_dia, notas


def _faixa_datas(ds):
    if not ds:
        return "-"
    if len(ds) <= 3:
        return ", ".join(d.strftime("%d/%m") for d in ds)
    return "%d dias de %s a %s" % (len(ds), ds[0].strftime("%d/%m"), ds[-1].strftime("%d/%m"))


def _mesma_fonte(ab, por_dia, d, j, raio=7):
    """Troca pelo "maior" só faz sentido se o BD e o arquivo medem a MESMA coisa: nos dias vizinhos (d±7) em que os
    dois têm número, a maioria tem de bater. Caso que criou a regra (10/11/2026): na Hortina, de 28/10 em diante o BD
    vem 5-10% ACIMA do portal todo dia (outra fonte); só no 29/10 o portal vinha maior — trocar só esse dia deixaria a
    coluna com duas fontes misturadas. Sem vizinho para comparar, vale a regra simples (é o caso do dia parcial
    isolado da API)."""
    iguais = tot = 0
    for k in range(-raio, raio + 1):
        if k == 0:
            continue
        dd = d + dt.timedelta(days=k)
        v = por_dia.get(dd, {}).get(j)
        b = ab.valor(dd, j)
        if v is None or not isinstance(b, (int, float)) or b == 0:
            continue
        if v > b * (1 + MAIS_QUE):              # vizinho também parcial no BD: não diz nada sobre a fonte
            continue
        tot += 1
        iguais += abs(v - b) <= max(_tol(b), abs(b) * MAIS_QUE)
    return tot < 3 or iguais / tot >= 0.6


_ESTADOS = {"novo": ("entra", "entram"), "troca": ("troca dia parcial", "trocam dia parcial"),
            "igual": ("já igual no BD", "já iguais no BD"),
            "mantido": ("ficou com o valor do BD", "ficaram com o valor do BD"),
            "fora": ("ficou fora", "ficaram fora"), "formula": ("é fórmula no BD", "são fórmula no BD")}


def _conferencia(ab, por_dia, novos, max_linhas=500, notas=None):
    """Todas as células que o arquivo trouxe, com o que aconteceu com cada uma — para a tela MOSTRAR e FALAR, também
    quando não há nada a colar (Levi, 10/11/2026: "mas é bom mostrar as células e falar"; 4 relatórios da Santarém 1B
    deram só "nada a colar · 36 já iguais")."""
    cols = sorted({j for d in por_dia for j in por_dia[d]})
    linhas, conta = [], collections.Counter()
    for d in sorted(por_dia)[:max_linhas]:
        r = ab.datas[d]
        cel = []
        for j in cols:
            v = por_dia[d].get(j)
            b = ab.valor(d, j)
            if v is None:
                cel.append({"v": None, "e": "", "bd": None})
                continue
            if (r, j) in novos:
                e = "troca" if novos[(r, j)][1] else "novo"
            elif formula(b):
                e = "formula"
            elif isinstance(b, (int, float)) and (abs(v - b) <= max(_tol(b), abs(b) * MAIS_QUE)):
                e = "igual"
            elif vazio(b):
                e = "fora"
            else:
                e = "mantido"
            conta[e] += 1
            bd = b if isinstance(b, (int, float)) else (None if vazio(b) else str(b))
            # observação de status do leitor (ETM com buraco: "parcial: buraco das 04:25 às 10:10") — o dado aparece e
            # a observação vai junto (Levi, 11/11/2026: "o ideal não seria descartar o dia e sim só sinalizar")
            cel.append({"v": round(v, 4), "e": e, "bd": bd, "novo": e in ("novo", "troca"),
                        "obs": (notas or {}).get((d, j))})
        linhas.append({"data": br(d), "cel": cel})
    n = sum(conta.values())
    partes = ["%d %s" % (conta[k], t[conta[k] > 1]) for k, t in _ESTADOS.items() if conta[k]]
    if conta["igual"] == n and n:
        resumo = "Nada a colar: os %d valores do arquivo já estão iguais no BD." % n
    else:
        resumo = "%d valores do arquivo: %s." % (n, ", ".join(partes))
    return {"cab": [ab.cab[j] for j in cols], "linhas": linhas, "resumo": resumo, "conta": dict(conta),
            "cortado": len(por_dia) > max_linhas}


def area(ab, por_dia):
    """Todas as células que o arquivo trouxe (dia fechado, com linha no BD), menos as que são fórmula no BD: é o que o
    bloco cobre. Levi, 10/11/2026: "o excel gerado tem que ser com todos os dados por dia, inclusive o que já está
    certo" — antes o bloco cobria só as células novas e o dia que já estava igual no BD nem aparecia."""
    return {(ab.datas[d], j) for d in por_dia for j in por_dia[d] if not formula(ab.valor(d, j))}


def blocos(ab, novos):
    """Retângulos sem fórmula que cobrem as células dadas (a `area` do arquivo): [(r1, r2, c1, c2)] (linhas do Excel,
    colunas 0-based). Dentro do retângulo, o que não é novo sai como cópia do BD."""
    if not novos:
        return []
    rows = [r for r, _ in novos]
    cols = [c for _, c in novos]
    r1, r2, c1, c2 = min(rows), max(rows), min(cols), max(cols)

    def tem_formula(r, c):
        x = ab.linhas.get(r, ())
        return c < len(x) and formula(x[c])

    sujas = {c for c in range(c1, c2 + 1) if any(tem_formula(r, c) for r in range(r1, r2 + 1))}
    out = []
    run = []
    for c in list(range(c1, c2 + 1)) + [None]:
        if c is None or c in sujas:
            if run:
                nr = [(r, cc) for (r, cc) in novos if cc in run]
                if nr:
                    rr = [r for r, _ in nr]
                    cc_ = [cc for _, cc in nr]
                    out.append((min(rr), max(rr), min(cc_), max(cc_)))
            run = []
        else:
            run.append(c)
    for c in sorted(sujas):                        # coluna com fórmula E valor novo: um bloco por trecho sem fórmula
        lin = sorted(r for r, cc in novos if cc == c)
        seg = []
        for r in lin:
            if seg and any(tem_formula(x, c) for x in range(seg[-1] + 1, r)):
                out.append((seg[0], seg[-1], c, c))
                seg = []
            seg.append(r)
        if seg:
            out.append((seg[0], seg[-1], c, c))
    return sorted(out, key=lambda b: (b[2], b[0]))


_PROIBIDO = re.compile(r"[\[\]:*?/\\]")


def _nome_aba(nome, usados):
    base = _PROIBIDO.sub("-", nome)[:31]
    n, k = base, 2
    while n in usados:
        suf = " (%d)" % k
        n, k = base[:31 - len(suf)] + suf, k + 1
    usados.add(n)
    return n


def _escrever(wb, nome_aba, destino, bd, ab, bls, novos, usados):
    ws = wb.create_sheet(_nome_aba(nome_aba, usados))
    ws["A1"] = "%s · aba \"%s\"" % (destino, ab.nome)
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = ("Como colar: selecione o bloco (vem selecionado o primeiro), Ctrl+C; no %s, aba \"%s\", clique na "
                "célula indicada e Ctrl+V. Amarelo = valor novo. O resto do bloco é cópia do que o BD já tem: colar "
                "não muda mais nada. O bloco traz todos os dias do arquivo, também os que já estão certos no BD."
                % (destino, ab.nome) + ("" if novos else " Nada novo nesta aba: tudo o que veio já está igual no BD."))
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 48
    lin, primeiro, info = 4, None, []
    larg = 1
    for k, (r1, r2, c1, c2) in enumerate(bls, 1):
        est = bd.estilos(ab.nome, r1, r2, c1, c2)
        alvo = "%s%d" % (L(c1 + 1), r1)
        d1 = next((d for d, n in ab.datas.items() if n == r1), None)
        ws.cell(lin, 1, "Bloco %d de %d — colar na célula %s do BD (linha de %s, coluna \"%s\")"
                % (k, len(bls), alvo, br(d1), ab.cab[c1])).font = Font(bold=True)
        lin += 1
        for jj, c in enumerate(range(c1, c2 + 1), 2):
            h = ws.cell(lin, jj, ab.cab[c])
            h.font = Font(bold=True)
            h.fill = CINZA
            h.alignment = Alignment(wrap_text=True)
        ws.cell(lin, 1, "Data").font = Font(bold=True)
        ws.cell(lin, 1).fill = CINZA
        lin += 1
        top = lin
        datas_por_linha = {n: d for d, n in ab.datas.items()}
        for r in range(r1, r2 + 1):
            d = datas_por_linha.get(r)
            ws.cell(lin, 1, d).number_format = "dd/mm/yyyy"
            linha_bd = ab.linhas.get(r, ())
            for jj, c in enumerate(range(c1, c2 + 1), 2):
                fmt, fill, fonte = est.get((r, c), ("General", None, None))
                if (r, c) in novos:
                    v = round(novos[(r, c)][0], 4)
                    cel = ws.cell(lin, jj, v)
                    cel.fill = PatternFill("solid", fgColor=AMARELO)
                    if len(novos[(r, c)]) > 2 and novos[(r, c)][2]:
                        cel.comment = Comment(novos[(r, c)][2], "Conversor Grid Co.")
                else:
                    v = linha_bd[c] if c < len(linha_bd) else None
                    cel = ws.cell(lin, jj, v)
                    if fill:
                        cel.fill = PatternFill("solid", fgColor=fill)
                    if fonte:
                        cel.font = Font(color=fonte)
                cel.number_format = fmt or "General"
            lin += 1
        faixa = "B%d:%s%d" % (top, L(c2 - c1 + 2), lin - 1)
        primeiro = primeiro or faixa
        info.append({"bloco": k, "colar_em": alvo, "faixa": faixa, "de": d1,
                     "ate": datas_por_linha.get(r2), "colunas": "%s a %s" % (ab.cab[c1], ab.cab[c2])})
        larg = max(larg, c2 - c1 + 2)
        lin += 2
    ws.column_dimensions["A"].width = 12
    for j in range(2, larg + 1):
        ws.column_dimensions[L(j)].width = 13
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(larg, 8))
    if primeiro:
        ws.sheet_view.selection[0].activeCell = primeiro.split(":")[0]
        ws.sheet_view.selection[0].sqref = primeiro
    return ws, info


def _previa(ab, bls, novos, max_linhas=500, max_cols=80):
    """A prévia é o bloco INTEIRO (todos os blocos da aba): na tela a pessoa clica numa célula para copiar ou arrasta
    para copiar várias (Levi, 10/11/2026) — prévia cortada não serviria para isso."""
    return {"blocos": [_previa_bloco(ab, bl, novos, max_linhas, max_cols) for bl in bls]}


def _previa_bloco(ab, bl, novos, max_linhas, max_cols):
    r1, r2, c1, c2 = bl
    c2v = min(c2, c1 + max_cols - 1)
    datas = {n: d for d, n in ab.datas.items()}
    linhas = []
    for r in range(r1, min(r2, r1 + max_linhas - 1) + 1):
        x = ab.linhas.get(r, ())
        cel = []
        for c in range(c1, c2v + 1):
            if (r, c) in novos:
                cel.append({"v": round(novos[(r, c)][0], 4), "novo": True,
                            "obs": novos[(r, c)][2] if len(novos[(r, c)]) > 2 else None})
            else:
                v = x[c] if c < len(x) else None
                cel.append({"v": v if isinstance(v, (int, float)) else (None if vazio(v) else str(v)), "novo": False})
        linhas.append({"data": br(datas.get(r)), "cel": cel})
    return {"cab": [ab.cab[c] for c in range(c1, c2v + 1)], "linhas": linhas,
            "colar_em": "%s%d" % (L(c1 + 1), r1), "cortado": c2 > c2v or r2 - r1 + 1 > max_linhas}


_ORDEM_SOLTA = ("IPOA", "GHI", "Temperatura", "ETM1", "ETM2")


def _separar_soltas(vals):
    """Tira de `vals` o que não tem lugar certo no BD: aba "Sem usina · ..." e canal ETM1/ETM2. Devolve
    {(destino, rótulo): {(data, coluna): (valor, fonte, so_vazio)}}."""
    soltas = collections.defaultdict(dict)
    for (destino, aba) in list(vals):
        for (d, col), x in list(vals[(destino, aba)].items()):
            if aba.startswith(SEM_USINA):
                soltas[(destino, aba)][(d, col)] = x
            elif col in ETM_SOLTAS:
                soltas[(destino, "%s · ETM sem canal" % aba)][(d, col)] = x
            else:
                continue
            del vals[(destino, aba)][(d, col)]
        if not vals[(destino, aba)]:
            del vals[(destino, aba)]
    return soltas


def _escrever_solta(wb, rotulo, destino, vals, hoje, usados):
    """Aba da planilha com os valores por dia, sem comparar com o BD (usina ou canal desconhecido). Tudo em amarelo:
    é valor que a pessoa cola à mão."""
    cols = sorted({c for (_, c) in vals}, key=lambda c: (_ORDEM_SOLTA.index(c) if c in _ORDEM_SOLTA else 99, c))
    dias = sorted({d for (d, _) in vals if d < hoje})
    ws = wb.create_sheet(_nome_aba(rotulo, usados))
    ws["A1"] = rotulo
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = ("Não sei em que aba do %s isto entra%s: os valores vão por dia, sem comparar com o BD. Confira e "
                "cole à mão na aba certa." % (destino, " (canal sem nome de POA ou GHI)" if "ETM sem canal" in rotulo
                                              else ""))
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 32
    for j, t in enumerate(["Data"] + cols, 1):
        h = ws.cell(4, j, t)
        h.font = Font(bold=True)
        h.fill = CINZA
    linhas = []
    for i, d in enumerate(dias, 5):
        ws.cell(i, 1, d).number_format = "dd/mm/yyyy"
        cel = []
        for j, c in enumerate(cols, 2):
            x = vals.get((d, c))
            v = round(x[0], 4) if x else None
            obs = x[4] if x and len(x) > 4 else None          # observação do leitor (dia incompleto etc.)
            if v is not None:
                k = ws.cell(i, j, v)
                k.fill = PatternFill("solid", fgColor=AMARELO)
                k.number_format = "0.00" if c == "Temperatura" else "0.000"
                if obs:
                    k.comment = Comment(obs, "Conversor Grid Co.")
            cel.append({"v": v, "novo": v is not None, "obs": obs})
        linhas.append({"data": br(d), "cel": cel})
    ws.column_dimensions["A"].width = 12
    for j in range(2, len(cols) + 2):
        ws.column_dimensions[L(j)].width = 13
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(len(cols) + 1, 8))
    if dias:
        ws.sheet_view.selection[0].activeCell = "B5"
        ws.sheet_view.selection[0].sqref = "B5:%s%d" % (L(len(cols) + 1), len(dias) + 4)
    n = sum(1 for l in linhas for c in l["cel"] if c["novo"])
    previa = {"blocos": [{"cab": cols, "linhas": linhas, "colar_em": "à mão", "cortado": False}]}
    return dias, n, previa


def montar(celulas, ctx, pasta, carimbo=None, avisos=None):
    """celulas: [(Celula, fonte)]. Grava uma planilha por BD de destino em `pasta`. Devolve o resultado para a tela."""
    avisos = list(avisos or [])
    carimbo = carimbo or dt.datetime.now()
    vals = _juntar(celulas, avisos)
    soltas = _separar_soltas(vals)
    por_destino = collections.defaultdict(list)
    for (destino, aba) in sorted(vals):
        por_destino[destino].append(aba)
    for (destino, _) in soltas:
        por_destino.setdefault(destino, [])
    tabela, saidas, previas = [], [], {}
    tot = collections.Counter()
    os.makedirs(pasta, exist_ok=True)
    for destino, abas in por_destino.items():
        bd = ctx.bd(destino)
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        usados = set()
        for (dest2, rotulo), sv in sorted(soltas.items()):
            if dest2 != destino:
                continue
            dias, n, prev = _escrever_solta(wb, rotulo, destino, sv, ctx.hoje, usados)
            fontes_s = sorted({x[1] for x in sv.values()})
            tot["novo"] += n
            tabela.append({"aba": rotulo, "destino": destino, "fonte": ", ".join(fontes_s),
                           "bloco": "%s a %s" % (dias[0].strftime("%d/%m"), dias[-1].strftime("%d/%m")) if dias else "-",
                           "colar_em": "à mão", "dias": len(dias), "celulas": n, "trocas": 0, "fora": 0,
                           "situacao": "sem_usina"})
            if dias:
                previas["%s|%s" % (destino, rotulo)] = prev
        if bd is None and abas:
            avisos.append(Aviso("erro", "%s não foi lido — não dá para montar o bloco sem saber o que já está "
                                "preenchido. Aponte o arquivo no topo da tela e converta de novo." % destino,
                                None, destino))
            for aba in abas:
                tabela.append({"aba": aba, "destino": destino, "fonte": "", "bloco": "-", "colar_em": "-",
                               "dias": 0, "celulas": 0, "trocas": 0, "fora": 0, "situacao": "erro"})
            abas = []
        for aba in abas:
            ab = bd.aba(aba)
            fontes_aba = sorted({x[1] for x in vals[(destino, aba)].values()})
            if ab is None:
                avisos.append(Aviso("erro", "a aba não existe no %s" % destino, aba, destino))
                tabela.append({"aba": aba, "destino": destino, "fonte": ", ".join(fontes_aba), "bloco": "-",
                               "colar_em": "-", "dias": 0, "celulas": 0, "trocas": 0, "fora": 0, "situacao": "erro"})
                continue
            novos, cont, _, por_dia, notas = _classificar(ab, vals[(destino, aba)], ctx.hoje, avisos, destino)
            conf = _conferencia(ab, por_dia, novos, notas=notas) if por_dia else None
            bls = blocos(ab, area(ab, por_dia))
            tot["novo"] += cont["novo"] + cont["troca"]
            tot["troca"] += cont["troca"]
            tot["fora"] += cont["fora"]
            if not bls:
                tabela.append({"aba": aba, "destino": destino, "fonte": ", ".join(fontes_aba), "bloco": "-",
                               "colar_em": "-", "dias": 0, "celulas": 0, "trocas": 0, "fora": cont["fora"],
                               "situacao": "nada", "iguais": cont["igual"]})
                if conf:
                    previas["%s|%s" % (destino, aba)] = {"blocos": [], "conferencia": conf}
                continue
            _, info = _escrever(wb, aba, destino, bd, ab, bls, novos, usados)
            dias = {r for r, _ in novos}
            de, ate = min(i["de"] for i in info if i["de"]), max(i["ate"] for i in info if i["ate"])
            if not novos:
                sit = "nada"                     # o bloco vai para a planilha (conferência), mas não muda nada no BD
            elif any(a["aba"] == aba and a["nivel"] in ("severo", "erro") for a in avisos):
                sit = "conferir"
            else:
                sit = "pronto"
            tabela.append({"aba": aba, "destino": destino, "fonte": ", ".join(fontes_aba),
                           "bloco": "%s a %s" % (de.strftime("%d/%m"), ate.strftime("%d/%m")),
                           "colar_em": ", ".join(i["colar_em"] for i in info), "blocos": len(info),
                           "dias": len(dias), "celulas": cont["novo"] + cont["troca"], "trocas": cont["troca"],
                           "fora": cont["fora"], "iguais": cont["igual"], "situacao": sit})
            previas["%s|%s" % (destino, aba)] = dict(_previa(ab, bls, novos), conferencia=conf)
        if not wb.sheetnames:
            continue
        av = wb.create_sheet("Avisos")
        av["A1"] = "Avisos (o que pede atenção antes de colar)"
        av["A1"].font = Font(bold=True, size=12)
        for j, t in enumerate(("Nível", "Aba", "Aviso"), 1):
            av.cell(3, j, t).font = Font(bold=True)
        n = 4
        for a in avisos:
            if a["destino"] in (destino, None):
                av.cell(n, 1, a["nivel"])
                av.cell(n, 2, a["aba"] or "")
                av.cell(n, 3, a["texto"])
                n += 1
        av.column_dimensions["A"].width = 9
        av.column_dimensions["B"].width = 26
        av.column_dimensions["C"].width = 120
        wb.active = 0
        caminho = os.path.join(pasta, "Para colar no %s - %s.xlsx" % (destino, carimbo.strftime("%d-%m %Hh%M")))
        wb.save(caminho)
        saidas.append({"destino": destino, "caminho": caminho, "abas": len(wb.sheetnames) - 1})
    tot["abas"] = sum(1 for t in tabela if t["celulas"])
    return {"tabela": tabela, "saidas": saidas, "previas": previas, "avisos": avisos, "totais": dict(tot)}
