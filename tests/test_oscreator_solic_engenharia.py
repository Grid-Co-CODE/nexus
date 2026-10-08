"""A Nova solicitação para a ENGENHARIA no OS Creator Web do Nexus (Levi, 06/10/2026): "Em 'Nova Solicitação' aparecerá
duas opções, PCM e Engenharia. PCM realmente criará uma solicitação. Para engenharia terá uma tela nova, estilo
Performance > Geração e ETM > ETM ... porém liberada para todos os ativos".

Pedidos de 08/10/2026: "Agrupar ativos em atividades por OS" (uma OS com uma atividade por ativo, além de uma OS por
ativo) e "Engenharia poder anexar arquivos" (PDF, imagem, planilha, documento, em cada OS criada).

Regras em `os_web/solic_eng_web.py` (do clone) e a tela inteira pelo app do clone, com o api trocado por dublês — nenhum
teste aqui faz rede, cria OS ou sobe anexo de verdade. Nomes, códigos e usinas são de mentira: o repositório é público."""
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app, solic_eng_web as reg  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE, "os_web")
JWT ="aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
USINA = "Cliente X - Usina Teste 1 - UF"
CATALOGO = [
    {"id": 1, "code": "TST-NBRK1", "label": "TST-NBRK1 — Nobreak", "description": "Nobreak 1      { TST-NBRK1 }",
     "tipo": "NBRK", "usina": USINA, "cliente": "Cliente X"},
    {"id": 2, "code": "TST-INV11", "label": "Inversor 1.1", "description": "Inversor 1.1 Marca Teste", "tipo": "Inversor",
     "usina": USINA, "cliente": "Cliente X"},
    {"id": 3, "code": "TST-RELE1", "label": "TST-RELE1 — Relé da Cabine", "description": "Relé da Cabine 1",
     "tipo": "RELE", "usina": USINA, "cliente": "Cliente X"},
    {"id": 4, "code": "OUT-INV99", "label": "Inversor 9.9", "description": "Inversor 9.9", "tipo": "Inversor",
     "usina": "Cliente Y - Outra Usina - UF", "cliente": "Cliente Y"},
]
PESSOAS = [{"code": "A1", "name": "Ana Teste Silva", "id_personnel": 501}, {"code": "B2", "name": "Bruno Souza", "id_personnel": 502},
           {"code": "B3", "name": "Brunoso Lima", "id_personnel": 503}, {"code": "C4", "name": "Carla Dias", "id_personnel": 504},
           {"code": "S0", "name": "Ana Teste Semid", "id_personnel": None}]
CFG = "Ana Teste;Bruno;Zeca"
AGORA = dt.datetime(2026, 10, 6, 10, 0, tzinfo=reg.BRT)
ETIQ = [{"id": 1, "description": "PERFORMANCE"}, {"id": 900, "description": "ENGENHARIA"}, {"id": 901, "description": "Remoto"},
        {"id": 902, "description": "Religamento Remoto"}, {"id": 2603, "description": "Dar prioridade"}]


# ── regras ─────────────────────────────────────────────────────────────────────────────────────────────
def test_tipo_de_ativo_com_o_nome_no_lugar_da_sigla():
    assert reg.rotulo_tipo("NBRK") == "Nobreak" and reg.rotulo_tipo("DINV") == "Disjuntor do Inversor"
    assert reg.rotulo_tipo("Inversor") == "Inversor" and reg.rotulo_tipo("NCU") == "NCU"     # sem nome no cadastro: como veio
    ativos = reg.ativos_da_usina(CATALOGO, USINA)
    assert reg.tipos_de(ativos) == [("Inversor", "Inversor"), ("NBRK", "Nobreak"), ("RELE", "Relé da Cabine")]


def test_todos_os_ativos_da_usina_de_qualquer_tipo():
    ativos = reg.ativos_da_usina(CATALOGO, USINA, api._asset_short_name)
    assert [a["code"] for a in ativos] == ["TST-INV11", "TST-NBRK1", "TST-RELE1"]           # pelo nome do tipo
    assert [a["curto"] for a in ativos] == ["Inversor 1.1", "Nobreak 1", "Relé da Cabine 1"]       # o mesmo do título


def test_responsavel_so_entre_os_nomes_da_engenharia():
    pessoas, faltam = reg.responsaveis(PESSOAS, reg.nomes_configurados(CFG))
    # "Bruno" não casa com "Brunoso"; quem não tem id_personnel não recebe OS; "Zeca" não está no Fracttal
    assert [p["name"] for p in pessoas] == ["Ana Teste Silva", "Bruno Souza"] and faltam == ["Zeca"]
    assert reg.nomes_configurados("") == [] and reg.nomes_configurados(" A ; B,C ") == ["A", "B", "C"]


def test_etiquetas_so_remoto_e_engenharia_pelo_nome_exato():
    """Levi, 06/10/2026: "Etiqueta de remoto e engenharia fixas sempre! só essas etiquetas viu, sem performance"."""
    assert reg.ETIQUETAS == ("Remoto", "ENGENHARIA")
    assert reg.etiquetas(ETIQ) == ([901, 900], [])
    # sem a "Remoto" no catálogo, a "Religamento Remoto" NÃO serve no lugar: a falta é dita, e nada é criado
    assert reg.etiquetas([e for e in ETIQ if e["id"] != 901]) == ([900], ["Remoto"])
    assert (reg.TIPO_TAREFA, reg.CLASSIF_1) == ("Administrativa", "Programada")


