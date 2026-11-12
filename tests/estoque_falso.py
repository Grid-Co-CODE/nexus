"""O Fracttal de mentira do estoque (inventário do almoxarifado, 26/10/2026).

`EstoqueFalso` cumpre o mesmo contrato da `EstoqueFracttal` (`nexus/pcm/inventario/estoque.py`, com as mesmas assinaturas:
o teste confere) e vive na memória. É o que os testes da gravação, da régua e da curadoria usam no lugar do Fracttal. Ele
imita o que o passo 0 de 26/10 mostrou do Fracttal de verdade:

- o saldo só se grava com o almoxarifado no modo 2 (sessão de ajuste); fora dele, `Recusado` (o `success: false`: toda
  recusa do falso é o "não" com todas as letras, que é o que o Fracttal de verdade responde a cada uma delas);
- ao FECHAR a sessão, sai um par de movimentos por peça mexida (a saída do saldo antigo inteiro e a entrada do novo, os dois
  com a referência); as peças que ninguém mexeu não geram nada;
- o fechamento são DOIS passos, como no Fracttal: `fechar_ajuste` finaliza (gera os movimentos) e então chama
  `voltar_ao_normal` (modo 0), cada um uma operação à parte para os defeitos. Entre os dois o almoxarifado fica em modo 2 com
  o ajuste "finalizado, modo 0 pendente": a recuperação é só `voltar_ao_normal`, e um segundo `fechar_ajuste` é erro;
- a régua se muda a qualquer hora, sem movimento.

O que o passo 0 NÃO provou e o falso SUPÕE (conferir na prova com o App, Task 10): gravar saldo fora do modo 2 é erro; ligar
duas vezes a mesma peça é erro; criar peça com código repetido é erro; abrir o ajuste num almoxarifado em inventário físico
(modo 3) é erro; abrir de novo o que já está em ajuste não faz nada; um segundo `fechar_ajuste` depois do finalize é erro;
`mover` (entrada ou saída) em modo 2 ou 3 é erro (o passo 0 viu a tela travar Entradas e Saídas; a API recusar, não);
`voltar_ao_normal` em modo 3 é erro, e num ajuste ainda aberto (sem finalizar) só solta o modo, deixando os saldos gravados
sem par de movimentos.

Os defeitos se pedem pelo construtor:
- `perder_resposta`: nomes de operação (`{"gravar_saldo", "fechar_ajuste", "voltar_ao_normal"}`). A PRIMEIRA chamada de cada
  uma grava e depois levanta `ConnectionError` (a resposta "se perdeu", como a conexão que cai depois do Fracttal gravar); as
  seguintes respondem. É o que a retomada precisa resolver sem duplicar o ajuste. `"finalizar"` é o 1º dos dois pedidos
  do `fechar_ajuste` (Task 7): o finalize vale, os movimentos existem, a resposta se perde e o modo 0 nem é pedido (o
  almoxarifado fica em modo 2, "finalizado, modo 0 pendente"). Não conta como chamada: o `limite_em` e o `expirar_em`
  seguem contando como antes.
- `limite_em`: a N-ésima chamada (contando todas, a partir de 1) levanta `Limite`, SEM executar nada. Só aquela: o limite
  passa e a seguinte responde. Aceita um número ou uma lista de números. `voltar_ao_normal` conta como chamada própria,
  logo depois da do `fechar_ajuste`: é assim que se faz o fechamento valer e só o modo 0 falhar.
- `expirar_em`: da N-ésima chamada em diante TODA chamada desta instância levanta `SemLogin`, SEM executar nada: o login
  morto não volta, e o adaptador de verdade reenvia o mesmo JWT morto. Continuar é com outra instância (outro login).
- `agora`: o relógio dos movimentos (uma função que devolve `datetime` ou texto ISO); sem ele, a hora de verdade.

`.chamadas` guarda o nome de cada operação chamada, em ordem (a que falhou também); `.movimentos`, os movimentos (dicts com
`id_almox`, `id_item`, `tipo` "entrada" ou "saida", `qtd`, `referencia`, `quando`, `folio`, `id` (o `id_movements`, crescente)
e `tipo_fracttal` (15 o ajuste do fechamento; 1 a entrada (a compra) e 5 a saída (a GENERAL) de `mover`, 15 com `ajuste=True`,
ou o `tipo_fracttal=` dado; 4 a saída ligada da requisição)), do mais velho ao mais novo.
`pecas_do_catalogo` (12/11/2026): as linhas da lista de peças do Fracttal com o Tipo e as Classificações (`id_group`,
`groups_description`, ...), de onde o `classificacoes` tira as opções, como o de verdade; a peça que `criar_peca` faz com
`grupos` os guarda em `grupos` no catálogo (só quando vêm).
As requisições de material (12/11/2026, item 6 da 2ª rodada): `requisicoes=` são as linhas do `movements_new_list` como o
Fracttal as devolve (`id`, `document`, `id_warehouse_source`, `id_movement_state`, `approved`, `approval_date`, ...),
`detalhes=` `{id da requisição: as linhas do movements_details_list}` e `responsaveis=` as linhas do
`personnel.responsibles_list` (`id`, `email`, `description`). O falso SUPÕE (a prova de 12/11/2026 viu só o caminho feliz):
aprovar e recusar só no estado 3 (fora dele, `STATE_CHANGED`, esse provado); a saída ligada só no estado 3, com o almoxarifado
no modo 0 e o saldo de cada peça cobrindo a quantidade (senão `Recusado`, e nada muda); ela baixa o saldo, leva a requisição a
5 e põe a saída em `.movimentos`. `.decisoes` guarda o corpo de cada aprovar e recusar; `.saidas`, o de cada saída.
`mudar_requisicao` (fora do contrato) muda a linha por fora (a requisição aprovada ou cancelada no meio).
`mover` e `definir_modo` não são do contrato (nem contam como chamada): o teste os usa para simular o que acontece fora do
inventário (uma OS que lança peça, uma compra que entra, um almoxarifado que ficou em inventário físico).
"""
import functools
from datetime import datetime, timezone

