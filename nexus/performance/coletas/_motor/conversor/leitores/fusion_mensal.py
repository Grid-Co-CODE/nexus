# -*- coding: utf-8 -*-
"""Relatório mensal INV do portal (FusionSolar) -> BD_Thopen. Veio dos scripts de 30/10/2026 (Altair, Indaiatuba,
Mandaguaçu, Taguaí, Matão 2: 546 células) e de 03/11/2026 (lote "COLETA POLARIS OUTUBRO", 48 usinas, casa_mensal.py).

Formato (aba "Report"): duas linhas de título ("Relatorio mensal INV_Mensal_AAAAMM") e o cabeçalho na linha 3:
"Nome da usina | Horário | Nome do dispositivo(Inversor) | S/N do dispositivo | Número de série do equipamento de
comunicação | Geração de energia(kWh) | Geração de energia total(kWh) | Geração de energia teórica por dia(kWh)", uma
linha por inversor e dia. A "usina" do portal é a planta ou a subusina ("Altair 1".."Altair 5", "Ceilândia 2 -
Atena", "Segredo 3, 4 e 5", "UFV Thopen - Sitio Bonfim"); várias caem na mesma aba do BD_Thopen.

O cabeçalho é o MESMO do portal da Sal Energia (leitor sal, BD_Performance). Quem separa é a usina: este leitor só
fica com o arquivo se alguma planta casar pelo nome com uma aba do BD_Thopen (ou estiver no de-para conhecido).

De-para: a ordem dos "InverterN" NÃO é a natural (Altair 1: Inverter1 = 1.2, Inverter6 = 1.1) e o nome às vezes
engana (Segredo 3: os "Inversor3.N" estão mortos, sem S/N e só com 0; os 3.x de verdade são Inverter33..40). Por isso
a coluna sai SEMPRE pela geração, inversor a inversor, contra os dias que o BD já tem:
1. de-para conhecido (DEPARA, abaixo), usado se a geração não o contradiz. Contradiz quando outra coluna (ou outro
   inversor) é igual ao centavo em >= MIN_DIAS dias e em mais dias do que o par conhecido; aí o inversor fica fora,
   com aviso (de-para mudou ou o BD gravou trocado: alguém confere no portal antes de colar);
2. sem de-para conhecido: a coluna igual ao centavo em >= MIN_DIAS dias, com "melhor dos dois lados" e sem empate
   (a coluna é a melhor do inversor E o inversor é o melhor da coluna, cada um com folga sobre o segundo).
Inversor sem casamento seguro não vira célula: vira aviso com o motivo. Mês sem nenhum dia no BD para casar: só o de-
para conhecido; sem ele, o inversor fica fora.

O que o arquivo traz: valor do dia, 0 inclusive (no mensal de 03/11 todo 0 vem com o contador "Geração de energia
total" presente e parado: é inversor desligado, leitura de verdade); célula vazia do portal não vira nada. O dia aberto
o portal deixa vazio (mensal de 30/10 09:03: o 30/10 em branco nos 92 inversores); pela hora no nome do arquivo o dia
da exportação sai mesmo assim. As regras de colar (só o que for a mais ou vazio, 0 nunca por cima, dia com colunas
trocadas, sem dia de hoje) são do núcleo."""
import collections
import datetime as dt
import re

from conversor.nucleo import BD_THOPEN, Celula, Leitor, Reconhecimento, data_de, norm, norm_cab, num

IGUAL = 0.005      # "igual ao centavo": 12.627 de 13.336 dias dos pares de 03/11 batem com diferença 0; o resto erra
                   # por 0,1 ou mais (arredondamento do portal x API), então não há meio-termo a calibrar
MIN_DIAS = 3       # casa_mensal.py (03/11): >= 3 dias iguais; Brodowski 1 só tinha 4 dias com geração no mês
SEM_GERACAO = "sem geração no mês (só 0 ou vazio)"


# ---------------------------------------------------------------- de-para conhecido
def _ordem(grupo, *nums):
    """"InverterN" em ordem -> coluna: _ordem(1, 2, 5) = {Inverter1: Inversor 1.2, Inverter2: Inversor 1.5}."""
    return {"Inverter%d" % i: "Inversor %d.%d" % (grupo, n) for i, n in enumerate(nums, 1)}


def _natural(fmt, grupo, n, inicio=1):
    """dispositivo com o número da coluna: _natural('Inversor %d', 1, 10) = {Inversor 1: Inversor 1.1, ...}."""
    return {fmt % i: "Inversor %d.%d" % (grupo, i) for i in range(inicio, n + 1)}


def _pares(grupo, texto):
    """'41=5 42=3' -> {Inverter41: Inversor g.5, Inverter42: Inversor g.3}."""
    return {"Inverter%s" % a: "Inversor %d.%s" % (grupo, b) for a, b in (p.split("=") for p in texto.split())}


