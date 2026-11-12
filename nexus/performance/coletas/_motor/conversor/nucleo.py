# -*- coding: utf-8 -*-
"""Núcleo do Conversor Grid Co.: arquivo de entrada, leitura do BD (só leitura, sempre de uma CÓPIA) e o contrato
dos leitores.

Pedido do Levi (10/11/2026): "um app de conversão de dados, começamos com Sal mas a ideia é pegar tudo o que você
converte e deixar independente para o app reconhecer, pega um padrão da tabela, identifica a UFV e devolve o excel já
convertido e pronto para colar no BD". Cada fonte é um LEITOR (pasta leitores/) que sabe duas coisas: reconhecer o
arquivo pelo conteúdo e ler os valores por dia. As regras do BD (o que entra, o que fica de fora, como sai a planilha)
ficam em montagem.py e valem para todas as fontes.

O app NUNCA grava no BD: lê uma cópia temporária para saber o que já está preenchido e devolve uma planilha para colar.
"""
import collections
import csv
import datetime as dt
import io
import os
import re
import shutil
import tarfile
import tempfile
import unicodedata
import warnings
import zipfile

import openpyxl

# relatório de portal vem sem estilo padrão e o openpyxl avisa; no .exe sem console o aviso não tem onde sair
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

BD_PERFORMANCE = "BD_Performance"
BD_THOPEN = "BD_Thopen"
_ONEDRIVE = os.path.join(os.path.expanduser("~"), "OneDrive - GRID CO")
BD_PADRAO = {
    BD_PERFORMANCE: os.path.join(_ONEDRIVE, "Área de Trabalho", "Grid Co_ - 4. O&M", "17. Backoffice",
                                 "4. Gestão à vista", "1. Banco de Dados", "BD_Performance.xlsx"),
    BD_THOPEN: os.path.join(_ONEDRIVE, "Grid Co_ - 17. Acesso Externo Thopen", "1. Registro usinas Thopen",
                            "BD_Thopen.xlsx"),
}
# Cada pessoa sincroniza as bibliotecas num lugar: o Levi em "OneDrive - GRID CO\Área de Trabalho\Grid Co_ - 4. O&M", a
# Lara em "OneDrive - GRID CO\Shortcuts\GRID CO_ - 4. O&M" (11/11/2026). Com só o caminho do Levi fixo, no PC dela o
# app não achava o BD nem a pasta das versões, e a atualização nunca aparecia ("só aparece 1.0.0"). Por isso a pasta da
# biblioteca é procurada pelo FIM do nome, poucos níveis abaixo de cada raiz do OneDrive.
_BIBLIOTECAS = {
    BD_PERFORMANCE: ("4. o&m", ("17. Backoffice", "4. Gestão à vista", "1. Banco de Dados", "BD_Performance.xlsx")),
    BD_THOPEN: ("17. acesso externo thopen", ("1. Registro usinas Thopen", "BD_Thopen.xlsx")),
}


def raizes_onedrive():
    out = []
    for v in (os.environ.get("OneDriveCommercial"), os.environ.get("OneDrive"), _ONEDRIVE):
        if v and os.path.isdir(v) and os.path.normcase(v) not in [os.path.normcase(x) for x in out]:
            out.append(v)
    import glob
    for v in glob.glob(os.path.join(os.path.expanduser("~"), "OneDrive - *")):
        if os.path.isdir(v) and os.path.normcase(v) not in [os.path.normcase(x) for x in out]:
            out.append(v)
    return out


def achar_biblioteca(fim, prof=3, raizes=None):
    """A pasta cujo nome termina com `fim` (sem caixa), até `prof` níveis abaixo das raízes do OneDrive (busca em
    largura: a mais rasa vence). Só lista pastas; nenhum arquivo é baixado da nuvem."""
    fim = fim.lower()
    for raiz in (raizes if raizes is not None else raizes_onedrive()):
        fila = [(raiz, 0)]
        while fila:
            p, d = fila.pop(0)
            try:
                with os.scandir(p) as it:
                    subs = sorted((e for e in it if e.is_dir()), key=lambda e: e.name.lower())
            except OSError:
                continue
            for e in subs:
                if e.name.lower().rstrip().endswith(fim):
                    return e.path
            if d + 1 < prof:
                fila.extend((e.path, d + 1) for e in subs)
    return None


