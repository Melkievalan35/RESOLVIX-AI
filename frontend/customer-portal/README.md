# Resolvix — Customer Portal (frontend)

A fully clickable customer portal for the Resolvix AI complaint-resolution
platform. Built as plain HTML/CSS/JS — **no build step, no npm install
required** — so it runs anywhere immediately, including offline during a
hackathon judging round.

## Run it

Any static file server works. From this folder:

```bash
python3 -m http.server 8080
# then open http://localhost:8080/login.html
```

Or just open `login.html` directly in a browser (uses `localStorage`, so it
works from the filesystem too).

**Demo login:** `demo@resolvix.ai` / `demo1234` — pre-seeded with 4 sample
cases in different states (open, in progress, resolved, escalated).

## Pages

| Page | File | What it does |
|---|---|---|
| Login | `login.html` | Email/password sign-in, inline validation |
| Register | `register.html` | Account creation, password confirmation |
| Dashboard | `dashboard.html` | Stat cards + recent case tickets |
| File a Complaint | `complaint-form.html` | Category, subject, description, priority, evidence upload, confirmation screen with generated ticket ID |
| Complaint History | `complaint-history.html` | Searchable, filterable ticket list; click a ticket for a full case timeline (Customer → Evidence → Policy → Resolution Agent) |
| Chat Interface | `chat-interface.html` | Simulated conversation with the Customer Agent, quick replies, typing indicator |
| Profile | `profile.html` | Contact details, notification toggles, password change |

## Design system

"The Claims Desk" — every complaint is rendered as a torn-stub ticket with a
rotated ink-stamp status badge, echoing physical claims paperwork crossed
with an ops-room dashboard. Tokens live at the top of `css/styles.css`:
dark ink background, teal/amber/coral status accents, Fraunces (display) +
Inter (body) + IBM Plex Mono (case IDs, timestamps, data).

## Wiring up the real backend

Everything currently backed by `localStorage` lives in `js/store.js`. Each
function there (`login`, `register`, `createComplaint`, `listComplaints`,
etc.) is written as a single async-shaped unit so you can swap its body for
a `fetch()` call into `backend/api/*` without touching any page:

- `Store.login` → `POST /api/auth/login`
- `Store.register` → `POST /api/auth/register`
- `Store.createComplaint` → `POST /api/complaints` (hands off to
  `ai/agents/orchestrator.py`)
- `Store.listComplaints` / `Store.getComplaint` → `GET /api/complaints`
- `Store.timelineFor` → replace with the real per-agent audit trail from
  `ai/explainable_ai/audit_summary.py`
- Chat interface → replace `routeReply()` in `chat-interface.html` with a
  streamed response from the Customer Agent endpoint.
