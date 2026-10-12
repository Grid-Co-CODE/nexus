"""O setor do pessoal do Fracttal (Base > Integração Fracttal; 12/10/2026, Levi: "Como faço para definir um setor????
tem que dar possibilidade"). O Fracttal não diz o setor de ninguém (grupo 1, grupo 2 e campos próprios vazios nas 150
pessoas em 12/10) e ainda não há uma base de setores: a lista nasce na tela. Quem é administrador cria, renomeia e
exclui setores e escolhe o de cada pessoa, uma a uma ou as marcadas de uma vez.

Livro `nexus_setores` no banco (registrado em `nexus/dados/catalogo.py`, fato `decisao_setor`; regras da governança em
`nexus/dados/CLAUDE.md`):
- `dim_setor`: 1 linha = 1 setor (`setor_id` 1, 2, 3...). Excluir marca `excluido = sim` e o ID nunca volta a ser usado:
  as decisões antigas continuam apontando para ele.
- `fato_decisao_setor`: 1 linha = 1 decisão de pôr 1 pessoa do Fracttal num setor, ou de tirá-la (`setor_id` vazio). Só
  acrescenta: o setor de cada pessoa é a ÚLTIMA decisão dela, e as de antes são o histórico.

A pessoa vai pelo id do Fracttal (`fracttal_id`, o id_personnel: o mesmo `tecnico_id` que o coletor do Campo grava), pela
ficha do cadastro quando liga (`pessoa_id` e `pessoa_ligada_por`, o critério do login) e pelo código do e-mail
(`pessoa_hmac`, NEXUS_PESSOA_HMAC, o mesmo do App). Nome e e-mail, nunca: a API do banco tem leitura aberta (regra 8).
Quem decidiu vai em `decidida_por_hmac` e no log da máquina.

Gravar troca o livro inteiro, sempre com as DUAS abas (gravar sem uma a apagaria), e `livros.publicar` relê e confere a
contagem de cada aba. Antes de gravar, o livro é relido do banco (nunca a cópia de 1 minuto); se a leitura falha, nada é
gravado, porque gravar sobre uma leitura vazia apagaria os setores. Uma gravação por vez neste processo (`_TRAVA`): duas
máquinas gravando no mesmo segundo ainda podem perder uma decisão (a última troca vence), risco aceito numa tela que só
administrador abre.
"""
import logging
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from ..dados import fatos as D
from ..dados import livros

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO = "nexus_setores", "Nexus · setores do pessoal"
ABA_SETOR, ABA_DECISAO = "dim_setor", "fato_decisao_setor"
CAB_SETOR = ("setor_id", "nome", "criado_em", "alterado_em", "excluido")
CAB_DECISAO = ("decidida_em", "data_id", "fracttal_id", "pessoa_id", "pessoa_ligada_por", "pessoa_hmac", "setor_id",
               "decidida_por_hmac", "origem")
NOME_MIN, NOME_MAX = 2, 60
LOTE_MAX = 300                   # o Fracttal tinha 150 pessoas em 12/10: marcar todas cabe com folga
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _setor(x: dict) -> dict | None:
    sid = D._id(x.get("setor_id"))
    if not sid:
        return None
    return {"setor_id": sid, "nome": " ".join(D._txt(x.get("nome")).split()), "criado_em": D._txt(x.get("criado_em")),
            "alterado_em": D._txt(x.get("alterado_em")), "excluido": D._txt(x.get("excluido")).lower() == "sim"}


def _decisao(x: dict) -> dict | None:
    fid = D._id(x.get("fracttal_id"))
    if not fid:
        return None
    return {"decidida_em": D._txt(x.get("decidida_em")), "data_id": D._id(x.get("data_id")), "fracttal_id": fid,
            "pessoa_id": D._id(x.get("pessoa_id")), "pessoa_ligada_por": D._txt(x.get("pessoa_ligada_por")),
            "pessoa_hmac": D._txt(x.get("pessoa_hmac")), "setor_id": D._id(x.get("setor_id")),
            "decidida_por_hmac": D._txt(x.get("decidida_por_hmac")), "origem": D._txt(x.get("origem"))}


