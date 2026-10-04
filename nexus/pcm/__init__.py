"""Programação semanal do PCM dentro do Nexus (Levi, 30/09/2026: "quero passar toda a programação semanal e autonomia
para o projeto nexus ... não derruba a atual, quando eu ver que está funcional a gente substitui completamente").

Regra aqui, sem Flask (como o cadastro): `fonte` lê a programação, `semana` calcula o que as telas mostram. As telas
moram em `telas.py` e se penduram na torre PCM (nexus/torres/pcm).

Etapa 1 (esta): LER a programação que está valendo — o banco_dados.json que o App de Campo e o painel do PCM já
leem — e mostrá-la no layout do Nexus. Nada é gravado e nada muda no sistema atual. A geração pelo Nexus vem depois,
em sombra, comparada linha a linha com a do Fabrício antes de substituir qualquer coisa.
"""
