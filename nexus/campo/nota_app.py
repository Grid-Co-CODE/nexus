"""A nota que o App de Campo dá a cada tarefa e o porquê dela, pela "Composição da nota" que o App grava no livro dos
fechamentos (`fechamentos_app_campo`, coluna "Composição da nota"; no formato da tabela do App, `nota_itens`).

A composição é a lista dos critérios do App (`regras_app._qualidade_os`: subtarefas obrigatórias, fotos, fotos com
descrição, assinatura, observações e GPS no fechamento), cada um com o peso, os pontos que a tarefa fez nele e o detalhe
("2 de 4 pedidas"); os pesos somam 100. Quem perdeu ponto num critério é quem explica a nota abaixo de 80.

Nasceu em 09/11/2026 com o pedido do Levi para a Aprovação de OS (pelo Scrum master): "Em OS 8159 aprovação de OS diz
que está aprovado porém a OS tem nota 50 no app, o interessante é ele saber o motivo da nota, tem que ter 'motivo da
nota abaixo de 80'". A leitura da composição era da janela do Ranking das equipes, que saiu no mesmo dia.
"""
import json

# a régua do App para a nota boa (o mesmo 80 da Triagem do App, `regras_app.TRIAGEM_NOTA_OK`)
NOTA_OK = 80


def itens(v) -> list[dict]:
    """A composição como lista de {"rot", "peso", "pts", "det"}; texto que não é a lista esperada vira lista vazia."""
    try:
        lista = json.loads(v) if isinstance(v, str) else v
    except ValueError:
        return []
    if not isinstance(lista, list):
        return []
    return [{"rot": str(i.get("rot") or ""), "peso": i.get("peso"), "pts": i.get("pts"), "det": str(i.get("det") or "")}
            for i in lista if isinstance(i, dict) and i.get("rot")]


def perdeu(it: dict) -> float:
    """Os pontos que a tarefa perdeu no critério (peso − pontos)."""
    try:
        return max(0.0, float(it.get("peso") or 0) - float(it.get("pts") or 0))
    except (TypeError, ValueError):
        return 0.0


def num(v) -> str:
    """O ponto como o App mostra: inteiro sem casa, o resto com uma casa e vírgula (13,3)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "?"
    return str(int(round(x))) if abs(x - round(x)) < 0.05 else f"{x:.1f}".replace(".", ",")


def motivo(nota, composicao) -> str:
    """O motivo da nota abaixo de 80, numa frase: os critérios em que a tarefa perdeu pontos, o que mais perdeu primeiro,
    cada um com o detalhe do App. Nota de 80 para cima, ou sem nota = "" (não há o que explicar). Sem a composição no
    livro (o App não guardou), diz isso em vez de inventar o porquê."""
    if nota is None or int(nota) >= NOTA_OK:
        return ""
    perdas = sorted((x for x in itens(composicao) if perdeu(x) > 0.05), key=lambda x: -perdeu(x))
    if not perdas:
        return "o App não guardou a composição desta nota"
    return "; ".join(f"{x['rot']} perdeu {num(perdeu(x))} de {num(x['peso'])}" + (f" ({x['det']})" if x["det"] else "")
                     for x in perdas)
