"""Importação da "criticidade validada pela foto" para o livro das rondas avulsas (Levi, 08/10/2026:
`ferramentas/importar_avulsas_planilha.py`). Planilha SINTÉTICA e banco falso (tests/pg_falso.py): as usinas da
planilha, as pessoas e os textos daqui são inventados (o repositório é público).

O que se prova: casamento EXATO com o de-para do Fracttal (o que não casa sai na lista "fora", com a usina que casaria
pelo nome normalizado, sem ligar); a data mais recente entre as duas fotos; "Sem foto" = vazio; a pessoa achada no
cadastro só quando é UMA ficha com e-mail (senão para); a gravação pelo mesmo caminho da tela, com nome e comentário
só cifrados; a conferência linha a linha depois de gravar; as linhas que já estavam no livro ficam; rodar de novo não
duplica; e a validação por foto não vira ronda no fato."""
import json
from datetime import datetime, time, timedelta

import pytest
from test_campo_ronda_avulsa import _form, tecnico  # noqa: F401 (fixture)
from test_campo_visao import CHAVE, CHAVE_CADASTRO, DE_PARA, HOJE, _aba, _pessoas, banco  # noqa: F401

from ferramentas import importar_avulsas_planilha as IMP
from nexus.cadastro.cifra import Cofre
from nexus.campo import ronda_avulsa as RA
from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.dados import fato_ronda as FR
from nexus.dados import fatos

FR_SISTEMA = "Fracttal · Classificação 1"
VALIDADORA, EMAIL_V = "Pessoa Validadora Exemplo", "validadora@exemplo.test"
COMENTARIO = "Níveis validados pela foto em teste (planilha inventada); importados a pedido de teste"
CAB = ["Usina", "Sujidade correta", "Vegetação correta", "Data da última ronda", "Data das fotos de sujidade",
       "Data das fotos de vegetação", "Sujidade registrada (técnico)", "Resultado sujidade"]


def _d(n):
    """O dia de n dias atrás como a célula de data do Excel (datetime à meia-noite)."""
    return datetime.combine(HOJE - timedelta(days=n), time())


def _planilha(tmp_path, linhas, aba="Criticidade validada", cab=CAB):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = aba
    ws.append(["Criticidade validada pela foto - planilha inventada para teste"])
    ws.append(["Régua inventada"])
    ws.append([])
    ws.append(cab)
    for l in linhas:
        ws.append(l)
    p = tmp_path / "planilha_inventada.xlsx"
    wb.save(p)
    return p


LINHAS = [
    # as duas datas diferentes: vale a mais recente (3 dias atrás)
    ["Cliente Inventado - Usina Um - XX", 3, 4, _d(1), _d(3), _d(6), 5, "Nota acima da foto"],
    # "Sem foto" na sujidade = vazio; a vegetação entra
    ["Cliente Inventado - Usina Dois - XX", "Sem foto", 2, _d(10), _d(10), _d(10), "Sem foto", "-"],
    # acento a mais: não é o texto do de-para (fica fora, dizendo com qual usina casaria). Espaço repetido, esse sim,
    # não conta (ver test_espaco_repetido_casa_e_quem_esta_fora_do_cadastro_vai_so_cifrado)
    ["Cliente Inventado - Usina Três - XX", 1, 1, _d(2), _d(2), _d(2), 1, "Bate"],
    ["Cliente Inventado - Usina Sem De-Para - XX", 2, 2, _d(2), _d(2), _d(2), 2, "Bate"],
    # sem nenhum nível validado: não entra
    ["Cliente Inventado - Usina Um - XX", "Sem foto", "Sem foto", _d(1), _d(1), _d(1), "Sem foto", "-"],
    # só a data da vegetação; sujidade fora do domínio (3,5 não arredonda): vazio, a vegetação entra
    ["Cliente Inventado - Usina Tres - XX", 3.5, 5, _d(4), None, _d(4), 3, "Bate"],
    # data no futuro: recusada
    ["Cliente Inventado - Usina Dois - XX", 2, 2, _d(-2), _d(-2), _d(-2), 2, "Bate"],
    [None, None, None, None, None, None, None, None],                       # linha em branco: não conta
]


