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
- o cliente só casa com quem já está no cadastro. A pessoa casa pelo nome inteiro, pelo nome padrão ou pelo nome do
  cadastro contido no do CSV, na ordem e com o mesmo primeiro nome, quando só uma ficha serve: o CSV de 15/10 traz o
  nome completo ("Fulana Rodrigues Prado"; nomes fictícios, o repositório é público) e o cadastro o curto ("Fulana
  Prado"): eram 203 usinas sem par pelo nome inteiro. Nome que serve a duas fichas não liga nem cria (é avisado);
- o valor do CSV contido no do Nexus, que tem mais detalhe ("SUN2000-250KTL-H1 + SUN2000-330KTL-H1" vira
  "SUN2000-250KTL-H1"), é marcado na prévia ("o CSV resume"), para a pessoa decidir a coluna;
- as colunas sem campo no Nexus (Mobilizado?, Impeditivo, Próximo passo, os kits...) ficam de fora e são listadas;
- AS PESSOAS DA USINA SÃO AS DO CSV (Levi, 16/10: "não quero que siga com os dados antigos, tem que aplicar no Nexus
  também! Entenda... a regra ainda não é o Nexus, temos que nos adaptar as informações que vem"). O Responsável O&M e o
  técnico, o eletricista e o mantenedor da usina (os da "Pessoas da equipe" DELA: "Nome (Cargo), Nome (Cargo ·
  Desligado)", só a vírgula separa) vão para a própria usina; quem atende duas equipes aparece nas duas; o CSV que lista
  a equipe sem um dos três deixa a usina sem ele ("-"), em vez de herdar o da equipe ou o do BD antigo; célula vazia
  não mexe. Quem não tem ficha ganha uma (o responsável, Supervisor de Campo, como a importação antiga; o resto,
  Colaborador de campo com o cargo e a equipe do CSV), com o nome e o e-mail da conta do Fracttal quando ela existe (é o
  e-mail que liga a ficha ao Fracttal; o Caio da Silva Cordeiro e o Dallas Ferreira, 16/10). Da ficha que existe,
  completa só o VAZIO (cargo, status, e-mail da conta do Fracttal) e a equipe quando o CSV dá uma só. A pessoa casa
  também pelo NOME PADRÃO calculado (o furo de 16/10: o CSV escreve "Bruno Samiel..." e "Italo Vitor das Virgens...",
  a ficha "Bruno Samuel..." e "Italo Vitor Dasvirgens...", e os padrões estão contidos no nome do CSV).
"""
import csv
import io
import re
import unicodedata
from collections import Counter

from . import tipos
from .calculos import ERRO
from .esquema import ENTIDADES, VINCULO_CAMPO, VINCULO_SUPERVISOR_CAMPO
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
CAMPO_PESSOAS = "pessoas"                   # a "coluna" das fichas de pessoas na prévia (a caixa de marcar dela)
NOVA_PESSOA = "nova-pessoa:"                # a ficha que nasce nesta aplicação (a usina aponta para ela)
NENHUM = "-"                                # o marcador "não tem": a usina fica sem a pessoa, sem herdar a da equipe
# técnico, eletricista e mantenedor da usina: os da "Pessoas da equipe" dela
PAPEIS = (("tecnico_om", "Técnico O&M", "técnico"), ("eletricista_om", "Eletricista O&M", "eletricista"),
          ("mantenedor_om", "Mantenedor O&M", "mantenedor"))
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


def _casar_pessoa(texto, pessoas: list):
    """(id, "") da ficha; (None, "nenhuma"), ou (None, "duas") quando o nome serve a mais de uma ficha (não adivinha nem
    cria outra)."""
    alvo = _nomes(texto)
    if not alvo:
        return None, "nenhuma"
    exatos = {pid for pid, nomes in pessoas if alvo in nomes}
    if exatos:
        return (next(iter(exatos)), "") if len(exatos) == 1 else (None, "duas")
    parecidos = {pid for pid, nomes in pessoas if any(n and (_contido(n, alvo) or _contido(alvo, n)) for n in nomes)}
    if len(parecidos) == 1:
        return next(iter(parecidos)), ""
    return None, ("duas" if parecidos else "nenhuma")


def _achar_pessoa(texto, pessoas: list):
    """O id da pessoa do cadastro, ou None (ninguém, ou mais de uma que serve: não adivinha)."""
    return _casar_pessoa(texto, pessoas)[0]


class _Fichas:
    """As fichas de pessoas que a atualização usa: acha a do cadastro (pelo nome, ou pela conta do Fracttal, que acha a
    ficha de outro nome pelo e-mail) ou anota uma nova, com o nome e o e-mail da conta do Fracttal quando ela existe (é
    o e-mail que liga a ficha ao Fracttal, o critério do login)."""

    def __init__(self, srv, pessoas, fracttal):
        self.srv, self.pessoas, self.fracttal = srv, pessoas, fracttal
        self.contas = [(i, [_nomes(f.get("nome")), _nomes(_primeiro_e_ultimo(f.get("nome")))])
                       for i, f in enumerate(fracttal) if f.get("email")]
        self.por_email = {}
        for r in srv.registros("pessoas"):
            e = str(r.valores.get("email") or "").strip().lower()
            if e:
                self.por_email[e] = r
        self.novas = {}          # chave -> {"chave", "nome", "formulario", "fracttal"}
        self.duas = Counter()    # nome que serve a duas fichas: não liga nem cria

    def conta(self, nome):
        i = _achar_pessoa(nome, self.contas)
        return self.fracttal[i] if i is not None else None

    def ref(self, nome, vinculo, cargo=None, equipe=None):
        """(ref, título, nota): o id da ficha, ou NOVA_PESSOA + chave da que vai nascer; ref None = nome de duas fichas."""
        pid, motivo = _casar_pessoa(nome, self.pessoas)
        if pid:
            titulo = self.srv.titulo_de("pessoas", pid)
            return pid, titulo, ("" if chave_texto(titulo) == chave_texto(nome) else f"no CSV: {nome}")
        if motivo == "duas":
            self.duas[nome] += 1
            return None, "", ""
        f = self.conta(nome)
        email = str((f or {}).get("email") or "").strip().lower()
        if email and email in self.por_email:                    # a conta do Fracttal acha a ficha de outro nome
            r = self.por_email[email]
            return r.id, r.titulo, f"no CSV: {nome}"
        chave = chave_texto((f or {}).get("nome") or nome)
        n = self.novas.get(chave)
        if n is None:
            form = {"nome": (f or {}).get("nome") or nome, "vinculo": vinculo, "status": "Ativo"}
            if email:
                form["email"] = email
            n = self.novas[chave] = {"chave": chave, "nome": form["nome"], "formulario": form, "fracttal": bool(email)}
        if cargo and "cargo" not in n["formulario"]:
            n["formulario"]["cargo"] = cargo
        if equipe and "equipe" not in n["formulario"]:
            n["formulario"]["equipe"] = equipe
        return NOVA_PESSOA + chave, n["nome"], "ficha nova"


def _equipe_do_csv(ln, equipes):
    """A equipe da linha: o id, "nova:" + nome (a que vai nascer) ou None."""
    texto = _limpo(ln.get("Equipe"))
    if not texto or texto == "0" or tipos.marcador(texto):
        return None
    e = equipes.get(chave_texto(texto))
    return e.id if e else "nova:" + texto


def proposta(linhas: list, srv, cabecalho=None, fracttal=None) -> dict:
    """O que a atualização faria, sem gravar nada: as usinas que mudam (campo a campo, antes e depois), por coluna, o que
    fica como está e por quê, as equipes e os valores de lista novos, o que não casou e as fichas de pessoas que nascem
    ou se completam. `fracttal` = o pessoal do Fracttal (`fracttal_pessoal.ler_pessoal()["pessoas"]`: nome, email,
    conta_ativa); sem ele, a ficha nova nasce sem e-mail."""
    from .importar import eh_rotulo_de_regiao
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
    regioes = [r.valores.get("nome") for r in srv.registros("regioes_campo")]
    pessoas = _indice_pessoas(srv)
    fichas = _Fichas(srv, pessoas, fracttal or [])
    colunas = {**COLUNAS, **REFS}
    por_campo = {cid: {"campo": cid, "coluna": col, "rotulo": campo[cid].rotulo, "oculto": bool(campo[cid].oculto),
                       "secao": campo[cid].secao, "linhas": [], "resumem": 0}
                 for col, cid in colunas.items() if cid in campo and campo[cid].editavel}
    for cid, _, papel in PAPEIS:
        por_campo[cid] = {"campo": cid, "coluna": f"{campo[cid].rotulo} (Pessoas da equipe)", "rotulo": campo[cid].rotulo,
                          "oculto": False, "secao": campo[cid].secao, "linhas": [], "resumem": 0}
    mudancas, sem_par, vistos = [], [], set()
    vazios, arredondados = Counter(), Counter()
    ignorados, ilegiveis, sem_cliente, sem_pessoa = Counter(), [], Counter(), Counter()
    novos_valores, equipes_novas = {}, {}

    def anotar(r, k, form, cid, valor, antes, depois, nota=""):
        form[cid] = valor
        resume = _resume(antes, depois) if cid in COLUNAS.values() else False
        pc = por_campo[cid]
        pc["linhas"].append({"id_bd": k, "nome": r.titulo, "antes": antes, "depois": depois, "nota": nota,
                             "resume": resume})
        pc["resumem"] += int(resume)

    def pessoa_hoje(v):
        return "" if v is None or v == "" or v is ERRO or tipos.marcador(v) else srv.titulo_de("pessoas", v)

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
        # as referências: o cliente só casa com quem existe; a equipe nova é criada; o Responsável O&M que não tem ficha
        # ganha uma (Supervisor de Campo), como a importação antiga fazia: o CSV manda, a usina não segue com o antigo
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
                if _casar_pessoa(texto, pessoas)[0] is None and eh_rotulo_de_regiao(texto, regioes):
                    sem_pessoa[texto] += 1          # a região no lugar da pessoa (a vaga): não vira ficha
                    continue
                alvo, depois, nota = fichas.ref(texto, VINCULO_SUPERVISOR_CAMPO)
                if alvo is None:
                    sem_pessoa[texto] += 1          # nome de duas fichas: não adivinha
                    continue
            if str(atual or "") == str(alvo):
                continue
            anotar(r, k, form, cid, alvo, srv.titulo_de(c.lista, atual) if atual else "", depois, nota)
        # técnico, eletricista e mantenedor da usina: os da "Pessoas da equipe" DELA (Levi, 16/10: "não quero que siga
        # com os dados antigos"); quem atende duas equipes aparece nas duas. O CSV que lista a equipe sem um dos três
        # deixa a usina sem ele ("-"), em vez de herdar o da equipe ou o do BD antigo. Célula vazia não mexe
        celula = _limpo(ln.get(COL_PESSOAS)) if COL_PESSOAS in ln else ""
        if celula:
            membros = pessoas_da_celula(celula)
            eq = _equipe_do_csv(ln, equipes)
            for cid, cargo, papel in PAPEIS:
                atual = r.valor(cid)
                atual = None if atual is ERRO or atual == "" else atual
                quem = next((m for m in membros if m[1] == cargo and not m[2]), None)
                if quem is None:
                    if atual is None or tipos.marcador(atual):
                        continue
                    anotar(r, k, form, cid, NENHUM, pessoa_hoje(atual), "—", f"o CSV não traz {papel}")
                    continue
                alvo, nome, nota = fichas.ref(quem[0], VINCULO_CAMPO, cargo, eq)
                if alvo is None or str(atual or "") == str(alvo):
                    continue
                anotar(r, k, form, cid, alvo, pessoa_hoje(atual), nome, nota)
        if form:
            mudancas.append({"usina_id": r.id, "id_bd": k, "nome": r.titulo, "versao": r.versao, "formulario": form})
    cab = list(cabecalho or (linhas[0].keys() if linhas else []))
    sem_campo = [c for c in cab if c and c != ID and c not in COLUNAS and c not in REFS and c != COL_PESSOAS]
    pessoas_mudam, desligadas = _proposta_pessoas(linhas, srv, usinas, equipes, fichas)
    # os valores que as fichas usam (vínculo, cargo, status) e a lista ainda não tem entram com os outros valores novos
    for m in pessoas_mudam:
        for cid, lista in (("vinculo", "vinculo"), ("cargo", "cargos"), ("status", "status_contratacao")):
            v = m["formulario"].get(cid)
            if not v:
                continue
            existente = next((x for x in listas.get(lista, []) if _chave_lista(x) == _chave_lista(v)), None)
            if existente is None:
                existente = novos_valores.setdefault(lista, {}).setdefault(_chave_lista(v), v)
            m["formulario"][cid] = existente
    return {"mudancas": mudancas, "sem_par": sem_par, "total": len(vistos),
            "por_campo": [pc for pc in por_campo.values() if pc["linhas"]],
            "vazios": dict(vazios.most_common()), "arredondados": dict(arredondados.most_common()),
            "ignorados": dict(ignorados), "ilegiveis": ilegiveis, "sem_cliente": dict(sem_cliente.most_common()),
            "sem_pessoa": dict(sem_pessoa.most_common()),
            "novos_valores": {lista: sorted(v.values()) for lista, v in novos_valores.items()},
            "equipes_novas": sorted(equipes_novas.values(), key=chave_texto), "sem_campo": sem_campo,
            "pessoas": pessoas_mudam, "pessoas_desligadas_sem_ficha": desligadas,
            "pessoas_ambiguas": dict(fichas.duas.most_common())}


def _proposta_pessoas(linhas, srv, usinas, equipes, fichas):
    """As fichas que nascem (toda pessoa da "Pessoas da equipe" e todo Responsável O&M sem ficha, menos o desligado) e
    o que se completa nas que existem: só o vazio (cargo, status, e-mail da conta do Fracttal) e a equipe quando o CSV dá
    uma só."""
    nome_eq = {r.id: r.valores.get("nome") for r in equipes.values()}
    membros, desligadas = {}, []
    for ln in linhas:
        k = _limpo(ln.get(ID)).upper()
        if k not in usinas or COL_PESSOAS not in ln:
            continue
        eq = _equipe_do_csv(ln, equipes)
        for nome, cargo, desligado in pessoas_da_celula(ln.get(COL_PESSOAS)):
            if desligado:
                pid = _achar_pessoa(nome, fichas.pessoas)
                if pid is None:
                    desligadas.append(nome)                  # desligado e sem ficha: não entra
                    continue
                ref = pid
            else:
                ref, _, _ = fichas.ref(nome, VINCULO_CAMPO, cargo, eq)
                if ref is None or ref.startswith(NOVA_PESSOA):
                    continue                                  # duas fichas, ou a nova (já leva cargo e equipe)
            m = membros.setdefault(ref, {"nome": nome, "equipes": set(), "cargos": set(), "desligado": False})
            if eq:
                m["equipes"].add(eq)
            if cargo:
                m["cargos"].add(cargo)
            m["desligado"] = m["desligado"] or desligado

    def titulo_eq(e):
        return e[5:] if str(e).startswith("nova:") else (nome_eq.get(e) or str(e or ""))

    mudam = []
    for pid, m in sorted(membros.items(), key=lambda kv: chave_texto(kv[1]["nome"])):
        r = srv.registro("pessoas", pid)
        if r is None:
            continue
        v, form, campos = r.valores, {}, []
        equipe = next(iter(m["equipes"])) if len(m["equipes"]) == 1 else None
        cargo = next(iter(m["cargos"])) if len(m["cargos"]) == 1 else None
        if equipe and str(v.get("equipe") or "") != str(equipe):
            form["equipe"] = equipe
            campos.append(("Equipe", f"{titulo_eq(v.get('equipe')) or '—'} → {titulo_eq(equipe)}"))
        if cargo and not v.get("cargo"):
            form["cargo"] = cargo
            campos.append(("Cargo", f"— → {cargo}"))
        if not v.get("status"):
            form["status"] = "Desligado" if m["desligado"] else "Ativo"
            campos.append(("Status", f"— → {form['status']}"))
        f = fichas.conta(m["nome"])
        email = str((f or {}).get("email") or "").strip().lower()
        if email and not v.get("email") and (email not in fichas.por_email or fichas.por_email[email].id == r.id):
            form["email"] = email
            campos.append(("E-mail", "— → o da conta do Fracttal"))
        if form:
            mudam.append({"acao": "completar", "pessoa_id": r.id, "chave": "", "nome": r.titulo, "versao": r.versao,
                          "formulario": form, "campos": campos})
    for n in sorted(fichas.novas.values(), key=lambda x: chave_texto(x["nome"])):
        f = n["formulario"]
        partes = [f.get("vinculo") if f.get("vinculo") != VINCULO_CAMPO else "", f.get("cargo") or "",
                  titulo_eq(f["equipe"]) if f.get("equipe") else "", "e-mail do Fracttal" if f.get("email") else ""]
        mudam.append({"acao": "criar", "pessoa_id": None, "chave": n["chave"], "nome": n["nome"], "versao": None,
                      "formulario": f, "campos": [("Ficha nova", " · ".join(x for x in partes if x))]})
    return mudam, desligadas


def _resolver(form, criadas, novas_pessoas):
    """Troca as referências ao que nasceu nesta aplicação (equipe "nova:", pessoa NOVA_PESSOA) pelo id; o que não nasceu
    (a coluna desmarcada) sai do formulário."""
    for cid in list(form):
        v = str(form[cid] or "")
        if v.startswith("nova:"):
            nova = criadas.get(chave_texto(v[5:]))
        elif v.startswith(NOVA_PESSOA):
            nova = novas_pessoas.get(v[len(NOVA_PESSOA):])
        else:
            continue
        if nova is None:
            form.pop(cid)
        else:
            form[cid] = nova
    return form


def aplicar(prop: dict, srv, quem: str, campos=None) -> dict:
    """Grava a proposta: os valores de lista novos, as equipes novas, as fichas de pessoas (as novas primeiro, que as
    usinas apontam para elas) e, usina a usina, os campos que mudam (a versão é a da leitura da prévia: quem salvou a
    ficha nesse meio tempo ganha, e ela é listada). `campos` = só estes campos (as colunas marcadas na prévia, e
    CAMPO_PESSOAS para as fichas); None = todos."""
    so = set(campos) if campos is not None else None
    usa = {}
    for c in ENTIDADES["usinas"].campos:
        if c.tipo == "lista":
            usa.setdefault(c.lista, set()).add(c.id)
    for lista in ("vinculo", "cargos", "status_contratacao"):
        usa.setdefault(lista, set()).add(CAMPO_PESSOAS)
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
    novas_pessoas, pessoas_criadas, pessoas_completadas = {}, 0, 0
    if so is None or CAMPO_PESSOAS in so:
        for m in sorted(prop.get("pessoas") or [], key=lambda x: x["acao"] != "criar"):
            form = _resolver(dict(m["formulario"]), criadas, novas_pessoas)
            if m["acao"] == "criar":
                res = srv.criar("pessoas", form, quem)
            else:
                res = srv.salvar("pessoas", m["pessoa_id"], form, m["versao"], quem)
            if res.ok:
                if m["acao"] == "criar":
                    pessoas_criadas += 1
                    novas_pessoas[m["chave"]] = res.registro.id
                else:
                    pessoas_completadas += 1
            elif res.conflito is not None:
                conflitos.append({"id_bd": "pessoa", "nome": m["nome"]})
            else:
                erros.append({"id_bd": "pessoa", "nome": m["nome"], "erro": "; ".join(
                    f"{k}: {v}" for k, v in (res.erros or {}).items())})
    for m in prop.get("mudancas") or []:
        form = _resolver({k: v for k, v in m["formulario"].items() if so is None or k in so}, criadas, novas_pessoas)
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
    srv.auditar(quem, "atualizou pelo CSV do BD_Operações", "usinas", str(prop.get("arquivo") or ""), [
        f"{atualizadas} usinas", f"{len(criadas)} equipes novas", f"{len(incluidos)} valores de lista novos",
        f"{pessoas_criadas} pessoas novas", f"{pessoas_completadas} pessoas completadas",
        f"{len(so) if so is not None else 'todas as'} colunas"])
    return {"atualizadas": atualizadas, "equipes_criadas": len(criadas), "valores_incluidos": incluidos,
            "pessoas_criadas": pessoas_criadas, "pessoas_completadas": pessoas_completadas,
            "conflitos": conflitos, "erros": erros}
