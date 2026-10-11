from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class SourceBase(BaseModel):
    name: str = Field(..., description="Unique code of the source (e.g. 'prop65', 'iarc', 'cosing')")
    version: str = Field(..., description="Snapshot version or date (e.g. '2026-07-31', 'vol-138')")
    license: str = Field(..., description="License / terms (e.g. 'Public Domain', 'CC BY-NC 3.0')")
    url: Optional[str] = Field(None, description="Official URL where source data was retrieved")
    attribution: Optional[str] = Field(None, description="Mandatory attribution text if required by license")

class SourceCreate(SourceBase):
    pass

class SourceInDB(SourceBase):
    id: str
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

def source_helper(source: dict) -> dict:
    """Convert MongoDB source document to a clean dict"""
    return {
        "id": str(source["_id"]),
        "name": source["name"],
        "version": source["version"],
        "license": source["license"],
        "url": source.get("url"),
        "attribution": source.get("attribution"),
        "retrieved_at": source.get("retrieved_at", datetime.utcnow()),
    }