def test_data_programada_7_dias_e_urgente_2():
    assert reg.data_padrao(AGORA, False) == AGORA + dt.timedelta(days=7)
    assert reg.data_padrao(AGORA, True) == AGORA + dt.timedelta(days=2)


def _corpo(**muda):
    c = {"ativos": [1, 3], "descricao": "  Avaliar   o religamento ", "problema": "Desarma toda manhã.",
         "responsavel": {"id_personnel": 501}, "urgente": False}
    c.update(muda)
    return c


def test_o_pedido_e_conferido_no_servidor():
    por_id = {str(a["id"]): a for a in CATALOGO}
    ok, _ = reg.responsaveis(PESSOAS, reg.nomes_configurados(CFG))
    erros = [reg.montar(_corpo(**m), por_id, ok, AGORA, api.perf_os_nome)[2]
             for m in ({"ativos": []}, {"ativos": [77]}, {"descricao": " "}, {"problema": ""}, {"responsavel": {"id_personnel": 504}})]
    assert erros == ["Marque ao menos um ativo.", "Um dos ativos marcados não está no catálogo — recarregue a página.",
                     "Escreva a atividade a ser realizada (o nome da OS).", "Descreva o problema.",
                     "Escolha o responsável entre os nomes da Engenharia."]
    ativos, c, erro = reg.montar(_corpo(), por_id, ok, AGORA, api.perf_os_nome)
    assert erro == "" and [a["code"] for a in ativos] == ["TST-NBRK1", "TST-RELE1"]
    assert c["por_ativo"] == {"TST-NBRK1": {"description": "[Nobreak 1] - Avaliar o religamento"},
                              "TST-RELE1": {"description": "[Relé da Cabine 1] - Avaliar o religamento"}}
    assert (c["note"], c["id_responsible"], c["responsible_name"]) == ("Desarma toda manhã.", 501, "Ana Teste Silva")
    assert c["prog_date"] == dt.datetime(2026, 10, 13, 10, 0, tzinfo=reg.BRT) and c["event_date"] == AGORA


def test_data_do_evento_e_da_tela_e_a_programada_conta_da_criacao():
    """Levi, 06/10/2026: "você sumiu com data do evento, tem que ter data do evento" — como na ETM: editável, padrão
    agora. A programada continua contando da CRIAÇÃO, não do evento."""
    por_id = {str(a["id"]): a for a in CATALOGO}
    ok, _ = reg.responsaveis(PESSOAS, reg.nomes_configurados(CFG))
    _, c, erro = reg.montar(_corpo(evento="2026-10-05T14:30"), por_id, ok, AGORA, api.perf_os_nome)
    assert erro == "" and c["event_date"] == dt.datetime(2026, 10, 5, 14, 30, tzinfo=reg.BRT)
    assert c["prog_date"] == AGORA + dt.timedelta(days=7)
    assert reg.montar(_corpo(evento=""), por_id, ok, AGORA, api.perf_os_nome)[1]["event_date"] == AGORA
    erros = [reg.montar(_corpo(evento=e), por_id, ok, AGORA, api.perf_os_nome)[2] for e in ("ontem", "2026-10-08T10:00")]
    assert erros == ["Data do evento inválida.", "A data do evento não pode estar no futuro."]


def test_a_data_programada_nao_se_edita_o_servidor_calcula():
    """Levi, 06/10/2026: "data programada não deve ser possível editar!". A data que vier no pedido é ignorada, mesmo
    mal escrita ou fora do prazo: vale a hora da criação + 7 dias (Urgente: + 2)."""
    por_id = {str(a["id"]): a for a in CATALOGO}
    ok, _ = reg.responsaveis(PESSOAS, reg.nomes_configurados(CFG))
    for urgente, dias in ((False, 7), (True, 2)):
        for mandada in ("2030-01-01T08:00", "2026-10-01T08:00", "ontem"):
            _, c, erro = reg.montar(_corpo(urgente=urgente, programada=mandada), por_id, ok, AGORA, api.perf_os_nome)
            assert erro == "" and c["prog_date"] == AGORA + dt.timedelta(days=dias), (urgente, mandada)
            assert c["urgente"] is urgente


