"""As fórmulas do BD_Operações portadas para o Nexus.

As expectativas foram tiradas à mão das fórmulas reais (29/09/2026), inclusive o que elas fazem de estranho:
o objetivo é que o Nexus calcule o MESMO que o Excel mostra, e a importação compara os dois valor a valor.
Onde o Nexus decide diferente de propósito (pessoa desligada não é o técnico da equipe), o teste diz.
"""
from nexus.cadastro.calculos import (ERRO, Contexto, cidade_estado_base, cidade_uf_endereco, cidade_uf_fallback,
                                     contato, localizacao, nome_padrao, proper, receita_contratual, receita_por_mwp)


# ── Nome Padrão: =LEFT(Nome;FIND(" ";Nome)-1)&" "&TRIM(RIGHT(SUBSTITUTE(Nome;" ";REPT(" ";255));255))

def test_nome_padrao_primeiro_e_ultimo():
    assert nome_padrao("Maria da Silva Souza") == "Maria Souza"
    assert nome_padrao("João Silva") == "João Silva"


def test_nome_padrao_sem_espaco_e_erro_como_no_excel():
    assert nome_padrao("Pedro") is ERRO


def test_nome_padrao_espaco_na_frente_segue_o_excel():
    # FIND acha o espaço na posição 1 e o LEFT devolve vazio.
    assert nome_padrao(" Ana Lima") == " Lima"


# ── LOCALIZAÇÃO: =CONCAT(CIDADE;",";UF;",";PAÍS)

def test_localizacao():
    assert localizacao("Brodowski", "SP", "Brasil") == "Brodowski,SP,Brasil"
    assert localizacao(None, "SP", "Brasil") == ",SP,Brasil"


# ── Cidade/UF (do endereço): a última sigla de UF da lista e o pedaço antes dela

def test_cidade_uf_do_endereco_pega_a_ultima_uf():
    assert cidade_uf_endereco("Rua A, 123, Centro, Brodowski, SP") == "Brodowski/SP"


def test_cidade_uf_do_endereco_barra_e_hifen_viram_virgula():
    assert cidade_uf_endereco("Av. Brasil 100 - Jardim - Ribeirão Preto/SP") == "Ribeirão Preto/SP"


def test_cidade_uf_do_endereco_tira_numero_da_frente_e_uf_em_minuscula_vale():
    # "14350-000 Brodowski, sp": o hífen quebra o CEP, o "000 Brodowski" perde o número, e o MATCH do Excel
    # não diferencia maiúscula (a UF sai como foi escrita).
    assert cidade_uf_endereco("Rua X, 12, 14350-000 Brodowski, sp") == "Brodowski/sp"


def test_cidade_uf_do_endereco_sem_uf_ou_uf_no_inicio_da_vazio():
    assert cidade_uf_endereco("Rua sem estado, 10") == ""
    assert cidade_uf_endereco("SP, Brodowski") == ""
    assert cidade_uf_endereco("   ") == ""
    assert cidade_uf_endereco(None) == ""


def test_cidade_uf_do_endereco_numero_sem_espaco_antes_da_uf_e_erro():
    # TEXTAFTER("123";" ";1) não acha espaço: #N/A na célula.
    assert cidade_uf_endereco("Rua A, 123, SP") is ERRO


# ── Cidade/UF (fallback): cidade digitada (ou o último pedaço de texto do endereço) + UF do cluster

def test_fallback_cidade_e_uf_do_cluster():
    assert cidade_uf_fallback("Ribeirão Preto", "SP Leste 01", None) == "Ribeirão Preto/SP"


def test_fallback_primeira_cidade_de_uma_lista():
    assert cidade_uf_fallback("Brodowski e Batatais", "SP Norte 02", None) == "Brodowski/SP"
    assert cidade_uf_fallback("Recife, PE", "XX Algo", None) == "Recife"


