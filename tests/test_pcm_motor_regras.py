"""As correções de 15/10/2026 na cópia do motor do PCM (nexus/pcm/motor/README.md).

Levi: "as tarefas estão vindo com horas previstas para a mesma quantidade de horas da OS [...] a OS 15596 de Elias
Fausto, a OS toda tem 25 Horas, porém por tarefa está somando 25 horas por tarefa" e "gostaria que o tipo zeladoria só
puxasse quando o tipo de tarefa fosse de fato zeladoria, não só pelo nome".

O que estes testes seguram: a duração de cada tarefa sai da própria tarefa ("Total de Horas") nas OS de mais de uma
tarefa, a OS de uma tarefa não muda, a tarefa sem duração própria divide a da OS, e a conta não se repete; e a
zeladoria do motor vem do tipo da tarefa, não do nome. O motor roda tudo no import, então a regra de zeladoria é lida do
arquivo pelo `ast`."""
import ast
import re
import sys
import unicodedata
from datetime import timedelta
from pathlib import Path

import pandas as pd

MOTOR = Path(__file__).resolve().parents[1] / "nexus" / "pcm" / "motor"
sys.path.insert(0, str(MOTOR))
import fonte_bd_api as F          # noqa: E402

COL = "Tarefa -> Duração estimada"


def _horas(df, os_):
    x = df[df["OSs ID"] == os_][COL]
    return [round(pd.Timedelta(v).total_seconds() / 3600, 2) for v in x]


def test_duracao_e_a_da_tarefa_e_nao_a_da_os():
    h = lambda v: timedelta(hours=v)       # noqa: E731
    df = pd.DataFrame([
        # a 14331: 4 tarefas, a OS com 6 h repetida em cada uma, 1,5 h por tarefa
        *[{"OSs ID": 14331, "Tarefa": "Teste de comando remoto", COL: h(6), "Total de Horas": h(1.5)}] * 4,
        # a 15596 em miniatura: 25 h na OS, tarefas de 0,25 h a 4 h
        {"OSs ID": 15596, "Tarefa": "MPA - Inversor", COL: h(25), "Total de Horas": h(0.25)},
        {"OSs ID": 15596, "Tarefa": "MPA - String", COL: h(25), "Total de Horas": h(4)},
        # OS de uma tarefa: fica a duração da OS, mesmo com outro valor na tarefa
        {"OSs ID": 16290, "Tarefa": "Ajustes no cercamento", COL: h(6), "Total de Horas": h(1)},
        # tarefa sem duração própria: a da OS dividida pelas tarefas
        {"OSs ID": 700, "Tarefa": "A", COL: h(3), "Total de Horas": None},
        {"OSs ID": 700, "Tarefa": "B", COL: h(3), "Total de Horas": h(1)},
        {"OSs ID": 701, "Tarefa": "C", COL: h(2), "Total de Horas": timedelta(0)},
        {"OSs ID": 701, "Tarefa": "D", COL: h(2), "Total de Horas": timedelta(0)},
    ])
    novo = F._duracao_da_tarefa(df.copy())
    assert _horas(novo, 14331) == [1.5] * 4
    assert _horas(novo, 15596) == [0.25, 4.0]
    assert _horas(novo, 16290) == [6.0]
    assert _horas(novo, 700) == [1.5, 1.0] and _horas(novo, 701) == [1.0, 1.0]
    # a conta não se repete (a divisão da tarefa sem duração não pode acontecer duas vezes)
    assert F._duracao_da_tarefa(novo)[COL].equals(novo[COL])
    # o que entrou não muda
    assert _horas(df, 14331) == [6.0] * 4


def test_sem_as_colunas_devolve_como_veio():
    df = pd.DataFrame([{"OSs ID": 1, "Tarefa": "x"}])
    assert F._duracao_da_tarefa(df) is df
    vazio = pd.DataFrame(columns=["OSs ID", COL, "Total de Horas"])
    assert F._duracao_da_tarefa(vazio) is vazio


