"""Mapa de equipe: o estado do processo por trás das três rotas do contrato com o Nexus Field (08/11/2026; as rotas em
`nexus/torres/campo/equipe_tela.py`).

Um `Servico` por app (`do_app`, em `app.extensions["nexus_equipe"]`), criado no primeiro pedido que precisa dele:
- as chaves dos aparelhos (`Chaveiro`), relidas do livro `nexus_equipe_aparelhos` ao nascer;
- os pontos do dia (`Diario`), relidos do disco ao nascer, para o mapa voltar com as últimas posições depois de um
  reinício, antes de o lote chegar ao banco;
- o último ponto e a permissão de localização de cada pessoa (`estado_de`, para a tela do mapa);
- quem é coletado: o piloto (`nexus_equipe_piloto`, cópia de 1 min) e os técnicos de campo ativos do cadastro (cópia de
  5 min), sem ir ao banco a cada lote, que chega de cada celular a cada 2 min.

Nada daqui grava no banco: as chaves novas e as revogadas esperam em `chaveiro.eventos_novos()` e os pontos no diário,
para a gravação em lote. O que vai ao log é o TIPO do erro: nunca token, chave nem coordenada.

**O banco fora não é chave inválida** (a mesma regra da Microsoft fora no `token_ms`): sem ter lido o livro das chaves,
o Nexus não sabe se uma chave vale, e o 401 faria a casca apagar a dela e parar até a próxima abertura do App. Até ler,
as rotas respondem 503 (a casca guarda a fila e a chave e tenta de novo); a leitura que falhou só se repete depois de
1 min. A listagem do banco que omite o livro por um instante (achado 6 da revisão de 05/11/2026) é falha, não livro
vazio: o `abas_conferidas` confere a conta de abas do livro.

**Quem é coletado quando o banco não responde:** a cópia boa segue valendo (como no `setor_telas.ler`: a leitura que
falha devolve a última boa), e sem nenhuma leitura boa ninguém é coletado (`coleta: false`, nunca 500). O cadastro que
volta sem nenhum técnico de campo é a leitura que falhou (a mesma listagem que omite o livro), não a equipe que sumiu.
"""
import logging
import threading
from datetime import datetime, timedelta, timezone

from nexus.campo.equipe import (ABA_APARELHOS, ABA_PILOTO, GUARDA_PONTOS_DIAS, LIVRO_APARELHOS, LIVRO_PILOTO)
from nexus.campo.equipe import aparelhos as AP
from nexus.campo.equipe import pontos as PT
from nexus.campo.equipe import token_ms as T

log = logging.getLogger(__name__)

CHAVE_EXT = "nexus_equipe"
PILOTO_S = 60                    # a decisão do piloto vale em até 1 min
TECNICOS_S = 5 * 60              # quem é técnico de campo ativo no cadastro
TETO_FALHA_S = 60                # o banco ou a Microsoft que falhou: a próxima ida só depois disto

_TRAVA_APP = threading.Lock()


class SemConfiguracao(RuntimeError):
    """O servidor sem a chave do cadastro: a posição não tem como ser cifrada, e nada é recebido."""


