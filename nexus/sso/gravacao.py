"""A gravação do SSO pelo Nexus: o gravador da Zeladoria (`nexus/zeladoria/gravacao.Gravador`) com o mapa do SSO.

Na hora, a mudança entra no estado do servidor e num diário cifrado na pasta de dados (`<NEXUS_DADOS>/sso/diario.jsonl`);
em lote (2 s sem mudança ou 20 s seguidos), o Nexus grava os livros `nexus_sso_*` que mudaram, conferindo antes e
depois (`livros.publicar`), e só então esvazia o diário. Ao subir, o diário se reaplica por cima do banco, livro a livro.

**Uma máquina grava:** a mesma da Zeladoria (o interruptor da página da troca, `/t/zeladoria/troca`, ligado no servidor
desde 12/11/2026), porque é ela a casa dos dados da zeladoria. `NEXUS_SSO_GRAVA` (1 ou 0) vence onde existir. Onde não
grava, a API do SSO responde que este Nexus não guarda o SSO, e o site mostra o erro sem perder o que foi digitado.

As regras do `_efeitos` são as do Postgres do Supabase (`esquema.py`: padrões, obrigatórias, listas fechadas, chave
repetida). Quem pode o quê fica antes, na API (`regras.py`): aqui chega o pedido já conferido.
"""
from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from ..zeladoria import gravacao as Z
from . import esquema as E
from . import tabelas as T

log = logging.getLogger(__name__)

Recusa = Z.Recusa
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def forcada(config) -> str:
    v = str(config.get("NEXUS_SSO_GRAVA") or os.environ.get("NEXUS_SSO_GRAVA") or "").strip()
    return v if v in ("0", "1") else ""


def ativo(config) -> bool:
    """O SSO grava nesta máquina? A variável decide onde existir; senão, onde a Zeladoria grava."""
    v = forcada(config)
    if v:
        return v == "1"
    return Z.ativo(config)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _txt(v) -> str:
    return Z._txt(v)


