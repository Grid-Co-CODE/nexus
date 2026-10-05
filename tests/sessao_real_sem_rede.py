"""`requests.Session` de VERDADE com um adaptador falso montado: o caminho do requests roda inteiro, sem abrir socket.

Por que existe (04/10/2026, re-revisão do c6810e8): a sessão falsa dos testes da ponte (`request()` devolvendo uma
resposta pronta) pula o que o requests faz de verdade. Em `Session.send`, mesmo com `allow_redirects=False`, o requests
LÊ a Location (`resolve_redirects(..., yield_requests=True)` para preencher `r._next`): `urlparse` da Location e
`Location.encode("latin1").decode("utf8")`, e os dois levantam ValueError (`UnicodeDecodeError` é subclasse) DENTRO de
`Session.request`. Os testes com sessão falsa passavam e a rota devolvia 500 em produção. Quem quer provar o que a ponte
faz com uma Location que o requests não consegue ler tem de passar pelo requests de verdade."""
import io

import requests
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict


class AdaptadorFalso(BaseAdapter):
    """Responde na ordem com (status, Location) e guarda cada `PreparedRequest` que o requests mandaria à rede."""

    def __init__(self, *respostas):
        super().__init__()
        self.respostas, self.pedidos = list(respostas), []

    def send(self, request, **kwargs):
        self.pedidos.append(request)
        status, location = self.respostas.pop(0)
        r = requests.Response()
        r.status_code, r.url, r.request = status, request.url, request
        r.headers = CaseInsensitiveDict({"Content-Type": "application/json", "X-Nexus-Leitura-Ok": "1"})
        if location is not None:
            # como o http.client entrega: o valor do cabeçalho já decodificado em latin-1 (str), não bytes
            r.headers["Location"] = location
        r._content = b"{}"
        r.raw = io.BytesIO(b"{}")          # `Response.close()` e `extract_cookies_to_jar` olham o `raw`
        return r

    def close(self):
        pass


def sessao_real(*respostas):
    """(sessão, adaptador): `requests.Session` real, sem proxy nem netrc do ambiente, com tudo indo ao adaptador falso."""
    s = requests.Session()
    s.trust_env = False
    ad = AdaptadorFalso(*respostas)
    s.mount("https://", ad)
    s.mount("http://", ad)
    return s, ad
