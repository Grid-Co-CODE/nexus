"""A 2ª rodada da Aprovação de OS em quadro por fatos (Levi, 05/11/2026): "1 - Engenharia entra no pré filtro / 2 - O que
tiver fora do pré filtro não é contabilizado / 3 - O visual está muito feio, pode adotar um visual de card de OS parecido
com Engenharia > Quadro da equipe porém com o botão aprovar / 4 - Esse texto: "fila de verificação do Fracttal, inteira
(...)" pode deixar no disclaimer da exclamação em amarelo / 5 - Sempre destacar o motivo de estar em dúvida ou não OK!
tem que estar bem visual e acessível / 6 - Ao invés desse underline fino abaixo do número da OS deixa o número da OS em
verde Grid e tire esse underline estranho!". O quadro falso é o do test_campo_aprovacao_responsavel (16001 Pronta; 15088
e 15002 Em dúvida; 15102 Não OK; 17001 religamento, fora do pré-filtro)."""
import re
from pathlib import Path

from test_campo_aprovacao_responsavel import _bloco, _cartao, _coluna, _folios, quadro  # noqa: F401  (quadro é fixture)
from test_campo_aprovacao_supervisor import _tarefa, fila  # noqa: F401  (fila é fixture)
from test_campo_aprovacao_responsavel import fila_resp  # noqa: F401  (fixture)

from nexus.campo import prefiltro

CSS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "campo.css"


def _html(logado):
    return logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)


def test_engenharia_entra_no_pre_filtro(quadro, logado):
    """1. A etiqueta ENGENHARIA não tira mais a OS do quadro (PERFORMANCE e CHAMADOS seguem fora)."""
    cruas = [{"tasks_log_task_type_main": "Corretiva", "description": "Troca", "labels": [{"description": "ENGENHARIA"}]}]
    assert prefiltro.fora_do_escopo(cruas, None) == ""
    duas = [{**cruas[0], "labels": [{"description": "ENGENHARIA"}, {"description": "PERFORMANCE"}]}]
    assert prefiltro.fora_do_escopo(duas, None) == "PERFORMANCE"
    quadro.linhas.append({**_tarefa(17004, 3, "SP 01"), "labels": [{"description": "Engenharia"}]})
    html = _html(logado)
    no_quadro = [f for k in ("pronta", "duvida", "nao_ok") for f in _folios(_coluna(html, k))]
    no_quadro += _folios(_bloco(html, "apq-conferindo"))
    assert "17004" in no_quadro and "17004" not in _folios(_bloco(html, "apq-fora"))


def test_o_que_esta_fora_do_pre_filtro_nao_conta(quadro, logado):
    """2. O total de OS esperando é o do quadro: a 17001 (religamento) não entra na conta; a lista de fora diz isso."""
    html = _html(logado)
    assert '<b class="gc-num">4</b> OS esperando aprovação' in html          # 15002, 15088, 15102 e 16001
    fora = _bloco(html, "apq-fora")
    assert _folios(fora) == ["17001"] and "não entram na conta" in fora


