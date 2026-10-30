from datetime import UTC, datetime
from pydantic import BaseModel, Field

class TimestampMixin(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> "TimestampMixin":
        return self.model_copy(update={"updated_at": datetime.now(UTC)})