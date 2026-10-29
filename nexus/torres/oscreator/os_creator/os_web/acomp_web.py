# os_creator/os_web/acomp_web.py
"""Acompanhamento de chamados (Levi, 27/09/2026): o quadro das OS de acompanhamento e a tela de cada uma. PURO — sem
Flask e sem rede; as rotas moram em `rotas_acomp.py`.

O QUE É A OS DE ACOMPANHAMENTO (a "OS 3" do chamado de garantia; ver app-campo-docs/notas-e-os-administrativa.html):
quando o técnico fecha a inspeção do chamado no App de Campo, o servidor do App cria sozinho a OS
"[Ativo] - Acompanhamento de chamado <marca>" — tipo Administrativa, etiqueta CHAMADOS, filha da inspeção, no nome
da equipe de chamados — com as respostas do técnico na NOTA e UMA subtarefa: o nº do ticket aberto no fornecedor.
Desde 20/10/2026 há também a RETROATIVA: a analista de chamados cria à mão a OS 3 de um chamado que já existia, com a
nota no jeito dela (a cadeia, a abertura do chamado e o histórico; ver `ler_nota`).

AS TRÊS COLUNAS saem da própria OS, sem estado paralelo em lugar nenhum:
    Chegaram       em processo e a subtarefa do ticket ainda vazia — é a fila da analista de chamados
    Ticket aberto  a subtarefa do ticket preenchida — o chamado está com o fornecedor
    Finalizados    a OS concluída (ou em verificação), nos últimos 90 dias
Cancelada fica fora do quadro (e é contada, para ninguém achar que sumiu).
"""
from __future__ import annotations

import datetime as dt
import os
import re
import unicodedata

import chamado_insp_spec as ci
import chamado_modelos_store as modelos

BRT = dt.timezone(dt.timedelta(hours=-3))
MARCA_NOTA = "[CHAMADO] Acompanhamento"
DIAS_FINALIZADOS = 90
# o pulso laranja da OS aberta sem comentário de atualização há 5 dias ou mais (Levi, 25/10/2026: "quando a OS ficar a
# partir de 5 dias sem comentário de atualização!"; o desenho é o do Quadro da equipe da Engenharia, que usa 7 dias)
DIAS_PARADA = 5
# o status do chamado que a analista de chamados escolhe na tela (27/10/2026, Levi: "Gostaria de poder mudar os status,
# pode ter essas opções"): a lista que ela mandou, na grafia dela (a mesma da planilha de gestão de chamados, de onde
# vem o "Status atual" da nota da retroativa). A linha em branco da lista dela é o "Sem status" da tela.
STATUS_CHAMADO = ("Testes em campo", "Aguardando retorno do Cliente", "Aguardando retorno do Supervisor",
                  "Aguardando retorno do Fabricante", "Aguardando retorno Pré - Operação", "Aguardando Abertura de OS",
                  "Standby", "Aguardando coleta do equipamento defeituoso")
# o status geral, AUTOMÁTICO pelo status (Levi, 28/10/2026: "Os gerais serão automáticos: Atividade Grid: Teste em Campo,
# Aguardando abertura de OS, Aguardando retorno Pré - Operação, Aguardando retorno do Supervisor; Atividade Cliente:
# Aguardando retorno do Cliente; Atividade Fabricante: Aguardando coleta do equipamento defeituoso, Aguardando retorno do
# Fabricante"; "stand by deixa de ser status comum e vira status geral": escolhido no mesmo seletor). É ele que agrupa
# o relatório que vai ao cliente e o filtro Status Gerais do quadro.
STATUS_GERAL = ("Grid", "Cliente", "Fabricante", "Standby")
GERAL_DO_STATUS = {"Testes em campo": "Grid", "Aguardando Abertura de OS": "Grid",
                   "Aguardando retorno Pré - Operação": "Grid", "Aguardando retorno do Supervisor": "Grid",
                   "Aguardando retorno do Cliente": "Cliente",
                   "Aguardando coleta do equipamento defeituoso": "Fabricante",
                   "Aguardando retorno do Fabricante": "Fabricante", "Standby": "Standby"}

