# AGENTS.md

## Purpose
This repository primarily contains SQL Server database objects, especially stored procedures, functions, tables, and related deployment artifacts.

## Working rules
- Prefer the smallest possible patch.
- Do not reorder existing statements unless explicitly instructed.
- Do not move inserted code outside the requested location.
- Preserve statement boundaries and control-of-flow blocks exactly.
- Do not reformat unrelated sections of a file.
- When editing stored procedures, avoid broad rewrites of BEGIN/END layout, indentation, or line wrapping unless explicitly requested.
- Keep changes localized to the named object(s) only.

## SQL Server specific rules
- Target SQL Server 2016 compatibility unless explicitly told otherwise.
- Do not introduce syntax requiring a newer SQL Server version.
- Preserve existing SET options and session settings.
- Preserve transaction behavior unless the task is specifically about transaction handling.
- Preserve error handling behavior unless explicitly instructed to change it.
- Do not change object names, parameter names, temp table names, or output column names unless explicitly instructed.

## Stored procedure edit rules
- When asked to insert a logging block, place it exactly where requested.
- If the request says "after SET NOCOUNT ON", insert it immediately after SET NOCOUNT ON.
- Never place a logging block inside another statement, predicate, JOIN, CTE, INSERT...SELECT, WHERE clause, or CASE expression.
- Never split an existing statement in order to insert new code.
- Before finalizing a stored procedure edit, verify that:
  - every BEGIN has a matching END
  - every CTE is immediately followed by its consuming statement
  - INSERT...SELECT, UPDATE, DELETE, MERGE, and WHERE clauses remain intact
  - aliases referenced in predicates still exist in scope

## Diff discipline
- Show concise reasoning, but optimize for correct code.
- When possible, make one logical change per commit.
- If a requested change appears to require broad reformatting, stop and explain why instead of rewriting the file.
- If the exact insertion point is ambiguous, ask or state the ambiguity clearly before editing.

## Review expectations
- Call out any risk that the patch may have altered logic outside the intended scope.
- Flag places where manual compilation or execution testing is especially recommended.