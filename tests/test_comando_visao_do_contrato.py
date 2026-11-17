"""A prévia da visão do contrato (12/11/2026; no Comando desde a noite do mesmo dia): o mockup para a avaliação de Contratos e
dos setores, numa moldura, de todos e com o aviso de dados fictícios."""
from nexus.torres.comando import TORRE

MOCKUP = "/static/previa/visao-do-contrato.html"


def test_a_previa_abre_na_moldura_com_o_aviso(logado):
    html = logado.get("/t/comando/visao-do-contrato").get_data(as_text=True)
    assert "Prévia: visão do contrato" in html and "fictícios" in html
    assert '<iframe class="previa-moldura"' in html and MOCKUP in html
    assert TORRE.tela("visao-do-contrato").de_todos


def test_o_cabecalho_da_previa_e_uma_linha_so(logado):
    """Levi, 12/11/2026: "É quase a tela inteira, só de nada com nada": o título com o aviso na mesma linha; a pergunta
    da tela e a faixa de aviso saíram de cima da moldura."""
    html = logado.get("/t/comando/visao-do-contrato").get_data(as_text=True)
    cab = html.split('class="campo-nativa"', 1)[1].split("<iframe", 1)[0]
    assert "cn-pergunta" not in cab and "cn-aviso" not in cab and "Abrir em tela cheia" in cab


def test_o_mockup_esta_no_static_e_se_esconde_dentro_do_nexus(cliente):
    r = cliente.get(MOCKUP)
    pagina = r.get_data(as_text=True)
    assert r.status_code == 200 and "Visão do contrato" in pagina
    # dentro da moldura do Nexus o topo do mockup some (o do Nexus já está na tela)
    assert 'classList.add("embutido")' in pagina and "html.embutido .topo{display:none}" in pagina
    r.close()


def test_o_mockup_e_so_o_contrato_e_abre_nas_regras(cliente):
    """Levi, 12/11/2026: "pode tirar o prontuário [...] Não tem nada a ver" e "A gente está vendo o quê? Regras do
    contrato. Então, tem que mostrar regras do contrato. Aí tem um filtro para isso, um filtro para aquilo. Aí uma
    porrada de KPI. Aí tem outro filtro lá em cima de contrato. Aí tem um botão de nova regra. Se decida, enxugue"."""
    r = cliente.get(MOCKUP)
    pagina = r.get_data(as_text=True)
    r.close()
    for fora in ("vProntuario", "PRONT", "#/prontuario", "Prontuário da usina</a>", "EQUIP"):     # o prontuário saiu inteiro
        assert fora not in pagina
    assert cliente.get("/static/previa/contratos-e-prontuario.html").status_code == 404
    # as seis partes do contrato, abrindo nas Regras
    assert ('var ABAS = [["regras", "Regras"], ["calendario", "Calendário"], ["atendimento", "Atendimento"], '
            '["entregaveis", "Entregáveis"], ["metas", "Metas"], ["financeiro", "Financeiro"]]') in pagina
    assert 'estado.aba = ABAS.some(function (a) { return a[0] === aba; }) ? aba : "regras";' in pagina
    # um controle só nas Regras (Todas | Acordadas): saíram os filtros por categoria, a ficha de seis caixas e o
    # seletor de contrato separado (o nome do cliente é a troca); a regra nova é a última linha da tabela
    assert pagina.count("data-cat") == 0 and 'class="chip' not in pagina
    assert pagina.count('seg("Quais regras"') == 1 and "data-ficha" in pagina
    assert pagina.index('class="tab') < pagina.index("data-nova-regra><i")
    assert "btn--prim\" data-nova" not in pagina


def test_a_barra_de_rolagem_do_nexus_as_regras_recolhidas_e_o_atraso_sempre_a_vista(cliente):
    """Levi, 12/11/2026 (3ª rodada): "esse scroll branco aí é zoado [...] deixa no estilo Nexus. E todas essas regras aí,
    deixa recolhido [...] eu quero ver entregáveis, quero ver SLA, a pessoa vai clicando [...] seria bom se fosse separado
    para o cliente [...] seria bom para os gestores de contrato [...] recebendo as notificações [...] tem tantos em
    atraso, isso está sempre para ele [...] Sempre"."""
    from pathlib import Path
    r = cliente.get(MOCKUP)
    pagina = r.get_data(as_text=True)
    r.close()
    # a barra de rolagem do Nexus (a página numa moldura não herda a da casca): os mesmos tokens do nexus.css
    css = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "nexus.css").read_text(encoding="utf-8")
    assert "--rolagem:#243154; --rolagem-hover:#34426b" in css and "--rolagem:#243154;--rolagem-hover:#34426b" in pagina
    assert "html{color-scheme:dark;scrollbar-width:thin;scrollbar-color:var(--rolagem) transparent}" in pagina
    assert "::-webkit-scrollbar-thumb{background:var(--rolagem);border-radius:8px}" in pagina
    # as regras recolhidas por categoria: nenhuma aberta ao entrar, o clique abre; o filtro das acordadas abre todas
    assert "grupos: {}" in pagina and 'data-grupo="' in pagina
    assert "var aberto = estado.soAcordadas || !!estado.grupos[cat]" in pagina and "if (!aberto) return;" in pagina
    # o atraso no cabeçalho do contrato (antes das abas: aparece em toda aba), com o aviso ao gestor
    assert pagina.index('class="atraso" role="status"') < pagina.index('<nav class="abas" aria-label="Partes do contrato">')
    assert " em atraso</b>" in pagina and ", todo dia, até resolver" in pagina
    # cada cliente com o contrato dele: o nome troca o contrato (sem o aviso que desfazia a escolha)
    assert "CONTRATOS[estado.ct]" in pagina and "escolha(CONTRATOS.map(" in pagina and 't.value = "0"' not in pagina


