"""Quem é a pessoa da Gestão, o que cada um lê e o que cada pedido de gravação pode fazer: o RLS do Supabase no Nexus.

**O passe da Gestão.** O site do SSO mora em outro endereço (`sso-zeladoria.gridco.com.br`, no Cloudflare do HEAD da
zeladoria; Levi, 12/11/2026: "Esse site fica a parte do nexus"). A Gestão entra pelo login do Nexus: o site manda a
pessoa ao `/t/sso/voltar`, que exige o login, e ela volta ao site com um passe assinado no fragmento do endereço (o `#`
não vai a servidor nenhum). O passe vale 8 h e diz só o e-mail do login (ou que é o administrador); o site o manda no
`Authorization`, como mandava o token do Supabase. A cada pedido o perfil é relido: quem perde a aprovação perde o acesso
na hora, sem esperar o passe vencer.

**O perfil.** A pessoa é casada pelo e-mail do login com o `iv_perfis`, como a Zeladoria faz com o `perfis` do Radar
(`nexus/zeladoria/leitura.quem_sou`). Sem linha, o id dela é um uuid fixo do e-mail (o mesmo em toda máquina), e o app
cria a linha "pendente" no 1º acesso, como fazia no Supabase. O administrador do Nexus vale como gestor aprovado.
"""
from __future__ import annotations

import uuid

from itsdangerous import BadData, URLSafeTimedSerializer

from . import arquivos as A
from . import esquema as E
from .esquema import Recusa

VALIDADE_PASSE_S = 8 * 3600
_ESPACO = uuid.UUID("6f1d2a8e-5c3b-4e7a-9b1f-0a2c4d6e8f10")         # o espaço dos uuid do Nexus para o SSO
ADMIN_ID = str(uuid.uuid5(_ESPACO, "nexus-admin"))


def _assinador(app) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.secret_key, salt="nexus/sso/passe")


def emitir_passe(app, email: str, admin: bool) -> str:
    return _assinador(app).dumps({"e": str(email or "").strip().lower(), "a": 1 if admin else 0})


VALIDADE_ADMIN_SEM_EMAIL_S = 2 * 3600


def ler_passe(app, passe: str | None, admins=None) -> dict | None:
    """{"email", "admin"} do passe válido; None sem passe, vencido ou mexido. O "administrador" do passe é reconferido a
    cada pedido (revisão de 12/11/2026): com e-mail, ele tem de estar na lista de administradores de agora (`admins`, um
    conjunto de e-mails; None = não reconfere); sem e-mail (a senha de administrador), o passe vale 2 h, e não 8."""
    if not passe:
        return None
    try:
        d, quando = _assinador(app).loads(passe, max_age=VALIDADE_PASSE_S, return_timestamp=True)
    except BadData:
        return None
    if not isinstance(d, dict):
        return None
    email, admin = str(d.get("e") or ""), bool(d.get("a"))
    if admin and email and admins is not None:
        admin = email in admins
    if admin and not email:
        import time
        if time.time() - quando.timestamp() > VALIDADE_ADMIN_SEM_EMAIL_S:
            return None
    return {"email": email, "admin": admin}


def id_do_email(email: str) -> str:
    return str(uuid.uuid5(_ESPACO, "email:" + str(email or "").strip().lower()))


FORNECEDOR = {"id": None, "email": None, "status": "fornecedor", "papel": "fornecedor"}


