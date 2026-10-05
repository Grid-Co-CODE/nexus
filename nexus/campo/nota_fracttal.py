"""A nota do fechamento da tarefa calculada com o que o Fracttal guarda (Levi, 04/10/2026: "tá óbvio que vem do
Fracttal com métricas bem estabelecidas, é só copiar a regra e fazer um código para o GitHub").

As réguas são as do App, copiadas sem mudar linha em regras_app.py, e são DUAS:
- a do PAINEL, `_qualidade_os` (subtarefas obrigatórias 25, fotos 20 com 3 dando o total, descrição 10, assinatura 10,
  observações 15, GPS no fechamento 20). É ela que o App grava no registro (`qualidade`) e que a Aprovação de OS, as
  Ordens de serviço e a Triagem mostram;
- a do PLACAR, `_qualidade_v2` (régua de 01/09/2026), que dá os pontos do ranking.
(Na 1ª prova, de 04/10, a nota mostrada ao Levi foi a do placar: corrigido no mesmo dia.)

Este módulo só TRADUZ: o App calcula com o fechamento que o celular manda, e quase tudo dele o App também grava no
Fracttal (medido em 04/10 no código do App v225 e na leitura do Fracttal):
- respostas do checklist -> work_orders_subtasks (valor, is_required, tipo); o "Não se aplica" vai escrito no valor;
- fotos -> work_orders_attachments, com a descrição "desc · GPS lat,lon · hora" (subir_fotos do App). A foto de
  subtarefa também sobe como anexo da tarefa, com a descrição começando pelo nome do campo;
- a observação escrita no checklist -> a própria subtarefa de texto;
- assinatura: a leitura do Fracttal não a devolve, mas o App não deixa concluir sem ela (campo.html, travasSheet:
  "Assinar no fim da folha"). Todo fechamento pelo App tem assinatura, então ela entra como dada.

O que a leitura do Fracttal NÃO tem, e por isso a nota daqui pode ficar ABAIXO da do App:
- a caixa "Registre observações" do App não vai ao Fracttal (o App guarda só no registro dele, `obs_app`): até 15
  pontos no painel quando o técnico escreveu só ali;
- o GPS do fechamento não vai: vale o GPS das fotos, que vai dentro da descrição de cada uma (20 pontos no painel);
- campo que já veio respondido do Fracttal e o técnico não tocou (`intocados` no App) conta como respondido.
Foto pedida: o App também não a enxerga. O fechamento manda o checklist sem `anexo`/`anexoApp` (campo.html,
formItemsParaChecklist), então `_v2_pede_foto` dá falso lá também: as duas notas tratam a foto do mesmo jeito.
"""
import re
import urllib.parse

from . import fracttal, regras_app

# campo.html, formItemsParaChecklist: o tipo do campo no Fracttal -> o tipo do item no App
TIPO_DO_FRACTTAL = {1: "texto", 2: "check", 3: "num", 4: "verif", 5: "num", 6: "texto", 7: "dropdown", 8: "date",
                    9: "check"}
NAO_SE_APLICA = "não se aplica"
MARCA_FOTO_NA = " · foto: não se aplica"     # o App acrescenta ao valor quando a foto do campo não se aplica
ASSINATURA_DO_APP = "data:image/png;base64,"  # só o começo: a régua do App olha se é imagem, não o desenho
FORA = ("observação escrita na caixa do App (até 15 pontos no painel)",
        "GPS do fechamento (vale o GPS das fotos)")
PAGINA = 100
_GPS = re.compile(r"^GPS\s+(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$")
_HORA = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_INTEIRO = re.compile(r"^[+-]?\d+")


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def valor_do_app(valor, tipo):
    """O valor cru do Fracttal no formato do item do App (espelha o _valorFracttal do campo.html)."""
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None
    if tipo == "check":
        return s.lower() == "true" or s == "1"
    if tipo == "verif":
        m = _INTEIRO.match(s)               # parseInt do JavaScript: lê o número do começo
        n = int(m.group()) if m else None
        return n if n is not None and 1 <= n <= 3 else None
    return s


def separar_nao_se_aplica(valor):
    """(valor sem a marca, se o campo foi marcado "não se aplica")."""
    if valor is None:
        return None, False
    s = str(valor)
    if s.strip().casefold() == NAO_SE_APLICA:
        return None, True
    if s.casefold().endswith(MARCA_FOTO_NA):
        return s[:-len(MARCA_FOTO_NA)], True
    return s, False