def test_o_gestor_do_contrato_aparece_quando_o_contrato_tem_um(cliente):
    """Levi, 12/11/2026: "Caso tenha gestor do contrato, também quero que apareça". Na 1ª linha do cabeçalho, no aviso
    de atraso e no Atendimento por cliente; o contrato sem gestor não mostra o campo vazio."""
    r = cliente.get(MOCKUP)
    pagina = r.get_data(as_text=True)
    r.close()
    assert 'gestor: "Marina Alves"' in pagina and 'gestor: ""' in pagina             # um com, um sem
    # a 1ª linha (a que aparece para todo cliente, antes do corte do cliente sem dados) leva o gestor, se houver
    linha = pagina.split("var h = '<div class=\"ct-linha\">", 1)[1].split("if (estado.ct) {", 1)[0]
    assert "(c.gestor ? '<span class=\"ct-gestor\">" in linha and "<small>Gestor do contrato</small>' + esc(c.gestor)" in linha
    assert '(c.gestor ? "No sino de " + esc(c.gestor)' in pagina and "Contrato sem gestor: o aviso vai para o setor Contratos" in pagina
    assert "<th>Cliente</th><th>Gestor do contrato</th>" in pagina and "sem gestor</span>" in pagina
    assert "<dt>Gestora</dt>" not in pagina                                             # saiu da linha de fatos


def test_a_lista_do_nexus_o_tema_claro_e_a_linha_que_abre_o_contrato(cliente):
    """Levi, 17/11/2026, em Comando > Prévia: visão do contrato: "1 - ARRUME ESSA LISTA FEIA, DEIXE NO PADRÃO NEXUS",
    "2 - Não tá pegando tema claro, arrume" e "3 - As linhas de clientes devem ser clicáveis com um botão de voltar!"."""
    from pathlib import Path
    r = cliente.get(MOCKUP)
    pagina = r.get_data(as_text=True)
    r.close()
    # 1. a lista nativa do navegador saiu: a troca de contrato é a lista do Nexus, com busca e teclado
    assert "selCt" not in pagina and "ct-nome" not in pagina
    assert 'role="listbox"' in pagina and 'aria-haspopup="listbox"' in pagina and 'placeholder="Buscar cliente"' in pagina
    assert 'ev.key === "ArrowDown"' in pagina and 'ev.key === "Escape"' in pagina and 'ev.key === "Enter"' in pagina
    assert 'ops.unshift({i: -1, nome: "Todos os contratos"' in pagina
    # 2. o tema: o da casca antes da 1ª pintura e a troca ao vivo; em tela cheia, o cookie. Os tokens do claro são os do
    #    nexus.css, e nenhuma cor fixa ficou nos gráficos do exemplo
    cabeca = pagina.split("<style>", 1)[0]
    assert "window.parent.document.documentElement" in cabeca and 'attributeFilter: ["data-tema"]' in cabeca
    assert "nexus_tema=(claro|escuro)" in cabeca and 'localStorage.getItem("nexus.tema")' in cabeca
    assert 'html[data-tema="claro"]{color-scheme:light}' in pagina
    css = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "nexus.css").read_text(encoding="utf-8")
    for token in ("--fundo:#ffffff", "--superficie:#e9ecf1", "--tinta:#1f2937", "--verde-texto:#566610", "--critico:#a81f2c"):
        assert token in css and token in pagina
    script = pagina.split("<body>", 1)[1]
    assert 'fill="#' not in script and 'stroke="#' not in script and "rgba(255,255,255" not in script
    # 3. a linha do cliente abre o contrato; o contrato aberto tem o Voltar; o endereço leva o contrato (o Voltar do
    #    navegador também volta à lista)
    assert "'<tr data-ir=\"' + x.i + '\"><td><a href=\"' + rota(x.i)" in pagina
    assert 'e.target.closest("[data-ir]")) && !e.target.closest("a")' in pagina
    assert 'class="btn ct-voltar" href="#/"' in pagina and "Voltar para todos os contratos" in pagina
    assert 'return ct >= 0 ? "#/c/" + encodeURIComponent(chave(ct))' in pagina
