"""A biblioteca de modos de falha do FMEA e da causa raiz (Levi, 29/10/2026: "Tem que ter emitir FEMEA emitir causa raiz
do pcm.gridco.com.br use como referência e implemente").

É a "camada 2" do módulo Confiabilidade do painel do PCM: cada padrão, casado pelo texto das OS de falha do ativo (a
tarefa e a nota do técnico), traz o modo, o efeito, a causa provável, a severidade e a detecção sugeridas, os cinco
porquês esboçados e as ações padrão. O que vem daqui é SUGESTÃO: a folha mostra em verde e a engenharia troca. O padrão
novo entra aqui, com o texto e o caso que o criou.

O serviço registrado como corretiva (limpeza, ensaio) não é padrão daqui: vale a marca da Confiabilidade
(`confiabilidade.RX_SERVICO`, o `servico` de cada OS e o `soServico` do ativo), para a folha e a lista dizerem o mesmo.
"""
import re

# a ordem importa: o primeiro padrão que casa com a OS vence (a mesma da biblioteca do PCM)
BIBLIOTECA = (
    {"chave": "string_corrente", "fam": "Inversor", "nome": "String com corrente nula ou reversa",
     "re": re.compile(r"string.*(sem corrente|corrente nula|corrente reversa|nula)", re.I),
     "modo": "String PV com corrente nula ou reversa no inversor",
     "efeito": "Perda de geração da string (cerca de 1/N da potência do inversor) enquanto não normalizada",
     "causa": "Conector MC4 degradado, fusível de string aberto ou diodo de bypass em curto",
     "tipo_falha": "eletrica", "sev": 5, "det": 4, "det_txt": "Alarme do monitoramento (corrente por string)",
     "pq": ("A string apresentou corrente nula no monitoramento",
            "Há circuito aberto entre a string e a entrada do inversor",
            "Conector MC4 ou fusível de string degradado por aquecimento",
            "Mau contato progressivo, sem inspeção termográfica na cadência atual",
            "O plano preventivo não inclui termografia dos conectores de string"),
     "acoes": (("Normalizar a string e substituir o conector ou o fusível afetado", 5, 5, 4),
               ("Termografia nos conectores de todas as strings do inversor", 4, 4, 4),
               ("Incluir a termografia de strings na MPT (trimestral)", 3, 3, 5))},
    {"chave": "inversor_desarme", "fam": "Inversor", "nome": "Inversor desarmou (religamento)",
     "re": re.compile(r"religamento d[oa] inversor|religamento.*inv|inversor (desarm|parad|fora)|trip|desarme", re.I),
     "modo": "Inversor desarmou e precisou de religamento manual",
     "efeito": "Geração do inversor a zero até o religamento: perda proporcional ao tempo parado",
     "causa": "Atuação de proteção (rede fora de faixa, falha de isolamento, sobretemperatura) ou falha de comunicação "
              "que impede o rearme automático",
     "tipo_falha": "eletrica", "sev": 6, "det": 3, "det_txt": "Alarme do monitoramento (inversor sem geração)",
     "pq": ("O inversor desarmou e não voltou sozinho",
            "Uma proteção interna atuou e o rearme automático não ocorreu",
            "A causa da atuação (rede, isolamento ou temperatura) não foi registrada na OS",
            "A OS de religamento só religa: não pede o código de alarme nem a causa",
            "Sem a causa, o mesmo desarme se repete e o plano não muda"),
     "acoes": (("Registrar o código de alarme do inversor na OS de religamento", 4, 5, 4),
               ("Verificar o isolamento CC e a temperatura do inversor na próxima MPM", 4, 4, 4),
               ("Com 3 ou mais desarmes no mês: abrir chamado ao fabricante com o log de alarmes", 3, 4, 5))},
    {"chave": "tracker_tcu", "fam": "Tracker", "nome": "TCU sem comunicação ou bateria baixa",
     "re": re.compile(r"bateria baixa|TCU|perda de comunica|tracker parado", re.I),
     "modo": "TCU do tracker sem comunicação ou com bateria baixa; tracker parado",
     "efeito": "Tracker fora do ângulo ótimo: perda do ganho de rastreamento (até 20 a 25% no dia) e risco em vento "
               "forte sem estivagem",
     "causa": "Bateria da TCU no fim da vida ou carga insuficiente (painel de carga sujo ou sombreado)",
     "tipo_falha": "eletrica", "sev": 4, "det": 3, "det_txt": "Alarme do SCADA do tracker",
     "pq": ("O tracker parou e a TCU indicou bateria baixa",
            "A bateria não sustenta a TCU durante a noite",
            "A capacidade da bateria caiu (fim da vida) ou a recarga é insuficiente",
            "Sem verificação da tensão da bateria na preventiva",
            "O plano não prevê a troca programada das baterias da TCU"),
     "acoes": (("Substituir a bateria da TCU e validar a comunicação", 4, 5, 4),
               ("Medir a tensão da bateria de todas as TCUs do bloco na próxima MPM", 3, 4, 4),
               ("Troca programada das baterias por idade no plano de 52 semanas", 3, 2, 5))},
    {"chave": "rele_protecao", "fam": "Cabine", "nome": "Relé de proteção sem alimentação",
     "re": re.compile(r"fonte capacitiva|rel[eé]\b|rele de prote", re.I),
     "modo": "Relé de proteção da cabine sem alimentação ou sem comunicação",
     "efeito": "Cabine sem supervisão de proteção: desligamento não detectado e risco de operar sem proteção",
     "causa": "Fonte capacitiva do relé com falha",
     "tipo_falha": "eletrica", "sev": 8, "det": 6, "det_txt": "Percebido na inspeção ou pela perda de comunicação do relé",
     "pq": ("O relé ficou sem alimentação",
            "A fonte capacitiva que o alimenta falhou",
            "A fonte foi submetida a sobretensões transitórias sem proteção adequada",
            "Não há redundância nem monitoramento da alimentação do relé",
            "O projeto da cabine não previu alarme de falha da fonte"),
     "acoes": (("Substituir a fonte capacitiva e testar o relé", 5, 5, 4),
               ("Verificar as fontes das demais cabines da usina", 4, 4, 3),
               ("Incluir o teste da fonte do relé na MPS (semestral)", 3, 3, 4))},
)
POR_CHAVE = {b["chave"]: b for b in BIBLIOTECA}

