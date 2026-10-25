"""Pré-carga das telas de quem tem setor (Levi, 12/10/2026: "para esses que tem setores, exceto sem setores e
administradores - assim que entrar já pré carrega tudo o que está disponível para aquela pessoa, pode fazer por partes
mas é interessante que fique cada vez mais leve da pessoa abrir uma informação e analisar!").

Medido em 12/10/2026 num processo novo (as 85 telas abertas duas vezes, o Fracttal bloqueado): no 1º clique, Visão do
responsável 10,8 s, Clima e risco 9,8 s, Confiabilidade 3,0 s, Rondas 2,6 s, Governança 2,4 s e Gestão PCM 1,0 s; no 2º,
todas abaixo de 0,1 s. O peso é encher as cópias do servidor (o banco, o INPE, o INMET, a NASA), e as cópias são de
todos: a tela aquecida para uma pessoa fica quente para quem vier depois.

- **Quando:** o portão (`setor_telas.portao`) chama `lembrar` a cada pedido de quem tem setor e não é administrador; no
  máximo uma vez por minuto para o mesmo conjunto de telas, as que não foram aquecidas nos últimos REAQUECER_S vão para a
  fila. O 1º pedido depois do login dispara a volta inteira, começando pela 1ª tela de cada torre (onde o cartão do
  Início leva) e seguindo na ordem do menu. Enquanto alguém do setor estiver usando, a volta se repete a cada
  REAQUECER_S (2 min): a cópia que venceu é refeita por trás em até 2 min, e não no clique. Com 4 min não bastava: a
  cópia de 5 min revista aos 4 ainda está boa, vence aos 5 e só seria refeita aos 8, no clique de alguém.
- **Como:** um trabalhador só (uma thread) abre cada tela por dentro (o `test_client` do próprio app, com uma sessão
  interna de administrador sem login do Fracttal, que não sai do processo), uma por vez e com PAUSA_S entre elas: é por
  partes, e o servidor segue livre para as pessoas. A tela aberta assim enche as mesmas cópias que a visita encheria (as
  do Campo seguem renovadas pelo `visao.manter_quente` enquanto forem usadas).
- **Fora:** as telas que leem o Fracttal ao abrir (FORA: a cota de 200 pedidos por minuto é da empresa inteira e o App de
  Campo vive dela), o OS Creator (a torre OS lê o Fracttal com o login da pessoa) e as telas da plataforma na moldura (o
  peso delas é da plataforma, que tem a própria pré-carga). Uma tela fora da FORA que leia o Fracttal durante a
  pré-carga é anotada (`campo.fracttal.marcar_pre_carga`), sai da pré-carga até o Nexus reiniciar, e o log pede para
  pô-la na FORA.
- `NEXUS_PRE_CARGA=0` desliga numa máquina. Nos testes, só liga quando o teste pede, e roda na hora (sem thread).
"""
import logging
import threading
import time
from collections import deque

from flask import current_app

log = logging.getLogger(__name__)

REAQUECER_S = 120
LEMBRAR_S = 60
PAUSA_S = 0.3
# as telas que leem o Fracttal ao abrir: medido em 12/10/2026 abrindo as 85 telas com o Fracttal bloqueado, só estas
# tentaram. Tela nova que lê o Fracttal ao abrir entra aqui (nexus/torres/CLAUDE.md).
FORA = frozenset({"engenharia/mesa", "engenharia/confiabilidade", "engenharia/equipe", "campo/aprovacao"})
CABECALHO = "X-Nexus-Pre-Carga"


def ligada(cfg) -> bool:
    v = cfg.get("NEXUS_PRE_CARGA")
    if v is None:
        return not cfg.get("TESTING")
    return str(v).strip().lower() not in ("", "0", "false", "nao", "não", "desligado")


def _estado(app) -> dict:
    e = app.extensions.get("nexus_pre_carga")
    if e is None:
        e = app.extensions.setdefault("nexus_pre_carga", {
            "trava": threading.Lock(), "fila": deque(), "na_fila": set(), "aquecida_em": {}, "ultimo": {},
            "lembrado_em": {}, "fracttal": set(), "trabalhando": False, "ultima_volta": None, "aqueciveis": None})
    return e


def aqueciveis(app) -> list[str]:
    """As telas que a pré-carga abre, na ordem do menu: todas menos a FORA, a torre OS e as molduras da plataforma."""
    e = _estado(app)
    if e["aqueciveis"] is None:
        from ..performance import porta
        torres = sorted(app.extensions["nexus_torres"], key=lambda t: t.ordem)
        fora = FORA | {f"{m.torre}/{m.tela}" for t in torres for m in porta.da_torre(t.id)}
        e["aqueciveis"] = [f"{t.id}/{s.id}" for t in torres if t.id != "os" for s in t.telas
                           if f"{t.id}/{s.id}" not in fora]
    return e["aqueciveis"]


def lembrar(telas) -> None:
    """Quem tem setor pediu algo: as telas dele que esfriaram vão para a fila (na ordem do menu)."""
    app = current_app._get_current_object()
    if not ligada(app.config) or not telas:
        return
    e = _estado(app)
    chave = frozenset(telas)
    agora = time.time()
    with e["trava"]:
        if agora - e["lembrado_em"].get(chave, 0.0) < LEMBRAR_S:
            return
        e["lembrado_em"][chave] = agora
        novas = [t for t in aqueciveis(app) if t in chave and t not in e["fracttal"] and t not in e["na_fila"]
                 and agora - e["aquecida_em"].get(t, 0.0) >= REAQUECER_S]
        # a 1ª tela de cada torre primeiro (o cartão do Início leva a ela), depois o resto na ordem do menu
        torres_vistas, primeiras, resto = set(), [], []
        for t in novas:
            torre = t.split("/", 1)[0]
            (resto if torre in torres_vistas else primeiras).append(t)
            torres_vistas.add(torre)
        e["fila"].extend(primeiras + resto)
        e["na_fila"].update(novas)
        acordar = bool(novas) and not e["trabalhando"]
        if acordar:
            e["trabalhando"] = True
    if not acordar:
        return
    if app.config.get("TESTING"):
        _trabalhar(app)
    else:
        threading.Thread(target=_trabalhar, args=(app,), daemon=True, name="nexus-pre-carga").start()