# ── a tela, pelo app do clone ──────────────────────────────────────────────────────────────────────────
@pytest.fixture
def cli(monkeypatch):
    """O Fracttal é FALSO em tudo: criar OS (uma por ativo e agrupada), ler as tarefas e subir anexo. E a rede fica
    proibida: um pedido que escapasse dos dublês derrubaria o teste, em vez de criar OS ou subir arquivo de verdade."""
    import requests

    def sem_rede(*a, **k):
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    feito, agrupada, subidos = {}, {}, []
    monkeypatch.setenv(reg.ENV_RESPONSAVEIS, CFG)
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(x) for x in CATALOGO])
    monkeypatch.setattr(api, "get_responsaveis", lambda *a, **k: [dict(p) for p in PESSOAS])
    monkeypatch.setattr(api, "get_request_types", lambda *a, **k: {})             # a tela do PCM, sem rede
    monkeypatch.setattr(api, "get_labels", lambda: [dict(e) for e in ETIQ])

    def classif(c1, c2):          # como o de verdade: nome vazio não acha nada
        out = {"id_task_type": 11, "tasks_types_description": c1} if c1 else {}
        out.update({"id_task_type_2": 22, "tasks_types_2_description": c2} if c2 else {})
        return out
    monkeypatch.setattr(api, "_classif_ids", classif)

    def criar(assets, description, task_type, subtasks, **kw):
        feito.update(assets=assets, description=description, task_type=task_type, subtasks=subtasks, **kw)
        return [{"code": a["code"], "ok": True, "os": {"wo_folio": 15000 + i, "id_work_order": 9000 + i}}
                for i, a in enumerate(assets)]
    monkeypatch.setattr(api, "create_work_orders_bulk", criar)

    def agrupar(assets, description, task_type, subtasks, **kw):
        agrupada.update(assets=assets, description=description, task_type=task_type, subtasks=subtasks, **kw)
        return {"ok": True, "n_tarefas": len(assets), "n_criadas": len(assets), "erros": [],
                "os": {"id_tasks": list(range(len(assets))), "id_work_order": 9100, "wo_folio": 15100}}
    monkeypatch.setattr(api, "create_work_orders_agrupada", agrupar)
    # a 1ª tarefa de cada OS é a que recebe o anexo (OS 9000 → tarefa 90001)
    monkeypatch.setattr(api, "_ids_tarefas_da_os", lambda idwo: [idwo * 10 + 1, idwo * 10 + 2])

    def subir(idwo, tid, dados, nome):
        subidos.append((idwo, tid, nome, dados))
        return {"ok": True, "value": ".ot/%s/%s" % (idwo, nome)}
    monkeypatch.setattr(api, "attach_imagem_os", subir)
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    c.feito, c.agrupada, c.subidos = feito, agrupada, subidos
    return c


def test_a_nova_solicitacao_tem_as_duas_portas(cli):
    pcm = cli.get("/os/solicitacao").get_data(as_text=True)
    assert '<a class="os-seg-btn on" role="tab" aria-selected="true" href="/os/solicitacao">PCM</a>' in pcm
    assert 'href="/os/solicitacao/engenharia">Engenharia</a>' in pcm
    r = cli.get("/os/solicitacao/engenharia")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert '<a class="os-seg-btn on" role="tab" aria-selected="true" href="/os/solicitacao/engenharia">Engenharia</a>' in h
    for txt in ("Cliente <i>*</i>", "Usina <i>*</i>", "Filtrar <small>", "Tipo de ativo <small>", 'id="cb_tipo" data-busca="1"',
                "Atividade a ser realizada (de forma direta)", "Descreva o problema <i>*</i>", 'id="ck_urg"', "Urgente"):
        assert txt in h, txt
    # a data do EVENTO se edita (padrão: agora); a PROGRAMADA só se vê (7 dias; o Urgente troca para 2)
    assert "Responsável e datas" in h and "Data do evento" in h
    evento = re.search(r'<input id="dt_evento" type="datetime-local" value="([^"]+)"', h).group(1)
    assert evento[:10] == dt.datetime.now(reg.BRT).strftime("%Y-%m-%d")
    assert "<input" not in re.search(r'id="dt_prog"[^>]*>', h).group(0) and h.count('type="datetime-local"') == 1
    mostrada = re.search(r'id="dt_prog"[^>]*>(\d{2}/\d{2}/\d{4} \d{2}:\d{2})<', h).group(1)
    agora = dt.datetime.now(reg.BRT)
    assert mostrada[:10] == (agora + dt.timedelta(days=7)).strftime("%d/%m/%Y")
    assert re.search(r'data-agora="%s' % agora.strftime("%Y-%m-%d"), h)


def test_ativos_e_responsaveis_da_tela(cli):
    j = cli.get("/os/api/solicitacao/engenharia/ativos", query_string={"usina": USINA}).get_json()
    assert [a["tipo_nome"] for a in j["ativos"]] == ["Inversor", "Nobreak", "Relé da Cabine"]
    assert {"tipo": "NBRK", "nome": "Nobreak"} in j["tipos"]
    r = cli.get("/os/api/solicitacao/engenharia/responsaveis").get_json()
    assert [p["name"] for p in r["pessoas"]] == ["Ana Teste Silva", "Bruno Souza"] and r["faltam"] == ["Zeca"]


def test_sem_a_lista_no_env_a_tela_avisa(cli, monkeypatch):
    monkeypatch.delenv(reg.ENV_RESPONSAVEIS)
    assert cli.get("/os/api/solicitacao/engenharia/responsaveis").get_json() == {"pessoas": [], "faltam": [], "configurado": False}
    r = cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo())
    assert r.status_code == 400 and r.get_json()["erro"] == "Escolha o responsável entre os nomes da Engenharia."


def _perto(data, esperada):
    return abs(data - esperada) < dt.timedelta(minutes=2)


