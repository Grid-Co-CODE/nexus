# -*- coding: utf-8 -*-
"""Uma conversão: os arquivos que a pessoa soltou na tela, o que cada um é, as perguntas em aberto e o resultado.

A tela (app.py) só fala com esta classe; o teste e a linha de comando também — a regra não mora no JavaScript."""
import datetime as dt
import os
import shutil
import tempfile
import threading
import traceback

from conversor import leitores as _leitores
from conversor import montagem
from conversor.nucleo import BD, BD_PADRAO, BD_PERFORMANCE, BD_THOPEN, SEM_USINA, Contexto, br, expandir

PASTA_SAIDA = os.path.join(os.path.expanduser("~"), "Downloads", "Conversor Grid Co")
NOME_LEVI = "Conversor - formatos novos"


def pasta_formatos_novos(bd_perf_caminho):
    """Arquivo que nenhum leitor reconhece vai para uma pasta ao lado do BD_Performance (OneDrive da equipe): o Levi vê
    sem ninguém precisar mandar. Sem o BD, vai para Downloads."""
    if bd_perf_caminho and os.path.isfile(bd_perf_caminho):
        return os.path.join(os.path.dirname(bd_perf_caminho), NOME_LEVI)
    return os.path.join(PASTA_SAIDA, NOME_LEVI)


