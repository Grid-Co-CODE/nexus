"""O De-para das fontes dentro de Base > Equipamentos das usinas (13/11/2026).

Levi, 13/11/2026: "o equipamentos das usinas tem que ser junto do de para de equipamentos, pois um complementa o outro";
"no de para do equipamento, tem que ser possível editar o equipamento da usina"; "Deixa a visualização dos dois
parecida". A prévia aprovada mora em `docs/mockups/equipamentos-e-depara` (repositório da plataforma).

O de-para é da PLATAFORMA (o livro `nexus_depara`, a tela `/admin/de-para`): aqui só se LÊ, pela ponte só de leitura
(`X-Nexus-Leitura`, `nexus/performance/ponte.py`), o diagnóstico (`/api/admin/de-para`) e a usina aberta
(`/api/admin/de-para/usina`). A plataforma deixa a chave ler só esses dois caminhos exatos (`leitura_nexus._GET_EXATO`) e
não abre a API PV em pedido do Nexus: o que a fonte "manda hoje" é o da tabela do ciclo dela. Decidir um par grava no
livro da plataforma: pelo editor dela numa janela por cima ("Ligar a…", pela porta única) ou, desde 17/11/2026, pela
coluna Equipamento Supervisório da tabela dos inversores, que manda o `/api/admin/de-para/decidir` do navegador com o
passe da porta única (`static/eq-ligacao.js`; por isso os pares levam os `alvos`). A ponte segue só de leitura.

Como a linha do diagnóstico chega à usina do Nexus: a `usina` dela é a chave do cadastro (a "Usina Supervisório"), e a
estrutura liga cada chave a uma usina do Registro mestre. Pelo `norm` (sem acento, caixa e espaços repetidos: o cadastro
escreve "Assis Chateaubriand  Skid 1 (79)" com dois espaços). A linha sem usina no Nexus fica em `sem_usina`.

Funções puras (sem Flask) para o teste; só `_get` fala com a rede, e por `ponte.enviar` (os testes a trocam).
"""
import threading
import time

from . import estrutura_usina as E

VALIDADE_S = 120         # o diagnóstico da plataforma vem do cache dela (o ciclo de 30 min): 2 min aqui bastam
TEMPO_S = 20             # a ponte espera até 150 s (o drill da API PV); a página de Equipamentos não fica presa nisso
_CACHE: dict = {}
_TRAVA = threading.Lock()

# A cor da luz de cada linha: o `pior` da plataforma (crítico, atenção, informação, ok) no semáforo do Nexus
LUZ = {"critico": "critico", "atencao": "alerta", "info": "ok", "ok": "ok"}
_PESO = {"critico": 0, "alerta": 1, "ok": 2}
# Como o inversor da fonte chega ao do cadastro (o `origem` da plataforma): o fio da tela
MODO = {"nome": "ok", "codigo": "ok", "tela": "decidido", "ordem": "ordem", "sem": "sem"}


def limpar() -> None:
    with _TRAVA:
        _CACHE.clear()


def _get(cfg, caminho: str, query=()) -> tuple:
    """(status, json ou None, erro). Só a resposta com `X-Nexus-Leitura-Ok` vale (falha fechada, como a ponte)."""
    from ..performance import ponte
    url, token = cfg.get("NEXUS_PLATAFORMA_URL"), cfg.get("NEXUS_PLATAFORMA_TOKEN")
    if not url or not token:
        return 0, None, "a ponte com a plataforma não está ligada neste servidor"
    try:
        pedido = ponte.montar_pedido(url, token, "GET", caminho, list(query), None, None)
        pedido["timeout"] = TEMPO_S
        r = ponte.enviar(**pedido)
    except ponte.Ocupada:
        return 0, None, "a ponte com a plataforma está ocupada: tente de novo em instantes"
    except Exception as ex:      # noqa: BLE001 — rede, tempo-limite: a tela diz, nada se inventa
        return 0, None, f"a plataforma não respondeu ({type(ex).__name__})"
    if {str(k).lower(): v for k, v in r.headers.items()}.get("x-nexus-leitura-ok") != "1":
        return r.status_code, None, f"a plataforma não confirmou a leitura ({r.status_code})"
    try:
        j = r.json()
    except ValueError:
        return r.status_code, None, f"resposta inesperada da plataforma ({r.status_code})"
    if r.status_code != 200:
        msg = j.get("error") if isinstance(j, dict) else ""
        return r.status_code, j if isinstance(j, dict) else None, str(msg or f"a plataforma respondeu {r.status_code}")
    return 200, j, ""


