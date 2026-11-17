"""O acompanhamento das contestações dos clientes (Levi, 15/10/2026: "Nas contestações do Nexus precisamos ter uma forma
de acompanhar a demanda [...] onde o responsável poderá inserir atualizações sobre a demanda com data e hora salva").

Desde 16/11/2026 o setor inteiro responde (Levi: "Tire esse 'Pegar pra mim' qualquer um daquele setor pode editar e salvar
por tanto que salve quem foi que fez isso!"): quem vê a contestação (o setor dela, ou o administrador) e entrou com um login
de pessoa (Fracttal ou Microsoft) escreve a atualização, marca como resolvida e reabre; cada evento guarda quem e quando.
Não há mais dono: o "responsavel" gravado até 15/11 segue na história ("ficou com a demanda"), sem dar nem tirar nada.

O Nexus é a FONTE deste fato: livro `nexus_contestacoes_tratamento` · `fato_tratamento_contestacao`, registrado no
catálogo antes da 1ª gravação (regra 10). Grão: 1 linha = 1 EVENTO sobre 1 contestação de 1 setor (a linha do
`thopen_contestacoes`, pelo `id` dela): `atualizacao` (alguém do setor escreveu), `resolvida` e `reaberta` (16/11/2026) e,
só na história, `responsavel` (o "Pegar para mim", até 15/11/2026). Só acrescenta: a situação de agora sai dos eventos na
ordem de gravação (`situacoes`), e nada se edita nem se apaga (o banco guarda a história).

A situação (16/11/2026, a escolha do Levi: "Sim, com Resolvida"): **resolvida** = o último `resolvida`/`reaberta` é um
`resolvida`; senão **em andamento** = já tem atualização; senão **sem resposta**. A sem resposta vai para o aviso do topo
do setor (`contratos/aviso.py`) até a 1ª atualização ou até alguém resolver.

A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): quem (nome e e-mail) e o texto vão só CIFRADOS com a
chave do cadastro (o Cofre, como a Observação do responsável); a pessoa liga pelo código do e-mail (`pessoa_hmac`). O
`evento` vai em claro: é o que o aviso do topo lê sem abrir nada.
"""
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros
from ..dados.conexao import banco as _banco

LIVRO, NOME_LIVRO = "nexus_contestacoes_tratamento", "Nexus · acompanhamento das contestações dos clientes"
ABA = "fato_tratamento_contestacao"
CAB = ("id", "registrado_em", "data_id", "contestacao_linha_id", "setor", "evento", "pessoa_hmac", "quem_cifrado",
       "texto_cifrado")
# o "responsavel" (o "Pegar para mim") só se lê: ninguém mais grava (16/11/2026)
EVENTOS = ("responsavel", "atualizacao", "resolvida", "reaberta")
SITUACOES = {"sem_resposta": ("Sem resposta", "alerta"), "em_andamento": ("Em andamento", "info"),
             "resolvida": ("Resolvida", "ok")}
TEXTO_MAX = 2000
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()       # o livro é trocado inteiro: duas ações juntas não se apagam


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela nada vai cifrado")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _cofre_ou_nada():
    try:
        return _cofre()
    except Recusada:
        return None


def _ctx(eid, campo) -> str:
    return f"banco/contestacoes_tratamento/{eid}/{campo}"


def ler_todas() -> list[dict]:
    """O livro inteiro, sem cópia em memória: quem acabou de pegar tem de se ver como responsável."""
    return livros.ler(*_banco(), LIVRO, ABA)


def _quando(v):
    try:
        return datetime.fromisoformat(str(v or "").replace("Z", "+00:00")).astimezone(_BRT)
    except ValueError:
        return None


def _abre(cofre, l: dict) -> dict:
    quem, texto = {}, ""
    if cofre:
        try:
            quem = json.loads(cofre.decifrar(l.get("quem_cifrado") or "", _ctx(l.get("id"), "quem")))
        except Exception:           # noqa: BLE001 — cifra de outra chave ou adulterada: sai sem nome
            quem = {}
        if l.get("texto_cifrado"):
            try:
                texto = cofre.decifrar(l.get("texto_cifrado"), _ctx(l.get("id"), "texto"))
            except Exception:       # noqa: BLE001
                texto = ""
    q = _quando(l.get("registrado_em"))
    return {"id": l.get("id"), "linha": str(l.get("contestacao_linha_id") or ""), "setor": str(l.get("setor") or ""),
            "evento": str(l.get("evento") or ""), "quando": q, "quando_txt": q.strftime("%d/%m/%Y às %H:%M") if q else "—",
            "hmac": str(l.get("pessoa_hmac") or ""), "nome": quem.get("nome") or quem.get("email") or "",
            "texto": texto}


def _em_ordem(linhas: list[dict]) -> list[dict]:
    """As linhas na ordem da gravação: pela hora e, no mesmo segundo, pela posição no livro (o livro só acrescenta, no
    fim). Pela hora e pelo id, dois eventos no mesmo segundo (resolver e reabrir logo depois) ficavam ao acaso."""
    ordem = {id(l): i for i, l in enumerate(linhas)}
    return sorted(linhas, key=lambda l: (_quando(l.get("registrado_em")) or datetime.min.replace(tzinfo=_BRT),
                                         ordem[id(l)]))


def _situacao(eventos: list[str]) -> str:
    fecha = [e for e in eventos if e in ("resolvida", "reaberta")]
    if fecha and fecha[-1] == "resolvida":
        return "resolvida"
    return "em_andamento" if "atualizacao" in eventos else "sem_resposta"


