"""As telas do cadastro, penduradas nas torres Base (usinas, equipes, listas, importação, qualidade) e Pessoas
(colaboradores). As torres chamam registrar_base(bp) / registrar_pessoas(bp); o resto mora aqui.

Regras de tela que valem para todas:
- só entra quem é admin (nesta fase, quem entra pela senha; o login Microsoft troca isso depois);
- dado sensível aparece mascarado; "Mostrar dados sensíveis" revela e fica na auditoria;
- campo mascarado NÃO vai no formulário: salvar com a máscara na tela não apaga o CPF;
- sem NEXUS_CHAVE_CADASTRO, a tela diz o que falta em vez de quebrar.
"""
import os
import secrets
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

from flask import abort, current_app, redirect, render_template, request, session

from . import tipos
from .armazem import ArmazemLocal
from .calculos import CARGO_TECNICO, ERRO
from .cifra import CifraErro, Cofre
from .esquema import CLIENTES, ENTIDADES, EQUIPES, LISTAS, PESSOAS, USINAS
from .importar import ler_xlsx, montar
from .servico import QUEM_IMPORTACAO, Servico, chave_texto
from .tipos import Legado

# Fora do OneDrive e fora do AppData (o Claude desktop virtualiza o AppData: 03/09/2026, banco do gêmeo).
ARMAZEM_PADRAO = (Path(r"C:\GridcoAuto\nexus\cadastro_ensaio.json") if os.name == "nt"
                  else Path(__file__).resolve().parents[2] / "dados" / "cadastro_ensaio.json")
PREVIA_TTL_S = 30 * 60


class SemCadastro(RuntimeError):
    pass


def servico() -> Servico:
    app = current_app
    s = app.extensions.get("nexus_cadastro")
    if s is not None:
        return s
    chave = app.config.get("NEXUS_CHAVE_CADASTRO")
    if not chave:
        raise SemCadastro("Falta a variável NEXUS_CHAVE_CADASTRO no .env do Nexus.")
    try:
        cofre = Cofre(chave)
    except CifraErro as e:
        raise SemCadastro(str(e)) from None
    s = Servico(ArmazemLocal(Path(app.config.get("NEXUS_ARMAZEM_LOCAL") or ARMAZEM_PADRAO)), cofre)
    app.extensions["nexus_cadastro"] = s
    return s


def _quem() -> str:
    return session.get("usuario") or "admin"


def hora_br(iso: str) -> str:
    try:
        d = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) - timedelta(hours=3)
    except (TypeError, ValueError):
        return iso or ""
    return d.strftime("%d/%m/%Y %H:%M")


def exibir_valor(srv: Servico, c, v) -> str:
    if v is None or v is ERRO:
        return ""
    if isinstance(v, Legado):
        return v.texto
    if c.tipo == "ref":
        m = tipos.marcador(v)
        if m:
            return "Não se aplica" if m == "N/A" else m
        return srv.titulo_de(c.lista, v)
    return tipos.exibir(c.tipo, v)


def _opcoes_ref(srv: Servico, c):
    if c.lista != "pessoas":
        return [("", [(r.id, r.titulo) for r in sorted(srv.registros(c.lista), key=lambda r: chave_texto(r.titulo))])]
    grupos = defaultdict(list)
    for r in srv.registros("pessoas"):
        extra = r.valores.get("cargo") or ""
        grupos[r.valores.get("vinculo") or "Sem vínculo"].append(
            (r.id, r.titulo + (f" · {extra}" if extra else "")))
    ordem = ["Supervisor", "Gestor de contrato", "Colaborador de campo"] if c.id in (
        "responsavel_om", "gestor_contrato", "supervisor") else ["Colaborador de campo", "Supervisor",
                                                                 "Gestor de contrato"]
    chaves = ordem + sorted(k for k in grupos if k not in ordem)
    return [(k, sorted(grupos[k], key=lambda x: chave_texto(x[1]))) for k in chaves if grupos.get(k)]