def _sapopema():
    # 03/11: SG125HV NN = 1.NN; os três trocados no portal viraram Inverter19 = 1.5, Inverter20 = 1.4, Inverter21 =
    # 1.10 (o SG125HV 10 ficou no relatório só com 0). O SG125HV 19 e o 20 continuam sendo 1.19 e 1.20.
    d = {"SG125HV %02d" % i: "Inversor 1.%d" % i for i in range(1, 21) if i not in (4, 5, 10)}
    d.update({"Inverter19": "Inversor 1.5", "Inverter20": "Inversor 1.4", "Inverter21": "Inversor 1.10"})
    return d


def _tanabi():
    # 03/11: TNBg_INnn = g.nn, menos TNB1_IN07 e TNB1_IN16 (sem S/N, só 0): Inverter42 = 1.7, Inverter41 = 1.16
    d = {"TNB%d_IN%02d" % (g, i): "Inversor %d.%d" % (g, i) for g in (1, 2) for i in range(1, 21)
         if (g, i) not in ((1, 7), (1, 16))}
    d.update({"Inverter41": "Inversor 1.16", "Inverter42": "Inversor 1.7"})
    return d


def _segredo(grupos):
    d = {"Inversor%d.%d" % (g, i): "Inversor %d.%d" % (g, i) for g in grupos if g != 3 for i in range(1, 9)}
    if 3 in grupos:
        # 03/11: os "Inversor3.N" estão sem S/N e só com 0; o grupo 3 de verdade é Inverter33..40 fora de ordem
        d.update(_pares(3, "33=6 34=1 35=8 36=7 37=4 38=2 39=3 40=5"))
    return d


