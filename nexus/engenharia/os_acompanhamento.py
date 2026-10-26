"""A OS acompanhada pela Engenharia, na página da OS do Quadro da equipe (Levi, 24/10/2026: "Ao clicar quero uma visão
parecida com o que aparece quando clica na OS da parte de CHAMADOS > GARANTIA", com o status da engenharia no lugar do
ticket do fornecedor, a prioridade "média, alta e urgente" e todo comentário na nota da OS). Desenho em
docs/superpowers/specs/2026-10-24-engenharia-os-do-quadro-design.md.

O Nexus é a FONTE do status e da prioridade: livro `nexus_engenharia_os`, registrado no catálogo antes da 1ª gravação
(regra 10), com três abas gravadas sempre juntas:
- `fato_acompanhamento_os`: 1 linha = 1 EVENTO numa OS (`status`, `prioridade` ou `comentario`). Só acrescenta: o estado
  de agora sai dos eventos, na ordem da gravação (o mesmo cuidado do acompanhamento dos ativos).
- `dim_status_os` e `dim_prioridade_os`: as listas fixas do pedido, para o banco dizer o que cada número quer dizer.

A prioridade é a da engenharia, não a criticidade do Fracttal: o caminho que o OS Creator usa no Fracttal não muda a
criticidade depois de a OS criada. O comentário vai também para a nota da OS no Fracttal, pela ponte do OS Creator (na
sessão do Fracttal da pessoa); aqui fica o registro, com `nota_fracttal` = "sim" ou o motivo de não ter ido.

A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): quem fez (nome e e-mail) e o texto vão só CIFRADOS
(o Cofre, a chave do cadastro); a pessoa liga pelo código do e-mail (`pessoa_hmac`). A OS vai pelo id do Fracttal e
pelo nº; o ativo pelo código canônico e pelo `equipamento_id`; a usina pelo `usina_id` da ligação com o cadastro.
"""
import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros
from ..dados.equipamento import canon, equipamento_id
from . import acompanhamento as AC

LIVRO, NOME_LIVRO = "nexus_engenharia_os", "Nexus · a OS acompanhada pela Engenharia"
ABA, ABA_STATUS, ABA_PRIORIDADE = "fato_acompanhamento_os", "dim_status_os", "dim_prioridade_os"
# origem e origem_id (26/10/2026): de onde veio o evento ("nexus", ou "app_etm" no histórico do app de ETM trazido
# uma vez, com o id do comentário de lá: trazer de novo não repete)
CAB = ("id", "registrado_em", "data_id", "evento", "os_id", "os_folio", "codigo_ativo", "equipamento_id", "usina_id",
       "usina_ligada_por", "pessoa_hmac", "status_id", "prioridade_id", "nota_fracttal", "dados_cifrados", "origem",
       "origem_id")
CAB_DIM = ("id", "nome")
# os oito do anexo do pedido, na ordem dele (o número é o id: nunca reaproveitar nem reordenar)
STATUS = ((1, "Análise de Solução"), (2, "Atividade em Andamento"), (3, "Diagnóstico em Andamento"),
          (4, "Agendamento de OS"), (5, "Tratativa com Equipe de Campo"), (6, "Validação Final"), (7, "Stand-By"),
          (8, "Diagnóstico Concluído"))
PRIORIDADES = ((1, "Média"), (2, "Alta"), (3, "Urgente"))
EVENTOS = ("status", "prioridade", "comentario")
ABERTAS = ("fazer", "execucao", "verificacao")   # as colunas do quadro em que a OS ainda pede atenção
DIAS_PARADA = 7                                   # "OSs que não tiveram atualizações nos últimos 7 dias" (Levi)
TEXTO_MAX = AC.TEXTO_MAX
TTL_S = 60
# o quadro e a página leem o livro no caminho do clique: com a API do banco pendurada, o pedido espera no máximo isto, e
# a falha fica guardada pelo TTL (revisão final de 24/10/2026: o quadro, que nunca dependeu do banco, esperava os 60 s)
PRAZO_S = 8
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}
Recusada = AC.Recusada
_txt, _int, _quando = AC._txt, AC._int, AC._quando


