# -*- coding: utf-8 -*-
"""Uma conversão por pessoa na tela Coletas: a `Sessao` do Conversor com o BD do banco e os arquivos que a pessoa soltou.

No .exe a sessão é do processo (uma pessoa, um PC). No Nexus o servidor é um só para todos: cada pessoa logada tem a
sua sessão, com os arquivos numa pasta temporária própria, que some quando a sessão fica parada (`PARADA_S`) ou a pessoa
clica em Limpar / Nova conversão. Nada do que a pessoa solta é guardado, salvo o formato que ninguém conhece, que vai
para a pasta "formatos novos" do Nexus, para o Levi ensinar o leitor (no .exe era a pasta ao lado do BD_Performance).

A regra continua no motor (`conversor.sessao`, `conversor.montagem`): aqui só o que muda por ser um servidor — o BD do
banco (`pg.py`), a pasta de cada pessoa, a data do arquivo (a do computador de quem soltou, não a da chegada ao
servidor: o "só dia fechado" usa a data do arquivo como a hora da baixa) e o reconhecimento em fundo, que a tela
acompanha perguntando o estado.
"""
import datetime as dt
import os
import re
import shutil
import tempfile
import threading
import time
import traceback

from . import motor  # noqa: F401 — o motor como `conversor`
from . import pg
from conversor import furos as _furos  # noqa: E402
from conversor import montagem  # noqa: E402
from conversor import mural as _mural  # noqa: E402
from conversor.nucleo import BD_PERFORMANCE, BD_THOPEN  # noqa: E402
from conversor.sessao import Sessao  # noqa: E402

PARADA_S = 3 * 3600             # sessão parada há 3 h: some com os arquivos
_RX_BD = re.compile(r"^BD_(Performance|Thopen)\b.*\.xls[xm]$", re.I)
_DESTINO_DO_NOME = {"performance": BD_PERFORMANCE, "thopen": BD_THOPEN}


def nome_seguro(rel):
    """O caminho relativo que o navegador mandou (o arquivo, ou a pasta/arquivo de "escolher uma pasta"), sem nada que
    saia da pasta do lote."""
    partes = [p for p in re.split(r"[\\/]+", str(rel or "")) if p not in ("", ".", "..")]
    partes = [re.sub(r'[<>:"|?*\x00-\x1f]', "_", p).strip() or "_" for p in partes]
    return os.path.join(*partes) if partes else "arquivo"


