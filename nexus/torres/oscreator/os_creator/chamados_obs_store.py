# -*- coding: utf-8 -*-
"""As observações da equipe de chamados sobre cada OS de acompanhamento (a OS 3), no banco da Gridco: workbook
`os_creator`, aba `chamados_obs`, UMA LINHA POR OBSERVAÇÃO.

Pedido do Levi em 27/09/2026: "ao clicar na OS abre uma tela onde ela vê todas as informações do chamado daquele ativo
e pode escrever observações, essas observações vão salvar o dia que a analista de chamados escreveu".

POR QUE NÃO NA NOTA DA OS: a nota da OS 3 é a cópia das respostas do técnico, montada pelo servidor do App (até 3.800
caracteres, de onde se abre o ticket no fornecedor). Misturar o diário ali estragaria as duas coisas — e editar a nota
troca o texto INTEIRO: duas pessoas escrevendo ao mesmo tempo, uma perde o que escreveu.

SÓ POST, NUNCA PUT: linha nova a cada vez é o que torna a escrita segura entre duas pessoas (não há linha para uma
sobrescrever a da outra) e o que mantém o histórico honesto. Desde 29/10/2026 a tela edita e exclui a observação escrita
(o administrador do Nexus ou o setor Chamados), também por linha nova (`edicao`, `exclusao`): a original nunca muda, e a
tela mostra a versão em vigor (`vigentes`).

A DATA É DO SERVIDOR, em Brasília, carimbada na hora em que a linha é gravada — a pessoa não digita data. A planilha de
chamados tinha 3 datas digitadas no futuro (2027); aqui isso não acontece.
"""
import datetime as dt
import json
import threading
import time
import uuid

import gridco_abas as ga

WORKBOOK = "os_creator"
NOME_ABA = "chamados_obs"
# `extra` é JSON para o que vier depois: a aba não alarga depois de criada (ver gridco_abas.Aba.id)
COLUNAS = ["id", "quando", "os", "ativo", "tipo", "texto", "quem", "email", "extra"]
# "status" (27/10/2026): a troca do status do chamado pela tela (Testes em campo, Aguardando retorno do Fabricante...),
# uma linha por troca, com o status em `extra` e a frase no texto ("Status: Standby"), que o código de antes mostra como
# observação comum
TIPOS = ("obs", "ticket", "finalizado", "status", "edicao", "exclusao")
# Editar e excluir (29/10/2026, Levi: "gostaria de poder excluir a observação e editar a observação"; quem pode, o
# Nexus decide: o administrador ou o setor Chamados) também só ACRESCENTAM: a linha `edicao` traz o texto novo e a
# `exclusao` some com a observação, as duas apontando a original em `extra.de`. A original nunca muda no banco; a tela
# mostra a versão em vigor (`vigentes`). Só a observação escrita muda; os automáticos (ticket, status, finalizado), não.
EDITAVEIS = ("obs",)
LIMITE_TEXTO = 2000
TTL = 60           # s: a leitura da aba inteira vale isto (a própria escrita já entra no cache na hora)
# Vencida, a leitura de antes sai NA HORA e a aba é relida por trás, uma releitura por vez (28/10/2026: o banco da Gridco
# levou 20,2 s com erro, 21,4 s e 0,8 s em três leituras seguidas; o quadro do Acompanhamento esperava isso a cada
# minuto, e no erro mostrava "Read timed out" e desligava o pulso e o status). Só a 1ª leitura, sem nada guardado,
# espera; a releitura que falha fica com a de antes.

ABA = ga.Aba(WORKBOOK, NOME_ABA, COLUNAS)
SemCredencial = ga.SemCredencial

_estado = {"lista": None, "lido": 0.0, "renovando": False}
_trava = threading.Lock()
BRT = dt.timezone(dt.timedelta(hours=-3))


def agora_brt() -> dt.datetime:
    return dt.datetime.now(BRT).replace(microsecond=0)


def _linhas() -> list:
    """As linhas cruas — o ÚNICO ponto que vai à rede na leitura (os testes trocam só este)."""
    return ABA.linhas()


def _de_linha(l: dict):
    r = ABA.registro(l)
    if not (str(r.get("id") or "").strip() and str(r.get("quando") or "").strip() and str(r.get("os") or "").strip()):
        return None
    try:
        extra = json.loads(r.get("extra") or "{}")
    except (TypeError, ValueError):
        extra = {}
    tipo = str(r.get("tipo") or "obs").strip()
    return {"id": str(r["id"]).strip(), "quando": str(r["quando"]).strip(), "os": str(r["os"]).strip(),
            "ativo": str(r.get("ativo") or "").strip(), "tipo": tipo if tipo in TIPOS else "obs",
            "texto": str(r.get("texto") or ""), "quem": str(r.get("quem") or "").strip(),
            "email": str(r.get("email") or "").strip(), "extra": extra if isinstance(extra, dict) else {}}


def _em_segundo_plano(fn):
    """Onde a releitura roda: uma thread solta (os testes trocam para rodar quando querem)."""
    threading.Thread(target=fn, daemon=True, name="chamados-obs-reler").start()


