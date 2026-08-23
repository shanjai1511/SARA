# PhD Roadmap — SARA to Doctorate
**Track: Fashion Market Intelligence (AI / Data Science)**
**Estimated Duration: 3.5 – 4 Years**
**Start Date: April 2026**

---

## How to Read This Document

- Every week has specific **tasks** and a **professor/application** action
- Professor actions are marked with **[PROF]**
- Milestones are marked with **[MILESTONE]**
- The plan assumes you are working on this part-time in the first few months while building the dataset, then transitioning to full-time once admitted
- Adjust the start date offsets to your actual situation — the relative ordering is what matters

---

## Pre-Phase: Foundations (Weeks 1–4)
> Goal: Get the data engine running continuously and prepare your "hook" for professors.

---

### Week 1 — Start the Data Clock

**Technical:**
- Enable daily automated crawls for at least 5 sites (start with open-access, no-paywall sites: `fashion_united_global_com`, `apparel_resources_com`, `flipkart_com`, `styleunion_com`, `myntra_com`)
- Add a `runs/` log table or simple SQLite DB that records: site, run_date, urls_discovered, urls_fetched, urls_parsed, timestamp
- Verify the `sara-scheduler` systemd service is running and survives reboots
- Confirm Elasticsearch is receiving data: run `curl localhost:9200/sara-commerce-crawl/_count`

**Professor [PROF]:**
- Open Google Scholar. Search: "fashion trend detection web crawling", "e-commerce price intelligence", "fashion NLP dataset"
- Read the top 10 most-cited papers (abstract + conclusion only). Note which labs/authors keep appearing.
- Start a spreadsheet: `Professor Tracker.xlsx` with columns: Name, University, Lab, Key papers, Email, Status

---

### Week 2 — Add Product Timeseries Storage

**Technical:**
- For each commerce site, implement a product deduplication key (ASIN for Amazon, product URL path for others)
- Add a Postgres or SQLite table: `product_snapshots(product_id, site, price, in_stock, scraped_at)`
- Wire the parser output to insert into this table on every run (in addition to ES/CSV)
- Test: run flipkart_com twice, verify two rows appear for the same product with different timestamps

**Why this matters:** This table is the raw material for Papers 3 and 4. Every day you delay costs you training data you can never recover.

**Professor [PROF]:**
- Identify 5 professors from your Week 1 search
- For each: read their most recent paper fully, not just abstract
- Note: Are they taking students? (check lab page for "openings" or "join us")
- Note: Do they have active PhD students? (good sign they supervise actively)

---

### Week 3 — NLP Pipeline Skeleton

**Technical:**
- Install spaCy and the `en_core_web_trf` transformer model
- Write a script `tools/extract_entities.py` that takes a media article (from `sara-media-crawl` ES index) and runs basic NER
- Note all the entities that spaCy gets WRONG for fashion text (e.g., it will miss "wide-leg trousers" as a trend, classify "Gucci" as ORG not BRAND)
- Create a `data/annotation/` folder and save 50 raw media articles there for later labeling

**Professor [PROF]:**
- Narrow your list to 3 professors who are the best fit
- For each, find a paper they published that is most similar to your idea
- Write 3 draft cold emails (one per professor) — do not send yet

---

### Week 4 — Write the 2-Page System Summary

**Technical:**
- Run `python -m tools.validate_site --all` and fix any broken sites
- Add one new site to either media or commerce crawl (pick an easy one — SSR, no paywall)
- Make sure all 22+ sites are crawling daily without manual intervention

**[MILESTONE] Write the "Pitch Document":**
This 2-page PDF is your most important asset for professor outreach. It must contain:
1. What SARA is (1 paragraph, no jargon)
2. The dataset you are building (sites, volume, how long it has been running)
3. The specific research question you want to pursue
4. Why it is novel (what has NOT been done before)
5. One figure — the architecture diagram from the README

Use this as an attachment in professor emails. Do not send a wall of text.

**Professor [PROF]:**
- Finalize the 3 cold emails. Make each one specific:
  - Mention one of their papers by name and why it connects to your work
  - Attach the 2-page pitch document
  - One clear ask: "Would you have 20 minutes for a call to discuss whether this fits your group's direction?"
- Send all 3 emails this week

---

## Phase 1: Dataset and Paper 1 (Weeks 5–16)
> Goal: 3 months of clean longitudinal data. Write and submit the system paper.

---

### Week 5

**Technical:**
- Add Prometheus metric: `sara_product_price_change_total` — incremented when a product's price changes between runs
- Add metric: `sara_new_products_per_run` per site
- Verify Grafana dashboard shows these metrics

