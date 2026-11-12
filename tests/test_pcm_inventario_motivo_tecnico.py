"""O motivo da recontagem chega ao técnico no App (12/11/2026, Levi: "O MOTIVO TEM QUE SUBIR PARA O TÉCNICO"; a pergunta
do PCM: "Quando eu peço a recontagem, o técnico consegue ver o motivo?").

O motivo já ia no `dados_cifrados` do `fato_evento_inventario`, mas cifrado com a NEXUS_CHAVE_CADASTRO, que abre CPF,
telefone e endereço e por isso nunca vai ao App. A cópia para o técnico é a coluna `motivo_tecnico`, a última do evento,
cifrada com uma chave derivada da NEXUS_PESSOA_HMAC (que o App já tem), só nos eventos `recontagem_pedida` e
`recontagem_item_pedida`. O contrato com o App (v342) está fechado e é provado aqui por um vetor fixo e por uma decifração
independente, escrita com o `cryptography` direto (o que o App faz). Dado de mentira: chave, IDs e motivos inventados."""
import base64
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pg_falso import ApiPGFalsa

from nexus.cadastro import cifra
from nexus.cadastro.cifra import gerar_chave
from nexus.dados import fato_inventario as F

BASE = "http://pg.falso"
CHAVE_HMAC = "chave-hmac-de-mentira-do-teste"
EVENTO = "ev-teste-0001"
MOTIVO = "caixa lacrada: conferir a prateleira 3 de novo"
NONCE = bytes(range(1, 13))
# o vetor fixo do contrato (a mesma conta que o App faz): a chave, o evento e o motivo acima, com o nonce 01..0c
VETOR = ("cf1:AQIDBAUGBwgJCgsMouCorjGGmilw8N3-ccz6xD9iqC8FqPR-6WpCvWXbEVobttnLs-R5kIpGEQKqnRZzjUnXtrEdynz__ynk9nY")
ALMOX = "900"
LIGADA = "de-para do Fracttal"


def _abrir_como_o_app(chave_hmac: str, evento_id: str, valor: str) -> str:
    """A decifração do App, escrita aqui à parte (sem nada do Nexus): HKDF-SHA256 da NEXUS_PESSOA_HMAC, sem sal, 32 bytes,
    info própria; AES-256-GCM com o AAD do evento; `cf1:` + base64url sem o `=` de (nonce de 12 + cifra com a tag)."""
    assert valor.startswith("cf1:")
    corpo = valor[4:]
    bruto = base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4))
    chave = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                 info=b"nexus-app-campo/motivo-recontagem/v1").derive(chave_hmac.encode("utf-8"))
    aad = f"almox/inventario/evento/{evento_id}/tecnico".encode("utf-8")
    return AESGCM(chave).decrypt(bruto[:12], bruto[12:], aad).decode("utf-8")


@pytest.fixture
def cfg(tmp_path):
    F.limpar()
    yield {"TESTING": True, "NEXUS_ALMOX_INVENTARIO_ARQUIVO": str(tmp_path / "inventario.json"),
           "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_PESSOA_HMAC": CHAVE_HMAC}
    F.limpar()


def _ev(tipo, **mais):
    return {"tipo": tipo, "contagem_id": "C-1", "id_almoxarifado": ALMOX, "usina_id": 7, "usina_ligada_por": LIGADA,
            **mais}


def _eventos(cfg):
    return F.ler(cfg, forcar=True)[F.ABA_EVENTO]


# ── a cifra do contrato ──────────────────────────────────────────────────────────────────────────────────────────────

def test_o_vetor_fixo_do_contrato(cfg, monkeypatch):
    """Com o nonce fixo, a cifra do Nexus é byte a byte a do vetor; a decifração independente (a do App) o lê; e o Nexus
    decifra o que cifrou."""
    monkeypatch.setattr(cifra.os, "urandom", lambda n: NONCE[:n])
    valor = F.motivo_para_o_tecnico(cfg, EVENTO, MOTIVO)
    assert valor == VETOR
    assert _abrir_como_o_app(CHAVE_HMAC, EVENTO, VETOR) == MOTIVO
    assert F.motivo_do_tecnico(cfg, {"evento_id": EVENTO, "motivo_tecnico": VETOR}) == MOTIVO


