"""Mapa de equipe: o "Celular pronto" de cada técnico do piloto (10/11/2026).

O Levi, pela sessão Nexus Field: "tem como sabermos qual o técnico não aceitou tudo? no caso de aceitar tudo e tirar a
restrição da bateria" ("Sim, constrói"). Desde a 1.2.2 a casca manda, em cada lote de pontos e no aviso sem permissão,
os `ajustes` do aparelho (só depois do termo aceito: antes dele a casca não manda nada):

    "ajustes": {"termo": "4" | ... | null, "localizacao": "precisa" | "aproximada" | "sem", "tempoTodo": bool,
                "bateriaSemRestricao": bool, "notificacao": bool}

A 1.2.1 e as de antes não mandam o campo, e o Nexus de antes o ignorava: o contrato segue compatível.

**Parte 2 (10/11/2026, a casca 1.2.3; Levi: "quando o cara instala já tem que ter tudo pronto"):** o 6º campo,
`inicioAutomatico` (true, false ou null; null = não é Xiaomi, Redmi nem POCO, ou não se sabe). O caso, no celular do Levi
pelo cabo: sem o Início automático do HyperOS o Android barra o app depois de atualizar ("MY_PACKAGE_REPLACED: process
is not permitted to auto start") e a coleta não volta. Só o false entra no "Falta:" ("Início automático"); a 1.2.2, sem o
campo, segue valendo. E o termo vale pela VERSÃO: número e não menor que o `TERMO_ATUAL` (a ordem da subida não importa:
o Nexus no "4" já aceita o "5" da 1.2.3; quando o `TERMO_ATUAL` subir para "5", a 1.2.2 passa a "Falta: termo novo").

**Pronto** = o termo na versão atual ou mais nova (`TERMO_ATUAL`), a localização precisa, o "Permitir o tempo todo", a
bateria sem restrição, a notificação e, no Xiaomi, o Início automático. Senão, "Falta:" e o que falta, nas palavras da casca. Sem os ajustes, o porquê: o
lote sem o campo é a versão antiga do app; a chave emitida sem lote nenhum, "não aceitou o termo ou não abriu o app"; sem
chave, "nunca abriu o app".

**Onde mora:** no disco da pasta de dados (`equipe/celulares.json`, cifrado com a chave do cadastro, como o diário), não
no banco: é a configuração do aparelho por pessoa, e o reinício (todo push) não a apaga. Grava só quando muda. O ajuste
torto (fora do contrato) não vale e não apaga o que já se sabia; nem ele nem o disco que falha derrubam o lote.
"""
import json
import logging
import threading
from datetime import timezone
from pathlib import Path

from nexus.campo.equipe import TERMO_ATUAL

log = logging.getLogger(__name__)

LOCALIZACOES = ("precisa", "aproximada", "sem")
_BOOLS = ("tempoTodo", "bateriaSemRestricao", "notificacao")
_CTX = "equipe/celulares"
_UTC = "%Y-%m-%dT%H:%M:%SZ"
# o que falta, na ordem e nas palavras da casca (o que o técnico vê no celular)
_FALTA = (("termo", "termo novo"), ("localizacao", "localização precisa"), ("tempoTodo", "Permitir o tempo todo"),
          ("bateriaSemRestricao", "bateria sem restrição"), ("notificacao", "notificação"),
          ("inicioAutomatico", "Início automático"))
_OPCIONAIS = ("inicioAutomatico",)      # da 1.2.3 em diante; a 1.2.2 não manda


