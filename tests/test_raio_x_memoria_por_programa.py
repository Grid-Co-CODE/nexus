"""Quem ocupa a memória da máquina, no Raio-X (20/10/2026). Raio-X das 14:17: 0,2 GB livres de 7,1 GB, 3,2 GB no swap
trocando 4,5 MB/s e algo esperando o disco 60% do tempo, com o Nexus em só 690 MB; o PDF das 13:45 ficou 1 min "trabalhando"
no desenho do logo (coisa de milissegundos). Levi escolheu ver no Raio-X quem ocupa os outros ~6 GB. Pelo /proc de cada
processo (só leitura, quando o Raio-X abre), somado por programa. Aqui o /proc é de mentira."""
import os

import pytest

from nexus.casca import raio_x as R

EU = os.getpid()                       # este processo é o Nexus


@pytest.fixture(autouse=True)
def _memoria_limpa(monkeypatch):
    """Os nomes guardados por processo e a última lista não passam de um teste para outro."""
    monkeypatch.setattr(R, "_ROTULOS", {}, raising=False)
    monkeypatch.setattr(R, "_MEMORIA", {"thread": None, "ultimo": None, "quando": None}, raising=False)


def _status(nome, anon_kb, shmem_kb=0, swap_kb=0):
    return (f"Name:\t{nome}\nVmRSS:\t{anon_kb + shmem_kb} kB\nRssAnon:\t{anon_kb} kB\nRssFile:\t9000 kB\n"
            f"RssShmem:\t{shmem_kb} kB\nVmSwap:\t{swap_kb} kB\n")


PROCS = {
    EU: (_status("python3", 600 * 1024, swap_kb=160 * 1024), "python3\0servir.py\0"),
    101: (_status("postgres", 50 * 1024, shmem_kb=400 * 1024, swap_kb=10 * 1024), "postgres: checkpointer\0"),
    102: (_status("postgres", 150 * 1024, shmem_kb=380 * 1024, swap_kb=20 * 1024), "postgres: app db 10.0.0.9\0"),
    103: (_status("postgres", 100 * 1024, shmem_kb=10 * 1024), "postgres: walwriter\0"),
    201: (_status("python3", 900 * 1024, swap_kb=1200 * 1024),
          "/usr/bin/python3\0/srv/PerformancePainel/plataforma/servir.py\0--senha=segredo-de-mentira\0"),
    202: (_status("python3", 80 * 1024), "python3\0-m\0http.server\0"),
    301: (_status("snapd", 30 * 1024, swap_kb=5 * 1024), "/usr/lib/snapd/snapd\0"),
    302: (_status("caddy", 40 * 1024), "caddy\0run\0"),
    303: (_status("gnome-shell", 200 * 1024, swap_kb=300 * 1024), "/usr/bin/gnome-shell\0"),
    304: (_status("Xorg", 60 * 1024), "/usr/lib/xorg/Xorg\0"),
    2: ("Name:\tkthreadd\n", ""),                                 # thread do kernel: sem memória própria
}


def _proc(monkeypatch, procs=PROCS):
    monkeypatch.setattr(R, "_pids", lambda: list(procs))

    def ler(nome):
        pid, _, arq = nome.partition("/")
        if pid.isdigit() and int(pid) in procs:
            return procs[int(pid)][0 if arq == "status" else 1]
        return ""
    monkeypatch.setattr(R, "_ler_proc", ler)


def test_soma_por_programa_com_a_memoria_compartilhada_uma_vez_so(monkeypatch):
    _proc(monkeypatch)
    q = R._quem_ocupa(teto=4)
    assert [(p["programa"], p["mem_mb"], p["swap_mb"], p["processos"]) for p in q["programas"]] == [
        ("python3 · plataforma/servir.py", 900, 1200, 1),
        ("Nexus (este processo)", 600, 160, 1),
        ("postgres", 300 + 400, 30, 3),            # a memória própria somada; os buffers compartilhados, uma vez só
        ("gnome-shell", 200, 300, 1)]
    assert (q["outros"], q["outros_mem_mb"], q["outros_swap_mb"]) == (4, 80 + 30 + 40 + 60, 5)


