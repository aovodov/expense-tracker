"""Запуск приложения из командной строки: python -m expense_tracker --help"""

import sys

from .cli import main

sys.exit(main())
