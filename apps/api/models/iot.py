from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float
    lon: float


class Container(BaseModel):
    id: str
    location: Location
    weight: float = Field(ge=0)
    volume: float = Field(ge=0)
    materials: list[str]
    name: str
