"""Os relatórios de análise de falha da Engenharia: o FMEA e a causa raiz de um ativo da Confiabilidade (Levi,
29/10/2026: "Tem que ter emitir FEMEA emitir causa raiz do pcm.gridco.com.br use como referência e implemente").

A referência é o módulo Confiabilidade do painel do PCM: as duas folhas (o FMEA com o RPN = ocorrência x severidade x
detecção; a causa raiz com os cinco porquês e a matriz GUT), a biblioteca de modos de falha (`biblioteca_falhas`) e o
número FMEA-AAAA-NNNN / RCA-AAAA-NNNN com a revisão R00. Lá o emitido ia para um arquivo do repositório do PCM; aqui vai
para o banco, no livro `nexus_engenharia_relatorios`, registrado no catálogo antes da 1ª gravação (regra 10):

- `fato_relatorio_falha`: 1 linha = 1 EMISSÃO (uma revisão) de 1 relatório, FMEA ou causa raiz, de 1 ativo. Só
  acrescenta: corrigir é emitir a revisão seguinte do mesmo número (R01, R02...), e cada linha guarda a folha inteira.

A API do banco tem LEITURA ABERTA (nexus/dados/CLAUDE.md, regra 8): em claro só os IDs (o ativo pelo código canônico e o
`equipamento_id`, a usina pelo `usina_id` da Confiabilidade, quem emitiu pelo `pessoa_hmac`, o acompanhamento), o número,
o tipo, a revisão, o padrão que a biblioteca reconheceu e o tipo de falha (listas fechadas) e as notas do RPN. O texto
da análise, a equipe e os responsáveis (nomes), a foto do ativo e das OS que motivaram vão só CIFRADOS (o Cofre, como o
acompanhamento). A foto é o que a folha mostra depois: a janela de 30 dias anda, e o relatório não pode mudar com ela.

Gravar troca o livro inteiro, relido do banco antes (leitura que falha não grava), uma gravação por vez neste processo
(`_TRAVA`, que também segura o número: dois emitindo juntos não pegam o mesmo).
"""
import json
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from ..dados import livros
from ..dados.equipamento import canon, equipamento_id
from . import acompanhamento as AC
from . import biblioteca_falhas as B

LIVRO, NOME_LIVRO = "nexus_engenharia_relatorios", "Nexus · FMEA e causa raiz da Engenharia"
ABA = "fato_relatorio_falha"
CAB = ("id", "registrado_em", "data_id", "numero", "tipo", "revisao", "codigo_ativo", "equipamento_id", "usina_id",
       "usina_ligada_por", "acompanhamento_id", "pessoa_hmac", "padrao_biblioteca", "tipo_falha", "falhas_30d_qtd",
       "ocorrencia_nivel", "severidade_nivel", "deteccao_nivel", "rpn_pts", "dados_cifrados")
# tipo: (o prefixo do número, o nome curto, o título da folha)
TIPOS = {"fmea": ("FMEA", "FMEA", "FMEA: análise de modos de falha e efeitos"),
         "rca": ("RCA", "Causa raiz", "Análise de causa raiz")}
# a lista fechada do tipo de falha (no PCM era um campo livre com estas cinco sugestões)
TIPOS_FALHA = (("eletrica", "Elétrica"), ("mecanica", "Mecânica"), ("comunicacao", "Comunicação"),
               ("ambiental", "Ambiental"), ("operacao", "Operação"))
ACOES = 3                                   # as linhas de ação das duas folhas (a biblioteca traz três)
TEXTO_MAX, LONGO_MAX = 300, 2000
LONGOS = {"descricao": LONGO_MAX}            # a descrição da falha da causa raiz é o único texto longo
_I = range(1, ACOES + 1)
# os campos que cada folha grava; o que vier além disso fica fora
TEXTO = {
    "fmea": ("equipe", "elaboracao", "revisao_resp", "componente", "modo_1", "efeito_1", "causa_1", "modo_2",
             "efeito_2", "causa_2", *[f"acao_{i}" for i in _I], *[f"acao_resp_{i}" for i in _I]),
    "rca": ("equipe", "descricao", *[f"pq_{i}" for i in range(1, 6)], "causa_raiz", "causa", "deteccao_metodo",
            *[f"acao_{i}" for i in _I], *[f"acao_resp_{i}" for i in _I], "resultado"),
}
DATAS = {"fmea": tuple(f"acao_prazo_{i}" for i in _I),
         "rca": (*[f"acao_prazo_{i}" for i in _I], "verificar_em")}
