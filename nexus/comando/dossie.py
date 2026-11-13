"""O dossiê da usina para a IA (12/11/2026): tudo o que o prontuário junta, num texto que uma IA lê de uma vez.

Levi, 12/11/2026: "Monte o dossiê da usina inteira, para a gente usar com a IA futuramente, do jeito que uma IA possa ver
facilmente"; e "A ideia é a pessoa ir no prontuário da usina e perguntar [...] por que a usina está com baixa
performance, enfim, quais são os problemas dela, e já aparece. Então, use tudo que tem no prontuário da usina, tá? Todas
as informações de todos os setores".

O que é: o contexto do prontuário (`torres/comando/prontuario_dados.contexto`) escrito em Markdown, uma seção por
assunto. Nada é lido de novo e nada é calculado aqui: cada número é o que a tela dona mostra, com a gravidade dela em
palavras. É o que o Nexus IA vai mandar junto da pergunta (a tela Base › Nexus IA; a chamada à API ainda não existe).

As regras do texto, que são o que faz uma IA ler bem e errar menos:
- **uma seção por assunto, sempre na mesma ordem e com o mesmo título**, e em cada uma a `Fonte:` (a tela do Nexus de
  onde o dado saiu), para a resposta poder citar de onde tirou;
- **o que não existe está escrito**: "sem dado" quando a fonte não tem o valor (não é zero), "sem leitura" quando a
  fonte não abriu, e a seção "O que ficou de fora" no fim. A IA não pode confundir falta de dado com "está tudo bem";
- **a gravidade em palavras** (crítico, atenção, em dia), no lugar da cor da tela;
- **nada de desenho**: sai o que é só da tela (largura de barra, coordenada de gráfico, classe de cor, endereço);
- **as pessoas pelo papel, sem o nome** (`com_pessoas=False`, o padrão): o texto vai sair do Nexus para a IA, e nome de
  pessoa é dado pessoal. O papel fica ("Responsável O&M: definido"), porque "ninguém cuida disso" é informação. O texto
  livre que alguém escreveu (a descrição de uma demanda, a última mensagem da conversa) vai como foi escrito. O cliente
  e o código da usina ficam: não são dado pessoal, e o código já traz o cliente.

O que os setores sabem e o prontuário ainda NÃO mostra entra por `extras` (Levi, 12/11/2026, conferindo o dossiê: "tá
indo o que a engenharia tá vendo [...] tá indo alguma anotação de supervisão"): a Engenharia (os ativos com sinal da
Confiabilidade com os números de lá, os ativos em acompanhamento com o diagnóstico e os comentários, os relatórios de FMEA
e de causa raiz) e as observações do Responsável O&M. Quem lê essas fontes é a view (`torres/comando`), cada uma no
`try` dela: a que não abre chega como None e o dossiê diz "sem leitura".

Funções puras: recebem o contexto pronto e devolvem o texto; o teste prova que o número do dossiê é o da tela.
"""
from datetime import date, datetime

from . import prontuario as PR

VERSAO = 1
# a cor da tela em palavras (a régua é a de cada tela dona; aqui só o nome)
GRAVIDADE = {"critico": "crítico", "alerta": "atenção", "atencao": "atenção", "semcom": "sem comunicação",
             "info": "informativo", "ok": "em dia", "neutro": ""}
SEM_DADO = "sem dado"
_FONTE_LINHA = {"cos": "COS", "ronda": "Ronda", "pt": "PT", "chamado": "Chamado", "os": "OS"}
_LUVAS = {"sem_luvas": "sem luvas na última ronda", "sem_verificacao": "nunca verificadas na ronda", "ok": "conferidas",
          "com_luvas": "conferidas"}


def _t(v) -> str:
    return "" if v is None else " ".join(str(v).split())


def _g(cls) -> str:
    return GRAVIDADE.get(_t(cls), "")


def _com_g(txt, cls) -> str:
    """ "85%" + "critico" -> "85% (crítico)"; sem gravidade, só o texto."""
    g, t = _g(cls), _t(txt)
    # o veredito da ronda já é a palavra ("Atenção"): não se repete entre parênteses
    return f"{t} ({g})" if g and t and t.lower() != g else t


def _junta(*partes, sep="; ") -> str:
    return sep.join(p for p in (_t(x) for x in partes) if p)


def _cel(v) -> str:
    return (_t(v) or "—").replace("|", "/")


def _tabela(cab: list[str], linhas: list[list]) -> list[str]:
    if not linhas:
        return []
    return ["| " + " | ".join(cab) + " |", "|" + "|".join(" --- " for _ in cab) + "|"] + \
           ["| " + " | ".join(_cel(c) for c in l) + " |" for l in linhas]


