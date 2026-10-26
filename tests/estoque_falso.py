"""O Fracttal de mentira do estoque (inventário do almoxarifado, 26/10/2026).

`EstoqueFalso` cumpre o mesmo contrato da `EstoqueFracttal` (`nexus/pcm/inventario/estoque.py`, com as mesmas assinaturas:
o teste confere) e vive na memória. É o que os testes da gravação, da régua e da curadoria usam no lugar do Fracttal. Ele
imita o que o passo 0 de 26/10 mostrou do Fracttal de verdade:

- o saldo só se grava com o almoxarifado no modo 2 (sessão de ajuste); fora dele, `ErroFracttal`;
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
  seguintes respondem. É o que a retomada precisa resolver sem duplicar o ajuste.
- `limite_em`: a N-ésima chamada (contando todas, a partir de 1) levanta `Limite`, SEM executar nada. Só aquela: o limite
  passa e a seguinte responde. Aceita um número ou uma lista de números. `voltar_ao_normal` conta como chamada própria,
  logo depois da do `fechar_ajuste`: é assim que se faz o fechamento valer e só o modo 0 falhar.
- `expirar_em`: da N-ésima chamada em diante TODA chamada desta instância levanta `SemLogin`, SEM executar nada: o login
  morto não volta, e o adaptador de verdade reenvia o mesmo JWT morto. Continuar é com outra instância (outro login).
- `agora`: o relógio dos movimentos (uma função que devolve `datetime` ou texto ISO); sem ele, a hora de verdade.

`.chamadas` guarda o nome de cada operação chamada, em ordem (a que falhou também); `.movimentos`, os movimentos (dicts com
`id_almox`, `id_item`, `tipo` "entrada" ou "saida", `qtd`, `referencia`, `quando`, `folio`), do mais velho ao mais novo.
`mover` e `definir_modo` não são do contrato (nem contam como chamada): o teste os usa para simular o que acontece fora do
inventário (uma OS que lança peça, uma compra que entra, um almoxarifado que ficou em inventário físico).
"""
import functools
from datetime import datetime, timezone

