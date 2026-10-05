"""A ligação do que o Campo · App grava com o cadastro do Nexus, por ID (Levi, 05/10/2026: "pode ligar ao usina_id e
pessoa_id do cadastro"; a visão: os setores ligados pela base de dados da API).

- usina_id: o `de_para` do `cadastro_nexus` já diz qual usina o Fracttal chama de quê (sistema "Fracttal ·
  Classificação 1", chave = o nome do grupo da OS, "Thopen - Altair 1 - SP"), que é o `groups_1_description` de cada
  tarefa. 188 usinas em 05/10.
- pessoa_id: o nome do técnico no Fracttal contra o nome (e o nome padrão) da pessoa no cadastro, que vai CIFRADO no
  banco (`sensivel_cifrado`, contexto `banco/pessoas/<id>`, chave NEXUS_CHAVE_CADASTRO). O Nexus decifra na hora; o
  nome não sai daqui, só o ID. Nome que bate em duas pessoas (homônimo) não liga: ID errado é pior que ID nenhum.

- pessoa por HMAC: o App de Campo (v226, 05/10) manda a pessoa dos fechamentos, PT, zeladoria e decisões como
  HMAC-SHA256 do e-mail com a chave NEXUS_PESSOA_HMAC (a mesma nos dois lados): o Nexus calcula o mesmo código para o
  e-mail de cada pessoa do cadastro e troca pelo pessoa_id. E-mail que bate em duas fichas não liga.

Lê o cadastro pela API (leitura pública), uma vez por rodada do coletor.
"""
import hashlib
import hmac
import json
import re
import unicodedata

from . import banco_campo

WORKBOOK_CADASTRO = "cadastro_nexus"
SISTEMA_FRACTTAL = "Fracttal · Classificação 1"


def _norm(s) -> str:
    # sem acento, sem caixa, espaço único, e o hífen sem espaço em volta: o Fracttal tem "Thopen - Coração 1 - SC" e
    # "Thopen - Coração 1- SC" para a mesma usina (05/10)
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s*-\s*", "-", " ".join(s.split()))


def _abas(base, s) -> dict:
    r = s.get(f"{base}/api/sheets", timeout=60)
    r.raise_for_status()
    return {x["sheet_name"]: x["id"] for x in r.json() if x.get("workbook_key") == WORKBOOK_CADASTRO}


def codigo_da_pessoa(chave: str, email) -> str | None:
    """O mesmo código que o App manda (`_pessoa_hmac` do function_app.py v226)."""
    em = str(email or "").strip().lower()
    if not chave or not em:
        return None
    return hmac.new(chave.encode("utf-8"), em.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def mapas(config, sessao=None) -> dict:
    """{"usina": {grupo no Fracttal: usina_id}, "pessoa": {nome: pessoa_id}, "hmac": {código do App: pessoa_id}}.
    Sem a chave do cadastro, só o mapa das usinas; sem NEXUS_PESSOA_HMAC, o mapa dos códigos vem vazio."""
    import requests
    s = sessao or requests
    base = (config.get("GRIDCO_DB_API") or banco_campo.BASE_API).rstrip("/")
    abas = _abas(base, s)
    usina = {}
    if "de_para" in abas:
        for d in banco_campo._linhas_da_aba(base, s, abas["de_para"]):
            if str(d.get("sistema") or "").strip() == SISTEMA_FRACTTAL and d.get("usina_id") not in (None, ""):
                usina[_norm(d.get("chave_externa"))] = int(float(d["usina_id"]))
    pessoa, por_codigo = {}, {}
    chave_hmac = config.get("NEXUS_PESSOA_HMAC")
    chave = config.get("NEXUS_CHAVE_CADASTRO")
    if chave and "pessoas" in abas:
        from ..cadastro.cifra import CifraErro, Cofre
        cofre = Cofre(chave)
        donos, codigos = {}, {}
        for p in banco_campo._linhas_da_aba(base, s, abas["pessoas"]):
            if str(p.get("excluido") or "").strip().lower() == "sim" or not p.get("sensivel_cifrado"):
                continue
            pid = int(float(p["pessoa_id"]))
            try:
                segredo = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{pid}"))
            except (CifraErro, ValueError):
                continue
            for campo in ("nome", "nome_padrao"):
                n = _norm(segredo.get(campo))
                if n:
                    donos.setdefault(n, set()).add(pid)
            cod = codigo_da_pessoa(chave_hmac, segredo.get("email"))
            if cod:
                codigos.setdefault(cod, set()).add(pid)
        pessoa = {n: next(iter(ids)) for n, ids in donos.items() if len(ids) == 1}
        por_codigo = {c: next(iter(ids)) for c, ids in codigos.items() if len(ids) == 1}
    return {"usina": usina, "pessoa": pessoa, "hmac": por_codigo}


def usina_id(m: dict, grupo) -> int | None:
    return (m or {}).get("usina", {}).get(_norm(grupo))


def pessoa_id(m: dict, nome) -> int | None:
    return (m or {}).get("pessoa", {}).get(_norm(nome))


def pessoa_id_do_codigo(m: dict, codigo) -> int | None:
    """O pessoa_id do código que o App manda (vários, separados por ;, devolvem o do primeiro)."""
    primeiro = str(codigo or "").split(";")[0].strip()
    return (m or {}).get("hmac", {}).get(primeiro) if primeiro else None
