# -*- coding: utf-8 -*-
"""As validações dos furos de coleta (o `confirmacoes_furos.json` da analista) e as paradas congeladas do HTML R01, guardadas
no Nexus para todos verem o mesmo (Levi, 16/11/2026: "Nexus vira a fonte"; valida quem tem a tela Coletas, e fica quem e
quando).

Mora em `<NEXUS_DADOS>/coletas/furos/`, NÃO no banco: o banco tem leitura aberta e a regra 8 do `nexus/dados/CLAUDE.md`
não deixa texto livre nem nome de pessoa nos fatos (o comentário do analista e o "quem" são as duas coisas).

A REGRA PERMANENTE da analista (13/11/2026): "sempre manter as configurações já salvas". Daí:
- importar (o JSON dela ou o HTML com as marcações) só acrescenta ou atualiza: por chave, vence o `t` mais recente, e se
  o total cair a gravação é abortada (o `assert len(conf) >= n0` do build2.py);
- antes de importar, e na 1ª gravação de cada dia, uma cópia em `confirmacoes_backup/`;
- cada mudança vai para o `historico_confirmacoes.jsonl` (o antes, o depois, quem, quando): nada some sem rastro;
- quem grava manda o `t` que viu de cada chave; se outra pessoa gravou a mesma chave depois, NADA do pedido é gravado
  (a segunda pessoa a salvar não apaga a primeira; a tela recarrega e mostra o que está valendo);
- escrita num .tmp e troca de uma vez (os.replace); arquivo ilegível nunca é sobrescrito.
"""
import copy
import datetime as dt
import glob
import json
import os
import re
import shutil
import threading

MOTIVOS = ("sem_ipoa", "sem_ghi", "coleta_alt", "fora_op", "nao_mob", "os", "zero_real", "corrigido", "outro")
FONTES = ("BD_Performance", "BD_Thopen")
_RX_MES = re.compile(r"^\d{4}-\d{2}$")
OBS_MAX = 2000
COPIAS_MAX = 90
ARQ_CONF = "confirmacoes_furos.json"
ARQ_HIST = "historico_confirmacoes.jsonl"
ARQ_CONG = "paradas_congeladas.json"
PASTA_COPIAS = "confirmacoes_backup"


class Conflito(RuntimeError):
    """Outra pessoa gravou uma das chaves depois que esta tela leu."""

    def __init__(self, chaves):
        super().__init__("outra pessoa mudou a validação depois que você abriu a tela")
        self.chaves = chaves


class Ilegivel(RuntimeError):
    """O arquivo existe e não abre: nada se grava por cima."""


