"""Os tipos de e-mail que o Nexus manda (25/11/2026). Todo id começa com "nx_": não colide com os 7 do App de Campo, e a
regra de cada um mora no livro do Nexus (`emails_controle.NEXUS`), que o App não lê.

Dois de onde: os EMBUTIDOS (no código, como o de teste) e os CRIADOS pela tela (Base › E-mails automáticos › Novo e-mail,
`nexus/emails/modelos.py`). Um tipo diz o nome, quando sai, para quem (o papel), se é crítico (desligar pede a
confirmação) e, quando tem agenda, como monta as mensagens daquela vez.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Tipo:
    id: str
    nome: str
    gatilho: str            # quando sai, em palavras
    destino: str            # para quem, o PAPEL (nunca o endereço)
    critico: bool = False
    criado: bool = False    # feito pela tela (um modelo), e não no código
    quem_deixa: str = ""    # o que se perde ao desligar um crítico (a confirmação)
    extra: dict = field(default_factory=dict)


def mensagem(*, tipo: str, referencia: str, chave: str, para: list[dict], assunto: str, html: str,
             cc: list[dict] | None = None) -> dict:
    """O que vai à fila. `para`/`cc`: [{email, papel}]. `referencia` vai em claro no registro (sem nome nem e-mail: o
    registro apaga e-mail de qualquer jeito). `chave` é única por envio: a mesma chave não entra duas vezes na fila (o
    agendado que roda de novo depois de um reinício)."""
    return {"tipo": tipo, "referencia": referencia, "chave": chave, "para": list(para), "cc": list(cc or []),
            "assunto": assunto, "html": html}


EMBUTIDOS = {
    "nx_teste": Tipo("nx_teste", "E-mail de teste do Nexus", "quando um administrador pede, na tela",
                     "quem pediu o teste"),
}


def criados() -> dict:
    """Os tipos dos modelos feitos pela tela (a fase 4). Sem o livro dos modelos (banco fora, teste), nenhum."""
    try:
        from . import modelos
        return modelos.tipos()
    except Exception:        # noqa: BLE001
        return {}


def do_app() -> dict:
    """Os tipos que nascem dos eventos do App de Campo (a fase 3, `evento_app.py`)."""
    from . import evento_app
    return evento_app.tipos()


def todos() -> dict:
    return {**EMBUTIDOS, **do_app(), **criados()}


def ids() -> tuple:
    return tuple(todos())


def do_id(tipo: str) -> Tipo | None:
    return todos().get(tipo)
