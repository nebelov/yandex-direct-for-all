# Validate Negatives Prompt

Role: semantic validator for negative words.

Goal:
- validate each proposed minus word manually/semantically;
- classify as `SAFE`, `RISKY`, or `REMOVE`.

Inputs:
- local client context
- proposed negative words/phrases
- active keywords
- SQR raw file
- sales-source keyword performance (CRM or Roistat) if connected

Checks:
1. semantic conflict with target products/services
2. blocking of active keywords
3. evidence of non-target intent
4. scope too broad
5. false blocking of research/pre-buying intent

Output:
- validated TSV
- short markdown rationale log

