# Going public

The repository is private until launch day. DnG-Crafts replied (2026-10-29): the code is free to use however
we like, with no rights claimed and credit optional (the thank-you stays in the About box and README).

## Before the day

- [ ] Two-factor sign-in is on for the GitHub account (github.com/settings/security).
- [ ] The newest version is tagged and its draft release checked (all three downloads, release notes).
- [ ] Old drafts no longer wanted are deleted (`gh release list`; e.g. 2.0.2 and 2.4.0).
- [ ] README and ROADMAP read well to a stranger; the screenshots are current.
- [ ] The history has nothing private in it. Checked 2026-10-29: no passwords, tokens or keys in any of the
      19 commits; the only personal detail was the name of the message to DnG in `.gitignore`, now removed
      from every commit (the message itself is in ~/Documents, outside the project).

## On the day

1. Lock it down and make it public (asks first, then applies everything; safe to run again):

       tools/github_launch.sh

   - `main`: no force-push or deleting; changes by pull request with the Mac and Windows tests passing.
     You can still push directly (admins bypass), as now.
   - `v*` tags: only you can create, move or delete them (a tag builds a release).
   - Actions: read-only unless a job needs more; outside contributors' pull requests wait for your approval.
   - Security: secret scanning with push protection, Dependabot alerts and fixes, private vulnerability
     reporting (see SECURITY.md).
   - Projects and Wiki off; Issues on, with templates for bugs and ideas.

2. Check it: `tools/github_launch.sh --check`, and the repo's Settings → Rules and Security pages.
3. Publish the release: on the draft, press **Publish release** (or `gh release edit vX.Y.Z --draft=false`).
4. Website: set `SPOOLHOUSE_REPO_PUBLIC=true` in the server's `.env` and deploy
   (`envoy run deploy-code`). The download buttons, source and issue links appear.
5. Desktop app: nothing to do. Its update check reads the public releases, so everyone gets the notice.

## Afterwards

- New work: as now. A tag (`git tag vX.Y.Z && git push origin vX.Y.Z`) builds the draft release.
- Pull requests from others: the tests run once you approve them (Actions tab); merge if happy.
- Dependabot opens pull requests for library updates and security fixes: merge when the tests pass.
