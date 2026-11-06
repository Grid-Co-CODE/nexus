"""A 3ª rodada da Aprovação de OS (Levi, 05/11/2026): "1 - Esse check box branco no tema escuro é muito feio! Melhore / 2 -
O ativo já está aparecendo no título, não precisa repetir o nome do ativo abaixo, ao invés disso bote a quantidade de
tarefas / 3 - essa repetição do em dúvida na coluna e na OS não faz sentido, tire esse "EM DÚVIDA" da OS deixe só a
mensagem em laranja / 4 - (...) clica no número da OS ou no próprio card da OS e abre uma barra lateral detalhando qual é
a pendência, em que tarefa é, uma coisa profissional e detalhada! poupa informação inicial e vai aprofundando / 5 - Tem
730 OSs conferindo fotos, veja se travou algo para seguir" (a leitura: test_campo_prefiltro_fundo.py). O quadro falso é o
do test_campo_aprovacao_responsavel (16001 Pronta; 15088 e 15002 Em dúvida; 15102 Não OK; 17001 fora do pré-filtro)."""
import re
from pathlib import Path

from test_campo_aprovacao_responsavel import _cartao, fila_resp, quadro  # noqa: F401  (fixtures)
from test_campo_aprovacao_supervisor import fila  # noqa: F401  (fixture)

from nexus.campo import aprovacao

CSS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "campo.css"


def _html(logado):
    return logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)


def test_a_caixa_de_marcar_no_desenho_do_nexus():
    """1. A caixa de marcar nativa sai branca no tema escuro: a do Nexus tem o fundo da superfície, o fio e, marcada, o
    verde com o visto."""
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r'\.apq-marcar,\.apq-todas input\{[^}]*appearance:none[^}]*background:var\(--superficie\)', css)
    assert re.search(r'\.apq-marcar:checked,\.apq-todas input:checked\{[^}]*background:var\(--verde\)', css)


def test_a_linha_de_baixo_diz_quantas_tarefas_e_nao_repete_o_ativo(quadro, logado):
    """2. O ativo já vem no título da tarefa: a linha de baixo traz a quantidade de tarefas, a UFV e o cliente."""
    c = _cartao(_html(logado), "15088")
    onde = c[c.index('class="apq-c-onde"'):c.index("</p>", c.index('class="apq-c-onde"'))]
    assert "2 tarefas" in onde and "Usina A" in onde and "Inversor 1" not in onde
    assert "tarefas" not in c[c.index('class="apq-c-pe"'):c.index("</footer>")]


def test_o_motivo_sem_repetir_o_nome_da_coluna(quadro, logado):
    """3. A coluna já diz Em dúvida ou Não OK: o cartão traz só a mensagem, na cor da coluna, com o ícone."""
    html = _html(logado)
    for folio, nivel, texto in (("15088", "alerta", "Foto repetida: p03 é a mesma imagem de p01"),
                                ("15102", "critico", "1 foto anexada 2 dias depois do fechamento no App")):
        c = _cartao(html, folio)
        m = re.search(rf'<div class="apq-motivo" data-nivel="{nivel}" role="note">(.*?)</div>', c, re.S)
        assert m and texto in m.group(1) and "apq-motivo-t" not in c, folio
        assert "EM DÚVIDA" not in c.upper().split("APQ-MOTIVO", 1)[1][:600] if nivel == "alerta" else True
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r'\.apq-motivo\[data-nivel="alerta"\] li\{[^}]*color:var\(--alerta\)', css)
    assert re.search(r'\.apq-motivo\[data-nivel="critico"\] li\{[^}]*color:var\(--critico\)', css)


def test_o_cartao_e_o_numero_abrem_a_barra_lateral(quadro, logado):
    """4. O número da OS e o próprio cartão abrem a barra lateral (a das Rondas), que busca o detalhe da OS; o card do OS
    Creator abre de dentro dela."""
    html = _html(logado)
    c = _cartao(html, "15088")
    assert 'data-apq-detalhe="/t/campo/aprovacao/15088/detalhe"' in c.split(">")[0]
    assert '<aside class="rd-gaveta apq-gaveta" id="apq-gaveta"' in html
    js = next(s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "data-apq-aprovar" in s)
    assert "getAttribute('data-apq-detalhe')" in js and "NexusOsCard.abrir(" in js and "data-apq-card" in js
    assert "'.apq-cartao'" in js                                 # o clique no cartão (fora dos botões) abre a barra