def _campo(srv: Servico, ent, reg, c, revelar, form=None, erros=None, novo=False, sugestoes=None) -> dict:
    atual = reg.valores.get(c.id) if reg else None
    efetivo = reg.valor(c.id) if reg else None
    origem = reg.origem(c.id) if reg else ("calculado" if c.modo == "calculado" else
                                            "automatico" if c.modo == "automatico" else "digitado")
    mascarado = c.oculto and not revelar and not novo
    exibido = exibir_valor(srv, c, efetivo)
    d = {"id": c.id, "rotulo": c.rotulo, "tipo": c.tipo, "modo": c.modo, "ajuda": c.ajuda, "sensivel": c.sensivel,
         "obrigatorio": c.obrigatorio, "erro": (erros or {}).get(c.id), "origem": origem,
         "legado": atual.texto if isinstance(atual, Legado) else None, "mascarado": mascarado,
         "exibido": tipos.mascarar(c.tipo, efetivo) if mascarado and c.tipo != "ref" else exibido,
         "erro_calculo": efetivo is ERRO}
    if form is not None and c.id in form:
        d["valor"] = form[c.id]
    else:
        d["valor"] = Servico._form_valor(c, atual)
    d["placeholder"] = ("Automático: " + exibido) if c.modo == "automatico" and origem == "automatico" and exibido \
        else ("Vazio = automático" if c.modo == "automatico" else "")
    if c.tipo == "lista":
        valores = srv.listas().get(c.lista, [])
        d["opcoes"] = [("", "—")] + [(v, v) for v in valores]
        if d["valor"] and d["valor"] not in valores:
            d["opcoes"].insert(1, (d["valor"], f"{d['valor']} (fora da lista)"))
    elif c.tipo == "simnao":
        d["opcoes"] = [("", "—"), ("Sim", "Sim"), ("Não", "Não")]
    elif c.tipo == "ref":
        primeiro = [("", ("Automático: " + exibido) if c.modo == "automatico" and origem == "automatico" and exibido
                     else ("Automático (pela equipe)" if c.modo == "automatico" else "—"))]
        if c.modo == "automatico":
            primeiro += [("N/A", "Não se aplica"), ("N/I", "Não informado")]
        if isinstance(atual, Legado):
            primeiro.append((atual.texto, f"Do Excel, sem cadastro: {atual.texto}"))
        d["grupos"] = [("", primeiro)] + _opcoes_ref(srv, c)
    elif c.tipo == "sugestao":
        d["sugestoes"] = (sugestoes or {}).get(c.id, [])
    # A caixa de seleção TEM de ter o valor atual entre as opções. Sem ele, o navegador marca a primeira, e salvar
    # a ficha sem mexer trocava o valor calado (29/09/2026: o "N/I" digitado no técnico virava "Automático").
    if c.tipo in ("lista", "simnao") and d["valor"] not in [v for v, _ in d["opcoes"]]:
        d["opcoes"].insert(1, (d["valor"], f"{d['valor']} (valor atual, fora das opções)"))
    if c.tipo == "ref" and d["valor"] not in [v for _, itens in d["grupos"] for v, _ in itens]:
        d["grupos"][0][1].append((d["valor"], f"{d['valor']} (valor atual)"))
    return d


def _secoes(srv: Servico, ent, reg, revelar, form=None, erros=None, novo=False):
    sug = {}
    for c in ent.campos:
        if c.tipo == "sugestao":
            sug[c.id] = sorted({str(r.valores.get(c.id)) for r in srv.registros(ent.id)
                                if isinstance(r.valores.get(c.id), str) and r.valores.get(c.id)}, key=chave_texto)
    out = []
    for s in ent.secoes:
        campos = [_campo(srv, ent, reg, c, revelar, form, erros, novo, sug) for c in ent.campos if c.secao == s.id]
        if campos:
            out.append({"id": s.id, "nome": s.nome, "campos": campos})
    return out


def _pendencias_de(srv: Servico, entidade, id_):
    return [p for p in srv.pendencias() if p["entidade"] == entidade and p["id"] == id_]


def _historico(srv: Servico, ent, id_):
    h = srv.historico(ent.id, id_)
    for x in h:
        x["quando_br"] = hora_br(x["quando"])
        x["rotulos"] = [ent.campo(c).rotulo if ent.tem(c) else c for c in x["campos"]]
    return h


def _tela(titulo):
    """Admin obrigatório e cadastro ligado; sem a chave, a tela avisa o que falta."""
    def deco(fn):
        @wraps(fn)
        def envolta(*a, **k):
            if not session.get("admin"):
                # 403 que diz o porquê e o caminho (Levi, 08/10/2026, pelo Fracttal e fora do NEXUS_ADMINS: recebia o
                # "Forbidden" cru do Flask e achou que o Nexus tinha quebrado)
                return render_template("cadastro/sem_permissao.html", titulo=titulo,
                                       email=(session.get("usuario") or {}).get("email", "")), 403
            try:
                srv = servico()
            except SemCadastro as e:
                return render_template("cadastro/sem_chave.html", titulo=titulo, motivo=str(e))
            return fn(srv, *a, **k)
        return envolta
    return deco


# ── listas de registros ────────────────────────────────────────────────────

# Colunas que ficam à esquerda: o nome e a equipe (Levi, 29/09: "todos os valores centralizados menos usina e
# equipes"). O resto, e todo cabeçalho, centralizado.
_A_ESQUERDA = {"nome", "nome_padrao", "equipe"}

# O nome de cada pendência, para a Qualidade do cadastro e para o aviso que abre na linha da lista.
NOMES_PENDENCIA = {
    "selo": "Linha alterada fora do Nexus", "legado": "Valor do Excel fora do tipo",
    "fora_da_lista": "Valor fora da lista", "sem_email": "Pessoa ativa sem e-mail",
    "cpf_invalido": "CPF com dígito errado", "email_repetido": "E-mail repetido",
    "calculo_erro": "Cálculo sem resultado", "equipe_cargo_duplicado": "Equipe com duas pessoas no mesmo cargo",
    "equipe_responsaveis": "Equipe com responsáveis diferentes", "equipe_sem_usina": "Equipe de pessoas sem usina",
    "usina_sem_equipe": "Usina sem equipe", "nome_repetido": "Nome de usina repetido",
    "nome_sem_cadastro": "Nome que não casou com ninguém do cadastro",
    "lista_parecida": "Valores parecidos na mesma lista"}
