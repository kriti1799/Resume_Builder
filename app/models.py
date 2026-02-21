from sqlalchemy import Column, Integer, String, JSON, DateTime
from app.database import Base
from sqlalchemy.sql import func

class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    
    # Structured fields for the template objective function
    education = Column(JSON) # e.g., [{"university": "...", "degree": "...", "start": "..."}]
    work_experience = Column(JSON)
    projects = Column(JSON)
    
    # Store the parsed unstructured data from the hard-copy resume
    resume_filename = Column(String, nullable=True)
    cover_letter_filename = Column(String, nullable=True)
    
    # The master JSON payload that your agent will generate and update
    parsed_data = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
