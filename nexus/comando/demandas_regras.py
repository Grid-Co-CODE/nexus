"""A regra das demandas entre setores (12/11/2026), sem Flask e sem banco: o prazo em dias úteis, a situação de cada
demanda pelos passos dela e os avisos do sininho. A gravação e a leitura moram em `demandas.py`; o desenho, em
docs/superpowers/specs/2026-11-12-demandas-entre-setores-design.md.

As regras do Levi (11-12/11/2026):
- o prazo é o do tema do setor, em dias úteis (sem sábado, domingo e feriado nacional), contado da abertura ou da última
  devolução;
- "Pedir informação" pausa o prazo até quem pediu responder: os dias úteis parados somam ao prazo;
- Finalizada (respondida) sem o ok nem a devolução de quem pediu em 3 dias úteis vira Concluída sozinha (só na leitura: a
  linha do tempo diz "concluída sozinha", e nada se grava);
- a vencida avisa quem recebeu e todo o setor dele.
"""
from datetime import date, datetime, timedelta, timezone

from ..dados.calendario import nacionais_calculados

SITUACOES = {"nova": ("Nova", "info"), "em_analise": ("Em análise", "alerta"),
             "aguardando": ("Aguardando quem pediu", "neutro"), "finalizada": ("Finalizada", "ok"),
             "concluida": ("Concluída", "ok"), "devolvida": ("Devolvida", "critico")}
EVENTOS = ("em_analise", "pediu_informacao", "informou", "respondeu", "devolveu", "concluiu")
# as situações em que a demanda ainda espera quem recebeu: é nelas que o prazo corre e que ela vence
ABERTAS = ("nova", "em_analise", "devolvida")
CONCLUI_SOZINHA_DIAS = 3
_BRT = timezone(timedelta(hours=-3))
_FERIADOS: dict[int, set] = {}


def _feriado(d: date) -> bool:
    if d.year not in _FERIADOS:
        _FERIADOS[d.year] = set(nacionais_calculados(d.year))
    return d in _FERIADOS[d.year]


def dia_util(d: date) -> bool:
    return d.weekday() < 5 and not _feriado(d)


def somar_dias_uteis(inicio: date, n: int) -> date:
    """O n-ésimo dia útil depois de `inicio` (o dia de início não conta)."""
    d = inicio
    while n > 0:
        d += timedelta(days=1)
        if dia_util(d):
            n -= 1
    return d


def dias_uteis_entre(a: date, b: date) -> int:
    """Os dias úteis em (a, b]: 0 com b <= a. Negativo quando b < a (o vencido conta para trás)."""
    if b == a:
        return 0
    if b < a:
        return -dias_uteis_entre(b, a)
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        n += dia_util(d)
    return n


def dia_de(iso) -> date | None:
    """O dia de Brasília de um `registrado_em` (ISO em UTC, com Z)."""
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(_BRT).date()


def estado(demanda: dict, eventos: list[dict], prazo_dias: int, hoje: date) -> dict:
    """A situação de agora da demanda pelos passos dela (na ordem da gravação) e o prazo de agora. O prazo conta da
    abertura ou da última devolução; cada "pediu informação" até o "informou" seguinte empurra o prazo pelos dias úteis
    parados (com a pausa ainda aberta, até hoje)."""
    sit = "nova"
    base = dia_de(demanda.get("registrado_em")) or hoje
    pausa_de, parado, respondida_em = None, 0, None
    for e in eventos:
        ev, dia = e.get("evento"), dia_de(e.get("registrado_em")) or hoje
        if ev == "em_analise" and sit in ("nova", "devolvida"):
            sit = "em_analise"
        elif ev == "pediu_informacao" and sit in ABERTAS:
            sit, pausa_de = "aguardando", dia
        elif ev == "informou" and sit == "aguardando":
            sit = "em_analise"
            parado += dias_uteis_entre(pausa_de, dia) if pausa_de else 0
            pausa_de = None
        elif ev == "respondeu" and sit in ABERTAS + ("aguardando",):
            sit, respondida_em = "finalizada", dia
        elif ev == "devolveu" and sit == "finalizada":
            sit, base, parado, pausa_de = "devolvida", dia, 0, None
        elif ev == "concluiu" and sit == "finalizada":
            sit = "concluida"
    if sit == "aguardando" and pausa_de:
        parado += dias_uteis_entre(pausa_de, hoje)
    sozinha = False
    if sit == "finalizada" and respondida_em and dias_uteis_entre(respondida_em, hoje) >= CONCLUI_SOZINHA_DIAS:
        sit, sozinha = "concluida", True
    aberta = sit in ABERTAS or sit == "aguardando"
    prazo = somar_dias_uteis(base, int(prazo_dias or 0) + parado) if prazo_dias else None
    restantes = dias_uteis_entre(hoje, prazo) if prazo and aberta else None
    if prazo and aberta and prazo < hoje:
        restantes = -dias_uteis_entre(prazo, hoje) or -1
    vencida = bool(prazo and sit in ABERTAS and hoje > prazo)
    rot, tom = SITUACOES[sit]
    return {"situacao": sit, "rotulo": "Concluída sozinha" if sozinha else rot, "tom": tom, "prazo": prazo,
            "dias_restantes": restantes, "vencida": vencida, "pausada": sit == "aguardando", "sozinha": sozinha,
            "aberta": aberta, "respondida_em": respondida_em}


