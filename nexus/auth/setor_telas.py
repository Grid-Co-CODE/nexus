"""O que cada setor vê no Nexus (Base → Acessos, 12/10/2026).

Levi: "Agora que temos os setores separados gostaria de uma seção no BASE > ACESSOS onde eu possa controlar o que cada
pessoa de setor pode ver ao logar no Nexus. A que não tiver setor vai aparecer a mensagem 'Sem setor, fale com o
responsável'. E aí eu teria essas visões do menu onde eu marcaria o que cada setor pode enxergar! Criarei um setor chamado
'Administrador' onde será liberado todas as seções para essas contas! Exclua a parte de cadeiras já que os setores irão
substituir!"

As regras:
- O setor da pessoa é o da tela Base → Integração Fracttal (`cadastro/setores.py`): a última decisão de cada pessoa do
  Fracttal. A pessoa do login se acha pelo código do e-mail (`pessoa_hmac`, com a NEXUS_PESSOA_HMAC), o mesmo que a
  decisão grava. Nome e e-mail nunca vão ao banco (regra 8 da governança).
- Administrador do Nexus (a NEXUS_ADMINS, a lista de Administradores desta tela e a senha de administrador) vê tudo,
  com ou sem setor: é quem configura, e não pode ficar trancado fora. Setor NÃO dá administrador (Levi, 12/10/2026:
  "não acho legal deixar como setores pois eu por exemplo sou da performance mas também sou administrador"): um setor
  chamado "Administrador" é um setor como os outros, e o administrador que tem setor segue vendo tudo.
- Os setores veem só as telas marcadas. Tela nunca marcada fica fechada (o setor novo nasce sem nada). O Início
  é de todos, com os cartões das torres liberadas. Sem setor (ou com o setor excluído): só a mensagem.
- O portão vale para as páginas e os dados de cada torre (`/t/<torre>/...`): o endereço que é de uma tela segue a marca
  dela; o resto da torre (os dados e as sub-rotas) abre para quem tem ao menos uma tela da torre. O OS Creator servido
  em `/os/` é o conteúdo da torre OS (as telas `/t/os/*` abrem nele): abre para quem tem ao menos uma tela dela. As ações
  do Nexus em `/os/_nexus/` (aprovar OS, decidir PT, o cartão da OS) são das telas do Campo e do HSEQ e seguem a régua de
  cada uma. As telas da plataforma dentro da moldura seguem o login de lá: o que fecha aqui é a tela do Nexus que as abre.

O dado: livro `nexus_setor_telas · fato_decisao_tela_setor`, no catálogo (`nexus/dados/catalogo.py`, fato
`decisao_tela_setor`). Grão: 1 linha = 1 decisão de liberar ou fechar 1 tela do menu (`torre/tela`) para 1 setor. Só
acrescenta: o que vale é a última decisão de cada setor × tela. Quem decidiu vai em `decidida_por_hmac` e no log.
Gravar troca a aba inteira (relida do banco antes, nunca a cópia de 1 minuto) e o `livros.publicar` confere a contagem.

Ligado fora dos testes: `NEXUS_ACESSO_POR_SETOR` (padrão ligado; com TESTING, desligado, para os testes de cada tela não
dependerem do banco de setores). `NEXUS_ACESSO_POR_SETOR=0` desliga numa máquina: todos veem tudo, como antes. Sem a
NEXUS_PESSOA_HMAC também fica desligado: sem ela não há como achar a pessoa do login nas decisões de setor, e ligar
trancaria todo mundo fora. A tela Acessos diz qual é o caso.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import current_app, has_request_context, jsonify, render_template, request, session

from ..cadastro import setores as S
from ..dados import fatos as D
from ..dados import livros

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO = "nexus_setor_telas", "Nexus · telas de cada setor"
ABA = "fato_decisao_tela_setor"
CAB = ("decidida_em", "data_id", "setor_id", "tela", "liberada", "decidida_por_hmac", "origem")
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}
# o que abre sem setor: entrar e sair, o tema, a saúde e os arquivos da página
LIVRES = frozenset({"auth.entrar", "auth.sair", "casca.tema", "casca.saude", "static"})
# Telas que mudaram de endereço: a decisão gravada com o nome antigo vale para o novo (a mais nova de cada setor × tela
# ganha, pela hora, como sempre). 13/10/2026: o Criador de relatório e o Relatório semanal saíram da Performance para
# Relatórios → Central de emissão (Levi: "Sai da parte de Performance!"); quem já os via continua vendo.
RENOMEADAS = {"performance/relatorio": "relatorios/relatorio",
              "performance/relatorio-semanal": "relatorios/relatorio-semanal"}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def estado(cfg) -> str:
    """"ligado"; "desligado" (NEXUS_ACESSO_POR_SETOR=0, ou teste que não pediu); "sem_chave" (falta a NEXUS_PESSOA_HMAC)."""
    v = cfg.get("NEXUS_ACESSO_POR_SETOR")
    pedido = (not cfg.get("TESTING")) if v is None else \
        str(v).strip().lower() not in ("", "0", "false", "nao", "não", "desligado")
    if not pedido:
        return "desligado"
    return "ligado" if cfg.get("NEXUS_PESSOA_HMAC") else "sem_chave"


def ligado(cfg) -> bool:
    return estado(cfg) == "ligado"


def chave(torre_id: str, tela_id: str) -> str:
    return f"{torre_id}/{tela_id}"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _decisao(x: dict) -> dict | None:
    sid, tela = D._id(x.get("setor_id")), D._txt(x.get("tela"))
    if not sid or not tela:
        return None
    return {"decidida_em": D._txt(x.get("decidida_em")), "data_id": D._id(x.get("data_id")), "setor_id": sid,
            "tela": tela, "liberada": D._txt(x.get("liberada")).lower() == "sim",
            "decidida_por_hmac": D._txt(x.get("decidida_por_hmac")), "origem": D._txt(x.get("origem"))}


def _ler_banco(base: str, sessao) -> list[dict]:
    a = livros.abas(base, sessao, LIVRO)
    return [d for d in (_decisao(x) for x in livros._linhas(base, sessao, a[ABA])) if d] if ABA in a else []


def ler(base: str, sessao, forcar: bool = False) -> dict:
    """{"decisoes", "lido_em", "erro"}: o livro, guardado por 1 minuto. Leitura que falha devolve a última boa com o erro;
    sem nenhuma, vazio com o erro (a tela não deixa gravar sem saber o que há no banco)."""
    c = _CACHE.get("livro")
    if c and not forcar and time.time() - c["lido_em"] < TTL_S:
        return c
    try:
        decisoes = _ler_banco(base, sessao)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if c:
            return dict(c, erro=erro, velha=True)
        return {"decisoes": [], "lido_em": None, "erro": erro}
    c = {"decisoes": decisoes, "lido_em": time.time(), "erro": ""}
    _CACHE["livro"] = c
    return c


def vigentes(decisoes: list[dict]) -> dict[int, set[str]]:
    """{setor_id: {telas liberadas}} pela última decisão de cada setor × tela (pela hora; empate fica na ordem do livro)."""
    ultima = {}
    for d in sorted(decisoes or [], key=lambda x: x["decidida_em"]):
        ultima[(d["setor_id"], RENOMEADAS.get(d["tela"], d["tela"]))] = d["liberada"]
    out: dict[int, set[str]] = {}
    for (sid, tela), lib in ultima.items():
        if lib:
            out.setdefault(sid, set()).add(tela)
    return out


def gravar(setor_id: int, marcadas, todas, cfg, base, sessao, quem_email: str = "") -> dict:
    """Grava o que mudou na matriz de um setor: para cada tela de `todas`, liberada se está em `marcadas`. Só a tela que
    mudou ganha linha (abrir e salvar sem mexer não grava nada). {"gravadas", "liberadas"}."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    marcadas, todas = set(marcadas), set(todas)
    if not marcadas <= todas:
        raise Recusada("Tela desconhecida na matriz: nada foi gravado.")
    quem = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), quem_email) or ""
    with _TRAVA:
        try:
            decisoes = _ler_banco(base, sessao)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler as telas dos setores no banco ({type(ex).__name__}): nada foi gravado, "
                           "para não apagar o que já está lá.") from ex
        tem = vigentes(decisoes).get(setor_id, set())
        agora = _agora()
        novas = [{"decidida_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "setor_id": setor_id, "tela": t,
                  "liberada": t in marcadas, "decidida_por_hmac": quem, "origem": "tela"}
                 for t in sorted(todas) if (t in marcadas) != (t in tem)]
        if novas:
            decisoes = decisoes + novas
            vazio = (lambda v: None if v in ("", None) else v)
            linhas = [[d["decidida_em"], d["data_id"], d["setor_id"], d["tela"], "sim" if d["liberada"] else "nao",
                       vazio(d["decidida_por_hmac"]), vazio(d["origem"])] for d in decisoes]
            livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), linhas)}, base=base, token=token, sessao=sessao)
        _CACHE["livro"] = {"decisoes": decisoes, "lido_em": time.time(), "erro": ""}
    log.info("Telas por setor: %s mudança(s) no setor %s, por %s.", len(novas), setor_id,
             quem_email or "senha de administrador")
    return {"gravadas": len(novas), "liberadas": len(marcadas)}


