"""As subtarefas padrão de cada atividade da Performance no OS Creator (05/11/2026).

Levi: "Quero que no OS Creator > Performance tenha um campo para subtarefas, que vamos poder editar as subtarefas padrões de
cada atividade!"; "Quando criamos uma OS as atividades já vem com aquelas subtarefas"; e quem pode mudar: "Qualquer um".

Até aqui as subtarefas de cada atividade (Inspeção Geral do Inversor, Recomposição de String, Verificação de Tracker Parado,
Coleta de dados de geração) eram as do plano do Fracttal, mais as perguntas que o app acrescenta (`os_planos.SUBTAREFAS_EXTRA`).
O plano é de outra área e vale para quem cria OS por fora do Nexus: o padrão editado mora aqui, e o plano não muda.

O livro `nexus_subtarefas_performance · fato_versao_subtarefas` (no catálogo antes da 1ª gravação, regra 10 do
`nexus/dados/CLAUDE.md`): 1 linha por versão salva da lista de uma atividade (`salvou`) ou pela volta ao plano do Fracttal
(`voltou_ao_fracttal`); só acrescenta. A versão em vigor é a última da atividade. Em claro: a atividade (a frase do plano), a
lista (o texto de uma subtarefa não é dado pessoal) e o código de quem salvou (`pessoa_hmac`, o do e-mail); o nome de quem
salvou, só cifrado (o Cofre), para a tela dizer "salvo por". O OS Creator chega aqui pela ponte (`ligar`), como os avisos.
"""
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ...comando import estado as ES
from ...dados import livros

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO, ABA = ("nexus_subtarefas_performance", "Nexus · subtarefas padrão da Performance (OS Creator)",
                          "fato_versao_subtarefas")
CAB = ("id", "registrado_em", "data_id", "atividade", "evento", "n_subtarefas", "subtarefas_json", "pessoa_hmac",
       "dados_cifrados")
