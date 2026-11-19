"""Os contratos editáveis, com histórico (Comando > Contratos, 18/11/2026).

Levi, 18/11/2026: "Tire essas opções de subir arquivos. [...] Eu quero que essas informações sejam editáveis. Tá? E quem
pode editar? O gestor do contrato, tendo um histórico de quem editou. [...] Só gestores de contrato ou administradores
podem editar, e tudo com histórico. Nesse histórico deve ter quem mudou, o que mudou, quando mudou, o motivo porque mudou,
anexar alguma coisa [...] um e-mail, uma mensagem, algo." Escolhas dele no mesmo dia: o anexo é OBRIGATÓRIO (arquivo ou o
texto colado do e-mail ou da mensagem), o administrador liga o gestor de cada contrato a uma pessoa, e TUDO é editável.

**De onde parte.** A carga inicial é o que já foi importado e não muda mais (as importações saíram da tela): a planilha
de controle de obrigações (`contratos/controle_obrigacoes.json`, 16/11/2026) e as fichas lidas dos PDFs dos contratos
(`contratos/fichas_contratos.json`, 18/11/2026), na pasta de dados do servidor. Cada coisa que se edita é um ITEM com um
id fixo tirado da carga (o mesmo arquivo dá sempre o mesmo id):
- `cliente`: a linha do cliente na planilha (gestor, vigência, aviso prévio, reajuste, SLA, referência, observações);
- `contrato`: cada contrato lido do PDF (vigência, aviso, valor mensal, reajuste);
- `regra`: cada regra lida do contrato; `obrigacao`: cada linha do Calendário; `adicional`: cada serviço adicional;
- `parametros`: as metas e os prazos da aba Cadastros (só o administrador).

**O registro.** Livro `nexus_contratos_edicoes` · `fato_edicao_contrato` (registrado no catálogo antes da 1ª gravação,
regra 10; só acrescenta). Grão: 1 linha = 1 mudança de 1 item (incluir, alterar ou retirar), com quem, quando, o que
era, o que ficou, o motivo e a prova. O estado de agora = a carga inicial + as mudanças na ordem da gravação. Nada se
apaga: retirar esconde o item e a história fica. A API do banco tem LEITURA ABERTA (regra 8): o conteúdo (o que era, o que
ficou, o motivo, a prova, quem) vai só CIFRADO com a chave do cadastro (o Cofre); a pessoa liga pelo código do e-mail. Os
arquivos da prova ficam no disco do servidor (`contratos_edicoes/<edicao_id>/1.pdf`), com nome neutro, como as Demandas.

**Quem edita.** O administrador, e o gestor do contrato daquele cliente (a pessoa ligada a ele: escolhida pelo
administrador, ou, enquanto ninguém escolheu, a pessoa com setor cujo nome é igual ao da planilha, quando só UMA tem esse
nome; nunca se chuta). Trocar o gestor é só do administrador, e vai ao histórico como o resto.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from ..dados import livros
from ..dados.conexao import banco as _banco
from . import controle as K
from . import fichas as F

LIVRO, NOME_LIVRO = "nexus_contratos_edicoes", "Nexus · edições dos contratos"
ABA = "fato_edicao_contrato"
CAB = ("edicao_id", "registrado_em", "data_id", "contrato_chave", "item_tipo", "item_id", "evento", "pessoa_hmac",
       "dados_cifrados")
TIPOS_ITEM = ("cliente", "contrato", "regra", "obrigacao", "adicional", "parametros",
              # o retorno da Ana Barros (chamada de 18/11/2026): o comentário (pedido da Danuth), a recorrência do calendário
              # e o check de entregue, a sugestão descartada e o lançamento do financeiro mês a mês
              "comentario", "recorrencia", "entrega", "descarte", "lancamento")
# o que não muda o contrato não pede motivo nem prova, só quem e quando (Levi, 18/11/2026: "Não: só quem e quando")
LEVES = ("comentario", "entrega", "descarte")
FREQUENCIAS = ("semanal", "mensal", "trimestral", "semestral", "anual")
DIAS_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
TIPOS_LANCAMENTO = ("Acréscimo", "Penalidade", "Desconto", "Outro")
EVENTOS = ("inclusao", "alteracao", "retirada")
MOTIVO_MIN, MOTIVO_MAX, PROVA_MIN, PROVA_MAX, TEXTO_MAX = 5, 2000, 10, 20000, 4000
ID_EDICAO = re.compile(r"e[0-9a-f]{11}")
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()

# as listas da aba Cadastros da planilha de controle (R00, 28/09/2026): o que a área já usava
TIPOS_OBRIGACAO = ("Entregável ao cliente (RMO, relatório)", "Medição / faturamento (BM)", "Reajuste", "Vigência / renovação",
                   "Reunião periódica com cliente", "Notificação / prazo de resposta",
                   "Documentação (SSMA, seguro, garantia, licença)", "Onboarding de contrato novo (CTR-01)", "Aditivo", "Outro")
STATUS = ("A levantar", "Não iniciado", "Em andamento", "Entregue", "Cancelado / não se aplica")
EXECUTORES = ("Supervisor de Contratos", "Coordenador", "Head", "COS", "Performance", "PCM", "Manutenção", "Financeiro",
              "Engenharia", "HSEQ")
RESPOSTAS = ("Pendente", "Aprovado", "Aprovado parcial", "Reprovado", "Contestado")
SETORES = ("COS", "Performance", "PCM", "Supervisão de Campo", "Zeladoria", "Engenharia de O&M", "Contratos", "HSEQ",
           "Financeiro")

# o que se edita em cada item: (campo, rótulo, tipo, opções). O campo com ponto é o caminho dentro do item da carga
# (o contrato lido guarda a vigência em "vigencia.fim"). "so_admin" = só o administrador muda.
CAMPOS: dict[str, tuple] = {
    "cliente": (("gestor_hmac", "Gestor do contrato", "pessoa", "so_admin"),
                ("referencia", "Contrato (nº ou referência)", "texto", None),
                ("inicio", "Início da vigência", "data", None), ("fim", "Fim da vigência", "data", None),
                ("aviso_dias", "Aviso prévio de renovação (dias)", "inteiro", None),
                ("indice", "Índice de reajuste", "texto", None), ("data_base", "Data-base do reajuste", "data", None),
                ("sla", "SLA de atendimento (resumo)", "longo", None), ("observacoes", "Observações", "longo", None)),
    "contrato": (("vigencia.inicio", "Início da vigência", "data", None), ("vigencia.fim", "Fim da vigência", "data", None),
                 ("renovacao.aviso_previo_dias", "Aviso prévio de renovação (dias)", "inteiro", None),
                 ("valor.mensal", "Valor mensal (R$)", "numero", None),
                 ("reajuste.indice", "Índice de reajuste", "texto", None),
                 ("reajuste.data_base", "Data-base do reajuste", "data", None)),
    "regra": (("categoria", "Categoria", "lista", F.CATEGORIAS), ("nome", "Regra", "texto", None),
              ("vigente", "Vale hoje", "longo", None), ("setor", "Setor que executa", "lista", ("",) + SETORES),
              ("prazo", "Prazo", "texto", None), ("periodicidade", "Periodicidade", "texto", None),
              ("contrato_id", "Contrato", "contrato", None),
              # a regra prioritária fica no alto das Regras (Ana Barros, 18/11/2026: "uma seleção de prioritárias [...] o
              # próprio supervisor [...] vai setando as mais prioritárias de acompanhamento")
              ("prioritaria", "Prioritária", "booleano", "oculto")),
    "obrigacao": (("tipo", "Tipo", "lista", TIPOS_OBRIGACAO), ("descricao", "Obrigação", "longo", None),
                  ("clausula", "Cláusula / origem", "texto", None), ("periodicidade", "Periodicidade", "texto", None),
                  ("vencimento", "Vencimento", "data", None), ("alerta_dias", "Avisar com antecedência (dias)", "inteiro", None),
                  ("executor", "Executor", "lista", ("",) + EXECUTORES), ("status", "Status", "lista", STATUS),
                  ("entrega", "Data de entrega", "data", None), ("observacoes", "Observações", "longo", None)),
    "adicional": (("usina", "Usina", "texto", None), ("servico", "Serviço executado", "longo", None),
                  ("os", "Nº da OS no Fracttal", "texto", None), ("execucao", "Data de execução", "data", None),
                  ("pedido", "Pedido / aviso do cliente", "texto", None), ("base", "Base contratual", "texto", None),
                  ("valor_estimado", "Valor estimado (R$)", "numero", None), ("memoria", "Memória enviada em", "data", None),
                  ("resposta", "Resposta do cliente", "lista", ("",) + RESPOSTAS),
                  ("valor_aprovado", "Valor aprovado (R$)", "numero", None), ("bm", "BM / competência", "texto", None),
                  ("nf", "Nº da NF", "texto", None), ("faturamento", "Data do faturamento", "data", None),
                  ("observacoes", "Observações", "longo", None)),
    "comentario": (("alvo_tipo", "Sobre", "lista", ("regra", "cliente", "contrato", "obrigacao", "adicional", "recorrencia")),
                   ("alvo_id", "Item", "texto", "oculto"), ("texto", "Comentário", "longo", None)),
    "recorrencia": (("nome", "Entrega ou rotina", "texto", None), ("tipo", "Tipo", "lista", TIPOS_OBRIGACAO),
                    ("frequencia", "Frequência", "lista", FREQUENCIAS),
                    ("dia_semana", "Dia da semana (semanal)", "lista", ("",) + DIAS_SEMANA),
                    ("dia_util", "Nº do dia útil do mês (ex.: 5 = 5º dia útil)", "inteiro", None),
                    ("dia_mes", "Ou o dia do mês", "inteiro", None),
                    ("mes_inicio", "Mês de partida (trimestral, semestral, anual: 1 a 12)", "inteiro", None),
                    ("setor", "Setor que entrega", "lista", ("",) + SETORES),
                    ("inicio", "Vale a partir de", "data", None), ("fim", "Vale até", "data", None),
                    ("origem_regra", "Regra do contrato", "texto", "oculto")),
    "entrega": (("recorrencia_id", "Recorrência", "texto", "oculto"), ("data", "Data", "data", None)),
    "descarte": (("sugestao_id", "Sugestão", "texto", "oculto"),),
    "lancamento": (("mes", "Mês (aaaa-mm)", "mes", None), ("tipo", "Tipo", "lista", TIPOS_LANCAMENTO),
                   ("valor", "Valor (R$)", "numero", None), ("descricao", "Descrição", "longo", None)),
    "parametros": (("meta_entregaveis", "Meta de entregáveis no prazo (0 a 1)", "numero", "so_admin"),
                   ("meta_vencidas", "Meta de obrigações vencidas em aberto", "numero", "so_admin"),
                   ("meta_adicionais", "Meta de adicionais faturados (0 a 1)", "numero", "so_admin"),
                   ("meta_cobertura", "Meta de cobertura de escopo (0 a 1)", "numero", "so_admin"),
                   ("alerta_padrao", "Antecedência padrão do alerta (dias)", "numero", "so_admin"),
                   ("prazo_memoria", "Prazo da memória de cobrança (dias)", "numero", "so_admin")),
}
# o que é obrigatório ao incluir
OBRIGATORIOS = {"regra": ("categoria", "nome", "vigente"), "obrigacao": ("tipo", "descricao", "status"),
                "comentario": ("alvo_id", "texto"), "recorrencia": ("nome", "frequencia"), "entrega": ("recorrencia_id", "data"),
                "descarte": ("sugestao_id",), "lancamento": ("mes", "tipo", "valor"),
                "adicional": ("servico",)}
ROTULO_ITEM = {"comentario": "Comentário", "recorrencia": "Recorrência do calendário", "entrega": "Entrega",
               "descarte": "Sugestão descartada", "lancamento": "Lançamento do financeiro",
               "cliente": "Dados do contrato", "contrato": "Contrato", "regra": "Regra", "obrigacao": "Obrigação",
               "adicional": "Serviço adicional", "parametros": "Metas e prazos"}


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


# ── ids fixos da carga ───────────────────────────────────────────────────────────────────────────────────────────────
def _h(*partes) -> str:
    return hashlib.sha1("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:11]


def id_cliente(cliente: str) -> str:
    return "c" + _h(K._chave(cliente))


def _sem(t) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", str(t or "")) if not unicodedata.combining(c))
    return " ".join(t.lower().split())


# ── a carga inicial ──────────────────────────────────────────────────────────────────────────────────────────────────
def carga(controle: dict | None, fichas_doc: dict | None) -> dict:
    """Os itens de partida (ver o docstring do módulo): {tipo: {id: item}} e o `info` da carga. O item guarda o
    cliente dele (`_cliente`) e, a regra, o contrato (`contrato_id`); a ordem da carga é a ordem de exibição."""
    st = {t: {} for t in TIPOS_ITEM}
    controle = controle or {}
    nomes = [c["cliente"] for c in controle.get("contratos") or []]
    for c in controle.get("contratos") or []:
        st["cliente"][id_cliente(c["cliente"])] = {**c, "_cliente": c["cliente"]}
    for i, o in enumerate(controle.get("obrigacoes") or []):
        st["obrigacao"]["o" + _h(K._chave(o["cliente"]), i, o.get("descricao"))] = {**o, "_cliente": o["cliente"]}
    for i, a in enumerate(controle.get("adicionais") or []):
        st["adicional"]["a" + _h(K._chave(a["cliente"]), i, a.get("servico"))] = {**a, "_cliente": a["cliente"]}
    st["parametros"]["p0"] = dict(controle.get("parametros") or {})
    fichas = F.por_cliente((fichas_doc or {}).get("fichas") or [], nomes)
    documentos = {}
    for cli, f in fichas.items():
        documentos[cli] = {"documentos": f.get("documentos") or [], "observacoes": f.get("observacoes") or []}
        if id_cliente(cli) not in st["cliente"]:      # ficha de cliente que a planilha não tem: o cliente nasce dela
            st["cliente"][id_cliente(cli)] = {"cliente": cli, "gestor": "", "recortes": [], "usinas": [], "_cliente": cli}
        for k in f.get("contratos") or []:
            kid = "k" + _h(K._chave(cli), k.get("id") or k.get("arquivo"))
            item = {kk: vv for kk, vv in k.items() if kk != "regras"}
            st["contrato"][kid] = {**item, "_cliente": cli}
            for i, r in enumerate(k.get("regras") or []):
                st["regra"]["r" + _h(K._chave(cli), k.get("id") or k.get("arquivo"), i, r.get("categoria"), r.get("nome"))] = \
                    {**r, "_cliente": cli, "contrato_id": kid}
    info = {"planilha": {k: controle.get(k) for k in ("arquivo", "importado_em", "importado_por")} if controle else None,
            "fichas": {k: (fichas_doc or {}).get(k) for k in ("arquivo", "importado_em", "importado_por", "por_cliente")} if fichas_doc else None,
            "documentos": documentos}
    return {"itens": st, "info": info}


def _pega(item: dict, campo: str):
    x = item
    for p in campo.split("."):
        if not isinstance(x, dict):
            return None
        x = x.get(p)
    return x


def _poe(item: dict, campo: str, valor) -> None:
    partes = campo.split(".")
    x = item
    for p in partes[:-1]:
        if not isinstance(x.get(p), dict):
            x[p] = {}
        x = x[p]
    x[partes[-1]] = valor


# ── o livro ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela nada vai cifrado, e nada "
                       "foi gravado")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _ctx(eid) -> str:
    return f"banco/contratos_edicoes/{eid}"


def ler_banco() -> list[dict]:
    """As linhas do livro como estão no banco. Livro que ainda não existe = vazio. Erro sobe."""
    return livros.ler(*_banco(), LIVRO, ABA)


def _quando(v):
    try:
        return datetime.fromisoformat(str(v or "").replace("Z", "+00:00")).astimezone(_BRT)
    except ValueError:
        return None


def abrir(linhas: list[dict]) -> list[dict]:
    """As mudanças decifradas, na ordem da gravação (a hora e, no mesmo segundo, a posição no livro). A linha que não
    decifra (outra chave, adulterada) fica fora e conta em `nao_abriu` da primeira."""
    try:
        cofre = _cofre()
    except Recusada:
        cofre = None
    ordem = {id(l): i for i, l in enumerate(linhas)}
    out = []
    for l in sorted(linhas, key=lambda l: (_quando(l.get("registrado_em")) or datetime.min.replace(tzinfo=_BRT), ordem[id(l)])):
        if not cofre:
            break
        try:
            d = json.loads(cofre.decifrar(l.get("dados_cifrados") or "", _ctx(l.get("edicao_id"))))
        except Exception:           # noqa: BLE001 — cifra de outra chave ou adulterada: fora, e o log diz
            current_app.logger.warning("Contratos: a edição %s não decifrou", l.get("edicao_id"))
            continue
        q = _quando(l.get("registrado_em"))
        out.append({"edicao_id": str(l.get("edicao_id") or ""), "quando": q,
                    "quando_txt": q.strftime("%d/%m/%Y às %H:%M") if q else "—", "item_tipo": str(l.get("item_tipo") or ""),
                    "item_id": str(l.get("item_id") or ""), "evento": str(l.get("evento") or ""),
                    "hmac": str(l.get("pessoa_hmac") or ""), **d})
    return out


def aplicar(base: dict, mudancas: list[dict]) -> dict:
    """O estado de agora: a carga + as mudanças, na ordem. {tipo: {id: item}} com `_retirado` e `_editado` ({campo: quem
    e quando, da última mudança}) em cada item mexido. Mudança de item que não existe (de uma carga que não é esta) é
    pulada."""
    st = json.loads(json.dumps(base["itens"], default=str))
    for m in mudancas:
        tipo, iid = m["item_tipo"], m["item_id"]
        if tipo not in st:
            continue
        marca = {"quem": m.get("quem", {}).get("nome") or "", "quando": m["quando_txt"], "edicao_id": m["edicao_id"]}
        if m["evento"] == "inclusao":
            item = {"_cliente": m.get("cliente") or "", "_incluido": marca, "_autor": m.get("hmac") or ""}
            for campo, v in (m.get("depois") or {}).items():
                _poe(item, campo, v)
            st[tipo][iid] = item
        elif iid in st[tipo]:
            item = st[tipo][iid]
            if m["evento"] == "retirada":
                item["_retirado"] = marca
            else:
                for campo, v in (m.get("depois") or {}).items():
                    _poe(item, campo, v)
                    item.setdefault("_editado", {})[campo] = marca
    return st


# ── quem é o gestor e quem edita ─────────────────────────────────────────────────────────────────────────────────────
def gestor_de(cliente_item: dict, pessoas: list[dict]) -> dict:
    """{hmac, nome, como}: a pessoa escolhida pelo administrador (`gestor_hmac`), ou a ÚNICA pessoa com setor cujo nome é
    igual ao do gestor da planilha ("pelo nome"), ou ninguém. Nunca se chuta: dois com o mesmo nome = ninguém."""
    escolhido = str(cliente_item.get("gestor_hmac") or "")
    por_hmac = {p["hmac"]: p for p in pessoas}
    if escolhido:
        p = por_hmac.get(escolhido)
        return {"hmac": escolhido, "nome": (p or {}).get("nome") or cliente_item.get("gestor_nome") or "", "como": "escolhido"}
    nome = _sem(cliente_item.get("gestor"))
    iguais = [p for p in pessoas if nome and _sem(p.get("nome")) == nome]
    if len(iguais) == 1:
        return {"hmac": iguais[0]["hmac"], "nome": iguais[0]["nome"], "como": "pelo nome"}
    return {"hmac": "", "nome": cliente_item.get("gestor") or "", "como": "sem ligação"}


def pode_editar(cliente_item: dict, pessoas: list[dict], meu_hmac: str | None, admin: bool) -> bool:
    if admin:
        return True
    g = gestor_de(cliente_item, pessoas)
    return bool(meu_hmac and g["hmac"] and g["hmac"] == meu_hmac)


# ── o estado para a tela ─────────────────────────────────────────────────────────────────────────────────────────────
def visao(base: dict, st: dict, hoje: date, pessoas: list[dict], meu_hmac: str | None, admin: bool) -> dict:
    """O que o dados.json entrega, no formato que a página lê (o mesmo da planilha e das fichas), com o estado de agora:
    as contas (`controle.com_datas`) depois de o contrato completar o vazio da planilha (`fichas.completar`)."""
    vivos = {t: {i: x for i, x in st[t].items() if not x.get("_retirado")} for t in st}
    clientes = []
    for cid, c in vivos["cliente"].items():
        g = gestor_de(c, pessoas)
        clientes.append({**{k: v for k, v in c.items() if not k.startswith("_")}, "cliente": c["_cliente"],
                         "gestor": g["nome"] or c.get("gestor") or "", "gestor_como": g["como"], "id": cid,
                         "pode_editar": pode_editar(c, pessoas, meu_hmac, admin), "_editado": c.get("_editado") or {},
                         "recortes": c.get("recortes") or [], "usinas": c.get("usinas") or []})
    # as fichas, remontadas com os contratos e as regras de agora
    fichas = {}
    for kid, k in vivos["contrato"].items():
        f = fichas.setdefault(k["_cliente"], {"cliente": k["_cliente"], "contratos": [], **(base["info"]["documentos"].get(k["_cliente"]) or {"documentos": [], "observacoes": []})})
        f["contratos"].append({**{a: b for a, b in k.items() if a != "_cliente"}, "_id": kid, "regras": []})
    por_k = {k["_id"]: k for f in fichas.values() for k in f["contratos"]}
    for rid, r in vivos["regra"].items():
        k = por_k.get(r.get("contrato_id"))
        if not k:                    # regra incluída sem contrato lido: o cliente ganha um "contrato" de regras próprias
            f = fichas.setdefault(r["_cliente"], {"cliente": r["_cliente"], "contratos": [], "documentos": [], "observacoes": []})
            k = next((x for x in f["contratos"] if x["_id"] == "geral"), None)
            if not k:
                k = {"_id": "geral", "id": "Regras incluídas no Nexus", "regras": []}
                f["contratos"].append(k)
                por_k["geral|" + r["_cliente"]] = k
        k["regras"].append({**{a: b for a, b in r.items() if a != "_cliente"}, "_id": rid})
    nomes = [c["cliente"] for c in clientes]
    fichas = {c: f for c, f in fichas.items() if c in nomes}
    obrig = [{**{a: b for a, b in o.items() if a != "_cliente"}, "cliente": o["_cliente"], "_id": i} for i, o in vivos["obrigacao"].items()]
    adic = [{**{a: b for a, b in a.items() if a != "_cliente"}, "cliente": a["_cliente"], "_id": i} for i, a in vivos["adicional"].items()]
    par = vivos["parametros"].get("p0") or {}
    dados = {"contratos": F.completar(clientes, fichas) if fichas else clientes, "obrigacoes": obrig, "adicionais": adic,
             "parametros": {k: v for k, v in par.items() if not k.startswith("_")},
             "abas": ["Carteira", "Calendario", "Usinas", "Adicionais", "Cadastros"]}
    out = K.com_datas(dados, hoje)
    out["obrigacoes"].sort(key=lambda o: (o.get("vencimento") or "9999", K._chave(o["cliente"])))
    out["adicionais"].sort(key=lambda a: (a.get("execucao") or "0000", K._chave(a["cliente"])), reverse=True)
    out["fichas"] = fichas
    out["parametros_editado"] = par.get("_editado") or {}
    out["admin"] = admin

    def lista(tipo):
        return [{**{a: b for a, b in x.items() if not a.startswith("_")}, "_id": i, "cliente": x.get("_cliente") or "",
                 "_quem": (x.get("_incluido") or {}).get("quem") or "", "_quando": (x.get("_incluido") or {}).get("quando") or "",
                 "_meu": bool(meu_hmac and x.get("_autor") == meu_hmac), "_editado": x.get("_editado") or {}}
                for i, x in vivos.get(tipo, {}).items()]
    out["comentarios"] = lista("comentario")
    out["recorrencias"] = lista("recorrencia")
    out["entregas"] = lista("entrega")
    out["descartes"] = [x.get("sugestao_id") for x in vivos.get("descarte", {}).values()]
    out["lancamentos"] = lista("lancamento")
    return out


# ── as provas (a regra das Demandas e das Sugestões, com o e-mail) ───────────────────────────────────────────────────
MB = 1024 * 1024
MAX_MB_ARQUIVO, MAX_ARQUIVOS, MAX_MB_TOTAL = 10, 5, 25
TIPOS_PROVA = {".pdf": "pdf", ".png": "imagem", ".jpg": "imagem", ".jpeg": "imagem", ".webp": "imagem", ".txt": "texto",
               ".eml": "texto", ".msg": "ole", ".doc": "ole", ".docx": "zip", ".xlsx": "zip"}
SERVIDO = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
           ".txt": "text/plain; charset=utf-8", ".eml": "message/rfc822", ".msg": "application/vnd.ms-outlook",
           ".doc": "application/msword",
           ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
           ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _bate(jeito: str, dados: bytes) -> bool:
    if jeito == "pdf":
        return b"%PDF-" in dados[:1024]
    if jeito == "imagem":
        return dados.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")) or (dados[:4] == b"RIFF" and dados[8:12] == b"WEBP")
    if jeito == "zip":
        return dados.startswith(b"PK\x03\x04")
    if jeito == "ole":
        return dados.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    return b"\x00" not in dados[:4096]


def provas(arquivos) -> list[dict]:
    """Os arquivos do formulário ([(nome, stream)]) -> [{nome, ext, dados}], ou Recusada com o motivo."""
    from ..casca.sugestoes import nome_seguro
    escolhidos = [(n, s) for n, s in (arquivos or []) if str(n or "").strip()]
    if len(escolhidos) > MAX_ARQUIVOS:
        raise Recusada(f"São {len(escolhidos)} anexos: o limite é {MAX_ARQUIVOS} por mudança")
    out, total = [], 0
    for nome_in, stream in escolhidos:
        nome = nome_seguro(nome_in)
        ext = os.path.splitext(nome)[1].lower()
        if ext not in TIPOS_PROVA:
            raise Recusada(f"“{nome or nome_in}”: tipo não aceito. Aceitos: {', '.join(sorted(TIPOS_PROVA))}")
        dados = stream.read(MAX_MB_ARQUIVO * MB + 1)
        if not dados:
            raise Recusada(f"“{nome}” veio vazio")
        if len(dados) > MAX_MB_ARQUIVO * MB:
            raise Recusada(f"“{nome}” passa de {MAX_MB_ARQUIVO} MB, o limite por arquivo")
        if not _bate(TIPOS_PROVA[ext], dados):
            raise Recusada(f"“{nome}” não é {ext} de verdade: o conteúdo não bate com a extensão")
        total += len(dados)
        if total > MAX_MB_TOTAL * MB:
            raise Recusada(f"Os anexos passam de {MAX_MB_TOTAL} MB juntos")
        out.append({"nome": nome, "ext": ext, "dados": dados})
    return out


def _pasta(eid: str):
    from ..cadastro.ligacoes import pasta_dados
    if not ID_EDICAO.fullmatch(eid):
        raise Recusada("Edição inválida")
    return pasta_dados(current_app.config) / "contratos_edicoes" / eid


def arquivo(eid: str, n, mudancas: list[dict]):
    """(caminho, registro) do anexo `n` da edição, ou None."""
    m = next((x for x in mudancas if x["edicao_id"] == eid), None)
    a = next((a for a in (m or {}).get("anexos") or [] if str(a.get("n")) == str(n)), None)
    if not a:
        return None
    caminho = _pasta(str(a.get("pasta") or eid)) / str(a.get("arquivo") or "")
    return (caminho, a) if caminho.is_file() else None


# ── conferir e gravar uma mudança ────────────────────────────────────────────────────────────────────────────────────
def _valor(tipo: str, opcoes, v, rotulo: str, contratos_do_cliente=()):
    t = "\n".join(" ".join(l.split()) for l in str(v if v is not None else "").replace("\r\n", "\n").split("\n")).strip()
    if tipo in ("texto", "longo"):
        if len(t) > (TEXTO_MAX if tipo == "longo" else 300):
            raise Recusada(f"{rotulo}: texto longo demais")
        return t
    if not t:
        return None
    if tipo == "data":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
            raise Recusada(f"{rotulo}: escreva a data como dd/mm/aaaa")
        try:
            date.fromisoformat(t)
        except ValueError:
            raise Recusada(f"{rotulo}: data inválida") from None
        return t
    if tipo in ("inteiro", "numero"):
        try:
            n = float(t.replace(".", "").replace(",", ".")) if "," in t else float(t)
        except ValueError:
            raise Recusada(f"{rotulo}: escreva um número") from None
        if n < 0:
            raise Recusada(f"{rotulo}: o número não pode ser negativo")
        return int(round(n)) if tipo == "inteiro" else round(n, 4)
    if tipo == "lista":
        if t not in opcoes:
            raise Recusada(f"{rotulo}: escolha uma das opções")
        return t
    if tipo == "contrato":
        if t not in contratos_do_cliente:
            raise Recusada(f"{rotulo}: escolha um dos contratos do cliente")
        return t
    if tipo == "pessoa":
        return t.lower()
    if tipo == "booleano":
        if t.lower() in ("1", "sim", "true", "s"):
            return True
        if t.lower() in ("0", "nao", "não", "false", "n"):
            return False
        raise Recusada(f"{rotulo}: sim ou não")
    if tipo == "mes":
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", t):
            raise Recusada(f"{rotulo}: escreva o mês como aaaa-mm")
        return t
    return t


def gravar(base: dict, item_tipo: str, item_ids, evento: str, cliente: str, valores: dict, motivo: str,
           prova_texto: str, arquivos, usuario: dict, admin: bool, pessoas: list[dict]) -> dict:
    """Confere e grava UMA mudança (ver o docstring do módulo), num ou em vários itens do mesmo cliente de uma vez (a regra
    igual nos seis contratos da 2C muda nos seis: uma linha por item, com o mesmo motivo e a mesma prova, guardada uma
    vez). Recusa sem gravar nada: sem login de pessoa, sem poder editar esse cliente, campo que não existe ou de
    administrador, nada mudou, sem motivo, sem prova. Volta as mudanças."""
    if isinstance(item_ids, str):
        item_ids = [item_ids]
    item_ids = [str(i) for i in item_ids or [] if str(i)] or [""]
    if len(item_ids) > 50:
        raise Recusada("Itens demais numa mudança só")
    from ..cadastro.ligacao_campo import codigo_da_pessoa
    cfg = current_app.config
    if item_tipo not in TIPOS_ITEM or evento not in EVENTOS:
        raise Recusada("Mudança inválida")
    email = str((usuario or {}).get("email") or "").strip().lower()
    nome = " ".join(str((usuario or {}).get("nome") or "").split()) or email
    if not email:
        raise Recusada("Entre com o seu login (Microsoft ou Fracttal) para editar: o histórico precisa dizer quem mudou")
    cod = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not cod or not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem as chaves de gravação (NEXUS_PESSOA_HMAC e GRIDCO_SQL_TOKEN)")
    motivo = str(motivo or "").strip()
    prova_texto = str(prova_texto or "").replace("\r\n", "\n").strip()
    if len(motivo) > MOTIVO_MAX:
        raise Recusada(f"O motivo passou de {MOTIVO_MAX} caracteres")
    if len(prova_texto) > PROVA_MAX:
        raise Recusada(f"O texto colado passou de {PROVA_MAX} caracteres: anexe o arquivo")
    lista = provas(arquivos)
    # leve: não muda o contrato (o comentário, o check de entregue, a sugestão descartada, a regra marcada prioritária)
    leve = item_tipo in LEVES or (item_tipo == "regra" and evento == "alteracao" and set(valores or {}) <= {"prioritaria"})
    with _TRAVA:
        linhas = ler_banco()
        st = aplicar(base, abrir(linhas))
        # a recorrência confirmada a partir de uma regra do contrato: a prova é o trecho da regra, e o motivo diz isso
        origem = st["regra"].get(str((valores or {}).get("origem_regra") or "")) if item_tipo == "recorrencia" else None
        if origem and evento == "inclusao" and not lista and len(prova_texto) < PROVA_MIN:
            ref = origem.get("ref") or {}
            prova_texto = (f'Regra do contrato "{origem.get("nome") or ""}": "{origem.get("trecho") or origem.get("vigente") or ""}" '
                           f'({ref.get("arquivo") or ""}, p. {ref.get("pagina") or ""})')
            motivo = motivo or "Confirmada a partir da regra do contrato"
        if leve:
            motivo = motivo or {"comentario": "Comentário", "entrega": "Marcou a entrega", "descarte": "Descartou a sugestão",
                                "regra": "Mudou a prioridade"}.get(item_tipo, "")
        else:
            if len(motivo) < MOTIVO_MIN:
                raise Recusada("Escreva o motivo da mudança")
            if not lista and len(prova_texto) < PROVA_MIN:
                raise Recusada("Anexe a prova (o e-mail, a mensagem, o documento) ou cole o texto dela: sem prova, nada é gravado")
        planos = []                       # (item_id, cliente, atual, antes, depois) de cada item
        for item_id in item_ids:
            if item_tipo == "parametros":
                if not admin:
                    raise Recusada("As metas e os prazos são do administrador")
                item_id, cli = "p0", ""
                atual = st["parametros"].get("p0") or {}
            elif evento == "inclusao":
                if item_tipo not in OBRIGATORIOS:
                    raise Recusada("Esse item não se inclui pela tela")
                if len(item_ids) > 1:
                    raise Recusada("Inclua um item por vez")
                cli, atual = str(cliente or ""), {}
                item_id = item_tipo[0] + uuid.uuid4().hex[:11]
            else:
                atual = st[item_tipo].get(item_id)
                if not atual or atual.get("_retirado"):
                    raise Recusada("Esse item não existe mais: atualize a página")
                cli = atual.get("_cliente") or ""
            if item_tipo != "parametros":
                c = st["cliente"].get(id_cliente(cli))
                if not c or c.get("_retirado"):
                    raise Recusada("Cliente não encontrado: atualize a página")
                if item_tipo == "comentario":
                    if evento == "retirada" and not admin and atual.get("_autor") != cod:
                        raise Recusada("Só quem escreveu o comentário, ou um administrador, tira o comentário")
                    if evento == "alteracao":
                        raise Recusada("O comentário não se edita: escreva outro")
                elif not pode_editar(c, pessoas, cod, admin):
                    raise Recusada("Só o gestor deste contrato ou um administrador edita")
                if planos and cli != planos[0][1]:
                    raise Recusada("Uma mudança é de um cliente só")
            if evento == "retirada" and item_tipo in ("cliente", "parametros", "contrato"):
                raise Recusada("Isso não se retira: altere o campo")
            spec = {x[0]: x for x in CAMPOS[item_tipo]}
            kids = tuple(k for k, x in st["contrato"].items() if x.get("_cliente") == cli and not x.get("_retirado"))
            antes, depois = {}, {}
            if evento != "retirada":
                for campo, v in (valores or {}).items():
                    if campo not in spec:
                        raise Recusada(f"Campo desconhecido: {campo}")
                    _c, rotulo, tipo, extra = spec[campo]
                    if extra == "so_admin" and not admin:
                        raise Recusada(f"{rotulo}: só o administrador muda")
                    novo = _valor(tipo, extra if tipo == "lista" else None, v, rotulo, kids)
                    velho = _pega(atual, campo)
                    if (velho in (None, "") and novo in (None, "")) or velho == novo:
                        continue
                    if tipo == "pessoa" and novo and novo not in {p["hmac"] for p in pessoas}:
                        raise Recusada(f"{rotulo}: escolha uma pessoa da lista")
                    antes[campo], depois[campo] = velho, novo
                    if tipo == "pessoa":         # o histórico mostra o nome, não o código
                        depois["gestor_nome"] = next((p["nome"] for p in pessoas if p["hmac"] == novo), "")
                        antes["gestor_nome"] = gestor_de(atual, pessoas)["nome"]
                if evento == "inclusao":
                    faltam = [spec[x][1] for x in OBRIGATORIOS[item_tipo] if depois.get(x) in (None, "")]
                    if faltam:
                        raise Recusada("Preencha: " + ", ".join(faltam))
                if not depois:
                    if len(item_ids) > 1:
                        continue          # neste item já estava assim: os outros mudam
                    raise Recusada("Nada mudou: altere algum campo antes de salvar")
            planos.append((item_id, cli, atual, antes, depois))
        if not planos:
            raise Recusada("Nada mudou: altere algum campo antes de salvar")
        lote = "e" + uuid.uuid4().hex[:11]
        feitos = []
        if lista:
            pasta = _pasta(lote)
            pasta.mkdir(parents=True, exist_ok=True)
            for n, a in enumerate(lista, 1):
                destino = pasta / f"{n}{a['ext']}"
                tmp = destino.with_name(destino.name + ".parcial")
                tmp.write_bytes(a["dados"])
                tmp.replace(destino)
                feitos.append({"n": n, "nome": a["nome"], "arquivo": destino.name, "tamanho": len(a["dados"]), "pasta": lote})
        agora = datetime.now(timezone.utc)
        cofre = _cofre()
        novas = []
        for i, (item_id, cli, atual, antes, depois) in enumerate(planos):
            eid = lote if i == 0 else "e" + uuid.uuid4().hex[:11]
            conteudo = {"cliente": cli, "item_rotulo": _rotulo(item_tipo, atual if evento != "inclusao" else depois, st),
                        "antes": antes, "depois": depois, "motivo": motivo, "prova_texto": prova_texto, "anexos": feitos,
                        "lote": lote, "quem": {"nome": nome, "email": email}}
            novas.append({"edicao_id": eid, "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")),
                          "contrato_chave": id_cliente(cli) if cli else "", "item_tipo": item_tipo, "item_id": item_id,
                          "evento": evento, "pessoa_hmac": cod,
                          "dados_cifrados": cofre.cifrar(json.dumps(conteudo, ensure_ascii=False, default=str), _ctx(eid))})
        try:
            base_b, sessao = _banco()
            livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in linhas + novas])},
                            base=base_b, token=cfg["GRIDCO_SQL_TOKEN"], sessao=sessao)
        except Exception:
            if feitos:
                shutil.rmtree(_pasta(lote), ignore_errors=True)
            raise
    return {"edicao_id": lote, "item_ids": [p[0] for p in planos], "evento": evento, "mudou": len(planos)}


def _rotulo(tipo: str, item: dict, st: dict) -> str:
    """O nome curto do item, para o histórico."""
    if tipo == "regra":
        return f"{item.get('categoria') or ''}: {item.get('nome') or ''}".strip(": ")
    if tipo == "obrigacao":
        return str(item.get("descricao") or "")[:120]
    if tipo == "adicional":
        return str(item.get("servico") or "")[:120]
    if tipo == "contrato":
        return str(item.get("id") or item.get("arquivo") or "Contrato")
    if tipo == "comentario":
        return str(item.get("texto") or "")[:120]
    if tipo == "recorrencia":
        return str(item.get("nome") or "")[:120]
    if tipo == "entrega":
        rec = st.get("recorrencia", {}).get(str(item.get("recorrencia_id") or "")) or {}
        return f"{rec.get('nome') or 'Entrega'} de {_dbr(item.get('data'))}"
    if tipo == "lancamento":
        return f"{item.get('tipo') or ''} de {item.get('mes') or ''}: {str(item.get('descricao') or '')[:80]}"
    return ROTULO_ITEM.get(tipo, tipo)


def historico(base: dict, mudancas: list[dict], cliente: str) -> list[dict]:
    """As mudanças do cliente (a mais nova primeiro), cada uma com o que mudou campo a campo, e no fim a carga inicial."""
    rot = {t: {c[0]: c[1] for c in CAMPOS[t]} for t in CAMPOS}
    out, por_lote = [], {}
    for m in mudancas:
        if m.get("cliente") != cliente:
            continue
        lote = m.get("lote") or m["edicao_id"]
        if lote in por_lote:             # a mesma mudança em vários contratos (a regra igual nos seis): uma entrada
            por_lote[lote]["itens"].append(m.get("item_rotulo") or "")
            continue
        antes, depois = m.get("antes") or {}, m.get("depois") or {}
        campos = []
        for k, v in depois.items():
            if k == "gestor_nome":
                continue
            if k == "gestor_hmac":
                campos.append({"campo": rot["cliente"]["gestor_hmac"], "antes": antes.get("gestor_nome") or None,
                               "depois": depois.get("gestor_nome") or None})
            else:
                campos.append({"campo": rot.get(m["item_tipo"], {}).get(k, k), "antes": antes.get(k), "depois": v})
        e = {"edicao_id": lote, "quando": m["quando_txt"], "quem": (m.get("quem") or {}).get("nome") or "",
             "item_tipo": ROTULO_ITEM.get(m["item_tipo"], m["item_tipo"]), "item": m.get("item_rotulo") or "",
             "itens": [m.get("item_rotulo") or ""], "evento": m["evento"], "campos": campos, "motivo": m.get("motivo") or "",
             "prova_texto": m.get("prova_texto") or "",
             "anexos": [{"n": a.get("n"), "nome": a.get("nome")} for a in m.get("anexos") or []]}
        por_lote[lote] = e
        out.append(e)
    out.reverse()
    info = base.get("info") or {}
    pl, fx = info.get("planilha") or {}, info.get("fichas") or {}
    partes = []
    if pl:
        partes.append(f"planilha de controle de obrigações de Contratos ({pl.get('arquivo') or 'importada'}, em "
                      f"{_dbr(pl.get('importado_em'))})")
    if fx and cliente in (info.get("documentos") or {}):
        docs = (info["documentos"][cliente] or {}).get("documentos") or []
        quando = ((fx.get("por_cliente") or {}).get(cliente) or {}).get("importado_em") or fx.get("importado_em")
        partes.append(f"{len(docs)} PDF{'s' if len(docs) != 1 else ''} do contrato lidos em {_dbr(quando)}: " +
                      "; ".join(str(d.get("arquivo") or "") for d in docs))
    out.append({"edicao_id": "", "quando": _dbr(pl.get("importado_em") or fx.get("importado_em")), "quem": "Carga inicial",
                "item_tipo": "Carga inicial", "item": "", "evento": "carga", "campos": [],
                "motivo": "O ponto de partida: " + " e ".join(partes) if partes else "O ponto de partida", "prova_texto": "",
                "anexos": []})
    return out


def juntar_fichas(atual: dict | None, novas: list[dict], clientes: list[str], mudancas: list[dict], quando: str,
                  quem: str, arquivo: str) -> tuple[dict, list[str], list[str]]:
    """As fichas novas na carga (18/11/2026 à tarde: mais PDFs depois que a importação saiu da tela). Cliente sem ficha
    entra; cliente com ficha é TROCADO só se ninguém editou um contrato lido ou uma regra dele (a troca muda os ids, e a
    mudança ficaria apontando para nada); senão fica como está e volta em `recusados`. A data de cada cliente fica em
    `por_cliente`, para a história dizer quando os PDFs dele foram lidos. Volta (o documento novo, entraram, recusados)."""
    doc = dict(atual or {"fichas": []})
    por = {K._chave(f["cliente"]): f for f in doc.get("fichas") or []}
    nomes = {K._chave(c): c for c in clientes}
    editados = {K._chave(m.get("cliente")) for m in mudancas if m.get("item_tipo") in ("contrato", "regra")}
    entraram, recusados = [], []
    por_cliente = dict(doc.get("por_cliente") or {})
    for f in novas:
        ch = K._chave(f["cliente"])
        if ch in por and ch in editados:
            recusados.append(f["cliente"])
            continue
        por[ch] = f
        entraram.append(f["cliente"])
        por_cliente[nomes.get(ch, f["cliente"])] = {"importado_em": quando, "importado_por": quem, "arquivo": arquivo}
    doc.update(fichas=list(por.values()), por_cliente=por_cliente)
    return doc, entraram, recusados


def _dbr(iso) -> str:
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) >= 10 else "—"
