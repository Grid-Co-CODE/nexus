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
abaixo devolvem cópias, no formato do `api` de antes).
- O BOOT SÓ LÊ O DISCO, nunca o Fracttal, nem com a cópia vencida (`aquecer`, por trás, ao ligar a ponte; e a 1ª leitura de cada
  assunto, se o aquecimento ainda não chegou). A cópia ilegível, cortada ou de outro formato é ignorada, e o motivo fica em
  `estado()`. O vencido é renovado DEPOIS, pela regra abaixo.
- QUEM RENOVA. As pessoas, com o leitor da empresa: o REST `personnel` do cadastro (`nexus/cadastro/fracttal_pessoal.py`), pela
  credencial da empresa, às 05h, 11h, 17h e 23h no minuto `minutos_ocupados.CATALOGOS_PESSOAS` (só o `servir.py` liga o laço:
  `ligar`), e só se o REST trouxer os campos que as telas usam e bater com o RPC (`ler_pessoas_rest`). O resto (e as pessoas
  sem o REST valendo: o PC, a credencial que falta, o REST sem os campos) não tem leitor da empresa: o RPC exige a sessão de
  uma pessoa (`os_web/sessao.py`). Então a 1ª sessão que acha o catálogo vencido o renova POR TRÁS, uma vez para todos, com a
  cópia do contexto (que leva o JWT dela), como o `api._renovar_catalogo_por_tras` dos ativos; quem chega com a renovação em
  curso usa a cópia velha e não espera. Sem cópia nenhuma (a máquina nova, o disco ilegível), a 1ª tela lê na hora, e quem
  chega junto espera a MESMA leitura (`_Assunto.trava`).
- O ERRO E O VAZIO NÃO FICAM GUARDADOS (a regra de 20/10/2026 dos catálogos de tela): a lista vazia da sessão de alguém sem a
  permissão no Fracttal esvaziaria a tela de todo mundo pelo prazo inteiro.
- QUEM RELÊ NA HORA: só quem não achou o que procura (`reler=True`, o tipo da Zeladoria criado hoje, a pessoa nova que a tela
  da Engenharia mostrou, a etiqueta da lista), uma vez por `RELER_NA_FALTA_S`, com a sessão de quem pediu.
- AS PESSOAS sem o e-mail: em disco e na memória vai o HMAC do e-mail (`email_h`, com a chave que a ponte deriva da do Nexus),
  e a pessoa logada é achada por ele (`da_pessoa`). O nome, o código e os ids são os que a lista de OS em disco já guarda. A
  cópia feita com outra chave é ignorada (ninguém seria achado) e o pessoal é relido uma vez.
- O REST DAS PESSOAS É CONFERIDO a cada leitura: os campos que as telas usam (`CAMPOS_REST`), a 1ª que vale contra um catálogo
  do RPC (a lista de responsáveis em comum) e nenhuma que encolhe demais; senão nada muda, e o estado diz por quê.

OS PLANOS DA PERFORMANCE (`planos_dos_ativos`, `detalhe_do_plano`) ficam por ATIVO, e não por grupo de tarefas: o RPC é
perguntado por `id_item` (os eventos são do ativo; o plano do tracker mora só no generalizado, e a estação tem planos que o
inversor não tem, `api.get_performance_alvos`), e nada no código mostra dois ativos do mesmo `id_group_task` respondendo o
mesmo. Guardar por grupo ofereceria a um ativo um plano que talvez ele não tenha.

Este módulo não importa o `api` ao carregar (o `api` o importa): os leitores são chamados pelo nome, no `api`, na hora da
leitura (os testes trocam o `api.<leitor>` e o catálogo lê o dublê).
"""
from __future__ import annotations

import contextlib
import contextvars
import copy
import hashlib
import hmac
import json
import logging
import os
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
FALTA_PESSOA_S = _H             # a pessoa logada que não está no catálogo pede a renovação por trás se ele tem mais que isto
FOLGA_REST_S = _H               # com o REST valendo, as pessoas só vencem 1 h depois do prazo: o laço das :MM pode atrasar
PAUSA_S = 1.0                   # em segundo plano, 1 pedido por segundo (como os leitores dos ativos e da lista de OS)
CAMPOS_MIN_PCT = 99.0           # do pessoal do REST, as linhas que trazem cada campo que as telas usam
PARIDADE_MIN_PCT = 95.0         # da lista de responsáveis, o que o REST e o RPC têm em comum (nos dois sentidos)
ENCOLHE_MAX_PCT = 10            # o REST com menos pessoas que isto do catálogo de agora não troca (página perdida)
# os planos guardados, por ativo: a carteira tem ~2.850 inversores e estações (~190 usinas). Medido com 8 planos por ativo e os
# nomes num objeto só (`_texto`): ~5,7 MB na memória e 1,7 MB em disco com a carteira inteira; os de 7 dias sem uso saem
PLANOS_MAX = 3000
# os detalhes de plano (o resumo da Performance, um por usina e plano escolhidos; sem o `raw`): medido, ~25 KB cada com 30
# subtarefas, 3,6 MB com 150
DETALHES_MAX = 150
GUARDA_S = 7 * 24 * _H          # o plano que ninguém pediu em 7 dias sai da cópia
NOME_ESTADO = "estado.json"     # o REST das pessoas (a última boa, a última falha), que sobrevive ao reinício
CHAVE = "oscreator_catalogos"
# o laço das pessoas pelo REST (só o servidor): as horas de Brasília e o minuto da lista única de minutos ocupados do Nexus
HORAS = (5, 11, 17, 23)
_BRT = timezone(timedelta(hours=-3))
_BRT_S = -3 * _H

_relogio = time.time            # os testes trocam (o prazo, a idade)
_dormir = time.sleep            # e a pausa entre as páginas do REST


def _em_segundo_plano(fn) -> None:
    """Onde a renovação por trás roda: uma thread solta (os testes trocam para rodar quando querem)."""
    threading.Thread(target=fn, name="os-catalogos-por-tras", daemon=True).start()


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
        self.erro, self.erro_em, self.tentou, self.renovando = None, 0.0, 0.0, False
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
    está ativa, a conta (quem cria OS) e o nome da conta no "Criado por" (o nome, ou o e-mail de quem não tem nome, como o
    `get_pessoas_contas` sempre mostrou), e o HMAC do e-mail no lugar dele."""
    nome = str(p.get("name") or "").strip()
    return {"id_personnel": p.get("id_personnel"), "code": p.get("code"), "name": nome, "active": p.get("active"),
            "id_account": p.get("id_account"), "nome_conta": str(p.get("nome_conta") or nome).strip(),
            "email_h": _hash_email(p.get("email"))}


