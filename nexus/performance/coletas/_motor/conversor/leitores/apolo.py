# -*- coding: utf-8 -*-
"""UFVs da Apolo no BD_Performance (Gravatá II, Iramaia II, Rio do Peixe I e II) e a ETM do supervisório da Irecê 2 e
da Macaíba 1. Veio dos scripts feitos à mão em 01/11/2026 (apolo0111/monta.py), 06/11 (apolo0611/monta_0611.py),
09/11 (irece0911 e macaiba0911, etm_funcs.py) e 10/11 (apolo_temp/temp.py); as regras de colar agora são as do núcleo
(montagem.py). As abas da Apolo são manuais (Equipamentos sem "Usina Supervisório"): a coleta não toca nelas.

Três formatos, um leitor cada:

1. SmartLogger (Huawei): PerformanceData_<SN>_<AAAAMMDDhhmmss>.zip; o núcleo extrai e cada CSV chega com origem = nome
   do zip. Vale só o perfmg_day.csv ("No.,Device,Statistical Period,..."), sinal "Energy yield" de "1 Day". Linha
   repetida do mesmo inversor e dia fica a MAIOR (o SmartLogger regrava o dia ao longo dele; a parcial é menor). A
   usina vem do SN no nome do zip; sem ele, do nome da pasta/arquivo; sem os dois, o padrão INV0k_RPr_SKs só existe na
   Rio do Peixe. O dia da baixa (a hora está no nome do zip) e os seguintes ficam fora: estavam abertos.
2. Datalogger da ETM: "ETM UFV <USINA>_N.csv" (";", vírgula decimal, 1 leitura por minuto, partes _1 _2 _3). IPOA/GHI
   do dia = SOMA das leituras de 1 min de PiranometroIPOA/PiranometroGHI (W/m², negativas inclusive) / 60000 — é como
   a equipe preenche, bate ao 6º decimal em 01-21/10/2026. Não é trapézio nem o PirPOA_Acumulado.
3. Export do supervisório: "Nome do data point,Tempo,Valor,Processado,Comentário", uma linha por ponto e horário, de
   5 em 5 min. Na Apolo, estações GRA/IRA/RPA/RPB/RPX (RPA, RPB e RPX são a MESMA estação da Rio do Peixe):
   - IPOA/GHI = o MAIOR "Irradiação Acumulada - POA/GHI" do dia / 3.600.000 (o ponto diz Wh/m², mas é J/m² e zera à
     meia-noite), só em dia com leitura depois das 18h (02/11/2026 parou às 14:58 e ficou fora). Conferido na Iramaia em
     31/10: 8,379 x 8,390 e 7,043 x 7,059 do método de 1 min.
     O maior conta só DEPOIS da zeragem (10/11/2026): no export de outubro a leitura de 00:00 ainda traz o total da
     véspera, e o "maior do dia inteiro" repetiu a véspera em todo dia mais fraco que o anterior (Iramaia 27/10: 5,90
     no lugar de 0,545). Com a regra nova o supervisório e o datalogger de 1 min batem em +-1,1% nos 92 dias em comum.
   - Temperatura = do MÓDULO pela regra da Tucano (coletar_semp.temp_modulo_solar): média das leituras de 06:00 a
     18:00, -20 a 90 °C, só com leitura em >= 8 das 12 horas; Módulo 1, senão Módulo 2.
   A Irecê 2 e a Macaíba 1 (09/11/2026) usam o MESMO export, com a estação "ESTM_01" e o W/m² de 5 em 5 min
   ("Pyranometer POA" / "Pyranometer GHI_1"), sem acumulado e sem a usina no conteúdo: a usina vem do nome do arquivo
   ou da pergunta. Dia = trapézio do W/m² (regras do etm_funcs.py, que reproduzem o BD das duas ao milésimo).

De-para do SmartLogger (21 de 21 dias iguais ao BD em cada inversor em 01-21/10/2026): Gravatá II InverterNN = 1.N;
Iramaia II "Inversor NN" em qualquer grafia = 1.N; Rio do Peixe um skid por SmartLogger (ver _col_rio).
"""
import collections
import csv
import datetime as dt
import io
import os
import re
import statistics

from conversor.nucleo import BD_PERFORMANCE, SEM_USINA, Celula, Leitor, Reconhecimento, data_de, norm, norm_col

GRAVATA, IRAMAIA, RIO = "Gravatá II", "Iramaia II", "Rio do Peixe I e II"
IRECE, MACAIBA = "Irece 2", "Macaiba 1"
APOLO = [GRAVATA, IRAMAIA, RIO]
ESTM = [IRECE, MACAIBA]

