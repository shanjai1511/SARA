from .sdf_fetch import *

class UrlDelivery:
    def __init__(self, base_dir, project_name, site_name):
        sdfFetch.print_info_message("info", f"Initializing UrlDelivery for project: {project_name} and site: {site_name}")
        self.base_dir = base_dir
        self.output_dir = ""
        self.collector_dir = ""
        self.project_name = project_name
        self.site_name = site_name
        self.count = 0