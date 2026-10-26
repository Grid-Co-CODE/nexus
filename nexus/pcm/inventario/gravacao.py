"""A gravação do inventário no Fracttal, em segundo plano (Levi, 26/10/2026; Task 7 do plano
`docs/superpowers/plans/2026-10-26-inventario-almoxarifado.md`, com as decisões do passo 0, `...-passo0.md`).

O PCM aprova o lote (as peças `not tirada and situacao in contas.MEXEM`) e o Nexus grava o saldo CONTADO no Fracttal, no
login de quem aprovou. O Fracttal não tem um ajuste por peça: grava-se numa SESSÃO do almoxarifado (modo 2, "Ajuste de
inventário"): abre, grava o saldo absoluto de cada peça, fecha com a referência (o fechamento são dois pedidos: o finalizar,
que gera os movimentos, e a volta ao modo 0). **Enquanto a sessão está aberta, o almoxarifado fica travado no Fracttal**:
nem entrada, nem saída, nem pedido de compra; o técnico em campo não consegue lançar peça. Caso real de 26/10: o
ATHN-MTS200 estava parado em "Inventário físico" (modo 3) com tudo travado. Por isso:

- **Uma sessão por lote de 50** (o ritmo é 1 pedido/s: ~1 minuto travado por lote; entre um lote e outro o almoxarifado
  volta ao normal). A referência é `INVENTARIO-<contagem>-L<n>`; a 2ª sessão do mesmo lote (a que grava o resto depois de
  uma parada) leva `-S<k>`, para o "achar o fechamento pela referência" nunca confundir as duas.
- **O modo manda.** 3 (inventário físico): para sem mexer. 2 que o controle não diz que é nosso (outra pessoa ou outra
  tela): para sem mexer (voltá-lo ao normal deixaria os saldos dela sem o par de movimentos). O modo se confere no começo do
  lote e de novo logo antes de abrir: entre uma conferência e a outra passam segundos (ligar as peças, ler). O 2 que o
  controle diz ser nosso, numa retomada, é conferido pelo histórico desde que a sessão abriu: movimento sem a nossa
  referência é a sessão que saiu das nossas mãos (alguém a finalizou e abriu outra), e a gravação para. QUASE nunca, e não
  nunca: quem solta o modo no Fracttal sem finalizar não deixa rastro, e uma sessão aberta por outra pessoa logo depois
  pareceria a nossa.
- **Conflito, nunca gravar por cima:** com a sessão aberta nada se move, e a leitura feita ali é a que vale; a peça cujo
  saldo não é o da aprovação, ou que se moveu no histórico depois do "Contada em", vira o evento `conflito` e não é gravada.
  O específico cujo genérico ainda tem unidades por identificar na curadoria também (as unidades pendentes talvez sejam
  dele), já na aprovação.
- **Retomar sem duplicar:** gravar o saldo é absoluto (regravar o mesmo número não muda nada); o finalizar NUNCA se repete
  sem procurar antes o fechamento pela referência, em toda retomada com o modo 2 e depois da resposta perdida (esta, depois
  de esperar: o histórico pode ainda não mostrar o finalize). A sessão em que nada se gravou não tem movimento para achar:
  aí só volta ao modo 0 (um 2º finalizar seria erro no Fracttal). O `movimento_fracttal` do evento é o folio do movimento
  achado pela referência depois de fechar, nos dois caminhos (o fechamento normal e a retomada).
- **Parar com a sessão aberta é o pior caso.** Antes de parar (429 de novo, erro inesperado) tenta fechar com o que já
  gravou. Sem login não há como fechar: para com o aviso forte ("ficou travado em ajuste no Fracttal; quem aprovou precisa
  continuar para destravar").

| Como para | O almoxarifado fica |
|---|---|
| modo 3 (inventário físico) | como estava (de outra pessoa) |
| modo 2 de outra pessoa ou tela | como estava (de outra pessoa) |
| na retomada, o modo 2 com movimento de outra referência desde que a nossa sessão abriu | como estava (saiu das nossas mãos) |
| 429, de novo depois de 62 s | fechado com o que gravou; travado (aviso forte) só se nem o fechamento passou |
| login do Fracttal expirou | travado se a sessão estava aberta (aviso forte); quem aprovou entra de novo e continua |
| erro inesperado (o Fracttal recusou, a rede caiu) | fechado com o que gravou (evento `erro` com o tipo); travado só se não fechou |
| o livro do inventário não aceitou o registro | normal (o registro é sempre depois de fechar) |
| a releitura não bateu | normal; o "Continuar" relê sem gravar (bate: gravada; não bate: conflito) |
| o Nexus reiniciou no meio | como o controle diz: a tela mostra "parada", e o aviso forte se a sessão ficou aberta |
| encerrada (quem aprovou, ou o administrador depois de 24 h parada) | normal: só se encerra com o almoxarifado fora do modo 2 |

**Encerrar** (`encerrar`, Levi, 26/10/2026): a gravação parada que ninguém vai continuar. Quem aprovou encerra a qualquer
hora; o administrador do Nexus, depois de 24 h parada (quem aprovou pode ter saído de férias). Só com o almoxarifado FORA
do modo 2, conferido na hora no Fracttal: encerrar com a sessão aberta largaria o almoxarifado travado sem dono. Pede o
motivo (cifrado). As peças já conferidas ficam `peca_gravada`; cada uma das outras vira `conflito` com o motivo (a contagem
sai de "gravando" e fica "gravada com conflitos"), e a vez do almoxarifado é solta.

O controle (`<NEXUS_DADOS>/almox_inventario/<contagem_id>.json`) guarda o ponto de retomada: o estado de cada lote
(`pendente`, `abrindo`, `aberto`, `fechando`, `feito`), a hora em que a sessão abriu, as peças que se moveram, e o de cada
peça (`pendente`, `enviando` = a peça sem resposta, `escrita`, `fechada`, `duvida` = a sem resposta numa sessão já fechada,
`gravada`, `conflito`, `erro`). NUNCA o login: o JWT e o e-mail vivem só na instância do `Estoque` (a do pedido de quem
aprovou); quem aprovou é o `pessoa_hmac`. O arquivo `trava-<almoxarifado>.json` é a vez do almoxarifado: o servidor é um
processo só (a trava da memória basta), mas o arquivo segura a reinicialização no meio.

Os eventos vão ao livro do inventário (`fato_inventario.acrescentar`) SEMPRE com o almoxarifado fora da sessão: o livro é o
banco, e gravar nele com o almoxarifado travado o deixaria travado mais tempo. Cada evento tem um `evento_id` que sai da
contagem, do tipo e da peça: registrar de novo (a retomada depois de uma falha do banco) não duplica a auditoria.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ...campo.ligacao_cadastro import codigo_da_pessoa
from ...dados import almoxarifado as A
from ...dados import fato_inventario as F
from . import contas
from .estoque import ErroFracttal, Limite, SemLogin, instante, validar_quantidade

TAMANHO_LOTE = 50
ESPERA_LIMITE_S = 62            # a cota do Fracttal é por minuto: 62 s e ela já virou
# O relógio do servidor e o do Fracttal (o `date_create`) não são o mesmo: procurar o fechamento só a partir da hora exata
# em que a sessão abriu perderia o que o Fracttal datou alguns segundos antes, e o "não achei" mandaria um 2º finalizar
MARGEM_RELOGIO = timedelta(minutes=10)
PASTA = "almox_inventario"
SESSAO = ("abrindo", "aberto", "fechando")      # o lote com a sessão (talvez) aberta no Fracttal
FINAIS = ("gravada", "conflito")                 # o estado de peça que encerra a peça no livro
REGISTRAVEIS = ("gravada", "conflito", "erro")
TIPO_DO_EVENTO = {"gravada": "peca_gravada", "conflito": "conflito", "erro": "erro"}

MODO_3 = "o almoxarifado está em Inventário físico no Fracttal"
OUTRO = "o almoxarifado já está em ajuste no Fracttal (outra pessoa ou outra tela)"
OUTRO_DEPOIS = "o almoxarifado está em ajuste por outra pessoa ou outra tela"
MODO_DESCONHECIDO = "o almoxarifado está num modo que o Nexus não conhece ({modo})"
LIMITE = "limite do Fracttal"
LOGIN = "o login do Fracttal expirou"
SEM_HISTORICO = "o Fracttal não disse o que se moveu depois da contagem"
SEM_LIVRO = "não consegui registrar no livro do inventário; o almoxarifado ficou normal"
RELEITURA = "{n} {pecas} não {conferiram} na releitura do Fracttal: confira e continue"
INTERROMPIDA = "a gravação parou no meio (o Nexus reiniciou)"
EM_ANDAMENTO = "já tem uma gravação em andamento neste almoxarifado"
SO_QUEM_APROVOU = "só quem aprovou continua"
AVISO_TRAVADO = "{almox} ficou travado em ajuste no Fracttal; quem aprovou precisa continuar para destravar."
SEM_PESSOA = ("Não sei quem está aprovando: entre com o seu login do Fracttal (a gravação fica no nome de quem aprova, e a "
              "senha de administrador não é uma pessoa).")
MUDOU = "A contagem mudou desde que você abriu a tela; recarregue. Nada foi gravado."
ADMIN_ENCERRA_H = 24            # o administrador encerra a gravação parada há mais que isto (quem aprovou, a qualquer hora)
MOTIVO_MAX = 1000
ENCERRADA = "a gravação foi encerrada: {motivo}"
# a gravação viva salva o controle a cada pedido; a pausa mais longa entre dois salvamentos é a do 429 (62 s, o pedido de
# novo, mais 62 s antes de fechar). O controle "gravando" mais velho que isto é de uma gravação que o Nexus já não roda
VIVA_S = 300

# os motivos que vão cifrados no evento (`dados`), sempre texto do Nexus, nunca o do Fracttal (pode ter nome de gente)
MEXIDA = "a peça se moveu no Fracttal depois da contagem"
NAO_LIGADA = "a peça não aparece no almoxarifado do Fracttal"
SALDO_MUDOU = "o saldo do Fracttal mudou depois da aprovação (era {de}, está {agora})"
GENERICO = "o genérico desta peça ainda tem unidades por identificar na curadoria"
NAO_BATEU = "a releitura depois de gravar não bateu com o contado (está {agora})"
NAO_BATEU_DE_NOVO = "a releitura não bateu de novo: confira no Fracttal (está {agora})"
ENCERRADA_SEM_GRAVAR = ("a gravação foi encerrada antes desta peça (o saldo dela talvez já seja o contado no Fracttal: "
                        "confira): {motivo}")

_TOLERANCIA = 1e-6
_RE_SEGURO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
_RE_DIGITOS = re.compile(r"\d{1,20}")

_TRAVA = threading.Lock()                # a vez de cada almoxarifado (iniciar, continuar e o fim de cada gravação)
_TRAVA_ARQ = threading.Lock()            # o arquivo de controle: no Windows o `replace` falha com o arquivo aberto
_ATIVAS: dict[str, tuple[str, threading.Thread | None]] = {}     # almoxarifado -> (contagem, thread; None = começando)
_dormir = time.sleep                     # os testes trocam: a espera de 62 s nunca é de verdade num teste


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return instante(d).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Recusada(F.Recusada):
    """A gravação recusada antes de mexer em qualquer coisa (nada foi gravado). `status`: o HTTP que a rota devolve."""

    def __init__(self, mensagem: str, status: int = 409):
        super().__init__(mensagem)
        self.status = status


class SoQuemAprovou(Recusada):
    """O "Continuar" de quem não aprovou: o resto vai no nome de quem aprovou, e só ele tem o login certo para isso."""

    def __init__(self):
        super().__init__(SO_QUEM_APROVOU, 403)


class _Parar(Exception):
    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


class _LimiteDeNovo(Exception):
    """O 429 que voltou depois da espera de 62 s: hora de parar (fechando antes)."""


# ── números ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _num(v) -> float | None:
    n = A.numero(v)
    return n if n is not None and n == n and n not in (float("inf"), float("-inf")) else None


def _igual(a, b) -> bool:
    """O saldo do Fracttal contra o número do lote: None só com None (o saldo "não informado" da aprovação continua não
    informado; virar 0 seria chutar), número com folga de ponto flutuante."""
    a, b = _num(a), _num(b)
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= _TOLERANCIA


def _txt_num(v) -> str:
    n = _num(v)
    if n is None:
        return "não informado"
    return str(int(n)) if n.is_integer() else f"{n:.6f}".rstrip("0").rstrip(".").replace(".", ",")


def _saldo(lido: dict, id_item: str):
    linha = lido.get(id_item) if isinstance(lido, dict) else None
    return linha.get("saldo") if isinstance(linha, dict) else None


def _digitos(folio) -> str:
    """O folio do Fracttal como o livro o guarda (só dígitos): o `folio_return` do fechamento ("7") ou o do movimento achado
    pela referência ("MOV-6" → "6"). Sem número, vazio."""
    m = re.search(r"\d{1,20}", str(folio or ""))
    return m.group(0) if m else ""


def _id_evento(*partes) -> str:
    """O `evento_id` que sai do que o evento é (contagem, tipo, peça...): registrar de novo não duplica a auditoria."""
    return "inv-" + hashlib.sha1("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:20]


# ── os arquivos de controle ──────────────────────────────────────────────────────────────────────────────────────────────
def _pasta(cfg) -> Path | None:
    """`<NEXUS_DADOS>/almox_inventario`. Em teste sem `NEXUS_DADOS`, None: nada se lê nem se grava na pasta de verdade."""
    if cfg.get("TESTING") and not cfg.get("NEXUS_DADOS"):
        return None
    from ...cadastro.ligacoes import pasta_dados
    return pasta_dados(cfg) / PASTA


def _nome(contagem_id: str) -> str:
    """`<contagem_id>.json`; o ID que não serve de nome de arquivo (o App gera, e pode mandar o que quiser) vai limpo e com
    um pedaço do hash, para dois IDs diferentes nunca darem o mesmo arquivo."""
    if _RE_SEGURO.fullmatch(contagem_id) and ".." not in contagem_id:
        return f"{contagem_id}.json"
    limpo = re.sub(r"[^A-Za-z0-9_.-]", "_", contagem_id)[:60].strip(".") or "contagem"
    return f"{limpo}-{hashlib.sha1(contagem_id.encode('utf-8')).hexdigest()[:10]}.json"


def _caminho(cfg, contagem_id: str) -> Path:
    p = _pasta(cfg)
    if p is None:
        raise Recusada("Este Nexus está sem pasta de dados (NEXUS_DADOS): nada foi gravado.", 503)
    return p / _nome(contagem_id)


def _caminho_trava(cfg, id_almox: str) -> Path:
    p = _pasta(cfg)
    if p is None:
        raise Recusada("Este Nexus está sem pasta de dados (NEXUS_DADOS): nada foi gravado.", 503)
    return p / f"trava-{id_almox}.json"


def _ler_json(p: Path) -> dict | None:
    with _TRAVA_ARQ:
        try:
            texto = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
    try:
        d = json.loads(texto)
    except ValueError:
        raise Recusada(f"O controle da gravação ({p.name}) está ilegível: chame quem cuida do Nexus antes de mexer no "
                       "almoxarifado.") from None
    return d if isinstance(d, dict) else None


def _gravar_json(p: Path, d: dict) -> None:
    with _TRAVA_ARQ:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)


def _apagar(p: Path) -> None:
    with _TRAVA_ARQ:
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def _controle(cfg, contagem_id: str) -> dict | None:
    p = _pasta(cfg)
    return None if p is None else _ler_json(p / _nome(str(contagem_id)))


def _viva(id_almox: str, contagem_id: str | None = None) -> bool:
    """Há gravação andando (ou começando) neste almoxarifado neste processo? Com `contagem_id`, só se for a dela."""
    reg = _ATIVAS.get(id_almox)
    if not reg or (contagem_id is not None and reg[0] != contagem_id):
        return False
    return reg[1] is None or reg[1].is_alive()


def _reservar(cfg, id_almox: str, contagem_id: str) -> None:
    """A vez do almoxarifado para esta contagem (chamar sob `_TRAVA`). Recusa se outra contagem anda neste processo, ou se o
    arquivo da vez é de outra contagem que ainda não terminou (a parada no meio também segura: o resto dela, e talvez a
    sessão aberta, esperam quem aprovou). O arquivo sem controle é de uma aprovação que nem começou (o controle se grava
    antes de qualquer pedido ao Fracttal): não segura nada."""
    reg = _ATIVAS.get(id_almox)
    if reg and reg[0] != contagem_id and _viva(id_almox):
        raise Recusada(f"Não gravei: {EM_ANDAMENTO}. Espere ela terminar.")
    p = _caminho_trava(cfg, id_almox)
    dono = _ler_json(p)
    outra = str((dono or {}).get("contagem_id") or "")
    if outra and outra != contagem_id:
        ctrl = _controle(cfg, outra)
        if ctrl is not None and ctrl.get("estado") not in ("concluida", "encerrada"):
            raise Recusada(f"Não gravei: {EM_ANDAMENTO} (outra contagem, parada no meio: quem a aprovou precisa continuar).")
    _gravar_json(p, {"contagem_id": contagem_id, "desde": _iso(_agora())})


def _soltar(cfg, id_almox: str, contagem_id: str) -> None:
    """Solta a vez do almoxarifado, se ainda for desta contagem."""
    p = _caminho_trava(cfg, id_almox)
    dono = _ler_json(p)
    if dono is None or str(dono.get("contagem_id") or "") == contagem_id:
        _apagar(p)


# ── quem aprova ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _hmac(cfg, pessoa) -> str:
    """O código da pessoa (o `pessoa_hmac`): o que veio pronto ou o do e-mail. Nunca o e-mail."""
    if not isinstance(pessoa, dict):
        return ""
    return str(pessoa.get("pessoa_hmac") or codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), pessoa.get("email")) or "")


def e_o_aprovador(cfg, contagem_id: str, pessoa) -> bool:
    """`pessoa` (`{"email"}` ou `{"pessoa_hmac"}`) é quem aprovou a gravação desta contagem? Pelo HMAC: o controle não
    guarda e-mail."""
    try:
        ctrl = _controle(cfg, contagem_id)
    except Recusada:
        return False
    quem = _hmac(cfg, pessoa)
    return bool(ctrl and quem and quem == (ctrl.get("aprovador") or {}).get("pessoa_hmac"))


# ── o específico cujo genérico ainda tem unidades por identificar ────────────────────────────────────────────────────────
def _com_generico_pendente(linhas: list[dict], curadoria: dict) -> set[str]:
    """Os específicos que receberam unidades confirmadas de um genérico que ainda tem linhas por identificar. As contas
    (`contas._ler`) marcam a pendência no genérico; aqui se acha o específico dele: as unidades ainda pendentes podem ser
    dele também, e gravar agora fixaria um número que a curadoria vai mudar."""
    cur = {A._id(k): v for k, v in (curadoria or {}).items() if isinstance(v, dict)}
    destinos: dict[str, set] = {}
    pendentes: set[str] = set()
    for l in contas._unicas(linhas):
        if A._txt(l.get("Tipo")).lower() != "identificar":
            continue
        generico = A._id(l.get("ID do item"))
        n = A.contado(l.get("Contado"))
        if not generico or n is None:
            continue
        dec = cur.get(A._id(l.get("ID da linha"))) or {}
        # como `contas._ler`: o "confirmar" sem alvo (nem na decisão, nem no "Identificado como") é pendente
        destino = (A._id(dec.get("id_item")) or A._id(l.get("Identificado como"))
                   if A._txt(dec.get("decisao")) == "confirmar" else "")
        if not destino:
            pendentes.add(generico)
        elif n != 0:
            destinos.setdefault(generico, set()).add(destino)
    return {d for g in pendentes for d in destinos.get(g, ())}


# ── o trabalho ───────────────────────────────────────────────────────────────────────────────────────────────────────────
class _Trabalho:
    """Uma rodada da gravação de UMA contagem (o `iniciar` ou um `continuar`), numa thread. Toda mudança de estado vai ao
    controle antes do pedido seguinte ao Fracttal: é dele que a retomada parte."""

    def __init__(self, cfg, ctrl: dict, estoque, dormir=None, agora=None):
        self.cfg, self.c, self.e = cfg, ctrl, estoque
        self._dormir = dormir or _dormir
        self._agora = agora or _agora
        self.almox = ctrl["id_almox"]
        self._atual: str | None = None            # a peça do pedido em curso (o evento de erro diz qual)
        self._lote_atual: int | None = None
        self._parando = False                       # fechando antes de parar: o disco que falha não segura o Fracttal

    # o controle
    def salvar(self) -> None:
        self.c["atualizado_em"] = _iso(self._agora())
        try:
            _gravar_json(_caminho(self.cfg, self.c["contagem_id"]), self.c)
        except OSError as ex:
            # parando, fechar a sessão no Fracttal vale mais que o controle em dia: a retomada parte do modo (o "aberto"
            # velho com o almoxarifado em modo 0 vira "fechada fora", e a releitura decide cada peça)
            if not self._parando:
                raise
            logging.error("inventário %s: o controle não gravou enquanto a gravação parava: %s", self.c["contagem_id"],
                          type(ex).__name__)

    def item(self, i: str) -> dict:
        return self.c["itens"][i]

    def marcar(self, it: dict, estado: str, **mais) -> None:
        it["estado"] = estado
        it.update(mais)
        if estado in REGISTRAVEIS:
            it["registrado"] = False
        self.salvar()

    def marcar_lote(self, lote: dict, estado: str, **mais) -> None:
        lote["estado"] = estado
        lote.update(mais)
        self.salvar()

    def ref(self, lote: dict) -> str:
        base = f"INVENTARIO-{self.c['contagem_id']}-L{lote['n']}"
        return base if lote["sessao"] <= 1 else f"{base}-S{lote['sessao']}"

    def desde(self, lote: dict) -> str:
        return _iso(instante(lote["aberto_em"]) - MARGEM_RELOGIO)

    def nos_estados(self, lote: dict, *estados) -> list[str]:
        return [i for i in lote["itens"] if self.item(i)["estado"] in estados]

    def lote_feito(self, lote: dict) -> bool:
        return lote["estado"] not in SESSAO and all(
            self.item(i)["estado"] in FINAIS and self.item(i).get("registrado") for i in lote["itens"])

    # o Fracttal
    def chamar(self, f, *args):
        """Um pedido ao Fracttal; o 429 espera 62 s e tenta UMA vez (o 429 do Fracttal não executa nada: repetir é seguro).
        Nunca para o `fechar_ajuste`, que são dois pedidos (ver `fechar`)."""
        try:
            return f(*args)
        except Limite:
            self._dormir(ESPERA_LIMITE_S)
            try:
                return f(*args)
            except Limite as ex:
                raise _LimiteDeNovo() from ex

    def modo(self, lote: dict) -> int:
        m = self.chamar(self.e.modo, self.almox)
        if m == 3:
            raise _Parar(MODO_3)
        if m == 2 and lote["estado"] not in SESSAO:
            raise _Parar(OUTRO)
        if m not in (0, 2):
            raise _Parar(MODO_DESCONHECIDO.format(modo=m))
        return m

    # a rodada
    def rodar(self) -> None:
        if not self.c.get("aprovacao_registrada"):
            try:
                self.registrar_aprovacao()         # o Fracttal ainda nem foi tocado: nenhuma sessão aberta
            except _Parar:
                raise
            except Exception as ex:                # noqa: BLE001 — é o banco que falhou, não o Fracttal
                raise _Parar(SEM_LIVRO) from ex
        # o que ficou por registrar da rodada anterior vai no `registrar` do 1º lote visitado, DEPOIS de fechar a sessão
        # que ela deixou aberta (registrar antes seria segurar o almoxarifado travado enquanto o banco responde)
        for lote in self.c["lotes"]:
            if self.lote_feito(lote):
                continue
            self._lote_atual = lote["n"]
            self.lote(lote)
        self._lote_atual = None
        erros = [i for i, it in self.c["itens"].items() if it["estado"] == "erro"]
        if erros:
            n = len(erros)
            raise _Parar(RELEITURA.format(n=n, pecas="peça" if n == 1 else "peças",
                                          conferiram="conferiu" if n == 1 else "conferiram"))

    def lote(self, lote: dict) -> None:
        if lote["estado"] in SESSAO:                # a sessão que a rodada anterior deixou (talvez) aberta
            m = self.modo(lote)
            if m == 2:
                self.conferir_que_e_nossa(lote)
            self.retomar_sessao(lote, m)
        self.confirmar(lote)
        self.registrar()
        if self.nos_estados(lote, "pendente"):
            self.sessao_nova(lote)
            self.confirmar(lote)
            self.registrar()
        if self.lote_feito(lote):
            self.marcar_lote(lote, "feito")

    def conferir_que_e_nossa(self, lote: dict) -> None:
        """O modo 2 que o controle diz ser nosso é mesmo a nossa sessão? O controle pode estar velho: alguém finalizou a
        nossa sessão no Fracttal e abriu outra, e a retomada finalizaria a dos outros. O histórico desde a hora em que a
        nossa abriu (sem folga: a de outra pessoa é depois) não pode ter movimento de outra referência. QUASE sempre pega:
        quem só solta o modo, sem finalizar, não deixa rastro."""
        outros = self.chamar(self.e.mexidas_desde, self.almox, lote["aberto_em"], None, self.prefixo())
        if outros is None or outros:
            raise _Parar(OUTRO_DEPOIS)

    def prefixo(self) -> str:
        return f"INVENTARIO-{self.c['contagem_id']}-"

    def retomar_sessao(self, lote: dict, m: int) -> None:
        """A sessão que a rodada anterior deixou em `abrindo`, `aberto` ou `fechando`, pelo modo de agora (já conferido:
        3 parou). Modo 2 é a nossa ainda aberta: grava o que faltava (a `enviando` regrava, absoluto) e fecha; do
        `fechando`, procura o fechamento antes de qualquer finalizar. Modo 0: ela já não está aberta (o `abrir` não valeu,
        ou os dois passos do fechamento valeram, ou alguém a fechou no Fracttal); a releitura decide cada peça."""
        if m == 2:
            if lote["estado"] != "fechando" and self.nos_estados(lote, "escrita", "enviando"):
                # o controle pode não saber que o finalizar já foi (o disco que falhou enquanto parava, e o 2º passo do
                # fechamento que falhou junto): procura antes de gravar mais ou de finalizar de novo
                achado = self.chamar(self.e.achar_movimento, self.almox, lote["ref"], self.desde(lote))
                if achado:
                    self.chamar(self.e.voltar_ao_normal, self.almox)
                    self.sessao_fechada(lote, _digitos(achado))
                    return
            if lote["estado"] == "abrindo":
                self.marcar_lote(lote, "aberto")
            if lote["estado"] == "aberto":
                self.gravar_itens(lote, self.chamar(self.e.ler, self.almox))
            self.fechar(lote, m)
        elif lote["estado"] == "abrindo":
            self.marcar_lote(lote, "pendente")      # nada se grava em "abrindo": não há o que conferir
        elif lote["estado"] == "fechando":
            self.sessao_fechada(lote, self.folio_achado(lote))
        else:
            self.sessao_fechada(lote, "")

    def sessao_nova(self, lote: dict) -> None:
        self.modo(lote)                             # 3 ou 2 de outro: para sem mexer
        # sem as nossas próprias sessões (as de outros lotes e a 1ª deste): o movimento que o Nexus fez não é conflito
        mexidas = self.chamar(self.e.mexidas_desde, self.almox, self.c["contada_em"], None, self.prefixo())
        if mexidas is None:
            raise _Parar(SEM_HISTORICO)
        antes = self.chamar(self.e.ler, self.almox)
        for i in self.nos_estados(lote, "pendente"):
            if i not in antes:                      # nunca ligada: liga ANTES de abrir (ligar no modo 2 não foi provado)
                self._atual = i
                self.chamar(self.e.ligar, self.almox, i)
        self._atual = None
        self.modo(lote)                             # de novo, logo antes de abrir: nunca gravar na sessão de outra pessoa
        lote["sessao"] = lote.get("sessao", 0) + 1
        self.marcar_lote(lote, "abrindo", ref=self.ref(lote), aberto_em=_iso(self._agora()),
                         mexidas=sorted({str(m) for m in mexidas} & set(lote["itens"])))
        self.chamar(self.e.abrir_ajuste, self.almox)
        self.marcar_lote(lote, "aberto")
        agora = self.chamar(self.e.ler, self.almox)  # com o modo aberto nada se move: esta é a leitura que vale
        self.gravar_itens(lote, agora)
        self.fechar(lote)

    def conflito(self, i: str, it: dict, agora: dict, mexidas) -> str:
        if i in mexidas:
            return MEXIDA
        if i not in agora:
            return NAO_LIGADA
        if not _igual(_saldo(agora, i), it["sistema"]):
            return SALDO_MUDOU.format(de=_txt_num(it["sistema"]), agora=_txt_num(_saldo(agora, i)))
        return ""

    def gravar_itens(self, lote: dict, agora: dict) -> None:
        """Grava as peças que faltam na sessão aberta. A `enviando` (a sem resposta) já passou pela conferência: regrava
        (absoluto). A `pendente` é conferida contra a leitura com o modo aberto e o histórico; conflito não grava."""
        for i in lote["itens"]:
            it = self.item(i)
            if it["estado"] == "pendente":
                motivo = self.conflito(i, it, agora, set(lote.get("mexidas") or ()))
                if motivo:
                    self.marcar(it, "conflito", motivo=motivo)
                    continue
                self.marcar(it, "enviando")
            elif it["estado"] != "enviando":
                continue
            self._atual = i
            self.chamar(self.e.gravar_saldo, self.almox, i, it["contado"])
            self.marcar(it, "escrita")
        self._atual = None

    # o fechamento
    def fechar(self, lote: dict, m: int | None = None) -> None:
        """Fecha a sessão. Do `aberto`: o finalizar, que NUNCA se repete às cegas (são dois pedidos: se o 2º falhou, o 1º
        valeu); um 429 espera 62 s e recupera procurando o fechamento. Do `fechando` (a retomada): recupera."""
        if lote["estado"] == "aberto":
            self.marcar_lote(lote, "fechando")
            try:
                self.e.fechar_ajuste(self.almox, lote["ref"])
            except Limite:
                self._dormir(ESPERA_LIMITE_S)
                folio = self.recuperar_fechamento(lote)
            except SemLogin:
                raise
            except Exception:
                # a resposta perdida (não o 429): o finalize talvez valeu, e o histórico pode ainda não mostrá-lo. Espera
                # antes de a parada procurar pela referência (`fechar_seguro`), senão o "não achei" finalizaria de novo
                self._dormir(ESPERA_LIMITE_S)
                raise
            else:
                # o folio do movimento achado pela referência, e não o `folio_return` (o "próximo número"): o mesmo número
                # que a retomada acha, nos dois caminhos
                folio = self.folio_achado(lote)
        else:
            folio = self.recuperar_fechamento(lote, m)
        self.sessao_fechada(lote, folio)

    def recuperar_fechamento(self, lote: dict, m: int | None = None) -> str:
        """A sessão em `fechando` (o finalizar talvez tenha valido). Modo 0: os dois passos valeram (ou fecharam fora do
        Nexus). Modo 2: procura o fechamento pela referência; achou, só volta ao normal ("fechamento feito, modo 0
        pendente"). Não achou: finaliza, se alguma peça foi gravada na sessão (a escrita certa, ou a sem resposta cujo
        saldo já é o contado); sem nada gravado não há movimento para achar, e só volta ao normal."""
        if m is None:
            m = self.chamar(self.e.modo, self.almox)
        if m == 0:
            return self.folio_achado(lote)
        if m == 3:
            raise _Parar(MODO_3)
        if m != 2:
            raise _Parar(MODO_DESCONHECIDO.format(modo=m))
        escritas, enviando = self.nos_estados(lote, "escrita"), self.nos_estados(lote, "enviando")
        if escritas or enviando:
            achado = self.chamar(self.e.achar_movimento, self.almox, lote["ref"], self.desde(lote))
            if achado:
                self.chamar(self.e.voltar_ao_normal, self.almox)
                return _digitos(achado)
            gravou = bool(escritas)
            if not gravou:
                agora = self.chamar(self.e.ler, self.almox)
                gravou = any(_igual(_saldo(agora, i), self.item(i)["contado"]) for i in enviando)
            if gravou:
                try:
                    return _digitos(self.e.fechar_ajuste(self.almox, lote["ref"]))
                except Limite as ex:                 # nunca repetido às cegas: a próxima retomada procura de novo
                    raise _LimiteDeNovo() from ex
        self.chamar(self.e.voltar_ao_normal, self.almox)
        return ""

    def folio_achado(self, lote: dict) -> str:
        if not self.nos_estados(lote, "escrita", "enviando"):
            return ""
        return _digitos(self.chamar(self.e.achar_movimento, self.almox, lote["ref"], self.desde(lote)))

    def sessao_fechada(self, lote: dict, folio: str) -> None:
        for i in lote["itens"]:
            it = self.item(i)
            if it["estado"] == "escrita":
                it.update(estado="fechada", folio=folio)
            elif it["estado"] == "enviando":
                it.update(estado="duvida", folio=folio)
        self.marcar_lote(lote, "pendente")

    def fechar_seguro(self) -> bool:
        """Antes de parar: fecha a sessão que ficou aberta com o que já gravou. True se não ficou nada aberto."""
        lote = next((l for l in self.c["lotes"] if l["estado"] in SESSAO), None)
        if lote is None:
            return True
        self._parando = True
        try:
            if lote["estado"] == "abrindo":
                # nada se grava em "abrindo": aberta ou não, só o modo 0 (sem finalizar uma sessão vazia que talvez nem abriu)
                if self.chamar(self.e.modo, self.almox) == 2:
                    self.chamar(self.e.voltar_ao_normal, self.almox)
                self.marcar_lote(lote, "pendente")
            else:
                self.fechar(lote)
            return True
        except Exception as ex:      # noqa: BLE001 — não fechou: a parada avisa que ficou travado
            logging.warning("inventário %s: não consegui fechar a sessão do almoxarifado %s antes de parar (%s)",
                            self.c["contagem_id"], self.almox, type(ex).__name__)
            return False

    # a releitura
    def confirmar(self, lote: dict) -> None:
        """Relê o almoxarifado (fora da sessão) e decide cada peça fechada: o saldo é o contado → `gravada`. A sem resposta
        com o saldo da aprovação nunca foi gravada → volta a `pendente`. O resto → `erro`. O `erro` de uma rodada anterior
        (o "Continuar") só relê, nunca regrava: bate → `gravada`; não bate → `conflito` (o PCM olha)."""
        rodada = self.c["rodada"]
        olhar = [i for i in lote["itens"] if self.item(i)["estado"] in ("fechada", "duvida")
                 or (self.item(i)["estado"] == "erro" and self.item(i).get("erro_rodada", 0) < rodada)]
        if not olhar:
            return
        depois = self.chamar(self.e.ler, self.almox)
        for i in olhar:
            it, saldo = self.item(i), _saldo(depois, i)
            if _igual(saldo, it["contado"]):
                it.update(estado="gravada", motivo="", registrado=False)
            elif it["estado"] == "duvida" and _igual(saldo, it["sistema"]):
                it.update(estado="pendente")
            elif it["estado"] == "erro":
                it.update(estado="conflito", motivo=NAO_BATEU_DE_NOVO.format(agora=_txt_num(saldo)), registrado=False)
            else:
                it.update(estado="erro", motivo=NAO_BATEU.format(agora=_txt_num(saldo)), registrado=False,
                          n_erros=it.get("n_erros", 0) + 1, erro_rodada=rodada)
        self.salvar()

    # o livro do inventário
    def base(self, tipo: str, evento_id: str) -> dict:
        e = {"evento_id": evento_id, "tipo": tipo, "contagem_id": self.c["contagem_id"], "id_almoxarifado": self.almox,
             "pessoa_hmac": self.c["aprovador"]["pessoa_hmac"]}
        if self.c["aprovador"].get("pessoa_id") is not None:
            e["pessoa_id"] = self.c["aprovador"]["pessoa_id"]
        if self.c.get("usina_id"):                   # a usina vai com a linhagem, ou nenhuma das duas
            e["usina_id"], e["usina_ligada_por"] = self.c["usina_id"], self.c["usina_ligada_por"]
        return e

    def evento(self, i: str, it: dict, tipo: str) -> dict:
        chave = (tipo, i, it.get("n_erros", 0)) if tipo == "erro" else (tipo, i)
        e = self.base(tipo, _id_evento(self.c["contagem_id"], *chave))
        e.update(id_item=i, codigo=it["codigo"], de_qtd=it["sistema"], para_qtd=it["contado"],
                 contado_qtd=it["contado_campo"], situacao=it["situacao"], lote=it["lote"])
        if tipo == "peca_gravada" and it.get("folio"):
            e["movimento_fracttal"] = it["folio"]
        if tipo != "peca_gravada" and it.get("motivo"):
            e["dados"] = {"motivo": it["motivo"]}
        return e

    def acrescentar(self, eventos: list[dict]) -> None:
        """Acrescenta os eventos que o livro ainda não tem (pelo `evento_id`): a retomada depois de uma resposta perdida do
        banco não duplica a auditoria."""
        ja = {str(e.get("evento_id")) for e in F.ler(self.cfg, forcar=True)[F.ABA_EVENTO]
              if str(e.get("contagem_id")) == self.c["contagem_id"]}
        novos = [e for e in eventos if e["evento_id"] not in ja]
        F.acrescentar(self.cfg, F.ABA_EVENTO, novos)

    def eventos_da_aprovacao(self) -> list[dict]:
        """UM `aprovada` por peça do lote (a leitura sabe o que falta por eles), e o `conflito` do específico preso pela
        curadoria, já na aprovação."""
        eventos = []
        for i, it in self.c["itens"].items():
            e = self.base("aprovada", _id_evento(self.c["contagem_id"], "aprovada", i))
            e.update(id_item=i, codigo=it["codigo"], de_qtd=it["sistema"], para_qtd=it["contado"],
                     contado_qtd=it["contado_campo"], situacao=it["situacao"], lote=it["lote"])
            eventos.append(e)
        eventos += [self.evento(i, it, "conflito") for i, it in self.c["itens"].items()
                    if it["estado"] == "conflito" and not it.get("registrado")]
        return eventos

    def registrar_aprovacao(self) -> None:
        try:
            self.acrescentar(self.eventos_da_aprovacao())
        except (F.Recusada, ValueError) as ex:
            raise _Parar(SEM_LIVRO) from ex
        self.c["aprovacao_registrada"] = True
        for it in self.c["itens"].values():
            if it["estado"] == "conflito":
                it["registrado"] = True
        self.salvar()

    def registrar(self) -> None:
        faltam = [(i, it) for i, it in self.c["itens"].items() if it["estado"] in REGISTRAVEIS and not it.get("registrado")]
        if not faltam:
            return
        try:
            self.acrescentar([self.evento(i, it, TIPO_DO_EVENTO[it["estado"]]) for i, it in faltam])
        except Exception as ex:      # noqa: BLE001 — o banco fora, ou a resposta perdida: a retomada registra de novo, sem duplicar
            raise _Parar(SEM_LIVRO) from ex
        for _, it in faltam:
            it["registrado"] = True
        self.salvar()

    def erro_geral(self, ex: Exception) -> None:
        """O evento `erro` da parada inesperada: o TIPO do erro (e o método do Fracttal), nunca o texto dele, que pode ter
        nome de gente. Melhor esforço: se o livro não aceitar, o controle guarda o motivo."""
        self.c["erros_gerais"] = self.c.get("erros_gerais", 0) + 1
        tipo = type(ex).__name__ + (f" em {ex.metodo}" if isinstance(ex, ErroFracttal) and ex.metodo else "")
        e = self.base("erro", _id_evento(self.c["contagem_id"], "erro_geral", self.c["rodada"], self.c["erros_gerais"]))
        if self._atual:
            it = self.item(self._atual)
            e.update(id_item=self._atual, codigo=it["codigo"], situacao=it["situacao"], lote=it["lote"])
        elif self._lote_atual:
            e["lote"] = self._lote_atual
        e["dados"] = {"motivo": f"a gravação parou: {tipo}"}
        try:
            self.acrescentar([e])
        except Exception as erro:   # noqa: BLE001 — o motivo fica no controle
            logging.warning("inventário %s: o evento de erro não entrou no livro (%s)", self.c["contagem_id"],
                            type(erro).__name__)
        self.salvar()

    def fim(self, estado: str, motivo: str) -> None:
        self.c.update(estado=estado, motivo=motivo, fim=_iso(self._agora()))
        self.salvar()
        if estado == "concluida":
            _soltar(self.cfg, self.almox, self.c["contagem_id"])


def _motivo_do_erro(ex: Exception) -> str:
    if isinstance(ex, ErroFracttal):
        return f"o Fracttal recusou um pedido ({type(ex).__name__} em {ex.metodo or 'um método'})"
    return f"o Fracttal não respondeu como esperado ({type(ex).__name__})"


def _executar(t: _Trabalho) -> None:
    cid = t.c["contagem_id"]
    try:
        try:
            t.rodar()
        except _Parar as p:
            t.fim("parada", p.motivo)
        except SemLogin:
            t.fim("parada", LOGIN)                  # sem login não há como fechar: o aviso forte sai do estado do lote
        except _LimiteDeNovo:
            t._dormir(ESPERA_LIMITE_S)              # a pausa que o Fracttal pediu, antes de tentar fechar
            t.fechar_seguro()
            t.fim("parada", LIMITE)
        except Exception as ex:                     # noqa: BLE001 — o Fracttal recusou, a rede caiu: fecha, registra e para
            logging.warning("inventário %s: a gravação parou (%s)", cid, type(ex).__name__)
            t.fechar_seguro()
            t.erro_geral(ex)
            t.fim("parada", _motivo_do_erro(ex))
        else:
            t.fim("concluida", "")
    except Exception as ex:                         # noqa: BLE001 — nem o controle gravou: o log diz, a vez se solta abaixo
        # só o tipo: o texto do erro pode ser o do Fracttal, e ele pode ter nome de gente
        logging.error("inventário %s: a gravação parou sem conseguir gravar o controle: %s", cid, type(ex).__name__)
    finally:
        with _TRAVA:
            reg = _ATIVAS.get(t.almox)
            if reg and reg[0] == cid:
                _ATIVAS.pop(t.almox, None)


def _comecar(t: _Trabalho) -> None:
    """A thread da gravação (chamar sob `_TRAVA`, com a vez já reservada)."""
    th = threading.Thread(target=_executar, args=(t,), name=f"inventario-{t.c['contagem_id']}", daemon=True)
    _ATIVAS[t.almox] = (t.c["contagem_id"], th)
    th.start()


# ── a interface ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def iniciar(cfg, contagem: dict, itens: list[dict], estoque, aprovador: dict, *, curadoria: dict | None = None,
            dormir=None, agora=None) -> dict:
    """Aprova e começa a gravação, numa thread. `contagem`: a de `leitura` (contagem_id, id_almox, almox, usina_id,
    usina_ligada_por, contada_em, linhas). `itens`: o `contas.itens_do_lote` com o saldo da aprovação; só vão
    `not tirada and situacao in MEXEM`. `estoque`: o `Estoque` com o login de quem aprova (só na memória). `aprovador`:
    `{"pessoa_hmac", "pessoa_id"}`. Grava UM evento `aprovada` por peça do lote antes de começar.

    `Recusada` (nada foi gravado, nem no livro nem no Fracttal): sem quem aprova, nada a gravar, a contagem já aprovada,
    outra gravação andando (ou parada no meio) no mesmo almoxarifado, sem a pasta de dados, o livro que não aceitou."""
    cid = A._txt(contagem.get("contagem_id"))
    almox = A._id(contagem.get("id_almox"))
    if not cid:
        raise Recusada("Contagem sem o ID: nada foi gravado.", 400)
    if not _RE_DIGITOS.fullmatch(almox):
        raise Recusada("Contagem sem o almoxarifado do Fracttal: nada foi gravado.", 400)
    hmac_ = A._txt((aprovador or {}).get("pessoa_hmac"))
    if not hmac_:
        raise Recusada(SEM_PESSOA)
    try:
        instante(contagem.get("contada_em"))
    except ValueError:
        raise Recusada("A data da contagem está ilegível: sem ela não há o que olhar depois dela.", 400) from None
    lote, vistos = [], set()
    for i in itens or []:
        if not isinstance(i, dict):
            continue
        id_item = A._id(i.get("id_item"))
        if not id_item or i.get("tirada") or i.get("situacao") not in contas.MEXEM or id_item in vistos:
            continue
        if not _RE_DIGITOS.fullmatch(id_item):
            raise Recusada(f"A peça {id_item[:20]} não tem um ID do Fracttal: nada foi gravado.", 400)
        try:
            contado = validar_quantidade(i.get("contado"), "contado")
        except ValueError:
            raise Recusada(f"A peça {id_item} tem um contado que não vai ao Fracttal: nada foi gravado.", 400) from None
        vistos.add(id_item)
        lote.append((id_item, i, contado))
    if not lote:
        raise Recusada("Nada a gravar: nenhuma peça do lote mexe no estoque.")
    F._cofre_ou_recusar(cfg)          # o motivo do conflito vai cifrado: sem a chave, pararia no meio da gravação
    if curadoria is None and contagem.get("linhas"):
        from . import leitura
        curadoria = leitura.curadoria_da(cfg, cid)
    presos = _com_generico_pendente(contagem.get("linhas") or [], curadoria or {})
    gravaveis = [x for x in lote if x[0] not in presos]
    lotes = [{"n": n, "itens": [x[0] for x in gravaveis[k:k + TAMANHO_LOTE]], "estado": "pendente", "sessao": 0, "ref": "",
              "aberto_em": "", "mexidas": []}
             for n, k in enumerate(range(0, len(gravaveis), TAMANHO_LOTE), 1)]
    n_do_lote = {i: l["n"] for l in lotes for i in l["itens"]}
    agora_ = _iso((agora or _agora)())
    ctrl = {
        "contagem_id": cid, "id_almox": almox, "almox_nome": A._txt(contagem.get("almox")) or f"O almoxarifado {almox}",
        "usina_id": contagem.get("usina_id") or None,
        "usina_ligada_por": contagem.get("usina_ligada_por") if contagem.get("usina_id") else None,
        "contada_em": A._txt(contagem.get("contada_em")),
        "aprovador": {"pessoa_hmac": hmac_, "pessoa_id": (aprovador or {}).get("pessoa_id")},
        "estado": "gravando", "motivo": "", "rodada": 1, "aprovada_em": agora_, "atualizado_em": agora_, "fim": None,
        "aprovacao_registrada": False, "erros_gerais": 0, "lotes": lotes,
        "itens": {i: {"codigo": A._txt(x.get("codigo")), "sistema": _num(x.get("sistema")), "contado": contado,
                      "contado_campo": _num(x.get("contado_campo")), "situacao": x.get("situacao"),
                      "lote": n_do_lote.get(i), "estado": "conflito" if i in presos else "pendente",
                      "motivo": GENERICO if i in presos else "", "folio": "", "registrado": False, "n_erros": 0,
                      "erro_rodada": 0}
                  for i, x, contado in lote},
    }
    t = _Trabalho(cfg, ctrl, estoque, dormir, agora)
    caminho = _caminho(cfg, cid)
    with _TRAVA:
        if _controle(cfg, cid) is not None:
            raise Recusada("Esta contagem já foi aprovada: a gravação dela está em andamento ou parada (quem aprovou "
                           "continua).")
        _reservar(cfg, almox, cid)
        _ATIVAS[almox] = (cid, None)                # a vez é desta contagem enquanto a aprovação se registra
        try:
            t.salvar()
        except Exception:
            _ATIVAS.pop(almox, None)
            _soltar(cfg, almox, cid)
            raise
    # o registro da aprovação vai ao banco fora da trava (pode levar segundos); o Fracttal ainda não foi tocado
    try:
        t.registrar_aprovacao()
    except _Parar as p:
        with _TRAVA:
            _ATIVAS.pop(almox, None)
            _apagar(caminho)
            _soltar(cfg, almox, cid)
        raise Recusada(f"O livro do inventário não aceitou a aprovação ({p.__cause__ or p.motivo}): nada foi gravado.",
                       503) from None
    except Exception as ex:      # noqa: BLE001 — o banco talvez tenha gravado: a aprovação fica parada, e o "Continuar" refaz
        t.fim("parada", "não consegui confirmar o registro da aprovação no livro do inventário: continue para tentar de novo")
        with _TRAVA:
            _ATIVAS.pop(almox, None)
        raise Recusada(f"Não consegui confirmar o registro da aprovação ({type(ex).__name__}): nada foi ao Fracttal; quem "
                       "aprovou pode continuar.", 503) from None
    with _TRAVA:
        _comecar(t)
    return estado(cfg, cid)


def continuar(cfg, contagem_id: str, estoque, pessoa: dict, *, dormir=None, agora=None) -> dict:
    """Retoma a gravação parada (ou a que o Nexus interrompeu ao reiniciar), no login de `pessoa`, que tem de ser quem
    aprovou (`SoQuemAprovou`, pelo HMAC). A retomada parte do controle: a sessão aberta é fechada (ou terminada) antes de
    qualquer outra coisa, e o `erro` da releitura só é relido."""
    cid = A._txt(contagem_id)
    ctrl = _controle(cfg, cid)
    if ctrl is None:
        raise Recusada("Esta contagem não tem gravação para continuar.", 404)
    if not e_o_aprovador(cfg, cid, pessoa):
        raise SoQuemAprovou()
    almox = ctrl["id_almox"]
    with _TRAVA:
        if _viva(almox, cid):
            raise Recusada("A gravação desta contagem já está andando.")
        ctrl = _controle(cfg, cid)
        if ctrl.get("estado") == "concluida":
            raise Recusada("A gravação desta contagem já terminou.")
        if ctrl.get("estado") == "encerrada":
            raise Recusada("A gravação desta contagem foi encerrada: não se continua.")
        _reservar(cfg, almox, cid)
        ctrl.update(estado="gravando", motivo="", fim=None, rodada=int(ctrl.get("rodada") or 1) + 1)
        t = _Trabalho(cfg, ctrl, estoque, dormir, agora)
        t.salvar()
        _comecar(t)
    return estado(cfg, cid)


def _fmt(v) -> str:
    n = _num(v)
    return "-" if n is None else f"{n:.6f}"


def assinatura(itens: list[dict]) -> str:
    """A impressão digital do lote que vai ao Fracttal: (id_item, sistema, contado) de cada peça `not tirada and situacao
    in MEXEM`, em ordem. A tela a manda de volta com o "Gravar": o N igual não basta (um saldo que mudou de 10 para 11, com
    o contado 12, segue "para cima" e o N não muda, mas o PCM aprovou o que viu)."""
    linhas = sorted(f"{A._id(i.get('id_item'))}|{_fmt(i.get('sistema'))}|{_fmt(i.get('contado'))}"
                    for i in itens or [] if isinstance(i, dict) and i.get("id_item") and not i.get("tirada")
                    and i.get("situacao") in contas.MEXEM)
    return hashlib.sha1("\n".join(linhas).encode("utf-8")).hexdigest()[:20]


def aprovar(cfg, contagem_id: str, estoque, aprovador: dict, n_visto=None, assinatura_vista=None, **opcoes) -> dict:
    """O botão "Gravar N alterações": confere a contagem de agora (o livro relido), lê o saldo NA HORA com o login de quem
    aprova, monta o lote pelas contas (com a revisão e a curadoria) e começa. `n_visto` e `assinatura_vista`: o N e a
    `assinatura` do lote que a tela mostrou (obrigatórios); se o lote mudou desde então (um saldo mudou, outro PCM revisou),
    recusa: ninguém grava o que não viu. `SemLogin` sobe (a ponte manda entrar pelo Fracttal); o resto vira `Recusada`."""
    from . import leitura
    if not aprovador or not aprovador.get("pessoa_hmac"):
        raise Recusada(SEM_PESSOA)
    if n_visto is None or not isinstance(assinatura_vista, str) or not assinatura_vista.strip():
        raise Recusada("A tela não mandou o lote que mostrou: recarregue a página. Nada foi gravado.", 400)
    try:
        F.ler(cfg, forcar=True)
        todas = leitura.ler(cfg)
    except F.Recusada as ex:
        raise Recusada(str(ex), 503) from None
    c = next((x for x in todas["contagens"] if x["contagem_id"] == contagem_id), None)
    if c is None:
        raise Recusada("Contagem não encontrada: atualize a página.", 404)
    if not c["aprovavel"]:
        raise Recusada(f"Esta contagem não se grava: {c['motivo_nao_aprovavel']}.")
    revisao, curadoria = leitura.revisao_da(cfg, contagem_id), leitura.curadoria_da(cfg, contagem_id)
    try:
        sistema = estoque.ler(c["id_almox"])
    except SemLogin:
        raise
    except Limite:
        raise Recusada("O Fracttal pediu uma pausa: tente de novo em 1 minuto. Nada foi gravado.", 503) from None
    except Exception as ex:      # noqa: BLE001 — rede fora, o Fracttal recusou: nada foi gravado
        raise Recusada(f"Não consegui ler o saldo do Fracttal agora ({type(ex).__name__}): nada foi gravado.", 503) from None
    itens = contas.itens_do_lote(c["linhas"], sistema, curadoria, revisao)
    n = sum(1 for i in itens if i["id_item"] and not i["tirada"] and i["situacao"] in contas.MEXEM)
    try:
        visto = int(n_visto)
    except (TypeError, ValueError):
        visto = -1
    if visto != n or assinatura_vista.strip() != assinatura(itens):
        raise Recusada(MUDOU)
    return iniciar(cfg, c, itens, estoque, aprovador, curadoria=curadoria, **opcoes)


# ── encerrar ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _parada_desde(ctrl: dict) -> datetime | None:
    try:
        return instante(ctrl.get("fim") or ctrl.get("atualizado_em"))
    except ValueError:
        return None


def _quem_encerra(ctrl: dict, quem: str, admin: bool, agora: datetime, cid: str) -> str:
    """Quem pode encerrar agora: "aprovador" (a qualquer hora) ou "administrador" (parada há mais de 24 h). Recusada com o
    porquê, senão. A gravação andando, a terminada e a já encerrada não se encerram."""
    if _viva(ctrl["id_almox"], cid):
        raise Recusada("A gravação está andando: espere ela parar.")
    if ctrl.get("estado") in ("concluida", "encerrada"):
        raise Recusada("A gravação desta contagem já terminou.")
    if quem and quem == (ctrl.get("aprovador") or {}).get("pessoa_hmac"):
        return "aprovador"
    if admin:
        desde = _parada_desde(ctrl)
        if desde is not None and agora - desde >= timedelta(hours=ADMIN_ENCERRA_H):
            return "administrador"
        raise Recusada(f"O administrador encerra só a gravação parada há mais de {ADMIN_ENCERRA_H} h (antes disso, só quem "
                       "aprovou).", 403)
    raise Recusada(f"Só quem aprovou encerra a gravação (o administrador, depois de {ADMIN_ENCERRA_H} h parada).", 403)


def existe(cfg, contagem_id: str) -> bool:
    """Esta contagem tem gravação? `Recusada` (409) se o controle está ilegível: a ponte diz isso, e não "só quem
    aprovou" (que seria mentira: ninguém sabe quem aprovou)."""
    return _controle(cfg, A._txt(contagem_id)) is not None