class SessaoNexus(Sessao):
    def __init__(self, banco, pasta, formatos_novos, hoje=None):
        super().__init__(caminhos_bd={BD_PERFORMANCE: None, BD_THOPEN: None}, hoje=hoje,
                         pasta_saida=os.path.join(pasta, "saida"))
        self._banco = banco                    # () -> pg.Banco
        self._pasta = pasta
        self._formatos_novos = formatos_novos
        self.origem_bd = {}                    # destino -> "banco" | "arquivo"
        self._trava_bd = threading.RLock()     # a troca de BD (banco em fundo x Excel solto): ver carregar_bd
        self.pronto = threading.Event()
        self.uso = time.time()
        self._lotes = 0
        self.saidas = []                       # os caminhos das planilhas da última conversão (a tela baixa pelo índice)

    # ------------------------------------------------------------ BDs: o banco, ou o Excel que a pessoa soltou
    # A leitura do banco NUNCA passa por cima do Excel que a pessoa soltou (12/11/2026, o 1º uso do Levi: "usei o subir
    # excel, não prestou nada!, clico em converter e dá erro!"). Ao abrir a tela, o banco é lido em fundo (segundos); o
    # BD_Thopen em Excel que chegou nesse meio-tempo entrava, e a leitura do banco, terminando depois, o tirava e punha o
    # "falta o mapa de fórmulas" no lugar: a conversão saía com "BD_Thopen não foi lido". Agora a troca é sob a trava da
    # sessão, e o banco só entra onde não há Excel (o Limpar, que tira o Excel, volta ao banco por `_voltar_ao_banco`).
    def carregar_bd(self, destino, caminho=None):
        if caminho:
            with self._trava_bd:
                velho = self.bds.pop(destino, None)
                if velho is not None and self.origem_bd.get(destino) == "arquivo":
                    velho.fechar()             # o do banco é o mesmo para todos: não se fecha aqui
                self.erros_bd.pop(destino, None)
                self.caminhos_bd[destino] = caminho
                r = super().carregar_bd(destino, caminho)
                if r is not None:
                    self.origem_bd[destino] = "arquivo"
                return r
        bd, erro = pg.bd_do_banco(destino, self._banco())          # fora da trava: leva segundos
        with self._trava_bd:
            if self.origem_bd.get(destino) == "arquivo":
                return self.bds.get(destino)   # o Excel chegou enquanto o banco era lido: vale o Excel
            self.bds.pop(destino, None)
            self.erros_bd.pop(destino, None)
            self.caminhos_bd[destino] = None
            if bd is not None:
                self.bds[destino] = bd
                self.origem_bd[destino] = "banco"
            else:
                self.erros_bd[destino] = erro
                self.origem_bd.pop(destino, None)
            return bd

    def _voltar_ao_banco(self, destino):
        with self._trava_bd:
            velho = self.bds.pop(destino, None)
            if velho is not None and self.origem_bd.get(destino) == "arquivo":
                velho.fechar()
            self.origem_bd.pop(destino, None)
        return self.carregar_bd(destino)

    def carregar_bds(self):
        for destino in (BD_PERFORMANCE, BD_THOPEN):
            if self.origem_bd.get(destino) != "arquivo":
                self.carregar_bd(destino)

    def estado_bds(self):
        out = []
        for destino in (BD_PERFORMANCE, BD_THOPEN):
            b = self.bds.get(destino)
            origem = self.origem_bd.get(destino)
            out.append({"destino": destino, "lido": bool(b), "origem": origem,
                        "lido_em": b.lido_em.strftime("%d/%m %H:%M") if b else None,
                        "caminho": (f"banco (subida de {b.lido_em:%d/%m %H:%M}; mapa de fórmulas de "
                                    f"{b.mapa_em:%d/%m %H:%M})" if origem == "banco" and b else
                                    os.path.basename(self.caminhos_bd.get(destino) or "")),
                        "velhas": len(getattr(b, "velhas", []) or []),
                        "erro": self.erros_bd.get(destino)})
        return out

    def iniciar(self):
        def vai():
            try:
                self.carregar_bds()
            except Exception:                  # noqa: BLE001 — o motivo vai no estado de cada BD
                traceback.print_exc()
            finally:
                self.pronto.set()
        threading.Thread(target=vai, daemon=True, name="coletas-bd").start()

    def estado(self):
        return {"versao": motor.APP_VERSAO, "bds": self.estado_bds(), "bd_pronto": self.pronto.is_set(),
                "atualizacao": None, "itens": [self.cartao(i) for i in self.itens]}

    # ------------------------------------------------------------ arquivos
    def novo_lote(self):
        with self._lock:
            self._lotes += 1
            n = self._lotes
        p = os.path.join(self._pasta, "arquivos", f"lote{n:03d}")
        os.makedirs(p, exist_ok=True)
        return n

    def _lote(self, n):
        p = os.path.join(self._pasta, "arquivos", f"lote{int(n):03d}")
        if not os.path.isdir(p):
            raise LookupError("o envio não existe mais (a sessão foi limpa): solte os arquivos de novo")
        return p

    def receber(self, lote, rel, fluxo, modificado_ms=None):
        """Grava um arquivo do lote. `modificado_ms`: a data do arquivo no computador de quem soltou (File.lastModified),
        que o motor usa como a hora da baixa (o mensal da Sal baixado 08/11 12:41 traz o 08/11 pela metade)."""
        destino = os.path.join(self._lote(lote), nome_seguro(rel))
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        if hasattr(fluxo, "save"):
            fluxo.save(destino)                # o FileStorage do Flask
        else:
            with open(destino, "wb") as f:
                shutil.copyfileobj(fluxo, f)
        try:
            ts = float(modificado_ms) / 1000.0
            if 946684800 < ts < time.time() + 86400:            # de 2000 a amanhã: o resto é lixo do navegador
                os.utime(destino, (ts, ts))
        except (TypeError, ValueError):
            pass
        return destino

    def lote_pronto(self, lote, topos):
        """Os arquivos (ou pastas) de cima do lote viram cartões. O BD em Excel solto junto não vira cartão: entra no
        lugar do BD do banco (o .exe pedia o arquivo; aqui a pessoa solta)."""
        base = self._lote(lote)
        caminhos, bds = [], []
        for t in topos or []:
            c = os.path.join(base, nome_seguro(t))
            if not os.path.exists(c):
                continue
            m = _RX_BD.match(os.path.basename(c)) if os.path.isfile(c) else None
            if m:
                bds.append((_DESTINO_DO_NOME[m.group(1).lower()], c))
            else:
                caminhos.append(c)
        for destino, c in bds:
            self.carregar_bd(destino, c)
            for it in self.itens:              # o reconhecimento pode depender do BD (casar pela geração)
                if it["estado"] in ("desconhecido", "pergunta_usina", "ok"):
                    self.reconhecer(it)
        itens = self.preparar(caminhos)

        def rec():
            self.pronto.wait(180)              # leitor que casa pela geração precisa do BD
            for it in itens:
                try:
                    self.reconhecer(it)
                except Exception as e:         # noqa: BLE001
                    traceback.print_exc()
                    it["estado"] = "desconhecido"
                    it["erro"] = "%s: %s" % (type(e).__name__, e)
        threading.Thread(target=rec, daemon=True, name="coletas-reconhecer").start()
        return self.estado()

    def cartao(self, item):
        c = super().cartao(item)
        if item.get("erro") and item["estado"] == "desconhecido":
            c["erro"] = item["erro"]
        return c

    def separar(self, id_, fonte=None):
        """Formato que ninguém reconhece: vai para a pasta "formatos novos" do Nexus, com a fonte no nome."""
        it = self.item(id_)
        if not it:
            return None
        os.makedirs(self._formatos_novos, exist_ok=True)
        pref = dt.datetime.now().strftime("%Y-%m-%d %Hh%M")
        nome = "%s - %s%s" % (pref, ("%s - " % fonte) if fonte else "", it["nome"])
        try:
            if os.path.isdir(it["caminho"]):
                shutil.copytree(it["caminho"], os.path.join(self._formatos_novos, nome_seguro(nome)))
            else:
                shutil.copy2(it["caminho"], os.path.join(self._formatos_novos, nome_seguro(nome)))
        except OSError as e:
            it["erro"] = str(e)
        it["estado"] = "separado"
        it["separado_para"] = "Nexus · formatos novos"
        return self.cartao(it)

    def limpar(self):
        super().limpar()
        self.saidas = []
        shutil.rmtree(os.path.join(self._pasta, "arquivos"), ignore_errors=True)
        shutil.rmtree(os.path.join(self._pasta, "saida"), ignore_errors=True)
        for destino in list(self.origem_bd):   # o BD solto em Excel sai com os arquivos: volta o do banco
            if self.origem_bd.get(destino) == "arquivo":
                self._voltar_ao_banco(destino)

    # ------------------------------------------------------------ conversão
    def converter(self, agora=None):
        r = super().converter(agora)
        self.saidas = [s["caminho"] for s in r.get("saidas") or []]
        for i, s in enumerate(r.get("saidas") or []):
            s["caminho"] = os.path.basename(s["caminho"])
            s["indice"] = i
        r["pasta"] = ""
        # o banco anda atrás do Excel: o que a equipe digitou depois da última subida não está aqui (o Conversor pode
        # propor um valor onde o Excel já tem um)
        for destino in (BD_PERFORMANCE, BD_THOPEN):
            b = self.bds.get(destino)
            if b is not None and self.origem_bd.get(destino) == "banco" and any(
                    t.get("destino") == destino and t.get("celulas") for t in r.get("tabela") or []):
                r["avisos"].insert(0, montagem.Aviso(
                    "leve", "o %s veio do banco, da subida de %s: o que foi digitado no Excel depois disso não está aqui. "
                    "Antes de colar, confira no Excel os dias de %s em diante (podem já ter valor)."
                    % (destino, b.lido_em.strftime("%d/%m às %H:%M"), b.lido_em.strftime("%d/%m")), None, destino))
        return r

    def fechar(self):
        for destino, b in list(self.bds.items()):
            if self.origem_bd.get(destino) == "arquivo":
                b.fechar()
        self.bds.clear()
        shutil.rmtree(self._tmp, ignore_errors=True)
        shutil.rmtree(self._pasta, ignore_errors=True)


