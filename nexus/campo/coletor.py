"""O que sobrou do coletor da torre Campo · App: o contexto da cifra do nome do técnico no livro `campo_nexus`.

O coletor do Fracttal (laço de escrita, `rodar`, `ligar`) está APOSENTADO desde 05/10/2026 e saiu do código em
08/11/2026 (gastava a cota de 200/min da empresa e a nota que recalculava batia com a do painel do App em 14% das
tarefas). Fica o que a fonte do banco ainda precisa para abrir o livro dele como reserva: o contexto com que o nome
foi cifrado (`fonte_pg.py` decifra com ele).
"""
from . import banco_campo


def contexto_do_tecnico(id_tarefa) -> str:
    return f"{banco_campo.WORKBOOK}/{banco_campo.ABA}/{id_tarefa}/tecnico"
