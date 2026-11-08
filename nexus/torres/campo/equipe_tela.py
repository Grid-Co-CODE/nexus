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
sem rede" (a fila e a chave ficam), para a Microsoft ou o banco fora (também o piloto, os técnicos ou o cadastro sem
nenhuma leitura boa: "não sei" nunca vira coleta false), o disco que não grava, o servidor sem configuração e a máquina
em que o gravador em lote não roda (quem recebe tem de ser quem grava); 413 é o lote acima
de 200 pontos ou o corpo acima de 64 KB; 400, o corpo que não segue o contrato (erro de quem programou a casca). Nenhuma
resposta é 500: o que quebrar responde 503 e vai ao log só pelo tipo do erro.

A tela (Task 7, no fim deste arquivo): `GET /t/campo/equipe` (o mapa e o painel), `GET /t/campo/equipe/rota` (o Abrir
rota: o servidor monta o link do Google Maps e redireciona; a página nunca tem a coordenada) e `POST
/t/campo/equipe/piloto` (quem entra no piloto da coleta; só o administrador). Quem vê é conferido DENTRO de cada uma
(`_quem_ve`), além do portão por setor: o portão fica desligado sem a NEXUS_PESSOA_HMAC, e a marca de outro setor em
Base → Acessos abriria a tela. Cada abertura do mapa e de cada rota vai ao registro da LGPD (`servico.registro`). O
nome do técnico aparece na tela (é para isso que ela existe), decifrado do cadastro, e nunca vai ao banco nem ao log.
"""
import json
import logging
import re
from collections import Counter
from datetime import timedelta, timezone

from flask import Response, abort, current_app, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from ...auth import chaves, microsoft, setor_telas
from ...cadastro import setor_ids as SID
from ...cadastro.servico import chave_texto
from ...campo import equipe as E
from ...campo import mapa_responsaveis as MR
from ...campo import visao
from ...campo.equipe import gravador as G
from ...campo.equipe import municipios as MU
from ...campo.equipe import piloto as PI
from ...campo.equipe import pontos as PT
from ...campo.equipe import servico as S
from ...campo.equipe import situacao as SI
from ...campo.equipe import token_ms as T
from ...campo.ligacao_cadastro import codigo_da_pessoa
from ...performance.clima import mapa as RISCO
from . import TORRE, bp

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
TEXTO_LENDO = "o cadastro está sendo lido; tente de novo em instantes"
TEXTO_DISCO = "não consegui guardar no disco do servidor agora; tente de novo"
# o id que vem na URL ou no formulário: só algarismos ASCII, até 12. O `isdigit` aceita "²" (e o `int` quebra: 500), e o
# número de 5000 algarismos passa do teto de algarismos do `int` (revisão final de 08/11/2026)
_ID = re.compile(r"[0-9]{1,12}")


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
    dois IDs do Entra não confere o login. A falta é dita pelo nome, para quem configura.

    E quem recebe tem de ser quem grava (revisão final de 08/11/2026): na máquina em que o gravador em lote não roda
    (`NEXUS_EQUIPE_GRAVA` diferente de "1"), a chave emitida, a revogação e os pontos ficariam só na memória e no disco
    dela e nunca chegariam ao banco; a casca recebe 503 (visível, e nenhuma chave se perde). Nos testes o gravador nunca
    liga, e as rotas valem."""
    if not cfg.get("TESTING") and not G.ativo(cfg):
        raise _Recusa(503, "o Mapa de equipe não grava nesta máquina (NEXUS_EQUIPE_GRAVA=1 só no servidor que grava): "
                           "nada é recebido aqui")
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
    try:
        # "não sei quem é / quem está no piloto" (o banco sem leitura boa) é 503, nunca o coleta false que pararia o
        # celular até a próxima abertura do App (revisão final de 08/11/2026)
        pid = srv.pessoa_do_email(email)
        vale = pid is not None and srv.coleta_vale(pid, agora)
    except S.AindaLendo:
        raise _Recusa(503, TEXTO_LENDO) from None
    except S.BancoFora as e:
        raise _Recusa(503, str(e)) from None
    if not vale:
        return 200, {"coleta": False}
    try:
        chave = srv.registrar(pid, aparelho, app, agora)
    except OSError as e:
        # o evento vai ao jornal em disco antes de a chave valer: sem o disco, nenhuma chave (a velha segue valendo)
        _log.error("equipe: a chave nova não foi para o jornal (%s)", type(e).__name__)
        raise _Recusa(503, TEXTO_DISCO) from None
    return 200, {"coleta": True, "chave": chave}


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
        raise _Recusa(503, TEXTO_LENDO) from None
    except S.BancoFora as e:
        raise _Recusa(503, str(e)) from None
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
        try:
            srv.revogar(chave, aparelho, agora)
        except OSError as e:
            # a revogação vai ao jornal antes de a chave cair: sem o disco, a casca tenta o Sair de novo
            _log.error("equipe: a revogação não foi para o jornal (%s)", type(e).__name__)
            raise _Recusa(503, TEXTO_DISCO) from None
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


