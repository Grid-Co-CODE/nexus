"""Quem cuida de quê nos contratos: a visão reduzida (Comando › Contratos › Todos os contratos, 26/11/2026).

As regras de Atendimento, Entregáveis, Metas e Financeiro dos contratos lidos juntadas em ATIVIDADES, cada uma com um setor
dono e quem também acompanha. O pedido: "uma visão reduzida [...] Esse lance de resposta à falha [...] isso aí é PCM.
Perda de comunicação [...] isso daí é COS [...] Ameaça à segurança [...] setor de segurança [...] Sobreaviso fora do
expediente [...] no supervisor" (Levi, 26/11/2026); e, vendo a 1ª versão: "esse setor de supervisão de campo é um setor de
manutenção [...] coisas relacionadas a acompanhamento de manutenção [...] também o time de manutenção vai ver, além do
COS"; "A performance vai cuidar de performance, então, baixa geração, alguns alarmes [...] O que o COS olha? Tempo real. A
usina desligou, algum equipamento [...] E pode até reportar alarmes, quedas de string. Mas essas coisas pequenas são mais
da performance hoje em dia". Depois: "um drill [...] clicar na atividade, ver quantas regras são, ver quais são as regras
por cliente e ver quais são os prazos" e "no mesmo formato que estava o PDF [...] para eu ir só abrindo ali".

O setor não está escrito nos contratos (eles dizem "a CONTRATADA"): sai do que a regra é. Cada atividade é (nome, setor,
regex no nome da regra, regex no que vale hoje ou None, origem); a 1ª que casa vence. Origem "Levi" = a distribuição que
ele deu; "proposta" = a nossa, para ele confirmar (a tela marca a dele). Os textos comparados vão sem acento e em
minúsculas. Puro: nada de rede nem Flask; a tela manda as fichas (`edicao.visao`).
"""
from __future__ import annotations

import re
import unicodedata

SEG, COS, PCM, MAN, ENG, ZEL, PERF, CTR, FIN = ("Segurança (HSEQ)", "COS", "PCM", "Manutenção (Supervisão de Campo)",
                                                "Engenharia de O&M", "Zeladoria", "Performance", "Contratos", "Financeiro")
ORDEM = [COS, PERF, PCM, MAN, ENG, ZEL, SEG, CTR, FIN, "a definir"]

ATENDIMENTO = [
    ('Sobreaviso, plantão e horário da equipe de campo', MAN,
     'sobreaviso|horario|plantao|cobertura em horario|quadro tecnico|ocorrencia fora|equipe minima|janela operacional|religamento (manual|sem comando)|canal de acionamento|servico de emergencia',
     None, 'Levi'),
    ('Chegada ao local e mobilização da equipe, por criticidade', MAN,
     '^(mobilizacao|chegada)',
     None, 'proposta'),
    ('Resposta à falha, correção e reparo (ações programadas, corretiva, substituições, rearme, religamento)', PCM,
     '^atendimento \\(conclusao\\)',
     None, 'Levi'),
    ('Falha que ameaça a segurança de bens e pessoas', SEG,
     '.',
     'seguranca (dos|das|de) (bens|pessoas)|ameaca', 'Levi'),
    ('Baixa geração, desvio de produção e alarmes: a Performance analisa e reporta', PERF,
     'desvio|baixo desempenho|baixa geracao',
     None, 'Levi'),
    ('Evento ou alarme menor, sem perda de energia nem de comunicação: a Performance olha, o PCM programa a intervenção', PERF,
     'resposta a falha|tempo de resposta|risco|criticidade|nivel \\d|evento (critico|maior|menor)|alarme|evento menor|alarme menor',
     'sem perda de energia|evento menor|alarme menor', 'Levi'),
    ('Usina ou equipamento parado e perda de comunicação, em tempo real: o COS acompanha, abre a OS e avisa a manutenção', COS,
     'resposta a falha|tempo de resposta|risco|criticidade|nivel \\d|evento (critico|maior|menor)|alarme',
     '(?<!sem )perda (parcial )?de comunicacao|sem comunicacao|parad[ao]|desligad|queda de rede|curto.circuito|incendio', 'Levi'),
    ('Monitoramento e operação remota em tempo real 24 h (SCADA, CFTV, central de atendimento)', COS,
     'monitoramento|operacao remota|cftv|central de atendimento|canal de acionamento|seguranca patrimonial|emergencia 24|servico de emergencia',
     None, 'Levi'),
    ('Como o SLA se conta (criticidade, janela, início, exceções)', CTR,
     'como se (conta|mede)|contagem|sla so|inicio da aplicacao|slas intermediarios|sem exclusividade|tabela de criticidade|criterio de falha|classificacao de criticidade|forma de atendimento|criticidade da proposta|plano de comunicacao|quando o sla|acionamento so com|falha que depende',
     None, 'proposta'),
    ('Avisar a falha, abrir a OS ou o ticket e acionar a concessionária', COS,
     'detec|report|informar|notificar|comunicar|relatar|abertura|registro e notificacao|aviso|chamados|ticket|desvio|religamento sem comando|restabelecimento|falha de agua|falta de energia|falha na internet|falta de conexao|perda de comunicacao|emergencia: acao',
     None, 'Levi'),
    ('Escalonamento ao 2º nível, plano de ação e garantias', ENG,
     '2. nivel|segundo nivel|plano de acao|fora do escopo|garantia|grande porte|nao pode corrigir',
     None, 'proposta'),
    ('Zeladoria sob demanda (roçada, limpeza pontual, risco no terreno)', ZEL,
     '\\broca|limpeza|mobilizacao sob demanda|atuar e concluir risco|informar risco',
     None, 'proposta'),
    ('Intrusão e ocorrência policial', SEG,
     'intrusao|boletim de ocorrencia',
     None, 'proposta'),
    ('Resposta à falha, correção e reparo (ações programadas, corretiva, substituições, rearme, religamento)', PCM,
     '.',
     None, 'Levi'),
]

