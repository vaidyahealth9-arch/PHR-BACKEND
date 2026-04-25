import pytest
from pydantic import ValidationError

from schemas import ProfileCreateRequest


def test_profile_create_valid_relationship():
    payload = ProfileCreateRequest(full_name="Anjali Sharma", relationship="parent")
    assert payload.relationship == "parent"


def test_profile_create_invalid_relationship_rejected():
    with pytest.raises(ValidationError):
        ProfileCreateRequest(full_name="Anjali Sharma", relationship="invalid-relation")


def test_profile_create_short_name_rejected():
    with pytest.raises(ValidationError):
        ProfileCreateRequest(full_name="A", relationship="other")
