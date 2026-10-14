"""Os quatro relatórios do PCM no Nexus (14/10/2026): Relatório diário de manutenção, Recuperação da tarde, Fechamento
da semana e Alerta da programação. Regras e porquês no CLAUDE.md desta pasta.

`TIPOS` é a lista que a Central, a tela e a emissão automática usam; `emitir` gera a folha de um tipo.
"""
from dataclasses import dataclass
from datetime import date, datetime

from . import alerta, dados, diario, fechamento, tarde


@dataclass(frozen=True)
class Tipo:
    id: str            # o do arquivo e do endereço: /t/relatorios/pcm-<id>
    letra: str         # a marca do item no bloco "Relatórios Padrão PCM" (a do "1 · Tipo" do painel do PCM)
    nome: str
    descricao: str     # a linha de baixo da lista, a mesma do painel
    por: str           # "dia" ou "semana": o que se escolhe para emitir
    pergunta: str      # a do cartão da Central

    @property
    def tela_id(self) -> str:
        return f"pcm-{self.id}"


TIPOS = {t.id: t for t in (
    Tipo("diario", "D", "Relatório diário de manutenção", "o que aconteceu num dia · 2 páginas · automático às 06:00", "dia",
         "O que aconteceu ontem na manutenção: aderência, não programadas, religamentos e backlog?"),
    Tipo("tarde", "T", "Recuperação da tarde",
         "programado para a manhã e ainda aberto · 1 página · automático às 13:00", "dia",
         "O que estava na manhã de hoje, ainda está aberto e precisa ser recuperado à tarde?"),
    Tipo("semanal", "S", "Fechamento da semana", "aderência, tendência e temas críticos · 2 páginas · sexta 17:00",
         "semana", "Como fechou a semana: aderência, rolagens, reincidentes e o que não coube?"),
    Tipo("alerta", "A", "Alerta da programação", "17 checagens da semana publicada · ao publicar", "semana",
         "A semana publicada é viável antes de ir para o campo (17 checagens)?"),
)}


def emitir(entradas, tipo: str, ref: str, gerado: datetime, cliente: str = "", grupo: str = ""):
    """A folha de `tipo` para `ref` (AAAA-MM-DD ou AAAA-Wnn): {"html", "titulo", "resumo", "avisos"} ou None quando o
    banco não tem a semana. Com cliente/grupo, as entradas saem recortadas (`dados.recortar`)."""
    ent = dados.recortar(entradas, cliente, grupo)
    recorte = ent.get("recorte")
    if tipo == "diario":
        return diario.gerar(ent, date.fromisoformat(ref), gerado, recorte)
    if tipo == "tarde":
        return tarde.gerar(ent, date.fromisoformat(ref), gerado, recorte)
    if tipo == "semanal":
        return fechamento.gerar(ent, ref, gerado, recorte)
    if tipo == "alerta":
        return alerta.gerar(ent, ref, gerado, recorte)
    raise ValueError(f"tipo de relatório desconhecido: {tipo!r}")