def _regra_de_zeladoria():
    texto = (MOTOR / "programacao_v7.py").read_text(encoding="utf-8")
    ns = {"re": re, "unicodedata": unicodedata, "pd": pd}
    for no in ast.parse(texto).body:
        if isinstance(no, ast.FunctionDef) and no.name in ("norm", "is_zeladoria"):
            exec(compile(ast.Module([no], []), "programacao_v7", "exec"), ns)
    return texto, ns["is_zeladoria"]


def _estimativa():
    """O estimate_h do motor, tirado do arquivo pelo `ast` com as constantes de lá; a Média da Planilha Confiabilidade
    (find_corretiva_mttr) é dublada."""
    texto = (MOTOR / "programacao_v7.py").read_text(encoding="utf-8")
    ns = {"re": re, "pd": pd, "find_corretiva_mttr": lambda tarefa: 2.5}
    nomes = {"estimate_h", "_estimate_h_sem_fracttal", "parse_duration_to_hours", "MAX_TAREFA_H", "MIN_PREVENTIVA_H",
             "_DUR_CAPADAS"}
    for no in ast.parse(texto).body:
        alvo = (no.name if isinstance(no, ast.FunctionDef) else
                next((t.id for t in getattr(no, "targets", []) if isinstance(t, ast.Name)), None))
        if alvo in nomes:
            exec(compile(ast.Module([no], []), "programacao_v7", "exec"), ns)
    return ns


def test_hora_da_tarefa_vale_para_todo_tipo():
    """Levi, 15/10/2026, sobre a 15596 (43 tarefas de MPA, 25 h na OS, 172 h com as fixas por sigla): "Tem que ser de
    acordo com nova regra". A hora é a da tarefa no Fracttal também nas MPx, sem o piso de 1 h; as fixas da calibração
    só valem para a tarefa sem duração; acima do teto, capa e lista."""
    ns = _estimativa()
    est = ns["estimate_h"]

    def t(dur_h=None, cat=None, corretiva=False, fallback=None):
        return {"OSs ID": 1, "Tarefa": "Tarefa", "mp_cat": cat, "corretiva": corretiva, "zeladoria": False,
                "mttr_h_fallback": fallback, "Tarefa -> Duração estimada": None if dur_h is None else timedelta(hours=dur_h)}

    assert est(t(0.25, "MPA")) == 0.25                       # o inversor da 15596, e não 4 h
    assert round(est(t(10 / 60, "MPM")), 4) == round(10 / 60, 4)
    assert est(t(0.5)) == 0.5                                  # sem o piso de 1 h
    assert est(t(None, "MPA")) == 4.0 and est(t(None, "MPM")) == 1.10   # sem duração: a calibração
    assert est(t(None, corretiva=True)) == 2.5                 # sem duração, corretiva: a Média da Confiabilidade
    assert est(t(None, fallback=0.5)) == ns["MIN_PREVENTIVA_H"]          # sem duração, o piso de antes
    assert est(t(20, "MPA")) == ns["MAX_TAREFA_H"] and ns["_DUR_CAPADAS"][-1][2] == 20


def test_zeladoria_pelo_tipo_da_tarefa():
    texto, is_zeladoria = _regra_de_zeladoria()
    assert "df_tasks['zeladoria']   = df_tasks['Tipo de tarefa'].apply(is_zeladoria)" in texto
    assert "KEYWORDS_ZELADORIA" not in texto
    assert is_zeladoria("Zeladoria") and is_zeladoria("ZELADORIA")
    # pelo nome, estes eram zeladoria: a corretiva de limpeza, a troca ("roça" sem acento) e o religamento de Sorocaba
    for tipo in ("Corretiva", "Preventiva", "Religamento", "Inspeção", "", None, float("nan")):
        assert not is_zeladoria(tipo)
