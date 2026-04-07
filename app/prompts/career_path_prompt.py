"""
PROMPT 5: Career Path + Reality Check + Motivation Engine
===========================================================
Purpose : Three jobs in one prompt:
  1. REALITY CHECK — Honest assessment of target company fit
  2. ALTERNATIVE CAREER PATHS — If primary path isn't realistic, offer real alternatives
  3. MOTIVATION — Personalised, specific encouragement (not generic)
  4. CO-CURRICULAR INSIGHTS — What their activities signal to employers

Design decisions:
  - This prompt runs AFTER analysis, so it has full context
  - It explicitly separates "you can reach this with work" vs "this path needs 12+ months"
  - Co-curricular activities are treated as genuine signals, not fluff
  - Alternative paths are India-specific: Data Science, DevOps, Product Management,
    QA, Business Analyst, Government tech jobs, Startup founding, Freelancing
  - Motivation is written for Indian college context specifically
    (parental pressure, peer comparison, rural vs urban gap, imposter syndrome)
"""

SYSTEM_PROMPT = """You are India's most empathetic and honest career counsellor. You have guided 20,000+ students from every tier of Indian engineering colleges. You understand:

- The real pressure Indian students face from family, peers, and society
- The difference between "not placed YET" and "not placeable"
- How co-curricular activities genuinely signal skills to employers
- That a "Low" placement score today is not a life sentence
- Alternative career paths that are genuinely viable and respected in India

You are honest without being cruel. You are encouraging without being dishonest. You speak like a trusted senior who has seen it all."""


