from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import yt_dlp
import os
import logging
import subprocess
import json

# ============================================================
#   YouTube Downloader - Railway Edition
#   Developed by @Hellfirez3643
#   No files stored on server — direct redirect to YT CDN
# ============================================================

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

COOKIES_FILE = 'cookies.txt'

class QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): logger.error(f"❌ {msg}")

def make_ydl_opts():
    opts = {
        'quiet': True,
        'no_warnings': True,
        'logger': QuietLogger(),
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        'extractor_retries': 2,
        'retries': 2,
        'extractor_args': {
            'youtube': {
                'player_client': ['web'],
                'po_token': [f'web+{get_po_token()}'],
            }
        },
    }
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    return opts

_po_token_cache = None

def get_po_token():
    """Generate PO token using bgutil script"""
    global _po_token_cache
    if _po_token_cache:
        return _po_token_cache
    try:
        result = subprocess.run(
            ['node', '/app/bgutil-ytdlp-pot-provider/server/build/generate-token.js'],
            capture_output=True, text=True, timeout=15
        )
        token = result.stdout.strip()
        if token:
            _po_token_cache = token
            logger.info("✅ PO token generated")
            return token
    except Exception as e:
        logger.warning(f"⚠️ PO token failed: {e}")
    return ''


def get_video_info(url):
    try:
        with yt_dlp.YoutubeDL(make_ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
            seen_qualities = {}

            for f in info.get('formats', []):
                direct_url = f.get('url')
                if not direct_url:
                    continue
                height = f.get('height')
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')

                if acodec != 'none' and vcodec == 'none':
                    key = 'audio'
                    if key not in seen_qualities or f.get('abr', 0) > seen_qualities[key].get('abr', 0):
                        seen_qualities[key] = {
                            'quality': 'audio', 'ext': f.get('ext', 'm4a'),
                            'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                            'direct_url': direct_url, 'abr': f.get('abr', 0), 'height': 0,
                        }
                elif vcodec != 'none' and height:
                    key = f'{height}p'
                    existing = seen_qualities.get(key)
                    has_audio = acodec != 'none'
                    existing_has_audio = existing and existing.get('has_audio', False)
                    if not existing or (has_audio and not existing_has_audio) or \
                       (has_audio == existing_has_audio and (f.get('filesize') or 0) > (existing.get('filesize') or 0)):
                        seen_qualities[key] = {
                            'quality': key, 'height': height, 'ext': f.get('ext', 'mp4'),
                            'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                            'direct_url': direct_url, 'has_audio': has_audio, 'fps': f.get('fps', 0),
                        }

            formats = sorted(seen_qualities.values(), key=lambda x: x.get('height', 0), reverse=True)
            return {
                'success': True,
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'formats': formats,
            }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def find_best_match(formats_dict, requested_quality):
    if requested_quality in formats_dict:
        return formats_dict[requested_quality]
    if requested_quality == 'audio':
        return None
    try:
        requested_height = int(requested_quality.replace('p', ''))
    except ValueError:
        return None
    video_qualities = sorted(
        [(int(k.replace('p', '')), v) for k, v in formats_dict.items() if k != 'audio'],
        reverse=True
    )
    for height, fmt in video_qualities:
        if height <= requested_height:
            return fmt
    return video_qualities[-1][1] if video_qualities else None


@app.route('/', methods=['GET'])
def home():
    return '''<html><head><title>YT Downloader by @Hellfirez3643</title>
    <style>body{font-family:Arial,sans-serif;padding:40px;background:#0f0f0f;color:#f1f1f1}
    h1{color:#ff0000}code{background:#272727;padding:4px 8px;border-radius:4px;color:#aaffaa}
    .label{color:#aaa;font-size:14px}footer{margin-top:40px;color:#555;font-size:13px}</style></head>
    <body><h1>🎬 YouTube Downloader</h1>
    <p class="label">No files stored on server. Direct redirect to YouTube CDN.</p>
    <h3>Get info</h3><code>/dl?url=VIDEO_URL</code>
    <h3>Download</h3><code>/dl?url=VIDEO_URL&q=720p</code>
    <p class="label">Quality options: 1080p, 720p, 480p, 360p, 240p, audio</p>
    <footer>Developed by @Hellfirez3643</footer></body></html>'''


@app.route('/dl', methods=['GET'])
def download_direct():
    url = request.args.get('url')
    quality = request.args.get('q')

    if not url:
        return jsonify({'error': 'Missing url parameter'}), 400

    info = get_video_info(url)
    if not info['success']:
        return jsonify(info), 400

    if not quality:
        duration = info['duration']
        return jsonify({
            'title': info['title'],
            'uploader': info['uploader'],
            'duration': f"{duration // 60}:{duration % 60:02d}",
            'views': info['view_count'],
            'thumbnail': info['thumbnail'],
            'available_qualities': [f['quality'] for f in info['formats']],
            'formats': info['formats'],
            'example': f"/dl?url={url}&q=720p",
        })

    formats_dict = {f['quality']: f for f in info['formats']}
    chosen = find_best_match(formats_dict, quality)

    if not chosen:
        return jsonify({'error': f'No format found for "{quality}"', 'available': list(formats_dict.keys())}), 400

    return redirect(chosen['direct_url'], code=302)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n{'='*60}\n  🎬 YouTube Downloader - Railway Edition\n  Developed by @Hellfirez3643\n{'='*60}")
    print(f"  🌐 Port: {port}\n  🍪 Cookies: {'✅' if os.path.exists(COOKIES_FILE) else '❌'}\n{'='*60}\n")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
