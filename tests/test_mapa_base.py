"""O mapa base do Brasil do Mapa de equipe (11/11/2026; `nexus/campo/equipe/mapa_base.py`).

Levi, 11/11/2026, com o guia e a prévia do Willian: "Quero que utilize essa referência para completar nosso mapa" — o mapa
de verdade (ruas, rodovias, cidades) no lugar do desenho dos estados, com três condições: sem 3D, só o Brasil e no estilo
do Nexus. O mapa base é NOSSO (nenhum bloco de terceiro vê o que o COS olha): um arquivo PMTiles do Brasil (2,39 GB,
recortado pela `ferramentas/mapa_base_brasil.py`), que sobe pelo próprio Nexus em partes de 8 MB (escolha do Levi: "Upload
pelo Nexus") e é servido por pedaço (HTTP Range) só a quem entrou.

Arquivos falsos, pasta de dados temporária; nada vai à rede."""
import hashlib
import struct

import pytest

from nexus.campo.equipe import mapa_base as MB

URL = "/t/base/mapa-base"
BLOCOS = "/t/campo/equipe/mapa-base.pmtiles"


def _pmtiles(tamanho=40_000) -> bytes:
    """Um PMTiles falso coerente: o cabeçalho de 127 bytes com as faixas dentro do arquivo, blocos MVT, zoom 0 a 14."""
    raiz, meta, folhas = 127, 600, 1000
    dados = 2000
    cab = b"PMTiles" + bytes([3]) + struct.pack(
        "<QQQQQQQQQQQ", raiz, 400, meta, 300, folhas, 900, dados, tamanho - dados, 10, 8, 6)
    cab += bytes([1, 2, 2, 1, 0, 14]) + struct.pack("<iiii", -740000000, -340000000, -284000000, 59000000)
    cab += bytes([4]) + struct.pack("<ii", -520000000, -145000000)
    assert len(cab) == 127
    return cab + bytes(tamanho - 127)


@pytest.fixture
def dados(app, tmp_path):
    # o administrador é o da lista do servidor: o `admin` da sessão segue a NEXUS_ADMINS a cada pedido
    app.config.update(NEXUS_DADOS=str(tmp_path / "dados"), NEXUS_ADMINS="admin.teste@gridco.com.br")
    return tmp_path / "dados"


def _entrar(cliente, admin=True):
    with cliente.session_transaction() as s:
        s["logado"], s["admin"] = True, admin
        s["usuario"] = {"email": "admin.teste@gridco.com.br" if admin else "outra.pessoa@gridco.com.br",
                        "nome": "Pessoa de Teste", "perfil": ""}
    return cliente


def _subir(cliente, corpo: bytes, parte=MB.PARTE_MAX, sha=True):
    r = cliente.post(f"{URL}/iniciar", json={"tamanho": len(corpo), "sha256": hashlib.sha256(corpo).hexdigest()
                                             if sha else ""})
    assert r.status_code == 200, r.get_data(as_text=True)
    for ini in range(0, len(corpo), parte):
        pedaco = corpo[ini:ini + parte]
        r = cliente.post(f"{URL}/parte", query_string={"offset": ini}, data=pedaco,
                         headers={"Content-Type": "application/octet-stream",
                                  "X-Sha256": hashlib.sha256(pedaco).hexdigest()})
        assert r.status_code == 200, r.get_data(as_text=True)
    return cliente.post(f"{URL}/concluir")


def test_sem_o_mapa_base_os_blocos_dizem_404(cliente, dados):
    r = _entrar(cliente).get(BLOCOS)
    assert r.status_code == 404 and "mapa base" in r.get_data(as_text=True).lower()
    assert MB.estado(cliente.application.config)["pronto"] is None


def test_o_upload_em_partes_poe_o_mapa_no_ar_e_os_blocos_saem_por_pedaco(cliente, dados):
    """O arquivo sobe em partes (cada uma conferida pelo SHA-256 dela), é conferido inteiro no fim (o SHA-256 que a
    ferramenta imprimiu, o cabeçalho do PMTiles e as faixas dentro do tamanho) e só então troca o que estava no ar. Os
    blocos saem por pedaço (206), como o MapLibre pede."""
    corpo = _pmtiles()
    r = _subir(_entrar(cliente), corpo, parte=16_384)
    assert r.status_code == 200, r.get_data(as_text=True)
    e = MB.estado(cliente.application.config)
    assert e["pronto"]["tamanho"] == len(corpo) and e["pronto"]["sha256"] == hashlib.sha256(corpo).hexdigest()
    assert e["parcial"] is None and (dados / "mapa" / MB.NOME).read_bytes() == corpo
    r = cliente.get(BLOCOS, headers={"Range": "bytes=0-6"})
    assert r.status_code == 206 and r.data == b"PMTiles"
    assert r.headers["Content-Range"] == f"bytes 0-6/{len(corpo)}"
    r = cliente.get(BLOCOS, headers={"Range": "bytes=2000-2009"})
    assert r.status_code == 206 and r.data == corpo[2000:2010]
    # a tela diz o que está no ar
    html = cliente.get(URL).get_data(as_text=True)
    assert hashlib.sha256(corpo).hexdigest() in html and "No ar" in html


