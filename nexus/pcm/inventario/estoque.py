"""O adaptador do estoque do Fracttal: a ÚNICA porta de leitura e gravação de estoque do inventário do almoxarifado
(Levi, 26/10/2026). A gravação, a régua e a curadoria só chamam os métodos daqui; nenhuma tela nem rotina fala
`inventories.*` direto. Isso vale por três razões que o passo 0 de 26/10 mostrou (`docs/superpowers/specs/2026-10-26-
inventario-almoxarifado-passo0.md`, com os métodos, os corpos e as respostas lidos da própria tela do Fracttal):

- O Fracttal responde HTTP 200 com `success: false` e a mensagem no corpo (caso real: desativar peça com saldo,
  `ASSET_CANNOT_BE_DESABLED_STOCK`), e o `_rpc_call` do OS Creator DEVOLVE isso em vez de levantar. Aqui toda resposta é
  conferida, e vira `ErroFracttal`. Lista que chega pela metade (página vazia antes do `total`) também é erro: número
  pela metade não vai para a tela.
- A cota de 200 pedidos por minuto é da EMPRESA inteira (os robôs e o App de Campo gastam dela): os pedidos do adaptador
  saem no máximo a 1 por segundo, no MESMO ritmo para todas as instâncias do processo (duas pessoas gravando juntas somam
  1 por segundo, não 2).
- O ajuste de saldo NÃO é um movimento por peça: é uma SESSÃO do almoxarifado (modo 2, "Ajuste de inventário"). Abre-se o
  modo, grava-se o saldo absoluto de cada peça e fecha-se com uma `description`; ao fechar, o Fracttal gera, por peça
  mexida, um par de movimentos do tipo 15 (saída do saldo antigo inteiro, entrada do novo). Gravar o mesmo número duas
  vezes dá o mesmo saldo (idempotente), e a referência `INVENTARIO-<contagem>` da `description` é como se confirma, depois
  de uma resposta perdida, que o fechamento valeu. ENQUANTO O MODO ESTÁ ABERTO, O ALMOXARIFADO TRAVA Entradas, Saídas e
  Pedidos de compra: quem abre fecha no mesmo trabalho, e a retomada começa fechando o que ficou aberto.

O login do Fracttal é o de quem aprovou (a sessão do OS Creator do pedido): o JWT e o e-mail vivem só na memória desta
instância, nunca em arquivo nem em log. `estoque_da_sessao(app)` monta a instância no pedido; ela pode seguir numa thread
depois, porque guarda o login e não precisa mais do pedido.

`responsible_description` (o nome de quem fez o movimento, no histórico) NUNCA é guardado nem devolvido: é nome de pessoa, e
o repositório e a API de dados são compartilhados.
"""
from __future__ import annotations

import abc
import math
import threading
import time
import unicodedata
from datetime import datetime, timezone

INTERVALO_S = 1.0           # um pedido por segundo (a cota de 200/min é da empresa)
PAGINA = 200                # o máximo que a tela do Fracttal pede
PAGINAS_MAX = 1000          # trava de segurança: uma lista que não acaba seria um laço contra a cota da empresa
TIMEOUT_S = 45              # o mesmo do `_rpc_call` do OS Creator
TIPO_PECA = 4               # `id_type_item` das peças (o que a tela de Peças e Suprimentos lista)

# Os métodos do Fracttal que o passo 0 provou (um nome só por operação, para o teste e o leitor acharem).
LISTA = "inventories.warehouses_list"
SALDOS = "inventories.warehouses_items_stock"
LIGAR = "inventories.associate_warehouses_insert"
MUDAR_MODO = "inventories.warehouse_change_mode"
ATUALIZAR_ALMOX = "inventories.warehouse_update"
ATUALIZAR_LIGACAO = "inventories.warehouses_items_update"
FECHAR = "inventories.warehouse_finalize_mode"
HISTORICO = "inventories.movement_history_list_new"
CRIAR = "inventories.item_insert"
PECAS = "inventories.items_list"
UNIDADES = "companies.units_list"


class Limite(Exception):
    """HTTP 429: a cota de 200 pedidos por minuto da empresa acabou. Quem grava espera e tenta de novo, ou para."""


class SemLogin(Exception):
    """O login do Fracttal de quem aprovou falta, foi recusado ou expirou. Quem grava para; outra sessão continua."""


