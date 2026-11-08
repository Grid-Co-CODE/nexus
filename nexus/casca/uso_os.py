"""O uso das telas do OS Creator por hora (31/10/2026, etapa 0 do canto central do OS Creator).

Em 13 e 14/10/2026 o OS Creator prendeu as threads do Nexus e ninguém soube dizer quais telas as pessoas abrem, a que
hora, em quantas, quanto cada uma demora e quanto pede ao Fracttal: o Raio-X mostra o momento, o log só o erro. Sem esse
número o "antes e depois" de cada etapa do canto central seria chute. Daqui saem as linhas por hora que o laço guarda no
disco e leva ao banco (`drenar`) e que o Raio-X mostra (`instantaneo`).

- **Uma linha por hora × rota × automático.** A hora é a de Brasília (`AAAAMMDDHH`), a do FIM do pedido, lida DENTRO da
  trava (o balde de uma hora que o `drenar` já tirou nunca renasce). `automatico` separa o clique da pessoa do que a tela pede sozinha (Histórico a cada 10
  min, Solicitações a cada 15, o `acompanhamento/estado`, a sessão a cada 5): o cabeçalho `X-Nexus-Auto: 1`, o
  `?nx_auto=1` (o formulário do Histórico não manda cabeçalho) ou, para a aba que ainda roda o JavaScript de antes, uma
  das `ROTAS_AUTOMATICAS`.
- **A rota é normalizada** (`normalizar_rota`): sem a query, número vira `<n>` e id opaco (hex, uuid, token) vira `<id>`,
  senão cada OS abriria uma linha nova. No máximo MAX_ROTAS rotas distintas por hora; as seguintes entram em `(outras)`.
- **O que conta:** todo pedido a `/os/*` e `/t/os/*` de quem entrou (`teto_os.do_os_creator` tira os estáticos e a
  pré-carga; sem sessão o portão manda ao login, e isso não é uso). Medido do `before_request` ao `teardown_request`: é o
  tempo até a resposta estar montada, não o do envio do corpo.
- **Pessoas distintas, sem guardar quem:** o HMAC do e-mail da sessão (`cadastro/ligacao_campo.codigo_da_pessoa`, com a
  chave das pessoas ou, sem ela, a do app) num conjunto só na memória, por balde. Nunca vai a disco nem ao banco, nem
  mesmo o código: o que sobra é a contagem. A senha de administrador não traz pessoa.
- **Duração:** um histograma de faixas de 3% por balde (só contagens, que somam e se gravam no disco sem guardar um
  tempo por pedido); a mediana e o p95 saem do centro da faixa, com erro de até 1,5%. Pedido que o teto recusou não tem
  duração (`None`): esperou a vaga, não foi atendido.
- **`erros_qtd`** são as respostas 5xx (ou a exceção) que a tela devolveu; **`ocupado_qtd`**, os 503 do teto
  (`casca/teto_os.py`), que nascem antes do Flask e chegam por `recusado`. As duas contas não se misturam, e os dois
  entram em `pedidos_qtd`.
- **`fracttal_qtd`:** quantos pedidos ao Fracttal o pedido fez (`fracttal_conta.pedidos_desta_thread()`, que inclui os das
  tarefas do fan-out que herdam o contexto). A mesma rota é a origem no contador do Fracttal, então dá para juntar o uso
  com o consumo da cota.
- **Toda rota do Flask marca a origem do Fracttal**, não só o OS Creator (31/10/2026): os pedidos que as telas do Campo, da
  Engenharia e do PCM fazem ao Fracttal caem na rota delas, e não em `fundo:waitress`. O uso só mede o OS Creator.
- **O reinício não perde a hora:** a cada 5 min (`PASSO_S`) os baldes, só contagens, vão a `casca/uso_os_parcial.json` na
  pasta de dados (atômico) e voltam no boot; a hora aberta segue de onde parou. `pessoas_qtd` depois de um reinício é
  aproximado: a soma dos dois lados, no máximo `pedidos_qtd` (quem veio antes e depois conta duas vezes).
- **O corte por setor** (`casca/uso_os_setor.json`, o setor da pessoa como o menu o acha, `setor_telas.acesso`, que já
  vem guardado): pedidos por dia × setor × rota, cliques e automáticos, só no disco do servidor e por 30 dias. **Nunca no
  banco:** há setor de uma ou duas pessoas, e "hora × rota × setor" diria o que ela fez e quando, num banco de leitura
  aberta que não apaga. Fica fora dele o pedido que o teto recusou (não tem sessão).
- **A memória não cresce:** as horas guardadas têm teto (MAX_HORAS, para o caso de ninguém drenar), como as rotas, os
  setores e o tamanho da rota.
- **O laço** (thread `nexus-uso-os-banco`, só com `gravar=True`: o servidor; nunca o PC nem os testes) tem dois passos, e
  é o Ruling M da controladora (31/10/2026): gravar o livro do mês inteiro no banco custa ~7 s de processador, e o Nexus é
  UM processo com o servidor já apertado, então não se faz de hora em hora.
  1. **No :05 de toda hora** (`drenar_para_o_disco`) tira as horas FECHADAS dos dois contadores (`drenar`, com a hora aberta
     lida UMA vez, antes dos dois) e as guarda no **pendente**, em `casca/uso_os_pendente.json` na pasta de dados
     (atômico: rascunho + `os.replace`). A memória dos contadores fica limitada, e o Raio-X lê o pendente. Depois do
     disco, `salvar()`: o parcial sem as horas que acabaram de sair.
  2. **Às 04:45 de Brasília, uma vez por dia** (`gravar_no_banco`) leva ao banco TUDO o que está pendente, agrupado pelo livro
     do mês de cada hora (`dados/fato_uso_os.py`: o mês que fechou ganha as últimas horas na primeira gravação depois da
     virada). Deu certo: anota a hora (`gravou_em`), as linhas gravadas saem do pendente (memória e disco) e `salvar()`
     roda. Deu errado (banco fora, leitura curta do livro, sem a chave): o pendente fica no disco e a gravação do dia
     seguinte leva tudo.
  **O pendente tem teto de 3 dias** (`MAX_HORAS_PENDENTES` = 72 horas, as mais novas; o banco fora por dias não enche o
  disco): as mais velhas saem, com aviso no log. **Reinício:** o pendente é relido no boot (arquivo quebrado é ignorado,
  com aviso, e a linha ruim não leva as boas; a mesma chave que o parcial velho traz de volta fica uma só, a mais nova).
  O que um reinício perde é só o que nunca saiu da memória: **a hora aberta do contador do Fracttal** (ele não guarda
  parcial em disco) e até 5 min do uso (o parcial é de 5 em 5). 04:45 não cai em cima de nenhum laço de hora em hora do
  Nexus (tarefas :10 a :20, normalizações :22, sync do App :25, zeladoria :32, carga :40, chamados :50), e o :05 também não.

Quem liga é o `servir.py` (o servidor), junto do `teto_os` e depois dele (é o teto que avisa o 503); o `create_app`, o PC
e os testes seguem sem isto. Os ganchos do Flask nunca derrubam o pedido: qualquer falha da medição vai ao log em debug.
"""
import contextlib
import json
import logging
import math
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl

