"""As OS da equipe de Performance, para o Quadro da equipe da torre Performance (Levi, 04/11/2026: "Quero que clone o
quadro de equipe da engenharia para o time de performance com as pessoas da performance!"; "tira do BASE > ACESSOS >
PESSOAS E SETORES").

O clone do Quadro da equipe da Engenharia (`nexus/engenharia/os_equipe.py`): a mesma leitura do Fracttal (o REST filtra
pelo nome do responsável, as linhas são conferidas pelo `id_personnel`), as mesmas colunas e o mesmo cartão. Muda quem é
da equipe: aqui são as pessoas do setor Performance em Base → Acessos → Pessoas e setores (livro `nexus_setores`, a
última decisão de cada pessoa do Fracttal), não uma lista no .env. A decisão já guarda o id do Fracttal da pessoa, então
ela vira a pessoa do Fracttal pelo id, sem casar nome (homônimo não confunde).

O estado é deste quadro (a cópia, a releitura por trás e o "pronto antes de abrir"), separado do da Engenharia: um não
espera nem apaga a leitura do outro. Nada vai para o banco.
"""
import json
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

from ..cadastro import setor_ids as SID
from ..engenharia import os_equipe as OE
from ..texto import sem_acento as _norm

SETOR = SID.PERFORMANCE         # o setor_id em Base → Acessos (pelo ID: renomear o setor não esvazia o quadro)
VALIDADE_S = OE.VALIDADE_S
FORCAR_S = OE.FORCAR_S
PESSOAS_S = OE.PESSOAS_S
USO_S = OE.USO_S
QUENTE_S = OE.QUENTE_S
COLUNAS = OE.COLUNAS
_EST = {"ts": 0.0, "pessoas_ts": 0.0, "pessoas": [], "os": [], "lendo": False, "erro": "", "erro_em": 0.0, "faltam": [],
        "usado": 0.0, "equipe": []}
_TRAVA = threading.Lock()


def ids_do_setor(setores: dict) -> list[str]:
    """Os ids do Fracttal (texto) de quem é do setor Performance hoje: a última decisão de cada pessoa
    (`setores.vigentes`, a mesma regra da tela Pessoas e setores). Setor apagado ou sem ninguém: lista vazia."""
    from ..cadastro import setores as S
    sid = next((s["setor_id"] for s in S.ativos(setores.get("setores") or []) if s["setor_id"] == SETOR), None)
    if sid is None:
        return []
    return [str(fid) for fid, s in S.vigentes(setores.get("decisoes") or []).items()
            if s == sid and fid not in (None, "")]


def _setores() -> dict:
    from ..cadastro import setores as S
    from ..dados import conexao
    return S.ler(*conexao.banco())


def _reler(app):
    a = _EST
    try:
        with app.app_context():
            st = _setores()
            if st.get("erro") and not st.get("decisoes"):
                raise RuntimeError(f"setores não lidos: {st['erro']}")
            fids = ids_do_setor(st)
            if time.time() - a["pessoas_ts"] > PESSOAS_S or not a["pessoas"]:
                a["pessoas"] = OE._paginas("personnel?x=1")
                a["pessoas_ts"] = time.time()
            por_id = {str(p.get("id_personnel")): p for p in a["pessoas"]}
            agora = datetime.now(timezone.utc)
            todas, faltam, equipe = [], [], []
            for fid in fids:
                p = por_id.get(fid)
                if not p:
                    faltam.append(f"id {fid}")
                    continue
                nome = " ".join(str(p.get("name") or p.get("full_name") or "").split())
                if not nome:
                    faltam.append(f"id {fid}")
                    continue
                pessoa = {"id": p.get("id_personnel"), "nome": nome, "nome_fracttal": nome}
                equipe.append(pessoa)
                linhas, vistas = [], set()
                for g in OE.grafias(nome, p):
                    for w in OE._paginas(f"work_orders?personnel_description={quote(g)}"):
                        chave = json.dumps(w, sort_keys=True, default=str)   # a mesma linha por dois trechos entra uma vez
                        if chave not in vistas:
                            vistas.add(chave)
                            linhas.append(w)
                    time.sleep(0.3)
                todas += OE.montar(linhas, pessoa, agora)
            equipe.sort(key=lambda p: _norm(p["nome"]))
            a.update(os=todas, equipe=equipe, faltam=faltam, ts=time.time(), erro="", erro_em=0.0)
    except Exception as e:      # noqa: BLE001 — 429, rede ou banco fora: fica a leitura anterior
        a.update(erro=str(e)[:160], erro_em=time.time())
    finally:
        a["lendo"] = False


def pedir_releitura(app=None, esperar=False, forcar=False):
    """Relê se a cópia tem mais de 5 min (`forcar`: mais de FORCAR_S, depois que o card do OS Creator mudou uma OS). Sem
    nenhuma cópia ainda, `esperar` lê na hora. A mesma regra do quadro da Engenharia (`os_equipe.pedir_releitura`)."""
    if time.time() - _EST["ts"] < (FORCAR_S if forcar else VALIDADE_S):
        return
    with _TRAVA:
        if _EST["lendo"] or time.time() - _EST["erro_em"] < 60:
            return
        _EST["lendo"] = True
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()
    if esperar or app.config.get("TESTING"):
        _reler(app)
    else:
        from ..casca import fracttal_conta          # a releitura por trás declara o fundo (o teto de 90 do porteiro)
        threading.Thread(target=fracttal_conta.de_fundo("fundo:nexus-os-equipe-performance", _reler), args=(app,),
                         daemon=True, name="nexus-os-equipe-performance").start()


def marcar_uso():
    _EST["usado"] = time.time()


def _tique(app, agora: float | None = None) -> bool:
    """Uma volta do `manter_quente`: relê por trás se alguém abriu o quadro nas últimas 2 h e a cópia passou dos 5 min."""
    agora = time.time() if agora is None else agora
    if not _EST["usado"] or agora - _EST["usado"] > USO_S:
        return False
    if _EST["ts"] and agora - _EST["ts"] < VALIDADE_S:
        return False
    pedir_releitura(app, forcar=True)
    return True


def manter_quente(app):
    """A volta de cada minuto (`_tique`), numa thread. Quem chama é o `instalar` da Engenharia (app.py e servir.py), nunca
    o create_app: teste não fala com a rede."""
    def laco():
        while True:
            time.sleep(QUENTE_S)
            try:
                _tique(app)
            except Exception:       # noqa: BLE001 — a volta seguinte tenta de novo; a tela relê na visita
                pass
    threading.Thread(target=laco, daemon=True, name="nexus-os-equipe-performance-quente").start()


def dados() -> dict:
    return {"os": list(_EST["os"]), "equipe": list(_EST.get("equipe") or []), "faltam": list(_EST["faltam"]),
            "lido": _EST["ts"], "lendo": _EST["lendo"], "erro": _EST["erro"]}


def limpar():
    _EST.update(ts=0.0, pessoas_ts=0.0, pessoas=[], os=[], equipe=[], lendo=False, erro="", erro_em=0.0, faltam=[],
                usado=0.0)