# planta no portal -> (aba do BD_Thopen, {dispositivo no portal: coluna do BD}). Fonte: memória
# depara-relatorio-mensal-fusion-thopen (30/10, casado pela geração, 20-28 dias por inversor) e casa_mensal.json de
# 03/11 (48 usinas, >= 3 dias iguais ao centavo, colado no BD e no PG em 04/11): 486 pares, iguais às duas fontes.
# Conferido em 10/11/2026: contra o BD de 03/11 (antes da colagem) a geração sozinha acha os 486 e nenhum diverge;
# contra o BD de 10/11, 472 confirmados e os 14 da Brodowski 1 contraditos. Dispositivo fora daqui casa pela geração.
DEPARA = {
    # 30/10: Inverter8 = 1.3 por 02/10 igual; Inverter5 = 1.8 por eliminação (depois de 02/10 a API gravava valor
    # parado no 1.5 e no 1.8, ~300 e ~45/dia): é o caso em que o de-para conhecido vale sem dia igual no BD
    "Altair 1": ("Altair", _ordem(1, 2, 5, 6, 4, 8, 1, 7, 3)),
    "Altair 2": ("Altair", _ordem(2, 4, 7, 2, 8, 6, 5, 1, 3)),
    "Altair 3": ("Altair", _ordem(3, 8, 4, 6, 2, 3, 5, 1, 7)),
    "Altair 4": ("Altair", _ordem(4, 4, 8, 3, 6, 2, 7, 5, 1)),
    "Altair 5": ("Altair", _ordem(5, 3, 2, 5, 4, 1, 7, 6, 8)),
    # 30/10: "INV10-SUBSTITUIDO" vem vazio/0 e o 1.10 de hoje é o Inverter15; o 2.1 não tem relatório
    "Indaiatuba 1": ("Indaiatuba", dict(_ordem(1, 1, 5, 9, 2, 6, 3, 7, 4, 8), Inverter15="Inversor 1.10")),
    "Indaiatuba 2": ("Indaiatuba", {"Inverter1": "Inversor 2.2"}),
    "Indaiatuba 3": ("Indaiatuba", _ordem(3, 4, 1, 2, 3)),
    "Indaiatuba 4": ("Indaiatuba", _ordem(4, 2, 1)),
    "Mandaguaçu 1": ("Mandaguaçu", _ordem(1, 5, 6, 3, 4, 1, 2, 7, 8)),
    "Mandaguaçu 2": ("Mandaguaçu", _ordem(2, 4, 3, 2, 1, 8, 7, 6, 5)),
    "Mandaguaçu 3": ("Mandaguaçu", _ordem(3, 4, 1, 3, 2)),
    # 03/11: 8 a 26 dias iguais por inversor; 16-21/10 o BD tinha metade das colunas trocadas (o núcleo segura o dia)
    "Mandaguaçu 4": ("Mandaguaçu", _ordem(4, 12, 19, 6, 14, 1, 20, 8, 16, 3, 11, 18, 5, 13, 7, 15, 2, 10, 9, 17, 4)),
    # 30/10: Inverter2 = 1.3 por eliminação (o portal fica 0,2-0,7% acima do BD); o 2.x não vinha nesse relatório
    "UFV Taguai 1": ("Taguaí", _ordem(1, 4, 3, 2, 1)),
    "UFV Taguai 2": ("Taguaí", _ordem(2, 1, 2)),
    "UFV Matão 2": ("Matão 2", _natural("Inversor %d", 1, 10)),
    "UFV Sapopema": ("Sapopema", _sapopema()),
    # 03/11 (casa_mensal.json): Barretos 1 sem o Inverter18 e Barretos 2 sem o Inverter21, que o BD não tem
    "Barretos 1": ("Barretos", _ordem(1, 1, 16, 15, 5, 19, 7, 17, 4, 2, 3, 12, 14, 18, 11, 6, 9, 8)
                   | _pares(1, "19=13 20=10")),
    "Barretos 2": ("Barretos", _ordem(2, 18, 13, 4, 17, 20, 15, 3, 6, 12, 16, 19, 7, 5, 2, 8, 14, 1, 10, 11, 9)),
    # 10/11: o BD de hoje tem o 1.x da Brodowski noutra ordem (29-31/10 permutados depois de 04/11, com o Inverter17
    # e o 18 no 1.5 e no 1.3) e a geração contradiz os 14 pares abaixo, 3 dias cada: o leitor segura todos até
    # alguém decidir qual ordem vale e corrigir aqui
    "Brodowski 1": ("Brodowski", _pares(1, "2=14 3=13 4=12 5=16 6=15 7=8 8=9 9=4 10=5 12=6 13=7 14=1 15=2 16=3")),
    "Brodowski 2": ("Brodowski", _ordem(2, 3, 4, 1, 2, 13, 7, 12, 8, 11, 5, 10, 6, 16, 15, 9, 14)),
    # 03/11: 40 dispositivos no portal para 20 colunas; os outros 20 vêm só com 0 (metade sem S/N)
    "Cambé": ("Cambé", _pares(1, "1=3 2=17 7=16 8=6 9=15 11=20 12=11 14=2 15=9 16=8 19=5 21=7 22=19 23=13 24=4 "
                                 "26=18 27=14 28=12 29=1 40=10")),
    "Ceilândia 2 - Pinheiro": ("Ceilândia 2", _ordem(1, 11, 5, 7, 3, 2, 10, 9, 4, 12, 6, 1, 8)),
    "Ceilândia 2 - Pitangueira": ("Ceilândia 2", _ordem(2, 1, 5, 6, 4, 9, 7, 8, 2)),
    "Ceilândia 2 - Atena": ("Ceilândia 2", _ordem(3, 3, 2, 5, 6, 4, 1)),
    "Ceilândia 2 - Cedro Rosa": ("Ceilândia 2", _ordem(4, 1, 3, 2, 8, 5, 4, 7, 6)),
    "Cidade Gaucha": ("Cidade Gaucha", _pares(1, "41=5 42=3 43=16 44=4 45=15 46=12 47=10 48=2 49=14 50=8 51=18 "
                                                 "52=11 53=6 54=17 55=13 56=7 57=19 58=1 59=20 60=9")),
    "Itajá 1": ("Itajá", _ordem(1, 4, 3, 1, 2)),
    "Itajá 2": ("Itajá", _ordem(2, 1, 3, 2, 4)),
    "OURO BRANCO 1": ("Ouro Branco 1", {"Inversor%02d" % i: "Inversor 1.%d" % c
                                        for i, c in enumerate((9, 6, 1, 3, 7, 4, 8, 5, 2), 1)}),
    "OURO BRANCO 2": ("Ouro Branco 2", {"Inversor01": "Inversor 1.9", "Inversor02": "Inversor 1.5",
                                        "Inversor03": "Inversor 1.1", "Inversor04": "Inversor 1.4",
                                        "Inversor05": "Inversor 1.3", "Inversor06": "Inversor 1.6",
                                        "Inversor07": "Inversor 1.2", "inversor08": "Inversor 1.8",
                                        "inversor09": "Inversor 1.7"}),
    "OURO BRANCO 3": ("Ouro Branco 3", {"Inversor 01": "Inversor 1.1", "inversor 02": "Inversor 1.2",
                                        "inversor 03": "Inversor 1.3", "inversor 04": "Inversor 1.4"}),
    "OURO BRANCO 4": ("Ouro Branco 4", {"Inversor01": "Inversor 1.2", "Inversor02": "Inversor 1.3",
                                        "Inversor03kenoa": "Inversor 1.4", "Inversor04kenoa": "Inversor 1.1"}),
    "OURO BRANCO 5": ("Ouro Branco 5", {"Inversor01": "Inversor 1.1", "Inversor02": "Inversor 1.3",
                                        "Inversor03": "Inversor 1.2", "Inversor04": "Inversor 1.4"}),
    "Parelhas": ("Parelhas", _pares(1, "5=2 6=1 7=4 8=3")),
    "Rodrigues 1": ("Rodrigues 1", _pares(1, "5=4 6=3 7=2 8=1")),
    # 03/11: INVab-2.c = c.a (INV01-2.2 = 2.1, INV02-2.3 = 3.2)
    "Rodrigues 2": ("Rodrigues 2", {"INV01-2.1": "Inversor 1.1", "INV02-2.1": "Inversor 1.2",
                                    "INV03-2.1": "Inversor 1.3", "INV04-2.1": "Inversor 1.4",
                                    "INV01-2.2": "Inversor 2.1", "INV02-2.2": "Inversor 2.2",
                                    "INV01-2.3": "Inversor 3.1", "INV02-2.3": "Inversor 3.2"}),
    "Segredo 1 e 2": ("Segredo", _segredo((1, 2))),
    "Segredo 3, 4 e 5": ("Segredo", _segredo((3, 4, 5))),
    "Sitio dos Nogueiras": ("Sitio dos Nogueiras", {"Inverter %d.%d" % (g, i): "Inversor %d.%d" % (g, i)
                                                    for g in range(1, 5) for i in range(1, 5)}),
    "Tanabi 1 e 2": ("Tanabi", _tanabi()),
    "UFV Aparecida do Taboado I": ("Aparecida do Taboado 1", dict(_natural("Inverter%d", 1, 14, 2),
                                                                  Inversor_01="Inversor 1.1")),
    "UFV Aparecida do Taboado II": ("Aparecida do Taboado 2", _natural("Inversor %d", 2, 14)),
    "UFV Bernardino de Campos": ("Bernardino", _ordem(1, 3, 1, 2, 4)),
    # 11/11/2026: o BD tinha o 1.4 e o 1.5 trocados de 18/07 a 10/11 (o supervisório da OEM troca os nomes; corrigido no
    # BD e no coletar_pg). O Inverter-4, parado o mês todo (COS: o 1.4 parado), é o 1.4; o Inverter-5 é o 1.5
    "UFV Ipixuna 1": ("Ipixuna 1", {"Inverter-%d" % i: "Inversor 1.%d" % c
                                    for i, c in enumerate((1, 2, 9, 4, 5, 8, 6, 3, 7), 1)}),
    # 11/11/2026: "Inversor-2" = 2.2 e "Inverter 4" = 2.4 pela ordem natural dos outros 11 (todos casados pela geração);
    # o BD não tem nenhum dia da 2.2 em novembro (o PG não entrega esse inversor), então ela não casava sozinha
    "UFV Ipixuna 2": ("Ipixuna 2", {"Inverter-1": "Inversor 2.1", "Inversor-2": "Inversor 2.2",
                                    "Inversor-3": "Inversor 2.3", "Inverter 4": "Inversor 2.4",
                                    "Inverter-5": "Inversor 2.5", "Inversor-6": "Inversor 2.6",
                                    "Inversor-7": "Inversor 2.7", "Inverter-8": "Inversor 2.8",
                                    "Inverter-9": "Inversor 2.9", "Inverter-10": "Inversor 2.10",
                                    "Inversor-11": "Inversor 2.11", "Inverter-12": "Inversor 2.12",
                                    "Inverter-13": "Inversor 2.13"}),
    "UFV SENADOR 1": ("Senador", _ordem(1, 1, 3, 2, 4)),
    "UFV Thopen - Sitio Bonfim": ("Sitio Bonfim", _ordem(1, 3, 2, 1, 4)),
}


