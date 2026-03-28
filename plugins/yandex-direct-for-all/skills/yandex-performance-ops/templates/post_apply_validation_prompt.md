# Post Apply Validation Prompt

Role: post-apply validator.

Goal:
- verify that applied changes match the plan and did not create regressions.

Inputs:
- pre-apply snapshot
- post-apply snapshot
- `campaign_autotest.py` output
- `change_tracker.py` output
- live API state

Output:
- markdown validation report

Check:
- intended entities changed
- no unrelated breakage
- no target keywords blocked by negatives
- no wrong group copy duplication
- no missing extensions/settings

