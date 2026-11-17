"""As pessoas que não estão no Fracttal (Base > Acessos > Pessoas e setores; 17/11/2026, Levi: "tem que ter a opção de
inserir uma pessoa que não está no fracttal").

Para que serve: o setor de quem entra no Nexus é o de Pessoas e setores, e a lista dali era só o pessoal do Fracttal. Quem
entra pela conta Microsoft da Grid e não tem conta no Fracttal (alguém do escritório que não usa o Fracttal, quem acabou de
chegar) ficava "Sem setor, fale com o responsável", sem como pôr num setor. Agora o administrador inclui a pessoa pelo
nome e pelo e-mail da Grid, ela aparece na mesma lista (com a etiqueta "fora do Fracttal") e ganha o setor como as outras.

O dado: livro `nexus_pessoas_fora_fracttal` · `dim_pessoa_fora_fracttal` (registrado no catálogo antes da 1ª gravação,
regra 10). 1 linha = 1 pessoa, o estado de agora (o livro é trocado inteiro sob a trava, relido do banco antes e conferido
depois). Tirar marca `ativa = não` e o id não volta. Nome e e-mail só cifrados (o Cofre, a chave do cadastro; a API do
banco tem leitura aberta, regra 8); a pessoa liga pelo código do e-mail (`pessoa_hmac`, NEXUS_PESSOA_HMAC), que é como o
login acha o setor.

O id (`pessoa_fora_id`) começa em 900.000.001, uma faixa que o Fracttal não usa (o id_personnel ia de 1.352.379 a
2.072.681 em 17/11/2026): é esse id que vai no `fracttal_id` das decisões de setor (`nexus_setores · fato_decisao_setor`),
e por isso o setor, o portão por setor (`setor_telas.setor_da_pessoa`, pelo código do e-mail) e o "excluir setor" valem
para ela sem mudar nada lá. Tirar a pessoa também a deixa sem setor (uma decisão "sem setor"): fora da lista, ela não
abre tela de setor nenhum.
"""
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone

from flask import current_app

from ..dados import fatos as D
from ..dados import livros
from . import fracttal_pessoal as FP

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO = "nexus_pessoas_fora_fracttal", "Nexus · pessoas fora do Fracttal"
ABA = "dim_pessoa_fora_fracttal"
CAB = ("pessoa_fora_id", "criada_em", "alterada_em", "ativa", "pessoa_hmac", "alterada_por_hmac", "dados_cifrados")
ID_BASE = 900_000_000
ACESSO = "Fora do Fracttal"
NOME_MIN, NOME_MAX = 3, 80
TTL_S = 60
_EMAIL = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def e_de_fora(pid) -> bool:
    """O id é de uma pessoa de fora do Fracttal (a faixa reservada)?"""
    i = D._id(pid)
    return bool(i and i > ID_BASE)


def _ctx(pid) -> str:
    return f"banco/pessoas_fora/{pid}"


def _cofre(cfg):
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela o nome e o e-mail não "
                       "vão cifrados, e nada foi gravado.")
    from .cifra import Cofre
    return Cofre(chave)


def _banco():
    from ..dados.conexao import banco
    return banco()


def ler_banco() -> list[dict]:
    """As linhas do livro, como estão no banco (sem cópia). Livro que ainda não existe = vazio. Erro sobe."""
    return livros.ler(*_banco(), LIVRO, ABA)


def _linha_da_tela(l: dict, cofre) -> dict | None:
    """Uma pessoa ativa no formato das linhas do Fracttal da tela (`fracttal_pessoal.da_api`), com `fora` = True."""
    pid = D._id(l.get("pessoa_fora_id"))
    if not pid or D._txt(l.get("ativa")).lower() != "sim":
        return None
    dados = {}
    if cofre:
        try:
            dados = json.loads(cofre.decifrar(l.get("dados_cifrados") or "", _ctx(pid)))
        except Exception:        # noqa: BLE001 — cifra de outra chave ou adulterada: a linha sai sem nome
            dados = {}
    email = D._txt(dados.get("email")).lower()
    dominio = email.split("@")[-1] if "@" in email else ""
    return {"id": pid, "nome": " ".join(D._txt(dados.get("nome")).split()), "email": email, "acesso": ACESSO,
            "conta_ativa": True, "dominio": dominio,
            "origem": FP.ORIGENS[0] if dominio in FP.DOMINIOS_GRID else FP.ORIGENS[1], "fora": True,
            "criada_em": D._txt(l.get("criada_em"))}


def ler(forcar: bool = False) -> dict:
    """{"pessoas": [linhas da tela, só as ativas], "erro"}: guardado por 1 minuto; a gravação deixa a cópia em dia.
    Leitura que falha devolve a última boa com o erro; sem nenhuma, vazio com o erro."""
    g = _CACHE.get("g")
    if g and not forcar and time.time() - g["t"] < TTL_S:
        return g
    cfg = current_app.config
    try:
        brutas = ler_banco()
    except Exception as ex:      # noqa: BLE001 — banco fora (ou teste sem banco): a lista segue só com o Fracttal
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(g, erro=erro) if g else {"pessoas": [], "erro": erro, "t": 0}
    return _guardar(brutas, cfg)


