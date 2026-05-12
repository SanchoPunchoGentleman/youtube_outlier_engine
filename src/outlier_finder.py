import os
import csv
import json
import subprocess
import re
import httpx
from youtubesearchpython import VideosSearch
from tqdm import tqdm
from niches import NICHES

# Load Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'config.json')
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)


from dotenv import load_dotenv

# Load the environment variables from the .env file
load_dotenv()

# Constants
API_KEY = os.getenv('YOUTUBE_API_KEY')

# Constants
OBSIDIAN_BASE_PATH = '/Users/Sanzhar/Documents/Obsidian vault/YouTube_brain'
CHANNELS_FOLDER = os.path.join(OBSIDIAN_BASE_PATH, '02_Channels')
NICHES_FOLDER = os.path.join(OBSIDIAN_BASE_PATH, '01_Niches')
PATTERNS_FOLDER = os.path.join(OBSIDIAN_BASE_PATH, '03_Patterns')
MASTER_NICHES_CSV = os.path.join(BASE_DIR, 'data', 'master_niches.csv')

def parse_count(count_str):
    if not count_str:
        return 0
    count_str = count_str.replace(',', '').upper()
    
    # Handle "Million", "Thousand", "Billion"
    multiplier = 1
    if 'MILLION' in count_str or 'M' in count_str:
        multiplier = 1000000
    elif 'THOUSAND' in count_str or 'K' in count_str:
        multiplier = 1000
    elif 'BILLION' in count_str or 'B' in count_str:
        multiplier = 1000000000
        
    match = re.search(r'([\d.]+)', count_str)
    if not match:
        return 0
    return int(float(match.group(1)) * multiplier)

def get_subs_count(channel_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=10.0) as client:
            r = client.get(channel_url)
            # Match formats like "1.23M subscribers"
            match = re.search(r'"subscriberCountText":\{"accessibility":\{"accessibilityData":\{"label":"(.*?)"\}', r.text)
            if match:
                return parse_count(match.group(1))
            match = re.search(r'"subscriberCountText":\{"simpleText":"(.*?)"\}', r.text)
            if match:
                return parse_count(match.group(1))
    except:
        pass
    return 0

def get_recent_titles(channel_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=10.0) as client:
            r = client.get(f"{channel_url}/videos")
            titles = re.findall(r'"videoRenderer":\{"videoId":".*?","title":\{"runs":\[\{"text":"(.*?)"\}\]', r.text)
            return titles[:5]
    except:
        return []

def check_exclusions(text):
    if not text:
        return False
    text = text.lower()
    for excl in config['exclusions']:
        if excl.lower() in text:
            return True
    return False

