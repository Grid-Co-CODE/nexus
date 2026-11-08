"""Os administradores do App de Campo (05/11/2026, nexus/pcm/admins_app.py: o livro `nexus_acessos_app_campo`, só deles).

Levi, 05/11/2026: "os administradores do App de Campo e os técnicos por usina têm de ser escolhidos no Nexus". O que
estes testes seguram: a assinatura igual à do contrato com o App (os dois vetores fixos); vale a última decisão de cada
código × papel (empate: a de depois no livro), com as datas e o dia de Brasília; pôr, tirar e a mesma decisão que não
grava de novo; o código que já está na lista com outra ficha é recusado; sem código, sem a NEXUS_PESSOA_HMAC, a leitura
que falha e a observação sem a chave do cadastro não gravam; nada em claro no livro; o livro é só deles (a gravação dos
técnicos não o toca, e a deles não toca o dos técnicos: revisão de 05/11, um Nexus antigo trocaria o livro dos técnicos
inteiro sem a aba nova); a leitura incompleta da listagem sobe em vez de virar "livro vazio"; e o catálogo e o radar da
Governança conhecem o livro. Nada vai ao banco de verdade."""
import hashlib
import hmac
import io
import json
from datetime import datetime, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.ligacao_campo import codigo_da_pessoa
from nexus.dados import catalogo, explica, livros, radar
from nexus.pcm import admins_app as AA
from nexus.pcm import atribuicoes as A
from test_dados_camada import PROIBIDAS
from test_pcm_atribuicoes import Relogio

PESSOA = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste"}
CHAVE = "chave-hmac-de-teste"
# os vetores do contrato (`_propostas/admins-app-nexus/LEIA.md` do app-campo-docs): os mesmos nos dois lados
VETOR_LINHA = {"pessoa_hmac": "0123456789abcdef01234567", "papel": "admin", "ativo": "sim", "de_data_id": "",
               "ate_data_id": 20261231, "decidida_em": "2026-11-05T14:30:00Z"}
VETOR = "c657c3aaf1d64a5aae81f585a40115bb9bf11dffbd98bcff9338c00eeea9241c"
LINHA_COMPLETA = {"decidida_em": "2026-11-05T14:30:00Z", "data_id": 20261105, "pessoa_id": 9001,
                  "pessoa_hmac": "71ed3f80ace91f8cf509cbda", "papel": "admin", "ativo": "sim", "de_data_id": "",
                  "ate_data_id": "", "origem": "tela", "decidida_por_hmac": "b9525c290e97596479379177",
                  "dados_cifrados": ""}
VETOR_COMPLETO = "8bae838bd5f8cb0672e38f5a1a091c3afe19ab1797d7f16f02f9ca351ae57f8c"


@pytest.fixture
def cfg(tmp_path):
    A.limpar()
    AA.limpar()
    return {"TESTING": True, "NEXUS_ADMINS_APP_ARQUIVO": str(tmp_path / "admins_app.json"),
            "NEXUS_PCM_ATRIBUICOES_ARQUIVO": str(tmp_path / "atribuicoes.json"),
            "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_PESSOA_HMAC": CHAVE}


@pytest.fixture
def relogio(monkeypatch):
    """O relógio do livro em 05/11/2026 12:00Z, um minuto a cada decisão."""
    return Relogio(monkeypatch, inicio=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc))


def cod(pid, versao=0):
    return f"{pid + 1000 * versao:024x}"


def _por(cfg, pid=10, codigo=None, **kw):
    return AA.decidir(cfg, pessoa_id=pid, pessoa_hmac=codigo or cod(pid), ativo=True, usuario=PESSOA, **kw)


def _tirar(cfg, pid=10, codigo=None):
    return AA.decidir(cfg, pessoa_id=pid, pessoa_hmac=codigo or cod(pid), ativo=False, usuario=PESSOA)