# o nome técnico do campo (o que a nota traz) → como a tela chama. É esse nome que liga a resposta do técnico ao campo
# do formulário do fornecedor — por isso ele continua visível, pequeno, embaixo do rótulo.
ROTULO = {"problema": "Descrição do problema", "acoes": "Ações já realizadas", "serial": "Nº de série",
          "modelo": "Modelo", "alarme": "ID do alarme", "tag": "TAG na usina", "tipo_equip": "Componente com falha",
          "mac": "Nº de MAC", "testes": "Testes e valores medidos", "serial_dl": "Nº de série do datalogger",
          "op_desde": "Em operação desde", "evidencias": "Fotos da instalação", "titulo_ch": "Objetivo do chamado",
          "gw_id": "ID do Gateway", "tracker_id": "IDs dos rastreadores", "produto": "Produto (catálogo Sungrow)",
          "posicao": "Posição do sensor", "acessorios": "Acessórios"}
MONO = {"serial", "mac", "modelo", "serial_dl", "gw_id", "tracker_id", "alarme"}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def agora_brt() -> dt.datetime:
    """Agora em Brasília, SEM fuso no objeto (as contas de dia são todas em horário local)."""
    return dt.datetime.now(BRT).replace(tzinfo=None, microsecond=0)


def utc_para_brt(iso):
    """'2026-09-03T11:25:36' (UTC, como o Fracttal devolve) → datetime de Brasília sem fuso. Vazio/estragado → None."""
    s = str(iso or "").strip().replace(" ", "T")[:19]
    if len(s) < 19:
        return None
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S") - dt.timedelta(hours=3)
    except ValueError:
        return None


def brt_iso(iso):
    """'2026-09-26T09:12:05-03:00' (a data das observações, já em Brasília) → datetime sem fuso."""
    try:
        d = dt.datetime.fromisoformat(str(iso or "").strip())
    except ValueError:
        return None
    return d.astimezone(BRT).replace(tzinfo=None) if d.tzinfo else d


def dias(de, ate) -> int | None:
    if de is None or ate is None:
        return None
    return max(0, (ate.date() - de.date()).days)


# ── a OS 3 e a nota dela ──────────────────────────────────────────────────────────────────────────────────────
def eh_os3(l: dict) -> bool:
    """A OS de acompanhamento, e não as 55 antigas com a etiqueta CHAMADOS (modelo de antes, etiqueta colada numa OS
    qualquer). O bloco da nota é o sinal forte; o título + tipo Administrativa cobrem nota vazia."""
    if MARCA_NOTA in str(l.get("note") or ""):
        return True
    return "acompanhamento de chamado" in _norm(l.get("descricao")) and "administrativa" in _norm(l.get("tipo_tarefa"))


def _perguntas() -> list:
    """Os textos de pergunta que a nota pode trazer em "Demais respostas" — do modelo em vigor e do código (a nota foi
    montada pelo App, que usa a cópia DELE do pacote). Do mais longo ao mais curto, para casar o mais específico."""
    blocos = [ci.BASE, modelos._ORIG["BASE"]]
    for d in (ci.POR_TIPO, modelos._ORIG["POR_TIPO"], ci.POR_FABRICANTE, modelos._ORIG["POR_FABRICANTE"]):
        blocos += list(d.values())
    return sorted({s["desc"] for b in blocos for s in b if s.get("desc")}, key=len, reverse=True)


# A OS 3 RETROATIVA (20/10/2026): a analista de chamados criou à mão, no Fracttal, a OS de acompanhamento de um chamado
# que só existia na planilha de gestão de chamados, com a nota no jeito dela: "OS de abertura: 11199 · OS de campo:
# 12565 · Solicitação: 3504 · Ativo: …" (a 11199 é a corretiva onde a falha apareceu, a OS de campo do App; a 12565, do
# tipo Inspeção, é a inspeção), a "Data da ocorrência / abertura do chamado" e o "Histórico (importado …)" com uma linha
# por data. A tela mostrou a cadeia e o ativo vazios e o chamado "chegando hoje". Levi, no mesmo dia: a nota dela vale
# como ela escreve, e sem cadeia na nota entra a OS mãe do Fracttal (`cadeia_pela_mae`).
_RX_CADEIA = re.compile(r"\b(?:OS de campo|OS de abertura|Inspeção|Ativo)\s*:")
_RX_ABERTURA = re.compile(r"^(?:Data da ocorrência(?:\s*/\s*abertura do chamado)?|Abertura do chamado)\s*:\s*(.*)$",
                          re.IGNORECASE)
_RX_HISTORICO = re.compile(r"^(\d{2}/\d{2}(?:/\d{4})?)\s*[-–—:]\s*(.+)$")
_CHAVES_DA_CADEIA = {"os de campo", "os de abertura", "inspecao", "ativo"}