GRAVIDADES = {"critico": "crítico", "alerta": "alerta", "info": "info"}
_ORDEM_GRAVIDADE = {"critico": 0, "alerta": 1, "info": 2}


def _colunas_da_lista(ent, extras):
    """Toda coluna que PODE aparecer na lista: os campos que não são mascarados (o sensível nunca vai para a lista,
    nem escondido) e os resumos da entidade. A padrão é a de sempre (na_lista); o resto vem escondido, para a
    pessoa acrescentar pelo botão Colunas. A escolha vale até atualizar a página (não fica guardada)."""
    secao = {s.id: s.nome for s in ent.secoes}
    cols = [{"id": c.id, "rotulo": c.rotulo, "padrao": c.na_lista, "secao": secao.get(c.secao, ""), "campo": c,
             "esquerda": c.id in _A_ESQUERDA} for c in ent.campos if not c.oculto]
    for i, rot in enumerate(extras(None) if extras else []):
        cols.append({"id": f"resumo{i}", "rotulo": rot, "padrao": True, "secao": "Resumo", "campo": None,
                     "esquerda": False})
    return cols


def _visoes_nav(visoes, atual):
    return [{"id": v, "rotulo": r, "atual": v == atual, "url": request.path + (f"?visao={v}" if v else "")}
            for v, r in (visoes or [])]


def _lista(srv: Servico, ent, titulo, filtros_def, busca_campos, url_nova, texto_novo, extras=None, visoes=None):
    q = request.args.get("q", "").strip()
    filtros = {k: request.args.get(k, "") for k, _, _ in filtros_def}
    # Os avisos vão inteiros para a linha: o clique na linha abre o que é (Levi, 30/09: "ao clicar na linha que
    # tivesse avisos expandiria o aviso"), o mais grave primeiro.
    pend = defaultdict(list)
    for p in sorted(srv.pendencias(), key=lambda p: _ORDEM_GRAVIDADE.get(p["gravidade"], 3)):
        pend[(p["entidade"], p["id"])].append(p)
    colunas = _colunas_da_lista(ent, extras)
    pedidas = [x for x in request.args.get("cols", "").split(",") if x]
    validas = {c["id"] for c in colunas}
    visiveis = {x for x in pedidas if x in validas} or {c["id"] for c in colunas if c["padrao"]}
    for c in colunas:
        c["visivel"] = c["id"] in visiveis
    titulo_col = next((c["id"] for c in colunas if c["padrao"]), None)
    linhas = []
    total = srv.registros(ent.id)
    for r in total:
        if q:
            partes = [r.id] + [exibir_valor(srv, ent.campo(b), r.valor(b)) for b in busca_campos]
            if chave_texto(q) not in chave_texto(" ".join(partes)):
                continue
        if any(filtros[k] and str(r.valores.get(k) or "") != filtros[k] for k, _, _ in filtros_def):
            continue
        resumo = extras(r) if extras else []
        celulas = []
        for c in colunas:
            if c["campo"] is not None:
                f = c["campo"]
                celulas.append({"col": c["id"], "texto": exibir_valor(srv, f, r.valor(f.id)),
                                "legado": isinstance(r.valores.get(f.id), Legado)})
            else:
                celulas.append({"col": c["id"], "texto": resumo[int(c["id"][6:])], "legado": False})
            celulas[-1].update(visivel=c["visivel"], esquerda=c["esquerda"], link=c["id"] == titulo_col,
                               chip=c["id"] == "status")
        avisos = pend.get((ent.id, r.id), [])
        linhas.append({"id": r.id, "url": ent.rota_ficha + r.id, "selo_ok": r.selo_ok, "celulas": celulas,
                       "avisos": len(avisos), "pendencias": avisos,
                       "gravidade": avisos[0]["gravidade"] if avisos else ""})
    opcoes = []
    for k, rotulo, fonte in filtros_def:
        if fonte in ENTIDADES:
            vals = [(e.id, e.titulo) for e in sorted(srv.registros(fonte), key=lambda e: chave_texto(e.titulo))]
        else:
            vals = [(v, v) for v in srv.listas().get(fonte, [])]
        opcoes.append({"id": k, "rotulo": rotulo, "valores": vals, "atual": filtros[k]})
    grupos = defaultdict(list)
    for c in colunas:
        grupos[c["secao"]].append(c)
    return render_template("cadastro/lista.html", titulo=titulo, ent=ent, colunas=colunas, linhas=linhas,
                           total=len(total), q=q, filtros=opcoes, url_nova=url_nova, texto_novo=texto_novo,
                           vazio=srv.vazio(), importado=request.args.get("importado"),
                           grupos_colunas=list(grupos.items()), visoes=_visoes_nav(visoes, ""),
                           cols_atuais=",".join(c["id"] for c in colunas if c["visivel"]),
                           cols_padrao=",".join(c["id"] for c in colunas if c["padrao"]),
                           n_colunas=2 + sum(1 for c in colunas if c["visivel"]),
                           nomes=NOMES_PENDENCIA, gravidades=GRAVIDADES)