def _dia(v) -> str:
    """ "2026-11-11" ou 20261111 -> "11/11/2026"; o que não for data volta como veio."""
    s = _t(v)
    d = PR.do_data_id(s.replace("-", "")[:8]) if s else None
    return d.strftime("%d/%m/%Y") if d else s


def _papel(rotulo: str, nome, com_pessoas: bool) -> str:
    n = _t(nome)
    if not n or n.lower().startswith("sem respons"):
        return f"- {rotulo}: não definido"
    return f"- {rotulo}: {n if com_pessoas else 'definido'}"


# ── as seções ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _identificacao(x: dict, u: dict, cu: dict, p: dict, com_pessoas: bool) -> list[str]:
    out = [f"- Usina: {_t(x.get('usina'))}", f"- Código: {_t(x.get('codigo')) or SEM_DADO}"]
    for rot, v in (("Cliente", x.get("cliente")), ("Cluster", x.get("cluster")), ("Tipologia", x.get("tipologia")),
                   ("Potência", f"{PR.num(x['mwp'])} MWp" if x.get("mwp") is not None else ""),
                   ("Local", " / ".join(q for q in (_t(u.get("cidade")), _t(u.get("uf"))) if q)),
                   ("Equipe de campo", u.get("equipe")), ("Região de campo", u.get("regiao_campo")),
                   ("Mobilizada em", p.get("mobilizada"))):
        if _t(v):
            out.append(f"- {rot}: {_t(v)}")
    estado = _junta(_t(x.get("estado_rot")), _t(x.get("detalhe")), sep=": ")
    out.append(f"- Estado agora, pelo COS: {estado or SEM_DADO}")
    pessoas = cu.get("pessoas") or {}
    out += ["", "Quem atende:", _papel("Responsável O&M", x.get("responsavel") or u.get("responsavel"), com_pessoas),
            _papel("Gestor", u.get("gestor") or pessoas.get("gestor"), com_pessoas),
            _papel("Supervisor de campo", pessoas.get("supervisor"), com_pessoas)]
    tecnicos = [_t(t) for t in pessoas.get("tecnicos") or [] if _t(t)]
    out.append(f"- Técnicos atribuídos: {(', '.join(tecnicos) if com_pessoas else len(tecnicos)) if tecnicos else 'nenhum'}")
    return out


def _parecer(p: dict, com_pessoas: bool) -> list[str]:
    par = p.get("parecer") or {}
    out = [f"- Parecer: {_t(par.get('titulo'))} ({_g(par.get('nivel')) or 'em dia'})", f"- Em uma frase: {_t(par.get('frase'))}"]
    itens = p.get("atencao") or []
    if itens:
        out += ["", f"O que pede atenção agora ({len(itens)}), do mais grave para o menos:"]
        for i in itens:
            # o detalhe da demanda vencida é "de Fulano para Beltrano": sem os nomes, fica só o título
            det = "" if (i.get("secao") == "demandas" and not com_pessoas) else _t(i.get("detalhe"))
            out.append(f"- [{_g(i.get('tom')) or 'atenção'}] {_t(i.get('titulo'))}" + (f": {det}" if det else ""))
    else:
        out += ["", "Nada pede atenção agora na Visão do responsável, no COS nem nos Insights."]
    bem = [_t(b) for b in p.get("em_dia") or [] if _t(b)]
    if bem:
        out += ["", "O que está em dia:"] + [f"- {b}" for b in bem]
    return out


def _performance(u: dict, cu: dict, p: dict) -> list[str]:
    perf = (p.get("painel") or {}).get("perf") or {}
    out = []
    if perf.get("periodo"):
        out.append(f"- O mês corrente é parcial: os números cobrem {perf['periodo']}.")
    if not perf.get("medidores"):
        out.append(f"- Meta, PR e disponibilidade do mês: {SEM_DADO}.")
    for m in perf.get("medidores") or []:
        if _t(m.get("txt")) in ("", "—"):
            out.append(f"- {m.get('rot')}: {SEM_DADO}")
            continue
        out.append(f"- {m.get('rot')}: " + _junta(_com_g(m.get("txt"), m.get("cls")), m.get("sub"),
                                                  f"mês anterior, {m['ant']}" if m.get("ant") else ""))
    anomalia = _t((u.get("meta") or {}).get("anomalia"))
    if anomalia:
        out.append(f"- Anomalia apontada na geração: {anomalia}")
    meses = p.get("meses") or []
    if meses:
        out += ["", "Mês a mês:"] + _tabela(
            ["Mês", "Atingimento da meta", "Geração", "PR", "PR previsto", "Disponibilidade", "Horas paradas", "Cobertura"],
            [[m.get("rot") + (" (parcial)" if m.get("parcial") else ""), _com_g(m.get("ating"), m.get("ating_cls")),
              m.get("geracao"), m.get("pr"), m.get("pr_meta"), m.get("disp"), m.get("h_perdidas"), m.get("dias")]
             for m in meses])
    # a dica de cada coluna do gráfico da geração é a frase do dia; o dia sem geração publicada vem com o travessão
    dias = [_t(c.get("dica")).replace("geração — MWh", f"geração {SEM_DADO}")
            for c in (cu.get("graf_ger") or {}).get("colunas") or [] if _t(c.get("dica"))]
    if dias:
        out += ["", "Geração de cada dia do mês (POA é a irradiação no plano dos módulos):"]
        out += [f"- {d}" for d in dias]
    return out


