"""As observações da semana como regras na tela. O texto que o motor lê não muda de gramática: a tela lê e escreve as
mesmas linhas, e a linha que ninguém mexeu volta idêntica."""
import pytest

from nexus.pcm import insumos as I
from nexus.pcm import observacoes as O

TEXTO = "\n".join([
    "# dias fixos de atendimento",
    "@usina Santana do Ipanema = seg, sex",
    "@usina Itajá 1 e 2 = seg, qua, sex",
    "13480; não",
    "10369; qua e qui; Limpeza, Roçada; manhã; sem: QGBT, Trafo",
    "10400; quinta; ; tarde; só: Inversor",
    "@usina Caicó = qua, sabado",
    "10500; segunda-feira",
    "OS 123 qua",
    "texto livre qualquer",
    "",
])


def test_le_cada_tipo_como_o_motor():
    r = O.ler(TEXTO)
    assert [x["tipo"] for x in r] == ["comentario", "usina", "usina", "fora", "fixar", "fixar", "usina", "fixar",
                                      "nota", "nota", "vazia"][:len(r)]
    assert r[1]["usina"] == "Santana do Ipanema" and r[1]["dias"] == ["seg", "sex"]
    assert r[2]["usina"] == "Itajá 1 e 2"                     # o "e" do nome não é conectivo de dia
    assert r[3]["os"] == 13480
    f = r[4]
    assert f["os"] == 10369 and f["dias"] == ["qua", "qui"] and f["tarefas"] == ["Limpeza", "Roçada"]
    assert f["turno"] == "manhã" and f["sem"] == ["QGBT", "Trafo"] and not f["problema"]
    assert r[5]["dias"] == ["qui"] and r[5]["so"] == ["Inversor"] and r[5]["turno"] == "tarde"


def test_problemas_com_as_mensagens_do_motor():
    r = O.ler(TEXTO)
    assert "ignorado: sabado" in r[6]["problema"]               # sábado não é dia de programação
    assert "dia não reconhecido" in r[7]["problema"]             # "segunda-feira" o motor não entende
    assert "comece pelo número da OS" in r[8]["problema"]        # "OS 123" com prefixo
    assert r[9]["problema"] is None                              # texto livre passa calado, como no motor
    assert O.resumo(r)["problemas"] == 3


def test_regra_escrita_pela_tela_volta_igual_quando_lida():
    regras = [{"tipo": "usina", "usina": "Elias Fausto", "dias": ["sex", "seg"]},
              {"tipo": "fora", "os": 8799},
              {"tipo": "fixar", "os": 10369, "dias": ["qua"], "tarefas": [], "turno": "", "so": ["Cabine"], "sem": []},
              {"tipo": "fixar", "os": 10400, "dias": [], "tarefas": ["Limpeza"], "turno": "noite", "so": [], "sem": ["QGBT"]}]
    linhas = [O.escrever_regra(r) for r in regras]
    assert linhas[0] == "@usina Elias Fausto = seg, sex"
    assert linhas[1] == "8799; não"
    assert linhas[2] == "10369; qua; só: Cabine"
    assert linhas[3] == "10400; ; Limpeza; noite; sem: QGBT"
    lidas = [O.ler_linha(l) for l in linhas]
    assert not any(x["problema"] for x in lidas)
    assert lidas[2]["so"] == ["Cabine"] and lidas[3]["turno"] == "noite" and lidas[3]["sem"] == ["QGBT"]


FRACTTAL = ["Athon - Marabá 1 - PA", "Athon - Marabá 10 - PA", "Thopen - Araçoiaba da Serra 1- SP",
            "Thopen -  Timon 1 - MA", "Axis - Linhares 1 - ES", "Thopen - Linhares 1 - ES", "Sal Energia - Cascavel 1 (Sunpower) - CE",
            "1.Essencial", "Thopen", "Usina Teste - X - SP"]


def test_separa_cliente_nome_e_uf_do_nome_do_fracttal():
    assert O.separar_nome("Thopen -  Timon 1 - MA") == {"fracttal": "Thopen -  Timon 1 - MA", "cliente": "Thopen",
                                                        "nome": "Timon 1", "uf": "MA"}
    assert O.separar_nome("Thopen - Araçoiaba da Serra 1- SP")["nome"] == "Araçoiaba da Serra 1"   # sem espaço antes
    assert O.separar_nome("Sal Energia - Cascavel 1 (Sunpower) - CE")["nome"] == "Cascavel 1 (Sunpower)"
    for nao_e_usina in ("1.Essencial", "Thopen", "Usina Teste - X - SP"):
        assert O.separar_nome(nao_e_usina) is None


