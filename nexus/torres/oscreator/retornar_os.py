"""Quem retorna uma OS Em Verificação para o responsável, pelo cadastro do Nexus (Levi, 10/11/2026: "Só quem criou ou o
supervisor/responsável/gestor de contrato"). O botão "Retornar para responsável" mora no card do OS Creator, que é um clone
e não conhece o cadastro, o cofre nem o banco: a ponte põe no pedido (`ponte.encaminhar`, só na rota `/retornar`) a função
daqui, já com quem pede (a sessão do Nexus), e o clone a chama com os códigos dos ativos da OS
(`os_web/rotas_os_acoes.py`, `RETORNAR`). Quem criou a OS o clone confere sozinho, pelo Fracttal.

Os papéis são os da assinatura da PT (`nexus/campo/decisao_pt.aprovadores`): o Responsável UFV (o Responsável O&M da ficha da
usina), o Supervisor de Campo da região (o Coordenador, com a vaga aberta) e o gestor de contrato. A usina sai do código do
ativo (`Ligador.usina`, o mesmo do fato do chamado). O administrador do Nexus passa sempre, como na PT.

Só roda quando alguém pergunta pelo botão de uma OS em verificação, ou o aperta: nunca na abertura do card (o cadastro lido
na frente de uma tela já prendeu pedidos por 40 s, `nexus/torres/chamados/ufv.py`)."""
import logging

from flask import session

CHAVE = "os_web.retornar_os"            # a mesma do `rotas_os_acoes.RETORNAR` do clone (o teste confere)
log = logging.getLogger("nexus.oscreator")


def no_pedido(app):
    """A função que o clone chama, com quem pede já guardado (a sessão do Nexus é lida aqui, no pedido do Nexus)."""
    admin = bool(session.get("admin"))
    u = session.get("usuario")
    u = u if isinstance(u, dict) else {}
    email, nome = str(u.get("email") or "").strip().lower(), str(u.get("nome") or "").strip()

    def decidir(codigos):
        try:
            with app.app_context():
                return papel_nas_usinas(codigos, email, nome)
        except Exception as e:          # noqa: BLE001 — sem o cadastro, fecha e diz que é leitura
            log.warning("Retornar para responsável: não consegui ler o cadastro (%s)", type(e).__name__)
            return {"pode": False, "erro": "Não consegui ler o cadastro das usinas agora para saber se você pode "
                                           "retornar esta OS: tente de novo em instantes."}
    decidir.admin = admin
    return decidir


def papel_nas_usinas(codigos, email: str, nome: str = "", b=None) -> dict:
    """{"pode": True, "papel"} se quem pede tem um dos papéis numa usina dos ativos; senão {"pode": False, "texto"} com quem
    pode (o texto entra em "Quem retorna esta OS para o responsável: quem a criou, <texto>.")."""
    from ...campo import decisao_pt, visao
    b = b or visao._Base()
    uids = []
    for c in codigos or []:
        try:
            uid, _como = b.lig.usina("", c)
        except Exception:               # noqa: BLE001 — o código que não liga fica de fora
            uid = None
        if uid and uid not in uids:
            uids.append(uid)
    if not uids:
        return {"pode": False, "texto": "o Responsável UFV, o Supervisor de Campo ou o gestor de contrato da usina (o ativo "
                                        "desta OS não liga a uma usina do cadastro do Nexus)"}
    pid = b.pessoa_do_login(email, nome) if (email or nome) else None
    partes = []
    for uid in uids:
        ids = decisao_pt.aprovadores({"usina_id": uid}, b)["ids"]
        papel = next((k for k, v in ids.items() if pid and v == pid), None)
        if papel:
            return {"pode": True, "papel": papel}
        for k, v in ids.items():
            partes.append("o %s (%s)" % (k, b.nome_da_pessoa(v, k.split()[0].capitalize())))
    partes = list(dict.fromkeys(partes))
    if not partes:
        return {"pode": False, "texto": "o Responsável UFV, o Supervisor de Campo ou o gestor de contrato da usina (a usina "
                                        "está sem eles no cadastro)"}
    return {"pode": False, "texto": (", ".join(partes[:-1]) + " ou " + partes[-1]) if len(partes) > 1 else partes[0]}
