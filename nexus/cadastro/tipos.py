"""Tipos de campo do cadastro: formulário -> Python -> API -> Python, e Excel -> Python.

Três regras que custaram caro em outros projetos da Grid e por isso moram aqui, num lugar só:
- vazio é None, nunca "": o sync-xlsx da API recusa célula de texto vazio (03/09/2026);
- data vai para a API como texto ISO e VOLTA como date: espelhar o texto sem restaurar o tipo fez as metas do
  gerencial colapsarem num mês só, sem erro na tela (25/08/2026);
- o que vem do Excel e não é do tipo NÃO se perde: vira Legado, que guarda o texto original e é marcado na
  tela. O BD_Operações tem "Pendente" em coluna de data e "2,,5" em coluna de potência; descartar isso seria
  perder a informação que a pessoa digitou.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime

# "Não se aplica" / "não informado": o BD usa em campo numérico (QTD TCU, Cabine, SKID) e no lugar da pessoa
# e do contato (115 células de técnico/eletricista/mantenedor na aba Operações: "esta usina não tem"). É valor.
MARCADORES = {"n/a": "N/A", "n/i": "N/I", "-": "-"}
TIPOS_NUMERICOS = {"numero", "inteiro", "moeda", "coordenada"}
TIPOS_COM_MARCADOR = TIPOS_NUMERICOS | {"data", "ref", "telefone"}


def marcador(v):
    """O marcador canônico (N/A, N/I, -) ou None."""
    return MARCADORES.get(v.strip().lower()) if isinstance(v, str) else None


class ValorInvalido(ValueError):
    """Valor digitado que não é do tipo do campo. A mensagem vai para o usuário, em pt-BR."""


@dataclass(frozen=True)
class Legado:
    """Valor herdado do Excel que não é do tipo do campo. Fica como estava até alguém corrigir."""
    texto: str

    def __str__(self) -> str:
        return self.texto


def _vazio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _marcador(s: str):
    return MARCADORES.get(s.strip().lower())


# ── números ────────────────────────────────────────────────────────────────

def _texto_para_float(s: str) -> float:
    """pt-BR primeiro: com vírgula, o ponto é milhar ("1.234,5"); sem vírgula, o ponto é decimal ("12.5")."""
    t = s.replace("R$", "").replace("°", "").replace(" ", "").replace("\xa0", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)", t):
        raise ValorInvalido("Número inválido. Use, por exemplo, 1.234,56.")
    return float(t)


def _texto_para_int(s: str) -> int:
    t = s.replace(" ", "").replace("\xa0", "")
    # Inteiro em pt-BR: ponto só como milhar, em grupos de três ("1.080").
    if re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+", t):
        return int(t.replace(".", ""))
    if re.fullmatch(r"[+-]?\d+(,0+)?", t):
        return int(t.split(",")[0])
    raise ValorInvalido("Número inteiro inválido.")


# ── documentos ─────────────────────────────────────────────────────────────

def _so_digitos(s: str) -> str:
    return re.sub(r"\D", "", s)


def cpf_valido(digitos: str) -> bool:
    """Os dois dígitos verificadores. Sequência repetida (111...) passa na conta e não é CPF."""
    if len(digitos) != 11 or not digitos.isdigit() or len(set(digitos)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(digitos[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(digitos[n]):
            return False
    return True


def _telefone_valido(d: str) -> bool:
    # DDD + número: 10 (fixo) ou 11 (celular); com o 55 do país, 12 ou 13.
    return len(d) in (10, 11) or (d.startswith("55") and len(d) in (12, 13))


# ── datas ──────────────────────────────────────────────────────────────────

def _texto_para_data(s: str) -> date:
    t = s.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
            return date.fromisoformat(t)
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        pass
    raise ValorInvalido("Data inválida. Use dd/mm/aaaa.")


# ── formulário ─────────────────────────────────────────────────────────────

def de_formulario(tipo: str, texto):
    """O que a pessoa digitou, no tipo do campo. Levanta ValorInvalido com mensagem para a tela."""
    if _vazio(texto):
        return None
    s = str(texto).strip()
    if tipo in TIPOS_COM_MARCADOR:
        m = _marcador(s)
        if m:
            return m
    if tipo in ("numero", "moeda"):
        return _texto_para_float(s)
    if tipo == "coordenada":
        v = _texto_para_float(s)
        if not -180 <= v <= 180:
            raise ValorInvalido("Coordenada fora da faixa (-180 a 180).")
        return v
    if tipo == "inteiro":
        return _texto_para_int(s)
    if tipo == "data":
        return _texto_para_data(s)
    if tipo == "simnao":
        k = s.lower().replace("ã", "a")
        if k in ("sim", "s"):
            return "Sim"
        if k in ("nao", "n"):
            return "Não"
        raise ValorInvalido("Use Sim ou Não.")
    if tipo == "email":
        e = s.lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
            raise ValorInvalido("E-mail inválido.")
        return e
    if tipo == "cpf":
        d = _so_digitos(s)
        if not cpf_valido(d):
            raise ValorInvalido("CPF inválido (confira os dígitos).")
        return d
    if tipo == "telefone":
        d = _so_digitos(s)
        if not _telefone_valido(d):
            raise ValorInvalido("Telefone inválido: DDD + número.")
        return d
    if tipo == "url":
        if not re.match(r"https?://\S+$", s):
            raise ValorInvalido("Endereço inválido: comece com https://")
        return s
    if tipo == "texto_longo":
        return str(texto).strip()
    return s


# ── Excel (importação) ─────────────────────────────────────────────────────

def do_excel(tipo: str, bruto):
    """Célula do BD_Operações no tipo do campo. O que não couber vira Legado: nada se perde na importação."""
    if _vazio(bruto):
        return None
    if isinstance(bruto, datetime):
        if tipo == "data":
            return bruto.date()
        bruto = bruto.strftime("%d/%m/%Y")
    if isinstance(bruto, bool):
        bruto = "Sim" if bruto else "Não"
    if isinstance(bruto, (int, float)):
        if tipo in ("numero", "moeda", "coordenada"):
            return float(bruto)
        if tipo == "inteiro":
            return int(bruto) if float(bruto).is_integer() else Legado(str(bruto))
        if tipo == "cpf":
            # O Excel guardou 58 CPFs como número e comeu o zero da frente.
            return str(int(bruto)).zfill(11)
        if tipo == "telefone":
            return str(int(bruto))
        bruto = str(int(bruto)) if float(bruto).is_integer() else str(bruto)
    texto = str(bruto)
    if tipo in TIPOS_COM_MARCADOR and marcador(texto):
        return marcador(texto)
    if tipo in ("texto", "texto_longo", "lista", "ref"):
        return texto.strip()
    if tipo == "cpf":
        d = _so_digitos(texto)
        return d if len(d) == 11 else Legado(texto)
    if tipo == "telefone":
        d = _so_digitos(texto)
        return d if _telefone_valido(d) else Legado(texto)
    try:
        return de_formulario(tipo, texto)
    except ValorInvalido:
        return Legado(texto)


# ── API ────────────────────────────────────────────────────────────────────

def para_api(tipo: str, valor):
    """O que vai na célula do workbook. Data vira texto ISO; Legado, o texto original."""
    if valor is None:
        return None
    if isinstance(valor, Legado):
        return valor.texto
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


def de_api(tipo: str, bruto):
    """Célula do workbook de volta no tipo. Texto que não é do tipo volta como Legado, não como erro."""
    if _vazio(bruto):
        return None
    if tipo == "data":
        if isinstance(bruto, str):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", bruto):
                try:
                    return date.fromisoformat(bruto)
                except ValueError:
                    return Legado(bruto)
            return _marcador(bruto) or Legado(bruto)
        return Legado(str(bruto))
    if tipo in TIPOS_NUMERICOS:
        if isinstance(bruto, bool):
            return Legado(str(bruto))
        if isinstance(bruto, (int, float)):
            if tipo == "inteiro":
                return int(bruto) if float(bruto).is_integer() else Legado(str(bruto))
            return float(bruto)
        return _marcador(str(bruto)) or Legado(str(bruto))
    if tipo == "cpf":
        s = str(bruto)
        return s if re.fullmatch(r"\d{11}", s) else Legado(s)
    if tipo == "telefone":
        s = str(bruto)
        if marcador(s):
            return marcador(s)
        return s if s.isdigit() and _telefone_valido(s) else Legado(s)
    if tipo == "simnao":
        return bruto if bruto in ("Sim", "Não") else Legado(str(bruto))
    return bruto if isinstance(bruto, str) else str(bruto)


# ── exibição ───────────────────────────────────────────────────────────────

def _milhar(inteiro: str) -> str:
    sinal = "-" if inteiro.startswith("-") else ""
    d = inteiro.lstrip("-")
    grupos = []
    while len(d) > 3:
        grupos.insert(0, d[-3:])
        d = d[:-3]
    grupos.insert(0, d)
    return sinal + ".".join(grupos)


def _num_br(v: float, casas: int | None = None) -> str:
    if casas is None:
        s = f"{v:.6f}".rstrip("0").rstrip(".")
    else:
        s = f"{v:.{casas}f}"
    inteiro, _, frac = s.partition(".")
    return _milhar(inteiro) + ("," + frac if frac else "")


def exibir(tipo: str, valor) -> str:
    """Valor pronto para a tela, em pt-BR."""
    if valor is None:
        return ""
    if isinstance(valor, Legado):
        return valor.texto
    if isinstance(valor, str) and tipo in TIPOS_NUMERICOS | {"data"}:
        return valor                       # marcador (N/A, N/I, -)
    if tipo == "moeda":
        return "R$ " + _num_br(float(valor), 2)
    if tipo == "inteiro":
        return _milhar(str(int(valor)))
    if tipo in ("numero", "coordenada"):
        return _num_br(float(valor))
    if tipo == "data":
        return valor.strftime("%d/%m/%Y")
    if tipo == "cpf":
        d = str(valor)
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else d
    if tipo == "telefone":
        d = str(valor)
        if d.startswith("55") and len(d) in (12, 13):
            d = d[2:]
        if len(d) == 11:
            return f"({d[:2]}) {d[2:7]}-{d[7:]}"
        if len(d) == 10:
            return f"({d[:2]}) {d[2:6]}-{d[6:]}"
        return d
    return str(valor)


def para_formulario(tipo: str, valor) -> str:
    """O texto que volta para dentro do campo do formulário (o <input value=...>)."""
    if valor is None:
        return ""
    if isinstance(valor, Legado):
        return valor.texto
    if tipo == "data" and isinstance(valor, date):
        # Campo de texto, não <input type="date">: o navegador apagaria o "Pendente" que veio do Excel.
        return valor.strftime("%d/%m/%Y")
    if tipo in ("cpf", "telefone"):
        return exibir(tipo, valor)
    if tipo in TIPOS_NUMERICOS and not isinstance(valor, str):
        return exibir(tipo, valor).replace("R$ ", "")
    return str(valor)


def mascarar(tipo: str, valor) -> str:
    """Dado sensível na tela antes de a pessoa pedir para ver: só o final."""
    t = exibir(tipo, valor)
    if not t:
        return ""
    if tipo == "cpf" and len(t) == 14:
        return "***.***.***-" + t[-2:]
    if tipo == "telefone":
        # Fica o DDD e os 4 últimos: dá para reconhecer o número sem expô-lo inteiro.
        pos = [i for i, ch in enumerate(t) if ch.isdigit()]
        manter = set(pos[:2] + pos[-4:])
        return "".join("*" if ch.isdigit() and i not in manter else ch for i, ch in enumerate(t))
    if tipo == "moeda":
        return "R$ ••••"
    return "•" * min(len(t), 10)