def test_a_cifra_e_amarrada_ao_evento_e_a_chave(cfg):
    """O AAD é o do evento: a cifra copiada para outro evento não abre (nem no App, nem no Nexus); a chave de outra
    instalação também não; e cada cifra tem o seu nonce (o mesmo motivo duas vezes não dá o mesmo texto)."""
    valor = F.motivo_para_o_tecnico(cfg, EVENTO, MOTIVO)
    assert valor.startswith("cf1:") and MOTIVO not in valor and valor != F.motivo_para_o_tecnico(cfg, EVENTO, MOTIVO)
    assert _abrir_como_o_app(CHAVE_HMAC, EVENTO, valor) == MOTIVO
    with pytest.raises(InvalidTag):
        _abrir_como_o_app(CHAVE_HMAC, "ev-outro", valor)
    with pytest.raises(InvalidTag):
        _abrir_como_o_app("outra-chave", EVENTO, valor)
    assert F.motivo_do_tecnico(cfg, {"evento_id": "ev-outro", "motivo_tecnico": valor}) == ""
    assert F.motivo_do_tecnico(dict(cfg, NEXUS_PESSOA_HMAC="outra-chave"), {"evento_id": EVENTO, "motivo_tecnico": valor}) == ""
    # a cifra do técnico NÃO é a do cadastro: o Cofre não a abre, e a chave do cadastro não entra na conta
    assert F.motivo_para_o_tecnico(dict(cfg, NEXUS_CHAVE_CADASTRO=gerar_chave()), EVENTO, MOTIVO) != valor
    assert _abrir_como_o_app(CHAVE_HMAC, EVENTO,
                             F.motivo_para_o_tecnico(dict(cfg, NEXUS_CHAVE_CADASTRO=""), EVENTO, MOTIVO)) == MOTIVO


def test_sem_a_chave_hmac_nao_ha_cifra(cfg):
    sem = dict(cfg, NEXUS_PESSOA_HMAC="")
    assert F.motivo_para_o_tecnico(sem, EVENTO, MOTIVO) is None
    assert F.motivo_para_o_tecnico({k: v for k, v in cfg.items() if k != "NEXUS_PESSOA_HMAC"}, EVENTO, MOTIVO) is None
    assert F.motivo_para_o_tecnico(cfg, EVENTO, "") is None and F.motivo_para_o_tecnico(cfg, EVENTO, "   ") is None
    assert F.motivo_do_tecnico(sem, {"evento_id": EVENTO, "motivo_tecnico": VETOR}) == ""


# ── a coluna no livro ────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_coluna_e_a_ultima_do_evento():
    assert F.CAB_EVENTO[-1] == "motivo_tecnico" and F.CAB_EVENTO[-2] == "usina_ligada_por"
    assert "motivo_tecnico" not in F.CAB_REGUA and "motivo_tecnico" not in F.CAB_CURADORIA
    assert F.TIPOS_MOTIVO_TECNICO == ("recontagem_pedida", "recontagem_item_pedida")


def test_a_coluna_so_nas_duas_recontagens(cfg):
    """Só a recontagem pedida (a contagem inteira) e a da peça levam o motivo ao técnico; os outros eventos com motivo
    (a peça tirada, o número corrigido) e a recontagem sem motivo ficam com a coluna vazia."""
    F.acrescentar(cfg, F.ABA_EVENTO, [
        _ev("peca_tirada", id_item="501", dados={"motivo": "da peça tirada"}),
        _ev("numero_corrigido", id_item="501", de_qtd=2, para_qtd=3, dados={"motivo": "do número corrigido"}),
        _ev("recontagem_pedida", dados={"motivo": "da contagem inteira"}),
        _ev("recontagem_item_pedida", id_item="502", dados={"motivo": "da peça 502"}),
        _ev("recontagem_item_pedida", id_item="503", dados={"motivo": ""}),
        _ev("recontagem_pedida", contagem_id="C-2"),
        _ev("contagem_recebida"),
    ])
    ev = _eventos(cfg)
    com = [(e["tipo"], e["contagem_id"], e.get("id_item")) for e in ev if e.get("motivo_tecnico")]
    assert com == [("recontagem_pedida", "C-1", None), ("recontagem_item_pedida", "C-1", "502")]
    assert F.motivo_do_tecnico(cfg, ev[2]) == "da contagem inteira"
    assert F.motivo_do_tecnico(cfg, ev[3]) == "da peça 502"
    assert _abrir_como_o_app(CHAVE_HMAC, ev[3]["evento_id"], ev[3]["motivo_tecnico"]) == "da peça 502"
    # o texto nunca em claro no livro
    bruto = Path(cfg["NEXUS_ALMOX_INVENTARIO_ARQUIVO"]).read_text(encoding="utf-8")
    assert "contagem inteira" not in bruto and "peça 502" not in bruto
    assert all("motivo_tecnico" in e for e in json.loads(bruto)[F.ABA_EVENTO])       # o arquivo ganha a coluna


