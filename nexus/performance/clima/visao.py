"""O que a tela Clima e risco mostra (06/10/2026): junta as leituras das três fontes com as usinas do cadastro e escreve os
textos, sem Flask (a view só chama `montar` e renderiza).

Gravidade, a mesma régua de três degraus (semáforo) para os três tipos de alerta:
  3 crítico   aviso "Grande Perigo" do INMET; foco de queimada a até 5 km (é um evento, não uma previsão); risco de fogo crítico
  2 alto      aviso "Perigo"; risco de fogo alto
  1 atenção   aviso "Perigo Potencial"
A usina vale o pior dos seus alertas. No empate: a que tem foco primeiro, depois a que tem mais tipos de alerta, o foco mais
perto, o aviso mais grave e, por fim, o nome.

A tela não pode parecer "tudo bem" quando a fonte não foi lida inteira (revisão de 06/10/2026):
- onde a fonte não tem leitura, o número é "—", nunca "0" (zero é "li e não há alerta"), e a lista diz que não a inclui;
- fonte lida só em parte (aviso sem polígono, arquivo de focos que falhou, linhas ilegíveis, dia do risco sem leitura), velha
  (a última leitura boa, com a hora) ou com o dado atrasado (focos parados, previsão de outro dia, sem a data do arquivo)
  fica em "atencao", nunca "ok", e os três cartões do topo repetem o qualificador ("parcial", "dado de HH:MM"...), em âmbar
  no lugar do verde quando não há alerta;
- sem alerta algum e sem ter lido tudo, o título não diz "nenhuma usina com alerta agora": diz que não dá para dizer.
"""
from datetime import datetime, timedelta, timezone

from ...cadastro.servico import chave_texto
from . import alertas as A
from . import leitura as L

BRT = timezone(timedelta(hours=-3))
DIAS = ("Hoje", "D+1", "D+2", "D+3")
NIVEL_ROTULO = {3: "Crítico", 2: "Alto", 1: "Atenção"}
FOCOS_ATRASO_MIN = 30          # o INPE publica a cada 10 min: sem arquivo novo há 30 min, algo está atrasado
SEM_DADO = "sem dado (sem vegetação no entorno)"
FORA_DA_GRADE = "fora da grade do INPE"
MOTIVO_SEM_RISCO = {"sem_dado": "sem vegetação no entorno", "fora_da_grade": FORA_DA_GRADE}
RECARGA_S = 60                 # a tela se recarrega a cada minuto...
RECARGA_LENDO_S = 10           # ...e a cada 10 s enquanto alguma fonte está sendo lida pela primeira vez


def agora() -> datetime:
    return datetime.now(BRT)


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


def celula_de_risco(i: int, amostra, rotulos=DIAS) -> dict:
    """Um dos quatro dias do risco de fogo de uma usina, escrito pela origem do valor: o do pixel dela, o do entorno de
    5 x 5 (quando o pixel é nodata: o INPE não calcula onde não há vegetação), ou a razão de não haver número."""
    rotulo = rotulos[i]
    if amostra.origem in ("ponto", "entorno") and amostra.valor is not None:
        classe = A.classe_risco_fogo(amostra.valor)
        return {"rotulo": rotulo, "valor": numero(amostra.valor), "classe": classe, "nivel": A.nivel_do_risco(classe),
                "nota": "entorno" if amostra.origem == "entorno" else "", "origem": amostra.origem}
    texto = {"sem_dado": SEM_DADO, "indisponivel": "indisponível", "fora_da_grade": FORA_DA_GRADE}.get(
        amostra.origem, "sem dado")
    return {"rotulo": rotulo, "valor": texto, "classe": "", "nivel": 0, "nota": "", "origem": amostra.origem}


# ── o estado de cada fonte ───────────────────────────────────────────────────────────────────────────────────────────