# ------------------------------------------------------------------------- as sessões de todo mundo
_SESSOES = {}
_TRAVA = threading.Lock()


def sessao_de(chave, banco, raiz_temp=None, formatos_novos=None):
    """A sessão da pessoa (cria na 1ª vez, com a leitura do BD do banco em fundo). Poda as paradas."""
    agora = time.time()
    with _TRAVA:
        for k, s in list(_SESSOES.items()):
            if agora - s.uso > PARADA_S and k != chave:
                _SESSOES.pop(k, None)
                try:
                    s.fechar()
                except Exception:              # noqa: BLE001
                    pass
        s = _SESSOES.get(chave)
        if s is None:
            pasta = tempfile.mkdtemp(prefix="nexus_coletas_", dir=raiz_temp)
            s = SessaoNexus(banco, pasta, formatos_novos or os.path.join(pasta, "formatos_novos"))
            _SESSOES[chave] = s
            s.iniciar()
        s.uso = agora
        return s


def esquecer(chave):
    with _TRAVA:
        s = _SESSOES.pop(chave, None)
    if s:
        s.fechar()


# ------------------------------------------------------------------------- furos de coleta
def furos_ler(caminho):
    """O relatório de furos (o HTML gerado fora) no formato da tela 3; {"erro": ...} quando não serve."""
    if not caminho or not os.path.isfile(caminho):
        return {"erro": "Nenhum relatório de furos no Nexus ainda. Clique em Abrir relatório e escolha o "
                        "Furos_Coleta_Performance mais novo: ele fica no Nexus e todos veem o mesmo."}
    try:
        r = _furos.ler(caminho)
    except (OSError, ValueError) as e:
        return {"erro": "Não consegui ler %s: %s" % (os.path.basename(caminho), e)}
    r["caminho"] = os.path.basename(caminho)
    r["conf"] = {}                          # as de cada pessoa ficam no navegador dela (a tela soma)
    return r


