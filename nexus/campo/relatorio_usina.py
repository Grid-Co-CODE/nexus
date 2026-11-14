"""O relatório da usina em PDF, para o cliente (Levi, 04/11/2026: "é interessante que dê para baixar um relatório da usina
também! Algo bem profissional para o cliente!"). O "Baixar relatório" da Central da usina (a aba da Visão do responsável)
abre a escolha do mês e dos temas, como no Painel ("Tem que poder escolher que nem é no painel").

Decisões do Levi (04/11/2026): o mês é escolhido na hora de baixar, o anterior (fechado) de início, e o mês corrente sai
parcial, até ontem; os temas Performance e disponibilidade, Rondas e limpeza, Manutenção e Chamados de garantia, todos
marcados; PT, Segurança e os nomes dos técnicos ficam de fora (são internos).

- **O dado é o das telas donas, pelo mesmo leitor**, nada recalculado aqui: a meta e o dia a dia do Gerencial
  (`responsaveis.metas`, `serie_diaria`, `tabela_meta`), a disponibilidade (`disponibilidade`, `disp_diaria`,
  `os_disponibilidade`), as rondas da usina (`visao.historico_usina`), as tarefas feitas pelo App (`fato_fechamento`, sem
  as devolvidas), as OS abertas (`fato_tarefa_os`, a regra do bloco Manutenção: sem backoffice, teste e OS de chamado) e
  os chamados (`fato_chamado`, o quadro Acompanhamento de chamados).
- **Os meses:** o atual e os dois anteriores: as rondas, os chamados e as tarefas ficam 90 dias no banco.
- **O tema que não abre** sai com "não consegui ler" no lugar, e o resto do relatório vale.
- Fonte Helvetica e a paleta dos outros relatórios do Nexus (`painel_relatorio`, `hseq/relatorio`): sem "≥" nem seta,
  que ela não tem; o logo é o da Grid Co. (`static/grid-h-branco.png`) na faixa navy do topo.
"""
import calendar
import collections
import io
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import visao

rl_config.useA85 = 0        # binário, sem ASCII85 (o arquivo 25% menor; ver o relatório dos extintores)

NAVY, VERDE, VERDE_ESC = colors.HexColor("#090d18"), colors.HexColor("#b5d334"), colors.HexColor("#6f8f0b")
TOM = {"critico": colors.HexColor("#c8102e"), "alerta": colors.HexColor("#b26a00"), "ok": colors.HexColor("#1f7a3f"),
       "neutro": colors.HexColor("#5b6475")}
LINHA, FUNDO, MUDO, TINTA = (colors.HexColor("#d8dce4"), colors.HexColor("#f3f5f8"), colors.HexColor("#5b6475"),
                             colors.HexColor("#111827"))
LOGO = Path(__file__).resolve().parents[1] / "static" / "grid-h-branco.png"
MESES_NOME = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
              "novembro", "dezembro")
MESES = 3                   # o atual e os dois anteriores (90 dias no banco)
LARG = 178 * mm - 12        # a largura útil (o quadro do SimpleDocTemplate tem 6 pt de folga de cada lado)
TEMAS = (("perf", "Performance e disponibilidade"), ("religamentos", "Paradas e religamentos"),
         ("rondas", "Rondas e limpeza"), ("manut", "Manutenção"), ("chamados", "Chamados de garantia"))
CHAVES_TEMAS = tuple(k for k, _ in TEMAS)
# Os CAMPOS de cada tema (12/11/2026, Levi, no prontuário da usina: "eu quero o relatório de forma profissional, que dê
# para editar os campos que eu quero que apareça"): cada bloco do PDF é um campo que a pessoa liga e desliga na janela
# do relatório. (a chave, o tema dele — "" = o resumo, que é de todos —, o nome na janela), na ordem do PDF. Sem `campo`
# no pedido valem todos os campos dos temas pedidos: o endereço de antes, só com `tema`, dá o mesmo PDF de sempre
CAMPOS = (("resumo", "", "Resumo do mês, em frases"),
          ("perf_numeros", "perf", "Os números do mês: geração, meta, PR e disponibilidade"),
          ("perf_grafico", "perf", "Gráfico da geração de cada dia contra a meta"),
          ("perf_dias", "perf", "Tabela do dia a dia"),
          ("perf_eventos", "perf", "Eventos que afetaram a disponibilidade"),
          # as paradas do mês com o que aconteceu (14/11/2026): o relato da Ronda COS, que já é escrito para o cliente
          # (frases-modelo: a causa reconhecida, a proteção, os horários, se voltou pelo religamento remoto ou no local)
          ("religamentos_lista", "religamentos", "Paradas do mês e o que aconteceu em cada uma"),
          ("religamentos_protecoes", "religamentos", "Proteções que mais atuaram"),
          ("rondas_lista", "rondas", "Rondas do mês, com sujidade e vegetação"),
          ("manut_feitas", "manut", "Tarefas executadas no mês"),
          ("manut_abertas", "manut", "Ordens de serviço em aberto"),
          ("manut_zeladoria", "manut", "Zeladoria feita"),
          ("chamados_lista", "chamados", "Chamados do mês"),
          ("chamados_abertos", "chamados", "Chamados em aberto hoje"))
CHAVES_CAMPOS = tuple(k for k, _tema, _rot in CAMPOS)
TIPO_TAREFA = {"preventiva": "Preventiva", "corretiva": "Corretiva", "corretiva_emergencial": "Corretiva emergencial",
               "religamento": "Religamento", "religamento_remoto": "Religamento remoto", "inspecao": "Inspeção",
               "preditiva": "Preditiva", "administrativa": "Administrativa", "zeladoria": "Zeladoria",
               "handover": "Handover"}


# ── o mês e os temas do pedido ─────────────────────────────────────────────────────────────────────────────────────
def meses(hoje: date) -> list[tuple[str, str]]:
    """[("AAAA-MM", "Outubro de 2026")]: o mês atual e os dois anteriores, o mais novo primeiro."""
    out, a, m = [], hoje.year, hoje.month
    for _ in range(MESES):
        out.append((f"{a:04d}-{m:02d}", f"{MESES_NOME[m - 1].capitalize()} de {a}"))
        a, m = (a, m - 1) if m > 1 else (a - 1, 12)
    return out


def mes_padrao(hoje: date) -> str:
    """O mês fechado anterior (a decisão do Levi: o relatório do cliente é de mês fechado, o anterior de início)."""
    return meses(hoje)[1][0]


def mes_do_pedido(valor, hoje: date) -> str:
    validos = [m for m, _ in meses(hoje)]
    return valor if valor in validos else mes_padrao(hoje)


def temas_do_pedido(pedidos) -> tuple:
    """Os temas pedidos, na ordem do relatório (o que não é tema não entra); nenhum pedido válido = todos."""
    quer = {str(x).strip() for x in pedidos or ()}
    return tuple(k for k in CHAVES_TEMAS if k in quer) or CHAVES_TEMAS


def campos_por_tema() -> list[tuple[str, str, list[tuple[str, str]]]]:
    """Os campos agrupados para a janela do relatório: [(tema, o nome do tema, [(campo, nome)])], o geral ("") primeiro."""
    nomes = dict(TEMAS)
    return [(t, nomes.get(t, "Geral"), [(k, rot) for k, tema, rot in CAMPOS if tema == t]) for t in ("",) + CHAVES_TEMAS]


