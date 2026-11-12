# -*- coding: utf-8 -*-
"""Portal da Sal Energia -> BD_Performance (Quixadá 1 e 2, Aquiraz 1 e 2). Veio do "Sal Energia para o BD.exe"
(08/11/2026, ferramentas/sal_energia/sal_para_colar.py); as regras de colar agora são as do núcleo (montagem.py).

Reconhece pelo CONTEÚDO (o portal põe data e hora no nome do arquivo):
- "INV - GERAÇÃO_Relatório mensal": "Nome da usina | Horário | Nome do dispositivo(Inversor) | S/N do dispositivo |
  ... | Geração de energia(kWh)", uma linha por inversor e dia.
- "Irradiação diária_Relatório mensal": "Nome da usina | Horário | ... | Irradiação diária da usina(Wh/㎡)". A diária
  ÷ 1000 é o IPOA (kWh/m²) do BD — conferido em outubro/2026, igual ao BD nas três usinas com estação.

De-para (08/11/2026, 26-27 de 31 dias iguais ao BD em cada inversor): "Inverter_NN" em qualquer grafia ("Inverter _01",
"Inverter_ 04", "Inverter_01_") = Inversor 1.NN. A Vitesse não tem estação: o IPOA dela no BD é fórmula (= Hortina) e
nunca sai daqui. Dispositivo sem S/N de verdade fica fora (a Salvales lista um "Inverter_04" com S/N "1.0", tudo 0,
além do inversor 04 real)."""
import re

from conversor.nucleo import (BD_PERFORMANCE, Celula, Leitor, Reconhecimento, data_de, norm, num)

USINAS = {                      # nome no portal (normalizado) -> (aba do BD_Performance, IPOA sai daqui?)
    "hortina": ("Quixadá 1 (Hortina)", True),
    "vitesse": ("Quixadá 2 (Vitesse)", False),
    "salvales": ("Aquiraz 1 (Salvales)", True),
    "carosa": ("Aquiraz 2 (Carosa)", True),
}
N_INV = 10


def _sn_valido(sn):
    return bool(re.fullmatch(r"[A-Za-z0-9]{6,}", str(sn or "").strip()))


def _inversor(nome):
    # "\w" engoliria o "_10" e o 10 virava 0: depois de "inverter" só não-dígitos até o número
    m = re.search(r"invert[a-z]*\D*(\d+)", norm(nome))
    return "Inversor 1.%d" % int(m.group(1)) if m and 1 <= int(m.group(1)) <= N_INV else None


def _tabela(arq):
    """(tipo, linhas) — tipo 'geracao' ou 'irradiacao'; linhas = [dict por coluna reconhecida]."""
    if arq.ext not in (".xlsx", ".xlsm"):
        return None, []
    for _, linhas in arq.planilhas():
        for i, r in enumerate(linhas[:15]):
            h = [norm(x) for x in r]
            if "nome da usina" not in h or "horario" not in h:
                continue
            col = {"usina": h.index("nome da usina"), "data": h.index("horario")}
            for j, x in enumerate(h):
                if x.startswith("nome do dispositivo"):
                    col["disp"] = j
                elif x.startswith("s/n do dispositivo"):
                    col["sn"] = j
                elif x.startswith("geracao de energia") and "total" not in x and "teoric" not in x:
                    # o portal pode trazer também "Geração de energia total" (contador) e "... teórica por dia";
                    # a do dia é a que não tem nem uma nem outra
                    col["ger"] = j
                elif x.startswith("irradiacao diaria da usina"):
                    col["irr"] = j
            tipo = "geracao" if {"disp", "ger"} <= set(col) else ("irradiacao" if "irr" in col else None)
            if not tipo:
                continue
            dados = [{k: (r2[j] if j < len(r2) else None) for k, j in col.items()}
                     for r2 in linhas[i + 1:] if r2 and not all(x in (None, "") for x in r2)]
            return tipo, dados
    return None, []


class PortalSal(Leitor):
    id = "sal"
    fonte = "Portal Sal Energia"
    destino = BD_PERFORMANCE

    def reconhecer(self, arq, ctx):
        tipo, dados = _tabela(arq)
        if not tipo:
            return None
        usinas = sorted({USINAS[norm(d["usina"])][0] for d in dados if norm(d["usina"]) in USINAS})
        dias = [x for x in (data_de(d["data"]) for d in dados) if x]
        desconhecidas = sorted({str(d["usina"]) for d in dados if norm(d["usina"]) not in USINAS})
        rec = Reconhecimento(self.fonte, usinas=usinas, periodo=(min(dias), max(dias)) if dias else None,
                             estado=(tipo, dados),
                             detalhe="Geração por inversor" if tipo == "geracao" else "Irradiação diária (IPOA)")
        if not usinas:
            rec.candidatas = [a for a, _ in USINAS.values()]
            rec.pergunta = ("O relatório é do portal da Sal Energia, mas a usina %s não está no de-para."
                            % ", ".join(repr(u) for u in desconhecidas[:3]))
        return rec

    def ler(self, arq, ctx, rec, escolha=None):
        tipo, dados = rec.estado
        cel, avisos, fantasmas = [], [], set()
        for d in dados:
            u = USINAS.get(norm(d["usina"]))
            aba, tem_ipoa = u if u else ((escolha, True) if escolha else (None, False))
            dia = data_de(d["data"])
            if not aba:
                avisos.append("Usina desconhecida no portal: %r" % d["usina"])
                continue
            if not dia:
                continue
            if tipo == "irradiacao":
                v = num(d["irr"])
                if v is not None and tem_ipoa:
                    cel.append(Celula(BD_PERFORMANCE, aba, dia, "IPOA", round(v / 1000, 3)))
                continue
            col = _inversor(d["disp"])
            if not col:
                avisos.append("%s: dispositivo sem número de inversor reconhecível: %r" % (aba, d["disp"]))
                continue
            if not _sn_valido(d.get("sn")):
                if (aba, d["disp"]) not in fantasmas:
                    fantasmas.add((aba, d["disp"]))
                    avisos.append("%s: dispositivo %r com S/N %r ficou fora (sem número de série de verdade)"
                                  % (aba, str(d["disp"]).strip(), d.get("sn")))
                continue
            v = num(d["ger"])
            if v is not None:
                cel.append(Celula(BD_PERFORMANCE, aba, dia, col, v))
        return cel, avisos


LEITORES = [PortalSal]
