"""Initialize persistent storage, apply migrations, and start one API worker."""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    from job_finder.settings import AppSettings

    settings = AppSettings.from_env()
    settings.output_directory.mkdir(parents=True, exist_ok=True)
    settings.resumes_directory.mkdir(parents=True, exist_ok=True)
    settings.companies_path.parent.mkdir(parents=True, exist_ok=True)
    seed = Path(__file__).with_name('seed-companies.json')
    if not settings.companies_path.exists() and seed.exists():
        shutil.copyfile(seed, settings.companies_path)
    subprocess.run([sys.executable, '-m', 'job_finder', 'db-upgrade'], check=True)
    port = str(int(os.environ.get('PORT', '8000')))
    os.execv(sys.executable, [sys.executable, '-m', 'job_finder', 'serve', '--host', '0.0.0.0', '--port', port])


if __name__ == '__main__':
    main()
