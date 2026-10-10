"""Porta local: faz o papel do Caddy do servidor num endereço só, para provar a porta única no PC.

Por quê (Levi, 09/10/2026: "a partir de segunda quero o Nexus como link principal"): no servidor o Nexus e a plataforma
estão na MESMA origem (`app.gridco.com.br/nexus` e `app.gridco.com.br`), e a porta única depende disso: a moldura da
plataforma só abre dentro do Nexus com `frame-ancestors 'self'`, os dois cookies dividem o mesmo endereço (o passo 0 do
spec) e o `postMessage` fala entre páginas da mesma origem. No PC cada cópia numa porta é OUTRA origem; esta porta junta
as duas como o servidor faz. Só repassa: não grava nada, não guarda nada, não fala com a internet.

Modos (`--modo`):
  prefixo (o padrão, o servidor de hoje): `/nexus` → 308 para `/nexus/`; `/nexus/*` → Nexus SEM o `/nexus` no caminho
      (medido de fora em 09/10/2026: o Nexus do servidor recebe `/entrar`, não `/nexus/entrar`); o resto → plataforma.
  raiz (a fase 4 do spec 2026-10-09-performance-no-nexus-design.md): `/` exato, `/t/*`, `/entrar`, `/sair`, `/saude`,
      `/tema`, `/cadeira`, `/os/*` e `/static/*` → Nexus, menos `/static/fonts/*`, `/static/logos/*` e
      `/static/notif.js`, que são da plataforma; o resto → plataforma.

`--reescrita-do-servidor` (só no modo prefixo): imita a camada que o servidor tem HOJE fora do repositório, medida de
fora em 09/10/2026 (o código do Nexus não sabe do `/nexus`, e mesmo assim as páginas saem com ele): (1) o `Location`
que começa por um caminho do Nexus ganha `/nexus`; (2) no HTML e no JavaScript, o caminho do Nexus logo depois de aspas
ou de `=` ganha `/nexus` (`"/entrar` → `"/nexus/entrar`, `next=/t/...` → `next=/nexus/t/...`), e o que não é do Nexus
fica (`"/usina/` não muda); (3) um calço no começo do `<head>` põe `/nexus` em todo `fetch` e XHR com caminho absoluto.
É uma APROXIMAÇÃO do que se viu de fora: serve para provar que o código novo convive com ela enquanto a T.I. não a tira.

Uso, com as cópias de prova no ar (`ferramentas/subir_copia_de_prova.py` aqui e `plataforma/subir_copia_de_prova.py` no
PerformancePainel):
    python ferramentas/porta_local.py --porta 5199 --nexus http://127.0.0.1:5170 --plataforma http://127.0.0.1:5150
    python ferramentas/porta_local.py ... --reescrita-do-servidor          (como o servidor está em 09/10/2026)
    python ferramentas/porta_local.py ... --modo raiz                      (fase 4)
"""
import argparse
import re

import requests

PREFIXO = "/nexus"
# Primeiro segmento de cada caminho do Nexus (spec, seção 2). "/" exato também é dele no modo raiz.
SEGMENTOS_NEXUS = ("t", "entrar", "sair", "saude", "tema", "cadeira", "os", "static")
ESTATICOS_DA_PLATAFORMA = ("/static/fonts/", "/static/logos/", "/static/notif.js")
SALTO_A_SALTO = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "trailers",
                 "transfer-encoding", "upgrade"}
# O calço que o servidor injeta no <head> das páginas do Nexus (copiado do que ele serve em 09/10/2026).
CALCO_DO_SERVIDOR = ("<script>(function(){var P=\"/nexus\";function f(u){return(typeof u==='string'&&u[0]==='/'&&"
                     "u[1]!=='/'&&u.indexOf(P+'/')!==0&&u!==P)?P+u:u}var F=window.fetch;if(F)window.fetch=function(u,o)"
                     "{return F.call(this,f(u),o)};var X=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open="
                     "function(m,u){arguments[1]=f(u);return X.apply(this,arguments)}})();</script>")
_SEG = "|".join(SEGMENTOS_NEXUS)
_NO_TEXTO = re.compile(r"(?<=[\"'=])/(?=(?:%s)(?:[/\"'?#&]|$))" % _SEG)


def destino(caminho: str, modo: str) -> tuple[str, str]:
    """('nexus' | 'plataforma' | 'barra', caminho a repassar)."""
    if modo == "prefixo":
        if caminho == PREFIXO:
            return "barra", PREFIXO + "/"
        if caminho.startswith(PREFIXO + "/"):
            return "nexus", caminho[len(PREFIXO):]
        return "plataforma", caminho
    if caminho.startswith(ESTATICOS_DA_PLATAFORMA):
        return "plataforma", caminho
    primeiro = caminho.lstrip("/").split("/", 1)[0]
    if caminho == "/" or primeiro in SEGMENTOS_NEXUS:
        return "nexus", caminho
    return "plataforma", caminho