def _guardado(chave, ler, forcar: bool):
    with _TRAVA:
        ent = _CACHE.get(chave)
        if ent and not forcar and time.monotonic() - ent[0] < VALIDADE_S:
            return ent[1]
    dados = ler()
    with _TRAVA:
        _CACHE[chave] = (time.monotonic(), dados)
    return dados


def ler_lista(cfg, forcar: bool = False) -> dict:
    """{"fontes": [{id, nome, lida, usinas: [linhas]}], "contagem", "erro", "lido_em"} do diagnóstico da plataforma."""
    def ler():
        _st, j, erro = _get(cfg, "/api/admin/de-para")
        if erro or not isinstance(j, dict):
            return {"fontes": [], "contagem": {}, "erro": erro or "resposta vazia", "lido_em": time.time()}
        return {"fontes": [f for f in j.get("fontes") or [] if isinstance(f, dict)], "contagem": j.get("contagem") or {},
                "erro": "", "lido_em": time.time()}
    return _guardado("lista", ler, forcar)


def ler_usina(cfg, fonte: str, id_, forcar: bool = False) -> dict:
    """A usina de uma fonte como o editor da plataforma a vê, sem o `cadastro_usinas` (a lista do cadastro inteiro, que
    esta tela não usa). {"erro": texto} quando a plataforma recusa (a fonte que liga pelo nome responde 400: "corrija no
    cadastro")."""
    def ler():
        _st, j, erro = _get(cfg, "/api/admin/de-para/usina", [("fonte", fonte), ("id", str(id_))])
        if erro or not isinstance(j, dict):
            return {"erro": erro or "resposta vazia"}
        return {k: v for k, v in j.items() if k not in ("cadastro_usinas", "decisoes", "sugestao")}
    return _guardado(("usina", fonte, str(id_)), ler, forcar)


def _dono_das_chaves(est: dict) -> dict:
    """{norm(nome): (usina_id, supervisorio_id, chave)} das chaves ligadas (as excluídas não contam): pela chave e, sem
    ela, pelo nome de exibição gravado no Nexus quando ele é de UMA chave só. A linha da API PV escreve o nome de
    exibição da plataforma, não a chave: medido em 13/11/2026, das 179 linhas do diagnóstico 155 casam pela chave
    ("Céu Azul III (104)"), 18 só pela exibição ("Alto Paraná 1", chave "Alto Parana 1 (40)") e 6 não estão ligadas a
    usina nenhuma do Nexus (a chave delas está na aba, sem ligação)."""
    vivos = [s for s in est.get("supervisorios") or [] if not s.get("excluido")]
    exib = {}
    for s in vivos:
        n = E.norm(s.get("usina_exibicao"))
        if n:
            exib.setdefault(n, []).append(s)
    out = {n: (v[0]["usina_id"], v[0]["supervisorio_id"], v[0]["usina_supervisorio"]) for n, v in exib.items()
           if len(v) == 1}
    out.update({E.norm(s["usina_supervisorio"]): (s["usina_id"], s["supervisorio_id"], s["usina_supervisorio"])
                for s in vivos})          # a chave vence a exibição
    return out


def por_usina(lista: dict, est: dict) -> tuple:
    """({usina_id: [linhas]}, [linhas sem usina no Nexus]). Cada linha leva o nome da fonte (`fonte_nome`), a luz e, se
    achou, o `supervisorio_id`."""
    dono = _dono_das_chaves(est)
    out, sem = {}, []
    for f in lista.get("fontes") or []:
        for u in f.get("usinas") or []:
            if not isinstance(u, dict):
                continue
            ln = dict(u, fonte_nome=f.get("nome") or f.get("id"), luz=LUZ.get(u.get("pior"), "ok"))
            d = dono.get(E.norm(u.get("usina")))
            if d:
                ln.update(usina_id=d[0], supervisorio_id=d[1], chave=d[2])
                out.setdefault(d[0], []).append(ln)
            else:
                sem.append(ln)
    for v in out.values():
        v.sort(key=lambda x: (_PESO[x["luz"]], str(x.get("fonte_nome")), str(x.get("usina"))))
    sem.sort(key=lambda x: (_PESO[x["luz"]], str(x.get("fonte_nome")), str(x.get("usina"))))
    return out, sem


