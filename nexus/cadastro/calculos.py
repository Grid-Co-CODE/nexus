"""As fórmulas do BD_Operações, portadas.

Cada função reproduz a fórmula da planilha COMO ELA É, inclusive nos cantos estranhos (o objetivo é o Nexus
mostrar o mesmo número que o Excel mostrava, e a importação conferir os dois valor a valor). A fórmula original
vai no comentário de cada uma. Onde o Nexus decide diferente de propósito, o comentário diz, e a comparação da
importação explica a diferença em vez de escondê-la:
- o técnico/eletricista/mantenedor e a base da equipe saem da primeira pessoa ATIVA: o PROCV do Excel pegava a
  primeira da planilha, mesmo desligada.

Quando o Excel daria erro (#N/A), a função devolve ERRO: a tela mostra vazio com aviso, e a comparação casa
ERRO com o "#N/A" que a planilha guardou.
"""
import re

from .tipos import Legado

UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
       "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")
CARGO_TECNICO, CARGO_ELETRICISTA, CARGO_MANTENEDOR = "Técnico O&M", "Eletricista O&M", "Mantenedor O&M"


class _Erro:
    def __repr__(self):
        return "ERRO"

    def __str__(self):
        return "#N/A"


ERRO = _Erro()


def _vazio(v) -> bool:
    return v is None or (isinstance(v, str) and v == "")


def _txt(v) -> str:
    """O `&""` do Excel: None vira "", número inteiro sai sem ",0"."""
    if v is None:
        return ""
    if isinstance(v, Legado):
        return v.texto
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def trim_excel(s: str) -> str:
    """TRIM do Excel: só o espaço comum, nas pontas, e junta os espaços repetidos do meio."""
    return re.sub(" +", " ", s.strip(" "))


def proper(s: str) -> str:
    """PROPER do Excel: maiúscula na letra que vem depois de algo que não é letra; o resto minúsculo."""
    out, antes_letra = [], False
    for ch in s:
        if ch.isalpha():
            out.append(ch.lower() if antes_letra else ch.upper())
            antes_letra = True
        else:
            out.append(ch)
            antes_letra = False
    return "".join(out)


def nome_padrao(nome):
    """=LEFT(Nome;FIND(" ";Nome)-1)&" "&TRIM(RIGHT(SUBSTITUTE(Nome;" ";REPT(" ";255));255))"""
    s = _txt(nome)
    i = s.find(" ")
    if i < 0:
        return ERRO
    ultimo = trim_excel(s.replace(" ", " " * 255)[-255:])
    return s[:i] + " " + ultimo


def localizacao(cidade, uf, pais) -> str:
    """=CONCAT(CIDADE;",";UF;",";PAÍS)"""
    return _txt(cidade) + "," + _txt(uf) + "," + _txt(pais)


def _pedacos_do_endereco(endereco: str) -> list[str]:
    # SUBSTITUTE(SUBSTITUTE(addr;"/";",");"-";",") e TEXTSPLIT(...;","): o TEXTSPLIT mantém pedaço vazio.
    return [trim_excel(t) for t in endereco.replace("/", ",").replace("-", ",").split(",")]


def cidade_uf_endereco(endereco):
    """Cidade/UF (do endereço): a ÚLTIMA sigla de UF entre os pedaços do endereço e o pedaço antes dela.
    Pedaço que começa com número perde tudo até o 1º espaço ("000 Brodowski" -> "Brodowski"); sem espaço, #N/A."""
    s = _txt(endereco)
    if trim_excel(s) == "":
        return ""
    tk = _pedacos_do_endereco(s)
    idx = max((i + 1 for i, t in enumerate(tk) if t.upper() in UFS), default=0)   # MATCH ignora maiúscula
    if idx <= 1:
        return ""
    bruta = tk[idx - 2]
    if bruta == "":
        return ""
    if bruta[0] in "0123456789":
        if " " not in bruta:
            return ERRO                                   # TEXTAFTER sem achar espaço
        limpa = trim_excel(bruta.split(" ", 1)[1])
    else:
        limpa = trim_excel(bruta)
    return "" if limpa == "" else limpa + "/" + tk[idx - 1]


