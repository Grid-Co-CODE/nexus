"""O dossiê da usina para a IA (12/11/2026). Levi: "Monte o dossiê da usina inteira, para a gente usar com a IA
futuramente, do jeito que uma IA possa ver facilmente"; "A ideia é a pessoa ir no prontuário da usina e perguntar [...]
por que a usina está com baixa performance [...] use tudo que tem no prontuário da usina, tá? Todas as informações de
todos os setores".

O que se prova: o texto sai do contexto do prontuário (o número do dossiê é o da tela), uma seção por assunto na mesma
ordem e com a fonte, o que falta está escrito (sem dado, sem leitura, o que ficou de fora), as pessoas vão pelo papel, e
nada do desenho da tela vai junto."""
import re
from datetime import datetime, timedelta, timezone

from test_campo_responsaveis import HOJE, tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)

from nexus.comando import dossie as DS

AGORA = datetime(2026, 11, 12, 22, 0, tzinfo=timezone(timedelta(hours=-3)))
NOMES = ("Ciclano Chefe", "Beltrano Supervisor", "Supervisora Campo", "Fulano Souza", "Técnico Silva")


def _ctx(logado):
    from flask import session

    from nexus.torres.comando.prontuario_dados import contexto
    with logado.application.test_request_context("/t/comando/usinas/1"):
        session.update(logado=True, admin=True)
        return contexto(1)


def test_uma_secao_por_assunto_na_mesma_ordem_e_com_a_fonte(tela, logado):
    d = DS.montar(_ctx(logado), AGORA)
    texto = d["texto"]
    assert texto.startswith("# Dossiê da usina Altair\n")
    assert "- Gerado em: 12/11/2026 às 22:00, horário de Brasília" in texto and f"(formato {DS.VERSAO})" in texto
    titulos = re.findall(r"^## (\d+)\. (.+)$", texto, flags=re.M)
    assert [int(n) for n, _t in titulos] == list(range(1, 15))
    esperados = [t for t, _f in DS.SECOES]
    esperados[esperados.index("Linha do tempo")] = "Linha do tempo dos últimos 30 dias"
    assert [t for _n, t in titulos] == esperados and d["secoes"] == [t for t, _f in DS.SECOES]
    # todos os setores do prontuário entram
    for assunto in ("Performance", "COS", "OS e manutenção", "Chamados de garantia", "Rondas e zeladoria", "Segurança",
                    "Insights do Nexus", "Demandas entre setores e conversa", "Composição da usina"):
        assert assunto in esperados
    # cada seção diz de que tela o dado veio, logo abaixo do título
    for bloco in re.split(r"^## \d+\. ", texto, flags=re.M)[1:]:
        assert bloco.split("\n")[2].startswith("Fonte: "), bloco[:80]
    assert "## Como ler" in texto and '"sem dado" quer dizer que a fonte não tem o valor: não é zero' in texto
    assert d["caracteres"] == len(texto) and d["tokens_estimados"] == round(len(texto) / 4) and d["palavras"] > 200


def test_o_numero_do_dossie_e_o_do_prontuario(tela, logado):
    ctx = _ctx(logado)
    p, texto = ctx["p"], DS.montar(ctx, AGORA)["texto"]
    html = logado.get("/t/comando/usinas/1").get_data(as_text=True)
    # o parecer e cada ponto de atenção, com a gravidade em palavras
    assert f"- Em uma frase: {p['parecer']['frase']}" in texto and "- Parecer: Pede ação agora (crítico)" in texto
    assert p["parecer"]["frase"] in html
    assert len(p["atencao"]) == 10 and f"O que pede atenção agora ({len(p['atencao'])})" in texto
    for i in p["atencao"]:
        assert i["titulo"] in texto
    assert "- [crítico] Meta do mês em 85%: abaixo de 90% (a Visão gerencial chama de Abaixo)" in texto
    # os medidores da Performance: o mesmo texto da tela, a gravidade e o que explica o número
    for m in p["painel"]["perf"]["medidores"]:
        assert m["txt"] in texto and m["txt"] in html
    assert "- Meta do mês: 85% (crítico); 850,0 de 1.000,0 MWh; mês anterior, out/26: 100%" in texto
    assert "- PR: 80,0% (em dia); previsto 79,0%" in texto and "- Disponibilidade: 85,0% (atenção); 3,6 h paradas" in texto
    assert "- O mês corrente é parcial: os números cobrem 10 de 31 dias." in texto
    assert "| novembro de 2026 (parcial) | 85% (crítico) | 850,0 de 1.000,0 MWh | 80,0% | 79,0% | 85,0% | 3,6 h paradas | 10 de 31 dias |" in texto
    # o dia a dia da geração, que é o que responde "por que a performance está baixa"
    assert "- Dia 2: geração 5,8 MWh (meta 40,0 MWh, 14%) · POA 1,40 kWh/m²" in texto
    assert "- Dia 3: geração sem dado · POA 5,00 kWh/m²" in texto and "geração — MWh" not in texto
    assert "- Inversor 1 (THPN-ALT100-INVR1): 4 falhas em 30 dias (crítico)" in texto
    # os outros setores
    assert "- OS de PARADA aberta agora: OS 13002; Corretiva Emergencial; Inversor 1; THPN-ALT100-INVR1; desde 02/11 08:00" in texto
    assert "| 16034 | Tracker 1 STI | STI | Estrutura Trackers | aberto | 26 dias | — |" in texto
    assert "| Tracker 1 STI | THPN-ALT100-ETKR1 | 0 | 0 | — | — | OS 16034, STI, aberto |" in texto
    assert "- Última ronda: há 1 dia; 11/11/2026; ronda longa pendente" in texto
    assert "| 11/11 | curta | 60 min | Atenção | — | — | 500 | incompleta |" in texto           # o veredito sem repetir a palavra
    assert "- Extintores: 2 na usina; vencidos: 1; a vencer: 0; sem conferir: 0; última conferência em 07/11/2026" in texto
    assert "  - PT-1; OS 700; Troca de string; esperando há 1 d 6 h; a tarefa está PARADA por ela" in texto
    assert "- [crítico] 1 extintor vencido\n  - regra R07: Extintor vencido" in texto and "  - ação sugerida: Programar a recarga" in texto
    assert "- Status: OPERAÇÃO" in texto and "- Mobilizada em: 10/2025" in texto