# ── a tela do Mapa de equipe (Task 7) ────────────────────────────────────────────────────────────────────────────────
_BRT = timezone(timedelta(hours=-3))
# o nome de cada setor que vê o mapa, para a recusa dizer a regra; quem vê de verdade é o `do_setor` da Tela
NOME_DO_SETOR = {SID.PCM: "PCM", SID.COS: "COS", SID.PERFORMANCE: "Performance",
                 SID.SUPERVISAO_CAMPO: "Supervisão Campo", SID.RESPONSAVEL_UFV: "Responsáveis UFV"}
NAO_HA_ROTA = ("A rota não abre para este técnico agora: ela só sai do ponto em deslocamento ou na usina (não do "
               "parado fora de usina, de quem está sem permissão de localização nem de quem está sem posição hoje). "
               "Volte ao Mapa de equipe e atualize a página.")
# o resumo do topo, na ordem de quem pede atenção: (chave da situação, singular, plural)
RESUMO = (("sem_permissao", "sem permissão", "sem permissão"), ("sem_sinal", "sem sinal", "sem sinal"),
          ("deslocamento", "em deslocamento", "em deslocamento"), ("na_usina", "na usina", "na usina"),
          ("fora_usina", "parado fora de usina", "parados fora de usina"),
          ("sem_posicao", "sem posição hoje", "sem posição hoje"))
PILOTO_MSG = {"ok": ("ok", "Decisão do piloto gravada: vale para o celular no próximo envio."),
              "erro": ("critico", "Não consegui gravar a decisão do piloto (o banco não respondeu): nada mudou. "
                                  "Tente de novo em instantes."),
              "sem_token": ("critico", "Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): a decisão "
                                       "do piloto não foi gravada.")}


def _juntar(nomes: list) -> str:
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _setores_que_veem() -> tuple:
    return setor_telas.donos_do_codigo(TORRE.tela("equipe"))


def _regra() -> str:
    nomes = [NOME_DO_SETOR.get(s, f"setor {s}") for s in _setores_que_veem()]
    return f"O Mapa de equipe é visto só pelos setores {_juntar(nomes)} e pelos administradores do Nexus."


def _usuario() -> tuple[str, str]:
    u = session.get("usuario")
    if not isinstance(u, dict):
        return "", ""
    return str(u.get("email") or "").strip().lower(), str(u.get("nome") or "").strip()


