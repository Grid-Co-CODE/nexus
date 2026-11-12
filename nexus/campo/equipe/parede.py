"""O painel do vídeo wall do Mapa de equipe (12/11/2026). Levi, com o mockup do COS ("COS · Ocorrências abertas ·
Usinas com problema agora"): "Prepare um modo vídeo wall que apareça informações como no anexo 1 do lado esquerdo do
mapa!". As escolhas dele no mesmo dia: TODAS as ocorrências abertas, agrupadas (a mais grave e a mais antiga primeiro);
a tela se atualiza a cada 2 minutos; a lista que não cabe rola sozinha, devagar.

De onde vem: a MESMA fotografia da Ronda COS que dá a cor das usinas no mapa (`comando.usinas.cos_por_usina`, a do
Andamento, cópia de 30 s por cliente), na régua de Comando > Usinas (`comando.usinas.classificar`), só refinada em
grupos: o crítico que é falta de energia da rede vai à Rede concessionária, o resto do crítico é usina parada; o
inversor, a comunicação e o que sobra (furto, outra corretiva) têm o grupo deles. Uma usina é UM cartão, no grupo da
pior ocorrência dela (a mesma que pinta a usina no mapa), com "e mais N" quando há outras. Nada se inventa: o PR do dia
do mockup ficou fora (o Nexus não tem o PR de hoje), e sem a fotografia o painel diz que não leu.

Funções puras: a rota lê as fontes e passa o dado já lido, e o teste prova a conta (`tests/test_equipe_parede.py`)."""
from datetime import datetime

from ...comando import usinas as CU
from ...cos import andamento as AND

# os grupos na ordem do painel (a do mockup: usina desligada, inversores, rede; depois comunicação e as outras):
# (id, título, rótulo curto do número de cima, tom)
GRUPOS = (("parada", "Usina parada", "Usina parada", "critico"),
          ("inversor", "Inversores desligados", "Inversor fora", "alerta"),
          ("rede", "Rede concessionária", "Rede", "critico"),
          ("com", "Sem comunicação", "Comunicação", "neutro"),
          ("outras", "Outras ocorrências", "Outras", "alerta"))
# a pior ocorrência da usina decide o grupo do cartão: o crítico primeiro (a parada antes da rede), depois a atenção
# (o inversor antes das outras) e a comunicação por último, como o Agora de Comando > Usinas pinta a usina
_GRAVIDADE = {"parada": 0, "rede": 1, "inversor": 2, "outras": 3, "com": 4}


def grupo(oc: dict) -> str:
    """O grupo do painel de UMA ocorrência aberta da Ronda COS, pela régua de Comando > Usinas."""
    g, _rot = CU.classificar(oc)
    falha, prob = CU._norm(oc.get("tipo_falha")), CU._norm(oc.get("problema"))
    if g == "critico":
        # a Rede concessionária é o grupo `rede` do placar da própria Ronda COS (a regra de lá; o religamento de uma
        # usina que a rede derrubou também é dela), ou a falha que diz concessionária
        return "rede" if prob == "rede" or "concessionaria" in falha else "parada"
    if g == "sem_com":
        return "com"
    if "inversor" in falha or prob == "inv":
        return "inversor"
    return "outras"


def duracao(minutos: int) -> str:
    """Há quanto tempo, como o mockup conta: "12 min", "2 h 12", "1 d 4 h", "6 d"."""
    m = max(0, int(minutos))
    if m < 1:
        return "agora"
    if m < 60:
        return f"{m} min"
    h, mm = divmod(m, 60)
    if h < 24:
        return f"{h} h {mm:02d}"
    d, hh = divmod(h, 24)
    return f"{d} d {hh} h" if hh and d < 2 else f"{d} d"


def tom_da_etapa(etapa: str) -> str:
    """A cor da etapa da Ronda COS na etiqueta: esperando alguém = atenção; técnico acionado ou em campo = informação;
    recém-identificada = crítico; o resto, neutro."""
    e = CU._norm(etapa)
    if "aguardando" in e:
        return "alerta"
    if "tecnico" in e or "campo" in e or "atendimento" in e:
        return "info"
    if "identificad" in e or e == "nova":
        return "critico"
    return "neutro"


