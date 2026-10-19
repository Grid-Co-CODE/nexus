"""O relatório dos extintores em Excel (Segurança · HSEQ).

A TST, 19/10/2026, depois do relatório por cliente em PDF: "e excel tbm? pq às vezes o cliente pede". O mesmo recorte do
PDF (a rota `extintores_planilha` usa o `_do_relatorio` da torre: os filtros da tela, a usina ou o cliente da linha), em
planilha para o cliente filtrar e somar:
- aba "Extintores": UMA linha por extintor, na ordem da tabela da tela (o cliente, a usina e o mais grave primeiro:
  `extintores.por_cliente`), com as mesmas contas (situação, sem atualização, status da TST). A conferência vai como
  data de verdade (o Excel ordena e filtra por ela); as validades vão como a etiqueta diz ("08/2026", "2027", "Sem
  data"), porque a etiqueta é o dado: o dia em que ela vence também vai, à parte, como data;
- aba "Não reconhecidos": os que a equipe não achou na usina, quando o recorte os leva (a regra do PDF);
- em cima da tabela, o título, quando foi gerado e os filtros, como no PDF.
Sem cor de fundo nem fórmula: o cliente abre em qualquer programa de planilha. A pessoa vai pelo nome (como no PDF),
nunca pelo HMAC.
"""
import io
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from . import extintores as EXT

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DATA = "DD/MM/YYYY"
CARGA = {"CARREGADO": "carregado", "SEM_CARGA": "sem carga", "SOBRECARGA": "sobrecarga"}
# (cabeçalho, largura, valor) de cada coluna da aba Extintores
COLUNAS = (
    ("Cliente", 18, lambda x, u: u["cliente"]),
    ("Usina", 28, lambda x, u: x["usina"]),
    ("Responsável", 22, lambda x, u: "" if u["responsavel"] == EXT.SEM_VALOR["responsavel"] else u["responsavel"]),
    ("Técnicos", 30, lambda x, u: ", ".join(u["tecnicos"])),
    ("Extintor", 10, lambda x, u: x["ext"]),
    ("Código", 28, lambda x, u: x["codigo"]),
    ("Classe", 12, lambda x, u: x.get("classe") or ""),
    ("Peso (kg)", 10, lambda x, u: x.get("peso")),
    ("Local", 20, lambda x, u: x.get("local") or ""),
    ("Posição", 12, lambda x, u: (x.get("posicao") or "").lower()),
    ("Ativo no Fracttal", 24, lambda x, u: x.get("ativo") or ""),
    ("Situação", 16, lambda x, u: EXT.SITUACOES[x["situacao"]][0]),
    ("Validade da recarga", 12, lambda x, u: x["val2"]),
    ("Recarga vence em", 12, lambda x, u: x.get("fim2")),
    ("Validade do hidrostático", 12, lambda x, u: x["val3"]),
    ("Hidrostático vence em", 12, lambda x, u: x.get("fim3")),
    ("Última conferência", 12, lambda x, u: x["conferencia"]),
    ("Sem atualização há mais de 30 dias", 12, lambda x, u: "sim" if x["sem_atualizacao"] else "não"),
    ("Origem da conferência", 14, lambda x, u: x.get("origem_conferencia") or ""),
    ("Conferido por", 22, lambda x, u: x.get("conferido_por") or ""),
    ("Carga", 12, lambda x, u: CARGA.get(x.get("carga") or "", "")),
    ("Itens com NÃO", 22, lambda x, u: ", ".join(x.get("itens_nao") or [])),
    ("Status da TST", 14, lambda x, u: (EXT.STATUS_TST.get(x.get("status")) or ("sem conferência",))[0]),
    ("Motivo do status", 40, lambda x, u: x.get("motivo") or ""),
)
COLUNAS_NR = (
    ("Cliente", 18, lambda x: EXT.valor_do_filtro(x, "cliente")),
    ("Usina", 28, lambda x: x["usina"]),
    ("Extintor", 10, lambda x: x["ext"]),
    ("Código", 28, lambda x: x["codigo"]),
    ("Local", 20, lambda x: x.get("local") or ""),
    ("Não reconhecido em", 12, lambda x: x["nao_reconhecido"]),
    ("Marcado por", 22, lambda x: x.get("nao_reconhecido_por") or ""),
    ("Conferência antes", 12, lambda x: x["conferencia"]),
)


def _aba(ws, titulo: str, topo: list[str], colunas, linhas) -> None:
    """O título e as linhas de cima, o cabeçalho (negrito, congelado, com o filtro do Excel) e as linhas."""
    ws.append([titulo])
    ws["A1"].font = Font(bold=True, size=14)
    for t in topo:
        ws.append([t])
    ws.append([])
    cab = len(topo) + 3
    ws.append([c[0] for c in colunas])
    for i, (_rot, larg, _f) in enumerate(colunas, 1):
        cel = ws.cell(row=cab, column=i)
        cel.font = Font(bold=True)
        cel.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[get_column_letter(i)].width = larg
    for valores in linhas:
        ws.append(valores)
        for cel in ws[ws.max_row]:
            if isinstance(cel.value, date):
                cel.number_format = DATA
    ws.freeze_panes = ws.cell(row=cab + 1, column=1)
    ws.auto_filter.ref = f"A{cab}:{get_column_letter(len(colunas))}{max(ws.max_row, cab)}"


def gerar(lista, *, filtros_tela: list[str], hoje: date, gerado_em: str, nao_reconhecidos=()) -> bytes:
    """O .xlsx: a aba Extintores e, se o recorte os leva, a aba Não reconhecidos. `lista` = os extintores já
    filtrados (os da tabela da tela)."""
    topo = [f"Gerado em {gerado_em} · situação no dia {hoje:%d/%m/%Y}",
            "Filtros: " + (" · ".join(filtros_tela) if filtros_tela else "nenhum (todos os extintores)")]
    wb = Workbook()
    ws = wb.active
    ws.title = "Extintores"
    linhas = [[f(x, u) for _r, _l, f in COLUNAS]
              for c in EXT.por_cliente(lista) for u in c["usinas"] for x in u["extintores"]]
    _aba(ws, "Relatório de extintores", topo + [f"{len(linhas)} extintor{'es' if len(linhas) != 1 else ''}"],
         COLUNAS, linhas)
    if nao_reconhecidos:
        nr = wb.create_sheet("Não reconhecidos")
        _aba(nr, "Extintores não reconhecidos em campo",
             topo + ["A equipe não achou estes extintores na usina; ficam fora das contas até a TST conferir o cadastro."],
             COLUNAS_NR, [[f(x) for _r, _l, f in COLUNAS_NR] for x in nao_reconhecidos])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
