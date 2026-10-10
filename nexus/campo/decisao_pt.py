"""A decisão da PT tomada no Nexus, gravada no banco (Levi, 05/10/2026: "Técnico faz APR e PT -> Chega no PG -> Atualiza
para os stakeholders -> Atualiza na aprovação de PT -> Supervisor faz -> Fica salvo!").

Quem assina entra com o login do Fracttal do OS Creator (Levi: "utilize o login do fractal do OS Creator Web que já dá
certo"): a sessão dele (cookie `os_sessao`, só em /os) traz o e-mail de quem entrou. Por isso as rotas que leem quem
assina moram em /os/_nexus/... (`nexus/torres/campo/assinatura.py`).

O livro `nexus_pt_decisoes` · `decisoes` (grão: 1 linha = 1 decisão tomada no Nexus sobre uma PT). A API do banco tem
LEITURA ABERTA: a pessoa vai só como o código do e-mail (`NEXUS_PESSOA_HMAC`, o mesmo do App), nunca nome nem e-mail; o
motivo (o que o técnico lê quando a PT é negada) vai mascarado e curto.

Quem aplica a decisão no campo é o App: ele confere se quem assinou pode assinar aquela PT (`_pt_pode_assinar`), se a
PT ainda está aguardando e se a decisão é recente, e só então libera ou nega (a pausa no Fracttal, o anexo). Até o App
ler este livro, a decisão fica salva aqui e o técnico continua esperando a decisão pelo App.

QUEM PODE DECIDIR (Levi, 09/10/2026: "A pessoa que pode aprovar a PT é: Supervisor de Campo, Gestor de contrato, admin
ou pessoa do COS"): o Supervisor de Campo da região da usina (com a vaga aberta, o Coordenador de Campo), o gestor de
contrato da usina, quem tem o vínculo COS no cadastro de pessoas e um administrador do Nexus (`aprovadores`,
`pode_decidir`). Quem assina é a pessoa do login do Fracttal, achada no cadastro pelo e-mail ou pelo nome de UMA pessoa
(`_Base.pessoa_do_login`); sem a chave do cadastro, só o administrador decide. O App precisa aceitar o mesmo conjunto
quando passar a ler este livro.
"""
import re
import threading
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..cadastro.esquema import VINCULO_COS
from ..dados import fatos as D
from ..dados import livros
from . import visao
from .ligacao_cadastro import codigo_da_pessoa

LIVRO, NOME_LIVRO, ABA = "nexus_pt_decisoes", "Nexus · decisões de PT", "decisoes"
CAB = ("decidida_em", "data_id", "pt", "os", "usina_id", "decisao", "motivo", "decidida_por_hmac", "login", "origem")
DECISOES = {"de_acordo": "De acordo", "negada": "Não autorizo"}
MOTIVO_MAX = 400
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()      # um processo grava por vez: duas decisões juntas não se apagam (o livro é trocado inteiro)


class Recusada(ValueError):
    """A decisão não pode ser gravada: o texto diz por quê, para a tela mostrar."""


def mascarar(texto) -> str:
    """Tira do motivo o que é dado pessoal (e-mail, telefone, CPF): o livro é de leitura aberta."""
    s = " ".join(str(texto or "").split())
    s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[e-mail]", s)
    s = re.sub(r"\d[\d .()/-]{7,}\d", "[número]", s)
    return s[:MOTIVO_MAX]