class AindaLendo(RuntimeError):
    """A 1ª leitura do banco está em curso noutro pedido: a rota responde 503 e o aparelho tenta de novo."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _ha_menos_de(segundos: float, agora: float, quando: float | None) -> bool:
    # o relógio que voltou (quando no futuro) conta como vencido, como no token_ms
    return quando is not None and 0 <= agora - quando < segundos


def _instante(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Copia:
    """Uma leitura do banco guardada por `validade_s`, uma ida por vez. Quem chega com a ida em curso fica com a cópia
    que há (e, sem nenhuma, `AindaLendo`), em vez de esperar: com o banco lento, os pedidos parados juntos ocupariam as
    threads do Nexus inteiro (o caso de 19/10/2026 em `visao._EM_CALCULO`). A leitura que falha fica com a cópia boa (ou
    None, sem nenhuma) e só se repete depois de `TETO_FALHA_S`."""

    def __init__(self, nome: str, validade_s: float, ler):
        self._nome, self._validade, self._ler = nome, validade_s, ler
        self._trava = threading.Lock()
        self._valor = None
        self._lida_em: float | None = None
        self._falhou_em: float | None = None
        self._lendo = False

    def valor(self, agora_s: float):
        with self._trava:
            if self._valor is not None and _ha_menos_de(self._validade, agora_s, self._lida_em):
                return self._valor
            if self._lendo:
                if self._valor is None:
                    raise AindaLendo(self._nome)
                return self._valor
            if _ha_menos_de(TETO_FALHA_S, agora_s, self._falhou_em):
                return self._valor
            self._lendo = True
        novo = None
        try:
            novo = self._ler()
        except Exception as e:      # noqa: BLE001 — banco fora, listagem incompleta: fica a cópia boa
            log.warning("equipe: não consegui ler %s (%s); %s", self._nome, type(e).__name__,
                        "fica a leitura anterior" if self._valor is not None else "ninguém é coletado até ler")
        finally:
            with self._trava:
                self._lendo = False
                if novo is not None:
                    self._valor, self._lida_em, self._falhou_em = novo, agora_s, None
                else:
                    self._falhou_em = agora_s
                atual = self._valor
        return atual


class Servico:
    """O estado do Mapa de equipe neste processo. As rotas (e a tela do mapa) usam só os métodos daqui."""

    def __init__(self, app, pasta, cofre, agora: datetime | None = None):
        agora = agora or _agora()
        self._app = app
        self.cofre = cofre
        self.chaveiro = AP.Chaveiro()
        self.diario = PT.Diario(pasta, cofre)
        self._trava = threading.Lock()
        self._ultimo: dict[int, dict] = self.diario.ultimos(agora)
        self._estado: dict[int, dict] = {}            # pessoa_id -> {"permissao", "desde"}
        self._chaves_lidas = False
        self._chaves_lendo = False
        self._chaves_falhou_em: float | None = None
        self._ms_falhou_em: float | None = None
        self._piloto = _Copia("o piloto (nexus_equipe_piloto)", PILOTO_S, self._ler_piloto)
        self._tecnicos = _Copia("os técnicos de campo do cadastro", TECNICOS_S, self._ler_tecnicos)

    # ── o banco ──────────────────────────────────────────────────────────────────────────────────────────────────
    def _ler_livro(self, livro: str, aba: str) -> list[dict]:
        from nexus.campo import visao
        from nexus.dados import livros
        with self._app.app_context():
            base, sessao = visao._base(), visao._sessao()
            a = livros.abas_conferidas(base, sessao, livro, ())
            return livros._linhas(base, sessao, a[aba]) if aba in a else []

    def _ler_piloto(self) -> frozenset:
        return frozenset(AP.piloto_atual(self._ler_livro(LIVRO_PILOTO, ABA_PILOTO)))

    def _ler_tecnicos(self) -> frozenset:
        from nexus.campo import visao
        from nexus.pcm.tecnicos_usina import pessoas_de_campo
        with self._app.app_context():
            ids = frozenset(pessoas_de_campo(visao._Base(), self._app.config))
        if not ids:
            raise RuntimeError("o cadastro veio sem nenhum técnico de campo")
        return ids

    def chaves_prontas(self, agora: datetime | None = None) -> bool:
        """O livro das chaves já foi lido (ou acabou de ser). Até lá, nenhuma chave vale nem é emitida: as rotas
        respondem 503. A ida ao banco que falhou só se repete depois de `TETO_FALHA_S`, e uma por vez."""
        ts = (agora or _agora()).timestamp()
        with self._trava:
            if self._chaves_lidas:
                return True
            if self._chaves_lendo or _ha_menos_de(TETO_FALHA_S, ts, self._chaves_falhou_em):
                return False
            self._chaves_lendo = True
        ok = False
        try:
            self.chaveiro.carregar(self._ler_livro(LIVRO_APARELHOS, ABA_APARELHOS))
            ok = True
        except Exception as e:          # noqa: BLE001
            log.warning("equipe: não consegui ler as chaves dos aparelhos (%s); 503 até ler", type(e).__name__)
        finally:
            with self._trava:
                self._chaves_lendo = False
                self._chaves_lidas = self._chaves_lidas or ok
                if not ok:
                    self._chaves_falhou_em = ts
        return ok

    # ── quem é ───────────────────────────────────────────────────────────────────────────────────────────────────
    def conferir_token(self, token: str, *, cliente, diretorio, dominios, agora: datetime) -> str:
        """O e-mail do ID token (`token_ms.conferir`), com um teto: sem a cópia das chaves e com a Microsoft fora, cada
        registro esperaria os 10 s dela; a falha de há menos de 1 min responde `MicrosoftForaDoAr` sem ir a ela."""
        ts = agora.timestamp()
        with self._trava:
            if _ha_menos_de(TETO_FALHA_S, ts, self._ms_falhou_em):
                raise T.MicrosoftForaDoAr("a Microsoft não respondeu há menos de 1 min")
        try:
            return T.conferir(token, cliente=cliente, diretorio=diretorio, dominios=dominios, agora=ts)
        except T.MicrosoftForaDoAr:
            with self._trava:
                self._ms_falhou_em = ts
            raise

    def pessoa_do_email(self, email: str) -> int | None:
        """O `pessoa_id` do e-mail pelo cadastro (`pessoa_do_login`: a ficha com o e-mail ou, sem ela, o nome de UMA
        pessoa). Cadastro que não se lê = None: a rota responde coleta false."""
        from nexus.campo import visao
        try:
            with self._app.app_context():
                return visao._Base().pessoa_do_login(email, "")
        except Exception as e:          # noqa: BLE001
            log.warning("equipe: não consegui ler o cadastro para achar a pessoa (%s)", type(e).__name__)
            return None

    def coleta_vale(self, pessoa_id, agora: datetime) -> bool:
        """Técnico de campo ativo E no piloto. O piloto vem antes: quem está fora dele nem custa a leitura do cadastro.
        `AindaLendo` sobe (a 1ª leitura em curso noutro pedido)."""
        ts = agora.timestamp()
        piloto = self._piloto.valor(ts)
        if not piloto or pessoa_id not in piloto:
            return False
        tecnicos = self._tecnicos.valor(ts)
        return bool(tecnicos) and AP.coleta_vale(pessoa_id, tecnicos, piloto)

    def quem(self, chave, aparelho) -> int | None:
        """O `pessoa_id` da chave ativa, se ela é deste aparelho; None para chave desconhecida, revogada ou de outro."""
        par = self.chaveiro.quem(chave)
        if par is None or par[1] != aparelho:
            return None
        return par[0]

    # ── o que muda ───────────────────────────────────────────────────────────────────────────────────────────────
    def registrar(self, pessoa_id: int, aparelho: str, app: str, agora: datetime) -> str:
        """A chave nova do par pessoa + aparelho (a velha cai). Só depois de lido o livro: emitir antes deixaria a chave
        velha do mesmo par, que só o livro conhece, valendo junto com a nova."""
        if not self._chaves_lidas:
            raise AindaLendo("as chaves dos aparelhos")
        return self.chaveiro.emitir(pessoa_id, aparelho, app, agora)

    def revogar(self, chave, aparelho, agora: datetime) -> bool:
        if not self._chaves_lidas or self.quem(chave, aparelho) is None:
            return False
        return self.chaveiro.revogar(chave, agora)

    def receber(self, pessoa_id: int, lote: dict, agora: datetime) -> int:
        """Os pontos válidos do lote vão ao diário (cifrados) e o estado da pessoa anda. Devolve quantos valeram (o
        reenvio do mesmo ponto conta, e o diário não duplica). Disco cheio sobe `OSError`: nada muda e a rota responde
        503, para a casca mandar de novo."""
        pontos = PT.aceitar(pessoa_id, lote, agora, self.cofre)
        if pontos:
            self.diario.acrescentar(pontos)
        permissao = "sem" if lote.get("permissao") == "sem" else "ok"
        with self._trava:
            if pontos:
                novo = max(pontos, key=lambda p: p["instante"])
                atual = self._ultimo.get(pessoa_id)
                if atual is None or novo["instante"] > atual["instante"]:
                    self._ultimo[pessoa_id] = novo
            e = self._estado.get(pessoa_id)
            if e is None or e["permissao"] != permissao:
                self._estado[pessoa_id] = {"permissao": permissao, "desde": agora}
        return len(pontos)

    # ── para a tela do mapa ──────────────────────────────────────────────────────────────────────────────────────
    def estado_de(self, pessoa_id, agora_utc: datetime | None = None) -> dict:
        """{"ultimo": o último ponto (com lat/lon, só em memória) ou None, "permissao": "ok" | "sem", "desde": quando a
        permissão atual começou a ser dita, ou None}. O ponto com mais de 7 dias não é usado. A permissão vive só na
        memória: depois de um reinício volta "ok" até a casca repetir o "sem" (ela repete a cada 30 min)."""
        agora = agora_utc or _agora()
        corte = _instante(agora - timedelta(days=GUARDA_PONTOS_DIAS))
        with self._trava:
            u = self._ultimo.get(pessoa_id)
            e = dict(self._estado.get(pessoa_id) or {})
        return {"ultimo": dict(u) if u and u["instante"] >= corte else None,
                "permissao": e.get("permissao", "ok"), "desde": e.get("desde")}


def do_app(app) -> Servico:
    """O serviço deste app, criado uma vez (o diário relido do disco) e, logo depois, fora da trava, a 1ª leitura das
    chaves (quem chega enquanto ela roda recebe 503, sem ficar parado). Sem a chave do cadastro: `SemConfiguracao`."""
    srv = app.extensions.get(CHAVE_EXT)
    if srv is not None:
        return srv
    with _TRAVA_APP:
        srv = app.extensions.get(CHAVE_EXT)
        nasceu = srv is None
        if nasceu:
            from nexus.cadastro.cifra import Cofre
            from nexus.cadastro.ligacoes import pasta_dados
            chave = str(app.config.get("NEXUS_CHAVE_CADASTRO") or "").strip()
            if not chave:
                raise SemConfiguracao("NEXUS_CHAVE_CADASTRO")
            srv = Servico(app, pasta_dados(app.config), Cofre(chave))
            app.extensions[CHAVE_EXT] = srv
    if nasceu:
        srv.chaves_prontas()
    return srv
