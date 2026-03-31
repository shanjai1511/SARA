from sdf_module.url_discovery import *

class AmazonInCommerceCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            dom = sdfFetch.get_page_content_hash(keyurl)
            if dom["status_code"] != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom["page_doc"])
            # look for pagination numbers
            pages = parsed_tree.xpath("//ul[contains(@class,'a-pagination')]//li[@class='a-normal']/a/text()")
            if not pages:
                return [keyurl]
            max_page = max(int(p) for p in pages if p.isdigit())
            for page in range(2, max_page + 1):
                pagination_url.append(f"{keyurl}&page={page}")
        except Exception as e:
            print(f"Exception occurred: {e}")
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            # remove page param if present
            base = url.split("&page=")[0]
            dom = sdfFetch.get_page_content_hash(base)
            if dom["status_code"] != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom["page_doc"])
            url_dom = parsed_tree.xpath("//div[@data-component-type='s-search-result']//a[@class='a-link-normal s-no-outline']/@href")
            rank = 1
            for prod in url_dom:
                category = {"rank": rank}
                rank += 1
                product_url.append(f"https://www.amazon.in{prod}|{category}")
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url[:10]
