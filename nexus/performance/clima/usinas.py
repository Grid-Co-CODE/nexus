"""As usinas do Clima e risco: as em operação, com a coordenada do cadastro do Nexus (06/10/2026).

A latitude e a longitude são campos sensíveis do cadastro: ficam cifradas (AES-GCM) no armazém e só se abrem aqui, no
processo do Nexus, com a `NEXUS_CHAVE_CADASTRO`. Elas alimentam as três fontes e NUNCA vão para a tela, para o log nem
para o `repr` (os campos `lat` e `lon` ficam fora do `repr`: um `print(usina)` esquecido não vaza coordenada).

Usina em operação sem coordenada utilizável nunca some: cai em `sem_coordenada` (vazia, marcador "N/A" ou texto herdado
do Excel) ou em `fora_do_brasil` (0, 0 e latitude e longitude trocadas são os erros de digitação que aparecem), e a tela
as lista, para alguém corrigir o cadastro.
"""
import math
from dataclasses import dataclass, field

from flask import current_app

from ...cadastro.servico import chave_texto
from ...cadastro.telas import SemCadastro, servico

__all__ = ["Cadastro", "SEM_CLIENTE", "SemCadastro", "Usina", "carregar", "do_app"]

SEM_CLIENTE = "Sem cliente"
# O Brasil com folga (as ilhas oceânicas entram); fora disto, a coordenada é erro de digitação, não usina.
LAT_BRASIL = (-35.0, 6.0)
LON_BRASIL = (-75.0, -28.0)


@dataclass(frozen=True)
class Usina:
    id: str
    nome: str
    cliente: str
    uf: str = ""
    cidade: str = ""
    lat: float | None = field(default=None, repr=False)
    lon: float | None = field(default=None, repr=False)


@dataclass
class Cadastro:
    usinas: list                      # em operação, com coordenada dentro do Brasil
    sem_coordenada: list              # em operação, sem coordenada utilizável
    fora_do_brasil: list              # em operação, com coordenada fora do Brasil (0, 0; lat e lon trocados)
    em_operacao: int                  # as três listas juntas
    ilegiveis: int = 0                # fichas que não abriram (a cifra não confere com a chave)

    def pontos(self) -> list:
        """[(id, lat, lon)] para as fontes."""
        return [(u.id, u.lat, u.lon) for u in self.usinas]

    def clientes(self) -> list:
        """Os clientes das usinas do mapa, sem repetir, em ordem; "Sem cliente" por último."""
        nomes = {u.cliente for u in self.usinas}
        return sorted(nomes - {SEM_CLIENTE}, key=chave_texto) + ([SEM_CLIENTE] if SEM_CLIENTE in nomes else [])


def _numero(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _texto(v) -> str:
    return str(v).strip() if v is not None else ""


def carregar(srv) -> Cadastro:
    """Lê as usinas em operação do serviço do cadastro (`nexus.cadastro.servico.Servico`)."""
    com, sem, fora, ilegiveis, em_operacao = [], [], [], 0, 0
    for r in srv.registros("usinas"):
        if r.ilegivel:
            ilegiveis += 1
            continue
        if chave_texto(r.valores.get("status")) != "operacao":
            continue
        em_operacao += 1
        lat, lon = _numero(r.valores.get("latitude")), _numero(r.valores.get("longitude"))
        usina = Usina(id=str(r.id), nome=_texto(r.valor("nome")) or str(r.id),
                      cliente=_texto(srv.titulo_de("clientes", r.valor("cliente"))) or SEM_CLIENTE,
                      uf=_texto(r.valores.get("uf")), cidade=_texto(r.valores.get("cidade")), lat=lat, lon=lon)
        if lat is None or lon is None:
            sem.append(usina)
        elif LAT_BRASIL[0] <= lat <= LAT_BRASIL[1] and LON_BRASIL[0] <= lon <= LON_BRASIL[1]:
            com.append(usina)
        else:
            fora.append(usina)
    return Cadastro(com, sem, fora, em_operacao, ilegiveis)


def do_app() -> Cadastro:
    """O cadastro do app em curso (precisa de contexto de requisição). Levanta SemCadastro, com o que falta, se não dá para abrir."""
    app = current_app
    if "nexus_cadastro" not in app.extensions:
        if not app.config.get("NEXUS_CHAVE_CADASTRO"):
            raise SemCadastro("Falta a variável NEXUS_CHAVE_CADASTRO no .env do Nexus.")
        # Teste que não diz onde está o cadastro dele não pode cair no arquivo de verdade, com as coordenadas reais
        # (o mesmo cuidado de `ligacoes.pasta_dados`, que recusa gravar na pasta real em TESTING).
        if app.config.get("TESTING") and not app.config.get("NEXUS_ARMAZEM_LOCAL"):
            raise SemCadastro("teste sem NEXUS_ARMAZEM_LOCAL: recuso ler o cadastro de verdade")
    srv = servico()
    if not srv.armazem.existe:
        raise SemCadastro("o cadastro não está nesta máquina (falta o arquivo do armazém local)")
    return carregar(srv)
