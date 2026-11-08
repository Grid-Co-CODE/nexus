"""O que o coletor aposentado do Campo (saiu do código em 08/11/2026) tinha de teste sobre a ligação ao cadastro e que
vale por si: o hífen sem espaço da usina e o código do App que vira pessoa_id (`cadastro/ligacao_campo.py`)."""
import json

from pg_falso import ApiPGFalsa

from nexus.cadastro import ligacao_campo as ligacao_cadastro
from nexus.cadastro.cifra import Cofre, gerar_chave

CHAVE = gerar_chave()


def test_hifen_sem_espaco_e_a_mesma_usina():
    m = {"usina": {ligacao_cadastro._norm("Thopen - Coração 1 - SC"): 7}, "pessoa": {}}
    assert ligacao_cadastro.usina_id(m, "Thopen - Coração 1- SC") == 7


def test_codigo_do_app_vira_pessoa_id():
    # o App (v226) manda a pessoa como HMAC do e-mail; o Nexus calcula o mesmo código para o e-mail do cadastro
    import hashlib as _h
    import hmac as _hm
    api = ApiPGFalsa()
    cofre = Cofre(CHAVE)
    api._id("cadastro_nexus", "pessoas")["linhas"] = [
        {"headers": ["pessoa_id", "excluido", "sensivel_cifrado"],
         "values": [17, "não", cofre.cifrar(json.dumps({"nome": "Ana", "email": "Ana@X.com"}), "banco/pessoas/17")]},
        {"headers": ["pessoa_id", "excluido", "sensivel_cifrado"],
         "values": [18, "não", cofre.cifrar(json.dumps({"nome": "Beto", "email": "beto@x.com"}), "banco/pessoas/18")]}]
    m = ligacao_cadastro.mapas({"GRIDCO_DB_API": "http://pg.falso", "NEXUS_CHAVE_CADASTRO": CHAVE,
                                        "NEXUS_PESSOA_HMAC": "k"}, api)
    do_app = _hm.new(b"k", b"ana@x.com", _h.sha256).hexdigest()[:24]          # o _pessoa_hmac do function_app.py
    assert ligacao_cadastro.pessoa_id_do_codigo(m, do_app) == 17
    assert ligacao_cadastro.pessoa_id_do_codigo(m, do_app + ";outro") == 17
    sem = ligacao_cadastro.mapas({"GRIDCO_DB_API": "http://pg.falso", "NEXUS_CHAVE_CADASTRO": CHAVE}, api)
    assert sem["hmac"] == {} and ligacao_cadastro.pessoa_id_do_codigo(sem, do_app) is None
