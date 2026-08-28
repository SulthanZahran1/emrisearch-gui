# Issue tracker: GitHub issues

This repo's wayfinder map and tickets live on GitHub issues.

## gh conventions

- Map issue: label `wayfinder:map`. Tickets: child issues of the map with labels `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`.
- Ticket bodies start with `Part of #<map>`.
- Blocking edges live in the ticket body as `Blocked by: #N` lines (one per line). A ticket is unblocked when every referenced issue is closed.
- Claiming = assigning: `gh issue edit <n> --add-assignee @me` before any work. An open, unassigned ticket is unclaimed.
- Resolution protocol: post the answer as a closing comment (`gh issue close <n> --reason completed --comment "..."`), then append a one-line gist to the map's `Decisions so far` via `gh issue edit <map> --body-file`.
- Research tickets resolve at charting time: dispatch a background `delegate_task` subagent, write the resolution comment from its verified output, close the ticket. The subagent's summary is a self-report; only claim sources as verified when the summary includes fetched sample data.
- Never loop over label names containing colons (`wayfinder:*`) in shell; create each label with one explicit quoted command.

## Wayfinding operations

- The map is the low-res view: Destination / Notes / Decisions so far / Not yet specified / Out of scope. Open tickets are found by query, not listed in the map.
- Frontier = open, unblocked, unclaimed child issues. Compute it by checking each open unassigned child's body for `Blocked by:` lines and confirming every referenced issue is closed (labels do not understand body-based dependencies).
- Never resolve more than one HITL ticket per session.
- When the map is complete, close the map issue itself with a completion comment.