def _quem_ve() -> dict:
    """{"pode", "aviso"}: o administrador, ou quem é de um dos setores donos da tela. É a regra escrita no aviso ao
    técnico (quem vê a posição dele), conferida aqui também, e não só no portão: o portão fica desligado sem a
    NEXUS_PESSOA_HMAC (e nos testes), e a marca de OUTRO setor em Base → Acessos abriria a tela. Sem saber o setor (sem
    a chave HMAC, o banco que não respondeu), só o administrador; o cliente, nunca."""
    regra = _regra()
    if session.get("via") == "cliente":
        return {"pode": False, "aviso": regra}
    if session.get("admin"):
        return {"pode": True, "aviso": ""}
    cfg = current_app.config
    if not cfg.get("NEXUS_PESSOA_HMAC"):
        return {"pode": False, "aviso": regra + " Este Nexus ainda não sabe o setor de cada pessoa (falta a "
                                                "NEXUS_PESSOA_HMAC no servidor): por enquanto só o administrador vê o "
                                                "mapa."}
    email, _nome = _usuario()
    try:
        setor = setor_telas.setor_da_pessoa(cfg, email, *setor_telas._banco())
    except Exception as e:      # noqa: BLE001 — sem saber o setor, fecha (e diz que é leitura, não falta de setor)
        _log.warning("equipe: não consegui ler o setor de quem abriu o mapa (%s)", type(e).__name__)
        return {"pode": False, "aviso": regra + " Não consegui ler o seu setor agora; tente de novo em instantes."}
    if setor and setor.get("id") in _setores_que_veem():
        return {"pode": True, "aviso": ""}
    onde = f"Você está no setor {setor['nome']}." if setor else "Você está sem setor no Nexus."
    return {"pode": False, "aviso": f"{regra} {onde}"}


def _texto(status: int, texto: str) -> Response:
    r = Response(texto, status=status, mimetype="text/plain")
    r.headers["Cache-Control"] = "no-store"
    return r


def _servico_da_tela():
    """(serviço, aviso): sem a chave do cadastro (ou com a pasta de dados que não abre), o mapa não tem o que mostrar e
    diz o porquê, sem 500."""
    try:
        return S.do_app(current_app._get_current_object()), ""
    except S.SemConfiguracao:
        return None, ("O Mapa de equipe precisa da chave do cadastro neste servidor (NEXUS_CHAVE_CADASTRO): sem ela as "
                      "posições não são recebidas nem mostradas.")
    except Exception as e:      # noqa: BLE001
        _log.error("equipe: o serviço do mapa não subiu (%s)", type(e).__name__)
        return None, f"O serviço do Mapa de equipe não subiu neste servidor ({type(e).__name__})."


def _equipe(srv, agora):
    """(cadastro, técnicos de campo, piloto, aviso). Quem o mapa mostra é quem a coleta vale (`servico.coleta_vale`):
    técnico de campo ativo do cadastro E no piloto. Quem não é coletado não aparece, nem como "sem posição hoje", e
    quem saiu do piloto sai do mapa, mesmo com ponto de hoje. O cadastro que não se lê sobe."""
    from ...pcm.tecnicos_usina import pessoas_de_campo
    b = visao._Base()
    tecnicos = pessoas_de_campo(b, current_app.config)
    try:
        piloto, aviso = srv.piloto(agora), ""
        if piloto is None:
            aviso = ("Não consegui ler o piloto no banco agora: o mapa fica sem técnicos até ler. Tente de novo em "
                     "instantes.")
    except S.AindaLendo:
        piloto, aviso = None, "O piloto está sendo lido do banco agora; atualize a página em instantes."
    return b, tecnicos, piloto or frozenset(), aviso