def test_so_o_administrador_sobe_e_so_quem_entrou_le(cliente, dados):
    _entrar(cliente, admin=False)
    assert cliente.get(URL).status_code == 403
    assert cliente.post(f"{URL}/iniciar", json={"tamanho": 10_000, "sha256": ""}).status_code == 403
    with cliente.session_transaction() as s:
        s.clear()
    assert cliente.get(BLOCOS).status_code in (302, 401, 403)


def test_parte_fora_de_ordem_ou_com_hash_errado_e_recusada(cliente, dados):
    corpo = _pmtiles()
    _entrar(cliente)
    assert cliente.post(f"{URL}/iniciar", json={"tamanho": len(corpo), "sha256": ""}).status_code == 200
    ok = {"Content-Type": "application/octet-stream"}
    r = cliente.post(f"{URL}/parte", query_string={"offset": 100}, data=corpo[100:200],
                     headers={**ok, "X-Sha256": hashlib.sha256(corpo[100:200]).hexdigest()})
    assert r.status_code == 409 and r.get_json()["recebido"] == 0          # a próxima parte é a do 0
    r = cliente.post(f"{URL}/parte", query_string={"offset": 0}, data=corpo[:100], headers={**ok, "X-Sha256": "0" * 64})
    assert r.status_code == 400
    r = cliente.post(f"{URL}/parte", query_string={"offset": 0}, data=corpo[:100],
                     headers={**ok, "X-Sha256": hashlib.sha256(corpo[:100]).hexdigest()})
    assert r.status_code == 200 and r.get_json()["recebido"] == 100
    # o reinício do mesmo arquivo continua de onde parou (a página do upload retoma)
    r = cliente.post(f"{URL}/iniciar", json={"tamanho": len(corpo), "sha256": ""})
    assert r.get_json()["parcial"]["recebido"] == 100
    # o fim antes da hora não troca nada
    assert cliente.post(f"{URL}/concluir").status_code == 409


def test_arquivo_que_nao_e_pmtiles_ou_com_outro_hash_nao_substitui_o_que_esta_no_ar(cliente, dados):
    bom = _pmtiles()
    assert _subir(_entrar(cliente), bom).status_code == 200
    ruim = b"isto nao e um pmtiles" + bytes(30_000)
    r = _subir(cliente, ruim, sha=False)
    assert r.status_code == 400 and "PMTiles" in r.get_json()["erro"]
    outro = _pmtiles(50_000)
    cliente.post(f"{URL}/iniciar", json={"tamanho": len(outro), "sha256": "a" * 64})
    cliente.post(f"{URL}/parte", query_string={"offset": 0}, data=outro,
                 headers={"Content-Type": "application/octet-stream", "X-Sha256": hashlib.sha256(outro).hexdigest()})
    r = cliente.post(f"{URL}/concluir")
    assert r.status_code == 400 and "SHA-256" in r.get_json()["erro"]
    assert (dados / "mapa" / MB.NOME).read_bytes() == bom                  # o que estava no ar continua


def test_sem_espaco_no_disco_o_upload_nem_comeca(cliente, dados, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(10, 9, 1))
    r = _entrar(cliente).post(f"{URL}/iniciar", json={"tamanho": 2_400_000_000, "sha256": ""})
    assert r.status_code == 507 and "espaço" in r.get_json()["erro"]


def test_parte_maior_que_o_teto_e_recusada(cliente, dados):
    _entrar(cliente).post(f"{URL}/iniciar", json={"tamanho": MB.PARTE_MAX * 3, "sha256": ""})
    grande = bytes(MB.PARTE_MAX + 1)
    r = cliente.post(f"{URL}/parte", query_string={"offset": 0}, data=grande,
                     headers={"Content-Type": "application/octet-stream", "X-Sha256": hashlib.sha256(grande).hexdigest()})
    assert r.status_code == 413
