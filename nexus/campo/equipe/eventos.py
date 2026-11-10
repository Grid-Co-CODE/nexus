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
"Para <usina>" e "chegada prevista" ficam para quando houver o destino (a programação do PCM ou a OS).

**O formato serve a outra tela** (o videowall do COS, se um dia quiser): cada evento é um dict com `instante` (UTC, com
Z), `hora` (Brasília), `pessoa_id`, `tipo`, `texto`, `rotulo`, `tom` e `usina_id`. Nenhuma coordenada sai daqui: a cidade
vem pronta de quem chama (`cidade(lat, lon) -> nome | None`, a malha do IBGE no disco).
"""
from datetime import datetime, timedelta, timezone

from nexus.campo.equipe import RAIO_USINA_KM, SEM_SINAL_MIN
from nexus.campo.equipe.deslocamentos import _usina_do_ponto

_BRT = timezone(timedelta(hours=-3))
_UTC = "%Y-%m-%dT%H:%M:%SZ"
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


def do_tecnico(pessoa_id, pontos: list, usinas: dict, nomes_usina: dict, agora: datetime, *, estado=None,
               cidade=None) -> list:
    """Os eventos de hoje (Brasília) de um técnico, na ordem em que aconteceram. `pontos` com instante, lat, lon e mov
    (o diário); `usinas` = {usina_id: (lat, lon, uf)}; `estado` = o `Servico.estado_de` (a permissão e desde quando)."""
    estado = estado or {}
    hoje = agora.astimezone(_BRT).date()
    lista = sorted((p for p in pontos if _inst(p).astimezone(_BRT).date() == hoje), key=lambda p: p["instante"])
    out = []

    def nome(u):
        return nomes_usina.get(u) or f"usina {u}"

    def evento(tipo, inst: datetime, texto, usina=None):
        rotulo, tom = TIPOS[tipo]
        out.append({"instante": inst.astimezone(timezone.utc).strftime(_UTC), "hora": f"{inst.astimezone(_BRT):%H:%M}",
                    "pessoa_id": pessoa_id, "tipo": tipo, "texto": texto, "rotulo": rotulo, "tom": tom,
                    "usina_id": usina})

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
                evento("saiu", _inst(a), f"saiu de {cid}" if cid else "saiu de um ponto fora de usina")
                partida = _inst(a)
            if ua is not None and ub != ua:
                evento("saiu", _inst(a), f"saiu da {nome(ua)}", ua)
                partida = _inst(a)
            if ub is not None and ub != ua:
                texto = f"chegou na {nome(ub)}"
                if partida is not None:
                    texto += f", depois de {_tempo(round((_inst(b) - partida).total_seconds() / 60))} de deslocamento"
                evento("chegou", _inst(b), texto, ub)
                partida = None
            if b.get("mov") or ub is not None:
                no_inicio = False
        ultimo = _inst(lista[-1])
        if estado.get("permissao") != "sem" and agora - ultimo >= timedelta(minutes=SEM_SINAL_MIN):
            evento("sem_sinal", ultimo + timedelta(minutes=SEM_SINAL_MIN),
                   f"sem sinal desde {ultimo.astimezone(_BRT):%H:%M}")
    desde = estado.get("desde")
    if estado.get("permissao") == "sem" and isinstance(desde, datetime) and desde.astimezone(_BRT).date() == hoje:
        evento("sem_permissao", desde, "sem permissão de localização no celular")
    return sorted(out, key=lambda e: e["instante"])


def da_equipe(pontos_por_pessoa: dict, usinas: dict, nomes_usina: dict, agora: datetime, *, estados=None,
              cidade=None) -> list:
    """Os eventos de hoje de todos, do MAIS NOVO ao mais velho (o quadro do COS). No mesmo instante, o que aconteceu
    depois vem antes (a saída antes do início do dia, do mesmo ponto)."""
    estados = estados or {}
    todos = []
    for pid, pontos in pontos_por_pessoa.items():
        todos += do_tecnico(pid, pontos, usinas, nomes_usina, agora, estado=estados.get(pid), cidade=cidade)
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
