"""Mapa de equipe (08/11/2026): as três rotas do contrato com o Nexus Field (seção 8 do desenho, confirmado pela casca).
O estado mora em `nexus/campo/equipe/servico.py`; aqui só o HTTP. Fica num módulo à parte, importado no fim do
`__init__` da torre, porque precisa do `bp` (como o `cliente_tela`).

As três são PÚBLICAS (`auth.ROTAS_PUBLICAS`), conscientemente: quem chama é o celular, sem a sessão do Nexus.
- `POST /t/campo/equipe/aparelho`: chamada pela PÁGINA do App de Campo dentro da casca (só ela tem o login Microsoft, e
  o token nunca vai ao nativo). Vale o ID token da Microsoft, conferido pela assinatura (`token_ms`). CORS só para a
  origem do App, em TODA resposta dela: sem o cabeçalho a página não lê o código, e não saberia separar o 401 do 503.
- `POST /t/campo/equipe/posicoes` e `POST /t/campo/equipe/aparelho/revogar`: chamadas pelo NATIVO, sem CORS. Vale a
  chave do aparelho (`Authorization: Bearer <chave>`), que tem de ser do `aparelho` do corpo.

Os códigos são o que a casca faz com eles: 401 apaga a chave dela (só quando a chave ou o token não valem); 503 é "como
sem rede" (a fila e a chave ficam), para a Microsoft ou o banco fora e o servidor sem configuração; 413 é o lote acima
de 200 pontos ou o corpo acima de 64 KB; 400, o corpo que não segue o contrato (erro de quem programou a casca). Nenhuma
resposta é 500: o que quebrar responde 503 e vai ao log só pelo tipo do erro.
"""
import json
import logging
import re

from flask import Response, current_app, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from ...auth import chaves, microsoft
from ...campo import equipe as E
from ...campo.equipe import pontos as PT
from ...campo.equipe import servico as S
from ...campo.equipe import token_ms as T
from . import bp

_log = logging.getLogger("nexus.campo.equipe")

TETO_CORPO = 64 * 1024
# o id que a casca cria uma vez por instalação (não é IMEI nem nada do aparelho); vai ao banco em claro: daí a forma
_APARELHO = re.compile(r"[A-Za-z0-9_-]{1,64}")
# "NexusField/<versão>": texto que vai ao banco; começa por letra ou algarismo (nada de "=", "+", "-" ou "@" no início,
# que uma planilha leria como fórmula) e sem caractere de controle
_APP = re.compile(r"[A-Za-z0-9][\x20-\x7e]{0,39}")
CORS = {"Access-Control-Allow-Origin": E.ORIGEM_APP, "Access-Control-Allow-Headers": "Authorization, Content-Type",
        "Access-Control-Allow-Methods": "POST, OPTIONS"}
_CONFIG = (("NEXUS_CHAVE_CADASTRO", "a chave do cadastro, que cifra a posição: .env"),
           ("NEXUS_EQUIPE_MS_CLIENT_ID", "o ID do aplicativo do App de Campo: Base → Chaves das fontes → Nexus"),
           ("NEXUS_EQUIPE_MS_TENANT_ID", "o diretório da Grid Co.: Base → Chaves das fontes → Nexus"))
TEXTO_NAO_LIDAS = "as chaves dos aparelhos ainda não foram lidas do banco; tente de novo em instantes"


class _Recusa(Exception):
    def __init__(self, status: int, texto: str):
        super().__init__(texto)
        self.status, self.texto = status, texto


def _resposta(status: int, corpo: dict | None, cors: bool = False) -> Response:
    r = Response(status=status) if corpo is None else jsonify(corpo)
    r.status_code = status
    r.headers["Cache-Control"] = "no-store"         # a chave e o estado da coleta não ficam em cache nenhum
    if cors:
        r.headers.update(CORS)
    return r


def _responder(fazer, cors: bool = False) -> Response:
    try:
        status, corpo = fazer()
    except _Recusa as e:
        status, corpo = e.status, {"erro": e.texto}
    except Exception as e:      # noqa: BLE001 — nunca 500 para a casca: 503 é "tente de novo"
        _log.error("equipe: %s inesperado em %s", type(e).__name__, request.endpoint)
        status, corpo = 503, {"erro": "falha no servidor do Nexus; tente de novo"}
    return _resposta(status, corpo, cors)