def test_o_dados_cifrados_e_a_auditoria_nao_mudam(cfg):
    """A coluna nova é só a cópia para o técnico: o `dados_cifrados` segue no Cofre do cadastro, com o mesmo JSON."""
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("recontagem_item_pedida", id_item="502", dados={"motivo": "caixa vazia"})])
    e = _eventos(cfg)[0]
    assert F.decifrar(cfg, F.ABA_EVENTO, e) == {"motivo": "caixa vazia"}
    assert e["dados_cifrados"] != e["motivo_tecnico"]
    # o cadastro não abre a cópia do técnico, e a chave do técnico não abre o dados_cifrados
    assert F.decifrar(cfg, F.ABA_EVENTO, dict(e, dados_cifrados=e["motivo_tecnico"])) == {}
    assert F.motivo_do_tecnico(cfg, dict(e, motivo_tecnico=e["dados_cifrados"])) == ""


def test_motivo_tecnico_nao_se_passa_pronto(cfg):
    """Como o `dados_cifrados`: só o módulo cifra. Texto passado pronto nessa coluna iria em claro a uma API aberta."""
    with pytest.raises(ValueError, match="motivo_tecnico"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev("recontagem_pedida", motivo_tecnico="o motivo em claro",
                                              dados={"motivo": "x"})])
    with pytest.raises(ValueError, match="motivo_tecnico"):
        F.acrescentar(cfg, F.ABA_EVENTO, [_ev("recontagem_pedida", motivo_tecnico="cf1:parece-cifra")])
    assert _eventos(cfg) == []


def test_sem_a_chave_hmac_a_coluna_fica_vazia_e_a_gravacao_passa(cfg):
    sem = {k: v for k, v in cfg.items() if k != "NEXUS_PESSOA_HMAC"}
    F.acrescentar(sem, F.ABA_EVENTO, [_ev("recontagem_pedida", dados={"motivo": "sem a chave"})])
    e = _eventos(sem)[0]
    assert not e.get("motivo_tecnico") and F.decifrar(sem, F.ABA_EVENTO, e) == {"motivo": "sem a chave"}
    # gravar de novo sem a chave também passa (o retroativo não tem como cifrar e não quebra)
    F.acrescentar(sem, F.ABA_EVENTO, [_ev("contagem_recebida", contagem_id="C-2")])
    assert [x.get("motivo_tecnico") for x in _eventos(sem)] == [None, None]


# ── o retroativo ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_o_retroativo_preenche_o_antigo_e_nao_mexe_no_que_ja_tem(cfg):
    """O livro é trocado inteiro a cada gravação: na montagem, a recontagem antiga sem a coluna ganha a cópia (o motivo sai
    do `dados_cifrados`); a que já tem não é recifrada (o valor fica byte a byte), e o `dados_cifrados` de nenhuma muda."""
    sem = {k: v for k, v in cfg.items() if k != "NEXUS_PESSOA_HMAC"}
    F.acrescentar(sem, F.ABA_EVENTO, [_ev("recontagem_pedida", dados={"motivo": "pedida antes da coluna"}),
                                      _ev("peca_tirada", id_item="501", dados={"motivo": "não é recontagem"})])
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("recontagem_item_pedida", id_item="502", dados={"motivo": "já com a coluna"})])
    ev = _eventos(cfg)
    antigo, tirada, novo = ev
    assert F.motivo_do_tecnico(cfg, antigo) == "pedida antes da coluna"
    assert _abrir_como_o_app(CHAVE_HMAC, antigo["evento_id"], antigo["motivo_tecnico"]) == "pedida antes da coluna"
    assert not tirada.get("motivo_tecnico")
    assert F.motivo_do_tecnico(cfg, novo) == "já com a coluna"
    cifras = {e["evento_id"]: (e["motivo_tecnico"], e["dados_cifrados"]) for e in ev}
    # a gravação seguinte não recifra ninguém, e o dados_cifrados segue igual
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("contagem_recebida", contagem_id="C-3")])
    depois = {e["evento_id"]: (e.get("motivo_tecnico"), e["dados_cifrados"]) for e in _eventos(cfg)[:3]}
    assert depois == cifras


