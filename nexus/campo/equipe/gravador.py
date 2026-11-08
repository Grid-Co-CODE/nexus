"""Mapa de equipe: o gravador em lote (08/11/2026). A cada 5 min leva ao banco o que as rotas juntaram na memória e no
diário: os pontos do dia, os deslocamentos do mês, os eventos de aparelho e os acessos ao mapa.

O banco só SUBSTITUI o livro inteiro (`livros.publicar`): não há "acrescentar". Por isso cada livro é relido e regravado
inteiro, sempre pela UNIÃO com o que o banco já tem (nada some por uma rodada que viu menos que o banco):
- pontos: o livro do dia é a união do diário com o que o banco tem (só CAB_PONTOS: a coordenada fica cifrada na coluna
  `cifra`), publicada sempre que o diário tem um ponto que o banco não tem. O diário MENOR que o banco (máquina nova,
  disco apagado no meio do dia) também publica: a união nunca encolhe o dia, e o livro é `so_cresce` no catálogo (a
  trava do `livros.publicar` recusa a gravação que encolheria). Antes (até a revisão final de 08/11/2026) uma trava à mão
  pela contagem barrava essa gravação, e os pontos novos do dia nunca chegavam ao banco. Dia vazio nunca vai por cima.
- deslocamentos: recalculados dos pontos de até 7 dias, cortados pelo INSTANTE (o arquivo do dia mais velho ainda tem
  ponto de mais de 7 dias, e o ponto bruto nunca é usado depois disso), e unidos ao livro do mês que o banco tem. O id é
  estável: republicar o mês não duplica.
- aparelhos e acessos: as linhas novas da fila (o jornal em disco, `jornal.py`) entram no livro relido, sob trava; se a
  gravação falha, as linhas VOLTAM à fila para a próxima rodada; se dá certo, o jornal é aparado.
Cada passo é isolado (regra 13 de nexus/dados/CLAUDE.md): o erro de um vai ao log (só o TIPO) e os outros seguem. Nada de
coordenada nem de chave no log.

Só roda onde `NEXUS_EQUIPE_GRAVA=1` (uma máquina por vez: o PC e o servidor não gravam juntos); nunca em teste. As rotas
do celular respondem 503 na máquina em que ele não roda (quem recebe tem de ser quem grava).
"""
import hashlib
import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone

from nexus.campo.equipe import (ABA_ACESSOS, ABA_APARELHOS, ABA_DESLOC, ABA_PONTOS, CAB_ACESSOS, CAB_APARELHOS,
                                CAB_DESLOC, CAB_PONTOS, GUARDA_PONTOS_DIAS, LIVRO_ACESSOS, LIVRO_APARELHOS,
                                livro_deslocamentos, livro_pontos)
from nexus.campo.equipe import pontos as PT
from nexus.campo.equipe.deslocamentos import deslocamentos

log = logging.getLogger(__name__)

A_CADA_S = 300
_BRT = timezone(timedelta(hours=-3))


def _linha(r: dict, cab) -> list:
    return [r.get(c) for c in cab]


def _assinatura(ids) -> str:
    return hashlib.sha1("|".join(sorted(str(i) for i in ids)).encode("utf-8")).hexdigest()


def ativo(config) -> bool:
    return str(config.get("NEXUS_EQUIPE_GRAVA") or "").strip() == "1"