from flask import current_app, request, session

from ..auth import setor_telas
from . import fracttal_conta, teto_os

log = logging.getLogger(__name__)

CHAVE = "nexus_uso_os"
CABECALHO_AUTO = "X-Nexus-Auto"                 # o que a tela manda quando pede sozinha (fetch)
_AMBIENTE_AUTO = "HTTP_X_NEXUS_AUTO"            # o mesmo cabeçalho no environ do WSGI
PARAMETRO_AUTO = "nx_auto"                      # o mesmo no endereço, para o formulário do Histórico (não manda cabeçalho)
# As perguntas que a página faz sozinha, e que existem em aba aberta com o JavaScript de antes (sem o cabeçalho): automáticas
# pela rota, de qualquer jeito. O `/os/historico/progresso` é o círculo de carga (`carga.js`) perguntando de 350 em 350 ms
# enquanto o Histórico busca: sem ele aqui seria a "rota mais clicada" por uma folga enorme.
ROTAS_AUTOMATICAS = frozenset({"/os/_nexus/sessao", "/os/chamados/acompanhamento/estado", "/os/historico/progresso"})
SEM_SETOR = "(sem setor)"
OUTRAS = "(outras)"
PASSO_S = 300                                   # o instantâneo em disco, de 5 em 5 minutos
MAX_HORAS = 48                                  # horas na memória sem ninguém drenar (o laço da gravação drena a cada hora)
DRENAR_NO_MINUTO = 5                            # o laço tira as horas fechadas dos contadores no :05 de cada hora
# e leva ao banco uma vez por dia, às 04:45 de Brasília (a hora mais parada). Era 03:45 até a revisão final de 31/10/2026: a
# noite de domingo da lista de OS (03:21, os 365 dias, 19 a 29 min) podia passar dela. Mora em `minutos_ocupados.USO_OS_BANCO`
# (um teste cruza as duas)
GRAVAR_NA_HORA, GRAVAR_NO_MINUTO = 4, 45
PASSO_DRENAR, PASSO_GRAVAR = "drenar", "gravar"
MAX_HORAS_PENDENTES = 72                        # 3 dias de horas já tiradas dos contadores que esperam o banco; as mais velhas saem
MAX_ROTAS = 200                                 # rotas distintas por hora (e por dia e setor no corte); o resto vai a OUTRAS
MAX_SETORES = 50                                # setores distintos por dia no corte
MAX_CARACTERES_DA_ROTA = 160
DIAS_SETOR = 30
ARQUIVO_PARCIAL = "uso_os_parcial.json"
ARQUIVO_SETOR = "uso_os_setor.json"
ARQUIVO_PENDENTE = "uso_os_pendente.json"       # as linhas que já saíram dos contadores e ainda não estão no banco
_BRT_S = -3 * 3600                              # Brasília é UTC-3 fixo (sem horário de verão desde 2019)
BASE = 1.03                                     # cada faixa da duração é 3% mais larga que a anterior
MAX_FAIXA = 450                                 # 1,03^450 ms = 10 min: o que passa disso cai na última faixa
_LOG_BASE = math.log(BASE)
_ENV = "nexus.uso_os"                           # onde o pedido em curso guarda a sua medição (no environ do próprio pedido)
_HORA_ID = re.compile(r"\d{10}")
_DIA_ID = re.compile(r"\d{8}")

_trava = threading.Lock()                       # a do estado: um pedido toma uma vez, no fim
_trava_disco = threading.Lock()                 # uma gravação em disco de cada vez (o laço e quem chamar `salvar`)
_horas: dict = {}                               # hora_id -> _Hora
_setor: dict = {}                               # dia -> setor -> rota -> [cliques, automáticos]
_estado: dict = {"gravar": False, "pasta": None, "config": None, "gravou_em": 0.0}
_trava_pendentes = threading.Lock()
_trava_gravacao = threading.Lock()              # uma volta de gravação por vez (o laço e quem mais chamar)
_pendentes: dict = {"uso": [], "fracttal": []}  # as linhas dos dois contadores que já saíram e ainda não chegaram ao banco
# a chave de cada linha (a mesma do fato): a que o parcial velho traz de volta depois de um reinício não repete a do pendente
_CHAVE_DA_LINHA = {"uso": lambda lin: (lin["hora_id"], lin["rota"], lin["automatico"]),
                   "fracttal": lambda lin: (lin["hora_id"], lin["origem"], lin["metodo"])}


def _agora() -> float:
    """O relógio (os testes o trocam: a hora de Brasília perto da meia-noite UTC não se espera acontecer)."""
    return time.time()


