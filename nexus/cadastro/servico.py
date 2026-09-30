"""O serviço do cadastro: tudo o que as telas e a importação fazem passa por aqui.

Ordem das garantias, do formulário ao disco:
1. converte o texto para o tipo do campo (tipos.py) e confere lista, referência, obrigatório e único;
2. campo que a pessoa NÃO mexeu fica como estava, inclusive o valor herdado do Excel fora do tipo (Legado):
   salvar a ficha para trocar a cidade não pode "corrigir" nem apagar o "Pendente" da data de mobilização;
3. cifra o sensível (o registro inteiro, nas pessoas), sela a linha e grava exigindo a versão que a pessoa leu;
4. registra na auditoria QUEM mudou e QUAIS campos (os valores ficam no histórico, cifrados como a linha).

Na leitura, o selo que não confere marca o registro: a linha foi mexida fora do Nexus.
"""
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import tipos
from .armazem import Conflito
from .calculos import ERRO, Contexto
from .cifra import CifraErro
from .esquema import ENTIDADES, LISTAS, Entidade
from .tipos import Legado, ValorInvalido, cpf_valido

QUEM_IMPORTACAO = "importação"


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chave_texto(s) -> str:
    """Sem acento, sem maiúscula, sem espaço sobrando: "Sudeste" e " SUDESTE " são a mesma chave."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def _vazio(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


@dataclass
class Carga:
    """O que a importação (ou um teste) entrega para gravar de uma vez."""
    entidades: dict            # entidade -> [{"id", "ordem", "valores": {campo: valor tipado}}]
    listas: dict               # lista -> [valores, na ordem]
    origem: dict = field(default_factory=dict)


class Registro:
    def __init__(self, ent: Entidade, id_, ordem, valores, versao, alterado_em, alterado_por, selo_ok, excluido,
                 ilegivel=False):
        self.ent, self.id, self.ordem, self.valores = ent, id_, ordem, valores
        self.versao, self.alterado_em, self.alterado_por = versao, alterado_em, alterado_por
        self.selo_ok, self.excluido, self.ilegivel = selo_ok, excluido, ilegivel
        self.calc = {}

    @property
    def entidade(self) -> str:
        return self.ent.id

    @property
    def titulo(self) -> str:
        v = self.valor(self.ent.campo_titulo) if self.ent.tem(self.ent.campo_titulo) else None
        if self.ent.id == "pessoas":
            v = self.valor("nome_padrao") or self.valores.get("nome")
        if v is ERRO or _vazio(v):
            v = self.valores.get("nome")
        return str(v) if not _vazio(v) else self.id

    def valor(self, cid):
        c = self.ent.campo(cid)
        if c.modo in ("automatico", "calculado"):
            return self.calc.get(cid)
        return self.valores.get(cid)

    def origem(self, cid) -> str:
        c = self.ent.campo(cid)
        if c.modo == "calculado":
            return "calculado"
        v = self.valores.get(cid)
        if c.modo == "automatico":
            return "sobreposto" if not _vazio(v) else "automatico"
        return "legado" if isinstance(v, Legado) else "digitado"


@dataclass
class Resultado:
    ok: bool
    registro: Registro | None = None
    erros: dict = field(default_factory=dict)
    conflito: Registro | None = None
    formulario: dict | None = None
    mudou: list = field(default_factory=list)


class Servico:
    def __init__(self, armazem, cofre):
        self.armazem, self.cofre = armazem, cofre
        self._cache = None                  # (marca, {entidade: [Registro]}, listas)

    # ── leitura ────────────────────────────────────────────────────────────

    def _contexto_cifra(self, ent: Entidade, id_, campo) -> str:
        return f"{ent.id}/{id_}/{campo}"

    def _decifrar(self, ent: Entidade, linha: dict) -> Registro:
        selo_ok = self.cofre.selo_confere(linha)
        corpo, ilegivel = {}, False
        try:
            if ent.cifra_registro:
                corpo = json.loads(self.cofre.decifrar(linha.get("dados") or "", self._contexto_cifra(ent, linha["id"], "dados")))
            else:
                for c in ent.campos:
                    if c.modo == "calculado":
                        continue
                    v = linha.get(c.id)
                    if c.sensivel and self.cofre.eh_cifrado(v):
                        v = json.loads(self.cofre.decifrar(v, self._contexto_cifra(ent, linha["id"], c.id)))
                    corpo[c.id] = v
        except CifraErro:
            ilegivel, selo_ok = True, False
        valores = {c.id: tipos.de_api(c.tipo, corpo.get(c.id)) for c in ent.campos if c.modo != "calculado"}
        return Registro(ent, linha["id"], linha.get("_ordem") or 0, valores, linha.get("_versao") or 0,
                        linha.get("_alterado_em") or "", linha.get("_alterado_por") or "", selo_ok,
                        bool(linha.get("_excluido")), ilegivel)

    def _carregar(self):
        marca = self.armazem.marca()
        if self._cache and self._cache[0] == marca:
            return self._cache
        regs = {eid: [self._decifrar(ent, x) for x in self.armazem.ler(eid)] for eid, ent in ENTIDADES.items()}
        listas = defaultdict(list)
        for x in sorted(self.armazem.ler("listas"), key=lambda r: r.get("_ordem") or 0):
            listas[x["lista"]].append(x["valor"])
        # Referência que não aponta para ninguém (nome do Excel que não casou) é Legado: mostra, não esconde.
        ids = {eid: {r.id for r in rs} for eid, rs in regs.items()}
        for eid, rs in regs.items():
            for c in ENTIDADES[eid].campos:
                if c.tipo != "ref":
                    continue
                for r in rs:
                    v = r.valores.get(c.id)
                    if isinstance(v, str) and v and v not in ids.get(c.lista, set()) and not tipos.marcador(v):
                        r.valores[c.id] = Legado(v)
        ativos = {eid: [r for r in rs if not r.excluido] for eid, rs in regs.items()}
        ctx = Contexto(usinas=[self._simples(r) for r in ativos["usinas"]],
                       pessoas=[self._simples(r) for r in ativos["pessoas"]],
                       equipes=[self._simples(r) for r in ativos["equipes"]])
        for r in ativos["usinas"]:
            r.calc = ctx.calcular_usina(self._simples(r))
        for r in ativos["pessoas"]:
            r.calc = ctx.calcular_pessoa(self._simples(r))
        self._cache = (marca, regs, dict(listas))
        return self._cache

    @staticmethod
    def _simples(r: Registro) -> dict:
        return {"id": r.id, "ordem": r.ordem, "valores": r.valores}

    def registros(self, entidade: str, incluir_excluidos=False) -> list[Registro]:
        rs = self._carregar()[1].get(entidade, [])
        return sorted([r for r in rs if incluir_excluidos or not r.excluido], key=lambda r: r.ordem)

    def registro(self, entidade: str, id_: str) -> Registro | None:
        return next((r for r in self._carregar()[1].get(entidade, []) if r.id == id_), None)

    def listas(self) -> dict:
        return self._carregar()[2]

    def vazio(self) -> bool:
        return not any(self._carregar()[1].values())

    def titulo_de(self, entidade: str, ref) -> str:
        """Nome para mostrar de uma referência (id) ou o texto herdado que não casou."""
        if _vazio(ref):
            return ""
        if isinstance(ref, Legado):
            return ref.texto
        r = self.registro(entidade, ref)
        return r.titulo if r else str(ref)

    # ── formulário ─────────────────────────────────────────────────────────

    @staticmethod
    def _form_valor(c, v) -> str:
        if v is None:
            return ""
        if c.tipo in ("ref", "lista", "sugestao", "texto", "texto_longo") or isinstance(v, Legado):
            return v.texto if isinstance(v, Legado) else str(v)
        return tipos.para_formulario(c.tipo, v)

    def formulario(self, r: Registro, revelar: bool = False) -> dict:
        """Os campos editáveis como a tela os mostra. Sensível só entra revelado: campo que não veio no
        formulário fica como está (é o que impede a máscara de apagar o CPF ao salvar)."""
        out = {}
        for c in r.ent.campos:
            if not c.editavel or (c.oculto and not revelar):
                continue
            out[c.id] = self._form_valor(c, r.valores.get(c.id))
        return out

    def _converter(self, c, texto):
        if c.tipo == "lista":
            v = tipos.de_formulario("texto", texto)
            if v is not None and v not in self.listas().get(c.lista, []):
                raise ValorInvalido(f"“{v}” não está na lista {LISTAS.get(c.lista, c.lista)}. Inclua em Listas.")
            return v
        if c.tipo == "ref":
            v = tipos.de_formulario("texto", texto)
            if v is not None and tipos.marcador(v):
                return tipos.marcador(v)            # "N/A": a usina não tem (diferente de vazio = automático)
            if v is not None and not self.registro(c.lista, v):
                raise ValorInvalido("Não existe no cadastro.")
            return v
        if c.tipo == "sugestao":
            return tipos.de_formulario("texto", texto)
        return tipos.de_formulario(c.tipo, texto)

    def _aplicar_formulario(self, ent: Entidade, atuais: dict, formulario: dict, novo: bool, id_=None):
        novos, erros, mudou = dict(atuais), {}, []
        for c in ent.campos:
            if not c.editavel or c.id not in formulario:
                continue
            texto = formulario[c.id]
            atual = atuais.get(c.id)
            if not novo and str(texto if texto is not None else "") == self._form_valor(c, atual):
                continue                                   # não mexeu: fica como estava, inclusive o Legado
            try:
                v = self._converter(c, texto)
            except ValorInvalido as e:
                erros[c.id] = str(e)
                continue
            if v is None and c.obrigatorio:
                erros[c.id] = "Obrigatório."
                continue
            if c.unico and v is not None:
                dono = next((r for r in self.registros(ent.id)
                             if r.id != id_ and chave_texto(r.valores.get(c.id)) == chave_texto(v)), None)
                if dono:
                    erros[c.id] = f"Já existe em {dono.titulo} ({dono.id})."
                    continue
            if v != atual:
                novos[c.id] = v
                mudou.append(c.id)
        if novo:
            for c in ent.campos:
                if c.obrigatorio and c.editavel and _vazio(novos.get(c.id)) and c.id not in erros:
                    erros[c.id] = "Obrigatório."
        return novos, erros, mudou

    # ── escrita ────────────────────────────────────────────────────────────

    def _para_linha(self, ent: Entidade, id_, ordem, valores, versao, quem, excluido) -> dict:
        linha = {"id": id_, "_ordem": ordem}
        if ent.cifra_registro:
            corpo = {c.id: tipos.para_api(c.tipo, valores.get(c.id)) for c in ent.campos
                     if c.modo != "calculado" and valores.get(c.id) is not None}
            linha["dados"] = self.cofre.cifrar(json.dumps(corpo, ensure_ascii=False),
                                               self._contexto_cifra(ent, id_, "dados"))
        else:
            for c in ent.campos:
                if c.modo == "calculado":
                    continue
                v = tipos.para_api(c.tipo, valores.get(c.id))
                if v is not None and c.sensivel:
                    v = self.cofre.cifrar(json.dumps(v, ensure_ascii=False), self._contexto_cifra(ent, id_, c.id))
                linha[c.id] = v
        linha.update({"_excluido": bool(excluido), "_versao": versao, "_alterado_em": _agora(),
                      "_alterado_por": quem})
        linha["_selo"] = self.cofre.selar(linha)
        return linha

    def salvar(self, entidade: str, id_: str, formulario: dict, versao: int, quem: str) -> Resultado:
        ent = ENTIDADES[entidade]
        atual = self.registro(entidade, id_)
        if atual is None:
            return Resultado(False, erros={"_": "Registro não existe."})
        novos, erros, mudou = self._aplicar_formulario(ent, atual.valores, formulario, novo=False, id_=id_)
        if erros:
            return Resultado(False, registro=atual, erros=erros, formulario=formulario)
        if not mudou:
            return Resultado(True, registro=atual)
        linha = self._para_linha(ent, id_, atual.ordem, novos, int(versao) + 1, quem, excluido=atual.excluido)
        try:
            self.armazem.gravar(entidade, linha, versao_esperada=int(versao))
        except Conflito:
            self._cache = None
            return Resultado(False, conflito=self.registro(entidade, id_), formulario=formulario,
                             erros={"_": "Outra pessoa salvou esta ficha depois que você a abriu."})
        self.armazem.auditar({"quem": quem, "acao": "alterou", "entidade": entidade, "id": id_, "campos": mudou})
        self._cache = None
        return Resultado(True, registro=self.registro(entidade, id_), mudou=mudou)

    def _proximo_id(self, ent: Entidade) -> str:
        """Número simples, por cadastro: 1, 2, 3 (Levi, 29/09: "reduza as caracteres do ID"). Id no formato antigo
        (E-001, do primeiro ensaio) não entra na conta."""
        nums = [int(r.id) for r in self.registros(ent.id, incluir_excluidos=True) if str(r.id).isdigit()]
        return str(max(nums, default=0) + 1)

    def criar(self, entidade: str, formulario: dict, quem: str) -> Resultado:
        ent = ENTIDADES[entidade]
        novos, erros, _ = self._aplicar_formulario(ent, {}, formulario, novo=True)
        if erros:
            return Resultado(False, erros=erros, formulario=formulario)
        id_ = self._proximo_id(ent)
        ordem = max((r.ordem for r in self.registros(entidade, incluir_excluidos=True)), default=0) + 1
        self.armazem.inserir(entidade, self._para_linha(ent, id_, ordem, novos, 1, quem, excluido=False))
        self.armazem.auditar({"quem": quem, "acao": "criou", "entidade": entidade, "id": id_,
                              "campos": sorted(k for k, v in novos.items() if not _vazio(v))})
        self._cache = None
        return Resultado(True, registro=self.registro(entidade, id_))

    def _linha_lista(self, id_, lista, valor, ordem, versao, quem) -> dict:
        linha = {"id": id_, "lista": lista, "valor": valor, "_ordem": ordem, "_versao": versao,
                 "_alterado_em": _agora(), "_alterado_por": quem}
        linha["_selo"] = self.cofre.selar(linha)
        return linha

    def adicionar_valor(self, lista: str, valor: str, quem: str) -> Resultado:
        v = (valor or "").strip()
        if not v:
            return Resultado(False, erros={"valor": "Obrigatório."})
        if lista not in LISTAS:
            return Resultado(False, erros={"lista": "Lista desconhecida."})
        if any(chave_texto(x) == chave_texto(v) for x in self.listas().get(lista, [])):
            return Resultado(False, erros={"valor": "Já existe na lista (sem contar acento e maiúscula)."})
        atuais = self.armazem.ler("listas")
        n = max((int(re.sub(r"\D", "", x["id"]) or 0) for x in atuais), default=0) + 1
        ordem = max((x.get("_ordem") or 0 for x in atuais), default=0) + 1
        self.armazem.inserir("listas", self._linha_lista(f"L-{n:04d}", lista, v, ordem, 1, quem))
        self.armazem.auditar({"quem": quem, "acao": "incluiu na lista", "entidade": "listas", "id": lista,
                              "campos": [v]})
        self._cache = None
        return Resultado(True)

    def auditar(self, quem: str, acao: str, entidade: str, id_: str, campos=()):
        self.armazem.auditar({"quem": quem, "acao": acao, "entidade": entidade, "id": id_, "campos": list(campos)})

    # ── importação ─────────────────────────────────────────────────────────

    def aplicar_carga(self, carga: Carga, quem: str = QUEM_IMPORTACAO):
        """Grava a carga inteira de uma vez (com cópia do arquivo antes). Registro que não mudou fica
        intocado (sem versão nova: importar de novo no ensaio não enche o histórico); o que sumiu da planilha
        é marcado como excluído, nunca apagado."""
        novas = {}
        for eid, regs in carga.entidades.items():
            ent = ENTIDADES[eid]
            atuais = {x["id"]: x for x in self.armazem.ler(eid)}
            linhas, vindos = [], set()
            for r in regs:
                vindos.add(r["id"])
                velha = atuais.get(r["id"])
                valores = {c.id: r["valores"].get(c.id) for c in ent.campos if c.modo != "calculado"}
                if velha is not None:
                    antes = self._decifrar(ent, velha)
                    if antes.valores == valores and antes.ordem == r["ordem"] and not antes.excluido and antes.selo_ok:
                        linhas.append(velha)
                        continue
                versao = (velha.get("_versao") or 0) + 1 if velha else 1
                linhas.append(self._para_linha(ent, r["id"], r["ordem"], valores, versao, quem, excluido=False))
            for id_, velha in atuais.items():
                if id_ in vindos:
                    continue
                if velha.get("_excluido"):
                    linhas.append(velha)
                    continue
                antes = self._decifrar(ent, velha)
                linhas.append(self._para_linha(ent, id_, antes.ordem, antes.valores, (velha.get("_versao") or 0) + 1,
                                               quem, excluido=True))
            novas[eid] = linhas
        if carga.listas is not None:
            atuais = {(x["lista"], x["valor"]): x for x in self.armazem.ler("listas")}
            linhas, n = [], 0
            for lista, valores in carga.listas.items():
                for v in valores:
                    n += 1
                    velha = atuais.get((lista, v))
                    if velha and velha.get("_ordem") == n and self.cofre.selo_confere(velha):
                        linhas.append(velha)
                    else:
                        linhas.append(self._linha_lista(f"L-{n:04d}", lista, v, n, 1, quem))
            novas["listas"] = linhas
        copia = self.armazem.substituir(novas, dict(carga.origem, quem=quem))
        self._cache = None
        return copia

    # ── histórico e qualidade ──────────────────────────────────────────────

    def historico(self, entidade: str, id_: str) -> list[dict]:
        ent = ENTIDADES[entidade]
        atual = next((x for x in self.armazem.ler(entidade) if x["id"] == id_), None)
        if atual is None:
            return []
        versoes = [atual] + self.armazem.historico(entidade, id_)
        regs = [self._decifrar(ent, v) for v in versoes]
        out = []
        for i, r in enumerate(regs):
            anterior = regs[i + 1] if i + 1 < len(regs) else None
            if anterior is None:
                campos = []
            else:
                campos = [c.id for c in ent.campos if c.modo != "calculado"
                          and r.valores.get(c.id) != anterior.valores.get(c.id)]
                if r.excluido != anterior.excluido:
                    campos.append("excluído" if r.excluido else "restaurado")
            out.append({"versao": r.versao, "quando": r.alterado_em, "quem": r.alterado_por, "campos": campos,
                        "selo_ok": r.selo_ok})
        return out

    def tentativa(self, entidade: str, id_: str, versao_lida: int, formulario: dict) -> list[dict]:
        """No conflito: o que a pessoa mudou em relação à versão que ELA abriu (não à atual). Reenviar o
        formulário inteiro desfaria o que a outra pessoa gravou nos campos que esta nem tocou."""
        ent = ENTIDADES[entidade]
        versoes = self.armazem.ler(entidade) + self.armazem.historico(entidade, id_)
        lida = next((v for v in versoes if v["id"] == id_ and v.get("_versao") == int(versao_lida)), None)
        if lida is None:
            return []
        antes = self._decifrar(ent, lida).valores
        out = []
        for c in ent.campos:
            if c.editavel and c.id in formulario and str(formulario[c.id]) != self._form_valor(c, antes.get(c.id)):
                out.append({"campo": c.id, "rotulo": c.rotulo, "valor": formulario[c.id]})
        return out

    def auditoria(self, limite: int = 100) -> list[dict]:
        return self.armazem.auditoria(limite)

    def importacoes(self) -> list[dict]:
        return self.armazem.importacoes()

    def pendencias(self) -> list[dict]:
        """O que o Excel escondia ou deixava passar calado. Cada item leva para a ficha certa."""
        out = []

        def add(tipo, grav, entidade, id_, titulo, detalhe=""):
            out.append({"tipo": tipo, "gravidade": grav, "entidade": entidade, "id": id_, "titulo": titulo,
                        "detalhe": detalhe})

        listas = self.listas()
        usinas, pessoas = self.registros("usinas"), self.registros("pessoas")
        equipes = self.registros("equipes")
        for eid in ENTIDADES:
            for r in self.registros(eid):
                if not r.selo_ok:
                    add("selo", "critico", eid, r.id, r.titulo,
                        "A linha foi alterada fora do Nexus (o selo não confere). Revise antes de usar.")
                leg = [r.ent.campo(k).rotulo for k, v in r.valores.items() if isinstance(v, Legado)]
                if leg:
                    add("legado", "alerta", eid, r.id, r.titulo,
                        "Valor herdado do Excel fora do tipo em: " + ", ".join(leg) + ".")
                for c in r.ent.campos:
                    v = r.valores.get(c.id)
                    if c.tipo == "lista" and isinstance(v, str) and v and v not in listas.get(c.lista, []):
                        add("fora_da_lista", "alerta", eid, r.id, r.titulo, f"{c.rotulo}: “{v}” não está na lista.")
        # pessoas
        emails = Counter(chave_texto(p.valores.get("email")) for p in pessoas if not _vazio(p.valores.get("email")))
        for p in pessoas:
            v = p.valores
            ativo = chave_texto(v.get("status")) != "desligado"
            if ativo and _vazio(v.get("email")):
                add("sem_email", "alerta", "pessoas", p.id, p.titulo, "Pessoa ativa sem e-mail.")
            cpf = v.get("cpf")
            if isinstance(cpf, str) and cpf and not cpf_valido(cpf):
                add("cpf_invalido", "alerta", "pessoas", p.id, p.titulo, "CPF com dígito verificador errado.")
            if not _vazio(v.get("email")) and emails[chave_texto(v.get("email"))] > 1:
                add("email_repetido", "critico", "pessoas", p.id, p.titulo, "O mesmo e-mail está em outra pessoa.")
            for campo in ("nome_padrao", "cidade_uf_endereco", "cidade_estado_base"):
                if p.calc.get(campo) is ERRO:
                    add("calculo_erro", "info", "pessoas", p.id, p.titulo,
                        f"{p.ent.campo(campo).rotulo}: não dá para calcular (o Excel mostrava #N/A).")
        # equipes
        por_equipe = defaultdict(list)
        for p in pessoas:
            if chave_texto(p.valores.get("status")) != "desligado" and isinstance(p.valores.get("equipe"), str):
                por_equipe[p.valores["equipe"]].append(p)
        usinas_da = defaultdict(list)
        for u in usinas:
            if isinstance(u.valores.get("equipe"), str) and u.valores.get("equipe"):
                usinas_da[u.valores["equipe"]].append(u)
        for e in equipes:
            cargos = Counter(p.valores.get("cargo") for p in por_equipe.get(e.id, []) if p.valores.get("cargo"))
            for cargo, n in cargos.items():
                if n > 1:
                    add("equipe_cargo_duplicado", "alerta", "equipes", e.id, e.titulo,
                        f"{n} pessoas ativas com o cargo {cargo}: o Excel escolhia a primeira da planilha, calado.")
            resp = {self.titulo_de("pessoas", u.valores.get("responsavel_om")) for u in usinas_da.get(e.id, [])
                    if not _vazio(u.valores.get("responsavel_om"))}
            if len(resp) > 1:
                add("equipe_responsaveis", "alerta", "equipes", e.id, e.titulo,
                    "Usinas da equipe com responsáveis diferentes: " + ", ".join(sorted(resp)) + ".")
            if e.id not in usinas_da and por_equipe.get(e.id):
                add("equipe_sem_usina", "info", "equipes", e.id, e.titulo, "Tem pessoas e nenhuma usina.")
        # usinas
        # Repetido é o mesmo nome no MESMO cliente. Mesmo nome com clientes diferentes é normal (2 pares no BD de
        # 29/09) e é o ID + cliente que separa (Levi: "conseguimos diferenciar usinas com mesmo nome").
        nomes = Counter((chave_texto(u.valores.get("nome")), str(u.valores.get("cliente") or "")) for u in usinas)
        for u in usinas:
            v = u.valores
            if _vazio(v.get("equipe")) and chave_texto(v.get("status")) in ("operacao", "a mobilizar"):
                add("usina_sem_equipe", "alerta", "usinas", u.id, u.titulo, "Usina sem equipe.")
            if nomes[(chave_texto(v.get("nome")), str(v.get("cliente") or ""))] > 1:
                add("nome_repetido", "alerta", "usinas", u.id, u.titulo,
                    "Outra usina do mesmo cliente tem o mesmo nome.")
            for c in ("responsavel_om", "gestor_contrato", "tecnico_om", "eletricista_om", "mantenedor_om"):
                if isinstance(v.get(c), Legado):
                    add("nome_sem_cadastro", "alerta", "usinas", u.id, u.titulo,
                        f"{u.ent.campo(c).rotulo}: “{v[c].texto}” não casou com nenhuma pessoa do cadastro.")
        # listas com valores quase iguais
        for lista, valores in listas.items():
            grupos = defaultdict(list)
            for x in valores:
                grupos[chave_texto(x)].append(x)
            parecidos = [g for g in grupos.values() if len(g) > 1]
            if parecidos:
                add("lista_parecida", "info", "listas", lista, LISTAS.get(lista, lista),
                    "Valores que só diferem em acento, maiúscula ou espaço: "
                    + "; ".join(" × ".join(g) for g in parecidos) + ".")
        return out