def campos_do_pedido(pedidos, temas=CHAVES_TEMAS) -> tuple:
    """Os campos que entram no PDF, na ordem dele: os pedidos (`campo` repetido) que são dos temas pedidos (o resumo é
    de todos). Sem nenhum campo válido no pedido, ou se nenhum for dos temas, valem todos os campos dos temas (o
    endereço só com `tema`): o relatório nunca sai vazio por um endereço torto."""
    quer = {str(x).strip() for x in pedidos or ()}
    dos_temas = tuple(k for k, tema, _rot in CAMPOS if not tema or tema in temas)
    return tuple(k for k in dos_temas if k in quer) or dos_temas


def temas_dos_campos(temas, campos) -> tuple:
    """Os temas que têm ao menos um campo ligado, na ordem do relatório: o resumo só fala deles (quem desligou todos os
    campos das Rondas não lê a frase das rondas). Com só o resumo ligado, ele fala de todos os temas pedidos."""
    com = {tema for k, tema, _rot in CAMPOS if k in campos and tema}
    return tuple(t for t in temas if t in com) or tuple(temas)


# ── os dados, das telas donas ──────────────────────────────────────────────────────────────────────────────────────
def _num(v):
    try:
        return None if v is None or v == "" else float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _dia_id(v) -> date | None:
    n = visao.D._int(v)
    try:
        return date(n // 10000, n // 100 % 100, n % 100) if n else None
    except ValueError:
        return None


def _tipo(v) -> str:
    t = visao.D._txt(v).strip().lower().replace(" ", "_")
    return TIPO_TAREFA.get(t) or (visao.D._txt(v).strip().capitalize() or "Outras")


def _religamentos_do_mes(uid: int, ano: int, mes: int) -> list[dict]:
    """As paradas do mês registradas pelo COS (`nexus_cos_normalizacoes · fato_normalizacao`), da mais velha para a mais
    nova: o início, o tipo, o tempo fora, se a geração parou, as proteções, a OS e o relato da Ronda COS."""
    from ..comando import prontuario as PR
    from ..cos import normalizacoes_banco as NB
    out = []
    for r in visao._livro(NB.LIVRO, NB.ABA):
        if visao.D._id(r.get("usina_id")) != uid:
            continue
        ini = PR.instante(r.get("inicio"))
        if not ini or (ini.year, ini.month) != (ano, mes):
            continue
        fora_min = _num(r.get("fora_min"))
        out.append({"ini": ini, "fim": ini + timedelta(minutes=fora_min) if fora_min is not None else None,
                    "tipo": PR.tipo_cos(r.get("tipo_falha"))[0], "fora": PR.fora_txt(r.get("fora_min")),
                    "parou": str(r.get("geracao_parou") or "") in ("1", "True"), "os": str(r.get("os") or "").strip(),
                    "protecoes": " ".join(str(r.get("protecoes") or "").split()),
                    "relato": " ".join(str(r.get("relato_cliente") or r.get("relato_continuacao") or "").split())})
    return sorted(out, key=lambda x: x["ini"])


# o nome de cada proteção, como o COS escreve no relato (conferido nas 1.830 normalizações do banco em 14/11/2026); o
# código da coluna `protecoes` vem com a fase ou o neutro (27ABC, 59N) e conta pelo número
PROTECAO_NOME = {"27": "Subtensão", "32": "Potência reversa", "46": "Desequilíbrio de corrente", "47": "Sequência de fase",
                 "50": "Sobrecorrente", "51": "Sobrecorrente", "59": "Sobretensão", "67": "Sobrecorrente direcional",
                 "78": "Salto de vetor", "81": "Frequência", "86": "Bloqueio"}
_RX_FRASES = re.compile(r"(?<=[.)])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])")
_HORA = r"\d{1,2}/\d{1,2} às \d{1,2}:\d{2}"
_RX_PERIODO = re.compile(rf"^(?:Continuação: )?(?P<rot>.+?) de {_HORA} a {_HORA}(?: \([^)]*\))?(?P<resto>.*?)\.?$")
_RX_VOLTOU = re.compile(rf"^(?P<quem>.+?) (?P<verbo>voltou|voltaram) a gerar em {_HORA}(?:, (?P<como>.+?))?\.?$")


def protecoes_do_texto(txt: str) -> list[str]:
    """Os códigos da coluna `protecoes` ("27ABC;59N") pelo número, sem repetir: ["27", "59"]."""
    out = []
    for p in re.split(r"[;,\s]+", txt or ""):
        m = re.match(r"\d+", p)
        if m and m.group() not in out:
            out.append(m.group())
    return out


def _como_voltou(como: str, plural: bool) -> tuple[str | None, str]:
    """('remoto' | 'local' | None, a frase da volta sem a hora, que já está no Período)."""
    c = como.strip().rstrip(".")
    jeito = "remoto" if re.search(r"remot|centro de operações|\bCOS\b", c) else "local" if "no local" in c else None
    verbo = "Voltaram a funcionar" if plural else "Voltou a funcionar"
    if re.fullmatch(r"religad[oa]s? remotamente pelo COS", c):
        return jeito, f"{verbo} pelo religamento remoto, feito pelo COS."
    if re.fullmatch(r"religad[oa]s? no local pela equipe de campo", c):
        return jeito, f"{verbo} pelo religamento no local, feito pela equipe de campo."
    if c.startswith("após"):
        return jeito, f"{verbo} {c}."
    return jeito, f"{verbo}: {c}."


_PLURAL = {"Cabine": "Cabines", "Inversor": "Inversores", "SKID": "SKIDs", "QGBT": "QGBTs", "Tracker": "Trackers"}


def _rotulo_curto(rot: str) -> str:
    """ "Cabine 1, Cabine 2, Cabine 4 e Cabine 5 desligadas" -> "Cabines 1, 2, 4 e 5 desligadas" (a coluna Parada é
    estreita: na Capitão Poço, em 10/11, o nome das cinco cabines ocupava seis linhas)."""
    m = re.match(r"^(?P<eq>Cabine|Inversor|SKID|QGBT|Tracker) (?P<lista>[\w.]+(?:(?:, | e )(?P=eq) [\w.]+)+)(?P<resto>.*)$", rot)
    if not m:
        return rot
    nums = re.split(r", | e ", m.group("lista").replace(m.group("eq") + " ", ""))
    return f"{_PLURAL[m.group('eq')]} {', '.join(nums[:-1])} e {nums[-1]}{m.group('resto')}"


def relato_partes(relato: str) -> dict:
    """O relato da Ronda COS sem o que a tabela já mostra (14/11/2026, Levi: "no usina desligada de dia tal a tal hora
    [...] já diz o período [...] Não precisa repetir quando voltou"). As frases são modelos fixos da Ronda COS
    (`relato-cliente.ts`), então dá para separar: {rotulo, causa, volta, jeito, extras}.
    - rotulo: o que parou ("Inversor 7.1 desligado", "Perda de comunicação"), da 1ª frase, para a coluna Parada;
    - causa: o "Causa: ..." (ou o resto da linha de continuação);
    - volta: como voltou, sem a hora; jeito: 'remoto' | 'local' | None;
    - extras: o que sobra (o chamado com a concessionária, "religado, mas desligou de novo", "sem impacto na geração").
    A frase da hora da volta sem o "como" e o "Normalizada em" saem: o Período já diz."""
    out = {"rotulo": "", "causa": "", "volta": "", "jeito": None, "extras": []}
    for f in _RX_FRASES.split(" ".join(str(relato or "").split())):
        f = f.strip()
        if not f:
            continue
        m = _RX_PERIODO.match(f)
        if m and not out["rotulo"] and not f.startswith("Em "):
            out["rotulo"] = _rotulo_curto(m.group("rot").replace(" com a usina", "").strip())
            resto = m.group("resto").strip(" ,")
            if re.match(r"sem (impacto|interrupção)", resto):
                out["extras"].append(resto[0].upper() + resto[1:] + ".")
            elif resto and not out["causa"]:
                out["causa"] = re.sub(r"^por ", "", resto)
            continue
        if f.startswith("Causa:"):
            out["causa"] = f[6:].strip().rstrip(".")
            continue
        if re.match(rf"^Normalizada em {_HORA}\.?$", f):
            continue
        if re.match(rf"^Em {_HORA}, a comunicação foi restabelecida\.?$", f):
            out["volta"] = "A comunicação foi restabelecida."
            continue
        if re.search(r"religad[oa]s? remotamente e voltou a gerar", f):
            out["jeito"], out["volta"] = "remoto", "Voltou a funcionar pelo religamento remoto."
            continue
        if re.match(r"^A equipe de campo religou .* no local", f):
            out["jeito"], out["volta"] = "local", "Voltou a funcionar pelo religamento no local, feito pela equipe de campo."
            continue
        m = _RX_VOLTOU.match(f)
        if m:
            if m.group("como"):
                out["jeito"], out["volta"] = _como_voltou(m.group("como"), m.group("verbo") == "voltaram")
            continue
        out["extras"].append(f if f.endswith(".") else f + ".")
    if out["causa"]:
        out["causa"] = out["causa"][0].upper() + out["causa"][1:]
    return out


def dados(uid: int, mes: str, hoje: date) -> dict:
    """Tudo o que o relatório mostra da usina no mês, cada tema da sua fonte; o tema que não abre fica em `erros`."""
    from ..dados import fato_tarefa_os as FT
    from . import responsaveis as R
    from . import ronda_checklist
    b = visao._Base()
    o = b.onde(uid)
    cad = b.por_id.get(uid) or {}
    ano, m = int(mes[:4]), int(mes[5:7])
    mes_id = ano * 100 + m
    corrente = (ano, m) == (hoje.year, hoje.month)
    fim = (hoje - timedelta(days=1)) if corrente else date(ano, m, calendar.monthrange(ano, m)[1])
    out = {"uid": uid, "usina": o.get("usina") or "", "cliente": o.get("cliente") or "", "cidade": o.get("cidade") or "",
           "uf": o.get("uf") or "", "potencia_mwp": _num(cad.get("potencia_real")), "mes": mes, "mes_id": mes_id,
           "mes_txt": f"{MESES_NOME[m - 1]} de {ano}", "ini": date(ano, m, 1), "fim": fim, "corrente": corrente,
           "hoje": hoje, "erros": {}}
    nomes = R.Nomes(b)
    try:
        meta = R.metas(nomes, mes_id)[0].get(uid) or {}
        disp = R.disponibilidade(nomes, mes)[0].get(uid) or {}
        serie = R.serie_diaria(uid, mes_id, nomes)
        out["perf"] = {"meta": meta, "disp": disp, "serie": serie,
                       "tabela": R.tabela_meta(serie, R.disp_diaria(uid, mes, nomes), disp.get("disp")),
                       "oss": R.os_disponibilidade(uid, mes, nomes)}
    except Exception as e:      # noqa: BLE001 — o tema diz que não leu; o resto vale
        out["erros"]["perf"] = type(e).__name__
    try:
        lr = visao.rondas()
        dr = lr.dados or {}
        if lr.erro:
            raise visao.SemBanco(lr.erro)
        hist = visao.historico_usina(dr.get("todas") or [], ronda_checklist.respostas(), uid, dr.get("validacoes") or [])
        out["rondas"] = sorted((r for r in hist if str(r.get("data") or "")[:7] == mes and not r.get("validada")),
                               key=lambda r: (r.get("data") or "", r.get("ini_hm") or ""))
    except Exception as e:      # noqa: BLE001
        out["erros"]["rondas"] = type(e).__name__
    try:
        os_chamado = {visao.D._id(r.get("os")) for r in visao._livro(R.LIVRO_CHAMADOS, R.ABA_CHAMADOS)}
        feitas = collections.defaultdict(lambda: {"tarefas": 0, "os": set()})
        for x in visao._fato("fechamento", b)["linhas"]:
            if visao.D._id(x.get("usina_id")) != uid or (visao.D._int(x.get("data_id")) or 0) // 100 != mes_id:
                continue
            if visao.D._int(x.get("devolvida")) == 1:
                continue
            g = feitas[_tipo(x.get("tipo_os"))]
            g["tarefas"] += 1
            g["os"].add(visao.D._id(x.get("os")))
        abertas, zel = collections.defaultdict(set), []
        for t in visao._livro(FT.LIVRO, FT.ABA):
            if visao.D._id(t.get("usina_id")) != uid:
                continue
            tipo, os_ = visao.D._txt(t.get("tipo_tarefa")), visao.D._id(t.get("os"))
            if tipo == "zeladoria":
                d = _dia_id(t.get("data_id_fim"))
                if d and (d.year, d.month) == (ano, m) and visao.D._txt(t.get("estado_tarefa")) == "finalizada":
                    zel.append(d)
                continue
            if (visao.D._int(t.get("do_backoffice")) == 1 or tipo == "teste" or os_ in os_chamado
                    or visao.D._txt(t.get("status_os")) not in ("em_processo", "em_verificacao")):
                continue
            abertas[_tipo(tipo)].add(os_)
        out["manut"] = {"feitas": sorted(({"tipo": k, "tarefas": v["tarefas"], "os": len(v["os"] - {None})}
                                          for k, v in feitas.items()), key=lambda x: -x["tarefas"]),
                        "abertas": sorted(({"tipo": k, "os": len(v - {None})} for k, v in abertas.items()),
                                          key=lambda x: -x["os"]),
                        "zeladoria": sorted(set(zel))}
    except Exception as e:      # noqa: BLE001
        out["erros"]["manut"] = type(e).__name__
    try:
        out["religamentos"] = _religamentos_do_mes(uid, ano, m)
    except Exception as e:      # noqa: BLE001
        out["erros"]["religamentos"] = type(e).__name__
    try:
        linhas = [r for r in visao._livro(R.LIVRO_CHAMADOS, R.ABA_CHAMADOS) if visao.D._id(r.get("usina_id")) == uid]
        nome_equip = {visao.D._id(r.get("equipamento_id")): str(r.get("descricao") or "").strip()
                      for r in visao._livro(R.LIVRO_EQUIP, R.ABA_EQUIP)} if linhas else {}
        def item(r):
            eid = visao.D._id(r.get("equipamento_id"))
            ini, fim_c = _dia_id(r.get("data_id_abertura")), _dia_id(r.get("data_id_fim"))
            return {"os": visao.D._id(r.get("os")), "ini": ini, "fim": fim_c, "situacao": str(r.get("situacao") or ""),
                    "dias": ((fim_c or hoje) - ini).days if ini else None,
                    "equip": (nome_equip.get(eid) or str(r.get("codigo_ativo") or "") or "equipamento")[:40],
                    "fabricante": str(r.get("fabricante") or ""), "componente": str(r.get("componente") or "")}
        todos = [item(r) for r in linhas]
        no_mes = [c for c in todos if (c["ini"] and (c["ini"].year, c["ini"].month) == (ano, m))
                  or (c["fim"] and c["situacao"] == "concluido" and (c["fim"].year, c["fim"].month) == (ano, m))]
        out["chamados"] = {"mes": sorted(no_mes, key=lambda c: (c["ini"] or date.min, c["os"] or 0)),
                           "em_aberto": sum(1 for c in todos if c["situacao"] in ("aberto", "verificacao"))}
    except Exception as e:      # noqa: BLE001
        out["erros"]["chamados"] = type(e).__name__
    return out


# ── o PDF ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _t(v) -> str:
    s = "" if v is None else str(v)
    for a, b in (("≥", ">="), ("→", "->"), (" ", " "), (" ", " ")):
        s = s.replace(a, b)
    return escape(s)


def _br(x, casas=1) -> str:
    return "—" if x is None else f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x, casas=1) -> str:
    return "—" if x is None else _br(x, casas) + "%"


