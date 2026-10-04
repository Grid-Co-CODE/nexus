"""Ponte do Nexus para a Plataforma de Performance (04/10/2026).

Levi: "tudo da plataforma, só leitura", "em paralelo por enquanto", e a meta de a plataforma morar 100% no Nexus. A
aba Performance → Tempo real mostra a Entrada e o Monitoramento da própria plataforma: o navegador fala só com o Nexus,
e esta ponte leva cada pedido à plataforma com a chave só de leitura (`X-Nexus-Leitura`) e o prefixo
(`X-Forwarded-Prefix`). A plataforma já sabe rodar debaixo de um caminho e devolve as páginas com o prefixo, então as
chamadas delas voltam para cá sem reescrever HTML. Aqui só se acrescenta o visual do Nexus e o guarda de leitura.

Só leitura em três camadas: o portão da plataforma (403 para gravação com a chave), `pode_passar` aqui, e o guarda no
navegador. Sem Flask: a rota está em nexus/torres/performance.
"""
import json
import threading
from urllib.parse import urljoin, urlsplit

import requests

PREFIXO = "/t/performance/plataforma"
# O drill da API PV leva até 120 s na plataforma (24/09/2026, API PV lenta); 150 s cobre sem prender para sempre.
TEMPO_LIMITE_S = 150
# os únicos POSTs que passam: consultas com a lista de usinas no corpo (a mesma lista do leitura_nexus da plataforma).
# ESPELHADA: muda aqui, muda em `plataforma/leitura_nexus.py`; divergência falha fechada (a plataforma devolve 403).
POSTS_DE_CONSULTA = frozenset({"/api/os-performance/counts", "/api/os-creator/fractall-usinas", "/api/etm/os"})
# Parâmetros de query que fazem uma rota GET reconstruir, coletar ou refazer histórico. É a mesma lista do
# `leitura_nexus.py` da plataforma: a chave de leitura RECUSA o pedido que os traz, então a ponte os tira antes de
# enviar. O "Atualizar" das páginas, pelo Nexus, lê o que o motor já montou. ESPELHADA: muda aqui, muda lá.
PARAMETROS_QUE_DISPARAM = frozenset({"force", "forcar", "run", "backfill"})
# cabeçalhos que a plataforma devolve e o navegador pode ver; o resto (Set-Cookie, salto, tamanho) fica aqui
_CABECALHOS_QUE_PASSAM = ("Content-Type", "Content-Disposition", "Cache-Control", "Last-Modified", "ETag")


# Vagas simultâneas na plataforma. Cada pedido segura uma thread do Nexus por até TEMPO_LIMITE_S (o drill da API PV leva
# 120 s): sem teto, a Entrada/Monitoramento aberta em poucas abas esgota as threads e trava até o login da casca. Quem não
# consegue vaga em ESPERA_VAGA_S recebe 503 na hora, em vez de ficar na fila segurando mais uma thread.
_VAGAS = threading.BoundedSemaphore(4)
ESPERA_VAGA_S = 2
# Uma sessão só: reaproveita a conexão com a plataforma (a Entrada dispara dezenas de GETs curtos em sequência).
_SESSAO = requests.Session()
# Quantos saltos (3xx) a ponte segue sozinha, e só dentro do mesmo servidor.
MAX_SALTOS = 3
_PORTA_PADRAO = {"http": 80, "https": 443}


class ForaDoAr(Exception):
    """A plataforma não respondeu (rede, tempo-limite)."""


class RedirecionamentoRecusado(ForaDoAr):
    """A plataforma mandou seguir para outro servidor (ou em círculos); a ponte não foi."""


class Ocupada(Exception):
    """Todas as vagas da ponte estão em uso: o Nexus não aceita mais um pedido à plataforma agora."""


def pode_passar(metodo: str, caminho: str) -> bool:
    m = (metodo or "").upper()
    if m in ("GET", "HEAD"):
        return True
    return m == "POST" and (caminho or "").split("?", 1)[0].rstrip("/") in POSTS_DE_CONSULTA


