# 0003 — Duplicate detection rework and blocked companies

## 1. Company boilerplate in duplicate detection

**Intention:** decide whether two postings are the same job by what the job says, not by
the company template around it. Duplicates are expected from the same job appearing on
several sources, and from reposts.

**Findings:** on the 136 stored postings, lines that recur across a company's postings
(found in at least 20% of them) make up about half of each posting's text: 49%
(SonarSource, 110 postings), 51% (Proton, 15), 46% (Scandit, 11). Because of it, two
*different* jobs at the same company already look alike: the median similarity of two
different SonarSource postings was 0.28, the 95th percentile 0.66, against a duplicate
cutoff of 0.7. Only the title check kept them apart. With the recurring lines removed,
the median drops to 0.00 for all three companies and the 95th percentile to 0.00–0.12.
This quick measurement counted lines per posting, not per distinct title as the final
rule does, and is one snapshot of three companies, not a general measurement.

**Spec changes:**
- Before comparing two postings' text, each company's template is removed: every line
  that appears in postings for at least 3 distinct titles and 20% of the company's
  titles. It is learned from the company's own postings each run. Companies with fewer
  than 5 distinct titles have nothing removed: there's too little to tell template from
  content.
- Lines are counted per distinct title, not per posting, so a role posted in four cities
  doesn't make its own description look like template.
- A posting with fewer than 20 words left after removing the template can only be an
  exact duplicate (same title, company and location), not a near one.
- Duplicates are only looked for within the same company. Before, a posting was compared
  with every company's postings.

**Findings (dry run on stored data):** re-running the new rules over the 136 postings
changed one result, for the better: "Staff Software Engineer (Java) - Identity" had been
merged with "- Billing" and is now kept. Both postings consist of the template alone, so
the old check saw identical text. (An earlier draft rule, where overlapping locations
counted as the same, also merged "Director, GTM Productivity & Revenue Enablement" in
London with the same title for "Austin, Texas, London"; under the final rule in topic 2
those stay two jobs.)

21 SonarSource postings have under 20 words left once the template is removed. Their
stored text is the company intro only, see topic 4.

**Decisions:** recurring-line removal over embeddings. Two different jobs at one company
are close in meaning anyway (same domain, same culture text), so embeddings would
separate them worse than word overlap does. It needs no model and is easy to explain.

## 2. Comparing locations as places

**Intention:** stop treating different spellings of the same place as a conflict.

**Findings:** stored location strings include "Geneva, Barcelona" and "Barcelona;
Geneva", "London; " and "London", and "Geneva, Switzerland, Paris, France", where the
comma separates both city from country and city from city.

**Spec changes:** a location is split on `,` `;` `/` `|` and each piece is looked up in a
city list (GeoNames, via `geonamescache`), so Zürich and Zurich are the same place.
Country and US state names or codes are dropped as qualifiers. "Remote ..." is kept as
its own place, and unknown text is kept as text.

**Decisions (user's call):** two postings can only be the same job if their locations
name exactly the same set of places. Overlap isn't enough: the same role in Geneva, and
in Geneva and Barcelona, can be two different teams. A posting with no location is only
compared with other postings that have no location, never with one that has a location.

**Known gaps:** an ambiguous city name goes to its most populous match: "London" is
always London UK, even with ", Ontario" next to it. "Remote from Switzerland" and
"Remote CHE" count as different places, and so do "Zurich, Metropolitan Area" and
"Zurich" ("Metropolitan Area" isn't a known place). These errors keep two postings
apart; they never merge two jobs.

## 3. Blocked companies

**Intention (user's call):** skip consultancies and recruitment agencies. They post many
jobs on behalf of clients, and it's better to apply to the hiring company directly. It
also removes a source of duplicates: a consultancy's copy of another company's job.

**Spec changes:** `blocked_companies` in `config/companies.yaml`. Postings whose company
matches (ignoring case and spacing) are skipped before any processing, never stored, and
counted in the run summary.

**Open questions:** the current boards (Greenhouse, Lever) only list their own company's
jobs, so the list has no effect yet. It applies once boards that list several companies'
jobs are added. Matching is by exact name, so each spelling has to be listed.

## 4. Lever postings lost their role content

**Findings:** the Lever fetcher stored only the `description` field, which for SonarSource
is mostly the company intro. The role-specific sections (responsibilities, requirements)
are in Lever's `lists` and `additional` fields and were dropped. Example: "Account
Executive - EMEA East" kept about 1,000 characters of intro and lost 3 lists plus 1,300
characters. This was found while measuring boilerplate: 21 of 110 SonarSource postings
had almost nothing left once the template was removed.

**Spec changes:** Lever postings now keep all three parts, in the order the careers page
shows them: description, then each list under its heading, then the closing text.

**Findings (dry run, text rebuilt from the stored raw responses):** median SonarSource
posting length goes from 278 to 881 words. Postings too short to compare after removing
the template go from 21 to 0. No duplicates are found among the 110 either way.

**Open questions:** postings already stored keep their short text, and their guard
verdicts were decided on it, until the data is re-ingested. The guard will now see about
three times as much text per Lever posting, so its verdicts on those postings may change.

## Tests

The user reversed the earlier "no duplicate-detection tests" decision. Tests were written
before the code. The ones that failed on the old code: same places written differently,
similar roles sharing a template (built so their full texts score 0.74, above the 0.7
cutoff), identical postings at different companies, and blocked companies. The ones that
already passed guard against the new template removal breaking the old behaviour: reposts,
the same job from two sources, the same role in different cities, and one role posted in
many cities. A later test, the same role in overlapping cities ("Geneva, Barcelona" vs
"Geneva"), encodes the user's same-set rule, and another checks that postings without a
location are only compared with each other.