def _atuais(cfg, hoje=20261105):
    return AA.atuais(AA.ler(cfg, forcar=True), hoje)


def _arquivo(cfg, chave="NEXUS_ADMINS_APP_ARQUIVO"):
    return json.loads(open(cfg[chave], encoding="utf-8").read())


# ── o contrato com o App ─────────────────────────────────────────────────────────────────────────────────────────
def test_assinatura_igual_a_do_contrato_com_o_app():
    assert AA.assinatura(VETOR_LINHA, CHAVE) == VETOR
    # a mesma conta, à mão, como o contrato a escreve (chave derivada pelo rótulo; o texto com o dia como inteiro)
    chave = hmac.new(CHAVE.encode(), b"nexus:pcm:admins-app", hashlib.sha256).digest()
    txt = "admin_app|0123456789abcdef01234567|admin|sim||20261231|2026-11-05T14:30:00Z"
    assert hmac.new(chave, txt.encode(), hashlib.sha256).hexdigest() == VETOR
    assert AA.assinatura(VETOR_LINHA, "") == "" and AA.assinatura(VETOR_LINHA, "outra") != VETOR
    # a assinatura dos técnicos é outra (outro rótulo, outro texto): uma linha não vale pela outra
    assert A.ROTULO_CHAVE != AA.ROTULO_CHAVE


def test_o_vetor_da_linha_completa_do_contrato():
    """O vetor da linha inteira (revisão de 05/11/2026): o código do e-mail da pessoa e de quem decidiu pelo
    `codigo_da_pessoa` (sem espaço nas pontas e sem caixa) e a assinatura da linha como ela vai ao livro."""
    assert codigo_da_pessoa(CHAVE, "tecnico.exemplo@exemplo.com.br") == "71ed3f80ace91f8cf509cbda"
    assert codigo_da_pessoa(CHAVE, "  Tecnico.Exemplo@EXEMPLO.com.br ") == "71ed3f80ace91f8cf509cbda"
    assert codigo_da_pessoa(CHAVE, "admin.exemplo@exemplo.com.br") == "b9525c290e97596479379177"
    # a chave com espaço nas pontas dá o mesmo código (2ª revisão de 05/11/2026: a lista, o avulso e o setores.definir
    # aparavam a chave cada um do seu jeito); os dois vetores não mudam
    assert codigo_da_pessoa(f"  {CHAVE} ", "tecnico.exemplo@exemplo.com.br") == "71ed3f80ace91f8cf509cbda"
    assert codigo_da_pessoa(f"{CHAVE}\n", "admin.exemplo@exemplo.com.br") == "b9525c290e97596479379177"
    assert codigo_da_pessoa("   ", "tecnico.exemplo@exemplo.com.br") is None
    assert AA.assinatura(VETOR_LINHA, f" {CHAVE} ") == VETOR
    assert list(LINHA_COMPLETA) == list(AA.CAB[:-1])
    assert AA.assinatura(LINHA_COMPLETA, CHAVE) == VETOR_COMPLETO
    chave = hmac.new(CHAVE.encode(), b"nexus:pcm:admins-app", hashlib.sha256).digest()
    txt = "admin_app|71ed3f80ace91f8cf509cbda|admin|sim|||2026-11-05T14:30:00Z"
    assert hmac.new(chave, txt.encode(), hashlib.sha256).hexdigest() == VETOR_COMPLETO