def reescreve_location(valor: str) -> str:
    if valor.startswith("/") and not valor.startswith("//"):
        primeiro = valor.lstrip("/").split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if valor in ("/",) or valor.startswith(("/?", "/#")) or primeiro in SEGMENTOS_NEXUS:
            return PREFIXO + valor
    return valor


def reescreve_corpo(texto: str, html: bool) -> str:
    texto = _NO_TEXTO.sub(PREFIXO + "/", texto)
    if html:
        i = texto.lower().find("<head>")
        if i >= 0:
            texto = texto[:i + 6] + CALCO_DO_SERVIDOR + texto[i + 6:]
    return texto


def criar_app(nexus: str, plataforma: str, modo: str, reescrita: bool):
    sessao = requests.Session()
    sessao.mount("http://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=64))
    bases = {"nexus": nexus.rstrip("/"), "plataforma": plataforma.rstrip("/")}

    def app(environ, start_response):
        caminho = environ.get("PATH_INFO") or "/"
        qs = environ.get("QUERY_STRING") or ""
        quem, repassar = destino(caminho, modo)
        if quem == "barra":
            start_response("308 Permanent Redirect", [("Location", repassar), ("Content-Length", "0")])
            return [b""]
        cabecalhos = {k[5:].replace("_", "-").title(): v for k, v in environ.items() if k.startswith("HTTP_")}
        for k in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            if environ.get(k):
                cabecalhos[k.replace("_", "-").title()] = environ[k]
        # Como o Caddy: o Host do navegador segue igual, e o X-Forwarded-* diz quem pediu
        cabecalhos["X-Forwarded-For"] = environ.get("REMOTE_ADDR", "127.0.0.1")
        cabecalhos["X-Forwarded-Proto"] = environ.get("wsgi.url_scheme", "http")
        cabecalhos["X-Forwarded-Host"] = environ.get("HTTP_HOST", "")
        reescrever = reescrita and modo == "prefixo" and quem == "nexus"
        if reescrever:
            cabecalhos["Accept-Encoding"] = "identity"
        tamanho = int(environ.get("CONTENT_LENGTH") or 0)
        corpo = environ["wsgi.input"].read(tamanho) if tamanho else None
        url = bases[quem] + repassar + ("?" + qs if qs else "")
        try:
            r = sessao.request(environ["REQUEST_METHOD"], url, headers=cabecalhos, data=corpo, stream=True,
                               allow_redirects=False, timeout=(5, 300))
        except requests.RequestException as e:
            msg = f"porta local: {quem} fora do ar ({e.__class__.__name__})".encode()
            start_response("502 Bad Gateway", [("Content-Type", "text/plain; charset=utf-8"),
                                               ("Content-Length", str(len(msg)))])
            return [msg]
        saida = [(k, v) for k, v in r.raw.headers.items() if k.lower() not in SALTO_A_SALTO]
        saida.append(("Via", "1.1 porta-local"))
        tipo = r.headers.get("Content-Type", "")
        texto_do_nexus = reescrever and ("text/html" in tipo or "javascript" in tipo)
        if reescrever:
            saida = [(k, reescreve_location(v)) if k.lower() == "location" else (k, v) for k, v in saida]
        # Com allow_redirects=False o requests ainda lê o corpo do salto (para soltar a conexão): o r.raw chega vazio e o
        # waitress acusava "too few bytes" para o Content-Length do upstream. Salto e texto reescrito vão já lidos.
        if r.is_redirect or texto_do_nexus:
            dados = r.content
            if texto_do_nexus:
                dados = reescreve_corpo(dados.decode(r.encoding or "utf-8", "replace"),
                                        "text/html" in tipo).encode(r.encoding or "utf-8")
            saida = [(k, v) for k, v in saida if k.lower() not in ("content-length", "content-encoding")]
            saida.append(("Content-Length", str(len(dados))))
            start_response(f"{r.status_code} {r.reason}", saida)
            return [dados]
        start_response(f"{r.status_code} {r.reason}", saida)
        return r.raw.stream(65536, decode_content=False)

    return app


def main() -> None:
    p = argparse.ArgumentParser(description="Faz o papel do Caddy do servidor no PC (Nexus e plataforma numa origem).")
    p.add_argument("--porta", type=int, default=5199)
    p.add_argument("--nexus", default="http://127.0.0.1:5170")
    p.add_argument("--plataforma", default="http://127.0.0.1:5150")
    p.add_argument("--modo", choices=("prefixo", "raiz"), default="prefixo")
    p.add_argument("--reescrita-do-servidor", action="store_true")
    args = p.parse_args()
    from waitress import serve
    print(f"Porta local em http://127.0.0.1:{args.porta} (modo {args.modo}"
          f"{', com a reescrita do servidor' if args.reescrita_do_servidor else ''}): "
          f"Nexus {args.nexus}, plataforma {args.plataforma}", flush=True)
    serve(criar_app(args.nexus, args.plataforma, args.modo, args.reescrita_do_servidor),
          listen=f"127.0.0.1:{args.porta}", threads=32)


if __name__ == "__main__":
    main()
