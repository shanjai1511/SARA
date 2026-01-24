from .sdf_fetch import *

class UrlDiscovery:
    def __init__(self, base_dir, project_name, site_name):
        sdfFetch.print_info_message("info", f"Initializing UrlDiscovery for project: {project_name} and site: {site_name}")
        self.base_dir = base_dir
        self.output_dir = ""
        self.collector_dir = ""
        self.project_name = project_name
        self.site_name = site_name
        self.count = 0

    def write_url_in_txt(self, result_url):
        sdfFetch.print_info_message("info", f"Writing URLs to file for project: {self.project_name} and site: {self.site_name}")
        filepath = Path(self.output_dir) / f"{self.site_name}_{self.project_name}.txt"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'a') as file:
            for item in result_url:
                file.write(f"{item}\n")
        sdfFetch.print_info_message("success", f"URLs written to file successfully for project: {self.project_name} and site: {self.site_name}")

    def get_final_url(self, url, depth, current_depth_level, max_depth, module_instance):
        sdfFetch.print_info_message("info", f"Getting final URL for project: {self.project_name} and site: {self.site_name}")
        current_depth = depth[f"depth{current_depth_level}"]
        method_name = current_depth["method_name"]
        method_to_call = getattr(module_instance, method_name)
        if method_to_call is None:
            return
        
        for i in url:
            try:
                result_url = method_to_call(i, depth, current_depth_level)
            except Exception as e:
                sdfFetch.print_error_message("error", f"URL fetching failed with error: {e}")
                logging.exception("URL fetching failed")
                continue
            if current_depth_level == max_depth:
                self.write_url_in_txt(result_url)
                self.count += len(result_url)
            else:
                self.get_final_url(result_url, depth, current_depth_level + 1, max_depth, module_instance)

    def main_execution(self):
        sdfFetch.print_info_message("info", f"Starting main execution for project: {self.project_name} and site: {self.site_name}")
        try:
            yaml_file_path = Path(self.collector_dir) / f"{self.site_name}_{self.project_name}.yml"
            sdfFetch.print_info_message("info", f"Loading configuration file: {yaml_file_path}")
            with open(yaml_file_path, 'r') as file:
                depth = yaml.safe_load(file)

            module_path = Path(self.collector_dir) / f"{self.site_name}_{self.project_name}.py"

            class_name_in_site_script = f"{self.site_name}_{self.project_name}"
            class_name_in_site_script = ''.join([word.capitalize() for word in class_name_in_site_script.split('_')])
            try:
                spec = importlib.util.spec_from_file_location(class_name_in_site_script, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                SiteClass = getattr(module, class_name_in_site_script)
                site_instance = SiteClass()
            except Exception as e:
                sdfFetch.print_error_message("error", f"Error importing module from {module_path}: {e}")
                logging.exception("Module import failed")
                return

            seed_url = depth["depth0"]["seed_url"]

            self.get_final_url(seed_url, depth, 0, len(depth) - 1, site_instance)

        except Exception as e:
            sdfFetch.print_error_message("error", f"Unhandled error during execution: {e}")
            logging.exception("Unhandled error during execution")
            raise

    def main(self):
        sdfFetch.print_info_message("info", f"Starting script execution of url_discovery for project: {self.project_name} and site: {self.site_name}")
        self.output_dir = Path(self.base_dir) / f"scrape_output/discovery_output/{self.project_name}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.collector_dir = Path(self.base_dir) / f"url_discovery/{self.project_name}"
        filepath = self.output_dir / f"{self.site_name}_{self.project_name}.txt"
        
        with open(filepath, 'w') as file:
            file.write('')
        self.main_execution()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python url_fetcher.py <project_name> <site_name>")
        sys.exit(1)
    project_name = sys.argv[1]
    site_name = sys.argv[2]
    base_dir = "C:/Users/shanj/OneDrive/Desktop/SARA"
    url_discovery = UrlDiscovery(base_dir,project_name,site_name)
    url_discovery.main()