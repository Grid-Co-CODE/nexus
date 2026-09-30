"""Serviço do cadastro: valida, cifra, sela, grava com versão e calcula o que era fórmula no Excel."""
from datetime import date

import pytest

from nexus.cadastro.armazem import ArmazemLocal
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.cadastro.servico import Carga, Servico
from nexus.cadastro.tipos import Legado


@pytest.fixture
def caminho(tmp_path):
    return tmp_path / "cadastro.json"


@pytest.fixture
def srv(caminho):
    s = Servico(ArmazemLocal(caminho), Cofre(gerar_chave()))
    s.aplicar_carga(Carga(
        entidades={
            "equipes": [
                {"id": "E-001", "ordem": 1, "valores": {"nome": "SP Leste 01"}},
                {"id": "E-002", "ordem": 2, "valores": {"nome": "CE Sul 01"}},
            ],
            "pessoas": [
                {"id": "P-0001", "ordem": 1, "valores": {
                    "nome": "Ana Maria Lima", "cargo": "Técnico O&M", "equipe": "E-001", "status": "Ativo",
                    "cpf": "52998224725", "email": "ana.lima@gridco.com.br", "telefone_corporativo": "11912345678",
                    "vinculo": "Colaborador de campo"}},
                {"id": "P-0002", "ordem": 2, "valores": {
                    "nome": "Bruno Costa", "cargo": "Técnico O&M", "equipe": "E-001", "status": "Ativo",
                    "vinculo": "Colaborador de campo"}},
                {"id": "P-0100", "ordem": 3, "valores": {"nome": "Carla Souza", "vinculo": "Supervisor"}},
            ],
            "usinas": [
                {"id": "1", "ordem": 1, "valores": {
                    "nome": "Brodowski", "status": "OPERAÇÃO", "equipe": "E-001", "responsavel_om": "P-0100",
                    "receita_mensal": 11745.0, "prazo_meses": 60, "cidade": "Brodowski", "uf": "SP",
                    "pais": "Brasil", "data_mobilizacao": Legado("Pendente")}},
                {"id": "2", "ordem": 2, "valores": {"nome": "Batatais", "status": "A MOBILIZAR"}},
            ],
        },
        listas={"status_usina": ["OPERAÇÃO", "A MOBILIZAR", "FINALIZADO"], "uf": ["SP", "CE"],
                "cargos": ["Técnico O&M", "Eletricista O&M", "Mantenedor O&M"],
                "status_contratacao": ["Ativo", "Desligado"],
                "vinculo": ["Colaborador de campo", "Supervisor", "Gestor de contrato"],
                "regiao": ["Sudeste", "SUDESTE", "Nordeste"]},
        origem={"arquivo": "teste.xlsx"},
    ), quem="importação")
    return s


def _form(srv, entidade, id_, **mudar):
    """O formulário como a tela o manda: todos os campos editáveis com o valor atual, e as mudanças."""
    r = srv.registro(entidade, id_)
    f = srv.formulario(r, revelar=True)
    f.update(mudar)
    return f, r.versao


# ── dado sensível nunca em claro no disco ──────────────────────────────────

def test_receita_e_cpf_nao_ficam_em_claro_no_arquivo(srv, caminho):
    bruto = caminho.read_text(encoding="utf-8")
    assert "11745" not in bruto                      # receita (usina, campo sensível)
    assert "52998224725" not in bruto                # CPF
    assert "Ana Maria Lima" not in bruto             # pessoa: o registro inteiro vai cifrado
    assert "ana.lima@gridco.com.br" not in bruto
    assert "Brodowski" in bruto                      # nome de usina não é sensível


def test_o_que_foi_cifrado_volta_no_tipo(srv):
    u = srv.registro("usinas", "1")
    assert u.valores["receita_mensal"] == 11745.0
    assert srv.registro("pessoas", "P-0001").valores["cpf"] == "52998224725"


# ── calculados ─────────────────────────────────────────────────────────────

