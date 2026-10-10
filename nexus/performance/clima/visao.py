"""O que a tela Clima e risco mostra (06/10/2026): junta as leituras das três fontes com as usinas do cadastro e escreve os
textos, sem Flask (a view só chama `montar` e renderiza).

Os níveis da usina (07/10/2026, regras e o porquê em `alertas.py`): Agir agora (foco a até 5 km, aviso vermelho, ou aviso
laranja de um evento que estraga usina), Atenção (qualquer outro aviso, ou risco de fogo alto ou crítico) e Sem alerta. A tela
mostra uma faixa de quatro números, um cartão por usina em "Agir agora", a grade por estado, as fontes e uma matriz das usinas
em "Atenção" (as 20 primeiras, ou todas com `todas=True`).

Além da tela, `montar_usina` monta a PÁGINA de uma usina (07/10/2026): os alertas dela e a irradiação diária da NASA POWER
(gráfico dos últimos 30 dias, mês até agora). A NASA só é chamada daqui, nunca por `montar`.

A ordem dentro de cada nível é a gravidade que já existia, a mesma régua de três degraus (semáforo) para os três tipos de alerta:
  3 crítico   aviso "Grande Perigo" do INMET; foco de queimada a até 5 km (é um evento, não uma previsão); risco de fogo crítico
  2 alto      aviso "Perigo"; risco de fogo alto
  1 atenção   aviso "Perigo Potencial"
A usina vale o pior dos seus alertas. No empate: a que tem foco primeiro, depois a que tem mais tipos de alerta, o foco mais
perto, o aviso mais grave e, por fim, o nome.

O fogo das últimas 24 h dos satélites da NASA (FIRMS, 10/10/2026) entra como a quarta fonte: fogo a até 5 km nas últimas 24 h
é Atenção, e o foco do INPE ganha a confirmação e a força (FRP) quando a NASA viu o mesmo fogo. Sem a leitura do FIRMS a usina não
fica cinza (o agir e o resto da atenção não dependem dele), mas o verde vira "sem alerta nas fontes lidas": sem ler a NASA, não dá
para dizer que não houve fogo perto nas últimas 24 h.

A tela não pode parecer "tudo bem" quando a fonte não foi lida inteira (revisão de 06/10/2026):
- onde a fonte não tem leitura, o número é "—", nunca "0" (zero é "li e não há alerta"); "Sem alerta" só é contado com as três
  fontes lidas, e "Agir agora" e "Atenção" só viram "—" quando NENHUMA das fontes de que dependem foi lida (o agir vive de
  avisos e focos; o atenção, de avisos e risco de fogo);
- fonte lida só em parte (aviso sem polígono, arquivo de focos que falhou, linhas ilegíveis, dia do risco sem leitura), velha
  (a última leitura boa, com a hora) ou com o dado atrasado (focos parados, previsão de outro dia, sem a data do arquivo)
  fica em "atencao", nunca "ok", e os números da faixa que dependem dela repetem o qualificador ("avisos do ... (INMET):
  parcial", "focos de queimada do ... (INPE): arquivos até 14:10"...), em âmbar no lugar do verde quando não há alerta;
- sem alerta algum e sem ter lido tudo o que a seção usa, o texto não diz "nenhuma usina para agir agora": diz que não dá para dizer.
"""
from datetime import datetime, timedelta, timezone

from ...cadastro.servico import chave_texto
from . import alertas as A
from . import explica as E
from . import fontes as F
from . import irradiacao as I
from . import leitura as L

BRT = timezone(timedelta(hours=-3))
DIAS = ("Hoje", "D+1", "D+2", "D+3")
_SEMANA = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
# A palavra do risco de fogo na tabela da Atenção (09/10/2026, "deixe mais didático"): "1,00" não diz nada a quem não conhece a
# escala do INPE; o número vai no balão da célula.
PALAVRA_DO_RISCO = {"crítico": "Crítico", "alto": "Alto", "médio": "Médio", "baixo": "Baixo", "mínimo": "Mínimo"}
FOCOS_ATRASO_MIN = 30          # o INPE publica a cada 10 min: sem arquivo novo há 30 min, algo está atrasado
FIRMS_ATRASO_H = 18            # os satélites da NASA passam perto das 13h30 e da 01h30, e o dado chega em até 3 h: sem foco novo
                               # há 18 h, alguma passagem se perdeu
SEM_DADO = "sem dado (sem vegetação no entorno)"
FORA_DA_GRADE = f"fora da grade do {F.extenso('inpe')}"
MOTIVO_SEM_RISCO = {"sem_dado": "sem vegetação no entorno", "fora_da_grade": FORA_DA_GRADE}
RECARGA_S = 60                 # a tela se recarrega a cada minuto...
RECARGA_LENDO_S = 10           # ...e a cada 10 s enquanto alguma fonte está sendo lida pela primeira vez
FOLGA_PROXIMA_S = 5            # o mapa e o modo TV voltam 5 s depois de o cache da fonte vencer: aí a visita já relê
PROXIMA_MAX_S = 30 * 60        # e nunca ficam mais de 30 min sem conferir (o TTL dos avisos)
LIMITE_ATENCAO = 20            # a matriz da Atenção mostra as 20 primeiras; "Ver todas" (?todas=1) mostra a lista inteira
COR_DO_AVISO = {1: "amarelo", 2: "laranja", 3: "vermelho"}      # a cor do INMET pelo nível; a cor que vem no aviso nunca é lida
# Os subtítulos dos números do topo, na língua de quem não é da meteorologia (09/10/2026); a regra inteira está em "Como ler".
SUB_AGIR = f"fogo a até {A.FOCO_KM:g} km ou aviso forte (tempestade, chuva forte, vento, granizo) do {F.extenso('inmet')}"
SUB_ATENCAO = (f"outro aviso do {F.extenso('inmet')}, risco de fogo alto nos próximos 4 dias ou fogo a até 5 km nas últimas "
               "24 h: acompanhar")
# De que fontes cada número da faixa depende: o "agir agora" vive de avisos e focos; o "atenção", de avisos e risco de fogo; o
# "sem alerta" precisa das três. Uma fonte parcial ou atrasada só qualifica o número que a usa.
FONTES_DO_NIVEL = {"agir": ("inmet", "focos"), "atencao": ("inmet", "risco", "firms"), "sem": ("inmet", "focos", "risco", "firms")}
# O nome de cada fonte na frase, por extenso e com a sigla (Levi, 09/10/2026: "Quero as fontes por extenso também, não só sigla"):
# o nome mora em `fontes.NOMES`; aqui só se diz qual dado de qual instituto. Vale também para o qualificador dos números da faixa
# ("avisos do Instituto ... (INMET): parcial"), que antes era só a sigla.
NOME_LONGO = {"inmet": f"avisos do {F.extenso('inmet')}", "focos": f"focos de queimada do {F.extenso('inpe')}",
              "risco": f"risco de fogo do {F.extenso('inpe')}", "firms": f"fogo das últimas 24 h da {F.extenso('nasa_firms')}"}
# a linha de cada fonte no painel "De onde vêm os dados" e na legenda do mapa: o instituto por extenso e, depois do ponto, o dado
ROTULO_DA_FONTE = {"inmet": f"{F.extenso('inmet')} · avisos", "focos": f"{F.extenso('inpe')} · focos de queimada",
                   "risco": f"{F.extenso('inpe')} · risco de fogo", "power": f"{F.extenso('nasa_power')} · irradiação",
                   "firms": f"{F.extenso('nasa_firms')} · fogo das últimas 24 h"}
# A grade por estado do desenho aprovado em 07/10/2026 (esquema, não é mapa): UF -> (coluna, linha) numa grade de 7 x 8.
UFS_GRADE = {"RR": (2, 1), "AP": (4, 1), "AM": (2, 2), "PA": (3, 2), "MA": (4, 2), "CE": (5, 2), "RN": (6, 2), "AC": (1, 3),
             "RO": (2, 3), "TO": (3, 3), "PI": (4, 3), "PE": (5, 3), "PB": (6, 3), "MT": (2, 4), "GO": (3, 4), "BA": (4, 4),
             "AL": (5, 4), "SE": (6, 4), "MS": (2, 5), "DF": (3, 5), "MG": (4, 5), "ES": (5, 5), "PR": (2, 6), "SP": (3, 6),
             "RJ": (4, 6), "SC": (2, 7), "RS": (2, 8)}


