#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "medprep.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django não está instalado. Ative .venv e execute "
            "'python -m pip install -r requirements.txt'."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

