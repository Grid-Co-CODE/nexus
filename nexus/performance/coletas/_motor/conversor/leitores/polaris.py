# -*- coding: utf-8 -*-
"""Usinas Polaris e Canarana 1 -> BD_Thopen. Veio da coleta manual de outubro/2026 (scratchpad pol0311, pol0411 e
can3010: le_diario.py, etm_pol.py, plano.py, plano2.py; memória depara-relatorio-mensal-fusion-thopen, "Lote de 03/11").
As regras de colar (vazio ou a mais, 0 nunca por cima, fórmula intocada, fora do padrão fora) são as do núcleo.

Três formatos, reconhecidos pelo CONTEÚDO:

1. Relatório de inversor diário do portal ("Relatório de inversor_DD-MM[-AAAA][ (n)].xlsx"): título "Relatório de
   inversor" e o cabeçalho "Nome da instalação | Nome do dispositivo | Capacidade total da cadeia (kWp) | Rendimento
   (kWh) | Rendimento total (kWh) | ...", uma linha por inversor e UM dia. O relatório NÃO traz a data por dentro
   (conferido nos 61 arquivos de 29-31/10/2026): a data é a do nome. Por isso a conferência é de ano: os da Santo Inácio
   XII do lote de 03/11 vieram "_29-10-2025" (o portal estava no ano errado) — relatório de mais de um ano antes de hoje
   vira aviso, não célula. Nome sem ano ("_29-10") = o último 29/10 antes de hoje. Se um dia o relatório trouxer uma
   coluna de data, ela vale e tem de bater com o nome.
   - Polaris: o número do dispositivo é o número da coluna (INV-01, INVERSOR_01, Inversor_08, "8", "Inv04 - S/N...",
     Inverter08), conferido ao centavo em 29/10/2026. A coluna sai do cabeçalho da aba: "Inversor 2.N" na BES B e na
     Santarém 1B (abas com 2.x), "Inversor N" na Aparecida 3 e na Ibaté 1. Caxambu "Inverter(MBUS-2)" = 1.2 (o 02 que
     falta). "MBUS-N" em outra usina fica fora: N é o endereço Modbus, não o inversor (na Canarana 1 o MBUS-19 é o 1.6).
   - Canarana 1: um arquivo por dia, dispositivo pelo S/N (a aba Equipamentos só diz INVERSOR0N = 1.N, sem S/N), de-para
     de 30/10/2026 na memória, casado pela geração em 05/10 (7 de 8 a 0,996 do portal): ver CANARANA_SN.
2. ETM das usinas Polaris ("<USINA> ETM.csv"; a da Aparecida do Taboado 1 e 2 vem em partes "1 (5).csv", "2 (4).csv"...
   numa pasta "APARECIDA DO TABOADO 1 E 2 ETM"), em W/m² minuto a minuto, para IPOA e GHI (kWh/m²):
   - supervisório: "Nome do data point,Tempo,Valor,Processado,Comentário", pontos "<ESTAÇÃO> - Irradiação_Inclinada"
     (IPOA) e "..._Horizontal" (GHI), ponto decimal;
   - datalogger: "RECORD;DATE;TIME;...", vírgula decimal: RAD_POA_MED / RAD_GHI_TORRE_MED (Aparecida do Taboado — a
     ETM do PG da OEM está errada e a coleta não grava, regra 13 do CLAUDE.md da coleta: é colada à mão, o caso deste
     app), Irrad_SR20_POA_MED / _GHI_MED (Boa Esperança), Irrad_SR05_POA_ACT / _GHI_ACT (Santo Inácio XII). POA_REAR
     (verso do bifacial) nunca é o IPOA.
   Usina pelo nome do arquivo, depois o da pasta, depois o prefixo da estação no supervisório (APA03, ASB01...). Uma
   estação serve às duas abas da mesma usina (Araçoiaba, Boa Esperança, Santarém, Aparecida do Taboado), como no lote
   de 03/11. Regra do dia (etm_pol.py, que é a regra 13 da coleta) em _fechar_dia.
3. Relatório da instalação do portal ("Relatório da instalação_<USINA>_MM-AAAA"): "Tempo estatístico | ... |
   Irradiação global (kWh/m²) | ... | Rendimento PV (kWh) | ...", um dia por linha. Só duas usinas têm regra, ambas
   conferidas contra o BD no lote de 03/11: Vargem Grande 1 (no portal "UFV VARGEM GRANDE 1B") -> Energia Produzida =
   "Rendimento PV" (a aba não tem coluna de inversor; valor, não fórmula); Rondonópolis -> IPOA = "Irradiação global".
   Outra usina nesse formato vira aviso: sem prova, não se adivinha se a irradiação global é POA ou GHI.
"""
import csv
import datetime as dt
import difflib
import io
import os
import re
import statistics

from conversor.nucleo import (BD_THOPEN, SEM_USINA, Arquivo, Celula, Leitor, Reconhecimento, br, data_de, norm,
                              num)

# ------------------------------------------------------------------------------------------------ usinas
# Nome no portal (normalizado) -> aba do BD_Thopen. Do le_diario.py de 03/11/2026, conferido ao centavo em 29/10: os
# nomes não casam sozinhos (romano I/II, "IA/IB" e "A/B" = 1/2, "1A/1B" = 1/2, "SALTO DO PIRAPORA" = Salto Pirapora 3).
PLANTA = {
    "ufv aparecida iii": "Aparecida 3",
    "ufv aracoiaba da serra ia": "Araçoiaba da Serra 1",
    "ufv aracoiaba da serra ib": "Araçoiaba da Serra 2",
    "ufv bes boa esperanca do sul a": "Boa Esperança do Sul 1",
    "ufv bes boa esperanca do sul b": "Boa Esperança do Sul 2",
    "ufv caxambu i": "Caxambu",
    "ufv goytacazes": "Goytacazes 1",
    "ufv guaratingueta v": "Guaratinguetá V",
    "ufv ibate i": "Ibaté 1",
    "ufv ibate ii": "Ibaté 2",
    "ufv marajoara i": "Marajoara 1",
    "ufv piracicaba": "Piracicaba 1",
    "ufv salto do pirapora": "Salto Pirapora 3",
    "ufv santa barbara do oeste": "Santa Bárbara I",
    "ufv santarem 1a": "Santarém 1",
    "ufv santarem 1b": "Santarém 2",
    "ufv santo inacio xii": "Santo Inácio XII",
    "ufv sao bento v": "São Bento V",
    "canarana 1": "Canarana 1",
    "ufv vargem grande 1b": "Vargem Grande 1",
    "usina rondonopolis": "Rondonopolis",
}