def agora() -> datetime:
    return datetime.now(BRT)


def proxima_leitura_s(leituras, momento=None) -> int:
    """Em quantos segundos a tela deve reler, no ritmo do cache de cada fonte (09/10/2026, o modo TV: "atualização sozinha, no
    ritmo dos caches de cada fonte; nunca mais do que eles"): quando a PRIMEIRA leitura vencer (`Leitura.vence_em`, mais
    `FOLGA_PROXIMA_S`); 10 s enquanto alguma fonte é lida pela primeira vez (a leitura em curso não vai de novo à rede); 60 s sem
    nenhuma data (leitura montada à mão). `momento` é o relógio dos caches (epoch)."""
    momento = L.agora() if momento is None else momento
    prazos = []
    for leitura in leituras:
        if leitura is None:
            continue
        if leitura.dados is None and leitura.erro == L.LENDO:
            return RECARGA_LENDO_S
        if leitura.vence_em is not None:
            prazos.append(leitura.vence_em - momento)
    if not prazos:
        return RECARGA_S
    return int(min(PROXIMA_MAX_S, max(RECARGA_LENDO_S, min(prazos) + FOLGA_PROXIMA_S)))


def hora(d: datetime, ref: datetime) -> str:
    """HH:MM em Brasília; com o dia na frente quando não é o dia de `ref`."""
    d, ref = d.astimezone(BRT), ref.astimezone(BRT)
    return d.strftime("%H:%M") if d.date() == ref.date() else d.strftime("%d/%m %H:%M")


def numero(v: float, casas: int = 2) -> str:
    return f"{v:.{casas}f}".replace(".", ",")


def milhar(n: int) -> str:
    """4829 -> "4.829" (ponto de milhar, como o resto do Nexus)."""
    return f"{n:,}".replace(",", ".")


def _plural(n: int, um: str, varios: str) -> str:
    return f"{milhar(n)} {um if n == 1 else varios}"


def _quando(t) -> datetime:
    return datetime.fromtimestamp(t, BRT)


def _juntar(nomes: list) -> str:
    """["a", "b", "c"] -> "a, b e c"."""
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


# ── risco de fogo, dia a dia ─────────────────────────────────────────────────────────────────────────────────────────

def rotulos_dos_dias(arquivo, ref: datetime) -> list:
    """Hoje, D+1, D+2 e D+3 pela data do CALENDÁRIO: cada dia do risco é a data do arquivo (T0) mais k, e o rótulo diz onde
    esse dia cai em relação a hoje. Com o arquivo de ontem (lido antes da publicação das ~06:30) o T0 é "Ontem", o T1 é
    "Hoje" e assim por diante: chamar de "Hoje" a previsão de ontem seria mentir sobre o dia. Sem a data do arquivo, assume
    que é de hoje (e a fonte fica em atenção por isso)."""
    hoje = ref.astimezone(BRT).date()
    base = arquivo.astimezone(BRT).date() if arquivo else hoje
    saida = []
    for k in range(len(DIAS)):
        dia = base + timedelta(days=k)
        delta = (dia - hoje).days
        saida.append("Hoje" if delta == 0 else f"D+{delta}" if 1 <= delta <= 3 else "Ontem" if delta == -1
                     else f"{dia:%d/%m}")
    return saida


def dias_amigaveis(arquivo, ref: datetime) -> list:
    """Os mesmos quatro dias de `rotulos_dos_dias`, com o nome que se fala (09/10/2026, "deixe mais didático"): "hoje", "amanhã"
    e, depois, o dia da semana com a data ("sáb 11/10"); "ontem" com o arquivo de ontem. "D+2" é jargão de quem planeja."""
    hoje = ref.astimezone(BRT).date()
    base = arquivo.astimezone(BRT).date() if arquivo else hoje
    saida = []
    for k in range(len(DIAS)):
        dia = base + timedelta(days=k)
        delta = (dia - hoje).days
        saida.append({0: "hoje", 1: "amanhã", -1: "ontem"}.get(delta) or f"{_SEMANA[dia.weekday()]} {dia:%d/%m}")
    return saida


def celula_de_risco(i: int, amostra, rotulos=DIAS, amigaveis=None) -> dict:
    """Um dos quatro dias do risco de fogo de uma usina, escrito pela origem do valor: o do pixel dela, o do entorno de
    5 x 5 (quando o pixel é nodata: o INPE não calcula onde não há vegetação), ou a razão de não haver número. Com `amigaveis`
    (os nomes de `dias_amigaveis`), a frase do risco fala "amanhã" e "sáb 11/10" no lugar de "D+1" e "D+2"."""
    rotulo = rotulos[i]
    dia = amigaveis[i] if amigaveis else _dia_na_frase(rotulo)
    if amostra.origem in ("ponto", "entorno") and amostra.valor is not None:
        classe = A.classe_risco_fogo(amostra.valor)
        nivel = A.nivel_do_risco(classe)
        # `curto` e `cor` são da matriz da Atenção: o número sozinho e c (crítico, vermelho), a (alto, laranja) ou n (o resto);
        # `palavra` é o que a célula mostra desde 09/10 (o número vai no balão)
        return {"rotulo": rotulo, "dia": dia, "valor": numero(amostra.valor), "curto": numero(amostra.valor), "classe": classe,
                "palavra": PALAVRA_DO_RISCO.get(classe, classe), "nivel": nivel, "cor": {3: "c", 2: "a"}.get(nivel, "n"),
                "nota": "entorno" if amostra.origem == "entorno" else "", "origem": amostra.origem, "_num": amostra.valor}
    texto = {"sem_dado": SEM_DADO, "indisponivel": "indisponível", "fora_da_grade": FORA_DA_GRADE}.get(
        amostra.origem, "sem dado")
    return {"rotulo": rotulo, "dia": dia, "valor": texto, "curto": "—", "classe": "", "palavra": "—", "nivel": 0, "cor": "n",
            "nota": "", "origem": amostra.origem, "_num": None}


def _dia_na_frase(rotulo: str) -> str:
    return rotulo.lower() if rotulo in ("Hoje", "Ontem") else rotulo


def _quando_dias(indices: list, dias: list) -> str:
    """[0, 1, 2, 3] -> "de hoje a D+3"; [0, 1] -> "hoje e D+1"; [2] -> "em D+2". Só três ou mais dias seguidos viram "de X a Y".
    Com os nomes de `dias_amigaveis` na célula: "de hoje a dom 12/10", "hoje e amanhã", "em sáb 11/10"."""
    rotulos = [dias[i].get("dia") or _dia_na_frase(dias[i]["rotulo"]) for i in indices]
    if len(indices) >= 3 and indices == list(range(indices[0], indices[-1] + 1)):
        return f"de {rotulos[0]} a {rotulos[-1]}"
    texto = _juntar(rotulos)
    return texto if rotulos[0] in ("hoje", "ontem", "amanhã") else f"em {texto}"


def frase_do_risco(dias: list):
    """O risco de fogo dos quatro dias numa frase: "Risco de fogo crítico de hoje a D+3 (1,00)". A classe mais alta primeiro, com o
    maior valor dela; o crítico leva atrás os dias de risco alto. Sem alto nem crítico, diz até onde o risco chega. None se
    nenhum dia tem número (a causa, "sem vegetação" ou "fora da grade", é dita por quem chama)."""
    por_nivel = {3: [], 2: []}
    for i, c in enumerate(dias):
        if c["nivel"] in por_nivel:
            por_nivel[c["nivel"]].append(i)
    pior = 3 if por_nivel[3] else 2 if por_nivel[2] else 0
    if pior:
        classe = "crítico" if pior == 3 else "alto"
        maior = max(dias[i]["_num"] for i in por_nivel[pior])
        frase = f"Risco de fogo {classe} {_quando_dias(por_nivel[pior], dias)} ({numero(maior)})"
        if pior == 3 and por_nivel[2]:
            frase += f"; alto {_quando_dias(por_nivel[2], dias)}"
        return frase
    com_numero = [c for c in dias if c["_num"] is not None]
    if not com_numero:
        return None
    mais_alto = max(com_numero, key=lambda c: c["_num"])
    # "Risco de fogo até mínimo (0,01)" lia como erro (09/10/2026): a classe mais alta dos quatro dias, com o número dela
    return f"Risco de fogo {mais_alto['classe']} nos 4 dias da previsão (no máximo {mais_alto['valor']})"