def descricao_da_foto(texto):
    """(o que o técnico escreveu, (lat, lon) ou None) da descrição que o App grava no anexo."""
    desc, gps = [], None
    for parte in str(texto or "").split(" · "):
        parte = parte.strip()
        m = _GPS.match(parte)
        if m:
            gps = gps or (float(m.group(1)), float(m.group(2)))
        elif parte and not _HORA.match(parte):
            desc.append(parte)
    return " · ".join(desc), gps


def _da_tarefa(linhas, tarefa):
    return [x for x in linhas if tarefa is None or str(x.get("id_work_order_task")) == str(tarefa)]


def evento(subtarefas, anexos, tarefa=None) -> dict:
    """O fechamento no formato que o App manda ao servidor (o `ev` das duas réguas)."""
    checklist, items, na = [], {}, []
    for s in sorted(_da_tarefa(subtarefas, tarefa), key=lambda x: _int(x.get("order_number")) or 0):
        fid = s.get("id_work_orders_tasks_form_items")
        ftype = _int(s.get("id_task_form_item_type"))
        tipo = TIPO_DO_FRACTTAL.get(ftype, "texto")
        bruto, e_na = separar_nao_se_aplica(s.get("value"))
        iid = f"f{fid}"
        checklist.append({"id": iid, "fid": fid, "tipo": tipo, "ftype": ftype, "desc": s.get("description") or "",
                          "req": bool(s.get("is_required"))})
        items[iid] = valor_do_app(bruto, tipo)
        if e_na:
            na.append(str(fid))
    # a foto de campo é a que começa pelo nome de uma subtarefa da mesma tarefa (o App monta assim); o nome mais
    # longo vence, para "Item 10" não ser lido como "Item 1"
    nomes = sorted({regras_app._norm(c["desc"]) for c in checklist if c["desc"]}, key=len, reverse=True)
    fotos, geo = [], {}
    for a in _da_tarefa(anexos, tarefa):
        desc, gps = descricao_da_foto(a.get("description"))
        if gps and not geo:
            geo = {"lat": gps[0], "lon": gps[1]}
        d = regras_app._norm(desc)
        fotos.append({"desc": desc, "campo": next((n for n in nomes if d.startswith(n)), None)})
    return {"tipo": "fechamento", "geo": geo,
            "dados": {"checklist": checklist, "items": items, "naoAplica": na, "intocados": [], "fotos": fotos,
                      "obs": "", "assinatura": ASSINATURA_DO_APP}}


def nota(subtarefas, anexos, tarefa=None) -> dict:
    """As duas notas do App para um fechamento feito pelo App, com o que o Fracttal mostra."""
    ev = evento(subtarefas, anexos, tarefa)
    painel = regras_app._qualidade_os(ev)
    placar = regras_app._qualidade_v2(ev)
    return {"q": painel["q"], "itens": painel["itens"], "n_fotos": painel["n_fotos"], "n_desc": painel["n_desc"],
            "obs_ok": painel["obs_ok"], "geo_ok": painel["geo_fim"], "sub_ok": painel["sub_ok"],
            "todas": painel["todas"], "gps_de": "fotos", "fora": list(FORA),
            "placar": {"q": placar["q"], "pontos": placar["pontos"], "itens": placar["itens"]}}


def _paginas(path, ler=None) -> list:
    ler = ler or fracttal.ler
    out, ini = [], 0
    while True:
        r = ler(f"{path}&limit={PAGINA}&start={ini}")
        linhas = (r.get("data") if isinstance(r, dict) else r) or []
        out += linhas
        if len(linhas) < PAGINA:
            return out
        ini += PAGINA


def _folio(folio) -> str:
    return urllib.parse.quote(str(folio))


def tarefas_da_os(folio, ler=None) -> list:
    return _paginas(f"work_orders?wo_folio={_folio(folio)}", ler)


def subtarefas_da_os(folio, ler=None) -> list:
    return _paginas(f"work_orders_subtasks/?folio={_folio(folio)}", ler)


def anexos_da_os(folio, ler=None) -> list:
    return _paginas(f"work_orders_attachments?folio={_folio(folio)}", ler)


def ler_os(folio, ler=None) -> dict:
    """As tarefas, as subtarefas e os anexos de uma OS. Só GET, no ritmo do nexus.campo.fracttal."""
    return {"tarefas": tarefas_da_os(folio, ler), "subtarefas": subtarefas_da_os(folio, ler),
            "anexos": anexos_da_os(folio, ler)}


def notas_da_os(folio) -> dict:
    """{id da tarefa: nota} de todas as tarefas da OS."""
    os_ = ler_os(folio)
    out = {}
    for t in os_["tarefas"]:
        idt = t.get("id_work_orders_tasks")
        if idt is not None and idt not in out:
            out[idt] = nota(os_["subtarefas"], os_["anexos"], tarefa=idt)
    return out