def _num(rx: str, s: str) -> str:
    m = re.search(rx, s)
    return m.group(1) if m else ""


def _data_br(s: str):
    """'21/08/2026' → datetime (00:00). Vazio ou estragado ('31/02/2026') → None."""
    try:
        return dt.datetime.strptime(str(s or "").strip()[:10], "%d/%m/%Y")
    except ValueError:
        return None


def _com_ano(ddmm: str, base) -> str:
    """'05/01' do histórico → '05/01/2026': o ano da abertura, e o seguinte quando a data cai antes dela (o chamado aberto
    em 20/12 e respondido em 05/01). Com o ano escrito, fica o escrito; sem a abertura, sem ano."""
    if len(ddmm) == 10 or base is None:
        return ddmm
    try:
        d = dt.datetime.strptime("%s/%d" % (ddmm, base.year), "%d/%m/%Y")
    except ValueError:
        return ddmm
    return (d.replace(year=base.year + 1) if d < base else d).strftime("%d/%m/%Y")


def ler_nota(nota: str) -> dict:
    """A nota da OS 3 de volta em partes: marca e tipo, a cadeia (OS de campo → inspeção → ativo), a data da falha, os
    campos do formulário do fornecedor e as demais respostas; da retroativa, também a data de abertura do chamado, as
    outras linhas "rótulo: valor" (`info`) e o histórico, com o ano.

    A pergunta das "Demais respostas" é casada contra o texto do modelo, porque ela mesma tem ':' ("Localização na
    planta: fileira, posição e nº dos trackers afetados: Tracker 40") — partir no primeiro ':' cortaria a pergunta."""
    out = {"marca": "", "tipo": "", "os_campo": "", "inspecao": "", "ativo": "", "data_falha": "", "menos7_nota": None,
           "campos": [], "demais": [], "abertura": "", "info": [], "historico": []}
    txt = str(nota or "")
    i = txt.find(MARCA_NOTA)
    if i < 0:
        return out
    linhas = txt[i:].split("\n")
    m = re.match(r"\[CHAMADO\] Acompanhamento\s+—\s+(.+?)\s+·\s+(.+)$", linhas[0].strip())
    if m:
        out["marca"], out["tipo"] = m.group(1).strip(), m.group(2).strip()
    perguntas = None
    modo = ""
    for l in linhas[1:]:
        s = l.strip()
        if not s:
            continue
        if not modo and _RX_CADEIA.search(s):
            # a cadeia em qualquer ordem: a do App começa por "OS de campo:"; a retroativa, por "OS de abertura:"
            abertura, campo = _num(r"OS de abertura:\s*(\d+)", s), _num(r"OS de campo:\s*(\d+)", s)
            insp = _num(r"Inspeção:\s*(\d+)", s)
            out["os_campo"], out["inspecao"] = (abertura, insp or campo) if abertura else (campo, insp)
            out["ativo"] = _num(r"Ativo:\s*(\S+)", s)
            for parte in s.split("·"):
                k, _, v = parte.partition(":")
                if v.strip() and _norm(k) not in _CHAVES_DA_CADEIA:
                    out["info"].append({"rotulo": k.strip(), "valor": v.strip()})
        elif not modo and _RX_ABERTURA.match(s):
            out["abertura"] = _num(r"(\d{2}/\d{2}/\d{4})", _RX_ABERTURA.match(s).group(1))
        elif not modo and s.startswith("Histórico") and s.endswith(":"):
            modo = "historico"
        elif modo == "historico" and not s.startswith(("Campos do formulário", "Demais respostas")):
            mm = _RX_HISTORICO.match(s)
            if mm:
                out["historico"].append({"data": mm.group(1), "texto": mm.group(2).strip()})
            elif out["historico"]:
                out["historico"][-1]["texto"] += " " + s           # a linha que continua a de cima
            else:
                out["historico"].append({"data": "", "texto": s})
        elif s.startswith("Data da falha:"):
            mm = re.search(r"Data da falha:\s*(\d{2}/\d{2}/\d{4}(?: \d{2}:\d{2})?)", s)
            out["data_falha"] = mm.group(1) if mm else ""
            mm = re.search(r"Menos de 7 dias:\s*(Sim|Não)", s)
            out["menos7_nota"] = (mm.group(1) == "Sim") if mm else None
        elif s.startswith("Campos do formulário"):
            modo = "campos"
        elif s.startswith("Demais respostas"):
            modo = "demais"
        elif modo == "campos":
            k, _, v = s.partition(":")
            k = k.strip()
            out["campos"].append({"chave": k, "rotulo": ROTULO.get(k, k), "valor": v.strip(), "mono": k in MONO})
        elif modo == "demais":
            perguntas = perguntas or _perguntas()
            p = next((q for q in perguntas if s.startswith(q + ":")), None)
            if p:
                out["demais"].append({"pergunta": p, "resposta": s[len(p) + 1:].strip()})
            else:
                k, _, v = s.partition(":")
                out["demais"].append({"pergunta": k.strip(), "resposta": v.strip()})
        elif not modo:
            # o resto do cabeçalho da retroativa (Status atual, Ticket, S/N, Título do e-mail…): mostrado, nunca jogado fora.
            # O título do e-mail tem ' - ' e '/', mas nenhum '·': só o '·' separa um rótulo do outro
            for parte in s.split("·"):
                k, _, v = parte.partition(":")
                out["info"].append({"rotulo": k.strip(), "valor": v.strip()} if v.strip() else
                                   {"rotulo": "", "valor": parte.strip()})
    base = _data_br(out["abertura"])
    for h in out["historico"]:
        h["data"] = _com_ano(h["data"], base)
    if out["abertura"] and not out["data_falha"]:
        out["data_falha"] = out["abertura"]          # ela escreveu "ocorrência / abertura": é também o dia da falha
    return out


