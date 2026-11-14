"""Mapa de equipe: os eventos do dia de cada técnico, a partir dos pontos (10/11/2026).

Pedido do Levi pela sessão Nexus Field, com a imagem do quadro de eventos do COS ("COS · Timeline, Eventos do dia"):
"Quero que apareça tipo ocorrências: Algo nesse estilo". Uma linha por evento, do mais novo ao mais velho, com a hora,
o técnico, o que aconteceu e a etiqueta colorida.

**Nenhuma régua nova:** a usina é o raio de 1 km (`RAIO_USINA_KM`); a saída da usina é o ÚLTIMO ponto nela e a chegada o
1º ponto na outra (a mesma regra de `deslocamentos.py`); "sem sinal" é `SEM_SINAL_MIN` sem ponto; e andando ou parado é o
que o próprio celular diz (`mov`). Os eventos:
- `inicio`: a primeira posição do dia (na usina, na cidade ou "fora de usina");
- `saiu`: saiu da usina, ou saiu do lugar do início do dia fora de usina (o 1º ponto andando depois dele). **Sem dado não
  se inventa:** "saiu de casa" seria dedução (pode ser o hotel); o texto é "saiu de <cidade>". A parada no meio do
  caminho, fora de usina, não vira evento: ela está no percurso;
- `chegou`: chegou na usina, com a duração desde a última saída do dia;
- `sem_sinal`: na hora em que virou sem sinal (o último ponto + 30 min), dizendo desde quando; não entra com o sem
  permissão, que já explica o silêncio;
- `sem_permissao`: na hora em que o celular avisou, se foi hoje.

**O destino (10/11/2026, Levi: "Pode subir o destino do técnico"):** `programa` = os blocos de HOJE da programação do PCM
da equipe do técnico (o `banco_dados.json` do App, o mesmo das telas do PCM; montado em `equipe_tela._programa_do_dia`).
Na saída, o destino é o próximo bloco que ainda não foi feito numa usina diferente da que ele deixa; a chegada prevista é
a régua do MOTOR DO PCM (`VELOCIDADE_KMH` e `FATOR_ROTA`, cópia do `TRAVEL_KMH` e do `TRAVEL_FACTOR` do
`pcm/motor/programacao_v7.py`, conferida no teste): a distância em linha reta do ponto da saída até a usina / 70 km/h x
1,2. A chegada diz a hora programada da usina. Sem programação, sem destino (nada inventado); a usina do bloco sem
coordenada vai pelo nome, sem a chegada prevista.

**O percurso contado por usina (11/11/2026, `do_percurso`).** Levi: "O percurso do técnico deve ser mais generalista
por exemplo 'Chegou na UFV X', 'Saiu da Usina X', 'Chegou na UFV X'". A lista do Ver percurso usa a MESMA regra destes
eventos, num período qualquer (não só hoje) e sem o destino nem o sem sinal: a primeira posição, a saída (da usina, com o
tempo que ficou nela quando a chegada está no período; ou do lugar do início fora de usina), a chegada (com o tempo de
deslocamento desde a última saída), cada parada fora de usina no caminho (com a cidade e o intervalo: os pontos parados
seguidos, a mesma junção da lista de antes) e, se o período termina andando, a última posição. O trecho andando fica
implícito entre a saída e a chegada. O nome da usina ganha "UFV" na frente quando não diz UFV nem Usina ("Entrou na UFV
Altair"). Desde 13/11/2026 a lista é uma linha do tempo curta: Entrou, Saiu, Voltou (ver `do_percurso`).

**O formato serve a outra tela** (o videowall do COS, se um dia quiser): cada evento é um dict com `instante` (UTC, com
Z), `hora` (Brasília), `pessoa_id`, `tipo`, `texto`, `rotulo`, `tom`, `usina_id`, `destino_usina_id`, `destino` (o
nome) e `chegada_prevista` (UTC, com Z; os três só na saída com destino). Nenhuma coordenada sai daqui: a cidade
vem pronta de quem chama (`cidade(lat, lon) -> nome | None`, a malha do IBGE no disco).
"""
from datetime import datetime, timedelta, timezone

