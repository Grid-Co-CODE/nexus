"""As OS da FAMA para o PCM: a porta única (`_linhas_fama`), o vocabulário da FAMA e a usina de cada OS (11/11/2026).

Levi, 11/11/2026: o cliente cria a OS na FAMA, ela aparece para o programador e cai no App de Campo; as retroativas abertas
também entram ("a ideia é não ficarmos criando e editando e sim acompanhando"). A FASE 1 é sombra: as OS da FAMA aparecem
no Quadro da semana (`fama_quadro.py`) e o adaptador do motor (`fama_motor.py`) fica pronto e desligado.

De onde vem: o livro `nexus_os_fama · fato_os_fama` (com o `dim_projeto_fama`), que a volta de 10 em 10 minutos mantém
a partir da API da FAMA (`nexus/dados/fama.py`, a parte A). O PCM não lê a FAMA nem o livro por conta própria: tudo entra
por `_linhas_fama(config)`, que lê o livro pelo `fama.ler_banco`. O título e a descrição moram cifrados no livro (Cofre do
cadastro): só o TÍTULO das OS abertas e em andamento é decifrado aqui, só em memória, para a tela; a descrição nunca, e
nada disso vai para log nem para o motor (o log do motor imprime o texto das tarefas).

O frescor: a porta devolve também o `gerado_em` da aba `atualizacao` (o batimento: a carga grava ao menos uma vez por dia,
mesmo sem mudança). Mais de `FRESCOR_H` sem batimento é a leitura da FAMA parada (`velho`): o Quadro avisa, e a rodada
com `NEXUS_FAMA_PROGRAMA=1` não sai.

Os valores da FAMA (o catálogo de lá, em inglês) ficam como vieram no dado; a tela fala português pelas tabelas abaixo, e
valor que a tabela não conhece aparece como veio (dado é dado).
"""
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from ..cadastro.ligacao_campo import SISTEMA_FRACTTAL      # o de-para do Fracttal ("Fracttal · Classificação 1")
from .semana import _norm

_BRT = timezone(timedelta(hours=-3))
# o batimento da carga é diário (`nexus/dados/fama.py`): 24 h e uma folga de 2 h para a volta atrasar
FRESCOR_H = 26

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


def _quando_dt(gerado_em) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(gerado_em or "").strip())
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=_BRT)


def velho(gerado_em, agora: datetime | None = None) -> bool:
    """A leitura da FAMA parou? Mais de `FRESCOR_H` desde o último batimento, ou batimento que não se lê (sem saber, vale
    como parado: nem o Quadro cala nem a rodada ligada sai)."""
    d = _quando_dt(gerado_em)
    return d is None or (agora or datetime.now(_BRT)) - d > timedelta(hours=FRESCOR_H)


def quando(gerado_em) -> str:
    """O batimento como a tela diz: "DD/MM HH:MM", em Brasília (vazio se não se lê)."""
    d = _quando_dt(gerado_em)
    return d.astimezone(_BRT).strftime("%d/%m %H:%M") if d else ""


@dataclass
class Lido:
    """O que a porta devolve: as OS e o batimento da carga (o `gerado_em` da aba `atualizacao`)."""
    linhas: list = field(default_factory=list)
    gerado_em: str | None = None


def _linhas_fama(config) -> Lido:
    """A ÚNICA entrada das OS da FAMA no PCM: todas as linhas do `fato_os_fama` (qualquer situação: o Quadro escolhe as
    da semana e o adaptador do motor acha nelas as usinas da FAMA), cada uma um dict com `fama_os_id`, `usina_id` (None
    = sem usina ligada em Base → Ligações), `status`, `tipo`, `severidade`, `data_id_prevista`, `data_id_criacao` e
    `titulo`, e o batimento da carga. Sem o livro no banco (antes da 1ª leitura do servidor), nenhuma linha e nenhum
    batimento. No teste, as linhas de `NEXUS_FAMA_LINHAS_TESTE` e o batimento de `NEXUS_FAMA_GERADO_EM_TESTE` (teste não
    vai ao banco). Erro de leitura sobe: quem chama decide (o Quadro avisa; a rodada com `NEXUS_FAMA_PROGRAMA=1` não
    sai). Lê o livro `nexus_os_fama` pela parte A (`nexus/dados/fama.ler_banco`).

    Só o título das OS abertas e em andamento é decifrado, em memória (revisão de 11/11/2026: o `textos` da parte A
    decifrava também a descrição, que o PCM não mostra, e uma cifra quebrada nela apagava o título). Sem a chave do
    cadastro, ou com outra, a OS vale sem o título: o Quadro nunca cai."""
    if config.get("TESTING"):
        return Lido([dict(l) for l in config.get("NEXUS_FAMA_LINHAS_TESTE") or []],
                    config.get("NEXUS_FAMA_GERADO_EM_TESTE"))
    from ..cadastro.cifra import CifraErro, Cofre
    from ..dados import conexao, fama
    from ..dados import fato_os_fama as FO
    livro = fama.ler_banco(*conexao.banco_de(config)) or {}
    try:
        chave = (config.get("NEXUS_CHAVE_CADASTRO") or "").strip()
        cofre = Cofre(chave) if chave else None
    except Exception:           # noqa: BLE001 — chave que não abre o Cofre
        cofre = None
    out = []
    for linha in livro.get(FO.ABA) or []:
        d = {k: v for k, v in linha.items() if k not in ("titulo_cifrado", "descricao_cifrada")}
        oid = FO.id_fama(linha.get("fama_os_id"))     # o banco pode devolver "10.0" ou um código em texto
        d["fama_os_id"] = oid
        for c in ("usina_id", "data_id_prevista", "data_id_criacao", "data_id_fim"):
            d[c] = inteiro(linha.get(c))
        d["titulo"] = None
        if cofre is not None and situacao(d.get("status")) is not None and linha.get("titulo_cifrado"):
            try:
                d["titulo"] = cofre.decifrar(str(linha["titulo_cifrado"]), FO.contexto(oid, "titulo"))
            except (CifraErro, ValueError, TypeError):
                pass
        out.append(d)
    batimento = (livro.get("atualizacao") or [{}])[0]
    return Lido(out, str(batimento.get("gerado_em") or "").strip() or None)