def test_criar_sai_como_a_os_de_analise_com_a_etiqueta_da_engenharia(cli):
    # a programada mandada pela tela não vale: o servidor programa para 7 dias depois da criação; o evento vem da tela
    ontem = (dt.datetime.now(reg.BRT) - dt.timedelta(days=1)).replace(second=0, microsecond=0)
    r = cli.post("/os/api/solicitacao/engenharia/criar",
                 json=_corpo(programada="2030-01-01T08:00", evento=ontem.strftime("%Y-%m-%dT%H:%M")))
    assert r.status_code == 200
    f = cli.feito
    assert _perto(f["prog_date"], dt.datetime.now(reg.BRT) + dt.timedelta(days=7)) and f["event_date"] == ontem
    assert r.get_json()["mensagem"] == ("2 OS criada(s) para a Engenharia — Nº 15000, 15001 — programada(s) para %s."
                                        % f["prog_date"].strftime("%d/%m/%Y %H:%M"))
    # tipo Administrativa, só a Classificação 1 (Programada) e só as etiquetas REMOTO + ENGENHARIA — sem PERFORMANCE
    assert (f["task_type"], f["subtasks"], f["etiqueta_ids"]) == ("Administrativa", [], [901, 900])
    assert f["tipo"] == {"id_c1": 11, "desc_c1": "Programada"}
    assert (f["id_responsible"], f["responsible_name"], f["note"]) == (501, "Ana Teste Silva", "Desarma toda manhã.")
    assert f["por_ativo"]["TST-NBRK1"] == {"description": "[Nobreak 1] - Avaliar o religamento"}


def test_urgente_so_muda_a_data_as_etiquetas_sao_as_mesmas(cli):
    r = cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo(urgente=True, programada="2030-01-01T08:00"))
    assert r.status_code == 200
    assert _perto(cli.feito["prog_date"], dt.datetime.now(reg.BRT) + dt.timedelta(days=2))
    assert cli.feito["etiqueta_ids"] == [901, 900]                  # sem "Dar prioridade": só REMOTO e ENGENHARIA


def test_sem_a_etiqueta_no_fracttal_nenhuma_os_e_criada(cli, monkeypatch):
    monkeypatch.setattr(api, "get_labels", lambda: [dict(e) for e in ETIQ if e["id"] != 901])
    r = cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo())
    assert r.status_code == 400
    assert r.get_json()["erro"] == "Não achei no Fracttal a etiqueta Remoto. Nenhuma OS foi criada."
    assert cli.feito == {}


def test_responsavel_de_fora_da_lista_e_recusado(cli):
    r = cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo(responsavel={"id_personnel": 504}))
    assert r.status_code == 400 and "Engenharia" in r.get_json()["erro"]


# ── anexos (Levi, 08/10/2026: "Engenharia poder anexar arquivos") ───────────────────────────────────────────────────
PDF = b"%PDF-1.7\n%conteudo de mentira\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
XLSX = b"PK\x03\x04" + b"\x00" * 32            # xlsx, docx, ods e odt são zip por dentro
EXE = b"MZ\x90\x00\x03" + b"\x00" * 64          # o começo de um executável do Windows
CRIAR = "/os/api/solicitacao/engenharia/criar"


def test_anexo_aceita_pdf_imagem_planilha_e_documento():
    assert reg.tipos_aceitos() == ("PDF; imagem (JPG, JPEG, PNG, WEBP, GIF, BMP); planilha (XLSX, XLS, CSV, ODS); "
                                   "documento (DOCX, DOC, ODT, TXT)")
    ok, erro = reg.anexos([("relatório.pdf", PDF), ("foto.PNG", PNG), ("medições.xlsx", XLSX), ("dados.csv", b"a;b\n1;2\n"),
                           ("notas.txt", "texto com acentuação".encode("utf-16"))])
    assert erro == "" and [a["nome"] for a in ok] == ["relatório.pdf", "foto.PNG", "medições.xlsx", "dados.csv", "notas.txt"]
    assert ok[0]["bytes"] == PDF and ok[0]["tamanho"] == len(PDF)
    # o .xls/.doc antigo também vale quando é texto por dentro (sistema que exporta HTML com nome de .xls)
    assert reg.anexos([("export.xls", b"<html><table><tr><td>1</td></tr></table></html>")])[1] == ""
    assert reg.anexos([("foto.jpg", b"RIFF\x00\x00\x00\x00WEBPVP8 ")])[1] == ""      # .jpg que é WEBP: é imagem
    assert reg.anexos([]) == ([], "") and reg.anexos(None) == ([], "")


def test_anexo_recusado_diz_por_que_e_que_nada_foi_criado():
    erros = [reg.anexos(b)[1] for b in (
        [("instalar.exe", EXE)],                       # tipo fora da lista
        [("relatorio.pdf", EXE)],                      # executável com nome de PDF: o conteúdo não bate
        [("planilha.xlsx", b"nada de zip aqui")],
        [("export.xls", EXE)],
        [("vazio.pdf", b"")],
        [("grande.pdf", PDF + b"0" * (10 * reg.MB))],
        [("%d.pdf" % i, PDF) for i in range(6)],
        [("a.pdf", PDF + b"0" * (9 * reg.MB)), ("b.pdf", PDF + b"0" * (9 * reg.MB)), ("c.pdf", PDF + b"0" * (3 * reg.MB))],
    )]
    assert erros[0].startswith("“instalar.exe”: tipo de arquivo não aceito. Aceitos: PDF; imagem (JPG")
    assert erros[1] == "“relatorio.pdf” não é um PDF de verdade: o conteúdo não bate com a extensão. Nenhuma OS foi criada."
    assert erros[2].startswith("“planilha.xlsx” não é uma planilha de verdade")
    assert erros[3].startswith("“export.xls” não é uma planilha de verdade")
    assert erros[4] == "“vazio.pdf” veio vazio. Nenhuma OS foi criada."
    # arredonda para cima: 10 MB e 30 bytes não pode aparecer como "10,0 MB" recusado por passar de 10 MB
    assert erros[5] == "“grande.pdf” tem 10,1 MB — o limite é 10 MB por arquivo. Nenhuma OS foi criada."
    assert erros[6] == "São 6 anexos — o limite é 5 por criação. Nenhuma OS foi criada."
    assert erros[7] == "Os anexos somam 21,1 MB — o limite é 20 MB no total. Nenhuma OS foi criada."