# SN do SmartLogger (nome do zip) -> aba. A Rio do Peixe tem quatro, um por skid (RP1/RP2 x SK1/SK2).
SN_SMARTLOGGER = {
    "102459808715": GRAVATA,
    "10255a564524": IRAMAIA,
    "102459571170": RIO,          # INV0k_RP1_SK1
    "102459571235": RIO,          # INV0k_RP1_SK2
    "102459571242": RIO,          # INV0k_RP2_SK1
    "102459571215": RIO,          # INV0k_RP2_SK2
}
NOMES_APOLO = (("rio do peixe", RIO), ("gravata", GRAVATA), ("iramaia", IRAMAIA))
NOMES_ESTM = (("irece", IRECE), ("macaiba", MACAIBA))
# o mesmo ponto ESTM_01 "Pyranometer POA" existe na Cedro 1/2 e na Castelo do Piauí (09/11/2026), que não estão
# conferidas aqui: com o nome delas no arquivo, o leitor nem reconhece — melhor "formato novo" do que a pessoa
# escolher Irecê ou Macaíba para um arquivo da Cedro
NOMES_ESTM_FORA = ("cedro", "castelo")
ESTACAO_APOLO = {"GRA": GRAVATA, "IRA": IRAMAIA, "RPA": RIO, "RPB": RIO, "RPX": RIO}
ORDEM_RIO = ("RPA", "RPB", "RPX")  # a RPA é a que o script de 06/11 usou; as outras só cobrem dia que falta nela

DL_MIN_LEITURAS = 1380            # 23 h de 1 min: o dia do datalogger que tem menos que isso está incompleto
DL_MAX_LEITURAS = 1445            # mais que 1 por minuto: a soma / 60000 deixaria de ser o dia (intervalo mudou)
BURACO_MAX_MIN = 30               # buraco maior que isso entre 06h e 18h = dia incompleto (perde o sol daquele trecho)
TEMP_INI, TEMP_FIM, TEMP_HORAS_MIN = 6, 18, 8   # coletar_semp: HORA_INI, HORA_FIM, _HORAS_MIN
TEMP_FAIXA = (-20.0, 90.0)        # fora disso é sentinela do sensor (99999, -666)


# ---------------------------------------------------------------- comuns
def _chave(s):
    return re.sub(r"[^a-z0-9]+", " ", norm(s)).strip()


def _usina_no_nome(arq, tabela):
    """aba pelo nome do arquivo e, sem ele, pelo da pasta/zip; dois nomes no mesmo texto = ambíguo (None)."""
    for texto in (arq.nome, arq.origem):
        t = " %s " % _chave(texto)
        achou = {aba for k, aba in tabela if (" %s" % k) in t}
        if len(achou) == 1:
            return achou.pop()
        if achou:
            return None
    return None


def _texto(caminho):
    with open(caminho, "rb") as f:
        b = f.read()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1", "replace")


def _cauda(caminho, n=4096):
    """últimas linhas do arquivo sem ler tudo (período do datalogger de 13 MB no reconhecer)."""
    try:
        with open(caminho, "rb") as f:
            f.seek(0, os.SEEK_END)
            tam = f.tell()
            f.seek(max(0, tam - n))
            b = f.read()
    except OSError:
        return []
    return b.decode("latin-1", "replace").splitlines()[1:]


def _aba_bd(ctx, nome):
    try:
        return ctx.aba(BD_PERFORMANCE, nome) if ctx is not None else None
    except Exception:                                 # noqa: BLE001 — BD ilegível não impede de ler o arquivo
        return None


def _antes_da_aba(ab):
    """primeira data da aba: o SmartLogger e o datalogger trazem um ano de histórico, e a aba da Apolo começa em
    01/10/2026 — sem esse corte o cartão listaria 300 dias "sem linha"."""
    return min(ab.datas) if ab is not None and ab.datas else None


# ---------------------------------------------------------------- 1. SmartLogger
_CAB_SL = ["no.", "device", "statistical period", "statistical start time", "signal name", "value"]


def _e_perfmg_day(arq):
    if arq.ext != ".csv":
        return False
    try:
        cab = arq.cabeca(40)
    except OSError:
        return False
    if not cab or [norm(x) for x in cab[0].split(",")][:6] != _CAB_SL:
        return False
    # perfmg_hour/month/year têm o mesmo cabeçalho com "1 H", "1 Month", "1 Year": só o diário entra
    return any(len(p) > 2 and p[2].strip() == "1 Day" for p in (l.split(",") for l in cab[1:]))


def _ler_perfmg(arq):
    """({dispositivo: {data: kWh}}, linhas repetidas, [(dispositivo, data)] com "No Data")."""
    serie = collections.defaultdict(dict)
    rep, sem = 0, []
    for r in csv.reader(io.StringIO(arq.texto())):
        if len(r) < 6 or r[2].strip() != "1 Day" or r[4].strip() != "Energy yield":
            continue
        dev, d = r[1].strip(), data_de(r[3])
        if not dev or not d:
            continue
        try:
            v = float(r[5].strip())                  # ponto decimal sempre; "No Data" = sem leitura, sem célula
        except ValueError:
            sem.append((dev, d))
            continue
        if d in serie[dev]:
            rep += 1
            v = max(v, serie[dev][d])
        serie[dev][d] = v
    return serie, rep, sem


