"""Typed contracts for data received from rest-core-api."""

import datetime

from pydantic import BaseModel, Field, TypeAdapter


class CoreChallengePM(BaseModel):
    id: str
    name: str
    challenge_config_id: str | None = None


class CoreCommitPM(BaseModel):
    cipher_commit: str
    committed_at: datetime.datetime


class CoreWeightPM(BaseModel):
    uid: int = Field(ge=0)
    score: float = Field(ge=0)


class CoreWeightMatrixPM(BaseModel):
    refreshed_at: datetime.datetime | None = None
    entries: list[CoreWeightPM]


CHALLENGES = TypeAdapter(list[CoreChallengePM])
COMMITS = TypeAdapter(list[CoreCommitPM])


__all__ = [
    "CHALLENGES",
    "COMMITS",
    "CoreChallengePM",
    "CoreCommitPM",
    "CoreWeightMatrixPM",
    "CoreWeightPM",
]