def achar_bds(atuais=None, raizes=None):
    """Os caminhos dos BDs: o atual quando existe; senão o da biblioteca achada no OneDrive desta pessoa."""
    out = dict(BD_PADRAO)
    out.update({k: v for k, v in (atuais or {}).items() if v})
    for destino, (fim, rel) in _BIBLIOTECAS.items():
        if out.get(destino) and os.path.isfile(out[destino]):
            continue
        lib = achar_biblioteca(fim, raizes=raizes)
        if lib and os.path.isfile(os.path.join(lib, *rel)):
            out[destino] = os.path.join(lib, *rel)
    return out


ARQUIVADOS = (".zip", ".tar", ".tar.gz", ".tgz", ".gz")
# Usina que o app não sabe: converte mesmo assim (Levi, 10/11/2026: "quando não sabe a usina não precisa apontar
# usina") — os valores vão por dia numa aba "Sem usina · <arquivo>" da planilha, sem comparar com o BD, e a pessoa cola
# onde quiser. Canal de irradiação sem nome claro de POA ou GHI sai como ETM1/ETM2 ("quando não sabe o que é IPOA e o
# que é GHI pode ficar como ETM1 e ETM2") e também vai para a lista solta: não existe coluna ETM1 no BD.
SEM_USINA = "Sem usina"
ETM_SOLTAS = ("ETM1", "ETM2")