def _cos(x: dict, p: dict) -> list[str]:
    ocs = x.get("os_cos") or []
    if x.get("estado") == "sem_leitura":
        out = ["- Agora: sem leitura do COS (a fonte não respondeu ou a usina não está na fotografia). Não quer dizer normal."]
    elif ocs:
        out = [f"- Agora: {len(ocs)} {'ocorrência aberta' if len(ocs) == 1 else 'ocorrências abertas'}"]
        for o in ocs:
            out.append("  - " + _junta(_com_g(o.get("motivo") or o.get("rotulo") or "ocorrência", o.get("tom")), o.get("os_rotulo"),
                                       f"aberta {o['ha']}" if o.get("ha") else "", o.get("etapa")))
    else:
        out = ["- Agora: nenhuma ocorrência aberta."]
    cos = p.get("cos") or {}
    if not cos.get("total"):
        return out + ["- Histórico de normalizações: nenhuma registrada no banco para esta usina."]
    out.append(f"- Normalizações registradas: {cos['total']}")
    if cos.get("por_mes"):
        out += ["", "Por mês:"] + _tabela(["Mês", "Normalizações", "Com a geração parada"],
                                         [[m.get("rot"), m.get("n"), m.get("parou")] for m in cos["por_mes"]])
    out += ["", f"As {len(cos.get('ultimas') or [])} mais recentes:"] + _tabela(
        ["Início", "Tipo", "Tempo fora", "A geração parou", "Voltou em", "OS", "Fora do escopo de O&M"],
        [[f"{c.get('dia')} {c.get('hora')}", _com_g(c.get("tipo"), c.get("tom")), c.get("fora"), "sim" if c.get("parou") else "não",
          c.get("volta"), c.get("os"), "sim" if c.get("fora_escopo") else "não"] for c in cos.get("ultimas") or []])
    return out


def _os(u: dict, p: dict, com_pessoas: bool) -> list[str]:
    out = []
    for par in u.get("paradas_abertas") or ():
        out.append("- OS de PARADA aberta agora: " + _junta(f"OS {_t(par.get('os'))}", par.get("tipo"), par.get("escopo"),
                                                           _t(par.get("codigo")), f"desde {_t(par.get('inicio'))}"))
    bloco = (p.get("painel") or {}).get("os")
    if bloco is None:
        return out + ["- OS abertas: sem leitura (as OS do Fracttal não chegaram ao banco). Não quer dizer zero."]
    out.append(f"- OS abertas: {bloco.get('abertas')}" + (
        " (" + ", ".join(f"{x['n']} {x['rot']}" for x in bloco.get("partes") or []) + ")" if bloco.get("partes") else ""))
    for l in bloco.get("linhas") or []:
        out.append(f"- {l.get('rot')}: " + _junta(_com_g(l.get("txt"), l.get("cls") if l.get("cls") != "ok" else ""), l.get("sub")))
    sem = bloco.get("semana")
    if sem:
        out.append(f"- Plano da semana passada: " + _junta(_com_g(sem.get("txt"), sem.get("cls")), sem.get("sub")))
    man = u.get("manutencao") or {}
    for g in p.get("os_grupos") or []:
        out += ["", f"{g.get('rot')} ({g.get('n')})" + (f", {g['nota']}" if g.get("nota") else "") + ":"]
        if g.get("chave") == "pausadas":
            # da lista crua, para o nome de quem pausou só entrar com `com_pessoas`
            for t in man.get("todas_paradas") or []:
                out.append("- " + _junta(f"OS {_t(t.get('os'))}", t.get("motivo"), f"desde {_dia(str(t.get('desde') or '')[:10])}"
                                         if t.get("desde") else "", t.get("quem") if com_pessoas else ""))
        elif g.get("detalhado"):
            out += ["- " + _junta(f"OS {_t(i.get('os'))}", i.get("txt")) for i in g.get("itens") or []]
        else:
            out.append("- OS " + ", ".join(_t(i.get("os")) for i in g.get("itens") or []))
    return out


