from sqlalchemy import Column, Integer, String, JSON
from app.database import Base

class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    
    # Structured fields for the template objective function
    education = Column(JSON) # e.g., [{"university": "...", "degree": "...", "start": "..."}]
    work_experience = Column(JSON)
    projects = Column(JSON)
    
    # Store the parsed unstructured data from the hard-copy resume
    raw_resume_data = Column(JSON)