# ---------------------------------------------------------------- texto, número e data
def norm(s):
    """minúsculo, sem acento, espaços colapsados — para comparar nome de usina, cabeçalho e ponto."""
    s = unicodedata.normalize("NFKD", str(s if s is not None else "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def norm_cab(s):
    """cabeçalho de portal que grava os acentos quebrados: o mensal INV em .csv vem com "Hor\ufffdrio" e
    "Gera\ufffd\ufffdo de energia(kWh)" (o caractere de substituição está no próprio arquivo, 10/11/2026). Cada letra
    perdida vira "_" — compare com regex que aceite a letra ou o "_" (ex.: r"hor[a_]rio")."""
    return norm(str(s if s is not None else "").replace("\ufffd", "_"))


def norm_col(s):
    """cabeçalho do BD comparável: 'Inversor 6,2' (Cascavel) = 'Inversor 6.2'; 'inversor 10' = 'Inversor 10'."""
    return re.sub(r"(\d),(\d)", r"\1.\2", norm(s))


def num(v):
    """número de célula ou de texto ('1.234,5', '5,969', '7.48'); None se não for número."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("\xa0", "")
    if not s or s in ("-", "--", "N/A", "n/a", "NaN", "nan"):
        return None
    # ponto sozinho é DECIMAL: o EMI da Huawei grava "5.969" (kWh/m²) e ler como milhar dava 5969 (10/11/2026).
    # Milhar com ponto só quando vem com vírgula decimal ("1.234,5") ou com mais de um ponto ("1.234.567").
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+,\d+", s) or re.fullmatch(r"-?\d{1,3}(\.\d{3}){2,}", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+\.\d+", s):           # 1,234.5
        s = s.replace(",", "")
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def data_de(v):
    """date de datetime, date, '2026-10-01[ 00:00]', '01/10/2026', '01-10-2026', '2026/10/01'."""
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v or "").strip()
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def datahora_de(v):
    """datetime de datetime ou de texto com hora ('2026-10-01 13:05[:00]', '01/10/2026 13:05')."""
    if isinstance(v, dt.datetime):
        return v
    s = str(v or "").strip()
    d = data_de(s)
    if not d:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s[8:])
    if not m:
        return dt.datetime(d.year, d.month, d.day)
    return dt.datetime(d.year, d.month, d.day, int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def br(d):
    return d.strftime("%d/%m/%Y") if d else "-"


# ---------------------------------------------------------------- arquivo de entrada
class Arquivo:
    """Um arquivo solto (xlsx, xls, csv, txt...). Arquivo compactado é aberto pelo núcleo e cada arquivo de dentro vira
    um Arquivo com `origem` = nome do pacote (a usina às vezes só aparece no nome da pasta ou do zip, ex.
    PerformanceData_<SN do SmartLogger>_...zip)."""

    def __init__(self, caminho, origem=""):
        self.caminho = caminho
        self.nome = os.path.basename(caminho)
        self.origem = origem
        n = self.nome.lower()
        self.ext = ".tar.gz" if n.endswith(".tar.gz") else os.path.splitext(n)[1]
        self._planilhas = None
        self._texto = None

    @property
    def dica(self):
        """origem + nome, normalizado — para leitor que reconhece usina pelo nome do arquivo ou da pasta."""
        return norm("%s %s" % (self.origem, self.nome))

    @property
    def tamanho(self):
        try:
            return os.path.getsize(self.caminho)
        except OSError:
            return 0

    # -- texto (csv/txt)
    def texto(self):
        if self._texto is None:
            with open(self.caminho, "rb") as f:
                b = f.read()
            for enc in ("utf-8-sig", "cp1252"):
                try:
                    self._texto = b.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                self._texto = b.decode("latin-1", "replace")
        return self._texto

    def cabeca(self, n=40):
        """primeiras n linhas do texto (para reconhecer sem ler um CSV de 15 MB inteiro)."""
        if self._texto is not None:
            return self._texto.splitlines()[:n]
        out = []
        with open(self.caminho, "rb") as f:
            for _ in range(n):
                l = f.readline()
                if not l:
                    break
                out.append(l)
        b = b"".join(out)
        for enc in ("utf-8-sig", "cp1252"):
            try:
                return b.decode(enc).splitlines()
            except UnicodeDecodeError:
                continue
        return b.decode("latin-1", "replace").splitlines()

    def linhas_csv(self, delimitador=None):
        """lista de listas; delimitador adivinhado entre ; , e tab pela primeira linha com conteúdo."""
        t = self.texto()
        if delimitador is None:
            # conta nas 20 primeiras linhas, não só na primeira: o mensal INV em .csv começa com um título sem
            # separador ("Relatorio mensal INV_Mensal_202611") e o palpite pela 1ª linha dava ";" (10/11/2026)
            amostra = "\n".join(t.splitlines()[:20])
            delimitador = max((";", ",", "\t"), key=amostra.count)
        return list(csv.reader(io.StringIO(t), delimiter=delimitador))

    # -- planilhas (xlsx/xlsm/xls/csv)
    def planilhas(self):
        """[(nome da aba, [linhas como tuplas de valores])]. CSV vira uma aba só."""
        if self._planilhas is not None:
            return self._planilhas
        out = []
        if self.ext in (".xlsx", ".xlsm"):
            # read_only não serve: portal grava a dimensão errada e a leitura para na linha 1
            wb = openpyxl.load_workbook(self.caminho, data_only=True)
            try:
                for ws in wb.worksheets:
                    out.append((ws.title, [tuple(r) for r in ws.iter_rows(values_only=True)]))
            finally:
                wb.close()
        elif self.ext == ".xls":
            out = _ler_xls(self.caminho)
        elif self.ext in (".csv", ".txt"):
            out = [(self.nome, [tuple(r) for r in self.linhas_csv()])]
        self._planilhas = out
        return out


def _ler_xls(caminho):
    """.xls BIFF (relatório NeoWind da Sunpower): xlrd. Alguns portais gravam HTML com extensão .xls — aí o openpyxl
    também não abre; devolve vazio e o leitor diz que não reconheceu."""
    try:
        import xlrd
    except ImportError:
        return []
    try:
        wb = xlrd.open_workbook(caminho)
    except Exception:
        return []
    out = []
    for sh in wb.sheets():
        linhas = []
        for i in range(sh.nrows):
            r = []
            for c in sh.row(i):
                v = c.value
                if c.ctype == xlrd.XL_CELL_DATE:
                    try:
                        v = xlrd.xldate.xldate_as_datetime(v, wb.datemode)
                    except Exception:
                        pass
                elif c.ctype == xlrd.XL_CELL_EMPTY:
                    v = None
                r.append(v)
            linhas.append(tuple(r))
        out.append((sh.name, linhas))
    return out


def expandir(caminhos, pasta_tmp):
    """Pastas viram os arquivos de dentro; pacote (.zip/.tar.gz) é extraído em pasta_tmp e cada arquivo de dentro vira
    um Arquivo com origem = nome do pacote. Devolve [(caminho original, [Arquivo...])] — um item por coisa solta na tela
    (o cartão é do pacote, não de cada arquivo de dentro)."""
    itens = []
    for c in caminhos:
        if os.path.isdir(c):
            for raiz, _, nomes in os.walk(c):
                for n in sorted(nomes):
                    p = os.path.join(raiz, n)
                    if _ignorar(n):
                        continue
                    itens.append((p, _abrir(p, pasta_tmp, origem=os.path.basename(raiz))))
        elif os.path.isfile(c) and not _ignorar(os.path.basename(c)):
            itens.append((c, _abrir(c, pasta_tmp, origem=os.path.basename(os.path.dirname(c)))))
    return itens


def _ignorar(nome):
    n = nome.lower()
    return n.startswith(("~$", ".")) or n.startswith("para colar no bd_") or n in ("desktop.ini", "thumbs.db")


def _abrir(caminho, pasta_tmp, origem="", nivel=0):
    n = caminho.lower()
    arq = Arquivo(caminho, origem=origem)
    if nivel > 2 or not n.endswith(ARQUIVADOS):
        return [arq]
    destino = tempfile.mkdtemp(dir=pasta_tmp)
    try:
        if n.endswith(".zip"):
            # extractall dá a data da extração; a data de DENTRO do zip é a da exportação e é ela que a sessão usa
            # para tirar o dia ainda aberto (PerformanceData_..._20261106133731.zip traz o 06/11 pela metade)
            import time
            with zipfile.ZipFile(caminho) as z:
                for zi in z.infolist():
                    p = z.extract(zi, destino)
                    if not zi.is_dir():
                        try:
                            t = time.mktime(zi.date_time + (0, 0, -1))
                            os.utime(p, (t, t))
                        except (OverflowError, ValueError, OSError):
                            pass
        elif n.endswith((".tar", ".tar.gz", ".tgz")):
            with tarfile.open(caminho) as t:
                t.extractall(destino, filter="data")
        elif n.endswith(".gz"):
            import gzip
            with gzip.open(caminho, "rb") as g, open(os.path.join(destino, os.path.basename(caminho)[:-3]), "wb") as f:
                shutil.copyfileobj(g, f)
    except Exception:
        return [arq]                                              # pacote quebrado: o cartão diz "não reconheci"
    out = []
    origem2 = ("%s %s" % (origem, os.path.basename(caminho))).strip()
    for raiz, _, nomes in os.walk(destino):
        for m in sorted(nomes):
            if not _ignorar(m):
                out += _abrir(os.path.join(raiz, m), pasta_tmp, origem=origem2, nivel=nivel + 1)
    return out or [arq]


# ---------------------------------------------------------------- BD (só leitura)
_ALIAS = {
    "ipoa": lambda h: h.startswith("ipoa") and "def" not in h,
    "ghi": lambda h: h.startswith("ghi"),
    "temperatura": lambda h: h == "temperatura" or h.startswith("temp mod"),
    "energia produzida": lambda h: h.startswith("energia produzida"),
    "multimedidor": lambda h: h.startswith("multimedidor"),
    "chuva": lambda h: h.startswith("chuva") or h.startswith("pluviometro"),
}


class AbaBD:
    def __init__(self, nome, linha_cab, cab, linhas):
        self.nome = nome
        self.linha_cab = linha_cab                 # 1-based: Sapopema (BD_Thopen) tem o cabeçalho na linha 2
        self.cab = cab
        self._ncab = [norm_col(h) for h in cab]
        self.linhas = linhas                       # {nº da linha no Excel: tupla de valores crus (fórmula = texto '=')}
        self.idata = self._ncab.index("data")
        self.datas = {}                            # {date: nº da linha}; data repetida fica a primeira
        for n, r in linhas.items():
            d = r[self.idata] if self.idata < len(r) else None
            d = d.date() if isinstance(d, dt.datetime) else d
            if isinstance(d, dt.date) and d not in self.datas:
                self.datas[d] = n

    def col(self, nome):
        """índice (0-based) da coluna pelo nome que o leitor usa. Ordem: igual; igual normalizado; apelido (IPOA,
        GHI, Temperatura, Energia Produzida...); 'Inversor 1.N' cai para 'Inversor N' (Ibaté 1 do BD_Thopen)."""
        if nome in self.cab:
            return self.cab.index(nome)
        n = norm_col(nome)
        if n in self._ncab:
            return self._ncab.index(n)
        teste = _ALIAS.get(n)
        if teste:
            for j, h in enumerate(self._ncab):
                if teste(h):
                    return j
        m = re.fullmatch(r"inversor 1\.(\d+)", n)
        if m and "inversor %d" % int(m.group(1)) in self._ncab:
            return self._ncab.index("inversor %d" % int(m.group(1)))
        return None

    def valor(self, data, j):
        n = self.datas.get(data)
        if n is None:
            return None
        r = self.linhas[n]
        return r[j] if j < len(r) else None

    def serie(self, j):
        """{date: valor cru} da coluna j."""
        return {d: (self.linhas[n][j] if j < len(self.linhas[n]) else None) for d, n in self.datas.items()}

    def colunas_inversor(self):
        return [h for h in self.cab if norm_col(h).startswith("inversor")]


class BD:
    """BD_Performance ou BD_Thopen lido de uma CÓPIA (o original pode estar aberto no Excel de alguém ou sincronizando
    no OneDrive — ler direto já devolveu meio arquivo)."""

    def __init__(self, destino, caminho):
        self.destino = destino
        self.caminho = caminho
        self.lido_em = dt.datetime.fromtimestamp(os.path.getmtime(caminho))
        self._tmp = tempfile.mkdtemp(prefix="conversor_bd_")
        self._copia = os.path.join(self._tmp, os.path.basename(caminho))
        shutil.copy2(caminho, self._copia)
        self._wb = openpyxl.load_workbook(self._copia, read_only=True)
        self._abas = {}

    def abas(self):
        return list(self._wb.sheetnames)

    def aba(self, nome):
        if nome in self._abas:
            return self._abas[nome]
        if nome not in self._wb.sheetnames:
            return None
        ws = self._wb[nome]
        linhas, cab, lcab = {}, None, None
        for n, r in enumerate(ws.iter_rows(values_only=True), 1):
            if cab is None:
                if n > 5:
                    break
                h = [norm_col(x) for x in r]
                if "data" in h:
                    cab = [str(x).strip() if x is not None else "" for x in r]
                    lcab = n
                continue
            linhas[n] = tuple(r)
        a = AbaBD(nome, lcab, cab, linhas) if cab else None
        self._abas[nome] = a
        return a

    def estilos(self, nome, r1, r2, c1, c2):
        """{(linha, col 0-based): (formato, cor do preenchimento ARGB ou None, cor da fonte ARGB ou None)} do retângulo —
        para a planilha de colar repetir a marcação que o BD já tem (amarelo de valor à mão, vermelho de falta)."""
        out = {}
        ws = self._wb[nome]
        for r in ws.iter_rows(min_row=r1, max_row=r2, min_col=c1 + 1, max_col=c2 + 1):
            for c in r:
                if not hasattr(c, "row"):
                    continue
                fill = None
                try:
                    if c.fill is not None and c.fill.fill_type == "solid":
                        fill = c.fill.fgColor.rgb if isinstance(c.fill.fgColor.rgb, str) else None
                except Exception:
                    fill = None
                fonte = None
                try:
                    fonte = c.font.color.rgb if c.font is not None and c.font.color is not None and \
                        isinstance(c.font.color.rgb, str) else None
                except Exception:
                    fonte = None
                out[(c.row, c.column - 1)] = (c.number_format, fill, fonte)
        return out

    def fechar(self):
        try:
            self._wb.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)


def vazio(v):
    return v is None or (isinstance(v, str) and not v.strip())


def formula(v):
    return isinstance(v, str) and v.startswith("=")


# ---------------------------------------------------------------- contrato dos leitores
# so_vazio=True: o valor só entra em célula VAZIA do BD, nunca troca número (nem pelo "maior"). Para fonte que mede
# outra coisa que o BD já tem na coluna — o EMI da Macaíba 1 é outro sensor: dentro de 1% do BD em só 27 de 88 dias
# (10/11/2026); trocar pelo maior misturaria os dois sensores na mesma coluna.
# confirmado: o leitor PROVOU que o valor é leitura de verdade (0 com o contador total do inversor parado no dia, mensal
# INV da Ipixuna 1 em 04/11/2026) — o "dia todo em 0 fica fora" da montagem não vale para ele
Celula = collections.namedtuple("Celula", "destino aba data coluna valor nota so_vazio confirmado")
Celula.__new__.__defaults__ = (None, False, False)


class Reconhecimento:
    """O que o leitor diz de um arquivo. Sem `usinas` e com `candidatas`, a tela pergunta "De qual usina é este
    arquivo?" (`pergunta` explica por quê) e a resposta volta no `ler(..., escolha=aba)`."""

    def __init__(self, fonte, usinas=None, candidatas=None, pergunta=None, periodo=None, estado=None, detalhe=None,
                 recusa=None):
        self.recusa = recusa                       # formato conhecido que não serve (relatório do ANO da NeoWind)
        self.fonte = fonte
        self.usinas = list(usinas or [])
        self.candidatas = list(candidatas or [])
        self.pergunta = pergunta
        self.periodo = periodo                     # (date, date) ou None
        self.estado = estado                       # o que o leitor quiser guardar entre reconhecer e ler
        self.detalhe = detalhe                     # linha curta para o cartão ("4 inversores · ETM")
        self.leitor = None                         # preenchido pelo núcleo


class Leitor:
    """Uma fonte. Subclasse define id, fonte (nome na tela), destino e os dois métodos.

    reconhecer(arq, ctx) -> Reconhecimento ou None: olha o CONTEÚDO (cabeçalho, nome dos pontos); o nome do arquivo
        só ajuda a achar a usina. Tem de ser rápido e não pode levantar exceção por arquivo de outro formato.
    ler(arq, ctx, rec, escolha=None) -> (lista de Celula, lista de avisos em texto): valores por dia; coluna pelo nome
        do cabeçalho do BD ('Inversor 1.1', 'IPOA', 'GHI', 'Temperatura', 'Energia Produzida'). Só o que o arquivo traz
        de verdade: sem dado, sem célula (nada de 0 deduzido). Dia de hoje em diante o núcleo já descarta.
    """
    id = ""
    fonte = ""
    destino = BD_PERFORMANCE

    def reconhecer(self, arq, ctx):
        return None

    def ler(self, arq, ctx, rec, escolha=None):
        return [], []


class Contexto:
    def __init__(self, bds=None, hoje=None):
        self.bds = bds or {}                       # {destino: BD ou None}
        self.hoje = hoje or dt.date.today()

    def bd(self, destino):
        return self.bds.get(destino)

    def abas(self, destino):
        b = self.bd(destino)
        return b.abas() if b else []

    def aba(self, destino, nome):
        b = self.bd(destino)
        return b.aba(nome) if b else None
