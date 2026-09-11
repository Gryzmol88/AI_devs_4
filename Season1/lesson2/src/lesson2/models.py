from pydantic import BaseModel, Field


class Person(BaseModel):
    name: str
    surname: str
    birth_year: int = Field(ge=1900, le=2100)


class Coordinates(BaseModel):
    lat: float
    lon: float


class PowerPlant(BaseModel):
    code: str
    lat: float
    lon: float


class CandidateReport(BaseModel):
    name: str
    surname: str
    birth_year: int
    power_plant: str
    distance_km: float
    is_candidate: bool


class VerifyAnswer(BaseModel):
    name: str
    surname: str
    accessLevel: int
    powerPlant: str


class VerifyPayload(BaseModel):
    apikey: str
    task: str = "findhim"
    answer: VerifyAnswer

