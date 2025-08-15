
# Python System Tray App — CI build to `.exe`

This repo is set up so **GitHub Actions** builds a Windows `.exe` for you (no local Python needed).

## Quick use (no installs on your PC)
1. Create a new GitHub repo and upload this folder.
2. Go to **Actions** tab (GitHub will ask to enable workflows if first time).
3. Push (or re-run) the workflow. It builds on `windows-latest` and uploads an artifact.
4. After it finishes, open the workflow run → **Artifacts** → download `tray-app-exe`.
   - Inside you'll find `main.exe` that runs without Python installed.
5. (Optional) Replace `icon.ico` with your own icon and commit again.

## Local build (if you ever want to)
```bash
pip install -r requirements.txt
python make_icon.py
pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --noconsole --icon=icon.ico main.py
```

## Notes
- The tray has two menu items: **Open** (updates tooltip timestamp) and **Quit**.
- To test a custom icon without rebuilding: `python main.py path\to\your_icon.ico`.
- If your antivirus flags self-built binaries, code-signing the `.exe` helps for distribution.