def _guardar(brutas: list[dict], cfg) -> dict:
    try:
        cofre = _cofre(cfg)
    except Recusada:
        cofre = None
    pessoas = [p for p in (_linha_da_tela(l, cofre) for l in brutas) if p]
    g = {"pessoas": sorted(pessoas, key=lambda x: FP._norm(x["nome"])), "erro": "", "t": time.time()}
    _CACHE["g"] = g
    return g


def esquecer() -> None:
    _CACHE.clear()


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _publicar(linhas: list[dict], cfg) -> None:
    base, sessao = _banco()
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in linhas])},
                    base=base, token=cfg["GRIDCO_SQL_TOKEN"], sessao=sessao)


def _codigo(cfg, email) -> str:
    from .ligacao_campo import codigo_da_pessoa
    return codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email) or ""


def _conferir_chaves(cfg) -> None:
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    if not cfg.get("NEXUS_PESSOA_HMAC"):
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC): sem ela o login não acharia a "
                       "pessoa, e nada foi gravado.")


def incluir(nome, email, emails_do_fracttal, cfg, quem_email: str = "") -> dict:
    """Inclui a pessoa (o nome e o e-mail da Grid). Recusa o e-mail que já está no Fracttal (a pessoa já está na lista) e
    o de quem já foi incluída. Devolve a linha da tela."""
    nome = " ".join(str(nome or "").split())
    email = str(email or "").strip().lower()
    if len(nome) < NOME_MIN:
        raise Recusada("Escreva o nome da pessoa.")
    if len(nome) > NOME_MAX:
        raise Recusada(f"O nome tem no máximo {NOME_MAX} letras.")
    if not _EMAIL.match(email):
        raise Recusada("Escreva o e-mail da pessoa (nome@gridco.com.br).")
    if email.split("@")[-1] not in FP.DOMINIOS_GRID:
        raise Recusada("Só e-mail da Grid Co. (gridco.com.br): é com a conta Microsoft da Grid que a pessoa entra no "
                       "Nexus, e quem é de fora não teria como entrar.")
    if email in {str(e or "").strip().lower() for e in emails_do_fracttal}:
        raise Recusada("Esse e-mail já está no Fracttal: a pessoa já está na lista. Procure pelo nome e escolha o setor "
                       "dela ali.")
    _conferir_chaves(cfg)
    cofre = _cofre(cfg)
    codigo = _codigo(cfg, email)
    with _TRAVA:
        linhas = ler_banco()
        for l in linhas:
            if D._txt(l.get("ativa")).lower() == "sim" and D._txt(l.get("pessoa_hmac")) == codigo:
                raise Recusada("Essa pessoa já foi incluída: ela está na lista, com a etiqueta \"fora do Fracttal\".")
        pid = max([ID_BASE] + [D._id(l.get("pessoa_fora_id")) or 0 for l in linhas]) + 1
        agora = _agora()
        nova = {"pessoa_fora_id": pid, "criada_em": agora, "alterada_em": agora, "ativa": "sim", "pessoa_hmac": codigo,
                "alterada_por_hmac": _codigo(cfg, quem_email) or "admin",
                "dados_cifrados": cofre.cifrar(json.dumps({"nome": nome, "email": email}, ensure_ascii=False), _ctx(pid))}
        _publicar(linhas + [nova], cfg)
        g = _guardar(linhas + [nova], cfg)
    log.info("Pessoas fora do Fracttal: incluiu a pessoa %s, por %s.", pid, quem_email or "senha de administrador")
    return next(p for p in g["pessoas"] if p["id"] == pid)


def tirar(pid, cfg, quem_email: str = "") -> dict:
    """Tira a pessoa da lista (`ativa = não`; o id não volta). Devolve a linha da tela que ela tinha."""
    pid = D._id(pid)
    if not e_de_fora(pid):
        raise Recusada("Só se tira da lista quem foi incluído aqui (fora do Fracttal).")
    _conferir_chaves(cfg)
    with _TRAVA:
        linhas = ler_banco()
        l = next((x for x in linhas if D._id(x.get("pessoa_fora_id")) == pid
                  and D._txt(x.get("ativa")).lower() == "sim"), None)
        if l is None:
            raise Recusada("Essa pessoa não está mais na lista (outra pessoa pode ter tirado): atualize a página.")
        try:
            cofre = _cofre(cfg)
        except Recusada:
            cofre = None
        antes = _linha_da_tela(l, cofre)
        l.update(ativa="não", alterada_em=_agora(), alterada_por_hmac=_codigo(cfg, quem_email) or "admin")
        _publicar(linhas, cfg)
        _guardar(linhas, cfg)
    log.info("Pessoas fora do Fracttal: tirou a pessoa %s, por %s.", pid, quem_email or "senha de administrador")
    return antes
