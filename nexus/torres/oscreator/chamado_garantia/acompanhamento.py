"""A OS de ACOMPANHAMENTO do chamado (a 3ª do fluxo: Administrativa, etiqueta CHAMADOS, do time de chamados).

A administrativa nasce quando a Inspeção é REALIZADA, com as respostas do técnico na nota (Levi, 08/11/2026: "quero que a
administrativa só nasça quando a de inspeção é realizada!"; o desenho do mesmo dia a fazia nascer junto com a Inspeção, e
isso foi revertido): o App cria a dele no fechamento, e o OS Creator a da Inspeção realizada que ficou sem (a do
supervisor, a fechada na web). Até a 1.2.0 o que a administrativa leva morava só no servidor do App
(`_acompanhamento_se_chamado` e `_mapa_chaves`); passou para cá para as duas pontas seguirem um padrão só. A nota com as respostas sai IGUAL à do App de hoje: o quadro do Acompanhamento de chamados do OS
Creator (`acomp_web`) lê a 1ª linha ("[CHAMADO] Acompanhamento") e acha o ticket pela subtarefa ("ticket"/"protocolo").

Fica FORA daqui, como no `montar` da Inspeção: o payload do RPC, os ids do Fracttal (tipo, etiqueta, pessoa) e o
responsável — cada lado tem o seu.
"""
from . import spec
from .ativos import tipo_do_ativo
from .regras import ETIQUETA_ACOMPANHAMENTO, TIPO_TAREFA_ACOMPANHAMENTO, derivados

AGUARDANDO_INSPECAO = "aguardando a inspeção"
# o texto da única subtarefa: o quadro do Acompanhamento acha o ticket por "ticket"/"protocolo" (acomp_web.item_do_ticket)
SUBTAREFA_TICKET = "Nº do ticket / protocolo aberto no fabricante"
MARCA_NOTA = "[CHAMADO] Acompanhamento"
TETO_NOTA = 3800          # o do App (o Fracttal corta a nota longa; 3800 deixa folga)
TETO_VALOR = 300          # cada resposta, como no App
LINHA_AGUARDANDO = "Campos do formulário do fabricante: %s" % AGUARDANDO_INSPECAO
_TRAD_VERIF = {1: "Aprovado", 2: "Alerta", 3: "Falhou", "1": "Aprovado", "2": "Alerta", "3": "Falhou"}


def mapa_chaves(tipo_ativo: str, marca: str) -> dict:
    """{descrição em minúsculas: chave do formulário do fabricante}. Os mesmos blocos, o mesmo filtro `so_para` e a mesma
    deduplicação do `spec.subtarefas`, mas guardando a `chave`, que o formato do RPC descarta: é ela que liga a resposta do
    técnico ao campo do chamado. Era o `_mapa_chaves` do servidor do App (até a 1.2.0)."""
    grupo = spec.grupo_de(tipo_ativo)
    blocos = (spec.BASE + spec.POR_TIPO.get(grupo, []) + spec.POR_FABRICANTE.get((marca or "").strip(), []))
    out, vistos = {}, set()
    for s in blocos:
        if s.get("so_para") and grupo not in s["so_para"]:
            continue
        k = s["desc"].strip().lower()
        if k in vistos:
            continue
        vistos.add(k)
        out[k] = s.get("chave") or ""
    return out


def respostas_de(checklist, itens) -> list:
    """[(descrição, valor em texto)] das respostas do técnico, na ordem do checklist: o que o App monta do fechamento
    (`dados.checklist` com {id, desc, tipo} e `dados.items` {id: valor}). Resposta vazia, None ou False fica de fora; a de
    Verificação vira Aprovado/Alerta/Falhou e o True vira "Sim", como no App."""
    itens = itens or {}
    out = []
    for c in checklist or []:
        if not isinstance(c, dict):
            continue
        desc = str(c.get("desc") or "").strip()
        v = itens.get(c.get("id"))
        if v in (None, "", False):
            continue
        if c.get("tipo") == "verif":
            v = _TRAD_VERIF.get(v, v)
        elif v is True:
            v = "Sim"
        out.append((desc, str(v)[:TETO_VALOR]))
    return out