def test_nome_do_anexo_fica_seguro_para_o_s3_e_nao_se_repete():
    """O nome vira a chave do arquivo no S3 da OS ('.ot/<OS>/<nome>'): nada de barra, '..', '#', '?', '%' ou '+'. E dois
    com o mesmo nome iriam para a mesma chave (o 2º apagaria o 1º): o 2º ganha ' (2)'."""
    assert reg.nome_seguro("C:\\fakepath\\relatório final.pdf") == "relatório final.pdf"
    assert reg.nome_seguro("../../etc/passwd") == "passwd"
    assert reg.nome_seguro("medição #3 (v2)?+100%.xlsx") == "medição _3 (v2)_100.xlsx"
    assert reg.nome_seguro("  .pdf ") == "pdf" and reg.nome_seguro("") == ""
    assert reg.nome_seguro("x" * 300 + ".docx") == "x" * reg.MAX_NOME + ".docx"
    ok, _ = reg.anexos([("foto.png", PNG), ("foto.png", PNG), ("FOTO.png", PNG), ("pasta/foto.png", PNG)])
    assert [a["nome"] for a in ok] == ["foto.png", "foto (2).png", "FOTO (3).png", "foto (4).png"]


def test_limite_de_envios_vale_quando_cada_anexo_sobe_para_cada_os():
    """Com uma OS por ativo, cada anexo sobe para cada OS: 2 pedidos ao Fracttal por envio, na cota da EMPRESA."""
    dois, _ = reg.anexos([("a.pdf", PDF + b"0" * (4 * reg.MB)), ("b.pdf", PDF + b"0" * (4 * reg.MB))])
    assert reg.erro_envios(dois, 1) == "" and reg.erro_envios(dois, 12) == ""           # 24 envios, ~96 MB
    assert reg.erro_envios(dois, 13) == (
        "Com uma OS por ativo, cada anexo sobe para cada OS: 13 OS × 2 anexo(s) = 26 envios (104,1 MB). O limite por "
        "criação é 30 envios e 100 MB. Escolha “Uma OS com todos os ativos” (os anexos sobem uma vez só) ou anexe menos "
        "arquivos. Nenhuma OS foi criada.")
    cinco, _ = reg.anexos([("%d.txt" % i, b"x") for i in range(5)])
    assert reg.erro_envios(cinco, 6) == "" and "= 35 envios" in reg.erro_envios(cinco, 7)
    assert reg.erro_envios([], 500) == ""


def test_anexar_sobe_cada_arquivo_em_cada_os_e_diz_o_que_falhou():
    subidos = []

    def subir(idwo, tid, dados, nome):
        if (idwo, nome) == (9001, "b.pdf"):
            raise api.FracttalError("upload S3 HTTP 403: AccessDenied")
        subidos.append((idwo, tid, nome))

    def tarefas(idwo):
        if idwo == 9002:
            raise api.SessionExpired("Sua sessão do Fracttal expirou")
        return [idwo * 10 + 1, idwo * 10 + 2]
    oss = [{"folio": 15000, "id_work_order": 9000}, {"folio": 15001, "id_work_order": 9001},
           {"folio": 15002, "id_work_order": 9002}]
    ok, _ = reg.anexos([("a.pdf", PDF), ("b.pdf", PDF)])
    res = reg.anexar(oss, ok, subir, tarefas)
    # na 1ª tarefa de cada OS; a falha de uma OS não impede as outras, e nenhum erro escapa (a OS já existe)
    assert sorted(subidos) == [(9000, 90001, "a.pdf"), (9000, 90001, "b.pdf"), (9001, 90011, "a.pdf")]
    assert [(r["ok"], [f for f, _e in r["falhas"]]) for r in res] == [(["15000", "15001"], ["15002"]),
                                                                       (["15000"], ["15001", "15002"])]
    out = reg.com_anexos({"ok": 3, "mensagem": "3 OS criada(s)"}, res, 2)
    assert out["anexos_falhas"] == 3 and out["ok"] == 3
    sessao = "não consegui ler a tarefa da OS (Sua sessão do Fracttal expirou)"
    assert out["mensagem"] == (
        "3 OS criada(s)\n\nAnexos:\n"
        "• a.pdf (1 KB): subiu nas OS 15000 e 15001; falhou na OS 15002 (%s).\n"
        "• b.pdf (1 KB): subiu na OS 15000; falhou na OS 15001 (upload S3 HTTP 403: AccessDenied); na OS 15002 (%s)."
        % (sessao, sessao))
    # OS que nasceu sem número não tem onde receber: entra na conta e na tela
    parcial = reg.com_anexos({"mensagem": "x"}, res, 2, sem_numero=1)
    assert parcial["mensagem"].endswith("• 1 OS sem número ficou sem os anexos.") and parcial["anexos_falhas"] == 5
    # sem OS para receber: a tela diz por quê
    assert reg.com_anexos({"mensagem": "Nenhuma OS criada."}, [], 2)["mensagem"].endswith(
        "Anexos: nenhum foi enviado — nenhuma OS foi criada.")
    assert reg.com_anexos({"mensagem": "x"}, [], 1, sem_numero=1)["mensagem"].endswith("— a OS não foi numerada.")
    assert reg.com_anexos({"mensagem": "x"}, [], 0) == {"mensagem": "x"}               # sem anexo, nada muda


