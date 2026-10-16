"""Atualizar o Registro mestre pelo CSV do BD_Operações novo (15/10/2026).

Levi, 15/10/2026, com o `operacao_usinas_2026-10-15.csv` (258 usinas, 73 colunas, `;` e decimal com vírgula): "Esse é o
novo BD_Operações, conseguimos atualizar os dados do Nexus com esse CSV? daqui a duas semanas vamos ter acesso em tempo
real a esses dados". Esta é a ponte até lá: a mesma regra (`proposta` + `aplicar`) serve ao arquivo de hoje e às linhas que
a fonte em tempo real mandar.

As regras (as decisões do Levi no mesmo dia, e o que o ensaio com o cadastro mostrou):
- casa pelo "ID da usina" (o "ID do BD", UFV-xxx): as 258 do arquivo de 15/10 casaram, nenhuma nova e nenhuma faltando.
  Usina sem par fica de fora e é listada; nada é criado nem excluído (a importação antiga, pela carga inteira, marcava
  como excluído o que não viesse);
- grava campo a campo, pela ficha (`Servico.salvar`, com versão e auditoria), só o que MUDOU, e só as colunas que a
  pessoa deixou marcadas na prévia;
- célula vazia no CSV NÃO apaga o que o Nexus tem (Levi: "Manter o do Nexus");
- número que só difere pelo arredondamento do CSV (7,0488 no Nexus e 7,049 no CSV) fica o do Nexus, o mais preciso; texto
  que é o mesmo número ("23.1" × "23,1") também não muda;
- campo automático vazio (a receita mensal = preço por MWp × potência) só recebe o valor do CSV se ele for OUTRO: o CSV
  que traz a mesma conta não congela o automático;
- o código "CÓDIGO" (o valor de mentira da Matões 100 desde a planilha antiga) não troca o código: é ele que liga a usina
  ao Fracttal;
- valor de lista novo entra na lista (os status "AGUARDANDO LIBERAÇÃO", "PRONTA PARA MOBILIZAR"; Levi: "Aplicar os
  novos"); o que só difere em acento, maiúscula, hífen ou espaço ("Centro-Oeste" × "Centro Oeste") é o mesmo valor;
- a equipe é a do CSV (Levi: "Trocar pela do CSV"): pelo nome; a que não existe é criada (sem código nem região, que a
  ficha da equipe completa). "0" é vazio e "N/A" é "a usina não tem", como na importação antiga;
- o cliente e o Responsável O&M só casam com quem já está no cadastro. A pessoa casa pelo nome inteiro ou pelo nome do
  cadastro contido no do CSV, na ordem e com o mesmo primeiro nome, quando só uma pessoa serve: o CSV de 15/10 traz o
  nome completo ("Fulana Rodrigues Prado"; nomes fictícios, o repositório é público) e o cadastro o curto ("Fulana
  Prado"): eram 203 usinas sem par pelo nome inteiro. O que não casa fica como está e é listado;
- o valor do CSV contido no do Nexus, que tem mais detalhe ("SUN2000-250KTL-H1 + SUN2000-330KTL-H1" vira
  "SUN2000-250KTL-H1"), é marcado na prévia ("o CSV resume"), para a pessoa decidir a coluna;
- as colunas sem campo no Nexus (Mobilizado?, Impeditivo, Próximo passo, os kits...) ficam de fora e são listadas;
- "Pessoas da equipe" ("Nome (Cargo), Nome (Cargo · Desligado)"; Levi, 16/10: "procure esses 5 no fractall, faça a
  relação e adicione no Nexus, não podemos ficar sem informação! Se adapte"): a pessoa casa também pelo NOME PADRÃO
  calculado (o furo de 16/10: o CSV escreve "Bruno Samiel Anjos Albuquerque" e "Italo Vitor das Virgens Oliveira", a
  ficha "Bruno Samuel..." e "Italo Vitor Dasvirgens...", e os padrões "Bruno Albuquerque" e "Italo Oliveira" estão
  contidos no nome do CSV). Da ficha que casa, completa só o VAZIO (cargo, status, e-mail da conta do Fracttal, que é o
  que liga a ficha ao Fracttal) e põe na equipe do CSV quando ele a dá numa equipe só (quem atende duas fica e é
  listado). Quem não tem ficha e não está desligado ganha uma (Colaborador de campo, o cargo e a equipe do CSV, Ativo),
  com o nome e o e-mail da conta do Fracttal quando ela existe (o Caio da Silva Cordeiro, 16/10).
"""
import csv
import io
import re
import unicodedata
from collections import Counter