def _engenharia(u: dict, extras: dict, com_pessoas: bool) -> list[str]:
    """O que a Engenharia vê da usina: os ativos com sinal na Confiabilidade (com os números da gaveta de lá), os que
    estão em acompanhamento (o diagnóstico, a OS de análise e os comentários) e os relatórios de falha emitidos."""
    out = []
    at = extras.get("ativos")
    if at is None:
        # a Confiabilidade não abriu: fica o que a Visão do responsável já tinha contado, e o aviso
        lista = (u.get("ativos") or {}).get("lista") or []
        out.append("- Confiabilidade dos ativos: sem leitura dos números agora" + (". O que a Visão do responsável contou:" if lista else "."))
        out += [f"  - {_t(a.get('nome'))} ({_t(a.get('cod'))}): {_com_g(a.get('porque'), a.get('nivel'))}" for a in lista]
    else:
        out.append(f"- Ativos com sinal de falha nos últimos {at.get('janela')} dias: {at.get('criticos') or 0} em crítico, "
                   f"{at.get('atencao') or 0} em atenção e {at.get('monitorar') or 0} só em monitoramento")
        for a in at.get("ativos") or []:
            out.append(f"  - {_t(a.get('nome'))} ({_t(a.get('cod'))})" + (f", {_t(a.get('fam'))}" if _t(a.get("fam")) else "")
                       + f" [{_g(a.get('cls')) or _t(a.get('nivel_txt'))}]: " + _junta(
                "; ".join(_t(q) for q in a.get("porque") or []),
                f"falhas em 30 dias: {a.get('n30')}", f"em 7 dias: {a.get('n7')}",
                f"MTBF {_t(a.get('mtbf'))}" if _t(a.get("mtbf")) not in ("", "—") else "",
                f"MTTR {_t(a.get('mttr'))}" if _t(a.get("mttr")) not in ("", "—") else "",
                f"disponibilidade do ativo {_t(a.get('disp'))}" if _t(a.get("disp")) not in ("", "—") else "",
                f"circuito {_t(a.get('circuito'))}" if _t(a.get("circuito")) else ""))
    acs = extras.get("acompanhamentos")
    if acs is None:
        out.append("- Ativos em acompanhamento pela Engenharia: sem leitura.")
    elif not acs:
        out.append("- Ativos em acompanhamento pela Engenharia: nenhum nesta usina.")
    else:
        abertos = [a for a in acs if a.get("aberto")]
        out.append(f"- Ativos em acompanhamento pela Engenharia: {len(abertos)} em aberto e {len(acs) - len(abertos)} já encerrados")
        for a in sorted(acs, key=lambda a: (not a.get("aberto"), _t(a.get("cod")))):
            ini, fim = a.get("inicio"), a.get("fim")
            coms = a.get("comentarios") or []
            out.append("  - " + _junta(
                _t(a.get("cod")), "em análise" if a.get("aberto") else "análise encerrada",
                f"início da análise em {ini.strftime('%d/%m/%Y')}" if isinstance(ini, date) else "",
                f"fim em {fim.strftime('%d/%m/%Y')}" if isinstance(fim, date) else "",
                f"diagnóstico: {_t(a.get('diagnostico')) or 'a definir'}",
                f"entrou com {a['falhas30_entrada']} falhas em 30 dias" if a.get("falhas30_entrada") is not None else "",
                f"OS de análise {_t(a.get('os_folio'))}" if _t(a.get("os_folio")) else "",
                f"com {_t((a.get('responsavel') or {}).get('nome'))}" if com_pessoas and _t((a.get("responsavel") or {}).get("nome")) else "",
                f"{len(coms)} {'comentário' if len(coms) == 1 else 'comentários'}" if coms else "sem comentário"))
            for c in coms[:3]:      # os mais novos primeiro (é a ordem do livro)
                out.append(f"    - {_t(c.get('quando_txt'))}" + (f", {_t(c.get('nome'))}" if com_pessoas and _t(c.get("nome")) else "")
                           + f": {_t(c.get('texto'))}")
    rels = extras.get("relatorios")
    if rels is None:
        out.append("- Relatórios de falha (FMEA e causa raiz): sem leitura.")
    elif not rels:
        out.append("- Relatórios de falha (FMEA e causa raiz): nenhum emitido para ativos desta usina.")
    else:
        out.append(f"- Relatórios de falha emitidos: {len(rels)}")
        for r in rels:
            out.append("  - " + _junta(f"{_t(r.get('numero'))} {_t(r.get('rev_txt'))}", _t(r.get("tipo_txt")), f"ativo {_t(r.get('cod'))}",
                                       f"emitido em {_t(r.get('data_txt'))}", f"tipo de falha: {_t(r.get('tipo_falha'))}" if _t(r.get("tipo_falha")) else "",
                                       f"RPN {r['rpn']}" if r.get("rpn") else "", f"por {_t(r.get('autor'))}" if com_pessoas and _t(r.get("autor")) else ""))
    return out