@pytest.fixture
def cadastro(banco):  # noqa: F811
    """O de-para do Fracttal para as usinas inventadas (1, 2 e 3 do cadastro de teste) e a validadora com e-mail, mais
    um nome que é de duas fichas."""
    _aba(banco, "cadastro_nexus", "de_para", DE_PARA + [
        {"usina_id": 1, "sistema": FR_SISTEMA, "chave_externa": "Cliente Inventado - Usina Um - XX"},
        {"usina_id": 2, "sistema": FR_SISTEMA, "chave_externa": "Cliente Inventado - Usina Dois - XX"},
        {"usina_id": 3, "sistema": FR_SISTEMA, "chave_externa": "Cliente Inventado - Usina Tres - XX"}])
    cofre = Cofre(CHAVE_CADASTRO)

    def ficha(pid, nome, email):
        return {"pessoa_id": pid, "vinculo": "Colaborador de campo", "cargo": "Analista", "equipe_id": None,
                "status": "Ativo", "supervisor_id": None, "excluido": "não",
                "sensivel_cifrado": cofre.cifrar(json.dumps({"nome": nome, "nome_padrao": nome, "email": email}),
                                                 f"banco/pessoas/{pid}")}
    _aba(banco, "cadastro_nexus", "pessoas", _pessoas() + [
        ficha(77, VALIDADORA, EMAIL_V), ficha(78, "Nome Repetido Exemplo", "r1@exemplo.test"),
        ficha(79, "Nome Repetido Exemplo", "r2@exemplo.test")])
    return banco


def _livro():
    return RA.ler_todas()


def test_ensaio_mede_e_nao_grava(tmp_path, cadastro):
    syncs = cadastro.syncs
    rel = IMP.executar(_planilha(tmp_path, LINHAS), "pessoa validadora exemplo", comentario=COMENTARIO)
    assert cadastro.syncs == syncs and _livro() == []                       # ensaio: nada gravado
    assert rel["modo"] == "ensaio" and rel["planilha"]["linhas"] == 7 and rel["planilha"]["cabecalho_na_linha"] == 4
    assert rel["usinas"] == {"linhas": 7, "casaram": 5, "entram": 3, "fora": 4, "nao_mobilizadas_entre_as_que_entram": 0}
    assert rel["pessoa"] == {"fichas_com_o_nome": 1, "pessoa_id": 77, "fora_do_cadastro": False, "tem_email": True}
    assert rel["gravaria"] == 3 and rel["pulariam_por_ja_estar_no_livro"] == 0 and rel["impede_gravar"] == []
    assert rel["datas"]["min"] == _d(10).date().isoformat() and rel["datas"]["max"] == _d(3).date().isoformat()
    assert rel["datas"]["as_duas_diferentes_vale_a_mais_recente"] == 1 and rel["datas"]["so_data_de_vegetacao"] == 1
    assert rel["niveis"]["com_sujidade"] == 1 and rel["niveis"]["com_vegetacao"] == 3
    assert rel["niveis"]["sem_foto_sujidade"] == 1 and rel["niveis"]["fora_do_dominio"] == 1
    fora = {f["linha"]: f for f in rel["fora"]}
    assert set(fora) == {7, 8, 9, 11}
    assert "texto exato" in fora[7]["motivo"] and fora[7]["casaria_sem_acento_e_espacos"][0]["usina_id"] == 3
    assert "texto exato" in fora[8]["motivo"] and "casaria_sem_acento_e_espacos" not in fora[8]
    assert "sem nível" in fora[9]["motivo"] and "futuro" in fora[11]["motivo"]
    # o relatório não traz o nome nem o e-mail de ninguém
    texto = json.dumps(rel, ensure_ascii=False, default=str).lower()
    assert "validadora" not in texto and "exemplo.test" not in texto


