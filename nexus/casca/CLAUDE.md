# CLAUDE.md — casca (moldura, login e menu)

O que envolve todas as torres: o layout, o portão de login, a troca de cadeira e o `/saude`.

## Os arquivos

| Arquivo | O que faz |
|---|---|
| `nexus/__init__.py` | `create_app`: lê o `.env`, instala o portão e o contexto, descobre as torres |
| `nexus/config.py` | `OBRIGATORIAS` (sem elas o app não sobe e diz qual falta) e `OPCIONAIS` |
| `nexus/casca/__init__.py` | `/` (Início), `/cadeira` (troca), `/saude` (`{"commit", "ok"}`) e o contexto dos templates (menu) |
| `nexus/auth/__init__.py` | `/entrar`, `/sair` e o portão (`before_request`) |
| `nexus/cadeiras.py` | as 10 cadeiras; diretoria e chefia caem na torre Comando |
| `nexus/templates/base.html` | a moldura: menu lateral, recolher (`[` ou botão, lembrado em `localStorage` `nexus.menu`), menu do celular |
| `nexus/static/nexus.css` | tokens do Design System Grid Co. e o subconjunto `gc-*` |
| `app.py` / `servir.py` | desenvolvimento (5070, IPv4 e IPv6, cookie sem Secure) / produção (atrás do proxy, cookie Secure) |

## Regras que já custaram caro

- **Rota pública é decisão consciente:** só o que está em `ROTAS_PUBLICAS` (entrar, saude, static). O teste
  `test_toda_rota_nao_publica_exige_login` pega rota nova esquecida.
- **Limite de senha:** 5 erros em 15 min por IP, guardado em `app.extensions` (estado global vazava entre testes).
  Em produção o IP vem do `X-Forwarded-For` do proxy, por isso o `trusted_proxy` do `servir.py`.
- **`next_seguro`:** o `?next=` só aceita caminho interno; nada de `//site` nem URL completa.
- **`[hidden]{display:none!important}`** no CSS: um `display:flex` vencia o `hidden` e o filtro "não filtrava" (01/10).
  Visível se confere pela geometria (`getBoundingClientRect`), não pelo atributo.
- **`<html data-nexus>`** + script anti-moldura: o OS Creator embutido não pode abrir o Nexus dentro do iframe dele.
- **Servidor local some com a sessão do Claude que o subiu.** Para ficar no ar: `Iniciar Nexus.bat` (pythonw
  escondido, log em `logs/`) e `Parar Nexus.bat` (só o processo da porta 5070).
- Edge "localhost recusou": o waitress tem de escutar em `127.0.0.1` **e** `[::1]`.
