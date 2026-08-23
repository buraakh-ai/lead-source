from pathlib import Path
from typing import Optional

from agno.skills import LocalSkills, Skills

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

_skills: Optional[Skills] = None


def get_skills() -> Skills:
    """Singleton Skills instance loading every SKILL.md folder under skills/
    (contact-extraction, icp-analysis, ...). Attach to an Agent via
    `skills=get_skills()` to give it the get_skill_instructions/reference/
    script tools."""
    global _skills
    if _skills is None:
        _skills = Skills(loaders=[LocalSkills(path=str(_SKILLS_DIR))])
    return _skills
