"""Ronda avulsa: lançada à mão no Nexus por quem fez a ronda (Levi, 07/10/2026: "tem que ser possível inserir rondas
avulsas, a pessoa loga pelo fractal dela ... não terá imagens, só informações da tabela, salva nome da pessoa, data e
hora e diz que foi avulso, quando passa o mouse em cima de avulso explica o que é ronda avulsa"). Decisões dele no mesmo
dia: conta na cobertura (tira a usina das pendentes) e leva um comentário livre opcional.

O Nexus é a FONTE deste fato: livro `nexus_rondas_avulsas` · `fato_ronda_avulsa` (grão: 1 linha = 1 lançamento). A API
do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): nome, e-mail e comentário vão só CIFRADOS com a chave do
cadastro; a pessoa liga por `pessoa_id` (cadastro) e pelo código do e-mail (`pessoa_hmac`, o mesmo do App). O banco não
apaga: o lançamento errado é anulado por outra linha (`anula_id`), e só quem lançou anula.

O domínio é o do App (08/10/2026, decisão 3 do Levi, ANTES da 1ª gravação do livro; spec Kimball, seção 9): a vala tem
as opções do App (`dominios.VALA_OPCOES`: o "Suja" do formulário de 07/10 não existia no App e não somava com
"Obstruída") e cada sensor tem três estados, gravados como a palavra do domínio ("Sujo", "Limpo"; vazio = não
verifiquei). O formulário de 07/10 gravava 0 para o sensor não marcado, que contava como limpo sem ninguém ter olhado.
A linha de anulação só aponta a anulada (`anula_id`), sem `data_id`, `data` e `usina_id`: com eles, um COUNT por usina e
dia no livro aberto contava 2 para uma ronda anulada (GR-7).

O livro recebe também a "criticidade validada pela foto" importada de planilha (`origem = "validacao_foto"`,
`ferramentas/importar_avulsas_planilha.py`), pelo MESMO caminho de gravação (`montar_linha` + `acrescentar`): mesmo
cabeçalho, mesma cifra. Ela não é ronda realizada (fica fora do `fato_ronda`, ver `fato_ronda.eh_validacao_foto`).

A tela de Rondas lê daqui junto com o livro do App (`visao._rondas_ligadas`): a avulsa entra em Registros, Sujidade e
vegetação, Histórico da usina e na cobertura, com o selo "Avulsa". Qualidade e veredito ficam "—": a nota do App depende
de foto e GPS, que a avulsa não tem.
"""
import json
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from ..dados import dominios as DOM
from ..dados import fatos as D
from ..dados import livros
from . import visao
from .ligacao_cadastro import codigo_da_pessoa

LIVRO, NOME_LIVRO, ABA = "nexus_rondas_avulsas", "Nexus · rondas avulsas", "fato_ronda_avulsa"
CAB = ("id", "lancada_em", "data_id", "data", "inicio", "fim", "duracao_min", "usina_id", "equipe_id", "pessoa_id",
       "pessoa_hmac", "quem_cifrado", "tipo", "sujidade", "vegetacao", "sombreamento", "vala", "ipoa_sujo",
       "albedo_sujo", "ghi_sujo", "comentario_cifrado", "anula_id", "origem")
EXPLICACAO = ("Ronda avulsa: lançada à mão no Nexus por quem fez a ronda, sem passar pelo App. Não tem fotos, GPS nem "
              "OS no Fracttal; vale o que a pessoa informou.")
ORIGEM, ORIGEM_ANULACAO = "avulsa", "anulação"
TIPOS = ("curta", "longa")
VALAS = DOM.VALA_OPCOES         # as opções do App: Limpa, Parcial, Obstruída, Não se aplica
SOMBRAS = ("sim", "não")
SENSORES = (("ipoa_sujo", "IPOA"), ("albedo_sujo", "Albedômetro"), ("ghi_sujo", "GHI"))
# Os três estados de cada sensor no formulário: (o que vai ao banco, o rótulo). "Não verifiquei" vai VAZIO: limpo é só
# o que alguém olhou (o 0 por não marcado do formulário de 07/10 era "limpo" sem ninguém ter visto).
ESTADOS_SENSOR = (("", "Não verifiquei"), (DOM.SENSOR_ROTULO[0], "Limpo"), (DOM.SENSOR_ROTULO[1], "Sujo"))
DIAS_ATRAS = 30                 # ronda de mais de 30 dias atrás não se lança: já saiu da conta da cobertura
DURACAO_MAX_MIN = 480           # o mesmo teto do relógio da ronda do App (visao._duracao_min)
COMENTARIO_MAX = 1000
_HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()       # o livro é trocado inteiro: dois lançamentos juntos não se apagam


