"""Observação do responsável (Levi, 13/10/2026): "Inclua também abaixo um campo para Observação do Responsável. Onde o
responsável pode pontuar o que quiser que ficará salvo o dia e hora, só os responsáveis podem comentar, incluindo
responsáveis de outras usinas podem comentar em usinas que não são responsáveis, para caso de férias! É importante que
fique salvo em algum canto do Nexus para posteriormente poder juntar esse comentário para relatórios".

O Nexus é a FONTE deste fato: livro `nexus_observacoes` · `fato_observacao_responsavel` (grão: 1 linha = 1 observação
de 1 Responsável O&M sobre 1 usina), registrado no catálogo antes da 1ª gravação (regra 10). No BANCO, e não num arquivo
da máquina: o PC (hoje, pelo túnel) e o servidor (depois do deploy) gravam e leem o mesmo livro, e o relatório junta de um
lugar só (`para_relatorio`). A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): o texto e o nome de quem
escreveu vão só CIFRADOS com a chave do cadastro (o Cofre, como o comentário da ronda avulsa, `ronda_avulsa.py`); a
pessoa liga por `pessoa_id` e pelo código do e-mail (`pessoa_hmac`, o mesmo do App).

Quem escreve: quem entrou pelo Fracttal e é Responsável O&M de alguma usina mobilizada, em QUALQUER usina (quem cobre as
férias de outro escreve nas usinas dele); `do_responsavel` diz se era o responsável da usina ("sim") ou se cobria outro
("não"). O administrador que entrou pela senha não escreve (a regra do Levi: só os responsáveis). O banco não apaga:
nada se edita; o livro é trocado inteiro a cada gravação, sob a trava, com o que já estava lá relido antes.
"""
import json
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from ..dados import fatos as D
from ..dados import livros
from . import visao
from .ligacao_cadastro import codigo_da_pessoa

LIVRO, NOME_LIVRO, ABA = "nexus_observacoes", "Nexus · observações do responsável", "fato_observacao_responsavel"
CAB = ("id", "escrita_em", "data_id", "mes_id", "usina_id", "pessoa_id", "pessoa_hmac", "quem_cifrado", "texto_cifrado",
       "do_responsavel", "tela")
TEXTO_MAX = 2000
TELAS = ("meta",)               # onde a observação foi escrita (a janela da Meta da Visão do responsável)
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()       # o livro é trocado inteiro: duas observações juntas não se apagam


class Recusada(ValueError):
    """A observação não pode ser gravada: o texto diz por quê, para a janela mostrar."""


def _cofre():
    chave = current_app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise Recusada("Este Nexus não tem a chave do cadastro (NEXUS_CHAVE_CADASTRO): sem ela o texto não vai cifrado")
    from ..cadastro.cifra import Cofre
    return Cofre(chave)


def _ctx(oid, campo) -> str:
    return f"banco/observacoes/{oid}/{campo}"


def ler_todas() -> list[dict]:
    """O livro inteiro, sem cópia em memória: quem acabou de escrever tem de ver a própria observação."""
    return livros.ler(visao._base(), visao._sessao(), LIVRO, ABA)


def _decifrada(cofre, l: dict) -> dict:
    quem, texto = {}, ""
    if cofre:
        try:
            quem = json.loads(cofre.decifrar(l.get("quem_cifrado") or "", _ctx(l["id"], "quem")))
        except Exception:           # noqa: BLE001 — cifra de outra chave ou vazia: sai sem nome
            quem = {}
        try:
            texto = cofre.decifrar(l.get("texto_cifrado") or "", _ctx(l["id"], "texto"))
        except Exception:           # noqa: BLE001
            texto = ""
    try:
        quando = datetime.fromisoformat(str(l.get("escrita_em") or "").replace("Z", "+00:00")).astimezone(_BRT)
    except ValueError:
        quando = None
    return {"id": l.get("id"), "usina_id": D._id(l.get("usina_id")), "mes_id": D._id(l.get("mes_id")),
            "quando": quando, "quando_txt": quando.strftime("%d/%m/%Y às %H:%M") if quando else "—",
            "nome": quem.get("nome") or "", "texto": texto, "tela": l.get("tela") or "",
            "do_responsavel": str(l.get("do_responsavel") or "").strip().lower() == "sim"}