class ErroFracttal(Exception):
    """O Fracttal respondeu `success: false` (HTTP 200). `mensagem` é o texto dele (um código, como
    `ASSET_CANNOT_BE_DESABLED_STOCK`) e `metodo`, o RPC que recusou."""

    def __init__(self, mensagem: str, metodo: str = ""):
        super().__init__(f"{metodo}: {mensagem}" if metodo else mensagem)
        self.mensagem, self.metodo = mensagem, metodo


# ── as regras que o adaptador e o Fracttal de mentira dividem ──────────────────────────────────────────────────────────
def instante(valor) -> datetime:
    """Uma data ISO (a `date_create` do Fracttal, o "Contada em" do App) como instante com fuso. Sem fuso, é UTC: o App
    grava o "Contada em" em UTC. ValueError se não for data."""
    if isinstance(valor, datetime):
        d = valor
    else:
        s = str(valor or "").strip()
        if s.endswith(("Z", "z")):
            s = s[:-1] + "+00:00"            # o `fromisoformat` só aceita o Z a partir do Python 3.11
        try:
            d = datetime.fromisoformat(s)
        except ValueError:
            raise ValueError(f"data fora do formato ISO: {valor!r}") from None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def validar_quantidade(valor, o_que: str = "saldo") -> float:
    """O número que vai ao estoque do Fracttal: finito e não negativo. Contagem negativa ou NaN gravada como saldo
    absoluto estragaria o estoque da empresa inteira, e o Fracttal não impede. ValueError."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{o_que} não é número: {valor!r}") from None
    if not math.isfinite(n) or n < 0:
        raise ValueError(f"{o_que} precisa ser um número finito e não negativo: {valor!r}")
    return n


def validar_nivel(valor, o_que: str) -> float | None:
    """Mínimo ou máximo da régua: None fica None (não muda); o resto, como a quantidade."""
    return None if valor is None else validar_quantidade(valor, o_que)


def _id(valor) -> int:
    try:
        return int(str(valor).strip())
    except ValueError:
        raise ValueError(f"id do Fracttal precisa ser número: {valor!r}") from None


def _numero_lido(valor, onde: str, metodo: str) -> float | None:
    """O número de uma linha do Fracttal. Nulo e vazio são "não informado" (None), NUNCA 0: o saldo que o Fracttal não
    disse não é saldo zero. Texto que não é número é erro, não vazio (número pela metade não vai para a tela)."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    try:
        n = float(valor)
    except (TypeError, ValueError):
        raise ErroFracttal(f"{onde} ilegível: {valor!r}", metodo) from None
    if not math.isfinite(n):
        raise ErroFracttal(f"{onde} ilegível: {valor!r}", metodo)
    return n


def _no_corpo(n: float):
    """O saldo como a tela o manda (`stock: 5`): inteiro quando é inteiro."""
    return int(n) if n.is_integer() else n


def _nivel_no_corpo(n: float) -> str:
    """A régua como a tela a manda (`"min_stock_level": "2"`, texto) e como a prova de 26/10 gravou."""
    return str(int(n)) if n.is_integer() else repr(n)


