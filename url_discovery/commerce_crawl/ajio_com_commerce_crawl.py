from sdf_module.url_discovery import *
from urllib.parse import urljoin
import re

class AjioComCommerceCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            dom = sdfFetch.get_page_content_hash(keyurl)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))

            # Strategy:
            # 1) Follow explicit rel=next if present.
            # 2) Else try to infer a few pages from page= pattern.
            next_links = parsed_tree.xpath("//a[@rel='next']/@href")
            if next_links:
                next_url = urljoin(keyurl, next_links[0])
                pagination_url.append(next_url)
                # we only need a small set; engine caps later too
                return pagination_url[:10]

            # Infer pages if current URL has a page parameter
            m = re.search(r"([?&])page=(\d+)", keyurl)
            if m:
                sep = m.group(1)
                cur = int(m.group(2))
                for p in range(cur + 1, cur + 11):
                    pagination_url.append(re.sub(r"([?&])page=\d+", rf"\1page={p}", keyurl, count=1))
            else:
                # If no pagination hint, return the seed itself so discovery continues
                pagination_url = [keyurl]
        except Exception as e:
            print(f"Exception occurred: {e}")
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            url = url.replace("-page", "")
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))

            hrefs = parsed_tree.xpath("//a[@href]/@href")
            seen = set()
            rank = 1
            for href in hrefs:
                if not href:
                    continue
                full = urljoin(url, href)

                # Ajio product pages commonly contain "/p/" in the path.
                if "/p/" not in full:
                    continue
                if full in seen:
                    continue
                seen.add(full)

                category = {"rank": rank}
                rank += 1
                product_url.append(f"{full}|{category}")
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url[:10]
