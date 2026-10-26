"""Torre Base: Cadastros e integrações que sustentam todo o resto.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/registro-mestre")
    def registro_mestre():
        return render_template("base/registro-mestre.html")
"""
from ...auth.chaves import aba_nexus, registrar_chaves
from ...auth.telas_acessos import registrar_acessos
from ...casca.raio_x import registrar_raio_x
from ...cadastro.telas import registrar_base
from ...cadastro.telas_equipamentos import registrar_equipamentos
from ...cadastro.telas_fracttal import registrar_fracttal
from ...cadastro.telas_ligacoes import registrar_ligacoes
from ...dados.telas import registrar_governanca
from ..modelo import Tela, Torre
from ..moldura import registrar_molduras

TORRE = Torre(
    id="base",
    nome="Base",
    ordem=110,
    icone="database",
    descricao="Cadastros e integrações que sustentam todo o resto.",
    telas=[
        # Cadastro: o BD_Operações fora da planilha (29/09/2026). As views moram em nexus/cadastro/telas.py.
        Tela("registro-mestre", "Registro mestre",
             "Quais usinas operamos, de quem, com que equipe e contrato?",
             "Cadastro do Nexus (antes: aba Operações do BD_Operações)"),
        Tela("clientes", "Clientes",
             "Quais clientes temos e quais usinas são de cada um?",
             "Cadastro do Nexus (antes: coluna CLIENTE da aba Operações)"),
        Tela("equipes", "Equipes",
             "Quem trabalha em cada equipe e em quais usinas?",
             "Cadastro do Nexus (antes: Equipe Cluster do BD_Operações)"),
        # Equipamentos das usinas (13/10/2026, Levi: "Temos que substituir a aba equipamentos aproveitando o que tem lá e
        # usando o Nexus como ponto de partida"): a usina ligada, à mão, ao Fracttal e às chaves do supervisório, e as
        # cabines, inversores, strings e potência dela. A view mora em nexus/cadastro/telas_equipamentos.py; só administrador.
        Tela("equipamentos", "Equipamentos das usinas",
             "Que nome a usina tem no Fracttal e no supervisório, e quais cabines, inversores e strings ela tem?",
             "Registro mestre, as Ligações (Fracttal) e o livro nexus_estrutura_usina; a aba Equipamentos só como "
             "referência; só administrador"),
        # Estrutura de O&M de 10/2026 (Levi, 08/10: "pode adaptar, deixa as vagas preparadas")
        Tela("regioes-campo", "Regiões de campo",
             "Quem é o Supervisor de Campo de cada região, que equipes ela tem e onde a vaga está aberta?",
             "Cadastro do Nexus (estrutura de O&M de 10/2026)"),
        # "Listas" saiu em 11/10/2026 (Levi: "pode tirar listas pois a governança faz mais sentido"): o endereço
        # /t/base/listas leva à Governança de dados (nexus/cadastro/telas.py); os valores das listas ficam no cadastro.
        # "Importar do Excel" saiu em 14/10/2026 (Levi: "Tire 'Importar do Excel' do módulo base"): o endereço
        # /t/base/importar leva ao Registro mestre (nexus/cadastro/telas.py); a importação do BD_Operações segue por
        # comando (nexus/cadastro/CLAUDE.md, "Importar o BD_Operações").
        # Governança de dados (05/10/2026, Levi: "prioridade 0"): a matriz de barramento e a qualidade da ligação por ID.
        # Desde 11/10/2026 traz no fim a seção Ligações entre bases (era a tela /t/base/ligacoes, que redireciona para lá).
        Tela("governanca", "Governança de dados",
             "Que dado temos, de onde vem, o que é cada linha e quanto dele liga por ID?",
             "Catálogo do Nexus (nexus/dados) e nexus_fatos · qualidade no banco"),
        Tela("qualidade", "Qualidade do cadastro",
             "O que o Excel deixava passar calado?",
             "Cadastro do Nexus"),
        # Porta única (09/10/2026): o /tokens da Plataforma de Performance (as chaves de SunOp, Axis e Plataforma) numa
        # moldura; só administrador do Nexus (spec 5.3). A view sai do mapa (nexus/performance/porta.py).
        Tela("chaves-fontes", "Chaves das fontes",
             "As chaves das fontes da Performance estão válidas, e quando vencem?",
             "Plataforma de Performance (/tokens), só administrador"),
        # As Chaves do Nexus (14/10/2026, nexus/auth/chaves.py) moram aqui, na aba "Nexus" (`?aba=nexus`): Levi, "bote
        # essa informação na seção Chave das fontes!". O endereço /t/base/chaves-nexus leva a ela.
        # Fontes do tempo real (11/10/2026): quais usinas de cada fonte entram no tempo real (e são coletadas), e as novas
        # esperando liberação. A tela é da plataforma (/admin/tempo-real), numa moldura; só administrador.
        Tela("fontes-tempo-real", "Fontes do tempo real",
             "Quais usinas de cada fonte entram no tempo real, e quais estão esperando liberação?",
             "Plataforma de Performance (/admin/tempo-real) e o livro nexus_tempo_real no banco, só administrador"),
        # De-para de equipamentos (11/10/2026): como cada usina de cada fonte se liga ao cadastro, e o editor (a ponte da
        # usina pelo id, o nome de cada inversor, a sugestão pelo kWh). A tela é da plataforma (/admin/de-para), numa
        # moldura; grava no livro nexus_depara; só administrador.
        Tela("de-para-equipamentos", "De-para de equipamentos",
             "Ligar cada usina e cada inversor de cada fonte ao cadastro, com a sugestão pelo kWh do BD",
             "Plataforma de Performance (/admin/de-para) e o livro nexus_depara no banco, só administrador"),
        # Acessos (11/10/2026: "Tem algum canto do Nexus onde eu posso administrar isso?"): quem é administrador, dar e
        # tirar pela tela, e quem entrou em 30 dias. Só administrador. A view e as regras moram em nexus/auth/. Desde
        # 25/10/2026 a aba Pessoas e setores (`?aba=pessoas`) é a antiga Integração Fracttal
        # (nexus/cadastro/telas_fracttal.py; /t/base/fracttal leva a ela): o pessoal do Fracttal e o setor de cada um.
        Tela("acessos", "Acessos",
             "O que cada setor vê, quem é administrador, quem entrou em 30 dias e o setor de cada pessoa do Fracttal",
             "NEXUS_ADMINS do servidor, a lista da tela, a API do Fracttal (pessoal) e o livro nexus_setores; só administrador"),
        Tela("ia", "Nexus IA",
             "O que a IA leu e sugeriu, e quanto custou?",
             "API do Claude (a definir)"),
        Tela("notificacoes", "Notificações",
             "Que evento avisa quem, por qual canal?",
             "Regras de notificação do Nexus"),
        Tela("estrutura", "Estrutura R02",
             "Quais torres, processos e KPIs compõem o book?",
             "Estrutura O&M (book R02)"),
        Tela("como-usar", "Como usar o Nexus",
             "Como cada tela responde à minha rotina?",
             "Textos de ajuda por tela"),
        Tela("roadmap", "Visão e roadmap",
             "Por que o Nexus existe e em que fase está?",
             "Specs R00 a R13"),
    ],
)

bp = TORRE.criar_blueprint(__name__)
registrar_base(bp)
registrar_equipamentos(bp)
registrar_fracttal(bp)
registrar_ligacoes(bp)
registrar_governanca(bp)
registrar_acessos(bp)
registrar_chaves(bp)
registrar_raio_x(bp)        # /t/base/raio-x: o que o processo faz agora (14/10/2026), só administrador, fora do menu
registrar_molduras(bp, TORRE, abas={"chaves-fontes": {"primeira": "Fontes da Performance",
                                                         "outras": [("nexus", "Nexus", aba_nexus)]}})