def _reler():
    try:
        _ler()
    except Exception:                                   # noqa: BLE001 — fica a leitura de antes; a próxima visita tenta
        pass
    finally:
        with _trava:
            _estado["renovando"] = False


def listar(forcar: bool = False) -> list:
    """Todas as observações, da mais antiga à mais nova. Vencida, sai a de antes e a aba é relida por trás; levanta só
    sem nada guardado (ou no `forcar`) e o banco sem responder."""
    with _trava:
        if _estado["lista"] is not None and not forcar:
            if time.time() - _estado["lido"] >= TTL and not _estado["renovando"]:
                _estado["renovando"] = True
                _em_segundo_plano(_reler)
            return list(_estado["lista"])
    return _ler()


def _ler() -> list:
    vistos, lista = set(), []
    for l in _linhas():
        x = _de_linha(l)
        if x and x["id"] not in vistos:               # o id é o que impede o clique duplo de virar duas entradas
            vistos.add(x["id"])
            lista.append(x)
    lista.sort(key=lambda x: x["quando"])
    with _trava:
        _estado.update(lista=lista, lido=time.time())
    return list(lista)


def vigentes(lista) -> list:
    """As observações como a tela mostra: a editada com o texto da última edição (`editada_em`, `editada_por`; a data dela
    continua a de quando foi escrita), sem a excluída e sem as linhas de edição e exclusão. Edição ou exclusão que aponta
    uma automática (ou uma que não existe) não vale."""
    por_id = {x["id"]: x for x in lista}
    edicoes, excluidas = {}, set()
    for x in lista:                                     # da mais antiga à mais nova: a última edição vence
        if x["tipo"] not in ("edicao", "exclusao"):
            continue
        de = str((x.get("extra") or {}).get("de") or "")
        alvo = por_id.get(de)
        if not alvo or alvo["tipo"] not in EDITAVEIS:
            continue
        if x["tipo"] == "edicao":
            edicoes[de] = x
        else:
            excluidas.add(de)
    out = []
    for x in lista:
        if x["tipo"] in ("edicao", "exclusao") or x["id"] in excluidas:
            continue
        e = edicoes.get(x["id"])
        out.append(dict(x, texto=e["texto"], editada_em=e["quando"], editada_por=e["quem"]) if e else x)
    return out


def do_os(folio) -> list:
    alvo = str(folio).strip()
    return [x for x in vigentes(listar()) if x["os"] == alvo]


def ultima_por_os() -> dict:
    """{nº da OS: quando da última entrada} — a régua da cobrança ("há N dias sem atualização")."""
    out = {}
    for x in vigentes(listar()):
        out[x["os"]] = max(out.get(x["os"], ""), x["quando"])
    return out


def finalizado_por_os() -> dict:
    """{nº da OS: quando foi finalizada pela tela}. A OS de acompanhamento é concluída sem registro de execução, e aí o
    Fracttal deixa a data de fim VAZIA — sem esta data o card finalizado não diria quando, nem sairia do quadro."""
    out = {}
    for x in listar():
        if x["tipo"] == "finalizado":
            out[x["os"]] = max(out.get(x["os"], ""), x["quando"])
    return out


def status_por_os() -> dict:
    """{nº da OS: o status da última troca} — "" quando a última troca foi para "sem status". OS nunca trocada não
    aparece (aí vale o "Status atual" da nota da retroativa, `acomp_web.status_atual`)."""
    out = {}
    for x in listar():
        if x["tipo"] == "status":
            st = (x.get("extra") or {}).get("status")
            out[x["os"]] = str(st if st is not None else "").strip()
    return out


def adicionar(os_folio, texto: str, tipo: str = "obs", ativo: str = "", quem: str = "", email: str = "",
              extra: dict = None, agora: dt.datetime = None, id_: str = "") -> dict:
    """Grava UMA observação, com a data e a hora do servidor. → o registro gravado."""
    texto = str(texto or "").strip()
    if not texto:
        raise ValueError("Escreva a observação antes de salvar.")
    if len(texto) > LIMITE_TEXTO:
        raise ValueError("A observação passa de %d caracteres." % LIMITE_TEXTO)
    if tipo not in TIPOS:
        raise ValueError("Tipo de observação desconhecido: %s." % tipo)
    if not str(os_folio or "").strip():
        raise ValueError("Sem o número da OS.")
    reg = {"id": (id_ or uuid.uuid4().hex[:12]), "quando": (agora or agora_brt()).isoformat(),
           "os": str(os_folio).strip(), "ativo": str(ativo or "").strip(), "tipo": tipo, "texto": texto,
           "quem": str(quem or "").strip(), "email": str(email or "").strip(), "extra": dict(extra or {})}
    ABA.inserir(dict(reg, extra=json.dumps(reg["extra"], ensure_ascii=False)))
    with _trava:
        if _estado["lista"] is not None and all(x["id"] != reg["id"] for x in _estado["lista"]):
            _estado["lista"].append(reg)
            _estado["lista"].sort(key=lambda x: x["quando"])
    return reg
