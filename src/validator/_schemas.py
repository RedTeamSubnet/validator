"""Typed contracts for data received from rest-core-api."""

import datetime

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class CoreChallengePM(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    kind: str
    is_active: bool
    config: "CoreChallengeConfigPM | None" = None


class CoreChallengeConfigPM(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    kind: str
    spec: dict


class CoreChallengeKindPM(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str


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
    "CoreChallengeConfigPM",
    "CoreChallengeKindPM",
    "CoreCommitPM",
    "CoreWeightMatrixPM",
    "CoreWeightPM",
]
