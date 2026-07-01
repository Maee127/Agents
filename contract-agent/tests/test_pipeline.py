# tests/test_pipeline.py
import sys
import os
from pathlib import Path
from src import pipeline, analyzer


# Strategy 1: Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Strategy 2: Also try adding the current directory
sys.path.insert(0, str(Path.cwd()))

# Debug: Print what we're looking for
print(f"Project root: {project_root}")
print(f"Files in project root: {[f.name for f in project_root.iterdir() if f.is_file()]}")
print(f"Python path: {sys.path[:3]}")

# Strategy 3: Try direct import with full path
try:
    # Try normal import first
    from src.pipeline import analyze_contract
    from src.analyzer import summarize_report
    print("✅ Successfully imported using normal import")
except ModuleNotFoundError as e:
    print(f"⚠️ Normal import failed: {e}")
    
    # Try alternative: import using importlib
    try:
        import importlib.util
        
        # Import pipeline.py directly
        spec = importlib.util.spec_from_file_location(
            "pipeline", 
            project_root / "pipeline.py"
        )
        pipeline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pipeline)
        analyze_contract = pipeline.analyze_contract
        
        # Import analyzer.py directly
        spec = importlib.util.spec_from_file_location(
            "analyzer", 
            project_root / "analyzer.py"
        )
        analyzer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(analyzer)
        summarize_report = analyzer.summarize_report
        
        print("✅ Successfully imported using direct file import")
    except Exception as e2:
        print(f"❌ Direct import also failed: {e2}")
        print("\nPlease make sure the following files exist in your project root:")
        print("  - pipeline.py")
        print("  - analyzer.py")
        print("  - chunking.py")
        print("  - ingestion.py")
        sys.exit(1)

def test_contract_analysis():
    """Test the complete contract analysis pipeline."""
    
    # Load environment variables
    from dotenv import load_dotenv
    env_path = project_root / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        print(f"✅ Loaded .env from {env_path}")
    else:
        print(f"⚠️ .env file not found at {env_path}")
    
    # Check if API key is set
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("❌ GROQ_API_KEY not found in environment!")
        print("Please set it in your .env file")
        print(f"Looking for .env at: {env_path}")
        return
    
    print(f"✅ GROQ_API_KEY found (starts with: {api_key[:10]}...)")
    
    # Find a test contract file
    test_files = [
        project_root / "sample_contract.pdf",
        project_root / "test_contract.pdf",
        project_root / "contract.pdf",
        project_root / "sample.txt",
        project_root / "test.txt",
    ]
    
    contract_path = None
    for file_path in test_files:
        if file_path.exists():
            contract_path = file_path
            break
    
    if not contract_path:
        print(f"❌ No contract file found in {project_root}")
        print("Please create a test file named one of:")
        for f in test_files:
            print(f"  - {f.name}")
        return
    
    print(f"🔍 Analyzing contract: {contract_path}")
    print("-" * 50)
    
    try:
        # Run the analysis
        report = analyze_contract(str(contract_path))
        
        # Print summary
        print("\n" + "=" * 50)
        print(f"Analysis complete! Found {len(report.verdicts)} clauses")
        print(f"Failed clauses: {len(report.failed_chunk_indices)}")
        print(f"High risk: {report.high_risk_count}")
        print(f"Medium risk: {report.medium_risk_count}")
        
        # Show first few verdicts
        print("\nFirst 3 clauses analyzed:")
        for i, verdict in enumerate(report.verdicts[:3]):
            print(f"\nClause {verdict.clause_index}:")
            print(f"  Risk: {verdict.risk_level}")
            print(f"  Summary: {verdict.summary[:100]}...")
        
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_contract_analysis()
    