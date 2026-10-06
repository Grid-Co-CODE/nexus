"""O checklist da ronda lido do Fracttal, para a visão de sujidade e vegetação (Levi, 05/10/2026: "Em rondas quero uma
visão focando em sujidade e vegetação, é importante!").

O livro de rondas que o App grava no banco não traz as respostas do checklist. Mas o App escreve, no texto da OS de
ronda no Fracttal (`note`), cada resposta como "Rótulo: valor" (`_nota_ronda_os` do function_app.py): "Sujidade dos
módulos: 2; Altura da vegetação: 3; Sujidade da vala de drenagem: Parcial; Piranômetro IPOA (...): Limpo; ...". As
listagens do REST trazem esse texto em lote (medido em 05/10):
- as rondas em verificação (status 2) já vêm na fila que a Aprovação de OS lê (`regras_app._FILA_CACHE`);
- as aprovadas (status 3) vêm da mesma listagem, da mais recente para trás, até passar do período.
Nada disso vai para o banco.

As aprovadas não mudam mais, então o que foi lido fica num arquivo da pasta de dados do Nexus (fora do git) e a
releitura só busca o que foi aprovado depois da última leitura completa (1 a 2 páginas). Antes (até 06/10/2026) cada
reinício e cada meia hora reliam ~30 páginas, tudo ou nada: no reinício das 10:09 de 06/10 o Fracttal recusou por
excesso de pedidos (429), a leitura inteira foi descartada e o histórico de Matões 200 mostrou "—" em OS aprovadas que
tinham a resposta no texto (15055: sujidade 2, vegetação 3, vala obstruída). Agora o que já veio fica, e a leitura que
cai continua de onde parou.

Escalas (as do App, `CHECKLIST_RONDA`): sujidade e vegetação de 1 a 5, comparadas com as fotos de referência; o App
alerta acima de 3 (`alerta_acima`).
"""
import json
import logging
import os
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone

from . import fracttal, regras_app

VALIDADE_S = 600             # as aprovadas novas, no máximo a cada 10 min (1 a 2 páginas)
ESPERA_APOS_ERRO_S = 300
DIAS_PARA_TRAS = 90          # o histórico da usina mostra os 90 dias do livro de rondas
MARGEM_DIAS = 3              # a aprovação em lote pode carimbar o fim antes da última leitura completa
GUARDA_DIAS = 120            # resposta mais velha que isso sai do arquivo
PAGINAS_MAX = 120
PAUSA_S = 0.5                # entre páginas: a cota do Fracttal é de 200 pedidos/min para a empresa toda
ALERTA_ACIMA = 3             # nível 4 e 5 pedem ação (App)
_APROVADAS = {"ts": 0.0, "resp": {}, "ate": "", "retomar": 0, "topo": "", "lendo": False, "erro": "", "erro_em": 0.0,
              "carregado": False}
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


def _arquivo():
    """O arquivo das respostas aprovadas, na pasta de dados do Nexus (fora do git). Teste sem pasta própria: só em
    memória (a pasta_dados recusa)."""
    from flask import current_app, has_app_context
    if not has_app_context():
        return None
    from ..cadastro.ligacoes import pasta_dados
    try:
        return pasta_dados(current_app.config) / "campo" / "rondas_aprovadas.json"
    except RuntimeError:
        return None


def _carregar():
    with _TRAVA:
        if _APROVADAS["carregado"]:
            return
        arq = _arquivo()
        if arq is None:
            return
        _APROVADAS["carregado"] = True
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        _APROVADAS.update(resp=d.get("resp") or {}, ate=d.get("ate") or "", retomar=int(d.get("retomar") or 0),
                          topo=d.get("topo") or "", ts=time.time() if d.get("ate") else 0.0)


def _gravar():
    arq = _arquivo()
    if arq is None:
        return
    a = _APROVADAS
    corpo = {"ate": a["ate"], "retomar": a["retomar"], "topo": a["topo"], "resp": a["resp"]}
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(corpo, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, arq)
    except OSError as e:
        logging.warning("rondas aprovadas: não gravei o arquivo (%s)", e)