def conferir_quem_encerra(cfg, contagem_id: str, pessoa, admin: bool = False, agora=None) -> str:
    """Antes de falar com o Fracttal: quem pode encerrar ("aprovador" ou "administrador"), ou `Recusada` com o porquê."""
    cid = A._txt(contagem_id)
    ctrl = _controle(cfg, cid)
    if ctrl is None:
        raise Recusada("Esta contagem não tem gravação para encerrar.", 404)
    return _quem_encerra(ctrl, _hmac(cfg, pessoa), bool(admin), instante((agora or _agora)()), cid)


def pode_encerrar(cfg, contagem_id: str, pessoa, admin: bool = False, agora=None) -> bool:
    """O "Encerrar" aparece para esta pessoa? Quem aprovou, com a gravação parada; o administrador, parada há 24 h."""
    try:
        conferir_quem_encerra(cfg, contagem_id, pessoa, admin, agora)
        return True
    except Recusada:
        return False


def encerrar(cfg, contagem_id: str, estoque, pessoa: dict, motivo, *, admin: bool = False, agora=None) -> dict:
    """Encerra a gravação parada que ninguém vai continuar (Levi, 26/10/2026). `pessoa`: `{"pessoa_hmac", "pessoa_id"}`
    (ou `{"email"}`) de quem encerra; `admin`: é administrador do Nexus. Só com o almoxarifado FORA do modo 2, lido agora no
    Fracttal pelo `estoque` (o login de quem encerra): encerrar com a sessão aberta largaria o almoxarifado travado sem dono.
    O motivo é obrigatório e vai só cifrado. As peças já conferidas ficam `peca_gravada`; cada uma das outras vira
    `conflito` com o motivo (no nome de quem encerra), e a contagem sai de "gravando". Solta a vez do almoxarifado.
    `Recusada` (nada mudou) com o status; `SemLogin` sobe."""
    cid = A._txt(contagem_id)
    ctrl = _controle(cfg, cid)
    if ctrl is None:
        raise Recusada("Esta contagem não tem gravação para encerrar.", 404)
    motivo = A._txt(motivo) if isinstance(motivo, str) else ""
    if not motivo:
        raise Recusada("Escreva o motivo: ele fica na auditoria.", 400)
    if len(motivo) > MOTIVO_MAX:
        raise Recusada(f"O motivo passa de {MOTIVO_MAX} caracteres: resuma.", 400)
    quem = _hmac(cfg, pessoa)
    if not quem:
        raise Recusada(SEM_PESSOA)
    relogio = agora or _agora
    _quem_encerra(ctrl, quem, admin, instante(relogio()), cid)
    F._cofre_ou_recusar(cfg)                         # o motivo vai cifrado
    try:
        m = estoque.modo(ctrl["id_almox"])
    except SemLogin:
        raise
    except Limite:
        raise Recusada("O Fracttal pediu uma pausa: tente de novo em 1 minuto. Nada mudou.", 503) from None
    except Exception as ex:      # noqa: BLE001 — sem saber o modo, não se encerra
        raise Recusada(f"Não consegui ler o modo do almoxarifado no Fracttal ({type(ex).__name__}): nada mudou.", 503) from None
    if m == 2:
        raise Recusada("O almoxarifado está em ajuste no Fracttal (modo 2): encerrar agora o deixaria travado sem dono. "
                       "Continue a gravação (ou feche o ajuste no Fracttal) e encerre depois.")
    with _TRAVA:
        ctrl = _controle(cfg, cid)                   # o de agora: ninguém continuou enquanto o Fracttal respondia
        papel = _quem_encerra(ctrl, quem, admin, instante(relogio()), cid)
        t = _Trabalho(cfg, ctrl, None, None, relogio)
        quem_ev = {"pessoa_hmac": quem}
        if (pessoa or {}).get("pessoa_id") is not None:
            quem_ev["pessoa_id"] = pessoa["pessoa_id"]
        eventos, mudancas = [], []
        for i, it in ctrl["itens"].items():
            if it["estado"] in FINAIS and it.get("registrado"):
                continue
            if it["estado"] in FINAIS:              # já conferida (ou já em conflito), só faltava o registro
                eventos.append(t.evento(i, it, TIPO_DO_EVENTO[it["estado"]]))
                mudancas.append((it, {"registrado": True}))
                continue
            texto = (ENCERRADA_SEM_GRAVAR if it["estado"] in ("enviando", "escrita", "fechada", "duvida", "erro")
                     else ENCERRADA).format(motivo=motivo)
            novo = dict(it, estado="conflito", motivo=texto)
            e = t.evento(i, novo, "conflito")
            e.pop("pessoa_id", None)
            e.update(quem_ev)                        # o conflito é de quem encerrou, e não de quem aprovou
            eventos.append(e)
            mudancas.append((it, {"estado": "conflito", "motivo": ENCERRADA.format(motivo="motivo na auditoria"),
                                  "registrado": True}))
        try:
            t.acrescentar(eventos)
        except Exception as ex:      # noqa: BLE001 — o banco fora: nada mudou no controle, e se encerra de novo
            raise Recusada(f"O livro do inventário não aceitou o encerramento ({type(ex).__name__}): nada mudou.",
                           503) from None
        for it, mais in mudancas:
            it.update(mais)
        for lote in ctrl["lotes"]:
            lote["estado"] = "feito"
        ctrl.update(estado="encerrada", motivo=f"encerrada por {'quem aprovou' if papel == 'aprovador' else 'um administrador'}",
                    encerrada_por=quem, fim=_iso(relogio()))
        t.salvar()
        _soltar(cfg, ctrl["id_almox"], cid)
    return estado(cfg, cid)


