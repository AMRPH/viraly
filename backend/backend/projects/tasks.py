import logging
import os
import uuid
import time
import glob
import gc
import re
import tempfile
from pathlib import Path

from django.conf import settings

import torch
import cv2
import pickle
import numpy as np
from tqdm import tqdm
from celery import shared_task
from yt_dlp import YoutubeDL
from scipy.ndimage import gaussian_filter1d
from natasha import Segmenter, Doc
from moviepy import VideoFileClip
from scipy.interpolate import CubicSpline
from PIL import ImageFont

from projects.models import Project
from clips.models import Clip
from overlays.models import ImageOverlay, TextOverlay, SubtitlesOverlay
import backend.models_loader as models_loader
from decord import VideoReader
from decord._ffi.base import DECORDError
import decord


import subprocess
import cupy as cp
from cupyx.scipy.ndimage import zoom, gaussian_filter


logger = logging.getLogger(__name__)

WINDOW_CONTEXT = getattr(settings, 'INTERESTING_WINDOW_CONTEXT', 3)
MIN_DURATION = getattr(settings, 'MIN_CLIP_DURATION', 8.0)
MAX_DURATION = getattr(settings, 'MAX_CLIP_DURATION', 120.0)
FILES_DIR = getattr(settings, 'MEDIA_ROOT', 'files')
MAX_VIDEO_DURATION = getattr(settings, 'MAX_VIDEO_DURATION', 10800)



def download_video(project: Project):
    if project.video_url:
        same_project = Project.objects.filter(
            video_url=project.video_url,
            video_filename__isnull=False,
            status='done').first()
        
        if same_project:
            if os.path.exists(f"{FILES_DIR}/sources/{same_project.video_filename}"):
                return same_project.video_filename

        
        video_id = uuid.uuid4()
        output_path = f"{FILES_DIR}/sources/{video_id}.%(ext)s"

        ydl_opts = {
            "proxy": "socks5h://127.0.0.1:10808",
            "ffmpeg_location": "/usr/bin/ffmpeg",
            "format": (
                "bestvideo[ext=mp4][vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/"
                "bestvideo[vcodec=h264][height<=1080]+bestaudio[ext=m4a]/"
                "bestvideo[vcodec~='^((?!(av01|vp9)).)*$'][height<=1080]+bestaudio/"
                "best[ext=mp4][height<=1080]/"
                "best[height<=1080]"
            ),
            "merge_output_format": "mp4",
            "postprocessors": [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}
            ],

            "outtmpl": output_path,
            "socket_timeout": 30,
            "retries": 5,
            "fragment_retries": 10,
            "nopart": True,
            "continuedl": True,
            "noplaylist": True, 
        }
        YoutubeDL(ydl_opts).download([project.video_url])


        downloaded_files = glob.glob(f"{FILES_DIR}/sources/{video_id}.*")
        if not downloaded_files:
            raise RuntimeError("yt-dlp did not produce any output file")

        output_path = downloaded_files[0]
        if os.path.getsize(output_path) < 1_000_000:
            os.remove(output_path)
            raise RuntimeError("Downloaded file too small (corrupted?)")

        logger.info('Video downloaded')
        return os.path.basename(output_path)
        
    elif project.video_filename:
        logger.info('Video has already been downloaded')
        return project.video_filename
    
    else:
        raise ValueError("No video URL or filename in project")

def transcribe_video(project: Project):
    segments, _ = models_loader.model_whisper.transcribe(
        f'{FILES_DIR}/sources/{project.video_filename}', 
        batch_size=32, 
        word_timestamps=True
    )

    words = [
        {
            "start": word.start,
            "end": word.end,
            "word": word.word
        }
        for segment in segments
        for word in segment.words
    ]
    
    return words


def split_by_sentences(text, segmenter):
    doc = Doc(text)
    doc.segment(segmenter)
    return [x.text for x in doc.sents]

