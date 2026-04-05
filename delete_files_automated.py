import argparse
from pathlib import Path
from sdf_module.files_import import *
from typing import Union


def print_status(status: str, path: Union[str, Path], project: str, site_name: str, info: str) -> None:
    status_message = {
        "status": status,
        "path": str(path),
        "project": project,
        "site_name": site_name,
        "info": info,
    }
    print(json.dumps(status_message, indent=4))


def delete_project_structure(base_path: Union[str, Path], project_name: str, site_name: str) -> None:
    project_path = Path(base_path) / project_name
    py_file = project_path / f"{site_name}_{project_name}.py"
    yml_file = project_path / f"{site_name}_{project_name}.yml"

    for fp, desc in ((py_file, "Python"), (yml_file, "YAML")):
        if fp.exists():
            fp.unlink()
            print_status("deleted", fp, project_name, site_name, f"{desc} file deleted")

    # remove directory if empty
    if project_path.exists() and not any(project_path.iterdir()):
        project_path.rmdir()
        print_status("deleted", project_path, project_name, site_name, "Directory deleted")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Delete generated project/site files.")
    parser.add_argument("project_name", help="Project name")
    parser.add_argument("site_name", help="Site name")
    args = parser.parse_args(argv)

    project_name = args.project_name
    site_name = args.site_name

    base_dir = Path.cwd()

    for sub in ("url_discovery", "url_retriever", "url_data_parser"):
        delete_project_structure(base_dir / sub, project_name, site_name)


if __name__ == "__main__":
    main()
