from sdf_module.url_retriever import *

class VoxComMediaCrawl():
    def get_page_content(self, url, args_hash):
        page_content = sdfFetch.get_page_content_hash(url, args_hash)
        return page_content
