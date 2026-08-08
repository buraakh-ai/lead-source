from typing import List, Optional

from pydantic import BaseModel, Field


class BusinessResearch(BaseModel):
    business_name: str
    location: str
    services: List[str]
    icp: str = Field(
        description=(
            "Narrative description of the business's ideal customers - the types of "
            "people or OTHER small businesses who would buy its services. This is about "
            "who the target business SELLS TO, never businesses that do the same thing "
            "as the target itself (no competitors)."
        )
    )
    icp_categories: List[str] = Field(
        description=(
            "3-6 concrete, generic small-business or consumer categories that are this "
            "business's customers, phrased as short searchable terms (e.g. for a tax "
            "consultancy: 'restaurants', 'hair salons', 'medical clinics', 'retail "
            "stores'; for a marketing agency: 'law firms', 'gyms', 'real estate agents'). "
            "These are used verbatim as search queries to find leads, so they must never "
            "be the target business's own category or a synonym of it."
        )
    )
    branding_notes: Optional[str] = Field(
        default=None, description="Notable branding, tone, or positioning details"
    )


class LeadSource(BaseModel):
    source_name: str
    url: str
    why_relevant: str
    stitching_instructions: Optional[str] = Field(
        default=None,
        description=(
            "If this page alone won't yield contact details, instructions for which "
            "additional pages/steps to combine to reach an actual lead's contact info."
        ),
    )


class LeadSourceList(BaseModel):
    sources: List[LeadSource]


# class Lead(BaseModel):
#     name: str
#     phone: Optional[str] = None
#     business_email: Optional[str] = None
#     personal_email: Optional[str] = None
#     linkedin_url: Optional[str] = None
#     source_url: str
class Lead(BaseModel):
    name: str
    phone: Optional[str] = None
    business_email: Optional[str] = None
    personal_email: Optional[str] = None
    linkedin_url: Optional[str] = None
    source_url: Optional[str] = None

class LeadList(BaseModel):
    leads: List[Lead]
