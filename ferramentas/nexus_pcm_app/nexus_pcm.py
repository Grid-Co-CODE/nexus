"""Nexus PCM: o aplicativo que gera a programação semanal no computador de uma pessoa do PCM (27/11/2026).

Por quê: no servidor, o motor do PCM roda dentro do teto de memória do Nexus, e a geração da W49 morreu quatro vezes
(o serviço inteiro caía). Levi, 27/11/2026: "roda a programação semanal no computador dela e aí salva no Nexus"; "tem que
ser algo bem feito"; o computador de fora não tem `.env`, então as chaves vêm do Nexus.

Como funciona (o lado do Nexus é `nexus/pcm/geracao_pc.py`):
1. A pessoa cola UMA vez o código do computador (Nexus → PCM → Gerar a semana → Gerar no PC → Ligar um computador). O código
   fica guardado cifrado pelo Windows (DPAPI, só este usuário deste computador o abre).
2. "Gerar a semana": o Nexus abre a rodada e manda o pacote (os insumos, o motor e o adaptador da FAMA) e as chaves do
   Fracttal, que ficam só na memória. Com OS da FAMA, o Fracttal é lido antes, as OS da FAMA entram no cache e o motor
   roda com ele (o MESMO caminho do servidor, `fama_motor.antes_do_motor`).
3. A planilha e o log voltam ao Nexus, que termina a rodada (conferência, comparação, Publicar no App).

O mesmo arquivo é o motor quando chamado com `--motor <script>` ou `--pre-leitura <pasta>`: empacotado (PyInstaller), o
`sys.executable` é o próprio .exe, e o motor roda num processo separado dele.

Uso em desenvolvimento: `python nexus_pcm.py`. O .exe: `python construir.py` (nesta pasta).
"""
from __future__ import annotations

import base64
import ctypes
import io
import json
import os
import queue
import runpy
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
import zipfile
from ctypes import wintypes
from pathlib import Path

VERSAO = "1.0.0"
PREFIXO = "NXPCM1."
NOME = "Nexus PCM"


# ── o motor no processo filho (antes de qualquer janela) ───────────────────────────────────────────────────────────────
def _como_motor(argv: list[str]) -> bool:
    """`--motor <script> [args]` roda o motor; `--pre-leitura <pasta do motor>` lê o Fracttal como o motor (a FAMA)."""
    if len(argv) >= 3 and argv[1] in ("--motor", "--pre-leitura") and sys.stdout is None:
        # o .exe de janela (sem console) começa sem stdout: o print do motor vai ao log da rodada (`PCM_APP_LOG`)
        destino = os.environ.get("PCM_APP_LOG")
        f = open(destino, "a", encoding="utf-8", buffering=1) if destino else open(os.devnull, "w")
        sys.stdout = sys.stderr = f
    if len(argv) >= 3 and argv[1] == "--motor":
        script = Path(argv[2])
        sys.path.insert(0, str(script.parent))
        sys.argv = [str(script)] + argv[3:]
        runpy.run_path(str(script), run_name="__main__")
        return True
    if len(argv) >= 3 and argv[1] == "--pre-leitura":
        sys.path.insert(0, argv[2])
        import fonte_bd_api  # noqa: F401 — o leitor do motor, da pasta do pacote
        fonte_bd_api.df_semanal()
        print("[FAMA] o Fracttal foi lido antes do motor (a mesma leitura dele)", flush=True)
        return True
    return False


def _ancoras():  # pragma: no cover — nunca roda: diz ao PyInstaller o que o motor importa (ele vem no pacote, à parte)
    import argparse, ast, concurrent.futures, hashlib, math, pickle, re, unicodedata, uuid  # noqa: F401,E401
    import openpyxl, pandas, requests  # noqa: F401,E401
    import numpy  # noqa: F401


