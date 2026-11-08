"""Mapa de equipe: os pontos de posição do Nexus Field, da validação ao diário do dia.

O celular manda lotes `{aparelho, fuso, pontos: [{t, lat, lon, prec, vel, mov}]}`. Aqui cada ponto é validado, filtrado pela
janela de trabalho NA HORA DO TÉCNICO, e a coordenada é cifrada (Cofre, contexto `equipe/ponto/<ponto_id>`): em claro ela
existe só na memória do processo. O que vai ao banco (`linha_do_banco`) nunca leva lat/lon. O `Diario` guarda os pontos do
dia em disco, cifrados, para o mapa sobreviver a um reinício antes de o lote chegar ao banco; passou de 7 dias, o arquivo
sai (a guarda vale também no disco).

Lógica pura + disco local: sem rota, sem banco (vêm nas tarefas seguintes).
"""
import hashlib
import json
import logging
import os
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from nexus.campo.equipe import CAB_PONTOS, GUARDA_PONTOS_DIAS, JANELA_H, MAX_PONTOS

log = logging.getLogger(__name__)

_BRT = timezone(timedelta(hours=-3))
_CTX_DIARIO = "equipe/diario"
_FUSO_MAX_MIN = 14 * 60            # o maior fuso do mundo é +14h; acima disso o celular mandou lixo
_FUTURO_TOLERADO = timedelta(minutes=5)   # relógio de celular adiantado um pouco é normal; mais que isso é suspeito