def aquecer_ao_subir(app, espera_s: int = 300) -> None:
    """Uma volta inteira da pré-carga depois do boot, para todo mundo (13/10/2026, Levi: "o link do servidor demorou
    muito para carregar"): cada deploy reinicia o Nexus e esfria todas as cópias, e no servidor recém-subido a 1ª janela
    da Meta levou 27 s. A volta é a de sempre (uma tela por vez, com pausa, por trás); depois, quem tem setor segue
    mantendo as dele quentes. Quem chama é o servir.py e o app.py, nunca o create_app (os testes não ligam nada).

    **5 minutos, e não 30 s:** a 1ª volta abre também as telas que pedem leitura ao Fracttal (Rondas, Visão do
    responsável, Engenharia), e as leituras da subida saem espaçadas de propósito (Aprovação 20 s, rondas 90 s, chamados
    120 s, OS de falha 150 s, Quadro 210 s). Aos 30 s a volta juntava todas e a cota da empresa (200/min) estourava: o
    "excesso de pedidos" que trava as fotos das rondas. Aos 5 min elas já rodaram e as telas acham tudo lido. Com
    `NEXUS_CAMPO_AQUECER=0` (a máquina que não lê o Fracttal ao subir) não roda, e `NEXUS_PRE_CARGA=0` desliga junto."""
    if not ligada(app.config) or str(app.config.get("NEXUS_CAMPO_AQUECER", "1")).strip() == "0":
        return

    def rodar():
        time.sleep(espera_s)
        try:
            with app.app_context():
                lembrar(aqueciveis(app))
        except Exception as ex:      # noqa: BLE001 — aquecer nunca derruba o Nexus
            log.warning("Pré-carga ao subir não rodou (%s: %s).", type(ex).__name__, ex)
    threading.Thread(target=rodar, daemon=True, name="nexus-pre-carga-boot").start()


def _biscoito(app) -> str:
    """A sessão interna: administrador, sem login do Fracttal (nenhuma tela lê o Fracttal com o login de alguém),
    assinada com a chave do próprio Nexus. Vai no cabeçalho, e não no pote do cliente, porque no servidor o cookie é
    Secure e o cliente interno fala http."""
    ser = app.session_interface.get_signing_serializer(app)
    valor = ser.dumps({"logado": True, "admin": True, "pre_carga": True})
    return f"{app.config.get('SESSION_COOKIE_NAME') or 'session'}={valor}"


def _trabalhar(app) -> None:
    from ..campo import fracttal as F
    e = _estado(app)
    # sem o pote de cookies: com ele, o cliente troca o cabeçalho Cookie pelo pote (vazio) e a sessão não chega
    cliente = app.test_client(use_cookies=False)
    cabecalhos = {"Cookie": _biscoito(app), CABECALHO: "1"}
    volta = {"inicio": time.time(), "telas": 0, "s": 0.0, "mais_lenta": None, "erros": 0}
    while True:
        with e["trava"]:
            if not e["fila"]:
                e["trabalhando"] = False
                if volta["telas"]:
                    volta["fim"] = time.time()
                    e["ultima_volta"] = volta
                    log.info("Pré-carga: %s tela(s) em %.1f s (a mais lenta, %s: %.1f s); %s com erro.", volta["telas"],
                             volta["s"], volta["mais_lenta"][0], volta["mais_lenta"][1], volta["erros"])
                return
            tela = e["fila"].popleft()
            e["na_fila"].discard(tela)
        t0 = time.time()
        F.marcar_pre_carga(True)
        try:
            status = cliente.get("/t/" + tela, headers=cabecalhos).status_code
        except Exception as ex:  # noqa: BLE001 — a tela que quebra aqui quebraria na visita: o log diz, a fila segue
            status = type(ex).__name__
        finally:
            leu = F.marcar_pre_carga(False)
        dt = time.time() - t0
        with e["trava"]:
            e["aquecida_em"][tela] = time.time()
            e["ultimo"][tela] = (status, round(dt, 2))
            if leu:
                e["fracttal"].add(tela)
        if leu:
            log.warning("Pré-carga: a tela %s leu o Fracttal ao abrir; saiu da pré-carga até o Nexus reiniciar. Ponha "
                        "na FORA de nexus/auth/pre_carga.py.", tela)
        if not isinstance(status, int) or status >= 400:
            volta["erros"] += 1
            log.warning("Pré-carga: a tela %s respondeu %s.", tela, status)
        volta["telas"] += 1
        volta["s"] += dt
        if not volta["mais_lenta"] or dt > volta["mais_lenta"][1]:
            volta["mais_lenta"] = (tela, dt)
        if not app.config.get("TESTING"):
            time.sleep(PAUSA_S)


def resumo(app) -> dict:
    """Para a tela Acessos: ligada, trabalhando agora, a última volta e o que ficou de fora."""
    e = _estado(app)
    with e["trava"]:
        v = dict(e["ultima_volta"]) if e["ultima_volta"] else None
        return {"ligada": ligada(app.config), "trabalhando": e["trabalhando"], "na_fila": len(e["fila"]), "volta": v,
                "fracttal": sorted(e["fracttal"]), "aqueciveis": len(aqueciveis(app))}