class Recusada(ValueError):
    """O lançamento não pode ser gravado: o texto diz por quê, para a tela mostrar."""


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela o nome não vai cifrado.")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _ctx(rid, campo) -> str:
    return f"banco/rondas_avulsas/{rid}/{campo}"


def _origem(linha) -> str:
    return str(linha.get("origem") or "").strip().lower()


def ler_todas() -> list[dict]:
    """O livro inteiro, na ordem em que foi lançado (sem cópia: quem lança precisa ver o último)."""
    return livros.ler(visao._base(), visao._sessao(), LIVRO, ABA)


def validas(linhas) -> list[dict]:
    """Os lançamentos que valem: sem as linhas de anulação e sem os que foram anulados."""
    anuladas = {str(l.get("anula_id")) for l in linhas if l.get("anula_id")}
    return [l for l in linhas if not l.get("anula_id") and str(l.get("id")) not in anuladas]


def para_tela(linhas) -> list[dict]:
    """Cada avulsa que vale, com o nome e o comentário decifrados (só na memória da tela). Sem a chave, sem nome."""
    try:
        cofre = _cofre()
    except Recusada:
        cofre = None
    out = []
    for l in validas(linhas):
        quem, coment = {}, ""
        if cofre:
            try:
                quem = json.loads(cofre.decifrar(l.get("quem_cifrado") or "", _ctx(l["id"], "quem")))
            except Exception:       # noqa: BLE001 — cifra de outra chave ou vazia: sai sem nome
                quem = {}
            if l.get("comentario_cifrado"):
                try:
                    coment = cofre.decifrar(l["comentario_cifrado"], _ctx(l["id"], "comentario"))
                except Exception:   # noqa: BLE001
                    coment = ""
        out.append({**l, "nome": quem.get("nome") or "", "email": quem.get("email") or "", "comentario": coment})
    return out


def _pessoa_id(base, email: str, nome: str):
    """O `pessoa_id` de quem lançou: pelo e-mail da ficha ou pelo nome quando ele é de UMA pessoa (regra 4: não liga =
    vazio, nunca chutar). As fichas têm o nome e o e-mail só cifrados."""
    try:
        cofre = _cofre()
    except Recusada:
        return None
    alvo_email = str(email or "").strip().lower()
    alvo_nome = visao._norm_nome(nome)
    por_email, por_nome = set(), set()
    for p in base.pessoas:
        pid = D._id(p.get("pessoa_id"))
        if not pid or not p.get("sensivel_cifrado") or str(p.get("excluido") or "").strip().lower() == "sim":
            continue
        try:
            s = json.loads(cofre.decifrar(p["sensivel_cifrado"], f"banco/pessoas/{pid}"))
        except Exception:           # noqa: BLE001
            continue
        if alvo_email and str(s.get("email") or "").strip().lower() == alvo_email:
            por_email.add(pid)
        elif alvo_nome and alvo_nome in {visao._norm_nome(s.get("nome")), visao._norm_nome(s.get("nome_padrao"))}:
            por_nome.add(pid)
    achados = por_email or por_nome
    return next(iter(achados)) if len(achados) == 1 else None


def usinas_para_escolher() -> list[dict]:
    """As usinas mobilizadas (as que a tela de Rondas conta), pelo nome do cadastro."""
    b = visao._Base()
    return sorted(({"usina_id": uid, "nome": str(u.get("nome") or ""), "uf": str(u.get("uf") or "")}
                   for uid, u in b.mobilizadas.items()), key=lambda u: visao._norm_nome(u["nome"]))


def _nivel(v, nome):
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise Recusada(f"{nome}: escolha de 1 a 5.") from None
    if not 1 <= n <= 5:
        raise Recusada(f"{nome}: escolha de 1 a 5.")
    return n


def _vala(v) -> str:
    """A opção do App, escrita como ele escreve ("obstruida" -> "Obstruída"); vazio = não informada. Outro texto (o
    "Suja" de 07/10) é recusado: não existe no App."""
    n = DOM.norm(v)
    if not n:
        return ""
    rotulo = {DOM.norm(o): o for o in VALAS}.get(n)
    if not rotulo:
        raise Recusada("Vala: " + ", ".join(VALAS) + ".")
    return rotulo


