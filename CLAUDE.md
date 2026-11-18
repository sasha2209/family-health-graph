# Working in this repository

- Backend: `python -m pytest -q`. Mobile: `cd mobile && npm run typecheck && npm run lint && npm test`.
  Expo installs need `EXPO_OFFLINE=1` in sandboxes without access to api.expo.dev.
- Health data rules: everything stored is encrypted with `FieldCipher`; every endpoint checks the caller owns
  the data; access and changes are audit-logged; nothing identifiable goes to partners or AI providers without
  the user's consent scope.

## Shipping a change (see docs/AUTOMATION.md)

1. Work on a `claude/<feature>` branch with tests, and open the PR as a **draft**.
2. When your own checks pass and CI is green, **mark it ready for review**. Do not merge it yourself.
3. The review agent comments and approves or requests changes; the merge agent merges approved, green PRs.
4. If changes are requested, fix them on the same branch and push; the review runs again.