def test_as_colunas_e_cada_linha_como_o_contrato(cfg, relogio):
    assert AA.CAB == ("decidida_em", "data_id", "pessoa_id", "pessoa_hmac", "papel", "ativo", "de_data_id",
                      "ate_data_id", "origem", "decidida_por_hmac", "dados_cifrados", "assinatura")
    assert (AA.LIVRO, AA.ABA) == ("nexus_acessos_app_campo", "fato_admin_app")
    assert _por(cfg)["gravou"] is True
    d = _arquivo(cfg)
    assert list(d) == [AA.ABA]
    linha = d[AA.ABA][0]
    assert list(linha) == list(AA.CAB)
    assert (linha["papel"], linha["ativo"], linha["origem"], linha["pessoa_id"], linha["pessoa_hmac"]) == (
        "admin", "sim", "tela", 10, cod(10))
    assert linha["decidida_em"] == "2026-11-05T12:01:00Z" and linha["data_id"] == 20261105
    assert linha["de_data_id"] is None and linha["ate_data_id"] is None            # vazio no livro
    assert linha["assinatura"] == AA.assinatura(linha, CHAVE)
    assert linha["decidida_por_hmac"] == codigo_da_pessoa(CHAVE, PESSOA["email"])


# ── o vigente ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_vale_a_ultima_decisao_de_cada_codigo_e_papel(cfg, relogio):
    _por(cfg, 10)
    _por(cfg, 11)
    _tirar(cfg, 10)
    assert set(_atuais(cfg)) == {(cod(11), "admin")}
    assert _atuais(cfg)[(cod(11), "admin")]["status"] == "vale"
    # o App acha a pessoa pelo código: a mesma ficha com o e-mail corrigido é outra linha (o tirar leva o código que pôs)
    _por(cfg, 11, codigo=cod(11, 1))
    assert set(_atuais(cfg)) == {(cod(11), "admin"), (cod(11, 1), "admin")}


def test_no_empate_da_hora_vale_a_de_depois_no_livro():
    def linha(ativo):
        return {"decidida_em": "2026-11-05T12:00:00Z", "pessoa_id": 10, "pessoa_hmac": cod(10), "papel": "admin",
                "ativo": ativo, "de_data_id": None, "ate_data_id": None}
    assert AA.atuais({"decisoes": [linha("sim"), linha("nao")]}, 20261105) == {}
    assert set(AA.atuais({"decisoes": [linha("nao"), linha("sim")]}, 20261105)) == {(cod(10), "admin")}


def test_as_datas_pelo_dia_de_brasilia(cfg, monkeypatch):
    rel = Relogio(monkeypatch, inicio=datetime(2026, 11, 6, 2, 29, tzinfo=timezone.utc))    # 23h30 de 05/11 em Brasília
    _por(cfg, 10, ate="2026-11-05")
    assert _arquivo(cfg)[AA.ABA][0]["data_id"] == 20261105
    _por(cfg, 11, de="2026-11-10")
    assert _atuais(cfg, 20261105)[(cod(10), "admin")]["status"] == "vale"          # o último dia ainda vale
    assert (cod(10), "admin") not in _atuais(cfg, 20261106)
    assert _atuais(cfg, 20261105)[(cod(11), "admin")]["status"] == "agendado"
    assert _atuais(cfg, 20261110)[(cod(11), "admin")]["status"] == "vale"
    with pytest.raises(AA.Recusada):
        _por(cfg, 12, ate="2026-11-04")                                           # o prazo que já acabou
    with pytest.raises(AA.Recusada):
        _por(cfg, 12, de="2026-11-20", ate="2026-11-12")
    with pytest.raises(AA.Recusada):
        _por(cfg, 12, ate="05/11/2026")
    assert rel.t.date().isoformat() == "2026-11-06"


# ── pôr e tirar ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_mesma_decisao_nao_grava_de_novo_e_tirar_quem_nao_e_recusa(cfg, relogio):
    assert _por(cfg)["gravou"] is True
    assert _por(cfg)["gravou"] is False
    assert len(_arquivo(cfg)[AA.ABA]) == 1
    assert _tirar(cfg)["gravou"] is True
    with pytest.raises(AA.Recusada, match="já não é administrador"):
        _tirar(cfg)
    with pytest.raises(AA.Recusada, match="já não é administrador"):
        _tirar(cfg, 11)
    assert [x["ativo"] for x in _arquivo(cfg)[AA.ABA]] == ["sim", "nao"]
    with pytest.raises(AA.Recusada):
        AA.decidir(cfg, pessoa_id=10, pessoa_hmac=cod(10), ativo=True, usuario=PESSOA, papel="dono")


