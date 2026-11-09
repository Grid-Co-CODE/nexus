"""A ficha da usina no COS (09/11/2026): tudo o que as telas do COS sabem de UMA usina, numa página só.

Por que existe: a mesma usina aparecia em oito telas (Ronda, Ocorrências, Mesa, Parede, Religamentos, Acionamentos, OS em
aberto, Normalizações) e em nenhuma dava para abri-la. O caso que motivou: a Mesa diz "Campo a acionar · atrasada"; para
saber quem chamar, o operador abria Acionamentos e procurava a usina de novo, para saber se ela repete abria
Religamentos e escolhia o cliente de novo, e para ver a OS abria OS em aberto e filtrava de novo.

Nenhuma fonte nova e nenhuma regra nova: a ficha lê as mesmas cópias do Andamento que as telas já leem (a fotografia, o
ciclo das ocorrências, as OS em aberto, as normalizações, a distribuidora) e passa cada uma pela conta da tela dona
(`ocorrencias.linha`, `religamentos.painel`, `os_abertas.painel`, `normalizacoes.painel`, `acionamentos.painel`). Só
recorta pela usina. Assim a ficha e a tela dizem sempre a mesma coisa.

A chave é o código da usina do Andamento (`codigo` na fotografia, `usina_codigo` no resto, o mesmo valor: "THPN-ALT100").
Os eventos trazem só o código curto (`cod`, "ALT100"): dentro do mesmo cliente ele casa pelo sufixo.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime

from ..dados import fatos as D
from . import acionamentos as AC
from . import andamento as AND
from . import normalizacoes as NO
from . import ocorrencias as OC
from . import os_abertas as OA
from . import religamentos as RE

# As ocorrências da ficha: o período padrão de Religamentos, para a conta de "repete" ser a mesma da tela.
DIAS_DO_CICLO = 30
# O que cabe em cada bloco sem virar outra tela: a tela dona, pelo link, mostra o resto.
CICLO_NA_FICHA = 15
EVENTOS_NA_FICHA = 20
NORMALIZACOES_NA_FICHA = 15
BUSCA_MAX = 80

# O código da usina: três letras e três números ("ALT100"), com ou sem o prefixo do cliente ("THPN-ALT100"). O mesmo
# padrão do cadastro (`cadastro.banco.codigo_do_equipamento`).
_SUFIXO = re.compile(r"[A-Z]{3}\d{3}")

# A ordem da lista de usinas: a cor da pior ocorrência aberta (a do Andamento), vermelhas primeiro.
_ORDEM_DA_COR = {"verm": 0, "amar": 1, "verde": 2}


def normal(codigo) -> str:
    return "".join(str(codigo or "").split()).upper()


def sufixo(codigo) -> str:
    achados = _SUFIXO.findall(normal(codigo))
    return achados[-1] if achados else ""


def mesma(a, b) -> bool:
    """`a` e `b` são a mesma usina? O código inteiro casa. Sem o prefixo de um dos lados (o `cod` "VER100" dos eventos
    contra o `codigo` "EX-VER100"), casa pelo sufixo. Dois códigos com prefixos diferentes ("EX-VER100" e "XY-VER100")
    são usinas diferentes: o prefixo é o cliente."""
    a, b = normal(a), normal(b)
    if not a or not b:
        return False
    if a == b:
        return True
    sa, sb = sufixo(a), sufixo(b)
    return bool(sa) and sa == sb and (a == sa or b == sa)


def achar(fotos: list, codigo: str):
    """(a leitura do cliente, a usina da fotografia) do código pedido, ou (None, None). O código inteiro primeiro, em
    todos os clientes; o sufixo só depois, para "VER100" não cair na usina de outro cliente com o mesmo sufixo."""
    alvo = normal(codigo)
    if not alvo:
        return None, None
    usinas = [(lt, u) for lt in fotos for u in (lt.dados or {}).get("usinas") or []]
    for lt, u in usinas:
        if normal(u.get("codigo")) == alvo:
            return lt, u
    for lt, u in usinas:
        if mesma(u.get("codigo"), alvo) or mesma(u.get("cod"), alvo):
            return lt, u
    return None, None


def lista(fotos: list, busca: str = "") -> list[dict]:
    """As usinas de todos os clientes lidos, para escolher uma: as com ocorrência aberta primeiro (a cor do Andamento),
    depois pelo nome. A busca casa cada palavra no nome, no código ou na cidade."""
    palavras = " ".join(str(busca or "").lower().split())[:BUSCA_MAX].split()
    saida = []
    for lt in fotos:
        for u in (lt.dados or {}).get("usinas") or []:
            alvo = " ".join(str(u.get(k) or "") for k in ("nome", "codigo", "cidade")).lower()
            if palavras and not all(p in alvo for p in palavras):
                continue
            saida.append({
                "cliente": lt.cliente, "codigo": u.get("codigo") or u.get("cod") or "", "nome": u.get("nome") or "",
                "cidade": u.get("cidade") or "", "uf": u.get("uf") or "", "status_rotulo": u.get("status_rotulo") or "",
                "tom": AND.CORES.get(str(u.get("cor")), "neutro"), "abertas": len(u.get("ocorrencias") or []),
                "_ordem": _ORDEM_DA_COR.get(str(u.get("cor")), 3),
            })
    saida.sort(key=lambda x: (x["_ordem"], x["nome"].lower()))
    return saida


@dataclass
class Ficha:
    cliente: str
    usina: dict                     # a usina da fotografia: codigo, cod, nome, cidade, uf, cor, status_rotulo
    tom: str
    abertas: list                   # as ocorrências abertas agora (da fotografia), cada uma com o prazo do ciclo
    ciclo: list                     # ocorrencias.Linha do período, desta usina
    ciclo_total: int
    religamentos: list              # religamentos.Equipamento desta usina
    eventos: list
    eventos_total: int
    os_abertas: list
    normalizacoes: list
    normalizacoes_total: int
    erros: list = field(default_factory=list)     # (de onde, o erro, se a tela mostra a última leitura boa)
    completo: dict = field(default_factory=dict)  # cada bloco foi lido? Sem a leitura, o bloco diz que falta

    @property
    def resumo(self) -> dict:
        return {
            "abertas": len(self.abertas),
            "religamentos": sum(e.total for e in self.religamentos),
            "repete": any(e.repete for e in self.religamentos),
            "reincidente": any(e.reincidente for e in self.religamentos),
            "os": len(self.os_abertas),
            "os_em_alerta": sum(1 for o in self.os_abertas if o["em_alerta"]),
            "normalizacoes": self.normalizacoes_total,
        }


def _erro(nome: str, lt):
    return (nome, lt.erro, lt.velha) if lt is not None and lt.erro else None


def painel(foto, usina: dict, ciclo, os_lt, norm_lt, agora: datetime, url_do_andamento: str = "") -> Ficha:
    """A ficha. `foto` é a leitura da fotografia do cliente da usina; `ciclo`, a das ocorrências de DIAS_DO_CICLO dias do
    mesmo cliente; `os_lt` e `norm_lt`, as de todos os clientes. Cada bloco usa a conta da tela dona e só recorta."""
    codigo = usina.get("codigo") or usina.get("cod") or ""

    # o ciclo de cada ocorrência (a conta da tela Ocorrências), desta usina, a mais nova primeiro
    p_oc = OC.painel(ciclo, agora, "", url_do_andamento) if ciclo is not None else None
    linhas = [x for x in (p_oc.itens if p_oc else []) if mesma(x.o.get("usina_codigo"), codigo)]
    linhas.sort(key=lambda x: AND.instante(x.o.get("inicio")) or datetime.min.replace(tzinfo=AND._BRT), reverse=True)
    por_registro = {str(x.o.get("registro")): x for x in linhas if x.o.get("registro")}

    # o que está aberto agora: a fotografia (a conta da Ronda), com o prazo do ciclo quando a ocorrência está nele
    r = AND.ronda(foto)
    aberta = next((u for u in (r or {}).get("usinas") or [] if normal(u.get("codigo")) == normal(codigo)), None)
    abertas = []
    for o in (aberta or {}).get("ocorrencias") or []:
        x = por_registro.get(str(o.get("registro")))
        abertas.append({**o, "linha": x})

    p_re = RE.painel(ciclo, "todos") if ciclo is not None and ciclo.dados else None
    religamentos = [e for e in (p_re.itens if p_re else []) if mesma(e.usina_codigo, codigo)]

    evs = [e for e in AND.eventos([foto], agora, "7d")["itens"] if mesma(e["cod"], usina.get("cod") or codigo)]

    p_os = OA.painel(os_lt, agora, "todas") if os_lt is not None else None
    os_abertas = [o for o in (p_os.itens if p_os else []) if mesma(o["usina_codigo"], codigo)]

    p_no = NO.painel(norm_lt, agora) if norm_lt is not None else None
    norms = [n for n in (p_no.todos if p_no else []) if mesma(n["usina_codigo"], codigo)]

    return Ficha(
        cliente=foto.cliente, usina=usina, tom=AND.CORES.get(str(usina.get("cor")), "neutro"), abertas=abertas,
        ciclo=linhas[:CICLO_NA_FICHA], ciclo_total=len(linhas), religamentos=religamentos,
        eventos=evs[:EVENTOS_NA_FICHA], eventos_total=len(evs), os_abertas=os_abertas,
        normalizacoes=norms[:NORMALIZACOES_NA_FICHA], normalizacoes_total=len(norms),
        erros=[e for e in (_erro("Fotografia", foto), _erro("Ocorrências", ciclo), _erro("OS em aberto", os_lt),
                           _erro("Normalizações", norm_lt)) if e],
        completo={"ciclo": bool(p_oc), "os": bool(p_os), "normalizacoes": bool(p_no)},
    )


def acionar(b, cofre, distribuidoras, agora: datetime, nome: str, codigo: str) -> dict:
    """Quem acionar e a distribuidora desta usina: a conta da tela Acionamentos (`acionamentos.painel`), recortada pela
    usina do cadastro. A usina do Andamento liga ao cadastro pelo `Ligador` (o mesmo da tela); sem ligação, a ficha diz,
    em vez de chutar a usina pelo nome."""
    uid, _como = b.lig.usina(nome, codigo)
    if not uid:
        return {"uid": None, "linha": None, "chamados": [], "erros": []}
    cad = b.por_id.get(uid) or {}
    alvo = D._txt(cad.get("codigo")) or D._txt(cad.get("nome")) or nome
    p = AC.painel(b, cofre, [distribuidoras] if distribuidoras is not None else [], agora, busca=alvo)
    return {
        "uid": uid,
        "linha": next((x for x in p["linhas"] if x["uid"] == uid), None),
        "chamados": [c for c in p["chamados"] if c["uid"] == uid],
        "erros": p["erros"],
        "sinal": p["sinal"],
    }
