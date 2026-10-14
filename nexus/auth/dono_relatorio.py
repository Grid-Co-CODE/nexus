"""O setor dono de cada relatório da Central de emissão, escolhido pelo administrador (14/10/2026, Levi: "adicione a
opção de eu escolher de qual setor é o relatório! Apenas administradores podem editar!").

- O padrão é o `Tela.do_setor` do código, pelo NOME do setor (os da plataforma são da Performance; os do PCM, do PCM).
  A escolha feita na Central vale por cima dele, pelo `setor_id`: o setor renomeado continua dono.
- O setor dono vê o relatório sem marcar nada em Base → Acessos (`setor_telas.das_do_setor`), e o cartão traz o nome
  dele. "Nenhum setor" = só o administrador e quem for marcado em Base → Acessos.
- Só administrador vê a seção e grava (o portão do POST: `torres/relatorios.central`).

O dado: livro `nexus_relatorio_setor · fato_decisao_dono_relatorio`, no catálogo (`nexus/dados/catalogo.py`, fato
`decisao_dono_relatorio`). Livro PRÓPRIO, e não uma aba a mais no `nexus_setor_telas`: gravar troca o livro inteiro
(`livros.publicar`), e no mesmo livro a gravação de um apagaria a aba do outro. Grão: 1 linha = 1 decisão do setor dono
de 1 relatório (`torre/tela`); setor_id vazio = nenhum setor. Só acrescenta: vale a última decisão de cada relatório.
Quem decidiu vai em `decidida_por_hmac` (nada de nome nem e-mail: a API tem leitura aberta).
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from ..dados import fatos as D
from ..dados import livros

log = logging.getLogger(__name__)

LIVRO, NOME_LIVRO = "nexus_relatorio_setor", "Nexus · setor de cada relatório"
ABA = "fato_decisao_dono_relatorio"
CAB = ("decidida_em", "data_id", "tela", "setor_id", "decidida_por_hmac", "origem")
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def _decisao(x: dict) -> dict | None:
    tela = D._txt(x.get("tela"))
    if not tela:
        return None
    return {"decidida_em": D._txt(x.get("decidida_em")), "data_id": D._id(x.get("data_id")), "tela": tela,
            "setor_id": D._id(x.get("setor_id")), "decidida_por_hmac": D._txt(x.get("decidida_por_hmac")),
            "origem": D._txt(x.get("origem"))}


def _ler_banco(base: str, sessao) -> list[dict]:
    a = livros.abas(base, sessao, LIVRO)
    return [d for d in (_decisao(x) for x in livros._linhas(base, sessao, a[ABA])) if d] if ABA in a else []


def ler(base: str, sessao, forcar: bool = False) -> dict:
    """{"decisoes", "lido_em", "erro"}: o livro, guardado por 1 minuto; a leitura que falha devolve a última boa com o
    erro (sem nenhuma, vazio com o erro: a tela não deixa gravar sem saber o que há no banco)."""
    c = _CACHE.get("livro")
    if c and not forcar and time.time() - c["lido_em"] < TTL_S:
        return c
    try:
        decisoes = _ler_banco(base, sessao)
    except Exception as ex:      # noqa: BLE001 — banco fora, rede
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if c:
            return dict(c, erro=erro, velha=True)
        return {"decisoes": [], "lido_em": None, "erro": erro}
    c = {"decisoes": decisoes, "lido_em": time.time(), "erro": ""}
    _CACHE["livro"] = c
    return c


def limpar() -> None:
    _CACHE.clear()


def vigentes(decisoes: list[dict]) -> dict[str, int | None]:
    """{tela: setor_id ou None} pela última decisão de cada relatório (pela hora; empate fica na ordem do livro)."""
    out: dict[str, int | None] = {}
    for d in sorted(decisoes or [], key=lambda x: x["decidida_em"]):
        out[d["tela"]] = d["setor_id"]
    return out


def gravar(escolhas: dict[str, int | None], atuais: dict[str, int | None], cfg, base, sessao,
           quem_email: str = "") -> dict:
    """Grava o dono dos relatórios que MUDARAM (`escolhas` contra o dono de agora, `atuais`, que já conta o padrão do
    código): abrir e salvar sem mexer não grava nada. {"gravadas": n}."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    mudou = {t: s for t, s in escolhas.items() if atuais.get(t) != s}
    if not mudou:
        return {"gravadas": 0}
    quem = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), quem_email) or ""
    with _TRAVA:
        try:
            decisoes = _ler_banco(base, sessao)
        except Exception as ex:  # noqa: BLE001
            raise Recusada(f"Não consegui ler os donos dos relatórios no banco ({type(ex).__name__}): nada foi gravado, "
                           "para não apagar o que já está lá.") from ex
        agora = datetime.now(timezone.utc)
        decisoes = decisoes + [{"decidida_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "tela": t, "setor_id": s,
                                "decidida_por_hmac": quem, "origem": "central"} for t, s in sorted(mudou.items())]
        vazio = (lambda v: None if v in ("", None) else v)    # noqa: E731
        linhas = [[d["decidida_em"], d["data_id"], d["tela"], vazio(d["setor_id"]), vazio(d["decidida_por_hmac"]),
                   vazio(d["origem"])] for d in decisoes]
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), linhas)}, base=base, token=token, sessao=sessao)
        _CACHE["livro"] = {"decisoes": decisoes, "lido_em": time.time(), "erro": ""}
    log.info("Setor dos relatórios: %s mudança(s) (%s), por %s.", len(mudou), ", ".join(sorted(mudou)),
             quem_email or "senha de administrador")
    return {"gravadas": len(mudou)}