from nexus.campo.equipe import RAIO_USINA_KM, SEM_SINAL_MIN
from nexus.campo.equipe.deslocamentos import _usina_do_ponto, haversine_km

_BRT = timezone(timedelta(hours=-3))
_UTC = "%Y-%m-%dT%H:%M:%SZ"
# a régua do deslocamento do motor do PCM (TRAVEL_KMH e TRAVEL_FACTOR de pcm/motor/programacao_v7.py): uma régua só
VELOCIDADE_KMH = 70.0
FATOR_ROTA = 1.2
# tipo -> (etiqueta, tom); o tom é o da situação no mapa (deslocamento = info, na usina = ok, ...)
TIPOS = {"inicio": ("Início do dia", "neutro"), "saiu": ("Deslocamento", "info"), "chegou": ("Na usina", "ok"),
         "sem_sinal": ("Sem sinal", "alerta"), "sem_permissao": ("Sem permissão", "critico")}
_RESUMO = (("saiu", "deslocamento", "deslocamentos"), ("chegou", "chegada", "chegadas"),
           ("inicio", "início do dia", "inícios do dia"), ("sem_sinal", "sem sinal", "sem sinal"),
           ("sem_permissao", "sem permissão", "sem permissão"))


def _inst(p) -> datetime:
    return datetime.strptime(p["instante"], _UTC).replace(tzinfo=timezone.utc)


def _tempo(minutos: int) -> str:
    m = max(0, int(minutos))
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d}"


def _destino(programa, deixa):
    """O próximo bloco de hoje ainda não feito numa usina diferente da que o técnico deixa (`deixa`, ou None)."""
    for bloco in programa or ():
        if not bloco.get("feita") and (bloco.get("usina_id") is None or str(bloco["usina_id"]) != str(deixa)):
            return bloco
    return None