# ---------------------------------------------------------------- nome da planta -> aba
_RUIDO = {"ufv", "usina", "thopen"}
_ROMANOS = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9",
            "x": "10", "xi": "11", "xii": "12"}


def _chave(s):
    """'UFV Aparecida do Taboado II' -> ('aparecida', 'do', 'taboado', '2'); 'UFV Thopen - Sitio Bonfim' ->
    ('sitio', 'bonfim'). Mesmo tratamento dos dois lados (planta e aba), então o romano da Santo Inácio XII também casa."""
    return tuple(_ROMANOS.get(t, t) for t in re.sub(r"[^a-z0-9]+", " ", norm(s)).split() if t not in _RUIDO)


def _abas_pelo_nome(planta, abas):
    """Abas do BD cujo nome casa com a planta: igual; senão um é prefixo do outro, palavra a palavra, e fica o mais
    longo ('Altair 3' -> Altair, 'Ceilândia 2 - Atena' -> Ceilândia 2, 'UFV Bernardino de Campos' -> Bernardino).
    Empate devolve todas: quem decide a coluna é a geração."""
    p = _chave(planta)
    if not p:
        return []
    chaves = {a: _chave(a) for a in abas}
    iguais = [a for a, k in chaves.items() if k == p]
    if iguais:
        return iguais
    melhor, out = 0, []
    for a, k in chaves.items():
        n = min(len(k), len(p))
        if n and k[:n] == p[:n]:
            if n > melhor:
                melhor, out = n, [a]
            elif n == melhor:
                out.append(a)
    return out


_DEPARA_N = {norm(p): (aba, {norm(d): c for d, c in m.items()}) for p, (aba, m) in DEPARA.items()}


# ---------------------------------------------------------------- arquivo
def _cel(r, j):
    return r[j] if j is not None and j < len(r) else None