class GravadorSSO(Z.Gravador):
    TABELAS = T.TABELAS
    CTX_DIARIO = "sso/diario"
    PREFIXO = "sso"
    CIFRADA = staticmethod(T.coluna_cifrada)
    regravacao = None           # o último "Regravar cifrado" pedido: {"versao", "em", "por"}
    gravado_em = None           # a última gravação no banco que terminou (para a página do administrador dizer)

    def _nomes_livros(self) -> dict:
        return T.NOMES_LIVROS

    def _validar(self, aba: str, linha: dict) -> dict:
        """O tipo do Postgres, como o da Zeladoria, mais o uuid, a data, a hora e a lista de texto, que lá não pesavam:
        um texto qualquer numa coluna uuid derrubaria a leitura do livro (o tipo é anotado na `atualizacao`)."""
        nova = super()._validar(aba, linha)
        tipos = self.estado["tipos"].get(aba, {})
        for c, v in list(nova.items()):
            t = (tipos.get(c) or "").lower()
            if v is None or v == "":
                if t not in ("text", "") and not t.startswith(("text", "character")):
                    nova[c] = None
                continue
            try:
                if t == "uuid":
                    if not isinstance(v, str) or not _UUID.match(v):
                        raise ValueError
                elif t == "date":
                    date.fromisoformat(str(v)[:10])
                    nova[c] = str(v)[:10]
                elif t.startswith("timestamp"):
                    datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                elif t.endswith("[]"):
                    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                        raise ValueError
                elif t in ("jsonb", "json"):
                    if isinstance(v, float) and not math.isfinite(v):
                        raise ValueError
                elif t == "text" and not isinstance(v, str):
                    nova[c] = str(v)
            except (ValueError, TypeError):
                raise Recusa(f"{aba}: o valor de {c} não é {tipos[c]}") from None
        return nova

    def _com_padroes(self, aba: str, linha: dict) -> dict:
        nova = dict(linha)
        for c, padrao in E.PADROES.get(aba, {}).items():
            if nova.get(c) is None and c in self.estado["tipos"].get(aba, {}):
                nova[c] = _agora() if padrao == E.AGORA else str(uuid.uuid4()) if padrao == E.UUID else \
                    (list(padrao) if isinstance(padrao, list) else dict(padrao) if isinstance(padrao, dict) else padrao)
        return nova

    @staticmethod
    def _conferir_listas(aba: str, linha: dict) -> None:
        for (a, c), permitidos in E.LISTAS.items():
            if a == aba and c in linha and linha[c] is not None and linha[c] not in permitidos:
                raise Recusa(f"{aba}: {c} = {linha[c]!r} não é permitido")

    def _efeitos(self, ops: list, quem: dict, interno: bool = False) -> tuple:
        """Os pedidos, já conferidos pela API, em efeitos (("por" | "tirar", aba, chave, linha)) e, por pedido, as
        linhas como ficaram (o `.select()` depois do insert ou do update)."""
        efeitos, resultado, sombra = [], [], {}

        def atual(aba):
            if aba not in sombra:
                sombra[aba] = {_txt(l.get(self._chave(aba))): l for l in self._linhas(aba)}
            return sombra[aba]

        def por(aba, linha):
            k = _txt(linha.get(self._chave(aba)))
            atual(aba)[k] = linha
            efeitos.append(["por", aba, k, linha])

        for op in ops:
            aba, nome = op["aba"], op["op"]
            self._linhas(aba)
            chave = self._chave(aba)
            feitas = []
            if nome in ("insert", "upsert"):
                for linha in op.get("linhas") or []:
                    if not isinstance(linha, dict):
                        raise Recusa(f"{aba}: linha inválida")
                    linha = self._validar(aba, linha)
                    if linha.get(chave) in (None, ""):
                        linha = self._com_padroes(aba, linha)          # o id que o banco daria
                    k = _txt(linha.get(chave))
                    if not k:
                        raise Recusa(f"{aba}: linha nova sem {chave}")
                    existente = atual(aba).get(k)
                    if existente is not None and (nome == "insert" or aba in T.HISTORICO):
                        raise Recusa(f"{aba}: o {chave} {k} já existe")
                    # a linha nova tem todas as colunas, como no Postgres (o que não veio fica nulo, ou o padrão); a que
                    # já existe (o upsert) só troca o que veio
                    nova = {**existente, **linha} if existente else \
                        self._com_padroes(aba, {c: None for c in self.estado["tipos"].get(aba, {})} | linha)
                    falta = [c for c in E.OBRIGATORIAS.get(aba, ()) if nova.get(c) in (None, "")]
                    if falta:
                        raise Recusa(f"{aba}: falta {', '.join(falta)}")
                    self._conferir_listas(aba, nova)
                    por(aba, nova)
                    feitas.append(nova)
            elif nome == "update":
                if aba in T.HISTORICO:
                    raise Recusa(f"{aba} é histórico: só recebe linha nova")
                patch = self._validar(aba, op.get("patch") or {})
                if chave in patch:
                    raise Recusa(f"{aba}: a chave {chave} não muda")
                self._conferir_listas(aba, patch)
                for l in self._filtrar_sombra(atual(aba), op.get("filtros")):
                    nova = {**l, **patch}
                    falta = [c for c in E.OBRIGATORIAS.get(aba, ()) if nova.get(c) in (None, "")]
                    if falta:
                        raise Recusa(f"{aba}: falta {', '.join(falta)}")
                    por(aba, nova)
                    feitas.append(nova)
            elif nome == "delete":
                if aba in T.HISTORICO:
                    raise Recusa(f"{aba} é histórico: só cresce, nada se exclui")
                for l in self._filtrar_sombra(atual(aba), op.get("filtros")):
                    k = _txt(l.get(chave))
                    atual(aba).pop(k, None)
                    efeitos.append(["tirar", aba, k, None])
                    feitas.append(l)
            else:
                raise Recusa(f"pedido {nome!r} não existe no SSO")
            resultado.append(feitas)
        return efeitos, resultado

    def regravar_tudo(self, quem: str) -> int:
        """Marca os sete livros para o lote regravar com a regra de cifra de agora (a usina em claro da 1ª cópia,
        12/11/2026). Uma versão nova, sem mudança de linha, no diário: reiniciar antes do lote não perde o pedido."""
        with self._trava:
            if self.regravacao and not self.regravacao_concluida():
                return self.regravacao["versao"]           # já está regravando: o 2º clique não pede outra
            versao = self.estado["versao"] + 1
            em = _agora()
            self._escrever_diario([{"versao": versao, "efeitos": [], "quem": quem, "em": em}], acrescentar=True)
            self.estado["versao"] = versao
            for livro in T.LIVROS:
                self._sujo[livro] = versao
            self.regravacao = {"versao": versao, "em": em, "por": quem}
            self.ultima_mudanca = time.time()
            return versao

    def regravacao_concluida(self) -> bool:
        """A regravação pedida já está no banco (os sete livros gravados e conferidos na versão dela ou depois)."""
        return bool(self.regravacao) and self.versao_banco >= self.regravacao["versao"]

    def persistir(self) -> dict:
        r = super().persistir()
        if r.get("gravados"):
            self.gravado_em = _agora()
        return r

    def carregar(self, est: dict) -> None:
        self.regravacao, self.gravado_em = None, None
        super().carregar(est)
        # o pedido de regravar que ficou no diário (a versão sem efeito) volta a marcar os livros
        with self._trava:
            for r in self._ler_diario():
                if not r["efeitos"] and r["versao"] > min((est.get("versoes") or {0: 0}).values()):
                    for livro in T.LIVROS:
                        self._sujo[livro] = max(self._sujo.get(livro, 0), r["versao"])
                    self.regravacao = {"versao": r["versao"], "em": r.get("em"), "por": r.get("quem")}

    def linha(self, aba: str, chave) -> dict | None:
        k = _txt(chave)
        return next((l for l in self.estado["abas"].get(aba, []) if _txt(l.get(self._chave(aba))) == k), None)