# ── visões somadas: por cliente (Registro mestre) e por supervisor (Equipes) ──

def _kwp(usinas) -> float:
    """Soma da potência contratual em kWp. O BD guarda em MWp; valor que não é número (legado) não entra."""
    return sum(u.valores["potencia_contratual"] * 1000 for u in usinas
               if isinstance(u.valores.get("potencia_contratual"), (int, float)))


def _chave_ref(v) -> str:
    if isinstance(v, Legado):
        return v.texto
    return "" if v is None or tipos.marcador(v) else str(v)


MASCARA_REAIS = "R$ •••••"


def _em_operacao(us) -> int:
    return sum(1 for u in us if u.valores.get("status") == "OPERAÇÃO")


def _falta_txt(faltam, n, o_que) -> str:
    if not faltam:
        return ""
    if faltam == n:
        return f"a usina não tem {o_que} no BD" if n == 1 else f"nenhuma das {n} usinas tem {o_que} no BD"
    return f"sem {o_que} em {faltam} de {n} usinas"


def _dinheiro(us, campo, revelar) -> dict:
    """Soma em reais de um campo de receita e quantas usinas ficaram sem ele. No ensaio de 30/09, 116 das 258
    usinas não têm receita no BD (E1, Faro, Elis, Apolo e Qair, nenhuma): a soma sem dizer isso passaria pelo
    valor do cliente inteiro. Mascarada, nem o número bruto sai (a ordenação por valor só existe revelada)."""
    if not revelar:
        return {"texto": MASCARA_REAIS, "falta": "", "faltam": 0, "bruto": None}
    nums = [v for v in (u.valor(campo) for u in us) if isinstance(v, (int, float)) and not isinstance(v, bool)]
    faltam = len(us) - len(nums)
    return {"texto": ("R$ " + tipos.exibir("numero", round(sum(nums)))) if nums else "—",
            "falta": _falta_txt(faltam, len(us), "valor"), "faltam": faltam, "bruto": round(sum(nums), 2)}


def _nota_receita(valor, mensal, n) -> str:
    """As duas receitas faltando nas mesmas usinas: a nota vai uma vez, embaixo das duas colunas (5 dos 16 clientes
    do ensaio não têm receita em usina nenhuma, e a mesma frase nas duas colunas só repetia). Sem a mensal não há
    contratual, então contagem igual quer dizer as mesmas usinas."""
    if not valor["faltam"] or valor["faltam"] != mensal["faltam"]:
        return ""
    valor["falta"] = mensal["falta"] = ""
    t = _falta_txt(valor["faltam"], n, "receita")
    return t[0].upper() + t[1:] + "."


def _visao(srv: Servico, titulo, ent_tela, visoes, visao, rotulo_grupo, rotulo_plural, entidade_grupo, campo_grupo,
           sem_grupo, dados_extra, url_usinas=None):
    """Um cartão por cliente (ou supervisor): o kWp em destaque, a parte da carteira, as usinas e o valor
    contratado (Levi, 30/09: "cards suspensos, algo bem mais dinâmico e visual. Soma o valor contratado também").
    "Só em operação" restringe às usinas com status OPERAÇÃO (29/09: "dando para priorizar só o que está em
    operação"). Valor contratado = a receita contratual (mensal × prazo); "por mês" = a receita mensal. As duas
    são sensíveis: vêm mascaradas como na ficha, e mostrar fica na auditoria."""
    so_operacao = request.args.get("operacao") == "1"
    revelar = request.args.get("sensiveis") == "1"
    if revelar:
        srv.auditar(_quem(), "viu dados sensíveis", "usinas", f"soma por {rotulo_grupo.lower()}",
                    ["Receita contratual", "Receita mensal"])
    usinas = [u for u in srv.registros("usinas") if not so_operacao or u.valores.get("status") == "OPERAÇÃO"]
    total_kwp = _kwp(usinas)
    grupos = defaultdict(list)
    for u in usinas:
        grupos[_chave_ref(u.valores.get(campo_grupo))].append(u)
    cartoes = []
    for chave, us in grupos.items():
        reg = srv.registro(entidade_grupo, chave) if chave else None
        kwp = _kwp(us)
        parte = kwp / total_kwp * 100 if total_kwp else 0.0
        dados = [("Usinas", str(len(us)))] + [(r, f(us)) for r, f in dados_extra]
        if not so_operacao:
            dados.append(("Em operação", str(_em_operacao(us))))
        valor, mensal = _dinheiro(us, "receita_contratual", revelar), _dinheiro(us, "receita_mensal", revelar)
        cartoes.append({"nome": reg.titulo if reg else (chave or sem_grupo),
                        "url": (ENTIDADES[entidade_grupo].rota_ficha + chave) if reg else None,
                        "url_usinas": url_usinas(chave, so_operacao) if url_usinas and reg else None,
                        "kwp": round(kwp, 3), "kwp_txt": tipos.exibir("numero", round(kwp, 1)),
                        "parte": round(parte, 1), "parte_txt": tipos.exibir("numero", round(parte, 1)) + "%",
                        "usinas": len(us), "dados": dados, "nota": _nota_receita(valor, mensal, len(us)),
                        "valor": valor, "mensal": mensal})
    cartoes.sort(key=lambda x: (-x["kwp"], chave_texto(x["nome"])))
    valor, mensal = _dinheiro(usinas, "receita_contratual", revelar), _dinheiro(usinas, "receita_mensal", revelar)
    faixa = ([{"r": rotulo_plural, "v": str(len(cartoes))},
              {"r": "Usinas", "v": str(len(usinas)), "d": "" if so_operacao else f"{_em_operacao(usinas)} em operação"}]
             + [{"r": r, "v": f(usinas)} for r, f in dados_extra]
             + [{"r": "kWp", "v": tipos.exibir("numero", round(total_kwp, 1))},
                {"r": "Valor contratado", "v": valor["texto"], "d": valor["falta"]},
                {"r": "Por mês", "v": mensal["texto"], "d": mensal["falta"]}])
    return render_template("cadastro/visao.html", titulo=titulo, ent=ent_tela, visoes=_visoes_nav(visoes, visao),
                           visao=visao, so_operacao=so_operacao, revelar=revelar, rotulo_grupo=rotulo_grupo,
                           cartoes=cartoes, faixa=faixa, mascara=MASCARA_REAIS, vazio=srv.vazio())