def test_o_cartao_no_modelo_do_quadro_da_equipe_com_o_aprovar(quadro, logado):
    """3. O cartão da OS do Quadro da equipe da Engenharia: o número e os dias no topo, o título (a tarefa), onde, e no pé
    o técnico com as iniciais e as tarefas; o Aprovar logo depois do score e dos avisos."""
    c = _cartao(_html(logado), "15088")
    cab = c[c.index('<header class="apq-c-cab">'):c.index("</header>")]
    assert 'class="apq-c-os"' in cab and 'class="apq-c-dias' in cab
    assert '<h3 class="apq-c-tit">' in c and 'class="apq-c-onde"' in c and "Usina A" in c and "Thopen" in c
    pe = c[c.index('class="apq-c-pe"'):c.index("</footer>")]
    assert 'class="cn-avatar apq-c-av"' in pe and "2 tarefas" in pe
    # 3ª volta (05/11/2026: "o botão aprovar pode ficar paralelo ao extremo direita do nome do técnico / Nota do app pode
    # ficar ao lado direito de tarefa (...) diminua o tamanho do botão para caber, nota também!")
    assert "data-apq-aprovar" in pe and pe.index("apq-c-quem") < pe.index("data-apq-aprovar")
    linha = c[c.index('<div class="apq-c-tarefa">'):c.index('class="apq-c-onde"')]
    assert linha.index('class="apq-c-tit"') < linha.index('class="apq-score"') and "Nota do App" in linha
    assert re.search(r"\.apq-c-pe \.apq-aprovar\{[^}]*margin-left:auto", CSS.read_text(encoding="utf-8"))
    assert c.index('class="apq-score') < c.index('class="apq-avisos"') < c.index("data-apq-aprovar")
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"\.apq-cartao\{[^}]*background:var\(--superficie-2\)", css)
    assert re.search(r'\.apq-cartao\[data-coluna="nao_ok"\]\{[^}]*box-shadow:inset 3px 0 0 var\(--critico-cheio\)', css)


def test_a_leitura_da_fila_vai_para_a_exclamacao(quadro, logado):
    """4. A caixa "fila de verificação do Fracttal, inteira (...) fila lida em (...) fotos conferidas de" sai do canto e
    vai para o "!" amarelo do título."""
    html = _html(logado)
    assert 'class="cn-frescor"' not in html
    caixa = html.split('<details class="gc-explica">', 1)[1].split("</details>", 1)[0]
    for t in ("Fila de verificação do Fracttal, inteira", "fila lida em", "fotos conferidas de"):
        assert t in caixa, t


def test_o_motivo_de_em_duvida_e_de_nao_ok_em_destaque(quadro, logado):
    """5. O motivo da coluna vem no topo do cartão, num bloco com a cor, o ícone e a palavra (não só a cor): o fato que
    pôs a OS ali, com a prova (as duas fotos da repetida)."""
    html = _html(logado)
    nao_ok = _cartao(html, "15102")
    m = re.search(r'<div class="apq-motivo" data-nivel="critico" role="note">(.*?)</div>\s*</div>', nao_ok, re.S)
    assert m and '<i class="ph ph-x-circle"' in m.group(1) and "Não OK" in m.group(1)
    assert "1 foto anexada 2 dias depois do fechamento no App" in m.group(1)
    assert nao_ok.index('class="apq-motivo"') < nao_ok.index('class="apq-c-tit"')     # antes de tudo, depois do topo
    duvida = _cartao(html, "15088")
    m = re.search(r'<div class="apq-motivo" data-nivel="alerta" role="note">(.*?)</div>\s*</div>', duvida, re.S)
    assert m and '<i class="ph ph-warning"' in m.group(1) and "Em dúvida" in m.group(1)
    assert "Foto repetida: p03 é a mesma imagem de p01" in m.group(1) and "p03 · Inversor" in m.group(1)
    assert "1 tarefa fechada fora do App" in _cartao(html, "15002").split('class="apq-c-tit"')[0]
    assert 'class="apq-motivo"' not in _cartao(html, "16001")                       # Pronta: nada a destacar
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r'\.apq-motivo\[data-nivel="critico"\]\{[^}]*background:var\(--critico-suave\)', css)
    assert re.search(r'\.apq-motivo\[data-nivel="alerta"\]\{[^}]*background:var\(--alerta-suave\)', css)


def test_o_numero_da_os_em_verde_sem_sublinhado(quadro, logado):
    """6. O número da OS no verde da Grid, sem o sublinhado fino."""
    css = CSS.read_text(encoding="utf-8")
    regra = re.search(r"\.apq-c-os\{([^}]*)\}", css).group(1)
    assert "color:var(--verde-texto)" in regra and "text-decoration:none" in regra
    assert "text-underline-offset" not in regra and "text-decoration-color" not in css.split(".apq-c-os", 1)[1][:400]