class Gravador:
    def __init__(self, app, servico, usinas=None):
        self._app = app
        self._srv = servico
        self._usinas_fn = usinas
        self._trava = threading.Lock()                  # uma rodada por vez
        self._pontos_gravados: dict[int, str] = {}      # data_id -> assinatura do conjunto da última gravação boa
        self._desloc_gravados: dict[int, str] = {}      # AAAAMM -> idem

    # ── o banco ──────────────────────────────────────────────────────────────────────────────────────────────────
    def _ler(self, livro: str, aba: str) -> list[dict]:
        """A aba do livro; livro que não existe = vazio. Listagem incompleta do banco SOBE (não é livro vazio): gravar
        por cima dela apagaria o histórico."""
        from nexus.campo import visao
        from nexus.dados import livros
        base, sessao = visao._base(), visao._sessao()
        a = livros.abas_conferidas(base, sessao, livro, ())
        return livros._linhas(base, sessao, a[aba]) if aba in a else []

    def _publicar(self, livro: str, nome: str, aba: str, cab, linhas: list[list]) -> None:
        from nexus.campo import visao
        from nexus.dados import livros
        livros.publicar(livro, nome, {aba: (list(cab), linhas)}, base=visao._base(),
                        token=self._app.config["GRIDCO_SQL_TOKEN"], sessao=visao._sessao())

    def _coordenadas_das_usinas(self) -> dict:
        if self._usinas_fn is not None:
            return self._usinas_fn()
        from nexus.campo.mapa_responsaveis import coordenadas
        return coordenadas()[0]

    # ── a rodada ─────────────────────────────────────────────────────────────────────────────────────────────────
    def rodada(self, agora: datetime) -> None:
        with self._trava, self._app.app_context():
            hoje = agora.astimezone(_BRT).date()
            passos = (("pontos", lambda: self._pontos(hoje)),
                      ("deslocamentos", lambda: self._deslocamentos(agora)),
                      ("aparelhos", self._aparelhos),
                      ("acessos", self._acessos),
                      ("diário velho", lambda: self._srv.diario.apagar_velhos(hoje)))
            for nome, passo in passos:
                try:
                    passo()
                except Exception as e:      # noqa: BLE001 — um passo que cai não derruba os outros
                    log.warning("equipe: o gravador falhou em %s (%s)", nome, type(e).__name__)

    def _pontos(self, hoje: date) -> None:
        for dia in (hoje, hoje - timedelta(days=1)):
            pts = self._srv.diario.do_dia(dia)
            if not pts:
                continue                                    # dia vazio nunca vai por cima de dia com linhas
            data_id = int(dia.strftime("%Y%m%d"))
            sig = _assinatura(p["ponto_id"] for p in pts)
            if self._pontos_gravados.get(data_id) == sig:
                continue
            livro = livro_pontos(dia)
            no_banco = self._ler(livro, ABA_PONTOS)
            ids_banco = {str(r.get("ponto_id")) for r in no_banco}
            if all(p["ponto_id"] in ids_banco for p in pts):
                self._pontos_gravados[data_id] = sig        # o banco já tem o diário inteiro: nada a gravar
                continue
            # a união, sempre (o diário menor que o banco também): a versão do diário de cada ponto que ele tem (com o
            # tipo certo de cada coluna) e as linhas que só o banco tinha, como vieram
            ids = {p["ponto_id"] for p in pts}
            linhas = [PT.linha_do_banco(p) for p in pts]
            linhas += [_linha(r, CAB_PONTOS) for r in no_banco if str(r.get("ponto_id")) not in ids]
            linhas.sort(key=lambda l: (str(l[2]), str(l[0])))       # pela hora do ponto
            self._publicar(livro, f"Mapa de equipe · pontos {dia:%d/%m/%Y}", ABA_PONTOS, CAB_PONTOS, linhas)
            self._pontos_gravados[data_id] = sig

    def _deslocamentos(self, agora: datetime) -> None:
        usinas = self._coordenadas_das_usinas()
        if not usinas:
            return                                          # sem coordenada de usina não há como dizer onde estava
        hoje = agora.astimezone(_BRT).date()
        # o ponto bruto nunca é usado depois de 7 dias: o corte é pelo instante, porque o arquivo do dia mais velho
        # ainda tem pontos de mais de 7 dias (o anti-objetivo do desenho; revisão final de 08/11/2026)
        corte = (agora - timedelta(days=GUARDA_PONTOS_DIAS)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        pontos = []
        for k in range(GUARDA_PONTOS_DIAS + 1):
            pontos += [p for p in self._srv.diario.do_dia(hoje - timedelta(days=k)) if p["instante"] >= corte]
        por_mes: dict[int, list[list]] = {}
        for l in deslocamentos(pontos, usinas):
            por_mes.setdefault(l[1] // 100, []).append(l)       # data_id da chegada -> AAAAMM
        for mes, novas in sorted(por_mes.items()):
            sig = _assinatura(l[0] for l in novas)
            if self._desloc_gravados.get(mes) == sig:
                continue
            dia = date(mes // 100, mes % 100, 1)
            livro = livro_deslocamentos(dia)
            no_banco = self._ler(livro, ABA_DESLOC)
            ids_novas = {l[0] for l in novas}
            if ids_novas <= {str(r.get("deslocamento_id")) for r in no_banco}:
                self._desloc_gravados[mes] = sig
                continue
            uniao = novas + [_linha(r, CAB_DESLOC) for r in no_banco if str(r.get("deslocamento_id")) not in ids_novas]
            uniao.sort(key=lambda l: (str(l[5]), str(l[0])))
            self._publicar(livro, f"Mapa de equipe · deslocamentos {dia:%m/%Y}", ABA_DESLOC, CAB_DESLOC, uniao)
            self._desloc_gravados[mes] = sig

    def _aparelhos(self) -> None:
        ch = self._srv.chaveiro
        self._acrescentar(LIVRO_APARELHOS, "Mapa de equipe · aparelhos", ABA_APARELHOS, CAB_APARELHOS,
                          ch.eventos_novos, ch.devolver, ch.confirmar)

    def _acessos(self) -> None:
        r = self._srv.registro
        self._acrescentar(LIVRO_ACESSOS, "Mapa de equipe · acessos", ABA_ACESSOS, CAB_ACESSOS, r.novos, r.devolver,
                          r.confirmar)

    def _acrescentar(self, livro, nome, aba, cab, retirar, devolver, confirmar) -> None:
        """Acrescenta por regravação: relê, junta as linhas novas (id que o banco já tem não entra de novo) e publica.
        A primeira coluna é o id. Falhou em qualquer ponto = as linhas voltam à fila (e ficam no jornal). Deu certo =
        o jornal é aparado. A linha que o banco já tem (o reinício entre a publicação e o aparo a traz de volta) não
        regrava nada: só sai do jornal."""
        novas = retirar()
        if not novas:
            return
        try:
            no_banco = self._ler(livro, aba)
            tem = {str(r.get(cab[0])) for r in no_banco}
            faltam = [l for l in novas if str(l[0]) not in tem]
            if faltam:
                self._publicar(livro, nome, aba, cab, [_linha(r, cab) for r in no_banco] + faltam)
        except Exception:
            devolver(novas)
            raise
        confirmar(novas)


def _laco(app) -> None:
    from nexus.campo.equipe import servico
    g = None
    while True:
        try:
            if g is None:
                g = Gravador(app, servico.do_app(app))
            g.rodada(datetime.now(timezone.utc))
        except Exception as e:      # noqa: BLE001 — sem a chave do cadastro, por exemplo: tenta de novo na próxima
            log.warning("equipe: a rodada do gravador não rodou (%s)", type(e).__name__)
        time.sleep(A_CADA_S)


def ligar(app) -> None:
    """Liga o laço em fundo, só onde NEXUS_EQUIPE_GRAVA=1 e nunca em teste."""
    if app.config.get("TESTING") or not ativo(app.config):
        return
    threading.Thread(target=_laco, args=(app,), daemon=True, name="nexus-equipe-gravador").start()