def agora_iso():
    """Como o `new Date().toISOString()` da tela da analista (UTC, milissegundos, Z)."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        "%03dZ" % (dt.datetime.now(dt.timezone.utc).microsecond // 1000)


def chave_ok(k):
    """"<fonte>|<usina>|<item>" ou "...@AAAA-MM" (§8.4)."""
    if not isinstance(k, str) or len(k) > 300:
        return False
    partes = k.split("|", 2)
    if len(partes) != 3 or partes[0] not in FONTES or not partes[1].strip() or not partes[2].strip():
        return False
    if "@" in partes[2]:
        mes = partes[2].rsplit("@", 1)[1]
        return bool(_RX_MES.match(mes))
    return True


def _vigencia_ok(v):
    return v == "*" or (isinstance(v, str) and v != "" and all(_RX_MES.match(x) for x in v.split(",")))


def normalizar(e, manter=False):
    """A entrada como a tela da analista grava: r (motivo, '' = só comentário), v (vigência), o (comentário), dm (dia ->
    motivo, por mês), t (quando) e, no Nexus, q (quem). ValueError se não for uma entrada."""
    if not isinstance(e, dict):
        raise ValueError("entrada não é um objeto")
    r = str(e.get("r") or "")
    if r and r not in MOTIVOS:
        raise ValueError("motivo desconhecido: %r" % r)
    v = str(e.get("v") if e.get("v") is not None else "")
    if not _vigencia_ok(v):
        raise ValueError("vigência inválida: %r" % v)
    out = {"r": r, "v": v, "o": str(e.get("o") or "")[:OBS_MAX]}
    dm = e.get("dm")
    if dm:
        if not isinstance(dm, dict):
            raise ValueError("dm não é um objeto")
        limpo = {}
        for mes, dias in dm.items():
            if not _RX_MES.match(str(mes)) or not isinstance(dias, dict):
                raise ValueError("dm inválido")
            dd = {}
            for dia, mot in dias.items():
                if not str(dia).isdigit() or not 1 <= int(dia) <= 31 or mot not in MOTIVOS:
                    raise ValueError("dia ou motivo inválido em dm")
                dd[str(int(dia))] = mot
            limpo[str(mes)] = dd
        out["dm"] = limpo
    if manter:
        if e.get("t"):
            out["t"] = str(e["t"])[:40]
        if e.get("q"):
            out["q"] = str(e["q"])[:120]
    return out


def para_tela3(conf, mes):
    """As validações na forma que a tela 3 do Conversor entende (a do .exe, de antes da validação por dia): o item
    inteiro, de UM mês ou de todos, na chave sem "@mês". Serve o "Para coletar": o que já foi validado no mês mais novo
    não entra na lista de coleta. A validação por dia fica de fora (lá o item segue pendente, que é o lado seguro)."""
    out = {}

    def simples(e, v):
        return {"r": e.get("r") or "", "v": v, "o": e.get("o") or "", "t": e.get("t") or ""}
    for k, e in conf.items():
        if "@" in k.split("|", 2)[-1] or not e.get("r") or (e.get("dm") or {}).get(mes):
            continue
        v = str(e.get("v") or "")
        out[k] = simples(e, "*" if v == "*" else (mes if mes in v.split(",") else v))
    for k, e in conf.items():                                # a entrada só do mês tem prioridade (§8.4)
        base, _a, m = k.rpartition("@")
        if "@" in k.split("|", 2)[-1] and m == mes:
            if e.get("r") and not (e.get("dm") or {}).get(mes):
                out[base] = simples(e, mes)
            else:
                out.pop(base, None)
    return out


def _gravar_json(caminho, dado):
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dado, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def _ler_json(caminho, vazio):
    if not os.path.exists(caminho):
        return vazio
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise Ilegivel(f"não consegui ler {os.path.basename(caminho)} ({e}); nada foi gravado") from e


class Confirmacoes:
    def __init__(self, pasta):
        self.pasta = pasta
        self.caminho = os.path.join(pasta, ARQ_CONF)
        self._trava = threading.Lock()

    def _doc(self):
        d = _ler_json(self.caminho, {"versao": 1, "rev": 0, "conf": {}})
        if not isinstance(d, dict) or not isinstance(d.get("conf"), dict):
            raise Ilegivel(f"{ARQ_CONF} não tem o formato das confirmações; nada foi gravado")
        return d

    def ler(self):
        with self._trava:
            d = self._doc()
            return copy.deepcopy(d["conf"]), int(d.get("rev") or 0)

    def _copia(self, sempre=False):
        if not os.path.exists(self.caminho):
            return None
        pasta = os.path.join(self.pasta, PASTA_COPIAS)
        os.makedirs(pasta, exist_ok=True)
        hoje = dt.datetime.now().strftime("%Y%m%d")
        feitas = sorted(glob.glob(os.path.join(pasta, "confirmacoes_furos_*.json")))
        if not sempre and feitas and os.path.basename(feitas[-1])[19:27] == hoje:
            return None
        destino = os.path.join(pasta, "confirmacoes_furos_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
        shutil.copy2(self.caminho, destino)
        for velho in sorted(glob.glob(os.path.join(pasta, "confirmacoes_furos_*.json")))[:-COPIAS_MAX]:
            try:
                os.remove(velho)
            except OSError:
                pass
        return destino

    def _historico(self, linhas):
        with open(os.path.join(self.pasta, ARQ_HIST), "a", encoding="utf-8") as f:
            for x in linhas:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")

    def aplicar(self, ops, quem):
        """`ops` = [{"k": chave, "v": entrada ou None (apagar), "base": o `t` que a tela viu ('' = não existia)}].
        Tudo ou nada: com uma chave mexida por outra pessoa depois, Conflito e nada se grava. -> (conf, rev)."""
        if not isinstance(ops, list) or not ops:
            raise ValueError("nenhuma mudança")
        limpas = []
        for op in ops:
            if not isinstance(op, dict) or not chave_ok(op.get("k")):
                raise ValueError("chave inválida: %r" % (op.get("k") if isinstance(op, dict) else op))
            limpas.append((op["k"], None if op.get("v") is None else normalizar(op["v"]), str(op.get("base") or "")))
        with self._trava:
            d = self._doc()
            conf = d["conf"]
            conflito = [k for k, _v, base in limpas if (conf.get(k) or {}).get("t", "") != base]
            if conflito:
                raise Conflito(conflito)
            t, hist = agora_iso(), []
            for k, v, _base in limpas:
                antes = conf.get(k)
                if v is None:
                    if antes is None:
                        continue
                    del conf[k]
                else:
                    v = dict(v, t=t, q=quem)
                    if antes is not None and {x: y for x, y in antes.items() if x not in ("t", "q")} == \
                            {x: y for x, y in v.items() if x not in ("t", "q")}:
                        continue                     # nada mudou de fato: fica o quem/quando de antes
                    conf[k] = v
                hist.append({"t": t, "q": quem, "acao": "validar", "k": k, "antes": antes, "depois": conf.get(k)})
            if hist:
                self._copia()
                d["rev"] = int(d.get("rev") or 0) + 1
                d["alterado_em"] = t
                _gravar_json(self.caminho, d)
                self._historico(hist)
            return copy.deepcopy(conf), int(d.get("rev") or 0)

    def importar(self, externo, quem, origem):
        """Funde as validações de fora (o JSON da analista, as do HTML): só acrescenta ou atualiza; vence o `t` mais recente;
        o total nunca cai. -> o resumo."""
        if not isinstance(externo, dict):
            raise ValueError("o arquivo não tem as confirmações")
        with self._trava:
            d = self._doc()
            conf = d["conf"]
            n0 = len(conf)
            res = dict(lidas=len(externo), novas=0, atualizadas=0, iguais=0, mais_novas_no_nexus=0, invalidas=0)
            for k, v in externo.items():
                try:
                    if not chave_ok(k):
                        raise ValueError("chave")
                    e = normalizar(v, manter=True)
                except ValueError:
                    res["invalidas"] += 1
                    continue
                a = conf.get(k)
                if a is None:
                    conf[k] = e
                    res["novas"] += 1
                elif (e.get("t") or "") > (a.get("t") or ""):
                    conf[k] = e
                    res["atualizadas"] += 1
                elif e == a:
                    res["iguais"] += 1
                else:
                    res["mais_novas_no_nexus"] += 1
            if len(conf) < n0:                       # o build2.py: "ERRO: perdeu confirmações"
                raise RuntimeError("a importação reduziria as validações; nada foi gravado")
            res.update(antes=n0, total=len(conf))
            if res["novas"] or res["atualizadas"]:
                res["copia"] = os.path.basename(self._copia(sempre=True) or "")
                d["rev"] = int(d.get("rev") or 0) + 1
                d["alterado_em"] = agora_iso()
                _gravar_json(self.caminho, d)
                self._historico([{"t": d["alterado_em"], "q": quem, "acao": "importar", "origem": origem,
                                  **{x: res[x] for x in ("lidas", "novas", "atualizadas", "antes", "total")}}])
            res["rev"] = int(d.get("rev") or 0)
            return res


class Congeladas:
    """As paradas que o Nexus não refaz (outubro inteiro e os tickets que entram em novembro), tiradas do HTML R01. Um
    mês já congelado só é trocado por um HTML gerado DEPOIS (o `gen` dele): importar um relatório velho não desfaz."""

    def __init__(self, pasta):
        self.caminho = os.path.join(pasta, ARQ_CONG)
        self._trava = threading.Lock()
        self._guarda = None

    def ler(self):
        with self._trava:
            try:
                mt = os.path.getmtime(self.caminho)
            except OSError:
                return {}
            if self._guarda and self._guarda[0] == mt:
                return self._guarda[1]
            d = _ler_json(self.caminho, {})
            self._guarda = (mt, d)
            return d

    def meses(self):
        return {m: x["usinas"] for m, x in (self.ler().get("meses") or {}).items()}

    def importar(self, congelado, gen, origem, quem):
        def quando(g):
            try:
                return dt.datetime.strptime(str(g), "%d/%m/%Y %H:%M")
            except ValueError:
                return dt.datetime.min
        with self._trava:
            d = _ler_json(self.caminho, {"versao": 1, "meses": {}})
            trocados, mantidos = [], []
            for m, usinas in congelado.items():
                atual = d["meses"].get(m)
                if atual and quando(atual.get("gen")) >= quando(gen):
                    mantidos.append(m)
                    continue
                d["meses"][m] = {"usinas": usinas, "gen": gen, "origem": origem, "importado_em": agora_iso(),
                                 "quem": quem}
                trocados.append(m)
            if trocados:
                _gravar_json(self.caminho, d)
                self._guarda = None
            return dict(congelados=trocados, mantidos=mantidos)
