"""Cofre das chaves de API: guarda os segredos CIFRADOS e presos a ESTE computador/usuário.

Secret vault: secrets are stored encrypted and bound to this machine/user.

Formatos guardados no settings.json (campo do segredo vira {"enc": "<esquema>:v1:<dados>"}):
  • dpapi:v1:<base64>   Windows — DPAPI (CryptProtectData, escopo do USUÁRIO atual, entropia própria do app,
                        CRYPTPROTECT_UI_FORBIDDEN). Só o mesmo usuário do Windows, neste PC, consegue abrir.
  • keyring:v1:<nome>   Linux/macOS com Secret Service/Keychain funcionando (pacote `keyring`, se instalado):
                        o segredo fica no chaveiro do sistema; o arquivo só guarda a referência.
  • aesgcm:v1:<base64>  Linux sem chaveiro: AES-256-GCM (`cryptography`) com chave derivada (scrypt) de
                        /etc/machine-id + uid do usuário + sal aleatório guardado à parte (0600). Mais fraco que o DPAPI:
                        protege contra copiar o arquivo para OUTRO PC, mas não contra quem já tem acesso à sua conta.
Nada aqui escreve segredos em log. Falhas viram VaultError (sem o conteúdo).
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import logging
import os
import secrets as _rnd
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ENTROPY = b"EasyGameTranslator/v4/api-key-vault/1"      # entropia própria do app (DPAPI) / contexto (AES)
KEYRING_SERVICE = "EasyGameTranslator"
SALT_NAME = "vault.salt"


class VaultError(Exception):
    """O segredo não pode ser aberto aqui (outro PC/usuário, arquivo adulterado ou chaveiro indisponível)."""


def is_blob(v) -> bool:
    return isinstance(v, dict) and isinstance(v.get("enc"), str)


# ------------------------------------------------------------------ Windows: DPAPI
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _blob_in(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)       # type: ignore[attr-defined]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)     # type: ignore[attr-defined]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    src, _keep1 = _blob_in(data)
    ent, _keep2 = _blob_in(ENTROPY)
    out = _Blob()
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(src), ctypes.c_wchar_p("EGT"), ctypes.byref(ent), None, None,
                                      CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(src), None, ctypes.byref(ent), None, None,
                                        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
    if not ok:
        raise VaultError(f"DPAPI falhou (erro {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


# ------------------------------------------------------------------ Linux/macOS: keyring (opcional)
def _keyring():
    """Backend do chaveiro do sistema, se o pacote existir e houver um chaveiro de verdade (não o 'fail'/texto puro)."""
    if os.environ.get("EGT_VAULT_NO_KEYRING") == "1":
        return None
    try:
        import keyring  # type: ignore
        from keyring.backends import fail  # type: ignore
        kr = keyring.get_keyring()
        name = type(kr).__module__ + "." + type(kr).__name__
        if isinstance(kr, fail.Keyring) or "plaintext" in name.lower() or "null" in name.lower():
            return None
        if getattr(kr, "priority", 0) <= 0:
            return None
        return keyring
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ Linux sem chaveiro: AES-GCM
def _machine_id() -> bytes:
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            v = Path(p).read_text().strip()
            if v:
                return v.encode()
        except OSError:
            pass
    return b"no-machine-id"


_key_cache: dict[str, bytes] = {}


def _aes_key(salt_dir: Path) -> bytes:
    salt_file = salt_dir / SALT_NAME
    ck = str(salt_file)
    if ck in _key_cache:
        return _key_cache[ck]
    try:
        salt = salt_file.read_bytes()
    except FileNotFoundError:
        salt_dir.mkdir(parents=True, exist_ok=True)
        salt = _rnd.token_bytes(32)
        fd = os.open(salt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(salt)
    if len(salt) < 16:
        raise VaultError("sal do cofre inválido")
    uid = str(os.getuid() if hasattr(os, "getuid") else 0).encode()
    key = hashlib.scrypt(_machine_id() + b"|" + uid + b"|" + ENTROPY, salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    _key_cache[ck] = key
    return key


def _aes(data: bytes, protect: bool, salt_dir: Path) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.exceptions import InvalidTag
    except ImportError as exc:
        raise VaultError("pacote 'cryptography' ausente (pip install cryptography)") from exc
    g = AESGCM(_aes_key(salt_dir))
    if protect:
        nonce = _rnd.token_bytes(12)
        return nonce + g.encrypt(nonce, data, ENTROPY)
    if len(data) < 13:
        raise VaultError("dados cifrados inválidos")
    try:
        return g.decrypt(data[:12], data[12:], ENTROPY)
    except InvalidTag as exc:
        raise VaultError("não foi possível abrir neste computador") from exc


# ------------------------------------------------------------------ API
def scheme(salt_dir: Optional[Path] = None) -> str:
    """Esquema usado para cifrar AGORA neste sistema."""
    if os.environ.get("EGT_VAULT_SCHEME"):          # só para testes
        return os.environ["EGT_VAULT_SCHEME"]
    if sys.platform == "win32":
        return "dpapi"
    return "keyring" if _keyring() else "aesgcm"


def protect(plain: str, name: str, salt_dir: Path) -> dict:
    """Cifra `plain` e devolve {"enc": "..."}; `name` identifica o segredo (ex.: 'ai.gemini_key')."""
    if not plain:
        raise ValueError("segredo vazio")
    sch = scheme(salt_dir)
    raw = plain.encode("utf-8")
    if sch == "dpapi":
        return {"enc": "dpapi:v1:" + base64.b64encode(_dpapi(raw, True)).decode()}
    if sch == "keyring":
        kr = _keyring()
        if kr is None:
            raise VaultError("chaveiro indisponível")
        ref = f"{name}:{_rnd.token_hex(8)}"
        kr.set_password(KEYRING_SERVICE, ref, plain)
        return {"enc": "keyring:v1:" + ref}
    if sch == "aesgcm":
        return {"enc": "aesgcm:v1:" + base64.b64encode(_aes(raw, True, salt_dir)).decode()}
    raise VaultError(f"esquema desconhecido: {sch}")


def unprotect(blob, salt_dir: Path) -> str:
    """Abre {"enc": ...}. Levanta VaultError se não der (outro PC/usuário, adulterado, chaveiro sem o item)."""
    if not is_blob(blob):
        raise VaultError("formato inválido")
    try:
        sch, ver, data = blob["enc"].split(":", 2)
    except ValueError as exc:
        raise VaultError("formato inválido") from exc
    if ver != "v1":
        raise VaultError("versão desconhecida")
    try:
        if sch == "dpapi":
            if sys.platform != "win32":
                raise VaultError("cifrado no Windows (DPAPI)")
            return _dpapi(base64.b64decode(data, validate=True), False).decode("utf-8")
        if sch == "keyring":
            kr = _keyring()
            v = kr.get_password(KEYRING_SERVICE, data) if kr else None
            if not v:
                raise VaultError("item não encontrado no chaveiro deste computador")
            return v
        if sch == "aesgcm":
            return _aes(base64.b64decode(data, validate=True), False, salt_dir).decode("utf-8")
    except VaultError:
        raise
    except Exception as exc:  # noqa: BLE001  (base64/utf-8/ctypes) — nunca inclui o conteúdo
        raise VaultError(type(exc).__name__) from exc
    raise VaultError(f"esquema desconhecido: {sch}")


def forget(blob) -> None:
    """Apaga o item do chaveiro do sistema (esquema keyring). Para DPAPI/AES basta remover o blob do arquivo."""
    if is_blob(blob) and blob["enc"].startswith("keyring:v1:"):
        kr = _keyring()
        if kr:
            try:
                kr.delete_password(KEYRING_SERVICE, blob["enc"].split(":", 2)[2])
            except Exception:  # noqa: BLE001
                pass


def selftest(salt_dir: Path) -> str:
    """Ida e volta + blob adulterado/estrangeiro falhando com elegância. Retorna um resumo (sem segredos)."""
    probe = "egt-selftest-" + _rnd.token_hex(8)
    b = protect(probe, "selftest", salt_dir)
    ok = unprotect(b, salt_dir) == probe
    sch = b["enc"].split(":", 1)[0]
    tampered = dict(b)
    if sch in ("dpapi", "aesgcm"):
        raw = bytearray(base64.b64decode(b["enc"].split(":", 2)[2]))
        raw[-1] ^= 0x55                                  # assinatura/tag no fim (DPAPI e AES-GCM)
        tampered = {"enc": f"{sch}:v1:" + base64.b64encode(bytes(raw)).decode()}
    else:
        tampered = {"enc": "keyring:v1:nao-existe"}
    try:
        unprotect(tampered, salt_dir)
        tamper_ok = False
    except VaultError:
        tamper_ok = True
    foreign_ok = True                                   # blob "de outro PC" (bytes aleatórios) → erro limpo
    for fake in ({"enc": f"{sch}:v1:" + base64.b64encode(_rnd.token_bytes(96)).decode()}, {"enc": "dpapi:v1:@@@"}, {"x": 1}):
        try:
            unprotect(fake, salt_dir)
            foreign_ok = False
        except VaultError:
            pass
    forget(b)
    return f"scheme={sch} roundtrip={ok} tamper_rejected={tamper_ok} foreign_rejected={foreign_ok}"
