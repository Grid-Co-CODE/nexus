"""As OSs em verificação do Painel do responsável (29/10/2026).

Levi: "ao lado de PTS PENDENTES quero um 'OSs em verificação' irá contar as OSs em verificação que não tem etiqueta da
performance, chamados, engenharia e não foi criada por ninguém do time do COS. Pense em como fazer isso sem pesar todo
carregamento. Aí ao clicar aparece uma lista dessas OSs com as colunas: OS; Criação; Título; Quantidade de ativos;
técnico; cliente; usina; tempo sem conclusão; botão de concluir; ao passar o mouse botão de baixar pdf. ao clicar na OS
aparece o card da os do os creator."

- **A fila** é a da Aprovação de OS (`aprovacao`): as OS em revisão no Fracttal (status 2), que o Nexus relê EM SEGUNDO
  PLANO e guarda na memória e em disco. Nada aqui pede ao Fracttal: a conta é sobre a fila guardada, e a tela pede o
  número depois de a página abrir (`/t/campo/responsaveis/verificacao`), sem pesar o Painel.
- **1 linha da fila = 1 tarefa.** A OS junta as tarefas dela (`id_work_order`): o título (`description`), a criação e o
  técnico são da OS (iguais em todas as tarefas, medido em 29/10 nas 2.229 OS da fila); os ativos são os `id_item`
  distintos; o "tempo sem conclusão" conta da tarefa terminada há mais tempo (`final_date`), a mesma conta da Aprovação
  de OS (`_por_os`: a espera da OS é a da tarefa mais antiga), para a mesma OS não ter dois números.
- **A usina** é a do cadastro pelo nome do Fracttal (Classificação 1, `groups_1_description`), a MESMA ligação da
  Aprovação (`visao.usinas_do_fracttal`, de-para "Fracttal · Classificação 1"): o número do responsável bate com o da
  Aprovação dele, menos as que ficam de fora.
- **Ficam de fora** a OS com a etiqueta PERFORMANCE, CHAMADOS ou ENGENHARIA (o `labels` da linha; os nomes conferidos na
  fila de 29/10: 934 tarefas com ENGENHARIA, 592 com PERFORMANCE, 12 com CHAMADOS) e a criada por alguém do setor COS
  (Base > Acessos > Pessoas e setores, livro `nexus_setores`), pelo código da pessoa no Fracttal (`code_create_by`) ou
  pelo nome (`created_by`): o código casa 8 das 9 pessoas do COS, o nome 7.
"""
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from . import regras_app

_BRT = timezone(timedelta(hours=-3))
ETIQUETAS_FORA = ("PERFORMANCE", "CHAMADOS", "CHAMADO", "ENGENHARIA")
SETOR_COS = "cos"
TTL_COS_S = 600              # quem é do COS muda pouco: 10 min de cópia (o pessoal do Fracttal já fica 1 h)
_COS: dict = {"t": 0.0, "v": None}


def _norm(s) -> str:
    """Maiúsculas, sem acento e com um espaço só: o nome do Fracttal vem com espaço no fim ("Nome Sobrenome ")."""
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(t.split())


def etiqueta_fora(linha: dict) -> str:
    """A etiqueta que tira a OS da lista (PERFORMANCE, CHAMADOS, ENGENHARIA) ou ""."""
    for x in linha.get("labels") or ():
        d = _norm(x.get("description") if isinstance(x, dict) else x)
        if d in ETIQUETAS_FORA:
            return d
    return ""


def criada_pelo_cos(linha: dict, cos: dict | None) -> bool:
    """Quem criou a OS é do COS? Pelo código da pessoa no Fracttal e, sem ele, pelo nome."""
    if not cos:
        return False
    cod, nome = _norm(linha.get("code_create_by")), _norm(linha.get("created_by"))
    return bool((cod and cod in cos.get("codigos", ())) or (nome and nome in cos.get("nomes", ())))


