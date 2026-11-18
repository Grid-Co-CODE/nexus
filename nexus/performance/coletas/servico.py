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
import hashlib
import hmac
import os
import re
import shutil
import tempfile
import threading
import time
import traceback

from . import motor  # noqa: F401 — o motor como `conversor`
from . import pg
from . import recoleta_fontes as RF
from conversor import furos as _furos  # noqa: E402
from conversor import montagem  # noqa: E402
from conversor import mural as _mural  # noqa: E402
from conversor import paradas as _paradas  # noqa: E402
from conversor import recoleta as _recoleta  # noqa: E402
from conversor.nucleo import BD_PERFORMANCE, BD_THOPEN  # noqa: E402
from conversor.sessao import Sessao  # noqa: E402

PARADA_S = 3 * 3600             # sessão parada há 3 h: some com os arquivos
RELER_S = 60                    # a sessão aberta confere o banco no máximo a cada minuto (ver SessaoNexus._conferir_banco)
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
        self._convertendo = threading.Event()  # a conferida do banco espera a conversão: ver _conferir_banco
        self._conferido = time.time()          # a 1ª leitura é a do iniciar
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
        return self._por_do_banco(destino, bd, erro)

    def _por_do_banco(self, destino, bd, erro):
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

    # A sessão aberta acompanha o banco (16/11/2026, o dia em que o mapa de fórmulas passou a subir: a tela aberta antes
    # de ele chegar seguia pedindo o Excel, porque a leitura do banco que falhou nunca era refeita; e a aberta de um dia
    # para o outro ficava na subida velha). No máximo uma conferida por minuto, e nunca no meio de uma conversão (o
    # Contexto do motor usa o mesmo dicionário de BDs). Conferir custa duas consultas pequenas: a leitura em si é a mesma
    # para todos e fica guardada por subida (`pg.bd_do_banco`). O Excel solto nunca sai por aqui.
    def _conferir_banco(self, agora=None):
        agora = time.time() if agora is None else agora
        if not self.pronto.is_set() or self._convertendo.is_set() or agora - self._conferido < RELER_S:
            return
        self._conferido = agora
        for destino in (BD_PERFORMANCE, BD_THOPEN):
            if self.origem_bd.get(destino) == "arquivo":
                continue
            atual = self.bds.get(destino)
            novo, erro = pg.bd_do_banco(destino, self._banco())
            if novo is atual or (novo is None and atual is not None):
                continue                       # mesma subida; ou o banco falhou agora e a sessão já tem um BD bom
            self._por_do_banco(destino, novo, erro)

    def estado(self):
        try:
            self._conferir_banco()
        except Exception:                      # noqa: BLE001 — conferir é extra: o estado sai com o BD que já havia
            traceback.print_exc()
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
        self._convertendo.set()
        try:
            r = super().converter(agora)
        finally:
            self._convertendo.clear()
        return self._fechar_resultado(r)

    def _fechar_resultado(self, r):
        """O resultado da montagem como a tela do Nexus o recebe: a planilha pelo índice (nada de caminho do servidor) e
        o aviso de que o banco anda atrás do Excel. Vale para a conversão de arquivo e para a recoleta."""
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

    # ------------------------------------------------------------ recoleta pela fonte (Conversor 1.0.14)
    # Os quatro métodos são os da Api do .exe (app.py: recoleta_opcoes, _fatias, _parte, _montar), com duas trocas de
    # servidor: a chave vem do ambiente do Nexus (`chave_recoleta`) e o "onde está no portal" vem da aba Equipamentos do
    # banco (`furos_portal`). Quem pode chamar é a rota que decide (a tela "Recoleta pelas fontes" de Base > Acessos).
    def recoleta_opcoes(self, chave, portal):
        """As usinas que dá para recoletar: as do cadastro (aba Equipamentos) com planta na fonte e aba num BD lido."""
        if not chave:
            return {"erro": "Este Nexus não tem a chave da recoleta (NEXUS_SSO_CHAVE ou CONVERSOR_RECOLETA_CHAVE)."}
        try:
            info = _recoleta.plantas(chave)
            m = _recoleta.mapa(portal() if callable(portal) else portal, info.get("plantas") or [])
        except _recoleta.Falha as e:
            return {"erro": str(e)}
        except Exception as e:                 # noqa: BLE001 — a tela mostra o motivo
            traceback.print_exc()
            return {"erro": "%s: %s" % (type(e).__name__, e)}
        ctx = self.ctx()
        us = []
        for usina, x in sorted(m.items()):
            d = _recoleta.destino_de(ctx, usina)
            if d:
                us.append({"usina": usina, "destino": d, "plantas": [n for _, n in x["plantas"]], "n_inv": len(x["inv"])})
        self._rec = {"chave": chave, "mapa": m}
        return {"usinas": us, "max_dias": info.get("max_dias"), "restam_hoje": info.get("restam_hoje"),
                "teto_dia": info.get("teto_dia")}

    def recoleta_fatias(self, ini, fim):
        a, b = dt.date.fromisoformat(ini), dt.date.fromisoformat(fim)
        return [[x.isoformat(), y.isoformat()] for x, y in _recoleta.fatias(a, b)]

    def recoleta_parte(self, usina, ini, fim, geracao, etm, primeira=False):
        """Uma fatia (até 7 dias) na plataforma. A tela chama uma por vez e mostra o andamento."""
        rec = getattr(self, "_rec", None)
        if not rec or usina not in rec["mapa"]:
            return {"erro": "Abra de novo a recoleta (a lista de usinas venceu)."}
        if primeira:
            rec["respostas"] = []
        try:
            r = _recoleta.pedir_fatia(rec["chave"], [i for i, _ in rec["mapa"][usina]["plantas"]],
                                      dt.date.fromisoformat(ini), dt.date.fromisoformat(fim), bool(geracao), bool(etm))
        except _recoleta.Falha as e:
            return {"erro": str(e)}
        rec.setdefault("respostas", []).append(r)
        return {"ok": True, "chamadas": r.get("chamadas"), "restam": r.get("restam")}

    def recoleta_montar(self, usina, geracao, etm, agora=None):
        """As fatias recebidas viram células e passam pela MESMA montagem da conversão (a tela 2 de sempre)."""
        rec = getattr(self, "_rec", None) or {}
        m = (rec.get("mapa") or {}).get(usina)
        if not m:
            return {"erro": "Abra de novo a recoleta (a lista de usinas venceu)."}
        self._convertendo.set()
        try:
            ctx = self.ctx()
            destino = _recoleta.destino_de(ctx, usina)
            cel, av = _recoleta.celulas(rec.get("respostas") or [], usina, destino, m, bool(geracao), bool(etm))
            avisos = [montagem.Aviso(n, "Recoleta %s: %s" % (usina, t)) for n, t in av]
            agora = agora or dt.datetime.now()
            pasta = os.path.join(self.pasta_saida, agora.strftime("%d-%m"))
            res = montagem.montar([(c, _recoleta.FONTE) for c in cel], ctx, pasta, carimbo=agora, avisos=avisos)
        except Exception as e:                 # noqa: BLE001 — a tela mostra o motivo
            traceback.print_exc()
            return {"erro": "%s: %s" % (type(e).__name__, e)}
        finally:
            self._convertendo.clear()
        res["totais"]["arquivos"] = 0
        res["totais"]["separados"] = 0
        res["hora"], res["origem"] = agora.strftime("%H:%M"), "recoleta"
        res["recoleta"] = {"usina": usina, "celulas": len(cel)}
        self.resultado = res
        return self._fechar_resultado(res)

    # ------------------------------------------------------------ recoleta pelas fontes (recoleta_fontes.py, 17/11/2026)
    # O mesmo desenho da recoleta do .exe, para as sete fontes: a lista de usinas da fonte, o custo antes (simular), os
    # pedidos um a um com o andamento na tela e, no fim, a MESMA montagem da conversão. O estado fica na sessão (`_rf`).
    # O que a recoleta guarda (a lista da fonte, o plano, as respostas) mora na memória desta sessão, e o Nexus reinicia
    # a cada publicação, várias vezes por dia: em 18/11/2026 o Levi, com o painel aberto, levou "Abra de novo a recoleta
    # (a lista de usinas venceu)" logo depois de uma ("e a lista fica vencendo ainda, resolva!"). Agora o simular e o
    # plano refazem a lista sozinhos (`_rf_ou_refaz`); só o que se perdeu no MEIO de uma busca (as respostas já recebidas)
    # volta como `refazer`, e a tela recomeça a busca sozinha, uma vez.
    _VENCEU = {"erro": "O Nexus reiniciou no meio desta recoleta e o que já tinha vindo se perdeu. Clique em Recoletar de novo.",
               "refazer": True}

    def fontes_plantas(self, fonte, chave):
        """As usinas que dá para recoletar nesta fonte: as que ela conhece e que têm aba num BD lido."""
        if not chave:
            return {"erro": "Este Nexus não tem a chave da recoleta (NEXUS_SSO_CHAVE ou CONVERSOR_RECOLETA_CHAVE)."}
        # logo depois de um reinício a sessão ainda está lendo os BDs do banco em fundo: sem esperar, toda usina sairia
        # como "BD não foi lido" e a lista viria vazia
        self.pronto.wait(25)
        try:
            info = RF.plantas(fonte, chave)
        except RF.Falha as e:
            return {"erro": str(e)}
        except Exception as e:                 # noqa: BLE001 — a tela mostra o motivo
            traceback.print_exc()
            return {"erro": "%s: %s" % (type(e).__name__, e)}
        ctx = self.ctx()
        mapa, sem_aba, sem_bd, nomes = {}, [], set(), {}
        for usina, x in RF.por_usina(info.get("plantas")).items():
            d = x["destino"]
            if ctx.bd(d) is None:
                sem_bd.add(d)
                continue
            # só o NOME da aba: `ctx.aba` leria do banco a aba inteira de cada usina (18/11/2026: 14 s para as 75 da API
            # PV, só para saber se existem). Quem lê a aba é a montagem, e só a da usina pedida
            if d not in nomes:
                nomes[d] = set(ctx.abas(d))
            if usina in nomes[d]:
                mapa[usina] = x
            else:
                sem_aba.append(usina)
        self._rf = {"fonte": fonte, "chave": chave, "mapa": mapa, "max_dias": info.get("max_dias"),
                    "max_plantas": info.get("max_plantas"), "plano": [], "respostas": [], "pedido": None}
        return {"fonte": fonte, "nome": RF.NOMES[fonte],
                "usinas": [{"usina": u, "destino": x["destino"], "plantas": len(x["ids"])} for u, x in sorted(mapa.items())],
                "sem_aba": sorted(sem_aba), "sem_bd": sorted(sem_bd), "paga": bool(info.get("paga")),
                "teto": info.get("teto"), "cota_restante": info.get("cota_restante"), "max_dias": info.get("max_dias")}

    def _rf_de(self, fonte, usina):
        rf = getattr(self, "_rf", None)
        return rf if rf and rf["fonte"] == fonte and usina in rf["mapa"] else None

    def _rf_ou_refaz(self, fonte, usina, chave):
        """O estado da recoleta desta fonte e usina; sem ele (o Nexus reiniciou, ou a pessoa trocou de fonte em outra
        aba), refaz a lista da fonte na hora. -> (rf, None) ou (None, {"erro"})."""
        rf = self._rf_de(fonte, usina)
        if rf:
            return rf, None
        r = self.fontes_plantas(fonte, chave)
        if r.get("erro"):
            return None, r
        rf = self._rf_de(fonte, usina)
        if rf:
            return rf, None
        return None, {"erro": "%s não está na lista de %s (ou não tem aba num BD lido). Escolha a usina de novo."
                              % (usina, RF.NOMES.get(fonte, fonte))}

    def fontes_simular(self, fonte, usina, ini, fim, geracao, etm, chuva, chave=None):
        """Quanto esta recoleta gasta, antes de a pessoa confirmar: a plataforma faz a conta e nada é buscado."""
        rf, erro = self._rf_ou_refaz(fonte, usina, chave)
        if not rf:
            return erro
        try:
            pl = RF.plano(rf["mapa"][usina]["ids"], dt.date.fromisoformat(ini), dt.date.fromisoformat(fim),
                          rf["max_plantas"], rf["max_dias"])
            total, resta, teto = 0, None, None
            for ids, a, b in pl:
                r = RF.pedir(fonte, rf["chave"], ids, a, b, geracao, etm, chuva, simular=True)
                total += int(r.get("consultas") or 0)
                resta, teto = r.get("cota_restante"), r.get("teto")
        except RF.Falha as e:
            return {"erro": str(e)}
        except ValueError:
            return {"erro": "Período inválido."}
        return {"consultas": total, "cota_restante": resta, "teto": teto, "pedidos": len(pl)}

    def fontes_plano(self, fonte, usina, ini, fim, geracao, etm, chuva, chave=None):
        rf, erro = self._rf_ou_refaz(fonte, usina, chave)
        if not rf:
            return erro
        try:
            rf["plano"] = RF.plano(rf["mapa"][usina]["ids"], dt.date.fromisoformat(ini), dt.date.fromisoformat(fim),
                                   rf["max_plantas"], rf["max_dias"])
        except ValueError:
            return {"erro": "Período inválido."}
        rf["respostas"], rf["pedido"] = [], (usina, bool(geracao), bool(etm), bool(chuva))
        return {"pedidos": [[a.isoformat(), b.isoformat(), len(ids)] for ids, a, b in rf["plano"]]}

    def fontes_parte(self, i):
        """Um pedido à plataforma (um bloco de plantas num trecho de dias). A tela chama um por vez."""
        rf = getattr(self, "_rf", None)
        if not rf or not rf.get("pedido") or not 0 <= int(i) < len(rf["plano"]):
            return dict(self._VENCEU)
        _usina, geracao, etm, chuva = rf["pedido"]
        ids, a, b = rf["plano"][int(i)]
        try:
            r = RF.pedir(rf["fonte"], rf["chave"], ids, a, b, geracao, etm, chuva)
        except RF.Falha as e:
            return {"erro": str(e)}
        rf["respostas"].append(r)
        RF.anotar_cota(rf["fonte"], r.get("cota_restante"))
        return {"ok": True, "consultas": r.get("consultas"), "cota_restante": r.get("cota_restante")}

    def fontes_montar(self, agora=None):
        """O que veio da fonte vira células e passa pela MESMA montagem da conversão (a tela 2 de sempre)."""
        rf = getattr(self, "_rf", None)
        if not rf or not rf.get("pedido"):
            return dict(self._VENCEU)
        usina = rf["pedido"][0]
        destino, nome = rf["mapa"][usina]["destino"], RF.NOMES[rf["fonte"]]
        cel, av = RF.celulas(rf["respostas"], usina, destino)
        if not cel:
            return {"erro": "%s não devolveu nenhum valor de %s no período.%s"
                            % (nome, usina, (" " + " ".join(t for _n, t in av[:2])) if av else "")}
        self._convertendo.set()
        try:
            avisos = [montagem.Aviso(n, "Recoleta %s: %s" % (usina, t)) for n, t in av]
            agora = agora or dt.datetime.now()
            pasta = os.path.join(self.pasta_saida, agora.strftime("%d-%m"))
            res = montagem.montar([(c, RF.FONTE_DA_MONTAGEM % nome) for c in cel], self.ctx(), pasta, carimbo=agora,
                                  avisos=avisos)
        except Exception as e:                 # noqa: BLE001 — a tela mostra o motivo
            traceback.print_exc()
            return {"erro": "%s: %s" % (type(e).__name__, e)}
        finally:
            self._convertendo.clear()
        res["totais"]["arquivos"] = 0
        res["totais"]["separados"] = 0
        res["hora"], res["origem"] = agora.strftime("%H:%M"), "recoleta"
        res["recoleta"] = {"usina": usina, "celulas": len(cel), "fonte": nome}
        self.resultado = res
        return self._fechar_resultado(res)

    def fechar(self):
        for destino, b in list(self.bds.items()):
            if self.origem_bd.get(destino) == "arquivo":
                b.fechar()
        self.bds.clear()
        shutil.rmtree(self._tmp, ignore_errors=True)
        shutil.rmtree(self._pasta, ignore_errors=True)


