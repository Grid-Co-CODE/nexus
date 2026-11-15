"""O bloco [PCM] não vai para a nota da OS (Levi, 15/11/2026, no prontuário de uma usina: "As subtarefa, nota da OS não
deveria estar aparecendo"). O bloco é o transporte da Fila do PCM dentro da observação da solicitação (tema, data
sugerida, subtarefas); a aprovação mandava a observação inteira como nota da OS, e a OS nascia com a lista das
subtarefas na nota (a 18338 de uma usina real). Agora a aprovação manda só o que a pessoa escreveu, e o card e o Raio X
tiram o bloco das OS que já nasceram com ele, sem cortar o comentário que veio depois. Textos inventados."""
from test_oscreator_solic_pcm import OBS, api, cli, sp  # noqa: F401  (fixture)

import os_detalhe

from nexus.engenharia import os_equipe

RELATO = "Inversor desligando à tarde."
BLOCO = sp.observacao_com_bloco("", {"tema": "vegetacao", "data": "03/11/2026 08:00",
                                     "subtarefas": [{"tipo": "texto", "desc": "Roçar o entorno"},
                                                    {"tipo": "foto", "desc": "Foto do depois", "anexo": True}]})


def test_sem_bloco_tira_so_o_bloco_e_guarda_o_que_vem_depois():
    nota = RELATO + "\n\n" + BLOCO + "\n\n15/11/2026 10:00 - Comentário da Engenharia"
    assert sp.sem_bloco(nota) == RELATO + "\n\n15/11/2026 10:00 - Comentário da Engenharia"
    assert sp.sem_bloco(BLOCO) == ""
    assert sp.sem_bloco(RELATO) == RELATO
    assert sp.sem_bloco("") == "" and sp.sem_bloco(None) == ""


def test_a_aprovacao_manda_so_o_relato_na_nota(cli):
    assert "[PCM]" in OBS
    r = cli.post("/os/api/solic/5001/aprovar", json={"id_responsible": 1, "responsavel": "Ana Teste Silva", "titulo": "T"})
    assert r.status_code == 200
    assert cli.gravado[-1][-1]["note"] == RELATO


def test_o_card_e_o_raio_x_nao_mostram_o_bloco_da_os_que_ja_nasceu_com_ele():
    tarefas = [{"note": RELATO + "\n\n" + BLOCO, "task_note": RELATO + "\n\n" + BLOCO}]
    assert os_detalhe.juntar_notas(tarefas) == [RELATO]
    assert os_equipe._nota_da_os(tarefas) == RELATO
    so_o_bloco = [{"note": "", "task_note": BLOCO}]
    assert os_detalhe.juntar_notas(so_o_bloco) == [] and os_equipe._nota_da_os(so_o_bloco) == ""