# ------------------------------------------------------------------------- onde buscar no portal (Conversor 1.0.10)
# A aba "Para coletar" dos Furos diz em que planta e equipamento do supervisório buscar o inversor que falta (13/11/2026,
# quem coleta a Thopen no iSolarCloud: "tem várias Ceilândia, aí eu não sei qual delas devo clicar"). No .exe sai da
# aba Equipamentos do BD_Performance em Excel (`furos.portal`); aqui, do Excel que a pessoa soltou ou, sem ele, da mesma
# aba no banco (a subida do coletor). A leitura é a do .exe, linha a linha: o cabeçalho é a linha com "Usina Supervisório"
# e "Equipamento"; o "(94)" do id da API PV sai do nome da planta; "Inversor 6,2" = "Inversor 6.2".
_PORTAL = {}
_TRAVA_PORTAL = threading.Lock()        # o furos.portal do .exe copia o Excel para um nome fixo no temp


def portal_de_linhas(linhas):
    out, cab = {}, None
    linhas = iter(linhas)
    for r in linhas:
        s_ = [str(c).strip() if c is not None else "" for c in r]
        if "Usina Supervisório" in s_ and "Equipamento" in s_:
            cab = {n: i for i, n in enumerate(s_)}
            break
    if cab is None:
        return {}
    pega = lambda r, n: r[cab[n]] if cab.get(n) is not None and cab[n] < len(r) else None   # noqa: E731
    for r in linhas:
        us, u = pega(r, "Usina Supervisório"), pega(r, "Usina")
        if not us or not u:
            continue
        d = out.setdefault(str(u).strip(), {"plantas": [], "inv": {}})
        pl = _furos._sem_id(us)
        if pl not in d["plantas"]:
            d["plantas"].append(pl)
        es, e = pega(r, "Equipamento Supervisório"), pega(r, "Equipamento")
        if es and e:
            d["inv"].setdefault(_furos._equip(e), [pl, str(es).strip()])
    return out


def _equipamentos_do_banco(banco):
    """As linhas da aba Equipamentos do BD_Performance no banco (o cabeçalho primeiro), guardadas 10 min."""
    with _TRAVA_PORTAL:
        g = _PORTAL.get("banco")
        if g and time.time() - g[0] < pg.VALE_S:
            return g[1]
    b = banco()
    sh = (b.abas().get(pg.CHAVE[BD_PERFORMANCE]) or {}).get("Equipamentos")
    rows = b.linhas(sh["id"]) if sh else []
    linhas = ([rows[0].get("headers") or []] if rows else []) + [x.get("values") or [] for x in rows]
    with _TRAVA_PORTAL:
        _PORTAL["banco"] = (time.time(), linhas)
    return linhas


