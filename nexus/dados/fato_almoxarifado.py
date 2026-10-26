"""Os fatos do almoxarifado (25/10/2026): o saldo por ciclo da varredura, os ciclos e as peças lançadas pelo App.

O livro do App guarda só o ÚLTIMO ciclo (o `sync-xlsx` com `replace` troca o livro inteiro): sem o Nexus guardar, o
saldo de ontem se perde. Aqui se monta o que a carga (`carga.gerar_almoxarifado`) acrescenta ao banco:
- `fato_saldo_almox`, uma foto por ciclo completo (~270 linhas), num livro por mês (`nexus_almoxarifado_saldo_AAAA_MM`).
  Foto, e não intervalos: o dia sem ciclo fica sem foto ("não medido" não vira "não mudou"), e nada fecha período por
  ausência (regra 6 do `nexus/dados/CLAUDE.md`). A releitura do Admin no mesmo dia é outra foto, com o mesmo data_id;
- `fato_ciclo_varredura`, cada ciclo que o Nexus viu, aplicado ou recusado (e a marca de anulado);
- `fato_peca_lancada`, cada peça lançada ou recusada pelo App; o reenvio de uma recusada regrava a linha, e a do banco
  que saiu da janela de 90 dias do App fica;
- `dim_item_almox` e `dim_almoxarifado`, que nunca encolhem.

Ligações (regra 4: não liga = vazio): a usina do almoxarifado pelo local "Cliente - Usina - UF", que é a mesma chave da
Classificação 1 do Fracttal, SÓ pela de-para (`Ligador.usina_do_fracttal`), nunca pelo código: o código de usina pode
ser de dois clientes. A pessoa pelo HMAC. O texto do erro do Fracttal e o da tarefa não entram (regra 8): a recusa vai
como o domínio `dominios.RECUSA_PECA`, e a tarefa como `tarefa_chave`. Módulo puro: nada de rede.
"""
import hashlib
import json

from . import almoxarifado as A
from .calendario import data_id
from .dominios import RECUSA_PECA, norm
from .fatos import CAB_QUALIDADE, tarefa_chave
from .historico import dia_brt

LIVRO = "nexus_almoxarifado"
NOME_LIVRO = "Nexus · almoxarifado: ciclos da varredura, peças lançadas pelo App, o item e o almoxarifado"
ABA_CICLO, ABA_PECA = "fato_ciclo_varredura", "fato_peca_lancada"
ABA_DIM_ITEM, ABA_DIM_ALMOX = "dim_item_almox", "dim_almoxarifado"
ABA_SALDO = "fato_saldo_almox"
LIVRO_SALDO_MOLDE = "nexus_almoxarifado_saldo_{:04d}_{:02d}"
LIGADA_DE_PARA = "de-para do Fracttal"

CAB_SALDO = ["saldo_id", "ciclo_inicio", "data_id", "id_item", "codigo", "id_almoxarifado", "usina_id",
             "usina_ligada_por", "saldo_qtd", "minimo_qtd"]
CAB_CICLO = ["ciclo_inicio", "data_id", "fim", "itens_lista_qtd", "itens_lidos_qtd", "erros_qtd", "origem",
             "situacao", "porque", "anulado", "visto_em"]
CAB_PECA = ["lancamento_id", "data_id", "data_id_recebida", "os", "codigo_ativo", "tarefa_chave", "id_item", "codigo",
            "id_almoxarifado", "usina_id", "usina_ligada_por", "pessoa_id", "quantidade_qtd", "lancada", "recusa"]
CAB_DIM_ITEM = ["id_item", "codigo", "nome", "unidade", "familia", "avariado", "ferramenta"]
CAB_DIM_ALMOX = ["id_almoxarifado", "nome", "local", "usina_id", "usina_ligada_por"]
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "como_ler", "ciclo_inicio", "sha_pecas"]
LIVRO_ORIGEM = {"saldo_almox": f"{A.LIVRO_SALDO} · {A.ABA_SALDO}", "ciclo_varredura": f"{A.LIVRO_CICLO} · {A.ABA_CICLO}",
                "peca_lancada": f"{A.LIVRO_PECAS} · {A.ABA_PECAS}"}


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _dia(iso) -> int | None:
    d = dia_brt(iso) if _txt(iso) else None
    return data_id(d) if d else None


def _sim(v) -> int:
    return 1 if norm(v) in ("sim", "1", "true", "verdadeiro") else 0


def _int(v):
    n = A.numero(v)
    return int(n) if n is not None else None


def _chave_id(v) -> str:
    """IDs do Fracttal ordenados como número quando são número (o "9" antes do "10"), e o sha não varia."""
    t = _txt(v)
    return t.zfill(20) if t.isdigit() else t


