# os_creator/os_web/acomp_raiox.py
"""O chamado de garantia no Raio X da OS do Nexus, sem moldura (16/11/2026, Levi: "A OS de garantia está abrindo um chamado
dentro do chamado ... o raio x da OS é uma evolução dessa visão de dentro"; no quiz, "Uma página só").

De 11/11 a 16/11/2026 o Raio X mostrava a tela do chamado inteira numa moldura (o modo "blocos"): com rolagem própria, o
status duplicado (o da Engenharia e o do chamado) e duas cadeias. Agora o Raio X monta ele mesmo os blocos que só o chamado
tem, com o que ele já leu da OS (o REST da empresa: a nota inteira, a situação, o responsável) e com o banco da Gridco (as
observações e o status do chamado): o status do chamado (no lugar do status da Engenharia), o ticket no fornecedor, o Como
abrir, os campos para abrir o ticket, as observações e os outros chamados. A cadeia fica a do Raio X.

Sem a sessão da pessoa no Fracttal: o Raio X é do Nexus, e o cookie do OS Creator (caminho /os) não chega lá. Por isso as
escritas não moram aqui: a tela chama as mesmas rotas do chamado (`/os/api/acomp/<nº>/ticket`, `status`, `obs`,
`obs/<id>/editar|excluir` e `finalizar`), com o cookie do OS Creator, e as regras delas valem igual (a atividade do 1º
comentário, quem edita e exclui, o Finalizar que encerra a atividade)."""
from __future__ import annotations

import datetime as dt

import chamado_spec as cs
import chamados_obs_store as obs_store
import gridco_abas as ga

from . import acomp_web as aw

# a coluna do Raio X → o status do Fracttal que o cartão do chamado entende
STATUS_DA_COLUNA = {"fazer": 1, "execucao": 1, "verificacao": 2, "concluida": 3, "cancelada": 4}


def _do_cache(folio: str) -> tuple:
    """(a linha da OS e todos os cartões) da última leitura do quadro de Garantias guardada, sem ir ao Fracttal; (None,
    []) sem leitura guardada. É dela que saem o cliente, a usina e os "outros chamados" do mesmo ativo."""
    from . import rotas_acomp as RA
    for chave in (("acomp", "TODOS"), ("acomp_linhas", "TODOS")):
        _, d = RA._guardado_com_idade(chave)
        if isinstance(d, dict) and d.get("linhas"):
            return RA._linha_de(d, folio), RA._cartoes(d, aw.agora_brt())
    return None, []


def _quando(texto):
    try:
        return dt.datetime.strptime(str(texto or "")[:16], "%d/%m/%Y %H:%M").replace(tzinfo=aw.BRT)
    except ValueError:
        return None


def blocos(folio, o: dict, ticket: str | None = None, obs=None, erro_obs: str = "") -> dict:
    """Tudo o que os blocos do chamado no Raio X mostram, para a OS `o` do Raio X (`os_equipe.ler_os`). `ticket` é a
    resposta da subtarefa do ticket, lida pelo Raio X (None: não lida; vale a da cópia do quadro). `obs` são as entradas
    da OS no banco da Gridco (None: lidas aqui)."""
    folio = str(folio)
    if obs is None:
        try:
            obs, erro_obs = obs_store.do_os(folio), ""
        except Exception as e:                          # noqa: BLE001 — sem o banco, a tela diz e não grava às cegas
            obs, erro_obs = [], "Não consegui ler as observações no banco da Gridco (%s)." % str(e)[:120]
    hoje = aw.agora_brt()
    linha, todos = _do_cache(folio)
    nota = str(o.get("nota") or "")
    criada, fim = _quando(o.get("criada")), _quando((o.get("fim") or "") + " 00:00") if o.get("fim") else None
    base = {"id": o.get("wid"), "folio": folio, "descricao": o.get("titulo"), "ativo": o.get("ativo"),
            "code": o.get("codigo"), "data": criada.isoformat() if criada else "",
            "data_fim": fim.isoformat() if fim else ""}
    linha = dict(linha or base)
    # o que o Raio X leu agora vale mais que a cópia do quadro (a situação, o fim, o responsável e a nota)
    linha.update(note=nota, status_id=STATUS_DA_COLUNA.get(o.get("coluna"), linha.get("status_id") or 1),
                 status=o.get("status") or linha.get("status") or "")
    if fim:
        linha["data_fim"] = fim.isoformat()
    resp = " ".join(str(o.get("pessoa") or "").split())
    if resp and resp != " ".join(str(linha.get("atribuido_a") or "").split()):
        linha.update(atribuido_a=resp, id_atribuido=None)
    if ticket is None:
        ticket = next((c.get("ticket") or "" for c in todos if c.get("folio") == folio), "")
    fim_tela = max((x["quando"] for x in obs if x["tipo"] == "finalizado"), default="")
    status = next((str((x.get("extra") or {}).get("status") or "").strip() for x in reversed(obs)
                   if x.get("tipo") == "status"), None)
    c = aw.cartao(linha, ticket, (obs[-1]["quando"] if obs else ""), hoje, fim_tela, status=status)
    if not c["code"]:
        c["code"] = str(o.get("codigo") or "")
    n = aw.ler_nota(nota)
    try:
        ajustes = obs_store.ajustes_do_historico(obs_store.listar(), folio)
    except Exception:                                   # noqa: BLE001 — sem o banco, o histórico sai como veio na nota
        ajustes = {}
    aberto = c["col"] in ("chegou", "ticket")
    # em verificação no Fracttal (27/11/2026, OS 17320): o chamado sai das filas de trabalho, mas só encerra com a
    # aprovação; o Finalizar fica para quem aprova
    em_verificacao = not aberto and str(c.get("status_id") or "") == "2"
    return {"c": c, "n": n, "aberto": aberto, "em_verificacao": em_verificacao, "tl": aw.linha_do_tempo(c, obs, n["historico"], ajustes),
            "outros": aw.outros(c, todos) if todos else {"ativo": [], "campo": []}, "canal": cs.CANAL.get(c["marca"], ""),
            "menos7": aw.menos_7d(n["data_falha"], hoje), "copiar": aw.copiar_tudo(n["campos"]),
            "erro_obs": erro_obs, "pode_gravar": ga.pode_gravar(), "opcoes_status": aw.STATUS_CHAMADO,
            "status_geral": aw.status_geral(c["status_ch"]), "ticket": c["ticket"]}