def test_o_codigo_que_ja_esta_na_lista_com_outra_ficha_e_recusado(cfg, relogio):
    """Revisão de 05/11/2026: o usuário do Fracttal religado da ficha 11 para a 10 leva o código junto. Pôr a 10 com o
    código que já vale na lista pela 11 não é "a mesma decisão": é outra pessoa no lugar, e o Nexus diria que a 10 é
    administradora sem ter gravado nada."""
    _por(cfg, 11, codigo=cod(500))
    with pytest.raises(AA.Recusada, match="outra ficha"):
        _por(cfg, 10, codigo=cod(500))
    assert [x["pessoa_id"] for x in _arquivo(cfg)[AA.ABA]] == [11]
    _tirar(cfg, 11, codigo=cod(500))
    assert _por(cfg, 10, codigo=cod(500))["gravou"] is True                 # tirada a outra, a 10 entra


def test_sem_codigo_nao_poe(cfg, relogio):
    with pytest.raises(AA.Recusada, match="e-mail na ficha nem usuário do Fracttal ligado: o App não a reconheceria"):
        AA.decidir(cfg, pessoa_id=10, pessoa_hmac="", ativo=True, usuario=PESSOA)
    assert AA.ler(cfg, forcar=True)["decisoes"] == []


def test_sem_a_chave_hmac_nada_grava(cfg, relogio):
    """Sem a NEXUS_PESSOA_HMAC a linha iria sem assinatura e o App a descartaria: o Nexus diria uma coisa e o App faria
    outra."""
    cfg.pop("NEXUS_PESSOA_HMAC")
    with pytest.raises(AA.Recusada, match="NEXUS_PESSOA_HMAC"):
        _por(cfg)
    assert AA.ler(cfg, forcar=True)["decisoes"] == []


def test_leitura_que_falha_nao_grava(cfg, relogio, monkeypatch, tmp_path):
    _por(cfg, 10)
    antes = (tmp_path / "admins_app.json").read_text(encoding="utf-8")

    def cai(c):
        raise ConnectionError("banco fora")
    monkeypatch.setattr(AA, "_ler_cru", cai)
    with pytest.raises(AA.Recusada, match="nada foi gravado"):
        _por(cfg, 11)
    assert (tmp_path / "admins_app.json").read_text(encoding="utf-8") == antes
    assert AA.ler(cfg, forcar=True)["erro"].startswith("ConnectionError")


def test_nada_em_claro_e_a_observacao_cifrada(cfg, relogio, tmp_path):
    _por(cfg, 10, obs="cobre as férias do supervisor")
    _tirar(cfg, 10)
    txt = (tmp_path / "admins_app.json").read_text(encoding="utf-8")
    assert "férias" not in txt and "ferias" not in txt and "Pessoa Teste" not in txt and "@" not in txt
    h = AA.historico(cfg, AA.ler(cfg, forcar=True))
    assert [x["acao"] for x in h] == ["tirou", "pôs"]
    assert h[1]["obs"] == "cobre as férias do supervisor" and h[0]["obs"] == ""
    assert h[1]["pessoa_id"] == 10 and h[1]["pessoa_hmac"] == cod(10) and h[1]["quem_hmac"]
    cfg.pop("NEXUS_CHAVE_CADASTRO")
    with pytest.raises(AA.Recusada, match="NEXUS_CHAVE_CADASTRO"):
        _por(cfg, 11, obs="sem a chave a observação não vai")
    assert AA.historico(cfg, AA.ler(cfg, forcar=True))[1]["obs"] == ""         # sem a chave, sem a observação


