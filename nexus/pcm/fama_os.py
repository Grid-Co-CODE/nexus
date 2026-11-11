"""As OS da FAMA para o PCM: a porta única (`_linhas_fama`), o vocabulário da FAMA e a usina de cada OS (11/11/2026).

Levi, 11/11/2026: o cliente cria a OS na FAMA, ela aparece para o programador e cai no App de Campo; as retroativas abertas
também entram ("a ideia é não ficarmos criando e editando e sim acompanhando"). A FASE 1 é sombra: as OS da FAMA aparecem
no Quadro da semana (`fama_quadro.py`) e o adaptador do motor (`fama_motor.py`) fica pronto e desligado.

De onde vem: o livro `nexus_os_fama · fato_os_fama` (com o `dim_projeto_fama`), que a carga de hora em hora mantém a
partir da API da FAMA (`nexus/dados/fama.py`, a parte A). O PCM não lê a FAMA nem o livro por conta própria: tudo entra
por `_linhas_fama(config)`, e é só ela que se ajusta quando as partes se juntam. O título e a descrição moram cifrados no
livro (Cofre do cadastro): chegam aqui já decifrados, em `titulo`, só em memória, para a tela; nunca vão para log nem
para o motor (o log do motor imprime o texto das tarefas).

Os valores da FAMA (o catálogo de lá, em inglês) ficam como vieram no dado; a tela fala português pelas tabelas abaixo, e
valor que a tabela não conhece aparece como veio (dado é dado).
"""
import importlib.util
import re
from datetime import date

from ..cadastro.ligacao_campo import SISTEMA_FRACTTAL      # o de-para do Fracttal ("Fracttal · Classificação 1")
from .semana import _norm

# a situação da OS na FAMA (o `status` do catálogo de lá)
ABERTAS = ("created", "planned", "paused")
EM_ANDAMENTO = ("under mobilization", "under execution")
STATUS_PT = {"created": "Criada", "planned": "Planejada", "paused": "Pausada", "under mobilization": "Em mobilização",
             "under execution": "Em execução", "under review": "Em revisão", "executed": "Executada",
             "approved": "Aprovada", "closed": "Fechada"}
# o "Estado da Tarefa" do Fracttal que cada uma é (o filtro de situação do Quadro e a linha do motor)
ESTADO_DA_TAREFA = {"created": "Não Iniciada", "planned": "Não Iniciada", "paused": "pausado",
                    "under mobilization": "Em progresso", "under execution": "Em progresso"}
TIPO_PT = {"corrective": "Corretiva", "preventive/predictive": "Preventiva/Preditiva",
           "vegetation control": "Controle de vegetação", "modules cleaning": "Limpeza de módulos",
           "equipments and materials movement": "Movimentação de equipamentos e materiais"}
# a preventiva da FAMA (a etiqueta de repetição do Quadro olha só esta: limpeza e roçada não repetem uma MPM)
PREVENTIVA = "preventive/predictive"
SEVERIDADE_PT = {"critical": "Crítica", "urgent": "Urgente", "routine": "Rotina", "non-urgent": "Não urgente"}


def inteiro(v) -> int | None:
    """O número de um ID (usina_id, fama_os_id), ou None."""
    try:
        i = int(float(str(v).strip()))
    except (TypeError, ValueError, OverflowError):
        return None
    return i if i > 0 else None


def situacao(status) -> str | None:
    """ "aberta" (criada, planejada, pausada), "andamento" (em mobilização, em execução) ou None (em revisão, executada,
    aprovada, fechada e o que não for do catálogo: não é trabalho a programar)."""
    s = _norm(status)
    if s in ABERTAS:
        return "aberta"
    if s in EM_ANDAMENTO:
        return "andamento"
    return None


def numero(fama_os_id) -> str:
    """O número que a tela mostra: FAMA-<id>."""
    i = inteiro(fama_os_id)
    return f"FAMA-{i if i is not None else str(fama_os_id or '').strip()}"


