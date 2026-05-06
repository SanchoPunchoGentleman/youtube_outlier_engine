import os
import csv
import json
import subprocess
from googleapiclient.discovery import build
from youtubesearchpython import ChannelsSearch
from tqdm import tqdm
from niches import NICHES

# Load Configuration
CONFIG_PATH = 'config.json'
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

# Constants
API_KEY = 'AIzaSyB4_KqvdsGHxguk-kV3zwLWfXZRRJ_OF9c'
OBSIDIAN_BASE_PATH = '/Users/Sanzhar/Documents/Obsidian vault/YouTube_brain'
CHANNELS_FOLDER = os.path.join(OBSIDIAN_BASE_PATH, '02_Channels')
NICHES_FOLDER = os.path.join(OBSIDIAN_BASE_PATH, '01_Niches')
PATTERNS_FOLDER = os.path.join(OBSIDIAN_BASE_PATH, '03_Patterns')
MASTER_NICHES_CSV = 'master_niches.csv'

youtube = build('youtube', 'v3', developerKey=API_KEY)

def check_exclusions(text):
    if not text:
        return False
    text = text.lower()
    for excl in config['exclusions']:
        if excl.lower() in text:
            return True
    return False

def get_channel_stats(channel_id):
    try:
        request = youtube.channels().list(
            part="statistics,snippet,contentDetails",
            id=channel_id
        )
        response = request.execute()
        if not response['items']:
            return None
        item = response['items'][0]
        
        # Ethical Guardrail check on snippet
        if check_exclusions(item['snippet']['title']) or check_exclusions(item['snippet']['description']):
            return None
            
        return {
            'title': item['snippet']['title'],
            'subs': int(item['statistics'].get('subscriberCount', 0)),
            'id': channel_id,
            'uploads_id': item['contentDetails']['relatedPlaylists']['uploads']
        }
    except Exception:
        return None

def get_last_5_videos(uploads_id):
    try:
        request = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_id,
            maxResults=5
        )
        response = request.execute()
        video_ids = [item['contentDetails']['videoId'] for item in response['items']]
        titles = [item['snippet']['title'] for item in response['items']]
        
        if not video_ids:
            return [], []
            
        # Ethical Guardrail check on titles
        for title in titles:
            if check_exclusions(title):
                return [], []
                
        request = youtube.videos().list(
            part="statistics",
            id=",".join(video_ids)
        )
        response = request.execute()
        views = [int(item['statistics'].get('viewCount', 0)) for item in response['items']]
        return views, titles
    except Exception:
        return [], []

def extract_patterns(titles):
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

def generate_niche_summary(niche_batch, batch_index):
    file_path = os.path.join(NICHES_FOLDER, f"Niche_Rollup_{batch_index}.md")
    with open(file_path, 'w') as f:
        f.write(f"# Niche Saturation Report: Batch {batch_index}\n\n")
        f.write("| Niche | Outliers Found | Avg Outlier Score | Top Pattern |\n")
        f.write("|-------|----------------|-------------------|-------------|\n")
        for data in niche_batch:
            f.write(f"| {data['niche']} | {data['count']} | {data['avg_score']} | {data['top_pattern']} |\n")

def update_pattern_master(pattern_name, context_niche):
    safe_pattern = pattern_name.replace('#', '').strip()
    file_path = os.path.join(PATTERNS_FOLDER, f"{safe_pattern}.md")
    
    exists = os.path.exists(file_path)
    mode = 'a' if exists else 'w'
    
    with open(file_path, mode) as f:
        if not exists:
            f.write(f"# Pattern Master Template: {pattern_name}\n\n")
            f.write("## Description\nHigh-performance structural pattern identified across multiple niches.\n\n")
            f.write("## Observations\n")
        f.write(f"- Identified in niche: {context_niche}\n")