def _observacoes(extras: dict, com_pessoas: bool) -> list[str]:
    """As observações do Responsável O&M sobre a usina (a anotação de supervisão), a mais nova primeiro. O texto vai como
    foi escrito; quem escreveu, pelo papel."""
    obs = extras.get("observacoes")
    if obs is None:
        return ["- Sem leitura das observações do responsável agora."]
    if not obs:
        return ["- Nenhuma observação registrada pelo responsável nesta usina."]
    out = [f"- Observações registradas: {len(obs)} (a mais nova primeiro)"]
    for o in obs:
        quem = "o responsável da usina" if o.get("do_responsavel") else "um responsável de outra usina, cobrindo"
        out.append(f"  - {_t(o.get('quando_txt'))}, {_t(o.get('nome')) if com_pessoas and _t(o.get('nome')) else quem}: "
                   f"{_t(o.get('texto')) or 'texto ilegível (a chave do cadastro não abriu)'}")
    return out


def _equipamentos(p: dict) -> list[str]:
    e = p.get("equip") or {}
    if not e.get("itens"):
        return ["- Nenhum equipamento com tarefa de OS aberta ou chamado de garantia aberto."]
    linhas = []
    for i in e["itens"]:
        ch = i.get("chamado") or {}
        linhas.append([i.get("nome"), i.get("codigo"), i.get("abertas"), i.get("pausadas"),
                       ", ".join(str(o) for o in i.get("os") or []), ", ".join(i.get("tipos") or []),
                       _junta(f"OS {ch['os']}" if ch.get("os") else "", ch.get("fabricante"), ch.get("situacao"), sep=", ") if ch else ""])
    out = _tabela(["Equipamento", "Código", "Tarefas abertas", "Pausadas", "OS", "Tipos de tarefa", "Chamado de garantia aberto"], linhas)
    if e.get("mais"):
        out += ["", f"E mais {e['mais']} equipamentos com tarefa aberta (de {e.get('ativos')} no total)."]
    return out


def _chamados(p: dict) -> list[str]:
    ch = p.get("chamados_abertos") or []
    if not ch:
        return ["- Nenhum chamado de garantia aberto."]
    return [f"- Chamados abertos: {p.get('chamados_n') or len(ch)}", ""] + _tabela(
        ["OS", "Equipamento", "Fabricante", "Componente", "Situação", "Aberto há", "Status no fabricante"],
        [[c.get("os"), c.get("equip") or c.get("ativo"), c.get("fabricante"), c.get("componente"), c.get("situacao"),
          f"{c['dias']} dias" if c.get("dias") is not None else "", c.get("status")] for c in ch])


def _rondas(u: dict, p: dict, com_pessoas: bool) -> list[str]:
    r, out = u.get("ronda") or {}, []
    dias = PR._int(r.get("dias"))
    out.append("- Última ronda: " + (SEM_DADO + " (nenhuma ronda lida em 90 dias)" if dias is None else
                                     _junta("hoje" if dias == 0 else f"há {dias} {'dia' if dias == 1 else 'dias'}", _dia(r.get("ultima")),
                                            PR._RONDA_TIPO.get(r.get("tipo"), ""), r.get("obs"))))
    rd = p.get("rondas")
    if rd is None:
        out.append("- Histórico de rondas: sem leitura.")
    else:
        out.append(f"- Rondas em 90 dias: {rd.get('total')} ({rd.get('curtas')} curtas e {rd.get('longas')} longas)")
        cab = ["Dia", "Tipo", "Duração", "Veredito", "Sujidade (1 a 5)", "Vegetação (1 a 5)", "OS", "Pendência"]
        linhas = [[x.get("dia"), x.get("tipo"), x.get("dur"), _com_g(x.get("veredito"), x.get("tom")), x.get("suj"), x.get("veg"),
                   x.get("os"), x.get("pendencia")] + ([x.get("tecnico")] if com_pessoas else []) for x in rd.get("ultimas") or []]
        out += [""] + _tabela(cab + (["Técnico"] if com_pessoas else []), linhas)
    z = p.get("zel")
    out.append("")
    if not z:
        lim = u.get("limpeza") or {}
        if lim.get("sujidade") not in (None, "") or lim.get("vegetacao") not in (None, ""):
            out.append("- Sujidade e vegetação, pela última ronda: " + _junta(
                f"sujidade {lim.get('sujidade')}", f"vegetação {lim.get('vegetacao')}", f"vala {_t(lim.get('vala')).lower()}" if _t(lim.get("vala")) else ""))
        else:
            out.append(f"- Leitura semanal de sujidade e vegetação (zeladoria): {SEM_DADO}.")
        return out
    ult = z.get("ultima") or {}
    out.append("- Zeladoria, última semana lida (níveis de 1 a 5; 5 é o pior): " + _junta(
        f"semana {ult.get('semana')}", f"sujidade {ult.get('suj') if ult.get('suj') is not None else SEM_DADO}",
        f"vegetação {ult.get('veg') if ult.get('veg') is not None else SEM_DADO}", f"vala {_t(ult.get('vala')).lower()}" if _t(ult.get("vala")) else ""))
    rec = z.get("recomendacao")
    if rec:
        out.append("- Recomendação da zeladoria: " + _junta(_com_g(rec.get("tipo"), rec.get("tom")), f"semana {rec.get('semana')}",
                                                           rec.get("situacao"), f"OS {rec['os']}" if rec.get("os") else ""))
    sem = (z.get("semanas") or [])[-8:]
    if len(sem) > 1:
        out += ["", "Últimas semanas:"] + _tabela(["Semana", "Início", "Sujidade", "Vegetação"],
                                                 [[s.get("semana"), s.get("inicio"), s.get("suj"), s.get("veg")] for s in sem])
    return out