# ── sem ficha e o avulso pelo e-mail (05/11/2026) ─────────────────────────────────────────────────────────────────
# Levi, 05/11/2026: "tem que aparecer todos do pessoas e setores! e tem que ter como fazer avulso também so digitando o
# e-mail". Quem é do escritório não tem ficha no cadastro: a linha vai sem `pessoa_id`, e o avulso leva o e-mail só cifrado.
AVULSO = "pessoa.avulsa@gridco.com.br"


def _avulso(cfg, email=AVULSO, **kw):
    return AA.decidir(cfg, pessoa_id=None, pessoa_hmac="", ativo=True, usuario=PESSOA, email=email, **kw)


def test_sem_ficha_o_pessoa_id_vai_vazio_e_o_vigente_e_o_tirar_sao_pelo_codigo(cfg, relogio):
    assert AA.decidir(cfg, pessoa_id=None, pessoa_hmac=cod(700), ativo=True, usuario=PESSOA)["gravou"] is True
    linha = _arquivo(cfg)[AA.ABA][0]
    assert list(linha) == list(AA.CAB)                                  # as 12 colunas, como sempre
    assert (linha["pessoa_id"], linha["pessoa_hmac"], linha["origem"], linha["dados_cifrados"]) == (
        None, cod(700), "tela", None)
    assert linha["assinatura"] == AA.assinatura(linha, CHAVE)
    assert set(_atuais(cfg)) == {(cod(700), "admin")}
    assert AA.decidir(cfg, pessoa_id=None, pessoa_hmac=cod(700), ativo=True, usuario=PESSOA)["gravou"] is False
    assert AA.decidir(cfg, pessoa_id=None, pessoa_hmac=cod(700), ativo=False, usuario=PESSOA)["gravou"] is True
    assert _atuais(cfg) == {}
    # o pessoa_id que veio e não é um ID não vira "sem ficha": só o None diz que a pessoa não tem ficha
    for ruim in ("", "abc", 0):
        with pytest.raises(AA.Recusada, match="Faltou a pessoa"):
            AA.decidir(cfg, pessoa_id=ruim, pessoa_hmac=cod(701), ativo=True, usuario=PESSOA)


def test_o_avulso_leva_o_email_so_cifrado_e_amarrado_a_linha(cfg, relogio, tmp_path):
    assert _avulso(cfg, email="  Pessoa.Avulsa@GRIDCO.com.br ", obs="cobre a gerência")["gravou"] is True
    linha = _arquivo(cfg)[AA.ABA][0]
    assert linha["pessoa_id"] is None and linha["pessoa_hmac"] == codigo_da_pessoa(CHAVE, AVULSO)
    assert linha["assinatura"] == AA.assinatura(linha, CHAVE) and linha["dados_cifrados"]
    txt = (tmp_path / "admins_app.json").read_text(encoding="utf-8")
    assert "@" not in txt and "avulsa" not in txt.lower() and "gerência" not in txt and "gerencia" not in txt
    h = AA.historico(cfg, AA.ler(cfg, forcar=True))[0]
    assert (h["email"], h["obs"], h["pessoa_id"], h["acao"]) == (AVULSO, "cobre a gerência", None, "pôs")
    # a cifra amarrada à linha: a mesma cifra noutra linha (outro código ou outra hora) não abre
    for outra in (dict(linha, pessoa_hmac=cod(9)), dict(linha, decidida_em="2026-11-05T12:59:00Z")):
        assert AA.historico(cfg, {"decisoes": [outra]})[0]["email"] == ""
    # o tirar é pelo código, como o dos outros; a linha do tirar não leva o e-mail
    assert AA.decidir(cfg, pessoa_id=None, pessoa_hmac=linha["pessoa_hmac"], ativo=False, usuario=PESSOA)["gravou"]
    h = AA.historico(cfg, AA.ler(cfg, forcar=True))
    assert [(x["acao"], x["email"]) for x in h] == [("tirou", ""), ("pôs", AVULSO)] and _atuais(cfg) == {}
    # o mesmo e-mail de novo, já valendo: a mesma decisão não grava
    _avulso(cfg)
    assert _avulso(cfg)["gravou"] is False and len(_arquivo(cfg)[AA.ABA]) == 3


