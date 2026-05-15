"""
UploadSession ORM model.

Records the mapping from (session_id, display_name) → file_path on disk for
every dataset uploaded in a session.

This table is populated at the start of the analysis pipeline so that the
Stage 5 export feature can reliably locate the original uploaded files.
Without this record, the export would have to guess which timestamped file
in the uploads directory corresponds to a given display name.
"""

from sqlalchemy import Column, Integer, String, Text

from app.models.database import Base


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False, index=True)
    dataset_name = Column(String, nullable=False)   # original display name (e.g. "policies.csv")
    file_path = Column(String, nullable=False)       # absolute path to the saved file on disk
    saved_as = Column(String, nullable=False)        # filename as stored (may include timestamp prefix)
    analyst_rules_json = Column(Text, nullable=True) # JSON-serialised AnalystRulesInput dict
