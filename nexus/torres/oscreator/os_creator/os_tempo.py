"""os_tempo.py: as datas e os tempos do OS Creator.

A data do Fracttal (UTC) em Brasília (`fmt_data_br`), o tempo entre duas datas (`duracao_os`), as horas de sol (`horas_solares`,
`duracao_solar`), o segundo do Fracttal como número (`_segundos`) e o tempo da OS, que é a SOMA do tempo das tarefas dela
(`_tempo_da_os`, 30/10/2026). Nada aqui fala com o Fracttal nem guarda estado.

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

from datetime import datetime, timedelta, timezone


def _iso_z(dt: datetime) -> str:
    """datetime → ISO UTC com milissegundos e Z (formato que o web app envia)."""
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


_BR_TZ = timezone(timedelta(hours=-3))   # Brasília (UTC-3)


def fmt_data_br(iso, com_hora: bool = True) -> str:
    """Data que o Fracttal devolve em UTC (creation_date / event_date / date...) → string em horário
    de BRASÍLIA: 'DD/MM/YYYY HH:MM' (ou só 'DD/MM/YYYY'). Tolerante a vazio/curto/cru."""
    s = str(iso or "").strip()
    if not s:
        return "—"
    s2 = s.replace(" ", "T")[:19]
    try:
        dt = datetime.strptime(s2, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:                                           # só data (sem hora) → NÃO aplica fuso
            return datetime.strptime(s2[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return s                                   # formato inesperado → devolve cru
    dt = dt.replace(tzinfo=timezone.utc).astimezone(_BR_TZ)
    return dt.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


def duracao_os(ini, fim) -> str:
    """'1d 16h 20m' entre dois ISO (UTC). '' se faltar/for inválido/negativo."""
    def _p(x):
        s = str(x or "").strip().replace(" ", "T")[:19]
        try:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    a, b = _p(ini), _p(fim)
    if not a or not b:
        return ""
    secs = int((b - a).total_seconds())
    if secs < 0:
        return ""
    d, r = divmod(secs, 86400); h, r = divmod(r, 3600); m = r // 60
    out = []
    if d:
        out.append(f"{d}d")
    if h or d:
        out.append(f"{h}h")
    out.append(f"{m}m")
    return " ".join(out)


def _parse_iso(x):
    """ISO 'YYYY-MM-DD[ T]HH:MM[:SS]' → datetime (naive). None se inválido/vazio."""
    s = str(x or "").strip().replace(" ", "T")[:19]
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(s[:16], "%Y-%m-%dT%H:%M")
        except ValueError:
            return None


def horas_solares(ini, fim, h0=6, h1=18) -> float:
    """Horas dentro da janela solar [h0,h1] de cada dia, entre dois datetime. 0 se fim<=ini."""
    from datetime import time as _time
    if not ini or not fim or fim <= ini:
        return 0.0
    total = 0.0
    d = ini.date()
    while d <= fim.date():
        a = max(ini, datetime.combine(d, _time(h0)))
        b = min(fim, datetime.combine(d, _time(h1)))
        if b > a:
            total += (b - a).total_seconds() / 3600.0
        d += timedelta(days=1)
    return total


def duracao_solar(event_iso, fim_iso=None, h0=6, h1=18):
    """Tempo do problema em HORAS SOLARES (janela h0–h1) do evento até o fim; sem fim → até AGORA.
    → (horas: float|None, em_aberto: bool). None se a data do evento for inválida."""
    ini = api._parse_iso(event_iso)
    if not ini:
        return (None, False)
    fim = api._parse_iso(fim_iso)
    aberto = fim is None
    if fim is None:
        fim = datetime.now()
    return (round(api.horas_solares(ini, fim, h0, h1), 2), aberto)


def _segundos(v):
    """A duração do Fracttal (segundos) como int, ou None quando falta ou não é número."""
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _tempo_da_os(duracoes) -> int:
    """O tempo da OS = a SOMA do tempo das tarefas dela (o PCM, 30/10/2026: "agora criando do zero o tempo na OS continua
    10 min igual na Fila, só na tarefa que o tempo é o que a gente colocou"). O `_work_order_insert` punha os 600 s de
    sempre na OS, fosse qual fosse o tempo das tarefas. A tarefa sem tempo conhecido conta os 10 min com que nasce."""
    return sum(int(d) if d else api.DURACAO_OS_AVULSA for d in duracoes) or api.DURACAO_OS_AVULSA


import api  # noqa: E402 — no fim: o `api` importa este módulo