def test_usina_calcula_o_que_era_formula(srv):
    u = srv.registro("usinas", "1")
    assert u.valor("receita_contratual") == 704700.0
    assert u.valor("localizacao") == "Brodowski,SP,Brasil"
    assert u.valor("tecnico_om") == "P-0001"                 # 1º técnico ativo da equipe
    assert u.valor("contato_tecnico") == "11912345678"
    assert u.origem("tecnico_om") == "automatico"


def test_sobrepor_e_voltar_ao_automatico(srv):
    f, v = _form(srv, "usinas", "1", tecnico_om="P-0002")
    assert srv.salvar("usinas", "1", f, v, quem="admin").ok
    u = srv.registro("usinas", "1")
    assert u.valor("tecnico_om") == "P-0002" and u.origem("tecnico_om") == "sobreposto"
    f, v = _form(srv, "usinas", "1", tecnico_om="")
    assert srv.salvar("usinas", "1", f, v, quem="admin").ok
    assert srv.registro("usinas", "1").valor("tecnico_om") == "P-0001"


def test_supervisor_da_pessoa_vem_das_usinas_da_equipe(srv):
    assert srv.registro("pessoas", "P-0001").valor("supervisor") == "P-0100"


# ── validação ──────────────────────────────────────────────────────────────

def test_cpf_errado_nao_grava(srv):
    f, v = _form(srv, "pessoas", "P-0001", cpf="529.982.247-24")
    res = srv.salvar("pessoas", "P-0001", f, v, quem="admin")
    assert not res.ok and "cpf" in res.erros
    assert srv.registro("pessoas", "P-0001").valores["cpf"] == "52998224725"


def test_valor_fora_da_lista_nao_grava(srv):
    f, v = _form(srv, "usinas", "1", status="EM OBRA")
    res = srv.salvar("usinas", "1", f, v, quem="admin")
    assert not res.ok and "status" in res.erros


def test_referencia_inexistente_nao_grava(srv):
    f, v = _form(srv, "usinas", "1", equipe="E-999")
    assert "equipe" in srv.salvar("usinas", "1", f, v, quem="admin").erros


def test_obrigatorio_nao_pode_ser_apagado(srv):
    f, v = _form(srv, "usinas", "1", nome="  ")
    assert "nome" in srv.salvar("usinas", "1", f, v, quem="admin").erros


def test_email_repetido_nao_grava(srv):
    f, v = _form(srv, "pessoas", "P-0002", email="ana.lima@gridco.com.br")
    assert "email" in srv.salvar("pessoas", "P-0002", f, v, quem="admin").erros


def test_valor_legado_intocado_continua_como_estava(srv):
    # "Pendente" na data de mobilização veio do Excel. Salvar OUTRO campo não pode apagar nem "corrigir" isso.
    f, v = _form(srv, "usinas", "1", cidade="Franca")
    res = srv.salvar("usinas", "1", f, v, quem="admin")
    assert res.ok and res.mudou == ["cidade"]
    assert srv.registro("usinas", "1").valores["data_mobilizacao"] == Legado("Pendente")


def test_legado_so_sai_quando_alguem_troca(srv):
    f, v = _form(srv, "usinas", "1", data_mobilizacao="2026-10-15")
    assert srv.salvar("usinas", "1", f, v, quem="admin").ok
    assert srv.registro("usinas", "1").valores["data_mobilizacao"] == date(2026, 10, 15)


# ── versão, conflito, histórico, selo ──────────────────────────────────────

def test_segunda_pessoa_a_salvar_recebe_conflito(srv):
    f, v = _form(srv, "usinas", "2", nome="Batatais 1")
    assert srv.salvar("usinas", "2", f, v, quem="admin").ok
    f2 = dict(f, nome="Batatais B")
    res = srv.salvar("usinas", "2", f2, v, quem="outro")        # versão velha
    assert res.conflito is not None and not res.ok
    assert srv.registro("usinas", "2").valores["nome"] == "Batatais 1"


def test_sem_mudanca_nao_grava_versao_nova(srv):
    f, v = _form(srv, "usinas", "2")
    assert srv.salvar("usinas", "2", f, v, quem="admin").ok
    assert srv.registro("usinas", "2").versao == v


