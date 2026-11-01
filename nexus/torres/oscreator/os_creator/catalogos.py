"""catalogos.py: os catálogos pequenos do OS Creator, UM dono para cada (31/10/2026, etapa 4 do canto central; tarefa 4.1).

Levi, 30/10/2026: "a ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as coisas se aproveitam e não
precisamos ficar fazendo novas requisições sempre!" (desenho: `docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`,
"Etapa 4").

O QUE HAVIA ANTES: o pessoal lido por 7 caminhos (a lista das telas em duas cópias de 10 e 30 min, o "Criado por" e o "eu" do
Histórico numa cópia por pessoa, a pessoa logada achada pelo e-mail uma vez por processo, o nome do responsável do card numa
cópia que nunca vencia, o COS e a criação da Engenharia lendo na hora); as etiquetas em 4 (duas cópias de tela, o id pelo nome
que guardava "não existe" para sempre, o id da etiqueta das listas relido a cada lista); os tipos e as classificações em 3 (duas
cópias que NUNCA venciam: o tipo novo no Fracttal só aparecia no reinício, e o conjunto vazio de quem não tinha a permissão
ficava para sempre); as falhas do COS numa cópia que nunca vencia; e os planos da Performance relidos inversor por inversor a
cada usina escolhida. E tudo só na memória: cada push na `main` (~10 por dia útil) reinicia o serviço.

COMO É AGORA: um dono por assunto (`ASSUNTOS`), com prazo próprio (`PRAZO_S`: as pessoas e as etiquetas 6 h; os tipos, as falhas,
os status e os motivos 24 h; os planos 24 h), uma cópia em disco (`<pasta de dados do clone>/oscreator/catalogos/<assunto>.json`,
escrita ao lado e trocada de uma vez pelo `canto_disco`) e a MESMA forma de antes para as telas (as funções de cada assunto
abaixo devolvem cópias, no formato do `api` de antes). Os planos da Performance moram em `catalogos_planos.py`, e o laço das
pessoas pelo REST da empresa, a única parte que importa o `nexus`, em `catalogos_leitor.py` (o par `ativos_central` /
`ativos_leitor`: este módulo guarda e entrega; o leitor se registra aqui, `ligar_leitor`).
- O BOOT SÓ LÊ O DISCO, nunca o Fracttal, nem com a cópia vencida (`aquecer`, por trás, ao ligar a ponte; e a 1ª leitura de cada
  assunto, se o aquecimento ainda não chegou). A cópia ilegível, cortada ou de outro formato é ignorada, e o motivo fica em
  `estado()`. O vencido é renovado DEPOIS, pela regra abaixo.
- QUEM RENOVA. As pessoas, com o leitor da empresa (`catalogos_leitor`: o REST `personnel` do cadastro, às 05h, 11h, 17h e
  23h no minuto `minutos_ocupados.CATALOGOS_PESSOAS`; só o `servir.py` liga), quando ele trouxer os campos que as telas usam e
  bater com o RPC. O resto (e as pessoas sem o REST valendo: o PC, a credencial que falta, o REST sem os campos) não tem leitor
  da empresa: o RPC exige a sessão de uma pessoa (`os_web/sessao.py`). Então a 1ª sessão que acha o catálogo vencido o renova
  POR TRÁS, uma vez para todos, com a cópia do contexto (que leva o JWT dela) e um estado de sessão próprio, como o
  `api._renovar_catalogo_por_tras` dos ativos; quem chega com a renovação em curso usa a cópia velha e não espera
  (`renovar_por_tras`, a mesma para os assuntos, os planos e os detalhes, com 1 pedido por segundo, a cota e a sessão que caiu).
  Sem cópia nenhuma (a máquina nova, o disco ilegível), a 1ª tela lê na hora, e quem chega junto espera a MESMA leitura
  (`_Assunto.trava`).
- O ERRO E O VAZIO NÃO FICAM GUARDADOS (a regra de 20/10/2026 dos catálogos de tela): a lista vazia da sessão de alguém sem a
  permissão no Fracttal esvaziaria a tela de todo mundo pelo prazo inteiro. A leitura PELA METADE também não (as falhas do COS
  só valem com as três listas).
- QUEM RELÊ NA HORA: só quem não achou o que procura (`reler=True`, o tipo da Zeladoria criado hoje, a etiqueta da lista, a
  pessoa logada que não está no catálogo), uma vez por `RELER_NA_FALTA_S`, com a sessão de quem pediu.
- O QUE NÃO É DO CATÁLOGO (revisão da 4.1): a GRAVAÇÃO não confia nele (a criação da Engenharia confere a pessoa e a etiqueta
  ao vivo, a regra de 19/10), e o "Criado por" do Histórico segue POR PESSOA (`api.get_pessoas_contas`, com a sessão dela:
  quem não tem a permissão de pessoal no Fracttal não vê as contas da empresa).
- AS PESSOAS sem o e-mail: em disco e na memória vai o HMAC do e-mail (`email_h`, com a chave que a ponte deriva da do Nexus),
  e a pessoa logada é achada por ele (`da_pessoa`). O nome, o código e os ids são os que a lista de OS em disco já guarda (o
  nome que é um e-mail não vai). A cópia feita com outra chave é ignorada (ninguém seria achado) e o pessoal é relido uma vez.

Este módulo não importa o `api` ao carregar (o `api` o importa): os leitores são chamados pelo nome, no `api`, na hora da
leitura (os testes trocam o `api.<leitor>` e o catálogo lê o dublê).
"""
from __future__ import annotations