def _dm(d) -> str:
    return d.strftime("%d/%m") if d else "—"


def _cor(nivel) -> str:
    return "#" + TOM.get(nivel, TOM["neutro"]).hexval()[2:]


def _cls_meta(a):
    from . import responsaveis as R
    return R.cls_meta(a)


def _cls_disp(x):
    from . import responsaveis as R
    return R.cls_disp(x)


def _estilos() -> dict:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12.5, textColor=TINTA)
    return {"base": base,
            "mudo": ParagraphStyle("mudo", parent=base, fontSize=8, leading=11, textColor=MUDO),
            "titulo": ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=21, leading=25),
            "sub": ParagraphStyle("sub", parent=base, fontSize=10, leading=14, textColor=MUDO),
            "secao": ParagraphStyle("secao", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17,
                                    spaceBefore=4, spaceAfter=2),
            "sub_secao": ParagraphStyle("sub_secao", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=14,
                                        spaceBefore=6, spaceAfter=3),
            "cel": ParagraphStyle("cel", parent=base, fontSize=8.5, leading=11),
            "cel_cab": ParagraphStyle("cel_cab", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10,
                                      textColor=MUDO),
            "cel_c": ParagraphStyle("cel_c", parent=base, fontSize=8.5, leading=11, alignment=TA_CENTER),
            "cel_cab_c": ParagraphStyle("cel_cab_c", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10,
                                        textColor=MUDO, alignment=TA_CENTER),
            "parada": ParagraphStyle("parada", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                                     alignment=TA_CENTER),
            "periodo": ParagraphStyle("periodo", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=10.5,
                                      alignment=TA_CENTER),
            "kpi_rot": ParagraphStyle("kpi_rot", parent=base, fontSize=8, leading=10, textColor=MUDO),
            "kpi_val": ParagraphStyle("kpi_val", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22),
            "kpi_sub": ParagraphStyle("kpi_sub", parent=base, fontSize=7.5, leading=10, textColor=MUDO)}