def selo_do_prazo(e: dict) -> tuple[str, str, str]:
    """O selo da linha: (linha 1, linha 2, tom)."""
    if e["situacao"] == "aguardando":
        return "Pausado", "aguarda", "neutro"
    if e["situacao"] == "finalizada":
        d = e.get("respondida_em")
        return "Respondida", d.strftime("%d/%m") if d else "", "neutro"
    if e["situacao"] == "concluida":
        return "Concluída", "", "neutro"
    r = e.get("dias_restantes")
    if r is None:
        return "Sem prazo", "", "neutro"
    if e["vencida"]:
        n = abs(r)
        return "Vencida", f"há {n} {'dia' if n == 1 else 'dias'}", "critico"
    if r == 0:
        return "Vence", "hoje", "critico"
    if r == 1:
        return "Falta", "1 dia", "alerta"
    return "Faltam", f"{r} dias", "ok"


def avisos(lista: list[dict], meu_hmac: str, meu_setor: int | None, hoje: date) -> list[dict]:
    """O que pede a ação da pessoa (o sininho): para quem recebe, a nova, o prazo apertando (faltam 2 dias, falta 1 dia,
    vence hoje), a vencida e a devolvida; para o setor de quem recebe, a vencida; para quem pediu, a respondida e o pedido
    de informação. Uma linha por demanda, a mais urgente primeiro."""
    out = []
    for d in lista:
        e = d["estado"]
        para_mim = bool(meu_hmac) and d.get("para_hmac") == meu_hmac
        pedi = bool(meu_hmac) and d.get("de_hmac") == meu_hmac
        do_setor = meu_setor is not None and d.get("para_setor_id") == meu_setor
        tipo = None
        if e["vencida"] and (para_mim or do_setor):
            tipo = "vencida"
        elif para_mim and e["situacao"] == "devolvida":
            tipo = "devolvida"
        # a pausada (aguardando quem pediu) não aperta quem recebeu: a vez é de quem pediu (revisão de 12/11/2026: o
        # pedido de informação no dia do prazo dava "Vence hoje" todo dia enquanto a linha dizia "Pausado")
        elif para_mim and e["aberta"] and e["situacao"] != "aguardando" and e["dias_restantes"] == 0:
            tipo = "vence_hoje"
        # a nova antes do prazo: a que acabou de chegar com 2 dias diz "Nova" (a prévia aprovada em 11/11/2026); a que
        # vence hoje já saiu acima
        elif para_mim and e["situacao"] == "nova":
            tipo = "nova"
        elif para_mim and e["aberta"] and e["situacao"] != "aguardando" and e["dias_restantes"] in (1, 2):
            tipo = "prazo"
        elif pedi and e["situacao"] == "finalizada":
            tipo = "respondida"
        elif pedi and e["situacao"] == "aguardando":
            tipo = "informacao"
        if tipo:
            out.append({"demanda_id": d["demanda_id"], "tipo": tipo, "tom": _TOM_AVISO[tipo],
                        "titulo_curto": d.get("titulo") or "", "de_nome": d.get("de_nome") or "",
                        "dias_restantes": e["dias_restantes"], "para_mim": para_mim, "pedi": pedi})
    ordem = {"vencida": 0, "vence_hoje": 1, "devolvida": 2, "prazo": 3, "nova": 4, "informacao": 5, "respondida": 6}
    out.sort(key=lambda a: ordem[a["tipo"]])
    return out


_TOM_AVISO = {"vencida": "critico", "vence_hoje": "critico", "devolvida": "critico", "prazo": "alerta", "nova": "info",
              "informacao": "alerta", "respondida": "ok"}
