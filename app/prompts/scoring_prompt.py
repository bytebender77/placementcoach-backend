"""
PROMPT 2: Placement Probability Scoring
=========================================
Purpose  : Give a realistic placement probability range — not a single number.
           A range is intentional: it's honest, and it gives students a target to move
           from the lower bound to the upper bound.
Model    : gpt-4o-mini
Mode     : JSON mode
Temp     : 0.3  (slightly higher than ATS — we want some reasoning variation)
Max tok  : 1000

Design decisions
----------------
- We pass the rule-based BASE SCORE as an anchor. This is critical prompt engineering:
  it gives GPT a starting reference, reducing hallucinated extreme scores.
  GPT is told to adjust ±15 points from it, not generate from scratch.
- We pass RESUME TEXT (first 2000 chars) so GPT can see actual content, not just metadata.
- We explicitly enumerate India-specific factors GPT should consider.
- Range is forced to 15–25 points wide — prevents GPT from saying "75%–76%" (useless)
  or "10%–90%" (meaningless).
- `reasoning` is written for the STUDENT, not the recruiter. Plain language, no jargon.
- `top_positive_signals` and `top_risk_factors` feed directly into dashboard cards.

India-specific calibration
--------------------------
- CGPA cutoffs: many companies (TCS, Infosys, Wipro) have hard 60% / 6.0 CGPA cutoffs.
  GPT must know this — a 5.8 CGPA student has near-zero chance at these companies
  even with great skills.
- Tier reality: Tier 2/3 students rarely get on-campus drives from product companies.
  Off-campus + referral is their path. GPT must mention this.
- DSA weight: For product companies (Amazon, Flipkart, Juspay, etc.) DSA on LeetCode
  is ~70% of the hiring signal. A Tier 3 student with 300 LeetCode problems solved
  will beat a Tier 1 student with none.
- Internship signal: Even a small startup internship on the resume is a massive positive
  signal for Indian campus placements — it breaks the "no experience" catch-22.
"""

SYSTEM_PROMPT = """You are India's most experienced campus placement consultant. You have mentored over 15,000 students from IITs, NITs, state colleges, and private engineering colleges across India. You have deep knowledge of:

- How Indian companies actually hire (TCS mass recruitment vs Amazon SDE interviews)
- The real weight of CGPA, college tier, and skills in Indian placements
- What separates placed vs unplaced students at Tier 2/3 colleges
- Off-campus strategies, referral networks, and mass recruitment drives in India
- How LeetCode/GFG performance translates to placement outcomes

You are honest. You give realistic assessments, not false hope. But you are also encouraging — you always explain what the student can do to improve their chances."""


