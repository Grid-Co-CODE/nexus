# -*- coding: utf-8 -*-
"""EMI da Huawei (estação ligada ao SmartLogger) -> BD_Performance, coluna IPOA.

Formato (Macaíba 1, "EMI_20261109164123.tar.gz" baixado do SmartLogger em 09/11/2026; o núcleo abre o pacote): um CSV
    #SmartLogger SN:102180338384
    #Sensor SN:EM03102180338384
    #Time,DST,WSP(m/s),WD,PV Temp.(degC),Amp Temp.(degC),Status,Total irradi.(W/m^2),Total irradi. 2(W/m^2),
         Daily irradiat(kWh/m^2),Daily irradiat 2(kWh/m^2),custom1,custom2
com uma leitura a cada 5 min, da mais nova para a mais velha; "--" = sem leitura.

IPOA do dia = o "Daily irradiat" do fim do dia (o maior do dia): é o acumulado que o próprio SmartLogger soma. Em 88
dias (11/08 a 08/11/2026) deu, em mediana, 1,003 vezes o IPOA do BD e 1,26 vezes o GHI — é o sensor do plano dos
módulos. Não usa nucleo.num(): ele lê "5.969" como 5969 (milhar pt-BR) e o EMI grava o acumulado com ponto e três casas.

Só dia completo: o sensor em 0 antes do nascer e depois do pôr do sol, e nenhuma leitura faltando enquanto há sol. O
plano feito à mão em 09/11 aceitou o 21/10 (5,969) porque a última leitura era 23:55, mas o arquivo não tem leitura de
08:05 a 10:55 e o acumulado foi de 1,407 para 1,450 nesse buraco: o SmartLogger não somou a manhã (o BD tem hoje 7,48
nesse dia). À noite a irradiância vem exatamente 0,0 (9.635 leituras noturnas de Macaíba), então "0 nas pontas" não
depende de horário de nascer/pôr do sol de cada usina.

Só dia vazio no BD: o EMI é um segundo sensor; o IPOA do BD vem da estação principal e os dois variam ±3% de um dia para
o outro. A regra do núcleo trocaria o BD sempre que o EMI viesse 1% acima, misturando sensores na mesma coluna — em
09/11 só os dias sem IPOA entraram ("não troquei nenhum, para não misturar os dois sensores"). Enquanto a Celula não
tiver como dizer "só vazio" ao núcleo, o filtro mora aqui.

GHI fica de fora: "Total irradi. 2" e "Daily irradiat 2" vêm "--" nas 25.919 leituras de Macaíba (a estação não mede
GHI). Se um arquivo trouxer o sensor 2, vira aviso, sem mapear — nada confirma que ele é o GHI. Temperatura também:
"PV Temp." vem "--" e "Amp Temp." é a do ar, não a do módulo."""
import collections
import datetime as dt
import os
import re

from conversor.nucleo import BD_PERFORMANCE, Celula, Leitor, Reconhecimento, br, datahora_de, norm

SMARTLOGGER = {                 # SN do SmartLogger -> aba do BD_Performance
    "102180338384": "Macaiba 1",  # 09/11/2026: o EMI dele bate 1,003x o IPOA da aba em 88 dias
}
COLUNA = "IPOA"
NOTA = "EMI do SmartLogger (segundo sensor): só dia vazio no BD"

Dia = collections.namedtuple("Dia", "valor completo motivo n primeira ultima")