ENTREGAVEIS = [
    ('Prazo, forma e conteúdo dos relatórios; pedidos de informação do cliente', CTR,
     'forma de entrega|ate o dia|ajuste do conteudo|prestacao de contas|pedido de informacao|requisicao de informac|exportacao dos dados|histograma',
     None, 'proposta'),
    ('Relatório semanal, KPIs e análises de desempenho', PERF,
     'semana|kpi|analytic|analitic|melhoria de performance|produtividade|pr mensal',
     None, 'proposta'),
    ('Relatório mensal de operação e desempenho', PERF,
     'relatorio (mensal|de desempenho|de performance|de operacao|gerencial)|rmo|mensal de o&m|indicadores|desempenho',
     None, 'proposta'),
    ('Relatório anual, consolidado ou de energia', PERF,
     'anual|consolidad|energia|geracao|balanco',
     None, 'proposta'),
    ('Relatório de falha, anomalia e evento crítico (RAF, defeito de fabricação)', ENG,
     '\\braf\\b|anomalia|defeito de fabricacao|evento critico|extraordinario|vicio',
     None, 'proposta'),
    ('Relatório do dia e da atividade (RDO, atendimento, serviços executados)', PCM,
     'diario|rdo|atividade|atendimento|ordem de servico|\\bos\\b|corretiva|ocorrencia|registro|servicos executados',
     None, 'proposta'),
    ('Plano e relatório de manutenção (preventiva, cronograma, plano anual, reaperto)', PCM,
     'preventiva|plano (de|anual)|cronograma|programacao|manutenc|checklist|inspec|reaperto',
     None, 'proposta'),
    ('Inventário, sobressalentes e almoxarifado', PCM,
     'inventario|sobressalente|estoque|pecas|almox',
     None, 'proposta'),
    ('Laudos e documentos técnicos (termografia, as-built, ART, garantia)', ENG,
     'laudo|termograf|analise|tecnic|as.built|projeto|garantia|eletroluminesc|curva|ensaio|causa|rca|engenharia|manual|\\bart\\b',
     None, 'proposta'),
    ('Segurança e meio ambiente (APR, PT, treinamentos, SSMA, sinistro)', SEG,
     'seguranca|ssma|sst|apr|\\bpt\\b|treinamento|incidente|acidente|meio ambiente|ambiental|epi|nr.?\\d|pgr|pcmso|aso|sinistro',
     None, 'proposta'),
    ('Limpeza e roçada (relatório e evidências)', ZEL,
     'limpeza|\\broca|vegeta|lavagem|zelador',
     None, 'proposta'),
    ('Medição, boletim e faturamento', FIN,
     'medicao|medicoes|boletim|\\bbm\\b|fatura|nota fiscal|cobranca',
     None, 'proposta'),
    ('Conformidade e comunicação com o cliente (reuniões, reclamações, obrigações legais, anticorrupção)', CTR,
     'reuniao|apresenta|comunica|contato|carta|notifica|onboarding|handover|transicao|ata|reclama|conformidade|obrigacoes legais|anticorrupcao|socioambienta',
     None, 'proposta'),
    ('Outros entregáveis', "",
     '.',
     None, 'proposta'),
]

