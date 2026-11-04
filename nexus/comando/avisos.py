"""Os avisos das OS de cada pessoa, no sino do topo (04/11/2026).

Levi: "Quero que inclua no nexus notificações para OSs abertas por mim que tiveram resposta ... e tem que ter um botão de
marcar como lida!"; "penso tanto em execução de OS quanto solicitação: 'Sua solicitação gerou uma OS', 'OS x concluída pelo
técnico'; aí clica na notificação e aparece a OS, pode ter um botão para fazer download do pdf da OS". O clique abre o card
da OS do OS Creator (`oscreator/card_os_abrir.html`), que já tem o botão do PDF.

De onde vem cada aviso, sem pedido a mais ao Fracttal:
- **execucao**: a lista central de OS do OS Creator (`os_central`, que o servidor lê a cada poucos minutos): as OS que a
  pessoa criou (o "Criado por", pelo nome, com a regra do homônimo do `filtrar`: com homônimo, nada) que foram para Em
  Verificação ou Concluída nos últimos JANELA_DIAS, pela data de fim. Quem executou é o atribuído; a OS que a própria pessoa
  executou não avisa;
- **solicitacao**: o evento `gerou_os`, gravado aqui quando o PCM aprova a solicitação no OS Creator
  (`rotas_solic.api_aprovar`, pelo gancho `AO_APROVAR` que a ponte liga). A aprovada direto no Fracttal não avisa (decidido
  em 04/11/2026: saber dela custaria ler no Fracttal as solicitações de cada pessoa).

O livro `nexus_avisos · fato_evento_aviso` (no catálogo antes da 1ª gravação, regra 10 do `nexus/dados/CLAUDE.md`): 1 linha
por evento, só acrescenta. `gerou_os` é o aviso de solicitação: para quem pediu (`destino_hmac`, o código do NOME, porque a
solicitação do Fracttal só traz o nome), por quem aprovou (`pessoa_hmac`). `leu` é quem marcou como lido (`pessoa_hmac`, o
código do e-mail, o mesmo das conversas). Em claro: o aviso, o tipo, o evento, a OS (id e nº) e os códigos; os nomes,
cifrados (o Cofre). O sino só lê a cópia de 1 minuto (`copia`): nenhuma página espera o banco.
"""
import json
import logging
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros
from . import estado as ES

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO, ABA = "nexus_avisos", "Nexus · avisos das OS (execução e solicitação)", "fato_evento_aviso"
CAB = ("id", "registrado_em", "data_id", "aviso_id", "tipo", "evento", "os_id", "folio", "destino_hmac", "pessoa_hmac",
       "dados_cifrados")
