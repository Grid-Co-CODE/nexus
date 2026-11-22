"""O novo da Sala de controle da Performance no sino do topo (16/11/2026).

Levi, ao aprovar a Sala: a ocorrência nova chega nas notificações de performance, agrupada POR USINA, e some quando a
pessoa abre. A regra do que é novo mora na plataforma (`sala_controle.novas_por_usina`: parou depois da 1ª vez que a
pessoa abriu a Sala, segue parado e ela ainda não abriu); aqui o Nexus só pergunta, pela ponte de leitura, o novo de
quem está na sessão (`/api/sala/novas?pessoa=<e-mail>`).

O sino nunca espera a plataforma: `do_sino` devolve a cópia que houver (até `VALIDADE_S`) e, vencida ou ausente, dispara a
leitura por trás. Na 1ª página depois de subir, ou da pessoa, não sai nada; na seguinte, sai. Falha vira "sem novidade"
(o sino nunca derruba uma página) e é tentada de novo só depois de `ESPERA_FALHA_S`.
"""
import threading
import time
from urllib.parse import urlencode

VALIDADE_S = 120
ESPERA_FALHA_S = 300
MAX_PESSOAS = 400               # teto da cópia (uma entrada por e-mail)
_COPIA = {}                     # e-mail -> {"t": monotonic, "dado": dict | None, "falhou": bool}
_EM_CURSO = set()
_TRAVA = threading.Lock()


def limpar() -> None:
    with _TRAVA:
        _COPIA.clear()
        _EM_CURSO.clear()


def ler(cfg, email) -> dict | None:
    """Pergunta à plataforma, pela ponte, o novo da pessoa. → {"total", "n_usinas", "usinas": [...], "desde"} ou None
    (ponte desligada, plataforma fora, resposta sem a marca da leitura)."""
    from . import ponte
    url, token = cfg.get("NEXUS_PLATAFORMA_URL"), cfg.get("NEXUS_PLATAFORMA_TOKEN")
    if not url or not token:
        return None
    r = ponte.enviar(**ponte.montar_pedido(url, token, "GET", "/api/sala/novas", [("pessoa", email)], None, None))
    ok = {str(k).lower(): v for k, v in r.headers.items()}.get("x-nexus-leitura-ok") == "1"
    if r.status_code != 200 or not ok:
        return None
    d = r.json()
    if not isinstance(d, dict) or not d.get("ok"):
        return None
    usinas = [{"usina": str(u.get("usina") or ""), "strings": int(u.get("strings") or 0), "inversores": int(u.get("inversores") or 0),
               "trackers": int(u.get("trackers") or 0), "inv": _lista(u.get("inv")), "trk": _lista(u.get("trk"))}
              for u in d.get("usinas") or [] if isinstance(u, dict) and u.get("usina")]
    return {"total": int(d.get("total") or 0), "n_usinas": int(d.get("n_usinas") or len(usinas)), "usinas": usinas,
            "desde": d.get("desde") or ""}


def _lista(v, teto=500) -> list:
    """Os nomes dos inversores ou trackers que a plataforma mandou, só texto (número vira texto; o resto sai)."""
    if not isinstance(v, list):
        return []
    return [str(x).strip()[:80] for x in v if isinstance(x, (str, int)) and not isinstance(x, bool) and str(x).strip()][:teto]


SALA = "/t/performance/sala-de-controle"
DESTINO_MAX = 1900               # a porta aceita destino de até 2048 letras (`porta.destino_permitido`); folga para o prefixo


def link(u) -> str:
    """O link do aviso de UMA usina: a Sala aberta nela e nos equipamentos citados (22/11/2026, Levi, com o print do sino:
    "quando eu abrir uma notificação da sala de controle tem que abrir exatamente na usina e nos equipamentos citados, se
    não, não serve"). Vai pelo `?p=` da moldura até `/painel/sala-de-controle?usina=&aba=&inv=&trk=`, que a Sala lê ao
    abrir (`irParaNovo` no `sala_controle.html` da plataforma). Lista que não cabe no limite da porta sai do link (os
    trackers primeiro, depois os inversores): a Sala, sem lista, aponta o novo da usina pela mesma regra. Sem usina, a Sala."""
    from . import porta
    nome = str((u or {}).get("usina") or "").strip()
    if not nome:
        return SALA
    base = [("usina", nome), ("aba", "str" if int(u.get("strings") or 0) or not u.get("trk") else "trk")]
    inv = [("inv", x) for x in _lista(u.get("inv"))]
    trk = [("trk", x) for x in _lista(u.get("trk"))]
    for extra in (inv + trk, inv, []):
        destino = "/painel/sala-de-controle?" + urlencode(base + extra)
        if len(destino) <= DESTINO_MAX and porta.destino_permitido(destino) == destino:
            return SALA + "?" + urlencode({"p": destino})
    return SALA


def _atualizar(cfg, email, leitor) -> None:
    dado, falhou = None, False
    try:
        dado = leitor(cfg, email)
        falhou = dado is None
    except Exception:            # noqa: BLE001 — a plataforma fora não é erro do sino
        falhou = True
    with _TRAVA:
        velho = _COPIA.get(email) or {}
        _COPIA[email] = {"t": time.monotonic(), "dado": dado if not falhou else velho.get("dado"), "falhou": falhou}
        _EM_CURSO.discard(email)
        if len(_COPIA) > MAX_PESSOAS:
            for k in sorted(_COPIA, key=lambda k: _COPIA[k]["t"])[:len(_COPIA) - MAX_PESSOAS]:
                _COPIA.pop(k, None)


def do_sino(cfg, email, leitor=ler, em_fundo=True) -> dict | None:
    """O novo da pessoa para o sino, SEM esperar a plataforma: a cópia que houver; vencida ou ausente, a leitura começa
    por trás (uma por pessoa de cada vez). `em_fundo=False` (os testes) lê na hora."""
    email = str(email or "").strip().lower()
    if "@" not in email or email.endswith(".invalid"):
        return None
    agora = time.monotonic()
    with _TRAVA:
        c = _COPIA.get(email)
        prazo = ESPERA_FALHA_S if (c and c["falhou"]) else VALIDADE_S
        vencida = c is None or agora - c["t"] > prazo
        dispara = vencida and email not in _EM_CURSO
        if dispara:
            _EM_CURSO.add(email)
    if dispara:
        if em_fundo:
            threading.Thread(target=_atualizar, args=(dict(cfg), email, leitor), daemon=True).start()
        else:
            _atualizar(cfg, email, leitor)
            with _TRAVA:
                c = _COPIA.get(email)
    return (c or {}).get("dado")