def _secao(titulo: str, e: dict) -> list:
    """O título da seção com o fio verde embaixo (a marca da Grid Co. nos relatórios)."""
    t = Table([[Paragraph(_t(titulo), e["secao"])]], colWidths=[LARG], hAlign="LEFT")
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.6, VERDE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    return [CondPageBreak(60 * mm), Spacer(1, 7 * mm), t, Spacer(1, 3 * mm)]


def _tabela(e: dict, cab: list[str], linhas: list[list], larguras: list[float], total: bool = False,
            direita: tuple = (), centro: tuple = (), cab_centro: bool = False) -> Table:
    """`centro`: as colunas do corpo centralizadas; `cab_centro`: o cabeçalho todo centralizado (a tabela das paradas,
    14/11/2026, Levi: "centralizar todas as colunas e cabeçalhos, a não ser a coluna do que aconteceu")."""
    dados_t = [[Paragraph(_t(c), e["cel_cab_c"] if cab_centro else e["cel_cab"]) for c in cab]]
    for ln in linhas:
        dados_t.append([c if isinstance(c, (Flowable, list)) else Paragraph(_t(c), e["cel_c"] if i in centro else e["cel"])
                        for i, c in enumerate(ln)])
    # as larguras em mm somam a largura toda; a tabela sai alinhada com o texto, à esquerda
    fator = LARG / (sum(larguras) * mm)
    t = Table(dados_t, colWidths=[w * mm * fator for w in larguras], repeatRows=1, hAlign="LEFT")
    st = [("LINEBELOW", (0, 0), (-1, 0), 0.8, MUDO), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINHA),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 4),
          ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    for i in range(1, len(dados_t)):
        if i % 2 == 0:
            st.append(("BACKGROUND", (0, i), (-1, i), FUNDO))
    if total and len(dados_t) > 1:
        st += [("LINEABOVE", (0, -1), (-1, -1), 0.8, MUDO), ("BACKGROUND", (0, -1), (-1, -1), colors.white)]
    t.setStyle(TableStyle(st))
    return t


def _p(txt: str, e: dict, estilo: str = "cel", cor: str | None = None, negrito: bool = False) -> Paragraph:
    s = _t(txt)
    if negrito:
        s = f"<b>{s}</b>"
    if cor:
        s = f'<font color="{_cor(cor)}">{s}</font>'
    return Paragraph(s, e[estilo])


def _kpis(d: dict, e: dict) -> Table:
    """Os quatro números do mês, na régua da Visão (a cor diz se está na meta)."""
    p = d.get("perf") or {}
    meta, disp = p.get("meta") or {}, p.get("disp") or {}
    ating, pr, prm, dv = meta.get("atingimento"), meta.get("pr"), meta.get("pr_meta"), disp.get("disp")
    cel = [
        ("Geração no mês", f"{_br((meta.get('prod_kwh') or 0) / 1000)} MWh" if meta.get("prod_kwh") is not None else "—",
         f"meta: {_br((meta.get('meta_kwh') or 0) / 1000)} MWh" if meta.get("meta_kwh") else "sem meta publicada",
         None),
        ("Atingimento da meta", _pct(ating, 0), f"{meta.get('dias_cob') or 0} dias medidos" if meta else "", _cls_meta(ating)),
        ("PR (performance ratio)", _pct(pr), f"previsto {_pct(prm)}" if prm is not None else "",
         None if pr is None or prm is None else ("ok" if pr >= prm else "alerta")),
        ("Disponibilidade", _pct(dv), f"{_br(disp.get('h_perdidas'))} h paradas" if disp else "", _cls_disp(dv))]
    linha = []
    for rot, val, sub, nivel in cel:
        linha.append([Paragraph(_t(rot), e["kpi_rot"]),
                      Paragraph(f'<font color="{_cor(nivel) if nivel else "#111827"}">{_t(val)}</font>', e["kpi_val"]),
                      Paragraph(_t(sub), e["kpi_sub"])])
    t = Table([linha], colWidths=[LARG / 4] * 4, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), FUNDO), ("BOX", (0, 0), (-1, -1), 0.5, LINHA),
                           ("LINEAFTER", (0, 0), (-2, -1), 0.5, LINHA), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _grafico(d: dict) -> Drawing | None:
    """A geração de cada dia (barras verdes) contra a meta do dia (a linha navy), em MWh."""
    dias = [x for x in ((d.get("perf") or {}).get("serie") or {}).get("dias") or [] if x.get("geracao_kwh") is not None]
    if not dias:
        return None
    n_mes = calendar.monthrange(d["ini"].year, d["ini"].month)[1]
    larg, alt, esq, base, topo = LARG, 58 * mm, 12 * mm, 9 * mm, 6 * mm
    area_l, area_a = larg - esq - 2 * mm, alt - base - topo
    maximo = max(max((x["geracao_kwh"] or 0) for x in dias), max((x.get("meta_kwh") or 0) for x in dias)) / 1000
    passo = next(p for p in (0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500) if maximo / p <= 5)
    teto = passo * (int(maximo / passo) + 1)
    g = Drawing(larg, alt)
    for i in range(int(teto / passo) + 1):
        y = base + area_a * (i * passo) / teto
        g.add(Line(esq, y, larg - 2 * mm, y, strokeColor=LINHA, strokeWidth=0.4))
        g.add(String(esq - 2, y - 2.5, _br(i * passo, 0 if passo >= 1 else 1), fontName="Helvetica", fontSize=6.5,
                     fillColor=MUDO, textAnchor="end"))
    coluna = area_l / n_mes
    pontos = []
    for x in dias:
        cx = esq + coluna * (x["dia"] - 0.5)
        h = area_a * (x["geracao_kwh"] / 1000) / teto
        g.add(Rect(cx - coluna * 0.32, base, coluna * 0.64, h, fillColor=VERDE, strokeColor=None))
        if x.get("meta_kwh") is not None:
            pontos += [cx, base + area_a * (x["meta_kwh"] / 1000) / teto]
    for dia in range(1, n_mes + 1):
        if dia == 1 or dia % 5 == 0:
            g.add(String(esq + coluna * (dia - 0.5), base - 7, str(dia), fontName="Helvetica", fontSize=6.5,
                         fillColor=MUDO, textAnchor="middle"))
    if len(pontos) >= 4:
        g.add(PolyLine(pontos, strokeColor=NAVY, strokeWidth=1.2))
    g.add(Rect(esq, alt - 4, 7, 4, fillColor=VERDE, strokeColor=None))
    g.add(String(esq + 10, alt - 4, "Geração do dia (MWh)", fontName="Helvetica", fontSize=7, fillColor=MUDO))
    g.add(Line(esq + 100, alt - 2, esq + 112, alt - 2, strokeColor=NAVY, strokeWidth=1.2))
    g.add(String(esq + 116, alt - 4, "Meta do dia (MWh)", fontName="Helvetica", fontSize=7, fillColor=MUDO))
    return g