def montar_pedido(base_url, token, metodo, caminho, query, corpo, tipo) -> dict:
    # A regra do caminho vive AQUI, e não só na rota: "@evil.com/x" colado na base viraria usuário "plat" no servidor
    # evil.com (a chave de leitura iria para fora), e "?"/"#" escondem query por fora do filtro de parâmetros abaixo.
    if not caminho.startswith("/") or "?" in caminho or "#" in caminho:
        raise ValueError("caminho inválido")
    # `force=1` refaz na hora o que o motor monta sozinho (no "Atualizar" dos trackers, curvas novas na SunOp); `run` e
    # `backfill` disparam coleta e histórico. Pelo Nexus, ler é ler o que já está pronto.
    params = [(k, v) for k, v in (query or []) if k not in PARAMETROS_QUE_DISPARAM]
    cab = {"X-Nexus-Leitura": token, "X-Forwarded-Prefix": PREFIXO, "Accept": "*/*", "User-Agent": "nexus-ponte"}
    pedido = {"method": metodo.upper(), "url": base_url.rstrip("/") + caminho, "params": params, "headers": cab,
              "timeout": TEMPO_LIMITE_S, "allow_redirects": False}
    if corpo is not None and pedido["method"] == "POST":
        pedido["data"] = corpo
        if tipo:
            cab["Content-Type"] = tipo
    return pedido


def ajustar_resposta(status, cabecalhos, corpo):
    # Nome de cabeçalho não tem caixa fixa: Cloudflare e HTTP/2 entregam tudo em minúsculo, e o `requests` mantém a
    # caixa de origem no `.items()`. Comparar com a caixa exata deixaria o HTML passar SEM o guarda de leitura (falha
    # aberta), então o casamento é por minúsculo e a resposta volta com o nome canônico.
    recebidos = {str(k).lower(): v for k, v in (cabecalhos or {}).items()}
    cab = {nome: recebidos[nome.lower()] for nome in _CABECALHOS_QUE_PASSAM if nome.lower() in recebidos}
    if str(cab.get("Content-Type", "")).lower().startswith("text/html"):
        corpo = injetar(corpo.decode("utf-8", "replace")).encode("utf-8")
    return status, cab, corpo


# O visual do Nexus por cima (mesmo Design System; muda a fonte, o fundo e some com o topo próprio da plataforma —
# o topo do Nexus já está na casca). O "‹ Entrada" leva ao nível 1 (Painel, OS, Gerencial), fora deste passo.
# Os seletores de `onclick`/`onchange`/`oninput` escondem SÓ o controle que grava (botão, campo, linha do seletor de OS),
# nunca um contêiner de dado. O atributo é o real de cada um na página (conferido em "Monitoramento (novo design).html"):
# `tkStrQtdSai` e `tkStrQuem` são `onchange`, a quantidade digitada é `oninput="tkStrQtdDig"`. O guarda do navegador já
# barra o POST; isto só tira o botão da frente do analista, que senão clicaria e veria apenas o aviso.
_VISUAL = """<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
<style id="nexus-visual">
body,button,input,select,textarea{font-family:"Poppins",system-ui,-apple-system,"Segoe UI",sans-serif!important}
body{background-image:none!important}
.topo,.pe,a.volta[href$="/plataforma/"],button.atualiza,[data-atualizar]{display:none!important}
[onclick*="trancarString"],[onclick*="excluirComent"],[onclick*="gcDesatribuirOS"],[onclick*="gcUsinaReligada"],
[onchange*="setTracking"],[oninput*="setTracking"],
[onclick*="toggleOsMode"],[onclick*="osGerar"],[onclick*="gcUsinaDesligada"],[onclick*="gcDeslConfirmar"],
[onclick*="tkStrSalvar"],[onclick*="tkStrFinalizar"],[onclick*="tkStrConfirmar"],[onclick*="tkStrQtd"],
[oninput*="tkStrQtdDig"],[onchange*="tkStrQtdSai"],[onclick*="tkStrCampo"],[onchange*="tkStrCampo"],
[onchange*="tkStrFim"],[onchange*="tkStrQuem"],[onclick*="publicarComent"],[onclick*="gcAtribuirOS"],
[onclick*="gcPickOS"],[onclick*="gcConfirmarOS"]{display:none!important}
#nexus-leitura-aviso{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:99999;background:#161d30;
  color:#e9eef6;border:1px solid rgba(255,216,61,.5);border-radius:10px;padding:10px 16px;font:500 13px/1.4 "Poppins",sans-serif;
  box-shadow:0 10px 30px rgba(0,0,0,.45)}
</style>"""

