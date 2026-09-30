"""Onde o cadastro fica guardado. Nesta fase, um JSON LOCAL (o ensaio); a API db_performace vem depois.

A interface é a mesma que o armazém da API vai ter (ler, inserir, gravar com versão, histórico, substituir,
auditoria), para a troca não mexer no resto. O armazém não cifra nem valida: recebe a linha pronta do serviço,
já com o dado sensível cifrado e o selo, e só cuida de três coisas:
- versão: gravar exige a versão que a pessoa leu; se outra gravação passou na frente, é Conflito (a segunda
  pessoa a salvar não apaga o que a primeira gravou);
- histórico: a linha anterior fica guardada a cada gravação;
- nada meio-gravado: escreve num .tmp e troca de uma vez (os.replace), e faz cópia antes de substituir.

O arquivo fica FORA do OneDrive e fora do AppData: o Claude desktop virtualiza o AppData, e o que um processo
aberto por ele grava lá não é o que os outros processos veem (03/09/2026, o banco do gêmeo).
"""
import copy
import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

FORMATO = 1


class Conflito(RuntimeError):
    """Alguém gravou o registro depois que ele foi lido. `atual` é a linha como está agora."""

    def __init__(self, atual: dict):
        super().__init__("o registro foi alterado depois de aberto")
        self.atual = atual


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ArmazemLocal:
    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)
        self._trava = threading.RLock()
        self._cache = None          # (mtime, dados)

    # ── arquivo ────────────────────────────────────────────────────────────

    def _vazio(self) -> dict:
        return {"formato": FORMATO, "entidades": {}, "historico": {}, "auditoria": [], "importacoes": []}

    def _carregar(self) -> dict:
        try:
            mtime = self.caminho.stat().st_mtime_ns
        except FileNotFoundError:
            return self._vazio()
        if self._cache and self._cache[0] == mtime:
            return self._cache[1]
        dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        self._cache = (mtime, dados)
        return dados

    def _salvar(self, dados: dict) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_suffix(self.caminho.suffix + ".tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.caminho)
        self._cache = (self.caminho.stat().st_mtime_ns, dados)

    @property
    def existe(self) -> bool:
        return self.caminho.exists()

    def marca(self) -> int:
        """Muda sempre que o arquivo muda, inclusive por fora do Nexus: é o que invalida o que o serviço
        já decifrou (uma linha mexida à mão tem de ser relida, para o selo acusar)."""
        try:
            return self.caminho.stat().st_mtime_ns
        except FileNotFoundError:
            return 0

    # ── leitura ────────────────────────────────────────────────────────────

    def ler(self, entidade: str) -> list[dict]:
        with self._trava:
            return copy.deepcopy(self._carregar()["entidades"].get(entidade, []))

    def historico(self, entidade: str, id_: str) -> list[dict]:
        """Versões anteriores, a mais recente primeiro."""
        with self._trava:
            h = self._carregar()["historico"].get(entidade, {}).get(id_, [])
            return copy.deepcopy(list(reversed(h)))

    def auditoria(self, limite: int = 200) -> list[dict]:
        with self._trava:
            return copy.deepcopy(list(reversed(self._carregar()["auditoria"]))[:limite])

    def importacoes(self) -> list[dict]:
        with self._trava:
            return copy.deepcopy(list(reversed(self._carregar()["importacoes"])))

    # ── escrita ────────────────────────────────────────────────────────────

    def inserir(self, entidade: str, linha: dict) -> None:
        with self._trava:
            dados = copy.deepcopy(self._carregar())
            linhas = dados["entidades"].setdefault(entidade, [])
            if any(x["id"] == linha["id"] for x in linhas):
                raise ValueError(f"{entidade}: o id {linha['id']} já existe")
            linhas.append(copy.deepcopy(linha))
            self._salvar(dados)

    def gravar(self, entidade: str, linha: dict, versao_esperada: int) -> None:
        with self._trava:
            dados = copy.deepcopy(self._carregar())
            linhas = dados["entidades"].get(entidade, [])
            pos = next((i for i, x in enumerate(linhas) if x["id"] == linha["id"]), None)
            if pos is None:
                raise KeyError(f"{entidade}: {linha['id']} não existe")
            atual = linhas[pos]
            if atual.get("_versao") != versao_esperada:
                raise Conflito(copy.deepcopy(atual))
            dados["historico"].setdefault(entidade, {}).setdefault(linha["id"], []).append(atual)
            linhas[pos] = copy.deepcopy(linha)
            self._salvar(dados)

    def substituir(self, entidades: dict[str, list[dict]], evento: dict) -> Path | None:
        """Troca as entidades enviadas de uma vez (importação). Faz cópia do arquivo antes; a linha que mudou
        vai para o histórico. Entidade que não veio não é tocada."""
        with self._trava:
            copia = None
            if self.existe:
                pasta = self.caminho.parent / "backups"
                pasta.mkdir(parents=True, exist_ok=True)
                marca = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                copia = pasta / f"{self.caminho.stem}_{marca}.json"
                shutil.copy2(self.caminho, copia)
            dados = copy.deepcopy(self._carregar())
            for entidade, novas in entidades.items():
                antes = {x["id"]: x for x in dados["entidades"].get(entidade, [])}
                hist = dados["historico"].setdefault(entidade, {})
                for n in novas:
                    velha = antes.get(n["id"])
                    if velha is not None and velha != n:
                        hist.setdefault(n["id"], []).append(velha)
                dados["entidades"][entidade] = copy.deepcopy(novas)
            dados["importacoes"].append(dict(evento, quando=evento.get("quando") or _agora()))
            self._salvar(dados)
            return copia

    def auditar(self, evento: dict) -> None:
        with self._trava:
            dados = copy.deepcopy(self._carregar())
            dados["auditoria"].append(dict(evento, quando=evento.get("quando") or _agora()))
            self._salvar(dados)
