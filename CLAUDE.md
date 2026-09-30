# CLAUDE.md — Nexus

Casca única da operação O&M da Grid Co. (specs de produto R00 a R13 do Fillipe Figueiró, no SharePoint
`Gridco/4. O&M/6.Gerencial/10. Nexus`). Responsável: Levi Maia. Repositório **privado**
(`Grid-Co-CODE/nexus`): tem, e vai ter mais, dado de cliente e de contrato.

Desenho da fase atual: `docs/superpowers/specs/2026-09-29-casca-nexus-design.md`.

## Rodar

```
copie .env.example para .env e preencha
python app.py                 -> http://localhost:5070
python -m pytest -q
```

Sem o `.env` completo o app não sobe, e diz qual variável falta.

## Como o código está organizado

- `nexus/torres/<torre>/__init__.py` — uma pasta por torre. Declara `TORRE` e `bp`; é descoberta sozinha.
  **Para construir uma tela**, crie uma view no `bp` da torre com a mesma rota da tela
  (`@bp.route("/mesa")`); ela vence o placeholder. Templates da torre em `nexus/torres/<torre>/templates/<torre>/`.
- `nexus/torres/oscreator/` — além da torre, traz o **clone do OS Creator Web** (cópia do `oem`) e a ponte
  `/os/*` (`ponte.py`), a única rota fora de `/t/<torre>`. Leia o `README.md` de lá antes de mexer: o clone fica
  idêntico ao do oem de propósito.
- `nexus/auth/` — o portão de login. Toda rota exige sessão, exceto as de `ROTAS_PUBLICAS`.
  Rota pública nova entra ali, conscientemente; o teste `test_toda_rota_nao_publica_exige_login` pega o esquecimento.
- `nexus/cadeiras.py` — catálogo de cadeiras. Cadeira nova no fim; id publicado nunca muda.
- `nexus/casca/` — Início, troca de cadeira, `/saude`, contexto dos templates (menu).
- `nexus/static/nexus.css` — tokens do Design System Grid Co., tema escuro.

## Regras

- **Origem de dado:** nada de Excel nem OneDrive. Dado vem da API `db_performace` (PostgreSQL da T.I.).
  A API é compartilhada por vários sistemas: nada que identifique pessoa vai para ela em claro
  (cifrado ou como HMAC).
- **Sempre pt-BR**, inclusive comentários. **Sem emoji na interface**; severidade por cor e palavra.
- Tema escuro **navy** (`#090d18` / `#161d30`) + verde Grid. Nunca lilás (o `#191528` do mockup não entra).
- Comentário de código explica **por quê**, de preferência com o caso real que motivou a regra.
- **Segredos** só no `.env` (gitignorado). Nunca imprima `NEXUS_SENHA_ADMIN` nem `NEXUS_SECRET_KEY`,
  nunca desligue o portão de login. Para validar tela atrás da senha, faça login por sessão lendo o `.env`.
- Commit só quando pedido. Quando houver deploy automático, push na `main` vai para produção.
- Antes de dar algo por pronto: testes passando e a tela conferida no navegador (desktop e 375 px).