def luz(linhas) -> str | None:
    """A pior luz das fontes de uma usina; None = nenhuma fonte chega nela (a luz fica apagada, nunca verde)."""
    if not linhas:
        return None
    return min((x["luz"] for x in linhas), key=lambda c: _PESO[c])


def _inversor_do_nexus(alvo: dict, invs: list) -> dict | None:
    """O inversor da estrutura do Nexus que é o alvo do cadastro da plataforma: o nome no supervisório (o `nome` do
    alvo, "INVERSOR01") e, sem ele, o nome do equipamento (a `exibicao`, "Inversor 3.1")."""
    n, ex = E.norm(alvo.get("nome")), E.norm(alvo.get("exibicao"))
    for i in invs:
        if n and E.norm(i.get("equipamento_supervisorio")) == n:
            return i
    for i in invs:
        if E.norm(i.get("nome")) in {x for x in (n, ex) if x}:
            return i
    return None


def pares(det: dict, invs_nexus: list) -> dict:
    """Os pares de uma fonte numa usina: {"linhas": [{fonte, id, repetido, modo, alvo, inversor_id}], "sobra": [{alvo,
    inversor_id}]}. `det` = a usina da plataforma (`inversores` que a fonte manda, `alvos` do cadastro); `invs_nexus` = os
    inversores da estrutura do Nexus nesta chave (para o lápis abrir o certo). O alvo é o do CADASTRO que a plataforma lê
    (a aba, ou a visão do Nexus na chave "no lugar da aba"); o inversor do Nexus vai junto só quando casa."""
    alvos = [a for a in det.get("alvos") or [] if isinstance(a, dict)]
    por_nome = {}
    for a in alvos:
        por_nome.setdefault(str(a.get("nome") or ""), a)
    # o rótulo é o nome que a FONTE dá ao inversor: o da API (`nome_api`) e, sem ele, o do código (`codigo`: no
    # scadaGridco, o nome do equipamento, "Inversor 1.6"), nunca o decidido na tela (o `nome` é o do cadastro). Na
    # usina do scadaGridco ligada pela tabela dos inversores (17/11/2026), o lado da fonte passava a repetir o cadastro
    rot = [str(i.get("nome_api") or i.get("codigo") or i.get("nome") or i.get("id") or "")
           for i in det.get("inversores") or []]
    vezes = {r: rot.count(r) for r in rot}
    usados, linhas = set(), []
    for i, r in zip(det.get("inversores") or [], rot):
        alvo = por_nome.get(str(i.get("nome") or "")) if i.get("nome") else None
        modo = MODO.get(i.get("origem"), "ok") if alvo else "sem"
        if alvo:
            usados.add(id(alvo))
        inv = _inversor_do_nexus(alvo, invs_nexus) if alvo else None
        linhas.append({"fonte": r, "id": str(i.get("id") or ""), "repetido": vezes.get(r, 0) > 1, "modo": modo,
                       "na_fonte_hoje": bool(i.get("na_fonte_hoje")),
                       "alvo": {"nome": alvo.get("nome"), "exibicao": alvo.get("exibicao"), "esp": alvo.get("esp")}
                       if alvo else None, "inversor_id": inv["id"] if inv else None})
    # sem nenhum inversor da fonte (a plataforma não tem a lista dela: a tabela do ciclo não tem a usina e o Nexus não
    # abre a API PV), o cadastro inteiro sobraria como "não chega da fonte", e isso não se sabe: vai como sem leitura
    sem_leitura = not linhas
    sobra = []
    for a in alvos:
        if id(a) in usados:
            continue
        inv = _inversor_do_nexus(a, invs_nexus)
        sobra.append({"alvo": {"nome": a.get("nome"), "exibicao": a.get("exibicao"), "esp": a.get("esp")},
                      "inversor_id": inv["id"] if inv else None, "sem_leitura": sem_leitura})
    # os inversores do cadastro que a PLATAFORMA lê (a aba, ou a visão do Nexus na chave no lugar da aba), na ordem dela:
    # a tabela dos inversores liga cada um ao inversor da fonte (17/11/2026), e o `nome` é o valor que o
    # `/api/admin/de-para/decidir` aceita (na API PV o nome no supervisório, "INVERSOR01"; no scadaGridco o nome do
    # equipamento, "Inversor 2.1"). Inversor do Nexus que não está aqui a plataforma não conhece: não se liga
    return {"linhas": linhas, "sobra": sobra, "sem_leitura": sem_leitura,
            "alvos": [{"nome": a.get("nome"), "exibicao": a.get("exibicao"), "esp": a.get("esp")} for a in alvos]}


