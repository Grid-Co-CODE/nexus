# -*- coding: utf-8 -*-
"""Os modelos da inspeção de chamado — base, tipo de ativo e fornecedor — no banco da Gridco, editáveis pela tela
"Controle de fornecedores" do OS Creator web.

Pedido do Levi em 27/09/2026: "as subtarefas padrões utilizadas para a criação de chamado no inspeção de chamados …
mudam por ativo e fornecedor … algo parecido com o PCM no OS Creator app na parte de administração dos temas".

O MOLDE É O `temas_store.py`: o mesmo workbook (`os_creator`), a mesma forma chave/valor em JSON e o CÓDIGO como
semente e rede de segurança. As chaves:

    BASE                  toda inspeção, de qualquer ativo e fornecedor
    TIPO:<tipo de ativo>  o bloco do tipo ("TIPO:Inversor", "TIPO:Estrutura Trackers"…)
    MARCA:<fornecedor>    o que o fornecedor pede a mais, o canal de abertura e os tipos que ele atende

Bloco sem linha no banco vale o do código. Com o banco fora do ar a tela funciona igual — só não salva.

O App de Campo: carrega a SUA cópia do pacote `chamado_garantia`, e é por ele que o técnico abre a maioria das
inspeções. Desde 20/10/2026 a regra de pôr esta aba por cima do código mora no pacote (`chamado_garantia.registro`),
para o App ler a mesma aba e aplicar igual (Levi: "quando a singrid adicione novos fabricantes em chamados > fabricantes
apareça atualizado no app"). Enquanto o App não publicar a versão que lê a aba, ele segue no código.

COMO VALE NO PROCESSO: `aplicar()` reescreve, EM MEMÓRIA e NO LUGAR, as estruturas do `chamado_garantia.spec`
(`registro.aplicar`) e o `chamado_spec.CANAL` (o canal de abertura, que é só do OS Creator). No lugar, e não trocando o
objeto, porque o `chamado_insp_spec` fez `from chamado_garantia.spec import BASE, POR_TIPO, …` — nomes presos ao objeto
de origem. Nada no disco muda.

QUEM APLICA: o os_web chama `garantir()` antes de cada rota da Inspeção (TTL de 5 min). O app de mesa lê UMA vez, na
abertura (`modelos_banco.py`: `carregar` no worker, `aplicar` na thread da interface) — o que se salva aqui chega nele
na próxima vez que ele abrir.
"""
import copy
import datetime as dt
import json
import re
import threading
import time

import chamado_insp_spec  # noqa: F401 — a ponte põe a raiz do repositório no sys.path, onde o pacote mora
import chamado_spec as cs
import gridco_abas as ga
from chamado_garantia import registro as R
from chamado_garantia import spec as sp

WORKBOOK = R.WORKBOOK
NOME_ABA = R.ABA
COLUNAS = list(R.COLUNAS)
TTL = 300          # s: de quanto em quanto tempo o processo relê o banco (a edição de outra máquina chega assim)
TTL_ERRO = 60      # s: banco fora do ar → tenta de novo depois disto, sem travar cada requisição

ABA = ga.Aba(WORKBOOK, NOME_ABA, COLUNAS)
SemCredencial = ga.SemCredencial

TIPOS = tuple(sp.TIPO_ID)                       # texto, longo, num, simnao, verif, lista
LIMITE_DESC = 250
LIMITE_CANAL = 300
LIMITE_NOME = R.LIMITE_NOME


class Conflito(RuntimeError):
    """O bloco mudou no banco entre a leitura da tela e o clique em salvar."""

    def __init__(self, por: str, versao: str):
        self.por, self.versao = por, versao
        super().__init__("alguém salvou este bloco depois que você abriu a tela%s. Recarregue para ver a versão nova."
                         % ((" (%s)" % por) if por else ""))


# ── a foto do código (a do pacote, tirada na importação dele) e o canal, que é só daqui ─────────────────────────────
_ORIG = dict(R._ORIG, CANAL=copy.deepcopy(dict(cs.CANAL)))
# No código, Brametal e Romiotto não têm lista própria: são o MESMO objeto da STI e da Hukseflux (chamado_spec,
# "CLONES (28/07)"). Enquanto ninguém salvar o clone sozinho, ele segue o original — inclusive a versão editada dele.
CLONES = R.CLONES

