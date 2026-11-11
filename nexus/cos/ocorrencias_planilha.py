"""As Ocorrências do COS em Excel (11/11/2026).

O dono, olhando o CSV da tela: "melhora a exportação do CSV, está muito feia". O CSV abria no Excel com tudo do mesmo
jeito: o código do veredito ("no_prazo", "nao_medido"), o texto da etapa misturado com o caminho ("flash · em 6 min"),
as notas numa linha só e as horas como texto. Aqui sai uma planilha de verdade, no padrão do relatório de extintores do
HSEQ (`nexus/hseq/planilha.py`):
- em cima, o título, quando foi gerada, o período, o cliente e os filtros — o mesmo recorte da tela;
- o cabeçalho em negrito, congelado e com o filtro do Excel; a largura de cada coluna, e as de texto longo quebrando;
- as horas como DATA (o Excel ordena e filtra por elas), em Brasília, sem fuso (a planilha não guarda fuso);
- o veredito de cada prazo em palavras ("No prazo", "Fora do prazo"), e os minutos até cumprir como NÚMERO, contados do
  mesmo relógio da tela (`ocorrencias.CONTA_DE`);
- a descrição e as notas, uma nota por linha dentro da célula.
Sem cor de fundo nem fórmula (o texto que começa com "=" vai como texto). Os dois nomes de pessoa são os da tela (quem
abriu a OS e o técnico).
"""
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from . import andamento as AND
from . import ocorrencias as OC

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FORMATO_HORA = "DD/MM/YYYY HH:MM"

# O veredito de cada etapa (`ocorrencias.Etapa.estado`) em palavras, como a pessoa lê.
VEREDITO = {
    "no_prazo": "No prazo",
    "fora": "Fora do prazo",
    "pendente": "Correndo o prazo",
    "atrasada": "Atrasada (ainda aberta)",
    "nao_informado": "Não avisado",
    "so_automatico": "Só o escalonamento automático",
    "nao_precisou": "Não precisou",
    "sem_campo": "Normalizada sem campo",
    "nao_medido": "Não se mede",
}


def _hora(iso) -> datetime | None:
    """O instante do Andamento em Brasília, SEM fuso (o Excel não guarda fuso; a tela também mostra Brasília)."""
    t = AND.instante(iso)
    return t.replace(tzinfo=None) if t else None


def _minutos(de, ate) -> int | None:
    a, b = AND.instante(de), AND.instante(ate)
    return round((b - a).total_seconds() / 60) if a and b else None


def _do_cos(o: dict, ate) -> int | None:
    """Os minutos de quando o COS viu (o relógio dos prazos, `ocorrencias.quando_o_cos_viu`) até `ate`."""
    viu, _base = OC.quando_o_cos_viu(o)
    b = AND.instante(ate)
    return round((b - viu).total_seconds() / 60) if viu and b else None


def _aviso(o: dict) -> dict | None:
    return o.get("cliente_informado")


def _acionamento(o: dict) -> str | None:
    return (o.get("campo") or {}).get("acionado_em")


