# os_creator/os_web/solic_eng_web.py
"""A Nova solicitação para a ENGENHARIA (Levi, 06/10/2026): "Em 'Nova Solicitação' aparecerá duas opções, PCM e
Engenharia. PCM realmente criará uma solicitação. Para engenharia terá uma tela nova, estilo Performance > Geração e ETM
> ETM ... porém liberada para todos os ativos".

O que a tela cria é uma OS (não uma solicitação), no molde da OS de análise (`api.create_os_analise`), com o título
'[Ativo] - Descrição'. Não usa plano: as telas da Performance dependem do plano do Fracttal, que só inversor, ETM e usina
têm — e aqui vale qualquer ativo. O resto, pedido por ele:
  - tipo de tarefa 'Administrativa' e SÓ a Classificação 1, 'Programada' (06/10: "o tipo de tarefa seria administrativa
    e class1 é programada!"); a 2 fica vazia — a tela vale para qualquer ativo, e 'Elétrica' não serve a uma cerca;
  - as etiquetas Remoto e ENGENHARIA, sempre, e só elas (06/10: "Etiqueta de remoto e engenharia fixas sempre! só essas
    etiquetas viu, sem performance"): nem PERFORMANCE nem "Dar prioridade" no urgente;
  - a data do EVENTO vem da tela, editável e com padrão agora, como na ETM (06/10: "tem que ter data do evento"); não
    pode estar no futuro;
  - data programada 7 dias depois da criação; "Urgente" (em vermelho) põe em 2 dias. NÃO se edita (Levi, 06/10:
    "data programada não deve ser possível editar!"): a tela só mostra, e o servidor calcula na hora de criar;
  - o responsável só entre os nomes da Engenharia — que vêm do .env (`OS_WEB_ENGENHARIA_RESPONSAVEIS`), nunca do
    código: o repositório é público, e nome de gente não vai para lá (é o mesmo caminho do responsável dos chamados);
  - o tipo de ativo dá para escrever, e a sigla do cadastro (NBRK) aparece com o nome (Nobreak).

Regras puras (sem Flask): o teste as roda sem rede, e a rota só monta a requisição e a resposta."""
from __future__ import annotations
import datetime as dt
import os
import re
import unicodedata

BRT = dt.timezone(dt.timedelta(hours=-3))
DIAS_PADRAO = 7
DIAS_URGENTE = 2
TIPO_TAREFA = "Administrativa"
CLASSIF_1 = "Programada"
ETIQUETAS = ("Remoto", "ENGENHARIA")         # os nomes como estão no catálogo do Fracttal (Levi, 06/10: "é Remoto")
ENV_RESPONSAVEIS = "OS_WEB_ENGENHARIA_RESPONSAVEIS"
SUB_DESCRICAO = "Atividade a ser realizada (de forma direta)"
ROTULO_PROBLEMA = "Descreva o problema"

# A sigla do cadastro (o campo `tipo` do catálogo) → o nome que aparece na tela. Tirado dos PRÓPRIOS ativos de cada tipo
# (06/10, catálogo de 16.289 ativos: "XXX-NBRK — Nobreak", "XXX-DINV — Disjuntor do Inversor"…). Sigla que não está aqui
# aparece como veio (NCU e RSU, dos trackers, não têm nome no cadastro). O VALOR filtrado continua sendo a sigla.
NOME_TIPO = {
    "ALB": "Albedômetro", "ALRM": "Central de Alarme", "ANM": "Anemômetro", "ARCD": "Ar Condicionado",
    "BRT": "Biruta", "CBCA": "Cabos CA", "CBCC": "Cabos CC", "CCOM": "Cabo de Comunicação", "CCPU": "Computador (CPU)",
    "CETH": "Cabo Ethernet", "CGAT": "Conversor Serial (Gateway)", "CHSC": "Chave Seccionadora",
    "CMBB": "Combiner Box", "CMRA": "Câmeras de Segurança", "CNM": "Conversor de Mídia", "CPF": "Captor Franklin",
    "CRC": "Cerca (Perímetro)", "CTRL": "Controladores", "CXDA": "Caixa d'Água", "CXDP": "Caixa de Passagem",
    "DINV": "Disjuntor do Inversor", "DJMT": "Disjuntor de Média Tensão", "DTRF": "Disjuntor do Transformador",
    "EFIX": "Estrutura Fixa", "FBOT": "Fibra Ótica", "FDL": "Fieldlogger", "FSEP": "Fossa Séptica",
    "GATE": "Gateway Ethernet", "HSAT": "Haste de Aterramento", "ILMN": "Iluminação", "MDFV": "Módulo Fotovoltaico",
    "MLAT": "Malha de Aterramento", "NBRK": "Nobreak", "NVR": "NVR (gravador das câmeras)",
    "PECN": "Ponto de Entrega", "PGINVR": "Preventiva Grupo de Inversores", "PLCS": "Placas de Sinalização",
    "PLV": "Pluviômetro", "PPCI": "Sistema de Combate a Incêndio", "PRN": "Piranômetro", "PRTE": "Portão de Entrada",
    "QGBT": "Quadro Geral de Baixa Tensão (QGBT)", "RELE": "Relé da Cabine", "SCMD": "Sala de Comando",
    "SDP": "Sensor de Pás", "SDRN": "Sistema de Drenagem", "SDT": "Sensor de Temperatura",
    "SPDA": "SPDA (Para-raios)", "SWTC": "Switch", "TMH": "Termohigrômetro", "TRAX": "Transformador Auxiliar",
}