from nexus.pcm.inventario import estoque as _E
from nexus.pcm.inventario.estoque import (TIPO_AJUSTE, Estoque, Limite, Recusado, SemLogin, classificacoes_das_pecas,
                                          corpo_dos_grupos, instante, validar_nivel, validar_quantidade)


def _conjunto(valor):
    if valor is None:
        return set()
    return {valor} if isinstance(valor, int) else set(valor)


def _operacao(f):
    """Toda operação do contrato: conta a chamada, deixa o limite ou o login cair nela e, se a resposta é das que se
    perdem, levanta DEPOIS de executar."""
    @functools.wraps(f)
    def chamada(self, *args, **kwargs):
        self._entrar(f.__name__)
        resultado = f(self, *args, **kwargs)
        self._depois(f.__name__)
        return resultado
    return chamada


class EstoqueFalso(Estoque):
    def __init__(self, saldos: dict, *, perder_resposta=(), limite_em=None, expirar_em=None, agora=None,
                 pecas_do_catalogo=None, requisicoes=None, detalhes=None, responsaveis=None):
        """`saldos`: `{id_almox: {id_item: saldo}}`, ou o item como `{"saldo", "minimo", "maximo", "codigo", "unidade",
        "criticidade"}` quando o teste precisa da régua, do código, da unidade ou da criticidade (o que falta é None, e o
        código, a unidade e a criticidade, vazios). Todo item de `saldos` já está ligado."""
        self._itens: dict[str, dict[str, dict]] = {}
        self._n_ligacao = 9_000_000
        for id_almox, itens in saldos.items():
            for id_item, valor in itens.items():
                v = valor if isinstance(valor, dict) else {"saldo": valor}
                self._itens.setdefault(str(id_almox), {})[str(id_item)] = {
                    "saldo": None if v.get("saldo") is None else float(v["saldo"]),
                    "minimo": None if v.get("minimo") is None else float(v["minimo"]),
                    "maximo": None if v.get("maximo") is None else float(v["maximo"]),
                    "ligacao": str(v.get("ligacao") or self._nova_ligacao()), "codigo": str(v.get("codigo") or ""),
                    "unidade": str(v.get("unidade") or ""), "criticidade": str(v.get("criticidade") or "")}
        self._modos: dict[str, int] = {}
        self._pendentes: set[str] = set()                           # finalizado, modo 0 pendente
        self._sessoes: dict[str, dict[str, float | None]] = {}      # almoxarifado -> {id_item: saldo de quando mexeu}
        self._catalogo: dict[str, dict] = {}                        # as peças que `criar_peca` fez
        self._pecas_do_catalogo = list(pecas_do_catalogo or [])     # a lista de peças com o Tipo e as Classificações
        self._movs = {str(r["id"]): dict(r) for r in (requisicoes or [])}
        self._detalhes = {str(k): [dict(l) for l in v] for k, v in (detalhes or {}).items()}
        self._responsaveis = [dict(r) for r in (responsaveis or [])]
        self.decisoes: list[dict] = []
        self.saidas: list[dict] = []
        self._n_item, self._n_movimento = 53_000_000, 0
        self._perder, self._perdidas = ({perder_resposta} if isinstance(perder_resposta, str)
                                        else set(perder_resposta or ())), set()
        self._limite, self._agora = _conjunto(limite_em), agora
        self._expira_em = min(_conjunto(expirar_em), default=None)  # a partir desta chamada, o login está morto
        self.movimentos: list[dict] = []
        self.chamadas: list[str] = []

    # ── o que o teste mexe por fora do contrato ──────────────────────────────────────────────────────────────────────────
    def definir_modo(self, id_almox: str, modo: int) -> None:
        """Põe o almoxarifado num modo (3 = inventário físico, o `ATHN-MTS200` do passo 0)."""
        self._modos[str(id_almox)] = int(modo)

    def mover(self, id_almox: str, id_item: str, tipo: str, qtd: float, *, quando=None, referencia: str = "",
              ajuste: bool = False, documento: str = "", tipo_fracttal: int | None = 0) -> None:
        """Um movimento real (uma OS lançou a peça, entrou uma compra): mexe no saldo e entra em `.movimentos`. `ajuste`: o
        movimento é um ajuste de inventário (tipo 15) feito por fora (outra tela), e não uma entrada ou saída comum. A saída é a
        GENERAL (5, a Saída Geral à mão) e a entrada, a compra (1); `tipo_fracttal` dá outro (2 a devolução; None, a linha do
        histórico que vem sem o tipo)."""
        if tipo not in ("entrada", "saida"):
            raise ValueError(f"tipo de movimento desconhecido: {tipo!r}")
        if self._modos.get(str(id_almox), 0) in (2, 3):
            raise Recusado("o almoxarifado trava entradas e saídas enquanto está em ajuste ou inventário", "mover")
        item = self._item(id_almox, id_item)
        item["saldo"] = (item["saldo"] or 0.0) + (qtd if tipo == "entrada" else -qtd)
        m = self._movimento(id_almox, id_item, tipo, qtd, referencia, self._iso(quando),
                            TIPO_AJUSTE if ajuste else (1 if tipo == "entrada" else _E.TIPO_SAIDA_GERAL))
        if tipo_fracttal != 0 and not ajuste:
            m["tipo_fracttal"] = tipo_fracttal
        m["documento"] = documento

    def mudar_requisicao(self, id_requisicao, **campos) -> None:
        """A requisição mudada por fora (alguém aprovou ou cancelou na tela do Fracttal)."""
        self._movs[str(id_requisicao)].update(campos)

    # ── as regras do falso ───────────────────────────────────────────────────────────────────────────────────────────────
    def _entrar(self, nome: str) -> None:
        self.chamadas.append(nome)
        n = len(self.chamadas)
        if self._expira_em is not None and n >= self._expira_em:
            raise SemLogin("o login do Fracttal expirou (de mentira)")
        if n in self._limite:
            raise Limite("RPC HTTP 429 (de mentira)")

    def _depois(self, nome: str) -> None:
        if nome in self._perder and nome not in self._perdidas:
            self._perdidas.add(nome)
            raise ConnectionError(f"a resposta de {nome} se perdeu (de mentira): o Fracttal já gravou")

    def _nova_ligacao(self) -> str:
        self._n_ligacao += 1
        return str(self._n_ligacao)

    def _iso(self, quando=None) -> str:
        valor = quando if quando is not None else (self._agora() if self._agora else datetime.now(timezone.utc))
        return instante(valor).isoformat()

    def _item(self, id_almox, id_item) -> dict:
        try:
            return self._itens[str(id_almox)][str(id_item)]
        except KeyError:
            raise ValueError(f"a peça {id_item} não está ligada ao almoxarifado {id_almox}") from None

    def _movimento(self, id_almox, id_item, tipo, qtd, referencia, quando, tipo_fracttal=None) -> dict:
        self._n_movimento += 1
        m = {"id_almox": str(id_almox), "id_item": str(id_item), "tipo": tipo, "qtd": float(qtd),
             "referencia": referencia, "quando": quando, "folio": f"MOV-{self._n_movimento}",
             "id": 84_000_000 + self._n_movimento, "tipo_fracttal": TIPO_AJUSTE if tipo_fracttal is None else tipo_fracttal}
        self.movimentos.append(m)
        return m

    # ── o contrato ────────────────────────────────────────────────────────────────────────────────────────────────────────
    @_operacao
    def modo(self, id_almox: str) -> int:
        return self._modos.get(str(id_almox), 0)

    @_operacao
    def abrir_ajuste(self, id_almox: str) -> None:
        a = str(id_almox)
        if self._modos.get(a, 0) == 3:
            raise Recusado("o almoxarifado está em inventário físico", "abrir_ajuste")
        self._modos[a] = 2
        self._sessoes.setdefault(a, {})

    @_operacao
    def gravar_saldo(self, id_almox: str, id_item: str, para: float) -> None:
        a = str(id_almox)
        if self._modos.get(a, 0) != 2:
            raise Recusado("o saldo só se grava com o almoxarifado em ajuste de inventário", "gravar_saldo")
        n = validar_quantidade(para, "saldo")
        item = self._item(id_almox, id_item)
        self._sessoes.setdefault(a, {}).setdefault(str(id_item), item["saldo"])      # o saldo de antes da 1ª mexida
        item["saldo"] = n

    @_operacao
    def fechar_ajuste(self, id_almox: str, referencia: str) -> str:
        a, ref = str(id_almox), str(referencia or "").strip()
        if a in self._pendentes:
            raise Recusado("o ajuste já foi finalizado: falta só voltar ao modo normal", "fechar_ajuste")
        if self._modos.get(a, 0) != 2:
            raise Recusado("não há ajuste de inventário aberto para fechar", "fechar_ajuste")
        if not ref:
            raise ValueError("o fechamento precisa da referência")
        quando = self._iso()
        for id_item, antes in self._sessoes.pop(a, {}).items():
            self._movimento(a, id_item, "saida", antes or 0.0, ref, quando)
            self._movimento(a, id_item, "entrada", self._itens[a][id_item]["saldo"] or 0.0, ref, quando)
        self._pendentes.add(a)                           # finalizado; o modo 0 é o passo seguinte, e pode falhar
        folio = str(self._n_movimento + 1)               # o "próximo número de movimento", como o `folio_return`
        # o finalizar é um ponto de defeito à parte, que não conta como chamada (a numeração da Task 2 fica a mesma):
        # `perder_resposta={"finalizar"}` é o finalize que valeu e cuja resposta se perdeu antes do pedido do modo 0
        self._depois("finalizar")
        self.voltar_ao_normal(a)
        return folio

    @_operacao
    def voltar_ao_normal(self, id_almox: str) -> None:
        a = str(id_almox)
        if self._modos.get(a, 0) == 3:
            raise Recusado("o almoxarifado está em inventário físico: não é do Nexus", "voltar_ao_normal")
        self._modos[a] = 0
        self._pendentes.discard(a)
        self._sessoes.pop(a, None)

    @_operacao
    def ler(self, id_almox: str) -> dict[str, dict]:
        return {i: dict(v) for i, v in self._itens.get(str(id_almox), {}).items()}

    @_operacao
    def ligar(self, id_almox: str, id_item: str) -> str:
        a, i = str(id_almox), str(id_item)
        if i in self._itens.get(a, {}):
            raise Recusado("a peça já está ligada a este almoxarifado", "ligar")
        ligacao = self._nova_ligacao()
        criada = self._catalogo.get(i, {})                        # a peça criada por `criar_peca` leva o código e a unidade
        self._itens.setdefault(a, {})[i] = {"saldo": 0.0, "minimo": 0.0, "maximo": 0.0, "ligacao": ligacao,
                                            "codigo": criada.get("codigo", ""), "unidade": criada.get("unidade", ""),
                                            "criticidade": ""}
        return ligacao

    @_operacao
    def achar_movimento(self, id_almox: str, referencia: str, desde_iso: str | None = None) -> str | None:
        alvo = str(referencia or "").strip()
        if not alvo:
            raise ValueError("sem a referência, qualquer movimento seria o achado")
        desde = instante(desde_iso) if desde_iso else None
        for m in reversed(self.movimentos):
            if m["id_almox"] == str(id_almox) and m["referencia"] == alvo and (desde is None or instante(m["quando"]) >= desde):
                return m["folio"]
        return None

    @_operacao
    def mexidas_desde(self, id_almox: str, desde_iso: str, ignorar_referencia: str | None = None,
                      ignorar_prefixo: str | None = None) -> set[str] | None:
        corte = instante(desde_iso)
        return {m["id_item"] for m in self.movimentos
                if m["id_almox"] == str(id_almox) and instante(m["quando"]) >= corte
                and not (ignorar_referencia and m["referencia"] == ignorar_referencia)
                and not (ignorar_prefixo and m["referencia"].startswith(ignorar_prefixo))}

    @_operacao
    def ultimo_movimento(self, id_almox: str) -> int | None:
        return max((m["id"] for m in self.movimentos if m["id_almox"] == str(id_almox)), default=None)

    @_operacao
    def ajustes_depois(self, id_almox: str, depois_de: int | None, desde_iso: str,
                       ignorar_prefixo: str | None = None) -> set[str] | None:
        instante(desde_iso)                              # a data ruim é erro de quem chama, como no de verdade
        return {m["id_item"] for m in self.movimentos
                if m["id_almox"] == str(id_almox) and m["tipo_fracttal"] == TIPO_AJUSTE
                and (depois_de is None or m["id"] > depois_de)
                and not (ignorar_prefixo and m["referencia"].startswith(ignorar_prefixo))}

    @_operacao
    def definir_regua(self, id_almox: str, id_item: str, minimo: float | None, maximo: float | None) -> None:
        mn, mx = validar_nivel(minimo, "mínimo"), validar_nivel(maximo, "máximo")
        if mn is not None and mx is not None and mn > mx:
            raise ValueError(f"o mínimo ({minimo}) não pode passar do máximo ({maximo})")
        if mn is None and mx is None:
            return
        item = self._item(id_almox, id_item)
        if mn is not None:
            item["minimo"] = mn
        if mx is not None:
            item["maximo"] = mx

    @_operacao
    def criar_peca(self, codigo: str, nome: str, unidade: str = "UNIDADE", descricao: str = "",
                   grupos: dict | None = None) -> str:
        codigo, nome, descricao = str(codigo or "").strip(), str(nome or "").strip(), str(descricao or "").strip()
        if not codigo or not nome:
            raise ValueError("a peça precisa de código e de nome")
        corpo = corpo_dos_grupos(grupos)                     # a mesma regra do de verdade: só os que vieram, como número
        if codigo.upper() in {c.upper() for c in self._todos_os_codigos()}:
            raise Recusado("já existe peça com esse código", "criar_peca")
        self._n_item += 1
        # a descrição e os grupos só entram quando vêm (30/10 e 12/11/2026): a peça de antes fica com as mesmas três chaves
        self._catalogo[str(self._n_item)] = {"codigo": codigo, "nome": nome, "unidade": unidade,
                                             **({"descricao": descricao} if descricao else {}),
                                             **({"grupos": corpo} if corpo else {})}
        return str(self._n_item)

    @_operacao
    def classificacoes(self) -> dict[str, list[tuple[str, str]]]:
        return classificacoes_das_pecas(self._pecas_do_catalogo)

    @_operacao
    def pecas_com_grupos(self) -> list[dict]:
        campos = ("code",) + tuple(c for par in _E.GRUPOS.values() for c in par)
        return [{k: l.get(k) for k in campos} for l in self._pecas_do_catalogo]

    # ── a requisição de material ──────────────────────────────────────────────────────────────────────────────────────────
    def _as_requisicoes(self, desde_dias, agora):
        corte = _E._ate(desde_dias, agora)
        for linha in sorted(self._movs.values(), key=lambda l: -int(l["id"])):
            r = _E.requisicao_da_linha(linha)
            if _E._velha(r, corte):
                return
            yield r

    @_operacao
    def requisicoes(self, desde_dias: int = 90, agora=None) -> list[dict]:
        return list(self._as_requisicoes(desde_dias, agora))

    @_operacao
    def reler_requisicao(self, id_requisicao: str, desde_dias: int = 90, agora=None) -> dict | None:
        alvo = str(int(str(id_requisicao).strip()))
        return next((r for r in self._as_requisicoes(desde_dias, agora) if r["id"] == alvo), None)

    @_operacao
    def pecas_da_requisicao(self, id_requisicao: str) -> list[dict]:
        return [dict(l) for l in self._detalhes.get(str(id_requisicao), [])]

    def _mov_no_estado_3(self, id_requisicao, operacao) -> dict:
        mov = self._movs.get(str(id_requisicao))
        if mov is None:
            raise Recusado("NOT_FOUND", operacao)
        if int(mov.get("id_movement_state") or 0) != _E.NAO_ENTREGUE:
            raise Recusado("STATE_CHANGED", operacao)
        return mov

    def _decidir(self, id_requisicao, aprovar, comentario, conta, operacao) -> None:
        id_conta, nome = _E.conta_valida(conta)
        texto = _E.comentario_valido(comentario)
        mov = self._mov_no_estado_3(id_requisicao, operacao)
        self.decisoes.append({"id": int(str(id_requisicao)), "approved": aprovar, "approved_comment": texto,
                              "id_accounts": id_conta, "accounts_log_name": nome})
        mov.update(approved=aprovar, approved_comment=texto, approval_date=self._iso(), accounts_log_name=nome)

    @_operacao
    def aprovar_requisicao(self, id_requisicao: str, comentario: str, conta: dict) -> None:
        self._decidir(id_requisicao, True, comentario, conta, "aprovar_requisicao")

    @_operacao
    def recusar_requisicao(self, id_requisicao: str, comentario: str, conta: dict) -> None:
        self._decidir(id_requisicao, False, comentario, conta, "recusar_requisicao")

    @_operacao
    def saida_da_requisicao(self, requisicao: dict, pecas: list[dict], responsavel: dict, agora=None) -> str:
        resp = responsavel or {}
        if not pecas or not all(isinstance(p, dict) for p in pecas):
            raise ValueError("a saída precisa das peças da requisição")
        if not str(resp.get("id") or "").strip() or not str(resp.get("descricao") or "").strip():
            raise ValueError("sem o responsável do Fracttal: a saída não vai sem dono")
        mov = self._mov_no_estado_3(requisicao["id"], "saida_da_requisicao")
        almox = str(mov["id_warehouse_source"])
        if self._modos.get(almox, 0) in (2, 3):
            raise Recusado("o almoxarifado trava as saídas enquanto está em ajuste ou inventário", "saida_da_requisicao")
        baixas = []
        for p in pecas:
            # o id da peça no catálogo é o `id_item_original` (o `id_item` da linha é o da peça no almoxarifado; 12/11/2026)
            id_item = str(p.get("id_item_original") or p.get("id_item"))
            item = self._itens.get(almox, {}).get(id_item)
            qtd = float(p.get("qty") or 0)
            if item is None or item["saldo"] is None or item["saldo"] < qtd:
                raise Recusado("INSUFFICIENT_STOCK (de mentira)", "saida_da_requisicao")
            baixas.append((id_item, item, qtd))
        quando = self._iso(agora)
        for id_item, item, qtd in baixas:
            item["saldo"] -= qtd
            m = self._movimento(almox, id_item, "saida", qtd, "", quando, 4)
            m["documento"] = str(mov.get("document") or "")
        mov["id_movement_state"] = _E.ENTREGA_TOTAL
        nova = str(70_000_000 + len(self.saidas) + 1)
        self.saidas.append({"id": nova, "id_movement_reference": int(str(requisicao["id"])), "id_warehouse_source": int(almox),
                            "id_responsible": int(str(resp["id"])), "document": str(requisicao.get("os") or ""),
                            "items": [dict(p) for p in pecas]})
        return nova

    @_operacao
    def saida_com_a_os(self, id_almox: str, os_: str, ids_itens: list[str], desde_iso: str) -> dict | None:
        desde = instante(desde_iso)
        movs = [{"id_item": m["id_item"], "referencia": m["referencia"], "documento": m.get("documento", ""),
                 "tipo": m["tipo_fracttal"], "folio": m["folio"], "quando": m["quando"]}
                for m in reversed(self.movimentos) if m["id_almox"] == str(id_almox) and instante(m["quando"]) >= desde]
        return _E.primeira_com_a_os(movs, os_, ids_itens)

    @_operacao
    def responsavel(self, email: str) -> dict | None:
        alvo = str(email or "").strip().lower()
        if not alvo:
            raise ValueError("sem o e-mail, qualquer responsável seria o achado")
        for r in self._responsaveis:
            if str(r.get("email") or "").strip().lower() == alvo and str(r.get("description") or "").strip():
                return {"id": str(r["id"]), "descricao": str(r["description"]).strip()}
        return None

    @_operacao
    def codigos(self, sigla: str) -> list[str]:
        sigla = str(sigla or "").strip()
        if not sigla:
            raise ValueError("a sigla da usina não pode ser vazia")
        prefixo = f"SP-{sigla}-".upper()
        return sorted(c for c in self._todos_os_codigos() if c.upper().startswith(prefixo))

    @_operacao
    def peca(self, codigo: str) -> dict | None:
        alvo = str(codigo or "").strip().upper()
        if not alvo:
            raise ValueError("sem o código, qualquer peça seria a achada")
        for id_item, v in self._catalogo.items():
            if v["codigo"].upper() == alvo:
                return {"id": id_item, "nome": v["nome"]}
        for itens in self._itens.values():
            for id_item, v in itens.items():
                if v["codigo"] and v["codigo"].upper() == alvo:
                    return {"id": id_item, "nome": ""}         # a peça que veio do saldo não traz o nome
        return None

    @_operacao
    def achar_peca(self, codigo: str) -> str | None:
        alvo = str(codigo or "").strip().upper()
        if not alvo:
            raise ValueError("sem o código, qualquer peça seria a achada")
        for id_item, v in self._catalogo.items():
            if v["codigo"].upper() == alvo:
                return id_item
        for itens in self._itens.values():
            for id_item, v in itens.items():
                if v["codigo"] and v["codigo"].upper() == alvo:
                    return id_item
        return None

    def _todos_os_codigos(self) -> set[str]:
        return ({c["codigo"] for c in self._catalogo.values()}
                | {v["codigo"] for itens in self._itens.values() for v in itens.values() if v["codigo"]})
