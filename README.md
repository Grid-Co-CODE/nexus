# Nexus

Ecossistema de Operação e Manutenção da Grid Co.: Performance, PCM, App de Campo, Fracttal e COS numa
casca só, organizada pelas torres da Estrutura O&M (book R02).

**Fase 0 (casca):** login por senha de admin, menu por torre que se reorganiza pela cadeira escolhida
e 68 telas em placeholder, cada uma dizendo a pergunta que vai responder e de onde virá o dado.

```
python -m pip install -r requirements.txt
cp .env.example .env    # e preencha
python app.py           # http://localhost:5070
python -m pytest -q
```

Convenções e como construir uma tela: [CLAUDE.md](CLAUDE.md).