def rotulo_tipo(tipo) -> str:
    t = str(tipo or "").strip()
    return NOME_TIPO.get(t, t) or "—"


def _sem_acento(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


# ── os ativos (todos os tipos) ───────────────────────────────────────────────────────────────────────
def ativos_da_usina(assets, usina: str, curto=None) -> list:
    """Todos os ativos da usina, de qualquer tipo — a diferença para a Performance, que só mostra os do plano.
    `curto(asset)` é o nome que vai entre colchetes no título (`api._asset_short_name`), para a prévia da tela ser a OS."""
    out = [{"id": a.get("id"), "code": a.get("code"), "label": a.get("label") or a.get("description") or a.get("code"),
            "tipo": a.get("tipo") or "", "tipo_nome": rotulo_tipo(a.get("tipo")),
            "curto": curto(a) if curto else (a.get("label") or a.get("code"))}
           for a in (assets or []) if isinstance(a, dict) and a.get("usina") == usina and a.get("id") is not None]
    out.sort(key=lambda a: (_sem_acento(a["tipo_nome"]), _sem_acento(a["label"])))
    return out


def tipos_de(ativos) -> list:
    """[(sigla, nome)] dos tipos presentes, em ordem pelo NOME que a pessoa lê."""
    vistos = {}
    for a in ativos or []:
        if a.get("tipo"):
            vistos[a["tipo"]] = rotulo_tipo(a["tipo"])
    return sorted(vistos.items(), key=lambda kv: _sem_acento(kv[1]))


# ── os responsáveis da Engenharia ─────────────────────────────────────────────────────────────────────
def nomes_configurados(valor: str | None = None) -> list:
    """Os nomes do .env, separados por ';' (ou vírgula). Sem a variável: lista vazia — e a tela diz isso."""
    bruto = os.environ.get(ENV_RESPONSAVEIS, "") if valor is None else valor
    return [n.strip() for n in re.split(r"[;,]", bruto or "") if n.strip()]


def _casa(nome_cfg: str, nome_pessoa: str) -> bool:
    """"Ana Teste" casa com "Ana Teste da Silva": o 1º nome igual e todos os pedaços do nome configurado no nome
    da pessoa, inteiros e sem acento — "Bruno" não casa com "Brunoso"."""
    cfg, pes = _sem_acento(nome_cfg).split(), _sem_acento(nome_pessoa).split()
    return bool(cfg) and bool(pes) and cfg[0] == pes[0] and all(p in pes for p in cfg)


def responsaveis(pessoas, nomes) -> tuple[list, list]:
    """(as pessoas do Fracttal que casam com os nomes configurados, os nomes que não acharam ninguém). Pessoa sem
    id_personnel fica de fora: sem ele a OS não ganha responsável (é o id_responsible)."""
    achadas, faltam, vistos = [], [], set()
    for n in nomes or []:
        hits = [p for p in (pessoas or []) if isinstance(p, dict) and p.get("id_personnel") and _casa(n, p.get("name"))]
        if not hits:
            faltam.append(n)
        for p in hits:
            if p["id_personnel"] not in vistos:
                vistos.add(p["id_personnel"])
                achadas.append({"id_personnel": p["id_personnel"], "code": p.get("code") or "", "name": p.get("name") or ""})
    achadas.sort(key=lambda p: _sem_acento(p["name"]))
    return achadas, faltam


# ── as etiquetas ───────────────────────────────────────────────────────────────────────────────────────
def _nome_etq(t) -> str:
    return " ".join(_sem_acento(t).split())


def etiquetas(catalogo) -> tuple[list, list]:
    """(ids das ETIQUETAS no catálogo do Fracttal, os nomes que faltam). Pelo nome EXATO, sem acento e sem caixa: a busca
    por trecho do `api.label_id_por_nome` tomaria a 'Religamento Remoto' pela 'Remoto'. Faltou uma: quem chama não cria
    nada — OS da Engenharia sem as duas etiquetas não sai."""
    por_nome = {}
    for e in catalogo or []:
        if isinstance(e, dict) and e.get("id"):
            por_nome.setdefault(_nome_etq(e.get("description")), e["id"])
    ids = [por_nome[_nome_etq(n)] for n in ETIQUETAS if _nome_etq(n) in por_nome]
    return ids, [n for n in ETIQUETAS if _nome_etq(n) not in por_nome]


def erro_etiquetas(faltam) -> str:
    um = len(faltam) == 1
    return "Não achei no Fracttal %s %s. Nenhuma OS foi criada." % ("a etiqueta" if um else "as etiquetas", ", ".join(faltam))


# ── a data programada ──────────────────────────────────────────────────────────────────────────────────
def data_padrao(agora: dt.datetime, urgente: bool) -> dt.datetime:
    """A ÚNICA data programada possível: a hora da criação + 7 dias (Urgente: + 2). Não há data vinda da tela."""
    return agora + dt.timedelta(days=DIAS_URGENTE if urgente else DIAS_PADRAO)


def data_br(d: dt.datetime) -> str:
    return d.strftime("%d/%m/%Y %H:%M")


# ── o pedido ───────────────────────────────────────────────────────────────────────────────────────────
def montar(corpo: dict, assets_por_id: dict, permitidos: list, agora: dt.datetime, nome_os) -> tuple[list, dict, str]:
    """Do JSON da tela → (ativos do catálogo, campos da criação, erro). `nome_os(asset, base)` é o `api.perf_os_nome`
    ('[Ativo] - base'), passado de fora para a regra não depender do api."""
    corpo = corpo or {}
    ids = [i for i in (corpo.get("ativos") or []) if i is not None]
    assets = [assets_por_id.get(str(i)) for i in ids]
    if not ids:
        return [], {}, "Marque ao menos um ativo."
    if any(a is None for a in assets):
        return [], {}, "Um dos ativos marcados não está no catálogo — recarregue a página."
    descricao = " ".join(str(corpo.get("descricao") or "").split())
    if not descricao:
        return [], {}, "Escreva a atividade a ser realizada (o nome da OS)."
    problema = str(corpo.get("problema") or "").strip()
    if not problema:
        return [], {}, "Descreva o problema."
    resp = corpo.get("responsavel") or {}
    pid = resp.get("id_personnel") if isinstance(resp, dict) else None
    pessoa = next((p for p in permitidos or [] if str(p.get("id_personnel")) == str(pid)), None)
    if not pessoa:
        return [], {}, "Escolha o responsável entre os nomes da Engenharia."
    try:
        evento = dt.datetime.fromisoformat(str(corpo["evento"])).replace(tzinfo=BRT) if corpo.get("evento") else agora
    except ValueError:
        return [], {}, "Data do evento inválida."
    if evento > agora + dt.timedelta(minutes=5):           # o evento já aconteceu: no futuro é dado errado
        return [], {}, "A data do evento não pode estar no futuro."
    urgente = bool(corpo.get("urgente"))
    prog = data_padrao(agora, urgente)          # uma "programada" no pedido é ignorada: a data não se edita
    por_ativo = {a.get("code"): {"description": nome_os(a, descricao)} for a in assets}
    campos = {"descricao": descricao, "note": problema, "urgente": urgente, "event_date": evento, "prog_date": prog,
              "id_responsible": pessoa["id_personnel"], "responsible_code": pessoa.get("code") or "",
              "responsible_name": pessoa.get("name") or "", "por_ativo": por_ativo}
    return assets, campos, ""


def mensagem(res, assets, prog: dt.datetime | None = None) -> dict:
    """[{code, ok, os:{wo_folio}} | {code, ok:False, erro}] do `create_work_orders_bulk` → {ok, falhas, mensagem, folios}.
    Com `prog`, a mensagem diz a data que o servidor pôs — a tela não a escolhe, então quem criou precisa vê-la."""
    nome = {a.get("code"): (a.get("label") or a.get("code")) for a in assets or []}
    res = res or []
    ok = [r for r in res if r.get("ok")]
    fail = [r for r in res if not r.get("ok")]
    folios = [(r.get("os") or {}).get("wo_folio") for r in ok]
    if not ok:
        msg = "Nenhuma OS criada.\n" + "\n".join("• %s: %s" % (nome.get(r.get("code"), r.get("code")), r.get("erro")) for r in fail[:8])
    else:
        msg = "%d OS criada(s) para a Engenharia — Nº %s" % (len(ok), ", ".join(str(f or "?") for f in folios[:12]))
        msg += (" — programada(s) para %s." % data_br(prog)) if prog else "."
        if fail:
            msg += "\n\n%d falharam:\n" % len(fail) + "\n".join(
                "• %s: %s" % (nome.get(r.get("code"), r.get("code")), r.get("erro")) for r in fail[:6])
    avisos = [str((r.get("os") or {}).get("aviso")) for r in ok if (r.get("os") or {}).get("aviso")]
    return {"ok": len(ok), "falhas": len(fail), "mensagem": msg, "folios": folios, "avisos": avisos}
