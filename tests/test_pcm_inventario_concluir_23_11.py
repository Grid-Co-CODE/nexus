"""O "Concluir sem alteração" do inventário (23/11/2026, `gravacao.concluir`, a ponte `/os/_nexus/inventario/<id>/concluir`).

O PCM, 23/11/2026: "quando a usina não tem, não foi feita a contagem [...] Quando eu vou aí revisar lote, ele não me deixa
salvar, gravar zero alterações [...] se você puder ver essa parte de eu salvar mesmo com a usina zerada". A contagem em que
nenhuma peça mexe no estoque ficava para sempre "a revisar": o "Gravar 0 alterações" vinha desligado. Agora o rodapé do lote
traz o "Concluir sem alteração": confere o lote de agora (o saldo lido na hora, como no Gravar) e grava UM evento
`contagem_concluida` no livro do inventário. Nada vai ao Fracttal. A contagem fica "Concluída sem alteração", conta como a
última contagem do almoxarifado e não se revisa mais.

O que estes testes seguram: o estado pelos eventos, a conclusão pela ponte (o evento, nenhum pedido de gravação ao
Fracttal, o estado), as recusas (o lote com peça que mexe, a curadoria por decidir, o lote que mudou, quem não pode, a já
concluída) e o botão no rodapé do lote. Dado de mentira, sem nome de gente."""
import re
from datetime import timedelta, timezone

from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_pcm_inventario_gravacao import PONTE, _cookie_os, _visto, grav, ponte_falsa  # noqa: F401  (fixtures)
from test_pcm_inventario_leitura import AGORA, _linha, _publicar, inv  # noqa: F401  (inv é fixture)
from test_pcm_inventario_telas import _cenario, _pcm

from nexus.cadastro import setor_ids as SID
from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import leitura as L

CONTADA = (AGORA.astimezone(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sem_alteracao(inv):  # noqa: F811
    """A C-1 do cenário das telas trocada por uma em que nada mexe: a 504 contada igual ao sistema (7) e a 505 em branco."""
    _cenario(inv)
    _publicar(inv, _linha("C-1", "L1", "504", "7", contada=CONTADA), _linha("C-1", "L2", "505", "", contada=CONTADA))


def _eventos(app, tipo=None):
    return [e for e in F.ler(app.config, forcar=True)[F.ABA_EVENTO] if tipo is None or e["tipo"] == tipo]


def _contagem(app, cid="C-1"):
    return next(c for c in L.contagens(app.config) if c["contagem_id"] == cid)


def test_o_estado_concluida_pelos_eventos():
    assert "contagem_concluida" in F.TIPOS_EVENTO
    assert "concluida" in L.ESTADOS and "concluida" in L.DA_GRAVACAO and "concluida" not in L.REVISAVEIS
    assert L.estado_dos_eventos([{"tipo": "contagem_concluida"}]) == "concluida"
    assert L.estado_dos_eventos([{"tipo": "peca_tirada"}, {"tipo": "contagem_concluida"}]) == "concluida"


def test_concluir_sem_alteracao_pela_ponte(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    _sem_alteracao(inv)
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    visto = _visto(app, ponte_falsa["falso"])
    assert visto["n"] == 0
    html = c.get(f"{PONTE}/C-1/lote").get_data(as_text=True)
    assert re.search(r'<button[^>]*\bdata-concluir="/os/_nexus/inventario/C-1/concluir"[^>]*>\s*Concluir sem alteração', html)
    assert 'data-gravar="' not in html
    r = c.post(f"{PONTE}/C-1/concluir", json=visto)
    assert r.status_code == 200 and r.get_json()["ok"] is True, r.get_json()
    ev = _eventos(app, "contagem_concluida")
    assert len(ev) == 1 and ev[0]["contagem_id"] == "C-1" and str(ev[0]["id_almoxarifado"]) == "10"
    assert _eventos(app, "aprovada") == [] and ponte_falsa["falso"].chamadas.count("abrir_ajuste") == 0
    cont = _contagem(app)
    assert cont["estado"] == "concluida" and not cont["aprovavel"]
    assert cont["motivo_nao_aprovavel"] == "concluída sem alteração"
    # concluída uma vez, não se conclui de novo nem se revisa
    r = c.post(f"{PONTE}/C-1/concluir", json=visto)
    assert r.status_code == 409 and len(_eventos(app, "contagem_concluida")) == 1


def test_concluir_recusa_o_lote_que_mexe_no_estoque(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    """A C-1 inteira do cenário tem 5 peças que mexem: concluir sem gravar deixaria o Fracttal sem o que foi contado."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    visto = _visto(app, ponte_falsa["falso"])
    assert visto["n"] == 5
    r = c.post(f"{PONTE}/C-1/concluir", json=visto)
    assert r.status_code == 409 and "mexem no estoque" in r.get_json()["erro"]
    assert _eventos(app) == []


def test_concluir_recusa_a_curadoria_por_decidir(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    """O achado fora do catálogo é decisão do PCM: concluída a contagem, ele sumiria da curadoria sem ninguém decidir."""
    _cenario(inv)
    _publicar(inv, _linha("C-1", "L1", "504", "7", contada=CONTADA),
              _linha("C-1", "L2", "", "2", tipo="fora_do_catalogo", contada=CONTADA, Descrição="peça sem etiqueta"))
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    visto = _visto(app, ponte_falsa["falso"])
    r = c.post(f"{PONTE}/C-1/concluir", json=visto)
    assert r.status_code == 409 and "curadoria" in r.get_json()["erro"]
    assert _eventos(app) == []


def test_concluir_recusa_lote_mudado_e_quem_nao_pode(app, inv, ponte_falsa, monkeypatch):  # noqa: F811
    _sem_alteracao(inv)
    falso = ponte_falsa["falso"]
    visto = _visto(app, falso)
    outro = _pcm(app, monkeypatch, setor=SID.PERFORMANCE)
    _cookie_os(app, outro)
    assert outro.post(f"{PONTE}/C-1/concluir", json=visto).status_code == 403
    c = _pcm(app, monkeypatch)
    _cookie_os(app, c)
    assert c.post(f"{PONTE}/C-1/concluir", json=visto, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert c.post(f"{PONTE}/C-1/concluir", json={"n": 0}).status_code == 400
    falso.mover("10", "504", "entrada", 1, quando="2026-10-20T12:00:00Z")     # 7 → 8: a 504 passa a descer
    r = c.post(f"{PONTE}/C-1/concluir", json=visto)
    assert r.status_code == 409 and "recarregue" in r.get_json()["erro"]
    assert c.post(f"{PONTE}/C-9/concluir", json=visto).status_code == 404
    assert _eventos(app) == []