FUNCAO = {"Inversor": "Converter CC dos strings em CA sincronizada com a rede",
          "Tracker": "Manter o ângulo dos módulos no ponto de máxima geração",
          "Cabine": "Elevar a tensão e proteger a saída da usina",
          "Transformador": "Elevar a tensão para a rede",
          "QGBT": "Distribuir e proteger os circuitos de baixa tensão"}


def funcao(fam) -> str:
    return FUNCAO.get(str(fam or ""), "—")


def ocorrencia(n) -> int:
    """A frequência em 30 dias na escala de 1 a 10 do RPN (a do PCM): 5 ou mais = 10, 4 = 8, 3 = 6, 2 = 4, senão 2."""
    n = int(n or 0)
    return 10 if n >= 5 else 8 if n == 4 else 6 if n == 3 else 4 if n == 2 else 2


def _casa(o: dict) -> dict | None:
    texto = f"{o.get('t') or ''} {o.get('nota') or ''}"
    return next((b for b in BIBLIOTECA if b["re"].search(texto)), None)


def pre(a: dict) -> dict:
    """O que a biblioteca reconhece nas OS do ativo (`a["os"]`, as da janela da Confiabilidade, a mais recente
    primeiro): o padrão MAIS FREQUENTE entre as falhas (empate: o que aparece primeiro na lista), as OS dele
    (`fontes`, até 3) e a severidade e a detecção sugeridas. Sem padrão, a severidade sai da criticidade do ativo
    (A = 8, B = 6, C = 4) e a detecção fica em 6, como no PCM."""
    oss = a.get("os") or []
    falhas = [o for o in oss if not o.get("servico")]
    servicos = [o for o in oss if o.get("servico")]
    casos = [(o, _casa(o)) for o in falhas]
    conta: dict = {}
    for _, b in casos:
        if b:
            conta[b["chave"]] = conta.get(b["chave"], 0) + 1
    padrao = None
    if conta:
        ordem = [b["chave"] for _, b in casos if b]
        chave = max(conta, key=lambda k: (conta[k], -ordem.index(k)))
        padrao = POR_CHAVE[chave]
    do_padrao = [o for o, b in casos if padrao and b is padrao]
    crit = str(a.get("crit") or "")
    return {"padrao": padrao, "n_padrao": len(do_padrao), "fontes": ", ".join("#" + o["os"] for o in do_padrao[:3]),
            "n_falha": len(falhas), "n_servico": len(servicos),
            "so_servico": bool(a.get("soServico")) or (bool(servicos) and not falhas),
            "tipo_falha": padrao["tipo_falha"] if padrao else "",
            "sev": padrao["sev"] if padrao else (8 if crit == "A" else 6 if crit == "B" else 4),
            "det": padrao["det"] if padrao else 6}
