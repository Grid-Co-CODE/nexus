"""O almoxarifado: o contrato dos livros que o App de Campo publica e as contas (25/10/2026).

Levi, 25/10/2026: "No fractall temos almoxarifado, gostaria de uma visão para a gestão desse almoxarifado na parte de
PCM". De onde vem: o saldo do Fracttal só sai item a item (`inventories.associate_warehouses_list`, 574 chamadas por
leitura), e o App já faz essa varredura uma vez por dia, a partir de 00:00 de Brasília, com folga na cota da empresa
(200/min). O App publica 4 livros na API de planilhas (um grão por livro: o `sync-xlsx` com `replace` troca o livro
inteiro), e o Nexus não chama o Fracttal. Desenho: docs/superpowers/specs/2026-10-25-almoxarifado-design.md.

As contas ficam AQUI, num lugar só: a tela (`nexus/pcm/almoxarifado.py`) e a carga do histórico
(`fato_almoxarifado.py`) usam as mesmas. Módulo puro: nada de rede.

O ciclo é identificado pelo INÍCIO, não pela data: o "Atualizar" do Admin no App reinicia o ciclo com a mesma data
(cursor 0), e o pedido entre 21:00 e 23:59 de Brasília cai na data UTC do dia seguinte. A completude é a do PRÓPRIO
ciclo (lidos ÷ itens na lista do Fracttal): comparar com o ciclo anterior travaria o histórico para sempre se o PCM
limpasse o catálogo, e não pegaria o ciclo encerrado cedo.

O inventário (26/10/2026, desenho docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md): o técnico conta
as peças no App e o livro das contagens (`LIVRO_CONTAGENS`, o 5º livro do App) chega aqui para o PCM aprovar e gravar no
Fracttal. O contrato dele mora aqui, do mesmo jeito dos outros: `COLUNAS_CONTAGENS` na ordem, coluna nova só no FIM, dos
dois lados. O almoxarifado de TESTE (a prova das gravações no Fracttal) fica fora das contas e das telas pelo ID
(`ids_de_teste`, da `NEXUS_ALMOX_TESTE_IDS`).
"""
import math
import re

LIVRO_CICLO, ABA_CICLO = "almoxarifado_ciclo_app_campo", "Ciclo"
LIVRO_ITENS, ABA_ITENS = "almoxarifado_itens_app_campo", "Itens"
LIVRO_SALDO, ABA_SALDO = "almoxarifado_saldo_app_campo", "Saldo"
LIVRO_PECAS, ABA_PECAS = "almoxarifado_pecas_app_campo", "Peças"

# O contrato com o App, na ordem; coluna nova só no FIM, dos dois lados (o teste do pacote do App compara com estas)
COLUNAS_CICLO = ("Início do ciclo", "Fim do ciclo", "Itens na lista do Fracttal", "Itens lidos", "Erros", "Origem",
                 # a revisão de 25/10/2026: quantas linhas o Saldo tem, para conferir que ele chegou inteiro
                 "Linhas de saldo")
COLUNAS_ITENS = ("ID do item", "Código", "Nome", "Unidade", "Família", "Avariado", "Ferramenta", "Início do ciclo",
                 "Lido")
COLUNAS_SALDO = ("ID do item", "Código", "ID do almoxarifado", "Almoxarifado", "Local do almoxarifado", "Saldo",
                 "Mínimo", "Início do ciclo")
COLUNAS_PECAS = ("ID do lançamento", "Recebido em", "Usada em", "OS", "Tarefa", "Código do ativo", "ID do item",
                 "Código", "ID do almoxarifado", "Quantidade", "Unidade", "Situação", "Motivo da recusa",
                 "Lançado por (HMAC)")
INICIO = "Início do ciclo"

# O livro das contagens do inventário (26/10/2026): 1 linha = 1 peça de uma contagem enviada, a pendência fora do catálogo
# inclusa. "Contado" vazio é "não contei" (nunca 0: o 0 digitado é "zerar"), o genérico com saldo que é de mais de um
# específico vem em uma linha por específico (o mesmo código do genérico, com o "Identificado como" de cada um), e quem
# contou vai só como HMAC do e-mail. O contrato inteiro, coluna a coluna: seção 4.1 do desenho. O "ID da linha" (a 14ª,
# no FIM, como manda o contrato) é um por peça contada, gerado pelo App e único dentro da contagem: sem ele, duas
# peças "fora do catálogo" com a mesma descrição na mesma contagem teriam a mesma chave.
LIVRO_CONTAGENS, ABA_CONTAGENS = "almoxarifado_contagens_app_campo", "Contagens"
COLUNAS_CONTAGENS = ("ID da contagem", "Enviada em", "Contada em", "ID do almoxarifado", "Usina", "Tipo", "ID do item",
                     "Código", "Contado", "Identificado como", "Descrição", "Foto", "Contou (HMAC)", "ID da linha")
# peça do catálogo; genérico com saldo que o técnico identifica; peça que não está no catálogo (vai à curadoria)
TIPOS_CONTAGEM = ("item", "identificar", "fora_do_catalogo")

COMPLETUDE_MIN = 0.9        # lidos ÷ itens na lista: abaixo disso o ciclo é recusado (fica no último bom)
CICLO_VELHO_H = 36          # a varredura é diária: mais de 36 h sem ciclo novo é o App parado