def _excel_numerico(s: str) -> bool:
    # O "--texto" do Excel: número, com expoente ou porcentagem, ou uma hora (12:30).
    return bool(re.fullmatch(r"[+-]?\d+(\.\d+)?([eE][+-]?\d+)?%?", s) or re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", s))


def cidade_uf_fallback(cidade, cluster, endereco):
    """Cidade/UF (fallback): a cidade digitada (a 1ª de uma lista "A e B", "A/B", "A, UF") ou, sem ela, o último
    pedaço de TEXTO do endereço (número e CEP não contam); a UF são as duas letras do começo do cluster."""
    c = _txt(cidade).replace("\n", "/").replace(" e ", "/")
    primeira = "" if c == "" else trim_excel(c.split("/", 1)[0].split(",", 1)[0])
    uf_cluster = trim_excel(_txt(cluster).upper())[:2]
    uf = uf_cluster if uf_cluster in UFS else ""
    ultimo = ""
    end = _txt(endereco)
    if end != "":
        validos = []
        for i, t in enumerate(_pedacos_do_endereco(end)):
            numerico = True if t == "" else _excel_numerico(t.replace(" ", "").replace(".", "").replace("-", ""))
            cep = t.upper()[:3] == "CEP"
            if not numerico and not cep and t != "":
                validos.append(t)
        ultimo = validos[-1] if validos else ""
    final = primeira if primeira != "" else ultimo
    if final == "":
        return ""
    return final + ("/" + uf if uf else "")


def cidade_estado_base(do_endereco, fallback):
    """=LET(raw;SE(P<>"";P;Q); SE(raw="";"";PRI.MAIÚSCULA(TEXTOANTES(raw;"/"))&"/"&MAIÚSCULA(TEXTODEPOIS(raw;"/"))))"""
    if do_endereco is ERRO:
        return ERRO
    raw = do_endereco if _txt(do_endereco) != "" else fallback
    if raw is ERRO:
        return ERRO
    raw = _txt(raw)
    if raw == "":
        return ""
    if "/" not in raw:
        return ERRO
    antes, depois = raw.split("/", 1)
    return proper(antes) + "/" + depois.upper()


def contato(corporativo, pessoal):
    """=SE(PROCV(tel. corporativo)="";PROCV(tel. pessoal);PROCV(tel. corporativo)). Vazio nos dois: o Excel
    mostra 0; aqui, None (a comparação trata 0 e vazio como iguais)."""
    if not _vazio(corporativo):
        return corporativo
    if not _vazio(pessoal):
        return pessoal
    return None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def receita_contratual(mensal, prazo):
    """=Receita Mensal * Prazo Contratual (Meses)"""
    m, p = _num(mensal), _num(prazo)
    return None if m is None or p is None else m * p


def receita_por_mwp(preco_mwp, potencia):
    """=3915,51 * POTÊNCIA CONTRATUAL, a fórmula de 70 usinas: o preço vira campo, e a receita acompanha a
    potência como acompanhava no Excel."""
    a, b = _num(preco_mwp), _num(potencia)
    return None if a is None or b is None else a * b


def _desligado(p) -> bool:
    return str((p["valores"].get("status") or "")).strip().lower() == "desligado"


class Contexto:
    """Os três cadastros juntos, para o que depende de outro cadastro. Registros: {"id", "ordem", "valores"}."""

    def __init__(self, usinas, pessoas, equipes):
        self.usinas = sorted(usinas, key=lambda r: r.get("ordem") or 0)
        self.pessoas = sorted(pessoas, key=lambda r: r.get("ordem") or 0)
        self.equipes = {e["id"]: e for e in equipes}
        self.pessoa = {p["id"]: p for p in self.pessoas}

    def nome_da_equipe(self, equipe):
        if isinstance(equipe, Legado):
            return equipe.texto
        e = self.equipes.get(equipe)
        return (e["valores"].get("nome") if e else None) or ""

    def pessoa_da_equipe(self, equipe_id, cargo):
        """=PROCX(Equipe & cargo; cod; Nome Padrão): a PRIMEIRA pessoa da equipe com o cargo. Diferença de
        propósito: o Nexus pula a desligada (o Excel a pegava, se viesse antes na planilha)."""
        if not equipe_id or isinstance(equipe_id, Legado):
            return None
        for p in self.pessoas:
            v = p["valores"]
            if v.get("equipe") == equipe_id and v.get("cargo") == cargo and not _desligado(p):
                return p
        return None

    def responsavel_da_equipe(self, equipe_id):
        """=PROCX(Cluster; Operações!Equipe Cluster; Operações!RESPONSÁVEL O&M): o da 1ª usina da equipe."""
        if not equipe_id:
            return None
        for u in self.usinas:
            if u["valores"].get("equipe") == equipe_id:
                return u["valores"].get("responsavel_om")
        return None

    def _calculos_da_pessoa_puros(self, p):
        v = p["valores"]
        do_end = cidade_uf_endereco(v.get("endereco"))
        fb = cidade_uf_fallback(v.get("cidade"), self.nome_da_equipe(v.get("equipe")), v.get("endereco"))
        return do_end, fb, cidade_estado_base(do_end, fb)

    def base_da_equipe(self, equipe_id):
        """=SE(Equipe="";"";SEERRO(PROCX(Equipe; Cluster das pessoas; Cidade/Estado (Base Equipe));""))"""
        if not equipe_id:
            return ""
        for p in self.pessoas:
            if p["valores"].get("equipe") == equipe_id and not _desligado(p):
                base = self._calculos_da_pessoa_puros(p)[2]
                return "" if base is ERRO else base
        return ""

    def _telefones(self, pessoa_ref):
        p = self.pessoa.get(pessoa_ref) if isinstance(pessoa_ref, str) else None
        if not p:
            return None
        return contato(p["valores"].get("telefone_corporativo"), p["valores"].get("telefone_pessoal"))

    def calcular_usina(self, u) -> dict:
        v = u["valores"]
        out = {"localizacao": localizacao(v.get("cidade"), v.get("uf"), v.get("pais"))}
        mensal = v.get("receita_mensal")
        if _vazio(mensal):
            mensal = receita_por_mwp(v.get("preco_mwp"), v.get("potencia_contratual"))
        out["receita_mensal"] = mensal
        out["receita_contratual"] = receita_contratual(mensal, v.get("prazo_meses"))
        base = v.get("base_equipe")
        out["base_equipe"] = base if not _vazio(base) else self.base_da_equipe(v.get("equipe"))
        for campo, cargo, contato_campo in (("tecnico_om", CARGO_TECNICO, "contato_tecnico"),
                                            ("eletricista_om", CARGO_ELETRICISTA, "contato_eletricista"),
                                            ("mantenedor_om", CARGO_MANTENEDOR, "contato_mantenedor")):
            quem = v.get(campo)
            if _vazio(quem):
                achada = self.pessoa_da_equipe(v.get("equipe"), cargo)
                quem = achada["id"] if achada else None
            out[campo] = quem
            tel = v.get(contato_campo)
            out[contato_campo] = tel if not _vazio(tel) else self._telefones(quem)
        return out

    def calcular_pessoa(self, p) -> dict:
        v = p["valores"]
        do_end, fb, base = self._calculos_da_pessoa_puros(p)
        np_ = v.get("nome_padrao")
        sup = v.get("supervisor")
        return {
            "nome_padrao": np_ if not _vazio(np_) else nome_padrao(v.get("nome")),
            "supervisor": sup if not _vazio(sup) else self.responsavel_da_equipe(v.get("equipe")),
            "cidade_uf_endereco": do_end,
            "cidade_uf_fallback": fb,
            "cidade_estado_base": base,
        }
