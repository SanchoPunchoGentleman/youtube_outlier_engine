import pandas as pd
import os

# Paths configuration
BASE_PATH = "/Users/Sanzhar/Documents/Obsidian vault/YouTube_brain/"
NICHE_DIR = os.path.join(BASE_PATH, "01_Niches/")
CHANNEL_DIR = os.path.join(BASE_PATH, "02_Channels/")
PATTERN_DIR = os.path.join(BASE_PATH, "03_Patterns/")
CSV_PATH = os.path.expanduser("~/youtube_outlier_engine/master_niches.csv")

def bridge_the_graph():
    # Load CSV and normalize column names to lowercase to prevent KeyErrors
    df = pd.read_csv(CSV_PATH)
    df.columns = [c.strip().lower() for c in df.columns]
    
    print(f"Detected columns: {list(df.columns)}")

    # 1. Generate Niche Aggregators
    if 'niche' in df.columns:
        for niche, group in df.groupby('niche'):
            filename = f"{str(niche).replace(':', '_').replace('/', '_')}.md"
            with open(os.path.join(NICHE_DIR, filename), 'w') as f:
                f.write(f"# Niche: {niche}\n\n")
                f.write(f"## Top Outliers (3x+ Score)\n")
                for _, row in group.iterrows():
                    # Attempt to find channel name column
                    c_name = row.get('channel_name', row.get('channel', 'Unknown Channel'))
                    f.write(f"- [[{c_name}]] (Score: {row.get('outlier_score', 'N/A')})\n")
    
    # 2. Extract Patterns
    if 'patterns' in df.columns:
        # Clean up the patterns string and split
        df['patterns'] = df['patterns'].fillna('')
        all_patterns = set()
        for p_list in df['patterns'].str.split(','):
            for p in p_list:
                if p.strip():
                    all_patterns.add(p.strip())

        for pattern in all_patterns:
            filename = f"{pattern.replace('#', '')}.md"
            with open(os.path.join(PATTERN_DIR, filename), 'w') as f:
                f.write(f"# Pattern: {pattern}\n\n")
                f.write("## Examples in the Wild\n")
                examples = df[df['patterns'].str.contains(pattern, na=False)]
                for _, row in examples.iterrows():
                    c_name = row.get('channel_name', row.get('channel', 'Unknown Channel'))
                    n_name = row.get('niche', 'Unknown Niche')
                    f.write(f"- [[{c_name}]] ([[ {n_name} ]])\n")

if __name__ == "__main__":
    bridge_the_graph()
    print("Graph Bridge Complete: 01_Niches and 03_Patterns populated.")
