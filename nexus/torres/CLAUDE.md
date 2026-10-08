# CLAUDE.md — torres (uma pasta por área do menu)

Cada pasta em `nexus/torres/` é uma torre do menu lateral. Torre com regra própria tem o seu `CLAUDE.md` (ou
`README.md`) na pasta: **leia antes de mexer**.

| Torre | Estado | Onde está a regra |
|---|---|---|
| `cos/` | em construção pelo dev do COS | `cos/CLAUDE.md` |
| `oscreator/` | clone do OS Creator Web servido em `/os/*` | `oscreator/README.md` |
| `performance/` | Tempo real = plataforma pela ponte, só leitura; Clima e risco = alertas públicos por usina (INMET e INPE), só leitura; as outras telas placeholder | `nexus/performance/CLAUDE.md` |
| `pcm/` | telas da programação semanal e a Gestão PCM (Plano & Fila das manutenções, do painel do PCM) | `nexus/pcm/CLAUDE.md` (o código mora em `nexus/pcm/`) |
| `base/`, `pessoas/` | telas do cadastro (BD_Operações); Base → Governança de dados é da camada de dados | `nexus/cadastro/CLAUDE.md`, `nexus/dados/CLAUDE.md` |
| `campo/` | Visão do Nexus sobre o campo, sem Azure nem moldura: Atenção, PT, Rondas e Zeladoria são contas nossas (`nexus/campo/visao.py`); Aprovação e Triagem usam as regras copiadas do App; tudo pelos livros que o App grava no banco (Ordens, Imagens e Ranking saíram em 08/10/2026) | `campo/CLAUDE.md` |
| as demais | só placeholder | — |

## Como funciona

- `__init__.py` da torre declara `TORRE` (`modelo.Torre` com as `Tela`s) e `bp = TORRE.criar_blueprint(__name__)`.
  `nexus/torres/__init__.py` descobre a pasta sozinho (`pkgutil`); não há lista para editar.
- Toda tela nasce como placeholder genérico. **Para construir uma tela**, crie a view no `bp` da torre com a mesma
  rota (`@bp.route("/mesa")`): a específica vence o placeholder, e a tela fica verde no menu sozinha.
- Templates em `nexus/torres/<torre>/templates/<torre>/`.
- **Abrir uma OS do Fracttal em qualquer tela** (os setores se conversam, Levi 08/10/2026): o card do Histórico do OS
  Creator, sem cópia. `{% include "oscreator/card_os_abrir.html" %}` e `NexusOsCard.abrir(id_work_order, {status})`;
  regra em `oscreator/README.md` ("O card da OS em qualquer torre"). Quem usa: o Quadro da equipe da Engenharia.
- `montar_menu` põe a torre da cadeira escolhida primeiro.
- O módulo-modelo chama `modelo.py`, não `base.py`: `base` colidia com o pacote da torre Base.