# ── o que as outras telas e o deploy perguntam ──────────────────────────────────────────────────────────────────────────
def _controles(pasta: Path):
    """Os controles da pasta (sem a vez dos almoxarifados), pulando o ilegível."""
    if pasta is None or not pasta.is_dir():
        return
    for arq in sorted(pasta.glob("*.json")):
        if arq.name.startswith("trava-"):
            continue
        try:
            ctrl = _ler_json(arq)
        except Recusada:
            continue
        if ctrl and ctrl.get("contagem_id"):
            yield ctrl


def travadas(cfg) -> list[dict]:
    """As gravações paradas com a sessão (talvez) aberta no Fracttal: `[{"contagem_id", "aviso"}]`. A lista das
    contagens mostra o aviso forte também: quem aprovou pode não abrir a contagem, e o almoxarifado segue travado."""
    out = []
    for ctrl in _controles(_pasta(cfg)):
        est = estado(cfg, ctrl["contagem_id"])
        if est and est["travado"]:
            out.append({"contagem_id": ctrl["contagem_id"], "aviso": est["aviso"]})
    return out


def com_lote_aberto(pasta: Path | None, agora: datetime | None = None) -> list[str]:
    """As contagens com uma gravação VIVA e um lote aberto no Fracttal agora (o deploy espera por elas, decisão do Levi
    de 26/10/2026): o controle em "gravando", um lote em `abrindo`/`aberto`/`fechando`, e salvo há menos de `VIVA_S`. O
    processo que pergunta (o `ferramentas/gravacao_aberta.py`) não é o do Nexus e não vê a thread: a gravação viva salva o
    controle a cada pedido, e a parada (a que o reinício matou, ou a sem login) não ganha nada com a espera."""
    agora = instante(agora or _agora())
    out = []
    for ctrl in _controles(pasta):
        if ctrl.get("estado") != "gravando" or not any(l.get("estado") in SESSAO for l in ctrl.get("lotes") or []):
            continue
        try:
            salvo = instante(ctrl.get("atualizado_em"))
        except ValueError:
            continue
        if agora - salvo <= timedelta(seconds=VIVA_S):
            out.append(str(ctrl["contagem_id"]))
    return out


