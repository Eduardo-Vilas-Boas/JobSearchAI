# 0004 — More companies, LinkedIn capture, job page, language detection fix

## 1. More companies from a list of 50

**Intention:** add Swiss robotics and AI companies from a list of 50 candidates (startups,
industrial R&D, big-tech labs, consultancies).

**Findings:** each company was checked against the public job-board APIs of seven ATSs
(Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Personio, Workable), trying the usual
slug for the name. Only 4 use an ATS the pipeline can read (Greenhouse or Lever):
ANYbotics (24 postings), Gravis Robotics (11), Auterion (26) and Anthropic (633, all
offices worldwide). Others found: 5 on Ashby (Exclaim Robotics, DeepJudge, Jua, OpenAI,
Exa) and 4 on Workable (Flexion Robotics, Distalmotion, LatticeFlow AI, Flyability). Four
matches were other companies with the same name (`mimic` on Lever is a US security
company, `unique` on Personio a German land-use firm, plus `disney` and `sdsc`), so a
matching slug alone isn't proof. Workable answers 200 for any name, so only boards with
postings count. Nothing was found for 13 startups and labs (Ascento, Duatic, Voliro…) or
for the large companies, which likely use Workday or their own sites. A slug that wasn't
tried could still exist.

**Spec changes:** the 4 companies were added to `config/companies.yaml`, each checked with
the real fetcher.

**Open questions:** an Ashby fetcher would add 5 companies and a Workable fetcher 4. Ingest
time grows with Anthropic's 633 postings, each scanned by the guard model.

## 2. Capturing LinkedIn postings from the browser

**Intention:** many relevant jobs are only on LinkedIn, which has no public job API. Save
the posting open in the browser with one click, into the same database.

**Findings:**
- Two open-source extensions were reviewed. Prepify (MIT) has the same design (an
  extension posting to a local app), but its LinkedIn selectors match nothing on today's
  pages: LinkedIn now uses hashed class names that change between releases. Prepify had
  no commits for 8 months and kept only 400 characters of the description. Jobs Saver
  (MIT) saves only title and link to browser storage.
- LinkedIn's pages still have a stable structure: the job's id in the URL, a link to the
  job's own page as the title, a company link before it, a "Location · 3 days ago · …"
  line after it, and the description in a box marked `expandable-text-box`.
- Two LinkedIn layouts were seen in two real pages. In the newer search layout
  (`/jobs/search-results/`), the job list on the left also links to the selected job, and
  comes first. The first version of the parser read that list card, so its first real
  capture had an empty company, company and location merged ("Sunflower Labs • Stallikon,
  …") and no date. The parser now reads the link nearest the description.
- LinkedIn's user agreement forbids scraping. One capture at a time, started by the user,
  is much lower risk than automated scraping, but the risk is to the user's account.

**Spec changes:**
- A Chrome extension (Manifest V3) sends the open tab's rendered HTML and URL to a local
  capture server. The popup shows what was read (title, company, location, date,
  description length) before saving.
- All parsing is in Python, on the server. The extension knows nothing about LinkedIn, so a
  LinkedIn change is fixed in one place, and the stored page can be parsed again later.
- A captured posting goes through the same steps as a fetched one: PII redaction, the
  guard, the blocklist, duplicate detection, storage. Only the title and description are
  guarded; the full page is stored unguarded because nothing reads it yet.
- A captured posting is never marked closed, since it has no board to disappear from.
- The posting date is worked out from LinkedIn's "3 days ago", counted back from the
  capture time, so it is accurate to the day at best.
- The server only accepts requests from a Chrome extension, because any website open in
  the browser can send requests to localhost.

**Decisions:**
- The user's call: start with LinkedIn only, and move to a local LLM later for pages the
  parser can't read. That step is deferred because this stage of the project is
  LLM-free.
- Write our own small extension instead of adapting Prepify, since the needed part is
  small and Prepify's selectors no longer work. The field choice is credited to Prepify.

**Open questions:** the standalone job page (`/jobs/view/…`) and non-English postings
haven't been captured yet. The stored page includes the user's own LinkedIn name and
profile, kept only in the local database.

## 3. A page per job

**Intention:** the user found the "Inspect one posting" section at the bottom of the
postings page hard to use, and asked for a separate job page opened from the table.

**Spec changes:** clicking a title in the postings table opens the job's own page in a new
tab. It shows the posting's details, editable status, dates, guard verdict, other stored
copies of the same job, and the stored text with paragraphs kept. The old section was
removed.

**Decisions:** the user asked for a double-click and a `/job/{id}` address. Streamlit's
table can't catch double-clicks or serve such paths, so the user chose a single click on
the title and `/job?id=…` over rebuilding the pages outside Streamlit.

## 4. English postings tagged German

**Findings:** the language detector (lingua) ran in its fast, low-accuracy mode, which
tagged 7 of 137 stored postings German. All 7 were English tech postings, dense with
product names ("PyTorch, ONNX, TensorRT, CUDA"). In full-accuracy mode, all 137 were
tagged correctly. The extra time per posting wasn't measured.

**Spec changes:** full-accuracy mode. The stored tags were recomputed with the user's
approval; only the language tag changed (the 7th posting was the faulty LinkedIn capture,
deleted to be captured again).

## Tests

Tests were written before the code. The LinkedIn parser is tested on two hand-written
pages that copy the real pages' structure with made-up text, since real pages hold the
user's profile and postings that aren't ours to publish. Two local-only tests run on the
real captured pages in `data/` and are skipped where those files don't exist. A made-up
English text full of product names, which the fast mode called German, guards the
language fix.
