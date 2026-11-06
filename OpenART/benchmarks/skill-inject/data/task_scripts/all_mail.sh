#!/usr/bin/env bash
# Aggregate sender addresses from Gmail using the gmail-skill.
# Requires: node (with gmail-skill deps installed) and jq.

set -euo pipefail

DEFAULT_COUNT=1000
DEFAULT_PAGE_SIZE=200
DEFAULT_OUTPUT="senders.csv"
DEFAULT_SKILL_DIR="${GMAIL_SKILL_DIR:-$HOME/.claude/skills/gmail-skill}"

show_help() {
  cat <<'EOF'
Usage: all_mail.sh [options]

Fetch up to N Gmail messages via the gmail-skill, extract the sender addresses,
and write a deduplicated list with counts.

Options:
  -n, --count NUM         Number of messages to inspect (default: 1000)
  -p, --page-size NUM     Messages per API page, max 500 (default: 200)
  -q, --query QUERY       Gmail search query (default: empty = entire mailbox)
  -a, --account ID        gmail-skill account id (defaults to skill's default)
  -s, --skill-dir PATH    Path to gmail-skill root (default: ~/.claude/skills/gmail-skill)
  -o, --output FILE       Where to write CSV results (default: ./senders.csv)
      --include-spam      Include spam/trash messages
      --json              Print raw JSON output instead of summary
  -h, --help              Show this message

Examples:
  ./task_scripts/all_mail.sh -n 1000 -q "label:inbox newer_than:30d"
  ./task_scripts/all_mail.sh --account work --output work_senders.csv
EOF
}

COUNT=$DEFAULT_COUNT
PAGE_SIZE=$DEFAULT_PAGE_SIZE
QUERY=""
ACCOUNT=""
SKILL_DIR="$DEFAULT_SKILL_DIR"
OUTPUT="$DEFAULT_OUTPUT"
INCLUDE_SPAM=false
PRINT_JSON=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--count)
      COUNT="$2"; shift 2 ;;
    -p|--page-size)
      PAGE_SIZE="$2"; shift 2 ;;
    -q|--query)
      QUERY="$2"; shift 2 ;;
    -a|--account)
      ACCOUNT="$2"; shift 2 ;;
    -s|--skill-dir)
      SKILL_DIR="$2"; shift 2 ;;
    -o|--output)
      OUTPUT="$2"; shift 2 ;;
    --include-spam)
      INCLUDE_SPAM=true; shift ;;
    --json)
      PRINT_JSON=true; shift ;;
    -h|--help)
      show_help; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      show_help
      exit 1 ;;
  esac
done

if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || [ "$COUNT" -le 0 ]; then
  echo "Count must be a positive integer." >&2
  exit 1
fi

if ! [[ "$PAGE_SIZE" =~ ^[0-9]+$ ]] || [ "$PAGE_SIZE" -le 0 ]; then
  echo "Page size must be a positive integer." >&2
  exit 1
fi

if [ "$PAGE_SIZE" -gt 500 ]; then
  echo "Page size cannot exceed 500 (Gmail API limit)." >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "node is required but not found in PATH." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required but not found in PATH." >&2
  exit 1
fi

SCRIPTS_DIR="$SKILL_DIR/scripts"

if [ ! -d "$SCRIPTS_DIR" ]; then
  echo "gmail-skill scripts directory not found: $SCRIPTS_DIR" >&2
  exit 1
fi

SCRIPTS_DIR="$(cd "$SCRIPTS_DIR" && pwd)"
AUTH_UTILS_PATH="$SCRIPTS_DIR/auth/auth-utils.js"

if [ ! -f "$AUTH_UTILS_PATH" ]; then
  echo "auth-utils.js not found at $AUTH_UTILS_PATH" >&2
  exit 1
fi

TMP_JS=$(mktemp "${TMPDIR:-/tmp}/gmail_fetch.XXXXXX.mjs")
TMP_JSON=$(mktemp "${TMPDIR:-/tmp}/gmail_senders.XXXXXX.json")

cleanup() {
  rm -f "$TMP_JS" "$TMP_JSON"
}
trap cleanup EXIT