def ler(bruto) -> dict | None:
    """Os `ajustes` do lote, conferidos contra o contrato; None se não seguem (o que veio do aparelho é entrada hostil)."""
    obrigatorias = {"termo", "localizacao", *_BOOLS}
    if not isinstance(bruto, dict) or not obrigatorias <= set(bruto) <= obrigatorias | set(_OPCIONAIS):
        return None
    termo = bruto["termo"]
    if termo is not None and not (isinstance(termo, str) and 0 < len(termo) <= 12):
        return None
    if bruto["localizacao"] not in LOCALIZACOES or not all(isinstance(bruto[k], bool) for k in _BOOLS):
        return None
    out = {"termo": termo, "localizacao": bruto["localizacao"], **{k: bruto[k] for k in _BOOLS}}
    if "inicioAutomatico" in bruto:
        if bruto["inicioAutomatico"] not in (True, False, None):
            return None
        out["inicioAutomatico"] = bruto["inicioAutomatico"]
    return out


def _versao(termo):
    try:
        return int(str(termo).strip())
    except (TypeError, ValueError):
        return None


def faltas(aj: dict) -> list[str]:
    v = _versao(aj["termo"])
    ok = {"termo": v is not None and v >= int(TERMO_ATUAL), "localizacao": aj["localizacao"] == "precisa",
          **{k: aj[k] is True for k in _BOOLS},
          "inicioAutomatico": aj.get("inicioAutomatico") is not False}     # só o false falta (null = não é Xiaomi)
    return [palavra for chave, palavra in _FALTA if not ok[chave]]


def situacao(tem_chave: bool, registro: dict | None) -> dict:
    """{"pronto", "tom", "texto"} para o Piloto. `registro` = o que se sabe do celular (`Celulares.de`)."""
    if registro is None:
        texto = "Não aceitou o termo ou não abriu o app" if tem_chave else "Nunca abriu o app"
        return {"pronto": False, "tom": "neutro", "texto": texto}
    if registro.get("ajustes") is None:
        return {"pronto": False, "tom": "alerta", "texto": "Versão antiga do app"}
    falta = faltas(registro["ajustes"])
    if falta:
        return {"pronto": False, "tom": "alerta", "texto": "Falta: " + ", ".join(falta)}
    return {"pronto": True, "tom": "ok", "texto": "Celular pronto"}


class Celulares:
    """{pessoa_id: {"ajustes": dict | None, "desde": instante UTC}} na memória e no disco (cifrado)."""

    def __init__(self, arquivo: Path | None, cofre):
        self._arquivo, self._cofre = arquivo, cofre
        self._trava = threading.Lock()
        self._por_pessoa: dict[int, dict] = {}
        if arquivo is not None and arquivo.exists():
            try:
                dados = json.loads(cofre.decifrar(arquivo.read_text(encoding="utf-8").strip(), _CTX))
                self._por_pessoa = {int(k): v for k, v in dados.items()}
            except Exception as e:      # noqa: BLE001 — o arquivo que não abre: começa vazio, e o próximo lote refaz
                log.warning("equipe: o arquivo dos celulares não abriu (%s)", type(e).__name__)

    def de(self, pessoa_id) -> dict | None:
        with self._trava:
            r = self._por_pessoa.get(pessoa_id)
            return dict(r) if r else None

    def anotar(self, pessoa_id: int, ajustes: dict | None, agora) -> None:
        """O que o lote disse do celular (`ajustes` já lidos; None = o lote veio sem o campo). Grava só quando muda; o
        disco que falha vai ao log e não derruba o lote."""
        with self._trava:                   # a gravação dentro da trava: dois lotes juntos não gravam a foto velha por último
            atual = self._por_pessoa.get(pessoa_id)
            if atual is not None and atual.get("ajustes") == ajustes:
                return
            self._por_pessoa[pessoa_id] = {"ajustes": ajustes,
                                           "desde": agora.astimezone(timezone.utc).strftime(_UTC)}
            if self._arquivo is None:
                return
            texto = json.dumps({str(k): v for k, v in self._por_pessoa.items()}, separators=(",", ":"))
            try:
                self._arquivo.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._arquivo.with_suffix(".tmp")
                tmp.write_text(self._cofre.cifrar(texto, _CTX), encoding="utf-8")
                tmp.replace(self._arquivo)
            except OSError as e:
                log.warning("equipe: o arquivo dos celulares não foi gravado (%s)", type(e).__name__)