def _multipart(corpo, arquivos):
    """O que a tela manda com anexo: o MESMO JSON no campo `payload` e cada arquivo em `anexos`."""
    return {"payload": json.dumps(corpo), "anexos": [(io.BytesIO(b), n) for n, b in arquivos]}


def test_criar_com_anexos_sobe_cada_um_em_cada_os(cli):
    r = cli.post(CRIAR, content_type="multipart/form-data",
                 data=_multipart(_corpo(), [("relatório.pdf", PDF), ("foto.png", PNG)]))
    assert r.status_code == 200, r.get_json()
    j = r.get_json()
    # as OS saem pelo mesmo pedido de antes; os anexos sobem DEPOIS, na 1ª tarefa de cada OS, com os bytes que vieram
    assert [a["code"] for a in cli.feito["assets"]] == ["TST-NBRK1", "TST-RELE1"] and cli.agrupada == {}
    assert sorted(cli.subidos) == [(9000, 90001, "foto.png", PNG), (9000, 90001, "relatório.pdf", PDF),
                                   (9001, 90011, "foto.png", PNG), (9001, 90011, "relatório.pdf", PDF)]
    assert (j["ok"], j["falhas"], j["anexos_falhas"]) == (2, 0, 0)
    assert j["mensagem"].endswith("\n\nAnexos:\n• relatório.pdf (1 KB): subiu nas OS 15000 e 15001.\n"
                                  "• foto.png (1 KB): subiu nas OS 15000 e 15001.")


def test_anexo_que_falha_no_fracttal_aparece_na_tela_e_a_os_continua(cli, monkeypatch):
    def subir(idwo, tid, dados, nome):
        if idwo == 9001:
            raise api.FracttalError("upload S3 HTTP 403: AccessDenied")
        cli.subidos.append((idwo, tid, nome, dados))
    monkeypatch.setattr(api, "attach_imagem_os", subir)
    r = cli.post(CRIAR, content_type="multipart/form-data", data=_multipart(_corpo(), [("relatorio.pdf", PDF)]))
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] == 2 and j["anexos_falhas"] == 1
    assert "• relatorio.pdf (1 KB): subiu na OS 15000; falhou na OS 15001 (upload S3 HTTP 403: AccessDenied)." in j["mensagem"]
    assert j["anexos"] == [{"nome": "relatorio.pdf", "tamanho": len(PDF), "ok": ["15000"],
                            "falhas": [{"os": "15001", "erro": "upload S3 HTTP 403: AccessDenied"}]}]


def test_os_sem_numero_nao_recebe_anexo_e_a_tela_diz(cli, monkeypatch):
    """Uma das OS ficou só como tarefa (não virou OS numerada): o anexo vai para as que têm número, e a tela conta."""
    monkeypatch.setattr(api, "create_work_orders_bulk", lambda assets, *a, **k: [
        {"code": "TST-NBRK1", "ok": True, "os": {"wo_folio": 15000, "id_work_order": 9000}},
        {"code": "TST-RELE1", "ok": True, "os": {"id_task": 77, "aviso": "tarefa criada, mas não a achei no kanban p/ virar WO."}}])
    r = cli.post(CRIAR, content_type="multipart/form-data", data=_multipart(_corpo(), [("relatorio.pdf", PDF)]))
    j = r.get_json()
    assert r.status_code == 200 and [(i, n) for i, _t, n, _d in cli.subidos] == [(9000, "relatorio.pdf")]
    assert j["mensagem"].endswith("Anexos:\n• relatorio.pdf (1 KB): subiu na OS 15000.\n• 1 OS sem número ficou sem os anexos.")
    assert j["anexos_falhas"] == 1 and j["avisos"] == ["tarefa criada, mas não a achei no kanban p/ virar WO."]


@pytest.mark.parametrize("arquivos", [[("instalar.exe", EXE)], [("relatorio.pdf", EXE)],
                                      [("%d.pdf" % i, PDF) for i in range(6)]], ids=["tipo", "conteudo", "quantidade"])
def test_anexo_recusado_nenhuma_os_e_criada(cli, arquivos):
    r = cli.post(CRIAR, content_type="multipart/form-data", data=_multipart(_corpo(), arquivos))
    assert r.status_code == 400 and r.get_json()["erro"].endswith("Nenhuma OS foi criada.")
    assert cli.feito == {} and cli.agrupada == {} and cli.subidos == []


