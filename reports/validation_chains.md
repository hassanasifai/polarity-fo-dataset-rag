# Three Validation Chains

Each chain documents one record at claim level. Quotes are verbatim sentences extracted from Firecrawl markdown snapshots taken on 2026-05-17 — see `data/processed/validation_chain_snippets.csv` for the source rows.

## Validation Chain 1 - Cat Trail Capital (`fo_001`)

- **Family office type:** `single_family_office`
- **Discovery source:** organic public-web discovery, filtered through `apify/google-search-scraper` for own-domain results.
- **Extraction method:** Firecrawl markdown of the official site URLs below; quotes selected manually from the markdown.
- **Validation logic:** live HTTP check on every source URL, ≥2 reachable sources, score ≥80, no discovery-only directory sources, name overlap with the assessment sample workbook checked and clear.

**Enrichment steps (in order applied):**

- Captured official site markdown via Firecrawl on 2026-05-17 (depth 0, exact source URLs only).
- Captured candidate corporate-contact signals via Apify vdrmota/contact-info-scraper; promoted admin@cattrail.com as primary_email with `corporate_public_listed` confidence.
- Matched the corporate LinkedIn URL via Apify automation-lab/linkedin-company-scraper (linkedin.com/company/cattrail-capital-llc) with `linkedin_scraped_match` confidence.
- Cross-checked the address via Apify compass/crawler-google-places (New York, NY).
- Recent activity: no qualifying 2025+ public news signal — recorded transparently in uncertainty_notes rather than padded with weak matches.

### Source: `https://www.cattrail.com/`

- **Source type:** official_site_home
- **Claim supported:** single-family office identity and Dekker family attribution
- **Quote 1:** "What We Do Cat Trail is a single family office (SFO), a private investment company focused on growing its General Partners’ capital."
- **Quote 2:** "Investment partners are caref...Show more Wealth Planning Providing a full suite of customized services, Cat Trail coordinates with trusted advisors to meet the needs of…"

### Source: `https://www.cattrail.com/#About`

- **Source type:** official_site_about_anchor
- **Claim supported:** investment mandate across public securities, fund managers, real assets, and private companies
- **Quote 1:** "Learn More Investment Management Cat Trail takes strategic positions in publicly traded securities, makes placements with unique fund managers, manages a portfolio of real assets…"
- **Quote 2:** "History Cat Trail is an investment company serving the Dekker family."

### Source: `https://www.cattrail.com/#Team`

- **Source type:** official_site_team_anchor
- **Claim supported:** principal family / team composition
- **Quote 1:** "Investing in both debt and equity, Cat Trail establishes active, on-going relationships with those with whom it invests."
- **Quote 2:** "Services include multigenerational estate planning, tax strategy, portfolio reporting & analytics, and financial planning."

**What remains uncertain:**

- No public AUM is disclosed on the site; AUM left blank.
- Named operators are visible on the team section, but personal contact channels and personal LinkedIn profiles are not linked by the official site.
- Sector exposure is derived from broad descriptions, not portfolio-level disclosure.

**What almost fooled me / what I had to reconcile:**

The first pass only captured Cat Trail as a Dekker-family entity, not a named operator. I almost left the principal layer at the family level until the official team section exposed David Dekker, Russell Dekker, and Andrew Budinoff with roles. I still did not promote personal contact channels because the site links only to the company LinkedIn page.

**What would change the conclusion:**

- If the site is found to be a multi-family office serving multiple families, the single-family office classification must be downgraded.
- If the Dekker family attribution is later contradicted by a primary source, principal_name must be cleared.

## Validation Chain 2 - JFG Family Office (`fo_007`)

- **Family office type:** `multi_family_office`
- **Discovery source:** organic public-web discovery, filtered through `apify/google-search-scraper` for own-domain results.
- **Extraction method:** Firecrawl markdown of the official site URLs below; quotes selected manually from the markdown.
- **Validation logic:** live HTTP check on every source URL, ≥2 reachable sources, score ≥80, no discovery-only directory sources, name overlap with the assessment sample workbook checked and clear.

**Enrichment steps (in order applied):**

- Captured official site markdown via Firecrawl on 2026-05-17 for the home and /better-way pages; the Form CRS PDF was downloaded and text-extracted with `pypdf` after Firecrawl skipped PDF text.
- Verified the canonical domain (jfgfamilyoffice.com) against the legacy jfgwealth.net brand; older references redirect to the current site.
- Captured corporate contact signals via Apify vdrmota/contact-info-scraper and Apify automation-lab/linkedin-company-scraper.
- Recent activity: promoted a 2025+ Business Journals headline ('JFG Family Office brings holistic wealth and philanthropy services to Dallas') into recent_activity, with source URL and date.

### Source: `https://jfgfamilyoffice.com/`

