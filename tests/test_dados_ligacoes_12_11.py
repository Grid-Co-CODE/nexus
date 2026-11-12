"""Os buracos das ligações medidos em 12/11/2026 (Levi: "Quero uma análise das relações de dados e se as bases estão
sendo lincadas da maneira correta"). O banco inteiro lido por GET: nos 19 fatos com IDs, nenhum ID órfão e nenhuma chave
repetida; os buracos estavam no que ainda não liga. Cada teste aqui é um deles, com o número medido naquele dia.
Nomes de usina fictícios.
"""
from datetime import date

from nexus.cadastro import ligacoes as L
from nexus.dados import calendario


def test_o_calendario_cobre_as_os_antigas_da_fama():
    """O `dim_data` começava em 01/01/2025, e 2.197 das 4.749 OS da FAMA (a mais antiga de 14/08/2023) tinham a data de
    criação fora do calendário: sem a linha do dia, a OS não entra em corte por semana, mês nem dia útil."""
    assert calendario.INICIO <= date(2023, 1, 1)
    ids = [linha[0] for linha in calendario.dias()]
    assert ids[0] == 20230101 and 20230814 in ids and ids[-1] == 20271231
    assert len(ids) == len(set(ids)) == (calendario.FIM - calendario.INICIO).days + 1


def _item(codigo, nome, fora=None, item=1):
    return {"fracttal_item_id": item, "codigo": codigo, "descricao": nome, "pai_item_id": None, "tipo_fracttal": "Local",
            "foto_em": "2026-11-06", "id_type_item": 1, "id_group_task": None, "fora_do_fracttal_desde": fora}


def test_a_usina_que_so_esta_na_foto_dos_ativos_entra_nas_ligacoes_com_o_codigo():
    """14 usinas de um cliente em operação estavam sem o nome do Fracttal no de-para, e a foto dos ativos do banco
    (renovada toda noite, igual nas duas máquinas) já tinha 2.362 ativos com o prefixo dele. A tela só conhecia as usinas
    das tarefas e da árvore que o motor do PCM guarda em arquivo. Entra a raiz da usina (o item cujo código é só o da
    usina e cujo nome é "Cliente - Usina - UF"), com o código, que é por onde ela liga ao Registro mestre."""
    foto = [_item("CLI-ALF100", "Cliente - Alfa 1 - MG"),
            _item("CLI-ALF100-INVR1.1", "Inversor 1.1", item=2),                  # equipamento: não é usina
            _item("CLI-ALF100-CABN1", "Cliente - Zeta 1 - SP", item=9),           # nem com nome de usina: o código decide
            _item("CLI-BET100", "Cliente - Beta  1 - PE", item=3),               # já é chave (só muda o espaço)
            _item("CLI-GAM100", "Cliente - Gama 1 - BA", fora=20261101, item=4),  # saiu do Fracttal
            _item("CLI", "Cliente", item=5), _item("DEL100", "Subestação", item=6),
            _item("CLI-EPS100", "Cliente - Épsilon 1 - PI", item=7), _item("CLI-EPS100", "Cliente - Épsilon 1 - PI", item=8)]
    novos = L.usinas_da_foto(foto, {"Cliente - Beta 1 - PE"})
    assert novos == [{"chave": "Cliente - Alfa 1 - MG", "nome": "Cliente - Alfa 1 - MG", "codigo": "CLI-ALF100",
                      "origem": "foto dos ativos do Fracttal"},
                     {"chave": "Cliente - Épsilon 1 - PI", "nome": "Cliente - Épsilon 1 - PI", "codigo": "CLI-EPS100",
                      "origem": "foto dos ativos do Fracttal"}]
    assert L.usinas_da_foto([], set()) == [] and L.usinas_da_foto(None, set()) == []


# ── o plant_id das fontes como sistema do de-para (a pendência 10 da camada de dados) ─────────────────────────────────
from test_cadastro_banco import cofre, srv  # noqa: E402,F401 — o cadastro de teste (a usina 1 e a 2)

from nexus.cadastro import banco as B  # noqa: E402


def _linha(fonte, plant, usina):
    return {"fonte": fonte, "plant_id": plant, "usina": usina}


