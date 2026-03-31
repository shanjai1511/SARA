from sdf_module.url_discovery import *

class BusinessOfFashionMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            # Business of Fashion uses a simple "?page=N" query parameter
            for i in range(1, 11):
                connector = "&" if "?" in keyurl else "?"
                pagination_url.append(f"{keyurl}{connector}page={i}")
        except Exception as e:
            print(f"Exception occurred: {e}")
        # limit to first 10 to avoid runaway
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url)
            if dom["status_code"] != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom["page_doc"])
            if parsed_tree is None:
                raise Exception("Parsing failed")
            # article links are under /articles/ path
            article_links = parsed_tree.xpath("//a[contains(@href,'/articles/')]/@href")
            for ur in article_links:
                if ur.startswith("http"):
                    product_url.append(ur)
                else:
                    product_url.append("https://www.businessoffashion.com" + ur)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url[:10]