def abertura_valida(n: dict, criada):
    """A abertura do chamado escrita na nota (`ler_nota`), como datetime à 00:00, quando ela vale: data de verdade e não
    depois da criação da OS (abertura "no futuro" da OS é erro de digitação). Senão None, e vale a criação da OS."""
    a = _data_br(n.get("abertura"))
    if a is None or (criada is not None and a.date() > criada.date()):
        return None
    return a


def cadeia_pela_mae(n: dict, folio_mae: str, tipo_mae: str) -> dict:
    """A cadeia do chamado ({os_campo, inspecao}). Com ela na nota, vale a nota. Sem ela (a retroativa escrita sem a linha
    da cadeia), a OS mãe da OS 3 no Fracttal entra pelo tipo dela: a do tipo Inspeção é a inspeção (a OS 3 do App é filha
    da inspeção); outra (a corretiva onde a falha apareceu) é a OS de campo."""
    if n.get("os_campo") or n.get("inspecao"):
        return {"os_campo": n.get("os_campo") or "", "inspecao": n.get("inspecao") or ""}
    folio_mae = str(folio_mae or "").strip()
    if not folio_mae:
        return {"os_campo": "", "inspecao": ""}
    if "inspecao" in _norm(tipo_mae):
        return {"os_campo": "", "inspecao": folio_mae}
    return {"os_campo": folio_mae, "inspecao": ""}


def marca_do_titulo(titulo: str) -> str:
    m = re.search(r"Acompanhamento de chamado\s+(.+)$", str(titulo or "").strip())
    return m.group(1).strip() if m else ""


def menos_7d(data_falha: str, hoje: dt.datetime) -> dict:
    """"Menos de 7 dias" RECALCULADO hoje. A nota congela o que valia no fechamento da inspeção; o formulário da Huawei
    pergunta no dia em que a analista de chamados abre o ticket (13926: a nota diz Sim, nove dias depois já é Não)."""
    try:
        f = dt.datetime.strptime(str(data_falha or "").strip()[:16], "%d/%m/%Y %H:%M")
    except ValueError:
        try:
            f = dt.datetime.strptime(str(data_falha or "").strip()[:10], "%d/%m/%Y")
        except ValueError:
            return {"sim": None, "dias": None}
    d = max(0, (hoje - f).days)
    return {"sim": d < ci.DIAS_DOA, "dias": d}


def item_do_ticket(subtarefas) -> dict | None:
    """A subtarefa do nº do ticket na lista do `get_os_detalhes` (a OS 3 tem só ela; casa pelo texto)."""
    for s in subtarefas or []:
        d = _norm(s.get("descricao"))
        if "ticket" in d or "protocolo" in d:
            return s
    return None


def texto_ticket(novo: str, antigo: str) -> str:
    antigo = str(antigo or "").strip()
    return ("Ticket alterado: %s → %s" % (antigo, novo)) if antigo else ("Ticket registrado: %s" % novo)