def test_o_avulso_so_aceita_o_dominio_da_grid_e_o_formato(cfg, relogio):
    """O administrador do App entra pela conta Microsoft da Grid: outro domínio nunca casaria com ela."""
    assert AA.email_do_avulso("  Pessoa.Avulsa@GridCo.com.BR ") == AVULSO
    for ruim in ("pessoa@exemplo.com", "pessoa@gridco.com", "pessoa@sub.gridco.com.br"):
        with pytest.raises(AA.Recusada, match="Só e-mail @gridco.com.br"):
            _avulso(cfg, email=ruim)
    for ruim in ("nao e email", "pessoa@", "a@b@gridco.com.br", "pessoa avulsa@gridco.com.br"):
        with pytest.raises(AA.Recusada, match="E-mail inválido"):
            _avulso(cfg, email=ruim)
    with pytest.raises(AA.Recusada, match="Digite o e-mail"):
        AA.email_do_avulso("   ")
    assert AA.ler(cfg, forcar=True)["decisoes"] == []


def test_o_avulso_sem_a_chave_do_cadastro_nao_grava(cfg, relogio):
    """O e-mail vai cifrado: sem a chave do cadastro ele iria em claro, então nada se grava."""
    cfg.pop("NEXUS_CHAVE_CADASTRO")
    with pytest.raises(AA.Recusada, match="NEXUS_CHAVE_CADASTRO"):
        _avulso(cfg)
    assert AA.ler(cfg, forcar=True)["decisoes"] == []


def test_o_avulso_e_so_sem_ficha_e_com_o_codigo_do_proprio_email(cfg, relogio):
    with pytest.raises(AA.Recusada, match="sem ficha"):
        AA.decidir(cfg, pessoa_id=10, pessoa_hmac="", ativo=True, usuario=PESSOA, email=AVULSO)
    with pytest.raises(AA.Recusada, match="não é o deste e-mail"):
        AA.decidir(cfg, pessoa_id=None, pessoa_hmac=cod(9), ativo=True, usuario=PESSOA, email=AVULSO)
    with pytest.raises(AA.Recusada, match="só vai no pôr"):
        AA.decidir(cfg, pessoa_id=None, pessoa_hmac="", ativo=False, usuario=PESSOA, email=AVULSO)
    assert AA.ler(cfg, forcar=True)["decisoes"] == []


def test_sem_ficha_com_o_codigo_que_ja_vale_por_uma_ficha_e_o_contrario(cfg, relogio):
    """O código que já vale por uma ficha não vai de novo sem ficha (o e-mail da ficha mudou e o código de antes ficou na
    linha: para o Nexus é outra pessoa; tire aquela antes). O que já vale sem ficha e hoje é o de uma ficha é a mesma
    pessoa para o App (o mesmo código): nada muda, e nada grava."""
    _por(cfg, 10, codigo=cod(800))
    with pytest.raises(AA.Recusada, match="outra ficha"):
        AA.decidir(cfg, pessoa_id=None, pessoa_hmac=cod(800), ativo=True, usuario=PESSOA)
    AA.decidir(cfg, pessoa_id=None, pessoa_hmac=cod(801), ativo=True, usuario=PESSOA)
    assert _por(cfg, 11, codigo=cod(801))["gravou"] is False
    assert [x["pessoa_id"] for x in _arquivo(cfg)[AA.ABA]] == [10, None]


# ── o livro só deles ────────────────────────────────────────────────────────────────────────────────────────────
def _tecnico(cfg, pid):
    return A.decidir(cfg, usina_id=1, usina_fracttal="Cliente A - Usina 1 - SP", pessoa_id=pid,
                     pessoa_hmac=cod(pid), na_usina=True, usuario=PESSOA)


