import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class Photo(BaseModel):
    id: uuid.UUID
    content_url: str
    position: int
    is_primary: bool
    width: int
    height: int
    mime_type: str
    size: int
    archived_at: datetime | None


class PhotoList(BaseModel):
    items: list[Photo]
    total: int


class PhotoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_primary: Literal[True] | None = None
    position: StrictInt | None = Field(default=None, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Укажите главную фотографию или порядок отображения.")
        return self