def _valor(x):
    """'9.458' -> 9.458; '--' ou vazio -> None."""
    s = str(x if x is not None else "").strip()
    if not s or not s.strip("-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _hora(s):
    s = str(s or "").strip()
    try:
        return dt.datetime.fromisoformat(s)      # "2026-11-09 16:40:00"; strptime levava 1 s nas 26 mil linhas
    except ValueError:
        pass
    if not re.search(r"\d:\d\d", s):
        return None
    return datahora_de(s)


def _cabecalho(linhas):
    """{'sn', 'sensor', 'sep', 'col': {t, inst, acc, inst2, acc2}} das primeiras linhas, ou None se não for o EMI."""
    info = {"sn": None, "sensor": None}
    for l in linhas:
        s = l.strip().lstrip("\ufeff")
        m = re.match(r"#\s*smartlogger\s*sn\s*:\s*([0-9A-Za-z]+)", s, re.I)
        if m:
            info["sn"] = m.group(1)
            continue
        m = re.match(r"#\s*sensor\s*sn\s*:\s*([0-9A-Za-z]+)", s, re.I)
        if m:
            info["sensor"] = m.group(1)
            continue
        if not re.match(r"#\s*time\s*[,;\t]", s, re.I):
            continue
        sep = max((",", ";", "\t"), key=s.count)
        col = {}
        for j, h in enumerate(norm(x) for x in s.lstrip("#").split(sep)):
            if h == "time":
                col["t"] = j
            elif re.match(r"daily irradiat\.?\s*2", h):
                col["acc2"] = j
            elif h.startswith("daily irradiat"):
                col["acc"] = j
            elif re.match(r"total irradi\.?\s*2", h):
                col["inst2"] = j
            elif h.startswith("total irradi"):
                col["inst"] = j
        if "t" not in col or "acc" not in col:
            return None
        info.update(sep=sep, col=col)
        return info
    return None


def leituras(texto, info):
    """[(datetime, irradiância W/m² ou None, acumulado kWh/m² ou None, acumulado do sensor 2 ou None)], em ordem de hora,
    sem hora repetida."""
    sep, col = info["sep"], info["col"]
    vistos = {}

    def pega(r, k):
        j = col.get(k)
        return _valor(r[j]) if j is not None and j < len(r) else None

    for l in texto.splitlines():
        if not l.strip() or l.lstrip().startswith("#"):
            continue
        r = l.split(sep)
        t = _hora(r[col["t"]]) if col["t"] < len(r) else None
        if t is None:
            continue
        vistos.setdefault(t, (t, pega(r, "inst"), pega(r, "acc"), pega(r, "acc2")))
    return [vistos[t] for t in sorted(vistos)]


def _passo(pts):
    """intervalo do registro (o mais comum entre duas leituras seguidas): 5 min em Macaíba."""
    dif = collections.Counter(b[0] - a[0] for a, b in zip(pts, pts[1:]) if b[0] > a[0])
    return dif.most_common(1)[0][0] if dif else dt.timedelta(minutes=5)


def dias(pts):
    """{date: Dia} — o IPOA de cada dia e se o dia está completo (motivo diz por que não)."""
    passo = _passo(pts)
    folga = passo * 1.5                          # mais que isso entre duas leituras = faltou pelo menos uma
    grupos = collections.defaultdict(list)
    for p in pts:
        grupos[p[0].date()].append(p)
    out = {}
    for d, p in sorted(grupos.items()):
        acc = [x[2] for x in p if x[2] is not None]
        ini, fim = p[0][0].strftime("%H:%M"), p[-1][0].strftime("%H:%M")
        if not acc:
            out[d] = Dia(None, False, "sem Daily irradiat", len(p), ini, fim)
            continue
        valor = round(max(acc), 3)
        motivo = None
        ant = None
        for x in p:                              # acumulado não volta: se voltou, o SmartLogger zerou no meio do dia
            if x[2] is None:
                continue
            if ant is not None and x[2] < ant - 0.0005:
                motivo = "o acumulado volta de %.3f para %.3f às %s" % (ant, x[2], x[0].strftime("%H:%M"))
                break
            ant = x[2]
        tem_inst = any(x[1] is not None for x in p)
        if motivo is None and tem_inst:
            sol = [i for i, x in enumerate(p) if (x[1] or 0) > 0]
            if not sol:
                motivo = "sensor em 0 o dia todo"
            elif sol[0] == 0:
                motivo = "começa às %s já com sol" % ini
            elif sol[-1] == len(p) - 1:
                motivo = "termina às %s ainda com sol" % fim
            elif p[sol[0] - 1][1] is None or p[sol[-1] + 1][1] is None:
                # "--" na leitura antes do primeiro sol (ou depois do último): não dá para ver se o dia estava inteiro
                x = p[sol[0] - 1] if p[sol[0] - 1][1] is None else p[sol[-1] + 1]
                motivo = "sem a irradiância às %s, na ponta do dia" % x[0].strftime("%H:%M")
            else:
                for a, b in zip(p[sol[0] - 1:sol[-1] + 1], p[sol[0]:sol[-1] + 2]):
                    if b[0] - a[0] > folga:
                        motivo = "sem leitura de %s a %s" % (a[0].strftime("%H:%M"), b[0].strftime("%H:%M"))
                        break
        elif motivo is None:
            # sem a irradiância instantânea não dá para ver o sol: exige o dia inteiro, sem buraco
            meia_noite = dt.datetime(d.year, d.month, d.day)
            if p[0][0] - meia_noite > folga or meia_noite + dt.timedelta(days=1) - p[-1][0] > folga:
                motivo = "leituras de %s a %s (sem a irradiância para ver o sol, só vale o dia inteiro)" % (ini, fim)
            else:
                for a, b in zip(p, p[1:]):
                    if b[0] - a[0] > folga:
                        motivo = "sem leitura de %s a %s" % (a[0].strftime("%H:%M"), b[0].strftime("%H:%M"))
                        break
        out[d] = Dia(valor, motivo is None, motivo, len(p), ini, fim)
    return out


def _cauda(caminho, n=4096):
    """últimas linhas do arquivo sem ler tudo (o EMI vem da mais nova para a mais velha: a data mais antiga está no fim)."""
    try:
        with open(caminho, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - n))
            return f.read().decode("latin-1", "replace").splitlines()[1:]
    except OSError:
        return []