def extract_patterns(titles):
    if not titles: return ""
    titles_str = "\n".join(titles)
    prompt = (
        "Analyze these YouTube video titles for high-authority B2B structural patterns. "
        "Identify recurring psychological triggers or content frameworks. "
        "Return ONLY a comma-separated list of hashtags. Avoid hype language. "
        f"Titles:\n{titles_str}"
    )
    try:
        result = subprocess.run(['gemini', prompt], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception:
        return ""

def main():
    for folder in [CHANNELS_FOLDER, NICHES_FOLDER, PATTERNS_FOLDER, os.path.join(BASE_DIR, 'data')]:
        if not os.path.exists(folder):
            os.makedirs(folder)
            
    combined_niches = list(set(NICHES + config['manual_niches']))
    pattern_tracker = {}
    niche_batch_data = []
    processed_count = 0
    processed_channels = set()

    for niche in tqdm(combined_niches, desc="Scanning Niches (Hybrid)"):
        if check_exclusions(niche):
            continue
            
        try:
            videos_search = VideosSearch(niche, limit=15, region='US', language='en')
            results = videos_search.result()['result']
            
            niche_outliers = []
            for video in results:
                channel_id = video['channel']['id']
                channel_url = video['channel']['link']
                if channel_id in processed_channels:
                    continue
                processed_channels.add(channel_id)
                
                subs = get_subs_count(channel_url)
                if subs < 1000: continue
                
                view_count = parse_count(video.get('viewCount', {}).get('short', '0'))
                if view_count == 0: continue
                
                outlier_score = view_count / subs
                
                if outlier_score > config['threshold']:
                    titles = get_recent_titles(channel_url)
                    if not titles: titles = [video['title']]
                    
                    patterns = extract_patterns(titles)
                    outlier_data = {
                        'Niche': niche,
                        'Channel': video['channel']['name'],
                        'Subs': subs,
                        'AvgViews': int(view_count),
                        'OutlierScore': round(outlier_score, 2),
                        'Patterns': patterns,
                        'URL': channel_url
                    }
                    niche_outliers.append(outlier_data)
                    
                    # Pattern tracking
                    for p in patterns.split(','):
                        p = p.strip()
                        if p:
                            if p not in pattern_tracker: pattern_tracker[p] = set()
                            pattern_tracker[p].add(niche)
                            if len(pattern_tracker[p]) > 1:
                                # Update pattern master file
                                safe_pattern = p.replace('#', '').strip()
                                pf = os.path.join(PATTERNS_FOLDER, f"{safe_pattern}.md")
                                with open(pf, 'a' if os.path.exists(pf) else 'w') as f:
                                    if not os.path.exists(pf):
                                        f.write(f"# Pattern Master: {p}\n\n## Observations\n")
                                    f.write(f"- Seen in: {niche}\n")
                    
                    # Generate Obsidian Note
                    safe_title = "".join([c for c in video['channel']['name'] if c.isalnum() or c in (' ', '_')]).strip()
                    file_path = os.path.join(CHANNELS_FOLDER, f"{safe_title}.md")
                    with open(file_path, 'w') as f:
                        f.write(f"---\n")
                        f.write(f"type: channel_analysis\n")
                        f.write(f"niche: {niche}\n")
                        f.write(f"metric_subs: {subs}\n")
                        f.write(f"metric_anchor_views: {view_count}\n")
                        f.write(f"performance_ratio: {round(outlier_score, 2)}\n")
                        f.write(f"--- \n\n")
                        f.write(f"# Analysis: {video['channel']['name']}\n\n")
                        f.write(f"## Discovery Method\n")
                        f.write(f"Viral anchor: `{video['title']}`\n\n")
                        f.write(f"## Structural Patterns\n")
                        f.write(f"{patterns}\n\n")
                        f.write(f"## Recent Content\n")
                        for t in titles:
                            f.write(f"- {t}\n")

            if niche_outliers:
                avg_niche_score = sum(o['OutlierScore'] for o in niche_outliers) / len(niche_outliers)
                top_p = niche_outliers[0]['Patterns'].split(',')[0] if niche_outliers[0]['Patterns'] else "N/A"
                niche_batch_data.append({
                    'niche': niche,
                    'count': len(niche_outliers),
                    'avg_score': round(avg_niche_score, 2),
                    'top_pattern': top_p
                })
            
            # Save to CSV
            with open(MASTER_NICHES_CSV, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['Niche', 'Channel', 'Subs', 'AvgViews', 'OutlierScore', 'Patterns', 'URL'])
                if f.tell() == 0:
                    writer.writeheader()
                writer.writerows(niche_outliers)
            
            processed_count += 1
            if processed_count % 100 == 0:
                # Generate niche rollup
                rf = os.path.join(NICHES_FOLDER, f"Niche_Rollup_{processed_count // 100}.md")
                with open(rf, 'w') as f:
                    f.write(f"# Niche Rollup {processed_count // 100}\n\n| Niche | Count | Avg Score |\n|---|---|---|\n")
                    for d in niche_batch_data:
                        f.write(f"| {d['niche']} | {d['count']} | {d['avg_score']} |\n")
                niche_batch_data = []

        except Exception:
            continue

if __name__ == "__main__":
    main()