def _cofre_ou_nada():
    try:
        return _cofre()
    except Recusada:
        return None


def da_usina(uid: int, limite: int = 50) -> list[dict]:
    """As observações da usina, a mais nova em cima, com o nome e o texto decifrados (só na memória da janela)."""
    cofre = _cofre_ou_nada()
    linhas = [l for l in ler_todas() if D._id(l.get("usina_id")) == uid]
    out = [_decifrada(cofre, l) for l in linhas]
    out.sort(key=lambda o: o["quando"] or datetime.min.replace(tzinfo=_BRT), reverse=True)
    return out[:limite]


def para_relatorio(de: date | None = None, ate: date | None = None) -> list[dict]:
    """Todas as observações do período (pelo dia de Brasília em que foram escritas), com a usina do cadastro, para juntar
    nos relatórios ("para posteriormente poder juntar esse comentário para relatórios"). Decifra com a chave do cadastro
    deste Nexus: o relatório roda no Nexus, nunca lê o texto direto do banco."""
    cofre = _cofre()
    b = visao._Base()
    out = []
    for l in ler_todas():
        dia = D._id(l.get("data_id"))
        if dia and ((de and dia < int(de.strftime("%Y%m%d"))) or (ate and dia > int(ate.strftime("%Y%m%d")))):
            continue
        o = _decifrada(cofre, l)
        o["usina"] = str((b.por_id.get(o["usina_id"]) or {}).get("nome") or "")
        out.append(o)
    out.sort(key=lambda o: (o["quando"] or datetime.min.replace(tzinfo=_BRT)))
    return out


def escrever(uid: int, texto: str, usuario: dict | None, responsavel_logado: str, responsavel_da_usina: str,
             mes_id: int, tela: str = "meta") -> dict:
    """Valida, grava e confere no banco. `responsavel_logado` = o Responsável O&M de quem entrou pelo Fracttal (vazio =
    não é responsável de nenhuma usina: recusa); `responsavel_da_usina` = o da usina, para o `do_responsavel`."""
    cfg = current_app.config
    email = str((usuario or {}).get("email") or "").strip().lower()
    nome = " ".join(str((usuario or {}).get("nome") or "").split())
    if not email or not responsavel_logado:
        raise Recusada("Só os Responsáveis O&M escrevem a observação, entrando com o login do Fracttal")
    texto = "\n".join(" ".join(l.split()) for l in str(texto or "").strip().splitlines()).strip()
    if not texto:
        raise Recusada("Escreva a observação antes de salvar")
    if len(texto) > TEXTO_MAX:
        raise Recusada(f"A observação passou de {TEXTO_MAX} caracteres")
    if tela not in TELAS:
        raise Recusada("Tela desconhecida")
    b = visao._Base()
    if uid not in b.mobilizadas:
        raise Recusada("Esta usina não está mobilizada no cadastro")
    codigo = codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email)
    if not codigo:
        raise Recusada("Este Nexus não tem a chave do código da pessoa (NEXUS_PESSOA_HMAC)")
    if not cfg.get("GRIDCO_SQL_TOKEN"):
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    cofre = _cofre()
    try:
        pid = visao.pessoa_do_login(email, nome)
    except Exception:               # noqa: BLE001 — sem cadastro: fica o código do e-mail (regra 4: não liga = vazio)
        pid = None
    oid = uuid.uuid4().hex[:12]
    agora = datetime.now(timezone.utc)
    nova = {"id": oid, "escrita_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "mes_id": int(mes_id), "usina_id": uid,
            "pessoa_id": pid, "pessoa_hmac": codigo,
            "quem_cifrado": cofre.cifrar(json.dumps({"nome": nome, "email": email}, ensure_ascii=False), _ctx(oid, "quem")),
            "texto_cifrado": cofre.cifrar(texto, _ctx(oid, "texto")),
            "do_responsavel": "sim" if visao._norm_nome(responsavel_logado) == visao._norm_nome(responsavel_da_usina)
            else "não", "tela": tela}
    with _TRAVA:
        linhas = ler_todas()
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(c) for c in CAB] for l in linhas + [nova]])},
                        base=visao._base(), token=cfg["GRIDCO_SQL_TOKEN"], sessao=visao._sessao())
    return nova