def _sensor(v, nome) -> str:
    """Três estados: "Sujo", "Limpo" ou vazio (não verifiquei). Nunca "limpo" por não ter marcado nada."""
    n = DOM.norm(v)
    if n in ("", "nao verifiquei"):
        return ""
    if n in DOM.SENSOR:
        return DOM.SENSOR_ROTULO[DOM.SENSOR[n]]
    raise Recusada(f"{nome}: limpo, sujo ou não verifiquei.")


def montar_linha(cofre, *, origem: str, dia: date, usina_id: int, equipe_id, pessoa_id, codigo, nome: str, email: str,
                 inicio: str, fim: str = "", duracao_min=None, tipo: str = "", sujidade=None, vegetacao=None,
                 vala: str = "", sombreamento: str = "", sensores: dict | None = None, comentario: str = "") -> dict:
    """UMA linha do livro (`CAB`), com quem lançou e o comentário só cifrados (`cofre` = o Cofre da chave do cadastro).
    É o caminho único de gravação: a tela (`lancar`) e a importação de planilha montam a linha aqui, para o livro ter um
    formato só. Sensor fora de `sensores` = vazio (não verificado)."""
    rid = uuid.uuid4().hex[:12]
    sensores = sensores or {}
    return {"id": rid, "lancada_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_id": int(dia.strftime("%Y%m%d")), "data": dia.isoformat(), "inicio": inicio, "fim": fim,
            "duracao_min": duracao_min, "usina_id": usina_id, "equipe_id": equipe_id, "pessoa_id": pessoa_id,
            "pessoa_hmac": codigo or "",
            "quem_cifrado": cofre.cifrar(json.dumps({"nome": nome, "email": email}, ensure_ascii=False),
                                         _ctx(rid, "quem")),
            "tipo": tipo, "sujidade": sujidade, "vegetacao": vegetacao, "sombreamento": sombreamento, "vala": vala,
            **{c: sensores.get(c) or "" for c, _n in SENSORES},
            "comentario_cifrado": cofre.cifrar(comentario, _ctx(rid, "comentario")) if comentario else "",
            "anula_id": "", "origem": origem}


def acrescentar(novas: list[dict], repetida=None) -> tuple[list[dict], list[dict]]:
    """Grava `novas` no FIM do livro junto com TODAS as linhas que já estão lá: o livro é trocado inteiro
    (`sync-xlsx?replace=true`), e o que não for reenviado some. `repetida(nova, validas)` diz se a nova repete uma
    linha válida (do livro ou das novas que já entraram nesta vez): essa não entra. Devolve (entraram, puladas). A
    contagem é conferida depois de gravar (`livros.publicar`); sob a trava, dois lançamentos juntos não se apagam."""
    with _TRAVA:
        linhas = ler_todas()
        vistas, entram, puladas = validas(linhas), [], []
        for n in novas:
            if repetida and repetida(n, vistas):
                puladas.append(n)
            else:
                entram.append(n)
                vistas.append(n)
        if entram:
            _gravar(linhas + entram)
    if entram:
        visao.limpar()
    return entram, puladas


def _mesma_ronda(nova, vistas) -> bool:
    """A mesma pessoa não lança duas vezes a mesma usina no mesmo início (entre as avulsas: a validação por foto é
    outra coisa, mesmo que caia na mesma usina e no mesmo dia)."""
    return any(D._id(l.get("usina_id")) == nova["usina_id"] and str(l.get("inicio")) == nova["inicio"]
               and l.get("pessoa_hmac") == nova["pessoa_hmac"] and _origem(l) == ORIGEM for l in vistas)