def equipe() -> tuple:
    """(id, nome) da equipe de chamados no Fracttal — o MESMO padrão do servidor do App (CHAMADO_RESP_ID/NOME, v198).

    Vem do .env (`OS_WEB_CHAMADO_RESP_ID`, `OS_WEB_CHAMADO_RESP_NOME`) e não do código: o repositório é público e não leva
    nome nem id de gente. Lido a cada chamada, e não no import, porque o .env só entra quando o `api` é importado."""
    try:
        rid = int(os.environ.get("OS_WEB_CHAMADO_RESP_ID") or 0)
    except ValueError:
        rid = 0
    return rid, " ".join((os.environ.get("OS_WEB_CHAMADO_RESP_NOME") or "").split())


def da_equipe(l: dict) -> bool:
    """A OS está no nome da equipe de chamados? Pelo id quando a linha traz; pelo nome quando não.

    Sem a equipe no .env, ninguém é "de fora": o aviso de OS no nome de outra pessoa só vale quando se sabe quem é a
    equipe — acusar todas as OS do quadro seria um alarme falso em cada card."""
    rid, nome = equipe()
    if not rid and not nome:
        return True
    try:
        if rid and l.get("id_atribuido") not in (None, ""):
            return int(l["id_atribuido"]) == rid
    except (TypeError, ValueError):
        pass
    return bool(nome) and _norm(l.get("atribuido_a")) == _norm(nome)


def coluna(status_id, ticket) -> str:
    if status_id == 4:
        return ""                                         # cancelada: fora do quadro
    if status_id in (2, 3):
        return "fim"
    return "ticket" if str(ticket or "").strip() else "chegou"


def local_txt(cliente, usina) -> str:
    return " · ".join(x for x in (str(cliente or "").strip(), str(usina or "").strip()) if x and x != "—")


def _quando_txt(n: int | None, jeito: str) -> str:
    if n is None:
        return ""
    if jeito == "chegou":
        return "chegou hoje" if n == 0 else ("chegou há 1 dia" if n == 1 else "chegou há %d dias" % n)
    return "atualizado hoje" if n == 0 else ("há 1 dia sem atualização" if n == 1 else "há %d dias sem atualização" % n)


def urgencia(col: str, n: int | None) -> str:
    """A cor do tempo segue o SEMÁFORO. Chegou: a fila é nossa, e 8 dias parada já é vermelho. Ticket aberto: é a
    régua da cobrança — a planilha tinha mediana de 22 dias sem atualização, 75% passando de 15."""
    if n is None or col == "fim":
        return "m"
    if col == "chegou":
        return "r" if n >= 8 else ("a" if n >= 3 else "m")
    if n == 0:
        return "g"
    return "r" if n >= 16 else ("a" if n >= 8 else "m")


CORES_AVATAR = 4     # as cores do avatar do responsável (chamados.css, .k-av0 a .k-av3)


def cor_avatar(nome: str) -> int:
    """A cor do avatar do responsável no cartão: a mesma pessoa tem sempre a mesma, como no Quadro da equipe da
    Engenharia do Nexus. Soma das letras e não `hash()`, que muda a cada processo (a cor trocaria a cada reinício)."""
    return sum(map(ord, _norm(nome))) % CORES_AVATAR if _norm(nome) else 0


def status_geral(status: str) -> str:
    """O status geral do status (`GERAL_DO_STATUS`); "" sem status ou com um que não é da lista (o da planilha antiga)."""
    return GERAL_DO_STATUS.get(str(status or "").strip(), "")


def status_atual(trocado, n: dict) -> str:
    """O status do chamado: o da última troca pela tela (`trocado`, "" = trocado para "sem status"); sem troca nenhuma
    (None), o "Status atual" escrito na nota da retroativa."""
    if trocado is not None:
        return str(trocado).strip()
    return next((x["valor"] for x in n.get("info") or [] if _norm(x.get("rotulo")) == "status atual"), "")