**Professor [PROF]:**
- Follow up on emails if no reply (one follow-up per professor, one week after first email)
- Research 2 more professors as backup — you want 5 active prospects at all times

---

### Week 6

**Technical:**
- Write `tools/price_timeseries.py` — a script that queries your `product_snapshots` table and plots price over time for a given product_id using matplotlib
- Generate 5 example charts for products you have data on so far
- These will go directly into Paper 1 as preliminary results figures

**Professor [PROF]:**
- If a professor replied: prepare for the call. Have a 5-minute verbal pitch ready.
  - "I have a live pipeline collecting from 22 fashion sites. I have X months of price history. I want to study Y."
  - Do not oversell. Be honest about what you have and what is still in progress.

---

### Week 7

**Technical:**
- Add `site_update_frequency.py` — measures how often each site updates its content (articles per day for media, new products per day for commerce)
- This answers: "how fresh does a crawl need to be?" — which is the scientific justification for your crawl schedule
- Run it across all 22 sites and save the results as a table

**Professor [PROF]:**
- Research PhD application requirements for your top 3 target universities
- Write down: application deadline, required documents, English test requirement (IELTS/TOEFL if needed), GRE requirement, fees
- Start a `PhD_Applications.xlsx` tracker

---

### Week 8 — Paper 1 Outline

**Technical:**
- Write the outline for Paper 1 in `docs/paper1_outline.md`:
  - Abstract (5 sentences: problem, system, dataset, key findings, conclusion)
  - Section 1: Introduction
  - Section 2: Related Work (you will fill this in)
  - Section 3: System Architecture (write from the README — you have this)
  - Section 4: Dataset Characterization (use your metrics and charts from weeks 6–7)
  - Section 5: Use Cases / Preliminary Results
  - Section 6: Conclusion
- Target venue: **WWW 2027 Industry Track** or **ECIR 2027 Demo Track** (deadlines are typically October–November)

**Professor [PROF]:**
- Start your Statement of Purpose (SoP) draft. Do not wait until applications open.
- Structure: (1) what problem you care about, (2) what you built, (3) what you want to research, (4) why this professor/university specifically
- First draft does not need to be good — just written

---

### Week 9

**Technical:**
- Write Section 3 of Paper 1 (architecture). Use the README as a base.
- Add a proper "Sites and Scale" table: site name, type, avg URLs/run, avg articles/day, requires proxy (Y/N)
- Run all 22 sites for at least 3 consecutive days and collect the statistics

**Professor [PROF]:**
- If you have a call scheduled with a professor: take it, ask these 3 questions:
  1. "Are you taking PhD students for the next intake?"
  2. "Is there a specific sub-problem within this space you think is most open?"
  3. "What would you want to see in an application from someone working on this?"

---

### Week 10

**Technical:**
- Write Section 4 of Paper 1 (dataset characterization)
- Figures to include:
  - URL discovery volume per site (bar chart)
  - Content update frequency per site (heatmap by day of week)
  - Price change frequency per commerce site
  - Crawl success rate (200 vs blocked) per site
- All figures should be publication quality (matplotlib with proper axis labels, font size ≥ 10)

**Professor [PROF]:**
- Research the specific PhD program structure at each target university
- Do they require a Masters first? (most UK/EU programs do not, most Indian programs do)
- Identify if there are Masters programs you should consider as a stepping stone (e.g., MSc by Research)

---

### Week 11

**Technical:**
- Write the Related Work section of Paper 1
- Papers to cite and situate your work against:
  - Cho & Garcia-Molina (2000) — web crawling fundamentals
  - Castillo (2005) — effective web crawling
  - Any recent papers on fashion e-commerce intelligence
  - Papers on web data pipelines at scale
- Use Google Scholar to find 15-20 relevant papers. Read abstract + intro of each.

**Professor [PROF]:**
- Ask someone (professor, mentor, senior colleague) to review your SoP draft
- Apply to take IELTS or TOEFL if required by your target universities (book at least 6 weeks ahead)

---

### Week 12

**Technical:**
- Write Introduction and Abstract of Paper 1
- The abstract must answer: (1) what problem, (2) what you built, (3) scale of dataset, (4) key finding, (5) where code/data is available
- Write a 1-paragraph "contributions" list — this is mandatory in CS papers

**Professor [PROF]:**
- Identify 2 conferences where you could present your work informally (workshops, local meetups, Indian NLP/IR conferences like FIRE, COMAD)
- These are networking opportunities, not publication targets — going to a conference and meeting people is very valuable at this stage

---

### Week 13 — Paper 1 First Full Draft

