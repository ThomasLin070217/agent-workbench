# Explicit development/review pilot

`pilot.py` dispatches one explicitly approved task turn to a native Codex or local DeepSeek Harness session. It records start/result/failure receipts under ignored `.state/pilot/` and forwards the result to the existing SharedNet Room using stable request IDs. It is a local coordinator command, not an internet-facing scheduling API.

Example (use an existing isolated worktree and your approved prompt file):

```sh
python3 pilot.py --agent codex --task TASK-EXAMPLE-001 \
  --workspace /absolute/path/to/development-worktree \
  --prompt /absolute/path/to/approved-task.txt --turn 1 --write
python3 pilot.py --agent deepseek-harness --task TASK-EXAMPLE-001-REVIEW \
  --workspace /absolute/path/to/reviewer-worktree \
  --prompt /absolute/path/to/review-task.txt --turn 1
```

For a correction/re-review, keep task, agent and workspace fixed, increment `--turn`, and supply the follow-up prompt. The native session ID is reused. Do not rerun a failed or uncertain delivery blindly: first inspect the local record and native conversation. A new turn number means a new deliberate instruction, not an automatic retry.

Codex development can explicitly opt into workspace-write; review Codex remains read-only. DeepSeek review uses its existing local Harness configuration and a read-only task instruction, not an independently enforced new sandbox. Review runs in a separate worktree; the coordinator must verify source cleanliness and candidate commit identity.

The coordinator still owns worktree creation, assigning roles, interpreting review findings, staging/committing changes, merge gating, post-merge tests, and marking user acceptance. This command does not implement a general autonomous scheduler, native GUI turn arbitration, or automatic extraction of human follow-ups. Round completion must not be displayed as project completion.

The viewer can show a trusted local artifact URL and an explicit workflow status stored in the session index. Only token-free `http://127.0.0.1:<port>` artifact links are allowed. Set an artifact link only after its server is running and verified; use a separate “awaiting user acceptance” state for interactive deliverables.

Room messages forwarded by this command are posted by the coordinator's brain seat and explicitly identify the source Harness; they do not impersonate the agent's native Room identity. A failed Room delivery leaves the local receipt and delivery error for recovery.

Forwarded report mentions are neutralized with a zero-width separator so quoted model output cannot inadvertently dispatch another fixed Room seat. The local receipt retains the exact report.