EVENTOS = ("salvou", "voltou_ao_fracttal")
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê."""


def limpar() -> None:
    _CACHE.clear()


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _ctx(l: dict) -> str:
    return f"banco/subtarefas_performance/{_txt(l.get('id'))}/{_txt(l.get('atividade'))}"


# ── o livro ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def ler(forcar: bool = False) -> dict:
    """{"linhas", "lido_em", "erro"}, cópia de 1 minuto. A leitura que falha devolve a última boa com o erro."""
    agora = time.time()
    g = _CACHE.get("livro")
    if g and not forcar and agora - (g.get("lido_em") or 0) < TTL_S:
        return g
    try:
        linhas = livros.ler(*ES._banco(), LIVRO, ABA)
    except Exception as ex:      # noqa: BLE001 — banco fora (ou o livro antes da 1ª gravação): quem lê decide o que dizer
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        _CACHE["livro"] = {"linhas": (g or {}).get("linhas") or [], "lido_em": agora, "erro": erro,
                           "ja_leu": bool((g or {}).get("ja_leu"))}
        return _CACHE["livro"]
    _CACHE["livro"] = {"linhas": linhas, "lido_em": agora, "erro": "", "ja_leu": True}
    return _CACHE["livro"]


def _gravar(nova: dict) -> None:
    """Acrescenta a linha (o livro inteiro de novo, como os outros livros do Nexus) e põe na cópia na hora."""
    base, sessao = ES._banco()
    with _TRAVA:
        lido = livros.ler(base, sessao, LIVRO, ABA)
        try:
            livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in lido + [nova]])},
                            base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
        finally:
            _CACHE["livro"] = {"linhas": list(lido) + [nova], "lido_em": time.time(), "erro": "", "ja_leu": True}


def _quando(l: dict) -> str:
    """O registrado_em da linha em Brasília, "dd/mm/aaaa hh:mm" (vazio se não der para ler)."""
    s = _txt(l.get("registrado_em")).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return ""
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(_BRT).strftime("%d/%m/%Y %H:%M")


def _nome(l: dict, cofre) -> str:
    if not l.get("dados_cifrados") or cofre is None:
        return ""
    try:
        return _txt(json.loads(cofre.decifrar(l["dados_cifrados"], _ctx(l))).get("nome"))
    except Exception:            # noqa: BLE001 — linha mexida ou chave trocada: fica a versão, sem o nome
        return ""


def atual(atividade: str, lido: dict | None = None) -> dict:
    """A versão em vigor da atividade: {"lista": [...] ou None (o plano do Fracttal), "evento", "quando", "por", "erro"}.

    `erro` só quando o livro não pôde ser lido NENHUMA vez desde que o Nexus subiu: aí não se sabe se há padrão salvo, e quem
    cria a OS avisa (a OS sai com as do plano do Fracttal). Com uma leitura boa guardada, vale a última boa."""
    lido = lido or ler()
    if lido.get("erro") and not lido.get("ja_leu"):
        return {"lista": None, "evento": "", "quando": "", "por": "", "erro": lido["erro"]}
    alvo = _txt(atividade)
    ult = None
    for l in lido.get("linhas") or []:
        if _txt(l.get("atividade")) == alvo and _txt(l.get("evento")) in EVENTOS:
            if ult is None or _txt(l.get("registrado_em")) >= _txt(ult.get("registrado_em")):
                ult = l
    if ult is None:
        return {"lista": None, "evento": "", "quando": "", "por": "", "erro": ""}
    lista = None
    if _txt(ult.get("evento")) == "salvou":
        try:
            lista = json.loads(ult.get("subtarefas_json") or "[]")
        except ValueError:
            lista = None
        if not isinstance(lista, list) or not lista:
            lista = None
    try:
        cofre = ES._cofre()
    except ES.Recusada:
        cofre = None
    return {"lista": lista, "evento": _txt(ult.get("evento")), "quando": _quando(ult), "por": _nome(ult, cofre),
            "erro": ""}


# ── gravar ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _linha_de(atividade: str, evento: str, lista: list | None, conta: dict) -> dict:
    c = conta if isinstance(conta, dict) else {}
    email = _txt(c.get("email")).lower()
    if not email:
        raise Recusada("Entre com o seu login do Fracttal no OS Creator: sem ele não se sabe quem mudou o padrão")
    if not current_app.config.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    from ...campo.ligacao_cadastro import codigo_da_pessoa
    quem = (codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) or "").lower()
    if not quem:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    agora = datetime.now(timezone.utc)
    l = {"id": "s" + uuid.uuid4().hex[:11],
         "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z",
         "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "atividade": _txt(atividade), "evento": evento,
         "n_subtarefas": len(lista or []), "subtarefas_json": json.dumps(lista, ensure_ascii=False) if lista else "",
         "pessoa_hmac": quem, "dados_cifrados": None}
    nome = _txt(c.get("nome"))
    if nome:
        try:
            l["dados_cifrados"] = ES._cofre().cifrar(json.dumps({"nome": nome}, ensure_ascii=False), _ctx(l))
        except ES.Recusada:
            pass                 # sem a chave do cadastro o nome não vai (nunca em claro): a versão fica sem o "salvo por"
    return l


def salvar(atividade: str, lista: list, conta: dict) -> dict:
    """Grava a lista (já conferida pela tela do OS Creator, `perf_web.validar_lista`) como o padrão da atividade."""
    if not _txt(atividade):
        raise Recusada("Sem a atividade")
    if not isinstance(lista, list) or not lista:
        raise Recusada("A lista de subtarefas está vazia")
    _gravar(_linha_de(atividade, "salvou", lista, conta))
    return atual(atividade)


def voltar_ao_fracttal(atividade: str, conta: dict) -> dict:
    """Desfaz o padrão do Nexus: a atividade volta às subtarefas do plano do Fracttal (o histórico fica no livro)."""
    if not _txt(atividade):
        raise Recusada("Sem a atividade")
    _gravar(_linha_de(atividade, "voltou_ao_fracttal", None, conta))
    return atual(atividade)


class _Gancho:
    """O que a ponte põe no `perf_web.SUBTAREFAS_PADRAO`: as funções acima no contexto do Nexus (a tela roda no app do
    clone). `Recusada` sobe como está, para a tela dizer o motivo."""

    Recusada = Recusada

    def __init__(self, app):
        self._app = app

    def atual(self, atividade: str) -> dict:
        with self._app.app_context():
            return atual(atividade)

    def salvar(self, atividade: str, lista: list, conta: dict) -> dict:
        with self._app.app_context():
            return salvar(atividade, lista, conta)

    def voltar(self, atividade: str, conta: dict) -> dict:
        with self._app.app_context():
            return voltar_ao_fracttal(atividade, conta)


def ligar(app) -> _Gancho:
    return _Gancho(app)