def test_anexos_demais_para_uma_os_por_ativo_pedem_a_agrupada(cli, monkeypatch):
    monkeypatch.setattr(reg, "MAX_ENVIOS", 3)                   # 2 OS × 2 anexos = 4 envios
    dois = [("a.pdf", PDF), ("b.pdf", PDF)]
    r = cli.post(CRIAR, content_type="multipart/form-data", data=_multipart(_corpo(), dois))
    assert r.status_code == 400 and "“Uma OS com todos os ativos”" in r.get_json()["erro"] and cli.feito == {}
    # numa OS só, os anexos sobem uma vez
    r = cli.post(CRIAR, content_type="multipart/form-data", data=_multipart(_corpo(agrupar=True), dois))
    assert r.status_code == 200 and cli.feito == {} and len(cli.subidos) == 2


def test_envio_grande_demais_responde_json_e_nada_e_criado(cli, monkeypatch):
    monkeypatch.setattr(reg, "LIMITE_PEDIDO", reg.MB)
    r = cli.post(CRIAR, content_type="multipart/form-data",
                 data=_multipart(_corpo(), [("grande.pdf", PDF + b"0" * (2 * reg.MB))]))
    assert r.status_code == 413
    assert r.get_json() == {"erro": "O envio passou do limite do servidor (1 MB): anexe menos arquivos, ou arquivos "
                                    "menores. Nenhuma OS foi criada."}
    assert cli.feito == {} and cli.subidos == []


def test_a_rota_abre_o_limite_do_app_so_para_os_anexos(cli):
    """O app inteiro aceita 4 MB (as imagens do Tradicional); a Engenharia aceita até 20 MB de anexos num pedido."""
    assert cli.application.config["MAX_CONTENT_LENGTH"] == 4 * reg.MB < reg.LIMITE_PEDIDO
    nove = [("a.pdf", PDF + b"0" * (9 * reg.MB))]
    r = cli.post(CRIAR, content_type="multipart/form-data", data=_multipart(_corpo(ativos=[1]), nove))
    assert r.status_code == 200 and [len(d) for *_x, d in cli.subidos] == [len(PDF) + 9 * reg.MB]


def test_anexos_passam_pela_ponte_do_nexus(cli, app, logado):
    """No Nexus o clone roda dentro do processo, pela ponte (/os/*): o multipart chega inteiro ao clone, e o limite
    aberto pela rota vale lá dentro (o Nexus não lê o corpo; o dele é 25 MB)."""
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    sessao = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": JWT, "conta": {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}})
    logado.set_cookie("os_sessao", sessao, path="/os")
    nove = [("relatório.pdf", PDF + b"0" * (9 * reg.MB)), ("foto.png", PNG)]
    r = logado.post(CRIAR, content_type="multipart/form-data", data=_multipart(_corpo(agrupar=True), nove))
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    assert sorted((i, t, n, len(d)) for i, t, n, d in cli.subidos) == [
        (9100, 91001, "foto.png", len(PNG)), (9100, 91001, "relatório.pdf", len(PDF) + 9 * reg.MB)]
    assert r.get_json()["mensagem"].startswith("1 OS criada para a Engenharia — Nº 15100, com 2 atividade(s)")


# ── uma OS com todos os ativos (Levi, 08/10/2026: "Agrupar ativos em atividades por OS") ─────────────────────────────
def test_uma_os_com_todos_os_ativos_uma_atividade_por_ativo(cli):
    """O `create_work_orders_agrupada`, o mesmo do "Agrupar em UMA OS" do Tradicional, com as regras de sempre:
    Administrativa, só a Classificação 1 Programada, só REMOTO + ENGENHARIA e a data programada do servidor."""
    r = cli.post(CRIAR, json=_corpo(agrupar=True, programada="2030-01-01T08:00"))
    assert r.status_code == 200 and cli.feito == {}                   # nada pelo caminho de uma OS por ativo
    g = cli.agrupada
    assert [a["code"] for a in g["assets"]] == ["TST-NBRK1", "TST-RELE1"]
    assert (g["task_type"], g["subtasks"], g["etiqueta_ids"]) == ("Administrativa", [], [901, 900])
    assert g["tipo"] == {"id_c1": 11, "desc_c1": "Programada"} and "responsible_code" not in g
    assert (g["id_responsible"], g["responsible_name"], g["note"]) == (501, "Ana Teste Silva", "Desarma toda manhã.")
    # cada atividade com o seu '[Ativo] - Descrição'
    assert g["por_ativo"] == {"TST-NBRK1": {"description": "[Nobreak 1] - Avaliar o religamento"},
                              "TST-RELE1": {"description": "[Relé da Cabine 1] - Avaliar o religamento"}}
    assert _perto(g["prog_date"], dt.datetime.now(reg.BRT) + dt.timedelta(days=7))
    assert r.get_json()["mensagem"] == ("1 OS criada para a Engenharia — Nº 15100, com 2 atividade(s), uma por ativo — "
                                        "programada para %s." % g["prog_date"].strftime("%d/%m/%Y %H:%M"))