def _cronometro() -> float:
    return time.perf_counter()


# ── a rota normalizada ───────────────────────────────────────────────────────────────────────────────────────────────
_NUMERO = re.compile(r"[0-9]+")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_HEX = re.compile(r"[0-9a-fA-F]{8,}")
_PREFIXADO = re.compile(r"[A-Za-z]{1,3}-?[0-9a-fA-F]{8,}")      # `s` + uuid.hex[:11], `ev-` + 16 hex
_OPACO = re.compile(r"[A-Za-z0-9_-]{16,}")                      # secrets.token_urlsafe(12) em diante


def _segmento(s: str) -> str:
    if not s:
        return s
    if "@" in s:
        return "<id>"       # quem digita um e-mail no endereço não o deixa na rota: o banco é de leitura aberta e não apaga
    if _NUMERO.fullmatch(s):
        return "<n>"
    if _UUID.fullmatch(s) or _HEX.fullmatch(s):
        return "<id>"
    tem_digito = any(c in "0123456789" for c in s)
    # exige dígito: palavra de rota nunca tem (e "acompanhamento-de-chamados" tem 16+ letras e nenhum id)
    if tem_digito and (_PREFIXADO.fullmatch(s) or _OPACO.fullmatch(s)):
        return "<id>"
    return s


def normalizar_rota(caminho) -> str:
    """O caminho sem a query e sem o que muda a cada pedido: segmento só de dígitos vira `<n>` e id opaco (uuid, hex de 8 ou
    mais, token) vira `<id>`. `/os/os/16995?parcial=1` -> `/os/os/<n>`. Palavra de rota não muda (o teste varre todas as
    rotas do Nexus e do clone do OS Creator para provar). Passa de MAX_CARACTERES_DA_ROTA, corta."""
    texto = str(caminho or "")
    for corte in ("?", "#"):
        texto = texto.split(corte, 1)[0]
    return "/".join(_segmento(s) for s in texto.split("/"))[:MAX_CARACTERES_DA_ROTA]


def _automatico(rota: str, cabecalho, no_endereco) -> int:
    return int(str(cabecalho or "").strip() == "1" or rota in ROTAS_AUTOMATICAS or str(no_endereco or "").strip() == "1")


# ── o estado ─────────────────────────────────────────────────────────────────────────────────────────────────────────
class _Balde:
    """Uma hora × rota × automático: os pedidos, as pessoas (o conjunto de códigos só na memória, mais a quantidade que veio
    do arquivo de antes do reinício), as faixas de duração, os erros, os recusados pelo teto e os pedidos ao Fracttal."""
    __slots__ = ("pedidos", "base_pessoas", "pessoas", "histo", "erros", "ocupado", "fracttal")

    def __init__(self):
        self.pedidos = self.base_pessoas = self.erros = self.ocupado = self.fracttal = 0
        self.pessoas: set = set()
        self.histo: dict = {}

    def pessoas_qtd(self) -> int:
        """A soma dos dois lados do reinício, no máximo os pedidos (quem veio antes e depois conta duas vezes)."""
        return min(self.pedidos, self.base_pessoas + len(self.pessoas))


class _Hora:
    __slots__ = ("baldes", "rotas")

    def __init__(self):
        self.baldes: dict = {}                  # (rota, automatico) -> _Balde
        self.rotas: set = set()                 # as rotas da hora (o teto é sobre elas, não sobre o automático)


def _com_vaga(conhecidas, chave: str, maximo: int) -> str:
    """`chave` se já é conhecida ou ainda cabe; senão o balaio (OUTRAS). O balaio e o "sem setor" não gastam vaga."""
    if chave in conhecidas or chave in (OUTRAS, SEM_SETOR):
        return chave
    usadas = len(conhecidas) - sum(1 for k in (OUTRAS, SEM_SETOR) if k in conhecidas)
    return chave if usadas < maximo else OUTRAS


def _balde(hora_id: str, rota: str, automatico: int) -> _Balde:
    """O balde de agora (com a trava na mão): cria a hora, derruba a mais velha se passou do teto, e põe a rota que não
    coube no balaio."""
    hora = _horas.get(hora_id)
    if hora is None:
        hora = _horas[hora_id] = _Hora()
        while len(_horas) > MAX_HORAS:
            del _horas[min(_horas)]
    rota = _com_vaga(hora.rotas, rota, MAX_ROTAS)
    hora.rotas.add(rota)
    chave = (rota, automatico)
    balde = hora.baldes.get(chave)
    if balde is None:
        balde = hora.baldes[chave] = _Balde()
    return balde


def _faixa(ms: float) -> int:
    return min(MAX_FAIXA, int(math.log(max(1.0, ms)) / _LOG_BASE))


def _quantil(histo: dict, q: float) -> int | None:
    """O quantil `q` (posição pelo menor posto) das faixas, pelo centro da faixa em que cai; None sem nenhuma duração."""
    total = sum(histo.values())
    if total <= 0:
        return None
    alvo = max(1, math.ceil(round(q * total, 9)))
    soma = 0
    for faixa in sorted(histo):
        soma += histo[faixa]
        if soma >= alvo:
            return max(1, round(BASE ** (faixa + 0.5)))
    return None


def _folha_do_setor(dia: str, setor: str, rota: str) -> list:
    """[cliques, automáticos] do dia × setor × rota (com a trava na mão), com o teto de setores e de rotas."""
    setores = _setor.setdefault(dia, {})
    setor = _com_vaga(setores, setor, MAX_SETORES)
    rotas = setores.setdefault(setor, {})
    return rotas.setdefault(_com_vaga(rotas, rota, MAX_ROTAS), [0, 0])


def _podar_setor(hoje: str) -> None:
    """Tira os dias de 30 ou mais dias atrás (com a trava na mão): ficam `hoje` e os 29 anteriores."""
    corte = (datetime.strptime(hoje, "%Y%m%d") - timedelta(days=DIAS_SETOR)).strftime("%Y%m%d")
    for dia in [d for d in _setor if d <= corte]:
        del _setor[dia]