**Technical:**
- Assemble the full draft of Paper 1 (all sections)
- Target length: 6-8 pages in ACM two-column format
- Download the ACM LaTeX template and start formatting
- Share with anyone you trust technically for feedback

**Professor [PROF]:**
- Research the top 2 Indian universities for your track (IIT Bombay, IIT Delhi, IIIT Hyderabad for CS)
- Find the specific faculty member at each you want to work with
- Email them with the 2-page pitch document if you have not already

---

### Week 14

**Technical:**
- Revise Paper 1 based on feedback
- Make sure figures are properly referenced, citations are consistent, no broken references
- Add a "limitations" paragraph (reviewers will ask for this)
- Add a "data availability" statement if you plan to release part of the dataset

**Professor [PROF]:**
- Finalize your PhD application list: target 4-6 programs across India + 2-3 international
- Check application deadlines — most PhD programs in India open applications in December–January

---

### Week 15

**Technical:**
- Proofread Paper 1 completely
- Run it through Grammarly or similar for language
- Ask a native English speaker to read the abstract and introduction if possible

**[MILESTONE]:**
- You should have: (1) 10+ weeks of daily crawl data, (2) product timeseries data with price changes, (3) Paper 1 full draft ready to submit

**Professor [PROF]:**
- If you have a professor who is interested: ask if they would be willing to co-author or provide feedback on Paper 1 before submission — this is a normal and strategic ask
- Even if they say no, the ask demonstrates you are serious

---

### Week 16 — Submit Paper 1

**Technical:**
- **[MILESTONE] Submit Paper 1** to your target venue (WWW Industry Track, ECIR Demo, or CIKM)
- After submission, immediately start on Paper 2 — do not wait for the review

**Professor [PROF]:**
- Email all professors you have been in contact with: "I just submitted a paper on SARA to [venue]. Happy to share the preprint."
- Upload the preprint to arXiv (cs.IR or cs.AI section) — this establishes your work as public and citable even before reviews come back

---

## Phase 2: NLP Layer and Paper 2 (Weeks 17–32)
> Goal: Build fashion NER dataset. Fine-tune a model. Write and submit Paper 2.

---

### Week 17

**Technical:**
- Install Label Studio or Prodigy for annotation
- Load 200 media articles from `sara-media-crawl` into the annotation tool
- Define your label taxonomy:
  - `BRAND` — e.g., "Gucci", "Zara", "Sabyasachi"
  - `TREND` — e.g., "wide-leg trousers", "quiet luxury", "dopamine dressing"
  - `MATERIAL` — e.g., "silk", "organic cotton", "recycled polyester"
  - `STYLE` — e.g., "Y2K", "minimalism", "streetwear"
  - `EVENT` — e.g., "Milan Fashion Week", "Lakme Fashion Week"

**Professor [PROF]:**
- Prepare PhD application documents: transcripts, recommendation letter requests, CV
- Send recommendation letter requests to your referees at least 6 weeks before any deadline

---

### Weeks 18–20 — Annotation Sprint