def cartao(l: dict, ticket, ultima_obs: str, hoje: dt.datetime, finalizado: str = "", obs_lidas: bool = True,
           status=None) -> dict:
    """Uma linha da lista do Fracttal + o ticket + a última observação → o que o card e a tela precisam.

    `finalizado` = quando a tela finalizou (do banco). A OS de acompanhamento é concluída sem registro de execução, e
    o Fracttal deixa a data de fim vazia nesse caso — então a data da finalização é a que diz "em 26/09".
    `obs_lidas` falso = as observações não vieram do banco: nenhuma OS pulsa (`parada`). `status` = o da última troca
    pela tela (None: nunca trocado; ver `status_atual`)."""
    n = ler_nota(l.get("note"))
    criada = utc_para_brt(l.get("data"))
    # a retroativa (criada à mão para um chamado que já existia) conta a idade da abertura escrita na nota, e não do dia
    # em que a OS entrou no Fracttal: a 1ª, de um chamado de 21/08, aparecia "chegou hoje" em 20/10
    aberto = abertura_valida(n, criada)
    chegou = aberto or criada
    fim = utc_para_brt(l.get("data_fim")) or (brt_iso(finalizado) if finalizado else None)
    ult = brt_iso(ultima_obs) if ultima_obs else None
    hist = [_data_br(h["data"]) for h in n["historico"]] if aberto else []
    referencia = max([x for x in [chegou, ult] + hist if x is not None], default=None)
    col = coluna(l.get("status_id"), ticket)
    d_chegou, d_sem = dias(chegou, hoje), dias(referencia, hoje)
    # o último comentário de atualização: a observação da tela (a do ticket gravado também) ou a data do histórico da
    # retroativa; sem nenhum, a abertura (a OS esquecida desde o início também pulsa)
    comentarios = [x for x in [ult] + hist if x is not None]
    marca = n["marca"] or marca_do_titulo(l.get("descricao"))
    c = {"id": l.get("id"), "folio": str(l.get("folio") or ""), "col": col, "status_id": l.get("status_id"),
         "status": l.get("status") or "", "ativo_nome": str(l.get("ativo") or "").strip() or n["ativo"],
         "code": n["ativo"], "cliente": l.get("cliente") or "", "usina": l.get("usina") or "",
         "local": local_txt(l.get("cliente"), l.get("usina")), "marca": marca, "tipo": n["tipo"] or l.get("tipo") or "",
         "inspecao": n["inspecao"], "os_campo": n["os_campo"], "data_falha": n["data_falha"],
         "ticket": str(ticket or "").strip(), "ticket_nao_lido": ticket is None,
         "chegou": (aberto.strftime("%d/%m/%Y") if aberto else criada.strftime("%d/%m/%Y %H:%M") if criada else ""),
         "criada": criada.strftime("%d/%m/%Y %H:%M") if criada else "", "retroativa": aberto is not None,
         "dias": d_chegou, "dias_sem": d_sem,
         # sem data nenhuma de fim (concluída direto no Fracttal, sem execução), a idade vem da chegada — senão a OS
         # nunca sairia da coluna dos 90 dias
         "fim": fim.strftime("%d/%m") if fim else "", "dias_fim": dias(fim or chegou, hoje),
         "responsavel": " ".join(str(l.get("atribuido_a") or "").split()), "da_equipe": da_equipe(l),
         "parada": parada(col, max(comentarios) if comentarios else chegou, hoje, obs_lidas),
         "status_ch": status_atual(status, n), "criado_por": " ".join(str(l.get("criado_por") or "").split()),
         # o Responsável UFV (o supervisor da usina) quem diz é o Nexus, pelo cadastro dele (rotas_acomp.RESPONSAVEL_UFV)
         "resp_ufv": ""}
    c["geral"] = status_geral(c["status_ch"])
    if not c["code"]:
        c["code"] = str(l.get("code") or "").strip()     # o código do ativo da lista, quando a nota não diz
    c["cor"] = cor_avatar(c["responsavel"])
    # `tempo_curto` é o estado no canto do cartão, no jeito do Quadro da equipe da Engenharia do Nexus ("atrasada 10 d",
    # "fechada 02/10"). Levi, 08/10/2026: "Precisamos padronizar a estética para que coisas parecidas não pareçam
    # completamente diferentes". A frase inteira continua em `tempo` (o title do cartão e a tela do chamado).
    if col == "chegou":
        c["tempo"], c["urg"] = _quando_txt(d_chegou, "chegou"), urgencia(col, d_chegou)
        # a coluna já diz "esperando ticket": a idade basta
        c["tempo_curto"] = "" if d_chegou is None else ("hoje" if d_chegou == 0 else "%d d" % d_chegou)
    elif col == "ticket":
        c["tempo"], c["urg"] = _quando_txt(d_sem, "ticket"), urgencia(col, d_sem)
        c["tempo_curto"] = "" if d_sem is None else ("atualizado hoje" if d_sem == 0 else "%d d sem atualização" % d_sem)
    else:
        c["tempo"], c["urg"] = ("em %s" % c["fim"]) if c["fim"] else "", "m"
        if col == "":
            c["tempo_curto"] = "cancelado"
        elif c["status_id"] == 2:                     # finalizado pela tela, esperando a verificação no Fracttal
            c["tempo_curto"] = ("em verificação %s" % c["fim"]) if c["fim"] else "em verificação"
        else:
            c["tempo_curto"] = ("fechado %s" % c["fim"]) if c["fim"] else "fechado"
    # a situação curta da tabela e da planilha (27/10/2026): a coluna e os dias (desde a chegada sem ticket; sem
    # atualização com o fornecedor); a finalizada, o estado do canto do cartão
    if col == "chegou":
        c["situacao"] = "Sem ticket" + ("" if d_chegou is None else " · %d d" % d_chegou)
    elif col == "ticket":
        c["situacao"] = "Com o fornecedor" + ("" if d_sem is None else " · %d d" % d_sem)
    else:
        c["situacao"] = (c["tempo_curto"] or "finalizado").capitalize()
    c["busca"] = _norm(" ".join(str(x or "") for x in (c["folio"], c["inspecao"], c["os_campo"], c["code"],
                                                          c["ativo_nome"], c["cliente"], c["usina"], marca,
                                                          c["ticket"], c["responsavel"])))
    return c