_estado = {"banco": None, "lido": 0.0, "proxima": 0.0, "erro": ""}
_trava = threading.Lock()


def agora_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).replace(microsecond=0).isoformat()


# ── subtarefa e chave: as do pacote (o App aplica com as mesmas) ───────────────────────────────────────────────
para_json = R.para_json
de_json = R.de_json
chave_valida = R.chave_valida


def semente() -> dict:
    """Os blocos como estão no código — o valor inicial e a rede de segurança (com o canal daqui)."""
    return R.semente(_ORIG["CANAL"])


# ── leitura ───────────────────────────────────────────────────────────────────────────────────────────────────
def _linhas() -> list:
    """As linhas cruas da aba — o ÚNICO ponto que vai à rede na leitura (os testes trocam só este)."""
    return ABA.linhas()


def _de_linha(l: dict):
    """Linha do banco → (chave, valor) ou None. Linha ilegível é PULADA: um JSON estragado num fornecedor não pode
    tirar os outros da tela (`registro.de_registro`, a mesma leitura do App)."""
    return R.de_registro(ABA.registro(l))


def carregar(forcar: bool = False) -> dict:
    """{chave: valor} do banco (cache de TTL). Levanta se o banco não responder — quem chama decide o que fazer."""
    with _trava:
        if _estado["banco"] is not None and not forcar and time.time() - _estado["lido"] < TTL:
            return _estado["banco"]
    # chave repetida (duas máquinas criando o mesmo fornecedor ao mesmo tempo): vale a versão mais nova
    banco = R.de_linhas(ABA.registro(l) for l in _linhas())
    with _trava:
        _estado.update(banco=banco, lido=time.time())
    return banco


def efetivo(banco: dict = None) -> dict:
    """Cada bloco como vale AGORA: o do banco quando existe, o do código quando não. `origem` diz qual."""
    if banco is None:
        banco = _estado["banco"] or {}
    return R.efetivo(banco, _ORIG["CANAL"])


_trocar_dict = R._trocar_dict


def aplicar(banco: dict = None):
    """Joga os blocos do banco por cima do código, em memória, no lugar (`registro.aplicar`, a mesma regra do App), e o
    canal de abertura de cada fornecedor no `chamado_spec.CANAL`. Sem banco (ou `{}`), volta ao código puro."""
    banco_efetivo = (_estado["banco"] or {}) if banco is None else banco
    R.aplicar(banco_efetivo)
    canal = dict(_ORIG["CANAL"])
    for ch, v in efetivo(banco_efetivo).items():
        if ch.startswith("MARCA:") and not v.get("arquivado"):
            canal[ch[6:]] = str(v.get("canal") or "")
    _trocar_dict(cs.CANAL, canal)


def garantir():
    """Relê o banco se a última leitura passou do TTL e aplica. Nunca levanta: sem banco, fica o que já estava."""
    agora = time.time()
    if agora < _estado["proxima"]:
        return
    with _trava:
        if agora < _estado["proxima"]:
            return
        _estado["proxima"] = agora + TTL                  # os outros threads não repetem a leitura enquanto esta roda
    try:
        aplicar(carregar(forcar=True))
        _estado["erro"] = ""
    except Exception as e:                               # noqa: BLE001 — banco fora: segue o que já estava aplicado
        _estado.update(proxima=time.time() + TTL_ERRO, erro=str(e)[:200])


# ── validação ─────────────────────────────────────────────────────────────────────────────────────────────────
def _limpa(s) -> str:
    return " ".join(str(s or "").split())