def cartoes(cfg, linhas: list, est_usina: dict, forcar: bool = False) -> list:
    """Um cartão por fonte que chega na usina aberta: a linha do diagnóstico e, na fonte que a plataforma edita por
    inversor, os pares. `est_usina` = `estrutura_usina.da_usina` da usina."""
    sid_chave = {s["supervisorio_id"]: s for s in est_usina.get("supervisorios") or []}
    out = []
    for ln in linhas:
        ch = sid_chave.get(ln.get("supervisorio_id")) or {}
        invs = [i for i in est_usina.get("inversores") or [] if i.get("supervisorio_id") == ln.get("supervisorio_id")]
        invs = [{"id": i["inversor_id"], "nome": i["nome"], "equipamento_supervisorio": i["equipamento_supervisorio"]}
                for i in invs]
        c = {"fonte": ln.get("fonte"), "fonte_nome": ln.get("fonte_nome"), "plant_id": ln.get("plant_id"),
             "usina": ln.get("usina"), "chave": ln.get("chave"), "supervisorio_id": ln.get("supervisorio_id"),
             "no_lugar_da_aba": bool(ch.get("substitui_aba")), "luz": ln["luz"], "liga": ln.get("liga"),
             "nomes_inversor": ln.get("nomes_inversor"), "inv_fonte": ln.get("inv_fonte"), "inv_esp": ln.get("inv_esp"),
             "str_esp": ln.get("str_esp"), "alertas": ln.get("alertas") or [], "edita_inversor": bool(ln.get("edita_inversor")),
             "linhas": [], "sobra": [], "alvos": [], "sem_leitura": False, "erro": "", "nota": "", "provisorio": ""}
        if c["edita_inversor"] and ln.get("plant_id") is not None:
            det = ler_usina(cfg, ln["fonte"], ln["plant_id"], forcar)
            if det.get("erro"):
                c["erro"] = det["erro"]
            else:
                c.update(pares(det, invs))
                c["provisorio"] = str(det.get("provisorio") or "")
                c["fonte_hoje_erro"] = str(det.get("fonte_hoje_erro") or "")
        else:
            c["nota"] = "Nesta fonte o inversor liga pelo nome que ela manda: o que não casa se corrige no cadastro."
            c["sobra"] = [{"alvo": {"nome": i["equipamento_supervisorio"] or i["nome"], "exibicao": i["nome"], "esp": None},
                           "inversor_id": i["id"], "so_cadastro": True} for i in invs]
        out.append(c)
    return out


def resumo(lista: dict, est: dict) -> dict:
    """O que a lista de usinas e os números do alto precisam: a luz de cada usina, as pendentes e as sem usina."""
    por, sem = por_usina(lista, est)
    luzes = {uid: luz(v) for uid, v in por.items()}
    linhas = [x for v in por.values() for x in v] + sem
    return {"luzes": luzes, "por_usina": por, "sem_usina": sem,
            "pendentes": sum(1 for v in luzes.values() if v in ("alerta", "critico")),
            "linhas": len(linhas), "linhas_ok": sum(1 for x in linhas if x["luz"] == "ok"),
            "sem_par": sum(1 for x in linhas if x.get("sem_depara")),
            "erro": lista.get("erro") or "", "lido_em": lista.get("lido_em")}