# (cabeçalho, largura, valor(linha)) — a ordem é a da leitura: quem, o quê, quando, os prazos, o que aconteceu.
COLUNAS = (
    ("Cliente", 14, lambda x: x.cliente),
    ("OS", 9, lambda x: int(x.os) if x.os.isdigit() else x.os),
    ("Usina", 26, lambda x: x.usina),
    ("Equipamentos", 22, lambda x: x.equipamentos),
    ("Falha", 22, lambda x: x.tipo),
    ("Severidade", 10, lambda x: x.severidade),
    ("Estado", 16, lambda x: x.estado),
    ("Aberta", 8, lambda x: "sim" if x.o.get("aberta") else "não"),
    ("Início da falha", 16, lambda x: _hora(x.o.get("inicio"))),
    ("COS viu", 16, lambda x: _hora(x.o.get("detectada_em"))),
    ("Registrada", 16, lambda x: _hora(x.o.get("registrada_em"))),
    ("OS aberta", 16, lambda x: _hora(x.o.get("os_aberta_em"))),
    ("Cliente informado", 16, lambda x: _hora((_aviso(x.o) or {}).get("em"))),
    ("Informado por", 12, lambda x: (_aviso(x.o) or {}).get("por") or ""),
    # os prazos contam de quando o COS viu (11/11/2026); a coluna diz qual relógio valeu na linha
    ("Prazos contam", 18, lambda x: OC.BASES.get(x.relogio, "")),
    ("Minutos até o COS ver", 11, lambda x: _minutos(x.o.get("inicio"), x.o.get("detectada_em"))),
    ("Minutos até informar", 11, lambda x: _do_cos(x.o, (_aviso(x.o) or {}).get("em"))),
    ("Prazo do aviso (min)", 9, lambda x: OC.prazo_do_aviso(x.o)),
    ("Aviso no prazo?", 18, lambda x: VEREDITO.get(x.etapas["informado"].estado, x.etapas["informado"].estado)),
    ("Campo acionado", 16, lambda x: _hora(_acionamento(x.o))),
    ("Minutos até o campo", 11, lambda x: _do_cos(x.o, _acionamento(x.o))),
    ("Campo no prazo? (30 min)", 18, lambda x: VEREDITO.get(x.etapas["campo"].estado, x.etapas["campo"].estado)),
    ("Normalizada (volta)", 16, lambda x: _hora((x.o.get("normalizada") or {}).get("fim"))),
    ("Encerrada", 16, lambda x: _hora(x.o.get("encerrada_em"))),
    ("Causa", 26, lambda x: (x.o.get("causa") or {}).get("rotulo") or ""),
    ("Ação", 20, lambda x: x.o.get("acao") or ""),
    ("Informe", 24, lambda x: x.o.get("informe") or ""),
    ("Aberta por (operador)", 20, lambda x: x.o.get("os_aberta_por") or ""),
    ("Técnico", 20, lambda x: x.o.get("tecnico") or ""),
    ("Status no Fracttal", 14, lambda x: OC.status_da_os(x.o)),
    ("% concluída", 9, lambda x: (x.o.get("os_fracttal") or {}).get("concluida_pct")),
    ("Descrição da ocorrência", 60, lambda x: x.o.get("descricao") or ""),
    ("Notas", 60, lambda x: "\n".join(x.o.get("notas") or [])),
)
# As colunas de texto longo quebram a linha dentro da célula.
QUEBRA = {"Equipamentos", "Causa", "Informe", "Descrição da ocorrência", "Notas"}


def gerar(p, *, titulo: str, topo: list[str]) -> bytes:
    """O .xlsx de uma aba, "Ocorrências", com as linhas da tabela da tela (`p.itens`, já filtradas e na ordem dela)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Ocorrências"
    ws.append([titulo])
    ws["A1"].font = Font(bold=True, size=14)
    for t in topo:
        ws.append([t])
    ws.append([])
    cab = len(topo) + 3
    ws.append([c[0] for c in COLUNAS])
    for i, (rotulo, largura, _f) in enumerate(COLUNAS, 1):
        cel = ws.cell(row=cab, column=i)
        cel.font = Font(bold=True)
        cel.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[get_column_letter(i)].width = largura
    for x in p.itens:
        ws.append([f(x) for _r, _l, f in COLUNAS])
        for i, cel in enumerate(ws[ws.max_row], 1):
            rotulo = COLUNAS[i - 1][0]
            if isinstance(cel.value, str) and cel.value.startswith(("=", "+", "-", "@")):
                cel.data_type = "s"          # texto digitado não vira fórmula
            elif isinstance(cel.value, datetime):
                cel.number_format = FORMATO_HORA
            cel.alignment = Alignment(vertical="top", wrap_text=rotulo in QUEBRA)
    ws.freeze_panes = ws.cell(row=cab + 1, column=1)
    ws.auto_filter.ref = f"A{cab}:{get_column_letter(len(COLUNAS))}{max(ws.max_row, cab)}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
