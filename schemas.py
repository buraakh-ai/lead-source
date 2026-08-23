from datetime import date, datetime
from typing import List, Optional
from uuid import uuid4

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


class CampaignTarget(BaseModel):
    """User-controlled market segment passed to the sourcing agents."""

    campaign_id: str = Field(default_factory=lambda: str(uuid4()))
    campaign_name: str = "Public-source lead sourcing campaign"
    campaign_status: str = "draft"
    period_start: date = Field(default_factory=date.today)
    period_end: date = Field(default_factory=date.today)
    country: str = "United States"
    state: str = "California"
    geography: str = ""
    cities_or_areas: List[str] = Field(default_factory=list)
    industries: List[str] = Field(default_factory=list)
    subcategories: List[str] = Field(default_factory=list)
    decision_maker_roles: List[str] = Field(
        default_factory=lambda: ["Owner", "Founder", "General Manager", "Finance Manager"]
    )
    inclusion_keywords: List[str] = Field(default_factory=list)
    exclusion_keywords: List[str] = Field(default_factory=list)

    def location_label(self) -> str:
        parts = [*self.cities_or_areas, self.state, self.country]
        return ", ".join(dict.fromkeys(part.strip() for part in parts if part and part.strip()))


class LeadSource(BaseModel):
    campaign_id: Optional[str] = None
    source_name: str
    url: str
    why_relevant: str
    source_type: str = "official_website"
    category: Optional[str] = None
    business_address: Optional[str] = None
    city: Optional[str] = None
    public_phone: Optional[str] = None
    google_place_id: Optional[str] = None
    google_maps_url: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    business_status: Optional[str] = None
    business_types: List[str] = Field(default_factory=list)
    evidence_urls: List[str] = Field(default_factory=list)
    verification_status: str = "discovered"
    stitching_instructions: Optional[str] = Field(
        default=None,
        description=(
            "If this page alone won't yield contact details, instructions for which "
            "additional pages/steps to combine to reach an actual lead's contact info."
        ),
    )


class LeadSourceList(BaseModel):
    sources: List[LeadSource]


class Lead(BaseModel):
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    run_id: Optional[str] = None
    name: str
    business_name: Optional[str] = None
    category: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    business_email: Optional[str] = None
    personal_email: Optional[str] = None
    decision_maker_name: Optional[str] = None
    decision_maker_role: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    source_url: Optional[str] = None
    source_urls: List[str] = Field(default_factory=list)
    verification_status: str = "incomplete"
    confidence_score: int = Field(default=0, ge=0, le=100)
    lead_score: int = Field(default=0, ge=0, le=100)
    marketing_notes: Optional[str] = None
    google_place_id: Optional[str] = None
    google_maps_url: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    business_status: Optional[str] = None


class LeadList(BaseModel):
    leads: List[Lead]


class RunSummary(BaseModel):
    run_id: str
    campaign_id: str
    campaign_name: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    sources_discovered: int = 0
    leads_returned: int = 0
    verified_leads: int = 0
    enriched_leads: int = 0
    incomplete_leads: int = 0
    database_configured: bool = False
    database_saved: bool = False
    database_message: str = "Database persistence was not requested."


class SourcingCampaignResponse(BaseModel):
    campaign: CampaignTarget
    lead_sources: List[LeadSource]
    leads: List[Lead]
    run_summary: RunSummary