def do_tecnico(pessoa_id, pontos: list, usinas: dict, nomes_usina: dict, agora: datetime, *, estado=None,
               cidade=None, programa=None) -> list:
    """Os eventos de hoje (Brasília) de um técnico, na ordem em que aconteceram. `pontos` com instante, lat, lon e mov
    (o diário); `usinas` = {usina_id: (lat, lon, uf)}; `estado` = o `Servico.estado_de` (a permissão e desde quando);
    `programa` = os blocos de hoje da equipe dele, na ordem da hora ({usina_id, usina, h_ini, feita})."""
    estado = estado or {}
    hoje = agora.astimezone(_BRT).date()
    lista = sorted((p for p in pontos if _inst(p).astimezone(_BRT).date() == hoje), key=lambda p: p["instante"])
    out = []

    def nome(u):
        return nomes_usina.get(u) or f"usina {u}"

    def evento(tipo, inst: datetime, texto, usina=None, destino=None, prevista=None, nome_destino=None):
        rotulo, tom = TIPOS[tipo]
        out.append({"instante": inst.astimezone(timezone.utc).strftime(_UTC), "hora": f"{inst.astimezone(_BRT):%H:%M}",
                    "pessoa_id": pessoa_id, "tipo": tipo, "texto": texto, "rotulo": rotulo, "tom": tom,
                    "usina_id": usina, "destino_usina_id": destino, "destino": nome_destino,
                    "chegada_prevista": prevista.astimezone(timezone.utc).strftime(_UTC) if prevista else None})

    def saida(p, texto, deixa=None):
        """A saída do ponto `p`, com o destino da programação e a chegada prevista pela régua do PCM."""
        bloco = _destino(programa, deixa)
        if bloco is None:
            evento("saiu", _inst(p), texto, deixa)
            return
        uid = bloco.get("usina_id")
        alvo = nomes_usina.get(uid) or bloco.get("usina") or f"usina {uid}"
        texto, prevista = f"{texto} para {alvo}", None
        if uid is not None and uid in usinas:
            km = haversine_km(p["lat"], p["lon"], usinas[uid][0], usinas[uid][1])
            prevista = _inst(p) + timedelta(hours=km / VELOCIDADE_KMH * FATOR_ROTA)
            texto += f"; chegada prevista {prevista.astimezone(_BRT):%H:%M}"
        evento("saiu", _inst(p), texto, deixa, uid, prevista, alvo)

    def programada(u):
        bloco = next((b for b in programa or () if str(b.get("usina_id")) == str(u)), None)
        return f"; programada às {bloco['h_ini']}" if bloco and bloco.get("h_ini") else ""

    if lista:
        lugares = [_usina_do_ponto(p, usinas, RAIO_USINA_KM) for p in lista]
        primeiro, u0 = lista[0], lugares[0]
        cid = None
        if u0 is None and cidade is not None:
            try:
                cid = cidade(primeiro["lat"], primeiro["lon"])
            except Exception:       # noqa: BLE001 — a cidade é enfeite: sem ela, "fora de usina"
                cid = None
        onde = f"na {nome(u0)}" if u0 is not None else (f"em {cid}" if cid else "fora de usina")
        evento("inicio", _inst(primeiro), f"primeira posição do dia, {onde}", u0)
        partida = None                      # o instante da última saída, para a duração da chegada
        # ainda no lugar do início do dia, fora de usina: os pontos PARADOS do começo. Quem começa andando não tem esse
        # lugar, e depois do 1º ponto andando ele ficou para trás (a parada no caminho não é ele)
        no_inicio = u0 is None and not primeiro.get("mov")
        for a, b, ua, ub in zip(lista, lista[1:], lugares, lugares[1:]):
            if no_inicio and ua is None and b.get("mov"):
                saida(a, f"saiu de {cid}" if cid else "saiu de um ponto fora de usina")
                partida = _inst(a)
            if ua is not None and ub != ua:
                saida(a, f"saiu da {nome(ua)}", ua)
                partida = _inst(a)
            if ub is not None and ub != ua:
                texto = f"chegou na {nome(ub)}"
                if partida is not None:
                    texto += f", depois de {_tempo(round((_inst(b) - partida).total_seconds() / 60))} de deslocamento"
                evento("chegou", _inst(b), texto + programada(ub), ub)
                partida = None
            if b.get("mov") or ub is not None:
                no_inicio = False
        ultimo = _inst(lista[-1])
        if estado.get("permissao") != "sem" and agora - ultimo >= timedelta(minutes=SEM_SINAL_MIN):
            evento("sem_sinal", ultimo + timedelta(minutes=SEM_SINAL_MIN),
                   f"sem sinal desde {ultimo.astimezone(_BRT):%H:%M}")
    desde = estado.get("desde")
    if estado.get("permissao") == "sem" and isinstance(desde, datetime) and desde.astimezone(_BRT).date() == hoje:
        evento("sem_permissao", desde, "sem permissão no celular")
    return sorted(out, key=lambda e: e["instante"])


def da_equipe(pontos_por_pessoa: dict, usinas: dict, nomes_usina: dict, agora: datetime, *, estados=None,
              cidade=None, programas=None) -> list:
    """Os eventos de hoje de todos, do MAIS NOVO ao mais velho (o quadro do COS). No mesmo instante, o que aconteceu
    depois vem antes (a saída antes do início do dia, do mesmo ponto). `programas` = {pessoa_id: blocos de hoje}."""
    estados, programas = estados or {}, programas or {}
    todos = []
    for pid, pontos in pontos_por_pessoa.items():
        todos += do_tecnico(pid, pontos, usinas, nomes_usina, agora, estado=estados.get(pid), cidade=cidade,
                            programa=programas.get(pid))
    ordem = list(enumerate(todos))
    ordem.sort(key=lambda x: (x[1]["instante"], x[0]), reverse=True)
    return [e for _i, e in ordem]


