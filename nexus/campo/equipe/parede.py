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
from datetime import datetime, timedelta, timezone

from ...comando import usinas as CU
from . import situacao as SI
from ...cos import andamento as AND

# os grupos na ordem do painel (a do mockup: usina desligada, inversores, rede; depois comunicação e as outras):
# (id, título, rótulo curto do número de cima, tom)
GRUPOS = (("parada", "Usina parada", "Usina parada", "critico"),
          ("inversor", "Inversores desligados", "Inversor fora", "alerta"),
          ("rede", "Rede concessionária", "Rede", "critico"),
          ("com", "Sem comunicação", "Comunicação", "semcom"),      # o roxo de Comando > Usinas (12/11/2026)
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


# ── as três colunas (26/11/2026) ───────────────────────────────────────────────────────────────────────────────────────
# O Levi aprovou o protótipo do Mapa de equipe redesenhado ("ok sobe"), com a referência do COS (a sugestão 10, "Videowall
# do COS: ocorrências, mapa e timeline em três colunas") e os pedidos dele: à esquerda as usinas com problema agora e há
# quanto tempo; à direita os eventos de hoje focados nas ocorrências do COS, com o técnico só quando ele tem a ver com
# uma delas ("mostra informações, tipo assim, técnico na usina"). Nada se inventa: a hora da abertura e a da nota são as
# do COS; a do técnico, a do Nexus Field; sem a fotografia do COS, a linha do tempo fica vazia.
_BRT = timezone(timedelta(hours=-3))
NOME_DO_GRUPO = {g[0]: g[1] for g in GRUPOS}
# a contagem do mapa, nas palavras do Agora de Comando > Usinas (a mesma régua que pinta a usina), com o que cada cor
# engloba em poucas palavras (27/11/2026, Levi: "crítico engloba isso, a atenção engloba isso [...]"; e no mesmo dia, ao
# ver a legenda num bloco à parte: "unir o texto [...] com esse usinas, alarmes e equipes e tentar deixar o texto mais
# resumido, porque deixou o mapa pequeno"). É a régua de `comando.usinas.classificar`: mudou lá, muda aqui.
# (id, rótulo, o que engloba)
CONTAGEM = (("critico", "críticas", "usina desligada, rede ou religamento"),
            ("alerta", "em atenção", "inversor, tracker ou string"),
            ("semcom", "sem comunicação", "o COS não enxerga a usina"),
            ("ok", "normais", "sem ocorrência aberta"),
            ("neutro", "sem leitura", "o COS não trouxe a usina"))


def _hhmm(iso_utc) -> str:
    q = AND.instante(iso_utc)
    return q.astimezone(_BRT).strftime("%H:%M") if q else ""


def tecnicos_nas_usinas(linhas: list, eventos: list) -> dict:
    """{usina_id (texto): [{"nome", "tipo" (na_usina | a_caminho), "texto"}]}. Na usina = a situação do mapa (a última
    posição a até 1 km dela), desde a última chegada do dia (o primeiro ponto do dia já na usina também conta); a caminho
    = em deslocamento, com a última saída levando o destino da programação e a chegada prevista. `eventos` do mais novo
    ao mais velho (o `_eventos_do_dia` da tela)."""
    out: dict = {}
    for l in linhas:
        s, pid = l.get("s") or {}, l.get("pid")
        if s.get("chave") == "na_usina" and s.get("usina_perto"):
            uid = str(s["usina_perto"][0])
            ch = next((e for e in eventos if e.get("pessoa_id") == pid and e.get("tipo") in ("chegou", "inicio")
                       and str(e.get("usina_id")) == uid), None)
            texto = f"{l['nome']} na usina" + (f" desde {ch['hora']}" if ch else "")
            out.setdefault(uid, []).append({"nome": l["nome"], "tipo": "na_usina", "texto": texto})
        elif s.get("chave") == "deslocamento":
            saida = next((e for e in eventos if e.get("pessoa_id") == pid and e.get("tipo") == "saiu"), None)
            if saida and saida.get("destino_usina_id") is not None:
                chega = _hhmm(saida.get("chegada_prevista"))
                out.setdefault(str(saida["destino_usina_id"]), []).append(
                    {"nome": l["nome"], "tipo": "a_caminho", "texto": f"{l['nome']} a caminho" + (f", chega {chega}" if chega else "")})
    return out


TOM_DO_GRUPO = {g[0]: g[3] for g in GRUPOS}


def ocorrencias_recentes(cos: dict | None, uids, nome_de, ficha_de, tecnicos: dict, agora: datetime) -> list:
    """As ocorrências abertas do COS, da mais nova para a mais velha (27/11/2026, Levi: "mostrar as ocorrências atuais, as
    que aconteceram agora, as ocorrências mais recentes do COS, e aí mostrar se o técnico chegou, se ele está chegando, se
    ele está em deslocamento"): [{"uid", "usina", "codigo", "quando" (a abertura: "HH:MM" hoje, "dd/mm HH:MM" antes),
    "ha", "texto" (o grupo e a falha), "os", "nota" (a última nota do COS com a hora), "tom", "tecnicos"}]. O técnico é o
    de `tecnicos_nas_usinas` (na usina desde, ou a caminho com a chegada prevista); sem ninguém, a lista vazia (só quem tem
    o Nexus Field aparece: a tela diz isso, não "sem técnico"). Sem a fotografia do COS, nada."""
    if cos is None:
        return []
    ocs = {str(k): v for k, v in (cos.get("ocs") or {}).items() if v}
    lidas = {str(x) for x in cos.get("lidas") or ()}
    itens = []
    for uid in (str(u) for u in uids):
        if uid not in lidas or uid not in ocs:
            continue
        for o in ocs[uid]:
            abriu = AND.instante(o.get("abertura"))
            g = grupo(o)
            falha = str(o.get("falha") or "").strip() or CU.motivo(o)
            os_ = str(o.get("os") or "")
            nota = o.get("ultima_nota") or {}
            itens.append((abriu, {
                "uid": uid, "usina": nome_de(uid), "codigo": _codigo(o, ficha_de(uid) or {}),
                "quando": _hora(o.get("abertura"), agora) if abriu else "",
                "ha": duracao(int((agora - abriu).total_seconds() // 60)) if abriu else "",
                "texto": f"{NOME_DO_GRUPO[g]}: {falha}", "os": f"OS {os_}" if os_.isdigit() else "ainda sem OS",
                "nota": f"{_hora(nota.get('quando'), agora)} · {nota.get('texto')}".strip(" ·") if nota.get("texto") else "",
                "tom": TOM_DO_GRUPO[g], "tecnicos": list(tecnicos.get(uid) or [])}))
    # a mais nova primeiro; a sem abertura (não devia acontecer) vai para o fim
    itens.sort(key=lambda x: x[0].timestamp() if x[0] else float("-inf"), reverse=True)
    return [i for _a, i in itens]


def _no_brt(x):
    q = x if isinstance(x, datetime) else AND.instante(x)
    return q.astimezone(_BRT) if q else None


def visao_tecnicos(linhas: list, eventos: list, ocorrencia_de: dict, nome_de, agora: datetime) -> list:
    """A visão dos técnicos da coluna da direita (27/11/2026, Levi: "Visão técnico, visão ocorrências, do lado direito
    [...] para a gente ter essas duas opções"): [{"pid", "nome", "equipe", "quando", "texto" (onde está: a usina e desde
    quando, o destino e a chegada prevista, a cidade), "hora" (a última posição), "rotulo", "tom", "uid" (a usina dele,
    para o zoom), "oc" (a ocorrência aberta dessa usina, pelo grupo)}]. `ocorrencia_de` = {usina_id: o grupo da pior
    ocorrência aberta}.

    Uma lista só, do mais novo para o mais velho, com a hora na lateral como as ocorrências (27/11/2026, Levi: "incluísse
    na dos técnicos o horário lateral, que nem tem nas ocorrências [...] Tem que ser de acordo com o horário mesmo [...]
    Não separe por tema"). `quando` = o último acontecimento do dia do técnico: a chegada na usina em que está, a saída
    de quem está em deslocamento, e para os outros o evento mais novo (a saída da última usina, o início do dia); para
    quem está sem sinal, o último ponto (o mesmo do texto); sem evento hoje, a última posição ("dd/mm HH:MM" de outro
    dia); sem posição nenhuma, vai para o fim."""
    na = {it["nome"]: (uid, it) for uid, lst in tecnicos_nas_usinas(linhas, eventos).items() for it in lst
          if it["tipo"] == "na_usina"}
    indo = {d["nome"]: d for d in deslocamentos(linhas, eventos, nome_de)}
    hoje = agora.astimezone(_BRT).date()
    itens = []
    for l in linhas:
        s, pid = l.get("s") or {}, l.get("pid")
        ch, uid, texto = s.get("chave"), "", ""
        do_pid = [e for e in eventos if e.get("pessoa_id") == pid]
        ev = do_pid[0] if do_pid else None
        if ch == "na_usina" and l["nome"] in na:
            uid = na[l["nome"]][0]
            desde = na[l["nome"]][1]["texto"].rsplit(" desde ", 1)
            texto = (SI.com_prep("em", nome_de(uid)) if nome_de(uid) else "na usina") + (f" desde {desde[1]}" if len(desde) == 2 else "")
            ev = next((e for e in do_pid if e.get("tipo") in ("chegou", "inicio") and str(e.get("usina_id")) == uid), ev)
        elif ch == "deslocamento":
            d = indo.get(l["nome"]) or {}
            uid = d.get("uid") or ""
            texto = (f"para {d['para']}" + (f", chega {d['chega']}" if d.get("chega") else "")) if d.get("para")                 else "em deslocamento, sem destino programado"
            ev = next((e for e in do_pid if e.get("tipo") == "saiu"), ev)
        elif ch == "fora_usina":
            texto = " · ".join(x for x in (l.get("onde"), l.get("perto")) if x)
        elif ch == "sem_permissao":
            texto = "sem a localização no celular" + (f" desde {l['desde']}" if l.get("desde") else "")
        else:
            texto = " · ".join(x for x in ((f"última posição {l['hora']}" if l.get("hora") else ""), l.get("perto")) if x)
        if ch in ("sem_sinal", "sem_posicao"):
            # a marca do sinal perdido sai meia hora depois do último ponto: a hora que vale é a do último ponto, a mesma
            # do "última posição" do texto
            ev = None
        q = (_no_brt(ev.get("instante")) if ev else None) or _no_brt(s.get("ultima"))
        quando = "" if q is None else q.strftime("%H:%M") if q.date() == hoje else q.strftime("%d/%m %H:%M")
        itens.append((q, {"pid": pid, "nome": l["nome"], "equipe": l.get("equipe") or "", "quando": quando,
                          "texto": texto, "hora": l.get("hora") or "", "rotulo": s.get("rotulo") or "",
                          "tom": s.get("tom") or "neutro", "uid": uid, "oc": ocorrencia_de.get(uid, "") if uid else ""}))
    # o mais novo primeiro; quem não tem hora nenhuma vai para o fim (a ordem estável mantém a do painel, pelo nome)
    itens.sort(key=lambda x: x[0].timestamp() if x[0] else float("-inf"), reverse=True)
    return [i for _q, i in itens]


def contagem(agora_por_usina: dict) -> list:
    """[{"id", "n", "rotulo", "explica"}] das usinas do mapa por cor do Agora (crítico, atenção, sem comunicação, normal
    e sem leitura)."""
    n = {k: 0 for k, _r, _e in CONTAGEM}
    for a in (agora_por_usina or {}).values():
        if a and a.get("tom") in n:
            n[a["tom"]] += 1
    return [{"id": k, "n": n[k], "rotulo": r, "explica": e} for k, r, e in CONTAGEM]


def deslocamentos(linhas: list, eventos: list, nome_de) -> list:
    """[{"nome", "saiu", "uid", "para", "chega"}] de quem está em deslocamento agora, pela última saída do dia: a hora,
    o destino da programação (vazio quando não há) e a chegada prevista pela régua do PCM."""
    out = []
    for l in linhas:
        if (l.get("s") or {}).get("chave") != "deslocamento":
            continue
        saida = next((e for e in eventos if e.get("pessoa_id") == l.get("pid") and e.get("tipo") == "saiu"), None)
        uid = str(saida["destino_usina_id"]) if saida and saida.get("destino_usina_id") is not None else ""
        out.append({"nome": l["nome"], "saiu": saida["hora"] if saida else "", "uid": uid,
                    "para": (nome_de(uid) or "") if uid else "", "chega": _hhmm(saida.get("chegada_prevista")) if saida else ""})
    return out
