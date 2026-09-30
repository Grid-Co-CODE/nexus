# Casca do Nexus · Plano de implementação

> **Para agentes:** executar tarefa a tarefa (superpowers:executing-plans). Passos com `- [ ]`.

**Objetivo:** casca Flask do Nexus com login por senha, menu por torre reordenado pela cadeira e telas placeholder.
**Arquitetura:** app factory; um Blueprint por torre descoberto por varredura de pasta; portão de login em `before_request`.
**Stack:** Python 3.14, Flask 3.1.3, python-dotenv 1.2.2, pytest.
**Spec:** `docs/superpowers/specs/2026-09-29-casca-nexus-design.md`

## Restrições globais

- pt-BR em tudo, inclusive comentários; sem emoji na interface; tema escuro navy (tokens `gc-*`), nunca lilás.
- Nenhum segredo no git; `.env` ao lado do `app.py`.
- Porta 5070.
- Nenhuma leitura de Excel ou OneDrive.

---

### Tarefa 1: Configuração e boot

**Arquivos:** `nexus/__init__.py`, `nexus/config.py`, `app.py`, `.env.example`, `.gitignore`, `requirements.txt`, `tests/conftest.py`, `tests/test_config.py`

**Interfaces:** `carregar_config(env: Mapping[str,str] | None = None) -> dict` levanta `ConfigErro` com o nome da variável faltante; `create_app(config: dict | None = None) -> Flask`.

- [ ] Teste: `carregar_config({})` levanta `ConfigErro` citando `NEXUS_SECRET_KEY`; com as duas variáveis devolve o dict.
- [ ] Implementar `config.py` (lê `.env` pelo caminho absoluto do `app.py`, `OBRIGATORIAS = ("NEXUS_SECRET_KEY", "NEXUS_SENHA_ADMIN")`).
- [ ] `create_app` registra cookie seguro, 12 h de sessão, blueprints (tarefas 2 a 4).
- [ ] `pytest -q` verde.

### Tarefa 2: Portão de login

**Arquivos:** `nexus/auth/__init__.py`, `nexus/templates/entrar.html`, `tests/test_auth.py`

**Interfaces:** Blueprint `auth` com `entrar` (GET/POST) e `sair`; `instalar_portao(app)`; `ROTAS_PUBLICAS = {"auth.entrar", "casca.saude", "static"}`; `next_seguro(valor: str | None) -> str`.

- [ ] Testes: percorrer `app.url_map` e exigir 302 para `/entrar` em toda rota não pública; senha errada não loga; 6ª tentativa errada do mesmo IP recebe 429; `next=https://mal.com` cai em `/`; senha certa loga e respeita `next=/t/cos/mesa`.
- [ ] Implementar com `hmac.compare_digest` e janela de 15 min / 5 erros por IP.
- [ ] `pytest -q` verde.

### Tarefa 3: Torres e cadeiras

**Arquivos:** `nexus/cadeiras.py`, `nexus/torres/__init__.py`, `nexus/torres/modelo.py`, `nexus/torres/<12 pastas>/__init__.py`, `tests/test_torres.py`

**Interfaces:** `Tela(id, nome, pergunta, fonte)`, `Torre(id, nome, ordem, telas, icone)`; `Torre.criar_blueprint() -> Blueprint` com rota `/t/<torre>/<tela>` para as telas sem view própria; `descobrir_torres() -> list[Torre]`; `CADEIRAS: dict[str, Cadeira]` com `Cadeira(id, nome, torre_inicial)`; `montar_menu(torres, cadeira_id, torre_atual) -> list[dict]`.

- [ ] Testes: 12 torres descobertas; toda tela do catálogo responde 200 logado; toda `torre_inicial` de cadeira existe; `montar_menu(..., "cos", None)` devolve Início e depois COS expandida e marcada como "sua".
- [ ] Implementar as 12 pastas com as telas da seção 7 da spec.
- [ ] `pytest -q` verde.

### Tarefa 4: Casca (layout, Início, cadeira, saúde)

**Arquivos:** `nexus/casca/__init__.py`, `nexus/templates/base.html`, `nexus/templates/inicio.html`, `nexus/templates/tela.html`, `nexus/static/nexus.css`, `nexus/static/grid-h-branco.png`, `tests/test_casca.py`

**Interfaces:** Blueprint `casca` com `inicio` (`/`), `cadeira` (POST `/cadeira`), `saude` (`/saude`); `context_processor` injeta `menu`, `cadeira`, `cadeiras`.

- [ ] Testes: `/saude` sem sessão devolve só `ok` e `commit`; `POST /cadeira` com id inexistente devolve 400; com `cos` grava na sessão e o menu muda.
- [ ] Implementar layout com os tokens da seção 9 da spec.
- [ ] `pytest -q` verde.

### Tarefa 5: Documentação e verificação

**Arquivos:** `CLAUDE.md`, `README.md`

- [ ] `CLAUDE.md` com convenções e como criar uma torre.
- [ ] Subir local (5070), entrar, trocar cadeira, abrir uma tela de cada torre, conferir celular (375 px), console sem erro.