from nexus.pcm.inventario.estoque import (ErroFracttal, Estoque, Limite, SemLogin, instante, validar_nivel,
                                          validar_quantidade)


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
    def __init__(self, saldos: dict, *, perder_resposta=(), limite_em=None, expirar_em=None, agora=None):
        """`saldos`: `{id_almox: {id_item: saldo}}`, ou o item como `{"saldo", "minimo", "maximo", "codigo"}` quando o teste
        precisa da régua ou do código (o que falta é None, e o código, vazio). Todo item de `saldos` já está ligado."""
        self._itens: dict[str, dict[str, dict]] = {}
        self._n_ligacao = 9_000_000
        for id_almox, itens in saldos.items():
            for id_item, valor in itens.items():
                v = valor if isinstance(valor, dict) else {"saldo": valor}
                self._itens.setdefault(str(id_almox), {})[str(id_item)] = {
                    "saldo": None if v.get("saldo") is None else float(v["saldo"]),
                    "minimo": None if v.get("minimo") is None else float(v["minimo"]),
                    "maximo": None if v.get("maximo") is None else float(v["maximo"]),
                    "ligacao": str(v.get("ligacao") or self._nova_ligacao()), "codigo": str(v.get("codigo") or "")}
        self._modos: dict[str, int] = {}
        self._pendentes: set[str] = set()                           # finalizado, modo 0 pendente
        self._sessoes: dict[str, dict[str, float | None]] = {}      # almoxarifado -> {id_item: saldo de quando mexeu}
        self._catalogo: dict[str, dict] = {}                        # as peças que `criar_peca` fez
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

    def mover(self, id_almox: str, id_item: str, tipo: str, qtd: float, *, quando=None, referencia: str = "") -> None:
        """Um movimento real (uma OS lançou a peça, entrou uma compra): mexe no saldo e entra em `.movimentos`."""
        if tipo not in ("entrada", "saida"):
            raise ValueError(f"tipo de movimento desconhecido: {tipo!r}")
        if self._modos.get(str(id_almox), 0) in (2, 3):
            raise ErroFracttal("o almoxarifado trava entradas e saídas enquanto está em ajuste ou inventário", "mover")
        item = self._item(id_almox, id_item)
        item["saldo"] = (item["saldo"] or 0.0) + (qtd if tipo == "entrada" else -qtd)
        self._movimento(id_almox, id_item, tipo, qtd, referencia, self._iso(quando))

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

    def _movimento(self, id_almox, id_item, tipo, qtd, referencia, quando) -> dict:
        self._n_movimento += 1
        m = {"id_almox": str(id_almox), "id_item": str(id_item), "tipo": tipo, "qtd": float(qtd),
             "referencia": referencia, "quando": quando, "folio": f"MOV-{self._n_movimento}"}
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
            raise ErroFracttal("o almoxarifado está em inventário físico", "abrir_ajuste")
        self._modos[a] = 2
        self._sessoes.setdefault(a, {})

    @_operacao
    def gravar_saldo(self, id_almox: str, id_item: str, para: float) -> None:
        a = str(id_almox)
        if self._modos.get(a, 0) != 2:
            raise ErroFracttal("o saldo só se grava com o almoxarifado em ajuste de inventário", "gravar_saldo")
        n = validar_quantidade(para, "saldo")
        item = self._item(id_almox, id_item)
        self._sessoes.setdefault(a, {}).setdefault(str(id_item), item["saldo"])      # o saldo de antes da 1ª mexida
        item["saldo"] = n

    @_operacao
    def fechar_ajuste(self, id_almox: str, referencia: str) -> str:
        a, ref = str(id_almox), str(referencia or "").strip()
        if a in self._pendentes:
            raise ErroFracttal("o ajuste já foi finalizado: falta só voltar ao modo normal", "fechar_ajuste")
        if self._modos.get(a, 0) != 2:
            raise ErroFracttal("não há ajuste de inventário aberto para fechar", "fechar_ajuste")
        if not ref:
            raise ValueError("o fechamento precisa da referência")
        quando = self._iso()
        for id_item, antes in self._sessoes.pop(a, {}).items():
            self._movimento(a, id_item, "saida", antes or 0.0, ref, quando)
            self._movimento(a, id_item, "entrada", self._itens[a][id_item]["saldo"] or 0.0, ref, quando)
        self._pendentes.add(a)                           # finalizado; o modo 0 é o passo seguinte, e pode falhar
        folio = str(self._n_movimento + 1)               # o "próximo número de movimento", como o `folio_return`
        self.voltar_ao_normal(a)
        return folio

    @_operacao
    def voltar_ao_normal(self, id_almox: str) -> None:
        a = str(id_almox)
        if self._modos.get(a, 0) == 3:
            raise ErroFracttal("o almoxarifado está em inventário físico: não é do Nexus", "voltar_ao_normal")
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
            raise ErroFracttal("a peça já está ligada a este almoxarifado", "ligar")
        ligacao = self._nova_ligacao()
        codigo = self._catalogo.get(i, {}).get("codigo", "")      # a peça criada por `criar_peca` leva o código
        self._itens.setdefault(a, {})[i] = {"saldo": 0.0, "minimo": 0.0, "maximo": 0.0, "ligacao": ligacao,
                                            "codigo": codigo}
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
    def mexidas_desde(self, id_almox: str, desde_iso: str, ignorar_referencia: str | None = None) -> set[str] | None:
        corte = instante(desde_iso)
        return {m["id_item"] for m in self.movimentos
                if m["id_almox"] == str(id_almox) and instante(m["quando"]) >= corte
                and not (ignorar_referencia and m["referencia"] == ignorar_referencia)}

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
    def criar_peca(self, codigo: str, nome: str, unidade: str = "UNIDADE") -> str:
        codigo, nome = str(codigo or "").strip(), str(nome or "").strip()
        if not codigo or not nome:
            raise ValueError("a peça precisa de código e de nome")
        if codigo.upper() in {c.upper() for c in self._todos_os_codigos()}:
            raise ErroFracttal("já existe peça com esse código", "criar_peca")
        self._n_item += 1
        self._catalogo[str(self._n_item)] = {"codigo": codigo, "nome": nome, "unidade": unidade}
        return str(self._n_item)

    @_operacao
    def codigos(self, sigla: str) -> list[str]:
        sigla = str(sigla or "").strip()
        if not sigla:
            raise ValueError("a sigla da usina não pode ser vazia")
        prefixo = f"SP-{sigla}-".upper()
        return sorted(c for c in self._todos_os_codigos() if c.upper().startswith(prefixo))

    def _todos_os_codigos(self) -> set[str]:
        return ({c["codigo"] for c in self._catalogo.values()}
                | {v["codigo"] for itens in self._itens.values() for v in itens.values() if v["codigo"]})