def nome_status(i) -> str:
    return dict(STATUS).get(_int(i), "")


def nome_prioridade(i) -> str:
    return dict(PRIORIDADES).get(_int(i), "")


def limpar() -> None:
    _CACHE.clear()


def _ctx(eid) -> str:
    return f"banco/engenharia_os/{eid}/dados"


def _abre(cofre, l: dict) -> dict:
    if not cofre or not l.get("dados_cifrados"):
        return {}
    try:
        return json.loads(cofre.decifrar(_txt(l.get("dados_cifrados")), _ctx(_txt(l.get("id")))))
    except Exception:           # noqa: BLE001 — cifra de outra chave ou adulterada: sai sem nome nem texto
        return {}


def _ler_banco(base: str, sessao) -> dict:
    a = livros.abas(base, sessao, LIVRO)
    return {"eventos": livros._linhas(base, sessao, a[ABA]) if ABA in a else []}


class _Curta:
    """A sessão do banco com prazo curto (a mesma ideia das telas por setor, `setor_telas._Curta`)."""

    def __init__(self, sessao):
        self._s = sessao

    def get(self, *a, **k):
        k["timeout"] = min(float(k.get("timeout") or PRAZO_S), PRAZO_S)
        return self._s.get(*a, **k)


def ler(forcar: bool = False) -> dict:
    """{"eventos" (as linhas cruas), "lido_em", "erro"}, guardado por 1 minuto. Leitura que falha devolve a última boa com
    o erro; sem nenhuma, vazio com o erro (a tela diz que não leu, e não "sem status"). A falha também fica guardada pelo
    minuto, e o livro que existe e veio sem a aba dos eventos é leitura incompleta, não "nada" (revisão final: um
    minuto de pulso e de números chutados no quadro)."""
    g = _CACHE.get("livro")
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    f = _CACHE.get("falha")
    if f and not forcar and time.time() - f["em"] < TTL_S:
        return dict(g, erro=f["erro"], velha=True) if g else {"eventos": [], "lido_em": None, "erro": f["erro"]}
    try:
        base, sessao = AC._banco()
        curta = _Curta(sessao)
        d = _ler_banco(base, curta)
        token = current_app.config.get("GRIDCO_SQL_TOKEN")
        if not d["eventos"] and token and livros.existe(LIVRO, base=base, token=token, sessao=curta):
            raise livros.GravacaoRecusada(f"{LIVRO}: o livro existe e a aba dos eventos não veio na leitura")
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e não deixa gravar
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        _CACHE["falha"] = {"em": time.time(), "erro": erro}
        if g:
            return dict(g, erro=erro, velha=True)
        return {"eventos": [], "lido_em": None, "erro": erro}
    _CACHE.pop("falha", None)
    g = dict(d, lido_em=time.time(), erro="")
    _CACHE["livro"] = g
    return g


def estado(eventos: list[dict]) -> dict[str, dict]:
    """{os_id: {"status_id", "prioridade_id", "ultimo" (o evento mais novo), "eventos" (o mais novo primeiro)}}."""
    cofre = AC._cofre_ou_nada()
    ordem = {id(e): i for i, e in enumerate(eventos)}
    linhas = sorted(eventos, key=lambda e: (_quando(e.get("registrado_em")) or datetime.min.replace(tzinfo=_BRT),
                                            ordem[id(e)]))
    out: dict[str, dict] = {}
    for l in linhas:
        oid, ev = _txt(l.get("os_id")), _txt(l.get("evento"))
        if not oid or ev not in EVENTOS:
            continue
        # a API pode devolver o id como "39550452.0": a chave é o número
        oid = str(_int(oid) or oid)
        e = out.setdefault(oid, {"status_id": None, "prioridade_id": None, "ultimo": None, "eventos": []})
        q = _quando(l.get("registrado_em"))
        d = _abre(cofre, l)
        if ev == "status" and _int(l.get("status_id")):
            e["status_id"] = _int(l.get("status_id"))
        if ev == "prioridade" and _int(l.get("prioridade_id")):
            e["prioridade_id"] = _int(l.get("prioridade_id"))
        if q and (e["ultimo"] is None or q > e["ultimo"]):
            e["ultimo"] = q
        e["eventos"].insert(0, {"evento": ev, "quando": q, "quando_txt": q.strftime("%d/%m/%Y %H:%M") if q else "",
                                "nome": ((d.get("quem") or {}).get("nome")) or "", "texto": _txt(d.get("texto")),
                                "status_id": _int(l.get("status_id")), "prioridade_id": _int(l.get("prioridade_id")),
                                "nota": _txt(l.get("nota_fracttal"))})
    return out


