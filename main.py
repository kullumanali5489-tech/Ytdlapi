from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import yt_dlp
import os
import logging

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

def base_ydl_opts():
    opts = {
        'quiet': True,
        'no_warnings': True,
        'logger': QuietLogger(),
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        # tv_embedded + ios bypass PO token requirement on datacenter IPs
        'extractor_retries': 3,
        'retries': 3,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded', 'ios', 'web'],
            }
        },
    }
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    return opts


def get_video_info(url):
    """Get video info — collects ALL formats including combined video+audio"""
    ydl_opts = base_ydl_opts()

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            seen_qualities = {}

            for f in info.get('formats', []):
                direct_url = f.get('url')
                if not direct_url:
                    continue

                height = f.get('height')
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')

                # Audio only
                if acodec != 'none' and vcodec == 'none':
                    key = 'audio'
                    if key not in seen_qualities or f.get('abr', 0) > seen_qualities[key].get('abr', 0):
                        seen_qualities[key] = {
                            'quality': 'audio',
                            'ext': f.get('ext', 'm4a'),
                            'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                            'direct_url': direct_url,
                            'abr': f.get('abr', 0),
                            'height': 0,
                        }

                # Video (with or without audio — tv_embedded gives combined)
                elif vcodec != 'none' and height:
                    key = f'{height}p'
                    existing = seen_qualities.get(key)
                    # Prefer formats that have audio included (combined)
                    has_audio = acodec != 'none'
                    existing_has_audio = existing and existing.get('has_audio', False)

                    if not existing or (has_audio and not existing_has_audio) or \
                       (has_audio == existing_has_audio and
                        (f.get('filesize') or 0) > (existing.get('filesize') or 0)):
                        seen_qualities[key] = {
                            'quality': key,
                            'height': height,
                            'ext': f.get('ext', 'mp4'),
                            'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                            'direct_url': direct_url,
                            'has_audio': has_audio,
                            'fps': f.get('fps', 0),
                        }

            formats = list(seen_qualities.values())
            formats.sort(key=lambda x: x.get('height', 0), reverse=True)

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
    """Find exact match or closest lower quality"""
    if requested_quality in formats_dict:
        return formats_dict[requested_quality]

    # Try to find closest available quality
    if requested_quality == 'audio':
        return None

    try:
        requested_height = int(requested_quality.replace('p', ''))
    except ValueError:
        return None

    # Get all video qualities sorted descending
    video_qualities = sorted(
        [(int(k.replace('p', '')), v) for k, v in formats_dict.items() if k != 'audio'],
        reverse=True
    )

    # Find closest quality at or below requested
    for height, fmt in video_qualities:
        if height <= requested_height:
            return fmt

    # If nothing lower, return lowest available
    if video_qualities:
        return video_qualities[-1][1]

    return None


@app.route('/', methods=['GET'])
def home():
    return '''
    <html>
    <head>
        <title>YT Downloader by @Hellfirez3643</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 40px; background: #0f0f0f; color: #f1f1f1; }
            h1 { color: #ff0000; }
            code { background: #272727; padding: 4px 8px; border-radius: 4px; color: #aaffaa; }
            .section { margin-bottom: 24px; }
            .label { color: #aaa; font-size: 14px; }
            footer { margin-top: 40px; color: #555; font-size: 13px; }
        </style>
    </head>
    <body>
        <h1>🎬 YouTube Downloader</h1>
        <p class="label">No files stored on server. Direct redirect to YouTube CDN.</p>

        <div class="section">
            <h3>Step 1 — Get available qualities</h3>
            <code>/dl?url=VIDEO_URL</code>
        </div>

        <div class="section">
            <h3>Step 2 — Download</h3>
            <code>/dl?url=VIDEO_URL&q=QUALITY</code>
            <p class="label">Redirects directly to YouTube CDN. Nothing stored here.</p>
        </div>

        <div class="section">
            <h3>Quality options</h3>
            <code>1080p</code> &nbsp;<code>720p</code> &nbsp;<code>480p</code> &nbsp;
            <code>360p</code> &nbsp;<code>240p</code> &nbsp;<code>audio</code>
            <p class="label">If exact quality unavailable, closest lower quality is used automatically.</p>
        </div>

        <div class="section">
            <h3>Examples</h3>
            <p>Get info: <code>/dl?url=https://youtube.com/watch?v=xyz</code></p>
            <p>Download 720p: <code>/dl?url=https://youtube.com/watch?v=xyz&q=720p</code></p>
            <p>Download audio: <code>/dl?url=https://youtube.com/watch?v=xyz&q=audio</code></p>
        </div>

        <footer>Developed by @Hellfirez3643</footer>
    </body>
    </html>
    '''


@app.route('/dl', methods=['GET'])
def download_direct():
    url = request.args.get('url')
    quality = request.args.get('q')

    if not url:
        return jsonify({'error': 'Missing url parameter. Usage: /dl?url=VIDEO_URL'}), 400

    logger.info(f"{'📋 Info' if not quality else f'🔗 Redirect [{quality}]'}: {url}")

    info = get_video_info(url)
    if not info['success']:
        return jsonify(info), 400

    # No quality — return JSON info
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
            'usage': f"/dl?url={url}&q=QUALITY",
            'example': f"/dl?url={url}&q=720p",
        })

    # Quality specified — find best match and redirect
    formats_dict = {f['quality']: f for f in info['formats']}
    chosen = find_best_match(formats_dict, quality)

    if not chosen:
        return jsonify({
            'error': f'No suitable format found for "{quality}"',
            'available': list(formats_dict.keys())
        }), 400

    actual_quality = chosen['quality']
    if actual_quality != quality:
        logger.info(f"⚠️  Requested {quality}, serving closest: {actual_quality}")

    logger.info(f"✅ Redirecting → {info['title']} [{actual_quality}]")
    return redirect(chosen['direct_url'], code=302)


@app.route('/info', methods=['GET'])
def info_only():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing url parameter'}), 400
    request.args = request.args.copy()
    return download_direct()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "=" * 60)
    print("  🎬 YouTube Downloader - Railway Edition")
    print("  Developed by @Hellfirez3643")
    print("=" * 60)
    print(f"  🌐 Port: {port}")
    print(f"  🍪 Cookies: {'✅ Found' if os.path.exists(COOKIES_FILE) else '❌ Not found'}")
    print("=" * 60 + "\n")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