def _seguranca(u: dict, cu: dict, p: dict, com_pessoas: bool) -> list[str]:
    seg = (p.get("resumos") or {}).get("seg") or {}
    out = [f"- Resumo: {_com_g(seg.get('txt'), seg.get('tom') if seg.get('tom') != 'ok' else '')}"]
    for g in cu.get("seguranca") or ():
        out.append(f"- {_t(g.get('rot'))} ({g.get('n')}): " + "; ".join(
            _junta(i.get("forte"), i.get("txt"), sep=" ") for i in g.get("itens") or []))
    ext = u.get("extintores") or {}
    if ext:
        out.append("- Extintores: " + _junta(f"{ext.get('total')} na usina", f"vencidos: {ext.get('vencidos') or 0}",
                                             f"a vencer: {ext.get('a_vencer') or 0}", f"sem conferir: {ext.get('sem_conferir') or 0}",
                                             f"última conferência em {_dia(ext.get('ultima'))}" if ext.get("ultima") else ""))
        out += [f"  - {_junta(e.get('ext'), e.get('onde'), e.get('txt'), sep=', ')}" for e in ext.get("lista") or []]
    else:
        out.append(f"- Extintores: {SEM_DADO}.")
    lv = p.get("luvas")
    out.append("- Luvas de alta tensão: " + (SEM_DADO if not lv else _junta(
        _LUVAS.get(_t(lv.get("situacao")), _t(lv.get("situacao")).replace("_", " ")),
        f"última verificação em {_dia(lv.get('ultima'))}" if lv.get("ultima") else "")))
    espera = p.get("pts_espera") or []
    out.append(f"- PT (permissão de trabalho) esperando o De acordo: {len(espera)}")
    for pt in espera:
        out.append("  - " + _junta(pt.get("numero"), f"OS {_t(pt.get('os'))}" if pt.get("os") else "", pt.get("tarefa"),
                                   f"esperando há {PR.fora_txt(pt.get('idade_min'))}" if pt.get("idade_min") is not None else "",
                                   "a tarefa está PARADA por ela" if pt.get("parada") else "", pt.get("solicitante") if com_pessoas else ""))
    pts = p.get("pts") or []
    if pts:
        out.append(f"- PT recentes ({p.get('pts_n') or len(pts)} no histórico):")
        out += ["  - " + _junta(x.get("numero"), _dia(x.get("dia")), f"OS {x['os']}" if x.get("os") else "", x.get("situacao"),
                                x.get("tarefa"), x.get("solicitante") if com_pessoas else "") for x in pts]
    return out


def _insights(ctx: dict) -> list[str]:
    vivos = ctx.get("insights") or []
    if (ctx.get("x") or {}).get("insights") is None:
        return ["- Os Insights ainda estão sendo calculados: sem leitura agora."]
    if not vivos:
        return ["- Nenhum insight aberto."]
    regras, sev = ctx.get("regras") or {}, ctx.get("severidades") or {}
    out = []
    for i in vivos:
        r = regras.get(i.get("regra")) or {}
        s = sev.get(i.get("sev")) or ()
        out.append(f"- [{(s[0].lower() if s else _t(i.get('sev')))}] {_t(i.get('titulo'))}")
        out.append("  - " + _junta(f"regra {_t(i.get('regra'))}: {_t(r.get('nome'))}" if r.get("nome") else f"regra {_t(i.get('regra'))}",
                                   f"indicador: {_t(r.get('kpi'))}" if r.get("kpi") else "", f"prazo: {s[2]}" if len(s) > 2 else ""))
        if i.get("evid"):
            out.append("  - evidência: " + "; ".join(_t(e) for e in i["evid"]))
        if _t(i.get("acao")):
            out.append(f"  - ação sugerida: {_t(i.get('acao'))}")
    return out