def _falha(nome: str, leitura, ref: datetime):
    """(estado, texto, detalhe) se a fonte não tem leitura ou só tem a velha; None se está limpa. "fora agora; última leitura
    boa às HH:MM" é a frase que o plano pede para a fonte que caiu: a tela nunca mostra dado velho como se fosse de agora."""
    if leitura.dados is None:
        if leitura.erro == L.LENDO:
            return "atencao", f"{nome}: lendo a fonte (a tela se atualiza sozinha)", ""
        return "fora", f"{nome} fora agora; ainda sem leitura boa", leitura.erro or ""
    if leitura.velha:
        return ("atencao", f"{nome} fora agora; última leitura boa às {hora(_quando(leitura.lido_em), ref)}",
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
    falha = _falha("INMET", leitura, ref)
    if leitura.dados is None:
        return _sem_dado("inmet", falha)
    d = leitura.dados
    n_hoje = sum(a.quando == "hoje" for a in d["avisos"])
    texto = (f"INMET · avisos: lido às {hora(_quando(leitura.lido_em), ref)} · "
             f"{_plural(len(d['avisos']), 'aviso ativo', 'avisos ativos')} ({n_hoje} hoje, {len(d['avisos']) - n_hoje} futuros)")
    parciais = ([f"{_plural(len(d['ignorados']), 'aviso foi ignorado', 'avisos foram ignorados')} por falta de polígono utilizável"]
                if d["ignorados"] else [])
    return _fechar("inmet", leitura, ref, falha, texto, parciais)


def _fonte_focos(leitura, ref) -> dict:
    falha = _falha("INPE (focos)", leitura, ref)
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
        texto = f"INPE · focos de queimada: o INPE não publica arquivo novo desde {hora(ate, ref)} · lido às {lido}"
        atrasos = [f"arquivos até {hora(ate, ref)}"]
    else:
        texto = (f"INPE · focos de queimada: arquivos até {hora(ate, ref)} · lido às {lido} · "
                 f"{_plural(len(d['focos']), 'foco', 'focos')} na última hora")
        atrasos = []
    return _fechar("focos", leitura, ref, falha, texto, parciais, atrasos)


def _fonte_risco(leitura, ref, rotulos) -> dict:
    falha = _falha("INPE (risco de fogo)", leitura, ref)
    if leitura.dados is None:
        return _sem_dado("risco", falha)
    d = leitura.dados
    parciais = [f"{rotulos[dia]} indisponível ({motivo})" for dia, motivo in sorted(d["erros"].items())]
    arquivo, lido, atrasos = _arquivo_t0(d), hora(_quando(leitura.lido_em), ref), []
    if arquivo is None:
        # sem Last-Modified não há como dizer de que dia é a previsão (nem se o arquivo mudou no meio da leitura)
        texto = f"INPE · risco de fogo: sem data do arquivo · lido às {lido}"
        atrasos.append("sem data do arquivo")
    else:
        a = arquivo.astimezone(BRT)
        texto = f"INPE · risco de fogo: previsão de {a:%d/%m} (arquivo das {a:%H:%M})"
        if a.date() != ref.astimezone(BRT).date():
            atrasos.append(f"previsão de {a:%d/%m}")
            texto += " · de ontem" if a.date() == (ref - timedelta(days=1)).astimezone(BRT).date() else f" · de {a:%d/%m}"
        texto += f" · lido às {lido}"
    return _fechar("risco", leitura, ref, falha, texto, parciais, atrasos)


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def _validade(a, ref) -> str:
    fim = f", até {hora(a.fim, ref)}" if a.fim else ""
    return "em vigor" + fim if A.em_vigor(a, ref) else f"começa {hora(a.inicio, ref)}" + fim


def _usina(u, avisos_l, indice, risco_l, ref, rotulos):
    avisos = A.avisos_que_contem(u.lat, u.lon, avisos_l.dados["avisos"], ref) if avisos_l.dados else []
    foco = indice.perto(u.lat, u.lon) if indice is not None else None
    dias = None
    if risco_l.dados:
        dias = [celula_de_risco(i, a, rotulos) for i, a in enumerate(risco_l.dados["por_ponto"].get(u.id, []))] or None
    n_inmet = max((a.nivel for a in avisos), default=0)
    n_foco = 3 if foco else 0
    n_risco = max((c["nivel"] for c in dias or []), default=0)
    nivel = max(n_inmet, n_foco, n_risco)
    # Os quatro dias sem número pelo mesmo motivo (sem vegetação em volta, ou fora da grade do INPE) viram UMA linha, e a usina
    # entra na lista de "risco de fogo sem dado" com o motivo.
    risco_linha = risco_origem = None
    if dias and dias[0]["origem"] in MOTIVO_SEM_RISCO and all(c["origem"] == dias[0]["origem"] for c in dias):
        risco_linha, risco_origem = dias[0]["valor"], dias[0]["origem"]
    cartao = {
        "nome": u.nome, "cliente": u.cliente, "uf": u.uf, "nivel": nivel, "rotulo": NIVEL_ROTULO.get(nivel, ""),
        "avisos": [{"evento": a.evento, "severidade": a.severidade, "nivel": a.nivel, "validade": _validade(a, ref)}
                   for a in avisos],
        "foco": None, "dias": dias, "risco_linha": risco_linha, "risco_origem": risco_origem,
        "_ordem": (-nivel, -(1 if foco else 0), -((n_inmet > 0) + (n_foco > 0) + (n_risco > 0)),
                   foco["km"] if foco else float("inf"), -n_inmet, chave_texto(u.nome)),
        "_tem_aviso": bool(avisos), "_em_vigor": any(A.em_vigor(a, ref) for a in avisos), "_n_inmet": n_inmet,
        "_n_foco": n_foco, "_n_risco": n_risco, "_foco_km": foco["km"] if foco else None,
        "_risco_por_dia": [c["nivel"] > 0 for c in dias] if dias else None,
    }
    if foco:
        cartao["foco"] = {"texto": f"{_plural(foco['n'], 'foco', 'focos')} a até {A.FOCO_KM:g} km · o mais perto a "
                                   f"{numero(foco['km'], 1)} km ({foco['satelite']}, {hora(foco['hora'], ref)})"}
    return cartao


def _cartao_resumo(id_, rotulo, leitura, fonte, valor, sub, nivel) -> dict:
    """Um dos três números do topo. Sem leitura: "—" e a razão. Com leitura que não está inteira (`fonte["qualifica"]`), o
    número fica, o qualificador vai no fim do texto, e a cor deixa de ser o verde do "zero alertas" (vira âmbar): a cor da
    gravidade só some quando não há gravidade nenhuma a mostrar."""
    if leitura.dados is None:
        return {"id": id_, "rotulo": rotulo, "valor": "—", "classe": "cl-nx",
                "sub": "lendo a fonte" if leitura.erro == L.LENDO else "fonte fora"}
    qualifica = fonte["qualifica"]
    return {"id": id_, "rotulo": rotulo, "valor": str(valor), "sub": " · ".join([sub, *qualifica]),
            "classe": f"cl-n{nivel}" if (nivel or not qualifica) else "cl-na"}


def montar(config, *, cadastro=None, erro_cadastro=None, cliente="", ref=None, sessao=None) -> dict:
    """Tudo o que o template precisa. `cadastro` é o `usinas.Cadastro` (ou None com `erro_cadastro` dizendo por quê)."""
    ref = ref or agora()
    v = {"erro_cadastro": erro_cadastro, "atualizada": hora(ref, ref), "clientes": [], "cliente": "", "n_usinas": 0,
         "resumo": [], "fontes": [], "faltando": [], "lendo": [], "completa": True, "recarrega_em": RECARGA_S,
         "titulo_lista": "", "sem_alerta_texto": "", "alertas": [], "sem_alerta": 0, "sem_risco": [],
         "sem_coordenada": [], "fora_do_brasil": [], "ilegiveis": 0, "sem_usinas": False}
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
    indice = A.IndiceFocos(focos_l.dados["focos"]) if focos_l.dados else None
    rotulos = rotulos_dos_dias(_arquivo_t0(risco_l.dados) if risco_l.dados else None, ref)
    cartoes = [_usina(u, avisos_l, indice, risco_l, ref, rotulos) for u in usinas]
    com_alerta = sorted((c for c in cartoes if c["nivel"] > 0), key=lambda c: c["_ordem"])
    fontes = [_fonte_inmet(avisos_l, ref), _fonte_focos(focos_l, ref), _fonte_risco(risco_l, ref, rotulos)]
    por_id = {f["id"]: f for f in fontes}

    com_aviso = [c for c in cartoes if c["_tem_aviso"]]
    com_foco = [c for c in cartoes if c["_n_foco"]]
    com_risco = [c for c in cartoes if c["_n_risco"]]
    # Dia do risco sem leitura: "—", nunca 0 (zero é "li e não há alerta").
    sem_leitura = set(risco_l.dados["erros"]) if risco_l.dados else set()
    por_dia = ["—" if i in sem_leitura else str(sum(1 for c in cartoes if c["_risco_por_dia"] and c["_risco_por_dia"][i]))
               for i in range(len(DIAS))]
    sub_risco = " · ".join(f"{rotulos[i].lower() if rotulos[i] in ('Hoje', 'Ontem') else rotulos[i]} {por_dia[i]}"
                           for i in range(len(DIAS)))
    v["resumo"] = [
        _cartao_resumo("avisos", "Aviso do INMET", avisos_l, por_id["inmet"], len(com_aviso),
                       f"{sum(c['_em_vigor'] for c in com_aviso)} em vigor agora" if com_aviso
                       else "nenhum aviso sobre as usinas", max((c["_n_inmet"] for c in cartoes), default=0)),
        _cartao_resumo("focos", f"Foco a até {A.FOCO_KM:g} km", focos_l, por_id["focos"], len(com_foco),
                       f"o mais perto a {numero(min(c['_foco_km'] for c in com_foco), 1)} km" if com_foco
                       else f"nenhum foco a até {A.FOCO_KM:g} km", 3 if com_foco else 0),
        _cartao_resumo("risco", "Risco de fogo alto ou crítico", risco_l, por_id["risco"], len(com_risco), sub_risco,
                       max((c["_n_risco"] for c in cartoes), default=0)),
    ]
    v["fontes"] = fontes
    nomes_das_fontes = (("avisos do INMET", avisos_l), ("focos do INPE", focos_l), ("risco de fogo do INPE", risco_l))
    # Fonte SEM leitura boa: ou ainda está sendo lida pela primeira vez ("lendo", a tela volta em 10 s) ou está fora. A lista
    # e os números não a incluem, e a tela diz (uma lista curta demais parece "só essas têm alerta").
    v["lendo"] = [n for n, leitura in nomes_das_fontes if leitura.dados is None and leitura.erro == L.LENDO]
    v["faltando"] = [n for n, leitura in nomes_das_fontes if leitura.dados is None and leitura.erro != L.LENDO]
    v["completa"] = all(f["estado"] == "ok" for f in fontes)
    v["recarrega_em"] = RECARGA_LENDO_S if v["lendo"] else RECARGA_S
    v["alertas"] = com_alerta
    v["sem_alerta"] = len(cartoes) - len(com_alerta)
    ausentes = [n for n, leitura in nomes_das_fontes if leitura.dados is None]       # na ordem do painel das fontes
    if com_alerta:
        v["titulo_lista"] = f"Usinas com alerta ({len(com_alerta)}), da mais grave para a menos"
    elif ausentes:
        v["titulo_lista"] = f"Sem leitura de {_juntar(ausentes)}: não dá para dizer que não há alerta"
    elif not v["completa"]:
        v["titulo_lista"] = "Nenhuma usina com alerta nas leituras disponíveis (veja o estado das fontes)"
    else:
        v["titulo_lista"] = "Nenhuma usina com alerta agora"
    v["sem_alerta_texto"] = (f"{_plural(v['sem_alerta'], 'usina sem alerta', 'usinas sem alerta')} "
                             f"{'agora' if v['completa'] else 'nas fontes lidas'}.")
    if risco_l.dados:
        for origem, motivo in MOTIVO_SEM_RISCO.items():
            nomes = [c["nome"] for c in cartoes if c["risco_origem"] == origem]
            if nomes:
                v["sem_risco"].append({"motivo": motivo, "nomes": nomes})
    return v