# ── a leitura no caminho de cada clique: nunca prende a pessoa no banco ─────────────────────────────────────────────
# O portão lê os setores e as telas a cada clique de toda sessão do Fracttal (e o `_admin_em_dia` também). Os livros
# esperam até 60 s por pedido, e a leitura que falha não renova a cópia: com o banco lento, TODO clique ficaria preso
# até minutos, inclusive o do administrador. Então: cópia fresca, ela; cópia vencida, ela na hora e a releitura em
# segundo plano (uma de cada vez); sem cópia, lê agora com prazo curto, e a falha faz os cliques dos próximos ESPERA_S
# responderem "não consegui ler" sem ir ao banco.
PRAZO_S = 8
ESPERA_S = 30
_FUNDO: dict = {}
_TRAVA_FUNDO = threading.Lock()


class _Curta:
    """A sessão do banco com prazo curto: o clique espera no máximo PRAZO_S por pedido."""

    def __init__(self, sessao):
        self._s = sessao

    def get(self, *a, **k):
        k["timeout"] = min(float(k.get("timeout") or PRAZO_S), PRAZO_S)
        return self._s.get(*a, **k)


def limpar() -> None:
    """Esquece as cópias e as falhas (os testes; nada no servidor chama)."""
    _CACHE.clear()
    with _TRAVA_FUNDO:
        _FUNDO.clear()