def parada(col: str, ultimo_comentario, hoje: dt.datetime, obs_lidas: bool = True) -> bool:
    """A OS ABERTA do quadro (Chegaram ou Ticket aberto) com DIAS_PARADA x 24 h ou mais desde o último comentário de
    atualização: o pulso laranja do cartão. Finalizada, em verificação ou cancelada não pulsa; sem as observações lidas
    do banco (fora do ar), nada pulsa, porque a OS comentada pareceria esquecida: não se chuta."""
    return (col in ("chegou", "ticket") and obs_lidas and ultimo_comentario is not None
            and hoje - ultimo_comentario >= dt.timedelta(days=DIAS_PARADA))


def precisa_ticket(l: dict, hoje: dt.datetime) -> bool:
    """Quem tem o ticket LIDO no Fracttal: as abertas e as finalizadas que ainda aparecem no quadro. A cota do Fracttal
    é por EMPRESA (200/min) — ler o ticket de OS que não vai para a tela seria gastar a dos outros."""
    st = l.get("status_id")
    if st in (1, 2):
        return True
    if st == 3:
        # sem data de fim (concluída sem execução) conta a chegada: lê de mais, nunca de menos
        d = dias(utc_para_brt(l.get("data_fim")) or utc_para_brt(l.get("data")), hoje)
        return d is None or d <= DIAS_FINALIZADOS
    return False


def montar_quadro(linhas, tickets: dict, ultimas: dict, hoje: dt.datetime, fins: dict = None,
                  obs_lidas: bool = True, status: dict = None) -> dict:
    fins, status = fins or {}, status or {}
    cards = [cartao(l, tickets.get(l.get("id"), ""), (ultimas or {}).get(str(l.get("folio") or ""), ""), hoje,
                    fins.get(str(l.get("folio") or ""), ""), obs_lidas, status.get(str(l.get("folio") or "")))
             for l in (linhas or []) if eh_os3(l)]
    col = {"chegou": [], "ticket": [], "fim": []}
    canceladas = antigas = 0
    for c in cards:
        if not c["col"]:
            canceladas += 1
        elif c["col"] == "fim" and c["dias_fim"] is not None and c["dias_fim"] > DIAS_FINALIZADOS:
            antigas += 1
        else:
            col[c["col"]].append(c)
    # a mais parada primeiro nas duas filas de trabalho; a finalizada mais recente primeiro
    col["chegou"].sort(key=lambda c: (-(c["dias"] or 0), c["folio"]))
    col["ticket"].sort(key=lambda c: (-(c["dias_sem"] or 0), c["folio"]))
    col["fim"].sort(key=lambda c: ((c["dias_fim"] if c["dias_fim"] is not None else 9999), c["folio"]))
    vis = col["chegou"] + col["ticket"] + col["fim"]
    opc = lambda k: sorted({c[k] for c in vis if c[k]}, key=lambda x: _norm(x))     # noqa: E731
    return {"colunas": col, "n": {k: len(v) for k, v in col.items()}, "total": len(vis), "canceladas": canceladas,
            "antigas": antigas, "fora": sum(1 for c in vis if not c["da_equipe"]),
            # a régua da cobrança na faixa de números: quantas esperam ticket há mais de uma semana, e a mais antiga
            "mais_7": sum(1 for c in col["chegou"] if (c["dias"] or 0) > 7),
            "mais_antiga": col["chegou"][0] if col["chegou"] else None,
            "opcoes": {"marca": opc("marca"), "cliente": opc("cliente"), "tipo": opc("tipo")}}