def test_fallback_sem_cidade_usa_o_ultimo_texto_do_endereco():
    assert cidade_uf_fallback(None, "CE Leste 01", "Rua A, 12, Centro, Fortaleza") == "Fortaleza/CE"
    # O CEP quebrado pelo hífen vira dois números e sai da conta; sobra a rua (é o que o Excel faz).
    assert cidade_uf_fallback(None, "CE Leste 01", "Rua A, 60000-000") == "Rua A/CE"
    assert cidade_uf_fallback(None, "", "CEP 14350, Brodowski") == "Brodowski"
    assert cidade_uf_fallback(None, None, None) == ""


def test_fallback_cidade_numerica_vira_texto():
    assert cidade_uf_fallback(123, "SP Leste 01", None) == "123/SP"


# ── Cidade/Estado (Base Equipe): PROPER(antes da barra) & "/" & UPPER(depois)

def test_cidade_estado_base():
    assert cidade_estado_base("são paulo/sp", "x") == "São Paulo/SP"
    assert cidade_estado_base("", "RIBEIRÃO PRETO/sp") == "Ribeirão Preto/SP"
    assert cidade_estado_base("", "") == ""
    assert cidade_estado_base("", "Recife") is ERRO
    assert cidade_estado_base(ERRO, "x/y") is ERRO


def test_proper_como_o_excel():
    assert proper("d'ávila") == "D'Ávila"
    assert proper("SÃO JOSÉ DOS CAMPOS") == "São José Dos Campos"


# ── contatos e receita

def test_contato_corporativo_primeiro():
    assert contato("11912345678", "11987654321") == "11912345678"
    assert contato(None, "11987654321") == "11987654321"
    assert contato(None, None) is None


def test_receita():
    assert receita_contratual(11745.0, 60) == 704700.0
    assert receita_contratual(None, 60) is None
    assert receita_contratual("N/A", 12) is None
    assert round(receita_por_mwp(3915.51, 3.0), 2) == 11746.53
    assert receita_por_mwp(None, 3.0) is None


# ── o que depende de outros cadastros

def _p(pid, ordem, equipe, cargo, status="Ativo", **extra):
    return {"id": pid, "ordem": ordem, "valores": dict(equipe=equipe, cargo=cargo, status=status, **extra)}


def _u(uid, ordem, equipe, responsavel):
    return {"id": uid, "ordem": ordem, "valores": {"equipe": equipe, "responsavel_om": responsavel}}


def test_tecnico_da_equipe_e_o_primeiro_ativo_do_cargo():
    # O PROCV do Excel pega o primeiro da planilha mesmo desligado; o Nexus pula o desligado, e a comparação
    # da importação diz por que os dois diferem.
    ctx = Contexto(usinas=[], equipes=[], pessoas=[
        _p("P-0001", 1, "E-001", "Técnico O&M", status="Desligado"),
        _p("P-0002", 2, "E-001", "Técnico O&M"),
        _p("P-0003", 3, "E-001", "Eletricista O&M"),
    ])
    assert ctx.pessoa_da_equipe("E-001", "Técnico O&M")["id"] == "P-0002"
    assert ctx.pessoa_da_equipe("E-001", "Mantenedor O&M") is None
    assert ctx.pessoa_da_equipe(None, "Técnico O&M") is None


def test_supervisor_e_o_responsavel_da_primeira_usina_da_equipe():
    ctx = Contexto(pessoas=[], equipes=[], usinas=[
        _u("UFV-9", 2, "E-001", "P-0100"),
        _u("UFV-3", 1, "E-001", "P-0200"),
        _u("UFV-5", 3, "E-002", "P-0300"),
    ])
    assert ctx.responsavel_da_equipe("E-001") == "P-0200"      # ordem 1 vem antes da 2
    assert ctx.responsavel_da_equipe("E-009") is None


def test_base_da_equipe_e_a_do_primeiro_ativo():
    # O Excel pegaria a desligada (Batatais/SP); o Nexus, a primeira ativa. A UF vem do nome da equipe.
    ctx = Contexto(usinas=[], equipes=[{"id": "E-001", "ordem": 1, "valores": {"nome": "SP Leste 01"}}], pessoas=[
        _p("P-0001", 1, "E-001", "Técnico O&M", status="Desligado", endereco="Rua A, 1, Centro, Batatais, SP"),
        _p("P-0002", 2, "E-001", "Eletricista O&M", cidade="Franca"),
    ])
    assert ctx.base_da_equipe("E-001") == "Franca/SP"


