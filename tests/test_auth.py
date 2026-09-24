"""Password hashing for the ingest credential."""

from custom_components.meal_recorder.auth import (
    hash_password,
    verify_password,
    verify_username,
)


def test_password_verifies():
    record = hash_password("secret")
    assert verify_password("secret", record)


def test_wrong_password_is_rejected():
    assert not verify_password("wrong", hash_password("secret"))


def test_the_password_is_not_stored():
    record = hash_password("secret")
    assert "secret" not in repr(record)


def test_each_hash_has_its_own_salt():
    assert hash_password("secret")["salt"] != hash_password("secret")["salt"]


def test_a_broken_record_is_rejected():
    assert not verify_password("secret", {"salt": "zz", "n": 1, "r": 1, "p": 1, "dklen": 32})


def test_usernames_compare():
    assert verify_username("meals", "meals")
    assert not verify_username("meals", "Meals")