def _separar(respostas, mapa: dict) -> tuple:
    """(com_chave, extras): a resposta cuja descrição tem chave no formulário do fabricante vai com a chave; a que já vem
    pela chave (quem chamou já traduziu) fica como está; o resto vai em "Demais respostas" pela descrição."""
    chaves = {c for c in mapa.values() if c}
    com_chave, extras = [], []
    for item in respostas or []:
        try:
            k, v = item
        except (TypeError, ValueError):
            continue
        k = str(k or "").strip()
        v = str(v if v is not None else "")[:TETO_VALOR]
        if not k or v == "":
            continue
        ch = mapa.get(k.lower())
        if ch:
            com_chave.append((ch, v))
        elif k in chaves:
            com_chave.append((k, v))
        else:
            extras.append((k, v))
    return com_chave, extras


def montar_acompanhamento(inspecao: dict, fabricante: str, respostas=None) -> dict:
    """O que a OS de acompanhamento leva, num dicionário só.

    `inspecao` = {"folio", "code", "nome_ativo", "tipo", "os_pai" ("" sem OS pai), "event_date" (ISO, o incidente)};
    `respostas` = a lista [(descrição, valor)] do `respostas_de` (aceita também a chave do formulário no lugar da
    descrição), as respostas da Inspeção realizada. None dá o bloco "aguardando a inspeção" (do desenho revertido em
    08/11/2026, a administrativa junto com a Inspeção): hoje ninguém a usa.

    → {"titulo", "nota", "tipo_tarefa", "etiqueta", "subtarefas", "campos", "extras", "aguardando"}"""
    i = inspecao or {}
    code = str(i.get("code") or "").strip()
    tipo = str(i.get("tipo") or "").strip() or tipo_do_ativo(code)
    marca = str(fabricante or "").strip()
    nome_ativo = str(i.get("nome_ativo") or "").strip()[:60] or code
    der = derivados({"tipo": tipo}, i.get("event_date"))
    linhas = ["%s — %s · %s" % (MARCA_NOTA, marca or "marca a confirmar", tipo),
              "OS de campo: %s · Inspeção: %s · Ativo: %s" % (str(i.get("os_pai") or "").strip() or "-",
                                                              str(i.get("folio") or "").strip(), code),
              "Data da falha: %s · Menos de 7 dias: %s" % (der.get("data_falha", "-"), der.get("menos_7d", "-")), ""]
    com_chave, extras = [], []
    if respostas is None:
        linhas.append(LINHA_AGUARDANDO)
    else:
        com_chave, extras = _separar(respostas, mapa_chaves(tipo, marca))
        if com_chave:
            linhas.append("Campos do formulário do fabricante (coletados na inspeção):")
            linhas += ["  %s: %s" % kv for kv in com_chave]
        if extras:
            linhas.append("Demais respostas:")
            linhas += ["  %s: %s" % kv for kv in extras]
    return {
        "titulo": ("[%s] - Acompanhamento de chamado %s" % (nome_ativo, marca)).strip(),
        "nota": "\n".join(linhas)[:TETO_NOTA],
        "tipo_tarefa": TIPO_TAREFA_ACOMPANHAMENTO,
        "etiqueta": ETIQUETA_ACOMPANHAMENTO,
        "subtarefas": [{"description": SUBTAREFA_TICKET, "id_task_form_item_type": 1, "is_required": False,
                        "attachments_required": False}],
        "campos": len(com_chave),
        "extras": len(extras),
        "aguardando": respostas is None,
    }


def nota_aguardando(nota) -> bool:
    """A nota da administrativa ainda está esperando a inspeção (nasceu com ela e não foi preenchida)?"""
    return LINHA_AGUARDANDO.lower() in str(nota or "").lower()