def quem_sou(est: dict, passe: dict | None) -> dict:
    """{"id", "email", "status", "papel"}: papel "fornecedor" (sem passe), "pendente" ou "gestao" (aprovada)."""
    if not passe:
        return dict(FORNECEDOR)
    email, admin = passe["email"], passe["admin"]
    perfis = est["abas"].get("iv_perfis", [])
    linha = next((p for p in perfis if email and str(p.get("email") or "").strip().lower() == email), None)
    if linha is None and admin:
        # o administrador pela senha do Nexus não tem e-mail: a linha dele é a do id fixo
        meu = id_do_email(email) if email else ADMIN_ID
        linha = next((p for p in perfis if _igual(p.get("user_id"), meu)), None)
        if linha is None:
            return {"id": meu, "email": email or "administrador", "status": "aprovado", "papel": "gestao"}
    if linha is not None:
        st = "aprovado" if admin else (linha.get("status") or "pendente")
        return {"id": linha.get("user_id"), "email": linha.get("email"), "status": st,
                "papel": "gestao" if st == "aprovado" else "pendente"}
    return {"id": id_do_email(email), "email": email, "status": "pendente", "papel": "pendente"}


def _igual(a, b) -> bool:
    return a == b or (a is not None and b is not None and str(a) == str(b))


def _filtrar(linhas: list, filtros: list) -> list:
    for op, col, val in filtros:
        if op == "eq":
            linhas = [l for l in linhas if _igual(l.get(col), val)]
        elif op == "neq":
            linhas = [l for l in linhas if not _igual(l.get(col), val)]
        else:
            raise Recusa(f"filtro {op} não existe no SSO")
    return linhas


def ler(est: dict, view: str, *, filtros: list, ordem: list, limite: int | None, colunas: list | None,
        quem: dict) -> list:
    """As linhas como o PostgREST devolvia ao app, já com o RLS: o fornecedor só a sessão ativa, a própria visualização
    pelo id e as usinas do diário; o pendente, a própria linha do perfil; a Gestão, tudo."""
    aba = E.aba_da_view(view)
    papel = quem["papel"]
    base = [dict(l) for l in est["abas"].get(aba, [])]
    if aba == "iv_perfis" and papel != "gestao":
        base = [l for l in base if quem.get("id") and _igual(l.get("user_id"), quem["id"])]
    elif papel != "gestao":
        if not E.pode("fornecedor", aba, "select"):
            return []
        if aba == "iv_sessoes_video":
            base = [l for l in base if l.get("ativo") is True]
        elif aba == "iv_visualizacoes":
            # a visualização sem o id no filtro é a lista de todas: o RLS deixava, mas não há por quê (seção 14 do pacote)
            if not any(op == "eq" and col == "id" for op, col, _v in filtros):
                return []
            base = [{c: l.get(c) for c in ("id", "sessao_id", "progresso_max_segundos", "concluido")} for l in base]
    base = _filtrar(base, filtros)
    # a ordem do Postgres: a primeira coluna manda; o vazio vai por último no crescente e primeiro no decrescente
    for col, desc in reversed(ordem or []):
        com = [l for l in base if l.get(col) is not None]
        com.sort(key=lambda l: (str(type(l[col])), l[col]), reverse=desc)
        sem = [l for l in base if l.get(col) is None]
        base = sem + com if desc else com + sem
    if limite is not None:
        base = base[:max(0, int(limite))]
    if colunas:
        base = [{c: l.get(c) for c in colunas} for l in base]
    return base