def test_grava_pelo_caminho_da_tela_confere_e_nao_duplica(tmp_path, cadastro, tecnico):  # noqa: F811
    assert tecnico.post("/t/campo/rondas/avulsa", data=_form()).status_code == 303     # alguém já lançou pela tela
    p = _planilha(tmp_path, LINHAS)
    rel = IMP.executar(p, VALIDADORA, comentario=COMENTARIO, gravar=True)
    assert rel["gravado"] == {"entraram": 3, "puladas_por_ja_estar_no_livro": 0}
    c = rel["conferencia"]
    assert c["problemas"] == [] and (c["enviadas"], c["batem"], c["linhas_antes"], c["no_livro_depois"]) == (3, 3, 1, 4)
    livro = _livro()
    assert livro[0]["origem"] == "avulsa"                                 # a da tela ficou, no mesmo lugar
    novas = livro[1:]
    assert [(x["usina_id"], x["data"], x["sujidade"], x["vegetacao"]) for x in novas] == [
        (1, _d(3).date().isoformat(), 3, 4), (2, _d(10).date().isoformat(), None, 2),
        (3, _d(4).date().isoformat(), None, 5)]
    cofre = Cofre(CHAVE_CADASTRO)
    for x in novas:
        assert x["origem"] == IMP.ORIGEM_VALIDACAO_FOTO == "validacao_foto"
        assert x["inicio"] == f"{x['data']}T00:00:00-03:00" and x["data_id"] == int(x["data"].replace("-", ""))
        assert (x["pessoa_id"], x["pessoa_hmac"]) == (77, codigo_da_pessoa(CHAVE, EMAIL_V))
        assert all(x[k] is None for k in ("tipo", "fim", "duracao_min", "vala", "sombreamento", "ipoa_sujo",
                                          "albedo_sujo", "ghi_sujo", "anula_id"))
        quem = json.loads(cofre.decifrar(x["quem_cifrado"], f"banco/rondas_avulsas/{x['id']}/quem"))
        assert quem == {"nome": VALIDADORA, "email": EMAIL_V}
        assert cofre.decifrar(x["comentario_cifrado"], f"banco/rondas_avulsas/{x['id']}/comentario") == COMENTARIO
    texto = json.dumps(livro, ensure_ascii=False).lower()
    assert "validadora" not in texto and EMAIL_V not in texto and "planilha inventada" not in texto
    # a validação por foto não é ronda realizada: o fato único de ronda só tem a avulsa da tela
    linhas, _ = FR.fato_ronda([], [], livro, fatos.Ligador([], [], [], {}), {})
    assert [l[FR.CAB_RONDA.index("origem")] for l in linhas] == ["avulsa"]
    # rodar de novo não duplica (mesma usina + data + pessoa + origem)
    de_novo = IMP.executar(p, VALIDADORA, comentario=COMENTARIO, gravar=True)
    assert de_novo["gravado"] == {"entraram": 0, "puladas_por_ja_estar_no_livro": 3} and len(_livro()) == 4
    assert IMP.executar(p, VALIDADORA)["pulariam_por_ja_estar_no_livro"] == 3


def test_conferencia_acusa_o_que_nao_bate(tmp_path, cadastro):
    """A conferência depois de gravar não é só a contagem: nível trocado, coluna que devia vir vazia, linha que já
    estava e sumiu, e e-mail em claro numa célula viram problema."""
    IMP.executar(_planilha(tmp_path, LINHAS), VALIDADORA, comentario=COMENTARIO, gravar=True)
    livro = _livro()
    depois = [dict(x) for x in livro]
    depois[0]["sujidade"] = 5
    depois[1]["vala"] = EMAIL_V
    r = IMP.conferir(livro, [{"id": "ja-estava"}], depois, Cofre(CHAVE_CADASTRO),
                     {"nome": VALIDADORA, "email": EMAIL_V}, COMENTARIO)
    assert r["batem"] == 1 and len(r["problemas"]) == 4
    assert "sujidade" in r["problemas"][0] and "vala deveria estar vazio" in r["problemas"][1]
    assert "sumiram" in r["problemas"][2] and "em claro" in r["problemas"][3]
    outro = IMP.conferir(livro, [], livro, Cofre(CHAVE_CADASTRO), {"nome": "Outra Pessoa", "email": "o@exemplo.test"},
                         COMENTARIO)
    assert outro["batem"] == 0 and all("outra pessoa" in p for p in outro["problemas"])


@pytest.mark.parametrize("nome, fichas", [("Nome Que Nao Existe", 0), ("Nome Repetido Exemplo", 2)])
def test_pessoa_que_nao_e_exatamente_uma_ficha_para(tmp_path, cadastro, nome, fichas):
    p = _planilha(tmp_path, LINHAS)
    rel = IMP.executar(p, nome)
    assert rel["pessoa"]["fichas_com_o_nome"] == fichas and rel["pessoa"]["pessoa_id"] is None
    assert rel["gravaria"] == 0 and rel["usinas"]["entram"] == 3 and "exatamente 1" in rel["impede_gravar"][0]
    with pytest.raises(IMP.Parada, match="Não gravei nada"):
        IMP.executar(p, nome, gravar=True)
    assert _livro() == []