# O guarda do navegador: todo POST que grava não sai e vira um 403 com aviso. Roda depois do calço da plataforma (que
# fica no topo do <head>), então recebe o caminho já com o prefixo e o tira para comparar.
# Atenção: esta string passa por `%` (dois `%s`); não pode haver outro `%` aqui dentro. E a barra invertida dupla da
# regex abaixo, no Python, chega ao navegador como uma só: a regex do JS fica /\/+$/ (barras finais).
_GUARDA = """<script id="nexus-leitura">(function(){var CONSULTA=%s,P=%s,_f=window.fetch;
function aviso(){var d=document.getElementById('nexus-leitura-aviso');if(!d){d=document.createElement('div');
d.id='nexus-leitura-aviso';document.body.appendChild(d);}d.textContent='Somente leitura no Nexus: faça isto na plataforma.';
clearTimeout(d._t);d.style.display='block';d._t=setTimeout(function(){d.style.display='none';},4000);}
if(_f)window.fetch=function(u,o){var m=((o&&o.method)||'GET').toUpperCase();
if(m!=='GET'&&m!=='HEAD'){var c=String(typeof u==='string'?u:(u&&u.url)||'').split('?')[0];
if(c.indexOf(P)===0)c=c.slice(P.length);c=c.replace(/\\/+$/,'');
if(CONSULTA.indexOf(c)<0){aviso();return Promise.resolve(new Response(JSON.stringify({ok:false,error:'somente leitura (Nexus)'}),
{status:403,headers:{'Content-Type':'application/json'}}));}}return _f.apply(this,arguments);};})();</script>"""


def injetar(html: str) -> str:
    extra = _VISUAL + _GUARDA % (json.dumps(sorted(POSTS_DE_CONSULTA)), json.dumps(PREFIXO))
    i = html.lower().find("</head>")
    return html[:i] + extra + html[i:] if i >= 0 else extra + html


def _origem(url: str):
    """(esquema, host, porta): o que define "o mesmo servidor". Porta omitida vale a padrão do esquema."""
    p = urlsplit(url)
    esq = (p.scheme or "").lower()
    return esq, (p.hostname or "").lower(), p.port or _PORTA_PADRAO.get(esq)


def vai_para_login(destino: str) -> bool:
    # A plataforma manda para o /login quem chega sem sessão e sem a chave valendo. Seguir mostraria a tela de login dela
    # dentro do Nexus; a rota traduz isto em "a plataforma recusou a chave".
    return urlsplit(destino).path.rstrip("/").endswith("/login")


def _seguir(pedido: dict):
    url = pedido["url"]
    origem = _origem(url)
    atual = dict(pedido, allow_redirects=False)
    for salto in range(MAX_SALTOS + 1):
        try:
            r = _SESSAO.request(**atual)
        except requests.RequestException as e:
            raise ForaDoAr(type(e).__name__) from e
        local = {str(k).lower(): v for k, v in (r.headers or {}).items()}.get("location")
        if r.status_code not in (301, 302, 303, 307, 308) or not local:
            return r
        destino = urljoin(atual["url"], local)
        # A chave de leitura vai em todo pedido: seguir um salto para outro host (ou outra porta, ou http) a entregaria a
        # quem a plataforma, ou alguém no caminho, escolheu. Só o mesmo servidor.
        if _origem(destino) != origem:
            raise RedirecionamentoRecusado("redirecionamento para outro servidor")
        if vai_para_login(destino):
            return r
        if salto == MAX_SALTOS:
            raise RedirecionamentoRecusado("redirecionamentos demais")
        # a query do pedido original já foi embutida na URL que saltou; o destino traz a sua própria
        atual = dict(atual, url=destino, params=[])
        if r.status_code in (301, 302, 303) and atual["method"] != "HEAD":
            # como o navegador e o `requests`: o salto vira GET e o corpo fica para trás (307/308 mantêm tudo)
            atual["method"] = "GET"
            atual.pop("data", None)
            atual["headers"] = {k: v for k, v in atual["headers"].items() if k.lower() != "content-type"}


def enviar(**pedido):
    """O único ponto que fala com a rede. Os testes trocam esta função."""
    if not _VAGAS.acquire(timeout=ESPERA_VAGA_S):
        raise Ocupada()
    try:
        return _seguir(pedido)
    finally:
        _VAGAS.release()