def _sn_e_baixa(arq):
    m = re.search(r"performancedata_([0-9a-z]+)_(\d{14})", norm("%s %s" % (arq.origem, arq.nome)))
    if not m:
        return None, None
    try:
        return m.group(1), dt.datetime.strptime(m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return m.group(1), None


def _col_gravata(dev, ab=None):
    m = re.fullmatch(r"inverter\s*0*(\d{1,2})", norm(dev))          # Inverter01..Inverter10
    return "Inversor 1.%d" % int(m.group(1)) if m and 1 <= int(m.group(1)) <= 10 else None


def _col_iramaia(dev, ab=None):
    m = re.fullmatch(r"inversor\s*0*(\d{1,2})", norm(dev))          # "Inversor 02", "inversor 01", "Inversor06"
    return "Inversor 1.%d" % int(m.group(1)) if m and 1 <= int(m.group(1)) <= 10 else None


def _rio_esquema_antigo(ab):
    cab = {norm_col(h) for h in (ab.cab if ab is not None else [])}
    return "inversor 1.6" in cab and "inversor 3.1" not in cab


def _col_rio(dev, ab=None):
    """INV0k_RPr_SKs. Cada SmartLogger é um skid: RP1_SK1 = 1.k, RP1_SK2 = 2.k, RP2_SK1 = 3.k, RP2_SK2 = 4.k.
    Até a manhã de 10/11/2026 a aba chamava os mesmos 20 inversores de 1.1-1.10 e 2.1-2.10 (RP1_SK2 = 1.(k+5),
    RP2_SK1 = 2.k, RP2_SK2 = 2.(k+5)); a renomeação não moveu dado (39 de 39 dias iguais coluna a coluna). Se o BD
    voltar a uma versão antiga, o cabeçalho volta junto (já aconteceu na União e na Matão 2): segue o cabeçalho."""
    m = re.fullmatch(r"inv\s*0*(\d)_rp([12])_sk([12])", norm(dev))
    if not m or not 1 <= int(m.group(1)) <= 5:
        return None
    k, rp, sk = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if _rio_esquema_antigo(ab):
        return "Inversor %d.%d" % (rp, k + (5 if sk == 2 else 0))
    return "Inversor %d.%d" % (2 * (rp - 1) + sk, k)


COLUNA_SL = {GRAVATA: _col_gravata, IRAMAIA: _col_iramaia, RIO: _col_rio}


class SmartLogger(Leitor):
    id = "apolo_smartlogger"
    fonte = "SmartLogger Huawei (Apolo)"
    destino = BD_PERFORMANCE

    def reconhecer(self, arq, ctx):
        if not _e_perfmg_day(arq):
            return None
        serie, rep, sem = _ler_perfmg(arq)
        devs = sorted(d for d in serie if norm(d) != "logger")
        if not devs:
            return None
        sn, baixa = _sn_e_baixa(arq)
        aba = SN_SMARTLOGGER.get(sn) or _usina_no_nome(arq, NOMES_APOLO)
        if not aba and all(_col_rio(d) for d in devs):
            aba = RIO
        dias = sorted({d for dev in devs for d in serie[dev]})
        rec = Reconhecimento(self.fonte, usinas=[aba] if aba else [], periodo=(dias[0], dias[-1]) if dias else None,
                             estado={"serie": serie, "aba": aba, "sn": sn, "baixa": baixa, "rep": rep, "sem": sem},
                             detalhe="%d inversores · energia do dia" % len(devs))
        if not aba:
            # o nome do inversor sozinho não prova a usina ("InverterNN" é o padrão de fábrica da Huawei)
            prov = [a for a in APOLO if all(COLUNA_SL[a](d) for d in devs)]
            rec.candidatas = prov + [a for a in APOLO if a not in prov]
            rec.pergunta = ("Relatório do SmartLogger%s sem número de série conhecido. Inversores: %s. Escolha só se "
                            "tiver certeza da usina." % (" %s" % sn.upper() if sn else "", ", ".join(devs[:4])))
        return rec

    def ler(self, arq, ctx, rec, escolha=None):
        e = rec.estado
        aba = e["aba"] or escolha
        if not aba:
            return [], ["SmartLogger sem usina: escolha a usina no cartão"]
        if aba not in COLUNA_SL:
            return [], ["%s: o de-para do SmartLogger só cobre %s" % (aba, ", ".join(APOLO))]
        ab = _aba_bd(ctx, aba)
        ini = _antes_da_aba(ab)
        fcol = COLUNA_SL[aba]
        cel, avisos = [], []
        por_col = collections.defaultdict(list)
        for dev in sorted(e["serie"]):
            if norm(dev) == "logger":                 # o total da usina, não é inversor
                continue
            col = fcol(dev, ab)
            if not col:
                avisos.append("%s: dispositivo %r fora do de-para do SmartLogger — ficou fora" % (aba, dev))
                continue
            por_col[col].append(dev)
        abertos = 0
        for col, devs in sorted(por_col.items()):
            if len(devs) > 1:                         # dois nomes no mesmo inversor: não dá para saber qual vale
                avisos.append("%s: %s caem os dois na %s — ficaram fora" % (aba, " e ".join(map(repr, devs)), col))
                continue
            for d, v in sorted(e["serie"][devs[0]].items()):
                if e["baixa"] and d >= e["baixa"].date():
                    abertos += 1
                    continue
                if ini and d < ini:                   # histórico de antes da aba existir
                    continue
                cel.append(Celula(BD_PERFORMANCE, aba, d, col, round(v, 2)))
        if abertos:
            avisos.append("%s: %d valor(es) de %s em diante ficaram fora — o relatório foi baixado nesse dia, às %s, "
                          "com o dia ainda aberto" % (aba, abertos, e["baixa"].strftime("%d/%m"),
                                                      e["baixa"].strftime("%H:%M")))
        com_dado = {(dev, d) for dev, x in e["serie"].items() for d in x}
        sem = sorted({(d, dev) for dev, d in e["sem"] if (dev, d) not in com_dado and norm(dev) != "logger"
                      and not (ini and d < ini) and not (e["baixa"] and d >= e["baixa"].date())})
        if sem:
            avisos.append("%s: o SmartLogger diz \"No Data\" em %d inversor-dia (%s%s) — sem célula"
                          % (aba, len(sem), ", ".join("%s %s" % (dev, d.strftime("%d/%m")) for d, dev in sem[:6]),
                             "..." if len(sem) > 6 else ""))
        return cel, avisos


# ---------------------------------------------------------------- 2. Datalogger da ETM
def _cab_datalogger(linha):
    linha = linha.lstrip("\ufeff").replace("\u00ef\u00bb\u00bf", "", 1)   # BOM lido como texto ou como latin-1
    h = [x.strip().strip('"').strip().lower() for x in linha.split(";")]
    if len(h) > 3 and h[0] == "date" and h[1] == "time" and "piranometroipoa" in h and "piranometroghi" in h:
        return h
    return None


def _num_dl(s):
    s = s.strip().strip('"').strip()
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
    except ValueError:
        return None


def _data_dl(dia):
    """'01/10/2026' -> date (o datalogger grava sempre assim; outra grafia = linha ignorada)."""
    try:
        d, m, a = dia.strip().strip('"').split("/")
        return dt.date(int(a), int(m), int(d))
    except (ValueError, TypeError, AttributeError):
        return None


def _seg_dl(hora):
    """segundos do dia de '00:00:57'."""
    h = (hora or "").strip().strip('"')
    try:
        if len(h) >= 8 and h[2] == ":" and h[5] == ":":
            s = int(h[0:2]) * 3600 + int(h[3:5]) * 60 + int(h[6:8])
        else:
            p = h.split(":")
            s = int(p[0]) * 3600 + int(p[1]) * 60 + (int(float(p[2])) if len(p) > 2 else 0)
    except (ValueError, IndexError):
        return None
    return s if 0 <= s < 86400 else None


_JANELA = (6 * 3600, 18 * 3600)


_DL_CACHE = {}


def _hm(seg):
    return "%02d:%02d" % (seg // 3600, seg % 3600 // 60)


def _buraco_na_janela(s0, s1):
    """minutos sem leitura entre s0 e s1 (segundos do dia) dentro da janela de sol (06h-18h)."""
    a, b = max(s0, _JANELA[0]), min(s1, _JANELA[1])
    return max(0.0, (b - a) / 60.0)


def _dias_datalogger(caminho, texto=None):
    """{data: dict(n, nI, sI, nG, sG, ini, fim, buraco, ordem)} de um CSV do datalogger (ini/fim em segundos do dia).
    Fica em cache por caminho, data de alteração e tamanho: as partes _1 _2 _3 de 13 MB são lidas uma vez só, mesmo
    quando cada parte lê as vizinhas."""
    try:
        st = os.stat(caminho)
    except OSError:
        return {}
    k = (os.path.normcase(os.path.abspath(caminho)), st.st_mtime, st.st_size)
    if k in _DL_CACHE:
        return _DL_CACHE[k]
    texto = texto if texto is not None else _texto(caminho)
    linhas = csv.reader(io.StringIO(texto), delimiter=";")
    h = _cab_datalogger(";".join(next(linhas, [])))
    out = {}
    if not h:
        _DL_CACHE[k] = out
        return out
    ji, jg = h.index("piranometroipoa"), h.index("piranometroghi")
    jmax = max(ji, jg)
    datas = {}
    for r in linhas:
        if len(r) <= jmax:
            continue
        d = datas.get(r[0], False)
        if d is False:
            d = datas[r[0]] = _data_dl(r[0])
        if d is None:
            continue                                  # linha vazia do fim do export ('"";"";...')
        s = _seg_dl(r[1])
        if s is None:
            continue
        x = out.get(d)
        if x is None:
            x = out[d] = {"n": 0, "nI": 0, "sI": 0.0, "nG": 0, "sG": 0.0, "ini": s, "fim": None, "buraco": 0.0,
                          "ordem": True}
        elif s <= x["fim"]:                           # repetida ou fora de ordem: a soma deixaria de ser confiável
            x["ordem"] = False
            continue
        else:
            x["buraco"] = max(x["buraco"], _buraco_na_janela(x["fim"], s))
        x["n"] += 1
        x["fim"] = s
        vi, vg = _num_dl(r[ji]), _num_dl(r[jg])
        if vi is not None:
            x["nI"] += 1
            x["sI"] += vi
        if vg is not None:
            x["nG"] += 1
            x["sG"] += vg
    _DL_CACHE[k] = out
    return out


def _partes(arq):
    """as partes do mesmo export na mesma pasta: 'ETM UFV IRAMAIA_1.csv', '_2', '_3'. O dia que cai na virada de uma
    parte para a outra (11/04 e 14/07/2026 na Iramaia) só fecha somando as duas."""
    m = re.fullmatch(r"(.*)_(\d+)\.csv", arq.nome, flags=re.I)
    pasta = os.path.dirname(arq.caminho)
    if not m or not os.path.isdir(pasta):
        return [arq.caminho]
    pref = m.group(1).lower()
    out = []
    for n in sorted(os.listdir(pasta)):
        mm = re.fullmatch(r"(.*)_(\d+)\.csv", n, flags=re.I)
        if mm and mm.group(1).lower() == pref:
            p = os.path.join(pasta, n)
            if os.path.normcase(p) == os.path.normcase(arq.caminho):
                out.append(p)
                continue
            try:
                with open(p, "rb") as f:
                    l0 = f.readline().decode("latin-1", "replace")
            except OSError:
                continue
            if _cab_datalogger(l0):
                out.append(p)
    return out or [arq.caminho]


def _juntar_dia(pedacos):
    """um dia que veio em mais de uma parte. Sobreposição de horário = leitura repetida possível: dia fora."""
    pedacos = sorted(pedacos, key=lambda x: x["ini"])
    tot = dict(pedacos[0])
    for x in pedacos[1:]:
        if x["ini"] <= tot["fim"]:
            tot["ordem"] = False
        tot["buraco"] = max(tot["buraco"], x["buraco"], _buraco_na_janela(tot["fim"], x["ini"]))
        for c in ("n", "nI", "sI", "nG", "sG"):
            tot[c] += x[c]
        tot["fim"] = max(tot["fim"], x["fim"])
        tot["ordem"] = tot["ordem"] and x["ordem"]
    return tot


class Datalogger(Leitor):
    id = "apolo_datalogger"
    fonte = "Datalogger da ETM (Apolo)"
    destino = BD_PERFORMANCE

    def reconhecer(self, arq, ctx):
        if arq.ext not in (".csv", ".txt"):
            return None
        try:
            cab = arq.cabeca(3)
        except OSError:
            return None
        if not cab or not _cab_datalogger(cab[0]):
            return None
        d0 = next((d for d in (_data_dl(l.split(";")[0]) for l in cab[1:]) if d), None)
        d1 = None
        for n in (4096, 65536, 2 ** 21):              # o export da Gravatá acaba em 1 MB de linhas '"";"";...'
            d1 = next((d for d in (_data_dl(l.split(";")[0]) for l in reversed(_cauda(arq.caminho, n))) if d), None)
            if d1:
                break
        aba = _usina_no_nome(arq, NOMES_APOLO)
        rec = Reconhecimento(self.fonte, usinas=[aba] if aba else [],
                             periodo=(d0, d1) if d0 and d1 and d0 <= d1 else None, estado={"aba": aba},
                             detalhe="IPOA e GHI de 1 em 1 min")
        if not aba:
            rec.candidatas = list(APOLO)
            rec.pergunta = ("CSV do datalogger da ETM (PiranometroIPOA/PiranometroGHI) sem o nome da usina no "
                            "arquivo ('ETM UFV <USINA>_N.csv').")
        return rec

    def ler(self, arq, ctx, rec, escolha=None):
        # sem usina no nome e sem escolha: converte assim mesmo, por dia, numa aba "Sem usina" (Levi, 10/11/2026: "quando
        # não sabe a usina não precisa apontar usina"). Até 11/11 o datalogger sem nome só avisava e não dava valor
        # nenhum ("etm_1.csv", 15/12/2025 a 20/08/2026: "buguei o beta com esse csv")
        aba = rec.estado["aba"] or escolha or SEM_USINA
        sem_usina = aba.startswith(SEM_USINA)
        if not sem_usina and aba not in APOLO:
            return [], ["%s: o datalogger da ETM (PiranometroIPOA) só está conferido na %s" % (aba, ", ".join(APOLO))]
        partes = _partes(arq)
        meus = _dias_datalogger(arq.caminho, arq.texto())
        outros = [_dias_datalogger(p) for p in partes if os.path.normcase(p) != os.path.normcase(arq.caminho)]
        ab = None if sem_usina else _aba_bd(ctx, aba)
        ini = _antes_da_aba(ab) if ab else None
        cel, avisos = [], []
        curtos, sobrepostos, buracos, densos = [], [], [], []
        for d in sorted(meus):
            if ini and d < ini:                       # histórico de antes da aba existir
                continue
            x = _juntar_dia([meus[d]] + [o[d] for o in outros if d in o])
            if not x["ordem"]:
                sobrepostos.append(d)
                continue
            if x["n"] > DL_MAX_LEITURAS:
                densos.append((d, x["n"]))
                continue
            # dia incompleto ENTRA com o que foi medido e a observação (Levi, 11/11/2026: "o ideal não seria descartar o
            # dia e sim só sinalizar em uma observação de status"); repetido e mais de 1 leitura/min seguem fora: a soma
            # / 60000 contaria em dobro (não é falta de dado, é conta errada)
            obs = []
            if x["buraco"] > BURACO_MAX_MIN:
                obs.append("%.0f min sem leitura entre 06h e 18h" % x["buraco"])
                buracos.append((d, x["buraco"]))
            for col, n, s in (("IPOA", x["nI"], x["sI"]), ("GHI", x["nG"], x["sG"])):
                o = list(obs)
                if n < DL_MIN_LEITURAS:
                    o.append("%d leituras (%s a %s)" % (n, _hm(x["ini"]), _hm(x["fim"])))
                    curtos.append((d, col, n, x["ini"], x["fim"]))
                v = s / 60000.0
                if v > 0:                             # irradiação <= 0 fica vazia, nunca zero nem negativa
                    cel.append(Celula(BD_PERFORMANCE, aba, d, col, round(v, 6),
                                      nota=("parcial: " + "; ".join(o)) if o else None))
        parciais = sorted({c[0] for c in curtos} | {d for d, _ in buracos})
        if parciais:
            avisos.append(("leve", "%s: %d dia(s) com leitura incompleta no datalogger entram com o que foi medido (pode "
                                   "ficar abaixo do real; a observação vai na célula): %s"
                           % ("Sem usina" if sem_usina else aba, len(parciais),
                              ", ".join(d.strftime("%d/%m") for d in parciais[:12])
                              + (" e mais %d" % (len(parciais) - 12) if len(parciais) > 12 else ""))))
        for d in sobrepostos:
            avisos.append("%s %s: leituras repetidas ou fora de ordem (partes do export se sobrepõem?) — dia fora"
                          % (aba, d.strftime("%d/%m")))
        for d, n in densos:
            avisos.append("%s %s: %d leituras, mais de uma por minuto — a soma / 60000 não vale; dia fora"
                          % (aba, d.strftime("%d/%m"), n))
        return cel, avisos


# ---------------------------------------------------------------- 3. Export do supervisório
_RE_APOLO = re.compile(r"^([a-z]{3})_etm_a - \1_med_(.+)$")


def _ponto(nome):
    """(estação, tipo) do ponto; tipo None = ponto que o BD não usa (piranômetro HOR, temperatura do ar...)."""
    n = norm(nome)
    m = _RE_APOLO.match(n)
    if m:
        est, resto = m.group(1).upper(), m.group(2)
        for pref, tipo in (("irradiacao acumulada - poa", "ac_IPOA"), ("irradiacao acumulada - ghi", "ac_GHI"),
                           ("temperatura do modulo 1", "m1"), ("temperatura do modulo 2", "m2"),
                           ("temperatura do ar", "ar")):
            if resto.startswith(pref):
                return est, tipo
        return est, None
    if n == "estm_01 - pyranometer poa":
        return "ESTM_01", "w_IPOA"
    if n.startswith("estm_01 - pyranometer ghi"):
        return "ESTM_01", "w_GHI"
    return None, None


def _conhecido(nome):
    """ponto de estação que este leitor cobre (uma estação de 3 letras desconhecida fica para outro leitor)."""
    est, tipo = _ponto(nome)
    return est in ESTACAO_APOLO or (est == "ESTM_01" and tipo is not None)


def _dh_scada(s):
    """'2026/10/31 00:03:33' -> datetime."""
    s = s.strip()
    try:
        return dt.datetime(int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]), int(s[14:16]), int(s[17:19]))
    except (ValueError, IndexError):
        return None


