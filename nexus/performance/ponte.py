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

import requests

PREFIXO = "/t/performance/plataforma"
# O drill da API PV leva até 120 s na plataforma (24/09/2026, API PV lenta); 150 s cobre sem prender para sempre.
TEMPO_LIMITE_S = 150
# os únicos POSTs que passam: consultas com a lista de usinas no corpo (a mesma lista do leitura_nexus da plataforma)
POSTS_DE_CONSULTA = frozenset({"/api/os-performance/counts", "/api/os-creator/fractall-usinas", "/api/etm/os"})
# Parâmetros de query que fazem uma rota GET reconstruir, coletar ou refazer histórico. É a mesma lista do
# `leitura_nexus.py` da plataforma: a chave de leitura RECUSA o pedido que os traz, então a ponte os tira antes de
# enviar. O "Atualizar" das páginas, pelo Nexus, lê o que o motor já montou.
PARAMETROS_QUE_DISPARAM = frozenset({"force", "forcar", "run", "backfill"})
# cabeçalhos que a plataforma devolve e o navegador pode ver; o resto (Set-Cookie, salto, tamanho) fica aqui
_CABECALHOS_QUE_PASSAM = ("Content-Type", "Content-Disposition", "Cache-Control", "Last-Modified", "ETag")


class ForaDoAr(Exception):
    """A plataforma não respondeu (rede, tempo-limite)."""


def pode_passar(metodo: str, caminho: str) -> bool:
    m = (metodo or "").upper()
    if m in ("GET", "HEAD"):
        return True
    return m == "POST" and (caminho or "").split("?", 1)[0].rstrip("/") in POSTS_DE_CONSULTA


def montar_pedido(base_url, token, metodo, caminho, query, corpo, tipo) -> dict:
    # `force=1` refaz na hora o que o motor monta sozinho (no "Atualizar" dos trackers, curvas novas na SunOp); `run` e
    # `backfill` disparam coleta e histórico. Pelo Nexus, ler é ler o que já está pronto.
    params = [(k, v) for k, v in (query or []) if k not in PARAMETROS_QUE_DISPARAM]
    cab = {"X-Nexus-Leitura": token, "X-Forwarded-Prefix": PREFIXO, "Accept": "*/*", "User-Agent": "nexus-ponte"}
    pedido = {"method": metodo.upper(), "url": base_url.rstrip("/") + caminho, "params": params, "headers": cab,
              "timeout": TEMPO_LIMITE_S, "allow_redirects": True}
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
_VISUAL = """<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
<style id="nexus-visual">
body,button,input,select,textarea{font-family:"Poppins",system-ui,-apple-system,"Segoe UI",sans-serif!important}
body{background-image:none!important}
.topo,.pe,a.volta[href$="/plataforma/"],button.atualiza,[data-atualizar]{display:none!important}
[onclick*="trancarString"],[onclick*="excluirComent"],[onclick*="gcDesatribuirOS"],[onclick*="gcUsinaReligada"],
[onchange*="setTracking"],[oninput*="setTracking"]{display:none!important}
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


def enviar(**pedido):
    """O único ponto que fala com a rede. Os testes trocam esta função."""
    try:
        return requests.request(**pedido)
    except requests.RequestException as e:
        raise ForaDoAr(type(e).__name__) from e