def test_os_administradores_moram_num_arquivo_so_deles_na_copia_de_prova(cfg, relogio):
    _tecnico(cfg, 10)
    _por(cfg, 20)
    _tecnico(cfg, 11)
    _por(cfg, 21)
    assert list(_arquivo(cfg, "NEXUS_PCM_ATRIBUICOES_ARQUIVO")) == [A.ABA]
    assert [x["pessoa_id"] for x in _arquivo(cfg, "NEXUS_PCM_ATRIBUICOES_ARQUIVO")[A.ABA]] == [10, 11]
    assert [x["pessoa_id"] for x in _arquivo(cfg)[AA.ABA]] == [20, 21]


class _Gravacoes(ApiPGFalsa):
    """O banco de mentira que guarda, de cada gravação, o livro e as abas que foram."""

    def __init__(self):
        super().__init__()
        self.enviadas = []

    def post(self, url, headers=None, json=None, params=None, files=None, timeout=None):
        if files:
            from openpyxl import load_workbook
            livro = url.split("/api/workbooks/")[1].split("/")[0]
            self.enviadas.append((livro, load_workbook(io.BytesIO(files["file"][1])).sheetnames))
        return super().post(url, headers=headers, json=json, params=params, files=files, timeout=timeout)


@pytest.fixture
def no_banco(app):
    """Os livros no banco de mentira (sem os arquivos da cópia de prova e fora do modo de teste, que não lê o banco)."""
    A.limpar()
    AA.limpar()
    api = _Gravacoes()
    app.extensions["nexus_dados_sessao"] = api
    cfg = {"GRIDCO_DB_API": "http://pg.falso", "GRIDCO_SQL_TOKEN": "tk", "NEXUS_PESSOA_HMAC": CHAVE,
           "NEXUS_CHAVE_CADASTRO": gerar_chave()}
    with app.app_context():
        yield api, cfg
    app.extensions.pop("nexus_dados_sessao", None)


def test_os_administradores_moram_num_livro_so_deles_no_banco(no_banco, relogio):
    """Revisão de 05/11/2026: com a aba no livro dos técnicos, um Nexus antigo (o `_gravar_cru` de 8cdead0 troca o
    livro inteiro só com a aba dele) apagaria os administradores. Cada um no seu livro, nenhum toca no outro."""
    api, cfg = no_banco
    _tecnico(cfg, 10)
    _por(cfg, 20)
    _tecnico(cfg, 11)
    _por(cfg, 21)
    assert api.enviadas == [(A.LIVRO, [A.ABA]), (AA.LIVRO, [AA.ABA])] * 2
    assert [x["pessoa_id"] for x in api.linhas(A.LIVRO, A.ABA)] == [10, 11]
    assert [x["pessoa_id"] for x in api.linhas(AA.LIVRO, AA.ABA)] == [20, 21]
    assert (A.LIVRO, AA.ABA) not in api.abas


def test_a_aba_que_some_da_listagem_e_leitura_incompleta_nao_livro_vazio(no_banco, relogio):
    """Achado 6 da revisão: com a listagem de abas falhando por um instante (o livro existe, o `sheet_count` diz 1 e a
    aba não vem), a leitura voltava [] e a gravação seguinte publicaria só a linha nova. Agora a leitura sobe, a tela
    diz e nada grava, nos dois livros."""
    api, cfg = no_banco
    _por(cfg, 20)
    _tecnico(cfg, 10)
    syncs = api.syncs
    api.omitir |= {AA.LIVRO, A.LIVRO}
    with pytest.raises(livros.LeituraIncompleta):
        AA._ler_cru(cfg)
    with pytest.raises(livros.LeituraIncompleta):
        A._ler_cru(cfg)
    with pytest.raises(AA.Recusada, match="nada foi gravado"):
        _por(cfg, 21)
    with pytest.raises(A.Recusada, match="nada foi gravado"):
        _tecnico(cfg, 11)
    assert AA.ler(cfg, forcar=True)["erro"].startswith("LeituraIncompleta")
    assert api.syncs == syncs
    api.omitir.clear()
    # a aba que o livro não tem (mas o livro existe e tem outra): também não é "vazio"
    api._id(AA.LIVRO, "outra_aba")["linhas"] = []
    api.abas.pop((AA.LIVRO, AA.ABA))
    with pytest.raises(livros.LeituraIncompleta):
        AA._ler_cru(cfg)