# ── o pedido ─────────────────────────────────────────────────────────────────────────────────────────────────────────
class _Pedido:
    """O pedido em curso: a rota, a marca de origem do Fracttal (sai no fim) e, se ele conta no uso das telas, o resto."""
    __slots__ = ("rota", "marca", "conta", "automatico", "pessoa", "inicio", "status")

    def __init__(self, rota: str):
        self.rota, self.marca, self.conta = rota, None, False
        self.automatico, self.pessoa, self.inicio, self.status = 0, None, 0.0, 0


def _pessoa() -> str | None:
    """O código (HMAC) do e-mail da sessão, ou None (a senha de administrador, por exemplo, não traz e-mail)."""
    usuario = session.get("usuario")
    email = str(usuario.get("email") or "").strip().lower() if isinstance(usuario, dict) else ""
    if not email:
        return None
    from ..cadastro.ligacao_campo import codigo_da_pessoa
    cfg = current_app.config
    return codigo_da_pessoa(str(cfg.get("NEXUS_PESSOA_HMAC") or cfg.get("SECRET_KEY") or ""), email)


def _setor_da_pessoa() -> str:
    """O setor da pessoa como o menu o acha (`setor_telas.acesso`: guardado no pedido, e o banco só lido de novo pela cópia
    de 1 min). Sem setor ou sem como saber, `SEM_SETOR`: o pedido nunca espera nem quebra por causa disto."""
    try:
        setor = setor_telas.acesso().get("setor")
        nome = str(setor.get("nome") or "").strip() if isinstance(setor, dict) else ""
        return nome[:60] or SEM_SETOR
    except Exception:                                   # noqa: BLE001
        return SEM_SETOR


def _antes() -> None:
    """O 1º `before_request` do app (antes do portão, para ver também o que ele recusa). Marca a origem do Fracttal com a rota
    normalizada em TODO pedido do Flask e, no do OS Creator, começa a medida. Nunca levanta."""
    try:
        rota = normalizar_rota(request.path)
        p = _Pedido(rota)
        request.environ[_ENV] = p                       # antes da marca: o `_depois` sempre acha o que tem de soltar
        marca = fracttal_conta.origem(rota)
        marca.__enter__()
        p.marca = marca
        if teto_os.do_os_creator(request.environ, current_app.extensions.get(teto_os.SEGREDO)) and session.get("logado"):
            p.automatico = _automatico(rota, request.headers.get(CABECALHO_AUTO), request.args.get(PARAMETRO_AUTO))
            p.pessoa = _pessoa()
            p.inicio = _cronometro()
            p.conta = True                              # por último: só conta quando tudo acima ficou pronto
    except Exception:                                   # noqa: BLE001 - a medição não derruba o pedido de ninguém
        log.debug("uso do OS Creator: não consegui começar a medida", exc_info=True)


def _resposta(resposta):
    """O último `after_request` a rodar (o 1º da lista): o código da resposta que de fato sai."""
    p = request.environ.get(_ENV)
    if p is not None:
        with contextlib.suppress(Exception):
            p.status = int(resposta.status_code)
    return resposta


def _depois(exc=None) -> None:
    """O `teardown_request`: fecha a conta do pedido que conta e solta a marca do Fracttal, mesmo que ele tenha quebrado."""
    p = request.environ.pop(_ENV, None)
    if p is None:
        return
    try:
        if p.conta:
            _contar(p, p.status or (500 if exc is not None else 0), fracttal_conta.pedidos_desta_thread())
    except Exception:                                   # noqa: BLE001
        log.debug("uso do OS Creator: não consegui fechar a medida", exc_info=True)
    finally:
        if p.marca is not None:
            try:
                p.marca.__exit__(None, None, None)      # volta a marca de antes; sem isto a thread levaria a rota ao próximo
            except Exception:                           # noqa: BLE001
                log.debug("uso do OS Creator: não consegui soltar a marca do Fracttal", exc_info=True)


def _contar(p: _Pedido, status: int, fracttal: int) -> None:
    ms = (_cronometro() - p.inicio) * 1000.0
    setor = _setor_da_pessoa() if p.pessoa else SEM_SETOR    # fora da trava: pode ir à cópia do setor
    faixa = _faixa(ms)
    with _trava:
        # A hora do FIM do pedido, lida AQUI DENTRO e não antes (como o `fracttal_conta._registrar`): lida antes, o `drenar`
        # podia passar entre o relógio e a trava (achar o setor demora), e o pedido recriaria a hora que o laço já tirou, com
        # 1 pedido; o próximo `drenar` devolveria a mesma chave com o número errado, e a gravação por chave trocaria a linha certa.
        hora_id = fracttal_conta.hora_id_de(_agora())
        b = _balde(hora_id, p.rota, p.automatico)
        b.pedidos += 1
        if p.pessoa:
            b.pessoas.add(p.pessoa)
        b.histo[faixa] = b.histo.get(faixa, 0) + 1
        if status >= 500:
            b.erros += 1
        b.fracttal += fracttal
        dia = hora_id[:8]
        if dia not in _setor:
            _setor[dia] = {}
            _podar_setor(dia)
        _folha_do_setor(dia, setor, p.rota)[1 if p.automatico else 0] += 1


def recusado(environ) -> None:
    """O teto recusou o pedido com 503, antes do Flask (`teto_os.Teto.ao_recusar`): conta como pedido e como `ocupado`, sem
    pessoa, sem duração e fora do corte por setor (não tem sessão)."""
    try:
        rota = normalizar_rota(environ.get("PATH_INFO", ""))
        no_endereco = next((v for k, v in parse_qsl(environ.get("QUERY_STRING", "") or "") if k == PARAMETRO_AUTO), None)
        automatico = _automatico(rota, environ.get(_AMBIENTE_AUTO), no_endereco)
        with _trava:
            hora_id = fracttal_conta.hora_id_de(_agora())   # dentro da trava, pelo mesmo motivo do `_contar`
            b = _balde(hora_id, rota, automatico)
            b.pedidos += 1
            b.ocupado += 1
    except Exception:                                   # noqa: BLE001
        log.debug("uso do OS Creator: não consegui contar o pedido recusado", exc_info=True)