def normalizar(chave: str, dados: dict) -> tuple:
    """(valor pronto para gravar, erro). A régua é a do pacote: tipo conhecido, lista com opções, nada repetido, e
    fornecedor com pelo menos um tipo de ativo — senão ele não aparece para ninguém escolher."""
    if not chave_valida(chave):
        return None, "Bloco desconhecido: %s." % chave
    dados = dados if isinstance(dados, dict) else {}
    marca = chave.startswith("MARCA:")
    atende = []
    if marca:
        atende = sorted({str(t) for t in (dados.get("atende") or []) if str(t) in _ORIG["POR_TIPO"]})
        if not atende and not dados.get("arquivado"):
            return None, "Diga que tipo de ativo este fornecedor atende — sem isso ele não aparece na inspeção."
    subs, vistos = [], set()
    for i, s in enumerate(dados.get("subtarefas") or [], 1):
        if not isinstance(s, dict):
            return None, "Pergunta %d ilegível." % i
        desc = _limpa(s.get("desc"))
        if not desc:
            return None, "A pergunta %d está vazia." % i
        if len(desc) > LIMITE_DESC:
            return None, "A pergunta %d passa de %d caracteres." % (i, LIMITE_DESC)
        if desc.lower() in vistos:
            return None, "A pergunta \"%s\" aparece duas vezes." % desc[:60]
        vistos.add(desc.lower())
        tipo = s.get("tipo") if s.get("tipo") in TIPOS else None
        if not tipo:
            return None, "Tipo desconhecido na pergunta %d." % i
        opcoes = []
        if tipo == "lista":
            for o in s.get("opcoes") or []:
                o = _limpa(o)
                if o and o.lower() not in {x.lower() for x in opcoes}:
                    opcoes.append(o)
            if len(opcoes) < 2:
                return None, "A pergunta \"%s\" é Lista e precisa de pelo menos duas opções." % desc[:60]
        so_para = sorted({str(t) for t in (s.get("so_para") or []) if str(t)})
        if marca and so_para and not set(so_para) <= set(atende):
            return None, "A pergunta \"%s\" vale para um tipo que o fornecedor não atende." % desc[:60]
        if not marca:
            so_para = []                                  # base e bloco do tipo valem sempre para o bloco inteiro
        chave_campo = re.sub(r"[^a-z0-9_]", "", str(s.get("chave") or "").lower())[:30]
        subs.append({"desc": desc, "tipo": tipo, "obrig": bool(s.get("obrig")), "anexo": bool(s.get("anexo")),
                     "opcoes": opcoes, "chave": chave_campo, "so_para": so_para})
    if chave == "BASE" and not subs:
        return None, "A base precisa de pelo menos uma pergunta — ela abre toda inspeção."
    valor = {"subtarefas": subs}
    if marca:
        canal = _limpa(dados.get("canal"))
        if len(canal) > LIMITE_CANAL:
            return None, "O canal de abertura passa de %d caracteres." % LIMITE_CANAL
        valor.update(canal=canal, atende=atende, arquivado=bool(dados.get("arquivado")))
    return valor, ""


# ── escrita ───────────────────────────────────────────────────────────────────────────────────────────────────
def salvar(chave: str, dados: dict, versao_lida: str, quem: str) -> dict:
    """Grava UM bloco e aplica na hora neste processo.

    RELÊ ANTES DE GRAVAR, sempre: o `row_number` não é chave (muda quando linha entra ou sai) e a versão que a tela
    leu tem de ser a que está no banco — senão a edição de outra pessoa sumiria em silêncio."""
    valor, erro = normalizar(chave, dados)
    if erro:
        raise ValueError(erro)
    if not ga.pode_gravar():
        raise SemCredencial("Este servidor não tem a credencial de escrita do banco da Gridco: dá para ver os "
                            "modelos, mas não para salvar.")
    banco = carregar(forcar=True)
    atual = banco.get(chave)
    if str(versao_lida or "") != str((atual or {}).get("versao") or ""):
        raise Conflito((atual or {}).get("por") or "", (atual or {}).get("versao") or "")
    valor.update(versao=agora_iso(), por=str(quem or "").strip())
    registro = {"chave": chave, "valor": json.dumps(valor, ensure_ascii=False)}
    if atual and atual.get("_linha"):
        ABA.trocar(atual["_linha"], registro)
    else:
        ABA.inserir(registro)
    aplicar(carregar(forcar=True))
    _estado["proxima"] = time.time() + TTL
    return valor