# Uma estação, duas abas (plano.py de 03/11: o mesmo CSV colado nas duas; regra 13 da coleta para a Aparecida do
# Taboado: "colar em amarelo nas DUAS abas (a estação é a mesma)"). Só vale para ETM: o relatório de inversor é de uma.
ESTACAO_COMPARTILHADA = (
    ("Araçoiaba da Serra 1", "Araçoiaba da Serra 2"),
    ("Boa Esperança do Sul 1", "Boa Esperança do Sul 2"),
    ("Santarém 1", "Santarém 2"),
    ("Aparecida do Taboado 1", "Aparecida do Taboado 2"),
)

# Prefixo da estação no supervisório -> abas. Tirado dos CSVs de outubro (nome do arquivo x ponto): é a usina pelo
# conteúdo quando o nome do arquivo não diz ("SALTO DO PIRAPORA.csv" nem tem "ETM").
PREFIXO_SCADA = {
    "apa03": ("Aparecida 3",), "asb01": ("Araçoiaba da Serra 1", "Araçoiaba da Serra 2"),
    "slp03": ("Salto Pirapora 3",), "sbo01": ("Santa Bárbara I",), "str01": ("Santarém 1", "Santarém 2"),
    "cxb01": ("Caxambu",), "gys01": ("Goytacazes 1",), "gua05": ("Guaratinguetá V",), "ibt01": ("Ibaté 1",),
    "ibt02": ("Ibaté 2",), "mrj01": ("Marajoara 1",), "sbt05": ("São Bento V",),
}

# Canais do datalogger: (POA, GHI) -> abas que usam (só ordena a pergunta: o mesmo sensor pode existir em outra usina).
CANAIS_LOGGER = {
    ("rad_poa_med", "rad_ghi_torre_med"): ("Aparecida do Taboado 1", "Aparecida do Taboado 2"),
    ("irrad_sr20_poa_med", "irrad_sr20_ghi_med"): ("Boa Esperança do Sul 1", "Boa Esperança do Sul 2"),
    ("irrad_sr05_poa_act", "irrad_sr05_ghi_act"): ("Santo Inácio XII",),
}

# Abas com ETM nos lotes de 03 e 04/11 — as candidatas quando o nome do arquivo não diz a usina.
ETM_ABAS = ("Aparecida 3", "Aparecida do Taboado 1", "Aparecida do Taboado 2", "Araçoiaba da Serra 1",
            "Araçoiaba da Serra 2", "Boa Esperança do Sul 1", "Boa Esperança do Sul 2", "Caxambu", "Goytacazes 1",
            "Guaratinguetá V", "Ibaté 1", "Ibaté 2", "Marajoara 1", "Salto Pirapora 3", "Santa Bárbara I", "Santarém 1",
            "Santarém 2", "Santo Inácio XII", "São Bento V")

# Canarana 1 (memória depara-relatorio-mensal-fusion-thopen, 30/10/2026). O mapa.json de 30/10 10:04 tinha 1.1/1.2 e
# 1.5/1.6/1.8 trocados; os 40 valores gravados às 10:11 (e o BD de hoje) seguem esta tabela.
CANARANA_SN = {
    "6t2259009496y": "Inversor 1.1", "6t2258006940y": "Inversor 1.2", "inv.03": "Inversor 1.3",
    "6t2259010532": "Inversor 1.4", "6t2259010667": "Inversor 1.5", "inverter(mbus-19)": "Inversor 1.6",
    "6t2259006936y": "Inversor 1.7", "6t2259009511y": "Inversor 1.8",
}
# Dispositivo cujo nome não diz o número do inversor, por aba. Canarana 1: só a tabela vale (S/N); Caxambu: a tabela só
# para o MBUS-2, o resto pelo número (INVERSOR_01...).
DISPOSITIVO = {
    "Canarana 1": CANARANA_SN,
    "Caxambu": {"inverter(mbus-2)": "Inversor 1.2"},
}
# Sem o BD lido, o grupo das colunas de inversor (a aba é a fonte de verdade quando existe)
GRUPO_2 = ("Boa Esperança do Sul 2", "Santarém 2", "Aparecida do Taboado 2")

# Relatório da instalação: aba -> {coluna do relatório (normalizada, sem a unidade): coluna do BD}
INSTALACAO = {
    "Vargem Grande 1": {"rendimento pv": "Energia Produzida"},
    "Rondonopolis": {"irradiacao global": "IPOA"},
}
_NOME_COLUNA = {"rendimento pv": "Rendimento PV", "irradiacao global": "Irradiação global"}

ANO = 365            # relatório de inversor com mais de um ano é o portal no ano errado (Santo Inácio XII, 03/11)

_ROMANO = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11,
           "xii": 12}
_RUIDO = {"ufv", "usina", "etm", "e", "do", "da", "de", "dos", "das", "csv", "xlsx", "xls", "txt"}


def _partes(s):
    """(palavras, números) de um nome: romano vira número; '1A', '1B', 'IA' ficam como palavra (não são '1'): no portal
    'SANTAREM 1B' é a Santarém 2 — casar pelo 1 erraria a usina em silêncio."""
    s = norm(s)
    s = re.sub(r"\(\d+\)", " ", s)                               # "(5)" da cópia do Windows
    s = re.sub(r"\.(csv|xlsx?|txt)$", " ", s)
    pal, nums = set(), set()
    for t in re.findall(r"[a-z0-9]+", s):
        if t.isdigit():
            nums.add(int(t))
        elif t in _ROMANO:
            nums.add(_ROMANO[t])
        elif t not in _RUIDO and len(t) > 1:
            pal.add(t)
    return pal, nums


