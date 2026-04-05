import argparse
from pathlib import Path
from sdf_module.files_import import *
from typing import Optional


def print_status(status: str, file_name: str, project: str, site_name: str, info: str) -> None:
    message = {
        "status": status,
        "file_name": file_name,
        "project": project,
        "site_name": site_name,
        "info": info,
    }
    print(json.dumps(message, indent=4))


def create_project_structure(base_path, project_name, site_name, py_content, yml_content):
    project_path = os.path.join(base_path, project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
        print_status("created", project_path, project_name, site_name, "Directory created")

    py_file_path = os.path.join(project_path, f"{site_name}_{project_name}.py")
    yml_file_path = os.path.join(project_path, f"{site_name}_{project_name}.yml")

    with open(py_file_path, 'w', encoding='utf-8') as py_file:
        py_file.write(py_content)
        print_status("created", py_file_path, project_name, site_name, "Python file created")

    with open(yml_file_path, 'w', encoding='utf-8') as yml_file:
        yml_file.write(yml_content)
        print_status("created", yml_file_path, project_name, site_name, "YAML file created")


def _discovery_py(class_name: str, project_name: str) -> str:
    is_media = "media" in project_name.lower()
    if is_media:
        return (
            f"from sdf_module.url_discovery import *\n"
            f"from core.discovery_helpers import wordpress_pages, querystring_pages\n"
            f"from urllib.parse import urljoin\n"
            f"\n"
            f"class {class_name}():\n"
            f"\n"
            f"    def get_pagination_url(self, keyurl, depth, current_depth_level):\n"
            f"        pagination_url = []\n"
            f"        try:\n"
            f"            # Most media sites use WordPress /page/N/ pagination.\n"
            f"            # Swap for querystring_pages(keyurl) if the site uses ?page=N instead.\n"
            f"            pagination_url = wordpress_pages(keyurl, count=10)\n"
            f"        except Exception as e:\n"
            f"            print(f\"Exception occurred: {{e}}\")\n"
            f"        return pagination_url[:10]\n"
            f"\n"
            f"    def get_product_url(self, url, depth, current_depth_level):\n"
            f"        product_url = []\n"
            f"        try:\n"
            f"            # TODO: set correct domain and article path prefixes\n"
            f"            DOMAIN = \"example.com\"\n"
            f"            ARTICLE_PATHS = [\"/news/\", \"/article/\", \"/features/\"]\n"
            f"            dom = sdfFetch.get_page_content_hash(url)\n"
            f"            if dom.get(\"status_code\") != 200:\n"
            f"                raise Exception(\"No proper DOM found\")\n"
            f"            parsed_tree = html.fromstring(dom.get(\"page_doc\", \"\"))\n"
            f"            seen = set()\n"
            f"            for link in parsed_tree.xpath(\"//a[@href]/@href\"):\n"
            f"                full = urljoin(url, link)\n"
            f"                if DOMAIN not in full:\n"
            f"                    continue\n"
            f"                if not any(p in full for p in ARTICLE_PATHS):\n"
            f"                    continue\n"
            f"                if full not in seen:\n"
            f"                    seen.add(full)\n"
            f"                    product_url.append(full)\n"
            f"        except Exception as e:\n"
            f"            print(f\"Exception occurred: {{e}}\")\n"
            f"        return product_url[:10]\n"
        )
    else:
        return (
            f"from sdf_module.url_discovery import *\n"
            f"from core.discovery_helpers import querystring_pages, wordpress_pages\n"
            f"from urllib.parse import urljoin\n"
            f"\n"
            f"class {class_name}():\n"
            f"\n"
            f"    def get_pagination_url(self, keyurl, depth, current_depth_level):\n"
            f"        pagination_url = []\n"
            f"        try:\n"
            f"            # Most commerce sites use ?page=N pagination.\n"
            f"            # Swap for wordpress_pages(keyurl) if the site uses /page/N/ instead.\n"
            f"            pagination_url = querystring_pages(keyurl, param=\"page\", start=1, count=10)\n"
            f"        except Exception as e:\n"
            f"            print(f\"Exception occurred: {{e}}\")\n"
            f"        return pagination_url[:10]\n"
            f"\n"
            f"    def get_product_url(self, url, depth, current_depth_level):\n"
            f"        product_url = []\n"
            f"        try:\n"
            f"            # TODO: update XPath to match product card links on this site\n"
            f"            dom = sdfFetch.get_page_content_hash(url)\n"
            f"            if dom.get(\"status_code\") != 200:\n"
            f"                raise Exception(\"No proper DOM found\")\n"
            f"            parsed_tree = html.fromstring(dom.get(\"page_doc\", \"\"))\n"
            f"            links = parsed_tree.xpath(\"//a[contains(@href,'/p/')]/@href | //a[contains(@href,'/product')]/@href\")\n"
            f"            seen = set()\n"
            f"            for link in links:\n"
            f"                full = urljoin(url, link)\n"
            f"                if full not in seen:\n"
            f"                    seen.add(full)\n"
            f"                    product_url.append(full)\n"
            f"        except Exception as e:\n"
            f"            print(f\"Exception occurred: {{e}}\")\n"
            f"        return product_url[:10]\n"
        )


def _discovery_yml(site_name: str) -> str:
    return f"""depth0:
  seed_url: ["https://TODO-set-seed-url.com/"]
  method_name: get_pagination_url
depth1:
  method_name: get_product_url
# Uncomment to route retriever fetches through the proxy pool:
# request_params:
#   proxy: webshare_proxy
#   timeout: 30
#   max_retries: 3
"""


def _parser_py_commerce(class_name: str) -> str:
    return f"""from sdf_module.url_parser import *

class {class_name}():

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        return current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        return str(inhash)

    @staticmethod
    def get_product_name(page_doc, inhash):
        # TODO: update XPath for this site
        elems = page_doc.xpath("//h1[@class='pdp-title']/text() | //h1/text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_list_price(page_doc, inhash):
        # TODO: update XPath for this site
        elems = page_doc.xpath("//*[contains(@class,'mrp')]//text() | //*[contains(@class,'list-price')]//text()")
        val = elems[0].strip() if elems else None
        if val:
            val = ''.join(c for c in val if c.isdigit())
        return int(val) if val else None

    @staticmethod
    def get_selling_price(page_doc, inhash):
        # TODO: update XPath for this site
        elems = page_doc.xpath("//*[contains(@class,'selling-price')]//text() | //*[contains(@class,'price')]//text()")
        val = elems[0].strip() if elems else None
        if val:
            val = ''.join(c for c in val if c.isdigit())
        return int(val) if val else None

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        # TODO: update XPath for this site
        elems = page_doc.xpath("//*[contains(@class,'discount')]//text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_size(page_doc, inhash):
        # TODO: update XPath — list of available sizes
        elems = page_doc.xpath("//*[contains(@class,'size-button')]//text()")
        return ", ".join(e.strip() for e in elems if e.strip()) or None

    @staticmethod
    def get_color(page_doc, inhash):
        elems = page_doc.xpath("//*[contains(@class,'color')]/@title | //*[contains(@class,'color')]//text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_description(page_doc, inhash):
        elems = page_doc.xpath("//*[contains(@class,'description')]//text()")
        return " ".join(e.strip() for e in elems if e.strip()) or None

    @staticmethod
    def get_sku(page_doc, inhash):
        elems = page_doc.xpath("//*[contains(@class,'sku')]//text() | //meta[@name='sku']/@content")
        return elems[0].strip() if elems else None
"""


def _parser_yml_commerce(site_name: str) -> str:
    domain = site_name.replace("_", ".")
    return f"""---
domain: {domain}
fields:
  crawl_timestamp:
  uniq_id:
  page_url:
  product_name:
  list_price:
  selling_price:
  discount_percentage:
  color:
  size:
  description:
  sku:
"""


def _parser_py_media(class_name: str) -> str:
    return f"""from sdf_module.url_parser import *

class {class_name}():

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        return current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        return str(inhash)

    @staticmethod
    def get_article_title(page_doc, inhash):
        # Generic og:title works for most sites — override with site-specific XPath if needed
        elems = page_doc.xpath("//meta[@property='og:title']/@content | //h1/text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_sub_title(page_doc, inhash):
        elems = page_doc.xpath("//meta[@property='og:description']/@content | //meta[@name='description']/@content")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_author_name(page_doc, inhash):
        elems = page_doc.xpath(
            "//meta[@property='article:author']/@content"
            " | //meta[@name='author']/@content"
            " | //a[@rel='author']/text()"
            " | //span[contains(@class,'author')]/text()"
        )
        return elems[0].strip() if elems else None

    @staticmethod
    def get_post_date(page_doc, inhash):
        elems = page_doc.xpath(
            "//meta[@property='article:published_time']/@content"
            " | //time/@datetime"
            " | //time/text()"
        )
        return elems[0].strip() if elems else None

    @staticmethod
    def get_article_content(page_doc, inhash):
        # TODO: narrow the XPath to this site's article body class for cleaner text
        elems = page_doc.xpath("//article//p//text() | //div[contains(@class,'article-body')]//p//text()")
        return " ".join(e.strip() for e in elems if e.strip()) or None

    @staticmethod
    def get_image_url(page_doc, inhash):
        elems = page_doc.xpath("//meta[@property='og:image']/@content")
        return elems[0] if elems else None
"""


def _parser_yml_media(site_name: str) -> str:
    domain = site_name.replace("_", ".")
    return f"""---
domain: {domain}
fields:
  crawl_timestamp:
  uniq_id:
  page_url:
  article_title:
  sub_title:
  author_name:
  post_date:
  article_content:
  image_url:
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scaffold new project/site modules.")
    parser.add_argument("project_name", help="Project name (e.g. commerce_crawl or media_crawl)")
    parser.add_argument("site_name", help="Site name (e.g. myntra_com)")
    args = parser.parse_args(argv)

    project_name = args.project_name
    site_name = args.site_name

    base_dir = Path.cwd()
    is_media = "media" in project_name.lower()

    class_name = ''.join(word.capitalize() for word in f"{site_name}_{project_name}".split('_'))

    # Discovery files
    create_project_structure(
        base_dir / 'url_discovery',
        project_name, site_name,
        _discovery_py(class_name, project_name),
        _discovery_yml(site_name),
    )

    # Parser files (project-type aware)
    if is_media:
        parser_py = _parser_py_media(class_name)
        parser_yml = _parser_yml_media(site_name)
    else:
        parser_py = _parser_py_commerce(class_name)
        parser_yml = _parser_yml_commerce(site_name)

    create_project_structure(
        base_dir / 'url_data_parser',
        project_name, site_name,
        parser_py,
        parser_yml,
    )


if __name__ == "__main__":
    main()
