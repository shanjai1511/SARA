## SARA – Scalable Automated Retrieval Architecture

SARA is a **three‑stage web data pipeline** for discovering URLs, fetching pages, and parsing them into structured datasets. It is designed to be:

- **Config‑driven**: per‑site behavior is defined by small Python classes and YAML files.
- **Composable**: each stage (discovery → retriever → parser) is independent and connected via RabbitMQ.
- **Observable**: structured JSON logging with crawl context (project, site, schedule id, stage).

You can run a full crawl for a given project/site/schedule using a single command:

```bash
python crawl_runner.py <project> <site> <schedule_id>
```

---

## Features

- **Three‑stage pipeline**
  - **URL Discovery**: find all URLs to crawl (e.g. product pages, articles).
  - **URL Retrieval**: robust, retried HTTP fetches, HTML caching.
  - **URL Parsing**: extract structured fields into CSV.

- **Pluggable per‑site logic**
  - Site‑specific logic lives in `url_discovery/`, `url_retriever/`, `url_data_parser/`.
  - Quickly scaffold new sites with `creation_script.py`.

- **Queue‑based decoupling**
  - Stages communicate via RabbitMQ queues.
  - Easy to add more retriever/parser workers later.

- **Structured logging**
  - Every log can include `stage`, `schedule_id`, `project`, and `site`.

---

## Directory Layout

```text
SARA/
  README.md                 # (this file)
  crawl_runner.py           # runs discovery → retriever → parser
  creation_script.py        # scaffolds new project+site configs
  delete_files_automated.py # deletes project+site configs
  proxy_config.py           # proxy list & env override
  logs/
    pipeline.log            # structured logs (JSON)
  scrape_output/
    discovery_output/
    retriever_output/
    parser_output/
  sdf_module/
    files_import.py         # central imports & constants
    sdf_fetch.py            # HTTP, retries, parsing, logging, RabbitMQ
    url_discovery.py        # discovery driver
    url_retriever.py        # retriever driver
    url_parser.py           # parser driver
  url_discovery/
    <project>/
      <site>_<project>.py   # per-site discovery logic
      <site>_<project>.yml  # per-site discovery config
  url_retriever/
    <project>/
      <site>_<project>.py   # usually thin wrappers
      <site>_<project>.yml  # retriever config (request params, etc.)
  url_data_parser/
    <project>/
      <site>_<project>.py   # per-site parsing logic
      <site>_<project>.yml  # per-site fields config
```

---

## Core Modules

### `sdf_module/files_import.py`

**Role**: central place for imports and shared constants.

- **Imports**:
  - Standard library: `os`, `glob`, `sys`, `subprocess`, `hashlib`, `json`, `csv`, `logging`, `math`, `re`, `pdb`, `time`, etc.
  - Third‑party: `requests`, `yaml`, `openpyxl`, `bs4.BeautifulSoup`, `lxml.etree`, `lxml.html`, `pika`, `pandas`, etc.
  - From project: `from proxy_config import *`.
  - `from contextvars import ContextVar` for crawl context.

- **Globals**:
  - **`base_dir`**: resolved dynamically from `Path(__file__).resolve().parent.parent` (project root).
  - **`CLOUDAMQP_URL`**:
    - Reads from `os.environ["CLOUDAMQP_URL"]` if set.
    - Falls back to a default CloudAMQP URL (should be overridden in production).

Every core module does:

```python
from .files_import import *
```

so it shares the same environment.

### `sdf_module/sdf_fetch.py` – Fetching, Parsing, Logging, RabbitMQ

**Role**: reusable toolbox for:

- HTTP requests with retries.
- HTML parsing helpers.
- Logging with per‑crawl context.
- RabbitMQ channel creation.

#### Crawl context and logging

- Uses a `ContextVar[dict]` to store crawl context:

  ```python
  {
    "stage": "discovery" | "retriever" | "parser",
    "schedule_id": "<schedule-id>",
    "project": "<project>",
    "site": "<site>"
  }
  ```

- **`sdfFetch.set_crawl_context(stage, schedule_id, project, site)`**
  - Called at the start of `UrlDiscovery.main`, `UrlRetriever.main`, `UrlParser.main`.
  - Any log emitted during that stage automatically includes this context.

