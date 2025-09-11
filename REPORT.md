# Branch Protection Checklist (Manual GitHub UI)

Follow these steps to enable required status checks and reviews for the `main` branch:

1. Open repository Settings
   - Navigate to: Settings → Branches

2. Create or edit a rule for `main`
   - Click “Add rule” (or edit the existing rule) and set Branch name pattern to `main`.

3. Require status checks to pass before merging
   - Check “Require status checks to pass before merging”.
   - In the list of checks, enable:
     - CI
     - Cross-Repo Smoke (Trading)

4. Require pull request reviews before merging
   - Check “Require a pull request before merging”.
   - Optionally enable:
     - Require approvals (e.g., 1 or more)
     - Dismiss stale approvals when new commits are pushed
     - Require review from Code Owners (ensures contracts/\*\* changes ping @JSunRae)

5. (Optional) Additional protections
   - Require conversation resolution before merging
   - Require linear history
   - Lock branch (admins only)

6. Save changes
   - Click “Create” or “Save changes”.

Notes

- The CI and Cross-Repo Smoke badges are visible in README for quick status.
- CODEOWNERS enforces review on `contracts/**` by @JSunRae.