def _evento(cofre, evento: str, quem: dict, os_: dict, *, status_id=None, prioridade_id=None, texto: str = "",
            nota: str | None = None, quando: datetime | None = None, origem: str = "nexus", origem_id=None) -> dict:
    eid = uuid.uuid4().hex[:12]
    agora = (quando or datetime.now(timezone.utc)).astimezone(timezone.utc)
    dados = {"quem": {"nome": quem["nome"], "email": quem["email"]}}
    if texto:
        dados["texto"] = texto
    cod = canon(os_.get("codigo"))
    return {"id": eid, "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "evento": evento,
            "os_id": _int(os_.get("wid")), "os_folio": _txt(os_.get("folio")), "codigo_ativo": cod or None,
            "equipamento_id": equipamento_id(cod) if cod else None, "usina_id": _int(os_.get("usina_id")),
            "usina_ligada_por": _txt(os_.get("usina_ligada_por")) or None, "pessoa_hmac": quem["hmac"],
            "status_id": status_id, "prioridade_id": prioridade_id, "nota_fracttal": nota,
            "dados_cifrados": cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(eid)), "origem": origem,
            "origem_id": origem_id}


def _reler() -> dict:
    """O livro relido do banco agora, sem a cópia. Com o livro no banco, a aba dos eventos que não veio é leitura
    incompleta (toda gravação leva ao menos um evento): gravar sobre ela apagaria o que há (a mesma regra do cadastro
    dos diagnósticos, auditoria da trava de 18/10/2026)."""
    base, sessao = AC._banco()
    lido = _ler_banco(base, sessao)
    if not lido["eventos"] and livros.existe(LIVRO, base=base, token=current_app.config["GRIDCO_SQL_TOKEN"],
                                             sessao=sessao):
        raise livros.GravacaoRecusada(f"{LIVRO}: os eventos não vieram na leitura do banco; não gravo por cima (tente "
                                      "de novo em instantes)")
    return lido