- **`sdfFetch.print_info_message(status, info=None, url=None)`**  
  **`sdfFetch.print_error_message(status, info)`**

  - Build a JSON object:

    ```json
    {
      "status": "info|success|error",
      "info": "<message>",
      "url": "<optional-url-or-path>",
      "crawl": {
        "stage": "...",
        "schedule_id": "...",
        "project": "...",
        "site": "..."
      }
    }
    ```

  - Log at INFO or ERROR level to `logs/pipeline.log` and stdout.

This gives you **structured, contextualised logs** for every crawl.

#### RabbitMQ

- **`get_rabbitmq_channel()`**:
  - Uses `pika.BlockingConnection` with `CLOUDAMQP_URL`.
  - Returns `(connection, channel)`.

#### HTTP request with retries

- **`get_page_content_hash(url, proxy=None, extended_header=None, max_retries=3, timeout=30, retry_statuses=None)`**:

  - Validates `url`.
  - For each attempt (0..`max_retries`):
    - Optionally attach headers via `extended_header`.
    - Optionally use a random proxy from `webshare_proxy` if `proxy == "webshare_proxy"`.
    - Call `session.get(url, verify=False, timeout=timeout)`.
    - If `status_code == 200`:
      - Save HTML to `cache/{md5(url)}.html`.
      - Log `"Page fetched successfully."`.
      - Return `{"page_doc": <html>, "status_code": 200, "url": url}`.
    - If `status_code` in retryable list (defaults to `429, 500, 502, 503, 504`):
      - Log and wait with exponential backoff (`1, 2, 4, ...` seconds), then retry.
    - Otherwise:
      - Log error and return with empty page_doc and the failing status code.
  - On repeated `RequestException`s:
    - Log failures and final error after all attempts.

This centralizes **resiliency and caching** for all HTTP calls.

#### HTML parsing and selectors

- **`get_parsed_tree(page_doc, format="lxml")`**:
  - `format="lxml"` → returns `lxml.html` element tree.
  - otherwise → returns `BeautifulSoup` document.

- **`get_value_from_xpath(parsed_tree, xpath_expr, count, attr="none")`**:
  - For lxml trees: uses `.xpath()`, returns text or attribute values.
  - For BeautifulSoup: falls back to `.select()` (CSS).

- **`get_value_from_css_selector(parsed_tree, css_selector, count, attr="none")`**:
  - For lxml: `.cssselect()`.
  - For BeautifulSoup: `.select()`.

- **`encode(array)`**:
  - Accepts string or iterable, returns an MD5 hex string.
  - Used to build deterministic file names (cache, retriever output, etc.).

---

## Stage 1: URL Discovery (`sdf_module/url_discovery.py`)

**Goal**: starting with **seed URLs**, generate a set of final URLs (e.g. product pages) and push them into a RabbitMQ queue.

### Discovery configuration (YAML)

Example: `url_discovery/internal_feasibility/styleunion_com_internal_feasibility.yml`:

```yaml
depth0:
  seed_url: ["https://styleunion.in/collections/women-caps", ...]
  method_name: get_pagination_url
depth1:
  method_name: get_product_url
```

- **`depth0.seed_url`**: list of starting URLs.
- **`depthN.method_name`**: name of method on the site discovery class that transforms a list of URLs at depth N into URLs for depth N+1.

### Site‑specific discovery (Python)

Example: `url_discovery/internal_feasibility/styleunion_com_internal_feasibility.py`:

- **`get_pagination_url(keyurl, depth, current_depth_level)`**:
  - Fetch category page.
  - Read `productCount` from embedded script.
  - Compute number of pages and generate pagination URLs.

- **`get_product_url(url, depth, current_depth_level)`**:
  - Fetch listing page.
  - Extract product links using XPath.
  - Build full URLs and append metadata (e.g. rank).

### Discovery driver: `UrlDiscovery`

- **`__init__(base_dir, project_name, site_name)`**
  - Stores project/site names and sets up internal state.

- **`main(schedule_key)`**
  - Sets crawl context: `stage="discovery"`, `schedule_id=schedule_key`, `project`, `site`.
  - Creates output dir: `scrape_output/discovery_output/<project>/`.
  - Creates an empty TXT file for this schedule.
  - Calls `main_execution(schedule_key)`.
  - On completion, logs URLs discovered.

- **`main_execution(schedule_key)`**
  - Loads YAML (depth config).
  - Dynamically imports the site discovery class from `url_discovery/<project>/<site>_<project>.py`.
  - Builds an instance and calls `get_final_url(...)`.