def data_de(v) -> date | None:
    """O `data_id` (AAAAMMDD, o da dimensão de data) em data; aceita também "AAAA-MM-DD". Vazio ou inválido: None."""
    s = str(v if v is not None else "").strip()
    if not s:
        return None
    try:
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(?:\.0+)?", s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _linhas_fama(config) -> list[dict]:
    """A ÚNICA entrada das OS da FAMA no PCM: todas as linhas do `fato_os_fama` (qualquer situação: o Quadro escolhe as
    da semana e o adaptador do motor acha nelas as usinas da FAMA), cada uma um dict com `fama_os_id`, `usina_id` (None
    = sem usina ligada em Base → Ligações), `status`, `tipo`, `severidade`, `data_id_prevista`, `data_id_criacao` e
    `titulo` (decifrado, só em memória). Sem o leitor da parte A (`nexus/dados/fama.py`) nesta máquina, nenhuma linha. No
    teste, as linhas de `NEXUS_FAMA_LINHAS_TESTE` (teste não vai ao banco). Erro de leitura sobe: quem chama decide (o
    Quadro avisa; a rodada com `NEXUS_FAMA_PROGRAMA=1` não sai). Quem junta as partes ajusta só esta função."""
    if config.get("TESTING"):
        return [dict(l) for l in config.get("NEXUS_FAMA_LINHAS_TESTE") or []]
    if importlib.util.find_spec("nexus.dados.fama") is None:
        return []
    from ..dados import conexao, fama
    return [dict(l) for l in fama.ler_banco(*conexao.banco_de(config)) or []]


# ── a usina de cada OS: o cadastro do banco ──────────────────────────────────────────────────────────────────────
DO_CADASTRO = (("cadastro_nexus", "usinas"), ("cadastro_nexus", "de_para"), ("cadastro_nexus", "equipes"),
               ("cadastro_nexus", "clientes"))


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def usinas_do_cadastro(usinas, de_para, equipes=(), clientes=()) -> dict[int, dict]:
    """{usina_id: {"nomes": os nomes da usina no Fracttal pelo de-para, "nome": o do cadastro, "cliente", "equipe"}}.
    Os nomes do Fracttal são os do de-para (sistema "Fracttal · Classificação 1"), a mesma ligação do
    `tecnicos_usina._fracttal`; o "(sem Classificação …)" vai por último, porque é o agrupamento do Fracttal para o
    ativo sem classificação, não o nome da usina. A usina excluída do cadastro não entra."""
    nome_equipe = {inteiro(e.get("equipe_id")): _txt(e.get("nome")) for e in equipes}
    nome_cliente = {inteiro(c.get("cliente_id")): _txt(c.get("nome")) for c in clientes}
    out: dict[int, dict] = {}
    for u in usinas:
        uid = inteiro(u.get("usina_id"))
        if not uid or _txt(u.get("excluido")).lower() == "sim":
            continue
        out[uid] = {"nomes": [], "nome": _txt(u.get("nome")), "cliente": nome_cliente.get(inteiro(u.get("cliente_id")), ""),
                    "equipe": nome_equipe.get(inteiro(u.get("equipe_id")), "")}
    for d in de_para:
        uid = inteiro(d.get("usina_id"))
        nome = " ".join(_txt(d.get("chave_externa")).split())
        if uid in out and nome and _txt(d.get("sistema")) == SISTEMA_FRACTTAL and nome not in out[uid]["nomes"]:
            out[uid]["nomes"].append(nome)
    for x in out.values():
        x["nomes"].sort(key=lambda n: (_norm(n).startswith("(sem classificacao"), n))
    return out


def cadastro_das_usinas(config) -> dict[int, dict]:
    """O `usinas_do_cadastro` do banco agora. Numa tela (há o app), pela cópia de 2 min das telas do Campo, com uma
    listagem só (`campo.visao.carregar`); fora dela (a ferramenta da foto), direto pelo `livros.ler`. No teste, o
    `NEXUS_FAMA_CADASTRO_TESTE` (já na forma de saída). Erro de leitura sobe."""
    if config.get("TESTING"):
        return dict(config.get("NEXUS_FAMA_CADASTRO_TESTE") or {})
    from flask import has_app_context
    if has_app_context():
        from ..campo import visao
        visao.carregar(DO_CADASTRO)
        lido = {aba: visao._livro(livro, aba) for livro, aba in DO_CADASTRO}
    else:
        from ..dados import conexao, livros
        base, sessao = conexao.banco_de(config)
        lido = {aba: livros.ler(base, sessao, livro, aba) for livro, aba in DO_CADASTRO}
    return usinas_do_cadastro(lido["usinas"], lido["de_para"], lido["equipes"], lido["clientes"])
