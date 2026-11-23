"""Liga o laço do Insights de madrugada (19/11/2026) com o que só as telas do Comando sabem fazer: a lista das usinas
mobilizadas, o dossiê de cada uma (o MESMO da tela e da chamada direta) e os setores ativos. A regra da noite mora em
`nexus/comando/diagnostico_noite.py`."""


def ligar(app) -> None:
    from ...comando import diagnostico_noite as NT
    from . import _dossie, _setores_ativos, _usinas_montadas

    def usinas() -> list[int]:
        return [l["usina_id"] for l in _usinas_montadas().get("linhas") or [] if l.get("usina_id")]

    def dossie(usina_id: int):
        _ctx, dz = _dossie(usina_id)          # a usina fora da lista dá 404: a noite a marca "sem dossiê" e segue
        return dz["texto"], dz["tokens_estimados"]

    NT.ligar(app, usinas, dossie, _setores_ativos)