def _em_fundo(chave: str, ler_de_novo) -> None:
    with _TRAVA_FUNDO:
        f = _FUNDO.setdefault(chave, {"rodando": False, "tentou_em": 0.0, "falhou_em": 0.0})
        if f["rodando"] or time.time() - f["tentou_em"] < ESPERA_S:
            return
        f["rodando"], f["tentou_em"] = True, time.time()

    def rodar():
        try:
            ler_de_novo()
        except Exception as e:   # noqa: BLE001 — a cópia velha segue valendo
            log.warning("Telas por setor: a releitura de %s em segundo plano falhou (%s).", chave, type(e).__name__)
        finally:
            with _TRAVA_FUNDO:
                _FUNDO[chave]["rodando"] = False
    threading.Thread(target=rodar, name=f"nexus-setor-{chave}", daemon=True).start()


def _no_clique(chave: str, cache: dict, ttl: float, ler_agora, ler_de_novo) -> dict:
    c = cache.get("livro")
    if c and c.get("lido_em"):
        if time.time() - c["lido_em"] >= ttl:
            _em_fundo(chave, ler_de_novo)
        return c
    with _TRAVA_FUNDO:
        f = _FUNDO.setdefault(chave, {"rodando": False, "tentou_em": 0.0, "falhou_em": 0.0})
        if time.time() - f["falhou_em"] < ESPERA_S:
            return {"setores": [], "decisoes": [], "lido_em": None, "erro": "o banco não respondeu há pouco"}
    r = ler_agora()
    if r.get("erro") and not r.get("lido_em"):
        with _TRAVA_FUNDO:
            _FUNDO[chave]["falhou_em"] = time.time()
    return r