def _preparar_pessoas(linhas) -> list:
    return [_pessoa(p) for p in (linhas or []) if isinstance(p, dict)]


def _pessoas_para_disco(v) -> list:
    """O pessoal como vai ao disco: sem e-mail nenhum. O nome da conta de quem não tem nome no Fracttal (o "Criado por" mostra
    o e-mail dela) não vai: depois de um reinício ela some do filtro até a próxima leitura. E, sem a chave da ponte, sem o
    HMAC (o de agora não valeria no próximo processo)."""
    chave = bool(_CHAVE_EMAIL["v"])
    return [dict(p, email_h=p.get("email_h") if chave else "",
                 nome_conta=p.get("nome_conta") if "@" not in str(p.get("nome_conta") or "") else "") for p in v]


ASSUNTOS = {a.nome: a for a in (
    _Assunto("pessoas", "Pessoas", "ler_pessoal", bool, _lista_de_dicts, preparar=_preparar_pessoas,
             para_disco=_pessoas_para_disco),
    _Assunto("etiquetas", "Etiquetas", "get_labels", bool, _lista_de_dicts),
    _Assunto("tipos", "Tipos e classificações da OS", "get_tipos_classif",
             lambda t: isinstance(t, dict) and bool(t.get("tipos") or t.get("c1")), _listas("tipos", "c1", "c2"),
             contar=_contar_listas),
    _Assunto("tipos_solicitacao", "Grupo e classificações da solicitação", "get_request_types",
             lambda t: isinstance(t, dict) and bool(t.get("classif1")), _listas("grupo", "classif1", "classif2"),
             contar=_contar_listas),
    _Assunto("falhas", "Falhas (COS)", "get_falha_listas", lambda d: isinstance(d, dict) and bool(d.get("tipos")),
             _listas("tipos", "causas", "metodos"), contar=_contar_listas),
    # o `status_solicitacao_catalogo` devolve a lista local quando o Fracttal falha (cancelar não pode depender da rede): aqui
    # ele levanta, para a lista local não ficar guardada 24 h como se fosse o que o Fracttal aceita (`status` a devolve sem guardar)
    _Assunto("status", "Status da solicitação", "status_solicitacao_catalogo", bool, _status_forma,
             kwargs={"levantar": True}, do_disco=lambda v: [tuple(t) for t in v]),
    _Assunto("motivos", "Motivos de cancelamento", "get_cancel_motivos", bool, _lista_de_dicts),
)}

_TRAVA = threading.Lock()               # o estado de todos (instalar, renovar, o REST)
_CONFIG: dict = {"pasta": None}
_GERACAO = [0]                          # o reinício (os testes) no meio de uma leitura: ela não instala nada depois


def _estado_rest() -> dict:
    return {"ligado": False, "motivo": "não ligado (só o servir.py liga o laço das pessoas pelo REST)", "credencial": None,
            "bom_em": 0.0, "falha_em": 0.0, "falha": None, "ultima": None}


_REST: dict = _estado_rest()
_APP: dict = {"app": None}


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
        _CHAVE_EMAIL["v"] = chave
        for a in ASSUNTOS.values():
            if a.valor is None:
                a.boot = False
        for p in (_PLANOS, _DETALHES):
            if not p["itens"]:
                p["boot"] = False
    _ler_estado_rest()


def reiniciar(pasta: str | None = None, chave: bytes | None = None) -> None:
    """Volta ao processo recém-subido (os testes, e quem reconfigura): nada na memória, nenhuma renovação valendo, o REST
    desligado, com a pasta e a chave que vierem."""
    with _TRAVA:
        _GERACAO[0] += 1
        _CONFIG["pasta"] = pasta
        _CHAVE_EMAIL["v"] = chave
        for a in ASSUNTOS.values():
            a.limpar()
        for p in (_PLANOS, _DETALHES):
            p.clear()
            p.update(_por_chave_limpo())
        _TEXTOS.clear()
        _REST.clear()
        _REST.update(_estado_rest())
        _APP["app"] = None
    _ler_estado_rest()


# ── o disco ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def arquivo(nome: str) -> str | None:
    """O arquivo da cópia em disco de um assunto (`pessoas`, ..., `planos`, `planos_detalhe`), ou None sem pasta."""
    return os.path.join(_CONFIG["pasta"], "%s.json" % nome) if _CONFIG["pasta"] else None