def _url_usinas_do_cliente(chave, so_operacao) -> str:
    return "/t/base/registro-mestre?" + urlencode({"cliente": chave, **({"status": "OPERAÇÃO"} if so_operacao else {})})


def _clusters(us) -> str:
    """Quantos clusters (Equipe Cluster, como a Carteira de Usinas do Excel conta) as usinas somam."""
    return str(len({u.valores.get("equipe") for u in us if isinstance(u.valores.get("equipe"), str)
                    and u.valores.get("equipe")}))


# ── ficha ──────────────────────────────────────────────────────────────────

def _ficha(srv: Servico, ent, id_, titulo_tela, extra=None, sub=None):
    reg = srv.registro(ent.id, id_)
    if reg is None:
        abort(404)
    url = ent.rota_ficha + id_
    if request.method == "POST":
        revelado = request.form.get("_revelado") == "1"
        form = {k: v for k, v in request.form.items() if not k.startswith("_")}
        if not revelado:
            form = {k: v for k, v in form.items() if not (ent.tem(k) and ent.campo(k).oculto)}
        versao = request.form.get("_versao") or "0"
        res = srv.salvar(ent.id, id_, form, int(versao), quem=_quem())
        if res.ok:
            return redirect(url + ("?sensiveis=1&salvo=1" if revelado else "?salvo=1"))
        if res.conflito is not None:
            atual = res.conflito
            return render_template(
                "cadastro/ficha.html", ent=ent, reg=atual, titulo_tela=titulo_tela, revelar=revelado,
                secoes=_secoes(srv, ent, atual, revelado), pendencias=_pendencias_de(srv, ent.id, id_),
                historico=_historico(srv, ent, id_), conflito=srv.tentativa(ent.id, id_, int(versao), form),
                conflito_quando=hora_br(atual.alterado_em), conflito_quem=atual.alterado_por, url=url,
                extra=extra(atual) if extra else None, hora_br=hora_br), 409
        return render_template(
            "cadastro/ficha.html", ent=ent, reg=reg, titulo_tela=titulo_tela, revelar=revelado,
            secoes=_secoes(srv, ent, reg, revelado, form, res.erros), pendencias=_pendencias_de(srv, ent.id, id_),
            historico=_historico(srv, ent, id_), erro_geral=res.erros.get("_"), url=url,
            extra=extra(reg) if extra else None, hora_br=hora_br), 422
    revelar = request.args.get("sensiveis") == "1"
    if revelar:
        srv.auditar(_quem(), "viu dados sensíveis", ent.id, id_)
    return render_template(
        "cadastro/ficha.html", ent=ent, reg=reg, titulo_tela=titulo_tela, revelar=revelar,
        secoes=_secoes(srv, ent, reg, revelar), pendencias=_pendencias_de(srv, ent.id, id_),
        historico=_historico(srv, ent, id_), salvo=request.args.get("salvo"), url=url,
        extra=extra(reg) if extra else None, sub=sub(reg) if sub else "", hora_br=hora_br)