def test_o_plant_id_liga_pela_chave_do_supervisorio_da_estrutura(srv):  # noqa: F811
    """As falhas de string e de tracker e os 163 mil eventos de tracker só tinham o `plant_id` da fonte e o nome que a
    fonte dá à usina; o de-para do cadastro não conhecia nenhum dos dois, e esses fatos só ligavam por nome (43,6% dos
    eventos de tracker). O nome da fonte é a chave do supervisório, que a estrutura das usinas já liga a UMA usina:
    medido em 12/11/2026, 295 dos 344 pares (fonte, plant_id) ligam por ela, e os 26 plant_id que aparecem em mais de
    uma fonte são a mesma usina com o mesmo nome. Sem a chave na estrutura, a linha fica à vista para ligar à mão."""
    estrutura = [{"usina_supervisorio": "Altair 1 (73)", "usina_id": 1, "excluido": "não"},
                 {"usina_supervisorio": "Mab  100", "usina_id": 2, "excluido": "não"},        # espaço duplo na aba
                 {"usina_supervisorio": "Velha (9)", "usina_id": 2, "excluido": "sim"}]       # chave desligada
    abas = [[_linha("Fonte A · API", 18749574.0, "Altair 1 (73)"), _linha("Fonte A · Banco", "18749574", "Altair 1 (73)"),
             _linha("Fonte B", "MAB100", "Mab 100"), _linha("Fonte B", "X-9", "Velha (9)"),
             _linha("Fonte B", "", "Sem id"), _linha("Fonte B", 77, "Fora da estrutura")],
            [_linha("Fonte A · API", 18749574, "Altair 1 (73)"),
             _linha("Fonte C", 500, "Altair 1 (73)"), _linha("Fonte C", 500, "Mab 100")]]      # um id, duas usinas
    itens = L.itens_plant(abas, estrutura)
    por = {i["chave"]: i for i in itens}
    assert list(por) == ["18749574", "500", "77", "MAB100", "X-9"]                             # um por plant_id, sem o vazio
    assert por["18749574"]["pela_estrutura"] == 1 and por["18749574"]["nome"] == "Altair 1 (73)"
    assert por["MAB100"]["pela_estrutura"] == 2
    assert por["77"]["pela_estrutura"] is None and por["X-9"]["pela_estrutura"] is None
    assert por["500"]["pela_estrutura"] is None, "o plant_id que a estrutura leva a duas usinas não liga"
    dp = B.de_para(srv, {L.SISTEMA_PLANT: itens})
    assert [1, L.SISTEMA_PLANT, "18749574", "chave do supervisório"] in dp
    assert [2, L.SISTEMA_PLANT, "MAB100", "chave do supervisório"] in dp
    assert [None, L.SISTEMA_PLANT, "77", B.SEM_PAR] in dp and [None, L.SISTEMA_PLANT, "500", B.SEM_PAR] in dp
    # a usina que a estrutura aponta e o Registro mestre já não tem não liga
    sumida = {L.SISTEMA_PLANT: [{"chave": "1", "nome": "Sumida", "pela_estrutura": 999}]}
    assert [None, L.SISTEMA_PLANT, "1", B.SEM_PAR] in B.de_para(srv, sumida)
    assert L.SISTEMA_PLANT in L.SEM_AUSENCIA                 # a plataforma não cobre a carteira inteira


# ── o número da OS, inteiro em todo fato ──────────────────────────────────────────────────────────────────────────────
def test_a_os_e_inteiro_em_todo_fato_e_o_que_tem_letra_fica_texto():
    """Medido no banco em 12/11/2026: a OS era texto em seis fatos e inteiro em quatro, e cruzar a OS entre setores pedia
    converter em cada leitura. Uma função só diz como todo fato a guarda."""
    import test_dados_camada as TC
    import test_dados_ronda_pt as TR

    from nexus.dados import fatos
    assert [fatos.os_do_fato(v) for v in ("17903", 17903, 17903.0, "17903.0", " 17903 ", "0017903")] == [17903] * 6
    assert [fatos.os_do_fato(v) for v in ("OS-12/B", "17903;17904", "", None, float("nan"))] == ["OS-12/B", "17903;17904",
                                                                                               None, None, None]
    fech = dict(zip(fatos.CAB_FECHAMENTO, fatos.fato_fechamento([TC._fech(OS="15400")], TC._lig())[0]))
    assert fech["os"] == 15400 and isinstance(fech["os"], int)
    pt = TR._fpt([TR._pt(OS="15001")])[0]
    assert pt["os"] == 15001 and isinstance(pt["os"], int)
