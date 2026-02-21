from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Union

class PersonalInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None

class Education(BaseModel):
    institution: str
    location: Optional[str] = None
    degree: str
    field_of_study: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[Union[str, Dict[str, str]]] = None
    coursework: List[str] = []

class WorkExperience(BaseModel):
    company: str
    location: Optional[str] = None
    role: str
    start_date: str
    end_date: str
    bullets: List[str] = []
    skills_used: List[str] = []
    metrics: List[str] = []
    experience_context: Optional[str] = None

# --- NEW STRICT MODELS TO REPLACE 'Any' ---
class Project(BaseModel):
    title: str
    description: Optional[str] = None
    link: Optional[str] = None

class Publication(BaseModel):
    title: str
    publisher: Optional[str] = None
    date: Optional[str] = None
    link: Optional[str] = None

class Certification(BaseModel):
    name: str
    issuer: str
    date: Optional[str] = None

class ApplicationHistory(BaseModel):
    company: str
    role: str
    date_applied: Optional[str] = None
    status: Optional[str] = None

class Skills(BaseModel):
    technical: List[str] = []
    tools: List[str] = []
    soft_skills: List[str] = []
# ------------------------------------------

class CandidateProfile(BaseModel):
    personal_info: PersonalInfo
    education: List[Education] = []
    work_experience: List[WorkExperience] = []
    
    # Updated to use strict models instead of Any
    projects: List[Project] = []
    skills: Optional[Skills] = None
    publications: List[Publication] = []
    certifications: List[Certification] = []
    application_history: List[ApplicationHistory] = []

class ExtractionResult(BaseModel):
    profile: CandidateProfile = Field(
        description="The structured candidate profile extracted so far."
    )
    
    assistant_message: Optional[str] = Field(
        default=None,
        description="A SHORT conversational reply ending with EXACTLY ONE question. NEVER ask multiple questions at once."
    )

    remaining_questions_count: int = Field(
        default=0,
        description="The estimated number of questions still needed to complete the profile. 0 if complete."
    )

    current_focus_field: Optional[str] = Field(
        default="Summary",
        description="The EXACT top-level JSON key you are currently asking about (e.g., 'work_experience', 'education', 'projects', 'skills')."
    )
    
    is_complete: bool = Field(
        description="Set to True ONLY if all mandatory fields, metrics, and context are fully populated."
    )