- **`get_final_url(url_list, depth, current_depth_level, max_depth, module_instance, schedule_key)`**
  - Uses the `method_name` at the current depth to transform `url_list`.
  - Sleeps between requests to avoid overloading servers.
  - If at final depth:
    - Calls `push_urls_to_queue(result_url, schedule_key)`.
    - Increments internal count.
  - Else:
    - Recursively calls itself for the next depth.

- **`push_urls_to_queue(result_url, schedule_key)`**
  - Constructs queue name:

    ```python
    f"{self.site_name}_{self.project_name}_{schedule_key}_queue"
    ```

  - Declares a durable queue.
  - Publishes each URL as a persistent message.
  - Logs success.

**Output of Stage 1**:

- RabbitMQ queue with **final target URLs** for this crawl.
- Optional discovery TXT file per schedule (currently only created and cleared).

---

## Stage 2: URL Retrieval (`sdf_module/url_retriever.py`)

**Goal**: consume URLs from the queue, fetch pages (with retries), and write HTML + metadata to disk.

### Request configuration

Retriever reads **request params** from the discovery YAML (under `request_params`):

```yaml
request_type: curl
request_params:
  max_retries: 3
  timeout: 30
  # extended_header: {}
```

- **`max_retries`**, **`timeout`** customize `sdfFetch.get_page_content_hash`.
- **`extended_header`** can set headers like `User-Agent`, cookies, etc.

### Retriever driver: `UrlRetriever`

- **`__init__(base_dir, project_name, site_name)`**
  - Stores project/site and sets up base paths.

- **`fetch_retriever_output(schedule_key)`**
  - Sets up queue name: `"{site}_{project}_{schedule_key}_queue"`.
  - Reads up to a configured maximum number of messages.
  - Decodes bodies into URL strings.
  - Acks each message.
  - Returns a **list of URL keys**.

- **`main(schedule_key)`**
  - Sets crawl context: `stage="retriever"`, `schedule_id=schedule_key`.
  - Loads `request_params` from YAML.
  - Calls `fetch_retriever_output` and logs how many URLs found.
  - Creates output directory:

    ```text
    scrape_output/retriever_output/<project>/<site>_<project>/<schedule_id>/
    ```

  - For each URL key:
    - Skip empty keys.
    - Derive base URL before `|` (if metadata encoded).
    - Sleep a bit to avoid hitting rate limits.
    - Call `sdfFetch.get_page_content_hash(...)` with `extended_header`, `max_retries`, `timeout`.
    - Build an HTML file path using current date + `sdfFetch.encode(key)`.
    - Write page content to disk if status is 200.
    - Log success or failure.
    - Append a metadata line `{"url": key, "output_file": "<path>"}` to `<schedule_id>_queue.txt`.
  - At the end, logs `Pages fetched: <ok>/<total>` for this schedule.

**Output of Stage 2**:

- **HTML files** under:

  ```text
  scrape_output/retriever_output/<project>/<site>_<project>/<schedule_id>/
  ```

- **Metadata file**:

  ```text
  <schedule_id>_queue.txt
  ```

  containing per‑line `str({"url": key, "output_file": path})`.

---

## Stage 3: URL Parsing (`sdf_module/url_parser.py`)

**Goal**: turn fetched HTML into structured records (CSV) using per‑site parser logic.

### Parser configuration (YAML)

Example: `url_data_parser/internal_feasibility/styleunion_com_internal_feasibility.yml`:

```yaml
---
domain: styleunion.com
fields:
  crawl_timestamp:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  uniq_id:
    ...
  page_url:
    ...
  product_name:
    ...
  # etc...
```

- **`fields`** defines which logical fields SARA should produce.
- Actual extraction is implemented in the Python parser class (one method per field).

### Site‑specific parser class

Example: `StyleunionComInternalFeasibility`:

- `modify_page_doc(inhash, page_doc)` – optionally splits a page into multiple sub‑documents (e.g. multiple products per page).
- `get_crawl_timestamp(page_doc, inhash)` – typically returns current datetime.
- `get_uniq_id(page_doc, inhash)` – e.g. uses `sdfFetch.encode(inhash)`.
- `get_page_url`, `get_product_name`, `get_list_price`, `get_size`, `get_color`, etc.

Each `get_<field>` should handle missing elements gracefully and return a value or `None`.

### Parser driver: `UrlParser`

- **`__init__(base_dir, project_name, site_name)`**
  - Prepares `parser_dir = base_dir / "url_data_parser"`.

