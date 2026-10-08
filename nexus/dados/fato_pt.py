"""A permissão de trabalho conformada (passo 3 do Kimball, 08/10/2026), do livro que o App grava (`pt_app_campo`).

Por quê. O catálogo dizia "1 linha = 1 PT", mas a auditoria de 08/10 (GR-4, DR-4) mediu outra coisa: 233 linhas para
227 números em 08/10 (uma PT de 3 ativos aparece 3 vezes), com `Criada em`, `Código do ativo` e `Decidida em`
diferentes em cada linha: o App decide POR LINHA. Contar linhas como PT punha a mesma PT 2 ou 3 vezes no "aguardando" e
na mediana de espera.

Grão: 1 linha = 1 PT × ativo. Tipo: snapshot acumulado (a linha muda quando a PT é decidida). Chave:
`pt_linha_id = sha1(Número + "|" + Código do ativo)[:16]` — (Número, Código do ativo) é único nas 233; (Número, Tarefa)
repete 5. Para contar PTs, `SUM(primeira_linha_da_pt)`: 1 na linha de menor código de cada número, 0 nas outras.

- Datas em papéis (regra 7): `data_id_criacao` e `data_id_decisao`, dia de Brasília (o App grava em UTC).
- Pessoa só como ID e HMAC (`Solicitante (HMAC)`, `Decidida por (HMAC)`). Medido em 08/10: o decisor liga 0% — as 6
  contas que decidem têm papel "Admin" e estão fora do cadastro (decisão do Levi, spec seção 9, item 4).
- `parada` = 1 quando a espera passou de 120 min (decidida) ou quando, ainda aguardando, já passou de 120 min na hora da
  carga. Uma vez 1, fica 1: a espera de quem foi decidida depois é sempre maior que a idade que ela tinha em qualquer
  carga anterior. Decidida sem `Decidida em` = vazio (nunca volta a 0 por falta de dado).
- Fora do fato: `Motivo` (texto do supervisor), `1º aviso: motivo` (230 linhas com a mensagem de erro do e-mail, não é
  dado da PT), `Ativo` e `Tarefa` (texto; o `equipamento_id` e o código já dizem qual é), `Atividades` (só a contagem).

Herda do passo 0 (adiado pelo Levi, 08/10): o livro do App guarda 90 dias e a PT começa em 28/09; refeito a cada hora,
o fato perde a PT a partir de ~27/12/2026. Com o passo 0, o fato vira ATUALIZAÇÃO por `pt_linha_id`, não acréscimo.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import dominios as DOM
from .fato_ronda import _equip, _quando, chave, conferir_grao, linha_de_qualidade
from .fatos import _int, _sim, _txt, data_do_registro

FATO, TIPO = "pt", "snapshot_acumulado"
GRAO = "1 linha = 1 PT × ativo (o App decide por linha)"
CHAVE = ("pt_linha_id",)
FONTES = (("pt_app_campo", "PT"),)
LIVRO_ORIGEM = "pt_app_campo"
JANELA_ORIGEM = "90 dias (App)"
_BRT = timezone(timedelta(hours=-3))

CAB_PT = ["pt_linha_id", "pt", "primeira_linha_da_pt", "os", "codigo_ativo", "data_id_criacao", "data_id_decisao",
          "usina_id", "usina_ligada_por", "equipe_id", "equipamento_id", "equipamento_ligado_por",
          "solicitante_pessoa_id", "solicitante_hmac",
          "decisor_pessoa_id", "decisor_hmac", "decisor_papel", "situacao", "decidida", "criada_em", "decidida_em",
          "espera_min", "parada", "respostas_nao_qtd", "atividades_qtd", "forcada", "efeito"]
MEDIDAS = (("espera_min", "min", "aditiva"), ("respostas_nao_qtd", "qtd", "aditiva"), ("atividades_qtd", "qtd", "aditiva"),
           ("primeira_linha_da_pt", "1/0", "aditiva"), ("decidida", "1/0", "aditiva"), ("parada", "1/0", "aditiva"),
           ("forcada", "1/0", "aditiva"))
_I = {c: i for i, c in enumerate(CAB_PT)}


def _hmac(v) -> str:
    return _txt(v).split(";")[0].strip()


def _minutos(de, ate):
    a, b = _quando(de), _quando(ate)
    return int((b - a).total_seconds() // 60) if a and b else None


def fato_pt(pt: list[dict], lig, equip=None, *, agora: datetime | None = None) -> list[list]:
    """As linhas do fato. `pt`: o `pt_app_campo`; `lig`: o `Ligador`; `equip`: código do ativo -> equipamento_id
    (o módulo de equipamento; sem ele, vazio); `agora`: a hora da carga (a `parada` de quem ainda espera)."""
    agora = agora or datetime.now(_BRT)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=_BRT)
    menor = {}
    for r in pt:
        n, cod = _txt(r.get("Número")), _txt(r.get("Código do ativo"))
        if n and (n not in menor or cod < menor[n]):
            menor[n] = cod
    out = []
    for r in pt:
        n, cod = _txt(r.get("Número")), _txt(r.get("Código do ativo"))
        if not n:
            continue            # sem número não é PT (a qualidade conta pela diferença com a origem)
        uid, como = lig.usina(r.get("Usina"), cod)
        sol, dec = _hmac(r.get("Solicitante (HMAC)")), _hmac(r.get("Decidida por (HMAC)"))
        sit = DOM.pt_situacao(r.get("Situação"))
        decidida = None if sit is None else int(sit in DOM.PT_DECIDIDAS)
        criada, decidida_em = _txt(r.get("Criada em")) or None, _txt(r.get("Decidida em")) or None
        espera = _minutos(criada, decidida_em) if decidida else None
        espera = espera if espera is not None and espera >= 0 else None
        if decidida:
            parada = None if espera is None else int(espera > DOM.PT_PARADA_MIN)
        elif sit == "aguardando":
            idade = _minutos(criada, agora.isoformat())
            parada = None if idade is None else int(idade > DOM.PT_PARADA_MIN)
        else:
            parada = None
        ativs = [a for a in (x.strip() for x in _txt(r.get("Atividades")).split(";")) if a]
        eid, eq_como = _equip(equip, cod)
        out.append([
            chave(n, cod), n, int(cod == menor[n]), _txt(r.get("OS")) or None, cod or None,
            data_do_registro(criada), data_do_registro(decidida_em), uid, como, lig.equipe(r.get("Região")),
            eid, eq_como, lig.pessoa(sol) if sol else None, sol or None, lig.pessoa(dec) if dec else None,
            dec or None, DOM.codigo(r.get("Papel de quem decidiu")), sit, decidida, criada, decidida_em, espera, parada,
            _int(r.get("Respostas NÃO")), len(ativs) if _txt(r.get("Atividades")) else 0, _sim(r.get("Forçada")),
            DOM.codigo(r.get("Efeito"))])
    conferir_grao(out, CAB_PT, "pt_linha_id")
    return out


def qualidade_pt(linhas, pt_origem, origem_em, agora, *, hist=None) -> dict:
    """A linha de qualidade 'pt'. Data = criação; pessoa = solicitante. O `extra` diz quantas PTs distintas, quantas
    decididas, quantas paradas, quantos decisores ligaram e o que veio fora do domínio."""
    por_chave = {chave(_txt(r.get("Número")), _txt(r.get("Código do ativo"))): r for r in pt_origem
                 if _txt(r.get("Número"))}
    origem_q = [{"Usina": _txt((por_chave.get(l[0]) or {}).get("Usina")),
                 "Região": _txt((por_chave.get(l[0]) or {}).get("Região"))} for l in linhas]
    i = _I
    sit = Counter(l[i["situacao"]] for l in linhas)
    decididas = [l for l in linhas if l[i["decidida"]] == 1]
    extra = {"pts": sum(l[i["primeira_linha_da_pt"]] for l in linhas),
             **{f"situacao_{k}": v for k, v in sit.items() if k},
             "situacao_fora": sit.get(None, 0),
             "paradas": sum(1 for l in linhas if l[i["parada"]] == 1),
             "decisor_ligado": sum(1 for l in decididas if l[i["decisor_pessoa_id"]] is not None),
             "decisor_com_hmac": sum(1 for l in decididas if l[i["decisor_hmac"]]),
             "decidida_em_outro_dia": sum(1 for l in decididas if l[i["data_id_decisao"]]
                                          and l[i["data_id_decisao"]] != l[i["data_id_criacao"]]),
             "fora_sem_numero": sum(1 for r in pt_origem if not _txt(r.get("Número")))}
    return linha_de_qualidade(FATO, LIVRO_ORIGEM, linhas, CAB_PT, origem_q, origem_em, agora,
                              col_data="data_id_criacao", col_pessoa="solicitante_pessoa_id", hist=hist, extra=extra)