EVENTOS = ("gerou_os", "leu")
JANELA_DIAS = 7
EXECUTADA = {2: "Em Verificação", 3: "Concluída"}
# E:<id da OS>:<data de fim, AAAAMMDDHHMM> (a OS executada de novo é outro aviso) ou S:<código da solicitação>
AVISO_RE = re.compile(r"E:\d{1,12}:\d{12}|S:[A-Za-z0-9_\-]{1,40}")
MAX_POR_VEZ = 200            # quantos avisos um "Marcar todas" grava de uma vez
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}
_RENOVANDO = {"thread": None}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê."""


def limpar() -> None:
    _CACHE.clear()


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _norm(nome) -> str:
    """O nome sem acento, sem caixa e com um espaço só (o "Criado por" e o nome do login nem sempre têm o mesmo acento)."""
    s = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    return " ".join(s.casefold().split())


def _codigo(texto: str) -> str:
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    return (codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), texto) or "").lower()


def codigo_do_nome(nome) -> str:
    """O código de quem pediu a solicitação: o do NOME (a solicitação do Fracttal não traz o e-mail), num espaço separado do
    código do e-mail (o prefixo `nome:`), para os dois nunca se confundirem."""
    n = _norm(nome)
    return _codigo("nome:" + n) if n else ""


def _quando(iso):
    """A data do Fracttal (ISO, em UTC quando sem fuso) em Brasília, ou None."""
    s = _txt(iso).replace("Z", "+00:00")
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(_BRT)


def _ctx(l: dict) -> str:
    return f"banco/avisos/{_txt(l.get('id'))}/{_txt(l.get('aviso_id'))}/{_txt(l.get('evento'))}"


# ── o livro ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def ler(forcar: bool = False) -> dict:
    """{"linhas", "lido_em", "erro"}, cópia de 1 minuto. A leitura que falha devolve a última boa com o erro."""
    agora = time.time()
    g = _CACHE.get("livro")
    if g and not forcar and agora - (g.get("lido_em") or 0) < TTL_S:
        return g
    try:
        linhas = livros.ler(*ES._banco(), LIVRO, ABA)
    except Exception as ex:      # noqa: BLE001 — banco fora (ou o livro antes da 1ª gravação): o sino segue sem os eventos
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        _CACHE["livro"] = {"linhas": (g or {}).get("linhas") or [], "lido_em": agora, "erro": erro}
        return _CACHE["livro"]
    _CACHE["livro"] = {"linhas": linhas, "lido_em": agora, "erro": ""}
    return _CACHE["livro"]


def copia() -> list[dict]:
    """As linhas da cópia de 1 minuto, para o sino de toda página: vencida ou ausente, a leitura começa por trás e o sino usa
    o que tem (o modelo das conversas, `conversa.copias`)."""
    g = _CACHE.get("livro")
    if (g is None or time.time() - (g.get("lido_em") or 0) >= TTL_S) and not current_app.config.get("TESTING"):
        t = _RENOVANDO["thread"]
        if t is None or not t.is_alive():
            app = current_app._get_current_object()

            def rodar():
                with app.app_context():
                    try:
                        ler(forcar=True)
                    except Exception:    # noqa: BLE001 — o sino só fica com a cópia de antes
                        current_app.logger.warning("sino: a cópia dos avisos não renovou", exc_info=True)
            t = threading.Thread(target=rodar, name="nexus-avisos", daemon=True)
            _RENOVANDO["thread"] = t
            t.start()
    return (g or {}).get("linhas") or []


def _gravar(novas: list[dict]) -> None:
    """Acrescenta as linhas (o livro inteiro de novo, como os outros livros do Comando) e põe na cópia na hora."""
    base, sessao = ES._banco()
    with _TRAVA:
        lido = livros.ler(base, sessao, LIVRO, ABA)
        try:
            livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in lido + novas])},
                            base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
        finally:
            _CACHE["livro"] = {"linhas": list(lido) + novas, "lido_em": time.time(), "erro": ""}


def _linha(aviso_id: str, tipo: str, evento: str, *, os_id=None, folio="", destino_hmac="", pessoa_hmac="",
           dados=None, cofre=None) -> dict:
    agora = datetime.now(timezone.utc)
    l = {"id": "a" + uuid.uuid4().hex[:11],
         "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z",
         "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "aviso_id": aviso_id, "tipo": tipo,
         "evento": evento, "os_id": os_id, "folio": _txt(folio), "destino_hmac": destino_hmac, "pessoa_hmac": pessoa_hmac,
         "dados_cifrados": None}
    if dados and cofre is not None:
        l["dados_cifrados"] = cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(l))
    return l


# ── os avisos de uma pessoa ─────────────────────────────────────────────────────────────────────────────────────────
def _os_central():
    from ..torres.oscreator import ponte
    return ponte.modulo_do_clone("os_central")


def execucoes(nome: str, agora: datetime | None = None) -> list[dict]:
    """As OS que `nome` criou e que foram executadas nos últimos JANELA_DIAS, da lista central (nada vai ao Fracttal). Lista
    vazia quando a lista central não responde pela pessoa (o homônimo, o nome sem OS, a lista ainda sem leitura)."""
    meu = _norm(nome)
    if not meu:
        return []
    agora = agora or datetime.now(_BRT)
    try:
        oc = _os_central()
        lista = oc.atual()
        # o sino está em toda página: a conta da pessoa vale enquanto a lista não muda, por até 1 minuto
        guardado = _CACHE.get(("exec", meu))
        if guardado and guardado[0] == lista.versao and time.time() - guardado[1] < TTL_S:
            return list(guardado[2])
        de = _txt((lista.janela or ("", ""))[0])[:10]
        if not de:
            return []
        sel = oc.filtrar("criadas", {"nome": nome}, de, agora.strftime("%Y-%m-%d"), status=list(EXECUTADA))
    except Exception:            # noqa: BLE001 — sem a lista central (o PC, os testes do Nexus sem o clone): sem avisos
        log.debug("avisos: a lista central de OS não respondeu", exc_info=True)
        return []
    out = []
    for r in sel or []:
        fim = _quando(r.data_fim)
        executor = _txt(r.atribuido_a)
        if fim is None or agora - fim > timedelta(days=JANELA_DIAS) or _norm(executor) == meu:
            continue
        out.append({"id": f"E:{r.id}:{fim.strftime('%Y%m%d%H%M')}", "tipo": "execucao", "wid": r.id,
                    "folio": _txt(r.folio), "status": EXECUTADA.get(r.status_id, ""), "quando": fim,
                    "titulo": f"OS {_txt(r.folio)} concluída pelo técnico",
                    "detalhe": " · ".join(x for x in (executor, EXECUTADA.get(r.status_id, ""), _txt(r.descricao)[:70]) if x)})
    _CACHE[("exec", meu)] = (lista.versao, time.time(), list(out))
    return out


def solicitacoes(nome: str, linhas: list[dict], agora: datetime | None = None, cofre=None) -> list[dict]:
    """Os avisos `gerou_os` para `nome` nos últimos JANELA_DIAS (o código do nome, `codigo_do_nome`)."""
    meu = codigo_do_nome(nome)
    if not meu:
        return []
    agora = agora or datetime.now(_BRT)
    out = {}
    for l in linhas:
        if _txt(l.get("evento")) != "gerou_os" or _txt(l.get("destino_hmac")).lower() != meu:
            continue
        aid, q = _txt(l.get("aviso_id")), _quando(l.get("registrado_em"))
        if not AVISO_RE.fullmatch(aid) or q is None or agora - q > timedelta(days=JANELA_DIAS):
            continue
        dados = {}
        if cofre is not None and l.get("dados_cifrados"):
            try:
                dados = json.loads(cofre.decifrar(l["dados_cifrados"], _ctx(l)))
            except Exception:    # noqa: BLE001 — linha mexida ou chave trocada: fica o aviso, sem o nome
                dados = {}
        sol, folio = aid.partition(":")[2], _txt(l.get("folio"))
        try:
            wid = int(l.get("os_id")) if l.get("os_id") not in (None, "") else None
        except (TypeError, ValueError):
            wid = None
        out[aid] = {"id": aid, "tipo": "solicitacao", "wid": wid, "folio": folio, "status": "Em Processo", "quando": q,
                    "titulo": "Sua solicitação gerou uma OS",
                    "detalhe": " · ".join(x for x in (f"Solicitação {sol}", f"OS {folio}" if folio else "",
                                                       _txt(dados.get("aprovador"))) if x)}
    return list(out.values())


def lidos(linhas: list[dict], meu_hmac: str) -> set:
    """Os avisos que esta pessoa já marcou como lidos."""
    meu = _txt(meu_hmac).lower()
    if not meu:
        return set()
    return {_txt(l.get("aviso_id")) for l in linhas
            if _txt(l.get("evento")) == "leu" and _txt(l.get("pessoa_hmac")).lower() == meu}


def da_pessoa(nome: str, meu_hmac: str, linhas: list[dict], agora: datetime | None = None, cofre=None) -> list[dict]:
    """Os avisos NÃO lidos da pessoa, do mais novo para o mais velho."""
    ja = lidos(linhas, meu_hmac)
    todos = execucoes(nome, agora) + solicitacoes(nome, linhas, agora, cofre)
    return sorted((a for a in todos if a["id"] not in ja), key=lambda a: a["quando"], reverse=True)


def para_o_sino(usuario) -> list[dict]:
    """Os avisos não lidos de quem está na sessão, com a hora já escrita, para o sino. Sem o código da pessoa (a senha de
    administrador não diz quem é), nada."""
    u = usuario if isinstance(usuario, dict) else {}
    email = _txt(u.get("email")).lower()
    nome = _txt(u.get("nome"))
    if not email or not nome:
        return []
    try:
        cofre = ES._cofre()
    except ES.Recusada:
        cofre = None
    itens = da_pessoa(nome, _codigo(email), copia(), cofre=cofre)
    for a in itens:
        a["quando_txt"] = a["quando"].strftime("%d/%m %H:%M")
    return itens


# ── gravar ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def marcar_lidos(usuario, aviso_ids) -> int:
    """Grava o `leu` de cada aviso (os já lidos e os ids que não são de aviso ficam de fora). Quantos gravou."""
    u = usuario if isinstance(usuario, dict) else {}
    email = _txt(u.get("email")).lower()
    if not email:
        raise Recusada("Entre com o seu login (Microsoft ou Fracttal): a senha de administrador não diz quem é a pessoa")
    if not current_app.config.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    meu = _codigo(email)
    if not meu:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    ja = lidos(ler()["linhas"], meu)
    ids = [a for a in dict.fromkeys(_txt(x) for x in (aviso_ids or [])) if AVISO_RE.fullmatch(a) and a not in ja]
    novas = [_linha(a, "execucao" if a.startswith("E:") else "solicitacao", "leu", pessoa_hmac=meu)
             for a in ids[:MAX_POR_VEZ]]
    if novas:
        _gravar(novas)
    return len(novas)


def registrar_gerou_os(d: dict) -> dict | None:
    """O aviso "Sua solicitação gerou uma OS", na aprovação feita no OS Creator. `d`: {"solicitacao", "solicitante",
    "folio", "id_work_order", "aprovador", "aprovador_email"}. Sem o nome de quem pediu ou sem as chaves, não grava (e diz
    no log): o aviso nunca derruba a aprovação."""
    sol = re.sub(r"[^A-Za-z0-9_\-]", "", _txt(d.get("solicitacao")))[:40]
    destino = codigo_do_nome(d.get("solicitante"))
    if not sol or not destino or not current_app.config.get("GRIDCO_SQL_TOKEN"):
        log.info("avisos: a solicitação %s aprovada não virou aviso (sem quem pediu ou sem a chave do banco)", sol or "?")
        return None
    try:
        cofre = ES._cofre()
    except ES.Recusada:
        cofre = None
    try:
        wid = int(d.get("id_work_order")) if d.get("id_work_order") not in (None, "") else None
    except (TypeError, ValueError):
        wid = None
    aprovador_email = _txt(d.get("aprovador_email")).lower()
    linha = _linha(f"S:{sol}", "solicitacao", "gerou_os", os_id=wid, folio=d.get("folio"), destino_hmac=destino,
                   pessoa_hmac=_codigo(aprovador_email) if aprovador_email else "",
                   dados={"solicitante": _txt(d.get("solicitante")), "aprovador": _txt(d.get("aprovador"))}, cofre=cofre)
    _gravar([linha])
    return linha


def ao_aprovar(app):
    """O gancho que a ponte põe no `rotas_solic.AO_APROVAR`: grava o aviso por trás, no contexto do Nexus (a aprovação roda
    no app do clone), para a aprovação não esperar o banco."""
    def fn(d: dict) -> None:
        def rodar():
            with app.app_context():
                try:
                    registrar_gerou_os(d)
                except Exception:    # noqa: BLE001 — o aviso nunca derruba a aprovação; fica o log
                    app.logger.exception("avisos: o aviso da solicitação aprovada não foi gravado")
        threading.Thread(target=rodar, name="nexus-avisos-solicitacao", daemon=True).start()
    return fn