NUMEROS = {
    "fmea": {"sev": (1, 10, "Severidade"), "det": (1, 10, "Detecção"),
             **{f"acao_rpn_{i}": (1, 1000, f"O RPN depois da ação {i}") for i in _I}},
    "rca": {**{f"g_{i}": (1, 5, f"Gravidade da ação {i}") for i in _I},
            **{f"u_{i}": (1, 5, f"Urgência da ação {i}") for i in _I},
            **{f"t_{i}": (1, 5, f"Tendência da ação {i}") for i in _I}},
}
ROTULO_DATA = {**{f"acao_prazo_{i}": f"O prazo da ação {i}" for i in _I}, "verificar_em": "O \"verificar em\""}
TTL_S = 60
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()
_CACHE: dict = {}

Recusada = AC.Recusada


def limpar() -> None:
    """Zera a cópia: quem acabou de emitir tem de se ver na próxima leitura."""
    _CACHE.clear()


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _ctx(rid) -> str:
    return f"banco/engenharia_relatorios/{rid}/dados"


def _ler_banco(base: str, sessao) -> list[dict]:
    """A aba lida agora (uma listagem e uma leitura). Livro que ainda não existe = vazio. Erro sobe."""
    a = livros.abas(base, sessao, LIVRO)
    return livros._linhas(base, sessao, a[ABA]) if ABA in a else []


def ler(forcar: bool = False) -> dict:
    """{"linhas", "lido_em", "erro"}, guardado por 1 minuto. Leitura que falha devolve a última boa com o erro; sem
    nenhuma, vazio com o erro (a tela diz que não leu, e não "nenhum relatório")."""
    g = _CACHE.get("livro")
    if g and not forcar and time.time() - g["lido_em"] < TTL_S:
        return g
    try:
        linhas = _ler_banco(*AC._banco())
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a tela diz e não deixa emitir
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        if g:
            return dict(g, erro=erro, velha=True)
        return {"linhas": [], "lido_em": None, "erro": erro}
    g = {"linhas": linhas, "lido_em": time.time(), "erro": ""}
    _CACHE["livro"] = g
    return g


def _abre(cofre, l: dict) -> dict:
    if not cofre or not l.get("dados_cifrados"):
        return {}
    try:
        return json.loads(cofre.decifrar(_txt(l.get("dados_cifrados")), _ctx(_txt(l.get("id")))))
    except Exception:           # noqa: BLE001 — cifra de outra chave ou adulterada: sai sem o texto
        return {}


def _revisao(cofre, l: dict) -> dict:
    tipo = _txt(l.get("tipo"))
    dados = _abre(cofre, l)
    q = AC._quando(l.get("registrado_em"))
    rev = AC._int(l.get("revisao")) or 0
    return {"id": _txt(l.get("id")), "numero": _txt(l.get("numero")), "tipo": tipo,
            "tipo_txt": TIPOS.get(tipo, ("", tipo or "—", ""))[1], "titulo": TIPOS.get(tipo, ("", "", tipo))[2],
            "revisao": rev, "rev_txt": f"R{rev:02d}", "quando": q, "data_txt": q.strftime("%d/%m/%Y") if q else "—",
            "cod": _txt(l.get("codigo_ativo")), "equipamento_id": AC._int(l.get("equipamento_id")),
            "usina_id": AC._int(l.get("usina_id")), "usina_ligada_por": _txt(l.get("usina_ligada_por")),
            "acompanhamento_id": _txt(l.get("acompanhamento_id")),
            "pessoa_hmac": _txt(l.get("pessoa_hmac")),
            "autor": ((dados.get("quem") or {}).get("nome") or ""), "padrao": _txt(l.get("padrao_biblioteca")),
            "tipo_falha": _txt(l.get("tipo_falha")), "falhas30": AC._int(l.get("falhas_30d_qtd")),
            "occ": AC._int(l.get("ocorrencia_nivel")), "sev": AC._int(l.get("severidade_nivel")),
            "det": AC._int(l.get("deteccao_nivel")), "rpn": AC._int(l.get("rpn_pts")),
            "ativo": dados.get("ativo") or {}, "os": dados.get("os") or [], "medido": dados.get("medido") or {},
            "campos": dados.get("campos") or {}}


