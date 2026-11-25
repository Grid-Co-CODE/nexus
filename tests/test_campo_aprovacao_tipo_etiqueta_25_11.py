"""Os filtros Tipo de tarefa e Etiqueta da Aprovação de OS, no padrão do Histórico de OS (25/11/2026).

O Otávio (supervisão), repassado pelo Levi: "seria possível aplicar alguns filtros no painel lá das OS. Tipo por
Handouver, MPA/MPS [...] e também de quem solicitou, por exemplo: Performance, COS etc ---> Para esse sei que o pessoal
usa uma etiqueta". O Levi: "adicionar filtros em aprovação de OS no estilo histórico de os do os creator web, com o mesmo
estilo e funcionalidade". Os dois são listas de marcar (`<select multiple>`, `?tipo=` e `?etiqueta=` repetidos): a OS
entra se alguma tarefa dela tem um dos tipos marcados, ou uma das etiquetas. O tipo é o `tasks_log_task_type_main` e a
etiqueta o `labels` das linhas do Fracttal que a fila já guarda (nenhum pedido novo ao Fracttal). A barra passa do
cartão suspenso (`campo-filtros.js`) ao componente do Histórico (`filtros-os.js`).

A fila dos testes (test_campo_aprovacao_responsavel.py): 15002, 15088, 15102 e 17001 na Usina A; 16001 na Usina C."""
import re

from test_campo_aprovacao_responsavel import _folios, fila_resp, quadro  # noqa: F401  (fixtures)
from test_campo_aprovacao_supervisor import fila  # noqa: F401  (fixture)

TIPO = {"15088": "Handover", "15102": "MPA - Manutenção Preventiva Anual",
        "16001": "MPS - Manutenção Preventiva Semestral"}
ETIQUETAS = {"15088": [{"description": "COS"}], "15102": ["ENGENHARIA"], "16001": [{"description": "COS"}]}


def _form(html):
    m = re.search(r'<form[^>]*data-apq-filtros.*?</form>', html, re.S)
    return m.group(0) if m else ""


def _marcar(fila_resp):  # noqa: F811
    for w in fila_resp.linhas:
        folio = str(w["wo_folio"])
        if folio in TIPO:
            w["tasks_log_task_type_main"] = TIPO[folio]
        if folio in ETIQUETAS:
            w["labels"] = ETIQUETAS[folio]


def test_o_tipo_de_tarefa_filtra_e_marca_mais_de_um(quadro, fila_resp, logado):  # noqa: F811
    _marcar(fila_resp)
    html = logado.get("/t/campo/aprovacao?responsavel=*&tipo=Handover").get_data(as_text=True)
    assert _folios(html) == ["15088"]
    f = _form(html)
    assert re.search(r'<select[^>]*name="tipo"[^>]*multiple', f)
    # as opções são os tipos da fila inteira, em ordem; o marcado vem marcado
    opcoes = re.findall(r'<option value="([^"]*)"( selected)?>', f.split('name="tipo"', 1)[1].split("</select>", 1)[0])
    assert opcoes == [("Handover", " selected"), ("MPA - Manutenção Preventiva Anual", ""),
                      ("MPS - Manutenção Preventiva Semestral", ""), ("Religamento Remoto", "")]
    dois = logado.get("/t/campo/aprovacao?responsavel=*&tipo=Handover&tipo=MPA+-+Manuten%C3%A7%C3%A3o+Preventiva+Anual")
    assert sorted(_folios(dois.get_data(as_text=True))) == ["15088", "15102"]
    # sem acento e sem caixa também casa
    assert _folios(logado.get("/t/campo/aprovacao?responsavel=*&tipo=handover").get_data(as_text=True)) == ["15088"]


def test_a_etiqueta_de_quem_pediu(quadro, fila_resp, logado):  # noqa: F811
    _marcar(fila_resp)
    html = logado.get("/t/campo/aprovacao?responsavel=*&etiqueta=COS").get_data(as_text=True)
    assert sorted(_folios(html)) == ["15088", "16001"]
    f = _form(html)
    assert re.search(r'<select[^>]*name="etiqueta"[^>]*multiple', f)
    assert '<option value="COS" selected>COS</option>' in f and '<option value="ENGENHARIA">ENGENHARIA</option>' in f
    junto = logado.get("/t/campo/aprovacao?responsavel=*&etiqueta=ENGENHARIA&tipo=Handover").get_data(as_text=True)
    assert _folios(junto) == []                         # os filtros valem juntos
    duas = logado.get("/t/campo/aprovacao?responsavel=*&etiqueta=ENGENHARIA&etiqueta=COS&usina=1").get_data(as_text=True)
    assert sorted(_folios(duas)) == ["15088", "15102"]