METAS = [
    ('Disponibilidade garantida e como se calcula', PERF,
     'disponibilidade|availability|indisponib|adisp',
     None, 'proposta'),
    ('Performance ratio e geração garantida', PERF,
     '\\bpr\\b|performance ratio|geracao|energia|desempenho|rendimento',
     None, 'proposta'),
    ('Apuração dos indicadores (expurgos, irradiância, PVsyst, curtailment, carência, metodologia)', PERF,
     'expurgo|exclus|nao (conta|entra)|forca maior|irradian|pvsyst|curtailment|perda de producao|dado de producao|escusave|carencia|apuracao|metodologia|validacao|kpis abaixo|danos indiretos|intermitente|faturamento frustrado',
     None, 'proposta'),
    ('Multa por atraso no atendimento e no tempo de resposta (por criticidade, reincidência)', PCM,
     'atraso (no|de|em|na) (atendimento|tempo|evento|intervencao)|reincidencia|mttr',
     None, 'proposta'),
    ('Falha não corrigida, serviço refeito e correção por terceiro; preventiva e registro de OS', PCM,
     'falha (nao|incorrigivel)|refazer|recusado|por terceiro|terceiros|inercia|preventiva|registro de os|mtbf|reduzir a producao|cronograma',
     None, 'proposta'),
    ('Retenção, atraso de pagamento, indenização e ressarcimento', FIN,
     'retencao|pagamento|mora|indeniza|ressarcimento|titulos|recebiveis',
     None, 'proposta'),
    ('Penalidades por meta não cumprida e o teto', CTR,
     'penalidade|multa|desconto|glosa|teto|limite|redutor|deducao',
     None, 'proposta'),
    ('Bônus por meta superada', CTR,
     'bonus|bonifica|premio|excedente|incentivo',
     None, 'proposta'),
    ('Segurança e meio ambiente (SSMA, proteção à vida)', SEG,
     'ssma|sst|protecao a vida|seguranca',
     None, 'proposta'),
    ('Garantia de funcionamento e mau uso', ENG,
     'garantia',
     None, 'proposta'),
    ('Zeladoria', ZEL,
     'zeladoria|\\broca|limpeza',
     None, 'proposta'),
    ('Infrações do contrato (sigilo, anticorrupção, paralisação, step-in, empregados)', CTR,
     '.',
     None, 'proposta'),
]

FINANCEIRO = [
    ('Zeladoria cobrada à parte (roçada e limpeza acima do previsto, avulsas)', ZEL,
     '\\broca|limpeza|zeladoria|lavada|vegetacao|agua potavel|pragas',
     None, 'proposta'),
    ('Garantia de fabricante (acionamento, logística, troca)', ENG,
     'garantia|defeito de fabrica',
     None, 'proposta'),
    ('Quem paga materiais, peças e sobressalentes', PCM,
     'materia|pecas|sobressalente|consumive|insumo|fusiveis|equipamento novo|cabeamento',
     None, 'proposta'),
    ('Deslocamento, diárias e reembolso de despesas', FIN,
     'deslocamento|diaria|hospedagem|reembolso|despesa|logistica',
     None, 'proposta'),
    ('Reajuste e reequilíbrio do contrato', CTR,
     'reajust|ipca|igp|indice|reequilibrio',
     None, 'proposta'),
    ('Valor, medição, nota fiscal e pagamento', FIN,
     'medicao|fatura|nota|\\bnf|boleto|boletim|\\bbm\\b|valor|preco|pagamento|vencimento|cobranca|retenc|imposto|tribut|banc|cessao|credito|pro rata|gratuito|remuneracao|comissao|mora|spe|controversa|carencia|parcela|conta comunicada',
     None, 'proposta'),
    ('O que o valor cobre: pequena e grande monta, exclusões', CTR,
     'monta|grande porte|pequeno porte|exclus|cobre|inclus|funcoes nao|premissa|analise do relatorio',
     None, 'proposta'),
    ('Serviços adicionais, hora extra e orçamento', CTR,
     'adiciona|hora|hh|homem.hora|orcamento|fora do escopo|extra|aditivo|tabela|mobiliza|a parte|avulsa|acima de|madrugada|noturno|religamento|verificacao presencial|terceiro|complexos|proposta|scada|condicoes para cobrar',
     None, 'proposta'),
    ('Outros itens financeiros', FIN,
     '.',
     None, 'proposta'),
]

