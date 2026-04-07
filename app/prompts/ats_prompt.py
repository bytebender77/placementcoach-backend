"""
PROMPT 1: ATS Resume Analysis
==============================
Purpose  : Score the resume against Indian ATS systems + give actionable feedback
Model    : gpt-4o-mini
Mode     : JSON mode (response_format: json_object)
Temp     : 0.2  (low — we want consistent, reliable scoring)
Max tok  : 1200

Design decisions
----------------
- System prompt sets the persona hard: "Indian ATS expert". GPT respects domain framing.
- We pass target_roles + target_companies so keywords are role-specific, not generic.
- Rubric is explicit and numerical — prevents GPT from giving vague mid-range scores.
- We explicitly say "Do not invent" — reduces hallucination of skills not in resume.
- Output schema is tightly specified. Every field has a type + constraint.
- `one_line_verdict` is the most human-readable field — shown prominently on dashboard.
- `formatting_issues` is separate from weaknesses — actionable for resume redesign.

India-specific calibration
--------------------------
- Keywords list biased toward what Indian companies actually filter on:
  DSA, OOPS, DBMS, OS, CN (core CS), not western buzzwords like "agile transformation"
- Mentions GFG, LeetCode — proxies for DSA strength that Indian ATS/HR recognise
- Score bands mapped to Indian placement reality (not US SWE reality)
- Checks for common Indian resume anti-patterns: photo, DOB, marital status
"""

SYSTEM_PROMPT = """You are an expert Applicant Tracking System (ATS) evaluator and resume screener with 12 years of experience in Indian campus placements. You have reviewed over 50,000 resumes for companies like TCS, Infosys, Wipro, Cognizant, Accenture, Amazon India, Flipkart, Zomato, Paytm, Juspay, and hundreds of Indian startups.

You understand exactly how Indian ATS systems filter resumes and what Indian HR screeners look for in the first 6-second scan. You are honest, direct, and specific — you do not give generic advice."""


def build_ats_prompt(
    resume_text: str,
    target_roles: list,
    target_companies: list,
) -> str:
    roles_str     = ", ".join(target_roles)     if target_roles     else "Software Engineer / Analyst"
    companies_str = ", ".join(target_companies) if target_companies else "top Indian product and service companies"

    # Truncate resume to 3000 chars — beyond this, GPT degrades. Most resumes are 1-2 pages.
    resume_trimmed = resume_text[:3000].strip()

    return f"""Analyse the following resume for a student targeting: {roles_str}
Target companies: {companies_str}

━━━ RESUME TEXT ━━━
{resume_trimmed}
━━━━━━━━━━━━━━━━━━

EVALUATION FRAMEWORK
====================

Score the resume on these 5 dimensions (then compute overall ats_score):

1. KEYWORD MATCH (0–25 pts)
   For {roles_str}:
   - Are key technical skills present? (languages, frameworks, tools)
   - Are core CS fundamentals mentioned? (DSA, OOPS, DBMS, OS, CN if applicable)
   - Are relevant domain keywords present for {companies_str}?
   - Missing high-value keywords get flagged

2. STRUCTURE & PARSABILITY (0–20 pts)
   Indian ATS systems struggle with:
   - Tables, columns, text boxes (score down if present)
   - Headers that don't match standard section names (Education, Experience, Projects, Skills)
   - Images, graphics, charts embedded in PDF
   - Fonts that may not parse correctly
   Check: Does the resume have clear, named sections?

3. CONTENT QUALITY (0–25 pts)
   - Projects: Are they real projects with outcomes, or just tutorial copies?
   - Experience: Are internships from recognised companies/startups?
   - Achievements: Are they quantified? (improved performance by X%, reduced Y by Z)
   - Education: CGPA present? Relevant coursework listed?

4. INDIA RED FLAGS (0–15 pts, lose points for each flag)
   Deduct for: photo on resume, date of birth, marital status, father's name,
   "Objective" section with generic text, no GitHub/LinkedIn, 3+ page resume for fresher,
   spelling/grammar errors, fake-sounding project names

5. ATS FORMATTING (0–15 pts)
   - File naming (should be "FirstName_LastName_Resume.pdf")
   - Single column layout (ATS-safe)
   - Standard fonts (Times New Roman, Calibri, Arial — not decorative)
   - No headers/footers with critical info
   - Proper date formats (Month Year, not DD/MM/YYYY)

SCORING SCALE
=============
90–100 : Exceptional. Will pass every Indian ATS. HR will call same day.
75–89  : Strong. Passes most ATS. Minor tweaks recommended.
60–74  : Average. Will pass ~60% of ATS filters. Needs targeted keyword additions.
45–59  : Below average. Will be filtered by strict ATS. Significant work needed.
0–44   : Poor. Major structural or content issues. Needs complete rework.

OUTPUT FORMAT
=============
Return ONLY this JSON. No preamble, no markdown, no explanation outside JSON.

{{
  "ats_score": <integer 0–100, computed from 5 dimensions above>,
  "dimension_scores": {{
    "keyword_match": <0–25>,
    "structure_parsability": <0–20>,
    "content_quality": <0–25>,
    "india_red_flags": <0–15>,
    "ats_formatting": <0–15>
  }},
  "strengths": [
    "<specific strength — mention actual content from resume, not generic praise>",
    "<specific strength>",
    "<specific strength — max 4 items>"
  ],
  "weaknesses": [
    "<specific weakness — say WHAT is missing or wrong, not just 'improve your resume'>",
    "<specific weakness>",
    "<specific weakness — max 4 items>"
  ],
  "missing_keywords": [
    "<keyword critical for {roles_str} that is NOT in resume>",
    "<keyword>",
    "<keyword — list 5–8 most impactful missing keywords only>"
  ],
  "formatting_issues": [
    "<specific formatting problem if any — e.g. 'Resume uses 2-column layout which breaks most ATS parsers'>",
    "<max 3 items — omit this list if no issues>"
  ],
  "india_red_flags_found": [
    "<e.g. 'Photo included on resume — remove immediately'>",
    "<e.g. 'Date of birth present — not required by Indian companies post-2020'>",
    "<omit list if none found>"
  ],
  "one_line_verdict": "<One honest sentence a student can understand. Example: 'Your resume has strong projects but is missing core CS keywords that TCS and Infosys ATS systems specifically filter for.'>"
}}"""