# ── o estado de cada fonte ───────────────────────────────────────────────────────────────────────────────────────────

def _falha(nome: str, leitura, ref: datetime):
    """(estado, texto, detalhe) se a fonte não tem leitura ou só tem a velha; None se está limpa. "fora agora; última leitura
    boa às HH:MM" é a frase que o plano pede para a fonte que caiu: a tela nunca mostra dado velho como se fosse de agora."""
    if leitura.dados is None:
        if leitura.erro == L.LENDO:
            return "atencao", f"{nome}: lendo a fonte (a tela se atualiza sozinha)", ""
        return "fora", f"{nome}: fora agora; ainda sem leitura boa", leitura.erro or ""
    if leitura.velha:
        return ("atencao", f"{nome}: fora agora; última leitura boa às {hora(_quando(leitura.lido_em), ref)}",
                leitura.erro or "")
    return None


def _sem_dado(id_: str, falha) -> dict:
    return {"id": id_, "estado": falha[0], "texto": falha[1], "detalhe": falha[2], "qualifica": []}


def _fechar(id_: str, leitura, ref: datetime, falha, texto_ok: str, parciais=(), atrasos=()) -> dict:
    """O estado de uma fonte COM dado. Leitura velha (`falha` vindo de `_falha`), leitura parcial (parte do que devia vir não
    veio: `parciais`) e dado atrasado (`atrasos`) deixam "atencao", nunca "ok", e dizem o que é em `qualifica`, que os
    cartões do topo repetem."""
    velha = falha is not None
    qualifica = ([f"dado de {hora(_quando(leitura.lido_em), ref)}"] if velha else []) + list(atrasos)
    if parciais:
        qualifica.append("parcial")
    detalhe = "; ".join(x for x in ([falha[2]] if velha else []) + list(parciais) if x)
    return {"id": id_, "estado": "atencao" if qualifica else "ok", "texto": falha[1] if velha else texto_ok,
            "detalhe": detalhe, "qualifica": qualifica}


def _arquivo_t0(dados: dict):
    """A data do arquivo do INPE: a do T0, ou a de outro dia se o T0 falhou (saem todos juntos, às ~06:30)."""
    arquivos = dados["arquivos"]
    return arquivos.get(0) or next((v for v in arquivos.values() if v), None)


def _fonte_inmet(leitura, ref) -> dict:
    falha = _falha(ROTULO_DA_FONTE["inmet"], leitura, ref)
    if leitura.dados is None:
        return _sem_dado("inmet", falha)
    d = leitura.dados
    n_hoje = sum(a.quando == "hoje" for a in d["avisos"])
    texto = (f"{ROTULO_DA_FONTE['inmet']}: lido às {hora(_quando(leitura.lido_em), ref)} · "
             f"{_plural(len(d['avisos']), 'aviso ativo', 'avisos ativos')} ({n_hoje} hoje, {len(d['avisos']) - n_hoje} futuros)")
    parciais = ([f"{_plural(len(d['ignorados']), 'aviso foi ignorado', 'avisos foram ignorados')} por falta de polígono utilizável"]
                if d["ignorados"] else [])
    return _fechar("inmet", leitura, ref, falha, texto, parciais)


def _fonte_focos(leitura, ref) -> dict:
    falha = _falha(ROTULO_DA_FONTE["focos"], leitura, ref)
    if leitura.dados is None:
        return _sem_dado("focos", falha)
    d = leitura.dados
    ate, lido = d["ate"], hora(_quando(leitura.lido_em), ref)
    parciais = []
    if d["falhos"]:
        parciais.append(f"{len(d['falhos'])} de {len(d['arquivos']) + len(d['falhos'])} arquivos indisponíveis")
    if d.get("linhas_ruins"):
        parciais.append(_plural(d["linhas_ruins"], "linha ilegível", "linhas ilegíveis"))
    if ref - ate.astimezone(BRT) > timedelta(minutes=FOCOS_ATRASO_MIN):
        texto = f"{ROTULO_DA_FONTE['focos']}: o INPE não publica arquivo novo desde {hora(ate, ref)} · lido às {lido}"
        atrasos = [f"arquivos até {hora(ate, ref)}"]
    else:
        texto = (f"{ROTULO_DA_FONTE['focos']}: arquivos até {hora(ate, ref)} · lido às {lido} · "
                 f"{_plural(len(d['focos']), 'foco', 'focos')} na última hora")
        atrasos = []
    return _fechar("focos", leitura, ref, falha, texto, parciais, atrasos)


def _fonte_risco(leitura, ref, rotulos) -> dict:
    falha = _falha(ROTULO_DA_FONTE["risco"], leitura, ref)
    if leitura.dados is None:
        return _sem_dado("risco", falha)
    d = leitura.dados
    parciais = [f"{rotulos[dia]} indisponível ({motivo})" for dia, motivo in sorted(d["erros"].items())]
    arquivo, lido, atrasos = _arquivo_t0(d), hora(_quando(leitura.lido_em), ref), []
    if arquivo is None:
        # sem Last-Modified não há como dizer de que dia é a previsão (nem se o arquivo mudou no meio da leitura)
        texto = f"{ROTULO_DA_FONTE['risco']}: sem data do arquivo · lido às {lido}"
        atrasos.append("sem data do arquivo")
    else:
        a = arquivo.astimezone(BRT)
        texto = f"{ROTULO_DA_FONTE['risco']}: previsão de {a:%d/%m} (arquivo das {a:%H:%M})"
        if a.date() != ref.astimezone(BRT).date():
            atrasos.append(f"previsão de {a:%d/%m}")
            texto += " · de ontem" if a.date() == (ref - timedelta(days=1)).astimezone(BRT).date() else f" · de {a:%d/%m}"
        texto += f" · lido às {lido}"
    return _fechar("risco", leitura, ref, falha, texto, parciais, atrasos)


def _fonte_firms(leitura, ref) -> dict:
    """O fogo das últimas 24 h da NASA (10/10/2026): de quando é a última passagem, quantos focos no Brasil nas últimas 24 h e os
    satélites que não vieram. Sem foco novo há `FIRMS_ATRASO_H` horas, alguma passagem se perdeu: fica em atenção."""
    falha = _falha(ROTULO_DA_FONTE["firms"], leitura, ref)
    if leitura.dados is None:
        return _sem_dado("firms", falha)
    d = leitura.dados
    lido, ate = hora(_quando(leitura.lido_em), ref), d.get("ate")
    n24 = len(A.focos_nasa_24h(d["focos"], ref))
    parciais = [f"{len(d['falhos'])} de {len(d['arquivos']) + len(d['falhos'])} satélites indisponíveis "
                f"({_juntar(sorted(d['falhos']))})"] if d["falhos"] else []
    if d.get("linhas_ruins"):
        parciais.append(_plural(d["linhas_ruins"], "linha ilegível", "linhas ilegíveis"))
    atrasos = []
    if ate is None or ref - ate.astimezone(BRT) > timedelta(hours=FIRMS_ATRASO_H):
        atrasos.append(f"passagens até {hora(ate, ref)}" if ate else "nenhum foco nos arquivos")
    texto = (f"{ROTULO_DA_FONTE['firms']}: passagens até {hora(ate, ref) if ate else '—'} · lido às {lido} · "
             f"{_plural(n24, 'foco', 'focos')} no Brasil nas últimas 24 h")
    return _fechar("firms", leitura, ref, falha, texto, parciais, atrasos)


_INDICE_NASA: dict = {}