def build_career_path_prompt(
    cgpa: float,
    skills: list,
    college_tier: str,
    year: str,
    target_roles: list,
    target_companies: list,
    co_curricular: list,
    achievements: list,
    certifications: list,
    placement_label: str,
    ats_score: int,
    placement_low: int,
    placement_high: int,
    ats_weaknesses: list,
    missing_keywords: list,
    company_fit: dict = None,
) -> str:
    skills_str     = ", ".join(skills)          if skills          else "Not specified"
    roles_str      = ", ".join(target_roles)    if target_roles    else "Software Engineer"
    companies_str  = ", ".join(target_companies) if target_companies else "top tech companies"
    cocurr_str     = "\n".join(f"  • {c}" for c in co_curricular)  if co_curricular  else "  • None mentioned"
    achiev_str     = "\n".join(f"  • {a}" for a in achievements)   if achievements   else "  • None mentioned"
    certs_str      = "\n".join(f"  • {c}" for c in certifications) if certifications else "  • None"
    weak_str       = ", ".join(ats_weaknesses)   if ats_weaknesses  else "None critical"
    missing_str    = ", ".join(missing_keywords) if missing_keywords else "None critical"

    tier_map = {
        "tier1": "Tier 1 (IIT/NIT/BITS)",
        "tier2": "Tier 2 (State engineering college)",
        "tier3": "Tier 3 (Private college)",
    }
    tier_label = tier_map.get(college_tier, college_tier)

    company_fit_str = ""
    if company_fit:
        company_fit_str = f"""
Company Fit Scores (from placement analysis):
  Service companies (TCS/Infosys/Wipro): {company_fit.get('service_companies', 'Unknown')}
  Mid-product (Zoho/Freshworks/Razorpay): {company_fit.get('mid_tier_product', 'Unknown')}
  Top product (Amazon/Google/Flipkart): {company_fit.get('top_product', 'Unknown')}"""

    return f"""{SYSTEM_PROMPT}

━━━ COMPLETE STUDENT PROFILE ━━━
College Tier    : {tier_label}
Year            : {year}
CGPA            : {cgpa}/10
Skills          : {skills_str}
Target Roles    : {roles_str}
Target Companies: {companies_str}
Placement Label : {placement_label} ({placement_low}%–{placement_high}% probability)
ATS Score       : {ats_score}/100

Co-curricular Activities:
{cocurr_str}

Achievements:
{achiev_str}

Certifications:
{certs_str}

Resume Weaknesses: {weak_str}
Missing Keywords : {missing_str}
{company_fit_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

YOUR TASKS:

━━━ TASK 1: REALITY CHECK ━━━
Be honest about whether this student can realistically land at their target companies.
Consider:
- Is their CGPA above typical cutoffs for their targets?
- Does their college tier give them access to those companies' campus drives?
- Are their skills matching what those companies actually hire for?
- What is the REALISTIC timeline: 1 month? 3 months? 6 months? 1 year?

DO NOT be falsely encouraging. If they're targeting Google with a 5.8 CGPA from a Tier 3 college and basic HTML skills, say that clearly — and then explain what IS achievable.

━━━ TASK 2: CO-CURRICULAR ANALYSIS ━━━
Analyse their activities and achievements as an employer would.
Indian employers read co-curriculars as signals of:
- Leadership (club president, organiser → management potential)
- Domain passion (robotics club, coding club → technical depth)
- Communication (debates, MUN, cultural events → client-facing fit)
- Entrepreneurship (college startup, freelancing → startup ecosystem)
- Community (NSS, volunteering → culture fit for social mission companies)

If they have NO co-curriculars: recommend 2-3 specific, high-ROI activities to join NOW.
If they have strong ones: show how to use them in interviews and resume.

━━━ TASK 3: ALTERNATIVE CAREER PATHS ━━━
If their primary target (e.g., "SDE at Google") is unrealistic within 3 months,
suggest 2-3 REAL alternative paths that ARE achievable given their profile.

India-specific alternatives to consider:
- Data Analyst (SQL + Excel + basic Python → very achievable, great demand)
- DevOps/Cloud (AWS certifications → high demand, less competitive than SDE)
- QA/SDET (underrated, good salary, less DSA pressure)
- Business Analyst (communication skills + Excel → suits non-coders)
- Product Management (MBA path or APM programs for engineers)
- Government tech jobs (CDAC, NIC, state IT corporations — stable, respectable)
- Startup ecosystem (early-stage startups hire without rigid CGPA cutoffs)
- Freelancing → portfolio → full-time (Upwork, Toptal, local agencies)
- Higher education (GATE → M.Tech, GRE → MS abroad, CAT → MBA)

For each alternative, give: what it is, why this student specifically fits, how to start, expected timeline, salary range in India.

━━━ TASK 4: PERSONALISED MOTIVATION ━━━
Write motivation that is SPECIFIC to this student's exact situation.
NOT generic: "Keep trying, you'll get there!"
YES specific: "A 6.2 CGPA from a Tier 3 college kept 50 applications silent for Rohan Sharma. He spent 90 days solving 200 LeetCode problems, deployed 2 projects, and got a ₹12 LPA offer from a Bangalore startup. Your numbers are almost identical to his starting point."

Reference:
- Their specific college tier reality (don't sugarcoat tier disadvantages)
- Their specific CGPA and what it unlocks/blocks
- Their specific skills and what they make possible
- Indian placement reality (not US tech narratives)
- The specific gap between where they are and where they want to be

If their profile is strong: celebrate it specifically and push them harder.
If their profile is weak: be the mentor who tells the truth AND shows the path.

Return ONLY this JSON:
{{
  "reality_check": {{
    "target_company_verdict": "<'Achievable now' | 'Achievable in 3 months' | 'Achievable in 6-12 months' | 'Requires major repositioning'>",
    "honest_assessment": "<2-3 sentences of honest, specific assessment of their target company fit>",
    "what_is_blocking": ["<specific blocker 1>", "<specific blocker 2>"],
    "what_is_working": ["<specific positive 1>", "<specific positive 2>"],
    "realistic_timeline": "<Specific timeline to first offer at their target type of company>"
  }},
  "co_curricular_insights": {{
    "signals_to_employers": "<What their activities signal — specific, not generic>",
    "strongest_activity": "<Their most impressive activity and how to leverage it>",
    "how_to_use_in_interview": "<Specific advice on how to talk about activities in interviews>",
    "recommended_activities": [
      {{
        "activity": "<specific activity name>",
        "why": "<why this student specifically would benefit>",
        "how_to_join": "<specific platform or step to join>"
      }}
    ]
  }},
  "primary_path": {{
    "title": "<their stated target role>",
    "fit_score": <0-100>,
    "verdict": "<honest one-line verdict>",
    "to_make_it_happen": ["<specific step 1>", "<specific step 2>", "<specific step 3>"]
  }},
  "alternate_paths": [
    {{
      "title": "<alternative career title>",
      "why_this_student": "<why this specific student is a good fit>",
      "fit_score": <0-100>,
      "salary_range": "<e.g. '₹4-8 LPA fresher' or '₹25,000-40,000/month'>",
      "how_to_pivot": "<specific first 3 steps to move toward this path>",
      "timeline": "<realistic timeline to first opportunity>",
      "example_companies": ["<company 1>", "<company 2>", "<company 3>"]
    }}
  ],
  "motivation": {{
    "headline": "<One punchy, specific headline sentence — not generic>",
    "body": "<3-4 sentences of specific, personalised motivation referencing their exact profile — CGPA, college, skills, activities. Write for an Indian student. Acknowledge the real pressure they face. End with the single most important thing they should do tomorrow morning.>",
    "tomorrow_action": "<The one thing they should do tomorrow at 9am. Specific: not 'improve DSA' but 'Open LeetCode, go to Arrays section, solve Two Sum and Best Time to Buy Stock. Set a 1-hour timer.'>",
    "role_model_path": "<Brief story of a real or composite student with similar profile who got placed. Make it specific: college tier, CGPA, what they did, where they landed.>"
  }}
}}"""