def test_o_retroativo_sem_a_chave_do_cadastro_fica_vazio(cfg):
    """O motivo antigo só sai do `dados_cifrados` com a chave do cadastro: sem ela (ou com a de outra instalação), a coluna
    segue vazia e a gravação passa."""
    sem = {k: v for k, v in cfg.items() if k != "NEXUS_PESSOA_HMAC"}
    F.acrescentar(sem, F.ABA_EVENTO, [_ev("recontagem_pedida", dados={"motivo": "antes"})])
    outra = dict(cfg, NEXUS_CHAVE_CADASTRO=gerar_chave())
    F.acrescentar(outra, F.ABA_EVENTO, [_ev("contagem_recebida", contagem_id="C-2")])
    assert not _eventos(cfg)[0].get("motivo_tecnico")
    F.acrescentar(cfg, F.ABA_EVENTO, [_ev("contagem_recebida", contagem_id="C-3")])
    assert F.motivo_do_tecnico(cfg, _eventos(cfg)[0]) == "antes"


def test_no_banco_a_coluna_nova_passa_pela_trava_e_pela_conferencia(app):
    """No banco (falso, devolvendo tudo como texto): o livro gravado sem a coluna ganha a coluna na gravação seguinte, sem
    disparar a trava do livro que só cresce (as linhas são as mesmas) nem a conferência de contagem do `publicar`; a
    qualidade conta as recontagens com e sem a cópia para o técnico."""
    api = ApiPGFalsa(como_texto=True)
    app.extensions["nexus_dados_sessao"] = api
    cfg = {"GRIDCO_DB_API": BASE, "GRIDCO_SQL_TOKEN": "tk", "NEXUS_CHAVE_CADASTRO": gerar_chave(),
           "NEXUS_PESSOA_HMAC": CHAVE_HMAC}
    sem = {k: v for k, v in cfg.items() if k != "NEXUS_PESSOA_HMAC"}
    F.limpar()
    try:
        with app.app_context():
            F.acrescentar(sem, F.ABA_EVENTO, [_ev("recontagem_pedida", dados={"motivo": "no banco, antes"}),
                                              _ev("recontagem_item_pedida", id_item="502", dados={"motivo": "outra"})])
            q = {l["fato"]: l for l in api.linhas(F.LIVRO, "qualidade")}["evento_inventario"]
            assert json.loads(q["extra"])["recontagem_sem_motivo_tecnico"] == 2
            F.limpar()
            F.acrescentar(cfg, F.ABA_EVENTO, [_ev("contagem_recebida", contagem_id="C-2")])
            ev = api.linhas(F.LIVRO, F.ABA_EVENTO)
            assert len(ev) == 3 and api.syncs == 2
            assert list(ev[0])[-1] == "motivo_tecnico"
            assert _abrir_como_o_app(CHAVE_HMAC, ev[0]["evento_id"], ev[0]["motivo_tecnico"]) == "no banco, antes"
            assert _abrir_como_o_app(CHAVE_HMAC, ev[1]["evento_id"], ev[1]["motivo_tecnico"]) == "outra"
            assert ev[2]["motivo_tecnico"] in (None, "")
            q = {l["fato"]: l for l in api.linhas(F.LIVRO, "qualidade")}["evento_inventario"]
            extra = json.loads(q["extra"])
            assert extra["recontagem_com_motivo_tecnico"] == 2 and "recontagem_sem_motivo_tecnico" not in extra
    finally:
        app.extensions.pop("nexus_dados_sessao", None)
        F.limpar()