def _rondas_de(linhas) -> dict:
    """{OS: (texto, dia do fim)} das OS de ronda de uma página."""
    return {str(w["wo_folio"]): (w.get("note") or w.get("task_note") or "", str(w.get("final_date") or "")[:10])
            for w in linhas or [] if str(w.get("description") or "").startswith("Ronda") and w.get("wo_folio")}


def _reler():
    """As OS de ronda aprovadas, da mais recente para trás. A primeira vez, até DIAS_PARA_TRAS (e, se cair no meio,
    continua da página em que parou); depois, só até a última leitura completa menos MARGEM_DIAS. O que cada página
    traz entra na hora: um 429 no meio não joga fora o que já veio."""
    _carregar()
    a = _APROVADAS
    hoje = datetime.now(timezone.utc).date()
    piso = (hoje - timedelta(days=DIAS_PARA_TRAS)).isoformat()
    if a["ate"]:
        piso = max(piso, (date.fromisoformat(a["ate"]) - timedelta(days=MARGEM_DIAS)).isoformat())
        inicio, topo = 0, ""
    else:
        inicio = a["retomar"]
        topo = a["topo"] if inicio else ""
    paginas = 0
    try:
        for _ in range(PAGINAS_MAX):
            if paginas:
                time.sleep(PAUSA_S)
            r = fracttal.ler(f"work_orders?id_status_work_order=3&limit=100&start={inicio}&sort=final_date:desc")
            pagina = (r.get("data") if isinstance(r, dict) else r) or []
            paginas += 1
            for os_, (nota, fim) in _rondas_de(pagina).items():
                a["resp"][os_] = {**ler_nota(nota), "fim": fim}
            datas = [str(w.get("final_date") or "")[:10] for w in pagina if w.get("final_date")]
            if datas and not topo:
                topo = max(datas)
            if len(pagina) < 100 or (datas and max(datas) < piso):
                break
            inicio += 100
            if not a["ate"]:
                a.update(retomar=max(0, inicio - 100), topo=topo)    # uma página antes: as novas empurram a lista
        a.update(ate=topo or a["ate"] or hoje.isoformat(), retomar=0, topo="", ts=time.time(), erro="", erro_em=0.0)
        logging.info("rondas aprovadas: %d página(s), %d respostas, completas até %s", paginas, len(a["resp"]), a["ate"])
    except Exception as e:      # noqa: BLE001 — 429 ou rede: fica o que já veio, e tenta de novo depois
        a.update(erro=str(e)[:160], erro_em=time.time())
        logging.warning("rondas aprovadas: leitura parou na página %d (%s); %d respostas guardadas", paginas,
                        str(e)[:120], len(a["resp"]))
    finally:
        corte = (hoje - timedelta(days=GUARDA_DIAS)).isoformat()
        a["resp"] = {k: v for k, v in a["resp"].items() if (v.get("fim") or corte) >= corte}
        _gravar()
        a["lendo"] = False


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
    """{número da OS: respostas} de todas as OS de ronda que o Nexus tem: as aprovadas (o arquivo e as releituras) e as
    em verificação (a fila da Aprovação), que valem por cima."""
    _carregar()
    out = {os_: {k: v for k, v in r.items() if k != "fim"} for os_, r in list(_APROVADAS["resp"].items())}
    out.update({os_: ler_nota(n) for os_, n in _notas_de(regras_app._FILA_CACHE.get("linhas")).items()})
    return out


def estado() -> dict:
    """lidas = a leitura das aprovadas já foi completa ao menos uma vez (até `ate`)."""
    return {"lendo": _APROVADAS["lendo"], "erro": _APROVADAS["erro"], "lidas": bool(_APROVADAS["ate"]),
            "ate": _APROVADAS["ate"], "n": len(_APROVADAS["resp"]),
            "fila": regras_app._FILA_CACHE.get("linhas") is not None}


def limpar():
    _APROVADAS.update(ts=0.0, resp={}, ate="", retomar=0, topo="", lendo=False, erro="", erro_em=0.0, carregado=False)