def _publicar(eventos: list[dict]) -> None:
    base, sessao = AC._banco()
    livros.publicar(LIVRO, NOME_LIVRO, {ABA_STATUS: (list(CAB_DIM), [list(x) for x in STATUS]),
                                        ABA_PRIORIDADE: (list(CAB_DIM), [list(x) for x in PRIORIDADES]),
                                        ABA: (list(CAB), [[e.get(c) for c in CAB] for e in eventos])},
                    base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
    limpar()


def _id_da_lista(v, lista, o_que: str) -> int | None:
    if v in (None, "", 0, "0"):
        return None
    i = _int(v)
    if i not in dict(lista):
        raise Recusada(f"Escolha {o_que} da lista")
    return i


def classificar(os_: dict, status_id, prioridade_id, usuario, pode: bool) -> dict:
    """Muda o status e/ou a prioridade da engenharia numa OS (vazio = mantém). Um evento por mudança."""
    quem = AC._quem(usuario, pode, "classifica a OS")
    st = _id_da_lista(status_id, STATUS, "o status")
    pr = _id_da_lista(prioridade_id, PRIORIDADES, "a prioridade")
    if not _int(os_.get("wid")):
        raise Recusada("OS sem o id do Fracttal: recarregue a página")
    if st is None and pr is None:
        raise Recusada("Escolha o status ou a prioridade")
    cofre = AC._cofre()
    with _TRAVA:
        lido = _reler()
        atual = estado(lido["eventos"]).get(str(_int(os_["wid"]))) or {}
        novos = []
        if st is not None and st != atual.get("status_id"):
            novos.append(_evento(cofre, "status", quem, os_, status_id=st))
        if pr is not None and pr != atual.get("prioridade_id"):
            novos.append(_evento(cofre, "prioridade", quem, os_, prioridade_id=pr))
        if not novos:
            raise Recusada("Nada mudou")
        _publicar(lido["eventos"] + novos)
    # o aviso diz só o que mudou (a prioridade igual à de antes não aparece como "salva")
    return {"status": next((nome_status(e["status_id"]) for e in novos if e["evento"] == "status"), ""),
            "prioridade": next((nome_prioridade(e["prioridade_id"]) for e in novos if e["evento"] == "prioridade"), ""),
            "eventos": novos}


def texto_do_comentario(texto) -> str:
    t = _txt(texto)
    if not t:
        raise Recusada("Escreva o comentário antes de salvar")
    if len(t) > TEXTO_MAX:
        raise Recusada(f"O comentário passou de {TEXTO_MAX} caracteres")
    return t


def linha_da_nota(texto: str, nome: str, quando: datetime) -> str:
    """A linha que vai para a nota da OS no Fracttal ("vai para a nota da OS com data e hora do comentário")."""
    return f"[{quando.astimezone(_BRT):%d/%m/%Y %H:%M}] {nome} (Engenharia): {texto}"


def quem_comenta(usuario, pode: bool) -> dict:
    """Quem pode comentar, conferido ANTES de ir ao Fracttal (nada vai à nota de quem o Nexus recusaria)."""
    return AC._quem(usuario, pode, "comenta na OS")


def registrar_comentario(os_: dict, texto, usuario, pode: bool, nota: str) -> dict:
    """O comentário no livro, com `nota` = "sim" (foi para a nota da OS) ou o motivo de não ter ido."""
    quem = AC._quem(usuario, pode, "comenta na OS")
    t = texto_do_comentario(texto)
    if not _int(os_.get("wid")):
        raise Recusada("OS sem o id do Fracttal: recarregue a página")
    cofre = AC._cofre()
    with _TRAVA:
        lido = _reler()
        novo = _evento(cofre, "comentario", quem, os_, texto=t, nota=_txt(nota)[:200] or None)
        _publicar(lido["eventos"] + [novo])
    return novo


def importar_comentarios(itens: list[dict], origem: str) -> int:
    """Os comentários trazidos de outro lugar (o histórico do app de ETM), com o autor e a data de lá e a `nota` de cada
    um ("sim" ou o motivo). Só os que o livro não tem, pelo `origem_id`; uma gravação só. Devolve quantos entraram."""
    cofre = AC._cofre()
    with _TRAVA:
        lido = _reler()
        ja = {str(e.get("origem_id")) for e in lido["eventos"] if e.get("origem") == origem and e.get("origem_id")}
        novos = [_evento(cofre, "comentario", {"nome": _txt(i["autor"]), "email": "", "hmac": None}, i["os_"],
                         texto=_txt(i["texto"])[:4000], nota=_txt(i.get("nota"))[:200] or None, quando=i.get("quando"),
                         origem=origem, origem_id=str(i["origem_id"]))
                 for i in itens if str(i["origem_id"]) not in ja]
        if novos:
            _publicar(lido["eventos"] + novos)
    return len(novos)


def ultima_atualizacao(datas) -> datetime | None:
    """O mais novo entre o último evento da engenharia, a criação da OS e o início e o fim das tarefas no Fracttal."""
    vistas = [d for d in datas if d]
    return max(vistas) if vistas else None


def parada(coluna: str, ultima: datetime | None, agora: datetime) -> bool:
    """A OS aberta sem atualização há mais de 7 dias (o pulso laranja do quadro). Sem data nenhuma, não se chuta."""
    return coluna in ABERTAS and ultima is not None and agora - ultima > timedelta(days=DIAS_PARADA)
