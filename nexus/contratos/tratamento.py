"""O acompanhamento das contestações dos clientes (Levi, 15/10/2026: "Nas contestações do Nexus precisamos ter uma forma
de acompanhar a demanda, um botão 'Pegar para mim' ao clicar nesse botão o usuário se torna o responsável por aquela
demanda. Ao clicar na linha, vai aparecer um card sobrepondo a tela com um blur de fundo onde o responsável poderá inserir
atualizações sobre a demanda com data e hora salva").

O Nexus é a FONTE deste fato: livro `nexus_contestacoes_tratamento` · `fato_tratamento_contestacao`, registrado no
catálogo antes da 1ª gravação (regra 10). Grão: 1 linha = 1 EVENTO sobre 1 contestação de 1 setor (a linha do
`thopen_contestacoes`, pelo `id` dela): `responsavel` (alguém pegou a demanda) ou `atualizacao` (o responsável escreveu).
Só acrescenta: o responsável de agora é o do último `responsavel`, e as atualizações saem na ordem. Nada se edita nem se
apaga (o banco guarda a história).

A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): quem (nome e e-mail) e o texto vão só CIFRADOS com a
chave do cadastro (o Cofre, como a Observação do responsável); a pessoa liga pelo código do e-mail (`pessoa_hmac`).

Quem faz o quê: pega quem entrou com um login de pessoa (Fracttal ou Microsoft) e vê a contestação (o setor dela, ou o
administrador). Contestação que já tem dono só muda de mãos por um administrador ("Assumir"). Só o responsável de agora
escreve atualização; o resto do setor lê.
"""
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from ..dados import livros

LIVRO, NOME_LIVRO = "nexus_contestacoes_tratamento", "Nexus · acompanhamento das contestações dos clientes"
ABA = "fato_tratamento_contestacao"
CAB = ("id", "registrado_em", "data_id", "contestacao_linha_id", "setor", "evento", "pessoa_hmac", "quem_cifrado",
       "texto_cifrado")
EVENTOS = ("responsavel", "atualizacao")
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


def _banco():
    from ..campo import visao
    return visao._base(), visao._sessao()


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


def estado(linhas: list[dict] | None = None) -> dict:
    """{linha_id: {"responsavel": evento | None, "atualizacoes": [evento, a mais antiga primeiro]}} — o responsável de
    agora é o do último `responsavel`. `linhas` = o livro (os testes passam; a tela lê do banco)."""
    cofre = _cofre_ou_nada()
    eventos = [_abre(cofre, l) for l in (ler_todas() if linhas is None else linhas)]
    # a ordem é a da gravação (o livro só acrescenta, no fim): dois eventos no mesmo segundo (pegar e o administrador
    # assumir logo depois) ficavam na ordem do id, ao acaso, e o responsável podia sair o de antes
    ordem = {id(e): i for i, e in enumerate(eventos)}
    eventos.sort(key=lambda e: (e["quando"] or datetime.min.replace(tzinfo=_BRT), ordem[id(e)]))
    out: dict = {}
    for e in eventos:
        x = out.setdefault(e["linha"], {"responsavel": None, "atualizacoes": []})
        if e["evento"] == "responsavel":
            x["responsavel"] = e
        elif e["evento"] == "atualizacao":
            x["atualizacoes"].append(e)
    return out


def codigo(usuario) -> str | None:
    """O código da pessoa do login (o mesmo do App e dos setores), ou None sem e-mail ou sem a NEXUS_PESSOA_HMAC."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
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


def pegar(linha_id: str, setor: str, usuario: dict, admin: bool) -> dict:
    """A pessoa do login vira a responsável. Livre: qualquer um que vê a contestação pega. Com dono: só o administrador
    assume (a demanda não troca de mãos sem quem coordena)."""
    nova = _gravar(linha_id, setor, "responsavel", usuario)
    with _TRAVA:
        linhas = ler_todas()
        atual = estado(linhas).get(str(linha_id), {}).get("responsavel")
        if atual and atual["hmac"] == nova["pessoa_hmac"]:
            raise Recusada("Esta demanda já é sua")
        if atual and not admin:
            raise Recusada(f"Esta demanda já tem responsável ({atual['nome'] or 'outra pessoa'}): só um administrador "
                           "passa para outra pessoa")
        _publicar(linhas + [nova])
    return nova


def atualizar(linha_id: str, setor: str, usuario: dict, texto: str) -> dict:
    """Uma atualização do responsável, com a data e a hora de agora. Só o responsável de agora escreve."""
    texto = "\n".join(" ".join(l.split()) for l in str(texto or "").strip().splitlines()).strip()
    if not texto:
        raise Recusada("Escreva a atualização antes de salvar")
    if len(texto) > TEXTO_MAX:
        raise Recusada(f"A atualização passou de {TEXTO_MAX} caracteres")
    nova = _gravar(linha_id, setor, "atualizacao", usuario, texto)
    with _TRAVA:
        linhas = ler_todas()
        atual = estado(linhas).get(str(linha_id), {}).get("responsavel")
        if not atual or atual["hmac"] != nova["pessoa_hmac"]:
            raise Recusada("Só o responsável pela demanda escreve atualização: use \"Pegar para mim\" antes")
        _publicar(linhas + [nova])
    return nova
