"""O pessoal do Fracttal ligado ao cadastro de pessoas do Nexus (Base > Acessos > Pessoas e setores; 12/10/2026, Levi: "Temos a
relação do time de campo, precisamos da relação do pessoal do fractall e também posteriormente vamos precisar relacionar
os setores, mas não tenho uma base em mãos agora para setores").

O cadastro de pessoas do Nexus é a "Relação Geral Colaboradores" do BD_Operações: o time de campo (124 colaboradores de
campo e 10 supervisores em 12/10). O Fracttal tem o pessoal inteiro (técnicos, supervisores, PCM, COS, engenharia,
gestão): 150 pessoas em 12/10, todas com e-mail; 144 com conta ativa (90 administradores, 54 de leitura). A ligação usa
o MESMO critério do login (`visao.pessoa_do_login`): o e-mail da ficha ou, sem ele, o nome de UMA pessoa (completo,
curto ou o do e-mail, "fulana.souza@" -> "fulana souza"); nome que serve a duas fichas não liga. Medido em 12/10: 62 das
150 ligam, 88 do Fracttal não têm ficha e 72 fichas não têm conta no Fracttal.

Setores: o Fracttal não diz o setor da pessoa (grupo 1, grupo 2 e campos próprios vazios nas 150). A lista de setores
e o setor de cada pessoa nascem na tela e vão ao banco: `setores.py`.

Só lê o Fracttal (o cliente de `nexus.campo.fracttal`, GET, 100 por página: 2 pedidos) e guarda por 1 hora. Nomes e
e-mails não vão ao banco: ficam na memória do servidor e na tela, que é só de administrador.
"""
import json
import threading
import time
import unicodedata

TTL_S = 3600
_CACHE: dict = {}
_TRAVA = threading.Lock()
ACESSO = {"administrator": "Administrador", "leitura": "Leitura"}
# Quem é da casa pelo domínio do e-mail. Medido em 12/10/2026: 107 da Grid Co.; 43 de fora (clientes com acesso de
# leitura, pelo domínio da empresa deles, e e-mails pessoais), todos entre os 88 sem ficha
DOMINIOS_GRID = ("gridco.com.br", "gridco.com")
ORIGENS = ("Grid Co.", "Externo")


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _curto(nome) -> str:
    """O "Nome padrão" (primeiro e último nome), a mesma regra do cadastro."""
    partes = str(nome or "").split()
    return f"{partes[0]} {partes[-1]}" if len(partes) > 1 else " ".join(partes)


def _local(email) -> str:
    e = str(email or "").strip().lower()
    return e.split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ") if "@" in e else ""


def da_api(p: dict) -> dict:
    """Uma pessoa do `personnel` do Fracttal no formato da tela."""
    acesso = str(p.get("groups_permissions_description") or "").strip()
    email = str(p.get("email") or p.get("account_email") or "").strip().lower()
    dominio = email.split("@")[-1] if "@" in email else ""
    return {"id": p.get("id_personnel"), "nome": " ".join(str(p.get("full_name") or p.get("name") or "").split()),
            "email": email,
            "acesso": ACESSO.get(acesso.lower(), acesso) if acesso else "sem acesso",
            "conta_ativa": p.get("account_active") is not False and bool(acesso),
            "dominio": dominio, "origem": ORIGENS[0] if dominio in DOMINIOS_GRID else ORIGENS[1]}


def ler_pessoal(forcar: bool = False, ler=None) -> dict:
    """{"pessoas": [...], "lido_em": epoch, "erro": ""}: o pessoal do Fracttal, guardado por 1 hora. `ler` troca o
    cliente (testes)."""
    with _TRAVA:
        g = _CACHE.get("pessoal")
        if g and not forcar and time.time() - g["lido_em"] < TTL_S and not g["erro"]:
            return g
    if ler is None:
        from ..campo import fracttal
        ler = fracttal.ler
    out, inicio, erro = [], 0, ""
    try:
        while True:
            r = ler(f"personnel?x=1&limit=100&start={inicio}")
            d = (r.get("data") if isinstance(r, dict) else r) or []
            out += d
            if len(d) < 100:
                break
            inicio += 100
    except Exception as ex:      # noqa: BLE001 — Fracttal fora, sem credencial, cota: a tela diz e mostra a última boa
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
    with _TRAVA:
        if erro:
            velho = _CACHE.get("pessoal")
            if velho and velho["pessoas"]:
                return dict(velho, erro=erro, velha=True)
            return {"pessoas": [], "lido_em": None, "erro": erro}
        # o código de cada pessoa (o `code` do Fracttal) fica à parte, fora da linha da tela (a coluna Código saiu em
        # 12/10/2026): é por ele que a OS diz quem a criou (`code_create_by`), e o nome dela no `created_by` nem sempre é
        # o do cadastro de pessoal (Painel do responsável, 29/10/2026: 8 das 9 pessoas do COS casam pelo código, 7 pelo
        # nome, e o código cobre mais OS)
        g = {"pessoas": sorted((da_api(p) for p in out), key=lambda x: _norm(x["nome"])), "lido_em": time.time(),
             "erro": "", "codigos": {p.get("id_personnel"): str(p.get("code") or "").strip() for p in out
                                     if str(p.get("code") or "").strip()}}
        _CACHE["pessoal"] = g
        return g