# ------------------------------------------------------------------------- a chave da recoleta
# A plataforma só atende a recoleta a quem manda X-Recoleta-Chave. O .exe a lê de um arquivo na pasta da equipe; o Nexus
# a calcula no próprio ambiente, sem nada no git: a CONVERSOR_RECOLETA_CHAVE, se a T.I. a puser no .env, ou um HMAC da
# NEXUS_SSO_CHAVE (a mesma nos dois servidores, a da porta única) com um rótulo fixo. A plataforma aceita esse HMAC ao
# lado da chave do .exe (`plataforma/recoleta_apipv.py`): mudou o rótulo aqui, muda lá.
ROTULO_RECOLETA = b"nexus/coletas/recoleta/v1"


def chave_recoleta(cfg):
    v = str(cfg.get("CONVERSOR_RECOLETA_CHAVE") or os.environ.get("CONVERSOR_RECOLETA_CHAVE") or "").strip()
    if v:
        return v
    sso = str(cfg.get("NEXUS_SSO_CHAVE") or "").strip()
    return hmac.new(sso.encode("utf-8"), ROTULO_RECOLETA, hashlib.sha256).hexdigest() if sso else ""


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


def furos_paradas():
    """As paradas do COS e do Fracttal por usina e dia e as OS abertas (Conversor 1.0.13, `paradas.carregar` do .exe: lê o
    livro falhas_performance do db_performace, guarda 30 min; sem rede devolve {"erro"} e a tela segue sem explicação)."""
    return _paradas.carregar()


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
    # 1.0.13: a parada do COS/Fracttal explica o dia baixo (a mesma fonte da aba Para coletar). Como no .exe, o mural
    # fica guardado pela subida dos BDs, não pela hora das paradas; só a leitura que falhou não fica
    pd = furos_paradas()
    marca.append(bool(pd.get("erro")))
    marca = tuple(marca)
    with _TRAVA_MURAL:
        if marca in _MURAL:
            return _MURAL[marca]
    if sessao.origem_bd.get(BD_PERFORMANCE) == "arquivo":
        with _TRAVA_PORTAL:                # o .exe copia o Excel para um nome fixo no temp
            kwp = _mural.potencias(sessao.caminhos_bd.get(BD_PERFORMANCE))
    else:
        kwp = potencias_de_linhas(_equipamentos_do_banco(banco))
    out = {"linhas": _mural.calcular(bds, kwp, ini, fim, paradas_dados=pd), "limiar": _mural.LIMIAR,
           "ini": ini.isoformat(), "fim": fim.isoformat(), "paradas": bool(pd and not pd.get("erro")),
           "paradas_erro": (pd or {}).get("erro")}
    for d, bd in bds.items():
        if sessao.bds.get(d) is not bd:
            bd.fechar()                    # o do banco era só para esta conta: solta a memória
    with _TRAVA_MURAL:
        _MURAL.clear()
        if not pd.get("erro"):
            _MURAL[marca] = out
    return out
