"""
Analyst Rules — runtime configuration model.

Analysts may supply these values at upload time to customise the thresholds
used by the data-correction rules engine.  Where not supplied, the defaults
from app.core.insurance_fields.ANALYST_RULES are used.

This is not a database model — it is a Pydantic model used to validate and
carry analyst-supplied configuration through the analysis pipeline.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.core.insurance_fields import ANALYST_RULES as _DEFAULTS


class AnalystRulesInput(BaseModel):
    """Runtime analyst rules sent with the upload request (all optional)."""

    min_premium: Optional[float] = Field(
        default=_DEFAULTS["minimum_premium"],
        description="Premiums below this value are flagged as anomalies.",
    )
    max_premium: Optional[float] = Field(
        default=_DEFAULTS["maximum_premium"],
        description="Premiums above this value are flagged. None disables the check.",
    )
    max_ncd: Optional[int] = Field(
        default=_DEFAULTS.get("max_ncd"),
        description="NCD values above this are flagged. None disables the check.",
    )
    date_format_standard: str = Field(
        default=_DEFAULTS["date_format_standard"],
        description="strftime format for date normalisation proposals.",
    )
    currency_symbol: str = Field(
        default=_DEFAULTS.get("currency_symbol", "£"),
        description="Symbol prepended when displaying money values.",
    )

    def to_dict(self) -> dict:
        return {
            "minimum_premium":  self.min_premium,
            "maximum_premium":  self.max_premium,
            "max_ncd":          self.max_ncd,
            "date_format_standard": self.date_format_standard,
            "currency_symbol":  self.currency_symbol,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AnalystRulesInput":
        return cls(
            min_premium=d.get("minimum_premium", _DEFAULTS["minimum_premium"]),
            max_premium=d.get("maximum_premium", _DEFAULTS["maximum_premium"]),
            max_ncd=d.get("max_ncd"),
            date_format_standard=d.get("date_format_standard", _DEFAULTS["date_format_standard"]),
            currency_symbol=d.get("currency_symbol", "£"),
        )
