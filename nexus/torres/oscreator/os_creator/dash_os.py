"""dash_os.py: a fila de OS sugeridas do dashboard de O&M (supervisório).

O dashboard calcula os trackers parados há mais de 36 h e os recorrentes atrás de uma senha; aqui só se lê, e o PCM confirma e
cria a OS pelo Criar OS. A configuração (url e senha) mora na pasta de dados do usuário (`api.DASH_CONFIG_FILE`).

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

import json
import os
import requests


def load_dash_config() -> dict:
    """Config do dashboard: {url, senha, tunnel_file}. url/senha p/ logar; tunnel_file (opcional) =
    caminho do tunnel_url.txt do dashboard (no OneDrive) p/ pegar a URL atual sozinho."""
    try:
        if os.path.exists(api.DASH_CONFIG_FILE):
            with open(api.DASH_CONFIG_FILE, encoding="utf-8") as f:
                d = json.load(f)
                return {"url": (d.get("url") or "").strip(),
                        "senha": d.get("senha") or "",
                        "tunnel_file": (d.get("tunnel_file") or "").strip()}
    except Exception:
        pass
    return {"url": "", "senha": "", "tunnel_file": ""}


def save_dash_config(url: str, senha: str, tunnel_file: str = "") -> None:
    with open(api.DASH_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"url": (url or "").strip(), "senha": senha or "",
                   "tunnel_file": (tunnel_file or "").strip()}, f, ensure_ascii=False)


def _dash_url(cfg: dict) -> str:
    """URL efetiva: se houver tunnel_file legível, usa o conteúdo dele (sempre fresco); senão a url fixa."""
    tf = cfg.get("tunnel_file")
    if tf and os.path.exists(tf):
        try:
            with open(tf, encoding="utf-8") as f:
                u = f.read().strip()
            if u.startswith("http"):
                return u.rstrip("/")
        except Exception:
            pass
    return (cfg.get("url") or "").strip().rstrip("/")


def fetch_os_sugeridas(cfg: dict = None) -> list:
    """Loga no dashboard (sessão + DASH_PASSWORD) e busca /api/trackers/os-sugeridas. Devolve a lista
    de sugestões (rows). Lança RuntimeError com mensagem amigável se URL/senha faltarem ou der erro."""
    cfg = cfg or api.load_dash_config()
    url = api._dash_url(cfg)
    senha = cfg.get("senha") or ""
    if not url:
        raise RuntimeError("Configure a URL do dashboard (botão Configurar).")
    s = requests.Session()
    try:
        if senha:
            s.post(f"{url}/login", data={"senha": senha}, timeout=20, allow_redirects=False)
        r = s.get(f"{url}/api/trackers/os-sugeridas", timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f"Não consegui falar com o dashboard ({url}). O túnel está no ar? [{e}]")
    if r.status_code == 401:
        raise RuntimeError("Login recusado — confira a senha do dashboard (DASH_PASSWORD).")
    if r.status_code != 200:
        raise RuntimeError(f"Dashboard respondeu HTTP {r.status_code}.")
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError("Resposta do dashboard não é JSON (sessão/URL errada?).")
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    return data.get("rows", [])


import api  # noqa: E402 — no fim: o `api` importa este módulo