# ── o progresso do vídeo (o `atualizar_progresso` do Supabase, que o app chamava sem achar: o bug da seção 6) ─────────
DEGRAU_S = 30       # o app manda a cada 4 s; o livro da integração só regrava quando o vídeo andou 30 s ou concluiu


def concluiu(progresso: int, duracao) -> bool:
    """A regra da função do banco: concluído com 97% (arredondado para baixo) ou a duração menos 3 s, o que for maior."""
    try:
        d = int(duracao or 0)
    except (TypeError, ValueError):
        return False
    return d > 0 and progresso >= max(d - 3, math.floor(d * 0.97))


def atualizar_progresso(g: GravadorSSO, visualizacao_id, segundos) -> dict:
    """{"gravou": bool}. O maior tempo assistido nunca diminui; `concluido` segue a regra do banco."""
    try:
        s = max(0, int(float(segundos or 0)))
    except (TypeError, ValueError, OverflowError):
        raise Recusa("progresso inválido") from None
    with g._trava:
        v = g.linha("iv_visualizacoes", visualizacao_id)
        if v is None:
            raise Recusa("visualização não encontrada")
        sessao = g.linha("iv_sessoes_video", v.get("sessao_id")) or {}
        antes = int(v.get("progresso_max_segundos") or 0)
        try:
            teto = int(sessao.get("duracao_segundos") or 0) or 24 * 3600
        except (TypeError, ValueError):
            teto = 24 * 3600
        novo = max(antes, min(s, teto))               # nunca passa da duração do vídeo
        feito = concluiu(novo, sessao.get("duracao_segundos"))
        if novo - antes < DEGRAU_S and feito == bool(v.get("concluido")):
            return {"gravou": False}
        g.aplicar([{"op": "update", "aba": "iv_visualizacoes", "filtros": [("eq", "id", v.get("id"))],
                    "patch": {"progresso_max_segundos": novo, "concluido": feito, "atualizado_em": _agora()}}],
                  {"email": "formulario", "status": "aprovado"}, g.estado["versao"])
        return {"gravou": True}


# ── o gravador do app (um por processo) e o laço do lote ─────────────────────────────────────────────────────────────
_DO_APP = {"g": None, "falha": None, "falhou_em": 0.0}
_TRAVA = threading.Lock()