def _ler_scada(arq):
    """Uma passada no CSV: o que cada regra precisa, por estação e dia."""
    ac = collections.defaultdict(list)                             # (est, col, dia) -> [(instante, J/m²)]
    temp = collections.defaultdict(dict)                           # (est, "m1"/"m2") -> {instante: valor}
    cobre = collections.defaultdict(lambda: [None, None])          # (est, dia) temperatura -> [1ª hora, última hora]
    w = collections.defaultdict(list)                              # (est, col, dia) -> [(instante, W/m²)]
    estacoes, ignorados = set(), set()
    dias = set()
    linhas = csv.reader(io.StringIO(arq.texto()))
    next(linhas, None)
    cache = {}
    for r in linhas:
        if len(r) < 3:
            continue
        p = cache.get(r[0])
        if p is None:
            p = cache[r[0]] = _ponto(r[0])
        est, tipo = p
        if est is None:
            ignorados.add(r[0])
            continue
        estacoes.add(est)
        if tipo is None:
            continue
        t = _dh_scada(r[1])
        if t is None:
            continue
        try:
            v = float(r[2].strip().lstrip("'"))      # "Valor" vem com ponto decimal (o "Processado" é que tem vírgula)
        except ValueError:
            continue
        d = t.date()
        dias.add(d)
        if tipo.startswith("ac_"):
            ac[(est, tipo[3:], d)].append((t, v))
        elif tipo in ("m1", "m2", "ar"):
            c = cobre[(est, d)]
            c[0] = t.hour if c[0] is None else min(c[0], t.hour)
            c[1] = t.hour if c[1] is None else max(c[1], t.hour)
            if tipo != "ar":
                temp[(est, tipo)][t] = v
        else:
            w[(est, tipo[2:], d)].append((t, v))
    return {"ac": dict(ac), "temp": dict(temp), "cobre": dict(cobre), "w": dict(w), "estacoes": estacoes,
            "ignorados": ignorados, "dias": dias}