def _quem_abriu(srv) -> tuple:
    """(pessoa_id, pessoa_hmac) de quem está olhando, para o registro da LGPD: o código do e-mail (o mesmo do App) e a
    pessoa do cadastro pelo e-mail EXATO da ficha (`servico.pessoa_do_email`, a mesma regra do registro do aparelho),
    nunca pelo nome: o `pessoa_do_login` acha pelo nome tirado do e-mail, e a trilha gravaria o homônimo (revisão final
    de 08/11/2026). Sem a ficha do e-mail, None: o código do e-mail identifica. A senha de administrador não tem e-mail:
    vai vazio, como nas decisões de setor."""
    email, _nome = _usuario()
    codigo = codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) or ""
    pid = None
    if email:
        try:
            pid = srv.pessoa_do_email(email)
        except Exception as e:  # noqa: BLE001 — sem a pessoa, o código basta para o registro
            _log.warning("equipe: não achei a pessoa de quem abriu o mapa (%s)", type(e).__name__)
    return pid, codigo


def _registrar_acesso(srv, acao, alvo, usina_id, agora) -> bool:
    """A linha da LGPD, no jornal em disco ANTES de o mapa ou a rota abrir. O disco que falha = False: a tela não abre
    sem a trilha."""
    quem_pid, quem_hmac = _quem_abriu(srv)
    try:
        srv.registro.acrescentar(acao, quem_pid, quem_hmac, alvo, usina_id, agora)
        return True
    except OSError as e:
        _log.error("equipe: o registro de acesso não foi para o disco (%s)", type(e).__name__)
        return False


SEM_REGISTRO = ("Não consegui gravar o registro desta abertura no disco do servidor (o registro da LGPD de quem abriu o "
                "mapa): sem ele o mapa não abre. Tente de novo em instantes.")


def _hora(inst, agora) -> str:
    """A hora de Brasília: "hoje às 11:57" ou "07/11 às 21:40"."""
    if inst is None:
        return ""
    local = inst.astimezone(_BRT)
    if local.date() == agora.astimezone(_BRT).date():
        return f"hoje às {local:%H:%M}"
    return f"{local:%d/%m} às {local:%H:%M}"


def _onde(s: dict) -> str:
    """O lugar do parado fora de usina, sem o ponto: "Cidade/UF" pela malha do IBGE; sem a cidade, só a UF."""
    if s.get("cidade") and s.get("uf"):
        return f"{s['cidade']}/{s['uf']}"
    return s.get("uf") or ""


def _cidade_de():
    """A função da cidade para a `situacao`: a malha de municípios do IBGE guardada na pasta de dados (baixada do IBGE
    só pela sigla do estado). Sem a pasta de dados, sem cidade: o painel mostra o estado."""
    from ...cadastro.ligacoes import pasta_dados
    try:
        pasta = pasta_dados(current_app.config)
    except Exception:           # noqa: BLE001
        return None
    return lambda lat, lon, uf: MU.cidade(lat, lon, uf, pasta=pasta)


def _linhas(srv, b, tecnicos, piloto, coords, nomes_usina, agora):
    """As linhas do painel (uma por técnico do piloto, pelo nome) e os pontos do mapa [(pessoa_id, lat, lon, tom)],
    estes só de quem vai ao mapa. A coordenada fica aqui, na memória do processo: a página recebe o x/y do `desenho`."""
    linhas, pontos, cidade = [], [], _cidade_de()
    for pid in sorted((p for p in tecnicos if p in piloto), key=lambda p: chave_texto(tecnicos[p]["nome"])):
        t = tecnicos[pid]
        est = srv.estado_de(pid, agora)
        s = SI.situacao(est, coords, agora, cidade=cidade)
        perto = s["usina_perto"]
        # o parado fora de usina leva o km inteiro (revisão final de 08/11/2026): com a casa decimal, a distância a
        # duas usinas já cercava a casa ou o hotel que o mapa não mostra
        inteiro = s["base"] == "fora_usina"
        linhas.append({
            "pid": pid, "nome": t["nome"], "equipe": b.nome_equipe.get(t["equipe_id"]) or "", "s": s,
            "hora": _hora(s["ultima"], agora), "onde": _onde(s),
            "perto": SI.texto_perto(perto[1], nomes_usina.get(perto[0]) or f"usina {perto[0]}", inteiro=inteiro)
                     if perto else "",
            "desde": _hora(s["desde"], agora) if s["chave"] == "sem_permissao" else ""})
        if s["no_mapa"]:
            u = est["ultimo"]
            pontos.append((pid, u["lat"], u["lon"], s["tom"]))
    return linhas, pontos