def _hora(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts), _BRT).strftime("%d/%m %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def _escrever_json(destino: str, carga: dict) -> None:
    def escrever(tmp):
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(carga, f, ensure_ascii=False, separators=(",", ":"))
    _trocar_de_uma_vez(destino, escrever)


def _ler_json(arq: str, nome: str) -> dict:
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
            _escrever_json(destino, carga)
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
        carga = _ler_json(arq, a.nome)
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
                        a.disco.update(lido="cópia de %s" % _hora(lido_em), lido_em=lido_em)
        finally:
            a.boot = True


# ── a leitura ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _motivo(e: BaseException) -> str:
    return "%s: %s" % (type(e).__name__, str(e)[:200])


def _sessao_de_uma_pessoa(e: BaseException) -> bool:
    """A sessão recusada de UMA pessoa (o login que caiu) não é falha do Fracttal: não segura a tentativa de mais ninguém."""
    return bool(getattr(e, "session_expired", False))


def _ler_do_fracttal(a: _Assunto):
    import api
    fn = getattr(api, a.leitor)
    return fn(**a.kwargs) if a.kwargs else fn()


def _instalar(a: _Assunto, valor, fonte: str, ger: int, lido_em: float | None = None) -> bool:
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
                a.erro, a.erro_em = _motivo(e), _relogio()
        raise
    valor = a.preparar(bruto) if a.preparar else bruto
    with _TRAVA:
        a.leituras += 1
    if a.serve(valor):
        _instalar(a, valor, "rpc", ger)
    else:
        with _TRAVA:
            a.vazias += 1
            a.erro, a.erro_em = "a leitura veio vazia (a sessão sem a permissão no Fracttal?): não foi guardada", _relogio()
    return valor


def _rest_valendo(agora: float) -> bool:
    """O laço do servidor está renovando as pessoas pelo REST: ligado, a última leitura REST valeu, nenhuma falhou depois, e ela
    tem no máximo o prazo e a folga (o laço que parou devolve as pessoas ao socorro pelo RPC)."""
    r = _REST
    return bool(r["ligado"]) and r["bom_em"] > r["falha_em"] and agora - r["bom_em"] <= PRAZO_S["pessoas"] + FOLGA_REST_S


def _prazo(a: _Assunto, agora: float) -> float:
    if a.nome == "pessoas" and a.fonte == "rest" and _rest_valendo(agora):
        return PRAZO_S["pessoas"] + FOLGA_REST_S
    return PRAZO_S[a.nome]


def _vencido(a: _Assunto, agora: float) -> bool:
    return agora - a.lido_em > _prazo(a, agora)


def _renovar_por_tras(a: _Assunto) -> bool:
    """A renovação do catálogo vencido, numa thread, com a sessão de quem o achou vencido (a cópia do contexto leva o JWT e a
    rota dela no contador do Fracttal), uma por vez e uma por `ESPERA_TENTATIVA_S` (a que falhou espera; a sessão caída de UMA
    pessoa não segura ninguém). As pessoas, com o REST valendo, ficam para o laço do servidor. True se começou."""
    agora = _relogio()
    with _TRAVA:
        if a.renovando or agora - a.tentou < ESPERA_TENTATIVA_S:
            return False
        if a.nome == "pessoas" and _rest_valendo(agora):
            return False
        a.renovando, a.tentou = True, agora
        ger = _GERACAO[0]
    ctx = contextvars.copy_context()

    def rodar():
        try:
            ctx.run(_ler_agora, a, ger)
        except Exception as e:                                       # noqa: BLE001 — fica a cópia de antes, e o erro anotado
            if _sessao_de_uma_pessoa(e):
                with _TRAVA:
                    a.tentou = 0.0
        finally:
            with _TRAVA:
                if ger == _GERACAO[0]:
                    a.renovando = False
    _em_segundo_plano(rodar)
    return True


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
    out = [{"code": p.get("code"), "name": p["name"], "id_personnel": p.get("id_personnel")}
           for p in _obter("pessoas", reler) if p.get("name") and p.get("active") is not False]
    out.sort(key=lambda x: x["name"].lower())
    return out


def contas() -> list:
    """Quem cria OS e solicitação, para o "Criado por": [{'id_account','nome'}] por nome, com quem está desligado (o
    `api.get_pessoas_contas()["pessoas"]` de antes)."""
    vistos: dict = {}
    for p in _obter("pessoas"):
        ida = p.get("id_account")
        if ida is not None and ida not in vistos:
            nome = str(p.get("nome_conta") or "").strip()
            if nome:
                vistos[ida] = nome
    return sorted(({"id_account": k, "nome": v} for k, v in vistos.items()), key=lambda x: x["nome"].lower())


def da_pessoa(email) -> tuple:
    """(id_personnel, id_account, nome) de quem tem este e-mail no Fracttal, ou (None, None, "") (o `api._current_user_info`
    de antes, que relia o pessoal uma vez por pessoa e por processo). A pessoa que não está num catálogo de mais de 1 h pede a
    renovação por trás (a conta nova no Fracttal)."""
    h = _hash_email(email)
    if not h:
        return (None, None, "")
    for p in _obter("pessoas"):
        if p.get("email_h") == h:
            return (p.get("id_personnel"), p.get("id_account"), p.get("name") or "")
    a = ASSUNTOS["pessoas"]
    if a.valor is not None and _relogio() - a.lido_em > FALTA_PESSOA_S:
        _renovar_por_tras(a)
    return (None, None, "")


def nome_por_id() -> dict:
    """{id_personnel: nome} do pessoal ativo (o nome do responsável no card, `api._personnel_nome_por_id`)."""
    return {p["id_personnel"]: p["name"] for p in pessoas() if p.get("id_personnel") is not None}


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
    ler, a lista local, que NÃO fica guardada como catálogo: perder a rede não pode impedir a pessoa de cancelar uma
    solicitação. Até 31/10/2026 a lista local ficava 30 min na cópia da Fila; agora, sem catálogo nenhum, a falha só faz o
    Fracttal ser tentado de novo depois de `ESPERA_TENTATIVA_S` (cada Fila aberta com o Fracttal fora não vira um pedido)."""
    import api
    a = ASSUNTOS["status"]
    _boot(a)
    if a.valor is None and a.erro_em and _relogio() - a.erro_em < ESPERA_TENTATIVA_S:
        return list(api.STATUS_SOLICITACAO)
    try:
        return list(_obter("status"))
    except Exception as e:                                          # noqa: BLE001 — como antes: a lista local
        if _sessao_de_uma_pessoa(e):
            with _TRAVA:
                a.erro_em = 0.0                                     # a sessão caída de uma pessoa não segura as outras
        return list(api.STATUS_SOLICITACAO)


def motivos() -> list:
    """Os motivos de cancelamento de OS: [{'id','description'}] (o `api.get_cancel_motivos`)."""
    return copy.deepcopy(_obter("motivos"))


# ── os planos da Performance, por ativo ────────────────────────────────────────────────────────────────────────────────
def _por_chave_limpo() -> dict:
    return {"itens": {}, "boot": False, "renovando": set(), "tentou": {}, "leituras": 0, "erro": None, "erro_em": 0.0,
            "disco": {"lido": None, "gravado_em": 0.0, "erro": None}}


_PLANOS: dict = _por_chave_limpo()      # {"<id_item>:<id_group_task>": {"lido_em", "planos": [{id_task, description}]}}
_DETALHES: dict = _por_chave_limpo()    # {"<id_task>:<id_item>": {"lido_em", "detalhe": o get_plan_details sem o raw}}
_TRAVA_PLANOS = threading.Lock()


def chave_plano(id_item, id_group_task) -> str:
    return "%s:%s" % (id_item, id_group_task)


_TEXTOS: dict = {}


def _planos_enxutos(planos) -> list:
    """Os planos de um ativo como ficam guardados: o id e o nome, com UM objeto para cada nome (os mesmos ~30 nomes de plano se
    repetem em milhares de ativos: medido, 7,4 MB contra 5,7 MB com a carteira inteira)."""
    return [{"id_task": p.get("id_task"), "description": _TEXTOS.setdefault(p.get("description"), p.get("description"))
             if isinstance(p.get("description"), str) else p.get("description")} for p in planos if isinstance(p, dict)]


def _boot_por_chave(store: dict, nome: str, campo: str) -> None:
    if store["boot"]:
        return
    with _TRAVA_PLANOS:
        if store["boot"]:
            return
        store["boot"] = True
        arq = arquivo(nome)
        if arq is None or not os.path.exists(arq):
            return
        try:
            carga = _ler_json(arq, nome)
            itens = carga.get("itens")
            if not isinstance(itens, dict):
                raise ValueError("sem os itens")
            bons = {k: v for k, v in itens.items() if isinstance(v, dict) and isinstance(v.get("lido_em"), (int, float))
                    and isinstance(v.get(campo), (list, dict))}
            for k, v in bons.items():
                if campo == "planos":
                    v = {"lido_em": v["lido_em"], "planos": _planos_enxutos(v["planos"])}
                store["itens"].setdefault(k, v)
            store["disco"]["lido"] = "cópia gravada em %s (%d)" % (_hora(carga.get("gravado_em")), len(bons))
        except (OSError, ValueError, TypeError, KeyError) as e:
            store["disco"]["erro"] = "ler: %s: %s" % (type(e).__name__, str(e)[:120])
            log.warning("catálogos: ignorei a cópia em disco de %s (%s)", nome, store["disco"]["erro"])


def _gravar_por_chave(store: dict, nome: str, maximo: int) -> None:
    """A cópia em disco dos planos (ou dos detalhes): os mais recentes até `maximo`, sem os de mais de 7 dias."""
    destino = arquivo(nome)
    agora = _relogio()
    with _TRAVA_PLANOS:
        vivos = sorted(((k, v) for k, v in store["itens"].items() if agora - v["lido_em"] <= GUARDA_S),
                       key=lambda kv: kv[1]["lido_em"], reverse=True)[:maximo]
        store["itens"] = dict(vivos)
        carga = {"formato": FORMATO, "nome": nome, "gravado_em": agora, "itens": dict(vivos)}
    if destino is None:
        return
    try:
        _escrever_json(destino, carga)
        store["disco"].update(gravado_em=agora, erro=None)
    except Exception as e:                                          # noqa: BLE001
        store["disco"]["erro"] = "gravar: %s: %s" % (type(e).__name__, str(e)[:120])
        log.warning("catálogos: não gravei a cópia de %s (%s)", nome, store["disco"]["erro"])


def _esquecer_tentativas(store: dict, agora: float) -> None:
    """As tentativas de renovação que já passaram da janela saem (dentro da `_TRAVA_PLANOS`): sem isso a conta cresceria com
    cada ativo pedido, para sempre."""
    for k in [k for k, t in store["tentou"].items() if agora - t >= ESPERA_TENTATIVA_S]:
        del store["tentou"][k]


def _renovar_planos_por_tras(ativos: list) -> None:
    """Os planos vencidos destes ativos, relidos numa thread com a sessão de quem os pediu, um ativo depois do outro; quem os
    pedir enquanto isso recebe os de antes. O que falha espera `ESPERA_TENTATIVA_S`."""
    agora = _relogio()
    with _TRAVA_PLANOS:
        _esquecer_tentativas(_PLANOS, agora)
        alvos = []
        for a in ativos:
            ch = chave_plano(a.get("id"), a.get("id_group_task"))
            if ch in _PLANOS["renovando"] or agora - _PLANOS["tentou"].get(ch, 0.0) < ESPERA_TENTATIVA_S:
                continue
            _PLANOS["renovando"].add(ch)
            _PLANOS["tentou"][ch] = agora
            alvos.append((ch, a))
        ger = _GERACAO[0]
    if not alvos:
        return
    ctx = contextvars.copy_context()

    def rodar():
        import api
        mudou = False
        try:
            for ch, a in alvos:
                try:
                    planos = ctx.run(api.ler_planos_do_ativo, a.get("id"), a.get("id_group_task"))
                except Exception as e:                               # noqa: BLE001 — fica o de antes
                    with _TRAVA_PLANOS:
                        _PLANOS["erro"], _PLANOS["erro_em"] = _motivo(e), _relogio()
                    continue
                with _TRAVA_PLANOS:
                    if ger != _GERACAO[0]:
                        return
                    _PLANOS["leituras"] += 1
                    if planos:
                        _PLANOS["itens"][ch] = {"lido_em": _relogio(), "planos": _planos_enxutos(planos)}
                    else:
                        _PLANOS["itens"].pop(ch, None)           # o ativo sem plano agora: sai, e a próxima escolha relê
                    mudou = True
            if mudou and ger == _GERACAO[0]:
                _gravar_por_chave(_PLANOS, "planos", PLANOS_MAX)
        finally:
            with _TRAVA_PLANOS:
                if ger == _GERACAO[0]:
                    _PLANOS["renovando"].difference_update(ch for ch, _a in alvos)
    _em_segundo_plano(rodar)


def planos_dos_ativos(ativos: list) -> dict:
    """{chave do ativo: [{'id_task','description'}]} dos planos de tarefa de cada ativo (o `task_events_list` por `id_item` e
    `id_group_task`, como o `api.get_plans_for_assets` lê), ou None no ativo cuja leitura falhou (o `api` o trata como "sem
    plano", como sempre). O que está guardado e em dia volta sem pedido nenhum; o vencido volta como está e é relido por trás;
    o que falta é lido agora, até 8 de uma vez, com a sessão de quem pediu (o executor do `api` leva o contexto). A lista vazia
    não fica guardada (pode ser a sessão sem a permissão). Grava a cópia em disco uma vez no fim."""
    import api
    _boot_por_chave(_PLANOS, "planos", "planos")
    agora = _relogio()
    out, faltam, vencidos = {}, [], []
    with _TRAVA_PLANOS:
        for a in ativos:
            ch = chave_plano(a.get("id"), a.get("id_group_task"))
            item = _PLANOS["itens"].get(ch)
            if item is None:
                faltam.append(a)
                continue
            out[ch] = item["planos"]
            if agora - item["lido_em"] > PRAZO_S["planos"]:
                vencidos.append(a)
    if faltam:
        ger = _GERACAO[0]

        def ler(a):
            try:
                return a, api.ler_planos_do_ativo(a.get("id"), a.get("id_group_task"))
            except api.FracttalError as e:
                return a, e
        with api._ExecutorComContexto(max_workers=8) as ex:
            lidos = list(ex.map(ler, faltam))
        novos = 0
        with _TRAVA_PLANOS:
            for a, r in lidos:
                ch = chave_plano(a.get("id"), a.get("id_group_task"))
                if isinstance(r, Exception):
                    out[ch] = None
                    _PLANOS["erro"], _PLANOS["erro_em"] = _motivo(r), _relogio()
                    continue
                out[ch] = r
                _PLANOS["leituras"] += 1
                if r and ger == _GERACAO[0]:
                    _PLANOS["itens"][ch] = {"lido_em": _relogio(), "planos": _planos_enxutos(r)}
                    novos += 1
        if novos:
            _gravar_por_chave(_PLANOS, "planos", PLANOS_MAX)
    if vencidos:
        _renovar_planos_por_tras(vencidos)
    return {ch: ([dict(p) for p in v] if v is not None else None) for ch, v in out.items()}


def plano(id_item, id_group_task=None) -> list:
    """Os planos de UM ativo: [{'id_task','description'}] (vazio quando a leitura falhou ou ele não tem plano)."""
    v = planos_dos_ativos([{"id": id_item, "id_group_task": id_group_task}]).get(chave_plano(id_item, id_group_task))
    return v or []


def _renovar_detalhe_por_tras(ch: str, id_task, id_item) -> None:
    agora = _relogio()
    with _TRAVA_PLANOS:
        _esquecer_tentativas(_DETALHES, agora)
        if ch in _DETALHES["renovando"] or agora - _DETALHES["tentou"].get(ch, 0.0) < ESPERA_TENTATIVA_S:
            return
        _DETALHES["renovando"].add(ch)
        _DETALHES["tentou"][ch] = agora
        ger = _GERACAO[0]
    ctx = contextvars.copy_context()

    def rodar():
        try:
            ctx.run(_ler_detalhe, ch, id_task, id_item, ger)
        except Exception as e:                                       # noqa: BLE001 — fica o de antes
            with _TRAVA_PLANOS:
                _DETALHES["erro"], _DETALHES["erro_em"] = _motivo(e), _relogio()
        finally:
            with _TRAVA_PLANOS:
                if ger == _GERACAO[0]:
                    _DETALHES["renovando"].discard(ch)
    _em_segundo_plano(rodar)


def _ler_detalhe(ch: str, id_task, id_item, ger: int) -> dict:
    import api
    det = {k: v for k, v in (api.get_plan_details(id_task, id_item) or {}).items() if k != "raw"}
    with _TRAVA_PLANOS:
        _DETALHES["leituras"] += 1
        guardar = bool(det.get("subtasks") or det.get("description")) and ger == _GERACAO[0]
        if guardar:
            _DETALHES["itens"][ch] = {"lido_em": _relogio(), "detalhe": det}
    if guardar:
        _gravar_por_chave(_DETALHES, "planos_detalhe", DETALHES_MAX)
    return det


def detalhe_do_plano(id_task, id_item) -> dict:
    """O detalhe de um plano para o resumo da Performance (o `api.get_plan_details`, SEM o `raw`: o resumo não o usa e ele
    repetiria as subtarefas na memória), em cópia. Guardado e em dia: sem pedido; vencido: volta e é relido por trás; sem
    ele: lido agora (o erro sobe, como antes)."""
    _boot_por_chave(_DETALHES, "planos_detalhe", "detalhe")
    ch = "%s:%s" % (id_task, id_item)
    with _TRAVA_PLANOS:
        item = _DETALHES["itens"].get(ch)
    if item is not None:
        if _relogio() - item["lido_em"] > PRAZO_S["detalhes"]:
            _renovar_detalhe_por_tras(ch, id_task, id_item)
        return copy.deepcopy(item["detalhe"])
    try:
        return copy.deepcopy(_ler_detalhe(ch, id_task, id_item, _GERACAO[0]))
    except Exception as e:
        with _TRAVA_PLANOS:
            _DETALHES["erro"], _DETALHES["erro_em"] = _motivo(e), _relogio()
        raise


# ── o aquecimento do boot ──────────────────────────────────────────────────────────────────────────────────────────────
def aquecer(esperar: bool = False) -> None:
    """Lê as cópias em disco de todos os assuntos, por trás (a ponte chama ao ligar): a 1ª tela não paga o disco. Só o disco,
    nunca o Fracttal. `esperar`: na thread de quem chamou (os testes)."""
    def rodar():
        for a in ASSUNTOS.values():
            try:
                _boot(a)
            except Exception:                                       # noqa: BLE001
                log.exception("catálogos: o aquecimento de %s falhou", a.nome)
        _boot_por_chave(_PLANOS, "planos", "planos")
        _boot_por_chave(_DETALHES, "planos_detalhe", "detalhe")
    if esperar:
        rodar()
    else:
        threading.Thread(target=rodar, name="os-catalogos-aquecer", daemon=True).start()


# ── as pessoas pelo REST da empresa (só o servidor) ────────────────────────────────────────────────────────────────────
# Os campos que as telas usam do pessoal, e os nomes com que o REST pode trazê-los. O cadastro (`fracttal_pessoal.da_api`)
# conhece do REST `personnel` o id, o código, o nome, o e-mail, o acesso e a conta ativa; o `active` (o pessoal ATIVO, a lista
# das telas) e o `id_account` (quem criou a OS: "criadas por mim" e o "Criado por") nunca foram vistos lá. A sondagem não pôde
# ser feita antes de construir (este computador não lê o Fracttal com a credencial da empresa): é esta conferência, a cada
# leitura, que a faz. Faltou um, a leitura não troca nada, e o estado diz qual.
CAMPOS_REST = (("id_personnel", ("id_personnel",)), ("code", ("code",)), ("nome", ("full_name", "name")),
               ("active", ("active",)), ("id_account", ("id_account",)), ("email", ("email", "account_email")))


class _Recusa(RuntimeError):
    """A leitura REST que veio, mas não serve (sem os campos, sem bater com o RPC, encolhida): nada muda."""


def campos_que_faltam(linhas: list) -> list:
    """Os campos de `CAMPOS_REST` que vêm em menos de `CAMPOS_MIN_PCT` das linhas (a chave, mesmo com o valor vazio)."""
    if not linhas:
        return [n for n, _c in CAMPOS_REST]
    faltam = []
    for nome, chaves in CAMPOS_REST:
        tem = sum(1 for p in linhas if any(k in p for k in chaves))
        if tem * 100 < len(linhas) * CAMPOS_MIN_PCT:
            faltam.append(nome)
    return faltam


def de_rest(p: dict) -> dict:
    """Uma pessoa do REST no formato do `api.ler_pessoal` (o do RPC chama o id de `id`; o REST, de `id_personnel`)."""
    nome = str(p.get("full_name") or p.get("name") or "").strip()
    return {"id_personnel": p.get("id_personnel"), "code": p.get("code"), "name": nome, "active": p.get("active"),
            "id_account": p.get("id_account"),
            "nome_conta": str(p.get("full_name") or p.get("name") or p.get("account_email") or "").strip(),
            "email": str(p.get("account_email") or p.get("email") or "").strip().lower()}


def _ids_responsaveis(linhas) -> set:
    return {p.get("id_personnel") for p in linhas if p.get("name") and p.get("active") is not False}


def _confere(novas: list) -> str:
    """O motivo de a leitura REST não servir, ou "". Encolheu demais contra o catálogo de agora (página perdida); ou é a 1ª
    contra um catálogo do RPC e a lista de responsáveis não bate com a dele (o mesmo campo com outro sentido mudaria quem as
    telas mostram). A 1ª leitura REST que já valeu precisa desse catálogo para conferir (a 1ª noite dos ativos, REST x RPC):
    sem ele (a máquina nova, sem cópia), espera a 1ª tela que o lê pela sessão de alguém."""
    a = ASSUNTOS["pessoas"]
    _boot(a)
    atual = a.valor
    if not atual:
        if not _REST["bom_em"]:
            return "ainda não há o catálogo do RPC para conferir a 1ª leitura REST (a 1ª tela o lê pela sessão de quem usa)"
        return ""
    if len(novas) * 100 < len(atual) * (100 - ENCOLHE_MAX_PCT):
        return "o REST trouxe %d pessoas e o catálogo tem %d (encolheu mais que %d%%)" % (len(novas), len(atual),
                                                                                           ENCOLHE_MAX_PCT)
    if a.fonte != "rpc":
        return ""
    r, n = _ids_responsaveis(atual), _ids_responsaveis(novas)
    comum = len(r & n)
    if r and n and comum * 100 >= len(r) * PARIDADE_MIN_PCT and comum * 100 >= len(n) * PARIDADE_MIN_PCT:
        return ""
    return ("o pessoal ativo do REST (%d) não bate com o do RPC (%d): %d em comum, abaixo de %d%% nos dois sentidos" % (
        len(n), len(r), comum, PARIDADE_MIN_PCT))


@contextlib.contextmanager
def _origem(assunto: str):
    """O laço conta no contador do Fracttal com o nome dele (`fundo:nexus-catalogos:<assunto>`)."""
    try:
        from nexus.casca import fracttal_conta
    except Exception:                                               # noqa: BLE001 — sem o contador, a leitura segue
        yield
        return
    with fracttal_conta.origem("fundo:nexus-catalogos:" + assunto):
        yield


def _anotar_rest(ok: bool, motivo: str = "") -> None:
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
    carga = {"formato": FORMATO, "nome": NOME_ESTADO[:-5],
             "rest": {k: _REST.get(k) for k in ("bom_em", "falha_em", "falha")}}
    try:
        _escrever_json(destino, carga)
    except Exception as e:                                          # noqa: BLE001
        log.warning("catálogos: não gravei o %s (%s)", NOME_ESTADO, _motivo(e))


def _ler_estado_rest() -> None:
    """A última leitura REST das pessoas de antes do reinício (a boa e a falha): sem ela, cada deploy faria o RPC renovar as
    pessoas que o laço do servidor renova."""
    arq = arquivo(NOME_ESTADO[:-5])
    if arq is None or not os.path.exists(arq):
        return
    try:
        r = _ler_json(arq, NOME_ESTADO[:-5]).get("rest") or {}
        with _TRAVA:
            for k in ("bom_em", "falha_em"):
                if isinstance(r.get(k), (int, float)):
                    _REST[k] = float(r[k])
            if r.get("falha"):
                _REST["falha"] = str(r["falha"])[:300]
    except (OSError, ValueError, TypeError, KeyError) as e:
        log.warning("catálogos: ignorei o %s (%s)", NOME_ESTADO, _motivo(e))


def ler_pessoas_rest(ler=None) -> dict:
    """As pessoas pelo REST `personnel` do cadastro (`fracttal_pessoal.ler_paginas`, o cliente e o ritmo do
    `nexus/campo/fracttal.py`), pela credencial da empresa, 1 pedido por segundo, contadas como `fundo:nexus-catalogos:pessoas`.
    Troca o catálogo só se a leitura trouxe os campos que as telas usam (`CAMPOS_REST`) e passou na conferência (`_confere`);
    senão nada muda, o motivo vai ao estado, e as pessoas seguem pelo RPC quando vencerem. Devolve o relatório."""
    rel = {"inicio": _relogio(), "fim": None, "pedidos": 0, "linhas": 0, "resultado": "", "erro": ""}
    conta = [0]
    if ler is None:
        from nexus.campo import fracttal
        ler = fracttal.ler

    def contando(path):
        if conta[0]:
            _dormir(PAUSA_S)
        conta[0] += 1
        return ler(path)
    ger = _GERACAO[0]
    try:
        with _origem("pessoas"):
            from nexus.cadastro import fracttal_pessoal
            brutas = [p for p in fracttal_pessoal.ler_paginas(contando) if isinstance(p, dict)]
        rel["linhas"] = len(brutas)
        faltam = campos_que_faltam(brutas)
        if faltam:
            raise _Recusa("o REST do pessoal não trouxe %s (as telas usam): as pessoas seguem pelo RPC" % ", ".join(faltam))
        valor = _preparar_pessoas([de_rest(p) for p in brutas])
        motivo = _confere(valor)
        if motivo:
            raise _Recusa(motivo + ": fica o catálogo do RPC")
        if not _instalar(ASSUNTOS["pessoas"], valor, "rest", ger):
            raise _Recusa("o processo reiniciou no meio da leitura")
        _anotar_rest(True)
        rel["resultado"] = "%d pessoas pelo REST" % len(valor)
    except _Recusa as e:
        rel["erro"] = rel["resultado"] = str(e)
        _anotar_rest(False, str(e))
        log.warning("catálogos: as pessoas pelo REST: %s", e)
    except Exception as e:                                          # noqa: BLE001 — Fracttal fora, credencial, cota: fica o de antes
        rel["erro"] = _motivo(e)
        rel["resultado"] = "nada mudou: " + rel["erro"]
        _anotar_rest(False, rel["erro"])
        log.warning("catálogos: as pessoas pelo REST falharam (%s)", rel["erro"])
    finally:
        rel.update(pedidos=conta[0], fim=_relogio())
        _REST["ultima"] = rel
    return rel


def proximo_passo(agora: float) -> float:
    """Os segundos até a próxima leitura das pessoas pelo REST: às `HORAS` de Brasília, no minuto da lista única de minutos
    ocupados (`minutos_ocupados.CATALOGOS_PESSOAS`). Estando no instante de uma, a próxima é a seguinte."""
    local = agora + _BRT_S
    dia0 = (local // 86400) * 86400
    cands = [dia0 + d * 86400 + h * _H + MINUTO * 60 for d in (0, 1) for h in HORAS]
    return min(t for t in cands if t > local) - local


def _laco() -> None:
    while True:
        _dormir(proximo_passo(_relogio()))
        app = _APP["app"]
        try:
            with app.app_context():
                rel = ler_pessoas_rest()
            log.info("catálogos: as pessoas pelo REST: %s (%d pedidos)", rel["resultado"], rel["pedidos"])
        except Exception:                                           # noqa: BLE001 — o laço nunca derruba o Nexus
            log.exception("catálogos: o laço das pessoas quebrou")


def ligar(app) -> None:
    """Liga o laço das pessoas pelo REST neste app (SÓ o `servir.py`, o servidor): diz aos catálogos onde mora a cópia em disco
    (`ponte.ligar_catalogos`, o mesmo que a criação do clone faz) e abre o laço (fora dos testes). Sem a credencial REST do
    Fracttal, não liga: o estado diz por quê, e as pessoas seguem pelo RPC, com a sessão de quem usa. Ligar de novo no mesmo app
    não faz nada."""
    if CHAVE in app.extensions:
        return
    app.extensions[CHAVE] = _REST
    try:
        from nexus.torres.oscreator import ponte
        ponte.ligar_catalogos(app)
    except Exception:                                               # noqa: BLE001 — sem a pasta, os catálogos vivem na memória
        log.exception("catálogos: não liguei a pasta de dados")
    from nexus.pcm.geracao import credencial
    cred = credencial(app.config)
    if not cred.ok:
        _REST.update(ligado=False, motivo="sem a credencial REST do Fracttal (FRACTTAL_CLIENT_ID e FRACTTAL_CLIENT_SECRET): "
                                          "as pessoas seguem pelo RPC, com a sessão de quem usa")
        log.warning("catálogos: %s", _REST["motivo"])
        return
    _APP["app"] = app
    _REST.update(ligado=True, motivo="", credencial=cred.onde)
    if not app.config.get("TESTING"):
        threading.Thread(target=_laco, name="nexus-catalogos", daemon=True).start()


def _minuto() -> int:
    from nexus.casca import minutos_ocupados
    return minutos_ocupados.CATALOGOS_PESSOAS


try:
    MINUTO = _minuto()
except Exception:                                                   # noqa: BLE001 — o clone servido sozinho (sem o Nexus)
    MINUTO = 4


# ── o estado, para o Raio-X ────────────────────────────────────────────────────────────────────────────────────────────
def estado() -> dict:
    """O que se sabe de cada catálogo, só com contagens, datas e motivos (nunca um nome nem um e-mail): a fonte (rpc, pela
    sessão de quem usa; rest, pela credencial da empresa), quando foi lido, a idade, o prazo, se venceu e está renovando, a
    última falha, quantas leituras do Fracttal neste processo e a cópia em disco; os planos e os detalhes da Performance; e o
    laço das pessoas pelo REST. Faz o boot do disco de cada um (o Raio-X quer ver o que voltou depois de um deploy)."""
    agora = _relogio()
    assuntos = []
    for a in ASSUNTOS.values():
        _boot(a)
        tem = a.valor is not None
        assuntos.append({"nome": a.nome, "rotulo": a.rotulo, "fonte": a.fonte if tem else None,
                         "lido_em": a.lido_em if tem else None, "idade_s": agora - a.lido_em if tem else None,
                         "prazo_s": _prazo(a, agora), "vencido": tem and _vencido(a, agora),
                         "n": a.contar(a.valor) if tem else 0, "erro": a.erro, "erro_em": a.erro_em or None,
                         "renovando": a.renovando, "leituras": a.leituras, "disco": dict(a.disco)})

    def por_chave(store, nome, campo, prazo):
        _boot_por_chave(store, nome, campo)
        with _TRAVA_PLANOS:
            idades = [v["lido_em"] for v in store["itens"].values()]
            return {"n": len(store["itens"]), "mais_velho": min(idades) if idades else None,
                    "mais_novo": max(idades) if idades else None,
                    "vencidos": sum(1 for t in idades if agora - t > prazo), "prazo_s": prazo,
                    "renovando": len(store["renovando"]), "leituras": store["leituras"], "erro": store["erro"],
                    "erro_em": store["erro_em"] or None, "disco": dict(store["disco"])}
    rest = {k: _REST.get(k) for k in ("ligado", "motivo", "credencial", "bom_em", "falha_em", "falha")}
    rest["valendo"] = _rest_valendo(agora)
    rest["proxima"] = agora + proximo_passo(agora) if rest["ligado"] else None
    ult = _REST.get("ultima")
    rest["ultima"] = dict(ult) if isinstance(ult, dict) else None
    return {"assuntos": assuntos, "planos": por_chave(_PLANOS, "planos", "planos", PRAZO_S["planos"]),
            "detalhes": por_chave(_DETALHES, "planos_detalhe", "detalhe", PRAZO_S["detalhes"]), "rest": rest}
