# PlacementCoach — Prompt Engineering Notes
# ==========================================
# Read this before touching any prompt.

## Core principle: Prompts are your product moat

The code (FastAPI, React, S3) can be copied overnight.
The prompts — tuned for Indian placements, calibrated on real profiles,
with the right scoring rubrics — are what make PlacementCoach genuinely useful.
Version-control them. A/B test them. Log the inputs + outputs.

---

## Architecture: Why 3 separate prompts instead of 1 big prompt?

We deliberately split into 3 separate API calls (ATS + Scoring + Plan) for these reasons:

1. PARALLEL EXECUTION — ATS and Scoring run in asyncio.gather() simultaneously.
   One combined prompt would be sequential and slower.

2. SPECIALISATION — Each prompt has a laser-focused persona and rubric.
   GPT performs better when the task scope is narrow and well-defined.

3. FAILURE ISOLATION — If the ATS call fails, we still have the scoring result.
   With a monolithic prompt, one failure = total failure.

4. ITERATION SPEED — You can improve the plan prompt without touching the ATS prompt.
   Clean separation = faster shipping.

5. COST CONTROL — In v2 you might use GPT-4o (expensive) for the plan but
   gpt-4o-mini for ATS scoring. Separation makes this trivial.

---

## Prompt design patterns used

### 1. Persona anchoring (System prompt)
Every prompt starts with a strong persona statement.
"You are India's most experienced campus placement consultant who has mentored 15,000 students."
This is not vanity — it materially affects output quality. GPT performs better when
grounded in a specific domain persona with quantified experience.

### 2. Explicit rubrics with numbers
Bad: "Score the resume from 0-100"
Good: "Score the resume on 5 dimensions: Keyword Match (0-25 pts), Structure (0-20 pts)..."
Rubrics with numerical breakdowns produce consistent, defensible scores.

### 3. Baseline anchoring (Scoring prompt)
We pass the rule-based score as a reference: "Suggested range: 35%–55%"
This is a form of in-context calibration. Without this anchor, GPT may produce
wildly inconsistent scores across similar profiles.
GPT then adjusts ±15 points based on resume evidence.
Result: much tighter variance in outputs.

### 4. Anti-hallucination instructions
"Do NOT invent experience or skills not present in the resume."
"Adjust from baseline range by maximum ±20 points."
These hard constraints prevent GPT from making up LeetCode profiles or inventing internships.

### 5. Negative examples (Plan prompt)
We show GPT what BAD output looks like alongside GOOD:
✗ BAD: "Practice DSA"
✓ GOOD: "Solve 15 LeetCode Easy problems on Arrays (Two Sum, Valid Anagram)..."
Negative examples are as important as positive examples for output quality.

### 6. Output schema as part of the prompt
We specify exact JSON field names, types, and constraints inside the prompt.
"placement_high must be 15–25 more than placement_low"
This produces cleaner, more parseable JSON than leaving structure to GPT.

### 7. India-specific grounding
Generic prompts produce generic advice.
Specific platform names (GFG, Unstop, InterviewBit, Internshala) produce India-relevant plans.
Company-tier knowledge (TCS CGPA cutoffs, Tier 3 off-campus reality) produces honest assessments.

---

## A/B variants to test in v2

### ATS Prompt A/B Tests

Variant A (current): One comprehensive prompt with 5-dimension rubric
Variant B: Two separate prompts — one for keyword analysis, one for formatting
Variant C: Include a "competitor resume" example as few-shot
Hypothesis: Variant A is fastest to implement. Variant C likely produces most specific feedback.

### Scoring Prompt A/B Tests

Variant A (current): Rule-based baseline passed as anchor
Variant B: No baseline — pure GPT judgment
Variant C: Pass 3 historical scores from similar profiles as few-shot examples
Hypothesis: Variant A produces least variance. Variant C may produce better calibration long-term.

### Plan Prompt A/B Tests

Variant A (current): 6-week plan, all weeks upfront
Variant B: 2-week plan first, then generate next 2 when student completes week 2
Hypothesis: Variant B has higher completion rates (shorter = less overwhelming) but requires
streaming/stateful UX. Build in v2 when you have user completion data.

Variant A-tone: Direct coach voice ("You need to solve 200 LeetCode problems")
Variant B-tone: Gentle guide voice ("A great starting point would be...")
Hypothesis: Test with different college tier users. Tier 1 students may prefer direct.
           Tier 3 students facing imposter syndrome may need gentler tone.

---

## Measuring prompt quality

Track these metrics per prompt version (log to DB):

1. ATS score distribution — should follow bell curve, not bimodal
2. Placement probability distribution — should vary meaningfully across CGPA tiers
3. Plan task specificity score — count generic phrases (run prompt_eval.py weekly)
4. User engagement — do users read all 6 weeks? (add click tracking on week headers)
5. "Was this useful?" — simple thumbs up/down after each section (v2)
6. Placement outcome — did the student get placed? (v3 — follow-up email 3 months later)

---

## Token cost estimates (gpt-4o-mini pricing, April 2025)

ATS prompt:
  Input:  ~800 tokens × $0.15/1M = $0.00012
  Output: ~400 tokens × $0.60/1M = $0.00024
  Total:  ~$0.00036 per ATS call

Scoring prompt:
  Input:  ~900 tokens × $0.15/1M = $0.000135
  Output: ~300 tokens × $0.60/1M = $0.00018
  Total:  ~$0.000315 per scoring call

Plan prompt:
  Input:  ~1000 tokens × $0.15/1M = $0.00015
  Output: ~700 tokens × $0.60/1M = $0.00042
  Total:  ~$0.00057 per plan call

TOTAL per user analysis: ~$0.00125 (~₹0.10 per full analysis)
At 1000 analyses/day: ~$1.25/day in OpenAI costs. Completely negligible.

---

## Version history (keep this updated)

v1.0 (launch)
  - 3-prompt architecture
  - Rule-based scoring baseline as anchor
  - India-specific platform references
  - 6-week fixed plan structure

v1.1 (planned)
  - Add few-shot examples to ATS prompt (3 sample resumes + scores)
  - Add `company_fit` object to scoring output → shown as 3-badge row on dashboard
  - Add `formatting_issues` to plan prompt input (it's already in prompt_eval but not wired)

v1.2 (planned)
  - Stream plan generation (show weeks as they arrive)
  - Add resume section detection (Education/Experience/Skills extraction)
  - Use extracted sections as structured input to all 3 prompts