def fichas(pessoas_cadastro: list[dict], chave: str | None) -> list[dict]:
    """As fichas do cadastro (não excluídas) com o nome e o e-mail decifrados. Sem a chave, vazio."""
    if not chave:
        return []
    from ..dados import fatos as D
    from .cifra import CifraErro, Cofre
    cofre, out = Cofre(chave), []
    for p in pessoas_cadastro:
        pid = D._id(p.get("pessoa_id"))
        if not pid or not p.get("sensivel_cifrado") or str(p.get("excluido") or "").strip().lower() == "sim":
            continue
        try:
            s = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{pid}"))
        except (CifraErro, ValueError):
            continue
        out.append({"pessoa_id": pid, "nome": " ".join(str(s.get("nome") or "").split()),
                    "nome_padrao": " ".join(str(s.get("nome_padrao") or "").split()),
                    "email": str(s.get("email") or "").strip().lower(), "vinculo": str(p.get("vinculo") or ""),
                    "cargo": str(p.get("cargo") or ""), "equipe_id": D._id(p.get("equipe_id")),
                    "status": str(p.get("status") or "")})
    return out


def ligar(pessoal: list[dict], fs: list[dict], nome_equipe: dict | None = None) -> dict:
    """Cada pessoa do Fracttal com a ficha do cadastro (`ficha`, `por`: "e-mail" ou "nome"), e as fichas sem conta no
    Fracttal. O critério é o do login: e-mail da ficha; sem ele, o nome de UMA ficha; dois achados = não liga."""
    nome_equipe = nome_equipe or {}
    variantes = {f["pessoa_id"]: {_norm(x) for x in (f["nome"], f["nome_padrao"], _curto(f["nome"]), _curto(f["nome_padrao"]))
                                  if x} for f in fs}
    linhas, usadas = [], {}
    for p in pessoal:
        alvos = {x for x in (_norm(p["nome"]), _norm(_curto(p["nome"])), _norm(_local(p["email"]))) if x}
        por_email = [f for f in fs if p["email"] and f["email"] == p["email"]]
        por_nome = [f for f in fs if f not in por_email and alvos & variantes[f["pessoa_id"]]]
        achados, por = (por_email, "e-mail") if por_email else (por_nome, "nome")
        ficha = achados[0] if len(achados) == 1 else None
        linha = dict(p, ficha=ficha, por=por if ficha else "", ambiguo=len(achados) > 1,
                     equipe=nome_equipe.get(ficha["equipe_id"], "") if ficha else "")
        linhas.append(linha)
        if ficha:
            usadas.setdefault(ficha["pessoa_id"], []).append(linha)
    for lst in usadas.values():          # a mesma ficha para duas contas do Fracttal: as duas ficam marcadas
        if len(lst) > 1:
            for linha in lst:
                linha["repetida"] = True
    sem_conta = [dict(f, equipe=nome_equipe.get(f["equipe_id"], "")) for f in fs if f["pessoa_id"] not in usadas]
    sem_conta.sort(key=lambda f: (f["status"].lower() != "ativo", _norm(f["nome_padrao"] or f["nome"])))
    return {"linhas": linhas, "sem_conta": sem_conta, "ligadas": sum(1 for x in linhas if x["ficha"]),
            "sem_ficha": sum(1 for x in linhas if not x["ficha"]), "ambiguas": sum(1 for x in linhas if x["ambiguo"]),
            "repetidas": sum(1 for x in linhas if x.get("repetida"))}


def filtrar(linhas: list[dict], q: str = "", ligacao: str = "", acesso: str = "", origem: str = "",
            setor: str = "") -> list[dict]:
    """`setor`: "" = todos, "sem" = sem setor, ou o setor_id (texto) da linha (`setor_id`, posto pela tela)."""
    termo = _norm(q)
    out = []
    for x in linhas:
        if ligacao == "ligadas" and not x["ficha"]:
            continue
        if ligacao == "sem_ficha" and x["ficha"]:
            continue
        if acesso and x["acesso"] != acesso:
            continue
        if origem and x["origem"] != origem:
            continue
        if setor == "sem" and x.get("setor_id"):
            continue
        if setor and setor != "sem" and str(x.get("setor_id") or "") != setor:
            continue
        if termo and termo not in _norm(" ".join((x["nome"], x["email"], x["equipe"], x.get("setor") or ""))):
            continue
        out.append(x)
    return out