def words_to_sentences(words):
    segmenter = Segmenter()
    sentences = []
    i = 0
    while i < len(words):
        stop = False
        j = i + 1
        while not stop and j <= len(words):
            clip = words[i:j]
            clip_text = ''.join([x['word'] for x in clip])
            clip_sentences = split_by_sentences(clip_text, segmenter)
            if len(clip_sentences) > 1:
                sentences.append({
                    "start": float(clip[0]['start']),
                    "end": float(clip[-1]['start']),
                    "text": clip_sentences[0]
                })
                i = j - 1
                stop = True
            else:
                j += 1

        if not stop and i < len(words):
            clip = words[i:]
            clip_text = ''.join([x['word'] for x in clip])
            sentences.append({
                "start": float(clip[0]['start']),
                "end": float(clip[-1]['end']),
                "text": clip_text
            })
            break
    return sentences


def predict_interesting(sentences):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    texts = [s['text'] for s in sentences]
    x = [
        ' '.join(texts[max(0, i - WINDOW_CONTEXT):min(len(texts), i + WINDOW_CONTEXT + 1)])
        for i in range(len(texts))
    ]
    
    inputs = models_loader.tokenizer_interesting(
        x, return_tensors="pt", truncation=True, padding=True
    ).to(device)

    with torch.no_grad():
        logits = models_loader.model_interesting(**inputs).logits

    y_pred = torch.sigmoid(logits).squeeze().cpu().numpy()
    y_pred = gaussian_filter1d(y_pred, sigma=2)
    y_pred = (y_pred >= 0.5).astype(int)

    logger.info(f"Predictions: {y_pred.tolist()}")

    for sentence, tag in zip(sentences, y_pred):
        sentence['tag'] = int(tag)

    return sentences

def create_clips(segments):
    clips = []
    current_group = []
    for s in segments:
        if s['tag'] == 1:
            current_group.append(s)
        else:
            if current_group:
                start = min(x['start'] for x in current_group)
                end = max(x['end'] for x in current_group)

                if end - start >= MIN_DURATION and end - start <= MAX_DURATION:
                    clips.append({
                        'start': start,
                        'end': end,
                        'text': ' '.join(x['text'] for x in current_group).strip()
                    })
                current_group = []

    if current_group:
        start = min(x['start'] for x in current_group)
        end = max(x['end'] for x in current_group)
        if end - start >= MIN_DURATION and end - start <= MAX_DURATION:
            clips.append({
                'start': start,
                'end': end,
                'text': ' '.join(x['text'] for x in current_group).strip()
            })
    
    return clips