def _resumo(d: dict, temas: tuple) -> list[str]:
    """As frases do resumo do mês, só dos temas escolhidos (o número e o que ele quer dizer)."""
    out = []
    if "perf" in temas and d.get("perf"):
        meta, disp = d["perf"].get("meta") or {}, d["perf"].get("disp") or {}
        if meta.get("prod_kwh") is not None and meta.get("meta_kwh"):
            dif = (meta.get("atingimento") or 0) - 100
            sinal = "acima" if dif >= 0 else "abaixo"
            out.append(f"A usina gerou {_br(meta['prod_kwh'] / 1000)} MWh, {_br(abs(dif), 0)}% {sinal} da meta dos "
                       f"{meta.get('dias_cob') or 0} dias medidos.")
        if meta.get("pr") is not None and meta.get("pr_meta") is not None:
            out.append(f"O PR do mês foi de {_pct(meta['pr'])}, contra {_pct(meta['pr_meta'])} previstos.")
        if disp.get("disp") is not None:
            n = len((d["perf"].get("oss") or {}).get("oss") or [])
            out.append(f"A disponibilidade foi de {_pct(disp['disp'])}" +
                       (f", com {n} evento{'s' if n != 1 else ''} de parada registrado{'s' if n != 1 else ''}."
                        if n else ", sem parada registrada."))
    # as paradas e religamentos não têm frase aqui: o número do alto da seção já diz (14/11/2026, Levi: "nesse resumo
    # aí, é a mesma coisa que se repete no KPI que tem no paradas e religamentos. Então pode tirar")
    if "rondas" in temas and d.get("rondas") is not None:
        n = len(d["rondas"])
        lidas = [r for r in d["rondas"] if r.get("sujidade") is not None]
        if n:
            frase = f"Foram feitas {n} rondas na usina" if n != 1 else "Foi feita 1 ronda na usina"
            if lidas:
                u = lidas[-1]
                frase += f"; na última leitura, sujidade {u['sujidade']} e vegetação {u.get('vegetacao') or '—'} (de 1 a 5)"
            out.append(frase + ".")
    if "manut" in temas and d.get("manut"):
        t = sum(x["tarefas"] for x in d["manut"]["feitas"])
        if t:
            out.append(f"A equipe executou {t} tarefa{'s' if t != 1 else ''} de manutenção no mês.")
    if "chamados" in temas and d.get("chamados"):
        fin = sum(1 for c in d["chamados"]["mes"] if c["situacao"] == "concluido" and c["fim"]
                  and (c["fim"].year, c["fim"].month) == (d["ini"].year, d["ini"].month))
        ab = d["chamados"]["em_aberto"]
        if fin or ab:
            out.append(f"Chamados de garantia: {fin} finalizado{'s' if fin != 1 else ''} no mês e {ab} em aberto "
                       f"em {_dm(d['hoje'])}.")
    return out


def _sem(e: dict, txt: str) -> Paragraph:
    return Paragraph(_t(txt), e["mudo"])


def _perf(d: dict, e: dict, campos=CHAVES_CAMPOS) -> list:
    p = d.get("perf") or {}
    out = []
    g = _grafico(d) if "perf_grafico" in campos else None
    if g:
        out += [Paragraph("Geração diária e meta", e["sub_secao"]), g, Spacer(1, 2 * mm)]
    tab = p.get("tabela") or {}
    if "perf_dias" not in campos:
        # sem a tabela, o gráfico pedido que não tem dado diz que não tem (a seção não fica muda)
        if "perf_grafico" in campos and not g:
            out.append(_sem(e, "Sem geração publicada para a usina neste mês."))
    elif tab.get("linhas"):
        linhas = [[f"{x['dia']:02d}", _br(x["real"]), _br(x["meta"]), _p(f"{x['pct']}%" if x["pct"] is not None else "—", e,
                   cor=x["cls"]), _br(x["poa"], 2), _p(_pct(x["disp"]), e, cor=x["disp_cls"] if x["disp"] is not None else None)]
                  for x in tab["linhas"]]
        t = tab["total"]
        linhas.append([_p("Total", e, negrito=True), _p(_br(t["real"]), e, negrito=True), _p(_br(t["meta"]), e, negrito=True),
                       _p(_pct(t["pct"], 0), e, negrito=True, cor=t["cls"]), _p(_br(t["poa"], 2), e, negrito=True),
                       _p(_pct(t["disp"]), e, negrito=True, cor=t["disp_cls"] if t["disp"] is not None else None)])
        out += [Paragraph("Dia a dia", e["sub_secao"]),
                _tabela(e, ["Dia", "Geração (MWh)", "Meta (MWh)", "% da meta", "POA (kWh/m²)", "Disponibilidade"], linhas,
                        [16, 32, 30, 28, 34, 38], total=True),
                Paragraph("A meta e o atingimento contam os dias com geração medida, como no Gerencial; a disponibilidade "
                          "do dia sai quando o dia fecha.", e["mudo"])]
    else:
        out.append(_sem(e, "Sem geração publicada para a usina neste mês."))
    if "perf_eventos" not in campos:
        return out
    oss = (p.get("oss") or {}).get("oss") or []
    out.append(Paragraph("Eventos que afetaram a disponibilidade", e["sub_secao"]))
    if oss:
        # a usina do cadastro que junta duas do Gerencial (Coração 1 e 2) tem o mesmo evento nas duas: a parte diz qual
        partes = len({x.get("usina") for x in oss}) > 1
        linhas = [[x["inicio"], x["fim"] or "em aberto", *([x.get("usina") or "—"] if partes else []),
                   (x["tipo"] or "—")[:1].upper() + (x["tipo"] or "")[1:], x["escopo"],
                   f"{_br((x['sol_min'] or 0) / 60)} h" if x["sol_min"] is not None else "—",
                   _br(x["perda_kwh"], 0) if x["perda_kwh"] is not None else "—"] for x in oss]
        out.append(_tabela(e, ["Início", "Fim", *(["Parte"] if partes else []), "Tipo", "Escopo", "Horas de sol",
                               "Perda (kWh)"], linhas,
                           [20, 20, *([22] if partes else []), 42, 30, 20, 22]))
    else:
        out.append(_sem(e, "Nenhum evento tirou disponibilidade da usina no mês."))
    return out