def _ler_banco(base: str, sessao) -> dict:
    """As duas abas lidas agora (uma listagem e duas leituras). Livro que ainda não existe = vazio. Erro sobe."""
    a = livros.abas(base, sessao, LIVRO)
    setores = [s for s in (_setor(x) for x in livros._linhas(base, sessao, a[ABA_SETOR])) if s] if ABA_SETOR in a else []
    decisoes = ([d for d in (_decisao(x) for x in livros._linhas(base, sessao, a[ABA_DECISAO])) if d]
                if ABA_DECISAO in a else [])
    return {"setores": setores, "decisoes": decisoes}


def ler(base: str, sessao, forcar: bool = False) -> dict:
    """{"setores", "decisoes", "lido_em", "erro"}: o livro, guardado por 1 minuto. Leitura que falha devolve a última
    boa com `velha` e o erro; sem nenhuma, vazio com o erro (a tela não deixa gravar sem saber o que há no banco)."""
    g = _CACHE.get("livro")
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        d = _ler_banco(base, sessao)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e não deixa gravar
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if g:
            return dict(g, erro=erro, velha=True)
        return {"setores": [], "decisoes": [], "lido_em": None, "erro": erro}
    g = dict(d, lido_em=time.time(), erro="")
    _CACHE["livro"] = g
    return g


def vigentes(decisoes: list[dict]) -> dict:
    """{fracttal_id: setor_id ou None}: a última decisão de cada pessoa (pela hora; empate fica na ordem do livro)."""
    out = {}
    for d in sorted(decisoes, key=lambda x: x["decidida_em"]):
        out[d["fracttal_id"]] = d["setor_id"]
    return out


def ativos(setores: list[dict]) -> list[dict]:
    """Os setores que valem (sem os excluídos), pelo nome."""
    return sorted((s for s in setores if not s["excluido"]), key=lambda s: _norm(s["nome"]))


def _nome_valido(nome) -> str:
    n = " ".join(str(nome or "").split())
    if len(n) < NOME_MIN:
        raise Recusada("Escreva o nome do setor.")
    if len(n) > NOME_MAX:
        raise Recusada(f"O nome do setor tem no máximo {NOME_MAX} letras.")
    if "@" in n:
        raise Recusada("O nome do setor não pode ter e-mail: o banco tem leitura aberta.")
    return n


def _repetido(setores, nome, fora=None) -> dict | None:
    return next((s for s in setores if not s["excluido"] and s["setor_id"] != fora and _norm(s["nome"]) == _norm(nome)),
                None)


def _do_livro(setores, setor_id) -> dict:
    s = next((x for x in setores if x["setor_id"] == setor_id and not x["excluido"]), None)
    if not s:
        raise Recusada("Esse setor não existe mais (outra pessoa pode ter mudado a lista): atualize a página.")
    return s


def _publicar(setores, decisoes, base, token, sessao) -> dict:
    vazio = (lambda v: None if v in ("", None) else v)
    linhas_s = [[s["setor_id"], s["nome"], s["criado_em"], vazio(s["alterado_em"]), "sim" if s["excluido"] else None]
                for s in sorted(setores, key=lambda s: s["setor_id"])]
    linhas_d = [[vazio(d.get(c)) for c in CAB_DECISAO] for d in decisoes]
    return livros.publicar(LIVRO, NOME_LIVRO, {ABA_SETOR: (list(CAB_SETOR), linhas_s),
                                               ABA_DECISAO: (list(CAB_DECISAO), linhas_d)},
                           base=base, token=token, sessao=sessao)


def _gravar(mudar, cfg, base, sessao):
    """Relê o livro do banco, aplica `mudar(setores, decisoes) -> (resultado, mudou)` e, se mudou, grava as duas abas e
    confere. Sem mudança, não grava (abrir e salvar sem mexer não muda nada)."""
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    with _TRAVA:
        try:
            atual = _ler_banco(base, sessao)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler os setores do banco ({type(ex).__name__}): nada foi gravado, para não "
                           "apagar o que já está lá.") from ex
        setores, decisoes = atual["setores"], atual["decisoes"]
        resultado, mudou = mudar(setores, decisoes)
        if mudou:
            _publicar(setores, decisoes, base, token, sessao)
        _CACHE["livro"] = {"setores": setores, "decisoes": decisoes, "lido_em": time.time(), "erro": ""}
        return resultado


