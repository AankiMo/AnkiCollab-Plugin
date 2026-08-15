# Contributing to AnkiCollab-Plugin

Thanks for wanting to help out. This is a small project maintained by one person in their spare
time, so this document exists to keep contributions reviewable and the codebase maintainable —
please read it before opening a PR.

## Start small

**First-time contributors: please open small, focused PRs.** A good first PR fixes one bug, adds
one small improvement, or tweaks one specific dialog/behavior. This isn't about your skill level —
it's about building trust and shared context incrementally, in both directions. I need to
understand how you write code before reviewing something large, and you'll get a feel for the
codebase's conventions before committing a lot of time to something big.

This matters more here than in a typical project: this add-on runs inside other people's Anki
installs, next to their personal card collections. A bug here can mean lost or corrupted decks for
someone, not just a crashed dev server. Small, reviewable changes are how we keep that risk low.

Concretely:

- **Large, unsolicited refactors will not be accepted.** If you think a module or pattern needs a
  significant rewrite, **open an issue first and discuss it before writing code.** I may agree the
  refactor is worth doing — but I'd rather align on the approach before either of us spends hours
  on a PR that gets rejected in review.
- **Large new features should also be discussed in an issue first**, for the same reason. A big PR
  implementing an entire new feature I never asked for and haven't reviewed the design of is very
  unlikely to be merged as-is, no matter how well-written it is.
- If you want to tackle something big, the path is: open an issue describing what and why → get
  a thumbs up on the approach → then build it, ideally in reviewable chunks rather than one giant
  PR.

## Code formatting

This project uses [Black](https://black.readthedocs.io/) to keep code style consistent. Pull requests are checked automatically in CI, and a PR with unformatted code will fail the `lint` check and be blocked from merging.

Before opening a PR, please format your code locally:

```bash
pip install black==26.5.1
black plugin_source/
```

This will rewrite any files that don't match the project's style. Review the changes, then commit and push as usual.

If you just want to see what *would* change without modifying files:

```bash
black --check --diff plugin_source/
```

## On AI-assisted code

Using AI tools (Copilot, Claude, ChatGPT, etc.) to help you write code is fine — plenty of us do.
What I can't accept is **code you don't understand or haven't reviewed yourself.**

In practice this means:

- Don't paste a large chunk of AI-generated code straight into a PR without reading, testing, and
  understanding every line of it. If I ask "why did you do it this way?" in review, you should be
  able to answer — it's your PR either way.
- Don't use AI to generate an entire new feature wholesale. Large, sprawling, "vibe-coded" PRs —
  inconsistent style, unnecessary abstractions, code that doesn't match how the rest of the addon
  does things, or code that touches Anki's collection/database APIs in ways you can't fully
  explain — will be closed, not extensively reviewed and fixed by me. I don't have the time to
  rewrite someone else's PR into something mergeable, and I especially won't merge something
  touching user data that I can't be confident is safe.
- Small, targeted changes are much easier to verify regardless of how they were written, which is
  another reason to keep PRs small (see above).

If a PR looks AI-generated wholesale and the author can't explain specific design decisions in
it, I'll close it and ask you to resubmit something smaller and in your own words.

## Before you open a PR

1. **Discuss non-trivial changes in an issue first.** Bug fixes and small, obvious improvements
   don't need this — just open the PR. Anything that changes how the addon reads/writes the Anki
   collection, touches sync behavior, or is more than a couple hundred lines should start as an
   issue.
2. **Test your change inside actual Anki**, not just by reading the code. Since this runs inside
   other people's Anki installs, "it imports without errors" isn't the same as "it works." Ideally
   test against a throwaway profile, not your main collection.
3. Match the existing code style in `plugin_source/` — consistent naming, similar structure to
   neighboring files. If you use a formatter/linter locally (e.g. `black`, `ruff`), that's welcome,
   but don't run a full-repo reformat as part of an unrelated PR — that makes the diff impossible
   to review. Formatting-only changes should be their own separate PR, discussed first.
4. Keep commits reasonably scoped and write a clear PR description: what changed, why, and how you
   tested it. "Fixes #123" is great when there's an issue to reference.

## What's especially welcome right now

- Bug fixes with a clear repro.
- Small, self-contained UI/UX improvements.
- Documentation fixes (README, FAQ, getting-started guides).

## Questions

If anything here is unclear, or you're not sure whether something counts as "small," just ask —
open an issue or drop a question on the [Discord](https://discord.gg/9x4DRxzqwM) before writing
code. That's cheaper for everyone than a rejected PR.
