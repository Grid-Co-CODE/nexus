"""O canal de abertura dos fabricantes que traz e-mail mora no banco do Nexus, cifrado (19/11/2026).

Levi, 19/11/2026: "OS Creator: os e-mails dos fabricantes vão para uma tabela de cadastro no banco" e "quem tiver um acesso
do Nexus vai ter a informação completa". O `chamado_spec.CANAL` do repositório (público) diz só que o canal é reservado; o
texto inteiro vem do livro `nexus_textos_reservados` (área `oscreator_canal`, a chave é o fabricante) e aparece igual no
"Como abrir", no Raio X, no Controle de fornecedores e no texto de abertura. O cadastro `os_creator · chamado_modelos` não
serviu: guarda em claro, num banco de leitura aberta, e a linha `MARCA:` gravada lá congela as subtarefas do fabricante
também para o App de Campo.

Endereços inventados; nenhum teste lê o banco de verdade."""
import base64
import inspect
import json
import re
import sys
from pathlib import Path

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import Cofre
from nexus.dados import textos_reservados as TR
from nexus.torres.oscreator import canais_reservados, ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import chamado_modelos_store as cms  # noqa: E402 — do clone
import chamado_spec as cs  # noqa: E402
from chamado_garantia import registro as R  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RESERVADAS = {"Axial", "Canadian Solar", "Convert", "Hukseflux"}
DO_BANCO = "E-mail — suporte@marca-um.exemplo.test e garantia@marca-um.exemplo.test"
CHAVE = base64.urlsafe_b64encode(b"c" * 32).decode()
BASE = "http://banco.exemplo.test"


@pytest.fixture(autouse=True)
def _codigo_puro():
    def limpar():
        cms.CANAIS_RESERVADOS = None
        cms._canais.update(marca=None, lido={})
        cms.aplicar({})
    limpar()
    yield
    limpar()


def test_nenhum_endereco_de_email_no_codigo_do_chamado():
    for arq in ("nexus/torres/oscreator/os_creator/chamado_spec.py", "nexus/torres/oscreator/chamado_garantia/spec.py"):
        assert not EMAIL.findall((RAIZ / arq).read_text(encoding="utf-8")), arq


def test_os_canais_com_email_sao_reservados_no_codigo_e_os_outros_seguem_como_eram():
    assert {m for m, c in cms._ORIG["CANAL"].items() if c == cs.RESERVADO} == RESERVADAS
    assert "banco do Nexus" in cs.RESERVADO and not EMAIL.findall(cs.RESERVADO)
    assert cms._ORIG["CANAL"]["Huawei"].startswith("Portal Digital Power")
    assert cms._ORIG["CANAL"]["Brametal"].startswith("Canal ainda não documentado")


def test_com_o_gancho_o_canal_do_banco_aparece_inteiro_em_toda_tela():
    cms.CANAIS_RESERVADOS = lambda: {"Axial": DO_BANCO, "Huawei": "não troca: o código não reservou este"}
    cms.canais_em_dia()
    assert cs.CANAL["Axial"] == DO_BANCO                                     # o "Como abrir" e o Raio X leem daqui
    assert cms.efetivo({})["MARCA:Axial"]["canal"] == DO_BANCO               # o Controle de fornecedores
    assert cms.semente()["MARCA:Axial"]["canal"] == DO_BANCO
    assert f"Abertura: {DO_BANCO}" in cs.texto_abertura("Axial")             # o texto que a equipe de chamados copia
    assert cs.CANAL["Huawei"].startswith("Portal Digital Power")
    # o fabricante reservado que o banco não trouxe segue dizendo que é reservado: nunca "não documentado"
    assert cs.CANAL["Convert"] == cs.RESERVADO


def test_o_canal_do_banco_que_muda_entra_no_pedido_seguinte_sem_reiniciar():
    canais = {"Axial": DO_BANCO}
    cms.CANAIS_RESERVADOS = lambda: dict(canais)
    cms.canais_em_dia()
    canais["Axial"] = "Portal novo do fabricante"
    cms.canais_em_dia()
    assert cs.CANAL["Axial"] == "Portal novo do fabricante"


def test_sem_o_gancho_ou_com_o_banco_fora_a_tela_diz_que_o_canal_e_reservado():
    assert cs.CANAL["Axial"] == cs.RESERVADO          # o OS Creator fora do Nexus (o app de mesa tem a cópia dele)

    def quebra():
        raise RuntimeError("banco fora")
    cms.CANAIS_RESERVADOS = quebra
    cms.canais_em_dia()                                # não levanta
    cms.aplicar({})
    assert cs.CANAL["Axial"] == cs.RESERVADO


def test_o_banco_que_cai_depois_de_lido_nao_apaga_o_canal_da_tela():
    estado = {"ok": True}

    def gancho():
        if not estado["ok"]:
            raise RuntimeError("banco fora")
        return {"Axial": DO_BANCO}
    cms.CANAIS_RESERVADOS = gancho
    cms.canais_em_dia()
    estado["ok"] = False
    cms.canais_em_dia()
    cms.aplicar({})                                    # o `garantir` de 5 em 5 minutos reaplica: o canal lido fica
    assert cs.CANAL["Axial"] == DO_BANCO


def test_o_canal_salvo_no_controle_de_fornecedores_segue_vencendo():
    cms.CANAIS_RESERVADOS = lambda: {"Axial": DO_BANCO}
    banco = R.de_linhas([{"chave": "MARCA:Axial", "valor": json.dumps(
        {"subtarefas": [], "canal": "Portal do fabricante", "atende": ["Estrutura Trackers"],
         "versao": "2026-11-19T10:00:00-03:00", "por": "Analista Teste"}, ensure_ascii=False)}])
    cms.aplicar(banco)
    assert cs.CANAL["Axial"] == "Portal do fabricante"


def test_o_gancho_do_nexus_le_a_area_do_os_creator_no_livro_dos_textos_reservados(app):
    api = ApiPGFalsa()
    TR.publicar(canais_reservados.AREA, {"Axial": DO_BANCO}, base=BASE, sessao=api, token="tk", cofre=Cofre(CHAVE))
    app.extensions["nexus_dados_sessao"] = api
    app.config.update(NEXUS_CHAVE_CADASTRO=CHAVE, GRIDCO_DB_API=BASE)
    assert canais_reservados.AREA == "oscreator_canal" and canais_reservados.ligar(app)() == {"Axial": DO_BANCO}


def test_a_ponte_liga_o_gancho_e_confere_o_canal_antes_de_cada_rota_do_clone():
    fonte = inspect.getsource(ponte._criar_clone)
    assert "CANAIS_RESERVADOS = canais_reservados.ligar(app)" in fonte
    assert "clone.before_request(modelos_do_clone.canais_em_dia)" in fonte
