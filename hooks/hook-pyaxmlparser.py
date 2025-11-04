# hooks/hook-pyaxmlparser.py
from PyInstaller.utils.hooks import collect_data_files

# Collect all data files (like public.xml) from the pyaxmlparser package
datas = collect_data_files('pyaxmlparser')
