import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OFFICES_PATH = ROOT / "workspace_office_locations.csv"
REGENERATED_OFFICES_PATH = ROOT / "workspace_office_locations_regenerated.csv"
BACKUP_OFFICES_PATH = ROOT / "workspace_office_locations.backup.csv"


def run_step(arguments):
    subprocess.run(arguments, cwd=ROOT, check=True)


def main():
    python_executable = sys.executable

    run_step([python_executable, "rebuild_workspace_offices.py"])

    if REGENERATED_OFFICES_PATH.exists():
        shutil.copy2(OFFICES_PATH, BACKUP_OFFICES_PATH)
        shutil.copy2(REGENERATED_OFFICES_PATH, OFFICES_PATH)

    run_step([python_executable, "find_gyms.py"])
    run_step([python_executable, "geocode_gyms.py"])
    run_step([python_executable, "init_db.py"])
    run_step([python_executable, "validate_gym_locations.py"])
    run_step([python_executable, "validate_workspace_offices.py"])


if __name__ == "__main__":
    main()