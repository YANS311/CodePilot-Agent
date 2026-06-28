# Git Interview Notes

> Concise answers to common Git interview questions, grounded in CodePilot project experience.

---

## 1. merge vs rebase

**merge**: Creates a merge commit. Preserves full history, including branch topology.
```
A---B---C (main)
     \
      D---E (feature)
→ merge: A---B---C---M (main)
              \     /
               D---E
```

**rebase**: Replays commits on top of target. Linear history, no merge commit.
```
→ rebase: A---B---C---D'---E' (feature on main)
```

**When to use which:**
- merge: shared branches, preserving context of "when feature was developed"
- rebase: local cleanup before push, keeping history linear

**CodePilot experience:** We used merge (fast-forward) to sync master→main. No rebase needed because master was always behind.

---

## 2. cherry-pick

**What:** Apply a specific commit from one branch to another.

```bash
git cherry-pick <commit-hash>
```

**When to use:**
- Bug fix on `main` needs to go to `release` branch
- Accidentally committed to wrong branch
- Want one specific commit without merging entire branch

**CodePilot experience:** Not needed — we kept main/master in sync via fast-forward merge.

---

## 3. revert vs reset

**revert**: Creates a NEW commit that undoes changes. Safe for shared branches.
```bash
git revert <commit-hash>  # Creates new commit undoing the changes
```

**reset**: Moves HEAD to a previous commit. Rewrites history. Dangerous for shared branches.
```bash
git reset --soft HEAD~1   # Undo commit, keep changes staged
git reset --mixed HEAD~1  # Undo commit, keep changes unstaged
git reset --hard HEAD~1   # Undo commit, discard changes
```

**Rule of thumb:**
- `revert` for public/shared branches (safe, creates undo commit)
- `reset` for local/private branches (rewrites history)

**CodePilot experience:** Used `git reset HEAD <file>` to unstage files during D34.1 (unstaged benchmark fixture that had no changes).

---

## 4. Already pushed wrong commit — how to roll back

**Don't** `git reset --hard` and `git push --force` (dangerous).

**Do** `git revert`:
```bash
git revert <bad-commit-hash>
git push origin main
```

This creates an undo commit and pushes it. History is preserved, collaborators are safe.

**If you must reset** (e.g., commit contains secrets):
```bash
git reset --hard <good-commit-hash>
git push --force origin main  # WARN: breaks collaborators
```

**CodePilot experience:** Never needed — we were careful to stage specific files and verify before push.

---

## 5. Local commit message wrong — how to fix

**If not yet pushed:**
```bash
git commit --amend -m "correct message"
```

**If already pushed:**
```bash
git commit --amend -m "correct message"
git push --force-with-lease origin main  # Safer than --force
```

**CodePilot experience:** Used `--amend` during early development when commit messages needed fixing.

---

## 6. Get specific bugfix commit to main

**cherry-pick:**
```bash
git checkout main
git cherry-pick <commit-hash>
git push origin main
```

**Or create a branch from the fix:**
```bash
git checkout -b hotfix/<issue> <commit-hash>
git checkout main
git merge hotfix/<issue>
```

**CodePilot experience:** Not needed — all fixes went directly to main.

---

## 7. Check which files a commit changed

```bash
git show <commit-hash> --stat      # Summary
git show <commit-hash> --name-only # File names only
git diff <commit-hash>~1 <commit-hash>  # Full diff
```

**CodePilot example:**
```bash
git show 9239b84 --stat
# Shows: 12 files changed, 510 insertions(+), 21 deletions(-)
```

---

## 8. Handling merge conflict

```bash
git merge feature-branch
# CONFLICT in app/main.py

# 1. See conflicting files
git status

# 2. Edit conflicting file (look for <<<<<<< markers)
# 3. Choose resolution
git add app/main.py
git commit  # or git merge --continue
```

**Prevention:**
- Pull before push
- Keep branches short-lived
- Communicate with team on shared files

**CodePilot experience:** No conflicts — single developer, sequential merges.

---

## 9. Avoid committing runtime files

**`.gitignore`:**
```
workspace/uploads/
data/
.pytest_cache/
__pycache__/
.env
```

**If already tracked:**
```bash
git rm --cached workspace/uploads/
git commit -m "stop tracking runtime files"
```

**CodePilot experience (D34.1):** The `workspace/uploads/` directory accumulated 34 runtime directories with conflicting `test_main.py` files. Fix: added `collect_ignore_glob = ["uploads/*"]` to `workspace/conftest.py` and `data/` to `.gitignore`.

---

## 10. CodePilot main/master sync strategy

**Current state:**
- `main`: active development branch
- `master`: kept in sync via fast-forward merge
- GitHub default: `main`

**Sync process:**
```bash
git checkout master
git merge main        # Fast-forward (master always behind)
git push origin master
git checkout main
```

**Why not delete master?**
- Zero risk: if someone clicks master, they see current code
- Can delete later if desired

**Release tags:**
- `v0.3.0`, `v0.4.0`, `v0.4.1` on main
- Tags fetched to master during sync