def test_agrupada_com_anexos_sobe_uma_vez_na_os(cli):
    r = cli.post(CRIAR, content_type="multipart/form-data",
                 data=_multipart(_corpo(agrupar=True), [("relatorio.pdf", PDF), ("medicoes.xlsx", XLSX)]))
    assert r.status_code == 200 and cli.feito == {}
    assert sorted((i, t, n) for i, t, n, _d in cli.subidos) == [(9100, 91001, "medicoes.xlsx"), (9100, 91001, "relatorio.pdf")]
    assert r.get_json()["mensagem"].endswith("Anexos:\n• relatorio.pdf (1 KB): subiu na OS 15100.\n"
                                             "• medicoes.xlsx (1 KB): subiu na OS 15100.")


def test_agrupar_com_um_ativo_so_vai_pelo_caminho_de_sempre(cli):
    r = cli.post(CRIAR, json=_corpo(ativos=[1], agrupar=True))
    assert r.status_code == 200 and cli.agrupada == {} and [a["code"] for a in cli.feito["assets"]] == ["TST-NBRK1"]


def test_agrupada_que_nao_fechou_diz_que_ficou_pendente(cli, monkeypatch):
    """O work_order_insert recusou: as atividades nasceram, pendentes. Responde 200 (a tela tira os ativos da seleção,
    ou um 2º clique criaria tudo de novo) e manda gerar a OS no Fracttal; os anexos não têm onde subir."""
    monkeypatch.setattr(api, "create_work_orders_agrupada", lambda *a, **k: {
        "ok": True, "n_tarefas": 2, "n_criadas": 2, "erros": [], "os": {"id_tasks": [1, 2]},
        "aviso": "tarefas criadas; a OS não fechou (RPC erro: recusado)."})
    r = cli.post(CRIAR, content_type="multipart/form-data",
                 data=_multipart(_corpo(agrupar=True), [("relatorio.pdf", PDF)]))
    j = r.get_json()
    assert r.status_code == 200 and (j["ok"], j["pendentes"], j["falhas"], j["anexos_falhas"]) == (0, 2, 1, 1)
    assert j["mensagem"].startswith("As 2 atividade(s) nasceram no Fracttal, mas a OS não foi numerada")
    assert j["mensagem"].endswith("Anexos: nenhum foi enviado — a OS não foi numerada.")
    assert j["avisos"] == ["tarefas criadas; a OS não fechou (RPC erro: recusado)."] and cli.subidos == []


def test_agrupada_diz_o_ativo_que_ficou_de_fora_e_a_que_falhou_inteira(cli, monkeypatch):
    monkeypatch.setattr(api, "create_work_orders_agrupada", lambda *a, **k: {
        "ok": True, "n_tarefas": 2, "n_criadas": 1, "erros": ["TST-RELE1: RPC erro: recusado"],
        "os": {"id_tasks": [1], "id_work_order": 9100, "wo_folio": 15100}})
    j = cli.post(CRIAR, json=_corpo(agrupar=True)).get_json()
    assert "Nº 15100, com 1 atividade(s)" in j["mensagem"] and j["falhas"] == 1
    assert j["mensagem"].endswith("1 ativo(s) ficaram de fora:\n• TST-RELE1 — Relé da Cabine: RPC erro: recusado")
    monkeypatch.setattr(api, "create_work_orders_agrupada", lambda *a, **k: {
        "ok": False, "erro": "Falha ao criar as tarefas: …", "n_tarefas": 2, "n_criadas": 0,
        "erros": ["TST-NBRK1: recusado", "TST-RELE1: recusado"]})
    r = cli.post(CRIAR, json=_corpo(agrupar=True))
    assert r.status_code == 400 and r.get_json()["mensagem"] == (
        "Nenhuma OS criada.\n• TST-NBRK1 — Nobreak: recusado\n• TST-RELE1 — Relé da Cabine: recusado")


def test_a_tela_tem_a_escolha_e_os_anexos(cli):
    h = cli.get("/os/solicitacao/engenharia").get_data(as_text=True)
    # a escolha, com o padrão no comportamento de antes (uma OS por ativo)
    assert '<input type="radio" name="eng_modo" value="por_ativo" checked>' in h
    assert '<input type="radio" name="eng_modo" value="agrupada">' in h
    for txt in ("<b>Uma OS por ativo</b>", "<b>Uma OS com todos os ativos</b>", "uma atividade por ativo, todas na mesma OS",
                'id="b_anexar"', ">Adicionar arquivos</button>", '<input id="anexo_in" type="file" multiple accept="%s" hidden>'
                % reg.ACEITAR, "Até 5 arquivos, 10 MB cada e 20 MB no total — cada anexo vai para cada OS criada.",
                "Tipos aceitos: PDF; imagem (JPG, JPEG, PNG, WEBP, GIF, BMP); planilha (XLSX, XLS, CSV, ODS); documento "
                "(DOCX, DOC, ODT, TXT).", 'data-anexo-max="5"', 'data-anexo-mb="10"', 'data-anexo-total-mb="20"',
                'data-anexo-envios="30"', 'data-anexo-envios-mb="100"'):
        assert txt in h, txt
    # o que a tela manda casa com o que o servidor lê: o JSON no campo `payload`, os arquivos em `anexos`, e o `agrupar`
    js = (WEB / "static" / "solic_eng.js").read_text(encoding="utf-8")
    for trecho in ("fd.append('payload', JSON.stringify(dados))", "fd.append('anexos', f, f.name)", "agrupar: agr",
                   "j.anexos_falhas > 0"):
        assert trecho in js, trecho