- **`extract_records(inhash, page_doc, config, site_instance)`**
  - Calls `site_instance.modify_page_doc(inhash, page_doc)`:
    - If returns subsections: one record per subsection.
    - If returns empty list: default to one record using the full `page_doc`.
  - For each section:
    - For each field in `config["fields"]`:
      - Compute `method_name = f"get_{field}"`.
      - If method exists on `site_instance`:
        - Call it and capture any exceptions.
    - Append record dict to `records`.
  - Logs completion and returns list of records.

- **`main(schedule_key)`**
  - Sets crawl context: `stage="parser"`, `schedule_id=schedule_key`.
  - Loads parser YAML config.
  - Dynamically loads the site parser class from `url_data_parser/<project>/<site>_<project>.py`.
  - Reads the retriever metadata file for this schedule.
  - Logs how many pages will be processed.
  - For each metadata line:
    - Evaluate into a dict (currently via `eval`, could be hardened later).
    - Open HTML file and parse with `etree.HTML`.
    - Call `extract_records(...)` to get records for that page.
    - Accumulate `total_records`.
    - Append records to a CSV:

      ```text
      scrape_output/parser_output/<project>/<site>_<project>_<schedule_id>/<site>_<project>.csv
      ```

  - At the end, logs `Records extracted: <records> from <pages> pages`.

**Output of Stage 3**:

- A **CSV file** containing all structured data for this crawl.

---

## Orchestration: Running the Full Pipeline

### Via `crawl_runner.py`

```bash
python crawl_runner.py <project> <site> <schedule_id>
```

Examples:

```bash
# Internal feasibility on styleunion.com
python crawl_runner.py internal_feasibility styleunion_com 20260207

# Media crawl on vogue.in
python crawl_runner.py media_crawl vogue_in 20260207
```

What happens:

1. **Discovery**: `python -m sdf_module.url_discovery <project> <site> <schedule_id>`
2. **Retriever**: `python -m sdf_module.url_retriever <project> <site> <schedule_id>`
3. **Parser**: `python -m sdf_module.url_parser <project> <site> <schedule_id>`

`crawl_runner.py` prints stage start/complete messages with `schedule_id`. Each subprocess writes its own logs to `logs/pipeline.log`.

---

## Adding a New Site

### 1. Scaffold configs and classes

```bash
python creation_script.py <project_name> <site_name>
```

This creates:

- `url_discovery/<project>/<site>_<project>.py|yml`
- `url_retriever/<project>/<site>_<project>.py|yml`
- `url_data_parser/<project>/<site>_<project>.py|yml`

### 2. Implement discovery logic

- Edit `url_discovery/<project>/<site>_<project>.py`:
  - Fill in methods like `get_pagination_url`, `get_product_url`.
- Update YAML to define `depth0.seed_url` and per‑depth `method_name`.

### 3. Configure retriever (optional)

- Edit `url_retriever/<project>/<site>_<project>.yml`:
  - Set `request_params.max_retries`, `timeout`, `extended_header` as needed.

### 4. Implement parser logic

- Edit `url_data_parser/<project>/<site>_<project>.py`:
  - Implement `modify_page_doc` and each `get_<field>` using XPath/CSS.
- Update YAML `fields` to match which `get_` methods you’ve implemented.

### 5. Run and validate

- Use `crawl_runner.py` with the new project and site.
- Inspect:
  - `logs/pipeline.log` for structured logs.
  - `scrape_output/` for HTML and CSV outputs.

---

## Logging and Monitoring

- **Central log file**: `logs/pipeline.log`
- All logs are **JSON strings**, usually containing:
  - `status` (e.g. `"info"`, `"success"`, `"error"`)
  - `info` (human‑readable message)
  - `url` or file path (where relevant)
  - `crawl` context:

    ```json
    "crawl": {
      "stage": "retriever",
      "schedule_id": "20260207",
      "project": "internal_feasibility",
      "site": "styleunion_com"
    }
    ```

This makes it straightforward to:

- Filter logs by `stage`, `schedule_id`, `project`, or `site`.
- Ship logs to an external system (e.g. ELK, Datadog) and create dashboards for pipelines.

---

## Quick Module‑Only Commands

For direct module runs (bypassing `crawl_runner.py`):

```bash
# Discovery only
python -m sdf_module.url_discovery internal_feasibility styleunion_com 20260207

# Retriever only
python -m sdf_module.url_retriever internal_feasibility styleunion_com 20260207

# Parser only
python -m sdf_module.url_parser internal_feasibility styleunion_com 20260207
```