# ── o que saiu ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _linhas_da_hora(hora_id: str, hora: _Hora) -> list:
    return [{"hora_id": hora_id, "rota": rota, "automatico": automatico, "pedidos_qtd": b.pedidos,
             "pessoas_qtd": b.pessoas_qtd(), "duracao_p50_ms": _quantil(b.histo, 0.5),
             "duracao_p95_ms": _quantil(b.histo, 0.95), "erros_qtd": b.erros, "ocupado_qtd": b.ocupado,
             "fracttal_qtd": b.fracttal}
            for (rota, automatico), b in sorted(hora.baldes.items(), key=lambda kv: kv[0])]


def _corte_do_setor() -> dict:
    return {dia: {setor: {rota: {"cliques": v[0], "automaticos": v[1]} for rota, v in sorted(rotas.items())}
                  for setor, rotas in sorted(setores.items())}
            for dia, setores in sorted(_setor.items())}


def instantaneo() -> dict:
    """`{"linhas": [...], "setor": {...}}` sem tirar nada (o Raio-X). As linhas são as de todas as horas guardadas, da mais
    antiga à mais nova (a aberta inclusive), como as do `drenar`. O corte por setor é `{dia: {setor: {rota: {"cliques",
    "automaticos"}}}}`, o mesmo que o arquivo guarda."""
    with _trava:
        return {"linhas": [lin for h in sorted(_horas) for lin in _linhas_da_hora(h, _horas[h])],
                "setor": _corte_do_setor()}


def drenar(ate_hora_id: str) -> list:
    """Devolve e tira as linhas das horas FECHADAS: as anteriores a `ate_hora_id`, que é a hora aberta (a de agora,
    `fracttal_conta.hora_id_de()`) e fica onde está (EXCLUSIVO, como o `fracttal_conta.drenar`). Cada linha: `hora_id`, `rota`,
    `automatico` (1 ou 0), `pedidos_qtd`, `pessoas_qtd`, `duracao_p50_ms` e `duracao_p95_ms` (None sem pedido atendido),
    `erros_qtd`, `ocupado_qtd` e `fracttal_qtd`. Depois de gravar, quem drena chama `salvar()` (o arquivo parcial de antes
    ainda tem a hora, e um reinício a traria de volta)."""
    limite = str(ate_hora_id)
    with _trava:
        fechadas = [(h, _horas.pop(h)) for h in sorted(h for h in _horas if h < limite)]
    return [lin for h, hora in fechadas for lin in _linhas_da_hora(h, hora)]


def limpar() -> None:
    """Esquece tudo (os testes; nada no servidor chama)."""
    with _trava:
        _horas.clear()
        _setor.clear()
        _estado.clear()
        _estado.update(gravar=False, pasta=None, config=None, gravou_em=0.0)
    with _trava_pendentes:
        for lista in _pendentes.values():
            lista.clear()


# ── o que sai dos contadores: para o disco de hora em hora, para o banco uma vez por dia ──────────────────────────────
def pendentes() -> dict:
    """O que já saiu dos contadores e ainda não está no banco: `{"uso", "fracttal", "horas"}`, só contagens."""
    with _trava_pendentes:
        horas = {lin["hora_id"] for lista in _pendentes.values() for lin in lista}
        return {"uso": len(_pendentes["uso"]), "fracttal": len(_pendentes["fracttal"]), "horas": len(horas)}


def linhas_pendentes() -> dict:
    """Cópia das linhas que já saíram dos contadores e esperam as 04:45: `{"uso": [...], "fracttal": [...]}` (a do Fracttal
    ainda com a linha de total `*`, que o `fato_uso_os.separar_total` leva para a aba dela). É o que o disco guarda: o
    Raio-X as soma ao que o banco tem."""
    with _trava_pendentes:
        return {nome: [dict(lin) for lin in lista] for nome, lista in _pendentes.items()}


def gravou_em() -> float:
    """Quando (relógio de parede) a última gravação no banco deu certo, ou 0 se nenhuma desde que o processo subiu. O Raio-X
    guarda o banco por 10 min: a leitura que começou antes desta hora não tem o que saiu do pendente, e é lida de novo."""
    return float(_estado.get("gravou_em") or 0.0)


def _juntar_pendentes(novas_uso: list, novas_fracttal: list) -> None:
    """Com a trava na mão: soma as linhas ao pendente, em ordem. A mesma chave fica uma só, a mais nova (a hora que o
    parcial velho traz de volta depois de um reinício, e que o pendente já tinha, não vai duas vezes ao banco: o grão
    quebraria e ninguém mais gravaria)."""
    for nome, novas in (("uso", novas_uso), ("fracttal", novas_fracttal)):
        chave = _CHAVE_DA_LINHA[nome]
        por_chave = {chave(lin): lin for lin in _pendentes[nome]}
        por_chave.update({chave(lin): lin for lin in novas})
        _pendentes[nome] = [por_chave[k] for k in sorted(por_chave)]


def _cortar_pendentes() -> None:
    """Com a trava na mão: fica no máximo MAX_HORAS_PENDENTES horas (3 dias), as mais novas. O banco fora por dias não pode
    encher o disco nem a memória do servidor."""
    horas = sorted({lin["hora_id"] for lista in _pendentes.values() for lin in lista})
    if len(horas) <= MAX_HORAS_PENDENTES:
        return
    corte = horas[-MAX_HORAS_PENDENTES]
    for nome in _pendentes:
        _pendentes[nome] = [lin for lin in _pendentes[nome] if lin["hora_id"] >= corte]
    log.warning("Uso do OS Creator: o banco segue sem receber e descartei %d hora(s) pendente(s), as mais velhas; "
                "ficam as %d mais novas (3 dias)", len(horas) - MAX_HORAS_PENDENTES, MAX_HORAS_PENDENTES)