ZERADO_MAX = 0.1 * 3.6e6           # J/m²: acumulado abaixo disso = já zerou na virada do dia
QUEDA_MAX = 0.2 * 3.6e6            # J/m²: queda maior que isso no mesmo dia = a estação reiniciou o acumulado


def _acumulado(pts):
    """(maior acumulado do dia em J/m², motivo para ficar fora). O MAIOR do dia, mas só DEPOIS da zeragem: a leitura de
    00:00 ainda traz o total da véspera em alguns dias (IRA 27/10/2026 00:00:41 = 2,122699E7 = o 26/10 inteiro; às
    00:05:41 já era -227,78). O maior do dia inteiro deu 5,90 kWh/m² na Iramaia em 27/10, quando o dia foi 0,545 (o
    datalogger de 1 min dá 0,546 e a geração foi 155 kWh por inversor, 8% de um dia comum)."""
    pts = sorted(pts)
    if not any(t.hour >= 18 for t, _ in pts):
        return None, "sem leitura depois das 18h (dia incompleto)"
    r = next((k for k, (_, v) in enumerate(pts) if v <= ZERADO_MAX), None)
    if r is None:
        return None, "o acumulado não zerou na virada do dia (menor leitura %.2f kWh/m²)" % (
            min(v for _, v in pts) / 3.6e6)
    topo = pts[r][1]
    for t, v in pts[r + 1:]:
        if v < topo - QUEDA_MAX:
            return None, "o acumulado caiu às %s (de %.2f para %.2f kWh/m²: a estação reiniciou?)" % (
                t.strftime("%H:%M"), topo / 3.6e6, v / 3.6e6)
        topo = max(topo, v)
    return topo, None


