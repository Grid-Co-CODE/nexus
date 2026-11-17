"""O aviso do Fora da programação ao setor citado, no topo, ao lado do botão do OS Creator (16/11/2026).

Levi, 16/11/2026: "fora da programação deve notificar quem é daquele setor caso o setor seja citado! a notificação fica
ao lado da notificação do OS Creator". O setor citado é o do MOTIVO da tarefa (`motivos.SETOR_PADRAO` e a coluna "Avisa
o setor" do Cadastro de motivos, `dim_motivo.setor_id`), pelo ID do setor, nunca pelo nome; o texto da justificativa não
conta. Quem é do setor é quem tem o setor em Base → Acessos → Pessoas e setores (`setor_telas.acesso`).

O aviso é a tarefa que SEGUE fora da programação com o motivo (a marca que vale, `motivos.vigentes`), até a pessoa
marcar como lida; a tarefa que volta à programação sai sozinha. O lido é o `leu` do livro dos avisos do sino
(`comando/avisos.py`, `nexus_avisos · fato_evento_aviso`), com o aviso `F:<item_id>:<desde, AAAAMMDDHHMM>`: trocar só a
observação não é aviso novo; o motivo que sai e volta, é. Medido no livro do servidor em 16/11/2026: 171 tarefas fora,
5 de Engenharia, 1 de Performance e nenhuma de Chamados.

Só da cópia do livro (`motivos.copia`): nenhuma página espera o banco por causa dele. A conta de cada setor fica guardada
enquanto a cópia é a mesma: decifrar as marcas a cada página custaria em toda tela do Nexus.
"""
import re
import threading

from . import motivos as M

_CACHE: dict = {}
_TRAVA = threading.Lock()


def limpar() -> None:
    _CACHE.clear()


def aviso_id(marca: dict) -> str:
    """F:<item_id>:<desde, AAAAMMDDHHMM em UTC>: a tarefa e o começo da sequência com o motivo."""
    return f"F:{marca['item_id']}:{re.sub(r'[^0-9]', '', marca.get('desde') or '')[:12].ljust(12, '0')}"


def _quando_txt(iso) -> str:
    d = M._brt(iso)
    return d.strftime("%d/%m %H:%M") if d else ""


def do_setor(cfg, est: dict, setor_id) -> list[dict]:
    """As tarefas que seguem fora da programação com um motivo que cita o setor, a mais nova primeiro."""
    setores = {m["id"]: m.get("setor_id") for m in M.ativos(est)}
    if setor_id not in setores.values():
        return []
    out = []
    for iid, m in M.vigentes(cfg, est).items():
        if iid.startswith("_") or setores.get(m["motivo_id"]) != setor_id:
            continue
        out.append({"id": aviso_id(m), "os": m["os"], "tarefa": m["tarefa"], "usina": m["usina"],
                    "cliente": m["cliente"], "motivo": m["motivo"], "obs": m["obs"], "quem": m["quem_motivo"],
                    "pelo_app": m["origem_motivo"] == "app", "desde": m["desde"], "quando_txt": _quando_txt(m["desde"])})
    return sorted(out, key=lambda a: a["desde"], reverse=True)


def citado(est: dict, setor_id) -> bool:
    """Algum motivo do cadastro cita o setor (sem nenhum, o botão do topo não aparece para ele)."""
    return any(m.get("setor_id") == setor_id for m in M.ativos(est))


def para_o_sino(cfg, setor_id, lidos: set) -> list[dict] | None:
    """Os avisos não lidos do setor, da cópia do livro. None: sem a cópia (logo depois de subir) ou sem motivo que cite o
    setor."""
    est = M.copia(cfg)
    if not est or not setor_id or not citado(est, setor_id):
        return None
    chave = (id(est), est.get("lido_em"), setor_id)
    with _TRAVA:
        lista = _CACHE.get(chave)
    if lista is None:
        lista = do_setor(cfg, est, setor_id)
        with _TRAVA:
            for k in [k for k in _CACHE if k[2] == setor_id]:
                del _CACHE[k]
            _CACHE[chave] = lista
    return [a for a in lista if a["id"] not in lidos]
