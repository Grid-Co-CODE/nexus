"""O Responsável UFV de cada chamado de Garantias (Levi, 28/10/2026: "Tire o filtro de responsável e inclua o filtro
Responsável UFV que é o supervisor da UFV"): o Responsável O&M da ficha da usina no cadastro do Nexus, o mesmo da Mesa da
Segurança e da Central de atenção (`nexus/campo/visao.py`, `_Base.responsavel_da_usina`).

O quadro mora no clone do OS Creator, que não importa o Nexus: a ponte põe aqui a função ao criar o clone
(`ponte._criar_clone`, `rotas_acomp.RESPONSAVEL_UFV`). A usina do chamado sai do nome da usina do Fracttal (o de-para) ou
do código do ativo, como no fato do chamado (`Ligador.usina`).

NUNCA NA FRENTE DO QUADRO (29/10/2026): até então o cadastro era lido dentro do pedido do quadro, de 10 em 10 min, e o
Raio-X pegou o GET /os/chamados/acompanhamento preso 30 vezes em 24 h, até 40 s em `livros.abas` (o banco da Gridco
lento). Agora o cadastro é lido POR TRÁS, numa thread, no app do Nexus (o nome da pessoa vem do cofre do cadastro: sem a
chave, sairia "Responsável 7"), e vira duas coisas na memória: o ligador e a tabela usina -> responsável, já com os
nomes. O quadro só consulta a memória: sem leitura ainda (a 1ª depois de subir), sai sem o supervisor e pede a leitura;
vencida (10 min), sai com a de antes e relê por trás, uma releitura por vez; a que falha fica com a de antes. A ponte
pede a 1ª leitura ao criar o clone (`ligar`)."""
import logging
import threading
import time

TTL = 600
_ESTADO = {"lig": None, "nomes": {}, "lido": 0.0, "lendo": False}
_TRAVA = threading.Lock()
log = logging.getLogger("nexus.chamados")


def _base():
    from ...campo import visao
    return visao._Base()


def _sem_responsavel() -> str:
    from ...campo import visao
    return visao.SEM_RESPONSAVEL


def _em_segundo_plano(fn):
    """Onde a leitura roda: uma thread solta (os testes trocam para rodar quando querem)."""
    threading.Thread(target=fn, daemon=True, name="nexus-responsavel-ufv").start()


def limpar() -> None:
    with _TRAVA:
        _ESTADO.update(lig=None, nomes={}, lido=0.0, lendo=False)


def _ler():
    """O ligador e {usina_id: Responsável O&M} de todas as usinas do cadastro (o nome já lido do cofre)."""
    b = _base()
    sem = _sem_responsavel()
    nomes = {}
    for uid in list(getattr(b, "por_id", {}) or {}):
        try:
            n = b.responsavel_da_usina(uid)
        except Exception:                               # noqa: BLE001 — a usina sem ficha legível fica sem o supervisor
            n = ""
        nomes[uid] = "" if n == sem else (n or "")
    return b.lig, nomes


def _renovar(app):
    try:
        if app is not None:
            with app.app_context():
                lig, nomes = _ler()
        else:
            lig, nomes = _ler()
        with _TRAVA:
            _ESTADO.update(lig=lig, nomes=nomes, lido=time.monotonic())
    except Exception as e:                              # noqa: BLE001 — fica a leitura de antes; a próxima visita tenta
        log.warning("Responsável UFV: não consegui ler o cadastro (%s)", type(e).__name__)
    finally:
        with _TRAVA:
            _ESTADO["lendo"] = False


def preparar(app=None) -> None:
    """Pede a leitura por trás, se não há uma em vigor nem uma em andamento."""
    with _TRAVA:
        vencida = _ESTADO["lig"] is None or time.monotonic() - _ESTADO["lido"] >= TTL
        if not vencida or _ESTADO["lendo"]:
            return
        _ESTADO["lendo"] = True
    _em_segundo_plano(lambda: _renovar(app))


def responsavel_ufv(cards, app=None) -> dict:
    """{nº da OS: o Responsável O&M da usina dela} ("" quando a usina não liga ou não tem responsável); {} sem nenhuma
    leitura do cadastro ainda. Nunca espera o banco (ver o topo)."""
    preparar(app)
    with _TRAVA:
        lig, nomes = _ESTADO["lig"], _ESTADO["nomes"]
    if lig is None:
        return {}
    out = {}
    for c in cards:
        try:
            uid, _como = lig.usina(c.get("usina") or "", c.get("code") or "")
        except Exception:                               # noqa: BLE001 — a usina que não liga fica sem o supervisor
            uid = None
        out[c.get("folio")] = nomes.get(uid, "") if uid else ""
    return out


def ligar(app):
    """A função que o clone chama; a leitura por trás roda no app do Nexus (a configuração e a chave do cofre). Já pede a
    1ª leitura, para o primeiro quadro depois de subir já ter o supervisor."""
    def no_nexus(cards):
        return responsavel_ufv(cards, app)
    no_nexus.nexus = responsavel_ufv
    preparar(app)
    return no_nexus
