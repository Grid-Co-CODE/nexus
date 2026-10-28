"""O Responsável UFV de cada chamado de Garantias (Levi, 28/10/2026: "Tire o filtro de responsável e inclua o filtro
Responsável UFV que é o supervisor da UFV"): o Responsável O&M da ficha da usina no cadastro do Nexus, o mesmo da Mesa da
Segurança e da Central de atenção (`nexus/campo/visao.py`, `_Base.responsavel_da_usina`).

O quadro mora no clone do OS Creator, que não importa o Nexus: a ponte põe aqui a função ao criar o clone
(`ponte._criar_clone`, `rotas_acomp.RESPONSAVEL_UFV`), e ela roda no app do Nexus, porque o nome da pessoa vem do cofre
do cadastro (sem a chave, sairia "Responsável 7"). A usina do chamado sai do nome da usina do Fracttal (o de-para) ou do
código do ativo, como no fato do chamado (`Ligador.usina`). O cadastro fica 10 min na memória; sem ele (o banco fora), o
quadro sai sem o supervisor, e não chuta."""
import threading
import time

TTL = 600
_MEMO: dict = {}
_TRAVA = threading.Lock()


def _base():
    from ...campo import visao
    return visao._Base()


def _sem_responsavel() -> str:
    from ...campo import visao
    return visao.SEM_RESPONSAVEL


def _base_guardada():
    with _TRAVA:
        v = _MEMO.get("base")
        if v and time.monotonic() - v[0] < TTL:
            return v[1]
    b = _base()
    with _TRAVA:
        _MEMO["base"] = (time.monotonic(), b)
    return b


def responsavel_ufv(cards) -> dict:
    """{nº da OS: o Responsável O&M da usina dela} ("" quando a usina não liga ou não tem responsável); {} sem o
    cadastro."""
    try:
        b = _base_guardada()
    except Exception:                                   # noqa: BLE001 — sem o cadastro, sem o supervisor
        return {}
    sem = _sem_responsavel()
    out = {}
    for c in cards:
        try:
            uid, _como = b.lig.usina(c.get("usina") or "", c.get("code") or "")
            nome = b.responsavel_da_usina(uid) if uid else ""
        except Exception:                               # noqa: BLE001 — a usina que não liga fica sem o supervisor
            nome = ""
        out[c.get("folio")] = "" if nome == sem else (nome or "")
    return out


def ligar(app):
    """A função que o clone chama, rodando no app do Nexus (a configuração e a chave do cofre do cadastro)."""
    def no_nexus(cards):
        with app.app_context():
            return responsavel_ufv(cards)
    no_nexus.nexus = responsavel_ufv
    return no_nexus