def outros(c: dict, todos) -> dict:
    """Os outros chamados do MESMO ativo e os da MESMA OS de campo (a 13761 abriu dois: Inversor 1.4 e 1.1)."""
    ativo = [x for x in todos if x["folio"] != c["folio"] and c.get("code") and x.get("code") == c["code"]]
    campo = [x for x in todos if x["folio"] != c["folio"] and c.get("os_campo") and x.get("os_campo") == c["os_campo"]
             and x not in ativo]
    return {"ativo": ativo, "campo": campo}


def entrada(reg: dict) -> dict:
    """Uma observação do banco → uma entrada da linha do tempo. A escrita (tipo obs) leva o id e `editavel` (os botões de
    editar e excluir, 29/10/2026); a editada diz quando e por quem."""
    q = brt_iso(reg.get("quando"))
    ed = brt_iso(reg.get("editada_em")) if reg.get("editada_em") else None
    editada = ("editada %s%s" % (ed.strftime("%d/%m %H:%M"), (" por %s" % reg["editada_por"]) if reg.get("editada_por")
                                  else "")) if ed else ""
    return {"d": q.strftime("%d/%m") if q else "", "a": q.strftime("%Y") if q else "", "texto": reg.get("texto") or "",
            "id": reg.get("id") or "", "editavel": reg.get("tipo") == "obs",
            "autor": " · ".join(x for x in (reg.get("quem") or "", q.strftime("%d/%m %H:%M") if q else "", editada) if x),
            "ev": reg.get("tipo") in ("ticket", "finalizado", "status"), "quando": reg.get("quando") or ""}


def linha_do_tempo(c: dict, obs, historico=None) -> list:
    """As observações da mais nova para a mais antiga, com a chegada da OS no fim (ela nasceu antes de tudo). O verde é
    EXCLUSIVO da entrada mais recente — "é o que aconteceu por último" (revisão do design do 1B).

    Na retroativa (`c["retroativa"]`), a OS não "nasceu sozinha": a entrada diz que ela foi criada à mão e de quando é o
    chamado, e o `historico` da nota (`ler_nota`) vem depois dela, do mais novo ao mais antigo, com as datas dele."""
    if c.get("retroativa"):
        chegada = {"d": c["criada"][:5], "a": c["criada"][6:10],
                   "texto": "Criada à mão no Fracttal em %s: o chamado é de %s, e o histórico abaixo veio na nota."
                            % (c["criada"][:10], c["chegou"]),
                   "autor": "Fracttal · %s" % c["criada"], "ev": False, "quando": ""}
    else:
        chegada = {"d": (c["chegou"] or "")[:5], "a": (c["chegou"] or "")[6:10],
                   "texto": "Chegou: a OS %s nasceu sozinha no fechamento da inspeção %s." % (c["folio"],
                                                                                         c["inspecao"] or "—"),
                   "autor": "App de Campo · %s" % c["chegou"] if c["chegou"] else "App de Campo", "ev": False,
                   "quando": ""}
    antes = []
    if c.get("retroativa"):
        # do mais novo ao mais antigo pela data (a do ano escrito ou deduzido); a sem data fica no fim, na ordem da nota
        com_data = [h for h in historico or [] if _data_br(h.get("data"))]
        com_data.sort(key=lambda h: _data_br(h["data"]), reverse=True)
        antes = [{"d": h["data"][:5], "a": h["data"][6:10], "texto": h["texto"], "autor": "Histórico importado na nota",
                  "ev": False, "quando": ""}
                 for h in com_data + [h for h in historico or [] if not _data_br(h.get("data"))]]
    # ordena do mais velho ao mais novo e VIRA: no empate (duas anotações no mesmo segundo — o ticket e a finalização
    # automáticos podem cair assim), a gravada depois fica em cima. `sorted(..., reverse=True)` manteria o empate na
    # ordem de gravação, e a finalização apareceria ABAIXO do ticket (visto na foto da bancada, 27/09).
    ordem = sorted(obs or [], key=lambda r: str(r.get("quando") or ""))
    lista = [entrada(r) for r in reversed(ordem)] + [chegada] + antes
    for i, e in enumerate(lista):
        e["novo"] = i == 0 and len(lista) > 1
    return lista


def copiar_tudo(campos) -> str:
    return "\n".join("%s: %s" % (x["rotulo"], x["valor"]) for x in campos or [])
