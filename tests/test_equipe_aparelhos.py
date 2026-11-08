"""Mapa de equipe: as chaves dos aparelhos (só o hash no banco) e quem é coletado. Nomes fictícios."""
import base64
import hashlib
from datetime import datetime, timezone

from nexus.campo.equipe import CAB_APARELHOS
from nexus.campo.equipe.aparelhos import Chaveiro, coleta_vale, piloto_atual

AGORA = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)


def _linhas(c):
    return [dict(zip(CAB_APARELHOS, l)) for l in c.eventos_novos()]


def test_a_chave_tem_32_bytes_e_o_banco_so_ve_o_hash():
    c = Chaveiro()
    chave = c.emitir(1, "aparelho-a", "nexus-field", AGORA)
    assert "=" not in chave and len(chave) == 43
    assert len(base64.urlsafe_b64decode(chave + "=")) == 32
    brutas = c.eventos_novos()
    ev = [dict(zip(CAB_APARELHOS, l)) for l in brutas]
    assert len(ev) == 1 and ev[0]["evento"] == "emitida"
    assert ev[0]["chave_hash"] == hashlib.sha256(chave.encode()).hexdigest()
    assert ev[0]["evento_id"].startswith("A") and len(ev[0]["evento_id"]) == 12
    assert ev[0]["data_id"] == 20261108
    assert ev[0]["instante"] == "2026-11-08T15:00:00Z"
    assert all(chave not in str(l) for l in brutas)
    assert c.quem(chave) == (1, "aparelho-a")


def test_a_chave_nova_do_mesmo_par_revoga_a_velha():
    c = Chaveiro()
    velha = c.emitir(1, "aparelho-a", "nexus-field", AGORA)
    nova = c.emitir(1, "aparelho-a", "nexus-field", AGORA)
    assert c.quem(velha) is None and c.quem(nova) == (1, "aparelho-a")
    assert [e["evento"] for e in _linhas(c)] == ["emitida", "revogada", "emitida"]


def test_outra_pessoa_no_mesmo_aparelho_tem_a_sua():
    c = Chaveiro()
    a = c.emitir(1, "aparelho-a", "nexus-field", AGORA)
    b = c.emitir(2, "aparelho-a", "nexus-field", AGORA)
    assert c.quem(a) == (1, "aparelho-a") and c.quem(b) == (2, "aparelho-a")


def test_revogar_e_sem_efeito_para_chave_desconhecida():
    c = Chaveiro()
    assert c.revogar("x" * 43, AGORA) is False
    assert c.revogar(None, AGORA) is False
    assert c.eventos_novos() == []
    chave = c.emitir(1, "aparelho-a", "nexus-field", AGORA)
    c.eventos_novos()
    assert c.revogar(chave, AGORA) is True and c.quem(chave) is None
    assert [e["evento"] for e in _linhas(c)] == ["revogada"]
    assert c.quem(None) is None and c.quem(123) is None and c.quem("") is None


def test_eventos_novos_entrega_cada_evento_uma_vez():
    c = Chaveiro()
    c.emitir(1, "aparelho-a", "nexus-field", AGORA)
    assert len(c.eventos_novos()) == 1 and c.eventos_novos() == []


def test_carregar_reconstroi_as_ativas():
    c = Chaveiro()
    k1 = c.emitir(1, "aparelho-a", "nexus-field", AGORA)
    k2 = c.emitir(2, "aparelho-b", "nexus-field", AGORA)
    c.revogar(k2, AGORA)
    eventos = _linhas(c)
    # o API devolve tudo como texto e fora de ordem
    eventos = [{k: str(v) for k, v in e.items()} for e in reversed(eventos)]
    novo = Chaveiro()
    novo.carregar(eventos)
    assert novo.quem(k1) == (1, "aparelho-a") and novo.quem(k2) is None
    assert novo.eventos_novos() == []


def test_piloto_atual_vale_a_ultima_decisao_de_cada_tecnico():
    d = [{"pessoa_id": "1", "instante": "2026-11-08T10:00:00Z", "no_piloto": "1"},
         {"pessoa_id": 1, "instante": "2026-11-08T11:00:00Z", "no_piloto": "0"},
         {"pessoa_id": 2, "instante": "2026-11-08T10:00:00Z", "no_piloto": True},
         {"pessoa_id": 3, "instante": "2026-11-08T10:00:00Z", "no_piloto": "true"},
         {"pessoa_id": 4, "instante": "2026-11-08T10:00:00Z", "no_piloto": 0},
         {"pessoa_id": 5, "instante": "2026-11-08T10:00:00Z", "no_piloto": 1},
         {"pessoa_id": 5, "instante": "2026-11-08T10:00:00Z", "no_piloto": 0}]  # empate: vale a ordem dada
    assert piloto_atual(d) == {2, 3}
    assert piloto_atual([]) == set()


def test_coleta_so_para_tecnico_ativo_e_no_piloto():
    tecnicos = {1: {"nome": "Ana"}, 2: {"nome": "Bia"}}
    assert coleta_vale(1, tecnicos, {1}) is True
    assert coleta_vale(2, tecnicos, {1}) is False      # técnico fora do piloto
    assert coleta_vale(3, tecnicos, {3}) is False      # no piloto, mas fora do cadastro/desligado/não técnico
    assert coleta_vale(1, tecnicos, set()) is False    # piloto vazio: ninguém
    assert coleta_vale(1, {}, {1}) is False
