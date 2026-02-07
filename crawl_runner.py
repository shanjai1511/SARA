from sdf_module.files_import import *

if len(sys.argv) != 4:
    print("Usage: python run_pipeline.py <project> <site> <date>")
    sys.exit(1)

project = sys.argv[1]
site = sys.argv[2]
date = sys.argv[3]

commands = [
    ["python", "-m", "sdf_module.url_discovery", project, site, date],
    ["python", "-m", "sdf_module.url_retriever", project, site, date],
    ["python", "-m", "sdf_module.url_parser", project, site, date],
]

for cmd in commands:
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"Failed: {' '.join(cmd)}")
        sys.exit(result.returncode)

print("Pipeline completed successfully")