def _num(v):
    """Número finito (bool não conta) ou None."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def _bool(v):
    if isinstance(v, bool):
        return v
    if not isinstance(v, str) and v in (0, 1):
        return bool(v)
    if isinstance(v, str) and v.strip().lower() in ("true", "false"):
        return v.strip().lower() == "true"
    return None


def _ponto_id(pessoa_id: int, t) -> str:
    # letra + hexadecimal (a API do banco infere o tipo pela coluna); determinístico, então o reenvio do lote cai no mesmo id
    return "P" + hashlib.sha1(f"{pessoa_id}|{t}".encode("utf-8")).hexdigest()[:11]


def aceitar(pessoa_id: int, lote: dict, agora_utc: datetime, cofre) -> list[dict]:
    """Os pontos válidos do lote. Mais de MAX_PONTOS = ValueError (a rota responde 413). Ponto ruim sai sozinho."""
    pontos = lote.get("pontos") or []
    if len(pontos) > MAX_PONTOS:
        raise ValueError(f"lote com {len(pontos)} pontos (máximo {MAX_PONTOS})")
    fuso = _num(lote.get("fuso"))
    # sem o fuso não dá para saber se é expediente: melhor perder o lote que rastrear fora do horário
    if fuso is None or abs(fuso) > _FUSO_MAX_MIN:
        return []
    fuso = int(fuso)
    out = []
    for p in pontos:
        if not isinstance(p, dict):
            continue
        t, lat, lon, prec = _num(p.get("t")), _num(p.get("lat")), _num(p.get("lon")), _num(p.get("prec"))
        mov = _bool(p.get("mov"))
        vel = _num(p.get("vel"))
        if None in (t, lat, lon, prec) or mov is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or prec < 0:
            continue
        try:
            inst = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            continue
        if inst > agora_utc + _FUTURO_TOLERADO or inst < agora_utc - timedelta(days=GUARDA_PONTOS_DIAS):
            continue
        hora_local = (inst + timedelta(minutes=fuso)).hour
        if not (JANELA_H[0] <= hora_local < JANELA_H[1]):
            continue
        pid = _ponto_id(pessoa_id, int(t))
        dado = {"lat": lat, "lon": lon, "prec_m": prec, "vel_ms": vel, "mov": mov}
        out.append({
            "ponto_id": pid,
            "data_id": int(inst.astimezone(_BRT).strftime("%Y%m%d")),   # o dia de Brasília (regra 7 do nexus/dados)
            "instante": inst.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pessoa_id": pessoa_id,
            "cifra": cofre.cifrar(json.dumps(dado, separators=(",", ":")), f"equipe/ponto/{pid}"),
            **dado,
        })
    return out


def linha_do_banco(p: dict) -> list:
    """A linha do livro: só as colunas de CAB_PONTOS, a coordenada apenas dentro da cifra."""
    return [p[c] for c in CAB_PONTOS]


class Diario:
    """Os pontos do dia em disco, uma linha cifrada por ponto, um arquivo por dia de Brasília."""

    def __init__(self, pasta: Path, cofre):
        self._dir = Path(pasta) / "equipe"
        self._cofre = cofre
        self._trava = threading.Lock()
        self._dias: dict[int, dict[str, dict]] = {}     # data_id -> ponto_id -> ponto
        self.linhas_ruins = 0
        self._carregar()

    def _arquivo(self, data_id: int) -> Path:
        return self._dir / f"pontos_{data_id}.jsonl"

    def _carregar(self) -> None:
        if not self._dir.exists():
            return
        for arq in sorted(self._dir.glob("pontos_*.jsonl")):
            for linha in arq.read_text(encoding="utf-8").splitlines():
                if not linha.strip():
                    continue
                try:
                    p = json.loads(self._cofre.decifrar(linha.strip(), _CTX_DIARIO))
                    self._dias.setdefault(p["data_id"], {})[p["ponto_id"]] = p
                except Exception:  # noqa: BLE001
                    # queda no meio da escrita ou arquivo adulterado: pula a linha, o resto do dia continua valendo
                    self.linhas_ruins += 1
                    log.warning("equipe: linha ilegível no diário %s foi ignorada", arq.name)

    def acrescentar(self, pontos: list[dict]) -> None:
        with self._trava:
            novos, vistos = [], set()
            for p in pontos:
                if p["ponto_id"] not in self._dias.get(p["data_id"], {}) and p["ponto_id"] not in vistos:
                    vistos.add(p["ponto_id"])
                    novos.append(p)
            if not novos:
                return
            self._dir.mkdir(parents=True, exist_ok=True)
            por_dia: dict[int, list[dict]] = {}
            for p in novos:
                por_dia.setdefault(p["data_id"], []).append(p)
            for data_id, lista in por_dia.items():
                texto = "".join(self._cofre.cifrar(json.dumps(p, ensure_ascii=False), _CTX_DIARIO) + "\n" for p in lista)
                with open(self._arquivo(data_id), "a", encoding="utf-8") as f:
                    antes = f.tell()
                    try:
                        f.write(texto)
                        f.flush()
                        os.fsync(f.fileno())
                    except OSError:
                        try:
                            f.truncate(antes)     # disco cheio: tira o pedaço, senão o próximo acréscimo cola nele
                        except OSError:
                            pass
                        raise
                # só entra na memória o que já está no disco
                for p in lista:
                    self._dias.setdefault(data_id, {})[p["ponto_id"]] = p

    def do_dia(self, dia: date) -> list[dict]:
        with self._trava:
            pts = list(self._dias.get(int(dia.strftime("%Y%m%d")), {}).values())
        return sorted(pts, key=lambda p: p["instante"])

    def ultimos(self, agora_utc: datetime | None = None) -> dict[int, dict]:
        """O último ponto de cada pessoa, até 7 dias atrás (ponto mais velho nunca é usado)."""
        agora_utc = agora_utc or datetime.now(timezone.utc)
        corte = (agora_utc - timedelta(days=GUARDA_PONTOS_DIAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        out: dict[int, dict] = {}
        with self._trava:
            for dia in self._dias.values():
                for p in dia.values():
                    atual = out.get(p["pessoa_id"])
                    if p["instante"] >= corte and (atual is None or p["instante"] > atual["instante"]):
                        out[p["pessoa_id"]] = p
        return out

    def apagar_velhos(self, hoje: date) -> None:
        """Tira do disco e da memória os dias com mais de 7 dias."""
        limite = int((hoje - timedelta(days=GUARDA_PONTOS_DIAS)).strftime("%Y%m%d"))
        with self._trava:
            for data_id in [d for d in self._dias if d < limite]:
                del self._dias[data_id]
            if self._dir.exists():
                for arq in self._dir.glob("pontos_*.jsonl"):
                    try:
                        if int(arq.stem.split("_")[1]) < limite:
                            arq.unlink()
                    except (ValueError, IndexError, OSError):
                        continue