def _demandas(p: dict, com_pessoas: bool) -> list[str]:
    dem, out = p.get("demandas") or [], []
    if not dem:
        out.append("- Nenhuma demanda entre setores cita esta usina (das que a pessoa que gerou o dossiê pode ver).")
    for d in dem:
        e = d.get("estado") or {}
        prazo = e.get("prazo")
        out.append("- " + _junta(_t(d.get("titulo")) or "demanda sem título",
                                 f"de {_t(d.get('de_setor_nome')) or 'setor não informado'} para {_t(d.get('para_setor_nome')) or 'setor não informado'}",
                                 f"tema: {_t(d.get('tema_nome'))}" if _t(d.get("tema_nome")) else "",
                                 _t(e.get("rotulo")) + (" (VENCIDA)" if e.get("vencida") else ""),
                                 f"prazo {prazo.strftime('%d/%m/%Y')}" if isinstance(prazo, date) else "",
                                 f"OS {d['os']}" if d.get("os") else "",
                                 f"de {_t(d.get('de_nome'))} para {_t(d.get('para_nome'))}" if com_pessoas else ""))
        if _t(d.get("descricao")):
            out.append(f"  - pedido: {_t(d.get('descricao'))}")
    cv = p.get("conversa") or {}
    n = PR._int(cv.get("n")) or 0
    ult = cv.get("ultima") or {}
    out.append(f"- Conversa da usina: {n} {'mensagem' if n == 1 else 'mensagens'}" + (
        ("; a última, de " + _t(ult.get("quando_txt")) + (f", por {_t(ult.get('por'))}" if com_pessoas and _t(ult.get("por")) else "")
         + f": {_t(ult.get('texto'))}") if n and ult else ""))
    return out


def _linha(p: dict, com_pessoas: bool) -> list[str]:
    dias = p.get("linha") or []
    if not dias:
        return [f"- Nenhum evento nos últimos {p.get('linha_dias') or PR.LINHA_DO_TEMPO_DIAS} dias."]
    out = []
    for d in dias:
        data = d.get("data")
        out.append(f"- {_t(d.get('dia'))}" + (f"/{data.year}" if isinstance(data, date) else "") + ":")
        for e in d.get("eventos") or []:
            titulo = _t(e.get("titulo"))
            # a ronda e a PT trazem a pessoa no fim do título ("Ronda curta · Fulano"): sem os nomes, sai
            if not com_pessoas and e.get("fonte") in ("ronda", "pt"):
                titulo = titulo.split(" · ")[0]
            out.append("  - " + _junta(e.get("hora"), f"[{_FONTE_LINHA.get(e.get('fonte'), _t(e.get('fonte')))}]",
                                       _com_g(titulo, e.get("tom") if e.get("tom") != "neutro" else ""), sep=" ")
                       + (f": {_t(e.get('detalhe'))}" if _t(e.get("detalhe")) else "") + (f" (OS {e['os']})" if e.get("os") else ""))
    return out


def _composicao(p: dict) -> list[str]:
    grupos = p.get("composicao") or []
    if not grupos:
        return [f"- Ficha da usina no cadastro: {SEM_DADO}."]
    out = []
    for g, linhas in grupos:
        out += [f"{g}:"] + [f"- {r}: {_t(v)}" for r, v in linhas] + [""]
    return out[:-1]


_EXTRAS = (("ativos", "os números da Confiabilidade (Engenharia)"), ("acompanhamentos", "os ativos em acompanhamento pela Engenharia"),
           ("relatorios", "os relatórios de falha da Engenharia"), ("observacoes", "as observações do responsável"))


def _fora(ctx: dict, p: dict, cu: dict, extras: dict) -> list[str]:
    fora = [_t(a) for a in ctx.get("avisos") or []] + [_t(a) for a in p.get("avisos") or []] + \
           [_t(e) for e in (cu.get("erros") or {}).values()] + [rot for k, rot in _EXTRAS if extras.get(k) is None]
    fora = [f for f in fora if f]
    if not fora:
        return ["- Todas as fontes do prontuário abriram."]
    return ["As fontes abaixo não abriram quando o dossiê foi gerado. O que depende delas está incompleto, e isso não quer "
            "dizer que não há problema:"] + [f"- {f}" for f in fora]


COMO_LER = (
    "- Este documento é tudo o que o Nexus sabe da usina neste instante. O que não está escrito aqui, o Nexus não sabe.",
    "- \"sem dado\" quer dizer que a fonte não tem o valor: não é zero nem \"está normal\". \"sem leitura\" quer dizer que "
    "a fonte não respondeu agora.",
    "- A gravidade vem entre parênteses ou colchetes: crítico (agir hoje), atenção (acompanhar esta semana), em dia. Ela "
    "é a da tela do Nexus que é dona do número, não uma opinião.",
    "- Cada seção diz a `Fonte`: a tela do Nexus de onde o dado veio. Ao responder, cite a seção ou a fonte.",
    "- O mês corrente é parcial; compare com a cobertura em dias antes de concluir sobre meta e geração.",
    "- Numa tabela, \"—\" quer dizer que não há o que dizer naquela célula (nenhuma OS, nenhuma pendência) ou que a fonte "
    "não tem o valor.",
    "- Siglas: OS = ordem de serviço do Fracttal; PT = permissão de trabalho; COS = centro de operações, que acompanha a "
    "usina em tempo real; PR = performance ratio; POA = irradiação no plano dos módulos; MWp = potência instalada.",
)