def test_cada_usina_do_fracttal_com_os_dias_do_motor():
    regras = O.ler("@usina Marabá 1 = seg, qua\n@usina Araçoiaba da Serra 1 = ter\n@usina Linhares 1 = sex\n")
    us = {u["fracttal"]: u for u in O.usinas_por_dia(regras, FRACTTAL)}
    assert len(us) == 7                                             # os não-usina ficam de fora
    assert us["Athon - Marabá 1 - PA"]["dias"] == ["seg", "qua"]
    assert us["Athon - Marabá 10 - PA"]["dias"] == list(O.DIAS)      # fronteira de palavra: 1 não é 10
    assert us["Athon - Marabá 10 - PA"]["regra"] is None
    assert us["Thopen - Araçoiaba da Serra 1- SP"]["dias"] == ["ter"]
    # "Linhares 1" casa com as duas Linhares: o motor aplica a mesma regra às duas
    assert us["Axis - Linhares 1 - ES"]["dias"] == us["Thopen - Linhares 1 - ES"]["dias"] == ["sex"]
    assert us["Axis - Linhares 1 - ES"]["divide"] == ["Linhares 1"]
    # regra nova para uma das Linhares usaria o nome inteiro, para não pegar a outra
    assert us["Axis - Linhares 1 - ES"]["nome_regra"] == "Axis - Linhares 1 - ES"
    assert us["Athon - Marabá 1 - PA"]["nome_regra"] == "Marabá 1"
    assert O.regras_sem_usina(regras, list(us.values())) == []


def test_regra_que_nao_casa_com_nenhuma_usina_fica_a_vista():
    regras = O.ler("@usina Usina Que Não Existe = seg\n@usina Marabá 1 = qua\n")
    us = O.usinas_por_dia(regras, FRACTTAL)
    assert O.regras_sem_usina(regras, us) == [0]


def test_primeira_regra_que_casa_vence_como_no_motor():
    regras = O.ler("@usina Marabá = seg\n@usina Marabá 1 = sex\n")
    us = {u["fracttal"]: u for u in O.usinas_por_dia(regras, FRACTTAL)}
    assert us["Athon - Marabá 1 - PA"]["dias"] == ["seg"] and us["Athon - Marabá 1 - PA"]["regra"] == 0


def test_le_a_lista_do_cache_mais_novo(tmp_path):
    import json, os, time
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / O.CACHE_ATIVOS).write_text(json.dumps({"1": ["Athon - Velha 1 - PA", "x"]}), encoding="utf-8")
    (b / O.CACHE_ATIVOS).write_text(json.dumps({"1": ["Athon - Nova 1 - PA", "x"], "2": ["", "y"]}), encoding="utf-8")
    os.utime(a / O.CACHE_ATIVOS, (time.time() - 3600, time.time() - 3600))
    nomes, quando = O.ler_usinas_fracttal([a, b, None])
    assert nomes == ["Athon - Nova 1 - PA"] and quando
    assert O.ler_usinas_fracttal([tmp_path / "nada"]) == ([], None)


def test_semana_anterior_vira_o_ano():
    assert O.semana_anterior("2026-W41") == "2026-W40"
    assert O.semana_anterior("2027-W01") == "2026-W53"


# ── tela ──────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def trab(app, tmp_path):
    app.config.update(NEXUS_PCM_TRABALHO=str(tmp_path / "trab"))
    return tmp_path / "trab"


def test_tela_mostra_as_regras_em_cartoes_e_etiquetas(logado, trab):
    I.salvar_observacoes(trab, "2026-W41", TEXTO)
    html = logado.get("/t/pcm/gerar?semana=2026-W41").get_data(as_text=True)
    assert 'data-usina="Santana do Ipanema"' in html
    assert 'class="obs-chip" data-os="13480"' in html
    assert "segunda-feira" in html and "dia não reconhecido" in html     # o problema aparece antes de gerar
    assert "3 linhas com problema" in html


def test_tela_lista_todas_as_usinas_do_fracttal_com_filtro_por_cliente(app, logado, trab, tmp_path):
    import json
    origem = tmp_path / "pcm"
    origem.mkdir()
    (origem / O.CACHE_ATIVOS).write_text(json.dumps({str(i): [n, "x"] for i, n in enumerate(FRACTTAL)}), encoding="utf-8")
    app.config.update(NEXUS_PCM_ORIGEM=str(origem))
    I.salvar_observacoes(trab, "2026-W41", "@usina Marabá 1 = seg, qua\n13480; não\n")
    html = logado.get("/t/pcm/gerar?semana=2026-W41").get_data(as_text=True)
    assert html.count('class="obs-usina obs-ufr') == 7                       # todas as usinas do Fracttal
    assert 'data-cliente="Athon"' in html and 'data-cliente="Sal Energia"' in html
    assert html.count('class="obs-cli"') == 1 + 4      # cards: Todos + Athon, Thopen, Axis, Sal Energia
    assert 'data-restritas-de="Athon">1<' in html      # Marabá 1 tem dia restrito
    assert "1</span> com dia restrito" in html
    # a regra continua no formulário, escondida, para o texto salvo sair igual
    assert 'data-usina="Marabá 1" data-dias="seg,qua"' in html