def _tabela(arq):
    """{'titulo', 'dados': {planta: {dispositivo: {data: valor ou None}}}, 'sn': {(planta, disp): S/N}} ou None."""
    # .csv também: o portal exporta o mesmo mensal em CSV, com os acentos do cabeçalho quebrados (10/11/2026)
    if arq.ext not in (".xlsx", ".xlsm", ".xls", ".csv"):
        return None
    if arq.ext == ".csv" and not any("nome da usina" in norm_cab(l) for l in arq.cabeca(15)):
        return None                              # CSV de outro formato: não ler o arquivo inteiro à toa
    ger = re.compile(r"gera[c_][a_]o de energia")
    for _, linhas in arq.planilhas():
        for i, r in enumerate(linhas[:15]):
            h = [norm_cab(x) for x in r]
            iu = next((j for j, x in enumerate(h) if x == "nome da usina"), None)
            ih = next((j for j, x in enumerate(h) if re.fullmatch(r"hor[a_]rio", x)), None)
            if iu is None or ih is None:
                continue
            idisp = next((j for j, x in enumerate(h) if x.startswith("nome do dispositivo")), None)
            # três colunas começam com "Geração de energia": a do dia é a sem "total" e sem "teórica"
            iger = next((j for j, x in enumerate(h) if ger.match(x) and x.endswith("(kwh)")
                         and "total" not in x and "te_rica" not in x and "teorica" not in x), None)
            if idisp is None or iger is None:
                continue
            isn = next((j for j, x in enumerate(h) if x.startswith("s/n do dispositivo")), None)
            itot = next((j for j, x in enumerate(h) if ger.match(x) and "total" in x), None)
            titulo = next((str(x).strip() for r0 in linhas[:i] for x in r0 if x not in (None, "")), "")
            dados = collections.OrderedDict()
            sn, tot = {}, collections.defaultdict(dict)
            for r2 in linhas[i + 1:]:
                planta, disp = str(_cel(r2, iu) or "").strip(), str(_cel(r2, idisp) or "").strip()
                dia = data_de(_cel(r2, ih))
                if not planta or not disp or not dia:
                    continue
                dados.setdefault(planta, collections.OrderedDict()).setdefault(disp, {})[dia] = num(_cel(r2, iger))
                sn[(planta, disp)] = str(_cel(r2, isn) or "").strip()
                tot[(planta, disp)][dia] = num(_cel(r2, itot))
            if dados:
                return {"titulo": titulo, "dados": dados, "sn": sn, "tot": dict(tot)}
    return None


def _exportado_em(arq):
    """Hora da exportação pelo nome que o portal dá ('..._Relatório mensal_20261030090320.xlsx'); None se renomeado."""
    m = re.search(r"(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\D*$", arq.nome.rsplit(".", 1)[0])
    if not m:
        return None
    try:
        return dt.datetime(*map(int, m.groups()))
    except ValueError:
        return None


def _corte(arq, dados):
    """Primeiro dia que NÃO entra (o da exportação, que ainda não tinha fechado) ou None. O portal deixa o dia aberto
    VAZIO (mensal de 30/10 09:03: os 92 inversores com o 30/10 em branco), então isto é rede de segurança e só vale
    com a hora no nome. Sem ela não se adivinha: "último dia com geração seguido de dias vazios" derrubaria o 29/10
    completo desse mesmo arquivo renomeado (01.xlsx)."""
    exp = _exportado_em(arq)
    if not exp:
        return None
    todos = {d for disp in dados.values() for s in disp.values() for d in s}
    pos = {d for disp in dados.values() for s in disp.values() for d, v in s.items() if v}
    if not todos or (pos and exp.date() < max(pos)):
        return None                                   # hora incoerente (geração depois dela): não é a da exportação
    return exp.date() if exp.date() <= max(todos) else None


# ---------------------------------------------------------------- casamento pela geração
def _iguais(serie_rel, serie_bd, corte):
    """(dias iguais ao centavo, dias comparáveis): os dois > 0, antes do corte."""
    eq = comp = 0
    for d, v in serie_rel.items():
        if not v or v <= 0 or (corte and d >= corte):
            continue
        b = serie_bd.get(d)
        if isinstance(b, bool) or not isinstance(b, (int, float)) or b <= 0:
            continue
        comp += 1
        if abs(v - b) < IGUAL:
            eq += 1
    return eq, comp