def _casa(texto, aba):
    pt, nt = _partes(texto)
    pa, na = _partes(aba)
    if not pa or not pt:
        return False
    palavras = pa <= pt or pt <= pa
    numeros = not nt or not na or bool(na & nt)
    return palavras and numeros


def _parecido(texto, abas):
    """abas em ordem de semelhança com o texto (a melhor primeiro)."""
    t = " ".join(sorted(_partes(texto)[0]))
    return sorted(abas, key=lambda a: -difflib.SequenceMatcher(None, t, " ".join(sorted(_partes(a)[0]))).ratio())


def _abas(ctx):
    return ctx.abas(BD_THOPEN) or sorted(set(PLANTA.values()) | set(ETM_ABAS))


def _achar(nome, abas):
    """o nome da aba como está no BD (ou None)."""
    n = norm(nome)
    return next((a for a in abas if norm(a) == n), None)


def _estacao(sel, abas):
    """abas escolhidas + a outra aba da mesma estação."""
    out = []
    for a in sel:
        grupo = next((g for g in ESTACAO_COMPARTILHADA if norm(a) in {norm(x) for x in g}), (a,))
        for x in grupo:
            x = _achar(x, abas) or (x if not abas else None)
            if x and x not in out:
                out.append(x)
    return out


def _planta(nome, abas):
    """(aba ou None, candidatas) para o nome da instalação de um relatório."""
    k = norm(nome)
    if k in PLANTA:
        a = _achar(PLANTA[k], abas)
        if a:
            return a, []
    achou = [a for a in abas if _casa(nome, a)]
    if len(achou) == 1:
        return achou[0], []
    return None, _parecido(nome, achou or abas)[:8]


# ------------------------------------------------------------------------------------------------ relatório de inversor
_DATA_NOME = re.compile(r"(?<!\d)(\d{1,2})-(\d{1,2})(?:-(\d{4}))?(?!\d)")
_NUM_DISP = re.compile(r"^(?:inv(?:ersor|erter)?)?[\s_.\-]*0*(\d{1,3})(?=$|[\s_.\-])")


def _data_do_nome(nome, hoje):
    """date do 'Relatório de inversor_DD-MM[-AAAA]' (sem ano = o último DD/MM antes de hoje) ou None."""
    n = norm(nome)
    m = re.search(r"inversor_(\d{1,2})-(\d{1,2})(?:-(\d{4}))?(?!\d)", n) or _DATA_NOME.search(n)
    if not m:
        return None
    d, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        if ano:
            return dt.date(int(ano), mes, d)
        x = dt.date(hoje.year, mes, d)
        return x if x < hoje else dt.date(hoje.year - 1, mes, d)
    except ValueError:
        return None


def _numero(dev):
    m = _NUM_DISP.match(norm(dev))
    n = int(m.group(1)) if m else 0
    return n or None


def _tabela_inversor(arq):
    """[(instalação, dispositivo, rendimento cru, data da linha ou None)] ou None se não for o relatório de inversor."""
    if arq.ext not in (".xlsx", ".xlsm", ".xls"):
        return None
    for _, linhas in arq.planilhas():
        for i, r in enumerate(linhas[:8]):
            h = [norm(x) for x in r]
            if "nome da instalacao" not in h or "nome do dispositivo" not in h or "rendimento (kwh)" not in h:
                continue
            iu, idv, ir = h.index("nome da instalacao"), h.index("nome do dispositivo"), h.index("rendimento (kwh)")
            idt = next((j for j, x in enumerate(h) if x.startswith(("tempo", "horario", "data"))), None)
            out = []
            for r2 in linhas[i + 1:]:
                x = list(r2) + [None] * (len(h) - len(r2))            # linha curta do portal: o que falta é vazio
                if x[iu] is None or not str(x[iu]).strip():
                    continue
                out.append((str(x[iu]).strip(), str(x[idv] or "").strip(), x[ir],
                            data_de(x[idt]) if idt is not None else None))
            return out
    return None


def _coluna_inversor(aba, n, ctx):
    """'Inversor G.N' ou 'Inversor N' pelo cabeçalho da aba (BES B e Santarém 1B = 2.N; Aparecida 3 e Ibaté 1 = N)."""
    ab = ctx.aba(BD_THOPEN, aba)
    if ab is None:
        return "Inversor %d.%d" % (2 if aba in GRUPO_2 else 1, n)
    grupos, simples = set(), {}
    for c in ab.colunas_inversor():
        x = norm(c).replace(",", ".")
        m = re.fullmatch(r"inversor (\d+)\.(\d+)", x)
        if m:
            grupos.add(int(m.group(1)))
            continue
        m = re.fullmatch(r"inversor (\d+)", x)
        if m:
            simples[int(m.group(1))] = c
    if simples and not grupos:
        return simples.get(n, "Inversor %d" % n)
    if len(grupos) == 1:
        return "Inversor %d.%d" % (grupos.pop(), n)
    return None                               # aba com vários grupos (1.x e 2.x): o número sozinho não diz a coluna