from . import tipos
from .calculos import ERRO
from .esquema import ENTIDADES
from .servico import chave_texto

ID = "ID da usina"
# coluna do CSV -> campo da usina (os de lista, texto, número, data e sim/não; os sensíveis vão cifrados pela ficha)
COLUNAS = {
    "Nome": "nome", "Código": "codigo", "Status": "status", "Tipologia": "tipologia",
    "Data de mobilização": "data_mobilizacao", "Potência contratual (MWp)": "potencia_contratual",
    "Potência real (MWp)": "potencia_real", "Capacidade (MW)": "capacidade_instalada", "Área (ha)": "area_instalada",
    "Nº de módulos": "n_modulos", "Fabricante dos módulos": "fabricante_modulos", "Modelo do módulo": "modelo_modulo",
    "Potência do módulo (W)": "potencia_modulos", "Fabricante dos inversores": "fabricante_inversores",
    "Modelo do inversor": "modelo_inversores", "Potência do inversor (kW)": "potencia_inversores",
    "Nº inversores": "n_inversores", "Fabricante do tracker": "fabricante_tracker",
    "Modelo do tracker": "modelo_tracker", "Qtd. TCU e motor": "qtd_tcu_motor",
    "Tipo transformador": "tipo_transformador", "Tensão de linha": "tensao_linha", "Transformador auxiliar": "tr_aux",
    "Concessionária": "concessionaria", "Nº cabines": "n_cabine", "Nº skids": "n_skid", "Nº QGBT": "n_qgbt",
    "Nº transformadores": "n_transformador", "UF": "uf", "Cidade": "cidade", "Região": "regiao",
    "Link do mapa": "maps", "Endereço": "endereco", "Latitude": "latitude", "Longitude": "longitude",
    "Contrato assinado": "contrato_assinado", "CNPJ de faturamento": "cnpj_faturamento", "Nome SPE": "nome_spe",
    "Instalação": "instalacao", "Conta contrato": "conta_contrato", "CNPJ": "cnpj",
    "Prazo contratual (meses)": "prazo_meses", "Receita mensal (R$)": "receita_mensal",
    "Receita contratual (R$)": "receita_contratual", "Código instalação (CMMS)": "codigo_instalacao_cmms",
    "Código equipamento (CMMS)": "codigo_equipamento_cmms", "Acesso comando remoto": "acesso_comando_remoto",
    "Acesso visualização": "acesso_visualizacao", "Databook": "databook",
}
REFS = {"Cliente": "cliente", "Equipe": "equipe", "Responsável O&M": "responsavel_om"}
COL_PESSOAS = "Pessoas da equipe"
CAMPO_PESSOAS = "pessoas"                   # a "coluna" das pessoas na prévia (a caixa de marcar dela)
VINCULO_NOVO = "Colaborador de campo"
# o cargo como o CSV escreve ("Técnico de O&M", "Eletricista", "Mantenedor", "Man") -> o da lista do cadastro
_CARGOS = (("tecnic", "Técnico O&M"), ("eletric", "Eletricista O&M"), ("manten", "Mantenedor O&M"))
_NUMERICOS = ("numero", "moeda", "coordenada")
_PLACEHOLDER_CODIGO = {"codigo"}            # chave_texto("CÓDIGO")
# o que sobra do valor do Nexus tirado o do CSV e que NÃO é detalhe: unidade e pontuação ("575 Wp" -> "575")
_SO_UNIDADE = re.compile(r"(?:[\s.,;:/()+\-]|\b(?:wp|kwp|mwp|w|kw|mw|kva|kv|v)\b)*")