def _configurado(cfg) -> None:
    """Sem a chave do cadastro o servidor não grava a coordenada (nem em claro, nem cifrada) e não emite chave; sem os
    dois IDs do Entra não confere o login. A falta é dita pelo nome, para quem configura."""
    falta = [f"{nome} ({onde})" for nome, onde in _CONFIG
             if not (str(cfg.get(nome) or "").strip() if nome == "NEXUS_CHAVE_CADASTRO" else chaves.valor(nome, cfg))]
    if falta:
        raise _Recusa(503, "o servidor está sem a configuração do Mapa de equipe: falta " + "; ".join(falta))


def _corpo() -> dict:
    """O JSON do corpo, com o teto de 64 KB posto ANTES de ler (o corpo sem tamanho declarado também para nele)."""
    request.max_content_length = TETO_CORPO
    try:
        bruto = request.get_data(cache=False)
    except RequestEntityTooLarge:
        raise _Recusa(413, "corpo acima de 64 KB") from None
    try:
        corpo = json.loads(bruto)
    except (ValueError, RecursionError):            # o JSON fundo demais levanta RecursionError, não ValueError
        raise _Recusa(400, "o corpo não é JSON") from None
    if not isinstance(corpo, dict):
        raise _Recusa(400, "o corpo tem de ser um objeto JSON")
    return corpo


def _aparelho(corpo: dict) -> str:
    a = corpo.get("aparelho")
    if not isinstance(a, str) or not a:
        raise _Recusa(400, "falta o aparelho")
    return a


def _portador() -> str:
    tipo, _, valor = request.headers.get("Authorization", "").partition(" ")
    return valor.strip() if tipo.lower() == "bearer" else ""


def _servico() -> S.Servico:
    try:
        return S.do_app(current_app._get_current_object())
    except Exception as e:      # noqa: BLE001 — a chave do cadastro inválida, a pasta de dados que não abre
        _log.error("equipe: o serviço não subiu (%s)", type(e).__name__)
        raise _Recusa(503, f"o serviço do Mapa de equipe não subiu ({type(e).__name__})") from None


def _registro():
    cfg = current_app.config
    _configurado(cfg)
    corpo = _corpo()
    aparelho, app = _aparelho(corpo), corpo.get("app", "")
    if not _APARELHO.fullmatch(aparelho):
        raise _Recusa(400, "aparelho fora do formato (até 64 letras, algarismos, _ ou -)")
    if not isinstance(app, str) or (app and not _APP.fullmatch(app)):
        raise _Recusa(400, "app fora do formato (NexusField/<versão>, até 40 caracteres)")
    token = _portador()
    if not token:
        raise _Recusa(401, "falta o token da Microsoft (Authorization: Bearer)")
    srv, agora = _servico(), S._agora()
    try:
        email = srv.conferir_token(token, cliente=chaves.valor("NEXUS_EQUIPE_MS_CLIENT_ID", cfg),
                                   diretorio=chaves.valor("NEXUS_EQUIPE_MS_TENANT_ID", cfg),
                                   dominios=microsoft.dominios(cfg), agora=agora)
    except T.TokenRecusado as e:
        # o texto da recusa nunca leva o token nem o e-mail (token_ms): pode ir ao journal e à resposta
        _log.info("equipe: registro recusado (%s)", e)
        raise _Recusa(401, f"token recusado: {e}") from None
    except T.MicrosoftForaDoAr as e:
        _log.warning("equipe: registro sem a Microsoft (%s)", e)
        raise _Recusa(503, "as chaves da Microsoft não responderam; tente de novo") from None
    except ValueError as e:
        # o GUID errado na configuração (o texto diz qual chave, nunca o valor): erro do servidor, não token ruim
        _log.error("equipe: configuração do Entra errada (%s)", e)
        raise _Recusa(503, f"o servidor está com a configuração errada: {e}") from None
    if not srv.chaves_prontas(agora):
        raise _Recusa(503, TEXTO_NAO_LIDAS)
    pid = srv.pessoa_do_email(email)
    try:
        vale = pid is not None and srv.coleta_vale(pid, agora)
    except S.AindaLendo:
        raise _Recusa(503, "o cadastro está sendo lido; tente de novo em instantes") from None
    if not vale:
        return 200, {"coleta": False}
    return 200, {"coleta": True, "chave": srv.registrar(pid, aparelho, app, agora)}