def situacoes(linhas: list[dict]) -> dict:
    """{linha_id: situação} só pelo `evento` (em claro), sem abrir nada: é o que o aviso do topo lê. A linha sem nenhum
    evento não está aqui (é "sem_resposta")."""
    por: dict = {}
    for l in _em_ordem(linhas):
        por.setdefault(str(l.get("contestacao_linha_id") or ""), []).append(str(l.get("evento") or ""))
    return {k: _situacao(v) for k, v in por.items()}


def estado(linhas: list[dict] | None = None) -> dict:
    """{linha_id: {"situacao", "eventos": [evento, o mais antigo primeiro], "atualizacoes": [só as escritas],
    "resolvida": o evento que resolveu (se está resolvida), "ultima": a última atualização}}. `linhas` = o livro (os
    testes passam; a tela lê do banco)."""
    cofre = _cofre_ou_nada()
    brutas = _em_ordem(ler_todas() if linhas is None else linhas)
    out: dict = {}
    for l in brutas:
        e = _abre(cofre, l)
        x = out.setdefault(e["linha"], {"situacao": "sem_resposta", "eventos": [], "atualizacoes": [],
                                        "resolvida": None, "ultima": None})
        x["eventos"].append(e)
        if e["evento"] == "atualizacao":
            x["atualizacoes"].append(e)
            x["ultima"] = e
    for x in out.values():
        x["situacao"] = _situacao([e["evento"] for e in x["eventos"]])
        if x["situacao"] == "resolvida":
            x["resolvida"] = next(e for e in reversed(x["eventos"]) if e["evento"] == "resolvida")
    return out


VAZIO = {"situacao": "sem_resposta", "eventos": [], "atualizacoes": [], "resolvida": None, "ultima": None}


def codigo(usuario) -> str | None:
    """O código da pessoa do login (o mesmo do App e dos setores), ou None sem e-mail ou sem a NEXUS_PESSOA_HMAC."""
    from ..cadastro.ligacao_campo import codigo_da_pessoa
    email = str((usuario or {}).get("email") or "").strip().lower()
    return codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) if email else None


def _gravar(linha_id: str, setor: str, evento: str, usuario: dict, texto: str = "") -> dict:
    cfg = current_app.config
    email = str((usuario or {}).get("email") or "").strip().lower()
    nome = " ".join(str((usuario or {}).get("nome") or "").split()) or email
    cod = codigo(usuario)
    if not email:
        raise Recusada("Entre com o seu login (Fracttal ou Microsoft) para acompanhar a demanda: a senha de "
                       "administrador não diz quem é a pessoa")
    if not cod:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    cofre = _cofre()
    eid = uuid.uuid4().hex[:12]
    agora = datetime.now(timezone.utc)
    return {"id": eid, "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "contestacao_linha_id": str(linha_id),
            "setor": setor, "evento": evento, "pessoa_hmac": cod,
            "quem_cifrado": cofre.cifrar(json.dumps({"nome": nome, "email": email}, ensure_ascii=False), _ctx(eid, "quem")),
            "texto_cifrado": cofre.cifrar(texto, _ctx(eid, "texto")) if texto else None}


def _publicar(linhas: list[dict]) -> None:
    base, sessao = _banco()
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in linhas])},
                    base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)


def _acrescentar(nova: dict, conferir=None) -> dict:
    """Relê o livro sob a trava, confere a situação de agora (`conferir(situacao)` recusa) e grava o evento no fim; depois
    a cópia do aviso do topo já sabe dele (quem gravou vê o aviso sumir na página seguinte)."""
    with _TRAVA:
        linhas = ler_todas()
        if conferir:
            conferir(situacoes(linhas).get(nova["contestacao_linha_id"], "sem_resposta"))
        _publicar(linhas + [nova])
    try:
        from . import aviso
        aviso.anotar(nova)
    except Exception:           # noqa: BLE001 — a cópia do aviso se acerta na próxima leitura
        current_app.logger.exception("Contestações: a cópia do aviso não anotou o evento")
    return nova


def atualizar(linha_id: str, setor: str, usuario: dict, texto: str) -> dict:
    """Uma atualização, com a data, a hora e quem escreveu. Qualquer um que vê a contestação escreve (16/11/2026): quem
    vê, a tela já conferiu (o setor dela, ou o administrador)."""
    texto = "\n".join(" ".join(l.split()) for l in str(texto or "").strip().splitlines()).strip()
    if not texto:
        raise Recusada("Escreva a atualização antes de salvar")
    if len(texto) > TEXTO_MAX:
        raise Recusada(f"A atualização passou de {TEXTO_MAX} caracteres")
    return _acrescentar(_gravar(linha_id, setor, "atualizacao", usuario, texto))


def resolver(linha_id: str, setor: str, usuario: dict) -> dict:
    """Marca como resolvida (16/11/2026): sai das abertas e do aviso do topo; fica quem e quando."""
    def conferir(sit):
        if sit == "resolvida":
            raise Recusada("Esta contestação já está resolvida")
    return _acrescentar(_gravar(linha_id, setor, "resolvida", usuario), conferir)


def reabrir(linha_id: str, setor: str, usuario: dict) -> dict:
    """Reabre a resolvida: volta às abertas, com a situação que tinha (em andamento, ou sem resposta e no aviso)."""
    def conferir(sit):
        if sit != "resolvida":
            raise Recusada("Esta contestação não está resolvida")
    return _acrescentar(_gravar(linha_id, setor, "reaberta", usuario), conferir)