import contextvars
import copy
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

# a troca de uma vez (rascunho ao lado + `os.replace`, que tenta de novo o arquivo preso do Windows) é comum às cópias do canto
from canto_disco import trocar_de_uma_vez as _trocar_de_uma_vez

log = logging.getLogger("oscreator.catalogos")

FORMATO = 1                     # o formato dos arquivos; outro número = arquivo de outra versão do código, ignorado
_H = 3600
PRAZO_S = {"pessoas": 6 * _H, "etiquetas": 6 * _H, "tipos": 24 * _H, "tipos_solicitacao": 24 * _H, "falhas": 24 * _H,
           "status": 24 * _H, "motivos": 24 * _H, "planos": 24 * _H, "detalhes": 24 * _H}
ESPERA_TENTATIVA_S = 600        # a renovação por trás que falhou só tenta de novo depois disto (o ASSETS_ESPERA_TENTATIVA)
RELER_NA_FALTA_S = 60           # quem não achou o que procura relê se o catálogo tem mais que isto (uma vez por minuto)
FOLGA_REST_S = _H               # com o REST valendo, as pessoas só vencem 1 h depois do prazo: o laço das :MM pode atrasar
PAUSA_S = 1.0                   # em segundo plano, 1 pedido por segundo (como os leitores dos ativos e da lista de OS)
# o 406/429 do Fracttal (a cota) na renovação por trás: espera e tenta a mesma chave de novo, como o cliente REST do Nexus
# (`nexus/campo/fracttal.ler`, 5 s e 10 s); a cota que não voltou para a renovação, e o que faltou espera a janela
ESPERAS_COTA_S = (5, 10)
_COTA = re.compile(r"\bHTTP (406|429)\b")
NOME_ESTADO = "estado.json"     # o REST das pessoas (a última boa, a última falha), que sobrevive ao reinício
_BRT = timezone(timedelta(hours=-3))

_relogio = time.time            # os testes trocam (o prazo, a idade)
_dormir = time.sleep            # e as pausas do trabalho por trás (o REST das pessoas, os planos)


def _em_segundo_plano(fn) -> None:
    """Onde a renovação por trás roda: uma thread solta (os testes trocam para rodar quando querem)."""
    threading.Thread(target=fn, name="os-catalogos-por-tras", daemon=True).start()


# os companheiros (`catalogos_planos`, `catalogos_leitor`) leem a hora e dormem por aqui, na hora da chamada: o teste que troca
# o `_relogio` ou o `_dormir` deste módulo vale para os três
def relogio() -> float:
    return _relogio()


def dormir(s: float) -> None:
    _dormir(s)


def geracao() -> int:
    """O reinício (os testes) conta aqui: a leitura que começou antes dele não instala nada depois."""
    return _GERACAO[0]


# ── um assunto ─────────────────────────────────────────────────────────────────────────────────────────────────────────
class _Assunto:
    """Um catálogo: o valor (o MESMO para todas as telas e pessoas; quem lê recebe cópia), de quando é, de onde veio e o que
    houve com ele. `leitor` é o nome da função do `api` que o lê pelo RPC; `serve(valor)` diz se a leitura pode ser guardada
    (não vazia); `forma(valor)` confere o que veio do disco; `do_disco` converte o que o JSON não guarda (as tuplas)."""

    def __init__(self, nome, rotulo, leitor, serve, forma, *, kwargs=None, preparar=None, para_disco=None, do_disco=None,
                 contar=len):
        self.nome, self.rotulo, self.leitor, self.serve, self.forma = nome, rotulo, leitor, serve, forma
        self.kwargs, self.preparar, self.para_disco, self.do_disco, self.contar = (kwargs or {}, preparar, para_disco,
                                                                                    do_disco, contar)
        self.trava = threading.Lock()           # a leitura na frente de quem pediu: uma para quem chega junto
        self.trava_boot = threading.Lock()      # o disco, uma vez só, mesmo com vários pedidos juntos
        self.trava_disco = threading.Lock()     # uma gravação por vez
        self.limpar()

    def limpar(self) -> None:
        # `seq` conta as leituras instaladas: a gravação pula só a que o disco já tem (`disco["seq"]`), e não a de mesmo
        # `lido_em` (duas leituras no mesmo instante, com conteúdo diferente, deixariam a 1ª no disco)
        self.valor, self.lido_em, self.fonte, self.boot, self.seq = None, 0.0, "", False, 0
        self.erro, self.erro_em = None, 0.0
        self.leituras, self.vazias = 0, 0
        self.disco = {"lido": None, "gravado_em": 0.0, "lido_em": 0.0, "seq": 0, "erro": None}


def _lista_de_dicts(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, dict) for x in v)


def _listas(*chaves):
    def forma(v) -> bool:
        return isinstance(v, dict) and all(_lista_de_dicts(v.get(k, [])) for k in chaves)
    return forma


def _status_forma(v) -> bool:
    return isinstance(v, list) and all(isinstance(t, (list, tuple)) and len(t) == 3 for t in v)


def _contar_listas(v) -> int:
    return sum(len(x) for x in v.values() if isinstance(x, list)) if isinstance(v, dict) else 0


# ── as pessoas: o mesmo registro do RPC e do REST, sem o e-mail ────────────────────────────────────────────────────────────
_CHAVE_EMAIL: dict = {"v": None, "aleatoria": os.urandom(32)}


