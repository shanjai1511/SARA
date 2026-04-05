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

def main(argv=None):
    parser = argparse.ArgumentParser(description="Scaffold new project/site modules.")
    parser.add_argument("project_name", help="Project name")
    parser.add_argument("site_name", help="Site name")
    args = parser.parse_args(argv)

    project_name = args.project_name
    site_name = args.site_name

    base_dir = Path.cwd()

    url_discovery_path = base_dir / 'url_discovery'
    url_retriever_path = base_dir / 'url_retriever'
    url_parser_path = base_dir / 'url_data_parser'
    class_name_in_site_script = f"{site_name}_{project_name}"
    class_name_in_site_script = ''.join([word.capitalize() for word in class_name_in_site_script.split('_')])
    # Content for each file type
    discovery_py_content = f"""from sdf_module.url_discovery import *

class {class_name_in_site_script}():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            pass
        except Exception as e:
            print(f"Exception occurred: {{e}}")
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            url = url.replace("-page", "")
        except Exception as e:
            print(f"Exception occurred: {{e}}")
        return product_url[:10]
    """
    discovery_yml_content = """depth0:
  seed_url: ["",""]
  method_name: get_pagination_url
depth1:
  method_name: get_product_url"""
    
    retriever_py_content = f"""from sdf_module.url_retriever import *

class {class_name_in_site_script}():
    def get_page_content(self, url, args_hash):
        page_content = sdfFetch.get_page_content_hash(url, args_hash)
        return page_content
"""
    retriever_yml_content = """request_type: curl
request_params:
  max_retries: 3
  timeout: 30
  # extended_header: {}
"""
    
    parser_py_content = f"""from sdf_module.url_parser import *

class {class_name_in_site_script}():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
            if isinstance(inhash, str) and "|" in inhash:
                url, category = inhash.split("|", 1)
        except Exception as e:
            print(f"Exception occurred: {{e}}")
        return final_data

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        # Format the date and time in the desired format
        formatted_datetime = current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]
        return formatted_datetime

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return

    @staticmethod
    def get_page_url(page_doc, inhash):
        return inhash.split("|")[0] if isinstance(inhash, str) and "|" in inhash else inhash

    @staticmethod
    def get_product_name(page_doc, inhash):
        return None  # Implement site-specific XPath extraction

    @staticmethod
    def get_list_price(page_doc, inhash):
        return None  # Implement site-specific XPath extraction
    
    @staticmethod
    def get_selling_price(page_doc, inhash):
        return None  # Implement site-specific XPath extraction

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        return None  # Implement site-specific XPath extraction
    
    @staticmethod
    def get_size(page_doc, inhash):
        return None  # Implement site-specific XPath extraction
    
    @staticmethod
    def get_color(page_doc, inhash):
        return None  # Implement site-specific XPath extraction
    
    @staticmethod
    def get_description(page_doc, inhash):
        return None  # Implement site-specific XPath extraction
    
    @staticmethod
    def get_sku(page_doc, inhash):
        return None  # Implement site-specific XPath extraction
"""
    parser_yml_content = f"""---
domain: {site_name.replace("_",".")}
fields:
  crawl_timestamp:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  uniq_id:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  page_url:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  product_name:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  list_price:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  selling_price:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  discount_percentage:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  color:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  size:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  description:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
  sku:
    desc_of_xpath:
    standard_nodeset_range: first
    standard_nodeset_join_char: "|"
    standard_post_processing_functions: "remove_line_and_spaces"
"""
    
    create_project_structure(url_discovery_path, project_name, site_name, discovery_py_content, discovery_yml_content)
    create_project_structure(url_retriever_path, project_name, site_name, retriever_py_content, retriever_yml_content)
    create_project_structure(url_parser_path, project_name, site_name, parser_py_content, parser_yml_content)

if __name__ == "__main__":
    main()
