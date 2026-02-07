from sdf_module.files_import import *

def print_status(status, path, project, site_name, info):
    status_message = {
        "status": status,
        "path": path,
        "project": project,
        "site_name": site_name,
        "info": info
    }
    print(json.dumps(status_message, indent=4))


def delete_project_structure(base_path, project_name, site_name):
    project_path = os.path.join(base_path, project_name)

    py_file = os.path.join(project_path, f"{site_name}_{project_name}.py")
    yml_file = os.path.join(project_path, f"{site_name}_{project_name}.yml")

    # delete python file
    if os.path.exists(py_file):
        os.remove(py_file)
        print_status("deleted", py_file, project_name, site_name, "Python file deleted")

    # delete yml file
    if os.path.exists(yml_file):
        os.remove(yml_file)
        print_status("deleted", yml_file, project_name, site_name, "YAML file deleted")

    # delete directory only if empty
    if os.path.exists(project_path) and not os.listdir(project_path):
        os.rmdir(project_path)
        print_status("deleted", project_path, project_name, site_name, "Directory deleted")


def main():
    if len(sys.argv) != 3:
        print("Usage: python cleanup_script.py <project_name> <site_name>")
        sys.exit(1)

    project_name = sys.argv[1]
    site_name = sys.argv[2]

    base_dir = os.getcwd()

    url_discovery_path = os.path.join(base_dir, "url_discovery")
    url_retriever_path = os.path.join(base_dir, "url_retriever")
    url_parser_path = os.path.join(base_dir, "url_data_parser")

    delete_project_structure(url_discovery_path, project_name, site_name)
    delete_project_structure(url_retriever_path, project_name, site_name)
    delete_project_structure(url_parser_path, project_name, site_name)


if __name__ == "__main__":
    main()