def _temperatura(m1, m2, cobre):
    """{dia: °C} pela regra da Tucano (coletar_semp.temp_modulo_solar), igual ao apolo_temp/temp.py de 10/11/2026 que
    gravou a coluna: por instante, Módulo 1 se válido, senão Módulo 2; média de 06h a 18h; >= 8 horas com leitura.
    O dia ainda precisa estar inteiro no export (leitura antes das 07h e depois das 18h): um export que acaba às 14:58
    passaria nas 8 horas com a tarde de fora."""
    por = collections.defaultdict(lambda: ([], set()))
    lo, hi = TEMP_FAIXA
    for t in sorted(set(m1) | set(m2)):
        if not (TEMP_INI <= t.hour < TEMP_FIM):
            continue
        a = m1.get(t)
        v = a if a is not None and lo <= a <= hi else m2.get(t)
        if v is None or not (lo <= v <= hi):
            continue
        por[t.date()][0].append(v)
        por[t.date()][1].add(t.hour)
    out, curtos = {}, []
    for d, (vs, hs) in por.items():
        c = cobre.get(d)
        if not c or c[0] is None or c[0] >= 7 or c[1] < 18:
            curtos.append((d, "export não cobre o dia todo"))
            continue
        if len(hs) < TEMP_HORAS_MIN:
            curtos.append((d, "só %d das 12 horas com leitura do módulo" % len(hs)))
            continue
        out[d] = round(sum(vs) / len(vs), 2)
    return out, curtos