def aprovadores(p: dict, b=None) -> dict:
    """Quem pode dar o De acordo nesta PT: {"ids": {papel: pessoa_id}, "cos": {pessoa_id}, "texto"}. O texto é o que a
    tela e a recusa dizem ("Supervisor de Campo da Sudeste 03 (Fulana), gestor de contrato Beltrano, alguém do COS ou
    um administrador")."""
    b = b or visao._Base()
    uid = D._id(p.get("usina_id"))
    rid = b.regiao_da_usina(uid) if uid else None
    r = b.regiao.get(rid) or {}
    u = b.por_id.get(uid) or {}
    ids = {"supervisor de campo": r.get("supervisor_id"),
           "coordenador de campo": None if r.get("supervisor_id") else r.get("coordenador_id"),
           "gestor de contrato": D._id(u.get("gestor_contrato_id"))}
    cos = {D._id(x.get("pessoa_id")) for x in b.pessoas
           if str(x.get("vinculo") or "").strip() == VINCULO_COS and str(x.get("excluido") or "").lower() != "sim"}
    partes = []
    if r:
        sup = b.nome_da_pessoa(r.get("supervisor_id"), "Supervisor") if r.get("supervisor_id") else ""
        coord = b.nome_da_pessoa(r.get("coordenador_id"), "Coordenador") if r.get("coordenador_id") else ""
        partes.append(f"o Supervisor de Campo da {r['nome']} ({sup})" if sup else
                      (f"o Coordenador de Campo da {r['nome']} ({coord}), com a vaga de supervisor aberta" if coord
                       else f"o Supervisor de Campo da {r['nome']} (vaga)"))
    if ids["gestor de contrato"]:
        partes.append(f"o gestor de contrato ({b.nome_da_pessoa(ids['gestor de contrato'], 'Gestor')})")
    partes.append("alguém do COS" if cos else "alguém do COS (ninguém com o vínculo COS no cadastro ainda)")
    partes.append("um administrador")
    texto = ", ".join(partes[:-1]) + " ou " + partes[-1]
    return {"ids": {k: v for k, v in ids.items() if v}, "cos": cos, "texto": texto[0].upper() + texto[1:]}


def pode_decidir(p: dict, email: str, nome: str = "", admin: bool = False, b=None) -> tuple[bool, str]:
    """(pode, papel ou o porquê não). Administrador do Nexus sempre pode."""
    if admin:
        return True, "administrador"
    b = b or visao._Base()
    a = aprovadores(p, b)
    pid = b.pessoa_do_login(email, nome)
    papel = next((k for k, v in a["ids"].items() if pid and v == pid), None) or ("COS" if pid and pid in a["cos"] else None)
    if papel:
        return True, papel
    return False, f"Quem pode dar o De acordo nesta PT: {a['texto'][0].lower()}{a['texto'][1:]}."


def decisoes() -> list[dict]:
    """As decisões já gravadas pelo Nexus (sem cópia: quem decide precisa ver a última)."""
    return livros.ler(visao._base(), visao._sessao(), LIVRO, ABA)


def da_pt(numero) -> dict | None:
    n = str(numero or "").strip()
    return next((d for d in reversed(decisoes()) if str(d.get("pt") or "") == n), None)


def decidir(numero, decisao: str, motivo: str, email: str, nome: str = "", admin: bool = False) -> dict:
    """Grava a decisão e confere no banco. Recusa: decisão inválida, negar sem motivo, quem não pode decidir esta PT
    (`pode_decidir`), PT que não existe, que já não está aguardando no livro do App ou que já tem decisão do Nexus (o
    primeiro que decide vale, como no App)."""
    cfg = current_app.config
    if decisao not in DECISOES:
        raise Recusada("A decisão precisa ser De acordo ou Não autorizo.")
    motivo = mascarar(motivo)
    if decisao == "negada" and len(motivo) < 3:
        raise Recusada("Escreva o motivo: é o que o técnico lê quando a PT não é autorizada.")
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not codigo:
        raise Recusada("Não sei quem está assinando: entre com o seu login do Fracttal.")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN).")
    with _TRAVA:
        visao.limpar()                        # decide sobre o livro do App lido agora, não a cópia de 5 min
        p = visao.pt(numero)
        if not p:
            raise Recusada(f"{numero} não está no livro do App.")
        if p["situacao"] != "aguardando":
            raise Recusada(f"{numero} já foi decidida no App ({p['situacao']}).")
        pode, porque = pode_decidir(p, email, nome, admin)
        if not pode:
            raise Recusada(porque)
        linhas = decisoes()
        if any(str(d.get("pt") or "") == p["numero"] for d in linhas):
            raise Recusada(f"{numero} já tem decisão gravada pelo Nexus.")
        agora = datetime.now(timezone.utc)
        nova = {"decidida_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "pt": p["numero"], "os": str(p["os"] or ""),
                "usina_id": p["usina_id"], "decisao": decisao, "motivo": motivo, "decidida_por_hmac": codigo,
                "login": "Fracttal (OS Creator)", "origem": "Nexus"}
        linhas = [[d.get(c) for c in CAB] for d in linhas] + [[nova[c] for c in CAB]]
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), linhas)}, base=visao._base(),
                        token=cfg["GRIDCO_SQL_TOKEN"], sessao=visao._sessao())
    return nova
