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
               "trackers": int(u.get("trackers") or 0)} for u in d.get("usinas") or [] if isinstance(u, dict) and u.get("usina")]
    return {"total": int(d.get("total") or 0), "n_usinas": int(d.get("n_usinas") or len(usinas)), "usinas": usinas,
            "desde": d.get("desde") or ""}


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
