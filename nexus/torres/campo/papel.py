"""O papel de quem entrou pelo Fracttal, que as telas do Campo usam para vir já filtradas (a região do Supervisor de
Campo, as usinas do Gestor de contrato, o Responsável O&M). Morava no portão do Aprovar da Aprovação de OS
(`aprovar_os.py`), que saiu em 18/10/2026 (Levi: "pode tirar a rota antiga!"): aprovar é o Concluir do card do OS
Creator."""
from flask import session


def papel_da_sessao() -> dict:
    """O papel de quem entrou pelo Fracttal (`supervisor_padrao`, gravado no login). Sessão de antes da estrutura de
    O&M de 10/2026 guardava ali o nome do supervisor (texto): não vale como papel."""
    p = session.get("supervisor_padrao")
    return p if isinstance(p, dict) else {}