def furos_portal(sessao, banco):
    """{usina do BD: {"plantas": [...], "inv": {"Inversor 2.3": [planta, equipamento]}}}; {} quando não há de onde ler."""
    if sessao.origem_bd.get(BD_PERFORMANCE) == "arquivo":
        with _TRAVA_PORTAL:
            return _furos.portal(sessao.caminhos_bd.get(BD_PERFORMANCE))
    return portal_de_linhas(_equipamentos_do_banco(banco))


# ------------------------------------------------------------------------- mural de baixa performance (Conversor 1.0.11)
# A régua é a do .exe (`mural.calcular`): cada inversor contra a média dos demais da usina no dia, em kWh/kWp quando a aba
# Equipamentos tem a potência de todos. No .exe usa os BDs que a janela leu; aqui, o Excel que a pessoa soltou ou, sem
# ele, os VALORES do banco (`pg.BDdoBanco(so_valores=True)`: ler não precisa do mapa de fórmulas, que só protege a
# colagem). A conta lê o BD inteiro: o resultado fica guardado por (mês, subida de cada BD), o BD não.
_MURAL = {}
_TRAVA_MURAL = threading.Lock()


def potencias_de_linhas(linhas):
    """A leitura do `mural.potencias` do .exe sobre as linhas da aba Equipamentos: {usina: {"Inversor 1.1": kWp}}."""
    out, cab = {}, None
    linhas = iter(linhas)
    for r in linhas:
        s_ = [str(c).strip() if c is not None else "" for c in r]
        if "Usina" in s_ and "Equipamento" in s_ and "Potência (kWp)" in s_:
            cab = {n: i for i, n in enumerate(s_)}
            break
    if cab is None:
        return {}
    for r in linhas:
        u, e, k = (r[cab[n]] if cab[n] < len(r) else None for n in ("Usina", "Equipamento", "Potência (kWp)"))
        if u and e and isinstance(k, (int, float)) and not isinstance(k, bool) and k > 0:
            out.setdefault(str(u).strip(), {})[_mural._equip(e)] = float(k)
    return out


def _janela(mes, hoje):
    """O mês até ontem, como o `mural.mural` do .exe."""
    a, m = (int(x) for x in mes.split("-"))
    ini = dt.date(a, m, 1)
    return ini, min(dt.date(a + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1), hoje - dt.timedelta(days=1))


def furos_mural(sessao, banco, mes, hoje=None):
    """{"linhas", "limiar", "ini", "fim"} como o `mural.mural` do .exe; {"erro": ...} quando não dá."""
    if not re.fullmatch(r"\d{4}-\d{2}", str(mes or "")):
        return {"erro": "mês inválido"}
    ini, fim = _janela(mes, hoje or dt.date.today())
    bds, marca = {}, [mes, fim.isoformat()]
    b = livros = abas = None
    for destino in (BD_PERFORMANCE, BD_THOPEN):
        if sessao.origem_bd.get(destino) == "arquivo" and sessao.bds.get(destino):
            bds[destino] = sessao.bds[destino]
            marca.append((destino, "arquivo", str(sessao.bds[destino].lido_em)))
            continue
        if livros is None:
            b = banco()
            livros, abas = b.livros(), b.abas()
        w = livros.get(pg.CHAVE[destino])
        if not w:
            continue
        bds[destino] = pg.BDdoBanco(destino, b, livros, abas, so_valores=True)
        marca.append((destino, "banco", w.get("updated_at")))
    if not bds:
        return {"erro": "Os BDs não estão no banco nem foram soltos em Excel: solte o BD_Performance e o BD_Thopen."}
    marca = tuple(marca)
    with _TRAVA_MURAL:
        if marca in _MURAL:
            return _MURAL[marca]
    if sessao.origem_bd.get(BD_PERFORMANCE) == "arquivo":
        with _TRAVA_PORTAL:                # o .exe copia o Excel para um nome fixo no temp
            kwp = _mural.potencias(sessao.caminhos_bd.get(BD_PERFORMANCE))
    else:
        kwp = potencias_de_linhas(_equipamentos_do_banco(banco))
    out = {"linhas": _mural.calcular(bds, kwp, ini, fim), "limiar": _mural.LIMIAR, "ini": ini.isoformat(),
           "fim": fim.isoformat()}
    for d, bd in bds.items():
        if sessao.bds.get(d) is not bd:
            bd.fechar()                    # o do banco era só para esta conta: solta a memória
    with _TRAVA_MURAL:
        _MURAL.clear()
        _MURAL[marca] = out
    return out