# ── o código guardado cifrado pelo Windows (DPAPI) ─────────────────────────────────────────────────────────────────────
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(dados: bytes, cifrar: bool) -> bytes:
    entrada = _Blob(len(dados), ctypes.cast(ctypes.create_string_buffer(dados, len(dados)), ctypes.POINTER(ctypes.c_char)))
    saida = _Blob()
    f = ctypes.windll.crypt32.CryptProtectData if cifrar else ctypes.windll.crypt32.CryptUnprotectData
    if not f(ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(saida)):
        raise OSError("o Windows não abriu o código guardado")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(saida.pbData)


def _pasta() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "NexusPCM"
    base.mkdir(parents=True, exist_ok=True)
    return base


def guardar_codigo(cod: str) -> None:
    (_pasta() / "conexao.bin").write_bytes(_dpapi(cod.encode("utf-8"), True))


def ler_codigo() -> str | None:
    p = _pasta() / "conexao.bin"
    try:
        return _dpapi(p.read_bytes(), False).decode("utf-8")
    except (OSError, ValueError):
        return None


def esquecer_codigo() -> None:
    try:
        (_pasta() / "conexao.bin").unlink()
    except OSError:
        pass


def abrir_codigo(cod: str) -> tuple[str, str]:
    """(o endereço do Nexus, a chave) do código colado; ValueError se não for um código do Nexus PCM."""
    cod = "".join(str(cod or "").split())
    if not cod.startswith(PREFIXO):
        raise ValueError("Esse não é um código do Nexus PCM. Copie de novo pela tela Gerar a semana.")
    b = cod[len(PREFIXO):]
    try:
        d = json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))
        return str(d["u"]).rstrip("/"), str(d["k"])
    except (ValueError, KeyError, TypeError):
        raise ValueError("O código veio cortado. Copie de novo pela tela Gerar a semana.") from None


# ── a conversa com o Nexus ─────────────────────────────────────────────────────────────────────────────────────────────
class ErroNexus(RuntimeError):
    def __init__(self, msg: str, desligado: bool = False):
        super().__init__(msg)
        self.desligado = desligado      # o Nexus não reconhece mais a chave (o código foi desligado)