def _nivel_txt(n) -> Paragraph | str:
    if n is None:
        return "—"
    return f'<font color="{_cor("critico" if n >= 5 else "alerta" if n >= 4 else "ok")}"><b>{n}</b></font>'


def _rondas(d: dict, e: dict, campos=CHAVES_CAMPOS) -> list:
    if "rondas_lista" not in campos:
        return []
    rs = d.get("rondas") or []
    if not rs:
        return [_sem(e, "Nenhuma ronda registrada na usina no mês.")]
    linhas = []
    for r in rs:
        dia = str(r.get("data") or "")
        sens = r.get("sensores_sujos") or []
        linhas.append([f"{dia[8:10]}/{dia[5:7]}", str(r.get("tipo") or "").capitalize() or "—",
                       Paragraph(_nivel_txt(r.get("sujidade")), e["cel"]), Paragraph(_nivel_txt(r.get("vegetacao")), e["cel"]),
                       str(r.get("vala") or "—").capitalize(),
                       ("sujo: " + ", ".join(sens)) if sens else ("limpos" if r.get("lida") else "—")])
    return [_tabela(e, ["Data", "Tipo", "Sujidade", "Vegetação", "Vala de drenagem", "Sensores"], linhas,
                    [20, 22, 22, 24, 40, 50]),
            Paragraph("Sujidade e vegetação em escala de 1 (baixa) a 5 (muito alta): 4 pede atenção e 5, ação. Ronda "
                      "curta: a volta de rotina; longa: a vistoria completa da usina.", e["mudo"])]


def _manut(d: dict, e: dict, campos=CHAVES_CAMPOS) -> list:
    mt = d.get("manut") or {}
    out = [Paragraph("Tarefas executadas no mês", e["sub_secao"])] if "manut_feitas" in campos else []
    if "manut_feitas" not in campos:
        pass
    elif mt.get("feitas"):
        linhas = [[x["tipo"], str(x["tarefas"]), str(x["os"])] for x in mt["feitas"]]
        linhas.append([_p("Total", e, negrito=True), _p(str(sum(x["tarefas"] for x in mt["feitas"])), e, negrito=True),
                       _p(str(sum(x["os"] for x in mt["feitas"])), e, negrito=True)])
        out.append(_tabela(e, ["Tipo", "Tarefas", "Ordens de serviço"], linhas, [70, 40, 50], total=True))
    else:
        out.append(_sem(e, "Nenhuma tarefa executada pela equipe registrada no mês."))
    if "manut_abertas" in campos:
        out.append(Paragraph(f"Ordens de serviço em aberto em {_dm(d['hoje'])}/{d['hoje'].year}", e["sub_secao"]))
        if mt.get("abertas"):
            out.append(_tabela(e, ["Tipo", "Ordens de serviço"], [[x["tipo"], str(x["os"])] for x in mt["abertas"]], [70, 50]))
        else:
            out.append(_sem(e, "Nenhuma ordem de serviço em aberto."))
    if "manut_zeladoria" in campos and mt.get("zeladoria"):
        out.append(Paragraph("Zeladoria feita em " + ", ".join(_dm(x) for x in mt["zeladoria"]) + ".", e["base"]))
    return out


def _chamados(d: dict, e: dict, campos=CHAVES_CAMPOS) -> list:
    ch = d.get("chamados") or {}
    out = []
    if "chamados_lista" not in campos:
        pass
    elif ch.get("mes"):
        linhas = [[str(c["os"] or "—"), c["equip"], c["fabricante"] or "—", c["componente"] or "—", _dm(c["ini"]),
                   _dm(c["fim"]) if c["situacao"] == "concluido" else ("em verificação" if c["situacao"] == "verificacao"
                                                                       else "em aberto"),
                   str(c["dias"]) if c["dias"] is not None else "—"] for c in ch["mes"]]
        out.append(_tabela(e, ["OS", "Equipamento", "Fabricante", "Componente", "Abertura", "Fim", "Dias"], linhas,
                           [16, 44, 28, 34, 18, 22, 16]))
    else:
        out.append(_sem(e, "Nenhum chamado de garantia aberto ou finalizado no mês."))
    if "chamados_abertos" in campos:
        out.append(Paragraph(f"Em aberto em {_dm(d['hoje'])}/{d['hoje'].year}: {ch.get('em_aberto', 0)} "
                             f"chamado{'s' if ch.get('em_aberto', 0) != 1 else ''} de garantia.", e["base"]))
    return out


# a cor da parada (o semáforo da casa): a usina inteira parada é crítica, um pedaço dela (cabine, inversor) é alerta, e a
# parada sem a geração parada (a comunicação) é neutra. O fundo claro da célula destaca a parada sem faixa lateral
_TINTA_PARADA = {"critico": colors.HexColor("#fdecee"), "alerta": colors.HexColor("#fdf3e3"), "neutro": colors.HexColor("#eef0f4")}


def _nivel_parada(x: dict, rotulo: str) -> str:
    if not x.get("parou") or rotulo.startswith("Manutenção"):
        return "neutro"
    return "critico" if rotulo.lower().startswith("usina") else "alerta"


def _contagem_protecoes(rel: list[dict]) -> list[tuple[str, int]]:
    """[(código, em quantas paradas atuou)], a que mais atuou primeiro."""
    return collections.Counter(c for x in rel for c in protecoes_do_texto(x.get("protecoes"))).most_common()


def _kpis_religamentos(rel: list[dict], partes: list[dict], e: dict) -> Table:
    parou = sum(1 for x in rel if x.get("parou"))
    remoto = sum(1 for p in partes if p["jeito"] == "remoto")
    local = sum(1 for p in partes if p["jeito"] == "local")
    conta = _contagem_protecoes(rel)
    if conta:
        cod, n = conta[0]
        prot = (cod, f"{PROTECAO_NOME.get(cod, 'proteção ' + cod).lower()}, em {n} parada{'s' if n != 1 else ''}")
    else:
        prot = ("—", "nenhuma proteção registrada")
    cel = [("Paradas no mês", str(len(rel)), f"{parou} com a geração parada", "critico" if parou else None),
           ("Religamento remoto", str(remoto), "a distância, sem ir à usina", None),
           ("Religamento no local", str(local), "com a equipe de campo na usina", None),
           ("Proteção que mais atuou", prot[0], prot[1], None)]
    linha = [[Paragraph(_t(rot), e["kpi_rot"]),
              Paragraph(f'<font color="{_cor(nivel) if nivel else "#111827"}">{_t(val)}</font>', e["kpi_val"]),
              Paragraph(_t(sub), e["kpi_sub"])] for rot, val, sub, nivel in cel]
    t = Table([linha], colWidths=[LARG / 4] * 4, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), FUNDO), ("BOX", (0, 0), (-1, -1), 0.5, LINHA),
                           ("LINEAFTER", (0, 0), (-2, -1), 0.5, LINHA), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    return t


# as pílulas do período (14/11/2026, Levi: "no horário que saiu, fica um pastelzinho vermelho. No horário que voltou,
# um pastelzinho verde"): o fundo pastel e o texto no tom escuro da mesma cor, para ler bem
PILULA_PARADA = (colors.HexColor("#fde4e7"), colors.HexColor("#a3122a"))
PILULA_VOLTA = (colors.HexColor("#dcf2e3"), colors.HexColor("#17603a"))


