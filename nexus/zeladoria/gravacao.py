"""A gravação da Zeladoria pelo Nexus (etapa 4 do desenho, 03/11/2026).

Levi, 03/11/2026, entre esperar o banco a cada clique (gravar e conferir o livro do app leva ~8 s, medido) e "Salvo em
1 s, banco logo depois": o segundo. Como funciona:
- **Na hora:** a mudança que o app manda (`aplicar`) entra no estado do servidor e num DIÁRIO no disco, cifrado linha a
  linha com a chave do cadastro, porque tem nome, e-mail e valor. O "Salvo" do app acende quando o diário gravou.
- **Em lote:** o Nexus grava no banco os livros que mudaram (`persistir`), conferindo antes e depois como todo livro
  (`livros.publicar`), e só então esvazia o diário até aquela versão. Ao subir, o diário é relido por cima do banco
  (`carregar`): o servidor reiniciar (todo push na main reinicia) não perde mudança. Banco fora do ar: a mudança fica no
  diário, a situação diz o erro, e a próxima volta tenta de novo.
- **Uma máquina grava:** só onde `NEXUS_ZELADORIA_GRAVA=1` (o servidor, depois da troca). Dois Nexus com estados
  diferentes apagariam um ao outro.
- **Conflito simples** (desenho, corte de prazo de 03/11): o app manda só as linhas que mudaram (a ponte compara com o que
  leu). A mudança de outra pessoa numa linha que você não mexeu fica. Na linha que os dois mexeram, vale a última, e a
  resposta diz quais foram (`sobrepostas`).
- **Exclusão definitiva deixa rastro:** a linha sai, e o registro (`log`) ganha quem tirou, o quê e quando.
- **Quem grava:** só quem está aprovado no `perfis` do Radar, como no RLS do Supabase; o `perfis` (a tela Usuários) e as
  funções do financeiro, só o HEAD.

O diário guarda os EFEITOS já resolvidos (a linha inteira que ficou, a chave que saiu), não o pedido. Por isso
reaplicá-lo dá o mesmo estado, inclusive o id que o servidor deu.
"""
import copy
import json
import logging
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from ..dados import livros
from . import guardar
from . import tabelas as T

log = logging.getLogger(__name__)

_BRT = timezone(timedelta(hours=-3))
CTX_DIARIO = "zeladoria/diario"
_INTEIROS = ("integer", "bigint", "smallint")
# as tabelas sem rastro de exclusão nem aviso de "mexeram no mesmo registro": o próprio registro (só cresce) e o
# histórico de valor, que o app regrava inteiro a cada salvamento (é derivado das cotações)
SEM_RASTRO = {"log", "historico_valor"}
# o ON DELETE do banco do Radar: o clone conta com ele (excluir o fornecedor tira as cotações só do estado dele e põe na
# fila só o fornecedor; revisão de 03/11/2026). "apagar" = cascade; "nulo" = set null. Os documentos ficam dentro do
# fornecedor e do colaborador no app: órfão não aparece em tela nenhuma, então saem junto
CASCATA = {
    "fornecedores": (("cotacoes", "fornecedor_id", "apagar"), ("documentos", "fornecedor_id", "apagar"),
                     ("fin_fornecedor_alias", "fornecedor_id", "apagar"), ("fin_cenario_item", "fornecedor_id", "nulo"),
                     ("fin_provisao", "fornecedor_id", "nulo")),
    "colaboradores": (("documentos", "colaborador_id", "apagar"),),
    "periodos": (("cotacoes", "periodo_id", "nulo"),),
    "fin_cenario": (("fin_cenario_item", "cenario_id", "apagar"),),
}
# o histórico só recebe linha nova, como no banco do Radar; a exceção é o motivo da alteração do cronograma, que o app
# preenche depois de gravar a alteração. O das provisões só pela função do financeiro (lá o insert era revogado)
HISTORICO_MUDA = {"cronograma_alteracoes": {"motivo"}}
SO_PELA_FUNCAO = {"fin_provisao_historico"}


class Recusa(ValueError):
    """Pedido que a regra não deixa (sem aprovação, sem papel, dado inválido). A mensagem volta ao app como erro."""