def _hora(iso, agora: datetime) -> str:
    q = AND.instante(iso)
    if q is None:
        return ""
    return q.strftime("%H:%M") if q.date() == agora.astimezone(q.tzinfo).date() else q.strftime("%d/%m %H:%M")


def _mwp(ficha: dict) -> str:
    x = CU.mwp(ficha.get("potencia_contratual"))
    return f"{x:.1f}".replace(".", ",") + " MWp" if x else ""


def _codigo(oc: dict, ficha: dict) -> str:
    """O código curto da usina (o `cod` do Andamento, "APR100"); sem ele, o do cadastro sem o prefixo do cliente."""
    cod = str(oc.get("usina_cod") or "").strip()
    if cod:
        return cod
    return str(ficha.get("codigo") or "").strip().split("-")[-1]


def _cartao(uid: str, ocs: list[dict], nome: str, ficha: dict, agora: datetime) -> dict:
    itens = []
    for o in ocs:
        abriu = AND.instante(o.get("abertura"))
        minutos = int((agora - abriu).total_seconds() // 60) if abriu else 0
        itens.append((_GRAVIDADE[grupo(o)], -minutos, o, minutos))
    itens.sort(key=lambda x: (x[0], x[1]))
    _g, _m, o, minutos = itens[0]
    falha = str(o.get("falha") or "").strip() or CU.motivo(o)
    equip = [str(e) for e in (o.get("equipamentos") or []) if str(e).strip() and str(e) not in falha]
    nota = o.get("ultima_nota") or None
    os_ = str(o.get("os") or "")
    etapa = str(o.get("etapa") or "").strip()
    return {"uid": uid, "grupo": grupo(o), "codigo": _codigo(o, ficha), "nome": nome, "mwp": _mwp(ficha),
            "falha": " · ".join([falha] + equip), "minutos": minutos, "dur": duracao(minutos),
            "nota": f"{_hora(nota.get('quando'), agora)} · {nota.get('texto')}".strip(" ·") if nota and nota.get("texto") else "",
            "os": f"OS {os_}" if os_.isdigit() else "ainda sem OS", "etapa": etapa, "etapa_tom": tom_da_etapa(etapa),
            "mais": len(ocs) - 1}


def montar(cos: dict | None, uids, nome_de, ficha_de, agora: datetime) -> dict:
    """O painel: {"ligada", "leitura" ("HH:MM" da fotografia mais velha), "kpis" [{"id", "rotulo", "n", "tom"}], "grupos"
    [{"id", "nome", "tom", "cartoes"}] (só os que têm cartão), "rodape" {"sem_ocorrencia", "sem_leitura"}}. `cos` =
    {"ocs": {usina_id: [ocorrências]}, "lidas", "leitura"} (None = o COS não respondeu); `uids` = as usinas do mapa (as
    de fora, sem coordenada, ficam de fora do painel também, para os números baterem com o mapa)."""
    if cos is None:
        return {"ligada": False, "leitura": "", "kpis": [], "grupos": [], "rodape": {}}
    ocs = {str(k): v for k, v in (cos.get("ocs") or {}).items() if v}
    lidas = {str(x) for x in cos.get("lidas") or ()}
    uids = [str(u) for u in uids]
    cartoes = [_cartao(u, ocs[u], nome_de(u), ficha_de(u) or {}, agora) for u in uids if u in lidas and u in ocs]
    por_grupo = {g[0]: sorted((c for c in cartoes if c["grupo"] == g[0]), key=lambda c: -c["minutos"]) for g in GRUPOS}
    kpis = [{"id": "abertas", "rotulo": "Abertas", "n": len(cartoes), "tom": ""}]
    kpis += [{"id": gid, "rotulo": curto, "n": len(por_grupo[gid]), "tom": tom} for gid, _n, curto, tom in GRUPOS]
    return {"ligada": True, "leitura": str(cos.get("leitura") or ""), "kpis": kpis,
            "grupos": [{"id": gid, "nome": nome, "tom": tom, "cartoes": por_grupo[gid]}
                       for gid, nome, _c, tom in GRUPOS if por_grupo[gid]],
            "rodape": {"sem_ocorrencia": sum(1 for u in uids if u in lidas and u not in ocs),
                       "sem_leitura": sum(1 for u in uids if u not in lidas)}}