def _ufv(nome) -> str:
    """O nome da usina no texto do percurso: "UFV Altair"; o nome que já diz UFV ou Usina fica como está."""
    n = " ".join(str(nome or "").split())
    return n if n.lower().startswith(("ufv", "usina")) else f"UFV {n}"


def do_percurso(pontos: list, usinas: dict, nomes_usina: dict, *, cidade=None, com_ponto=False) -> list:
    """O percurso de um período contado por usina e por cidade: [{"tipo" (inicio, saiu, chegou, cidade, parado, ultimo),
    "de", "ate" (a hora de Brasília; "dd/mm HH:MM" se o período passa de um dia; iguais num ponto só), "texto" (a frase
    curta, a do marco no mapa), "acao", "lugar", "detalhe" (o tempo, curto), "repete" (o lugar é o da linha de cima: a
    lista não o repete), "usina_id"}], na ordem. `pontos` com instante, lat, lon e mov (a trilha do `Servico.percurso`); `usinas` = {usina_id:
    (lat, lon, uf)}; `cidade(lat, lon) -> nome | None`. `com_ponto`: cada linha leva também `ponto`, o índice na lista em
    ordem do ponto do marco (o mapa de verdade põe a coordenada dele).

    A usina (11/11/2026): a regra de `do_tecnico` (o raio de 1 km; a saída é o último ponto nela, a chegada o 1º na
    outra): "Entrou na UFV X" (detalhe "N de deslocamento"), "Saiu da UFV X" (detalhe "N na usina").
    Fora de usina (Levi, 12/11/2026: "Fica repetindo parado em guaratinguetá... deixa bem simples e direto, 'Em
    garatinguetá' se ele ficou o dia todo vai aparecer só isso o dia todo!"): as paradas seguidas na mesma cidade viram
    UMA linha "Em <cidade>", do primeiro ao último ponto dela; o andar entre elas não quebra a linha, e o começo e o fim
    do período andando entram nela quando o ponto é da mesma cidade (a cidade só se lê nos pontos parados e nas duas
    pontas). Parada sem cidade: "Parado fora de usina". O deslocamento da chegada conta da saída da usina anterior (ou
    do lugar do início), não da parada no caminho.
    A linha do tempo (Levi, 13/11/2026: "Tá com muito texto. Eu queria mais essa visão de linha do tempo mesmo [...]
    Entrou, saiu, voltou"): o texto é o que aconteceu e onde ("Entrou na UFV X", "Saiu da UFV X", "Voltou à UFV X" quando
    volta à usina de onde acabou de sair, "Começou"/"Terminou"), e o tempo vai num detalhe curto ("40 min de
    deslocamento", "1 h 30 na usina", "14 min fora")."""
    lista = sorted(pontos, key=lambda p: p["instante"])
    if not lista:
        return []
    fmt = "%d/%m %H:%M" if len({_inst(p).astimezone(_BRT).date() for p in lista}) > 1 else "%H:%M"
    n = len(lista)
    lugares = [_usina_do_ponto(p, usinas, RAIO_USINA_KM) for p in lista]
    cache = {}

    def cid(i):
        if i not in cache:
            try:
                cache[i] = cidade(lista[i]["lat"], lista[i]["lon"]) if cidade is not None else None
            except Exception:       # noqa: BLE001 — a cidade é enfeite: sem ela, "fora de usina"
                cache[i] = None
        return cache[i]

    def nome(u) -> str:
        return _ufv(nomes_usina.get(u) or f"usina {u}")

    def minutos(a, b) -> str:
        return _tempo(round((_inst(lista[b]) - _inst(lista[a])).total_seconds() / 60))

    out = []
    # a preposição de cada ação na frase do marco ("Entrou na", "Saiu da", "Voltou à"; a usina tem o nome com UFV/Usina)
    _PREP = {"Entrou": "na", "Saiu": "da", "Voltou": "à", "Começou": "na", "Em": "", "Parado": "", "Terminou": ""}

    def item(tipo, a, b, acao, lugar, detalhe="", usina=None):
        prep = _PREP.get(acao, "") if usina is not None else ""
        texto = " ".join(x for x in (acao, prep, lugar) if x)
        linha = {"tipo": tipo, "de": _inst(lista[a]).astimezone(_BRT).strftime(fmt),
                 "ate": _inst(lista[b]).astimezone(_BRT).strftime(fmt), "texto": texto, "acao": acao, "lugar": lugar,
                 "detalhe": detalhe, "repete": bool(out) and usina is not None and out[-1]["usina_id"] == usina,
                 "usina_id": usina}
        if com_ponto:
            linha["ponto"] = a
        out.append(linha)

    # as estadas: os pontos seguidos na mesma usina, e os de fora de usina entre elas
    estadas, k = [], 0
    while k < n:
        f = k
        while f + 1 < n and lugares[f + 1] == lugares[k]:
            f += 1
        estadas.append((lugares[k], k, f))
        k = f + 1
    partida = None              # o índice do ponto da última saída (a da usina, ou a do lugar do início)
    saiu_de = None              # a usina da última saída: chegar de novo nela é "Voltou"
    for e, (u, a, b) in enumerate(estadas):
        primeira, ultima = e == 0, e == len(estadas) - 1
        if u is not None:
            if primeira and not (a == b and not ultima):
                item("inicio", a, a, "Começou", nome(u), usina=u)
            elif not primeira:
                volta = saiu_de == u
                fora = minutos(partida, a) if partida is not None else ""
                detalhe = (f"{fora} fora" if volta else f"{fora} de deslocamento") if fora else ""
                item("chegou", a, a, "Voltou" if volta else "Entrou", nome(u), detalhe, u)
            if not ultima:
                item("saiu", b, b, "Saiu", nome(u), "" if primeira else f"{minutos(a, b)} na usina", u)
                partida, saiu_de = b, u
            continue
        # fora de usina: os grupos pela cidade dos pontos parados (o andar entre eles fica no grupo)
        grupos = []                 # [cidade, primeiro, último]
        for i in range(a, b + 1):
            if lista[i].get("mov"):
                continue
            c = cid(i)
            if grupos and grupos[-1][0] == c:
                grupos[-1][2] = i
            else:
                grupos.append([c, i, i])
        if primeira and (not grupos or grupos[0][1] > a):
            # o período começa andando: entra no 1º grupo se o ponto é da mesma cidade
            if grupos and grupos[0][0] is not None and cid(a) == grupos[0][0]:
                grupos[0][1] = a
            else:
                item("inicio", a, a, "Começou", "em deslocamento")
        fim_andando = ultima and (not grupos or grupos[-1][2] < b)
        if fim_andando and grupos and grupos[-1][0] is not None and cid(b) == grupos[-1][0]:
            grupos[-1][2] = b
            fim_andando = False
        for c, ga, gb in grupos:
            item("cidade" if c else "parado", ga, gb, "Em" if c else "Parado", c or "fora de usina")
        if primeira and grupos:
            partida = grupos[0][2]
        if fim_andando and not (primeira and a == b and not grupos):
            item("ultimo", b, b, "Terminou", "em deslocamento")
    return out


def resumo(eventos: list) -> str:
    """"2 deslocamentos · 1 chegada · 3 inícios do dia": o que houve, sem o que não houve."""
    partes = []
    for tipo, um, varios in _RESUMO:
        n = sum(1 for e in eventos if e["tipo"] == tipo)
        if n:
            partes.append(f"{n} {um if n == 1 else varios}")
    return " · ".join(partes)
