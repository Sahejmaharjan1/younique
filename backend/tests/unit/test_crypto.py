import uuid

import pytest

from younique.crypto.envelope import EnvKek, decrypt, encrypt, new_dek


@pytest.mark.asyncio
async def test_round_trip_and_tamper() -> None:
    kek = EnvKek(b"k" * 32)
    dek = new_dek()
    wrapped = await kek.wrap(dek)
    assert await kek.unwrap(wrapped) == dek
    workspace = uuid.uuid4()
    row = uuid.uuid4()
    other = uuid.uuid4()
    blob = encrypt(dek, b"sk-test-secret", workspace_id=workspace, secret_kind="provider_key", row_id=row, key_version=1)
    assert decrypt(dek, blob, workspace_id=workspace, secret_kind="provider_key", row_id=row, key_version=1) == b"sk-test-secret"
    with pytest.raises(ValueError):
        decrypt(dek, blob, workspace_id=workspace, secret_kind="provider_key", row_id=other, key_version=1)
    with pytest.raises(ValueError):
        decrypt(dek, blob, workspace_id=uuid.uuid4(), secret_kind="provider_key", row_id=row, key_version=1)
    mutated = bytearray(blob)
    mutated[-1] ^= 0x01
    with pytest.raises(ValueError):
        decrypt(dek, bytes(mutated), workspace_id=workspace, secret_kind="provider_key", row_id=row, key_version=1)
    rotated = new_dek()
    wrapped_next = await kek.wrap(rotated)
    assert await kek.unwrap(wrapped_next) == rotated
    blob2 = encrypt(rotated, b"next", workspace_id=workspace, secret_kind="provider_key", row_id=row, key_version=2)
    with pytest.raises(ValueError):
        decrypt(dek, blob2, workspace_id=workspace, secret_kind="provider_key", row_id=row, key_version=2)
    assert decrypt(rotated, blob2, workspace_id=workspace, secret_kind="provider_key", row_id=row, key_version=2) == b"next"