def _trapezio(pts):
    """ETM do dia (kWh/m²) do W/m² de 5 em 5 min — regras do etm_funcs.py (09/11/2026), que dão o BD da Irecê 2 e da
    Macaíba 1 ao milésimo: fora de -50..2000 descartado; negativo = 0; madrugada (00-04h) com mediana > 20 W/m² =
    sensor travado; precisa de leitura até 07h e depois das 17h; buraco > 30 min não interpola; > 12 kWh/m² fora;
    menos de 20 valores distintos de 07 a 17h = sensor parado. A mais: buraco > 30 min entre 07h e 17h = dia fora (o
    trapézio sem o buraco daria um dia menor, que entraria em célula vazia como se fosse o dia)."""
    pts = sorted(pts)
    noite = [v for t, v in pts if t.hour < 4]
    if noite and statistics.median(noite) > 20:
        return None, "sensor travado (madrugada acima de 20 W/m²)"
    p2 = [(t, max(0.0, v)) for t, v in pts if -50 <= v <= 2000]
    if not p2 or p2[0][0].time() > dt.time(7) or p2[-1][0].time() < dt.time(17):
        return None, "dia incompleto (%s a %s)" % (pts[0][0].strftime("%H:%M"), pts[-1][0].strftime("%H:%M")) \
            if pts else "sem leitura"
    tot, maior = 0.0, 0.0
    for (t0, v0), (t1, v1) in zip(p2, p2[1:]):
        h = (t1 - t0).total_seconds() / 3600
        if h > 0.5:
            if t1.time() > dt.time(7) and t0.time() < dt.time(17):
                maior = max(maior, h * 60)
            continue
        tot += (v0 + v1) / 2 * h
    if maior:
        return None, "%.0f min sem leitura no meio do dia" % maior
    kwh = tot / 1000
    if kwh > 12:
        return None, "%.1f kWh/m² — acima do possível" % kwh
    if len({round(v, 2) for t, v in p2 if 7 <= t.hour < 17}) < 20:
        return None, "sensor parado (valor repetido o dia todo)"
    return round(kwh, 3), None