def _chave() -> bytes:
    """A chave do HMAC do e-mail: a que a ponte deriva da do Nexus (sobrevive ao reinício), ou, sem ela (os testes, quem não
    ligou a ponte), uma do processo (só na memória: sem a chave da ponte, o `email_h` não vai ao disco)."""
    return _CHAVE_EMAIL["v"] or _CHAVE_EMAIL["aleatoria"]


def _id_da_chave() -> str:
    return hashlib.sha256(_chave()).hexdigest()[:12]


def _hash_email(email: str) -> str:
    e = str(email or "").strip().lower()
    return hmac.new(_chave(), e.encode("utf-8"), hashlib.sha256).hexdigest()[:32] if e else ""


def _pessoa(p: dict) -> dict:
    """A linha guardada de uma pessoa (a do `api.ler_pessoal` ou a do REST, já no mesmo formato): o id, o código, o nome, se
    está ativa, a conta (quem cria OS: "criadas por mim") e o HMAC do e-mail no lugar dele. O nome da conta do "Criado por"
    não mora aqui: o Histórico o lê por pessoa (`api.get_pessoas_contas`, revisão da 4.1)."""
    return {"id_personnel": p.get("id_personnel"), "code": p.get("code"), "name": str(p.get("name") or "").strip(),
            "active": p.get("active"), "id_account": p.get("id_account"), "email_h": _hash_email(p.get("email"))}


def preparar_pessoas(linhas) -> list:
    """As linhas guardadas do pessoal (`_pessoa`), do RPC ou do REST (`catalogos_leitor`)."""
    return [_pessoa(p) for p in (linhas or []) if isinstance(p, dict)]


def ativas(linhas) -> list:
    """O pessoal ATIVO, por nome, na forma das telas: [{'code','name','id_personnel'}]. Das linhas do catálogo (`pessoas`) ou
    das do `api.ler_pessoal` (a criação da Engenharia, que confere ao vivo: `api.responsaveis_ao_vivo`)."""
    out = [{"code": p.get("code"), "name": str(p.get("name") or "").strip(), "id_personnel": p.get("id_personnel")}
           for p in (linhas or []) if str(p.get("name") or "").strip() and p.get("active") is not False]
    out.sort(key=lambda x: x["name"].lower())
    return out


def _pessoas_para_disco(v) -> list:
    """O pessoal como vai ao disco: sem e-mail nenhum. A pessoa sem nome no Fracttal aparece nas telas pelo e-mail (o
    `full_name` dela é o e-mail): esse nome não vai ao disco em claro, e depois de um reinício ela some das listas até a
    próxima leitura (revisão da 4.1). E, sem a chave da ponte, sem o HMAC (o de agora não valeria no próximo processo)."""
    chave = bool(_CHAVE_EMAIL["v"])
    return [dict(p, email_h=p.get("email_h") if chave else "",
                 name=p.get("name") if "@" not in str(p.get("name") or "") else "") for p in v]


def _falhas_completas(d) -> bool:
    """As três listas do "O ativo falhou?": sem uma delas o COS recusa toda OS de falha. A leitura com uma lista vazia (a cota
    no meio, a sessão sem a permissão) não troca a cópia completa (revisão da 4.1: um 429 nas causas guardava `{"causas": []}`
    por 24 h)."""
    return isinstance(d, dict) and all(d.get(k) for k in ("tipos", "causas", "metodos"))


ASSUNTOS = {a.nome: a for a in (
    _Assunto("pessoas", "Pessoas", "ler_pessoal", bool, _lista_de_dicts, preparar=preparar_pessoas,
             para_disco=_pessoas_para_disco),
    _Assunto("etiquetas", "Etiquetas", "get_labels", bool, _lista_de_dicts),
    _Assunto("tipos", "Tipos e classificações da OS", "get_tipos_classif",
             lambda t: isinstance(t, dict) and bool(t.get("tipos") or t.get("c1")), _listas("tipos", "c1", "c2"),
             contar=_contar_listas),
    _Assunto("tipos_solicitacao", "Grupo e classificações da solicitação", "get_request_types",
             lambda t: isinstance(t, dict) and bool(t.get("classif1")), _listas("grupo", "classif1", "classif2"),
             contar=_contar_listas),
    # o `get_falha_listas` engole o erro de cada lista (a tela de antes seguia com o que veio); aqui ele levanta, e o erro de
    # verdade (a cota, a sessão) fica no estado e na tela
    _Assunto("falhas", "Falhas (COS)", "get_falha_listas", _falhas_completas, _listas("tipos", "causas", "metodos"),
             kwargs={"levantar": True}, contar=_contar_listas),
    # o `status_solicitacao_catalogo` devolve a lista local quando o Fracttal falha (cancelar não pode depender da rede): aqui
    # ele levanta, para a lista local não ficar guardada 24 h como se fosse o que o Fracttal aceita (`status` a devolve sem guardar)
    _Assunto("status", "Status da solicitação", "status_solicitacao_catalogo", bool, _status_forma,
             kwargs={"levantar": True}, do_disco=lambda v: [tuple(t) for t in v]),
    _Assunto("motivos", "Motivos de cancelamento", "get_cancel_motivos", bool, _lista_de_dicts),
)}