def test_a_barra_detalha_a_pendencia_em_que_tarefa_e_com_a_prova(quadro, logado):
    """4. A barra: a OS, a coluna, o que pede o olho em cada fato (a tarefa, a foto, a hora), as tarefas da OS e os
    botões (Aprovar e abrir o card da OS)."""
    logado.get("/t/campo/aprovacao?responsavel=*")
    nao_ok = logado.get("/t/campo/aprovacao/15102/detalhe").get_data(as_text=True)
    assert "OS 15102" in nao_ok and "Não OK" in nao_ok
    assert "1 foto anexada 2 dias depois do fechamento no App" in nao_ok
    assert "Fechada no App em" in nao_ok and "anexada em" in nao_ok and "p01" in nao_ok
    assert 'data-apq-aprovar-de="15102"' in nao_ok and 'data-apq-card="15102"' in nao_ok
    duvida = logado.get("/t/campo/aprovacao/15088/detalhe").get_data(as_text=True)
    assert "Em dúvida" in duvida and "p03" in duvida and "p01" in duvida and "Inversor" in duvida
    tarefas = duvida[duvida.index('class="apq-g-tarefas"'):]
    for t in ("Tarefa 1 da OS 15088", "Tarefa 2 da OS 15088"):
        assert t in tarefas, t
    assert "Nota do registro 71%" in duvida
    fora = logado.get("/t/campo/aprovacao/15002/detalhe").get_data(as_text=True)
    assert "fechada fora do App" in fora and "Tarefa 1 da OS 15002" in fora
    assert "Fotos não lidas" in fora                               # a OS inteira fora do App não tem as fotos lidas


def test_a_barra_so_le_a_memoria_e_da_404_fora_da_fila(quadro, logado):
    logado.get("/t/campo/aprovacao?responsavel=*")
    pedidos = len(quadro.pedidos)
    assert logado.get("/t/campo/aprovacao/15088/detalhe").status_code == 200
    assert logado.get("/t/campo/aprovacao/99999/detalhe").status_code == 404
    assert len(quadro.pedidos) == pedidos                          # nada pedido ao Fracttal


def test_quem_e_do_app_sai_da_conta_pronta_sem_refazer(quadro, logado):
    """A leitura de fundo pergunta à conta pronta da fila quais tarefas de cada OS foram pelo App (sem refazer a conta)."""
    aprovacao.limpar()
    assert aprovacao.tarefas_do_app() is None                     # a conta ainda não saiu: a leitura lê como antes
    logado.get("/t/campo/aprovacao?responsavel=*")
    do_app = aprovacao.tarefas_do_app()
    assert do_app["15002"] == set() and do_app["15088"]


def test_a_barra_baixa_o_pdf_da_os(quadro, logado):
    """"Quero o botão de baixar o PDF da OS!" (05/11/2026): o PDF do OS Creator (o mesmo das OSs em verificação do Painel),
    com a sessão do Fracttal de quem clica; a sessão do Nexus vencida e o 401 têm a frase própria."""
    logado.get("/t/campo/aprovacao?responsavel=*")
    barra = logado.get("/t/campo/aprovacao/15088/detalhe").get_data(as_text=True)
    assert 'data-apq-pdf="15088"' in barra and "Baixar o PDF da OS" in barra
    html = _html(logado)
    js = next(s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "data-apq-aprovar" in s)
    pdf = js[js.index("closest('[data-apq-pdf]')"):]
    assert "nexusRota('/os/api/os/pdf')" in pdf and "r.ok && !r.redirected && r.j.url" in pdf
    assert "r.status === 401" in pdf and "SESSAO" in pdf