def main():
    for folder in [CHANNELS_FOLDER, NICHES_FOLDER, PATTERNS_FOLDER]:
        if not os.path.exists(folder):
            os.makedirs(folder)
            
    combined_niches = list(set(NICHES + config['manual_niches']))
    pattern_tracker = {} # pattern -> set(niches)
    niche_batch_data = []
    
    processed_count = 0
    
    for niche in tqdm(combined_niches, desc="Scanning Niches (v2.0)"):
        if check_exclusions(niche):
            continue
            
        try:
            # Strictly use US/en as requested
            search = ChannelsSearch(niche, limit=10, region='US', language='en')
            results = search.result()['result']
            channel_ids = [res['id'] for res in results]
            
            niche_outliers = []
            for cid in channel_ids:
                stats = get_channel_stats(cid)
                if not stats or stats['subs'] < 1000:
                    continue
                    
                views, titles = get_last_5_videos(stats['uploads_id'])
                if not views:
                    continue
                    
                avg_views = sum(views) / len(views)
                outlier_score = avg_views / stats['subs']
                
                if outlier_score > config['threshold']:
                    patterns = extract_patterns(titles)
                    outlier_data = {
                        'Niche': niche,
                        'Channel': stats['title'],
                        'Subs': stats['subs'],
                        'AvgViews': int(avg_views),
                        'OutlierScore': round(outlier_score, 2),
                        'Patterns': patterns,
                        'URL': f"https://www.youtube.com/channel/{cid}"
                    }
                    niche_outliers.append(outlier_data)
                    
                    # Track patterns for Master Templates
                    for p in patterns.split(','):
                        p = p.strip()
                        if p:
                            if p not in pattern_tracker:
                                pattern_tracker[p] = set()
                            pattern_tracker[p].add(niche)
                            if len(pattern_tracker[p]) > 1: # Found in multiple niches
                                update_pattern_master(p, niche)
                    
                    # Generate Obsidian Note (B2B Style)
                    safe_title = "".join([c for c in stats['title'] if c.isalnum() or c in (' ', '_')]).strip()
                    file_path = os.path.join(CHANNELS_FOLDER, f"{safe_title}.md")
                    with open(file_path, 'w') as f:
                        f.write(f"---\n")
                        f.write(f"type: channel_analysis\n")
                        f.write(f"niche: {niche}\n")
                        f.write(f"metric_subs: {stats['subs']}\n")
                        f.write(f"metric_avg_views: {int(avg_views)}\n")
                        f.write(f"performance_ratio: {round(outlier_score, 2)}\n")
                        f.write(f"status: high_performance\n")
                        f.write(f"--- \n\n")
                        f.write(f"# Analysis: {stats['title']}\n\n")
                        f.write(f"## Data Points\n")
                        f.write(f"- **Authority Level**: {'High' if stats['subs'] > 50000 else 'Emerging'}\n")
                        f.write(f"- **Content Velocity**: Last 5 videos analysis\n")
                        f.write(f"- **URL**: {outlier_data['URL']}\n\n")
                        f.write(f"## Structural Patterns\n")
                        f.write(f"{patterns}\n\n")
                        f.write(f"## Recent Content Output\n")
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
            file_exists = os.path.isfile(MASTER_NICHES_CSV)
            with open(MASTER_NICHES_CSV, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['Niche', 'Channel', 'Subs', 'AvgViews', 'OutlierScore', 'Patterns', 'URL'])
                if not file_exists:
                    writer.writeheader()
                writer.writerows(niche_outliers[:10])
            
            processed_count += 1
            if processed_count % 100 == 0:
                generate_niche_summary(niche_batch_data, processed_count // 100)
                niche_batch_data = []

        except Exception as e:
            if "quotaExceeded" in str(e):
                break
            continue
            
    # Final rollup if any left
    if niche_batch_data:
        generate_niche_summary(niche_batch_data, (processed_count // 100) + 1)

if __name__ == "__main__":
    main()