def _salvar_pendente() -> None:
    """O pendente no disco (`casca/uso_os_pendente.json`, atômico: rascunho + `os.replace`). A memória é a cópia de trabalho
    e o arquivo, a durável: falha de disco vai ao log e a memória segue com as linhas (a próxima vez grava de novo). Sem
    pasta de dados (o teste sem `NEXUS_DADOS`) não faz nada. Quem tira a cópia da memória a tira com a trava do disco na mão,
    senão duas gravações podiam trocar de ordem e deixar no arquivo a mais velha."""
    pasta = _estado.get("pasta")
    if pasta is None:
        return
    with _trava_disco:
        with _trava_pendentes:
            dados = {"versao": 1, "gravado_em": _agora(),
                     **{nome: [dict(lin) for lin in lista] for nome, lista in _pendentes.items()}}
        _gravar(pasta / ARQUIVO_PENDENTE, dados)


def _carregar_pendente(arquivo: Path) -> None:
    """O pendente que ficou no disco antes do reinício volta à memória (o que já saiu dos contadores não se perde). Arquivo
    quebrado ou fora da forma é ignorado, com aviso no log; a linha ruim é ignorada e as boas ficam, porque uma ruim deixada
    no meio faria a gravação subir para sempre."""
    dados = _ler_json(arquivo)
    if dados is None:
        return
    from ..dados import fato_uso_os                     # aqui dentro: a casca não puxa a camada de dados no import
    boas, ruins = {"uso": [], "fracttal": []}, 0
    for nome, aba in (("uso", fato_uso_os.ABA_USO), ("fracttal", fato_uso_os.ABA_FRACTTAL)):
        lista = dados.get(nome)
        if not isinstance(lista, list):
            log.warning("Uso do OS Creator: %s não tem a lista \"%s\"; ignoro essa parte", arquivo, nome)
            continue
        for d in lista:
            if fato_uso_os.valida(d, aba):
                boas[nome].append(d)
            else:
                ruins += 1
    if ruins:
        log.warning("Uso do OS Creator: %d linha(s) ruim(ns) de %s ignorada(s)", ruins, arquivo)
    with _trava_pendentes:
        _juntar_pendentes(boas["uso"], boas["fracttal"])
        _cortar_pendentes()


