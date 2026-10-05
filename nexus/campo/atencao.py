"""Central de atenção do Nexus: as mesmas contas do painel do App (Levi, 04/10/2026: "pode passar para o Nexus").

Quem calcula é a cópia das regras do App (regras_app.py): o mesmo `_central_atencao` + `_aplicar_tratamentos` da
rota gestao/atencao, e para os encaminhamentos o mesmo filtro da rota gestao/encaminhamentos?todos=1 com o mesmo
`_enc_resumo`. O escopo é o do Admin (vê tudo): no Nexus só entra quem tem a senha de admin.
"""
import importlib

from . import leitura, regras_app
from .leitura import Leitura  # noqa: F401  (a tela e os testes usam daqui)

# as tabelas do App que esta tela lê; sem a chave de todas, a tela segue no painel do App
TABELAS = ("rondas", "atencaoos", "decisoes", "rondaativos")
# os estados que a rota gestao/encaminhamentos?todos=1 do App lista
ESTADOS_ENC = ("encaminhada", "feita", "confirmada", "resolvida")


def limpar_cache():
    """Esquece o que foi lido, inclusive os caches internos das regras do App (catálogo de usinas, fila do Fracttal)."""
    leitura.limpar()
    importlib.reload(regras_app)


def central(dias: int = 14) -> Leitura:
    def calcular():
        d = regras_app._central_atencao(None, int(dias))
        d["pontos"] = regras_app._aplicar_tratamentos(d.get("pontos") or [])
        return d
    return leitura.ler(("central", int(dias)), calcular)


def encaminhamentos() -> Leitura:
    def calcular():
        hoje = regras_app._agora_iso()[:10]
        itens = []
        for t in regras_app._tratamentos().values():
            est = str(t.get("estado"))
            if est not in ESTADOS_ENC:
                continue
            itens.append({
                "chave": t.get("RowKey"), "estado": est, "tipo": t.get("tipo"), "usina": t.get("usina"),
                "os": t.get("os"), "oque": t.get("oque"), "instrucao": t.get("motivo"), "prazo": t.get("prazo"),
                # como no App: sem prazo também conta como vencida ("" < hoje)
                "vencida": str(t.get("prazo") or "") < hoje,
                "resp_nome": t.get("resp_nome"), "por_nome": t.get("por_nome"), "quando": t.get("quando"),
                "desfecho": t.get("desfecho") or "", "os_gerada": t.get("os_gerada") or "",
                "seguranca": str(t.get("tipo") or "") in regras_app.ATN_SEG,
                "conversas": len(regras_app._hist_ler(t)),
            })
        resumo = regras_app._enc_resumo(itens, hoje)
        # Apresentação: o que está aberto vem antes do que já fechou; dentro de cada grupo, a ordem do App
        # (vencidas primeiro, depois o prazo mais antigo).
        itens.sort(key=lambda x: (x["estado"] != "encaminhada", not x["vencida"], str(x.get("prazo") or "9999")))
        return {"itens": itens, "total": len(itens), "resumo": resumo}
    return leitura.ler(("enc",), calcular)