def tracking_video(
    project: Project,
    track_per_second: int,
    smoothing_factor: float,
    batch_size: int,
):
    # vr = VideoReader(f'{FILES_DIR}/sources/{project.video_filename}', ctx=decord.gpu(0))
    vr = VideoReader(f'{FILES_DIR}/sources/{project.video_filename}')
    fps = vr.get_avg_fps()
    total_frames = len(vr)
    width, height = vr[0].shape[1], vr[0].shape[0]

    track_every_n = max(int(fps // track_per_second), 1)

    logger.info(f"Tracking: Video loaded (fps={fps}, width={width}, track_every_n={track_every_n}, frames={total_frames})")


    indices = list(range(0, total_frames, track_every_n))


    centers = {}
    for i in tqdm(range(0, len(indices), batch_size)):
        batch_indices = indices[i:i+batch_size]

        try:
            batch = vr.get_batch(batch_indices).asnumpy()
        except DECORDError as e:
            logger.warning(f"Decord failed at batch {i} ({batch_indices}): {e}")
            frames = []
            for idx in batch_indices:
                try:
                    frames.append(vr[idx].asnumpy())
                except DECORDError as e2:
                    logger.error(f"Frame {idx} failed: {e2}")
                    frames.append(np.zeros((height, width, 3), dtype=np.uint8))
            batch = np.stack(frames, axis=0)

        batch = [cv2.cvtColor(f, cv2.COLOR_RGB2BGR) for f in batch]

        with torch.no_grad():
            results = models_loader.model_tracking(batch, verbose=False)

        for j, result in enumerate(results):
            idx = indices[i + j]
            if result.boxes and result.boxes.xyxy.numel() > 0:
                x1, y1, x2, y2 = result.boxes.xyxy[0].tolist()
                cx = int((x1 + x2) / 2)
            else:
                cx = width // 2
            centers[idx] = cx
        
    del batch, results
    torch.cuda.empty_cache()
    gc.collect()
            
    
    centers_x = np.zeros(total_frames, dtype=np.float32)
    for idx, cx in centers.items():
        centers_x[idx] = cx

    known_indices = np.array(sorted(centers.keys()))
    known_values = np.array([centers[i] for i in known_indices])

    all_indices = np.arange(total_frames)
    # centers_x = np.interp(all_indices, known_indices, known_values, left=known_values[0], right=known_values[-1])
    cs = CubicSpline(known_indices, known_values, bc_type='clamped')
    centers_x = cs(all_indices)
    centers_x[:known_indices[0]] = known_values[0]
    centers_x[known_indices[-1]+1:] = known_values[-1]


    smoothed = np.empty_like(centers_x)
    smoothed[0] = centers_x[0]
    alpha = smoothing_factor
    for i in range(1, len(centers_x)):
        smoothed[i] = smoothed[i-1] + alpha * (centers_x[i] - smoothed[i-1])

    del vr, centers_x, known_indices, known_values, all_indices, cs
    gc.collect()

    return smoothed.astype(int).tolist()


def save_subtitles_as_ass(subtitles, output_path):
    def format_time(seconds):
        hrs, rem = divmod(seconds, 3600)
        mins, secs = divmod(rem, 60)
        cs = int((secs % 1) * 100)  # centiseconds
        secs = int(secs)
        return f"{int(hrs):01}:{int(mins):02}:{secs:02}.{cs:02}"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("[Script Info]\n")
        f.write("Title: Subtitle Export\n")
        f.write("ScriptType: v4.00+\n")
        f.write("Collisions: Normal\n")
        f.write("PlayResX: 1920\n")
        f.write("PlayResY: 1080\n")
        f.write("Timer: 100.0000\n\n")

        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
                "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
                "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write("Style: Default,OpenSans-Semibold,48,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
                "0,0,0,0,100,100,0,0,1,2,0,2,10,10,40,1\n\n")

        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        
        for sub in subtitles:
            start = format_time(sub['start'])
            end = format_time(sub['end'])
            text = sub['word'].replace('\n', ' ')  # Убрать лишние переносы
            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")



@shared_task
def process_project(project_id):
    logger.info(f'Start processing project_id={project_id}')
    try:
        project = Project.objects.get(id=project_id)
        project.status = 'processing'
        project.save()

        start = time.perf_counter()
        project.video_filename = download_video(project)
        end = time.perf_counter()
        logger.info(f'Download video ({project.video_filename}):{end - start:.3f}s')


        clip = VideoFileClip(f'{FILES_DIR}/sources/{project.video_filename}')
        project.duration = clip.duration
        clip.close()

        video_uuid = project.video_filename.split('.')[0]

        need_processing = not (
            Path(f'{FILES_DIR}/sources/subtitles_{video_uuid}.ass').exists() and
            Path(f'{FILES_DIR}/sources/interesting_{video_uuid}.pkl').exists() and
            Path(f'{FILES_DIR}/sources/tracking_{video_uuid}.pkl').exists()
        )

        if need_processing:

            words = transcribe_video(project)

            sentences = words_to_sentences(words)

            predicted_segments = predict_interesting(sentences)

            clips = create_clips(predicted_segments)

            start = time.perf_counter()
            tracking = tracking_video(project=project, track_per_second=2, smoothing_factor=0.2, batch_size=16)
            end = time.perf_counter()
            logger.info(f'Tracking video time: {end - start:.3f}s')


            with open(f'{FILES_DIR}/sources/tracking_{video_uuid}.pkl', 'wb') as f:
                pickle.dump(tracking, f)
            with open(f'{FILES_DIR}/sources/interesting_{video_uuid}.pkl', 'wb') as f:
                pickle.dump(clips, f)
            save_subtitles_as_ass(words, f'{FILES_DIR}/sources/subtitles_{video_uuid}.ass')

            project.tracking_filename = f'tracking_{video_uuid}.pkl'
            project.subtitles_filename = f'subtitles_{video_uuid}.ass'
            project.interesting_filename = f'interesting_{video_uuid}.pkl'
            project.save()

        else:
            with open(f'{FILES_DIR}/sources/interesting_{video_uuid}.pkl', 'rb') as f:
                clips = pickle.load(f)
            with open(f'{FILES_DIR}/sources/tracking_{video_uuid}.pkl', 'rb') as f:
                tracking = pickle.load(f)

            project.tracking_filename = f'tracking_{video_uuid}.pkl'
            project.subtitles_filename = f'subtitles_{video_uuid}.ass'
            project.interesting_filename = f'interesting_{video_uuid}.pkl'
            project.save()

        logger.info(f'Count clips: {len(clips)}')

        if clips:
            for clip_data in clips:
                
                clip = Clip.objects.create(
                    user=project.user,
                    project=project,
                    start=clip_data['start'],
                    end=clip_data['end'],
                    crop='9:16',
                )
                clip.save()
                pre_render_clip.apply_async(args=[clip.id], priority=0)

        project.status = 'done'
        project.save()

    except Exception as e:
        logger.error(f"Error processing project {project_id}: {e}")
        project.status = 'error'
        project.save()
        raise






def cp_resize(img, new_size):
    scale_y = new_size[0] / img.shape[0]
    scale_x = new_size[1] / img.shape[1]
    if img.dtype != cp.float32:
        img = img.astype(cp.float32)
    resized = zoom(img, (scale_y, scale_x, 1), order=1)
    return cp.clip(resized, 0, 255).astype(cp.uint8)


def gaussian_blur_gpu(img, sigma):
    if img.dtype != cp.float32:
        img = img.astype(cp.float32)
    
    blurred = cp.empty_like(img)
    for c in range(3):
        blurred[:, :, c] = gaussian_filter(img[:, :, c], sigma=sigma)
    
    return cp.clip(blurred, 0, 255).astype(cp.uint8)


def process_1_1_gpu(frame_gpu, params, frame_idx, centers_x):
    if params["resize_needed"]:
        frame_gpu = cp_resize(frame_gpu, (params["resize_h"], params["resize_w"]))
    h, w = frame_gpu.shape[:2]
    cx = int(centers_x[frame_idx])
    s = params["square_size"]
    x1 = max(0, min(cx - s // 2, w - s))
    y1 = max(0, min((h - s) // 2, h - s))

    blur_frame = gaussian_blur_gpu(frame_gpu, 20)
    blur_resized = cp_resize(blur_frame, (1920, 1080))

    crop = frame_gpu[y1:y1 + s, x1:x1 + s]
    square_resized = cp_resize(crop, (1080, 1080))

    final = cp.empty((1920, 1080, 3), dtype=cp.uint8)
    final[:] = blur_resized
    top = (1920 - 1080) // 2
    final[top:top + 1080, :] = square_resized
    return final


def process_9_16_gpu(frame_gpu, params, frame_idx, centers_x):
    h, w = frame_gpu.shape[:2]
    cx = int(centers_x[frame_idx])
    crop_w = params["crop_w_px"]
    crop_h = params["crop_h_px"]
    y1 = params["y1"]
    x1 = max(0, min(cx - crop_w // 2, w - crop_w))
    cropped = frame_gpu[y1:y1 + crop_h, x1:x1 + crop_w]
    return cp_resize(cropped, (1920, 1080))


def process_batch_gpu(frames_batch, crop_params, frame_offset, crop, centers_x):
    gpu_frames = cp.asarray(frames_batch)
    result = []
    for i in range(gpu_frames.shape[0]):
        frame_gpu = gpu_frames[i]
        idx = frame_offset + i
        if crop == "9:16":
            out = process_9_16_gpu(frame_gpu, crop_params, idx, centers_x)
        else:
            out = process_1_1_gpu(frame_gpu, crop_params, idx, centers_x)
        result.append(cp.asnumpy(out))
        del out
    del gpu_frames
    cp.get_default_memory_pool().free_all_blocks()
    return result


def precompute_crop_params(width, height, crop):
    if crop == "9:16":
        crop_w, crop_h = 9, 16
        if height * crop_w / crop_h <= width:
            crop_h_px = height
            crop_w_px = int(height * crop_w / crop_h)
        else:
            crop_w_px = width
            crop_h_px = int(width * crop_h / crop_w)
        return {
            "crop_w_px": crop_w_px,
            "crop_h_px": crop_h_px,
            "y1": (height - crop_h_px) // 2
        }
    elif crop == "1:1":
        square_size = 1080
        return {
            "square_size": square_size,
            "resize_needed": width < square_size or height < square_size,
            "resize_w": max(width, square_size),
            "resize_h": max(height, square_size)
        }
    return {}


def pre_render(input_path: str, centers_x: list[int], output_path: str,
               start: float, end: float, crop: str, batch_size: int):
    decord.bridge.set_bridge("native")
    vr = decord.VideoReader(input_path)
    fps = vr.get_avg_fps()
    width, height = vr[0].shape[1], vr[0].shape[0]
    start_frame = int(start * fps)
    end_frame = int(end * fps)

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-loglevel", "debug",
        "-hwaccel", "cuda",
        "-hwaccel_output_format", "cuda",
        "-ss", str(start),
        "-to", str(end),
        "-i", input_path,
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", "1080x1920",
        "-r", str(fps),
        "-i", "-",
        "-map", "1:v:0",
        "-map", "0:a:0",
        "-c:v", "h264_nvenc",
        "-pix_fmt", "yuv420p",
        '-preset', 'p1',
        '-b:v', '1M',
        "-c:a", "aac",
        "-b:a", "192k",
        '-movflags', '+faststart',
        output_path
    ]

    crop_params = precompute_crop_params(width, height, crop)

    with subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE) as pipe:
        for i in range(start_frame, end_frame, batch_size):
            batch_end = min(i + batch_size, end_frame)
            indices = list(range(i, batch_end))

            frames_batch = vr.get_batch(indices).asnumpy()
            processed = process_batch_gpu(frames_batch, crop_params, i, crop, centers_x)

            for frame in processed:
                pipe.stdin.write(frame.tobytes())
            
            del frames_batch, processed
            cp.get_default_memory_pool().free_all_blocks()
            gc.collect()

        pipe.stdin.close()
        pipe.wait()


@shared_task
def pre_render_clip(clip_id):
    logger.info(f'Start pre-render {clip_id}')
    try:
        clip = Clip.objects.get(id=clip_id)
        clip.status = 'processing'
        clip.save()

        input_path = f'{FILES_DIR}/sources/{clip.project.video_filename}'
        output_path = f'{FILES_DIR}/clips/{clip_id}.mp4'

        with open(f'{FILES_DIR}/sources/{clip.project.tracking_filename}', 'rb') as f:
            tracking = pickle.load(f)

        
        pre_render(
            input_path = input_path,
            centers_x = tracking,
            output_path = output_path,
            crop = clip.crop,
            start = clip.start,
            end = clip.end,
            batch_size=32
        )


        clip.video_filename = f'{clip_id}.mp4'
        clip.status = 'done'
        clip.save()
        logger.info(f"Clip {clip_id} pre-rendered")

    except Exception as e:
        clip.status = 'error'
        clip.save()
        logger.error(f"Error during pre-render task: {e}")
        raise









def ass_time_to_seconds(t):
    h, m, s = t.split(":")
    s, ms = s.split(".")
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/100

def seconds_to_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{ms:02d}"

def generate_ass(
    project_ass_path: str,
    clip_start: float,
    clip_end: float, 
    overlay,
    output_ass_path: str
):
    lines = Path(f'{FILES_DIR}/sources/{project_ass_path}').read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines):
        if line.startswith("PlayResX:"):
            lines[i] = "PlayResX: 1080"
        elif line.startswith("PlayResY:"):
            lines[i] = "PlayResY: 1920"

    new_lines = []
    styles_section = []
    events_section = []
    styles_start = False
    events_start = False

    for line in lines:
        if line.strip() == "[V4+ Styles]":
            styles_start = True
            events_start = False
            new_lines.append(line)
            continue
        elif line.strip() == "[Events]":
            events_start = True
            styles_start = False
            new_lines.append(line)
            continue
        elif line.startswith("[") and line.endswith("]"):
            styles_start = False
            events_start = False
            new_lines.append(line)
            continue

        if styles_start:
            styles_section.append(line)
        elif events_start:
            events_section.append(line)
        else:
            new_lines.append(line)

    styles_section = [s for s in styles_section if not s.startswith("Style:CustomStyle")]

    hex_color = overlay.font_color.lstrip("#")
    r = hex_color[0:2]
    g = hex_color[2:4]
    b = hex_color[4:6]
    alpha = "00"
    primary_color = f"&H{alpha}{b}{g}{r}&"

    custom_style = (
        # f"Style: CustomStyle,Open Sans Semibold, {overlay.font_size},"
        f"Style: CustomStyle,Open Sans,{overlay.font_size},"
        f"{primary_color},&H000000FF,&H00000000,&H64000000,"
        "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1"
    )
    styles_section.append(custom_style)

    filtered_events = []
    for line in events_section:
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            start_t = parts[1]
            end_t = parts[2]
            start_sec = ass_time_to_seconds(start_t) - clip_start
            end_sec = ass_time_to_seconds(end_t) - clip_start

            if end_sec < 0 or start_sec > (clip_end - clip_start):
                # Полностью вне клипа - пропускаем
                continue

            # Клипуем по краям, если субтитры выходят за границы клипа
            if start_sec < 0:
                start_sec = 0
            if end_sec > (clip_end - clip_start):
                end_sec = clip_end - clip_start

            # Переводим обратно в строку для .ass
            parts[1] = seconds_to_ass_time(start_sec)
            parts[2] = seconds_to_ass_time(end_sec)

            text = re.sub(r"[^\w\s]", "", parts[9])

            x_pos = int((overlay.x1 + overlay.x2) / 2)
            y_pos = int((overlay.y1 + overlay.y2) / 2)
            text = f"{{\\pos({x_pos},{y_pos})}}{text}"

            parts[3] = "CustomStyle"
            parts[9] = text
            line = ",".join(parts)

            filtered_events.append(line)
        else:
            filtered_events.append(line)

    out_lines = []

    for line in new_lines:
        out_lines.append(line)
        if line.strip() == "[V4+ Styles]":
            out_lines.extend(styles_section)
        elif line.strip() == "[Events]":
            out_lines.extend(filtered_events)

    Path(output_ass_path).write_text("\n".join(out_lines), encoding="utf-8")


def wrap_text_precise(text, font_path, font_size, max_width_px):
    font = ImageFont.truetype(font_path, font_size)
    lines = []
    words = text.split()
    line = ""
    for word in words:
        test_line = line + (" " if line else "") + word
        w= font.getlength(test_line)
        if w <= max_width_px:
            line = test_line
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines, font


@shared_task
def render_clip(clip_id):
    logger.info(f'Start render {clip_id}')
    clip = None
    try:
        clip = Clip.objects.get(id=clip_id)
        clip.status = 'processing'
        clip.save()

        input_path = f"{FILES_DIR}/clips/{clip_id}.mp4"
        output_path = f"{FILES_DIR}/clips/rendered_{clip_id}.mp4"


        input_args = [input_path]
        filter_parts = []
        last_output = "0:v"

        input_index = 1



        for image_overlay in ImageOverlay.objects.filter(clip_id=clip_id):
            img_path = f"{FILES_DIR}/overlays/{image_overlay.image_filename}"
            input_args.append(img_path)

            target_width = int(image_overlay.x2 - image_overlay.x1)
            target_height = int(image_overlay.y2 - image_overlay.y1)

            filter_parts.append(
                f"[{input_index}:v] scale={target_width}:{target_height} [ovr{input_index}];"
                f"[{last_output}][ovr{input_index}] overlay={int(image_overlay.x1)}:{int(image_overlay.y1)}:"
                f"enable='between(t,{image_overlay.start},{image_overlay.end})'[v{input_index}]"
            )

            last_output = f"v{input_index}"
            input_index += 1



        for text_overlay in TextOverlay.objects.filter(clip_id=clip_id):
            box_w = text_overlay.x2 - text_overlay.x1
            box_h = text_overlay.y2 - text_overlay.y1

            lines, font = wrap_text_precise(text_overlay.text, '/home/dev/workspace/shidlovskiy/viraly-backend/backend/OpenSans-Semibold.ttf', text_overlay.font_size, box_w)
            bbox = font.getbbox("Й")
            line_height = bbox[3] - bbox[1] + 10
            
            for i, line in enumerate(lines):
                x_pos = text_overlay.x1 + (box_w - font.getlength(line)) / 2
                y_pos = text_overlay.y1 + (box_h - line_height * len(lines)) / 2 + i * line_height
                filter_parts.append(
                    f"[{last_output}] drawtext=text='{line}':"
                    f"fontfile='/home/dev/workspace/shidlovskiy/viraly-backend/backend/OpenSans-Semibold.ttf':"
                    f"fontcolor={text_overlay.font_color.replace('#', '0x')}:"
                    f"fontsize={text_overlay.font_size}:"
                    f"x={x_pos}:"
                    f"y={y_pos}:"
                    f"borderw=3:bordercolor=black:"
                    f"enable='between(t,{text_overlay.start},{text_overlay.end})'"
                    f"[v{input_index}]"
                )
                last_output = f"v{input_index}"
                input_index += 1
        

        subtitles_overlay = SubtitlesOverlay.objects.filter(clip_id=clip_id).first()
        if subtitles_overlay and clip.project.subtitles_filename:
            subtitles_overlay.x1 = 0
            subtitles_overlay.x2 = 1080

            subtitles_overlay.y1 = 1300
            subtitles_overlay.y2 = 1920


            tmp_ass_filename = f"tmp_subs_{uuid.uuid4().hex}.ass"
            tmp_ass_path = f"{FILES_DIR}/{tmp_ass_filename}"

            generate_ass(
                project_ass_path=clip.project.subtitles_filename,
                clip_start=clip.start,
                clip_end=clip.end,
                overlay=subtitles_overlay,
                output_ass_path=tmp_ass_path
            )


            filter_parts.append(
                f"[{last_output}] subtitles='{'/home/dev/workspace/shidlovskiy/viraly-backend/backend/' + tmp_ass_path}' [v{input_index}]"
            )
            last_output = f"v{input_index}"
            input_index += 1



        filter_complex = ";".join(filter_parts)
        final_video = f"[{last_output}]"

        cmd = [
            "ffmpeg", "-y",
            "-loglevel", "debug",
            "-hwaccel", "cuda",
            # "-hwaccel_output_format", "cuda"
        ]

        for inp in input_args:
            cmd.extend(["-i", inp])

        if filter_complex:
            cmd.extend(["-filter_complex", filter_complex, "-map", final_video, "-map", "0:a?"])
        else:
            cmd.extend(["-map", "0:v", "-map", "0:a?"])


        cmd.extend([
            "-c:v", "h264_nvenc",
            "-pix_fmt", "yuv420p",
            '-preset', 'p1',
            '-b:v', '1M',
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            output_path
        ])

        subprocess.run(cmd, check=True, timeout=300)

        if subtitles_overlay:
            os.remove(tmp_ass_path)

        clip.rendered_video_filename = f"rendered_{clip_id}.mp4"
        clip.status = "done"
        clip.save()

        logger.info(f"Clip {clip_id} rendered successfully")

    except Exception as e:
        if clip:
            clip.status = "error"
            clip.save()
        logger.exception(f"Error during render task for clip {clip_id}: {e}")
        raise