- **Source type:** official_site_home
- **Claim supported:** current brand and family-office identity
- **Quote 1:** "Introducing a better way to manage your family’s wealth "A Better Way" One of the Nation’s Premier Integrated Family Offices Our Legacy Our history as…"
- **Quote 2:** "Our Clientele We serve an exclusive clientele with fully integrated family office services."

### Source: `https://jfgfamilyoffice.com/better-way`

- **Source type:** official_site_better_way_page
- **Claim supported:** single-family-office origin story now serving client families as an MFO
- **Quote 1:** "Better Service JFG was built to serve our founding family as a single family office."
- **Quote 2:** "We provide access to the same investments, under the same terms, with the same level of service afforded to our founding family."

### Source: `https://jfgfamilyoffice.com/pdf/JFG-Family-Office-Form-CRS.pdf`

- **Source type:** official_form_crs_pdf
- **Claim supported:** regulatory Form CRS disclosure of advisory relationship
- **Quote 1:** "Johnson Financial Group LLC, DBA JFG Family Office is registered with the Securities and Exchange Commission as an investment adviser."
- **Quote 2:** "JFG's minimum annual fee is $100,000."

**What remains uncertain:**

- Former jfgwealth.net brand still surfaces in older references; current canonical domain is jfgfamilyoffice.com.
- Leadership names and roles are visible in official bios, but personal contact channels are not linked by the official site.

**What almost fooled me / what I had to reconcile:**

JFG uses both legacy JFG Wealth wording and the current JFG Family Office brand. I treated the current domain as canonical, then used the Form CRS PDF only after manually extracting the PDF text instead of pretending Firecrawl had read it.

**What would change the conclusion:**

- If the Form CRS PDF describes JFG as a generic RIA without family-office framing, the MFO label must be re-evaluated.
- If the better-way page is removed and no MFO/SFO-origin language is preserved anywhere on the site, the classification basis weakens.

## Validation Chain 3 - Verlinvest (`fo_020`)

- **Family office type:** `family_backed_investment_firm`
- **Discovery source:** organic public-web discovery, filtered through `apify/google-search-scraper` for own-domain results.
- **Extraction method:** Firecrawl markdown of the official site URLs below; quotes selected manually from the markdown.
- **Validation logic:** live HTTP check on every source URL, ≥2 reachable sources, score ≥80, no discovery-only directory sources, name overlap with the assessment sample workbook checked and clear.

**Enrichment steps (in order applied):**

- Captured official site markdown via Firecrawl on 2026-05-17 for the home and /approach pages; the /team page is a grid of profile cards, so exact card text was used for names and roles rather than a fabricated narrative sentence.
- Confirmed the family-backed framing through the /approach page's verbatim phrasing 'as a family-backed business'.
- Recent activity: promoted a 2025 YourStory.com headline ('Verlinvest invests $75M in Coimbatore-based The Eye Foundation') into recent_activity with source URL and date.
- Cross-checked the European HQ via Apify compass/crawler-google-places (Brussels, Belgium).

### Source: `https://www.verlinvest.com/`

- **Source type:** official_site_home
- **Claim supported:** family-backed investment company identity and AB InBev heritage context
- **Quote 1:** "Learn how we do it Long-term, flexible capital We use patient, permanent capital to build businesses for the long-term."
- **Quote 2:** "Futurekind: Discover Verlinvest’s 30 Years of Heritage in Motion."

### Source: `https://www.verlinvest.com/approach/`

- **Source type:** official_site_approach_page
- **Claim supported:** long-term consumer-brand investment thesis
- **Quote 1:** "Lifestyle Long-term, flexible capital For nearly 30 years, as a family-backed business, we have empowered companies and founders to challenge the status quo to do…"
- **Quote 2:** "We typically invest between €20 to €200m and take a long term view Read more about some of our brands"

### Source: `https://www.verlinvest.com/team/`

- **Source type:** official_site_team_page
- **Claim supported:** team composition and family-sponsor context
- **Quote 1:** "Roberto Italia Chief Executive Officer"
- **Quote 2:** "Rachel Citera Principal, New York"

**What remains uncertain:**

- Family sponsor wording (de Spoelberch and related families) is intentionally broad because ownership structure varies across sources.
- Not a classic single-family office — labeled family_backed_investment_firm so the row is not mis-classified as an SFO.

**What almost fooled me / what I had to reconcile:**

Verlinvest is not a classic SFO. The strongest evidence says `family-backed business`, so I kept the label broad. The team page also looked like a failed extraction at first, but the markdown did contain profile-card names and roles; I used those exact card strings and did not invent a sentence around them.

**What would change the conclusion:**

- If public filings show Verlinvest is now majority-owned outside the founding families, the family-backed classification must be revisited.
- If the team page de-emphasizes family sponsor framing, source_notes must be updated to reflect a pure investment-firm description.

