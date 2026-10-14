"""Torre Relatórios: Emissão dos relatórios diários, semanais e mensais.

A Central de emissão (13/10/2026). Levi: "Criador de relatório e relatório semanal vai para a central de emissão no Nexus >
Relatórios. Ficará filtrado no setor da pessoa, caso a pessoa seja administradora aparece todos os relatórios. Aí a pessoa
escolhe que tipo de relatório ela quer! Sai da parte de Performance!"

- Cada relatório é uma tela desta torre que se abre POR DENTRO da Central (`Tela.dentro_de`): sem item próprio no menu,
  ele acende a Central quando está aberto. Os da Plataforma de Performance abrem na moldura, pelo mapa da porta única
  (`nexus/performance/porta.py`, torre "relatorios"; as views saem de `registrar_molduras`).
- O filtro do setor: cada relatório é DO setor dono (`Tela.do_setor`; os três de hoje são da Performance, Levi,
  13/10/2026: "Potência ativa faz parte da performance!" e "Esses dois são do setor performance"), e quem é do setor o
  vê sem marcar; outro setor vê o que for marcado para ele em Base → Acessos (`auth/setor_telas.py`); o administrador vê
  todos. Quem tem um relatório vê a Central (a tela de fora) sem marcá-la. As marcas de antes, quando os relatórios eram
  da Performance (`performance/relatorio`...), valem para os daqui (`setor_telas.RENOMEADAS`).
- Relatório novo: uma `Tela(..., dentro_de="central", do_setor="<setor dono>")` aqui e o ícone em RELATORIOS.
- Os quatro do PCM (14/10/2026, Levi: "Quero trazer esses quatro relatórios para a plataforma, com as mesmas métricas e
  parâmetros e estilos"): Relatório diário de manutenção, Recuperação da tarde, Fechamento da semana e Alerta da
  programação, do setor PCM, NATIVOS do Nexus (não da plataforma): as telas e a folha em `nexus/pcm/relatorios`
  (`telas.registrar`), com a emissão automática nos horários do PCM (`agenda.py`).
"""
from flask import render_template

from ...auth import setor_telas
from ...pcm.relatorios import TIPOS as TIPOS_PCM
from ...pcm.relatorios import telas as telas_pcm
from ...performance import porta
from ..modelo import Tela, Torre
from ..moldura import estado_da_porta, registrar_molduras

TORRE = Torre(
    id="relatorios",
    nome="Relatórios",
    ordem=70,
    icone="file-text",
    descricao="Emissão dos relatórios diários, semanais e mensais.",
    telas=[
        Tela("central", "Central de emissão",
             "Que relatório eu preciso emitir, e onde ele está?",
             "os relatórios liberados para o setor de quem entrou (todos, para o administrador)"),
        Tela("relatorio", "Criador de relatório",
             "Como monto o relatório do cliente com os números certos?",
             "Plataforma de Performance", dentro_de="central", do_setor="Performance"),
        Tela("relatorio-semanal", "Relatório semanal",
             "Como foi a semana de cada usina no relatório do cliente?",
             "Plataforma de Performance", dentro_de="central", do_setor="Performance"),
        Tela("potencia-ativa", "Potência Ativa dos Inversores",
             "Como a potência ativa de cada inversor se comportou, dia a dia?",
             "Plataforma de Performance (as leituras das curvas do Tempo real)", dentro_de="central",
             do_setor="Performance"),
        *[Tela(t.tela_id, t.nome, t.pergunta,
               "o robô do PCM: Programação Semanal, Gestão PCM, Gerencial e Confiabilidade", dentro_de="central",
               do_setor="PCM") for t in TIPOS_PCM.values()],
    ],
)

# O ícone (Phosphor) do cartão de cada relatório na Central; a área do cartão é o setor dono (`Tela.do_setor`)
RELATORIOS = {
    "relatorio": "file-text",
    "relatorio-semanal": "calendar-check",
    "potencia-ativa": "chart-line",
    "pcm-diario": "sun-horizon",
    "pcm-tarde": "clock-afternoon",
    "pcm-semanal": "calendar-check",
    "pcm-alerta": "warning",
}

bp = TORRE.criar_blueprint(__name__)


@bp.route("/central")
def central():
    """Os relatórios que a pessoa pode emitir: os do setor dela (todos, para o administrador), na ordem da torre."""
    liberadas = setor_telas.liberadas_do_menu()
    molduras = {t.tela for t in porta.da_torre(TORRE.id)}
    cartoes = [{"tela": t, "url": f"/t/{TORRE.id}/{t.id}", "area": t.do_setor, "icone": RELATORIOS.get(t.id, "file-text"),
                "moldura": t.id in molduras}
               for t in TORRE.telas
               if t.dentro_de == "central" and (liberadas is None or setor_telas.chave(TORRE.id, t.id) in liberadas)]
    estado = estado_da_porta()
    # o aviso da plataforma desligada é só dos relatórios dela (os do PCM são do Nexus e abrem sempre)
    return render_template("relatorios/central.html", torre=TORRE, tela=TORRE.tela("central"), cartoes=cartoes,
                           todos=liberadas is None, ligada=estado["ligada"], motivo=estado["motivo"],
                           com_moldura=any(c["moldura"] for c in cartoes))


# Os relatórios da Plataforma de Performance, cada um na moldura (porta única)
registrar_molduras(bp, TORRE)
# Os quatro do PCM, nativos (nexus/pcm/relatorios)
telas_pcm.registrar(bp, TORRE)
