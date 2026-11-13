"""Quem instalou o Nexus Field, em Base → Acessos → Pessoas e setores (13/11/2026). Levi, pela sessão Nexus Field:
"conseguimos saber que já instalou o nexus field e logou sem eu ter que ficar cadastrando?" ("Pede"). A fonte é o livro
que o App de Campo publica (`aparelhos_nexus_field_app_campo · Aparelhos`, a v354), com a pessoa só como o código do
e-mail. O que estes testes seguram: a tela casa a linha pelo código do e-mail; vale o celular do último acesso; a versão
atual é a mais nova que algum celular tem (nada fixo no código); o filtro (instalou, versão antiga, não instalou) na
página e no endereço; o livro que ainda não existe vira aviso; e o livro está no catálogo. Nada vai ao Fracttal."""
import pytest
from test_base_fracttal import URL, com_fracttal, _visivel  # noqa: F401 (fixture)
from test_campo_visao import CHAVE, _aba, banco  # noqa: F401  (fixture)

from nexus.cadastro import setores as S
from nexus.cadastro import telas_fracttal as TF
from nexus.cadastro.ligacao_campo import codigo_da_pessoa
from nexus.campo import field_aparelhos as NF
from nexus.campo import visao
from nexus.dados import catalogo, explica


@pytest.fixture(autouse=True)
def _limpo():
    S._CACHE.clear()
    TF.esquecer()
    visao.limpar()
    yield
    S._CACHE.clear()
    TF.esquecer()
    visao.limpar()


def _ap(email, aparelho, versao, instalado, acesso):
    return {NF.C_PESSOA: codigo_da_pessoa(CHAVE, email), NF.C_APARELHO: aparelho, NF.C_VERSAO: versao,
            NF.C_INSTALADO: instalado, NF.C_ACESSO: acesso}


def _linha(h, pid):
    i = h.index(f'id="p-{pid}"')
    return h[i:h.index("</tr>", i)]


def test_a_coluna_e_o_filtro_do_nexus_field(banco, com_fracttal, logado):
    _aba(banco, NF.LIVRO, NF.ABA, [
        _ap("beltrano@exemplo.test", "moto g35 5G", "1.2.4", "2026-11-01T12:00:00Z", "2026-11-12T23:10:00Z"),
        _ap("beltrano@exemplo.test", "Galaxy A15", "1.2.3", "2026-10-20T12:00:00Z", "2026-11-01T10:00:00Z"),
        _ap("ciclano.chefe@empresa.test", "Redmi 13C", "1.2.3", "2026-10-30T12:00:00Z", "2026-11-10T12:00:00Z"),
        {NF.C_PESSOA: "nao-e-um-codigo", NF.C_APARELHO: "x", NF.C_VERSAO: "9.9.9", NF.C_INSTALADO: "",
         NF.C_ACESSO: ""}])                                         # a linha sem o código não entra (nem na versão)
    h = logado.get(URL).get_data(as_text=True)
    assert "<th>Acesso</th><th>Nexus Field</th>" in h
    b = _linha(h, 501)                                              # dois celulares: vale o do último acesso
    assert 'data-f-field="instalou"' in b and "1.2.4" in b and "12/11/2026 20:10 · moto g35 5G · 2 celulares" in b
    assert 'title="Outros celulares: Galaxy A15 (1.2.3, 01/11/2026 07:00)"' in b
    c = _linha(h, 502)                                              # abaixo da mais nova que algum celular tem
    assert 'data-f-field="instalou|antiga"' in c and "cad-chip cad-chip--alerta" in c and "1.2.3 · antiga" in c
    f = _linha(h, 503)
    assert 'data-f-field="nao_instalou"' in f and "não instalou" in f
    assert 'Nexus Field mais novo: <span class="gc-num">1.2.4</span>' in h
    assert '>Instalou (2)</option>' in h and '>Versão antiga (1)</option>' in h and '>Não instalou (2)</option>' in h
    assert 'name="field" class="gc-campo" data-fl' in h and "ainda não publicou" not in h
    # o filtro pelo endereço chega com as linhas certas escondidas (a página filtra sem ir ao servidor)
    h = logado.get(URL + "&field=antiga").get_data(as_text=True)
    assert _visivel(h, 502) and not _visivel(h, 501) and not _visivel(h, 503)
    assert 'value="antiga" data-rotulo="Versão antiga" selected' in h
    h = logado.get(URL + "&field=nao_instalou").get_data(as_text=True)
    assert _visivel(h, 503) and _visivel(h, 504) and not _visivel(h, 501)


def test_sem_o_livro_do_app_a_tela_avisa_e_ninguem_aparece_instalado(banco, com_fracttal, logado):
    h = logado.get(URL).get_data(as_text=True)
    assert "O App de Campo ainda não publicou os aparelhos do Nexus Field" in h
    assert 'data-f-field="nao_instalou"' in _linha(h, 501) and "Nexus Field mais novo" not in h