class RelatorioInversor(Leitor):
    id = "polaris_inversor"
    fonte = "Relatório de inversor diário (Polaris, Canarana)"
    destino = BD_THOPEN

    def reconhecer(self, arq, ctx):
        try:
            linhas = _tabela_inversor(arq)
        except Exception:                                  # arquivo de outro formato não derruba a tela
            return None
        if linhas is None:
            return None
        abas = _abas(ctx)
        mapa, cand = {}, []
        for planta in sorted({l[0] for l in linhas}):
            a, c = _planta(planta, abas)
            mapa[planta] = a
            if not a and not cand:
                cand = c
        dias = sorted({l[3] for l in linhas if l[3]})
        d = dias[0] if dias else _data_do_nome(arq.nome, ctx.hoje)
        usinas = sorted({a for a in mapa.values() if a})
        velho = " (mais de um ano: não entra)" if d and (ctx.hoje - d).days > ANO else ""
        rec = Reconhecimento(self.fonte, usinas=usinas, periodo=(d, dias[-1] if dias else d) if d else None,
                             estado={"linhas": linhas, "mapa": mapa},
                             detalhe="%d inversores · %s%s" % (len(linhas), br(d) if d else "sem data no nome", velho))
        sem = [p for p, a in mapa.items() if not a]
        if sem and not usinas:
            rec.candidatas = cand
            rec.pergunta = ("O relatório de inversor é da instalação %s, que não está no de-para da Polaris."
                            % ", ".join(repr(p) for p in sem[:3]))
        return rec

    def ler(self, arq, ctx, rec, escolha=None):
        linhas, mapa = rec.estado["linhas"], rec.estado["mapa"]
        avisos = []
        dnome = _data_do_nome(arq.nome, ctx.hoje)
        dias_dentro = {l[3] for l in linhas if l[3]}
        if dias_dentro:
            # a data de dentro vale; se o nome diz outra, o arquivo foi renomeado ou o portal estava em outro dia
            if dnome and dnome not in dias_dentro:
                return [], ["o nome diz %s e o relatório traz %s — confira no portal; nada entrou"
                            % (br(dnome), ", ".join(br(x) for x in sorted(dias_dentro)))]
        elif not dnome:
            return [], ["o relatório de inversor não traz a data e o nome do arquivo não tem DD-MM — renomeie para "
                        "\"Relatório de inversor_DD-MM-AAAA\" e converta de novo"]
        cel, vistos, sem_valor = [], {}, []
        for planta, dev, bruto, dlin in linhas:
            dia = dlin or dnome
            if (ctx.hoje - dia).days > ANO:
                if not any("mais de um ano" in a for a in avisos):
                    avisos.append("relatório de %s, mais de um ano antes de hoje — o portal estava no ano errado? (os "
                                  "da Santo Inácio XII de 03/11/2026 vieram de 2025). Nada entrou; baixe de novo no "
                                  "dia certo" % br(dia))
                continue
            aba = mapa.get(planta) or (escolha if not rec.usinas else None)
            if not aba:
                avisos.append("instalação %r fora do de-para — ficou de fora" % planta)
                continue
            tabela = DISPOSITIVO.get(aba)
            if tabela is not None and norm(dev) in tabela:
                col = tabela[norm(dev)]
            elif aba == "Canarana 1":
                avisos.append("%s: dispositivo %r fora do de-para por S/N — ficou de fora" % (aba, dev))
                continue
            else:
                n = _numero(dev)
                if not n:
                    extra = " (MBUS-N é o endereço Modbus, não o número do inversor)" if "mbus" in norm(dev) else ""
                    avisos.append("%s: dispositivo %r sem número de inversor reconhecível%s — ficou de fora"
                                  % (aba, dev, extra))
                    continue
                col = _coluna_inversor(aba, n, ctx)
                if not col:
                    avisos.append("%s: a aba tem inversores de vários grupos; %r não diz qual — ficou de fora"
                                  % (aba, dev))
                    continue
            v = num(bruto)
            if v is None:
                sem_valor.append((aba, col, dev))
                continue
            vistos.setdefault((aba, dia, col), []).append((dev, v))
        for (aba, dia, col), devs in sorted(vistos.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
            if len(devs) > 1:
                # dois dispositivos na mesma coluna: não dá para saber qual é o inversor de verdade
                avisos.append("%s %s: %s caem na mesma coluna %s — nenhum entrou"
                              % (aba, br(dia), " e ".join(repr(d) for d, _ in devs), col))
                continue
            cel.append(Celula(BD_THOPEN, aba, dia, col, devs[0][1]))
        # informativo, não amarelo: inversor sem rendimento no portal é inversor parado ou sem leitura, e a célula do BD
        # fica como está (Santarém 1B, 01-04/11/2026: o "7" vem vazio todo dia e o BD já tem 0 — eram 4 avisos
        # amarelos com "'7'" que ninguém entendia)
        for aba, col, dev in sem_valor:
            avisos.append(("info", "%s · %s (dispositivo %r): o relatório vem sem rendimento — a célula fica como está "
                                   "no BD (não vira 0)" % (aba, col, dev)))
        return cel, avisos


# ------------------------------------------------------------------------------------------------ relatório da instalação
def _tabela_instalacao(arq):
    """(nome da instalação, [(date, {coluna normalizada sem unidade: valor cru})]) ou None."""
    if arq.ext not in (".xlsx", ".xlsm", ".xls"):
        return None
    for _, linhas in arq.planilhas():
        titulo = next((str(r[0]) for r in linhas[:3] if r and r[0] and norm(r[0]).startswith("relatorio da instalacao")),
                      None)
        for i, r in enumerate(linhas[:8]):
            h = [norm(x) for x in r]
            if "tempo estatistico" not in h:
                continue
            cols = {re.sub(r"\s*\(.*$", "", x).strip(): j for j, x in enumerate(h) if x}
            if "rendimento pv" not in cols and "irradiacao global" not in cols:
                continue
            nome = titulo.split("_", 1)[1].strip() if titulo and "_" in titulo else ""
            it = cols["tempo estatistico"]
            dias = []
            for r2 in linhas[i + 1:]:
                d = data_de(r2[it]) if r2 and it < len(r2) else None
                if d:
                    dias.append((d, {k: (r2[j] if j < len(r2) else None) for k, j in cols.items()}))
            return nome, dias
    return None


class RelatorioInstalacao(Leitor):
    id = "polaris_instalacao"
    fonte = "Relatório da instalação (Vargem Grande 1, Rondonópolis)"
    destino = BD_THOPEN

    def reconhecer(self, arq, ctx):
        try:
            t = _tabela_instalacao(arq)
        except Exception:
            return None
        if t is None:
            return None
        nome, dias = t
        abas = _abas(ctx)
        a = _achar(PLANTA.get(norm(nome), ""), abas) if norm(nome) in PLANTA else None
        if not a:
            achou = [x for x in abas if _casa(nome, x) and x in INSTALACAO]
            a = achou[0] if len(achou) == 1 else None
        ds = [d for d, _ in dias]
        regra = INSTALACAO.get(a) if a else None
        det = (" · ".join("%s = %s" % (dest, _NOME_COLUNA[orig]) for orig, dest in regra.items()) if regra else
               "usina sem regra de colunas: %s" % (nome or "?"))
        return Reconhecimento(self.fonte, usinas=[a] if a else [], periodo=(min(ds), max(ds)) if ds else None,
                              estado={"nome": nome, "dias": dias, "aba": a}, detalhe=det)

    def ler(self, arq, ctx, rec, escolha=None):
        aba = rec.estado["aba"]
        regra = INSTALACAO.get(aba) if aba else None
        if not regra:
            return [], ["relatório da instalação de %r: só a Vargem Grande 1 (Rendimento PV) e a Rondonópolis "
                        "(Irradiação global = IPOA) têm regra conferida — nada entrou" % rec.estado["nome"]]
        cel, zeros = [], []
        for d, vals in rec.estado["dias"]:
            for orig, dest in regra.items():
                v = num(vals.get(orig))
                if v is None:
                    continue
                if v <= 0:
                    # irradiação <= 0 fica vazia (regra 12 da coleta); energia 0 da usina inteira é o portal sem
                    # leitura, como o dia de inversores todos em 0
                    zeros.append(d)
                    continue
                cel.append(Celula(BD_THOPEN, aba, d, dest, v))
        av = ["%s: %d dia(s) com 0 no relatório ficaram vazios (%s)" % (aba, len(zeros), ", ".join(
            x.strftime("%d/%m") for x in zeros[:6]))] if zeros else []
        return cel, av


# ------------------------------------------------------------------------------------------------ ETM
BURACO = 1800              # s: buraco maior que 30 min não se interpola
CONGELADO = 1800           # s: a mesma leitura (não zero) por mais de 30 min = supervisório repetindo o último valor
NOITE_MAX = 20.0           # W/m²: mediana da madrugada (00-04 h) acima disso = estação travada
CANAIS = ("IPOA", "GHI", "ETM1", "ETM2")


def _tira_congelado(p):
    """(p sem os trechos congelados, {início do trecho: motivo}). Fica a primeira leitura de cada trecho (ela era
    verdade naquele minuto); as repetições saem e o trecho vira buraco."""
    out, congelados, i = [], {}, 0
    while i < len(p):
        j = i
        while j + 1 < len(p) and p[j + 1][1] == p[i][1]:
            j += 1
        if p[i][1] != 0 and (p[j][0] - p[i][0]).total_seconds() > CONGELADO:
            out.append(p[i])
            congelados[p[i][0]] = "leitura congelada em %s W/m² das %s às %s" % (
                ("%.1f" % p[i][1]).replace(".", ","), p[i][0].strftime("%H:%M"), p[j][0].strftime("%H:%M"))
        else:
            out.extend(p[i:j + 1])
        i = j + 1
    return out, congelados


def _fechar_dia(pts):
    """(kWh/m² ou None, motivo) de um canal num dia. pts = [(datetime, W/m²)].

    Regra do etm_pol.py (lote de 03/11/2026) = regra 13 da coleta: leitura fora de -50..2000 W/m² sai (lixo como
    -3,2e26 no São Bento V e 2,6e4 no Goytacazes, 28/08); negativo conta 0; trapézio entre leituras, sem interpolar
    buraco > 30 min; o dia só fecha com leitura antes das 07 h e depois das 17 h e sem buraco > 30 min entre 06 e 18 h.
    Dia que não fecha fica VAZIO (nunca 0 nem meio dia).

    Três travas a mais, cada uma de um caso real:
    - leitura congelada: o mesmo valor (não zero) repetido por mais de 30 min é o supervisório sem comunicação
      repetindo o último valor — sai e vira buraco. Santa Bárbara I: 1,4 W/m² o dia inteiro de 13 a 19/10/2026 (o
      plano de 03/11 tirou esses dias à mão) e 168,3 W/m² das 19 h de 23/10 às 09 h de 24/10; São Bento V 01/11:
      396,9 W/m² das 12:50 às 17:14; GHI da Ibaté 1: 27,13 W/m² dia e noite em outubro inteiro (sensor morto);
    - buraco que começa antes das 06 h (ou acaba depois das 18 h) e come mais de 30 min de 07-17 h conta. O etm_pol só
      via pares de leituras dentro de 06-18 h: a leitura das 00:00 e a próxima às 09:15 (o congelado da Santa Bárbara
      em 24/10) passavam e o dia fechava sem a manhã. A janela é 07-17 h, a mesma folga das pontas do etm_pol (primeira
      leitura até 06:59 fecha): congelado que acaba às 06:38 (Marajoara 21/10) não derruba o dia;
    - madrugada com mediana > 20 W/m²: estação travada (Ibaté 1, 28/08/2026: 848,7 W/m² também às 00:00 e 03:00).
    """
    vistos = {}
    for t, v in pts:
        if -50 <= v <= 2000:
            vistos[t] = v
    p, congelados = _tira_congelado(sorted(vistos.items()))
    if not p:
        return None, "sem leitura válida"
    # o 1º ponto de um trecho congelado não conta como madrugada: é o valor velho repetido (Santa Bárbara I, 168,3 W/m²
    # das 19 h de 23/10 às 09:15 de 24/10), não a estação travada; o resto do dia entra
    noite = [v for t, v in p if t.hour < 4 and t not in congelados]
    if noite and statistics.median(noite) > NOITE_MAX:
        return None, "madrugada a %.0f W/m² (estação travada)" % statistics.median(noite)
    # Dia que não fecha (sem leitura antes das 07 h ou depois das 17 h, buraco > 30 min de dia) ENTRA com o que foi
    # medido, com o motivo, em vez de ficar vazio (Levi, 11/11/2026: a consulta simples no Excel do "IPOA e GHI (44).csv"
    # da Araçoiaba 1 dava os 23 dias e o Conversor deixava vazios 24-25/10 e 01, 02, 04 e 05/11). O valor pode ficar
    # abaixo do real — o aviso diz onde está o buraco para quem cola decidir.
    parcial = []
    if p[0][0].hour >= 7:
        parcial.append("primeira leitura às %s" % p[0][0].strftime("%H:%M"))
    if p[-1][0].hour < 17:
        parcial.append(congelados.get(p[-1][0]) or "última leitura às %s" % p[-1][0].strftime("%H:%M"))
    zero = p[0][0].replace(hour=0, minute=0, second=0, microsecond=0)
    n0, n1 = zero.replace(hour=7), zero.replace(hour=17)
    for (a, _), (b, _) in zip(p, p[1:]):
        dentro = 6 <= a.hour < 18 and 6 <= b.hour < 18 and (b - a).total_seconds() > BURACO     # etm_pol
        come = (min(b, n1) - max(a, n0)).total_seconds() > BURACO                               # trava a mais
        if dentro or come:
            parcial.append(congelados.get(a) or "buraco das %s às %s" % (a.strftime("%H:%M"), b.strftime("%H:%M")))
    tot = 0.0
    for (a, va), (b, vb) in zip(p, p[1:]):
        s = (b - a).total_seconds()
        if 0 < s <= BURACO:
            tot += (max(0.0, va) + max(0.0, vb)) / 2 * s / 3600
    v = round(tot / 1000, 4)
    if v <= 0:
        return None, "irradiação zero"                    # <= 0 fica vazia, nunca 0 (regra 12 da coleta)
    return v, ("; ".join(parcial) if parcial else None)


def _hora(s):
    s = s.strip()
    for f in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return dt.datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def _canal_logger(h, tipo):
    """índice do canal médio/atual de POA ou GHI no cabeçalho do datalogger (nunca REAR, MAX, MIN nem kWh)."""
    conhecidos = {"poa": ("rad_poa_med", "irrad_sr20_poa_med", "irrad_sr05_poa_act"),
                  "ghi": ("rad_ghi_torre_med", "irrad_sr20_ghi_med", "irrad_sr05_ghi_act")}[tipo]
    for c in conhecidos:
        if c in h:
            return h.index(c)
    cand = [j for j, x in enumerate(h) if tipo in x and "rear" not in x and "kwh" not in x
            and x.endswith(("_med", "_act", "_avg", "_mean"))]
    return cand[0] if len(cand) == 1 else None


def _canal_temp(h):
    """temperatura do MÓDULO no datalogger (Temp_PV_MED, Temp_Modulo_MED...), nunca a do ar. Levi, 10/11/2026: "seria
    interessante IPOA, GHI e temperatura dos módulos, o que não tem fica nulo mesmo"."""
    for j, x in enumerate(h):
        if "temp" in x and any(k in x for k in ("pv", "mod", "painel", "placa", "celula")) and \
                not any(k in x for k in ("_ar", "amb", "max", "min")) and x.endswith(("_med", "_act", "_avg", "_mean")):
            return j
    return None


def _canais_soltos(h):
    """irradiação sem nome de POA nem de GHI: até dois canais médios/atuais viram ETM1 e ETM2 (Levi, 10/11/2026)."""
    out = []
    for j, x in enumerate(h):
        if any(k in x for k in ("irrad", "rad_", "pyr", "piran", "sr05", "sr20", "sr30", "solar")) and \
                not any(k in x for k in ("rear", "kwh", "max", "min", "albedo")) and \
                x.endswith(("_med", "_act", "_avg", "_mean")):
            out.append(j)
    return out[:2]


def _formato_etm(linhas):
    """das primeiras linhas: {'tipo': 'scada'} | {'tipo': 'logger', 'sep', 'date', 'time', 'poa', 'ghi', 'nomes'} | None"""
    cab = next((l for l in linhas if l.strip()), "").lstrip("﻿")
    h0 = norm(cab)
    if h0.startswith("nome do data point") and "tempo" in h0 and "valor" in h0:
        if any("irradia" in norm(l) for l in linhas[1:6]):
            return {"tipo": "scada", "cab": cab.strip()}
        return None
    sep = ";" if cab.count(";") >= 3 else ("," if cab.count(",") >= 3 else None)
    if not sep:
        return None
    h = [norm(x) for x in cab.strip().split(sep)]
    if "date" not in h or "time" not in h:
        return None
    poa, ghi = _canal_logger(h, "poa"), _canal_logger(h, "ghi")
    etm = _canais_soltos(h) if poa is None and ghi is None else []
    if poa is None and ghi is None and not etm:
        return None
    return {"tipo": "logger", "sep": sep, "date": h.index("date"), "time": h.index("time"), "poa": poa, "ghi": ghi,
            "etm": etm, "temp": _canal_temp(h),
            "nomes": (h[poa] if poa is not None else None, h[ghi] if ghi is not None else None), "cab": cab.strip()}


def _ultima_linha(caminho):
    try:
        with open(caminho, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            t = f.read().decode("utf-8", "replace")
    except OSError:
        return ""
    ls = [l for l in t.splitlines() if l.strip()]
    return ls[-1] if ls else ""


def _data_linha(linha, fmt):
    if fmt["tipo"] == "scada":
        r = next(csv.reader([linha]), [])
        t = _hora(r[1]) if len(r) > 1 else None
        return t.date() if t else None
    r = linha.split(fmt["sep"])
    return data_de(r[fmt["date"]]) if fmt["date"] < len(r) else None


def _prefixo(ponto):
    m = re.match(r"([a-z]{2,4}\d{2})", norm(ponto))
    return m.group(1) if m else None


def _pontos_scada(texto):
    """{prefixo da estação: {(canal, date): [(datetime, W/m²)]}} — Valor com ponto decimal (float direto: o num() leria
    '848.125' como 848125)."""
    out = {}
    for r in csv.reader(io.StringIO(texto)):
        if len(r) < 3:
            continue
        n = norm(r[0])
        canal = "IPOA" if "inclinada" in n else ("GHI" if "horizontal" in n else None)
        if not canal or "irradia" not in n:
            continue
        t = _hora(r[1])
        try:
            v = float(r[2])
        except ValueError:
            continue
        if t:
            out.setdefault(_prefixo(r[0]) or "?", {}).setdefault((canal, t.date()), []).append((t, v))
    return out


def _pontos_logger(texto, fmt):
    """{(canal, datetime): W/m²} — vírgula decimal; TIME '08:52:59,193' (milissegundo fora)."""
    out = {}
    jd, jt = fmt["date"], fmt["time"]
    for i, l in enumerate(texto.splitlines()):
        if i == 0 or not l.strip():
            continue
        r = l.split(fmt["sep"])
        if max(jd, jt) >= len(r):
            continue
        t = _hora("%s %s" % (r[jd].strip(), r[jt].split(",")[0].strip()))
        if not t:
            continue
        canais = [("IPOA", fmt["poa"]), ("GHI", fmt["ghi"]), ("Temperatura", fmt.get("temp"))]
        canais += [("ETM%d" % (k + 1), j) for k, j in enumerate(fmt.get("etm") or [])]
        for canal, j in canais:
            if j is None or j >= len(r):
                continue
            try:
                out[(canal, t)] = float(r[j].strip().replace(",", "."))
            except ValueError:
                continue
    return out


def _usinas_do_texto(texto, abas):
    """(abas, candidatas): uma usina (ou as duas abas da mesma estação) ou, se o nome serve a mais de uma, a pergunta."""
    achou = [a for a in abas if _casa(texto, a)]
    if not achou:
        return [], []
    nomes = {norm(a) for a in achou}
    if len(achou) == 1 or any(nomes <= {norm(x) for x in g} for g in ESTACAO_COMPARTILHADA):
        return _estacao(achou, abas), []
    return [], _parecido(texto, achou)


def _usinas_etm(arq, fmt, prefixos, abas):
    """(usinas, candidatas, pergunta): nome do arquivo, depois o da pasta (arq.origem), depois o prefixo da estação."""
    nome, cand = _usinas_do_texto(arq.nome, abas)
    if not nome and not cand and arq.origem:
        nome, cand = _usinas_do_texto(arq.origem, abas)
    conteudo = []
    for p in sorted(prefixos):
        conteudo += [a for a in _estacao(PREFIXO_SCADA.get(p, ()), abas) if a not in conteudo]
    if nome and conteudo and {norm(a) for a in nome} != {norm(a) for a in conteudo}:
        return [], conteudo + [a for a in nome if a not in conteudo], (
            "O nome do arquivo diz %s, mas a estação do supervisório (%s) é de %s."
            % (", ".join(nome), ", ".join(p.upper() for p in sorted(prefixos)), ", ".join(conteudo)))
    if nome:
        return nome, [], None
    if conteudo:
        return conteudo, [], None
    if cand:
        return [], cand, "O nome %r serve a mais de uma usina." % (
            arq.nome if not arq.origem else "%s/%s" % (arq.origem, arq.nome))
    dica = [a for a in CANAIS_LOGGER.get(fmt.get("nomes"), ()) if a in abas]
    resto = [a for a in ETM_ABAS if a not in dica and a in abas]
    return [], dica + resto, "Não achei a usina no nome do arquivo nem no da pasta."


def _irmaos(arq, fmt, usinas, abas):
    """As outras partes do mesmo datalogger: mesma pasta, mesmo cabeçalho, nome que não diz outra usina. A Aparecida do
    Taboado vem em partes ("1 (5).csv" a "4 (4).csv" só de 29/10/2026): uma parte sozinha nunca fecha o dia."""
    pasta = os.path.dirname(arq.caminho)
    meu = {norm(a) for a in usinas}
    out = []
    try:
        nomes = sorted(os.listdir(pasta))
    except OSError:
        return out
    for n in nomes:
        c = os.path.join(pasta, n)
        if os.path.normcase(c) == os.path.normcase(arq.caminho) or not n.lower().endswith((".csv", ".txt")):
            continue
        if n.startswith(("~$", ".")) or not os.path.isfile(c):
            continue
        outro = Arquivo(c, origem=arq.origem)
        try:
            cab = next((l for l in outro.cabeca(3) if l.strip()), "").lstrip("﻿").strip()
        except OSError:
            continue
        if cab != fmt["cab"]:
            continue
        dele, cand = _usinas_do_texto(n, abas)
        if (dele and {norm(a) for a in dele} != meu) or cand:
            continue
        out.append(outro)
    return out


class EtmPolaris(Leitor):
    id = "polaris_etm"
    fonte = "ETM Polaris (supervisório e datalogger)"
    destino = BD_THOPEN

    def reconhecer(self, arq, ctx):
        if arq.ext not in (".csv", ".txt"):
            return None
        try:
            cab = arq.cabeca(6)
            fmt = _formato_etm(cab)
            if not fmt:
                return None
            ult = _ultima_linha(arq.caminho)
            amostra = [l for l in cab[1:3] + [ult] if l.strip()]
            dias = [d for d in (_data_linha(l, fmt) for l in amostra) if d]
            prefixos = set()
            if fmt["tipo"] == "scada":
                prefixos = {p for p in (_prefixo(next(csv.reader([l]), [""])[0]) for l in amostra) if p}
        except Exception:                                  # arquivo de outro formato não derruba a tela
            return None
        abas = _abas(ctx)
        usinas, cand, perg = _usinas_etm(arq, fmt, prefixos, abas)
        if fmt["tipo"] == "scada":
            det = "IPOA e GHI · supervisório"
        else:
            o_que = [n for n, ok in (("IPOA", fmt["poa"] is not None), ("GHI", fmt["ghi"] is not None),
                                     ("ETM1 e ETM2" if len(fmt.get("etm") or []) > 1 else "ETM1", bool(fmt.get("etm"))),
                                     ("temperatura do módulo", fmt.get("temp") is not None)) if ok]
            det = "%s · datalogger" % ", ".join(o_que)
        rec = Reconhecimento(self.fonte, usinas=usinas, periodo=(min(dias), max(dias)) if dias else None,
                             estado=fmt, detalhe=det)
        if not usinas:
            rec.candidatas, rec.pergunta = cand, perg
        return rec

    def ler(self, arq, ctx, rec, escolha=None):
        fmt = rec.estado
        abas = _abas(ctx)
        if not rec.usinas and (not escolha or escolha == SEM_USINA):
            usinas = [SEM_USINA]                         # converte assim mesmo; a sessão põe o nome do arquivo
        else:
            usinas = rec.usinas or _estacao([escolha], abas) or [escolha]
        avisos = []
        if fmt["tipo"] == "scada":
            por_estacao = _pontos_scada(arq.texto())
            dias = sorted({d for s in por_estacao.values() for (_, d) in s})
            if len(por_estacao) > 1:
                # Santarém 1 já mandou duas estações no PG: fica a de maior integral no dia (regra do PG, 28/08)
                avisos.append("o arquivo tem %d estações (%s): em cada dia ficou a de maior irradiação"
                              % (len(por_estacao), ", ".join(p.upper() for p in sorted(por_estacao))))
            serie = {}
            for s in por_estacao.values():
                for k, pts in s.items():
                    serie.setdefault(k, []).append(pts)
        else:
            meus = _pontos_logger(arq.texto(), fmt)
            dias = sorted({t.date() for (_, t) in meus})
            junto = dict(meus)
            partes = _irmaos(arq, fmt, usinas, abas)
            conflito = 0
            for p in partes:
                for k, v in _pontos_logger(p.texto(), fmt).items():
                    if k in junto and abs(junto[k] - v) > 0.01:
                        conflito += 1
                    junto[k] = v
            if conflito:
                # duas partes dizendo coisas diferentes no mesmo minuto não são o mesmo datalogger
                avisos.append("%d leitura(s) do mesmo horário com valores diferentes entre as partes da pasta — não "
                              "juntei; só este arquivo" % conflito)
                junto = meus
            elif partes:
                avisos.append("lido junto com %d parte(s) da mesma pasta (o dia só fecha com as partes juntas)"
                              % len(partes))
                if usinas == [SEM_USINA]:
                    # as partes do mesmo datalogger sem usina vão para UMA aba "Sem usina" (logging_00001 e
                    # logging_00002, 10/11/2026: saíam duas abas repetidas); o nome junta as partes em ordem
                    usinas = ["%s · %s" % (SEM_USINA, " + ".join(sorted([arq.nome] + [p.nome for p in partes])))]
            serie, temp, cobre = {}, {}, {}
            for (canal, t), v in junto.items():
                if canal == "Temperatura":
                    temp[t] = v
                    continue
                serie.setdefault((canal, t.date()), [[]])[0].append((t, v))
                c = cobre.get(t.date())
                cobre[t.date()] = (min(c[0], t.hour), max(c[1], t.hour)) if c else (t.hour, t.hour)
            if temp:
                # regra da Tucano (a mesma da Apolo): média de 06-18 h, >= 8 das 12 horas, dia inteiro no arquivo
                from conversor.leitores.apolo import _temperatura
                tdia, curtos = _temperatura(temp, {}, cobre)
                for d, v in sorted(tdia.items()):
                    if d not in dias:                       # só os dias deste arquivo, como o IPOA e o GHI
                        continue
                    for aba in usinas:
                        cel_temp = Celula(BD_THOPEN, aba, d, "Temperatura", v)
                        serie.setdefault(("_temp", d), []).append(cel_temp)
        cel, fora, parciais = [], {}, {}
        for k, lst in list(serie.items()) if fmt["tipo"] != "scada" else []:
            if k[0] == "_temp":
                cel += lst
                del serie[k]
        for d in dias:
            for canal in CANAIS:
                listas = serie.get((canal, d))
                if not listas:
                    continue
                vals, motivos = [], []
                for pts in listas:
                    v, m = _fechar_dia(pts)
                    if v is not None:
                        vals.append((v, m))
                    else:
                        motivos.append(m)
                if not vals:
                    fora.setdefault(d, []).append("%s: %s" % (canal, motivos[0]))
                    continue
                v, m = max(vals, key=lambda x: x[0])
                if m:
                    parciais.setdefault(d, []).append("%s: %s" % (canal, m))
                for aba in usinas:
                    cel.append(Celula(BD_THOPEN, aba, d, canal, v, nota=("parcial: " + m) if m else None))
        if parciais:
            ds = sorted(parciais)
            txt = "; ".join("%s (%s)" % (d.strftime("%d/%m"), " | ".join(parciais[d])) for d in ds)
            avisos.append(("leve", "%d dia(s) de ETM com buraco na leitura entram com o que foi medido (pode ficar abaixo "
                                   "do real): %s" % (len(ds), txt)))
        if fora:
            ds = sorted(fora)
            txt = "; ".join("%s (%s)" % (d.strftime("%d/%m"), " | ".join(fora[d])) for d in ds[:6])
            avisos.append("%d dia(s) de ETM sem leitura que sirva ficaram vazios: %s%s"
                          % (len(ds), txt, " e mais %d" % (len(ds) - 6) if len(ds) > 6 else ""))
        return cel, avisos


LEITORES = [RelatorioInversor, RelatorioInstalacao, EtmPolaris]