def ativo(config) -> bool:
    return str(config.get("NEXUS_ZELADORIA_GRAVA") or os.environ.get("NEXUS_ZELADORIA_GRAVA") or "").strip() == "1"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _txt(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return "" if v is None else str(v)


def _igual(a, b) -> bool:
    return a == b or (a is not None and b is not None and _txt(a) == _txt(b))


class Gravador:
    def __init__(self, *, base: str, token: str, sessao, cofre, diario: Path):
        self.base, self.token, self.sessao, self.cofre = base, token, sessao, cofre
        self.diario = Path(diario)
        self._trava = threading.RLock()
        self._trava_banco = threading.Lock()
        self.estado = None
        # (aba, chave) -> (versão, quem) da última mudança; e quem salvou cada versão. A versão base do app é a da
        # página aberta: a mudança de OUTRA pessoa depois dela é o aviso; a sua própria não
        self._mudou = {}
        self._autor = {}
        self._sujo = {}             # livro -> versão da última mudança ainda não gravada
        self._maior = {}            # aba -> o maior id inteiro já visto ou dado neste processo
        self.versao_banco = 0
        self.erro = None
        self.ultima_mudanca = 0.0

    # ── carregar e reaplicar ─────────────────────────────────────────────────────────────────────────────────────
    def carregar(self, est: dict) -> None:
        with self._trava:
            self.estado = copy.deepcopy(est)
            self.versao_banco = int(est.get("versao") or 0)
            for aba, linhas in self.estado["abas"].items():
                ch = self._chave(aba)
                nums = [int(float(l[ch])) for l in linhas if _txt(l.get(ch)).lstrip("-").isdigit()]
                if nums:
                    self._maior[aba] = max(nums)
            # livro a livro: se o banco gravou o livro do app e caiu antes do histórico, o diário do histórico se
            # reaplica, mesmo com o livro do app já na versão nova (o efeito é a linha inteira: reaplicar não muda nada)
            versoes = est.get("versoes") or {}
            for registro in self._ler_diario():
                v = registro["versao"]
                efeitos = [e for e in registro["efeitos"] if versoes.get(T.TABELAS[e[1]], 0) < v]
                if efeitos:
                    self._efetivar(efeitos, v, registro.get("quem"))
                self._autor[v] = registro.get("quem")
                self.estado["versao"] = max(self.estado["versao"], v)

    def _ler_diario(self) -> list:
        if not self.diario.exists():
            return []
        out = []
        linhas = [l.strip() for l in self.diario.read_text(encoding="utf-8").splitlines() if l.strip()]
        for n, linha in enumerate(linhas):
            try:
                out.append(json.loads(self.cofre.decifrar(linha, CTX_DIARIO)))
            except Exception:  # noqa: BLE001
                # a última linha pela metade é um acréscimo que não terminou (queda no meio): o app não recebeu o
                # "Salvo" dela. Linha ruim no meio é outra coisa, e não se adivinha: a torre não sobe
                if n == len(linhas) - 1:
                    log.warning("zeladoria: a última linha do diário está incompleta e foi ignorada")
                    continue
                raise
        return sorted(out, key=lambda r: r["versao"])

    def _escrever_diario(self, registros: list, acrescentar: bool) -> None:
        self.diario.parent.mkdir(parents=True, exist_ok=True)
        texto = "".join(self.cofre.cifrar(json.dumps(r, ensure_ascii=False, default=str), CTX_DIARIO) + "\n"
                        for r in registros)
        if acrescentar:
            with open(self.diario, "a", encoding="utf-8") as f:
                antes = f.tell()
                try:
                    f.write(texto)
                    f.flush()
                    os.fsync(f.fileno())
                except OSError:
                    # disco cheio no meio: tira o pedaço, senão o próximo acréscimo cola nele e fica ilegível
                    try:
                        f.truncate(antes)
                    except OSError:
                        pass
                    raise
        else:
            tmp = self.diario.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(texto)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.diario)
            if hasattr(os, "O_DIRECTORY"):           # no Linux, a troca do nome só fica no disco com o fsync da pasta
                d = os.open(self.diario.parent, os.O_DIRECTORY)
                try:
                    os.fsync(d)
                finally:
                    os.close(d)

    # ── aplicar ──────────────────────────────────────────────────────────────────────────────────────────────────
    def _chave(self, aba: str) -> str:
        return self.estado["chaves"].get(aba) or "id"

    def _linhas(self, aba: str) -> list:
        if aba not in self.estado["abas"]:
            raise Recusa(f"a tabela {aba} não está na cópia")
        return self.estado["abas"][aba]

    def _proximo_id(self, aba: str, linhas, ja: set) -> int:
        """O maior + 1, olhando as linhas do salvamento em curso e o maior que este processo já deu (a sequência do
        Postgres nunca reaproveita o número da linha excluída)."""
        chave = self._chave(aba)
        nums = [int(float(l[chave])) for l in linhas if _txt(l.get(chave)).lstrip("-").isdigit()]
        n = max(nums + list(ja) + [self._maior.get(aba, 0), 0]) + 1
        ja.add(n)
        return n

    def _validar(self, aba: str, linha: dict) -> dict:
        """A coluna tem de existir e o valor tem de caber no tipo, como no Postgres. Sem isto, a coluna nova sumia calada
        no lote, e o texto numa coluna de número derrubava a leitura no boot seguinte (revisão de 03/11/2026)."""
        tipos = self.estado["tipos"].get(aba, {})
        nova = {}
        for c, v in linha.items():
            if c not in tipos:
                raise Recusa(f"{aba}: a coluna {c} não existe")
            t = (tipos[c] or "").lower()
            if v is None or v == "":
                nova[c] = None if t in _INTEIROS or t in guardar._DECIMAIS or t == "boolean" else v
                continue
            try:
                if t in _INTEIROS:
                    d = Decimal(str(v))
                    if d != d.to_integral_value():
                        raise ValueError
                    v = int(d)
                elif t in guardar._DECIMAIS:
                    v = float(v) if not isinstance(v, bool) else float("nan")
                    if not math.isfinite(v):
                        raise ValueError
                elif t == "boolean" and not isinstance(v, bool):
                    v = {"true": True, "false": False}[str(v).strip().lower()]
            except (ValueError, ArithmeticError, KeyError):
                raise Recusa(f"{aba}: o valor de {c} não é {tipos[c]}") from None
            nova[c] = v
        return nova

    def _com_padroes(self, aba: str, linha: dict) -> dict:
        tipos = self.estado["tipos"].get(aba, {})
        nova = dict(linha)
        if "criado_em" in tipos and not nova.get("criado_em"):
            nova["criado_em"] = _agora_iso()
        if aba == "log" and "em" in tipos and not nova.get("em"):
            nova["em"] = datetime.now(_BRT).date().isoformat()
        if "excluido" in tipos and nova.get("excluido") is None:
            nova["excluido"] = False
        return nova

    def _efeitos(self, ops: list, quem: dict, interno: bool = False) -> list:
        """Resolve os pedidos em efeitos: ("por", aba, chave, linha inteira) ou ("tirar", aba, chave, None), e os ids
        que o servidor deu, por pedido (a ponte guarda o id da linha nova para a próxima comparação). `interno` = o
        pedido vem de uma função do financeiro, não do app."""
        if quem.get("status") != "aprovado":
            raise Recusa("só quem está aprovado no Radar grava (fale com o HEAD da zeladoria)")
        efeitos, ids_novos, sombra, gerados = [], {}, {}, []

        def atual(aba):
            if aba not in sombra:
                sombra[aba] = {_txt(l.get(self._chave(aba))): l for l in self._linhas(aba)}
            return sombra[aba]

        def novo_id(aba):
            return self._proximo_id(aba, atual(aba).values(), ids_novos.setdefault(aba, set()))

        def por(aba, linha):
            k = _txt(linha.get(self._chave(aba)))
            atual(aba)[k] = linha
            efeitos.append(["por", aba, k, linha])

        def tirar(aba, k, cascata=False):
            linha = atual(aba).pop(k, None)
            efeitos.append(["tirar", aba, k, None])
            if linha is None:
                return
            levou = {}
            for filha, col, como in CASCATA.get(aba, ()):
                if filha not in self.estado["abas"]:
                    continue
                for f in [x for x in atual(filha).values() if _igual(x.get(col), linha.get(self._chave(aba)))]:
                    if como == "apagar":
                        tirar(filha, _txt(f.get(self._chave(filha))), cascata=True)
                    else:
                        por(filha, {**f, col: None})
                    levou[filha] = levou.get(filha, 0) + 1
            if aba not in SEM_RASTRO and not cascata:
                rastro = {"quem": quem.get("email"), "acao": "excluir-definitivo", "alvo": f"{aba}:{k}"}
                if levou and "obs" in self.estado["tipos"].get("log", {}):
                    rastro["obs"] = "em cascata: " + ", ".join(f"{a} {n}" for a, n in sorted(levou.items()))
                rastro = self._com_padroes("log", rastro)
                rastro[self._chave("log")] = novo_id("log")
                por("log", rastro)

        for op in ops:
            gerados.append([])
            try:
                aba = T.aba_da_view(op.get("view"))
            except T.TabelaDesconhecida as e:
                raise Recusa(str(e)) from None
            self._linhas(aba)
            if aba == "perfis" and quem.get("papel") != "HEAD":
                raise Recusa("só o HEAD mexe nos usuários do Radar")
            if aba in SO_PELA_FUNCAO and not interno:
                raise Recusa(f"{aba} só muda pelas funções do financeiro")
            chave = self._chave(aba)
            tipo_chave = self.estado["tipos"].get(aba, {}).get(chave, "text")
            nome = op.get("op")
            historico = aba in T.HISTORICO and not interno
            if nome in ("upsert", "insert"):
                for linha in op.get("linhas") or []:
                    if not isinstance(linha, dict):
                        raise Recusa(f"{aba}: linha inválida")
                    linha = self._validar(aba, linha)
                    k = _txt(linha.get(chave))
                    if not k:
                        if tipo_chave not in _INTEIROS:
                            raise Recusa(f"{aba}: linha nova sem {chave}")
                        linha[chave] = novo_id(aba)
                        gerados[-1].append(linha[chave])
                        k = _txt(linha[chave])
                    existente = atual(aba).get(k)
                    if existente is not None and (nome == "insert" or historico):
                        raise Recusa(f"{aba}: o {chave} {k} já existe (outra pessoa criou ao mesmo tempo); "
                                     "recarregue a página")
                    por(aba, {**existente, **linha} if existente else self._com_padroes(aba, linha))
            elif nome == "update":
                patch = self._validar(aba, op.get("patch") or {})
                if historico and not set(patch) <= HISTORICO_MUDA.get(aba, set()):
                    raise Recusa(f"{aba} é histórico: só recebe linha nova")
                for l in list(self._filtrar_sombra(atual(aba), op.get("filtros"))):
                    por(aba, {**l, **patch})
            elif nome == "delete":
                # o livro do histórico só cresce (a trava do catálogo): a exclusão nele faria o lote ser recusado no
                # banco para sempre, e o diário cresceria sem gravar
                if aba in T.HISTORICO:
                    raise Recusa(f"{aba} é histórico: só cresce, nada se exclui")
                for l in list(self._filtrar_sombra(atual(aba), op.get("filtros"))):
                    tirar(aba, _txt(l.get(self._chave(aba))))
            else:
                raise Recusa(f"pedido {nome!r} não existe na zeladoria")
        return efeitos, gerados

    @staticmethod
    def _filtrar_sombra(por_chave: dict, filtros: list) -> list:
        linhas = list(por_chave.values())
        for op, col, val in filtros or []:
            if op not in ("eq", "neq"):
                raise Recusa(f"filtro {op} não existe na zeladoria")
            linhas = [l for l in linhas if _igual(l.get(col), val) == (op == "eq")]
        return linhas

    def _efetivar(self, efeitos: list, versao: int, quem) -> None:
        """Copia a lista de cada tabela tocada e troca no fim: quem está lendo a lista antiga (o GET, o lote) não a vê
        mudar no meio (revisão de 03/11/2026)."""
        self._autor[versao] = quem
        novas = {}
        for tipo, aba, k, linha in efeitos:
            chave = self._chave(aba)
            linhas = novas.setdefault(aba, list(self.estado["abas"][aba]))
            i = next((n for n, l in enumerate(linhas) if _txt(l.get(chave)) == k), None)
            if tipo == "por":
                if i is None:
                    linhas.append(linha)
                else:
                    linhas[i] = linha
                if k.lstrip("-").isdigit():
                    self._maior[aba] = max(self._maior.get(aba, 0), int(k))
            elif i is not None:
                linhas.pop(i)
            self._mudou[(aba, k)] = (versao, quem)
            self._sujo[T.TABELAS[aba]] = versao
        self.estado["abas"].update(novas)

    def aplicar(self, ops: list, quem: dict, base_versao: int, interno: bool = False) -> dict:
        """Aplica os pedidos de um salvamento, todos ou nenhum. {"versao", "outros_salvaram", "sobrepostas", "ids"}."""
        with self._trava:
            efeitos, gerados = self._efeitos(ops, quem, interno)
            base, eu = int(base_versao or 0), quem.get("email")

            def de_outro(v, q):
                return v > base and q != eu

            sobrepostas = sorted({f"{aba}:{k}" for _t, aba, k, _l in efeitos
                                  if aba not in SEM_RASTRO and de_outro(*self._mudou.get((aba, k), (0, eu)))})
            outros = any(de_outro(v, q) for v, q in self._autor.items())
            if not efeitos:
                return {"versao": self.estado["versao"], "outros_salvaram": outros, "sobrepostas": [], "ids": gerados}
            versao = self.estado["versao"] + 1
            self._escrever_diario([{"versao": versao, "efeitos": efeitos, "quem": quem.get("email"),
                                    "em": _agora_iso()}], acrescentar=True)
            self._efetivar(efeitos, versao, eu)
            self.estado["versao"] = versao
            self.ultima_mudanca = time.time()
            return {"versao": versao, "outros_salvaram": outros, "sobrepostas": sobrepostas, "ids": gerados}

    def chamar(self, nome: str, args: dict, quem: dict, base_versao: int) -> dict:
        """Uma função do financeiro (`financeiro.FUNCOES`): confere e aplica num salvamento só, tudo ou nada.
        {"versao", "outros_salvaram", "sobrepostas", "dados"}; "dados" é o que a função do banco do Radar devolvia."""
        from . import financeiro
        if nome not in financeiro.FUNCOES:
            raise Recusa(f"a função {nome} não existe na zeladoria")
        with self._trava:
            try:
                ops, dados = financeiro.FUNCOES[nome](self.estado, quem, args or {})
            except financeiro.FinErro as e:
                raise Recusa(str(e)) from None
            except (ValueError, TypeError, AttributeError) as e:
                raise Recusa(f"{nome}: dado inválido ({type(e).__name__})") from None
            return {**self.aplicar(ops, quem, base_versao, interno=True), "dados": dados}

    def garantir_perfil(self, quem: dict) -> None:
        """A pessoa nova que entra na torre ganha a linha "pendente" no `perfis`, para o HEAD aprovar em Usuários (no
        Supabase era uma regra do banco que criava)."""
        with self._trava:
            if any(_igual(p.get("user_id"), quem.get("id")) for p in self.estado["abas"].get("perfis", [])):
                return
            tipos = self.estado["tipos"].get("perfis", {})
            linha = {c: v for c, v in {"user_id": quem.get("id"), "email": quem.get("email"), "papel": None,
                                       "status": "pendente", "solicitado_em": _agora_iso()}.items() if c in tipos}
            sistema = {"status": "aprovado", "papel": "HEAD", "email": "nexus"}
            self.aplicar([{"op": "insert", "view": "rf_perfis", "linhas": [linha]}], sistema, self.estado["versao"])

    # ── gravar no banco ──────────────────────────────────────────────────────────────────────────────────────────
    def _montar(self, livro: str, versao: int, est: dict) -> dict:
        tabelas, atualizacao = {}, []
        for aba in (a for a, lv in T.TABELAS.items() if lv == livro):
            colunas = list(est["tipos"][aba].items())
            linhas = est["abas"][aba]
            tabelas[aba] = guardar.para_aba(aba, colunas, linhas, self.cofre, est["chaves"][aba])
            atualizacao += [[aba, c, t, est["chaves"][aba], len(linhas), est.get("copiado_em"), est.get("exportado_em"),
                             versao] for c, t in colunas]
        from .copia import CAB_ATUALIZACAO
        tabelas["atualizacao"] = (list(CAB_ATUALIZACAO), atualizacao)
        return tabelas

    def persistir(self) -> dict:
        """Grava no banco os livros que mudaram, confere, e esvazia o diário até a versão gravada."""
        with self._trava_banco:
            with self._trava:
                versao = self.estado["versao"]
                sujos = sorted(self._sujo)
                if not sujos:
                    return {"gravados": [], "versao": versao}
                # a fotografia das listas (o `_efetivar` troca a lista, não a muda): cifrar e montar fica fora da trava
                foto = {**self.estado, "abas": dict(self.estado["abas"])}
            prontos = {livro: self._montar(livro, versao, foto) for livro in sujos}
            from .copia import NOMES_LIVROS
            try:
                for livro in sujos:
                    livros.publicar(livro, NOMES_LIVROS[livro], prontos[livro], base=self.base, token=self.token,
                                    sessao=self.sessao)
            except Exception as e:  # noqa: BLE001 — banco fora do ar: o diário segura, a próxima volta tenta de novo
                with self._trava:
                    self.erro = f"{type(e).__name__}: {str(e)[:160]}"
                log.warning("zeladoria: a gravação no banco falhou (%s); o diário segura até a próxima volta", self.erro)
                raise
            with self._trava:
                for livro in sujos:
                    if self._sujo.get(livro, 0) <= versao:
                        self._sujo.pop(livro, None)
                self.versao_banco = versao
                self.erro = None
                restantes = [r for r in self._ler_diario() if r["versao"] > versao]
                self._escrever_diario(restantes, acrescentar=False)
            return {"gravados": sujos, "versao": versao}

    def situacao(self) -> dict:
        with self._trava:
            return {"pendente": bool(self._sujo), "erro": self.erro, "versao": self.estado["versao"],
                    "versao_banco": self.versao_banco}


