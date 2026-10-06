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
"""
import re
import threading
from datetime import datetime, timedelta, timezone

from flask import current_app

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


def decisoes() -> list[dict]:
    """As decisões já gravadas pelo Nexus (sem cópia: quem decide precisa ver a última)."""
    return livros.ler(visao._base(), visao._sessao(), LIVRO, ABA)


def da_pt(numero) -> dict | None:
    n = str(numero or "").strip()
    return next((d for d in reversed(decisoes()) if str(d.get("pt") or "") == n), None)


def decidir(numero, decisao: str, motivo: str, email: str) -> dict:
    """Grava a decisão e confere no banco. Recusa: decisão inválida, negar sem motivo, PT que não existe, que já não
    está aguardando no livro do App ou que já tem decisão do Nexus (o primeiro que decide vale, como no App)."""
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