def _setores_no_clique(base: str, sessao) -> dict:
    return _no_clique("setores", S._CACHE, S.TTL_S, lambda: S.ler(base, _Curta(sessao), forcar=True),
                      lambda: S.ler(base, sessao, forcar=True))


def _telas_no_clique(base: str, sessao) -> dict:
    return _no_clique("telas", _CACHE, TTL_S, lambda: ler(base, _Curta(sessao), forcar=True),
                      lambda: ler(base, sessao, forcar=True))


def escolhas_de_dono() -> dict[str, int | None]:
    """{torre/tela: setor_id ou None} dos relatórios cujo setor dono o administrador escolheu na Central de emissão
    (14/10/2026, `dono_relatorio.py`); o que não está aqui segue o `Tela.do_setor` do código. No caminho do clique, com a
    mesma cópia de 1 minuto e releitura em segundo plano das telas por setor; banco fora = só o padrão do código."""
    from . import dono_relatorio as DR
    try:
        base, sessao = _banco()
        d = _no_clique("donos", DR._CACHE, DR.TTL_S, lambda: DR.ler(base, _Curta(sessao), forcar=True),
                       lambda: DR.ler(base, sessao, forcar=True))
    except Exception:            # noqa: BLE001 — sem o endereço do banco (os testes de cada tela), por exemplo
        return {}
    return DR.vigentes(d.get("decisoes") or [])


# ── a pessoa do login ───────────────────────────────────────────────────────────────────────────────────────────────
def _banco():
    from ..campo import visao
    return visao._base(), visao._sessao()


def setor_de_cada_codigo(decisoes: list[dict]) -> dict[str, int | None]:
    """{pessoa_hmac: setor_id ou None} pela última decisão de cada pessoa do Fracttal. O mesmo código em duas pessoas do
    Fracttal (o mesmo e-mail em dois cadastros) fica com a decisão mais nova."""
    ultima = {}
    for d in sorted(decisoes or [], key=lambda x: x["decidida_em"]):
        ultima[d["fracttal_id"]] = d
    out: dict[str, int | None] = {}
    for d in sorted(ultima.values(), key=lambda x: x["decidida_em"]):
        if d.get("pessoa_hmac"):
            out[d["pessoa_hmac"]] = d["setor_id"]
    return out


