"""A memória e o disco da máquina no Raio-X (20/10/2026). Raio-X das 10:08: o `GET /os/` estava há 18 s numa cópia que
leva 17 ms, com o processador do Nexus a 13% e a carga da máquina em 2,5 a 3,9 (4 núcleos): a máquina engasgava em
outra coisa, e a página não dizia o quê (a carga do Linux soma quem espera o disco). Agora diz, pelo /proc do Linux:
o processador da máquina inteira e o tempo esperando o disco na mesma janela de 1 s, a memória livre, o swap em uso e
se está trocando agora, o quanto o Nexus ocupa e, havendo a PSI do kernel, o tempo com algo parado esperando memória ou
disco. Levi: "Se não for causar nenhum gargalo na operação pode aplicar": são leituras de arquivos do /proc, só quando
o Raio-X abre. Aqui o /proc é de mentira."""
from nexus.casca import raio_x as R

STAT_ANTES = "cpu  1000 0 500 8000 500 0 0 0 0 0\ncpu0 1 2 3 4 5 6 7 8 9 10\n"
STAT_DEPOIS = "cpu  1100 0 550 8150 700 0 0 0 0 0\n"           # 500 a mais: 150 ocupado, 150 ocioso, 200 no disco
VM_ANTES, VM_DEPOIS = "pswpin 100\npswpout 200\nnr_free_pages 9\n", "pswpin 400\npswpout 468\n"   # 568 páginas
MEMINFO = ("MemTotal:        3984588 kB\nMemFree:          100000 kB\nMemAvailable:     419430 kB\n"
           "SwapTotal:       2097148 kB\nSwapFree:         838860 kB\n")
STATUS = "Name:\tpython\nVmRSS:\t  665600 kB\nVmSwap:\t  102400 kB\n"
PSI_MEM = "some avg10=12.50 avg60=8.00 avg300=3.00 total=123\nfull avg10=5.00 avg60=1.00 avg300=0.50 total=9\n"
PSI_IO = "some avg10=30.10 avg60=20.00 avg300=9.00 total=456\nfull avg10=20.00 avg60=1.00 avg300=0.50 total=9\n"


def _proc(monkeypatch, psi=True):
    fila = {"stat": [STAT_ANTES, STAT_DEPOIS], "vmstat": [VM_ANTES, VM_DEPOIS]}
    fixos = {"meminfo": MEMINFO, "self/status": STATUS, "pressure/memory": PSI_MEM if psi else "",
             "pressure/io": PSI_IO if psi else ""}

    def ler(nome):
        if nome in fila:
            return fila[nome].pop(0) if fila[nome] else ""
        return fixos.get(nome, "")
    monkeypatch.setattr(R, "_ler_proc", ler)


def test_le_o_processador_o_disco_e_a_memoria_da_maquina(monkeypatch):
    _proc(monkeypatch)
    m = R._processador(janela_s=0)["maquina"]
    assert (m["ocupado"], m["disco"]) == (30, 40)
    assert (m["livre_gb"], m["total_gb"], m["swap_gb"], m["tem_swap"]) == ("0,4", "3,8", "1,2", True)
    assert (m["nexus_mb"], m["nexus_swap_mb"]) == (650, 100)
    assert (m["pressao_mem"], m["pressao_io"]) == (12.5, 30.1)


def test_troca_de_swap_por_segundo():
    s0, s1 = R._cpu_da_maquina(STAT_ANTES), R._cpu_da_maquina(STAT_DEPOIS)
    v0, v1 = R._vmstat(VM_ANTES), R._vmstat(VM_DEPOIS)
    assert R._troca_mb_s(v0, v1, 2.0) == "1,1"                     # 568 páginas de 4 KB em 2 s
    assert R._troca_mb_s(v0, v0, 1.0) == "0" and s1[0] - s0[0] == 500


def test_sem_o_proc_do_linux_nao_mostra(monkeypatch):
    monkeypatch.setattr(R, "_ler_proc", lambda nome: "")
    assert R._processador(janela_s=0)["maquina"] is None


def test_sem_a_psi_do_kernel_o_resto_aparece(monkeypatch):
    _proc(monkeypatch, psi=False)
    m = R._processador(janela_s=0)["maquina"]
    assert m["pressao_mem"] is None and m["pressao_io"] is None and m["livre_gb"] == "0,4"


def test_a_pagina_mostra_a_memoria_e_a_espera_do_disco(app, logado, monkeypatch):
    _proc(monkeypatch)
    cpu = R._processador(janela_s=0)
    cpu["maquina"]["trocando_mb_s"] = "3,0"
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: dict(cpu, pct=13, nucleos=4, carga=[2.51, 2.87, 3.91]))
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "Memória da máquina" in h and "0,4 GB livres" in h and "de 3,8 GB" in h
    assert "swap 1,2 GB em uso, trocando 3,0 MB/s agora" in h and "o Nexus usa 650 MB, 100 MB dele no swap" in h
    assert "processador da máquina 30%, esperando o disco 40%" in h
    assert "esperando memória 12,5% e disco 30,1% do tempo" in h


def test_a_pagina_sem_o_linux_fica_como_era(app, logado, monkeypatch):
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 37, "nucleos": 4, "carga": None})
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "Memória da máquina" not in h and "(só no Linux)" in h