def test_a_linha_de_comando_nao_aparece(monkeypatch):
    """Do Python sai só o arquivo e a pasta dele (o Nexus e a plataforma são ambos python), nunca a linha inteira: ela
    pode ter senha. Dos outros programas, só o nome."""
    _proc(monkeypatch)
    nomes = " ".join(p["programa"] for p in R._quem_ocupa(teto=20)["programas"])
    assert "segredo" not in nomes and "/srv" not in nomes and "10.0.0.9" not in nomes
    assert "python3 · -m http.server" in nomes


def test_sem_o_proc_do_linux_nao_ha_lista(monkeypatch):
    monkeypatch.setattr(R, "_pids", lambda: [])
    assert R._quem_ocupa() is None


def _proc_preso(monkeypatch, solta):
    """O /proc com a linha de comando de um processo que não volta (a página dele está no swap) até `solta`."""
    _proc(monkeypatch)
    ler_ok = R._ler_proc

    def ler(nome):
        if nome.endswith("/cmdline"):
            solta.wait(10)
        return ler_ok(nome)
    monkeypatch.setattr(R, "_ler_proc", ler)


def test_o_proc_preso_nao_prende_o_raio_x(monkeypatch):
    """Raio-X das 16:16 de 20/10/2026: a máquina trocando com o disco e o Raio-X 4 min 18 s parado em `_ler_proc`. Ler a
    linha de comando de um processo que está no swap faz o kernel trazê-la do disco, e com o disco tomado ela não volta.
    A lista sai de uma thread à parte com prazo; enquanto aquela não voltar, nenhuma outra é aberta."""
    import threading
    import time
    solta = threading.Event()
    _proc_preso(monkeypatch, solta)
    monkeypatch.setattr(R, "_ROTULOS", {})
    monkeypatch.setattr(R, "_MEMORIA", {"thread": None, "ultimo": None, "quando": None})
    try:
        t0 = time.monotonic()
        q = R._memoria_por_programa(prazo_s=0.2)
        assert time.monotonic() - t0 < 2 and q["atrasado"] and q["anterior"] is None
        vivas = threading.active_count()
        assert R._memoria_por_programa(prazo_s=0.1)["atrasado"] and threading.active_count() == vivas   # nada de outra
    finally:
        solta.set()
    R._MEMORIA["thread"].join(5)
    q = R._memoria_por_programa(prazo_s=5)                             # o /proc voltou: a lista de novo
    assert not q.get("atrasado") and q["programas"][0]["programa"] == "python3 · plataforma/servir.py"


def test_a_linha_de_comando_e_lida_uma_vez_por_processo(monkeypatch):
    _proc(monkeypatch)
    lidas, ler_ok = [], R._ler_proc
    monkeypatch.setattr(R, "_ler_proc", lambda nome: (lidas.append(nome) if nome.endswith("/cmdline") else None)
                        or ler_ok(nome))
    monkeypatch.setattr(R, "_ROTULOS", {})
    R._quem_ocupa()
    n = len(lidas)
    assert n == 2 and R._quem_ocupa()["programas"][0]["programa"] == "python3 · plataforma/servir.py"
    assert len(lidas) == n                                              # a 2ª vez, do que já foi lido


def test_a_pagina_com_o_proc_preso_diz_isso_e_mostra_a_anterior(app, logado, monkeypatch):
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 13, "nucleos": 4, "carga": [3.08, 3.65, 3.79],
                                                                   "maquina": None})
    monkeypatch.setattr(R, "_memoria_por_programa", lambda prazo_s=R.PRAZO_MEMORIA_S: {
        "atrasado": True, "anterior_quando": "16:05:10",
        "anterior": {"programas": [{"programa": "python · worker.py", "mem_mb": 3277, "swap_mb": 391, "processos": 1}],
                     "outros": 0, "outros_mem_mb": 0, "outros_swap_mb": 0}})
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "O /proc não respondeu em 2 s" in h and "a lista das 16:05:10" in h and "python · worker.py" in h


def test_a_pagina_mostra_quem_ocupa_a_memoria(app, logado, monkeypatch):
    _proc(monkeypatch)
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 0, "nucleos": 4, "carga": [3.57, 3.13, 3.64],
                                                                   "maquina": None})
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "Quem ocupa a memória da máquina" in h
    assert "python3 · plataforma/servir.py" in h and "Nexus (este processo)" in h
    assert "E mais 2 programas: 70 MB de memória, 5 MB no swap" in h           # o teto da página é 6
    assert "segredo" not in h