**Technical:**
- Annotate 100 articles per week (target: 500 total by end of week 20)
- Write inter-annotator agreement calculation script (Cohen's Kappa) — even if you annotate alone, you need to re-annotate 50 articles a second time after 2 weeks to measure consistency
- This number (Kappa score) goes directly in Paper 2

**Professor [PROF]:**
- Weeks 18-20: write your research proposal document (required by most PhD programs, 1000–2000 words)
  - Problem statement
  - Related work (4-5 key papers)
  - Proposed methodology
  - Expected contributions
  - Tentative timeline
- This is different from the SoP — the SoP is about you, the research proposal is about the work

---

### Weeks 21–22 — Model Training

**Technical:**
- Convert your annotated data to IOB2 format (standard for NER)
- Fine-tune `bert-base-uncased` or `roberta-base` on your dataset using HuggingFace Transformers
- Split: 80% train, 10% dev, 10% test
- Report F1 score per entity type on the test set
- Baseline comparison: run vanilla spaCy `en_core_web_trf` on the same test set and show your model wins

**Professor [PROF]:**
- Submit at least 1 PhD application this month
- The earlier you apply the better — many programs admit on a rolling basis

---

### Weeks 23–24 — Paper 2 Writing

**Technical:**
- Write Paper 2: "Fashion-NER: A Named Entity Recognition Dataset and Model for Fashion Editorial Text"
- Key sections: dataset creation, annotation process, model fine-tuning, results table, error analysis
- Include a qualitative analysis: show 3-4 examples where your model works and 2-3 where it fails — reviewers respect honesty

**Professor [PROF]:**
- Continue submitting PhD applications
- For each program: check if you need to contact a professor before applying (most Indian programs require you to have a supervisor lined up)

---

### Weeks 25–28 — Dataset Release and Submission

**Technical:**
- Release the annotated dataset on Hugging Face Datasets (even if small — 500 articles)
- A dataset release in a paper significantly increases acceptance rate and citation count
- Submit Paper 2 to ACL Findings, EMNLP, or COLING

**Professor [PROF]:**
- By Week 28: you should have submitted 3-4 PhD applications
- Follow up with any professor who has not replied to your initial email (third and final contact)

---

### Weeks 29–32 — Bridge Work (Between Paper 2 Submission and Results)

**Technical:**
- While waiting for Paper 2 reviews, work on the core data infrastructure for Paper 3:
  - Build a trend salience score: for each TREND entity extracted from media articles, compute a weekly frequency (how many articles mention this trend per week)
  - Store this as a timeseries: `trend_weekly(trend_text, week_start, mention_count, site_name)`
  - Build the same for commerce: `product_availability_weekly(style_category, week_start, product_count, site_name)`

**Professor [PROF]:**
- Weeks 29-32: interview prep for any PhD interview invitations
  - Know your work cold: you must be able to explain SARA in 2 minutes to a non-technical person
  - Prepare for: "What is your research question?", "What is novel?", "What is your methodology?", "What do you expect to find?"

---

## Phase 3: Core Research and Paper 3 (Weeks 33–60)
> This is the heart of the PhD. You need at least 12 months of data before this analysis is meaningful.

---

### Weeks 33–36 — Temporal Correlation Setup

**Technical:**
- You now have ~8 months of data. Start the lag correlation analysis.
- For each trend entity that appears in ≥ 50 media articles: correlate its weekly media mention count against new product listings on commerce sites mentioning the same trend
- Use Granger causality test: does media coverage Granger-cause commerce inventory changes?
- Expected finding: media leads commerce by 2-6 weeks for trend items

---

### Weeks 37–40 — Price Intelligence Analysis

**Technical:**
- Run the price correlation analysis across sites:
  - Does Myntra reprice within N days after Ajio changes price on the same product category?
  - Use DTW (Dynamic Time Warping) or simple cross-correlation on price timeseries
- Run entity analysis on commerce product titles: cluster products by style (using Fashion-NER from Paper 2) and track cluster-level pricing over time

---

### Weeks 41–48 — Paper 3 Writing

**Technical:**
- Write Paper 3: "Media-Commerce Signal Propagation in Indian Fashion Markets"
- This is your primary research contribution
- Key results to include:
  - The lag distribution (media → commerce) by category
  - Statistical significance of Granger causality findings
  - Price correlation patterns across competing sites
  - Case studies: 3-5 specific trend "cycles" you can trace from media mention to product availability

**Professor [PROF]:**
- By Week 48: you should have received admission decisions from some programs
- If admitted: begin formal PhD registration process
- If not yet admitted: revise applications and reapply next cycle with Paper 1 and Paper 2 now accepted/published

---

### Weeks 49–52 — Submit Paper 3

**[MILESTONE] Submit Paper 3** to KDD, SIGIR, or WWW (research track)

**This is the paper that defines your PhD.** Take the time to get it right. If reviewers reject it, revise seriously and resubmit — this paper will be rejected at least once before it gets accepted. That is completely normal.

---

### Weeks 53–60 — Revision Cycles and Early Thesis Work

**Technical:**
- Respond to Paper 3 reviews (revision typically takes 1-2 months)
- Begin writing thesis Chapter 1 (Introduction) and Chapter 2 (Background/Related Work) — these can be done now before Paper 3 is accepted
- Start planning Paper 4

---

## Phase 4: Paper 4 and Thesis (Weeks 61–100)

---

### Weeks 61–72 — Paper 4 (Forecasting)

**Technical:**
- Build the price/availability forecasting model
  - Input features: media trend signals (from Paper 2 entity extraction), historical price data, seasonal indicators
  - Model: start with ARIMAX (simple, interpretable), then try Temporal Fusion Transformer
  - Evaluation: RMSE, MAE on held-out data; compare against "no media signal" baseline to show the media signal adds value
- Write and submit Paper 4 to RecSys or ECML-PKDD

**Professor [PROF]:**
- Weeks 61-72: If you are enrolled in a PhD program, this is typically the end of your first year
- Submit your first formal progress report to your supervisor (most programs require this)

---

### Weeks 73–88 — Thesis Writing (Core Chapters)

Write the following chapters in order:

- **Chapter 3: SARA — The Data Collection Platform** (largely from Paper 1)
- **Chapter 4: Fashion NER** (from Paper 2)
- **Chapter 5: Media-Commerce Signal Propagation** (from Paper 3)
- **Chapter 6: Demand Forecasting** (from Paper 4)

Each thesis chapter is longer and more comprehensive than the paper — add more methodology detail, more error analysis, additional experiments reviewers made you cut for space.

---

### Weeks 89–100 — Thesis Completion and Defense

- **Chapter 1: Introduction** — frame the whole thesis as one coherent story
- **Chapter 7: Conclusion** — what did you find, what are the limitations, what comes next
- Submit thesis draft to supervisor (typically 3 months before defense)
- **[MILESTONE] PhD Defense**

---

## Professor Outreach — Master Template

### Cold Email Template

> Subject: PhD Enquiry — Fashion Market Intelligence Platform with Live Dataset
>
> Dear Professor [Name],
>
> I am reaching out because your work on [specific paper title] addresses a closely related problem to one I have been building infrastructure for.
>
> I have developed SARA (Scalable Automated Retrieval Architecture), a distributed web crawling platform that collects structured data from 22 fashion e-commerce and media sites (including Myntra, Ajio, WWD, and Business of Fashion). The system has been running in production for [X months] and has accumulated [X months] of longitudinal price and editorial data — a dataset I believe is unique in the academic literature for Indian fashion markets.
>
> My proposed research question is: *Does media coverage of fashion trends predict shifts in e-commerce product availability and pricing in Indian markets, and what is the lag?*
>
> I have attached a 2-page summary of the platform and the dataset. I would very much welcome a 20-minute call to understand whether this direction fits your group's current focus.
>
> Best regards,
> [Your name]
> [Your LinkedIn / GitHub with SARA code]

---

### Professor Target List — Where to Look

**India**

| Professor type | Where to look |
|---|---|
| Web mining / IR | IIT Bombay (CSE), IIT Delhi (CSE/EE), IIIT Hyderabad (LTRC, SEIL labs) |
| NLP / computational linguistics | IISc Bangalore, IIT Madras, Jadavpur University (NLPAI lab) |
| Data science / e-commerce | IIM Ahmedabad (CIIE), IIM Bangalore, ISB Hyderabad |
| Fashion technology | NIFT Delhi (limited PhD, but good for collaboration) |

**International (Funded positions)**

| Country | Where to look |
|---|---|
| Netherlands | University of Amsterdam (IRLab — Maarten de Rijke's group) |
| UK | UCL, University of Sheffield (NLP group), University of Edinburgh |
| Germany | MPI for Informatics (Saarbrücken), TU Berlin, LMU Munich |
| Singapore | NUS, NTU — strong IR/NLP labs, proximity to Indian market |

**How to find the right professor on Google Scholar:**

1. Search: `"fashion" "e-commerce" "trend" site:scholar.google.com`
2. Search: `"web crawling" "information extraction" "temporal"` 
3. Filter by "since 2022" to ensure they are still active
4. Check their lab page: are there current PhD students? Is there a "Join us" page?

---

## Summary Checklist — Year by Year

### Year 0 (Months 1–4, Pre-PhD)
- [ ] Daily crawls running reliably across 22 sites
- [ ] Product timeseries table capturing price changes
- [ ] 2-page pitch document written
- [ ] Cold emails sent to 5 professors
- [ ] Paper 1 submitted
- [ ] Preprint on arXiv
- [ ] At least 1 PhD application submitted

### Year 1
- [ ] Admitted to a PhD program
- [ ] 500 annotated articles (NER dataset)
- [ ] Fashion-NER model trained and evaluated
- [ ] Paper 2 submitted
- [ ] 12 months of longitudinal data accumulated

### Year 2
- [ ] Temporal correlation analysis complete
- [ ] Paper 3 (core contribution) submitted
- [ ] Thesis Chapters 3 and 4 drafted
- [ ] Paper 3 accepted (possibly after revision)

### Year 3
- [ ] Forecasting model complete
- [ ] Paper 4 submitted and accepted
- [ ] All thesis chapters drafted
- [ ] Thesis submitted to supervisor

### Year 3.5 – 4
- [ ] PhD Defense
- [ ] Thesis corrections complete
- [ ] Degree awarded

---

## The Single Most Important Rule

**Start collecting longitudinal data today.**

Every other part of this plan can be accelerated, delayed, or revised. The data cannot be backdated. The correlation study in Paper 3 and the forecasting model in Paper 4 require months of daily price and content history. The clock started when you first ran a crawl. Make sure it never stops.

---

*Last updated: April 2026*