# ── a usina de cada OS: o cadastro do banco ──────────────────────────────────────────────────────────────────────
DO_CADASTRO = (("cadastro_nexus", "usinas"), ("cadastro_nexus", "de_para"), ("cadastro_nexus", "equipes"),
               ("cadastro_nexus", "clientes"))


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def usinas_do_cadastro(usinas, de_para, equipes=(), clientes=(), gestores=None) -> dict[int, dict]:
    """{usina_id: {"nomes": os nomes da usina no Fracttal pelo de-para, "nome": o do cadastro, "cliente", "equipe",
    "gestor_id", "responsavel": o nome do gestor de contrato (`gestores`: {pessoa_id: nome}, decifrados por quem chama)}}.
    O responsável é o da coluna Responsável da programação (a AUXILIAR do motor escreve o Gestor de Contrato da ficha).
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
        gid = inteiro(u.get("gestor_contrato_id"))
        out[uid] = {"nomes": [], "nome": _txt(u.get("nome")), "cliente": nome_cliente.get(inteiro(u.get("cliente_id")), ""),
                    "equipe": nome_equipe.get(inteiro(u.get("equipe_id")), ""), "gestor_id": gid,
                    "responsavel": (gestores or {}).get(gid, "")}
    for d in de_para:
        uid = inteiro(d.get("usina_id"))
        nome = " ".join(_txt(d.get("chave_externa")).split())
        if uid in out and nome and _txt(d.get("sistema")) == SISTEMA_FRACTTAL and nome not in out[uid]["nomes"]:
            out[uid]["nomes"].append(nome)
    for x in out.values():
        x["nomes"].sort(key=lambda n: (_norm(n).startswith("(sem classificacao"), n))
    return out


def _nomes_dos_gestores(config, pessoas, ids) -> dict[int, str]:
    """{pessoa_id: nome} dos gestores pedidos, decifrados da ficha (o nome inteiro, o mesmo que a AUXILIAR escreve no
    Gestor de Contrato). Sem a chave do cadastro, ou cifra de outra chave: sem nome (a OS fica sem responsável)."""
    chave = (config.get("NEXUS_CHAVE_CADASTRO") or "").strip()
    if not chave or not ids:
        return {}
    from ..cadastro.cifra import CifraErro, Cofre
    try:
        cofre = Cofre(chave)
    except CifraErro:
        return {}
    out = {}
    for p in pessoas:
        pid = inteiro(p.get("pessoa_id"))
        if pid in ids and p.get("sensivel_cifrado"):
            try:
                s = json.loads(cofre.decifrar(str(p["sensivel_cifrado"]), f"banco/pessoas/{pid}"))
            except (CifraErro, ValueError):
                continue
            out[pid] = " ".join(_txt(s.get("nome") or s.get("nome_padrao")).split())
    return out


def cadastro_das_usinas(config, gestores_de=None) -> dict[int, dict]:
    """O `usinas_do_cadastro` do banco agora; com `gestores_de` (as usinas cujo gestor de contrato interessa: as da FAMA
    no Quadro), também o nome do gestor, decifrado da ficha da pessoa. Numa tela ou na renovação por trás (há o app), pela
    cópia de 2 min das telas do Campo, com uma listagem só (`campo.visao.carregar`); fora dela (a ferramenta da foto),
    direto pelo `livros.ler`. No teste, o `NEXUS_FAMA_CADASTRO_TESTE` (já na forma de saída). Erro de leitura sobe."""
    if config.get("TESTING"):
        return dict(config.get("NEXUS_FAMA_CADASTRO_TESTE") or {})
    pares = DO_CADASTRO + ((("cadastro_nexus", "pessoas"),) if gestores_de else ())
    from flask import has_app_context
    if has_app_context():
        from ..campo import visao
        visao.carregar(pares)
        lido = {aba: visao._livro(livro, aba) for livro, aba in pares}
    else:
        from ..dados import conexao, livros
        base, sessao = conexao.banco_de(config)
        lido = {aba: livros.ler(base, sessao, livro, aba) for livro, aba in pares}
    gestores = {}
    if gestores_de:
        ids = {inteiro(u.get("gestor_contrato_id")) for u in lido["usinas"] if inteiro(u.get("usina_id")) in gestores_de}
        gestores = _nomes_dos_gestores(config, lido["pessoas"], ids - {None})
    return usinas_do_cadastro(lido["usinas"], lido["de_para"], lido["equipes"], lido["clientes"], gestores)
