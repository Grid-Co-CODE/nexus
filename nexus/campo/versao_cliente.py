"""As versões do cliente das telas do Nexus (08/11/2026, Levi: "a ideia é liberar os campos e conforme for o cliente
aparecerá as usinas só daquele cliente"; o filtro de mês no topo vale para todas).

Cada tela que o setor Clientes vê ganha aqui a conta da versão dele: o mesmo dado da tela da Grid, SÓ das usinas do
cliente da sessão (`setor_telas.usinas_do_cliente`) e no mês escolhido (`setor_telas.mes_do_cliente`), e SEM o que o
mockup da Visão do cliente tira dele: nome e telefone de técnico, supervisor, gestor, custo, horas, comentário interno e
a causa da falha antes da Engenharia. As funções são puras (recebem o dado já lido), para o teste provar o recorte.
"""
from datetime import date, datetime


def _no_mes(iso: str | None, mes: date) -> bool:
    try:
        d = datetime.fromisoformat(str(iso)[:10]).date()
    except (TypeError, ValueError):
        return False
    return d.year == mes.year and d.month == mes.month


def rondas(dados: dict, usinas: set[int], mes: date) -> dict:
    """As rondas do mês nas usinas do cliente e a cobertura de agora. Sem técnico, sem nota, sem duração."""
    feitas = [r for r in dados.get("todas") or [] if r.get("usina_id") in usinas and _no_mes(r.get("data"), mes)]
    linhas = [{"data": r["data"], "usina": r.get("usina") or "", "onde": r.get("cidade") or "",
               "tipo": r.get("tipo") or "Ronda", "os": r.get("os"),
               "pendente": bool(r.get("pendencia")),
               "situacao": "com pendência" if r.get("pendencia") else "concluída"}
              for r in sorted(feitas, key=lambda r: (r.get("data") or "", r.get("fim") or ""), reverse=True)]
    cobertura = [{"usina": c.get("usina") or "", "ultima": c.get("ultima"),
                  "dias": c.get("dias") if c.get("ultima") else None}
                 for c in dados.get("cobertura") or [] if c.get("usina_id") in usinas]
    cobertura.sort(key=lambda c: (-(c["dias"] if c["dias"] is not None else 9999), c["usina"]))
    com_ronda = {r.get("usina_id") for r in feitas}
    return {"linhas": linhas, "cobertura": cobertura, "n": len(linhas),
            "usinas": len(cobertura), "com_ronda": len(com_ronda & {c.get("usina_id") for c in dados.get("cobertura") or []
                                                                    if c.get("usina_id") in usinas}),
            "atrasadas": sum(1 for c in cobertura if c["dias"] is None or c["dias"] >= 7)}
