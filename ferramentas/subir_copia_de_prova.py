"""Sobe uma CÓPIA DE PROVA do Nexus noutra porta: sem carga no banco, sem ler o Fracttal ao subir, sem gravar fora.

Por quê (porta única com a plataforma, 09/10/2026; Levi: "a partir de segunda quero o Nexus como link principal"): a
5070 do PC é o Nexus que o Levi usa e não reinicia. Para provar uma mudança, sobe-se o código da worktree noutra porta,
ao lado de uma cópia da plataforma (`plataforma/subir_copia_de_prova.py` no PerformancePainel), e não a 5070.

O que esta cópia NÃO faz, de propósito:
- a carga de hora em hora no banco (`NEXUS_CARGA_DADOS=0`): a do PC do Levi e a do servidor já disputam a hora;
- as leituras do Fracttal ao subir (`NEXUS_CAMPO_AQUECER=0`): a cota é de 200/min para a empresa inteira;
- o coletor do Campo (`NEXUS_CAMPO_COLETOR` vazio);
- nenhum pedido sai para a SunOp ou a API PV, e nenhum pedido que não seja GET/HEAD/OPTIONS sai da máquina (gravação
  no banco, no Fracttal, no GitHub do PCM): a trava abaixo recusa com `ConnectionError`, e a tela mostra a falha. Por
  isso o login pelo Fracttal (um POST) não funciona aqui: entre pela senha de administrador (`/entrar?admin=1`, a
  `NEXUS_SENHA_ADMIN` do `.env`, sem nunca imprimi-la).
O cookie sai sem `Secure` (http local), como no `app.py`. Variável `NEXUS_*` do ambiente vence o `.env` (é a regra do
`nexus/config.py`), então dá para apontar outra plataforma sem mexer no `.env`.

Uso, da raiz do repositório:
    python ferramentas/subir_copia_de_prova.py                                   porta 5170
    python ferramentas/subir_copia_de_prova.py --porta 5171 --plataforma http://127.0.0.1:5150
"""
import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
FONTES_PAGAS = ("sunop.net", "pvoperation.com")
LOCAIS = ("127.0.0.1", "localhost", "::1")
METODOS_DE_LEITURA = ("GET", "HEAD", "OPTIONS")


def motivo_da_recusa(metodo: str, url: str) -> str | None:
    """None = pode sair. Fonte paga sai nunca; para fora da máquina, só leitura."""
    host = (urlsplit(url).hostname or "").lower()
    if any(p in host for p in FONTES_PAGAS):
        return "fonte paga"
    if host and host not in LOCAIS and (metodo or "GET").upper() not in METODOS_DE_LEITURA:
        return "gravação fora da máquina"
    return None


def instalar_trava() -> None:
    """Antes de importar o Nexus: tudo o que usa `requests` passa pelo HTTPAdapter.send, e o urllib pelo urlopen."""
    import urllib.error
    import urllib.request

    import requests
    import requests.adapters

    enviar = requests.adapters.HTTPAdapter.send

    def send(self, pedido, *a, **k):
        motivo = motivo_da_recusa(pedido.method, pedido.url)
        if motivo:
            print(f"[cópia de prova] recusado ({motivo}): {pedido.method} {urlsplit(pedido.url).hostname}", flush=True)
            raise requests.exceptions.ConnectionError(f"cópia de prova: {motivo} recusada")
        return enviar(self, pedido, *a, **k)

    requests.adapters.HTTPAdapter.send = send
    abrir = urllib.request.urlopen

    def urlopen(pedido, *a, **k):
        url = pedido if isinstance(pedido, str) else pedido.full_url
        metodo = "GET" if isinstance(pedido, str) else pedido.get_method()
        motivo = motivo_da_recusa(metodo, url)
        if motivo:
            print(f"[cópia de prova] recusado ({motivo}): {metodo} {urlsplit(url).hostname}", flush=True)
            raise urllib.error.URLError(f"cópia de prova: {motivo} recusada")
        return abrir(pedido, *a, **k)

    urllib.request.urlopen = urlopen


def main() -> None:
    p = argparse.ArgumentParser(description="Cópia de prova do Nexus noutra porta (sem carga, sem Fracttal ao subir).")
    p.add_argument("--porta", type=int, default=5170)
    p.add_argument("--plataforma", help="NEXUS_PLATAFORMA_URL desta cópia (ex.: http://127.0.0.1:5150)")
    args = p.parse_args()
    if args.porta == 5070:
        sys.exit("A 5070 é o Nexus do Levi: use outra porta.")

    os.environ["NEXUS_CARGA_DADOS"] = "0"
    os.environ["NEXUS_CAMPO_AQUECER"] = "0"
    os.environ["NEXUS_CAMPO_COLETOR"] = ""
    if args.plataforma:
        os.environ["NEXUS_PLATAFORMA_URL"] = args.plataforma
    instalar_trava()

    sys.path.insert(0, str(RAIZ))
    os.chdir(RAIZ)                     # o .env aponta caminhos relativos à raiz (dados/campo/identidades.json)
    from waitress import serve

    from nexus import create_app
    from nexus.campo import instalar as instalar_campo
    from nexus.config import ConfigErro
    from nexus.dados import instalar as instalar_dados
    from nexus.engenharia import instalar as instalar_engenharia

    try:
        app = create_app()
    except ConfigErro as erro:
        sys.exit(f"Nexus não subiu: {erro}")
    app.config["SESSION_COOKIE_SECURE"] = False
    instalar_campo(app)
    instalar_dados(app)
    instalar_engenharia(app)
    print(f"Nexus (cópia de prova) em http://127.0.0.1:{args.porta}  plataforma: "
          f"{app.config.get('NEXUS_PLATAFORMA_URL') or '(sem)'}", flush=True)
    serve(app, listen=f"127.0.0.1:{args.porta}", threads=8)


if __name__ == "__main__":
    main()