# "Cliente - Usina - UF": o pedaço do caminho do Fracttal que é a usina (o mesmo do `ligacoes.usina_do_caminho`)
_LOCAL = re.compile(r"\s*(.+?\s+-\s+.+?\s+-\s+[A-Z]{2})\s*")


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def numero(v) -> float | None:
    """O número da API (que pode devolver tudo como texto; o Fracttal manda "10.00"). Vazio ou texto = None, nunca 0:
    o mínimo vazio é "não sabemos", o 0 é "sem mínimo cadastrado"."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(_txt(v).replace(",", "."))
    except ValueError:
        return None


def contado(v) -> float | None:
    """O número que o técnico contou, ou None se NÃO CONTOU. Em branco é "não contei" e a peça não é tocada: virar 0
    zeraria o estoque de uma peça que ninguém contou (o 0 é só o que o técnico digitou). A API devolve tudo como texto, e
    o `sync-xlsx` escreve o vazio como "None": é "não contei" por regra, e não por acaso de o `float` não ler o texto.
    O "nan" e o "inf", que o `float` aceita, também são "não contei"."""
    if isinstance(v, bool) or _txt(v).lower() in ("", "none"):
        return None
    n = numero(v)
    return n if n is not None and math.isfinite(n) else None


def _id(v) -> str:
    """O ID do Fracttal como texto, sem o ".0" que a API às vezes põe ("999.0" é o 999)."""
    t = _txt(v)
    return t[:-2] if t.endswith(".0") else t


def ids_de_teste(config) -> set[str]:
    """Os IDs dos almoxarifados de TESTE (NEXUS_ALMOX_TESTE_IDS, separados por vírgula). A prova das gravações do
    inventário no Fracttal é num almoxarifado de teste, nunca num de usina; ele não conta nas telas do PCM nem no
    histórico (que só cresce: uma linha de teste gravada ficaria para sempre). Sem a chave, nenhum é de teste."""
    return {_id(p) for p in _txt((config or {}).get("NEXUS_ALMOX_TESTE_IDS")).split(",") if _txt(p)}


def sem_almoxarifado_de_teste(saldo: list[dict], config) -> list[dict]:
    """As linhas do Saldo sem as dos almoxarifados de teste. Vale DEPOIS de `ciclo_comum` e `conferir_ciclo`: o ciclo diz
    quantas linhas o livro do App tem (as do teste inclusas), e conferir já filtrado recusaria todo ciclo como "pela
    metade"."""
    ids = ids_de_teste(config)
    return [l for l in saldo if _id(l.get("ID do almoxarifado")) not in ids] if ids else saldo


def chave_do_local(caminho) -> str | None:
    """"// Greenyellow/ Greenyellow - Irecê 1 - BA/" -> "Greenyellow - Irecê 1 - BA". O almoxarifado debaixo de uma
    sublocalização ("... - SP/ Cabine 1/") continua achando a usina: vale o pedaço no formato, não o último."""
    for p in _txt(caminho).split("/"):
        m = _LOCAL.fullmatch(p)
        if m:
            return m.group(1).strip()
    return None


def situacao(saldo, minimo) -> str:
    """A situação de uma peça num almoxarifado. "No limite" separado de "abaixo": o Fracttal costuma ter o mínimo igual
    ao saldo (25/10: 0 abaixo e 54 no limite), e misturar os dois daria um alarme falso por peça. Saldo vazio é "não
    informado" (o Fracttal não deu o número), nunca 0: virava "abaixo, falta 2" na Reposição (a revisão de 25/10)."""
    s, m = numero(saldo), numero(minimo)
    if s is None:
        return "nao_informado"
    if m and m > 0:
        return "abaixo" if s < m else "no_limite" if s == m else "ok"
    return "zerada" if s == 0 else "sem_minimo"


def completo(ciclo: dict) -> bool:
    """O ciclo leu ao menos `COMPLETUDE_MIN` dos itens que estavam na lista do Fracttal."""
    total, lidos = numero((ciclo or {}).get("Itens na lista do Fracttal")), numero((ciclo or {}).get("Itens lidos"))
    return bool(total and total > 0 and lidos is not None and lidos / total >= COMPLETUDE_MIN)


def conferir_ciclo(ciclo: list[dict], itens: list[dict], saldo: list[dict]) -> str:
    """Vazio se os três livros do ciclo chegaram INTEIROS; senão, o porquê. O Itens tem uma linha por item da lista, os
    lidos batem com o ciclo e o Saldo tem as linhas que o ciclo diz (a revisão de 25/10/2026: o Nexus lendo no meio da
    publicação, ou o App subindo pela metade, aplicava uma foto parcial como completa, e a inteira não entrava mais).
    É passageiro: quem chama não aplica nesta hora e tenta na seguinte. A completude de 90% é outra conta (`completo`)."""
    c = (ciclo or [{}])[0]
    total, lidos, linhas = numero(c.get("Itens na lista do Fracttal")), numero(c.get("Itens lidos")), numero(
        c.get("Linhas de saldo"))
    if total is not None and len(itens) != int(total):
        return f"o livro de itens tem {len(itens)} de {int(total)} itens: livros do App incompletos"
    sim = sum(1 for i in itens if _txt(i.get("Lido")).lower() == "sim")
    if lidos is not None and sim != int(lidos):
        return f"o livro de itens tem {sim} itens lidos e o ciclo diz {int(lidos)}: livros do App incompletos"
    if linhas is not None and len(saldo) != int(linhas):
        return f"o livro de saldo tem {len(saldo)} de {int(linhas)} linhas: livros do App incompletos"
    return ""


def ciclo_comum(ciclo: list[dict], itens: list[dict], saldo: list[dict]) -> str | None:
    """O início do ciclo quando os três livros são do MESMO ciclo (o App sobe os três um depois do outro: se um falhar,
    ou o Nexus ler entre dois, ficariam Itens de hoje com Saldo de ontem). Senão, None."""
    inicios = set()
    for linhas in (ciclo, itens, saldo):
        if not linhas:
            return None
        inicios |= {_txt(l.get(INICIO)) for l in linhas}
    return inicios.pop() if len(inicios) == 1 and "" not in inicios else None
