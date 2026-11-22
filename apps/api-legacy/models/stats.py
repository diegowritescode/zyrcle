from pydantic import BaseModel


class CollectionStats(BaseModel):
    today: dict[str, float]
    week: dict[str, float]
    carbon_monthly: dict[str, float]


class ContainerDetail(BaseModel):
    name: str
    status: str
    fill_level: float
    weight: float
    tokens: float
    co2_saved: float


class ResidenceStats(BaseModel):
    name: str
    total_containers: int
    total_weight: float
    cycle_tokens: float
    carbon_offset: float
    activity_by_material: dict[str, dict[str, dict[str, float]]]
    containers: list[ContainerDetail]