_TRAVA = threading.Lock()               # o estado de todos (instalar, renovar, o REST)
_CONFIG: dict = {"pasta": None}
_GERACAO = [0]                          # o reinício (os testes) no meio de uma leitura: ela não instala nada depois
# quem está renovando cada assunto por trás e quando tentou (`renovar_por_tras`)
_VEZ: dict = {"renovando": set(), "tentou": {}}
# o REST das pessoas: a última leitura que valeu e a última que falhou (vão ao `estado.json`, sobrevivem ao reinício)
_REST: dict = {"bom_em": 0.0, "falha_em": 0.0, "falha": None}
# o leitor do servidor (`catalogos_leitor.ligar`, só pelo servir.py) se registra aqui: se está ligado e o estado dele
_LEITOR: dict = {"ligado": False, "estado": None}
# {HMAC do e-mail: quando}: a pessoa logada que não estava no catálogo e o fez reler pelo RPC (`da_pessoa`, uma vez a cada
# `ESPERA_TENTATIVA_S`)
_FALTOU: dict = {}


def configurar(pasta: str | None, chave: bytes | None = None) -> None:
    """Onde mora a cópia em disco (`<pasta>/<assunto>.json`) e a chave do HMAC do e-mail das pessoas. Quem chama é a ponte do
    Nexus (`ponte.ligar_catalogos`); nos testes ela não chama: sem pasta, os catálogos vivem só na memória. O assunto que ainda
    não tem nada na memória lê o disco na próxima vez."""
    with _TRAVA:
        _CONFIG["pasta"] = pasta
        if chave != _CHAVE_EMAIL["v"]:
            # o HMAC de quem já está na memória foi feito com a chave de antes: com ele ninguém seria achado nem iria certo
            # ao disco (a ponte liga antes de qualquer tela, então isto é só a defesa)
            ASSUNTOS["pessoas"].limpar()
            _FALTOU.clear()
        _CHAVE_EMAIL["v"] = chave
        for a in ASSUNTOS.values():
            if a.valor is None:
                a.boot = False
    planos = sys.modules.get("catalogos_planos")
    if planos is not None:
        planos.configurado()
    _ler_estado_rest()


def reiniciar(pasta: str | None = None, chave: bytes | None = None) -> None:
    """Volta ao processo recém-subido (os testes, e quem reconfigura): nada na memória (os planos também), nenhuma renovação
    valendo, o leitor das pessoas desligado, com a pasta e a chave que vierem."""
    with _TRAVA:
        _GERACAO[0] += 1
        _CONFIG["pasta"] = pasta
        _CHAVE_EMAIL["v"] = chave
        for a in ASSUNTOS.values():
            a.limpar()
        _VEZ["renovando"].clear()
        _VEZ["tentou"].clear()
        _FALTOU.clear()
        _REST.update(bom_em=0.0, falha_em=0.0, falha=None)
        _LEITOR.update(ligado=False, estado=None)
    for nome in ("catalogos_planos", "catalogos_leitor"):              # os companheiros, se já carregados
        mod = sys.modules.get(nome)
        if mod is not None:
            mod.reiniciar()
    _ler_estado_rest()


# ── o disco ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def arquivo(nome: str) -> str | None:
    """O arquivo da cópia em disco de um assunto (`pessoas`, ..., `planos`, `planos_detalhe`), ou None sem pasta."""
    return os.path.join(_CONFIG["pasta"], "%s.json" % nome) if _CONFIG["pasta"] else None


