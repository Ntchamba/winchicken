---
name: app-navigator
description: Use when exploring or modifying code in this project, before reading files or making edits, to keep investigation targeted and avoid loading unnecessary context into the session.
---

# App Navigator

## Overview

This project is large and multi-domain (batches, houses, alerts, protocols, finance, stock, onboarding). Reading whole files by default burns context fast and buries the signal. Default to targeted, minimal-footprint investigation; open full files only when a targeted search says you need to.

## Rules

1. **Search before you read.** Use `Grep`/`Glob` (or the `Explore` agent for broad lookups) to find the relevant symbol, file, or line range first. Do not open a file "just to look around."
2. **Cap full-file reads at 5 per investigation step.** That covers a typical cross-cutting look (e.g. model + serializer + view + urls + test, or component + hook + api client + page + styles) without opening the whole app. If a 6th file seems necessary, stop and state why before opening it, or narrow the search instead.
3. **Validate the impacted-files list before editing.** Once you know which files a change touches, list them for the user and get confirmation before making any modification — even a small one — unless the user has already approved the scope.
4. **Never rewrite a whole existing file to make a small change.** Use `Edit` with the minimal diff. `Write`/full-file rewrites are reserved for genuinely new files or changes the user explicitly asked to restructure wholesale.

## Quick Reference

| Situation | Do | Don't |
|---|---|---|
| "Where is X handled?" | `Grep` for the symbol/route/model name | Open every file in the app to skim |
| Found the file, need context | `Read` with `offset`/`limit` around the match | `Read` the entire file top to bottom |
| About to touch 6+ files | Post the file list, wait for a go-ahead | Start editing immediately |
| Fixing one function | `Edit` just that block | `Write` the whole file back out |

## Common Mistakes

| Excuse | Reality |
|---|---|
| "I'll just skim the whole file, it's faster" | Grep is faster and doesn't fill the context window with unrelated code. |
| "It's only a small file" | The rule is about habit, not file size — habits compound across a session. |
| "The edit touches most of the file anyway" | Still express it as an `Edit` diff; a rewrite hides exactly what changed. |
| "I already know which files are impacted, no need to check" | Confirm anyway — the user may know about a dependent file you don't. |

## Red Flags — Stop and Recheck

- About to `Read` a 6th full file in the same investigation step without having said why.
- About to `Edit`/`Write` a file that wasn't on the confirmed impacted-files list.
- About to use `Write` on a file that already exists, for a change smaller than the whole file.
