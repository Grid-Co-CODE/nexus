"""O vocabulário puro das OS da FAMA (27/11/2026): as tabelas e as contas que não leem banco nem cadastro.

Saiu do `fama_os.py` para o "Gerar no PC" (`geracao.py`, seção do PC): o pacote que roda o motor no computador do PCM leva
o `fama_motor.py` e o que ele usa, e o `fama_os.py` puxa o cadastro e os livros do banco. Aqui só o que o adaptador do motor
precisa e o que roda igual no servidor e no PC; o `fama_os.py` reexporta tudo, e quem o usava não muda.
"""
import re
from datetime import date, timedelta, timezone

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