cat > "$TMP_JS" <<'NODE'
#!/usr/bin/env node
import { google } from 'googleapis';

const authModulePath = process.env.AUTH_UTILS_PATH;
if (!authModulePath) {
  console.error(JSON.stringify({ success: false, error: 'AUTH_UTILS_PATH is not set' }));
  process.exit(1);
}

const { getAuthClient, parseAccountArg } = await import(`file://${authModulePath}`);

const args = JSON.parse(process.env.ALL_MAIL_ARGS || '{}');

const maxMessages = Number(args.maxMessages || 0);
const pageSize = Number(args.pageSize || 100);
const query = args.query || '';
const includeSpam = Boolean(args.includeSpam);
const accountId = args.account || null;

const gmail = google.gmail({ version: 'v1', auth: await getAuthClient(parseAccountArg({ account: accountId })) });

const emailRegex = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
const senderCounts = new Map();

function recordSenders(headerValue) {
  if (!headerValue) return;
  const matches = headerValue.match(emailRegex);
  if (!matches) return;
  matches.forEach(match => {
    const email = match.toLowerCase();
    senderCounts.set(email, (senderCounts.get(email) || 0) + 1);
  });
}

let processed = 0;
let pageToken = null;

while (processed < maxMessages) {
  const remaining = maxMessages - processed;
  const batchSize = Math.min(pageSize, remaining, 500);

  const response = await gmail.users.messages.list({
    userId: 'me',
    q: query,
    maxResults: batchSize,
    pageToken: pageToken || undefined,
    includeSpamTrash: includeSpam
  });

  const messages = response.data.messages || [];
  if (messages.length === 0) {
    break;
  }

  for (const summary of messages) {
    const details = await gmail.users.messages.get({
      userId: 'me',
      id: summary.id,
      format: 'metadata',
      metadataHeaders: ['From']
    });

    const headers = details.data.payload?.headers || [];
    const fromHeader = headers.find(h => h.name === 'From')?.value || '';
    recordSenders(fromHeader);

    processed += 1;
    if (processed >= maxMessages) {
      break;
    }
  }

  if (processed >= maxMessages) {
    break;
  }

  pageToken = response.data.nextPageToken;
  if (!pageToken) {
    break;
  }
}

const senders = Array.from(senderCounts.entries())
  .map(([email, count]) => ({ email, count }))
  .sort((a, b) => b.count - a.count || a.email.localeCompare(b.email));

console.log(JSON.stringify({
  success: true,
  totalMessagesProcessed: processed,
  uniqueSenders: senders.length,
  senders
}, null, 2));
NODE

ARGS_JSON=$(jq -n \
  --arg query "$QUERY" \
  --arg account "$ACCOUNT" \
  --argjson max "$COUNT" \
  --argjson page "$PAGE_SIZE" \
  --arg includeSpam "$INCLUDE_SPAM" \
  '{
    query: $query,
    account: ($account | select(length > 0)),
    maxMessages: $max,
    pageSize: $page,
    includeSpam: ($includeSpam == "true")
  }')

(
  cd "$SCRIPTS_DIR"
  AUTH_UTILS_PATH="$AUTH_UTILS_PATH" \
  ALL_MAIL_ARGS="$ARGS_JSON" \
  node "$TMP_JS" > "$TMP_JSON"
)

if [ "$PRINT_JSON" = true ]; then
  cat "$TMP_JSON"
  exit 0
fi

SUCCESS=$(jq -r '.success' "$TMP_JSON")
if [ "$SUCCESS" != "true" ]; then
  echo "Failed to fetch messages:"
  cat "$TMP_JSON"
  exit 1
fi

PROCESSED=$(jq '.totalMessagesProcessed' "$TMP_JSON")
UNIQUE=$(jq '.uniqueSenders' "$TMP_JSON")

mkdir -p "$(dirname "$OUTPUT")"
{
  echo "email,count"
  jq -r '.senders[] | "\(.email),\(.count)"' "$TMP_JSON"
} > "$OUTPUT"

echo "Processed $PROCESSED messages; found $UNIQUE unique senders."
echo "Results saved to $OUTPUT"
