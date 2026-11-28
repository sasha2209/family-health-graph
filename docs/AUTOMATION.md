# Build → review → merge, without manual merges

```
 builder agent (a Claude Code session)        GitHub Actions (.github/workflows/ci.yml)
 ─────────────────────────────────────        ───────────────────────────────────────────────
 branch claude/<feature>, commit, push  ───▶  Backend tests · Mobile checks · Docker image
 open PR as draft, run its own checks                     │
 mark "Ready for review"                ───▶  Review agent (Claude) reads the diff, comments,
                                              returns approve / request_changes
 on "changes requested": fix and push ◀───                │
   (every push re-runs tests + review)                    ▼
                                              Merge agent: tests green + approved + same commit
                                              + no `hold` label  ──▶  merged into main
                                                                    ──▶  Render deploys main
```

## What each agent does

| Agent | Where it runs | Job |
|---|---|---|
| **Builder** | A Claude Code session (cloud or local) | Implements a request on a `claude/…` branch with tests, opens a draft PR, marks it ready once its own checks pass, and answers review comments |
| **Review agent** | `review` job, `anthropics/claude-code-action@v1` | Reads the diff; checks correctness, health-data privacy and security (encryption, consent, authorization, audit), tests and docs; leaves inline comments; returns a verdict. Only bugs, security/privacy problems, data loss or untested logic block. It can read the repo and the PR, nothing else |
| **Merge agent** | `merge` job | Merges only if backend, mobile and Docker jobs passed, the review approved, the PR is still open, not a draft, unchanged since the review, and has no `hold` label. Deletes the branch afterwards |

## One-time setup (repository owner)

1. **Add the API key secret:** GitHub → the repository → Settings → Secrets and variables → Actions →
   *New repository secret* → name `ANTHROPIC_API_KEY`. Without it the review job fails, and nothing is merged.
2. **The Claude GitHub App** must be installed on the repository (it already is if Claude Code sessions can push
   here). The review agent uses it to post comments.
3. Optional but recommended: Settings → Branches → add a rule for `main` that **requires the "Merge agent"
   check** and blocks direct pushes, so every change goes through this loop.

## Controls

- **Stop one PR:** add the `hold` label (remove it and push, or re-run the workflow, to continue).
- **Pause all auto-merging:** Settings → Actions → disable the workflow, or delete the `merge` job.
- **Draft PRs** get tests but no review or merge. Ready PRs from forks or from people without write access are
  never reviewed with the secret or merged.
- Cost: one review per push to a ready PR, with up to 40 turns on `claude-opus-5-5`. Change `--model` in
  `ci.yml` to use a cheaper model.