def _norm(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


def _traduzir(erro: Exception) -> Exception | None:
    """O erro do `_rpc_call` do OS Creator como o adaptador o diz; None quando não é limite nem login (segue como veio).
    O adaptador não importa o `api.py` (só está no caminho depois que o clone sobe): lê o que ele escreve nos erros,
    e o `test_o_marcador_de_sessao_morta_e_o_do_api_de_verdade` cai se o `api.py` mudar. Sessão morta: o marcador
    `session_expired` da `SessionExpired` (HTTP 401/403 ou USER_NOT_LOGIN no corpo) e, sem marcador, as duas frases do
    `_login_jwt` e do `_rpc_headers` (sem JWT na sessão, e JWT vencido que não renovou). Limite: "HTTP 429"."""
    texto = str(erro)
    if getattr(erro, "session_expired", False) or "não está logado no Fracttal" in texto \
            or "JWT do login do Fracttal expirou" in texto:
        return SemLogin(texto)
    if "HTTP 429" in texto:
        return Limite(texto)
    return None


class Ritmo:
    """O ritmo dos pedidos ao Fracttal: o relógio e a trava de UM só lugar, que todas as instâncias dividem (`RITMO`). A
    cota de 200/min é da empresa: se cada instância tivesse o relógio dela, duas pessoas gravando ao mesmo tempo (cada uma
    com o login e a instância dela) pediriam 2 por segundo. Reserva o próximo segundo livre sob trava e espera por ele fora
    da trava. Conta do INÍCIO de um pedido ao início do outro: o Fracttal que levou 1,5 s já pagou o intervalo.
    É por processo (o Nexus roda num só, com threads) e só dos pedidos do adaptador: os do OS Creator e os dos robôs não
    passam por aqui. O relógio e o `dormir` são injetáveis para o teste não esperar de verdade."""

    def __init__(self, relogio=time.monotonic, dormir=time.sleep, intervalo: float = INTERVALO_S):
        self._relogio, self._dormir, self._intervalo = relogio, dormir, intervalo
        self._trava, self._proximo = threading.Lock(), 0.0

    def esperar(self) -> None:
        with self._trava:
            agora = self._relogio()
            inicio = max(agora, self._proximo)
            self._proximo = inicio + self._intervalo
        if inicio > agora:
            self._dormir(inicio - agora)


RITMO = Ritmo()             # o da empresa: toda `EstoqueFracttal` sem ritmo próprio usa este


# ── o contrato ─────────────────────────────────────────────────────────────────────────────────────────────────────────
class Estoque(abc.ABC):
    """O que a gravação, a régua e a curadoria esperam do estoque. A `EstoqueFracttal` (o Fracttal de verdade) e a
    `EstoqueFalso` (`tests/estoque_falso.py`) cumprem o mesmo contrato, com as mesmas assinaturas (o teste confere).

    Todo id é texto (`id_almox`, `id_item`, a ligação). Erros: `Limite` (429), `SemLogin` (login faltando, recusado ou
    expirado), `ErroFracttal` (o Fracttal recusou, com a mensagem dele), `ValueError` (o pedido não faz sentido e nem
    foi ao Fracttal: peça não ligada, número ruim). Qualquer outro erro (rede, 500) passa como veio: a resposta pode ter
    se perdido DEPOIS do Fracttal gravar, e quem grava confere antes de repetir."""

    @abc.abstractmethod
    def modo(self, id_almox: str) -> int:
        """O `mode` do almoxarifado: 0 normal, 2 ajuste de inventário, 3 inventário físico."""

    @abc.abstractmethod
    def abrir_ajuste(self, id_almox: str) -> None:
        """Abre a sessão de ajuste (modo 2). O almoxarifado trava Entradas, Saídas e Pedidos de compra até fechar."""

    @abc.abstractmethod
    def gravar_saldo(self, id_almox: str, id_item: str, para: float) -> None:
        """Grava o saldo ABSOLUTO da peça, com a sessão aberta. Idempotente. ValueError se a peça não está ligada."""

    @abc.abstractmethod
    def fechar_ajuste(self, id_almox: str, referencia: str) -> str:
        """Fecha a sessão com a `referencia` na `description` dos movimentos (o `finalize`) e depois volta ao modo 0
        (`voltar_ao_normal`). Devolve o `folio_return` do Fracttal como texto ('' se ele não disse). SÃO DOIS PEDIDOS: se
        o 2º falhar, o fechamento JÁ VALEU (os movimentos existem) e o almoxarifado fica em modo 2 ("fechamento feito,
        modo 0 pendente"): a recuperação é só `voltar_ao_normal`, nunca um segundo `fechar_ajuste`."""

    @abc.abstractmethod
    def voltar_ao_normal(self, id_almox: str) -> None:
        """Põe o almoxarifado no modo 0 (`warehouse_update`), liberando Entradas, Saídas e Pedidos de compra. É o 2º passo
        do `fechar_ajuste` e, sozinho, a recuperação do fechamento cujo modo 0 falhou. Só para o que o Nexus abriu: nunca
        para o modo 3 (inventário físico, de outra pessoa)."""

    @abc.abstractmethod
    def ler(self, id_almox: str) -> dict[str, dict]:
        """As peças ligadas ao almoxarifado: `{id_item: {"saldo", "minimo", "maximo", "ligacao", "codigo", "unidade"}}`.
        Saldo, mínimo e máximo são número ou None (o Fracttal não disse: nunca 0); a `unidade` é o `units_description` da
        linha (UNIDADE, METRO, MASSA), vazia quando ele não diz. A peça nunca ligada não vem."""

    @abc.abstractmethod
    def ligar(self, id_almox: str, id_item: str) -> str:
        """Liga a peça ao almoxarifado (saldo e régua em 0). Devolve a ligação."""

    @abc.abstractmethod
    def achar_movimento(self, id_almox: str, referencia: str, desde_iso: str | None = None) -> str | None:
        """O `folio` do movimento mais novo cuja `description` é exatamente a `referencia`, ou None. É como a retomada
        confirma que um fechamento cuja resposta se perdeu valeu. Com `desde_iso` (ISO UTC, o "Contada em" ou o começo da
        gravação), só olha os movimentos dessa data em diante e para na primeira linha mais velha: o "não achei" não lê o
        histórico inteiro da cota que é de todos."""

    @abc.abstractmethod
    def mexidas_desde(self, id_almox: str, desde_iso: str, ignorar_referencia: str | None = None) -> set[str] | None:
        """Os `id_item` com movimento a partir de `desde_iso` (o "Contada em", ISO UTC), sem os movimentos cuja
        `description` é a `ignorar_referencia` (o ajuste da própria contagem). None = o Fracttal não diz."""

    @abc.abstractmethod
    def definir_regua(self, id_almox: str, id_item: str, minimo: float | None, maximo: float | None) -> None:
        """Muda o mínimo e o máximo da peça no almoxarifado, só o que não é None. Fora da sessão de ajuste; não mexe em
        saldo nem gera movimento."""

    @abc.abstractmethod
    def criar_peca(self, codigo: str, nome: str, unidade: str = "UNIDADE") -> str:
        """Cria a peça (tipo 4) no catálogo do Fracttal. Devolve o id do item."""

    @abc.abstractmethod
    def codigos(self, sigla: str) -> list[str]:
        """Os códigos `SP-<sigla>-NNN` que já existem no catálogo (ativas ou não: o código é de quem o usou primeiro)."""

    @abc.abstractmethod
    def achar_peca(self, codigo: str) -> str | None:
        """O id do item do catálogo cujo código é exatamente `codigo` (sem caixa), ou None. É como a curadoria cadastra sem
        duplicar: o `criar_peca` pode ter criado a peça e perdido a resposta, e a nova tentativa procura o código que ela
        reservou antes de criar de novo."""


# ── o de verdade ───────────────────────────────────────────────────────────────────────────────────────────────────────
class EstoqueFracttal(Estoque):
    """O estoque do Fracttal pelo RPC da própria tela. `chamar(metodo, params) -> dict` é o `_rpc_call` do OS Creator já
    dentro da sessão de quem aprovou (`estoque_da_sessao`); os testes passam um gravador no lugar.

    O ritmo é o da empresa (`RITMO`, de todas as instâncias). Os testes dão o `ritmo` deles, ou o `relogio`, o `dormir` e o
    `intervalo` (que montam um `Ritmo` só desta instância), para não esperar de verdade. `pagina` é o `limit` dos pedidos.
    Uma instância serve uma gravação de cada vez: guarda as ligações lidas (peça × almoxarifado) para gravar o saldo e a
    régua sem ler o almoxarifado a cada peça (uma leitura são alguns pedidos de 1 s)."""

    def __init__(self, chamar, *, relogio=None, dormir=None, intervalo: float | None = None, pagina: int = PAGINA,
                 ritmo: Ritmo | None = None):
        if pagina < 1:
            raise ValueError("a página precisa ter ao menos 1 linha")
        if ritmo is None and (relogio is not None or dormir is not None or intervalo is not None):
            ritmo = Ritmo(relogio or time.monotonic, dormir or time.sleep, INTERVALO_S if intervalo is None else intervalo)
        self._chamar_rpc, self._ritmo, self._pagina = chamar, ritmo, pagina
        self._ligacoes: dict[str, dict[str, str]] = {}      # almoxarifado -> {id_item: ligação}
        self._unidades: dict[str, tuple[int, str]] | None = None

    # o pedido: o ritmo, a tradução dos erros e o `success`
    def _esperar(self) -> None:
        (self._ritmo if self._ritmo is not None else RITMO).esperar()      # o do módulo, buscado a cada pedido

    def _rpc(self, metodo: str, params: dict) -> dict:
        self._esperar()
        try:
            r = self._chamar_rpc(metodo, params)
        except Exception as e:                            # noqa: BLE001 — só traduz limite e login; o resto sobe igual
            traduzido = _traduzir(e)
            if traduzido is None:
                raise
            raise traduzido from e
        if not isinstance(r, dict):
            raise ErroFracttal("o Fracttal respondeu sem corpo", metodo)
        if r.get("success") is False:
            raise ErroFracttal(str(r.get("message") or "o Fracttal recusou o pedido"), metodo)
        return r

    def _linhas(self, metodo: str, base: dict):
        """As linhas de uma lista do Fracttal, página a página, na ordem dele; o `start` anda o que a página trouxe, até
        o `total`. É um gerador: quem para de olhar (achou o que queria, passou da data) não paga as páginas seguintes."""
        start = 0
        for _ in range(PAGINAS_MAX):
            r = self._rpc(metodo, {**base, "page": start // self._pagina + 1, "limit": self._pagina, "start": start})
            try:
                total = int(r.get("total"))
            except (TypeError, ValueError):
                total = None
            dados = r.get("data")
            if dados is None:
                dados = []                                    # sem linhas; se o `total` diz que há, é erro logo abaixo
            elif not isinstance(dados, list):
                raise ErroFracttal(f"o Fracttal mandou `data` que não é lista ({type(dados).__name__})", metodo)
            if not dados:
                if total is not None and start < total:
                    # Caso reproduzido na revisão: `ler` devolvia 1 peça de `total: 5`, e `data: null, total: 120` virava
                    # `{}`. Lista curta passando por inteira iria para a tela e para a conta do que "não mexeu".
                    raise ErroFracttal(f"a lista veio vazia com {start} de {total} linhas lidas", metodo)
                return
            yield from dados
            start += len(dados)
            # com o `total`, a última página é a que o fecha; sem ele, a que veio mais curta que o pedido
            acabou = start >= total if total is not None else len(dados) < self._pagina
            if acabou:
                return
        raise ErroFracttal(f"a lista não acaba em {PAGINAS_MAX} páginas", metodo)

    @staticmethod
    def _id_do_dado(r: dict, metodo: str) -> str:
        d = r.get("data")
        if not isinstance(d, dict) or d.get("id") is None:
            raise ErroFracttal("o Fracttal não devolveu o id", metodo)
        return str(d["id"])

    def _ligacao_de(self, id_almox, id_item) -> int:
        """A ligação (o `id` da linha do saldo) da peça no almoxarifado: a da última leitura ou `ligar`; sem ela, lê de
        novo uma vez (a peça pode ter sido ligada por fora). ValueError se continua sem."""
        chave, item = str(_id(id_almox)), str(id_item)
        mapa = self._ligacoes.get(chave)
        if mapa is None or item not in mapa:
            self.ler(id_almox)
            mapa = self._ligacoes.get(chave, {})
        if item not in mapa:
            raise ValueError(f"a peça {item} não está ligada ao almoxarifado {id_almox}")
        return _id(mapa[item])

    # o modo e a sessão de ajuste
    def modo(self, id_almox: str) -> int:
        alvo = _id(id_almox)
        base = {"filter": [], "sort": [], "is_tree": False, "node": None}
        for l in self._linhas(LISTA, base):
            if isinstance(l, dict) and str(l.get("id")) == str(alvo):
                modo = _numero_lido(l.get("mode"), "mode", LISTA)
                if modo is None:
                    # é a conferência da trava (o almoxarifado em ajuste ou em inventário físico não aceita movimento):
                    # vazio nunca é "0 = normal"
                    raise ErroFracttal(f"o almoxarifado {id_almox} veio sem o `mode`", LISTA)
                return int(modo)
        raise ErroFracttal(f"o almoxarifado {id_almox} não está na lista do Fracttal", LISTA)

    def abrir_ajuste(self, id_almox: str) -> None:
        """Os dois pedidos que a tela faz, nessa ordem: muda o modo e atualiza o almoxarifado."""
        alvo = _id(id_almox)
        self._rpc(MUDAR_MODO, {"id_warehouse": alvo, "mode": 2})
        self._rpc(ATUALIZAR_ALMOX, {"id": alvo, "mode": 2})

    def gravar_saldo(self, id_almox: str, id_item: str, para: float) -> None:
        n = validar_quantidade(para, "saldo")
        self._rpc(ATUALIZAR_LIGACAO, {"id": self._ligacao_de(id_almox, id_item), "stock": _no_corpo(n)})

    def fechar_ajuste(self, id_almox: str, referencia: str) -> str:
        """Fecha com a `referencia` na `description` e só então volta ao modo 0: o fechamento que o Fracttal recusa
        deixa o almoxarifado como está, e a retomada o vê aberto. Se o fechamento valeu e o modo 0 falhou, o erro sobe
        daqui e o almoxarifado fica em modo 2 com os movimentos já gerados: a recuperação é só `voltar_ao_normal`, nunca
        um segundo fechamento. Sem `folio_return` na resposta ('' no retorno), o fechamento valeu mesmo assim: quem
        confere procura o movimento pela referência."""
        alvo, ref = _id(id_almox), str(referencia or "").strip()
        if not ref:
            raise ValueError("o fechamento precisa da referência: é por ela que se confirma que valeu")
        r = self._rpc(FECHAR, {"id_warehouse": alvo, "description": ref})
        self.voltar_ao_normal(alvo)
        d = r.get("data")
        folio = d.get("folio_return") if isinstance(d, dict) else None
        return "" if folio is None else str(folio)

    def voltar_ao_normal(self, id_almox: str) -> None:
        self._rpc(ATUALIZAR_ALMOX, {"id": _id(id_almox), "mode": 0})

    # o saldo, a ligação e a régua
    def ler(self, id_almox: str) -> dict[str, dict]:
        base = {"filter": [], "sort": [], "is_tree": False, "node": None, "id_warehouse": _id(id_almox)}
        lido, ligacoes = {}, {}
        for l in self._linhas(SALDOS, base):
            if not isinstance(l, dict) or l.get("id_item") is None or l.get("id") is None:
                raise ErroFracttal("linha de saldo sem a peça ou sem a ligação", SALDOS)
            item = str(l["id_item"])
            lido[item] = {"saldo": _numero_lido(l.get("stock"), "stock", SALDOS),
                          "minimo": _numero_lido(l.get("min_stock_level"), "min_stock_level", SALDOS),
                          "maximo": _numero_lido(l.get("max_stock_level"), "max_stock_level", SALDOS),
                          "ligacao": str(l["id"]), "codigo": str(l.get("code") or ""),
                          # a régua (Task 8) arredonda por ela: METRO e MASSA aceitam duas casas, UNIDADE é inteira
                          "unidade": str(l.get("units_description") or "").strip()}
            ligacoes[item] = str(l["id"])
        self._ligacoes[str(_id(id_almox))] = ligacoes
        return lido

    def ligar(self, id_almox: str, id_item: str) -> str:
        r = self._rpc(LIGAR, {"id_warehouse": _id(id_almox), "id_item": _id(id_item), "location": "", "stock": 0,
                              "min_stock_level": 0, "max_stock_level": 0, "reorder_level": 0})
        ligacao = self._id_do_dado(r, LIGAR)
        self._ligacoes.setdefault(str(_id(id_almox)), {})[str(id_item)] = ligacao
        return ligacao

    def definir_regua(self, id_almox: str, id_item: str, minimo: float | None, maximo: float | None) -> None:
        mn, mx = validar_nivel(minimo, "mínimo"), validar_nivel(maximo, "máximo")
        if mn is not None and mx is not None and mn > mx:
            raise ValueError(f"o mínimo ({minimo}) não pode passar do máximo ({maximo})")
        corpo = {}
        if mn is not None:
            corpo["min_stock_level"] = _nivel_no_corpo(mn)
        if mx is not None:
            corpo["max_stock_level"] = _nivel_no_corpo(mx)
        if not corpo:
            return                                        # nada a mudar: nem pedido
        self._rpc(ATUALIZAR_LIGACAO, {"id": self._ligacao_de(id_almox, id_item), **corpo})

    # o histórico de movimentos
    def _historico(self, id_almox: str, desde: datetime | None = None):
        """Os movimentos do almoxarifado do mais novo ao mais velho, só com o que o adaptador usa. O resto da linha (e com
        ele o `responsible_description`, o nome de quem movimentou) sai aqui e não vai a lugar nenhum. Com `desde`, para na
        primeira linha mais velha (a lista é ordenada por `date_create`: o resto é mais velho ainda e a cota é de todos);
        a linha de data ilegível não para nada e segue como mexida."""
        base = {"sort": [{"property": "date_create", "direction": "desc"}], "is_tree": False, "node": None,
                "id_warehouse": _id(id_almox)}
        for l in self._linhas(HISTORICO, base):
            if not isinstance(l, dict):
                continue
            if desde is not None:
                try:
                    if instante(l.get("date_create")) < desde:
                        return
                except ValueError:
                    pass
            yield {"folio": str(l.get("folio") or l.get("id_movements") or ""), "id_item": str(l.get("id_item") or ""),
                   "quando": l.get("date_create"), "referencia": str(l.get("description") or "").strip()}

    def achar_movimento(self, id_almox: str, referencia: str, desde_iso: str | None = None) -> str | None:
        alvo = str(referencia or "").strip()
        if not alvo:
            raise ValueError("sem a referência, qualquer movimento sem descrição seria o achado")
        desde = instante(desde_iso) if desde_iso else None
        for m in self._historico(id_almox, desde):
            if m["referencia"] == alvo:
                return m["folio"]
        return None

    def mexidas_desde(self, id_almox: str, desde_iso: str, ignorar_referencia: str | None = None) -> set[str] | None:
        """O histórico vem do mais novo ao mais velho (ordenado por `date_create`): lê até passar da data e para. A
        linha com data ilegível conta como mexida (na dúvida, vira conflito para o PCM olhar, e não ajuste por cima)."""
        corte = instante(desde_iso)
        ignorar = str(ignorar_referencia).strip() if ignorar_referencia else None
        mexidas = set()
        for m in self._historico(id_almox, corte):
            if ignorar and m["referencia"] == ignorar:
                continue
            if m["id_item"]:
                mexidas.add(m["id_item"])
        return mexidas

    # o catálogo de peças
    def _unidade(self, nome: str) -> tuple[int, str]:
        """O `id_unit` e o nome da unidade, de `companies.units_list` (lida uma vez por instância). Casa sem acento e sem
        caixa pela descrição ou pelo código da unidade."""
        if self._unidades is None:
            unidades = {}
            for u in self._linhas(UNIDADES, {"filter": [], "sort": [], "is_tree": False, "node": None}):
                if isinstance(u, dict) and u.get("id") is not None:
                    descricao = str(u.get("description") or u.get("name") or u.get("code") or "")
                    for campo in ("description", "name", "code"):
                        if u.get(campo):
                            unidades.setdefault(_norm(u[campo]), (_id(u["id"]), descricao))
            self._unidades = unidades
        achada = self._unidades.get(_norm(nome))
        if achada is None:
            raise ErroFracttal(f"a unidade {nome!r} não existe no Fracttal", UNIDADES)
        return achada

    def criar_peca(self, codigo: str, nome: str, unidade: str = "UNIDADE") -> str:
        codigo, nome = str(codigo or "").strip(), str(nome or "").strip()
        if not codigo or not nome:
            raise ValueError("a peça precisa de código e de nome")
        id_unit, descricao_da_unidade = self._unidade(unidade)
        r = self._rpc(CRIAR, {
            "id_type_item": TIPO_PECA, "field_1": nome, "code": codigo, "id_unit": id_unit,
            "units_description": descricao_da_unidade, "active": True, "description": "", "is_serial_control": False,
            "is_lot_control": False, "visible_to_all": False, "ids_batch": [], "associate_warehouses": [],
            "associate_third_parties": [], "attached": [], "files": [], "custom_fields": []})
        return self._id_do_dado(r, CRIAR)

    def codigos(self, sigla: str) -> list[str]:
        sigla = str(sigla or "").strip()
        if not sigla:
            raise ValueError("a sigla da usina não pode ser vazia")
        prefixo = f"SP-{sigla}-".upper()
        base = {"filter": [], "sort": [], "is_tree": False, "node": 0, "id_type_item": TIPO_PECA}
        return [str(l["code"]) for l in self._linhas(PECAS, base)
                if isinstance(l, dict) and l.get("code") and str(l["code"]).upper().startswith(prefixo)]

    def achar_peca(self, codigo: str) -> str | None:
        """Pede a lista de peças com o filtro do código (`code =`, o mesmo `filter` que o `api.py` do OS Creator usa nas
        listas do Fracttal) e CONFERE a linha que volta: o filtro que o Fracttal ignorasse devolveria o catálogo inteiro (o
        `api.py` anota esse caso com o `id_parent_wo`), e o código parecido (SP-CAB-0130) não é o procurado. Para na primeira
        página que acha: a cota é de todos. O filtro `code =` ainda não foi provado contra o Fracttal de verdade (o passo 0 só
        listou); a conferência da linha vale de qualquer jeito, e a prova com o App (Task 10) confirma."""
        alvo = str(codigo or "").strip()
        if not alvo:
            raise ValueError("sem o código, qualquer peça seria a achada")
        base = {"filter": [{"operator": "=", "property": "code", "value": alvo}], "sort": [], "is_tree": False, "node": 0,
                "id_type_item": TIPO_PECA}
        for l in self._linhas(PECAS, base):
            if isinstance(l, dict) and l.get("id") is not None and str(l.get("code") or "").strip().upper() == alvo.upper():
                return str(l["id"])
        return None


# ── a sessão do pedido ─────────────────────────────────────────────────────────────────────────────────────────────────
class _SessaoDoClone:
    """O `_rpc_call` do OS Creator dentro da sessão de UMA pessoa. Guarda o JWT e o e-mail só aqui, na memória. O `api.py`
    do OS Creator lê o JWT do contexto da requisição (`os_web.sessao.contexto`): cada pedido entra no contexto e sai dele,
    e o token que o `api` renovar no meio (ele renova quando falta menos de 1 minuto) só existe dentro daquele pedido;
    sem guardá-lo aqui, cada pedido seguinte renovaria de novo, e o desktop o escreveria em arquivo (isto aqui nunca)."""

    def __init__(self, os_api, os_sessao, jwt: str, email: str):
        self._api, self._sessao, self._jwt, self._email = os_api, os_sessao, jwt, email

    def chamar(self, metodo: str, params: dict):
        # `_rpc_chamar` e não `_rpc_call`: o `_rpc_call` classifica pelo NOME do método (leitura é "_list", "get",
        # "details" ou "load_"; o resto é gravação de OS) e, a cada "gravação", limpa a memória das leituras de OS do
        # processo inteiro. `warehouses_items_stock` e toda gravação de estoque caem nesse "resto": cada pedido do
        # adaptador esvaziaria o cache de card do OS Creator de todo mundo (o card voltaria a ler o Fracttal). Nenhum
        # pedido daqui toca numa OS, e é o mesmo POST e os mesmos erros, sem essa limpeza. O `api.py` não se edita (o
        # clone fica idêntico ao do oem). Buscado a cada pedido: o teste troca o que quiser.
        with self._sessao.contexto(self._jwt, self._email):
            try:
                return self._api._rpc_chamar(metodo, params, TIMEOUT_S)
            finally:
                novo = self._sessao.jwt_novo()
                if novo:
                    self._jwt = novo

    def __repr__(self) -> str:
        return "<sessão do Fracttal (o login fica só na memória)>"


def _estoque_do_clone(app, jwt: str, email: str, **ritmo) -> EstoqueFracttal:
    """A `EstoqueFracttal` com o login dado, pelo `api` do clone do OS Creator. `ritmo`: o relógio, o `dormir`, o
    intervalo e a página (os testes trocam; a produção usa os padrões)."""
    from ...torres.oscreator import ponte
    ponte.clone(app)                                 # põe o `api` do clone no sys.path e costura a sessão dele
    import api as os_api                             # noqa: E402 — o `api` do clone do OS Creator
    from os_web import sessao as os_sessao           # noqa: E402
    return EstoqueFracttal(_SessaoDoClone(os_api, os_sessao, jwt, email).chamar, **ritmo)


def estoque_da_sessao(app) -> EstoqueFracttal:
    """O estoque com o login do Fracttal de quem está no pedido (a sessão do OS Creator, o cookie `os_sessao` que o login do
    Nexus pelo Fracttal abre). SemLogin se não há: quem entra pela senha de administrador não tem login no Fracttal, e a
    gravação precisa dele. Chamar DENTRO do pedido; a instância pode seguir numa thread depois."""
    from ...torres.oscreator import ponte
    s = ponte.sessao_do_os(app)
    jwt = str(s.get("jwt") or "")
    if not jwt:
        raise SemLogin("sem o login do Fracttal nesta sessão (quem entra pela senha de administrador não tem)")
    return _estoque_do_clone(app, jwt, str((s.get("conta") or {}).get("email") or ""))