class Supervisorio(Leitor):
    id = "apolo_supervisorio"
    fonte = "Supervisório (export de pontos)"
    destino = BD_PERFORMANCE

    def reconhecer(self, arq, ctx):
        if arq.ext not in (".csv", ".txt"):
            return None
        try:
            cab = arq.cabeca(40)
        except OSError:
            return None
        if not cab or not norm(cab[0]).startswith("nome do data point,tempo,valor"):
            return None
        # o cabeçalho é o do export genérico do supervisório: só fica com o arquivo se algum ponto é dos que este leitor
        # conhece (export de outra usina, com outros pontos, segue para os outros leitores). O export vem ordenado por
        # ponto: se o primeiro não é conhecido, olha a primeira coluna do arquivo todo antes de desistir.
        if not any(_conhecido(l.split(",", 1)[0]) for l in cab[1:] if l.strip()):
            primeiros = {l.split(",", 1)[0] for l in arq.texto().splitlines()[1:]}
            if not any(_conhecido(p) for p in primeiros):
                return None
        dados = _ler_scada(arq)
        if "ESTM_01" in dados["estacoes"] and not any(e in ESTACAO_APOLO for e in dados["estacoes"]):
            nome = " %s %s " % (_chave(arq.nome), _chave(arq.origem))
            if any(" %s" % k in nome for k in NOMES_ESTM_FORA):
                return None
        apolo = sorted({ESTACAO_APOLO[e] for e in dados["estacoes"] if e in ESTACAO_APOLO})
        tem_estm = "ESTM_01" in dados["estacoes"]
        estm = _usina_no_nome(arq, NOMES_ESTM) if tem_estm else None
        tipos = [t for t, k in (("ETM acumulada", "ac"), ("temperatura do módulo", "temp"),
                                ("POA/GHI de 5 em 5 min", "w")) if dados[k]]
        ests = sorted(dados["estacoes"])
        dias = sorted(dados["dias"])
        rec = Reconhecimento(self.fonte, usinas=apolo + ([estm] if estm else []),
                             periodo=(dias[0], dias[-1]) if dias else None,
                             estado={"dados": dados, "estm": estm},
                             detalhe="%s · %s" % (", ".join(sorted(tipos)) or "sem ponto que o BD usa",
                                                  ", ".join(ests)))
        if tem_estm and not estm and not apolo:
            rec.candidatas = list(ESTM)
            rec.pergunta = ("Export do supervisório da estação ESTM_01: o arquivo não diz a usina. Este leitor cobre "
                            "a Irecê 2 e a Macaíba 1 (a Cedro e a Castelo usam o mesmo ponto e ainda não estão aqui).")
        return rec

    def ler(self, arq, ctx, rec, escolha=None):
        dados = rec.estado["dados"]
        cel, avisos = [], []
        # --- Apolo: ETM acumulada e temperatura do módulo
        for aba in APOLO:
            ests = [e for e in (("GRA",) if aba == GRAVATA else ("IRA",) if aba == IRAMAIA else ORDEM_RIO)
                    if e in dados["estacoes"]]
            if not ests:
                continue
            ab = _aba_bd(ctx, aba)
            ini = _antes_da_aba(ab)
            valores, motivos = {}, {}
            for est in ests:                                       # Rio do Peixe: RPA; RPB e RPX só no que falta
                for (e, col, d), pts in dados["ac"].items():
                    if e != est or (d, col) in valores:
                        continue
                    maior, motivo = _acumulado(pts)
                    if motivo:
                        motivos.setdefault((d, col), motivo)
                    elif maior <= 0:                               # irradiação <= 0 fica vazia
                        motivos.setdefault((d, col), "acumulado do dia <= 0")
                    else:
                        valores[(d, col)] = round(maior / 3.6e6, 4)
                tt, curtos = _temperatura(dados["temp"].get((est, "m1"), {}), dados["temp"].get((est, "m2"), {}),
                                          {d: c for (e, d), c in dados["cobre"].items() if e == est})
                for d, v in tt.items():
                    valores.setdefault((d, "Temperatura"), v)
                for d, motivo in curtos:
                    motivos.setdefault((d, "Temperatura"), motivo)
            for (d, col), v in sorted(valores.items()):
                if not (ini and d < ini):             # histórico de antes da aba existir sai calado
                    cel.append(Celula(BD_PERFORMANCE, aba, d, col, v))
            fora = collections.defaultdict(list)
            for (d, col), m in sorted(motivos.items()):
                if (d, col) not in valores and not (ini and d < ini):
                    fora[d].append("%s: %s" % (col, m))
            for d in sorted(fora):
                avisos.append("%s %s: %s — ficou fora" % (aba, d.strftime("%d/%m"), "; ".join(fora[d])))
        # --- ESTM_01 (Irecê 2, Macaíba 1): W/m² de 5 em 5 min
        if dados["w"]:
            aba = rec.estado["estm"] or escolha
            if not aba:
                avisos.append("estação ESTM_01 sem usina: escolha a usina no cartão")
            elif aba not in ESTM:
                avisos.append("%s: a estação ESTM_01 só está conferida na %s — ficou fora" % (aba, " e na ".join(ESTM)))
            else:
                for (e, col, d), pts in sorted(dados["w"].items(), key=lambda x: (x[0][2], x[0][1])):
                    v, motivo = _trapezio(pts)
                    if motivo:
                        avisos.append("%s %s %s: %s — ficou fora" % (aba, d.strftime("%d/%m"), col, motivo))
                    elif v > 0:
                        cel.append(Celula(BD_PERFORMANCE, aba, d, col, v))
        outras = sorted(e for e in dados["estacoes"] if e not in ESTACAO_APOLO and e != "ESTM_01")
        if outras:
            avisos.append("estação(ões) %s fora do de-para — ficaram fora" % ", ".join(outras))
        return cel, avisos


LEITORES = [SmartLogger, Datalogger, Supervisorio]