def _pilula(txt: str, cor: tuple, e: dict) -> Table:
    """O horário numa pílula de cantos redondos, com o fundo pastel."""
    fundo, tinta = cor
    t = Table([[Paragraph(f'<font color="{tinta.hexval().replace("0x", "#")}">{_t(txt)}</font>', e["periodo"])]],
              colWidths=[21 * mm], hAlign="CENTER")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fundo), ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                           ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    return t


def _o_que_aconteceu(p: dict, e: dict) -> Paragraph:
    """A causa, como voltou (em verde: é a resolução) e o que mais o relato traz; nada do que a linha já mostra."""
    partes = []
    if p["causa"]:
        partes.append(f"<b>Causa:</b> {_t(p['causa'])}.")
    if p["volta"]:
        partes.append(f'<font color="{TOM["ok"].hexval().replace("0x", "#")}">{_t(p["volta"])}</font>')
    if p["extras"]:
        partes.append(f'<font color="{MUDO.hexval().replace("0x", "#")}">{_t(" ".join(p["extras"]))}</font>')
    if not partes:
        return Paragraph(_t("O relato não veio da Ronda COS."), e["mudo"])
    return Paragraph("<br/>".join(partes), e["cel"])


def _religamentos(d: dict, e: dict, campos=CHAVES_CAMPOS) -> list:
    """As paradas do mês (14/11/2026, Levi: "um negócio explicando religamento, bonitinho mesmo"): a explicação do
    religamento, os quatro números, a tabela (a parada em destaque; o "o que aconteceu" só completa) e as proteções."""
    rel = d.get("religamentos") or []
    out = []
    partes = [relato_partes(x.get("relato")) for x in rel]
    if "religamentos_lista" in campos:
        out.append(Paragraph(_t("Cada parada do mês registrada pelo Centro de Operações (COS) da Grid Co., com a causa e "
                                "a forma como a usina voltou. Quando uma proteção do relé desliga a usina, a volta é o "
                                "religamento: remoto, feito a distância, ou no local, com a equipe de campo na usina. "
                                "No período, o fundo vermelho marca a hora da parada e o verde, a hora da volta."),
                             e["base"]))
        out.append(Spacer(1, 3 * mm))
        if not rel:
            out.append(_sem(e, "Nenhuma parada registrada pelo COS no mês."))
        else:
            out += [_kpis_religamentos(rel, partes, e), Spacer(1, 4 * mm)]
    # o gráfico das proteções logo depois dos números, antes da tabela (14/11/2026, Levi: "esse gráfico aí de proteções
    # que mais atuaram deve vir para cima [...] Depois dos KPIs vem esse gráfico")
    if "religamentos_protecoes" in campos and rel:
        out += _grafico_protecoes(rel, partes, e)
    if "religamentos_lista" in campos and rel:
        linhas, tintas = [], []
        for x, p in zip(rel, partes):
            rotulo = p["rotulo"] or x.get("tipo") or "Parada"
            nivel = _nivel_parada(x, rotulo)
            tintas.append(_TINTA_PARADA[nivel])
            # o período em destaque: a hora da parada numa pílula vermelho-pastel e a da volta numa verde-pastel
            # (14/11/2026, Levi; o sublinhado colorido da primeira versão "não gostei muito")
            fim = x.get("fim")
            periodo = [_pilula(f"{x['ini']:%d/%m %H:%M}", PILULA_PARADA, e)]
            if fim:
                periodo += [Spacer(1, 3), _pilula(f"{fim:%d/%m %H:%M}", PILULA_VOLTA, e)]
            linhas.append([Paragraph(f'<font color="{_cor(nivel)}">{_t(rotulo)}</font>', e["parada"]),
                           periodo,
                           _h_min(minutos_solares(x["ini"], fim)), ", ".join(protecoes_do_texto(x.get("protecoes"))) or "—",
                           x.get("os") or "—", _o_que_aconteceu(p, e)])
        # a Parada na frente (14/11/2026, Levi: "Parada fica na frente")
        t = _tabela(e, ["Parada", "Período", "Tempo indisponível (solar)", "Proteções", "OS", "O que aconteceu"], linhas,
                    [26, 25, 23, 18, 13, 73], centro=(1, 2, 3, 4), cab_centro=True)
        # a parada em destaque: o fundo claro da cor dela (por cima da zebra)
        t.setStyle(TableStyle([("BACKGROUND", (0, i), (0, i), c) for i, c in enumerate(tintas, start=1)]))
        out.append(t)
    return out


# o período solar (14/11/2026, Levi: "a parte de tempo fora, tem que ser calculado em período solar [...] De 6 da manhã
# às 6 da tarde [...] bota assim, tempo indisponível. Aí bota entre parênteses solar"): a parada da noite não tira
# geração, então só conta o pedaço dela dentro da janela
SOLAR = (time(6), time(18))


def minutos_solares(ini: datetime | None, fim: datetime | None) -> int | None:
    """Os minutos da parada dentro do período solar (6h às 18h, no fuso do início), somados dia a dia. None sem o fim.
    Ex.: de 02/11 21:40 a 03/11 08:51 = 2 h 51 min (só a manhã do dia 3)."""
    if not ini or not fim:
        return None
    total, dia = 0.0, ini.date()
    while dia <= fim.date():
        a = datetime.combine(dia, SOLAR[0], tzinfo=ini.tzinfo)
        b = datetime.combine(dia, SOLAR[1], tzinfo=ini.tzinfo)
        total += max(0.0, (min(fim, b) - max(ini, a)).total_seconds())
        dia += timedelta(days=1)
    return round(total / 60)


def _h_min(m: int | None) -> str:
    """171 -> "2 h 51 min"; 0 -> "0 min"; em horas mesmo passando de um dia (as horas solares de vários dias)."""
    if m is None:
        return "—"
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h" + (f" {m % 60} min" if m % 60 else "")


def sem_protecao(rel: list[dict], partes: list[dict]) -> int:
    """Os desligamentos sem proteção atuada: a geração parou e o COS não registrou proteção nenhuma (o inversor, a cabine
    que caiu sem o relé). A perda de comunicação (a geração não para) e a manutenção programada não contam (14/11/2026,
    Levi: "Sem proteção atuada. Quando for desligamento")."""
    return sum(1 for x, p in zip(rel, partes) if x.get("parou") and not protecoes_do_texto(x.get("protecoes"))
               and not (p.get("rotulo") or "").startswith("Manutenção"))


def _contagem_combinacoes(rel: list[dict]) -> list[tuple[tuple, int]]:
    """[((códigos), em quantas paradas atuou exatamente esta combinação)], a maior primeiro; no empate, a de menos
    proteções e depois o código. Cada parada conta uma vez só (14/11/2026, Levi: "para esse caso aí de ser 2 ao mesmo
    tempo, incluir uma linha [...] bota 27 e 59 [...] subtensão e sobretensão [...] as paradas bota 3")."""
    conta = collections.Counter(tuple(sorted(protecoes_do_texto(x.get("protecoes")), key=int)) for x in rel)
    conta.pop((), None)
    return sorted(conta.items(), key=lambda kv: (-kv[1], len(kv[0]), [int(c) for c in kv[0]]))