def build_scoring_prompt(
    resume_text: str,
    cgpa: float,
    skills: list,
    college_tier: str,
    year: str,
    target_roles: list,
    target_companies: list,
    base_score: dict,        # from rule-based scorer — used as anchor
) -> str:
    skills_str    = ", ".join(skills)
    roles_str     = ", ".join(target_roles)     if target_roles     else "Software Engineer / Analyst"
    companies_str = ", ".join(target_companies) if target_companies else "product and service companies"

    tier_labels = {
        "tier1": "Tier 1 (IIT / NIT / BITS / IIIT)",
        "tier2": "Tier 2 (State govt. / reputed private college)",
        "tier3": "Tier 3 (Other private college)",
    }
    tier_label = tier_labels.get(college_tier, college_tier)

    year_labels = {
        "fresher": "Fresher (2024 graduate, currently job hunting)",
        "2nd":     "2nd Year (2 years left before graduation)",
        "3rd":     "3rd Year (1 year left, internship season approaching)",
        "4th":     "Final Year (placement season now)",
    }
    year_label = year_labels.get(year, year)

    resume_trimmed = resume_text[:2000].strip()

    return f"""━━━ STUDENT PROFILE ━━━
College Tier : {tier_label}
Academic Year: {year_label}
CGPA         : {cgpa}/10
Skills       : {skills_str}
Target Roles : {roles_str}
Companies    : {companies_str}

━━━ RESUME CONTENT (first 2000 chars) ━━━
{resume_trimmed}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ RULE-BASED BASELINE (use as anchor — adjust with your expert judgment) ━━━
Base score        : {base_score['base_score']}/100
Suggested range   : {base_score['placement_low']}% – {base_score['placement_high']}%
Initial label     : {base_score['label']}
CGPA sub-score    : {base_score['breakdown']['cgpa_score']}/40
Skills sub-score  : {base_score['breakdown']['skills_score']}/40
College weight    : {base_score['breakdown']['tier_weight']}x
Year weight       : {base_score['breakdown']['year_weight']}x
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EVALUATION FACTORS (India-specific, weighted)
=============================================

1. CGPA ANALYSIS (high weight)
   - Below 6.0 CGPA: FILTERED by TCS, Infosys, Wipro, Accenture, Cognizant automatically.
     Mass-recruitment doors are largely closed. Score accordingly.
   - 6.0–7.0: Passes most service company filters. Struggles at product companies.
   - 7.0–8.0: Good. Opens doors at mid-tier product companies and good service companies.
   - 8.0–9.0: Strong signal. Competitive for most companies.
   - Above 9.0: Excellent, but rarely the only differentiator above 8.5.

2. COLLEGE TIER REALITY
   - Tier 1: On-campus drives from top companies. Alumni network strong. Dream companies accessible.
   - Tier 2: Some on-campus drives. Off-campus + referrals critical. 
     Strong skills can overcome tier disadvantage.
   - Tier 3: Very few on-campus product company drives. 
     Must rely on off-campus (Unstop, Naukri, LinkedIn, referrals).
     However: Tier 3 students with strong DSA + projects DO get placed at product companies off-campus.

3. SKILLS QUALITY (check resume content)
   - DSA / Competitive Programming: Most critical for product companies. 
     Look for LeetCode, Codeforces, CodeChef mentions. Absence is a red flag.
   - Core CS: DBMS, OS, Computer Networks, OOPS — asked in every Indian company interview.
   - Projects: Are they deploy-worthy (with live link / GitHub)? Or just tutorial clones?
   - Internships: Even one internship (startup/remote) dramatically improves chances.
   - Certifications: Google, AWS, Coursera — modest positive signal.

4. TARGET COMPANY REALITY
   - Service companies (TCS, Infosys, Wipro, Accenture, Cognizant, HCL):
     Low bar for skills, high bar for CGPA cutoff. Mass recruiter.
   - Mid-tier product (Zoho, Freshworks, Razorpay, Juspay, Chargebee):
     Strong DSA + 1-2 good projects. College tier less important.
   - Top product (Amazon, Google, Microsoft, Flipkart, Zomato, Swiggy):
     Exceptional DSA required. Tier 2/3 students rarely land here without referrals.

5. YEAR-SPECIFIC ADVICE
   - Fresher: Time is limited. Focus on immediate off-campus applications.
   - 2nd Year: 2 years to fix everything. Most room to improve.
   - 3rd Year: Internship season is now. This is the most critical placement signal.
   - 4th Year: Placement season. Assess as-is, but highlight quick wins.

SCORING RULES
=============
- Your range MUST span 15–25 percentage points (e.g., 40%–60%, not 48%–52%)
- Adjust from baseline range by maximum ±20 points based on resume evidence
- If CGPA < 6.0: cap placement_high at 35% regardless of other factors
- If no projects AND no internships: reduce range by 10 points
- If strong DSA evidence (LeetCode/CF mentions): increase range by 5–10 points
- If college is Tier 3 AND targeting top-product companies: add explicit note in reasoning

LABEL DEFINITIONS
=================
"Strong"   → 65%+ high-end. Student is well-positioned. Minor polish needed.
"Good"     → 50–65% high-end. Solid foundation. Specific gaps to address.
"Moderate" → 35–50% high-end. Real work needed. Achievable with 4–8 weeks of effort.
"Low"      → Below 35% high-end. Significant gaps. Needs structured 3–6 month effort.

OUTPUT FORMAT
=============
Return ONLY this JSON. No preamble, no markdown.

{{
  "placement_low"  : <integer — lower bound percentage>,
  "placement_high" : <integer — upper bound percentage, must be 15–25 more than low>,
  "label"          : "<'Low' | 'Moderate' | 'Good' | 'Strong'>",
  "reasoning"      : "<2–3 sentences in plain language the student can understand. Mention their specific situation — college, CGPA, skills. Be honest and direct, not corporate-speak. Example: 'With a 7.2 CGPA from a Tier 2 college and solid Python skills, you're well-positioned for service companies like TCS and Infosys. Your main gap for product companies is DSA — no LeetCode or competitive programming is visible on your resume.'>",
  "top_positive_signals": [
    "<specific thing working in their favour — from the actual resume/profile>",
    "<specific signal — max 3>"
  ],
  "top_risk_factors": [
    "<specific thing holding them back — be honest>",
    "<specific risk — max 3>"
  ],
  "company_fit": {{
    "service_companies"      : "<'High' | 'Medium' | 'Low'> — TCS, Infosys, Wipro class",
    "mid_tier_product"       : "<'High' | 'Medium' | 'Low'> — Zoho, Freshworks class",
    "top_product"            : "<'High' | 'Medium' | 'Low'> — Amazon, Flipkart class"
  }},
  "fastest_improvement"      : "<ONE specific action that would most increase their probability in the next 30 days>"
}}"""