def lancar(form, usuario: dict | None) -> dict:
    """Valida, grava e confere no banco. `form` é o request.form (ou um dict)."""
    cfg = current_app.config
    email = str((usuario or {}).get("email") or "").strip().lower()
    nome = " ".join(str((usuario or {}).get("nome") or "").split())
    if not email:
        raise Recusada("Para lançar uma ronda avulsa, entre com o seu login do Fracttal: a ronda fica no seu nome.")
    try:
        uid = int(str(form.get("usina_id") or "").strip())
    except ValueError:
        raise Recusada("Escolha a usina.") from None
    b = visao._Base()
    if uid not in b.mobilizadas:
        raise Recusada("Escolha uma usina mobilizada do cadastro.")
    try:
        dia = date.fromisoformat(str(form.get("data") or "").strip())
    except ValueError:
        raise Recusada("Data inválida.") from None
    hoje = datetime.now(_BRT).date()
    if dia > hoje:
        raise Recusada("A data da ronda não pode ser no futuro.")
    if dia < hoje - timedelta(days=DIAS_ATRAS):
        raise Recusada(f"Só dá para lançar ronda feita até {DIAS_ATRAS} dias atrás.")
    ini, fim = str(form.get("inicio") or "").strip(), str(form.get("fim") or "").strip()
    if not _HM.match(ini) or not _HM.match(fim):
        raise Recusada("Início e fim no formato hora:minuto (ex.: 08:00).")
    a = datetime.fromisoformat(f"{dia.isoformat()}T{ini}:00").replace(tzinfo=_BRT)
    z = datetime.fromisoformat(f"{dia.isoformat()}T{fim}:00").replace(tzinfo=_BRT)
    dur = int((z - a).total_seconds() // 60)
    if dur <= 0:
        raise Recusada("O fim tem de ser depois do início.")
    if dur > DURACAO_MAX_MIN:
        raise Recusada("A ronda passou de 8 horas: confira o início e o fim.")
    if z > datetime.now(_BRT) + timedelta(minutes=5):
        raise Recusada("O fim da ronda não pode ser no futuro.")
    tipo = str(form.get("tipo") or "").strip().lower()
    if tipo not in TIPOS:
        raise Recusada("Tipo: curta ou longa.")
    suj, veg = _nivel(form.get("sujidade"), "Sujidade"), _nivel(form.get("vegetacao"), "Vegetação")
    vala = _vala(form.get("vala"))
    sombra = str(form.get("sombreamento") or "").strip().lower()
    if sombra and sombra not in SOMBRAS:
        raise Recusada("Sombreamento: sim ou não.")
    sensores = {c: _sensor(form.get(c), n) for c, n in SENSORES}
    coment = " ".join(str(form.get("comentario") or "").split())[:COMENTARIO_MAX]
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not codigo:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC).")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN).")
    cofre = _cofre()
    u = b.por_id[uid]
    nova = montar_linha(cofre, origem=ORIGEM, dia=dia, usina_id=uid, equipe_id=D._id(u.get("equipe_id")),
                        pessoa_id=_pessoa_id(b, email, nome), codigo=codigo, nome=nome, email=email,
                        inicio=a.isoformat(), fim=z.isoformat(), duracao_min=dur, tipo=tipo, sujidade=suj,
                        vegetacao=veg, vala=vala, sombreamento=sombra, sensores=sensores, comentario=coment)
    entrou, _ = acrescentar([nova], _mesma_ronda)
    if not entrou:
        raise Recusada("Você já lançou esta ronda (mesma usina, dia e início).")
    return nova


def anular(rid: str, usuario: dict | None) -> dict:
    """Anula um lançamento: só quem lançou (pelo código do e-mail). Vira outra linha; o banco não apaga. A linha de
    anulação leva só o `anula_id` (e quem anulou e quando): sem dia nem usina, ela não conta como ronda daquela usina
    naquele dia para quem soma o livro aberto."""
    cfg = current_app.config
    email = str((usuario or {}).get("email") or "").strip().lower()
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email) if email else ""
    with _TRAVA:
        linhas = ler_todas()
        alvo = next((l for l in validas(linhas) if str(l.get("id")) == str(rid)), None)
        if not alvo:
            raise Recusada("Esta ronda avulsa não existe ou já foi anulada.")
        if not codigo or alvo.get("pessoa_hmac") != codigo:
            raise Recusada("Só quem lançou a ronda avulsa pode anular.")
        agora = datetime.now(timezone.utc)
        linha = {c: "" for c in CAB}
        linha.update({"id": uuid.uuid4().hex[:12], "lancada_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "pessoa_hmac": codigo, "anula_id": str(rid), "origem": ORIGEM_ANULACAO})
        _gravar(linhas + [linha])
    visao.limpar()
    return linha


def _gravar(linhas: list[dict]) -> None:
    cfg = current_app.config
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in linhas])},
                    base=visao._base(), token=cfg["GRIDCO_SQL_TOKEN"], sessao=visao._sessao())
