"""O Andamento da Ronda COS como fonte das telas Ronda padronizada e Parede de eventos (22/10/2026).

O Andamento é o sistema da Ronda COS que tira a fotografia da operação de hora em hora, manda o flash de desligou e
religou ao cliente e guarda os eventos das ocorrências (nova, atualizada, normalizada). Ele expõe uma rota de LEITURA
para o Nexus (`GET /api/nexus/<cliente>`, com a chave de máquina no cabeçalho `X-Nexus-Chave`), e este módulo só lê e
prepara o que as telas mostram. **A regra mora no Andamento**: o que é ocorrência, o problema de cada uma, a cor da
usina, o que entra nos eventos ("nada sem OS"). Reescrevê-la aqui daria duas respostas para a mesma pergunta.

Configuração (`.env` do Nexus ou variável de ambiente; não é obrigatória, sem ela as telas dizem que a fonte não está
ligada e o resto do Nexus segue igual):

- `NEXUS_COS_ANDAMENTO_URL`: o endereço do Andamento (a porta 3002 do servidor da Ronda COS);
- `NEXUS_COS_ANDAMENTO_CHAVE`: a chave de máquina, a MESMA do `ANDAMENTO_NEXUS_CHAVE` de lá. Nunca vai ao log nem à tela;
- `NEXUS_COS_ANDAMENTO_CLIENTES` (opcional): os clientes, separados por vírgula. Sem ela, a lista vem do Andamento.

Nos testes, sem a chave na config do app, NÃO se vai à rede (o mesmo cuidado de `nexus/pcm/fonte.py`).

A leitura não trava a tela: 5 s de teto por pedido, 30 s de cópia em memória por cliente (o Andamento lê a Ronda COS de
minuto em minuto, e as duas telas recarregam sozinhas), e na falha a última cópia boa continua na tela, dita velha.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..config import ler_ambiente

# O contrato que este módulo entende (o `versao` da resposta). Outro número é recusado com aviso, em vez de mostrar
# campo errado: quem muda o contrato lá muda aqui junto.
VERSAO_DO_CONTRATO = 1
TIMEOUT_S = 5
TTL_S = 30
# A lista de clientes muda quando o Andamento ganha um cliente (raro): 5 min de cópia.
TTL_CLIENTES_S = 300
# O Brasil não tem horário de verão desde 2019: o fuso fixo é o padrão da casa (nexus/auth/acessos.py).
_BRT = timezone(timedelta(hours=-3))

URL = "NEXUS_COS_ANDAMENTO_URL"
CHAVE = "NEXUS_COS_ANDAMENTO_CHAVE"
CLIENTES = "NEXUS_COS_ANDAMENTO_CLIENTES"

_cache: dict[tuple[str, str], tuple[float, dict, float]] = {}
_cache_clientes: dict[str, tuple[float, list[str]]] = {}
_trava = threading.Lock()


class FonteErro(RuntimeError):
    pass


@dataclass
class Leitura:
    cliente: str
    dados: dict | None
    lido_em: float | None = None    # epoch da leitura que está em uso
    erro: str = ""                  # preenchido quando a última tentativa falhou
    velha: bool = False             # True: a tentativa falhou e a tela mostra a última cópia boa


@dataclass
class Fonte:
    """O que a configuração diz. `ligada` é falso sem endereço ou sem chave: a tela diz que a fonte não está ligada."""
    url: str = ""
    chave: str = field(default="", repr=False)
    clientes: list[str] = field(default_factory=list)

    @property
    def ligada(self) -> bool:
        return bool(self.url and self.chave)


def _valor(config, chave: str) -> str:
    v = config.get(chave)
    if v:
        return str(v).strip()
    if config.get("TESTING"):           # nos testes, só o que o teste pôs na config
        return ""
    return str(ler_ambiente().get(chave) or "").strip()


def fonte(config) -> Fonte:
    return Fonte(
        url=_valor(config, URL).rstrip("/"),
        chave=_valor(config, CHAVE),
        clientes=[c.strip() for c in _valor(config, CLIENTES).split(",") if c.strip()],
    )


def _pedir(f: Fonte, caminho: str):
    """GET com a chave no cabeçalho. O erro diz o que aconteceu em palavras, nunca a chave."""
    req = urllib.request.Request(f.url + caminho, headers={"X-Nexus-Chave": f.chave, "User-Agent": "Nexus-GridCo/1 (cos)"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # noqa: S310 — endereço do .env
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        motivo = {
            401: "o Andamento recusou a chave do Nexus",
            404: "o Andamento não tem este cliente, ou a rota do Nexus está desligada lá",
            503: "o Andamento ainda não tem leitura deste cliente",
        }.get(ex.code, f"o Andamento respondeu {ex.code}")
        raise FonteErro(motivo) from None
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        raise FonteErro(f"o Andamento não respondeu ({type(ex).__name__})") from None
    except ValueError:
        raise FonteErro("o Andamento respondeu algo que não é JSON") from None


def validar(d) -> dict:
    if not isinstance(d, dict):
        raise FonteErro("a resposta do Andamento não é um objeto")
    if d.get("versao") != VERSAO_DO_CONTRATO:
        raise FonteErro(f"o Andamento fala a versão {d.get('versao')!r} do contrato, e o Nexus entende a {VERSAO_DO_CONTRATO}")
    for k, tipo in (("usinas", list), ("eventos", list), ("placar", dict), ("problemas", list), ("fotografias", list)):
        if not isinstance(d.get(k), tipo):
            raise FonteErro(f"a resposta do Andamento não tem {k}")
    return d


def clientes(config) -> tuple[list[str], str]:
    """(clientes, erro). Os da configuração, ou a lista do Andamento."""
    f = fonte(config)
    if not f.ligada:
        return [], ""
    if f.clientes:
        return f.clientes, ""
    agora = time.monotonic()
    with _trava:
        em_cache = _cache_clientes.get(f.url)
        if em_cache and agora - em_cache[0] < TTL_CLIENTES_S:
            return em_cache[1], ""
    try:
        d = _pedir(f, "/api/nexus/clientes")
        lista = [str(c) for c in d.get("clientes", []) if str(c).strip()] if isinstance(d, dict) else []
    except FonteErro as ex:
        return (em_cache[1] if em_cache else []), str(ex)
    with _trava:
        _cache_clientes[f.url] = (agora, lista)
    return lista, ""


def ler(config, cliente: str) -> Leitura:
    f = fonte(config)
    if not f.ligada:
        return Leitura(cliente, None, erro="a fonte do Andamento não está ligada neste servidor")
    chave = (f.url, cliente)
    agora = time.monotonic()
    with _trava:
        em_cache = _cache.get(chave)
        if em_cache and agora - em_cache[0] < TTL_S:
            return Leitura(cliente, em_cache[1], lido_em=em_cache[2])
    try:
        dados = validar(_pedir(f, "/api/nexus/" + urllib.parse.quote(cliente, safe="")))
    except FonteErro as ex:
        if em_cache:
            return Leitura(cliente, em_cache[1], lido_em=em_cache[2], erro=str(ex), velha=True)
        return Leitura(cliente, None, erro=str(ex))
    with _trava:
        _cache[chave] = (agora, dados, time.time())
    return Leitura(cliente, dados, lido_em=time.time())


def limpar_cache() -> None:
    with _trava:
        _cache.clear()
        _cache_clientes.clear()


# ----------------------------------------------------------------------------------------------------------------------
# O que as telas mostram (puro: o teste chama direto, sem rede e sem Flask)
# ----------------------------------------------------------------------------------------------------------------------

def agora() -> datetime:
    """O agora em Brasília (o teste o troca para fixar a janela da Parede)."""
    return datetime.now(_BRT)


def instante(iso: str | None) -> datetime | None:
    """O instante do Andamento ("2026-10-22T13:00:00.123456-03:00") em Brasília, ou None."""
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(_BRT)


# A situação do evento como o Andamento a escreve, com o tom da casa (cn-t-*). "normalizada" é a Ronda COS; "encerrada",
# as OS do Fracttal: as duas são a volta.
SITUACOES = {
    "nova": ("Nova", "critico"),
    "atualizada": ("Atualizada", "info"),
    "normalizada": ("Normalizada", "ok"),
    "encerrada": ("Encerrada", "ok"),
}

# A cor da usina no Andamento (corDoStatus) no tom da casa.
CORES = {"verm": "critico", "amar": "alerta", "verde": "ok"}

# O estado de cada envio da fotografia ao WhatsApp, em palavras (db/repositorio.ts do Andamento).
ESTADOS_DO_ENVIO = {
    "ENVIADO": ("enviada", "ok"),
    "RETIDO": ("retida até zerar as pendências", "alerta"),
    "PENDENTE": ("saindo", "info"),
    "ENVIANDO": ("saindo", "info"),
    "FALHOU": ("falhou", "critico"),
    "INCERTO": ("sem confirmação de entrega", "alerta"),
    "PAUSADO": ("envio pausado", "neutro"),
    "SEM_DESTINO": ("sem grupo de WhatsApp", "neutro"),
    "SUPRIMIDO": ("não saiu", "neutro"),
}

# As janelas da Parede de eventos: o Andamento guarda 7 dias de eventos.
JANELAS = {"8h": 8, "24h": 24, "7d": 24 * 7}
JANELA_PADRAO = "24h"


def nomes_dos_problemas(dados: dict) -> dict[str, str]:
    return {str(p.get("id")): str(p.get("nome") or p.get("id")) for p in dados.get("problemas") or []}


def eventos(leituras: list[Leitura], agora: datetime, janela: str = JANELA_PADRAO, cliente: str = "",
            problema: str = "", situacao: str = "") -> dict:
    """A Parede de eventos: os eventos de todos os clientes lidos, do mais novo para o mais velho, na janela.

    Devolve `itens` (já filtrados) e `contagem` por situação e por problema (sobre a janela e o cliente, ANTES dos filtros
    de problema e situação, para o número ao lado de cada filtro dizer quantos ele traz)."""
    horas = JANELAS.get(janela, JANELAS[JANELA_PADRAO])
    desde = agora - timedelta(hours=horas)
    base = []
    for lt in leituras:
        if not lt.dados or (cliente and lt.cliente != cliente):
            continue
        nomes = nomes_dos_problemas(lt.dados)
        anterior = instante(lt.dados.get("fotografia_anterior"))
        for e in lt.dados.get("eventos") or []:
            q = instante(e.get("quando"))
            if q is None or q < desde or q > agora + timedelta(minutes=5):
                continue
            sit = str(e.get("situacao") or "")
            rot, tom = SITUACOES.get(sit, (sit.capitalize() or "Evento", "neutro"))
            retro = instante(e.get("retro"))
            base.append({
                "cliente": lt.cliente,
                "quando": q,
                "hora": q.strftime("%H:%M"),
                "dia": q.strftime("%d/%m"),
                "hoje": q.date() == agora.date(),
                "retro": retro,
                "cod": e.get("cod") or "",
                "nome": e.get("nome") or "",
                "os": str(e.get("os") or ""),
                "problema": str(e.get("problema") or ""),
                "problema_nome": nomes.get(str(e.get("problema") or ""), str(e.get("problema") or "")),
                "situacao": sit,
                "situacao_rotulo": rot,
                "tom": tom,
                "texto": e.get("texto") or "",
                "desde_a_anterior": bool(anterior and q > anterior),
            })
    base.sort(key=lambda x: (x["quando"], x["os"]), reverse=True)
    contagem = {"situacao": {}, "problema": {}}
    for x in base:
        contagem["situacao"][x["situacao"]] = contagem["situacao"].get(x["situacao"], 0) + 1
        contagem["problema"][x["problema"]] = contagem["problema"].get(x["problema"], 0) + 1
    itens = [x for x in base if (not problema or x["problema"] == problema) and (not situacao or x["situacao"] == situacao)]
    return {"itens": itens, "total": len(base), "contagem": contagem, "desde": desde, "janela": janela if janela in JANELAS else JANELA_PADRAO}


def fotografias_por_hora(dados: dict) -> list[dict]:
    """As fotografias das últimas 24 h, uma linha por hora cheia (da mais nova), com o estado de cada região."""
    horas: dict[str, dict] = {}
    for f in dados.get("fotografias") or []:
        h = instante(f.get("hora"))
        if h is None:
            continue
        chave = h.strftime("%Y-%m-%dT%H")
        linha = horas.setdefault(chave, {"hora": h, "rotulo": h.strftime("%d/%m %H:00"), "envios": []})
        rot, tom = ESTADOS_DO_ENVIO.get(str(f.get("estado")), (str(f.get("estado") or "").lower(), "neutro"))
        enviada = instante(f.get("enviada_em"))
        linha["envios"].append({
            "regiao": f.get("regiao_rotulo") or ("Todas as usinas" if not f.get("regiao") else str(f.get("regiao"))),
            "estado": str(f.get("estado") or ""),
            "rotulo": rot,
            "tom": tom,
            "enviada": enviada.strftime("%H:%M") if enviada else "",
        })
    for linha in horas.values():
        linha["envios"].sort(key=lambda x: x["regiao"])
        tons = {e["tom"] for e in linha["envios"]}
        linha["tom"] = "critico" if "critico" in tons else "alerta" if "alerta" in tons else "ok" if tons == {"ok"} else "neutro"
    return sorted(horas.values(), key=lambda x: x["hora"], reverse=True)


def ronda(leitura: Leitura) -> dict | None:
    """A Ronda padronizada de um cliente: o placar, os problemas, as fotografias da hora e as usinas com ocorrência aberta
    (vermelhas primeiro), com o que está aberto em cada uma. Usina sem ocorrência é verde no Andamento (corDoStatus)."""
    d = leitura.dados
    if not d:
        return None
    nomes = nomes_dos_problemas(d)
    ordem = {"verm": 0, "amar": 1}
    usinas = []
    for u in d.get("usinas") or []:
        if not u.get("ocorrencias"):
            continue
        ocorrencias = []
        for o in u.get("ocorrencias") or []:
            nota = o.get("ultima_nota") or None
            quando = instante(nota.get("quando")) if nota else None
            os_ = str(o.get("os") or "")
            ocorrencias.append({
                **o,
                # a ocorrência da Ronda COS ainda sem OS no Fracttal vem como "R-<registro>": conta no placar (é
                # ocorrência aberta), e a tela diz que a OS ainda não existe em vez de mostrar o código interno
                "os_rotulo": f"OS {os_}" if os_.isdigit() else "ainda sem OS",
                "problema_nome": nomes.get(str(o.get("problema") or ""), str(o.get("problema") or "")),
                "tom": "critico" if o.get("severidade_classe") in ("crit", "alto") else "alerta",
                "abertura_em": instante(o.get("abertura")),
                "nota": {"quando": quando.strftime("%d/%m %H:%M") if quando else str(nota.get("quando") or ""),
                         "texto": nota.get("texto") or ""} if nota else None,
            })
        usinas.append({
            **u,
            "tom": CORES.get(str(u.get("cor")), "neutro"),
            "problema_nome": nomes.get(str(u.get("problema") or ""), ""),
            "ocorrencias": ocorrencias,
        })
    usinas.sort(key=lambda u: (ordem.get(str(u.get("cor")), 2), str(u.get("nome") or "")))
    return {
        "cliente": d.get("cliente") or leitura.cliente,
        "gerado_em": instante(d.get("gerado_em")),
        "anterior": instante(d.get("fotografia_anterior")),
        "volta": d.get("volta") or "normalizada",
        "placar": d.get("placar") or {},
        "desde": d.get("desde_a_anterior") or {},
        "problemas": [p for p in d.get("problemas") or [] if p.get("vermelhas") or p.get("amarelas") or p.get("novas") or p.get("voltas")],
        "fotografias": fotografias_por_hora(d),
        "usinas": usinas,
    }