def test_ficha_sem_email_e_chave_faltando_param(app, tmp_path, cadastro):
    p = _planilha(tmp_path, LINHAS)
    with pytest.raises(IMP.Parada, match="não tem e-mail"):
        IMP.executar(p, "Ciclano Chefe", gravar=True)                     # supervisor de teste, ficha sem e-mail
    app.config.pop("NEXUS_PESSOA_HMAC")
    with pytest.raises(IMP.Parada, match="NEXUS_PESSOA_HMAC"):
        IMP.executar(p, VALIDADORA, gravar=True)
    assert _livro() == []


def test_planilha_sem_as_colunas_ou_sem_a_aba_para(tmp_path, cadastro):
    with pytest.raises(IMP.Parada, match="cabeçalho"):
        IMP.executar(_planilha(tmp_path, LINHAS, cab=CAB[:2]), VALIDADORA)
    with pytest.raises(IMP.Parada, match="aba"):
        IMP.executar(_planilha(tmp_path, LINHAS), VALIDADORA, aba="Outra aba")


def test_nivel_e_data_da_planilha():
    assert [IMP.nivel(v) for v in (3, "4", 5.0, "Sem foto", " sem FOTO ", None, "", 3.5, 6, "alto")] == [
        (3, "ok"), (4, "ok"), (5, "ok"), (None, "sem_foto"), (None, "sem_foto"), (None, "vazio"), (None, "vazio"),
        (None, "fora"), (None, "fora"), (None, "fora")]
    assert IMP.data(datetime(2026, 9, 24)) == (datetime(2026, 9, 24).date(), "ok")
    assert IMP.data("24/09/2026")[0] == IMP.data("2026-09-24")[0] == datetime(2026, 9, 24).date()
    assert IMP.data("ontem") == (None, "ilegivel") and IMP.data(None) == (None, "vazio")


def test_espaco_repetido_casa_e_quem_esta_fora_do_cadastro_vai_so_cifrado(tmp_path, cadastro):
    """Levi, 08/10/2026: o de-para do Fracttal tinha "Belo Jardim  1" e "Saturnino 1  - RJ" com espaço duplo que a
    planilha não tem (as duas ficavam de fora) e quem validou não tem ficha no cadastro ("quem validou, fora do
    cadastro"). Espaço repetido não conta (acento e maiúscula continuam contando); a pessoa de fora vai só cifrada,
    sem pessoa_id, e o nome que casa com uma ficha não pode ser tratado como "de fora"."""
    p = _planilha(tmp_path, [["Cliente Inventado -  Usina Um - XX", 2, 3, _d(2), _d(2), _d(1), 2, "Bate"]])
    rel = IMP.executar(p, "Pessoa De Fora Exemplo", comentario=COMENTARIO, gravar=True, fora_do_cadastro=True)
    assert rel["usinas"]["entram"] == 1 and rel["fora"] == [] and rel["gravado"]["entraram"] == 1
    assert rel["pessoa"] == {"fichas_com_o_nome": 0, "pessoa_id": None, "fora_do_cadastro": True, "tem_email": False}
    assert rel["conferencia"]["problemas"] == []
    x = _livro()[-1]
    assert (x["usina_id"], x["data"], x["pessoa_id"], x["pessoa_hmac"]) == (1, _d(1).date().isoformat(), None, None)
    quem = json.loads(Cofre(CHAVE_CADASTRO).decifrar(x["quem_cifrado"], f"banco/rondas_avulsas/{x['id']}/quem"))
    assert quem == {"nome": "Pessoa De Fora Exemplo", "email": ""}
    assert "de fora" not in json.dumps(_livro(), ensure_ascii=False).lower()
    # o nome de uma ficha não passa como "de fora": a mesma pessoa não pode ir para o livro de dois jeitos
    with pytest.raises(IMP.Parada):
        IMP.executar(p, VALIDADORA, fora_do_cadastro=True)