def livro_do_mes(dia: int) -> str:
    return LIVRO_SALDO_MOLDE.format(int(dia) // 10000, int(dia) // 100 % 100)


def _usina(lig, local) -> tuple:
    uid = lig.usina_do_fracttal(A.chave_do_local(local)) if A.chave_do_local(local) else None
    return (uid, LIGADA_DE_PARA) if uid else (None, None)


def saldo_do_ciclo(saldo: list[dict], lig) -> list[list]:
    """A foto do ciclo: uma linha por item × almoxarifado, ordenada (as duas máquinas dão as mesmas linhas)."""
    out = []
    for s in saldo:
        inicio, item, almox = _txt(s.get(A.INICIO)), _txt(s.get("ID do item")), _txt(s.get("ID do almoxarifado"))
        uid, por = _usina(lig, s.get("Local do almoxarifado"))
        sid = hashlib.sha1(f"{inicio}|{item}|{almox}".encode("utf-8")).hexdigest()[:20]
        out.append([sid, inicio, _dia(inicio), item, _txt(s.get("Código")), almox, uid, por,
                    A.numero(s.get("Saldo")), A.numero(s.get("Mínimo"))])
    return sorted(out, key=lambda l: (l[1], _chave_id(l[3]), _chave_id(l[5])))


def dim_itens(itens: list[dict]) -> list[list]:
    return sorted(([_txt(i.get("ID do item")), _txt(i.get("Código")), _txt(i.get("Nome")), _txt(i.get("Unidade")),
                    _txt(i.get("Família")), _sim(i.get("Avariado")), _sim(i.get("Ferramenta"))]
                   for i in itens if _txt(i.get("ID do item"))), key=lambda l: _chave_id(l[0]))


def dim_almoxarifados(saldo: list[dict], lig) -> list[list]:
    por = {}
    for s in saldo:
        aid = _txt(s.get("ID do almoxarifado"))
        if aid and aid not in por:
            uid, como = _usina(lig, s.get("Local do almoxarifado"))
            por[aid] = [aid, _txt(s.get("Almoxarifado")), A.chave_do_local(s.get("Local do almoxarifado")), uid, como]
    return [por[k] for k in sorted(por, key=_chave_id)]


def mesclar_dim(no_banco: list[dict], novas: list[list], chave: str, cab: list) -> list[list]:
    """A dimensão nunca encolhe: o item que não veio neste ciclo (desativado no Fracttal) segue, para as fotos antigas
    continuarem ligando; o que veio troca a linha."""
    i = cab.index(chave)
    por = {_txt(d.get(chave)): [d.get(c) for c in cab] for d in no_banco if _txt(d.get(chave))}
    por.update({_txt(l[i]): list(l) for l in novas})
    return [por[k] for k in sorted(por, key=_chave_id)]


def _recusa(p: dict) -> str:
    if norm(p.get("Situação")) == "lancada":
        return ""
    m = norm(p.get("Motivo da recusa"))
    return next((r for r in RECUSA_PECA if norm(r) == m), "outro")


def mesclar_pecas(no_banco: list[dict], app: list[dict], lig, almox: dict) -> list[list]:
    """As peças do banco com as do App por cima (`lancamento_id`; vale a do App: a recusada reenviada vira lançada). A
    do banco que saiu da janela de 90 dias do App fica. `almox`: ID do almoxarifado -> (usina_id, por onde ligou), da
    `dim_almoxarifado`. A data é a do uso (o celular; a fila offline atrasa o recebimento), e a do recebimento quando o
    App não mandou o uso (as linhas de antes da mudança do App)."""
    por = {_txt(d.get("lancamento_id")): [d.get(c) for c in CAB_PECA] for d in no_banco if _txt(d.get("lancamento_id"))}
    for p in app:
        lid = _txt(p.get("ID do lançamento"))
        if not lid:
            continue
        recebida = _dia(p.get("Recebido em"))
        uid, por_onde = almox.get(_txt(p.get("ID do almoxarifado")), (None, None))
        por[lid] = [lid, _dia(p.get("Usada em")) or recebida, recebida, _txt(p.get("OS")),
                    _txt(p.get("Código do ativo")), tarefa_chave(p.get("Tarefa")), _txt(p.get("ID do item")),
                    _txt(p.get("Código")), _txt(p.get("ID do almoxarifado")), uid, por_onde,
                    lig.pessoa(p.get("Lançado por (HMAC)")), A.numero(p.get("Quantidade")),
                    1 if norm(p.get("Situação")) == "lancada" else 0, _recusa(p)]
    return [por[k] for k in sorted(por)]


def linha_ciclo(ciclo: dict, situacao: str, porque: str, visto_em: str) -> list:
    inicio = _txt(ciclo.get(A.INICIO))
    return [inicio, _dia(inicio), _txt(ciclo.get("Fim do ciclo")), _int(ciclo.get("Itens na lista do Fracttal")),
            _int(ciclo.get("Itens lidos")), _int(ciclo.get("Erros")), _txt(ciclo.get("Origem")), situacao, porque, 0,
            visto_em]


def _pct(n, total) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def linha_qualidade(fato: str, linhas: list[list], cab: list, origem_em: str, agora: str, *, sem_usina=(),
                    extra: dict | None = None) -> list:
    """A linha da aba `qualidade` no cabeçalho da casa (`fatos.CAB_QUALIDADE`), preenchida pelo nome da coluna."""
    n = len(linhas)
    com = {c: sum(1 for l in linhas if l[cab.index(c)] not in (None, "")) for c in ("data_id", "usina_id", "pessoa_id")
           if c in cab}
    por_de_para = sum(1 for l in linhas if "usina_ligada_por" in cab and l[cab.index("usina_ligada_por")] == LIGADA_DE_PARA)
    valores = {"fato": fato, "livro_origem": LIVRO_ORIGEM.get(fato, ""), "linhas": n,
               "com_data": com.get("data_id"), "com_usina": com.get("usina_id"), "com_pessoa": com.get("pessoa_id"),
               "pct_data": _pct(com["data_id"], n) if "data_id" in com else None,
               "pct_usina": _pct(com["usina_id"], n) if "usina_id" in com else None,
               "pct_pessoa": _pct(com["pessoa_id"], n) if "pessoa_id" in com else None,
               "usina_por_de_para": por_de_para if "usina_id" in com else None, "usina_por_codigo": 0 if "usina_id" in com else None,
               "sem_usina_exemplos": "; ".join(sorted(set(sem_usina))[:5]), "origem_atualizada_em": origem_em,
               "gerado_em": agora, "extra": json.dumps(extra or {}, ensure_ascii=False, separators=(",", ":"))}
    return [valores.get(c) for c in CAB_QUALIDADE]