def _novo(srv: Servico, ent, titulo_tela):
    url = ent.rota_ficha + ("novo" if ent.id in ("pessoas", "clientes") else "nova")
    if request.method == "POST":
        form = {k: v for k, v in request.form.items() if not k.startswith("_")}
        res = srv.criar(ent.id, form, quem=_quem())
        if res.ok:
            return redirect(ent.rota_ficha + res.registro.id)
        return render_template("cadastro/ficha.html", ent=ent, reg=None, titulo_tela=titulo_tela, revelar=True,
                               secoes=_secoes(srv, ent, None, True, form, res.erros, novo=True), pendencias=[],
                               historico=[], novo=True, url=url, hora_br=hora_br), 422
    return render_template("cadastro/ficha.html", ent=ent, reg=None, titulo_tela=titulo_tela, revelar=True,
                           secoes=_secoes(srv, ent, None, True, novo=True), pendencias=[], historico=[], novo=True,
                           url=url, hora_br=hora_br)


# ── equipes e clientes: o que cada um junta, para os painéis da ficha ──────

def _item_usina(srv: Servico, u) -> dict:
    return {"url": USINAS.rota_ficha + u.id, "texto": u.titulo,
            "detalhe": f"ID {u.id}" + (f" · {u.valores.get('id_bd')}" if u.valores.get("id_bd") else ""),
            "chip": u.valores.get("status") or "", "chip_ok": u.valores.get("status") == "OPERAÇÃO"}


def _tecnicos(srv: Servico, usinas, pessoas) -> list[str]:
    """Os técnicos O&M da equipe: o que cada usina aponta (o automático ou o digitado por cima da fórmula) e o
    técnico ativo da equipe que nenhuma usina cita. No ensaio de 30/09, 55 das 145 equipes não tinham técnico ativo
    no cadastro de pessoas, mas as usinas delas tinham o técnico digitado: contar só a pessoa da equipe as deixaria
    vazias. "N/I" e "N/A" não são nome."""
    nomes = {srv.titulo_de("pessoas", t) for t in (u.valor("tecnico_om") for u in usinas)
             if t is not None and t is not ERRO and not tipos.marcador(t)}
    nomes |= {p.titulo for p in pessoas
              if p.valores.get("cargo") == CARGO_TECNICO and chave_texto(p.valores.get("status")) != "desligado"}
    return sorted((n for n in nomes if n), key=chave_texto)


def _resumo_equipe(srv: Servico, eq):
    usinas = [u for u in srv.registros("usinas") if u.valores.get("equipe") == eq.id]
    pessoas = [p for p in srv.registros("pessoas") if p.valores.get("equipe") == eq.id]
    resp = sorted({srv.titulo_de("pessoas", u.valores.get("responsavel_om")) for u in usinas
                   if u.valores.get("responsavel_om") and not tipos.marcador(u.valores.get("responsavel_om"))})
    tec = _tecnicos(srv, usinas, pessoas)
    base = next((u.valor("base_equipe") for u in usinas if u.valor("base_equipe")), "")
    return {"usinas": usinas, "pessoas": pessoas, "responsaveis": resp, "tecnicos": tec, "base": base,
            "meta": [("Usinas", str(len(usinas))), ("Responsáveis", ", ".join(resp) or "—"),
                     ("Técnicos", ", ".join(tec) or "—"), ("Base", base or "—")],
            "listas": [
                {"titulo": "Usinas da equipe", "itens": [_item_usina(srv, u) for u in usinas]},
                {"titulo": "Pessoas da equipe", "itens": [
                    {"url": PESSOAS.rota_ficha + p.id, "texto": p.titulo,
                     "detalhe": p.valores.get("cargo") or p.valores.get("vinculo") or "",
                     "chip": "desligado" if p.valores.get("status") == "Desligado" else "", "chip_ok": False}
                    for p in pessoas]},
            ]}


def _resumo_cliente(srv: Servico, cl):
    usinas = [u for u in srv.registros("usinas") if u.valores.get("cliente") == cl.id]
    pot = sum(u.valores.get("potencia_contratual") for u in usinas
              if isinstance(u.valores.get("potencia_contratual"), (int, float)))
    em_op = sum(1 for u in usinas if u.valores.get("status") == "OPERAÇÃO")
    return {"usinas": usinas, "em_operacao": em_op, "potencia": pot,
            "meta": [("Usinas", str(len(usinas))), ("Em operação", str(em_op)),
                     ("Potência contratual", tipos.exibir("numero", round(pot, 3)) + " MWp")],
            "listas": [{"titulo": "Usinas do cliente", "itens": [_item_usina(srv, u) for u in usinas]}]}


def _extras_cliente(srv: Servico):
    def f(r):
        if r is None:
            return ["Usinas", "Em operação", "Potência (MWp)"]
        x = _resumo_cliente(srv, r)
        return [str(len(x["usinas"])), str(x["em_operacao"]), tipos.exibir("numero", round(x["potencia"], 3))]
    return f


def _sub_usina(srv: Servico):
    def f(r):
        partes = []
        if r.valores.get("cliente"):
            partes.append("Cliente: " + srv.titulo_de("clientes", r.valores.get("cliente")))
        if r.valores.get("id_bd"):
            partes.append("ID do BD: " + str(r.valores.get("id_bd")))
        return " · ".join(partes)
    return f