def casar(dados, abas_bd, candidatas, conhecido, corte=None):
    """Casa (planta, dispositivo) com (aba, coluna).

    dados: {planta: {disp: {data: valor}}}; abas_bd: {aba: AbaBD}; candidatas: {planta: [aba...]};
    conhecido: {planta: (aba, {disp: coluna})} (nomes como no relatório).
    Devolve (casados {(planta, disp): (aba, coluna, como, iguais, comparáveis)}, fora {(planta, disp): motivo}).
    `como` = 'conhecido' (de-para conferido: a geração não contradiz), 'conhecido sem conferir' (nenhum dia igual no
    BD) ou 'geração'."""
    series = {}                                   # (aba, col) -> {data: valor do BD}
    for aba in {a for lst in candidatas.values() for a in lst}:
        ab = abas_bd.get(aba)
        if not ab:
            continue
        for col in ab.colunas_inversor():
            series[(aba, col)] = ab.serie(ab.cab.index(col))
    eq = {}                                       # (planta, disp) -> {(aba, col): (iguais, comparáveis)}
    for planta, disps in dados.items():
        cols = [c for c in series if c[0] in candidatas.get(planta, [])]
        for disp, s in disps.items():
            eq[(planta, disp)] = {c: _iguais(s, series[c], corte) for c in cols}
    por_col = collections.defaultdict(dict)       # (aba, col) -> {(planta, disp): iguais}
    for k, m in eq.items():
        for c, (n, _) in m.items():
            if n:
                por_col[c][k] = n

    casados, fora, travadas, usadas_con = {}, {}, set(), set()
    # 1) de-para conhecido: vale se a geração não aponta outro par com mais dias iguais
    for planta, disps in dados.items():
        aba_c, mapa = conhecido.get(planta, (None, {}))
        for disp in disps:
            col = mapa.get(disp)
            if not col:
                continue
            k, c = (planta, disp), (aba_c, col)
            if c not in series:
                fora[k] = ("o de-para conhecido diz %s, mas a aba %s não tem essa coluna" % (col, aba_c)
                           if aba_c in abas_bd else "o de-para conhecido aponta a aba %s, que não está no BD" % aba_c)
                continue
            if c in usadas_con:
                fora[k] = "o de-para conhecido dá %s a dois inversores desta planta; corrija a tabela" % col
                continue
            n, comp = eq[k].get(c, (0, 0))
            outra_c = max(((m[0], cc) for cc, m in eq[k].items() if cc != c), default=(0, None))
            outro_k = max(((m, kk) for kk, m in por_col[c].items() if kk != k), default=(0, None))
            if outra_c[0] >= MIN_DIAS and outra_c[0] > n:
                fora[k] = ("o de-para conhecido diz %s, mas a geração é igual à coluna %s%s em %d dias (%s: %d)"
                           % (col, outra_c[1][1], "" if outra_c[1][0] == aba_c else " da aba " + outra_c[1][0],
                              outra_c[0], col, n))
                travadas.update((c, outra_c[1]))
                continue
            if outro_k[0] >= MIN_DIAS and outro_k[0] > n:
                fora[k] = ("o de-para conhecido diz %s, mas essa coluna é igual a %s em %d dias (este: %d)"
                           % (col, outro_k[1][1], outro_k[0], n))
                travadas.add(c)
                continue
            casados[k] = (aba_c, col, "conhecido" if n else "conhecido sem conferir", n, comp)
            usadas_con.add(c)
    usadas = {(a, c) for a, c, *_ in casados.values()} | travadas

    # 2) pela geração: melhor dos dois lados, >= MIN_DIAS, sem empate. Repete porque um par aceito libera os outros.
    livres = [k for k in eq if k not in casados and k not in fora]
    mudou = True
    while mudou:
        mudou = False
        for k in list(livres):
            ops = sorted(((m[0], c) for c, m in eq[k].items() if c not in usadas and m[0]), reverse=True)
            if not ops or ops[0][0] < MIN_DIAS or (len(ops) > 1 and ops[1][0] == ops[0][0]):
                continue
            n, c = ops[0]
            # rival é todo inversor ainda sem coluna, inclusive o de-para conhecido travado por contradição:
            # a coluna que a geração dava a ele não passa para um inversor mais fraco
            rivais = [m for kk, m in por_col[c].items() if kk != k and kk not in casados]
            if rivais and max(rivais) >= n:
                continue
            casados[k] = (c[0], c[1], "geração", n, eq[k][c][1])
            usadas.add(c)
            livres.remove(k)
            mudou = True

    # 3) o motivo de quem sobrou
    for k in livres:
        planta, disp = k
        s = dados[planta][disp]
        if not any(v for d, v in s.items() if v and not (corte and d >= corte)):
            fora[k] = SEM_GERACAO
            continue
        if not eq[k]:
            fora[k] = "nenhuma aba do BD para comparar"
            continue
        ops = sorted(((m[0], c) for c, m in eq[k].items() if m[0]), reverse=True)
        comp = max((m[1] for m in eq[k].values()), default=0)
        if not comp:
            fora[k] = "o BD não tem nenhum dia com geração para comparar e não há de-para conhecido"
        elif not ops:
            fora[k] = "nenhum dia igual ao centavo em nenhuma coluna (%d dias comparáveis)" % comp
        elif ops[0][0] < MIN_DIAS:
            fora[k] = ("só %d dia(s) igual(is) ao centavo (%s), o mínimo é %d; inversor que o BD não tem?"
                       % (ops[0][0], ops[0][1][1], MIN_DIAS))
        elif ops[0][1] in usadas:
            dono = next((kk for kk, v in casados.items() if (v[0], v[1]) == ops[0][1]), None)
            if dono:
                # Barretos 2 (03/11): Inverter21 tem 5 dias iguais ao 2.1, que é do Inverter17 (17 dias): é o
                # inversor trocado no meio do mês, dois aparelhos na mesma posição
                fora[k] = ("a coluna %s (%d dias iguais) já é de %s; se é o inversor trocado no mês, os dias dele "
                           "vão à mão" % (ops[0][1][1], ops[0][0], dono[1] if dono[0] == planta
                                          else "%s · %s" % dono))
            else:
                fora[k] = "a coluna mais parecida (%s) está em disputa com o de-para conhecido" % ops[0][1][1]
        elif len(ops) > 1 and ops[1][0] == ops[0][0]:
            fora[k] = "empate: %s e %s com %d dias iguais" % (ops[0][1][1], ops[1][1][1], ops[0][0])
        else:
            fora[k] = "a coluna %s casa melhor com outro inversor" % ops[0][1][1]
    return casados, fora


