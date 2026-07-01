# check_files.py
from pathlib import Path

project_root = Path(__file__).parent
print(f"📁 Checking: {project_root}")
print("\nFiles in project root:")
print("-" * 50)

for item in sorted(project_root.iterdir()):
    if item.is_file():
        print(f"  📄 {item.name}")
    elif item.is_dir():
        print(f"  📁 {item.name}/")

print("\n" + "=" * 50)
print("Checking for required files:")
required_files = ["pipeline.py", "analyzer.py", "chunking.py", "ingestion.py", ".env"]
for file in required_files:
    exists = (project_root / file).exists()
    status = "✅" if exists else "❌"
    print(f"  {status} {file}")
    