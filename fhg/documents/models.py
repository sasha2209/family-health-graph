"""What the document reader returns for review before anything is saved."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

DOC_TYPES = ("prescription", "lab_report", "discharge_summary", "other")


class ExtractedCondition(BaseModel):
    name: str
    category: Optional[str] = None
    onset_age: Optional[int] = None
    evidence: str = ""  # the line it was read from, shown on the review screen


class ExtractedMedication(BaseModel):
    name: str
    dosage: Optional[str] = None
    evidence: str = ""


class ExtractedObservation(BaseModel):
    code: str
    display: str = ""
    value: float
    unit: str = ""
    flag: Optional[str] = None  # "h" / "l" as printed on the report
    evidence: str = ""


class ExtractedRelative(BaseModel):
    relationship: str
    conditions: list[ExtractedCondition] = Field(default_factory=list)


class PatientInfo(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None


class Extraction(BaseModel):
    doc_type: str = "other"
    doc_date: Optional[date] = None
    facility: Optional[str] = None
    doctor: Optional[str] = None
    patient: PatientInfo = Field(default_factory=PatientInfo)
    conditions: list[ExtractedCondition] = Field(default_factory=list)
    medications: list[ExtractedMedication] = Field(default_factory=list)
    observations: list[ExtractedObservation] = Field(default_factory=list)
    family: list[ExtractedRelative] = Field(default_factory=list)
    read_by: str = "rules"  # "rules" | "rules+ai"

    def is_empty(self) -> bool:
        return not (self.conditions or self.medications or self.observations or self.family)
