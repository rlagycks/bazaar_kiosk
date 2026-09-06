# Safe Git recovery strategy

Last verified: 2026-09-06

## What is actually tangled

The source tree at `origin/main` and `origin/develop` is identical, but the branch
tips are not ancestors of each other. Their histories contain repeated feature,
merge, and conflict-resolution lines. This is graph complexity rather than a
large-object problem: the packed repository is small and the inspected tips share
one tree.

This means an urgent history rewrite is unnecessary. A clean working convention
can begin without changing old commit IDs or breaking links to existing PRs.

## Recommended path: preserve, designate, archive

Use this option unless a content-level secret scan proves that published history
must be rewritten.

1. Finish the analysis and verify that `main` and `develop` still have equivalent
   release content.
2. Choose one canonical branch in `DECISIONS.md`. `main` is the conventional
   recommendation, but the current GitHub default is `develop`, so this is a user
   and repository-settings decision.
3. Create immutable annotated snapshot tags for both pre-modernization tips.
4. Protect the canonical branch, require CI, disable direct pushes, and choose
   squash merging for modernization PRs.
5. Build each blueprint phase on a short-lived branch or worktree from the
   canonical tip.
6. After all owners confirm that stale branches contain no unique work, archive
   their tip SHAs/tags and delete the remote branches in one separately approved
   maintenance operation.
7. Keep the old commit graph available for archaeology; do not merge the obsolete
   branch lines back into the modernized branch.

No remote ref, tag, default branch, or protection setting has been changed by the
preparation work.

## Alternative: clean v2 history

Create a new repository or an orphan `v2` branch from the verified tree only when
the user values a clean history more than old blame, commit links, and PR ancestry.
Keep the original repository read-only as an archive. Document the old repository
URL and tip SHAs in the new history.

This option is reasonable for a true product reboot, but it is not required for
technical modernization and must not be mixed casually with an incremental
refactor.

## History rewrite: exceptional only

Use `git filter-repo` or force-push only to remove confirmed sensitive material or
for another explicit, reviewed requirement. Before any rewrite:

- capture a mirror backup and exact ref inventory;
- run a content-level secret scan across all refs;
- produce old-to-new commit/ref mapping;
- define collaborator re-clone instructions;
- pause automation and deployments;
- obtain explicit approval for the exact repository and refs.

## Evidence commands for the analysis session

```bash
git status --short --branch
git remote -v
git branch -a -vv
git rev-list --all --count
git rev-list --all --merges --count
git rev-list --left-right --count origin/main...origin/develop
git diff --stat origin/main..origin/develop
git show -s --format='%H %T %P %s' origin/main
git show -s --format='%H %T %P %s' origin/develop
```

Also inspect unique commits and run an approved secret scanner before deleting or
rewriting anything. A filename-only scan is not sufficient.