def proximo_passo(agora: float) -> tuple:
    """`(segundos, passo)` do próximo compromisso do laço: tirar as horas fechadas dos contadores (`PASSO_DRENAR`, no :05 de
    toda hora; o fuso do Brasil é de horas inteiras, então o minuto é o mesmo em qualquer um) ou levar o pendente ao banco
    (`PASSO_GRAVAR`, às 04:45 de Brasília). Estando no instante de um deles, o próximo é o da vez seguinte."""
    drenar_em = (agora // 3600) * 3600 + DRENAR_NO_MINUTO * 60
    if drenar_em <= agora:
        drenar_em += 3600
    local = agora + _BRT_S                              # o relógio de Brasília, contado como se fosse UTC
    gravar_em = (local // 86400) * 86400 + GRAVAR_NA_HORA * 3600 + GRAVAR_NO_MINUTO * 60 - _BRT_S
    if gravar_em <= agora:
        gravar_em += 86400
    if gravar_em < drenar_em:
        return gravar_em - agora, PASSO_GRAVAR
    return drenar_em - agora, PASSO_DRENAR


def drenar_para_o_disco() -> dict:
    """O passo de TODA hora: tira as horas FECHADAS dos dois contadores e as guarda no pendente em disco (`_salvar_pendente`),
    de onde o Raio-X as lê e a gravação das 04:45 as leva ao banco. A memória dos contadores fica limitada, e um reinício não
    perde o que já saiu deles. Depois, `salvar()`: o parcial sem as horas que acabaram de sair (senão o reinício as traria
    de volta). Nunca vai ao banco.

    A hora aberta (a de agora) é lida UMA vez, antes dos dois `drenar`: o relógio que anda entre os dois não faz o segundo
    tirar uma hora que ainda não fechou. Devolve só contagens: `{"drenou": {"uso", "fracttal"}, "pendentes": {...}}`."""
    ate = fracttal_conta.hora_id_de()                   # a hora aberta, lida ANTES dos dois drenar
    novas_uso, novas_fracttal = drenar(ate), fracttal_conta.drenar(ate)
    if novas_uso or novas_fracttal:
        with _trava_pendentes:
            _juntar_pendentes(novas_uso, novas_fracttal)
            _cortar_pendentes()
        _salvar_pendente()
        try:
            salvar()
        except Exception:                               # noqa: BLE001
            log.warning("Uso do OS Creator: guardei o pendente e não consegui guardar o parcial", exc_info=True)
    return {"drenou": {"uso": len(novas_uso), "fracttal": len(novas_fracttal)}, "pendentes": pendentes()}


def gravar_no_banco(config=None, *, sessao=None) -> dict:
    """O passo das 04:45: leva ao banco TUDO o que está pendente (o que o :05 guardou desde a última gravação, mais o que
    fechou depois dele), agrupado pelo livro do mês de cada hora (`dados/fato_uso_os.gravar`). Devolve só contagens: o que
    `gravar` devolve; `{"pulou": ...}` sem nada a gravar; ou `{"erro": ..., "pendentes": ...}`, e então o pendente fica no
    disco e a gravação do dia seguinte leva tudo (até o teto de 3 dias).

    Deu certo: anota a hora (`gravou_em`), as linhas gravadas saem do pendente (memória e disco) e `salvar()` roda. `sessao` e
    `config` são para os testes; no servidor vêm do app e do `requests`. Teste sem sessão não tira nada dos contadores e
    nunca vai à rede."""
    config = config if config is not None else (_estado.get("config") or {})
    if sessao is None and config.get("TESTING"):
        return {"pulou": "teste sem banco: nada foi tirado dos contadores"}
    if not _trava_gravacao.acquire(blocking=False):
        return {"pulou": "outra volta da gravação está em curso"}
    try:
        return _gravar_pendente(config, sessao)
    finally:
        _trava_gravacao.release()


def _gravar_pendente(config, sessao) -> dict:
    drenar_para_o_disco()                               # o que fechou desde o último :05 (nada, no horário normal)
    with _trava_pendentes:
        uso, fracttal = list(_pendentes["uso"]), list(_pendentes["fracttal"])
    if not uso and not fracttal:
        return {"pulou": "nada pendente para gravar"}
    token = str(config.get("GRIDCO_SQL_TOKEN") or "").strip()
    if not token:
        return {"erro": "sem GRIDCO_SQL_TOKEN: o pendente fica no disco do servidor", "pendentes": pendentes()}
    from ..cadastro.ligacoes import BASE_API
    from ..dados import fato_uso_os                     # aqui dentro: a casca não puxa a camada de dados no import
    try:
        if sessao is None:
            import requests
            sessao = requests.Session()
        rel = fato_uso_os.gravar(uso, fracttal, base=(config.get("GRIDCO_DB_API") or BASE_API).rstrip("/"), token=token,
                                 sessao=sessao)
    except Exception as ex:                             # noqa: BLE001 - banco fora, leitura curta, conferência: tenta amanhã
        log.warning("Uso do OS Creator: não gravei no banco (%s); %d linha(s) ficam no disco para a gravação do dia "
                    "seguinte", type(ex).__name__, len(uso) + len(fracttal), exc_info=True)
        return {"erro": type(ex).__name__, "pendentes": pendentes()}
    # a hora da gravação ANTES de limpar o pendente: o Raio-X que olhar no meio vê o banco como velho, lê de novo e acha as
    # linhas nos dois lados (a chave repetida vale a do pendente), nunca num buraco
    _estado["gravou_em"] = _agora()
    gravadas = {id(lin) for lin in uso} | {id(lin) for lin in fracttal}
    with _trava_pendentes:                              # só sai o que foi gravado: o que chegou durante a gravação fica
        for nome in _pendentes:
            _pendentes[nome] = [lin for lin in _pendentes[nome] if id(lin) not in gravadas]
    _salvar_pendente()
    try:
        salvar()
    except Exception:                                   # noqa: BLE001
        log.warning("Uso do OS Creator: gravei no banco e não consegui guardar o parcial", exc_info=True)
    return rel


def _laco_gravacao() -> None:
    while True:
        espera, passo = proximo_passo(_agora())
        time.sleep(espera)
        try:
            rel = gravar_no_banco() if passo == PASSO_GRAVAR else drenar_para_o_disco()
            log.info("Uso do OS Creator (%s): %s", passo, rel)
        except Exception:                               # noqa: BLE001 - a medição nunca derruba o Nexus
            log.exception("Uso do OS Creator: o passo %s do laço quebrou", passo)


# ── o disco: o parcial e o corte por setor ───────────────────────────────────────────────────────────────────────────
def _gravar(caminho: Path, dados: dict) -> None:
    """Grava inteiro ou nada (rascunho + `os.replace`): o arquivo de antes só sai quando o novo está completo."""
    tmp = caminho.with_name(caminho.name + ".tmp")
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, caminho)
    except OSError as ex:
        log.warning("Uso do OS Creator: não gravei %s (%s)", caminho, ex)
        with contextlib.suppress(OSError):
            tmp.unlink()


def salvar() -> None:
    """Grava o parcial (os baldes, só contagens) e o corte por setor na pasta de dados. O laço de 5 em 5 minutos chama;
    sem pasta de dados (o teste sem `NEXUS_DADOS`) não faz nada. Falha de disco vai ao log e o laço segue."""
    pasta = _estado.get("pasta")
    if pasta is None:
        return
    agora = _agora()
    with _trava:
        _podar_setor(fracttal_conta.hora_id_de(agora)[:8])
        parcial = {"versao": 1, "gravado_em": agora, "horas": {
            h: [{"rota": rota, "automatico": automatico, "pedidos": b.pedidos, "pessoas": b.pessoas_qtd(),
                 "histo": {str(f): n for f, n in sorted(b.histo.items())}, "erros": b.erros, "ocupado": b.ocupado,
                 "fracttal": b.fracttal} for (rota, automatico), b in sorted(hora.baldes.items(), key=lambda kv: kv[0])]
            for h, hora in sorted(_horas.items())}}
        corte = {"versao": 1, "gravado_em": agora, "dias": _corte_do_setor()}
    with _trava_disco:
        _gravar(pasta / ARQUIVO_PARCIAL, parcial)
        _gravar(pasta / ARQUIVO_SETOR, corte)


def _ler_json(arquivo: Path) -> dict | None:
    """O JSON do arquivo se ele existe e é um objeto; senão None (arquivo ausente, quebrado ou de outra forma: ignora)."""
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None                                     # o 1º boot: nada guardado ainda
    except (OSError, ValueError, RecursionError) as ex:     # inclusive o que nem decodifica ou aninha demais
        log.warning("Uso do OS Creator: não li %s (%s); começo do zero", arquivo, ex)
        return None
    if not isinstance(dados, dict):
        log.warning("Uso do OS Creator: %s não tem a forma esperada; começo do zero", arquivo)
        return None
    return dados


def _inteiro(v, maximo: int = 2 ** 53) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= maximo


def _balde_do_arquivo(d) -> tuple | None:
    """(rota, automatico, pedidos, pessoas, histo, erros, ocupado, fracttal) de um balde do parcial, ou None se ele não faz
    sentido (um balde ruim não leva os bons junto)."""
    if not isinstance(d, dict) or not isinstance(d.get("rota"), str) or not d["rota"]:
        return None
    if len(d["rota"]) > MAX_CARACTERES_DA_ROTA or d.get("automatico") not in (0, 1):
        return None
    campos = [d.get(k) for k in ("pedidos", "pessoas", "erros", "ocupado", "fracttal")]
    if not all(_inteiro(v) for v in campos):
        return None
    pedidos, pessoas, erros, ocupado, fracttal = campos
    if pessoas > pedidos or erros > pedidos or ocupado > pedidos:
        return None
    bruto = d.get("histo")
    if not isinstance(bruto, dict):
        return None
    histo = {}
    for faixa, n in bruto.items():
        try:
            f = int(faixa)
        except (TypeError, ValueError):
            return None
        if not (0 <= f <= MAX_FAIXA and _inteiro(n)):
            return None
        histo[f] = n
    if sum(histo.values()) > pedidos:
        return None
    return d["rota"], int(d["automatico"]), pedidos, pessoas, histo, erros, ocupado, fracttal


def _carregar_parcial(arquivo: Path) -> None:
    dados = _ler_json(arquivo)
    horas = dados.get("horas") if dados else None
    if not isinstance(horas, dict):
        if dados is not None:
            log.warning("Uso do OS Creator: %s não tem as horas; começo do zero", arquivo)
        return
    validas = sorted((h, b) for h, b in horas.items() if isinstance(h, str) and _HORA_ID.fullmatch(h)
                     and isinstance(b, list))
    with _trava:
        for hora_id, baldes in validas[-MAX_HORAS:]:
            for d in baldes:
                lido = _balde_do_arquivo(d)
                if lido is None:
                    continue
                rota, automatico, pedidos, pessoas, histo, erros, ocupado, fracttal = lido
                b = _balde(hora_id, rota, automatico)
                b.pedidos += pedidos
                b.base_pessoas += pessoas
                b.erros += erros
                b.ocupado += ocupado
                b.fracttal += fracttal
                for faixa, n in histo.items():
                    b.histo[faixa] = b.histo.get(faixa, 0) + n


def _carregar_setor(arquivo: Path) -> None:
    dados = _ler_json(arquivo)
    dias = dados.get("dias") if dados else None
    if not isinstance(dias, dict):
        return
    with _trava:
        for dia, setores in dias.items():
            if not (isinstance(dia, str) and _DIA_ID.fullmatch(dia) and isinstance(setores, dict)):
                continue
            for setor, rotas in setores.items():
                if not (isinstance(setor, str) and setor and isinstance(rotas, dict)):
                    continue
                for rota, v in rotas.items():
                    if not (isinstance(rota, str) and rota and isinstance(v, dict)
                            and _inteiro(v.get("cliques")) and _inteiro(v.get("automaticos"))):
                        continue
                    folha = _folha_do_setor(dia, setor[:60], rota[:MAX_CARACTERES_DA_ROTA])
                    folha[0] += v["cliques"]
                    folha[1] += v["automaticos"]
        _podar_setor(fracttal_conta.hora_id_de(_agora())[:8])


def _pasta(config) -> Path | None:
    from ..cadastro.ligacoes import pasta_dados
    try:
        return pasta_dados(config) / "casca"
    except RuntimeError:                                # teste sem NEXUS_DADOS: a pasta de dados real não se toca
        return None


def _laco() -> None:
    while True:
        time.sleep(PASSO_S)
        try:
            salvar()
        except Exception:                               # noqa: BLE001 - a medição nunca derruba o Nexus
            log.exception("Uso do OS Creator: não consegui guardar o instantâneo")


def ligar(app, *, gravar: bool) -> None:
    """Liga a medição neste app: os ganchos do pedido, o aviso do teto, o parcial e o corte por setor de antes do reinício e
    (fora dos testes) o laço de 5 em 5 minutos. `gravar` diz se este processo leva as horas ao banco (o servidor sim, o PC
    não): só com ele abre o laço (`drenar_para_o_disco` no :05 de toda hora, `gravar_no_banco` às 04:45). O pendente que ficou
    no disco volta no boot. Chame DEPOIS do `teto_os.ligar` (é ele que avisa o 503). Ligar de novo no mesmo app não faz nada."""
    if CHAVE in app.extensions:
        return
    _estado["gravar"] = bool(gravar)
    _estado["config"] = app.config
    _estado["pasta"] = _pasta(app.config)
    app.extensions[CHAVE] = _estado
    # na frente do portão (vê o que ele recusa e mede o tempo dele) e atrás de tudo no depois (vê a resposta que sai)
    app.before_request_funcs.setdefault(None, []).insert(0, _antes)
    app.after_request_funcs.setdefault(None, []).insert(0, _resposta)
    app.teardown_request_funcs.setdefault(None, []).append(_depois)
    teto = app.extensions.get(teto_os.CHAVE)
    if teto is not None:
        teto.ao_recusar = recusado
    if _estado["pasta"] is not None:
        for carregar, nome in ((_carregar_parcial, ARQUIVO_PARCIAL), (_carregar_setor, ARQUIVO_SETOR),
                               (_carregar_pendente, ARQUIVO_PENDENTE)):
            try:
                carregar(_estado["pasta"] / nome)
            except Exception:                           # noqa: BLE001 - arquivo ruim não impede o Nexus de subir
                log.exception("Uso do OS Creator: não consegui ler %s; começo do zero", nome)
    if not app.config.get("TESTING"):
        threading.Thread(target=_laco, name="nexus-uso-os", daemon=True).start()
        if gravar:                                      # o laço do disco e do banco é só do servidor
            threading.Thread(target=_laco_gravacao, name="nexus-uso-os-banco", daemon=True).start()
