# De onde veio o `radar.html`

É o app do Radar de Fornecedores (a plataforma de zeladoria) como estava no ar em 11/11/2026, o último dia dele (baixado
de zeladoria.gridco.com.br; a 1ª versão foi a `f0b4cac`, do pacote de 28/10/2026, e a de 06/11 trouxe o painel dos
contratos por cliente, os PDFs dos contratos e a consulta da OS no Fracttal). O Radar original de cada versão fica fora
do repositório, em `Downloads\Deploy\radar_<data>`. Desenho: `docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md`.

**Congelado em 11/11/2026:** o Supabase do Radar parou (a cota estourou, e os pedidos são recusados até 10/12), e o Radar
parou junto. Desde então este arquivo é a casa da zeladoria e **se edita direto**, como o OS Creator desde 31/10 (quem
programa: o HEAD da zeladoria; ver "Como entregar" no `CLAUDE.md` da torre). A ferramenta abaixo fica como registro.

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
- **O visual da Zeladoria (etapa 3):** a paleta com as três cores, as fontes do Nexus, as cores fixas viradas variável, sem emoji, o tema vindo do Nexus e as regras de tela estreita (`vestir`).

## Rodar de novo

Só se o Radar voltar a ser editado fora do Nexus (depois de 11/11 não há por quê; editar o clone direto e depois rodar a
ferramenta apaga o que foi editado). Para trazer o que o time do Radar mudou:

```
python -I ferramentas/zeladoria_limpar_clone.py --origem <index.html novo> --nomes <de_para_nomes.json> --saida nexus/torres/zeladoria/clone/radar.html
```

A ferramenta para, sem gravar nada, se alguma troca não casar exatamente uma vez ou se sobrar nome. Depois, rode
`python -m pytest tests/test_zeladoria_clone.py tests/test_sem_nomes_no_repositorio.py -q`, com o `.env`.
