"""O status do chamado no fato (28/10/2026, Levi, no Painel do responsável: "Seria bom mostrar o status do chamado"): o da
tela de Garantias do OS Creator, a última troca pela tela (`os_creator · chamados_obs`) ou, sem troca, o "Status atual"
da nota da OS retroativa; só os valores da lista da analista, com a linhagem (`status_por`). Dado falso: nenhuma pessoa,
nenhum texto de nota real."""
import ast
import json
from pathlib import Path

from test_campo_chamados_acompanhamento import AGORA, _Fracttal, _lig, _w, banco  # noqa: F401  (banco é fixture)

from nexus.campo import chamados_acompanhamento as P
from nexus.dados import dominios as DOM
from nexus.dados import fato_chamado as F

RAIZ = Path(__file__).resolve().parent.parent
NOTA_RETRO = ("[CHAMADO] Acompanhamento — Sungrow · Inversor\n"
              "OS de abertura: 4142 · UFV: Usina Teste · Ticket: 24910\n"
              "Status atual: Aguardando retorno do Cliente · Equipamento: RSU\n"
              "Data da ocorrência / abertura do chamado: 26/01/2026\n"
              "Histórico:\n"
              "10/02 - Status atual: Testes em campo\n")


def test_a_lista_e_a_mesma_da_tela_de_garantias():
    """CÓPIA de `acomp_web.STATUS_CHAMADO` (o OS Creator não importa o Nexus, e a camada de dados não importa o clone):
    lida do arquivo, sem importar."""
    arq = RAIZ / "nexus" / "torres" / "oscreator" / "os_creator" / "os_web" / "acomp_web.py"
    arvore = ast.parse(arq.read_text(encoding="utf-8"))
    tela = next(ast.literal_eval(n.value) for n in arvore.body
                if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "STATUS_CHAMADO" for t in n.targets))
    assert tuple(tela) == DOM.STATUS_CHAMADO


def test_o_dominio_do_status():
    assert DOM.status_chamado("Aguardando retorno do Fabricante") == "Aguardando retorno do Fabricante"
    assert DOM.status_chamado("  aguardando RETORNO pre - operacao ") == "Aguardando retorno Pré - Operação"
    assert DOM.status_chamado("STANDBY") == "Standby"
    # Levi, 28/10/2026, sobre os 2 da planilha: "Standby nos 2; Sem status no outro"
    assert DOM.status_chamado("STANDBY – chamado fechado pelo fabricante em 10/09") == "Standby"
    assert DOM.status_chamado("Testes em campo: inversor religado") == "Testes em campo"
    assert DOM.status_chamado("(em branco na V02)") is None
    assert DOM.status_chamado("Standbyzinho") is None                    # começa igual, sem o separador: fora
    assert DOM.status_chamado("") is None and DOM.status_chamado(None) is None


def test_o_status_atual_da_nota_como_a_tela_le():
    assert F.status_da_nota(NOTA_RETRO) == "Aguardando retorno do Cliente"      # o do cabeçalho, nunca o do histórico
    assert F.status_da_nota("[CHAMADO] Acompanhamento — STI · Estrutura Trackers\nOS de campo: 1") is None
    assert F.status_da_nota("Status atual: Standby") is None                    # sem a marca: não é a OS do chamado
    assert F.status_da_nota(None) is None


def test_a_ultima_troca_pela_tela_vale():
    obs = [{"os": "17311", "tipo": "status", "quando": "2026-10-28T10:00:00", "extra": json.dumps({"status": "Standby"})},
           {"os": "17311", "tipo": "obs", "quando": "2026-10-28T11:00:00", "extra": "{}"},
           {"os": "17311", "tipo": "status", "quando": "2026-10-28T09:00:00",
            "extra": {"status": "Testes em campo"}},                            # mais velha, mesmo vindo depois
           {"os": "17400", "tipo": "status", "quando": "2026-10-27T09:00:00", "extra": json.dumps({"status": ""})},
           {"os": "", "tipo": "status", "quando": "2026-10-27T09:00:00", "extra": "{}"}]
    assert F.status_da_tela(obs) == {"17311": "Standby", "17400": ""}


def test_a_tela_por_cima_da_nota_e_a_linhagem():
    tela = {"17311": "Aguardando retorno do Fabricante", "17400": ""}
    assert F.status_do_chamado(17311, NOTA_RETRO, tela) == ("Aguardando retorno do Fabricante", "tela", False)
    assert F.status_do_chamado(17400, NOTA_RETRO, tela) == (None, "tela", False)     # trocado para "Sem status"
    assert F.status_do_chamado(17500, NOTA_RETRO, tela) == ("Aguardando retorno do Cliente", "nota", False)
    assert F.status_do_chamado(17600, "[CHAMADO] Acompanhamento — STI · X\nStatus atual: (em branco na V02)",
                               {}) == (None, "nota", True)                       # fora da lista: vazio e conta
    assert F.status_do_chamado(17700, "[CHAMADO] Acompanhamento — STI · X", {}) == (None, None, False)


def test_as_colunas_novas_no_fim_e_a_conta_do_fora_da_lista():
    from collections import Counter
    assert F.CAB_CHAMADO[-2:] == ["status", "status_por"]
    rows = [_w(16034, 1, "2026-10-10T13:00:00+00:00", nota=NOTA_RETRO),
            _w(16040, 1, "2026-10-10T13:00:00+00:00",
               nota="[CHAMADO] Acompanhamento — STI · X\nStatus atual: (em branco na V02)"),
            _w(16050, 1, "2026-10-10T13:00:00+00:00")]
    conta = Counter()
    out = F.linhas(rows, _lig(), {}, None, {"16050": "Standby"}, conta)
    d = {r[0]: dict(zip(F.CAB_CHAMADO, r)) for r in out}
    assert (d[16034]["status"], d[16034]["status_por"]) == ("Aguardando retorno do Cliente", "nota")
    assert (d[16040]["status"], d[16040]["status_por"]) == (None, "nota")
    assert (d[16050]["status"], d[16050]["status_por"]) == ("Standby", "tela")
    assert conta["status_fora_da_lista"] == 1


def test_a_publicacao_le_a_troca_feita_na_tela(app, banco):
    banco.workbooks["os_creator"] = {}
    banco._id("os_creator", "chamados_obs")["linhas"] = [
        {"headers": ["id", "quando", "os", "ativo", "tipo", "texto", "quem", "email", "extra"],
         "values": ["a1", "2026-10-11T09:00:00", "16034", "X", "status", "Status: Standby", "", "",
                    json.dumps({"status": "Standby"})]}]
    ler = _Fracttal({1: [_w(16034, 1, "2026-10-10T13:00:00+00:00", nota=NOTA_RETRO)]})
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert (rel["status_tela"], rel["status_nota"], rel["status_fora_da_lista"]) == (1, 0, 0)
    linha = banco.linhas(F.LIVRO, F.ABA)[0]
    assert (linha["status"], linha["status_por"]) == ("Standby", "tela")
    # da aba das observações só o status sai: nem o texto, nem a pessoa, nem o e-mail
    assert set(linha) == set(F.CAB_CHAMADO)