# ---------------------------------------------------------------- leitor
class FusionMensal(Leitor):
    id = "fusion_mensal"
    fonte = "Relatório mensal INV (portal)"
    destino = BD_THOPEN

    def reconhecer(self, arq, ctx):
        try:
            t = _tabela(arq)
        except Exception:                               # noqa: BLE001 — arquivo de outro formato não derruba nada
            return None
        if not t:
            return None
        abas = ctx.abas(BD_THOPEN)
        usinas, sem_aba = set(), []
        for planta in t["dados"]:
            pelo_nome = _abas_pelo_nome(planta, abas) if abas else []
            con = _DEPARA_N.get(norm(planta))
            if pelo_nome:
                usinas.update(pelo_nome)
            elif con and (not abas or con[0] in abas):
                usinas.add(con[0])
            else:
                sem_aba.append(planta)
        if not usinas:
            return None                                 # é o mesmo cabeçalho da Sal Energia: sem usina do Thopen, não é daqui
        dias = sorted({d for disp in t["dados"].values() for s in disp.values() for d in s})
        n_inv = sum(len(x) for x in t["dados"].values())
        det = "%d planta(s) · %d inversores" % (len(t["dados"]), n_inv)
        if sem_aba:
            det += " · %d sem aba pelo nome" % len(sem_aba)
        return Reconhecimento(self.fonte, usinas=sorted(usinas), periodo=(dias[0], dias[-1]) if dias else None,
                              estado=t, detalhe=det)

    def ler(self, arq, ctx, rec, escolha=None):
        t = rec.estado
        dados = t["dados"]
        bd = ctx.bd(BD_THOPEN)
        avisos = []
        corte = _corte(arq, dados)
        if corte and any(v is not None for disp in dados.values() for s in disp.values()
                         for d, v in s.items() if d >= corte):
            avisos.append("Dia %s fora de todas as usinas: o relatório foi exportado nesse dia, às %s, com o dia "
                          "ainda aberto. Exporte de novo depois que ele fechar."
                          % (corte.strftime("%d/%m/%Y"), _exportado_em(arq).strftime("%H:%M")))
        nomes_abas = ctx.abas(BD_THOPEN)
        candidatas, pelo_nome = {}, {}
        for planta in dados:
            lst = _abas_pelo_nome(planta, nomes_abas) if nomes_abas else []
            con = _DEPARA_N.get(norm(planta))
            if con and con[0] in nomes_abas and con[0] not in lst:
                lst = lst + [con[0]]
            pelo_nome[planta] = bool(lst)
            candidatas[planta] = lst
        if bd and not all(pelo_nome.values()):
            # planta sem aba pelo nome: procura pela geração em todas as abas com inversor (casa_mensal de 03/11
            # achava aba e coluna sozinho assim); a aba que sair vai no aviso para alguém conferir
            todas = [a for a in nomes_abas if (bd.aba(a) and bd.aba(a).colunas_inversor())]
            for planta, ok in pelo_nome.items():
                if not ok:
                    candidatas[planta] = todas
        abas_bd = {a: bd.aba(a) for a in {x for lst in candidatas.values() for x in lst}} if bd else {}
        abas_bd = {a: ab for a, ab in abas_bd.items() if ab}
        conhecido = {}
        for planta, disps in dados.items():
            con = _DEPARA_N.get(norm(planta))
            if con:
                conhecido[planta] = (con[0], {d: con[1][norm(d)] for d in disps if norm(d) in con[1]})
        if not bd:
            avisos.append("BD_Thopen não carregado: só o de-para conhecido, sem conferir pela geração.")
            casados = {}
            for planta, (aba, mapa) in conhecido.items():
                for d, col in mapa.items():
                    casados[(planta, d)] = (aba, col, "conhecido sem conferir", 0, 0)
            fora = {(p, d): "sem BD para casar pela geração e sem de-para conhecido"
                    for p, ds in dados.items() for d in ds if (p, d) not in casados}
        else:
            casados, fora = casar(dados, abas_bd, candidatas, conhecido, corte)

        cel = []
        for (planta, disp), (aba, col, como, n, comp) in casados.items():
            for d, v in sorted(dados[planta][disp].items()):
                if v is None or (corte and d >= corte):
                    continue
                cel.append(Celula(BD_THOPEN, aba, d, col, v,
                                  confirmado=(v == 0 and _zero_confirmado(t.get("tot", {}).get((planta, disp), {}),
                                                                          dados[planta][disp], d))))
        avisos += _avisos(dados, casados, fora, pelo_nome)
        return cel, avisos


