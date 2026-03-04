from sdf_module.url_discovery import *

class VogueInMediaCrawl():

    def  get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            for i in range(1, 10):
                pagination_url.append(keyurl+"?page="+str(i))
        except Exception as e:
            print(f"Exception occurred: {e}")
        return pagination_url

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url)
            if dom["status_code"] != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom["page_doc"])
            if parsed_tree is None:
                raise Exception("Parsing failed")
            article_url = parsed_tree.xpath("//a[contains(@class,'SummaryItemHedLink')]/@href")
            for ur in article_url:
                product_url.append("https://www.vogue.in" + ur)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url
