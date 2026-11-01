#!/usr/bin/env python
"""Django's command-line entry point for local development and tests."""

import os
import sys


def main():
    """Run Django management commands such as runserver, migrate, and test."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "study_organiser.settings")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as error:
        raise ImportError(
            "Django is not installed. Install the project dependencies after approval."
        ) from error

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