def _texto(est: dict) -> str:
    if est["estado"] == "gravando":
        return (f"Gravando no Fracttal: lote {est['lote']} de {est['lotes']}, {est['gravadas'] + est['conflitos']} de "
                f"{est['total']} peças conferidas.")
    if est["estado"] in ("concluida", "encerrada"):
        partes = [f"{est['gravadas']} {'peça gravada' if est['gravadas'] == 1 else 'peças gravadas'}"]
        if est["conflitos"]:
            partes.append(f"{est['conflitos']} em conflito (não gravadas: o PCM confere)")
        titulo = "Gravação concluída" if est["estado"] == "concluida" else f"Gravação {est['motivo']}"
        return f"{titulo}: " + ", ".join(partes) + "."
    return f"Gravação parada: {est['motivo']}."


def estado(cfg, contagem_id: str) -> dict | None:
    """O andamento da gravação desta contagem, ou None se ela não tem. `{"estado": "gravando" | "parada" | "concluida" |
    "encerrada", "motivo", "feitas" (peças já escritas no Fracttal), "gravadas" (conferidas na releitura), "total",
    "conflitos", "erros", "lote" (o lote em curso), "lotes", "travado" (parada com a sessão talvez aberta), "aviso" (o aviso
    forte), "parada_desde" (ISO UTC, ou ""), "texto"}`. O controle que diz "gravando" sem a gravação viva neste processo (o
    Nexus reiniciou) é "parada"."""
    cid = A._txt(contagem_id)
    try:
        ctrl = _controle(cfg, cid)
    except Recusada as ex:
        est = {"estado": "parada", "motivo": str(ex), "feitas": 0, "gravadas": 0, "total": 0, "conflitos": 0, "erros": 0,
               "lote": 0, "lotes": 0, "travado": True, "aviso": str(ex), "parada_desde": ""}
        return dict(est, texto=_texto(est))
    if ctrl is None:
        return None
    situacao, motivo = ctrl.get("estado"), ctrl.get("motivo") or ""
    if situacao == "gravando" and not _viva(ctrl["id_almox"], cid):
        situacao, motivo = "parada", INTERROMPIDA
    itens = list((ctrl.get("itens") or {}).values())
    conta = lambda *es: sum(1 for it in itens if it.get("estado") in es)      # noqa: E731
    lotes = ctrl.get("lotes") or []
    aberto = any(l.get("estado") in SESSAO for l in lotes)
    atual = next((l["n"] for l in lotes if l.get("estado") != "feito"), len(lotes))
    travado = situacao == "parada" and aberto
    est = {"estado": situacao, "motivo": motivo, "feitas": conta("escrita", "fechada", "gravada"),
           "gravadas": conta("gravada"), "total": len(itens), "conflitos": conta("conflito"), "erros": conta("erro"),
           "lote": atual, "lotes": len(lotes), "travado": travado,
           "aviso": AVISO_TRAVADO.format(almox=ctrl.get("almox_nome") or "O almoxarifado") if travado else "",
           "parada_desde": _iso(_parada_desde(ctrl)) if situacao == "parada" and _parada_desde(ctrl) else ""}
    est["texto"] = _texto(est)
    return est


def aguardar(contagem_id: str, timeout: float = 30) -> None:
    """Espera a gravação desta contagem terminar neste processo (os testes e as ferramentas)."""
    th = next((t for c, t in list(_ATIVAS.values()) if c == contagem_id and t is not None), None)
    if th is not None:
        th.join(timeout)
