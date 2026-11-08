"""Mapa de equipe: a fila de linhas à espera do gravador em lote, espelhada num jornal cifrado em disco (revisão final de
08/11/2026).

Quem usa: as chaves dos aparelhos (`aparelhos.Chaveiro`, os eventos emitida/revogada) e o registro da LGPD
(`acessos.Registro`, quem abriu o mapa ou a rota). As duas filas viviam só na memória até a rodada do gravador, a cada
5 min, e todo push reinicia o servidor: a chave emitida há menos de 5 min sumia (o celular recebia 401 e parava até a
próxima abertura do App), a revogação se perdia (a chave velha, que o livro conhece, voltava a valer) e a linha da LGPD
desaparecia. Agora:
- cada linha vai ao jornal ANTES de entrar na memória (`flush` + `fsync`, como o diário dos pontos): o que a rota
  respondeu está no disco. O disco que falha sobe `OSError` e nada muda (a rota responde 503);
- no boot o jornal é relido: as linhas voltam à fila para a próxima publicação, e as chaves também o veem
  (`Chaveiro.carregar` junta as do livro do banco com as `pendentes` daqui);
- depois da publicação boa o gravador `confirma` as linhas e o jornal é aparado (reescrito sem elas, de uma vez). O
  reinício entre a publicação e o aparo só repete a linha, e a publicação não duplica: ela pula o id que o banco já tem.

Cada linha do arquivo é a lista da linha do livro cifrada (Cofre, um contexto por fila): nem o hash da chave, nem o
aparelho, nem o código de quem abriu o mapa ficam em claro no disco. Sem arquivo (`arquivo=None`), a fila é só de
memória (os testes da regra pura).
"""
import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)


class Fila:
    """As linhas a publicar de um livro (a 1ª coluna é o id), na memória e no jornal em disco."""

    def __init__(self, arquivo: Path | None = None, cofre=None, contexto: str = ""):
        self._arq = Path(arquivo) if arquivo is not None else None
        self._cofre, self._ctx = cofre, contexto
        self._trava = threading.Lock()
        self._fila: list[list] = []          # à espera de `retirar` (a próxima publicação)
        self._no_disco: list[list] = []      # tudo o que está no jornal e o banco ainda não confirmou
        self.linhas_ruins = 0
        self._carregar()

    def _carregar(self) -> None:
        if self._arq is None or not self._arq.exists():
            return
        for texto in self._arq.read_text(encoding="utf-8").splitlines():
            if not texto.strip():
                continue
            try:
                linha = json.loads(self._cofre.decifrar(texto.strip(), self._ctx))
                if not isinstance(linha, list) or not linha:
                    raise ValueError("linha do jornal fora do formato")
            except Exception:  # noqa: BLE001
                # a queda no meio da escrita deixa a última linha pela metade: pula, o resto do jornal vale
                self.linhas_ruins += 1
                log.warning("equipe: linha ilegível no jornal %s foi ignorada", self._arq.name)
                continue
            self._fila.append(linha)
            self._no_disco.append(linha)

    def _cifrada(self, linha: list) -> str:
        return self._cofre.cifrar(json.dumps(linha, ensure_ascii=False, separators=(",", ":")), self._ctx) + "\n"

    def acrescentar(self, linhas: list[list]) -> None:
        """As linhas novas: primeiro o disco (com `fsync`), depois a memória. O disco que falha sobe `OSError` e a fila
        fica como estava."""
        linhas = [list(l) for l in linhas]
        if not linhas:
            return
        with self._trava:
            if self._arq is not None:
                self._arq.parent.mkdir(parents=True, exist_ok=True)
                texto = "".join(self._cifrada(l) for l in linhas)
                with open(self._arq, "a", encoding="utf-8") as f:
                    antes = f.tell()
                    try:
                        f.write(texto)
                        f.flush()
                        os.fsync(f.fileno())
                    except OSError:
                        try:
                            f.truncate(antes)     # disco cheio: tira o pedaço, senão a próxima linha cola nele
                        except OSError:
                            pass
                        raise
            self._fila += linhas
            self._no_disco += linhas

    def retirar(self) -> list[list]:
        """As linhas ainda não publicadas; cada uma sai uma vez (o jornal só é aparado no `confirmar`)."""
        with self._trava:
            fila, self._fila = self._fila, []
        return fila

    def devolver(self, linhas: list[list]) -> None:
        """A publicação falhou: as linhas voltam ao começo da fila (no jornal elas nunca saíram)."""
        with self._trava:
            self._fila = list(linhas) + self._fila

    def pendentes(self) -> list[list]:
        """Tudo o que o banco ainda não confirmou (para as chaves do boot valerem antes da 1ª gravação)."""
        with self._trava:
            return [list(l) for l in self._no_disco]

    def confirmar(self, linhas: list[list]) -> None:
        """A publicação deu certo: o jornal é reescrito sem estas linhas (pelo id), num arquivo temporário que troca o
        de antes de uma vez. Se o disco falhar aqui nada se perde: as linhas ficam no jornal, e o próximo boot as publica
        de novo sem duplicar (o id que o banco já tem não entra)."""
        ids = {str(l[0]) for l in linhas}
        if not ids:
            return
        with self._trava:
            resto = [l for l in self._no_disco if str(l[0]) not in ids]
            if self._arq is not None:
                try:
                    tmp = self._arq.with_suffix(".tmp")
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write("".join(self._cifrada(l) for l in resto))
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, self._arq)
                except OSError as e:
                    log.warning("equipe: não consegui aparar o jornal %s (%s); a próxima publicação pula o que o "
                                "banco já tem", self._arq.name, type(e).__name__)
                    return
            self._no_disco = resto
