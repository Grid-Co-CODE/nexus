# CLAUDE.md — torres (uma pasta por área do menu)

Cada pasta em `nexus/torres/` é uma torre do menu lateral. Torre com regra própria tem o seu `CLAUDE.md` (ou
`README.md`) na pasta: **leia antes de mexer**.

| Torre | Estado | Onde está a regra |
|---|---|---|
| `cos/` | em construção pelo dev do COS | `cos/CLAUDE.md` |
| `oscreator/` | clone do OS Creator Web servido em `/os/*` | `oscreator/README.md` |
| `performance/` | Tempo real = plataforma pela ponte, só leitura; as outras telas placeholder | `nexus/performance/CLAUDE.md` |
| `pcm/` | telas da programação semanal | `nexus/pcm/CLAUDE.md` (o código mora em `nexus/pcm/`) |
| `base/`, `pessoas/` | telas do cadastro (BD_Operações) | `nexus/cadastro/CLAUDE.md` |
| as demais | só placeholder | — |

## Como funciona

- `__init__.py` da torre declara `TORRE` (`modelo.Torre` com as `Tela`s) e `bp = TORRE.criar_blueprint(__name__)`.
  `nexus/torres/__init__.py` descobre a pasta sozinho (`pkgutil`); não há lista para editar.
- Toda tela nasce como placeholder genérico. **Para construir uma tela**, crie a view no `bp` da torre com a mesma
  rota (`@bp.route("/mesa")`): a específica vence o placeholder.
- Templates em `nexus/torres/<torre>/templates/<torre>/`.
- `montar_menu` põe a torre da cadeira escolhida primeiro.
- O módulo-modelo chama `modelo.py`, não `base.py`: `base` colidia com o pacote da torre Base.
