# De onde veio o `radar.html`

É o app do Radar de Fornecedores (a plataforma de zeladoria), versão `f0b4cac`, a mesma que estava no ar em 28/10/2026.
Veio no pacote que o Levi recebeu nessa data (`public/index.html`). Desenho:
`docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md`.

**Não edite à mão antes do congelamento.** O arquivo sai do `ferramentas/zeladoria_limpar_clone.py`. Depois que o Radar
congelar (fim da etapa 2), este arquivo passa a ser a casa da zeladoria e se edita direto, como o OS Creator desde
31/10.

## O que a ferramenta trocou

- **Os nomes de colegas viraram o papel:**
  - o primeiro aprovador (colunas `status_analista`) é o Analista;
  - o segundo (`status_head`) é o Head;
  - o supervisor da equipe primarizada é a Equipe. Por isso `rf_gastos_<nome>` é `rf_gastos_equipe` aqui e no Nexus
    (`nexus/zeladoria/tabelas.py`).

  O de-para com os nomes fica fora do repositório, que é público: `Downloads\Deploy\radar_2026-10-28\de_para_nomes.json`
  no PC do Levi.
- **O Supabase saiu:** o endereço, a chave e o carregador das CDNs. No lugar do carregador ficou
  `<!--ZELADORIA:PONTE-->`, onde a torre põe a ponte (`nexus/static/zeladoria/ponte.js`). No `<head>` ficou
  `<!--ZELADORIA:CONFIG-->`, para a configuração.
- **A aba inicial** vem do menu do Nexus (`window.ZELADORIA_ABA`).
- **O e-mail de exemplo do login** virou `voce@empresa.com.br`.

## Rodar de novo

Para trazer o que o time do Radar mudou até o congelamento:

```
python -I ferramentas/zeladoria_limpar_clone.py --origem <index.html novo> --nomes <de_para_nomes.json> --saida nexus/torres/zeladoria/clone/radar.html
```

A ferramenta para, sem gravar nada, se alguma troca não casar exatamente uma vez ou se sobrar nome. Depois, rode
`python -m pytest tests/test_zeladoria_clone.py tests/test_sem_nomes_no_repositorio.py -q`, com o `.env`.