def _extras_equipe(srv: Servico):
    def f(r):
        if r is None:
            return ["Usinas", "Pessoas ativas", "Responsáveis", "Técnicos"]
        x = _resumo_equipe(srv, r)
        ativas = [p for p in x["pessoas"] if chave_texto(p.valores.get("status")) != "desligado"]
        return [str(len(x["usinas"])), str(len(ativas)), ", ".join(x["responsaveis"]), ", ".join(x["tecnicos"])]
    return f


# ── registro das rotas nas torres ──────────────────────────────────────────

def registrar_base(bp):
    @_tela("Registro mestre")
    def usinas(srv):
        visoes = [("", "Lista"), ("cliente", "Por cliente")]
        if request.args.get("visao") == "cliente":
            return _visao(srv, "Registro mestre", USINAS, visoes, "cliente", "Cliente", "Clientes", "clientes",
                          "cliente", "Sem cliente", [], url_usinas=_url_usinas_do_cliente)
        return _lista(srv, USINAS, "Registro mestre", [("status", "Status", "status_usina"),
                                                       ("cliente", "Cliente", "clientes"), ("uf", "UF", "uf"),
                                                       ("equipe", "Equipe", "equipes")],
                      ["nome", "codigo", "id_bd", "cliente", "cidade", "equipe", "responsavel_om"],
                      "/t/base/usina/nova", "Nova usina", visoes=visoes)

    @_tela("Nova usina")
    def usina_nova(srv):
        return _novo(srv, USINAS, "Registro mestre")

    @_tela("Usina")
    def usina(srv, id_):
        return _ficha(srv, USINAS, id_, "Registro mestre", sub=_sub_usina(srv))

    @_tela("Clientes")
    def clientes(srv):
        return _lista(srv, CLIENTES, "Clientes", [], ["nome"], "/t/base/cliente/novo", "Novo cliente",
                      extras=_extras_cliente(srv))

    @_tela("Novo cliente")
    def cliente_novo(srv):
        return _novo(srv, CLIENTES, "Clientes")

    @_tela("Cliente")
    def cliente(srv, id_):
        return _ficha(srv, CLIENTES, id_, "Clientes", extra=lambda r: _resumo_cliente(srv, r))

    @_tela("Equipes")
    def equipes(srv):
        visoes = [("", "Lista"), ("supervisor", "Por supervisor")]
        if request.args.get("visao") == "supervisor":
            return _visao(srv, "Equipes", EQUIPES, visoes, "supervisor", "Supervisor", "Supervisores", "pessoas",
                          "responsavel_om", "Sem responsável", [("Clusters", _clusters)])
        return _lista(srv, EQUIPES, "Equipes", [], ["nome"], "/t/base/equipe/nova", "Nova equipe",
                      extras=_extras_equipe(srv), visoes=visoes)

    @_tela("Nova equipe")
    def equipe_nova(srv):
        return _novo(srv, EQUIPES, "Equipes")

    @_tela("Equipe")
    def equipe(srv, id_):
        return _ficha(srv, EQUIPES, id_, "Equipes", extra=lambda r: _resumo_equipe(srv, r))

    @_tela("Listas")
    def listas(srv):
        erro = None
        if request.method == "POST":
            res = srv.adicionar_valor(request.form.get("lista", ""), request.form.get("valor", ""), quem=_quem())
            if res.ok:
                return redirect("/t/base/listas?incluido=1")
            erro = next(iter(res.erros.values()), "Não foi possível incluir.")
        uso = defaultdict(Counter)
        for eid, ent in ENTIDADES.items():
            for c in ent.campos:
                if c.tipo == "lista":
                    for r in srv.registros(eid):
                        v = r.valores.get(c.id)
                        if isinstance(v, str) and v:
                            uso[c.lista][v] += 1
        grupos = [{"id": k, "nome": nome, "valores": [(v, uso[k].get(v, 0)) for v in srv.listas().get(k, [])]}
                  for k, nome in LISTAS.items()]
        return render_template("cadastro/listas.html", grupos=grupos, erro=erro,
                               incluido=request.args.get("incluido")), (422 if erro else 200)

    @_tela("Importar do Excel")
    def importar(srv):
        if request.method == "GET":
            imps = srv.importacoes()
            for x in imps:
                x["quando_br"] = hora_br(x.get("quando", ""))
            return render_template("cadastro/importar.html", importacoes=imps, erro=None)
        f = request.files.get("arquivo")
        nome = (f.filename if f else "") or ""
        if not f or not nome.lower().endswith((".xlsx", ".xlsm")):
            return render_template("cadastro/importar.html", importacoes=[],
                                   erro="Envie o BD_Operacoes.xlsx (arquivo .xlsx)."), 400
        dados = f.read()
        try:
            abas = ler_xlsx(dados)
        except Exception as e:                        # arquivo corrompido ou não é Excel
            return render_template("cadastro/importar.html", importacoes=[],
                                   erro=f"Não consegui ler o arquivo: {str(e)[:160]}"), 400
        if "Operações" not in abas:
            return render_template("cadastro/importar.html", importacoes=[],
                                   erro="O arquivo não tem a aba Operações: é mesmo o BD_Operações?"), 400
        proposta = montar(abas, srv, arquivo=nome, dados=dados)
        previas = current_app.extensions.setdefault("nexus_cadastro_previas", {})
        agora = time.time()
        for k in [k for k, (_, t) in previas.items() if agora - t > PREVIA_TTL_S]:
            previas.pop(k, None)
        token = secrets.token_urlsafe(16)
        previas[token] = (proposta, agora)
        return render_template("cadastro/previa.html", p=proposta, token=token, ENTIDADES=ENTIDADES)

    @_tela("Importar do Excel")
    def importar_aplicar(srv):
        previas = current_app.extensions.setdefault("nexus_cadastro_previas", {})
        item = previas.pop(request.form.get("token", ""), None)
        if item is None:
            return render_template("cadastro/importar.html", importacoes=[],
                                   erro="A prévia expirou (30 min). Envie o arquivo de novo."), 410
        proposta = item[0]
        srv.aplicar_carga(proposta.carga, quem=QUEM_IMPORTACAO)
        srv.auditar(_quem(), "importou", "cadastro", proposta.origem.get("arquivo", ""),
                    [f"{k}: {v['novos']} novos, {v['alterados']} alterados" for k, v in proposta.resumo.items()])
        return redirect("/t/base/registro-mestre?importado=1")

    @_tela("Qualidade do cadastro")
    def qualidade(srv):
        pend = srv.pendencias()
        pend.sort(key=lambda p: (_ORDEM_GRAVIDADE.get(p["gravidade"], 3), p["tipo"], chave_texto(p["titulo"])))
        grupos = defaultdict(list)
        for p in pend:
            ent = ENTIDADES.get(p["entidade"])
            p["url"] = (ent.rota_ficha + p["id"]) if ent else "/t/base/listas"
            grupos[p["tipo"]].append(p)
        aud = srv.auditoria(60)
        for a in aud:
            a["quando_br"] = hora_br(a.get("quando", ""))
        return render_template("cadastro/qualidade.html", grupos=grupos, total=len(pend), auditoria=aud,
                               contagem=Counter(p["gravidade"] for p in pend), nomes=NOMES_PENDENCIA,
                               gravidades=GRAVIDADES)

    bp.add_url_rule("/registro-mestre", "cad_usinas", usinas)
    bp.add_url_rule("/usina/nova", "cad_usina_nova", usina_nova, methods=["GET", "POST"])
    bp.add_url_rule("/usina/<id_>", "cad_usina", usina, methods=["GET", "POST"])
    bp.add_url_rule("/clientes", "cad_clientes", clientes)
    bp.add_url_rule("/cliente/novo", "cad_cliente_novo", cliente_novo, methods=["GET", "POST"])
    bp.add_url_rule("/cliente/<id_>", "cad_cliente", cliente, methods=["GET", "POST"])
    bp.add_url_rule("/equipes", "cad_equipes", equipes)
    bp.add_url_rule("/equipe/nova", "cad_equipe_nova", equipe_nova, methods=["GET", "POST"])
    bp.add_url_rule("/equipe/<id_>", "cad_equipe", equipe, methods=["GET", "POST"])
    bp.add_url_rule("/listas", "cad_listas", listas, methods=["GET", "POST"])
    bp.add_url_rule("/importar", "cad_importar", importar, methods=["GET", "POST"])
    bp.add_url_rule("/importar/aplicar", "cad_importar_aplicar", importar_aplicar, methods=["POST"])
    bp.add_url_rule("/qualidade", "cad_qualidade", qualidade)


def registrar_pessoas(bp):
    @_tela("Colaboradores Operação")
    def pessoas(srv):
        return _lista(srv, PESSOAS, "Colaboradores Operação", [("vinculo", "Vínculo", "vinculo"), ("cargo", "Cargo", "cargos"),
                                                      ("status", "Status", "status_contratacao"),
                                                      ("equipe", "Equipe", "equipes")],
                      ["nome", "nome_padrao", "equipe", "cargo", "cliente"], "/t/pessoas/colaborador/novo",
                      "Novo colaborador")

    @_tela("Novo colaborador")
    def pessoa_nova(srv):
        return _novo(srv, PESSOAS, "Colaboradores Operação")

    @_tela("Colaborador")
    def pessoa(srv, id_):
        return _ficha(srv, PESSOAS, id_, "Colaboradores Operação")

    bp.add_url_rule("/colaboradores", "cad_pessoas", pessoas)
    bp.add_url_rule("/colaborador/novo", "cad_pessoa_nova", pessoa_nova, methods=["GET", "POST"])
    bp.add_url_rule("/colaborador/<id_>", "cad_pessoa", pessoa, methods=["GET", "POST"])
