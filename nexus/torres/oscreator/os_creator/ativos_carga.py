"""ativos_carga.py: o catálogo de ativos para as telas.

A cola do `api` com o catálogo central (`ativos_central.py`, etapa 2): entregar a lista (`load_assets_cached`), baixar pelo RPC
quando não há nada ou está vencido (`_baixar_pelo_rpc`, um por vez), renovar por trás com a sessão de quem pediu, esperar os
ativos novos do leitor do servidor, e os textos que os três botões "Atualizar ativos" mostram. O estado (a lista, a recusa, a
falha) é do `ativos_central`.

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

import contextvars
import threading
import time
from concurrent.futures import as_completed
from datetime import datetime
from fracttal_erro import FracttalError, SessionExpired
import ativos_central


RPC_ITEMS = "inventories.items_list"   # ativos (RPC, sessão do usuário) — flat com is_tree=false


def _items_params(start: int, limit: int = 200) -> dict:
    return {"filter": [], "sort": [{"property": "id_type_item", "direction": "asc"}], "group": {},
            "page": start // limit + 1, "limit": limit, "start": start, "is_tree": False,
            "node": None, "id_type_item": 0, "id_type_item_not": "", "id_location": None}


def _items_page_rpc(start: int, limit: int = 200) -> list:
    res = api._rpc_call(RPC_ITEMS, api._items_params(start, limit), timeout=45)
    data = res.get("data") if isinstance(res, dict) else res
    return data if isinstance(data, list) else []


def get_assets() -> list:
    """TODOS os ativos (16k+) via RPC inventories.items_list (is_tree=false, sessão do usuário —
    SEM OAuth). 1ª página dá o total; as demais em paralelo. Cada registro recebe cliente/usina/tipo
    derivados (parent_description + code) p/ o drill-down. Ordenado por cliente+usina+code."""
    first = api._rpc_call(RPC_ITEMS, api._items_params(0, 200), timeout=45)
    total = int(first.get("total") or 0) if isinstance(first, dict) else 0
    data = list(first.get("data") or []) if isinstance(first, dict) else []
    starts = list(range(200, total, 200))
    if starts:
        res = {}
        with api._ExecutorComContexto(max_workers=6) as ex:
            futs = {ex.submit(api._items_page_rpc, s): s for s in starts}
            for f in as_completed(futs):
                res[futs[f]] = f.result()
        for s in starts:
            data.extend(res.get(s, []))
    return api._build_records(data)          # pelo `api.`: o `montar_registros` do `ativos_central`, que o teste pode trocar


ASSETS_TTL   = 24 * 3600
_ASSETS_RECARGA = threading.Lock()      # uma recarga do Fracttal por vez (~110 pedidos); quem chega espera a dela


ASSETS_TTL_LEITOR = 26 * 3600   # com o leitor do servidor pronto: a leitura da noite de hoje renova o catálogo antes disto


def catalogo_vencido(cat) -> bool:
    """O catálogo foi conferido com o Fracttal há 24 h ou mais (`ASSETS_TTL`). Conferido é o `lido_em` dele OU a leitura
    completa que ele recusou depois (`ativos_central.conferido_em`): a recusa também foi uma ida de ~110 pedidos ao Fracttal, e
    repeti-la a cada aprovação da Fila (e de 10 em 10 min por trás) só trazia o mesmo resultado, minutos depois. Com o leitor do
    servidor pronto, 26 h (`ASSETS_TTL_LEITOR`): a leitura da noite de ontem vence 24 h depois, em cima da de hoje, e um pedido
    nesse minuto dispararia o RPC (~110 pedidos) junto com o REST (revisão 1 da 2.2). O catálogo que veio da foto do banco
    está SEMPRE vencido (o código da foto é o canônico, sem espaço, e ela é o socorro da máquina sem cópia nenhuma: a 1ª
    leitura do Fracttal a troca). Vencido, o catálogo continua servindo; só se renova."""
    if cat.fonte == "banco":
        return True
    ttl = api.ASSETS_TTL_LEITOR if ativos_central.leitor_pronto() else api.ASSETS_TTL
    return time.time() - ativos_central.conferido_em(cat) >= ttl


def aviso_da_recusa() -> str:
    """O motivo da última leitura completa do Fracttal que o catálogo recusou, em texto curto com a hora, enquanto nenhuma
    leitura aceita veio depois dela; senão "". Os três botões "Atualizar ativos" levam isto na resposta (campo `recusa`): a
    pessoa clicava, o número não mudava (`delta` 0) e ninguém dizia por quê."""
    r = ativos_central.recusa_vigente()
    if not r:
        return ""
    quando = datetime.fromtimestamp(r["lido_em"], api._BR_TZ).strftime("%d/%m %H:%M")
    return "A leitura do Fracttal de %s não entrou: %s. Ficou o catálogo de antes." % (quando, r["motivo"])


def aviso_da_falha() -> str:
    """O download pelo RPC que FALHOU há menos de `ASSETS_ESPERA_TENTATIVA` (Fracttal fora, cota estourada), em texto curto com
    a hora; senão "". Os botões levam isto (campo `falha`): dentro da janela eles devolvem o catálogo de antes sem tentar de
    novo, e a pessoa precisa saber por quê (revisão 1 da 2.2)."""
    f = ativos_central.falha()
    if not f or f.get("fonte") != "rpc" or time.time() - float(f.get("em") or 0.0) >= api.ASSETS_ESPERA_TENTATIVA:
        return ""
    quando = datetime.fromtimestamp(f["em"], api._BR_TZ).strftime("%H:%M")
    return "O Fracttal não deu os ativos às %s (%s); ficou a lista de antes, e ele é tentado de novo em alguns minutos." % (
        quando, f.get("erro") or "sem motivo")


def _quando(ts: float, hoje) -> str:
    q = datetime.fromtimestamp(ts, api._BR_TZ)
    return q.strftime("%H:%M" if q.date() == hoje else "%d/%m %H:%M")


def ativos_de(cat=None, agora: float | None = None) -> str:
    """"ativos de HH:MM" (Brasília) pela última vez que a lista foi comparada com o Fracttal (`ativos_central.visto_em`: a
    lista inteira ou os novos do dia, a mais nova: Ruling AL, o botão existe para o ativo novo); de outro dia, "ativos de dd/mm
    HH:MM" (à 01:00, "de 02:20" seria lido como a de hoje, que ainda não houve). Sem catálogo, "". É o que os três botões
    "Atualizar ativos" respondem na hora; as duas horas, separadas, estão no `ativos_de_titulo`."""
    cat = ativos_central.atual() if cat is None else cat
    if cat is None:
        return ""
    visto = ativos_central.visto_em(cat)
    if not visto:
        return ""
    return "ativos de " + api._quando(visto, datetime.fromtimestamp(time.time() if agora is None else agora, api._BR_TZ).date())


def ativos_de_titulo(cat=None, agora: float | None = None) -> str:
    """O `title` do "ativos de HH:MM" (Ruling AL): as duas horas, "lista completa de dd/mm HH:MM; novos até HH:MM" (sem
    leitura dos novos depois da lista completa, só a primeira). A lista completa conferida de madrugada vê o que saiu e o que
    mudou; os novos do dia, só o que entrou."""
    cat = ativos_central.atual() if cat is None else cat
    if cat is None or not cat.lido_em:
        return ""
    hoje = datetime.fromtimestamp(time.time() if agora is None else agora, api._BR_TZ).date()
    texto = "lista completa de " + datetime.fromtimestamp(cat.lido_em, api._BR_TZ).strftime("%d/%m %H:%M")
    if cat.novos_em > cat.lido_em:
        texto += "; novos até " + api._quando(cat.novos_em, hoje)
    return texto


def texto_dos_novos(desfecho: dict | None) -> str:
    """O que a tela diz depois de "Atualizar ativos" com o leitor do servidor, pelo desfecho da leitura dos novos
    (`ativos_central.esperar_novos`), nesta ordem (revisão 1 da 2.2: "nenhum ativo novo no Fracttal" saía de qualquer delta 0,
    também quando a busca estourava a espera ou falhava):
    - não terminou dentro da espera: a busca ainda não terminou;
    - falhou: não consegui buscar, e o motivo;
    - deixou ativos para a noite (o novo sem o pai no catálogo, os novos demais): quantos; "mais de N" quando a leitura parou
      no teto com a última página toda de novos (`muitos_mais`, revisão 2 da 2.2: o N é só o que ela viu);
    - terminou bem sem nada: "nenhum ativo novo no Fracttal";
    - terminou bem com novos: quantos (a tela de Ativos põe no lugar a conta da lista, o delta).
    Sem desfecho (sem o leitor, ou a última leitura é de mais de 2 min: não é a de agora), nada."""
    if not desfecho:
        return ""
    if not desfecho.get("terminou"):
        return "a busca no Fracttal ainda não terminou: os ativos novos aparecem em instantes"
    if desfecho.get("erro"):
        return "não consegui buscar os ativos novos no Fracttal: %s" % desfecho["erro"]
    noite = int(desfecho.get("sem_pai") or 0) + int(desfecho.get("muitos") or 0)
    n = int(desfecho.get("acrescentados") or 0)
    if noite:
        texto = ("%d ativo novo fica" if noite == 1 else "%d ativos novos ficam") % noite + " para a leitura da noite"
        if desfecho.get("muitos_mais"):
            texto = "mais de " + texto
        return texto + ("; %d entrou agora" % n if n == 1 else "; %d entraram agora" % n if n else "")
    if not n:
        return "nenhum ativo novo no Fracttal"
    return "%d ativo novo do Fracttal na lista" % n if n == 1 else "%d ativos novos do Fracttal na lista" % n


def _read_asset_cache():
    """O catálogo central como está, SEM a trava das 24 h e sem ir ao Fracttal (era o arquivo, vencido = None): a lista
    compartilhada, ou None se esta máquina ainda não tem catálogo nenhum. Para quem só precisa LER o que há (as frases do tipo,
    a contagem da tela inicial); quem precisa dele de qualquer jeito pede `load_assets_cached()`."""
    cat = ativos_central.atual()
    return cat.lista if cat is not None else None


def assets_cache_info() -> dict:
    """De quando é o catálogo e quantos ativos ele tem. → {'ts': epoch|0, 'n': ativos, 'idade_h': float, 'expirado': bool,
    'ativos_de': "ativos de HH:MM", 'ativos_de_titulo': as duas horas, 'leitor': bool}. Serve para a aba Ativos dizer de
    QUANDO é a lista que está na tela — sem isso, "18.259 ativos" parece um número de agora mesmo quando é de dez dias atrás. Lê
    o catálogo da memória (até 20/10/2026 decodificava o arquivo inteiro, 10,5 MB, a cada chamada, e a tela inicial chama a cada
    5 min). O `ts` e o `expirado` são da lista inteira (o "desatualizado" da tela inicial); o `ativos_de` conta também os novos
    do dia; `leitor` diz se o servidor lê os ativos sozinho (os botões pedem só os novos)."""
    cat = ativos_central.atual()
    if cat is None:
        return {"ts": 0, "n": 0, "idade_h": 0.0, "expirado": True, "ativos_de": "", "ativos_de_titulo": "", "leitor": False}
    idade = max(0.0, time.time() - cat.lido_em)
    return {"ts": cat.lido_em, "n": len(cat.lista), "idade_h": idade / 3600.0,
            "expirado": idade > api.ASSETS_TTL or cat.fonte == "banco", "ativos_de": api.ativos_de(cat),
            "ativos_de_titulo": api.ativos_de_titulo(cat), "leitor": ativos_central.leitor_pronto()}


ESPERA_NOVOS_S = 6     # s: quem espera os ativos novos do leitor do servidor (a aprovação da Fila, o "?novos=1" das telas)


def load_assets_cached(force: bool = False, em_dia: bool = False) -> tuple:
    """Os ativos: a lista COMPARTILHADA do catálogo central (uma tupla de registros só de leitura, sem copiar), ou, sem catálogo
    nenhum nesta máquina, a recarga via RPC (sessão do usuário — sem OAuth), que entra no catálogo e na cópia em disco.

    COM O LEITOR DO SERVIDOR PRONTO (31/10/2026, tarefa 2.2 do canto central; `ativos_leitor.py`, que só o `servir.py` liga;
    pronto = a leitura REST conferida há no máximo 30 h e nenhuma leitura REST falhando, `ativos_central.leitor_pronto`):
    ninguém mais espera o Fracttal inteiro. `force=True` (os três botões "Atualizar ativos") pede ao leitor os ativos NOVOS por
    trás e volta na hora com o catálogo de agora. `em_dia=True` (a aprovação da Fila) volta com o catálogo como está: quem não
    acha o ativo da solicitação nele espera os novos (`rotas_solic._ativo_para_aprovar`, revisão 1 da 2.2), e não toda
    aprovação. Vencido (26 h sem uma lista inteira conferida: a noite não veio, ou o leitor parou; a lista que o catálogo
    recusou por encolher CONTA como conferida, `catalogo_vencido`), o catálogo ainda é renovado por trás pelo RPC, uma vez, com
    a sessão de quem pediu: o socorro de sempre.

    SEM O LEITOR PRONTO (o PC, os testes, a paridade que falhou ou envelheceu, o REST falhando): como era. force=True ignora o
    que há e baixa (o catálogo é um só, vale para todos). VENCIDO (24/10/2026): devolve o de ontem na hora e baixa o novo por
    trás (`_renovar_catalogo_por_tras`). Em 23/10 às 10:44 o 1º a precisar do catálogo vencido baixou os ~22 mil ativos DENTRO
    do pedido: um "Criar OS" da Performance ficou 3 min 51 s em `get_assets` e o Histórico 1 min 52 s esperando o mesmo
    download. `em_dia=True` espera o novo, como antes; sem catálogo nenhum (nem a cópia em disco, nem o arquivo antigo, nem a
    foto do banco), também.

    A RECUSA E A FALHA SÃO LEMBRADAS: ver `_baixar_pelo_rpc`."""
    cat = ativos_central.atual()            # o boot local (o disco), que traz também a paridade de antes do reinício
    por_tras = _POR_TRAS.get()
    if not por_tras and ativos_central.leitor_pronto():
        cat = cat or ativos_central.garantir()
        if cat is not None:
            if force:
                ativos_central.pedir_novos()
            if api.catalogo_vencido(cat):
                api._renovar_catalogo_por_tras()
            return cat.lista
    if not force:
        cat = cat or ativos_central.garantir()
        if cat is not None:
            vencido = api.catalogo_vencido(cat)
            if not vencido or not em_dia:
                if vencido:
                    api._renovar_catalogo_por_tras()
                return cat.lista
    return api._baixar_pelo_rpc(force, por_tras=por_tras)


# a thread da renovação por trás (`_renovar_catalogo_por_tras`) marca o contexto dela: o download dela é o RPC (o socorro), e
# não os novos do leitor, e ela tem a janela própria de tentativas (a falha lembrada não a segura)
_POR_TRAS = contextvars.ContextVar("api_catalogo_por_tras", default=False)


def esperar_os_novos(so_em_curso: bool = True) -> dict | None:
    """Espera a leitura dos ativos novos até `ESPERA_NOVOS_S` e devolve o DESFECHO dela, com o `texto` que a tela mostra
    (`texto_dos_novos`) e `ok` (terminou bem, sem nada para a noite: a tela de Ativos põe no lugar a conta da lista). Com
    `so_em_curso` (o padrão: a tela que acabou de apertar "Atualizar ativos", que voltou na hora com `?novos=1`), a leitura que o
    botão pediu; sem ele (a aprovação que não achou o ativo), uma nova se a última já não é fresca. None sem o leitor, e quando
    a última leitura terminou há mais de 2 min sem nenhuma em curso (o F5 da Fila: o desfecho velho não é o de agora)."""
    desfecho = ativos_central.esperar_novos(api.ESPERA_NOVOS_S, so_em_curso=so_em_curso)
    if not isinstance(desfecho, dict):
        return None
    ok = bool(desfecho.get("terminou")) and not desfecho.get("erro") and not desfecho.get("sem_pai") and \
        not desfecho.get("muitos")
    return dict(desfecho, ok=ok, texto=api.texto_dos_novos(desfecho))


def _baixar_pelo_rpc(force: bool = False, por_tras: bool = False) -> tuple:
    """O download do catálogo pelo RPC, um por vez (`_ASSETS_RECARGA`).

    A RECUSA É LEMBRADA (revisão 1 da tarefa 2.1). A recarga que o tamanho recusa (menor que a de agora em mais de 5%: o RPC que
    perde páginas em silêncio) não troca nada, mas conta como conferida: o catálogo só vence 24 h depois dela, quem esperou a vez
    usa a leitura de quem baixou (entrando ou não) e o `force` (o botão) dentro de `ASSETS_ESPERA_TENTATIVA` depois dela devolve
    o catálogo de agora, sem baixar de novo. Antes, cada aprovação da Fila, depois das 24 h, baixava os ~110 pedidos de novo, e
    o download por trás repetia de 10 em 10 min. O motivo vai a `estado()["recusa"]` e aos botões (`aviso_da_recusa`).

    A FALHA TAMBÉM (2.2): o download que levantou (Fracttal fora, cota estourada) fica anotado (`ativos_central.anotar_falha`).
    Quem esperava a vez na trava enquanto ele falhava não tenta de novo em fila (N aprovações juntas não viram N leituras), e o
    `force` e o `em_dia` que chegarem dentro de `ASSETS_ESPERA_TENTATIVA` depois dela devolvem o catálogo de agora (sem
    catálogo nenhum, o erro), e os botões dizem por quê (`aviso_da_falha`). A renovação por trás (`por_tras`) tem a janela dela
    (`_ASSETS_RENOVA`) e não olha esta. A sessão recusada de UMA pessoa (`SessionExpired`: 401/403, o login que caiu) NÃO é
    falha do Fracttal: não segura o download de mais ninguém (revisão 1 da 2.2)."""
    pedido = time.time()
    with _ASSETS_RECARGA:
        cat = ativos_central.atual()
        falhou = ativos_central.falha()
        if falhou and falhou.get("fonte") == "rpc" and (
                falhou["em"] >= pedido or (not por_tras and time.time() - falhou["em"] < api.ASSETS_ESPERA_TENTATIVA)):
            if cat is not None:
                return cat.lista
            raise FracttalError("O Fracttal não deu os ativos há pouco (%s); tente de novo em alguns minutos."
                                % falhou.get("erro"))
        if cat is not None:
            # quem esperou a recarga de outro pedido usa a dela: o Fracttal foi lido depois deste pedido (e a leitura entrou
            # no catálogo ou foi recusada, tanto faz: baixar de novo traria o mesmo)
            if ativos_central.conferido_em(cat) >= pedido or (not force and not api.catalogo_vencido(cat)):
                return cat.lista
            recusa = ativos_central.recusa_vigente(cat) if force else None
            if recusa is not None and time.time() - recusa["lido_em"] < api.ASSETS_ESPERA_TENTATIVA:
                return cat.lista            # o botão logo depois de uma recusa: o Fracttal deu a mesma lista, não se baixa de novo
        try:
            assets = api.get_assets()
        except SessionExpired:
            raise                           # a sessão de quem pediu, e não o Fracttal: os outros seguem tentando
        except Exception as e:
            ativos_central.anotar_falha("rpc", e)
            raise
        ativos_central.anotar_falha("rpc", None)
        ativos_central.trocar(assets, "rpc")        # entra, ou é recusada (fica em estado()["recusa"] e conta como conferida)
        cat = ativos_central.atual()
        return cat.lista if cat is not None else tuple(assets)


ASSETS_ESPERA_TENTATIVA = 600     # s: o download por trás que falhou (Fracttal fora, cota) só tenta de novo depois disto, e o
#                                   botão "Atualizar ativos" logo depois de uma leitura recusada (ou que falhou) não baixa de novo
_ASSETS_RENOVA = {"tentou": 0.0}
_ASSETS_RENOVA_TRAVA = threading.Lock()


def _renovar_catalogo_por_tras() -> None:
    """Baixa o catálogo vencido pelo RPC numa thread, com a sessão de quem pediu (a cópia do contexto leva o JWT). Uma thread por
    ASSETS_ESPERA_TENTATIVA (a que achar outro download em curso espera a vez e usa o dele: `_baixar_pelo_rpc`), e a que falhou
    só tenta de novo depois disso. Com o leitor do servidor ligado, é o socorro da noite que não entrou: a marca `_POR_TRAS`
    no contexto da thread faz o `load_assets_cached(True)` dela ir ao RPC, e não pedir os novos ao leitor."""
    with _ASSETS_RENOVA_TRAVA:
        if time.time() - api._ASSETS_RENOVA["tentou"] < api.ASSETS_ESPERA_TENTATIVA:
            return
        api._ASSETS_RENOVA["tentou"] = time.time()
    ctx = contextvars.copy_context()

    def baixar():
        _POR_TRAS.set(True)
        return api.load_assets_cached(True)

    def rodar():
        try:
            ctx.run(api._na_sessao_propria, baixar)
        except Exception:                               # noqa: BLE001 — fica o de ontem; o próximo pedido tenta depois
            pass
    threading.Thread(target=rodar, name="os-catalogo-por-tras", daemon=True).start()


def _asset_by_code(code: str):
    """Registro completo do ativo pelo code: uma CÓPIA, pelo índice do catálogo central (até 31/10/2026 percorria uma cópia
    nova da lista inteira a cada código). None se não achar. Lê do que o `load_assets_cached()` devolve: a lista de outra
    origem (um dublê de teste, um recorte) é percorrida, como sempre foi."""
    try:
        lista = api.load_assets_cached()            # garante o catálogo (sem catálogo nenhum, baixa uma vez, como sempre)
        cat = ativos_central.atual()
        if cat is not None and lista is cat.lista:
            return ativos_central.registro(code)
        for a in lista:
            if a.get("code") == code:
                return dict(a)
    except Exception:
        pass
    return None


import api  # noqa: E402 — no fim: o `api` importa este módulo
