from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PurchaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Developer laptops", min_length=3, max_length=120)
    quantity: int = Field(default=10, ge=1, le=100, strict=True)
    budget_inr: int = Field(default=900000, ge=10000, le=100000000, strict=True)
    delivery_days: int = Field(default=14, ge=1, le=90, strict=True)
    min_ram_gb: Literal[16, 32, 64] = 32
    min_storage_gb: Literal[256, 512, 1024, 2048] = 512
    priority: Literal["value", "delivery", "performance"] = "value"
    notes: str = Field(
        default="Prefer a balance of price and warranty.", max_length=2000
    )
    simulate_timeout: bool = False

    @field_validator("notes")
    @classmethod
    def notes_byte_budget(cls, value):
        if len(value.encode("utf-8")) > 2000:
            raise ValueError("Preferences must fit within 2000 UTF-8 bytes")
        return value


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "reject", "revise"]
    proposal_hash: str = Field(min_length=64, max_length=64)
    note: str = Field(default="", max_length=1000)
    revision: PurchaseRequest | None = None


class ForkRequest(BaseModel):
    checkpoint_id: str
    request: PurchaseRequest


class Assessment(BaseModel):
    summary: str = Field(max_length=1200)
    considerations: list[str] = Field(max_length=5)


class Recommendation(BaseModel):
    selected_id: str
    reason_codes: list[
        Literal[
            "meets_requirements",
            "lowest_total",
            "fastest_delivery",
            "largest_storage",
            "most_ram",
            "longest_warranty",
            "highest_rating",
        ]
    ] = Field(min_length=1, max_length=3)


class Route(BaseModel):
    next_worker: Literal["requirements", "suppliers", "policy", "recommendation"]