class EmiHuawei(Leitor):
    id = "huawei_emi"
    fonte = "EMI Huawei (SmartLogger)"
    destino = BD_PERFORMANCE

    def reconhecer(self, arq, ctx):
        if arq.ext not in (".csv", ".txt"):
            return None
        try:
            cab = arq.cabeca(12)
            info = _cabecalho(cab)
            if not info:
                return None
            datas, jt = [], info["col"]["t"]
            for l in cab + _cauda(arq.caminho):
                r = l.split(info["sep"])
                t = _hora(r[jt]) if not l.lstrip().startswith("#") and jt < len(r) else None
                if t:
                    datas.append(t.date())
        except Exception:                        # arquivo de outro formato não pode derrubar a tela
            return None
        aba = SMARTLOGGER.get(info["sn"])
        rec = Reconhecimento(self.fonte, usinas=[aba] if aba else [], estado=info,
                             periodo=(min(datas), max(datas)) if datas else None,
                             detalhe="IPOA (Daily irradiat) · SmartLogger %s" % (info["sn"] or "sem SN"))
        if not aba:
            abas = (ctx.abas(BD_PERFORMANCE) if ctx else []) or sorted(set(SMARTLOGGER.values()))
            rec.candidatas = ([a for a in abas if norm(a).startswith("macaiba")] +
                              [a for a in abas if not norm(a).startswith("macaiba")])
            rec.pergunta = ("O arquivo é o EMI (estação) de um SmartLogger da Huawei, mas o SmartLogger %s não está no "
                            "de-para. De qual usina é?" % (info["sn"] or "sem número de série"))
        return rec

    def ler(self, arq, ctx, rec, escolha=None):
        info = rec.estado
        aba = SMARTLOGGER.get(info["sn"]) or escolha
        if not aba:
            return [], ["SmartLogger %s sem usina: nada foi lido" % info["sn"]]
        pts = leituras(arq.texto(), info)
        ds = dias(pts)
        avisos = []
        if any(x[3] is not None for x in pts):
            avisos.append("o arquivo traz o segundo sensor (Daily irradiat 2) — ficou de fora: nada confirma que ele é "
                          "o GHI da usina")
        fora = [(d, x) for d, x in sorted(ds.items()) if not x.completo]
        if fora:
            avisos.append("%d dia(s) incompleto(s) ficaram de fora: %s" % (
                len(fora), "; ".join("%s (%s)" % (br(d), x.motivo) for d, x in fora[:8]) +
                ("; ..." if len(fora) > 8 else "")))
        # so_vazio: o núcleo nunca troca número do BD por valor do EMI (outro sensor, ±3% da estação do BD) — nem
        # pela regra do "maior"; só preenche dia vazio
        ab = ctx.aba(BD_PERFORMANCE, aba) if ctx else None
        j = ab.col(COLUNA) if ab else None
        cel, ja_tem = [], 0
        for d, x in sorted(ds.items()):
            if not x.completo:
                continue
            b = ab.valor(d, j) if j is not None else None
            if isinstance(b, (int, float)) and not isinstance(b, bool) and b > 0:
                ja_tem += 1
            cel.append(Celula(BD_PERFORMANCE, aba, d, COLUNA, x.valor, NOTA, True))
        if ja_tem:
            avisos.append("%d dia(s) já têm IPOA no BD e ficaram com o BD: o EMI é um segundo sensor (varia ±3%% da "
                          "estação do BD) e só preenche dia vazio" % ja_tem)
        return cel, avisos


LEITORES = [EmiHuawei]