def test_a_versao_atual_e_a_mais_nova_que_algum_celular_tem():
    r = NF.resumo([{NF.C_PESSOA: "a" * 24, NF.C_VERSAO: "1.2.10", NF.C_ACESSO: "2026-11-01T00:00:00Z"},
                   {NF.C_PESSOA: "b" * 24, NF.C_VERSAO: "v1.2.9", NF.C_ACESSO: "2026-11-02T00:00:00Z"},
                   {NF.C_PESSOA: "c" * 24, NF.C_VERSAO: "beta", NF.C_ACESSO: "2026-11-02T00:00:00Z"}])
    assert r["versao_atual"] == "1.2.10"                            # 1.2.10 > 1.2.9: número a número, não texto
    assert not r["por_pessoa"]["a" * 24]["antiga"] and r["por_pessoa"]["b" * 24]["antiga"]
    assert not r["por_pessoa"]["c" * 24]["antiga"]                  # versão que não se lê não vira "antiga"
    assert NF.resumo([])["versao_atual"] == ""


def test_a_versao_como_o_app_publica():
    """O 1º livro de verdade (13/11/2026 11:25) trouxe a versão como o agente da casca: "NexusField/1.2.4" e, num celular
    de teste, "NexusField/1.2.0-rc.1". A conta só lia "1.2.4" e "v1.2.4": nenhuma versão se lia e ninguém virava
    "versão antiga". O nome antes da barra sai; a prévia fica abaixo da mesma versão sem ela."""
    assert NF.versao("NexusField/1.2.4") == NF.versao("1.2.4") == NF.versao("v1.2.4") is not None
    assert NF.versao("1.1.9") < NF.versao("NexusField/1.2.0-rc.1") < NF.versao("1.2.0") < NF.versao("NexusField/1.2.4")
    assert NF.versao("1.2.0-rc.1") < NF.versao("1.2.0-rc.2") and NF.versao("1.2") == NF.versao("1.2.0")
    assert NF.rotulo("NexusField/1.2.4") == "1.2.4" and NF.rotulo("NexusField/1.2.0-rc.1") == "1.2.0-rc.1"
    assert NF.rotulo("beta") == "beta" and NF.versao("beta") is None
    r = NF.resumo([{NF.C_PESSOA: "a" * 24, NF.C_APARELHO: "android", NF.C_VERSAO: "NexusField/1.2.4",
                    NF.C_ACESSO: "2026-11-13T13:17:48.729Z"},
                   {NF.C_PESSOA: "b" * 24, NF.C_APARELHO: "android", NF.C_VERSAO: "NexusField/1.2.0-rc.1",
                    NF.C_ACESSO: "2026-11-13T10:49:50.008Z"}])
    a, b = r["por_pessoa"]["a" * 24], r["por_pessoa"]["b" * 24]
    assert r["versao_atual"] == "1.2.4" and a["versao"] == "1.2.4" and not a["antiga"]
    assert b["versao"] == "1.2.0-rc.1" and b["antiga"] and a["acesso_txt"] == "13/11/2026 10:17"


def test_a_tela_com_o_livro_como_o_app_publica(banco, com_fracttal, logado):
    _aba(banco, NF.LIVRO, NF.ABA, [
        _ap("beltrano@exemplo.test", "android", "NexusField/1.2.4", "2026-11-12T13:01:51.638Z", "2026-11-13T13:17:48.729Z"),
        _ap("ciclano.chefe@empresa.test", "android", "NexusField/1.2.0-rc.1", "2026-11-09T18:31:16.623Z",
            "2026-11-13T10:49:50.008Z")])
    h = logado.get(URL).get_data(as_text=True)
    assert "NexusField/" not in h and 'Nexus Field mais novo: <span class="gc-num">1.2.4</span>' in h
    assert 'data-f-field="instalou"' in _linha(h, 501) and "1.2.4" in _linha(h, 501)
    c = _linha(h, 502)
    assert 'data-f-field="instalou|antiga"' in c and "1.2.0-rc.1 · antiga" in c
    assert '>Instalou (2)</option>' in h and '>Versão antiga (1)</option>' in h


def test_o_livro_do_app_esta_no_catalogo():
    f = catalogo.POR_ID["aparelho_field"]
    assert f.livro == f"{NF.LIVRO} · {NF.ABA}" and f.fontes == (f.livro,) and f.dims["pessoa"][0] == "hmac"
    assert set(f.chave) <= {NF.C_PESSOA, NF.C_APARELHO, NF.C_VERSAO, NF.C_INSTALADO, NF.C_ACESSO}
    assert "aparelho_field" in explica.RESUMO and "aparelho_field" in explica.PARA_QUE
