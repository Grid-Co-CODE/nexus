# -*- coding: utf-8 -*-
"""Furos de coleta — a tela 3 do Conversor (Levi, 11/11/2026: "inclua também na versão 1.0.3 esse HTML porém deixe estilo
nexus, melhor os filtros e sempre centralize as tabelas").

Os dados NÃO são calculados aqui: vêm do relatório "Furos_Coleta_Performance*.html" (gerado fora do app, com BD, COS,
OS do Fracttal e tickets; o _18 de 11/11 tem out e nov, 144 usinas). Decisão do Levi: o app lê o MAIS NOVO da pasta de
publicação (SharePoint "4. O&M > 9.Pós Operação > 1. Performance", a mesma das versões do app) — quem gera solta lá e
todos veem igual. Na falta dele, o mais novo da pasta Downloads; e a pessoa pode abrir outro arquivo.

Do HTML saem duas coisas: `const DB={...};` (os meses, as usinas e o código de cada célula) e as confirmações embutidas
entre /*CONF0*/ e /*END0*/. As confirmações de cada pessoa ficam num JSON em %LOCALAPPDATA%\\Conversor Grid Co (o
WebView2 do app abre em modo privado: o localStorage do HTML original não sobreviveria a fechar o app)."""
import glob
import json
import os
import re

from conversor import atualizacao

PADRAO = "Furos_Coleta_Performance*.html"
PASTA_ESTADO = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Conversor Grid Co")
ARQ_ESTADO = os.path.join(PASTA_ESTADO, "furos.json")
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
_RX_DB = re.compile(r"^const DB=(\{.*\});\s*$", re.M)
_INI, _FIM = "/*CONF0*/", "/*END0*/"


def _estado():
    try:
        with open(ARQ_ESTADO, encoding="utf-8") as f:
            e = json.load(f)
        return e if isinstance(e, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar_estado(e):
    os.makedirs(PASTA_ESTADO, exist_ok=True)
    tmp = ARQ_ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False)
    os.replace(tmp, ARQ_ESTADO)


def pastas(caminho_bd_perf=None):
    """Onde procurar, na ordem: a pasta de publicação e a Downloads."""
    out = []
    pub = atualizacao.pasta_publicacao(caminho_bd_perf)
    if pub and os.path.isdir(pub):
        out.append(pub)
    if os.path.isdir(DOWNLOADS):
        out.append(DOWNLOADS)
    return out


def localizar(caminho_bd_perf=None, escolhido=None):
    """O relatório a mostrar: o que a pessoa abriu (se ainda existe), senão o mais novo da pasta de publicação, senão o
    mais novo da Downloads."""
    escolhido = escolhido or _estado().get("escolhido")
    if escolhido and os.path.isfile(escolhido):
        return escolhido
    for pasta in pastas(caminho_bd_perf):
        achados = [p for p in glob.glob(os.path.join(pasta, PADRAO)) if os.path.isfile(p)]
        if achados:
            return max(achados, key=os.path.getmtime)
    return None


def extrair(texto):
    """(db, conf) do HTML do relatório; ValueError se não for um relatório de furos."""
    m = _RX_DB.search(texto)
    if not m:
        raise ValueError("o arquivo não é um relatório de furos de coleta (não achei os dados 'const DB=')")
    db = json.loads(m.group(1))
    if not isinstance(db, dict) or not isinstance(db.get("months"), dict) or not db["months"]:
        raise ValueError("o relatório não tem nenhum mês")
    conf = {}
    i, j = texto.find(_INI), texto.find(_FIM)
    if i >= 0 and j > i:
        try:
            conf = json.loads(texto[i + len(_INI):j]) or {}
        except ValueError:
            conf = {}
    return db, conf


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        texto = f.read()
    db, conf = extrair(texto)
    return {"caminho": caminho, "nome": os.path.basename(caminho), "gerado": db.get("gen") or "",
            "modificado": os.path.getmtime(caminho), "db": {"months": db["months"], "gen": db.get("gen")},
            "conf_arquivo": conf}


def carregar(caminho_bd_perf=None, escolhido=None):
    """O que a tela recebe: o relatório lido e as confirmações desta pessoa. {"erro": ...} quando não dá."""
    p = localizar(caminho_bd_perf, escolhido)
    if not p:
        return {"erro": "Nenhum relatório de furos encontrado. Solte o Furos_Coleta_Performance mais novo na pasta "
                        "4. O&M > 9.Pós Operação > 1. Performance, ou clique em Abrir relatório.",
                "pastas": pastas(caminho_bd_perf)}
    try:
        r = ler(p)
    except (OSError, ValueError) as e:
        return {"erro": "Não consegui ler %s: %s" % (os.path.basename(p), e), "caminho": p}
    r["conf"] = _estado().get("conf") or {}
    return r


def escolher(caminho):
    e = _estado()
    e["escolhido"] = caminho
    _gravar_estado(e)


def esquecer_escolha():
    e = _estado()
    e.pop("escolhido", None)
    _gravar_estado(e)


def gravar_conf(conf):
    e = _estado()
    e["conf"] = conf if isinstance(conf, dict) else {}
    _gravar_estado(e)
    return True


def html_com_marcacoes(caminho, conf):
    """O HTML original com as confirmações embutidas (o "Salvar HTML com as marcações" do relatório)."""
    with open(caminho, encoding="utf-8") as f:
        texto = f.read()
    i, j = texto.find(_INI), texto.find(_FIM)
    if i < 0 or j < i:
        raise ValueError("o relatório não tem o lugar das confirmações (/*CONF0*/ ... /*END0*/)")
    js = json.dumps(conf, ensure_ascii=False).replace("*/", "*\\/").replace("</", "<\\/")
    return texto[:i + len(_INI)] + js + texto[j:]