def test_a_barra_e_a_do_historico_de_os_e_o_csv_leva_os_marcados(quadro, fila_resp, logado):  # noqa: F811
    _marcar(fila_resp)
    html = logado.get("/t/campo/aprovacao?responsavel=*&tipo=Handover&tipo=Religamento+Remoto").get_data(as_text=True)
    f = _form(html)
    assert "data-fo" in f.split(">", 1)[0] and "data-fs" not in f.split(">", 1)[0]
    assert "filtros-os.js" in html and "campo-filtros.js" not in html
    # o Exportar CSV leva os dois tipos marcados (o endereço guardava só o primeiro valor de cada filtro)
    csv_href = re.search(r'href="([^"]*)"[^>]*data-apq-csv', f).group(1)
    assert "tipo=Handover" in csv_href and "tipo=Religamento+Remoto" in csv_href
    csv = logado.get("/t/campo/aprovacao?responsavel=*&tipo=Handover&csv=1").get_data(as_text=True)
    linhas = [x for x in csv.splitlines()[1:] if x.strip()]
    assert len(linhas) == 1 and linhas[0].startswith("15088;")
    # a rota dos cartões (o Ver mais e a busca) recorta igual
    j = logado.get("/t/campo/aprovacao/cartoes?responsavel=*&tipo=Handover").get_json()
    assert "15088" in str(j) and "15102" not in str(j) and "16001" not in str(j)


def _preventivas(fila_resp):  # noqa: F811
    """15102 e 16001 viram Preventiva, com o plano no nome da tarefa (como no Fracttal: o tipo é "Preventiva" e o MPA, o
    MPS, o MPM... vêm no nome); 15002 tem "Limpar" no nome (o "mpa" no meio da palavra)."""
    _marcar(fila_resp)
    for w in fila_resp.linhas:
        texto = {"15102": "MPA - Limpeza dos módulos", "16001": "MPS - Inspeção termográfica",
                 "15002": "Limpar o quadro de proteção"}.get(str(w["wo_folio"]))
        if texto:
            w["tasks_description"] = texto
        if str(w["wo_folio"]) in ("15102", "16001"):
            w["tasks_log_task_type_main"] = "Preventiva"


def test_mpa_e_mps_vem_do_nome_da_tarefa_da_preventiva(quadro, fila_resp, logado):  # noqa: F811
    """Levi, 25/11/2026, testando: "pesquisei por MPA e não filtrou nada". No Fracttal o tipo é "Preventiva" e o plano
    (MPM, MPT, MPQ, MPS, MPA) vem no nome da tarefa; a escolha dele: "No Tipo e na busca". O Tipo de tarefa ganha
    "Preventiva MPA", "Preventiva MPS"... (o código como palavra inteira no nome da tarefa da Preventiva)."""
    _preventivas(fila_resp)
    html = logado.get("/t/campo/aprovacao?responsavel=*&tipo=Preventiva+MPA").get_data(as_text=True)
    assert _folios(html) == ["15102"]
    f = _form(html)
    opcoes = re.findall(r'<option value="([^"]*)"', f.split('name="tipo"', 1)[1].split("</select>", 1)[0])
    assert "Preventiva MPA" in opcoes and "Preventiva MPS" in opcoes and "Preventiva" not in opcoes
    dois = logado.get("/t/campo/aprovacao?responsavel=*&tipo=Preventiva+MPA&tipo=Preventiva+MPS").get_data(as_text=True)
    assert sorted(_folios(dois)) == ["15102", "16001"]


def test_a_busca_acha_o_nome_da_tarefa_no_comeco_da_palavra(quadro, fila_resp, logado):  # noqa: F811
    _preventivas(fila_resp)
    # "MPA" acha a 15102 pelo nome da tarefa, e não a 15002 ("Limpar": o "mpa" no meio da palavra)
    assert _folios(logado.get("/t/campo/aprovacao?responsavel=*&q=MPA").get_data(as_text=True)) == ["15102"]
    assert _folios(logado.get("/t/campo/aprovacao?responsavel=*&q=termografica").get_data(as_text=True)) == ["16001"]
    # a rota dos cartões (a busca enquanto se digita) acha igual
    j = logado.get("/t/campo/aprovacao/cartoes?responsavel=*&q=mps").get_json()
    assert "16001" in str(j) and "15102" not in str(j)
    # o que já se achava segue: o número da OS no meio
    assert _folios(logado.get("/t/campo/aprovacao?responsavel=*&q=508").get_data(as_text=True)) == ["15088"]
