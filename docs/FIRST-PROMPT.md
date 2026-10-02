# NAME: First Prompt

This replaces the opener that stalled claude.ai before, paste it as your very first message to NAME in VS Code, once Mike's handed the folder over.

```
Read CLAUDE.md, then state/taylor/blueprint.md sections 1, 3, 4, 12 (Phase 1 and G1-G5)
and the Phase 1 line in section 13. Do not summarise it back to me.
Then run the Phase 1 audit this system can actually perform, using the scripts, not memory:
  python scripts/ea_doctor.py
  python scripts/link_docs.py --status
  python scripts/calendar_next.py --status
  python scripts/register.py owed
Report in under 40 lines under Reuse, Connect, Create and Need from Taylor. Under Need from Taylor
list only what the scripts could not verify. State plainly what this system cannot audit from
this machine (claude.ai projects, GRETA bots, Supabase). List every entry in docs/DEVIATIONS.md
and ask me to approve or reject each. Build nothing in this chat.
```

A good answer stays under 40 lines, split into Reuse, Connect, Create and Need from Taylor, without re-explaining the architecture back to you.
Need from Taylor names only what the four scripts actually could not verify, not a generic wish list.
It ends by asking you to approve or reject each open item in `docs/DEVIATIONS.md`, and builds nothing yet.