def test_copiar_da_semana_anterior(logado, trab):
    I.salvar_observacoes(trab, "2026-W40", "@usina Caicó = qua\n13480; não\n")
    resp = logado.post("/t/pcm/gerar/observacoes/copiar", data={"semana": "2026-W41"})
    assert resp.status_code == 303
    assert I.observacoes(trab, "2026-W41") == "@usina Caicó = qua\n13480; não\n"


def test_copiar_nao_apaga_o_que_ja_tem(logado, trab):
    I.salvar_observacoes(trab, "2026-W40", "@usina Caicó = qua\n")
    I.salvar_observacoes(trab, "2026-W41", "13480; não\n")
    resp = logado.post("/t/pcm/gerar/observacoes/copiar", data={"semana": "2026-W41"})
    assert resp.status_code == 409
    assert I.observacoes(trab, "2026-W41") == "13480; não\n"


# ── o padrão é a última programação (05/10/2026, Levi: "quero como padrão marcado o que já estava marcado na última
#    programação semanal, quero que apareça só o que está marcado, o que não estiver só vai aparecer por um botão
#    adicionar"). Herança de DADO, não só de tela: o motor recebe os mesmos dias que a tela mostra. ──

def test_semana_sem_observacao_herda_os_dias_por_usina_da_ultima_salva(trab):
    I.salvar_observacoes(trab, "2026-W39", "@usina Caicó = seg\n")
    I.salvar_observacoes(trab, "2026-W40", "# comentário\n@usina Marabá 1 = seg, qua\n13480; não\n10369; qua\n")
    texto, de = I.observacoes_efetivas(trab, "2026-W42")
    assert de == "2026-W40"                                    # a mais recente antes da semana
    assert texto == "@usina Marabá 1 = seg, qua\n"            # só os dias por usina: OS fora e dia fixo são da semana


def test_semana_salva_vale_o_que_foi_salvo_mesmo_vazio(trab):
    I.salvar_observacoes(trab, "2026-W40", "@usina Marabá 1 = seg, qua\n")
    I.salvar_observacoes(trab, "2026-W41", "13480; não\n")
    assert I.observacoes_efetivas(trab, "2026-W41") == ("13480; não\n", None)
    I.salvar_observacoes(trab, "2026-W42", "")                  # salvou vazia: é decisão, não herda
    assert I.observacoes_efetivas(trab, "2026-W42") == ("", None)
    # a última salva (W41) não tinha dia por usina: a W43 herda isso, nada
    assert I.observacoes_efetivas(trab, "2026-W43") == ("", None)


def test_semana_depois_nao_vale_como_anterior(trab):
    I.salvar_observacoes(trab, "2026-W43", "@usina Caicó = seg\n")
    assert I.observacoes_efetivas(trab, "2026-W42") == ("", None)
    assert I.observacoes_efetivas(trab, "2027-W01") == ("@usina Caicó = seg\n", "2026-W43")   # vira o ano


def test_tela_mostra_so_as_usinas_marcadas_e_herda_da_ultima(app, logado, trab, tmp_path):
    import json
    origem = tmp_path / "pcm"
    origem.mkdir()
    (origem / O.CACHE_ATIVOS).write_text(json.dumps({str(i): [n, "x"] for i, n in enumerate(FRACTTAL)}), encoding="utf-8")
    app.config.update(NEXUS_PCM_ORIGEM=str(origem))
    I.salvar_observacoes(trab, "2026-W41", "@usina Marabá 1 = seg, qua\n13480; não\n")
    html = logado.get("/t/pcm/gerar?semana=2026-W42").get_data(as_text=True)
    assert "herdados da 2026-W41" in html                       # a tela diz de onde veio o padrão
    assert 'data-usina="Marabá 1" data-dias="seg,qua"' in html  # a regra herdada está no formulário (salvar fixa)
    assert 'data-os="13480"' not in html                         # OS fora não passa para a semana seguinte
    cards = html.split('class="obs-usina obs-ufr')[1:]
    assert len(cards) == 7                                       # todas continuam na página, para o Adicionar
    marcadas = [c for c in cards if "obs-restrita" in c.split(">")[0]]
    escondidas = [c for c in cards if " hidden" in c.split(">")[0]]
    assert len(marcadas) == 1 and len(escondidas) == 6           # só a marcada aparece
    assert 'id="obs-add-usina-btn"' in html                      # as outras entram pelo botão