class ForaDoAr(RuntimeError):
    """Este Nexus não grava o SSO, ou a cópia não está inteira no banco: a API diz isso, sem dado pela metade."""


def _carregar(config) -> GravadorSSO:
    """Lê os sete livros e o diário (~40 s no servidor), com a trava. Toda falha conta para a espera de 30 s: sem isso,
    cada pedido repetiria a leitura inteira (revisão de 12/11/2026)."""
    from ..zeladoria import leitura as ZL
    from . import leitura
    with _TRAVA:
        if _DO_APP["g"] is not None:
            return _DO_APP["g"]
        if _DO_APP["falha"] and time.time() - _DO_APP["falhou_em"] < Z.ESPERA_FALHA_S:
            raise ForaDoAr(_DO_APP["falha"])
        from ..cadastro.ligacoes import pasta_dados
        if config.get("TESTING") and not config.get("NEXUS_DADOS"):
            raise ForaDoAr("teste sem NEXUS_DADOS: o diário não vai para a pasta de dados real")
        import requests
        try:
            g = GravadorSSO(base=ZL._base(config), token=config.get("GRIDCO_SQL_TOKEN") or "", sessao=ZL._sessao(),
                            cofre=ZL.cofre_de(config), diario=Path(pasta_dados(config)) / "sso" / "diario.jsonl")
            g.carregar(leitura.ler_banco(ZL._base(config), g.sessao, g.cofre))
        except Exception as e:  # noqa: BLE001 — banco fora, cópia incompleta, diário ilegível: a mesma espera
            if isinstance(e, requests.RequestException):
                msg = f"o banco do Nexus não respondeu agora ({type(e).__name__}): tente de novo em 1 minuto"
            elif isinstance(e, (leitura.CopiaAusente, ZL.CopiaAusente)):
                msg = str(e)
            else:
                log.exception("sso: a leitura dos livros falhou")
                msg = f"o Nexus não conseguiu ler o SSO agora ({type(e).__name__})"
            _DO_APP.update(falha=msg, falhou_em=time.time())
            raise ForaDoAr(msg) from None
        _DO_APP.update(g=g, falha=None)
        if not config.get("TESTING"):
            threading.Thread(target=Z._laco, args=(g,), daemon=True, name="nexus-sso-gravacao").start()
        return g


_EM_FUNDO = {"thread": None}


def do_app(config, *, esperar: bool = False) -> GravadorSSO:
    """O gravador carregado. O pedido nunca espera a leitura dos livros (~40 s): sem o gravador, a leitura começa por
    trás e o pedido volta 503 "carregando". Revisão de 12/11/2026: 32 pedidos anônimos esperando a leitura tomavam todas as
    threads do waitress, e o Nexus inteiro parava depois de cada deploy. `esperar` (o aquecimento ao subir, os testes)
    lê na hora."""
    if not ativo(config):
        raise ForaDoAr("este Nexus não guarda o SSO (a gravação fica no servidor)")
    g = _DO_APP["g"]
    if g is not None:
        return g
    if esperar or config.get("TESTING"):
        return _carregar(config)
    if _DO_APP["falha"] and time.time() - _DO_APP["falhou_em"] < Z.ESPERA_FALHA_S:
        raise ForaDoAr(_DO_APP["falha"])
    from flask import current_app
    app = current_app._get_current_object()
    with _TRAVA_FUNDO:
        t = _EM_FUNDO["thread"]
        if t is None or not t.is_alive():
            def tarefa():
                try:
                    with app.app_context():
                        _carregar(app.config)
                except ForaDoAr:
                    pass
            t = threading.Thread(target=tarefa, daemon=True, name="nexus-sso-carga")
            _EM_FUNDO["thread"] = t
            t.start()
    raise ForaDoAr("o Nexus está lendo os dados do SSO agora (cerca de 1 minuto): tente de novo em instantes")


_TRAVA_FUNDO = threading.Lock()


def ja_carregado() -> GravadorSSO | None:
    return _DO_APP["g"]


def esquecer() -> None:
    with _TRAVA:
        _DO_APP.update(g=None, falha=None, falhou_em=0.0)
