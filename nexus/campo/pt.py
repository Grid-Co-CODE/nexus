"""Permissões de trabalho do Nexus: a fila de PT do painel do App (Levi aprovou a proposta em 04/10/2026).

Quem calcula é a cópia das regras do App (regras_app.py): o mesmo `_pt_lista` + `_pt_publico` da rota gestao/pt,
com o mesmo destaque (PT_DESTAQUE_MIN) e a mesma validade. A PT sai SEM o modo "completo" do App: nada de assinatura
nem das respostas da APR, que a tela do Nexus não mostra. Decidir (De acordo / Não autorizo) continua no App.
"""
from . import leitura, regras_app, tabelas
from .leitura import Leitura

# as tabelas do App que esta tela lê; na dos tokens, só as partições pt e cadastro, cada uma pela sua chave
TABELAS = ("acessos", "atribuicoes", ("fracttaltokens", "pt"), ("fracttaltokens", "cadastro"))
# escopo de Admin: vê todas as PT (no Nexus só entra quem tem a senha de admin)
ESCOPO_ADMIN = {"clusters": None, "papel": "Admin"}
DIAS_ESPERANDO = 7        # como o painel do App: gestao/pt?so=aguardando&dias=7
DIAS_HISTORICO = 30       # e o histórico padrão de 30 dias
SITUACOES = ("aguardando", "de_acordo", "negada", "vencida")


def situacao(p) -> str:
    """A situação como o painel do App mostra (ptSit, no gestao.html): vencida é a "de acordo" que passou da validade."""
    st = p.get("status")
    if st == "aguardando":
        return "aguardando"
    if st == "negada":
        return "negada"
    return "vencida" if p.get("vencida") else "de_acordo"


def configurado() -> bool:
    return tabelas.configurado(TABELAS)


def painel(dias: int = DIAS_HISTORICO) -> Leitura:
    def calcular():
        r = regras_app
        esperando = [r._pt_publico(e) for e in r._pt_lista(DIAS_ESPERANDO, status="aguardando")
                     if r._pt_ve(ESCOPO_ADMIN, "", e)]
        esperando = sorted((x for x in esperando if x["status"] == "aguardando"), key=lambda x: x.get("criado_em") or "")
        for x in esperando:
            x["atrasada"] = (x.get("idade_min") or 0) >= r.PT_DESTAQUE_MIN
        dh = max(1, min(int(dias), r.PT_HIST_DIAS_MAX))
        historico = [r._pt_publico(e) for e in r._pt_lista(dh, campos=r.PT_CAMPOS_RESUMO) if r._pt_ve(ESCOPO_ADMIN, "", e)]
        historico.sort(key=lambda x: x.get("criado_em") or "", reverse=True)
        for x in historico:
            x["situacao"] = situacao(x)
        return {"esperando": esperando, "historico": historico[:r.PT_HIST_MAX], "total": len(historico),
                "contagem": {k: sum(1 for x in historico if x["situacao"] == k) for k in SITUACOES},
                "destaque_min": r.PT_DESTAQUE_MIN, "validade_dias": r.PT_VALIDADE_DIAS, "dias": dh}
    return leitura.ler(("pt", int(dias)), calcular)