def preparar(est: dict, quem: dict, ops: list, *, hosts: set) -> list:
    """Os pedidos do app ([{"op", "view", "linhas" | "patch", "filtros"}]) conferidos e prontos para o gravador
    ([{"op", "aba", ...}]). Recusa o que o RLS recusava; na linha do fornecedor, o servidor decide os campos dele."""
    prontos = []
    papel = quem["papel"]
    for op in ops:
        nome = op.get("op")
        if nome not in ("insert", "upsert", "update", "delete"):
            raise Recusa("pedido inválido")
        aba = E.aba_da_view(op.get("view"))
        filtros = [tuple(f) for f in (op.get("filtros") or [])]
        if not all(len(f) == 3 and f[0] in ("eq", "neq") and isinstance(f[1], str) for f in filtros):
            raise Recusa("filtro inválido")
        linhas = op.get("linhas") or []
        if not isinstance(linhas, list) or not all(isinstance(l, dict) for l in linhas):
            raise Recusa("linhas inválidas")
        if aba == "iv_perfis" and papel != "gestao":
            # o pendente só cria a PRÓPRIA linha, e ela nasce pendente (o `perfis_self_insert` do Supabase)
            if nome != "insert" or papel != "pendente" or len(linhas) != 1:
                raise Recusa("sem permissão")
            linha = linhas[0]
            if not _igual(linha.get("user_id"), quem["id"]):
                raise Recusa("sem permissão")
            prontos.append({"op": "insert", "aba": aba, "linhas": [
                {"user_id": quem["id"], "email": quem["email"], "status": "pendente"}]})
            continue
        papel_do_rls = "gestao" if papel == "gestao" else "fornecedor"
        precisa = "insert" if nome == "insert" else ("insert", "update") if nome == "upsert" else nome
        if not all(E.pode(papel_do_rls, aba, p) for p in ((precisa,) if isinstance(precisa, str) else precisa)):
            raise Recusa("sem permissão")
        if papel_do_rls == "fornecedor":
            linhas = [_do_fornecedor(est, aba, l, hosts) for l in linhas]
        else:
            linhas = [A.sem_assinatura(l) for l in linhas]
        pronto = {"op": nome, "aba": aba, "linhas": linhas, "filtros": filtros}
        if nome == "update":
            pronto["patch"] = A.sem_assinatura(op.get("patch") or {})
            if not isinstance(pronto["patch"], dict):
                raise Recusa("pedido inválido")
            if not filtros:
                raise Recusa("update sem filtro")          # o PostgREST também recusava
        if nome == "delete" and not filtros:
            raise Recusa("delete sem filtro")
        prontos.append(pronto)
    return prontos


MAX_LINHA = 1024 * 1024       # a maior linha real tinha 130 KB (uma vistoria com assinatura, 12/11/2026)


def _do_fornecedor(est: dict, aba: str, linha: dict, hosts: set) -> dict:
    import json
    # a linha grande demais: sem teto, um anônimo mandava 120 linhas de 10 MB por hora, e cada lote recifra e remonta o
    # livro inteiro na memória do Nexus (revisão de 12/11/2026)
    if len(json.dumps(linha, ensure_ascii=False, default=str)) > MAX_LINHA:
        raise Recusa("envio grande demais")
    # o endereço da foto vai ao banco sem a assinatura de 12 h que o envio devolveu para a miniatura
    nova = A.sem_assinatura({c: v for c, v in linha.items() if c not in E.DO_SERVIDOR.get(aba, ())})
    if aba == "vistoria_checklists" and nova.get("fase") not in ("antes", "depois"):
        raise Recusa("a fase da vistoria é antes ou depois")          # a fase fica em claro: só a lista fechada
    ruins = A.estranhas(nova, hosts)
    if ruins:
        raise Recusa("endereço de arquivo que não é do SSO: " + ruins[0])
    if aba == "iv_visualizacoes":
        nova = {c: nova.get(c) for c in ("id", "sessao_id") if c in nova}
    if aba in ("iv_visualizacoes", "iv_presencas"):
        sessoes = {str(s.get("id")): s for s in est["abas"].get("iv_sessoes_video", [])}
        s = sessoes.get(str(nova.get("sessao_id")))
        if not s or s.get("ativo") is not True:
            raise Recusa("sessão de integração não encontrada")
        if aba == "iv_presencas" and nova.get("visualizacao_id") is not None:
            v = next((x for x in est["abas"].get("iv_visualizacoes", []) if _igual(x.get("id"), nova["visualizacao_id"])),
                     None)
            if v is None or not _igual(v.get("sessao_id"), nova.get("sessao_id")):
                raise Recusa("visualização não encontrada")
    if aba == "diario_usinas":
        nome = " ".join(str(nova.get("nome") or "").split())
        if not nome or len(nome) > 120:
            raise Recusa("nome de usina inválido")
        nova = {"nome": nome}
    return nova
