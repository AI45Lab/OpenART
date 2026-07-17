# Reference: Confluence Log Source FAQ Generator

## Purpose

Each Log Source FAQ article documents **one specific issue** for a log source — the symptom, root cause, and resolution. These are focused operational notes, not onboarding guides. Think of them as the written-down version of "we've seen this before, here's what to do."

---

## Workflow

### Step 1 — Understand the issue

Ask the user the minimum needed to write the article. Keep questions grouped and conversational — don't ask everything at once. The key things to establish:

1. **Log source**: What product/vendor generates this log? Which SIEM/platform receives it?
2. **The problem**: What symptom does the user or team observe? When does it happen?
3. **Root cause**: What actually causes it? (If unknown, note that explicitly.)
4. **Resolution**: What steps fix it? Is there a workaround?
5. **Verification**: How do you confirm the issue is resolved?

If the user's description is already detailed enough, proceed directly and flag any gaps with `[TODO]`.

**Example clarifying questions** (adapt to context):
- "What exactly does the team observe — missing logs, parsing errors, wrong field values?"
- "Is this happening consistently or only on certain devices/environments?"
- "What's the fix — a config change, a parser update, a query tweak?"

### Step 2 — Fetch reference URLs (if provided)

If the user provides one or more URLs:
- Fetch and read the content at each URL.
- Extract relevant technical details — error messages, config snippets, version notes.
- Treat URL content as authoritative; prioritize it over general knowledge.
- All provided URLs must appear in the **References** section of the final article.

### Step 3 — Generate the article using the template

Load the template from:
```
assets/log-source-faq-template.md
```

Fill in every `{{PLACEHOLDER}}` with real content. Mark anything still unknown as `[TODO — verify with team]`.

**Formatting and writing style:**
- **Be concise.** Every sentence should carry information. Cut preamble, filler, and anything the reader can infer.
- **Short sentences.** Prefer one idea per sentence. If a sentence has more than two clauses, split it.
- **Bullets over paragraphs.** Use numbered steps for procedures, bullets for lists of facts. Avoid prose blocks.
- **Analyst-first language.** Describe what the analyst sees, does, and checks — not abstract system behaviour.
- **No redundant qualifiers.** Avoid phrases like "please note that", "it is important to", "in order to". Start with the verb.
- Resolution steps must be a numbered list — each step is a single, concrete action.
- The title format is: `{{LOG_SOURCE_NAME}} — {{ISSUE_TITLE}}` where the issue title is a short plain-English description of the problem (e.g., "Logs Not Ingested After Agent Upgrade", "Timestamp Parsing Failure on Windows Events").

**Bad example (too wordy):**
> It is important to note that in order to resolve this issue, you may need to consider restarting the collector service, which should help ensure that the logs begin flowing again.

**Good example (concise):**
> Restart the collector service. Logs should resume within 2 minutes.

### Step 4 — Show preview and publish

Present the completed article to the user for review before publishing (per the Confirmation Protocol in SKILL.md).

Then publish via MCP:

```
Tool: createConfluencePage (or equivalent)
Parameters:
  - spaceId: <from MCP config>
  - title: "<LOG_SOURCE_NAME> — <ISSUE_TITLE>"
  - parentPageTitle: "Log Source FAQ"
  - content: <full article content>
```

If the MCP cannot create the page, output the content in a code block for manual copy-paste.

---

## Quality Checklist

Before publishing, verify:
- [ ] No `{{PLACEHOLDER}}` tokens remain (or remaining ones are explicitly marked `[TODO]`)
- [ ] The symptom is described from the analyst's perspective (what they see, not an abstract definition)
- [ ] Root cause is stated clearly, or noted as "Unknown / under investigation"
- [ ] Resolution steps are numbered and actionable
- [ ] Verification section explains how to confirm success
- [ ] Reference URLs are listed if any were provided
