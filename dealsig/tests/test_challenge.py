import hashlib
import time

import pytest

from app.services import challenge

SESSION = "session-token-for-tests"
BITS = 10  # cheap to solve in a test; production default is CONTACT_POW_BITS


def solve(nonce: str, bits: int = BITS) -> str:
    counter = 0
    while True:
        if challenge.solution_is_valid(nonce, str(counter), bits):
            return str(counter)
        counter += 1


def issued(seconds_ago: int = 10) -> tuple[str, str]:
    token = challenge.issue(SESSION, now=int(time.time()) - seconds_ago)
    return token, solve(token.split(".")[1])


def test_a_correctly_solved_challenge_passes():
    token, counter = issued()
    challenge.verify(token, counter, SESSION, difficulty_bits=BITS)


def test_forged_signature_is_rejected():
    token, counter = issued()
    issued_at, nonce, _ = token.split(".")
    forged = f"{issued_at}.{nonce}.{'0' * 32}"
    with pytest.raises(challenge.ChallengeError):
        challenge.verify(forged, counter, SESSION, difficulty_bits=BITS)


def test_challenge_from_another_session_is_rejected():
    """Signature covers the session token, so a stolen challenge does not travel."""
    token, counter = issued()
    with pytest.raises(challenge.ChallengeError):
        challenge.verify(token, counter, "a-different-session", difficulty_bits=BITS)


def test_unsolved_challenge_is_rejected():
    token, _ = issued()
    with pytest.raises(challenge.ChallengeError):
        challenge.verify(token, "0", SESSION, difficulty_bits=24)


def test_missing_counter_is_rejected():
    token, _ = issued()
    with pytest.raises(challenge.ChallengeError):
        challenge.verify(token, "", SESSION, difficulty_bits=BITS)


def test_non_numeric_counter_is_rejected():
    token, _ = issued()
    with pytest.raises(challenge.ChallengeError):
        challenge.verify(token, "abc", SESSION, difficulty_bits=BITS)


def test_submission_faster_than_a_human_is_rejected():
    token, counter = issued(seconds_ago=0)
    with pytest.raises(challenge.ChallengeError, match="faster than a person"):
        challenge.verify(token, counter, SESSION, difficulty_bits=BITS)


def test_stale_challenge_is_rejected():
    token, counter = issued(seconds_ago=challenge.MAX_SECONDS + 60)
    with pytest.raises(challenge.ChallengeError, match="expired"):
        challenge.verify(token, counter, SESSION, difficulty_bits=BITS)


def test_malformed_token_is_rejected():
    for bad in ("", "nope", "a.b", "a.b.c.d"):
        with pytest.raises(challenge.ChallengeError):
            challenge.verify(bad, "0", SESSION, difficulty_bits=BITS)


def test_leading_zero_bit_counting_matches_hashlib():
    digest = hashlib.sha256(b"anything").digest()
    expected = 0
    for byte in digest:
        if byte:
            expected += 8 - byte.bit_length()
            break
        expected += 8
    assert challenge._leading_zero_bits(digest) == expected
