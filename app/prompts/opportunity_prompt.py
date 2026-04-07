"""
PROMPT 4: Internship & Job Opportunity Finder
===============================================
Strategy: Use OpenAI with web_search tool to find REAL, CURRENT openings.
This is the only reliable approach for India's fragmented job market
without paying for Naukri/LinkedIn API access.

How it works:
  1. Build a targeted search prompt with student's exact profile
  2. Call GPT with tools=[{"type":"web_search_preview"}]
  3. GPT searches the web and returns real job listings with URLs
  4. We parse and store them, score them for fit, return to student

Sources GPT will find:
  - Internshala (internshala.com/internships)
  - Unstop (unstop.com)
  - LinkedIn Jobs (linkedin.com/jobs)
  - Naukri (naukri.com)
  - Company career pages directly
  - AngelList/Wellfound (startups)
  - GeeksforGeeks Jobs (gfg.jobs)
  - HackerEarth / HackerRank contests

Cost: ~$0.003 per search (web search tool adds token cost)
Freshness: Real-time — results from today
Risk: URLs may expire. We store them with fetched_at timestamp.
"""

def build_opportunity_prompt(
    cgpa: float,
    skills: list,
    college_tier: str,
    year: str,
    target_roles: list,
    target_companies: list,
    co_curricular: list,
    certifications: list,
    open_to_remote: bool,
    preferred_locations: list,
    placement_label: str,
) -> str:
    skills_str     = ", ".join(skills) if skills else "Python, SQL"
    roles_str      = ", ".join(target_roles) if target_roles else "Software Engineer"
    companies_str  = ", ".join(target_companies) if target_companies else "any"
    cocurr_str     = ", ".join(co_curricular) if co_curricular else "none mentioned"
    certs_str      = ", ".join(certifications) if certifications else "none"
    locations_str  = ", ".join(preferred_locations) if preferred_locations else "anywhere in India"

    tier_map = {
        "tier1": "IIT/NIT/BITS student",
        "tier2": "State engineering college student",
        "tier3": "Private engineering college student",
    }
    tier_label = tier_map.get(college_tier, college_tier)

    year_context = {
        "fresher": "fresher looking for first job",
        "2nd":     "2nd year student looking for internships",
        "3rd":     "3rd year student looking for 2-6 month internships urgently",
        "4th":     "final year student looking for full-time roles AND PPO opportunities",
    }.get(year, year)

    remote_str = "open to remote/hybrid roles" if open_to_remote else "prefers on-site only"

    return f"""You are a job search assistant for Indian engineering students. Search the web and find REAL, CURRENTLY OPEN internships and job opportunities for this student.

STUDENT PROFILE:
- Background: {tier_label}, {year_context}
- CGPA: {cgpa}/10
- Skills: {skills_str}
- Certifications: {certs_str}
- Co-curricular: {cocurr_str}
- Target roles: {roles_str}
- Dream companies: {companies_str}
- Locations: {locations_str}, {remote_str}
- Readiness level: {placement_label}

SEARCH INSTRUCTIONS:
Search for CURRENTLY OPEN opportunities on these platforms:
1. internshala.com — for internships (most important for Indian students)
2. unstop.com — for hackathons, contests, and fresher jobs
3. linkedin.com/jobs — for jobs and internships
4. wellfound.com — for startup roles
5. Direct company career pages for: {companies_str}
6. naukri.com — for fresher/entry-level jobs

Search queries to use:
- "{skills_str} internship India 2025"
- "{roles_str} fresher job India"  
- "internshala {skills_str} internship"
- "unstop {roles_str} challenge"
- Company name + "careers" + "fresher" for each target company

MATCHING RULES:
- For CGPA {cgpa}: avoid listing roles with higher CGPA cutoffs
- For {college_tier}: include off-campus opportunities prominently
- For skills {skills_str}: match at least 60% of listed required skills
- Prioritise roles with APPLY LINK directly accessible (not login-gated)

Return ONLY this JSON (no preamble, no markdown):
{{
  "opportunities": [
    {{
      "type": "<'internship' | 'job' | 'hackathon' | 'contest'>",
      "title": "<exact job/internship title>",
      "company": "<company name>",
      "location": "<city or 'Remote' or 'Hybrid'>",
      "stipend_or_ctc": "<e.g. '₹15,000/month' or '4-6 LPA' or 'Unpaid' or 'Prize pool ₹1L'>",
      "duration": "<e.g. '2 months' or 'Full-time' or '3 days hackathon'>",
      "apply_url": "<DIRECT apply URL — must be a real, working URL>",
      "source": "<platform name: 'internshala' | 'unstop' | 'linkedin' | 'naukri' | 'company_direct' | 'wellfound'>",
      "deadline": "<application deadline if visible, else 'Rolling'>",
      "skills_needed": ["<skill1>", "<skill2>"],
      "match_score": <integer 0-100 — how well this student fits>,
      "match_reason": "<1 sentence: why this is a good fit for THIS student specifically>"
    }}
  ],
  "search_summary": "<2 sentences: what you found and any notable patterns>",
  "best_immediate_action": "<The single best opportunity and exactly how to apply — platform, URL, deadline>"
}}

Find 8-12 opportunities. Include a mix of:
- 3-4 internships (Internshala priority)
- 2-3 entry-level jobs or PPO opportunities
- 1-2 hackathons/contests from Unstop (great for Tier 2/3 students)
- 1-2 from company career pages directly

Sort by match_score descending. Be honest about match_score — don't give 95+ unless truly exceptional fit."""


def build_opportunity_search_config() -> dict:
    """OpenAI API config with web search tool enabled."""
    return {
        "model": "gpt-4o-mini-search-preview",  # web search enabled model
        "tools": [{"type": "web_search_preview"}],
        "tool_choice": "auto",
        "temperature": 0.2,
        "max_tokens": 3000,
    }