class Sessao:
    def __init__(self, caminhos_bd=None, hoje=None, pasta_saida=PASTA_SAIDA):
        self.caminhos_bd = dict(BD_PADRAO)
        self.caminhos_bd.update(caminhos_bd or {})
        self.hoje = hoje
        self.pasta_saida = pasta_saida
        self.leitores = _leitores.carregar()
        self.bds = {}
        self.erros_bd = {}
        self.itens = []                       # cartões
        self._tmp = tempfile.mkdtemp(prefix="conversor_")
        self._seq = 0
        self._lock = threading.Lock()
        self.resultado = None

    # ------------------------------------------------------------ BDs
    def carregar_bds(self):
        for destino in (BD_PERFORMANCE, BD_THOPEN):
            self.carregar_bd(destino)

    def carregar_bd(self, destino, caminho=None):
        if caminho:
            self.caminhos_bd[destino] = caminho
        c = self.caminhos_bd.get(destino)
        velho = self.bds.pop(destino, None)
        if velho:
            velho.fechar()
        self.erros_bd.pop(destino, None)
        if not c or not os.path.isfile(c):
            self.erros_bd[destino] = "não encontrei o arquivo"
            return None
        try:
            self.bds[destino] = BD(destino, c)
        except Exception as e:                # BD aberto e travado, corrompido, OneDrive baixando
            self.erros_bd[destino] = "%s: %s" % (type(e).__name__, e)
            return None
        return self.bds[destino]

    def estado_bds(self):
        out = []
        for destino in (BD_PERFORMANCE, BD_THOPEN):
            b = self.bds.get(destino)
            out.append({"destino": destino, "caminho": self.caminhos_bd.get(destino),
                        "lido": bool(b), "lido_em": b.lido_em.strftime("%d/%m %H:%M") if b else None,
                        "erro": self.erros_bd.get(destino)})
        return out

    def ctx(self):
        return Contexto(self.bds, hoje=self.hoje)

    # ------------------------------------------------------------ cartões
    def adicionar(self, caminhos):
        novos = self.preparar(caminhos)
        for item in novos:
            self.reconhecer(item)
        return [self.cartao(i) for i in novos]

    def preparar(self, caminhos):
        """Cria os cartões em "identificando" (a tela mostra na hora; reconhecer um CSV de 15 MB leva segundos)."""
        novos = []
        for original in caminhos:
            with self._lock:
                self._seq += 1
                item = {"id": self._seq, "caminho": original, "nome": os.path.basename(original.rstrip("\\/")),
                        "tamanho": os.path.getsize(original) if os.path.isfile(original) else 0,
                        "estado": "identificando", "arqs": [], "recs": [], "escolha": None}
                self.itens.append(item)
            novos.append(item)
        return novos

    def dado_bruto(self, id_, i_arq=0, i_aba=0, inicio=0, n=500):
        """O arquivo como veio, separado em colunas (CSV pelo separador adivinhado), em páginas de `n` linhas (Levi,
        11/11/2026: "tem que ter a opção de ver o dado bruto separado por colunas também no caso de CSV")."""
        import datetime as _dt
        item = next((x for x in self.itens if x["id"] == id_), None)
        if not item:
            return {"erro": "o arquivo não está mais na lista"}
        if not item["arqs"]:
            item["arqs"] = [a for _, arqs in expandir([item["caminho"]], self._tmp) for a in arqs]
        arqs = item["arqs"]
        if not arqs:
            return {"erro": "não consegui abrir o arquivo"}
        i_arq = max(0, min(int(i_arq or 0), len(arqs) - 1))
        arq = arqs[i_arq]
        try:
            abas = arq.planilhas()
            if not abas:
                abas = [(arq.nome, [(l,) for l in arq.texto().splitlines()])]
        except Exception as e:                       # noqa: BLE001 — mostrar o erro é melhor que derrubar a tela
            return {"erro": "não consegui ler %s: %s" % (arq.nome, e), "arquivos": [a.nome for a in arqs]}
        i_aba = max(0, min(int(i_aba or 0), len(abas) - 1))
        nome, linhas = abas[i_aba]
        total = len(linhas)
        inicio = max(0, min(int(inicio or 0), max(total - 1, 0)))
        fatia = linhas[inicio:inicio + n]
        ncol = max((len(r) for r in fatia), default=0)

        def val(x):
            if x is None:
                return ""
            if isinstance(x, _dt.datetime):
                return x.strftime("%d/%m/%Y %H:%M:%S") if (x.hour or x.minute or x.second) else x.strftime("%d/%m/%Y")
            if isinstance(x, _dt.date):
                return x.strftime("%d/%m/%Y")
            if isinstance(x, bool):
                return str(x)
            if isinstance(x, (int, float)):
                return x
            return str(x)
        return {"arquivos": [a.nome for a in arqs], "i_arq": i_arq, "abas": [a[0] for a in abas], "i_aba": i_aba,
                "inicio": inicio, "n": n, "total": total, "ncol": ncol,
                "linhas": [[val(x) for x in r] + [""] * (ncol - len(r)) for r in fatia]}

    def reconhecer(self, item):
        if not item["arqs"]:
            item["arqs"] = [a for _, arqs in expandir([item["caminho"]], self._tmp) for a in arqs]
        if os.path.isdir(item["caminho"]):
            item["tamanho"] = sum(a.tamanho for a in item["arqs"])
        self._reconhecer(item)
        return self.cartao(item)

    def _reconhecer(self, item):
        ctx = self.ctx()
        recs = []
        for arq in item["arqs"]:
            # todos os leitores olham o arquivo; fica o que ACHOU a usina. O mensal INV do portal do Thopen tem o mesmo
            # cabeçalho do relatório da Sal ("Nome da usina | Horário | ... | Geração de energia"): o leitor da Sal
            # reconhecia e só perguntava a usina ("Altair 1 não está no de-para"), e o do mensal nunca rodava (10/11/2026)
            achados = []
            for lt in self.leitores:
                try:
                    r = lt.reconhecer(arq, ctx)
                except Exception:                 # leitor não pode derrubar a tela por um arquivo estranho
                    r = None
                if r:
                    r.leitor = lt
                    achados.append(r)
            if achados:
                melhor = next((r for r in achados if r.usinas), None) or                     next((r for r in achados if r.recusa), None) or achados[0]
                recs.append((arq, melhor))
        item["recs"] = recs
        if not recs:
            item["estado"] = "desconhecido"
        elif all(r.recusa for _, r in recs):
            item["estado"] = "recusado"
        elif any(not r.usinas and not r.recusa for _, r in recs) and not item["escolha"]:   # sem usina, com ou sem candidata
            item["estado"] = "pergunta_usina"
        else:
            item["estado"] = "ok"

    def cartao(self, item):
        recs = [r for _, r in item["recs"]]
        fontes = sorted({r.fonte for r in recs})
        usinas = sorted({u for r in recs for u in r.usinas} | ({item["escolha"]} if item["escolha"] else set()))
        pers = [r.periodo for r in recs if r.periodo]
        cand, perg = [], None
        for r in recs:
            if not r.usinas and r.candidatas:
                cand, perg = r.candidatas, r.pergunta
                break
        destinos = sorted({r.leitor.destino for r in recs})
        return {"id": item["id"], "nome": item["nome"], "tamanho": item["tamanho"], "estado": item["estado"],
                "fonte": ", ".join(fontes), "usinas": usinas, "destino": ", ".join(destinos),
                "periodo": ("%s a %s" % (br(min(p[0] for p in pers)), br(max(p[1] for p in pers)))) if pers else None,
                "detalhe": " · ".join(sorted({r.detalhe for r in recs if r.detalhe})),
                "pergunta": perg, "candidatas": cand,
                "todas_abas": self._abas_destino(destinos[0]) if cand and destinos else [],
                "fontes_conhecidas": sorted({lt.fonte for lt in self.leitores}),
                "membros": len(item["arqs"]), "reconhecidos": len(recs), "separado_para": item.get("separado_para"),
                "recusa": next((r.recusa for r in recs if r.recusa), None)}

    def _abas_destino(self, destino):
        b = self.bds.get(destino)
        return b.abas() if b else []

    def item(self, id_):
        return next((i for i in self.itens if i["id"] == id_), None)

    def responder_usina(self, id_, aba):
        it = self.item(id_)
        if it:
            it["escolha"] = aba
            it["estado"] = "ok"
            return self.cartao(it)

    def separar(self, id_, fonte=None):
        """Formato que ninguém reconhece: copia para a pasta do Levi, com a fonte que a pessoa disse no nome."""
        it = self.item(id_)
        if not it:
            return None
        destino = pasta_formatos_novos(self.caminhos_bd.get(BD_PERFORMANCE))
        os.makedirs(destino, exist_ok=True)
        pref = dt.datetime.now().strftime("%Y-%m-%d %Hh%M")
        nome = "%s - %s%s" % (pref, ("%s - " % fonte) if fonte else "", it["nome"])
        try:
            if os.path.isdir(it["caminho"]):
                shutil.copytree(it["caminho"], os.path.join(destino, nome))
            else:
                shutil.copy2(it["caminho"], os.path.join(destino, nome))
        except OSError as e:
            it["erro"] = str(e)
        it["estado"] = "separado"
        it["separado_para"] = destino
        return self.cartao(it)

    def remover(self, id_):
        self.itens = [i for i in self.itens if i["id"] != id_]

    def limpar(self):
        self.itens = []
        self.resultado = None

    def pendencias(self):
        # usina em aberto não trava mais: converte em "Sem usina" (Levi, 10/11/2026)
        return sum(1 for i in self.itens if i["estado"] in ("desconhecido", "identificando"))

    # ------------------------------------------------------------ conversão
    def converter(self, agora=None):
        agora = agora or dt.datetime.now()
        ctx = self.ctx()
        celulas, avisos = [], []
        av_leitor = {}
        convertidos = 0
        for it in self.itens:
            if it["estado"] not in ("ok", "pergunta_usina"):
                continue
            ok = False
            sem_usina = "%s · %s" % (SEM_USINA, it["nome"])
            for arq, rec in it["recs"]:
                if rec.recusa:
                    avisos.append(montagem.Aviso("leve", "%s: %s" % (arq.nome, rec.recusa)))
                    continue
                escolha = it["escolha"] or (SEM_USINA if not rec.usinas else None)
                try:
                    cel, av = rec.leitor.ler(arq, ctx, rec, escolha=escolha)
                    # leitor que escreveu na "Sem usina" genérica: uma aba por cartão, para dois arquivos de usinas
                    # diferentes não se misturarem
                    cel = [c._replace(aba=sem_usina) if c.aba == SEM_USINA else c for c in cel]
                except Exception as e:
                    avisos.append(montagem.Aviso("erro", "%s: não consegui ler (%s: %s)" % (arq.nome, type(e).__name__,
                                                                                           e)))
                    traceback.print_exc()
                    continue
                # o dia em que o relatório foi baixado ainda estava aberto no portal (Sal, 08/11/2026 12:41: o mensal
                # de novembro traz o 08/11 pela metade) — a data do arquivo é a da baixa
                try:
                    lim = dt.date.fromtimestamp(os.path.getmtime(arq.caminho))
                except OSError:
                    lim = None
                if lim:
                    abertos = [c for c in cel if c.data >= lim and c.data < ctx.hoje]
                    if abertos:
                        avisos.append(montagem.Aviso("info", "%s: %d valor(es) de %s em diante ficaram de fora — o "
                                                     "arquivo é desse dia, o dia ainda estava aberto"
                                                     % (arq.nome, len(abertos), lim.strftime("%d/%m"))))
                    cel = [c for c in cel if c.data < lim]
                ok = ok or bool(cel)
                celulas += [(c, rec.fonte) for c in cel]
                for a in av:                                 # texto, ou (nível, texto)
                    nivel, texto = a if isinstance(a, tuple) else ("leve", a)
                    av_leitor.setdefault((nivel, texto), []).append(arq.nome)
            convertidos += ok
        # o mesmo aviso de vários arquivos vira um só (4 relatórios diários da mesma usina = 1 aviso, não 4)
        for (nivel, texto), arqs in av_leitor.items():
            arqs = list(dict.fromkeys(arqs))
            onde = arqs[0] if len(arqs) == 1 else "%d arquivos" % len(arqs)
            avisos.append(montagem.Aviso(nivel, "%s: %s" % (onde, texto)))
        for e in _leitores.ERROS:
            avisos.append(montagem.Aviso("erro", e))
        pasta = os.path.join(self.pasta_saida, agora.strftime("%d-%m"))
        res = montagem.montar(celulas, ctx, pasta, carimbo=agora, avisos=avisos)
        res["totais"]["arquivos"] = convertidos
        res["totais"]["separados"] = sum(1 for i in self.itens if i["estado"] == "separado")
        res["pasta"] = pasta
        res["hora"] = agora.strftime("%H:%M")
        self.resultado = res
        return res

    def fechar(self):
        for b in self.bds.values():
            b.fechar()
        shutil.rmtree(self._tmp, ignore_errors=True)
