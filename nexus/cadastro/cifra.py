"""Cifra do dado sensível (AES-256-GCM) e selo da linha (HMAC-SHA256).

Por que cifrar: a API db_performace é compartilhada por vários sistemas e pessoas; dado pessoal só vai para lá cifrado.
CPF, telefone, endereço, receita e CNPJ só podem ir para lá cifrados. A cifra é amarrada ao CONTEXTO
(entidade/registro/campo) como dado associado: quem tem o token de escrita da API não consegue mover o CPF de
uma pessoa para a linha de outra, porque a decifração falha.

Por que selar: o token de escrita é um só para vários programas (plataforma, coletor, OS Creator). O selo é
o que diz se a linha que voltou da API é a que o Nexus gravou.

Uma chave só no .env (NEXUS_CHAVE_CADASTRO, 32 bytes em base64); dela saem, por HKDF, a chave da cifra e a do
selo. Perder a chave é perder o dado cifrado: a cópia em cofre é item obrigatório da virada.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PREFIXO = "cf1:"


class CifraErro(RuntimeError):
    """Chave inválida, cifra adulterada ou cifra de outro lugar. Nunca traz o dado nem a chave."""


def _b64d(s: str) -> bytes:
    s = s.strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def gerar_chave() -> str:
    return _b64e(secrets.token_bytes(32))


def _derivar(mestra: bytes, uso: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"nexus-cadastro/" + uso).derive(mestra)


class Cofre:
    def __init__(self, chave_b64: str):
        try:
            mestra = _b64d(chave_b64 or "")
        except (ValueError, TypeError):
            raise CifraErro("NEXUS_CHAVE_CADASTRO não é base64 válido") from None
        if len(mestra) != 32:
            raise CifraErro("NEXUS_CHAVE_CADASTRO precisa ter 32 bytes (gere com gerar_chave())")
        self._aead = AESGCM(_derivar(mestra, b"cifra/v1"))
        self._selo = _derivar(mestra, b"selo/v1")

    @staticmethod
    def eh_cifrado(valor) -> bool:
        return isinstance(valor, str) and valor.startswith(PREFIXO)

    def cifrar(self, texto: str, contexto: str) -> str:
        nonce = os.urandom(12)
        corpo = self._aead.encrypt(nonce, texto.encode("utf-8"), contexto.encode("utf-8"))
        return PREFIXO + _b64e(nonce + corpo)

    def decifrar(self, valor: str, contexto: str) -> str:
        if not self.eh_cifrado(valor):
            raise CifraErro("valor não está cifrado")
        try:
            bruto = _b64d(valor[len(PREFIXO):])
            return self._aead.decrypt(bruto[:12], bruto[12:], contexto.encode("utf-8")).decode("utf-8")
        except Exception:
            # InvalidTag, base64 quebrado, UTF-8 inválido: para a tela é tudo "não confere".
            raise CifraErro("cifra não confere: adulterada, de outra linha ou de outra chave") from None

    def selar(self, linha: dict) -> str:
        corpo = {k: v for k, v in linha.items() if k != "_selo"}
        texto = json.dumps(corpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        return hmac.new(self._selo, texto.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    def selo_confere(self, linha: dict) -> bool:
        selo = linha.get("_selo")
        return isinstance(selo, str) and hmac.compare_digest(selo, self.selar(linha))
