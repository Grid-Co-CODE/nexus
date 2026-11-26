"""As PTs esperando o De acordo de quem entrou, no sino do topo (26/11/2026).

Levi, 26/11/2026: "além de receber o e-mail, ele também tem que receber notificação no Nexus"; "a notificação do Nexus pode
subir". O sino mostra as linhas de PT que a pessoa do login pode decidir agora (`decisao_pt.assinaveis`, a mesma lista do
"Outras PTs esperando nas suas usinas" do card de assinar): as usinas em que ela é o Responsável UFV, o Supervisor de
Campo da região (ou o Coordenador, com a vaga aberta) ou o gestor de contrato; o COS, todas, mas só no plantão. O
administrador não recebe todas por ser administrador (seriam dezenas): recebe as do papel dele, como qualquer um.

O sino roda em toda página, e a conta de quem pode decidir decifra o cadastro (uma vez por linha de PT). Por isso a lista
de cada pessoa fica numa cópia de 90 s, na memória, e a conta vencida se refaz POR TRÁS (a página mostra a cópia velha ou
nada, nunca espera). Nos testes (`TESTING`) a conta é na hora."""
from __future__ import annotations

import threading
import time
from urllib.parse import quote

from flask import current_app

TTL_S = 90
_CACHE: dict = {}          # e-mail -> {"em": time.time(), "itens": [...]}
_RODANDO: dict = {}        # e-mail -> a thread da conta


def limpar() -> None:
    _CACHE.clear()


def _espera(m) -> str:
    """O tempo de espera curto do sino ("40 min", "3 h 5 min", "2 d 4 h"), como o chip da APR e PT."""
    if m is None:
        return ""
    m = int(m)
    if m < 60:
        return f"{m} min"
    if m < 24 * 60:
        return f"{m // 60} h" + (f" {m % 60} min" if m % 60 else "")
    return f"{m // 1440} d" + (f" {(m % 1440) // 60} h" if (m % 1440) // 60 else "")


def _calcular(email: str, nome: str) -> list[dict]:
    from . import decisao_pt as DP
    from . import visao
    leitura = visao.pts()
    if leitura.erro:
        return []
    out = []
    for p in DP.assinaveis((leitura.dados or {}).get("aguardando") or [], email, nome, admin=False):
        numero, codigo = str(p.get("numero") or ""), str(p.get("codigo") or "")
        out.append({"numero": numero, "codigo": codigo, "os": str(p.get("os") or ""),
                    "usina": p.get("usina") or "", "ativo": p.get("ativo") or p.get("codigo") or "",
                    "idade_min": p.get("idade_min"), "espera": _espera(p.get("idade_min")), "parada": bool(p.get("parada")),
                    "link": f"/t/campo/pt/{quote(numero, safe='')}/assinar"
                            + (f"?ativo={quote(codigo, safe='')}" if codigo else "")})
    return out


def _por_tras(email: str, nome: str) -> None:
    t = _RODANDO.get(email)
    if t is not None and t.is_alive():
        return
    app = current_app._get_current_object()

    def rodar():
        with app.app_context():
            try:
                _CACHE[email] = {"em": time.time(), "itens": _calcular(email, nome)}
            except Exception:    # noqa: BLE001 — o sino só não mostra as PTs desta vez
                app.logger.exception("PTs do sino")
    t = threading.Thread(target=rodar, name="nexus-pt-sino", daemon=True)
    _RODANDO[email] = t
    t.start()


def para_o_sino(email: str, nome: str = "") -> list[dict] | None:
    """As PTs que esta pessoa pode assinar, da mais antiga para a mais nova; None = ainda não sei (sem cópia)."""
    email = (email or "").strip().lower()
    if not email:
        return None
    g = _CACHE.get(email)
    if current_app.config.get("TESTING"):
        if not g or time.time() - g["em"] >= TTL_S:
            g = _CACHE[email] = {"em": time.time(), "itens": _calcular(email, nome)}
        return g["itens"]
    if not g or time.time() - g["em"] >= TTL_S:
        _por_tras(email, nome)
    return g["itens"] if g else None