def test_base_da_equipe_com_erro_na_pessoa_fica_vazia():
    # A Base Equipe embrulha o PROCV em SEERRO: "Franca" sem barra dá #N/A na pessoa e vazio na usina.
    ctx = Contexto(usinas=[], equipes=[], pessoas=[_p("P-0002", 1, "E-001", "Técnico O&M", cidade="Franca")])
    assert ctx.base_da_equipe("E-001") == ""


def test_calculos_da_usina_seguem_a_equipe_e_a_sobreposicao():
    pessoas = [
        _p("P-0001", 1, "E-001", "Técnico O&M", telefone_corporativo="11912345678", nome="Ana Maria Lima"),
        _p("P-0002", 2, "E-001", "Eletricista O&M", telefone_pessoal="11987654321", nome="Bruno Costa"),
        _p("P-0003", 3, "E-002", "Técnico O&M", telefone_corporativo="21912345678", nome="Caio Dias"),
    ]
    usina = {"id": "UFV-1", "ordem": 1, "valores": {
        "equipe": "E-001", "cidade": "Brodowski", "uf": "SP", "pais": "Brasil",
        "potencia_contratual": 3.0, "preco_mwp": 3915.51, "prazo_meses": 60,
        "tecnico_om": "P-0003",                      # sobreposto na própria usina
    }}
    ctx = Contexto(usinas=[usina], pessoas=pessoas, equipes=[])
    c = ctx.calcular_usina(usina)
    assert c["localizacao"] == "Brodowski,SP,Brasil"
    assert c["tecnico_om"] == "P-0003"                # a sobreposição vence a equipe
    assert c["contato_tecnico"] == "21912345678"      # e o contato acompanha a pessoa escolhida
    assert c["eletricista_om"] == "P-0002"            # sem sobreposição, vem da equipe
    assert c["contato_eletricista"] == "11987654321"  # sem corporativo, o pessoal
    assert c["mantenedor_om"] is None
    assert round(c["receita_mensal"], 2) == 11746.53  # preço × potência (a fórmula de 70 usinas)
    assert round(c["receita_contratual"], 2) == 704791.8


def test_nao_se_aplica_vence_a_equipe_e_nao_tem_contato():
    pessoas = [_p("P-0001", 1, "E-001", "Mantenedor O&M", telefone_corporativo="11912345678")]
    usina = {"id": "UFV-1", "ordem": 1, "valores": {"equipe": "E-001", "mantenedor_om": "N/A"}}
    c = Contexto(usinas=[usina], pessoas=pessoas, equipes=[]).calcular_usina(usina)
    assert c["mantenedor_om"] == "N/A"
    assert c["contato_mantenedor"] is None


def test_receita_digitada_vence_o_preco_por_mwp():
    usina = {"id": "UFV-2", "ordem": 1, "valores": {"receita_mensal": 3915.0, "preco_mwp": 3915.51,
                                                     "potencia_contratual": 3.0, "prazo_meses": 12}}
    c = Contexto(usinas=[usina], pessoas=[], equipes=[]).calcular_usina(usina)
    assert c["receita_mensal"] == 3915.0
    assert c["receita_contratual"] == 46980.0


def test_calculos_da_pessoa():
    p = _p("P-0001", 1, "E-001", "Técnico O&M", nome="Maria da Silva Souza", cidade="Ribeirão Preto",
           endereco="Rua A, 12, Centro, Brodowski, SP")
    usina = _u("UFV-1", 1, "E-001", "P-0100")
    ctx = Contexto(usinas=[usina], pessoas=[p], equipes=[{"id": "E-001", "ordem": 1, "valores": {"nome": "SP Leste 01"}}])
    c = ctx.calcular_pessoa(p)
    assert c["nome_padrao"] == "Maria Souza"
    assert c["supervisor"] == "P-0100"
    assert c["cidade_uf_endereco"] == "Brodowski/SP"
    assert c["cidade_uf_fallback"] == "Ribeirão Preto/SP"      # a UF vem do NOME da equipe (SP Leste 01)
    assert c["cidade_estado_base"] == "Brodowski/SP"
