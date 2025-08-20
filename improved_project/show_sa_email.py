# show_sa_email.py
import os, json
from pathlib import Path

def load_env(p: Path):
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k,v=line.split("=",1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def main():
    load_env(Path.cwd()/".env")
    mode=None; info=None
    js=os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON","").strip()
    fp=os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE","").strip()
    if js:
        try: info=json.loads(js); mode="JSON (.env)"
        except Exception as e: print("❌ Bad GOOGLE_SHEETS_CREDENTIALS_JSON:", e)
    if info is None and fp:
        p=Path(fp);
        if not p.is_absolute(): p=(Path.cwd()/p).resolve()
        try: info=json.loads(p.read_text(encoding="utf-8")); mode=f"FILE ({p})"
        except Exception as e: print("❌ Bad GOOGLE_SHEETS_CREDENTIALS_FILE:", e)
    if not info:
        print("⚠️ Не найден сервис-аккаунт. Проверь .env и переменные."); return
    print("Using:", mode)
    print("Service account email:\n ", info.get("client_email"))
    print("project_id:", info.get("project_id"))

if __name__ == "__main__":
    main()