def hora(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts), _BRT).strftime("%d/%m %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def escrever_json(destino: str, carga: dict) -> None:
    """Uma cópia em disco, escrita ao lado e trocada de uma vez (`canto_disco`)."""
    def escrever(tmp):
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(carga, f, ensure_ascii=False, separators=(",", ":"))
    _trocar_de_uma_vez(destino, escrever)


def ler_json(arq: str, nome: str) -> dict:
    """O JSON de uma cópia, conferido (formato e nome). Levanta ValueError/OSError com o motivo."""
    with open(arq, encoding="utf-8") as f:
        carga = json.load(f)
    if not isinstance(carga, dict) or carga.get("formato") != FORMATO:
        raise ValueError("formato %r, o esperado é %d" % (carga.get("formato") if isinstance(carga, dict) else None, FORMATO))
    if carga.get("nome") != nome:
        raise ValueError("a cópia é de %r, não de %r" % (carga.get("nome"), nome))
    return carga


def _gravar(a: _Assunto) -> None:
    """A cópia em disco do valor VIGENTE (lido dentro da trava do disco, e não o que pediu a gravação: duas leituras terminando
    em ordem trocada não deixam a velha no disco). Pula o que o disco já tem. Falha de disco vai ao log e ao estado; o
    catálogo segue na memória."""
    destino = arquivo(a.nome)
    if destino is None:
        return
    with a.trava_disco:
        valor, lido_em, fonte, seq = a.valor, a.lido_em, a.fonte, a.seq
        if valor is None or a.disco["seq"] == seq:
            return
        carga = {"formato": FORMATO, "nome": a.nome, "fonte": fonte, "lido_em": lido_em, "gravado_em": _relogio(),
                 "chave": _id_da_chave() if a.nome == "pessoas" and _CHAVE_EMAIL["v"] else None,
                 "valor": a.para_disco(valor) if a.para_disco else valor}
        try:
            escrever_json(destino, carga)
            a.disco.update(gravado_em=carga["gravado_em"], lido_em=lido_em, seq=seq, erro=None)
        except Exception as e:                                          # noqa: BLE001 — o disco não derruba o catálogo
            a.disco["erro"] = "gravar: %s: %s" % (type(e).__name__, str(e)[:120])
            log.warning("catálogos: não gravei a cópia de %s (%s)", a.nome, a.disco["erro"])


def _ler_disco(a: _Assunto):
    """(valor, lido_em, fonte) da cópia em disco, ou None: sem arquivo, ilegível, cortada, de outro formato ou vazia (o motivo
    fica no estado). Nunca levanta."""
    arq = arquivo(a.nome)
    if arq is None or not os.path.exists(arq):
        return None
    try:
        carga = ler_json(arq, a.nome)
        valor = carga.get("valor")
        if not a.forma(valor):
            raise ValueError("o catálogo dentro não tem a forma esperada")
        valor = a.do_disco(valor) if a.do_disco else valor
        if not a.serve(valor):
            raise ValueError("o catálogo dentro está vazio")
        if a.nome == "pessoas" and carga.get("chave") != _id_da_chave():
            # o HMAC do e-mail foi feito com outra chave (a NEXUS_SECRET_KEY trocou, ou a cópia é de antes da ponte): com ela
            # ninguém seria achado ("criadas por mim" e "atribuídas" sem dono até a próxima leitura); relê-se, uma vez
            raise ValueError("a cópia das pessoas é de outra chave do e-mail")
        return valor, float(carga["lido_em"]), str(carga.get("fonte") or "")
    except (OSError, ValueError, TypeError, KeyError) as e:     # UnicodeError e JSONDecodeError são ValueError
        a.disco["erro"] = "ler: %s: %s" % (type(e).__name__, str(e)[:120])
        log.warning("catálogos: ignorei a cópia em disco de %s (%s)", a.nome, a.disco["erro"])
        return None


def _boot(a: _Assunto) -> None:
    """A cópia em disco, uma vez por processo (quem chega com o boot em curso espera nele: são milissegundos). Nunca o
    Fracttal: a cópia vencida volta como está, e a renovação é a de sempre (por trás)."""
    if a.boot:
        return
    with a.trava_boot:
        if a.boot:
            return
        try:
            carga = _ler_disco(a)
            if carga is not None:
                valor, lido_em, fonte = carga
                with _TRAVA:
                    if a.valor is None:
                        a.valor, a.lido_em, a.fonte = valor, lido_em, fonte
                        a.disco.update(lido="cópia de %s" % hora(lido_em), lido_em=lido_em)
        finally:
            a.boot = True


# ── a leitura ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def motivo_do_erro(e: BaseException) -> str:
    return "%s: %s" % (type(e).__name__, str(e)[:200])


def sessao_de_uma_pessoa(e: BaseException) -> bool:
    """A sessão recusada de UMA pessoa (o login que caiu) não é falha do Fracttal: não segura a tentativa de mais ninguém."""
    return bool(getattr(e, "session_expired", False))


def _ler_do_fracttal(a: _Assunto):
    import api
    fn = getattr(api, a.leitor)
    return fn(**a.kwargs) if a.kwargs else fn()


def instalar(nome: str, valor, fonte: str, ger: int, lido_em: float | None = None) -> bool:
    """Põe no lugar o valor de um assunto (já preparado) e grava a cópia em disco. False se um reinício (os testes) aconteceu
    no meio da leitura (`ger`): ela não vale mais."""
    a = ASSUNTOS[nome]
    with _TRAVA:
        if ger != _GERACAO[0]:
            return False                                         # um reinício no meio da leitura: ela não vale mais
        a.valor, a.lido_em, a.fonte = valor, _relogio() if lido_em is None else lido_em, fonte
        a.erro, a.erro_em, a.boot = None, 0.0, True
        a.seq += 1
    _gravar(a)
    return True


def _ler_agora(a: _Assunto, ger: int | None = None):
    """Lê do Fracttal (o RPC, com a sessão do contexto), guarda o que serve e devolve o que veio. O erro sobe (quem chama
    decide), fica anotado e não guarda nada; o vazio volta sem ficar guardado."""
    ger = _GERACAO[0] if ger is None else ger
    try:
        bruto = _ler_do_fracttal(a)
    except Exception as e:
        with _TRAVA:
            if ger == _GERACAO[0]:
                a.erro, a.erro_em = motivo_do_erro(e), _relogio()
        raise
    valor = a.preparar(bruto) if a.preparar else bruto
    with _TRAVA:
        a.leituras += 1
    if a.serve(valor):
        instalar(a.nome, valor, "rpc", ger)
    else:
        with _TRAVA:
            a.vazias += 1
            a.erro, a.erro_em = "a leitura veio vazia (a sessão sem a permissão no Fracttal?): não foi guardada", _relogio()
    return valor


def rest_valendo(agora: float | None = None) -> bool:
    """O laço do servidor está renovando as pessoas pelo REST: ligado, a última leitura REST valeu, nenhuma falhou depois, e ela
    tem no máximo o prazo e a folga (o laço que parou devolve as pessoas ao socorro pelo RPC)."""
    agora = _relogio() if agora is None else agora
    r = _REST
    return bool(_LEITOR["ligado"]) and r["bom_em"] > r["falha_em"] and \
        agora - r["bom_em"] <= PRAZO_S["pessoas"] + FOLGA_REST_S


def _prazo(a: _Assunto, agora: float) -> float:
    if a.nome == "pessoas" and a.fonte == "rest" and rest_valendo(agora):
        return PRAZO_S["pessoas"] + FOLGA_REST_S
    return PRAZO_S[a.nome]


def _vencido(a: _Assunto, agora: float) -> bool:
    return agora - a.lido_em > _prazo(a, agora)


# ── a renovação por trás (uma só para os assuntos, os planos e os detalhes) ──────────────────────────────────────────────
def esquecer_tentativas(vez: dict, agora: float) -> None:
    """As tentativas de renovação que já passaram da janela saem (dentro da trava de quem chama): sem isso a conta cresceria com
    cada ativo pedido, para sempre."""
    for k in [k for k, t in vez["tentou"].items() if agora - t >= ESPERA_TENTATIVA_S]:
        del vez["tentou"][k]


def _cota(e: BaseException) -> bool:
    return bool(_COTA.search(str(e)))


def _na_sessao_propria(fn, *args):
    """`fn` com um estado de sessão PRÓPRIO, na cópia do contexto de quem pediu (o mesmo JWT e o mesmo e-mail): a cópia leva o
    MESMO dicionário de estado do pedido dela, e um 401 por trás o marcava como morto, e o pedido dela, se ainda corria, saía
    para o login (revisão da 4.1). Quem separa é o `api._na_sessao_propria` (o `os_web.sessao.propria`, que a web instala)."""
    import api
    return api._na_sessao_propria(fn, *args)


def _renovar_uma(ctx, vez, alvos, i, ler_uma, ger, trava) -> bool:
    """Uma chave da renovação por trás, na cópia do contexto e com a sessão própria. False: a renovação para (a sessão de quem
    pediu caiu, ou a cota do Fracttal não voltou)."""
    for espera in ESPERAS_COTA_S + (None,):
        try:
            ctx.run(_na_sessao_propria, ler_uma, alvos[i], ger)
            return True
        except Exception as e:                                       # noqa: BLE001 — fica a cópia de antes, e o erro anotado
            if sessao_de_uma_pessoa(e):
                # a sessão de UMA pessoa não é falha do Fracttal: esta chave e as que faltavam voltam a ser de quem chegar
                with trava:
                    for ch in alvos[i:]:
                        vez["tentou"].pop(ch, None)
                return False
            if not _cota(e):
                return True                                          # outra falha: fica a cópia de antes desta, e segue
            if espera is None:
                return False                                         # a cota não voltou: o que falta espera a janela
            _dormir(espera)
    return False


def renovar_por_tras(vez: dict, chaves, ler_uma, *, trava, depois=None) -> list:
    """A renovação por trás de algumas chaves (um assunto, os planos de alguns ativos, um detalhe de plano), numa thread, com a
    cópia do contexto de quem as achou vencidas (o JWT dela e a rota dela no contador do Fracttal) e um estado de sessão
    próprio (`_na_sessao_propria`), uma por vez: quem chega com a renovação em curso usa a cópia velha e não espera. `vez` =
    {"renovando": set, "tentou": {chave: quando}}: cada chave uma vez por `ESPERA_TENTATIVA_S` (a que falhou espera).
    O RITMO (revisão da 4.1): 1 pedido por segundo entre as chaves (`PAUSA_S`, como os leitores do servidor); o 406/429
    espera `ESPERAS_COTA_S` e tenta a mesma chave de novo, e a cota que não voltou para a renovação; a sessão caída de UMA
    pessoa para a renovação e solta a vez da chave e das que faltavam (outra sessão tenta já). `ler_uma(chave, ger)` lê e
    guarda uma chave, e levanta o erro; `depois()` roda no fim, também depois de parar (a gravação dos planos). Devolve as
    chaves que começou (vazio: nada a fazer)."""
    agora = _relogio()
    with trava:
        esquecer_tentativas(vez, agora)
        alvos = [ch for ch in chaves if ch not in vez["renovando"] and agora - vez["tentou"].get(ch, 0.0) >= ESPERA_TENTATIVA_S]
        for ch in alvos:
            vez["renovando"].add(ch)
            vez["tentou"][ch] = agora
        ger = _GERACAO[0]
    if not alvos:
        return []
    ctx = contextvars.copy_context()

    def rodar():
        try:
            for i in range(len(alvos)):
                if ger != _GERACAO[0]:
                    return
                if i:
                    _dormir(PAUSA_S)
                if not _renovar_uma(ctx, vez, alvos, i, ler_uma, ger, trava):
                    break
            if depois is not None and ger == _GERACAO[0]:
                depois()
        finally:
            with trava:
                if ger == _GERACAO[0]:
                    vez["renovando"].difference_update(alvos)
    _em_segundo_plano(rodar)
    return alvos


def _renovar_por_tras(a: _Assunto) -> bool:
    """A renovação do assunto vencido (`renovar_por_tras`). As pessoas, com o REST valendo, ficam para o laço do servidor. True
    se começou."""
    if a.nome == "pessoas" and rest_valendo():
        return False
    return bool(renovar_por_tras(_VEZ, [a.nome], lambda nome, ger: _ler_agora(ASSUNTOS[nome], ger), trava=_TRAVA))


def _obter(nome: str, reler: bool = False):
    """O valor de um assunto (o MESMO objeto para todos; as funções públicas copiam). Na memória e em dia: volta. Vencido: volta
    como está, e a renovação vai por trás. Sem nada (nem na memória, nem no disco): lê agora, e quem chega junto espera a mesma
    leitura. `reler`: quem não achou o que procura relê agora, se o catálogo tem mais que `RELER_NA_FALTA_S`."""
    a = ASSUNTOS[nome]
    _boot(a)
    v = a.valor
    agora = _relogio()
    if v is not None and not (reler and agora - a.lido_em > RELER_NA_FALTA_S):
        if _vencido(a, agora):
            _renovar_por_tras(a)
        return v
    with a.trava:
        w = a.valor
        if w is not None and (v is None or w is not v):
            return w                                             # outro pedido leu enquanto este esperava a vez
        try:
            novo = _ler_agora(a)
        except Exception:
            if w is not None:
                return w                                         # a releitura de quem não achou falhou: fica o de antes
            raise
        # a releitura que veio vazia (a sessão sem a permissão) não apaga o catálogo de quem perguntou
        return w if (w is not None and not a.serve(novo)) else novo


# ── o que as telas leem (a mesma forma do `api` de antes, em cópia) ─────────────────────────────────────────────────────────
def pessoas(reler: bool = False) -> list:
    """O pessoal ATIVO, por nome: [{'code','name','id_personnel'}] (o `api.get_responsaveis` de antes)."""
    return ativas(_obter("pessoas", reler))


def _achar(linhas, h: str):
    for p in linhas or []:
        if p.get("email_h") == h:
            return (p.get("id_personnel"), p.get("id_account"), p.get("name") or "")
    return None


def da_pessoa(email) -> tuple:
    """(id_personnel, id_account, nome) de quem tem este e-mail no Fracttal, ou (None, None, "") (o `api._current_user_info`
    de antes, que relia o pessoal uma vez por pessoa e por processo).
    A PESSOA QUE NÃO ESTÁ NO CATÁLOGO (a conta nova no Fracttal) relê o pessoal pelo RPC, com a sessão DELA, na hora, uma vez
    por pessoa a cada `ESPERA_TENTATIVA_S`, e não com o catálogo recém-lido (`RELER_NA_FALTA_S`). Com o REST valendo, a
    renovação das pessoas é só do laço do servidor (05h, 11h, 17h e 23h): até a revisão da 4.1 a conta nova ficava até 6 h sem
    "criadas por mim"."""
    h = _hash_email(email)
    if not h:
        return (None, None, "")
    achou = _achar(_obter("pessoas"), h)
    if achou is not None:
        return achou
    agora, a = _relogio(), ASSUNTOS["pessoas"]
    if a.valor is None or agora - a.lido_em <= RELER_NA_FALTA_S:
        return (None, None, "")                                  # o pessoal acabou de ser lido: ela não está no Fracttal
    with _TRAVA:
        for k in [k for k, t in _FALTOU.items() if agora - t >= ESPERA_TENTATIVA_S]:
            del _FALTOU[k]
        if h in _FALTOU:
            return (None, None, "")
        _FALTOU[h] = agora
    return _achar(_obter("pessoas", reler=True), h) or (None, None, "")


def nome_por_id() -> dict:
    """{id_personnel: nome} do pessoal ativo (o nome do responsável no card, `api._personnel_nome_por_id`)."""
    return {p["id_personnel"]: p["name"] for p in pessoas() if p.get("id_personnel") is not None}


def pessoas_guardadas() -> tuple:
    """(as linhas guardadas do pessoal, de onde vieram), sem ler o Fracttal (só o disco, se ainda não houve boot): a conferência
    da leitura REST (`catalogos_leitor`) compara com elas."""
    a = ASSUNTOS["pessoas"]
    _boot(a)
    return a.valor, a.fonte


def etiquetas(reler: bool = False) -> list:
    """As etiquetas habilitadas: [{'id','description','color'}] (o `api.get_labels`)."""
    return copy.deepcopy(_obter("etiquetas", reler))


def tipos_classif(reler: bool = False) -> dict:
    """{'tipos','c1','c2'} da OS (o `api.get_tipos_classif`)."""
    return copy.deepcopy(_obter("tipos", reler))


def tipos_solicitacao() -> dict:
    """{'grupo','classif1','classif2'} da Nova solicitação (o `api.get_request_types`)."""
    return copy.deepcopy(_obter("tipos_solicitacao"))


def falhas() -> dict:
    """{'tipos','causas','metodos'} do "O ativo falhou?" do COS (o `api.get_falha_listas`)."""
    return copy.deepcopy(_obter("falhas"))


def status() -> list:
    """[(id, código, rótulo)] do que o Fracttal aceita na solicitação (o `api.status_solicitacao_catalogo`). Sem conseguir
    ler, ou com o Fracttal respondendo a lista vazia, a lista local, que NÃO fica guardada como catálogo: perder a rede não
    pode impedir a pessoa de cancelar uma solicitação. Até 31/10/2026 a lista local ficava 30 min na cópia da Fila; agora, sem
    catálogo nenhum, a falha (ou o vazio) só faz o Fracttal ser tentado de novo depois de `ESPERA_TENTATIVA_S` (cada Fila
    aberta com o Fracttal fora não vira um pedido)."""
    import api
    a = ASSUNTOS["status"]
    _boot(a)
    if a.valor is None and a.erro_em and _relogio() - a.erro_em < ESPERA_TENTATIVA_S:
        return list(api.STATUS_SOLICITACAO)
    try:
        v = _obter("status")
    except Exception as e:                                          # noqa: BLE001 — como antes: a lista local
        if sessao_de_uma_pessoa(e):
            with _TRAVA:
                a.erro_em = 0.0                                     # a sessão caída de uma pessoa não segura as outras
        return list(api.STATUS_SOLICITACAO)
    return list(v) if v else list(api.STATUS_SOLICITACAO)


def motivos() -> list:
    """Os motivos de cancelamento de OS: [{'id','description'}] (o `api.get_cancel_motivos`)."""
    return copy.deepcopy(_obter("motivos"))


# ── o REST das pessoas: o que o leitor do servidor registra aqui ───────────────────────────────────────────────────────────
def ligar_leitor(*, ligado: bool, estado=None) -> None:
    """O laço das pessoas pelo REST (`catalogos_leitor.ligar`, só pelo servir.py) se registra: se está ligado (sem a credencial
    ele registra só o `estado`, para o motivo aparecer) e a função do estado dele, para o Raio-X."""
    _LEITOR.update(ligado=bool(ligado), estado=estado)


def rest_bom_em() -> float:
    """Quando a última leitura REST das pessoas valeu (0 = nunca): a 1ª precisa do catálogo do RPC para conferir."""
    return float(_REST["bom_em"] or 0.0)


def anotar_leitura_rest(ok: bool, motivo: str = "") -> None:
    """Uma leitura REST das pessoas que valeu (`ok`) ou que falhou (o motivo). Vai ao `estado.json`: o reinício não esquece."""
    agora = _relogio()
    with _TRAVA:
        if ok:
            _REST.update(bom_em=agora)
        else:
            _REST.update(falha_em=agora, falha=str(motivo or "")[:300])
    _gravar_estado_rest()


def _gravar_estado_rest() -> None:
    destino = arquivo(NOME_ESTADO[:-5])
    if destino is None:
        return
    carga = {"formato": FORMATO, "nome": NOME_ESTADO[:-5], "rest": {k: _REST.get(k) for k in ("bom_em", "falha_em", "falha")}}
    try:
        escrever_json(destino, carga)
    except Exception as e:                                          # noqa: BLE001
        log.warning("catálogos: não gravei o %s (%s)", NOME_ESTADO, motivo_do_erro(e))


def _ler_estado_rest() -> None:
    """A última leitura REST das pessoas de antes do reinício (a boa e a falha): sem ela, cada deploy faria o RPC renovar as
    pessoas que o laço do servidor renova."""
    arq = arquivo(NOME_ESTADO[:-5])
    if arq is None or not os.path.exists(arq):
        return
    try:
        r = ler_json(arq, NOME_ESTADO[:-5]).get("rest") or {}
        with _TRAVA:
            for k in ("bom_em", "falha_em"):
                if isinstance(r.get(k), (int, float)):
                    _REST[k] = float(r[k])
            if r.get("falha"):
                _REST["falha"] = str(r["falha"])[:300]
    except (OSError, ValueError, TypeError, KeyError) as e:
        log.warning("catálogos: ignorei o %s (%s)", NOME_ESTADO, motivo_do_erro(e))


# ── o aquecimento do boot ──────────────────────────────────────────────────────────────────────────────────────────────
def aquecer(esperar: bool = False) -> None:
    """Lê as cópias em disco de todos os assuntos e dos planos, por trás (a ponte chama ao ligar): a 1ª tela não paga o disco.
    Só o disco, nunca o Fracttal. `esperar`: na thread de quem chamou (os testes)."""
    def rodar():
        for a in ASSUNTOS.values():
            try:
                _boot(a)
            except Exception:                                       # noqa: BLE001
                log.exception("catálogos: o aquecimento de %s falhou", a.nome)
        try:
            import catalogos_planos
            catalogos_planos.aquecer()
        except Exception:                                           # noqa: BLE001
            log.exception("catálogos: o aquecimento dos planos falhou")
    if esperar:
        rodar()
    else:
        threading.Thread(target=rodar, name="os-catalogos-aquecer", daemon=True).start()


# ── o estado, para o Raio-X ────────────────────────────────────────────────────────────────────────────────────────────
def estado() -> dict:
    """O que se sabe de cada catálogo, só com contagens, datas e motivos (nunca um nome nem um e-mail): a fonte (rpc, pela
    sessão de quem usa; rest, pela credencial da empresa), quando foi lido, a idade, o prazo, se venceu e está renovando, a
    última falha, quantas leituras do Fracttal neste processo e a cópia em disco; os planos e os detalhes da Performance
    (`catalogos_planos`); e o laço das pessoas pelo REST (o que ele registrou, `ligar_leitor`). Faz o boot do disco de cada um
    (o Raio-X quer ver o que voltou depois de um deploy)."""
    agora = _relogio()
    assuntos = []
    for a in ASSUNTOS.values():
        _boot(a)
        tem = a.valor is not None
        assuntos.append({"nome": a.nome, "rotulo": a.rotulo, "fonte": a.fonte if tem else None,
                         "lido_em": a.lido_em if tem else None, "idade_s": agora - a.lido_em if tem else None,
                         "prazo_s": _prazo(a, agora), "vencido": tem and _vencido(a, agora),
                         "n": a.contar(a.valor) if tem else 0, "erro": a.erro, "erro_em": a.erro_em or None,
                         "renovando": a.nome in _VEZ["renovando"], "leituras": a.leituras, "disco": dict(a.disco)})
    import catalogos_planos
    planos, detalhes = catalogos_planos.estado()
    ligado = bool(_LEITOR["ligado"])
    rest = {"ligado": ligado, "motivo": "" if ligado else "não ligado (só o servir.py liga o laço das pessoas pelo REST)",
            "credencial": None, "proxima": None, "ultima": None}
    if _LEITOR["estado"] is not None:
        try:
            rest.update(_LEITOR["estado"]())
        except Exception as e:                                      # noqa: BLE001 — o estado nunca derruba quem o lê
            rest["motivo"] = "o estado do leitor falhou: %s" % motivo_do_erro(e)
    rest.update({k: _REST.get(k) for k in ("bom_em", "falha_em", "falha")}, valendo=rest_valendo(agora))
    return {"assuntos": assuntos, "planos": planos, "detalhes": detalhes, "rest": rest}