# (o título da seção, a fonte dita à IA): a ordem é a do texto, sempre a mesma
SECOES = (
    ("Identificação", "Base › Registro mestre e Comando › Usinas"),
    ("Parecer e o que pede atenção", "Comando › Usinas › prontuário (a contagem do que as telas donas apontam)"),
    ("Performance", "Performance › Visão gerencial e Disponibilidade, pela Visão do responsável"),
    ("COS", "COS › Ronda COS (a fotografia de agora) e as normalizações gravadas no banco"),
    ("OS e manutenção", "As OS do Fracttal no banco, pela Visão do responsável › Manutenção"),
    ("Engenharia", "Engenharia › Confiabilidade, o acompanhamento dos ativos e os relatórios de FMEA e de causa raiz"),
    ("Equipamentos com OS ou chamado aberto", "As tarefas das OS abertas por ativo e os chamados de garantia"),
    ("Chamados de garantia", "Chamados › Garantias (o Acompanhamento de chamados)"),
    ("Rondas e zeladoria", "Usinas 360° › Rondas e Zeladoria"),
    ("Segurança", "Segurança · HSEQ (PT, extintores e luvas)"),
    ("Insights do Nexus", "Comando › Nexus Insights (as regras que cruzam as fontes)"),
    ("Anotações do responsável", "Usinas 360° › Visão do responsável › Observação do responsável"),
    ("Demandas entre setores e conversa", "Comando › Caixa de entrada e a conversa da usina"),
    ("Linha do tempo", "Rondas, COS, PT, chamados e OS, numa lista só"),
    ("Composição da usina", "Base › Registro mestre (a ficha) e Base › Equipamentos das usinas"),
    ("O que ficou de fora", "As fontes que não abriram ao gerar este dossiê"),
)


def montar(ctx: dict, agora: datetime, com_pessoas: bool = False, extras: dict | None = None) -> dict:
    """{"texto": o dossiê em Markdown, "secoes": [títulos], "caracteres", "palavras", "tokens_estimados"}. `ctx` = o
    contexto do prontuário (`prontuario_dados.contexto`); `agora` = a hora de Brasília em que foi gerado; `extras` = o
    que os setores sabem e o prontuário não mostra: {"ativos" (`responsaveis.ativos_da_usina`), "acompanhamentos",
    "relatorios", "observacoes"}, cada um None quando a fonte não abriu. Os tokens são uma estimativa pelo tamanho do
    texto (4 caracteres por token): a conta exata só a API dá."""
    x, cu, p = ctx.get("x") or {}, ctx.get("cu") or {}, ctx.get("p") or {}
    u, extras = cu.get("u") or {}, extras or {}
    corpos = (_identificacao(x, u, cu, p, com_pessoas), _parecer(p, com_pessoas), _performance(u, cu, p), _cos(x, p),
              _os(u, p, com_pessoas), _engenharia(u, extras, com_pessoas), _equipamentos(p), _chamados(p),
              _rondas(u, p, com_pessoas), _seguranca(u, cu, p, com_pessoas), _insights(ctx),
              _observacoes(extras, com_pessoas), _demandas(p, com_pessoas), _linha(p, com_pessoas), _composicao(p),
              _fora(ctx, p, cu, extras))
    dias = p.get("linha_dias") or PR.LINHA_DO_TEMPO_DIAS
    linhas = [f"# Dossiê da usina {_t(x.get('usina'))}", "",
              f"- Documento: dossiê da usina, gerado pelo Nexus para leitura por IA (formato {VERSAO})",
              f"- Gerado em: {agora.strftime('%d/%m/%Y às %H:%M')}, horário de Brasília",
              "- Pessoas: " + ("citadas pelo nome" if com_pessoas else "citadas pelo papel, sem o nome"), "",
              "## Como ler", ""] + list(COMO_LER)
    for n, ((titulo, fonte), corpo) in enumerate(zip(SECOES, corpos), 1):
        if titulo == "Linha do tempo":
            titulo = f"Linha do tempo dos últimos {dias} dias"
        # a seção nunca fica em branco: sem nenhuma linha, a fonte inteira faltou, e isso se diz
        linhas += ["", f"## {n}. {titulo}", "", f"Fonte: {fonte}.", ""] + (corpo or [f"- {SEM_DADO} nesta fonte."])
    texto = "\n".join(linhas).rstrip() + "\n"
    return {"texto": texto, "secoes": [t for t, _f in SECOES], "caracteres": len(texto), "palavras": len(texto.split()),
            "tokens_estimados": round(len(texto) / 4)}