def _grupos(linhas: list) -> list:
    """O painel sem técnico escolhido: quem está no mapa, e os três grupos que ficam só na lista."""
    no_mapa = [l for l in linhas if l["s"]["no_mapa"]]
    fora = [l for l in linhas if not l["s"]["no_mapa"] and l["s"]["chave"] in ("fora_usina", "sem_sinal")]
    sem_perm = [l for l in linhas if not l["s"]["no_mapa"] and l["s"]["chave"] == "sem_permissao"]
    sem_pos = [l for l in linhas if l["s"]["chave"] == "sem_posicao"]
    return [("mapa", "No mapa", no_mapa), ("sem_permissao", "Sem permissão de localização", sem_perm),
            ("fora", "Parados fora de usina", fora), ("sem_posicao", "Sem posição hoje", sem_pos)]


def _resumo(linhas: list) -> list:
    n = Counter(l["s"]["chave"] for l in linhas)
    return [(n[k], um if n[k] == 1 else varios, SI.TOM[k]) for k, um, varios in RESUMO if n[k]]


def _supervisor_da_equipe(b, equipe_id):
    """O Supervisor de Campo da região de campo da equipe (`equipes.regiao_campo_id` -> `regioes_campo.
    supervisor_campo_id`), ou None (equipe sem região, vaga aberta). É assim que o cadastro diz quem lidera o técnico
    desde a estrutura de O&M de 10/2026 (`visao._Base`): o `supervisor_id` da ficha da pessoa saiu das telas, porque na
    prática era o Gestor de contrato."""
    r = b.regiao.get(b.regiao_da_equipe.get(equipe_id))
    return r["supervisor_id"] if r else None


def _filtro(b, tecnicos: dict, piloto) -> dict:
    """O filtro por supervisor e por equipe (Levi, 08/11/2026: "Opção de filtrar por supervisor ou equipe"), pela URL
    (`?supervisor=<pessoa_id>&equipe=<equipe_id>`). As opções são só as de quem o mapa mostra (técnico de campo ativo E
    no piloto), com o nome do cadastro (o da pessoa decifrado da ficha; o da equipe, de `cadastro_nexus · equipes`). O
    id que não está nas opções (o que não existe, o de quem está fora do piloto, o torto) não filtra: a tela mostra
    todos, sem erro. Os dois juntos valem juntos. Devolve {"supervisor", "equipe" (o id escolhido ou None), "opcoes_*"
    [(id, nome)], "q" (o que vai em todo link da tela, para o clique no técnico não perder o filtro)}."""
    no_mapa = [t for pid, t in tecnicos.items() if pid in piloto]
    sups = {s for s in (_supervisor_da_equipe(b, t["equipe_id"]) for t in no_mapa) if s}
    nomes = b.nomes(sups)
    opcoes_sup = sorted(((s, nomes.get(s) or f"Supervisor {s}") for s in sups), key=lambda x: chave_texto(x[1]))
    opcoes_eq = sorted(((e, b.nome_equipe.get(e) or f"Equipe {e}") for e in {t["equipe_id"] for t in no_mapa} if e),
                       key=lambda x: chave_texto(x[1]))

    def escolha(nome, opcoes):
        pedido = str(request.args.get(nome) or "").strip()
        return int(pedido) if _ID.fullmatch(pedido) and int(pedido) in {i for i, _n in opcoes} else None
    f = {"supervisor": escolha("supervisor", opcoes_sup), "equipe": escolha("equipe", opcoes_eq),
         "opcoes_supervisor": opcoes_sup, "opcoes_equipe": opcoes_eq}
    f["q"] = {k: f[k] for k in ("supervisor", "equipe") if f[k] is not None}
    return f