def relatorios(linhas: list[dict]) -> list[dict]:
    """[{"numero", "tipo", "revisoes" (da R00 à última), "ultima"}], o emitido por último primeiro. A linha sem número
    (gravada por fora) fica fora."""
    cofre = AC._cofre_ou_nada()
    por: dict[str, list] = {}
    for i, l in enumerate(linhas):
        if _txt(l.get("numero")):
            por.setdefault(_txt(l.get("numero")), []).append((i, _revisao(cofre, l)))
    nunca = datetime.min.replace(tzinfo=_BRT)
    out = []
    for numero, revs in por.items():
        revs = [r for _, r in sorted(revs, key=lambda x: (x[1]["revisao"], x[0]))]
        out.append({"numero": numero, "tipo": revs[-1]["tipo"], "revisoes": revs, "ultima": revs[-1]})
    out.sort(key=lambda r: (r["ultima"]["quando"] or nunca, r["numero"]), reverse=True)
    return out


def por_ativo(rels: list[dict]) -> dict[str, list[dict]]:
    """{código canônico: a última revisão de cada relatório do ativo, o mais recente primeiro}."""
    out: dict[str, list] = {}
    for r in rels:
        out.setdefault(canon(r["ultima"]["cod"]), []).append(r["ultima"])
    return out


def achar(rels: list[dict], numero) -> dict | None:
    n = _txt(numero).upper()
    return next((r for r in rels if r["numero"].upper() == n), None)


def proximo_numero(linhas: list[dict], tipo: str, ano: int) -> str:
    """O próximo número do tipo no ano (o maior + 1: um número que faltou não volta a ser usado)."""
    pref = TIPOS[tipo][0]
    rx = re.compile(rf"^{pref}-{ano}-(\d+)$", re.I)
    ns = [int(m.group(1)) for l in linhas if (m := rx.match(_txt(l.get("numero"))))]
    return f"{pref}-{ano}-{max(ns, default=0) + 1:04d}"


def limpar_campos(tipo: str, campos: dict) -> dict:
    """Os campos da folha `tipo` como vão ao livro: só os que a folha tem, o texto sem espaços sobrando e com teto, as
    datas em AAAA-MM-DD, as notas dentro da escala. Fora disso, Recusada com o porquê (nada se corta calado)."""
    out: dict = {}
    for k in TEXTO[tipo]:
        v = " ".join(_txt(campos.get(k)).split()) if k not in LONGOS else _txt(campos.get(k))
        teto = LONGOS.get(k, TEXTO_MAX)
        if len(v) > teto:
            raise Recusada(f"Um campo da folha passa de {teto} letras: encurte e emita de novo")
        if v:
            out[k] = v
    for k in DATAS[tipo]:
        v = _txt(campos.get(k))
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise Recusada(f"{ROTULO_DATA[k]} precisa ser uma data") from None
            out[k] = v
    for k, (mn, mx, rot) in NUMEROS[tipo].items():
        v = _txt(campos.get(k))
        if not v:
            continue
        n = AC._int(v)
        if n is None or not mn <= n <= mx:
            raise Recusada(f"{rot} vai de {mn} a {mx}")
        out[k] = n
    tf = _txt(campos.get("tipo_falha"))
    if tf:
        if tf not in dict(TIPOS_FALHA):
            raise Recusada("Tipo de falha fora da lista")
        out["tipo_falha"] = tf
    return out


def _foto(ativo: dict) -> tuple[dict, list, dict]:
    """O que a folha mostra depois, como estava na emissão: o ativo, as OS que pesaram (sem quem atendeu nem a nota do
    técnico, que pode ter nome) e as contas da Confiabilidade."""
    a = {k: ativo.get(k) for k in ("cod", "nome", "usina", "cliente", "uf", "fam", "crit", "circuito")}
    oss = [{k: o.get(k) for k in ("os", "t", "tipo", "d", "st", "servico")} for o in ativo.get("os") or []]
    medido = {k: ativo.get(k) for k in ("nivel", "nFalha", "n7", "n30", "p90", "mtbf", "mttr", "disp", "soServico",
                                        "porQue")}
    return a, oss, medido