def _posicoes():
    _configurado(current_app.config)
    corpo = _corpo()
    aparelho, pontos = _aparelho(corpo), corpo.get("pontos", [])
    if not isinstance(pontos, list):
        raise _Recusa(400, "pontos tem de ser uma lista")
    fuso = PT._num(corpo.get("fuso"))
    if pontos and (fuso is None or abs(fuso) > PT._FUSO_MAX_MIN):
        # sem o fuso o `aceitar` descarta o lote inteiro (não sabe se é expediente) e o 200 faria a casca apagar os
        # pontos dela calada: o 400 mostra o erro de quem programou
        raise _Recusa(400, "fuso fora do formato (minutos somados ao UTC; Brasília = -180)")
    chave = _portador()
    if not chave:
        raise _Recusa(401, "falta a chave do aparelho (Authorization: Bearer)")
    srv, agora = _servico(), S._agora()
    if not srv.chaves_prontas(agora):
        raise _Recusa(503, TEXTO_NAO_LIDAS)
    pid = srv.quem(chave, aparelho)
    if pid is None:
        # a mesma resposta para a chave desconhecida, a revogada e a de outro aparelho
        raise _Recusa(401, "chave do aparelho desconhecida ou revogada")
    if len(pontos) > E.MAX_PONTOS:
        raise _Recusa(413, f"lote com mais de {E.MAX_PONTOS} pontos")
    try:
        if not srv.coleta_vale(pid, agora):
            # saiu do piloto ou não é mais técnico de campo ativo: nada entra, e a casca para até a próxima carga
            return 200, {"aceitos": 0, "coleta": False}
        aceitos = srv.receber(pid, corpo, agora)
    except S.AindaLendo:
        raise _Recusa(503, "o cadastro está sendo lido; tente de novo em instantes") from None
    except OSError as e:
        _log.error("equipe: os pontos não foram para o diário (%s)", type(e).__name__)
        raise _Recusa(503, "não consegui guardar os pontos agora; tente de novo") from None
    return 200, {"aceitos": aceitos, "coleta": True}


def _revogacao():
    _configurado(current_app.config)
    aparelho = _aparelho(_corpo())
    chave = _portador()
    if chave:
        srv, agora = _servico(), S._agora()
        if not srv.chaves_prontas(agora):
            raise _Recusa(503, TEXTO_NAO_LIDAS)
        # 204 em todo caso: a resposta não diz se a chave valia (sem oráculo); a de outro aparelho não cai
        srv.revogar(chave, aparelho, agora)
    return 204, None


@bp.route("/equipe/aparelho", methods=["POST", "OPTIONS"], endpoint="equipe_aparelho")
def equipe_aparelho():
    """O registro do aparelho: `{aparelho, app}` com o ID token -> `{coleta: true, chave}` ou `{coleta: false}`."""
    cors = request.headers.get("Origin") == E.ORIGEM_APP       # igual, inteira: a que só começa igual não passa
    if request.method == "OPTIONS":
        r = _resposta(204, None, cors)
    else:
        r = _responder(_registro, cors)
    r.vary.add("Origin")        # a resposta muda com a origem: a cópia de um proxy não serve a outra
    return r


@bp.route("/equipe/posicoes", methods=["POST"], endpoint="equipe_posicoes")
def equipe_posicoes():
    """As posições: `{aparelho, fuso, pontos: [...], permissao?}` com a chave -> `{aceitos, coleta}`."""
    return _responder(_posicoes)


@bp.route("/equipe/aparelho/revogar", methods=["POST"], endpoint="equipe_revogar")
def equipe_revogar():
    """O Sair da casca: `{aparelho}` com a chave -> 204."""
    return _responder(_revogacao)
