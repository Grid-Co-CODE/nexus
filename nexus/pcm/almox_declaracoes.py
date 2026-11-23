"""As declarações do técnico sobre o almoxarifado da usina, a confirmar pelo PCM no Inventário (23/11/2026).

O PCM, 23/11/2026: "quando o técnico botar que não tem almoxarifado, mostra aqui para mim no inventário" e "no app de campo
[...] botar que a usina é compartilhada e botar qual usina ela compartilha". O App de Campo grava cada declaração no livro
`almoxarifado_declaracoes_app_campo · Declaracoes` (o contrato em `nexus/dados/almoxarifado.py`). O Levi decidiu no mesmo
dia: a declaração NÃO muda nada sozinha (não tira a cobrança do App nem dá pontos); quem decide é o PCM, que confirma (a
marcação em Usinas e almoxarifados, `almox_usinas.marcar`, com as regras de lá) ou marca a usina como Próprio.

A declaração a confirmar é a ÚLTIMA de cada usina enquanto o PCM não decidiu nada daquela usina depois dela e a marcação de
hoje não é já a declarada. A que não se confirma como veio (a usina ou a dona fora da lista, a dona de outro cliente, a cadeia)
aparece com o porquê e sem o Confirmar. Só lê: a cópia de 2 min dos livros do App (`visao._livro`) e o livro das usinas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..dados import almox_usinas as AU
from ..dados import almoxarifado as A
from . import almox_usinas as P

_BRT = timezone(timedelta(hours=-3))


def _instante(iso) -> datetime | None:
    try:
        d = datetime.fromisoformat(P._txt(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _sem_ponto_final(texto: str) -> str:
    return texto.replace(" Nada foi gravado.", "").strip()


def pendentes(cfg, b=None) -> dict:
    """{"itens": [...], "erro"}: as declarações a confirmar, a mais nova primeiro. Cada item: `id`, `usina_id` (None se a usina
    não está na lista), `usina`, `situacao`, `rotulo`, `dona_id`, `dona`, `quando_txt`, `tecnico`, `observacao`,
    `contagem_id`, `confirmavel` e `problema` (o porquê de não se confirmar como veio)."""
    from ..campo import visao
    try:
        linhas = visao._livro(A.LIVRO_DECLARACOES, A.ABA_DECLARACOES)
    except Exception as ex:      # noqa: BLE001 — o banco fora: a tela diz, e não mostra "nenhuma"
        return {"itens": [], "erro": f"Não consegui ler as declarações dos técnicos agora ({type(ex).__name__})."}
    if not linhas:
        return {"itens": [], "erro": ""}
    b = b or visao._Base()
    usinas = P.usinas_com_fracttal(b)
    por_local = {}
    for u in usinas.values():
        for local in u["locais"]:
            por_local.setdefault(P._norm(local), u["id"])
    est = AU.ler(cfg)
    marcadas = est["marcadas"]
    ultima_decisao: dict[int, datetime] = {}
    for d in est["decisoes"]:
        uid, quando = AU._int(d.get("usina_id")), _instante(d.get("decidida_em"))
        if uid and quando and (uid not in ultima_decisao or quando > ultima_decisao[uid]):
            ultima_decisao[uid] = quando
    # a última declaração de cada usina (pelo nome que o App mandou)
    ultimas: dict[str, tuple] = {}
    for l in linhas:
        quando = _instante(l.get("Declarada em"))
        chave = P._norm(l.get("Usina"))
        if not chave or quando is None:
            continue
        if chave not in ultimas or quando > ultimas[chave][0]:
            ultimas[chave] = (quando, l)
    quem = visao._quem()
    itens = []
    for chave, (quando, l) in ultimas.items():
        uid = por_local.get(chave)
        sit = P._txt(l.get("Situação")).lower()
        dona_nome = P._txt(l.get("Usina dona"))
        dona_id = por_local.get(P._norm(dona_nome)) if dona_nome else None
        if uid and ultima_decisao.get(uid) and ultima_decisao[uid] >= quando:
            continue                                   # o PCM decidiu depois da declaração
        atual = marcadas.get(uid) if uid else None
        if atual and atual["situacao"] == sit and (atual.get("usina_dona_id") or None) == (dona_id if sit == AU.COMPARTILHA else None):
            continue                                   # já está marcada como o técnico disse
        problema = ""
        if not uid:
            problema = "A usina não está na lista de Usinas e almoxarifados (sem o local no Fracttal no cadastro)."
        elif sit not in A.SITUACOES_DECLARADAS:
            problema = f"Situação que o Nexus não conhece: {sit or 'vazia'}."
        elif sit == AU.COMPARTILHA and not dona_id:
            problema = "A usina dona não está na lista de Usinas e almoxarifados."
        else:
            try:
                P.conferir(usinas, marcadas, uid, sit, dona_id if sit == AU.COMPARTILHA else None)
            except AU.Recusada as ex:
                problema = _sem_ponto_final(str(ex))
        u = usinas.get(uid) if uid else None
        itens.append({"id": P._txt(l.get("ID da declaração")), "usina_id": uid,
                      "usina": u["nome"] if u else P._txt(l.get("Usina")), "situacao": sit,
                      "rotulo": P.ROTULO.get(sit, sit), "tom": P.TOM.get(sit, "neutro"),
                      "dona_id": dona_id if sit == AU.COMPARTILHA else None,
                      "dona": (usinas[dona_id]["nome"] if dona_id in usinas else dona_nome) if sit == AU.COMPARTILHA else "",
                      "quando": quando, "quando_txt": quando.astimezone(_BRT).strftime("%d/%m/%Y às %H:%M"),
                      "tecnico": visao._nome(quem, l.get("Técnico (HMAC)")) or "um técnico",
                      "observacao": P._txt(l.get("Observação"))[:300], "contagem_id": P._txt(l.get("ID da contagem")),
                      "confirmavel": not problema, "problema": problema})
    itens.sort(key=lambda x: x["quando"], reverse=True)
    return {"itens": itens, "erro": ""}