def ler_csv(dados: bytes) -> tuple[list[str], list[dict]]:
    """(cabeçalho, linhas) do CSV: UTF-8 com ou sem BOM (senão cp1252), `;` ou `,`."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):           # o latin-1 lê qualquer byte: nunca sobra sem texto
        try:
            txt = dados.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    primeira = txt.split("\n", 1)[0]
    delim = ";" if primeira.count(";") >= primeira.count(",") else ","
    leitor = csv.DictReader(io.StringIO(txt), delimiter=delim)
    cab = [str(c or "").strip() for c in (leitor.fieldnames or [])]
    linhas = [{str(k or "").strip(): (v if isinstance(v, str) else "") for k, v in ln.items()} for ln in leitor]
    return cab, linhas


def _chave_lista(v) -> str:
    """'Centro-Oeste', 'centro oeste' e 'CENTRO OESTE' são o mesmo valor de lista."""
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[\s\-–—_]+", " ", s).strip()


def _decimais(texto: str) -> int:
    m = re.search(r"[,.](\d+)\s*$", texto.strip())
    return len(m.group(1)) if m else 0


def _so_arredondado(tipo: str, texto: str, atual) -> bool:
    """O valor do CSV é o do Nexus arredondado nas casas que o CSV mostra (fica o do Nexus, mais preciso)."""
    if not isinstance(atual, (int, float)) or isinstance(atual, bool):
        return False
    try:
        v = tipos.de_formulario(tipo, texto)
    except tipos.ValorInvalido:
        return False
    if not isinstance(v, (int, float)):
        return False
    return abs(v - atual) <= 0.5 * 10 ** -_decimais(texto) + 1e-9


def _mesmo_numero(a: str, b: str) -> bool:
    """Texto que é o mesmo número, com ponto ou vírgula decimal ("23.1" × "23,1")."""
    def num(s):
        s = str(s or "").strip()
        if not re.fullmatch(r"[+-]?\d+([.,]\d+)?", s):
            return None
        return float(s.replace(",", "."))
    x, y = num(a), num(b)
    return x is not None and x == y


def _resume(antes: str, depois: str) -> bool:
    """O valor do CSV está contido no do Nexus, que diz mais do que unidade ("250 kW / 275 kVA" -> "250")."""
    a, d = chave_texto(antes), chave_texto(depois)
    if not d or len(a) <= len(d):
        return False
    # contido como palavra: "250" está em "250 kW", não em "1250" (aí é outro número, não resumo)
    m = re.search(r"(?<![0-9a-z])" + re.escape(d) + r"(?![0-9a-z])", a)
    return bool(m) and not _SO_UNIDADE.fullmatch(a[:m.start()] + " " + a[m.end():])


def _limpo(t) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip()


def _nomes(s) -> list:
    return chave_texto(s).split()


def _contido(curto: list, longo: list) -> bool:
    """Os nomes de `curto` aparecem em `longo`, na mesma ordem e com o mesmo primeiro nome ("Fulana Prado" em
    "Fulana Rodrigues Prado"). Um nome só não basta."""
    if len(curto) < 2 or len(longo) < len(curto) or curto[0] != longo[0]:
        return False
    resto = iter(longo)
    return all(t in resto for t in curto)


def _cargo_do_csv(texto):
    k = chave_texto(texto)
    for prefixo, cargo in _CARGOS:
        if k.startswith(prefixo):
            return cargo
    return "Mantenedor O&M" if k == "man" else None


def pessoas_da_celula(texto) -> list[tuple]:
    """'Fulana Prado (Técnico de O&M), Beltrano Nunes (Eletricista · Desligado)' -> [(nome, cargo, desligado)]. Só a
    vírgula separa: "Manuel ... da Silva e Silva" é um nome só."""
    out = []
    for parte in str(texto or "").split(","):
        m = re.match(r"^\s*(.*?)\s*(?:\(([^)]*)\))?\s*$", parte)
        nome = _limpo(m.group(1)) if m else ""
        if not nome:
            continue
        info = [x.strip() for x in re.split(r"[·•|]", (m.group(2) or "")) if x.strip()]
        cargo = next((c for c in (_cargo_do_csv(x) for x in info) if c), None)
        out.append((nome, cargo, any(chave_texto(x) == "desligado" for x in info)))
    return out


def _primeiro_e_ultimo(nome) -> str:
    partes = str(nome or "").split()
    return f"{partes[0]} {partes[-1]}" if len(partes) > 1 else " ".join(partes)


def _indice_pessoas(srv) -> list:
    """(id, [nome completo, nome padrão]) das fichas; o padrão é o CALCULADO quando a ficha não tem um digitado."""
    out = []
    for r in srv.registros("pessoas"):
        padrao = r.valor("nome_padrao") if r.ent.tem("nome_padrao") else None
        out.append((r.id, [_nomes(r.valores.get("nome")), _nomes("" if padrao is ERRO else padrao)]))
    return out


def _achar_pessoa(texto, pessoas: list):
    """O id da pessoa do cadastro, ou None (ninguém, ou mais de uma que serve: não adivinha)."""
    alvo = _nomes(texto)
    if not alvo:
        return None
    exatos = {pid for pid, nomes in pessoas if alvo in nomes}
    if exatos:
        return next(iter(exatos)) if len(exatos) == 1 else None
    parecidos = {pid for pid, nomes in pessoas if any(n and (_contido(n, alvo) or _contido(alvo, n)) for n in nomes)}
    return next(iter(parecidos)) if len(parecidos) == 1 else None


def proposta(linhas: list, srv, cabecalho=None, fracttal=None) -> dict:
    """O que a atualização faria, sem gravar nada: as usinas que mudam (campo a campo, antes e depois), por coluna, o que
    fica como está e por quê, as equipes e os valores de lista novos, o que não casou e as pessoas das equipes.
    `fracttal` = o pessoal do Fracttal (`fracttal_pessoal.ler_pessoal()["pessoas"]`: nome, email, conta_ativa); sem
    ele, a ficha nova nasce sem e-mail."""
    ent = ENTIDADES["usinas"]
    campo = {c.id: c for c in ent.campos}
    usinas = {}
    for r in srv.registros("usinas"):
        k = str(r.valores.get("id_bd") or "").strip().upper()
        if k and k not in usinas:
            usinas[k] = r
    listas = srv.listas()
    clientes = {chave_texto(r.valores.get("nome")): r.id for r in srv.registros("clientes")}
    equipes = {chave_texto(r.valores.get("nome")): r for r in srv.registros("equipes")}
    pessoas = _indice_pessoas(srv)
    colunas = {**COLUNAS, **REFS}
    por_campo = {cid: {"campo": cid, "coluna": col, "rotulo": campo[cid].rotulo, "oculto": bool(campo[cid].oculto),
                       "secao": campo[cid].secao, "linhas": [], "resumem": 0}
                 for col, cid in colunas.items() if cid in campo and campo[cid].editavel}
    mudancas, sem_par, vistos = [], [], set()
    vazios, arredondados = Counter(), Counter()
    ignorados, ilegiveis, sem_cliente, sem_pessoa = Counter(), [], Counter(), Counter()
    novos_valores, equipes_novas = {}, {}

    def anotar(r, k, form, cid, valor, antes, depois, nota=""):
        form[cid] = valor
        resume = _resume(antes, depois)
        pc = por_campo[cid]
        pc["linhas"].append({"id_bd": k, "nome": r.titulo, "antes": antes, "depois": depois, "nota": nota,
                             "resume": resume})
        pc["resumem"] += int(resume)

    for ln in linhas:
        k = _limpo(ln.get(ID)).upper()
        if not k or k in vistos:
            continue
        vistos.add(k)
        r = usinas.get(k)
        if r is None:
            sem_par.append({"id_bd": k, "nome": _limpo(ln.get("Nome"))})
            continue
        form = {}
        for col, cid in COLUNAS.items():
            c = campo.get(cid)
            if c is None or not c.editavel or col not in ln:
                continue
            texto, atual = _limpo(ln.get(col)), r.valores.get(cid)
            if c.modo == "automatico" and (atual is None or atual == ""):
                # vazio = automático (a receita mensal sai do preço por MWp × potência): o CSV que traz a mesma conta
                # não congela o valor; compara com o que o Nexus calcula
                atual = r.valor(cid)
                atual = None if atual is ERRO else atual
            antes = srv._form_valor(c, atual)
            if not texto:
                if antes:
                    vazios[col] += 1
                continue
            if cid == "codigo" and chave_texto(texto) in _PLACEHOLDER_CODIGO:
                ignorados["Código (o valor de mentira \"CÓDIGO\")"] += 1
                continue
            if c.tipo == "lista":
                if _chave_lista(antes) == _chave_lista(texto):
                    continue
                existente = next((v for v in listas.get(c.lista, []) if _chave_lista(v) == _chave_lista(texto)), None)
                if existente is None:
                    # uma grafia só para todas as usinas: a lista recebe o valor uma vez, como a primeira linha o escreveu
                    existente = novos_valores.setdefault(c.lista, {}).setdefault(_chave_lista(texto), texto)
                texto = existente
            elif c.tipo in _NUMERICOS and _so_arredondado(c.tipo, texto, atual):
                if tipos.de_formulario(c.tipo, texto) != atual:     # o mesmo número não é arredondamento: não conta
                    arredondados[col] += 1
                continue
            else:
                try:
                    convertido = tipos.de_formulario("texto" if c.tipo == "sugestao" else c.tipo, texto)
                except tipos.ValorInvalido as e:
                    ilegiveis.append({"id_bd": k, "nome": r.titulo, "coluna": col, "motivo": str(e)})
                    continue
                if convertido == atual or _limpo(antes) == texto or _mesmo_numero(antes, texto):
                    continue
            anotar(r, k, form, cid, texto, antes, texto)
        # as referências: o cliente e a pessoa só casam com quem existe; a equipe nova é criada
        for col, cid in REFS.items():
            texto = _limpo(ln.get(col))
            if not texto or texto == "0" or col not in ln:
                continue                            # "0" é a célula vazia da fórmula do Excel, como na importação antiga
            c, atual = campo[cid], r.valores.get(cid)
            depois, nota = texto, ""
            if tipos.marcador(texto):
                alvo = tipos.marcador(texto)        # "N/A": a usina não tem (não é equipe nem pessoa chamada "N/A")
            elif cid == "cliente":
                alvo = clientes.get(chave_texto(texto))
                if alvo is None:
                    sem_cliente[texto] += 1
                    continue
            elif cid == "equipe":
                e = equipes.get(chave_texto(texto))
                alvo = e.id if e else "nova:" + texto
                if e is None:
                    equipes_novas[chave_texto(texto)] = texto
                    nota = "equipe nova"
            else:
                alvo = _achar_pessoa(texto, pessoas)
                if alvo is None:
                    sem_pessoa[texto] += 1
                    continue
                nome = srv.titulo_de("pessoas", alvo)
                if chave_texto(nome) != chave_texto(texto):
                    depois, nota = nome, f"no CSV: {texto}"
            if str(atual or "") == str(alvo):
                continue
            anotar(r, k, form, cid, alvo, srv.titulo_de(c.lista, atual) if atual else "", depois, nota)
        if form:
            mudancas.append({"usina_id": r.id, "id_bd": k, "nome": r.titulo, "versao": r.versao, "formulario": form})
    cab = list(cabecalho or (linhas[0].keys() if linhas else []))
    sem_campo = [c for c in cab if c and c != ID and c not in COLUNAS and c not in REFS and c != COL_PESSOAS]
    pessoas_mudam, varias_equipes, desligadas_sem_ficha = _proposta_pessoas(linhas, srv, usinas, equipes, pessoas,
                                                                             fracttal or [])
    return {"mudancas": mudancas, "sem_par": sem_par, "total": len(vistos),
            "por_campo": [pc for pc in por_campo.values() if pc["linhas"]],
            "vazios": dict(vazios.most_common()), "arredondados": dict(arredondados.most_common()),
            "ignorados": dict(ignorados), "ilegiveis": ilegiveis, "sem_cliente": dict(sem_cliente.most_common()),
            "sem_pessoa": dict(sem_pessoa.most_common()),
            "novos_valores": {lista: sorted(v.values()) for lista, v in novos_valores.items()},
            "equipes_novas": sorted(equipes_novas.values(), key=chave_texto), "sem_campo": sem_campo,
            "pessoas": pessoas_mudam, "pessoas_varias_equipes": varias_equipes,
            "pessoas_desligadas_sem_ficha": desligadas_sem_ficha}


def _proposta_pessoas(linhas, srv, usinas, equipes, pessoas, fracttal):
    """As fichas que a coluna "Pessoas da equipe" cria ou completa (ver o docstring do módulo)."""
    nome_eq = {r.id: r.valores.get("nome") for r in equipes.values()}
    membros = {}
    for ln in linhas:
        k = _limpo(ln.get(ID)).upper()
        if k not in usinas or COL_PESSOAS not in ln:
            continue
        texto_eq = _limpo(ln.get("Equipe"))
        alvo_eq = None
        if texto_eq and texto_eq != "0" and not tipos.marcador(texto_eq):
            e = equipes.get(chave_texto(texto_eq))
            alvo_eq = e.id if e else "nova:" + texto_eq
        for nome, cargo, desligado in pessoas_da_celula(ln.get(COL_PESSOAS)):
            pid = _achar_pessoa(nome, pessoas)
            m = membros.setdefault(pid or "novo:" + chave_texto(nome), {"pid": pid, "nome": nome, "equipes": set(),
                                                                         "cargos": set(), "desligado": False})
            if alvo_eq:
                m["equipes"].add(alvo_eq)
            if cargo:
                m["cargos"].add(cargo)
            m["desligado"] = m["desligado"] or desligado
    contas = [(i, [_nomes(f.get("nome")), _nomes(_primeiro_e_ultimo(f.get("nome")))])
              for i, f in enumerate(fracttal) if f.get("email")]
    por_email = {}
    for r in srv.registros("pessoas", incluir_excluidos=True):
        e = str(r.valores.get("email") or "").strip().lower()
        if e:
            por_email[e] = r

    def conta(nome):
        i = _achar_pessoa(nome, contas)
        return fracttal[i] if i is not None else None

    def titulo_eq(e):
        return e[5:] if str(e).startswith("nova:") else (nome_eq.get(e) or str(e or ""))

    mudam, varias, desligadas = [], [], []
    for chave, m in sorted(membros.items(), key=lambda kv: chave_texto(kv[1]["nome"])):
        f = conta(m["nome"])
        email = str((f or {}).get("email") or "").strip().lower()
        r = srv.registro("pessoas", m["pid"]) if m["pid"] else por_email.get(email) if email else None
        if r is not None and r.excluido:
            r = None if m["pid"] is None else r
        if len(m["equipes"]) > 1:
            varias.append({"nome": r.titulo if r else m["nome"], "equipes": sorted(titulo_eq(e) for e in m["equipes"])})
        equipe = next(iter(m["equipes"])) if len(m["equipes"]) == 1 else None
        cargo = next(iter(m["cargos"])) if len(m["cargos"]) == 1 else None
        if r is None:
            if m["desligado"]:
                desligadas.append(m["nome"])
                continue
            form = {"nome": (f or {}).get("nome") or m["nome"], "vinculo": VINCULO_NOVO, "status": "Ativo"}
            if cargo:
                form["cargo"] = cargo
            if equipe:
                form["equipe"] = equipe
            if email:
                form["email"] = email
            mudam.append({"acao": "criar", "pessoa_id": None, "nome": form["nome"], "versao": None, "formulario": form,
                          "campos": [("Ficha nova", " · ".join(x for x in (cargo or "", titulo_eq(equipe) if equipe else "",
                                                                       "e-mail do Fracttal" if email else "") if x))]})
            continue
        v, form, campos = r.valores, {}, []
        if equipe and str(v.get("equipe") or "") != str(equipe):
            form["equipe"] = equipe
            campos.append(("Equipe", f"{titulo_eq(v.get('equipe')) or '—'} → {titulo_eq(equipe)}"))
        if cargo and not v.get("cargo"):
            form["cargo"] = cargo
            campos.append(("Cargo", f"— → {cargo}"))
        if not v.get("status"):
            form["status"] = "Desligado" if m["desligado"] else "Ativo"
            campos.append(("Status", f"— → {form['status']}"))
        if email and not v.get("email") and (email not in por_email or por_email[email].id == r.id):
            form["email"] = email
            campos.append(("E-mail", "— → o da conta do Fracttal"))
        if form:
            mudam.append({"acao": "completar", "pessoa_id": r.id, "nome": r.titulo, "versao": r.versao,
                          "formulario": form, "campos": campos})
    return mudam, varias, desligadas


def aplicar(prop: dict, srv, quem: str, campos=None) -> dict:
    """Grava a proposta: os valores de lista novos, as equipes novas e, usina a usina, os campos que mudam (a versão é a
    da leitura da prévia: quem salvou a ficha nesse meio tempo ganha, e a usina dela é listada). `campos` = só estes
    campos (as colunas que ficaram marcadas na prévia); None = todos."""
    so = set(campos) if campos is not None else None
    usa = {}
    for c in ENTIDADES["usinas"].campos:
        if c.tipo == "lista":
            usa.setdefault(c.lista, set()).add(c.id)
    incluidos, criadas, conflitos, erros, atualizadas = [], {}, [], [], 0
    for lista, valores in (prop.get("novos_valores") or {}).items():
        if so is not None and not (usa.get(lista, set()) & so):
            continue
        for v in valores:
            if srv.adicionar_valor(lista, v, quem).ok:
                incluidos.append(v)
    if so is None or "equipe" in so:
        for nome in prop.get("equipes_novas") or []:
            res = srv.criar("equipes", {"nome": nome}, quem)
            if res.ok:
                criadas[chave_texto(nome)] = res.registro.id
            else:
                erros.append({"id_bd": "", "nome": f"equipe {nome}", "erro": "; ".join((res.erros or {}).values())})
    for m in prop.get("mudancas") or []:
        form = {k: v for k, v in m["formulario"].items() if so is None or k in so}
        if str(form.get("equipe") or "").startswith("nova:"):
            nova = criadas.get(chave_texto(form["equipe"][5:]))
            if nova is None:
                form.pop("equipe")
            else:
                form["equipe"] = nova
        if not form:
            continue
        res = srv.salvar("usinas", m["usina_id"], form, m["versao"], quem)
        if res.ok:
            atualizadas += 1
        elif res.conflito is not None:
            conflitos.append({"id_bd": m["id_bd"], "nome": m["nome"]})
        else:
            erros.append({"id_bd": m["id_bd"], "nome": m["nome"], "erro": "; ".join(
                f"{k}: {v}" for k, v in (res.erros or {}).items())})
    pessoas_criadas = pessoas_completadas = 0
    if so is None or CAMPO_PESSOAS in so:
        for m in prop.get("pessoas") or []:
            form = dict(m["formulario"])
            if str(form.get("equipe") or "").startswith("nova:"):
                nova = criadas.get(chave_texto(form["equipe"][5:]))
                if nova is None:
                    form.pop("equipe")
                else:
                    form["equipe"] = nova
            if m["acao"] == "criar":
                res = srv.criar("pessoas", form, quem)
            else:
                res = srv.salvar("pessoas", m["pessoa_id"], form, m["versao"], quem)
            if res.ok:
                if m["acao"] == "criar":
                    pessoas_criadas += 1
                else:
                    pessoas_completadas += 1
            elif res.conflito is not None:
                conflitos.append({"id_bd": "pessoa", "nome": m["nome"]})
            else:
                erros.append({"id_bd": "pessoa", "nome": m["nome"], "erro": "; ".join(
                    f"{k}: {v}" for k, v in (res.erros or {}).items())})
    srv.auditar(quem, "atualizou pelo CSV do BD_Operações", "usinas", str(prop.get("arquivo") or ""), [
        f"{atualizadas} usinas", f"{len(criadas)} equipes novas", f"{len(incluidos)} valores de lista novos",
        f"{pessoas_criadas} pessoas novas", f"{pessoas_completadas} pessoas completadas",
        f"{len(so) if so is not None else 'todas as'} colunas"])
    return {"atualizadas": atualizadas, "equipes_criadas": len(criadas), "valores_incluidos": incluidos,
            "pessoas_criadas": pessoas_criadas, "pessoas_completadas": pessoas_completadas,
            "conflitos": conflitos, "erros": erros}
