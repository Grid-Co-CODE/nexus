"""O deploy espera o lote aberto da gravação do inventário (Levi, 26/10/2026). O `deploy/atualizar.sh` chama:

    .venv/bin/python -B ferramentas/gravacao_aberta.py

Enquanto a gravação do inventário tem um lote aberto no Fracttal (a sessão de ajuste, modo 2), o almoxarifado fica travado:
nem entrada, nem saída, nem pedido de compra. Push na `main` reinicia o Nexus em ~2 min (`DEPLOY.md`, seção 8), e o restart
no meio do lote mata a gravação com o almoxarifado travado até quem aprovou voltar e continuar. Então o restart espera o
lote fechar, por no máximo 10 minutos contados da 1ª espera; depois reinicia assim mesmo (um deploy não fica preso por
uma gravação que não termina).

- Saída 1 e a linha `ESPERAR` (só ela, na saída padrão): há uma gravação VIVA com um lote aberto (o controle em
  "gravando", um lote em `abrindo`/`aberto`/`fechando` e salvo há menos de 5 min: `gravacao.com_lote_aberto`) e a 1ª espera
  foi há menos de 10 min. A hora da 1ª espera fica em `<NEXUS_DADOS>/almox_inventario/deploy-espera.txt`.
- Saída 0: pode reiniciar (nenhum lote aberto, os 10 min passaram, ou QUALQUER erro aqui: o deploy nunca fica preso por
  causa deste ajudante). O script só espera com a saída 1 E o `ESPERAR`: um `sudo` ou um Python que falhe também sai com 1.

A pasta é achada como o Nexus a acha (`NEXUS_DADOS` do .env ou do ambiente, senão a padrão: `gravacao._pasta`). O porquê vai
para a saída de erro (o journal do timer); nunca o conteúdo do controle.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LIMITE = timedelta(minutes=10)
MARCA = "deploy-espera.txt"
ESPERAR = "ESPERAR"


def _ler_marca(marca: Path) -> datetime | None:
    try:
        d = datetime.fromisoformat(marca.read_text(encoding="utf-8").strip().replace("Z", "+00:00"))
    except (FileNotFoundError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _apagar(marca: Path | None) -> None:
    if marca is not None:
        try:
            marca.unlink()
        except FileNotFoundError:
            pass


def decidir(pasta: Path | None, agora: datetime, limite: timedelta = LIMITE) -> tuple[int, str]:
    """(saída, o porquê). 1 = esperar; 0 = pode reiniciar. A marca da 1ª espera nasce na 1ª vez que há lote aberto e some
    quando não há mais, ou quando os 10 min passam (a próxima gravação aberta ganha os 10 min dela)."""
    from nexus.pcm.inventario import gravacao as G
    abertas = G.com_lote_aberto(pasta, agora)
    marca = pasta / MARCA if pasta is not None else None
    if not abertas:
        _apagar(marca)
        return 0, "nenhuma gravação do inventário com lote aberto no Fracttal: pode reiniciar"
    desde = _ler_marca(marca) if marca is not None else None
    if desde is None:
        desde = agora
        if marca is not None:
            marca.parent.mkdir(parents=True, exist_ok=True)
            marca.write_text(agora.astimezone(timezone.utc).isoformat(), encoding="utf-8")
    if agora - desde < limite:
        falta = int((limite - (agora - desde)).total_seconds() // 60) + 1
        return 1, (f"{len(abertas)} gravação(ões) do inventário com lote aberto no Fracttal: o restart espera o lote fechar "
                   f"(no máximo mais {falta} min)")
    _apagar(marca)
    return 0, "a gravação do inventário segue com lote aberto há 10 min: reinicia assim mesmo"


def main(argv=None, *, cfg=None, agora: datetime | None = None) -> int:
    try:
        if str(RAIZ) not in sys.path:
            sys.path.insert(0, str(RAIZ))
        from nexus.pcm.inventario import gravacao as G
        if cfg is None:
            from nexus.config import ler_ambiente
            cfg = ler_ambiente()
        codigo, porque = decidir(G._pasta(cfg), agora or datetime.now(timezone.utc))
    except Exception as ex:      # noqa: BLE001 — o deploy nunca fica preso aqui
        print(f"gravacao_aberta: não consegui saber ({type(ex).__name__}): pode reiniciar", file=sys.stderr)
        return 0
    if codigo == 1:
        print(ESPERAR)
    print(f"gravacao_aberta: {porque}", file=sys.stderr)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