# ── o gravador do app (um por processo) e o laço que grava em lote ───────────────────────────────────────────────────
_DO_APP = {"g": None, "falha": None, "falhou_em": 0.0}
ESPERA_FALHA_S = 30       # a carga que falhou não se repete a cada pedido
_DO_APP_TRAVA = threading.Lock()
ESPERA_S = 2          # grava depois de 2 s sem mudança...
TETO_S = 20           # ...ou a cada 20 s, se as mudanças não param


def do_app(config):
    from . import leitura
    with _DO_APP_TRAVA:
        # o banco fora: a carga lê os três livros inteiros com a trava presa; repetida a cada pedido, cada tela da torre
        # esperaria a anterior (revisão de 03/11/2026). Por 30 s, a mesma recusa volta na hora
        if _DO_APP["g"] is None and _DO_APP["falha"] and time.time() - _DO_APP["falhou_em"] < ESPERA_FALHA_S:
            raise _DO_APP["falha"]
        if _DO_APP["g"] is None:
            from ..cadastro.ligacoes import pasta_dados
            if config.get("TESTING") and not config.get("NEXUS_DADOS"):
                raise leitura.CopiaAusente("teste sem NEXUS_DADOS: o diário não vai para a pasta de dados real")
            pasta = Path(pasta_dados(config))
            g = Gravador(base=leitura._base(config), token=config.get("GRIDCO_SQL_TOKEN") or "",
                         sessao=leitura._sessao(), cofre=leitura.cofre_de(config),
                         diario=pasta / "zeladoria" / "diario.jsonl")
            try:
                g.carregar(leitura._ler(config))
            except leitura.CopiaAusente as e:
                _DO_APP.update(falha=e, falhou_em=time.time())
                raise
            _DO_APP.update(g=g, falha=None)
            if not config.get("TESTING"):
                threading.Thread(target=_laco, args=(g,), daemon=True, name="nexus-zeladoria-gravacao").start()
        return _DO_APP["g"]


def esquecer() -> None:
    """Para os testes: o próximo `do_app` relê o banco e o diário."""
    with _DO_APP_TRAVA:
        _DO_APP.update(g=None, falha=None, falhou_em=0.0)


def _laco(g: Gravador) -> None:
    primeira = None
    falhas = 0
    while True:
        time.sleep(1)
        try:
            if not g.situacao()["pendente"]:
                primeira = None
                continue
            primeira = primeira or time.time()
            quieto = time.time() - g.ultima_mudanca >= ESPERA_S
            if quieto or time.time() - primeira >= TETO_S:
                time.sleep(min(60, 5 * falhas))
                g.persistir()
                primeira, falhas = None, 0
        except Exception:  # noqa: BLE001 — o erro já está na situação; espera mais a cada falha seguida
            falhas += 1
