"""Mapa de equipe: a decisão de pôr um técnico no piloto da coleta ou tirá-lo (08/11/2026), gravada no livro
`nexus_equipe_piloto · fato_decisao_piloto`.

Só o administrador do Nexus decide (a rota `POST /t/campo/equipe/piloto` confere). No piloto, o Nexus Field só coleta
quem o administrador escolheu (padrão: ninguém), e o livro diz quem entrou, quem saiu, quando e por quem: vale a última
decisão de cada técnico (`aparelhos.piloto_atual`). O livro só acrescenta (`so_cresce` no catálogo).

O banco só troca o livro INTEIRO (`livros.publicar`): cada decisão relê o livro agora (não a cópia de 1 min do serviço)
e grava o que havia mais a linha nova, sob uma trava, como a decisão de PT (`nexus/campo/decisao_pt.py`): duas decisões
ao mesmo tempo neste processo não se perdem uma à outra. A listagem do banco que omite o livro por um instante é falha,
não livro vazio (`livros.abas_conferidas`, achado 6 da revisão de 05/11/2026): gravar por cima dela apagaria o
histórico.

Quem decidiu vai só pelo código HMAC do e-mail (`decidida_por_hmac`); a senha de administrador, sem e-mail, grava
vazio. O `no_piloto` é 1 (entrou) ou 0 (saiu), como o catálogo descreve.
"""
import secrets
import threading
from datetime import timedelta, timezone

from nexus.campo.equipe import ABA_PILOTO, CAB_PILOTO, LIVRO_PILOTO

_BRT = timezone(timedelta(hours=-3))
NOME_LIVRO = "Mapa de equipe · piloto"
_TRAVA = threading.Lock()


class Recusada(ValueError):
    """Nada foi gravado: o texto diz por quê, para a tela mostrar."""


def decidir(cfg, pessoa_id: int, no_piloto: bool, quem_hmac: str, agora, teste: bool = False) -> dict:
    """Acrescenta a decisão ao livro do piloto e devolve a linha gravada. Sem a chave de gravação do banco: `Recusada`.
    O banco que falha (na leitura ou na gravação) sobe a exceção dele: nada foi gravado."""
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        raise Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN): nada foi gravado.")
    nova = {"decisao_id": "L" + secrets.token_hex(6)[:11],      # letra + hexadecimal: o banco infere o tipo da coluna
            "instante": agora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "pessoa_id": int(pessoa_id),
            "no_piloto": 1 if no_piloto else 0, "decidida_por_hmac": quem_hmac or None, "teste": 1 if teste else 0}
    from nexus.campo import visao
    from nexus.dados import livros
    with _TRAVA:
        base, sessao = visao._base(), visao._sessao()
        a = livros.abas_conferidas(base, sessao, LIVRO_PILOTO, ())
        antes = livros._linhas(base, sessao, a[ABA_PILOTO]) if ABA_PILOTO in a else []
        # a decisão de antes da coluna `teste` (09/11/2026) não era de teste: 0, e não vazio
        linhas = ([[(r.get(c) or 0) if c == "teste" else r.get(c) for c in CAB_PILOTO] for r in antes]
                  + [[nova[c] for c in CAB_PILOTO]])
        livros.publicar(LIVRO_PILOTO, NOME_LIVRO, {ABA_PILOTO: (list(CAB_PILOTO), linhas)}, base=base, token=token,
                        sessao=sessao)
    return nova
