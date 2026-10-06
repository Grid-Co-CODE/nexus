"""O que a tela Clima e risco mostra (06/10/2026): junta as leituras das três fontes com as usinas do cadastro e escreve os
textos, sem Flask (a view só chama `montar` e renderiza).

Gravidade, a mesma régua de três degraus (semáforo) para os três tipos de alerta:
  3 crítico   aviso "Grande Perigo" do INMET; foco de queimada a até 5 km (é um evento, não uma previsão); risco de fogo crítico
  2 alto      aviso "Perigo"; risco de fogo alto
  1 atenção   aviso "Perigo Potencial"
A usina vale o pior dos seus alertas. No empate: a que tem foco primeiro, depois a que tem mais tipos de alerta, o foco mais
perto, o aviso mais grave e, por fim, o nome.

Onde a fonte não tem leitura a tela mostra "—", nunca "0": zero é "li e não há alerta".
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


# ── risco de fogo, dia a dia ─────────────────────────────────────────────────────────────────────────────────────────

def celula_de_risco(i: int, amostra) -> dict:
    """Um dos quatro dias do risco de fogo de uma usina, escrito pela origem do valor: o do pixel dela, o do entorno de
    5 x 5 (quando o pixel é nodata: o INPE não calcula onde não há vegetação), ou a razão de não haver número."""
    rotulo = DIAS[i]
    if amostra.origem in ("ponto", "entorno") and amostra.valor is not None:
        classe = A.classe_risco_fogo(amostra.valor)
        return {"rotulo": rotulo, "valor": numero(amostra.valor), "classe": classe, "nivel": A.nivel_do_risco(classe),
                "nota": "entorno" if amostra.origem == "entorno" else ""}
    texto = {"sem_dado": SEM_DADO, "indisponivel": "indisponível", "fora_da_grade": "fora da grade do INPE"}.get(
        amostra.origem, "sem dado")
    return {"rotulo": rotulo, "valor": texto, "classe": "", "nivel": 0, "nota": ""}


# ── o estado de cada fonte ───────────────────────────────────────────────────────────────────────────────────────────

def _falha(nome: str, leitura, ref: datetime):
    """(estado, texto, detalhe) se a fonte não está limpa; None se está. "fora agora; última leitura boa às HH:MM" é a frase
    que o plano pede para a fonte que caiu: a tela nunca mostra dado velho como se fosse de agora."""
    if leitura.dados is None:
        if leitura.erro == L.LENDO:
            return "atencao", f"{nome}: lendo a fonte (a tela se atualiza sozinha)", ""
        return "fora", f"{nome} fora agora; ainda sem leitura boa", leitura.erro or ""
    if leitura.velha:
        return ("atencao", f"{nome} fora agora; última leitura boa às {hora(_quando(leitura.lido_em), ref)}",
                leitura.erro or "")
    return None


def _fonte_inmet(leitura, ref) -> dict:
    f = _falha("INMET", leitura, ref)
    if f:
        return {"id": "inmet", "estado": f[0], "texto": f[1], "detalhe": f[2]}
    d = leitura.dados
    n_hoje = sum(a.quando == "hoje" for a in d["avisos"])
    texto = (f"INMET · avisos: lido às {hora(_quando(leitura.lido_em), ref)} · "
             f"{_plural(len(d['avisos']), 'aviso ativo', 'avisos ativos')} ({n_hoje} hoje, {len(d['avisos']) - n_hoje} futuros)")
    detalhe = (f"{_plural(len(d['ignorados']), 'aviso foi ignorado', 'avisos foram ignorados')} por falta de polígono utilizável"
               if d["ignorados"] else "")
    return {"id": "inmet", "estado": "ok", "texto": texto, "detalhe": detalhe}


def _fonte_focos(leitura, ref) -> dict:
    f = _falha("INPE (focos)", leitura, ref)
    if f:
        return {"id": "focos", "estado": f[0], "texto": f[1], "detalhe": f[2]}
    d = leitura.dados
    ate, lido = d["ate"], hora(_quando(leitura.lido_em), ref)
    detalhe = (f"{len(d['falhos'])} de {len(d['arquivos']) + len(d['falhos'])} arquivos indisponíveis"
               if d["falhos"] else "")
    if ref - ate.astimezone(BRT) > timedelta(minutes=FOCOS_ATRASO_MIN):
        return {"id": "focos", "estado": "atencao", "detalhe": detalhe,
                "texto": f"INPE · focos de queimada: o INPE não publica arquivo novo desde {hora(ate, ref)} · lido às {lido}"}
    return {"id": "focos", "estado": "ok", "detalhe": detalhe,
            "texto": f"INPE · focos de queimada: arquivos até {hora(ate, ref)} · lido às {lido} · "
                     f"{_plural(len(d['focos']), 'foco', 'focos')} na última hora"}


def _fonte_risco(leitura, ref) -> dict:
    f = _falha("INPE (risco de fogo)", leitura, ref)
    if f:
        return {"id": "risco", "estado": f[0], "texto": f[1], "detalhe": f[2]}
    d = leitura.dados
    erros = "; ".join(f"{DIAS[dia]} indisponível ({motivo})" for dia, motivo in sorted(d["erros"].items()))
    arquivo = d["arquivos"].get(0) or next((v for v in d["arquivos"].values() if v), None)
    lido = hora(_quando(leitura.lido_em), ref)
    if arquivo is None:
        return {"id": "risco", "estado": "atencao" if erros else "ok", "detalhe": erros,
                "texto": f"INPE · risco de fogo: lido às {lido}"}
    a = arquivo.astimezone(BRT)
    texto = f"INPE · risco de fogo: previsão de {a:%d/%m} (arquivo das {a:%H:%M})"
    estado = "atencao" if erros else "ok"
    if a.date() != ref.date():
        estado = "atencao"
        texto += " · de ontem" if a.date() == (ref - timedelta(days=1)).date() else f" · de {a:%d/%m}"
    return {"id": "risco", "estado": estado, "detalhe": erros, "texto": texto + f" · lido às {lido}"}


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def _validade(a, ref) -> str:
    fim = f", até {hora(a.fim, ref)}" if a.fim else ""
    return "em vigor" + fim if A.em_vigor(a, ref) else f"começa {hora(a.inicio, ref)}" + fim


def _usina(u, avisos_l, indice, risco_l, ref):
    avisos = A.avisos_que_contem(u.lat, u.lon, avisos_l.dados["avisos"], ref) if avisos_l.dados else []
    foco = indice.perto(u.lat, u.lon) if indice is not None else None
    dias = None
    if risco_l.dados:
        dias = [celula_de_risco(i, a) for i, a in enumerate(risco_l.dados["por_ponto"].get(u.id, []))] or None
    n_inmet = max((a.nivel for a in avisos), default=0)
    n_foco = 3 if foco else 0
    n_risco = max((c["nivel"] for c in dias or []), default=0)
    nivel = max(n_inmet, n_foco, n_risco)
    cartao = {
        "nome": u.nome, "cliente": u.cliente, "uf": u.uf, "nivel": nivel, "rotulo": NIVEL_ROTULO.get(nivel, ""),
        "avisos": [{"evento": a.evento, "severidade": a.severidade, "nivel": a.nivel, "validade": _validade(a, ref)}
                   for a in avisos],
        "foco": None, "dias": dias,
        "_ordem": (-nivel, -(1 if foco else 0), -((n_inmet > 0) + (n_foco > 0) + (n_risco > 0)),
                   foco["km"] if foco else float("inf"), -n_inmet, chave_texto(u.nome)),
        "_tem_aviso": bool(avisos), "_em_vigor": any(A.em_vigor(a, ref) for a in avisos), "_n_inmet": n_inmet,
        "_n_foco": n_foco, "_n_risco": n_risco, "_foco_km": foco["km"] if foco else None,
        "_risco_por_dia": [c["nivel"] > 0 for c in dias] if dias else None,
        "risco_sem_dado": bool(dias) and all(c["valor"] == SEM_DADO for c in dias),
    }
    if foco:
        cartao["foco"] = {"texto": f"{_plural(foco['n'], 'foco', 'focos')} a até {A.FOCO_KM:g} km · o mais perto a "
                                   f"{numero(foco['km'], 1)} km ({foco['satelite']}, {hora(foco['hora'], ref)})"}
    return cartao


def _cartao_resumo(id_, rotulo, tem_dado, valor, sub, nivel) -> dict:
    return {"id": id_, "rotulo": rotulo, "valor": str(valor) if tem_dado else "—",
            "sub": sub if tem_dado else "fonte fora", "classe": f"cl-n{nivel}" if tem_dado else "cl-nx"}


def montar(config, *, cadastro=None, erro_cadastro=None, cliente="", ref=None, sessao=None) -> dict:
    """Tudo o que o template precisa. `cadastro` é o `usinas.Cadastro` (ou None com `erro_cadastro` dizendo por quê)."""
    ref = ref or agora()
    v = {"erro_cadastro": erro_cadastro, "atualizada": hora(ref, ref), "clientes": [], "cliente": "", "n_usinas": 0,
         "resumo": [], "fontes": [], "faltando": [], "alertas": [], "sem_alerta": 0, "sem_risco": [], "sem_coordenada": [],
         "fora_do_brasil": [], "ilegiveis": 0, "sem_usinas": False}
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
    cartoes = [_usina(u, avisos_l, indice, risco_l, ref) for u in usinas]
    com_alerta = sorted((c for c in cartoes if c["nivel"] > 0), key=lambda c: c["_ordem"])

    com_aviso = [c for c in cartoes if c["_tem_aviso"]]
    com_foco = [c for c in cartoes if c["_n_foco"]]
    com_risco = [c for c in cartoes if c["_n_risco"]]
    por_dia = [sum(1 for c in cartoes if c["_risco_por_dia"] and c["_risco_por_dia"][i]) for i in range(len(DIAS))]
    v["resumo"] = [
        _cartao_resumo("avisos", "Aviso do INMET", avisos_l.dados is not None, len(com_aviso),
                       f"{sum(c['_em_vigor'] for c in com_aviso)} em vigor agora" if com_aviso
                       else "nenhum aviso sobre as usinas", max((c["_n_inmet"] for c in cartoes), default=0)),
        _cartao_resumo("focos", f"Foco a até {A.FOCO_KM:g} km", focos_l.dados is not None, len(com_foco),
                       f"o mais perto a {numero(min(c['_foco_km'] for c in com_foco), 1)} km" if com_foco
                       else f"nenhum foco a até {A.FOCO_KM:g} km", 3 if com_foco else 0),
        _cartao_resumo("risco", "Risco de fogo alto ou crítico", risco_l.dados is not None, len(com_risco),
                       " · ".join(f"{'hoje' if i == 0 else d} {n}" for i, (d, n) in enumerate(zip(DIAS, por_dia))),
                       max((c["_n_risco"] for c in cartoes), default=0)),
    ]
    v["fontes"] = [_fonte_inmet(avisos_l, ref), _fonte_focos(focos_l, ref), _fonte_risco(risco_l, ref)]
    # Fonte sem NENHUMA leitura boa: a lista e os números não a incluem, e a tela diz (uma lista curta demais parece "só
    # essas têm alerta"). A leitura velha ainda vale, com a hora dela, e não entra aqui.
    v["faltando"] = [nome for nome, leitura in (("avisos do INMET", avisos_l), ("focos do INPE", focos_l),
                                                ("risco de fogo do INPE", risco_l)) if leitura.dados is None]
    v["alertas"] = com_alerta
    v["sem_alerta"] = len(cartoes) - len(com_alerta)
    if risco_l.dados:
        v["sem_risco"] = [c["nome"] for c in cartoes if c["risco_sem_dado"]]
    return v
