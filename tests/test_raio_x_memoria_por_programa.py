"""Quem ocupa a memória da máquina, no Raio-X (20/10/2026). Raio-X das 14:17: 0,2 GB livres de 7,1 GB, 3,2 GB no swap
trocando 4,5 MB/s e algo esperando o disco 60% do tempo, com o Nexus em só 690 MB; o PDF das 13:45 ficou 1 min "trabalhando"
no desenho do logo (coisa de milissegundos). Levi escolheu ver no Raio-X quem ocupa os outros ~6 GB. Pelo /proc de cada
processo (só leitura, quando o Raio-X abre), somado por programa. Aqui o /proc é de mentira."""
import os

from nexus.casca import raio_x as R

EU = os.getpid()                       # este processo é o Nexus


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


def test_a_pagina_mostra_quem_ocupa_a_memoria(app, logado, monkeypatch):
    _proc(monkeypatch)
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 0, "nucleos": 4, "carga": [3.57, 3.13, 3.64],
                                                                   "maquina": None})
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "Quem ocupa a memória da máquina" in h
    assert "python3 · plataforma/servir.py" in h and "Nexus (este processo)" in h
    assert "E mais 2 programas: 70 MB de memória, 5 MB no swap" in h           # o teto da página é 6
    assert "segredo" not in h
