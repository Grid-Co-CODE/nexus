"""Atividades feitas sem APR ou sem PT (24/10/2026).

A TST: "em APR e PT - preciso de uma visibilidade de atividades realizadas sem APR e sem PT, por exemplo essa APR OS
#16866 precisa de PT, porém o técnico não fez e eu só consegui ver que precisava de PT porque abri a APR". As respostas
da APR moravam só no App e no PDF anexado à OS no Fracttal; desde a v298 do servidor o App publica o livro
`apr_app_campo · APR` (registrado no catálogo antes da 1ª gravação; contrato fechado com a sessão do App de Campo):
1 linha = 1 APR de pré-execução feita no App (a do dia é uma por técnico, OS e dia, com as versões do "Novo risco"
juntas), desde 09/10/2026 (v251; antes, a APR só existe no Fracttal), janela de 90 dias.

As duas listas:
- **APR que pedia PT e ficou sem**: "Precisa de PT" = sim (uma das 5 atividades críticas marcada) e a coluna PT vazia.
  "Precisa de PT" vazio é "ainda não medido" (as APRs de antes da v298 são lidas do documento aos poucos): não entra.
  Caso real: a OS 16866 TINHA PT (PT-16866-2010-1457, da APR do dia); a TST a procurou no Fracttal, onde só vai o PDF
  da APR. A busca da tela de APR e PT acha a PT pelo número da OS.
- **OS fechada pelo App sem APR**: cada tarefa do `fato_fechamento` desde 09/10/2026 sem APR da mesma OS no mesmo dia
  de Brasília, nem APR da tarefa com a mesma OS e a mesma tarefa. Por OS e dia, com quantas tarefas. A régua não olha o
  técnico (a do App olha): melhor deixar passar um caso do que apontar quem fez a APR. Deve ser raro: o servidor do App
  barra a 1ª tarefa da OS no dia sem a APR do dia desde a v246; o que aparecer tende a ser App velho, o robô ou APR
  feita no Fracttal.
"""
from datetime import date

from ..campo import leitura, visao
from ..dados import fatos as D
from ..dados import livros

LIVRO, ABA = "apr_app_campo", "APR"
INICIO = date(2026, 10, 9)          # a fila do PDF da APR do App registra toda APR desde a v251


def _txt(v) -> str:
    return D._txt(v)


def _dia(v) -> date | None:
    try:
        return date.fromisoformat(_txt(v)[:10])
    except ValueError:
        return None


def sem_apr_ou_pt() -> leitura.Leitura:
    """{livro_existe, sem_pt: [APR que pedia PT sem PT], sem_apr: [OS e dia fechados sem APR], hoje}. Cópia de 5 min,
    renovada em segundo plano (`visao._ler`)."""
    def calcular():
        abas = visao._ciclo(("_abas", LIVRO), lambda: livros.abas(visao._base(), visao._sessao(), LIVRO))
        b = visao._Base()
        hoje = visao._agora().date()
        if ABA not in abas:
            return {"livro_existe": False, "sem_pt": [], "sem_apr": [], "hoje": hoje, **visao._estrutura(b)}
        aprs = visao._livro(LIVRO, ABA)
        quem = visao._quem() if aprs else {}
        sem_pt, por_os_dia, por_os_tarefa = [], set(), set()
        for x in aprs:
            os_, dia = _txt(x.get("OS")), _dia(x.get("Dia"))
            if os_ and dia:
                por_os_dia.add((os_, dia))
            if os_ and _txt(x.get("Tipo")) == "tarefa" and _txt(x.get("Tarefa")):
                por_os_tarefa.add((os_, D.tarefa_chave(x.get("Tarefa"))))
            if _txt(x.get("Precisa de PT")).lower() == "sim" and not _txt(x.get("PT")):
                uid, _como = b.lig.usina(_txt(x.get("Usina")), _txt(x.get("Código do ativo")))
                sem_pt.append({"dia": dia, "os": os_, "tipo": _txt(x.get("Tipo")), **b.onde(uid, _txt(x.get("Usina"))),
                               "tarefa": _txt(x.get("Tarefa")),
                               "atividades": [a.strip() for a in _txt(x.get("Atividades críticas")).split(";")
                                              if a.strip()],
                               "tecnico": visao._nome(quem, x.get("Técnico (HMAC)"))})
        grupos = {}
        f = visao._fato("fechamento", b)
        for x in f["linhas"]:
            os_, quando = _txt(x.get("os")), visao._dt(x.get("registrado_em"))
            if not os_ or not quando or quando.date() < INICIO:
                continue
            dia = quando.date()
            if (os_, dia) in por_os_dia or (os_, _txt(x.get("tarefa_chave"))) in por_os_tarefa:
                continue
            uid = D._id(x.get("usina_id"))
            g = grupos.setdefault((os_, dia), {"dia": dia, "os": os_, **(b.onde(uid) if uid else {"usina": ""}),
                                               "tarefas": 0,
                                               "tipo_os": _txt(x.get("tipo_os")), "pessoas": set()})
            g["tarefas"] += 1
            if D._id(x.get("pessoa_id")):
                g["pessoas"].add(D._id(x.get("pessoa_id")))
        nomes = b.nomes({p for g in grupos.values() for p in g["pessoas"]})
        sem_apr = [dict(g, tecnico=", ".join(sorted(nomes.get(p) or f"Técnico {p}" for p in g.pop("pessoas"))))
                   for g in grupos.values()]
        chave = (lambda r: (r["dia"] or INICIO, r["os"]))
        return {"livro_existe": True, "sem_pt": sorted(sem_pt, key=chave, reverse=True),
                "sem_apr": sorted(sem_apr, key=chave, reverse=True), "hoje": hoje, "aviso_fato": f.get("aviso", ""),
                **visao._estrutura(b)}
    return visao._ler(("hseq_sem_apr",), calcular)