class Nexus:
    def __init__(self, url: str, chave: str):
        import requests
        self.url, self.s = url, requests.Session()
        self.s.headers.update({"Authorization": "Bearer " + chave, "User-Agent": f"NexusPCM/{VERSAO}"})

    def _pedir(self, metodo: str, rota: str, **kw):
        import requests
        try:
            r = self.s.request(metodo, self.url + rota, timeout=kw.pop("timeout", 120), **kw)
        except requests.RequestException as ex:
            raise ErroNexus(f"Sem conexão com o Nexus ({type(ex).__name__}). Confira a internet e tente de novo.") from ex
        if r.status_code == 401:
            raise ErroNexus("O Nexus não reconheceu este computador: o código foi desligado. Peça um código novo.",
                            desligado=True)
        if r.status_code >= 400:
            try:
                msg = r.json().get("erro")
            except ValueError:
                msg = None
            raise ErroNexus(msg or f"O Nexus respondeu {r.status_code}.")
        return r

    def ola(self) -> dict:
        return self._pedir("GET", "/t/pcm/pc/ola").json()

    def rodada(self, semana: str) -> dict:
        # a preparação lê o banco (histórico, cadastro, FAMA): logo depois de o Nexus reiniciar ela passou de 5 min (a prova
        # de 27/11/2026, às 13:09, com o servidor recém-subido); 15 min de espera
        return self._pedir("POST", "/t/pcm/pc/rodada", json={"semana": semana}, timeout=900).json()

    def pacote(self, rid: str) -> bytes:
        return self._pedir("GET", f"/t/pcm/pc/rodada/{rid}/pacote", timeout=300).content

    def credencial(self) -> dict:
        return self._pedir("GET", "/t/pcm/pc/credencial").json()

    def andamento(self, rid: str, etapa: str) -> None:
        try:
            self._pedir("POST", f"/t/pcm/pc/rodada/{rid}/andamento", json={"etapa": etapa}, timeout=30)
        except ErroNexus:
            pass                      # o andamento é só para a tela do Nexus: não derruba a rodada

    def entregar(self, rid: str, planilha: Path | None, log: Path, relato: dict) -> dict:
        arquivos = {"log": ("log_motor.txt", log.read_bytes() if log.exists() else b"", "text/plain")}
        if planilha is not None and planilha.exists():
            arquivos["planilha"] = ("sombra.xlsx", planilha.read_bytes(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        ultimo = None
        for tentativa in range(5):    # a volta é o que não pode se perder: tenta de novo com a internet instável
            try:
                return self._pedir("POST", f"/t/pcm/pc/rodada/{rid}/entregar", files=arquivos,
                                   data={"relato": json.dumps(relato)}, timeout=300).json()
            except ErroNexus as ex:
                ultimo = ex
                if "Sem conexão" not in str(ex):
                    raise
                time.sleep(10 * (tentativa + 1))
        raise ultimo


# ── a rodada no PC ─────────────────────────────────────────────────────────────────────────────────────────────────────
ETAPAS = (("preparar", "Preparando a rodada no Nexus"), ("fracttal", "Lendo o Fracttal e pondo as OS da FAMA"),
          ("motor", "Rodando o motor do PCM"), ("devolver", "Devolvendo a planilha ao Nexus"))


def _comando_motor(script: Path, *args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--motor", str(script), *args]
    return [sys.executable, str(Path(__file__).resolve()), "--motor", str(script), *args]


def _comando_pre_leitura(pasta_motor: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--pre-leitura", str(pasta_motor)]
    return [sys.executable, str(Path(__file__).resolve()), "--pre-leitura", str(pasta_motor)]


def _ambiente(cred: dict, meta: dict, pasta: Path, saida: Path) -> dict:
    """O mesmo ambiente que o Nexus dá ao motor no servidor (`geracao._ambiente`), com as chaves vindas do Nexus."""
    fora = ("PCM_PROG_DIR", "PCM_OUTPUT", "PCM_WEEK_FORCE", "TZ")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEXUS_", "FRACTTAL_")) and k not in fora}
    env.update({"FRACTTAL_CLIENT_ID": cred["client_id"], "FRACTTAL_CLIENT_SECRET": cred["client_secret"],
                "FRACTTAL_BASE_URL": meta.get("url_api") or cred.get("base_url") or "",
                "FRACTTAL_INTERVALO_S": str(meta.get("intervalo_s") or "1.0"),
                "PROG_API_INTERVALO_S": str(meta.get("intervalo_s") or "1.0"),
                "PCM_PROG_DIR": str(pasta), "PCM_OUTPUT": str(saida), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
                "PCM_APP_LOG": str(pasta / "log_motor.txt")})
    return env


def _criar_sem_janela() -> int:
    return 0x08000000 if os.name == "nt" else 0      # CREATE_NO_WINDOW: o motor não abre um terminal preto


def rodar(nexus: Nexus, semana: str, avisar) -> dict:
    """A rodada inteira; `avisar(tipo, valor)` fala com a janela ("etapa", "log", "fim"). Devolve o que o Nexus disse."""
    t0 = time.monotonic()
    avisar("etapa", ("preparar", "andando"))
    r = nexus.rodada(semana)
    rid = r["id"]
    base = _pasta() / "rodadas" / rid
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    zipfile.ZipFile(io.BytesIO(nexus.pacote(rid))).extractall(base)
    meta = json.loads((base / "rodada.json").read_text(encoding="utf-8"))
    pasta = base / "rodada"
    (pasta / "saida").mkdir(exist_ok=True)
    saida = pasta / "saida" / "sombra.xlsx"
    log = pasta / "log_motor.txt"
    cred = nexus.credencial()
    env = _ambiente(cred, meta, pasta, saida)
    pasta_motor = base / "pcm" / "motor"
    relato: dict = {"maquina": os.environ.get("COMPUTERNAME", "")}
    avisar("etapa", ("preparar", "ok"))
    # o link da rodada pelo endereço do código (o que o servidor diria de si, atrás do proxy, é o de dentro)
    tela = f"{nexus.url}/t/pcm/gerar?rodada={rid}" if getattr(nexus, "url", "") else r.get("tela", "")
    avisar("rodada", dict(r, tela=tela))

    codigo = 1
    with open(log, "wb") as f:
        # 1. a FAMA: o Fracttal lido antes, as OS da FAMA no cache, e o motor com o TTL longo para usar esse cache
        avisar("etapa", ("fracttal", "andando"))
        nexus.andamento(rid, "lendo o Fracttal")
        if meta.get("fama") and (pasta / "fama.json").exists():
            f.write("[FAMA] lendo o Fracttal antes do motor, para pôr as OS da FAMA na semana\n".encode("utf-8"))
            f.flush()
            try:
                p = subprocess.run(_comando_pre_leitura(pasta_motor), cwd=str(pasta), env=env, stdout=f,
                                   stderr=subprocess.STDOUT, timeout=int(meta.get("tempo_max_s") or 3600),
                                   creationflags=_criar_sem_janela())
                if p.returncode != 0 or not (pasta / meta["cache"]).is_file():
                    raise RuntimeError(f"a leitura do Fracttal antes do motor falhou (código {p.returncode})")
                for nome in [m for m in sys.modules if m == "pcm" or m.startswith("pcm.")]:
                    del sys.modules[nome]        # a rodada anterior deixou o pacote dela importado
                sys.path.insert(0, str(base))
                import pcm.fama_motor as FM      # o adaptador do pacote: o MESMO código do servidor
                fama = json.loads((pasta / "fama.json").read_text(encoding="utf-8"))
                cadastro = {int(k): v for k, v in fama["cadastro"].items()}
                rel = FM.aplicar_no_cache(pasta, fama["linhas"], cadastro, fama.get("tirar_preventivas", True))
                rel["vai_ao_app"] = bool(fama.get("tirar_preventivas", True))
                relato["fama"] = rel
                env["PROG_API_TTL_MIN"] = str(meta.get("ttl_fama_min") or "180")
                f.write((f"[FAMA] {rel['os_fama']} OS da FAMA entraram na semana; ficaram de fora: {rel['sem_usina']} "
                         f"sem usina, {rel['sem_previsao']} sem previsão\n").encode("utf-8"))
            except Exception as ex:      # noqa: BLE001 — sem a FAMA, a rodada de sempre (como no servidor)
                motivo = str(ex)[:300]
                relato["fama"] = {"fora": motivo}
                f.write(f"[FAMA] as OS da FAMA ficaram fora desta rodada: {motivo}\n".encode("utf-8"))
            f.flush()
        elif meta.get("fama_fora"):
            relato["fama"] = {"fora": meta["fama_fora"]}
        avisar("etapa", ("fracttal", "ok"))

        # 2. o motor
        avisar("etapa", ("motor", "andando"))
        nexus.andamento(rid, "rodando o motor")
        script = pasta_motor / meta["motor"]
        p = subprocess.Popen(_comando_motor(script, "--semana", meta["semana"]), cwd=str(pasta), env=env, stdout=f,
                             stderr=subprocess.STDOUT, creationflags=_criar_sem_janela())
        limite = time.monotonic() + int(meta.get("tempo_max_s") or 3600)
        while p.poll() is None:
            if time.monotonic() > limite:
                p.kill()
                f.write(b"\n[Nexus PCM] o motor passou do tempo maximo e foi parado\n")
                break
            avisar("log", log)
            time.sleep(2)
        codigo = p.returncode if p.returncode is not None else 1
    avisar("log", log)
    avisar("etapa", ("motor", "ok" if codigo == 0 and saida.exists() else "erro"))

    # 3. a volta
    avisar("etapa", ("devolver", "andando"))
    relato.update(codigo=codigo, duracao_s=int(time.monotonic() - t0))
    if codigo != 0:
        relato["erro"] = _cauda(log, 12)
    v = dict(nexus.entregar(rid, saida if saida.exists() else None, log, relato), tela=tela)
    avisar("etapa", ("devolver", "ok"))
    shutil.rmtree(base, ignore_errors=True)           # a planilha e o log já estão no Nexus
    return v


def _cauda(p: Path, n: int) -> str:
    try:
        return "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


# ── a janela ───────────────────────────────────────────────────────────────────────────────────────────────────────────
COR = {"fundo": "#090d18", "sup": "#161d30", "sup2": "#1c2640", "linha": "#2a3552", "texto": "#e8ecf4",
       "texto2": "#9aa6bf", "verde": "#a3d900", "verde_txt": "#c4e755", "alerta": "#ffd83d", "critico": "#ff5b6e"}


class App:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.raiz = tk.Tk()
        self.raiz.title(NOME)
        self.raiz.geometry("640x620")
        self.raiz.minsize(560, 560)
        self.raiz.configure(bg=COR["fundo"])
        self.fila: queue.Queue = queue.Queue()
        self.rodando = False
        self.nexus: Nexus | None = None
        self.tela_rodada = ""
        self._estilo()
        self.corpo = tk.Frame(self.raiz, bg=COR["fundo"])
        self.corpo.pack(fill="both", expand=True, padx=24, pady=20)
        self.raiz.protocol("WM_DELETE_WINDOW", self._fechar)
        cod = ler_codigo()
        self._conectar_com(cod) if cod else self._tela_codigo()
        self.raiz.after(150, self._ouvir)

    def _estilo(self):
        s = self.ttk.Style(self.raiz)
        s.theme_use("clam")
        s.configure("Nx.Horizontal.TProgressbar", troughcolor=COR["sup2"], background=COR["verde"], bordercolor=COR["sup2"],
                    lightcolor=COR["verde"], darkcolor=COR["verde"])

    # pequenas peças no visual do Nexus
    def _limpar(self):
        for w in self.corpo.winfo_children():
            w.destroy()

    def _rotulo(self, pai, txt, tam=10, cor="texto", negrito=False, **kw):
        return self.tk.Label(pai, text=txt, bg=pai["bg"], fg=COR[cor], font=("Segoe UI", tam, "bold" if negrito else "normal"),
                             justify="left", anchor="w", **kw)

    def _botao(self, pai, txt, cmd, primario=True):
        b = self.tk.Button(pai, text=txt, command=cmd, bg=COR["verde"] if primario else COR["sup2"],
                           fg=COR["fundo"] if primario else COR["texto"], activebackground=COR["verde_txt"] if primario else COR["linha"],
                           relief="flat", bd=0, padx=16, pady=8, font=("Segoe UI", 10, "bold"), cursor="hand2")
        return b

    def _topo(self, sub: str):
        self._rotulo(self.corpo, "PCM · PROGRAMAÇÃO SEMANAL", 9, "verde_txt", True).pack(fill="x")
        self._rotulo(self.corpo, NOME, 20, "texto", True).pack(fill="x", pady=(2, 0))
        self._rotulo(self.corpo, sub, 10, "texto2", wraplength=580).pack(fill="x", pady=(4, 16))

    # 1. o código do computador
    def _tela_codigo(self, erro: str = ""):
        self._limpar()
        self._topo("Gera a programação da semana neste computador e devolve a planilha ao Nexus, pronta para conferir e "
                   "publicar no App.")
        caixa = self.tk.Frame(self.corpo, bg=COR["sup"], padx=18, pady=16)
        caixa.pack(fill="x")
        self._rotulo(caixa, "Ligar este computador", 12, negrito=True).pack(fill="x")
        self._rotulo(caixa, "No Nexus: PCM → Gerar a semana → Gerar no PC → Ligar um computador. Copie o código e cole "
                     "aqui. Ele fica guardado cifrado pelo Windows: você só faz isso uma vez.", 10, "texto2",
                     wraplength=540).pack(fill="x", pady=(4, 10))
        self.campo = self.tk.Text(caixa, height=4, bg=COR["sup2"], fg=COR["texto"], insertbackground=COR["texto"],
                                  relief="flat", font=("Consolas", 9), wrap="char", padx=8, pady=8)
        self.campo.pack(fill="x")
        if erro:
            self._rotulo(caixa, erro, 10, "critico", wraplength=540).pack(fill="x", pady=(8, 0))
        linha = self.tk.Frame(caixa, bg=COR["sup"])
        linha.pack(fill="x", pady=(12, 0))
        self._botao(linha, "Conectar", lambda: self._conectar_com(self.campo.get("1.0", "end"), guardar=True)).pack(side="left")

    def _conectar_com(self, cod: str, guardar: bool = False):
        try:
            url, chave = abrir_codigo(cod)
            nexus = Nexus(url, chave)
            ola = nexus.ola()
        except ValueError as ex:
            return self._tela_codigo(str(ex))
        except ErroNexus as ex:
            if ex.desligado:
                esquecer_codigo()               # o código desligado não serve mais; a internet que caiu, sim
            return self._tela_codigo(str(ex))
        if guardar:
            guardar_codigo("".join(cod.split()))
        self.nexus = nexus
        self._tela_gerar(ola)

    # 2. gerar a semana
    def _tela_gerar(self, ola: dict):
        self._limpar()
        self._topo(f"Este computador está ligado ao Nexus como “{ola.get('computador')}”.")
        caixa = self.tk.Frame(self.corpo, bg=COR["sup"], padx=18, pady=16)
        caixa.pack(fill="x")
        linha = self.tk.Frame(caixa, bg=COR["sup"])
        linha.pack(fill="x")
        self._rotulo(linha, "Semana", 10, "texto2").pack(side="left")
        self.semana = self.tk.Entry(linha, width=10, bg=COR["sup2"], fg=COR["texto"], insertbackground=COR["texto"],
                                    relief="flat", font=("Segoe UI", 11))
        self.semana.insert(0, ola.get("semana") or "")
        self.semana.pack(side="left", padx=(10, 12), ipady=5)
        self.botao_gerar = self._botao(linha, "Gerar a semana", self._gerar)
        self.botao_gerar.pack(side="left")
        self._rotulo(caixa, "Leva de 15 a 40 minutos: o motor lê o Fracttal a 1 pedido por segundo. Deixe o computador "
                     "ligado e esta janela aberta; pode usar o computador enquanto isso.", 9, "texto2",
                     wraplength=540).pack(fill="x", pady=(10, 0))

        self.etapas = {}
        lista = self.tk.Frame(self.corpo, bg=COR["fundo"])
        lista.pack(fill="x", pady=(16, 6))
        for chave, txt in ETAPAS:
            f = self.tk.Frame(lista, bg=COR["fundo"])
            f.pack(fill="x", pady=3)
            marca = self._rotulo(f, "○", 12, "texto2", width=2)
            marca.pack(side="left")
            self._rotulo(f, txt, 10).pack(side="left")
            self.etapas[chave] = marca
        self.barra = self.ttk.Progressbar(self.corpo, mode="indeterminate", style="Nx.Horizontal.TProgressbar")
        self.barra.pack(fill="x", pady=(6, 10))
        self.situacao = self._rotulo(self.corpo, "", 10, "texto2", wraplength=580)
        self.situacao.pack(fill="x")
        self.log = self.tk.Text(self.corpo, height=8, bg=COR["sup"], fg=COR["texto2"], relief="flat", font=("Consolas", 8),
                                wrap="none", padx=8, pady=6, state="disabled")
        self.log.pack(fill="both", expand=True, pady=(8, 8))
        pe = self.tk.Frame(self.corpo, bg=COR["fundo"])
        pe.pack(fill="x")
        self.botao_abrir = self._botao(pe, "Abrir no Nexus", self._abrir)
        self.tk.Button(pe, text="Trocar o código", command=self._trocar, bg=COR["fundo"], fg=COR["texto2"], relief="flat",
                       bd=0, cursor="hand2", font=("Segoe UI", 9)).pack(side="right")

    def _gerar(self):
        semana = self.semana.get().strip()
        if not (len(semana) == 8 and semana[4:6] == "-W" and semana[:4].isdigit() and semana[6:].isdigit()):
            self.situacao.configure(text="Semana no formato 2026-W49.", fg=COR["critico"])
            return
        self.rodando = True
        self.botao_gerar.configure(state="disabled")
        self.botao_abrir.pack_forget()
        for m in self.etapas.values():
            m.configure(text="○", fg=COR["texto2"])
        self.situacao.configure(text=f"Gerando a semana {semana}…", fg=COR["texto2"])
        self.barra.start(12)

        def trabalho():
            try:
                v = rodar(self.nexus, semana, lambda t, x: self.fila.put((t, x)))
                self.fila.put(("fim", v))
            except ErroNexus as ex:
                self.fila.put(("erro", str(ex)))
            except Exception as ex:      # noqa: BLE001 — a janela mostra o motivo; o detalhe vai ao log local
                (_pasta() / "ultimo_erro.txt").write_text(traceback.format_exc(), encoding="utf-8")
                self.fila.put(("erro", f"Algo deu errado neste computador ({type(ex).__name__}: {str(ex)[:200]})."))
        threading.Thread(target=trabalho, daemon=True).start()

    def _ouvir(self):
        try:
            while True:
                tipo, x = self.fila.get_nowait()
                if tipo == "etapa":
                    chave, est = x
                    marca = {"andando": ("●", "alerta"), "ok": ("✓", "verde"), "erro": ("✕", "critico")}[est]
                    self.etapas[chave].configure(text=marca[0], fg=COR[marca[1]])
                elif tipo == "rodada":
                    self.tela_rodada = x.get("tela") or ""
                elif tipo == "log":
                    self._mostrar_log(_cauda(x, 12))
                elif tipo == "fim":
                    self._terminou(x)
                elif tipo == "erro":
                    self._falhou(x)
        except queue.Empty:
            pass
        self.raiz.after(400, self._ouvir)

    def _mostrar_log(self, txt: str):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", txt)
        self.log.configure(state="disabled")

    def _parar(self):
        self.rodando = False
        self.barra.stop()
        self.botao_gerar.configure(state="normal")

    def _terminou(self, v: dict):
        self._parar()
        self.tela_rodada = v.get("tela") or self.tela_rodada
        if v.get("estado") == "ok":
            self.situacao.configure(text="Pronta no Nexus. Confira a rodada e publique no App pela tela Gerar a semana.",
                                    fg=COR["verde_txt"])
        else:
            self.situacao.configure(text="O motor não terminou. O log foi para o Nexus: abra a rodada para ver o motivo.",
                                    fg=COR["critico"])
        self.botao_abrir.pack(side="left")

    def _falhou(self, msg: str):
        self._parar()
        for m in self.etapas.values():
            if m.cget("text") == "●":
                m.configure(text="✕", fg=COR["critico"])
        self.situacao.configure(text=msg, fg=COR["critico"])
        if self.tela_rodada:
            self.botao_abrir.pack(side="left")

    def _abrir(self):
        if self.tela_rodada:
            webbrowser.open(self.tela_rodada)

    def _trocar(self):
        if self.rodando:
            return
        esquecer_codigo()
        self.nexus = None
        self._tela_codigo()

    def _fechar(self):
        from tkinter import messagebox
        if self.rodando and not messagebox.askyesno(NOME, "A semana ainda está sendo gerada. Fechar agora perde esta rodada. "
                                                          "Fechar mesmo assim?"):
            return
        self.raiz.destroy()

    def rodar(self):
        self.raiz.mainloop()


def main():
    if _como_motor(sys.argv):
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)      # o texto nítido na tela com zoom do Windows (125%, 150%)
    except (AttributeError, OSError):
        pass
    App().rodar()


if __name__ == "__main__":
    main()