def _no_filtro(b, t: dict, f: dict) -> bool:
    return ((f["equipe"] is None or t["equipe_id"] == f["equipe"])
            and (f["supervisor"] is None or _supervisor_da_equipe(b, t["equipe_id"]) == f["supervisor"]))


def _tela(contexto: dict, status: int = 200):
    tela = TORRE.tela("equipe")
    r = current_app.make_response((render_template("campo/equipe.html", torre=TORRE, tela=tela, **contexto), status))
    r.headers["Cache-Control"] = "no-store"         # a posição de pessoas não fica na cópia do navegador nem de proxy
    return r


# o botão Usinas: o Mapa de risco da Performance com os links voltando aqui. O `ver` desta tela é o botão Técnicos |
# Usinas (o `?ver=` dos botões de vista do Campo, como Lista | Quadro das Ocorrências): as camadas de cima do mapa, que
# na tela da Performance vão em `ver`, aqui vão em `camadas`
ENDERECO_USINAS = RISCO.Endereco(rota="torre_campo.equipe", fixos=(("ver", "usinas"),), camadas="camadas")


def _tela_usinas():
    """O botão Usinas (Levi, 08/11/2026: "Consegue incluir as informações de performance clima e risco? dando certo a
    gente deixa tudo em mapa de equipe... aí vai ser possível ver tempestades e pontos de fogo! Tendo um botão de técnico
    e usina, quando clica em usinas aparece os alertas das UFVs, quando é técnico mostra só essa tela padrão!"): o Mapa de
    risco da Performance DENTRO desta página, do mesmo modelo (`mapa_tela.modelo` -> `clima.mapa.montar`) e do mesmo SVG,
    sem moldura e sem regra copiada. Nada de técnico aqui: o serviço das posições nem sobe, e a abertura não grava
    "abriu_mapa" na trilha da LGPD (não há dado pessoal); a releitura sozinha do mapa (clima-mapa.js) pede esta mesma
    página. Quem vê é o mesmo do Técnicos (`_quem_ve`, conferido antes)."""
    from ..performance import TORRE as TORRE_PERFORMANCE
    from ..performance import mapa_tela
    v, eventos = mapa_tela.modelo(request.args, ENDERECO_USINAS)
    return _tela({"ver": "usinas", "v": v, "eventos": eventos, "tela_risco": TORRE_PERFORMANCE.tela("clima/mapa")})


