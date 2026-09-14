import os
import pandas as pd
import glob
import sys

def inspect_csvs(data_dir):
    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    csv_files.sort()
    
    if not csv_files:
        print(f"No CSV files found in {data_dir}")
        return

    for file in csv_files:
        filename = os.path.basename(file)
        try:
            df = pd.read_csv(file)
            print(f"={'='*80}")
            print(f"FILE: {filename}")
            print(f"ROWS: {len(df)}")
            print(f"COLUMNS ({len(df.columns)}): {', '.join(df.columns)}")
            
            print("\nDATA TYPES & MISSING VALUES:")
            for col in df.columns:
                dtype = df[col].dtype
                missing = df[col].isnull().sum()
                num_unique = df[col].nunique()
                unique_pct = (num_unique / len(df)) * 100 if len(df) > 0 else 0
                
                is_unique = " (Unique Identifier? Yes)" if num_unique == len(df) and len(df) > 0 else ""
                print(f"  - {col}: {dtype}, Missing: {missing}, Unique: {num_unique} ({unique_pct:.1f}%){is_unique}")
                
            print("\nSAMPLE RECORDS:")
            print(df.head(2).to_string(index=False))
            print(f"={'='*80}\n")
            
        except Exception as e:
            print(f"Error reading {filename}: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        data_dir = sys.argv[1]
    else:
        # Default to the known data directory relative to the script or project root
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.abspath(os.path.join(script_dir, "../../data"))
        
    inspect_csvs(data_dir)