def test_o_livro_criado_e_nunca_gravado_le_vazio(no_banco):
    """O livro que o banco diz ter 0 abas (criado e nunca gravado) é vazio de verdade, como na trava da gravação."""
    api, cfg = no_banco
    api.workbooks[AA.LIVRO] = {"key": AA.LIVRO}
    api.workbooks[A.LIVRO] = {"key": A.LIVRO}
    assert AA._ler_cru(cfg) == [] and A._ler_cru(cfg) == []


def test_a_trava_do_catalogo_nao_deixa_o_livro_encolher(no_banco, relogio):
    api, cfg = no_banco
    _por(cfg, 20)
    _por(cfg, 21)
    with pytest.raises(livros.GravacaoRecusada, match="2"):
        livros.publicar(AA.LIVRO, AA.NOME_LIVRO, {AA.ABA: (list(AA.CAB), [])}, base="http://pg.falso", token="tk",
                        sessao=api)
    assert len(api.linhas(AA.LIVRO, AA.ABA)) == 2


# ── a governança ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_livro_esta_no_catalogo_e_o_radar_nao_o_acusa():
    f = catalogo.POR_ID["decisao_admin_app"]
    assert f.livro == f"{AA.LIVRO} · {AA.ABA}" == "nexus_acessos_app_campo · fato_admin_app" and f.fontes == (f.livro,)
    assert f.area == "base"
    assert f.grao.startswith("1 linha = 1 decisão de pôr ou tirar 1 pessoa como administrador do App de Campo")
    assert f.tipo == "sem_medida" and f.medidas == () and f.chave[0] == AA.CAB[0]
    assert set(f.chave) <= set(AA.CAB)
    assert {d for d, (e, _c) in f.dims.items() if e != "nao"} == {"data", "pessoa"}
    assert f.dims["data"][0] == f.dims["pessoa"][0] == "id"
    # o pessoa_id pode vir vazio (sem ficha: Pessoas e setores ou o avulso, 05/11/2026), e o catálogo diz
    assert "vazio = sem ficha" in f.dims["pessoa"][1] and "avulso" in f.dims["pessoa"][1]
    lv = catalogo.LIVRO_POR_NOME[AA.LIVRO]
    assert lv.abas == (AA.ABA,) and lv.so_cresce == lv.abas and "admins_app.py" in lv.quem_grava and not lv.no_banco
    # o livro dos técnicos volta a ter uma aba só
    assert catalogo.LIVRO_POR_NOME[A.LIVRO].abas == (A.ABA,)
    caixas = radar.classificar({(AA.LIVRO, AA.ABA): {"id": 1, "row_count": 2},
                                (A.LIVRO, A.ABA): {"id": 2, "row_count": 9}})
    assert caixas["nova"] == [] and {(t["livro"], t["aba"]) for t in caixas["fato"]} == {(AA.LIVRO, AA.ABA),
                                                                                          (A.LIVRO, A.ABA)}
    assert explica.RESUMO["decisao_admin_app"] and explica.PARA_QUE["decisao_admin_app"]
    # nada pessoal em claro nas colunas (regra 8): pessoa só como pessoa_id e código; a observação só cifrada
    assert not [c for c in AA.CAB if any(c == p or c.startswith(p + "_") for p in PROIBIDAS)]
