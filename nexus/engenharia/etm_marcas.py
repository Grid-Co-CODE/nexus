"""O que a Engenharia marca em cada OS de ETM, na tela ETMs (Levi, 26/10/2026: "Quero que inclua essa visão de ETMs no
Nexus, engenharia, aba própria"): as cinco marcações do app de ETM da Engenharia, que lá eram labels de Issues num
repositório do GitHub. Desenho em docs/superpowers/specs/2026-10-26-engenharia-etm-design.md.

O Nexus é a FONTE: livro `nexus_engenharia_etm`, registrado no catálogo antes da 1ª gravação (regra 10), com quatro abas
gravadas sempre juntas:
- `fato_marcacao_etm`: 1 linha = 1 marcação numa OS (`diagnostico`, `status_pos`, `etiqueta`, `acompanhamento` ou
  `finalizado`). Só acrescenta: o estado de agora sai dos eventos, na ordem da gravação. `valor_id` é o item da lista
  (0 limpa o diagnóstico e o status pós-OS); `ligado` liga ou desliga a etiqueta, o acompanhamento e o finalizado.
  `origem` diz de onde veio ("nexus", ou "app_etm" no histórico trazido uma vez) e `origem_id` a chave de lá.
- `dim_diagnostico_etm`, `dim_status_pos_etm` e `dim_etiqueta_etm`: as listas fixas do app, para o banco dizer o que
  cada número quer dizer (o id nunca se reaproveita nem se reordena).

Os comentários das OS de ETM são os da Engenharia (`os_acompanhamento`, livro `nexus_engenharia_os`), que vão também para
a nota da OS no Fracttal. Quem fez vai só CIFRADO (o Cofre, a chave do cadastro) e pelo código do e-mail (`pessoa_hmac`);
a OS pelo id do Fracttal e pelo nº, o ativo pelo código canônico e pelo `equipamento_id`, a usina pelo `usina_id`.
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

LIVRO, NOME_LIVRO = "nexus_engenharia_etm", "Nexus · o que a Engenharia marca nas OS de ETM"
ABA = "fato_marcacao_etm"
ABA_DIAGNOSTICO, ABA_STATUS_POS, ABA_ETIQUETA = "dim_diagnostico_etm", "dim_status_pos_etm", "dim_etiqueta_etm"
CAB = ("id", "registrado_em", "data_id", "evento", "os_id", "os_folio", "codigo_ativo", "equipamento_id", "usina_id",
       "usina_ligada_por", "pessoa_hmac", "valor_id", "ligado", "origem", "origem_id", "dados_cifrados")
CAB_DIM = ("id", "nome")
# as listas do app de ETM (comments.py de lá), na ordem dele
DIAGNOSTICOS = ((1, "Falha de Equipamento"), (2, "Falha de Comunicação"), (3, "Sujidade"), (4, "Outro"))
STATUS_POS = ((1, "Chamado de Garantia"), (2, "Alinhamento com o Cliente"), (3, "Regularizado"))
ETIQUETAS = ((1, "OS em campo"), (2, "Stand By"), (3, "Validação Final"))
EVENTOS = ("diagnostico", "status_pos", "etiqueta", "acompanhamento", "finalizado")
_LISTA = {"diagnostico": (DIAGNOSTICOS, "o diagnóstico"), "status_pos": (STATUS_POS, "o status pós-OS"),
          "etiqueta": (ETIQUETAS, "a etiqueta")}
TTL_S = 60
PRAZO_S = 8                  # a tela lê o livro no caminho do clique: com a API pendurada, no máximo isto
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}
Recusada = AC.Recusada
_txt, _int, _quando = AC._txt, AC._int, AC._quando


def nome(lista, i) -> str:
    return dict(lista).get(_int(i), "")


def limpar() -> None:
    _CACHE.clear()


def _ctx(eid) -> str:
    return f"banco/engenharia_etm/{eid}/dados"


def _abre(cofre, l: dict) -> dict:
    if not cofre or not l.get("dados_cifrados"):
        return {}
    try:
        return json.loads(cofre.decifrar(_txt(l.get("dados_cifrados")), _ctx(_txt(l.get("id")))))
    except Exception:           # noqa: BLE001 — cifra de outra chave ou adulterada: sai sem nome
        return {}


def _ler_banco(base: str, sessao) -> dict:
    a = livros.abas(base, sessao, LIVRO)
    return {"eventos": livros._linhas(base, sessao, a[ABA]) if ABA in a else []}


class _Curta:
    """A sessão do banco com prazo curto (a mesma do livro da OS da Engenharia)."""

    def __init__(self, sessao):
        self._s = sessao

    def get(self, *a, **k):
        k["timeout"] = min(float(k.get("timeout") or PRAZO_S), PRAZO_S)
        return self._s.get(*a, **k)


def ler(forcar: bool = False) -> dict:
    """{"eventos", "lido_em", "erro"}, guardado por 1 minuto. A leitura que falha devolve a última boa com o erro (e a
    falha fica guardada pelo minuto); o livro que existe e veio sem a aba dos eventos é leitura incompleta, não "nada"."""
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
            raise livros.GravacaoRecusada(f"{LIVRO}: o livro existe e a aba das marcações não veio na leitura")
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


def _ligado(v) -> bool:
    return _txt(v).lower() in ("sim", "true", "1")


def estado(eventos: list[dict]) -> dict[str, dict]:
    """{os_id: {"diagnostico_id", "status_pos_id", "etiquetas" (set), "acompanhamento", "finalizado", "ultima" (a
    marcação mais nova), "finalizado_em", "eventos" (o mais novo primeiro)}}."""
    cofre = AC._cofre_ou_nada()
    ordem = {id(e): i for i, e in enumerate(eventos)}
    linhas = sorted(eventos, key=lambda e: (_quando(e.get("registrado_em")) or datetime.min.replace(tzinfo=_BRT),
                                            ordem[id(e)]))
    out: dict[str, dict] = {}
    for l in linhas:
        oid, ev = _txt(l.get("os_id")), _txt(l.get("evento"))
        if not oid or ev not in EVENTOS:
            continue
        oid = str(_int(oid) or oid)          # a API pode devolver o id como "50001.0": a chave é o número
        e = out.setdefault(oid, {"diagnostico_id": None, "status_pos_id": None, "etiquetas": set(),
                                 "acompanhamento": False, "finalizado": False, "ultima": None, "finalizado_em": None,
                                 "eventos": []})
        q, v, lig = _quando(l.get("registrado_em")), _int(l.get("valor_id")), _ligado(l.get("ligado"))
        if ev == "diagnostico":
            e["diagnostico_id"] = v or None
        elif ev == "status_pos":
            e["status_pos_id"] = v or None
        elif ev == "etiqueta" and v:
            (e["etiquetas"].add if lig else e["etiquetas"].discard)(v)
        elif ev == "acompanhamento":
            e["acompanhamento"] = lig
        elif ev == "finalizado":
            e["finalizado"], e["finalizado_em"] = lig, (q if lig else None)
        if q and (e["ultima"] is None or q > e["ultima"]):
            e["ultima"] = q
        d = _abre(cofre, l)
        e["eventos"].insert(0, {"evento": ev, "quando": q, "quando_txt": q.astimezone(_BRT).strftime("%d/%m/%Y %H:%M")
                                if q else "", "nome": ((d.get("quem") or {}).get("nome")) or "", "valor_id": v,
                                "ligado": lig, "origem": _txt(l.get("origem")) or "nexus"})
    return out


def _evento(cofre, evento: str, quem: dict, os_: dict, *, valor_id=None, ligado=None, origem="nexus",
            origem_id=None, quando: datetime | None = None) -> dict:
    eid = uuid.uuid4().hex[:12]
    agora = quando or datetime.now(timezone.utc)
    cod = canon(os_.get("codigo"))
    return {"id": eid, "registrado_em": agora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "evento": evento,
            "os_id": _int(os_.get("wid")), "os_folio": _txt(os_.get("folio")), "codigo_ativo": cod or None,
            "equipamento_id": equipamento_id(cod) if cod else None, "usina_id": _int(os_.get("usina_id")),
            "usina_ligada_por": _txt(os_.get("usina_ligada_por")) or None, "pessoa_hmac": quem.get("hmac"),
            "valor_id": valor_id, "ligado": None if ligado is None else ("sim" if ligado else "não"),
            "origem": origem, "origem_id": origem_id,
            "dados_cifrados": cofre.cifrar(json.dumps({"quem": {"nome": quem.get("nome") or "",
                                                                "email": quem.get("email") or ""}},
                                                      ensure_ascii=False), _ctx(eid))}


def _reler() -> dict:
    """O livro relido do banco agora, sem a cópia. Com o livro no banco, a aba que não veio é leitura incompleta (toda
    gravação leva ao menos uma marcação): gravar sobre ela apagaria o que há."""
    base, sessao = AC._banco()
    lido = _ler_banco(base, sessao)
    if not lido["eventos"] and livros.existe(LIVRO, base=base, token=current_app.config["GRIDCO_SQL_TOKEN"],
                                             sessao=sessao):
        raise livros.GravacaoRecusada(f"{LIVRO}: as marcações não vieram na leitura do banco; não gravo por cima (tente "
                                      "de novo em instantes)")
    return lido


def _publicar(eventos: list[dict]) -> None:
    base, sessao = AC._banco()
    livros.publicar(LIVRO, NOME_LIVRO, {ABA_DIAGNOSTICO: (list(CAB_DIM), [list(x) for x in DIAGNOSTICOS]),
                                        ABA_STATUS_POS: (list(CAB_DIM), [list(x) for x in STATUS_POS]),
                                        ABA_ETIQUETA: (list(CAB_DIM), [list(x) for x in ETIQUETAS]),
                                        ABA: (list(CAB), [[e.get(c) for c in CAB] for e in eventos])},
                    base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
    limpar()


def _valor(evento: str, valor):
    """O que a tela mandou, conferido: (valor_id, ligado, a frase do aviso)."""
    if evento in ("diagnostico", "status_pos"):
        lista, o_que = _LISTA[evento]
        i = _int(valor) if valor not in (None, "") else None
        if i is None or (i and i not in dict(lista)):
            raise Recusada(f"Escolha {o_que} da lista")
        return i, None, (f"{o_que[2:]}: {nome(lista, i)}" if i else f"{o_que[2:]} limpo")
    if evento == "etiqueta":
        i, lig = valor if isinstance(valor, (tuple, list)) and len(valor) == 2 else (None, None)
        if _int(i) not in dict(ETIQUETAS):
            raise Recusada("Escolha a etiqueta da lista")
        return _int(i), bool(lig), f"etiqueta {nome(ETIQUETAS, i)} {'ligada' if lig else 'desligada'}"
    if evento in ("acompanhamento", "finalizado"):
        rot = "em acompanhamento" if evento == "acompanhamento" else "finalizado pela Engenharia"
        return None, bool(valor), (rot if valor else f"não mais {rot}")
    raise Recusada("Essa marcação não existe na tela ETMs")


def _igual(atual: dict, evento: str, valor_id, ligado) -> bool:
    if evento == "diagnostico":
        return (atual.get("diagnostico_id") or 0) == (valor_id or 0)
    if evento == "status_pos":
        return (atual.get("status_pos_id") or 0) == (valor_id or 0)
    if evento == "etiqueta":
        return (valor_id in (atual.get("etiquetas") or set())) == ligado
    return bool(atual.get(evento)) == ligado


def marcar(os_: dict, evento: str, valor, usuario, pode: bool) -> dict:
    """Uma marcação numa OS de ETM. Diagnóstico e status pós-OS: o id da lista (0 limpa); etiqueta: (id, ligado);
    acompanhamento e finalizado: liga ou desliga. Devolve {"aviso", "evento"}."""
    if evento not in EVENTOS:
        raise Recusada("Essa marcação não existe na tela ETMs")
    quem = AC._quem(usuario, pode, "marca a OS de ETM")
    valor_id, ligado, aviso = _valor(evento, valor)
    if not _int(os_.get("wid")):
        raise Recusada("OS sem o id do Fracttal: recarregue a página")
    cofre = AC._cofre()
    with _TRAVA:
        lido = _reler()
        atual = estado(lido["eventos"]).get(str(_int(os_["wid"]))) or {}
        if _igual(atual, evento, valor_id, ligado):
            raise Recusada("Nada mudou")
        novo = _evento(cofre, evento, quem, os_, valor_id=valor_id, ligado=ligado)
        _publicar(lido["eventos"] + [novo])
    return {"aviso": aviso[0].upper() + aviso[1:], "evento": novo}


def importar_marcas(itens: list[dict], origem: str) -> int:
    """As marcações trazidas de outro lugar (as labels do app de ETM), com a data de lá. Só as que o livro não tem, pelo
    `origem_id`; uma gravação só. Devolve quantas entraram."""
    cofre = AC._cofre()
    with _TRAVA:
        lido = _reler()
        ja = {str(e.get("origem_id")) for e in lido["eventos"] if e.get("origem") == origem and e.get("origem_id")}
        novos = [_evento(cofre, i["evento"], {"nome": "app de ETM", "email": "", "hmac": None}, i["os_"],
                         valor_id=i.get("valor_id"), ligado=i.get("ligado"), origem=origem, origem_id=str(i["origem_id"]),
                         quando=i.get("quando"))
                 for i in itens if str(i["origem_id"]) not in ja]
        if novos:
            _publicar(lido["eventos"] + novos)
    return len(novos)