def setor_da_pessoa(cfg, email: str, base: str, sessao) -> dict | None:
    """{"id", "nome"} do setor de agora da pessoa do login, ou None: sem setor, setor excluído, ou sem a
    NEXUS_PESSOA_HMAC (sem ela não há como achar a pessoa nas decisões). O banco nunca lido levanta erro: "não consegui
    ler" não é "sem setor"."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not codigo:
        return None
    st = _setores_no_clique(base, sessao)
    if st.get("erro") and not st.get("lido_em"):
        raise RuntimeError(f"setores ilegíveis no banco: {st['erro']}")
    sid = setor_de_cada_codigo(st["decisoes"]).get(codigo)
    setor = next((s for s in S.ativos(st["setores"]) if s["setor_id"] == sid), None) if sid else None
    if not setor:
        return None
    return {"id": setor["setor_id"], "nome": setor["nome"]}


def _email() -> str:
    u = session.get("usuario")
    return str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""


def acesso() -> dict:
    """O que a sessão de agora vê, uma vez por pedido: {"tudo": bool, "telas": set, "setor": dict | None, "erro": str}.
    Administrador (de qualquer jeito) e o portão desligado: tudo. Fica guardado no próprio pedido, não no `g`: o `g` é
    do contexto da aplicação, que um contexto já aberto (o de um teste, um job) empresta a vários pedidos, e o acesso de
    uma pessoa vazaria para o pedido da outra."""
    if not has_request_context():
        return {"tudo": True, "telas": set(), "setor": None, "erro": ""}
    guardado = getattr(request, "_nexus_acesso", None)
    if guardado is not None:
        return guardado
    cfg = current_app.config
    r = {"tudo": True, "telas": set(), "setor": None, "erro": ""}
    if ligado(cfg) and session.get("logado") and not session.get("admin"):
        try:
            base, sessao = _banco()
            setor = setor_da_pessoa(cfg, _email(), base, sessao)
            if setor:
                d = _telas_no_clique(base, sessao)
                # erro só quando nunca houve leitura boa: com a cópia velha, vale ela
                # as marcas do setor, as telas que são DELE (Tela.do_setor) e a de fora de cada uma
                telas = vigentes(d["decisoes"]).get(setor["id"], set()) | das_do_setor(setor)
                r = {"tudo": False, "telas": com_as_de_fora(telas), "setor": setor,
                     "erro": d["erro"] if not d.get("lido_em") else ""}
            else:
                r = {"tudo": False, "telas": set(), "setor": None, "erro": ""}
        except Exception as e:   # noqa: BLE001 — sem saber o setor, fecha (a mensagem diz que é leitura, não falta de setor)
            r = {"tudo": False, "telas": set(), "setor": None, "erro": type(e).__name__}
    elif session.get("logado") and session.get("admin"):
        try:
            if ligado(cfg) and _email():
                r["setor"] = setor_da_pessoa(cfg, _email(), *_banco())
        except Exception:        # noqa: BLE001 — só o nome no topo
            pass
    request._nexus_acesso = r
    return r


def _sem_acento(texto) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(c) != "Mn").strip().lower()


def donos_do_codigo(tela) -> tuple[str, ...]:
    """Os nomes dos setores donos de uma tela no código (`Tela.do_setor`: um nome ou uma tupla deles; 16/10/2026, o
    Gerar e o Quadro do PCM são do PCM e dos Responsáveis UFV)."""
    d = tela.do_setor
    return tuple(x for x in (d if isinstance(d, (tuple, list)) else (d,)) if x)


def das_do_setor(setor) -> set[str]:
    """As telas que são DO setor: quem é dele as vê sem marcar (13/10/2026, Levi, sobre os relatórios da Central de
    emissão: "Potência ativa faz parte da performance!" e "Esses dois são do setor performance"). Setor de outro nome
    não ganha nada; a marca em Base → Acessos segue valendo para ele.
    O dono é o que o administrador escolheu na Central (14/10/2026, `escolhas_de_dono`, pelo setor_id: o setor renomeado
    continua dono) e, sem escolha, o `Tela.do_setor` do código, pelo nome (sem acento nem caixa). `setor` é o dict
    {"id", "nome"} da pessoa ou só o nome (aí a escolha casa pelo nome de agora do setor escolhido)."""
    nome = setor.get("nome") if isinstance(setor, dict) else setor
    sid = setor.get("id") if isinstance(setor, dict) else None
    alvo = _sem_acento(nome)
    if not alvo and sid is None:
        return set()
    escolhas = escolhas_de_dono()
    nomes: dict = {}
    if escolhas and sid is None:
        try:
            st = _setores_no_clique(*_banco())
            nomes = {s["setor_id"]: s["nome"] for s in S.ativos(st.get("setores") or [])}
        except Exception:        # noqa: BLE001 — sem os nomes, a escolha não casa por nome
            nomes = {}
    out = set()
    for t in current_app.extensions.get("nexus_torres", []):
        for s in t.telas:
            k = chave(t.id, s.id)
            if k in escolhas:
                dono = escolhas[k]
                if dono is not None and (dono == sid or (sid is None and _sem_acento(nomes.get(dono)) == alvo)):
                    out.add(k)
            elif alvo and any(_sem_acento(d) == alvo for d in donos_do_codigo(s)):
                out.add(k)
    return out


def dono_de(torre_id: str, tela, escolhas: dict, setores: list[dict]) -> dict:
    """O dono de agora de um relatório, para a Central: {"setor_id" (None = nenhum), "nome", "escolhido" (a escolha da
    Central) ou False (o padrão do código, pelo nome)}. `setores` = os ativos ({setor_id, nome})."""
    k = chave(torre_id, tela.id)
    if k in escolhas:
        sid = escolhas[k]
        nome = next((s["nome"] for s in setores if s["setor_id"] == sid), "setor excluído" if sid is not None else "")
        return {"setor_id": sid, "nome": nome, "escolhido": True}
    primeiro = (donos_do_codigo(tela) or ("",))[0]          # a Central mostra um dono: o primeiro do código
    alvo = _sem_acento(primeiro)
    s = next((s for s in setores if alvo and _sem_acento(s["nome"]) == alvo), None)
    return {"setor_id": s["setor_id"] if s else None, "nome": s["nome"] if s else primeiro,
            "escolhido": False}


def com_as_de_fora(telas: set[str]) -> set[str]:
    """As telas liberadas mais a de fora de cada uma (`Tela.dentro_de`, 13/10/2026): quem tem um relatório liberado vê a
    Central de emissão, que é por onde ele se abre, sem precisar marcá-la."""
    torres = {t.id: t for t in current_app.extensions.get("nexus_torres", [])}
    out = set(telas)
    for k in telas:
        torre_id, _, tela_id = k.partition("/")
        decl = torres[torre_id].tela(tela_id) if torre_id in torres else None
        if decl and decl.dentro_de:
            out.add(chave(torre_id, decl.dentro_de))
    return out


def liberadas_do_menu() -> set[str] | None:
    """O que o menu mostra: None = tudo; senão o conjunto de `torre/tela` liberadas."""
    a = acesso()
    return None if a["tudo"] else set(a["telas"])


def _tela_do_caminho(caminho: str):
    """(torre_id, chave da tela ou None) de um caminho `/t/<torre>/...`; (None, None) fora das torres. A tela é a de id
    mais longo que casa (o "clima/mapa" da Performance tem barra no id)."""
    if not caminho.startswith("/t/"):
        return None, None
    partes = caminho[3:].split("/", 1)
    torre_id = partes[0]
    resto = partes[1] if len(partes) > 1 else ""
    torre = next((t for t in current_app.extensions.get("nexus_torres", []) if t.id == torre_id), None)
    if torre is None:
        return torre_id, None
    achadas = [s.id for s in torre.telas if resto == s.id or resto.startswith(s.id + "/")]
    return torre_id, (chave(torre_id, max(achadas, key=len)) if achadas else None)


def pode(caminho: str, telas: set[str]) -> bool:
    """O caminho abre para quem tem estas telas? A tela segue a marca dela; o resto da torre (dados, sub-rotas), quem tem
    ao menos uma tela da torre; o OS Creator em /os/ (fora as ações /os/_nexus/), quem tem uma tela da torre OS; o
    resto, sim."""
    if caminho.startswith("/os/") and not caminho.startswith("/os/_nexus/"):
        return any(t.startswith("os/") for t in telas)
    torre_id, tela = _tela_do_caminho(caminho)
    if torre_id is None:
        return True
    if tela:
        return tela in telas
    return any(t.startswith(torre_id + "/") for t in telas)


def _quer_pagina() -> bool:
    from . import quer_pagina
    return quer_pagina()


def portao():
    """O portão por setor, depois do login (`instalar_portao`): None = segue; senão a resposta."""
    cfg = current_app.config
    if not ligado(cfg) or not session.get("logado") or session.get("admin"):
        return None
    if request.endpoint in LIVRES or (request.endpoint or "").endswith(".static"):
        return None
    a = acesso()
    if a["tudo"]:
        return None
    if not a["setor"]:
        if not _quer_pagina():
            return jsonify(ok=False, erro="Sem setor, fale com o responsável."), 403
        return render_template("sem_setor.html", leitura=bool(a["erro"])), 403
    # as telas do setor esquentam por trás (pre_carga.py: no 1º pedido depois do login e a cada 2 min de uso)
    from . import pre_carga
    pre_carga.lembrar(a["telas"])
    if pode(request.path, a["telas"]):
        return None
    # sem ler as telas do setor no banco (nunca leu), a mensagem é de leitura, não de tela fechada
    leitura = bool(a["erro"])
    if not _quer_pagina():
        return jsonify(ok=False, erro="Não consegui ler as telas do seu setor agora." if leitura
                       else "Esta tela não está liberada para o seu setor."), 403
    return render_template("sem_setor.html", bloqueada=not leitura, leitura=leitura, setor=a["setor"]), 403