def _e(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _grafico_protecoes(rel: list[dict], partes: list[dict], e: dict) -> list:
    """As proteções que atuaram, uma linha por combinação (a 27 sozinha, a 59 sozinha, a 27 e a 59 juntas), em barras
    verdes, até 6 linhas; e os desligamentos sem proteção atuada numa linha âmbar, à parte. Cada parada entra numa linha
    só, então as linhas somam as paradas com a geração parada."""
    conta = _contagem_combinacoes(rel)[:6]
    sem = sem_protecao(rel, partes)
    if not conta and not sem:
        return []
    maior = max([n for _c, n in conta] + [sem])

    def barra(n, cor):
        b = Drawing(60 * mm, 8)
        b.add(Rect(0, 1, 60 * mm, 6, fillColor=FUNDO, strokeColor=None))
        b.add(Rect(0, 1, 60 * mm * n / maior, 6, fillColor=cor, strokeColor=None))
        return b
    linhas = []
    for cods, n in conta:
        nomes = [PROTECAO_NOME.get(c, f"proteção {c}") for c in cods]
        nomes = [nomes[0]] + [x.lower() for x in nomes[1:]]
        linhas.append([_e(list(cods)), _e(nomes), str(n), barra(n, VERDE)])
    if sem:
        cor = _cor("alerta")
        linhas.append(["—", Paragraph(f'<font color="{cor}"><b>Sem proteção atuada</b></font>', e["cel_c"]),
                       Paragraph(f'<font color="{cor}"><b>{sem}</b></font>', e["cel_c"]), barra(sem, TOM["alerta"])])
    t = _tabela(e, ["Código", "Proteção", "Paradas", ""], linhas, [16, 48, 18, 96], centro=(0, 1, 2), cab_centro=True)
    if sem:
        # o destaque da linha: o fundo âmbar-claro (o mesmo da parada em alerta)
        t.setStyle(TableStyle([("BACKGROUND", (0, len(linhas)), (-1, len(linhas)), _TINTA_PARADA["alerta"]),
                               ("LINEABOVE", (0, len(linhas)), (-1, len(linhas)), 0.8, MUDO)]))
    # sem a nota embaixo (14/11/2026, Levi: "esse textinho aí debaixo do gráfico de paradas pode tirar")
    return [Paragraph(_t("Proteções que mais atuaram"), e["sub_secao"]), t, Spacer(1, 5 * mm)]


# de onde vem o dado de cada tema (as telas donas, `dados`)
FONTES = {"perf": "geração, meta e PR do Gerencial da Grid Co.; disponibilidade e eventos de parada do sistema de "
                  "manutenção (Fracttal)",
          "religamentos": "paradas e religamentos registrados pelo Centro de Operações (COS) da Grid Co.",
          "rondas": "rondas do App de Campo",
          "manut": "tarefas executadas pelo App de Campo; ordens de serviço e zeladoria do sistema de manutenção (Fracttal)",
          "chamados": "chamados de garantia do sistema de manutenção (Fracttal)"}


def gerar(d: dict, temas=CHAVES_TEMAS, gerado_em: str = "", campos=None) -> bytes:
    """O PDF: a faixa navy com o logo, a usina e o mês, os números do mês, o resumo e um tema por seção. `campos` = os
    campos escolhidos na janela (`campos_do_pedido`; None = todos): o campo desligado não se desenha, e o tema sem
    nenhum campo ligado não abre seção."""
    campos = CHAVES_CAMPOS if campos is None else tuple(campos)
    e = _estilos()
    buf = io.BytesIO()
    periodo = (f"{d['ini'].day} a {d['fim'].day} de {d['mes_txt']}" if d["fim"] >= d["ini"] else d["mes_txt"])
    titulo_pdf = f"Relatório da usina {d['usina']} · {d['mes_txt']}"

    def pagina(c, doc):
        w, h = A4
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, h - 20 * mm, w, 20 * mm, fill=1, stroke=0)
        c.setFillColor(VERDE)
        c.rect(0, h - 20.8 * mm, w, 0.8 * mm, fill=1, stroke=0)
        if LOGO.exists():
            try:
                c.drawImage(str(LOGO), 16 * mm, h - 13.4 * mm, width=34 * mm, height=6 * mm, mask="auto",
                            preserveAspectRatio=True, anchor="w")
            except Exception:       # noqa: BLE001 — sem o logo, segue o texto
                pass
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 8.5)
        c.drawRightString(w - 16 * mm, h - 9 * mm, "Relatório mensal da usina")
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(VERDE)
        c.drawRightString(w - 16 * mm, h - 14.5 * mm, d["mes_txt"].capitalize())
        c.setStrokeColor(LINHA)
        c.setLineWidth(0.5)
        c.line(16 * mm, 13 * mm, w - 16 * mm, 13 * mm)
        c.setFillColor(MUDO)
        c.setFont("Helvetica", 7.5)
        c.drawString(16 * mm, 9 * mm, f"Grid Co. · {d['usina']} · gerado em {gerado_em} (horário de Brasília)")
        c.drawRightString(w - 16 * mm, 9 * mm, f"Página {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=28 * mm,
                            bottomMargin=19 * mm, title=titulo_pdf, author="Grid Co.")
    onde = " · ".join(v for v in (d["cliente"], f"{d['cidade']}/{d['uf']}" if d["cidade"] else d["uf"],
                                  f"{_br(d['potencia_mwp'], 2)} MWp" if d["potencia_mwp"] else "") if v)
    story = [Paragraph(_t(d["usina"]), e["titulo"]), Paragraph(_t(onde), e["sub"]),
             Paragraph(_t(f"Período: {periodo}" + (" (mês em andamento, até ontem)" if d["corrente"] else "")), e["sub"]),
             Spacer(1, 6 * mm)]
    if "perf" in temas and "perf_numeros" in campos:
        story += [_kpis(d, e), Spacer(1, 5 * mm)]
    frases = _resumo(d, temas) if "resumo" in campos else []
    if frases:
        story += [Paragraph("Resumo do mês", e["sub_secao"])]
        story += [Paragraph("• " + _t(f), e["base"]) for f in frases]
    secoes = {"perf": ("Performance e disponibilidade", _perf), "religamentos": ("Paradas e religamentos", _religamentos),
              "rondas": ("Rondas e limpeza", _rondas),
              "manut": ("Manutenção", _manut), "chamados": ("Chamados de garantia", _chamados)}
    for k in temas:
        titulo, f = secoes[k]
        if k in d["erros"]:
            corpo = [_sem(e, f"Não consegui ler os dados deste tema ({d['erros'][k]}): ele ficou de fora.")]
        else:
            corpo = f(d, e, campos)
        if corpo:
            story += _secao(titulo, e) + corpo
    # as fontes só dos temas que entraram (14/11/2026, Levi, no PDF só de religamentos: "a fonte está vindo do próprio
    # COS mesmo, né? Não sei porque você botou meta, PR, gerencial"): a linha era uma só para o relatório inteiro
    fontes = [FONTES[k] for k in temas_dos_campos(temas, campos) if k in FONTES]
    if fontes:
        solar = ("O tempo indisponível das paradas conta só o período solar, das 6h às 18h: a parte da parada fora "
                 "desse horário não entra. " if "religamentos" in temas_dos_campos(temas, campos)
                 and "religamentos_lista" in campos and d.get("religamentos") else "")
        story += [Spacer(1, 8 * mm),
                  Paragraph(("Fontes: " if len(fontes) > 1 else "Fonte: ") + "; ".join(fontes).rstrip(".") + ". " + solar
                            + ("O mês em andamento é parcial: os números mudam até o mês fechar." if d["corrente"] else ""),
                            e["mudo"])]
    doc.build(story, onFirstPage=pagina, onLaterPages=pagina)
    return buf.getvalue()