# quem também acompanha a atividade (o dono continua um só, o da coluna Setor)
TAMBEM = {
    'Usina ou equipamento parado e perda de comunicação, em tempo real: o COS acompanha, abre a OS e avisa a manutenção': ['Manutenção', 'PCM'],
    'Avisar a falha, abrir a OS ou o ticket e acionar a concessionária': ['Manutenção'],
    'Baixa geração, desvio de produção e alarmes: a Performance analisa e reporta': ['PCM'],
    'Evento ou alarme menor, sem perda de energia nem de comunicação: a Performance olha, o PCM programa a intervenção': ['PCM', 'Manutenção'],
    'Resposta à falha, correção e reparo (ações programadas, corretiva, substituições, rearme, religamento)': ['Manutenção'],
    'Chegada ao local e mobilização da equipe, por criticidade': ['PCM'],
    'Falha que ameaça a segurança de bens e pessoas': ['COS', 'Manutenção'],
    'Relatório do dia e da atividade (RDO, atendimento, serviços executados)': ['Manutenção'],
    'Plano e relatório de manutenção (preventiva, cronograma, plano anual, reaperto)': ['Manutenção'],
    'Multa por atraso no atendimento e no tempo de resposta (por criticidade, reincidência)': ['Manutenção', 'COS'],
    'Falha não corrigida, serviço refeito e correção por terceiro; preventiva e registro de OS': ['Manutenção'],
}

TEMAS = [("Atendimento", ("SLA",), ATENDIMENTO), ("Entregáveis", ("Entregáveis",), ENTREGAVEIS),
         ("Metas", ("Disponibilidade e desempenho", "Benefícios", "Penalidades"), METAS),
         ("Financeiro", ("Medição e faturamento", "Adicionais e hora extra"), FINANCEIRO)]
_COMPILADAS = {t: [(n, s, re.compile(rn), re.compile(rv) if rv else None, o) for n, s, rn, rv, o in fam] for t, _, fam in TEMAS}


def _sa(t) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(c) != "Mn").lower()


def _vale(r: dict):
    v = r.get("vigente")
    return v if v not in (None, "") else r.get("contratual")


def atividade(tema: str, regra: dict) -> tuple[str, str, str]:
    """(nome, setor, origem) da regra no tema; a última atividade de cada tema casa com tudo."""
    n, v = _sa(regra.get("nome")), _sa(_vale(regra))
    for nome, setor, rn, rv, origem in _COMPILADAS[tema]:
        if rn.search(n) and (rv is None or rv.search(v)):
            return nome, setor or "a definir", origem
    return "Outros", "a definir", "proposta"


def montar(fichas: dict) -> dict:
    """`fichas` = {cliente: {"contratos": [{"regras": [{_id, categoria, nome, contratual, vigente, ...}]}]}} (a ficha de
    cada cliente com as mudanças da tela). A mesma regra em mais de um contrato do cliente (mesma categoria, nome e o que
    vale) conta uma vez. Volta {"temas": [{nome, regras, clientes, atividades: [{nome, setor, origem, tambem, regras,
    clientes, por_cliente: {cliente: [_id]}}]}], "matriz": {setor: {tema: n}}, "ordem": [setores]}."""
    temas = []
    matriz: dict = {}
    for tema, cats, _ in TEMAS:
        grupos: dict = {}
        clientes = set()
        n_regras = 0
        for cli in sorted(fichas, key=lambda c: _sa(c)):
            vistos = set()
            for k in (fichas[cli] or {}).get("contratos") or []:
                for r in k.get("regras") or []:
                    if r.get("categoria") not in cats:
                        continue
                    ch = (r.get("categoria"), _sa(r.get("nome")).strip(), _sa(_vale(r)).strip())
                    if ch in vistos:
                        continue
                    vistos.add(ch)
                    a = atividade(tema, r)
                    g = grupos.setdefault(a, {})
                    g.setdefault(cli, []).append(r.get("_id"))
                    clientes.add(cli)
                    n_regras += 1
        ativ = []
        for (nome, setor, origem), por_cli in grupos.items():
            n = sum(len(x) for x in por_cli.values())
            ativ.append({"nome": nome, "setor": setor, "origem": origem, "tambem": TAMBEM.get(nome, []), "regras": n,
                         "clientes": len(por_cli), "por_cliente": por_cli})
            matriz.setdefault(setor, {})[tema] = matriz.get(setor, {}).get(tema, 0) + n
        ativ.sort(key=lambda x: (ORDEM.index(x["setor"]) if x["setor"] in ORDEM else 99, -x["regras"]))
        temas.append({"nome": tema, "regras": n_regras, "clientes": len(clientes), "atividades": ativ})
    return {"temas": temas, "matriz": matriz, "ordem": [s for s in ORDEM if s in matriz]}
