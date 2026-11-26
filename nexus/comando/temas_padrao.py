"""Os temas padrão das demandas entre setores (14/11/2026).

Levi: "crie temas padrões para setores. O que seria solicitado? Então, o que um supervisor solicitaria para o setor? O que
o setor poderia solicitar para o supervisor [...] acompanhamento de chamado, verificação da engenharia, verificação de
ativo da engenharia, verificação de ativo da performance, todas essas indicações que o Nexus IA pode gerar, transformar em
um tema para diferentes setores. Lembrando que o setor da performance também tem chamados [...] a parte da performance
poderia iniciar com ter a opção de escolher o setor chamados, mas no back-end entender que é um setor de performance [...]
E aí, mais ter temas separados para ele."

- `PADRAO`: por setor (o nome do cadastro, sem acento), a lista (área, tema, prazo em dias úteis). Os prazos são o ponto de
  partida: cada setor muda o seu em Caixa de entrada › Temas do setor.
- A **área** é um pedaço do setor com temas próprios: "Chamados" é da Performance (não há setor de Garantias no cadastro).
  Na Nova demanda ela aparece como mais uma escolha de setor ("Chamados"); a demanda vai para a Performance
  (`para_setor_id`), com o tema da área.
- O código de cada tema padrão é fixo (`codigo`, do setor, da área e do nome): criar de novo não duplica.
"""
from __future__ import annotations

import hashlib
import unicodedata

# as áreas de cada setor (o setor pelo nome do cadastro, sem acento): o nome que aparece na Nova demanda
AREAS = {"performance": ("Chamados",)}

PADRAO = {
    # o que o supervisor pede à Engenharia (as recorrências, os ajustes, o ativo que falha)
    "engenharia": (("", "Verificação de ativo", 5), ("", "Análise de recorrência de falha", 5),
                   ("", "Revisão de ajuste de proteção", 5), ("", "Parecer técnico", 5)),
    # à Performance: o ativo pela geração, o PR, a meta e o relatório; e à área de Chamados, as garantias
    "performance": (("", "Verificação de ativo", 3), ("", "Análise de geração e PR", 3),
                    ("", "Revisão de meta ou disponibilidade", 3), ("", "Relatório da usina", 2),
                    ("Chamados", "Acompanhamento de chamado", 2), ("Chamados", "Abertura de chamado de garantia", 2),
                    ("Chamados", "Cobrança ao fabricante", 2), ("Chamados", "Envio de peça ou RMA", 5),
                    # 15/11/2026, da pré-análise de 5 usinas pela IA (Levi: "todas as ações que a IA sugerir ver como
                    # tema e aí a gente coloca como padrão"): Céu Azul e Santa Maria do Pará pediam juntar a corretiva
                    # ao chamado de garantia do mesmo equipamento
                    ("Chamados", "Vincular OS ao chamado de garantia", 2)),
    # ao COS: a concessionária, o religamento, o alarme
    "cos": (("", "Chamado com a concessionária", 1), ("", "Religamento remoto", 1), ("", "Verificação de alarme", 1),
            ("", "Acompanhamento de parada", 1)),
    "pcm": (("", "Programação de ronda", 2), ("", "Reprogramação de OS", 2), ("", "Programação de manutenção", 3)),
    # a comunicação da usina (Céu Azul: "restaurar comunicação da usina, offline há 195 dias", da mesma pré-análise)
    "manutencao": (("", "Execução de corretiva", 3), ("", "Verificação em campo", 2), ("", "Peça ou material", 5),
                   ("", "Restabelecer a comunicação da usina", 2)),
    # a conferência dos extintores é diferente da recarga (Linhares 1 e Mãe do Rio: "conferir os extintores sem conferência")
    "seguranca": (("", "Extintor vencido ou recarga", 5), ("", "Conferência de extintores", 3), ("", "Verificação de EPI", 3),
                  ("", "APR ou análise de risco", 3)),
    # a vala obstruída ou parcial (Céu Azul, Mãe do Rio e Santa Maria do Pará, na zeladoria)
    "zeladoria": (("", "Limpeza de módulos", 5), ("", "Roçada e vegetação", 5), ("", "Desobstrução de vala e drenagem", 5)),
    # o que os setores pedem ao supervisor de campo
    "supervisao campo": (("", "Inspeção na usina", 2), ("", "Informação de campo", 1), ("", "Retorno de OS", 2),
                         ("", "Foto ou evidência", 1),
                         # a demanda que sai do chamado de Garantias para o supervisor da usina (24/11/2026, Levi:
                         # "Podemos criar um tema de acompanhamento de chamado. E aí o supervisor pode responder até 3
                         # dias úteis"); é o tema que a Nova demanda do chamado já traz escolhido (`TEMA_DO_CHAMADO`)
                         ("", "Acompanhamento de chamado", 3)),
    "supervisor de contrato": (("", "Comunicação ao cliente", 2), ("", "Informação do contrato", 3)),
}


# o tema que a Nova demanda do chamado de Garantias já traz escolhido: o setor do supervisor de campo e o nome do padrão
TEMA_DO_CHAMADO = ("", "Acompanhamento de chamado")


def chave(nome) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", str(nome or ""))
                            if not unicodedata.combining(c)).lower().split())


def codigo(setor_id, area: str, nome: str) -> str:
    """O tema_id fixo do tema padrão ("m" + 11 hexadecimais, o formato do `ID_TEMA`)."""
    return "m" + hashlib.sha1(f"padrao|{setor_id}|{chave(area)}|{chave(nome)}".encode()).hexdigest()[:11]


def areas_do_setor(nome_setor) -> tuple:
    return AREAS.get(chave(nome_setor), ())


def para_criar(setores: list[dict], temas: list[dict]) -> list[dict]:
    """Os temas padrão que faltam: [{tema_id, setor_id, area, nome, prazo_dias_uteis}]. Falta = nem o código fixo nem um
    tema do setor com o mesmo nome e a mesma área (o tema que o setor já criou à mão não ganha um gêmeo)."""
    ja_ids = {t.get("tema_id") for t in temas}
    ja_nomes = {(t.get("setor_id"), chave(t.get("area")), chave(t.get("nome"))) for t in temas}
    out = []
    for s in setores:
        for area, nome, prazo in PADRAO.get(chave(s.get("nome")), ()):
            tid = codigo(s["setor_id"], area, nome)
            if tid in ja_ids or (s["setor_id"], chave(area), chave(nome)) in ja_nomes:
                continue
            out.append({"tema_id": tid, "setor_id": s["setor_id"], "area": area, "nome": nome, "prazo_dias_uteis": prazo})
    return out