def _quando(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def espera_txt(horas: float) -> str:
    """"3 d 4 h", "5 h", "40 min": a mesma escrita da idade das PT."""
    m = int(round(horas * 60))
    if m >= 1440:
        return f"{m // 1440} d {(m % 1440) // 60} h"
    if m >= 60:
        return f"{m // 60} h"
    return f"{max(m, 0)} min"


def oss(linhas: list[dict], usinas: dict, cos: dict | None, agora: datetime) -> dict:
    """{"lista": as OS (a que espera há mais tempo primeiro), "fora": quantas OS das usinas ficaram de fora e por quê}.
    `linhas` = a fila guardada (as tarefas em revisão); `usinas` = {nome do Fracttal normalizado (`regras_app._norm`): a
    usina do cadastro ({"usina", "cliente", ...})}, só as do responsável (e do cliente e da busca da tela)."""
    por: dict = {}
    for w in linhas or ():
        u = usinas.get(regras_app._norm(w.get("groups_1_description")))
        wo = w.get("id_work_order")
        if not u or not wo:
            continue
        o = por.get(wo)
        if o is None:
            o = por[wo] = {"id_wo": wo, "os": str(w.get("wo_folio") or ""), "criada": _quando(w.get("creation_date")),
                           "titulo": " ".join(str(w.get("description") or "").split()),
                           "tecnico": " ".join(str(w.get("personnel_description") or "").split()),
                           "usina": u.get("usina") or "", "cliente": u.get("cliente") or "", "_itens": set(),
                           "_fim": None, "etiqueta": "", "cos": False}
        o["_itens"].add(w.get("id_item") or w.get("code") or w.get("id_work_orders_tasks"))
        fim = _quando(w.get("final_date"))
        if fim and (o["_fim"] is None or fim < o["_fim"]):
            o["_fim"] = fim
        o["etiqueta"] = o["etiqueta"] or etiqueta_fora(w)
        o["cos"] = o["cos"] or criada_pelo_cos(w, cos)
    lista, fora = [], {"etiqueta": 0, "cos": 0}
    for o in por.values():
        if o["etiqueta"]:
            fora["etiqueta"] += 1
            continue
        if o["cos"]:
            fora["cos"] += 1
            continue
        fim = o.pop("_fim")
        horas = (agora - fim).total_seconds() / 3600 if fim else None
        lista.append({**{k: v for k, v in o.items() if not k.startswith("_")}, "ativos": len(o["_itens"]),
                      "criada_txt": o["criada"].astimezone(_BRT).strftime("%d/%m/%Y") if o["criada"] else "—",
                      "espera_h": horas, "espera": espera_txt(horas) if horas is not None else "—",
                      "espera_d": int(horas // 24) if horas is not None else None})
    lista.sort(key=lambda x: (-(x["espera_h"] if x["espera_h"] is not None else -1), x["os"]))
    return {"lista": lista, "fora": fora}


def criadores_cos(base: str, sessao, ler_pessoal) -> dict:
    """{"nomes", "codigos", "pessoas", "erro"}: quem está hoje no setor COS (a última decisão de cada pessoa no livro
    `nexus_setores`), pelo nome e pelo código no Fracttal (`ler_pessoal`, o pessoal guardado 1 h). Guardado 10 min. Sem o
    setor, vazio (nada sai por COS)."""
    v = _COS["v"]
    if v is not None and time.time() - _COS["t"] < TTL_COS_S:
        return v
    from ..cadastro import setores as S
    st = S.ler(base, sessao)
    sid = {x["setor_id"] for x in S.ativos(st.get("setores") or []) if S._norm(x["nome"]) == SETOR_COS}
    quem = {str(fid) for fid, s in S.vigentes(st.get("decisoes") or []).items() if s in sid}
    p = ler_pessoal() or {}
    codigos = p.get("codigos") or {}
    nomes, cods = set(), set()
    for x in p.get("pessoas") or ():
        if str(x.get("id")) in quem:
            nomes.add(_norm(x.get("nome")))
            cods.add(_norm(codigos.get(x.get("id"))))
    v = {"nomes": nomes - {""}, "codigos": cods - {""}, "pessoas": len(quem),
         "erro": st.get("erro") or p.get("erro") or ""}
    _COS.update(t=time.time(), v=v)
    return v


def limpar() -> None:
    _COS.update(t=0.0, v=None)
