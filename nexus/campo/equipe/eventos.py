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


def resumo(eventos: list) -> str:
    """"2 deslocamentos · 1 chegada · 3 inícios do dia": o que houve, sem o que não houve."""
    partes = []
    for tipo, um, varios in _RESUMO:
        n = sum(1 for e in eventos if e["tipo"] == tipo)
        if n:
            partes.append(f"{n} {um if n == 1 else varios}")
    return " · ".join(partes)