def test_o_que_falta_esta_escrito_e_nao_vira_zero(tela, logado):
    texto = DS.montar(_ctx(logado), AGORA)["texto"]
    assert "- Agora: sem leitura do COS (a fonte não respondeu ou a usina não está na fotografia). Não quer dizer normal." in texto
    assert "- OS abertas: sem leitura (as OS do Fracttal não chegaram ao banco). Não quer dizer zero." in texto
    assert "- Leitura semanal de sujidade e vegetação (zeladoria): sem dado." in texto
    fora = texto.split("## 14. O que ficou de fora", 1)[1]
    assert "não abriram quando o dossiê foi gerado" in fora and "- o COS (a coluna Agora)" in fora
    # sem nada (a fonte inteira fora), o dossiê ainda sai inteiro, dizendo o que não tem
    vazio = DS.montar({"x": {"usina": "Usina X", "insights": None}, "cu": {}, "p": {}}, AGORA)["texto"]
    assert len(re.findall(r"^## \d+\. ", vazio, flags=re.M)) == 14
    for frase in ("- Código: sem dado", "- Estado agora, pelo COS: sem dado", "- Meta, PR e disponibilidade do mês: sem dado.",
                  "- OS abertas: sem leitura", "- Última ronda: sem dado", "- Extintores: sem dado.",
                  "- Luvas de alta tensão: sem dado", "- Os Insights ainda estão sendo calculados: sem leitura agora.",
                  "- Ficha da usina no cadastro: sem dado.", "- Todas as fontes do prontuário abriram."):
        assert frase in vazio, frase
    # nenhuma seção em branco: depois da fonte vem sempre ao menos uma linha
    for bloco in re.split(r"^## \d+\. ", vazio, flags=re.M)[1:]:
        assert len([l for l in bloco.strip().splitlines() if l.strip()]) >= 3, bloco[:60]


def test_as_pessoas_vao_pelo_papel_e_o_nome_so_entra_quando_pedido(tela, logado):
    ctx = _ctx(logado)
    sem = DS.montar(ctx, AGORA)["texto"]
    for nome in NOMES:
        assert nome not in sem, nome
    assert "- Pessoas: citadas pelo papel, sem o nome" in sem
    assert "- Responsável O&M: definido" in sem and "- Supervisor de campo: definido" in sem
    assert "  - 07:00 [Ronda] Ronda curta (atenção): 60 min · incompleta (OS 500)" in sem        # a ronda sem o técnico
    assert "[PT] PT De acordo (em dia): Troca de string (OS 700)" in sem
    com = DS.montar(ctx, AGORA, com_pessoas=True)["texto"]
    assert "- Pessoas: citadas pelo nome" in com and "- Responsável O&M: Ciclano Chefe" in com
    assert "Ronda curta · Fulano Souza" in com and "Técnico Silva" in com
    # quem não tem responsável aparece como falta, não some
    ctx["x"]["responsavel"], ctx["cu"]["u"]["responsavel"] = "", "Sem responsável O&M"
    assert "- Responsável O&M: não definido" in DS.montar(ctx, AGORA)["texto"]


def test_nada_do_desenho_da_tela_vai_no_texto(tela, logado):
    texto = DS.montar(_ctx(logado), AGORA)["texto"]
    for desenho in ("viewbox", "largura", "cls", "ating_cls", "http", "/t/", "<", "None", "{", "}"):
        assert desenho not in texto, desenho


def test_a_pagina_e_o_texto_puro(tela, logado):
    r = logado.get("/t/comando/usinas/1/dossie")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Dossiê para a IA" in html and "data-ds-texto" in html and "data-ds-copiar" in html
    assert "# Dossiê da usina Altair" in html and "Tokens, estimativa" in html
    assert 'href="/t/comando/usinas/1/dossie.md?baixar=1"' in html and 'href="/t/comando/usinas/1"' in html
    md = logado.get("/t/comando/usinas/1/dossie.md")
    assert md.status_code == 200 and md.mimetype == "text/markdown" and md.headers["Cache-Control"] == "no-store"
    assert md.headers["Content-Disposition"] == 'inline; filename="dossie-THPN-ALT100.md"'
    assert md.get_data(as_text=True).startswith("# Dossiê da usina Altair\n")
    baixar = logado.get("/t/comando/usinas/1/dossie.md?baixar=1")
    assert baixar.headers["Content-Disposition"] == 'attachment; filename="dossie-THPN-ALT100.md"'
    assert logado.get("/t/comando/usinas/999/dossie").status_code == 404
    assert logado.get("/t/comando/usinas/999/dossie.md").status_code == 404


def test_o_atalho_no_prontuario_e_so_do_administrador(tela, logado):
    assert 'href="/t/comando/usinas/1/dossie"' in logado.get("/t/comando/usinas/1").get_data(as_text=True)
    with logado.session_transaction() as s:
        s["admin"] = False
    html = logado.get("/t/comando/usinas/1").get_data(as_text=True)
    assert "/dossie" not in html
    # o endereço segue abrindo para quem abre o prontuário: é o mesmo dado
    assert logado.get("/t/comando/usinas/1/dossie").status_code == 200