@bp.route("/equipe", endpoint="equipe")
def equipe():
    """O mapa: os técnicos do piloto com a situação de cada um, o painel ao lado e, para o administrador, o piloto. Com
    `?ver=usinas`, o Mapa de risco das usinas (`_tela_usinas`)."""
    quem = _quem_ve()
    if not quem["pode"]:
        return _tela({"recusa": quem["aviso"]}, 403)
    if str(request.args.get("ver") or "").strip() == "usinas":
        return _tela_usinas()
    srv, aviso = _servico_da_tela()
    if srv is None:
        return _tela({"erro": aviso})
    agora = S._agora()
    try:
        b, tecnicos, piloto, aviso_piloto = _equipe(srv, agora)
    except Exception as e:      # noqa: BLE001 — sem o cadastro, a tela diz por quê
        _log.warning("equipe: não consegui ler o cadastro para o mapa (%s)", type(e).__name__)
        return _tela({"erro": f"Não consegui ler o cadastro do Nexus agora ({type(e).__name__}); tente de novo em "
                              "instantes."})
    coords, erro_coords = MR.coordenadas()
    nomes_usina = {str(uid): str(u.get("nome") or "").strip() for uid, u in b.por_id.items()}
    filtro = _filtro(b, tecnicos, piloto)
    # o filtro vale para tudo o que mostra técnico: os pontos, as listas, o resumo e o painel do escolhido (que sai
    # das linhas). O controle do piloto, não: é quem o administrador põe e tira da coleta, filtro nenhum o esconde
    vistos = {pid: t for pid, t in tecnicos.items() if _no_filtro(b, t, filtro)}
    linhas, pontos = _linhas(srv, b, vistos, piloto, coords, nomes_usina, agora)
    try:
        mapa = SI.desenho(coords, pontos)
    except ValueError as e:     # o contorno do IBGE que não abre: a lista continua valendo
        _log.warning("equipe: o contorno dos estados não abriu (%s)", type(e).__name__)
        mapa = {"viewbox": None, "ufs": [], "usinas": [], "pontos": []}
    pedido = str(request.args.get("tecnico") or "").strip()
    sel = next((l for l in linhas if _ID.fullmatch(pedido) and l["pid"] == int(pedido)), None)
    # o registro da LGPD: quem abriu, quando e, com um técnico escolhido no painel, de quem; antes de a página sair
    if not _registrar_acesso(srv, "abriu_mapa", sel["pid"] if sel else None, None, agora):
        return _tela({"erro": SEM_REGISTRO}, 503)
    avisos = [a for a in (aviso_piloto,) if a]
    if erro_coords:
        avisos.append(f"Sem as coordenadas das usinas neste servidor ({erro_coords}): ninguém conta como na usina, e o "
                      "parado fica fora do mapa.")
    admin = bool(session.get("admin"))
    todos = []
    if admin:
        todos = sorted(({"pid": pid, "nome": t["nome"], "equipe": b.nome_equipe.get(t["equipe_id"]) or "",
                         "no_piloto": pid in piloto} for pid, t in tecnicos.items()),
                       key=lambda t: (not t["no_piloto"], chave_texto(t["nome"])))
    return _tela({
        "linhas": linhas, "grupos": _grupos(linhas), "resumo": _resumo(linhas), "mapa": mapa, "sel": sel,
        "nome_de": {l["pid"]: l for l in linhas}, "nomes_usina": nomes_usina,
        "opcoes_rota": sorted(((uid, nomes_usina.get(uid) or f"Usina {uid}") for uid in coords),
                              key=lambda x: chave_texto(x[1])),
        "filtro": filtro,
        "avisos": avisos, "admin": admin, "todos": todos, "no_piloto": sum(1 for t in todos if t["no_piloto"]),
        "piloto_msg": PILOTO_MSG.get(str(request.args.get("piloto") or "")),
        "agora": f"{agora.astimezone(_BRT):%H:%M}"})


def _de_outro_site_na_navegacao() -> bool:
    """A navegação que veio de OUTRO site (Sec-Fetch-Site `cross-site`, ou `same-site`: todo subdomínio de gridco.com.br
    é same-site). O botão da tela manda `same-origin`; o endereço digitado ou o favorito, `none`. Sem isto, uma página
    de fora abriria a rota em nome de quem está logado (a posição iria ao Google e o registro diria que ele abriu)."""
    return (request.headers.get("Sec-Fetch-Site") or "").strip().lower() in ("cross-site", "same-site")