def indice_nasa(leitura, ref):
    """O índice dos focos da NASA das últimas 24 h até `ref` (None sem leitura). Na seca são uns 100 mil focos no Brasil em 40 h de
    arquivo: o índice sai uma vez por leitura e por janela de 5 min, e a lista, o mapa e a página da usina dividem."""
    if leitura is None or leitura.dados is None:
        return None
    chave = (id(leitura.dados), int(ref.timestamp() // 300))
    if chave not in _INDICE_NASA:
        _INDICE_NASA.clear()
        _INDICE_NASA[chave] = A.IndiceFocos(A.focos_nasa_24h(leitura.dados["focos"], ref))
    return _INDICE_NASA[chave]


def idade(d: datetime, ref: datetime) -> str:
    """Há quanto tempo, em palavra curta: "há 40 min", "há 9 h"."""
    minutos = max(0, int((ref - d).total_seconds() // 60))
    return f"há {minutos} min" if minutos < 60 else f"há {minutos // 60} h"


def do_satelite(f) -> str:
    """"VIIRS NOAA-20, confiança alta, força 35 MW (forte)": o que a NASA diz do foco."""
    return (f"{f.sensor} {f.satelite}, confiança {f.confianca}, força {numero(f.frp, 0 if f.frp >= 10 else 1)} MW "
            f"({A.classe_frp(f.frp)})")


def _na_usina(km: float) -> str:
    return (f"a menos de {int(A.NA_USINA_KM * 1000)} m do ponto da usina: pode ser a própria usina (reflexo do sol nos módulos ou "
            "telhado quente); confira antes de acionar") if km <= A.NA_USINA_KM else ""


def fogo_curto(fogo: dict, ref) -> str:
    """"Fogo a 2,3 km há 9 h": o fogo da NASA no motivo resumido."""
    return f"Fogo a {numero(fogo['km'], 1)} km {idade(fogo['foco'].data, ref)}"


def fogo_detalhe(fogo: dict, ref) -> str:
    """O fogo da NASA por extenso: quantos, o mais perto (quando, satélite, confiança, força) e o mais forte."""
    f = fogo["foco"]
    texto = (f"{_plural(fogo['n'], 'foco', 'focos')} a até {A.FOGO_24H_KM:g} km nas últimas {A.FOGO_24H_H} h · o mais perto a "
             f"{numero(fogo['km'], 1)} km, às {hora(f.data, ref)} ({do_satelite(f)})")
    if fogo["frp_max"] > f.frp:
        texto += f" · o mais forte com {numero(fogo['frp_max'], 0)} MW"
    perto = _na_usina(fogo["km"])
    return texto + (f" · {perto}" if perto else "")


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def _validade(a, ref) -> str:
    fim = f", até {hora(a.fim, ref)}" if a.fim else ""
    return "em vigor" + fim if A.em_vigor(a, ref) else f"começa {hora(a.inicio, ref)}" + fim


def _janela(inicio, fim, vigor: bool, ref) -> str:
    """"agora, até 23:59", "a partir de 10/10 00:00, até 10/10 23:59" ou "agora" (sem fim conhecido)."""
    ate = f", até {hora(fim, ref)}" if fim else ""
    if vigor or inicio is None:
        return "agora" + ate
    return f"a partir de {hora(inicio, ref)}" + ate


def agrupar_avisos(avisos, ref) -> list:
    """Os avisos de uma usina com o MESMO evento e o MESMO nível viram uma linha (09/10/2026, "deixe mais didático"): em 09/10 uma
    usina tinha três avisos de "Baixa Umidade" (hoje, amanhã e depois) e a tela repetia a pílula três vezes, sem dizer que era a
    mesma coisa. A janela vai do primeiro início ao último fim (um aviso sem início ou sem fim deixa a ponta aberta) e `n` diz
    quantos avisos são. Os que mandam agir vêm antes; dentro deles, a ordem de `avisos_que_contem` (o mais grave primeiro)."""
    grupos = {}
    for a in avisos:
        g = grupos.setdefault((chave_texto(a.evento), a.nivel), {
            "evento": a.evento, "nome": E.nome_amigavel(a.evento), "severidade": a.severidade, "nivel": a.nivel,
            "agir": A.aviso_manda_agir(a), "n": 0, "em_vigor": False, "_inicios": [], "_fins": []})
        g["n"] += 1
        g["em_vigor"] = g["em_vigor"] or A.em_vigor(a, ref)
        g["_inicios"].append(a.inicio)
        g["_fins"].append(a.fim)
    saida = sorted(grupos.values(), key=lambda g: (not g["agir"], -g["nivel"]))
    for g in saida:
        inicios, fins = g.pop("_inicios"), g.pop("_fins")
        _completar(g, None if None in inicios else min(inicios), None if None in fins else max(fins), ref)
        g["quer_dizer"] = E.QUER_DIZER_NIVEL.get(g["nivel"], "")
    return saida


def _completar(g: dict, inicio, fim, ref) -> None:
    """A janela de um grupo: `inicio` e `fim` (datas, para quem junta grupos), `comeca` ("" se já está valendo) e `quando`."""
    g["inicio"], g["fim"] = inicio, fim
    g["comeca"] = hora(inicio, ref) if inicio is not None and not g["em_vigor"] else ""
    g["quando"] = _janela(inicio, fim, g["em_vigor"], ref) + (f" · {g['n']} avisos" if g["n"] > 1 else "")


def por_evento(grupos: list, ref) -> list:
    """Junta os grupos de `agrupar_avisos` do MESMO evento, em níveis diferentes (09/10/2026): na seca de 09/10 a "Baixa Umidade"
    vinha em Perigo hoje e em Perigo Potencial amanhã, e o porquê da usina dizia "Baixa umidade (Perigo) · Baixa umidade
    (Perigo Potencial)". Fica o nível mais alto (`nivel`, `severidade`), a janela de todos, a soma dos avisos e, em `niveis`, os
    grupos de cada nível (o balão da pílula e o "Também" do cartão dizem quando vale cada um). Na ordem dos grupos: o evento que
    manda agir primeiro."""
    saida, por_chave = [], {}
    for g in grupos:
        e = por_chave.get(chave_texto(g["evento"]))
        if e is None:
            # o primeiro grupo de um evento é o mais grave dele: `agrupar_avisos` põe o que manda agir antes e, dentro, o nível mais
            # alto primeiro, e dentro de um MESMO evento quem manda agir é sempre o nível mais alto (Perigo de evento que estraga
            # usina implica Grande Perigo também mandando)
            e = por_chave[chave_texto(g["evento"])] = {"evento": g["evento"], "nome": g["nome"], "nivel": g["nivel"],
                                                       "severidade": g["severidade"], "agir": g["agir"], "n": 0,
                                                       "em_vigor": False, "niveis": []}
            saida.append(e)
        e["n"] += g["n"]
        e["em_vigor"] = e["em_vigor"] or g["em_vigor"]
        e["niveis"].append(g)
    for e in saida:
        inicios, fins = [g["inicio"] for g in e["niveis"]], [g["fim"] for g in e["niveis"]]
        _completar(e, None if None in inicios else min(inicios), None if None in fins else max(fins), ref)
        e["quer_dizer"] = E.QUER_DIZER_NIVEL.get(e["nivel"], "")
        e["detalhe"] = " · ".join(f"{g['severidade']}: {g['quando']}" for g in e["niveis"])
    return saida


def risco_curto(dias) -> str:
    """O risco de fogo alto ou crítico em poucas palavras ("Risco de fogo crítico de hoje a dom 12/10"); "" sem alto nem crítico."""
    if not dias:
        return ""
    por_nivel = {n: [i for i, c in enumerate(dias) if c["nivel"] == n] for n in (3, 2)}
    pior = 3 if por_nivel[3] else 2 if por_nivel[2] else 0
    if not pior:
        return ""
    return f"Risco de fogo {'crítico' if pior == 3 else 'alto'} {_quando_dias(por_nivel[pior], dias)}"


MOTIVOS_CURTOS = 2      # o motivo resumido leva os dois mais importantes e "e mais N"


def motivo_curto(avisos, foco, dias, ref, fogo=None) -> str:
    """Por que a usina está no nível dela, numa linha curta e em língua de gente (09/10/2026): o fogo perto (o da última hora do
    INPE; sem ele, o das últimas 24 h da NASA, 10/10/2026), os avisos (os que mandam agir antes, iguais juntos) e o risco de fogo
    alto. É o "por quê" da tabela da Atenção e o motivo da tabela do mapa."""
    itens = [f"Fogo a {numero(foco['km'], 1)} km"] if foco else [fogo_curto(fogo, ref)] if fogo else []
    for e in por_evento(agrupar_avisos(avisos, ref), ref):
        itens.append(f"{e['nome']} ({e['severidade']}" + (f", a partir de {e['comeca']}" if e["comeca"] else "") + ")")
    if risco_curto(dias):
        itens.append(risco_curto(dias))
    if len(itens) > MOTIVOS_CURTOS:
        return " · ".join(itens[:MOTIVOS_CURTOS]) + f" · e mais {len(itens) - MOTIVOS_CURTOS}"
    return " · ".join(itens)


def _motivo_do_foco(foco: dict, ref, confirma=None, nasa_lida: bool = False) -> dict:
    """O foco do INPE que manda agir. Com a NASA lida (10/10/2026), a prova diz se ela viu o mesmo fogo (a até 1 km e 1 h), com a
    força e a confiança; e o foco a menos de 400 m do ponto da usina leva o aviso de que pode ser a própria usina."""
    km = numero(foco["km"], 1)
    prova = (f"{_plural(foco['n'], 'foco de queimada', 'focos de queimada')} a até {A.FOCO_KM:g} km na última hora · "
             f"visto pelo satélite {foco['satelite']} às {hora(foco['hora'], ref)}")
    if confirma is not None:
        prova += f" · confirmado pela NASA ({do_satelite(confirma)})"
    elif nasa_lida:
        prova += " · ainda sem confirmação dos satélites da NASA (eles passam perto das 13h30 e da 01h30)"
    perto = _na_usina(foco["km"])
    return {"tipo": "foco", "pill": f"Fogo a {km} km", "principal": f"Fogo a {km} km da usina",
            "prova": prova + (f" · {perto}" if perto else ""), **E.FOCO}


def _motivo_do_aviso(g: dict) -> dict:
    """Um grupo de `agrupar_avisos` que manda agir: o nível com o que ele quer dizer e o texto do evento (`explica.py`)."""
    return {"tipo": "aviso", "pill": f"{g['nome']} · {g['severidade']}",
            "principal": f"{g['nome']}: {g['severidade']} ({g['quer_dizer']})", "prova": f"Quando: {g['quando']}",
            **E.evento(g["evento"])}


def _contexto_do_risco(dias, risco_linha, risco_lido: bool) -> str:
    if dias is None:
        return "Risco de fogo: sem dado para esta usina" if risco_lido else f"Risco de fogo: sem leitura do {F.extenso('inpe')}"
    if risco_linha:
        return f"Risco de fogo: {risco_linha}"
    return frase_do_risco(dias) or "Risco de fogo: sem dado"


def _usina(u, avisos_l, indice, risco_l, ref, rotulos, amigaveis=None, nasa=None):
    """O cartão de uma usina. `nasa` é o índice dos focos da NASA das últimas 24 h (`indice_nasa`), ou None sem a leitura."""
    avisos = A.avisos_que_contem(u.lat, u.lon, avisos_l.dados["avisos"], ref) if avisos_l.dados else []
    foco = indice.perto(u.lat, u.lon) if indice is not None else None
    fogo = A.fogo_24h(nasa, u.lat, u.lon) if nasa is not None else None
    confirma = A.confirmacao(nasa, foco["foco"]) if foco and nasa is not None else None
    dias = None
    if risco_l.dados:
        dias = [celula_de_risco(i, a, rotulos, amigaveis)
                for i, a in enumerate(risco_l.dados["por_ponto"].get(u.id, []))] or None
    n_inmet = max((a.nivel for a in avisos), default=0)
    n_foco = 3 if foco else 0
    n_risco = max((c["nivel"] for c in dias or []), default=0)
    n_fogo = A.gravidade_do_fogo_24h(fogo) if fogo else 0
    gravidade = max(n_inmet, n_foco, n_risco, n_fogo)  # a régua de três degraus de antes: segue ordenando DENTRO de cada nível
    nivel = A.nivel_da_usina(avisos, foco is not None, n_risco > 0, fogo is not None)
    # Os quatro dias sem número pelo mesmo motivo (sem vegetação em volta, ou fora da grade do INPE) viram UMA linha, e a usina
    # entra na lista de "risco de fogo sem dado" com o motivo.
    risco_linha = risco_origem = None
    if dias and dias[0]["origem"] in MOTIVO_SEM_RISCO and all(c["origem"] == dias[0]["origem"] for c in dias):
        risco_linha, risco_origem = dias[0]["valor"], dias[0]["origem"]
    grupos = agrupar_avisos(avisos, ref)
    eventos = por_evento(grupos, ref)
    # Um motivo por EVENTO que manda agir (o grupo mais grave dele); os outros níveis do mesmo evento e os eventos que só pedem
    # atenção vão para o "Também" (09/10/2026: o cartão repetia "Tempestade: Grande Perigo" e "Tempestade: Perigo", cada um
    # com o mesmo "o que pode acontecer").
    motivos = [_motivo_do_foco(foco, ref, confirma, nasa is not None)] if foco else []
    tambem = []
    if fogo and not confirma:
        # o fogo das últimas 24 h da NASA que NÃO é o foco da última hora (esse já está na prova, confirmado)
        tambem.append(f"Também: fogo visto pela NASA, {fogo_detalhe(fogo, ref)}")
    for e in eventos:
        if e["agir"]:
            principal = next(g for g in e["niveis"] if g["agir"])
            motivos.append(_motivo_do_aviso(principal))
            tambem += [f"Também: {g['nome']} ({g['severidade']}), {g['quando']}" for g in e["niveis"] if g is not principal]
        else:
            tambem.append(f"Também: {e['nome']} ({e['severidade']}), {e['quando']}")
    cartao = {
        "id": u.id, "nome": u.nome, "cliente": u.cliente, "uf": u.uf, "onde": f"{u.cliente} · {u.uf}" if u.uf else u.cliente,
        "nivel": nivel, "rotulo": A.ROTULO_NIVEL[nivel],
        "avisos": [{"evento": a.evento, "severidade": a.severidade, "nivel": a.nivel, "cor": COR_DO_AVISO[a.nivel],
                    "agir": A.aviso_manda_agir(a), "validade": _validade(a, ref),
                    "comeca": hora(a.inicio, ref) if a.inicio is not None and not A.em_vigor(a, ref) else ""} for a in avisos],
        "foco": None, "dias": dias, "risco_linha": risco_linha, "risco_origem": risco_origem,
        # os avisos iguais juntos (`grupos`: evento e nível) e um por evento (`eventos`: a tabela da Atenção mostra uma pílula por
        # evento, no nível mais alto, com a janela de todos e quando vale cada nível no balão)
        "grupos": grupos, "eventos": eventos,
        # por que a usina pede ação (o foco primeiro, depois os eventos que mandam agir, do mais grave), cada motivo com o que pode
        # acontecer na usina e o que conferir (`explica.py`), e o resto que ajuda a decidir
        "motivos": motivos,
        "contexto": tambem + [_contexto_do_risco(dias, risco_linha, risco_l.dados is not None)],
        "por_que": motivo_curto(avisos, foco, dias, ref, fogo),
        # o fogo das últimas 24 h da NASA (10/10/2026): a célula "Fogo a até 5 km" da Atenção e a página da usina
        "fogo24": ({"texto": f"a {numero(fogo['km'], 1)} km {idade(fogo['foco'].data, ref)}", "detalhe": fogo_detalhe(fogo, ref),
                    "classe": A.classe_frp(fogo["frp_max"])} if fogo else None),
        "_ordem": (-gravidade, -(1 if foco else 0), -((n_inmet > 0) + (n_foco > 0) + (n_risco > 0) + (n_fogo > 0)),
                   foco["km"] if foco else fogo["km"] if fogo else float("inf"), -n_inmet, chave_texto(u.nome)),
    }
    if foco:
        cartao["foco"] = {"texto": f"{_plural(foco['n'], 'foco', 'focos')} a até {A.FOCO_KM:g} km · o mais perto a "
                                   f"{numero(foco['km'], 1)} km ({foco['satelite']}, {hora(foco['hora'], ref)})"}
    return cartao


def _uf_da_grade(texto):
    uf = str(texto or "").strip().upper()
    return uf if uf in UFS_GRADE else None


def _grade_ufs(com_alerta: list, completa: bool) -> tuple:
    """(os 27 quadrados em ordem de leitura, quantas usinas com alerta ficaram sem UF válida). O número do quadrado é o de usinas
    com alerta (agir agora e atenção) no estado; a cor é a do pior nível. Usina com alerta e UF que não é uma das 27 siglas não
    some: o chamador diz quantas são."""
    por_uf, sem_uf = {}, 0
    for c in com_alerta:
        uf = _uf_da_grade(c["uf"])
        if uf is None:
            sem_uf += 1
            continue
        n, agir = por_uf.get(uf, (0, 0))
        por_uf[uf] = (n + 1, agir + (c["nivel"] == A.AGIR))
    quadrados = []
    for uf, (col, lin) in sorted(UFS_GRADE.items(), key=lambda kv: (kv[1][1], kv[1][0])):
        n, agir = por_uf.get(uf, (0, 0))
        if n:
            titulo = f"{uf}: {_plural(n, 'usina com alerta', 'usinas com alerta')}" + (f", {agir} para agir agora" if agir else "")
        else:
            titulo = f"{uf}: sem usina com alerta" + ("" if completa else " nas fontes lidas")
        quadrados.append({"uf": uf, "col": col, "row": lin, "n": n, "texto": str(n) if n else "·", "titulo": titulo,
                          "nivel": "agir" if agir else "atencao" if n else ""})
    return quadrados, sem_uf


def _qualificadores(ids, leituras, por_id) -> list:
    """O que a leitura das fontes `ids` tem de errado ou incompleto, para repetir no número da faixa que as usa: fonte sem leitura
    ("sem leitura de avisos do ... (INMET)", ou "lendo ..." enquanto a primeira leitura não veio) e fonte com dado mas não
    inteiro ("avisos do ... (INMET): parcial", "focos de queimada do ... (INPE): arquivos até 14:10"): o nome por extenso, como
    em toda a tela (09/10/2026)."""
    saida = []
    for i in ids:
        if leituras[i].dados is None:
            saida.append(f"{'lendo' if leituras[i].erro == L.LENDO else 'sem leitura de'} {NOME_LONGO[i]}")
        else:
            saida += [f"{NOME_LONGO[i]}: {q}" for q in por_id[i]["qualifica"]]
    return saida


def _celula_da_faixa(id_: str, rotulo: str, n, sub: str, qual: list, *, traco: bool, ambar: bool) -> dict:
    """Um dos quatro números do topo. `traco`: não há leitura para dizer o número ("—", nunca 0). `ambar`: o número vale, mas
    veio de fonte que não está inteira, e a cor deixa de ser a do "tudo bem"."""
    classe = f"cl-{id_}" + (" cl-nx" if traco else " cl-na" if ambar else "")
    if traco:
        return {"id": id_, "rotulo": rotulo, "valor": "—", "unidade": "", "sub": sub, "qual": qual, "classe": classe, "fazer": ""}
    # "O que fazer" (09/10/2026, "deixe mais didático") só quando há usina no nível: "avisar o supervisor" com zero usinas, ou
    # "nada" com o número em "—", diriam o contrário do que a tela sabe
    fazer = next((c["fazer"] for c in E.COMO_LER if c["id"] == id_), "") if n else ""
    return {"id": id_, "rotulo": rotulo, "valor": str(n), "unidade": "usina" if n == 1 else "usinas", "sub": sub, "qual": qual,
            "classe": classe, "fazer": fazer}


def _faixa(n_agir, n_atencao, n_sem, n_usinas, v, leituras, por_id) -> list:
    ids = ("inmet", "focos", "risco")
    ausentes = [i for i in ids if leituras[i].dados is None]

    def qual(nivel):
        return _qualificadores(FONTES_DO_NIVEL[nivel], leituras, por_id)

    def sem_nenhuma(nivel):
        return all(leituras[i].dados is None for i in FONTES_DO_NIVEL[nivel])

    q_agir, q_atencao, q_sem = qual("agir"), qual("atencao"), qual("sem")
    sub_sem = "não dá para dizer" if ausentes else "nas fontes lidas" if q_sem else "nas quatro fontes lidas"
    n_sem_risco = sum(len(g["nomes"]) for g in v["sem_risco"])
    cobertura = "em operação com coordenada"
    if n_sem_risco:
        cobertura += f" · {n_sem_risco} sem dado de risco"
    if v["sem_coordenada"]:
        cobertura += f" · {len(v['sem_coordenada'])} sem coordenada"
    if v["fora_do_brasil"]:
        cobertura += f" · {len(v['fora_do_brasil'])} com coordenada fora do Brasil"
    return [
        _celula_da_faixa("agir", "Agir agora", n_agir, SUB_AGIR, q_agir, traco=sem_nenhuma("agir"), ambar=bool(q_agir) and n_agir == 0),
        _celula_da_faixa("atencao", "Atenção", n_atencao, SUB_ATENCAO, q_atencao, traco=sem_nenhuma("atencao"),
                         ambar=bool(q_atencao) and n_atencao == 0),
        _celula_da_faixa("sem", "Sem alerta", n_sem, sub_sem, q_sem, traco=bool(ausentes), ambar=bool(q_sem)),
        _celula_da_faixa("cobertura", "Cobertura", n_usinas, cobertura, [], traco=False, ambar=False),
    ]


def glossario(cartoes: list) -> dict:
    """O "Entenda os alertas" do pé da tela (09/10/2026, "deixe mais didático"): os três níveis do INMET, o foco de queimada, o
    risco de fogo e cada evento: primeiro os que estão nos avisos de agora (na ordem em que aparecem), depois os outros que o
    `explica.py` conhece. Evento que o INMET publicar e que o `explica.py` não conhece entra com o texto genérico, nunca some."""
    agora_, vistos = [], set()
    for c in cartoes:
        for g in c["grupos"]:
            k = chave_texto(g["evento"])
            if k not in vistos:
                vistos.add(k)
                agora_.append({"nome": g["nome"], "conhecido": E.conhecido(g["evento"]), **E.evento(g["evento"])})
    outros = [{"nome": E.nome_amigavel(nome), "conhecido": True, **E.evento(nome)}
              for nome in E._EVENTOS if chave_texto(nome) not in vistos]
    return {"niveis": E.NIVEIS_INMET, "foco": E.FOCO, "risco": E.RISCO_FOGO, "fogo24": E.FOGO_24H, "forca": E.FORCA_DO_FOGO,
            "confianca": E.CONFIANCA, "eventos_agora": agora_, "eventos_outros": outros}


def montar(config, *, cadastro=None, erro_cadastro=None, cliente="", ref=None, sessao=None, todas=False) -> dict:
    """Tudo o que o template precisa. `cadastro` é o `usinas.Cadastro` (ou None com `erro_cadastro` dizendo por quê). `todas`:
    a matriz da Atenção mostra a lista inteira, e não só as `LIMITE_ATENCAO` primeiras."""
    ref = ref or agora()
    v = {"erro_cadastro": erro_cadastro, "atualizada": hora(ref, ref), "clientes": [], "cliente": "", "n_usinas": 0,
         "faixa": [], "fontes": [], "faltando": [], "lendo": [], "completa": True, "recarrega_em": RECARGA_S,
         "agir": [], "atencao": [], "alertas": [], "atencao_linhas": [], "n_atencao": 0, "atencao_resumida": False,
         "vazio_agir": "", "vazio_atencao": "", "sem_alerta": None, "aviso_vazio": "—", "foco_vazio": "—",
         "ufs": [], "ufs_legenda_sem": "", "ufs_sem_uf": 0, "sem_risco": [], "sem_coordenada": [], "fora_do_brasil": [],
         "ilegiveis": 0, "sem_usinas": False, "rotulos": list(DIAS), "limite_atencao": LIMITE_ATENCAO,
         "matriz_tem_entorno": False, "dias_amigaveis": [], "como_ler": E.COMO_LER, "glossario": glossario([])}
    if cadastro is None:
        return v
    v["clientes"] = cadastro.clientes()
    v["cliente"] = cliente if cliente in v["clientes"] else ""

    def pertence(u):
        return not v["cliente"] or u.cliente == v["cliente"]

    usinas = [u for u in cadastro.usinas if pertence(u)]
    v["n_usinas"] = len(usinas)
    v["sem_coordenada"] = [u.nome for u in cadastro.sem_coordenada if pertence(u)]
    v["fora_do_brasil"] = [u.nome for u in cadastro.fora_do_brasil if pertence(u)]
    v["ilegiveis"] = cadastro.ilegiveis
    if not usinas:
        v["sem_usinas"] = True          # nada a cruzar (cadastro sem coordenada, ou cliente sem usina no mapa): nem se vai à rede
        return v

    # O risco de fogo é lido para TODAS as usinas com coordenada, não só as do filtro: o filtro é da tela, e o cache
    # do risco vale pelo conjunto de pontos (mudar de cliente não pode refazer a leitura de 6 h).
    avisos_l = L.avisos(config, sessao)
    focos_l = L.focos(config, sessao)
    risco_l = L.risco(config, cadastro.pontos(), sessao)
    firms_l = L.firms(config, sessao)
    leituras = {"inmet": avisos_l, "focos": focos_l, "risco": risco_l, "firms": firms_l}
    indice = A.IndiceFocos(focos_l.dados["focos"]) if focos_l.dados else None
    nasa = indice_nasa(firms_l, ref)
    arquivo = _arquivo_t0(risco_l.dados) if risco_l.dados else None
    rotulos, amigaveis = rotulos_dos_dias(arquivo, ref), dias_amigaveis(arquivo, ref)
    cartoes = [_usina(u, avisos_l, indice, risco_l, ref, rotulos, amigaveis, nasa) for u in usinas]
    agir = sorted((c for c in cartoes if c["nivel"] == A.AGIR), key=lambda c: c["_ordem"])
    atencao = sorted((c for c in cartoes if c["nivel"] == A.ATENCAO), key=lambda c: c["_ordem"])
    fontes = [_fonte_inmet(avisos_l, ref), _fonte_focos(focos_l, ref), _fonte_risco(risco_l, ref, rotulos),
              _fonte_firms(firms_l, ref)]
    por_id = {f["id"]: f for f in fontes}

    v["fontes"] = fontes
    v["agir"], v["atencao"], v["alertas"] = agir, atencao, agir + atencao
    v["n_atencao"] = len(atencao)
    v["atencao_resumida"] = not todas and len(atencao) > LIMITE_ATENCAO
    v["atencao_linhas"] = atencao[:LIMITE_ATENCAO] if v["atencao_resumida"] else atencao
    v["rotulos"] = rotulos          # os quatro dias da matriz: pela data do arquivo do INPE, não fixos ("Ontem · Hoje · D+1 · D+2")
    v["dias_amigaveis"] = amigaveis  # os mesmos dias com o nome que se fala ("hoje", "amanhã", "sáb 11/10"): o cabeçalho da matriz
    v["glossario"] = glossario(cartoes)
    v["matriz_tem_entorno"] = any(d["nota"] for c in v["atencao_linhas"] for d in c["dias"] or [])
    ausentes = [i for i in ("inmet", "focos", "risco") if leituras[i].dados is None]
    # Fonte SEM leitura boa: ou ainda está sendo lida pela primeira vez ("lendo", a tela volta em 10 s) ou está fora. Os números
    # não a incluem, e a tela diz (uma lista curta demais parece "só essas têm alerta"). A NASA entra nesta nota, mas não em
    # `ausentes`: sem ela a usina não fica cinza (ver o cabeçalho do módulo).
    sem_leitura = ausentes + (["firms"] if firms_l.dados is None else [])
    v["lendo"] = [NOME_LONGO[i] for i in sem_leitura if leituras[i].erro == L.LENDO]
    v["faltando"] = [NOME_LONGO[i] for i in sem_leitura if leituras[i].erro != L.LENDO]
    v["completa"] = all(f["estado"] == "ok" for f in fontes)
    v["recarrega_em"] = RECARGA_LENDO_S if v["lendo"] else RECARGA_S

    def vazio(texto, ids):
        """O que a seção vazia diz. Só olha as fontes que ELA usa: o risco de fogo velho não tira o "nenhuma usina para agir"."""
        faltam = [NOME_LONGO[i] for i in ids if leituras[i].dados is None]
        if faltam:
            return f"Sem leitura de {_juntar(faltam)}: não dá para dizer que não há alerta"
        if any(por_id[i]["estado"] != "ok" for i in ids):
            return f"{texto} nas leituras disponíveis (veja o estado das fontes)"
        return texto

    v["vazio_agir"] = "" if agir else vazio("Nenhuma usina para agir agora", FONTES_DO_NIVEL["agir"])
    v["vazio_atencao"] = "" if atencao else vazio("Nenhuma usina em atenção", FONTES_DO_NIVEL["atencao"])
    # "Sem alerta" só se diz com as três fontes lidas; com alguma fora, "—" (o número seria "sem alerta nas fontes lidas")
    n_sem = len(cartoes) - len(agir) - len(atencao)
    v["sem_alerta"] = None if ausentes else n_sem
    # na tabela da Atenção: "nenhum" e "não" dizem com palavra que a fonte foi lida e não há (09/10/2026; antes era "—")
    v["aviso_vazio"] = "sem leitura" if avisos_l.dados is None else "nenhum"
    # o fogo das últimas 24 h da NASA também mora nessa célula: sem lê-la, o "não" vale só para a última hora
    v["foco_vazio"] = "sem leitura" if focos_l.dados is None else "não" if firms_l.dados is not None else "não na última hora"
    if risco_l.dados:
        for origem, motivo in MOTIVO_SEM_RISCO.items():
            nomes = [c["nome"] for c in cartoes if c["risco_origem"] == origem]
            if nomes:
                v["sem_risco"].append({"motivo": motivo, "nomes": nomes})
    v["faixa"] = _faixa(len(agir), len(atencao), n_sem, len(usinas), v, leituras, por_id)
    v["ufs"], v["ufs_sem_uf"] = _grade_ufs(agir + atencao, v["completa"])
    v["ufs_legenda_sem"] = "sem usina com alerta" + ("" if v["completa"] else " nas fontes lidas")
    return v


# ── a página de uma usina ────────────────────────────────────────────────────────────────────────────────────────────

SEM_COORDENADA = ("Sem coordenada no cadastro: sem latitude e longitude não há onde procurar aviso, foco, risco de fogo nem "
                  "irradiação. Corrija a coordenada no cadastro.")
FORA_DO_BRASIL = ("Coordenada fora do Brasil no cadastro: provável erro de digitação (zero, sinal ou latitude e longitude "
                  "trocadas). Sem uma coordenada certa não há onde procurar aviso, foco, risco de fogo nem irradiação. Corrija a "
                  "coordenada no cadastro.")
ETM_PROXIMA_ETAPA = {
    "texto": "Comparação com a ETM: próxima etapa",
    # O que a investigação de 07/10/2026 achou (ver nexus/performance/CLAUDE.md): o dado existe, a ligação com a usina não é certa.
    "motivo": ("O GHI medido da usina está nos livros BD_Thopen e BD_Performance (coluna \"GHI (kWh/m²)\", em kWh/m² por dia), mas ainda "
               "não há uma ligação certa entre esta usina do cadastro e a aba dela: no BD_Performance nenhuma aba leva o código do "
               "de-para, e no BD_Thopen o nome da aba nem sempre é o do de-para. Sem essa ligação a tela não compara, em vez de "
               "arriscar um \"conferir a ETM\" na usina errada."),
}


def _mes_ate_agora(m: dict, publicado_ate) -> dict:
    """O mês até agora, escrito para a página: o número, até que dia, e o que a soma NÃO tem (dia sem leitura no meio)."""
    nome = m["mes"].split("/")[0]
    if m["soma"] is None:
        texto = (f"A NASA não publicou nenhum dia nos últimos {L.JANELA_POWER_DIAS} dias" if publicado_ate is None
                 else f"A NASA ainda não publicou nenhum dia de {nome} (último dia publicado: {I.dd_mm(publicado_ate)})")
        return {"rotulo": m["mes"], "valor": "—", "unidade": "", "sub": "nenhum dia publicado", "texto": texto, "avisos": []}
    avisos = []
    if m["buracos"]:
        n = len(m["buracos"])
        avisos.append(f"{n} {'dia' if n == 1 else 'dias'} sem leitura da NASA ({', '.join(I.dd_mm(d) for d in m['buracos'])})")
    dias_ = _plural(m["n"], "dia", "dias")
    texto = f"{numero(m['soma'], 1)} kWh/m² em {dias_}, até {I.dd_mm(m['ate'])} (o último dia que a NASA publicou)"
    return {"rotulo": m["mes"], "valor": numero(m["soma"], 1), "unidade": "kWh/m²", "sub": f"{dias_}, até {I.dd_mm(m['ate'])}",
            "texto": texto + "".join(f"; {a}" for a in avisos), "avisos": avisos}


def _irradiacao(leitura, ref) -> dict:
    """O bloco da NASA POWER da página: o estado da leitura, o gráfico, o mês até agora e a tabela dia a dia. Sem leitura boa não
    há gráfico nem número (a página diz por quê); leitura velha mostra a última boa, dita velha, com a hora."""
    hoje = ref.astimezone(BRT).date()
    b = {"estado": "ok", "texto": "", "erro": "", "grafico": None, "mes": None, "tabela": []}
    falha = _falha(ROTULO_DA_FONTE["power"], leitura, ref)
    if leitura.dados is None:
        if leitura.erro == L.LENDO:
            b.update(estado="lendo", texto=f"Lendo a irradiação do {F.extenso('nasa_power')}: a página se atualiza sozinha")
        else:
            b.update(estado="fora", texto=falha[1], erro=leitura.erro or "")
        return b
    publicado_ate = leitura.dados["publicado_ate"]
    if falha is not None:
        b.update(estado="velha", texto=falha[1], erro=leitura.erro or "")
    else:
        b["texto"] = (f"{ROTULO_DA_FONTE['power']}: lida às {hora(_quando(leitura.lido_em), ref)}"
                      + (f" · publicada até {I.dd_mm(publicado_ate)}" if publicado_ate else ""))
    serie = I.ultimos_dias(leitura.dados["dias"], hoje)
    if publicado_ate is not None:
        b["grafico"] = I.grafico(serie, publicado_ate)
        b["tabela"] = [{"dia": I.dd_mm(d), "valor": numero(v) if v is not None else "—"} for d, v in serie]
    b["mes"] = _mes_ate_agora(I.mes_ate_agora(leitura.dados["dias"], hoje), publicado_ate)
    return b


def _fonte_nasa(leitura, ref, irradiacao: dict) -> dict:
    if leitura.dados is None or leitura.velha:
        falha = _falha(ROTULO_DA_FONTE["power"], leitura, ref)
        return {"id": "power", "estado": falha[0], "texto": falha[1], "detalhe": falha[2], "qualifica": []}
    return {"id": "power", "estado": "ok", "texto": irradiacao["texto"], "detalhe": "", "qualifica": []}


def montar_usina(config, *, cadastro, usina_id, cliente="", ref=None, sessao=None):
    """Tudo o que a página de uma usina precisa, ou None se a usina não é uma das em operação do cadastro (a rota responde 404).
    Usina sem coordenada utilizável (ou com coordenada fora do Brasil) vem com `pendencia` dizendo o que falta e NÃO vai a fonte
    nenhuma. Os alertas são os da tela principal (o mesmo `_usina`, as mesmas leituras e o mesmo cache: o risco de fogo é lido para
    todas as usinas do cadastro, não só para esta); a NASA é lida só aqui, pelo cache da usina."""
    ref = ref or agora()
    todas = cadastro.usinas + cadastro.sem_coordenada + cadastro.fora_do_brasil
    u = next((x for x in todas if x.id == str(usina_id)), None)
    if u is None:
        return None
    v = {"id": u.id, "nome": u.nome, "cliente": u.cliente, "uf": u.uf, "onde": f"{u.cliente} · {u.uf}" if u.uf else u.cliente,
         "atualizada": hora(ref, ref), "cliente_filtro": cliente if cliente in cadastro.clientes() else "", "pendencia": "",
         "recarrega_em": RECARGA_S, "nivel": "", "rotulo": "", "card": None, "alertas": None, "fontes": [], "faltando": [],
         "lendo": [], "irradiacao": None, "etm": ETM_PROXIMA_ETAPA}
    if u in cadastro.sem_coordenada:
        v["pendencia"] = SEM_COORDENADA
        return v
    if u in cadastro.fora_do_brasil:
        v["pendencia"] = FORA_DO_BRASIL
        return v
    avisos_l = L.avisos(config, sessao)
    focos_l = L.focos(config, sessao)
    risco_l = L.risco(config, cadastro.pontos(), sessao)
    firms_l = L.firms(config, sessao)
    leituras = {"inmet": avisos_l, "focos": focos_l, "risco": risco_l, "firms": firms_l}
    indice = A.IndiceFocos(focos_l.dados["focos"]) if focos_l.dados else None
    arquivo = _arquivo_t0(risco_l.dados) if risco_l.dados else None
    rotulos = rotulos_dos_dias(arquivo, ref)
    card = _usina(u, avisos_l, indice, risco_l, ref, rotulos, dias_amigaveis(arquivo, ref), indice_nasa(firms_l, ref))
    fontes = [_fonte_inmet(avisos_l, ref), _fonte_focos(focos_l, ref), _fonte_risco(risco_l, ref, rotulos),
              _fonte_firms(firms_l, ref)]
    nasa_l = L.irradiacao(config, u.id, u.lat, u.lon, ref.astimezone(BRT).date(), sessao)
    irradiacao = _irradiacao(nasa_l, ref)
    fontes.append(_fonte_nasa(nasa_l, ref, irradiacao))
    ausentes = [i for i in ("inmet", "focos", "risco") if leituras[i].dados is None]
    if card["nivel"] != A.SEM_ALERTA:
        v["nivel"], v["rotulo"] = card["nivel"], card["rotulo"]
    elif ausentes:                       # sem alerta nas fontes lidas não é "sem alerta" quando falta fonte
        v["nivel"], v["rotulo"] = "duvida", "Sem leitura completa"
    elif any(f["qualifica"] for f in fontes[:3]) or fontes[3]["estado"] != "ok":
        v["nivel"], v["rotulo"] = "sem", "Sem alerta nas fontes lidas"
    else:
        v["nivel"], v["rotulo"] = "sem", "Sem alerta"
    v["card"], v["fontes"], v["irradiacao"] = card, fontes, irradiacao
    v["alertas"] = {
        "avisos": card["avisos"],
        "avisos_vazio": "" if card["avisos"] else (f"Sem leitura dos avisos do {F.extenso('inmet')}" if avisos_l.dados is None
                                                  else f"Nenhum aviso do {F.extenso('inmet')} sobre esta usina"),
        "foco": (card["foco"]["texto"] if card["foco"] else f"Sem leitura dos focos do {F.extenso('inpe')}" if focos_l.dados is None
                 else f"Nenhum foco a até {A.FOCO_KM:g} km"),
        "fogo24": (card["fogo24"]["detalhe"] if card["fogo24"] else
                   f"Sem leitura do fogo das últimas 24 h da {F.extenso('nasa_firms')}" if firms_l.dados is None
                   else f"Nenhum fogo a até {A.FOGO_24H_KM:g} km nas últimas {A.FOGO_24H_H} h"),
        "dias": card["dias"], "risco_linha": card["risco_linha"],
        "risco_vazio": None if card["dias"] else f"Sem leitura do risco de fogo do {F.extenso('inpe')}",
    }
    sem_leitura = ausentes + (["firms"] if firms_l.dados is None else [])
    v["lendo"] = [NOME_LONGO[i] for i in sem_leitura if leituras[i].erro == L.LENDO]
    v["faltando"] = [NOME_LONGO[i] for i in sem_leitura if leituras[i].erro != L.LENDO]
    v["recarrega_em"] = RECARGA_LENDO_S if (v["lendo"] or irradiacao["estado"] == "lendo") else RECARGA_S
    return v