def emitir(tipo: str, ativo: dict, campos: dict, usuario, pode: bool, *, acompanhamento_id: str | None = None,
           de: str | None = None) -> dict:
    """Emite o relatório `tipo` ("fmea" ou "rca") do ativo (o item da Confiabilidade: {"cod", "nome", "usina",
    "usina_id", "ligada_por", "nFalha", "os", ...}) com os `campos` da folha. `de` = o número de um relatório já
    emitido: a revisão seguinte dele (o mesmo tipo e o mesmo ativo). Devolve a linha gravada."""
    quem = AC._quem(usuario, pode, "emite FMEA e causa raiz")
    if tipo not in TIPOS:
        raise Recusada("Relatório de tipo desconhecido: é FMEA ou causa raiz")
    cod = canon(ativo.get("cod"))
    if not cod:
        raise Recusada("Ativo sem código")
    c = limpar_campos(tipo, campos or {})
    if tipo == "fmea" and not c.get("modo_1"):
        raise Recusada("Escreva o modo de falha (a primeira linha da análise da falha) antes de emitir")
    if tipo == "rca" and not c.get("causa_raiz"):
        raise Recusada("Escreva a causa raiz (a conclusão dos cinco porquês) antes de emitir")
    cofre = AC._cofre()
    p = B.pre(ativo)
    n_falha = AC._int(ativo.get("nFalha"))
    occ = B.ocorrencia(n_falha) if tipo == "fmea" else None
    sev = c.get("sev", p["sev"]) if tipo == "fmea" else None
    det = c.get("det", p["det"]) if tipo == "fmea" else None
    with _TRAVA:
        linhas = _ler_banco(*AC._banco())
        agora = datetime.now(timezone.utc)
        if de:
            ant = achar(relatorios(linhas), de)
            if not ant:
                raise Recusada(f"Nova revisão: não achei o relatório {de} no livro (recarregue a página)")
            if ant["tipo"] != tipo:
                raise Recusada(f"O {ant['numero']} é {TIPOS.get(ant['tipo'], ('', ant['tipo']))[1]}: a nova revisão é do "
                               "mesmo tipo")
            if canon(ant["ultima"]["cod"]) != cod:
                raise Recusada(f"O {ant['numero']} é de outro ativo ({ant['ultima']['cod']})")
            numero, revisao = ant["numero"], max(r["revisao"] for r in ant["revisoes"]) + 1
        else:
            numero, revisao = proximo_numero(linhas, tipo, agora.astimezone(_BRT).year), 0
        rid = uuid.uuid4().hex[:12]
        foto_a, foto_os, medido = _foto(ativo)
        dados = {"quem": {"nome": quem["nome"], "email": quem["email"]}, "ativo": foto_a, "os": foto_os,
                 "medido": medido, "campos": c}
        nova = {"id": rid, "registrado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data_id": int(agora.astimezone(_BRT).strftime("%Y%m%d")), "numero": numero, "tipo": tipo,
                "revisao": revisao, "codigo_ativo": cod, "equipamento_id": equipamento_id(cod),
                "usina_id": AC._int(ativo.get("usina_id")),
                "usina_ligada_por": _txt(ativo.get("usina_ligada_por") or ativo.get("ligada_por")) or None,
                "acompanhamento_id": _txt(acompanhamento_id) or None, "pessoa_hmac": quem["hmac"],
                "padrao_biblioteca": p["padrao"]["chave"] if p["padrao"] else None,
                "tipo_falha": c.get("tipo_falha") or None, "falhas_30d_qtd": n_falha, "ocorrencia_nivel": occ,
                "severidade_nivel": sev, "deteccao_nivel": det,
                "rpn_pts": occ * sev * det if tipo == "fmea" else None,
                "dados_cifrados": cofre.cifrar(json.dumps(dados, ensure_ascii=False), _ctx(rid))}
        base, sessao = AC._banco()
        livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), [[l.get(k) for k in CAB] for l in linhas + [nova]])},
                        base=base, token=current_app.config["GRIDCO_SQL_TOKEN"], sessao=sessao)
        limpar()
    return nova