@bp.route("/equipe/rota", endpoint="equipe_rota")
def equipe_rota():
    """O Abrir rota: `?tecnico=<pessoa_id>&usina=<usina_id>` -> 302 para o Google Maps, do último ponto do técnico até a
    usina. Só para quem vê o mapa, e só quando a situação dá rota (`situacao.rota`): parado fora de usina, sem
    permissão e sem posição respondem 404. O registro vem ANTES do redirecionamento: a coordenada sai do servidor
    nesta hora."""
    if _de_outro_site_na_navegacao():
        abort(403)
    quem = _quem_ve()
    if not quem["pode"]:
        return _texto(403, quem["aviso"])
    srv, aviso = _servico_da_tela()
    if srv is None:
        return _texto(503, aviso)
    agora = S._agora()
    pedido_t = str(request.args.get("tecnico") or "").strip()
    pedido_u = str(request.args.get("usina") or "").strip()
    coords, _erro = MR.coordenadas()
    destino = coords.get(pedido_u) if _ID.fullmatch(pedido_u) else None
    if not _ID.fullmatch(pedido_t) or destino is None:
        return _texto(404, NAO_HA_ROTA)
    pid = int(pedido_t)
    try:
        _b, tecnicos, piloto, _aviso = _equipe(srv, agora)
    except Exception as e:      # noqa: BLE001
        _log.warning("equipe: não consegui ler o cadastro para a rota (%s)", type(e).__name__)
        return _texto(503, "Não consegui ler o cadastro do Nexus agora; tente de novo em instantes.")
    if pid not in tecnicos or pid not in piloto:
        return _texto(404, NAO_HA_ROTA)
    est = srv.estado_de(pid, agora)
    if not SI.situacao(est, coords, agora)["rota"]:
        return _texto(404, NAO_HA_ROTA)
    u = est["ultimo"]
    url = SI.url_da_rota((u["lat"], u["lon"]), destino[:2])
    if not _registrar_acesso(srv, "abriu_rota", pid, int(pedido_u), agora):
        return _texto(503, SEM_REGISTRO)            # sem a trilha, a posição não sai do servidor
    r = redirect(url, code=302)
    r.headers["Cache-Control"] = "no-store"
    # o Google não recebe o endereço do Nexus (com o técnico e a usina) como origem do clique
    r.headers["Referrer-Policy"] = "no-referrer"
    return r


@bp.route("/equipe/piloto", methods=["POST"], endpoint="equipe_piloto")
def equipe_piloto():
    """Pôr um técnico de campo no piloto da coleta ou tirá-lo (`pessoa_id`, `no_piloto` = sim | nao). Só o
    administrador; só técnico de campo ativo do cadastro. Grava no livro (`piloto.decidir`) e a cópia do piloto cai,
    para a decisão valer já no mapa e no próximo envio do celular."""
    from ..moldura import _de_outro_site
    if _de_outro_site():
        abort(403)
    if not session.get("admin"):
        abort(403)
    pedido = str(request.form.get("pessoa_id") or "").strip()
    quer = str(request.form.get("no_piloto") or "").strip().lower()
    if not _ID.fullmatch(pedido) or quer not in ("sim", "nao"):
        abort(400)
    pid = int(pedido)
    srv, aviso = _servico_da_tela()
    if srv is None:
        return _texto(503, aviso)
    try:
        from ...pcm.tecnicos_usina import pessoas_de_campo
        tecnicos = pessoas_de_campo(visao._Base(), current_app.config)
    except Exception as e:      # noqa: BLE001
        _log.warning("equipe: não consegui ler o cadastro para o piloto (%s)", type(e).__name__)
        return redirect(url_for("torre_campo.equipe", piloto="erro"), code=303)
    if pid not in tecnicos:
        abort(400)              # só técnico de campo ativo é coletado: pôr outro no piloto não teria efeito
    email, _nome = _usuario()
    quem = codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) or ""
    try:
        PI.decidir(current_app.config, pid, quer == "sim", quem, S._agora())
        resultado = "ok"
    except PI.Recusada:
        resultado = "sem_token"
    except Exception as e:      # noqa: BLE001 — banco fora, leitura incompleta: nada gravado
        _log.warning("equipe: a decisão do piloto não foi gravada (%s)", type(e).__name__)
        resultado = "erro"
    finally:
        srv.esquecer_piloto()   # gravou (ou pode ter gravado antes de a conferência falhar): o próximo pedido relê
    if resultado == "ok":
        _log.info("equipe: a pessoa %s %s o piloto (decisão de um administrador)", pid,
                  "entrou no" if quer == "sim" else "saiu do")
    return redirect(url_for("torre_campo.equipe", piloto=resultado), code=303)