def _avisos(dados, casados, fora, pelo_nome):
    """Avisos por planta, curtos: o mesmo motivo vira uma linha só com a lista dos inversores (Cambé tem 20
    dispositivos só com 0, metade sem S/N; uma linha para cada seria ruído)."""
    out = []
    for planta, disps in dados.items():
        abas = sorted({casados[(planta, d)][0] for d in disps if (planta, d) in casados})
        if not pelo_nome.get(planta) and abas:
            out.append("%s: nenhuma aba do BD_Thopen com esse nome; os inversores casaram pela geração na aba %s. "
                       "Confira se é essa usina." % (planta, " e ".join(abas)))
        por_motivo = collections.OrderedDict()
        for d in disps:
            if (planta, d) in fora:
                por_motivo.setdefault(fora[(planta, d)], []).append(d)
        if not abas and por_motivo and len(por_motivo) == 1:
            m, ds = next(iter(por_motivo.items()))
            if m == SEM_GERACAO:
                out.append("%s: nenhum inversor com geração no mês; nada a colar." % planta)
            else:
                out.append("%s ficou fora (%d inversores): %s. Confira a usina no portal ou acrescente o de-para."
                           % (planta, len(ds), m))
            continue
        contra = [(d, m) for m, ds in por_motivo.items() if m.startswith("o de-para conhecido diz") for d in ds]
        if len(contra) >= 3:
            # Brodowski 1 (10/11): o BD de hoje tem o 1.x noutra ordem que o de 03/11 e os 14 pares batem com outra
            # coluna; uma linha por inversor seria um muro de texto para o mesmo conserto
            out.append("%s: o de-para conhecido não bate com o BD em %d inversores (%s); ficaram fora. Confira a ordem "
                       "no portal e corrija o DEPARA do leitor." % (
                           planta, len(contra), "; ".join("%s: %s" % (d, _curto(m)) for d, m in contra)))
            por_motivo = collections.OrderedDict((m, ds) for m, ds in por_motivo.items()
                                                 if not m.startswith("o de-para conhecido diz"))
        for m, ds in por_motivo.items():
            ds = sorted(ds, key=_ordem_natural)
            if m == SEM_GERACAO:
                out.append("%s: %s só com 0 ou vazio no mês; sem como casar pela geração, %s fora."
                           % (planta, ", ".join(ds), "ficou" if len(ds) == 1 else "ficaram"))
            else:
                out.append("%s · %s %s sem coluna: %s%s" % (planta, ", ".join(ds),
                                                            "ficou" if len(ds) == 1 else "ficaram", m,
                                                            "" if m.endswith(("?", ".")) else "."))
        sem_dia = [d for d in disps if casados.get((planta, d), (0, 0, ""))[2] == "conhecido sem conferir"
                   and not casados[(planta, d)][4]]
        sem_igual = [d for d in disps if casados.get((planta, d), (0, 0, ""))[2] == "conhecido sem conferir"
                     and casados[(planta, d)][4]]
        if sem_dia:
            out.append("%s: %s pelo de-para conhecido; o BD não tem dia com geração para conferir."
                       % (planta, ", ".join(sem_dia)))
        if sem_igual:
            out.append("%s: %s pelo de-para conhecido, mas nenhum dia do BD é igual (valor parado da API?). "
                       "Confira antes de colar." % (planta, ", ".join(sem_igual)))
    return out


def _zero_confirmado(tot, dia, d):
    """O 0 do dia é leitura de verdade quando o contador total do inversor está lá e não andou: igual ao da véspera, ou
    o do dia seguinte menos o diário do dia seguinte. Ipixuna 1, 04/11/2026: os 9 inversores com 0 e o total parado
    (358.680,5 em 03 e 04/11, 359.327,3 em 05/11 = +646,8 do dia 05): a usina não gerou, não foi o portal sem ler."""
    t = tot.get(d)
    if t is None:
        return False
    um = dt.timedelta(days=1)
    ant = tot.get(d - um)
    if ant is not None:
        return abs(t - ant) < 0.05
    prox, dprox = tot.get(d + um), dia.get(d + um)
    return prox is not None and dprox is not None and abs(prox - dprox - t) < 0.05


def _ordem_natural(s):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s)]


def _curto(motivo):
    """'o de-para conhecido diz Inversor 1.12, mas a geração é igual à coluna Inversor 1.8 em 3 dias (...)' ->
    'tabela 1.12, geração 1.8'."""
    m = re.match(r"o de-para conhecido diz Inversor (\S+), mas a geração é igual à coluna Inversor (\S+)", motivo)
    if m:
        return "tabela %s, geração %s" % m.groups()
    m = re.match(r"o de-para conhecido diz Inversor (\S+), mas essa coluna é igual a (.+?) em", motivo)
    if m:
        return "tabela %s, que é igual a %s" % m.groups()
    return motivo


LEITORES = [FusionMensal]