def criar(nome, cfg, base, sessao, quem: str = "") -> dict:
    nome = _nome_valido(nome)

    def mudar(setores, decisoes):
        outro = _repetido(setores, nome)
        if outro:
            raise Recusada(f"Já existe o setor {outro['nome']}.")
        novo = {"setor_id": max((s["setor_id"] for s in setores), default=0) + 1, "nome": nome,
                "criado_em": _iso(_agora()), "alterado_em": "", "excluido": False}
        setores.append(novo)
        return novo, True
    novo = _gravar(mudar, cfg, base, sessao)
    log.info("Setores: criou %s (setor %s), por %s.", novo["nome"], novo["setor_id"], quem or "?")
    return novo


def renomear(setor_id, nome, cfg, base, sessao, quem: str = "") -> dict:
    nome = _nome_valido(nome)

    def mudar(setores, decisoes):
        s = _do_livro(setores, setor_id)
        if s["nome"] == nome:
            return s, False
        outro = _repetido(setores, nome, fora=setor_id)
        if outro:
            raise Recusada(f"Já existe o setor {outro['nome']}.")
        s["nome"], s["alterado_em"] = nome, _iso(_agora())
        return s, True
    s = _gravar(mudar, cfg, base, sessao)
    log.info("Setores: setor %s agora se chama %s, por %s.", setor_id, nome, quem or "?")
    return s


def excluir(setor_id, cfg, base, sessao, quem: str = "") -> dict:
    def mudar(setores, decisoes):
        s = _do_livro(setores, setor_id)
        n = sum(1 for v in vigentes(decisoes).values() if v == setor_id)
        if n:
            raise Recusada(f"{n} {'pessoa está' if n == 1 else 'pessoas estão'} no setor {s['nome']}: mude o setor "
                           f"{'dela' if n == 1 else 'delas'} antes de excluir.")
        s["excluido"], s["alterado_em"] = True, _iso(_agora())
        return s, True
    s = _gravar(mudar, cfg, base, sessao)
    log.info("Setores: excluiu %s (setor %s), por %s.", s["nome"], setor_id, quem or "?")
    return s


def definir(pessoas: list[dict], setor_id, cfg, base, sessao, quem_email: str = "") -> dict:
    """Põe as `pessoas` (do Fracttal, com a ficha ligada: `fracttal_pessoal.ligar`) no setor `setor_id` (None = tira do
    setor). Quem já está nele não ganha linha nova. {"gravadas", "iguais", "setor"}."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    if not pessoas:
        raise Recusada("Marque ao menos uma pessoa.")
    if len(pessoas) > LOTE_MAX:
        raise Recusada(f"No máximo {LOTE_MAX} pessoas de uma vez.")
    chave = cfg.get("NEXUS_PESSOA_HMAC")
    quem = codigo_da_pessoa(chave, quem_email) or ""

    def mudar(setores, decisoes):
        nome = _do_livro(setores, setor_id)["nome"] if setor_id else ""
        vig, agora = vigentes(decisoes), _agora()
        novas = []
        for p in pessoas:
            if vig.get(p["id"]) == setor_id:
                continue
            f = p.get("ficha")
            novas.append({"decidida_em": _iso(agora), "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")),
                          "fracttal_id": p["id"], "pessoa_id": f["pessoa_id"] if f else None,
                          "pessoa_ligada_por": (p.get("por") or "") if f else "",
                          "pessoa_hmac": codigo_da_pessoa(chave, p.get("email")) or "", "setor_id": setor_id,
                          "decidida_por_hmac": quem, "origem": "tela"})
        decisoes.extend(novas)
        return {"gravadas": len(novas), "iguais": len(pessoas) - len(novas), "setor": nome}, bool(novas)
    r = _gravar(mudar, cfg, base, sessao)
    log.info("Setores: %s pessoa(s) %s, por %s.", r["gravadas"], f"no setor {r['setor']}" if setor_id else "sem setor",
             quem_email or "senha de administrador")
    return r
