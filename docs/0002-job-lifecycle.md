# 0002 · Job lifecycle and posting dates

The postings page becomes the place to track applications as well as to
review the guard: each job gets a status, the dates that matter, and filters.

## 1. Posting date shown and filterable

**Intention:** see how recent a job is, and narrow the list to recent ones.

**Spec changes:**
- The page shows each job's posting date, and can show only jobs posted in
  the last 7, 30 or 90 days. Jobs without a date are left out of those views.
- The date comes from the job board: Greenhouse's publish date, and Lever's
  creation date (when the job was created in Lever, which can be before it
  went public; Lever's public API has no publish date).

**Findings:** the date was already stored for all 136 postings; the page just
didn't show it.

## 2. Job status and lifecycle dates

**Intention:** track where each application stands, and notice when a job
disappears from the company's board.

**Spec changes:**
- Each job has a status: new, shortlisted, applied, interviewing, offer,
  rejected (they said no), not interested (the user said no), or closed (the
  role went away first). New jobs start as "new".
- The status is set by hand, in the table, to any value at any time; there
  are no rules about which status can follow which. The time of the last
  change is recorded.
- Each ingest run records, per job, when it was last seen on the board, and
  when it left the board ("closed"). A job that comes back is reopened.
- The pipeline never changes the status: if the ad for a job in
  "interviewing" comes down, it stays "interviewing" and only gets a closed
  date.
- A board that fails to load closes nothing, so a network error can't mark a
  company's jobs as gone. A board that loads but is empty does close them.
- Duplicates are hidden from the table (the status lives on the original
  posting). Quarantined postings stay visible, marked by their verdict.
- Postings stored before this change get "last seen" set to when they were
  first seen; the next ingest run updates it.

**Decisions (user):**
- One table for both status tracking and guard review, with a status filter
  and left/right scrolling to see every column.
- Last seen and closed dates are updated automatically by ingest; status is
  only ever set by hand.
- Duplicates hidden, quarantined postings shown.

**Open questions:**
- Only the current status is kept, not a history of changes, so "when did I
  apply" is lost once the status moves on.

## 3. UI code changes without a rebuild

**Spec changes:** the page's container now runs the code from the working
copy and reloads when a file is saved, so code changes no longer need an
image rebuild. Dependency changes still do.