def test_historico_diz_quem_e_o_que_mudou(srv):
    f, v = _form(srv, "usinas", "2", nome="Batatais 1")
    srv.salvar("usinas", "2", f, v, quem="admin")
    h = srv.historico("usinas", "2")
    assert h[0]["quem"] == "admin" and h[0]["campos"] == ["nome"]
    assert h[-1]["quem"] == "importação"


def test_linha_mexida_fora_do_nexus_perde_o_selo(srv, caminho):
    bruto = caminho.read_text(encoding="utf-8").replace('"Batatais"', '"Batatais X"')
    caminho.write_text(bruto, encoding="utf-8")
    u = srv.registro("usinas", "2")
    assert not u.selo_ok
    assert any(p["tipo"] == "selo" and p["id"] == "2" for p in srv.pendencias())


# ── criar ──────────────────────────────────────────────────────────────────

def test_criar_usina_gera_o_proximo_id(srv):
    res = srv.criar("usinas", {"nome": "Franca", "status": "A MOBILIZAR"}, quem="admin")
    assert res.ok and res.registro.id == "3"


def test_criar_sem_obrigatorio_recusa(srv):
    res = srv.criar("usinas", {"nome": "Franca"}, quem="admin")
    assert not res.ok and "status" in res.erros


def test_id_novo_e_numero_mesmo_com_id_antigo_de_prefixo(srv):
    # As equipes do fixture têm id no formato antigo (E-001). Registro novo já nasce no formato novo.
    res = srv.criar("equipes", {"nome": "PA Norte 09"}, quem="admin")
    assert res.ok and res.registro.id == "1"


def test_mesmo_nome_de_cliente_diferente_nao_e_repetido(caminho):
    s = Servico(ArmazemLocal(caminho), Cofre(gerar_chave()))
    s.aplicar_carga(Carga(entidades={
        "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente A"}},
                     {"id": "2", "ordem": 2, "valores": {"nome": "Cliente B"}}],
        "usinas": [
            {"id": "1", "ordem": 1, "valores": {"nome": "Jaguaré", "status": "OPERAÇÃO", "cliente": "1"}},
            {"id": "2", "ordem": 2, "valores": {"nome": "Jaguaré", "status": "OPERAÇÃO", "cliente": "2"}},
            {"id": "3", "ordem": 3, "valores": {"nome": "Serra", "status": "OPERAÇÃO", "cliente": "1"}},
            {"id": "4", "ordem": 4, "valores": {"nome": "Serra", "status": "OPERAÇÃO", "cliente": "1"}},
        ]}, listas={"status_usina": ["OPERAÇÃO"]}))
    rep = {p["id"] for p in s.pendencias() if p["tipo"] == "nome_repetido"}
    assert rep == {"3", "4"}                          # repetido é o mesmo nome no MESMO cliente
    assert s.titulo_de("clientes", s.registro("usinas", "2").valor("cliente")) == "Cliente B"


def test_coordenada_cifrada_no_arquivo_e_visivel_sem_revelar(srv, caminho):
    f, v = _form(srv, "usinas", "1", latitude="-9,8712", longitude="-47,123")
    assert srv.salvar("usinas", "1", f, v, quem="admin").ok
    bruto = caminho.read_text(encoding="utf-8")
    assert "9.8712" not in bruto and "47.123" not in bruto
    assert srv.formulario(srv.registro("usinas", "1"), revelar=False)["latitude"] == "-9,8712"


# ── listas e qualidade ─────────────────────────────────────────────────────

def test_valor_novo_na_lista_passa_a_valer(srv):
    srv.adicionar_valor("status_usina", "EM OBRA", quem="admin")
    f, v = _form(srv, "usinas", "1", status="EM OBRA")
    assert srv.salvar("usinas", "1", f, v, quem="admin").ok


def test_pendencias_do_que_o_excel_escondia(srv):
    tipos = {(p["tipo"], p["id"]) for p in srv.pendencias()}
    assert ("equipe_cargo_duplicado", "E-001") in tipos      # dois técnicos ativos na mesma equipe
    assert ("sem_email", "P-0002") in tipos                  # pessoa ativa sem e-mail
    assert ("legado", "1") in tipos                      # "Pendente" na data
    assert ("lista_parecida", "regiao") in tipos             # Sudeste × SUDESTE
