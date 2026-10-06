"""O checklist da ronda lido do Fracttal, para a visão de sujidade e vegetação (Levi, 05/10/2026: "Em rondas quero uma
visão focando em sujidade e vegetação, é importante!").

O livro de rondas que o App grava no banco não traz as respostas do checklist. Mas o App escreve, no texto da OS de
ronda no Fracttal (`note`), cada resposta como "Rótulo: valor" (`_nota_ronda_os` do function_app.py): "Sujidade dos
módulos: 2; Altura da vegetação: 3; Sujidade da vala de drenagem: Parcial; Piranômetro IPOA (...): Limpo; ...". As
listagens do REST trazem esse texto em lote (medido em 05/10):
- as rondas em verificação (status 2) já vêm na fila que a Aprovação de OS lê (`regras_app._FILA_CACHE`);
- as aprovadas (status 3) vêm da mesma listagem, da mais recente para trás, até passar do período: ~6 páginas por mês.
Nada disso vai para o banco. A releitura das aprovadas é em segundo plano, uma por vez, a cada 30 min no máximo.

Escalas (as do App, `CHECKLIST_RONDA`): sujidade e vegetação de 1 a 5, comparadas com as fotos de referência; o App
alerta acima de 3 (`alerta_acima`).
"""
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from . import fracttal, regras_app

VALIDADE_S = 1800            # as aprovadas de novo no máximo a cada 30 min
ESPERA_APOS_ERRO_S = 300
DIAS_PARA_TRAS = 45          # o maior período da tela (30 dias) + 15 para a leitura anterior (a seta): ~30 páginas
PAGINAS_MAX = 60
ALERTA_ACIMA = 3             # nível 4 e 5 pedem ação (App)
_APROVADAS = {"ts": 0.0, "notas": {}, "lendo": False, "erro": "", "erro_em": 0.0}
_TRAVA = threading.Lock()


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


# o rótulo do App -> a nossa chave (pelo começo do rótulo, sem acento: o texto do Fracttal pode vir com outra grafia)
CAMPOS = (("sujidade dos modulos", "sujidade"), ("altura da vegetacao", "vegetacao"),
          ("sujidade da vala", "vala"), ("sombreamento", "sombreamento"), ("dejeto", "dejeto"),
          ("piranometro ipoa", "ipoa"), ("albedometro", "albedo"), ("piranometro ghi", "ghi"))
SENSORES = {"ipoa": "IPOA", "albedo": "Albedômetro", "ghi": "GHI"}


def ler_nota(note) -> dict:
    """As respostas que interessam, do texto da OS de ronda. Nível que não é número de 1 a 5 = sem leitura."""
    s = str(note or "")
    if " — " in s:
        s = s.split(" — ", 1)[1]
    out = {}
    for parte in s.split("; "):
        rot, sep, val = parte.rpartition(": ")
        if not sep:
            continue
        r = _norm(rot)
        chave = next((k for prefixo, k in CAMPOS if r.startswith(prefixo)), None)
        if chave:
            out[chave] = val.strip()
    for k in ("sujidade", "vegetacao"):
        v = out.get(k, "")
        out[k] = int(v) if v.isdigit() and 1 <= int(v) <= 5 else None
    out["sensores_sujos"] = [SENSORES[k] for k in SENSORES if _norm(out.get(k)) == "sujo"]
    return out


def _notas_de(linhas) -> dict:
    return {str(w.get("wo_folio") or ""): w.get("note") or w.get("task_note") or ""
            for w in linhas or [] if str(w.get("description") or "").startswith("Ronda") and w.get("wo_folio")}


def _reler():
    """As OS de ronda aprovadas, da mais recente para trás, até passar de DIAS_PARA_TRAS."""
    try:
        piso = (datetime.now(timezone.utc) - timedelta(days=DIAS_PARA_TRAS)).strftime("%Y-%m-%d")
        notas, inicio = {}, 0
        for _ in range(PAGINAS_MAX):
            r = fracttal.ler(f"work_orders?id_status_work_order=3&limit=100&start={inicio}&sort=final_date:desc")
            pagina = (r.get("data") if isinstance(r, dict) else r) or []
            notas.update(_notas_de(pagina))
            datas = [str(w.get("final_date") or "")[:10] for w in pagina if w.get("final_date")]
            if len(pagina) < 100 or (datas and max(datas) < piso):
                break
            inicio += 100
        _APROVADAS.update(ts=time.time(), notas=notas, erro="", erro_em=0.0)
    except Exception as e:      # noqa: BLE001 — 429 ou rede: fica a leitura anterior, e tenta de novo depois
        _APROVADAS.update(erro=str(e)[:160], erro_em=time.time())
    finally:
        _APROVADAS["lendo"] = False


def em_segundo_plano(fn):
    """Numa thread; nos testes, na hora (o teste troca esta função)."""
    from flask import current_app, has_app_context
    if has_app_context() and current_app.config.get("TESTING"):
        fn()
        return
    threading.Thread(target=fn, daemon=True, name="nexus-ronda-checklist").start()


def pedir_releitura(app=None):
    if time.time() - _APROVADAS["ts"] < VALIDADE_S:
        return
    with _TRAVA:
        if _APROVADAS["lendo"] or time.time() - _APROVADAS["erro_em"] < ESPERA_APOS_ERRO_S:
            return
        _APROVADAS["lendo"] = True
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()

    def rodar():
        with app.app_context():
            _reler()
    em_segundo_plano(rodar)


def respostas() -> dict:
    """{número da OS: respostas} de todas as OS de ronda que o Nexus tem: as em verificação (a fila da Aprovação) e as
    aprovadas (lidas aqui)."""
    notas = dict(_APROVADAS["notas"])
    notas.update(_notas_de(regras_app._FILA_CACHE.get("linhas")))
    return {os_: ler_nota(n) for os_, n in notas.items()}


def estado() -> dict:
    return {"lendo": _APROVADAS["lendo"], "erro": _APROVADAS["erro"], "lidas": bool(_APROVADAS["ts"]),
            "fila": regras_app._FILA_CACHE.get("linhas") is not None}


def limpar():
    _APROVADAS.update(ts=0.0, notas={}, lendo=False, erro="", erro_em=0.0)
