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

O Ver percurso (10/11/2026, Levi pela sessão Nexus Field: "mostra só o ponto de localização e caso a pessoa queira,
consegue ver o percurso que aquela pessoa fez em determinado período de dias e horas!"): `GET /t/campo/equipe?tecnico=
<id>&de=<AAAA-MM-DDTHH:MM>&ate=<...>` (horas de Brasília, dentro dos 7 dias) desenha no mapa a linha do percurso, com os
pontos em ordem e a hora de cada um, projetados no servidor (`situacao.desenho_percurso`). Cada abertura do percurso vai
ao registro da LGPD como `abriu_percurso`, com o período, antes de a página sair.
"""
import json
import logging
import re
from collections import Counter
from datetime import datetime, time, timedelta, timezone

from flask import Response, abort, current_app, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from ...auth import chaves, microsoft, setor_telas
from ...cadastro import setor_ids as SID
from ...cadastro.servico import chave_texto
from ...campo import equipe as E
from ...campo import mapa_responsaveis as MR
from ...campo import visao
from ...campo.equipe import celulares as CE
from ...campo.equipe import eventos as EV
from ...campo.equipe import gravador as G
from ...campo.equipe import mapa_base as MB
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
        raise _Recusa(503, "o Mapa de equipe não grava nesta máquina (Base → Chaves → Nexus: NEXUS_EQUIPE_GRAVA = 1, "
                           "só no servidor que grava): nada é recebido aqui")
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
NAO_HA_ROTA = ("A rota não abre para este técnico agora: ela só sai do ponto de hoje (não de quem está sem permissão "
               "no celular nem do ponto de outro dia). Volte ao Mapa de equipe e atualize a página.")
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
    return b, _com_teste(b, tecnicos, piloto), piloto or frozenset(), aviso


def _com_teste(b, tecnicos: dict, piloto) -> dict:
    """Os técnicos de campo e as pessoas de teste do piloto (09/11/2026, pedido do Levi pela sessão Nexus Field: testar
    com o próprio usuário, que não é técnico de campo). A de teste entra com o nome do cadastro, sem equipe e com a marca
    `teste`: o painel a mostra marcada e o resumo dos técnicos não a conta. O vínculo dela no cadastro não muda."""
    teste = set(getattr(piloto, "teste", ()) or ()) - set(tecnicos)
    if not teste:
        return tecnicos
    nomes = b.nomes(teste)
    out = dict(tecnicos)
    for pid in teste:
        out[pid] = {"nome": nomes.get(pid) or f"Pessoa {pid}", "equipe_id": None, "cargo": "", "hmac": "", "teste": True}
    return out


def _pessoas_para_teste(b, tecnicos: dict) -> list:
    """As pessoas do cadastro que o administrador pode pôr no piloto como teste: as que não são técnicas de campo (essas
    entram pelo caminho de sempre) nem estão excluídas, pelo nome padrão. Escolhe-se pelo pessoa_id; nome nenhum vai ao
    livro do piloto."""
    ids = set()
    for p in b.pessoas:
        pid = visao.D._id(p.get("pessoa_id"))
        if pid and pid not in tecnicos and str(p.get("excluido") or "").strip().lower() != "sim":
            ids.add(pid)
    nomes = b.nomes(ids)
    return sorted(((pid, nomes.get(pid) or f"Pessoa {pid}") for pid in ids), key=lambda x: chave_texto(x[1]))


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


def _registrar_acesso(srv, acao, alvo, usina_id, agora, periodo=None) -> bool:
    """A linha da LGPD, no jornal em disco ANTES de o mapa, a rota ou o percurso abrir (o percurso leva o `periodo`
    visto). O disco que falha = False: a tela não abre sem a trilha."""
    quem_pid, quem_hmac = _quem_abriu(srv)
    try:
        srv.registro.acrescentar(acao, quem_pid, quem_hmac, alvo, usina_id, agora, periodo=periodo)
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
    """O lugar do parado fora de usina: "Cidade/UF" pela malha do IBGE; sem a cidade, só a UF."""
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
    """As linhas do painel (uma por técnico do piloto, pelo nome) e os pontos do mapa [(pessoa_id, lat, lon, tom,
    velho)]: desde 10/11/2026 a última posição de todo técnico que tem ponto nos 7 dias, também o parado fora de usina e
    o de outro dia (`velho`). A coordenada fica aqui, na memória do processo: a página recebe o x/y do `desenho`."""
    linhas, pontos, cidade = [], [], _cidade_de()
    for pid in sorted((p for p in tecnicos if p in piloto), key=lambda p: chave_texto(tecnicos[p]["nome"])):
        t = tecnicos[pid]
        est = srv.estado_de(pid, agora)
        s = SI.situacao(est, coords, agora, cidade=cidade)
        perto = s["usina_perto"]
        linhas.append({
            "pid": pid, "nome": t["nome"], "equipe": b.nome_equipe.get(t["equipe_id"]) or "", "s": s,
            "teste": bool(t.get("teste")),
            "hora": _hora(s["ultima"], agora), "onde": _onde(s),
            "perto": SI.texto_perto(perto[1], nomes_usina.get(perto[0]) or f"usina {perto[0]}") if perto else "",
            "desde": _hora(s["desde"], agora) if s["chave"] == "sem_permissao" else ""})
        if s["no_mapa"]:
            u = est["ultimo"]
            pontos.append((pid, u["lat"], u["lon"], s["tom"], s["velho"]))
    return linhas, pontos


# os grupos do painel sem técnico escolhido, na ordem do resumo (quem pede atenção primeiro); o título no plural
GRUPOS = (("sem_permissao", "Sem permissão no celular"), ("sem_sinal", "Sem sinal"),
          ("deslocamento", "Em deslocamento"), ("na_usina", "Na usina"), ("fora_usina", "Parados fora de usina"),
          ("sem_posicao", "Sem posição hoje"))


def _grupos(linhas: list) -> list:
    """O painel sem técnico escolhido: um grupo por situação, só os que têm alguém (10/11/2026: todo técnico com ponto
    está no mapa, e o grupo "No mapa" deixou de separar quem está e quem não está)."""
    return [(chave, titulo, lista) for chave, titulo in GRUPOS
            if (lista := [l for l in linhas if l["s"]["chave"] == chave])]


def _resumo(linhas: list) -> list:
    # a pessoa de teste (09/11/2026) fica fora da conta dos técnicos: aparece no painel, com a marca, mas não no resumo
    n = Counter(l["s"]["chave"] for l in linhas if not l.get("teste"))
    return [(n[k], um if n[k] == 1 else varios, SI.TOM[k]) for k, um, varios in RESUMO if n[k]]


# ── o Ver percurso (10/11/2026) ──────────────────────────────────────────────────────────────────────────────────
_PERIODO = "%Y-%m-%dT%H:%M"         # o valor do <input type="datetime-local">, na hora de Brasília
PERIODO_TORTO = "Período fora do formato: escolha o dia e a hora do início e do fim."
PERIODO_AO_CONTRARIO = "O fim do período tem de ser depois do início."


def _ler_hora(texto: str):
    texto = str(texto or "").strip()[:19]
    for formato in (_PERIODO, _PERIODO + ":%S"):        # há navegador que manda os segundos
        try:
            return datetime.strptime(texto, formato).replace(tzinfo=_BRT).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _periodo(agora) -> dict | None:
    """O período pedido (`?de=&ate=`, horas de Brasília): None sem pedido; {"erro"} torto; {"de", "ate", "aviso"} em UTC.
    Fica dentro da guarda: o início antes dos 7 dias vai para o limite (e a tela diz), o fim depois de agora vira agora."""
    de_txt, ate_txt = request.args.get("de"), request.args.get("ate")
    if not str(de_txt or "").strip() and not str(ate_txt or "").strip():
        return None
    de, ate = _ler_hora(de_txt), _ler_hora(ate_txt)
    if de is None or ate is None:
        return {"erro": PERIODO_TORTO}
    limite, aviso = agora - timedelta(days=E.GUARDA_PONTOS_DIAS), ""
    if de < limite:
        de = limite
        aviso = (f"O percurso guarda só os últimos {E.GUARDA_PONTOS_DIAS} dias: o início foi para "
                 f"{de.astimezone(_BRT):%d/%m às %H:%M}.")
    ate = min(ate, agora)
    if ate <= de:
        return {"erro": PERIODO_AO_CONTRARIO}
    return {"de": de, "ate": ate, "aviso": aviso}


def _percurso_do_dia(linha: dict, agora) -> dict:
    """O período que o clique no ponto do técnico abre (Levi, 10/11/2026: "Quero que ao clicar na pessoa no mapa já
    apareça o percurso"): o dia da última posição dele, das 6h às 22h (ou até agora), nos valores do formulário
    ({"de", "ate"}). Sem posição, ou com menos de um minuto de período (o 1º ponto das 6h): {} (abre só a gaveta)."""
    ultima = linha["s"]["ultima"]
    if ultima is None:
        return {}
    f = _form_do_percurso(linha, agora, None)
    return {"de": f["de"], "ate": f["ate"]} if f["ate"] > f["de"] else {}


def _form_do_percurso(sel: dict, agora, pedido: dict | None) -> dict:
    """Os valores do formulário do Ver percurso: o período aberto, ou o dia da última posição do técnico das 6h até as
    22h (ou até agora), dentro do limite dos 7 dias."""
    minimo = agora - timedelta(days=E.GUARDA_PONTOS_DIAS)
    if pedido and "de" in pedido:
        de, ate = pedido["de"], pedido["ate"]
    else:
        dia = (sel["s"]["ultima"] or agora).astimezone(_BRT).date()
        de = max(datetime.combine(dia, time(E.JANELA_H[0]), tzinfo=_BRT), minimo)
        ate = min(datetime.combine(dia, time(E.JANELA_H[1]), tzinfo=_BRT), agora)
    def fmt(x):
        return x.astimezone(_BRT).strftime(_PERIODO)
    return {"de": fmt(de), "ate": fmt(ate), "min": fmt(minimo), "max": fmt(agora)}


def _cidade_do_ponto():
    """A cidade de um ponto (lat, lon) pela malha do IBGE no disco, ou None: a dos eventos e a do percurso."""
    cidade_uf = _cidade_de()

    def cidade(lat, lon):
        uf = SI.uf_do_ponto(lat, lon)
        return cidade_uf(lat, lon, uf) if uf and cidade_uf is not None else None
    return cidade


def _percurso(srv, sel, pedido, coords, nomes_usina, agora, *, com_coordenada=False) -> dict:
    """O percurso aberto: {"desenho", "itens", "resumo", "vazio", "vista"} (a trilha com lat/lon fica aqui; a `vista` é
    o recorte do desenho, para o clima, e não vai à página). O fundo é a malha de
    municípios do IBGE que já está no disco (`municipios.na_caixa`, nunca espera o IBGE)."""
    trilha = srv.percurso(sel["pid"], pedido["de"], pedido["ate"], agora)
    if not trilha:
        return {"desenho": None, "itens": [], "resumo": "", "vazio": f"Nenhum ponto de {sel['nome']} neste período."}
    from ...cadastro.ligacoes import pasta_dados
    lons, lats = [p["lon"] for p in trilha], [p["lat"] for p in trilha]
    # os municípios do fundo: os da caixa do percurso e os vizinhos (a folga é metade do lado, no mínimo ~30 km), para a
    # pessoa aproximar e ver as cidades em volta; o mapa inteiro com todos os municípios pesaria a página
    folga = max(0.3, (max(lons) - min(lons)) / 2, (max(lats) - min(lats)) / 2)
    caixa = (min(lons) - folga, min(lats) - folga, max(lons) + folga, max(lats) + folga)
    try:
        municipios = MU.na_caixa(caixa, pasta=pasta_dados(current_app.config))
    except Exception as e:      # noqa: BLE001 — o fundo é enfeite: sem ele, o percurso vale
        _log.warning("equipe: os municípios do percurso não abriram (%s)", type(e).__name__)
        municipios = []
    vista = None
    try:
        desenho = SI.desenho_percurso(coords, trilha, municipios)
        vista = SI.vista_do_mapa(coords, [(q["lat"], q["lon"]) for q in trilha])     # a mesma do desenho: a do clima
    except ValueError as e:     # o contorno do IBGE que não abre: a lista do painel continua valendo
        _log.warning("equipe: o desenho do percurso não abriu (%s)", type(e).__name__)
        desenho = {"viewbox": None, "marcas": [{"n": i, "hora": _hora(SI._instante(p["instante"]), agora),
                                                "mov": bool(p.get("mov"))} for i, p in enumerate(trilha, 1)]}
    n = len(trilha)
    marcas = desenho["marcas"]
    resumo = (f"{n} ponto{'s' if n != 1 else ''} · de {marcas[0]['hora']} a {marcas[-1]['hora']} · "
              f"{SI.km_texto(SI.distancia_km(trilha))} em linha reta entre os pontos")
    itens = EV.do_percurso(trilha, coords, nomes_usina, cidade=_cidade_do_ponto(), com_ponto=com_coordenada)
    out = {"desenho": desenho if desenho.get("viewbox") else None, "resumo": resumo, "vazio": "",
           "vista": vista if desenho.get("viewbox") else None, "itens": itens}
    if com_coordenada:
        # o mapa de verdade (11/11/2026): a trilha e os marcos em (lon, lat), para o navegador desenhar
        ordem = sorted(trilha, key=lambda q: q["instante"])
        lon = [q["lon"] for q in ordem]
        lat = [q["lat"] for q in ordem]
        out["js"] = {"linha": [_lonlat(q["lat"], q["lon"]) for q in ordem],
                     # o instante de cada ponto (segundos), para a reprodução do percurso no mapa (12/11/2026)
                     "pontos": [{"c": _lonlat(q["lat"], q["lon"]), "hora": m["hora"], "mov": bool(q.get("mov")),
                                 "t": int(SI._instante(q["instante"]).timestamp())} for q, m in zip(ordem, marcas)],
                     "marcos": [{"c": _lonlat(ordem[i["ponto"]]["lat"], ordem[i["ponto"]]["lon"]), "tipo": i["tipo"],
                                 "texto": i["texto"], "hora": i["de"] if i["de"] == i["ate"] else f"{i['de']} a {i['ate']}"}
                                for i in itens],
                     "caixa": [round(min(lon), 5), round(min(lat), 5), round(max(lon), 5), round(max(lat), 5)]}
    return out


def _programa_do_dia(b, linhas: list, agora) -> dict:
    """{pessoa_id: os blocos de HOJE da programação do PCM da equipe dele, na ordem da hora} (10/11/2026, Levi: "Pode
    subir o destino do técnico"). A fonte é a das telas do PCM: o `banco_dados.json` do App (`pcm.fonte.ler`, cópia de
    5 min), a semana ativa, e só se ela for a semana de hoje (a da virada ainda não publicada não vale). A equipe do
    bloco é o `cluster` (o nome da aba do PCM, o mesmo da equipe do cadastro); a usina, o nome do Fracttal, ligado ao
    `usina_id` pelo de-para do cadastro (`tecnicos_usina._fracttal`). Sábado, domingo ou a fonte que não abre: vazio
    (o evento sai sem destino; nada inventado)."""
    from ...pcm import fonte as PF
    from ...pcm import semana as PS
    from ...pcm.tecnicos_usina import _fracttal
    hoje = agora.astimezone(_BRT).date()
    if hoje.weekday() >= len(PS.DIAS):
        return {}
    dia = PS.DIAS[hoje.weekday()]
    try:
        leitura = PF.ler(current_app.config)
        sem = PS.achar(leitura.dados) if leitura.dados else None
        ano, num, _ = hoje.isocalendar()
        if not sem or str(sem.get("week")) != f"{ano}-W{num:02d}":
            return {}
        usina_de = {}
        for uid, nomes in _fracttal(b, do_app=None).items():
            for n in nomes:
                usina_de.setdefault(PS._norm(n), str(uid))
        por_equipe: dict = {}
        for r in sem.get("rows") or []:
            if PS.dia_curto(r.get("dia")) != dia:
                continue
            nome = " ".join(str(r.get("usina") or "").split())
            por_equipe.setdefault(PS._norm(r.get("cluster")), []).append(
                {"usina_id": usina_de.get(PS._norm(nome)), "usina": nome, "h_ini": str(r.get("h_ini") or ""),
                 "feita": PS.situacao(r) == "feita"})
    except Exception as e:      # noqa: BLE001 — a programação é o destino: sem ela, o evento segue sem
        _log.warning("equipe: não consegui ler a programação do PCM (%s)", type(e).__name__)
        return {}
    for blocos in por_equipe.values():
        blocos.sort(key=lambda x: x["h_ini"])
    return {l["pid"]: por_equipe.get(PS._norm(l["equipe"]), []) for l in linhas if l.get("equipe")}


def _destino_atual(eventos: list, pid) -> str:
    """O destino do técnico agora: a última saída de hoje com destino, se ele não chegou em usina depois dela
    ("Usina X · chegada prevista 13:40"). `eventos` do mais novo ao mais velho."""
    for e in eventos:
        if e["pessoa_id"] != pid:
            continue
        if e["tipo"] == "chegou":
            return ""
        if e["tipo"] == "saiu":
            if not e.get("destino"):
                return ""
            texto = e["destino"]
            if e.get("chegada_prevista"):
                prevista = datetime.strptime(e["chegada_prevista"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                texto += f" · chegada prevista {prevista.astimezone(_BRT):%H:%M}"
            return texto
    return ""


def _eventos_do_dia(srv, linhas: list, coords: dict, nomes_usina: dict, filtro: dict, agora, programas=None) -> list:
    """Os eventos de hoje dos técnicos que a tela mostra (no piloto e no filtro), do mais novo ao mais velho
    (`eventos.da_equipe`; 10/11/2026, Levi: "Quero que apareça tipo ocorrências"). Cada um ganha, só para a tela, o
    nome do técnico e o endereço do clique: o percurso do dia dele (o sem permissão, o painel dele), com o filtro."""
    hoje = agora.astimezone(_BRT).date()
    meia_noite = datetime.combine(hoje, time(0), tzinfo=_BRT)
    pontos = {l["pid"]: srv.percurso(l["pid"], meia_noite, agora, agora) for l in linhas}
    estados = {l["pid"]: srv.estado_de(l["pid"], agora) for l in linhas}
    cidade = _cidade_do_ponto()
    nome = {l["pid"]: l["nome"] for l in linhas}
    periodo = {"de": datetime.combine(hoje, time(E.JANELA_H[0]), tzinfo=_BRT).strftime(_PERIODO),
               "ate": agora.astimezone(_BRT).strftime(_PERIODO)}
    out = []
    for e in EV.da_equipe(pontos, coords, nomes_usina, agora, estados=estados, cidade=cidade, programas=programas):
        q = {"tecnico": e["pessoa_id"], **({} if e["tipo"] == "sem_permissao" else periodo), **filtro["q"]}
        out.append({**e, "nome": nome.get(e["pessoa_id"]) or f"Pessoa {e['pessoa_id']}", "q": q})
    return out


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


# o que diz qual tela está aberta: o botão Incluir clima troca só o clima e guarda o resto
_CHAVES_DA_TELA = ("ver", "tecnico", "de", "ate", "painel", "supervisor", "equipe")


def _com_clima() -> bool:
    return str(request.args.get("clima") or "").strip() == "1"


def _q_do_clima(ligado: bool) -> dict:
    """Os parâmetros do botão Incluir clima (o template monta o endereço pelo `url_for`): a mesma tela (o Usinas, o
    técnico, o percurso, o painel e o filtro abertos), com o clima trocado."""
    q = {k: str(request.args.get(k) or "").strip() for k in _CHAVES_DA_TELA}
    q = {k: v for k, v in q.items() if v and (k != "ver" or v == "usinas")}
    if not ligado:
        q["clima"] = "1"
    return q


def _tela(contexto: dict, status: int = 200):
    tela = TORRE.tela("equipe")
    clima = _com_clima()
    # o Incluir clima (11/11/2026): o botão, e o `clima=1` que o Técnicos | Usinas leva de um lado para o outro
    # o link para Base > Chaves no "falta a chave" do Satélite (12/11/2026): só o administrador cola a chave
    contexto = {"clima_on": clima, "q_clima": {"clima": "1"} if clima else {}, "q_botao_clima": _q_do_clima(clima),
                "link_chaves": bool(session.get("admin")), **contexto}
    r = current_app.make_response((render_template("campo/equipe.html", torre=TORRE, tela=tela, **contexto), status))
    r.headers["Cache-Control"] = "no-store"         # a posição de pessoas não fica na cópia do navegador nem de proxy
    return r


# ── o mapa de verdade (11/11/2026) ───────────────────────────────────────────────────────────────────────────────────
def _usa_mapa_base() -> bool:
    """O MapLibre sobre o mapa base do Brasil, quando o arquivo está no servidor (Base > Mapa base); sem ele, ou com
    `?mapa=desenho`, o desenho dos estados de antes."""
    return str(request.args.get("mapa") or "").strip() != "desenho" and MB.arquivo(current_app.config) is not None


def _lonlat(lat, lon) -> list:
    """[lon, lat] com 5 casas (~1 m): a ordem do GeoJSON e do MapLibre."""
    return [round(float(lon), 5), round(float(lat), 5)]


def _iniciais(nome: str) -> str:
    partes = [p for p in str(nome or "").split() if p]
    return "".join(p[0] for p in (partes[:1] + partes[-1:] if len(partes) > 1 else partes)).upper()


def _cos_por_usina(b):
    """A fotografia da Ronda COS de cada cliente do Andamento por usina, como Comando > Usinas a lê
    (`comando.usinas.cos_por_usina`, a cópia de 30 s por cliente): {"ocs", "lidas"}, ou None sem a fonte."""
    from ...comando import usinas as CU
    from ...cos import andamento as AND
    cfg = current_app.config
    if b is None or not AND.fonte(cfg).ligada:
        return None
    clientes, _erro = AND.clientes(cfg)
    leituras = [AND.ler(cfg, c) for c in clientes]
    return CU.cos_por_usina(leituras, lambda nome, codigo: b.lig.usina(nome or "", codigo or "")[0])


def _agora_por_usina(b, uids) -> dict:
    """O "Agora" de Comando > Usinas de cada usina (Levi, 12/11/2026: "Quero as cores das usinas de acordo com o tempo
    real, OS Abertas do setor COS, as regras estão em 'Comando > Usinas' pode pegar as cores de lá!"): a régua de lá
    (`comando.usinas.agora_pelo_cos`: religamento em campo = crítico, inversor = atenção, comunicação = sem comunicação,
    o que para a usina = crítico; sem ocorrência = normal; a usina que a fotografia não trouxe = sem leitura). {usina_id
    em texto: {"estado", "rotulo", "tom", "motivo"}}; sem a leitura do COS, {} (a usina fica sem cor, nunca "normal")."""
    from ...comando import usinas as CU
    try:
        cos = _cos_por_usina(b)
    except Exception:           # noqa: BLE001 — sem o COS, o mapa segue sem a cor de agora
        _log.exception("equipe: a fotografia do COS não abriu (a cor das usinas)")
        cos = None
    if cos is None:
        return {}
    ocs = {str(k): v for k, v in (cos.get("ocs") or {}).items()}
    lidas = {str(x) for x in cos.get("lidas") or ()}
    out = {}
    for uid in uids:
        a = CU.agora_pelo_cos(ocs.get(str(uid), []) if str(uid) in lidas else None)
        out[str(uid)] = {"estado": a["estado"], "rotulo": a["estado_rot"], "tom": a["estado_tom"], "motivo": a["detalhe"]}
    return out


URL_ESRI = ("https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}?token=")
CREDITO_ESRI = "Satélite: Esri, Maxar, Earthstar Geographics e a comunidade de usuários do GIS · Powered by Esri"


def _satelite() -> dict | None:
    """O satélite da Esri (12/11/2026, a escolha do Levi), com a chave de Base > Chaves; sem ela, sem o botão."""
    chave = chaves.valor("NEXUS_ESRI_CHAVE", current_app.config)
    return {"url": URL_ESRI + chave, "credito": CREDITO_ESRI} if chave else None


def _dados_do_mapa(modo, coords, nome_de_usina, onde_de_usina, *, linhas=(), pontos=(), sel=None, perc=None,
                   clima=None, b=None) -> dict:
    """O que o campo-mapa.js desenha (11/11/2026, o guia do Willian com o MapLibre): as usinas uma a uma (a coordenada do
    cadastro, a ocorrência aberta e, com o clima, o nível), os técnicos que o mapa mostra (o último ponto, a situação e o
    endereço do clique), o percurso aberto e o clima em coordenadas. A coordenada do técnico vai SÓ de quem está em
    `pontos` (o piloto, o filtro, com ponto nos 7 dias), e esta função só roda depois do registro da LGPD (Levi, 11/11/2026:
    "Pode trocar" a regra de antes, a página sem coordenada nenhuma)."""
    agora_de = _agora_por_usina(b, list(coords)) if coords else {}
    por_nivel = (clima or {}).get("por_id") or {}
    usinas = []
    for uid, (lat, lon, *_r) in coords.items():
        c = por_nivel.get(str(uid))
        usinas.append({"id": str(uid), "nome": nome_de_usina(uid), "onde": onde_de_usina(uid), "c": _lonlat(lat, lon),
                       "agora": agora_de.get(str(uid)), "nivel": c["nivel"] if c else None,
                       "rotulo": c["rotulo"] if c else "", "motivo": c["motivo_curto"] if c else ""})
    linha_de = {l["pid"]: l for l in linhas}
    tecnicos = []
    for pid, lat, lon, tom, velho in pontos:
        l = linha_de.get(pid)
        if l is None:
            continue
        tecnicos.append({"pid": pid, "nome": l["nome"], "ini": _iniciais(l["nome"]), "equipe": l["equipe"] or "",
                         "tom": tom, "rotulo": l["s"]["rotulo"], "velho": bool(velho), "hora": l["hora"],
                         "sel": bool(sel and sel["pid"] == pid), "c": _lonlat(lat, lon),
                         "url": url_for("torre_campo.equipe", **l["q_ponto"])})
    geo = ((clima or {}).get("m") or {}).get("geo")
    return {"modo": modo, "blocos": url_for("torre_campo.equipe_mapa_base"),
            "brasil": url_for("static", filename="clima/ibge-brasil-minima.geojson"),
            # as fontes dos rótulos: o endereço do static SEM o ?v= do controle de cache (ele cairia no meio do molde)
            "fontes": url_for("static", filename="mapa/fontes/FONTE/FAIXA.pbf").split("?")[0]
            .replace("FONTE", "{fontstack}").replace("FAIXA", "{range}"),
            "usinas": usinas, "tecnicos": tecnicos, "percurso": (perc or {}).get("js"), "clima": geo,
            "satelite": _satelite()}


# ── o clima por usina (o botão Incluir clima, 11/11/2026) ────────────────────────────────────────────────────────────
# a cor de cada nível do Mapa de risco nas etiquetas daqui (o semáforo do Nexus) e a ordem do desenho: quem pede ação
# por último, para ficar por cima
TOM_DO_NIVEL = {RISCO.A.AGIR: "critico", RISCO.A.ATENCAO: "alerta", RISCO.A.REGIAO: "info", RISCO.A.SEM_ALERTA: "ok",
                RISCO.NX: "neutro"}
CLIMA_FORA = "O clima não abriu agora (o motivo está no log do servidor); o mapa segue sem ele."


def _cadastro_do_clima() -> tuple:
    """(o cadastro das usinas do clima, None) ou (None, o porquê): o mesmo que o Mapa de risco lê (`usinas.do_app`)."""
    from ...performance.clima import usinas as CU
    try:
        return CU.do_app(), None
    except CU.SemCadastro as e:
        return None, str(e)
    except Exception:           # noqa: BLE001 — o arquivo do cadastro corrompido, por exemplo: a tela diz, e o log guarda
        _log.exception("equipe: o cadastro das usinas não abriu (clima)")
        return None, "o cadastro não abriu (o motivo está no log do servidor)."


def _clima(vista, cadastro, erro, geo=False) -> dict:
    """O clima POR USINA no desenho deste mapa (Levi, 11/11/2026: 'vai mostrar os climas os alertas, tanto por usina ou
    por técnico, por mais que mostre os técnicos os avisos tem que ser por usina'). É o modelo do Mapa de risco da
    Performance (`clima.mapa.montar`: as mesmas fontes, o mesmo cache, a mesma regra de nível), pedido na `vista` daqui:
    regra nenhuma copiada. A camada de fundo é a dos avisos (as de calor nem são lidas). Devolve {"m" (o modelo), "por_id"
    {usina_id: a linha da usina, com o `tom` da etiqueta}, "urgentes" (Agir agora e Atenção, quem pede ação primeiro),
    "acompanhar" (o risco na região: o painel as recolhe), "contagem" [(nível, rótulo, tom, quantas)], "avisos" e "focos"
    (as camadas lidas, ou None)}. Sem a vista (não há mapa), o modelo sai no Brasil inteiro e só o painel o usa."""
    m = RISCO.montar(current_app.config, cadastro=cadastro, erro_cadastro=erro, vista_propria=vista, fundo="avisos",
                     ver=frozenset({"usinas", "focos"}), geo=geo)
    rotulo = {**RISCO.A.ROTULO_NIVEL, RISCO.A.SEM_ALERTA: m["rotulo_sem"], RISCO.NX: RISCO.ROTULO_NX}
    linhas = [{**u, "tom": TOM_DO_NIVEL[u["nivel"]]} for u in m["tabela"]]

    def lida(camada):
        return camada if vista is not None and camada and camada.get("estado") == "ok" else None
    return {"m": m, "por_id": {str(u["id"]): u for u in linhas},
            "urgentes": [u for u in linhas if u["nivel"] in (RISCO.A.AGIR, RISCO.A.ATENCAO)],
            "acompanhar": [u for u in linhas if u["nivel"] == RISCO.A.REGIAO],
            "contagem": [(n, rotulo[n], TOM_DO_NIVEL[n], m["contagem"][n]) for n in RISCO.NIVEIS if m["contagem"][n]],
            "avisos": lida(m["camada_avisos"]), "focos": lida(m["camada_focos"])}


def _clima_no_desenho(desenho: dict | None, clima: dict | None) -> None:
    """Com o clima, a usina que pede ação é desenhada por último (por cima), como no Mapa de risco."""
    if desenho and clima:
        nivel = {uid: u["nivel"] for uid, u in clima["por_id"].items()}
        desenho["usinas"] = sorted(desenho["usinas"],
                                   key=lambda u: RISCO.ORDEM_DE_DESENHO.get(nivel.get(str(u["usina_id"])), 0))


def _tela_usinas(com_clima: bool):
    """O botão Usinas (Levi, 11/11/2026: "esse botão usinas poderia mostrar só as usinas no mapa"): o MESMO mapa do
    Técnicos, só com as usinas em operação do cadastro (em destaque, com o nome na dica) e a lista delas ao lado. De
    08/11 a 10/11/2026 este botão trazia a tela inteira do Mapa de risco da Performance para dentro desta; o clima
    passou ao botão Incluir clima, que vale aqui e no Técnicos (`_clima`). Nada de técnico: o serviço das posições nem
    sobe, e a abertura não grava "abriu_mapa" na trilha da LGPD (não há dado pessoal). Quem vê é o mesmo do Técnicos
    (`_quem_ve`, conferido antes). Sem o clima pedido, a página nem vai às fontes do clima."""
    cad, erro = _cadastro_do_clima()
    do_cadastro = cad.usinas if cad else []
    lista = sorted(({"id": str(u.id), "nome": u.nome, "onde": f"{u.cliente} · {u.uf}" if u.uf else u.cliente}
                    for u in do_cadastro), key=lambda u: chave_texto(u["nome"]))
    coords = {str(u.id): (u.lat, u.lon, u.uf) for u in do_cadastro}
    vista, avisos = None, []
    try:
        mapa = SI.desenho(coords, [])
        vista = SI.vista_do_mapa(coords, []) if coords else None
    except ValueError as e:     # o contorno do IBGE que não abre: a lista continua valendo
        _log.warning("equipe: o contorno dos estados não abriu (%s)", type(e).__name__)
        mapa = {"viewbox": None, "ufs": [], "usinas": [], "pontos": []}
    clima, ml = None, _usa_mapa_base()
    if com_clima:
        try:
            clima = _clima(None if ml else vista, cad, erro, geo=ml)
            _clima_no_desenho(mapa, clima)
        except Exception:       # noqa: BLE001 — o clima é uma camada a mais: sem ele, o mapa das usinas vale
            _log.exception("equipe: o clima não abriu (usinas)")
            avisos.append(CLIMA_FORA)
    usina_de = {u["id"]: u for u in lista}
    mapa_js = None
    if ml:
        try:
            b = visao._Base()
        except Exception:       # noqa: BLE001 — sem o cadastro, as usinas seguem sem a cor do COS
            b = None
        mapa_js = _dados_do_mapa("usinas", coords, lambda uid: usina_de[str(uid)]["nome"],
                                 lambda uid: usina_de[str(uid)]["onde"], clima=clima, b=b)
    return _tela({"ver": "usinas", "mapa": mapa, "usinas_lista": lista, "usina_de": usina_de,
                  "erro_usinas": erro, "clima": clima, "avisos": avisos, "perc": None, "sel": None,
                  "painel_ev": False, "admin": False, "piloto_msg": None, "mapa_js": mapa_js})


@bp.route("/equipe", endpoint="equipe")
def equipe():
    """O mapa: os técnicos do piloto com a situação de cada um, o painel ao lado e, para o administrador, o piloto. Com
    `?ver=usinas`, só as usinas (`_tela_usinas`); com `?clima=1`, o clima por usina por cima (`_clima`)."""
    quem = _quem_ve()
    if not quem["pode"]:
        return _tela({"recusa": quem["aviso"]}, 403)
    com_clima = _com_clima()
    if str(request.args.get("ver") or "").strip() == "usinas":
        return _tela_usinas(com_clima)
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
    # o `q` vai em todo link da tela; o clima (11/11/2026) vai junto, e o `tem` diz se há filtro de técnico de verdade
    filtro["tem"] = bool(filtro["q"])
    if com_clima:
        filtro["q"] = {**filtro["q"], "clima": "1"}
    # o filtro vale para tudo o que mostra técnico: os pontos, as listas, o resumo e o painel do escolhido (que sai
    # das linhas). O controle do piloto, não: é quem o administrador põe e tira da coleta, filtro nenhum o esconde
    vistos = {pid: t for pid, t in tecnicos.items() if _no_filtro(b, t, filtro)}
    linhas, pontos = _linhas(srv, b, vistos, piloto, coords, nomes_usina, agora)
    # o endereço do clique no ponto de cada um: o percurso do dia da última posição, com o filtro da tela
    for l in linhas:
        l["q_ponto"] = {"tecnico": l["pid"], **_percurso_do_dia(l, agora), **filtro["q"]}
    try:
        mapa = SI.desenho(coords, pontos)
    except ValueError as e:     # o contorno do IBGE que não abre: a lista continua valendo
        _log.warning("equipe: o contorno dos estados não abriu (%s)", type(e).__name__)
        mapa = {"viewbox": None, "ufs": [], "usinas": [], "pontos": []}
    pedido = str(request.args.get("tecnico") or "").strip()
    sel = next((l for l in linhas if _ID.fullmatch(pedido) and l["pid"] == int(pedido)), None)
    # o Ver percurso (10/11/2026): só do técnico que o painel abre; o período torto é dito e o painel de sempre abre
    periodo = _periodo(agora) if sel else None
    perc, ml = None, _usa_mapa_base()
    if periodo and "de" in periodo:
        # o registro da LGPD do percurso, com o período, ANTES de a trilha ser lida e a página sair
        if not _registrar_acesso(srv, "abriu_percurso", sel["pid"], None, agora, (periodo["de"], periodo["ate"])):
            return _tela({"erro": SEM_REGISTRO}, 503)
        perc = _percurso(srv, sel, periodo, coords, nomes_usina, agora, com_coordenada=ml)
        perc["aviso"] = periodo["aviso"]
    # o registro da LGPD: quem abriu, quando e, com um técnico escolhido no painel, de quem; antes de a página sair
    elif not _registrar_acesso(srv, "abriu_mapa", sel["pid"] if sel else None, None, agora):
        return _tela({"erro": SEM_REGISTRO}, 503)
    # os eventos do dia (10/11/2026), com o destino da programação do PCM: o painel ao lado do mapa os mostra quando
    # ninguém está escolhido e não se pediu a lista de técnicos (`?painel=tecnicos`, o botão Técnico e Rotas); a gaveta
    # do escolhido usa o destino dele
    eventos = _eventos_do_dia(srv, linhas, coords, nomes_usina, filtro, agora, _programa_do_dia(b, linhas, agora))
    painel = "tecnicos" if str(request.args.get("painel") or "").strip() == "tecnicos" else "eventos"
    avisos = [a for a in (aviso_piloto,) if a]
    # o clima por usina (11/11/2026), na vista do desenho que a página mostra: a do percurso aberto, ou a do mapa
    clima = None
    if com_clima:
        try:
            vista = perc.get("vista") if perc and perc.get("desenho") else None
            if vista is None and not (perc and perc.get("desenho")) and mapa["viewbox"]:
                vista = SI.vista_do_mapa(coords, [(q[1], q[2]) for q in pontos])
            # o mapa de verdade desenha o clima no navegador, em coordenadas: o modelo sai no Brasil inteiro
            clima = _clima(None if ml else vista, *_cadastro_do_clima(), geo=ml)
            _clima_no_desenho(perc.get("desenho") if perc else None, clima)
            _clima_no_desenho(mapa, clima)
        except Exception:       # noqa: BLE001 — o clima é uma camada a mais: sem ele, o mapa dos técnicos vale
            _log.exception("equipe: o clima não abriu (técnicos)")
            avisos.append(CLIMA_FORA)
    if erro_coords:
        avisos.append(f"Sem as coordenadas das usinas neste servidor ({erro_coords}): ninguém conta como na usina, e o "
                      "parado fica fora do mapa.")
    # os dados do mapa de verdade: depois do registro da LGPD, só de quem o mapa mostra
    mapa_js = (_dados_do_mapa("tecnicos", coords, lambda uid: nomes_usina.get(str(uid)) or f"Usina {uid}",
                              lambda uid: "Usina", linhas=linhas, pontos=pontos, sel=sel, perc=perc, clima=clima,
                              b=b)
               if ml else None)
    admin = bool(session.get("admin"))
    todos = []
    if admin:
        # o "Celular pronto" (10/11/2026): de quem está no piloto, pelos ajustes que o celular manda
        com_chave = srv.chaveiro.pessoas()
        todos = sorted(({"pid": pid, "nome": t["nome"], "equipe": b.nome_equipe.get(t["equipe_id"]) or "",
                         "no_piloto": pid in piloto, "teste": bool(t.get("teste")),
                         "celular": CE.situacao(pid in com_chave, srv.celulares.de(pid)) if pid in piloto else None}
                        for pid, t in tecnicos.items()),
                       key=lambda t: (not t["no_piloto"], chave_texto(t["nome"])))
    return _tela({
        "linhas": linhas, "grupos": _grupos(linhas), "resumo": _resumo(linhas), "mapa": mapa, "sel": sel,
        "nome_de": {l["pid"]: l for l in linhas}, "nomes_usina": nomes_usina,
        # a dica da usina no mapa (o nome), e o clima por usina quando pedido
        "usina_de": {uid: {"nome": nomes_usina.get(uid) or f"Usina {uid}", "onde": "Usina"} for uid in coords},
        "clima": clima,
        "opcoes_rota": sorted(((uid, nomes_usina.get(uid) or f"Usina {uid}") for uid in coords),
                              key=lambda x: chave_texto(x[1])),
        "filtro": filtro,
        # o Ver percurso: o percurso aberto (ou None), o erro do período e os valores do formulário do técnico
        "perc": perc, "erro_periodo": periodo.get("erro", "") if periodo else "",
        "eventos": eventos, "eventos_resumo": EV.resumo(eventos), "painel_ev": sel is None and painel == "eventos",
        "destino_sel": _destino_atual(eventos, sel["pid"]) if sel else "",
        "form_perc": _form_do_percurso(sel, agora, periodo) if sel else None,
        "avisos": avisos, "admin": admin, "todos": todos,
        "no_piloto": sum(1 for t in todos if t["no_piloto"] and not t["teste"]),
        # quem o administrador pode pôr no piloto como pessoa de teste (09/11/2026): só para ele
        "pessoas_teste": _pessoas_para_teste(b, tecnicos) if admin else [],
        # se a gravação está ligada nesta máquina (09/11/2026, a chave da tela Base → Chaves): só para o administrador
        "grava": G.ativo(current_app.config) if admin else None,
        "piloto_msg": PILOTO_MSG.get(str(request.args.get("piloto") or "")),
        "mapa_js": mapa_js,
        "agora": f"{agora.astimezone(_BRT):%H:%M}"})


@bp.route("/equipe/mapa-base.pmtiles", endpoint="equipe_mapa_base")
def equipe_mapa_base():
    """Os blocos do mapa base do Brasil (11/11/2026), lidos por pedaço (HTTP Range) pelo MapLibre do Mapa de equipe: o
    mapa de ruas é nosso, servido só a quem vê o Mapa de equipe (o guia do Willian, LGPD item 2: nenhum bloco de
    terceiro vê a região que o COS está olhando). Sem o arquivo (antes da subida em Base > Mapa base), 404 e o mapa usa
    o desenho dos estados."""
    if not _quem_ve()["pode"]:
        abort(403)
    p = MB.arquivo(current_app.config)
    if p is None:
        return _texto(404, "O mapa base não está neste servidor: suba o arquivo em Base > Mapa base.")
    r = send_file(p, mimetype="application/octet-stream", conditional=True, etag=True, max_age=3600)
    r.headers["Cache-Control"] = "private, max-age=3600"
    return r


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
    # a pessoa de teste (09/11/2026): marcada no livro do piloto, entra sem ser técnica de campo
    teste = str(request.form.get("teste") or "").strip() == "1"
    if not _ID.fullmatch(pedido) or quer not in ("sim", "nao"):
        abort(400)
    pid = int(pedido)
    srv, aviso = _servico_da_tela()
    if srv is None:
        return _texto(503, aviso)
    try:
        from ...pcm.tecnicos_usina import pessoas_de_campo
        b = visao._Base()
        tecnicos = pessoas_de_campo(b, current_app.config)
    except Exception as e:      # noqa: BLE001
        _log.warning("equipe: não consegui ler o cadastro para o piloto (%s)", type(e).__name__)
        return redirect(url_for("torre_campo.equipe", piloto="erro"), code=303)
    if teste:
        # qualquer pessoa do cadastro que exista e não esteja excluída; o técnico de campo segue sem a marca
        if pid in tecnicos or pid not in {i for i, _n in _pessoas_para_teste(b, tecnicos)}:
            abort(400)
    elif pid not in tecnicos:
        abort(400)              # só técnico de campo ativo é coletado: pôr outro no piloto não teria efeito
    email, _nome = _usuario()
    quem = codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) or ""
    try:
        PI.decidir(current_app.config, pid, quer == "sim", quem, S._agora(), teste=teste)
        resultado = "ok"
    except PI.Recusada:
        resultado = "sem_token"
    except Exception as e:      # noqa: BLE001 — banco fora, leitura incompleta: nada gravado
        _log.warning("equipe: a decisão do piloto não foi gravada (%s)", type(e).__name__)
        resultado = "erro"
    finally:
        srv.esquecer_piloto()   # gravou (ou pode ter gravado antes de a conferência falhar): o próximo pedido relê
    if resultado == "ok":
        _log.info("equipe: a pessoa %s %s o piloto%s (decisão de um administrador)", pid,
                  "entrou no" if quer == "sim" else "saiu do", " como teste" if teste else "")
    return redirect(url_for("torre_campo.equipe", piloto=resultado), code=303)
