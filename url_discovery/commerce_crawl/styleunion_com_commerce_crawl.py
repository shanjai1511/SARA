from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)

class StyleunionComCommerceCrawl():

    def  get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            url = keyurl
            dom = sdfFetch.get_page_content_hash(url)
            if dom["status_code"] != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom["page_doc"])
            if parsed_tree is None:
                raise Exception("Parsing failed")
            product_count = parsed_tree.xpath("//script[contains(.,'productCount')]")
            product_count = product_count[0].text
            product_count = product_count.split("productCount: '")[-1].split("'")[0]
            product_count = math.ceil(int(product_count)/12)
            if product_count > 1:
                for page in range(1,product_count):
                    pagination_url.append(f"{url}?page={page}")
            else:
                return [keyurl]
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return pagination_url

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            url = url.replace("-page","")
            dom = sdfFetch.get_page_content_hash(url)
            if dom["status_code"] != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom["page_doc"])
            if parsed_tree is None:
                raise Exception("Parsing failed")
            url_dom = parsed_tree.xpath("//a[contains(@id,'card-product-')]/@href")
            rank = 1
            category = {}
            for prod in url_dom:
                category["rank"] = rank
                rank = rank + 1
                product_url.append(f"https://styleunion.in{prod}|{category}")
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
