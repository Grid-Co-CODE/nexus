"""As fotos da ronda na barra lateral (Levi, 05/11/2026: "Ao clicar na ronda tire esse 'demais fotos' quero tudo
expandido"; "O texto não está encaixando onde deveria encaixar, conserte!"): na barra, o cartão com legenda era forçado a
ficar quadrado (o `aspect-ratio:1` das miniaturas maiores), a foto ficava com 96 px, a legenda embaixo e um vão; a
etiqueta da resposta ("limpo"), presa a 24 px do fim do cartão, caía em cima da legenda. Agora a etiqueta mora na
própria foto e o cartão é a foto quadrada mais a legenda."""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")


def _regra(seletor):
    m = re.search(re.escape(seletor) + r"\{([^}]*)\}", CSS)
    assert m, seletor
    return m.group(1)


def test_a_etiqueta_fica_na_foto_e_a_legenda_embaixo():
    assert "position:relative" in _regra(".cn-foto-img") and "display:block" in _regra(".cn-foto-img")
    assert "bottom:4px" in _regra(".cn-foto--legenda .cn-foto-resp")
    assert "height:auto" in _regra(".cn-foto--legenda")


def test_na_barra_lateral_a_foto_e_quadrada_e_o_cartao_cresce_com_a_legenda():
    assert "aspect-ratio:auto" in _regra(".rg-fotos .cn-foto--legenda")
    img = _regra(".rg-fotos .cn-foto--legenda img")
    assert "height:auto" in img and "aspect-ratio:1" in img


def test_a_legenda_nao_sai_sublinhada():
    assert "text-decoration:none" in _regra(".cn-foto")
